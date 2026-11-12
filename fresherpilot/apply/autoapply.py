"""Auto-apply brain. The clicking happens in YOUR browser, inside the FresherPilot extension, so your
existing logins are used. This module (served by main.py) does the thinking and keeps the state:

  - builds the queue (one job from its "Auto-apply" button, or your best matches for "Auto-apply all")
  - decides each next step: the extension labels every clickable element with a Vimium-style key and
    sends a snapshot; the LLM answers click <key> / fill / done / skip / needs_user
  - code-level guards (never click Follow/Save/Sign up..., confirmation detection)
  - progress, log, and the Continue / Skip / Stop commands from the app

When a site needs you (sign in, CAPTCHA, verification code, or a question your profile can't
answer), the extension pauses, brings the tab to the front, and the app asks you to finish it and
click Continue.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
def _log_path() -> Path:
    from fresherpilot.core import users

    return users.path("autoapply_log.jsonl")

STATE: dict[str, Any] = {
    "running": False, "mode": None, "queue": [], "total": 0, "index": 0,
    "applied": 0, "skipped": 0, "failed": 0, "current": None, "waiting": None,
    "log": [], "command": None, "commands": [],  # commands = clicks on the page waiting to be read (one slot lost clicks)
    # Jobs set aside because they need you (sign in, CAPTCHA, a question, a form to submit): the run goes on with
    # the next job and comes back to these when you've done it or press Continue on one. uid -> info / command.
    "parked": {}, "job_commands": {}, "final": [], "paused": False, "current_at": None,
    "run_id": None, "ext_seen": 0.0, "titles": {},
    # The run the extension has not picked up yet. The extension pulls it itself (alarm every ~30 s), so a run can be
    # started without an app page open (CLI / assistant / API), like a consumer reading a queue.
    "pending": None, "started_at": 0.0,
}
_lock = threading.Lock()

# Pacing used by the extension (seconds).
# The extension also waits for each page to be ready (loaded, no spinners, DOM/network quiet);
# these are only the short human-like pauses on top of that.
SETTINGS = {"step_delay": [0.8, 2.0], "before_submit": [1.5, 3.0], "between_jobs": [20, 40], "max_steps": 28}


# ---------------------------------------------------------------- queue

# ---------------------------------------------------------------- your choices (users/<id>/autoapply_prefs.json)
# never:   jobs auto-apply must not try again (you skipped it, it's closed / you're not eligible, or it failed twice).
#          Per job ("that JD"): its uid + description fingerprint, so a repost or the same post on another board is
#          left out too, but other openings at the same company are not.
# blocked: companies you never want auto-applied to.
# fails:   failed attempts per job (2 = never again).
NEVER_AGAIN = re.compile(r"skipped by you|applied by you|no longer accepting|not (?:currently )?accepting|"
                         r"applications? (?:are|is|have been|has been) closed|job (?:is )?closed|posting (?:is )?closed|"
                         r"not eligible|not found|expired|no longer (?:available|active|open)|position (?:has been )?filled|"
                         r"already applied", re.I)
MAX_FAILS = 2
_prefs_lock = threading.Lock()


def _prefs_path() -> Path:
    from fresherpilot.core import users

    return users.path("autoapply_prefs.json")


def load_prefs() -> dict[str, Any]:
    if not _prefs_path().exists():
        return _prefs_from_log()
    try:
        data = json.loads(_prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"never": data.get("never") or {}, "blocked": data.get("blocked") or [], "fails": data.get("fails") or {}}


def _prefs_from_log() -> dict[str, Any]:
    """First use: earlier runs' outcomes from the auto-apply log (skipped by you / closed = never again, failures counted)."""
    data: dict[str, Any] = {"never": {}, "blocked": [], "fails": {}}
    try:
        lines = _log_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        uid, detail = e.get("uid"), str(e.get("detail") or "")
        if not uid:
            continue
        if e.get("event") == "skipped" and NEVER_AGAIN.search(detail):
            data["never"][uid] = {"reason": detail[:160], "at": e.get("at"), "title": e.get("title"), "company": e.get("company"),
                                  "keys": [uid]}
        elif e.get("event") == "failed":
            data["fails"][uid] = int(data["fails"].get(uid, 0)) + 1
            if data["fails"][uid] >= MAX_FAILS:
                data["never"][uid] = {"reason": f"failed {data['fails'][uid]} times (last: {detail[:120]})", "at": e.get("at"),
                                      "title": e.get("title"), "company": e.get("company"), "keys": [uid]}
    _save_prefs(data)
    return data


def _save_prefs(data: dict[str, Any]) -> None:
    from fresherpilot.core import users

    users.write_atomic(_prefs_path(), json.dumps(data, indent=1, ensure_ascii=False))


def _company(job: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(job.get("employer") or job.get("company") or "")).strip()


def _jd_keys(job: dict[str, Any]) -> list[str]:
    """The job's id + its description fingerprint (same post on another board / reposted)."""
    from fresherpilot.jobs import visited

    ks = visited.keys(job)
    return [ks[0]] + [k for k in ks if k.startswith("ds:")]


def remember_never(uid: str, reason: str, item: dict[str, Any] | None = None) -> None:
    item = item or {}
    with _prefs_lock:
        data = load_prefs()
        data["never"][uid] = {"reason": reason[:160], "at": datetime.now(timezone.utc).isoformat(),
                              "title": item.get("title"), "company": item.get("company"), "source": item.get("source"),
                              "keys": item.get("jd_keys") or [uid]}
        data["fails"].pop(uid, None)
        _save_prefs(data)


def _note_outcome(event: str, uid: str, detail: str, item: dict[str, Any] | None) -> None:
    """After a job's final result: remember the ones auto-apply must not try again."""
    if event == "skipped" and NEVER_AGAIN.search(detail or ""):
        remember_never(uid, detail, item)
    elif event == "failed":
        with _prefs_lock:
            data = load_prefs()
            data["fails"][uid] = int(data["fails"].get(uid, 0)) + 1
            n = data["fails"][uid]
            _save_prefs(data)
        if n >= MAX_FAILS:
            remember_never(uid, f"failed {n} times (last: {detail})", item)


def set_choice(action: str, company: str = "", uid: str = "") -> dict[str, Any]:
    """block / unblock a company; allow = let a never-again job be auto-applied again; never = leave a job out."""
    with _prefs_lock:
        data = load_prefs()
        name = re.sub(r"\s+", " ", company or "").strip()
        if action == "block" and name and name.lower() not in {c.lower() for c in data["blocked"]}:
            data["blocked"].append(name)
        elif action == "unblock" and name:
            data["blocked"] = [c for c in data["blocked"] if c.lower() != name.lower()]
        elif action == "allow" and uid:
            data["never"].pop(uid, None)
            data["fails"].pop(uid, None)
        elif action == "never" and uid:
            data["never"][uid] = {"reason": "left out by you", "at": datetime.now(timezone.utc).isoformat(), "keys": [uid]}
        _save_prefs(data)
    return choices()


def choices() -> dict[str, Any]:
    data = load_prefs()
    never = [{"uid": u, **{k: v for k, v in e.items() if k != "keys"}} for u, e in data["never"].items()]
    never.sort(key=lambda e: e.get("at") or "", reverse=True)
    return {"blocked": sorted(data["blocked"], key=str.lower), "never": never}


def emailed_only() -> set[str]:
    """Jobs applied to by email but not yet on the job site (from the auto-apply log)."""
    mailed, site = set(), set()
    try:
        lines = _log_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        uid = e.get("uid")
        if not uid:
            continue
        if e.get("event") == "emailed" or (e.get("event") == "applied" and str(e.get("detail") or "").startswith("emailed")):
            mailed.add(uid)
        elif e.get("event") in ("applied", "skipped"):  # the job site was tried (applied, or closed / not possible)
            site.add(uid)
    return mailed - site


def eligible_jobs(include_with_instructions: bool = False, force: set[str] | None = None) -> list[dict[str, Any]]:
    """AI-approved jobs not applied yet, newest first. force = uids the user asked for by link: no AI verdict needed."""
    from fresherpilot.apply import applicant
    from fresherpilot.outreach import contacts
    from fresherpilot.jobs import llm_filter
    from fresherpilot.jobs.apify_jobs import load_cache
    from fresherpilot.server import _newest_first, _normalized_jobs

    apps = applicant.applications()
    email_only = emailed_only()
    prefs = load_prefs()
    never_keys = {k for e in prefs["never"].values() for k in (e.get("keys") or [])} | set(prefs["never"])
    blocked = {c.lower() for c in prefs["blocked"]}
    out = []
    for job in _normalized_jobs(load_cache()):
        if not (job.get("url") or "").startswith("http"):
            continue
        uid = f"{job.get('source')}:{job.get('id')}"
        verdict = llm_filter.cached_verdict(job) or {}
        if (verdict.get("decision") != "keep" and uid not in (force or ())) or (uid in apps and uid not in email_only):
            continue
        if verdict.get("apply_instructions") and not include_with_instructions:
            continue
        job["uid"] = uid
        job["employer"] = contacts.resolve_company(job)
        if blocked and (_company(job).lower() in blocked or str(job.get("company") or "").strip().lower() in blocked):
            continue
        if llm_filter.blocked_company(job.get("company", "")):  # the Settings blocklist
            continue
        from fresherpilot.jobs.apify_jobs import in_wanted_location
        if not in_wanted_location(job):  # e.g. "United States, Remote": can't be applied to from India
            continue
        if uid in never_keys or (never_keys and any(k in never_keys for k in _jd_keys(job))):
            continue
        job["apply_instructions"] = verdict.get("apply_instructions")
        out.append(job)
    return _easy_first(_newest_first(out))


# ---------------------------------------------------------------- special "how to apply" instructions

_FORM = re.compile(r"docs\.google\.com/forms|forms\.gle/|forms\.office\.com|typeform\.com|jotform\.com|zfrmz\.|forms\.zohopublic", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Inboxes that are never for applications (Nov 5 2026: a CV went to reasonableaccommodations@aon.com).
_NOT_FOR_CVS = re.compile(r"accommodat|accessib|disabilit|privacy|gdpr|dpo|no-?reply|donotreply|do-not-reply|grievance|fraud|"
                          r"scam|security|abuse|legal|complian|ethic|whistle|press|media|investor|billing|invoice|sales|"
                          r"support|helpdesk|feedback|unsubscribe|webmaster|postmaster|admin", re.I)
# ...and the words around the address must say to send something there
_ASKS_FOR_CV = re.compile(r"resume|\bcv\b|curriculum|apply|application|send|share|mail|email|forward|drop|submit|interested", re.I)


def _instruction_plan(job: dict[str, Any]) -> tuple[str, Any]:
    """How to apply to a job with special instructions:
    ("email", (addresses, subject))  the post asks to email the CV: the app sends it from your Gmail;
    ("form", url)                    a Google / MS / Typeform form: the extension fills it, you submit;
    ("manual", summary)              anything else (assessment, walk-in, WhatsApp...): left to you;
    ("normal", None)                 no special instructions: the usual apply flow."""
    ins = job.get("apply_instructions") or {}
    if not ins:
        return "normal", None
    text = f"{job.get('description') or ''}\n{ins.get('summary') or ''}"
    # Only addresses that are really in the post (never one the AI made up), real inboxes only
    from fresherpilot.outreach import messages

    low = text.lower()
    emails = [e.strip().lower() for e in ins.get("emails") or [] if e and e.strip().lower() in low
              and messages._email_ok(e.strip().lower()) and not _NOT_FOR_CVS.search(e.split("@")[0])
              and _ASKS_FOR_CV.search(low[max(0, low.find(e.strip().lower()) - 160): low.find(e.strip().lower()) + 80])]
    forms = [u for u in ins.get("links") or [] if _FORM.search(u or "")]
    if emails:
        return "email", (emails[:2], (ins.get("subject_line") or "").strip())
    if forms:
        url = forms[0] if forms[0].startswith("http") else f"https://{forms[0]}"
        return "form", url
    return "manual", ins.get("summary") or "special instructions"


def _send_application_emails(jobs: list[tuple[dict[str, Any], list[str], str]], finish: bool = False) -> None:
    """Email applications (the post said "send your CV to ..."): one tailored email per job, resume attached,
    sent from the user's Gmail with the outreach safety checks (placeholder filter, mailbox check, daily cap)."""
    from fresherpilot.apply import applicant
    from fresherpilot.outreach import messages

    for job, emails, subject in jobs:
        try:
            draft = applicant.application_email(job, subject)
            if applicant.has_placeholder(draft["subject"]) or applicant.has_placeholder(draft["body"][:400]):
                report("email_failed", job["uid"], f"email not sent: unfilled placeholder in '{draft['subject'][:80]}'")
                continue
            results = messages.send_emails(job, job["uid"], [{"to": e, "name": ""} for e in emails],
                                           draft["subject"], draft["body"], attach_resume=True)
            sent = [r for r in results if r.get("ok")]
            if sent:
                report("emailed", job["uid"], f"emailed {', '.join(r['to'] for r in sent)} (subject: {draft['subject'][:60]})")
            else:
                report("email_failed", job["uid"], "email not sent: " + "; ".join(str(r.get("error"))[:80] for r in results))
        except Exception as exc:  # noqa: BLE001 — one job's problem never stops the rest
            report("email_failed", job["uid"], f"email not sent: {str(exc)[:150]}")
    if finish:  # nothing ran in the browser: this run ends here
        report("finished", None)


# Easy Apply jobs go first (short in-site forms: LinkedIn Easy Apply, Naukri's own apply, Indeed Apply...), in this
# board order; company-site applications (long ATS forms) last; unknown in between. Newest first within each group.
_EASY_ORDER = {"LinkedIn": 0, "Naukri": 1, "Indeed": 2, "Internshala": 3, "Wellfound": 4}


def _easy_first(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from fresherpilot.outreach.telegram_bot import apply_mode

    def key(job: dict[str, Any]) -> tuple[int, int]:
        mode = apply_mode(job)
        group = 0 if mode == "easy" else 2 if mode == "site" else 1
        return group, _EASY_ORDER.get(str(job.get("source")), 9) if group == 0 else 0

    return sorted(jobs, key=key)  # stable: keeps newest first inside each group


# ---------------------------------------------------------------- Easy Apply or company site?
# LinkedIn shows it only on the job page (Apply button: onsite = Easy Apply, offsite = company site). Jobs read
# before Nov 5 have no tag (measured: 3 of 230 approved LinkedIn jobs). This opens each untagged one's public page
# once (~2.5 s each, LinkedIn's guest pace, free), saves the tag, and leaves out jobs that are closed or removed.
TAG: dict[str, Any] = {"running": False, "done": 0, "total": 0, "easy": 0, "site": 0, "closed": 0, "started": None,
                       "finished": None, "error": None}
_CLOSED_LI = re.compile(r"no longer accepting applications", re.I)


def tag_status() -> dict[str, Any]:
    return dict(TAG)


def start_tagging() -> dict[str, Any]:
    from fresherpilot.core import users

    if TAG["running"]:
        return tag_status()
    todo = [j for j in eligible_jobs(include_with_instructions=True) if j.get("source") == "LinkedIn" and not j.get("apply_mode")]
    TAG.update(running=bool(todo), done=0, total=len(todo), easy=0, site=0, closed=0, started=time.time(),
               finished=None if todo else time.time(), error=None)
    if todo:
        users.thread(_tag_linkedin, todo)
    return tag_status()


def _tag_linkedin(todo: list[dict[str, Any]]) -> None:
    import requests

    from fresherpilot.jobs import apify_jobs, free_boards

    session = requests.Session()
    batch: dict[str, dict[str, Any]] = {}
    try:
        for j in todo:
            try:
                r = free_boards._li_get(session, free_boards._LI_JOB.format(j["id"]))
            except free_boards.Blocked as exc:
                TAG["error"] = str(exc)
                break
            except Exception:  # noqa: BLE001 — one page's problem: next job
                r = None
            if r is None:  # 404: the job was removed
                remember_never(j["uid"], "LinkedIn: job removed", {"title": j.get("title"), "company": _company(j), "source": "LinkedIn"})
                TAG["closed"] += 1
            elif _CLOSED_LI.search(r.text):
                remember_never(j["uid"], "LinkedIn: no longer accepting applications",
                               {"title": j.get("title"), "company": _company(j), "source": "LinkedIn"})
                TAG["closed"] += 1
            else:
                mode = free_boards.li_apply_mode(r.text)
                if mode:
                    batch[j["uid"]] = {"apply_mode": mode}
                    TAG[mode] += 1
            TAG["done"] += 1
            if len(batch) >= 10:
                apify_jobs.set_fields(batch)
                batch = {}
    finally:
        apify_jobs.set_fields(batch)
        TAG.update(running=False, finished=time.time())


def preview() -> dict[str, Any]:
    """Jobs Auto-apply would do, per platform (for the platform checkboxes on the Auto-apply page)."""
    from fresherpilot.outreach.telegram_bot import apply_mode

    per: dict[str, dict[str, int]] = {}
    jobs = []
    for j in eligible_jobs(include_with_instructions=True):
        c = per.setdefault(str(j.get("source") or "Other"), {"total": 0, "easy": 0})
        c["total"] += 1
        c["easy"] += apply_mode(j) == "easy"
        jobs.append({"uid": j["uid"], "title": j.get("title"), "company": _company(j), "source": j.get("source") or "Other",
                     "found": j.get("first_seen") or "", "posted": j.get("posted") or "", "location": j.get("location") or "",
                     "mode": apply_mode(j), "url": j.get("url")})
    order = list(_EASY_ORDER) + ["Careers", "Telegram"]
    return {"platforms": [{"source": k, **v} for k, v in sorted(per.items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else 99, kv[0]))],
            "jobs": jobs, "untagged": sum(1 for x in jobs if x["source"] == "LinkedIn" and not x["mode"]), "tag": tag_status(),
            **choices()}


def start(uids: list[str] | None, max_jobs: int = 0, sources: list[str] | None = None,
          pick: list[str] | None = None, hours: float | None = None, force: list[str] | None = None) -> dict[str, Any]:
    with _lock:
        if STATE["running"]:
            raise RuntimeError("Auto-apply is already running")
    single = bool(uids)
    done_email = emailed_only()
    jobs = eligible_jobs(include_with_instructions=True, force=set(force or ()))
    if pick and not uids:  # the jobs ticked on the Auto-apply page (bulk run, Easy Apply first as usual)
        chosen = set(pick)
        jobs = [j for j in jobs if j["uid"] in chosen]
        if not jobs:
            raise RuntimeError("None of the jobs you picked can be auto-applied any more (applied, skipped or blocked).")
    if hours and not uids:  # only jobs found in the last N hours
        cutoff = datetime.now(timezone.utc).timestamp() - float(hours) * 3600

        def found(j: dict[str, Any]) -> float:
            try:
                return datetime.fromisoformat(str(j.get("first_seen") or "").replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0

        jobs = [j for j in jobs if found(j) >= cutoff]
        if not jobs:
            raise RuntimeError(f"No approved jobs found in the last {hours:g} hours that are left to apply to.")
    if sources and not uids:  # only the platforms ticked on the Auto-apply page
        wanted_src = set(sources)
        jobs = [j for j in jobs if str(j.get("source") or "Other") in wanted_src]
        if not jobs:
            raise RuntimeError("No approved jobs left on the platforms you picked.")
    if uids:
        wanted = set(uids)
        jobs = [j for j in jobs if j["uid"] in wanted]
        if not jobs:
            raise RuntimeError("That job isn't eligible (already applied, or not approved).")
    if max_jobs > 0:  # 0 = no limit: every approved job, Easy Apply ones first
        jobs = jobs[:max_jobs]
    queue, browser, emails, manual = [], [], [], []
    for j in jobs:
        item = {"uid": j["uid"], "url": j["url"], "title": j["title"], "company": j.get("employer") or j.get("company"),
                "source": j.get("source"), "jd_keys": _jd_keys(j)}
        kind, info = _instruction_plan(j)
        if kind == "email":  # apply on the job site AND send the email the post asks for
            if j["uid"] not in done_email:
                emails.append((j, info[0], info[1]))
            item["kind"] = "email+site"
            browser.append(item)
        elif kind == "form":  # fill the form the post points to; the user checks it and submits
            item.update(kind="form", url=info, review=True)
            browser.append(item)
        elif kind == "manual":  # e.g. "apply only on the official site": that's the job link; the extension
            item["note"] = str(info)[:200]  # sets the job aside in "Waiting for you" if it really needs you
            browser.append(item)
        else:  # no instructions, or one job the user asked for: the usual flow on the job page
            browser.append(item)
        queue.append(item)
    with _lock:
        STATE.update(running=True, mode="single" if single else "bulk", queue=queue, total=len(queue), index=0,
                     applied=0, skipped=0, failed=0, current=None, waiting=None, command=None, commands=[], parked={}, job_commands={},
                     final=[], paused=False, current_at=None, run_id=uuid.uuid4().hex[:12], ext_seen=time.time())
        STATE["titles"].update({q["uid"]: {"title": q.get("title"), "company": q.get("company")} for q in queue})
    _log("start", None, f"{len(queue)} job(s) queued ({'this job' if single else 'Easy Apply first, then newest'}): "
                        f"{len(browser)} in the browser, {len(emails)} by email, {len(manual)} need you")
    for item, summary in manual:
        report("skipped", item["uid"], f"needs you: {summary[:140]}")
    if emails:
        from fresherpilot.core import users

        users.thread(_send_application_emails, emails, False)  # the browser queue always has these jobs too  # runs as this user (keys, Gmail, profile)
    elif not browser:
        report("finished", None)
    payload = {"queue": browser, "settings": SETTINGS, "mode": STATE["mode"], "run_id": STATE["run_id"]}
    with _lock:
        STATE["pending"], STATE["started_at"] = payload, time.time()
    return payload


def _log(event: str, job: dict[str, Any] | None, detail: str = "", uid: str | None = None) -> None:
    uid = (job or {}).get("uid") or uid
    known = STATE["titles"].get(uid or "", {})
    entry = {"at": datetime.now(timezone.utc).isoformat(), "event": event, "detail": detail, "uid": uid,
             "title": (job or {}).get("title") or known.get("title"), "company": (job or {}).get("company") or known.get("company")}
    with _lock:
        STATE["log"] = (STATE["log"] + [entry])[-200:]
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def report(event: str, uid: str | None, detail: str = "", waiting: dict[str, Any] | None = None,
           run: str | None = None) -> dict[str, Any]:
    """Progress from the extension: job_start / applied / skipped / failed / waiting / resumed / finished.
    run = the extension's run id: events of an older run (still going in the browser after the app restarted or a
    new Start) are ignored, so they never mix with this run's counts."""
    from fresherpilot.apply import applicant

    if run:
        with _lock:
            STATE["ext_seen"] = time.time()
            stale = run != STATE.get("run_id")
            if not stale:
                STATE["pending"] = None  # the extension has it (handed over by the page or pulled)
        if stale:
            return {"stale": True}
    job = next((q for q in STATE["queue"] if q["uid"] == uid), None) if uid else None
    with _lock:
        repeat = event in ("applied", "skipped", "failed") and bool(uid) and uid in STATE["final"]
        if event in ("applied", "skipped", "failed") and uid and not repeat:
            STATE["final"].append(uid)
    if repeat:  # already recorded (e.g. you pressed "I applied" before the extension reported): count each job once
        return status()
    with _lock:
        if event == "job_start" and job:
            STATE["current"] = job
            STATE["current_at"] = datetime.now(timezone.utc).isoformat()
            STATE["index"] = STATE["queue"].index(job) + 1
            STATE["waiting"] = None
        elif event in ("applied", "skipped", "failed"):
            STATE[event] += 1
            STATE["waiting"] = None
        elif event == "waiting":
            STATE["waiting"] = waiting or {"reason": detail}
        elif event == "resumed":
            STATE["waiting"] = None
        elif event == "parked" and uid:
            STATE["parked"][uid] = {**(waiting or {"reason": detail}), "uid": uid,
                                    "title": (job or {}).get("title") or (waiting or {}).get("title") or STATE["titles"].get(uid, {}).get("title"),
                                    "company": (job or {}).get("company") or STATE["titles"].get(uid, {}).get("company"),
                                    "url": (job or {}).get("url"),
                                    "at": datetime.now(timezone.utc).isoformat()}
            STATE["waiting"] = None
        elif event == "finished":
            STATE.update(running=False, current=None, waiting=None, command=None, commands=[], paused=False, current_at=None, pending=None)
        if event in ("applied", "skipped", "failed") and uid:
            STATE["parked"].pop(uid, None)
            STATE["job_commands"].pop(uid, None)
    if event in ("skipped", "failed") and uid:
        try:
            _note_outcome(event, uid, detail, job)
        except Exception:  # noqa: BLE001 — never let bookkeeping break a run
            pass
    if event in ("applied", "emailed") and uid:
        applicant.set_application(uid, "applied", note="auto-applied" if event == "applied" else "emailed")
        from fresherpilot.jobs import visited
        from fresherpilot.jobs.apify_jobs import load_cache
        from fresherpilot.server import _normalized_jobs

        match = [j for j in _normalized_jobs(load_cache()) if f"{j.get('source')}:{j.get('id')}" == uid]
        if match:
            visited.mark(match, True)
    if event != "job_start" or detail:
        _log(event, job, detail, uid)
    return status()


def command(action: str, uid: str | None = None) -> None:
    """From the Auto-apply page. Run: stop / pause / resume / skip (the current job) / applied (you applied the current
    job yourself) / continue (single-job mode). One set-aside job (uid): open / continue / skip / applied.
    Skip and "I applied" are recorded here at once (the counts and the list change immediately); the extension
    closes the tab within ~2 s."""
    with _lock:
        cur = (STATE.get("current") or {}).get("uid")
        if action in ("pause", "resume"):
            STATE["paused"] = action == "pause"
    if uid:
        if action == "applied":
            report("applied", uid, "applied by you")
        elif action == "skip":
            report("skipped", uid, "skipped by you")
        with _lock:  # after the report (which clears old commands): the extension reads it and tidies up the tab
            STATE["job_commands"][uid] = action
        return
    with _lock:
        STATE["commands"] = [c for c in STATE["commands"] if c != action]  # a click twice = once
        if action == "stop":
            STATE["commands"] = []  # nothing else matters any more
        STATE["commands"].append(action)
    if action in ("applied", "skip") and cur and STATE.get("mode") != "single":
        report("applied" if action == "applied" else "skipped", cur, "applied by you" if action == "applied" else "skipped by you")


def take_command(uid: str | None = None, run: str | None = None, accept: list[str] | None = None) -> str | None:
    """Next click for one reader. accept = the commands this reader handles: the others stay for their own reader
    (before, the Continue click of one poller could be eaten by another that ignored it, and a second click
    overwrote the first)."""
    with _lock:
        if run:
            if run != STATE.get("run_id"):
                return "stop"  # an old run still going in the browser: end it
            STATE["ext_seen"] = time.time()
        if uid:
            return STATE["job_commands"].pop(uid, None)
        for i, c in enumerate(STATE["commands"]):
            if accept is None or c in accept:
                return STATE["commands"].pop(i)
        return None


def take_pending() -> dict[str, Any] | None:
    """The extension asks for work. A started run nobody picked up yet is handed over once."""
    with _lock:
        p = STATE.get("pending")
        if not (STATE["running"] and p):
            return None
        STATE["pending"] = None
        STATE["ext_seen"] = time.time()
        return p


NOBODY_PICKED_UP_S = 150   # a run no browser picked up: Chrome closed / extension missing -> end it, don't hang
GONE_SILENT_S = 600        # the extension stopped checking in during a run (it polls every 2 s) -> end it


def watchdog() -> None:
    """Ends runs that can never finish by themselves (they showed "running" forever before: Nov 6 2026)."""
    now = time.time()
    with _lock:
        if not STATE["running"]:
            return
        never = STATE.get("pending") is not None and now - (STATE.get("started_at") or now) > NOBODY_PICKED_UP_S
        silent = STATE.get("pending") is None and STATE.get("ext_seen") and now - STATE["ext_seen"] > GONE_SILENT_S             and not STATE["paused"]
    if never:
        STATE["pending"] = None
        _log("finished", None, f"no browser picked this run up within {NOBODY_PICKED_UP_S} s: open Chrome with the FresherPilot extension, then Start again")
        report("finished", None)
    elif silent:
        _log("finished", None, "the extension stopped answering: run ended (press Start to run again)")
        report("finished", None)


def status() -> dict[str, Any]:
    watchdog()
    with _lock:
        nxt = [{k: q.get(k) for k in ("uid", "title", "company", "source", "kind")} for q in STATE["queue"][STATE["index"]:STATE["index"] + 8]]
        seen = STATE.get("ext_seen") or 0
        return ({k: v for k, v in STATE.items() if k not in ("log", "queue", "parked", "job_commands", "final", "titles", "ext_seen", "pending", "started_at")}
                | {"log": STATE["log"][-200:], "parked": list(STATE["parked"].values()), "next": nxt,
                   "waiting_for_browser": STATE.get("pending") is not None and STATE["running"],
                   "ext_seen_s": round(time.time() - seen) if seen else None})


def reset() -> dict[str, Any]:
    """The page's "Reset": the extension stopped answering (reloaded / browser closed). Ends this run in the app;
    a run still going in the browser is told to stop the next time it checks in."""
    with _lock:
        STATE.update(running=False, current=None, waiting=None, command=None, commands=[], paused=False, current_at=None,
                     run_id=None, parked={}, job_commands={}, pending=None)
    _log("finished", None, "reset from the Auto-apply page")
    return status()


# ---------------------------------------------------------------- deciding the next step

NAV_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["click", "fill", "done", "skip", "needs_user"]},
        "key": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["action", "key", "reason"],
    "additionalProperties": False,
}

NAV_PROMPT = """You drive a browser to submit ONE job application, either through the job board's quick-apply flow
(LinkedIn "Easy Apply", Naukri "Apply", Indeed "Apply now", Wellfound) or, when the job only offers
"Apply on company site", through the company's own careers page / applicant tracking system (Greenhouse, Lever,
Workday, Ashby...). The candidate is logged in to the job boards in this browser.
Each step you see the page URL and title, the visible text (of the open dialog if there is one), how many form
fields are visible and empty, the filler status, previous actions, and clickable elements with hint keys.
Reply with ONE action:

- fill       : application form fields are visible and the filler has NOT run on this step yet.
- click      : press the element with that key to move the application forward (elements marked "further down
               the page" are fine; clicking scrolls to them): Easy Apply / Apply / Apply now /
               Apply on company site / Apply for this job / I'm interested, Next, Continue, Save and continue,
               Review, Submit application / Submit. Prefer elements inside the dialog. On a careers page, open
               THIS job's application (not other openings). Accepting necessary cookies is fine.
- done       : the page clearly confirms the application was submitted / sent / applied.
- needs_user : the candidate must act: sign in / log in page, create an account, CAPTCHA, email/OTP/phone code,
               or a question that can't be answered from their profile. Say exactly what they need to do.
- skip       : the job is closed / no longer accepting applications / already applied, or the flow needs something
               that can't be done (video interview, live test). Give the reason.

Never click: Save (job), Follow, Share, Message, Dismiss, Discard, Cancel, Back, Sign in / Log in / Create account /
Sign up (ask the candidate instead), social login buttons, ads, other job listings, premium/upsell, profile/settings
links, cookie "reject"/settings. key is "" unless action is click."""

CONFIRMED = re.compile(
    r"application (has been |was )?(successfully )?(submitted|sent|received)|thank(s| you) for (applying|your application)|"
    r"successfully applied|you('ve| have) (successfully )?applied|we('ve| have) received your application|your application was sent",
    re.I,
)
NEVER_CLICK = re.compile(
    r"^\s*save\s*(job)?\s*$|^undo|follow|share|message|dismiss|discard|cancel|premium|sign ?(out|in|up)|log ?(out|in)|"
    r"create (an )?account|register|continue with (google|linkedin|facebook|apple)",
    re.I,
)
# Buttons that only move an application forward (used for the no-AI shortcut).
FORWARD = re.compile(
    r"^(next|continue|continue to next step|save and continue|review|review (your )?application|"
    r"submit|submit (your )?application|send application)$",
    re.I,
)
# Links that leave the application (opening them loses the form).
LEAVES_FORM = re.compile(r"terms|privacy|legal|policy|cookie|help|faq|support|about|blog|learn more|guidelines", re.I)
BLOCK_TEXT = re.compile(r"captcha|verify you are (a )?human|are you a robot|security check|unusual activity", re.I)
LOGIN_URL = re.compile(r"/login|/authwall|nlogin|secure\.indeed\.com/auth|/signin|/sign-in|/register|/signup|accounts\.google", re.I)


ALREADY_BTN = re.compile(r"^(?:✓\s*)?(?:already\s+)?applied(?:\s*✓)?(?:\s+\d+\s*\w+\s+ago|\s+on\s+.{1,15})?$"
                         r"|^application\s+(?:already\s+)?(?:sent|submitted)$", re.I)
ALREADY_TEXT = re.compile(r"you(?:'ve| have) already applied|already applied (?:to|for) this|you applied \d+\s*\w+ ago|"
                          r"applied on \d{1,2}[ /-]\w{2,9}|application (?:already )?(?:sent|submitted) on|"
                          r"\bapplied\s+\d+\s*(?:minute|hour|day|week|month)s? ago", re.I)


# The apply button on a job page, by board (aria-label or text). Only a button is ever matched (never a link),
# and only when exactly one matches: two candidates = unusual page = the AI decides.
_APPLY_BUTTON = {
    "LinkedIn": re.compile(r"^easy apply( to this job)?$", re.I),
    "Naukri": re.compile(r"^apply$", re.I),
    "Indeed": re.compile(r"^(apply now|easily apply|apply)$", re.I),
    "Wellfound": re.compile(r"^(apply|apply now|apply to .{2,60})$", re.I),
    "Internshala": re.compile(r"^(apply now|apply)$", re.I),
}
_FORWARD_RANK = [  # when a step offers several forward buttons, the furthest one first
    re.compile(r"^(submit|submit (your )?application|send application)$", re.I),
    re.compile(r"^review( (your )?application)?$", re.I),
    re.compile(r"^(next|continue|continue to next step|save and continue)$", re.I),
]
_SENT = re.compile(r"application sent|applied successfully|successfully applied|your application (has been |was )?sent|"
                   r"you('ve| have) applied", re.I)


def _label(it: dict[str, Any]) -> str:
    return (it.get("text") or it.get("label") or "").strip()


def _playbook(snap: dict[str, Any], items: list[dict[str, Any]], filled: bool, submitted: bool, source: str,
              history: list[str] | None = None) -> dict[str, Any] | None:
    full = snap.get("full_text", "")
    dialog = bool(snap.get("dialog"))
    if submitted and _SENT.search(snap.get("text", "") + " " + full[:3000]):
        return {"action": "done", "key": "", "reason": "playbook: application sent shown"}
    # Wellfound holds a sent application for a few minutes with an "Undo · 4:29" button (and may pop an optional
    # "Share my AI interview" window): the Undo button IS the confirmation (Nov 12 live test). Never click it.
    if submitted and any(re.match(r"^undo", _label(it), re.I) for it in items):
        return {"action": "done", "key": "", "reason": "playbook: Wellfound shows Undo = application sent"}
    # ...and once Send was clicked and the Send button is gone, the application is in (a follow-up "Share my AI interview" window may remain)
    if submitted and source == "Wellfound" and not any(re.match(r"^send application$", _label(it), re.I) for it in items):
        return {"action": "done", "key": "", "reason": "playbook: Wellfound Send application clicked and the form is gone"}
    # Naukri: the recruiter question was answered and Saved, the drawer is gone: Naukri now shows "Applied" (live test Nov 12)
    if source == "Naukri" and not dialog and history and "Naukri Save" in str(history[-1]):
        return {"action": "done", "key": "", "reason": "playbook: Naukri question answered and saved"}
    if not dialog and not submitted:
        pat = _APPLY_BUTTON.get(source)
        if pat:
            hits = [it for it in items if it.get("tag") == "button" and (pat.match(_label(it)) or pat.match((it.get("label") or "").strip()))]
            labels = [_label(it) for it in items if it.get("tag") != "a"]
            # a company-site flow, or two apply buttons, is not the quick-apply template: let the AI look
            # Wellfound shows the same apply action twice (header "Apply" + body "Apply now"): the first one is fine
            if (len(hits) == 1 or (source == "Wellfound" and 1 < len(hits) <= 3)) and not any(re.search(r"company site|apply on", x, re.I) for x in labels):
                return {"action": "click", "key": hits[0]["key"], "reason": f"playbook: {source} apply button", "is_submit": False}
    # Indeed's apply flow is its own page (smartapply.indeed.com): contact -> resume -> questions -> review, each with
    # one Continue / Submit button (the AI skipped the Submit on the review page twice: Nov 12 test).
    if not dialog and "smartapply.indeed.com" in snap.get("url", "") and not submitted:
        if snap.get("empty_fields") and not filled:
            return {"action": "fill", "key": "", "reason": "playbook: Indeed form fields"}
        btns = [it for it in items if it.get("tag") == "button"]
        for rank in _FORWARD_RANK:
            hit = [it for it in btns if rank.match(_label(it))]
            if len(hit) == 1:
                label = _label(hit[0])
                return {"action": "click", "key": hit[0]["key"], "reason": f"playbook: Indeed {label[:30]}",
                        "is_submit": bool(re.search(r"submit", label, re.I))}
    if dialog:
        inside = [it for it in items if it.get("in_dialog") and it.get("tag") != "a"]
        # Naukri's recruiter questions (side drawer): radio options are labels, then a Save button. Answer the
        # affirmative option ("Yes", "Yes - Interested"...), press Save, repeat for the next question. Anything that is
        # not a plain choice (free text, "No" only...) stays with the AI / you.
        if source == "Naukri":
            opts = [it for it in inside if it.get("tag") == "label"]
            save = [it for it in inside if re.match(r"^save$", _label(it), re.I)]
            last = str((history or [""])[-1])
            if save and "Naukri option" in last:
                return {"action": "click", "key": save[0]["key"], "reason": "playbook: Naukri Save", "is_submit": False}
            if opts and "Naukri option" not in last:
                yes = [o for o in opts if re.match(r"^\s*(yes|interested|i am|i have|available)", _label(o), re.I)]
                if yes:
                    return {"action": "click", "key": yes[0]["key"], "reason": f"playbook: Naukri option {_label(yes[0])[:20]}", "is_submit": False}
        if snap.get("fields") and not filled:
            return {"action": "fill", "key": "", "reason": "playbook: form fields in the dialog"}
        if filled or not snap.get("fields"):
            for rank in _FORWARD_RANK:
                hit = [it for it in inside if rank.match(_label(it))]
                if len(hit) == 1:
                    label = _label(hit[0])
                    return {"action": "click", "key": hit[0]["key"], "reason": f"playbook: {label[:30]}",
                            "is_submit": bool(re.search(r"submit|send application", label, re.I))}
            # LinkedIn's last screen: "Application sent" + a Done button
            if submitted:
                done = [it for it in inside if re.match(r"^(done|close)$", _label(it), re.I)]
                if done and _SENT.search(snap.get("text", "")):
                    return {"action": "done", "key": "", "reason": "playbook: application sent"}
    return None


def decide(body: dict[str, Any]) -> dict[str, Any]:
    """Next action for the extension, from a page snapshot. Every step is written to autoapply_steps.jsonl."""
    began = time.time()
    out = _decide(body)
    try:
        from fresherpilot.core import users

        path = users.path("autoapply_steps.jsonl")
        if path.exists() and path.stat().st_size > 5_000_000:
            path.write_text("", encoding="utf-8")
        snap = body.get("snapshot") or {}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "uid": (body.get("job") or {}).get("uid"),
                                "url": (snap.get("url") or "")[:200], "action": out.get("action"), "key": out.get("key"),
                                "reason": (out.get("reason") or "")[:200], "items": len(snap.get("items") or []),
                                "filled": bool(body.get("filled")), "s": round(time.time() - began, 1),
                                "dialog": bool(snap.get("dialog")), "fields": snap.get("fields"),
                                "dlg": [(i.get("key"), (i.get("text") or i.get("label") or "")[:25], i.get("tag")) for i in (snap.get("items") or []) if i.get("in_dialog")][:14]}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — logging never breaks a run
        pass
    return out


def _decide(body: dict[str, Any]) -> dict[str, Any]:
    """Next action for the extension, from a page snapshot."""
    from fresherpilot.jobs import llm_filter

    snap = body.get("snapshot") or {}
    url, text = snap.get("url", ""), snap.get("text", "")
    full = snap.get("full_text", text)
    filled, submitted = bool(body.get("filled")), bool(body.get("submitted"))
    history = body.get("history") or []

    # Code-level checks first (cheap and reliable).
    if submitted and CONFIRMED.search(full):
        return {"action": "done", "key": "", "reason": "confirmation shown after submit"}
    # The extension detects real challenges (visible CAPTCHA widgets / "verify you are human"), not just
    # the word "captcha", which many normal pages show in their footer.
    if snap.get("blocked") == "challenge":
        return {"action": "needs_user", "key": "", "reason": "Solve the security check (CAPTCHA) in the tab"}
    if snap.get("blocked") == "login" or LOGIN_URL.search(url):
        return {"action": "needs_user", "key": "", "reason": "Sign in on this site in the opened tab"}

    items = snap.get("items") or []

    # No progress: the same action repeated again and again (a disabled Send button, a US-only job...) ends the job
    # instead of looping until the time limit.
    last = [str(h) for h in history[-6:]]
    ai_loop = len(last) >= 4 and len(set(last[-4:])) == 1 and "playbook" not in last[-1]
    if ai_loop or (len(last) >= 6 and len(set(last)) == 1):
        return {"action": "skip", "key": "", "reason": "no progress: the same step repeated and nothing changed (button disabled or not applicable)"}

    # After our own Submit click, a board that now shows "Already applied" / "Applied" confirms it (Internshala has no
    # confirmation text: Nov 12 the application went through but was logged as skipped).
    if submitted and any(ALREADY_BTN.match((it.get("text") or it.get("label") or "").strip()) for it in items if it.get("tag") != "a"):
        return {"action": "done", "key": "", "reason": "button now says Applied after submit"}

    # Already applied (Internshala shows an "Applied" button / "already applied", LinkedIn "Applied X ago",
    # Naukri "Applied"): done, no AI call. Before any submit only, so our own confirmation isn't mistaken for it.
    if not submitted and not filled:
        # buttons only: a sidebar LINK "Applied" (Wellfound's nav) is the list of your applications, not this job's state
        labels = [(it.get("text") or it.get("label") or "").strip() for it in items if it.get("tag") != "a"]
        if any(ALREADY_BTN.match(x) for x in labels) or ALREADY_TEXT.search(full) or snap.get("already"):
            return {"action": "skip", "key": "", "reason": "already applied to this job earlier"}

    # Site playbooks (Nov 12): these boards' quick-apply flows are fixed templates, so the usual steps need no AI
    # call (each one cost ~2-15 s). Anything unusual still falls through to the AI below.
    quick = _playbook(snap, items, filled, submitted, (body.get("job") or {}).get("source", ""), history)
    if quick:
        return quick

    # Obvious step, no AI call: inside a dialog, nothing left to fill, and exactly one forward button.
    if snap.get("dialog") and (filled or not snap.get("fields")):
        forward = [it for it in items if it.get("in_dialog") and it.get("tag") != "a"
                   and FORWARD.match((it.get("text") or it.get("label") or "").strip())]
        if len(forward) == 1:
            label = forward[0].get("text") or forward[0].get("label") or ""
            return {"action": "click", "key": forward[0]["key"], "reason": f"only forward button: {label[:30]}",
                    "is_submit": bool(re.search(r"submit|send application|finish", label, re.I))}
    # With a dialog open, the application lives in it: send its elements plus a few page buttons.
    if snap.get("dialog"):
        inside = [it for it in items if it.get("in_dialog")]
        outside = [it for it in items if not it.get("in_dialog") and it.get("tag") != "a"][:8]
        items = inside + outside if inside else items[:60]
    else:
        items = items[:70]
    listing = "\n".join(
        f"{it['key']} {'L' if it.get('tag') == 'a' else 'B'}{'d' if it.get('in_dialog') else ''}{'v' if it.get('below') else ''} "
        f"{(it.get('text') or it.get('label'))[:60]}"
        + (f" ({it['label'][:40]})" if it.get("label") and it.get("label") != it.get("text") else "")
        for it in items
    )
    job = body.get("job") or {}
    user = (
        f"JOB: {job.get('title')} at {job.get('company')} ({job.get('source')})\nURL: {url}\nTITLE: {snap.get('title')}\n"
        f"Dialog open: {snap.get('dialog')}. Visible form fields: {snap.get('fields')} (empty text fields: {snap.get('empty_fields')}).\n"
        + ("FILLER STATUS: the form on this step is ALREADY FILLED and all required fields have values. Do NOT answer "
           "'fill'; press Next / Continue / Review / Submit (or 'done' if submitted).\n" if filled
           else "FILLER STATUS: not run on this step yet.\n")
        + f"Previous: {'; '.join(history[-4:]) or 'none'}\n\nTEXT:\n{text[:1300]}\n\nCLICKABLE (key, B=button L=link, d=in dialog, v=further down):\n{listing}"
    )
    messages = [{"role": "system", "content": NAV_PROMPT}, {"role": "user", "content": user}]
    client = llm_filter._client()
    for _attempt in range(3):
        # Picking a button is easy: small model, low effort first; keeps the big model's quota for job checks.
        content, _model = llm_filter._create(client, messages, schema=NAV_SCHEMA, name="next_action",
                                             models=["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"], effort="low")
        decision = json.loads(content)
        if decision["action"] != "click":
            break
        item = next((it for it in items if it["key"] == decision.get("key")), None)
        if not item:
            problem = f"'{decision.get('key')}' is not in the list."
        else:
            label = f"{item.get('text', '')} {item.get('label', '')}"
            if NEVER_CLICK.search(label) and re.search(r"sign ?(in|up)|log ?in|create (an )?account|register", label, re.I):
                return {"action": "needs_user", "key": "", "reason": "This site needs you to sign in / create an account"}
            if NEVER_CLICK.search(label) or (item.get("tag") == "a" and LEAVES_FORM.search(label)):
                problem = f"'{label.strip()[:50]}' ({item['key']}) leaves or derails the application; it is not allowed."
            else:
                decision["is_submit"] = bool(re.search(r"submit|send application|finish", label, re.I))
                return decision
        # Ask again with the problem explained (the Submit button may be further down the list).
        messages += [{"role": "assistant", "content": content},
                     {"role": "user", "content": f"{problem} Choose a different element that moves the application forward "
                                                 "(Next / Continue / Review / Submit, possibly further down the page), or another action."}]
    else:
        return {"action": "skip", "key": "", "reason": "couldn't find a safe button to press"}
    if decision["action"] == "skip" and submitted and CONFIRMED.search(full):
        return {"action": "done", "key": "", "reason": "confirmation shown after submit"}
    return decision
