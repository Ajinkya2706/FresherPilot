# Automating apply flows on Internshala and Wellfound (as of Nov 2026)

Evidence is thin. I found no authoritative DOM documentation for either site, and no Internshala terms or ban reports. The best primary source is the wellfound-bot README. Your own live-tested selectors in CLAUDE.md are stronger evidence than anything below.

## Apply flow steps, DOM structure, question types and how to fill each

### Takeaway
Wellfound is a modal with a note (cover-letter-like) and "Send Application", and it cannot be undone. Internshala is a form with a cover letter ("why hire you"), optional assignment answers, and sometimes availability. I found no public selector documentation for either; the open-source bots confirm only the high-level flow.

### Cited Findings
- Wellfound apply: sign in, press Apply on the posting, write a note "akin to a cover letter" in the pop-up, press Send Application. This shares the job profile and any resume, and cannot be undone. Applications expire after two weeks of inactivity. The article says nothing about screening questions or external apply. — [Wellfound help: How do I apply](https://help.wellfound.com/article/769-how-do-i-apply-to-a-job)
- Wellfound's GraphQL apply is two steps: a read-only `JobApplicationModal` query resolves `startupId` and the screening questions, then a `CreateJobApplication` mutation sends the application. The wf_apply.py client refuses to proceed if a required screening question is unanswered. So screening questions do exist in the data model. — [wellfound-bot README](https://github.com/apoorvdarshan/wellfound-bot)
- Internshala: if an internship requires answers to specific questions, they are listed in the description under a separate section. The form has a separate upload button for answers in .doc/.pdf/.rtf. The blog says not to upload your CV or cover letter there. — [Internshala blog](https://internshala.com/blog/how-not-to-apply-for-an-internship-3/) (as surfaced by search; the blog is old)
- Internshala asks "Why should you be hired for this internship?" on every application (third-party guide). The blog warns against generic pasted letters. Availability should be stated in the application and profile (third-party guides). — [Internshala blog: successful application](https://internshala.com/blog/how-to-make-a-successful-internship-application-on-internshala/)
- The PyPI internshala-bot flow: generates a cover letter with ChatGPT from the resume plus the listing description and required skills, adds the listing's required skills to the Internshala resume, then answers the assignment questions below the cover letter. It skips an assignment if it contains a URL or asks for personal info (LinkedIn/GitHub links), saves the cover letter in `reports/` as a failure, and has a `--skip` flag to disable the check. — [PyPI internshala-bot](https://pypi.org/project/internshala-bot/)
- That same bot also lists fake-listing filtering (employer hiring and posting history) as a feature, without detail. — [Eviltr0N/internshala-bot](https://github.com/Eviltr0N/internshala-bot)
- applybot (notDEVANG) fills forms and submits with AI-generated cover letters (Groq llama-3.3-70b). I could not see its selectors. — [notDEVANG/applybot](https://github.com/notDEVANG/applybot)

### Inferences
- Treat the Wellfound note as one free-text field and the Internshala "why hire you" as one required textarea. Assignment questions are free text, so route them through your AI step with the full JD.
- Reuse your existing generic-field machinery (`__jfForceFill`, `snap.py`) rather than hardcoding selectors. Both bots' maintenance history shows selectors rot.
- Rule from the bot: skip or hand to the user any assignment that asks for personal links or files.
- Per-question types to prepare: free text (note/cover/why-hire), assignment answers (text, sometimes a file upload), availability (date or radio), screening questions (Wellfound).

### Gaps
- Exact current DOM, selectors, field names and question types for both forms: not documented publicly. Needs a live capture. Your own notes (Wellfound modal `div[role=dialog]`, "Undo m:ss") are the only detail.
- The Internshala availability question's exact wording and control type: only third-party advice found.
- The current Internshala assignment upload flow: the blog source is old.

## Detecting already applied/closed, external-apply vs on-platform

### Takeaway
Little documented. Wellfound's applications tab lists applied jobs. The Internshala scraper exposes `deadlineStatus` (open, closing_soon, expired) as a closed signal. No source documents an external-apply marker for either site.

### Cited Findings
- Wellfound tracks applications in the applications tab on the left-hand side. — [Wellfound help](https://help.wellfound.com/article/769-how-do-i-apply-to-a-job)
- The Internshala scraper actor exposes `deadlineStatus` (`open`, `closing_soon`, `expired`), and monitor mode a `changeType` including `closed`. It has no applied field and no external apply URL field. It reads only logged-out public pages. — [getascraper/internshala-scraper](https://apify.com/getascraper/internshala-scraper.md)
- Wellfound apply data comes from the `JobApplicationModal` query; wellfound-bot resolves the startup and questions from it. — [wellfound-bot](https://github.com/apoorvdarshan/wellfound-bot)

### Inferences
- Closed: parse the deadline or expired text on Internshala, and a missing Apply button on Wellfound. Applied: a disabled "Applied" button or the applications tab, never a nav link (your Nov 12 gotcha).
- External vs on-platform: detect by whether the Apply button opens the modal or navigates off-domain (new tab or `target=_blank`). I did not find a source.

### Gaps
- No source on Internshala's "already applied" DOM markers or external-apply handling.
- No source on how Wellfound marks external-apply jobs.

## Login persistence, bot detection, captcha, rate limits, ban risk

### Takeaway
Wellfound uses DataDome and serves a CAPTCHA to headless browsers; headed Chrome with a persistent real profile worked. Wellfound has an active-applications cap and may ban for spam. Internshala has little visible protection, and no ban reports were found.

### Cited Findings
- Wellfound uses DataDome. In the wellfound-bot README, headless browsers got a CAPTCHA while a headed Chrome with a real profile did not. First login must be manual and visible. Runs should be headed, since headless exposes `HeadlessChrome` in the user agent. The session persists in `user_data/` (includes the `datadome` cookie). — [wellfound-bot](https://github.com/apoorvdarshan/wellfound-bot)
- The same README says the external HTTP client's TLS fingerprint and the `datadome` cookie binding can get requests blocked; run fetches inside the real browser. It reports one run applying to 171 of 178 listings with no DataDome blocks (author's own claim), using batch caps and delays like `--delay 45`, small batches and several short runs a day. — [wellfound-bot](https://github.com/apoorvdarshan/wellfound-bot)
- Apify scraper vendors claim DataDome lets through a fluctuating 5-15% of attempts per IP-session on company pages. They use Camoufox, a residential proxy and a warm-up. These are vendor claims. — [memo23 actor](https://apify.com/memo23/wellfound-jobs-scraper.md)
- An Apify Discord reply suggests Playwright with residential proxies and reusing the DataDome token from XHR. Rebrowser-patches are said to help with DataDome. Anecdotal. — [Apify Discord](https://discord.apify.com/anyone-managed-to-get-past-datadome-r93j2WblLbDG)
- Wellfound caps active applications per candidate. It warns at the limit, and applications expire to free space. The article gives no number. — [Wellfound: application limits](https://help.wellfound.com/article/767-application-limits)
- Wellfound's enforcement FAQ says bans can happen without warning for serious or continued violations, and appeals are often possible. Its code of conduct lists spamming applications as a violation, with no hard numeric limit. Trustpilot reports say bans are tied to the account, not the IP. — [Enforcement FAQ](https://help.wellfound.com/article/1201-community-guidelines-enforcement-faq)
- The wellfound-bot README says automation goes against Wellfound's ToS and can lead to suspension. — [wellfound-bot](https://github.com/apoorvdarshan/wellfound-bot)
- Internshala: an Apify scraper reads public logged-out pages directly, falling back to a datacenter proxy if the connection is refused. No CAPTCHA handling is mentioned. The vendor's claim of minimal bot protection is not independently verified. — [getascraper actor](https://apify.com/getascraper/internshala-scraper.md)
- internshala-bot uses `undetected_playwright` and saves the session after one manual sign-in. — [PyPI](https://pypi.org/project/internshala-bot/)

### Inferences
- Cloud (GitHub runner, datacenter IP, headless) Wellfound apply is unlikely to work given DataDome. Your existing decision to do Wellfound via the laptop extension in the owner's real, logged-in Chrome fits the evidence.
- Keep Wellfound to a few selective applications a day with human-like pacing, to avoid both the active-application cap and spam bans.
- Internshala from a runner: persist the storage state after a manual login. Expect login prompts or OTP; I found nothing on a captcha.

### Gaps
- No Internshala ToS, rate-limit or ban reports found.
- The Wellfound active-application cap number is not stated.
- No independent test of DataDome vs Playwright from a GitHub runner.

## Known open-source bots, breakpoints, and whether internal APIs are practical

### Takeaway
Internshala has several small Playwright bots (Eviltr0N/internshala-bot on PyPI is the most complete) that break when the UI changes. Wellfound has a reverse-engineered GraphQL apply in an educational repo, but it is fragile because of DataDome and TLS binding.

### Cited Findings
- internshala-bot (Apache-2.0, 10 stars, 33 commits): a May 2025 update fixed Internshala UI changes, and version 0.0.6 was yanked for breaking the application process. GUI and extension are still to-do. — [PyPI](https://pypi.org/project/internshala-bot/), [GitHub](https://github.com/Eviltr0N/internshala-bot)
- Other Internshala projects: beingaayush/Internshala-Automation (Puppeteer, auto login and cookie reuse), notDEVANG/applybot (Playwright, Groq), InternSync and Web Scraper Internshala (scrapers only). — [search results via awesome.ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Frohit1kumar%2Finternsync)
- wellfound-bot (MIT; Playwright, curl_cffi, GraphQL): layers are capture-assist, a browser driver with human-like input, GraphQL replay and apply clients, and a batch agent. Dry-run is the default and `--send` sends. Selectors are "best-effort and may break". It recommends re-capturing when the request signature expires. Tag filters use numeric ids resolved through `wf_resolve.py`. — [wellfound-bot](https://github.com/apoorvdarshan/wellfound-bot)
- An older AngelList script exists but is outdated and uses the old product. — [alejandrorioja.com](https://alejandrorioja.com/how-to-apply-to-a-lot-of-jobs-on-angellist-script/)
- AIHawk is a generic bot; I did not confirm Wellfound support. — [AIHawk](https://github.com/feder-cr/jobs_applier_ai_agent_aihawk)

### Inferences
- The Wellfound GraphQL path (`JobApplicationModal` then `CreateJobApplication`) is practical only when called from the logged-in browser context (e.g. fetch from the page or extension), where the cookies and TLS match. It also exposes the screening questions cleanly as data, which is better than DOM scraping. Capture the exact schema live, since signatures expire.
- For Internshala I found no documented internal API. DOM automation is the known approach.

### Gaps
- No Internshala internal apply API documented. Source code of the bots was not readable through my fetches, so their selectors are unknown.
- The dev.to article "I reverse engineered Wellfound" returned 404, so its details are not included.

## Success verification

### Takeaway
No source documents the success signals. The bots write success and failure reports; Wellfound's applications tab is the verification surface.

### Cited Findings
- internshala-bot writes a success report and a failed report under `reports/`. — [PyPI](https://pypi.org/project/internshala-bot/)
- Wellfound applications appear in the applications tab. — [Wellfound help](https://help.wellfound.com/article/769-how-do-i-apply-to-a-job)

### Inferences
- Verify by re-loading the job page and finding a disabled "Applied" button, or by checking the applications list. This matches what you already observed (the Wellfound "Undo m:ss" button, and Internshala's "Already applied").

### Gaps
- No documented success page text for either site.
