"""Does this email carry a one-time code (or verification link)? A SCORE over several signals, like phone keyboards / Truecaller
do, instead of a fixed phrase list: "Thanks for opening the website, your 6 digit identifier is 482913" counts, a newsletter
with a number in it does not.

    detect(subject, text, html, sender, headers) -> {"code", "link", "score", "why"} | None   (None = not an OTP mail)

Signals (+): a 4-8 character token beside code words (code / otp / pin / passcode / identifier / token / key / "6-digit"),
the token alone on a line or in bold / <code>, expiry and "do not share" wording, a short body, a noreply / auth sender.
Signals (-): List-Unsubscribe / bulk headers, "unsubscribe" text, a long body, invoice / order / receipt subjects, years,
prices, phone numbers and postcodes as the "code". Pure functions: tested offline in `tests/test_otp_detect.py`."""
from __future__ import annotations

import re

THRESHOLD = 5
BORDERLINE = 3          # between BORDERLINE and THRESHOLD the app may ask the AI (see mailwatch.AI)

CODE_WORDS = re.compile(r"(one[- ]?time|verification|verify|confirmation|confirm|security|authentication|authenticat\w*|access|login|log[- ]in|sign[- ]?in|"
                        r"passcode|pass code|passkey|otp|\bpin\b|\bcode\b|identifier|\btoken\b|\bkey\b|6[- ]digit|4[- ]digit|8[- ]digit|six[- ]digit|activation|"
                        r"registration|reset)", re.I)
EXPIRY = re.compile(r"(expires?|valid for|valid until|within \d+ ?(min|minute|hour)|\d+ ?(min|minutes) |do not share|don'?t share|never share|"
                    r"if you (did not|didn'?t) (request|ask|try)|ignore this|was not you|wasn'?t you|single[- ]use|only be used once)", re.I)
BULK = re.compile(r"(unsubscribe|manage (your )?(email )?preferences|view (this )?(email )?in (your )?browser|newsletter|% off|discount|sale ends|limited offer|"
                  r"special offer|deals?\b|follow us)", re.I)
NOT_OTP_SUBJECT = re.compile(r"(invoice|receipt|order|statement|bill|ticket|booking|delivery|shipment|payment|transaction|refund|newsletter|webinar|digest)", re.I)
SENDER_OK = re.compile(r"^(no-?reply|do-?not-?reply|noreply|otp|verify|verification|security|auth|accounts?|account-?security|notifications?|mailer|"
                       r"support|careers?|jobs?|recruit\w*|talent|hr|donotreply|authenticat\w*|login|signin|registration|candidates?)\b", re.I)
LINK = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)
LINK_WORDS = re.compile(r"(verify|verification|confirm|activate|activation|validate|token|registration|register|auth|account|reset|magic|login|signin)", re.I)
BAD_LINK = re.compile(r"(unsubscribe|privacy|facebook|twitter|linkedin\.com/company|instagram|youtube|\.png|\.jpg|\.gif|googleusercontent|w3\.org|mailto:|preferences)", re.I)

# token candidates: 4-8 digits, or 6-8 letters+digits (Greenhouse-style "xYz12ABc") that contain a digit AND a letter
TOKEN = re.compile(r"(?<![\w@/:+#$₹€£%-])(?<!\w\.)(\d{3}[ -]?\d{3}|\d{4,8}|(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{6,8})(?![\w@/:%-]|\.\w)")
# "Access Code:" + the value; any characters (Taleo sends 10-character codes such as 5il$MFEGLJ), but not a plain word
LABELLED = re.compile(r"(access code|verification code|security code|confirmation code|login code|sign[- ]in code|authentication code|passcode|pass code|"
                      r"one[- ]time (?:code|password|pin)|\botp\b|temporary password|access token)\s*(?:is\s*)?[:=-]\s*([^\s<>]{4,24})", re.I)
MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


def _strip_html(html: str) -> tuple[str, list[str]]:
    """(plain text with line breaks, texts that were bold / code / big)"""
    emph = [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r"(?is)<(?:b|strong|code|h1|h2|h3|big)[^>]*>(.*?)</(?:b|strong|code|h1|h2|h3|big)>", html or "")]
    emph += [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r'(?is)<[^>]+style="[^"]*(?:font-size:\s*(?:2\d|3\d|4\d)px|letter-spacing)[^"]*"[^>]*>(.*?)</', html or "")]
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html or "")
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|td)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as _h

    return _h.unescape(t), [e for e in emph if e]


def _bad_context(token: str, around: str) -> bool:
    """Years, prices, phones, postcodes, dates are not codes."""
    low = around.lower()
    digits = re.sub(r"\D", "", token)
    if re.fullmatch(r"(19|20)\d\d", token):
        return True
    if re.search(rf"(₹|rs\.?|inr|usd|\$|€|£)\s*{re.escape(token)}", low) or re.search(rf"{re.escape(token)}\s*(₹|rs\b|inr|usd|%|/-)", low):
        return True
    if re.search(rf"(pin ?code|postal|zip|address)[^.\n]{{0,25}}{re.escape(token)}", low):
        return True
    if re.search(rf"{MONTHS}\s*{re.escape(token)}|{re.escape(token)}\s*{MONTHS}", low) and len(digits) <= 4:
        return True
    if re.search(rf"(\+\d|tel|phone|call|mobile)[^.\n]{{0,15}}{re.escape(token)}", low):
        return True
    return False


def detect(subject: str, text: str = "", html: str = "", sender: str = "", headers: dict | None = None) -> dict | None:
    headers = {k.lower(): str(v) for k, v in (headers or {}).items()}
    plain, emph = _strip_html(html) if html and len(html) > len(text or "") else (text or "", [])
    if html and not emph:
        emph = _strip_html(html)[1]
    body = (plain or text or "").strip()
    subj = subject or ""
    local = (sender or "").split("@")[0].split("<")[-1]
    base = 0
    why: list[str] = []
    # ---- the mail as a whole
    if "list-unsubscribe" in headers or headers.get("precedence", "").lower() in ("bulk", "list", "junk"):
        base -= 3
        why.append("bulk headers")
    if BULK.search(body):
        base -= 3 if re.search(r"unsubscribe", body, re.I) else 2
        why.append("marketing words")
    if NOT_OTP_SUBJECT.search(subj) and not re.search(r"(otp|code|verif)", subj, re.I):
        base -= 3
        why.append("invoice/order subject")
    if len(body) > 5000:
        base -= 2
        why.append("long body")
    elif len(body) < 1200:
        base += 1
    if SENDER_OK.match(local):
        base += 1
        why.append("transactional sender")
    if EXPIRY.search(subj + " " + body[:1500]):
        base += 2
        why.append("expiry / do-not-share wording")
    subject_hint = bool(CODE_WORDS.search(subj))
    if subject_hint:
        base += 1
        why.append("code word in subject")
    # ---- the best token
    best: tuple[int, str] | None = None
    head_text = f"{subj}\n{body[:3000]}"
    for lm in LABELLED.finditer(head_text):
        val = lm.group(2).strip(".,;")
        if len(val) >= 4 and re.search(r"[\d\W_]", val) and not re.fullmatch(r"https?://\S+", val) and not re.fullmatch(r"[A-Za-z]+", val):
            best = (6, val)
            break
    for m in TOKEN.finditer(head_text):
        tok = m.group(1)
        norm = re.sub(r"[ -]", "", tok)
        around = head_text[max(0, m.start() - 90): m.end() + 60]
        if _bad_context(tok, around):
            continue
        s = 0
        before = head_text[max(0, m.start() - 80): m.start()]
        after = head_text[m.end(): m.end() + 40]
        if CODE_WORDS.search(before):
            s += 3
        elif CODE_WORDS.search(after):
            s += 2
        line_start = head_text.rfind("\n", 0, m.start()) + 1
        line_end = head_text.find("\n", m.end())
        line = head_text[line_start: line_end if line_end > 0 else len(head_text)].strip()
        if line == tok or re.fullmatch(r"\W*" + re.escape(tok) + r"\W*", line):
            s += 2                      # the code stands alone on its line
        if any(norm == re.sub(r"[ -]", "", e) or tok == e for e in emph):
            s += 2                      # bold / code / big letters
        if re.search(r"\d", norm) and re.search(r"[A-Za-z]", norm) and s < 3:
            continue                    # a letters+digits token needs a code word beside it (else it is a reference number)
        if len(norm) in (6,):
            s += 1
        if best is None or (s > best[0] and best[0] < 6):
            best = (s, norm)
    link = ""
    links = [u.rstrip(".,;)") for u in LINK.findall(plain + "\n" + (html or "")) if LINK_WORDS.search(u) and not BAD_LINK.search(u)]
    if links:
        link = links[0]
    score = base + (best[0] if best else 0)
    result = {"code": best[1] if best else "", "link": link, "score": score, "why": ", ".join(why)}
    if link and not best:
        # a verification mail with only a link: needs the usual verification words + the mail-level signals
        if re.search(r"(verify|confirm|activate|validate)", subj + " " + body[:600], re.I) and base >= 2:
            result["score"] = THRESHOLD
            return result
    if score >= BORDERLINE and (best or link):
        return result
    return None


def is_otp(res: dict | None) -> bool:
    return bool(res and res["score"] >= THRESHOLD and (res["code"] or res["link"]))
