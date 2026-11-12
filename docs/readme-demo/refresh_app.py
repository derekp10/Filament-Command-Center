"""Copy FCC's code from this repo into the README demo's own app/ folder (git-ignored).

Usage (from anywhere):  python docs/readme-demo/refresh_app.py [repo root]
Then restart the demo's FCC so it runs the new code:  docker restart fcc_readme_demo

- Copies every file git tracks under inventory-hub/, except data/ and tests/, so nothing
  untracked (a log, a scratch file, a real backup) reaches the demo.
- The demo keeps its own made-up places in app/data/: written once from
  locations.seed.json when app/data/locations.json is missing, never overwritten.
- Copies setup-and-rebuild/setup_fields.py beside it, for Spoolman's extra fields.
It never reads or writes inventory-hub/data/ (dev's real places).
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parent.parent
APP = HERE / "app"

listed = subprocess.run(["git", "ls-files", "-z", "inventory-hub"], cwd=REPO,
                        capture_output=True, check=True).stdout.decode("utf-8").split("\0")
copied = 0
for rel in filter(None, listed):
    parts = Path(rel).parts                      # ('inventory-hub', ...)
    if len(parts) < 2 or parts[1] in ("data", "tests"):
        continue
    dst = APP.joinpath(*parts[1:])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / rel, dst)
    copied += 1
if copied < 20:
    sys.exit(f"only {copied} files copied from {REPO}: is that the repo root?")

(APP / "data").mkdir(parents=True, exist_ok=True)
places = APP / "data" / "locations.json"
if not places.exists():
    shutil.copy2(HERE / "locations.seed.json", places)
    print("made-up places written to", places)

setup = HERE / "setup-and-rebuild"
setup.mkdir(exist_ok=True)
shutil.copy2(REPO / "setup-and-rebuild" / "setup_fields.py", setup / "setup_fields.py")
print(f"copied {copied} files into {APP}; restart the demo's FCC: docker restart fcc_readme_demo")
