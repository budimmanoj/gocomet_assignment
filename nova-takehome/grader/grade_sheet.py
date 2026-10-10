"""Compare an answer_sheet.json with a key and print one page: totals on top, then one row per class.

    python grader/grade_sheet.py answer_sheet.json --key data/scenarios/answers/ [--json result.json]

The key can be:
- a folder of answer files (data/scenarios/answers/*.yaml),
- another answer_sheet.json (for example one made from a reference report),
- the reviewer's answer_key.json.
By default the key is read as it stands after the last batch; `--batch batch_01` grades an earlier point.

A row is ✓ when the count, every id and every amount match (amounts within USD 0.01 per finding), and for expiry and
late-fee risk every deadline. The row lists the ids that are missing (in the key, not on your sheet), extra (on your
sheet, not in the key) and those with the wrong amount or date. A conflict must cite both documents that disagree
(citing more, such as the contract clause, is fine). The page prints both report dates and warns when they differ.
Exit code 0 when every row is ✓.

On the exam mailbox this check is Part 1 of a submission, and it is a pass/fail gate (Ayush, 2026-09-28): PASS (every
row ✓) means the reviewer goes on to run the code on the hidden set; NOT YET ends the review. It carries no weight in
the final grade beyond that.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

try:
    from grader.make_sheet import CLASSES, item_id, sheet_from_items
except ImportError:                                   # run as a script: python grader/grade_sheet.py
    from make_sheet import CLASSES, item_id, sheet_from_items

TOL = Decimal("0.01")
OK, BAD = "✓", "✗"
LABEL = {"overcharge": "overcharge", "duplicate": "duplicate", "waived_but_billed": "waived but billed",
         "late_fee_not_owed": "late fee not owed", "cashback": "cashback owed", "late_fee_risk": "late fee risk",
         "expiry": "expiry alerts"}
TOTALS = ["total_overpayment", "cashback_owed", "late_fees_avoided", "total_savings"]


# ---- reading a key ----------------------------------------------------------------------------------------------------
def _key_class(key: dict, finding_class: str | None = None) -> str:
    if "class" in key:
        return key["class"]
    if "period" in key:
        return "cashback"
    return "expiry"


def _item_at(entry: dict, by_batch: list, batch: str | None, as_ofs: set | None = None) -> dict | None:
    """The item a key entry expects after `batch` (default: the last one), or None when it must be absent. The
    batch's as_of is added to `as_ofs`."""
    if by_batch:
        pick = by_batch[-1] if batch is None else next((b for b in by_batch if b.get("after_batch") == batch), None)
        if pick is None:
            return None
        if as_ofs is not None and pick.get("as_of"):
            as_ofs.add(str(pick["as_of"]))
        exp = pick.get("expect")
        if exp in ("absent", "no"):
            return None
        if isinstance(exp, dict):
            entry = {**entry, **{("amount_range" if k == "amount_range_usd" else k): v for k, v in exp.items()}}
    return entry


def items_from_answer_key(data: dict, batch: str | None, as_ofs: set | None = None) -> list[dict]:
    out = []
    for s in data["scenarios"]:
        key = s["key"]
        it = {**key, "class": _key_class(key), "verdict": s["verdict"], "amount_usd": s.get("amount_usd"),
              "amount_range": s.get("amount_range_usd"), "deadline": s.get("deadline"), "evidence": [],
              "missing_doc": ({"name": s["missing_doc"].get("reference_as_cited"), "holder": s["missing_doc"].get("holder")}
                              if s.get("missing_doc") else None)}
        it = _item_at(it, s.get("answers_by_batch") or [], batch, as_ofs)
        if it is not None:
            out.append(it)
    return out


def items_from_answers_dir(d: Path, batch: str | None, as_ofs: set | None = None) -> list[dict]:
    import yaml
    out = []
    for f in sorted(d.glob("*.yaml")):
        a = yaml.safe_load(f.read_text())
        key = a["key"]
        ev = a.get("evidence") or []
        if a["verdict"] == "conflict" and a.get("deciding_clause"):
            # the two sources that disagree; the clause that declines to rank them is extra, never required
            ev = [e for e in ev if e.get("doc") != a["deciding_clause"].get("doc")]
        it = {**key, "class": _key_class(key), "verdict": a["verdict"], "amount_usd": a.get("amount_usd"),
              "amount_range": a.get("amount_range"), "deadline": a.get("deadline"),
              "evidence": ev, "missing_doc": a.get("missing_doc")}
        it = _item_at(it, a.get("by_batch") or [], batch, as_ofs)
        if it is not None:
            out.append(it)
    return out


def load_key(path: str, batch: str | None = None) -> dict:
    p = Path(path)
    as_ofs: set = set()
    if p.is_dir():
        its = items_from_answers_dir(p, batch, as_ofs)
        return sheet_from_items(its, as_of=", ".join(sorted(as_ofs)) or None, source=str(p))
    data = json.loads(p.read_text())
    if "scenarios" in data:
        its = items_from_answer_key(data, batch, as_ofs)
        return sheet_from_items(its, as_of=", ".join(sorted(as_ofs)) or None, source=p.name)
    if "classes" in data and "totals" in data:
        return data
    raise ValueError(f"{path}: not an answers folder, an answer sheet or an answer key")


# ---- comparing --------------------------------------------------------------------------------------------------------
def _d(x) -> Decimal:
    return Decimal(str(x)) if x not in (None, "") else Decimal("0")


def _same_doc(key_doc: str, doc: str) -> bool:
    """A key's source matches a cited doc written as the mailbox path, with '#attach/', or as the bare attachment."""
    a, b = key_doc.replace("#attach/", "#"), doc.replace("#attach/", "#")
    return a == b or (("#" in a) and a.split("#", 1)[1] == b)


def _holder_name(h) -> str:
    if isinstance(h, dict):
        return str(h.get("person") or h.get("party") or "")
    return str(h or "")


def grade(sheet: dict, key: dict) -> dict:
    rows = []
    for c in CLASSES:
        e = key["classes"].get(c, {"count": 0, "amount_usd": "0.00", "ids": [], "amounts_by_id": {}})
        g = sheet.get("classes", {}).get(c, {"count": 0, "amount_usd": "0.00", "ids": [], "amounts_by_id": {}})
        eid, gid = set(e.get("ids") or []), set(g.get("ids") or [])
        wrong, wrong_date = [], []
        if c != "expiry":
            ea, ga = e.get("amounts_by_id") or {}, g.get("amounts_by_id") or {}
            for i in sorted(eid & gid):
                if i in ea and i in ga and abs(_d(ea[i]) - _d(ga[i])) > TOL:
                    wrong.append({"id": i, "expected": ea[i], "yours": ga[i]})
        ed, gd = e.get("deadlines_by_id") or {}, g.get("deadlines_by_id") or {}
        for i in sorted(eid & gid):
            if i in ed and gd.get(i) != ed[i]:
                wrong_date.append({"id": i, "expected": ed[i], "yours": gd.get(i)})
        n = max(len(eid), 1)
        amount_ok = c == "expiry" or abs(_d(e.get("amount_usd")) - _d(g.get("amount_usd"))) <= TOL * n
        ok = eid == gid and not wrong and not wrong_date and amount_ok and e.get("count", 0) == g.get("count", 0)
        rows.append({"class": c, "ok": ok, "expected": {"count": e.get("count", 0), "amount_usd": e.get("amount_usd")},
                     "yours": {"count": g.get("count", 0), "amount_usd": g.get("amount_usd")},
                     "missing": sorted(eid - gid), "extra": sorted(gid - eid), "wrong_amount": wrong,
                     "wrong_deadline": wrong_date})
    # conflicts: the id, the range and at least two cited sources
    ec = {x["id"]: x for x in key.get("conflicts") or []}
    gc = {x["id"]: x for x in sheet.get("conflicts") or []}
    problems = []
    for i in sorted(set(ec) & set(gc)):
        er, gr = ec[i].get("amount_range"), gc[i].get("amount_range")
        if er and (not gr or any(abs(_d(a) - _d(b)) > TOL for a, b in zip(er, gr))):
            problems.append({"id": i, "problem": f"range {gr} should be {er}"})
        theirs = gc[i].get("sources") or []
        need = ec[i].get("sources") or []
        lost = [d for d in need if not any(_same_doc(d, t) for t in theirs)]
        if lost:
            problems.append({"id": i, "problem": "cite the source(s) that disagree: " + ", ".join(lost)})
        elif len(theirs) < 2:
            problems.append({"id": i, "problem": "cite both source documents"})
    rows.append({"class": "conflicts", "ok": set(ec) == set(gc) and not problems,
                 "expected": {"count": len(ec)}, "yours": {"count": len(gc)}, "missing": sorted(set(ec) - set(gc)),
                 "extra": sorted(set(gc) - set(ec)), "wrong_amount": [], "problems": problems})
    # cannot_determine: the id, the missing document and who holds it
    ek = {x["id"]: x for x in key.get("cannot_determine") or []}
    gk = {x["id"]: x for x in sheet.get("cannot_determine") or []}
    problems = []
    for i in sorted(set(ek) & set(gk)):
        en, gn = " ".join(str(ek[i].get("missing_doc") or "").lower().split()), " ".join(str(gk[i].get("missing_doc") or "").lower().split())
        if en and en not in gn:
            problems.append({"id": i, "problem": f"missing document should be {ek[i].get('missing_doc')!r}"})
        eh, gh = _holder_name(ek[i].get("holder")).lower(), _holder_name(gk[i].get("holder")).lower()
        if eh and eh != gh:
            problems.append({"id": i, "problem": f"holder should be {_holder_name(ek[i].get('holder'))!r}"})
    rows.append({"class": "cannot_determine", "ok": set(ek) == set(gk) and not problems,
                 "expected": {"count": len(ek)}, "yours": {"count": len(gk)}, "missing": sorted(set(ek) - set(gk)),
                 "extra": sorted(set(gk) - set(ek)), "wrong_amount": [], "problems": problems,
                 "missing_detail": {i: {"missing_doc": ek[i].get("missing_doc"), "holder": _holder_name(ek[i].get("holder"))}
                                    for i in sorted(set(ek) - set(gk))}})
    n_find = sum(len(key["classes"].get(c, {}).get("ids") or []) for c in CLASSES if c != "expiry")
    totals = []
    for t in TOTALS:
        e, g = key["totals"].get(t), sheet.get("totals", {}).get(t)
        totals.append({"name": t, "expected": e, "yours": g,
                       "ok": g is not None and abs(_d(e) - _d(g)) <= TOL * max(n_find, 1)})
    passed = all(r["ok"] for r in rows) and all(t["ok"] for t in totals)
    warn = []
    if key.get("as_of") and sheet.get("as_of") and str(key["as_of"]) != str(sheet["as_of"]):
        warn.append(f"your sheet is as of {sheet['as_of']} and the key is as of {key['as_of']}: run report with "
                    f"--as-of {key['as_of']}, or grade against that batch with --batch")
    return {"pass": passed, "rows_ok": sum(r["ok"] for r in rows), "rows": len(rows), "totals": totals,
            "classes": rows, "key": key.get("source"), "as_of": sheet.get("as_of"), "key_as_of": key.get("as_of"),
            "warnings": warn}


# ---- the page ---------------------------------------------------------------------------------------------------------
def _money(x) -> str:
    return "" if x is None else f"${_d(x):,.2f}"


def page(result: dict, sheet_name: str = "answer_sheet.json") -> str:
    W = {"name": 20, "n": 5, "usd": 14}
    L = []
    verdict = "PASS" if result["pass"] else "NOT YET"
    L.append(f"Answer sheet check: {sheet_name} against {result['key']}")
    L.append(f"Your sheet is as of {result.get('as_of') or '(not stated)'}; the key is as of "
             f"{result.get('key_as_of') or '(not stated)'}.")
    for w in result.get("warnings") or []:
        L.append(f"WARNING: {w}")
    L.append(f"Result: {verdict}. {result['rows_ok']} of {result['rows']} rows match.")
    L.append("")
    L.append(f"{'TOTALS':{W['name']}}  {'expected':>{W['usd']}}  {'yours':>{W['usd']}}  ok")
    for t in result["totals"]:
        L.append(f"{t['name']:{W['name']}}  {_money(t['expected']):>{W['usd']}}  "
                 f"{_money(t['yours']) or '(missing)':>{W['usd']}}  {OK if t['ok'] else BAD}")
    L.append("")
    L.append(f"{'CLASS':{W['name']}}  {'expected':>{W['n'] + W['usd'] + 1}}  {'yours':>{W['n'] + W['usd'] + 1}}  ok  "
             "what differs")
    for r in result["classes"]:
        name = LABEL.get(r["class"], r["class"].replace("_", " "))
        ex, yo = r["expected"], r["yours"]
        es = f"{ex['count']:>{W['n']}} {_money(ex.get('amount_usd')):>{W['usd']}}"
        ys = f"{yo['count']:>{W['n']}} {_money(yo.get('amount_usd')):>{W['usd']}}"
        diffs = []
        if r["missing"]:
            md = r.get("missing_detail") or {}
            diffs.append("missing " + ", ".join(
                f"{i} ({md[i]['missing_doc']}, held by {md[i]['holder']})" if i in md else i for i in r["missing"]))
        if r["extra"]:
            diffs.append("extra " + ", ".join(r["extra"]))
        for w in r["wrong_amount"]:
            diffs.append(f"{w['id']} amount {_money(w['yours'])}, expected {_money(w['expected'])}")
        for w in r.get("wrong_deadline") or []:
            diffs.append(f"{w['id']} deadline {w['yours']}, expected {w['expected']}")
        for p in r.get("problems") or []:
            diffs.append(f"{p['id']}: {p['problem']}")
        L.append(f"{name:{W['name']}}  {es}  {ys}  {OK if r['ok'] else BAD}   {diffs[0] if diffs else ''}".rstrip())
        pad = " " * (W["name"] + 2 * (W["n"] + W["usd"] + 3) + 7)
        for d in diffs[1:]:
            L.append(pad + d)
    L.append("")
    L.append("How to read this: each row compares the key with your sheet. A row is ✓ when the count, every id and every")
    L.append("amount match (within USD 0.01 per finding), and for expiry and late-fee risk every deadline. 'missing' ids")
    L.append("are in the key and not on your sheet; 'extra' ids are on your sheet and not in the key. Only verdict")
    L.append("'finding' counts in the class rows and the totals; conflicts and cannot_determine have their own rows and")
    L.append("never add money. A conflict must cite both documents that disagree. On the exam mailbox this is Part 1,")
    L.append("and it is pass or fail: every row must match before we run your code on our set.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="grade_sheet.py", description="answer_sheet.json against a key: one page")
    ap.add_argument("sheet", help="answer_sheet.json from make_sheet.py")
    ap.add_argument("--key", required=True, help="answers folder, answer sheet, or answer_key.json")
    ap.add_argument("--batch", help="grade the key as it stands after this batch (default: the last)")
    ap.add_argument("--json", dest="json_out", help="also write the result as JSON here")
    a = ap.parse_args(argv)
    try:
        sheet = json.loads(Path(a.sheet).read_text())
        key = load_key(a.key, a.batch)
    except (OSError, ValueError, KeyError) as e:
        print(f"grade_sheet: {e}", file=sys.stderr)
        return 2
    res = grade(sheet, key)
    print(page(res, Path(a.sheet).name))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
