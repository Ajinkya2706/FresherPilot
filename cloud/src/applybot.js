// Cloud side of the laptop's company-site applier: the AI proxy, the OTP relay through Telegram, notifications.
// (The GitHub-hosted apply runner, its queue dispatch, the 🤖 button and /apply commands were removed Nov 18: unused.)
//   a portal asks for a verification code or link -> runner POSTs otp/request -> Telegram -> the owner replies -> runner GETs otp

let ready = false;
export async function ensureApply(env) {
  if (ready) return;
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS apply_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT UNIQUE, url TEXT, title TEXT, company TEXT, source TEXT,
      status TEXT NOT NULL, attempts INTEGER DEFAULT 0, detail TEXT, steps TEXT, created INTEGER, updated INTEGER)`),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS apply_queue_status ON apply_queue(status)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS apply_accounts (domain TEXT PRIMARY KEY, email TEXT, at INTEGER)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS apply_otp (req TEXT PRIMARY KEY, queue_id INTEGER, kind TEXT, hint TEXT, domain TEXT, code TEXT, at INTEGER)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS apply_files (name TEXT PRIMARY KEY, mime TEXT, body TEXT)"),
  ]);
  ready = true;
}

const GH = (env) => ({ Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "fresherpilot-cloud", "X-GitHub-Api-Version": "2022-11-28" });
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const RUNNER_ALIVE_MS = 4 * 60 * 1000;
const DONE = ["applied", "needs_you", "failed", "closed", "blocked", "skipped"];
// Portals that need the owner's own logged-in browser (LinkedIn Easy Apply, Naukri, Indeed, Internshala, Wellfound): the local runner on his machine
// takes those; every other link (company career sites) is done by the GitHub runner. Both drain the same queue by scope.
const LOCAL_SQL = "('LinkedIn','Naukri','Indeed','Internshala','Wellfound','Foundit')";
const scopeWhere = (scope) => (scope === "local" ? `source IN ${LOCAL_SQL}` : `source NOT IN ${LOCAL_SQL}`);

// Put a job in the queue (once per uid). Returns "queued" | "exists" | "no_link".
export async function enqueueApply(env, H, job, why = "") {
  await ensureApply(env);
  const url = String(job.url || "");
  if (!/^https?:/.test(url)) return "no_link";
  // The owner's LinkedIn (5k connections) is never driven by automation: LinkedIn's terms forbid it and enforcement ends in restrictions / bans.
  // /applylinkedin on lifts this (not recommended).
  if (/^LinkedIn$/i.test(String(job.source || "")) && !(await H.getState(env, "apply_linkedin", false))) return "linkedin_excluded";
  const uid = String(job.uid || job.id || url);
  const t = H.now();
  const r = await env.DB.prepare("INSERT OR IGNORE INTO apply_queue (uid, url, title, company, source, status, created, updated) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)")
    .bind(uid, url, String(job.title || "").slice(0, 160), String(job.company || "").slice(0, 100), String(job.source || ""), t, t).run();
  return r.meta?.changes ? "queued" : "exists";
}

const STATUS_LINE = {
  applied: "✅ <b>Applied</b>", needs_you: "⚠️ <b>Needs you</b>", failed: "❌ <b>Auto-apply failed</b>", closed: "🚫 <b>Job closed</b>",
  blocked: "🛑 <b>Blocked (CAPTCHA / bot check)</b>", skipped: "⏭️ <b>Skipped</b>",
};

export async function applyRoute(req, env, url, H) {
  const p = url.pathname;
  if (!p.startsWith("/api/apply")) return null;
  await ensureApply(env);
  const { json } = H;
  const t = H.now();
  const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};

  if (p === "/api/apply/enqueue" && req.method === "POST") return json({ result: await enqueueApply(env, H, body) });

  if (p === "/api/apply/file") {
    if (req.method === "POST") {   // owner uploads profile.json / resume.pdf once (body: {name, mime, body})
      if (!["profile", "resume"].includes(body.name) || !body.body) return json({ detail: "bad file" }, 400);
      await env.DB.prepare("INSERT INTO apply_files (name, mime, body) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET mime = excluded.mime, body = excluded.body")
        .bind(body.name, body.mime || "", String(body.body)).run();
      return json({ ok: true });
    }
    const row = await env.DB.prepare("SELECT mime, body FROM apply_files WHERE name = ?").bind(url.searchParams.get("name") || "").first();
    return row ? json(row) : json({ detail: "no such file" }, 404);
  }

  if (p === "/api/apply/claim") {   // a runner takes the oldest waiting job of its scope (cloud = GitHub runner, local = the owner's machine)
    const scope = url.searchParams.get("scope") === "local" ? "local" : "cloud";
    await H.setState(env, scope === "local" ? "apply_alive_local" : "apply_alive", t);
    const skip = (url.searchParams.get("skip") || "").split(",").map((x) => x.replace(/[^A-Za-z]/g, "")).filter(Boolean);   // sources that hit today's cap
    const skipSql = skip.length ? ` AND source NOT IN (${skip.map((x) => `'${x}'`).join(",")})` : "";
    const job = await env.DB.prepare(`SELECT * FROM apply_queue WHERE status = 'queued' AND ${scopeWhere(scope)}${skipSql} ORDER BY id LIMIT 1`).first();
    if (!job) return json({ job: null });
    await env.DB.prepare("UPDATE apply_queue SET status = 'running', updated = ? WHERE id = ? AND status = 'queued'").bind(t, job.id).run();
    const accts = (await env.DB.prepare("SELECT domain FROM apply_accounts").all()).results.map((r) => r.domain);
    const prof = await env.DB.prepare("SELECT body FROM apply_files WHERE name = 'profile'").first();
    return json({ job, accounts: accts, profile: prof ? JSON.parse(prof.body) : null });
  }

  if (p === "/api/apply/notify" && req.method === "POST") {   // the Gmail watcher forwards codes / verification links to Telegram
    await H.tg(env, new H.Budget(5), "sendMessage", { chat_id: env.TELEGRAM_CHAT_ID, text: String(body.text || "").slice(0, 900), parse_mode: "HTML", disable_web_page_preview: true,
      ...(/^[A-Za-z0-9]{4,10}$/.test(String(body.copy || "")) ? { reply_markup: { inline_keyboard: [[{ text: `📋 Copy ${body.copy}`, copy_text: { text: String(body.copy) } }]] } } : {}) });
    return json({ ok: true });
  }
  if (p === "/api/apply/mode" && req.method === "POST") {   // owner switch (same as /applylive, /applydry on Telegram)
    await H.setState(env, "apply_dry", !!body.dry);
    return json({ dry: !!body.dry });
  }
  if (p === "/api/apply/dry") return json({ dry: await H.getState(env, "apply_dry", true) });
  if (p === "/api/apply/alive") { await H.setState(env, "apply_alive", t); await env.DB.prepare("UPDATE apply_queue SET updated = ? WHERE id = ? AND status = 'running'").bind(t, +body.id || 0).run(); return json({ ok: true }); }

  if (p === "/api/apply/account" && req.method === "POST") {
    await env.DB.prepare("INSERT INTO apply_accounts (domain, email, at) VALUES (?, ?, ?) ON CONFLICT(domain) DO UPDATE SET at = excluded.at").bind(String(body.domain || ""), String(body.email || ""), t).run();
    return json({ ok: true });
  }

  if (p === "/api/apply/result" && req.method === "POST") {
    const st = DONE.includes(body.status) ? body.status : "failed";
    const job = await env.DB.prepare("SELECT * FROM apply_queue WHERE id = ?").bind(+body.id || 0).first();
    if (!job) return json({ detail: "no such job" }, 404);
    await env.DB.prepare("UPDATE apply_queue SET status = ?, detail = ?, steps = ?, updated = ? WHERE id = ?")
      .bind(st, String(body.detail || "").slice(0, 600), String(body.steps || "").slice(0, 4000), t, job.id).run();
    if (st === "applied" || st === "closed") {   // the same effect as the ✅ button: the laptop app marks it, /jobs stops showing it
      await env.DB.batch([
        env.DB.prepare("INSERT INTO actions (uid, action, at) VALUES (?, ?, ?)").bind(job.uid, st === "applied" ? "a" : "x", t),
        env.DB.prepare("UPDATE alerts SET state = ? WHERE uid = ?").bind(st === "applied" ? "applied" : "hidden", job.uid),
      ]);
    }
    const line = `${STATUS_LINE[st]} — ${H.esc(job.title)} (${H.esc(job.company)})` + (body.detail ? `\n${H.esc(String(body.detail).slice(0, 500))}` : "")
      + (st === "needs_you" || st === "failed" || st === "blocked" ? `\n${H.esc(job.url)}` : "");
    if (st === "skipped" && /^Easy Apply: handed/i.test(String(body.detail || ""))) return json({ ok: true });
    if (st !== "applied") return json({ ok: true });   // problems are collected into one digest (below), not one message each
    if (st === "failed" && /^Runner error|stopped/i.test(String(body.detail || ""))) return json({ ok: true });   // internal hiccups are not worth a message
    await H.tg(env, new H.Budget(5), "sendMessage", { chat_id: env.TELEGRAM_CHAT_ID, text: line, parse_mode: "HTML", disable_web_page_preview: true });
    return json({ ok: true });
  }

  if (p === "/api/apply/otp/request" && req.method === "POST") {
    const reqId = `${+body.id || 0}-${t}`;
    await env.DB.prepare("INSERT INTO apply_otp (req, queue_id, kind, hint, domain, at) VALUES (?, ?, ?, ?, ?, ?)").bind(reqId, +body.id || 0, String(body.kind || "code"), String(body.hint || "").slice(0, 200), String(body.domain || ""), t).run();
    await H.setState(env, "apply_otp_open", { req: reqId, at: t });
    if (body.kind === "login") {   // the local runner's Chrome is logged out of a job portal: one-time sign-in by the owner (no reply needed)
      await H.tg(env, new H.Budget(5), "sendMessage", { chat_id: env.TELEGRAM_CHAT_ID, parse_mode: "HTML",
        text: `🔑 Please sign in to <b>${H.esc(body.domain || "the portal")}</b> in the Chrome window that opened on your laptop (only needed once). I carry on by myself afterwards.` });
      return json({ req: reqId });
    }
    const what = body.kind === "link" ? "the <b>verification link</b> from the email" : "the <b>verification code</b>";
    await H.tg(env, new H.Budget(5), "sendMessage", { chat_id: env.TELEGRAM_CHAT_ID, parse_mode: "HTML",
      text: `🔐 <b>${H.esc(body.domain || "A portal")}</b> needs ${what} (it was emailed to you).\n${body.hint ? H.esc(String(body.hint).slice(0, 160)) + "\n" : ""}Reply here with just the ${body.kind === "link" ? "link" : "code"} — I wait about 10 minutes.` });
    return json({ req: reqId });
  }
  if (p === "/api/apply/otp") {
    const row = await env.DB.prepare("SELECT code FROM apply_otp WHERE req = ?").bind(url.searchParams.get("req") || "").first();
    return json({ code: row && row.code ? row.code : null });
  }

  if (p === "/api/apply/ai" && req.method === "POST") {   // the runner's text AI (keys stay here; usage is logged under step "apply")
    try {
      const items = await H.groq(env, new H.Budget(12), String(body.system || ""), String(body.user || "").slice(0, 14000), body.schema, "apply", true, body.effort || "low");
      return json({ r: items });
    } catch (e) { return json({ r: null, error: String(e && e.message || e).slice(0, 200) }, 200); }
  }

  if (p === "/api/apply/status") {
    const rows = (await env.DB.prepare("SELECT id, status, title, company, attempts, detail, updated FROM apply_queue ORDER BY id DESC LIMIT 25").all()).results;
    return json({ cloud_runner_ms_ago: t - (await H.getState(env, "apply_alive", 0)), local_runner_ms_ago: t - (await H.getState(env, "apply_alive_local", 0)),
                  dry_run: await H.getState(env, "apply_dry", true), queue: rows });
  }
  if (p === "/api/apply/requeue" && req.method === "POST") {   // owner retry of a finished job
    await env.DB.prepare("UPDATE apply_queue SET status = 'queued', attempts = 0, detail = '', updated = ? WHERE id = ?").bind(t, +body.id || 0).run();
    return json({ ok: true });
  }
  return json({ detail: "not found" }, 404);
}

// A code or link typed to the bot while a portal waits for it (the laptop runner asks, the owner replies here).
export async function applyTelegram(env, b, m, say, H, repo) {
  await ensureApply(env);
  const text = String(m.text || "").trim();
  const open = await H.getState(env, "apply_otp_open", null);
  const waiting = open && H.now() - open.at < 12 * 60000;
  if (waiting && text && !text.startsWith("/")) {
    const link = text.match(/https?:\/\/\S+/);
    const code = text.match(/^(?:code[:\s]*)?([A-Za-z0-9]{4,10})$/i);
    const val = link ? link[0] : code ? code[1] : "";
    if (val) {
      await env.DB.prepare("UPDATE apply_otp SET code = ? WHERE req = ?").bind(val, open.req).run();
      await H.setState(env, "apply_otp_open", null);
      await say("👍 Got it, passing it on.");
      return true;
    }
  }
  return false;
}
