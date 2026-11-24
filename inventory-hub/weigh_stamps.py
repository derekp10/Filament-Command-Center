"""When FCC itself last weighed each spool, and what FCC itself charged to it
(Group 64, Decision 1; Derek, 2026-11-20).

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

It also keeps each charge FCC lands (Group 64 review, S1). A print charged after
another print's end read (the earlier print's file waited behind the printer's
screen, its download ran long, or its card was applied meanwhile) changed the
spool's used weight by FCC's own hand, which is no weighing: print_deduct takes
those grams off the change before it holds a print.

{"weighed": {sid: {"at": epoch seconds, "how": the screen's words}},
 "charged": {sid: [[epoch seconds, grams], ...]}}: the latest weighing per spool and
every charge, an entry older than _KEEP_S dropped at each write. The file as this
module first wrote it ({sid: stamp}, before it kept charges) is read as weighings. A
store FCC can't read is read as no stamps and no charges (FCC then can't tell, and
fills in the print's grams); a write that fails is one WARNING in hub.log and never
fails the weighing or the charge.

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


def _split(data):
    """(weighings, charges) of the stored dict. The flat form this module first
    wrote ({sid: stamp}, before it kept charges) is all weighings."""
    if not isinstance(data, dict):
        return {}, {}
    if "weighed" in data or "charged" in data:
        w, c = data.get("weighed"), data.get("charged")
        return (w if isinstance(w, dict) else {}), (c if isinstance(c, dict) else {})
    return data, {}


def _at(stamp):
    try:
        return float(stamp.get("at") or 0) if isinstance(stamp, dict) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _charges_of(entries):
    """[(at, grams)] of one spool's stored charges, each read safely."""
    out = []
    for e in entries if isinstance(entries, list) else []:
        try:
            out.append((float(e[0]), float(e[1])))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    return out


def _write(weighed, charged, now):
    cutoff = now - _KEEP_S
    kept = {}
    for sid, entries in charged.items():
        left = [[at, g] for at, g in _charges_of(entries) if at >= cutoff]
        if left:
            kept[sid] = left
    _save({"weighed": {k: v for k, v in weighed.items() if _at(v) >= cutoff}, "charged": kept})


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
            weighed, charged = _split(_load())
            weighed = dict(weighed)
            weighed[sid] = stamp
            _write(weighed, charged, stamp["at"])
    except Exception as e:
        try:
            state.logger.warning(f"⚖️ couldn't note that spool #{sid} was weighed ({e}).")
        except Exception:
            pass


def note_charge(sid, grams, at=None):
    """Note that FCC charged `grams` to spool `sid` (Group 64 review, S1), at `at`
    (epoch seconds: the moment before the write was sent, so a print-end read made
    while it was on its way is never told the charge came after it), else now. A
    charge of nothing notes nothing. Never raises: a store FCC can't write is one
    WARNING line (a print ended before the charge is then held as one FCC can't
    place, its own grams filled in)."""
    try:
        sid = str(int(sid))
        grams = float(grams)
    except (TypeError, ValueError):
        return
    if not grams > 0:
        return
    when = float(time.time() if at is None else at)
    try:
        with _LOCK:
            weighed, charged = _split(_load())
            charged = dict(charged)
            charged[sid] = [[a, g] for a, g in _charges_of(charged.get(sid))] + [[when, round(grams, 4)]]
            _write(weighed, charged, when)
    except Exception as e:
        try:
            state.logger.warning(f"⚖️ couldn't note FCC's charge of {grams:.2f} g to spool #{sid} ({e}).")
        except Exception:
            pass


def charged_after(sid, since):
    """The grams FCC charged to `sid` after `since` (epoch seconds; Group 64 review,
    S1): 0.0 for none, or no `since`."""
    try:
        key = str(int(sid))
        since = float(since)
    except (TypeError, ValueError):
        return 0.0
    with _LOCK:
        _weighed, charged = _split(_load())
    return round(sum(g for at, g in _charges_of(charged.get(key)) if at > since), 4)


def last(sid):
    """{"at", "how"} of FCC's last weighing of `sid`, or None."""
    try:
        key = str(int(sid))
    except (TypeError, ValueError):
        return None
    with _LOCK:
        got = _split(_load())[0].get(key)
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
