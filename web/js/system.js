/* Control room: the backend made visible. Live pipeline, event feed, source health, AI usage, filter reasons. */
(() => {
  const { $, $$, esc, I, n, bus, api, when, clock, fmtDur } = FP;
  let root, offs = [], usage = null, usageAt = 0;
  const NV = (m) => /nemotron|minimax|nvidia/i.test(m);
  const k = (x) => (x >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : `${Math.round(x / 1000)}k`);

  function node(cls, icon, title, big, sub, extra = "") { return `<div class="node ${cls}"><div class="ttl"><span class="ico">${I(icon)}</span>${extra}</div><div style="margin-top:4px"><div class="faint xs up" style="letter-spacing:.06em">${title}</div><div class="big">${big}</div></div><div class="sub">${sub}</div></div>`; }
  function flow() {
    const s = FP.live.status || {}, p = FP.live.pipeline || {}, a = FP.live.apply || {}, m = FP.data.meta || {};
    const busy = (s.live?.busy || []).map((b) => FP.BOARD[b] || b), rate = p.rate || {}, ap = p.apply || {};
    const paused = rate.paused_until && rate.paused_until * 1000 > Date.now(); const fetching = !!s.fetch?.running;
    const kept = FP.data.jobs.filter((j) => j.status === "keep").length, newc = FP.newCount();
    const stuck = ap.running && ap.extension_seen_s != null && ap.extension_seen_s > 25;
    const link = (on) => `<div class="link-flow ${on ? "on" : ""}"></div>`;
    const aiBusy = !!rate.running;
    return `<div class="flow-wrap">
      ${node(busy.length || fetching ? "busy" : "ok", "radar", "1 · Sources", busy.length ? "Reading…" : fetching ? "Fetching…" : "Watching", busy.length ? esc(busy.join(", ")) : "LinkedIn, Indeed, Naukri, Telegram, careers pages. The cloud reads 24/7.")}
      ${link(busy.length || fetching)}
      ${node("ok", "funnel", "2 · Free rules", n(m.total_fetched || 0), `in your live list · ${n(m.total_rejected || 0)} dropped by city, title, experience &amp; AI rules`)}
      ${link(aiBusy)}
      ${node(rate.error ? "warn" : aiBusy ? "busy" : "ok", "cpu", "3 · AI rating", aiBusy ? `${n(rate.done)}<span class="faint" style="font-size:15px">/${n(rate.total)}</span>` : rate.waiting == null ? "…" : rate.waiting ? `${n(rate.waiting)} waiting` : "All rated", rate.error ? esc(String(rate.error).slice(0, 80)) : paused ? `AI limit reached · resumes ${new Date(rate.paused_until * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : aiBusy ? esc(rate.stage || "checking facts, fit and seniority") : "Groq → NVIDIA fallback, reads every post")}
      ${link(aiBusy)}
      ${node("ok", "inbox", "4 · Your matches", n(kept), `${n(newc)} new for you · alerts go to Telegram`)}
      ${link(a.running || ap.running)}
      ${node(stuck || ap.waiting_for_you ? "warn" : a.running ? "busy" : "ok", "bolt", "5 · Auto-apply", a.running ? `${a.index || 0}<span class="faint" style="font-size:15px">/${a.total || 0}</span>` : ap.ready == null ? "…" : `${n(ap.ready)} ready`, stuck ? "Extension not answering. Open Auto-apply and press Reset." : ap.waiting_for_you ? `${ap.waiting_for_you} waiting for you` : a.running ? `applied ${a.applied || 0} · skipped ${a.skipped || 0} · failed ${a.failed || 0}` : "approved jobs not applied yet")}
    </div>`;
  }
  function sources() {
    const s = FP.live.status || {}, b = s.live?.boards || {}, busy = new Set(s.live?.busy || []);
    const keys = [...new Set([...Object.keys(FP.BOARD), ...Object.keys(b)])].filter((x) => x !== "naukri" || b[x]);
    const bySrc = {}; for (const j of FP.data.jobs) bySrc[j.source] = (bySrc[j.source] || 0) + 1;
    return keys.map((key) => { const r = b[key] || {}, name = FP.BOARD[key] || key, isBusy = busy.has(key), cnt = bySrc[name] || 0;
      return `<div class="src"><div class="nm"><span class="dot ${isBusy ? "busy" : r.error ? "warn" : r.at ? "good" : ""}"></span>${esc(name)}<span class="chip" style="margin-left:auto">${n(cnt)}</span></div><div class="st">${isBusy ? "reading now…" : r.at ? `read ${esc(when(r.at))}${r.added ? ` · ${r.added} new` : ""}` : "not read yet this session"}</div>${r.error ? `<div class="xs" style="color:var(--warn)">${esc(String(r.error).slice(0, 80))}</div>` : ""}</div>`; }).join("");
  }
  function feed() {
    if (!FP.feed.length) return `<div class="empty" style="padding:30px"><p>Waiting for activity. Press <b>Fetch new jobs</b> and watch this fill up.</p></div>`;
    return FP.feed.slice(0, 80).map((e) => `<div class="ev"><time>${clock(e.at)}</time><span class="ei ${e.kind}">${I(e.icon, "sm")}</span><div><div>${esc(e.text)}</div>${e.sub ? `<small>${esc(e.sub)}</small>` : ""}</div></div>`).join("");
  }
  function usageHtml() {
    if (!usage) return '<div class="sk block"></div>'; const lim = usage.daily_limit_per_model || 200000, models = Object.entries(usage.models || {}).sort((a, b) => b[1] - a[1]);
    const steps = Object.entries(usage.steps || {}).sort((a, b) => b[1].total - a[1].total).slice(0, 7), maxS = Math.max(1, ...steps.map(([, v]) => v.total));
    return `<div class="col" style="gap:12px">${models.map(([m, t]) => { const nv = NV(m), pct = nv ? Math.min(100, t / 20000) : Math.min(100, (t / lim) * 100); return `<div class="meter"><span class="name" title="${esc(m)}">${esc(m.split("/").pop())}</span><div class="progress"><i style="width:${nv ? 100 : pct}%;${!nv && pct > 85 ? "background:var(--bad)" : !nv && pct > 60 ? "background:var(--warn)" : ""};opacity:${nv ? 0.35 : 1}"></i></div><span class="val">${k(t)}${nv ? "" : ` / ${k(lim)}`}</span></div>`; }).join("") || '<p class="faint">No AI calls yet today.</p>'}</div>
      <p class="faint xs" style="margin:10px 0 0">Groq's free tier allows ${k(lim)} tokens per model per key per day; NVIDIA has no daily cap. This laptop only.</p>
      ${steps.length ? `<hr class="divider"><div class="up" style="margin-bottom:10px">What the AI spent tokens on</div><div class="col" style="gap:9px">${steps.map(([name, v]) => `<div class="meter"><span class="name">${esc(name.replace(/_/g, " "))}</span><div class="progress"><i style="width:${(v.total / maxS) * 100}%"></i></div><span class="val">${n(v.calls)} calls</span></div>`).join("")}</div>` : ""}`;
  }
  function reasons() {
    const r = FP.data.meta.rejected_by_category || {}; const e = Object.entries(r).filter(([, v]) => v).sort((a, b) => b[1] - a[1]); if (!e.length) return '<p class="faint">No filtered-out jobs yet.</p>'; const max = Math.max(...e.map(([, v]) => v));
    return `<div class="hbars">${e.map(([c, v]) => `<div class="hbar" style="grid-template-columns:150px 1fr 56px"><span class="ellipsis">${esc(FP.CATEGORY[c] || c)}</span><div class="track"><div class="fill" style="width:${(v / max) * 100}%"></div></div><b>${n(v)}</b></div>`).join("")}</div>`;
  }
  function facts() {
    const L = FP.live, newest = FP.data.jobs.reduce((m, j) => Math.max(m, Date.parse(j.first_seen || 0) || 0), 0);
    const rows = [["Backend response", L.ok === false ? "offline" : `${L.latency ?? "–"} ms`], ["Last job found", newest ? when(new Date(newest).toISOString()) : "–"], ["Jobs in memory", n(FP.data.jobs.length)], ["Browser extension", FP.hasExtension() ? `connected · v${document.documentElement.dataset.jobfinderExtension}` : "not detected"], ["Telemetry", "polling every 2–4 s"], ["Account", FP.data.me?.user?.username || "–"]];
    return rows.map(([a, b]) => `<div class="row between" style="padding:9px 0;border-bottom:1px solid var(--line)"><span class="muted">${a}</span><b class="mono" style="font-size:12.5px;font-weight:550">${esc(b)}</b></div>`).join("");
  }
  const paint = () => { if (!root?.isConnected) return; $("#sFlow", root).innerHTML = flow(); $("#sSrc", root).innerHTML = sources(); $("#sFacts", root).innerHTML = facts(); };
  const paintFeed = () => { if (root?.isConnected) $("#sFeed", root).innerHTML = feed(); };
  async function loadUsage() { try { usage = await api("/api/usage", { quiet: true }); usageAt = Date.now(); if (root?.isConnected) $("#sUsage", root).innerHTML = usageHtml(); } catch {} }

  FP.views.system = {
    async mount(el) {
      root = el;
      root.innerHTML = `<div class="page-head"><div><h1>Control room</h1><p>Everything the backend is doing right now, live. Nothing here is decoration: it's read from your running server.</p></div><div class="row"><span class="chip good"><span class="dot live"></span>Live</span><button class="btn" id="fetchNow">${I("refresh")} Fetch new jobs</button></div></div>
        <section class="card" style="margin-bottom:14px"><div class="card-head"><h3>Pipeline</h3><span class="sub">jobs flow left to right, from the internet to your applications</span></div><div id="sFlow"></div></section>
        <div class="panels"><section class="card span-8"><div class="card-head"><h3>Live activity</h3><span class="sub">newest first</span></div><div class="feed" id="sFeed"></div></section>
        <section class="card span-4"><div class="card-head"><h3>System</h3></div><div id="sFacts"></div></section>
        <section class="card span-12"><div class="card-head"><h3>Sources</h3><span class="sub">jobs held per board · last read</span></div><div class="srcgrid" id="sSrc"></div></section>
        <section class="card span-6"><div class="card-head"><h3>AI usage today</h3><span class="sub">tokens per model</span></div><div id="sUsage"></div></section>
        <section class="card span-6"><div class="card-head"><h3>Why jobs get filtered out</h3><span class="sub">your rules, applied before you see anything</span></div><div id="sReasons"></div></section></div>`;
      $("#sReasons", root).innerHTML = reasons(); $("#fetchNow", root).onclick = () => FP.startFetch(); paint(); paintFeed(); $("#sUsage", root).innerHTML = usageHtml(); loadUsage();
      offs.push(bus.on("live", paint), bus.on("feed", paintFeed), bus.on("jobs", () => root.isConnected && ($("#sReasons", root).innerHTML = reasons())));
      const t = setInterval(() => root.isConnected && !document.hidden && loadUsage(), 20000); offs.push(() => clearInterval(t));
      const t2 = setInterval(paintFeed, 30000); offs.push(() => clearInterval(t2));
    },
    unmount() { offs.forEach((f) => f()); offs = []; },
  };
})();
