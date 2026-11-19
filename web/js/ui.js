/* Small shared UI: confirm dialog + copy buttons. */
(() => {
  const { esc, toast } = FP;
  FP.confirm = ({ title, text = "", ok = "OK", cancel = "Cancel", danger = false }) => new Promise((resolve) => {
    const d = document.createElement("dialog"); d.className = "modal confirm";
    d.innerHTML = `<form method="dialog" class="modal-body"><h2>${esc(title)}</h2><p class="muted">${esc(text)}</p><div class="row"><button class="btn" value="no">${esc(cancel)}</button><button class="btn ${danger ? "danger" : "primary"}" value="yes" autofocus>${esc(ok)}</button></div></form>`;
    document.body.appendChild(d); d.addEventListener("close", () => { resolve(d.returnValue === "yes"); d.remove(); });
    d.addEventListener("click", (e) => { if (e.target === d) d.close("no"); }); d.showModal();
  });
  document.addEventListener("click", async (e) => {
    const c = e.target.closest("[data-copy]"); if (!c) return;
    try { await navigator.clipboard.writeText(c.dataset.copy); toast("Copied", { kind: "good", ms: 1400 }); } catch { toast("Couldn't copy", { kind: "bad" }); }
  });
})();
