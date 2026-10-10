"""`make validate`: is this repo ready to send? One line per check (SUBMISSION.md lists them). Exit 0 when all pass.

    python tools/check_submission.py [--harness harness/harness.py]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "grader"))

SOLUTION_SECTIONS = ["How to run it", "What works", "What doesn't", "The eval case that caught a bug"]
DESIGN_SECTIONS = ["Fact model", "Conflicts", "Confidence", "People in the loop", "Feedback", "New documents", "Cost",
                   "What I'd do next"]
DESIGN_MAX_WORDS = 1000
MIN_SECTION_WORDS = 15
MIN_OWN_CASES = 10
KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
SKIP = {".git", ".venv", "venv", "__pycache__", "data", ".state", "node_modules", ".pytest_cache"}


def sections(md: str) -> dict[str, str]:
    out, cur = {}, None
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = ""
        elif cur is not None:
            out[cur] += line + "\n"
    return out


def own_words(body: str) -> int:
    """Words in a section, leaving out the template's prompt lines (they start with '>')."""
    return len(re.findall(r"[A-Za-z0-9']+", "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))))


def check_cli(harness: Path) -> tuple[bool, str]:
    from validate import cli_errors
    errs = cli_errors(harness)
    return not errs, "; ".join(errs) or "ingest, report and feedback take the grader's arguments"


def check_solution() -> tuple[bool, str]:
    """SOLUTION.md is your write-up; README.md and BRIEF.pdf stay the brief (keep them)."""
    f = ROOT / "SOLUTION.md"
    if not f.is_file():
        return False, "SOLUTION.md is missing: copy the template's headings and write each section"
    s = sections(f.read_text())
    empty = [h for h in SOLUTION_SECTIONS if h not in s or own_words(s[h]) < MIN_SECTION_WORDS]
    if empty:
        return False, f"SOLUTION.md sections still to write: {', '.join(empty)}"
    return True, "SOLUTION.md: every section written"


def check_card() -> tuple[bool, str]:
    f = ROOT / "report_card.json"
    if not f.is_file():
        return False, "report_card.json is missing: run make grade"
    try:
        card = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        return False, f"report_card.json is not JSON: {e}"
    if "card_version" not in card or "scenarios" not in str(card.get("key", "")):
        return False, "report_card.json doesn't look like make grade's card on the practice mailbox"
    return True, f"report_card.json: {card.get('points')} / {card.get('points_max')}"


def exam_date() -> str | None:
    f = ROOT / "data" / "exam" / "batches.json"
    if not f.is_file():
        return None
    return max(b["as_of"] for b in json.loads(f.read_text())["batches"])


def check_sheet() -> tuple[bool, str]:
    f = ROOT / "answer_sheet.json"
    if not f.is_file():
        return False, "answer_sheet.json is missing: run make sheet"
    try:
        sheet = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        return False, f"answer_sheet.json is not JSON: {e}"
    if "sheet_version" not in sheet or "totals" not in sheet:
        return False, "answer_sheet.json wasn't made by make sheet (grader/make_sheet.py)"
    want = exam_date()
    if sheet.get("mailbox") != "exam" or (want and sheet.get("as_of") != want):
        return False, (f"answer_sheet.json must come from the exam mailbox as of {want}; it says mailbox "
                       f"{sheet.get('mailbox')}, as of {sheet.get('as_of')}: run make sheet")
    return True, f"answer_sheet.json as of {sheet['as_of']}: total_savings {sheet['totals'].get('total_savings')}"


def check_exam_report() -> tuple[bool, str]:
    f = ROOT / "out" / "exam_report.json"
    if not f.is_file():
        return False, "out/exam_report.json is missing: run make sheet"
    from validate import citation_errors, schema_errors
    try:
        report = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        return False, f"out/exam_report.json is not JSON: {e}"
    errs = schema_errors(report)
    if errs:
        return False, f"schema: {len(errs)} problem(s), first: {errs[0]}"
    errs = citation_errors(report, ROOT / "data" / "exam")
    if errs:
        return False, f"citations: {len(errs)} don't resolve, first: {errs[0]}"
    return True, "out/exam_report.json matches the schema and every citation resolves"


def check_evals() -> tuple[bool, str]:
    cases = [f for f in (ROOT / "evals" / "cases").glob("*.yaml") if not f.name.startswith("sample_")]
    res = ROOT / "evals" / "results.json"
    if len(cases) < MIN_OWN_CASES:
        return False, f"evals/cases has {len(cases)} case(s) of your own; we ask for at least {MIN_OWN_CASES}"
    if not res.is_file():
        return False, "evals/results.json is missing: run make eval"
    r = json.loads(res.read_text())
    return True, f"{len(cases)} cases of your own; results.json: {r.get('passed')} of {r.get('total')} pass"


def check_design() -> tuple[bool, str]:
    f = ROOT / "DESIGN.md"
    if not f.is_file():
        return False, "DESIGN.md is missing"
    s = sections(f.read_text())
    empty = [h for h in DESIGN_SECTIONS if h not in s or own_words(s[h]) < MIN_SECTION_WORDS]
    words = len(re.findall(r"[A-Za-z0-9']+", f.read_text()))
    if empty:
        return False, f"DESIGN.md sections still to write: {', '.join(empty)}"
    if words > DESIGN_MAX_WORDS:
        return False, f"DESIGN.md is {words} words; keep it under about {DESIGN_MAX_WORDS}"
    return True, f"DESIGN.md: every section written, {words} words"


def check_ai_use() -> tuple[bool, str]:
    f = ROOT / "AI_USE.md"
    if not f.is_file():
        return False, "AI_USE.md is missing"
    s = sections(f.read_text())
    log_dir = ROOT / "ai_log"
    has_log_files = log_dir.is_dir() and any(p.is_file() for p in log_dir.rglob("*"))
    miss = []
    if own_words(s.get("Tools", "")) < 3:
        miss.append("Tools")
    if own_words(s.get("Prompt log", "")) < 10 and not has_log_files:
        miss.append("Prompt log (paste it, or put the files in ai_log/)")
    if miss:
        return False, f"AI_USE.md still to write: {', '.join(miss)}"
    return True, "AI_USE.md names your tools and has a prompt log"


def check_no_keys() -> tuple[bool, str]:
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or SKIP & set(p.relative_to(ROOT).parts) or p.stat().st_size > 5_000_000:
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if KEY_RE.search(text):
            hits.append(str(p.relative_to(ROOT)))
    if hits:
        return False, f"something that looks like an Anthropic API key is in: {', '.join(hits[:5])}. Remove it and rotate the key"
    return True, "no API keys in the repo"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="check_submission.py", description="is this repo ready to send?")
    ap.add_argument("--harness", default=str(ROOT / "harness" / "harness.py"))
    a = ap.parse_args(argv)
    checks = [("command line", lambda: check_cli(Path(a.harness))), ("SOLUTION.md", check_solution),
              ("report card", check_card), ("answer sheet", check_sheet), ("exam report", check_exam_report),
              ("evals", check_evals), ("DESIGN.md", check_design), ("AI_USE.md", check_ai_use),
              ("secrets", check_no_keys)]
    bad = 0
    for name, fn in checks:
        try:
            ok, why = fn()
        except Exception as e:                      # a check that crashes is a failed check, with the reason
            ok, why = False, f"{type(e).__name__}: {e}"
        bad += not ok
        print(f"{'✓' if ok else '✗'} {name:13} {why}")
    print(f"\n{len(checks) - bad} of {len(checks)} checks pass." + (" Ready to send." if not bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
