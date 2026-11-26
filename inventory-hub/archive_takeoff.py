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
one record per spool, {sid, place, since, tries, next_at, last_error, listed, rev,
quiet?}) and tried again:
  - by the print monitor's loop (FCC's only always-on loop), on a thread of its own
    (`start_retry_pass`: a slow Spoolman never holds up the watcher's print edges,
    the 2026-11-11 hotfix's rule; Group 63 review, K29): first ~30 s after, then
    backing off (RETRY_DELAYS_S). After LIST_AFTER_TRIES failed tries it is
    listed: one WARNING Activity Log line names the spool and its place, with a
    "Take it off" button (POST /api/spool/archive_takeoff, `take_off_now`), shown
    again after every restart while it waits (`resurface`, from
    startup_migrations). FCC keeps trying every SLOW_RETRY_S after that, and says
    so when one lands;
  - before any move onto that place (`retry_at`, from logic.perform_smart_move,
    the auto-deploy chain's head included): Derek's hook above.
Each try re-reads the spool strictly and writes only while it is still archived
exactly where the record says: a spool weighed back into stock, moved, already
taken off or deleted since is dropped with an INFO line, never written.

Group 63 review:
  - One try at a time per spool (`_CLAIMS`, as print_monitor's _FETCH_CLAIMS): the
    loop, a move's hook and the button never write the same take-off twice; a try
    works from the record as it is when it starts, and drops or reschedules it only
    while it is still that record (`rev`, which note_stuck bumps), never a record
    written down again meanwhile (K28).
  - A spool taken off a head on a later try lets its own single-slot box go only
    while no other spool runs on that head from that box (K24: the next spool put
    into the same PolyDryer and loaded meanwhile keeps its attachment); a box FCC
    can't read keeps it (a stale attachment shows with Unbind, a lost one shows
    nothing).
  - A record with no place (`place` '') is a weigh to empty whose answer was lost
    and couldn't be read back (K26): its spool is taken off wherever it is archived
    now, and a spool found in stock or Unassigned is forgotten quietly (`quiet`),
    so a write that never landed leaves no misleading line.
  - A store file that can't be read is never read as "nothing written down" (C5):
    the retries skip it with one ERROR line, the button says so, and a write sets
    the file aside (renamed, kept for a person) before it starts a new list.

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

# The spools a try is working on now (K28), and whether a retry pass runs (K29).
_CLAIMS = set()
_PASS = {"running": False}
# The reasons an unreadable store has been said for, so the loop says each once.
_UNREADABLE_SAID = set()
# Review round 2: a store write that fails inside a try (a disk that refuses
# writes) is said once per spool and kind, and the spool's next try is kept here
# in memory, so the loop still backs off when the store can't hold it.
_STORE_FAIL_SAID = set()
_NEXT_AT_MEM = {}


class StoreUnreadable(Exception):
    """The store's file is there but can't be read: not JSON, not an object, or the
    disk refusing it. Never read as "nothing written down" (Group 63 review, C5)."""


def _key(sid):
    return str(int(sid))


def _place(loc):
    return str(loc if loc is not None else '').strip().strip('"')


def _where(place):
    """A record's place in words: its LocationID, escaped (the Activity Log is
    HTML), or "its place" for a record that names none (K26)."""
    return html.escape(place, quote=False) if place else "its place"


def _load():
    """The records by spool id; {} when nothing has been written down yet (no
    file). Raises StoreUnreadable for a file that can't be read."""
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:   # ValueError: json's decode errors, a bad encoding
        raise StoreUnreadable(str(e) or type(e).__name__) from e
    if not isinstance(data, dict):
        raise StoreUnreadable("it holds no list of spools")
    return data


def _say_unreadable(e):
    """One ERROR line per reason per process: the retry loop reads the store on
    every tick."""
    why = str(e)
    if (_STORE_PATH, why) in _UNREADABLE_SAID:
        return
    _UNREADABLE_SAID.add((_STORE_PATH, why))
    state.add_log_entry(
        f"❌ FCC couldn't read its list of archived spools to take off "
        f"({html.escape(os.path.basename(_STORE_PATH), quote=False)}: {html.escape(why, quote=False)}), "
        f"so the spools in it aren't tried again until it can.", "ERROR", "ff4444")


def _load_for_write():
    """The records, to change and save. A file that can't be read is set aside
    first (renamed, never overwritten: its records are a person's to put back), and
    a new list is started, said in one ERROR line. Raises StoreUnreadable when it
    can't even be set aside."""
    try:
        return _load()
    except StoreUnreadable as e:
        aside = f"{_STORE_PATH}.unreadable-{int(time.time())}"
        try:
            os.replace(_STORE_PATH, aside)
        except OSError as e2:
            raise StoreUnreadable(f"{e}; it couldn't be set aside either ({e2})") from e2
        state.add_log_entry(
            f"❌ FCC couldn't read its list of archived spools to take off ({html.escape(str(e), quote=False)}): "
            f"it is kept as {html.escape(os.path.basename(aside), quote=False)}, and a new list was started. "
            f"The spools in the old one aren't tried again.", "ERROR", "ff4444")
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
    """Every spool written down, oldest first ([] when the store can't be read,
    said once)."""
    with _LOCK:
        try:
            return [dict(r) for r in _load().values() if isinstance(r, dict)]
        except StoreUnreadable as e:
            _say_unreadable(e)
            return []


def get(sid):
    """Spool `sid`'s record, or None. Raises StoreUnreadable."""
    with _LOCK:
        rec = _load().get(_key(sid))
        return dict(rec) if isinstance(rec, dict) else None


def drop(sid, rev=None):
    """Forget spool `sid`; with `rev`, only while its record is still that one (a
    record written down again since is kept). Returns the record it held, or None."""
    with _LOCK:
        data = _load_for_write()
        rec = data.get(_key(sid))
        if not isinstance(rec, dict) or (rev is not None and rec.get('rev') != rev):
            return None
        data.pop(_key(sid), None)
        _save(data)
        _NEXT_AT_MEM.pop(_key(sid), None)
        return rec


def _store_write_failed(sid, what, e, next_at):
    """A store write inside a try failed (review round 2): one ERROR line per spool
    and kind, and the spool's next try kept in memory (`next_at`), so the loop
    doesn't try it on every tick."""
    with _LOCK:
        _NEXT_AT_MEM[_key(sid)] = float(next_at)
        said = (_key(sid), what) in _STORE_FAIL_SAID
        _STORE_FAIL_SAID.add((_key(sid), what))
    if not said:
        state.add_log_entry(
            f"❌ FCC couldn't update its list of archived spools to take off for #{sid} ({what}: "
            f"{html.escape(str(e), quote=False)}).", "ERROR", "ff4444")


def _next_at(rec):
    """When `rec`'s next try is due: the later of the stored time and the one kept
    in memory after a store write failed."""
    stored = float((rec or {}).get('next_at') or 0)
    try:
        mem = _NEXT_AT_MEM.get(_key((rec or {}).get('sid')), 0)
    except (TypeError, ValueError):
        mem = 0
    return max(stored, float(mem or 0))


def note_stuck(sid, place, why, now=None, quiet=False):
    """Write down a take-off that failed (/api/spool/update's, the wizard's): spool
    `sid`, archived at `place` ('' when where it is couldn't be read: K26). A spool
    written down already keeps its tries and its `listed`; its place and reason are
    brought up to date, and its `rev` moves on. `quiet`: a spool found in stock or
    Unassigned is forgotten with no Activity Log line (a lost answer's guess).
    Returns the record. Raises StoreUnreadable when the store can't be written."""
    now = time.time() if now is None else float(now)
    with _LOCK:
        data = _load_for_write()
        key = _key(sid)
        rec = data.get(key) if isinstance(data.get(key), dict) else None
        if rec is None:
            rec = {"sid": int(sid), "since": now, "tries": 0, "listed": False}
        rec["place"] = _place(place)
        rec["last_error"] = str(why or '')[:400]
        rec["next_at"] = now + RETRY_DELAYS_S[0]
        rec["rev"] = int(rec.get("rev") or 0) + 1
        if quiet:
            rec["quiet"] = True
        else:
            rec.pop("quiet", None)
        data[key] = rec
        _save(data)
        _NEXT_AT_MEM.pop(key, None)
        return dict(rec)


def _release_box(sid, place, pre_extra, check_feed=True, emptied=True):
    """A spool taken off a head lets its own single-slot box go (Derek's 42.1 rule:
    by any path), as logic._release_single_slot_box does; best-effort. On a try
    after the save's own request (`check_feed`), only while no other spool runs on
    that head from that box (K24: the next spool put into the same PolyDryer and
    loaded since keeps the attachment). `emptied`: its record reads empty (the log
    line says "archived empty" only then: a ticked spool has grams left)."""
    head = _place(place).upper()
    try:
        if not head or head not in (locations_db.get_active_printer_map() or {}):
            return
        box = _place((pre_extra or {}).get('physical_source')).upper()
        if not box or box == head:
            return
        if check_feed and spoolman_api._box_runs_another(box, head, sid):
            return
        if locations_db.detach_single_slot_box(box, head):
            state.add_log_entry(f"🔓 {html.escape(box, quote=False)} detached from "
                                f"{html.escape(head, quote=False)} — its spool #{sid} was archived"
                                f"{' empty' if emptied else ''}", "INFO")
    except Exception as e:
        state.logger.warning(f"63.2: the box release for #{sid} skipped: {e}")


def take_off(sid, rec, same_request=False):
    """Take spool `sid` off the place its record `rec` (as Spoolman answered it)
    has it at, as an archive does: Unassigned, its slot and trail blank, its notes
    by the one rule (spoolman_api._archive_note_extras: the place it left, the
    before-the-box note used up), and its own single-slot box released when it was
    on a head (`same_request`: the save that archived it, when the spool was the
    head's only one until then; a later try checks the box first, K24). Asks
    nothing about a print, as the archive edge never has (a spool weighed empty is
    in the person's hand).

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
    _release_box(sid, place, pre_extra, check_feed=not same_request, emptied=_reads_empty(rec))
    return True, None


def _reads_empty(rec):
    """Whether spool record `rec` has no filament left on it: Spoolman's
    remaining_weight, else its effective capacity less what is used. A record
    that says neither reads as empty (the take-off's usual case: a weigh to 0 g)."""
    try:
        left = (rec or {}).get('remaining_weight')
        if left is not None and not isinstance(left, bool):
            return float(left) <= 0
        cap = spoolman_api.effective_initial_weight(rec)
        used = (rec or {}).get('used_weight')
        if cap is None or used is None:
            return True
        return float(cap) - float(used) <= 0
    except (TypeError, ValueError):
        return True


def _button(sid, place=''):
    """The listed line's button, in the line itself so every view of the log has it
    (the audit report's 📝 pattern); the page's one delegated click posts it, with
    the place the line names (`data-takeoff-place`, review round 3: take_off_now
    reads a spool archived anywhere else as one FCC left there)."""
    at = f' data-takeoff-place="{html.escape(_place(place), quote=True)}"' if _place(place) else ''
    return (' <button type="button" class="btn btn-sm btn-outline-warning ms-2 py-0 px-1 fcc-takeoff-btn" '
            f'data-takeoff-spool="{int(sid)}"{at}>Take it off</button>')


def _sentence(words):
    """`words` ending in one full stop, for a sentence that goes on after it (K27:
    refusal_words' "Spoolman refused it: database is locked" has none)."""
    said = str(words or '').rstrip()
    return said if said.endswith(('.', '!', '?')) else said + '.'


def _log_listed(rec, again=False):
    sid, place = rec.get('sid'), _place(rec.get('place'))
    why = spoolman_api.refusal_words(rec.get('last_error') or '') if rec.get('last_error') else ''
    reason = f" ({html.escape(why.rstrip('.'), quote=False)})" if why else ""
    lead = "Still waiting from before FCC restarted: " if again else ""
    if rec.get('quiet'):
        # A lost save's guess (review round 2): FCC never saw it archived there, so
        # the words hedge, whatever place the guess names.
        msg = (f"⚠️ {lead}Spool #{sid} was weighed empty while Spoolman wasn't answering, and FCC "
               f"couldn't check whether it came off {_where(place)}{reason}. If it is still there, it is "
               f"hidden there until it comes off, and FCC keeps trying.{_button(sid, place)}")
    elif place:
        msg = (f"⚠️ {lead}Spool #{sid} is archived but still at {_where(place)}: "
               f"FCC couldn't take it off there{reason}. "
               f"It is hidden there until it comes off, and FCC keeps trying.{_button(sid, place)}")
    else:
        msg = (f"⚠️ {lead}Spool #{sid} was weighed empty, and FCC couldn't check that it came off "
               f"its place{reason}. If it is still there, it is hidden there until it comes off, "
               f"and FCC keeps trying.{_button(sid)}")
    state.add_log_entry(msg, "WARNING", "ffaa00", meta={"type": META_TYPE, "spool_id": sid, "place": place})


def _failed(sid, now, why, rev=None):
    """A try that didn't land: the next one is scheduled, and the spool is listed
    once it has failed LIST_AFTER_TRIES times; with `rev`, only while its record is
    still that one. A store that can't be written keeps the next try in memory
    (review round 2: the loop tried the spool on every tick)."""
    listed = None
    nxt = now + SLOW_RETRY_S
    try:
        with _LOCK:
            data = _load_for_write()
            rec = data.get(_key(sid))
            if not isinstance(rec, dict) or (rev is not None and rec.get('rev') != rev):
                return 'failed'
            tries = int(rec.get('tries') or 0) + 1
            rec['tries'] = tries
            rec['last_error'] = str(why or '')[:400]
            nxt = now + (RETRY_DELAYS_S[tries] if tries < min(LIST_AFTER_TRIES, len(RETRY_DELAYS_S))
                         else SLOW_RETRY_S)
            rec['next_at'] = nxt
            if tries >= LIST_AFTER_TRIES and not rec.get('listed'):
                rec['listed'] = True
                listed = dict(rec)
            data[_key(sid)] = rec
            _save(data)
            _NEXT_AT_MEM.pop(_key(sid), None)
    except (OSError, ValueError, StoreUnreadable) as e:
        _store_write_failed(sid, "its next try", e, nxt)
        return 'failed'
    if listed:
        _log_listed(listed)
    return 'failed'


def _drop_after(sid, rev, now):
    """Forget a spool a try settled (review round 2: a store write that fails here
    never escapes the try; its line is written already)."""
    try:
        drop(sid, rev)
    except (OSError, ValueError, StoreUnreadable) as e:
        _store_write_failed(sid, "forgetting it", e, now + SLOW_RETRY_S)


def _claim(sid):
    with _LOCK:
        if _key(sid) in _CLAIMS:
            return False
        _CLAIMS.add(_key(sid))
        return True


def _unclaim(sid):
    with _LOCK:
        _CLAIMS.discard(_key(sid))


def _try(rec, now, source, target=None):
    """One try at taking a written-down spool off its place. Returns what happened:
    'landed', 'off' (it is Unassigned already), 'refilled', 'moved', 'gone' (each
    dropped), 'failed' (kept, its next try scheduled), 'busy' (another try is
    working on it now: K28) or 'none' (nothing is written down for it any more).
    `rec` names the spool; the try works from its record as it is now. `target`:
    the place a move is about to go onto (retry_at), for its log line's words."""
    sid = (rec or {}).get('sid')
    if sid is None:
        return 'none'
    if not _claim(sid):
        return 'busy'
    try:
        return _try_claimed(sid, now, source, target)
    finally:
        _unclaim(sid)


def _try_claimed(sid, now, source, target=None):
    try:
        cur = get(sid)
    except StoreUnreadable as e:
        _say_unreadable(e)
        return 'failed'
    if cur is None:
        return 'none'
    place, rev, quiet = _place(cur.get('place')), cur.get('rev'), bool(cur.get('quiet'))
    got, answered = spoolman_api.get_spool_answer(sid)
    if not answered:
        return _failed(sid, now, "Spoolman didn't answer.", rev)
    if got is None:
        return _failed(sid, now, "Spoolman's answer couldn't be read.", rev)
    esc = _where(place)

    def forget(outcome, words):
        # The line first: a store write that fails after it can't lose it.
        if quiet:
            state.logger.info(f"63.2: #{sid} needs no take-off ({outcome})")
        else:
            state.add_log_entry(words, "INFO")
        _drop_after(sid, rev, now)
        return outcome

    if not isinstance(got, dict) or str(got.get('id')) != str(sid):
        return forget('gone', f"ℹ️ Spool #{sid} is gone from Spoolman, so there is nothing to take off {esc}")
    if not got.get('archived'):
        return forget('refilled', f"ℹ️ Spool #{sid} is back in stock, so FCC no longer takes it off {esc}")
    now_at = _place(got.get('location'))
    if not now_at:
        return forget('off', f"ℹ️ Archived Spool #{sid} is off {esc} now (Unassigned)")
    if place and now_at.upper() != place.upper():
        return forget('moved', f"ℹ️ Archived Spool #{sid} is at {html.escape(now_at, quote=False)} now, "
                               f"so FCC left it there")
    landed, why = take_off(sid, got)
    if landed:
        if source == "move":
            # Onto the place it came off, or a move somewhere else (a record with
            # no place is tried before every move: review round 2's words).
            onto = _place(target).upper() if target else ''
            tail = " before a move onto it" if onto and onto == now_at.upper() else " before a move"
        else:
            tail = {"button": "", "retry": " on a later try"}.get(source, "")
        state.add_log_entry(f"📦 Took archived Spool #{sid} off {html.escape(now_at, quote=False)}{tail}: "
                            f"it is Unassigned now", "INFO", "00ccff")
        _drop_after(sid, rev, now)
        return 'landed'
    return _failed(sid, now, why, rev)


def retry_due(now=None):
    """One try for every spool whose next try is due, on the calling thread (the
    pass `start_retry_pass` starts). Never raises."""
    now = time.time() if now is None else float(now)
    try:
        for rec in pending():
            try:
                if _next_at(rec) <= now:
                    _try(rec, now, 'retry')
            except Exception as e:
                state.logger.warning(f"63.2: a take-off retry for #{rec.get('sid')} skipped: {e}")
    except Exception as e:
        state.logger.warning(f"63.2: the take-off retries skipped: {e}")


def start_retry_pass(now=None):
    """The print monitor's tick (Group 63 review, K29): when a retry is due, one
    pass of retry_due on a thread of its own, so a slow Spoolman (each try can wait
    on several timeouts) never holds up the watcher's print edges; none while the
    last pass still runs. Returns whether it started one. Never raises."""
    try:
        when = time.time() if now is None else float(now)
        if not any(_next_at(r) <= when for r in pending()):
            return False
        with _LOCK:
            if _PASS["running"]:
                return False
            _PASS["running"] = True

        def run():
            try:
                retry_due(now)
            finally:
                with _LOCK:
                    _PASS["running"] = False

        try:
            threading.Thread(target=run, name="fcc-archive-takeoff-retry", daemon=True).start()
        except Exception:
            with _LOCK:
                _PASS["running"] = False
            raise
        return True
    except Exception as e:
        state.logger.warning(f"63.2: the take-off retry pass didn't start: {e}")
        return False


def retry_at(place, now=None, placeless=True):
    """Before a move onto `place` (logic.perform_smart_move, the auto-deploy
    chain's head too; Derek's hook): one try for every spool written down at that
    place, whatever its slot, and for every one whose place couldn't be read (K26;
    `placeless=False` leaves those out: the chain's head, after the outer move tried
    them a moment before, review round 2). A Spoolman that can't take this write
    would refuse the move's too. Never raises, never blocks the move."""
    lid = _place(place).upper()
    if not lid:
        return
    now = time.time() if now is None else float(now)
    try:
        for rec in pending():
            at = _place(rec.get('place')).upper()
            if at == lid or (placeless and not at):
                _try(rec, now, 'move', target=lid)
    except Exception as e:
        state.logger.warning(f"63.2: the take-off retry before a move onto {lid} skipped: {e}")


def take_off_now(sid, listed_at=None):
    """The listed line's "Take it off" button: one try now. Returns (ok, msg), the
    msg in words for the page's toast. `listed_at`: the place the line names (its
    button's `data-takeoff-place`; None from an older line or a line that names no
    place)."""
    try:
        rec = get(sid)
    except StoreUnreadable as e:
        _say_unreadable(e)
        return False, (f"FCC couldn't read its list of archived spools to take off ({e}), "
                       f"so nothing was done for #{int(sid)}.")
    if rec is None:
        # Nothing written down: the spool says whether that is the whole story
        # (review round 2: after a store was set aside, a listed line's button
        # answered "nothing left" while its spool stayed archived, hidden). Review
        # round 3: a spool archived somewhere other than the place its line names
        # was moved there, and a try dropped it as left there (Derek's 43.2 rule:
        # an archived spool stays where it was put), so it is told so, as a press
        # before that drop was; only one still at that place, or a line that names
        # none, is told to unassign it.
        got, answered = spoolman_api.get_spool_answer(sid)
        if not answered or got is None:
            return False, (f"FCC has #{int(sid)} on no list to take off, and couldn't check it in Spoolman just "
                           f"now: try again in a moment.")
        at = _place(got.get('location')) if isinstance(got, dict) else ''
        named = _place(listed_at)
        if isinstance(got, dict) and str(got.get('id')) == str(sid) and got.get('archived') and at:
            if named and at.upper() != named.upper():
                return True, f"#{int(sid)} isn't at {named} any more, so it was left where it is."
            return False, (f"#{int(sid)} is still archived at {at}, and FCC's list of spools to take off "
                           f"doesn't hold it: set its Location to Unassigned in Edit Spool to take it off.")
        return True, f"FCC has nothing left to take off for #{int(sid)}."
    place = _place(rec.get('place'))
    where = place or "its place"
    outcome = _try(rec, time.time(), 'button')
    if outcome == 'busy':
        return False, f"FCC is trying to take #{int(sid)} off {where} right now: look again in a moment."
    if outcome == 'failed':
        try:
            now = get(sid) or rec
        except StoreUnreadable:
            now = rec
        why = spoolman_api.refusal_words(now.get('last_error') or "Spoolman didn't answer.")
        return False, f"Couldn't take #{int(sid)} off {where}: {_sentence(why)} FCC keeps trying."
    return True, {
        'landed': f"Took #{int(sid)} off {where}: it is Unassigned now.",
        'off': f"#{int(sid)} is off {where} already.",
        'refilled': f"#{int(sid)} is back in stock, so it was left where it is.",
        'moved': f"#{int(sid)} isn't at {where} any more, so it was left where it is.",
        'gone': f"#{int(sid)} is gone from Spoolman.",
        'none': f"FCC has nothing left to take off for #{int(sid)}.",
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
