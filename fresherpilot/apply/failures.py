"""Failure taxonomy for application attempts: every skipped/failed/parked line of `autoapply_log.jsonl` maps to one
code, so "it breaks at many points" becomes a ranked list of problems. Pure; `scripts/apply_health.py` prints it.

Codes (first match wins, order matters):
  closed_posting      the job no longer accepts applications            -> free pre-check, never open a tab
  already_applied     board says we applied
  limit_reached       daily Easy Apply / quota limit
  captcha             CAPTCHA / security check                          -> needs_you
  auth_required       sign-in / account creation needed
  otp_needed          verification code / link requested
  needs_human         assessment, link/file asked, "answer:" questions the bank can't answer
  validation_loop     same step repeated, nothing changed
  too_many_steps      step budget used up
  stuck_timeout       took over / stuck page
  page_error          tab/frame crashed, kept reloading, closed
  button_not_found    no usable apply/next/submit button
  user_skipped        stopped or skipped by the owner
  other"""
from __future__ import annotations

import re
from typing import Any

_RULES: list[tuple[str, re.Pattern[str]]] = [(c, re.compile(p, re.I)) for c, p in [
    ("closed_posting", r"no longer accepting|not (currently )?accepting|applications? (are )?closed|unavailable or removed|"
                       r"job (has )?expired|position (has been )?filled|job removed|closed or removed|removed or the job id|posting (is|has been) (closed|removed)|"
                       r"no specific job listing"),
    ("handed_off", r"handed to the local playwright runner|handed to the cloud"),
    ("already_applied", r"already applied|you applied|applied (to|earlier)|already (been )?submitted|application submitted"),
    ("not_eligible", r"not eligible|requires .* location|location (mismatch|requirement)"),
    ("limit_reached", r"daily limit|limit reached|quota"),
    ("captcha", r"captcha|security check|verify you are human|turnstile"),
    ("otp_needed", r"\botp\b|verification code|verify your email|one[- ]time"),
    ("auth_required", r"sign ?in|log ?in|create (an )?account|password|register"),
    ("validation_loop", r"no progress|same step repeated|validation"),
    ("wrong_page", r"not the (actual|specific) job|'not found'|not found|isn't available|homepage|fraud-reporting"),
    ("too_many_steps", r"too many steps"),
    ("stuck_timeout", r"took over|stuck|timed? ?out|no result within|killed"),
    ("page_error", r"frame with id|error page|kept reloading|keeps reloading|tab (was )?closed|no tab with id|no current window|"
                   r"tabs cannot be edited|cannot read properties|extension stopped answering"),
    ("button_not_found", r"chosen button disappeared|no (visible|listed)|couldn't find a safe button|no clickable"),
    ("needs_human", r"answer:|assessment|email a link|project|upload|cv upload|requires the candidate|needs you:|"
                    r"easy apply (alone )?(is|isn|not)|does not display an apply|redirect(ed)? (confirmation|to the company)|whatsapp|official .* website|apply (via|using)"),
    ("user_skipped", r"by you"),
]]


def classify(detail: str, event: str = "") -> str:
    text = (detail or "").strip()
    for code, pat in _RULES:
        if pat.search(text):
            return code
    return "user_skipped" if event == "stopped" else "other"


# Failure codes where retrying cannot help (job-state facts) vs those worth a re-try or a code fix
TERMINAL = {"not_eligible", "closed_posting", "already_applied", "limit_reached", "user_skipped", "handed_off"}


def summarize(log: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts per outcome and per failure code (skipped/failed/parked lines)."""
    outcomes: dict[str, int] = {}
    codes: dict[str, int] = {}
    for line in log:
        ev = str(line.get("event") or "")
        outcomes[ev] = outcomes.get(ev, 0) + 1
        if ev in ("skipped", "failed", "parked"):
            code = classify(str(line.get("detail") or ""), ev)
            codes[code] = codes.get(code, 0) + 1
    return {"outcomes": outcomes, "failure_codes": dict(sorted(codes.items(), key=lambda kv: -kv[1]))}


# Codes that point at OUR automation breaking on a site (not at the job): 3 of a source's last 5 finished attempts
# like this = its DOM probably changed -> pause that source instead of burning every job (per-site breaker).
BREAKING = {"page_error", "button_not_found", "validation_loop", "too_many_steps", "stuck_timeout", "wrong_page"}


def tripped_sources(log: list[dict[str, Any]], window: int = 5, limit: int = 3, max_age_h: float = 12.0) -> dict[str, int]:
    """{source: breaking failures among its last `window` finished attempts} for sources at/over `limit`.
    A finished attempt = applied / skipped / failed / parked line carrying a uid "<Source>:<id>". Only the last
    `max_age_h` hours count, so a broken site is retried the next day (after a fix or a site recovery)."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).timestamp()
    last: dict[str, list[bool]] = {}
    for line in log:
        uid = str(line.get("uid") or "")
        ev = line.get("event")
        if ":" not in uid or ev not in ("applied", "skipped", "failed", "parked"):
            continue
        try:
            at = datetime.fromisoformat(str(line.get("at")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if now - at > max_age_h * 3600:
            continue
        src = uid.split(":", 1)[0]
        broke = ev in ("skipped", "failed", "parked") and classify(str(line.get("detail") or ""), ev) in BREAKING
        last.setdefault(src, []).append(broke)
    return {s: sum(v[-window:]) for s, v in last.items() if sum(v[-window:]) >= limit}
