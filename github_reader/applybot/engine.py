"""The apply loop: look (snapshot) -> classify -> act -> check progress. One job at a time.

Returns (status, detail): applied | needs_you | failed | closed | blocked | skipped.
Nothing personal is ever printed: logs carry page kinds, field LABELS and counts, never the values typed.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import actions as act
from . import brain, cloud, mail
from .answers import match_option, resolve
from .classify import APPLY_WORDS, CREATE_BTN, FINAL, NEXT, classify
from .snap import locate, snapshot, state_key
from .understand import wait_ready

AVOID = re.compile(r"^(accept( all)?( cookies)?|reject( all)?( cookies)?|cookie|manage (cookies|preferences)|modify cookie|cookies? (settings|preferences)|got it|i understand|allow (all|cookies)|back|previous|cancel|close|discard|save for later|sign ?out|log ?out|help|decline|reject|withdraw|skip|no thanks|not now|dismiss|clear|reset|edit|delete|remove|add another|add (a )?(work|education|experience|language|skill|website)|"
                   r"forgot|learn more|view|download|print|share|menu|search|filter|upload|apply with (linkedin|indeed|google|facebook|apple|seek)|sign in with|continue with (google|linkedin|facebook|apple)|google|linkedin|facebook|apple)\b", re.I)
SOCIAL = re.compile(r"(google|linkedin|facebook|apple|microsoft|github|indeed|seek)\b", re.I)
class Stuck(Exception):
    pass

# portals where the OWNER's own account is used (never create an account there): when logged out the runner asks once on Telegram and waits
PORTAL = re.compile(r"(^|\.)(linkedin\.com|naukri\.com|indeed\.com|internshala\.com|wellfound\.com|foundit\.in)$", re.I)


MAX_STEPS = 70
MAX_SECONDS = 15 * 60


_NOT_RESUME = re.compile(r"cover ?letter|transcript|portfolio|photo|picture|id proof|identity|certificate|marksheet|"
                         r"mark sheet|passport|signature|writing sample|sample|recommendation|reference|salary slip|payslip", re.I)


def file_slot_is_resume(f: dict) -> bool:
    """The resume goes into the resume slot only. An optional cover-letter / transcript / photo slot stays empty
    (Nov 18 dry run: Greenhouse's Cover Letter got the resume too); a REQUIRED unnamed or cover-letter slot still
    gets the resume as the best available file (better than a blocked form)."""
    name = f"{f.get('heading') or ''} {f.get('label') or ''} {f.get('name') or ''}"
    if re.search(r"resume|\bcv\b|curriculum", name, re.I):
        return True
    if _NOT_RESUME.search(name):
        return bool(f.get("required")) and bool(re.search(r"cover ?letter", name, re.I))
    return True  # unnamed slot ("Attach"): the resume


class Run:
    def __init__(self, ctx, job: dict, profile: dict, accounts: list[str], resume_path: str, dry: bool):
        self.ctx, self.job, self.profile, self.accounts = ctx, job, profile, set(accounts)
        self.resume, self.dry = resume_path, dry
        self.page = ctx.new_page()
        self.steps: list[str] = []
        self.created: set[str] = set()      # domains where an account was created in this run
        self.tried_signin: set[str] = set()
        self.clicked_create: set[str] = set()
        self.fill_rounds = 0
        self.clicks: dict[str, int] = {}
        self.t0 = time.time()
        self.email = profile["personal"]["email"]
        self.mem = brain.load(job.get("uid") or job.get("url", "job"))   # what already happened on this portal (survives restarts)
        self._act = ""          # the action just taken, described for the history
        self._prev = ("", "")   # (page description, state key) before that action
        self.ai_steps = 0

    # ------------------------------------------------------------------ helpers
    def log(self, msg: str) -> None:
        line = f"{int(time.time() - self.t0):>3}s {msg}"
        self.steps.append(line)
        print("   " + line, flush=True)

    def adopt_newest_page(self) -> None:
        pages = [p for p in self.ctx.pages if not p.is_closed()]
        if pages and pages[-1] != self.page:
            self.page = pages[-1]
            self.log("switched to the new tab")

    COOKIE_NO = re.compile(r"^(dismiss|reject( all)?( non-?essential)?( cookies)?|decline( all)?( cookies)?|deny( all)?|only (necessary|essential)( cookies)?|(necessary|essential) (cookies )?only|continue without accepting|refuse( all)?|no,? thanks)$", re.I)

    def dismiss_cookies(self) -> None:
        """Privacy-friendly choice on a cookie banner (reject / necessary only). A banner with only 'Accept' is left alone."""
        try:
            btn = self.page.get_by_role("button", name=self.COOKIE_NO).first
            if btn.is_visible(timeout=300):
                btn.click(timeout=2000)
                self.log("cookie banner: rejected non-essential")
                self.page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            pass

    def settle(self, ms: int = 450) -> None:
        self.adopt_newest_page()
        self.dismiss_cookies()
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        self.page.wait_for_timeout(ms)
        try:
            self.page.wait_for_load_state("networkidle", timeout=1000)   # SPAs (Workday) never go idle: do not pay 4 s per page
        except Exception:  # noqa: BLE001
            pass
        r = wait_ready(self.page, 10000)   # understand the page only after it stopped loading: spinners gone, no DOM change for 0.6 s
        self.busy = r.startswith("timeout")
        if self.busy:
            self.busy_since = getattr(self, "busy_since", 0) or time.time()
            self.log(f"page still busy ({r[8:]}), reading it anyway")
        else:
            self.busy_since = 0

    def ai(self, system: str, user: str, schema: dict):
        return cloud.ai(system, user, schema)

    # ------------------------------------------------------------------ main loop
    def run(self, resume: bool = False) -> tuple[str, str]:
        url = self.job["url"]
        err = ""
        for attempt in ((0, 1, 2) if not resume else ()):
            try:
                self.page.goto(url, wait_until="commit" if attempt else "domcontentloaded", timeout=45000)
                err = ""
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)[:80]
                self.log(f"open attempt {attempt + 1} failed: {err}")
                self.page.wait_for_timeout(3000)
        if err:
            return "failed", "Couldn't open the apply link"
        last, same = "", 0
        for step in range(MAX_STEPS):
            if time.time() - self.t0 > MAX_SECONDS:
                return "needs_you", "Took too long, finish it by hand"
            self.settle()
            if step % 4 == 0:
                cloud.alive(self.job["id"])
            snap = snapshot(self.page)
            kind = classify(snap)
            key = kind + "|" + state_key(snap)
            same = same + 1 if key == last else 0
            if same == 0:
                self.clicks.clear()   # the page changed: pressing "Save and Continue" on the NEXT page is not "going in circles"
            last = key
            if self._act:   # close the previous step in the history: what did that action lead to?
                moved = key != self._prev[1]
                res = (f"-> {kind}: {snap['title'][:40]}" if moved else "same page") + (" | errors: " + "; ".join(e[:80] for e in snap['errors'][:2]) if snap["errors"] else "")
                self.mem["history"].append({"page": self._prev[0], "action": self._act, "result": res})
                self._act = ""
            self._prev = (f"{kind} | {snap['title'][:40]}", key)
            self.mem["facts"]["last_page"] = f"{kind} @ {snap['host']}"
            brain.save(self.job.get("uid") or self.job.get("url", "job"), self.mem)
            # a page that is still showing its spinner (Workday's "My Information" took 55 s to draw, Nov 18) has not
            # "stayed the same": give it up to 150 s before the stuck rule applies
            if same and getattr(self, "busy", False) and time.time() - (getattr(self, "busy_since", 0) or time.time()) < 150:
                same = 0
            try:   # the newest page picture, so a stuck window can be looked at without the screen (Nov 18, Cisco)
                shot = os.environ.get("APPLYBOT_SHOT")
                if shot:
                    self.page.screenshot(path=shot, full_page=False, timeout=4000)
            except Exception:  # noqa: BLE001
                pass
            self.log(f"{kind} @ {snap['host']} fields={len(snap['fields'])} buttons={len(snap['buttons'])}" + (f" errors={len(snap['errors'])}" if snap["errors"] else "")
                     + " | b: " + ", ".join(x["text"][:22] + ("(off)" if x["disabled"] else "") for x in snap["buttons"][:9])
                     + (" | f: " + ", ".join(f"{x['kind']}:{x['label'][:24]}" for x in snap["fields"][:5]) if snap["fields"] else "")
                     + (" | ERR: " + " ; ".join(e[:90] for e in snap["errors"][:3]) if snap["errors"] else "")
                     + (" | EMPTY-REQ: " + ", ".join(x["label"][:28] for x in snap["fields"] if x["required"] and not x["value"] and x["kind"] not in ("file", "checkbox"))[:200]
                        if any(x["required"] and not x["value"] and x["kind"] not in ("file", "checkbox") for x in snap["fields"]) else ""))
            if same >= 2 or (snap["errors"] and same >= 1):   # the same state again: the AI looks at the history and decides
                r = self.ai_step(snap, kind)
                if r == "acted":
                    same = 0
                    continue
                if r:
                    return r
            if same >= 4:
                return "needs_you", f"Stuck on a {kind} page (nothing changed after 4 tries, the AI had no safe next step)"
            try:
                res = self.handle(kind, snap, same)
            except Stuck as e:
                return "needs_you", f"Stuck: {e}"
            if res:
                return self.verify(res)
        return "needs_you", "Too many steps, finish it by hand"

    def verify(self, res: tuple[str, str]) -> tuple[str, str]:
        """A job-portal 'applied' is only believed when the job page itself shows Applied afterwards (a wrong 'applied' would hide a real backlog job)."""
        if res[0] != "applied" or not res[1].startswith("Submitted") or not PORTAL.search(re.sub(r"^https?://(www\.)?", "", self.job["url"]).split("/")[0]):
            return res
        try:
            vp = self.ctx.new_page()
            vp.goto(self.job["url"], wait_until="domcontentloaded", timeout=40000)
            vp.wait_for_timeout(3500)
            sn = snapshot(vp)
            ok = classify(sn) == "already_applied"
            vp.close()
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            return "applied", "Submitted and confirmed (the job page shows Applied)"
        return "needs_you", "Pressed submit, but the job page does not show Applied: check it by hand"

    @staticmethod
    def _portal_home(url: str) -> bool:
        """The portal's front page / search page (Workday .../en-US/Careers), not a job or an application."""
        from urllib.parse import urlparse
        parts = [x for x in urlparse(url).path.split("/") if x and not re.fullmatch(r"[a-z]{2}-[A-Za-z]{2}", x)]
        return len(parts) <= 1 and not re.search(r"/(job|jobs|apply|application|requisition)/", urlparse(url).path, re.I)

    def handle(self, kind: str, snap: dict, same: int) -> tuple[str, str] | None:
        if kind == "job_detail":
            self.seen_job = True
        elif getattr(self, "seen_job", False) and kind in ("form", "unknown", "job_detail") and self._portal_home(snap["url"])                 and re.search(r"/job/|/apply", self.job.get("url", "")):
            # Apply on a job page sent us to the portal's home: the posting no longer takes applications (Workday LSEG, Nov 18: the req was a year old).
            # Wandering through the site's search for it burned minutes and never found it.
            return "closed", "The posting no longer accepts applications: the portal sent Apply back to its home page"
        if kind == "submitted":
            from .classify import SUBMITTED
            m = SUBMITTED.search(snap["text"])
            self.log(f"submitted? url={snap['url'].split('?')[0][-70:]} matched='{(snap['text'][max(0, m.start() - 30):m.end() + 30] if m else '')[:110]}' headings={snap['headings'][:2]}")
            return "applied", "Submitted (the page confirms it)"
        if kind == "already_applied":
            # only a clear statement counts as applied; a vague match (or a greyed button we cannot see) is left to the owner, never reported as done
            if re.search(r"you('ve| have) already applied|already applied (for|to) this|already submitted an application", snap["text"], re.I) or any(
                    re.match(r"^(\W*)(applied|already applied|application submitted|view (my )?application)(\W*)$", b["text"], re.I) for b in snap["buttons"]):
                return "applied", "Already applied earlier"
            return "needs_you", "The page may say you already applied; check it by hand (not marked as applied)"
        if kind == "closed":
            return "closed", "The posting is closed or removed"
        if kind in ("captcha", "blocked"):
            if same == 0:
                self.page.wait_for_timeout(7000)   # some checks clear by themselves
                return None
            return "blocked", "Bot check / CAPTCHA: needs you"
        if kind == "account_exists":   # a previous try already created it: use the password we derive for this portal
            self.created.add(snap["host"])
            cloud.account(snap["host"], self.email)
            b = next((x for x in snap["buttons"] if re.match(r"^(sign ?in|log ?in|login|back to (the )?(log ?in|sign ?in)( page)?)$", x["text"], re.I) and not x["disabled"]), None)
            if not b:
                return "needs_you", f"An account for {snap['host']} already exists and I can't find its sign-in button"
            self.press(snap, b)
            return None
        if kind == "otp":
            return self.do_otp(snap)
        if kind == "verify_email":
            return self.do_verify_email(snap)
        if kind == "signin":
            return self.do_signin(snap)
        if kind == "create_account":
            return self.do_create(snap)
        if kind == "job_detail":
            return self.do_job_detail(snap)
        if kind in ("form", "unknown") and os.environ.get("APPLYBOT_RULES_ONLY") != "1":   # the AI drives these pages; the rules are the fallback
            r = self.ai_page(snap, kind)
            if r != "unavailable":
                return r
        if kind == "form":
            return self.do_form(snap)
        return self.do_unknown(snap, same)

    def press(self, snap: dict, b: dict) -> None:
        self._act = f"click {b['text'].strip().lower()}"
        """Click a button; the same control (kind + text + link target) pressed 3 times means we are going in circles."""
        key = f"{snap['host']}|{'a' if b['link'] else 'b'}|{b['text'].lower()}|{b.get('href', '')[:80]}"
        self.clicks[key] = self.clicks.get(key, 0) + 1
        if self.clicks[key] > 3:
            raise Stuck(f"pressing '{b['text']}' again and again changes nothing")
        if self.dry and re.match(r"^(submit( (my )?application)?|send( application)?|finish|complete application|confirm( and submit)?)\s*$", b["text"].strip(), re.I):
            # last line of defence for every click path (rules, AI plan, AI step): a dry run NEVER presses the final Submit
            self.log(f"DRY RUN: not pressing '{b['text']}'")
            self.dry_blocked = True
            return
        self.log(f"click '{b['text']}'")
        act.click(self.page, locate(snap, b["id"]))

    # ------------------------------------------------------------------ job page -> application
    EXTERNAL = re.compile(r"(company|employer|external|careers?)\b.*(site|website|page)|apply (externally|on website)|apply on .*(site|website)", re.I)

    def do_job_detail(self, snap: dict) -> tuple[str, str] | None:
        cands = [b for b in snap["buttons"] if APPLY_WORDS.match(b["text"]) and not b["disabled"] and not SOCIAL.search(b["text"])]
        if not cands:
            cands = [b for b in snap["buttons"] if re.search(r"\bapply\b", b["text"], re.I) and not b["disabled"] and not AVOID.match(b["text"])]
        if not cands:
            return "needs_you", "No Apply button found on the job page; buttons: " + ", ".join(x["text"][:20] for x in snap["buttons"][:8])
        order = ["apply manually", "apply now", "apply", "start", "i'm interested", "apply for this job", "apply online"]
        prev = getattr(self, "_prev_buttons", set())
        # a dropdown that just opened shows NEW buttons (Wipro: "Apply now" -> menu item "Apply Now"): take those first
        cands.sort(key=lambda b: (0 if (b["link"], b["text"].lower(), b.get("href", "")) not in prev else 1,
                                  next((i for i, o in enumerate(order) if b["text"].lower().startswith(o)), 99)))
        self._prev_buttons = {(x["link"], x["text"].lower(), x.get("href", "")) for x in snap["buttons"]}
        b = cands[0]
        if PORTAL.search(snap["host"]) and not self.EXTERNAL.search(b["text"]) and not getattr(self, "_left_portal", False):
            return "handoff", f"'{b['text']}' is the portal's own Easy Apply: handed to the extension system in your normal Chrome"
        if self.dry and re.match(r"^(submit|send|finish|complete|confirm)", b["text"], re.I):
            return "needs_you", "DRY RUN: stopped before the final Submit"
        self.press(snap, b)
        return None

    # ------------------------------------------------------------------ accounts
    def email_pw(self, host: str) -> tuple[str, str]:
        """(user name or email, password) for a portal: after an account recovery the recovered user name and the new password."""
        pws = cloud.passwords_for(host)
        who = getattr(self, "usernames", {}).get(host) or self.email
        if host in getattr(self, "pw_override", {}):
            return who, self.pw_override[host]
        return who, pws[min(getattr(self, "pw_idx", {}).get(host, 0), len(pws) - 1)]

    def _fill_by_kind(self, snap: dict, mapping: list[tuple[Any, str]]) -> None:
        for f, v in mapping:
            act.set_text(self.page, locate(snap, f["id"]), v)

    def _find_link(self, snap: dict, rx: re.Pattern) -> dict | None:
        for b in snap["buttons"]:
            if rx.search(b["text"]) and not b["disabled"] and not SOCIAL.search(b["text"]):
                return b
        return None

    def wait_for_owner_login(self, snap: dict) -> tuple[str, str] | None:
        """A job portal shows its login page: the owner signs in once in this Chrome window (asked on Telegram); the session is kept for good."""
        host = snap["host"]
        self.log(f"not signed in to {host}: asking the owner once")
        try:
            cloud.otp_request(self.job["id"], "login", f"Sign in to {host} in the Chrome window on your laptop (only the first time).", host)
        except Exception:  # noqa: BLE001
            pass
        end = time.time() + 20 * 60
        while time.time() < end:
            self.page.wait_for_timeout(5000)
            cloud.alive(self.job["id"])
            try:
                sn = snapshot(self.page)
            except Exception:  # noqa: BLE001
                continue
            if classify(sn) not in ("signin", "create_account") or not PORTAL.search(sn["host"]):
                self.log("signed in, continuing")
                return None
        return "needs_you", f"Not signed in to {host}: sign in in the Chrome window and I will retry"

    def do_signin(self, snap: dict) -> tuple[str, str] | None:
        host = snap["host"]
        if PORTAL.search(host):
            return self.wait_for_owner_login(snap)
        email, pw = self.email_pw(host)
        if not brain.budget_left(host, "signin") and host not in getattr(self, "pw_override", {}):
            return "needs_you", f"{host}: today's sign-in budget ({brain.LEDGER_CAPS['signin']}) is used up: not trying again (a failed login can lock the account). Sign in by hand or run again tomorrow."
        if os.environ.get("APPLYBOT_RECOVER_FIRST") == "1" and not getattr(self, "_recovered", False) and host not in getattr(self, "pw_override", {}):
            self._recovered = True   # owner said: the account exists, credentials unknown: reset first (failed sign-ins lock Taleo accounts)
            from .recover import recover

            self.usernames = {**getattr(self, "usernames", {}), host: self.email}   # the owner confirmed user name = email
            res = recover(self, host, self.t0 - 60)
            if res:
                return res
            self.tried_signin.discard(host)
            return None
        known = host in self.accounts or host in self.created
        make = self._find_link(snap, re.compile(r"(create (an )?account|register|sign ?up|new (user|candidate)|don't have an account|join)", re.I))
        if not known and make and host not in self.clicked_create:
            self.clicked_create.add(host)
            self.log("no account here yet: opening 'create account'")
            act.click(self.page, locate(snap, make["id"]))
            return None
        # signed in once already on this page with the same inputs and still here: try the other password, then the create-account link
        if not hasattr(self, "pw_idx"):
            self.pw_idx = {}
        if host in self.tried_signin and self.pw_idx.get(host, 0) == 0 and len(cloud.passwords_for(host)) > 1:
            self.pw_idx[host] = 1
            self.tried_signin.discard(host)
            email, pw = self.email_pw(host)
        if host in self.tried_signin:
            # Taleo & co. offer "Apply as Guest": no account needed (an existing account of ours with unknown credentials is no blocker)
            if (getattr(self, "_guest_used", False) or host in self.created) and not getattr(self, "_recovered", False):
                self._recovered = True   # the email has an account whose credentials we do not have: user name + password reset by mail
                from .recover import recover

                res = recover(self, host, self.t0 - 60)
                if res:
                    return res
                self.tried_signin.discard(host)
                return None
            guest = next((b for b in snap["buttons"] if re.match(r"^(apply|continue) as (a )?guest$|^(apply|continue) without (an )?(account|signing in)$|^guest( apply)?$", b["text"], re.I) and not b["disabled"]), None)
            if guest and not getattr(self, "_guest_used", False):
                self._guest_used = True
                self.log("sign-in did not work: applying as a guest")
                self.press(snap, guest)
                return None
            if make and host not in self.clicked_create:
                self.clicked_create.add(host)
                self.log("sign-in did not work: trying 'create account'")
                act.click(self.page, locate(snap, make["id"]))
                return None
            return "needs_you", f"Couldn't sign in to {host} (check the account / password)"
        self.tried_signin.add(host)
        brain.ledger_add(host, "signin")
        for f in snap["fields"]:
            if f["kind"] == "password":
                act.set_text(self.page, locate(snap, f["id"]), pw)
            elif f["kind"] in ("email", "text") and not f["value"]:
                act.set_text(self.page, locate(snap, f["id"]), email)
        self.log("signing in")
        return self._press(snap, re.compile(r"^(sign ?in|log ?in|login|continue|next|submit)$", re.I))

    DOC_LINK = re.compile(r"((read|review|view|open)( and)?( accept| agree)?.*(privacy|terms|policy|statement|agreement|conditions|notice))|((accept|agree to|i agree( to)?|i accept).*(privacy|terms|policy|statement|agreement|conditions))", re.I)
    DOC_OK = re.compile(r"^(accept|i accept|accept (all|and continue|terms)|agree|i agree|agree and continue|ok|okay|continue|confirm|done|close|yes)$", re.I)

    def accept_documents(self, snap: dict) -> bool:
        """Portals that make you OPEN the privacy statement / terms and press Accept before the box can be ticked or the form sent."""
        host = snap["host"]
        if getattr(self, "_docs_done", None) is None:
            self._docs_done = set()
        for b in snap["buttons"]:
            if b["disabled"] or not self.DOC_LINK.search(b["text"]) or SOCIAL.search(b["text"]) or f"{host}|{b['text']}" in self._docs_done:
                continue
            self._docs_done.add(f"{host}|{b['text']}")
            self.log(f"opening '{b['text'][:50]}' to accept it")
            home = self.page
            n0 = len(self.ctx.pages)
            act.click(self.page, locate(snap, b["id"]))
            self.page.wait_for_timeout(1500)
            opened = len(self.ctx.pages) > n0
            if opened:
                self.page = [p for p in self.ctx.pages if not p.is_closed()][-1]
            s2 = snapshot(self.page)
            ok = next((x for x in s2["buttons"] if self.DOC_OK.match(x["text"]) and not x["disabled"]), None)
            if ok:
                self.log(f"pressing '{ok['text']}'")
                act.click(self.page, locate(s2, ok["id"]))
                self.page.wait_for_timeout(1000)
            if opened and not self.page.is_closed() and self.page != home:   # a document opened in its own tab: back to the form
                self.page.close()
            self.page = home
            return True
        return False

    def fix_named_errors(self, snap: dict) -> None:
        """Workday lists "Error-<field> The field <field> is required": the field itself can be invisible to the page reader (a 1px input behind a styled
        control). Find it by its label and fill it from the answer bank / AI, so the form can move on."""
        from .answers import resolve
        done = getattr(self, "_named_done", set())
        self._named_done = done
        for e in snap["errors"]:
            m = re.search(r"Error-?\s*(.+?)\s+The field", e)
            if not m:
                continue
            label = m.group(1).strip(" :*")
            if not label or label in done:
                continue
            if any(label.lower() in f["label"].lower() and f["value"] for f in snap["fields"]):
                continue
            done.add(label)
            try:
                ctl = self.page.get_by_label(re.compile(re.escape(label[:60]), re.I)).first
                if ctl.count() == 0:
                    ctl = self.page.locator(f'[aria-label*="{label[:40]}" i], [data-automation-id*="multiselect" i]').first
                fake = {"id": "named", "kind": "combo", "label": label, "required": True, "value": "", "invalid": False, "error": "", "options": [], "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0}
                ans = resolve([fake], self.profile, self.job, self.ai).get("named")
                if ans and ans["value"]:
                    ok = act.set_combo(self.page, ctl, ans["value"], ans.get("alts"))
                    self.log(f"named-error field '{label[:40]}': {'set' if ok else 'could not set'}")
            except Exception as ex:  # noqa: BLE001
                self.log(f"named-error field '{label[:40]}': {str(ex)[:60]}")

    def repair_invalid(self, snap: dict) -> int:
        """A field the page marks invalid / shows an error for: read the error and set the next sensible value (end month = start + 1,
        salary 0 -> 1, "enter a number" -> 0 / 1 ...). No AI, so it is instant and works on every portal. Max 3 tries per field."""
        from . import repair
        tried = getattr(self, "_repair_tries", {})
        self._repair_tries = tried
        n = 0
        for f in snap["fields"]:
            if f["kind"] in ("file", "radio", "checkbox", "select", "combo") or f.get("disabled") or f.get("readonly"):
                continue
            key = (snap["host"], f.get("block") or f.get("name") or f["label"][:60])
            new = repair.repair_value(f, snap["fields"], tried.get(key, 0))
            if new is None or new == str(f.get("value") or ""):
                continue
            tried[key] = tried.get(key, 0) + 1
            try:
                ok = act.set_text(self.page, locate(snap, f["id"]), new)
            except Exception:  # noqa: BLE001
                ok = False
            self.log(f"repair '{f['label'][:40]}': {f.get('value', '')!r} -> {new!r} ({(f.get('error') or f.get('validation') or 'invalid')[:60]}) {'ok' if ok else 'failed'}")
            n += 1 if ok else 0
        return n

    HEAR = re.compile(r"linkedin|twitter|indeed|glassdoor|referr|friend|conference|job ?board|job portal|campus|career|website|social|search engine|google|blog|event|newspaper|naukri", re.I)
    HEAR_PREF = ["linkedin", "job board", "job portal", "careers website", "career", "company website", "website", "internet", "social", "other"]

    def fill_checkbox_groups(self, snap: dict) -> set[str]:
        """'How did you hear about us' = a group of boxes where ONE must be ticked (each box looks 'required'). Tick the best matching one.
        Returns the ids of all boxes in handled groups so they are not reported as missing."""
        groups: dict[str, list[dict]] = {}
        for f in snap["fields"]:
            if f["kind"] == "checkbox" and f.get("grp"):
                groups.setdefault(f["grp"], []).append(f)
        handled: set[str] = set()
        for boxes in groups.values():
            if len(boxes) < 3:
                continue
            labels = [b["label"] for b in boxes]
            if sum(1 for l in labels if self.HEAR.search(l)) < 3:
                continue
            handled.update(b["id"] for b in boxes)
            if any(b.get("checked") for b in boxes):
                continue
            pick = None
            for pref in self.HEAR_PREF:
                pick = next((b for b in boxes if pref in b["label"].lower()), None)
                if pick:
                    break
            pick = pick or boxes[-1]
            act.set_checkbox(self.page, locate(snap, pick["id"]), True)
            self.log(f"'how did you hear' group: ticked '{pick['label'][:30]}'")
        return handled

    def _resume_listed(self, snap: dict) -> bool:
        """The page already shows our resume file (Taleo lists attached files in a table and refuses a second copy:
        "This file has already been attached", Nov 18)."""
        import os as _os

        name = _os.path.basename(self.resume or "").lower()
        text = (snap.get("full_text") or snap.get("text") or "").lower()
        return bool(name and name in text) or any(re.search(r"already (been )?(attached|uploaded)", e, re.I) for e in snap.get("errors") or [])

    def _file_done(self, f: dict) -> bool:
        """A file box we already uploaded to (the page may re-render it empty, with a new id, once the file is processed)."""
        return f["kind"] == "file" and (f["value"] != "" or (f["label"] or f["name"]).strip().lower() in getattr(self, "_uploaded", set()))

    def untick_marketing(self, snap: dict) -> None:
        from .answers import MARKETING
        for f in snap["fields"]:
            if f["kind"] == "checkbox" and f.get("checked") and MARKETING.search(f["label"]) and not f["required"]:
                act.set_checkbox(self.page, locate(snap, f["id"]), False)

    def do_create(self, snap: dict) -> tuple[str, str] | None:
        host = snap["host"]
        if PORTAL.search(host):
            return self.wait_for_owner_login(snap)
        email, pw = self.email_pw(host)
        pwf = [f for f in snap["fields"] if f["kind"] == "password"]
        for f in pwf:
            act.set_text(self.page, locate(snap, f["id"]), pw)
        others = [f for f in snap["fields"] if f["kind"] != "password"]
        ans = resolve(others, self.profile, self.job, self.ai)
        for f in others:
            a = ans.get(f["id"])
            if a and a["value"]:
                act.apply_answer(self.page, snap, f, a)
        from .answers import CONSENT, MARKETING
        for f in others:   # consent boxes on a sign-up form ("Yes I Consent", "I agree...") are part of creating the account
            if f["kind"] == "checkbox" and not f.get("checked") and (f["required"] or CONSENT.search(f["label"])) and not MARKETING.search(f["label"]):
                act.set_checkbox(self.page, locate(snap, f["id"]), True)
        self.untick_marketing(snap)
        if (any(re.search(r"privacy|terms|agreement|statement|accept", e, re.I) for e in snap["errors"]) or True) and self.accept_documents(snap):
            return None
        self.log("creating the account")
        self.created.add(host)
        r = self._press(snap, re.compile(r"(create|register|sign ?up|join|submit|continue|next)", re.I))
        if not r:
            cloud.account(host, email)
        return r

    def do_otp(self, snap: dict) -> tuple[str, str] | None:
        host = snap["host"]
        code = None
        got = mail.wait(host, self.t0 - 180, "code", 3, [self.job.get("company", "")])   # straight from Gmail: nothing for the owner to do
        if got:
            self.log(f"read the {got[0]} from Gmail")
            code = got[1]
        else:
            req = cloud.otp_request(self.job["id"], "code", "", host)
            self.log("no mail found: asking on Telegram")
            code = cloud.otp_wait(req, self.job["id"])
        if not code:
            return "needs_you", f"{host} wanted a verification code and none arrived in 10 minutes"
        if code.startswith("http"):
            self.page.goto(code, wait_until="domcontentloaded", timeout=40000)
            return None
        boxes = [f for f in snap["fields"] if f["kind"] in ("text", "number", "code", "tel", "password")]
        named = [f for f in boxes if re.search(r"code|otp|passcode|pin", f"{f['label']} {f['name']}", re.I)]
        if named and len(named) < len(boxes):
            boxes = named + [f for f in boxes if f not in named]   # the box that is labelled as the code first (a blank hidden box may come before it)
        if len(boxes) >= 4 and all(f["maxlength"] == 1 for f in boxes[:4]):
            act.click(self.page, locate(snap, boxes[0]["id"]))
            self.page.keyboard.type(code, delay=80)
        elif boxes:
            act.set_text(self.page, locate(snap, boxes[0]["id"]), code)
        self.log("code entered")
        r = self._press(snap, re.compile(r"(verify|confirm|submit|continue|next|activate|validate)", re.I))
        if r is None and not any(re.search(r"(verify|confirm|submit|continue|next|activate|validate)", b["text"], re.I) for b in snap["buttons"] if not b["disabled"]):
            self.page.keyboard.press("Enter")
        return r

    def do_verify_email(self, snap: dict) -> tuple[str, str] | None:
        host = snap["host"]
        val = None
        got = mail.wait(host, self.t0 - 180, "link", 3, [self.job.get("company", "")])
        if got:
            self.log(f"read the {got[0]} from Gmail")
            val = got[1]
        else:
            req = cloud.otp_request(self.job["id"], "link", "Open the email from this site and send me its verification link", host)
            self.log("no mail found: asking on Telegram")
            val = cloud.otp_wait(req, self.job["id"])
        if not val:
            return "needs_you", f"{host} wants the email verified and nothing arrived in 10 minutes"
        if val.startswith("http"):
            self.page.goto(val, wait_until="domcontentloaded", timeout=40000)
        else:
            self.log("got a code instead of a link: looking for a box")
        # the link verified the account in this browser; the original apply link continues from the portal's own sign-in
        self.page.goto(self.job["url"], wait_until="domcontentloaded", timeout=40000)
        return None

    # ------------------------------------------------------------------ the form
    def do_form(self, snap: dict) -> tuple[str, str] | None:
        # Workday & co. render after the first load: a "form" with no labelled field and no Next/Submit is a page still loading (or a header only)
        real = [f for f in snap["fields"] if (f["label"].strip() and f["label"].strip().lower() not in ("english", "language", "search")) or f["kind"] in ("file", "textarea")]
        action = [b for b in snap["buttons"] if not b["disabled"] and re.match(r"^(next|continue|submit|save|review|apply|send)\b", b["text"], re.I)]
        if not real and not action:
            self.loading = getattr(self, "loading", 0) + 1
            if self.loading <= 6:
                self.log("page still loading, waiting")
                self.page.wait_for_timeout(2000)
                return None
        self.fill_rounds += 1
        self.untick_marketing(snap)
        self.fix_named_errors(snap)
        if self.repair_invalid(snap):
            self.page.wait_for_timeout(400)
        grouped = self.fill_checkbox_groups(snap)
        fields = [f for f in snap["fields"] if f["id"] not in grouped]
        # custom dropdowns: read their options first so the answer is matched to a real option
        for f in fields:
            if f["kind"] == "combo" and not f["value"] and not f["options"] and f["required"]:
                f["options"] = act.read_combo_options(self.page, locate(snap, f["id"]))
        ans = resolve(fields, self.profile, self.job, self.ai)
        done: set[str] = set()
        failed: list[str] = []
        for f in fields:
            a = ans.get(f["id"])
            if not a or not a["value"] or f.get("disabled") or f.get("readonly"):
                continue
            ok = False
            try:
                ok = act.apply_answer(self.page, snap, f, a)
            except Exception:  # noqa: BLE001
                ok = False
            (done.add(f["id"]) if ok else failed.append(f["label"][:50]))
        for f in fields:   # resume
            if f["kind"] == "file" and not f["value"]:
                if self._resume_listed(snap):
                    self.log("resume already attached on this page: not uploading again")
                    continue
                if not file_slot_is_resume(f):
                    self.log(f"file slot left empty: {(f.get('heading') or f['label'])[:40]}")
                    continue
                if act.upload(self.page, locate(snap, f["id"]), self.resume):
                    done.add(f["id"])
                    self._uploaded = getattr(self, "_uploaded", set()) | {(f["label"] or f["name"]).strip().lower()}
                    self.log(f"resume uploaded ({f['label'][:30] or 'file'})")
        self.log(f"filled {len(done)} field(s)" + (f"; couldn't set: {', '.join(failed[:4])}" if failed else "") + (f" [combo: {act.LAST_COMBO}]" if act.LAST_COMBO else ""))
        self.page.wait_for_timeout(500)
        # look again: what is still empty / invalid?
        snap2 = snapshot(self.page)
        missing = []
        for f in snap2["fields"]:
            if f["kind"] in ("password",) or f["id"] in grouped or self._file_done(f):
                continue
            empty = (not f["value"]) if f["kind"] != "checkbox" else not f.get("checked")
            if (f["required"] and empty and f["id"] not in done) or ((f["invalid"] or f["error"]) and f["required"]):
                missing.append(f)
        # fields the page REJECTED (red message / invalid state) are re-answered from what the message says: the spec learns the expected shape,
        # the same answer is re-formatted, and when that gives the identical text the AI is asked with the page's own words (max 2 tries per field)
        tries = getattr(self, "_fix_tries", None)
        if tries is None:
            tries = self._fix_tries = {}
        rejected = [f for f in snap2["fields"] if f["kind"] not in ("password", "file", "checkbox") and (f["error"] or (f["invalid"] and f.get("validation")))
                    and not f.get("disabled") and tries.get(f["id"], 0) < 2]
        if rejected:
            retry = []
            for f in rejected:
                tries[f["id"]] = tries.get(f["id"], 0) + 1
                self.log(f"page rejected '{(f['label'] or f['name'])[:30]}': {(f['error'] or f.get('validation'))[:90]}")
                retry.append(dict(f, invalid=True, error=f["error"] or f.get("validation"), _force_ai=tries[f["id"]] > 1, value=""))
            ans3 = resolve(retry, self.profile, self.job, self.ai)
            for f in retry:
                a = ans3.get(f["id"])
                if a and a["value"] and a["value"].strip().lower() != (next((x["value"] for x in rejected if x["id"] == f["id"]), "") or "").strip().lower():
                    try:
                        act.apply_answer(self.page, snap2, f, a)
                        self.log(f"re-answered '{(f['label'] or f['name'])[:30]}' in the shape the page asked for")
                    except Exception:  # noqa: BLE001
                        pass
            self.page.wait_for_timeout(500)
            snap2 = snapshot(self.page)
            missing = []
            for f in snap2["fields"]:
                empty = (not f["value"]) if f["kind"] != "checkbox" else not f.get("checked")
                if f["kind"] != "password" and f["id"] not in grouped and not self._file_done(f) and ((f["required"] and empty and f["id"] not in done) or ((f["invalid"] or f["error"]) and f["required"])):
                    missing.append(f)
        # the same fields on this page, answered again with the portal's error text (once per page)
        if missing and self.fill_rounds % 2 == 1:
            retry = [f for f in missing if f["kind"] not in ("file",)]
            ans2 = resolve([dict(f, value="", invalid=True) for f in retry], self.profile, self.job, self.ai)
            for f in retry:
                a = ans2.get(f["id"])
                if a and a["value"]:
                    try:
                        act.apply_answer(self.page, snap2, f, a)
                    except Exception:  # noqa: BLE001
                        pass
            self.page.wait_for_timeout(400)
            snap2 = snapshot(self.page)
            missing = [f for f in snap2["fields"] if f["kind"] != "password" and f["id"] not in grouped and not self._file_done(f) and f["required"] and ((not f["value"]) if f["kind"] != "checkbox" else not f.get("checked"))
                       and not (f["id"] in done and f["kind"] in ("combo", "radio"))]
        buttons = [b for b in snap2["buttons"] if not b["disabled"] and not AVOID.match(b["text"]) and not SOCIAL.search(b["text"])]
        final = next((b for b in buttons if FINAL.match(b["text"])), None)
        nxt = next((b for b in buttons if NEXT.match(b["text"])), None)
        target = final or nxt
        if not target:
            target = next((b for b in buttons if b["primary"]), None)
        # Workday shows a chosen dropdown value as a tag / in the label, so "empty?" cannot be read for those: with no error message on the page the
        # dropdowns count as answered, and the portal's own validation (after Save / Continue) tells us if one really is missing.
        if missing and not snap2["errors"]:
            missing = [f for f in missing if f["kind"] not in ("combo", "select")]
        if missing and done and getattr(self, "dyn_rounds", 0) < 4 and len(snap2["fields"]) > len(snap["fields"]):
            # a dynamic form: answering one field (Country...) reveals more required fields. Fill the newly shown ones before giving up.
            self.dyn_rounds = getattr(self, "dyn_rounds", 0) + 1
            self.log("the form grew: filling the newly shown fields")
            self.page.wait_for_timeout(800)
            return None
        self.dyn_rounds = 0
        if missing:
            names = ", ".join(sorted({(f["label"] or f["name"] or f["kind"])[:60] for f in missing})[:6])
            return "needs_you", f"Couldn't answer: {names}"
        if not target:
            self.log("page text: " + re.sub(r"\s+", " ", snap2.get("text", ""))[:400])
            r = self.ai_step(snap2, "form")
            if r == "acted":
                return None
            if r:
                return r
            return "needs_you", "No Next / Submit button found; buttons: " + ", ".join(x["text"][:20] for x in snap2["buttons"][:8])
        if final and FINAL.match(target["text"]) and self.dry:
            return "needs_you", "DRY RUN: everything filled, stopped before the final Submit"
        self.press(snap2, target)
        self.settle(700)
        return None

    # ------------------------------------------------------------------ unknown page
    def _supported(self, label: str) -> bool:
        """A skill / technology box is ticked only when the resume (or work history) really mentions it: the acronym in brackets, else a
        distinctive word of the label. "None of the above" is never ticked."""
        if re.search(r"none of the above|not applicable|^none$", label, re.I):
            return False
        text = ((self.profile.get("resume_text") or "") + " " + json.dumps(self.profile.get("experience") or []) + " " + str(self.profile.get("job_preferences", {}).get("relevant_experience", ""))).lower()
        if not text.strip():
            return False
        acr = re.search(r"\(([A-Za-z0-9+#.]{2,12})\)", label)
        keys = []
        if acr:
            keys.append(acr.group(1).lower().rstrip("s"))
        keys += [w for w in re.findall(r"[a-z0-9+#.]{5,}", label.lower()) if w not in ("large", "language", "models", "model", "based", "using", "other", "technologies")]
        return any(k and k in text for k in keys)

    def _close_pickers(self, snap: dict) -> None:
        """A month / date picker that is still open covers the buttons below it (Nov 18, Cisco: 'Add experience' sat under the open month picker, the
        click did nothing and the AI repeated the same plan for minutes): click an empty spot at the left margin so the picker closes first."""
        try:
            open_pick = any("picker opened" in (f.get("label") or "").lower() for f in snap.get("fields", [])) or \
                self.page.locator("[class*=datepicker]:visible, [class*=monthpicker]:visible, [class*=calendar]:visible").count() > 0
            if open_pick:
                self.page.mouse.click(12, 420)
                self.page.wait_for_timeout(350)
        except Exception:  # noqa: BLE001
            pass

    def _same_job(self, snap: dict) -> bool:
        """False when the page is clearly ANOTHER job (Nov 18, Micron: the AI clicked 'view all jobs' and began applying to 'Staff Design
        Engineer, DRAM' instead of 'Engineer, Data Science'): every distinctive word of the wanted title must appear on the page."""
        words = [w for w in re.findall(r"[a-z0-9+#]{3,}", str(self.job.get("title") or "").lower()) if w not in ("the", "and", "for", "with")]
        text = (snap.get("title", "") + " " + snap.get("text", "")).lower()
        if not words or len(text) < 200:
            return True
        return all(w in text for w in words)

    def ai_page(self, snap: dict, kind: str):
        """AI-driven page: one call -> a batch plan on element ids, executed in order (stops at the first click). Returns None to carry on
        (the loop re-observes), a (status, detail) to stop, or "unavailable" when no plan could be made (the caller falls back to the rules)."""
        from . import plan

        if getattr(self, "ai_pages", 0) >= 80:
            return "unavailable"
        self.ai_pages = getattr(self, "ai_pages", 0) + 1
        # A page that only shows the portal header (no labelled field, no Next/Save/Apply button) is still being drawn: give it time before the AI
        # sees it (Workday LSEG, Nov 18: right after "Continue Application" the AI judged the empty shell and quit with "no Apply button").
        def _empty(sn: dict) -> bool:
            return len([f for f in sn["fields"] if f["label"].strip()]) <= 1 and not any(
                re.match(r"^(next|continue|save|submit|review|apply|send)", b["text"], re.I) for b in sn["buttons"] if not b["disabled"] and not b["link"])
        for _ in range(4):
            if not _empty(snap):
                break
            self.log("page looks empty (still loading): waiting before asking the AI")
            self.page.wait_for_timeout(5000)
            snap = snapshot(self.page)
        # The page was re-read while we waited: it may now be a page the rules own (Workday drew "Create Account" 5-10 s after "Apply Manually",
        # CBA Nov 19: the AI got it, typed the email and quit with "need a password"). Sign-in / account / code / closed / done pages are never the AI's:
        # hand them back so the loop dispatches them to their handlers (which hold the portal password and the mail watcher).
        now = classify(snap)
        if now not in ("form", "unknown"):
            self.ai_pages -= 1
            self.log(f"page became '{now}' while waiting: handing it to the {now} handler")
            return self.handle(now, snap, 0)
        # Custom dropdowns show no options until opened: without them the AI invents a wording ("B.E.", "Yes") that is not in the list
        # (CBA Workday Nov 19: "Undergraduate / Graduate / Postgraduate" looped for 6 minutes). Open each empty one once and read its list.
        cache = self.__dict__.setdefault("_opt_cache", {})
        n_read = 0
        for f in snap["fields"]:
            if f["kind"] == "combo" and not f["value"] and not f["options"] and f["label"].strip() and n_read < 14:
                loc = locate(snap, f["id"])
                try:
                    if act._wd_multi(loc):   # search-style multiselect: its list is the search result, not a fixed set
                        continue
                except Exception:  # noqa: BLE001
                    pass
                ck = (f.get("block") or "") + "|" + (f.get("name") or f["label"][:200])
                if ck not in cache:
                    n_read += 1
                    cache[ck] = act.read_combo_options(self.page, loc)
                f["options"] = list(cache[ck])
        pl = plan.ask_ai(self.ai, self.job, self.profile, self.mem, snap)
        if not pl:
            return "unavailable"
        self.mem["notes"] = str(pl.get("note") or "")[:300]
        fb: list[str] = []
        acts = plan.check_plan(pl, snap, self._supported, fb)
        if fb:   # the AI reads this next turn (history): it is told exactly what it left empty
            self.mem["history"].append({"page": f"{kind} | {snap['title'][:40]}", "action": "(my plan was refused before the click)", "result": "refused: " + fb[0]})
        fields = {f["id"]: f for f in snap["fields"]}
        buttons = {b["id"]: b for b in snap["buttons"]}
        sets = ticks = 0
        dropped, clicked, failed_sets = [], "", []
        self.log(f"AI plan ({len(acts)}): {pl.get('note', '')[:120]}")
        if any(a.get("do") == "_dropped" and "unknown field" in str(a.get("_drop", "")) for a in acts):   # say exactly what was refused and which fields exist
            self.log("refused: " + "; ".join(f"{a.get('id')}={str(a.get('value', ''))[:14]!r} known={a.get('id') in fields}" for a in acts if a.get("do") == "_dropped")[:300])
            self.log("date-like fields: " + ", ".join(f"{f['id']}|{f['kind']}|{f['label'][:14]}|{f.get('name', '')[:22]}|{f.get('placeholder', '')}" for f in snap["fields"] if re.search(r"from|to|month|year|date|mm|yyyy", f"{f['label']} {f.get('name', '')} {f.get('placeholder', '')}", re.I))[:700])
        for a in acts:
            do, i, v = a["do"], a.get("id", ""), str(a.get("value", ""))
            if do == "_dropped":
                dropped.append(f"{a.get('do')}:{i} {a.get('_drop', '')}")
                continue
            try:
                if do == "set":
                    f = fields[i]
                    if f["kind"] in ("combo", "select") and f.get("options") and not match_option(v, f["options"]):
                        failed_sets.append(f"{f['label'][:40]}: '{v[:30]}' is not one of the options {[o[:40] for o in f['options'][:8]]}")
                        dropped.append(f"set:{f['label'][:30]} value not in options")
                        continue
                    if f["kind"] in ("combo", "select") and f.get("options"):
                        v = match_option(v, f["options"]) or v
                    if f["kind"] in ("text", "email", "tel", "number", "date", "textarea", "code"):
                        act.set_text(self.page, locate(snap, i), v)
                        sets += 1
                    elif act.apply_answer(self.page, snap, f, {"value": v, "source": "ai"}):
                        sets += 1
                    else:
                        dropped.append(f"set:{f['label'][:30]} not set")
                        failed_sets.append(f"{f['label'][:40]}: could not be set to '{v[:30]}'" + (f" (options {[o[:40] for o in f['options'][:8]]})" if f.get("options") else ""))
                elif do == "tick":
                    f = fields[i]
                    if act.apply_answer(self.page, snap, f, {"value": "true" if v.strip().lower() in ("true", "yes", "1", "checked") else "false", "source": "ai"}):
                        ticks += 1
                elif do == "upload":
                    if self._resume_listed(snap):
                        continue
                    act.upload(self.page, locate(snap, i), self.resume)
                    sets += 1
                elif do == "click":
                    if re.match(r"^(apply|i'?m interested|start (my )?(application|applying))", buttons[i]["text"].strip(), re.I) and not self._same_job(snap):
                        return "needs_you", f"This page is a different job from '{self.job.get('title', '')}' ({snap.get('title', '')[:60]}): not applying to it"
                    if self.dry and re.match(r"^(submit|send application|send|finish|complete application|confirm)", buttons[i]["text"].strip(), re.I):
                        return "needs_you", "DRY RUN: everything filled, stopped before the final Submit"
                    if failed_sets and re.match(r"^(next|continue|save|submit|review|send)", buttons[i]["text"].strip(), re.I):
                        # a field was not accepted: moving on only produces the same error page. Look again; the AI is told what failed.
                        self.mem["history"].append({"page": f"{kind} | {snap['title'][:40]}", "action": "(I did not press " + buttons[i]["text"].strip() + ": a field was not accepted)",
                                                    "result": "failed: " + " | ".join(failed_sets)[:400]})
                        self.log("not pressing the button: " + failed_sets[0][:150])
                        self.page.wait_for_timeout(500)
                        return None
                    self._close_pickers(snap)
                    self.press(snap, buttons[i])
                    clicked = buttons[i]["text"].strip()
                    break
                elif do == "code":
                    self._act = "AI plan: read the e-mailed code from Gmail"
                    return self.do_otp(snap)
                elif do == "link":
                    self._act = "AI plan: read the verification link from Gmail"
                    return self.do_verify_email(snap)
                elif do == "wait":
                    self.page.wait_for_timeout(3500)
                    break
                elif do == "ask":
                    # A question about WHERE a button is (or about a page that has no real field yet) means the portal is still drawing the page
                    # (Workday LSEG, Nov 18: right after "Continue Application" the AI gave up with "where is the Apply button?"). Wait and look again.
                    real_fields = [f for f in snap["fields"] if f["label"].strip() and f["kind"] not in ("file",)]
                    if getattr(self, "_ask_waits", 0) < 4 and (re.search(r"(where|which|button|link|page|load)", v, re.I) or len(real_fields) <= 2):
                        self._ask_waits = getattr(self, "_ask_waits", 0) + 1
                        self.log(f"page may still be loading: waiting instead of asking ({self._ask_waits}/4)")
                        self.page.wait_for_timeout(6000)
                        return None
                    return "needs_you", "Needs a fact I don't have: " + v[:200]
                elif do == "done":
                    return "applied", "Submitted (the AI judged the application complete: " + str(a.get("why", ""))[:120] + ")"
                elif do == "stop":
                    return "needs_you", "Cannot continue safely: " + (v or str(a.get("why", "")))[:200]
            except Exception as exc:  # noqa: BLE001
                dropped.append(f"{do}:{i} failed ({str(exc)[:50]})")
        if dropped:
            self.log("AI plan, skipped: " + "; ".join(dropped[:5]))
        self._act = f"AI plan: {sets} fields set, {ticks} ticked" + (f", clicked '{clicked.lower()}'" if clicked else "")
        if clicked:
            self._act = f"{self._act}"
        return None

    def ai_step(self, snap: dict, kind: str):
        """Ask the brain for the next action; None = it had nothing to add, "acted" = something was done, (status, detail) = stop."""
        if self.ai_steps >= 30:
            return None
        self.ai_steps += 1
        from .answers import compact_profile

        act_ = brain.decide(self.ai, self.job, compact_profile(self.profile), self.mem, snap)
        if not act_:
            return None
        ok, why = brain.validate(act_, snap, self.mem)
        self.log(f"AI decides: {act_.get('action')} {act_.get('button') or ''} | {act_.get('reason', '')[:110]}" + ("" if ok else f" | REFUSED: {why}"))
        if not ok:
            self.mem["history"].append({"page": f"{kind} | {snap['title'][:40]}", "action": f"(AI proposed {act_.get('action')} {act_.get('button') or ''})", "result": f"refused: {why}"})
            return None
        a = act_["action"]
        if a == "wait":
            self._act = "wait"
            self.page.wait_for_timeout(4000)
            return "acted"
        if a == "click":
            b = next(x for x in snap["buttons"] if x["text"].strip().lower() == act_["button"].strip().lower() and not x["disabled"])
            self.press(snap, b)
            return "acted"
        if a == "fill":
            done, missed, taken = 0, [], set()
            for want in act_["fields"]:
                f = brain.match_field(snap["fields"], want["label"], taken)
                if not f or not want["value"]:
                    missed.append(want["label"][:40])
                    continue
                taken.add(f["id"])
                try:
                    v = want["value"]
                    if f["kind"] == "checkbox":
                        v = "true" if str(v).strip().lower() in ("true", "yes", "checked", "tick", "1") else "false"
                        if v == "true" and not self._supported(f["label"]):
                            missed.append(f["label"][:30] + " (not in the resume: left unticked)")
                            continue
                    elif f.get("options"):   # a choice: the page's own option text
                        from .answers import match_option

                        v = match_option(v, f["options"]) or v
                    if act.apply_answer(self.page, snap, f, {"value": v, "source": "ai"}):
                        done += 1
                    else:
                        missed.append(want["label"][:40] + " (not set)")
                except Exception:  # noqa: BLE001
                    missed.append(want["label"][:40] + " (error)")
            self.log(f"AI fill: {done} set" + (f"; not matched / not set: {missed[:6]}" if missed else ""))
            self._act = f"filled {done} field(s) (AI)"
            return "acted" if done else None
        if a == "get_code":
            self._act = "read the code from Gmail"
            return self.do_otp(snap) or "acted"
        if a == "ask_owner":
            return "needs_you", "Needs a fact I don't have: " + act_.get("reason", "")[:200]
        if a == "give_up":
            return "needs_you", "Cannot continue safely: " + act_.get("reason", "")[:200]
        if a == "done":
            return "applied", "Submitted (the AI judged the application complete: " + act_.get("reason", "")[:120] + ")"
        return None

    def do_unknown(self, snap: dict, same: int) -> tuple[str, str] | None:
        if re.search(r"currently unavailable|temporarily unavailable|under maintenance|service unavailable|try again later|something went wrong", snap["text"][:600], re.I) or "community.workday.com" in snap["host"]:
            self.outage = getattr(self, "outage", 0) + 1   # the portal is down / throttling: wait, then open the job again (the saved draft resumes)
            if self.outage <= 4:
                self.log(f"portal says it is unavailable: waiting 25 s and reopening ({self.outage}/4)")
                self.page.wait_for_timeout(25000)
                try:
                    self.page.goto(self.job["url"], wait_until="domcontentloaded", timeout=45000)
                except Exception:  # noqa: BLE001
                    pass
                return None
            return "needs_you", "The portal stayed unavailable (its own outage): try again later"
        no = next((b for b in snap["buttons"] if not b["disabled"] and self.COOKIE_NO.match(b["text"].strip())), None)
        if no and same < 3:   # a cookie wall that covers the page: reject non-essential (privacy-friendly), then look again
            self.log(f"cookie wall: '{no['text']}'")
            act.click(self.page, locate(snap, no["id"]))
            self.page.wait_for_timeout(1500)
            return None
        btns = [b for b in snap["buttons"] if not b["disabled"] and not AVOID.match(b["text"]) and not SOCIAL.search(b["text"])]
        pick = next((b for b in btns if APPLY_WORDS.match(b["text"]) or FINAL.match(b["text"]) or NEXT.match(b["text"])), None)
        if pick:
            self.press(snap, pick)
            return None
        if not snap["text"].strip() and not snap["fields"] and not snap["buttons"]:   # blank page (slow portal / failed script): wait, then reload once or twice
            self.blank = getattr(self, "blank", 0) + 1
            if self.blank in (2, 4):
                self.log("blank page: reloading")
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=40000)
                except Exception:  # noqa: BLE001
                    pass
            self.page.wait_for_timeout(3000)
            if self.blank < 10:
                return None
            return "needs_you", f"The page stayed blank ({snap['host']})"
        if same == 0:   # slow page: wait and look again
            self.page.wait_for_timeout(4000)
            return None
        self.log("buttons: " + " | ".join(b["text"][:25] for b in snap["buttons"][:12]))
        r = self.ai_step(snap, "unknown")
        if r == "acted":
            return None
        if r:
            return r
        return "needs_you", f"Unfamiliar page ({snap['title'][:60]}); buttons: " + ", ".join(b["text"][:20] for b in snap["buttons"][:8])

    def _press(self, snap: dict, rx: re.Pattern) -> tuple[str, str] | None:
        btn = None
        for b in snap["buttons"]:
            if b["disabled"] or SOCIAL.search(b["text"]) or AVOID.match(b["text"]):
                continue
            if rx.search(b["text"]):
                if not b["link"] or b.get("primary"):
                    btn = b
                    break
                btn = btn or b
        if not btn:
            self.page.keyboard.press("Enter")
            return None
        act.click(self.page, locate(snap, btn["id"]))
        self.settle(700)
        return None
