"""The six classes, conflicts and missing documents, computed from the World.

Pricing follows the contract on the pickup date: the MSA's Annex A for the period, replaced lane by lane by signed
amendments in force, and by a rate notice only when its sender is the carrier's Schedule 1 `rates` person (or a person
feedback confirmed). An amendment and an authorised notice that disagree under an "unranked" clause are a conflict.
A rate table an amendment names but we don't hold makes the key cannot_determine. All arithmetic is Decimal, rounded
half up to cents, line by line, as the glossary says.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, timedelta

from .common import (ZERO, add_months, dec, master_awb, month_key, norm_invoice, quarter_bounds, quarter_of, r2,
                     to_date)
from .world import World, _in_scope

OUTBOUND_CLASSES = ("overcharge", "duplicate", "waived_but_billed", "late_fee_not_owed")
QS_CORE = {"FRT", "FUEL", "SEC"}
NOT_QS = {"DUTY", "TAX", "LATE", "COST", "MARGIN"}
# charges a shipment carries once; storage, redelivery and customs work can legitimately be billed again
ONCE_PER_SHIPMENT = {"FRT", "FUEL", "SEC", "PEAK", "DG", "DRYICE"}
ADJUSTMENT_RE = re.compile(r"\b(adjust|correct|supplement|difference|balance|re-?bill|re-?weigh|amend)", re.I)


def new_item(cls: str, **kw) -> dict:
    it = {"class": cls, "verdict": "finding", "amount": None, "range": None, "deadline": None, "evidence": [],
          "missing_doc": None, "outbound": None, "internal": None, "conf": 0.9, "fb": [], "flags": set(),
          "contract_id": None, "lanes": set(), "relies": [], "native": None, "currency": "USD"}
    it.update(kw)
    return it


def add_ev(it: dict, *cites) -> None:
    for c in cites:
        if c and c.get("quote") and len("".join(c["quote"].split())) >= 12 and c not in it["evidence"]:
            it["evidence"].append(c)


# ---- rates --------------------------------------------------------------------------------------------------------------
def band_ok(band, w) -> bool:
    if band == ("min",):
        return False
    lo, hi = band
    return w >= dec(str(lo)) and (hi is None or w <= dec(str(hi)))


def pick_band(rows: list[dict], w) -> dict | None:
    hits = [r for r in rows if r["band"] != ("min",) and band_ok(r["band"], w)]
    if hits:
        return hits[0]
    below = [r for r in rows if r["band"] != ("min",) and dec(str(r["band"][0])) <= w]
    return max(below, key=lambda r: r["band"][0]) if below else None


def period_index(c: dict, d: date) -> int:
    ps = c["periods"]
    for i, p in enumerate(ps):
        if p["start"] and p["end"] and p["start"] <= d <= p["end"]:
            return i
    if ps and ps[-1]["end"] and d > ps[-1]["end"]:
        return len(ps) - 1
    return 0


def msa_rate(c: dict, lane: str, w, d: date) -> dict | None:
    i = period_index(c, d)
    rows = [r for r in c["rates"] if r["lane"] == lane]
    if not rows:
        return None
    rr = pick_band(rows, w)
    mn = next((r for r in rows if r["band"] == ("min",)), None)

    def val(r):
        return r["values"][min(i, len(r["values"]) - 1)] if r else None
    if not rr:
        return None
    return {"rate": val(rr), "min": val(mn), "cite": rr["cite"], "min_cite": mn["cite"] if mn else None,
            "source": "msa", "level": 1, "doc": c["ref"]}


def held_annex(W: World, name: str, lane: str) -> list[dict] | None:
    """Rates from a named annex revision if any document we hold carries it."""
    from . import docs as D
    for r in W.records.values():
        for att in r.get("attachments", []):
            text = "\n".join(att.get("pages") or [])
            if name.lower() in text[:400].lower() and "amendment no" not in text[:400].lower():
                rows = []
                for p, ln in D.lines_of(att["pages"]):
                    import re
                    mm = re.match(r"^(?P<lane>[A-Z]{2,5}\d{0,2}-[A-Z]{2,5}\d{0,2})\s+" + D.BAND_RE +
                                  r"\s+(?P<rates>[\d,.\s]+?)\s*(?:USD|INR|EUR)?$", ln)
                    if mm and mm.group("lane") == lane:
                        rows.append({"lane": lane, "band": D.parse_band(mm),
                                     "rate": dec(mm.group("rates").split()[-1]), "cite": D.cite(att["ref"], p, ln)})
                if rows:
                    return rows
    return None


def _rows_rate(rows, w, src, level, doc, received=None, effective=None):
    rr = pick_band(rows, w)
    if not rr:
        return None
    mn = next((r for r in rows if r["band"] == ("min",)), None)
    return {"rate": rr["rate"], "min": mn["rate"] if mn else None, "cite": rr["cite"],
            "min_cite": mn["cite"] if mn else None, "source": src, "level": level, "doc": doc,
            "received": received, "effective": effective}


def freight_decision(W: World, c: dict, lane: str, w, pickup: date) -> dict:
    """-> {"status": ok|conflict|missing|unknown, "options": [rate sources], "missing": {...}, "fb": [...]}"""
    out = {"status": "ok", "options": [], "missing": None, "fb": [], "extra_cites": []}
    base = msa_rate(c, lane, w, pickup)
    cid = c["contract_id"]
    # signed amendments in force on the pickup date, latest effective last
    amd = None
    for a in sorted([a for a in W.amendments if a.get("contract_id") == cid and a.get("signed")],
                    key=lambda a: (a.get("effective") or date.min, a["received_ts"])):
        if a.get("effective") and a["effective"] > pickup:
            continue
        rows = [r for r in a["rates"] if r["lane"] == lane]
        if rows:
            amd_r = _rows_rate(rows, w, "amendment", 1, a["ref"], a["received"], a["effective"])
            if amd_r:
                if amd_r["min"] is None and base:
                    amd_r["min"], amd_r["min_cite"] = base["min"], base["min_cite"]
                amd_r["amendment"] = a.get("amendment_ref")
                amd = amd_r
        for mref in a.get("missing_refs", []):
            if lane in mref["lanes"] and mref["from"] and pickup >= mref["from"]:
                rows2 = held_annex(W, mref["name"], lane)
                if rows2:
                    amd = _rows_rate(rows2, w, "amendment", 1, rows2[0]["cite"]["doc"], a["received"], mref["from"])
                    if amd and amd["min"] is None and base:
                        amd["min"], amd["min_cite"] = base["min"], base["min_cite"]
                    out["missing"] = None
                else:
                    out["missing"] = {"name": mref["name"], "cite": mref["cite"], "amendment": a}
                    amd = None
    # rate notices covering the pickup date for this lane
    auth_notices, accepted = [], []
    for n in W.notices:
        if n.get("contract_id") and n["contract_id"] != cid:
            continue
        if not n.get("contract_id") and lane not in {r["lane"] for r in c["rates"]}:
            continue
        rows = [r for r in n["rows"] if r["lane"] == lane]
        if not rows or not n.get("start") or pickup < n["start"] or (n.get("end") and pickup > n["end"]):
            continue
        ok, fbi = W.authorised(c, n["sender"]["email"], "rates", pickup)
        opt = _rows_rate(rows, w, "notice", 2, n["ref"], n["received"], n["start"])
        if not opt:
            continue
        if opt["min"] is None and base:
            opt["min"], opt["min_cite"] = base["min"], base["min_cite"]
        if ok:
            opt["fb"] = [fbi] if fbi else []
            auth_notices.append(opt)
        # feedback: "rate_accepted" makes the named notice the rate for that contract and lane inside its dates
        for fb in W.feedback:
            fact = fb.get("fact") or {}
            if fact.get("type") != "rate_accepted":
                continue
            subj, val = fact.get("subject") or {}, fact.get("value") or {}
            ap = (fb.get("scope") or {}).get("applies_to") or {}
            if (ap.get("contract_id") or subj.get("contract_id")) not in (None, cid):
                continue
            if (ap.get("lane") or subj.get("lane")) not in (None, lane):
                continue
            if not _in_scope(fb, pickup):
                continue
            sent_by = (val.get("sent_by") or "").lower()
            if sent_by and sent_by != (n["sender"].get("name") or "").lower():
                continue
            if val.get("sent_on") and to_date(val["sent_on"]) and n["received"] != to_date(val["sent_on"]):
                continue
            o2 = dict(opt)
            o2["fb"] = [fb]
            o2["level"] = 2
            accepted.append(o2)
    if out["missing"] and not amd:
        out["status"] = "missing"
        return out
    notice = (auth_notices or accepted)
    notice = max(notice, key=lambda o: (o["effective"] or date.min, o["received"])) if notice else None
    if notice is not None and notice in accepted and notice not in auth_notices:
        out["fb"] += notice["fb"]
    # feedback "resolve_conflict": use the named source for this contract and lane from valid_from
    for fb in W.feedback:
        fact = fb.get("fact") or {}
        if fact.get("type") != "precedence" or fb.get("decision") != "resolve_conflict":
            continue
        ap = (fb.get("scope") or {}).get("applies_to") or {}
        subj = fact.get("subject") or {}
        if (ap.get("contract_id") or subj.get("contract_id")) not in (None, cid):
            continue
        if (ap.get("lane") or subj.get("lane")) not in (None, lane) or not _in_scope(fb, pickup):
            continue
        use = str((fact.get("value") or {}).get("use", "")).lower()
        if amd and notice:
            later_signed = amd.get("received") and fb.get("decided_at") and \
                amd["received"] > to_date(fb["decided_at"])
            chosen = amd if ("amend" in use or later_signed) else notice
            out["options"] = [chosen]
            out["fb"].append(fb)
            return out
    if amd and notice and notice["rate"] != amd["rate"]:
        if c.get("unranked"):
            out["status"] = "conflict"
            out["options"] = [amd, notice]
            out["extra_cites"] = [c.get("unranked_cite")]
            return out
        out["options"] = [amd]
        return out
    if notice:
        out["options"] = [notice]
        out["fb"] += notice.get("fb") or []
    elif amd:
        out["options"] = [amd]
    elif base:
        out["options"] = [base]
    else:
        out["status"] = "unknown"
    return out


# ---- one invoice, line by line ------------------------------------------------------------------------------------------
def acc(c: dict, code: str) -> dict | None:
    return (c.get("accessorials") or {}).get(code)


def storage_days(W: World, awb: str, free: int) -> tuple[int | None, list]:
    ev = W.events.get(awb) or W.events.get(master_awb(awb)) or []
    arr = [e for e in ev if e["event"] == "ARRIVED_FACILITY"]
    rel = [e for e in ev if e["event"] in ("DELIVERED", "COLLECTED_BY_CONSIGNEE", "RELEASED")]
    if not arr or not rel:
        return None, []
    a, r = arr[-1], rel[-1]
    return max(0, (r["date"] - a["date"]).days - free), [a["cite"], r["cite"]]


def analyse_invoice(W: World, inv: dict, skip_lines: set) -> dict:
    """-> per-option overcharge per line. Lines in skip_lines (duplicates, waived, late fees) are left to their class."""
    c = W.contract_for(inv)
    res = {"invoice": inv, "contract": c, "lines": [], "status": "ok", "missing": None, "conflict_opts": None,
           "lanes": set(), "pickup_sources": set(), "fb": [], "extra_cites": [], "notes": []}
    if not c:
        res["status"] = "no_contract"
        return res
    groups: dict[str, list] = defaultdict(list)
    for i, ln in enumerate(inv["lines"]):
        ln["_id"] = (inv["invoice_id"], i)
        groups[ln["awb"] or f"~{ln.get('period') or ''}"].append(ln)
    for awb, lines in groups.items():
        frt = next((x for x in lines if x["code"] == "FRT"), None)
        w = (frt or {}).get("qty") or next((x["qty"] for x in lines if x["code"] in ("SEC", "PEAK") and x["qty"]), None)
        lane = next((x["lane"] for x in lines if x.get("lane")), None)
        if lane:
            res["lanes"].add(lane)
        ldate = next((x["date"] for x in lines if x.get("date")), None)
        pickup, psrc, pcite = (W.pickup(awb, ldate) if not awb.startswith("~") else (inv.get("date"), "invoice", None))
        if pickup is None:
            pickup = inv.get("date") or W.as_of
        res["pickup_sources"].add(psrc)
        # chargeable weight: the AWB's own figure wins when the invoice bills more
        awb_doc = W.awbs.get(awb)
        w_cite = None
        if w is not None and awb_doc and awb_doc.get("chargeable") and not awb_doc.get("master") \
                and awb_doc["chargeable"] < w:
            w, w_cite = awb_doc["chargeable"], awb_doc.get("cw_cite")
        dec_ = freight_decision(W, c, lane, w, pickup) if (frt and lane and w is not None) else None
        if dec_:
            res["fb"] += dec_["fb"]
            if dec_["status"] == "missing":
                res["status"] = "missing"
                res["missing"] = {**dec_["missing"], "lane": lane}
            elif dec_["status"] == "conflict":
                res["status"] = "conflict" if res["status"] == "ok" else res["status"]
                res["extra_cites"] += dec_["extra_cites"]
        opts = (dec_["options"] if dec_ and dec_["options"] else [None])
        fuel = (c.get("fuel") or {}).get(month_key(pickup))
        for ln in lines:
            if ln["_id"] in skip_lines:
                continue
            per_opt = []
            for o in opts:
                exp, cites, why = expected_line(W, c, ln, o, w, pickup, fuel, frt, awb, inv, w_cite)
                per_opt.append((exp, cites, why))
            billed = ln["amount"]
            res["lines"].append({"line": ln, "awb": awb, "lane": lane, "pickup": pickup, "psrc": psrc, "pcite": pcite,
                                 "billed": billed, "opts": per_opt, "decision": dec_})
    return res


def expected_line(W, c, ln, o, w, pickup, fuel, frt, awb, inv, w_cite):
    """-> (expected amount or None when we don't check it, citations, short reason)."""
    code = ln["code"]
    if code == "FRT":
        if not o or o.get("rate") is None or w is None:
            return None, [], ""
        exp = r2(o["rate"] * w)
        cites = [o["cite"], c.get("pricing_cite"), w_cite]
        if o.get("min") is not None and exp < o["min"]:
            exp = o["min"]
            cites.append(o.get("min_cite"))
            cites.append(c.get("minimum_cite"))
        return exp, cites, f"rate {o['rate']} ({o['source']})"
    if code == "FUEL":
        if not fuel:
            return None, [], ""
        base = None
        if frt is not None:
            e, _, _ = expected_line(W, c, frt, o, w, pickup, fuel, frt, awb, inv, w_cite)
            base = e
        if base is None:
            base = ln.get("base")
        if base is None:
            return None, [], ""
        return r2(fuel["pct"] / 100 * base), [fuel["cite"], c.get("fuel_cite"), c.get("pricing_cite")], \
            f"fuel {fuel['pct']}%"
    a = acc(c, code) if code else None
    if code == "SEC":
        if not a or w is None:
            return None, [], ""
        return r2(a["fee"] * w), [a["cite"]], "security per kg"
    if code == "PEAK":
        if not a or w is None:
            return None, [], ""
        if a.get("months") and pickup.month not in a["months"]:
            return ZERO, [a["cite"], c.get("pricing_cite")], "peak outside its months"
        return r2(a["fee"] * w), [a["cite"]], "peak"
    if code in ("DG", "DRYICE"):
        dry, other, dcite = W.dangerous_goods(awb)
        if dry is None and other is None:
            return None, [], ""
        if code == "DG":
            owed = bool(other)
            return (a["fee"] if (a and owed) else (ln["amount"] if owed else ZERO)), \
                [dcite, c.get("dryice_cite") if not owed else None, c.get("mixed_cite")], "dangerous goods"
        owed = bool(dry) and not other
        return (a["fee"] if (a and owed) else (ln["amount"] if owed else ZERO)), \
            [dcite, c.get("mixed_cite") if other else c.get("dryice_cite")], "dry ice"
    if code == "STOR":
        if not a or c.get("storage_free_days") is None:
            return None, [], ""
        days, sc = storage_days(W, awb, c["storage_free_days"])
        if days is None:
            return None, [], ""
        return r2(a["fee"] * days), [a["cite"], c.get("storage_cite")] + sc, f"{days} storage days"
    if code == "DLV":
        ev = W.events.get(awb) or W.events.get(master_awb(awb)) or []
        ms = W.milestones.get(awb, [])
        names = {e["event"] for e in ev} | {m["event"] for m in ms}
        if "COLLECTED_BY_CONSIGNEE" in names and "DELIVERED" not in names and "OUT_FOR_DELIVERY" not in names:
            col = next((e["cite"] for e in ev if e["event"] == "COLLECTED_BY_CONSIGNEE"), None)
            return ZERO, [col, c.get("delivery_cite")], "collected, not delivered"
        return (a["fee"] if a else None), ([a["cite"]] if a else []), "delivery"
    if code == "CUSTOMS":
        holds = W.customs.get(awb, [])
        if holds and any(h.get("reason") and "CARRIER" in h["reason"].upper() for h in holds):
            return ZERO, [holds[0]["cite"], c.get("customs_cite")], "hold caused by the carrier"
        return (a["fee"] if a else None), ([a["cite"]] if a else []), "customs"
    if code in ("ACCT", "SPROG", "PPROG"):
        if not a:
            return None, [], ""
        q = ln.get("qty") or dec("1")
        return r2(a["fee"] * q), [a["cite"]], "monthly fee"
    return None, [], ""


# ---- money helpers ------------------------------------------------------------------------------------------------------
def to_usd(c: dict | None, amount, currency: str, on: date | None):
    """-> (usd, fx citation, missing month). Converted once, at Annex F for the invoice date's month."""
    if amount is None or currency in (None, "USD"):
        return amount, None, None
    fx = ((c or {}).get("fx") or {}).get(month_key(on)) if on else None
    if not fx:
        return None, None, month_key(on) if on else "?"
    return r2(amount / fx["rate"]), fx["cite"], None


def fx_missing_doc(W: World, c: dict, month: str) -> dict:
    tre = W.contact(c, "treasury")
    holder = {"party": c.get("carrier_party")}
    if tre:
        holder.update(person=tre["name"], role=tre["title"])
    return {"name": f"Annex F update (exchange rate for {month})", "holder": holder}


# ---- the run ------------------------------------------------------------------------------------------------------------
def run(W: World) -> list[dict]:
    items: list[dict] = []
    invs = W.invoices()
    dup_lines, dup_items = find_duplicates(W, invs)
    waived_lines, waiver_items = find_waivers(W, invs)
    items += dup_items + waiver_items
    skip = set(dup_lines) | set(waived_lines)
    for inv in invs:
        for ln in inv["lines"]:
            if ln["code"] == "LATE":
                skip.add((inv["invoice_id"], inv["lines"].index(ln)))
    for inv in invs:
        it = overcharge_item(W, inv, skip)
        if it:
            items.append(it)
    disputed = defaultdict(lambda: ZERO)
    for it in items:
        if it["verdict"] == "finding" and it["class"] in OUTBOUND_CLASSES and it.get("native") is not None:
            disputed[it["invoice_id"]] += it["native"]
    items += late_fee_items(W, invs, disputed, set(waived_lines))
    items += risk_items(W, disputed)
    items += cashback_items(W, invs)
    items += expiry_items(W)
    return items


def overcharge_item(W: World, inv: dict, skip: set) -> dict | None:
    an = analyse_invoice(W, inv, skip)
    c = an["contract"]
    if not c:
        return None
    it = new_item("overcharge", invoice_id=inv["invoice_id"], contract_id=c["contract_id"], lanes=an["lanes"],
                  currency=inv.get("currency") or "USD")
    it["fb"] = list({id(f): f for f in an["fb"]}.values())
    n_opts = max((len(x["opts"]) for x in an["lines"]), default=1)
    totals = []
    for k in range(n_opts):
        tot, wrong = ZERO, []
        for x in an["lines"]:
            exp, cites, why = x["opts"][min(k, len(x["opts"]) - 1)]
            if exp is None:
                continue
            diff = x["billed"] - exp
            if diff > dec("0.004"):
                tot += diff
                wrong.append((x, exp, cites, why))
        totals.append((tot, wrong))
    if an["status"] == "missing":
        miss = an["missing"]
        rates = W.contact(c, "rates")
        holder = {"party": c.get("carrier_party")}
        if rates:
            holder.update(person=rates["name"], role=rates["title"])
        it.update(verdict="cannot_determine", missing_doc={"name": miss["name"], "holder": holder},
                  outbound="request_document", conf=0.8)
        add_ev(it, miss["cite"])
        line = next((x for x in an["lines"] if x["lane"] == miss["lane"] and x["line"]["code"] == "FRT"), None)
        if line:
            add_ev(it, line["line"]["cite"])
        it["relies"].append(miss["amendment"])
        return it
    if an["status"] == "conflict" and n_opts >= 2:
        vals = []
        for tot, _ in totals:
            usd, fxc, mm = to_usd(c, tot, it["currency"], inv.get("date"))
            vals.append(usd if usd is not None else tot)
        lo, hi = min(vals), max(vals)
        if hi <= 0:
            return None
        it.update(verdict="conflict", range=[max(ZERO, lo), hi], outbound=None, conf=0.85)
        for x in an["lines"]:
            if x["decision"] and x["decision"]["status"] == "conflict":
                add_ev(it, *[o["cite"] for o in x["decision"]["options"]])
                add_ev(it, x["line"]["cite"])
        add_ev(it, *an["extra_cites"])
        return it
    tot, wrong = totals[0]
    if tot <= 0:
        return None
    # a billing credit the carrier already issued against this invoice comes off what is still owed back
    cred, ccites = credited(W, inv["invoice_id"])
    if cred:
        tot -= min(tot, cred)
        add_ev(it, *ccites)
        if tot <= 0:
            return None
    usd, fxc, missing_month = to_usd(c, tot, it["currency"], inv.get("date"))
    if missing_month:
        it.update(verdict="cannot_determine", missing_doc=fx_missing_doc(W, c, missing_month),
                  outbound="request_document", conf=0.75)
        add_ev(it, *[w[0]["line"]["cite"] for w in wrong])
        return it
    it.update(amount=usd, native=tot, outbound="dispute")
    for x, exp, cites, why in wrong:
        add_ev(it, x["line"]["cite"])
    for x, exp, cites, why in wrong:
        add_ev(it, *[ci for ci in cites if ci])
        if x["line"]["code"] in ("FRT", "FUEL"):
            add_ev(it, x["pcite"])
    add_ev(it, fxc)
    it["pickup_sources"] = {x["psrc"] for x, *_ in wrong if x["line"]["code"] in ("FRT", "FUEL")}
    if any(x["decision"] and x["decision"]["options"] and x["decision"]["options"][0].get("source") == "notice"
           for x, *_ in wrong):
        it["relies"] += [x["decision"]["options"][0] for x, *_ in wrong if x["decision"]]
    it["conf"] = 0.92
    if it["pickup_sources"] - {"tracking", "email"}:
        it["conf"] -= 0.1
    if inv.get("scan"):
        it["conf"] -= 0.08
    if it["currency"] != "USD":
        it["conf"] -= 0.03
    it["n_wrong"] = len(wrong)
    return it


# ---- duplicates ---------------------------------------------------------------------------------------------------------
def credited(W: World, inv_id: str | tuple, awb: str | None = None):
    """Billing credit notes that reference this invoice (or any of several), or this waybill."""
    ids = {inv_id} if isinstance(inv_id, str) else set(inv_id)
    tot = ZERO
    cites = []
    for cn in W.credit_notes:
        if cn["kind"] != "billing":
            continue
        hit = bool(ids & set(cn["invoice_refs"])) or (awb and any(ln["awb"] == awb for ln in cn["lines"]))
        if hit:
            # a credit itemised by waybill counts only its lines for this waybill; one that names no waybill
            # (a credit of the whole invoice) counts in full
            if awb and any(ln["awb"] for ln in cn["lines"]):
                tot += sum((ln["amount"] for ln in cn["lines"] if ln["awb"] == awb), ZERO)
            else:
                tot += cn["total"] or ZERO
            cites.append(cn["cite"])
    return tot, cites


def find_duplicates(W: World, invs: list[dict]) -> tuple[list, list[dict]]:
    seen: dict = {}
    per_inv: dict[str, list] = defaultdict(list)
    for inv in invs:
        for i, ln in enumerate(inv["lines"]):
            if ln["code"] in ("LATE", "TAX") or ln["amount"] is None:
                continue
            if ln["awb"]:
                key = ("awb", ln["awb"], ln["code"], ln["amount"])
            elif ln.get("period") and ln["code"]:
                key = ("period", ln["period"], ln["code"], ln["amount"])
            else:
                continue
            # a charge billed once per shipment, billed again on another invoice at a different amount
            loose = ("once", ln["awb"], ln["code"]) if ln["awb"] and ln["code"] in ONCE_PER_SHIPMENT else None
            if key in seen and seen[key][0]["invoice_id"] != inv["invoice_id"]:
                per_inv[inv["invoice_id"]].append((i, ln, seen[key]))
            elif loose in seen and seen[loose][0]["invoice_id"] != inv["invoice_id"] and \
                    not ADJUSTMENT_RE.search(ln.get("desc") or "") and \
                    not any(cn["kind"] == "billing" and seen[loose][0]["invoice_id"] in cn["invoice_refs"]
                            for cn in W.credit_notes):
                # a rebill after the original was credited, or a stated adjustment, is not a second charge
                per_inv[inv["invoice_id"]].append((i, ln, seen[loose]))
            else:
                seen.setdefault(key, (inv, ln))
                if loose:
                    seen.setdefault(loose, (inv, ln))
    lines, items = [], []
    for inv_id, hits in per_inv.items():
        inv = W.invoice(inv_id)
        c = W.contract_for(inv)
        tot = sum((ln["amount"] for _, ln, _ in hits), ZERO)
        cred, ccites = ZERO, []
        originals = tuple({inv_id} | {o[0]["invoice_id"] for _, _, o in hits})
        for awb in {ln["awb"] for _, ln, _ in hits if ln["awb"]}:
            a, cc = credited(W, originals, awb)
            cred += a
            ccites += cc
        if not ccites:
            a, cc = credited(W, originals)
            cred += a
            ccites += cc
        amt = tot - cred
        lines += [(inv_id, i) for i, _, _ in hits]
        if amt <= 0:
            continue
        it = new_item("duplicate", invoice_id=inv_id, contract_id=(c or {}).get("contract_id"),
                      currency=inv.get("currency") or "USD", lanes={ln["lane"] for _, ln, _ in hits if ln["lane"]})
        usd, fxc, mm = to_usd(c, amt, it["currency"], inv.get("date"))
        if mm:
            continue
        it.update(amount=usd, native=amt, outbound="dispute", conf=0.88)
        for _, ln, (oinv, oln) in hits:
            add_ev(it, ln["cite"], oln["cite"])
        if c:
            for _, ln, _ in hits:
                al = (c.get("aliases") or {}).get(ln["code"])
                if al and ln["desc"] and ln["desc"].split("(")[0].strip().lower() != al["labels"][0].lower():
                    add_ev(it, al["cite"])
        add_ev(it, *ccites, fxc)
        items.append(it)
    # the same invoice number sent again, asking for payment of an invoice already paid
    for inv_id, copies in W.invoice_copies.items():
        if len(copies) < 2 or inv_id in per_inv:
            continue
        row = W.ledger_row(inv_id)
        if not row or not (row["status"].startswith("paid") or row["status"].startswith("sched")):
            continue
        for cp in copies[1:]:
            em = W.emails.get(cp["email_ref"])
            if not em or not em["asks_payment"] or em["copy"]:
                continue
            if row["paid"] and row["paid"] > cp["received"]:
                continue
            first = copies[0]
            c = W.contract_for(first)
            it = new_item("duplicate", invoice_id=inv_id, contract_id=(c or {}).get("contract_id"),
                          currency=first.get("currency") or "USD")
            amt = first.get("total") or row.get("amount")
            usd, fxc, mm = to_usd(c, amt, it["currency"], first.get("date"))
            if mm or not usd:
                continue
            it.update(amount=usd, native=amt, outbound="dispute", conf=0.9, variant="resend")
            add_ev(it, row["cite"], em["pay_cite"], cp.get("total_cite"), fxc)
            items.append(it)
            break
    return lines, items


# ---- waivers ------------------------------------------------------------------------------------------------------------
def _waiver_contract(W: World, wv: dict) -> dict | None:
    for c in W.contracts.values():
        if W.person(c, email=wv["sender"]["email"]):
            return c
    dom = (wv["sender"]["email"] or "").split("@")[-1]
    for c in W.contracts.values():
        if any(p["email"].endswith("@" + dom) and p["party"] == c.get("carrier_party") for p in c["people"]):
            return c
    return None


def _condition_met(W: World, wv: dict) -> bool | None:
    import re
    t = wv.get("condition") or ""
    m = re.search(r"([A-Z]{2,}[A-Z0-9/\-]*\d)[^.]{0,60}?(?:paid|settled)\s+(?:in full\s+)?(?:by|before|on or before)\s+"
                  r"(\d{4}-\d{2}-\d{2})", t) or \
        re.search(r"(?:paid|settled|pay|settle)[^.]{0,40}?([A-Z]{2,}[A-Z0-9/\-]*\d)[^.]{0,40}?(?:by|before)\s+"
                  r"(\d{4}-\d{2}-\d{2})", t)
    if not m:
        return None
    row = W.ledger_row(m.group(1))
    by = to_date(m.group(2))
    return bool(row and row["paid"] and row["paid"] <= by)


def _waiver_targets(wv: dict, inv: dict) -> list[int]:
    out = []
    for i, ln in enumerate(inv["lines"]):
        if wv["code"] and ln["code"] != wv["code"]:
            continue
        if ln["code"] in ("TAX", "DUTY") or (ln["code"] == "LATE" and wv["code"] != "LATE"):
            continue
        hit = (ln["awb"] and (ln["awb"] in wv["awbs"] or master_awb(ln["awb"]) in wv["awbs"])) or \
            (ln.get("period") and ln["period"] in wv["months"] and not wv["awbs"]) or \
            (inv["invoice_id"] in wv["invoices"] and not wv["awbs"] and wv["code"])
        if hit:
            out.append(i)
    return out


def find_waivers(W: World, invs: list[dict]) -> tuple[list, list[dict]]:
    lines, per_inv = [], defaultdict(list)
    quoted_hits = defaultdict(list)
    for wv in W.waivers:
        if not (wv["awbs"] or wv["months"] or wv["invoices"]):
            continue
        c = _waiver_contract(W, wv)
        if not c:
            continue
        if wv["source"] == "own":
            ok, fbi = W.authorised(c, wv["sender"]["email"], "waivers", wv["received"])
            if not ok:
                continue
            if wv.get("condition"):
                met = _condition_met(W, wv)
                if not met:
                    continue
            for inv in invs:
                if W.contract_for(inv) is not c:
                    continue
                for i in _waiver_targets(wv, inv):
                    per_inv[inv["invoice_id"]].append((i, wv, fbi))
        else:
            qa = wv.get("quoted_author") or {}
            p = W.person(c, email=qa.get("email"), name=qa.get("name"))
            if not p or "waivers" not in p["categories"] or p["party"] != c.get("carrier_party"):
                continue
            for inv in invs:
                if W.contract_for(inv) is not c:
                    continue
                for i in _waiver_targets(wv, inv):
                    quoted_hits[inv["invoice_id"]].append((i, wv, p, c))
    items = []
    for inv_id, hits in per_inv.items():
        inv = W.invoice(inv_id)
        c = W.contract_for(inv)
        seen, amt = set(), ZERO
        it = new_item("waived_but_billed", invoice_id=inv_id, contract_id=c["contract_id"],
                      currency=inv.get("currency") or "USD")
        for i, wv, fbi in hits:
            if i in seen:
                continue
            seen.add(i)
            ln = inv["lines"][i]
            part = r2(ln["amount"] * wv["fraction"] / 100) if wv.get("fraction") else ln["amount"]
            cred, ccites = credited(W, inv_id, ln["awb"])
            part -= min(part, cred)
            amt += part
            p = W.person(c, email=wv["sender"]["email"])
            add_ev(it, wv["cite"], (p or {}).get("cite"), ln["cite"], c.get("waiver_cite"))
            if fbi:
                it["fb"].append(fbi)
            lines.append((inv_id, i))
        if amt <= 0:
            continue
        usd, fxc, mm = to_usd(c, amt, it["currency"], inv.get("date"))
        if mm:
            continue
        it.update(amount=usd, native=amt, outbound="dispute", conf=0.93)
        add_ev(it, fxc)
        items.append(it)
    for inv_id, hits in quoted_hits.items():
        if inv_id in per_inv:
            continue
        inv = W.invoice(inv_id)
        i, wv, p, c = hits[0]
        ln = inv["lines"][i]
        it = new_item("waived_but_billed", invoice_id=inv_id, contract_id=c["contract_id"], verdict="cannot_determine",
                      outbound="request_document", conf=0.75)
        qa = wv.get("quoted_author") or {}
        label = ln["desc"] or "charge"
        it["missing_doc"] = {"name": f"original email from {p['name']} waiving the {label} on AWB {ln['awb'] or ''}"
                                     .strip(),
                             "holder": {"party": p["party"], "person": p["name"], "role": p["title"]}}
        add_ev(it, wv["cite"], ln["cite"], c.get("waiver_cite"))
        lines += [(inv_id, x[0]) for x in hits]
        items.append(it)
    return lines, items


# ---- late fees ----------------------------------------------------------------------------------------------------------
def due_date(W: World, inv_id: str, c: dict | None) -> tuple[date | None, dict | None, dict | None, list]:
    """-> (due date, the extension used, the ledger row, feedback used)."""
    row = W.ledger_row(inv_id)
    inv = W.invoice(inv_id)
    due = (row or {}).get("due") or (inv or {}).get("due")
    used, fbs = None, []
    for ex in sorted(W.extensions, key=lambda e: e["received_ts"]):
        if ex["invoice_id"] != norm_invoice(inv_id) or not ex.get("new_due"):
            continue
        cc = c or (W.contract_for(inv) if inv else None)
        if not cc:
            continue
        ok, fbi = W.authorised(cc, ex["sender"]["email"], "payment_terms", ex["received"])
        if ok:
            due, used = ex["new_due"], ex
            if fbi:
                fbs.append(fbi)
    return due, used, row, fbs


def late_fee_items(W: World, invs: list[dict], disputed: dict, waived: set = frozenset()) -> list[dict]:
    items = []
    for inv in invs:
        c_inv = W.contract_for(inv)
        it = new_item("late_fee_not_owed", invoice_id=inv["invoice_id"], contract_id=(c_inv or {}).get("contract_id"),
                      currency=inv.get("currency") or "USD")
        tot = ZERO
        for i, ln in enumerate(inv["lines"]):
            if ln["code"] != "LATE" or not ln.get("late_ref") or (inv["invoice_id"], i) in waived:
                continue
            ref = ln["late_ref"]
            rinv = W.invoice(ref)
            c = (W.contract_for(rinv) if rinv else None) or c_inv
            if not c:
                continue
            due, ext, row, fbs = due_date(W, ref, c)
            if not row or not row.get("paid") or not due:
                continue
            days = (row["paid"] - due).days
            grace = c.get("grace_days") or 0
            pct = c.get("late_pct") or ln.get("pct")
            months = math.ceil(days / 30) if days > grace else 0
            principal = (ln.get("principal") or row.get("amount") or ZERO) - disputed.get(ref, ZERO)
            k = ln.get("late_month") or 1
            exp = ZERO
            if k <= months and pct:
                base, fees = principal, []
                for _ in range(k):
                    f = r2(pct / 100 * base)
                    fees.append(f)
                    if c.get("compounding"):
                        base += f
                exp = fees[-1]
            diff = ln["amount"] - exp
            if diff <= 0:
                continue
            tot += diff
            add_ev(it, ln["cite"], ext["cite"] if ext else None, row["cite"], c.get("late_cite"),
                   c.get("extension_cite") if ext else None)
            it["fb"] += fbs
        if tot <= 0:
            continue
        usd, fxc, mm = to_usd(c_inv, tot, it["currency"], inv.get("date"))
        if mm:
            continue
        it.update(amount=usd, native=tot, outbound="dispute", conf=0.9)
        add_ev(it, fxc)
        items.append(it)
    return items


def risk_items(W: World, disputed: dict) -> list[dict]:
    items = []
    led = W.latest_ledger()
    cands = {}
    if led:
        for row in led["rows"]:
            if row["status"] and not row["status"].startswith(("paid", "sched", "cancel", "void", "credited")):
                cands[row["invoice_id"]] = row
    for inv in W.invoices():
        if inv["invoice_id"] in cands:
            continue
        if led and inv["received"] <= led["received"] and W.ledger_row(inv["invoice_id"]):
            continue
        if led and W.ledger_row(inv["invoice_id"]):
            continue
        cands[inv["invoice_id"]] = None
    for inv_id, row in cands.items():
        inv = W.invoice(inv_id)
        c = W.contract_for(inv) if inv else None
        if not c or not c.get("late_pct"):
            continue
        due, ext, _, fbs = due_date(W, inv_id, c)
        if not due:
            continue
        gap = (due - W.as_of).days
        if not 0 < gap <= 14:
            continue
        principal = ((row or {}).get("amount") or (inv or {}).get("total") or ZERO) - disputed.get(inv_id, ZERO)
        if principal <= 0:
            continue
        fee = r2(c["late_pct"] / 100 * principal)
        cur = (inv or {}).get("currency") or (row or {}).get("currency") or "USD"
        usd, fxc, mm = to_usd(c, fee, cur, (inv or {}).get("date") or (row or {}).get("date"))
        if mm:
            continue
        it = new_item("late_fee_risk", invoice_id=inv_id, contract_id=c["contract_id"], amount=usd, native=fee,
                      currency=cur, deadline=due, internal="payment_reminder", conf=0.9, fb=fbs)
        add_ev(it, (row or {}).get("cite") or (inv or {}).get("header_cite"), ext["cite"] if ext else None,
               c.get("late_cite"), fxc)
        items.append(it)
    return items


# ---- cashback -----------------------------------------------------------------------------------------------------------
def qualifying(c: dict, inv: dict) -> tuple:
    codes = QS_CORE | set((c.get("accessorials") or {}).keys())
    q = sum((ln["amount"] for ln in inv["lines"] if ln["code"] in codes and ln["code"] not in NOT_QS), ZERO)
    unknown = [ln for ln in inv["lines"] if ln["code"] is None]
    return q, unknown


def spend(W: World, c: dict, invs: list[dict], start: date, end: date):
    """Qualifying spend in USD, the USD value of lines whose charge we couldn't name, and an INR month with no rate."""
    tot, unknown, missing = ZERO, ZERO, None
    for inv in invs:
        if W.contract_for(inv) is not c or not inv.get("date") or not start <= inv["date"] <= end:
            continue
        q, unk = qualifying(c, inv)
        cur = inv.get("currency") or "USD"
        usd, _, mm = to_usd(c, q, cur, inv["date"])
        if mm:
            if q or unk:
                missing = missing or mm
            continue
        tot += usd
        if unk:
            unknown += to_usd(c, sum((ln["amount"] or ZERO for ln in unk), ZERO), cur, inv["date"])[0] or ZERO
    for cn in W.credit_notes:
        if cn["kind"] != "billing" or cn.get("contract_id") not in (None, c["contract_id"]):
            continue
        if cn.get("date") and start <= cn["date"] <= end and cn.get("total"):
            usd, _, mm = to_usd(c, cn["total"], cn.get("currency") or "USD", cn["date"])
            tot -= usd or ZERO
    return tot, unknown, missing


def cashback_items(W: World, invs: list[dict]) -> list[dict]:
    items = []
    for c in W.contracts.values():
        eff = c.get("effective")
        if not eff:
            continue
        # quarterly volume rebate, once the quarter has closed
        if c.get("rebate_tiers"):
            q = quarter_of(eff)
            while True:
                qs_, qe = quarter_bounds(q)
                if qe >= W.as_of or qs_ > W.as_of:
                    break
                tot, unknown, missing = spend(W, c, invs, max(qs_, eff), qe)
                tier = tier_hi = None
                for th, pct in c["rebate_tiers"]:
                    if tot >= th:
                        tier = pct
                    if tot + unknown >= th:
                        tier_hi = pct
                if missing:
                    # spend in a month with no Annex F rate can't be valued, so neither can the rebate
                    it = new_item("cashback", contract_id=c["contract_id"], period=q, credit_type="rebate",
                                  verdict="cannot_determine", missing_doc=fx_missing_doc(W, c, missing),
                                  outbound="request_document", conf=0.7)
                    add_ev(it, c.get("rebate_cite"), c.get("qs_cite"))
                    items.append(it)
                elif tier:
                    earned = r2(tot * tier / 100)
                    paid = sum((to_usd(c, cn["total"], cn.get("currency"), cn.get("date"))[0] or ZERO
                                for cn in W.credit_notes if cn["kind"] == "rebate"
                                and cn.get("contract_id") in (None, c["contract_id"]) and cn.get("period") == q), ZERO)
                    owed = earned - paid
                    if owed > 0:
                        due = qe + timedelta(days=c.get("rebate_due_days") or 45)
                        it = new_item("cashback", contract_id=c["contract_id"], period=q, credit_type="rebate",
                                      amount=owed, deadline=None,
                                      # lines we couldn't name that would change the tier make this a guess
                                      conf=0.85 if tier_hi == tier else 0.55)
                        if W.as_of > due:
                            it["outbound"] = "claim_credit"
                        else:
                            it["internal"] = "track_credit"
                        add_ev(it, c.get("rebate_cite"), c.get("qs_cite"))
                        it["qs"] = tot
                        items.append(it)
                y, n = int(q[:4]), int(q[-1])
                q = f"{y + (n == 4)}-Q{1 if n == 4 else n + 1}"
        # a handling margin that should have stepped down: one item per quarter, summed over every invoice after
        # the one that crossed the threshold (never split into per-invoice overcharges)
        if c.get("margin"):
            items += margin_items(W, c, invs)
        # the annual improvement credit, once the contract year has closed
        if c.get("improvement_pct"):
            n = 1
            while True:
                start = add_months(eff, 12 * (n - 1))
                end = add_months(eff, 12 * n) - timedelta(days=1)
                if end >= W.as_of:
                    break
                tot, unknown, missing = spend(W, c, invs, start, end)
                if missing:
                    it = new_item("cashback", contract_id=c["contract_id"], period=f"CY{n}",
                                  credit_type="promised_credit", verdict="cannot_determine",
                                  missing_doc=fx_missing_doc(W, c, missing), outbound="request_document", conf=0.7)
                    add_ev(it, c.get("improvement_cite"), c.get("qs_cite"))
                    items.append(it)
                    n += 1
                    continue
                earned = r2(tot * c["improvement_pct"] / 100)
                paid = sum((to_usd(c, cn["total"], cn.get("currency"), cn.get("date"))[0] or ZERO
                            for cn in W.credit_notes if cn["kind"] == "promised_credit"
                            and cn.get("contract_id") in (None, c["contract_id"]) and cn.get("period") == f"CY{n}"),
                           ZERO)
                owed = earned - paid
                if owed > dec("0.004"):
                    due = end + timedelta(days=1 + (c.get("improvement_due_days") or 60))
                    it = new_item("cashback", contract_id=c["contract_id"], period=f"CY{n}",
                                  credit_type="promised_credit", amount=owed, conf=0.8)
                    if W.as_of > due:
                        it["outbound"] = "claim_credit"
                    else:
                        it["internal"] = "track_credit"
                    add_ev(it, c.get("improvement_cite"), c.get("qs_cite"))
                    items.append(it)
                n += 1
    return items


def margin_items(W: World, c: dict, invs: list[dict]) -> list[dict]:
    m = c["margin"]
    items = []
    by_q = defaultdict(list)
    for inv in invs:
        if W.contract_for(inv) is c and inv.get("date"):
            by_q[quarter_of(inv["date"])].append(inv)
    for q, qinvs in sorted(by_q.items()):
        _, qe = quarter_bounds(q)
        if qe >= W.as_of:
            continue
        cum, crossed, owed = ZERO, False, ZERO
        it = new_item("cashback", contract_id=c["contract_id"], period=q, credit_type="margin_step_down", conf=0.7)
        for inv in sorted(qinvs, key=lambda x: (x["date"], x["invoice_id"])):
            if crossed:
                for ln in inv["lines"]:
                    if ln["code"] != "MARGIN":
                        continue
                    base = ln.get("base") or sum((x["amount"] for x in inv["lines"] if x["code"] == "COST"), ZERO)
                    if not base:
                        continue
                    diff = ln["amount"] - r2(m["to_pct"] / 100 * base)
                    if diff > 0:
                        owed += diff
                        add_ev(it, ln["cite"])
            if m["on_cost"]:
                cum += sum((x["amount"] for x in inv["lines"] if x["code"] == "COST"), ZERO)
            else:
                cum += qualifying(c, inv)[0]
            if not crossed and cum >= m["threshold"]:
                crossed = True
        if owed > 0:
            usd, fxc, mm = to_usd(c, owed, c.get("currency") or "USD", qe)
            if mm:
                continue
            it.update(amount=usd, outbound="claim_credit")
            add_ev(it, m["cite"], fxc)
            items.append(it)
    return items


# ---- expiry -------------------------------------------------------------------------------------------------------------
def expiry_items(W: World) -> list[dict]:
    items = []
    for c in W.contracts.values():
        end, cite_ = c.get("end"), c.get("term_cite")
        for a in sorted([a for a in W.amendments if a.get("contract_id") == c["contract_id"] and a.get("signed")
                         and a.get("end")], key=lambda a: a["received_ts"]):
            end, cite_ = a["end"], a["end_cite"]
        if not end:
            continue
        deadline = end
        if c.get("auto_renew"):
            while True:
                deadline = end - timedelta(days=c.get("notice_days") or 0)
                if deadline >= W.as_of:
                    break
                end = add_months(end, c.get("renew_months") or 12)
            cite_ = c.get("renew_cite") or cite_
        gap = (deadline - W.as_of).days
        if 0 <= gap <= 60:
            it = new_item("expiry", contract_id=c["contract_id"], deadline=deadline, internal="alert", conf=0.95)
            add_ev(it, cite_, c.get("term_cite"), c.get("renew_cite"))
            items.append(it)
    return items
