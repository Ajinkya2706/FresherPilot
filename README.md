# FresherPilot

**An AI job-search copilot for Indian fresher developers.** It watches LinkedIn, Naukri, Indeed, Internshala,
Wellfound, Telegram job channels and company career pages around the clock, uses an LLM to keep only the
**full-time, 0-year roles that fit your stack**, and sends each match to your Telegram within minutes of it being
posted. A local web app shows everything, applies for you (browser extension plus a company-portal runner) and finds
recruiters to contact.

Everything runs on free tiers: Cloudflare Workers + D1, GitHub Actions, Groq and NVIDIA AI keys, and Apify's $5/month
credit (for Naukri). **Your computer can be off:** the cloud and the GitHub reader do the reading, checking and
alerting; the local app is for browsing, applying and outreach.

> 🗺️ **Visual guide:** open [`docs/system_map.html`](docs/system_map.html) in a browser for animated-style diagrams of
> every pipeline: how jobs arrive, how the AI judges them, how alerts and button taps sync, and how applying works.
> Longer write-up: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
                 ┌──────────── runs 24/7, your PC can be off ────────────┐
 LinkedIn, Indeed ──▶ GitHub Actions reader ──┐                          │
 Naukri (Apify), Telegram, Internshala,       ├──▶ Cloudflare Worker ──▶ AI check (Groq → NVIDIA)
 Wellfound, career pages ─────────────────────┘     (D1 database)            │
                 └───────────────────────────────────────────────────────┘ ▼
                                     Telegram alerts ◀─┬─▶ web dashboard (password)
                                                       └─▶ local app: list, apply (extension + portal runner),
                                                           outreach
```

## Contents

1. [How fast are jobs found?](#how-fast-are-jobs-found)
2. [Features](#features)
3. [How it works (the whole pipeline)](#how-it-works-the-whole-pipeline)
4. [Getting started](#getting-started)
5. [Daily use and Telegram commands](#daily-use-and-telegram-commands)
6. [Applying: the two pipelines](#applying-the-two-pipelines)
7. [Configuration](#configuration)
8. [Costs and limits](#costs-and-limits)
9. [Environment variables](#environment-variables)
10. [Testing](#testing)
11. [Project structure](#project-structure)
12. [Troubleshooting](#troubleshooting)
13. [Privacy, disclaimer, license](#privacy)

---

## How fast are jobs found?

| Source | Read by | Every |
|---|---|---|
| LinkedIn | GitHub Actions reader (2 machines in parallel, 40 searches) | ~2 min |
| Indeed | GitHub Actions reader (all roles × places) | ~3-4 min |
| Telegram job channels | Cloudflare Worker (cheap "new post?" check, full read when it changes or every 30 min) | 1 min |
| Naukri | Cloudflare Worker, via Apify | ~4 min |
| Internshala | Cloudflare Worker | 4 min |
| Wellfound, company career pages (Greenhouse / Lever / Ashby / SmartRecruiters, 44 companies) | Cloudflare Worker | 8 min |
| Private "Pro" Telegram channel (optional) | browser extension reading your open Telegram Web tab | live |

A job that passes the AI check reaches Telegram within about a minute of being read. These sites offer no
"new job" notifications, so frequent checking is as close to real time as it gets.

## Features

- **AI relevance filter.** Free title rules first, then an LLM extracts facts (employment type, minimum years,
  seniority, role type) and your preferences are applied to them in code (`decide()`), then a skill-fit check against
  your resume, with a second look at every rejection. 45 test cases cover tricky postings. Posts that list "3-5 years"
  but welcome freshers in any wording are kept when the post itself supports it.
- **Fast, cheap AI.** Groq keys first (fastest), NVIDIA keys for bursts and when Groq's daily limit runs out; several
  keys are used in parallel; duplicate postings reuse an earlier answer (51 % of fact calls skipped).
- **Telegram alerts** with Apply / Applied / Seen / Not-for-me buttons, the real posting age, one alert per job across
  boards (reposts within 30 days are skipped), and a ⭐ **PRIORITY** banner for target companies (IBM, NTT DATA,
  Cognizant ... simple test + interview hiring; see [`docs/TARGET_COMPANIES.md`](docs/TARGET_COMPANIES.md)).
- **Phone or laptop?** Every alert says **📱 Easy Apply** (apply inside LinkedIn / Indeed / Naukri / Internshala /
  Wellfound) or **💻 Company site** (the company's careers page).
- **Everything in sync.** Jobs you mark applied anywhere (Telegram button, auto-apply, the app's list) are counted in
  Telegram's `/dashboard`, hidden from `/jobs`, and shown as applied in the app.
- **Pipeline status** (`/status` in Telegram, *Pipeline* tab on the dashboard): when each source last read, new jobs per
  hour, and every stage (ruled out by rules → rejected by the AI → approved → alerted), so a stall shows at once.
- **Web dashboard** on the Worker, behind a password: approved jobs (filter by Easy Apply / company site), the same
  buttons, pipeline status and per-source stats.
- **Local app** (`python main.py`): full job list and dashboard synced with the cloud (including its AI verdicts), a
  *Fetch new jobs* button, profile, apply kit, auto-apply page, recruiter contacts and outreach.
- **Browser extension (MV3).** Autofills application forms (shadow DOM, custom dropdowns, LinkedIn Easy Apply dialogs)
  and runs supervised **auto-apply** with per-board playbooks for LinkedIn, Naukri, Indeed, Wellfound and Internshala.
  Written answers use job-description keywords your resume supports, never ones it doesn't.
- **Company-portal runner** (`apply/site_apply.py` + `github_reader/applybot/`). Opens a real Chrome window on a
  company careers portal (Greenhouse, Lever, Ashby, Workday, Taleo ...), creates or reuses the account, reads the
  verification code from Gmail, and lets the AI plan each page (fill / tick / upload / click), with guard rails and a
  per-job memory. Verified portals are submitted; others are filled and left open for you.
- **Special instructions.** Posts saying "email your CV to ... with subject ..." are answered from your Gmail (resume
  attached, only to an address that is really in the post); Google Form links are filled and wait for your submit.
- **Outreach.** Templated email (Gmail) and WhatsApp messages; placeholder and scraped example addresses are skipped
  and each mailbox is checked before sending to avoid bounces.

## How it works (the whole pipeline)

```
 SOURCES                      CLOUD (Cloudflare Worker, cron every minute)                 YOU
 ───────                      ────────────────────────────────────────────                 ───
 LinkedIn ─┐ GitHub reader ─▶ /api/ingest ─┐
 Indeed ───┘ (Actions)                      │
 Telegram channels ───────────────────────┤
 Naukri (Apify) ──────────────────────────┼─▶ D1 `jobs` (status new)
 Internshala / Wellfound ─────────────────┤        │
 Career pages (ATS) ──────────────────────┘        ▼
                                          1. free rules: city, board experience, title,
                                             blocklist, foreign location, "N+ years" text
                                          2. AI title screen (drops only clear cases)
                                          3. AI facts → decide(): full-time, entry level, 0 years
                                          4. AI skill fit (+ second look at rejections)
                                                    │ keep
                                                    ▼
                                          claims (one alert per opening, 30 days)
                                                    ▼
                                          Telegram alert ──▶ ✅ Applied / 👀 Seen / 🚫 Not for me
                                                    │                    │
                                                    ▼                    ▼
                                          password dashboard /app   D1 `actions` + `applied`
                                                                         │ (synced both ways)
                                          local app ◀── jobs + verdicts ─┘
                                          list · apply · outreach
```

1. **Reading.** Sources are read on their own schedules (table above). The GitHub reader gets its searches and the
   known job IDs from the Worker and posts new cards to `/api/ingest`; it pauses for nothing and skips IDs your laptop
   already read. A new Telegram post replaces the Worker's source step for that minute.
2. **Free rules first.** Nothing reaches the AI if a free rule can decide: wrong city, board experience ≥ 1 year, senior /
   lead / manager / intern / non-dev titles, off-stack words, blocked companies, foreign locations, postings older than
   3 days, and posts that explicitly ask for ≥ 3 years with no fresher wording (34 % of jobs skip the AI this way).
3. **AI steps** (Groq 120b → Groq 20b → NVIDIA models, keys rotated; per-minute 429s only cool that key). Title screen →
   facts → `decide()` → skill fit → a second look at every fit rejection. Full rules in
   [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
4. **Alert.** One alert per opening (`claims`, fingerprints of jobs you were shown: company + title words, description
   hash). Old jobs (> 30 h) are never alerted. Missed alerts are retried for a day.
5. **Sync.** The Worker is the source of truth for alerts and button taps; the local app, while open, pulls jobs and
   verdicts every 40 seconds and pushes back what you marked applied or opened.
6. **Apply.** See [Applying](#applying-the-two-pipelines).

### Duplicates

Same title + company counts as a duplicate only if the descriptions are ≥ 80 % similar (reposts measured 0.97-0.99,
genuinely different openings 0.04-0.50); otherwise it is stored as another opening. The list shows each job once with
"also on" for its other copies.

### Posting age and location

LinkedIn and Indeed give only a date, so every read asks for "posted in the last N minutes" and the window is saved with
the job: alerts say "< 32 min ago" instead of "1 day ago". Locations are your cities plus Remote plus anything open to
every city ("PAN India", "Virtual Drive"); "United States, Remote" style postings are dropped unless India is named.

## Getting started

### 1. Install

```bash
git clone https://github.com/Rugvedrc/fresherpilot.git
cd fresherpilot
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Python 3.11+ (3.13 tested) and Node.js (for `wrangler`, only if you deploy the cloud).

### 2. Run the local app

```bash
python main.py                  # Windows: set PYTHONIOENCODING=utf-8 if the console shows encoding errors
```

Open **http://localhost:8000** (the server listens on both IPv4 and IPv6 loopback, so `localhost` is fast), create your
account (the first one becomes the owner), then:

1. Add your keys in **Settings**: [Groq](https://console.groq.com/keys) (free; several keys from separate accounts are
   better), optionally [NVIDIA](https://build.nvidia.com/settings/api-keys) (free), [Apify](https://console.apify.com/account/integrations)
   (Naukri) and a Gmail [app password](https://myaccount.google.com/apppasswords) for email outreach.
2. **Upload your resume.** The AI drafts your profile and search settings (roles, skills, stacks to skip); check them,
   add your cities and save. Fill the **Profile** page completely (education, work history, answers to common form
   questions): the autofill and portal runner use it.
3. Connect Telegram in **Settings** (create a bot with [@BotFather](https://t.me/BotFather), send it a message, then use
   *Connect* so the app learns your chat ID).

Keys can also go in `.env` for the owner account; see [Environment variables](#environment-variables).

### 3. Make it run 24/7 (optional, recommended)

1. **Cloud** ([Cloudflare](https://dash.cloudflare.com/sign-up), free): `npm i -g wrangler`, `wrangler login`, then
   `python cloud/deploy.py`. It creates the D1 database and Worker, stores your keys as encrypted secrets, registers the
   Telegram webhook and command menu, preloads known job IDs, and writes `FP_CLOUD_URL` / `FP_CLOUD_SECRET` to `.env`.
2. **Dashboard password:** `cd cloud && npx wrangler secret put DASH_PASSWORD`, then open `<FP_CLOUD_URL>/app`.
3. **LinkedIn + Indeed reader** (GitHub Actions, free on public repos):
   - Create a public repo from [`github_reader/`](github_reader/) (copy its files, including `.github/workflows`) and add
     the repo secrets `FP_CLOUD_URL` and `FP_CLOUD_SECRET`.
   - Create a [fine-grained token](https://github.com/settings/personal-access-tokens/new) for that repo only with
     **Actions: Read and write**, and store it in the cloud: `npx wrangler secret put GH_TOKEN`.
   - Put the repo name in `.env` as `FP_READER_REPO=<you>/<repo>` and run `python cloud/deploy.py --config`.

   The Worker starts the reader every 10 minutes; each run loops for almost 6 hours and GitHub's own 30-minute cron is
   only a backup. No personal data lives in that repo.
4. After changing settings, prompts or rules, always run `python cloud/deploy.py --config` so the cloud matches.
5. **Windows deploy note:** `wrangler` sometimes crashes on exit (`UV_HANDLE_CLOSING`). Just run `npx wrangler deploy` in
   `cloud/` again.

### 4. Install the browser extension

1. Open `chrome://extensions` (or `edge://extensions`) and turn on **Developer mode**.
2. **Load unpacked** and select the [`extension/`](extension/) folder.
3. Refresh the app page while logged in; the extension then works as your account. After updating extension files,
   press the reload icon in `chrome://extensions` (Chrome does not pick up changed files by itself). The Auto-apply
   page warns when Chrome runs an older version than `extension/manifest.json`.

Optional: to read a private Telegram channel through the extension (`tgwatch.js`), keep that channel open in
`web.telegram.org` in the same Chrome.

### 5. Self-hosting the full app for a few people

See [`docs/DEPLOY.md`](docs/DEPLOY.md): private, invite-only; your PC + Cloudflare Tunnel or an Oracle Cloud VM, Google
sign-in for invited emails, consent per account, data export and delete endpoints.

## Daily use and Telegram commands

1. **Telegram** brings new matching jobs on its own. Commands (the menu is registered by `deploy.py`):

   | Command | What it does |
   |---|---|
   | `/dashboard` (or `/today`) | today (IST): jobs applied, priority-company jobs applied, alerts sent, seen, still unmarked, last 7 days, list of today's applications |
   | `/jobs` | the 5 newest alerts you haven't marked (doesn't fetch) |
   | `/easy` / `/site` | same, only Easy Apply (phone) or company-site (laptop) jobs |
   | `/status` | pipeline: every source's last read, new jobs per hour, why jobs were dropped in 24 h |
   | `/stop` / `/resume` | pause / resume alerts |
   | `/laptopoff` | hand everything to the cloud right now |
   | `/help` | all commands |

   Anyone else who messages the bot only gets a "not linked, here is how to set up your own" message with the repo links.
2. **Apply:** tap *Apply* on the alert, or open the job and press **Alt+Shift+F** to autofill; review and submit.
3. **Open the local app** for the full list, the auto-apply page, the apply kit, contacts and outreach. It pulls everything
   the cloud found, with the AI verdicts. *Fetch new jobs* reads every board once more right away (range: latest / 1 h /
   3 h / 24 h / all).

## Applying: the two pipelines

**A. Easy Apply (inside the board)**: the extension.
`Auto-apply` page → choose boards and jobs → the extension opens each job in Chrome and runs the board's playbook
(LinkedIn *Easy Apply*, Naukri *Apply*, Indeed, Wellfound, Internshala) → fills fields from your profile, the answer bank
and, for new questions, the AI → Submit → verifies "Application sent". The server hands the run to the extension (the
extension pulls it by long poll, so it starts at once). Jobs that need you (sign-in, CAPTCHA, unknown answers) are set
aside and the queue goes on. Closed jobs are filtered first (a free LinkedIn guest-page check); LinkedIn's daily Easy
Apply limit pauses LinkedIn for 14 hours.

**B. Company portals**: `site_apply.py` runs `scripts/apply_site.py` per job in a real Chrome window (Playwright) using
the engine in `github_reader/applybot/`:
- `snap.py` reads the page (fields, buttons, errors, dialogs, shadow DOM); `classify.py` names the page (sign-in, create
  account, OTP, job detail, form, submitted, closed, CAPTCHA...).
- Rules are the fast path; for any form/unknown page the **AI plans a batch of actions** (`plan.py`) using your complete
  facts (all education and work entries, resume text), the portal's memory and the page. `plan.check_plan` refuses unknown
  ids, Cancel/Back/Delete, Next/Submit with empty required fields, and skills the resume doesn't support.
- Accounts: your email + a per-portal password derived from a secret; verification codes are read from Gmail (or asked via
  Telegram); an **attempt ledger** limits sign-ins, reset mails and code mails per portal per 24 h so accounts are never
  locked. Saved portal sessions are reused for 12 hours.
- Submit policy `site_submit`: `verified` (Greenhouse / Lever / Ashby are submitted, others are filled and the window is left
  open for you), `all`, `never`. A paused job continues in the same window when you answer (`site_cmd/<uid>.json`).
- CAPTCHAs and Cloudflare "verify you are human" pages are never solved; the job waits for you.

A free route classifier (`apply/route.py`) decides easy / site / needs-check for every job with evidence (board field → link
host → board default).

## Configuration

| What | Where |
|---|---|
| Roles, cities, skills, stacks to skip, years of experience, blocked companies, "skilled freshers", stretch jobs | **Settings** page (per user) |
| Boards, title rules, career pages, target companies, Apify budget, schedules | [`core/search_config.py`](fresherpilot/core/search_config.py) |
| AI prompts, model order (Groq / NVIDIA) | [`jobs/llm_filter.py`](fresherpilot/jobs/llm_filter.py) |
| Cloud schedule, alerts, commands, dashboard | [`cloud/src/index.js`](cloud/src/index.js), [`cloud/src/dashboard.js`](cloud/src/dashboard.js) |
| Autofill rules (ATS guidance), profile, answers | `AUTOFILL_RULES` in [`apply/applicant.py`](fresherpilot/apply/applicant.py), [`apply/answerbank.py`](fresherpilot/apply/answerbank.py) |
| Auto-apply choices (never again, blocked companies) | `users/<id>/autoapply_prefs.json` (Auto-apply page) |

`LIVE_AUTO = False` (default) means the laptop reads only on demand; `True` restores always-on laptop readers
(`scripts/keep_running.py`, `scripts/install_autostart.ps1`).

## Costs and limits

| Service | Free tier | Used for |
|---|---|---|
| Groq | 200k tokens/day per model per key, 8k tokens/min | AI checks (a normal day needs ~0.6-1M tokens: use 3-4 keys) |
| NVIDIA | per-key rate limit (~10 requests/min) | AI bursts, fallback, second look |
| Apify | $5/month, 5 concurrent runs | Naukri (~$0.6/day at the 4-minute interval; the budget is capped daily) |
| Cloudflare Workers + D1 | free plan: ~10 ms CPU and ≤ 45 sub-requests per run; D1 5M reads / 100k writes per day | cloud reader, AI step, alerts, dashboard |
| GitHub Actions | unlimited on public repos | LinkedIn + Indeed reader (3 machines per run) |

Design consequences: one source step per Worker minute, Telegram checked by newest post number first, LinkedIn split across
two machines (≈ 1 request / 2.5 s per IP), D1 queries metered and indexed (`/status` shows the daily budget).

## Environment variables

Copy [`.env.example`](.env.example) to `.env`. Keep comments on their own lines (never `# comment` after `KEY=`).

| Variable | Meaning |
|---|---|
| `GROQ_API_KEY`, `GROQ_API_KEY1..20` | Groq keys (separate accounts) |
| `NVIDIA_API_KEY`, `NVIDIA_API_KEY1..2` | NVIDIA keys |
| `APIFY_API_KEY` | Naukri via Apify |
| `SERPER_API_KEY` | optional Google results for contact search |
| `GMAIL_APP_PASSWORD` | email outreach, application emails, verification codes |
| `TELEGRAM_BOT_TOKEN` | your bot (alerts, buttons, commands) |
| `FP_CLOUD_URL`, `FP_CLOUD_SECRET` | written by `deploy.py` |
| `FP_READER_REPO` | `owner/repo` of your copy of `github_reader/` |
| `FP_MODE` | `local` (default) or `cloud` (server deploy) |
| `GOOGLE_CLIENT_ID`, `FP_OWNER_EMAIL`, `FP_ALLOWED_EMAILS`, `FP_SECRET_KEY`, `FP_OPERATOR_NAME`, `FP_CONTACT_EMAIL`, `FP_PASSWORD_SIGNUP` | server deploy only, see `docs/DEPLOY.md` |

Cloud (Worker) secrets: `GROQ_KEYS`, `NVIDIA_KEYS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `APIFY_TOKEN`,
`CLOUD_SECRET`, `GH_TOKEN`, `DASH_PASSWORD` (set by `deploy.py` or `wrangler secret put`).

## Testing

```bash
python -m scripts.check_filter           # 45 hard cases for the AI filter (real AI calls)
python -m scripts.recheck "<job title>"  # re-judge cached jobs after a prompt change
python -m scripts.test_route             # easy / site routing: hand cases + back-test on your own cache
python -m tests.test_applybot_classify   # page classifier on saved real pages (tests/fixtures)
python -m scripts.apply_health           # which apply failure codes happen most (from the auto-apply log)
python -c "import main"; node --check cloud/src/index.js     # quick syntax checks after edits
```

`python scripts/apply_url.py <job link>` starts auto-apply for one link; `python -m scripts.portal_password <host>` prints the
password the runner uses for a portal.

## Project structure

```
fresherpilot/
├── main.py                    entry point: python main.py → http://localhost:8000
├── fresherpilot/              local app (Python package)
│   ├── server.py              FastAPI app, auth, API endpoints, AI check / fetch / auto-apply state
│   ├── core/                  users.py (accounts, encrypted keys, prefs), search_config.py (boards, rules)
│   ├── jobs/                  free_boards.py (LinkedIn, Indeed, Internshala, Wellfound, Telegram), ats_jobs.py (career pages),
│   │                          apify_jobs.py (Naukri, merge, cache), llm_filter.py (AI filter + decide()), live_poller.py
│   │                          (Fetch button), pro_channel.py, visited.py (dedupe keys), missed.py, dashboard.py, ranker.py
│   ├── apply/                 onboarding.py, applicant.py (profile, autofill, apply kit), answerbank.py, autoapply.py
│   │                          (bulk run, playbooks), route.py (easy/site), failures.py, site_apply.py (portal queue)
│   └── outreach/              telegram_bot.py (alerts, cloud sync, mark push), contacts.py, domains.py, messages.py
├── cloud/                     Cloudflare Worker: src/index.js (cron, AI step, alerts, commands, API), dashboard.js (/app),
│                              applybot.js, schema.sql (D1), deploy.py, wrangler.toml
├── github_reader/             GitHub Actions reader (own public repo): reader.py, careers_src.py, workflows, and
│   └── applybot/              the portal-apply engine (snap, classify, plan, brain, engine, actions, mail, otp_detect ...)
├── web/                       local UI (jobs, dashboard, profile, auto-apply, outreach, settings)
├── extension/                 MV3 extension: content.js (fill), background.js (auto-apply), agent.js, bridge.js, tgwatch.js
├── scripts/                   tests, re-check, portal runner entry, health report, password tools
├── tests/                     classifier tests + real page fixtures
├── deploy/                    server setup / update scripts
└── docs/                      ARCHITECTURE, DEPLOY, TARGET_COMPANIES, HISTORY, system_map.html
```

## Old jobs: cold storage and how to get one back

To keep the app fast, jobs first seen **more than 3 days ago** are moved out of the live cache (`users/<id>/jobs_cache.json`)
into compressed files in `users/<id>/archive/` (`jobs_<date>.jsonl.gz`, one JSON job per line, with the AI verdict).
Nothing is deleted. The move runs 90 s after the app starts and every 6 hours (`fresherpilot/jobs/archive.py`,
`ARCHIVE_AFTER_DAYS`). It never moves jobs you applied to, jobs you emailed, or jobs the AI has not rated yet.

What stays visible without loading the archive: applied / outreach numbers (kept in `applications.json` and
`outreach_log.json`), the dashboard's daily "new matches" chart (per-day counts in `archive/stats.json`), your visited marks
(`visited.json`) and the AI verdict cache (`llm_verdicts.json`).

**If you need an old job:**
- **Dashboard:** the "cold storage" card at the bottom has a search box (title, company, location words). Each result links to the original posting.
- **API:** `GET http://localhost:8000/api/archive/search?q=python+developer&limit=40`.
- **By hand:** `python -c "import gzip,json,glob; [print(json.loads(l)['title']) for f in glob.glob('users/*/archive/jobs_*.jsonl.gz') for l in gzip.open(f,'rt',encoding='utf-8')]"`.
- **Put jobs back in the live list:** append the lines of an archive file to the `jobs` array of `users/<id>/jobs_cache.json` (app stopped), or just use the original link.
- **Run the archive now / preview it:** `POST /api/archive/run` (add `?dry_run=true` to only count). `?days=N` archives jobs older than N days (default 3).
- **Safety copy** from before the first run: `backup/data_2026-11-18/jobs_cache_before_archive.json` (delete it once you are happy).

Duplicates: the ids of archived jobs are kept in `archive/seen.json` (about 1 MB, ids older than 45 days drop out). The readers and the
merge step treat them as already known, so a board listing an archived posting again does not bring it back as new.

Slow-app diagnosis: the server logs `[slow]` requests (> 1 s) and, when the event loop stalls for more than 0.7 s, writes every thread's
stack to `logs/lag.txt`, which names the culprit.

## Troubleshooting

| Symptom | Check |
|---|---|
| App is slow on Windows | the server must be reachable on both `127.0.0.1` and `::1`; `requests.get('http://localhost:8000/api/health')` should take ~0.02 s |
| No alerts | `/status` in Telegram: a ⚠️ source or "waiting for AI"; all AI keys exhausted pauses the checker for 5 min |
| `/dashboard` count too low | the app must run once so it pushes jobs marked applied; Telegram counts them within one sync (≈ 40 s) |
| Deploy ends with `UV_HANDLE_CLOSING` | run `npx wrangler deploy` again |
| Extension does nothing after an update | reload it in `chrome://extensions` |
| Cloud readers paused | a non-passive heartbeat (the always-on laptop mode) pauses them 15 min; the manual app sends passive ones |
| Apify "no credit" | the month's $5 is used; the cloud keeps everything else running |
| `.env` value looks wrong | no `# comments` after `KEY=` |

## Privacy

Your resume, jobs, applications and keys stay in `users/<id>/` on your computer (git-ignored) and, if you deploy the
cloud, in your own Cloudflare account. Keys are stored as encrypted secrets. Nothing personal is in this repository; the
cloud's settings file (`cloud/src/config.json`) is generated from your own settings by `deploy.py` and is git-ignored, as are
`.env`, `users/`, `logs/` and OAuth client files. The reader repo contains no personal data and logs never print typed
values.

## Disclaimer

LinkedIn, Naukri and Indeed don't allow automated applying in their terms of service. Use auto-apply at your own risk and at
modest volume; autofill (you review and submit) is the low-risk option. Read job sites politely: the readers pace their
requests and back off when rate-limited. CAPTCHAs are never bypassed.

## License

[MIT](LICENSE)
