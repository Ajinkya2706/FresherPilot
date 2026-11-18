"""Where do applications break? `python -m scripts.apply_health` ranks the failure codes in the owner's
autoapply_log.jsonl (see fresherpilot/apply/failures.py) and shows the lines still falling into "other"."""
from __future__ import annotations

import json

from fresherpilot.apply import failures
from fresherpilot.core import users


def main() -> None:
    path = users.path("autoapply_log.jsonl")
    log = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    s = failures.summarize(log)
    print("outcomes:", s["outcomes"])
    print("failure codes:")
    for code, n in s["failure_codes"].items():
        print(f"  {n:4d}  {code}{'  (job state, no retry)' if code in failures.TERMINAL else ''}")
    other = [l for l in log if l.get("event") in ("skipped", "failed", "parked")
             and failures.classify(str(l.get("detail") or ""), l["event"]) == "other"]
    for l in other[:15]:
        print("  other:", str(l.get("detail"))[:110])


if __name__ == "__main__":
    main()
