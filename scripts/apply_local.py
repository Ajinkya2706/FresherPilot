"""Run the local auto-apply runner:  python -m scripts.apply_local [--login] [--once] [--dry]   (see github_reader/applybot/local.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "github_reader"))
from applybot.local import main

if __name__ == "__main__":
    sys.exit(main())
