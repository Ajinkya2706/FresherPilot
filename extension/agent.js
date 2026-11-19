// Auto-apply helpers injected into the job tab: readiness detection, challenge detection,
// Vimium-style hints, clicking, and a small status panel with Continue / Skip / Stop.
(() => {
  if (window.__jfAgent) return;

  const visible = (e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0" && r.bottom > 0 && r.top < innerHeight * 1.6 && !e.disabled;
  };
  // Rendered and usable anywhere on the page (not just on screen), so a Submit far below is still found.
  const rendered = (e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0" && !e.disabled;
  };
  const clean = (t) => String(t || "").replace(/\s+/g, " ").trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---------------------------------------------------------------- readiness

  // Page changes and network activity, recorded continuously.
  let lastMutation = performance.now();
  new MutationObserver((records) => {
    // Ignore our own hint badges / status panel.
    if (records.every((r) => [...r.addedNodes, ...r.removedNodes].every((n) => n.classList?.contains("__jfhint") || n.id === "__jf_status"))) return;
    lastMutation = performance.now();
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  let lastRequest = performance.now();
  try {
    new PerformanceObserver(() => (lastRequest = performance.now())).observe({ type: "resource", buffered: false });
  } catch {}

  const BUSY_TEXT = /^(loading|please wait|just a moment|submitting|processing|uploading)\b|checking your browser|loading\.\.\.|loading…|preparing (your |the )?review|preparing your application/i;

  // Why the page is still busy, or "" when it looks ready.
  function busyReason() {
    if (document.readyState !== "complete") return "page loading";
    if (blockedState() === "challenge-loading") return "security check running";
    if ([...document.querySelectorAll('[aria-busy="true"]')].some(visible)) return "page says it is busy";
    // Step indicators ("step 4 of 4", 100%) are determinate and static: not loading. Only an
    // indeterminate bar (no value) means "wait"; a moving bar also keeps the DOM changing.
    const indeterminate = [...document.querySelectorAll("[role=progressbar], progress")].find(
      (e) => visible(e) && (e.tagName === "PROGRESS" ? !e.hasAttribute("value") : !e.hasAttribute("aria-valuenow"))
    );
    if (indeterminate) return "loading bar";
    // A spinner/skeleton only counts while it is actually animating.
    const animating = (e) => {
      try {
        return e.getAnimations({ subtree: true }).some((a) => a.playState === "running");
      } catch {
        return getComputedStyle(e).animationName !== "none";
      }
    };
    const spinner = [...document.querySelectorAll('[class*="spinner" i], [class*="loader" i], [class*="loading" i], [class*="skeleton" i], [class*="shimmer" i]')]
      .find((e) => visible(e) && e.getBoundingClientRect().width < innerWidth * 0.9 && animating(e));
    if (spinner) return "spinner";
    const dialog = currentDialog();
    const text = clean((dialog || document.body).innerText).slice(0, 400);
    if (BUSY_TEXT.test(text)) return "loading text";
    return "";
  }

  // Wait until the page is loaded, nothing is spinning, and the DOM + network have been quiet a moment.
  async function waitReady(timeout = 30000, quietMs = 800) {
    const start = performance.now();
    let reason = "";
    while (performance.now() - start < timeout) {
      reason = busyReason();
      const now = performance.now();
      if (!reason && now - lastMutation > quietMs && now - lastRequest > 500) return { ready: true, waited: Math.round(now - start) };
      await sleep(200);
    }
    return { ready: false, waited: Math.round(performance.now() - start), reason: reason || "page kept changing" };
  }

  // ---------------------------------------------------------------- security checks / login

  // "challenge" = a human must act, "challenge-loading" = an automatic check still running, "login", or "".
  function blockedState() {
    const frames = [...document.querySelectorAll("iframe")].filter(visible);
    const challengeFrame = frames.find((f) => /challenges\.cloudflare\.com|hcaptcha\.com|recaptcha\/api2\/(bframe|anchor)|arkoselabs|funcaptcha/i.test(f.src || "") && f.getBoundingClientRect().width > 60);
    const text = clean(document.body ? document.body.innerText : "").slice(0, 2000);
    if (/just a moment|checking your browser|checking if the site connection is secure/i.test(document.title + " " + text) && !challengeFrame) return "challenge-loading";
    if (challengeFrame || /verify you are (a )?human|are you a robot|press (&|and) hold|complete the security check/i.test(text)) return "challenge";
    if (/\/(login|signin|sign-in|authwall)\b|nlogin|secure\.indeed\.com\/auth|accounts\.google/i.test(location.href)) return "login";
    return "";
  }

  // ---------------------------------------------------------------- hints

  function currentDialog() {
    // A real dialog element first (LinkedIn's Easy Apply is a <dialog>): a looser "modal"-named element inside it
    // must not be taken for the dialog, or the footer's Next / Submit buttons count as outside it.
    // (an empty wrapper, e.g. Wellfound's, is skipped: the form lives in a sibling modal found below)
    // (opacity is ignored: in a background tab the fade-in never finishes and LinkedIn's dialog stays at opacity 0)
    const boxed = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && r.bottom > 0 && r.top < innerHeight * 1.6; };
    const real = [...document.querySelectorAll("dialog[open],[role=dialog],[aria-modal=true],[data-testid=dialog]")].filter((e) => boxed(e) && clean(e.innerText).length > 0);
    if (real.length) return real[real.length - 1];
    const dialogs = [...document.querySelectorAll(".artdeco-modal,[class*=modal],[class*=Drawer]")].filter(visible);
    return dialogs[dialogs.length - 1] || null;
  }

  function snapshot() {
    document.querySelectorAll(".__jfhint").forEach((n) => n.remove());
    document.querySelectorAll("[data-jf-hint]").forEach((n) => n.removeAttribute("data-jf-hint"));
    const sel = "a[href],button,[role=button],[role=link],input[type=submit],input[type=button],[role=menuitem],[role=tab],[role=radio],[role=option],summary,label.ssrc__label,div.sendMsg";
    // buttons built from div/span (Indeed's review page, many ATS): include them when their own text is a Submit/Next-style word
    const STEP_WORD = /^(submit( application)?|review( your application)?|next|continue|apply( now)?|send( application)?|done|finish|save and continue|continue to next step)$/i;
    const extra = [...document.querySelectorAll("div[class*=btn i],span[class*=btn i],div[class*=button i],span[class*=button i],div[tabindex='0'],span[tabindex='0'],[onclick]")]
      .filter((e) => !e.matches(sel) && STEP_WORD.test(clean(e.innerText)) && !e.querySelector("button,a[href]"));
    const all = [...document.querySelectorAll(sel), ...extra].filter((e) => rendered(e) && !e.closest("#__jf_status"));
    const dialog = currentDialog();
    // Real buttons (Next / Submit...) first, then links; dialog contents before the rest of the page.
    const isButton = (e) => e.tagName !== "A";
    const order = (list) => list.filter(isButton).concat(list.filter((e) => !isButton(e)));
    const pool = dialog ? order(all.filter((e) => dialog.contains(e))).concat(order(all.filter((e) => !dialog.contains(e))).slice(0, 90)) : order(all);
    const letters = "asdfghjklqwertyuiopzxcvbnm";
    const items = [];
    pool.slice(0, 320).forEach((e, i) => {
      const key = letters[Math.floor(i / 26) % 26] + letters[i % 26];
      e.setAttribute("data-jf-hint", key);
      const r = e.getBoundingClientRect();
      const b = document.createElement("div");
      b.className = "__jfhint";
      b.textContent = key;
      Object.assign(b.style, {
        position: "fixed", left: `${Math.max(0, r.left)}px`, top: `${Math.max(0, r.top)}px`, background: "#fde047",
        color: "#000", font: "bold 11px monospace", padding: "0 3px", zIndex: 2147483646, borderRadius: "3px", pointerEvents: "none",
      });
      document.body.appendChild(b);
      items.push({
        key, text: clean(e.innerText || e.value).slice(0, 80), label: clean(e.getAttribute("aria-label")).slice(0, 80),
        tag: e.tagName.toLowerCase(), href: (e.getAttribute("href") || "").slice(0, 100), in_dialog: !!(dialog && dialog.contains(e)),
        below: r.top > innerHeight, // further down the page (clicking scrolls to it)
      });
    });
    const root = dialog || document.body;
    const fields = [...root.querySelectorAll("input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea")].filter((f) => (rendered(f) || ((f.type === "radio" || f.type === "checkbox") && f.labels && [...f.labels].some(rendered))) && !f.closest("#__jf_status"));  // LinkedIn hides the radio input itself, only its label shows
    const empty = fields.filter((f) => (f.type === "radio" || f.type === "checkbox" ? false : !clean(f.value))).length;
    // "Applied" shown as a plain span/div (Naukri, LinkedIn "Applied 2d ago"), not a button the list above would hold.
    const already = !dialog && [...document.querySelectorAll("button,div,span,a,p")].some((e) => {
      if (e.childElementCount > 1 || e.closest("#__jf_status, nav, aside, header, footer, [role=navigation], a[href]")) return false;  // a nav link "Applied" is not this job's state
      const t = clean(e.innerText);
      return t.length > 0 && t.length < 24 && /^(?:✓\s*)?(?:already\s+)?applied(?:\s*✓)?(?:\s+\d+\s*\w+\s+ago)?$/i.test(t) && e.getBoundingClientRect().width > 2 && e.getBoundingClientRect().height > 2 && e.getBoundingClientRect().top < innerHeight * 1.2;  // a DISABLED "Applied" button counts too
    });
    return {
      already, url: location.href, title: document.title, items, dialog: !!dialog, fields: fields.length, empty_fields: empty,
      blocked: blockedState(), text: clean(root.innerText).slice(0, 2500), full_text: clean(document.body.innerText).slice(0, 8000),
    };
  }

  function click(key) {
    const el = document.querySelector(`[data-jf-hint="${key}"]`);
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    document.querySelectorAll(".__jfhint").forEach((n) => n.remove());
    if (el.tagName === "A" && el.target === "_blank") el.removeAttribute("target"); // keep the flow in this tab
    el.click();
    lastMutation = performance.now();
    return true;
  }

  function emptyRequired() {
    const root = currentDialog() || document;
    const out = [];
    const shown = (n) => n && n.getClientRects().length > 0 && getComputedStyle(n).visibility !== "hidden";
    root.querySelectorAll("input, select, textarea").forEach((el) => {
      if (el.closest("#__jf_status")) return;
      const req = el.required || el.getAttribute("aria-required") === "true";
      if (!req || el.disabled || el.type === "hidden" || el.type === "file") return;
      if (!shown(el) && !(el.labels && [...el.labels].some(shown))) return;
      if (el.type === "radio") {
        if (!root.querySelector(`input[type=radio][name="${CSS.escape(el.name)}"]:checked`)) out.push(el.name);
      } else if (el.type === "checkbox") {
        if (!el.checked) out.push((el.labels && el.labels[0] && clean(el.labels[0].innerText)) || el.name || "checkbox");
      } else if (!clean(el.value)) {
        out.push(clean((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute("aria-label") || el.name || el.id).slice(0, 60));
      }
    });
    return [...new Set(out)];
  }

  // ---------------------------------------------------------------- status panel (in the job tab)

  function showStatus(text, waiting) {
    let host = document.getElementById("__jf_status");
    if (!host) {
      host = document.createElement("div");
      host.id = "__jf_status";
      Object.assign(host.style, { position: "fixed", right: "16px", bottom: "16px", zIndex: 2147483647 });
      host.attachShadow({ mode: "open" });
      document.documentElement.appendChild(host);
    }
    const esc = (s) => String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
    const accent = waiting ? "#f59e0b" : "#34d399";
    const min = host.dataset.min === "1";
    host.shadowRoot.innerHTML = `
      <style>
        *{box-sizing:border-box}
        .box{font:13px/1.45 "Segoe UI",system-ui,sans-serif;background:#0f1720;color:#e8eef5;border:1px solid #243042;border-radius:14px;
             width:${min ? "auto" : "304px"};box-shadow:0 12px 36px rgba(0,0,0,.45);overflow:hidden}
        .hd{display:flex;align-items:center;gap:8px;padding:9px 10px 9px 12px;border-bottom:${min ? "0" : "1px solid #1c2735"}}
        .logo{width:22px;height:22px;border-radius:6px;background:#34d399;color:#052419;font:800 10px/22px "Segoe UI",sans-serif;text-align:center}
        .name{font-weight:700;letter-spacing:-.01em}
        .dot{width:8px;height:8px;border-radius:50%;background:${accent};box-shadow:0 0 0 0 ${accent};animation:p 1.6s infinite}
        @keyframes p{70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
        .sp{flex:1}
        .min{border:0;background:none;color:#93a3b6;cursor:pointer;font:700 16px/1 inherit;padding:2px 6px;border-radius:6px}
        .min:hover{background:#1c2735;color:#fff}
        .bd{padding:10px 12px 12px;display:${min ? "none" : "grid"};gap:10px}
        .msg{color:#c2ccd8;word-break:break-word}
        .row{display:flex;gap:6px;flex-wrap:wrap}
        button.a{font:inherit;font-weight:600;border:1px solid #34414f;border-radius:999px;padding:6px 14px;cursor:pointer;background:#17212d;color:#e8eef5}
        button.a:hover{border-color:#93a3b6}
        button.go{background:#34d399;border-color:#34d399;color:#052419}
        button.stop{color:#ff8a80;border-color:#5a2a2b;background:transparent}
        button:focus-visible{outline:2px solid #34d399;outline-offset:2px}
      </style>
      <div class="box" role="status" aria-live="polite">
        <div class="hd"><span class="logo">JF</span><span class="name">FresherPilot</span><span class="dot"></span><span class="sp"></span>
          <button class="min" data-a="min" aria-label="${min ? "Expand" : "Minimize"}">${min ? "+" : "-"}</button></div>
        <div class="bd"><div class="msg">${esc(text)}</div>
          <div class="row">${waiting ? '<button class="a go" data-a="continue">Continue</button><button class="a" data-a="skip">Skip job</button>' : ""}<button class="a stop" data-a="stop">Stop</button></div></div>
      </div>`;
    host.shadowRoot.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => {
        if (b.dataset.a === "min") { host.dataset.min = host.dataset.min === "1" ? "0" : "1"; showStatus(text, waiting); return; }
        chrome.runtime.sendMessage({ type: "jf-command", action: b.dataset.a });
        showStatus(b.dataset.a === "continue" ? "Continuing…" : b.dataset.a === "skip" ? "Skipping this job…" : "Stopping…", false);
      })
    );
  }

  // Scroll down the page and back so content that only appears when scrolled into view
  // (lazy-loaded Apply buttons, e.g. on Indeed) is created before the page is read.
  async function scrollThrough() {
    const scroller = currentDialog() || document.scrollingElement || document.documentElement;
    const startY = scroller.scrollTop;
    for (let i = 0; i < 12; i++) {
      const before = scroller.scrollTop;
      scroller.scrollBy({ top: Math.max(400, innerHeight * 0.8), behavior: "instant" });
      await sleep(250);
      if (scroller.scrollTop === before) break; // reached the bottom
    }
    await sleep(400);
    scroller.scrollTo({ top: startY, behavior: "instant" });
    await sleep(200);
    return true;
  }

  window.__jfAgent = { snapshot, click, emptyRequired, waitReady, blockedState, showStatus, scrollThrough };
})();
