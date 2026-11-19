/* Motion layer: stagger on lists, count-up numbers, button ripple, scroll reveal, confetti on success. No dependencies, no data logic. */
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // 1) stagger: anything list-like that appears gets a delay by its index
  const LISTY = ".card, .q-item, .log-row, .job, .tk, .kpi, .pick-row, .src, .node, .stat, .feed .ev";
  const seen = new WeakSet();
  let queued = false;
  function sweep() {
    queued = false;
    const batch = $$(LISTY).filter((el) => !seen.has(el) && !el.closest(".palette"));
    batch.slice(0, 60).forEach((el, i) => { seen.add(el); if (reduce) return; el.style.setProperty("--i", Math.min(i, 14)); el.classList.add("fx-in"); });
    batch.slice(60).forEach((el) => seen.add(el));
    countUps();
  }
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(sweep); } }).observe(document.body, { childList: true, subtree: true });

  // 2) count-up: plain integer stats animate to their value; a changed value pops
  const last = new WeakMap();
  function countUps() {
    $$(".tk b, .stat b, .kpi .value, .hello .stats b").forEach((el) => {
      const t = el.textContent.trim(); if (!/^\d{1,6}$/.test(t)) return;
      const to = +t, from = last.get(el);
      if (from === to) return; last.set(el, to);
      if (from === undefined) { if (reduce || to === 0) return; tween(el, 0, to); }
      else { el.closest(".stat, .tk")?.classList.remove("bump"); void el.offsetWidth; el.closest(".stat, .tk")?.classList.add("bump"); }
    });
  }
  function tween(el, from, to) {
    const t0 = performance.now(), d = 650;
    const step = (now) => { const p = Math.min(1, (now - t0) / d), e = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(from + (to - from) * e); if (p < 1) requestAnimationFrame(step); else el.textContent = to; };
    requestAnimationFrame(step);
  }

  // 3) ripple on buttons
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn"); if (!b || b.disabled || reduce) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height) * 2, d = document.createElement("span");
    d.className = "fx-ripple"; d.style.cssText = `width:${s}px;height:${s}px;left:${e.clientX - r.left - s / 2}px;top:${e.clientY - r.top - s / 2}px`;
    b.appendChild(d); setTimeout(() => d.remove(), 650);
  }, { passive: true });

  // 4) page leave transition: a short fade before the router swaps the view
  window.addEventListener("hashchange", () => { const v = document.getElementById("view"); if (!v || reduce) return; v.classList.remove("leaving"); void v.offsetWidth; });

  // 5) success: confetti + check mark when an application goes through
  FP_ready(() => {
    let lastId = null;
    FP.bus.on("feed", () => {
      const e = FP.feed && FP.feed[0]; if (!e || e.id === lastId) return; lastId = e.id;
      if (e.kind === "good" && /^(Applied|Emailed)/.test(e.text) && Date.now() - Date.parse(e.at) < 4000) celebrate();
    });
  });
  function celebrate() {
    if (reduce) return;
    const box = document.createElement("div"); box.className = "fx-confetti";
    const colors = ["#7c6cff", "#35d0ff", "#3ddc97", "#ffb84d", "#ff6b7a"];
    const x0 = innerWidth - 60, y0 = innerHeight - 60;
    for (let i = 0; i < 42; i++) {
      const p = document.createElement("i"), a = Math.random() * Math.PI - Math.PI * 1.05, v = 140 + Math.random() * 260;
      p.style.cssText = `left:${x0}px;top:${y0}px;background:${colors[i % 5]};--x:${Math.cos(a) * v}px;--y:${Math.sin(a) * v + 120}px;--r:${Math.random() * 720 - 360}deg;animation-delay:${Math.random() * 120}ms`;
      box.appendChild(p);
    }
    document.body.appendChild(box);
    const ck = document.createElement("div"); ck.className = "fx-check"; ck.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    document.body.appendChild(ck);
    setTimeout(() => { box.remove(); ck.remove(); }, 2000);
  }
  function FP_ready(fn) { if (window.FP && FP.bus) fn(); else setTimeout(() => FP_ready(fn), 200); }
})();
