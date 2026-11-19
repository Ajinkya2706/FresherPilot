/* Settings: API keys, Telegram, search preferences, account, data. Profile: applicant details used to fill forms. */
(() => {
  const { $, $$, esc, I, api, toast, bus, sleep } = FP;
  const LISTS = ["skills", "roles", "linkedin_titles", "off_stack", "locations", "telegram_channels"];
  const KEYS = [["GROQ_API_KEY", "Groq API key(s)", "Comma-separated. Used in order; the next takes over when one hits its daily limit.", "gsk_…"], ["NVIDIA_API_KEY", "NVIDIA API key(s)", "Optional backup (build.nvidia.com). Used when Groq's main models are used up.", "nvapi-…"], ["APIFY_API_KEY", "Apify API token", "Used for Naukri jobs. The free $5/month plan is enough.", "apify_api_…"], ["GMAIL_ADDRESS", "Gmail address", "Used to send outreach emails.", "you@gmail.com", false], ["GMAIL_APP_PASSWORD", "Gmail app password", "Create one at myaccount.google.com/apppasswords.", ""], ["TELEGRAM_BOT_TOKEN", "Telegram bot token", "From @BotFather. Needed for job alerts.", "123456789:AA…"]];
  let root, me, offs = [];

  /* chip input for comma lists */
  const tagBox = (id, vals, ph) => `<div class="tagbox" data-tags="${id}"><div class="tags">${vals.map((v) => `<span class="chip accent" data-v="${esc(v)}">${esc(v)}<button type="button" class="link" data-x aria-label="Remove" style="margin-left:2px">✕</button></span>`).join("")}</div><input class="tag-in" placeholder="${esc(ph || "Type and press Enter")}"></div>`;
  const tagVals = (id) => $$(`[data-tags="${id}"] .chip`, root).map((c) => c.dataset.v);
  function wireTags() {
    root.addEventListener("keydown", (e) => { const inp = e.target.closest(".tag-in"); if (!inp) return; if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(inp); } else if (e.key === "Backspace" && !inp.value) inp.previousElementSibling.lastElementChild?.remove(); });
    root.addEventListener("focusout", (e) => { if (e.target.closest?.(".tag-in")) add(e.target); });
    root.addEventListener("click", (e) => { const x = e.target.closest("[data-x]"); if (x) x.closest(".chip").remove(); const box = e.target.closest(".tagbox"); if (box && !x) box.querySelector("input").focus(); });
    function add(inp) { const v = inp.value.replace(/,$/, "").trim(); if (!v) return; const box = inp.closest(".tagbox"); if ($$(".chip", box).some((c) => c.dataset.v.toLowerCase() === v.toLowerCase())) { inp.value = ""; return; } const s = document.createElement("span"); s.className = "chip accent"; s.dataset.v = v; s.innerHTML = `${esc(v)}<button type="button" class="link" data-x aria-label="Remove" style="margin-left:2px">✕</button>`; box.querySelector(".tags").appendChild(s); inp.value = ""; }
  }
  const msg = (id, t, kind = "") => { const el = $("#" + id, root); if (el) { el.textContent = t; el.className = "msg " + kind; } };
  const field = (id, label, input, hint = "") => `<label class="field"><span>${label}</span>${input}${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;

  async function loadTelegram() {
    const t = await api("/api/telegram", { quiet: true }).catch(() => ({}));
    const el = $("#tgStatus", root); if (!el) return;
    el.innerHTML = !t.token ? `<span class="chip">Not set up</span> Add a bot token first.` : t.error ? `<span class="chip bad">Problem</span> ${esc(t.error)}` : t.connected ? `<span class="chip good">${I("check", "sm")} Connected</span> bot @${esc(t.bot)}${t.alerts ? "" : " · alerts paused (send /resume to the bot)"}` : `<span class="chip warn">Almost</span> Bot @${esc(t.bot)} found. Now press Connect.`;
    $("#tgTest", root).disabled = !t.connected;
  }

  function render() {
    const s = me.prefs || {}, u = me.user || {}, list = (k) => (s[k] || []).map((x) => String(x).trim()).filter(Boolean);
    root.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Signed in as <b style="color:var(--text)">${esc(u.username)}</b>${u.owner ? ' <span class="chip accent">owner</span>' : ""}</p></div><button class="btn" id="logout">${I("logout")} Log out</button></div>
    <div class="settings"><nav class="snav">${[["keys", "API keys"], ["telegram", "Telegram alerts"], ["search", "Job search"], ["account", "Account"], ["data", "Your data"]].map(([k, l]) => `<a href="#/settings" data-jump="${k}">${l}</a>`).join("")}</nav><div>
      <section class="card sec" id="sec-keys"><div class="card-head"><div><h2>API keys</h2><p class="sub">Stored encrypted, only usable while you're logged in. Saved keys show a green check.</p></div></div><div class="form">
        ${KEYS.map(([k, l, h, ph, secret]) => field(k, `${l} ${me.keys?.[k] ? '<span class="chip good">saved</span>' : ""}`, `<input class="input" id="${k}" ${secret === false ? "" : 'type="password"'} autocomplete="off" placeholder="${me.keys?.[k] ? "saved · type to replace" : esc(ph)}">`, h)).join("")}
        <div class="row"><button class="btn primary" id="saveKeys">Save keys</button><span class="msg" id="keysMsg"></span></div></div></section>
      <section class="card sec" id="sec-telegram"><div class="card-head"><div><h2>Telegram job alerts</h2><p class="sub">Every job that passes the AI check reaches your phone within minutes, with Applied / Seen / Not for me buttons. Free.</p></div></div>
        <ol class="muted small" style="margin:0 0 14px 18px;line-height:1.8"><li>In Telegram open <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a>, send <code>/newbot</code>, pick a name and a username ending in “bot”.</li><li>Paste the token above in <b>Telegram bot token</b> and press <b>Save keys</b>.</li><li>Press <b>Connect Telegram</b>, open the link and tap <b>Start</b>.</li></ol>
        <p class="small" id="tgStatus">Checking…</p><div class="row" style="margin-top:12px"><button class="btn primary" id="tgConnect">Connect Telegram</button><button class="btn" id="tgTest">Send a test message</button><span class="msg" id="tgMsg"></span></div></section>
      <section class="card sec" id="sec-search"><div class="card-head"><div><h2>Job search</h2><p class="sub">The AI matches every job against these. Changes apply from the next fetch.</p></div></div><div class="form">
        ${field("summary", "Summary", `<textarea class="textarea" id="summary" rows="2">${esc(s.summary || "")}</textarea>`, "What you do and want, in a sentence or two.")}
        <div class="grid-2">${field("target_area", "Jobs that fit you", `<input class="input" id="target_area" value="${esc(s.target_area || "")}">`)}${field("headline", "Who you are (used in messages)", `<input class="input" id="headline" value="${esc(s.headline || "")}">`)}</div>
        <div class="grid-2">${field("experience_years", "Years of full-time experience", `<input class="input" id="experience_years" type="number" min="0" step="0.5" value="${esc(s.experience_years ?? "")}">`)}${field("reject_from_years", "Hide jobs asking this many years or more", `<input class="input" id="reject_from_years" type="number" min="1" step="1" value="${esc(s.reject_from_years ?? 1)}">`)}</div>
        <label class="check"><input type="checkbox" id="skilled_freshers" ${s.skilled_freshers !== false ? "checked" : ""}><span>Keep jobs that list years (e.g. “3-5 yrs”) but say skilled freshers / strong projects are welcome</span></label>
        <label class="check"><input type="checkbox" id="stretch_jobs" ${s.stretch_jobs ? "checked" : ""}><span>Also show jobs asking for one year more (e.g. “1-3 yrs”) as “stretch” jobs</span></label>
        ${field("roles", "Job titles to search", tagBox("roles", list("roles"), "e.g. python developer"), "Used for Naukri, Indeed and Internshala.")}
        ${field("linkedin_titles", "LinkedIn searches: job titles (up to 10)", tagBox("linkedin_titles", list("linkedin_titles")), "Also used for Wellfound.")}
        ${field("linkedin_queries", "Extra LinkedIn searches, one per line", `<textarea class="textarea" id="linkedin_queries" rows="3">${esc((s.linkedin_queries || []).join("\n"))}</textarea>`, "LinkedIn's OR / AND / “quotes” work. Up to 6.")}
        ${field("locations", "Cities", tagBox("locations", list("locations"), "e.g. Pune, Remote"), "Empty = all of India. Each extra city adds LinkedIn searches.")}
        ${field("telegram_channels", "Telegram job channels", tagBox("telegram_channels", list("telegram_channels"), "channel name or t.me link"), "Public channels, free.")}
        ${field("off_stack", "Technologies you don't work with", tagBox("off_stack", list("off_stack")), "Jobs with these in the title are skipped for free.")}
        ${field("skills", "Skills", tagBox("skills", list("skills")), "Empty = read from your resume.")}
        ${field("blocked_companies", "Blocked companies, one per line", `<textarea class="textarea" id="blocked_companies" rows="3" placeholder="Bajaj Finance">${esc((s.blocked_companies || []).join("\n"))}</textarea>`, "Their jobs never reach you and are never auto-applied.")}
        <div class="row"><button class="btn primary" id="savePrefs">Save search settings</button><a class="btn ghost" href="/onboarding">Upload a new resume…</a><span class="msg" id="prefsMsg"></span></div></div></section>
      ${me.needs_consent ? `<section class="card sec"><div class="card-head"><h2>Updated terms</h2></div><p class="muted small">Please read the updated <a href="/terms" target="_blank">Terms</a> and <a href="/privacy" target="_blank">Privacy Policy</a>.</p><div class="row" style="margin-top:12px"><button class="btn primary" id="acceptTerms">I agree</button></div></section>` : ""}
      <section class="card sec" id="sec-account"><div class="card-head"><h2>Account</h2></div>
        <div class="form"><p class="small muted" id="googleState">${u.google ? `Google sign-in is on (${esc(u.email)}).` : me.google_client_id ? "Link your Google account to sign in with it too." : "Google sign-in isn't set up on this server."}</p><div id="googleLink"></div>
        ${u.has_password ? `<hr class="divider" style="margin:4px 0"><div class="grid-2">${field("oldPw", "Current password", '<input class="input" id="oldPw" type="password" autocomplete="current-password">')}${field("newPw", "New password (8+ characters)", '<input class="input" id="newPw" type="password" autocomplete="new-password">')}</div><div class="row"><button class="btn" id="savePw">Change password</button><span class="msg" id="pwMsg"></span></div>` : ""}</div></section>
      ${u.owner ? `<section class="card sec" id="invitePanel" hidden><div class="card-head"><div><h2>Invites</h2><p class="sub">Only these emails can create an account (with Google).</p></div></div><div class="form">${field("invites", "Invited emails", '<textarea class="textarea" id="invites" rows="4"></textarea>', "One per line or comma-separated.")}<div class="row"><button class="btn primary" id="saveInvites">Save invites</button><span class="msg" id="invitesMsg"></span></div><div class="up">Members</div><div id="members"></div></div></section>` : ""}
      <section class="card sec" id="sec-data"><div class="card-head"><div><h2>Your data</h2><p class="sub">Download everything stored for your account, or delete it for good. See the <a href="/privacy" target="_blank">Privacy Policy</a>.</p></div></div><div class="row"><a class="btn" href="/api/account/export">${I("download")} Download my data (.zip)</a></div>
        ${u.owner ? "" : `<div class="row" style="margin-top:14px"><input class="input" id="deleteConfirm" placeholder="Type DELETE to confirm" style="max-width:240px"><button class="btn danger" id="deleteAccount">${I("trash")} Delete my account</button><span class="msg" id="deleteMsg"></span></div>`}</section></div></div>`;
    loadTelegram(); if (u.owner) loadInvites(); googleLink();
  }

  function googleLink() {
    const u = me.user; if (u.google || !me.google_client_id) return; const sc = document.createElement("script"); sc.src = "https://accounts.google.com/gsi/client"; sc.async = true;
    sc.onload = () => { google.accounts.id.initialize({ client_id: me.google_client_id, callback: async (r) => { try { const d = await api("/api/account/google", { json: { credential: r.credential } }); $("#googleLink", root).hidden = true; $("#googleState", root).textContent = `Google sign-in is on (${d.user.email}).`; toast("Google linked", { kind: "good" }); } catch (e) { toast(e.message, { kind: "bad" }); } } }); google.accounts.id.renderButton($("#googleLink", root), { theme: "outline", size: "medium", text: "signin_with" }); };
    document.head.appendChild(sc);
  }
  function members(list) { const box = $("#members", root); box.innerHTML = list.map((m) => `<div class="row between" style="padding:9px 0;border-bottom:1px solid var(--line)"><span>${esc(m.username)}${m.email ? ` <span class="faint">· ${esc(m.email)}</span>` : ""}${m.owner ? ' <span class="chip accent">owner</span>' : ""}</span>${m.owner ? "" : `<button class="btn sm danger" data-rm="${esc(m.id)}" data-name="${esc(m.username)}">Remove</button>`}</div>`).join(""); }
  async function loadInvites() { try { const d = await api("/api/admin/invites", { quiet: true }); $("#invitePanel", root).hidden = false; $("#invites", root).value = d.emails.join("\n"); members(d.users); } catch {} }

  const KEYF = KEYS.map((k) => k[0]);
  async function saveKeys() {
    const body = {}; for (const k of KEYF) { const v = $("#" + k, root).value.trim(); if (v) body[k] = v; }
    if (!Object.keys(body).length) return msg("keysMsg", "Nothing to save.", "bad");
    try { await api("/api/account/keys", { method: "PUT", json: body }); me = await api("/api/me", { quiet: true }); FP.data.me = me; toast("Keys saved (encrypted)", { kind: "good" }); render(); }
    catch (e) { msg("keysMsg", "Couldn't save the keys.", "bad"); }
  }
  async function savePrefs() {
    const v = (id) => $("#" + id, root).value.trim(), lines = (id) => v(id).split("\n").map((x) => x.trim()).filter(Boolean);
    const p = { summary: v("summary"), target_area: v("target_area"), headline: v("headline"), experience_years: Number(v("experience_years") || 0), reject_from_years: Math.max(1, Number(v("reject_from_years") || 1)), stretch_jobs: $("#stretch_jobs", root).checked, skilled_freshers: $("#skilled_freshers", root).checked, blocked_companies: lines("blocked_companies") };
    for (const k of LISTS) p[k] = tagVals(k); p.linkedin_titles = p.linkedin_titles.slice(0, 10); p.linkedin_queries = lines("linkedin_queries").slice(0, 6);
    p.off_stack = p.off_stack.map((w) => (/^[a-z]+$/i.test(w) ? w.toLowerCase() + " " : w.toLowerCase()));
    const b = $("#savePrefs", root); b.classList.add("busy");
    try { await api("/api/account/prefs", { method: "PUT", json: p }); toast("Search settings saved. They apply from the next fetch.", { kind: "good" }); msg("prefsMsg", "Saved"); } catch (e) { msg("prefsMsg", "Couldn't save", "bad"); toast(e.message, { kind: "bad" }); } finally { b.classList.remove("busy"); }
  }

  FP.views.settings = {
    async mount(el) {
      root = el; root.innerHTML = `<div class="sk block" style="height:90px"></div><div class="sk block" style="height:300px;margin-top:14px"></div>`;
      me = await api("/api/me"); FP.data.me = me; render(); wireTags();
      root.onclick = async (e) => {
        const t = (s) => e.target.closest(s), id = (t("button,a") || {}).id;
        const j = t("[data-jump]"); if (j) { e.preventDefault(); $("#sec-" + j.dataset.jump, root)?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
        if (id === "saveKeys") return saveKeys(); if (id === "savePrefs") return savePrefs();
        if (id === "logout") { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); location.href = "/login"; }
        if (id === "tgConnect") { try { const d = await api("/api/telegram/connect", { method: "POST" }); window.open(d.link, "_blank"); msg("tgMsg", "Opened Telegram: tap Start there, then come back."); for (let i = 0; i < 40 && root.isConnected; i++) { await sleep(3000); const x = await api("/api/telegram", { quiet: true }).catch(() => ({})); if (x.connected) { msg("tgMsg", "Connected", "good"); return loadTelegram(); } } } catch (x) { msg("tgMsg", x.message, "bad"); } }
        if (id === "tgTest") { try { await api("/api/telegram/test", { method: "POST" }); msg("tgMsg", "Sent. Check Telegram.", "good"); } catch (x) { msg("tgMsg", x.message, "bad"); } }
        if (id === "acceptTerms") { try { await api("/api/account/consent", { method: "POST" }); me.needs_consent = false; render(); toast("Thanks", { kind: "good" }); } catch { toast("Couldn't save", { kind: "bad" }); } }
        if (id === "saveInvites") { const emails = $("#invites", root).value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean); try { const d = await api("/api/admin/invites", { method: "PUT", json: { emails } }); $("#invites", root).value = d.emails.join("\n"); members(d.users); msg("invitesMsg", `Saved (${d.emails.length} invited)`, "good"); } catch (x) { msg("invitesMsg", x.message, "bad"); } }
        const rm = t("[data-rm]"); if (rm && (await FP.confirm({ title: `Remove ${rm.dataset.name}?`, text: "This also deletes all their data.", ok: "Remove", danger: true }))) { try { const d = await api(`/api/admin/users/${encodeURIComponent(rm.dataset.rm)}`, { method: "DELETE" }); members(d.users); } catch (x) { toast(x.message, { kind: "bad" }); } }
        if (id === "savePw") { try { await api("/api/account/password", { json: { old: $("#oldPw", root).value, new: $("#newPw", root).value } }); msg("pwMsg", "Password changed", "good"); } catch (x) { msg("pwMsg", x.message, "bad"); } }
        if (id === "deleteAccount") { if ($("#deleteConfirm", root).value !== "DELETE") return msg("deleteMsg", "Type DELETE first.", "bad"); try { await api("/api/account/delete", { json: { confirm: "DELETE" } }); location.href = "/login"; } catch (x) { msg("deleteMsg", x.message, "bad"); } }
      };
    },
  };

  /* ---------------------------------------------------------------- profile */
  const LABELS = { first_name: "First name", middle_name: "Middle name", last_name: "Last name", full_name: "Full name", email: "Email", phone: "Phone (10 digits)", phone_country_code: "Country code", city: "City", state: "State", country: "Country", pincode: "Pincode", address: "Address", date_of_birth: "Date of birth (YYYY-MM-DD)", gender: "Gender", nationality: "Nationality", linkedin: "LinkedIn URL", github: "GitHub URL", portfolio: "Portfolio / website", leetcode: "LeetCode URL", total_experience_years: "Total experience (years)", relevant_experience: "Relevant experience", current_company: "Current company", current_ctc_lpa: "Current CTC (LPA)", expected_ctc_lpa: "Expected CTC (LPA)", notice_period: "Notice period", willing_to_relocate: "Willing to relocate", preferred_locations: "Preferred locations", work_mode: "Work mode", authorized_to_work_in_india: "Authorized to work in India", requires_visa_sponsorship: "Needs visa sponsorship", graduation_year: "Graduation year", available_from: "Available from", disability: "Disability", veteran: "Veteran", caste_category: "Category (optional)", hispanic_latino: "Hispanic / Latino (US forms)", race_ethnicity: "Race / ethnicity (US forms)", end_year: "End year", start_year: "Start year", cgpa: "CGPA", percentage: "Percentage" };
  const TITLES = { personal: "Personal details", links: "Links", job_preferences: "Job preferences", diversity: "Diversity questions (optional; blank = “prefer not to say”)", education: "Education", experience: "Work experience", custom_answers: "Saved answers" };
  const pretty = (k) => LABELS[k] || k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  let prof = null, missing = [];
  const isLong = (k, v) => String(v ?? "").length > 70 || /summary|description|address|answer|about/.test(k);
  const pfield = (attrs, k, v, miss) => `<label class="field ${miss ? "missing" : ""}"><span>${esc(pretty(k))}</span>${isLong(k, v) ? `<textarea class="textarea" ${attrs} rows="2">${esc(v)}</textarea>` : `<input class="input" ${attrs} value="${esc(v)}">`}</label>`;
  function renderProfile(el) {
    let h = `<div class="page-head"><div><h1>Applicant profile</h1><p>Used to fill application forms (browser extension) and to write cover letters and answers. <span style="color:var(--warn)">Highlighted fields are empty</span>: forms asking for them will be left for you.</p></div><a class="btn" href="/api/resume" download>${I("download")} Resume PDF</a></div><div class="form" style="max-width:980px">`;
    for (const [key, val] of Object.entries(prof)) {
      if (val && typeof val === "object" && !Array.isArray(val) && key !== "custom_answers") {
        const flat = Object.entries(val).filter(([, v]) => v === null || typeof v !== "object");
        if (!flat.length) continue;
        h += `<section class="card"><div class="card-head"><h3>${esc(TITLES[key] || pretty(key))}</h3></div><div class="grid-2">${flat.map(([k, v]) => pfield(`data-sec="${esc(key)}" data-key="${esc(k)}"`, k, v, missing.includes(`${key}.${k}`))).join("")}</div></section>`;
      } else if (Array.isArray(val) && val.length && typeof val[0] === "object") {
        h += `<section class="card"><div class="card-head"><h3>${esc(TITLES[key] || pretty(key))}</h3></div><div class="col">${val.map((it, i) => `<div class="repeat"><div class="grid-2">${Object.entries(it).filter(([, v]) => typeof v !== "object").map(([k, v]) => pfield(`data-arr="${esc(key)}" data-i="${i}" data-key="${esc(k)}"`, k, v)).join("")}</div></div>`).join("")}</div></section>`;
      }
    }
    const ca = Object.entries(prof.custom_answers || {});
    h += `<section class="card"><div class="card-head"><div><h3>Saved answers</h3><div class="sub">Exact answers for questions you get often (matched by question text). Everything else is answered by AI from your resume.</div></div></div><div class="col" id="answers">${ca.map(([q, a], i) => `<div class="repeat"><label class="field"><span>Question</span><input class="input" data-q="${i}" value="${esc(q)}"></label><label class="field"><span>Answer</span><textarea class="textarea" data-a="${i}">${esc(a)}</textarea></label><button type="button" class="btn sm danger" data-rmans="${i}" style="align-self:flex-start">Remove</button></div>`).join("")}</div><div style="margin-top:12px"><button class="btn" id="addAns">${I("plus", "sm")} Add a saved answer</button></div></section></div>
      <div class="savebar"><button class="btn primary" id="saveProf">Save profile</button><span class="msg" id="profMsg"></span></div>`;
    el.innerHTML = h;
  }
  function readProfile() {
    const out = JSON.parse(JSON.stringify(prof)), r = root;
    $$("[data-sec]", r).forEach((x) => (out[x.dataset.sec][x.dataset.key] = x.value.trim()));
    $$("[data-arr]", r).forEach((x) => (out[x.dataset.arr][+x.dataset.i][x.dataset.key] = x.value.trim()));
    out.custom_answers = {}; $$("[data-q]", r).forEach((q) => { const a = $(`[data-a="${q.dataset.q}"]`, r); if (q.value.trim()) out.custom_answers[q.value.trim()] = a.value.trim(); });
    return out;
  }
  FP.views.profile = {
    async mount(el) {
      root = el; root.innerHTML = `<div class="sk block" style="height:80px"></div><div class="sk block" style="height:260px;margin-top:14px"></div>`;
      const d = await api("/api/profile"); prof = d.profile; missing = d.missing || []; renderProfile(root);
      root.onclick = async (e) => {
        if (e.target.closest("#addAns")) { prof = readProfile(); prof.custom_answers["New question"] = ""; renderProfile(root); $$("[data-q]", root).pop()?.focus(); }
        const rm = e.target.closest("[data-rmans]"); if (rm) { prof = readProfile(); delete prof.custom_answers[Object.keys(prof.custom_answers)[+rm.dataset.rmans]]; renderProfile(root); }
        if (e.target.closest("#saveProf")) { const b = $("#saveProf", root); b.classList.add("busy"); try { const r = await api("/api/profile", { method: "PUT", json: { profile: readProfile() } }); prof = r.profile; missing = r.missing || []; renderProfile(root); toast("Profile saved", { kind: "good" }); } catch (x) { msg("profMsg", x.message, "bad"); toast(x.message, { kind: "bad" }); } finally { b.classList.remove("busy"); } }
      };
    },
  };
})();
