# Architecture patterns for a two-pipeline job-application automation system

(Research depth: ~7 searches, search-result snippets only, no full-page fetches. Sources are mostly vendor blogs; treat numbers as rough.)

## 1. Deterministic-first / AI-fallback layering, per-site playbooks vs generic agents

### Takeaway
Sources converge on a hybrid: deterministic scripts for known steps, a model only for ambiguity or repair, and a loud signal when a deterministic contract breaks. Pure agents cost far more and are slower; pure scripts are cheap but need maintenance.

### Cited Findings
- Skyvern 2.0 uses a Planner (goal + working memory), Actor (narrow goal execution) and Validator (asserts goal achieved, feeds back); reported WebVoyager accuracy ~45% single loop -> ~68.7% with Planner -> ~85.85% with Validator (secondary summary; check the official blog) — [Skyvern blog](https://blog.skyvern.com/skyvern-2-0-state-of-the-art-web-navigation-with-85-8-on-webvoyager-eval)
- Stagehand caches successful act() calls (key = hash of instruction, URL, selector, action) and replays with no LLM; cache miss -> inference. Official doc: replay runs with self-healing off, and if the recorded selector no longer resolves it falls back to inference. Small runtime-state differences change the accessibility tree and thus the cache key. Mintlify-hosted pages claim it "self-heals", which conflicts with the official doc — [Stagehand caching](https://docs.stagehand.dev/best-practices/caching); [deterministic agent](https://docs.stagehand.dev/best-practices/deterministic-agent); contradicted in wording by [Mintlify mirror](https://www.mintlify.com/browserbase/stagehand/concepts/caching)
- Cost/speed (vendor blogs, no independent benchmark): Playwright ~a few dollars per 10k ops vs $200-3,000 for Browser Use; ~3 s deterministic vs ~20 s agent run; hand-written Playwright 98% vs Browser Use 89.1% vs Stagehand agent 75% on one guide's WebVoyager figure; 15-25% of scripts break within 30 days of site updates — [Scrapfly](https://scrapfly.io/blog/posts/browser-use-vs-playwright); [noqta](https://noqta.tn/blog/ai-browser-agents-browser-use-stagehand-web-automation-2026)
- Hybrid pattern: agent explores a new flow, the repeated part becomes a script; a repair agent handles only failures; a fully agentic flow can route around a site change and hide it, while a hybrid flags that the deterministic contract broke — [alexcloudstar](https://alexcloudstar.com/md/blog/self-healing-playwright-ai-browser-automation-2026/); [Tinyfish](https://current.tinyfish.ai/issue/6/foundations/article/5568/browser-automation-vs-web-agents)

### Inferences
- The existing engine already matches this: snap.py -> classify.py -> actions.py with AI only for required unknown fields. Keep AI out of navigation; use it for (a) unknown required fields and (b) a "page-unclassified" fallback that proposes one action, which is logged and, if it worked, promoted to a playbook rule/fixture.
- Make each page-state classifier a pure function `snapshot_json -> state` so it is testable offline with no browser.
- Decomposition into independently testable problems: (1) job classification, (2) page snapshot, (3) page classification, (4) field-to-answer mapping, (5) action execution per field type, (6) per-site step transitions, (7) human-in-loop channel, (8) result/health reporting.
- Skyvern's Validator maps to a post-action check: after each action assert the expected change (field value readback, new page state, error list empty) before continuing.

### Gaps
- No independent head-to-head benchmark for job-application automation specifically; numbers above are generic web navigation.
- Skyvern/browser-use/AIHawk form-fill internals not read in depth.

## 2. Job classification (easy vs external)

### Takeaway
No sources found on this specific problem; recommendations are inference. Decide from the source board's structured signals first, open the page only if ambiguous.

### Cited Findings
- None directly sourced.

### Inferences
- Signal order: (1) source board + per-board rule table (Naukri "Apply on company site" vs "Apply"; LinkedIn "Easy Apply" vs "Apply"; Indeed smartapply vs external; Internshala/Wellfound on-platform); (2) apply-URL host: board's own domain -> easy, ATS host (greenhouse, lever, workday, ashby, smartrecruiters, icims) -> external; (3) only then render the page and read the apply button text/aria-label/href.
- Store the class with evidence (`class`, `signal`, `url_host`) for audit; unknown -> third bucket `needs_check`, never silently one pipeline.
- Test as a table-driven unit test on a golden set of ~50 labelled saved job records per board. Explicit fallback: an easy attempt that redirects off-platform reclassifies to external and enqueues.
- Cache per (board, job id) so reruns are deterministic.

### Gaps
- Uncited; verify per board on real pages (LinkedIn guest pages hide the company link, per project notes).

## 3. Testing strategy

### Takeaway
Test each layer on recorded data, not live sites: snapshot fixtures for classifiers, HAR replay or a mock portal for flows, dry-run in production, plus a few canaries.

### Cited Findings
- Playwright best practices: isolate tests (own state/storage/cookies), prefer user-facing locators such as getByRole — [Playwright best practices](https://playwright.dev/docs/best-practices)
- HAR record/replay: `page.routeFromHAR` with `update: true` to record, omit to replay; an unmatched URL+method+payload throws; set `serviceWorkers: 'block'` when relying on HAR (third-party tutorial; verify in official docs) — [Steve Kinney](https://stevekinney.com/courses/self-testing-ai-agents/recording-hars-for-network-isolation)
- Canaries: hand-verified known records re-checked every run are "the cheapest high-signal check"; one example runs canaries every four hours and saves failure artifacts — [Tap blog](https://taprun.dev/blog/health-contracts-catch-silent-failures.html); [DEV: 1-in-3 rule](https://dev.to/taranpreet_kaur_4b538d878/the-1-in-3-rule-what-actually-breaks-in-a-scraping-pipeline-after-90-days-39ai)

### Inferences
- Fixture layers: (a) `snap.json` + expected `state` per step per site (classifier tests, ms); (b) saved HTML pages served by a local mock server, driven by the real engine (step tests); (c) HAR/mock multi-step flow (acceptance: reaches "submitted" in dry mode); (d) weekly live dry-run canary per site, stopping before Submit.
- Auto-capture snapshot + screenshot + HTML on every unclassified/stuck page so each production failure becomes a regression fixture.
- Failure taxonomy (suggested): classify_unknown, field_unmapped, field_fill_failed, validation_error_loop, auth_required, otp_timeout, captcha, closed_posting, already_applied, redirected_offsite, stuck_timeout, site_blocked. Log code + step + screenshot + snapshot, never typed values (public repo).
- Acceptance test per problem = pass/fail on fixtures, e.g. "classifier labels 40/40 saved Workday pages".

### Gaps
- No source on mock-portal frameworks; standard practice, uncited.

## 4. Answer bank and unknown-field handling

### Takeaway
No directly relevant source; design is inference from the existing answerbank.py.

### Cited Findings
- AIHawk reporting: users told Business Insider the tool added false information into their resumes (risk of free-form AI answers); automated Easy Apply often never reaches a human because of knockout screening questions (blog) — [Business Insider NL](https://www.businessinsider.nl/a-free-ai-tool-can-help-you-apply-to-hundreds-of-jobs-per-day-users-said-there-are-risks-but-theyre-worth-it/); [Scoutify](https://scoutify.com/blog/linkedin-auto-apply/)

### Inferences
- Structure: canonical key (`notice_period_days`, `current_ctc_lpa`, `expected_ctc_lpa`, `current_location`, `relocate`, `work_auth`...) -> value; label patterns per key; option aliases for dropdowns/radios ("Immediately" ~ "0 days"); type-aware formatting (number vs "6 LPA").
- Resolution order: exact label -> pattern -> high-threshold fuzzy -> (required only) AI constrained to choose from the bank/options and checked against profile facts -> else park and ask via Telegram -> else skip the job. Never guess required fields.
- Log every unknown normalized label with a count; review weekly and promote the top ones. AI must never invent numeric/legal facts (CTC, years, work auth).

### Gaps
- No sourced accuracy benchmarks for form question answering.

## 5. Keyboard-driven ("vim-style") automation: more reliable?

### Takeaway
Weak evidence that keyboard flows are more reliable; Playwright docs suggest they are less self-checking than locator actions. Use keyboard for specific cases (comboboxes, widgets that ignore programmatic fill), not as the backbone.

### Cited Findings
- `locator.press` focuses first; `page.keyboard.press` does not, so Tab/Enter flows depend on the correct element already being focused — [Playwright input docs](https://playwright.dev/docs/input)
- Locator `click` runs actionability checks; keyboard press has no equivalent pre-check; `force` bypasses checks — [Playwright input docs](https://playwright.dev/docs/input); [Checkly](https://checklyhq.com/learn/headless/basics-clicking-typing/)
- If `fill` leaves a field empty while typing works, the page listens for key events and `pressSequentially` is the fix; insertText-style input fires no key events — [Hyperping](https://hyperping.com/learn/playwright/playwright-forms-and-inputs)
- The searches did NOT confirm whether click/keyboard events are `isTrusted`; verify with a listener.

### Inferences
- No evidence found that Tab-order navigation beats role/label locators; Tab order varies by site (hidden/skip links) and breaks silently when the DOM changes. Locator actions with actionability checks fail loudly, which is better for observability.
- Practical rule: locate via role/label (snap.py `data-fp` stamps), act with real mouse/keyboard events (`click`, `press_sequentially`), verify by readback; fall back to keyboard (focus + type + ArrowDown + Enter) for custom comboboxes. Any speed gain is likely small versus network waits; measure first.
- Vimium-style hints are a human-assist technique; the automation equivalent is the stamped `data-fp` ids.

### Gaps
- No studies or engineering posts comparing keyboard vs selector reliability; LinkedIn sensitivity to keystroke timing not found.

## 6. Human-in-the-loop via Telegram (OTP, captcha, approval)

### Takeaway
No sources found; patterns below are inference.

### Cited Findings
- None.

### Inferences
- Model as a persisted state `waiting_human(kind, job_id, deadline)` in D1/queue, not runner memory, so the runner can exit and resume (a runner blocked on OTP wastes minutes).
- Request message: job, site, screenshot, unique request id; match replies by reply-to message id, not "latest message", to avoid cross-job mixups. Timeouts: OTP ~3-5 min (codes expire) with one resend then park as `needs_you`; captcha -> park immediately with link; approval -> default skip.
- Idempotent resume: on resume re-snapshot and reclassify rather than replay clicks.
- Rate-limit prompts: instant only for OTP, daily digest for approvals.

### Gaps
- Uncited; check the Telegram Bot API docs for reply handling.

## 7. Observability: success dashboards, stuck detection, circuit breakers

### Takeaway
Track success per (site, step) rather than HTTP success; trip a per-site breaker on rising failure/unclassified rates; keep a canary per site.

### Cited Findings
- Error-budget breaker: shut down when failure rate crosses a threshold (example 10%); schema validation as a breaker — [DEV: resilient DOM selection](https://dev.to/anderecit/future-proofing-your-scrapers-strategies-for-resilient-dom-selection-1j4f); [Evomi](https://evomi.com/blog/why-your-scrapers-are-flying-blind-(and-how-to-fix-that))
- Selector fallback chains: log when a lower-priority selector is used ("canary in the coal mine"); HTTP 200 is not success (consent walls, challenge pages); watch field fill rates and null-rate jumps (example 2% -> 40% = lost selectors or soft-blocking) — [DEV: dynamic selector fallbacks](https://dev.to/withatte/dynamic-selector-fallbacks-how-to-scrape-e-commerce-sites-that-change-frequently-2de8); [DEV: 1-in-3 rule](https://dev.to/taranpreet_kaur_4b538d878/the-1-in-3-rule-what-actually-breaks-in-a-scraping-pipeline-after-90-days-39ai)
- Account risk: AIHawk's author had LinkedIn access restricted; LinkedIn's agreement bans automation and can restrict accounts; one user estimated ~250 Easy Apply/day as a ceiling — [Business Insider NL](https://www.businessinsider.nl/a-free-ai-tool-can-help-you-apply-to-hundreds-of-jobs-per-day-users-said-there-are-risks-but-theyre-worth-it/); [Scoutify](https://scoutify.com/blog/linkedin-auto-apply/)

### Inferences
- Minimal solo implementation: one D1 table `apply_events(ts, site, job_id, step, state, outcome, taxonomy, duration)`; `/applystatus` adds a per-site success line.
- Stuck detection: same (state, snapshot hash) N times, or step time over limit -> abort with screenshot (4x repeat rule exists).
- Breaker: per site, if >=3 of last 5 attempts fail with classify_unknown/field_fill_failed, pause that site's queue and alert; half-open: one canary retry after cooldown; auto-capture fixtures on trip.
- Keep LinkedIn Easy Apply volume conservative and human-paced because of account-restriction risk.

### Gaps
- No application-specific breaker thresholds found; the ones above are inference.
