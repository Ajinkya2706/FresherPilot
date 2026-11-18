"""Keeps the old Easy Apply system (the extension in the owner's normal Chrome) applying while jobs are still open.

Every 45 seconds, if no run is active: ask the app which approved jobs are REAL Easy Apply (mode == easy) and were found in the last
FRESH_HOURS, and start a run on exactly those, newest first. Company-site jobs are never touched here (Playwright does those).
LinkedIn is capped at LI_PER_CYCLE jobs per cycle (gentle pace for the owner's account). Indeed is left out (CAPTCHA on its last page).
  python -m scripts.easy_loop
"""
import datetime as dt
import time

import requests

BASE = "http://localhost:8000"
OTHERS = ("Naukri", "Internshala", "Wellfound")
FRESH_HOURS = 12
LI_PER_CYCLE = 3
OTHERS_PER_CYCLE = 15


def age_hours(found: str) -> float:
    try:
        return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(found.replace("Z", "+00:00"))).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return 999.0


while True:
    try:
        if not requests.get(f"{BASE}/api/autoapply", timeout=30).json().get("running"):
            jobs = requests.get(f"{BASE}/api/autoapply/preview", timeout=60).json().get("jobs", [])
            easy = [j for j in jobs if j.get("mode") == "easy" and age_hours(j.get("found", "")) <= FRESH_HOURS]
            easy.sort(key=lambda j: j.get("found", ""), reverse=True)
            li = [j["uid"] for j in easy if j["source"] == "LinkedIn"][:LI_PER_CYCLE]
            ot = [j["uid"] for j in easy if j["source"] in OTHERS][:OTHERS_PER_CYCLE]
            pick = ot + li
            if pick:
                r = requests.post(f"{BASE}/api/autoapply", json={"pick": pick, "max": len(pick)}, timeout=60)
                print(time.strftime("%H:%M"), f"started a run: {len(ot)} other + {len(li)} LinkedIn Easy Apply -> HTTP {r.status_code}", flush=True)
            else:
                print(time.strftime("%H:%M"), "no fresh Easy Apply jobs waiting", flush=True)
    except Exception as e:  # noqa: BLE001
        print(time.strftime("%H:%M"), "app not reachable:", str(e)[:60], flush=True)
    time.sleep(45)
