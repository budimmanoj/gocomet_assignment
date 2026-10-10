"""Small shared helpers: money, dates, identifiers, JSON on disk."""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal("0")

# ---- money ------------------------------------------------------------------------------------------------------------
MONEY_RE = re.compile(r"^-?\(?[\d,]*\d\.\d{2}\)?$")


def dec(x) -> Decimal | None:
    """'1,234.56', 'USD 12.00', '(5.00)' -> Decimal. None when it isn't a number."""
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    s = str(x).strip()
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in ("-", "."):
        return None
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return -v if neg else v


def r2(x: Decimal) -> Decimal:
    """Round half up to cents (ties away from zero), the only rounding the glossary allows."""
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def money(x: Decimal | None) -> str | None:
    return None if x is None else f"{r2(x):.2f}"


def pct_of(pct: Decimal, base: Decimal) -> Decimal:
    return r2(pct / 100 * base)


# ---- dates ------------------------------------------------------------------------------------------------------------
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
ISO_RE = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
DMY_RE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
WORD_DATE_RE = re.compile(r"\b(\d{1,2})[ -]([A-Za-z]{3,9})\.?[ -,]*(\d{4})\b")
WORD_DATE2_RE = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2}),? (\d{4})\b")
YM_RE = re.compile(r"^(\d{4})-(\d{2})$")


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def to_date(s) -> date | None:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    m = ISO_RE.search(str(s))
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


def parse_date(tok: str, dayfirst: bool | None = True) -> date | None:
    """ISO, DD/MM/YYYY (or MM/DD when dayfirst is False), '05 Jun 2035', 'June 5, 2035'."""
    tok = tok.strip()
    d = to_date(tok) if ISO_RE.search(tok) else None
    if d:
        return d
    m = DMY_RE.search(tok)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        order = [(a, b), (b, a)] if dayfirst is not False else [(b, a), (a, b)]
        for dd, mm in order:
            try:
                return date(y, mm, dd)
            except ValueError:
                continue
        return None
    m = WORD_DATE_RE.search(tok)
    if m and m[2].lower() in MONTHS:
        try:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
        except ValueError:
            return None
    m = WORD_DATE2_RE.search(tok)
    if m and m[1].lower() in MONTHS:
        try:
            return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
        except ValueError:
            return None
    return None


def find_dates(text: str, dayfirst: bool | None = True) -> list[date]:
    out = []
    for rx in (ISO_RE, DMY_RE, WORD_DATE_RE, WORD_DATE2_RE):
        for m in rx.finditer(text):
            d = parse_date(m.group(0), dayfirst)
            if d:
                out.append((m.start(), d))
    return [d for _, d in sorted(out)]


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def quarter_of(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def quarter_bounds(q: str) -> tuple[date, date]:
    y, n = int(q[:4]), int(q[-1])
    start = date(y, 3 * (n - 1) + 1, 1)
    end = add_months(start, 3) - timedelta(days=1)
    return start, end


# ---- identifiers ------------------------------------------------------------------------------------------------------
def norm_invoice(s: str) -> str:
    return re.sub(r"[\s#:]", "", str(s or "")).upper()


def nospace(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def norm_ws(s: str) -> str:
    return " ".join(str(s or "").split())


# A waybill: carrier letters + digits (TX12345678, CA12345678), or IATA style 123-12345678; houses end in -H<n>.
AWB_RE = re.compile(r"^(?:[A-Z]{2,4}\d{7,11}|\d{3}-?\d{8})(?:-H\d{1,3})?$")
AWB_IN_TEXT = re.compile(r"\b(?:[A-Z]{2,4}\d{7,11}|\d{3}-\d{8})(?:-H\d{1,3})?\b")
# A lane: two station codes joined by a dash (USS2-INW2, DEFRA-USJFK).
LANE_RE = re.compile(r"^[A-Z]{2,5}\d{0,2}-[A-Z]{2,5}\d{0,2}$")
LANE_IN_TEXT = re.compile(r"\b[A-Z]{2,5}\d{0,2}-[A-Z]{2,5}\d{0,2}\b")
CONTRACT_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z]{2,3}-[A-Z]{2,5}-[A-Z]?\d{1,4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def master_awb(awb: str) -> str:
    return re.sub(r"-H\d+$", "", awb or "")


# ---- disk -------------------------------------------------------------------------------------------------------------
def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, data) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
