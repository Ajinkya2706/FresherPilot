/* Jobs: filter + list (left), job detail (right). Keyboard: j/k move, o open, a applied, v visited, / search, Esc close. */
(() => {
  const { $, $$, esc, I, n, store, bus, api, toast, safeUrl, postedLabel, avatar, when } = FP;
  const O = () => FP.outreach;
  const PAGE = 50;
  let root, offs = [], S, listEl, detEl, kits = {}, tab = "desc", io, shown = [], pageN = PAGE;

  const defaults = () => ({ q: "", quick: store.get("jobsq", "all"), sources: [], sort: store.get("jobs.sort", "newest"), days: store.get("jobs.days", ""), hideVisited: store.get("jobs.hv", false), hideApplied: store.get("jobs.ha", false), pending: store.get("jobs.pending", true), rejected: false, sel: null });
  const days = (j) => (j.posted_days === null || j.posted_days === undefined || j.posted_days === "" ? 999 : +j.posted_days);
  const isNew = (j) => j.status !== "reject" && !j.visited_at;
  const QUICK = [["all", "All"], ["new", "New"], ["strong", "Strong fit"], ["easy", "Easy apply"], ["today", "Today"], ["applied", "Applied"]];
  const quickOk = { all: () => true, new: isNew, strong: (j) => j.ai_fit === "strong", easy: (j) => j.apply_mode === "easy", today: (j) => days(j) <= 0 || /^</.test(postedLabel(j)) || /m ago|h ago|just now/.test(postedLabel(j)), applied: (j) => !!j.application };

  function visible() {
    const q = S.q.trim().toLowerCase(), src = new Set(S.sources), maxd = S.days ? +S.days : null, ok = quickOk[S.quick] || quickOk.all;
    const out = FP.data.jobs.filter((j) => {
      if (j.status === "reject" && !S.rejected) return false; if (j.status === "unchecked" && !S.pending) return false;
      if (S.hideVisited && j.visited_at) return false; if (S.hideApplied && j.application) return false;
      if (src.size && !src.has(j.source)) return false; if (maxd !== null && days(j) > maxd) return false; if (!ok(j)) return false;
      if (q) { const hay = `${j.title} ${j.employer || ""} ${j.company || ""} ${j.location || ""} ${(j.skills || []).join(" ")} ${(j.ai_stack || []).join(" ")}`.toLowerCase(); if (!q.split(/\s+/).every((w) => hay.includes(w))) return false; }
      return true;
    });
    const rank = (j) => (j.status === "keep" ? 0 : j.status === "unchecked" ? 1 : 2), seen = (j) => (j.visited_at ? 1 : 0), fit = (j) => (j.ai_fit === "strong" ? 0 : j.ai_fit === "partial" ? 1 : 2);
    const found = (j) => -Date.parse(j.first_seen || 0) || 0;
    out.sort(S.sort === "fit" ? (a, b) => rank(a) - rank(b) || fit(a) - fit(b) || days(a) - days(b) : S.sort === "found" ? (a, b) => rank(a) - rank(b) || found(a) - found(b) : (a, b) => rank(a) - rank(b) || days(a) - days(b) || seen(a) - seen(b));
    return out;
  }

  /* ---------------------------------------------------------------- chips */
  const fitChip = (j) => (j.ai_fit === "strong" ? `<span class="chip good" title="${esc(j.ai_fit_reason || "")}">${I("sparkle", "sm")} Strong fit</span>` : j.ai_fit === "partial" ? `<span class="chip info" title="${esc(j.ai_fit_reason || "")}">Partial fit</span>` : "");
  function yearsChip(j) {
    if (j.open_to_skilled) return `<span class="chip warn" title="${esc("Lists years but says: " + j.open_to_skilled)}">Lists ${j.ai_years >= 1 ? j.ai_years + "+ yrs" : "years"} · skilled freshers OK</span>`;
    if (j.ai_category === "stretch") return `<span class="chip warn" title="${esc(j.ai_evidence || "")}">Stretch · asks 1 yr</span>`;
    if (j.ai_freshers) return `<span class="chip good">Freshers welcome</span>`;
    if (j.ai_intern_credit) return `<span class="chip warn" title="${esc(j.ai_intern_credit)}">1 yr · internships count</span>`;
    if (typeof j.ai_years === "number") return `<span class="chip ${j.ai_years >= 1 ? "bad" : "warn"}" title="${esc(j.ai_evidence || "")}">Needs ${j.ai_years < 1 ? Math.round(j.ai_years * 12) + " months" : j.ai_years + "+ yr"}</span>`;
    return "";
  }
  const company = (j) => j.employer || j.company || "Company not disclosed";

  /* ---------------------------------------------------------------- list */
  function itemHtml(j, k) {
    const rej = j.status === "reject", vis = !!j.visited_at, selc = S.sel === j.uid;
    const first = (k < 10 ? ` enter" style="animation-delay:${k * 25}ms` : "");
    return `<div class="job${selc ? " sel" : ""}${vis ? " visited" : ""}${rej ? " rejected" : ""}${first}" data-uid="${esc(j.uid)}" role="button" tabindex="-1">
      ${avatar(company(j))}
      <div style="min-width:0"><div class="t"><span class="ellipsis">${!vis && !rej ? '<span class="dot accent" title="New" style="margin-right:7px"></span>' : ""}${esc(j.title)}</span></div>
        <div class="c ellipsis">${esc(company(j))}${j.location ? " · " + esc(j.location) : ""}</div>
        <div class="chips"><span class="chip outline">${esc(j.source)}</span>${j.apply_mode === "easy" ? `<span class="chip accent">${I("bolt", "sm")} Easy apply</span>` : ""}${j.status === "unchecked" ? '<span class="chip warn">AI pending</span>' : rej ? `<span class="chip bad">${esc(FP.CATEGORY[j.ai_category] || "Filtered")}</span>` : fitChip(j) + yearsChip(j)}${j.apply_instructions ? '<span class="chip warn">⚠ Special steps</span>' : ""}${j.outreach ? '<span class="chip good">Contacted</span>' : ""}${j.also_on?.length ? `<span class="chip">+${new Set(j.also_on.map((a) => a.source)).size} boards</span>` : ""}</div></div>
      <div class="side"><span class="time">${esc(postedLabel(j))}</span>${j.application ? `<span class="applied-mark" title="Applied">${I("check")}</span>` : ""}</div></div>`;
  }
  function renderChips() {
    const base = FP.data.jobs.filter((j) => j.status !== "reject");
    const cnt = { all: base.length, new: base.filter(isNew).length, strong: base.filter(quickOk.strong).length, easy: base.filter(quickOk.easy).length, today: base.filter(quickOk.today).length, applied: base.filter(quickOk.applied).length };
    $("#quick", root).innerHTML = QUICK.map(([k, l]) => `<button class="chip ${S.quick === k ? "on" : ""}" data-quick="${k}">${l} <span class="n">${n(cnt[k])}</span></button>`).join("");
    const sc = {}; for (const j of base) sc[j.source] = (sc[j.source] || 0) + 1;
    $("#srcs", root).innerHTML = Object.entries(sc).sort((a, b) => b[1] - a[1]).map(([s, c]) => `<button class="chip outline ${S.sources.includes(s) ? "on" : ""}" data-src="${esc(s)}">${esc(s)} <span class="n">${n(c)}</span></button>`).join("");
  }
  function renderList(keepScroll) {
    shown = visible(); const sc = listEl.scrollTop;
    $("#meta", root).innerHTML = `<span><b style="color:var(--text)">${n(shown.length)}</b> job${shown.length === 1 ? "" : "s"}${S.q ? ` matching “${esc(S.q)}”` : ""}</span><span>${FP.data.meta.total_unchecked ? `${n(FP.data.meta.total_unchecked)} awaiting AI` : ""}</span>`;
    if (!FP.data.jobs.length) { listEl.innerHTML = `<div class="empty"><div class="art">${I("inbox")}</div><h3>No jobs yet</h3><p>Press <b>Fetch new jobs</b> and FresherPilot will read every board and rate what it finds.</p><button class="btn primary" onclick="FP.startFetch()">Fetch new jobs</button></div>`; return; }
    if (!shown.length) { listEl.innerHTML = `<div class="empty"><div class="art">${I("filter")}</div><h3>Nothing matches</h3><p>Try clearing a filter${S.hideVisited ? " or turning off “Hide visited”" : ""}.</p><button class="btn" data-reset>Clear filters</button></div>`; return; }
    const page = shown.slice(0, pageN);
    listEl.innerHTML = page.map(itemHtml).join("") + (shown.length > pageN ? `<div class="job-more" id="more"><span class="spinner"></span> Loading more…</div>` : shown.length > 30 ? `<div class="job-more">That's all ${n(shown.length)}</div>` : "");
    if (keepScroll) listEl.scrollTop = sc; observe();
  }
  function observe() {
    io?.disconnect(); const m = $("#more", listEl); if (!m) return;
    io = new IntersectionObserver((e) => { if (e[0].isIntersecting) { pageN += PAGE; renderList(true); } }, { root: listEl, rootMargin: "400px" }); io.observe(m);
  }
  const rerender = () => { pageN = PAGE; renderChips(); renderList(); };

  /* ---------------------------------------------------------------- detail */
  const fpTag = (url, uid) => { try { const u = new URL(url); if (!/^https?:$/.test(u.protocol) || u.searchParams.has("fp_job") || !uid) return url; u.searchParams.set("utm_source", "fresherpilot"); u.searchParams.set("utm_medium", "app"); u.searchParams.set("fp_job", uid); return u.toString(); } catch { return url; } };
  const KIT = [["cover_letter", "Cover letter"], ["why_hire_me", "Why should we hire you?"], ["about_me", "Tell us about yourself"], ["relevant_project", "Most relevant project"], ["why_this_company", "Why this company / role?"], ["linkedin_note", "LinkedIn connection note"], ["email_subject", "Cold email: subject"], ["email_body", "Cold email: body"]];
  function meter(j) {
    const v = j.ai_fit === "strong" ? 100 : j.ai_fit === "partial" ? 58 : 0, c = 2 * Math.PI * 30, col = j.ai_fit === "strong" ? "var(--good)" : "var(--info)";
    return `<div class="fitmeter"><svg viewBox="0 0 70 70"><circle class="bg" cx="35" cy="35" r="30" fill="none" stroke-width="7"/><circle class="fg" cx="35" cy="35" r="30" fill="none" stroke="${col}" stroke-width="7" stroke-dasharray="${c}" stroke-dashoffset="${c}" data-off="${c * (1 - v / 100)}"/></svg><b>${j.ai_fit === "strong" ? "Strong<br>fit" : j.ai_fit === "partial" ? "Partial<br>fit" : "–"}</b></div>`;
  }
  function verdictCard(j) {
    if (j.status === "unchecked") return `<div class="notice warn">${I("clock")}<div><b>Waiting for the AI check.</b> It starts automatically; this card fills in when the job is rated.</div></div>`;
    const rej = j.status === "reject";
    return `<div class="card ${rej ? "flat" : "glow"}"><div class="verdict" style="position:relative">${rej ? `<div class="avatar" style="background:var(--bad-soft);color:var(--bad)">${I("x", "lg")}</div>` : meter(j)}<div>
      <div class="row" style="margin-bottom:8px"><h3>${rej ? `Filtered out: ${esc(FP.CATEGORY[j.ai_category] || "not relevant")}` : "Why FresherPilot kept this"}</h3>${rej ? "" : '<span class="chip accent">AI verdict</span>'}</div>
      <p class="muted">${esc(j.ai_reason || "")}</p>${j.ai_fit_reason && !rej ? `<p class="muted" style="margin-top:6px"><b style="color:var(--text)">Skill fit:</b> ${esc(j.ai_fit_reason)}</p>` : ""}
      ${j.ai_evidence ? `<div class="quote">“${esc(j.ai_evidence)}”</div>` : ""}
      <div class="row" style="margin-top:12px;gap:6px">${rej ? "" : yearsChip(j)}${j.ai_employment ? `<span class="chip">${esc(j.ai_employment.replace(/_/g, " "))}</span>` : ""}${j.ai_seniority ? `<span class="chip">${esc(j.ai_seniority)} level</span>` : ""}${(j.ai_stack || []).map((t) => `<span class="chip outline">${esc(t)}</span>`).join("")}</div></div></div></div>`;
  }
  function instr(j) {
    const x = j.apply_instructions; if (!x) return "";
    const links = (x.links || []).map((u) => `<li>${I("external")}<a class="v grow" href="${esc(/^https?:/i.test(u) ? u : "https://" + u)}" target="_blank" rel="noopener">${esc(u)}</a></li>`).join("");
    const emails = (x.emails || []).map((e) => `<li>${I("mail")}<a class="v grow" href="mailto:${esc(e)}${x.subject_line ? "?subject=" + encodeURIComponent(x.subject_line) : ""}">${esc(e)}</a><button class="btn ghost sm icon-only" data-copy="${esc(e)}">${I("copy", "sm")}</button></li>`).join("");
    return `<div class="notice warn">${I("alert")}<div class="grow"><b>Special application instructions</b><p>${esc(x.summary || "")}</p>${x.subject_line ? `<p class="small">Required subject: <code>${esc(x.subject_line)}</code></p>` : ""}${links || emails ? `<ul class="contact-list" style="margin-top:8px">${links}${emails}</ul>` : ""}<p class="faint xs" style="margin-top:6px">Easy Apply alone may not be enough. Auto-apply emails your resume with the required subject when an address is given, or fills the form and waits for you.</p></div></div>`;
  }
  function kitHtml(j) {
    if (j.status === "reject") return `<div class="empty" style="padding:30px"><p>Filtered-out jobs don't get an apply kit.</p></div>`;
    const k = kits[j.uid] || {};
    const btn = `<button class="btn sm ${k.data ? "" : "primary"}" data-kit="${esc(j.uid)}" ${k.loading ? "disabled" : ""}>${I("sparkle", "sm")} ${k.data ? "Regenerate" : "Write it for this job"}</button>`;
    let body;
    if (k.loading) body = `<div class="col"><div class="row"><span class="spinner"></span><span class="muted">Writing your cover letter and answers… (10–30 seconds)</span></div><div class="sk block"></div><div class="sk block" style="height:60px"></div></div>`;
    else if (k.error) body = `<div class="notice bad">${I("alert")}<div>${esc(k.error)}</div></div>`;
    else if (!k.data) body = `<div class="empty" style="padding:30px"><div class="art">${I("file")}</div><h3>Your apply kit</h3><p>A cover letter, answers to “why should we hire you?”, “about yourself” and outreach messages, written from your resume for this exact job.</p></div>`;
    else body = KIT.filter(([x]) => k.data[x]).map(([x, t]) => `<details class="kit-item" ${x === "cover_letter" ? "open" : ""}><summary>${t} <span class="faint xs">${k.data[x].length} chars</span></summary><div class="txt">${esc(k.data[x])}</div><div style="padding:0 14px 14px"><button class="btn sm" data-copy="${esc(k.data[x])}">${I("copy", "sm")} Copy</button></div></details>`).join("");
    return `<div class="card"><div class="card-head"><h3>Apply kit</h3>${btn}</div>${body}</div>`;
  }
  async function loadKit(uid, gen) {
    const j = FP.job(uid); if (!j || j.status === "reject") return; const cur = kits[uid]; if (cur && (cur.loading || (cur.data && !gen))) return;
    kits[uid] = { ...(cur || {}), loading: !!gen, error: null }; if (S.sel === uid) renderDetail();
    try { const r = await api(`/api/applykit?uid=${encodeURIComponent(uid)}${gen ? (cur?.data ? "&refresh=true" : "") : "&generate=false"}`, { quiet: true }); kits[uid] = { loading: false, data: r.kit }; }
    catch (e) { kits[uid] = { loading: false, data: cur?.data, error: e.message }; }
    if (S.sel === uid) renderDetail();
  }
  async function loadDesc(uid) {
    const j = FP.job(uid); if (!j || !j.lazy_description || j._dl) return; j._dl = true;
    try { const r = await api(`/api/job/description?uid=${encodeURIComponent(uid)}`, { quiet: true }); j.description = r.description || ""; j.lazy_description = false; } catch {} finally { j._dl = false; }
    const el = $(`[data-desc="${CSS.escape(uid)}"]`, detEl); if (el) el.textContent = j.description || "No description.";
  }
  function renderDetail() {
    const j = S.sel && FP.job(S.sel); document.body.classList.toggle("show-detail", !!j);
    if (!j) { detEl.innerHTML = `<div class="placeholder"><div><div class="empty" style="padding:0"><div class="art">${I("briefcase")}</div></div><p class="big" style="margin-top:14px">Pick a job to see the details</p><p>The AI's verdict, the description, people to contact and a ready-made apply kit all live here.</p>
      <div class="shortcuts"><div><span class="kbd">J</span><span class="kbd">K</span> next / previous</div><div><span class="kbd">O</span> open &amp; apply</div><div><span class="kbd">V</span> mark visited · <span class="kbd">A</span> mark applied</div><div><span class="kbd">/</span> search · <span class="kbd">Esc</span> close</div></div></div></div>`; return; }
    const url = fpTag(safeUrl(j.url), j.uid), rej = j.status === "reject", app = j.application;
    if (j.lazy_description) setTimeout(() => loadDesc(j.uid), 0);
    const meta = [[j.location, "pin"], [j.experience && !/^not /i.test(j.experience) ? j.experience : "", "briefcase"], [j.salary && !/^not /i.test(j.salary) ? j.salary : "", "star"], [postedLabel(j), "clock"]].filter(([x]) => x);
    const also = j.also_on?.length ? `<div class="faint small">Also on: ${j.also_on.map((a) => (safeUrl(a.url) ? `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.source)} ↗</a>` : esc(a.source))).join(" · ")}</div>` : "";
    const tabs = [["desc", "Description"], ["reach", "Reach out"], ["kit", "Apply kit"]];
    detEl.innerHTML = `<div class="detail">
      <button class="btn sm back-btn" data-back>${I("back", "sm")} All jobs</button>
      <div class="detail-top">${avatar(company(j), "lg")}<div class="grow" style="min-width:0"><h2>${esc(j.title)}</h2><div class="co">${esc(company(j))}</div><div class="detail-meta">${meta.map(([x, i]) => `<span>${I(i, "sm")}${esc(x)}</span>`).join("")}<span class="chip outline">${esc(j.source)}</span></div></div></div>
      ${j.blog_url && safeUrl(j.blog_url) && j.blog_url !== j.url ? `<div class="faint small">From a Telegram post: <a href="${esc(j.blog_url)}" target="_blank" rel="noopener">post with the details ↗</a></div>` : ""}${also}${instr(j)}
      <div class="actionbar">${url ? `<a class="btn primary lg" href="${esc(url)}" target="_blank" rel="noopener" data-open="${esc(j.uid)}">Open on ${esc(j.source)} ${I("external")}</a>` : ""}
        ${url && j.status === "keep" && !app ? `<button class="btn lg" data-autoapply="${esc(j.uid)}" title="Applies in your browser using your logins">${I("bolt")} Auto-apply</button>` : ""}
        ${rej ? "" : app ? `<button class="btn good" data-notapplied="${esc(j.uid)}">${I("check")} Applied · undo</button>` : `<button class="btn" data-applied="${esc(j.uid)}">${I("check")} Mark applied</button>`}
        <button class="btn ${j.visited_at ? "" : "ghost"}" data-visit="${esc(j.uid)}">${I("eye")} ${j.visited_at ? "Visited" : "Mark visited"}</button>
        ${rej || !app ? "" : `<select class="select sm" data-status="${esc(j.uid)}" style="width:150px">${["applied", "interview", "offer", "rejected"].map((v) => `<option value="${v}" ${v === app.status ? "selected" : ""}>${FP.STATUS[v]}</option>`).join("")}</select>`}</div>
      ${verdictCard(j)}
      ${rej ? "" : O().bar(j)}
      <div class="dtabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" class="${tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
      <div id="tabBody">${tab === "desc" ? `<div class="card"><div class="desc" data-desc="${esc(j.uid)}">${esc(j.description || (j.lazy_description ? "Loading the full description…" : "No description."))}</div></div>` : tab === "reach" ? O().html(j) : kitHtml(j)}</div></div>`;
    requestAnimationFrame(() => $$(".fitmeter .fg", detEl).forEach((c) => (c.style.strokeDashoffset = c.dataset.off)));
  }
  function select(uid, scroll = true) {
    S.sel = uid; tab = "desc"; store.set("sel", uid);
    $$(".job.sel", listEl).forEach((e) => e.classList.remove("sel")); $(`.job[data-uid="${CSS.escape(uid)}"]`, listEl)?.classList.add("sel");
    if (location.hash !== "#/jobs/" + encodeURIComponent(uid)) history.replaceState(null, "", "#/jobs/" + encodeURIComponent(uid));
    renderDetail(); detEl.scrollTop = 0; if (scroll) $(`.job[data-uid="${CSS.escape(uid)}"]`, listEl)?.scrollIntoView({ block: "nearest" });
  }
  function setTab(t) { tab = t; const j = FP.job(S.sel); if (!j) return; if (t === "reach") O().loadContacts(j.uid); if (t === "kit") loadKit(j.uid, false); renderDetail(); }
  const markApplied = (uid) => { FP.setStatus(uid, "applied"); toast("Marked as applied", { kind: "good", action: { label: "Undo", run: () => undo(uid) } }); };
  const undo = async (uid) => { if (FP.job(uid)?.application) await FP.setStatus(uid, ""); if (!FP.job(uid)?.visited_at) await FP.setVisited([uid], true); };

  /* ---------------------------------------------------------------- mount */
  function filtersMenu() {
    return `<div class="menu"><button class="btn sm" id="fbtn">${I("filter", "sm")} View</button><div class="menu-panel" id="fmenu" hidden style="width:290px;padding:14px;right:auto;left:0">
      <div class="col" style="gap:12px"><label class="field"><span>Sort by</span><select class="select sm" id="sortSel"><option value="newest">Newest posting</option><option value="found">Recently found</option><option value="fit">Best fit</option></select></label>
      <label class="field"><span>Posted within</span><select class="select sm" id="daysSel"><option value="">Any time</option><option value="1">Last 24 hours</option><option value="3">Last 3 days</option><option value="7">Last 7 days</option></select></label>
      <label class="check"><input type="checkbox" id="hv"><span>Hide visited</span></label><label class="check"><input type="checkbox" id="ha"><span>Hide applied</span></label>
      <label class="check"><input type="checkbox" id="hp"><span>Show jobs pending AI check</span></label><label class="check"><input type="checkbox" id="hr"><span>Show filtered-out jobs <span class="faint" id="rc"></span></span></label>
      <button class="btn sm" id="markAll">Mark all shown as visited</button></div></div></div>`;
  }
  function syncMenu() { $("#sortSel", root).value = S.sort; $("#daysSel", root).value = S.days; $("#hv", root).checked = S.hideVisited; $("#ha", root).checked = S.hideApplied; $("#hp", root).checked = S.pending; $("#hr", root).checked = S.rejected; const t = FP.data.meta.total_rejected; $("#rc", root).textContent = t ? `(${n(t)})` : ""; }

  FP.views.jobs = {
    full: true,
    async mount(el, params) {
      root = el; S = defaults(); pageN = PAGE; if (S.quick === "new") store.set("jobsq", "all");
      root.innerHTML = `<div class="jobs"><section class="jobs-list"><div class="jobs-filters">
        <div class="row nowrap"><div class="search grow">${I("search")}<input class="input" id="q" placeholder="Search title, company, skill…" autocomplete="off" spellcheck="false"><span class="kbd">/</span></div>${filtersMenu()}</div>
        <div class="chips-scroll" id="quick"></div><div class="chips-scroll" id="srcs"></div></div><div class="list-meta" id="meta"></div><div class="job-scroll" id="list"></div></section><section class="jobs-detail" id="detail"></section></div>`;
      listEl = $("#list", root); detEl = $("#detail", root); syncMenu(); rerender();
      const want = params?.[0] || store.get("sel"); if (want && FP.job(want)) { S.sel = want; } renderDetail(); if (S.sel) { $(`.job[data-uid="${CSS.escape(S.sel)}"]`, listEl)?.scrollIntoView({ block: "center" }); }
      $("#q", root).oninput = (e) => { S.q = e.target.value; rerender(); };
      $("#fbtn", root).onclick = (e) => { e.stopPropagation(); $("#fmenu", root).hidden = !$("#fmenu", root).hidden; };
      const closeMenu = (e) => { if (!e.target.closest(".menu")) $("#fmenu", root) && ($("#fmenu", root).hidden = true); }; document.addEventListener("click", closeMenu); offs.push(() => document.removeEventListener("click", closeMenu));
      $("#sortSel", root).onchange = (e) => { S.sort = e.target.value; store.set("jobs.sort", S.sort); rerender(); };
      $("#daysSel", root).onchange = (e) => { S.days = e.target.value; store.set("jobs.days", S.days); rerender(); };
      $("#hv", root).onchange = (e) => { S.hideVisited = e.target.checked; store.set("jobs.hv", S.hideVisited); rerender(); };
      $("#ha", root).onchange = (e) => { S.hideApplied = e.target.checked; store.set("jobs.ha", S.hideApplied); rerender(); };
      $("#hp", root).onchange = (e) => { S.pending = e.target.checked; store.set("jobs.pending", S.pending); rerender(); };
      $("#hr", root).onchange = async (e) => { S.rejected = e.target.checked; if (S.rejected && !FP.data.rejected) { toast("Loading filtered-out jobs…", { ms: 2500 }); try { await FP.loadRejected(); } catch (x) { toast(x.message, { kind: "bad" }); } } syncMenu(); rerender(); };
      $("#markAll", root).onclick = () => { const u = shown.filter((j) => !j.visited_at && j.status !== "reject").map((j) => j.uid); if (!u.length) return toast("Nothing to mark."); FP.setVisited(u, true); toast(`Marked ${n(u.length)} as visited`, { kind: "good", action: { label: "Undo", run: () => FP.setVisited(u, false) } }); };
      $("#quick", root).onclick = (e) => { const b = e.target.closest("[data-quick]"); if (b) { S.quick = b.dataset.quick; rerender(); } };
      $("#srcs", root).onclick = (e) => { const b = e.target.closest("[data-src]"); if (!b) return; const s = b.dataset.src; S.sources = S.sources.includes(s) ? S.sources.filter((x) => x !== s) : [...S.sources, s]; rerender(); };
      listEl.onclick = (e) => { if (e.target.closest("[data-reset]")) { S = { ...defaults(), sel: S.sel, quick: "all", days: "", hideVisited: false, hideApplied: false }; $("#q", root).value = ""; syncMenu(); return rerender(); } const it = e.target.closest("[data-uid]"); if (it) select(it.dataset.uid, false); };
      detEl.onclick = async (e) => {
        const t = (s) => e.target.closest(s);
        if (t("[data-back]")) { S.sel = null; document.body.classList.remove("show-detail"); renderList(true); history.replaceState(null, "", "#/jobs"); return; }
        const op = t("[data-open]"); if (op) { const j = FP.job(op.dataset.open); if (j && !j.visited_at) setTimeout(() => FP.setVisited([j.uid], true), 0); return; }
        const a = t("[data-applied]"); if (a) return markApplied(a.dataset.applied); const u = t("[data-notapplied]"); if (u) return undo(u.dataset.notapplied);
        const v = t("[data-visit]"); if (v) { const j = FP.job(v.dataset.visit); return FP.setVisited([j.uid], !j.visited_at); }
        const tb = t("[data-tab]"); if (tb) return setTab(tb.dataset.tab);
        const rf = t("[data-refresh]"); if (rf) return O().loadContacts(rf.dataset.refresh, true);
        const kb = t("[data-kit]"); if (kb) return loadKit(kb.dataset.kit, true);
        const aa = t("[data-autoapply]"); if (aa) return FP.startAutoApply([aa.dataset.autoapply]);
      };
      detEl.onchange = (e) => { const s = e.target.closest("[data-status]"); if (s) FP.setStatus(s.dataset.status, s.value); };
      offs.push(FP.bus.on("jobs", (d) => { if (!root.isConnected) return; if (d?.reason === "load" || d?.reason === "rejected") { renderChips(); renderList(true); } else { renderChips(); renderList(true); } if (S.sel && d?.uids?.includes?.(S.sel) || d?.reason === "outreach") renderDetail(); }));
      offs.push(FP.bus.on("detail-refresh", (uid) => { if (root.isConnected && S.sel === uid) { const sc = detEl.scrollTop; renderDetail(); detEl.scrollTop = sc; } }));
      const key = (e) => {
        if (!root.isConnected || e.ctrlKey || e.metaKey || e.altKey) return; const typing = e.target.matches("input, select, textarea");
        if (e.key === "/" && !typing) { e.preventDefault(); $("#q", root).focus(); return; } if (typing) { if (e.key === "Escape") e.target.blur(); return; }
        if (e.key === "Escape" && S.sel) { S.sel = null; renderList(true); renderDetail(); return; }
        const i = shown.findIndex((j) => j.uid === S.sel);
        if (e.key === "j" || e.key === "k") { const nx = shown[Math.max(0, Math.min(shown.length - 1, i + (e.key === "j" ? 1 : -1)))]; if (nx) { if (shown.indexOf(nx) >= pageN - 2) { pageN += PAGE; renderList(true); } select(nx.uid); } }
        else if (S.sel && e.key === "o") $("[data-open]", detEl)?.click(); else if (S.sel && e.key === "a") markApplied(S.sel); else if (S.sel && e.key === "v") { const j = FP.job(S.sel); FP.setVisited([j.uid], !j.visited_at); }
      };
      document.addEventListener("keydown", key); offs.push(() => document.removeEventListener("keydown", key));
      if (S.sel) { tab = "desc"; }
    },
    update(params) { if (params?.[0] && FP.job(params[0]) && params[0] !== S.sel) select(params[0]); },
    unmount() { offs.forEach((f) => f()); offs = []; io?.disconnect(); document.body.classList.remove("show-detail"); },
  };
})();
