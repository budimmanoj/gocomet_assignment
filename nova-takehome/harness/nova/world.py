"""Everything we hold on the report date, indexed for the detectors.

Only documents received by the end of `as_of` exist. Each fact keeps where it came from (the citation), when it
arrived, and how much authority its source has (glossary levels 1-5).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from pathlib import Path

from . import docs as D
from . import llm
from .common import dec, find_dates, master_awb, norm_invoice, parse_date, to_date


class World:
    def __init__(self, records: list[dict], as_of: date, feedback: list[dict] | None = None, state_dir=None):
        self.as_of = as_of
        self.warnings: list[str] = []
        held = [r for r in records if r.get("received") and to_date(r["received"]) <= as_of]
        self.records = {r["id"]: r for r in held}
        # pass 1 finds the contracts, whose Annex E labels then read every invoice line in pass 2
        aliases = {k: list(v) for k, v in D.DEFAULT_ALIASES.items()}
        for r in held:
            for f in D.parse_record(r):
                if f["type"] == "contract":
                    for code, a in f["aliases"].items():
                        aliases.setdefault(code, [])
                        aliases[code] += [x for x in a["labels"] if x not in aliases[code]]
                    for code, a in f["accessorials"].items():
                        aliases.setdefault(code, [])
                        if a["name"] not in aliases[code]:
                            aliases[code].append(a["name"])
        self.index = D.label_index(aliases)
        self.contracts: dict[str, dict] = {}
        self.amendments: list[dict] = []
        self.notices: list[dict] = []
        self.waivers: list[dict] = []
        self.extensions: list[dict] = []
        self.pickups: dict[str, list[dict]] = defaultdict(list)
        self.milestones: dict[str, list[dict]] = defaultdict(list)
        self.customs: dict[str, list[dict]] = defaultdict(list)
        self.invoice_copies: dict[str, list[dict]] = defaultdict(list)
        self.credit_notes: list[dict] = []
        self.awbs: dict[str, dict] = {}
        self.dgds: dict[str, dict] = {}
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.ledgers: list[dict] = []
        self.emails: dict[str, dict] = {}
        self.annex_revisions: list[dict] = []
        self.reader = llm.Reader(Path(state_dir) / "llm_cache") if state_dir else None
        for r in sorted(held, key=lambda x: (x["received"], x["id"])):
            recv = to_date(r["received"])
            for f in D.parse_record(r, self.index):
                if f["type"] == "invoice" and self.reader is not None:
                    self._check_invoice(f, r)
                if f["type"] == "contract" and self.reader is not None:
                    self._check_contract(f, r)
                f["received"] = recv
                f["received_ts"] = r["received"]
                f["batch"] = r["batch"]
                f["email_ref"] = r["id"]
                self._add(f)
        self.feedback = feedback or []
        for inv_id, copies in self.invoice_copies.items():
            copies.sort(key=lambda x: (x["received_ts"], x["ref"]))

    def _check_invoice(self, inv: dict, rec: dict) -> None:
        """When the lines we read don't add up to the printed total, ask the model which printed lines are charges.
        It must copy each line exactly; we keep only lines that are really on the page, then parse them ourselves."""
        total = inv.get("total")
        got = sum((x["amount"] for x in inv["lines"]), dec("0"))
        if total is None or abs(got - total) <= dec("0.02"):
            return
        att = next((a for a in rec.get("attachments", []) if a["ref"] == inv["ref"]), None)
        if not att or not llm.enabled():
            inv["parse_gap"] = str(total - got)
            self.warnings.append(f"{inv['ref']}: lines add up to {got}, printed total {total}")
            return
        task = ("This is a carrier invoice. List every charge line (freight, surcharges, fees, duties, taxes, late "
                "fees; not subtotals or totals). For each give: page (1-based), line (the printed line copied exactly, "
                "character for character), awb, lane, description, quantity, unit, rate, percent, base, amount. "
                'JSON: {"lines": [...]}')
        text = "\n".join(f"--- page {i + 1} ---\n{p}" for i, p in enumerate(att["pages"]))
        data = self.reader.extract(task, text) or {}
        lines = []
        for x in data.get("lines") or []:
            page, printed = int(x.get("page") or 1), str(x.get("line") or "")
            if not printed or not (1 <= page <= len(att["pages"])) or \
                    " ".join(printed.split()) not in " ".join(att["pages"][page - 1].split()):
                continue
            f = D.parse_line(printed, inv.get("dayfirst", True)) or {"nums": [], "words": [], "text": printed}
            for k_src, k_dst in (("awb", "awb"), ("lane", "lane"), ("quantity", "qty"), ("percent", "pct")):
                if f.get(k_dst) is None and x.get(k_src) not in (None, ""):
                    f[k_dst] = dec(x[k_src]) if k_dst in ("qty", "pct") else str(x[k_src])
            f.setdefault("desc", x.get("description") or "")
            f["nums"] = f.get("nums") or [v for v in (dec(x.get("rate")), dec(x.get("base")), dec(x.get("amount")))
                                          if v is not None]
            if not f["nums"]:
                continue
            D._assign(f)
            if dec(x.get("amount")) is not None:
                f["amount"] = dec(x["amount"])
            f.update(page=page, code=D.charge_code(f.get("desc") or x.get("description") or "", self.index),
                     cite=D.cite(inv["ref"], page, printed), via="model")
            for k in ("mawb", "date", "period", "unit", "rate", "base", "line_no", "currency"):
                f.setdefault(k, None)
            lines.append(f)
        if lines and abs(sum((x["amount"] for x in lines), dec("0")) - total) <= dec("0.02"):
            inv["lines"] = lines
            inv["read_by_model"] = True
        else:
            inv["parse_gap"] = str(total - got)

    # contract terms the parser may miss in unseen wording: field -> (what to ask, value kind, citation key)
    CONTRACT_FIELDS = {
        "effective": ("the date the agreement takes effect", "date", "term_cite"),
        "end": ("the last day of the initial term", "date", "term_cite"),
        "payment_days": ("invoice payment terms, in days", "int", None),
        "late_pct": ("the late payment fee, in percent per month", "number", "late_cite"),
        "auto_renew": ("whether the agreement renews automatically (true/false)", "bool", "renew_cite"),
        "notice_days": ("days of notice needed to stop renewal", "int", "renew_cite"),
    }

    def _check_contract(self, c: dict, rec: dict) -> None:
        """Terms the parser couldn't find are asked of the model, which must quote the sentence that states each one.
        A value is kept only when its quote is on the cited page and the quote contains that value."""
        want = [k for k in self.CONTRACT_FIELDS if c.get(k) is None or (k == "auto_renew" and not c.get("renew_cite"))]
        att = next((a for a in rec.get("attachments", []) if a["ref"] == c["ref"]), None)
        if not want or not att or not llm.enabled():
            return
        task = ("This is a freight services contract. For each field below, find the clause that states it. Give the "
                "value, the page (1-based) and the sentence that states it, copied exactly. Use null when the contract "
                "doesn't say. Dates as YYYY-MM-DD. Fields:\n" +
                "\n".join(f"- {k}: {self.CONTRACT_FIELDS[k][0]}" for k in want) +
                '\nJSON: {"<field>": {"value": ..., "page": n, "quote": "..."}, ...}')
        text = "\n".join(f"--- page {i + 1} ---\n{p}" for i, p in enumerate(att["pages"]))
        data = self.reader.extract(task, text) or {}
        for k in want:
            x = data.get(k)
            if not isinstance(x, dict) or x.get("value") is None:
                continue
            quote, kind = " ".join(str(x.get("quote") or "").split()), self.CONTRACT_FIELDS[k][1]
            try:
                page = int(x.get("page") or 0)
            except (TypeError, ValueError):
                continue
            if len(quote.replace(" ", "")) < 12 or not 1 <= page <= len(att["pages"]) or \
                    quote not in " ".join(att["pages"][page - 1].split()):
                continue
            v = x["value"]
            if kind == "date":
                v = parse_date(str(v))
                if v is None or v not in find_dates(quote):
                    continue
            elif kind in ("int", "number"):
                v = dec(str(v))
                if v is None or v not in {dec(n) for n in re.findall(r"\d+(?:\.\d+)?", quote)}:
                    continue
                v = int(v) if kind == "int" else v
            elif kind == "bool":
                if not isinstance(v, bool):
                    continue
            c[k] = v
            ck = self.CONTRACT_FIELDS[k][2]
            if ck and not c.get(ck):
                c[ck] = D.cite(c["ref"], page, quote)
            c.setdefault("read_by_model", []).append(k)
        if c.get("read_by_model"):
            self.warnings.append(f"{c['ref']}: contract terms read by the model: {', '.join(c['read_by_model'])}")

    def _add(self, f: dict) -> None:
        t = f["type"]
        if t == "contract" and f.get("contract_id"):
            if f["contract_id"] not in self.contracts:
                self.contracts[f["contract_id"]] = f
        elif t == "amendment":
            self.amendments.append(f)
        elif t == "rate_notice":
            self.notices.append(f)
        elif t == "waiver":
            self.waivers.append(f)
        elif t == "extension":
            self.extensions.append(f)
        elif t == "picked_up":
            self.pickups[f["awb"]].append(f)
        elif t == "milestone":
            self.milestones[f["awb"]].append(f)
        elif t == "customs_hold":
            self.customs[f["awb"]].append(f)
        elif t == "invoice" and f.get("invoice_id"):
            self.invoice_copies[f["invoice_id"]].append(f)
        elif t == "credit_note":
            self.credit_notes.append(f)
        elif t == "awb" and f.get("awb"):
            self.awbs[f["awb"]] = f
        elif t == "dgd" and f.get("awb"):
            self.dgds[f["awb"]] = f
        elif t == "tracking":
            for e in f["events"]:
                self.events[e["awb"]].append(e)
        elif t == "ledger":
            self.ledgers.append(f)
        elif t == "email":
            self.emails[f["ref"]] = f
        elif t == "annex_revision":
            self.annex_revisions.append(f)

    # ---- lookups ----------------------------------------------------------------------------------------------------
    def invoice(self, inv_id: str) -> dict | None:
        c = self.invoice_copies.get(norm_invoice(inv_id))
        return c[0] if c else None

    def invoices(self) -> list[dict]:
        """One per invoice number (its first copy), oldest first."""
        out = [c[0] for c in self.invoice_copies.values()]
        return sorted(out, key=lambda x: (x.get("date") or x["received"], x["received_ts"], x["invoice_id"]))

    def contract_for(self, inv: dict) -> dict | None:
        cid = inv.get("contract_id")
        if cid in self.contracts:
            return self.contracts[cid]
        # no contract printed: among contracts in the invoice's currency that price one of its lanes, prefer the one
        # whose carrier sent it, then the one in force on the invoice date, then the most lanes in common
        lanes = {ln["lane"] for ln in inv.get("lines", []) if ln.get("lane")}
        em = self.emails.get(inv.get("email_ref") or "")
        dom = ((em or {}).get("sender", {}).get("email") or "").split("@")[-1]
        when = inv.get("date")
        best, best_score = None, None
        for c in self.contracts.values():
            common = lanes & {r["lane"] for r in c["rates"]}
            if c.get("currency") != inv.get("currency") or not common:
                continue
            sent_by = bool(dom) and any(p["email"].endswith("@" + dom) and p["party"] == c.get("carrier_party")
                                        for p in c.get("people", []))
            in_force = bool(when and c.get("effective") and c["effective"] <= when
                            and (not c.get("end") or when <= c["end"]))
            score = (sent_by, in_force, len(common))
            if best_score is None or score > best_score:
                best, best_score = c, score
        return best

    def ledger_row(self, inv_id: str) -> dict | None:
        inv_id = norm_invoice(inv_id)
        for led in sorted(self.ledgers, key=lambda x: x["received_ts"], reverse=True):
            for row in led["rows"]:
                if row["invoice_id"] == inv_id:
                    return row
        return None

    def latest_ledger(self) -> dict | None:
        return max(self.ledgers, key=lambda x: x["received_ts"]) if self.ledgers else None

    def person(self, c: dict, email: str | None = None, name: str | None = None) -> dict | None:
        for p in c.get("people", []):
            if email and p["email"] == (email or "").lower():
                return p
        if name:
            for p in c.get("people", []):
                if p["name"].lower() == name.lower():
                    return p
        return None

    def contact(self, c: dict, category: str, party: str | None = None) -> dict | None:
        party = party or c.get("carrier_party")
        for p in c.get("people", []):
            if p["party"] == party and category in p["categories"]:
                return p
        return None

    def authorised(self, c: dict, email: str, category: str, on: date | None = None) -> tuple[bool, dict | None]:
        """Is the sender the carrier's Schedule 1 person for this category (address must match)? A person's
        confirmed authority from feedback counts too, inside its scope. -> (ok, feedback item used or None)."""
        p = self.person(c, email=email)
        if p and p["party"] == c.get("carrier_party") and category in p["categories"]:
            return True, None
        for fb in self.feedback:
            fact = fb.get("fact") or {}
            if fb.get("decision") != "confirm" or fact.get("type") != "sender_authority":
                continue
            sc = (fb.get("scope") or {}).get("applies_to") or {}
            subj = fact.get("subject") or {}
            cats = (fact.get("value") or {}).get("categories") or []
            who = (sc.get("person") or subj.get("person") or "").lower()
            if category not in cats or (sc.get("category") and sc["category"] != category):
                continue
            if sc.get("contract_id") and sc["contract_id"] != c.get("contract_id"):
                continue
            sender_name = (p or {}).get("name") or self._name_for(email)
            if not sender_name or sender_name.lower() != who:
                continue
            if not _in_scope(fb, on):
                continue
            return True, fb
        return False, None

    def _name_for(self, email: str) -> str | None:
        for r in self.records.values():
            if r.get("from_addr") == (email or "").lower() and r.get("from_name"):
                return r["from_name"]
        return None

    # ---- shipment facts ---------------------------------------------------------------------------------------------
    def pickup(self, awb: str, fallback: date | None = None) -> tuple[date | None, str, dict | None]:
        """Pickup date by the glossary's order: tracking PICKED_UP, carrier 'picked up' email, AWB date, invoice."""
        for key in (awb, master_awb(awb)):
            for e in self.events.get(key, []):
                if e["event"] in ("PICKED_UP", "PICKUP", "COLLECTED_FROM_SHIPPER"):
                    return e["date"], "tracking", e["cite"]
        for key in (awb, master_awb(awb)):
            for e in self.pickups.get(key, []):
                return e["date"], "email", e["cite"]
        for key in (awb, master_awb(awb)):
            a = self.awbs.get(key)
            if a and a.get("date"):
                return a["date"], "awb", a.get("date_cite")
        return fallback, "invoice", None

    def dangerous_goods(self, awb: str) -> tuple[bool | None, bool | None, dict | None]:
        """-> (dry ice present, other dangerous goods present, citation). None = we hold nothing that says."""
        d = self.dgds.get(awb) or self.dgds.get(master_awb(awb))
        if d and d["items"]:
            dry = any(i["un"] == "1845" for i in d["items"])
            other = any(i["un"] != "1845" for i in d["items"])
            pick = next((i for i in d["items"] if (i["un"] == "1845") == (not other)), d["items"][0])
            return dry, other, pick["cite"]
        a = self.awbs.get(awb) or self.awbs.get(master_awb(awb))
        if a and a.get("un"):
            return "1845" in a["un"], any(u != "1845" for u in a["un"]), a.get("cw_cite")
        return None, None, None


def _in_scope(fb: dict, on: date | None) -> bool:
    sc = fb.get("scope") or {}
    a, b = to_date(sc.get("valid_from")), to_date(sc.get("valid_to"))
    if on is None:
        return True
    return (a is None or on >= a) and (b is None or on <= b)
