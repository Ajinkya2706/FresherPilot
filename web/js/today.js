/* Today: the one screen to open first. What needs you, what is running, fresh jobs, what failed (with reasons + retry). */
(() => {
  const { $, esc, I, api, when, avatar, bus } = FP;
  let root, timer = null, data = null, sig = "";

  // "New" = approved, not opened yet, and posted in the last 30 h: the same rule as the Telegram alerts
  const ageH = (j) => {
    const p = Date.parse(j.posted || "");
    if (String(j.posted || "").includes("T") && !isNaN(p)) return (Date.now() - p) / 3.6e6;   // exact posting time
    const days = j.posted_days === null || j.posted_days === undefined || j.posted_days === "" ? null : +j.posted_days;
    if (days !== null && days >= 1) return days * 24;                                          // date-only posting
    const f = Date.parse(j.first_seen || "");
    return isNaN(f) ? 999 : (Date.now() - f) / 3.6e6;
  };
  FP.freshJobs = () => FP.data.jobs.filter((j) => j.status !== "reject" && !j.visited_at && !j.application && ageH(j) <= 30)
    .sort((a, b) => (Date.parse(b.first_seen || 0) || 0) - (Date.parse(a.first_seen || 0) || 0));
  FP.newCount = () => FP.freshJobs().length;

  const REASON_HELP = {
    otp_needed: "Type the code you got by e-mail below.", captcha: "Open the window and tick the box, then press Continue.",
    needs_human: "Answer below and it continues in the same window.", auth_required: "Sign in once in that window; it remembers you.",
  };

  function section(title, sub, body, count) {
    return `<section class="card" style="margin-bottom:14px"><div class="card-head"><div><h3>${esc(title)}${count != null ? ` <span class="chip ${count ? "warn" : ""}">${count}</span>` : ""}</h3>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div></div>${body}</section>`;
  }
  const row = (inner) => `<div class="q-item" style="display:flex;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--border)">${inner}</div>`;

  function needsHtml(list) {
    if (!list.length) return `<p class="faint" style="margin:6px 0">Nothing is waiting for you.</p>`;
    return list.map((n) => row(`${avatar(n.company || n.title)}<div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:600">${esc(n.title || n.uid)}</div>
      <div class="small muted">${esc(n.why)}${n.company ? " · " + esc(n.company) : ""}</div>
      ${n.kind === "site" ? `<div class="row" style="gap:6px;margin-top:6px"><input class="input" data-ans="${esc(n.uid)}" placeholder="${esc(REASON_HELP.needs_human)}" style="max-width:320px"><button class="btn sm" data-answer="${esc(n.uid)}">Send</button><button class="btn sm" data-cont="${esc(n.uid)}">Continue</button></div>` : ""}</div>
      ${n.kind === "board" ? `<button class="btn sm" data-p="continue" data-uid="${esc(n.uid)}">Continue</button><button class="btn sm" data-p="skip" data-uid="${esc(n.uid)}">Skip</button>` : (n.url ? `<a class="btn sm" href="${esc(FP.safeUrl(n.url))}" target="_blank" rel="noopener">Open page</a>` : "")}`)).join("");
  }

  function runningHtml(r) {
    const parts = [];
    if (r.board_on && r.board) parts.push(`<span class="dot busy"></span> <b>${esc(r.board.title || "")}</b> <span class="muted">${esc(r.board.company || "")} · in your browser</span>`);
    if (r.site) parts.push(`<span class="dot busy"></span> <b>${esc(r.site.title || "")}</b> <span class="muted">${esc(r.site.company || "")} · company site${r.site_queue ? ` · ${r.site_queue} more queued` : ""}</span>`);
    return parts.length ? parts.map((p) => `<div style="padding:6px 0">${p}</div>`).join("") : `<p class="faint" style="margin:6px 0">Nothing running. Pick jobs below and press Apply.</p>`;
  }

  function freshHtml(list) {
    if (!list.length && FP.jobsLoading) return `<div class="sk block" style="height:120px"></div>`;
    if (!list.length) return `<p class="faint" style="margin:6px 0">No new jobs from the last 30 hours. Use "Fetch new jobs" or wait: the cloud keeps reading.</p>`;
    return list.slice(0, 10).map((j) => row(`${avatar(j.employer || j.company)}<div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:600">${esc(j.title)}</div>
      <div class="small muted ellipsis">${esc(j.employer || j.company || "")} · ${esc(j.source || "")} · ${esc(FP.postedLabel ? FP.postedLabel(j) : when(j.first_seen))}</div></div>
      <button class="btn sm primary" data-go="${esc(j.uid)}">Auto-apply</button><a class="btn sm" href="#/jobs/${encodeURIComponent(j.uid)}">Details</a>`)).join("")
      + (list.length > 10 ? `<div style="padding-top:10px"><a class="link" href="#/jobs">See all ${list.length} new jobs</a></div>` : "");
  }

  function failedHtml(list) {
    if (!list.length) return `<p class="faint" style="margin:6px 0">No failed applications. When one fails you will see why here, with a Retry button.</p>`;
    return list.map((f) => row(`<div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:600">${esc((f.uid || "").split(":").slice(-1)[0].slice(0, 50) || f.uid)}</div>
      <div class="small muted">${esc(f.reason)} · ${esc(when(f.at))}</div>${f.detail ? `<div class="xs faint ellipsis">${esc(f.detail.slice(0, 140))}</div>` : ""}</div>
      ${f.has_shot ? `<a class="btn sm" href="/api/failures/shot?id=${encodeURIComponent(f.id)}" target="_blank">Screenshot</a>` : ""}${f.url ? `<button class="btn sm" data-retry="${esc(f.uid)}" data-url="${esc(f.url)}">Retry</button>` : ""}`)).join("");
  }

  const appliedToday = () => { const d = new Date().toDateString(); return FP.data.jobs.filter((j) => j.application && j.application.status === "applied" && new Date(j.application.applied_at).toDateString() === d).length; };
  function hero(h) {
    const A = FP.live.apply || {}, site = A.site || {}, on = !!A.running || !!site.running;
    const cur = A.running ? A.current : site.current;
    const steps = (A.running ? (A.steps || []) : (site.steps || [])).slice(-4).reverse();
    const need = data.needs_you.length, fresh = FP.newCount(), failed = data.failed.length;
    const ext = h.extension_ok ? "" : `<div class="notice warn" style="margin-top:12px">${I("alert")}<div>Browser extension not answering: reload it in chrome://extensions.</div></div>`;
    const main = on
      ? `<span class="chip accent"><span class="dot busy"></span>Working now</span><h2>${esc(cur?.title || "Applying…")}</h2><div class="muted">${esc(cur?.company || "")} · ${A.running ? "in your browser" : "on a company site"}</div><div class="mini-steps">${steps.map((x) => `<div>${esc(String(x.text || "").slice(0, 120))}</div>`).join("")}</div><div style="margin-top:14px"><a class="btn" href="#/apply">Open live view</a></div>`
      : need ? `<span class="chip warn">Needs you</span><h2>${need} application${need === 1 ? " is" : "s are"} waiting for you</h2><div class="muted">Scroll down: each one says what to do.</div>`
      : fresh ? `<span class="chip good">Ready</span><h2>${fresh} new job${fresh === 1 ? "" : "s"} to apply to</h2><div class="muted">Nothing is running. Press Auto-apply on a job below, or start a batch.</div><div style="margin-top:14px"><a class="btn primary" href="#/apply">Apply to new jobs</a></div>`
      : `<span class="chip">Idle</span><h2>All caught up</h2><div class="muted">The cloud keeps reading boards and will alert you on Telegram.</div>`;
    return `<div class="hero"><div class="hero-main">${main}${ext}</div><div class="tks">
      <div class="tk"><b>${appliedToday()}</b><span>Applied today</span></div><a class="tk ${need ? "hot" : ""}" href="#/apply"><b>${need}</b><span>Need you</span></a>
      <a class="tk" href="#/jobs"><b>${fresh}</b><span>New jobs (30 h)</span></a><div class="tk ${failed ? "hot" : ""}"><b>${failed}</b><span>Failed (retry below)</span></div></div></div>`;
  }

  function render() {
    if (!data) return;
    const fresh = FP.freshJobs();
    const s = JSON.stringify([data, fresh.length, fresh[0]?.uid, FP.live.apply?.running, FP.live.apply?.site?.running, (FP.live.apply?.steps || []).length, (FP.live.apply?.site?.steps || []).length]);
    if (s === sig) return; sig = s;
    root.innerHTML = `<div class="page-head"><div><h1>Today</h1><p>What needs you, what is running, and what is new.</p></div></div>
      ${hero(data.health)}
      ${section("Needs you", "Things the robot cannot do alone.", needsHtml(data.needs_you), data.needs_you.length)}
      ${section("Running now", "", runningHtml(data.running))}
      ${section("New jobs to apply", "Approved, from the last 30 hours, not opened yet (same rule as Telegram).", freshHtml(fresh), fresh.length)}
      ${section("Failed applications", "Why it failed, and a one-click retry.", failedHtml(data.failed), data.failed.length)}`;
  }

  async function load() {
    try { data = await api("/api/today", { quiet: true }); render(); } catch (e) { if (!data) root.innerHTML = `<div class="empty"><h3>Could not load Today</h3><p>${esc(e.message)}</p></div>`; }
  }

  FP.views.today = {
    async mount(el) {
      root = el; data = null; sig = "";
      root.innerHTML = `<div class="page-head"><div><h1>Today</h1></div></div><div class="sk block" style="height:90px"></div><div class="sk block" style="height:160px;margin-top:14px"></div><div class="sk block" style="height:220px;margin-top:14px"></div>`;
      root.onclick = async (e) => {
        const t = (s) => e.target.closest(s);
        const go = t("[data-go]"); if (go) { go.disabled = true; return FP.startAutoApply([go.dataset.go]); }
        const p = t("[data-p]"); if (p) { p.disabled = true; return api("/api/autoapply/command", { json: { action: p.dataset.p, uid: p.dataset.uid } }).then(load); }
        const rt = t("[data-retry]"); if (rt) { rt.disabled = true; try { await api("/api/failures/retry", { json: { uid: rt.dataset.retry, url: rt.dataset.url } }); FP.toast("Queued again", { kind: "good" }); } catch (x) { FP.toast(x.message, { kind: "bad" }); } return load(); }
        const an = t("[data-answer]"); if (an) { const v = $(`[data-ans="${CSS.escape(an.dataset.answer)}"]`, root)?.value.trim(); if (!v) return; await api("/api/site/answer", { json: { uid: an.dataset.answer, answers: { answer: v, code: v } } }); FP.toast("Sent to the open window", { kind: "good" }); return; }
        const ct = t("[data-cont]"); if (ct) { await api("/api/site/answer", { json: { uid: ct.dataset.cont, cmd: "continue" } }); FP.toast("Told it to continue", { kind: "good" }); }
      };
      await load();
      timer = setInterval(() => { if (!document.hidden) load(); }, 5000);
    },
    update() { load(); },
    unmount() { clearInterval(timer); timer = null; },
  };
  bus.on("jobs", () => { if (root && timer) render(); });
  bus.on("live", () => { if (root && timer) render(); });
  // nav badge: how many things wait for you, on every page
  const badge = async () => {
    try { const d = await api("/api/today", { quiet: true }); const el = $("#navToday"); if (el) { const k = d.needs_you.length; el.hidden = !k; el.textContent = k; } } catch { /* offline */ }
  };
  setTimeout(badge, 4000); setInterval(() => { if (!document.hidden) badge(); }, 20000);
})();
