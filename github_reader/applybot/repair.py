"""Validation-error repair: a page says a value is not accepted -> pick the next sensible value (no AI, instant).

  end date = start date          -> end = start + 1 month
  salary / CTC / number 0 refused -> 1 (then 2)
  "enter a number" for text       -> 0, then 1
  "letters only" for a number     -> "Fresher"
  too long                        -> cut to maxlength
  number outside min..max         -> clamp

`repair_value(field, fields, tries)` returns the new value (str) or None when no rule applies. Pure: the engine sets it.
"""
from __future__ import annotations

import re
from typing import Any


def _digits(v: str) -> list[str]:
    return re.findall(r"\d+", str(v or ""))


def parse_month(value: str) -> tuple[int, int, str] | None:
    """(month, year, format) from '08/2026', '8/2026', '2026-08', '2026-08-01', '01/08/2026' (day/month/year)."""
    v = str(value or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s*[/.-]\s*(\d{4})", v)
    if m:
        return int(m[1]), int(m[2]), "mm/yyyy"
    m = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{1,2})", v)
    if m:
        return int(m[2]), int(m[1]), "yyyy-mm"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        return int(m[2]), int(m[1]), "iso:" + m[3]
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", v)
    if m:
        return int(m[2]), int(m[3]), "dmy:" + m[1]
    return None


def fmt_month(month: int, year: int, fmt: str) -> str:
    while month > 12:
        month, year = month - 12, year + 1
    while month < 1:
        month, year = month + 12, year - 1
    if fmt == "mm/yyyy":
        return f"{month:02d}/{year}"
    if fmt == "yyyy-mm":
        return f"{year}-{month:02d}"
    if fmt.startswith("iso:"):
        return f"{year}-{month:02d}-{int(fmt[4:]):02d}"
    if fmt.startswith("dmy:"):
        return f"{int(fmt[4:]):02d}/{month:02d}/{year}"
    return f"{month:02d}/{year}"


def shift_month(value: str, delta: int) -> str | None:
    p = parse_month(value)
    if not p:
        return None
    return fmt_month(p[0] + delta, p[1], p[2]) if p[2] != "x" else None


def _err(f: dict[str, Any]) -> str:
    return " ".join(str(f.get(k) or "") for k in ("error", "validation", "hint")).lower()


DATE_CLASH = re.compile(r"same|equal|must be (after|later|greater)|after the start|later than|before (the )?start|earlier than|cannot be (before|earlier)|"
                        r"end date|date range|between|invalid date|start date", re.I)
NEEDS_POSITIVE = re.compile(r"greater than|larger than|more than|at least|minimum|positive|cannot be (zero|0)|must be (a )?[1-9]|not (be )?(zero|0)|"
                            r"enter a (valid )?(number|value|amount)|invalid", re.I)


def _is_end(label: str) -> bool:
    return bool(re.search(r"\b(end|to|until|graduation|completion|finish|expected)\b", label, re.I)) and not re.search(r"\b(start|from|begin)\b", label, re.I)


def _is_start(label: str) -> bool:
    return bool(re.search(r"\b(start|from|begin|joining|joined)\b", label, re.I))


def repair_value(f: dict[str, Any], fields: list[dict[str, Any]], tries: int = 0) -> str | None:
    """New value for `f` given the error the page shows for it, or None."""
    err = _err(f)
    value = str(f.get("value") or "").strip()
    label = str(f.get("label") or "")
    kind = f.get("kind")
    bad = bool(f.get("invalid") or err.strip())
    if not bad:
        return None
    if tries >= 3:
        return None

    # 1) dates: end must be after start
    is_date = kind == "date" or f.get("htype") in ("wd-date", "date", "month") or parse_month(value) is not None
    if is_date and value and (DATE_CLASH.search(err) or f.get("invalid")):
        if _is_end(label):
            partner = next((o for o in fields if o is not f and o.get("value") and parse_month(o["value"]) and _is_start(o.get("label", ""))
                            and _group(o) == _group(f)), None)
            base = partner["value"] if partner else value
            return shift_month(base, 1 + tries)           # same month -> next month (August), then September
        if _is_start(label):
            return shift_month(value, -(1 + tries))
        return shift_month(value, 1 + tries)

    # 2) numbers the page refuses
    low = (f.get("min") or "").strip()
    high = (f.get("max") or "").strip()
    num = re.fullmatch(r"\d+(\.\d+)?", value)
    if num and low and float(value) < float(low):
        return low
    if num and high and float(value) > float(high):
        return high
    m = re.search(r"between (\d+(?:\.\d+)?) and (\d+(?:\.\d+)?)", err)
    if num and m:
        lo, hi = float(m[1]), float(m[2])
        x = float(value)
        if x < lo or x > hi:
            return _n(min(max(x, lo), hi))
    if (not value or (num and float(value) == 0)) and NEEDS_POSITIVE.search(err):
        return str(max(1, int(float(low))) if low else 1 + tries)   # 0 refused -> 1, then 2
    if value and not num and re.search(r"number|numeric|digits|decimal|whole", err) and not re.search(r"letters|text only", err):
        return "0" if tries == 0 else "1"
    if num and re.search(r"letters|alphabet|text|characters only|alphanumeric", err):
        return "Fresher" if tries == 0 else "NA"

    # 3) too long
    ml = int(f.get("maxlength") or 0)
    if ml and len(value) > ml:
        return value[:ml].rstrip()
    return None


def _n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _group(f: dict[str, Any]) -> str:
    """Fields of one entry (same education / job block): Workday block id, else the name prefix."""
    return str(f.get("block") or re.sub(r"(start|end|from|to)\w*$", "", str(f.get("name") or ""), flags=re.I))
