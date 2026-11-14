"""Freshershunt Pro (private Telegram channel) -> jobs.

The channel can't be read from outside (private), so the FresherPilot extension watches the owner's open
Telegram Web tab and sends every new message here (`POST /api/pro/ingest`). Three post shapes (measured Nov 13 2026):
  1. digests   "14 TECHNICAL FRESHER JOB OPENINGS ..." with blocks "N. Company: X / Role: Y / Location / Apply Link: URL"
               (official Workday / Oracle / company links, e.g. NTT DATA's nttlimited.wd3.myworkdayjobs.com);
  2. lists     "N. Company — Role" followed by the link on the next line (WFH lists);
  3. single    a re-shared LinkedIn post ("IBM Hiring for Freshers ... Apply Link: https://lnkd.in/xxxx"): the lnkd.in
               link is a redirect to the real page (IBM's postings are only reachable this way).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from fresherpilot.jobs import free_boards

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
_BLOCK = re.compile(r"(?m)^\s*\d+\.\s*Company\s*:")
_LISTED = re.compile(r"(?m)^\s*\d+\.\s*(?P<company>[^\n—–]{2,60}?)\s+[—–-]\s+(?P<title>[^\n]{3,140})\n\s*(?P<url>https?://\S+)")
_SKIP = re.compile(r"mercor\.com|freshershunt\.in|fhlinks\.in|t\.me/|whatsapp", re.I)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").replace("​", "")


def resolve_link(url: str) -> str:
    """Where a link really goes: lnkd.in / linkedin.com/safety/go interstitials give the external page."""
    url = free_boards.unshorten(url)
    try:
        host = urlparse(url).netloc.lower()
        if host.endswith("lnkd.in") or "linkedin.com/safety/go" in url:
            r = requests.get(url, headers=_HEADERS, timeout=(8, 15), allow_redirects=True)
            final = r.url
            q = parse_qs(urlparse(final).query)
            if "url" in q:
                return unquote(q["url"][0])
            if "linkedin.com/safety/go" in final or "lnkd.in" in urlparse(final).netloc:
                m = re.search(r'href="(https?://[^"]+)"[^>]*>\s*(?:Continue|Open|Visit)', r.text, re.I) or \
                    re.search(r'data-tracking-control-name="external_url_click"[^>]*href="(https?://[^"]+)"', r.text) or \
                    re.search(r'<a[^>]+href="(https?://(?!www\.linkedin\.com)[^"]+)"', r.text)
                if m:
                    return m.group(1).replace("&amp;", "&")
            return final
    except Exception:  # noqa: BLE001 — slow / blocked: keep the short link, it still opens in the browser
        pass
    return url


def _fields(block: str) -> dict[str, str] | None:
    text = _norm(block)
    links = [u.rstrip(").,") for u in re.findall(r"https?://\S+", text)]
    links = [u for u in links if not _SKIP.search(u)]
    return free_boards.parse_telegram_post(text, links)


def parse_message(text: str, links: list[str] | None = None) -> list[dict[str, str]]:
    """Job field dicts (title, company, url, ...) found in one channel message (several for a digest)."""
    text = _norm(text)
    links = list(links or [])
    out: list[dict[str, str]] = []
    if _BLOCK.search(text):  # digest: split on "N. Company:"
        starts = [m.start() for m in _BLOCK.finditer(text)]
        for i, s in enumerate(starts):
            block = text[s: starts[i + 1] if i + 1 < len(starts) else len(text)]
            block = re.split(r"\n\s*(?:freshershunt\.in/pro|Telegram:|WhatsApp:)", block)[0]
            block = re.sub(r"^\s*\d+\.\s*", "", block)  # "1. Company: X" -> "Company: X"
            f = _fields(block)
            if f:
                out.append({**f, "description": block.strip()})
        return out
    listed = list(_LISTED.finditer(text))
    if listed:  # "N. Company — Role" + link
        for m in listed:
            url = m.group("url").rstrip(").,")
            if _SKIP.search(url):
                continue
            out.append({"title": m.group("title").strip(" ·-–")[:120], "company": m.group("company").strip()[:80],
                        "experience": "Not specified", "location": "", "salary": "Not disclosed", "url": url,
                        "description": m.group("company").strip() + " — " + m.group("title").strip() + chr(10) + url})
        return out
    f = _fields(text) if not links else free_boards.parse_telegram_post(text, [u for u in links if not _SKIP.search(u)] +
                                                                         re.findall(r"https?://\S+", text))
    return [f] if f else []


def to_jobs(messages: list[dict[str, Any]], known: set[str] | None = None) -> list[dict[str, Any]]:
    """Messages {id, text, links, at?} from the extension -> job dicts ready for apify_jobs.merge_external."""
    jobs: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for msg in messages:
        mid = str(msg.get("id") or "")
        text = str(msg.get("text") or "")
        if not mid or not text.strip():
            continue
        for n, fields in enumerate(parse_message(text, [str(u) for u in (msg.get("links") or [])])):
            body = fields.pop("description", "") or text[:3000]
            jid = f"tgpro:{mid}:{n}"
            if known and jid in known:
                continue
            url = resolve_link(fields["url"])
            if free_boards._AD_LINK.search(url):
                continue
            jobs.append({
                "id": jid, "source": "Telegram", **fields, "url": url,
                "posted": now.isoformat(), "posted_days": 0, "posted_within_min": 5, "skills": [],
                "description": f"{text[:6000]}\n\n(Posted in Telegram channel Freshershunt Pro, message {mid})",
                "work_type": "", "apply_mode": "site", "via": "tgpro",
            })
    return jobs
