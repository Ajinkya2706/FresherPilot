# Automating quick apply on Naukri and Indeed (India fresher, 2026)

Evidence base is thin. Search and fetch results mostly gave README-level facts. No source documents Naukri's apply API, the chatbot DOM, or Indeed smartapply DOM. Anything not cited below is listed under Gaps.

## Apply flow and DOM/network behaviour (Naukri chatbot, Indeed smartapply)

### Takeaway
No public documentation exists for either flow. The only concrete Naukri selectors come from one Selenium bot, which does not handle the chatbot at all. Plan on capturing live DOM and network traffic yourself.

### Cited Findings
- Naukri's reference Selenium bot tries these apply-button selectors in order (3 s wait each): `//button[contains(text(),'Apply on company site')]`, `//button[contains(text(),'Apply')]`, id `company-site-button`, `button[class*='company-site-button']`, `[class*='apply-button-container'] button`. After the click it only checks for `input#CUSTOM-FIRSTNAME`, `input#CUSTOM-LASTNAME` and a `//*[text()='Submit and Apply']` button. It has no chatbot or questionnaire logic. — [Naukri-Edge.py](https://raw.githubusercontent.com/lordzohar/Naukri-autoapply-bot/main/Naukri-Edge.py)
- The same repo says it was updated for Naukri's 2026 redesign. Job cards are now `div.srp-jobtuple-wrapper > div.cust-job-tuple` and titles are `a.title` inside an `h2`. Naukri is a React/Next.js app with hashed CSS classes, so selectors are fragile. Search URLs look like `/{keyword}-jobs-in-{location}`. — [lordzohar/Naukri-autoapply-bot](https://github.com/lordzohar/Naukri-autoapply-bot)
- Naukri recruiters can attach questionnaires and custom questions to a job. Candidates are interrupted with them during apply. — [Naukri recruiter FAQ](https://recruiterfaq.naukri.com/2016/09/16/job-posting-questionnaires), [Custom Questions](https://recruiterzone.naukri.com/custom-questions-with-job-posting), [Auto-generated questionnaire](https://recruiterzone.naukri.com/?p=5721)
- The JobPilot Chrome extension says it "falls back to a contenteditable chatbot flow" on Naukri. It matches fields to resume data with regex maps. It sets values through native setters plus synthetic React events, waits for the form to settle with a MutationObserver, and answers free-text questions with an LLM. — [JobPilot write-up](https://mahi.is-a.dev/work/jobpilot)
- A Chrome extension notes that bulk apply keeps asking the same questions, such as notice period and expected CTC. — [Naukri Auto-Fill Assistant](https://chromewebstore.google.com/detail/naukri-auto-fill-assistan/iggoogkgadebfnoaepgpodmpegfiahje) (from search summary)
- On the beatwad bot, Indeed Easy Apply forms are auto-filled from your Indeed on-site profile (work history, education, skills, desired salary). A fuller profile means fewer questions go to the LLM. A flag chooses between the on-site resume and an uploaded one. — [beatwad/LinkedIn-AI-Job-Applier-Ultimate](https://github.com/beatwad/LinkedIn-AI-Job-Applier-Ultimate)
- Another Indeed bot repo claims a SmartApply handler that detects a new tab and an iframe. I did not verify this. — [RayeesYousufGenAi/multi-platform-job-apply-bot](https://github.com/RayeesYousufGenAi/multi-platform-job-apply-bot) (search summary only)

### Inferences
- The Naukri chatbot is a contenteditable message box, not ordinary `<input>`s. Typing with real keystrokes plus waiting for each bot message is more likely to work than setting `.value`. This matches JobPilot's approach and FresherPilot's existing contenteditable support in `content.js`.
- The generic page-state approach already in `applybot/snap.py` (read fields and buttons, no AI) fits better than hardcoded selectors, because Naukri uses hashed classes.

### Gaps
- Chatbot question types, answer formats (chips, radio, free text), and the DOM container names. I found no source.
- Indeed smartapply step list and question types. I found no source.
- Network endpoints for either flow.

## Telling easy apply from "apply on company site"

### Takeaway
Use the button label, then confirm by whether the click leaves the board's domain. No single DOM attribute is documented for either site.

### Cited Findings
- Naukri: the button text "Apply on company site" marks an external redirect. Naukri's own bot treats it as leaving naukri.com. The same repo says many jobs now redirect to company career sites. — [lordzohar repo](https://github.com/lordzohar/Naukri-autoapply-bot)
- Indeed: "Apply now" is Indeed's on-site form. "Apply on company site" redirects to the employer's career site. — [Careerist](https://support.careerist.com/knowledge/how-to-use-indeed), [Indeed help](https://support.indeed.com/hc/en-in/articles/115002786323)
- Apify Indeed scrapers expose this as data. One has `applyType` with values "Easy Apply" or "CS Apply". Another has `applyUrlStatus: "external"` plus an `atsProvider`. Some Indeed Apply links never expose an external URL. — [trakk actor](https://apify.com/trakk/indeed-jobs-intelligence-scraper)
- beatwad's bot says the vast majority of Indeed listings redirect to external sites, which it cannot reliably handle. — [beatwad](https://github.com/beatwad/LinkedIn-AI-Job-Applier-Ultimate)

### Inferences
- Cheap pre-filter: the scraper already collects jobs. If the Apify/jobspy output carries an apply-type or external-URL field, store it at ingest so the apply step knows the type before opening a tab.
- Rule at apply time: label contains "company site" means external; anything else on an Indeed or Naukri domain after the click means on-platform.

### Gaps
- Stable attributes (data-testid, ids) for either button. Not found.
- Naukri API field for easy vs external apply. Not found.

## Open-source bots, bot detection, login, OTP/captcha

### Takeaway
Existing bots are small and break on markup changes. Indeed shows frequent CAPTCHAs even with stealth patches. Reusing a persistent logged-in browser session is the common login approach.

### Cited Findings
- Naukri bots: lordzohar (Selenium + BeautifulSoup; login via `login.naukri.com`, fields `usernameField`/`passwordField`; fixed `sleep()` waits; no success verification). — [Naukri-Edge.py](https://raw.githubusercontent.com/lordzohar/Naukri-autoapply-bot/main/Naukri-Edge.py). Others: [snapfast/AutoMates](https://awesome.ecosyste.ms/projects/github.com%2Fsnapfast%2FAutoMates), [Naukri-Automation (pnangare10)](https://dev.to/pranesh_nangare_2dff2c3a1/built-a-tool-to-auto-apply-to-jobs-on-naukricom-using-ai-1557). The DEV post has a comment saying "its not working" with no reply.
- Indeed: beatwad's bot uses Patchright (patched Playwright) and claims it defeats Cloudflare and similar systems. It still reports that Indeed "aggressively deploys CAPTCHAs that interrupt automated flows, even with bot-detection bypass techniques," and recommends LinkedIn for automation and Indeed only for search. It keeps a `browser_session` folder; deleting it clears session problems. Indeed login is by email in `.env`. — [beatwad](https://github.com/beatwad/LinkedIn-AI-Job-Applier-Ultimate)
- A plain HTTP request to Indeed returns a Cloudflare security check page. — [ZenRows](https://www.zenrows.com/blog/indeed-scraper) (search summary)
- Reddit thread (Nov 2024, developersIndia): a developer had to reverse engineer Naukri's network calls, found tokens short-lived and login happening in a desktop app, and named captcha as the main obstacle. — [Reddit mirror](https://reddit.birdcat.cafe/r/developersIndia/comments/1gspkgn/share_the_wildest_thing_youve_automated_as_a/lxg0yge) (search summary only)
- Open-source Indeed bots break when Indeed changes form markup. Complex employer portals are the usual gap. — [LoopCV blog](https://blog.loopcv.pro/indeed-auto-apply-bot/amp/) (a vendor with a commercial interest)

### Inferences
- Akamai on Naukri: no source found confirming it. Do not assume it. Observed behaviour per sources is token-gated job API and recaptcha for plain HTTP.
- Practical stack: headed or Patchright browser with a persistent profile, logged in once manually (this also avoids OTP). Pause and notify via Telegram on captcha or OTP, which `applybot` already does for portals.
- Datacenter runners (GitHub Actions) are likely to meet more CAPTCHAs on Indeed than a residential laptop. This is an inference; no source measured it.

### Gaps
- No evidence on Akamai specifically. No source on OTP handling for Naukri or Indeed login.

## Rate limits, ban risk, success verification, already-applied

### Takeaway
Naukri has a daily apply quota, reported around 100 per day, and a detectable quota message. Neither site publishes ban thresholds. Verification must be done by reading the page after submit, since the reference bot does not.

### Cited Findings
- lordzohar's README says Naukri allows about 100 applications per day, defaults to 50, and warns that excessive automation may lead to account restrictions. The bot detects the text "Your daily quota has been expired." and stops. — [repo](https://github.com/lordzohar/Naukri-autoapply-bot), [Naukri-Edge.py](https://raw.githubusercontent.com/lordzohar/Naukri-autoapply-bot/main/Naukri-Edge.py)
- That bot counts a job as applied when the click succeeds, with no post-submit check. — [Naukri-Edge.py](https://raw.githubusercontent.com/lordzohar/Naukri-autoapply-bot/main/Naukri-Edge.py)
- Session-driving tools expose the account to detection of automated activity. The source gives no thresholds. — [LoopCV](https://blog.loopcv.pro/indeed-auto-apply-bot/amp/)
- Naukri's terms restrict automation (stated in a search summary, terms page not read). Naukri sells its own auto-apply agent, Neo, in the Naukri360 plan. — [Naukri Neo](https://www.naukri.com/naukri360/neo-auto-apply-job-agent)

### Inferences
- Verify success with a positive signal (a "applied" confirmation text, or the apply button turning into a disabled "Applied") rather than a click. FresherPilot's CLAUDE.md already warns to take "Already applied" only from a button, not nav links.
- Keep volume far below 100 per day and add random pauses.

### Gaps
- Indeed per-day limits, ban reports with numbers, Naukri success-message text, "already applied" markup for both.

## Internal APIs versus UI automation

### Takeaway
Not practical. No public apply API exists, tokens are short-lived and bound to the browser, and plain HTTP gets a captcha.

### Cited Findings
- There is no public Naukri developer API. Integrations are commercial deals. A guide says community "JSON API" projects hit Naukri's internal endpoints, and plain HTTP scrapers get a recaptcha error because the job API is gated behind an in-browser token. — [JobsPipe guide](https://jobspipe.dev/blog/naukri-api), [Reddit mirror](https://reddit.birdcat.cafe/r/developersIndia/comments/1gspkgn/share_the_wildest_thing_youve_automated_as_a/lxg0yge) (both via search summaries, not read in full)
- Indeed returns a Cloudflare check page to plain requests. — [ZenRows](https://www.zenrows.com/blog/indeed-scraper)
- I found no documentation of a Naukri apply endpoint or payload.

### Inferences
- Stay with UI automation in a real browser. Network capture (via the Chrome tool's `read_network_requests`) is useful for learning the chatbot's request shape and for verifying success, not for replaying calls.

### Gaps
- The actual apply request and payload for either site. Would need live traffic capture.

## Suggested small problems for the writer
1. Classify the job as easy or external before opening a tab (apply-type field, button label).
2. Naukri button click, then detect which UI appeared: chatbot, inline form (CUSTOM-FIRSTNAME style), or redirect.
3. Chatbot loop: read last bot message, answer by the answer bank, send with real typing, wait for the next message.
4. Indeed smartapply: step loop using page-state reading, with profile prefill reliance.
5. Success and already-applied detection from page text and button state.
6. Quota and CAPTCHA handling: stop, notify, resume.
7. Session persistence with a manually logged-in profile.
