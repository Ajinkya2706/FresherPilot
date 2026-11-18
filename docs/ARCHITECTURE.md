# Architecture

> Visual version: open [`system_map.html`](system_map.html) in a browser (pipelines, funnel, sync, apply flows).

FresherPilot has four parts. Only the local app needs your computer.

| Part | Runs on | Does |
|---|---|---|
| **Local app** (`fresherpilot/`, `web/`, `extension/`) | your PC, when you start it | full job list and dashboard, *Fetch new jobs*, apply kit, auto-apply, portal runner, contacts, outreach |
| **Cloud** (`cloud/`) | Cloudflare Worker + D1, cron every minute | reads Telegram, Naukri (Apify), Internshala, Wellfound and career pages; AI check; Telegram alerts, buttons and commands; password dashboard at `/app` |
| **Reader** (`github_reader/`) | GitHub Actions, 3 machines per run | reads LinkedIn (two machines, half the searches each) and Indeed nonstop, sends new jobs to the cloud |
| **Extension** (`extension/`) | your Chrome | form autofill, board auto-apply playbooks, optional private-channel reader |

## 1. Data flow

```
reader (LinkedIn, Indeed) ──POST /api/ingest──┐
cloud sources (Telegram, Naukri, ...) ────────┼─▶ D1 `jobs` (status new)
extension tgwatch (private channel) ──▶ laptop ┘
                                              │
cron, every minute: AI step ◀─────────────────┘
  rules → title screen → facts → decide() → skill fit → second look (rejections)
  └─▶ status keep/reject ─▶ Telegram alert (dedupe: D1 `claims`, 30 days)
                          └─▶ local app pulls jobs + verdicts (GET /api/jobs) while it's open
Telegram buttons / dashboard buttons ─▶ D1 `actions` + `applied` ─▶ local app marks applied / seen
local app marks (applied, opened) ──POST /api/mark──▶ D1 `alerts.state` + `applied`
```

- **One decision logic, two languages.** The cloud uses the local app's own prompts and rules (`cloud/deploy.py` builds
  `cloud/src/config.json` from them); `decide()`, the title rules, the board rules and the duplicate fingerprints exist in
  Python and JavaScript and must stay in sync (verified identical on real data). Run `python cloud/deploy.py --config` after
  any change.
- **Cron tick (every minute).** (1) cheap Telegram "new post?" check (newest post number only); (2) one source step from an
  8-minute cycle: Apify every 2 min (Naukri every ~4), Internshala 4, Wellfound / career pages 8; a new Telegram post replaces
  the step; (3) `dispatchReader` every 10 min (GitHub keeps one run + one waiting); (4) one AI step (≤ 10 jobs: title screen →
  facts → fit → ≤ 2 second looks) and alerts (≤ 6). Each step records `src_ok` / `src_err` for the status pages.
- **Heartbeats.** The laptop's passive heartbeat (manual mode) doesn't pause anything; a non-passive one (the old always-on
  laptop mode) pauses the cloud readers for 15 minutes. `deploy.py` must never send one.

## 2. Filtering: what reaches you

1. **Free rules** (Python `_board_reject` / `title_excluded`, JS `boardReject` / `titleExcluded`): senior / lead / manager /
   architect / intern / non-dev words, non-software engineering, off-stack words unless the title has own-stack words,
   "N+ yrs" in the title, board experience field ≥ `reject_from_years`, LinkedIn Director / Executive, city filter (cities +
   Remote + nationwide; LinkedIn "Remote" searches get "Remote, " prefixed), foreign-remote locations, blocked companies,
   postings older than 3 days (Naukri refreshed listings), Naukri internships, and posts whose own text states ≥ 3 years
   with no fresher wording (`PRE_AI_YEARS_MIN`; 34 % of jobs skip the AI, back-tested with 0 approved lost). Posts listing
   "N+ years" are still read by the AI when `skilled_freshers` is on (title not Senior/Lead, description ≥ 80 chars).
2. **AI title screen** drops only clear cases.
3. **AI facts → `decide()`**: full-time only; no internship / contract / part-time; seniority entry or unclear (Mid-Senior only
   with freshers welcome or < 1 year); roles developer / AI-ML-data / DevOps / QA automation; 1+ years rejected unless
   freshers are explicitly welcome (`stretch_jobs` off). "Freshers welcome" must be supported by the post (quoted evidence,
   fresher wording or a fresher title); a board range starting at 0 is exempt. Master's / PhD requirements are rejected.
4. **AI skill fit**: strong / partial kept; non-developer or not-fresher rejected; every rejection gets a **second look**
   (full post, medium effort, other model family; "none" stacks stay rejected).

Measured: audit of 220 rejections → ~2 % wrong. Approval rates by source: Telegram 38 %, Naukri 10 %, Internshala 9 %,
LinkedIn 6 %, Wellfound 5 %, Indeed 3 %, Careers 0.6 %. LinkedIn's experience-level filter is not used ("Not Applicable"
holds about half the approved LinkedIn jobs).

### AI providers (`jobs/llm_filter.py`, cloud mirror in `index.js`)

Order per call: Groq 120b on every key → Groq 20b → NVIDIA (nemotron-3-ultra → nemotron-3.5-lightning → minimax-flash; thinking
off; keys rotated per worker) → Groq qwen last. A per-minute 429 cools that key+model (no sleeping); an NVIDIA timeout (60 s)
skips that model for 10 minutes; a daily limit or 401 marks the key exhausted for 30 minutes; all keys out pauses the checker
5 minutes. The second look goes NVIDIA-first (saves ~300k Groq tokens/day). The local app runs one worker per Groq key and adds
NVIDIA workers only when chunks > 2 × Groq keys. The cloud logs usage in D1 `ai_usage` (`/api/usage?days=N`) and reuses an
earlier answer for the same title + company within 7 days when the description is ≥ 85 % the same (`findReusable`).

## 3. Duplicates and alerts

- **Per board** (`merge_external`): same title|company is a duplicate only if the description is ≥ 0.8 similar (`_same_post`);
  otherwise it is another opening (`dedupe_variant`, key `title|company#n`). Old copies leave the cache after 21 days.
- **Across boards**: visited keys = uid, `title|company`, loose `fz:` (cleaned company + title words) and `ds:` (description
  hash). The list collapses jobs sharing a key (best copy by source rank) and shows "also on".
- **Alerts**: the only "already alerted" check is D1 `claims` (fingerprints of jobs shown: alerted or visited), kept 30 days;
  blocked dupes get an `alerts` row state `dup`, too-old ones `old` (> 30 h by real time / read time + `within_min`). Approved
  jobs without an alert row from the last day are retried. Alerts carry a ⭐ PRIORITY banner for target companies.
- **Buttons** (✅ Applied, 👀 Seen, 🚫 Not for me) are handled by the Worker's webhook: they write `actions` (+ `applied` for ✅)
  and update the alert. The app pulls `actions` and marks the job locally; it pushes its own marks back (`/api/mark`) so the
  two sides agree.
- **Posting age**: LinkedIn / Indeed give only a date; reads stamp `posted_within_min` and alerts show "< 32 min ago".
- **Apply mode**: `easy` (inside LinkedIn / Indeed / Naukri / Internshala / Wellfound) or `site` (company careers page), from the
  board's apply button or `route.classify` evidence; shown on alerts and filterable.

## 4. Telegram bot

`/dashboard` `/today` (applied today = every job in D1 `applied`, with priority = target company), `/jobs` `/easy` `/site`,
`/status` (pipeline, 24 h drop reasons, D1 budget), `/stop` `/resume`, `/laptopoff`, `/help`. Only the owner's chat is served;
other private chats get a once-an-hour "not linked yet, here is how to set up your own" message with the repo links.

## 5. D1 tables (`cloud/schema.sql`)

| Table | Holds |
|---|---|
| `seen` | job IDs the cloud/laptop/reader already know (cleaned after 45 days) |
| `jobs` | every read job with status new / keep / reject, facts, fit, category, found_at, within_min (21 days) |
| `claims` | fingerprints of jobs shown to you (30 days) |
| `alerts` | alert text, source, url, state (NULL / applied / seen / hidden / dup / old) |
| `actions` | button taps, pulled by the laptop (`a` applied, `v` seen, `x` hidden) |
| `applied` | one row per job marked applied anywhere, with its real time, title and company: counted by `/dashboard` |
| `state` | key-value: source timestamps, `gh_read`, `d1_use`, `alerts_off`, `apply_dry`, ... |
| `ai_usage` | AI tokens per day / provider / model / key / step |
| `apply_queue`, `apply_otp` | legacy cloud-runner queue; the Worker still relays Telegram verification codes |

Daily free limits are metered (`metered(env.DB)`): > 60 % of a limit raises one Telegram warning a day.

## 6. GitHub reader (`github_reader/`)

The Worker dispatches the workflow every 10 minutes; its concurrency keeps one run + one waiting, so reading never stops
(`*/30` cron is only a backup). One run = 3 machines (`FP_SHARD`): `li0` / `li1` each read half of the 40 LinkedIn searches
(separate IPs, a full round every ~2 min), `indeed` reads Indeed back to back (~3-4 min). Each loops ~340 minutes. Config, known
IDs and title rules come from the Worker (`/api/reader`, `/api/titles`) and new jobs go back through `/api/ingest`. LinkedIn
uses the guest search with a 2.5 s pace and 429 backoff; known IDs and excluded titles are never opened; it reads the window
since the last read (+ 10 minutes). The laptop's heartbeat sends the IDs it already has so the reader skips them. Read times are
stored in `gh_read` for `/status`.

## 7. Local app

- FastAPI server (`server.py`) with JSON files per user under `users/<id>/` (no database): `jobs_cache.json`,
  `llm_verdicts.json`, `visited.json`, `applications.json`, `telegram_alerts.json`, `cloud_sync.json`, `autoapply_*`,
  `site_*` (accounts, memory, ledger, sessions, commands), `applicant_profile.json`, `search_prefs.json`, `keys.enc`.
- Binds both loopback addresses (otherwise `localhost` waits ~2 s for IPv6 to fail on Windows).
- `/api/jobs?slim=true` is what the web list loads (rejected jobs without descriptions; memoized by file mtimes; gzip).
- Independent stages: AI-consumer thread (every 20 s checks unrated jobs), live readers (`live_poller.run_once` = Fetch button:
  every board once + one LinkedIn round + Naukri on Apify), auto-apply; `GET /api/pipeline` shows the three queues.
- `telegram_bot.cloud_sync` (every ~40 s while open): heartbeat (passive) → imports cloud jobs with AI verdicts (no re-check, other
  cities skipped) → pulls button taps → pushes marks (applied with real times, seen). `live_poller._cloud_failover` starts the
  always-on readers if the cloud stops answering.
- Housekeeping: `_trim_old_rejects` shortens old rejected descriptions; `reopen_stale_board_rejects` re-opens free rejects after a
  rule change; visited keys and the unrated-job set are cached.

## 8. Applying

### A. Board auto-apply (extension)
`autoapply.start()` builds the queue (`eligible_jobs`: closed jobs pre-checked, never-again / blocked companies removed, per-site
breaker `failures.tripped_sources`) and leaves a payload in `STATE["pending"]`; the extension long-polls
`GET /api/autoapply/pending?wait=25` and runs it. Per job `decide()` picks the next step (playbooks for LinkedIn Easy Apply,
Naukri, Indeed, Wellfound, Internshala; "already applied" only from a real button or page text; Submit > Review > Next; success
text "Application sent"). `content.js` fills fields (shadow DOM, custom dropdowns, React-safe setters, forced fill for LinkedIn's
numeric boxes) with answers from the profile, the answer bank and the AI (batches in parallel per key; demographics straight
from the profile). Jobs needing you are parked; per-job limit 8 minutes; Stop and per-job commands come from the Auto-apply
page. Special instructions: email-your-CV posts are sent from Gmail (guards against placeholder subjects and non-CV
addresses); Google Forms are filled and wait for you.

### B. Company-portal runner (`site_apply.py` → `scripts/apply_site.py` → `github_reader/applybot/`)
Per job a real Chrome window (Playwright). `snap.py` → `classify.py` → rules for known states; for forms / unknown pages `plan.py`
asks the AI for a batch of actions with complete facts + portal memory (`brain.py`, `users/<id>/site_memory/<uid>.json`),
validated by `plan.check_plan`. `engine.py` handles accounts (per-portal derived password), OTP / verification links (Gmail
watcher + `otp_detect`, else Telegram), cookie banners, privacy statements, resume slot detection, stuck detection (state repeats
→ AI, then `needs_you`). The attempt ledger (sign-ins 2, reset mails 1, code mails 6 per portal per 24 h) prevents lock-outs.
Saved logins are reused 12 hours. Submit policy `site_submit`: `verified` (Greenhouse / Lever / Ashby), `all`, `never`.
After `needs_you` the runner stays alive and continues in the same window when a command file arrives.

### Routing and health
`route.classify(job)` → easy / site / needs_check with evidence; `route.classify_page` reads decisive page signals;
`apply_health` ranks failure codes. Closed jobs were 44 % of early skips, hence the preflight.

## 9. Pro channel (optional)
A private Telegram channel is read by the extension (`tgwatch.js`) from an open Telegram Web tab, posted to
`/api/pro/ingest`, parsed by `jobs/pro_channel.py` (digest blocks, role lists, single posts; short links resolved to the real
page) and merged like any other source.

## 10. Limits that shape the design

- Cloudflare free: ~10 ms CPU and ~45 sub-requests per run → one source per minute + one AI step.
- LinkedIn rate-limits by IP (~1 request / 2.5 s) → two reader machines.
- Apify's $5/month pays for Naukri only; per-run caps and a daily share (credit left / days left).
- Groq free: 200k tokens/day per model per key, 8k/minute; NVIDIA ~10 requests/minute per key.
- Never put `# comments` after `KEY=` in `.env`; keys are never printed or logged.

See also: [`DEPLOY.md`](DEPLOY.md) (self-hosting), [`TARGET_COMPANIES.md`](TARGET_COMPANIES.md) (priority companies),
[`HISTORY.md`](HISTORY.md) (dated fix logs and measurements).
