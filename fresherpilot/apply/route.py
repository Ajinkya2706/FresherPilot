"""Step 1 of both pipelines: decide where a job is applied for. Pure functions (no network, no browser), so every
rule is testable offline on saved job records (`scripts/test_route.py`).

    easy        apply inside the board's own app (LinkedIn Easy Apply, Naukri, Indeed, Internshala, Wellfound)
                -> pipeline A, owner's real Chrome (extension)
    site        the company's own site / ATS -> pipeline B (Playwright, per-portal password, OTP over Telegram)
    needs_check not known yet: the caller must look at the page (never guessed silently, never sent to B blindly)

Every answer carries its evidence: {"cls", "signal", "host", "ats", "board"} so a wrong class can be traced."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Board hosts: a job whose link is on one of these is applied for through that board (unless the board says
# "company site"). Value = the source name the board uses in job["source"].
BOARDS = {
    "linkedin.com": "LinkedIn", "naukri.com": "Naukri", "indeed.com": "Indeed", "internshala.com": "Internshala",
    "wellfound.com": "Wellfound", "angel.co": "Wellfound", "foundit.in": "Foundit", "monsterindia.com": "Foundit",
    "cutshort.io": "Cutshort", "glassdoor.com": "Glassdoor", "shine.com": "Shine", "instahyre.com": "Instahyre",
    "hirist.tech": "Hirist", "hirist.com": "Hirist", "iimjobs.com": "IIMJobs", "ziprecruiter.com": "ZipRecruiter",
}
# Links that are not an application page at all (aggregators, messengers, shorteners, blog posts)
NOT_A_PORTAL = ("t.me", "telegram.me", "freshershunt.in", "lnkd.in", "bit.ly", "tinyurl.com", "wa.me", "whatsapp.com",
                "youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com", "x.com")

# ATS fingerprints by host, then by path. `ready` = verified by a live dry run on a real form (Greenhouse, Lever, Ashby,
# Nov 18 2026); SmartRecruiters answers headless Chromium with "Access is temporarily restricted".
_ATS_HOST = [
    ("workday", r"(^|\.)myworkdayjobs\.com$|(^|\.)myworkdaysite\.com$|(^|\.)wd\d+\.myworkdayjobs\.com$", False),
    ("greenhouse", r"(^|\.)greenhouse\.io$", True),
    ("lever", r"(^|\.)lever\.co$", True),
    ("ashby", r"(^|\.)ashbyhq\.com$", True),
    ("smartrecruiters", r"(^|\.)smartrecruiters\.com$", False),  # bot-blocks headless browsers (live 2026-11-18)
    ("successfactors", r"(^|\.)successfactors\.(com|eu)$|(^|\.)jobs2web\.com$", False),
    ("taleo", r"(^|\.)taleo\.net$", False),
    ("icims", r"(^|\.)icims\.com$", False),
    ("oracle", r"(^|\.)oraclecloud\.com$|(^|\.)oracle\.com$", False),
    ("zoho", r"(^|\.)zohorecruit\.(com|in)$|(^|\.)zrecruit\.(com|in)$", False),
    ("phenom", r"(^|\.)phenompeople\.com$", False),
    ("eightfold", r"(^|\.)eightfold\.ai$", False),
    ("bamboohr", r"(^|\.)bamboohr\.com$", False),
    ("recruitee", r"(^|\.)recruitee\.com$", False),
    ("workable", r"(^|\.)workable\.com$", False),
    ("jobvite", r"(^|\.)jobvite\.com$", False),
    ("breezy", r"(^|\.)breezy\.hr$", False),
    ("darwinbox", r"(^|\.)darwinbox\.(in|com)$", False),
    ("keka", r"(^|\.)keka\.com$", False),
]
# Branded career domains hide the vendor: the URL query/path often still says which one
_ATS_PATH = [
    ("greenhouse", r"[?&]gh_jid=|/embed/job_app"),
    ("lever", r"/lever\.co/|[?&]lever-source"),
    ("workday", r"/job/[^/]+/[^/]+_[A-Z]?R?-?\d+"),
    ("successfactors", r"/job/[^/]+/\d+/?$|career_ns=job_listing|/sap/"),
    ("taleo", r"/careersection/|/requisition"),
]
# Open ATS where playbooks are cheapest: promote these to live first
READY_ATS = {name for name, _p, ready in _ATS_HOST if ready}

_LAUNCH_PARAMS = re.compile(r"[?&](utm_[a-z]+|fp_job|trackingId|refId|trk|lipi|eBP|origin|from)=[^&]*", re.I)


def host_of(url: str) -> str:
    """Lower-case host without 'www.'; "" when it is not an http(s) URL."""
    u = (url or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    try:
        h = (urlparse(u).hostname or "").lower()
    except ValueError:
        return ""
    h = h[4:] if h.startswith("www.") else h
    return h if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", h) else ""


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def board_of_host(host: str) -> str:
    for d, name in BOARDS.items():
        if _matches(host, d):
            return name
    return ""


def ats_of(url: str) -> str:
    """Which ATS a link belongs to ("" = unknown / the company's own system)."""
    host = host_of(url)
    for name, pat, _ready in _ATS_HOST:
        if re.search(pat, host):
            return name
    for name, pat in _ATS_PATH:
        if re.search(pat, url or "", re.I):
            return name
    return ""


def normalize_url(url: str) -> str:
    """Tracking parameters removed, so one job is one key (tracking params made duplicate-looking URLs)."""
    u = _LAUNCH_PARAMS.sub("", url or "")
    return re.sub(r"[?&]+$", "", u.replace("?&", "?")).rstrip("/")


# Board defaults when nothing else is known: these two have no company-site flow in our data
_WEAK_DEFAULT = {"Internshala": "easy", "Wellfound": "easy", "Careers": "site", "Telegram": "site"}


def _result(cls: str, signal: str, host: str = "", ats: str = "", board: str = "") -> dict[str, str]:
    return {"cls": cls, "signal": signal, "host": host, "ats": ats, "board": board}


def classify(job: dict[str, Any]) -> dict[str, str]:
    """easy / site / needs_check with the evidence. Order (strongest first):
    1. the board's own field (`apply_mode`: LinkedIn offsite/onsite link, Naukri companyApplyJob, Indeed job_url_direct)
    2. where the job link points: a company / ATS host = site
    3. the board's usual default (Internshala/Wellfound = easy, Careers/Telegram = site)
    4. needs_check"""
    source = str(job.get("source") or "")
    url = str(job.get("apply_url") or job.get("url") or "")
    blog = str(job.get("blog_url") or "")
    host = host_of(url)
    ats = ats_of(url)
    board = board_of_host(host)

    mode = job.get("apply_mode")
    if mode in ("easy", "site"):
        return _result(mode, "board_field", host, ats if mode == "site" else "", board)

    # An external link wins over the source name: Indeed/Naukri copies of a company-site job carry that link
    if host and not board and not any(_matches(host, d) for d in NOT_A_PORTAL):
        return _result("site", "url_host", host, ats, board)
    # The blog post of a Telegram job is not the portal; its resolved apply link is
    if blog and source == "Telegram":
        bh = host_of(blog)
        if bh and not board_of_host(bh) and not any(_matches(bh, d) for d in NOT_A_PORTAL):
            return _result("site", "blog_url_host", bh, ats_of(blog), "")

    default = _WEAK_DEFAULT.get(source)
    if default:
        return _result(default, "source_default", host, ats, board)
    return _result("needs_check", "unknown", host, ats, board)


def classify_page(source: str, buttons: list[dict[str, str]], text: str = "") -> dict[str, str]:
    """The decisive answer from a rendered job page (live captures, Nov 18 2026). `buttons` = [{"id", "text", "aria"}].
      Naukri    button#apply-button = on Naukri (easy), button#company-site-button / "Apply on company site" = site
      LinkedIn  button aria-label "Easy Apply to this job" = easy; "Not currently accepting applications" = closed;
                a plain "Apply" button (opens another site) = site
      Indeed    "Apply now" = easy, "Apply on company site" = site (button text; Indeed's pages sit behind Cloudflare,
                so a challenge page = needs_check, never a guess)"""
    low = (text or "")[:3000].lower()
    labels = [((b.get("text") or "") + " " + (b.get("aria") or "")).strip().lower() for b in buttons]
    ids = {(b.get("id") or "").lower() for b in buttons}
    if re.search(r"no longer accepting applications|not currently accepting applications|job (has )?expired", low):
        return _result("needs_check", "closed_page")  # closed: the caller skips it (failures.closed_posting)
    if re.search(r"verify you are human|additional verification required|just a moment", low):
        return _result("needs_check", "challenge_page")
    if source == "Naukri":
        if "company-site-button" in ids or any("apply on company site" in x for x in labels):
            return _result("site", "naukri_company_site_button")
        if "apply-button" in ids:
            return _result("easy", "naukri_apply_button")
    elif source == "LinkedIn":
        if any("easy apply" in x for x in labels):
            return _result("easy", "linkedin_easy_apply_button")
        if any(re.fullmatch(r"apply( on company (website|site))?", x) for x in labels):
            return _result("site", "linkedin_external_apply_button")
    elif source == "Internshala":
        if ids & {"top_easy_apply_button", "easy_apply_button", "mobile_easy_apply_button"}:
            return _result("easy", "internshala_easy_apply_button")
    elif source == "Wellfound":
        # the nav LINK "Applied" is the applications list, not this job's state: buttons only
        if any(re.fullmatch(r"apply( now)?", x) for x in labels):
            return _result("easy", "wellfound_apply_button")
    elif source == "Indeed":
        if any("apply on company site" in x for x in labels):
            return _result("site", "indeed_company_site_button")
        if any(re.fullmatch(r"(apply now|easily apply)", x) for x in labels):
            return _result("easy", "indeed_apply_now_button")
    return _result("needs_check", "no_apply_button")


def pipeline(job: dict[str, Any]) -> str:
    """Where the job runs: "A" (owner's Chrome, board's own apply), "B" (cloud Playwright on the company site),
    "?" (look at the page first)."""
    return {"easy": "A", "site": "B"}.get(classify(job)["cls"], "?")


def reclassify_after_landing(job: dict[str, Any], landed_url: str) -> dict[str, str] | None:
    """An "easy" attempt ended up on another site (LinkedIn/Naukri sent the owner to the company's page):
    returns the new classification (site + ATS) so the job can be handed to pipeline B, or None if it is still on
    the board / not a portal page."""
    host = host_of(landed_url)
    if not host or board_of_host(host) or any(_matches(host, d) for d in NOT_A_PORTAL):
        return None
    return _result("site", "landed_off_platform", host, ats_of(landed_url), "")
