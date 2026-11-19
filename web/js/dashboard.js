/* Dashboard: greeting, KPIs with sparklines, charts, funnel, recent applications. */
(() => {
  const { $, $$, esc, I, n, store, bus, api, countUp, when, avatar } = FP;
  const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dayOf = (iso) => new Date(`${iso}T00:00:00`);
  const fmtDay = (iso) => { const d = dayOf(iso); return `${WD[d.getDay()]} ${d.getDate()} ${MO[d.getMonth()]}`; };
  let root, data, offs = [], firstName = "";

  function spark(vals, color) {
    const W = 200, H = 44, max = Math.max(1, ...vals), step = W / Math.max(1, vals.length - 1);
    const pts = vals.map((v, i) => [i * step, H - 4 - (v / max) * (H - 12)]);
    const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const id = "sg" + Math.random().toString(36).slice(2, 7);
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs><path d="${line} L${W},${H} L0,${H} Z" fill="url(#${id})"/><path d="${line}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>`;
  }
  const niceMax = (v) => { if (v <= 4) return 4; const s = Math.pow(10, Math.floor(Math.log10(v))); for (const m of [1, 2, 2.5, 5, 10]) if (m * s >= v) return m * s; return 10 * s; };

  function bars(el, series, keys) {
    const W = Math.max(320, Math.round(el.clientWidth || 560)), H = 220, m = { l: 30, r: 6, t: 20, b: 28 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    const totals = series.map((d) => keys.reduce((s, k) => s + (d[k.key] || 0), 0)), max = niceMax(Math.max(1, ...totals));
    const band = iw / series.length, bw = Math.max(6, Math.min(30, band * 0.6)), y = (v) => m.t + ih - (v / max) * ih;
    const ticks = [0, max / 2, max].filter((v, i, a) => Number.isInteger(v) && a.indexOf(v) === i);
    let svg = `<g class="grid">${ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/>`).join("")}</g><g class="axis">${ticks.map((t) => `<text x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}</g>`;
    const every = band < 36 ? 2 : 1, maxI = totals.indexOf(Math.max(...totals));
    series.forEach((d, i) => {
      const cx = m.l + band * i + band / 2, x = cx - bw / 2; let acc = 0;
      const segs = keys.map((k) => ({ k, v: d[k.key] || 0 })).filter((s) => s.v > 0);
      segs.forEach((s, j) => {
        const y0 = y(acc), y1 = y(acc + s.v); acc += s.v; const top = j === segs.length - 1, h = Math.max(2, y0 - y1 - (j ? 2 : 0));
        const r = Math.min(5, h, bw / 2);
        svg += top ? `<path class="bar" fill="${s.k.color}" d="M${x},${y1 + h} V${y1 + r} Q${x},${y1} ${x + r},${y1} H${x + bw - r} Q${x + bw},${y1} ${x + bw},${y1 + r} V${y1 + h} Z"><animate attributeName="opacity" from="0" to="1" dur=".5s" begin="${i * 0.03}s" fill="freeze"/></path>` : `<rect class="bar" fill="${s.k.color}" x="${x}" y="${y1}" width="${bw}" height="${h}"/>`;
      });
      const today = i === series.length - 1;
      if (totals[i] && (today || i === maxI)) svg += `<text class="val" x="${cx}" y="${y(totals[i]) - 6}" text-anchor="middle">${totals[i]}</text>`;
      if (today || (series.length - 1 - i) % every === 0) { const dd = dayOf(d.date); svg += `<text class="lbl" x="${cx}" y="${H - 8}" text-anchor="middle">${today ? "Today" : `${WD[dd.getDay()][0]} ${dd.getDate()}`}</text>`; }
      svg += `<rect class="hit" data-i="${i}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${ih}" rx="6"/>`;
    });
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(keys.map((k) => k.label).join(" and "))} per day">${svg}</svg><div class="tip" hidden></div>`;
    const tip = el.querySelector(".tip");
    el.querySelectorAll(".hit").forEach((r) => {
      r.onmouseenter = () => { const i = +r.dataset.i, d = series[i];
        tip.innerHTML = `<b>${fmtDay(d.date)}</b><br>${keys.map((k) => `<i style="display:inline-block;width:8px;height:8px;border-radius:3px;background:${k.color};margin-right:6px"></i>${k.label}: <b>${d[k.key] || 0}</b>`).join("<br>")}`;
        const bx = el.getBoundingClientRect(), rb = r.getBoundingClientRect(); tip.style.left = `${rb.left - bx.left + rb.width / 2}px`; tip.style.top = `${(y(totals[i]) / H) * bx.height - 6}px`; tip.hidden = false; };
      r.onmouseleave = () => (tip.hidden = true);
    });
  }
  const hbars = (entries, labels = {}) => {
    if (!entries.some(([, v]) => v)) return `<div class="empty" style="padding:26px"><p>Nothing here yet.</p></div>`;
    const max = Math.max(1, ...entries.map(([, v]) => v));
    return `<div class="hbars">${entries.map(([k, v]) => `<div class="hbar"><span class="ellipsis">${esc(labels[k] || k)}</span><div class="track"><div class="fill" data-w="${(v / max) * 100}"></div></div><b>${v}</b></div>`).join("")}</div>`;
  };
  const delta = (a, b) => { const d = a - b; return !a && !b ? `<span class="faint">quiet so far</span>` : d === 0 ? `<span class="faint">same as yesterday</span>` : `<span class="delta ${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d)}</span> <span class="faint">vs yesterday</span>`; };

  function render() {
    const d = data, k = d.kpi, s = d.series; const hr = new Date().getHours();
    const greet = hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon" : "Good evening";
    const c1 = getComputedStyle(document.documentElement).getPropertyValue("--viz-1").trim(), c2 = getComputedStyle(document.documentElement).getPropertyValue("--viz-2").trim();
    const p = FP.live.pipeline || {}; const ready = p.apply?.ready;
    const recent = d.recent.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>Job</th><th>Board</th><th>Applied</th><th>Outreach</th><th>Status</th></tr></thead><tbody>${d.recent.map((a) => {
      const reach = [a.outreach.email && `${I("mail", "sm")} ${esc(a.outreach.email)}`, a.outreach.whatsapp && `WhatsApp ${esc(a.outreach.whatsapp)}`].filter(Boolean).join(" · ");
      return `<tr><td><div class="row nowrap">${avatar(a.company, "sm")}<div style="min-width:0"><div class="ellipsis" style="font-weight:600;max-width:340px">${a.url ? `<a href="${esc(FP.safeUrl(a.url))}" target="_blank" rel="noopener" style="color:inherit">${esc(a.title)}</a>` : esc(a.title)}</div><div class="faint xs">${esc(a.company)}</div></div></div></td>
        <td><span class="chip">${esc(a.source)}</span></td><td class="muted">${esc(when(a.applied_at))}</td><td class="muted small">${reach || "–"}</td>
        <td><select class="select sm" data-st="${esc(a.uid)}" style="width:140px">${["applied", "interview", "offer", "rejected"].map((v) => `<option value="${v}" ${v === a.status ? "selected" : ""}>${FP.STATUS[v]}</option>`).join("")}</select></td></tr>`;
    }).join("")}</tbody></table></div>` : `<div class="empty"><div class="art">${I("send")}</div><h3>No applications yet</h3><p>Open a job and apply, or run Auto-apply. Everything you apply to shows up here automatically.</p><button class="btn primary" data-go="jobs">Browse jobs</button></div>`;

    root.innerHTML = `
      <section class="card glow hello"><div style="position:relative"><h1>${greet}${firstName ? ", " + esc(firstName) : ""} 👋</h1><p class="muted" style="margin-top:6px">${fmtDay(d.today)} · ${k.new_matches ? `<b style="color:var(--text)">${n(k.new_matches)} new matches</b> are waiting for you.` : "You're all caught up."}</p></div>
        <div class="stats" style="position:relative"><div><b>${n(k.reviewed_today)}</b><span>jobs reviewed today</span></div><div><b>${n(ready ?? "–")}</b><span>ready to auto-apply</span></div><div><b>${Math.round(d.ai_tokens_today / 1000)}k</b><span>AI tokens today</span></div>
        ${k.new_matches ? `<button class="btn primary lg" data-go="jobs" style="align-self:center">Review matches ${I("back").replace("m15 5-7 7 7 7", "m9 5 7 7-7 7")}</button>` : ""}</div></section>
      <div class="kpis">
        <div class="kpi hero"><span class="label">${I("send", "sm")} Applied today</span><span class="value" data-c="${k.applied_today}">0</span><span class="sub">${delta(k.applied_today, k.applied_yesterday)}</span>${spark(s.map((x) => x.applied), c1)}</div>
        <div class="kpi"><span class="label">${I("layers", "sm")} Last 7 days</span><span class="value" data-c="${k.applied_week}">0</span><span class="sub">${n(k.applied_total)} applications in total</span>${spark(s.map((x) => x.applied), c2)}</div>
        <div class="kpi"><span class="label">${I("mail", "sm")} Outreach today</span><span class="value" data-c="${k.emails_today + k.whatsapp_today}">0</span><span class="sub">${k.emails_today} email · ${k.whatsapp_today} WhatsApp</span>${spark(s.map((x) => x.emails + x.whatsapp), c1)}</div>
        <button class="kpi" data-go="jobs"><span class="label">${I("sparkle", "sm")} New matches</span><span class="value" data-c="${k.new_matches}">0</span><span class="sub">not visited yet${k.pending_ai ? ` · ${k.pending_ai} pending AI` : ""}</span>${spark(s.map((x) => x.matches), c2)}</button>
        <div class="kpi"><span class="label">${I("star", "sm")} Interviews</span><span class="value" data-c="${k.interviews}">0</span><span class="sub">${k.offers} offer${k.offers === 1 ? "" : "s"} · ${k.rejected} not selected</span></div>
      </div>
      <div class="panels">
        <section class="card span-8"><div class="card-head"><h3>Applications per day</h3><span class="sub">last ${s.length} days</span></div><div class="chart" id="chA"></div></section>
        <section class="card span-4"><div class="card-head"><h3>Where you stand</h3><span class="sub">all applications</span></div>${hbars(Object.entries(d.pipeline), FP.STATUS)}<hr class="divider"><div class="card-head" style="margin-bottom:10px"><h3>By board</h3></div>${hbars(Object.entries(d.sources))}</section>
        <section class="card span-6"><div class="card-head"><h3>Outreach per day</h3><div class="legend"><span><i style="background:${c1}"></i>Email</span><span><i style="background:${c2}"></i>WhatsApp</span></div></div><div class="chart" id="chO"></div><p class="faint xs" style="margin-top:8px">Daily send limits: ${d.caps.email} emails · ${d.caps.whatsapp} WhatsApp</p></section>
        <section class="card span-6"><div class="card-head"><h3>New matches per day</h3><span class="sub">what the AI approved</span></div><div class="chart" id="chM"></div></section>
        <section class="card span-12"><div class="card-head"><h3>Recent applications</h3></div>${recent}</section>
        ${d.archive && d.archive.jobs ? `<section class="card span-12 flat"><div class="row between"><div class="row nowrap">${I("database")}<div><b>${n(d.archive.jobs)} older jobs are in cold storage</b><div class="faint small">Jobs older than 3 days live in a compressed archive on this computer (${d.archive.mb} MB), not in memory, which keeps the app fast. Your totals still include them: ${n(d.archive.kept)} approved matches archived.</div></div></div><div class="row nowrap"><input class="input" id="arcQ" placeholder="Search the archive…" style="width:220px"><button class="btn" id="arcGo">Search</button></div></div><div id="arcRes" style="margin-top:12px"></div></section>` : ""}
      </div>`;
    $$(".value[data-c]", root).forEach((el) => countUp(el, +el.dataset.c));
    $$(".fill[data-w]", root).forEach((el) => requestAnimationFrame(() => (el.style.width = el.dataset.w + "%")));
    bars($("#chA", root), s, [{ key: "applied", label: "Applied", color: c1 }]);
    bars($("#chO", root), s, [{ key: "emails", label: "Email", color: c1 }, { key: "whatsapp", label: "WhatsApp", color: c2 }]);
    bars($("#chM", root), s, [{ key: "matches", label: "New matches", color: getComputedStyle(document.documentElement).getPropertyValue("--viz-3").trim() }]);
  }

  const skeleton = () => `<div class="sk block" style="height:120px;margin-bottom:14px"></div><div class="kpis">${'<div class="sk block"></div>'.repeat(5)}</div><div class="panels"><div class="sk block span-8" style="height:290px"></div><div class="sk block span-4" style="height:290px"></div></div>`;
  async function load(first) {
    try { data = await api("/api/dashboard", { quiet: !first }); render(); }
    catch (e) { if (!data) root.innerHTML = `<div class="empty"><div class="art">${I("alert")}</div><h3>Couldn't load the dashboard</h3><p>${esc(e.message)}</p><button class="btn" data-retry>Retry</button></div>`; }
  }
  FP.views.home = {
    async mount(el) {
      root = el; root.innerHTML = skeleton();
      root.onclick = (e) => { const g = e.target.closest("[data-go]"); if (g) FP.go(g.dataset.go); if (e.target.closest("[data-retry]")) load(true); };
      root.onchange = (e) => { const s = e.target.closest("[data-st]"); if (s) FP.setStatus(s.dataset.st, s.value); };
      root.addEventListener("click", async (e) => {
        if (!e.target.closest("#arcGo")) return; const q = $("#arcQ", root).value.trim(); if (!q) return; const box = $("#arcRes", root); box.innerHTML = '<span class="spinner"></span>';
        try { const r = await api("/api/archive/search?q=" + encodeURIComponent(q) + "&limit=25"); box.innerHTML = r.results.length ? r.results.map((j) => `<div class="q-item"><div class="grow" style="min-width:0"><div class="ellipsis" style="font-weight:580">${j.url ? `<a href="${esc(FP.safeUrl(j.url))}" target="_blank" rel="noopener" style="color:inherit">${esc(j.title)}</a>` : esc(j.title)}</div><div class="faint xs">${esc(j.employer || j.company || "")} · ${esc(j.source)} · ${esc(when(j.first_seen))}</div></div><span class="chip ${j._verdict?.decision === "keep" ? "good" : ""}">${j._verdict?.decision === "keep" ? "was approved" : "filtered"}</span></div>`).join("") : '<p class="faint">No archived job matches.</p>'; } catch (x) { box.textContent = x.message; }
      });
      offs.push(bus.on("dash-stale", () => load()));
      if (!firstName) api("/api/profile", { quiet: true }).then((p) => { firstName = (p.profile || p).personal?.first_name || ""; if (data) render(); }).catch(() => {});
      const t = setInterval(() => !document.hidden && root.isConnected && load(), 45000); offs.push(() => clearInterval(t));
      let rt; const rs = () => { clearTimeout(rt); rt = setTimeout(() => data && root.isConnected && render(), 200); }; window.addEventListener("resize", rs); offs.push(() => window.removeEventListener("resize", rs));
      await load(true);
    },
    unmount() { offs.forEach((f) => f()); offs = []; },
  };
})();
