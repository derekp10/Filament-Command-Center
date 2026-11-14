#!/usr/bin/env python3
"""refresh_dev_from_prod.py: refresh dev's data from prod, and keep it repeatable (Group 45.6 / 45.7).

Agent-invoked, like reset_dev.py: Claude runs it. A person's only part is stopping and starting
the dev Spoolman app in TrueNAS when the swap asks for it.

WHAT IT REFRESHES
  - Dev Spoolman's database becomes a copy of prod's database FILE, so every spool keeps the
    number on Derek's labels (an API copy would renumber them).
  - Dev FCC's inventory-hub/data/locations.json becomes prod's, plus dev's own pieces.
  - config.json is out of scope (dev keeps its own; its Spoolman address must stay dev's).

PROD IS READ-ONLY, in code:
  - Every HTTP call goes through `http()`. It sends only GETs to prod Spoolman, only GETs to dev
    FCC, and refuses any address that isn't dev Spoolman, prod Spoolman or dev FCC.
  - Every file write goes through `_guard_write()`. It refuses any path on prod's TrueNAS share
    folders (App_Data\\Spoolman, App_Data\\InventoryHub, on any host name) and any path outside
    the stage folder, dev's inventory-hub/data/ and dev Spoolman's database file.
  - Prod's files are only ever opened for reading, and never with SQLite: the database is
    copied as bytes and the LOCAL copy is opened read-only.
  - No phase prints, logs or writes a printer login. Reports name the rows that carry one and
    say, true or false, whether prod's differ. (The dev-data backup is a byte copy of dev's own
    folder, logins included as dev's own files hold them; it stays on this PC.)

EVERY PHASE IS A DRY RUN unless --apply is given. Run them in this order:

   1. stage            dev Spoolman UP. Copies prod's spoolman.db and reads prod's locations.json
                       at the same moment (a stripped copy, no logins, goes to the stage folder),
                       and snapshots dev Spoolman's counts and max ids for the swap's identity
                       guard. Writes only in the stage folder.
   2. -- a person stops the dev Spoolman app in TrueNAS (never the prod one), right after
         `stage`: a write to dev in between (a test run) makes the swap's identity guard refuse --
   3. swap             dev Spoolman DOWN, prod UP. Refuses unless: dev doesn't answer and prod
                       does; dev FCC tracks no print (every printer IDLE in the latch, the fetch
                       queue empty); the target file, copied locally and opened read-only, has
                       exactly the counts and max ids of the stage snapshot (so it really is
                       dev's database). Then backs the target up, overwrites it IN PLACE with
                       shutil.copyfile (its owner and permissions on TrueNAS stay), and checks
                       the hash.
   4. -- a person starts the dev Spoolman app in TrueNAS --
   5. verify-spoolman  dev answers with prod's records, every vendor, filament and spool
                       (archived ones too), field by field. The test spool `fixtures` moved is
                       named as the one expected difference.
   6. locations        builds dev's locations.json from prod's rows (prod's order) and dev's
                       pieces, validates it (shape, ids, the test fleet, every boot migration at
                       its fixpoint), then with FCC stopped backs up dev's data folder, writes the
                       file atomically, empties the review cards and fetch queue (only while
                       every latch reads IDLE), starts FCC and checks its answers.
   7. fixtures         dev Spoolman only: exactly one stored, in-stock spool in the Quick-Swap
                       test box's slot (TST-MDB-1 slot 1), slots 2-6 empty; a direct PATCH while
                       FCC is stopped.
   8. count            45.7, read-only: in-stock spools whose physical_source is set while they
                       are not on a head, on prod's data and on dev's data before the refresh.
   9. seeds            retakes setup-and-rebuild/seeds/ from the refreshed dev through
                       reset_dev.py --capture (which never writes printer_creds) and checks them.
                       Don't commit the seeds without Derek's OK: they hold his real inventory.
      checklist        any time, read-only: the Bulk Move checklist's starting state on dev
                       (Feature-Buglist.md, PENDING DEREK).

DEV'S OWN PIECES (`locations`):
  - printer_creds: each row takes dev's current row's printer_creds (same LocationID), never
    prod's; a row dev has no login for gets none.
  - Blank-LocationID rows (prod's hand-made "Unknown Location") are dropped and named: two sweep
    reds come back with one (Group 46.5). Nothing is cascaded to spools.
  - The boxes in tests/conftest.py's DEV_BOX_BINDING_BASELINES are Dryer Boxes at exactly their
    baseline slot_targets ({} today); sibling extra keys stay, a box prod lacks comes from dev
    (else the committed seed), and every prod binding replaced is reported.
  - The CR-TC test carts, verbatim from dev (else the seed), unless prod has those ids.
  - Everything else is prod's (RCOI's parent_id included).

DEV'S FCC STATE: the review cards (pending_cancel_deducts.json) and the fetch queue are emptied
after the backup, because dev's spools now carry prod's charges and applying a dev-only card
would charge twice. The deduct ledger and the print latch stay.

ROLLBACK: Spoolman: stop the dev app, copy <stage>/dev-spoolman-before.db over dev's
spoolman.db the same way (shutil.copyfile), start it. FCC: docker stop inventory_hub, copy
<stage>/dev-data-before/* back into inventory-hub/data/, docker start inventory_hub. Seeds: git.

Runs on the host's Python (stdlib only). Read the TrueNAS share from PowerShell:
    & "C:/Python314/python.exe" -I -X utf8 setup-and-rebuild/refresh_dev_from_prod.py <phase> [--apply]
Env overrides: FCC_REFRESH_STAGE_DIR (or --stage-dir), DEV_SPOOLMAN_URL,
FCC_REFRESH_PROD_SPOOLMAN_URL, FCC_REFRESH_DEV_FCC_URL, INVENTORY_HUB_CONTAINER,
FCC_REFRESH_PROD_SPOOLMAN_DB, FCC_REFRESH_DEV_SPOOLMAN_DB, FCC_REFRESH_PROD_FCC_DATA_DIR,
FCC_REFRESH_DEV_DATA_DIR. Prod's share folders are refused whatever they are set to.
"""
from __future__ import annotations

import argparse
import ast
import copy
import datetime
import fnmatch
import hashlib
import json
import ntpath
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Paths, addresses and fixtures (constants; env overrides as in reset_dev.py)
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HUB_DIR = os.path.join(REPO_ROOT, "inventory-hub")
CONFTEST = os.path.join(HUB_DIR, "tests", "conftest.py")
LOCATIONS_DB_PY = os.path.join(HUB_DIR, "locations_db.py")
RESET_DEV = os.path.join(HERE, "reset_dev.py")
SEEDS_DIR = os.path.join(HERE, "seeds")
LOCATIONS_SEED = os.path.join(SEEDS_DIR, "locations-seed.json")
SPOOLMAN_SEED = os.path.join(SEEDS_DIR, "spoolman-dev-seed.json")
CONFIG_JSON = os.path.join(REPO_ROOT, "config.json")


def _env(name, default):
    value = os.environ.get(name)
    return value if value else default


PROD_SPOOLMAN_URL = _env("FCC_REFRESH_PROD_SPOOLMAN_URL", "http://192.168.1.29:7912").rstrip("/")
DEV_SPOOLMAN_URL = _env("DEV_SPOOLMAN_URL", "http://192.168.1.29:7913").rstrip("/")
DEV_FCC_URL = _env("FCC_REFRESH_DEV_FCC_URL", "http://localhost:8000").rstrip("/")
CONTAINER = _env("INVENTORY_HUB_CONTAINER", "inventory_hub")
PROD_SPOOLMAN_DB = _env("FCC_REFRESH_PROD_SPOOLMAN_DB",
                        r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db")
DEV_SPOOLMAN_DB = _env("FCC_REFRESH_DEV_SPOOLMAN_DB", r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db")
PROD_FCC_DATA_DIR = _env("FCC_REFRESH_PROD_FCC_DATA_DIR",
                         r"\\TRUENAS\App_Data\InventoryHub\inventory-hub\data")
DEV_DATA_DIR = _env("FCC_REFRESH_DEV_DATA_DIR", os.path.join(HUB_DIR, "data"))
STAGE_DIR = _env("FCC_REFRESH_STAGE_DIR",
                 os.path.join(REPO_ROOT, ".captures", "dev-refresh-" + datetime.date.today().isoformat()))

# Prod's share folders: never written, whatever the env says. Matched on any host name too.
PROD_SHARE_FOLDERS = (r"\\TRUENAS\App_Data\Spoolman", r"\\TRUENAS\App_Data\InventoryHub",
                      r"\\192.168.1.29\App_Data\Spoolman", r"\\192.168.1.29\App_Data\InventoryHub")
PROD_SHARE = "app_data"
PROD_SHARE_SUBFOLDERS = frozenset({"spoolman", "inventoryhub"})
# Prod Spoolman's addresses: GET only, whatever the env says.
PROD_NETLOCS = frozenset({"192.168.1.29:7912", "truenas:7912", "truenas.local:7912"})

CREDS = "printer_creds"
LATCH_FILE = "print_tracker_latch.json"
PENDING_FILES = ("pending_cancel_deducts.json", "pending_cancel_fetches.json")
BACKUP_SKIP = ("val_*.gcode",)       # large print captures that never change
STAGED_PROD_DB = "prod-spoolman.db"
DEV_DB_BACKUP = "dev-spoolman-before.db"
STAGE_REPORT = "stage-report.json"
PROD_LOCATIONS_AS_READ = "prod-locations-as-read.json"     # prod's rows, logins stripped
DEV_DATA_BACKUP = "dev-data-before"

# The Quick-Swap pictures pin this spool's line (tests/test_quickswap_visual.py). The box and
# slot come from tests/conftest.py (QUICKSWAP_TEST_BOX / _SLOT).
FIXTURE_SPOOL = 123
FIXTURE_LABEL = "#123 [Legacy: 112] Jayo PLA (White)"
FIXTURE_EXTRAS = ("container_slot", "physical_source", "physical_source_slot", "fcc_pre_box_location")
# Dev-only test carts (Derek's manual Bulk Move pass uses them as empty destinations).
TEST_CARTS = ("CR-TC-1", "CR-TC-R1", "CR-TC-2", "CR-TC-2-R1", "CR-TC-2-R2", "CR-TC-2-R3")
# The printer fleet the tests name. XL's display Name is part of an API path in the tests.
FLEET = (("XL", tuple("XL-%d" % i for i in range(1, 6))),
         ("RCOI", tuple("RCOI-%d" % i for i in range(1, 9))))
NAME_MUST_STAY = ("XL",)
# The Bulk Move checklist's places (Feature-Buglist.md, PENDING DEREK): sources, then the empty
# destinations it uses.
CHECKLIST_SOURCES = ("CR-CT-2-R3", "CR-CT-2-R1", "LR-MDB-2", "CR-MDB-1", "LR-MDB-1")
CHECKLIST_EMPTY = ("CR-TC-2-R1", "CR-TC-2-R2")
SPOOLS_TESTS_NAME = (1, 2)       # the weigh-out tests scan these ids
NOT_A_ROW = ("", "UNASSIGNED", "UNKNOWN")


class Refused(Exception):
    """A guard said no. Its message says why. Nothing after the guard ran."""


def _say(msg=""):
    print(msg, flush=True)


# --------------------------------------------------------------------------
# Guard (a): prod is read-only, for files
# --------------------------------------------------------------------------
def _norm_path(path):
    """A path in one comparable spelling, by Windows rules on any OS (the share is SMB): back
    slashes, case folded, '..' resolved."""
    p = str(path).replace("/", "\\")
    if not p.startswith("\\\\"):
        p = os.path.abspath(str(path)).replace("/", "\\")
    return ntpath.normcase(ntpath.normpath(p))


def _is_under(path_n, folder_n):
    folder_n = folder_n.rstrip("\\")
    return path_n == folder_n or path_n.startswith(folder_n + "\\")


def _prod_folders():
    folders = list(PROD_SHARE_FOLDERS) + [os.path.dirname(PROD_SPOOLMAN_DB), PROD_FCC_DATA_DIR]
    return [_norm_path(f) for f in folders if f]


def is_prod_path(path):
    """True for any path on prod's share folders (on any host name, any spelling)."""
    n = _norm_path(path)
    if any(_is_under(n, f) for f in _prod_folders()):
        return True
    if n.startswith("\\\\"):
        parts = n.lstrip("\\").split("\\")
        if len(parts) >= 3 and parts[1] == PROD_SHARE and parts[2] in PROD_SHARE_SUBFOLDERS:
            return True
    return False


def _guard_write(path):
    """Every write goes through here. Prod's share: never. Anything else: only the stage folder,
    dev's data folder, or dev Spoolman's database file itself."""
    if is_prod_path(path):
        raise Refused("refusing to write %s: it is on prod's share, which is read-only" % path)
    n = _norm_path(path)
    if is_prod_path(DEV_SPOOLMAN_DB):
        raise Refused("FCC_REFRESH_DEV_SPOOLMAN_DB points at prod's share (%s)" % DEV_SPOOLMAN_DB)
    if n == _norm_path(DEV_SPOOLMAN_DB):
        return
    if any(_is_under(n, _norm_path(d)) for d in (STAGE_DIR, DEV_DATA_DIR)):
        return
    raise Refused("refusing to write %s: outside the stage folder (%s), dev's data folder (%s) "
                  "and dev Spoolman's database" % (path, STAGE_DIR, DEV_DATA_DIR))


def _makedirs(path):
    _guard_write(os.path.join(path, "_"))
    os.makedirs(path, exist_ok=True)


def _write_text_atomic(path, text):
    """Temp file in the same folder, fsync, os.replace. '\\n' line ends, as FCC writes them."""
    _guard_write(path)
    folder = os.path.dirname(os.path.abspath(path))
    _makedirs(folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".refresh-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _write_json(path, data, indent=2):
    _write_text_atomic(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")


def _copy_keep_times(src, dst):
    """A backup copy (shutil.copy2 keeps the mtime)."""
    _guard_write(dst)
    shutil.copy2(src, dst)


def _copy_in_place(src, dst):
    """shutil.copyfile truncates and rewrites dst, so its owner and permissions stay."""
    _guard_write(dst)
    shutil.copyfile(src, dst)


def _rmtree(path):
    _guard_write(os.path.join(path, "_"))
    shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------
# Guard (a): prod is read-only, for HTTP
# --------------------------------------------------------------------------
def _netloc(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def _prod_netlocs():
    return set(PROD_NETLOCS) | {_netloc(PROD_SPOOLMAN_URL)}


def http(method, url, payload=None, timeout=30):
    """The one HTTP helper. Returns (status, json_or_None, text, headers); a connection that
    fails raises (urllib.error.URLError / OSError)."""
    method = method.upper()
    loc = _netloc(url)
    if loc in _prod_netlocs():
        if method != "GET":
            raise Refused("refusing %s %s: prod Spoolman is read-only" % (method, url))
    elif loc == _netloc(DEV_FCC_URL):
        if method != "GET":
            raise Refused("refusing %s %s: this script only reads dev FCC" % (method, url))
    elif loc != _netloc(DEV_SPOOLMAN_URL):
        raise Refused("refusing %s %s: not dev Spoolman, prod Spoolman or dev FCC" % (method, url))
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, body, hdrs = resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        status, body, hdrs = exc.code, exc.read(), dict(exc.headers or {})
    text = body.decode("utf-8", "replace")
    try:
        parsed = json.loads(text) if text else None
    except ValueError:
        parsed = None
    return status, parsed, text, hdrs


def get_json(url, timeout=60):
    status, parsed, text, _ = http("GET", url, timeout=timeout)
    if status != 200 or parsed is None:
        raise Refused("GET %s answered HTTP %s: %s" % (url, status, text[:200]))
    return parsed


def spoolman_answers(base, timeout=5):
    """(True, 'Spoolman 0.27.1') when base answers Spoolman's info; else (False, why)."""
    try:
        status, parsed, _, _ = http("GET", base + "/api/v1/info", timeout=timeout)
    except (urllib.error.URLError, OSError, socket.timeout) as exc:
        return False, "no answer (%s)" % type(getattr(exc, "reason", exc)).__name__
    if status == 200 and isinstance(parsed, dict) and parsed.get("version"):
        return True, "Spoolman %s" % parsed.get("version")
    return False, "HTTP %s, not Spoolman's info" % status


def spoolman_info(base):
    return get_json(base + "/api/v1/info", timeout=15)


def spoolman_lists(base):
    """Every vendor, filament and spool (archived spools included)."""
    return {"vendor": get_json(base + "/api/v1/vendor"),
            "filament": get_json(base + "/api/v1/filament"),
            "spool": get_json(base + "/api/v1/spool?allow_archived=true")}


def identity_from_lists(lists):
    out = {}
    for kind in ("vendor", "filament", "spool"):
        ids = [r.get("id") for r in lists[kind] if isinstance(r, dict) and isinstance(r.get("id"), int)]
        out[kind] = {"count": len(lists[kind]), "max_id": max(ids) if ids else None}
    return out


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def stage_path(name):
    return os.path.join(STAGE_DIR, name)


def dev_path(name):
    return os.path.join(DEV_DATA_DIR, name)


def _lid(row):
    return str(row.get("LocationID") or "").strip() if isinstance(row, dict) else ""


def _norm_loc(value):
    """A location id as FCC compares it: trimmed, quotes stripped, upper case."""
    return str(value or "").strip().strip('"').strip().upper()


def strip_creds(rows):
    """A copy of a locations list with no printer_creds on any row."""
    if not isinstance(rows, list):
        return rows
    return [{k: v for k, v in r.items() if k != CREDS} if isinstance(r, dict) else r for r in rows]


def normalized_slot_targets(slot_targets):
    """conftest._normalized_slot_targets: string keys, blank / None values dropped."""
    if not isinstance(slot_targets, dict):
        return {}
    return {str(k): str(v) for k, v in slot_targets.items() if v is not None and str(v).strip() != ""}


def decode_extra(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def trail_of(extra):
    """(physical_source, physical_source_slot) as FCC reads them: '' when unset."""
    extra = extra if isinstance(extra, dict) else {}
    src = decode_extra(extra.get("physical_source"))
    slot = decode_extra(extra.get("physical_source_slot"))
    src = "" if src in (None, "") else _norm_loc(src)
    slot = "" if slot in (None, "") else str(slot).strip().strip('"').strip()
    return src, slot


def slot_of(extra):
    extra = extra if isinstance(extra, dict) else {}
    value = decode_extra(extra.get("container_slot"))
    return "" if value in (None, "") else str(value).strip().strip('"').strip()


def _parse_inbound(spool):
    """spoolman_api.parse_inbound_data: every extra JSON-decoded, the spool's and its filament's
    (so an original_color stored as '"Silver"' reads Silver, as FCC shows it)."""
    spool = copy.deepcopy(spool)
    fil = spool.get("filament")
    for rec in (spool, fil if isinstance(fil, dict) else None):
        if isinstance(rec, dict) and isinstance(rec.get("extra"), dict):
            for key, value in list(rec["extra"].items()):
                if isinstance(value, str):
                    try:
                        rec["extra"][key] = json.loads(value)
                    except ValueError:
                        pass
    return spool


def spool_display(spool):
    """spoolman_api.format_spool_display's text, line for line, on the record as FCC parses it
    ("#123 [Legacy: 112] Jayo PLA (White)"): the line the Quick-Swap card and its confirm show."""
    try:
        spool = _parse_inbound(spool)
        sid = spool.get("id", "?")
        ext_id = str(spool.get("external_id", "")).replace('"', "").strip()
        if not ext_id or ext_id.lower() == "none":
            fil_data = spool.get("filament", {})
            ext_id = str(fil_data.get("external_id", "")).replace('"', "").strip()
            if ext_id.lower() == "none":
                ext_id = ""
        fil = spool.get("filament")
        if not fil:
            return "#%s [No Filament Data]" % sid
        vendor = fil.get("vendor")
        brand = str(vendor.get("name", "Generic") if vendor else "Generic").strip()
        mat = str(fil.get("material", "PLA")).strip().upper()
        fil_extra = fil.get("extra") or {}
        col_name = fil_extra.get("original_color")
        if not col_name:
            col_name = fil.get("name", "Unknown")
        if col_name:
            col_name = str(col_name).strip().title()
        parts = ["#%s" % sid]
        if ext_id:
            parts.append("[Legacy: %s]" % ext_id)
        parts.extend([brand, mat, "(%s)" % col_name])
        return " ".join(parts)
    except Exception:  # noqa: BLE001 - the original falls back the same way
        return "#%s Error" % spool.get("id", "?")


# --------------------------------------------------------------------------
# What the backend and the tests define (read from source, never imported in-process: importing
# a backend module here would open hub.log in the working directory)
# --------------------------------------------------------------------------
def _module_assignments(path, names):
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Refused("%s doesn't parse right now (%s); try again in a moment" % (path, exc))
    found = {}
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target.id], node.value
        elif isinstance(node, ast.Assign):
            targets, value = [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
        for name in targets:
            if name in names and value is not None:
                if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                        and value.func.id in ("frozenset", "set") and len(value.args) == 1):
                    value = value.args[0]
                found[name] = ast.literal_eval(value)
    missing = sorted(set(names) - set(found))
    if missing:
        raise Refused("%s defines no %s" % (path, ", ".join(missing)))
    return found


def conftest_constants():
    names = ("DEV_BOX_BINDING_BASELINES", "QUICKSWAP_TEST_BOX", "QUICKSWAP_TEST_SLOT")
    found = _module_assignments(CONFTEST, names)
    return {"baselines": {str(k): dict(v) for k, v in found["DEV_BOX_BINDING_BASELINES"].items()},
            "box": str(found["QUICKSWAP_TEST_BOX"]), "slot": str(found["QUICKSWAP_TEST_SLOT"])}


def backend_constants():
    found = _module_assignments(LOCATIONS_DB_PY, ("TOOLHEAD_TYPES", "PSEUDO_ROOM_PREFIXES"))
    return {"toolhead_types": frozenset(found["TOOLHEAD_TYPES"]),
            "pseudo_rooms": frozenset(found["PSEUDO_ROOM_PREFIXES"])}


# --------------------------------------------------------------------------
# Places: which location is a head (the move engine's one-spool rule)
# --------------------------------------------------------------------------
class Places:
    """A locations list read the way FCC classifies its rows."""

    def __init__(self, rows, toolhead_types):
        self.rows = rows if isinstance(rows, list) else []
        self.by_id = {}
        for r in self.rows:
            if isinstance(r, dict) and _norm_loc(r.get("LocationID")) and _norm_loc(r.get("LocationID")) not in self.by_id:
                self.by_id[_norm_loc(r.get("LocationID"))] = r
        self.toolhead_types = toolhead_types
        self.printer_heads = set()
        for r in self.rows:
            if isinstance(r, dict) and str(r.get("Type", "")).strip() == "Printer":
                for t in (r.get("toolheads") or []):
                    if isinstance(t, dict) and _norm_loc(t.get("location_id")):
                        self.printer_heads.add(_norm_loc(t.get("location_id")))

    def type_of(self, loc):
        row = self.by_id.get(_norm_loc(loc))
        return str(row.get("Type", "")).strip() if isinstance(row, dict) else None

    def is_head(self, loc):
        """(a) a printer_map key; (b) a row whose Type is a toolhead Type; (c) a Printer row that
        owns no head but itself, Max Spools <= 1 (a dual-role printer). XL / RCOI are not heads."""
        lid = _norm_loc(loc)
        if not lid:
            return False
        if lid in self.printer_heads:
            return True
        row = self.by_id.get(lid)
        if not isinstance(row, dict):
            return False
        kind = str(row.get("Type", "")).strip()
        if kind in self.toolhead_types:
            return True
        if kind != "Printer":
            return False
        own = [_norm_loc(x.get("location_id")) for x in (row.get("toolheads") or []) if isinstance(x, dict)]
        try:
            one = int(str(row.get("Max Spools", "0")).strip() or "0") <= 1
        except ValueError:
            one = True
        return one and not any(h and h != lid for h in own)

    def max_spools(self, loc):
        row = self.by_id.get(_norm_loc(loc))
        try:
            return int(str((row or {}).get("Max Spools", "")).strip())
        except ValueError:
            return None

    def place_kind(self, loc):
        lid = _norm_loc(loc)
        if lid in ("", "UNASSIGNED"):
            return "(unassigned)"
        if lid == "UNKNOWN":
            return "UNKNOWN"
        return self.type_of(lid) or "(no row)"


# --------------------------------------------------------------------------
# Spool lists from Spoolman's API or from a database FILE (a local copy, read-only)
# --------------------------------------------------------------------------
def _sqlite_ro(path):
    uri = "file:" + urllib.request.pathname2url(os.path.abspath(path)) + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def identity_from_db(path):
    con = _sqlite_ro(path)
    try:
        out = {}
        for kind in ("vendor", "filament", "spool"):
            count, max_id = con.execute('SELECT COUNT(*), MAX(id) FROM "%s"' % kind).fetchone()
            out[kind] = {"count": count, "max_id": max_id}
        return out
    finally:
        con.close()


def spools_from_db(path):
    """Spool records shaped like the API's for what the count reads: id, location, archived,
    extra (each value the raw JSON text Spoolman stores, the same text its API returns)."""
    con = _sqlite_ro(path)
    try:
        spools = {}
        for sid, location, archived in con.execute("SELECT id, location, archived FROM spool"):
            spools[sid] = {"id": sid, "location": location or "", "archived": bool(archived), "extra": {}}
        for sid, key, value in con.execute("SELECT spool_id, key, value FROM spool_field"):
            if sid in spools:
                spools[sid]["extra"][key] = value
        return [spools[k] for k in sorted(spools)]
    finally:
        con.close()


def db_report(path):
    """Integrity, journal mode, every table's rows and max id, AUTOINCREMENT, alembic head."""
    con = _sqlite_ro(path)
    try:
        rep = {"integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
               "journal_mode": con.execute("PRAGMA journal_mode").fetchone()[0]}
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rep["tables"] = {}
        for t in tables:
            cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % t)]
            rows = con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
            max_id = con.execute('SELECT MAX(id) FROM "%s"' % t).fetchone()[0] if "id" in cols else None
            rep["tables"][t] = {"rows": rows, "max_id": max_id}
        ddl = {r[0]: r[1] for r in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('spool','filament','vendor')")}
        rep["autoincrement"] = {k: "AUTOINCREMENT" in (v or "").upper() for k, v in ddl.items()}
        rep["alembic"] = ([r[0] for r in con.execute("SELECT version_num FROM alembic_version")]
                          if "alembic_version" in tables else None)
        return rep
    finally:
        con.close()


def side_files(db_path):
    """spoolman.db-journal / -wal / -shm beside a database: a write in progress or cut off."""
    folder, base = os.path.split(db_path)
    return sorted(n for n in os.listdir(folder) if n.startswith(base) and n != base)


# --------------------------------------------------------------------------
# Guard (c): dev FCC isn't tracking a print
# --------------------------------------------------------------------------
def latch_state():
    """(idle, detail). Idle when every printer in dev's print latch reads IDLE."""
    path = dev_path(LATCH_FILE)
    try:
        data = load_json(path)
    except FileNotFoundError:
        return True, "no latch file (FCC has tracked nothing)"
    except (ValueError, OSError) as exc:
        return False, "couldn't read %s (%s)" % (path, exc)
    if not isinstance(data, dict):
        return False, "%s isn't a JSON object" % path
    busy = {}
    for name, entry in data.items():
        state = str((entry or {}).get("state", "") if isinstance(entry, dict) else "").upper()
        if state != "IDLE":
            busy[name] = state or "(blank)"
    if busy:
        return False, "not IDLE: " + ", ".join("%s=%s" % kv for kv in sorted(busy.items()))
    return True, "%d printer(s), all IDLE" % len(data)


def fetch_queue_state():
    path = dev_path("pending_cancel_fetches.json")
    try:
        data = load_json(path)
    except FileNotFoundError:
        return True, "no fetch queue file"
    except (ValueError, OSError) as exc:
        return False, "couldn't read %s (%s)" % (path, exc)
    if isinstance(data, dict) and not data:
        return True, "empty"
    return False, "%d queued print download(s)" % (len(data) if isinstance(data, dict) else -1)


def review_cards():
    try:
        data = load_json(dev_path("pending_cancel_deducts.json"))
    except (FileNotFoundError, ValueError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    return [{"key": k, "kind": (v or {}).get("kind"), "job_id": (v or {}).get("job_id"),
             "total_grams": (v or {}).get("total_grams")} for k, v in data.items()]


# --------------------------------------------------------------------------
# Docker and dev FCC
# --------------------------------------------------------------------------
def docker(*args, timeout=120):
    proc = subprocess.run(["docker"] + list(args), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise Refused("docker %s failed: %s" % (" ".join(args), (proc.stderr or proc.stdout).strip()[:300]))
    return proc.stdout.strip()


def container_running():
    try:
        return docker("inspect", "-f", "{{.State.Running}}", CONTAINER, timeout=30) == "true"
    except Refused:
        return False


def wait_for_fcc(timeout=240):
    """Poll GET /api/locations until it answers a list."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            status, parsed, _, _ = http("GET", DEV_FCC_URL + "/api/locations", timeout=10)
            if status == 200 and isinstance(parsed, list):
                return True
            last = "HTTP %s" % status
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise Refused("dev FCC didn't answer /api/locations within %d s (last: %s)" % (timeout, last))


def fcc_get(path, timeout=30, tries=15):
    """GET from dev FCC, retried while the Werkzeug reloader restarts it."""
    last = None
    for _ in range(tries):
        try:
            return http("GET", DEV_FCC_URL + path, timeout=timeout)
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            last = exc
            time.sleep(2)
    raise Refused("dev FCC didn't answer GET %s (%s)" % (path, last))


class FccStopped:
    """docker stop on enter, docker start on exit (always, so a failure never leaves dev FCC down)."""

    def __init__(self):
        self.was_running = None

    def __enter__(self):
        self.was_running = container_running()
        _say("  docker stop %s (it was %s)" % (CONTAINER, "running" if self.was_running else "not running"))
        docker("stop", CONTAINER)
        return self

    def __exit__(self, exc_type, exc, tb):
        _say("  docker start %s" % CONTAINER)
        try:
            docker("start", CONTAINER)
        except Refused as start_err:
            _say("  !! %s" % start_err)
            if exc is None:
                raise
        return False


# --------------------------------------------------------------------------
# Prod reads (read-only, the share)
# --------------------------------------------------------------------------
def read_prod_file(path):
    """Read a prod file as bytes, refusing if it changed while it was read."""
    st0 = os.stat(path)
    with open(path, "rb") as fh:
        raw = fh.read()
    st1 = os.stat(path)
    if (st0.st_size, st0.st_mtime) != (st1.st_size, st1.st_mtime):
        raise Refused("%s changed while it was read; run again" % path)
    return raw, {"path": path, "size": st1.st_size, "mtime": _iso(st1.st_mtime),
                 "sha256": hashlib.sha256(raw).hexdigest()}


def read_prod_locations():
    raw, meta = read_prod_file(os.path.join(PROD_FCC_DATA_DIR, "locations.json"))
    rows = json.loads(raw.decode("utf-8"))
    meta["rows"] = len(rows) if isinstance(rows, list) else None
    return rows, meta


def prod_data_listing():
    try:
        return sorted(os.listdir(PROD_FCC_DATA_DIR)), None
    except OSError as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def prod_hidden_choices():
    path = os.path.join(PROD_FCC_DATA_DIR, "attr_hidden_choices.json")
    if not os.path.exists(path):
        return None
    raw, meta = read_prod_file(path)
    try:
        meta["content"] = json.loads(raw.decode("utf-8"))
    except ValueError:
        meta["content"] = "(not JSON)"
    return meta


def prod_db_stat():
    st = os.stat(PROD_SPOOLMAN_DB)
    return {"size": st.st_size, "mtime": _iso(st.st_mtime), "side_files": side_files(PROD_SPOOLMAN_DB)}


def load_stage_report(required=True):
    path = stage_path(STAGE_REPORT)
    if not os.path.exists(path):
        if required:
            raise Refused("no %s: run `stage` first (stage folder %s)" % (STAGE_REPORT, STAGE_DIR))
        return {}
    return load_json(path)


# --------------------------------------------------------------------------
# Phase: stage
# --------------------------------------------------------------------------
def phase_stage(args):
    rep = {"at": _now(), "stage_dir": STAGE_DIR}
    keep = ("version", "db_type", "data_dir", "backups_dir", "automatic_backups", "debug_mode")
    prod_info, dev_info = spoolman_info(PROD_SPOOLMAN_URL), spoolman_info(DEV_SPOOLMAN_URL)
    rep["prod_info"] = {k: prod_info.get(k) for k in keep}
    rep["dev_info"] = {k: dev_info.get(k) for k in keep}
    _say("prod Spoolman: %s" % rep["prod_info"])
    _say("dev  Spoolman: %s" % rep["dev_info"])
    if prod_info.get("version") != dev_info.get("version"):
        raise Refused("prod and dev run different Spoolman versions; a database copy needs the same one")
    if str(prod_info.get("db_type", "")).lower() != "sqlite":
        raise Refused("prod's database isn't SQLite")
    dest = stage_path(STAGED_PROD_DB)
    if os.path.exists(dest):
        raise Refused("%s already exists: this folder has been staged; use a new --stage-dir" % dest)
    side = side_files(PROD_SPOOLMAN_DB)
    if side:
        raise Refused("prod has a write in progress (side files: %s)" % side)

    lists = spoolman_lists(DEV_SPOOLMAN_URL)
    rep["dev_identity"] = identity_from_lists(lists)
    _say("dev identity (the swap's guard): %s" % rep["dev_identity"])
    prod_rows, rep["prod_locations"] = read_prod_locations()
    rep["prod_data_listing"], listing_err = prod_data_listing()
    hidden = prod_hidden_choices()
    rep["prod_hidden_choices"] = None if hidden is None else {k: v for k, v in hidden.items() if k != "content"}
    _say("prod locations.json: %s rows, mtime %s" % (rep["prod_locations"]["rows"], rep["prod_locations"]["mtime"]))
    _say("prod data folder: %s" % (rep["prod_data_listing"] if listing_err is None else listing_err))
    if not args.apply:
        _say("\nDRY RUN: would copy %s to %s, check it with SQLite and save the stage report, "
             "prod's locations (no logins) and the dev identity snapshot. Nothing written." % (PROD_SPOOLMAN_DB, dest))
        return 0

    _makedirs(STAGE_DIR)
    st0 = os.stat(PROD_SPOOLMAN_DB)
    _guard_write(dest)
    shutil.copyfile(PROD_SPOOLMAN_DB, dest)        # read from prod, written locally
    st1 = os.stat(PROD_SPOOLMAN_DB)
    if (st0.st_size, st0.st_mtime) != (st1.st_size, st1.st_mtime) or side_files(PROD_SPOOLMAN_DB):
        os.remove(dest)
        raise Refused("prod's database changed during the copy; run stage again")
    rep["prod_db"] = {"size": st1.st_size, "mtime": _iso(st1.st_mtime), "sha256": sha256_file(dest)}
    rep.update(db_report(dest))
    api = {"vendor": len(get_json(PROD_SPOOLMAN_URL + "/api/v1/vendor")),
           "filament": len(get_json(PROD_SPOOLMAN_URL + "/api/v1/filament")),
           "spool": len(get_json(PROD_SPOOLMAN_URL + "/api/v1/spool?allow_archived=true"))}
    rep["prod_api_counts"] = api
    rep["counts_match"] = api == {k: rep["tables"].get(k, {}).get("rows") for k in api}
    _write_json(stage_path("prod-locations-at-stage.json"), strip_creds(prod_rows), indent=4)
    if hidden is not None:
        _write_json(stage_path("prod-attr_hidden_choices.json"), hidden.get("content"))
    _write_json(stage_path(STAGE_REPORT), rep)
    _say("copied prod db: %s | integrity %s | counts match the API: %s"
         % (rep["prod_db"], rep["integrity"], rep["counts_match"]))
    _say("stage report: %s" % stage_path(STAGE_REPORT))
    _say("\nNEXT: stop the dev Spoolman app in TrueNAS (NOT prod's), then run `swap --apply`.")
    return 0 if rep["integrity"] == "ok" and rep["counts_match"] else 4


# --------------------------------------------------------------------------
# Phase: swap (guards b and c)
# --------------------------------------------------------------------------
def check_target_identity(snapshot):
    """Guard (b): copy dev's database file locally, open THAT read-only, and compare its counts and
    max ids with the snapshot of dev's API. Returns (ok, identity_of_the_file)."""
    work = stage_path(".tmp-swap-%d" % os.getpid())
    _makedirs(work)
    try:
        local = os.path.join(work, "target.db")
        _guard_write(local)
        shutil.copyfile(DEV_SPOOLMAN_DB, local)      # read from the share, written locally
        ident = identity_from_db(local)
    finally:
        _rmtree(work)
    return ident == snapshot, ident


def phase_swap(args):
    rep = load_stage_report()
    staged = stage_path(STAGED_PROD_DB)
    want = (rep.get("prod_db") or {}).get("sha256")
    if not os.path.exists(staged) or sha256_file(staged) != want:
        raise Refused("the staged prod copy %s is missing or no longer matches the stage report" % staged)
    _say("staged prod copy: %s (sha256 %s...)" % (staged, want[:12]))
    if is_prod_path(DEV_SPOOLMAN_DB):
        raise Refused("the swap's target %s is on prod's share" % DEV_SPOOLMAN_DB)
    _say("target (dev's database): %s" % DEV_SPOOLMAN_DB)

    problems = []
    dev_up, dev_why = spoolman_answers(DEV_SPOOLMAN_URL)
    prod_up, prod_why = spoolman_answers(PROD_SPOOLMAN_URL)
    _say("dev  Spoolman (%s): %s" % (DEV_SPOOLMAN_URL, dev_why))
    _say("prod Spoolman (%s): %s" % (PROD_SPOOLMAN_URL, prod_why))
    if dev_up:
        problems.append("dev Spoolman still answers: stop the dev Spoolman app in TrueNAS first")
    if not prod_up:
        problems.append("prod Spoolman doesn't answer: was the prod app stopped instead of dev's? Start it again")
    idle, latch_why = latch_state()
    queue_ok, queue_why = fetch_queue_state()
    _say("dev FCC print latch: %s; fetch queue: %s" % (latch_why, queue_why))
    if not idle:
        problems.append("dev FCC is tracking a print (%s): swap once every printer is IDLE" % latch_why)
    if not queue_ok:
        problems.append("dev FCC has a print download queued (%s): it would charge the new spools" % queue_why)
    side = side_files(DEV_SPOOLMAN_DB)
    if side:
        problems.append("dev's folder holds %s: a write was cut off; look before replacing" % side)
    if os.path.exists(stage_path(DEV_DB_BACKUP)):
        problems.append("%s already exists: this swap has run from this stage folder" % stage_path(DEV_DB_BACKUP))

    snapshot = rep.get("dev_identity")
    if snapshot is None and not args.apply and dev_up:
        snapshot = identity_from_lists(spoolman_lists(DEV_SPOOLMAN_URL))
        _say("(dry run: the stage report has no dev identity snapshot, so dev's API was read now)")
    if snapshot is None:
        problems.append("the stage report has no dev identity snapshot: run `stage` while dev Spoolman is up")
    else:
        ok, ident = check_target_identity(snapshot)
        _say("identity: dev's API (snapshot) %s" % snapshot)
        _say("          the target file      %s -> %s" % (ident, "SAME: it is dev's database" if ok else "DIFFERENT"))
        if not ok:
            problems.append("the target file's counts and max ids differ from dev's snapshot: it may not be "
                            "dev's database (both config files name the same spoolman_db_path, so a wrong guess "
                            "would overwrite prod's). If dev Spoolman was written after `stage` (a test run, "
                            "say), start it again and re-run `stage` with a new --stage-dir")
    if problems:
        _say("\nREFUSED%s:" % ("" if args.apply else " (dry run)"))
        for p in problems:
            _say("  - " + p)
        return 2
    if not args.apply:
        _say("\nDRY RUN: every guard passes. --apply would back the target up to %s, overwrite it in place "
             "with the staged copy and check the hash." % stage_path(DEV_DB_BACKUP))
        return 0
    backup = stage_path(DEV_DB_BACKUP)
    _guard_write(backup)
    shutil.copyfile(DEV_SPOOLMAN_DB, backup)
    before = sha256_file(DEV_SPOOLMAN_DB)
    if sha256_file(backup) != before or identity_from_db(backup) != snapshot:
        raise Refused("the backup of dev's database doesn't match it; nothing was replaced")
    _say("dev backup: %s (%d bytes, sha256 %s...)" % (backup, os.path.getsize(backup), before[:12]))
    _copy_in_place(staged, DEV_SPOOLMAN_DB)
    after = sha256_file(DEV_SPOOLMAN_DB)
    _say("dev's database now: sha256 %s... (the staged copy: %s...)" % (after[:12], want[:12]))
    if after != want:
        raise Refused("dev's database doesn't match the staged copy: put %s back the same way" % backup)
    _say("\nOK. NEXT: start the dev Spoolman app in TrueNAS, then run `verify-spoolman`.")
    return 0


# --------------------------------------------------------------------------
# Phase: verify-spoolman
# --------------------------------------------------------------------------
def _fixture_only_difference(prod_rec, dev_rec, box):
    """True when dev's spool sits in the test box and differs from prod's only by the fixture move."""
    if _norm_loc(dev_rec.get("location")) != box.upper():
        return False
    strip = lambda r: {k: v for k, v in r.items() if k not in ("location", "extra")}  # noqa: E731
    if strip(prod_rec) != strip(dev_rec):
        return False
    pe = {k: v for k, v in (prod_rec.get("extra") or {}).items() if k not in FIXTURE_EXTRAS}
    de = {k: v for k, v in (dev_rec.get("extra") or {}).items() if k not in FIXTURE_EXTRAS}
    return pe == de


def phase_verify_spoolman(args):
    consts = conftest_constants()
    rep = {"at": _now(), "dev_version": spoolman_info(DEV_SPOOLMAN_URL).get("version"),
           "prod_version": spoolman_info(PROD_SPOOLMAN_URL).get("version"), "kinds": {}}
    _say("dev Spoolman %s, prod Spoolman %s" % (rep["dev_version"], rep["prod_version"]))
    prod, dev = spoolman_lists(PROD_SPOOLMAN_URL), spoolman_lists(DEV_SPOOLMAN_URL)
    unexpected, fixture = 0, []
    for kind in ("vendor", "filament", "spool"):
        p = {r["id"]: r for r in prod[kind]}
        d = {r["id"]: r for r in dev[kind]}
        only_p, only_d = sorted(set(p) - set(d)), sorted(set(d) - set(p))
        differing = [i for i in sorted(set(p) & set(d)) if p[i] != d[i]]
        real = []
        for i in differing:
            if kind == "spool" and _fixture_only_difference(p[i], d[i], consts["box"]):
                fixture.append(i)
            else:
                real.append(i)
        rep["kinds"][kind] = {"prod": len(p), "dev": len(d), "only_prod": only_p, "only_dev": only_d,
                              "differing": real}
        _say("%-8s prod %d, dev %d, only prod %s, only dev %s, differing %s"
             % (kind, len(p), len(d), only_p[:10], only_d[:10], real[:10]))
        for i in real[:3]:
            keys = sorted(k for k in set(p[i]) | set(d[i]) if p[i].get(k) != d[i].get(k))
            _say("   #%s differs in %s" % (i, keys))
        unexpected += len(only_p) + len(only_d) + len(real)
    rep["fixture_differences"] = fixture
    if fixture:
        _say("expected: spool(s) %s differ only by the fixture move into %s" % (fixture, consts["box"]))
    stage = load_stage_report(required=False)
    staged = stage_path(STAGED_PROD_DB)
    if os.path.exists(staged):
        rep["staged_copy_identity"] = identity_from_db(staged)
        rep["dev_api_identity"] = identity_from_lists(dev)
        same = rep["staged_copy_identity"] == rep["dev_api_identity"]
        _say("staged prod copy %s vs dev's API %s: %s" % (rep["staged_copy_identity"], rep["dev_api_identity"],
                                                         "SAME" if same else "DIFFERENT"))
        if not same:
            unexpected += 1
    if (stage.get("prod_db") or {}).get("mtime"):
        try:
            now = prod_db_stat()
            rep["prod_db_now"] = now
            changed = now["mtime"] != stage["prod_db"]["mtime"]
            _say("prod's spoolman.db mtime: staged %s, now %s%s" % (
                stage["prod_db"]["mtime"], now["mtime"],
                " -> CHANGED: prod has been written since the copy" if changed else " (unchanged)"))
            rep["prod_changed_since_copy"] = changed
        except OSError as exc:
            _say("couldn't stat prod's database: %s" % exc)
    rep["verdict"] = "MATCH" if not unexpected else "DIFFERENCES: %d" % unexpected
    _say(rep["verdict"] + (" (apart from the fixture spool%s %s)" % ("s" if len(fixture) > 1 else "", fixture)
                           if fixture and not unexpected else ""))
    if args.apply:
        _write_json(stage_path("verify-spoolman-report.json"), rep)
    return 0 if not unexpected else 1


# --------------------------------------------------------------------------
# Phase: locations (the build is a pure function, so it can be read and tested on its own)
# --------------------------------------------------------------------------
def build_dev_locations(prod_rows, dev_rows, baselines, test_carts, fallback_rows=None):
    """Dev's new locations list and a report of every choice made. No I/O."""
    if not isinstance(prod_rows, list):
        raise Refused("prod's locations.json is not a list")

    def index(rows):
        out = {}
        for r in rows or []:
            if isinstance(r, dict) and _lid(r) and _lid(r).upper() not in out:
                out[_lid(r).upper()] = r
        return out

    dev_by, fb_by = index(dev_rows), index(fallback_rows)
    rep = {"prod_rows": len(prod_rows), "dropped_blank": [], "dropped_non_dict": 0, "logins_kept": [],
           "prod_logins_not_taken": [], "boxes": [], "bindings_replaced": [], "boxes_added": [],
           "parents_added": [], "parents_missing": [], "carts_added": [], "carts_in_prod": [],
           "carts_missing": []}
    out = []
    for r in prod_rows:
        if not isinstance(r, dict):
            rep["dropped_non_dict"] += 1
            continue
        if not _lid(r):
            rep["dropped_blank"].append({"Type": r.get("Type"), "Name": r.get("Name"),
                                         "parent_id": r.get("parent_id")})
            continue
        dev_row = dev_by.get(_lid(r).upper())
        dev_has = isinstance(dev_row, dict) and CREDS in dev_row
        row = {}
        for k, v in r.items():          # prod's key order; a login sits where prod's did
            if k == CREDS:
                if dev_has:
                    row[CREDS] = copy.deepcopy(dev_row[CREDS])
                continue
            row[k] = copy.deepcopy(v)
        if dev_has and CREDS not in row:
            row[CREDS] = copy.deepcopy(dev_row[CREDS])
        if dev_has:
            rep["logins_kept"].append({"LocationID": _lid(r),
                                       "prod_differs": r.get(CREDS) != dev_row.get(CREDS)})
        elif CREDS in r:
            rep["prod_logins_not_taken"].append(_lid(r))
        out.append(row)

    out_by = {_lid(r).upper(): r for r in out}

    def take(key, source_rows_by):
        src = source_rows_by.get(key)
        return None if src is None else {k: copy.deepcopy(v) for k, v in src.items() if k != CREDS}

    for box, baseline in baselines.items():
        key, target = box.strip().upper(), normalized_slot_targets(baseline)
        row = out_by.get(key)
        source = "prod"
        if row is None:
            row = take(key, dev_by)
            source = "dev"
            if row is None:
                row = take(key, fb_by)
                source = "seed"
            if row is None:
                raise Refused("%s is in neither prod's locations, dev's nor the seed" % box)
            out.append(row)
            out_by[key] = row
            rep["boxes_added"].append({"box": box, "from": source})
        if str(row.get("Type", "")).strip() != "Dryer Box":
            raise Refused("%s is a %r in %s's file, not a Dryer Box; the tests borrow it as one. "
                          "Decide what dev needs before refreshing" % (box, row.get("Type"), source))
        extra = row.get("extra")
        if not isinstance(extra, dict):
            if extra is not None:
                rep["bindings_replaced"].append({"box": box, "prod_extra_was": type(extra).__name__})
            extra = {}
        previous = extra.get("slot_targets")
        if source == "prod" and normalized_slot_targets(previous) != target:
            rep["bindings_replaced"].append({"box": box, "prod_slot_targets": previous})
        extra["slot_targets"] = dict(target)
        row["extra"] = extra
        rep["boxes"].append({"box": box, "from": source, "slot_targets": dict(target)})

    for box in baselines:
        pid = out_by[box.strip().upper()].get("parent_id")
        seen = set()
        while pid and str(pid).upper() not in out_by and str(pid).upper() not in seen:
            seen.add(str(pid).upper())
            row = take(str(pid).upper(), dev_by) or take(str(pid).upper(), fb_by)
            if row is None:
                rep["parents_missing"].append({"box": box, "parent_id": pid})
                break
            out.append(row)
            out_by[_lid(row).upper()] = row
            rep["parents_added"].append(_lid(row))
            pid = row.get("parent_id")

    for cart in test_carts:
        key = cart.upper()
        if key in out_by:
            rep["carts_in_prod"].append(cart)
            continue
        row, source = take(key, dev_by), "dev"
        if row is None:
            row, source = take(key, fb_by), "seed"
        if row is None:
            rep["carts_missing"].append(cart)
            continue
        out.append(row)
        out_by[key] = row
        rep["carts_added"].append({"id": cart, "from": source})
    rep["rows_out"] = len(out)
    return out, rep


_REQUIRED_KEYS = {"Tool Head": {"Max Spools", "Name"}, "Dryer Box": {"Max Spools", "Name"},
                  "MMU Slot": {"Max Spools", "Name"}, "No MMU Direct Load": {"Max Spools", "Name"},
                  "Cart": {"Name"}, "Sliding Drawer": {"Name"}}


def validate_locations(rows, dev_rows, baselines, test_carts, consts):
    """Every check tests/test_locations_json_integrity.py makes, plus the fixtures and the fleet.
    Returns a list of problems (empty = valid)."""
    problems = []
    if not isinstance(rows, list) or not rows:
        return ["not a non-empty list"]
    all_ids = {_lid(r).upper() for r in rows if isinstance(r, dict) and _lid(r)}
    seen = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append("row %d is not a dict" % i)
            continue
        lid, kind = _lid(row), str(row.get("Type") or "").strip()
        if not lid:
            problems.append("row %d has a blank LocationID" % i)
        if not kind:
            problems.append("row %d (%s) has a blank Type" % (i, lid))
        if lid:
            if lid.upper() in seen:
                problems.append("duplicate LocationID %s (rows %d and %d)" % (lid, seen[lid.upper()], i))
            seen.setdefault(lid.upper(), i)
        missing = ({"LocationID", "Type", "Name"} | _REQUIRED_KEYS.get(row.get("Type"), set())) - set(row)
        if missing:
            problems.append("row %d (%s, %s) lacks %s" % (i, lid, row.get("Type"), sorted(missing)))
        pid = row.get("parent_id")
        if pid is not None:
            if not isinstance(pid, str) or not pid or pid != pid.upper():
                problems.append("row %s has parent_id %r (want None or an upper-case id)" % (lid, pid))
            elif pid.upper() not in all_ids and pid.upper() not in consts["pseudo_rooms"]:
                problems.append("row %s has a dangling parent_id %r" % (lid, pid))
    text = json.dumps(rows, indent=4)
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if ":" in s and s.startswith('"') and '": "' in s:
            n = s.replace('\\"', "").count('"')
            if n % 2 or n not in (4, 6):
                problems.append("line %d has an odd quote count (%d)" % (lineno, n))
    by = {_lid(r).upper(): r for r in rows if isinstance(r, dict) and _lid(r)}
    dev_by = {_lid(r).upper(): r for r in (dev_rows or []) if isinstance(r, dict) and _lid(r)}
    for printer, heads in FLEET:
        row = by.get(printer)
        if not row or str(row.get("Type", "")).strip() != "Printer":
            problems.append("the fleet: no Printer row %s" % printer)
            continue
        have = {_norm_loc(t.get("location_id")) for t in (row.get("toolheads") or []) if isinstance(t, dict)}
        if have != set(heads):
            problems.append("the fleet: %s's heads are %s, not %s" % (printer, sorted(have), list(heads)))
        for h in heads:
            if str((by.get(h) or {}).get("Type", "")).strip() not in consts["toolhead_types"]:
                problems.append("the fleet: %s has no toolhead row" % h)
    for printer in NAME_MUST_STAY:
        if printer in by and printer in dev_by and by[printer].get("Name") != dev_by[printer].get("Name"):
            problems.append("%s's display Name changed from dev's (the tests use it in an API path; "
                            "the Group 44 trap)" % printer)
    for box, baseline in baselines.items():
        row = by.get(box.upper())
        st = (row or {}).get("extra", {}).get("slot_targets") if isinstance((row or {}).get("extra"), dict) else None
        if not row or row.get("Type") != "Dryer Box" or st != normalized_slot_targets(baseline):
            problems.append("test box %s isn't a Dryer Box at slot_targets %s" % (box, normalized_slot_targets(baseline)))
    for cart in test_carts:
        if cart.upper() not in by:
            problems.append("test cart %s is missing" % cart)
    for lid, row in by.items():
        if CREDS in row and (lid not in dev_by or dev_by[lid].get(CREDS) != row.get(CREDS)):
            problems.append("%s carries a printer login that isn't dev's" % lid)
    return problems


_MIGRATE_CHILD = r'''
import copy, json, logging, os, sys
hub, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, hub)
logging.disable(logging.CRITICAL)
import locations_db
with open(os.path.join(work, "candidate.json"), encoding="utf-8") as fh:
    cur = json.load(fh)
with open(os.path.join(work, "maps.json"), encoding="utf-8") as fh:
    maps = json.load(fh)
pm = maps.get("printer_map") or {}
feeder = maps.get("feeder_map") or {}

def ids(rows):
    return {str(r.get("LocationID", "")).strip().upper(): r for r in rows if isinstance(r, dict)}

steps = []
def step(name, fn):
    global cur
    out, changed = fn(copy.deepcopy(cur))
    rec = {"name": name, "changed": bool(changed)}
    if changed:
        a, b = ids(cur), ids(out)
        rec["added"] = sorted(set(b) - set(a))
        rec["removed"] = sorted(set(a) - set(b))
        rec["changed_rows"] = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        cur = out
    steps.append(rec)

if feeder:
    step("feeder_map -> slot_targets", lambda l: locations_db.migrate_feeder_map_if_needed(l, feeder))
step("Phase 1A parent_id backfill", locations_db.migrate_parent_ids_if_needed)
step("Phase 3 printer rows", lambda l: locations_db.migrate_printers_to_rows_if_needed(
    l, {} if locations_db.printer_rows_are_authoritative(l) else pm))
step("Phase 3.5 immediate parents", locations_db.migrate_immediate_parent_ids_if_needed)
step("Phase 5 shelf grouping", locations_db.migrate_shelf_grouping_rows_if_needed)
step("Phase 4 toolheads (prime only)", lambda l: locations_db.migrate_printer_map_to_toolheads_if_needed(
    l, {} if locations_db.printer_rows_are_authoritative(l) else pm, prime_only=True))
with open(os.path.join(work, "result.json"), "w", encoding="utf-8") as fh:
    json.dump({"steps": steps}, fh)
'''


def migration_fixpoint(rows):
    """Run the pure migrate_* functions that startup_migrations.run_startup_migrations calls, in its
    order, on the list in memory, in a subprocess whose working directory and FCC_DATA_DIR are an
    empty temp folder (so nothing can touch dev's data). Returns the steps, each with `changed`."""
    cfg = load_json(CONFIG_JSON)
    work = stage_path(".tmp-migrate-%d" % os.getpid())
    _makedirs(work)
    try:
        _write_json(os.path.join(work, "candidate.json"), strip_creds(rows))
        _write_json(os.path.join(work, "maps.json"), {"printer_map": cfg.get("printer_map") or {},
                                                       "feeder_map": cfg.get("feeder_map") or {}})
        env = dict(os.environ, FCC_DATA_DIR=work)
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", _MIGRATE_CHILD, HUB_DIR, work],
                              cwd=work, env=env, capture_output=True, text=True, timeout=120)
        result_path = os.path.join(work, "result.json")
        if proc.returncode != 0 or not os.path.exists(result_path):
            raise Refused("the migration check failed: %s" % (proc.stderr or proc.stdout).strip()[-600:])
        return load_json(result_path)["steps"]
    finally:
        _rmtree(work)


def _safe_row(row):
    out = {k: row.get(k) for k in ("LocationID", "Type", "Name", "parent_id", "Max Spools")}
    if isinstance(row.get("extra"), dict) and "slot_targets" in row["extra"]:
        out["slot_targets"] = row["extra"]["slot_targets"]
    return out


def diff_rows(old_rows, new_rows):
    """Rows added, removed and changed by LocationID; changed rows name their keys only."""
    a = {_lid(r).upper(): r for r in old_rows if isinstance(r, dict) and _lid(r)}
    b = {_lid(r).upper(): r for r in new_rows if isinstance(r, dict) and _lid(r)}
    changed = {}
    for k in sorted(set(a) & set(b)):
        keys = sorted(x for x in set(a[k]) | set(b[k]) if a[k].get(x) != b[k].get(x))
        if keys:
            changed[k] = keys
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)), "changed": changed}


def bak_files():
    out = {}
    for name in os.listdir(DEV_DATA_DIR):
        if fnmatch.fnmatch(name, "locations.json.pre-*.bak"):
            st = os.stat(dev_path(name))
            out[name] = {"size": st.st_size, "mtime": _iso(st.st_mtime)}
    return out


def backup_dev_data():
    """Byte copies of every file in dev's data folder (not the val_*.gcode captures), hashes checked.
    The first backup is dev-data-before/; a later one gets a time stamp, so it never overwrites it."""
    target = stage_path(DEV_DATA_BACKUP)
    if os.path.exists(target) and os.listdir(target):
        target = stage_path("%s-%s" % (DEV_DATA_BACKUP, datetime.datetime.now().strftime("%H%M%S")))
    _makedirs(target)
    copied, skipped = [], []
    for name in sorted(os.listdir(DEV_DATA_DIR)):
        src = dev_path(name)
        if not os.path.isfile(src):
            skipped.append(name + " (folder)")
            continue
        if any(fnmatch.fnmatch(name, pat) for pat in BACKUP_SKIP):
            skipped.append(name)
            continue
        dst = os.path.join(target, name)
        _copy_keep_times(src, dst)
        if sha256_file(src) != sha256_file(dst):
            raise Refused("the backup of %s doesn't match it" % name)
        copied.append(name)
    return target, copied, skipped


def _spool_location_report(spools, rows, baselines, toolhead_types):
    places = Places(rows, toolhead_types)
    boxes = {b.upper() for b in baselines}
    no_row, from_box = [], []
    for s in spools:
        if s.get("archived"):
            continue
        loc = _norm_loc(s.get("location"))
        if loc not in NOT_A_ROW and loc not in places.by_id:
            no_row.append({"id": s.get("id"), "location": loc})
        src, slot = trail_of(s.get("extra"))
        if src in boxes:
            from_box.append({"id": s.get("id"), "location": loc, "trail": src + (":" + slot if slot else "")})
    return no_row, from_box


def phase_locations(args):
    consts = dict(conftest_constants(), **backend_constants())
    baselines = consts["baselines"]
    stage = load_stage_report(required=False)
    rep = {"at": _now(), "stage_dir": STAGE_DIR}

    _say("Reading prod (read-only) ...")
    prod_rows, rep["prod_locations"] = read_prod_locations()
    _say("  %s: %s rows, %d bytes, mtime %s" % (rep["prod_locations"]["path"], rep["prod_locations"]["rows"],
                                                 rep["prod_locations"]["size"], rep["prod_locations"]["mtime"]))
    at_stage = stage.get("prod_locations") or {}
    if at_stage.get("sha256"):
        same = at_stage["sha256"] == rep["prod_locations"]["sha256"]
        rep["prod_locations_changed_since_stage"] = not same
        _say("  prod's locations.json %s since the stage (%s)" % ("is unchanged" if same else "CHANGED",
                                                                   at_stage.get("mtime")))
    rep["prod_data_listing"], listing_err = prod_data_listing()
    _say("  prod's data folder: %s" % (", ".join(rep["prod_data_listing"]) if listing_err is None else listing_err))
    hidden = prod_hidden_choices()
    rep["prod_hidden_choices"] = hidden
    dev_hidden = dev_path("attr_hidden_choices.json")
    _say("  prod's attr_hidden_choices.json: %s; dev's: %s" % (
        "absent" if hidden is None else "%s (mtime %s)" % (json.dumps(hidden.get("content"), ensure_ascii=False)[:300],
                                                           hidden.get("mtime")),
        "present" if os.path.exists(dev_hidden) else "absent"))
    if (stage.get("prod_db") or {}).get("mtime"):
        now = prod_db_stat()
        rep["prod_db_now"] = now
        rep["prod_spoolman_changed_since_copy"] = now["mtime"] != stage["prod_db"]["mtime"] or bool(now["side_files"])
        _say("  prod's spoolman.db mtime: copied at %s, now %s -> %s" % (
            stage["prod_db"]["mtime"], now["mtime"],
            "CHANGED: prod's Spoolman was written after the copy, so the two snapshots aren't from one moment"
            if rep["prod_spoolman_changed_since_copy"] else "unchanged (the two snapshots are from one moment)"))

    dev_rows = load_json(dev_path("locations.json"))
    seed_rows = load_json(LOCATIONS_SEED) if os.path.exists(LOCATIONS_SEED) else []
    new_rows, build = build_dev_locations(prod_rows, dev_rows, baselines, TEST_CARTS, seed_rows)
    rep["build"] = build
    problems = validate_locations(new_rows, dev_rows, baselines, TEST_CARTS, consts)
    steps = migration_fixpoint(new_rows)
    rep["migrations"] = steps
    for s in steps:
        if s["changed"]:
            problems.append("boot migration %r would change %s" % (s["name"], {k: s.get(k) for k in
                                                                               ("added", "removed", "changed_rows")}))
    rep["problems"] = problems
    rep["diff_vs_dev"] = diff_rows(dev_rows, new_rows)
    dev_rcoi = next((r for r in dev_rows if _lid(r).upper() == "RCOI"), {})
    new_rcoi = next((r for r in new_rows if _lid(r).upper() == "RCOI"), {})
    rep["rcoi_parent"] = {"dev": dev_rcoi.get("parent_id"), "prod": new_rcoi.get("parent_id")}

    _say("\nThe new file: %d prod rows -> %d rows" % (build["prod_rows"], build["rows_out"]))
    for b in build["dropped_blank"]:
        _say("  dropped a blank-LocationID row: Type %r, Name %r" % (b["Type"], b["Name"]))
    if build["dropped_non_dict"]:
        _say("  dropped %d row(s) that weren't objects" % build["dropped_non_dict"])
    for lg in build["logins_kept"]:
        _say("  %s keeps dev's printer login (prod's differ: %s)" % (lg["LocationID"], lg["prod_differs"]))
    for lid in build["prod_logins_not_taken"]:
        _say("  %s: prod has a login, dev has none, so it gets none" % lid)
    for b in build["boxes"]:
        _say("  test box %s from %s, slot_targets %s" % (b["box"], b["from"], b["slot_targets"]))
    for b in build["bindings_replaced"]:
        _say("  REPLACED prod binding on %s: %s" % (b["box"], b.get("prod_slot_targets", b)))
    if not build["bindings_replaced"]:
        _say("  no prod binding replaced (every test box already read its baseline in prod's file)")
    for p in build["parents_added"]:
        _say("  added parent row %s" % p)
    for p in build["parents_missing"]:
        _say("  %s's parent %s has no row on prod, dev or the seed (left as it is)" % (p["box"], p["parent_id"]))
    _say("  test carts added: %s; already in prod: %s; missing: %s" % (
        [c["id"] + " (" + c["from"] + ")" for c in build["carts_added"]], build["carts_in_prod"], build["carts_missing"]))
    _say("  RCOI parent_id: dev %r -> prod's %r" % (rep["rcoi_parent"]["dev"], rep["rcoi_parent"]["prod"]))
    d = rep["diff_vs_dev"]
    _say("  vs dev's current file: +%d rows %s, -%d rows %s, %d changed" % (
        len(d["added"]), d["added"][:12], len(d["removed"]), d["removed"][:12], len(d["changed"])))
    for lid, keys in list(d["changed"].items())[:40]:
        _say("     %s: %s" % (lid, keys))
    _say("  boot migrations: " + ", ".join("%s=%s" % (s["name"], "CHANGES" if s["changed"] else "fixpoint")
                                           for s in steps))

    spools = get_json(DEV_SPOOLMAN_URL + "/api/v1/spool?allow_archived=true")
    no_row, from_box = _spool_location_report(spools, new_rows, baselines, consts["toolhead_types"])
    rep["spools_at_no_row"], rep["spools_trailing_test_boxes"] = no_row, from_box
    _say("  in-stock dev spools filed at a place with no row: %d %s" % (len(no_row), no_row[:10]))
    _say("  in-stock dev spools whose trail names a test box: %d %s" % (len(from_box), from_box[:10]))
    idle, latch_why = latch_state()
    queue_ok, queue_why = fetch_queue_state()
    cards = review_cards()
    rep["latch"], rep["fetch_queue"], rep["review_cards_before"] = latch_why, queue_why, cards
    _say("  dev FCC: latch %s; fetch queue %s; review cards %s" % (
        latch_why, queue_why, [(c["job_id"], c["kind"], c["total_grams"]) for c in cards]))

    if problems:
        _say("\nREFUSED: the new file doesn't validate:")
        for p in problems:
            _say("  - " + p)
        return 2
    if not args.apply:
        _say("\nDRY RUN: valid. --apply would stop FCC, back up %s to %s, write locations.json, empty the "
             "review cards and fetch queue (only while every latch reads IDLE), start FCC and check it. "
             "Nothing written." % (DEV_DATA_DIR, stage_path(DEV_DATA_BACKUP)))
        return 0

    _say("\nAPPLY")
    _makedirs(STAGE_DIR)
    with FccStopped():
        target, copied, skipped = backup_dev_data()
        rep["backup"] = {"folder": target, "copied": copied, "skipped": skipped}
        _say("  backed up %d files to %s (skipped %s)" % (len(copied), target, skipped))
        baks_before = bak_files()
        _write_text_atomic(dev_path("locations.json"), json.dumps(new_rows, indent=4))
        _say("  wrote %s (%d rows)" % (dev_path("locations.json"), len(new_rows)))
        idle, latch_why = latch_state()
        if idle:
            for name in PENDING_FILES:
                _write_text_atomic(dev_path(name), "{}")
            rep["pending_cleared"] = list(PENDING_FILES)
            _say("  emptied %s (latch: %s)" % (", ".join(PENDING_FILES), latch_why))
        else:
            rep["pending_cleared"] = []
            _say("  left the review cards and fetch queue as they are: %s" % latch_why)
        _write_json(stage_path(PROD_LOCATIONS_AS_READ), strip_creds(prod_rows), indent=4)
    wait_for_fcc()
    _say("  dev FCC answers again")
    status, api_rows, _, hdrs = fcc_get("/api/locations")
    api_ids = {_lid(r).upper() for r in api_rows if isinstance(r, dict)} if isinstance(api_rows, list) else set()
    file_ids = {_lid(r).upper() for r in new_rows}
    rep["api_locations"] = {"status": status, "rows": len(api_rows) if isinstance(api_rows, list) else None,
                            "spool_read": hdrs.get("X-FCC-Spool-Read"),
                            "only_api": sorted(api_ids - file_ids), "only_file": sorted(file_ids - api_ids)}
    _say("  GET /api/locations: HTTP %s, %s rows (the file has %d), X-FCC-Spool-Read %s; only in the API %s, "
         "only in the file %s" % (status, rep["api_locations"]["rows"], len(new_rows), rep["api_locations"]["spool_read"],
                                  rep["api_locations"]["only_api"], rep["api_locations"]["only_file"]))
    rep["bindings_after"] = {}
    for box in baselines:
        st, body, _, _ = fcc_get("/api/dryer_box/%s/bindings" % urllib.parse.quote(box))
        rep["bindings_after"][box] = (body or {}).get("slot_targets") if st == 200 else "HTTP %s" % st
        _say("  %s bindings: %s" % (box, rep["bindings_after"][box]))
    baks_after = bak_files()
    rep["bak_files"] = {"before": baks_before, "after": baks_after, "same": baks_before == baks_after}
    _say("  locations.json.pre-*.bak: %d before, %d after, %s" % (
        len(baks_before), len(baks_after), "the same files" if baks_before == baks_after else "CHANGED"))
    _say("  review cards now: %s" % review_cards())
    _write_json(stage_path("locations-report.json"), rep)
    ok = (status == 200 and all(v == normalized_slot_targets(baselines[b]) for b, v in rep["bindings_after"].items())
          and baks_before == baks_after)
    _say("\n%s. Report: %s" % ("OK" if ok else "CHECK FAILED", stage_path("locations-report.json")))
    return 0 if ok else 3


# --------------------------------------------------------------------------
# Phase: fixtures (dev Spoolman only)
# --------------------------------------------------------------------------
def _choose_fixture(spools_by, places, box):
    """Prod-copy #123 when it still reads as the Quick-Swap pictures show it, is in stock and is
    on no head; else the lowest-numbered in-stock spool stored in a plain place."""
    pref = spools_by.get(FIXTURE_SPOOL)
    why = []
    if pref is None:
        why.append("#%d doesn't exist" % FIXTURE_SPOOL)
    else:
        if spool_display(pref) != FIXTURE_LABEL:
            why.append("#%d reads %r, not %r" % (FIXTURE_SPOOL, spool_display(pref), FIXTURE_LABEL))
        if pref.get("archived"):
            why.append("#%d is archived" % FIXTURE_SPOOL)
        if places.is_head(pref.get("location")):
            why.append("#%d is on a head (%s)" % (FIXTURE_SPOOL, pref.get("location")))
    if not why:
        return pref, []
    for sid in sorted(spools_by):
        s = spools_by[sid]
        kind = places.type_of(s.get("location"))
        if (not s.get("archived") and kind and kind not in ("Printer", "Dryer Box") and not places.is_head(s.get("location"))
                and (s.get("remaining_weight") or 0) > 0 and _norm_loc(s.get("location")) != box.upper()):
            return s, why
    raise Refused("no spool fits the fixture: %s" % why)


def phase_fixtures(args):
    consts = dict(conftest_constants(), **backend_constants())
    box, slot = consts["box"], consts["slot"]
    rows = load_json(dev_path("locations.json"))
    places = Places(rows, consts["toolhead_types"])
    box_row = places.by_id.get(box.upper())
    rep = {"at": _now(), "box": box, "slot": slot}
    if not box_row or box_row.get("Type") != "Dryer Box":
        raise Refused("%s isn't a Dryer Box in dev's locations.json: run `locations` first" % box)
    max_spools = places.max_spools(box)
    _say("%s: Dryer Box, Max Spools %s, slot_targets %s" % (
        box, max_spools, (box_row.get("extra") or {}).get("slot_targets")))
    if max_spools is None or int(slot) > max_spools:
        raise Refused("%s has no slot %s" % (box, slot))
    fields = {f.get("key"): f for f in get_json(DEV_SPOOLMAN_URL + "/api/v1/field/spool")}
    for key in FIXTURE_EXTRAS:
        if key not in fields:
            raise Refused("dev Spoolman has no spool field %r: FCC's boot registers it (REQUIRED_SPOOL_EXTRAS)" % key)
        if fields[key].get("field_type") != "text":
            raise Refused("dev Spoolman's %r is a %r field, not text" % (key, fields[key].get("field_type")))
    spools = get_json(DEV_SPOOLMAN_URL + "/api/v1/spool?allow_archived=true")
    by = {s["id"]: s for s in spools}
    fixture, why_not_pref = _choose_fixture(by, places, box)
    rep["fixture"] = {"id": fixture["id"], "display": spool_display(fixture), "was_at": fixture.get("location"),
                      "preferred_skipped_because": why_not_pref}
    _say("fixture spool: #%s %r, now at %r" % (fixture["id"], spool_display(fixture), fixture.get("location")))
    if why_not_pref:
        _say("  (not #%d: %s) -> the two Quick-Swap confirm baselines need recapturing "
             "(quickswap-confirm-overlay*.png)" % (FIXTURE_SPOOL, "; ".join(why_not_pref)))
    occupants = [s for s in spools if _norm_loc(s.get("location")) == box.upper() and s["id"] != fixture["id"]]
    deployed = [s for s in spools if trail_of(s.get("extra"))[0] == box.upper()]
    rep["other_occupants"] = [{"id": s["id"], "slot": slot_of(s.get("extra")), "archived": s.get("archived")}
                              for s in occupants]
    rep["deployed_from_box"] = [{"id": s["id"], "location": s.get("location")} for s in deployed]
    _say("other spools in %s: %s; spools deployed from it: %s" % (box, rep["other_occupants"], rep["deployed_from_box"]))
    for sid in SPOOLS_TESTS_NAME:
        s = by.get(sid)
        rep.setdefault("weigh_out_spools", {})[sid] = None if s is None else {
            "exists": True, "archived": bool(s.get("archived")), "location": s.get("location"),
            "display": spool_display(s), "remaining_weight": s.get("remaining_weight")}
        _say("spool #%d: %s" % (sid, "MISSING" if s is None else "%s, %s, at %r, %s g left" % (
            spool_display(s), "ARCHIVED" if s.get("archived") else "in stock", s.get("location"),
            s.get("remaining_weight"))))
    if occupants or deployed:
        _say("\nREFUSED: %s must hold only the fixture spool; move the others out by hand first." % box)
        return 2

    want = {"container_slot": json.dumps(str(slot)), "physical_source": json.dumps(""),
            "physical_source_slot": json.dumps(""), "fcc_pre_box_location": json.dumps("")}
    extra_now = fixture.get("extra") or {}
    in_place = (_norm_loc(fixture.get("location")) == box.upper()
                and all(decode_extra(extra_now.get(k, '""')) == decode_extra(v) for k, v in want.items()))
    payload = {"location": box, "extra": want}
    rep["payload"] = payload
    if in_place:
        _say("already in place: #%s sits in %s slot %s with no trail" % (fixture["id"], box, slot))
    elif not args.apply:
        _say("\nDRY RUN: would stop FCC and PATCH %s/api/v1/spool/%s with %s (every other extra kept: "
             "Spoolman 0.27 merges a PATCH's extra key by key), then start FCC and check "
             "/api/get_contents?id=%s." % (DEV_SPOOLMAN_URL, fixture["id"], json.dumps(payload), box))
        return 0
    else:
        with FccStopped():
            status, body, text, _ = http("PATCH", "%s/api/v1/spool/%s" % (DEV_SPOOLMAN_URL, fixture["id"]), payload)
            if status != 200:
                raise Refused("PATCH spool %s answered HTTP %s: %s" % (fixture["id"], status, text[:300]))
            after = get_json("%s/api/v1/spool/%s" % (DEV_SPOOLMAN_URL, fixture["id"]))
            kept = {k: v for k, v in (fixture.get("extra") or {}).items() if k not in want}
            kept_after = {k: v for k, v in (after.get("extra") or {}).items() if k not in want}
            problems = []
            if after.get("location") != box:
                problems.append("location reads %r" % after.get("location"))
            for k, v in want.items():
                if decode_extra((after.get("extra") or {}).get(k)) != decode_extra(v):
                    problems.append("%s reads %r" % (k, (after.get("extra") or {}).get(k)))
            if kept != kept_after:
                problems.append("other extras changed: %s -> %s" % (sorted(kept), sorted(kept_after)))
            if problems:
                raise Refused("the PATCH didn't land as sent: %s" % problems)
            _say("  PATCHed #%s: location %s, %s" % (fixture["id"], box, want))
        wait_for_fcc()
    st, contents, _, _ = fcc_get("/api/get_contents?id=%s" % urllib.parse.quote(box))
    items = contents if isinstance(contents, list) else []
    rep["get_contents"] = [{"id": it.get("id"), "slot": it.get("slot"), "display": it.get("display"),
                            "is_ghost": it.get("is_ghost")} for it in items]
    _say("GET /api/get_contents?id=%s: HTTP %s, %s" % (box, st, rep["get_contents"]))
    ok = (st == 200 and len(items) == 1 and items[0].get("id") == fixture["id"]
          and str(items[0].get("slot", "")).replace('"', "").strip() == slot)
    if fixture["id"] == FIXTURE_SPOOL and ok:
        ok = items[0].get("display") == FIXTURE_LABEL
    rep["ok"] = ok
    _say("%s: %s slot %s holds #%s and slots 2-%s are empty" % ("OK" if ok else "CHECK FAILED", box, slot,
                                                                fixture["id"], max_spools))
    if args.apply:
        _write_json(stage_path("fixtures-report.json"), rep)
    return 0 if ok else 3


# --------------------------------------------------------------------------
# Phase: count (45.7)
# --------------------------------------------------------------------------
def drift_count(spools, rows, toolhead_types):
    """The 45.7 number and what goes with it. A spool counts when it is in stock, its
    physical_source is set, and its location is not a head (Places.is_head)."""
    places = Places(rows, toolhead_types)
    counted, companions = [], {"archived_with_trail": [], "slot_only_residue": [], "archived_on_head": [],
                               "on_head_no_trail": [], "on_head_with_trail": []}
    for s in spools:
        src, slot = trail_of(s.get("extra"))
        on_head = places.is_head(s.get("location"))
        loc = _norm_loc(s.get("location"))
        entry = {"id": s.get("id"), "location": loc or "(unassigned)", "trail": src + (":" + slot if slot else "")}
        if s.get("archived"):
            if src:
                companions["archived_with_trail"].append(entry)
            if on_head:
                companions["archived_on_head"].append(entry)
            continue
        if not src and slot:
            companions["slot_only_residue"].append(entry)
        if on_head:
            companions["on_head_with_trail" if src else "on_head_no_trail"].append(entry)
        elif src:
            counted.append(entry)
    by_place, by_trail, own = {}, {}, 0
    for e in counted:
        kind = places.place_kind(e["location"] if e["location"] != "(unassigned)" else "")
        by_place[kind] = by_place.get(kind, 0) + 1
        src = e["trail"].split(":")[0]
        if src == e["location"]:
            own += 1
        if places.is_head(src) or src == "UNKNOWN":
            t = "a toolhead or UNKNOWN (never a valid trail)"
        elif src not in places.by_id:
            t = "a place with no row"
        elif places.type_of(src) == "Dryer Box":
            ms = places.max_spools(src)
            t = "a multi-slot box (a stale slot claim)" if ms is not None and ms > 1 else "a single-slot box"
        else:
            t = "another place (%s)" % places.type_of(src)
        by_trail[t] = by_trail.get(t, 0) + 1
    in_stock = sum(1 for s in spools if not s.get("archived"))
    return {"number": len(counted), "counted": sorted(counted, key=lambda e: e["id"]),
            "by_place_kind": by_place, "by_trail": by_trail, "trail_is_own_location": own,
            "spools": len(spools), "in_stock": in_stock, "archived": len(spools) - in_stock,
            "heads": len(places.printer_heads), "companions": companions}


def _print_count(label, res):
    _say("\n[%s] 45.7 count = %d   (%d spools: %d in stock, %d archived; %d heads)" % (
        label, res["number"], res["spools"], res["in_stock"], res["archived"], res["heads"]))
    for e in res["counted"]:
        _say("    #%s at %s, trail %s" % (e["id"], e["location"], e["trail"]))
    if res["counted"]:
        _say("  by the place the spool is in: %s" % res["by_place_kind"])
        _say("  by what the trail names: %s; trail is the spool's own location: %d"
             % (res["by_trail"], res["trail_is_own_location"]))
    c = res["companions"]
    _say("  companions (not in the number): archived with a trail %d %s; slot-only residue (in stock) %d %s; "
         "archived still on a head %d %s; in stock on a head with a trail %d %s; on a head with no trail %d"
         % (len(c["archived_with_trail"]), [e["id"] for e in c["archived_with_trail"]],
            len(c["slot_only_residue"]), [e["id"] for e in c["slot_only_residue"]],
            len(c["archived_on_head"]), [e["id"] for e in c["archived_on_head"]],
            len(c["on_head_with_trail"]), ["#%s %s<-%s" % (e["id"], e["location"], e["trail"])
                                           for e in c["on_head_with_trail"]],
            len(c["on_head_no_trail"])))


def phase_count(args):
    consts = backend_constants()
    rep = {"at": _now()}
    prod_locs_path = args.prod_locations or stage_path(PROD_LOCATIONS_AS_READ)
    if os.path.exists(prod_locs_path):
        prod_rows = load_json(prod_locs_path)
        rep["prod_locations"] = prod_locs_path
    else:
        prod_rows, meta = read_prod_locations()
        rep["prod_locations"] = "%s (read now, mtime %s)" % (meta["path"], meta["mtime"])
    _say("prod's locations as read: %s (%d rows)" % (rep["prod_locations"], len(prod_rows)))
    dev_spools = get_json(DEV_SPOOLMAN_URL + "/api/v1/spool?allow_archived=true")
    rep["prod_from_dev_api"] = drift_count(dev_spools, prod_rows, consts["toolhead_types"])
    _print_count("prod: dev Spoolman's API (prod's data) + prod's locations as read", rep["prod_from_dev_api"])
    staged = stage_path(STAGED_PROD_DB)
    if os.path.exists(staged):
        rep["prod_from_staged_db"] = drift_count(spools_from_db(staged), prod_rows, consts["toolhead_types"])
        same = [e["id"] for e in rep["prod_from_staged_db"]["counted"]] == \
               [e["id"] for e in rep["prod_from_dev_api"]["counted"]]
        _say("  cross-check, the staged prod database: %d (%s)" % (
            rep["prod_from_staged_db"]["number"], "the same spools" if same else "DIFFERENT spools"))
    dev_db = stage_path(DEV_DB_BACKUP)
    dev_locs = args.dev_locations or os.path.join(stage_path(DEV_DATA_BACKUP), "locations.json")
    if os.path.exists(dev_db) and os.path.exists(dev_locs):
        rep["dev_before"] = drift_count(spools_from_db(dev_db), load_json(dev_locs), consts["toolhead_types"])
        rep["dev_before_sources"] = {"db": dev_db, "locations": dev_locs}
        _print_count("dev before the refresh: %s + %s" % (os.path.basename(dev_db), dev_locs), rep["dev_before"])
    else:
        _say("\n(dev's old number needs %s and %s)" % (dev_db, dev_locs))
    if args.apply:
        _write_json(stage_path("count-report.json"), rep)
        _say("\nreport: %s" % stage_path("count-report.json"))
    return 0


# --------------------------------------------------------------------------
# Phase: seeds
# --------------------------------------------------------------------------
def _find_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_find_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_find_key(v, key) for v in obj)
    return False


def check_seeds(baselines):
    problems, info = [], {}
    with open(LOCATIONS_SEED, encoding="utf-8") as fh:
        text = fh.read()
    rows = json.loads(text)
    info["locations_rows"] = len(rows)
    if _find_key(rows, CREDS) or "printer_creds" in text or "api_key" in text or "ip_address" in text:
        problems.append("locations-seed.json holds printer login keys")
    by = {_lid(r).upper(): r for r in rows if isinstance(r, dict)}
    for box, baseline in baselines.items():
        row = by.get(box.upper())
        st = normalized_slot_targets(((row or {}).get("extra") or {}).get("slot_targets"))
        if not row or row.get("Type") != "Dryer Box" or st != normalized_slot_targets(baseline):
            problems.append("seed: %s isn't a Dryer Box at %s" % (box, normalized_slot_targets(baseline)))
    seed = load_json(SPOOLMAN_SEED)
    info["spoolman_counts"] = seed.get("counts")
    return problems, info


def phase_seeds(args):
    consts = conftest_constants()
    if args.apply:
        _say("Running reset_dev.py --capture ...")
        proc = subprocess.run([sys.executable, RESET_DEV, "--capture"], capture_output=True, text=True, timeout=600)
        _say(proc.stdout.strip())
        if proc.returncode != 0:
            raise Refused("reset_dev.py --capture failed: %s" % proc.stderr.strip()[-500:])
    else:
        _say("DRY RUN: would run reset_dev.py --capture. Checking the current seeds instead.")
    problems, info = check_seeds(consts["baselines"])
    _say("seeds: %s" % info)
    _say("Running reset_dev.py --dry-run --no-restart (read-only) ...")
    proc = subprocess.run([sys.executable, RESET_DEV, "--dry-run", "--no-restart"],
                          capture_output=True, text=True, timeout=600)
    _say(proc.stdout.strip())
    if args.apply:
        out = proc.stdout
        if "already matches seed" not in out:
            problems.append("reset_dev.py --dry-run doesn't say locations.json already matches the seed")
        drifted = [int(n) for n in re.findall(r"(\d+) drifted", out)]
        if len(drifted) != 3 or any(drifted):
            problems.append("reset_dev.py --dry-run reports drift right after the capture: %s" % drifted)
        if re.search(r"\d+ missing", out) or re.search(r"\d+ sweep-created", out):
            problems.append("reset_dev.py --dry-run reports missing or sweep-created records")
    for p in problems:
        _say("  PROBLEM: " + p)
    _say("OK" if not problems else "CHECK FAILED")
    if args.apply:
        _say("The seeds are git-tracked: don't commit them without Derek's OK (they hold his real inventory).")
    return 0 if not problems else 3


# --------------------------------------------------------------------------
# Phase: checklist (read-only)
# --------------------------------------------------------------------------
def checklist_state(spools, rows, toolhead_types):
    places = Places(rows, toolhead_types)
    out = {}
    for place in CHECKLIST_SOURCES + CHECKLIST_EMPTY:
        key = place.upper()
        stored = [s for s in spools if not s.get("archived") and _norm_loc(s.get("location")) == key]
        deployed = [s for s in spools if not s.get("archived") and trail_of(s.get("extra"))[0] == key
                    and places.is_head(s.get("location"))]
        out[place] = {"type": places.type_of(place), "max_spools": places.max_spools(place),
                      "stored": [{"id": s["id"], "display": spool_display(s), "slot": slot_of(s.get("extra"))}
                                 for s in sorted(stored, key=lambda x: (slot_of(x.get("extra")), x["id"]))],
                      "deployed": [{"id": s["id"], "display": spool_display(s), "head": _norm_loc(s.get("location")),
                                    "slot": trail_of(s.get("extra"))[1]}
                                   for s in sorted(deployed, key=lambda x: x["id"])]}
    return out


def phase_checklist(args):
    consts = backend_constants()
    spools = get_json(DEV_SPOOLMAN_URL + "/api/v1/spool?allow_archived=true")
    state = checklist_state(spools, load_json(dev_path("locations.json")), consts["toolhead_types"])
    for place, st in state.items():
        _say("%s (%s, Max Spools %s):" % (place, st["type"], st["max_spools"]))
        if not st["stored"] and not st["deployed"]:
            _say("    empty")
        for s in st["stored"]:
            _say("    #%s %s%s" % (s["id"], s["display"].split(" ", 1)[-1], " (slot %s)" % s["slot"] if s["slot"] else ""))
        for s in st["deployed"]:
            _say("    #%s %s: deployed from slot %s onto %s" % (s["id"], s["display"].split(" ", 1)[-1],
                                                               s["slot"] or "?", s["head"]))
    if args.apply:
        _write_json(stage_path("checklist-state.json"), state)
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
PHASES = {"stage": phase_stage, "swap": phase_swap, "verify-spoolman": phase_verify_spoolman,
          "locations": phase_locations, "fixtures": phase_fixtures, "count": phase_count,
          "seeds": phase_seeds, "checklist": phase_checklist}


def main(argv=None):
    global STAGE_DIR
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--apply", action="store_true", help="Write. Without it every phase is a dry run.")
    common.add_argument("--stage-dir", help="The stage folder (default %s, or FCC_REFRESH_STAGE_DIR)." % STAGE_DIR)
    ap = argparse.ArgumentParser(prog="refresh_dev_from_prod.py",
                                 description="Refresh dev's data from prod, read-only on prod (Group 45.6 / 45.7).")
    sub = ap.add_subparsers(dest="phase", required=True)
    for name in PHASES:
        p = sub.add_parser(name, parents=[common], help=(PHASES[name].__doc__ or "").strip().split("\n")[0] or None)
        if name == "count":
            p.add_argument("--prod-locations", help="prod's locations.json as read (default: the stage copy)")
            p.add_argument("--dev-locations", help="dev's locations.json before the refresh (default: the backup)")
    args = ap.parse_args(argv)
    if args.stage_dir:
        STAGE_DIR = args.stage_dir
    if _netloc(DEV_SPOOLMAN_URL) in _prod_netlocs():
        _say("REFUSED: DEV_SPOOLMAN_URL (%s) points at prod Spoolman." % DEV_SPOOLMAN_URL)
        return 2
    for name, value in (("stage folder", STAGE_DIR), ("dev data folder", DEV_DATA_DIR)):
        if is_prod_path(value):
            _say("REFUSED: the %s (%s) is on prod's share." % (name, value))
            return 2
    _say("refresh_dev_from_prod %s%s | stage %s" % (args.phase, "" if args.apply else " (DRY RUN)", STAGE_DIR))
    try:
        return PHASES[args.phase](args)
    except Refused as exc:
        _say("\nREFUSED: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
