"""Tests for fresherpilot/apply/route.py: `python -m scripts.test_route` (exit 1 on failure).
Part 1 = hand-written cases. Part 2 = back-test on the real job cache: hide each job's own `apply_mode`, ask the
classifier, compare (jobs whose board said easy/site are the ground truth)."""
from __future__ import annotations

import collections
import json
import sys

from fresherpilot.apply import route

CASES = [
    # (job, expected class, expected ats)
    ({"source": "LinkedIn", "apply_mode": "easy", "url": "https://in.linkedin.com/jobs/view/x-1"}, "easy", ""),
    ({"source": "LinkedIn", "apply_mode": "site", "url": "https://in.linkedin.com/jobs/view/x-1"}, "site", ""),
    ({"source": "LinkedIn", "url": "https://in.linkedin.com/jobs/view/x-1"}, "needs_check", ""),
    ({"source": "Indeed", "url": "https://careers.persistent.com/jobview/dev-pune-1"}, "site", ""),
    ({"source": "Indeed", "url": "https://in.indeed.com/viewjob?jk=abc"}, "needs_check", ""),
    ({"source": "Naukri", "url": "https://www.naukri.com/job-listings-sde-1"}, "needs_check", ""),
    ({"source": "Naukri", "apply_mode": "easy", "url": "https://www.naukri.com/job-listings-sde-1"}, "easy", ""),
    ({"source": "Internshala", "url": "https://internshala.com/job/detail/x"}, "easy", ""),
    ({"source": "Wellfound", "url": "https://wellfound.com/jobs/123-dev"}, "easy", ""),
    ({"source": "Careers", "url": "https://boards.greenhouse.io/acme/jobs/1"}, "site", "greenhouse"),
    ({"source": "Careers", "url": "https://jobs.lever.co/acme/1"}, "site", "lever"),
    ({"source": "Careers", "url": "https://jobs.ashbyhq.com/acme/1"}, "site", "ashby"),
    ({"source": "Careers", "url": "https://acme.wd5.myworkdayjobs.com/en-US/Careers/job/Pune/Dev_R-1"}, "site", "workday"),
    ({"source": "Careers", "url": "https://www.coinbase.com/careers/positions/8335621?gh_jid=8335621"}, "site", "greenhouse"),
    ({"source": "Careers", "url": "https://careers.smartrecruiters.com/Acme/1"}, "site", "smartrecruiters"),
    ({"source": "Telegram", "url": "https://t.me/freshershunt/1", "blog_url": "https://freshershunt.in/post"}, "site", ""),
    ({"source": "Telegram", "url": "https://t.me/freshershunt/1", "blog_url": "https://jobs.lever.co/x/1"}, "site", "lever"),
    ({"source": "Cutshort", "url": "https://cutshort.io/job/x"}, "needs_check", ""),
    ({"source": "LinkedIn", "url": ""}, "needs_check", ""),
    ({"source": "Indeed", "url": "https://lnkd.in/abc"}, "needs_check", ""),
]


def unit() -> int:
    bad = 0
    for job, cls, ats in CASES:
        r = route.classify(job)
        if r["cls"] != cls or (ats and r["ats"] != ats):
            bad += 1
            print("FAIL", job, "->", r, "expected", cls, ats)
    # the host helper and the landing hand-over
    assert route.host_of("https://www.Example.com/a?b=1") == "example.com"
    assert route.host_of("") == "" and route.host_of("not a url ::") == ""
    assert route.normalize_url("https://x.com/job/1?utm_source=fresherpilot&fp_job=abc") == "https://x.com/job/1"
    assert route.normalize_url("https://x.com/job?id=7&utm_medium=app") == "https://x.com/job?id=7"
    assert route.reclassify_after_landing({}, "https://acme.wd1.myworkdayjobs.com/x")["ats"] == "workday"
    assert route.reclassify_after_landing({}, "https://www.linkedin.com/jobs/view/1") is None
    assert route.reclassify_after_landing({}, "https://lnkd.in/x") is None
    assert route.pipeline({"source": "Careers", "url": "https://jobs.lever.co/a/1"}) == "B"
    page = [  # captured live 2026-11-18
        ("Naukri", [{"id": "apply-button", "text": "Apply"}], "", "easy"),
        ("Naukri", [{"id": "company-site-button", "text": "Apply on company site"}], "", "site"),
        ("LinkedIn", [{"aria": "Easy Apply to this job", "text": "Easy Apply"}], "", "easy"),
        ("LinkedIn", [{"text": "Apply"}], "", "site"),
        ("LinkedIn", [], "Not currently accepting applications", "needs_check"),
        ("Indeed", [], "Just a moment... Verify you are human", "needs_check"),
        ("Indeed", [{"text": "Apply now"}], "", "easy"),
        ("Indeed", [{"text": "Apply on company site"}], "", "site"),
        ("Wellfound", [], "", "needs_check"),
        ("Wellfound", [{"text": "Apply now"}], "", "easy"),
        ("Internshala", [{"id": "top_easy_apply_button", "text": "Apply now"}], "", "easy"),
    ]
    for src, btns, txt, want in page:
        got = route.classify_page(src, btns, txt)["cls"]
        if got != want:
            bad += 1
            print("FAIL page", src, btns, txt, got, want)
    print(f"unit: {len(CASES) - bad}/{len(CASES)} cases")
    return bad


def backtest() -> int:
    from fresherpilot.core import users

    try:
        jobs = json.loads(users.path("jobs_cache.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("back-test skipped (no job cache):", exc)
        return 0
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", list(jobs.values()))
    agree = collections.Counter()
    wrong = []
    unknown_now = collections.Counter()
    for j in jobs:
        truth = j.get("apply_mode")
        hidden = dict(j, apply_mode="")
        got = route.classify(hidden)["cls"]
        if truth in ("easy", "site"):
            key = (j.get("source"), "ok" if got == truth else "wrong" if got != "needs_check" else "undecided")
            agree[key] += 1
            if got not in (truth, "needs_check") and len(wrong) < 12:
                wrong.append((j.get("source"), truth, got, (j.get("url") or "")[:90]))
        else:
            unknown_now[(j.get("source"), got)] += 1
    print("back-test (hide apply_mode, compare with the board's own answer):")
    for k, v in sorted(agree.items(), key=str):
        print("  ", k, v)
    print("jobs the board left unlabelled -> classifier:")
    for k, v in sorted(unknown_now.items(), key=str):
        print("  ", k, v)
    for w in wrong:
        print("  WRONG", w)
    # the rule that matters: a decided answer must (almost) never contradict the board
    wrong_n = sum(v for (s, o), v in agree.items() if o == "wrong")
    decided = wrong_n + sum(v for (s, o), v in agree.items() if o == "ok")
    print(f"decided {decided}, contradicting the board: {wrong_n}")
    return 1 if decided and wrong_n / decided > 0.02 else 0


if __name__ == "__main__":
    sys.exit(1 if unit() + backtest() else 0)
