"""When FCC itself last weighed each spool (Group 64, Decision 1; Derek, 2026-11-20).

FCC charges a print by adding its grams to the spool's used weight as Spoolman has
it at the charge. A spool weighed after the print ended already counts the print's
filament, so charging it then counts the print twice; on the INDX the download
before the charge takes 20 to 33 minutes, and a print whose file waits behind the
printer's screen can wait for hours. The print-end read keeps each head spool's used
weight (print_deduct._capture_print_heads' `used`); when that weight has changed by
the charge, this store says whether FCC weighed the spool after the print ended, and
when and on which screen. Derek's rule: "0 Should be the default if we can tell the
order of things, and a value if we aren't sure but both should be heavily noted in
the UI". Only FCC's own weighings are stamped (the weigh screens' saves through
/api/spool/update, Edit Spool's weight fields); a weight typed in Spoolman's own
page has no stamp, so FCC can't tell its order.

{sid: {"at": epoch seconds, "how": the screen's words}}, the latest weighing per
spool, an entry older than _KEEP_S dropped at each write. A store FCC can't read is
read as no stamps (FCC then can't tell, and fills in the print's grams); a write that
fails is one WARNING in hub.log and never fails the weighing.

FCC_DATA_DIR (Group 45.9, set only by a host test run) puts the file in that run's
own folder; dev's container and prod never set it, and keep this module's data/."""
from __future__ import annotations

import json
import os
import threading
import time

import atomic_store
import state  # type: ignore

_STORE_PATH = (os.path.join(os.environ["FCC_DATA_DIR"], "weigh_stamps.json")
               if os.environ.get("FCC_DATA_DIR")
               else os.path.join(os.path.dirname(__file__), "data", "weigh_stamps.json"))
_LOCK = threading.RLock()
_KEEP_S = 14 * 24 * 3600     # a queued print's charge waits 72 h at most


def _load():
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        state.logger.warning(f"⚖️ couldn't read {_STORE_PATH} ({e}); FCC can't tell when a spool "
                             f"was weighed until it can.")
        return {}


def _save(data):
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    atomic_store.replace_with_retry(tmp, _STORE_PATH)


def note(sid, how, at=None):
    """Stamp spool `sid` as weighed now (or at `at`, epoch seconds) on screen `how`.
    Never raises: a store FCC can't write is one WARNING line."""
    try:
        sid = str(int(sid))
    except (TypeError, ValueError):
        return
    stamp = {"at": float(time.time() if at is None else at), "how": str(how or "a weight save")}
    try:
        with _LOCK:
            data = _load()
            cutoff = stamp["at"] - _KEEP_S
            data = {k: v for k, v in data.items()
                    if isinstance(v, dict) and float(v.get("at") or 0) >= cutoff}
            data[sid] = stamp
            _save(data)
    except Exception as e:
        try:
            state.logger.warning(f"⚖️ couldn't note that spool #{sid} was weighed ({e}).")
        except Exception:
            pass


def last(sid):
    """{"at", "how"} of FCC's last weighing of `sid`, or None."""
    try:
        key = str(int(sid))
    except (TypeError, ValueError):
        return None
    with _LOCK:
        got = _load().get(key)
    if not isinstance(got, dict):
        return None
    try:
        return {"at": float(got.get("at")), "how": str(got.get("how") or "a weight save")}
    except (TypeError, ValueError):
        return None


def weighed_after(sid, since):
    """FCC's last weighing of `sid` when it came after `since` (epoch seconds),
    else None (none, an older one, or no `since`)."""
    stamp = last(sid)
    try:
        return stamp if stamp is not None and since is not None and stamp["at"] > float(since) else None
    except (TypeError, ValueError):
        return None
