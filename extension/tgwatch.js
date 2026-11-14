// Watches the owner's open Telegram Web tab for new posts in the private "Freshershunt Pro" channel and sends them
// to the FresherPilot app (POST /api/pro/ingest), which turns them into jobs, AI-checks them and alerts at once.
// Reads only the channel named below, only while its chat is open in the tab; nothing is sent anywhere else.
(() => {
  if (window.__jfTgWatch) return;
  window.__jfTgWatch = true;
  const CHANNEL = /freshershunt pro/i;
  const KEY = "tgpro_last_id";
  const BACKFILL = 12;  // first time: also take the last N messages (today's digests)
  let sending = false;

  const header = () => (document.querySelector(".MiddleHeader") || {}).innerText || "";
  const num = (el) => Number((el.id || "").replace("message-", "")) || 0;

  async function scan() {
    if (sending || !CHANNEL.test(header())) return;
    const els = [...document.querySelectorAll('.Message[id^="message-"]')];
    if (!els.length) return;
    let { [KEY]: last } = await chrome.storage.local.get(KEY);
    const ids = els.map(num).filter(Boolean).sort((a, b) => a - b);
    if (!last) last = ids[Math.max(0, ids.length - BACKFILL)] - 1;  // first run: backfill a few recent messages
    const fresh = els.filter((el) => num(el) > last);
    if (!fresh.length) return;
    const messages = fresh.map((el) => {
      const body = el.querySelector(".text-content") || el;
      const links = [...el.querySelectorAll("a[href]")].map((a) => a.href).filter((h) => /^https?:/.test(h));
      return { id: String(num(el)), text: (body.innerText || "").trim(), links };
    }).filter((m) => m.text);
    const top = Math.max(...fresh.map(num));
    sending = true;
    try {
      if (messages.length) {
        const res = await chrome.runtime.sendMessage({ type: "jf-tgpro", messages });
        if (!res || res.error) throw new Error((res && res.error) || "no answer");
      }
      await chrome.storage.local.set({ [KEY]: top });  // only after the app took them: a failed send is retried
    } catch (e) {
      // app not running: try again on the next scan
    } finally {
      sending = false;
    }
  }

  setInterval(scan, 1500);
  new MutationObserver(() => scan()).observe(document.body, { childList: true, subtree: true });
})();
