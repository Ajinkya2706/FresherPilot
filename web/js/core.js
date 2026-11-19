/* FresherPilot core: helpers, icons, api, data layer, live telemetry, router, palette, toasts, shell. */
(() => {
  "use strict";
  const FP = (window.FP = { views: {}, data: { jobs: [], by: new Map, meta: {}, rejected: null, me: null, profile: null, loaded: false }, live: { ok: null, latency: null, status: null, pipeline: null, apply: null, at: 0 }, feed: [] });
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const n = (x) => Number(x || 0).toLocaleString();
  const store = {
    get(k, d = null) { try { const v = localStorage.getItem("fp." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("fp." + k, JSON.stringify(v)); } catch {} },
  };
  const bus = (() => { const m = {}; return { on(e, f) { (m[e] ||= new Set()).add(f); return () => m[e].delete(f); }, emit(e, d) { (m[e] || []).forEach((f) => { try { f(d); } catch (x) { console.error(x); } }); } }; })();
  Object.assign(FP, { $, $$, esc, safeUrl, sleep, n, store, bus });

  /* ---------------------------------------------------------------- icons */
  const P = {
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/>', briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>', activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>', user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    settings: '<path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', check: '<path d="m5 12 5 5L20 7"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>', mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>', copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>', back: '<path d="m15 5-7 7 7 7"/>', refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
    alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 18h.01"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>', play: '<path d="M7 4v16l13-8z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>', send: '<path d="m22 2-11 11M22 2l-7 20-4-9-9-4z"/>', building: '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>', database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    cloud: '<path d="M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9z"/>', sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
    filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>', eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', download: '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 20h16"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>', plus: '<path d="M12 5v14M5 12h14"/>', lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>', shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>', link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>', logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    pin: '<path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>', hand: '<path d="M8 13V5a1.5 1.5 0 0 1 3 0v6M11 10V4a1.5 1.5 0 0 1 3 0v7M14 11V6a1.5 1.5 0 0 1 3 0v8a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-2-4a1.5 1.5 0 0 1 2.5-1.5L8 14"/>',
    skip: '<path d="m5 4 10 8-10 8zM19 5v14"/>', radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 18 6"/>', funnel: '<path d="M3 4h18l-7 9v6l-4 2v-8z"/>', inbox: '<path d="M3 13h5l1 3h6l1-3h5M5 13l2-8h10l2 8v6H5z"/>',
    star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>', command: '<path d="M9 9V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
  };
  const I = (name, cls = "") => `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ""}</svg>`;
  Object.assign(FP, { I });

  /* ---------------------------------------------------------------- formatting */
  const agoText = (secs) => {
    const m = Math.max(0, secs) / 60;
    if (m < 1) return "just now"; if (m < 60) return `${Math.round(m)}m ago`;
    if (m < 36 * 60) return `${Math.round(m / 60)}h ago`; return `${Math.round(m / 1440)}d ago`;
  };
  const when = (iso) => { const t = Date.parse(iso || ""); return isNaN(t) ? "–" : agoText((Date.now() - t) / 1000); };
  const clock = (iso) => { const d = iso ? new Date(iso) : new Date(); return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); };
  const fmtDur = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`; };
  const postedLabel = (job) => {
    const p = String(job.posted || "");
    if (p.includes("T") && !p.includes("T00:00:00")) { const t = Date.parse(p); if (!isNaN(t)) return agoText((Date.now() - t) / 1000); }
    if (job.posted_within_min && job.first_seen) {
      const age = (Date.now() - Date.parse(job.first_seen)) / 1000 + job.posted_within_min * 60;
      if (!isNaN(age) && age < 36 * 3600) return "< " + agoText(age).replace(" ago", "") + " ago";
    }
    const d = job.posted_days;
    if (d === null || d === undefined || d === "") return job.posted || "";
    return +d === 0 ? "Today" : +d === 1 ? "1 day ago" : `${d} days ago`;
  };
  const hue = (s) => { let h = 0; for (const c of String(s || "?")) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
  const avatar = (name, cls = "") => {
    const t = String(name || "?").trim(); const h = hue(t);
    const ch = (t.match(/[A-Za-z0-9]/) || ["?"])[0].toUpperCase();
    return `<div class="avatar ${cls}" style="background:linear-gradient(135deg,hsl(${h} 70% 56%),hsl(${(h + 40) % 360} 75% 46%))">${esc(ch)}</div>`;
  };
  const countUp = (el, to, ms = 700) => {
    if (!el) return; const from = +el.dataset.v || 0; el.dataset.v = to;
    if (from === to || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = n(to); return; }
    const t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / ms); const e = 1 - Math.pow(1 - k, 3); el.textContent = n(Math.round(from + (to - from) * e)); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };
  Object.assign(FP, { agoText, when, clock, fmtDur, postedLabel, avatar, countUp, hue });
  FP.CATEGORY = { internship: "Internship", not_full_time: "Not full-time", too_senior: "Too senior", needs_postgrad: "Needs Master's/PhD", needs_experience: "Needs 1+ years", non_developer: "Not a developer role", non_software_engineering: "Non-software eng.", off_stack: "Different stack", too_old: "Posted > 3 days ago", other_city: "Other city", other: "Not relevant" };
  FP.STATUS = { applied: "Applied", interview: "Interview", offer: "Offer", rejected: "Not selected" };

  /* ---------------------------------------------------------------- api */
  let inflight = 0;
  const topload = () => { const b = $("#topload"); if (b) b.classList.toggle("on", inflight > 0); };
  async function api(path, opts = {}) {
    const { json, raw, quiet, ...rest } = opts;
    const init = { ...rest, headers: { ...(rest.headers || {}) } };
    if (json !== undefined) { init.method = init.method || "POST"; init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(json); }
    if (!quiet) { inflight++; topload(); }
    const t0 = performance.now();
    try {
      const res = await fetch(path, init);
      FP.live.latency = Math.round(performance.now() - t0);
      if (res.status === 401 && !path.includes("/api/auth")) { location.href = "/login"; throw new Error("Signed out"); }
      if (raw) return res;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { const e = new Error(data.detail || data.error || `Server error ${res.status}`); e.status = res.status; e.data = data; throw e; }
      return data;
    } finally { if (!quiet) { inflight--; topload(); } }
  }
  FP.api = api;

  /* ---------------------------------------------------------------- toast */
  function toast(msg, o = {}) {
    const kind = o.kind || "", ms = o.ms ?? 4200; const box = $("#toasts"); if (!box) return;
    const el = document.createElement("div"); el.className = `toast ${kind}`;
    el.innerHTML = `${I(kind === "good" ? "check" : kind === "bad" ? "alert" : kind === "warn" ? "alert" : "info", "k")}<div class="grow">${esc(msg)}</div>${o.action ? `<button class="btn sm" data-a>${esc(o.action.label)}</button>` : ""}`;
    const kill = () => { el.classList.add("out"); setTimeout(() => el.remove(), 220); };
    el.querySelector("[data-a]")?.addEventListener("click", () => { o.action.run(); kill(); });
    box.appendChild(el); while (box.children.length > 3) box.firstChild.remove();
    if (ms) setTimeout(kill, ms); return kill;
  }
  FP.toast = toast;

  /* ---------------------------------------------------------------- extension bridge */
  FP.hasExtension = () => !!document.documentElement.dataset.jobfinderExtension;
  FP.toExtension = (message, timeout = 10000) => new Promise((resolve, reject) => {
    const id = Math.random().toString(36).slice(2);
    const on = (e) => { if (e.source !== window || !e.data || e.data.__jf !== "from-extension" || e.data.id !== id) return; window.removeEventListener("message", on); const r = e.data.response; r && r.ok ? resolve(r.data) : reject(new Error((r && r.error) || "Extension didn't answer")); };
    window.addEventListener("message", on); window.postMessage({ __jf: "to-extension", id, message }, "*");
    setTimeout(() => { window.removeEventListener("message", on); reject(new Error("The extension didn't answer. Reload it in chrome://extensions, then refresh.")); }, timeout);
  });

  /* ---------------------------------------------------------------- data layer */
  const D = FP.data;
  const index = () => { D.by = new Map(D.jobs.map((j) => [j.uid, j])); };
  async function readStream(res, onBytes) {
    if (!res.body || !res.body.getReader) return res.json();
    const reader = res.body.getReader(); const dec = new TextDecoder(); let text = "", bytes = 0;
    for (;;) { const { done, value } = await reader.read(); if (done) break; bytes += value.length; text += dec.decode(value, { stream: true }); onBytes && onBytes(bytes); }
    return JSON.parse(text + dec.decode());
  }
  let jobsLoad = null;
  FP.loadJobs = (onBytes) => jobsLoad || (jobsLoad = (async () => {
    try {
      const res = await api("/api/jobs?slim=true&rejected=false", { raw: true, quiet: !!D.loaded });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await readStream(res, onBytes);
      D.meta = { ...data, jobs: undefined }; D.jobs = data.jobs || []; D.loaded = true; index();
      if (D.rejected) D.jobs = D.jobs.concat(D.rejected), index();
      bus.emit("jobs", { reason: "load" }); return D;
    } finally { jobsLoad = null; }
  })());
  FP.loadRejected = async () => {
    if (D.rejected) return;
    const res = await api("/api/jobs?slim=true", { raw: true });
    const data = await readStream(res);
    D.rejected = (data.jobs || []).filter((j) => j.status === "reject");
    D.meta = { ...D.meta, total_rejected: data.total_rejected, rejected_by_category: data.rejected_by_category };
    D.jobs = D.jobs.concat(D.rejected); index(); bus.emit("jobs", { reason: "rejected" });
  };
  FP.job = (uid) => D.by.get(uid);
  FP.newCount = () => D.jobs.filter((j) => j.status !== "reject" && !j.visited_at).length;
  FP.setVisited = async (uids, v) => {
    const stamp = v ? new Date().toISOString() : null; const set = new Set(uids);
    for (const j of D.jobs) if (set.has(j.uid)) j.visited_at = stamp;
    bus.emit("jobs", { reason: "visited", uids });
    try { await api("/api/visited", { json: { uids, visited: v }, quiet: true }); } catch (e) { toast("Couldn't save that: " + e.message, { kind: "bad" }); }
  };
  FP.setStatus = async (uid, status) => {
    const j = FP.job(uid);
    if (j) { j.application = status ? { ...(j.application || {}), status } : null; if (status) j.visited_at = j.visited_at || new Date().toISOString(); bus.emit("jobs", { reason: "status", uids: [uid] }); }
    try { await api("/api/application", { json: { uid, status: status || null }, quiet: true }); bus.emit("dash-stale"); } catch (e) { toast("Couldn't save the status: " + e.message, { kind: "bad" }); }
  };

  /* ---------------------------------------------------------------- live telemetry */
  const L = FP.live;
  const feed = (kind, icon, text, sub = "") => {
    FP.feed.unshift({ at: new Date().toISOString(), kind, icon, text, sub, id: Math.random() });
    if (FP.feed.length > 250) FP.feed.length = 250; bus.emit("feed");
  };
  FP.feedAdd = feed;
  const BOARD = { linkedin: "LinkedIn", indeed: "Indeed", internshala: "Internshala", wellfound: "Wellfound", telegram: "Telegram", careers: "Company pages", naukri: "Naukri" };
  FP.BOARD = BOARD;
  let prev = {}, polling = false, failStreak = 0, lastJobsRefresh = 0;
  async function pollOnce() {
    const t0 = performance.now();
    try {
      const [status, pipeline, apply] = await Promise.all([api("/api/status", { quiet: true }), api("/api/pipeline", { quiet: true }), api("/api/autoapply", { quiet: true })]);
      L.latency = Math.round(performance.now() - t0); L.status = status; L.pipeline = pipeline; L.apply = apply; L.at = Date.now();
      if (L.ok === false) feed("good", "check", "Backend reconnected", `${L.latency} ms`);
      L.ok = true; failStreak = 0; diff(status, pipeline, apply); bus.emit("live", L);
    } catch (e) {
      failStreak++; if (failStreak >= 2 && L.ok !== false) { L.ok = false; feed("bad", "alert", "Lost contact with the backend", "retrying…"); bus.emit("live", L); }
    }
  }
  function diff(st, pl, ap) {
    const live = st.live || {}, boards = live.boards || {};
    const busy = new Set(live.busy || []);
    for (const b of Object.keys({ ...boards })) {
      const was = prev.busy?.has(b), is = busy.has(b);
      if (is && !was) feed("accent", "radar", `Reading ${BOARD[b] || b}…`);
      if (!is && was) { const r = boards[b] || {}; feed(r.error ? "warn" : "good", r.error ? "alert" : "check", `${BOARD[b] || b}: ${r.added ? r.added + " new job" + (r.added === 1 ? "" : "s") : "nothing new"}`, r.error ? String(r.error).slice(0, 90) : ""); }
    }
    const rate = pl.rate || {};
    if (rate.running && !prev.rateRunning) feed("accent", "cpu", "AI rating started", rate.total ? `${n(rate.total)} jobs queued` : "");
    if (rate.running && rate.done - (prev.rateLogged || 0) >= 25) { feed("info", "cpu", `AI rated ${n(rate.done)} of ${n(rate.total)}`); prev.rateLogged = rate.done; }
    if (!rate.running && prev.rateRunning) { feed("good", "check", "AI rating finished", prev.rateTotal ? `${n(prev.rateTotal)} jobs checked` : ""); prev.rateLogged = 0; }
    if (rate.error && rate.error !== prev.rateError) feed("warn", "alert", "AI check problem", String(rate.error).slice(0, 110));
    if (st.fetch?.running && !prev.fetching) feed("accent", "refresh", "Fetch started", "reading every board");
    if (!st.fetch?.running && prev.fetching && !(live.busy || []).length) feed("good", "check", "Fetch finished");
    const a = ap || {};
    const seen = prev.applyLog || new Set();
    (a.log || []).slice(-30).forEach((e) => {
      const k = e.at + e.event + (e.uid || ""); if (seen.has(k) || !prev.applyInit) { seen.add(k); return; } seen.add(k);
      if (e.event === "job_start") return;
      const map = { applied: ["good", "check", "Applied"], emailed: ["good", "mail", "Emailed"], skipped: ["", "skip", "Skipped"], failed: ["bad", "alert", "Failed"], parked: ["warn", "hand", "Needs you"], waiting: ["warn", "hand", "Needs you"], start: ["accent", "bolt", "Auto-apply started"], finished: ["good", "check", "Auto-apply finished"] };
      const m = map[e.event]; if (m) feed(m[0], m[1], `${m[2]}${e.title ? ": " + e.title : ""}${e.company ? " · " + e.company : ""}`, (e.detail || "").slice(0, 100));
    });
    prev.applyLog = seen; prev.applyInit = true;
    prev.busy = busy; prev.rateRunning = !!rate.running; prev.rateTotal = rate.total || prev.rateTotal; prev.rateError = rate.error; prev.fetching = !!st.fetch?.running;
    const active = prev.fetching || busy.size || rate.running || a.running;
    const progressed = rate.running && rate.done !== prev.lastDone;
    const justEnded = (prev.wasActive && !active) || (prev.wasFetch && !prev.fetching);
    prev.lastDone = rate.done; prev.wasActive = !!active; prev.wasFetch = prev.fetching;
    if (D.loaded && (justEnded || ((progressed || prev.fetching || busy.size) && Date.now() - lastJobsRefresh > 9000))) {
      lastJobsRefresh = Date.now(); const before = D.jobs.length;
      FP.loadJobs().then(() => { const d = D.jobs.length - before; if (d > 0) feed("good", "inbox", `${n(d)} new job${d === 1 ? "" : "s"} added to your list`); }).catch(() => {});
    }
  }
  FP.startPolling = () => {
    if (polling) return; polling = true;
    const loop = async () => { if (!document.hidden) await pollOnce(); const act = L.status?.running || L.apply?.running || (L.status?.live?.busy || []).length; setTimeout(loop, document.hidden ? 8000 : act ? 1800 : 4000); };
    loop(); document.addEventListener("visibilitychange", () => !document.hidden && pollOnce());
  };
  FP.isBusy = () => !!(L.status?.fetch?.running || (L.status?.live?.busy || []).length);

  /* ---------------------------------------------------------------- fetch (button + floating panel) */
  FP.startFetch = async (range) => {
    range = range || store.get("range", "latest"); store.set("range", range);
    try { await api(`/api/fetch?hours=${encodeURIComponent(range)}`, { method: "POST" }); feed("accent", "refresh", "Fetch requested", range === "latest" ? "since the last fetch" : range === "all" ? "everything from the last 7 days" : `last ${range} h`); toast("Fetching new jobs…", { kind: "good", ms: 2500 }); pollOnce(); }
    catch (e) { if (e.status === 409) toast("A fetch is already running."); else toast(e.message, { kind: "bad" }); }
  };
  let panelHide = 0;
  function renderFetchPanel() {
    const box = $("#fetchPanel"); if (!box) return; const st = L.status; const m = st?.live?.manual;
    if (!m) { box.hidden = true; return; }
    const boards = st.live.boards || {}, started = m.started * 1000;
    const after = (b) => boards[b] && Date.parse(boards[b].at || 0) >= started - 1000;
    let units = 0, done = 0, found = 0;
    const steps = m.boards.map((b) => {
      const info = boards[b] || {}, busy = !!info.busy, fin = !busy && after(b) && (b !== "linkedin" || m.finished);
      if (after(b)) found += info.added || 0;
      let label = BOARD[b] || b, tail = "";
      if (b === "linkedin") { const r = st.live.linkedin_round; const d = m.finished ? m.li_total : r ? r.done : 0; units += m.li_total; done += d; tail = `${d}/${m.li_total} searches`; }
      else { units += 1; done += fin ? 1 : 0; }
      if (fin && info.added) tail = (tail ? tail + " · " : "") + `${info.added} new`;
      const cls = fin ? (info.error ? "err" : "done") : busy ? "busy" : "";
      return `<div class="step ${cls}"><span class="tick">${fin ? I(info.error ? "alert" : "check", "sm") : busy ? '<span class="spinner"></span>' : ""}</span><span>${esc(label)}</span><span class="faint xs" style="margin-left:auto">${esc(tail)}</span></div>`;
    });
    const readFrac = m.finished ? 1 : units ? done / units : 0; const c = st.check || {}; const aiOn = c.running && c.total;
    const aiFrac = !m.finished ? 0 : aiOn ? c.done / c.total : !c.running ? 1 : 0;
    steps.push(`<div class="step ${aiOn ? "busy" : m.finished && !c.running ? "done" : ""}"><span class="tick">${aiOn ? '<span class="spinner"></span>' : m.finished && !c.running ? I("check", "sm") : ""}</span><span>AI rating</span><span class="faint xs" style="margin-left:auto">${aiOn ? `${c.done}/${c.total}` : ""}</span></div>`);
    const pct = Math.round(100 * (0.75 * readFrac + 0.25 * aiFrac)); const all = m.finished && !c.running;
    if (all && !panelHide) panelHide = Date.now() + 45000; if (!all) panelHide = 0;
    box.hidden = all && Date.now() > panelHide; if (box.dataset.closed === String(m.started)) box.hidden = true;
    const secs = (Date.now() - started) / 1000; let eta = "";
    if (!all) eta = !m.finished && readFrac > 0.05 ? `about ${fmtDur((secs / readFrac) * (1 - readFrac))} left` : m.finished && aiOn ? "AI is rating what was found" : "estimating…";
    box.innerHTML = `<div class="between row nowrap"><b>${all ? `Done in ${fmtDur((m.finished * 1000 - started) / 1000)}` : "Fetching jobs…"}</b><span class="row nowrap"><span class="chip ${all ? "good" : "accent"}">${all ? `${found} new` : pct + "%"}</span><button class="btn ghost sm icon-only" data-close aria-label="Hide">${I("x", "sm")}</button></span></div>
      <div class="progress" style="margin:10px 0 4px"><i style="width:${all ? 100 : pct}%"></i></div><div class="xs faint" style="margin-bottom:10px">${esc(eta)}</div><div class="step-list">${steps.join("")}</div>`;
    box.querySelector("[data-close]").onclick = () => { box.dataset.closed = String(m.started); box.hidden = true; };
  }
  bus.on("live", () => { renderFetchPanel(); renderShellLive(); });

  /* ---------------------------------------------------------------- shell / router */
  const ROUTES = [
    ["today", "Today", "check"], ["home", "Stats", "activity"], ["jobs", "Jobs", "briefcase"], ["apply", "Auto-apply", "bolt"], ["system", "Control room", "activity"], ["profile", "Profile", "user"], ["settings", "Settings", "settings"],
  ];
  const TITLES = Object.fromEntries(ROUTES.map((r) => [r[0], r[1]]));
  let current = null;
  const parse = () => {
    let h = location.hash.replace(/^#\/?/, ""); const alias = { dashboard: "home", "": "today", autoapply: "apply", account: "settings" };
    const [name, ...rest] = h.split("/"); const key = alias[name] ?? name; return { name: FP.views[key] ? key : "today", params: rest.map(decodeURIComponent) };
  };
  async function route() {
    const { name, params } = parse(); const root = $("#view");
    if (current && FP.views[current.name]?.unmount && current.name !== name) FP.views[current.name].unmount();
    const same = current && current.name === name && FP.views[name].update;
    document.body.classList.remove("show-detail");
    current = { name, params };
    $$("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === name));
    $("#pageTitle").textContent = TITLES[name]; document.title = `${TITLES[name]} · FresherPilot`;
    if (same) return FP.views[name].update(params);
    root.className = "view" + (FP.views[name].full ? " full" : ""); root.innerHTML = ""; root.style.animation = "none"; void root.offsetWidth; root.style.animation = "";
    try { await FP.views[name].mount(root, params); } catch (e) { console.error(e); root.innerHTML = `<div class="empty"><div class="art">${I("alert")}</div><h3>This page hit a problem</h3><p>${esc(e.message)}</p><button class="btn" onclick="location.reload()">Reload</button></div>`; }
    root.scrollTop = 0; window.scrollTo(0, 0);
  }
  FP.go = (path) => { location.hash = "#/" + path; };
  FP.route = () => current;

  /* the run bar: on EVERY page while anything is applying, with a Stop button that always works */
  let stopping = 0;
  function renderRunBar(a) {
    const bar = $("#runbar"); if (!bar) return;
    const site = a.site || {}, on = !!a.running || !!site.running;
    if (!on) { stopping = 0; bar.hidden = true; return; }
    const cur = a.running ? a.current : site.current;
    const last = a.running ? (a.steps || []).slice(-1)[0] : (site.steps || []).slice(-1)[0];
    const where = a.running ? "in your browser" : "on a company site";
    const q = (a.running ? (a.total ? `${Math.min(a.index || 0, a.total)} of ${a.total}` : "") : (site.queued ? `${site.queued} more queued` : ""));
    const wasStopping = stopping && Date.now() - stopping < 15000;
    bar.hidden = false;
    bar.innerHTML = `<span class="dot busy"></span><div class="grow" style="min-width:0"><div class="ellipsis"><b>${wasStopping ? "Stopping…" : "Applying " + where}</b>${cur?.title ? " · " + esc(cur.title) : ""}${cur?.company ? ` <span class="muted">· ${esc(cur.company)}</span>` : ""}</div>
      <div class="xs muted ellipsis">${esc(q)}${q && last ? " · " : ""}${last ? esc(String(last.text || "").slice(0, 110)) : ""}</div></div>
      <a class="btn sm" href="#/apply">Watch</a><button class="btn sm danger" id="runStop" ${wasStopping ? "disabled" : ""}>${I("x", "sm")} Stop</button>`;
    $("#runStop").onclick = async () => { stopping = Date.now(); try { await api("/api/autoapply/command", { json: { action: "stop" } }); toast("Stopped. Nothing else will be applied.", { kind: "good" }); } catch (e) { toast("Stop failed: " + e.message, { kind: "bad" }); } pollOnce(); };
  }

  function renderShellLive() {
    const s = L.status || {}, p = L.pipeline || {}, a = L.apply || {};
    const conn = $("#conn"); if (conn) {
      conn.className = "conn" + (L.ok === false ? " bad" : "");
      conn.innerHTML = L.ok === false ? `<span class="dot bad"></span><span class="txt">Reconnecting…</span>` : `<span class="dot ${FP.isBusy() || s.check?.running || a.running ? "busy" : "live"}"></span><span class="txt">${FP.isBusy() ? "Reading boards" : s.check?.running ? "AI rating" : a.running ? "Applying" : "Backend live"}</span><span class="faint xs mono">${L.latency ?? "–"}ms</span>`;
    }
    const pc = $("#pulse"); if (pc) {
      const busyB = (s.live?.busy || []).map((b) => BOARD[b] || b); const rate = p.rate || {};
      const paused = rate.paused_until && rate.paused_until * 1000 > Date.now();
      pc.innerHTML = `<div class="pulse-head"><span>System</span><span class="chip ${L.ok === false ? "bad" : "good"}"><span class="dot ${L.ok === false ? "bad" : "live"}"></span>${L.ok === false ? "offline" : "live"}</span></div>
        <div class="pulse-row"><span class="dot ${busyB.length || s.fetch?.running ? "busy" : ""}"></span><span class="ellipsis"><b>Reading</b> ${busyB.length ? esc(busyB.join(", ")) : "idle"}</span></div>
        <div class="pulse-row"><span class="dot ${rate.running ? "busy" : paused ? "warn" : ""}"></span><span class="ellipsis"><b>AI</b> ${rate.running ? `${n(rate.done)}/${n(rate.total)}` : paused ? "limit reached" : rate.waiting ? `${n(rate.waiting)} waiting` : "all rated"}</span></div>
        <div class="pulse-row"><span class="dot ${a.running ? "busy" : (a.site?.running ? "busy" : "")}"></span><span class="ellipsis"><b>Apply</b> ${a.running ? `${a.index || 0}/${a.total || 0}` : a.site?.running ? "company site" : "ready"}</span></div>`;
    }
    renderRunBar(a);
    const cnt = FP.newCount(); const bd = $("#navNew"); if (bd) { bd.hidden = !cnt; bd.textContent = cnt > 999 ? "999+" : cnt; }
    const fb = $("#fetchBtn"); if (fb) { const busy = FP.isBusy(); fb.classList.toggle("busy", busy && false); fb.innerHTML = busy ? `<span class="spinner"></span> Fetching…` : `${I("refresh")} Fetch new jobs`; fb.disabled = busy; }
  }
  bus.on("jobs", renderShellLive);

  function theme(t) {
    const root = document.documentElement;
    if (t) { store.set("theme", t); }
    const cur = store.get("theme", null) || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    root.dataset.theme = cur; const b = $("#themeBtn"); if (b) b.innerHTML = I(cur === "dark" ? "sun" : "moon");
  }
  FP.toggleTheme = () => theme((document.documentElement.dataset.theme || "dark") === "dark" ? "light" : "dark");

  function buildShell() {
    const nav = ROUTES.filter((r) => r[0] !== "profile" && r[0] !== "settings").map((r) => `<a href="#/${r[0]}" data-nav="${r[0]}">${I(r[2])}<span>${r[1]}</span>${r[0] === "jobs" ? '<span class="count" id="navNew" hidden></span>' : r[0] === "today" ? '<span class="count" id="navToday" hidden></span>' : ""}</a>`).join("");
    const nav2 = ROUTES.filter((r) => r[0] === "profile" || r[0] === "settings").map((r) => `<a href="#/${r[0]}" data-nav="${r[0]}">${I(r[2])}<span>${r[1]}</span></a>`).join("");
    const tabs = ROUTES.filter((r) => ["today", "jobs", "apply", "system", "settings"].includes(r[0])).map((r) => `<a href="#/${r[0]}" data-nav="${r[0]}">${I(r[2], "lg")}<span>${r[0] === "system" ? "Live" : r[1]}</span></a>`).join("");
    document.body.insertAdjacentHTML("afterbegin", `<div class="topload" id="topload"><i></i></div>
    <div class="app">
      <aside class="sidebar">
        <a class="brand" href="#/today"><span class="logo"><svg viewBox="0 0 24 24"><path d="M12 3 4 14h6l-1 7 9-12h-6z"/></svg></span><span><b>FresherPilot</b><small>Never miss a job</small></span></a>
        <nav class="nav" aria-label="Main">${nav}</nav>
        <div class="up nav-label">Account</div><nav class="nav">${nav2}</nav>
        <div class="pulse-card" id="pulse" title="Open the control room"></div>
        <a class="user-chip" href="#/settings"><span id="userAv"></span><span class="grow"><b id="userName" class="ellipsis" style="display:block;font-size:13px">…</b><span class="faint xs">Settings &amp; keys</span></span></a>
      </aside>
      <div class="main">
        <header class="topbar">
          <h1 id="pageTitle">Dashboard</h1><span class="grow"></span>
          <button class="cmdk-btn" id="cmdkBtn" aria-label="Search and commands">${I("search")}<span>Search jobs, jump to…</span><span class="kbd">Ctrl K</span></button>
          <button class="conn" id="conn" title="Live connection to the backend. Click to open the control room"></button>
          <div class="fetch-split"><select class="select" id="fetchRange" aria-label="Fetch range"><option value="latest">Since last fetch</option><option value="1">Past hour</option><option value="3">Past 3 hours</option><option value="24">Past 24 hours</option><option value="all">All 7 days</option></select><button class="btn primary" id="fetchBtn">${I("refresh")} Fetch new jobs</button></div>
          <button class="btn ghost icon-only" id="themeBtn" aria-label="Toggle theme"></button>
        </header>
        <div id="runbar" class="runbar" hidden></div>
        <div id="banners"></div>
        <main id="view" class="view"></main>
      </div>
    </div>
    <nav class="tabbar" aria-label="Main">${tabs}</nav>
    <div class="toasts" id="toasts" aria-live="polite"></div>
    <aside id="fetchPanel" class="card" hidden style="position:fixed;right:20px;bottom:20px;width:320px;z-index:70;box-shadow:var(--shadow-3)"></aside>`);
    $("#fetchRange").value = store.get("range", "latest");
    $("#fetchRange").onchange = (e) => store.set("range", e.target.value);
    $("#fetchBtn").onclick = () => FP.startFetch($("#fetchRange").value);
    $("#themeBtn").onclick = FP.toggleTheme; $("#pulse").onclick = () => FP.go("system"); $("#conn").onclick = () => FP.go("system");
    $("#cmdkBtn").onclick = () => FP.palette(); theme();
  }

  /* ---------------------------------------------------------------- command palette */
  FP.palette = () => {
    if ($("#palette")) return; const prevFocus = document.activeElement;
    const ov = document.createElement("div"); ov.className = "overlay"; ov.id = "palette";
    ov.innerHTML = `<div class="palette" role="dialog" aria-label="Command palette"><input id="pq" placeholder="Search jobs, or type a command…" autocomplete="off" spellcheck="false"><div class="res" id="pres"></div><div class="foot"><span><span class="kbd">↑↓</span> move</span><span><span class="kbd">Enter</span> open</span><span><span class="kbd">Esc</span> close</span></div></div>`;
    document.body.appendChild(ov); const q = $("#pq"), res = $("#pres"); q.focus(); let items = [], sel = 0;
    const cmds = [
      ...ROUTES.map((r) => ({ g: "Go to", t: r[1], i: r[2], run: () => FP.go(r[0]) })),
      { g: "Actions", t: "Fetch new jobs now", i: "refresh", run: () => FP.startFetch() }, { g: "Actions", t: "Toggle light / dark theme", i: "sun", run: FP.toggleTheme },
      { g: "Actions", t: "Show only new jobs", i: "sparkle", run: () => { store.set("jobsq", "new"); FP.go("jobs"); } }, { g: "Actions", t: "Open Auto-apply", i: "bolt", run: () => FP.go("apply") },
      { g: "Actions", t: "Refresh everything", i: "refresh", run: () => location.reload() },
    ];
    const build = () => {
      const s = q.value.trim().toLowerCase(); items = [];
      const c = cmds.filter((x) => !s || x.t.toLowerCase().includes(s)); items.push(...c);
      if (s.length >= 2) {
        const found = []; for (const j of D.jobs) { if (j.status === "reject") continue; if (`${j.title} ${j.employer || j.company}`.toLowerCase().includes(s)) { found.push(j); if (found.length >= 8) break; } }
        items.push(...found.map((j) => ({ g: "Jobs", t: j.title, sub: j.employer || j.company, i: "briefcase", r: j.source, run: () => { store.set("sel", j.uid); FP.go("jobs/" + encodeURIComponent(j.uid)); } })));
      }
      let last = ""; sel = Math.min(sel, Math.max(0, items.length - 1));
      res.innerHTML = items.length ? items.map((x, k) => `${x.g !== last ? `<div class="grp up">${(last = x.g)}</div>` : ""}<div class="it ${k === sel ? "on" : ""}" data-k="${k}">${I(x.i)}<span class="ellipsis"><b>${esc(x.t)}</b>${x.sub ? ` <span class="faint">· ${esc(x.sub)}</span>` : ""}</span>${x.r ? `<span class="r">${esc(x.r)}</span>` : ""}</div>`).join("") : `<div class="empty" style="padding:30px">Nothing matches “${esc(q.value)}”.</div>`;
      res.querySelector(".it.on")?.scrollIntoView({ block: "nearest" });
    };
    const close = () => { ov.remove(); prevFocus?.focus?.(); };
    const run = (k) => { const it = items[k]; if (!it) return; close(); it.run(); };
    q.oninput = () => { sel = 0; build(); };
    q.onkeydown = (e) => { if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); build(); e.preventDefault(); } else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); build(); e.preventDefault(); } else if (e.key === "Enter") run(sel); else if (e.key === "Escape") close(); };
    res.onclick = (e) => { const it = e.target.closest("[data-k]"); if (it) run(+it.dataset.k); }; ov.onmousedown = (e) => { if (e.target === ov) close(); }; build();
  };
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#palette") ? $("#palette").remove() : FP.palette(); } });

  /* ---------------------------------------------------------------- boot */
  const LOGO = '<svg viewBox="0 0 24 24"><path d="M12 3 4 14h6l-1 7 9-12h-6z"/></svg>';
  async function boot() {
    const seen = sessionStorage.getItem("fp.booted") === "1";
    const el = document.createElement("div"); el.className = "boot"; el.id = "boot";
    el.innerHTML = `<div class="boot-card"><span class="logo">${LOGO}</span><div class="center"><h1>FresherPilot</h1><p class="muted small" id="bootSub">Starting up…</p></div><div class="steps" id="bootSteps"></div><div class="progress boot-bar"><i id="bootBar"></i></div></div>`;
    document.body.appendChild(el);
    const steps = [["backend", "Connecting to your backend"], ["account", "Loading your account"], ["pipeline", "Checking readers & AI pipeline"], ["jobs", "Loading your jobs"]];
    $("#bootSteps").innerHTML = steps.map(([k, t]) => `<div class="step" id="bs-${k}"><span class="tick"></span><span>${t}</span><span class="r" id="br-${k}"></span></div>`).join("");
    const mark = (k, cls, r = "") => { const s = $("#bs-" + k); s.className = "step " + cls; s.querySelector(".tick").innerHTML = cls === "done" ? I("check", "sm") : cls === "busy" ? '<span class="spinner"></span>' : cls === "err" ? I("alert", "sm") : ""; $("#br-" + k).textContent = r; };
    const bar = (k) => ($("#bootBar").style.width = Math.round((k / steps.length) * 100) + "%");
    const t0 = performance.now(); let doneN = 0;
    try {
      mark("backend", "busy"); const h0 = performance.now(); await api("/api/health", { quiet: true }); const lat = Math.round(performance.now() - h0); mark("backend", "done", `${lat} ms`); bar(++doneN); feed("good", "check", "Connected to the backend", `${lat} ms`);
      mark("account", "busy"); D.me = await api("/api/me", { quiet: true }); mark("account", "done", D.me.user?.username || ""); bar(++doneN);
      mark("pipeline", "busy"); L.pipeline = await api("/api/pipeline", { quiet: true }).catch(() => null); const live = await api("/api/status", { quiet: true }).catch(() => null); L.status = live; mark("pipeline", "done", live?.check?.running ? "AI rating now" : "idle"); bar(++doneN);
      // The job list (3 MB, 10-50 s to build right after a restart) loads in the BACKGROUND: the app opens at once (Nov 19: a blank boot screen for 48 s)
      mark("jobs", "done", "loading…"); bar(++doneN); FP.jobsLoading = true;
      FP.loadJobs().then(() => { const c = D.jobs.filter((j) => j.status === "keep").length; feed("info", "inbox", `Loaded ${n(c)} matching jobs`, `${n(D.meta.total_rejected || 0)} filtered out by your rules`); })
        .catch((e) => toast(`Couldn't load the job list: ${e.message}`, { kind: "bad" })).finally(() => { FP.jobsLoading = false; const b = $("#jobsBanner"); if (b) b.hidden = true; });
      $("#bootSub").textContent = "All systems go";
    } catch (e) {
      const cur = steps.find(([k]) => $("#bs-" + k).classList.contains("busy")); if (cur) mark(cur[0], "err", "failed");
      $("#bootSub").innerHTML = `Couldn't finish starting: ${esc(e.message)}<br><button class="btn" style="margin-top:12px" onclick="location.reload()">Try again</button>`; throw e;
    }
    const min = seen ? 0 : 900 - (performance.now() - t0); if (min > 0) await sleep(min);
    el.classList.add("done"); setTimeout(() => el.remove(), 600); sessionStorage.setItem("fp.booted", "1");
  }

  function afterBoot() {
    const me = D.me || {}; const u = me.user || {};
    $("#userName").textContent = u.username || "Account"; $("#userAv").innerHTML = avatar(u.username || "U", "sm");
    const setup = me.setup || {}; const missing = [!setup.ai_key && "an AI key (Groq, free)", !setup.resume && "your resume"].filter(Boolean);
    FP.setupMissing = missing.length > 0;
    if (missing.length) $("#banners").innerHTML = `<div style="padding:14px 24px 0"><div class="notice warn">${I("alert")}<div class="grow"><b>Finish setup:</b> add ${missing.join(" and ")} so the AI can check which jobs fit you.</div><a class="btn sm" href="/onboarding">Finish setup</a></div></div>`;
    if (me.extension_token && FP.hasExtension()) FP.toExtension({ type: "jf-set-token", token: me.extension_token }).catch(() => {});
    if (FP.jobsLoading) { const bn = $("#banners"); if (bn) bn.insertAdjacentHTML("beforeend", `<div id="jobsBanner" style="padding:10px 24px 0"><div class="notice info"><span class="spinner"></span><div class="grow">Loading your job list… the rest of the app works meanwhile.</div></div></div>`); }
    FP.startPolling(); renderShellLive();
  }

  FP.start = async () => {
    buildShell(); try { await boot(); } catch { return; }
    afterBoot(); window.addEventListener("hashchange", route); route();
    window.addEventListener("online", () => toast("Back online", { kind: "good" })); window.addEventListener("offline", () => toast("You're offline", { kind: "warn" }));
  };
})();
