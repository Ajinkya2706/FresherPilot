"""Page-classifier fixtures from real captures (run: python -m tests.test_applybot_classify). Snapshots are tiny hand-made dicts
with the text of pages seen live; every production failure that was a wrong classification becomes one more case here."""
import sys
sys.path.insert(0, "github_reader")
from applybot.classify import classify  # noqa: E402


def snap(text, buttons=(), fields=(), url="https://x.example/", headings=(), title=""):
    return {"title": title, "text": text, "url": url, "headings": list(headings), "captcha": False, "dialog": False,
            "fields": list(fields), "buttons": [{"text": b, "disabled": False, "link": False} for b in buttons], "errors": []}


CASES = [
    ("SmartRecruiters bot block (2026-11-18)", snap("Access is temporarily restricted We detected unusual activity from your device or network. Reasons may include: Rapid taps", ["Submit feedback."]), "blocked"),
    ("Indeed Cloudflare (2026-11-18)", snap("Additional Verification Required Your Ray ID for this request is abc Verify you are human", ["Return home"]), "blocked"),
    ("Workday removed job (2026-11-18)", snap("English Sign In Search for Jobs The page you are looking for doesn't exist. Search for Jobs", ["English Sign In", "Sign In", "Search for Jobs"]), "closed"),
    ("SmartRecruiters job page", snap("Associate Software Test Engineer Pune Job Description", ["I'm interested", "Privacy Notice"]), "job_detail"),
    ("Wipro/Taleo sign-in page that also offers New user (2026-11-18)", snap("Career Opportunities: Sign In Returning user Email Password New user? Create an account", ["Sign In", "Create an account"], fields=[{"kind": "email", "label": "Email", "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False}, {"kind": "password", "label": "Password", "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False}], headings=["Returning user", "New user"], title="Career Opportunities: Sign In"), "signin"),
    ("Real create-account page stays create_account", snap("Create an Account Email Password Confirm password", ["Create Account"], fields=[{"kind": "email", "label": "Email", "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False}, {"kind": "password", "label": "Password", "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False}, {"kind": "password", "label": "Confirm password", "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False}], headings=["Create an Account"], title="Career Opportunities: Create an Account"), "create_account"),
    ("Micron application form must not read as already applied (2026-11-18)", snap("Application Form Email First name Last name Phone Country City Have you applied on any previous occasions for employment in any capacity with Micron? Are you at least 18 years old?", ["Cancel", "Read more"], fields=[{"kind": "text", "label": l, "name": "", "placeholder": "", "autocomplete": "", "maxlength": 0, "required": True, "disabled": False, "hidden": False} for l in ("Email", "First name", "Last name", "Phone", "City", "Country of Residence", "Expected CTC")], title="Submit application for Engineer, Data Science"), "form"),
]
bad = 0
for name, s, want in CASES:
    got = classify(s)
    if got != want:
        bad += 1
        print("FAIL", name, got, "!=", want)
print(f"{len(CASES) - bad}/{len(CASES)} classifier fixtures ok")
sys.exit(1 if bad else 0)
