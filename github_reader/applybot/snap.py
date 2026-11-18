"""Page-state reader: turns what is on the screen into a compact, structured description (no AI, no screenshots).

snapshot(page) -> {
  url, host, title, headings[], text (visible text, trimmed), dialog (True when a modal holds the form),
  fields[]  : {id, frame, kind (text|textarea|select|radio|checkbox|combo|file|date|password|email|tel|number|code),
               label, required, value, invalid, error, options[], opt_ids[], placeholder, name, autocomplete, maxlength, checked}
  buttons[] : {id, frame, text, disabled, primary, link}
  errors[]  : visible error messages
}
Every interactive element is stamped data-fp="<frame>.<n>" so the engine can find it again with a plain locator.
"""
from __future__ import annotations

JS = r"""
(frameNo) => {
  // Open shadow roots are searched too (SmartRecruiters' "I'm interested" button and many career widgets live in
  // web components; Nov 18 dry run saw only the cookie buttons). Hosts are found once per snapshot.
  const hosts = []; { const seen = new Set(), todo = [document]; while (todo.length) { const n = todo.pop(); for (const e of n.querySelectorAll('*')) if (e.shadowRoot && !seen.has(e)) { seen.add(e); hosts.push(e); todo.push(e.shadowRoot); } } }
  const q = (s, r = document) => {
    const out = Array.from(r.querySelectorAll(s));
    for (const h of hosts) if (r === document || (r.contains && r.contains(h)) || (r.host && r.contains(h))) out.push(...h.shadowRoot.querySelectorAll(s));
    return out;
  };
  const vis = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return false;
    if (el.closest('[aria-hidden="true"]') && !el.closest('dialog[open],[role=dialog],[aria-modal=true]')) return false;
    return r.width > 1 && r.height > 1;
  };
  const txt = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const dlgs = q('dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]').filter(vis).filter((d) => txt(d).length > 20)
    .filter((d) => !(/cookie|privacy notice|consent preferences|your privacy choices/i.test(txt(d).slice(0, 400)) && !d.querySelector('input:not([type=hidden]):not([type=checkbox]),textarea,select')));   // a cookie banner is not the form
  const root = dlgs.length ? dlgs[dlgs.length - 1] : document;
  const inRoot = (el) => root === document || root.contains(el);
  const usedStamps = new Set();   // a cloned block ("Add another education") copies data-fp: every element must still get its OWN id
  const stamp = (el) => { let v = el.getAttribute('data-fp'); if (!v || !v.startsWith(frameNo + '.') || usedStamps.has(v)) { window.__fpn = (window.__fpn || 0) + 1; v = frameNo + '.' + window.__fpn; el.setAttribute('data-fp', v); } usedStamps.add(v); return v; };

  const own = (l) => { const c = l.cloneNode(true); c.querySelectorAll('select,option,textarea,input,button,[role=listbox],ul').forEach((x) => x.remove()); return txt(c); };
  const CTRL = 'input:not([type=hidden]),textarea,select,[role=combobox],button[aria-haspopup]';
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);   // a is before b
  const labelOf = (el) => {
    const out = [];
    const al = el.getAttribute('aria-label'); if (al && al.replace(/select one|required|\\*/ig, '').trim().length > 2) out.push(al);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((i) => { const x = document.getElementById(i); if (x) out.push(own(x)); });
    if (el.id) q('label[for="' + CSS.escape(el.id) + '"]').forEach((l) => out.push(own(l)));
    const wrap = el.closest('label'); if (wrap) out.push(own(wrap));
    if (!out.some(Boolean)) {   // a label / short text right before the control (siblings)
      let sib = el.previousElementSibling;
      for (let i = 0; i < 2 && sib && !out.some(Boolean); i++, sib = sib.previousElementSibling) {
        if (!sib.querySelector(CTRL) && own(sib) && own(sib).length < 120) out.push(own(sib));
      }
    }
    if (!out.some(Boolean)) {   // nearest group label / the closest label or text BEFORE the control
      const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg) out.push(txt(lg)); }
      let up = el.parentElement;
      for (let i = 0; i < 4 && up && !out.some(Boolean); i++, up = up.parentElement) {
        if (q(CTRL, up).filter((c) => c !== el && !el.contains(c) && !c.contains(el)).length > 2) break;   // a container of many fields: labels in it are not ours
        const ls = q('label,legend,[class*=label i],[data-automation-id*=label i]', up).filter((l) => !l.contains(el) && !l.querySelector(CTRL) && before(l, el) && own(l) && own(l).length < 200);
        if (ls.length) out.push(own(ls[ls.length - 1]));
      }
    }
    if (!out.some(Boolean) && el.placeholder) out.push(el.placeholder);
    return out.filter(Boolean)[0] || '';
  };
  const groupLabel = (el) => {
    const g = el.closest('fieldset,[role=radiogroup],[role=group]');
    if (g) { const lg = g.querySelector('legend') || (g.getAttribute('aria-labelledby') && document.getElementById(g.getAttribute('aria-labelledby').split(' ')[0])); if (lg && txt(lg)) return txt(lg); const al = g.getAttribute('aria-label'); if (al) return al; }
    let up = el.parentElement;
    for (let i = 0; i < 5 && up; i++, up = up.parentElement) {
      const l = up.querySelector(':scope > label, :scope > legend, :scope > [class*=label i], :scope > span, :scope > p, :scope > div > label');
      if (l && !l.contains(el) && txt(l).length > 3 && txt(l).length < 250) return txt(l);
    }
    return '';
  };
  const ERRSEL = '[role=alert],[class*=error i],[id*=error i],[data-automation-id*=error i],[class*=invalid i],[class*=feedback i],[class*=danger i]';
  const PLACEHOLDERISH = /^(select|choose|please select|search)[\s.…]*(an? option|one)?[\s.…]*$/i;
  const errOf0 = (el) => {
    const d = el.getAttribute('aria-describedby');
    if (d && el.getAttribute('aria-invalid') === 'true') { const x = document.getElementById(d.split(' ')[0]); if (x && txt(x)) return txt(x).slice(0, 200); }
    // an error message belongs to a control when it sits right after it (siblings of the control or of its wrapper), never "the first error in the form"
    let node = el;
    for (let lvl = 0; lvl < 3 && node && node.parentElement; lvl++, node = node.parentElement) {
      let sib = node.nextElementSibling;
      for (let i = 0; i < 3 && sib; i++, sib = sib.nextElementSibling) {
        if (sib.matches('label,button,input,select,textarea') || sib.querySelector(CTRL)) break;
        const e = sib.matches(ERRSEL) ? sib : sib.querySelector(ERRSEL);
        if (e && vis(e) && txt(e) && txt(e).length < 200) return txt(e);
      }
    }
    let up = el.parentElement;
    for (let i = 0; i < 3 && up; i++, up = up.parentElement) {
      if (q(CTRL, up).filter((c) => c !== el && !el.contains(c) && !c.contains(el)).length > 1) break;
      const e = q(ERRSEL, up).find((x) => vis(x) && txt(x) && txt(x).length < 200 && !x.contains(el));
      if (e) return txt(e);
    }
    return '';
  };
  const errOf = (el) => { const e = errOf0(el); return PLACEHOLDERISH.test(e) ? '' : e; };
  // help text that tells what the field expects: aria-describedby, text right after the control, "Format: DD/MM/YYYY", "Max 500 characters"
  const hintOf = (el) => {
    const out = [];
    const d = el.getAttribute('aria-describedby');
    if (d) d.split(/\s+/).forEach((i) => { const x = document.getElementById(i); if (x) out.push(txt(x)); });
    // text right after the control (siblings, or after its wrapper): short, no control inside, not a label
    let node = el;
    for (let lvl = 0; lvl < 3 && node && node.parentElement; lvl++, node = node.parentElement) {
      let sib = node.nextElementSibling;
      for (let i = 0; i < 2 && sib; i++, sib = sib.nextElementSibling) {
        if (sib.matches('label,button,input,select,textarea,h1,h2,h3,fieldset') || sib.querySelector(CTRL)) break;
        const t = txt(sib); if (t && t.length < 200 && vis(sib)) out.push(t);
      }
      if (out.length) break;
    }
    let up = el.parentElement;
    for (let i = 0; i < 3 && up; i++, up = up.parentElement) {
      if (q(CTRL, up).filter((c) => c !== el && !el.contains(c) && !c.contains(el)).length > 1) break;
      q('small,[class*=hint i],[class*=help i],[class*=helper i],[class*=description i],[class*=instruction i],[class*=format i],[class*=caption i],[class*=sub-label i],[class*=sublabel i],[class*=form-text i],[class*=counter i],[class*=char i]', up)
        .filter((h) => !h.contains(el) && !h.querySelector(CTRL) && txt(h) && txt(h).length < 220).forEach((h) => out.push(txt(h)));
    }
    return [...new Set(out)].join(' | ').slice(0, 300);
  };
  const needsStar = (s) => /\*\s*$|\(required\)|\brequired\b/i.test(s || '');

  const fields = [];
  const seenRadio = new Set();
  q('input,textarea,select,[role=combobox],[role=listbox][aria-haspopup],button[aria-haspopup=listbox],[role=radio],[role=checkbox],[contenteditable=true]').forEach((el) => {
    if (!inRoot(el)) return;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && ['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;   // (a <button type=button aria-haspopup=listbox> is a dropdown: kept)
    const isFile = type === 'file';
    const wd = el.getAttribute('data-automation-id') === 'searchBox' || /selectinput|multiselect/.test(el.getAttribute('data-uxi-widget-type') || '');
    if (!isFile && !wd && !vis(el) && !(type === 'radio' || type === 'checkbox')) return;
    if (isFile ? false : (type === 'radio' || type === 'checkbox') && !vis(el) && !(el.labels && el.labels[0] && vis(el.labels[0])) && !vis(el.parentElement)) return;
    let kind = 'text';
    if (tag === 'textarea') kind = 'textarea';
    else if (tag === 'select') kind = 'select';
    else if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('aria-autocomplete') === 'list' || el.getAttribute('role') === 'listbox') kind = 'combo';
    else if (type === 'radio' || el.getAttribute('role') === 'radio') kind = 'radio';
    else if (type === 'checkbox' || el.getAttribute('role') === 'checkbox') kind = 'checkbox';
    else if (isFile) kind = 'file';
    else if (wd || (tag === 'input' && (el.getAttribute('placeholder') || '') === 'Search' && el.getAttribute('autocomplete') === 'off' && el.getAttribute('aria-required') !== null)) kind = 'combo';   // Workday: a search box whose pop-up list holds the options
    else if (['password', 'email', 'tel', 'number', 'date'].includes(type)) kind = type;
    else if (el.getAttribute('contenteditable') === 'true') kind = 'textarea';
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    let label = kind === 'radio' ? groupLabel(el) : labelOf(el);
    if (/^(month|day|year|mm|dd|yyyy|hour|minute)$/i.test((label || '').trim())) { const g = groupLabel(el); if (g && g.toLowerCase() !== label.trim().toLowerCase()) label = g + ' ' + label.trim(); }   // Taleo: two selects named Month / Year under a legend "Start Date"
    const f = { frame: frameNo, kind, label: label.slice(0, 240), name: el.getAttribute('name') || el.id || '', placeholder: (el.getAttribute('placeholder') || '').slice(0, 80),
                autocomplete: ac, maxlength: el.maxLength > 0 ? el.maxLength : 0, required: !!(el.required || el.getAttribute('aria-required') === 'true' || needsStar(label)),
                invalid: el.getAttribute('aria-invalid') === 'true' || (el.validity && !el.validity.valid && el.value !== ''), error: errOf(el),
                htype: type, hint: hintOf(el), inputmode: (el.getAttribute('inputmode') || '').toLowerCase(), pattern: (el.getAttribute('pattern') || '').slice(0, 120),
                minlength: el.minLength > 0 ? el.minLength : 0, min: el.getAttribute('min') || '', max: el.getAttribute('max') || '', step: el.getAttribute('step') || '',
                readonly: !!el.readOnly, disabled: !!el.disabled, title: (el.getAttribute('title') || '').slice(0, 120), validation: (el.validationMessage || '').slice(0, 160) };
    if (kind === 'radio') {
      const key = (el.name || '') + '|' + (groupLabel(el) || '');
      if (el.name && seenRadio.has(key)) { const g = fields.find((x) => x._key === key); if (g) { g.options.push(labelOf(el) || txt(el.parentElement)); g.opt_ids.push(stamp(el)); if (el.checked || el.getAttribute('aria-checked') === 'true') g.value = labelOf(el) || txt(el.parentElement); } return; }
      seenRadio.add(key); f._key = key;
      f.options = [labelOf(el) || txt(el.parentElement)]; f.opt_ids = [stamp(el)];
      f.value = (el.checked || el.getAttribute('aria-checked') === 'true') ? f.options[0] : '';
      f.id = f.opt_ids[0];
    } else {
      f.id = stamp(el);
      if (kind === 'select') { f.options = Array.from(el.options).map((o) => txt(o)).filter(Boolean); f.value = el.selectedIndex > 0 || (el.options[el.selectedIndex] && el.value) ? txt(el.options[el.selectedIndex]) : ''; if (/^(select|choose|please)/i.test(f.value)) f.value = ''; }
      else if (kind === 'checkbox') { f.checked = !!el.checked || el.getAttribute('aria-checked') === 'true'; f.value = f.checked ? 'true' : '';
        const g = el.closest('fieldset,[role=group],[role=checkboxgroup]') || (el.parentElement && el.parentElement.parentElement);
        if (g) { if (!g.getAttribute('data-fpg')) { window.__fpg = (window.__fpg || 0) + 1; g.setAttribute('data-fpg', frameNo + 'g' + window.__fpg); } f.grp = g.getAttribute('data-fpg'); } }
      else if (kind === 'combo') { f.value = (el.value !== undefined && el.tagName !== 'BUTTON' ? el.value : txt(el)).trim(); if (/^(select|choose|please|search)/i.test(f.value)) f.value = ''; f.options = [];
        if (!f.value) {   // react-select & co: the chosen value is shown in a sibling element, the input itself stays empty
          let up = el.parentElement;
          for (let i = 0; i < 5 && up && !f.value; i++, up = up.parentElement) {
            const sv = up.querySelector('[class*=single-value i],[class*=singleValue i],[class*=multi-value__label i],[class*=selected-value i],[class*=SelectedValue i]');
            if (sv && txt(sv) && !/^(select|choose)/i.test(txt(sv))) f.value = txt(sv);
            if (q(CTRL, up).filter((c) => c !== el && !el.contains(c)).length > 2) break;
          }
        } }
      else if (kind === 'file') {
        f.value = (el.files && el.files.length) ? el.files[0].name : '';
        // The upload button's own label ("Attach", "Choose file") says nothing: the slot's name is the heading above it
        // ("Resume/CV", "Cover Letter"). Walk up a few levels to the nearest heading / label that is not a button word.
        let up = el.parentElement, head = '';
        for (let i = 0; i < 5 && up && !head; i++, up = up.parentElement) {
          for (const h of q('label,legend,h1,h2,h3,h4,h5,[class*=label i],[class*=title i]', up)) {
            const t = own(h) || txt(h);
            if (t && t.length < 80 && !/^(attach|choose|upload|browse|dropbox|google drive|enter manually|or|remove|select file|drag)/i.test(t)) { head = t; break; }
          }
        }
        f.heading = head;
      }
      else f.value = el.value !== undefined ? el.value : txt(el);
    }
    fields.push(f);
  });
  fields.forEach((f) => delete f._key);

  const buttons = [];
  q('button,[role=button],input[type=submit],input[type=button],a[href],a[role=button],[data-automation-id*=Button i]').forEach((el) => {
    if (!inRoot(el) || !vis(el)) return;
    if (el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('role') === 'combobox') return;
    const t = (el.getAttribute('aria-label') || txt(el) || el.value || el.title || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    if (!t) return;
    const isLink = el.tagName === 'A';
    if (isLink && !/\b(apply|add|another|interested|continue|next|submit|sign ?in|log ?in|create|register|sign ?up|start|proceed|review|manually|resume|upload|verify|finish|send|privacy|terms|statement|agreement|policy|conditions|accept)\b/i.test(t)) return;
    buttons.push({ id: stamp(el), frame: frameNo, text: t, disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'), link: isLink, href: isLink ? (el.href || '') : '',
                   primary: /primary|submit|next|continue|apply/i.test((el.className && el.className.toString()) + ' ' + (el.getAttribute('data-automation-id') || '')) });
  });
  const errors = q('[role=alert],[class*=error i],[class*=alert-danger i],[data-automation-id*=error i],[aria-live=assertive]').filter((e) => inRoot(e) && vis(e)).map(txt).filter((s) => s && s.length < 220);
  const headings = q('h1,h2,h3,[role=heading]').filter((e) => inRoot(e) && vis(e)).map(txt).filter(Boolean).slice(0, 6);
  const captcha = q('iframe[src*=recaptcha],iframe[src*=hcaptcha],iframe[src*=turnstile],iframe[src*=captcha],[class*=g-recaptcha],[class*=h-captcha],[id*=captcha i]').some(vis);
  return { frame: frameNo, url: location.href, title: document.title, headings, text: txt(root === document ? document.body : root).slice(0, 3500), dialog: dlgs.length > 0,
           fields, buttons, errors: [...new Set(errors)].slice(0, 6), captcha };
}
"""


def snapshot(page) -> dict:
    """Merge the snapshots of the page and its (visible) frames."""
    snaps = []
    for i, fr in enumerate(page.frames[:8]):
        try:
            if fr != page.main_frame:
                el = fr.frame_element()
                if not el.is_visible():
                    continue
            s = fr.evaluate(JS, i)
            if i == 0 or s["fields"] or s["buttons"]:
                snaps.append((fr, s))
        except Exception:  # noqa: BLE001 - a frame that navigated away
            continue
    main = snaps[0][1] if snaps else {"url": page.url, "title": "", "headings": [], "text": "", "fields": [], "buttons": [], "errors": [], "dialog": False, "captcha": False}
    out = dict(main)
    out["frames"] = {str(s["frame"]): fr for fr, s in snaps}
    for fr, s in snaps[1:]:
        out["fields"] = out["fields"] + s["fields"]
        out["buttons"] = out["buttons"] + s["buttons"]
        out["errors"] = out["errors"] + s["errors"]
        out["text"] = (out["text"] + " " + s["text"])[:5000]
        out["captcha"] = out["captcha"] or s["captcha"]
        out["dialog"] = out["dialog"] or s["dialog"]
    from urllib.parse import urlparse
    out["host"] = (urlparse(out["url"]).hostname or "").removeprefix("www.")
    out["fp_page"] = page
    return out


def locate(snap: dict, ident: str):
    """Playwright locator of a stamped element (ident like '0.12')."""
    frame_no = ident.split(".")[0]
    fr = snap["frames"].get(frame_no) or snap["fp_page"].main_frame
    return fr.locator(f'[data-fp="{ident}"]').first


def state_key(snap: dict) -> str:
    """Changes when anything the user would notice changes (used to detect 'no progress')."""
    f = "|".join(f"{x['id']}={x['value']}" for x in snap["fields"])
    b = "|".join(x["text"] for x in snap["buttons"])
    return f"{snap['url']}#{'/'.join(snap['headings'][:2])}#{b}#{f}#{len(snap['errors'])}"
