"""Answers for form fields: the answer bank first (no AI), then the AI only for required questions the bank does not know."""
from __future__ import annotations

import difflib
import json
import re
from typing import Any, Callable

from .answerbank import alias_match, bank_answer, alts as _alts
from .understand import conform, describe, learn_error, spec_for

CONSENT = re.compile(r"(check (the )?box|tick (the )?box|^\W*(i |we )?(agree|accept|consent|confirm|acknowledge|understand)\b|have read (and|the)|confirm (that )?(you|i)|i agree|agree to|i accept|accept (the )?(terms|privacy|policy)|consent|terms (and|&) conditions|privacy (policy|notice|statement)|declar|certify|confirm that|acknowledge|"
                     r"i have read|authori[sz]e|data (protection|processing)|information (provided|given) (is|are) (true|correct|accurate))", re.I)
MARKETING = re.compile(r"(follow |newsletter|marketing|promotional|job alerts?|email me|text me|sms|notify me|keep me (informed|updated)|talent community|stay connected|opt[- ]?in|receive (updates|emails|communications))", re.I)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.%< -]+", " ", (t or "").lower())).strip()


def match_option(value: str, options: list[str]) -> str:
    if not value or not options:
        return ""
    v = _norm(value)
    norm = {o: _norm(o) for o in options if str(o).strip()}
    for o, n in norm.items():
        if n == v:
            return o
    if v in {"yes", "true", "y"}:
        for o, n in norm.items():
            if n.startswith("yes") or n in {"y", "true"}:
                return o
    if v in {"no", "false", "n"}:
        for o, n in norm.items():
            if n == "no" or n.startswith("no ") or n.startswith("no,") or n in {"n", "false"}:
                return o
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        x = float(v)
        for o, n in norm.items():
            r = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", n)
            if r and float(r.group(1)) <= x <= float(r.group(2)):
                return o
            lt = re.search(r"(less than|under|below|<)\s*(\d+)", n)
            if lt and x < float(lt.group(2)):
                return o
            mp = re.search(r"(\d+(?:\.\d+)?)\s*\+|(\d+(?:\.\d+)?)\s*(?:or more|and above)", n)
            if mp and x >= float(mp.group(1) or mp.group(2)):
                return o
            if x == 0 and re.search(r"\bfresher\b|\bno experience\b|^0$|\bnone\b", n):
                return o
    for o, n in norm.items():
        if min(len(v), len(n)) >= 2 and (re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", n) or re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", v)):
            return o
    a = alias_match(value, options)
    if a:
        return a
    best = difflib.get_close_matches(v, list(norm.values()), n=1, cutoff=0.72)
    return next((o for o, n in norm.items() if n == best[0]), "") if best else ""


def ctc_for(field: dict[str, Any], raw: str) -> str:
    """Profile CTC (4 / 4.5 LPA / 400000) in the unit the field asks for (default: LPA)."""
    m = re.search(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    if not m:
        return ""
    amount = float(m.group(0))
    if amount == 0:
        return "1"   # a fresher has no salary, but portals reject 0 ("must be greater than 0"): owner said enter 1 (Nov 19)
    lpa = amount / 100000 if amount >= 1000 else amount
    hint = f"{field.get('label', '')} {field.get('placeholder', '')} {field.get('hint', '')}".lower()
    if re.search(r"monthly|per month", hint):
        v = lpa * 100000 / 12
    elif re.search(r"lpa|lakh|lac", hint):
        v = lpa
    elif re.search(r"inr|rupee|₹|per annum|annual|\bpa\b|in rs|full amount", hint):
        v = lpa * 100000
    else:
        v = lpa
    return f"{v:g}" if v < 1000 else str(int(round(v)))


def as_app_field(f: dict[str, Any]) -> dict[str, Any]:
    kind = {"combo": "combobox", "tel": "text", "password": "text", "code": "text", "date": "text"}.get(f["kind"], f["kind"])
    label = f["label"]
    if f["kind"] in ("combo", "select"):
        # Workday names a dropdown "<Question> <current value> Required": strip the noise so the question is recognised ("Country Indonesia Required" -> "Country")
        label = re.sub(r"\s+(required|select one)\b", "", label, flags=re.I).strip()
        val = (f.get("value") or "").strip()
        if val and label.lower().endswith(val.lower()) and len(label) > len(val):
            label = label[: -len(val)].strip()
    sp = spec_for(f)
    return {"id": f["id"], "name": f.get("name", ""), "type": kind, "label": label, "options": f.get("options") or [], "placeholder": f.get("placeholder", ""),
            "maxlength": f.get("maxlength") or None, "hint": f.get("hint", ""), "required": f["required"],
            "expects": describe(sp) if f["kind"] not in ("combo", "select", "radio", "checkbox", "file") else "",
            "error": f.get("error") or f.get("validation") or ""}


def compact_profile(profile: dict[str, Any]) -> str:
    p, j, e = profile["personal"], profile["job_preferences"], profile.get("education", [])
    lines = [f"Name: {p.get('full_name')}; email {p.get('email')}; phone {p.get('phone_country_code')} {p.get('phone')}; {p.get('city')}, {p.get('state')}, {p.get('country')}",
             f"Experience: {j.get('total_experience_years')} years full-time; {j.get('relevant_experience')}",
             f"Current CTC {j.get('current_ctc_lpa', '0')} LPA (not employed now: for current / last / ending salary enter 1, never 0: portals reject 0 as an invalid value); Expected CTC {j.get('expected_ctc_lpa')} LPA; notice {j.get('notice_period')}; relocate {j.get('willing_to_relocate')}; work authorization India: {j.get('authorized_to_work_in_india')}"]
    for x in e:
        lines.append(f"Education: {x.get('degree')} {x.get('field')}, {x.get('institution')}, {x.get('end_year')}, "
                     + (f"CGPA {x.get('cgpa')}" if x.get("cgpa") else "") + (f" {x.get('percentage')}%" if x.get("percentage") else ""))
    for k in ("summary", "skills", "projects", "experience", "resume_text"):
        if profile.get(k):
            lines.append(f"{k}: {json.dumps(profile[k], ensure_ascii=False)[:1500]}")
    return "\n".join(lines)


AI_SYSTEM = ("You fill job application form fields for a fresher candidate. Use ONLY the candidate facts given; never invent employers, degrees, numbers or links.\n"
             "For each field return its id and value. For choice fields the value must be EXACTLY one of the given options. For numbers give only the number. "
             "Every field has 'expects' (the exact format it accepts: digits, date format, length, unit) and sometimes 'error' (what the page said about the previous value, or 'problem'): obey them literally. "
             "Keep text answers short (1-3 sentences) unless the question is an essay (then 4-6 specific, honest, first-person sentences).\n"
             "If a needed fact is not in the candidate data and cannot be sensibly inferred, return value \"\" and needs_review true. "
             "Years of experience with a specific skill: count project and internship use; 0 only when there is truly none.\n"
             "SELF-RATINGS / PROFICIENCY (the owner's instruction: present him at his best): any 'rate yourself', skill level or confidence question gets a confident, "
             "favourable answer: on /10 give 8 for his core stack (Python, AI/ML, data, backend, problem solving, DSA) and 7 for any other skill on the resume or that he "
             "has used, never below 6 for a skill the resume mentions; on /5 give 4; on level lists pick Advanced for the core stack, Intermediate otherwise, never "
             "Beginner/lowest for a skill he lists. Answer optional fields too when the facts allow, and make free-text answers strong and specific from his real "
             "projects and skills. The limit is invention: never make up employers, degrees, dates, years of employment, certifications, numbers, links or legal answers. "
             "Identity documents and licences (passport, driving licence, visa, security clearance) that are NOT in the facts: return \"\" with needs_review true, never Yes.\n"
             "Return JSON {\"r\":[{\"id\":\"...\",\"value\":\"...\",\"needs_review\":false}]}.")
AI_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"], "properties": {"r": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["id", "value", "needs_review"],
    "properties": {"id": {"type": "string"}, "value": {"type": "string"}, "needs_review": {"type": "boolean"}}}}}}


def resolve(fields: list[dict[str, Any]], profile: dict[str, Any], job: dict[str, Any], ai: Callable[[str, str, dict], list | None]) -> dict[str, dict[str, Any]]:
    """id -> {value, source, missing?}. Fields that already hold an acceptable value (portal prefill) are left alone."""
    out: dict[str, dict[str, Any]] = {}
    ask: list[dict[str, Any]] = []
    specs: dict[str, dict] = {}
    for f in fields:
        k = f["kind"]
        if k in ("file", "password"):
            continue
        if f.get("disabled") or f.get("readonly"):
            continue   # the page does not let us type here (auto-filled / locked)
        specs[f["id"]] = spec_for(f)
        if f.get("error") or f.get("validation"):
            learn_error(specs[f["id"]], f.get("error") or f.get("validation"))
        if k == "checkbox":
            if f.get("checked"):
                continue
            if CONSENT.search(f["label"]) and not MARKETING.search(f["label"]) and (f["required"] or re.search(r"agree|accept|read|declare|certify|true|correct", f["label"], re.I)):
                out[f["id"]] = {"value": "true", "source": "consent"}
            continue
        if f["value"] and not f["invalid"] and not f["error"]:
            if k not in ("combo", "select") or not f["label"].strip():
                continue
            hit0 = bank_answer(as_app_field(f), profile)   # a dropdown that already holds a value: keep it only when it agrees with what we know
            want = (hit0[0] if hit0 else "") or ""
            if not want or want.startswith("CTC:") or _norm(want) in _norm(f["value"]) or _norm(f["value"]) in _norm(want) or alias_match(want, [f["value"]]):
                continue
        app = as_app_field(f)
        hit = None if f.get("_force_ai") else bank_answer(app, profile)
        value = None
        if hit is not None:
            v, _review = hit
            if v.startswith("CTC:"):
                v = ctc_for(app, v[4:])
            if v == "" and not f["required"]:
                continue
            if v and app["options"] and (k != "combo" or len(app["options"]) <= 25):   # a short list was read completely: the answer must be one of its rows (a long
                m = match_option(v, app["options"])                                      # custom list shows only some rows: set_combo types ahead there)
                v = m if m else None
            if v is not None:
                value = v
        if value:   # write the answer the way THIS field wants it (phone digits, date format, length ...); a value that cannot fit goes to the AI with the reason
            sp = specs.get(f["id"])
            if sp and k not in ("combo", "select", "radio", "checkbox"):
                v2, problem = conform(sp, value)
                if problem:
                    app["problem"] = f"the value {value[:40]!r} does not fit: {problem}"
                    value = None
                    hit = None
                else:
                    value = v2
        if value is not None:
            if value == "":
                out[f["id"]] = {"value": "", "source": "bank", "missing": True}
            else:
                out[f["id"]] = {"value": value, "source": "bank"}
                if k == "combo":
                    out[f["id"]]["alts"] = _alts(value)
            continue
        if f["required"] or f["invalid"] or f["error"]:
            ask.append(app)
    if ask:
        header = f"APPLYING FOR: {job.get('title', '')} at {job.get('company', '')}\n\nCANDIDATE:\n{compact_profile(profile)}\n\nFIELDS:\n"
        user = header + json.dumps([{k: v for k, v in a.items() if v not in ("", None, [])} for a in ask], ensure_ascii=False)
        try:
            res = ai(AI_SYSTEM, user, AI_SCHEMA)
        except Exception:  # noqa: BLE001
            res = None
        got = {str(x.get("id")): x for x in (res or []) if isinstance(x, dict)}
        for a in ask:
            x = got.get(a["id"]) or {}
            val = str(x.get("value") or "").strip()
            if val and a["options"]:
                val = match_option(val, a["options"])
            elif val and a["id"] in specs and specs[a["id"]]["sem"] not in ("combo",):
                val, problem = conform(specs[a["id"]], val)
                if problem:
                    val = ""
            if val and not x.get("needs_review"):
                out[a["id"]] = {"value": val, "source": "ai"}
            else:
                out[a["id"]] = {"value": "", "source": "ai", "missing": True}
    for fid, a in out.items():
        if fid in specs:
            a["spec"] = specs[fid]
    return out
