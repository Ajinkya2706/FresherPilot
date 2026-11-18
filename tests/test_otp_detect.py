"""OTP detector fixtures (python -m tests.test_otp_detect). Wording-independent: every new wording that slipped through becomes a case."""
import sys
sys.path.insert(0, "github_reader")
from applybot.otp_detect import detect, is_otp  # noqa: E402

POS = [  # (name, subject, body, sender, expected code)
    ("taleo mfa (real wording, Nov 18)", "Multifactor authentication access code", "To better secure your account with UnitedHealth Group, multifactor authentication is enabled. Please use the following access code to log in to your account." + chr(10)*2 + "618204" + chr(10)*2 + "Thank You, Talent Acquisition. Please do not reply to this email.", "donotreply@recruiting.taleo.net", "618204"),
    ("owner's wording", "Welcome", "Thanks for opening the website, your 6 digit identifier is 482913", "hello@acme.com", "482913"),
    ("test mail", "Acme Careers: your verification code", "Hi,\n\nYour verification code is 731942.\n\nEnter this code to verify your email. It expires in 10 minutes.", "noreply@acme.com", "731942"),
    ("alone on line", "Sign in to Workday", "Use this code to sign in:\n\n284 193\n\nThis code will expire in 15 minutes. Do not share it.", "workday@myworkday.com", "284193"),
    ("otp word", "Your OTP", "OTP for your login is 5521. Valid for 5 minutes. Do not share with anyone.", "alerts@portal.in", "5521"),
    ("greenhouse alnum", "Security code for your application", "Copy and paste this code into the security code field on your application: xK29Lm4Q\nAfter you enter the code, resubmit your application.", "no-reply@us.greenhouse-mail.io", "xK29Lm4Q"),
    ("pin wording", "Confirm it's you", "Your one-time PIN is 903318. We will never ask you for it.", "security@x.com", "903318"),
    ("passcode", "Candidate portal", "Passcode: 77281904 (expires in 10 min)", "donotreply@successfactors.com", "77281904"),
    ("token wording", "Almost there", "Here is your access token 118204 to finish creating your account. If you didn't request this, ignore this email.", "accounts@lever.co", "118204"),
]
NEG = [  # (name, subject, body, sender, headers)
    ("newsletter", "Top 10 jobs this week", "Hi! 2026 hiring trends: 45% growth. Apply to 1200 jobs now. Unsubscribe | View in browser", "news@jobs.com", {"List-Unsubscribe": "<x>"}),
    ("invoice", "Your invoice 482913", "Invoice number 482913 for order 55512. Total Rs 4500. Thank you for shopping with us.", "billing@shop.com", {}),
    ("address", "Delivery update", "Delivered to Flat 4, Pune pin code 411038. Thanks!", "orders@shop.com", {}),
    ("phone", "Call us", "Call +91 98765 43210 for support. Our office address is Baner, Pune.", "hello@acme.com", {}),
    ("plain hello", "Meeting tomorrow", "Hi, can we meet at 4:30 tomorrow? Room 204. Thanks.", "friend@gmail.com", {}),
    ("promo with number", "Flat 50% off", "Use coupon SAVE50 and get 50% off. Sale ends 30 Nov 2026. Unsubscribe here.", "promo@brand.com", {"Precedence": "bulk"}),
]
bad = 0
for name, subj, body, snd, want in POS:
    r = detect(subj, body, "", snd)
    if not (is_otp(r) and r["code"] == want):
        bad += 1; print("FAIL +", name, r)
for name, subj, body, snd, hdr in NEG:
    r = detect(subj, body, "", snd, hdr)
    if is_otp(r):
        bad += 1; print("FAIL -", name, r)
# html: code in bold only
h = '<p>Thanks for visiting.</p><p>Your identifier:</p><p style="font-size:32px;letter-spacing:6px"><b>615207</b></p><p>Valid for 10 minutes.</p>'
r = detect("Welcome to Acme", "", h, "hello@acme.com")
if not (is_otp(r) and r["code"] == "615207"):
    bad += 1; print("FAIL html", r)
print(f"{len(POS) + len(NEG) + 1 - bad}/{len(POS) + len(NEG) + 1} otp detector fixtures ok")
sys.exit(1 if bad else 0)
