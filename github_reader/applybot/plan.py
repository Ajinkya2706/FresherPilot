"""AI-driven page handling: ONE call per page returns a batch PLAN, executed by element id.

The AI sees: the goal, ALL candidate facts (every education / work entry, skills, resume), the portal memory (facts + its own running
notes), the recent history (what was done and what each step led to) and the current page with an id for every field and button.
It answers with a list of actions on those ids, e.g. set f3 "...", set f4 "...", tick f7, click b2. The engine executes them in
order, stops at the first click (the page changes), re-observes, and asks again. Hard checks stay OUTSIDE the AI (`check_plan`):
known ids only, no Cancel/Back/Delete, never a final Submit while a required field is empty, skills ticked only if the resume says so.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import brain

ACTS = ["set", "tick", "click", "upload", "code", "link", "wait", "ask", "done", "stop"]

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"], "properties": {"r": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["note", "actions"],
    "properties": {
        "note": {"type": "string"},
        "actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["do", "id", "value", "why"],
            "properties": {"do": {"type": "string", "enum": ACTS}, "id": {"type": "string"}, "value": {"type": "string"}, "why": {"type": "string"}}}}}}}}}

_CORE = (
    "You operate a browser to complete ONE job application for the candidate, as a careful, efficient human would. Each turn you get the GOAL, the "
    "candidate's FACTS, the PORTAL MEMORY, the HISTORY (what you did before and what each step led to) and the CURRENT PAGE (every field and button has an id).\n"
    "Return a PLAN: a short list of actions on those ids, executed in order. Actions: set (id of a text/select/radio/date field; value = what to enter; "
    "for a choice copy the option text), tick (checkbox id; value 'true' or 'false'), click (button/link id; the plan stops after a click because the page "
    "changes), upload (file id: the resume), code (the page wants an e-mailed code: the system reads it from Gmail, no id), link (an e-mailed "
    "verification link is needed), wait (page loading), ask (a required fact is NOT in the facts: value = what is missing), done (the application is "
    "submitted / confirmed), stop (cannot proceed safely).\n"
    "Also return 'note': one line for your future self (what is done / what is next).\n"
    "How to work:\n"
    "- Fill EVERY empty required field and every optional field the facts answer, in ONE plan, and END THE SAME PLAN with the click that moves on (never set the "
    "same field id twice in one plan; Save and Continue / Next / Continue; prefer them over 'Save as Draft'). Do not re-set fields that already hold the right value.\n"
    "- Read the page ERRORS and the HISTORY: fix the cause of an error instead of repeating the same click; never repeat an action that did not change the page.\n"
    "- Facts only: NEVER invent employers, degrees, dates, years of employment, certifications, numbers, links or legal yes/no answers. A missing fact => ask. "
    "Identity documents and licences (passport, driving licence, visa, clearance) not in the facts: leave an optional one empty; for a required one use 'ask'. "
    "Gender/diversity: the facts' diversity answers.\n"
    "- Apply ONLY to the job named in the GOAL. If the page shows a different job (another title), do NOT apply to it and do NOT pick one from 'all jobs' "
    "lists: go back to the goal job's own page, or stop with the reason.\n"
    "- Location / notification / cookie prompts on the page: allow location (or 'Not now' if there is no Allow), accept essential cookies, and carry on.\n"
    "- Click the final Submit only on the last review/submit page and only when no required field is empty. After a submit, read the page: 'done' only if "
    "it confirms the application was received; otherwise fix what it complains about.\n"
    "- Never click Cancel, Back, Delete, Withdraw, social sign-ins, ads. Sign-in / account creation are handled by the system, not by you.")

# Blocks added only when the page needs them (each one costs ~100-250 tokens on EVERY call otherwise).
_BLOCKS = {
    "repeat": (
        "- REPEATABLE SECTIONS (education, work experience, projects, languages...): the candidate has N entries of each (see facts). Enter ALL of them, "
        "most recent first. Entry k goes into block k: fill ONLY the blocks that exist on the page NOW (one entry per block, in order); if fewer blocks than "
        "entries and an 'Add ...' button exists, END the plan with the Add click (the new empty block appears next turn). Never put two entries into one block "
        "or enter an entry twice. Before leaving the page every block must hold an entry. Use your note to track the count.\n"),
    "ratings": (
        "- SELF-RATINGS / PROFICIENCY (the owner's instruction: present him at his best, this is a job application): any 'rate yourself', skill level, "
        "proficiency or confidence question gets a confident, favourable answer: on /10 give 8 for his core stack (Python, AI/ML, data, backend, problem solving, "
        "DSA) and 7 for any other skill on the resume; never below 6 for a skill the resume mentions; on /5 give 4; on level lists pick Advanced for the core "
        "stack, Intermediate/Proficient otherwise, never Beginner/lowest for a skill he lists. Count project and internship use as experience with a skill. "
        "Fill every optional field the facts can answer (links, summary, why-us, strengths, notice period, expected salary) and write free-text answers strong "
        "and specific from his real projects, internships and skills. Skills the resume does not mention stay honest.\n"),
    "dates": (
        "- DATES: month/year dropdowns are separate fields (their label says which date). A work entry whose end month equals its start month (the Intern "
        "entry, 07/2026 to 07/2026) is entered as it is; if the page rejects it (end must be after start, same month not accepted, error on the end date), "
        "use that entry's end_month_alt / end_year_alt (August 2026) and carry on. Do not retry the rejected value.\n"),
    "skills": "- Technology/skill checkboxes: tick only those the resume text mentions. 'None of the above' only if nothing applies.\n",
}
SYSTEM = _CORE + "\n" + "".join(_BLOCKS.values())   # the full text (tests / tools); calls use build_system(snap)


def _page_blob(snap: dict) -> str:
    labels = " ".join(f"{f.get('label', '')}" for f in snap.get("fields", []))
    btns = " ".join(b.get("text", "") for b in snap.get("buttons", []))
    return f"{labels} {btns} {' '.join(snap.get('headings', []) or [])}".lower()


def build_system(snap: dict) -> str:
    """The core prompt plus only the blocks this page needs."""
    blob = _page_blob(snap)
    fields = snap.get("fields", [])
    use = []
    if re.search(r"\badd (another |more )?(education|experience|employment|work|project|language|school|job|position|qualification)|\badd\b", " ".join(b.get("text", "") for b in snap.get("buttons", [])).lower()) \
            or re.search(r"education|school|university|degree|employer|job title|work experience|employment history|company name|project", blob):
        use.append("repeat")
    if any(f.get("kind") == "textarea" for f in fields) or re.search(r"\brate\b|\bscale\b|proficien|skill level|confiden|rating|out of|/10|/5|\bwhy\b|describe|tell us|cover|strength|summary|about (you|yourself)|years of experience|how many years|experience (with|in)", blob):
        use.append("ratings")
    if any(re.search(r"^\s*(from|to)\b|\bdate\b|\bmonth\b|\byear\b|\bstart\b|\bend\b|\bperiod\b|\bduration\b", str(f.get("label", "")).lower()) for f in fields):
        use.append("dates")
    if sum(1 for f in fields if f.get("kind") == "checkbox") >= 4:
        use.append("skills")
    return _CORE + ("\n" + "".join(_BLOCKS[k] for k in use) if use else "")


def needs_resume(snap: dict) -> bool:
    """The resume text (~900 tokens) is only needed for essays, skill boxes and skill / experience questions."""
    fields = snap.get("fields", [])
    if any(f.get("kind") == "textarea" for f in fields) or sum(1 for f in fields if f.get("kind") == "checkbox") >= 4:
        return True
    return bool(re.search(r"skill|technolog|\btools?\b|framework|programming|project|summary|about (you|yourself)|\bwhy\b|describe|cover|strength|achievement|experience (with|in)|years of|\brate\b|proficien", _page_blob(snap)))


def _clean(obj: Any) -> Any:
    """Drop empty values, duplicates of the same date (start + start_month + start_year...) and bookkeeping keys, so the facts stay short."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("start_month", "start_year", "end_month", "end_year", "start_derived", "current") and ("start" in obj or "end" in obj) and k != "current":
                continue
            v = _clean(v)
            if v in ("", None, [], {}, False):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        return [x for x in (_clean(i) for i in obj) if x not in ("", None, [], {})]
    return obj


def _j(obj: Any) -> str:
    return json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":"))


def facts_text(profile: dict[str, Any], limit_resume: int = 3500) -> str:
    p, j = profile.get("personal", {}), profile.get("job_preferences", {})
    edu, exp = profile.get("education") or [], profile.get("experience") or []
    j = dict(j)
    for k in ("current_ctc_lpa", "current_fixed_salary", "current_salary"):   # portals reject 0 ("must be greater than 0"): the owner's rule is to enter 1
        if k in j and str(j[k]).strip() in ("", "0", "0.0", "none", "None", "nil", "NA", "N/A"):
            j[k] = "1"
    lines = [f"Name: {p.get('full_name')} ({p.get('first_name')} {p.get('last_name')}); email {p.get('email')}; phone {p.get('phone_country_code')} {p.get('phone')}; "
             f"address: {p.get('address')}, {p.get('city')}, {p.get('state')}, {p.get('country')} {p.get('pincode')}; DOB {p.get('date_of_birth')}; gender {p.get('gender')}; nationality {p.get('nationality')}",
             f"Links: {_j(profile.get('links') or {})}",
             f"Preferences: {_j(j)}",
             "SALARY RULE: the candidate is a fresher with no salary, but portals refuse 0. For ANY current / last / ending / fixed / variable salary field enter 1 (never 0, never blank); expected salary comes from Preferences.",
             f"Diversity / EEO answers: {_j(profile.get('diversity') or {})}",
             f"Saved answers: {_j(profile.get('custom_answers') or {})}",
             f"EDUCATION ({len(edu)} entries, most recent first): {_j(edu)}",
             f"WORK EXPERIENCE ({len(exp)} entries, most recent first): {_j(exp)}"]
    if limit_resume:
        lines.append(f"RESUME TEXT:\n{(profile.get('resume_text') or '')[:limit_resume]}")
    return "\n".join(lines)


def page_view(snap: dict) -> str:
    out = [f"URL: {snap.get('url', '')[:150]}", f"TITLE: {snap.get('title', '')[:80]}", f"HEADINGS: {snap.get('headings', [])[:5]}"]
    if snap.get("errors"):
        out.append(f"ERRORS: {[e[:160] for e in snap['errors'][:5]]}")
    out.append("FIELDS (id [kind] label | value | options):")
    for f in snap.get("fields", [])[:80]:
        val = (f.get("value") or "")
        val = "✓" if f.get("checked") else (val[:40] if val else "")
        opts = f" | options: {[o[:70] for o in f['options'][:25]]}" if f.get("options") else ""
        flags = ("REQUIRED " if f.get("required") else "") + ("INVALID " if f.get("invalid") or f.get("error") else "")
        out.append(f"  {f['id']} [{f['kind']}] {flags}'{f['label'][:90]}' | value: {val!r}{opts}")
    out.append("BUTTONS / LINKS (id 'text'):")
    out += [f"  {b['id']} '{b['text'][:50]}'{' (disabled)' if b.get('disabled') else ''}" for b in snap.get("buttons", [])[:40]]
    out.append("PAGE TEXT: " + re.sub(r"\s+", " ", snap.get("text", ""))[:900])
    return "\n".join(out)


def history_text(mem: dict[str, Any], n: int = 8) -> str:
    rows = [f"{i + 1}. [{h.get('page', '')[:50]}] {h.get('action', '')[:140]} => {h.get('result', '')[:150]}" for i, h in enumerate(mem["history"][-n:])]
    return "\n".join(rows) or "(nothing yet)"


def ask_ai(ai, job: dict, profile: dict, mem: dict[str, Any], snap: dict) -> dict | None:
    user = (f"GOAL: apply to '{job.get('title', '')}' at '{job.get('company', '')}'.\n\nCANDIDATE FACTS:\n{facts_text(profile, 3500 if needs_resume(snap) else 0)}\n\n"
            f"PORTAL MEMORY: facts={json.dumps(mem['facts'], ensure_ascii=False)[:700]}; your notes: {mem.get('notes', '(none)')}\n\n"
            f"FILES: the candidate's resume (PDF) IS available. To attach it use do=upload with the id of the resume/CV file field (any 'Attach resume / Upload CV' control). "
            f"Never ask for the resume or say you are waiting for it.\n"
            f"DEFAULTS (never use ask for these): 'current company / employer' = his most recent employer in the facts, else 'Fresher'; 'current title' = his most recent "
            f"role, else 'Fresher'; 'LinkedIn/portfolio' left empty if not in the facts and optional; 'how did you hear' = 'Company website' / 'Job board'; "
            f"a required free-text with no fact = a short honest line from his real projects. EXPERIENCE fields: a NUMBER of years/months with a tool or in a role he has "
            f"not worked in professionally = 0 (if the page rejects 0, type 1); a text box asking for his experience = 'Fresher, no full-time experience yet; hands-on with "
            f"<that skill> through projects and internships, eager to learn on the job'; never leave a required experience field empty and never ask the owner. SALARY / CTC / "
            f"notice numbers: current CTC 0, expected as in the facts; if the page refuses 0 use 1. When the page shows an error on a field after your answer, change the "
            f"value in the direction the error asks (end date equal to start date -> end = one month later; value too low -> next higher) instead of repeating it. Use ask ONLY for a one-time secret/code or a fact that cannot be guessed (e.g. a government ID).\n\n"
            f"HISTORY:\n{history_text(mem)}\n\nCURRENT PAGE:\n{page_view(snap)}")
    try:
        res = ai(build_system(snap), user, SCHEMA)
    except Exception:  # noqa: BLE001
        return None
    item = res[0] if isinstance(res, list) and res else None
    return item if isinstance(item, dict) and isinstance(item.get("actions"), list) else None


FINAL_BTN = re.compile(r"^(submit( (my )?application)?|send application|finish|complete application|confirm and submit|apply)$", re.I)
BLOCKED = re.compile(r"cancel|back|delete|withdraw|discard|remove|google|facebook|linkedin|apple|sign ?out|log ?out", re.I)


MOVE_BTN = re.compile(r"^(save and continue|save & continue|continue|next|next step|save and next|proceed|review|submit( (my )?application)?|send application|finish)$", re.I)


def check_plan(plan: dict, snap: dict, supported, feedback: list | None = None) -> list[dict]:
    """Keep only the actions that are possible and safe; drop the rest (reasons are logged by the caller)."""
    fields = {f["id"]: f for f in snap.get("fields", [])}
    buttons = {b["id"]: b for b in snap.get("buttons", [])}
    required_empty = [f for f in snap.get("fields", []) if f.get("required") and not f.get("value") and not f.get("checked") and f["kind"] not in ("file",)]
    out: list[dict] = []
    seen_set: set[str] = set()
    for a in plan["actions"]:
        do, i = a.get("do"), a.get("id", "")
        if do in ("set", "tick") and i in seen_set:   # two entries written into one block: keep the first value only
            out.append({**a, "do": "_dropped", "_drop": "the same field twice in one plan (first value kept)"})
            continue
        if do in ("set", "tick"):
            seen_set.add(i)
        if do in ("set", "tick", "upload"):
            f = fields.get(i)
            if not f or (do == "set" and not str(a.get("value", "")).strip()):
                a["_drop"] = "unknown field or empty value"
            elif do == "tick" and str(a.get("value", "")).lower() in ("true", "yes", "1", "checked") and not supported(f["label"]):
                a["_drop"] = "the resume does not support ticking this"
            elif do == "upload" and f["kind"] != "file":
                a["_drop"] = "not a file field"
        elif do == "click":
            b = buttons.get(i)
            if not b or b.get("disabled"):
                a["_drop"] = "unknown or disabled button"
            elif BLOCKED.search(b["text"]):
                a["_drop"] = f"'{b['text']}' is not allowed"
            elif MOVE_BTN.match(b["text"].strip()) and required_empty:
                filled_now = {x["id"] for x in out if x.get("do") in ("set", "tick", "upload")}
                left = [f for f in required_empty if f["id"] not in filled_now]
                if left:
                    a["_drop"] = "required fields still empty: " + ", ".join(f["label"][:30] for f in left[:5])
                    if feedback is not None:
                        feedback.append(a["_drop"])
        if not a.get("_drop"):
            out.append(a)
        else:
            out.append({**a, "do": "_dropped"})
    return out
