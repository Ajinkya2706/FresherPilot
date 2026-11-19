/* Outreach: contacts for a job, ready-made drafts, one-click Gmail / WhatsApp sending. */
(() => {
  const { esc, I, api, toast, safeUrl, when, bus, sleep, avatar } = FP;
  const enc = encodeURIComponent;
  const O = (FP.outreach = { contacts: {}, previews: {}, st: { uid: null, p: null, sending: false, focus: null } });
  const BAD = /^(no-?reply|do-?not-?reply|donotreply|privacy|abuse|legal|unsubscribe|press|media|sales|support|help|helpdesk|security|postmaster|webmaster|admin|billing|marketing|grievance)([._-].*)?@/i;
  const FAKE = /@(example|mysite|yoursite|yourdomain|domain|yourcompany|company|email|test|sample|website|mail)\.(com|in|org|net|co)$/i;
  const ORIGIN = { listed: ["good", "In the job post"], "job post": ["good", "In the job post"], public: ["good", "Public on the web"], "found online": ["good", "Public on the web"], guessed: ["warn", "Guessed · verify"] };
  const ROLE = { recruiter: "Recruiter / HR", leader: "Hiring leader", employee: "Works there" };
  const badge = (k) => { const [c, t] = ORIGIN[k] || ["", k]; return `<span class="chip ${c}">${esc(t)}</span>`; };
  const gmailUrl = (sender, to, su, body) => `https://mail.google.com/mail/?authuser=${enc(sender)}&view=cm&fs=1&tf=1&to=${enc(to)}&su=${enc(su)}&body=${enc(body)}`;
  const digits = (raw) => { let x = String(raw || "").replace(/\D/g, ""); if (x.length === 11 && x.startsWith("0")) x = x.slice(1); if (x.length === 10 && /^[6-9]/.test(x)) return "91" + x; if (x.length === 12 && /^91[6-9]/.test(x)) return x; return ""; };
  const fill = (t, v) => String(t || "").replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m)).replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const personVals = (p, name) => { const f = (String(name || "").match(/[A-Za-z]{2,}/) || [""])[0]; return { ...p.values, name: f ? f[0].toUpperCase() + f.slice(1).toLowerCase() : p.values.name }; };
  const copyBtn = (v) => `<button class="btn ghost sm icon-only" data-copy="${esc(v)}" title="Copy">${I("copy", "sm")}</button>`;
  const refresh = (uid) => bus.emit("detail-refresh", uid);

  /* ---- contacts */
  O.loadContacts = async (uid, force = false) => {
    const job = FP.job(uid); if (!job || job.status === "reject") return;
    const cur = O.contacts[uid]; if (cur && !force && !cur.loading) return; if (cur?.loading) return;
    O.contacts[uid] = { loading: true }; refresh(uid);
    try {
      const d = await api(`/api/contacts?uid=${enc(uid)}${force ? "&refresh=true" : ""}`, { quiet: true });
      O.contacts[uid] = { loading: false, data: d };
      if (d.employer && !job.employer) { job.employer = d.employer; bus.emit("jobs", { reason: "employer" }); }
      if (d.company) { const x = d.from_description || { emails: [], phones: [] }; for (const j of FP.data.jobs) if (j.employer && j.employer === job.employer && j.status !== "reject") j.contacts_summary = { people: d.company.people.length, emails: d.company.emails.length + x.emails.length, phones: d.company.phones.length + x.phones.length, searched: true }; }
    } catch (e) { O.contacts[uid] = { loading: false, data: { status: "search_failed", error: e.message } }; }
    refresh(uid); preview(uid);
  };
  function preview(uid) {
    const c = O.previews[uid]; if (c) return c.data || null;
    if (!O.contacts[uid]?.data || O.contacts[uid].loading) return null;
    O.previews[uid] = { loading: true };
    api(`/api/outreach?uid=${enc(uid)}`, { quiet: true }).then((data) => (O.previews[uid] = { data })).catch(() => (O.previews[uid] = { error: true })).finally(() => refresh(uid));
    return null;
  }
  const gmailBtn = (job, addr, name = "") => {
    const p = preview(job.uid); if (!p || BAD.test(addr) || FAKE.test(addr)) return ""; const v = personVals(p, name);
    return `<a class="btn sm" href="${esc(gmailUrl(p.sender, addr, fill(p.settings.email_subject, v), fill(p.settings.email_body, v)))}" target="_blank" rel="noopener" title="Opens Gmail (${esc(p.sender)}) with the message filled in">${I("mail", "sm")} Gmail</a>`;
  };
  const emailRow = (job, addr, kind, source = "") => FAKE.test(addr) ? "" : `<li>${I("mail")}<span class="v grow">${esc(addr)}</span>${BAD.test(addr) ? '<span class="chip">not a hiring inbox</span>' : badge(kind)}${copyBtn(addr)}${BAD.test(addr) ? "" : gmailBtn(job, addr)}${source ? `<a class="small" href="${esc(safeUrl(source))}" target="_blank" rel="noopener">source</a>` : ""}</li>`;
  const phoneRow = (job, raw, kind, source = "") => {
    const num = digits(raw), p = preview(job.uid);
    const wa = num && p ? `<a class="btn sm" href="https://wa.me/${num}?text=${enc(fill(p.settings.whatsapp_body, p.values))}" target="_blank" rel="noopener">WhatsApp</a>` : "";
    return `<li>${I("phone")}<a class="v grow" href="tel:${esc(raw)}" style="color:inherit">${esc(raw)}</a>${num ? badge(kind) : '<span class="chip">landline · call</span>'}${copyBtn(raw)}${wa}${source ? `<a class="small" href="${esc(safeUrl(source))}" target="_blank" rel="noopener">source</a>` : ""}</li>`;
  };
  function estimate(job) {
    const d = O.contacts[job.uid]?.data; if (!d) return null; const jd = d.from_description || { emails: [], phones: [] }, c = d.company || {};
    const emails = new Set([...jd.emails, ...(c.emails || []).map((e) => e.value)].map((e) => e.toLowerCase()).filter((e) => !BAD.test(e)));
    const mob = (p) => { let x = String(p).replace(/\D/g, ""); if (x.length === 11 && x.startsWith("0")) x = x.slice(1); if (x.length === 12 && x.startsWith("91")) x = x.slice(2); return x.length === 10 && /^[6-9]/.test(x) ? x : ""; };
    const phones = new Set([...jd.phones, ...(c.phones || []).map((p) => p.value)].map(mob).filter(Boolean));
    return { emails: emails.size, phones: phones.size, guessed: (d.guessed?.mx && d.guessed.emails?.length) || 0 };
  }
  O.bar = (job) => {
    if (job.status === "reject") return ""; const sent = job.outreach, e = O.contacts[job.uid], uid = esc(job.uid);
    if (sent) return `<div class="reach-bar done"><div>${I("check")} <b>Contacted</b> · ${[sent.email && `${sent.email} email${sent.email === 1 ? "" : "s"}`, sent.whatsapp && `${sent.whatsapp} WhatsApp`].filter(Boolean).join(" + ")} sent</div><button class="btn sm" data-outreach="${uid}">Send more…</button></div>`;
    if (!e || e.loading) return "";
    const est = estimate(job); if (!est || (!est.emails && !est.phones)) return est?.guessed ? `<div class="reach-bar"><div>No public email found. ${est.guessed} likely inboxes (careers@, hr@…) can be tried.</div><button class="btn sm" data-outreach="${uid}">Choose &amp; send…</button></div>` : "";
    const what = [est.emails && `${est.emails} email${est.emails === 1 ? "" : "s"}`, est.phones && `${est.phones} WhatsApp`].filter(Boolean).join(" + ");
    return `<div class="reach-bar"><div>${I("sparkle")} <b>Reach out:</b> ${what} found for this job</div><button class="btn primary sm" data-outreach="${uid}">Send to all</button></div>`;
  };
  const draftHtml = (job) => {
    const p = preview(job.uid); if (!p) return O.previews[job.uid]?.loading ? `<div class="sk line" style="width:50%"></div>` : "";
    const subj = fill(p.settings.email_subject, p.values), body = fill(p.settings.email_body, p.values), wa = fill(p.settings.whatsapp_body, p.values);
    return `<details class="kit-item" open><summary>Ready-to-send draft <span class="faint xs">use “Gmail” next to an address</span></summary><div style="padding:0 14px 14px">
      <div class="draft-field"><span class="up">Subject</span><div class="t">${esc(subj)}</div>${copyBtn(subj)}</div><div class="draft-field"><span class="up">Body</span><div class="t">${esc(body)}</div>${copyBtn(body)}</div>
      ${p.recipients.phones.length ? `<div class="draft-field"><span class="up">WhatsApp</span><div class="t">${esc(wa)}</div>${copyBtn(wa)}</div>` : ""}
      <p class="faint xs">Gmail opens as <b>${esc(p.sender)}</b>. Gmail links can't attach files: <a href="/api/resume" download>download your resume PDF</a>.</p></div></details>`;
  };
  O.html = (job) => {
    if (job.status === "reject") return `<div class="empty" style="padding:30px"><p>This job was filtered out, so no contacts are searched.</p></div>`;
    const e = O.contacts[job.uid]; const head = `<div class="card-head"><h3>People &amp; contacts at ${esc(job.employer || "the company")}</h3><button class="btn sm" data-refresh="${esc(job.uid)}" ${e?.loading ? "disabled" : ""}>${I("refresh", "sm")} Search again</button></div>`;
    if (!e) return `<div class="card">${head}<div class="empty" style="padding:28px"><div class="art">${I("search")}</div><h3>Find who to message</h3><p>Looks through the job post and public web results for recruiters, hiring managers and email addresses.</p><button class="btn primary" data-refresh="${esc(job.uid)}">Find contacts</button></div></div>`;
    if (e.loading) return `<div class="card">${head}<div class="col"><div class="row"><span class="spinner"></span><span class="muted">Searching for recruiters and contacts at ${esc(job.employer || "this company")}… (about 20 seconds)</span></div><div class="sk block"></div><div class="sk block" style="height:60px"></div></div></div>`;
    const d = e.data || {}, jd = d.from_description || { emails: [], phones: [], linkedin: [] }, c = d.company || {}, g = d.guessed || {}, blocks = [];
    const jdItems = [...jd.emails.map((x) => emailRow(job, x, "listed")), ...jd.phones.map((x) => phoneRow(job, x, "listed")), ...jd.linkedin.map((u) => `<li>${I("user")}<a class="v grow" href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\/(www\.)?/, ""))}</a></li>`)];
    if (jdItems.length) blocks.push(`<div class="group-h">Listed in the job post</div><ul class="contact-list">${jdItems.join("")}</ul>`);
    if ((c.people || []).length) blocks.push(`<div class="group-h">People</div><div class="col" style="gap:8px">${c.people.map((p) => `<div class="person">${avatar(p.name, "sm")}<div class="grow" style="min-width:0"><div class="nm">${esc(p.name)} <span class="chip ${p.role === "recruiter" ? "good" : p.role === "leader" ? "accent" : ""}">${esc(ROLE[p.role] || p.role)}</span></div><div class="faint small ellipsis">${esc(p.headline)}</div></div><a class="btn sm" href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener">LinkedIn ${I("external", "sm")}</a></div>`).join("")}</div>`);
    const reach = [...(c.emails || []).map((x) => emailRow(job, x.value, "public", x.source)), ...(c.phones || []).map((x) => phoneRow(job, x.value, "public", x.source))];
    const site = c.website || (g.domain ? `https://${g.domain}` : ""); if (site) reach.unshift(`<li>${I("globe")}<a class="v grow" href="${esc(safeUrl(site))}" target="_blank" rel="noopener">${esc(site.replace(/^https?:\/\//, ""))}</a></li>`);
    if (reach.length) blocks.push(`<div class="group-h">Company contacts</div><ul class="contact-list">${reach.join("")}</ul>`);
    if (g.domain && g.mx && ((g.emails || []).length || (g.people || []).length)) blocks.push(`<div class="group-h">Likely addresses <span class="chip warn">guessed · may bounce</span></div><ul class="contact-list">${(g.emails || []).map((x) => emailRow(job, x, "guessed")).join("")}${(g.people || []).map((p) => `<li>${I("user")}<b>${esc(p.name)}</b>${p.emails.map((x) => `<span class="muted">${esc(x)}</span>${copyBtn(x)}${gmailBtn(job, x, p.name)}`).join(" ")}</li>`).join("")}</ul><p class="faint xs" style="margin-top:6px">${esc(g.domain)} accepts email but these inboxes aren't verified. careers@ and hr@ are most common.</p>`);
    let msg = ""; if (d.status === "no_company") msg = `<div class="notice">${I("info")}<div>${esc(job.source)} hides the employer and a web search didn't reveal it. Contacts written in the job post are shown below.</div></div>`; else if (d.error) msg = `<div class="notice warn">${I("alert")}<div>${esc(d.error)}</div></div>`; else if (!blocks.length) msg = `<div class="notice">${I("info")}<div>No contacts found for ${esc(job.employer || "this company")}.</div></div>`;
    if (d.employer_evidence && d.employer) msg = `<div class="notice">${I("info")}<div>${esc(job.source)} hid the employer. Identified as <b>${esc(d.employer)}</b> from <a href="${esc(safeUrl(d.employer_evidence))}" target="_blank" rel="noopener">this listing</a>.</div></div>` + msg;
    const manual = (c.searches || []).length ? `<p class="faint small" style="margin-top:12px">Search yourself: ${c.searches.map((u, i) => `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener">${i ? "leaders" : "recruiters"}</a>`).join(" · ")}</p>` : "";
    return `<div class="card">${head}<div class="col" style="gap:12px">${msg}${O.bar(job)}${draftHtml(job)}</div>${blocks.join("")}${manual}</div>`;
  };

  /* ---- send dialog */
  function dlg() { let d = document.getElementById("orDialog"); if (!d) { d = document.createElement("dialog"); d.className = "modal"; d.id = "orDialog"; d.innerHTML = '<form id="orForm" class="modal-body"></form>'; document.body.appendChild(d); wire(d); } return d; }
  const sel = (kind) => [...document.querySelectorAll(`#orForm input[data-r="${kind}"]:checked`)].map((i) => ({ to: i.value, name: i.dataset.name || "" }));
  function recip(r, kind) {
    const p = O.st.p, label = kind === "email" ? r.to : `+${r.to.slice(0, r.to.length - 10)} ${r.to.slice(-10)}`, v = personVals(p, r.name);
    const link = kind === "email" ? gmailUrl(p.sender, r.to, fill(p.settings.email_subject, v), fill(p.settings.email_body, v)) : `https://wa.me/${r.to}?text=${enc(fill(p.settings.whatsapp_body, v))}`;
    return `<li><label class="check grow"><input type="checkbox" data-r="${kind}" value="${esc(r.to)}" data-name="${esc(r.name || "")}" ${r.selected ? "checked" : ""}><span style="color:var(--text)">${esc(label)}</span></label>${badge(r.origin)}${r.sent_at ? `<span class="chip">sent ${esc(when(r.sent_at))}</span>` : ""}<a class="small" href="${esc(link)}" target="_blank" rel="noopener">${kind === "email" ? "open in Gmail" : "open chat"} ↗</a></li>`;
  }
  function renderDialog() {
    const p = O.st.p, job = FP.job(O.st.uid) || {}, s = p.settings, { emails, phones } = p.recipients, v = p.values;
    const ph = Object.entries(p.placeholders).map(([k, x]) => `<button type="button" class="chip" data-ph="{${k}}" title="${esc(x)}">{${k}}</button>`).join("");
    const left = { email: p.caps.email - p.sent_today.email, whatsapp: p.caps.whatsapp - p.sent_today.whatsapp };
    document.getElementById("orForm").innerHTML = `
      <div><h2>Reach out about ${esc(v.role)} at ${esc(v.company)}</h2><p class="muted small" style="margin-top:4px">One message per person · sent from ${esc(p.sender || "your Gmail")} and your WhatsApp · today ${p.sent_today.email}/${p.caps.email} emails, ${p.sent_today.whatsapp}/${p.caps.whatsapp} WhatsApp</p></div>
      ${p.email_ready ? "" : `<div class="notice warn">${I("alert")}<div><b>Gmail isn't connected</b>, so emails can't be sent from here. Add your Gmail address and an app password in <a href="#/settings" onclick="document.getElementById('orDialog').close()">Settings → API keys</a> (one-time, 2 minutes).</div></div>`}
      <div class="grid-2"><div><div class="up">Email · ${emails.length}</div>${emails.length ? `<ul class="recips">${emails.map((r) => recip(r, "email")).join("")}</ul>` : '<p class="faint small" style="margin-top:8px">No email addresses found.</p>'}${emails.some((r) => r.origin === "guessed") ? '<p class="faint xs" style="margin-top:6px">Guessed inboxes may bounce and hurt your Gmail reputation. Untick them unless nothing else is available.</p>' : ""}</div>
      <div><div class="up">WhatsApp · ${phones.length}</div>${phones.length ? `<ul class="recips">${phones.map((r) => recip(r, "phone")).join("")}</ul><p class="faint xs" style="margin-top:6px">Sent through WhatsApp Web in this browser (keep it logged in), about 30 s apart.</p>` : '<p class="faint small" style="margin-top:8px">No mobile numbers found.</p>'}</div></div>
      <div><div class="up" style="margin-bottom:8px">Preview</div><div class="preview" id="pv0"></div>${phones.length ? '<div class="preview" id="pv1" style="margin-top:8px"></div>' : ""}</div>
      <details><summary class="link">Edit the template (used for every job)</summary><div class="col" style="margin-top:12px"><div class="row" style="gap:6px">${ph}</div>
        <label class="field"><span>Email subject</span><input class="input" type="text" name="email_subject" value="${esc(s.email_subject)}"></label><label class="field"><span>Email message</span><textarea class="textarea" name="email_body" rows="9">${esc(s.email_body)}</textarea></label><label class="field"><span>WhatsApp message</span><textarea class="textarea" name="whatsapp_body" rows="4">${esc(s.whatsapp_body)}</textarea></label></div></details>
      <div class="modal-foot"><label class="check grow"><input type="checkbox" name="hide_draft" ${s.show_draft ? "" : "checked"}><span>Don't show this again: send right away next time</span></label><button type="button" class="btn" id="orCancel">Cancel</button><button type="submit" class="btn primary" id="orSend"></button></div>`;
    live(); label(left);
  }
  function live() { const f = document.getElementById("orForm"), p = O.st.p, s = p.settings, v = p.values; for (const k of ["email_subject", "email_body", "whatsapp_body"]) if (f.elements[k]) s[k] = f.elements[k].value;
    const a = document.getElementById("pv0"), b = document.getElementById("pv1"); if (a) a.innerHTML = `<span class="subj">${esc(fill(s.email_subject, v))}</span>${esc(fill(s.email_body, v))}${s.attach_resume ? "\n\n📎 resume.pdf attached" : ""}`; if (b) b.textContent = fill(s.whatsapp_body, v); }
  function label(left) { const p = O.st.p; left = left || { email: p.caps.email - p.sent_today.email }; const e = p.email_ready ? sel("email").length : 0, w = sel("phone").length, btn = document.getElementById("orSend"), parts = [e && `${e} email${e === 1 ? "" : "s"}`, w && `${w} WhatsApp`].filter(Boolean);
    btn.textContent = O.st.sending ? "Sending…" : parts.length ? `Send ${parts.join(" + ")}` : !p.email_ready && sel("email").length && !w ? "Connect Gmail to send" : "Nothing selected"; btn.disabled = O.st.sending || !parts.length || (e && left.email <= 0 && !w); }
  function wire(d) {
    const f = d.querySelector("form");
    f.addEventListener("input", (e) => e.target.matches("textarea, input[type=text]") && live());
    f.addEventListener("change", (e) => e.target.matches("[data-r]") && label());
    f.addEventListener("focusin", (e) => e.target.matches("textarea, input[type=text]") && (O.st.focus = e.target));
    f.addEventListener("click", (e) => { const ph = e.target.closest("[data-ph]"); if (ph && O.st.focus) { const el = O.st.focus, at = el.selectionStart ?? el.value.length; el.value = el.value.slice(0, at) + ph.dataset.ph + el.value.slice(el.selectionEnd ?? at); el.focus(); el.selectionStart = el.selectionEnd = at + ph.dataset.ph.length; live(); } if (e.target.closest("#orCancel")) d.close(); });
    f.addEventListener("submit", (e) => { e.preventDefault(); const emails = O.st.p.email_ready ? sel("email") : []; send(O.st.uid, { emails, phones: sel("phone"), email_subject: f.elements.email_subject.value, email_body: f.elements.email_body.value, whatsapp_body: f.elements.whatsapp_body.value, show_draft: !f.elements.hide_draft.checked }); });
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  }
  O.open = async (uid, force = false) => {
    const job = FP.job(uid); if (!job) return; toast("Preparing messages…", { ms: 1800 });
    let p; try { p = await api(`/api/outreach?uid=${enc(uid)}`); } catch (e) { return toast(e.message, { kind: "bad" }); }
    O.st.uid = uid; O.st.p = p; const em = p.recipients.emails.filter((r) => r.selected), ph = p.recipients.phones.filter((r) => r.selected);
    if (!force && !p.settings.show_draft && (em.length || ph.length) && (p.email_ready || !em.length)) return send(uid, { emails: em.map((r) => ({ to: r.to, name: r.name })), phones: ph.map((r) => ({ to: r.to, name: r.name })) });
    const d = dlg(); renderDialog(); d.showModal();
  };
  async function send(uid, body) {
    const d = dlg(); O.st.sending = true; if (d.open) label(); const k = body.emails.length;
    const kill = toast(k ? `Sending ${k} email${k === 1 ? "" : "s"}… (a few seconds apart)` : "Starting WhatsApp…", { ms: 0 });
    try {
      const r = await api("/api/outreach/send", { json: { uid, ...body } }); O.previews = {};
      const ok = r.emails.filter((x) => x.ok).length, failed = r.emails.filter((x) => !x.ok); let wa = "";
      if (r.whatsapp.length) {
        if (!FP.hasExtension()) wa = " WhatsApp needs the FresherPilot extension (reload it, then refresh).";
        else { const s = await FP.toExtension({ type: "jf-whatsapp-send", items: r.whatsapp, gap: r.whatsapp_gap }).catch((e) => ({ ok: false, error: e.message })); wa = s?.ok === false ? ` WhatsApp: ${s.error}` : ` Sending ${r.whatsapp.length} WhatsApp in the background.`; if (s?.ok !== false) follow(uid, r.whatsapp.length); }
      }
      const errs = [...r.errors, ...failed.map((x) => `${x.to}: ${x.error}`)], job = FP.job(uid);
      if (job && ok) job.outreach = { email: (job.outreach?.email || 0) + ok, whatsapp: job.outreach?.whatsapp || 0 };
      if (job && (ok || r.whatsapp.length)) job.visited_at = job.visited_at || new Date().toISOString();
      if (d.open && (ok || r.whatsapp.length)) d.close(); kill();
      toast(`${ok ? `${ok} email${ok === 1 ? "" : "s"} sent.` : ""}${wa}${errs.length ? ` Problems: ${errs.join("; ")}` : ""}`.trim() || "Nothing was sent.", { kind: errs.length ? "warn" : "good", ms: errs.length ? 12000 : 6000 });
      if (ok) FP.feedAdd("good", "mail", `Emailed ${ok} contact${ok === 1 ? "" : "s"}`, job?.title || ""); bus.emit("jobs", { reason: "outreach" }); bus.emit("dash-stale"); refresh(uid);
    } catch (e) { kill(); toast(e.message, { kind: "bad", ms: 8000 }); } finally { O.st.sending = false; if (d.open) label(); }
  }
  async function follow(uid, expected) {
    const ev = async () => { const r = await api(`/api/outreach/job?uid=${enc(uid)}`, { quiet: true }); return { r, wa: r.sent.filter((e) => e.channel === "whatsapp") }; };
    let start; try { start = (await ev()).wa.length; } catch { return; } const end = Date.now() + expected * 120000 + 60000; let seen = start;
    while (Date.now() < end && seen < start + expected) { await sleep(8000); try { const { r, wa } = await ev(); for (const e of wa.slice(seen)) toast(e.ok ? `WhatsApp sent to +${e.to}` : `WhatsApp to +${e.to} failed: ${e.error}`, { kind: e.ok ? "good" : "bad" }); seen = wa.length; const j = FP.job(uid); if (j) j.outreach = r.counts.email || r.counts.whatsapp ? { ...r.counts } : null; bus.emit("jobs", { reason: "outreach" }); refresh(uid); } catch {} }
    bus.emit("dash-stale");
  }
  document.addEventListener("click", (e) => { const b = e.target.closest("[data-outreach]"); if (b) O.open(b.dataset.outreach, !!FP.job(b.dataset.outreach)?.outreach); });
})();
