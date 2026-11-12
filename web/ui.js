/* FresherPilot shared UI behaviour (loaded on every page, before the page's own script):
   1. a thin progress bar while any request is in flight (so nothing ever looks frozen)
   2. an "app not reachable" banner + a connection dot in the nav
   3. one shared top navigation for the secondary pages (<div id="appnav" data-active="...">)
   4. uiToast(message, kind) */
(function () {
  "use strict";

  // ---- progress bar + offline detection: wrap fetch --------------------------------------------------------
  const bar = document.createElement("div");
  bar.id = "uiLoadBar";
  bar.setAttribute("aria-hidden", "true");
  let inflight = 0, offline = false, hideTimer = 0;

  function setOffline(off) {
    if (off === offline) return;
    offline = off;
    let b = document.getElementById("uiOffline");
    if (off && !b) {
      b = document.createElement("div");
      b.id = "uiOffline";
      b.setAttribute("role", "alert");
      b.textContent = "Can't reach the FresherPilot app. Is it running (python main.py)? Retrying…";
      document.body.prepend(b);
    } else if (!off && b) b.remove();
    const dot = document.getElementById("uiConn");
    if (dot) { dot.dataset.state = off ? "off" : "on"; dot.textContent = off ? "App offline" : "Connected"; }
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const own = url.startsWith("/") || url.startsWith(location.origin);
    if (own) { inflight++; clearTimeout(hideTimer); bar.classList.add("on"); }
    return realFetch(input, init).then(
      (res) => { if (own) { setOffline(false); done(); } return res; },
      (err) => { if (own) { setOffline(true); done(); } throw err; }
    );
  };
  function done() {
    inflight = Math.max(0, inflight - 1);
    if (!inflight) hideTimer = setTimeout(() => bar.classList.remove("on"), 250);
  }

  // ---- toast ------------------------------------------------------------------------------------------------
  let toastEl, toastTimer = 0;
  window.uiToast = function (message, kind) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.id = "uiToast";
      toastEl.setAttribute("role", "status");
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.dataset.kind = kind || "";
    toastEl.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("on"), 3200);
  };

  // ---- shared navigation ------------------------------------------------------------------------------------
  const LINKS = [
    ["dashboard", "/#dashboard", "Dashboard"],
    ["jobs", "/#jobs", "Jobs"],
    ["autoapply", "/autoapply", "Auto-apply"],
    ["profile", "/static/profile.html", "Profile"],
    ["settings", "/account", "Settings"],
  ];
  function buildNav() {
    const host = document.getElementById("appnav");
    if (!host) return;
    const active = host.dataset.active || "";
    host.className = "topbar ui-nav";
    host.innerHTML =
      `<a class="brand" href="/"><span class="logo" aria-hidden="true">JF</span><span class="brand-name">FresherPilot</span></a>` +
      `<nav class="ui-links" aria-label="Main">` +
      LINKS.map(([id, href, label]) => `<a href="${href}"${id === active ? ' aria-current="page"' : ""}>${label}</a>`).join("") +
      `</nav><span class="ui-conn" id="uiConn" data-state="on">Connected</span>`;
  }

  function ready() {
    document.body.prepend(bar);
    buildNav();
    // a quiet heartbeat so the "offline" banner appears even when the page is idle
    setInterval(() => { if (!document.hidden) realFetch("/api/health").then(() => setOffline(false), () => setOffline(true)); }, 10000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready); else ready();
})();
