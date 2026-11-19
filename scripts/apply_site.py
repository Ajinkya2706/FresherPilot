"""Apply to ONE company-career-site job, here on this laptop (no cloud runner): a real Chrome window, the same engine the
cloud runner uses (github_reader/applybot), local AI keys, local account list.

    python -m scripts.apply_site --url <apply link> --title "<title>" --company "<company>" [--uid UID] [--live]
                                 [--keep 15]

Without --live it fills everything and stops before the final Submit (the window stays open `--keep` minutes so you can
read it and press Submit yourself). With --live the final Submit is pressed. The last stdout line is
`RESULT {"status": ..., "detail": ...}` (applied | needs_you | blocked | closed | already_applied | failed | skipped).
Verification codes: Gmail first (GMAIL_APP_PASSWORD in .env), else asked on Telegram through the Worker (Telegram
allows one receiver, the Worker); nothing else touches the cloud."""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "github_reader"))


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")


def _user_dir() -> Path:
    d = next((Path(p).parent for p in glob.glob(str(ROOT / "users" / "*" / "applicant_profile.json"))), None)
    if not d:
        raise SystemExit("No applicant_profile.json found (finish the profile in the app first)")
    return d


def local_ai(system: str, user: str, schema: dict):
    """The app's own AI keys (.env GROQ_API_KEY.. / NVIDIA_API_KEY..) instead of the Worker's."""
    from fresherpilot.jobs import llm_filter

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content, _model = llm_filter._create(llm_filter._client(), messages, schema=schema, name="apply_fields",
                                         models=["openai/gpt-oss-120b", "openai/gpt-oss-20b"], effort="low")
    return json.loads(content).get("r")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--company", default="")
    ap.add_argument("--uid", default="")
    ap.add_argument("--live", action="store_true", help="press the final Submit (default: fill only)")
    ap.add_argument("--keep", type=float, default=15.0, help="minutes the window stays open when it needs you")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--recover-first", action="store_true", help="the portal account exists but its password is unknown: reset it by email first (user name = your email)")
    a = ap.parse_args()
    _load_env()
    if a.recover_first:
        os.environ["APPLYBOT_RECOVER_FIRST"] = "1"
    ud = _user_dir()
    profile = json.loads((ud / "applicant_profile.json").read_text(encoding="utf-8"))
    os.environ.setdefault("GMAIL_USER", profile["personal"]["email"])
    resume = next(iter(sorted(glob.glob(str(ud / "*Resume.pdf")))), "")
    if not resume:
        print('RESULT ' + json.dumps({"status": "failed", "detail": "no resume PDF in the user folder"}))
        return 1

    try:   # the resume text is part of the facts the AI decides from (skills, projects, dates)
        from pypdf import PdfReader

        profile["resume_text"] = chr(10).join(pg.extract_text() or "" for pg in PdfReader(resume).pages)[:5000]
    except Exception:  # noqa: BLE001
        pass
    from applybot import brain, cloud

    brain.MEM_DIR = ud / "site_memory"

    accounts_file = ud / "site_accounts.json"
    try:
        accounts = json.loads(accounts_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        accounts = []

    def account(domain: str, email: str) -> None:   # local list instead of the Worker's table
        if domain not in accounts:
            accounts.append(domain)
            accounts_file.write_text(json.dumps(accounts), encoding="utf-8")

    cloud.ai = local_ai
    cloud.alive = lambda job_id: None
    cloud.account = account
    # verification codes keep using cloud.otp_request / otp_wait (Gmail first in the engine, Telegram via the Worker)

    from playwright.sync_api import sync_playwright

    from applybot.engine import Run

    job = {"id": 0, "url": a.url, "title": a.title, "company": a.company, "uid": a.uid}
    with sync_playwright() as p:
        try:   # the real Chrome (visible): far fewer bot challenges than the bundled headless Chromium
            browser = p.chromium.launch(channel="chrome", headless=a.headless, args=["--disable-blink-features=AutomationControlled"],
                                        ignore_default_args=["--enable-automation"])
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(headless=a.headless, args=["--disable-blink-features=AutomationControlled"])
        # Saved login per portal (cookies after a successful sign-in + MFA): the next run for the same portal is already signed in,
        # so no new sign-in, no new code e-mail (owner, Nov 18: repeated logins / codes are a lock-out risk)
        from urllib.parse import urlparse

        host = (urlparse(a.url).hostname or "site").removeprefix("www.")
        sess_dir = ud / "site_sessions"
        sess_dir.mkdir(exist_ok=True)
        sess_file = sess_dir / f"{host}.json"
        state = str(sess_file) if sess_file.exists() and time.time() - sess_file.stat().st_mtime < 12 * 3600 else None
        ctx = browser.new_context(viewport={"width": 1366, "height": 850}, locale="en-IN", timezone_id="Asia/Kolkata", storage_state=state)
        if state:
            print("using the saved login for " + host, flush=True)
        # Career sites ask "allow location access?" (Micron...): the page freezes behind Chrome's prompt. Allow it with the coordinates of the
        # candidate's OWN city (profile), so nothing waits for a click.
        try:
            geo = {"pune": (18.5204, 73.8567), "mumbai": (19.0760, 72.8777), "bengaluru": (12.9716, 77.5946), "bangalore": (12.9716, 77.5946), "hyderabad": (17.3850, 78.4867)}
            c = geo.get(str((profile.get("personal") or {}).get("city") or "").strip().lower())
            if c:
                ctx.set_geolocation({"latitude": c[0], "longitude": c[1], "accuracy": 50})
                ctx.grant_permissions(["geolocation"])
        except Exception:  # noqa: BLE001
            pass

        def save_session() -> None:
            try:
                ctx.storage_state(path=str(sess_file))
            except Exception:  # noqa: BLE001
                pass
        ctx.set_default_timeout(15000)
        try:
            shots = ud / "site_shots"
            shots.mkdir(exist_ok=True)
            os.environ["APPLYBOT_SHOT"] = str(shots / (re.sub(r"[^A-Za-z0-9_-]+", "_", a.uid or "job") + ".png"))
        except Exception:  # noqa: BLE001
            pass
        run = Run(ctx, job, profile, accounts, resume, not a.live)
        status, detail = "failed", "runner error"
        try:
            status, detail = run.run()
        except Exception as exc:  # noqa: BLE001
            detail = f"runner error: {str(exc)[:200]}"
        save_session()
        print("RESULT " + json.dumps({"status": status, "detail": detail[:500], "steps": run.steps[-12:]}), flush=True)
        if status not in ("applied", "already_applied"):   # evidence for every run that did not finish: what the page looked like + the last steps
            try:
                import shutil
                from datetime import datetime
                from fresherpilot.apply import failures as _fl
                fdir = ud / "failures" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + re.sub(r"[^A-Za-z0-9_-]+", "_", a.uid or "job")[:60])
                fdir.mkdir(parents=True, exist_ok=True)
                shot = os.environ.get("APPLYBOT_SHOT")
                if shot and os.path.exists(shot):
                    shutil.copy(shot, fdir / "page.png")
                (fdir / "meta.json").write_text(json.dumps({
                    "uid": a.uid, "url": a.url, "status": status, "code": _fl.classify(detail, status), "detail": detail[:500],
                    "steps": run.steps[-25:], "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        # Stay alive in the SAME window and take instructions: users/<id>/site_cmd/<uid>.json = {"answers": {"Employer": "..."}, "cmd": "continue"}.
        # Continuing re-enters the loop from the page that is open (no new sign-in, no new code mail).
        cmd_dir = ud / "site_cmd"
        cmd_dir.mkdir(exist_ok=True)
        cmd_file = cmd_dir / ((a.uid.replace(":", "_") or "job") + ".json")
        end_wait = time.time() + a.keep * 60
        while status in ("needs_you", "blocked") and not a.headless and time.time() < end_wait:
            try:
                if all(pg.is_closed() for pg in ctx.pages):   # the window was closed
                    break
                if cmd_file.exists():
                    cmd = json.loads(cmd_file.read_text(encoding="utf-8"))
                    cmd_file.unlink()
                    for lab, val in (cmd.get("answers") or {}).items():
                        profile.setdefault("custom_answers", {})[lab] = val
                    print("continuing in the open window", flush=True)
                    status, detail = run.run(resume=True)
                    save_session()
                    print("RESULT " + json.dumps({"status": status, "detail": detail[:500], "steps": run.steps[-12:]}), flush=True)
                    end_wait = time.time() + a.keep * 60
                run.page.wait_for_timeout(1500) if not run.page.is_closed() else time.sleep(1.5)
            except Exception:  # noqa: BLE001
                break
        try:
            ctx.close()
            browser.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
