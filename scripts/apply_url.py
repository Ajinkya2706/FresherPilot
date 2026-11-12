"""Apply to job links through the running app + Chrome extension (free Groq/NVIDIA AI, no screenshots).

    python -m scripts.apply_url <job link> [<job link> ...]

Needs: `python main.py` running and Chrome open with the FresherPilot extension (v1.16+, reloaded in chrome://extensions):
the app keeps the started run as "pending" and the extension pulls it within ~30 s (no app page has to be open). Prints ONE short line per job, so
an assistant (Claude Code) can call this instead of driving the browser itself (a browser-driven LinkedIn Easy Apply
cost 3-5% of a 5-hour limit; this costs a few hundred tokens)."""
from __future__ import annotations

import sys
import time

import requests

BASE = "http://localhost:8000"


def apply(url: str, wait_s: int = 600) -> str:
    r = requests.post(f"{BASE}/api/autoapply/url", json={"url": url}, timeout=240)
    if r.status_code != 200:
        return f"not started: {r.json().get('detail', r.text)[:160]}"
    info = r.json()
    uid, name = info["queued"], f"{info.get('title')} @ {info.get('company')}"
    end = time.time() + wait_s
    last = ""
    while time.time() < end:
        time.sleep(3)
        st = requests.get(f"{BASE}/api/autoapply", timeout=30).json()
        w = st.get("waiting") or next((p for p in st.get("parked") or [] if p.get("uid") == uid), None)
        if w:
            return f"NEEDS YOU: {name}: {str(w.get('reason') or w)[:140]}"
        for e in reversed(st.get("log") or []):
            if e.get("uid") == uid and e["event"] in ("applied", "skipped", "failed"):
                return f"{e['event'].upper()}: {name}: {str(e.get('detail') or '')[:140]}"
        if not st.get("running"):
            return f"finished without a result for {name} (extension not running?)"
        last = (st.get("ext_seen_s") or 0) > 25 and "extension not responding" or ""
    return f"timed out: {name} {last}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for link in sys.argv[1:]:
        print(apply(link))
