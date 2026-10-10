"""Read one batch folder: every .eml, its PDF and Excel attachments, as text pages, onto disk.

The text layer is grader/extract.py's, so every quote we cite is checked against the same text. A PDF with no text
layer is a scan: we read it with local OCR (rapidocr), or with Claude vision when OCR isn't installed or reads nothing.
"""
from __future__ import annotations

import sys
from datetime import timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from . import llm
from .common import read_json, write_json

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "grader") not in sys.path:
    sys.path.insert(0, str(ROOT / "grader"))
import extract as X  # noqa: E402  (grader/extract.py: the grader's own text layer)


def _ocr_png(png: bytes) -> str:
    """Local OCR: rapidocr boxes grouped into lines by their vertical position, left to right."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:  # noqa: BLE001 - not installed: the caller falls back to vision
        return ""
    res, _ = RapidOCR()(png)
    if not res:
        return ""
    boxes = []
    for box, txt, _conf in res:
        ys = [p[1] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(p[0] for p in box), txt))
    boxes.sort()
    lines: list[list] = []
    for y, h, x, t in boxes:
        if lines and abs(lines[-1][0] - y) <= max(h, lines[-1][1]) * 0.5:
            lines[-1][2].append((x, t))
        else:
            lines.append([y, h, [(x, t)]])
    return "\n".join(" ".join(t for _, t in sorted(ws)) for _, _, ws in lines)


def read_scan(data: bytes, reader: llm.Reader) -> tuple[list[str], str]:
    """-> (text per page, how it was read)."""
    import pymupdf
    pages, how = [], "ocr"
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for p in doc:
            png = p.get_pixmap(dpi=200).tobytes("png")
            text = _ocr_png(png)
            if len(text.strip()) < 40:
                v = reader.transcribe_image(png)
                if v:
                    text, how = v, "vision"
            pages.append(text)
    return pages, how


def read_email(path: Path, batch: str, reader: llm.Reader) -> dict:
    raw = path.read_bytes()
    msg = X.parse_eml(raw)
    name, addr = parseaddr(str(msg["From"]))
    try:
        dt = parsedate_to_datetime(str(msg["Date"])).astimezone(timezone.utc)
        received = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        received = None
    ref = f"{batch}/{path.name}"
    body = msg.get_body(preferencelist=("plain",))
    rec = {
        "id": ref, "batch": batch, "file": path.name, "received": received,
        "from_name": name, "from_addr": addr.lower(), "to": str(msg["To"] or ""), "cc": str(msg["Cc"] or ""),
        "subject": str(msg["Subject"] or ""), "message_id": str(msg["Message-ID"] or ""),
        "page": X.pages_of(raw, "eml")[0],
        "body": body.get_content().replace("\r\n", "\n") if body else "",
        "attachments": [],
    }
    for fname, data in X.attachments(raw):
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        att = {"name": fname, "ref": f"{ref}#{fname}", "ext": ext, "pages": [], "scan": False, "read": "text"}
        try:
            if ext == "pdf" and X.pdf_is_image_only(data):
                att["scan"] = True
                att["pages"], att["read"] = read_scan(data, reader)
            elif ext in ("pdf", "xlsx"):
                att["pages"] = X.pages_of(data, ext)
            else:
                att["read"] = "skipped"
        except Exception as e:  # noqa: BLE001 - one unreadable attachment must not stop the batch
            att["read"] = f"error: {type(e).__name__}: {e}"
        rec["attachments"].append(att)
    return rec


def ingest(batch_dir: str, state_dir: str) -> int:
    bdir, state = Path(batch_dir), Path(state_dir)
    batch = bdir.name
    reader = llm.Reader(state / "llm_cache")
    n = 0
    for f in sorted(bdir.glob("*.eml")):
        out = state / "docs" / f"{batch}__{f.name}.json"
        if out.is_file():
            continue                      # idempotent: a re-run of the same batch reads nothing twice
        write_json(out, read_email(f, batch, reader))
        n += 1
    meta = read_json(state / "meta.json", {}) or {}
    batches = meta.get("batches", [])
    if batch not in batches:
        batches.append(batch)
    meta["batches"] = sorted(batches)
    write_json(state / "meta.json", meta)
    return n


def load_docs(state_dir: str) -> list[dict]:
    return [read_json(p) for p in sorted((Path(state_dir) / "docs").glob("*.json"))]
