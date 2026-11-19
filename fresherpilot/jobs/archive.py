"""Cold storage for old jobs.

Jobs first seen more than ARCHIVE_AFTER_DAYS (3) days ago leave the live cache (jobs_cache.json, which every page load, AI pass and
dashboard call has to parse) and are written to users/<id>/archive/jobs_<date>.jsonl.gz instead. Nothing is deleted:
the files stay on this computer and are searched only when asked (`search`). What the dashboard needs from them is
kept as tiny per-day counts in archive/stats.json, so numbers and charts do not change.

Never archived: jobs you applied to or contacted, and jobs the AI has not rated yet.
"""

from __future__ import annotations

import gzip
import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fresherpilot.core import users

ARCHIVE_AFTER_DAYS = 3
SEEN_KEEP_DAYS = 45  # boards do not re-list postings older than this; older ids drop out of the index


def _dir():
    d = users.path("archive")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stats_path():
    return _dir() / "stats.json"


def stats() -> dict[str, Any]:
    p = _stats_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"days": {}, "jobs": 0, "runs": []}


# ---- seen-index: ids of archived jobs, so a posting a board lists again is still recognised as already known
_SEEN: dict[str, Any] = {"key": None, "ids": set()}


def _seen_path():
    return _dir() / "seen.json"


def _load_seen() -> dict[str, str]:
    try:
        return json.loads(_seen_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def seen_ids() -> set[str]:
    """{'LinkedIn:123', ...} of archived jobs. Cached until seen.json changes (a set lookup per job)."""
    p = _seen_path()
    try:
        key = (users.current(), p.stat().st_mtime_ns)
    except OSError:
        if not p.exists() and any(_dir().glob("jobs_*.jsonl.gz")):
            rebuild_seen()
            return seen_ids()
        return set()
    if _SEEN["key"] != key:
        _SEEN["ids"], _SEEN["key"] = set(_load_seen()), key
    return _SEEN["ids"]


def is_archived(job: dict[str, Any]) -> bool:
    return f"{job.get('source')}:{job.get('id')}" in seen_ids()


def archived_by_source() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for uid in seen_ids():
        src, _, i = uid.partition(":")
        out.setdefault(src, set()).add(i)
    return out


def _write_seen(index: dict[str, str]) -> None:
    cutoff = (datetime.now() - timedelta(days=SEEN_KEEP_DAYS)).date().isoformat()
    users.write_atomic(_seen_path(), json.dumps({k: v for k, v in index.items() if v >= cutoff}, separators=(",", ":")))


def rebuild_seen() -> int:
    """Rebuild the index from the archive files (first run after upgrading, or if seen.json was lost)."""
    idx: dict[str, str] = {}
    for f in sorted(_dir().glob("jobs_*.jsonl.gz")):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        j = json.loads(line)
                    except ValueError:
                        continue
                    idx[f"{j.get('source')}:{j.get('id')}"] = _local_day(j.get("first_seen")) or datetime.now().date().isoformat()
        except (OSError, EOFError):
            continue
    _write_seen(idx)
    return len(idx)


def daily_kept() -> dict[str, int]:
    """{'2026-11-05': approved jobs first seen that day} for jobs that left the live cache."""
    return {d: v.get("kept", 0) for d, v in (stats().get("days") or {}).items()}


def _local_day(iso: str | None) -> str | None:
    try:
        return datetime.fromisoformat(iso).astimezone().date().isoformat() if iso else None
    except ValueError:
        return None


def run(days: int = ARCHIVE_AFTER_DAYS, dry_run: bool = False) -> dict[str, Any]:
    """Move jobs first seen more than `days` days ago out of the live cache. Returns what was (or would be) moved."""
    from fresherpilot.apply import applicant
    from fresherpilot.jobs import apify_jobs, llm_filter, visited
    from fresherpilot.outreach import messages as outreach
    from fresherpilot.server import _normalize_job

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    apps = applicant.applications()
    contacted = {e.get("uid") for e in outreach.log() if e.get("ok")}
    started = time.time()
    with apify_jobs._CACHE_LOCK:
        payload = apify_jobs.load_cache() or {}
        jobs = payload.get("jobs") or []
        keep, move, day_stats = [], [], {}
        for j in jobs:
            fs = j.get("first_seen")
            if not fs or fs >= cutoff:
                keep.append(j)
                continue
            uid = visited.uid(j)
            if uid in apps or uid in contacted:
                keep.append(j)
                continue
            v = llm_filter.cached_verdict(_normalize_job(j))
            if v is None:  # not rated yet: the AI still has to see it
                keep.append(j)
                continue
            move.append({**j, "_verdict": {"decision": v.get("decision"), "category": v.get("category"), "reason": v.get("reason")}})
            d = day_stats.setdefault(_local_day(fs) or "unknown", {"found": 0, "kept": 0, "rejected": 0, "sources": {}})
            d["found"] += 1
            if v.get("decision") == "keep":
                d["kept"] += 1
                d["sources"][j.get("source") or "?"] = d["sources"].get(j.get("source") or "?", 0) + 1
            else:
                d["rejected"] += 1
        result = {"archived": len(move), "kept_live": len(keep), "days": days, "dry_run": dry_run}
        if dry_run or not move:
            return result
        out = _dir() / f"jobs_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.jsonl.gz"
        with gzip.open(out, "wt", encoding="utf-8") as f:
            for j in move:
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
        if not out.exists() or out.stat().st_size < 100:  # never drop jobs from the live cache unless the archive is on disk
            raise RuntimeError("archive file was not written")
        st = stats()
        for day, d in day_stats.items():
            cur = st["days"].setdefault(day, {"found": 0, "kept": 0, "rejected": 0, "sources": {}})
            cur["found"] += d["found"]; cur["kept"] += d["kept"]; cur["rejected"] += d["rejected"]
            for s, c in d["sources"].items():
                cur["sources"][s] = cur["sources"].get(s, 0) + c
        st["jobs"] = st.get("jobs", 0) + len(move)
        st.setdefault("runs", []).append({"at": datetime.now().isoformat(timespec="seconds"), "moved": len(move), "file": out.name})
        st["runs"] = st["runs"][-30:]
        users.write_atomic(_stats_path(), json.dumps(st, indent=1))
        idx = _load_seen()
        for j in move:
            idx[f"{j.get('source')}:{j.get('id')}"] = _local_day(j.get("first_seen")) or datetime.now().date().isoformat()
        _write_seen(idx)
        payload["jobs"] = keep
        users.write_atomic(apify_jobs._cache_path(), json.dumps(payload, indent=2))
        result.update(file=out.name, seconds=round(time.time() - started, 1), mb_saved=round(sum(len(j.get("description") or "") for j in move) / 1e6, 1))
        return result


def search(q: str, limit: int = 40) -> list[dict[str, Any]]:
    """Look through the archive files (newest first) for jobs whose title/company/location contain every word of `q`."""
    words = [w for w in q.lower().split() if w]
    out: list[dict[str, Any]] = []
    if not words:
        return out
    for f in sorted(_dir().glob("jobs_*.jsonl.gz"), reverse=True):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    hay = line[:1500].lower()  # title / company / location come first in each record
                    if all(w in hay for w in words):
                        j = json.loads(line)
                        out.append({k: j.get(k) for k in ("uid", "title", "company", "employer", "location", "source", "url", "first_seen", "posted", "_verdict")} | {"id": j.get("id")})
                        if len(out) >= limit:
                            return out
        except (OSError, ValueError, EOFError):
            continue
    return out


def totals() -> dict[str, Any]:
    st = stats()
    days = st.get("days") or {}
    c = Counter()
    for v in days.values():
        c["found"] += v.get("found", 0); c["kept"] += v.get("kept", 0); c["rejected"] += v.get("rejected", 0)
    size = sum(f.stat().st_size for f in _dir().glob("jobs_*.jsonl.gz"))
    return {"jobs": st.get("jobs", 0), "kept": c["kept"], "rejected": c["rejected"], "mb": round(size / 1e6, 1), "runs": (st.get("runs") or [])[-3:]}
