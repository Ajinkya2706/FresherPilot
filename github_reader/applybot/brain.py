"""The decision layer: memory of what happened + an AI that decides the next step from (goal, facts, history, current page).

Rules (engine.py handlers) stay the FAST PATH for pages we know. The brain takes over when a page is unfamiliar, when the same
state repeats, when an error shows, or when no safe button is known: it is shown
  * the goal and the candidate facts (never to be invented),
  * the FACTS we learned about this portal (account exists, user name, signed in, pages done, attempts used...),
  * the last steps with what each one did (page before -> action -> page after / error),
  * the current page (fields with labels / values / options, buttons, errors, text).
It answers with ONE action; `validate` refuses anything unsafe or impossible before it is executed.

Memory is saved per job (users/<id>/site_memory/<uid>.json) so a later run / resume knows what already happened, and the
per-portal ATTEMPT LEDGER (sign-ins, reset e-mails, code e-mails per day) is shared by all runs: a portal is never hammered."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

MEM_DIR: Path | None = None            # set by scripts/apply_site.py (users/<id>/site_memory)
LEDGER_CAPS = {"signin": 2, "reset": 1, "code_mail": 6}   # per portal per rolling 24 h
ACTIONS = ["fill", "click", "wait", "get_code", "ask_owner", "done", "give_up"]

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"], "properties": {"r": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["action", "button", "fields", "reason"],
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "button": {"type": "string"},
        "fields": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "value"],
                                              "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}},
        "reason": {"type": "string"}}}}}}

SYSTEM = (
    "You drive a browser to complete ONE job application for a fresher candidate, like a careful human would. You are shown the goal, the "
    "candidate's facts, what has happened so far on this portal (facts + recent steps with their outcomes) and the CURRENT page. Choose the ONE "
    "next action.\n"
    "Actions: fill (set the listed fields, then the page stays; give label + value per field), click (press the named button), wait (page loading), "
    "get_code (an e-mailed code / access code is needed: the system reads it from Gmail), ask_owner (a required fact is not in the candidate facts), "
    "done (the application is submitted / confirmed), give_up (cannot proceed safely).\n"
    "The candidate facts contain a WORK HISTORY (key 'experience': most recent first) and the current CTC: use them for Employer / Job title / dates / "
    "salary fields on work-experience pages; ask_owner is only for a fact that is really absent from ALL the facts. When errors say a field is "
    "required, fill it from the facts and press Save/Continue.\n"
    "Rules: use ONLY the candidate facts; NEVER invent employers, numbers, dates, links or yes/no legal answers; a required field whose fact is "
    "missing => ask_owner. Look at the HISTORY: never repeat an action that did not change the page; if the last step produced an error, fix the "
    "cause (read the error text) instead of pressing the same button. Do not sign in / request a reset again if FACTS say the attempt budget is used "
    "or you are already signed in. Prefer Save/Next/Continue over Save as Draft. Press the final Submit only when every required field is filled and "
    "the page is the last review/submit step. Never click Cancel, Back, Delete, Withdraw, social sign-ins, or ads. 'button' must be the visible text of "
    "a listed button exactly; use '' when not clicking.\n"
    "CHECKBOXES: to tick one, give its own label as the field label and value 'true' (one entry per box to tick); tick only what the facts support.")


# ------------------------------------------------------------------ memory
def _path(uid: str) -> Path | None:
    if MEM_DIR is None:
        return None
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    return MEM_DIR / (re.sub(r"[^A-Za-z0-9._-]+", "_", uid or "job") + ".json")


def load(uid: str) -> dict[str, Any]:
    p = _path(uid)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {"facts": {}, "history": []}
    except (OSError, ValueError):
        return {"facts": {}, "history": []}


def save(uid: str, mem: dict[str, Any]) -> None:
    p = _path(uid)
    if p:
        try:
            mem["history"] = mem["history"][-60:]
            p.write_text(json.dumps(mem, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def _ledger_path() -> Path | None:
    return (MEM_DIR.parent / "site_ledger.json") if MEM_DIR is not None else None


def ledger_count(host: str, kind: str) -> int:
    p = _ledger_path()
    try:
        rows = json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {}
    except (OSError, ValueError):
        rows = {}
    now = time.time()
    return sum(1 for t in rows.get(f"{host}|{kind}", []) if now - t < 86400)


def ledger_add(host: str, kind: str) -> None:
    p = _ledger_path()
    if not p:
        return
    try:
        rows = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        rows = {}
    now = time.time()
    rows[f"{host}|{kind}"] = [t for t in rows.get(f"{host}|{kind}", []) if now - t < 86400] + [now]
    try:
        p.write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        pass


def budget_left(host: str, kind: str) -> bool:
    """True while the portal may still be asked for this (sign-in / reset mail / code mail) today."""
    return ledger_count(host, kind) < LEDGER_CAPS.get(kind, 3)


# ------------------------------------------------------------------ the decision
def page_view(snap: dict) -> str:
    fields = []
    for f in snap.get("fields", [])[:40]:
        opts = f" options={f['options'][:8]}" if f.get("options") else ""
        fields.append(f"- [{f['kind']}] '{f['label'][:70]}' {'REQUIRED ' if f.get('required') else ''}value={'(set)' if f.get('value') else '(empty)'}{' INVALID' if f.get('invalid') else ''}{opts}")
    buttons = [f"'{b['text'][:40]}'{' (disabled)' if b.get('disabled') else ''}" for b in snap.get("buttons", [])[:25]]
    return (f"URL: {snap.get('url', '')[:140]}\nTITLE: {snap.get('title', '')[:80]}\nHEADINGS: {snap.get('headings', [])[:4]}\n"
            f"ERRORS: {snap.get('errors', [])[:4]}\nFIELDS:\n" + ("\n".join(fields) or "(none)") + f"\nBUTTONS: {', '.join(buttons) or '(none)'}\n"
            f"TEXT: {re.sub(chr(92) + 's+', ' ', snap.get('text', ''))[:700]}")


def decide(ai, job: dict, profile_text: str, mem: dict[str, Any], snap: dict) -> dict[str, Any] | None:
    hist = "\n".join(f"{i + 1}. {h.get('page', '')[:60]} | did: {h.get('action', '')[:90]} | then: {h.get('result', '')[:100]}" for i, h in enumerate(mem["history"][-8:]))
    user = (f"GOAL: apply to '{job.get('title', '')}' at '{job.get('company', '')}'.\n\nCANDIDATE FACTS:\n{profile_text}\n\n"
            f"FACTS ABOUT THIS PORTAL: {json.dumps(mem['facts'], ensure_ascii=False)[:900]}\n\nHISTORY (oldest first):\n{hist or '(none yet)'}\n\n"
            f"CURRENT PAGE:\n{page_view(snap)}")
    try:
        res = ai(SYSTEM, user, SCHEMA)
    except Exception:  # noqa: BLE001
        return None
    item = res[0] if isinstance(res, list) and res else None
    return item if isinstance(item, dict) else None


def validate(act: dict[str, Any], snap: dict, mem: dict[str, Any]) -> tuple[bool, str]:
    """Refuse an action that is impossible, unsafe or a repeat of one that did nothing."""
    a = act.get("action")
    if a not in ACTIONS:
        return False, "unknown action"
    if a == "click":
        names = [b["text"].strip().lower() for b in snap.get("buttons", []) if not b.get("disabled")]
        want = (act.get("button") or "").strip().lower()
        if want not in names:
            return False, f"button '{want}' is not on the page"
        if re.search(r"cancel|back|delete|withdraw|discard|google|facebook|linkedin|apple|remove", want):
            return False, f"'{want}' is not allowed"
        recent = [h for h in mem["history"][-4:] if h.get("action") == f"click {want}" and h.get("result", "").startswith("same page")]
        if len(recent) >= 2:
            return False, f"'{want}' was pressed twice and the page did not change"
    if a == "fill" and not act.get("fields"):
        return False, "no fields"
    return True, ""


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def match_field(fields: list[dict], label: str, taken: set[str] | None = None) -> dict | None:
    """The page field an AI label points to: exact, then either contains the other, then the best word overlap (>= 0.6).
    Checkbox / radio labels are often quoted with their question in front ("Generative AI technologies: LangChain")."""
    want = _norm(label)
    if not want:
        return None
    taken = taken or set()
    cands = [f for f in fields if f.get("id") not in taken and f.get("label")]
    for f in cands:
        if _norm(f["label"]) == want:
            return f
    for f in cands:
        n = _norm(f["label"])
        if n and (want in n or n in want) and min(len(n), len(want)) >= 4:
            return f
    best, score = None, 0.0
    ws = set(want.split())
    for f in cands:
        fs = set(_norm(f["label"]).split())
        if not fs or not ws:
            continue
        r = len(ws & fs) / max(len(ws), len(fs))
        if r > score:
            best, score = f, r
    return best if score >= 0.6 else None
