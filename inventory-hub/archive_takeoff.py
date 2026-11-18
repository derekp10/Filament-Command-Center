"""Group 63.2: a spool weighed to empty that FCC couldn't take off its place.

A weigh to empty archives a spool and takes it off its place: the archive edge in
spoolman_api.update_spool. When FCC can't read the spool just before the save
(Spoolman restarting for an update, a network blip, "database is locked"), the
edge can't run, and the weigh page's own `archived: true` archives the spool
where it stands. /api/spool/update then takes it off itself (`take_off`, from the
record Spoolman just answered), so a closed tab can't leave it there. When that
write fails too, the spool is archived on its toolhead or in its slot, and every
FCC view hides it there (they list spools in stock).

Derek, 2026-11-18: *"If we can resolve by retry then thats good ... So I'm thinking
a try, like in the retry and list, List if it never resonves, and if by the time
that a new spool is being assigned to the location with a unupdated archiveds
spool, we try again to perform the update?"*

So a take-off that failed is written down here (data/pending_archive_takeoffs.json:
one record per spool, {sid, place, since, tries, next_at, last_error, listed}) and
tried again:
  - by the print monitor's loop (FCC's only always-on loop): first ~30 s after,
    then backing off (RETRY_DELAYS_S). After LIST_AFTER_TRIES failed tries it is
    listed: one WARNING Activity Log line names the spool and its place, with a
    "Take it off" button (POST /api/spool/archive_takeoff, `take_off_now`), shown
    again after every restart while it waits (`resurface`, from
    startup_migrations). FCC keeps trying every SLOW_RETRY_S after that, and says
    so when one lands;
  - before any move onto that place (`retry_at`, from logic.perform_smart_move):
    Derek's hook above.
Each try re-reads the spool strictly and writes only while it is still archived
exactly where the record says: a spool weighed back into stock, moved, already
taken off or deleted since is dropped with an INFO line, never written.

A flat module (tests/test_no_direct_extra_patch.py scans the root); it reads
FCC_DATA_DIR once at import, as the other stores do, and starts nothing at import.
It imports spoolman_api and locations_db, never logic (logic imports it).
"""
from __future__ import annotations

import html
import json
import os
import threading
import time

import atomic_store
import locations_db
import spoolman_api
import state

# Overridable by tests (monkeypatch this attribute to a tmp path). FCC_DATA_DIR
# (Group 45.9, set only by a host test run) puts it in that run's own folder;
# dev's container and prod never set it, and keep this module's data/.
_STORE_PATH = (os.path.join(os.environ["FCC_DATA_DIR"], "pending_archive_takeoffs.json")
               if os.environ.get("FCC_DATA_DIR")
               else os.path.join(os.path.dirname(__file__), "data", "pending_archive_takeoffs.json"))
_LOCK = threading.RLock()
_MAX_ENTRIES = 200

# Seconds before each retry, from the take-off that failed: ~30 s, then backing
# off. After LIST_AFTER_TRIES failed retries the spool is listed, and FCC goes on
# trying every SLOW_RETRY_S.
RETRY_DELAYS_S = (30, 60, 120, 240, 480)
LIST_AFTER_TRIES = 5
SLOW_RETRY_S = 600

# The Activity Log line's `meta`, for a page that looks for it.
META_TYPE = "archive_takeoff_pending"


def _key(sid):
    return str(int(sid))


def _place(loc):
    return str(loc if loc is not None else '').strip().strip('"')


def _load():
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def _save(data):
    if len(data) > _MAX_ENTRIES:
        data = dict(list(data.items())[-_MAX_ENTRIES:])
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # 32.1 — retry on the Windows host↔container bind-mount sharing collision.
    atomic_store.replace_with_retry(tmp, _STORE_PATH)


def pending():
    """Every spool written down, oldest first."""
    with _LOCK:
        return [dict(r) for r in _load().values() if isinstance(r, dict)]


def get(sid):
    with _LOCK:
        rec = _load().get(_key(sid))
        return dict(rec) if isinstance(rec, dict) else None


def drop(sid):
    """Forget spool `sid`. Returns the record it held, or None."""
    with _LOCK:
        data = _load()
        rec = data.pop(_key(sid), None)
        if rec is not None:
            _save(data)
        return rec


def note_stuck(sid, place, why, now=None):
    """Write down a take-off that failed (/api/spool/update's): spool `sid`,
    archived at `place`. A spool written down already keeps its tries and its
    `listed`; its place and reason are brought up to date. Returns the record."""
    now = time.time() if now is None else float(now)
    with _LOCK:
        data = _load()
        key = _key(sid)
        rec = data.get(key) if isinstance(data.get(key), dict) else None
        if rec is None:
            rec = {"sid": int(sid), "since": now, "tries": 0, "listed": False}
        rec["place"] = _place(place)
        rec["last_error"] = str(why or '')[:400]
        rec["next_at"] = now + RETRY_DELAYS_S[0]
        data[key] = rec
        _save(data)
        return dict(rec)


def _release_box(sid, place, pre_extra):
    """A spool taken off a head lets its own single-slot box go (Derek's 42.1 rule:
    by any path), as logic._release_single_slot_box does; best-effort."""
    head = _place(place).upper()
    try:
        if not head or head not in (locations_db.get_active_printer_map() or {}):
            return
        box = _place((pre_extra or {}).get('physical_source')).upper()
        if box and box != head and locations_db.detach_single_slot_box(box, head):
            state.add_log_entry(f"🔓 {html.escape(box, quote=False)} detached from "
                                f"{html.escape(head, quote=False)} — its spool #{sid} was archived empty",
                                "INFO")
    except Exception as e:
        state.logger.warning(f"63.2: the box release for #{sid} skipped: {e}")


def take_off(sid, rec):
    """Take spool `sid` off the place its record `rec` (as Spoolman answered it)
    has it at, as an archive does: Unassigned, its slot and trail blank, its notes
    by the one rule (spoolman_api._archive_note_extras: the place it left, the
    before-the-box note used up), and its own single-slot box released when it was
    on a head. Asks nothing about a print, as the archive edge never has (a spool
    weighed empty is in the person's hand).

    Returns (landed, why): `why` is Spoolman's refusal (LAST_SPOOLMAN_ERROR) when
    it didn't land. It reports a failed write only by what it returns, so it is in
    tests/test_spoolman_write_sites.py's WRAPPER_WRITERS, and its callers read it.
    A write whose answer was lost reads as failed here; the next try re-reads, and
    finds it off."""
    place = _place((rec or {}).get('location'))
    pre_extra = (rec or {}).get('extra') if isinstance((rec or {}).get('extra'), dict) else {}
    extra = {'container_slot': '', 'physical_source': '', 'physical_source_slot': ''}
    extra.update(spoolman_api._archive_note_extras(pre_extra, place))
    out = spoolman_api.update_spool(sid, {'location': '', 'extra': extra})
    if not out:
        why = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman didn't answer."
        # update_spool's timeout is a READ timeout, so a write whose answer was lost
        # may have landed: one strict re-read before it is called failed (Group 63.5's
        # rule), or a take-off that landed would be written down as stuck.
        back, answered = spoolman_api.get_spool_answer(sid)
        if not (answered and isinstance(back, dict) and str(back.get('id')) == str(sid)
                and back.get('archived') and not _place(back.get('location'))):
            return False, why
        state.logger.warning(f"63.2: taking #{sid} off {place} answered {why!r}, but a re-read shows it off")
    _release_box(sid, place, pre_extra)
    return True, None


def _button(sid):
    """The listed line's button, in the line itself so every view of the log has it
    (the audit report's 📝 pattern); the page's one delegated click posts it."""
    return (' <button type="button" class="btn btn-sm btn-outline-warning ms-2 py-0 px-1 fcc-takeoff-btn" '
            f'data-takeoff-spool="{int(sid)}">Take it off</button>')


def _log_listed(rec, again=False):
    sid, place = rec.get('sid'), _place(rec.get('place'))
    why = spoolman_api.refusal_words(rec.get('last_error') or '') if rec.get('last_error') else ''
    reason = f" ({html.escape(why.rstrip('.'), quote=False)})" if why else ""
    lead = "Still waiting from before FCC restarted: " if again else ""
    msg = (f"⚠️ {lead}Spool #{sid} is archived but still at {html.escape(place, quote=False)}: "
           f"FCC couldn't take it off there{reason}. "
           f"It is hidden there until it comes off, and FCC keeps trying.{_button(sid)}")
    state.add_log_entry(msg, "WARNING", "ffaa00", meta={"type": META_TYPE, "spool_id": sid, "place": place})


def _failed(sid, now, why):
    """A try that didn't land: the next one is scheduled, and the spool is listed
    once it has failed LIST_AFTER_TRIES times."""
    listed = None
    with _LOCK:
        data = _load()
        rec = data.get(_key(sid))
        if not isinstance(rec, dict):
            return 'failed'
        tries = int(rec.get('tries') or 0) + 1
        rec['tries'] = tries
        rec['last_error'] = str(why or '')[:400]
        rec['next_at'] = now + (RETRY_DELAYS_S[tries] if tries < min(LIST_AFTER_TRIES, len(RETRY_DELAYS_S))
                                else SLOW_RETRY_S)
        if tries >= LIST_AFTER_TRIES and not rec.get('listed'):
            rec['listed'] = True
            listed = dict(rec)
        data[_key(sid)] = rec
        _save(data)
    if listed:
        _log_listed(listed)
    return 'failed'


def _try(rec, now, source):
    """One try at taking a written-down spool off its place. Returns what happened:
    'landed', 'off' (it is Unassigned already), 'refilled', 'moved', 'gone' (each
    dropped), or 'failed' (kept, its next try scheduled)."""
    sid, place = rec.get('sid'), _place(rec.get('place'))
    got, answered = spoolman_api.get_spool_answer(sid)
    if not answered:
        return _failed(sid, now, "Spoolman didn't answer.")
    if got is None:
        return _failed(sid, now, "Spoolman's answer couldn't be read.")
    esc = html.escape(place, quote=False)
    if not isinstance(got, dict) or str(got.get('id')) != str(sid):
        drop(sid)
        state.add_log_entry(f"ℹ️ Spool #{sid} is gone from Spoolman, so there is nothing to take off {esc}", "INFO")
        return 'gone'
    if not got.get('archived'):
        drop(sid)
        state.add_log_entry(f"ℹ️ Spool #{sid} is back in stock, so FCC no longer takes it off {esc}", "INFO")
        return 'refilled'
    now_at = _place(got.get('location'))
    if not now_at:
        drop(sid)
        state.add_log_entry(f"ℹ️ Archived Spool #{sid} is off {esc} now (Unassigned)", "INFO")
        return 'off'
    if now_at.upper() != place.upper():
        drop(sid)
        state.add_log_entry(f"ℹ️ Archived Spool #{sid} is at {html.escape(now_at, quote=False)} now, "
                            f"so FCC left it there", "INFO")
        return 'moved'
    landed, why = take_off(sid, got)
    if landed:
        drop(sid)
        tail = {"move": " before a move onto it", "button": "", "retry": " on a later try"}.get(source, "")
        state.add_log_entry(f"📦 Took archived Spool #{sid} off {esc}{tail}: it is Unassigned now", "INFO", "00ccff")
        return 'landed'
    return _failed(sid, now, why)


def retry_due(now=None):
    """The print monitor's loop: one try for every spool whose next try is due.
    Never raises."""
    now = time.time() if now is None else float(now)
    try:
        for rec in pending():
            try:
                if float(rec.get('next_at') or 0) <= now:
                    _try(rec, now, 'retry')
            except Exception as e:
                state.logger.warning(f"63.2: a take-off retry for #{rec.get('sid')} skipped: {e}")
    except Exception as e:
        state.logger.warning(f"63.2: the take-off retries skipped: {e}")


def retry_at(place, now=None):
    """Before a move onto `place` (logic.perform_smart_move; Derek's hook): one try
    for every spool written down at that place, whatever its slot. A Spoolman that
    can't take this write would refuse the move's too. Never raises, never blocks
    the move."""
    lid = _place(place).upper()
    if not lid:
        return
    now = time.time() if now is None else float(now)
    try:
        for rec in pending():
            if _place(rec.get('place')).upper() == lid:
                _try(rec, now, 'move')
    except Exception as e:
        state.logger.warning(f"63.2: the take-off retry before a move onto {lid} skipped: {e}")


def take_off_now(sid):
    """The listed line's "Take it off" button: one try now. Returns (ok, msg), the
    msg in words for the page's toast."""
    rec = get(sid)
    if rec is None:
        return True, f"FCC has nothing left to take off for #{int(sid)}."
    place = _place(rec.get('place'))
    outcome = _try(rec, time.time(), 'button')
    if outcome == 'failed':
        now = get(sid) or rec
        why = spoolman_api.refusal_words(now.get('last_error') or "Spoolman didn't answer.")
        return False, f"Couldn't take #{int(sid)} off {place}: {why} FCC keeps trying."
    return True, {
        'landed': f"Took #{int(sid)} off {place}: it is Unassigned now.",
        'off': f"#{int(sid)} is off {place} already.",
        'refilled': f"#{int(sid)} is back in stock, so it was left where it is.",
        'moved': f"#{int(sid)} isn't at {place} any more, so it was left where it is.",
        'gone': f"#{int(sid)} is gone from Spoolman.",
    }.get(outcome, "Done.")


def resurface():
    """At startup (startup_migrations): the listed line again for every spool that
    was listed before the restart and still waits, so its button is there after
    one. Never raises."""
    try:
        for rec in pending():
            if rec.get('listed'):
                _log_listed(rec, again=True)
    except Exception as e:
        state.logger.warning(f"63.2: the take-off re-surface skipped: {e}")
