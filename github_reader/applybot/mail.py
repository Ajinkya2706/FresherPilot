"""Reads verification codes / links straight from the owner's Gmail (IMAP + app password): no Telegram step, nothing manual.
env: GMAIL_USER, GMAIL_APP_PASSWORD. Only mails that arrived after `since` and that look like they come from the portal are used.
Nothing from a mail is ever printed (the repo's logs are public)."""
from __future__ import annotations

import email
import imaplib
import os
import re
import time
from email.header import decode_header
from email.utils import parsedate_to_datetime
from html import unescape

CODE_NEAR = re.compile(r"(?:code|otp|passcode|pin|verification|verify|security)[^0-9]{0,60}\b(\d{4,8})\b", re.I)
CODE_ALONE = re.compile(r"(?m)^\s*(\d{6})\s*$")
LINK = re.compile(r"https?://[^\s\"'<>)]+", re.I)
LINK_WORDS = re.compile(r"(verify|verification|confirm|activate|activation|validate|token|registration|register|account|auth)", re.I)
BAD_LINK = re.compile(r"(unsubscribe|privacy|facebook|twitter|linkedin\.com/company|instagram|youtube|\.png|\.jpg|\.gif|googleusercontent|w3\.org|mailto:)", re.I)


# ---- the OTP inbox: the mail watcher (mailwatch.py) saves every code / verification link it forwards to Telegram here,
# and the engine takes codes from this file first ("whenever the system needs one it takes it from there").
def inbox_path():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    d = next((p.parent for p in sorted((root / "users").glob("*/applicant_profile.json"))), root)
    return d / "otp_inbox.jsonl"


def save_inbox(entry: dict) -> None:
    import json

    try:
        p = inbox_path()
        lines = p.read_text(encoding="utf-8").splitlines()[-199:] if p.exists() else []
        p.write_text(chr(10).join(lines + [json.dumps(entry, ensure_ascii=False)]) + chr(10), encoding="utf-8")
    except OSError:
        pass


def from_inbox(since: float, tokens: list[str], want: str = "any", max_age_s: float = 900) -> tuple[str, str] | None:
    """Newest saved code / link that arrived after `since`: one from the portal (its name in sender / subject) first;
    with no brand match only when exactly one fresh mail is there (never a guess among several)."""
    import json

    try:
        rows = [json.loads(x) for x in inbox_path().read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return None
    now = time.time()
    fresh = [r for r in rows if r.get("ts", 0) >= since and now - r.get("ts", 0) <= max_age_s]
    fresh.sort(key=lambda r: r["ts"], reverse=True)
    branded = [r for r in fresh if any(t in f"{r.get('sender', '')} {r.get('subject', '')}".lower() for t in tokens)] if tokens else []
    pool = branded if tokens else (fresh if len(fresh) == 1 else [])   # a known portal: only ITS mail, never another sender's code
    for r in pool:
        if want in ("code", "any") and r.get("code"):
            return ("code", r["code"])
        if want in ("link", "any") and r.get("link"):
            return ("link", r["link"])
        if want == "link" and r.get("code"):
            return ("code", r["code"])
        if want == "code" and r.get("link"):
            return ("link", r["link"])
    return None


def configured() -> bool:
    return bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))


def _text(msg: email.message.Message) -> str:
    out = []
    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/plain", "text/html"):
            continue
        try:
            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        if ct == "text/html":
            links = re.findall(r'href=["\']([^"\']+)["\']', body, re.I)
            body = re.sub(r"(?is)<(script|style).*?</\1>", " ", body)
            body = unescape(re.sub(r"<[^>]+>", "\n", body)) + "\n" + "\n".join(unescape(x) for x in links)
        out.append(body)
    return "\n".join(out)


def _hdr(v: str) -> str:
    try:
        return "".join((t.decode(c or "utf-8", "replace") if isinstance(t, bytes) else t) for t, c in decode_header(v or ""))
    except Exception:  # noqa: BLE001
        return v or ""


def _tokens(host: str) -> list[str]:
    parts = [p for p in re.split(r"[.\-]", host.lower()) if p and p not in ("www", "com", "in", "co", "org", "net", "careers", "career", "jobs", "wd1", "wd3", "wd5", "wd103", "myworkdayjobs", "taleo", "eu", "io")]
    return [p for p in parts if len(p) >= 4] + ["successfactors", "workday", "icims", "smartrecruiters", "greenhouse", "lever"] * 0


def _scan(m: imaplib.IMAP4_SSL, folder: str, since: float, tokens: list[str], want: str):
    try:
        if m.select(folder, readonly=True)[0] != "OK":
            return None
    except Exception:  # noqa: BLE001
        return None
    day = time.strftime("%d-%b-%Y", time.gmtime(since - 86400))
    typ, data = m.search(None, f'(SINCE "{day}")')
    ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-25:]
    cands = []
    for i in reversed(ids):
        typ, d = m.fetch(i, "(RFC822)")
        if typ != "OK" or not d or not d[0]:
            continue
        msg = email.message_from_bytes(d[0][1])
        try:
            ts = parsedate_to_datetime(msg["Date"]).timestamp()
        except Exception:  # noqa: BLE001
            ts = time.time()
        if ts < since:
            continue
        head = f"{_hdr(msg['From'])} {_hdr(msg['Subject'])}".lower()
        body = _text(msg)
        low = (head + " " + body[:3000]).lower()
        brand = any(t in low for t in tokens) if tokens else True
        from . import otp_detect

        res = otp_detect.detect(_hdr(msg["Subject"]), body, "", _hdr(msg["From"]), {k: msg.get(k, "") for k in ("List-Unsubscribe", "Precedence")})
        # scored like the watcher: a clear OTP mail counts; a borderline one only when it names the portal we are waiting for
        scored = bool(res) and (res["score"] >= otp_detect.THRESHOLD or (brand and res["score"] >= otp_detect.BORDERLINE))
        old_rule = bool(re.search(r"(verif|confirm|activat|one[- ]time|otp|passcode|security code)", head + " " + body[:600], re.I))
        if scored or old_rule:
            cands.append((brand, ts, body, (res or {}).get("code", "")))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    for brand, ts, body, rcode in cands:
        if not brand and len(cands) > 1:
            continue   # several unrelated mails and none mentions the portal: do not guess
        code = CODE_NEAR.search(body) or CODE_ALONE.search(body)
        links = [u.rstrip(".,;") for u in LINK.findall(body) if LINK_WORDS.search(u) and not BAD_LINK.search(u)]
        if want in ("code", "any") and rcode:   # the scored detector's code (handles 10-character / symbol codes)
            return ("code", rcode)
        if want in ("code", "any") and code:
            return ("code", code.group(1))
        if want in ("link", "any") and links:
            return ("link", links[0])
        if want == "link" and code:
            return ("code", code.group(1))
        if want == "code" and links:
            return ("link", links[0])
    return None


def wait(host: str, since: float, want: str = "any", minutes: float = 4.0, brands: tuple | list = ()) -> tuple[str, str] | None:
    """('code', '123456') | ('link', 'https://...') | None. Polls Gmail every ~8 s (inbox, then spam)."""
    if not configured():
        return None
    tokens = _tokens(host) + [w for b in brands for w in re.split(r"[^a-z0-9]+", str(b).lower()) if len(w) >= 4 and w not in ("limited", "private", "technologies", "services", "india", "solutions")]
    end = time.time() + minutes * 60
    while time.time() < end:
        got = from_inbox(since, tokens, want)   # the watcher already saw it (and sent it to Telegram)
        if got:
            return got
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
            m.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
            try:
                for folder in ("INBOX", "[Gmail]/Spam"):
                    r = _scan(m, folder, since, tokens, want)
                    if r:
                        return r
            finally:
                try:
                    m.logout()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        time.sleep(8)
    return None


def wait_mail(host: str, since: float, brands: tuple | list = (), minutes: float = 4.0, pattern: str = "") -> tuple[str, str] | None:
    """(subject, text) of the newest mail after `since` that names the portal (host / company words) and, if given, matches
    `pattern` in its text. Used by account recovery (username mails, reset links). Polls Gmail like wait()."""
    if not configured():
        return None
    tokens = _tokens(host) + [w for b in brands for w in re.split(r"[^a-z0-9]+", str(b).lower()) if len(w) >= 4 and w not in ("limited", "private", "technologies", "services", "india", "solutions")]
    end = time.time() + minutes * 60
    while time.time() < end:
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
            m.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
            try:
                for folder in ("INBOX", "[Gmail]/Spam"):
                    if m.select(folder, readonly=True)[0] != "OK":
                        continue
                    day = time.strftime("%d-%b-%Y", time.gmtime(since - 86400))
                    typ, data = m.search(None, f'(SINCE "{day}")')
                    ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-20:]
                    for i in reversed(ids):
                        typ, d = m.fetch(i, "(RFC822)")
                        if typ != "OK" or not d or not d[0]:
                            continue
                        msg = email.message_from_bytes(d[0][1])
                        try:
                            ts = parsedate_to_datetime(msg["Date"]).timestamp()
                        except Exception:  # noqa: BLE001
                            ts = time.time()
                        if ts < since:
                            continue
                        head = f"{_hdr(msg['From'])} {_hdr(msg['Subject'])}"
                        text = _text(msg)
                        low = (head + " " + text[:3000]).lower()
                        if tokens and not any(t in low for t in tokens):
                            continue
                        if pattern and not re.search(pattern, text, re.I):
                            continue
                        return _hdr(msg["Subject"]), text
            finally:
                try:
                    m.logout()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        time.sleep(8)
    return None
