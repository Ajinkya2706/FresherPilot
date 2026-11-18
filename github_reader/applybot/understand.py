"""Field understanding: what does this input EXPECT, and is my answer in that shape?

Three jobs, no AI needed for any of them:
  spec_for(field)            -> what the field is (email / phone / date / year / number / url / text ...) plus every constraint the page declares
                                (html type, pattern, min/max, length, inputmode, "Format: DD/MM/YYYY", "10 digits", "numbers only", "max 500 characters").
  conform(spec, value)       -> the SAME answer written the way this field wants it (phone without +91, date in the page's format, digits only, trimmed to
                                the length limit, https:// on links ...). Returns (value, problem): problem != "" means the value cannot fit this field at all.
  learn_error(spec, error)   -> the page said "enter a valid 10 digit mobile number": tighten the spec from that text so the next try is right.
  wait_ready(page)           -> let the page finish loading (spinners gone, DOM quiet) before anything is read or typed.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


# ------------------------------------------------------------------ page readiness
_READY_JS = r"""
async (maxMs) => {
  const t0 = Date.now();
  const busySel = '[aria-busy=true],[class*=spinner i],[class*=loading i],[class*=loader i],[class*=skeleton i],[role=progressbar],[data-automation-id*=progress i],[data-automation-id*=loading i]';
  const visible = (e) => { const r = e.getBoundingClientRect(), c = getComputedStyle(e); return r.width > 4 && r.height > 4 && c.visibility !== 'hidden' && c.display !== 'none' && +c.opacity > 0.05; };
  let lastMut = Date.now();
  const mo = new MutationObserver(() => { lastMut = Date.now(); });
  mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  let why = 'ok';
  while (Date.now() - t0 < maxMs) {
    const busy = Array.from(document.querySelectorAll(busySel)).some((e) => visible(e) && !/search|filter/i.test(e.className && e.className.toString()));
    const quiet = Date.now() - lastMut > 600;
    if (document.readyState === 'complete' && !busy && quiet) { mo.disconnect(); return 'ready'; }
    why = document.readyState !== 'complete' ? 'loading' : busy ? 'spinner' : 'changing';
    await new Promise((r) => setTimeout(r, 150));
  }
  mo.disconnect();
  return 'timeout:' + why;
}
"""


def wait_ready(page, max_ms: int = 12000) -> str:
    """Wait until the page has stopped loading: document complete, no visible spinner / skeleton, no DOM change for 0.6 s. Returns 'ready' or 'timeout:<why>'."""
    try:
        return page.evaluate(_READY_JS, max_ms)
    except Exception:  # noqa: BLE001 - the page navigated while we waited: that is fine, caller looks again
        try:
            page.wait_for_timeout(600)
        except Exception:  # noqa: BLE001
            pass
        return "navigated"


# ------------------------------------------------------------------ what a field is
def _hay(f: dict) -> str:
    return " ".join(str(f.get(k) or "") for k in ("label", "name", "placeholder", "autocomplete", "title")).lower()


def _kind_of(f: dict) -> str:
    """Semantic kind from html type / autocomplete / wording."""
    ht, ac, hay, k = (f.get("htype") or ""), (f.get("autocomplete") or ""), _hay(f), f.get("kind", "text")
    if k in ("select", "combo", "radio", "checkbox", "file"):
        return k
    if ht == "email" or ac == "email" or re.search(r"\be-?mail\b", hay):
        return "email"
    if ht == "url" or re.search(r"linkedin|github|portfolio|website|web ?site|\burl\b|profile link|blog|behance|\blink\b", hay):
        return "url"
    if ht == "tel" or ac.startswith("tel") or re.search(r"\b(phone|mobile|cell|whatsapp|contact (no|number))\b", hay):
        return "phone"
    if ht in ("date", "month", "datetime-local") or ac in ("bday",) or re.search(r"\b(dob|date of birth|birth ?date|start date|end date|from date|to date|date)\b|dd ?/ ?mm|mm ?/ ?dd|yyyy", hay):
        return "date"
    if re.search(r"\b(zip|postal|pin ?code|post ?code)\b", hay) or ac == "postal-code":
        return "pincode"
    if re.search(r"\b(year of (passing|graduation|completion)|passing year|graduation year|batch|year)\b", hay) and not re.search(r"years? of (experience|exp)|experience", hay):
        return "year"
    if re.search(r"\b(ctc|salary|compensation|stipend|lpa|package)\b", hay):
        return "money"
    if re.search(r"\b(cgpa|gpa|percentage|percent|marks|aggregate|grade)\b", hay):
        return "score"
    if ht == "number" or f.get("inputmode") in ("numeric", "decimal") or re.search(r"years? of (experience|exp)|notice period|how many|number of|\bage\b|\bexperience\b.*\b(years|months)\b|in (years|months|days)", hay):
        return "number"
    if k == "textarea":
        return "longtext"
    if re.search(r"\b(first|given|fore) ?name\b|\bfname\b", hay) or ac == "given-name":
        return "first_name"
    if re.search(r"\b(last|sur|family) ?name\b|\blname\b", hay) or ac == "family-name":
        return "last_name"
    if re.search(r"\bfull name\b|^name\b|\byour name\b|candidate name", hay) or ac == "name":
        return "full_name"
    return "text"


_DATE_FMTS = [  # (regex over placeholder/hint text, python strftime-ish tokens)
    (r"yyyy\s*[-/.]\s*mm\s*[-/.]\s*dd", "%Y{s}%m{s}%d", None),
    (r"dd\s*[-/.]\s*mm\s*[-/.]\s*yyyy", "%d{s}%m{s}%Y", None),
    (r"mm\s*[-/.]\s*dd\s*[-/.]\s*yyyy", "%m{s}%d{s}%Y", None),
    (r"dd\s*[-/.]\s*mm\s*[-/.]\s*yy\b", "%d{s}%m{s}%y", None),
    (r"mm\s*[-/.]\s*dd\s*[-/.]\s*yy\b", "%m{s}%d{s}%y", None),
    (r"dd\s*[-/ ]\s*mmm\s*[-/ ,]+\s*yyyy", "%d{s}%b{s}%Y", None),
    (r"mmm\s*[-/ ]\s*dd\s*,?\s*[-/ ]*\s*yyyy", "%b{s}%d{s}%Y", None),
    (r"mm\s*[-/.]\s*yyyy", "%m{s}%Y", None),
    (r"mmm\s*[-/ ]?\s*yyyy|month\s*yyyy", "%b{s}%Y", None),
]


def _sep(text: str) -> str:
    m = re.search(r"(?:dd|mm|mmm|yyyy)\s*([-/.])\s*(?:dd|mm|mmm|yyyy|yy)", text)
    return m.group(1) if m else "/"


def parse_constraints(text: str) -> dict:
    """Constraints written in words (help text, placeholder, error message)."""
    t = (text or "").lower()
    c: dict = {}
    m = re.search(r"\b(\d{1,2})[- ]?digits?\b", t)
    if m:
        c["digits"] = int(m.group(1))
    m = re.search(r"(?:max(?:imum)?|up to|not (?:more|exceed)\w*(?: than)?|at most|limit(?:ed)? to|within|<=?)\s*(\d{1,5})\s*(char|letter|word|digit)", t) or re.search(r"(\d{1,5})\s*(char|letter|word)\w*\s*(?:max|limit|allowed|or (?:less|fewer))", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else "char"
        if unit == "word":
            c["maxwords"] = n
        elif unit != "digit":
            c["maxlen"] = n
    m = re.search(r"(?:min(?:imum)?|at least)\s*(\d{1,4})\s*(char|letter|word)", t)
    if m:
        c["minlen" if m.group(2) != "word" else "minwords"] = int(m.group(1))
    m = re.search(r"(?:between|from)\s*(-?\d+(?:\.\d+)?)\s*(?:and|to|-)\s*(-?\d+(?:\.\d+)?)", t) or re.search(r"(?:range|value)\D{0,12}(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)", t)
    if m:
        c["min"], c["max"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"(?:min(?:imum)?(?: value)?|greater than or equal to|at least)\s*(?:of )?(-?\d+(?:\.\d+)?)\b(?!\s*(?:char|letter|word))", t)
    if m and "min" not in c:
        c["min"] = float(m.group(1))
    m = re.search(r"(?:max(?:imum)?(?: value)?|less than or equal to|no more than|not (?:more|greater) than)\s*(?:of )?(-?\d+(?:\.\d+)?)\b(?!\s*(?:char|letter|word))", t)
    if m and "max" not in c:
        c["max"] = float(m.group(1))
    if re.search(r"numbers? only|only (numbers?|digits?|numeric)|digits only|numeric(?:al)? (value|only)|enter (a )?(valid )?(number|numeric)|must be (a )?number|only numeric|whole number|integer", t):
        c["numeric"] = True
    if re.search(r"whole number|integer|no decimals?", t):
        c["integer"] = True
    if re.search(r"letters only|alphabets? only|only (letters|alphabets?)|no (numbers|digits)|alphabetic", t):
        c["alpha"] = True
    if re.search(r"no special char|without special char|alphanumeric", t):
        c["nospecial"] = True
    if re.search(r"(with|include|including|add|plus) (the )?country code|\+91 ?\d|\+\d{1,3} format|e\.?164|start with \+", t):
        c["cc_in"] = True
    if re.search(r"without (the )?(country code|\+91|isd)|do not (include|add) (the )?(country code|\+91)|excluding (the )?country code", t):
        c["cc_out"] = True
    if re.search(r"https?://|full url|start with http|include https?|valid url|enter (a )?(valid )?(link|url|website)", t):
        c["url"] = True
    if re.search(r"\blpa\b|lakhs?|lacs?", t):
        c["unit"] = "lpa"
    elif re.search(r"\binr\b|rupees|₹|full amount|per annum|annual(ly)?\b|in rs", t):
        c["unit"] = "inr"
    if re.search(r"per month|monthly", t):
        c["unit"] = "monthly"
    if re.search(r"in months", t):
        c["unit"] = "months"
    elif re.search(r"in years|\(years\)|years\b", t) and "unit" not in c:
        c["unit"] = "years"
    if re.search(r"out of 10|/ ?10\b|cgpa|on a (scale of )?10", t):
        c["scale"] = 10
    elif re.search(r"out of 4|/ ?4\b|scale of 4", t):
        c["scale"] = 4
    elif re.search(r"percent|%|out of 100", t):
        c["scale"] = 100
    # date format
    for rx, fmt, sep in _DATE_FMTS:
        if re.search(rx, t):
            s = sep or _sep(t)
            c["datefmt"] = fmt.replace("{s}", " " if "%b" in fmt and re.search(r"mmm\s* ", t) else s)
            break
    if re.search(r"\bvalid (e-?mail|email address)|e-?mail (address )?is (invalid|not valid)", t):
        c["kind_email"] = True
    if re.search(r"valid (mobile|phone|contact)|(mobile|phone)( number)? (is )?(invalid|not valid)", t):
        c.setdefault("digits", 10)
    return c


def spec_for(f: dict) -> dict:
    """Everything known about what this field accepts."""
    sem = _kind_of(f)
    hint = " ".join([str(f.get("hint") or ""), str(f.get("placeholder") or ""), str(f.get("title") or ""), str(f.get("label") or "")])
    c = parse_constraints(hint)
    ht = f.get("htype") or ""
    sp: dict = {"sem": sem, "htype": ht, "constraints": c, "learned": [], "hay": _hay(f)}
    if f.get("maxlength"):
        c["maxlen"] = min(int(f["maxlength"]), c.get("maxlen", 10 ** 6))
    if f.get("minlength"):
        c["minlen"] = max(int(f["minlength"]), c.get("minlen", 0))
    for key in ("min", "max"):
        if f.get(key) not in (None, ""):
            try:
                c[key] = float(f[key])
            except ValueError:
                pass
    if f.get("pattern"):
        sp["pattern"] = f["pattern"]
        p = f["pattern"]
        m = re.fullmatch(r"\^?\[?0?-?9\]?\{(\d+)\}\$?|\^?\\d\{(\d+)\}\$?", p)
        if m:
            c["digits"] = int(m.group(1) or m.group(2))
            c["numeric"] = True
    if ht in ("number", "range") or f.get("inputmode") in ("numeric", "decimal"):
        c["numeric"] = True
        if f.get("inputmode") == "numeric" and ht != "number" and "." not in str(f.get("step") or ""):
            c["integer"] = c.get("integer", False) or sem in ("year", "pincode", "phone")
    if sem == "date" and ht == "date":
        c["datefmt"] = "%Y-%m-%d"
    elif sem == "date" and ht == "month":
        c["datefmt"] = "%Y-%m"
    sp["disabled"] = bool(f.get("disabled") or f.get("readonly"))
    return sp


# ------------------------------------------------------------------ value shaping
def _digits(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _parse_date(v: str):
    v = (v or "").strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", v)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", v)   # DD/MM/YYYY (the profile is Indian)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"(\d{1,2})[-/ ]([A-Za-z]{3,9})[-/ ,]+(\d{4})", v)
    if m and m.group(2).lower()[:3] in [x[:3] for x in MONTHS]:
        return int(m.group(3)), [x[:3] for x in MONTHS].index(m.group(2).lower()[:3]) + 1, int(m.group(1))
    return None


def _fmt_date(ymd, fmt: str) -> str:
    y, mo, d = ymd
    out = fmt
    out = out.replace("%Y", f"{y:04d}").replace("%y", f"{y % 100:02d}").replace("%m", f"{mo:02d}").replace("%d", f"{d:02d}")
    out = out.replace("%b", MONTHS[mo - 1][:3].title())
    return out


def _cut(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    cut = text[:n]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end > n * 0.5:
        return cut[: end + 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip(" ,;:-")


def conform(sp: dict, value: str, profile: dict | None = None) -> tuple[str, str]:
    """(value written the way the field wants it, problem). problem = "" when it fits; otherwise why it cannot (the engine then asks the AI with that reason)."""
    v = (value or "").strip()
    if not v:
        return v, ""
    sem, c = sp["sem"], sp["constraints"]
    if sem == "email":
        v = v.replace(" ", "").lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", v):
            return v, "not an email address"
    elif sem == "phone":
        d = _digits(v)
        if d.startswith("0091"):
            d = d[4:]
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        elif len(d) == 11 and d.startswith("0"):
            d = d[1:]
        want = c.get("digits")
        if c.get("cc_in") or (c.get("maxlen") in (13, 14, 15) and not c.get("cc_out") and len(d) == 10 and sp.get("cc_hint")):
            v = "+91" + d
        elif want == 12 and len(d) == 10:
            v = "91" + d
        else:
            v = d
        if len(d) != 10 and not (want and len(_digits(v)) == want):
            return v, f"phone has {len(d)} digits"
    elif sem == "pincode":
        v = _digits(v)[:6]
        if len(v) != 6:
            return v, "pin code needs 6 digits"
    elif sem == "year":
        m = re.search(r"(19|20)\d{2}", v)
        if not m:
            return v, "not a year"
        v = m.group(0)
    elif sem == "date":
        ymd = _parse_date(v)
        if not ymd and re.search(r"immediate|asap|now|^0|within 15|serving", v, re.I) and re.search(r"avail|join|start|from|earliest|notice", sp.get("hay", "")):
            t = date.today()
            ymd = (t.year, t.month, t.day)   # "Immediate" notice period asked as a date = today
        if not ymd:
            return v, "not a date"
        fmt = c.get("datefmt") or ("%Y-%m-%d" if sp.get("htype") == "date" else "%d/%m/%Y")
        v = _fmt_date(ymd, fmt)
    elif sem == "url":
        low = v.lower()
        if re.fullmatch(r"(www\.)?[\w.-]+\.[a-z]{2,}(/\S*)?", low) and not low.startswith("http"):
            v = "https://" + v
        if c.get("url") and not v.lower().startswith("http"):
            return v, "needs a full link starting with https://"
    elif sem in ("number", "money", "score"):
        m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
        if not m:
            if c.get("numeric") or sem != "number":
                return v, "needs a number"
        else:
            x = float(m.group(0))
            if sem == "score":
                scale = c.get("scale")
                if scale == 100 and x <= 10:
                    x = x * 9.5   # CGPA out of 10 -> percentage (the usual university formula)
                elif scale == 10 and x > 10:
                    x = x / 9.5
                elif scale == 4 and x > 4:
                    x = x / 100 * 4 if x > 10 else x * 0.4
                v = f"{x:.2f}".rstrip("0").rstrip(".") if "%" not in v else f"{x:.2f}"
            else:
                if "min" in c and x < c["min"]:
                    x = c["min"]
                if "max" in c and x > c["max"]:
                    x = c["max"]
                unit = c.get("unit")
                if sem == "money":   # profile CTC is in LPA: write it in the unit this field uses
                    if unit == "inr" and x < 1000:
                        x *= 100000
                    elif unit == "monthly" and x < 1000:
                        x = x * 100000 / 12
                    elif unit == "lpa" and x >= 1000:
                        x /= 100000
                if sem == "number" and unit == "months" and re.search(r"year", v, re.I):
                    x *= 12
                v = f"{int(round(x))}" if (c.get("integer") or x == int(x)) else f"{x:g}"
            if c.get("numeric") and not re.fullmatch(r"-?\d+(\.\d+)?", v):
                return v, "needs a plain number"
    elif sem in ("first_name", "last_name", "full_name"):
        v = re.sub(r"\s+", " ", re.sub(r"[\d_@#$%^&*()+=<>{}\[\]|\\/~`!?:;\"]", "", v)).strip()
    if c.get("digits") and sem not in ("phone", "pincode") and c.get("numeric", True) and sem in ("text", "number", "money"):
        d = _digits(v)
        if d:
            v = d
        if len(d) != c["digits"]:
            return v, f"needs exactly {c['digits']} digits"
    elif c.get("numeric") and sem == "text":
        v2 = re.sub(r"[^\d.]", "", v)
        if v2:
            v = v2
    if c.get("alpha"):
        v = re.sub(r"[^A-Za-z .'-]", "", v).strip()
    elif c.get("nospecial"):
        v = re.sub(r"[^A-Za-z0-9 ]", "", v).strip()
    if c.get("maxwords"):
        w = v.split()
        if len(w) > c["maxwords"]:
            v = " ".join(w[: c["maxwords"]])
    n = c.get("maxlen")
    if n and len(v) > n:
        v = _cut(v, n) if sem in ("longtext", "text") else v[:n]
    if c.get("minlen") and len(v) < c["minlen"]:
        return v, f"needs at least {c['minlen']} characters"
    if sp.get("pattern"):
        try:
            if not re.fullmatch(sp["pattern"], v):
                return v, "does not match the field's pattern"
        except re.error:
            pass
    return v, ""


def learn_error(sp: dict, error: str) -> bool:
    """The page rejected a value and said why: fold that text into the spec. True when the spec changed (so re-shaping the answer may fix it)."""
    if not error:
        return False
    new = parse_constraints(error)
    if re.search(r"e-?mail", error, re.I):
        new["kind_email"] = True
    c = sp["constraints"]
    changed = False
    for k, v in new.items():
        if k == "kind_email":
            if sp["sem"] != "email":
                sp["sem"] = "email"
                changed = True
            continue
        if c.get(k) != v:
            c[k] = v
            changed = True
    # generic wording
    if re.search(r"valid (date|dob)|invalid date|date (is )?(invalid|required)", error, re.I) and sp["sem"] != "date":
        sp["sem"] = "date"
        changed = True
    if re.search(r"valid (phone|mobile|contact)|invalid (phone|mobile)", error, re.I) and sp["sem"] != "phone":
        sp["sem"] = "phone"
        changed = True
    if re.search(r"valid (url|link|website)|invalid (url|link)", error, re.I) and sp["sem"] != "url":
        sp["sem"] = "url"
        c["url"] = True
        changed = True
    if re.search(r"already (exists|registered|in use|taken)", error, re.I):
        sp["learned"].append("duplicate")   # not fixable by reshaping
    if changed:
        sp["learned"].append(error[:80])
    return changed


def describe(sp: dict) -> str:
    """One line for the AI prompt: what this field expects."""
    c = sp["constraints"]
    bits = [f"type={sp['sem']}"]
    if c.get("datefmt"):
        bits.append("date format " + c["datefmt"].replace("%Y", "YYYY").replace("%m", "MM").replace("%d", "DD").replace("%b", "Mon").replace("%y", "YY"))
    if c.get("digits"):
        bits.append(f"exactly {c['digits']} digits")
    elif c.get("numeric"):
        bits.append("digits only" if c.get("integer") else "a plain number")
    if c.get("unit"):
        bits.append("unit " + c["unit"])
    if "min" in c or "max" in c:
        bits.append(f"range {c.get('min', '')}..{c.get('max', '')}")
    if c.get("maxlen"):
        bits.append(f"max {c['maxlen']} characters")
    if c.get("maxwords"):
        bits.append(f"max {c['maxwords']} words")
    if c.get("minlen"):
        bits.append(f"min {c['minlen']} characters")
    if c.get("alpha"):
        bits.append("letters only")
    if c.get("url"):
        bits.append("full https:// link")
    if c.get("scale"):
        bits.append(f"scale out of {c['scale']}")
    return ", ".join(bits)
