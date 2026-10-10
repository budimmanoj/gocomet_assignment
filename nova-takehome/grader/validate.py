"""Check a report.json before grading: the schema, every citation, and the harness command line.

    python grader/validate.py --report report.json --mailbox data/scenarios [--harness harness/harness.py]

1. Schema: report.json matches grader/schema/report.schema.json.
2. Citations: every evidence `doc` exists in the mailbox and its `quote` is on the cited `page`
   (a scanned PDF has no text, so only its page number is checked).
3. Command line (dry run, nothing is executed for real): `harness.py ingest|report|feedback --help` each exit 0 and
   mention the arguments the grader passes (--state-dir everywhere, --as-of and --mode for report).
Any of the three can run alone. Exit code 0 when nothing failed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from grader.extract import Mailbox
    from grader.make_sheet import item_id, items
except ImportError:                                   # run as a script: python grader/validate.py
    from extract import Mailbox
    from make_sheet import item_id, items

HERE = Path(__file__).resolve().parent


def schema_path() -> Path:
    for p in (HERE / "schema" / "report.schema.json", HERE.parent / "contract" / "report.schema.json"):
        if p.exists():
            return p
    raise FileNotFoundError("report.schema.json not found next to the grader")


def schema_errors(report: dict) -> list[str]:
    import jsonschema
    schema = json.loads(schema_path().read_text())
    v = jsonschema.Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(report), key=lambda e: [str(x) for x in e.absolute_path]):
        where = "/".join(str(x) for x in e.absolute_path) or "(top)"
        out.append(f"{where}: {e.message}")
    ids = [it.get("id") for it in items(report) if isinstance(it, dict)]
    dup = sorted({i for i in ids if ids.count(i) > 1 and i is not None})
    if dup:
        out.append(f"finding ids must be unique: {dup}")
    keys = [(it.get("class"), item_id(it)) for it in items(report) if isinstance(it, dict)]
    dupk = sorted({f"{c} {k}" for c, k in keys if keys.count((c, k)) > 1})
    if dupk:
        out.append(f"one item per finding key: {dupk}")
    return out


def citation_errors(report: dict, mailbox: Path) -> list[str]:
    mb = Mailbox(mailbox)
    out = []
    for it in items(report):
        if not isinstance(it, dict):
            continue
        for n, ev in enumerate(it.get("evidence") or [], 1):
            if not isinstance(ev, dict):
                continue
            why = mb.check(str(ev.get("doc", "")), int(ev.get("page") or 0), str(ev.get("quote", "")))
            if why:
                out.append(f"{it.get('id')} ({it.get('class')} {item_id(it)}) evidence {n}: {why}")
    return out


def cli_errors(harness: Path, python: str = sys.executable) -> list[str]:
    """A dry run of the command line: each subcommand's --help exits 0 and names the grader's arguments."""
    if not harness.exists():
        return [f"{harness} not found"]
    harness = harness.resolve()
    need = {"ingest": ["--state-dir"], "report": ["--as-of", "--mode", "--state-dir"], "feedback": ["--state-dir"]}
    out = []
    for cmd, flags in need.items():
        try:
            r = subprocess.run([python, str(harness), cmd, "--help"], capture_output=True, text=True, timeout=60,
                               cwd=harness.parent)
        except subprocess.TimeoutExpired:
            out.append(f"`harness.py {cmd} --help` did not finish in 60 s")
            continue
        if r.returncode != 0:
            out.append(f"`harness.py {cmd} --help` exited {r.returncode}: {(r.stderr or r.stdout).strip()[-200:]}")
            continue
        text = r.stdout + r.stderr
        miss = [f for f in flags if f not in text]
        if miss:
            out.append(f"`harness.py {cmd}` does not accept {', '.join(miss)}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="validate.py", description="schema, citations and command-line checks")
    ap.add_argument("--report", help="report.json to check")
    ap.add_argument("--mailbox", help="folder holding batch_01/, batch_02/ ... that the report cites")
    ap.add_argument("--harness", help="path to harness.py for the command-line dry run")
    a = ap.parse_args(argv)
    if not (a.report or a.harness):
        ap.error("give --report (and --mailbox) and/or --harness")
    failed = 0
    if a.report:
        try:
            report = json.loads(Path(a.report).read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"FAIL schema: can't read {a.report}: {e}")
            return 1
        errs = schema_errors(report)
        print(f"{'PASS' if not errs else 'FAIL'} schema: {len(errs)} problem(s)")
        for e in errs[:40]:
            print(f"  - {e}")
        failed += bool(errs)
        if a.mailbox:
            errs = citation_errors(report, Path(a.mailbox))
            n = sum(len(it.get("evidence") or []) for it in items(report) if isinstance(it, dict))
            print(f"{'PASS' if not errs else 'FAIL'} citations: {n - len(errs)} of {n} resolve")
            for e in errs[:40]:
                print(f"  - {e}")
            failed += bool(errs)
    if a.harness:
        errs = cli_errors(Path(a.harness))
        print(f"{'PASS' if not errs else 'FAIL'} command line: ingest / report / feedback")
        for e in errs:
            print(f"  - {e}")
        failed += bool(errs)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
