"""report.json -> answer_sheet.json (Part 1 of the submission).

    python grader/make_sheet.py report.json [-o answer_sheet.json]

The sheet holds, per class, the count, the USD amount and the ids of every `verdict: finding`; the four totals; every
conflict with its two source documents; every cannot_determine with the missing document and who holds it.

Totals (the brief's formulas):
    total_overpayment = overcharge + duplicate + waived_but_billed + late_fee_not_owed
    cashback_owed     = sum of cashback findings
    late_fees_avoided = sum of late_fee_risk findings (one month's fee each)
    total_savings     = total_overpayment + cashback_owed + late_fees_avoided
conflict, cannot_determine and no_finding never count. Expiry findings are counted and listed; they carry no money.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

CLASSES = ["overcharge", "duplicate", "waived_but_billed", "late_fee_not_owed", "cashback", "late_fee_risk", "expiry"]
DATED = ("expiry", "late_fee_risk")          # the deadline is part of the answer: the notice date, the due date
OVERPAYMENT = ["overcharge", "duplicate", "waived_but_billed", "late_fee_not_owed"]
SHEET_VERSION = "1.0"


def money(x) -> str:
    return f"{Decimal(x):.2f}"


def item_id(item: dict) -> str:
    """The printed id of a finding key: the invoice id; contract/period/credit_type for cashback; the contract for
    expiry."""
    cls = item.get("class")
    if cls == "cashback":
        return f"{item.get('contract_id')}/{item.get('period')}/{item.get('credit_type')}"
    if cls == "expiry":
        return str(item.get("contract_id"))
    return str(item.get("invoice_id"))


def items(report: dict) -> list[dict]:
    """Every item in the report, findings first, then the portfolio."""
    out = list(report.get("findings") or [])
    pf = report.get("portfolio") or {}
    for k in ("cashback", "expiry", "late_fee_risk"):
        out += list(pf.get(k) or [])
    return out


def _amount(it: dict) -> Decimal:
    try:
        return Decimal(str(it.get("amount_usd")))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def sheet_from_items(its: list[dict], *, as_of=None, mode=None, source=None) -> dict:
    """Build the sheet from report items (the same shape the key uses, so the key and a report go through here)."""
    per = {c: {"count": 0, "amount_usd": Decimal("0"), "ids": [], "amounts_by_id": {}, "deadlines_by_id": {}}
           for c in CLASSES}
    conflicts, cannot = [], []
    for it in its:
        cls, v = it.get("class"), it.get("verdict")
        iid = item_id(it)
        if v == "finding" and cls in per:
            row = per[cls]
            row["count"] += 1
            row["ids"].append(iid)
            if cls in DATED and it.get("deadline"):
                row["deadlines_by_id"][iid] = str(it["deadline"])
            if cls != "expiry":
                a = _amount(it)
                row["amount_usd"] += a
                row["amounts_by_id"][iid] = money(a)
        elif v == "conflict":
            docs = []
            for e in it.get("evidence") or []:
                d = e.get("doc")
                if d and d not in docs:
                    docs.append(d)
            conflicts.append({"id": iid, "class": cls, "amount_range": it.get("amount_range"), "sources": docs})
        elif v == "cannot_determine":
            md = it.get("missing_doc") or {}
            cannot.append({"id": iid, "class": cls, "missing_doc": md.get("name"), "holder": md.get("holder")})
    classes = {}
    for c in CLASSES:
        r = per[c]
        classes[c] = {"count": r["count"], "amount_usd": None if c == "expiry" else money(r["amount_usd"]),
                      "ids": sorted(r["ids"]), "amounts_by_id": dict(sorted(r["amounts_by_id"].items()))}
        if c in DATED:
            classes[c]["deadlines_by_id"] = dict(sorted(r["deadlines_by_id"].items()))
    over = sum((per[c]["amount_usd"] for c in OVERPAYMENT), Decimal("0"))
    cb = per["cashback"]["amount_usd"]
    lfa = per["late_fee_risk"]["amount_usd"]
    return {
        "sheet_version": SHEET_VERSION,
        "as_of": as_of,
        "mode": mode,
        "source": source,
        "totals": {"total_overpayment": money(over), "cashback_owed": money(cb), "late_fees_avoided": money(lfa),
                   "total_savings": money(over + cb + lfa)},
        "classes": classes,
        "conflicts": sorted(conflicts, key=lambda x: (str(x["class"]), x["id"])),
        "cannot_determine": sorted(cannot, key=lambda x: (str(x["class"]), x["id"])),
    }


def make_sheet(report: dict, source=None) -> dict:
    return sheet_from_items(items(report), as_of=report.get("as_of"), mode=report.get("mode"), source=source)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="make_sheet.py", description="report.json -> answer_sheet.json")
    ap.add_argument("report", help="the report.json your harness printed")
    ap.add_argument("-o", "--out", default="answer_sheet.json", help="where to write the sheet (default answer_sheet.json)")
    a = ap.parse_args(argv)
    try:
        report = json.loads(Path(a.report).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"make_sheet: can't read {a.report}: {e}", file=sys.stderr)
        return 2
    sheet = make_sheet(report, source=Path(a.report).name)
    Path(a.out).write_text(json.dumps(sheet, indent=1) + "\n")
    t = sheet["totals"]
    print(f"wrote {a.out}: total_savings {t['total_savings']} (overpayment {t['total_overpayment']}, cashback "
          f"{t['cashback_owed']}, late fees avoided {t['late_fees_avoided']}); {len(sheet['conflicts'])} conflict(s), "
          f"{len(sheet['cannot_determine'])} cannot_determine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
