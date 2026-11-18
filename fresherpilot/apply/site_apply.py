"""Pipeline B, all on this laptop: jobs whose apply page is a company / ATS site (not a job board) are filled by
Playwright in a real Chrome window (`scripts/apply_site.py`, one job at a time). No cloud runner.

Where jobs come from:
  * `autoapply.start()` sends approved jobs whose own link is a company / ATS page here instead of to the extension;
  * an extension attempt that LANDS on a company page (LinkedIn / Naukri "apply on company site") is handed over
    (`autoapply.handoff_to_site`).

Submit policy: Greenhouse / Lever / Ashby (`route.READY_ATS`, verified by dry runs on real forms) are submitted for
real; every other portal is filled and the window is left open for you to check and press Submit (`needs_you`)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_lock = threading.Lock()
QUEUE: list[dict[str, Any]] = []
SEEN: dict[str, float] = {}          # uid -> when it was queued (never twice within a day)
STATE: dict[str, Any] = {"running": False, "current": None, "done": 0, "applied": 0, "needs_you": 0, "failed": 0}
_worker: threading.Thread | None = None
_MAX_MINUTES = 8                     # one job's time limit (the form-filling itself; a waiting window is left alone)


def live_for(ats: str) -> bool:
    """Press the final Submit only on the portals whose flow was verified; elsewhere you press it."""
    from fresherpilot.apply import autoapply, route

    prefs = autoapply.load_prefs()
    mode = str(prefs.get("site_submit", "verified"))   # verified (default) | all | never
    return mode == "all" or (mode == "verified" and ats in route.READY_ATS)


DAILY_CAP_DEFAULT = 25   # company-site applications per day: each costs ~35-50k AI tokens (measured Nov 18), the free AI budget cannot carry more


def _within_daily_cap(uid: str) -> bool:
    """At most `site_daily_cap` (autoapply_prefs, default 25) NEW company-site jobs per calendar day (IST); counted when queued."""
    from fresherpilot.apply import autoapply
    from fresherpilot.core import users

    try:
        cap = int(autoapply.load_prefs().get("site_daily_cap", DAILY_CAP_DEFAULT))
    except (TypeError, ValueError):
        cap = DAILY_CAP_DEFAULT
    if cap <= 0:
        return True   # 0 = no cap
    path = users.path("site_budget.json")
    today = datetime.now(timezone.utc).astimezone(timezone(__import__("datetime").timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    if data.get("day") != today:
        data = {"day": today, "uids": []}
    if uid in data["uids"]:
        return True
    if len(data["uids"]) >= cap:
        return False
    data["uids"].append(uid)
    try:
        users.write_atomic(Path(path), json.dumps(data))
    except Exception:  # noqa: BLE001
        pass
    return True


def enqueue(job: dict[str, Any], url: str, why: str = "") -> str:
    """Queue one job for the local Playwright runner. Returns queued | exists."""
    from fresherpilot.apply import route
    from fresherpilot.core import users

    uid = str(job.get("uid") or f"{job.get('source')}:{job.get('id')}")
    now = time.time()
    title = str(job.get("title") or "")
    company = str(job.get("employer") or job.get("company") or "").strip()
    # Not one real opening (Nov 18: each tied a window for up to 12 minutes): a Telegram digest post ("HIRING DRIVE", "MEGA HIRING", "8 Openings",
    # emoji headlines) or a post with no company
    if not company or company.lower() in ("unknown", "n/a", "na") or re.search(r"hiring (drive|2026|2027)|mega hiring|\d+ openings?|openings!|walk-?in|[🚀🚨🔥📢]", title, re.I):
        return "skipped"
    if not _within_daily_cap(uid):
        return "capped"
    key = "k:" + re.sub(r"[^a-z0-9]+", " ", (company + " " + re.sub(r"\|.*$", "", title)).lower()).strip()   # the same posting from two feeds
    with _lock:
        if now - SEEN.get(uid, 0) < 24 * 3600 or now - SEEN.get(key, 0) < 24 * 3600:
            return "exists"
        SEEN[uid] = now
        SEEN[key] = now
        QUEUE.append({"uid": uid, "url": route.normalize_url(url), "title": job.get("title") or "",
                      "company": job.get("employer") or job.get("company") or "", "ats": route.ats_of(url), "why": why})
        global _worker
        if not (_worker and _worker.is_alive()):
            _worker = users.thread(_work)
    return "queued"


def status() -> dict[str, Any]:
    with _lock:
        return {**STATE, "queued": len(QUEUE), "queue": [{k: q[k] for k in ("uid", "title", "company", "ats")} for q in QUEUE[:20]]}


def _work() -> None:
    while True:
        with _lock:
            if not QUEUE:
                STATE.update(running=False, current=None)
                return
            item = QUEUE.pop(0)
            STATE.update(running=True, current={k: item[k] for k in ("uid", "title", "company", "ats")})
        try:
            status_, detail = _run_one(item)
        except Exception as exc:  # noqa: BLE001 — one job never stops the queue
            status_, detail = "failed", f"runner error: {str(exc)[:160]}"
        _finish(item, status_, detail)
        with _lock:
            STATE["done"] += 1
        time.sleep(2)


def _run_one(item: dict[str, Any]) -> tuple[str, str]:
    live = live_for(item["ats"])
    cmd = [sys.executable, "-u", "-m", "scripts.apply_site", "--url", item["url"], "--title", item["title"],
           "--company", item["company"], "--uid", item["uid"]] + (["--live"] if live else [])
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    result: dict[str, Any] | None = None
    got = threading.Event()
    end = time.time() + _MAX_MINUTES * 60

    def read() -> None:
        nonlocal result
        for line in proc.stdout or []:
            if line.startswith("RESULT ") and result is None:
                try:
                    result = json.loads(line[7:])
                except ValueError:
                    result = {"status": "failed", "detail": "unreadable result"}
                got.set()   # the queue moves on now; the process may stay alive (a filled form waiting for you)
        got.set()           # the process ended without a result

    threading.Thread(target=read, daemon=True).start()
    got.wait(max(1.0, end - time.time()))
    if result is None:
        try:
            proc.kill()
        except OSError:
            pass
        return "failed", f"no result within {_MAX_MINUTES} minutes (killed)"
    return str(result.get("status") or "failed"), str(result.get("detail") or "")


_OUTCOME = {"applied": "applied", "closed": "skipped", "already_applied": "skipped"}


def _finish(item: dict[str, Any], status_: str, detail: str) -> None:
    """Write the result the way the extension's results are written: log, applied mark, Telegram line."""
    from fresherpilot.apply import applicant, autoapply

    uid = item["uid"]
    event = _OUTCOME.get(status_, "failed" if status_ == "failed" else "skipped")
    label = {"applied": "company site (Playwright)", "needs_you": f"needs you: {detail}", "blocked": f"needs you (bot check): {detail}"}.get(
        status_, detail)
    autoapply._log(event, {"uid": uid, "title": item["title"], "company": item["company"]}, label, uid)
    with _lock:
        if status_ == "applied":
            STATE["applied"] += 1
        elif status_ in ("needs_you", "blocked"):
            STATE["needs_you"] += 1
        elif status_ == "failed":
            STATE["failed"] += 1
    if status_ == "applied":
        applicant.set_application(uid, "applied", note="auto-applied on the company site")
        try:
            from fresherpilot.jobs import visited
            from fresherpilot.server import _jobs_by_uids

            match = _jobs_by_uids({uid})
            if match:
                visited.mark(match, True)
        except Exception:  # noqa: BLE001
            pass
    elif event in ("skipped", "failed") and status_ not in ("needs_you", "blocked"):
        try:
            autoapply._note_outcome(event, uid, detail, {"title": item["title"], "company": item["company"]})
        except Exception:  # noqa: BLE001
            pass
    try:   # one Telegram line (through the Worker, the bot's receiver); silent if it is not reachable
        from fresherpilot.outreach import telegram_bot

        if telegram_bot._cloud() and status_ in ("applied", "needs_you", "blocked", "failed"):
            icon = {"applied": "✅", "needs_you": "✋", "blocked": "🛑", "failed": "⚠️"}[status_]
            telegram_bot._cloud_call("/api/apply/notify", {"text": f"{icon} <b>{item['company'] or item['title']}</b> ({item['ats'] or 'company site'}): "
                                                                   f"{label[:300]}"}, timeout=10)
    except Exception:  # noqa: BLE001
        pass


_mail_stop = None


def start_mailwatch() -> bool:
    """Always on while the app runs: every verification / one-time-code email in your Gmail goes to Telegram within ~20 s
    and is kept in users/<id>/otp_inbox.jsonl, where the Playwright runner takes codes from when a portal asks for one."""
    global _mail_stop
    import os

    if _mail_stop is not None:
        return True
    try:
        from fresherpilot.core import users
        from fresherpilot.outreach import messages

        pw, who = users.key("GMAIL_APP_PASSWORD"), messages.sender_address()
        if not (pw and who):
            return False
        os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"] = who, pw
        sys.path.insert(0, str(ROOT / "github_reader"))
        from applybot import mailwatch

        from fresherpilot.jobs import llm_filter

        def ai(system: str, user_text: str, schema: dict):   # borderline mails: the app's own AI keys decide
            content, _m = llm_filter._create(llm_filter._client(), [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
                                             schema=schema, name="otp_mail", models=["openai/gpt-oss-20b"], effort="low")
            return json.loads(content)

        mailwatch.AI = ai
        _mail_stop = mailwatch.start()
        return _mail_stop is not None
    except Exception as exc:  # noqa: BLE001 — the app runs fine without it
        print(f"[mail watcher] not started: {str(exc)[:100]}", flush=True)
        return False
