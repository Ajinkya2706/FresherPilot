"""Account recovery for portals where our email already has an account but we do not know its credentials (Taleo / UHG, Nov 18):
  1. "Forgot your user name?"  -> enter the email -> the portal mails the username -> read it from Gmail
  2. "Forgot your password?"   -> enter username + email -> the portal mails a reset link -> open it
  3. set the new password (the one in .env: GOOGLE_PASSWORD, else the per-portal derived one) -> sign in with it.
Owner-approved action ("do forgot username, then forgot password and use the password in my env"). Nothing typed is logged."""
from __future__ import annotations

import re
import time

from . import actions as act
from . import brain, cloud, mail
from .snap import locate, snapshot

LINK_USER = re.compile(r"forgot(ten)? (your )?(user ?name|login|username)", re.I)
LINK_PASS = re.compile(r"forgot(ten)? (your )?(password|pass ?word)", re.I)
SUBMIT = re.compile(r"^(validate|ok|submit|send|continue|next|reset( password)?|save( (changes|password))?|confirm|change( my)? password|update( password)?|set( new)? password|finish|done|apply|create password|activate)$", re.I)
NOT_SUBMIT = re.compile(r"cancel|back|privacy|e-?verify|poster|google|sign ?in|new user|guest|home|dashboard", re.I)


def _submit_button(snap: dict):
    """The submit-like button: a known wording first, else the only enabled button that is not cancel / back / footer."""
    btn = next((b for b in snap["buttons"] if SUBMIT.match(b["text"].strip()) and not b["disabled"]), None)
    if btn:
        return btn
    rest = [b for b in snap["buttons"] if not b["disabled"] and not NOT_SUBMIT.search(b["text"])]
    return rest[0] if len(rest) == 1 else None
USER_IN_MAIL = re.compile(r"(?:user ?name|login (?:id|name))\s*(?:is|:|-|=)?\s*[:\-=]?\s*([A-Za-z0-9][A-Za-z0-9._@+-]{2,60})", re.I)
ACCESS_CODE = re.compile(r"(?:access code|temporary password|one[- ]time password)\s*(?:is\s*)?[:=]\s*([^\s<>]{4,40})", re.I)
NOT_A_NAME = {"is", "and", "for", "the", "your", "to", "has", "was", "will", "can", "you", "that", "this", "with", "request", "reminder", "recovery"}


def _find_link(snap: dict, rx: re.Pattern):
    return next((b for b in snap["buttons"] if rx.search(b["text"])), None) or None


def _click_text(page, rx: re.Pattern) -> bool:
    try:
        loc = page.get_by_text(rx).first
        if loc.is_visible(timeout=2000):
            act.click(page, loc)
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        loc = page.get_by_role("link", name=rx).first
        act.click(page, loc)
        return True
    except Exception:  # noqa: BLE001
        return False


def _fill_and_submit(run, fields_by: dict[str, str]) -> bool:
    """Fill the visible text fields by label word (user name / email), press the submit-like button."""
    run.settle(600)
    snap = snapshot(run.page)
    for f in snap["fields"]:
        label = f"{f['label']} {f['name']}".lower()
        if f["kind"] in ("password",):
            continue
        for key, val in fields_by.items():
            if key in label and val and not f["value"]:
                act.set_text(run.page, locate(snap, f["id"]), val)
                break
    btn = next((b for b in snap["buttons"] if SUBMIT.match(b["text"].strip()) and not b["disabled"]), None)
    if not btn:
        return False
    act.click(run.page, locate(snap, btn["id"]))
    return True


def recover(run, host: str, since: float) -> tuple[str, str] | None:
    """Returns None when new credentials are in place (run.usernames[host], run.pw_override[host]) and the sign-in page is open again,
    or (status, detail) when it cannot be done."""
    brands = [run.job.get("company", "")]
    email = run.email
    login_url = run.page.url
    # 1) the user name
    username = getattr(run, "usernames", {}).get(host, "")
    if not username:
        run.log("account recovery: asking the portal for the user name")
        if not _click_text(run.page, LINK_USER):
            return "needs_you", f"{host}: an account exists but there is no 'forgot user name' link; sign in or reset it by hand"
        t0 = time.time() - 30
        if not _fill_and_submit(run, {"email": email}):
            return "needs_you", f"{host}: couldn't submit the 'forgot user name' form"
        got = mail.wait_mail(host, t0, brands, minutes=2, pattern=r"user ?name\s*(is|:|=)|(forgot|forgotten|reminder|recover)\w*.{0,40}user ?name")
        if got and not re.search(r"locked|suspend|disabled", got[0], re.I):
            m = USER_IN_MAIL.search(got[1])
            username = (m.group(1).strip(".,;:") if m and m.group(1).lower() not in NOT_A_NAME else "")
        if username:
            run.log("account recovery: got the user name from the mail")
        else:
            # no user-name mail (Taleo sends none for some accounts): many portals use the email itself as the user name,
            # and "this user name cannot be used to create a candidate" said exactly that
            username = email
            run.log("account recovery: no user-name mail, trying the email as the user name")
        run.usernames = {**getattr(run, "usernames", {}), host: username}
        run.page.goto(login_url, wait_until="domcontentloaded", timeout=40000)
        run.settle(800)
    # 2) the password reset link. A reset mail from the last 20 minutes is REUSED (every request mails the owner and the newest
    #    code replaces the older ones: Nov 18, five reset mails in a row from repeated runs).
    RESET_PAT = r"https?://\S*(reset|password|passwd|forgot|access)\S*"
    got = mail.wait_mail(host, time.time() - 1200, brands, minutes=0.05, pattern=RESET_PAT)
    if got:
        run.log("account recovery: a recent reset email is already in Gmail, using it (no new request)")
    else:
        if not brain.budget_left(host, "reset"):
            return "needs_you", f"{host}: a password-reset e-mail was already requested today and no usable one is in Gmail: not requesting another (every request replaces the code and mails you)"
        brain.ledger_add(host, "reset")
        run.log("account recovery: asking the portal to reset the password")
        snap = snapshot(run.page)
        if not any(LINK_PASS.search(b["text"]) for b in snap["buttons"]) and not _click_text(run.page, LINK_PASS):
            return "needs_you", f"{host}: no 'forgot password' link found"
        _click_text(run.page, LINK_PASS) if "password" not in run.page.url.lower() else None
        run.settle(800)
        t1 = time.time() - 30
        if not _fill_and_submit(run, {"user name": username, "username": username, "email": email}):
            return "needs_you", f"{host}: couldn't submit the 'forgot password' form"
        got = mail.wait_mail(host, t1, brands, minutes=6, pattern=RESET_PAT)
    link = ""
    if got:
        urls = [u.rstrip(".,;)") for u in re.findall(r"https?://[^\s\"'<>)]+", got[1]) if re.search(r"reset|password|passwd|forgot|access", u, re.I) and not mail.BAD_LINK.search(u)]
        link = urls[0] if urls else ""
    if not link:
        req = cloud.otp_request(0, "link", f"{host}: open the password-reset email and send me its link", host)
        link = cloud.otp_wait(req, 0, 8) or ""
    if not link.startswith("http"):
        return "needs_you", f"{host}: the password-reset email didn't arrive (or no link in it)"
    # 3) the new password. Taleo's mail carries a temporary ACCESS CODE: sign in with user name + that code, then it asks for the
    #    code again plus the new password twice. Other portals open a "set new password" page straight from the link.
    run.log("account recovery: opening the reset link")
    access = ""
    if got:
        found = ACCESS_CODE.findall(got[1])   # "Password / Access Code : <code>": the LAST labelled value is the code
        access = found[-1].strip(".,;") if found else ""
    run.page.goto(link, wait_until="domcontentloaded", timeout=40000)
    run.settle(1000)
    pws = cloud.passwords_for(host)
    if access:
        snap = snapshot(run.page)
        for f in snap["fields"]:
            lab = f"{f['label']} {f['name']}".lower()
            if f["kind"] == "password":
                act.set_text(run.page, locate(snap, f["id"]), access)
            elif f["kind"] in ("text", "email") and not f["value"] and ("user" in lab or "mail" in lab):
                act.set_text(run.page, locate(snap, f["id"]), username)
        btn = next((b for b in snap["buttons"] if re.match(r"^(sign ?in|log ?in|login|continue|next|ok|submit)$", b["text"].strip(), re.I) and not b["disabled"]), None)
        if not btn:
            return "needs_you", f"{host}: the access-code sign-in page has no sign-in button I know"
        run.log("account recovery: signing in with the access code from the mail")
        act.click(run.page, locate(snap, btn["id"]))
        run.settle(1500)
    for idx, pw in enumerate(pws):   # the .env password first; if the portal rejects it (rules), the derived one
        snap = snapshot(run.page)
        pw_fields = [f for f in snap["fields"] if f["kind"] == "password"]
        if not pw_fields:
            break
        if access and len(pw_fields) >= 3:   # access code, new password, confirm
            values = [access, pw, pw] + [pw] * (len(pw_fields) - 3)
        else:
            values = [pw] * len(pw_fields)
        for f, val in zip(pw_fields, values):
            act.set_text(run.page, locate(snap, f["id"]), val)
        for f in snap["fields"]:   # a "user name / email" box on the same page
            lab = f"{f['label']} {f['name']}".lower()
            if f["kind"] in ("text", "email") and not f["value"] and ("user" in lab):
                act.set_text(run.page, locate(snap, f["id"]), username)
            elif f["kind"] in ("text", "email") and not f["value"] and "mail" in lab:
                act.set_text(run.page, locate(snap, f["id"]), email)
        btn = _submit_button(snap)
        if not btn:
            run.log("account recovery: new-password page buttons: " + ", ".join(b["text"][:24] for b in snap["buttons"][:10]) + " | fields: " + ", ".join(f"{f['kind']}:{f['label'][:20]}" for f in snap["fields"][:8]))
            return "needs_you", f"{host}: the new-password page has no submit button I know"
        act.click(run.page, locate(snap, btn["id"]))
        run.settle(1500)
        after = snapshot(run.page)
        if after["errors"] and idx + 1 < len(pws):
            run.log("account recovery: the portal refused that password, trying the other one")
            continue
        if after["errors"]:
            return "needs_you", f"{host}: the portal refused the new password"
        run.pw_override = {**getattr(run, "pw_override", {}), host: pw}
        run.log("account recovery: new password set")
        break
    else:
        return "needs_you", f"{host}: couldn't set a new password"
    run.page.goto(login_url, wait_until="domcontentloaded", timeout=40000)
    run.settle(800)
    return None
