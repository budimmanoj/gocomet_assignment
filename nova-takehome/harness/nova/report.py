"""Turn detector items into report.json: feedback decisions, actions per mode, confidence, ids across reports.

A report is a pure function of (documents received by as_of, feedback decided by as_of, mode). To say what changed
since the last report (`supersedes`, `retro`) we compare with the report printed for the previous batch, kept in the
state folder, or recompute it at the previous batch's cutoff when there is none.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from . import detect as DT
from .common import ZERO, dec, iso, money, norm_invoice, read_json, to_date, write_json
from .reader import load_docs
from .world import World

HUMAN_REVIEW_AT = dec("5000.00")


# ---- feedback ---------------------------------------------------------------------------------------------------------
def store_feedback(path: str, state_dir: str) -> int:
    fb = read_json(Path(path))
    if not isinstance(fb, dict):
        raise ValueError(f"{path}: not a feedback file")
    d = Path(state_dir) / "feedback"
    n = len(list(d.glob("*.json"))) if d.is_dir() else 0
    write_json(d / f"{n:03d}_{fb.get('after_batch', 'batch')}.json", fb)
    return len(fb.get("items") or [])


def load_feedback(state_dir: str, as_of: date) -> list[dict]:
    out = []
    for f in sorted((Path(state_dir) / "feedback").glob("*.json")):
        fb = read_json(f) or {}
        decided = to_date(fb.get("decided_at"))
        if decided and decided > as_of:
            continue
        for it in fb.get("items") or []:
            if isinstance(it, dict):
                out.append({**it, "decided_at": fb.get("decided_at"), "_batch": fb.get("after_batch"),
                            "_by": fb.get("decided_by")})
    return out


def key_of(it: dict) -> tuple:
    c = it["class"]
    if c == "cashback":
        return ("cashback", it["contract_id"], it["period"], it["credit_type"])
    if c == "expiry":
        return ("expiry", it["contract_id"])
    return (c, norm_invoice(it["invoice_id"]))


def fb_key(fb: dict) -> tuple | None:
    k = fb.get("finding_key") or {}
    cls = k.get("class") or ("cashback" if "period" in k else "expiry" if "contract_id" in k else None)
    if not cls:
        return None
    if cls == "cashback":
        return ("cashback", k.get("contract_id"), k.get("period"), k.get("credit_type"))
    if cls == "expiry":
        return ("expiry", k.get("contract_id"))
    return (cls, norm_invoice(k.get("invoice_id")))


def apply_feedback(W: World, items: list[dict]) -> list[dict]:
    """Decisions on exact keys. Standing facts (authority, accepted rates, precedence) were used by the detectors."""
    by_key = {key_of(it): it for it in items}
    for fb in W.feedback:
        k = fb_key(fb)
        if not k:
            continue
        dec_ = fb.get("decision")
        fact = fb.get("fact") or {}
        if dec_ in ("close", "reject"):
            by_key.pop(k, None)
        elif dec_ == "override_amount":
            amt = dec((fact.get("value") or {}).get("amount_usd"))
            it = by_key.get(k)
            if amt is not None and it is not None:
                it.update(amount=amt, verdict="finding", range=None, missing_doc=None)
                it["fb"].append(fb)
                if it["class"] in DT.OUTBOUND_CLASSES and not it.get("outbound"):
                    it["outbound"] = "dispute"
        elif dec_ == "one_off_approval" and k[0] == "waived_but_billed":
            it = one_off_waiver(W, fb, k[1])
            if it:
                by_key[k] = it
        elif dec_ == "resolve_conflict":
            it = by_key.get(k)
            if it is not None and it["verdict"] == "conflict":
                by_key.pop(k, None)           # recomputed by the detectors with the precedence; nothing left
    return list(by_key.values())


def one_off_waiver(W: World, fb: dict, inv_id: str) -> dict | None:
    """A waiver a person approved for named months, on this one invoice only."""
    inv = W.invoice(inv_id)
    if not inv:
        return None
    fact = fb.get("fact") or {}
    months = set((fact.get("value") or {}).get("months") or [])
    who = ((fact.get("subject") or {}).get("person") or "").lower()
    codes = {wv["code"] for wv in W.waivers if (wv["sender"].get("name") or "").lower() == who and wv["code"]}
    c = W.contract_for(inv)
    it = DT.new_item("waived_but_billed", invoice_id=inv_id, contract_id=(c or {}).get("contract_id"),
                     currency=inv.get("currency") or "USD", fb=[fb])
    amt = ZERO
    for ln in inv["lines"]:
        m = ln.get("period") or (ln["date"].isoformat()[:7] if ln.get("date") else None)
        if m in months and (not codes or ln["code"] in codes):
            amt += ln["amount"]
            DT.add_ev(it, ln["cite"])
    for wv in W.waivers:
        if (wv["sender"].get("name") or "").lower() == who:
            DT.add_ev(it, wv["cite"])
    if amt <= 0:
        return None
    usd, fxc, mm = DT.to_usd(c, amt, it["currency"], inv.get("date"))
    if mm:
        return None
    it.update(amount=usd, native=amt, outbound="dispute", conf=0.85)
    return it


# ---- actions ----------------------------------------------------------------------------------------------------------
def group_sums(items: list[dict]) -> dict:
    sums = defaultdict(lambda: ZERO)
    for it in items:
        if it["verdict"] == "finding" and it.get("outbound") in ("dispute", "claim_credit") and it.get("amount"):
            sums[group_of(it)] += it["amount"]
    return sums


def group_of(it: dict) -> tuple:
    if it["class"] == "cashback":
        return key_of(it)
    return ("invoice", norm_invoice(it.get("invoice_id")))


def unattended_ok(W: World, it: dict, gsum, conflicts: set) -> tuple[bool, list[str]]:
    """The glossary's five checks. -> (pass, reasons it failed)."""
    why = []
    c = W.contracts.get(it.get("contract_id") or "")
    if it["verdict"] == "finding":
        if it.get("missing_doc"):
            why.append("missing document")
        if it["class"] == "overcharge" and (it.get("pickup_sources") or set()) - {"tracking", "email"}:
            why.append("pickup date not from tracking or a carrier email")
        if gsum >= HUMAN_REVIEW_AT:
            why.append("outbound amount on this invoice is $5,000 or more")
    if any((it.get("contract_id"), ln) in conflicts for ln in it.get("lanes") or ()):
        why.append("open conflict on the same contract and lane")
    if c:
        if it.get("outbound") in ("dispute", "claim_credit") and not W.contact(c, "billing_disputes") \
                and not W.contact(c, "notices"):
            why.append("no Schedule 1 recipient")
        if it.get("outbound") == "request_document" and not (it.get("missing_doc") or {}).get("holder", {}).get("person"):
            why.append("holder not on Schedule 1")
    return not why, why


def recipient(W: World, it: dict) -> str | None:
    c = W.contracts.get(it.get("contract_id") or "")
    if not c:
        return None
    if it.get("outbound") == "request_document":
        h = (it.get("missing_doc") or {}).get("holder") or {}
        p = W.person(c, name=h.get("person")) if h.get("person") else None
        return p["email"] if p else None
    p = W.contact(c, "billing_disputes") or W.contact(c, "notices")
    return p["email"] if p else None


def action(W: World, it: dict, mode: str, gsum, conflicts: set) -> str:
    v = it["verdict"]
    if v == "conflict":
        return "escalate"
    if v == "no_finding":
        return "none"
    if v == "finding" and it.get("internal"):
        return f"internal:{it['internal']}"
    out = it.get("outbound")
    if not out:
        return "none"
    if v == "finding" and gsum >= HUMAN_REVIEW_AT:
        return "human_review"
    if mode == "supervised":
        return f"draft:{out}"
    ok, _ = unattended_ok(W, it, gsum, conflicts)
    return f"execute:{out}" if ok else "human_review"


def confidence(it: dict) -> float:
    c = it.get("conf", 0.85)
    amt = it.get("amount")
    if amt is not None and amt < dec("1.00"):
        c -= 0.15
    if it.get("fb"):
        c -= 0.02
    if it["class"] == "cashback" and it.get("currency", "USD") != "USD":
        c -= 0.05
    return round(max(0.3, min(0.97, c)), 2)


# ---- assembling ---------------------------------------------------------------------------------------------------------
def compute(records: list[dict], as_of: date, fb: list[dict], state_dir: str | None = None) -> tuple[World, list[dict]]:
    W = World(records, as_of, fb, state_dir)
    items = DT.run(W)
    items = apply_feedback(W, items)
    for it in items:
        if it.get("invoice_id"):
            inv = W.invoice(it["invoice_id"])
            it["inv_received"] = inv["received"] if inv else None
            it["scan_only"] = bool(inv and inv.get("scan"))
    return W, items


def key_str(k: tuple) -> str:
    return k[0] + ":" + "/".join(str(x) for x in k[1:])


def signature(x: dict) -> tuple:
    rng = x.get("amount_range")
    return (x.get("verdict"), x.get("amount_usd"), tuple(rng) if rng else None, x.get("deadline"))


def previous(state_dir: str, records: list[dict], as_of: date, mode: str) -> tuple[date | None, dict]:
    """-> (previous report date, {key: printed item}) for the batch before this one."""
    hist = read_json(Path(state_dir) / f"history_{mode}.json", []) or []
    earlier = [h for h in hist if to_date(h["as_of"]) < as_of]
    if earlier:
        h = max(earlier, key=lambda h: h["as_of"])
        return to_date(h["as_of"]), h["items"]
    held = [r for r in records if r.get("received") and to_date(r["received"]) <= as_of]
    batches = sorted({r["batch"] for r in held})
    if len(batches) < 2:
        return None, {}
    prev_b = batches[-2]
    cut = max(to_date(r["received"]) for r in held if r["batch"] <= prev_b)
    _, items = compute(records, cut, load_feedback(state_dir, cut), state_dir)
    return cut, {key_str(key_of(it)): {"id": f"{key_str(key_of(it))}", **_sig_fields(it)} for it in items}


def _sig_fields(it: dict) -> dict:
    return {"verdict": it["verdict"], "amount_usd": money(it.get("amount")) if it["verdict"] == "finding" else None,
            "amount_range": [money(x) for x in it["range"]] if it.get("range") else None,
            "deadline": iso(it.get("deadline"))}


def build(state_dir: str, as_of_s: str, mode: str) -> dict:
    as_of = to_date(as_of_s)
    records = load_docs(state_dir)
    fb = load_feedback(state_dir, as_of)
    W, items = compute(records, as_of, fb, state_dir)
    prev_date, prev = previous(state_dir, records, as_of, mode)
    sums = group_sums(items)
    conflicts = {(it.get("contract_id"), ln) for it in items if it["verdict"] == "conflict" for ln in it.get("lanes", ())}
    report = {"schema_version": "1.0", "as_of": as_of.isoformat(), "mode": mode, "findings": [],
              "portfolio": {"cashback": [], "expiry": [], "late_fee_risk": []}}
    printed = {}
    for it in sorted(items, key=lambda x: key_str(key_of(x))):
        k = key_of(it)
        ks = key_str(k)
        gsum = sums.get(group_of(it), ZERO)
        out = {"id": ks, "class": it["class"]}
        if it["class"] == "cashback":
            out.update(contract_id=it["contract_id"], period=it["period"], credit_type=it["credit_type"])
        elif it["class"] == "expiry":
            out.update(contract_id=it["contract_id"])
        else:
            out.update(invoice_id=norm_invoice(it["invoice_id"]))
        out.update(_sig_fields(it))
        out["action"] = action(W, it, mode, gsum, conflicts)
        out["confidence"] = confidence(it)
        out["evidence"] = it["evidence"][:10]
        out["missing_doc"] = it.get("missing_doc")
        if out["action"].startswith(("draft:", "execute:")) or out["action"] == "human_review":
            rc = recipient(W, it)
            if rc:
                out["recipient"] = rc
        if mode == "autonomous" and out["action"] == "human_review":
            ok, why = unattended_ok(W, it, gsum, conflicts)
            if why:
                out["held_because"] = why
        # what changed since the previous report
        p = prev.get(ks)
        out["supersedes"] = []
        if p is not None:
            if signature(p) == signature(out):
                out["id"] = p["id"]
            else:
                out["id"] = f"{ks}@{as_of.isoformat()}"
                out["supersedes"] = [p["id"]]
        elif prev_date is not None and it.get("inv_received") and it["inv_received"] <= prev_date and any(
                (r.get("received") and r["received"] > prev_date and r.get("effective") and
                 r["effective"] <= prev_date) for r in it.get("relies") or []):
            out["retro"] = True
        fbs = [f for f in it.get("fb") or [] if f]
        out["learned_at"] = {"feedback_item_id": fbs[-1].get("item_id"), "batch": fbs[-1].get("_batch")} if fbs else None
        printed[ks] = {k2: out.get(k2) for k2 in ("id", "verdict", "amount_usd", "amount_range", "deadline")}
        if it["class"] == "cashback":
            report["portfolio"]["cashback"].append(out)
        elif it["class"] == "expiry":
            report["portfolio"]["expiry"].append(out)
        elif it["class"] == "late_fee_risk":
            report["portfolio"]["late_fee_risk"].append(out)
        else:
            report["findings"].append(out)
    _save_history(state_dir, mode, as_of, printed)
    return report


def _save_history(state_dir: str, mode: str, as_of: date, printed: dict) -> None:
    p = Path(state_dir) / f"history_{mode}.json"
    hist = [h for h in (read_json(p, []) or []) if h.get("as_of") != as_of.isoformat()]
    hist.append({"as_of": as_of.isoformat(), "items": printed})
    write_json(p, sorted(hist, key=lambda h: h["as_of"]))
