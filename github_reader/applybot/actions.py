"""Doing things on the page with real input (Playwright sends trusted mouse / keyboard events), with fallbacks for stubborn widgets."""
from __future__ import annotations

import re
from typing import Any

from .answerbank import alias_match
from .snap import locate

OPTION_SEL = ("[role=option], [role=listbox] li, ul[role=listbox] > *, [data-automation-id=promptOption], [data-automation-id*=menuItem i], "
              ".select2-results__option, .Select-option, [class*=option i][role], li[class*=option i], div[class*=menu] [class*=option i], mat-option, .ant-select-item-option, .dropdown-menu li")


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.%@ ]+", " ", (t or "").lower())).strip()


def _scroll(loc) -> None:
    """Bring the element to the MIDDLE of the screen: at the edge, fixed headers / footers (Workday's pageFooter) sit on top of it and swallow the click."""
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    try:
        loc.evaluate("e => e.scrollIntoView({block: 'center', inline: 'nearest'})")
    except Exception:  # noqa: BLE001
        pass


def click(page, loc) -> bool:
    """Real click; scrolls into view, waits for it to be enabled, falls back to force and then to a DOM click."""
    _scroll(loc)
    for attempt in (0, 1, 2):
        try:
            if attempt == 0:
                loc.click(timeout=4000)
            elif attempt == 1:
                loc.click(timeout=3000, force=True)
            else:
                loc.evaluate("e => e.click()")
            return True
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(200)
    return False


def _read(loc) -> str:
    try:
        return (loc.input_value(timeout=1500) or "").strip()
    except Exception:  # noqa: BLE001
        try:
            return (loc.inner_text(timeout=1500) or "").strip()
        except Exception:  # noqa: BLE001
            return ""


def set_text(page, loc, value: str) -> bool:
    """fill() first; if the page did not keep the value (masked / React inputs) retype it key by key; last resort: events through JS."""
    _scroll(loc)
    for attempt in (0, 1, 2):
        try:
            if attempt == 0:
                loc.fill(value, timeout=4000)
            elif attempt == 1:
                loc.click(timeout=3000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                loc.press_sequentially(value, delay=12, timeout=8000)
            else:
                loc.evaluate("""(e, v) => { const d = Object.getOwnPropertyDescriptor(e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value');
                    e.focus(); d.set.call(e, v); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); e.blur(); }""", value)
            got = _read(loc)
            if _norm(got) == _norm(value) or (re.sub(r"\D", "", value) and re.sub(r"\D", "", got) == re.sub(r"\D", "", value)):
                try:
                    loc.blur()
                except Exception:  # noqa: BLE001
                    pass
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def set_select(page, loc, value: str) -> bool:
    _scroll(loc)
    for kw in ({"label": value}, {"value": value}):
        try:
            loc.select_option(timeout=3000, **kw)
            return True
        except Exception:  # noqa: BLE001
            continue
    try:   # case / whitespace differences
        opts = loc.evaluate("e => Array.from(e.options).map(o => [o.value, o.textContent])")
        for v, t in opts:
            if _norm(t) == _norm(value):
                loc.select_option(value=v, timeout=3000)
                return True
    except Exception:  # noqa: BLE001
        pass
    try:   # the answer is a shorter / looser wording of ONE option ("Job Posting Site" -> "Job Posting Site (e.g., Indeed)"; Nov 18, Cisco)
        opts = loc.evaluate("e => Array.from(e.options).filter(o => o.value !== '').map(o => [o.value, o.textContent])")
        texts = [t.strip() for _, t in opts]
        pref = [t for t in texts if len(_norm(value)) >= 6 and _norm(t).startswith(_norm(value))]   # a TRUNCATED copy of one option
        pick = (pref[0] if len(set(pref)) == 1 else "") or best_option(texts, value) or alias_match(value, texts) or unique_overlap(texts, value)
        if pick:
            v = next(v for v, t in opts if t.strip() == pick)
            loc.select_option(value=v, timeout=3000)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def set_checkbox(page, loc, want: bool) -> bool:
    _scroll(loc)
    try:
        loc.set_checked(want, timeout=3000, force=True)
        return True
    except Exception:  # noqa: BLE001
        pass
    try:   # custom checkbox: click it (or its label) until the state matches
        for _ in range(2):
            now = loc.evaluate("e => e.checked === true || e.getAttribute('aria-checked') === 'true'")
            if now == want:
                return True
            click(page, loc)
            page.wait_for_timeout(150)
        return loc.evaluate("e => e.checked === true || e.getAttribute('aria-checked') === 'true'") == want
    except Exception:  # noqa: BLE001
        return False


def choose_radio(page, snap: dict, field: dict[str, Any], value: str) -> bool:
    from .answers import match_option
    opt = match_option(value, field["options"])
    if not opt:
        return False
    i = field["options"].index(opt)
    loc = locate(snap, field["opt_ids"][i])
    _scroll(loc)
    try:
        loc.check(timeout=3000, force=True)
        return True
    except Exception:  # noqa: BLE001
        pass
    try:   # the visible thing is often the label / a styled span
        loc.evaluate("e => (e.labels && e.labels[0] ? e.labels[0] : e.parentElement).click()")
        return True
    except Exception:  # noqa: BLE001
        return click(page, loc)


def visible_options(page, near=None) -> list[tuple[Any, str]]:
    """(locator, text) of the options of the dropdown that is open now: ONE page call reads every candidate (a per-element loop took minutes on Workday).
    Pages like Workday keep OLD lists in the DOM (off screen): with near=<the control> only options on the screen and beside that control count."""
    try:
        box = None
        if near is not None:
            try:
                box = near.bounding_box(timeout=1500)
            except Exception:  # noqa: BLE001
                box = None
            if not box:
                return []
        rows = page.evaluate("""([sel, b]) => { const out = []; const els = Array.from(document.querySelectorAll(sel));
            for (let i = 0; i < els.length && out.length < 150; i++) {
                const e = els[i], q = e.getBoundingClientRect();
                if (q.width < 2 || q.height < 2) continue;
                const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
                if (b) {
                    if (q.bottom < 0 || q.top > innerHeight) continue;
                    if (q.top < b.y - 480 || q.top > b.y + b.height + 480) continue;
                    if (q.right < b.x - 40 || q.left > b.x + b.width + 260) continue;
                }
                const t = (e.innerText || '').trim(); if (t) out.push([i, t]);
            } return out; }""", [OPTION_SEL, box])
        loc = page.locator(OPTION_SEL)
        return [(loc.nth(i), t) for i, t in rows]
    except Exception:  # noqa: BLE001
        return []


def read_combo_options(page, loc) -> list[str]:
    """Open a custom dropdown, read its options, close it (so the answer can be matched to a real option)."""
    try:
        click(page, loc)
        for _ in range(8):
            page.wait_for_timeout(100)
            opts = visible_options(page, loc)
            if opts:
                texts = list(dict.fromkeys(t for _, t in opts))[:120]
                page.keyboard.press("Escape")
                page.wait_for_timeout(120)
                if visible_options(page, loc):   # Escape did not close it (toggle-style dropdown): click the control again
                    click(page, loc)
                    page.wait_for_timeout(150)
                return [t for t in texts if not re.match(r"^(select|choose|please|no results|loading)", t, re.I)]
        page.keyboard.press("Escape")
    except Exception:  # noqa: BLE001
        pass
    return []


LAST_COMBO = ""   # what the last failed dropdown looked like (for the log: option count + a few texts, never typed values)


def pick_in_scrolling_list(page, loc, names: list[str]) -> bool:
    """Open a listbox button, scroll through ALL its rows (long lists only render the visible ones) and click the row whose text EQUALS one of the
    wanted names (never a prefix guess: type-ahead picked Indonesia for India). True only when the control then shows that text."""
    try:
        box = loc.bounding_box(timeout=1500)
    except Exception:  # noqa: BLE001
        box = None
    if not box:
        return False
    if visible_options(page, loc):
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
    click(page, loc)
    page.wait_for_timeout(350)
    for name in names:
        # brackets that carry a NAME are part of the answer: "Citizen (India)" is not "Citizen (Finland)" (Nov 18, Micron: comparing with the
        # brackets stripped matched the first "Citizen" row = Finland)
        keep = bool(re.search(r"\([^)]*[A-Za-z]{3,}[^)]*\)", name))
        target = re.sub(r"[^a-z0-9]+", " ", (name if keep else re.sub(r"\(.*\)", "", name)).lower()).strip()
        if len(target) < 3:
            continue
        found = page.evaluate("""async ([b, target, keep]) => {
            const norm = (t) => (t || '').toLowerCase().replace(keep ? /[()]/g : /\([^)]*\)/g, ' ').replace(/[^a-z0-9]+/g, ' ').trim();
            const lists = Array.from(document.querySelectorAll('ul[role=listbox]')).filter(u => { const q = u.getBoundingClientRect();
                return q.height > 20 && q.bottom > 0 && q.top < innerHeight && q.top > b.y - 480 && q.top < b.y + b.height + 480; });
            const ul = lists.sort((x, y) => Math.abs(x.getBoundingClientRect().top - b.y) - Math.abs(y.getBoundingClientRect().top - b.y))[0];
            if (!ul) return 'nolist';
            ul.scrollTop = 0; await new Promise(r => setTimeout(r, 60));
            for (let i = 0; i < 120; i++) {
                const hit = Array.from(ul.querySelectorAll('li[role=option]')).find(li => norm(li.innerText) === target);
                if (hit) { const tgt = hit.querySelector('button, [role=button]') || hit; tgt.setAttribute('data-fp-pick', '1'); tgt.scrollIntoView({block: 'center'}); return 'ok'; }
                const before = ul.scrollTop; ul.scrollTop += 140; await new Promise(r => setTimeout(r, 40));
                if (ul.scrollTop === before) break;
            }
            return 'absent'; }""", [box, target, keep])
        global LAST_COMBO
        LAST_COMBO = f"scroll-pick '{name[:20]}': {found}"
        if found == "ok":
            try:
                page.locator('[data-fp-pick="1"]').first.click(timeout=2500)
            except Exception:  # noqa: BLE001
                try:
                    page.locator('[data-fp-pick="1"]').first.evaluate("e => e.click()")
                except Exception:  # noqa: BLE001
                    pass
            finally:
                try:
                    page.evaluate("document.querySelectorAll('[data-fp-pick]').forEach(e => e.removeAttribute('data-fp-pick'))")
                except Exception:  # noqa: BLE001
                    pass
            page.wait_for_timeout(250)
            shown = ""
            try:
                # the control's OWN text: its wrapper also contains the open list ("India, 2 matches found, British Indian Ocean Territory, India"),
                # which made an unselected box look chosen (Nov 18, Micron "Country of Residence")
                shown = (loc.evaluate("e => { const c = e.cloneNode(true); c.querySelectorAll('[role=listbox],ul,[aria-live],[role=status]').forEach(x => x.remove()); return c.innerText || '' }") or "").strip()
            except Exception:  # noqa: BLE001
                pass
            norm_shown = re.sub(r"[^a-z0-9]+", " ", shown.lower()).strip()
            if shown and (target in norm_shown or norm_shown in target) and not re.match(r"^(select|choose|please)", shown, re.I):
                return True
        elif found == "nolist":
            break
    try:
        page.keyboard.press("Escape")
    except Exception:  # noqa: BLE001
        pass
    return False


def _popup_closed(page) -> bool:
    page.wait_for_timeout(200)
    return not visible_options(page, loc)


def unique_overlap(texts: list[str], value: str) -> str:
    """The ONE option sharing a distinctive word with value (Race 'Asian (Indian)' -> 'Indian (India)'); "" when none or several."""
    toks = {w for w in re.findall(r"[a-z]{4,}", value.lower()) if w not in GENERIC_WORDS}
    rel = sorted({t for t in texts if toks & set(re.findall(r"[a-z]{4,}", t.lower())) and not re.search(r"\b(not|do not|don't|decline|prefer not)\b", t, re.I)})
    return rel[0] if len(rel) == 1 else ""


def _own_text(loc) -> str:
    """What the control itself shows, WITHOUT the open list / screen-reader text inside its wrapper ("India, 2 matches found, ... India")."""
    try:
        return (loc.evaluate("e => { const c = e.cloneNode(true); c.querySelectorAll('[role=listbox],ul,[aria-live],[role=status]').forEach(x => x.remove()); return (c.innerText || '') + ' ' + [...e.querySelectorAll('input')].map(i => (i.getAttribute('role') === 'combobox' && i.getAttribute('aria-expanded') === 'true' ? '' : i.value)).join(' ') }") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


GENERIC_WORDS = {"citizen", "non", "status", "please", "select", "other", "others", "none", "yes", "prefer", "decline", "identify", "wish", "answer"}


def best_option(texts: list[str], v: str) -> str:
    """The option that MEANS v, best match first: identical, then starts with it ("India +91"), then contains it as a whole word, then any substring.
    (First-substring picked 'British Indian Ocean Territory' for 'India'.)"""
    nv = _norm(v)
    if not nv:
        return ""
    norm = [(t, _norm(re.sub(r"\(.*?\)", " ", t))) for t in texts]
    for t, n in norm:
        if n == nv or _norm(t) == nv:
            return t
    for t, n in norm:
        if n.startswith(nv + " ") or n.startswith(nv):
            return t
    for t, n in norm:
        if re.search(rf"(?<![a-z0-9]){re.escape(nv)}(?![a-z0-9])", n):
            return t
    return next((t for t, n in norm if nv in n), "")


def _wd_multi(loc) -> bool:
    try:
        return bool(loc.evaluate("e => !!e.closest('[data-automation-id=multiSelectContainer]')"))
    except Exception:  # noqa: BLE001
        return False


def _wd_selected(loc) -> bool:
    try:
        return bool(loc.evaluate("""e => { const c = e.closest('[data-automation-id=multiSelectContainer]'); if (!c) return false;
            const x = c.querySelector('[data-automation-id=selectedItem], [data-automation-id=selectedItemList] li, [data-automation-id=promptSelectionLabel]');
            return !!(x && (x.innerText || '').trim()); }"""))
    except Exception:  # noqa: BLE001
        return False


_WD_SOURCE_FALLBACKS = ["LinkedIn", "Job Board", "Job Site", "Career Site", "Company Website", "Corporate Website", "Website", "Internet", "Other"]


def set_workday_multiselect(page, loc, value: str, alts: list[str] | None = None) -> bool:
    """Workday's search-style multiselect ("How Did You Hear About Us?", skills, schools): type a word, press ENTER (the list
    is only searched then), click the matching row (categories open a second list: up to 3 levels), and only call it done when
    the field shows a selected pill. Tries the wanted wording, then generic ones (Nov 18: typing without Enter showed 0 options)."""
    global LAST_COMBO
    seen: set[str] = set()
    words = [w for w in ([value] + list(alts or []) + _WD_SOURCE_FALLBACKS) if w and not (w.lower() in seen or seen.add(w.lower()))]
    for v in words[:7]:
        try:
            _scroll(loc)
            if _wd_selected(loc):
                return True
            click(page, loc)
            page.keyboard.press("Control+A")
            loc.press_sequentially(re.sub(r"\(.*\)", "", v).strip() or v, delay=35, timeout=6000)
            page.keyboard.press("Enter")
            for level in range(3):
                opts = []
                for _ in range(30):
                    page.wait_for_timeout(150)
                    opts = visible_options(page, loc)
                    if opts:
                        break
                texts = [t for _, t in opts]
                LAST_COMBO = f"workday multiselect '{v[:18]}' level {level}: {len(opts)} options e.g. " + " | ".join(t[:24] for t in texts[:5])
                if not opts:
                    break
                pick = best_option(texts, v) or next((t for t in texts if v.lower() in t.lower()), None) or (texts[0] if level else None)
                if not pick:
                    break
                o = next(o for o, t in opts if t == pick)
                if not click(page, o):
                    break
                page.wait_for_timeout(500)
                if _wd_selected(loc):
                    page.keyboard.press("Escape")
                    return True
            page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            continue
    return _wd_selected(loc)


def set_combo(page, loc, value: str, alts: list[str] | None = None) -> bool:
    """Custom dropdown / search-box dropdown (Workday...): open it, type a NAME to filter (never '+91': the list is searched by name),
    click the option that means the same as value, and only call it done when the list has closed. Keyboard (Down + Enter) as a fallback."""
    global LAST_COMBO
    if _wd_multi(loc):
        return set_workday_multiselect(page, loc, value, alts)
    tries = [value] + [a for a in (alts or []) if a != value]
    is_input = False
    try:
        is_input = loc.evaluate("e => e.tagName === 'INPUT' || e.isContentEditable")
    except Exception:  # noqa: BLE001
        pass
    full_value = value
    if is_input:   # names first ("india"), codes / numbers last
        tries.sort(key=lambda t: not re.search(r"[A-Za-z]{3,}", t))
        # a type-ahead list opened with a generic word lists ARBITRARY entries (Micron citizenship: 'Citizen' -> Finland first): search by the
        # distinctive bracketed part ('Citizen (India)' -> 'India') before the generic one
        inner = [m.group(1).strip() for t in list(tries) for m in [re.search(r"\(([^)]*[A-Za-z]{3,}[^)]*)\)", t)] if m]
        tries = inner + [t for t in tries if t not in inner]
    if not is_input:
        # the full wording first; the bracket-stripped form only when the brackets hold no name ("India (+91)" -> "India")
        names = [t for t in tries if re.search(r"[A-Za-z]{3,}", t)]
        names += [re.sub(r"\(.*\)", "", t).strip() for t in tries
                  if re.search(r"[A-Za-z]{3,}", t) and not re.search(r"\([^)]*[A-Za-z]{3,}[^)]*\)", t)]
        if names and pick_in_scrolling_list(page, loc, names[:6]):
            return True
    if visible_options(page, loc):   # a list left open by the PREVIOUS dropdown (Workday keeps it open after a choice) would swallow this click: close it first
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
    for attempt, v in enumerate(tries[:5]):
        try:
            if not visible_options(page, loc):
                click(page, loc)
            if is_input:
                page.keyboard.press("Control+A")
                loc.press_sequentially(re.sub(r"\(.*\)", "", v).strip() or v, delay=15, timeout=6000)
            opts = []
            for _ in range(20):
                page.wait_for_timeout(100)
                opts = visible_options(page, loc)
                if opts:
                    break
            if is_input and (not opts or all(re.match(r"^\W*(no (options?|results?|matches)( found)?)\W*$", t, re.I) for _, t in opts)):
                # typing the whole answer filtered the list to nothing ("No, I am not a protected veteran" is not inside the
                # option "I am not a protected veteran"): clear the filter and choose from the FULL list instead
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                for _ in range(15):
                    page.wait_for_timeout(100)
                    opts = visible_options(page, loc)
                    if opts:
                        break
            texts = [t for _, t in opts]
            pick = best_option(texts, full_value) or best_option(texts, v)
            if not pick and is_input:   # one distinctive-word overlap, and only ONE such option (Race 'Asian (Indian)' -> 'Indian (India)')
                toks = {w for w in re.findall(r"[a-z]{4,}", full_value.lower()) if w not in GENERIC_WORDS}
                rel = [t for t in texts if toks & set(re.findall(r"[a-z]{4,}", t.lower()))]
                if len(set(rel)) == 1:
                    pick = rel[0]
            if not pick and (attempt > 0 or is_input):   # loose synonyms ("website" ~ "Corporate Website") only AFTER the exact wording had its chance (type-ahead below)
                pick = alias_match(v, texts)
            if pick:
                o = next(o for o, t in opts if t == pick)
                try:   # a list row is often <li><button>: the click must land on the button (Micron: the <li> click selected nothing)
                    inner = o.locator("button, [role=button]").first
                    if inner.count():
                        o = inner
                except Exception:  # noqa: BLE001
                    pass
                if click(page, o):
                    page.wait_for_timeout(200)
                    if not is_input:   # a plain dropdown shows what it holds: an unchanged "Select" means the click selected nothing
                        own = ""
                        try:
                            own = (loc.evaluate("e => { const c = e.cloneNode(true); c.querySelectorAll('[role=listbox],ul,[aria-live],[role=status]').forEach(x => x.remove()); return c.innerText || '' }") or "").strip()
                        except Exception:  # noqa: BLE001
                            own = pick
                        if re.match(r"^(select|choose|please|--)", own, re.I) or not own:
                            page.keyboard.press("Escape")
                            continue
                    page.keyboard.press("Escape")   # close the list so it does not cover the next field
                    page.wait_for_timeout(80)
                    return True   # search-box dropdowns keep showing list items after a choice and never echo the value: a clicked option is the success signal
                try:
                    o.hover()
                except Exception:  # noqa: BLE001
                    pass
                page.keyboard.press("Enter")
                if _popup_closed(page):
                    return True
            if not pick and not is_input:
                # a long scrolling list shows only some rows: type the name (a listbox jumps to the item that starts with it) and press Enter
                # Type-ahead list that shows only a few arbitrary rows (Micron): SEARCH for the distinctive text, then click the row whose FULL text
                # is the answer, and check the box really holds it. Never press Enter on "whatever came first" ("Citizen" -> Citizen (Finland)).
                m_in = re.search(r"\(([^)]*[A-Za-z]{3,}[^)]*)\)", full_value)
                search = m_in.group(1).strip() if m_in else re.sub(r"\(.*\)", "", v).strip()
                if re.search(r"[A-Za-z]{3,}", search):
                    page.keyboard.type(search, delay=70)
                    opts2 = []
                    for _ in range(15):
                        page.wait_for_timeout(120)
                        opts2 = visible_options(page, loc)
                        if opts2:
                            break
                    texts2 = [t for _, t in opts2]
                    pick2 = best_option(texts2, full_value) or unique_overlap(texts2, full_value)
                    if pick2:
                        o2 = next(o for o, t in opts2 if t == pick2)
                        try:
                            inner2 = o2.locator("button, [role=button]").first
                            if inner2.count():
                                o2 = inner2
                        except Exception:  # noqa: BLE001
                            pass
                        if click(page, o2):
                            page.wait_for_timeout(250)
                            if _own_text(loc) and not re.match(r"^(select|choose|please|--)", _own_text(loc), re.I):
                                page.keyboard.press("Escape")
                                return True
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
            LAST_COMBO = f"{len(opts)} options visible, e.g. " + " | ".join(t[:26] for t in texts[:5]) + f" (input={is_input}, tried {v[:14]})"
            page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            continue
    return False


def upload(page, loc, path: str) -> bool:
    try:
        loc.set_input_files(path, timeout=8000)
        page.wait_for_timeout(1200)
        return True
    except Exception:  # noqa: BLE001
        return False


def apply_answer(page, snap: dict, field: dict[str, Any], ans: dict[str, Any]) -> bool:
    k, value = field["kind"], ans["value"]
    if not value:
        return False
    if k == "radio":
        return choose_radio(page, snap, field, value)
    loc = locate(snap, field["id"])
    if k == "checkbox":
        return set_checkbox(page, loc, value == "true")
    if k == "select":
        return set_select(page, loc, value)
    if k == "combo":
        return set_combo(page, loc, value, ans.get("alts"))
    return set_text(page, loc, value)
