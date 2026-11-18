# Career-site ATS application automation with Playwright (India fresher focus, 2026)

Research caveat: web search in this session returned mostly vendor blogs and little primary technical material. Items marked "(prior knowledge)" in Inferences are NOT sourced from this session and should be verified against live pages before being built on.

## Per-ATS flow and quirks (Workday, Taleo/Oracle, SuccessFactors, iCIMS, Greenhouse, Lever, Ashby, SmartRecruiters, Zoho, Phenom, Eightfold, Indian company portals)

### Takeaway
Workday is the dominant multi-page, account-gated ATS among large employers (and Wipro reportedly uses it); Greenhouse/Lever/Ashby/SmartRecruiters are open and simple. Little primary documentation of Workday apply-form selectors was found; `data-automation-id` is the confirmed stable-ish hook.

### Cited Findings
- Workday elements carry `data-automation-id`, `data-uxi-element-id`, `data-uxi-widget-type` attributes, used by Nexthink to target Workday dropdowns — [Nexthink docs](https://docs.nexthink.com/platform/user-guide/adopt/guide-creation-and-management-from-nexthink-applications/configuring-adoption-settings/use-case-element-selector-for-workday)
- An open-source Playwright project for Workday HCM uses `[data-automation-id="..."]` CSS selectors (reporting tasks, not applications; 1 star, treat as example) — [awesome.ecosyste.ms listing](https://awesome.ecosyste.ms/projects/github.com%2FBrowser-Automation-Hub%2Fworkday-hcm-browser-automation)
- Playwright's default test-id attribute is `data-testid`, so Workday needs plain attribute selectors or `testIdAttribute: 'data-automation-id'` config — [Playwright patterns guide](https://www.skills.lc/ed3dai/ed3d-plugins/ed3dai-ed3d-plugins-plugins-ed3d-playwright-skills-playwright-patterns-skill-md)
- Typical Workday apply pages: contact info, employment history, education, job-specific questions, then review; autofill from resume helps but screening questions (salary, availability, work authorization, consent) are often not covered — [JobWizard](https://jobwizard.ai/blog/how-to-automate-workday-job-applications-with-a-chrome-extension) (vendor blog)
- Workday resume parsing is confused by tables, multi-column layouts, icons, contact info in headers/footers; MM/YYYY dates recommended — [Scale.jobs](https://scale.jobs/blog/cheap-ai-apply-tools-fail-workday-applications) (promotional; its statistics are unsourced)
- A job-apply plugin notes radio buttons in screening questions often use custom overlays that intercept clicks — [search summary of skillsmp job-apply skill](https://skillsmp.com/skills/neonwatty-job-apply-plugin-skills-job-apply-skill-md)
- Greenhouse, Lever, Ashby, SmartRecruiters publish open job-board APIs (no key); Workday's job API caps `limit` at 20; Taleo, Oracle Cloud Recruiting, Phenom, iCIMS are session-bound JS-heavy portals with no public feed (35 of 42 tested Gulf employers unreachable) — [dev.to 42 employers](https://dev.to/get_anything/i-tested-42-large-employers-to-see-which-ones-you-can-actually-scrape-only-7-worked-535e)
- Market share among 305 top employers (Nov 2026 crawl, estimates): Greenhouse 37.7%, Workday 24.6%, Oracle HCM 7.5%, Lever 7.5%, Phenom 3.6%, Ashby 3.6%, SuccessFactors 2.3%, SmartRecruiters/Eightfold 1% each, iCIMS 0.7% — [ResumeGeni](https://resumegeni.com/research/ats-market-share-2026) (curated set, skews to tech/US)
- Indian IT: Wipro reportedly migrated to Workday; Infosys uses SAP SuccessFactors for lateral hiring plus its own InfyTQ for campus; TCS reportedly Taleo (uncorroborated); Cognizant/Accenture ATS not found — [JobRise](https://jobrise.io/en/ats-checker/wipro/), [Unstop](https://unstop.com/blog/infosys-recruitment-process) (secondary vendor sources)
- LazyApply-like tools are claimed to often skip Workday and Taleo (promotional claim) — [Scale.jobs](https://scale.jobs/blog/cheap-ai-apply-tools-fail-workday-applications)

### Inferences
- (prior knowledge, verify) Workday: accounts are per tenant (each company host needs its own account), flow = Apply > Autofill with Resume / Apply Manually / Use Last Application > Create Account or Sign In > "My Information" > "My Experience" > "Application Questions" > "Voluntary Disclosures" > "Self Identify" > Review > Submit. Common ids: `createAccountSubmitButton`, `bottom-navigation-next-button`, `legalNameSection_firstName`, `file-upload-input-ref`, `adventureButton` (Apply). Dropdowns are button+listbox popups (click the button, then click `[role=option]`); date fields are segmented MM/YYYY inputs; many pages need explicit waits after Next. Not confirmed by sources found here.
- Greenhouse/Lever/Ashby forms are single-page, no account; Ashby/Greenhouse often add reCAPTCHA/hCaptcha; SmartRecruiters has an OneClick/profile flow. Easiest first playbooks for a fresher pipeline. (prior knowledge)
- Since the user's pipeline already treats target-company jobs via `applybot`, the highest-value order is: Greenhouse > Lever > Ashby > SmartRecruiters > Workday (big payoff, hardest) > SuccessFactors/Taleo/iCIMS/Oracle (session-bound, per-tenant quirks, expect `needs_you`).

### Gaps
- No primary source for Workday apply-page selectors, Zoho Recruit, Phenom, Eightfold, iCIMS, Taleo, SuccessFactors application-form flows, or TCS iON/Cognizant/Accenture/IBM portals.
- No verified current ATS for TCS, Cognizant, Accenture, IBM.

## Detecting the ATS from a URL or page

### Takeaway
Host name is the fastest fingerprint; for vanity career domains, regex the HTML (script/stylesheet URLs, outbound apply links) for vendor strings. Detection does not imply the apply form is automatable.

### Cited Findings
- Hosts: Workday `*.wdN.myworkdayjobs.com/<site>` (regex `([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/([\w-]+)`), iCIMS `icims.com`, Taleo `taleo.net` and sometimes `oraclecloud.com`, SuccessFactors `career.sap.com`/`successfactors.eu`/`jobs2web.com` (least certain) — [search synthesis of Apify ATS detectors](https://apify.com/forevertools/ats-company-jobs.md), [coregent detector](https://apify.com/coregent/career-page-discovery-ats-detector)
- For skinned sites, view source and search for `workday`, `greenhouse`, `icims`, `taleo`, `successfactors` in script/stylesheet URLs — [withresumeai](https://withresumeai.com/ats-checker/how-to-find-ats)
- Some detectors miss Workday, iCIMS, Taleo and in-house sites; several scrapers mark SmartRecruiters/iCIMS/SuccessFactors/Jobvite/Taleo as detected-but-unsupported — [Apify pulselab](https://apify.com/pulselab/company-jobs-checker.md)

### Inferences
- (prior knowledge) Other host patterns: `boards.greenhouse.io`/`job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `jobs.smartrecruiters.com`, `*.zohorecruit.in/.com`, `*.phenompeople.com`, `*.eightfold.ai`, `*.fa.<dc>.oraclecloud.com/hcmUI/CandidateExperience`. Playbook router should follow redirects (`page.url` after load) and check for embedded iframes (Greenhouse `?gh_jid=` embeds on company sites).
- Resolve LinkedIn/company links to the final apply host first, then dispatch to a playbook by host, with generic engine as fallback.

### Gaps
- No authoritative DOM-fingerprint list per vendor found.

## Account creation, passwords, email verification and OTP

### Takeaway
Two workable patterns: poll Gmail API/IMAP for the code, or ask the owner via Telegram and wait. The user's existing design (per-host HMAC password + Telegram code/link relay) matches common practice; use retry-with-timeout loops, not fixed sleeps.

### Cited Findings
- Playwright email-verification bots commonly fetch the code via Gmail API and type it; recommended approach is a retry-and-timeout polling loop for delivery delay — [dev.to email verification bots](https://dev.to/francofuji/email-verification-bots-with-playwright-1dc7)
- A Telegram-bot + Flask + Playwright system sends a captcha image to the user, waits for the reply, then resumes (same pause/resume pattern applies to OTP) — [Contra post](https://contra.com/community/sHVJceck-i-built-an-automation-system-that)
- Mailslurp-style disposable inboxes offer blocking "wait for email" calls — [MailSlurp](https://www.mailslurp.com/guides/test-sms-otp-mfa-using-playwright/)

### Inferences
- (prior knowledge) Gmail via IMAP app password or Gmail API with a refresh token can read verification mails on GitHub Actions without a human; filter by sender domain and received-after timestamp, extract link or 6-digit code by regex. Use a dedicated mailbox or Gmail plus-addressing/label to scope reads. Telegram path: runner posts "need code for host X", Worker stores reply keyed by job id, runner polls the Worker (already in the user's `applyTelegram`). Add expiry/retry ("resend code") and cap waits (e.g. 10 min) then mark `needs_you`.
- Verification links must be opened in the same browser context/IP where possible; some Workday tenants only require clicking the link once, then sign-in.

### Gaps
- No source on Workday tenant-specific verification behaviour (link vs code, expiry).

## Robust Playwright techniques, headless on GitHub Actions, CAPTCHAs

### Takeaway
`fill()` sets value and fires `input`; for masked/React fields use keystroke typing. GitHub runner IPs are datacenter IPs that Cloudflare-style protections tend to distrust; no reliable free fix exists.

### Cited Findings
- `locator.fill` focuses, sets value and triggers an `input` event; for fine-grained keyboard events use `pressSequentially`; `frameLocator` enters iframes — [Playwright Locator docs](https://playwright.dev/docs/api/class-locator)
- `dispatchEvent` creates synthetic events even on hidden elements — [Playwright Locator docs](https://playwright.dev/docs/api/class-locator)
- Reports that CI runners (GitHub Actions, GitLab, Hetzner, OVH, DO) are on an "elevated risk" list for Cloudflare Turnstile; headless fingerprints plus datacenter IP got 403s — [dev.to arsonxdev](https://dev.to/arsonxdev/i-tried-every-headless-browser-to-solve-cloudflare-turnstile-only-one-worked-1j20), [capsolver blog](https://capsolver-website-nuxt.pages.dev/blog/cloudflare/playwright-blocked-by-cloudflare-turnstile-causes-fix) (vendor/third-party; not Cloudflare-published)
- Suggested mitigations: residential proxies, TLS/fingerprint matching, stealth plugins (inconsistent), persistent contexts — [Browserless](https://browserless.io/blog/bypass-cloudflare-with-playwright)

### Inferences
- (prior knowledge) Playwright mouse/keyboard/`click`/`type` produce trusted (isTrusted) events; `dispatchEvent`/JS value setting produces untrusted ones, which some validators ignore. Playwright CSS/text locators pierce open shadow DOM automatically; closed shadow roots do not. File upload: `setInputFiles` on the `input[type=file]` or `page.waitForEvent('filechooser')` for custom buttons. Date pickers: type into segmented inputs rather than clicking calendars. Custom dropdowns: click opener, wait for `[role=option]`, match text, verify displayed value after. Stuck detection: hash of (url, visible field values, error texts) unchanged across N iterations. Save screenshot + HTML on every failure (never log typed values, repo is public).
- Given the user's setup (headless Chromium on GitHub runners), expect CAPTCHA/Turnstile portals to be `blocked`; either route to `needs_you` with a deep link, or run those from the laptop headed. CAPTCHA-solving services exist but add cost and ToS risk.

### Gaps
- No 2026 source confirming a documented Cloudflare policy against GitHub-hosted runners.
- Shadow DOM and `setInputFiles` docs not retrieved in this session.

## Failure points in open-source universal application agents

### Takeaway
Little specific failure data found. Evidence is that generic/LLM agents struggle with custom controls and multi-step enterprise forms; Workday is repeatedly named as the hard case.

### Cited Findings
- Skyvern's cookbook loops over jobs with `continue_on_failure: true` so one failed application does not stop the run; credentials are injected without exposure to the LLM — [Skyvern cookbook](https://www.skyvern.com/docs/cookbooks/job-application-filler)
- Skyvern claims handling of dropdowns, checkboxes, uploads and validation errors, but no independent Workday benchmarks found — [Skyvern blog](https://blog.skyvern.com/automate-form-filling-with-skyvern-ai-browser-automation)
- Autofill can shift dropdown values and truncate pasted text — [JobWizard](https://jobwizard.ai/blog/workday-auto-apply-review-first-autofill)
- "Rapid submission times and repetitive field entries" may flag applications as spam — [Scale.jobs](https://scale.jobs/blog/cheap-ai-apply-tools-fail-workday-applications) (promotional)
- Custom radio overlays intercept clicks in agent-driven apply attempts — [skillsmp job-apply skill](https://skillsmp.com/skills/neonwatty-job-apply-plugin-skills-job-apply-skill-md)

### Inferences
- Lessons to apply: per-job failure isolation; deterministic playbooks for known ATS with AI only for unknown required fields (already the user's design); read-back verification of each field; humanlike pacing.

### Gaps
- AIHawk issue tracker content (e.g. issue #454) and browser-use/LazyApply failure reports were not retrievable; no sourced list of fixes.

## Success verification and dry-run

### Takeaway
No sourced best-practice found; the user's `apply_dry` default is sound.

### Cited Findings
- None retrieved from sources.

### Inferences
- (prior knowledge) Verify submission by: confirmation text/URL change ("Application submitted", "Thank you"), disappearance of Submit, confirmation email via the same Gmail/IMAP reader, and re-opening the job to see "Applied"/"Already applied" from a button. Dry-run = run through every page, screenshot the Review page, never click final Submit; promote per-ATS to live only after N clean dry runs.

### Gaps
- No external source on verification patterns; per-ATS confirmation strings not collected.
