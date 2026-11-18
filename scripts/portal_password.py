"""Print the password the auto-apply bot uses on a portal:  python -m scripts.portal_password careers.ibm.com
Same derivation as github_reader/applybot/cloud.py (HMAC of the host with APPLY_PW_SECRET from .env)."""
import base64, hashlib, hmac, sys
from dotenv import dotenv_values

from fresherpilot.core.users import ROOT
key = dotenv_values(ROOT / ".env").get("APPLY_PW_SECRET", "")
for host in sys.argv[1:]:
    d = hmac.new(key.encode(), host.lower().encode(), hashlib.sha256).digest()
    print(host, base64.urlsafe_b64encode(d).decode()[:12] + "aA1!")
