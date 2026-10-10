"""Replay the mailbox through a harness, batch by batch, and print the report card.

    python grader/run_grader.py --harness "python harness/harness.py" --data data/scenarios \
        --key data/scenarios/answers [--mode supervised|autonomous|both] [--out card.json]
    reviewer: ... --key answer_key.json --exclude-key <practice answers>   (practice keys replayed, not scored)
              --sandbox --submission <repo>   (every step in a container; reviewer tooling, not in the pack)

For each mode and each world, in a fresh folder outside <data>, for each batch in order:
    <harness> ingest <tmp>/mailbox/batch_k --state-dir <tmp>/state     (only the batches seen so far are copied)
    <harness> report --as-of <batch cutoff> --mode <mode> --state-dir <dir>      (stdout = report.json)
    <harness> feedback <tmp>/mailbox/feedback/<world>_batch_k.json --state-dir <dir>   (copied when due)
Every step is a new process with a wall-clock timeout. The first world's batches live in <data>/batch_NN/; a second
world (the reviewer's W2) in <data>/W2/batch_NN/ and gets its own fresh state dir. Every report is kept and scored by
grader/score.py. The candidate and the reviewer run exactly this file; only --data and --key differ.

Exit code 0 when no hard gate triggered and the last report of every world matches the key (the Level 2 page is
green); 1 otherwise; 2 when the grader itself can't start (bad arguments, unreadable key).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from grader import score as S
except ImportError:                                   # run as a script: python grader/run_grader.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import score as S  # type: ignore

MODES = ("supervised", "autonomous")


def world_dir(data: Path, world: str, first: str) -> Path:
    """The first world of a key lives at the data root; any other world under <data>/<world>/."""
    return data if world == first or not (data / world).is_dir() else data / world


def feedback_file(data: Path, fb_dir: Path | None, world: str, batch: str) -> Path | None:
    for d in [fb_dir, data / "feedback"]:
        if d and (d / f"{world}_{batch}.json").is_file():
            return d / f"{world}_{batch}.json"
    return None


def run_step(cmd: list[str], timeout: float, env: dict, cwd: Path | None = None) -> dict:
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = "timeout", (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), \
            f"timed out after {timeout:.0f} s"
    except OSError as e:
        rc, out, err = "error", "", str(e)
    return {"rc": rc, "stdout": out, "stderr": (err or "")[-600:], "secs": round(time.monotonic() - t0, 1)}


ENV_PASS = ("PATH", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")


def harness_env(home: Path, tmp: Path) -> dict:
    """Only PATH, a fresh HOME and TMPDIR, and the Anthropic key and base URL reach the harness."""
    env = {k: os.environ[k] for k in ENV_PASS if k in os.environ}
    env.update(HOME=str(home), TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp))
    return env


def absolute(harness: list[str]) -> list[str]:
    """Harness arguments that name files become absolute paths (the harness runs in its own empty folder)."""
    return [os.path.abspath(a) if not a.startswith("-") and Path(a).exists() else a for a in harness]   # no symlink resolving: a venv python must stay itself


def replay(harness: list[str], data: Path, key: dict, modes: list[str], timeout: float, fb_dir: Path | None = None,
           log=print, reports_dir: Path | None = None, work_dir: Path | None = None, sandbox=None) -> tuple[dict, dict]:
    """-> (runs, feedback delivered). runs[mode][world] = [{"batch", "as_of", "report", "error", "steps"}, ...].

    Isolation: each mode and world gets a fresh folder outside --data holding mailbox/, state/, home/ and tmp/. Before
    each ingest only that batch is copied into mailbox/ (so mailbox/ holds the batches seen so far); a feedback file
    is copied there only after its batch's report. The harness never gets a path into --data or the key, runs with
    home/ as its working folder, and sees only PATH, HOME, TMPDIR and the ANTHROPIC_* variables. The grading sandbox
    (read-only mounts, no network but the API) is the second layer: with `sandbox` (reviewer mode, --sandbox) every
    step runs in a fresh container that mounts only mailbox/ (read-only) and state/."""
    harness = absolute(harness)
    worlds = key["worlds"]
    first = next(iter(worlds), "W1")
    runs: dict = {}
    delivered: dict = {}
    for mode in modes:
        runs[mode] = {}
        for world, batches in worlds.items():
            wdir = world_dir(data, world, first)
            root = Path(tempfile.mkdtemp(prefix="grader-", dir=work_dir))
            box = root / "run" / "box"            # nested, so nothing the harness is given sits next to other files
            mailbox, state, home, tmp = (box / d for d in ("mailbox", "state", "home", "tmp"))
            for d in (mailbox, state, home, tmp):
                d.mkdir(parents=True)
            if sandbox is not None:
                step = sandbox.stepper(harness, mailbox, state, timeout)
            else:
                env = harness_env(home, tmp)

                def step(args, env=env, home=home):
                    return run_step(harness + args, timeout, env, cwd=home)
            out = runs[mode][world] = []
            try:
                for batch, as_of in batches:
                    rec = {"batch": batch, "as_of": as_of, "report": None, "error": None, "steps": []}
                    src = wdir / batch
                    if not src.is_dir():
                        rec["error"] = f"no batch folder {batch}"
                        out.append(rec)
                        continue
                    bdir = mailbox / batch
                    shutil.copytree(src, bdir)
                    st = step(["ingest", str(bdir), "--state-dir", str(state)])
                    rec["steps"].append({"step": "ingest", **{k: v for k, v in st.items() if k != "stdout"}})
                    if st["rc"] != 0:
                        rec["error"] = f"ingest exited {st['rc']}: {st['stderr'].strip()[-300:]}"
                    st = step(["report", "--as-of", as_of, "--mode", mode, "--state-dir", str(state)])
                    rec["steps"].append({"step": "report", **{k: v for k, v in st.items() if k != "stdout"}})
                    if st["rc"] != 0:
                        rec["error"] = (rec["error"] + "; " if rec["error"] else "") + \
                            f"report exited {st['rc']}: {st['stderr'].strip()[-300:]}"
                    else:
                        try:
                            rec["report"] = json.loads(st["stdout"])
                        except json.JSONDecodeError as e:
                            rec["error"] = f"report did not print JSON: {e}"
                    if reports_dir is not None and rec["report"] is not None:
                        reports_dir.mkdir(parents=True, exist_ok=True)
                        (reports_dir / f"{mode}_{world}_{batch}.json").write_text(json.dumps(rec["report"], indent=1))
                    fb = feedback_file(data, fb_dir, world, batch)
                    if fb is not None:
                        due = mailbox / "feedback" / fb.name
                        due.parent.mkdir(exist_ok=True)
                        shutil.copyfile(fb, due)
                        st = step(["feedback", str(due), "--state-dir", str(state)])
                        rec["steps"].append({"step": "feedback", **{k: v for k, v in st.items() if k != "stdout"}})
                        if st["rc"] != 0:
                            rec["error"] = (rec["error"] + "; " if rec["error"] else "") + \
                                f"feedback exited {st['rc']}: {st['stderr'].strip()[-300:]}"
                        delivered.setdefault(world, {})[batch] = json.loads(fb.read_text())
                    n = len(S.report_items(rec["report"] or {}))
                    log(f"  {mode:10} {world} {batch} as of {as_of}: {n} item(s)"
                        + (f"  [{rec['error'][:160]}]" if rec["error"] else ""))
                    out.append(rec)
            finally:
                shutil.rmtree(root, ignore_errors=True)
    return runs, delivered


def mailboxes(data: Path, key: dict) -> dict:
    first = next(iter(key["worlds"]), "W1")
    return {w: world_dir(data, w, first) for w in key["worlds"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_grader.py", description="replay the batches through a harness and score it")
    ap.add_argument("--harness", required=True, help='the command that runs your harness, e.g. "python harness/harness.py"')
    ap.add_argument("--data", required=True, help="the mailbox: the folder holding batch_01/, batch_02/ ...")
    ap.add_argument("--key", required=True, help="answers folder (data/scenarios/answers) or an answer_key.json")
    ap.add_argument("--mode", choices=["supervised", "autonomous", "both"], default="both")
    ap.add_argument("--out", help="write the report card as JSON here")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds per ingest / report / feedback step")
    ap.add_argument("--feedback-dir", help="feedback files (<world>_<batch>.json); default <data>/feedback")
    ap.add_argument("--reports-dir", help="also save every report.json here")
    ap.add_argument("--exclude-key", help="a key whose items are replayed but not scored (the reviewer passes the "
                    "practice answers, so only items the candidate has not seen count)")
    ap.add_argument("--work-dir", help="where the per-run sandboxes go (default: the system temp folder); keep it "
                    "free of keys and generated splits")
    ap.add_argument("--quiet", action="store_true", help="print only the card")
    ap.add_argument("--sandbox", action="store_true", help="reviewer mode: run every step in the grading sandbox "
                    "(docker; sandbox/ in the reviewer's repo, not shipped to candidates)")
    ap.add_argument("--submission", help="with --sandbox: the submission's root folder, copied into the image "
                    "(default: the current folder); the harness file must be inside it")
    a = ap.parse_args(argv)
    data = Path(a.data)
    try:
        key = S.load_key(a.key, data)
        exclude = S.load_key(a.exclude_key) if a.exclude_key else None
    except (OSError, ValueError, KeyError) as e:
        print(f"run_grader: can't read the key {a.key}: {e}", file=sys.stderr)
        return 2
    if not data.is_dir():
        print(f"run_grader: no data folder {data}", file=sys.stderr)
        return 2
    harness = shlex.split(a.harness)
    if harness and harness[0] in ("python", "python3"):
        harness[0] = sys.executable            # the same interpreter (and packages) as the grader
    modes = list(MODES) if a.mode == "both" else [a.mode]
    log = (lambda *x, **k: None) if a.quiet else (lambda s: print(s, file=sys.stderr))
    log(f"replaying {sum(len(b) for b in key['worlds'].values())} batch(es) in {len(key['worlds'])} world(s), "
        f"modes {', '.join(modes)}")
    sandbox = None
    if a.sandbox:
        runner = Path(__file__).resolve().parents[1] / "sandbox" / "runner.py"
        if not runner.is_file():
            print("run_grader: --sandbox is the reviewer's grading sandbox and is not part of this pack; run without "
                  "it", file=sys.stderr)
            return 2
        import importlib.util
        spec = importlib.util.spec_from_file_location("nova_sandbox_runner", runner)
        SB = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(SB)
        try:
            sandbox = SB.Sandbox(Path(a.submission or "."), log=log)
            sandbox.container_cmd(absolute(harness))
            sandbox.start()
        except SB.SandboxError as e:
            print(f"run_grader: sandbox: {e}", file=sys.stderr)
            return 2
    try:
        runs, delivered = replay(harness, data, key, modes, a.timeout,
                                 Path(a.feedback_dir) if a.feedback_dir else None, log,
                                 Path(a.reports_dir) if a.reports_dir else None,
                                 Path(a.work_dir) if a.work_dir else None, sandbox)
    finally:
        if sandbox is not None:
            sandbox.stop()
    card = S.score(key, runs, mailboxes(data, key), delivered, exclude)
    if sandbox is not None:
        card["sandbox"] = sandbox.summary()
        u = card["sandbox"]["llm_usage"]
        log(f"sandbox: {card['sandbox']['steps']} container step(s); LLM proxy {u.get('requests', 0)} request(s), "
            f"{u.get('input_tokens', 0)} input / {u.get('output_tokens', 0)} output tokens, "
            f"{u.get('refused', 0)} refused")
    card["runs"] = {m: {w: [{"batch": r["batch"], "as_of": r["as_of"], "error": r["error"], "steps": r["steps"],
                             "items": len(S.report_items(r["report"] or {}))} for r in rs] for w, rs in ws.items()}
                    for m, ws in runs.items()}
    print(S.page(card))
    if a.out:
        Path(a.out).write_text(json.dumps(card, indent=1, ensure_ascii=False, default=str) + "\n")
    green = all(res.get("pass") for res in card["sheets"].values()) and card["sheets"]
    return 0 if green and not card["capped_by_hard_gate"] else 1


if __name__ == "__main__":
    sys.exit(main())
