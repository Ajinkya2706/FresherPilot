/* Auto-apply: choose jobs, run in the browser extension, watch it work, help it when it needs you. */
(() => {
  const { $, $$, esc, I, n, store, bus, api, toast, avatar, clock } = FP;
  const LABEL = { applied: "Applied", emailed: "Emailed", email_failed: "Email not sent", skipped: "Skipped", failed: "Failed", parked: "Set aside", waiting: "Needs you", resumed: "Continued", start: "Started", finished: "Finished" };
  const TONE = { applied: "good", emailed: "good", email_failed: "bad", skipped: "", failed: "bad", parked: "warn", waiting: "warn", resumed: "info", start: "accent", finished: "good" };
  const ICO = { applied: "check", emailed: "mail", email_failed: "alert", skipped: "skip", failed: "alert", parked: "hand", waiting: "hand", resumed: "play", start: "bolt", finished: "check" };
  let root, offs = [], P = { platforms: [], jobs: [], blocked: [], never: [], tag: null, untagged: 0 }, off = new Set(), filter = "", tagging = false, tagged = false, runSig = "", extWarned = false;
  const secs = (iso) => Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  const ago = (iso) => { if (!iso) return ""; const s = secs(iso); return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`; };
  const since = (iso) => { const m = Math.max(0, Math.round((Date.now() - Date.parse(iso || 0)) / 60000)); if (!iso || !Number.isFinite(m)) return "some time ago"; return m < 60 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`; };

  async function send(action, uid) {
    try { await api("/api/autoapply/command", { json: uid ? { action, uid } : { action } }); toast({ applied: "Marked as applied", skip: "Skipped", stop: "Stopping… the open job ends within ~2 s", pause: "Paused after this job", resume: "Resumed", continue: uid ? "Queued: continues once the current job finishes" : "Continuing this job", open: "Opening its tab…" }[action] || "Done", { kind: "good", ms: 2800 }); }
    catch (e) { toast(`Didn't work: ${e.message}`, { kind: "bad" }); }
    const a = await api("/api/autoapply", { quiet: true }).catch(() => null); if (a) { FP.live.apply = a; bus.emit("live"); }
  }
  FP.startAutoApply = async (pick) => {
    if (!FP.hasExtension()) return toast("The FresherPilot extension isn't active on this page. Reload it in chrome://extensions, then refresh.", { kind: "warn", ms: 8000 });
    if (!pick?.length) return toast("Tick at least one job.", { kind: "warn" });
    const ok = await FP.confirm({ title: `Apply to ${pick.length} job${pick.length === 1 ? "" : "s"}?`, text: "They're applied to one by one in background tabs, using your logins. Jobs that need you wait in “Waiting for you” while the run goes on.", ok: "Start applying" }); if (!ok) return;
    let kill = toast("Preparing: checking each job is still open and open for you… (a few seconds)", { ms: 0 });
    const busyBtns = $$("[data-autoapply], #startBtn, #easyBtn"); busyBtns.forEach((b) => b.classList.add("busy"));
    try {
      const start = await api("/api/autoapply", { json: pick.length === 1 ? { uids: pick, max: 1 } : { max: 0, pick } });
      if (!(start.queue || []).length) {  // every job was a company-site one: the local Playwright runner has them, the extension has nothing to do
        kill(); toast(start.site_jobs ? `${start.site_jobs} company-site job${start.site_jobs === 1 ? "" : "s"} sent to the Playwright runner. A Chrome window opens on this computer and fills the application.` : "None of those jobs can be auto-applied right now (closed, already applied, or blocked).", { kind: start.site_jobs ? "good" : "warn", ms: 9000 });
        if (start.site_jobs) { FP.feedAdd("accent", "globe", `${start.site_jobs} company-site job(s) sent to the Playwright runner`); FP.go("apply"); }
        return;
      }
      if (start.site_jobs) toast(`${start.site_jobs} company-site job(s) went to the Playwright runner; the rest run in your browser.`, { ms: 6000 });
      kill(); kill = toast("Handing the run to your browser extension…", { ms: 0 });
      const ext = await FP.toExtension({ type: "jf-autoapply-start", start });
      if (ext && ext.ok === false) { await api("/api/autoapply/reset", { method: "POST" }); throw new Error(ext.error || "The extension didn't start the run."); }
      kill(); toast("Auto-apply started. Watch it work here.", { kind: "good" }); FP.feedAdd("accent", "bolt", `Auto-apply started on ${pick.length} job${pick.length === 1 ? "" : "s"}`); FP.go("apply");
    } catch (e) { kill(); toast(e.message, { kind: "bad", ms: 10000 }); }
    finally { busyBtns.forEach((b) => b.classList.remove("busy")); }
  };

  async function extCheck() {
    const box = $("#extWarn", root); if (!box) return;
    try {
      const want = (await api("/api/extension/version", { quiet: true })).version, have = document.documentElement.dataset.jobfinderExtension || "";
      if (!have) { box.hidden = false; box.innerHTML = `<div class="notice warn">${I("alert")}<div><b>The FresherPilot extension isn't active on this page.</b> Open <code>chrome://extensions</code>, make sure it's on, then refresh. Auto-apply needs it.</div></div>`; }
      else if (want && have !== want) { box.hidden = false; box.innerHTML = `<div class="notice warn">${I("alert")}<div class="grow"><b>Extension out of date:</b> Chrome runs ${esc(have)}, the app ships ${esc(want)}. Press reload ↻ on FresherPilot in <code>chrome://extensions</code>, then refresh.</div><button class="btn sm" id="extReload">Try reloading it from here</button></div>`; $("#extReload", root).onclick = async () => { try { await FP.toExtension({ type: "jf-reload" }); box.innerHTML = '<div class="notice good">Reloading the extension… refresh this page in a few seconds.</div>'; } catch { toast("This older version can't reload itself: use chrome://extensions", { kind: "warn" }); } }; }
      else box.hidden = true;
    } catch {}
  }


  /* ================================================================ live view: where is the robot right now */
  const STAGES = ["Opening the job", "Filling the form", "Submitting", "Done"];
  const stageOf = (txt) => {
    const t = String(txt || "").toLowerCase();
    if (/submitted|application sent|applied|confirmed/.test(t)) return 3;
    if (/submit|review|send application|finish|dry run/.test(t)) return 2;
    if (/fill|form|answer|field|plan|upload|resume|repair/.test(t)) return 1;
    return 0;
  };
  const plain = (st) => {
    const t = String(st.text || "");
    if (st.who === "browser") return t;
    let m;
    if (/^job_detail/.test(t)) return "Reading the job page";
    if ((m = t.match(/^form @ \S+ fields=(\d+)/))) return `Reading the form (${m[1]} fields)`;
    if ((m = t.match(/^AI plan \((\d+)\):\s*(.*)/))) return `Filled ${m[1]} fields. ${m[2].slice(0, 90)}`;
    if ((m = t.match(/^click '(.*)'/))) return `Pressing '${m[1]}'`;
    if ((m = t.match(/^repair '(.*?)': .*-> '?(.*?)'? \(/))) return `Fixed a rejected value in "${m[1]}" → ${m[2]}`;
    if (/page looks empty|still loading/.test(t)) return "Waiting for the page to load";
    if (/saved login/.test(t)) return "Using your saved login";
    if (/^(unknown|signin|create_account|otp)/.test(t)) return "Handling the sign-in / account step";
    return t.replace(/\s+@\s+\S+/, "").slice(0, 120);
  };
  const REASON = (d) => String(d || "").replace(/^company site \(Playwright\):?\s*/i, "").replace(/^needs you:\s*/i, "").slice(0, 150);
  const mmss = (iso) => { const s = secs(iso); return s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

  function renderLive() {
    const s = FP.live.apply; const box = $("#live", root); if (!s || !box) return;
    const site = s.site || {};
    const browserOn = !!s.running, siteOn = !!site.running, working = browserOn || siteOn;
    const silent = browserOn && s.ext_seen_s !== null && s.ext_seen_s > 25;
    const cur = browserOn ? s.current : site.current;
    const where = browserOn ? "in your browser" : "in its own Chrome window";
    const steps = [...(browserOn ? (s.steps || []).filter((x) => !cur || x.uid === cur.uid) : []), ...(siteOn ? site.steps || [] : [])]
      .sort((a, b) => Date.parse(a.at) - Date.parse(b.at)).slice(-7);
    const stage = steps.length ? Math.max(...steps.slice(-3).map((x) => stageOf(x.text))) : 0;
    const lastStart = s.log.map((e) => e.event).lastIndexOf("start");
    const run = s.log.slice(Math.max(0, lastStart)).filter((e) => ["applied", "emailed", "skipped", "failed"].includes(e.event));
    const cnt = (ev) => run.filter((e) => e.event === ev).length;
    const parked = s.parked || [];
    const sig = JSON.stringify([working, s.paused, s.index, s.total, cur?.uid, steps.map((x) => x.at), silent, run.length, parked.length, Math.floor(secs(s.current_at || new Date()) / 5), s.waiting_for_browser]);
    if (sig === box._sig) return; box._sig = sig;
    const head = silent ? ["bad", "The browser extension stopped answering", `No sign of it for ${s.ext_seen_s} s. Reload it in chrome://extensions, then press Reset.`]
      : s.waiting_for_browser ? ["warn", "Waking the browser extension…", "Chrome picks the run up within about 30 seconds."]
      : s.paused ? ["warn", "Paused", "It stops after the job in progress. Press Resume to carry on."]
      : working ? ["busy", cur?.title ? `Applying: ${cur.title}` : "Applying…", `${cur?.company ? esc(cur.company) + " · " : ""}${cur?.source ? esc(cur.source) + " · " : ""}${where}${s.current_at && browserOn ? " · " + mmss(s.current_at) : ""}`]
      : ["ok", "Ready", run.length ? `Last run: ${cnt("applied")} applied, ${cnt("skipped")} skipped, ${cnt("failed")} failed.` : "Nothing is running. Choose jobs below to start."];
    const doneN = (s.applied || 0) + (s.skipped || 0) + (s.failed || 0) + parked.length, pct = s.total ? Math.min(100, Math.round((100 * doneN) / s.total)) : 0;
    const ch = $("#chooser", root); if (ch) ch.hidden = working;
    box.innerHTML = `
      <div class="live-head"><span class="dot ${head[0] === "busy" ? "busy" : head[0] === "warn" ? "warn" : head[0] === "bad" ? "bad" : ""}"></span>
        <div class="grow" style="min-width:0"><h2 class="ellipsis" style="margin:0">${esc(head[1])}</h2><div class="muted small" style="margin-top:2px">${head[2]}</div></div>
        <div class="row" style="gap:8px">${browserOn ? `${s.paused ? `<button class="btn good" data-cmd="resume">${I("play")} Resume</button>` : `<button class="btn" data-cmd="pause">${I("pause")} Pause</button>`}<button class="btn" data-cmd="skip">Skip this job</button>` : ""}${working ? `<button class="btn danger" data-cmd="stop">${I("x")} Stop everything</button>` : ""}${silent || s.waiting_for_browser ? `<button class="btn ghost" id="resetBtn">Reset</button>` : ""}</div></div>
      ${working ? `<div class="stages">${STAGES.map((n_, i) => `<div class="stage ${i < stage ? "done" : i === stage ? "now" : ""}"><i>${i < stage ? I("check", "sm") : i + 1}</i><span>${n_}</span></div>`).join("<b></b>")}</div>` : ""}
      ${browserOn && s.total ? `<div class="row" style="gap:10px;margin:12px 0 4px"><div class="progress grow"><i style="width:${pct}%"></i></div><span class="small muted num">${Math.min(doneN, s.total)} of ${s.total} done</span></div>` : ""}
      ${working ? `<div class="steps">${steps.length ? [...steps].reverse().map((x, i) => `<div class="step ${i === 0 ? "latest" : ""}"><time>${clock(x.at)}</time><span>${esc(plain(x))}</span></div>`).join("") : `<div class="step latest"><span>Starting…</span></div>`}</div>` : ""}
      <div class="statrow" style="margin-top:14px"><div class="stat"><b>${cnt("applied") + (cnt("emailed") ? 0 : 0)}</b><span>Applied</span></div><div class="stat"><b>${cnt("emailed")}</b><span>Emailed</span></div><div class="stat"><b>${cnt("skipped")}</b><span>Skipped</span></div><div class="stat"><b>${cnt("failed")}</b><span>Failed</span></div><div class="stat ${parked.length ? "warnstat" : ""}"><b>${parked.length}</b><span>Needs you</span></div></div>`;
  }

  function renderLists() {
    const s = FP.live.apply; if (!s) return;
    const parked = s.parked || [], nxt = s.next || [], site = s.site || {}, sq = site.queue || [];
    const needs = $("#needs", root), q = $("#queue", root), res = $("#results", root);
    const nsig = JSON.stringify([parked.map((p) => p.uid), nxt.map((x) => x.uid), sq.map((x) => x.uid), s.log.length, showAll]);
    if (root._lsig === nsig) return; root._lsig = nsig;
    needs.hidden = !parked.length;
    needs.innerHTML = parked.length ? `<div class="card-head"><div><h3>${I("hand", "sm")} Needs you · ${parked.length}</h3><div class="sub">Set aside so the rest keeps going. Do what it asks in that tab, then press Continue.</div></div></div>${parked.map((p) => `<div class="q-item" data-uid="${esc(p.uid)}">${avatar(p.company || p.title)}<div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:600">${esc(p.title || p.uid)}</div><div class="small muted">${esc(REASON(p.reason || p.detail))}${p.company ? " · " + esc(p.company) : ""} · ${since(p.at)}</div></div>${p.url ? `<a class="btn sm" href="${esc(FP.safeUrl(p.url))}" target="_blank" rel="noopener">Open</a>` : ""}<button class="btn sm primary" data-p="continue">Continue</button><button class="btn sm" data-p="applied">I applied</button><button class="btn sm" data-p="skip">Skip</button></div>`).join("")}` : "";
    const waiting = nxt.length + sq.length;
    q.hidden = !waiting;
    q.innerHTML = waiting ? `<div class="card-head"><h3>Up next</h3><span class="sub">${nxt.length} in the browser${sq.length ? `, ${sq.length} on company sites` : ""}</span></div>${[...nxt.slice(0, 6), ...sq.slice(0, 4).map((x) => ({ ...x, source: "Company site" }))].map((j, i) => `<div class="q-item"><span class="idx">${i + 1}</span><div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:560">${esc(j.title || j.uid)}</div><div class="small muted ellipsis">${esc(j.company || "")}${j.source ? " · " + esc(j.source) : ""}</div></div></div>`).join("")}` : "";
    const lastStart = s.log.map((e) => e.event).lastIndexOf("start");
    const ev = ["applied", "emailed", "email_failed", "skipped", "failed", "parked"];
    const all = [...s.log].filter((e) => ev.includes(e.event)).reverse();
    const thisRun = all.filter((e) => s.log.indexOf(e) >= Math.max(0, lastStart));
    const rows = showAll ? all.slice(0, 60) : thisRun.slice(0, 30);
    res.innerHTML = `<div class="card-head"><div><h3>${showAll ? "Recent results" : "This run"}</h3><div class="sub">${showAll ? "Across earlier runs." : "Updates here as each job finishes."}</div></div><button class="chip" id="moreBtn">${showAll ? "Show this run only" : "Show earlier runs"}</button></div>
      ${rows.length ? rows.map((e) => `<div class="log-row"><time>${clock(e.at)}</time><span class="chip ${TONE[e.event] || ""}">${I(ICO[e.event] || "info", "sm")} ${esc(LABEL[e.event] || e.event)}</span><div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:560">${esc(e.title || e.uid || "")}${e.company ? ` <span class="muted">· ${esc(e.company)}</span>` : ""}</div>${e.detail ? `<div class="small muted ellipsis">${esc(REASON(e.detail))}</div>` : ""}</div></div>`).join("") : `<p class="faint" style="margin:6px 0">Nothing finished yet.</p>`}`;
  }
  let showAll = false;

  /* ================================================================ start a run: only fresh jobs, one clear button */
  const ticked = () => $$("#platforms input:checked", root).map((x) => x.value);
  function shownJobs() {
    const plats = new Set(ticked()), hours = +$("#hours", root).value || 0, cut = hours ? Date.now() - hours * 3600e3 : 0, q = $("#q", root).value.trim().toLowerCase();
    return P.jobs.filter((x) => plats.has(x.source) && (!cut || Date.parse(x.found || 0) >= cut) && (!q || `${x.title} ${x.company}`.toLowerCase().includes(q)));
  }
  const picked = () => shownJobs().filter((x) => !off.has(x.uid));
  function renderChooser(rebuild) {
    const saved = store.get("aa.plats", null);
    if (rebuild || !$("#platforms", root).dataset.built) {
      $("#platforms", root).innerHTML = P.platforms.length ? P.platforms.map((p) => { const on = saved ? saved.includes(p.source) : p.source !== "Internshala"; return `<label class="plat ${on ? "on" : ""}"><input type="checkbox" value="${esc(p.source)}" ${on ? "checked" : ""}> ${esc(p.source)} <span class="faint">${n(p.total ?? 0)}</span></label>`; }).join("") : '<span class="faint">No approved jobs yet.</span>';
      $("#platforms", root).dataset.built = "1";
    }
    const list = shownJobs(), sel = list.filter((x) => !off.has(x.uid)), easy = sel.filter((x) => x.mode === "easy"), site = sel.filter((x) => x.mode === "site");
    $("#startSummary", root).innerHTML = P.jobs.length ? `<b class="num">${n(list.length)}</b> job${list.length === 1 ? "" : "s"} found in this window: <b>${easy.length}</b> quick Easy Apply, <b>${site.length}</b> on company sites${P.tag?.running ? ` · still checking ${n(P.tag.total - P.tag.done)} LinkedIn jobs` : P.untagged ? ` · ${P.untagged} not checked yet` : ""}` : "Loading jobs…";
    $("#easyBtn", root).innerHTML = easy.length ? `${I("bolt")} Apply to ${easy.length} Easy Apply job${easy.length === 1 ? "" : "s"}` : `${I("bolt")} No Easy Apply jobs here`; $("#easyBtn", root).disabled = !easy.length;
    $("#startBtn", root).innerHTML = sel.length ? `${I("play")} Apply to all ${n(sel.length)} (incl. company sites)` : `${I("play")} Start`; $("#startBtn", root).disabled = !sel.length;
    $("#pickCount", root).textContent = `${n(sel.length)} ticked of ${n(list.length)}`;
    $("#pickList", root).innerHTML = list.length ? list.slice(0, 250).map((x) => `<label class="pick-row"><input type="checkbox" data-job="${esc(x.uid)}" ${off.has(x.uid) ? "" : "checked"}><div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:580">${esc(x.title)}</div><div class="small muted ellipsis">${esc(x.company || "")} · ${esc(x.source)} · ${since(x.found)}</div></div><span class="chip ${x.mode === "easy" ? "good" : ""}">${x.mode === "easy" ? "Easy Apply" : x.mode === "site" ? "Company site" : "Checking"}</span></label>`).join("") : '<p class="faint" style="margin:8px 4px">Nothing in this window. Try a longer time range.</p>';
    $("#nBlocked", root).textContent = P.blocked.length; $("#blockedList", root).innerHTML = P.blocked.map((c) => `<span class="chip outline">${esc(c)} <button class="link" data-unblock="${esc(c)}" aria-label="Unblock">✕</button></span>`).join("") || '<span class="faint small">None</span>';
    $("#companies", root).innerHTML = [...new Set(P.jobs.map((x) => x.company))].sort().map((c) => `<option value="${esc(c)}">`).join("");
    $("#nNever", root).textContent = P.never.length; $("#neverList", root).innerHTML = P.never.length ? P.never.slice(0, 200).map((x) => `<div class="q-item"><div class="grow ellipsis"><b>${esc(x.title || x.uid)}</b> <span class="muted">· ${esc(x.company || "")}</span></div><button class="btn sm" data-allow="${esc(x.uid)}">Allow again</button></div>`).join("") : '<p class="faint small">None</p>';
  }
  async function loadChooser(quiet) {
    try {
      P = await api("/api/autoapply/preview", { quiet: true }); renderChooser(true);
      if (P.untagged && !P.tag?.running && !tagged) { tagged = true; await api("/api/autoapply/tag", { method: "POST", quiet: true }); watchTag(); } else if (P.tag?.running) watchTag();
    } catch { if (!quiet) $("#platforms", root).innerHTML = '<span class="faint">Couldn\'t load the jobs.</span>'; }
  }
  async function watchTag() {
    if (tagging) return; tagging = true; let last = Date.now();
    try {
      for (;;) {
        if (!root.isConnected) break; const t = await api("/api/autoapply/tag", { quiet: true }); P.tag = t; if (!t.running) break;
        if (Date.now() - last > 20000) { last = Date.now(); P = await api("/api/autoapply/preview", { quiet: true }); renderChooser(true); } else renderChooser(false);
        await FP.sleep(2500);
      }
    } finally { tagging = false; }
    if (root.isConnected) { P = await api("/api/autoapply/preview", { quiet: true }).catch(() => P); renderChooser(true); }
  }
  async function choose(body) { try { await api("/api/autoapply/choices", { json: body }); toast({ block: `Never applying to ${body.company}`, unblock: `${body.company} allowed again`, never: "Left out for good", allow: "Can be auto-applied again" }[body.action] || "Saved", { kind: "good" }); await loadChooser(true); } catch (e) { toast(e.message, { kind: "bad" }); } }

  FP.views.apply = {
    async mount(el) {
      root = el; runSig = ""; tagged = false; showAll = false; off = new Set();
      root.innerHTML = `<div class="page-head"><div><h1>Auto-apply</h1><p>Watch every application happen, and step in only when it needs you.</p></div></div>
        <div id="extWarn" hidden style="margin-bottom:14px"></div>
        <section class="card live-card" id="live"><div class="sk block" style="height:150px"></div></section>
        <section class="card warn-card" id="needs" hidden style="margin-top:14px"></section>
        <div class="two-col" style="margin-top:14px"><section class="card" id="results"></section><section class="card" id="queue" hidden></section></div>
        <section class="card" id="chooser" style="margin-top:14px">
          <div class="card-head"><div><h3>Start applying</h3><div class="sub">Only recent jobs are listed. Older ones stay in the Jobs page.</div></div></div>
          <div class="muted" id="startSummary" style="margin-bottom:12px"></div>
          <div class="row" style="gap:10px;margin-bottom:12px"><select class="select" id="hours" style="width:190px"><option value="3">Last 3 hours</option><option value="12">Last 12 hours</option><option value="24" selected>Last 24 hours</option><option value="72">Last 3 days</option><option value="">Any time</option></select><div class="row" id="platforms" style="gap:6px"></div></div>
          <div class="row" style="gap:10px"><button class="btn primary lg" id="easyBtn" disabled></button><button class="btn lg" id="startBtn" disabled></button></div>
          <details style="margin-top:16px"><summary class="link">Choose individual jobs (<span id="pickCount">0</span>)</summary>
            <div class="row" style="margin:10px 0;gap:8px"><div class="search grow">${I("search")}<input class="input" id="q" placeholder="Search title or company"></div><button class="chip" data-pick="all">Tick all</button><button class="chip" data-pick="none">Untick all</button></div>
            <div class="pick" id="pickList"></div></details>
          <details style="margin-top:12px"><summary class="link">Never apply to… (<span id="nBlocked">0</span> companies, <span id="nNever">0</span> jobs)</summary>
            <div class="row" style="margin:10px 0"><input class="input" id="blockInput" list="companies" placeholder="Company name" style="max-width:300px"><datalist id="companies"></datalist><button class="btn" id="blockBtn">Block company</button></div>
            <div class="row" id="blockedList" style="gap:6px"></div><div id="neverList" style="margin-top:10px"></div></details>
        </section>`;
      root.onclick = (e) => {
        const t = (s) => e.target.closest(s);
        const cm = t("[data-cmd]"); if (cm) { if (cm.dataset.cmd === "stop") return send("stop"); return send(cm.dataset.cmd); }
        const pk = t("[data-p]"); if (pk) { pk.disabled = true; setTimeout(() => (pk.disabled = false), 4000); return send(pk.dataset.p, pk.closest("[data-uid]").dataset.uid); }
        if (t("#resetBtn")) return api("/api/autoapply/reset", { method: "POST" }).then(() => { toast("Reset. You can start again.", { kind: "good" }); $("#live", root)._sig = ""; });
        if (t("#moreBtn")) { showAll = !showAll; root._lsig = ""; return renderLists(); }
        const pc = t("[data-pick]"); if (pc) { shownJobs().forEach((x) => (pc.dataset.pick === "all" ? off.delete(x.uid) : off.add(x.uid))); return renderChooser(); }
        const nv = t("[data-allow]"); if (nv) return choose({ action: "allow", uid: nv.dataset.allow });
        const ub = t("[data-unblock]"); if (ub) return choose({ action: "unblock", company: ub.dataset.unblock });
        if (t("#blockBtn")) { const c = $("#blockInput", root).value.trim(); if (c) { $("#blockInput", root).value = ""; choose({ action: "block", company: c }); } }
        if (t("#startBtn")) FP.startAutoApply(picked().map((x) => x.uid));
        if (t("#easyBtn")) FP.startAutoApply(picked().filter((x) => x.mode === "easy").map((x) => x.uid));
      };
      root.onchange = (e) => {
        if (e.target.closest("#platforms")) { store.set("aa.plats", ticked()); $$(".plat", root).forEach((l) => l.classList.toggle("on", l.querySelector("input").checked)); renderChooser(); }
        else if (e.target.dataset.job) { e.target.checked ? off.delete(e.target.dataset.job) : off.add(e.target.dataset.job); renderChooser(); }
        else if (e.target.id === "hours") { store.set("aa.hours", e.target.value); renderChooser(); }
      };
      $("#q", root).oninput = () => renderChooser(); const h = store.get("aa.hours", null); if (h !== null) $("#hours", root).value = h;
      const tick = () => { if (!root.isConnected) return; renderLive(); renderLists(); };
      offs.push(bus.on("live", tick)); const tk = setInterval(() => { const l = $("#live", root); if (l) l._sig = ""; tick(); }, 2000); offs.push(() => clearInterval(tk));
      if (FP.live.apply) tick(); loadChooser(); extCheck();
    },
    unmount() { offs.forEach((f) => f()); offs = []; },
  };
})();
