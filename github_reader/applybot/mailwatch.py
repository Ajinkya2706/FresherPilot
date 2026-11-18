"""Forwards every verification / one-time-code email from your Gmail to Telegram within seconds (runs as a thread in the local runner).
Only mails that look like codes / verification links are forwarded; they are also kept in otp_inbox.jsonl (last 200) for the apply engine. Needs GMAIL_USER + GMAIL_APP_PASSWORD (read from .env by the runner)."""
from __future__ import annotations

import email
import imaplib
import os
import re
import threading
import time
from email.utils import parseaddr, parsedate_to_datetime

from . import cloud
from . import otp_detect
from .mail import _hdr, _text, save_inbox

LOOKS = re.compile(r"(verification code|verify your|confirm your (e-?mail|account)|one[- ]time|\botp\b|passcode|security code|login code|sign[- ]in code|activate your account|your code is|is your .{0,30}code|"
                   r"confirm(ation)? (link|code)|authentication code|account verification|complete your registration)", re.I)


AI = None   # optional: set by the app to a callable (system, user, schema) -> parsed JSON, for borderline mails


def _ai_check(subject: str, body: str, res: dict) -> dict | None:
    """Borderline score: ask the model whether the mail contains a one-time code / verification link (any wording)."""
    schema = {"type": "object", "additionalProperties": False, "required": ["is_otp", "code"],
              "properties": {"is_otp": {"type": "boolean"}, "code": {"type": "string"}}}
    try:
        out = AI("Decide if this email is a one-time code / verification-code / identifier email sent to the reader so they can sign in or verify an account. "
                 "Marketing, receipts and newsletters are not. If it is, return the code exactly as written (digits/letters only), else an empty string.",
                 "SUBJECT: " + subject[:200] + chr(10) + chr(10) + "BODY:" + chr(10) + body[:1500], schema)
        if isinstance(out, dict) and out.get("is_otp") and re.fullmatch(r"[A-Za-z0-9]{4,10}", str(out.get("code") or "")):
            return {**res, "code": str(out["code"]), "score": otp_detect.THRESHOLD, "why": "ai"}
    except Exception:  # noqa: BLE001
        pass
    return None


def _forward(text: str, code: str = "") -> None:
    try:
        cloud._call("POST", "/api/apply/notify", json={"text": text[:900], "copy": code})
    except Exception:  # noqa: BLE001
        pass


def _loop(stop: threading.Event) -> None:
    started = time.time() - 120
    seen: set[str] = set()
    while not stop.is_set():
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
            m.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
            try:
                for folder in ("INBOX", "[Gmail]/Spam"):
                    if m.select(folder, readonly=True)[0] != "OK":
                        continue
                    day = time.strftime("%d-%b-%Y", time.gmtime(started - 86400))
                    typ, data = m.search(None, f'(SINCE "{day}")')
                    ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-15:]
                    for i in reversed(ids):
                        typ, d = m.fetch(i, "(RFC822)")
                        if typ != "OK" or not d or not d[0]:
                            continue
                        msg = email.message_from_bytes(d[0][1])
                        mid = str(msg.get("Message-ID") or i)
                        if mid in seen:
                            continue
                        try:
                            ts = parsedate_to_datetime(msg["Date"]).timestamp()
                        except Exception:  # noqa: BLE001
                            ts = time.time()
                        if ts < started:
                            seen.add(mid)
                            continue
                        seen.add(mid)
                        subject = _hdr(msg["Subject"])
                        body = _text(msg)
                        sender_addr = parseaddr(_hdr(msg["From"]))[1]
                        html = chr(10).join((p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "replace")
                                         for p in msg.walk() if p.get_content_type() == "text/html")
                        plain = chr(10).join((p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "replace")
                                          for p in msg.walk() if p.get_content_type() == "text/plain") or body
                        res = otp_detect.detect(subject, plain, html, sender_addr,
                                                {k: msg.get(k, "") for k in ("List-Unsubscribe", "Precedence", "Auto-Submitted")})
                        if res and not otp_detect.is_otp(res) and AI is not None:   # borderline wording: let the AI read it
                            res = _ai_check(subject, plain or body, res) or res
                        if not otp_detect.is_otp(res):
                            continue
                        sender = sender_addr.split("@")[-1] or "?"
                        code, link = res["code"], res["link"]
                        save_inbox({"ts": ts, "sender": sender, "subject": subject[:120], "code": code, "link": link[:600]})
                        parts = [f"🔐 <b>{sender}</b>: {subject[:80]}"]
                        if code:
                            parts.append(f"Code (tap to copy): <code>{code}</code>")
                        if link:
                            parts.append(f"Link: {link[:300]}")
                        _forward(chr(10).join(parts), code)
            finally:
                try:
                    m.logout()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        stop.wait(20)


def start() -> threading.Event | None:
    if not (os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")):
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), daemon=True).start()
    return stop
