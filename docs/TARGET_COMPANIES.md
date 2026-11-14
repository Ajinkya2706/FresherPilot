# Target companies: realistic fresher hiring (Nov 13 2026)

Goal (owner's words): companies where a normal tier-3 fresher can apply, get a normal online test (aptitude / English /
basic coding, not impossible), then interviews, and actually get selected. No hard FAANG-style OAs, no bulk
auto-reject, no TCS-NQT-style mass exam as the only door.

Evidence level: the process descriptions below come from public prep/aggregator pages found by web search
(third-party, not official) plus the owner's friend (IBM, NTT DATA, Cognizant: test, then interviews, then selected).
"Realistic" is a judgement, not a measured fact. Treat unverified ones as candidates, confirm from the owner's own results.

## Tier A: confirmed by the owner's friend / consistent public reports
| Company | Typical fresher role | Process | Where the apply link really lives |
|---|---|---|---|
| IBM India | Associate System Engineer / Associate Developer / Associate Software Engineer | online assessment (aptitude + coding), technical interview, HR | NOT searchable on careers.ibm.com. Postings are reached only through links published on drive/aggregator pages (older ones used BrassRing: `krb-sjobs.brassring.com/...PageType=JobDetails&jobid=<id>`), so we must catch the link when it is posted. Kyndryl is a separate company (kyndryl.com). |
| NTT DATA | Associate Software Engineer / Associate Engineer / Test Engineer / Graduate Engineer Trainee / Associate DevOps | written test (AMCAT-style: aptitude, English, basics), technical, HR (group discussion sometimes) | `careers-inc.nttdata.com/job/...` (SuccessFactors) and Workday; aggregator pages link there |
| Cognizant | GenC / GenC Next / GenC Elevate | aptitude + English + technical test, then interview | cognizant.com careers + Superset (off-campus drives) |

## Tier B: same pattern (large mass-fresher intake, standard tests, interviews), to be confirmed one by one
Capgemini (Analyst / Exceller), Accenture (Associate Software Engineer), Infosys (own portal; 67 jobs already in our list),
Wipro (Elite NTH / Turbo), HCLTech (fresher drives), Tech Mahindra, LTIMindtree, Mphasis, Coforge, Hexaware, Birlasoft,
Zensar, CGI, Genpact (tech roles), DXC, Persistent, Sonata, Cyient, KPIT (bigger tests, check), Deloitte USI (harder).

## Tier C: skip (assessments or competition not realistic for the goal)
Amazon, Google, Microsoft, Atlassian, Flipkart, Uber, Adobe, Goldman/JPM tech, most product unicorns, TCS NQT-only gates.

## Already in the system
Telegram (@freshershunt) posts IBM / NTT DATA / Cognizant drives; `free_boards.resolve_blog` already turns a blog post into
the official apply link. Counts in the current approved list (Nov 13): Infosys 67, Accenture ~22, NTT DATA ~13, IBM 6,
Zensar 9, Capgemini ~7, Birlasoft 4, Genpact 3, Cognizant 2, Mphasis 2, CGI 2.

## How to find every posting (pipeline)
1. Aggregators/Telegram stay the front door for redirect-only companies (IBM): watch the post, resolve to the official
   apply URL (BrassRing / company portal), keep the redirect link as the apply link. Same for NTT DATA / Cognizant drives.
2. Add a `TARGET_COMPANIES` list (this file's tiers A+B) and use it to: always alert (even when the AI/fit says partial),
   mark the alert "assessment drive: apply now", never drop it for "company site" apply mode, and keep it out of the
   auto-apply "skip company sites" rule (these need the human to do the test anyway).
3. Direct crawl where the portal is open: NTT DATA (`careers-inc.nttdata.com`, Workday), Capgemini, Accenture, Cognizant,
   Infosys, Wipro, HCLTech, TechM, LTIMindtree careers pages; add to `CAREER_PAGES` (currently 44).
4. LinkedIn guest search per company name (`f_C` / keywords "IBM Associate System Engineer" etc.) as a safety net.
5. Calendar of drives: weekday.works, lets-code.co.in, beincareer.com, freshershunt `/off-campus-drive` pages as extra
   readers (drive announcements, closing dates).

## Open questions for the owner
- Which of tier B did your friends actually clear? (Prioritise those.)
- OK to alert every drive for tier A/B (even outside Pune/Mumbai/Bengaluru/Hyderabad, since these are often "Pan India")?

## Measured on Nov 13 2026 (real requests from this PC, not assumptions)
| Source | Result | Use |
|---|---|---|
| Telegram `@freshershunt` (public) | 144 KB preview with messages: readable (already our reader) | keep |
| Telegram "Fresher Hunt Pro" | none of the guessed public handles (`freshershuntpro`, `freshershunt_pro`, `freshers_hunt_pro`, `FreshersHuntPro`...) has a web preview = it is a PRIVATE channel: needs the owner's access, see below | blocked until owner answers |
| NTT DATA `careers-inc.nttdata.com/search/?locationsearch=India` | 200, plain HTML, 35 India jobs listed (mostly experienced: ERP/Oracle/Senior), job URLs `/job/<place>-<title>/<id>/` | easy crawl, but entry-level roles are rare here: fresher drives usually come via aggregator links |
| Capgemini `capgemini.com/wp-json/macs/v1/jobs?country_code=en-in` | 200 JSON, 720 India jobs, official | easy crawl (filter graduate/fresher) |
| IBM `ibm.com/in-en/careers/search` | 200, 125 KB, but no job data in the HTML (JS app); BrassRing home gives an empty page: fresher reqs are only reachable by direct link | only via posted links (Telegram/aggregators) |
| Cognizant `careers.cognizant.com` | 200, 40 KB, no job links in the static HTML (JS app) | needs a browser-based read, or drive announcements |
| Accenture, Wipro, HCLTech, TechM, Mphasis | 200 HTML (large), job lists are JS-rendered or need the site's search API | later: one probe each |
| Infosys `career.infosys.com` | 403 for plain requests | needs the extension/browser, or aggregators |
| Workday (NTT, LTIMindtree, Capgemini, Cognizant tenants guessed) | 422: tenant/site names wrong, not found by guessing | skip guessing; find the real tenant from a live job link |

## Built Nov 13 2026 (measured, working)
- NTT DATA: real portal found from the Pro channel's links = Workday `nttlimited.wd3.myworkdayjobs.com/NTT_Careers` (JSON at `/wday/cxs/nttlimited/NTT_Careers/jobs`, 261 India jobs, "Posted Today/Yesterday" dates). Added as a `workday` career page (laptop `ats_jobs._workday` + cloud `srcCareers`); first cloud run added 6 jobs, the AI kept 1, 1 alert sent.
- Capgemini feed measured and rejected: 691 of 720 India jobs are tagged "Experienced Professionals" (no graduate level), no real posting dates.
- IBM: reachable only through links the Pro channel re-shares (`lnkd.in/xxxx` -> `careers.ibm.com/en_US/careers/JobDetail?jobId=...`, resolved by `jobs/pro_channel.resolve_link`, tested). Needs the Telegram Web tab open (extension `tgwatch.js`).
- Still to find per company (one probe each): Cognizant, Accenture, Infosys, Wipro, HCLTech, TechM, LTIMindtree, Mphasis: their sites are JS apps or need a browser; real drives come via the Pro/@freshershunt channels and LinkedIn.

## Built Nov 14 2026: per-company LinkedIn searches (the "hidden" redirect-only companies)
- Why: IBM / NTT DATA / Cognizant (and tier B) fresher jobs can't be found on their own career pages, but LinkedIn lists them
  and Apply redirects to the company page. Measured Nov 14 (company-filtered LinkedIn search, last 7 days, India, vs `seen`):
  IBM 39 title-passing postings -> 26 never seen; Cognizant 86 -> 68; Capgemini 37 -> 13 (107 of 162 = 66% unseen). Their titles
  ("Application Developer-Asset Management", "Data Scientist-Artificial Intelligence", "AI Observ. & Telemetry Engr") never matched
  the generic title searches. NTT DATA 4 cards, Accenture 2 (little on LinkedIn).
- How: `search_config.TARGET_COMPANIES_LI` (25 companies: LinkedIn company ids from `jobs-guest/api/typeaheadHits?typeaheadType=COMPANY&query=<name>`)
  -> cloud config `li_companies` / `li_company_every_min` (8) -> `/api/reader` -> `github_reader/reader.py read_linkedin_companies`
  (guest search with `f_C=<id>`, location India, all roles, window since last read `gh_read.linkedin_co`, max 24 h, <=10 pages,
  7-min budget per round, runs on the li0 machine only) -> `/api/ingest` -> usual title rules, city filter, AI, alerts.
- To add a company: find its id with the typeahead URL above, append to `TARGET_COMPANIES_LI`, `python cloud/deploy.py --config`.
- Not covered: the laptop's manual "Fetch" does not run these searches (cloud/GitHub reader only). Naukri/Indeed company searches not added.

## Research Nov 14 2026: speed, "hidden" drives, how FreshersHunt gets them (measured)
- `@freshershunt` (public) is NOT real-time: it posts on a clock, ~1 job per hour at :00-:10 IST (87 of 120 posts; median gap 62 min,
  ~24/day). Its website `freshershunt.in` (WordPress, open REST API `/wp-json/wp/v2/posts` + `/feed/`) publishes each drive HOURS earlier
  than the Telegram post: IBM Associate System Engineer blog 04:53 UTC -> Telegram 06:59; Capgemini ASE +7.5 h; Accenture +7.5 h;
  ServiceNow +9 h; Honeywell +12.5 h. The blog's apply links point mostly to the companies' own career systems (Amazon, Cisco, HPE, Wipro,
  Citi, Qualcomm, Workday/Oracle HCM/Eightfold portals), so the curators watch official career pages. Built: `srcBlog` in the Worker
  (every minute; jobs stored as source "Telegram", id `blog:<post id>`; the later Telegram repost is dropped via seen `blogurl:<link>`).
- IBM's own search API (`www-api.ibm.com/search/api/v2`, open) lists 2,492 "Professional" + 2 "Internship" roles in India and NO entry-level
  roles, and `JobDetail` pages return an empty 202 (bot protection): so fresher drives can't be found there. But the IBM "Associate System
  Engineer" drive IS a LinkedIn job (blog says "Open IBM's LinkedIn listing"); our system found it at 04:46 UTC, 6 min BEFORE the blog.
  LinkedIn company search (f_C) shows IBM/Cognizant "Professional" roles with odd titles that generic searches missed (66% unseen).
- Our own processing is not the slow part: ingest -> AI check -> alert measured median 0.5 min, max 1.8 min (384 kept jobs/48 h);
  LinkedIn detection lag 1-12 min. The slow parts were the 8-min company cadence (now a dedicated `co` machine, ~1-2 min) and, for
  Telegram-sourced drives, the hourly drip (now bypassed by reading the blog).
- Still not covered: official career sites of the companies the blog curates (Workday / Oracle HCM / Eightfold / Lever / Greenhouse
  tenants): only 44 are in CAREER_PAGES; adding the ones the blog links to (Cisco, HPE, Wipro, Citi, Qualcomm, Salesforce, Honeywell...)
  is the next lever. Private Pro channel still needs the laptop + Telegram Web tab (tgwatch.js).

## Built Nov 14 2026 (later): direct career-site readers + minimum-delay pipeline
- **Reader machines now** (GitHub Actions, free): `read.yml` = li0, li1 (LinkedIn halves), indeed. `fast.yml` (own concurrency group, started by the
  Worker's `dispatchReader` every 10 min) = co0, co1 (target-company LinkedIn searches, 12-13 companies each, round ~35 s) and `careers`
  (`github_reader/careers_src.py` every round ~100 s + a blog poke `POST /api/tick?step=blog` every 20 s).
- **careers_src.py** (India only, last posted_within_days, new jobs only, detail only for titles that pass): Workday (NTT DATA, Walmart,
  Salesforce, LSEG, Zebra, Kaleris, Altera, Accenture, Genpact; to verify when Workday is up: HPE, Qualys, State Street, TransUnion, Unisys,
  Cigna, Danaher, Rackspace, Silicon Labs, Edwards, Light & Wonder, Kyndryl Early/Professional), Oracle HCM (Honeywell x2, JPMorgan, Nokia,
  Zensar), Eightfold PCSX (Microsoft, Qualcomm, PayPal, Eaton, Micron), Phenom (Cisco, HPE, GE Healthcare, P&G, Quest Global, NTT DATA),
  Amazon (search.json), Cognizant (full XML feed `careers.cognizant.com/global-en/jobs/xml/?rss=true`, newest first, streamed),
  Wipro (SuccessFactors `POST /services/recruiting/v1/jobs`, sortBy "date"; no description available), Capgemini (SuccessFactors HTML list).
  Probed, NOT usable: IBM (public index has no entry level; detail pages bot-protected), Infosys/TCS (403), HCLTech (SF service returns 0),
  Tech Mahindra/LTIMindtree/Mphasis/Coforge/Persistent/Birlasoft/Cyient/KPIT (JS or custom sites, not probed further), Deloitte USI (TalentBrew HTML,
  skipped: mostly non-dev). Fingerprints (Nov 14): Wipro, HCLTech, Capgemini = SuccessFactors; Hexaware, Zensar = Oracle HCM; Genpact, Kyndryl,
  Accenture = Workday; Cognizant = own CMS + feed.
- **Delay**: the Worker judges + alerts at once after `/api/ingest` (`aiAndAlerts` via `ctx.waitUntil`, 45 s lock shared with the cron):
  measured found -> alert 5-47 s for career-site jobs. Blog poked every 20 s. Company searches every ~35 s instead of 8 min; career sites
  every ~100 s instead of ~3 h (old `srcCareers` still runs for its 44 pages, slowly).
- **Title rule** `TITLE_LEVEL`: "L3".."L9" in the title = experienced (Wipro/Cognizant grades; L1 = fresher, L2 left to the AI). Back-test: 72
  cached jobs, 0 approved, 0 applied.
