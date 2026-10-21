import itertools
import re
import threading
import time
import typing
import urllib.parse
import uuid
import requests
import state
import config_loader
import spoolman_api
import locations_db


def _active_print_info_for_location(location_str, printer_map=None):
    """If `location_str` is a toolhead whose printer is currently PRINTING/
    PAUSED/BUSY, return {'printer_name', 'state', 'toolhead'} so a warning
    can be surfaced. Returns None otherwise (not a toolhead, printer idle,
    or probe failed — fail open, never block moves).

    Used as a shared backend pre-flight so every spool-move surface
    (manage_contents add/remove, smart_move, identify_scan assignment,
    quickswap) inherits the same protection without each endpoint
    re-implementing the lookup.
    """
    if not location_str:
        return None
    loc_up = str(location_str).strip().strip('"').upper()
    if printer_map is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    info = printer_map.get(loc_up)
    if not info:
        return None
    printer_name = info.get('printer_name')
    if not printer_name:
        return None
    try:
        # Deferred import: keeps logic.py usable in unit tests that don't
        # have prusalink_api's `requests` import graph fully satisfied.
        import prusalink_api
        _, fb_url = config_loader.get_api_urls()
        state_dict = prusalink_api.get_printer_state(fb_url, printer_name)
    except Exception:
        state_dict = None
    if not state_dict:
        # The probe couldn't tell (fail open). A printer the page itself saw
        # printing when the user chose still counts as printing (Group 40.3
        # review, C1): the deposit skips its own dialog when its probe sees a
        # print and trusts the move to ask, so a second probe failing open
        # loaded a spool mid-print with no question at all.
        if _page_saw_printing(printer_name, printer_map):
            return {'toolhead': loc_up, 'printer_name': printer_name, 'state': 'PRINTING'}
        return None
    if not state_dict.get('is_active'):
        return None
    return {
        'toolhead': loc_up,
        'printer_name': printer_name,
        'state': state_dict.get('state', 'ACTIVE'),
    }


# Group 40.3 review (C1): the toolheads the page saw printing, for the move in
# progress on this thread (perform_smart_move sets it for its outermost call).
_move_seen_printing = threading.local()


def _page_saw_printing(printer_name, printer_map):
    """True when the page saw a head of `printer_name` printing (the move's
    `seen_printing`): its printer counts as printing whenever the move's own
    probe can't reach it."""
    heads = getattr(_move_seen_printing, 'heads', None)
    if not heads or not printer_name:
        return False
    return any(str((printer_map.get(h) or {}).get('printer_name') or '') == str(printer_name) for h in heads)


def seen_printing_from(data):
    """Group 40.3 review (C1) — the toolheads a page saw printing when the user
    chose (`seen_printing`: the Quick-Swap deposit probes before it posts, and
    leaves the question to FCC when it sees a print). The move treats their
    printers as printing whenever its own probe fails open, so the question
    never hangs on a second probe. Upper-cased head ids; anything that isn't a
    non-blank string is ignored. Read by the three doors that can load a bound
    box slot's head."""
    d = data if isinstance(data, dict) else {}
    value = d.get('seen_printing')
    if not isinstance(value, (list, tuple)):
        return []
    return [str(h).strip().strip('"').upper() for h in value if isinstance(h, str) and h.strip().strip('"')]


def _confirm_scope(confirm):
    """Group 39.1 — what a `confirm_active_print` value covers, as
    (covers_every_head, covered_heads).

    True covers every head: execute_bulk_move, whose plan re-planned from live
    state, and the boolean doors (eject, force-unassign). Falsy covers none.
    An iterable of LocationIDs covers exactly the heads whose active-print
    warning the user saw (`confirmed_toolheads`), so a stale confirm — a grid
    whose slot was rebound to another head — is asked again (R2-08)."""
    if confirm is True:
        return True, frozenset()
    if not confirm:
        return False, frozenset()
    if isinstance(confirm, (str, bytes)):
        heads = [confirm]
    else:
        try:
            heads = list(confirm)
        except TypeError:
            return True, frozenset()   # any other truthy value is the legacy blanket confirm
    return False, frozenset(str(h).strip().strip('"').upper() for h in heads if str(h).strip())


def confirmed_heads(data):
    """Group 39.1 — the `confirm_active_print` a browser move request carries:
    the heads in its `confirmed_toolheads`, i.e. the active-print warnings the
    user actually saw. A bare legacy `confirm_active_print: true` (a stale
    cached page) covers NO head, so the user is asked again: the safe direction,
    and the build-version cache-bust keeps that window short. Used by the five
    move doors (manage_contents add, /api/smart_move, the identify_scan slot
    branch, /api/quickswap, /api/quickswap/return); eject, force-unassign,
    clear-location and the bulk-move commit keep their boolean."""
    heads = (data or {}).get('confirmed_toolheads')
    if isinstance(heads, (list, tuple)):
        return [str(h).strip().strip('"').upper() for h in heads if str(h or '').strip()]
    return []


STALE_PAGE_MSG = ("This FCC page is out of date, so it can't confirm a move during a print. "
                  "Reload the page (Ctrl+F5) and try again.")


def stale_confirm_refusal(data, result):
    """Group 39 review (frontend-12): a page loaded before Group 39 answers an
    active-print confirm with a bare `confirm_active_print: true` and never
    sends `confirmed_toolheads`. The five move doors ignore that flag, so each
    Yes got the same question back, forever, until the page was reloaded. When
    such a request is asked again, this logs and returns the message the door
    answers with instead (as an error, which every old page toasts); otherwise
    None. A move that no longer needs a confirm goes ahead as usual."""
    d = data if isinstance(data, dict) else {}
    if d.get('confirm_active_print') is not True or 'confirmed_toolheads' in d:
        return None
    if not (isinstance(result, dict) and result.get('status') == 'requires_confirm'):
        return None
    state.add_log_entry(f"⚠️ {STALE_PAGE_MSG}", "WARNING", "ffaa00")
    return STALE_PAGE_MSG


def _confirm_covers(confirm, head):
    """True when `confirm` covers the active-print warning for `head`."""
    every, heads = _confirm_scope(confirm)
    return every or str(head or '').strip().strip('"').upper() in heads


def _uncovered_active_heads(touched, confirm, printer_map, spools=None):
    """Group 39.1 — the actively printing heads this move would touch that the
    caller's confirm doesn't cover. One list, so a move answers ONE confirm.

    `touched` is [(head_id, role)] or [(head_id, role, spool_ids)], role
    'destination' (the move's target), 'feeds' (a named slot's bound head,
    which the auto-deploy chain loads) or 'source' (Group 39.4: the head a
    moving spool leaves). An entry's spools are its own `spool_ids`, else the
    move's `spools`. A covered head is never probed. The rest go through
    _active_print_info_for_location, whose per-move memo (perform_smart_move)
    probes each printer once, and which fails open: an unreachable printer is
    not active. Returns [{toolhead, printer_name, state, role, spools}]."""
    every, covered = _confirm_scope(confirm)
    if every:
        return []
    out, seen = [], set()
    for item in touched:
        head, role = item[0], item[1]
        head_spools = item[2] if len(item) > 2 else spools
        h = str(head or '').strip().strip('"').upper()
        if not h or h in seen or h in covered:
            continue
        seen.add(h)
        ap = _active_print_info_for_location(h, printer_map)
        if ap:
            out.append({"toolhead": ap['toolhead'], "printer_name": ap['printer_name'],
                        "state": ap['state'], "role": role,
                        "spools": [int(s) for s in (head_spools or []) if str(s).isdigit()]})
    return out


def _and_list(items):
    """'a', 'a and b', 'a, b and c'."""
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _active_print_message(active_prints, target, residents=(), target_slot=None,
                          skip_feeds=(), named=(), empty_heads=()):
    """The text of an active-print confirm, in Derek's D6 wording (Group 39.4):
      one source   "#42 is loaded on XL-3. Moving it to CR-CT-2-R1 means FCC
                    stops charging this print to it. Continue?"
      several      "#42 is loaded on XL-3 and #57 on XL-1. Moving them to
                    CR-CT-2-R1 means FCC stops charging this XL print to them.
                    Continue?"
      destination  "XL is PRINTING. Loading #57 onto XL-2 unloads #196, so FCC
                    stops charging this print to #196. Continue?"
      feeds        "XL is PRINTING. LR-MDB-1 slot 2 feeds XL-2, so this also
                    loads #42 onto XL-2 and unloads what XL-2 holds. Continue?"
    A head -> head move on one printer is one message: the source sentence
    names both heads. A bound slot's head always gets its own sentence naming
    it: the Yes covers that head, so the user must see it (R2-08). When it is
    on a source's printer, the spool keeps feeding that print, so the source
    sentence drops "stops charging". A destination with no resident keeps the
    sentence the overlays have always shown.

    Group 40.0c's head_fed question names a fed head in its own sentence:
    `skip_feeds` (head ids) leaves out those heads' 'feeds' sentences, and
    `named` (printer names) are printers whose state that sentence already
    gave, so no other sentence repeats it. `empty_heads`: bound heads a strict
    read showed empty, whose 'feeds' sentence doesn't claim to unload anything."""
    sources = [a for a in active_prints if a.get('role') == 'source']
    feeds = [a for a in active_prints if a.get('role') == 'feeds']
    source_printers = {a['printer_name'] for a in sources}
    told = set(source_printers) | set(named)
    skip = {str(h).strip().upper() for h in skip_feeds}
    empties = {str(h).strip().upper() for h in empty_heads}
    out = []
    if sources:
        loaded = [(sid, a['toolhead']) for a in sources for sid in (a.get('spools') or [])]
        if len(loaded) == 1:
            where, pronoun = f"#{loaded[0][0]} is loaded on {loaded[0][1]}", "it"
        else:
            where = _and_list([f"#{loaded[0][0]} is loaded on {loaded[0][1]}"]
                              + [f"#{s} on {h}" for s, h in loaded[1:]])
            pronoun = "them"
        if any(f['printer_name'] in source_printers for f in feeds):
            out.append(f"{where}.")
        else:
            whose = ("this print" if len(loaded) == 1 else
                     f"this {sources[0]['printer_name']} print" if len(source_printers) == 1 else "these prints")
            out.append(f"{where}. Moving {pronoun} to {target} means FCC stops charging {whose} to {pronoun}.")
        if residents:
            out.append(f"It also unloads {_and_list('#' + str(r) for r in residents)} from {target}.")
    for a in active_prints:
        role = a.get('role')
        if role == 'source':
            continue
        if role == 'feeds':
            if str(a.get('toolhead', '')).upper() in skip:
                told.add(a['printer_name'])
                continue
            moving = _and_list('#' + str(s) for s in a.get('spools') or []) if a.get('spools') else "the spool"
            slot = f"{target} slot {target_slot}" if target_slot not in (None, '') else target
            lead = "" if a['printer_name'] in told else f"{a['printer_name']} is {a['state']}. "
            told.add(a['printer_name'])
            holds = ("" if str(a['toolhead']).upper() in empties
                     else f" and unloads what {a['toolhead']} holds")
            out.append(f"{lead}{slot} feeds {a['toolhead']}, so this also loads {moving} onto "
                       f"{a['toolhead']}{holds}.")
            continue
        if a['printer_name'] in told:
            continue
        told.add(a['printer_name'])
        if role == 'destination' and residents:
            gone = _and_list('#' + str(r) for r in residents)
            moving = _and_list('#' + str(s) for s in a.get('spools') or []) if a.get('spools') else "a spool"
            out.append(f"{a['printer_name']} is {a['state']}. Loading {moving} onto {a['toolhead']} "
                       f"unloads {gone}, so FCC stops charging this print to {gone}.")
        else:
            out.append(f"{a['printer_name']} is {a['state']} — moving a spool here will disrupt the print.")
    return " ".join(out) + " Continue?"


def _requires_confirm_answer(active_prints, target, target_slot, residents=(), spools=(), empty_heads=()):
    """Group 39.1 — the ONE shape every move confirm answers in. Groups 40-42
    extend it (40.0c fills fed_heads / can_store); none redefines it.
    `active_print` keeps the first entry's three original keys for existing
    consumers; a replay sends back the heads in `active_prints`. `spools`
    (40.0c): the moving spools the question is about, so a replay names them
    rather than re-reading a buffer that changed while the dialog was open."""
    first = active_prints[0]
    return {
        "status": "requires_confirm",
        "confirm_type": "active_print",
        "active_prints": active_prints,
        "active_print": {k: first[k] for k in ("toolhead", "printer_name", "state")},
        "fed_heads": [],
        "can_store": False,
        "target_slot": None if target_slot in (None, '') else str(target_slot),
        "spools": [int(s) for s in spools if str(s).isdigit()],
        "msg": _active_print_message(active_prints, target, residents, target_slot,
                                     empty_heads=empty_heads),
    }


# ---- Group 40.0c: the "head already fed from elsewhere" confirm -------------------

def confirmed_fed_heads_from(data):
    """Group 40.0c — the fed heads whose "already running another spool" warning
    the user saw (`confirmed_fed_heads`), the fed-head twin of confirmed_heads.
    A current page sends each answer's `confirm_key` ("XL-1#99"): the head AND
    the spools it was running, so a Yes about #99 never covers a spool loaded
    onto XL-1 while the dialog was open (_fed_covered). Only confirm keys count
    (Group 40 review): a bare head id covers the head whatever it runs, which is
    the engine keyword's meaning for internal callers, so a browser request could
    have turned the key scoping and the chain guard off. Read by the three doors
    that can load a bound box slot's head: manage_contents add, /api/smart_move
    and the identify_scan slot branch."""
    heads = (data or {}).get('confirmed_fed_heads')
    if isinstance(heads, (list, tuple)):
        keys = (str(h).strip().strip('"').upper() for h in heads if isinstance(h, str))
        return [k for k in keys if '#' in k]
    return []


def auto_deploy_requested(data):
    """Group 40.0c — a move door's `auto_deploy`, on unless the request says
    false. "Just store it" replays the move with `auto_deploy: false`: the spool
    goes in its slot and the head that slot feeds is left alone (40.0b)."""
    value = (data or {}).get('auto_deploy')
    if value is None or isinstance(value, bool):
        return value is not False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ('false', '0', 'no', 'off')


def record_source_from(data):
    """Group 40.5 (D3, item G) — the box slot the user chose as where a spool put
    on a head came from (the Printer picker's "Record it as coming from…"):
    None when the request names none (the engine's silent 13.6 rule), '' for
    "No box" (record nothing), or {'box', 'slot'}. A malformed value reads as ''
    (record nothing): a source is never guessed from a bad request. Read by
    manage_contents add and /api/smart_move."""
    d = data if isinstance(data, dict) else {}
    if 'record_source' not in d or d.get('record_source') is None:
        return None
    value = d.get('record_source')
    if isinstance(value, dict):
        box = str(value.get('box') or '').strip().strip('"').upper()
        slot = _norm_slot(value.get('slot'))
        if box and slot.isdigit():
            return {'box': box, 'slot': slot}
    return ''


def swap_requested(data):
    """Swap option C: the user chose Swap for a slot that holds a stored spool
    (`swap: true`, sent by the Location Manager grid's Swap and the slot
    picker's). The engine then files that spool back where it sat before the
    slot and puts it in the scan buffer (`perform_smart_move(swap_out=True)`)
    instead of leaving it in the box with no slot. Only a real true counts; read
    by manage_contents add and /api/smart_move."""
    value = (data or {}).get('swap') if isinstance(data, dict) else None
    return value is True or str(value).strip().lower() == 'true'


def expected_residents_from(data):
    """Group 51.6 — the spools the page showed on the target head when the user
    picked it (the Printer picker's "XL-3 holds #99", or [] for a head it showed
    empty), as ids; None when the request names none (an older page, an internal
    caller): no check. A malformed value reads as None. Read by the move doors
    (manage_contents add, /api/smart_move, the wizard's edit and create)."""
    d = data if isinstance(data, dict) else {}
    raw = d.get('expected_residents')
    if not isinstance(raw, (list, tuple)):
        return None
    out = []
    for x in raw:
        try:
            out.append(int(str(x).strip().strip('"')))
        except (TypeError, ValueError):
            return None
    return out


def expected_occupant_from(data):
    """Group 51.7 — the stored spool the page showed in the target slot when the
    user chose Swap or Overwrite (the Location Manager grid's prompt, the slot
    picker's), as an id; None when the request names none: no check. Read by the
    same doors as expected_residents_from."""
    raw = (data or {}).get('expected_occupant') if isinstance(data, dict) else None
    if raw in (None, ''):
        return None
    try:
        return int(str(raw).strip().strip('"'))
    except (TypeError, ValueError):
        return None


def _feed_token(value):
    """Group 40.3 — "what a box slot feeds" in one form: an upper-cased head id,
    or '' for none (unbound, a PRINTER:<id> Printer Pool slot, no slot). The form
    _slot_binding answers, so a request's expected_feed and the engine's read
    compare equal exactly when they name the same feed."""
    t = str(value if value is not None else '').strip().strip('"').strip().upper()
    if not t or t in ('NONE', 'NULL') or locations_db.is_printer_sentinel(t):
        return ''
    return t


def expected_feed_from(data):
    """Group 40.3 — the feed a box-slot question named for its slot, which every
    replay of it sends back (`expected_feed`: the answer's `feed`); a screen that
    showed the slot's feed when the user chose it (a Quick-Swap deposit tile)
    sends it on its first request too. None when the request carries none (a
    first request, a blind slot-label scan, a page from before 40.3, an internal
    caller): no check. A non-string reads as '' (it named no feed), so a
    malformed request is asked rather than trusted. Read by the three doors that
    can load a bound box slot's head."""
    d = data if isinstance(data, dict) else {}
    value = d.get('expected_feed')
    if value is None:
        return None
    return _feed_token(value) if isinstance(value, str) else ''


def _fed_key(head, residents):
    """A fed head's confirm key: the head and the spools the question named
    ("XL-1#99", "XL-1#7,99")."""
    ids = sorted({str(r).strip() for r in residents}, key=lambda s: (len(s), s))
    return f"{str(head or '').strip().upper()}#{','.join(ids)}"


def _fed_blanket(confirmed, head):
    """True when `confirmed` covers `head` whatever it runs: True (every head) or
    the bare head id (internal callers and tests; a page sends confirm keys)."""
    every, keys = _confirm_scope(confirmed)
    return every or str(head or '').strip().strip('"').upper() in keys


def _fed_covered(confirmed, head, residents):
    """Whether `confirmed` covers loading over `head` while it runs `residents`
    (its spools fed from elsewhere): blanket, or the confirm key naming exactly
    those spools. A different spool on the head is asked about again."""
    return _fed_blanket(confirmed, head) or _fed_key(head, residents) in _confirm_scope(confirmed)[1]


def stale_fed_refusal(data, result):
    """Group 40.0c — a page loaded before 40.0c can't answer a head_fed question:
    its replay rebuilt the confirm from `active_print` and sent back only the
    heads in `active_prints`, so every Yes got the same question back, forever.
    The question goes only to a request that carries `confirmed_fed_heads` (any
    list, even []), which every door call of a 40.3 page does. Otherwise this
    logs and returns the message the door answers with instead, naming what it
    refused; else None. Checked BEFORE stale_confirm_refusal: a pre-Group-39
    page asked a head_fed question about an idle head must hear "XL-1 is
    running #99 … reload", not "can't confirm a move during a print". A
    feed_changed answer (40.3) reaches neither rule: only a page that sends
    expected_feed gets one."""
    d = data if isinstance(data, dict) else {}
    if 'confirmed_fed_heads' in d:
        return None
    if not (isinstance(result, dict) and result.get('status') == 'requires_confirm'
            and result.get('confirm_type') == 'head_fed'):
        return None
    fed = (result.get('fed_heads') or [{}])[0]
    running = _and_list(f"#{r.get('id')}" for r in (fed.get('residents') or [fed.get('resident') or {}]))
    msg = (f"Not moved: {fed.get('toolhead') or 'that toolhead'} is running {running}, and this request "
           f"can't ask before loading over it. Reload the page (Ctrl+F5) and try again.")
    state.add_log_entry(f"⚠️ {msg} It would have asked: {result.get('msg')}", "WARNING", "ffaa00")
    return msg


def _norm_slot(slot):
    """A slot as one comparable string: quotes and blanks stripped, 'None' /
    'null' read as no slot, and a number without leading zeros ('01' -> '1').
    Slots arrive as JSON ints, quoted Spoolman extras and scan text."""
    s = str(slot if slot is not None else '').strip().strip('"').strip()
    if s in ('None', 'null'):
        return ''
    return str(int(s)) if s.isdigit() else s


def _slot_binding(box_row, slot):
    """What `slot` of `box_row` feeds, upper-cased, or '' when the slot is
    unbound or a PRINTER:<id> pool slot. The pre-flight, the fed-head check and
    the auto-deploy chain all read the binding here, so the head the user is
    asked about is the head the chain loads."""
    s = _norm_slot(slot)
    if not s:
        return ''
    for key, bound in locations_db.bindings_from_row(box_row).items():
        if _norm_slot(key) == s:
            # _feed_token's form (Group 40.3 review, A2): a hand-edited "None" /
            # "null" (the Feeds editor saves them as unassigned) reads as
            # unbound, so `feed` and a replay's `expected_feed` compare equal.
            return _feed_token(bound)
    return ''


def _spool_record(sid):
    """A spool's own record, or None when Spoolman can't give it: get_spool
    returns Spoolman's error body (a truthy dict without an id) for a missing
    spool, so the id decides (as print_deduct._spool_read does)."""
    rec = spoolman_api.get_spool(sid)
    return rec if isinstance(rec, dict) and rec.get('id') is not None else None


def recommend_box_slot(max_slots, claims, own_slot=None, would_prompt=None):
    """Group 40.0e / 40.1 — the ONE box-slot recommendation (Derek's D2.1),
    shared by the engine's auto-slot and the slot picker's ⭐ so the two can't
    drift:
      1. `own_slot`: the moving spool already sits in this box, in a slot no
         other spool claims;
      2. else the lowest-numbered empty slot for which `would_prompt(slot)` is
         false (the caller's rule: unbound, a pool slot, or a head with no
         spool on it; any empty slot when nothing would load);
      3. else the lowest-numbered empty slot;
      4. else None: the box is full. Never assume an empty slot exists.
    `claims` holds the slots other spools hold, directly or as the slot a
    deployed spool came from. `would_prompt` is asked lazily, lowest slot
    first, and may raise (the engine then refuses the move). Returns
    (slot or None, 'own_slot' | 'no_prompt' | 'lowest_empty' | 'full')."""
    try:
        n = int(str(max_slots if max_slots is not None else '').strip() or '0')
    except (TypeError, ValueError):
        n = 0
    taken = {_norm_slot(s) for s in (claims or ())}
    own = _norm_slot(own_slot)
    if own.isdigit() and 1 <= int(own) <= n and own not in taken:
        return own, 'own_slot'
    empty = [str(i) for i in range(1, n + 1) if str(i) not in taken]
    if not empty:
        return None, 'full'
    for s in empty:
        if would_prompt is None or not would_prompt(s):
            return s, 'no_prompt'
    return empty[0], 'lowest_empty'


_AUTO_SLOT_WHY = {
    'own_slot': "the slot it already sits in",
    'no_prompt': "the lowest free slot that loads no busy toolhead",
    'lowest_empty': "the lowest free slot",
    'picked': "the slot picked when the move was asked about",
}


def box_slot_claims(box_row, box_id, in_box, moving_ids):
    """Group 40.0e / 40.1 — who holds which slot of a multi-slot box, from one
    read of it (get_spools_at_location_detailed(_strict) items, or a bucket of
    them): the ONE reading the engine's auto-slot (step 3) and the slot
    picker's ⭐ share, so the two can't drift. Returns (claims, own_slot,
    ghost_slot):
      - `claims` {slot: [ids]}: the slots OTHER spools hold, directly or as the
        slot a deployed spool came from (the one slot rule, 42.2);
      - `own_slot`: the slot a moving spool sits in directly, else `ghost_slot`;
      - `ghost_slot`: the slot a moving spool was deployed from, which it still
        holds physically (putting it back there from its head is an unload)."""
    box = str(box_id or '').strip().strip('"').upper()
    moving = {str(s) for s in (moving_ids or ())}
    items = list(in_box or [])
    others = [item for item in items if str(item.get('id')) not in moving]
    claims: typing.Dict[str, typing.List[typing.Any]] = {}
    for item in others:
        s = _norm_slot(locations_db.effective_slot(box_row, item.get('slot', ''), occupants=len(others)))
        if s:
            claims.setdefault(s, []).append(item.get('id'))
    own_slot = next((_norm_slot(item.get('slot', '')) for item in items
                     if str(item.get('id')) in moving and not item.get('is_ghost')
                     and str(item.get('location') or '').strip().strip('"').upper() == box), None)
    ghost_slot = next((_norm_slot(item.get('slot', '')) for item in items
                       if str(item.get('id')) in moving and item.get('is_ghost')), None)
    return claims, (own_slot or ghost_slot), ghost_slot


def slot_would_prompt(box_row, slot, moving_from, printer_map, loc_info_map, residents_of):
    """Group 40.0e / 40.1 — whether loading `slot`'s head could ask: a one-spool
    head that holds a spool. A binding to anything else (a deleted head, a
    printer row) counts as asking too, since the chain would move the spool out
    of the box to it. A slot feeding the head the spool is leaving (`moving_from`)
    never asks: the move stores it there. Static, with no printer probe (the
    engine's step 5 asks about a printing head either way). `residents_of(head)`
    lists the spools whose own record is on that head, other than the moving
    one; the engine reads it strictly (and may raise), the picker's model from
    its one strict read. Shared by the engine's auto-slot and the picker's ⭐."""
    head = _slot_binding(box_row, slot)
    if not head or head == str(moving_from or '').strip().strip('"').upper():
        return False
    if not _holds_one_spool(head, printer_map, loc_info_map):
        return True
    return bool(residents_of(head))


def _same_feed(rec, box_id, slot, loc_info_map):
    """True when a head's resident `rec` is the slot's OWN spool: its trail names
    exactly this box and slot. That is the same-slot swap (Derek's everyday
    "replace the spool in LR-MDB-1 slot 3"), which asks nothing new. Compared
    through the one slot rule (42.2's effective_slot)."""
    extra = (rec or {}).get('extra') or {}
    src = str(extra.get('physical_source') or '').strip().strip('"').upper()
    if not src or src != str(box_id or '').strip().strip('"').upper():
        return False
    trail_slot = _norm_slot(locations_db.effective_slot(
        (loc_info_map or {}).get(src), extra.get('physical_source_slot')))
    return bool(trail_slot) and trail_slot == _norm_slot(slot)


def _fed_resident(rec, head, printer_map, loc_list, loc_info_map):
    """One spool running on a fed head, as the head_fed answer names it: where it
    came from and where loading over it sends it, both from exactly where Smart
    Load's eject sends it (its saved home, else the Room the printer sits in,
    else Unassigned), so the dialog can't drift from the real eject. A trail the
    eject won't use (a stale toolhead, a loop) reads as "doesn't know"."""
    extra = rec.get('extra') or {}
    src = str(extra.get('physical_source') or '').strip().strip('"').upper()
    src_slot = _norm_slot(locations_db.effective_slot((loc_info_map or {}).get(src),
                                                      extra.get('physical_source_slot'))) if src else ''
    dest = _eject_destination(rec, printer_map, homeless_destination=_known_room_of(head, loc_list))
    home = str(dest.get('home') or '').strip().strip('"').upper()
    if home:
        try:
            multi = int(str(((loc_info_map or {}).get(home) or {}).get('Max Spools', '0')).strip() or '0') > 1
        except (TypeError, ValueError):
            multi = False
        home_slot = _norm_slot(dest.get('slot'))
        came_from = f"{home} slot {home_slot}" if multi and home_slot else home
        goes_to, goes = home, f"back to {home}"
    else:
        came_from = ""
        goes_to = str(dest.get('target') or '').strip().upper()
        goes = f"to Room {goes_to}" if goes_to else "to Unassigned"
    try:
        display = spoolman_api.format_spool_display(rec).get('text') or f"#{rec.get('id')}"
    except Exception:
        display = f"#{rec.get('id')}"
    return {"id": rec.get('id'), "display": display,
            "trail": {"box": src, "slot": src_slot} if src else None,
            "from": came_from, "goes_to": goes_to, "goes": goes}


def _running_text(residents):
    """"#99 (from PM-DB-2)", "#99 (FCC doesn't know where it came from)", or a list."""
    return _and_list(f"#{r['id']} (from {r['from']})" if r.get('from')
                     else f"#{r['id']} (FCC doesn't know where it came from)" for r in residents)


def _fed_sentence(entry, loading, charged, with_feed=True):
    """"LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #1 (from PM-DB-3).
    Loading #57 sends #1 back to PM-DB-3." (Derek's wording, 2026-10-13).
    `charged`: the head's printer is printing, so the unloaded spool stops
    being charged for this print. `with_feed=False` drops the "LR-MDB-1 slot 1
    feeds XL-1, and" lead, for a question whose own lead already said what the
    slot feeds (40.3's feed_changed)."""
    head = entry['toolhead']
    residents = entry.get('residents') or [entry['resident']]
    sends = _and_list(f"#{r['id']} {r['goes']}" for r in residents)
    gone = _and_list(f"#{r['id']}" for r in residents)
    tail = f", so FCC stops charging this print to {gone}" if charged else ""
    lead = f"{entry['box']} slot {entry['slot']} feeds {head}, and {head}" if with_feed else head
    return f"{lead} is running {_running_text(residents)}. Loading #{loading} sends {sends}{tail}."


def _head_print_state(head, active_prints, printer_map):
    """A fed head's printer state for the sentence about it: from the answer's
    active prints under ANY role, else (the caller had already confirmed that
    head, so it isn't listed) from the per-move probe memo, one probe per
    printer at most. The unloaded spool stops being charged for the print either
    way, so the question must say so (Group 40 review,
    protocol:fed-text-drops-print-consequence). None when not printing."""
    h = str(head or '').strip().upper()
    for a in active_prints or ():
        if str(a.get('toolhead', '')).strip().upper() == h:
            return a
    if printer_map is None:
        return None
    return _active_print_info_for_location(h, printer_map)


def _head_fed_answer(fed_heads, active_prints, target, target_slot, spools, empty_heads=(),
                     can_store=True, printer_map=None):
    """Group 40.0c — the head_fed question, in the ONE shape every move confirm
    answers in (39.1): `fed_heads` beside `active_prints`, so a head that is
    fed from elsewhere AND printing is one question. "Load it instead" replays
    the move with each fed head's `confirm_key` in `confirmed_fed_heads` (and
    the printing heads in `confirmed_toolheads`); "Just store it" (`can_store`)
    replays it with auto_deploy false. Both replays name the slot
    (`picked_slot`: target_slot) and the spools (`spools`) the question was
    about. `title` asks; `body` (= `msg`) explains, with no "Continue?".
    `printer_map` (40.3): a fed head the caller already confirmed is not in
    `active_prints`, but its print still decides whether the unloaded spool
    stops being charged; it is looked up through the probe memo."""
    loading = spools[-1]   # the chain deploys the last spool placed in the slot
    told: typing.Set[str] = set()
    parts = []
    for f in fed_heads:
        ap = _head_print_state(f['toolhead'], active_prints, printer_map)
        lead = ""
        if ap and ap['printer_name'] not in told:
            lead = f"{ap['printer_name']} is {ap['state']}. "
            told.add(ap['printer_name'])
        parts.append(lead + _fed_sentence(f, loading, charged=bool(ap)))
    rest = _active_print_message(active_prints, target, (), target_slot,
                                 skip_feeds=[f['toolhead'] for f in fed_heads], named=told,
                                 empty_heads=empty_heads)
    rest = rest[:-len("Continue?")].strip() if rest.endswith("Continue?") else rest.strip()
    if rest:
        parts.append(rest)
    first = active_prints[0] if active_prints else None
    msg = " ".join(parts)
    return {
        "status": "requires_confirm",
        "confirm_type": "head_fed",
        "fed_heads": fed_heads,
        "active_prints": active_prints,
        "active_print": {k: first[k] for k in ("toolhead", "printer_name", "state")} if first else None,
        "can_store": can_store,
        "target_slot": _norm_slot(target_slot) or None,
        "spools": [int(s) for s in spools if str(s).isdigit()],
        "title": f"Load #{loading} onto {fed_heads[0]['toolhead']}?",
        "body": msg,
        "msg": msg,
        # The dialog's printing style follows the body (Group 40.3 review, C4):
        # a fed head the caller already confirmed is printing too.
        "printing": bool(told) or bool(active_prints),
    }


def _feed_phrases(box_row, slot, token, printer_map, loc_info_map):
    """How a box slot's feed reads in the feed_changed question: (now, was), e.g.
    ("now feeds XL-2", "it fed XL-2"). A '' token is told apart by the slot's
    raw binding: a Printer Pool slot, or no toolhead at all."""
    t = _feed_token(token)
    if t and _holds_one_spool(t, printer_map, loc_info_map):
        return f"now feeds {t}", f"it fed {t}"
    if t:
        return f"now points at {t}, which isn't a toolhead", f"it pointed at {t}"
    raw = ''
    for key, bound in locations_db.bindings_from_row(box_row).items():
        if _norm_slot(key) == _norm_slot(slot):
            raw = str(bound or '').strip()
            break
    if raw and locations_db.is_printer_sentinel(raw):
        return "is now a Printer Pool slot", "it fed no toolhead"
    return "now feeds no toolhead", "it fed no toolhead"


def _feed_changed_answer(feed_changed, fed_heads, active_prints, target, target_slot, spools, box_row,
                         bound_th, loads_head, can_store, leaving, repicked, empty_heads,
                         printer_map, loc_info_map):
    """Group 40.3 (Derek, 2026-10-14: multi-user awareness) — a replay named the
    feed its question was about (`expected_feed`), and the slot feeds something
    else now: re-pointed in the Feeds editor, a Printer Pool or unbound slot now
    bound to a head, or a full box that freed a slot. Nothing is written; this
    asks again, naming both: "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when
    you were asked). Load #57 onto XL-2?", even when XL-2 is an empty, idle
    head (Derek fills slot 1 because a slicer file depends on it). It carries the
    new head's fed residents (and their confirm keys) and active prints, so the
    next Yes covers everything in one round; a new feed that loads nothing
    (a pool, no toolhead, a binding to a non-head) offers only the store
    (`can_load` false)."""
    loading = spools[-1]
    where = f"{target} slot {_norm_slot(target_slot)}" if _norm_slot(target_slot) else target
    now, _ = _feed_phrases(box_row, target_slot, feed_changed['now'], printer_map, loc_info_map)
    _, was = _feed_phrases(box_row, target_slot, feed_changed['was'], printer_map, loc_info_map)
    if repicked:
        bound = now[len("now "):] if now.startswith("now ") else now
        lead = f"{where} is free now, and it {bound} (the box was full when you were asked)."
    else:
        lead = f"{where} {now} ({was} when you were asked)."
    parts = [lead]
    told: typing.Set[str] = set()
    if bound_th:
        ap = _head_print_state(bound_th, active_prints, printer_map)
        if ap:
            parts.append(f"{ap['printer_name']} is {ap['state']}.")
            told.add(ap['printer_name'])
        for f in fed_heads:
            parts.append(_fed_sentence(f, loading, charged=bool(ap), with_feed=False))
    if leaving:
        parts.append(f"#{loading} is leaving {feed_changed['now']}, so it is stored there, not loaded back.")
    rest = _active_print_message(active_prints, target, (), target_slot,
                                 skip_feeds=[bound_th] if bound_th else [], named=told,
                                 empty_heads=empty_heads)
    rest = rest[:-len("Continue?")].strip() if rest.endswith("Continue?") else rest.strip()
    if rest:
        parts.append(rest)
    title = f"Load #{loading} onto {bound_th}?" if loads_head else f"Store #{loading} in {where}?"
    body = " ".join(parts)
    first = active_prints[0] if active_prints else None
    return {
        "status": "requires_confirm",
        "confirm_type": "feed_changed",
        "feed_changed": {"was": feed_changed['was'], "now": feed_changed['now']},
        "fed_heads": fed_heads,
        "active_prints": active_prints,
        "active_print": {k: first[k] for k in ("toolhead", "printer_name", "state")} if first else None,
        "can_store": bool(can_store),
        "can_load": bool(loads_head),
        "target_slot": _norm_slot(target_slot) or None,
        "spools": [int(s) for s in spools if str(s).isdigit()],
        "title": title,
        "body": body,
        "msg": f"{body} {title}",
        "printing": bool(told) or bool(active_prints),
    }


def _ghost_head(item):
    """Where a spool deployed FROM a slot (a ghost in the slot read) is now."""
    return str((item or {}).get('deployed_to') or '').strip().strip('"').upper()


def _ghost_claim_refusal(target, slot, ghost, slot_feed, bound_th, loads_head, printer_map, loc_info_map):
    """Why a slot whose own spool is deployed refuses another spool (the step-6
    ghost guard), with the one thing the user can do about it. "Load the new
    spool instead" is offered only where a load swaps the spool out: the slot
    feeds the head it runs on (Group 40.3 review, A3)."""
    gid = (ghost or {}).get('id')
    dep = _ghost_head(ghost)
    if not _holds_one_spool(dep, printer_map, loc_info_map):
        # A stale trail (Group 40.3 fix check, E1/S1): the spool isn't loaded
        # anywhere; its record never let go of the slot.
        here = f"on {dep}" if dep else "in Unassigned"
        there = f"{dep}'s label" if dep else "the label of where it sits"
        return (f"{target} slot {slot} is still claimed by #{gid}, whose record says it came from there, "
                f"though it is {here}: scan #{gid}, then {there}, to clear that, so nothing moved")
    lead = f"{target} slot {slot} still holds #{gid}, loaded on {dep}"
    if loads_head:
        return f"{lead}, while the slot feeds {bound_th}: take #{gid} off {dep} first, so nothing moved"
    if bound_th:
        return (f"{lead}, and the slot is bound to {bound_th}, which isn't a toolhead: take #{gid} off {dep} "
                f"first, and fix the binding in {target}'s 🔗 Slot → Toolhead Feeds, so nothing moved")
    if slot_feed and slot_feed == dep and _holds_one_spool(slot_feed, printer_map, loc_info_map):
        return f"{lead}: take it off first, or load the new spool instead, so nothing moved"
    return f"{lead}: take it off first, so nothing moved"


def _toolhead_of(location_str, printer_map=None):
    """Resolve a location string to its (printer_name, toolhead_id) tuple.

    Returns None if the location is empty or not a registered toolhead.
    Used so callers can decide whether a filabridge unmap is needed
    before a move.
    """
    if not location_str:
        return None
    if printer_map is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    loc = str(location_str).strip().strip('"').upper()
    if loc in printer_map:
        p = printer_map[loc]
        return (p.get('printer_name'), p.get('position'))
    return None


def _find_box_slot_feeding_toolhead(toolhead_id, loc_list=None):
    """Reverse-lookup the dryer-box slot that feeds `toolhead_id` via
    `extra.slot_targets`. Returns (box_loc_id, slot_str) or (None, None).

    Used by `perform_smart_move`'s PRINTER MOVE branch (13.6 Part A) to
    synthesize a ghost binding when a spool is moved directly to a toolhead
    that has a reverse-binding back to a dryer-box slot. Without this, the
    box card never sees the spool and the user has to manually re-assign.

    Multiple boxes pointing the same toolhead is degenerate but tolerated:
    we return the first match in `locations.json` iteration order.
    """
    if not toolhead_id:
        return (None, None)
    if loc_list is None:
        loc_list = locations_db.load_locations_list()
    target_th = str(toolhead_id).strip().upper()
    for row in loc_list:
        if not isinstance(row, dict) or row.get('Type') != 'Dryer Box':
            continue
        # Group 42.1 step 5: a single-slot box is attached only by its OWN spool
        # (the Group 20.2 attach), never by this lookup. Its spool's blank slot
        # read as free, so a stranger scanned onto a head with a PolyDryer
        # attached (every RCOI head: no multi-slot box feeds the INDX) recorded
        # that PolyDryer as its home, and a later Return landed it on top.
        if locations_db._is_single_slot_dryer_box(row):
            continue
        # The guarded reader: one malformed box row must not break every
        # source-less move onto a toolhead (this runs unguarded in the PRINTER
        # MOVE branch).
        slot_targets = locations_db.bindings_from_row(row)
        for slot, bound_th in slot_targets.items():
            if not bound_th:
                continue
            if str(bound_th).strip().upper() == target_th:
                return (row.get('LocationID'), str(slot))
    return (None, None)


def _feed_slots_for(toolhead_id, loc_list):
    """Every (box, slot) of a multi-slot Dryer Box bound to `toolhead_id`, in
    locations.json order. Single-slot boxes never feed (42.1 step 5); the
    PRINTER:<id> pool sentinel names no head."""
    target_th = str(toolhead_id or '').strip().upper()
    out = []
    if not target_th:
        return out
    for row in (loc_list or []):
        if not isinstance(row, dict) or row.get('Type') != locations_db.DRYER_BOX_TYPE:
            continue
        if locations_db._is_single_slot_dryer_box(row):
            continue
        for slot, bound_th in locations_db.bindings_from_row(row).items():
            if bound_th and str(bound_th).strip().upper() == target_th:
                out.append((str(row.get('LocationID', '')).strip().upper(), str(slot)))
    return out


def _free_feed_slots(toolhead_id, loc_list, sid):
    """Group 40.0d — the feed slots of `toolhead_id` that no other spool claims,
    directly or through its trail (the one slot rule, 42.2's effective_slot), as
    ([(box, slot)], why_none). Each box is read STRICTLY: the fail-open read
    answered [] on a Spoolman blip, so every slot looked free and a spare took
    one another spool held. A box that can't be read yields no candidates at all
    (it might hold the second free slot), with `why_none` saying so."""
    rows = {str(r.get('LocationID', '')).strip().upper(): r
            for r in (loc_list or []) if isinstance(r, dict)}
    held: typing.Dict[str, typing.List[dict]] = {}
    free = []
    for box, slot in _feed_slots_for(toolhead_id, loc_list):
        if box not in held:
            try:
                held[box] = [o for o in (spoolman_api.get_spools_at_location_detailed_strict(box) or [])
                             if str(o.get('id')) != str(sid)]
            except Exception as e:
                return [], f"couldn't read {box} from Spoolman ({e})"
        items = held[box]
        # One slot form on both sides (Group 51.4): a slot stored as "02" or
        # '"2"' is slot 2, so it isn't free.
        if not any(_norm_slot(locations_db.effective_slot(rows.get(box), o.get('slot', ''), occupants=len(items)))
                   == _norm_slot(slot) for o in items):
            free.append((box, slot))
    return free, ""


def _spool_brand_color_suffix(sid):
    """Return a ' — Brand MAT (Color)' suffix for a spool, or '' if unavailable.

    Used by Activity Log entries (e.g. auto-deploy) so the line identifies the
    physical spool, not just its numeric ID. Never raises — a missing spool,
    network hiccup, or malformed payload collapses to an empty suffix.
    """
    try:
        snap = spoolman_api.get_spool(sid) or {}
        info = spoolman_api.format_spool_display(snap) or {}
        short = str(info.get("text_short", "")).strip()
        return f" — {short}" if short else ""
    except Exception:
        return ""


def _resolve_legacy_spool_lookup(legacy_id):
    """Item 3.6 — wrap `find_spools_by_legacy_id` so the scan path can
    surface the ambiguous case to the UI instead of silently picking the
    first candidate.

    Returns one of:
      * `None`                                          — no matching spool
      * `{'type': 'spool', 'id': N}`                    — exactly one match
      * `{'type': 'ambiguous', 'legacy_id': str,
          'candidates': [...]}`                         — 2+ matches; UI prompts

    Each candidate dict carries enough display data for a picker without
    forcing a second round-trip per spool: id, remaining_weight, location,
    archived, filament_id, plus a flat `display` string that mirrors
    `format_spool_display`'s text for selector readability.
    """
    spools = spoolman_api.find_spools_by_legacy_id(legacy_id)
    if not spools:
        return None
    if len(spools) == 1:
        return {'type': 'spool', 'id': spools[0]['id']}
    candidates = []
    for s in spools:
        info = {}
        try:
            info = spoolman_api.format_spool_display(s) or {}
        except Exception:
            info = {}
        fil = s.get('filament') or {}
        candidates.append({
            'id': s.get('id'),
            'remaining_weight': s.get('remaining_weight'),
            'location': s.get('location') or '',
            'archived': bool(s.get('archived')),
            'filament_id': fil.get('id'),
            'filament_name': fil.get('name') or '',
            'material': fil.get('material') or '',
            'vendor_name': (fil.get('vendor') or {}).get('name') or '',
            'color_hex': fil.get('color_hex') or '',
            'display': info.get('text') or info.get('text_short') or f"Spool #{s.get('id')}",
        })
    return {'type': 'ambiguous', 'legacy_id': str(legacy_id), 'candidates': candidates}


def resolve_scan(text):
    text = text.strip().strip('"').strip("'")
    decoded = urllib.parse.unquote(text)
    upper_text = text.upper()

    # 1. [ALEX FIX] PRIORITY: SLOT ASSIGNMENT (LOC:x:SLOT:y)
    # Must be checked FIRST. regex is non-greedy to capture the location ID correctly.
    slot_match = re.search(r'LOC:(.+?):SLOT:(\d+)', upper_text)
    if slot_match:
        return {
            'type': 'assignment', 
            'location': slot_match.group(1).strip(), 
            'slot': slot_match.group(2).strip()
        }

    # 2. COMMAND HANDLING
    if "CMD:" in upper_text:
        if "CMD:UNDO" in upper_text: return {'type': 'command', 'cmd': 'undo'}
        if "CMD:CLEAR" in upper_text: return {'type': 'command', 'cmd': 'clear'}
        if "CMD:EJECT" in upper_text: return {'type': 'command', 'cmd': 'eject'} 
        if "CMD:CONFIRM" in upper_text: return {'type': 'command', 'cmd': 'confirm'}
        if "CMD:EJECTALL" in upper_text: return {'type': 'command', 'cmd': 'ejectall'} 
        
        # NAV
        if "CMD:CYCLE" in upper_text: return {'type': 'command', 'cmd': 'next'}
        if "CMD:NEXT" in upper_text: return {'type': 'command', 'cmd': 'next'}
        if "CMD:PREV" in upper_text: return {'type': 'command', 'cmd': 'prev'}
        if "CMD:DONE" in upper_text: return {'type': 'command', 'cmd': 'done'}
        # 18.2 Part B — CMD:CANCEL is the safe-bail counterpart to CMD:DONE
        # for audit mode. DONE commits + auto-parks missing spools at UNKNOWN;
        # CANCEL closes the session without any moves. Required so the
        # AUDIT deck button toggle can map to CANCEL (no accidental
        # auto-parks) and the visual panel can surface both actions.
        if "CMD:CANCEL" in upper_text: return {'type': 'command', 'cmd': 'cancel'}
        
        # SLOT (Interactive)
        if "CMD:SLOT:" in upper_text:
            try:
                parts = upper_text.split(':')
                val = parts[-1].strip()
                if val.isdigit(): return {'type': 'command', 'cmd': 'slot', 'value': val}
            except: pass
        
        # AUDIT
        if "CMD:AUDIT" in upper_text: return {'type': 'command', 'cmd': 'audit'}

        # BULK MOVE (L298 Phase 2) — arms the scan-driven "move everything from
        # A to B" session. Shares CMD:DONE (commit) / CMD:CANCEL (bail) with
        # audit; those only mean something while a session is active. Safe
        # anywhere in this substring-matched ladder: "CMD:BULKMOVE" contains
        # none of the patterns above (notably not CMD:EJECT/CMD:DONE).
        if "CMD:BULKMOVE" in upper_text: return {'type': 'command', 'cmd': 'bulkmove'}

        return {'type': 'error', 'msg': 'Malformed Command'}

    # 3. [ALEX FIX] STANDARD LOCATION SCAN (LOC: Prefix)
    # This handles "LOC:BOX-01" or "LOC:PRINTER". 
    # It MUST run after the Slot check (so it doesn't steal slot codes) but BEFORE legacy checks.
    if upper_text.startswith("LOC:"):
        clean_loc = upper_text[4:].strip()
        if clean_loc:
             return {'type': 'location', 'id': clean_loc}
        return {'type': 'error', 'msg': 'Empty Location Code'}

    # 4. EXPLICIT LEGACY ID (Manual Override)
    if upper_text.startswith("LEGACY:") or upper_text.startswith("LEG:") or upper_text.startswith("OLD:"):
        clean_id = upper_text.split(":")[-1].strip()
        result = _resolve_legacy_spool_lookup(clean_id)
        if result is not None:
            return result
        # A legacy id can map to a FILAMENT that currently has no spools (e.g.
        # every spool used up + archived, or never created). Surface the
        # filament instead of dead-ending — mirrors the pure-number branch's
        # Priority-4 fallback (buglist 2026-06-02).
        fid = spoolman_api.find_filament_by_legacy_id(clean_id)
        if fid:
            return {'type': 'filament', 'id': fid}
        return {'type': 'error', 'msg': f'Legacy Spool ID {clean_id} not found'}

    # 5. DIRECT SPOOL ID
    if upper_text.startswith("ID:") or upper_text.startswith("SPL:"):
        prefix_len = 3 if upper_text.startswith("ID:") else 4
        clean_id = text[prefix_len:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Spool ID Format'}

    # 5. FILAMENT DEFINITION ID
    if upper_text.startswith("FIL:"):
        clean_id = text[4:].strip()
        if clean_id.isdigit(): return {'type': 'filament', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Filament ID Format'}

    # 5.5 — Prusament spool QR. The physical Prusament spool label encodes a
    # https://prusament.com/spool/<id>/<hash>/ URL. Recognize it BEFORE the
    # generic URL branch below (which would otherwise dead-end on "Unknown/
    # Invalid Link") so the scan pipeline can backfill temps onto the matching
    # existing filament or onboard a brand-new spool.
    #
    # The numeric <id> identifies the *product* (shared by every spool of that
    # product); the trailing <hash> identifies the *unique physical spool*.
    # Recognition stays keyed on the product <id> so a malformed or absent hash
    # never breaks the scan. The hash is captured best-effort as an optional,
    # contiguous alphanumeric run — real Prusament hashes are 10 lowercase hex
    # chars (see setup-and-rebuild/seeds), but we stay permissive and
    # case-insensitive so we neither truncate nor mis-recognize. The greedy
    # product-id group stops at the '/', so an all-digit hash isn't swallowed.
    # spool_hash is None when the URL carries no hash segment. Consumers needing
    # spool-level granularity (vs. product-level temp backfill) match on the
    # hash — see _handle_prusament_url_scan in app.py.
    pm = re.search(r'prusament\.com/spool/(\d+)(?:/([0-9a-z]+))?', text, re.IGNORECASE)
    if pm:
        return {
            'type': 'prusament_url',
            'url': text,
            'spool_id': pm.group(1),
            'spool_hash': pm.group(2),
        }

    # 6. LEGACY / URL PARSING
    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        legacy_candidate = m.group(1) if m else None
        if legacy_candidate:
            result = _resolve_legacy_spool_lookup(legacy_candidate)
            if result is not None:
                return result
        result = _resolve_legacy_spool_lookup(text)
        if result is not None:
            return result
        # Spool lookup came up empty. A legacy id can map to a FILAMENT that
        # currently has no spools (Derek 2026-06-02 — a Google-Sheets `range=`
        # link dead-ended with "unknown error" because the filament had zero
        # active spools). Fall back to surfacing the filament itself rather
        # than erroring out. Mirrors the pure-number branch's Priority 4.
        if legacy_candidate:
            fid = spoolman_api.find_filament_by_legacy_id(legacy_candidate)
            if fid:
                return {'type': 'filament', 'id': fid}
        return {'type': 'error', 'msg': 'Unknown/Invalid Link'}

    # 7. PURE NUMBER SCAN (Priority Stack)
    if text.isdigit():
        # Priority 1: Direct Spool ID
        spool_check = spoolman_api.get_spool(text)
        if spool_check and spool_check.get('id'):
            return {'type': 'spool', 'id': int(text)}

        # Priority 2: Direct Filament ID
        fil_check = spoolman_api.get_filament(text)
        if fil_check and fil_check.get('id'):
            return {'type': 'filament', 'id': int(text)}

        # Priority 3: Legacy Spool
        result = _resolve_legacy_spool_lookup(text)
        if result is not None:
            return result
        
        # Priority 4: Legacy Filament
        fid = spoolman_api.find_filament_by_legacy_id(text)
        if fid: return {'type': 'filament', 'id': fid}
        
        return {'type': 'error', 'msg': 'ID Not Found'}
        
    # 8. LEGACY LOCATION FALLBACK (Len > 2)
    # Only accepts a "random string" if it matches a known location in DB.
    if len(text) > 2:
        loc_list = locations_db.load_locations_list()
        valid_ids = {row['LocationID'].upper() for row in loc_list}
        valid_ids.add("UNASSIGNED") # [ALEX FIX] Allow the virtual Unassigned bucket
        valid_ids.add("UNKNOWN")    # 18.1 — virtual UNKNOWN bucket (physically lost)

        if text.upper() in valid_ids:
            return {'type': 'location', 'id': text.upper()}
        else:
            return {'type': 'error', 'msg': 'Unknown Code (Use LOC: prefix)'}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

def smart_move_failure(move_result, spool_id):
    """Why perform_smart_move did not move `spool_id`, or '' when it did.

    A rejected per-spool write leaves `status` at "success" and puts the reason
    in `failures` (L298 Phase 3). A caller that checks `status` alone therefore
    reports a move that never happened; the slot-QR assign, Quick-Swap and
    Return all did (2026-09-12). Callers handle "requires_confirm" before this.
    """
    if not isinstance(move_result, dict):
        return "the move returned no result"
    per_spool = (move_result.get('failures') or {}).get(str(spool_id))
    if per_spool:
        return str(per_spool)
    status = move_result.get('status')
    if status and status != 'success':
        return str(move_result.get('msg') or f"move {status}")
    return ""


def _is_single_occupancy(loc_id, printer_map, loc_info_map):
    """True for a location that holds one spool: a printer_map toolhead, or a
    row whose Type is a toolhead type or the dual-role "Printer"."""
    lid = str(loc_id or '').strip().strip('"').upper()
    if not lid:
        return False
    if lid in printer_map:
        return True
    row = loc_info_map.get(lid) or {}
    return row.get('Type') in (locations_db.TOOLHEAD_TYPES | {'Printer'})


def _holds_one_spool(loc_id, printer_map, loc_info_map):
    """The move engine's one-spool rule (step 2 and Smart Load): a printer_map
    head, a toolhead-type row, or a Printer row that owns no head but itself
    (the dual-role Core One, or a one-slot printer not yet set up; hotfix
    2026-09-29). A multi-head Printer row (XL, RCOI) is not a deploy slot and
    holds any number of spools: a LOC:XL scan files them on XL itself.
    _is_single_occupancy counts every Printer row, on purpose, for trails and
    eject destinations; Undo's occupancy check uses this rule (Group 42 review)."""
    lid = str(loc_id or '').strip().strip('"').upper()
    if not lid:
        return False
    if lid in (printer_map or {}):
        return True
    row = (loc_info_map or {}).get(lid)
    if not isinstance(row, dict):
        return False
    if row.get('Type') in locations_db.TOOLHEAD_TYPES:
        return True
    if str(row.get('Type', '')).strip() != 'Printer':
        return False
    own_heads = [str(t.get('location_id', '')).strip().upper()
                 for t in (row.get('toolheads') or []) if isinstance(t, dict)]
    try:
        one_slot = int(str(row.get('Max Spools', '0')).strip() or '0') <= 1
    except (TypeError, ValueError):
        one_slot = True
    return one_slot and not any(h and h != lid for h in own_heads)


def _ghost_trail_from(current_loc, current_extra, printer_map, loc_info_map):
    """(physical_source, physical_source_slot) for a spool arriving on a toolhead
    from `current_loc`.

    The trail names where the spool lives when it is not feeding (a box, shelf
    or room); Return, eject and the ghost matcher all send it back there. A
    toolhead is never that place. A head -> head move used to record the OLD
    head, and that stale trail later made Smart Load "eject" a spool from
    another head back onto the one being loaded, sent ejects onto occupied
    heads, and charged one spool for two heads' print usage (2026-09-12
    investigation). Such a move now starts with no trail; the 13.6
    reverse-binding in the PRINTER MOVE branch fills in the new head's bound
    box when it has one, which is where Return should take it.
    """
    if _is_single_occupancy(current_loc, printer_map, loc_info_map):
        return "", ""
    return current_loc, current_extra.get('container_slot')


# Step 4's rule for an archived spool going onto a head (Derek, 2026-10-20):
# with at least this much filament left on its record it is un-archived by the
# load; below it (an auto-archive at 0 g, or a rounding crumb) it is refused.
UNARCHIVE_ON_LOAD_MIN_G = 1.0


def _filament_left_g(rec):
    """The filament left on a spool record, in grams: Spoolman's
    `remaining_weight`, else its effective capacity (its own initial weight,
    else its filament's) minus what it used. None when unknown (the stock
    report's reading, stock_report.remaining_g)."""
    if not isinstance(rec, dict):
        return None
    try:
        rem = rec.get('remaining_weight')
        if rem is not None and str(rem).strip() != '':
            return float(rem)
    except (TypeError, ValueError):
        pass
    cap = spoolman_api.effective_initial_weight(rec)
    if cap is None:
        return None
    try:
        return cap - float(rec.get('used_weight') or 0)
    except (TypeError, ValueError):
        return None


# Group 42.6 — the "before the box" note (Derek's Q-A caveat: "we shouldn't
# overwrite the spool location before the box load. Say it was on a cart or
# something, so that if we unload it from the box, we know where it was before
# and move it back to that location"; option 1, decided 2026-10-13).
PRE_BOX_KEY = 'fcc_pre_box_location'


def _pre_box_note(loc, slot, printer_map, loc_info_map):
    """What a spool entering a single-slot box from `loc` records: `loc`, plus
    ":<slot>" when it sat in a slot of a multi-slot box (Claude's call 21:
    "LR-MDB-1 slot 4" goes back to slot 4). '' for places never recorded: a
    toolhead or printer, a room (a bare Room is a pain to find, D4), Unassigned
    or Unknown."""
    lid = str(loc or '').strip().strip('"').upper()
    if not lid or lid in ('UNASSIGNED', 'UNKNOWN') or lid in (printer_map or {}):
        return ''
    row = (loc_info_map or {}).get(lid)
    typ = str((row or {}).get('Type', '')).strip()
    if typ in (locations_db.TOOLHEAD_TYPES | {'Printer', 'Room', 'Virtual Room'}):
        return ''
    if row is None and '-' not in lid:
        return ''   # a "(Room)" FCC only knows from its spools
    s = str(slot or '').strip().strip('"')
    try:
        multi = int(str((row or {}).get('Max Spools', '0')).strip() or '0') > 1
    except (TypeError, ValueError):
        multi = False
    return f"{lid}:{s}" if s and multi else lid


def _pre_box_place(note):
    """(location, slot) of the place a "before the box" note names first, or
    ('', ''). A Swap option C note goes on with the plain place behind it
    ("LR-MDB-2:1>CR-CT-2-R1"), which this leaves out."""
    n = str(note or '').strip().strip('"').upper().split(PRE_SLOT_SEP, 1)[0].strip()
    if not n:
        return '', ''
    loc, _, slot = n.rpartition(':')
    if loc and slot.isdigit():
        return loc, slot
    return n, ''


# Group 40, Swap option C (Derek, 2026-10-15): the note also remembers where a
# spool sat before it went into a multi-slot box's slot, so a Swap that takes it
# back out can file it there ("it goes back to its previous location but also in
# the buffer in case that isn't correct"). "LR-MDB-2:1>CR-CT-2-R1" is the place it
# came from (here another slot), then the last plain place it sat in before any
# slot: a cart, shelf or drawer, the fallback when that slot is taken. A plain
# place alone ("CR-CT-2-R1") is both.
PRE_SLOT_SEP = '>'


def _is_dryer_box_row(row):
    return isinstance(row, dict) and str(row.get('Type', '')).strip() == locations_db.DRYER_BOX_TYPE


def _pre_box_plain(note, loc_info_map):
    """The last plain place a note remembers (a place with no slots: never a
    dryer box), or ''."""
    n = str(note or '').strip().strip('"').upper()
    if PRE_SLOT_SEP in n:
        return n.split(PRE_SLOT_SEP, 1)[1].strip()
    loc, slot = _pre_box_place(n)
    if not loc or slot or _is_dryer_box_row((loc_info_map or {}).get(loc)):
        return ''
    return loc


def _is_plain_place(loc, loc_info_map):
    """Group 40 review (engine-2): a place a spool can be filed back at with a
    bare write (no Smart Load, no slot): a location row that isn't a toolhead, a
    printer, a room or a dryer box (a cart, shelf, drawer). A note's plain place
    is trusted only while it still is one: a cart deleted since, a hand-edited
    "Pre-Box Location (system)" or a retyped row fall back instead."""
    lid = str(loc or '').strip().strip('"').upper()
    row = (loc_info_map or {}).get(lid) if lid else None
    if not isinstance(row, dict) or _is_dryer_box_row(row):
        return False
    return str(row.get('Type', '')).strip() not in (locations_db.TOOLHEAD_TYPES | {'Printer', 'Room', 'Virtual Room'})


def _join_note(place, plain):
    """A note naming `place` first, then the plain place behind it."""
    place = str(place or '').strip().upper()
    plain = str(plain or '').strip().upper()
    if not place:
        return plain
    return f"{place}{PRE_SLOT_SEP}{plain}" if plain and plain != place else place


def _note_after_move(current_loc, current_extra, target, target_slot, tgt_info, to_head,
                     printer_map, loc_info_map):
    """What the "before the box" note (PRE_BOX_KEY) becomes when a spool moves
    from `current_loc` to `target` (slot `target_slot`), or None to leave it.

    Into a single-slot box (Group 42.6, Claude's call 21): where it sat, from a
    place that isn't a head; coming back from a head, or a re-scan, keeps it.
    Into a multi-slot box (Swap option C): the place it sat before this slot,
    with the plain place behind it: from a cart, that cart; from another slot,
    that slot (a spool deployed from a box counts as sitting in its slot); back
    into the slot it was deployed from (a Return), or a spool with no box trail
    coming off a head, keeps what it remembers. Onto a head: from a plain place,
    that place (so a slot it goes into straight off the head still knows where it
    sat); a deploy from a box, head to head and a re-scan keep it. Anywhere else,
    or from a place FCC never records (a room, Unassigned), it is used up."""
    extra = current_extra or {}
    n0 = str(extra.get(PRE_BOX_KEY) or '').strip().strip('"')
    plain0 = _pre_box_plain(n0, loc_info_map)
    clear = '' if n0 else None
    cur = str(current_loc or '').strip().strip('"').upper()
    tgt = str(target or '').strip().strip('"').upper()
    cur_row = (loc_info_map or {}).get(cur)
    cur_slot = _norm_slot(extra.get('container_slot'))
    from_head = _is_single_occupancy(cur, printer_map, loc_info_map)

    def _slot_place(box, slot):
        """'B:s' for a multi-slot box's slot, 'B' for a single-slot box, '' for
        a multi-slot box with no slot (never a place to file a spool back)."""
        row = (loc_info_map or {}).get(box)
        if locations_db._is_single_slot_dryer_box(row):
            return box
        s = _norm_slot(slot)
        return f"{box}:{s}" if s else ''

    if locations_db._is_single_slot_dryer_box(tgt_info):
        if cur == tgt or from_head:
            return None
        prev = _pre_box_note(cur, extra.get('container_slot'), printer_map, loc_info_map)
        if prev and _is_dryer_box_row(cur_row):
            prev = _join_note(prev, plain0)
        return prev if (prev or n0) else None
    if to_head:
        if from_head or cur == tgt or _is_dryer_box_row(cur_row):
            return None
        return _pre_box_note(cur, '', printer_map, loc_info_map) or clear
    if _is_dryer_box_row(tgt_info):
        ts = _norm_slot(target_slot)
        if cur == tgt:
            if cur_slot and ts and cur_slot != ts:
                return _join_note(_slot_place(tgt, cur_slot), plain0)
            return None
        if from_head:
            src = str(extra.get('physical_source') or '').strip().strip('"').upper()
            src_row = (loc_info_map or {}).get(src)
            if not src or not _is_dryer_box_row(src_row):
                return None
            src_slot = _norm_slot(locations_db.effective_slot(src_row, extra.get('physical_source_slot')))
            if src == tgt and (not ts or src_slot == ts):
                return None
            prev = _slot_place(src, src_slot)
            return _join_note(prev, plain0) if prev else None
        if _is_dryer_box_row(cur_row):
            prev = _slot_place(cur, cur_slot)
            if prev:
                return _join_note(prev, plain0)
            return plain0 if (plain0 or n0) else None
        return _pre_box_note(cur, '', printer_map, loc_info_map) or clear
    return clear


def _swap_out_place(note, from_box, from_slot, loc_info_map, claims_of):
    """Group 40, Swap option C (Derek, 2026-10-15; all three points confirmed
    that evening): where a spool a Swap takes out of `from_box` slot `from_slot`
    is filed while it waits in the scan buffer. From its note (PRE_BOX_KEY):
      - the slot it sat in before (or the single-slot box), only while no other
        spool claims it ("shouldn't bump a spool in a slot if it's not empty"),
        and never the slot it is leaving;
      - else the plain place it sat in before any slot (a cart, shelf, drawer);
      - else ('', ''), Unassigned: a spool slotted before FCC kept the note
        ("seems right for now"), never the box without a slot (the 5/4).
    `claims_of(box)` gives the slots other spools hold there and may raise: an
    unreadable box is passed over, never bumped. Returns (location, slot)."""
    fb = str(from_box or '').strip().strip('"').upper()
    fs = _norm_slot(from_slot)
    rows = loc_info_map or {}

    def _free(box, slot):
        try:
            return _norm_slot(slot) not in {_norm_slot(s) for s in (claims_of(box) or ())}
        except Exception as e:
            state.logger.info(f"Swap: couldn't read {box} to file a spool back into slot {slot} ({e})")
            return False

    prev, prev_slot = _pre_box_place(note)
    row = rows.get(prev) if prev else None
    if isinstance(row, dict):
        if locations_db._is_single_slot_dryer_box(row):
            if prev != fb and _free(prev, '1'):
                return prev, '1'
        elif _is_dryer_box_row(row):
            try:
                max_slots = int(str(row.get('Max Spools', '0')).strip() or '0')
            except (TypeError, ValueError):
                max_slots = 0
            if (prev_slot.isdigit() and 1 <= int(prev_slot) <= max_slots
                    and not (prev == fb and _norm_slot(prev_slot) == fs) and _free(prev, prev_slot)):
                return prev, _norm_slot(prev_slot)
        elif not prev_slot and _is_plain_place(prev, rows):
            return prev, ''
    plain = _pre_box_plain(note, rows)
    if plain and plain != fb and _is_plain_place(plain, rows):
        return plain, ''
    return '', ''


def _swap_out_write(sid, rec, from_box, from_slot, loc_info_map):
    """File the spool a Swap took out of `from_box` slot `from_slot` where
    _swap_out_place says, with its slot set, its trail cleared and its note
    updated (back in the slot it came from, the note is what it was there: the
    plain place behind it; anywhere else it is used up). A re-reading write
    (_move_write). Returns (landed, location, slot)."""
    extra = dict((rec or {}).get('extra') or {})
    note = extra.get(PRE_BOX_KEY)

    def _claims(box):
        items = spoolman_api.get_spools_at_location_detailed_strict(box) or []
        claims, _own, _ghost = box_slot_claims((loc_info_map or {}).get(box), box, items, [sid])
        return set(claims)

    loc, slot = _swap_out_place(note, from_box, from_slot, loc_info_map, _claims)
    extra['container_slot'] = slot
    extra['physical_source'] = ""
    extra['physical_source_slot'] = ""
    new_note = _pre_box_plain(note, loc_info_map) if slot else ''
    if extra.get(PRE_BOX_KEY) or new_note:
        extra[PRE_BOX_KEY] = new_note
    return _move_write(sid, loc, extra), loc, slot


def _filed_text(loc, slot, loc_info_map=None):
    """'CR-CT-2-R1', 'LR-MDB-2 slot 1', 'PM-DB-2' (a single-slot box has one
    place), or '' for Unassigned."""
    lid = str(loc or '').strip().upper()
    if not lid:
        return ''
    s = _norm_slot(slot)
    if s and locations_db._is_single_slot_dryer_box((loc_info_map or {}).get(lid)):
        s = ''
    return f"{lid} slot {s}" if s else lid


def _known_room_of(loc_id, loc_list):
    """The Room `loc_id` really sits in according to the location tree, or ''.

    Where Smart Load sends a resident that has no saved home (Derek,
    2026-09-12: "if we have no history and the current location is accurate
    then ... the room it's located in. Otherwise unassigned is fine").
    resolve_room returns the TOP-LEVEL ancestor, which for a printer that is not
    nested in a room is the printer itself (XL-1 -> XL), and for an id with no
    row is a prefix guess, so only an actual Type "Room" row counts.
    """
    lid = str(loc_id or '').strip().upper()
    if not lid:
        return ""
    room = locations_db.resolve_room(lid, loc_list=loc_list) or ""
    if not room or room == lid or room in locations_db.PSEUDO_ROOM_PREFIXES:
        return ""
    row = next((r for r in (loc_list or [])
                if str(r.get('LocationID', '')).strip().upper() == room), None)
    return room if row and row.get('Type') == 'Room' else ""


# Group 41.1 / 41.9 — the views Eject All refuses, decided from locations.json
# and the printer map only (no Spoolman read), so the browser can ask before it
# shows "Nuke all unslotted in …?" (manage_contents clear_location check_only).
_EJECT_ALL_REFUSED = {
    'blank': "no location",
    'unassigned': "the Unassigned list",
    'unknown': "the Unknown list",
    'synthesized': "not a saved location",
    'room_view': "a room",
    'printer_view': "a printer",
}


def eject_all_block_reason(loc_id, loc_row, printer_map):
    """Why Eject All refuses `loc_id`, or None when it may run.

    - 'blank': no location (the 2026-09-13 guard: '' matches every Unassigned spool);
    - 'unassigned' / 'unknown': the two virtual lists. The matcher reads UNASSIGNED
      as every spool with no location, and Eject All there "returned" trail-carrying
      spools into their old boxes (41.9);
    - 'synthesized': no locations.json row (a "<prefix> (Room)" or a Spoolman-native
      name); a prefix sweep with nothing on disk to scope it;
    - 'room_view': Derek's D4 ("an eject all on a room would be catastrophic"): a
      Room, a "Virtual Room / Zone", or a dash-less row with no Type, which
      /api/locations shows as "<id> (Room)" (Group 41 review);
    - 'printer_view': a Printer row that is not itself a head (XL, RCOI, or one with
      no heads yet), so Eject All can't sweep every head mid-print.
    Every other view (a box, cart, shelf, row, or a head) keeps Eject All."""
    lid = str(loc_id or '').strip().upper()
    if not lid:
        return 'blank'
    if lid in ('UNASSIGNED', 'UNKNOWN'):
        return lid.lower()
    if not isinstance(loc_row, dict):
        return 'synthesized'
    rtype = str(loc_row.get('Type', '')).strip().lower()
    if rtype in ('room', 'virtual room') or (not rtype and '-' not in lid):
        return 'room_view'
    if locations_db.is_printer_row_not_head(lid, loc_row, printer_map):
        return 'printer_view'
    return None


def eject_all_block_message(reason, loc_id, loc_list, bulk_moves_enabled):
    """The toast for a refused Eject All (Derek, 2026-10-13: a room's pointer
    follows the Bulk Moves switch; a printer points at its cards and heads)."""
    lid = str(loc_id or '').strip().upper()
    if reason == 'blank':
        return "No location given. Open a location in the Location Manager, then use Eject All."
    if reason == 'unassigned':
        return ("Eject All doesn't apply to the Unassigned list: those spools have no "
                "location to leave. Nothing was moved.")
    if reason == 'unknown':
        return ("Eject All doesn't apply to the Unknown (lost) list. Eject spool by spool "
                "once you've found them. Nothing was moved.")
    if reason == 'synthesized':
        return (f"Eject All is off here: {lid} isn't a saved location (FCC only knows it "
                f"from its spools), so nothing was moved. Eject spool by spool from its cards.")
    if reason == 'room_view':
        if bulk_moves_enabled:
            return (f"Eject All is off for rooms, so nothing was moved. To empty {lid}, use "
                    f"🔀 Move all →. Its preview includes the spools in {lid}'s boxes, "
                    f"drawers and shelves too, so check it before you commit.")
        return (f"Eject All is off for rooms, so nothing was moved. Eject from {lid}'s "
                f"boxes, drawers and shelves, or spool by spool from its cards.")
    if reason == 'printer_view':
        heads = locations_db.printer_row_toolheads(loc_list, lid)
        if not heads:
            return (f"Eject All is off for printers, so nothing was moved. {lid} has no "
                    f"toolheads yet; add them in ⚙️ Settings → Toolheads.")
        span = heads[0] if len(heads) == 1 else f"{heads[0]} … {heads[-1]}"
        return (f"Eject All is off for printers, so nothing was moved. Eject each spool "
                f"from its card, or open a head ({span}); FCC asks first if {lid} is printing.")
    return "Eject All was refused. Nothing was moved."


def printer_row_refusal(loc_id, loc_row, loc_list):
    """Why a spool can't be filed on a Printer row that is not itself a toolhead
    (Group 40.0a; Claude's call 26, g40-q7): name its toolheads, and a Printer
    Pool only when it has one; a printer whose toolheads aren't set up yet points
    at Settings. "RCOI (🦝 Core One INDX) is a printer, not a toolhead — pick one
    of its toolheads (RCOI-1 to RCOI-8)." """
    lid = str(loc_id or '').strip().strip('"').upper()
    heads = locations_db.printer_row_toolheads(loc_list, lid)
    if not heads:
        return f"{lid} has no toolheads set up yet — add them in ⚙️ Settings → Toolheads."
    name = str((loc_row or {}).get('Name') or '').strip()
    # "🦝 XL" names the row XL itself; only a different name is worth repeating.
    plain = re.sub(r'^[^0-9A-Za-z]+', '', name).strip().upper()
    label = f"{lid} ({name})" if name and plain != lid else lid
    span = heads[0] if len(heads) == 1 else f"{heads[0]} to {heads[-1]}"
    # A Printer Pool slot is bound to the PRINTER:<prefix> sentinel (XL-1 → XL).
    sentinels = {f"PRINTER:{p}" for p in {lid} | {h.split('-', 1)[0] for h in heads}}
    has_pool = any(str(t or '').strip().upper() in sentinels
                   for r in (loc_list or []) if isinstance(r, dict)
                   and r.get('Type') == locations_db.DRYER_BOX_TYPE
                   for t in locations_db.bindings_from_row(r).values())
    return (f"{label} is a printer, not a toolhead — pick one of its toolheads ({span})"
            + (" or a Printer Pool slot." if has_pool else "."))


def _eject_refusal_reason(result):
    """Why perform_smart_eject did not return True, in words for a log line.

    A False carries no reason of its own. The eject logs its Spoolman error
    right next to the failing write, so point there rather than read the
    module-global LAST_SPOOLMAN_ERROR, which may belong to an earlier call.
    """
    if isinstance(result, dict):
        return result.get('msg') or "it needs a confirm"
    if result == "REQUIRE_CONFIRM":
        return "it needs an unassign confirm"
    return "its eject failed (see the Activity Log)"


# The auto-deploy chain collects the undo record(s) its chained move pushes, so
# it can fold exactly those into the parent record (see the chain).
_chain_undo_sink = threading.local()


_UNDO_IDS = itertools.count(1)
# The stack lives in memory and the count restarts with the process, so a bare
# number left in a dialog across a restart named a DIFFERENT move: the first one
# after the restart (Group 41 review). The process's own token makes it unique.
_UNDO_EPOCH = uuid.uuid4().hex[:8]


def _push_undo(record):
    """Push a move's undo record, and hand it to an enclosing auto-deploy chain.

    Group 41.4: every record gets a number. Undo asks first, naming the move it
    will reverse, and UNDO_STACK is shared by every tab, so the Yes carries the
    number and is refused if another move landed on top meanwhile."""
    record['id'] = f"{_UNDO_EPOCH}-{next(_UNDO_IDS)}"
    state.UNDO_STACK.append(record)
    sink = getattr(_chain_undo_sink, 'records', None)
    if sink is not None:
        sink.append(record)


def _move_write(sid, target, new_extra, unarchive=False):
    """The move engine's spool write: True when it landed.

    update_spool's timeout is a READ timeout, so a PATCH Spoolman committed but
    answered slowly comes back as a failure (Group 43.6's lesson). The move then
    reported the spool as failed, left it out of the undo record and tallied it
    as failed in a bulk move, although it had moved (Group 41 review). So a
    failed write is re-read, and counts as landed when the spool now sits at
    `target` with exactly the slot and trail this write set. `unarchive`: the
    same PATCH takes the spool out of the archive (step 4's rule for a spool
    loaded onto a head with filament left on its record)."""
    payload = {"location": target, "extra": new_extra}
    if unarchive:
        payload["archived"] = False
    if spoolman_api.update_spool(sid, payload):
        return True
    err = spoolman_api.LAST_SPOOLMAN_ERROR
    rec = spoolman_api.get_spool(sid)
    if not isinstance(rec, dict) or rec.get('id') is None:
        return False
    if str(rec.get('location') or '').strip().upper() != str(target).strip().upper():
        return False
    if unarchive and str(rec.get('archived')).strip().lower() == 'true':
        return False
    have = rec.get('extra') or {}
    for k in spoolman_api.SYSTEM_MANAGED_EXTRAS:
        if (str(have.get(k) or '').strip().strip('"')
                != str(new_extra.get(k) or '').strip().strip('"')):
            return False
    state.add_log_entry(
        f"⚠️ Spoolman answered an error moving Spool #{sid} -> {target or 'Unassigned'} ({err or 'no detail'}), "
        f"but a re-read shows it there: counted as moved.", "WARNING", "ffaa00")
    return True


def strict_direct_occupants(loc_id, exclude=()):
    """The ONE strict "direct residents" reader (Groups 39.7, 42.3b, 42.3c; Group
    40.0c reuses it): ids of the spools whose OWN record puts them at `loc_id`,
    read strictly, so a Spoolman blip RAISES instead of reading as "empty".
    Ghosts (a trail naming the location) and first-segment prefix hits (a
    Printer row's heads) are not residents; ids in `exclude` are left out."""
    lid = str(loc_id or '').strip().strip('"').upper()
    skip = {str(x) for x in (exclude or ())}
    return [row.get('id') for row in (spoolman_api.get_spools_at_location_detailed_strict(lid) or [])
            if str(row.get('id')) not in skip and not row.get('is_ghost')
            and str(row.get('location') or '').strip().strip('"').upper() == lid]


def _release_single_slot_box(sid, from_loc, pre_extra, printer_map, log=True):
    """Group 42.1 — Derek's rule (2026-09-13): a single-slot box stays bound to a
    head until ITS OWN spool leaves that head, by any path (eject, Return,
    Quick-Swap, any move). Call it after `sid`'s write has landed somewhere
    other than `from_loc`. `pre_extra` is the spool's extra BEFORE the move: its
    trail (`physical_source`) names its own box, so ejecting a different spool
    from a doubled head no longer unbinds the box feeding the one that stays.

    Returns the released box id, or None. Best-effort, like the attach: it
    never fails the move it follows. `log=False` lets a caller name the release
    in its own Activity Log sentence (the eject does, 42.5a)."""
    head = str(from_loc or '').strip().strip('"').upper()
    if not head or head not in (printer_map or {}):
        return None
    box = str((pre_extra or {}).get('physical_source') or '').strip().strip('"').upper()
    if not box or box == head:
        return None
    try:
        if not locations_db.detach_single_slot_box(box, head):
            return None
    except Exception as _re:
        state.logger.warning(f"42.1 single-slot box release skipped: {_re}")
        return None
    if log:
        state.add_log_entry(f"🔓 {box} detached from {head} — its spool #{sid} left the head", "INFO")
    return box


def release_box_after_direct_write(sid, pre, post):
    """Group 42 review: the wizard and /api/spool/update write a spool's location
    straight through update_spool, not through the move engine, so a spool edited
    off its head released nothing and its single-slot box stayed attached there.
    Call after such a write landed; `pre` / `post` are the spool before and after
    (the archive edge releases inside update_spool, and a second release finds
    nothing to do). Returns the released box id, or None; never raises."""
    try:
        before = str((pre or {}).get('location') or '').strip().strip('"').upper()
        after = str((post or {}).get('location') or '').strip().strip('"').upper()
        if not before or before == after:
            return None
        return _release_single_slot_box(sid, before, (pre or {}).get('extra') or {},
                                        locations_db.get_active_printer_map())
    except Exception as e:
        state.logger.warning(f"single-slot box release after a direct edit of #{sid} skipped: {e}")
        return None


def _put_in_buffer(spool_ids, off_head='', filed=None):
    """Group 40, the same-slot swap: put spools a move took off `off_head` (they
    are in the user's hand) at the END of the scan buffer, behind the spools
    already waiting there, so the next slot scan still loads the next new spool.
    Returns (entries, added): the buffer entries (the fields the buffer renders,
    read after the move, plus `off_head` for the page's toast) for the move's
    answer, which the page adds to its own buffer too, since its next save
    replaces this replica whole; and the ids it really appended (a spool already
    buffered isn't added twice, and Undo takes out only what the move added).
    A scanner's double-read of the slot label is the page's to drop (processScan's
    repeat guard); scanning the label again on purpose swaps the two straight
    back, as Derek expects (2026-10-15: no hard stop on fixing a wrong scan).
    `filed` {sid: where FCC filed it} (Swap option C: back where it sat before
    the slot, '' for Unassigned) rides on each entry as `filed_to` for the toast."""
    live = get_live_spools_data(list(spool_ids))
    items: typing.List[typing.Dict[str, typing.Any]] = []
    for sid in spool_ids:
        data = live.get(str(sid)) or {"display": f"#{sid}", "color": "888888"}
        items.append({"id": int(sid), **data, "off_head": str(off_head or '').strip().upper(),
                      "filed_to": str((filed or {}).get(str(sid)) or '')})
    buf = list(getattr(state, 'GLOBAL_BUFFER', None) or [])
    held = {str(b.get('id')) for b in buf if isinstance(b, dict)}
    added = [i['id'] for i in items if str(i['id']) not in held]
    state.GLOBAL_BUFFER = buf + [dict(i) for i in items if str(i['id']) not in held]
    return items, added


# Thread-local re-entry depth for perform_smart_move. The auto-deploy chain
# re-enters the wrapper synchronously on the same thread; depth 0 is the
# outermost move, which owns the per-move printer-state probe cache (L3 fix A).
_smart_move_depth = threading.local()


def perform_smart_move(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False,
                       confirmed_fed_heads=(), fed_check_from=None, picked_slot=None, expected_feed=None,
                       seen_printing=(), swap_slot=None, swap_out=False, record_source=None, unslotted=False,
                       expected_residents=None, expected_occupant=None, keep_archived=False):
    """Entry point for the slot-move pipeline.

    Owns the per-move printer-state probe cache (L3 fix A) so the auto-deploy
    recursion probes a given printer ONCE, not twice: a thread-local depth guard
    detects the OUTERMOST call and begins/clears the cache around it, while the
    recursive re-entry (depth > 0) leaves the outer cache untouched. All real
    work lives in _perform_smart_move_impl — this is a behaviour-neutral wrapper.

    `confirmed_fed_heads` (Group 40.0c): the fed heads whose "already running
    another spool" warning the user saw, as confirm keys ("XL-1#99": the head and
    the spools it ran) or bare head ids (any spool; internal callers); True
    covers every head, and the default covers none, so any caller that loads a
    bound slot's head is asked first. `fed_check_from` is internal: the
    auto-deploy chain passes (box, slot, the head's spools the question saw), so
    the chained load refuses to unload a spool that arrived during the probe.
    `picked_slot` (Group 40.0e): the slot an earlier answer picked for this
    slotless move (`target_slot`), taken only while it is still free; unlike
    `target_slot` it never unseats a spool that took it meanwhile.
    `expected_feed` (Group 40.3): what the target slot fed when the user decided
    (an earlier answer's `feed`: a head id, or '' for no toolhead); when the slot
    feeds something else now, the move asks again (`feed_changed`) and writes
    nothing. None: no check. Multi-slot Dryer Box targets only; the auto-deploy
    chain never passes it (the outer move already checked before any write).
    `seen_printing` (Group 40.3 review): toolheads the page saw printing; for
    this whole move (the chain too), their printers count as printing whenever
    the move's own probe can't reach them. Only the outermost call sets it.
    `swap_slot` is internal: the auto-deploy chain passes the (box, slot) it is
    loading the head from, so Smart Load sends that slot's OWN spool, coming off
    the head, to the scan buffer instead of back into the box (the same-slot
    swap; Derek, 2026-10-15). The answer names it in `to_buffer`.
    `swap_out` (Swap option C; Derek, 2026-10-15): the user chose Swap for an
    explicit slot that holds a stored spool (the Location Manager grid's Swap,
    the slot picker's). That spool is filed back where it sat before the slot
    (_swap_out_place) and put in the scan buffer (`to_buffer`), instead of the
    Overwrite's "stays in the box with no slot". Undo puts it back in the slot.
    `record_source` (Group 40.5, D3 / item G; toolhead targets): the Printer
    picker's "Record it as coming from…" answer for a spool that arrives from no
    box. None: the silent 13.6 rule (a feed slot only when exactly one is free);
    '' : record no box; {'box', 'slot'}: exactly that slot, which must be a
    multi-slot box's slot feeding the target head that no other spool holds
    (checked strictly before anything is written; refused otherwise,
    `blocked_reason: record_source`). A spool arriving from a box keeps its own
    trail and the answer says `record_source_ignored`.
    `unslotted` (Group 40.6): the spool goes into the box with no slot on
    purpose (Return's "No slot"), so step 3 picks none for it.
    `expected_residents` (Group 51.6; head targets): the spools the page showed on
    the head when the user picked it (the Printer picker's "XL-3 holds #99"). A
    spool on the head that wasn't among them, at step 4's strict read or step 6's
    re-list, refuses the move with nothing written (`blocked_reason:
    residents_changed`), instead of unloading a spool nobody was shown. None: no
    check. `expected_occupant` (Group 51.7; an explicit box slot): the stored
    spool the page showed in the slot when the user chose Swap or Overwrite; a
    different spool filed there now refuses that spool's move at step 6's strict
    slot read (`blocked_reason: occupant_changed` when every spool was refused).
    A head that emptied, or a slot whose spool left, meanwhile is filled as
    asked. The auto-deploy chain never passes either.
    """
    depth = getattr(_smart_move_depth, "n", 0)
    owns_move = depth == 0
    # Built before the depth goes up (Group 40.3 fix check, E4): a value that
    # can't be iterated raises here, not after the counter that only the
    # finally below restores.
    seen = frozenset(str(h).strip().strip('"').upper() for h in (seen_printing or ())
                     if str(h or '').strip()) if owns_move else None
    _smart_move_depth.n = depth + 1
    _pa = None
    if owns_move:
        _move_seen_printing.heads = seen
        # Deferred import keeps logic.py importable in unit tests that don't
        # satisfy prusalink_api's import graph (mirrors _active_print_info_*).
        try:
            import prusalink_api as _pa
            _pa.begin_probe_cache()
        except Exception:
            _pa = None
    try:
        return _perform_smart_move_impl(
            target, raw_spools, target_slot=target_slot, origin=origin,
            auto_deploy=auto_deploy,
            confirm_active_print=confirm_active_print,
            confirmed_fed_heads=confirmed_fed_heads,
            fed_check_from=fed_check_from,
            picked_slot=picked_slot,
            expected_feed=expected_feed,
            swap_slot=swap_slot,
            swap_out=swap_out,
            record_source=record_source,
            unslotted=unslotted,
            expected_residents=expected_residents,
            expected_occupant=expected_occupant,
            keep_archived=keep_archived,
        )
    finally:
        _smart_move_depth.n = getattr(_smart_move_depth, "n", 1) - 1
        if owns_move:
            _move_seen_printing.heads = None
        if owns_move and _pa is not None:
            try:
                _pa.clear_probe_cache()
            except Exception:
                pass


def _perform_smart_move_impl(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False,
                             confirmed_fed_heads=(), fed_check_from=None, picked_slot=None, expected_feed=None,
                             swap_slot=None, swap_out=False, record_source=None, unslotted=False,
                             expected_residents=None, expected_occupant=None, keep_archived=False):
    """Move spool(s) to `target`, optionally into `target_slot` of that location.

    `auto_deploy` (default True): when the target is a Dryer Box AND the
    target_slot is bound to a toolhead in that box's extra.slot_targets,
    chain a second move that ghost-deploys the spool onto that toolhead.
    This centralizes the behavior so every caller (scan, /api/manage_contents
    action=add, Feeds-editor post-save triggers, future callers) gets it
    consistently — not just the slot-QR scan path.

    Internal recursive calls set auto_deploy=False to prevent infinite
    chains (the toolhead deploy itself would otherwise try to auto-deploy
    onto its own printer binding).

    `origin_toolhead` (optional): location string naming the spool's
    previous toolhead, used only for the filabridge unmap. The
    auto-deploy recursive call passes this because by phase 2 the
    spool's Spoolman location is the dryer box, not the toolhead it
    came from — without this hint, phase 2 can't unmap the origin and
    filabridge rejects the destination map on its one-spool-one-toolhead
    invariant (the 2026-04-22 desync).
    """
    target = target.strip().upper()
    # One slot form for the whole move (Group 40.0c): a JSON int, a quoted
    # Spoolman extra and a zero-padded label name the same slot, so the head the
    # pre-flight asks about, the slot written and the head the chain loads can't
    # disagree. Slots count from 1.
    target_slot = _norm_slot(target_slot) or None
    if target_slot == '0':
        target_slot = None
    picked_slot = _norm_slot(picked_slot) or None
    expected_feed = None if expected_feed is None else _feed_token(expected_feed)
    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    loc_list = locations_db.load_locations_list()
    loc_info_map = {row['LocationID'].upper(): row for row in loc_list}

    # Group 41.9: a non-numeric item names a LOCATION and expands to its spools.
    # A blank one matched every spool with no location (plus every spool with no
    # trail, as a ghost), and the two virtual lists sweep the same way, so any
    # door that passed one moved essentially every live spool. Refuse before
    # any read or write.
    for item in (raw_spools or []):
        name = str(item).strip().strip('"').upper()
        if not str(item).isdigit() and name in ('', 'UNASSIGNED', 'UNKNOWN'):
            state.add_log_entry(
                f"⚠️ Move to {target or 'UNASSIGNED'} refused: {name or 'a blank'} isn't a "
                f"spool or a place to move spools from. Nothing was moved.", "WARNING", "ffaa00")
            return {"status": "error",
                    "msg": f"{name or 'A blank item'} isn't a spool or a location to move from. Nothing was moved."}

    spools = []
    for item in raw_spools:
        if str(item).isdigit(): spools.append(item)
        else:
            found = spoolman_api.get_spools_at_location(str(item))
            if found: spools.extend(found)

    if not spools: return {"status": "error", "msg": "No spools found"}

    # ---- THE SHARED PRE-WRITE CONTRACT (Group 39.1) ----------------------------
    # Groups 39-42 all edit this section. The order is fixed; extend a step,
    # never reorder or redefine it:
    #   1. Resolve the spool list (above).
    #   2. Structural refusals, no Spoolman or printer I/O, answered as
    #      {"status": "error", "blocked_reason", "msg", "failures"}: a Printer row
    #      that is not its own toolhead (40.0a); several spools onto a
    #      single-occupancy target (42.3a).
    #   3. Slot choice (40.0e): a slotless single spool into a multi-slot box
    #      gets recommend_box_slot's pick here, BEFORE anything is asked, so the
    #      pick is a named slot from then on (its head is probed and checked);
    #      a single-slot box's spool takes slot 1 (42.2).
    #   4. Strict reads, failing closed (status error, nothing written): the
    #      moving spools' own records (39.4; at a head, an archived one is
    #      refused, `blocked_reason: archived`, Group 51 review), the target
    #      head's residents (39.7; with `expected_residents`, a spool that arrived
    #      unseen refuses the move, 51.6),
    #      the bound head's residents and their records (40.0c; step 3's pick
    #      read them already, once per head). A replay's `expected_feed` (40.3)
    #      is compared here with no I/O against what the slot feeds now; when it
    #      differs, a load reads the slot's new head as for any load, so step 5
    #      can describe it, and a store reads no head (it is asked as a store).
    #   5. ONE confirm answer: _uncovered_active_heads over the destination /
    #      feeds / source heads (one probe per printer, through the memo), plus
    #      40.0c's fed heads: `feed_changed` (_feed_changed_answer, 40.3) first
    #      when a replay's expected feed no longer holds; else `head_fed`
    #      (_head_fed_answer) when a bound head runs a spool from elsewhere; else
    #      _requires_confirm_answer's `active_print`. Every answer carries what
    #      its replay sends back: `target`, `slot_picked`, `feed`, `can_load`.
    #   6. Writes, per spool, in this order: Smart Load's resident ejects (from
    #      a fresh strict list of the head when step 5 could have probed, which
    #      a chained deploy re-checks for a newly fed head, 40.0c); the slot
    #      unseat (41.6); the spool's own write (13.6 / record_source at a head,
    #      40.0d; the single-slot box release, 42.1); then the chain.
    # -----------------------------------------------------------------------------

    # Single-occupancy target (Printer/Toolhead): Smart Load (step 6) unloads
    # its resident before the incoming spool is written.
    tgt_info = loc_info_map.get(target)
    is_printer = target in printer_map
    # 21.3 — single-occupancy = the canonical toolhead type set (Tool Head /
    # MMU Slot / No MMU Direct Load) plus the dual-role "Printer" row. The old
    # inline list omitted "No MMU Direct Load" (the Core One direct-load type),
    # so manually assigning a spool to such a head — when it wasn't ALSO present
    # in printer_map to be caught by is_printer — skipped the resident auto-eject
    # and left two spools on one head. Sourced from locations_db.TOOLHEAD_TYPES
    # so this can't drift out of sync with the rest of the codebase again.
    # Hotfix 2026-09-29: a Printer row stays single-occupancy only while it owns
    # no toolhead other than itself — the dual-role Core One, or a one-slot
    # printer not yet set up in Settings. A multi-head printer (the INDX: RCOI
    # owns RCOI-1..8) is not a deploy slot, and the resident lookup prefix-
    # matches its heads — loading onto the printer row used to eject every
    # spool on all of them. The rule lives in _holds_one_spool (Undo uses it).
    is_toolhead = _holds_one_spool(target, {}, loc_info_map)

    # sid(str) -> why that spool did not move. Declared before the strict reads
    # and Smart Load, which can refuse the whole move; see the L298 Phase 3 note
    # at the write loop.
    failures: typing.Dict[str, str] = {}
    # Groups 51.3 / 51.7: sid(str) -> why step 6 refused it over what the slot
    # holds: `slot_claimed` (its own spool, deployed, still claims it; the
    # question path refuses the same way) or `occupant_changed` (another spool
    # than the one shown for Swap / Overwrite). When one reason refused every
    # spool, the answer carries it as `blocked_reason`.
    step6_refused: typing.Dict[str, str] = {}
    # sid(str) -> "BOX:slot" the 13.6 reverse-binding recorded as its home (40.0d).
    recorded_sources: typing.Dict[str, str] = {}

    # Step 2 (Group 40.0a, Derek's D3): nothing is filed on a Printer row that is
    # not itself one of its printer's toolheads (XL, RCOI, or one whose heads
    # aren't set up yet, Claude's call 26). Since the 2026-09-29 hotfix such a
    # row is a generic target, so LOC:XL with a buffer filed every buffered
    # spool on XL itself. A row that is its own head (the old CORE1) is in the
    # printer map and stays loadable. Refused before any read or write; the
    # Printer picker (40.5) opens on the browser's doors instead.
    if locations_db.is_printer_row_not_head(target, tgt_info, printer_map):
        msg = printer_row_refusal(target, tgt_info, loc_list)
        for sid in spools:
            failures[str(sid)] = msg
        state.add_log_entry(f"⚠️ Not moved: {msg}", "WARNING", "ffaa00")
        return {"status": "error", "blocked_reason": "printer_row", "msg": msg, "failures": failures}

    # Step 2 (Group 42.3a): a head holds one spool. Every spool sent to a
    # single-occupancy target used to be written onto it (the dashboard's
    # one-spool trim, L124, guards only its own scan path), so /api/smart_move
    # with two spools, or a location that expands to two, stacked them on one
    # head. Refused before any read or write, like Bulk Move's block. The same
    # spool listed twice is still one spool.
    _unique: typing.List[typing.Any] = []
    for _s in spools:
        if str(_s) not in {str(u) for u in _unique}:
            _unique.append(_s)
    spools = _unique
    if (is_printer or is_toolhead) and len(spools) > 1:
        msg = f"{target} holds one spool — move them one at a time (got {len(spools)})"
        for sid in spools:
            failures[str(sid)] = msg
        state.add_log_entry(f"⚠️ Not moved: {msg}.", "WARNING", "ffaa00")
        return {"status": "error", "blocked_reason": "single_occupancy", "msg": msg,
                "failures": failures}

    # Step 3 (Group 40.0e): the slot choice, BEFORE anything is asked. Auto-slot
    # used to run after the pre-flight, so a slotless move into a multi-slot box
    # never asked about the head its picked slot feeds: the chain then skipped a
    # printing head's deploy with a warning, or unloaded an idle head's spool
    # unasked. The pick is a named slot from here on (step 5 probes its head,
    # step 4 checks whether that head runs a spool from elsewhere), and every
    # answer carries it as `target_slot`; the replay sends it back as
    # `picked_slot`, taken only while it is still free. One spool only: in a
    # bulk move a shared slot would make each spool unseat the one before, so a
    # bulk slotless move stays slotless. Each bound head is read strictly once
    # per move: the pick and step 4's fed check share the read.
    head_residents: typing.Dict[str, typing.List[typing.Any]] = {}

    def _residents_of(head):
        """The spools whose own record is on `head`, other than the moving ones,
        read strictly once per move. Raises when Spoolman can't say."""
        h = str(head or '').strip().strip('"').upper()
        if h not in head_residents:
            head_residents[h] = strict_direct_occupants(h, exclude=spools)
        return head_residents[h]

    # The engine chose this slot, so it never unseats anyone: step 6 refuses
    # (or, in a single-slot box, goes unslotted) if a spool took it meanwhile.
    slot_was_picked = False
    # The pick feeds the head the spool is leaving: the spool is stored in the
    # box and not loaded straight back (a slotless move off a head into a box).
    store_only = False
    # `unslotted` (Group 40.6): the caller chose no slot (Return's "No slot"), so none is picked.
    if not target_slot and not unslotted and tgt_info and len(spools) == 1 and not (is_printer or is_toolhead):
        try:
            max_slots_auto = int(str(tgt_info.get('Max Spools', '0')).strip() or '0')
        except (TypeError, ValueError):
            max_slots_auto = 0
        if max_slots_auto > 1:
            moving = {str(s) for s in spools}
            # Strictly (Group 41 review): a fail-open read answered [] on a
            # Spoolman blip, so slot 1 was picked whoever held it, and the slot
            # block in step 6 then unseated that spool.
            try:
                in_box = spoolman_api.get_spools_at_location_detailed_strict(target) or []
            except Exception as _pick_err:
                why = f"couldn't read {target} from Spoolman to pick a free slot ({_pick_err})"
                for sid in spools:
                    failures[str(sid)] = why
                state.add_log_entry(f"❌ Not moved to <b>{target}</b>: {why}", "ERROR", "ff4444")
                return {"status": "error", "msg": f"Not moved: {why}.", "failures": failures}
            # slot -> the other spools that hold it, directly or as the slot a
            # deployed spool came from. Its own slot: where it sits in the box,
            # else (Group 40 review) the slot it was deployed from, which it
            # still physically holds; putting it back there from its head is an
            # unload, so that pick only stores it (below). It used to take the
            # lowest free slot and load another head. One reading with the slot
            # picker's ⭐ (box_slot_claims, Group 40.1).
            claims, own_slot, ghost_slot = box_slot_claims(tgt_info, target, in_box, moving)
            box_feeds = tgt_info.get('Type') == locations_db.DRYER_BOX_TYPE and auto_deploy
            # Where the spool is now: a slot feeding the head it is leaving only
            # stores it (below), so that slot never asks. Read failing closed
            # (Group 40 review): a blip turned "store it off its head" into a
            # silent load onto another head.
            mover = _spool_record(spools[0]) if box_feeds else None
            if box_feeds and mover is None:
                why = f"couldn't read #{spools[0]} from Spoolman to pick a slot in {target}"
                for sid in spools:
                    failures[str(sid)] = why
                state.add_log_entry(f"❌ Not moved to <b>{target}</b>: {why}", "ERROR", "ff4444")
                return {"status": "error", "msg": f"Not moved: {why}.", "failures": failures}
            moving_from = str((mover or {}).get('location') or '').strip().strip('"').upper()

            def _pick_residents(head):
                try:
                    return _residents_of(head)
                except Exception as e:
                    raise RuntimeError(f"couldn't read {head} from Spoolman to pick a slot in {target} ({e})")

            def _would_prompt(slot):
                """The shared rule (slot_would_prompt), over strict reads that
                refuse the move when Spoolman can't say."""
                if not box_feeds:
                    return False
                return slot_would_prompt(tgt_info, slot, moving_from, printer_map, loc_info_map,
                                         _pick_residents)

            if picked_slot:
                # The replay of a question about this pick: the same slot while
                # it is free. Otherwise nothing moves: it never unseats a spool
                # that took the slot while the user was deciding.
                if (picked_slot.isdigit() and 1 <= int(picked_slot) <= max_slots_auto
                        and picked_slot not in claims):
                    pick, pick_why = picked_slot, 'picked'
                else:
                    holders = claims.get(picked_slot) or []
                    if holders or (picked_slot.isdigit() and 1 <= int(picked_slot) <= max_slots_auto):
                        why = (f"{target} slot {picked_slot} was taken"
                               + (f" by {_and_list('#' + str(h) for h in holders)}" if holders else "")
                               + " while you were deciding, so nothing moved — try again")
                    else:
                        # The box lost the slot (its Max Spools lowered) while the
                        # user decided (Group 40 review): it wasn't "taken".
                        why = f"{target} has no slot {picked_slot} any more, so nothing moved — try again"
                    for sid in spools:
                        failures[str(sid)] = why
                    state.add_log_entry(f"⚠️ Not moved: {why}.", "WARNING", "ffaa00")
                    return {"status": "error", "blocked_reason": "picked_slot_taken",
                            "msg": f"Not moved: {why}.", "failures": failures}
            else:
                try:
                    pick, pick_why = recommend_box_slot(max_slots_auto, claims, own_slot, _would_prompt)
                except Exception as _pick_err:
                    for sid in spools:
                        failures[str(sid)] = str(_pick_err)
                    state.add_log_entry(f"❌ Not moved to <b>{target}</b>: {_pick_err}", "ERROR", "ff4444")
                    return {"status": "error", "msg": f"Not moved: {_pick_err}.", "failures": failures}
            if pick:
                target_slot = pick
                slot_was_picked = True
                state.logger.info(f"🪑 Auto-slot: {target} slot {pick}, {_AUTO_SLOT_WHY.get(pick_why, pick_why)}")
                if (moving_from and _slot_binding(tgt_info, pick) == moving_from) or \
                        (ghost_slot and pick == ghost_slot):
                    store_only = True
                    state.logger.info(f"🪑 {target} slot {pick} feeds {moving_from}, which #{spools[0]} is "
                                      f"leaving: it is stored there, not loaded back")
        elif locations_db._is_single_slot_dryer_box(tgt_info):
            # Group 42.2: a single-slot box has one place, so its spool is in
            # slot 1. It used to be stored blank, which left a toolhead's
            # Quick-Swap tile for the box reading empty while its spool was
            # loaded. Only while no other spool claims slot 1 (Group 42 review):
            # the box's own spool, deployed to a head, still holds it through
            # its trail, and a second spool in slot 1 made Quick-Swap move a
            # different spool than its card showed (and Return unseat the one
            # it had just said it would leave alone). Such a spool goes in
            # unslotted. A read that fails leaves it unslotted too: no slot is
            # claimed, so nothing can be unseated. (A `picked_slot` "1" decides
            # the same way.)
            try:
                _in_box = [o for o in (spoolman_api.get_spools_at_location_detailed_strict(target) or [])
                           if str(o.get('id')) not in {str(s) for s in spools}]
                _taken_by = next((o.get('id') for o in _in_box if locations_db.effective_slot(
                    tgt_info, o.get('slot', ''), occupants=len(_in_box)) == '1'), None)
                _why_unslotted = f"slot 1 is taken by #{_taken_by}" if _taken_by is not None else ""
            except Exception as _pick_err:
                _why_unslotted = f"couldn't read it from Spoolman ({_pick_err})"
            if not _why_unslotted:
                target_slot = '1'
                slot_was_picked = True
            else:
                state.logger.info(f"🪑 {target}: {_why_unslotted} — the spool goes in unslotted")

    # Step 4 (Group 39.4): the moving spools' own records. A spool loaded on a
    # printer head is LEAVING it (role 'source', D6), unless this re-scans it
    # onto the head it already sits on. Read only when the confirm doesn't
    # cover every head, so the True path (internal callers, the legacy browser
    # flag) reads exactly what it always did. The write loop re-reads each
    # record rather than trust one read before a printer probe.
    sources: typing.Dict[str, typing.List[int]] = {}
    # True only when every moving spool's own record already puts it on the
    # target: a re-scan onto its own head moves nothing, so it isn't asked
    # about (39.4), unless Smart Load would unload another resident.
    all_here = False
    every_head_covered = _confirm_scope(confirm_active_print)[0]
    moving_records: typing.Dict[str, typing.Any] = {}
    if not every_head_covered:
        unreadable = []
        here_count = 0
        for sid in spools:
            rec = spoolman_api.get_spool(sid)
            if not rec:
                unreadable.append(str(sid))
                continue
            moving_records[str(sid)] = rec
            here = str(rec.get('location') or '').strip().upper()
            if here == target:
                here_count += 1
            if here and here != target and here in printer_map:
                sources.setdefault(here, []).append(int(sid))
        all_here = here_count == len(spools)
        if unreadable:
            names = ", ".join(f"#{u}" for u in unreadable)
            for sid in spools:
                failures[str(sid)] = ("could not read the spool from Spoolman" if str(sid) in unreadable
                                      else f"not moved: could not read {names} from Spoolman")
            state.add_log_entry(
                f"❌ Not moved to <b>{target}</b>: could not read {names} from Spoolman, so FCC "
                f"can't tell whether it is leaving a printing head", "ERROR", "ff4444")
            return {"status": "error", "msg": f"Not moved: could not read {names} from Spoolman.",
                    "failures": failures}

    # Step 4 (Group 51 review, engine-1; Derek, 2026-10-20): an archived spool is
    # never left archived on a head. A move's write doesn't un-archive one (51.1),
    # and every reader of a head (Smart Load, the print deduct, Printer Status)
    # lists only spools in stock, so an archived spool on a head was invisible
    # there: the next print charged nothing and a second spool was loaded on top
    # of it. Derek's rule: spools are archived because they hit 0 g, rarely by
    # hand, so one whose record still has filament on it (at least
    # UNARCHIVE_ON_LOAD_MIN_G) and is being loaded physically has filament: the
    # head write un-archives it (`unarchived` in the answer, a WARNING line). One
    # at 0 g, or with no known weight, is refused with nothing written
    # (`blocked_reason: archived`), and so is any archived spool when the caller
    # keeps it archived (`keep_archived`: a wizard Save that ticks Archived). Into
    # a bound slot the box write stores it, and the chained deploy (this same
    # check) loads it or says why not. Read for every head move, the True path
    # included (the chain may run under it); an unreadable record is left to the
    # write loop's read. Undo puts the spool back but leaves it in stock.
    unarchive_on_load: typing.Dict[str, float] = {}
    if is_printer or is_toolhead:
        refused_archived = []
        for sid in spools:
            rec = moving_records.get(str(sid)) or spoolman_api.get_spool(sid)
            if not (isinstance(rec, dict) and str(rec.get('archived')).strip().lower() == 'true'):
                continue
            left = _filament_left_g(rec)
            if not keep_archived and left is not None and left >= UNARCHIVE_ON_LOAD_MIN_G:
                unarchive_on_load[str(sid)] = left
            else:
                refused_archived.append((sid, left))
        if refused_archived:
            whys = []
            for sid, left in refused_archived:
                if left is None:
                    whys.append(f"#{sid} is archived and its record doesn't say how much filament is left, so it "
                                f"was not loaded onto {target}: weigh it back into stock first")
                elif left < UNARCHIVE_ON_LOAD_MIN_G:
                    whys.append(f"#{sid} is archived with no filament left on its record ({max(left, 0.0):.0f} g), "
                                f"so it was not loaded onto {target}: weigh it back into stock first")
                else:
                    whys.append(f"#{sid} is archived, so it was not loaded onto {target}: untick Archived to load it")
            why = "; ".join(whys)
            for sid in spools:
                failures[str(sid)] = why
            state.add_log_entry(f"⚠️ Not loading onto {target}: {why}.", "WARNING", "ffaa00")
            return {"status": "error", "blocked_reason": "archived", "msg": f"Not loaded: {why}.",
                    "failures": failures}

    # Step 4 (Group 39.7, R1-03): the target head's residents, read strictly.
    # The old fail-open read answered [] on a Spoolman blip, so an occupied
    # head looked empty and the incoming spool landed on top of its resident.
    # A resident is a spool whose OWN record says it is on this head: the
    # matcher also returns ghosts (a stale physical_source naming this head)
    # and, for a Printer row, every toolhead's spool by prefix. Those are
    # skipped on the row, with no read of their own (R1-02).
    def _strict_residents():
        """(residents, None), or (None, the fail-closed answer)."""
        try:
            residents_now = strict_direct_occupants(target, exclude=spools)
        except Exception as e:
            state.logger.error(f"Smart Load: resident read failed for {target}: {e}")
            why = f"could not read {target} from Spoolman"
            for sid in spools:
                failures[str(sid)] = why
                state.add_log_entry(
                    f"❌ <b>Smart Load:</b> not loading Spool #{sid} onto {target} — {why}",
                    "ERROR", "ff4444")
            return None, {"status": "error", "msg": f"Not loaded: {why}.", "failures": failures}
        return residents_now, None

    def _residents_changed(residents_now):
        """Group 51.6: the page named the spools it showed on this head when the
        user picked it (the Printer picker's "XL-3 holds #99"). A spool on it now
        that wasn't among them was never shown, so it is not unloaded unasked:
        the answer refuses the move, nothing written, and the picker opens
        again. One that left meanwhile is fine (the head is filled as asked)."""
        if expected_residents is None or not (is_printer or is_toolhead):
            return None
        shown = {str(x) for x in expected_residents}
        arrived = [r for r in (residents_now or []) if str(r) not in shown]
        if not arrived:
            return None
        was = (f"it held {_and_list('#' + str(x) for x in expected_residents)}" if expected_residents
               else "it was empty")
        why = (f"{target} now holds {_and_list('#' + str(r) for r in arrived)}, which wasn't on it when you "
               f"picked {target} ({was}), so {_and_list('#' + str(s) for s in spools)} was not loaded: "
               f"pick again")
        for sid in spools:
            failures[str(sid)] = why
        state.add_log_entry(f"⚠️ Not loading onto {target}: {why}.", "WARNING", "ffaa00")
        return {"status": "error", "blocked_reason": "residents_changed", "msg": f"Not loaded: {why}.",
                "failures": failures}

    residents: typing.List[typing.Any] = []
    if is_printer or is_toolhead:
        residents, refused = _strict_residents()
        if refused:
            return refused
        refused = _residents_changed(residents)
        if refused:
            return refused

    # Step 4 (Group 40.5, D3 / item G): the "came from" slot the user named in the
    # Printer picker, checked before anything is written: a multi-slot Dryer
    # Box's slot that feeds this head and that no other spool holds (read
    # strictly). Re-checked at the write, which records nothing if another
    # spool took it during the printer probe.
    record_named = None
    if (is_printer or is_toolhead) and isinstance(record_source, dict):
        r_box = str(record_source.get('box') or '').strip().strip('"').upper()
        r_slot = _norm_slot(record_source.get('slot'))
        r_row = loc_info_map.get(r_box)
        why = ''
        if not _is_dryer_box_row(r_row) or locations_db._is_single_slot_dryer_box(r_row):
            why = f"{r_box or 'that box'} isn't a box with slots"
        elif _slot_binding(r_row, r_slot) != target:
            why = f"{r_box} slot {r_slot} doesn't feed {target}"
        else:
            try:
                _r_items = spoolman_api.get_spools_at_location_detailed_strict(r_box) or []
                _r_claims, _o, _g = box_slot_claims(r_row, r_box, _r_items, spools)
                _r_holders = _r_claims.get(r_slot) or []
                if _r_holders:
                    why = f"{r_box} slot {r_slot} holds {_and_list('#' + str(h) for h in _r_holders)}"
            except Exception as _r_err:
                why = f"couldn't read {r_box} from Spoolman ({_r_err})"
        if why:
            moving = _and_list('#' + str(s) for s in spools)
            msg = f"Not moved: {why}, so {moving} can't be recorded as coming from it"
            for sid in spools:
                failures[str(sid)] = msg
            state.add_log_entry(f"⚠️ {msg}.", "WARNING", "ffaa00")
            return {"status": "error", "blocked_reason": "record_source", "msg": msg + ".", "failures": failures}
        record_named = (r_box, r_slot)
    # A spool arriving from somewhere keeps that trail; the answer says the
    # named source (or "No box") was not used.
    record_ignored = False
    record_kept = ''   # the trail it kept instead (Group 40 review, BD-3), for the toast

    # The head a named slot feeds: the auto-deploy chain loads it. It counts only
    # when the chain will load it (I1-06): Return parks a spool with
    # auto_deploy=False, and must not ask about a head it never touches. A
    # single-slot box's slot 1 binding records where its OWN spool is loaded
    # (the Group 20.2 lifecycle), not a feed, so it is never a feeds head and
    # never auto-deploys (Group 42.2). A pick that feeds the head the spool is
    # leaving stores it (step 3). The chain loads exactly this head.
    feed_box = bool(tgt_info and tgt_info.get('Type') == locations_db.DRYER_BOX_TYPE
                    and not locations_db._is_single_slot_dryer_box(tgt_info))
    # What the target slot feeds NOW, in _feed_token's form ('' = no toolhead:
    # unbound, a Printer Pool slot, or no slot). Every question carries it as
    # `feed`; a replay sends it back as `expected_feed`.
    slot_feed = _slot_binding(tgt_info, target_slot) if (feed_box and target_slot) else ''
    # Step 4 (Group 40.3, Derek 2026-10-14, multi-user awareness): a replay names
    # the feed its question was about. A slot re-pointed while the dialog was
    # open is asked about again with nothing written, even when the new head is
    # empty and idle ("he fills slot 1 because a slicer file depends on it"). A
    # load is asked as a load: the new head is read below as for any load, so
    # step 5's question describes it and the next Yes covers it. A store
    # (auto_deploy off) is asked as a store (a stored spool is staged for
    # whatever the slot feeds), offering no load (Group 40.3 review, B1: the
    # browser keeps a chosen store a store, so a "Load it instead" there stored)
    # and reading no head. No I/O here.
    feed_changed = None
    if expected_feed is not None and feed_box and expected_feed != slot_feed:
        feed_changed = {"was": expected_feed, "now": slot_feed}
    bound_th = ''
    if feed_box and target_slot and auto_deploy and not store_only:
        bound_th = slot_feed
        if feed_changed and bound_th in sources:
            bound_th = ''   # the new feed is the head a moving spool leaves: a store (40.0e's rule)
    loads_head = bool(bound_th) and _holds_one_spool(bound_th, printer_map, loc_info_map)

    # Step 4 (Group 40.0c, Derek's D2.2): that head already runs a spool from
    # somewhere else. The chain unloaded it without a word on an idle printer
    # (Derek: "XL-1 running off a PolyDryer while slot 1 is prepped for later").
    # A resident whose trail is this very box and slot is the slot's own spool
    # coming back out, his everyday swap, and asks nothing new; any other trail,
    # or none (FCC can't tell where it is fed from), is asked about. A Yes
    # covers the spools it named (the confirm key), never one that arrived
    # since. Read strictly, once per head (step 3's pick may have read it); an
    # unreadable head or resident refuses the move before anything is written.
    fed_heads: typing.List[typing.Dict[str, typing.Any]] = []
    # The head's spools this move saw, for the chained deploy's guard (None: not
    # read, because the caller covered the head whatever it runs).
    fed_seen: typing.Optional[typing.Tuple[typing.Any, ...]] = None
    # What the read showed (Group 40 review): the head runs the slot's own spool,
    # which still physically holds the slot, so "Just store it" isn't offered;
    # or it is empty, so its sentence doesn't claim to unload anything.
    own_on_head = False
    empty_heads: typing.Set[str] = set()
    if loads_head and not _fed_blanket(confirmed_fed_heads, bound_th):
        def _fed_unreadable(why):
            for _sid in spools:
                failures[str(_sid)] = why
            state.add_log_entry(
                f"❌ Not moved to <b>{target}</b> slot {target_slot}: {why}, so FCC can't tell "
                f"whether {bound_th} (the toolhead that slot feeds) runs a spool from elsewhere",
                "ERROR", "ff4444")
            return {"status": "error", "msg": f"Not moved: {why}.", "failures": failures}
        try:
            fed_rids = _residents_of(bound_th)
        except Exception as e:
            return _fed_unreadable(f"couldn't read {bound_th} from Spoolman ({e})")
        elsewhere = []
        # The spools whose own record still put them on the head when it was
        # checked: what the question showed (or the slot's own spool). Only
        # these count as "seen" for the chained deploy's guard (Group 40 review,
        # engine:fed-seen-includes-left): a spool listed but already gone was
        # never shown, so if it comes back during the probe it is not unloaded
        # unasked.
        still_here = []
        for rid in fed_rids:
            rec = _spool_record(rid)
            if rec is None:
                return _fed_unreadable(f"couldn't read #{rid} on {bound_th} from Spoolman")
            if str(rec.get('location') or '').strip().strip('"').upper() != bound_th:
                continue   # it left the head between the two reads
            still_here.append(rid)
            if _same_feed(rec, target, target_slot, loc_info_map):
                own_on_head = True
            else:
                elsewhere.append(_fed_resident(rec, bound_th, printer_map, loc_list, loc_info_map))
        fed_seen = tuple(still_here)
        if not still_here:
            empty_heads.add(bound_th)
        # A re-pointed slot's question names the new head's spools even when an
        # old confirm key covers them (40.3): a re-point back (XL-1 -> XL-2 ->
        # XL-1) must name #99 again, though "XL-1#99" is still in the union.
        if elsewhere and (feed_changed or not _fed_covered(confirmed_fed_heads, bound_th, [r['id'] for r in elsewhere])):
            fed_heads.append({
                "toolhead": bound_th,
                "printer_name": str((printer_map.get(bound_th) or {}).get('printer_name') or bound_th),
                "box": target, "slot": _norm_slot(target_slot),
                "resident": elsewhere[0], "residents": elsewhere,
                # What "Load it instead" sends back in confirmed_fed_heads.
                "confirm_key": _fed_key(bound_th, [r['id'] for r in elsewhere]),
            })

    # Step 5. The heads the moving spools leave, the destination, and a named
    # slot's bound head (the auto-deploy chain loads it) are checked BEFORE any
    # Spoolman write, so the user is asked once, before anything moves, rather
    # than the chained call swallowing the answer. `confirm_active_print` is
    # True (covers every head), falsy (none) or the LocationIDs whose warning
    # the user saw. A fed head (40.0c) is the same one question, with its
    # active prints beside it.
    touched: typing.List[tuple] = [(head, 'source', sids) for head, sids in sources.items()]
    if not (all_here and not residents):
        touched.append((target, 'destination'))
    if bound_th:
        touched.append((bound_th, 'feeds'))
    active_prints = _uncovered_active_heads(touched, confirm_active_print, printer_map, spools)
    # Whether step 5 could have asked a printer (an uncovered head was touched),
    # for the race refusal's wording below (Group 40 review,
    # io:race-refusal-text-says-printer): "while FCC was checking the printer"
    # only when it could have been; else "meanwhile".
    probed = any(str(t[0] or '').strip().strip('"').upper() in printer_map
                 and not _confirm_covers(confirm_active_print, t[0]) for t in touched)
    # What a replay of any question sends back (Group 40.3): the target, whether
    # the engine picked the slot (`slot_picked`: replayed as picked_slot, never
    # as an Overwrite `slot`), what the slot feeds (`feed`: replayed as
    # expected_feed; None for a target that isn't a multi-slot box) and whether
    # the Yes loads a head (`can_load`).
    # `leaving` (Group 40.3 fix check, W4): the heads the moving spools leave,
    # printing or not, so a store's toast never says such a head "was left as
    # it was".
    replay = {"target": target, "slot_picked": bool(slot_was_picked),
              "feed": slot_feed if feed_box else None, "can_load": loads_head,
              "leaving": sorted(sources)}
    # Step 5 (Group 40.5: the 40.3 "Open, narrow" note and the 40.2 review's
    # stale-store note): before a question about a box slot, read the slot as
    # step 6 will, so a question never offers an answer step 6 then refuses. A
    # slot whose own spool runs on another head refuses the load and the store
    # alike: said now, with nothing written and no question. A slot a record
    # still claims (a spool deployed from it, or a stale trail) refuses a store:
    # no "Just store it". Only on the question path (no read otherwise), and only
    # for a named slot: a slot the engine picked (step 3) was read free of every
    # claim, deployed spools included; a race there is step 6's. An unreadable
    # slot asks as before, and step 6 reads it again.
    slot_ghosts: typing.List[typing.Dict[str, typing.Any]] = []
    if (feed_changed or fed_heads or active_prints) and feed_box and target_slot and not slot_was_picked:
        try:
            _q_items = spoolman_api.get_spools_at_location_detailed_strict(target) or []
            _q_moving = {str(s) for s in spools}
            slot_ghosts = [e for e in _q_items if e.get('is_ghost') and str(e.get('id')) not in _q_moving
                           and _norm_slot(e.get('slot', '')) == target_slot]
        except Exception as _q_err:
            state.logger.info(f"Slot read before the question skipped for {target} slot {target_slot}: {_q_err}")
        # The step-6 guard's own rule: a load passes over the slot's own spool on
        # the head it feeds (the same-slot swap) and a stale trail; a store
        # passes over none.
        _blocking = [g for g in slot_ghosts
                     if not (loads_head and (_ghost_head(g) == bound_th
                                             or not _holds_one_spool(_ghost_head(g), printer_map, loc_info_map)))]
        if _blocking:
            why = _ghost_claim_refusal(target, target_slot, _blocking[0], slot_feed, bound_th, loads_head,
                                       printer_map, loc_info_map)
            for sid in spools:
                failures[str(sid)] = why
            state.add_log_entry(f"❌ Not moving {_and_list('#' + str(s) for s in spools)}: {why}",
                                "ERROR", "ff4444")
            return {"status": "error", "blocked_reason": "slot_claimed", "msg": f"Not moved: {why}.",
                    "failures": failures}
    no_store = bool(slot_ghosts)
    if feed_changed:
        answer = _feed_changed_answer(
            feed_changed, fed_heads, active_prints, target, target_slot, spools, tgt_info,
            bound_th, loads_head, can_store=((not own_on_head) if loads_head else True) and not no_store,
            leaving=bool(slot_feed) and slot_feed in sources,
            repicked=bool(slot_was_picked and picked_slot is None and not feed_changed['was']),
            empty_heads=empty_heads, printer_map=printer_map, loc_info_map=loc_info_map)
        answer.update(replay)
        return answer
    if fed_heads:
        answer = _head_fed_answer(fed_heads, active_prints, target, target_slot, spools,
                                  empty_heads=empty_heads, can_store=not own_on_head and not no_store,
                                  printer_map=printer_map)
        answer.update(replay)
        return answer
    if active_prints:
        answer = _requires_confirm_answer(active_prints, target, target_slot, residents, spools=spools,
                                          empty_heads=empty_heads)
        answer.update(replay)
        # "Just store it" (40.3) is an answer only where a store differs from a
        # load: a slot whose chain would load a head. Its three-way dialog asks
        # in the `title` and explains in the `body` (`msg` minus "Continue?",
        # which no button there answers); `msg` keeps the yes/no wording.
        # Not while the head runs the slot's own spool (Group 40 review): the
        # slot still holds it, so storing another there makes two claim it.
        # And only when the head the chain loads is itself mid-print (Group 40.3
        # review, C5): Enter stores because a head isn't loaded mid-print, so a
        # print on the head the spool only LEAVES keeps the yes / no.
        offers_store = bool(loads_head and _head_print_state(bound_th, active_prints, printer_map))
        answer['can_store'] = offers_store and not own_on_head and not no_store
        if offers_store:
            answer['title'] = f"Load #{spools[-1]} onto {bound_th}?"
            m = answer['msg']
            answer['body'] = m[:-len("Continue?")].strip() if m.endswith("Continue?") else m
        answer['printing'] = True
        return answer

    # L298 Phase 0 — undo hardening: `extras` snapshots each moved spool's
    # system-managed extras (container_slot / physical_source /
    # physical_source_slot) as they were BEFORE the move, so perform_undo can
    # restore them — not just `location` — making an undo a TRUE rollback (the
    # spool returns to its exact slot + ghost state). Benefits single moves too;
    # a prerequisite for a trustworthy bulk-move undo.
    # `released` / `ejection_released` (Group 42 review): the single-slot box each
    # spool's leaving released from its head, so Undo re-attaches exactly that,
    # and never a box the move did not release.
    # `displaced` (Swap option C): {sid: {"location", "extras"}} for each stored
    # spool a Swap took out of its slot, so Undo puts it back in that slot.
    undo_record: typing.Dict[str, typing.Any] = {"target": target, "moves": {}, "extras": {}, "labels": {}, "ejections": {}, "ejection_extras": {}, "released": {}, "ejection_released": {}, "displaced": {}, "summary": f"Moved {len(spools)} -> {target}", "origin": origin}

    # Step 6 opens with a fresh strict list of the head (review engine-2): the
    # step-4 list was read BEFORE the source reads and the printer probe, which
    # take seconds when a printer is unreachable, and a spool another request
    # loads onto the head meanwhile must be unloaded too, or the head holds
    # two. The True path has no probe and no source reads, so it keeps one read.
    if (is_printer or is_toolhead) and not every_head_covered:
        residents, refused = _strict_residents()
        if refused:
            return refused
        # Group 51.6: a spool loaded onto the head during the probe was never
        # shown to a user who named what the head held.
        refused = _residents_changed(residents)
        if refused:
            return refused

    # Group 40.0c, the chained deploy's guard. The bound-slot move read this
    # head's spools before its printer probe, which can take seconds. A spool
    # loaded onto the head meanwhile was never shown to the user, so it is not
    # unloaded unasked, whatever its trail says (a spare scanned onto the head
    # records the one free slot that feeds it, 40.0d). Nothing is written: the
    # spool stays in its slot and the outer move reports it as not deployed.
    # (The `_fed_blanket` clause is defensive: fed_check_from is None exactly
    # when the outer move's caller covered the head whatever it runs.)
    if (fed_check_from and residents and (is_printer or is_toolhead)
            and not _fed_blanket(confirmed_fed_heads, target)):
        g_box, g_slot, g_seen = fed_check_from
        seen = {str(x) for x in (g_seen or ())}
        arrived = [rid for rid in residents if str(rid) not in seen]
        if arrived:
            named, claimers = [], []
            for rid in arrived:
                rec = _spool_record(rid)
                named.append(_fed_resident(rec, target, printer_map, loc_list, loc_info_map)
                             if rec else {"id": rid, "from": ""})
                if rec and _same_feed(rec, g_box, g_slot, loc_info_map):
                    claimers.append(rid)
            loading = _and_list('#' + str(s) for s in spools)
            why = (f"{target} started running {_running_text(named)} while FCC was checking the "
                   f"printer, so {loading} stayed in {g_box} slot {g_slot} and was not loaded. ")
            if claimers:
                # Its trail claims this slot too (Group 40 review); Quick-Swap
                # refuses a slot two spools claim, so don't send the user there.
                why += (f"{_and_list('#' + str(c) for c in claimers)} also claims that slot: open "
                        f"{g_box} and move one of them")
            else:
                why += f"To load it, use {target}'s Quick-Swap ({g_box} slot {g_slot})"
            for sid in spools:
                failures[str(sid)] = why
            state.add_log_entry(f"⚠️ Not loading onto {target}: {why}.", "WARNING", "ffaa00")
            return {"status": "error", "blocked_reason": "head_fed", "msg": f"Not loaded: {why}.",
                    "failures": failures}

    # The slot's own spools Smart Load swapped out into the scan buffer (the
    # same-slot swap, `swap_slot`), and their buffer entries for the answer.
    swapped_out: typing.List[typing.Any] = []
    # Where each swapped-out spool was filed (Swap option C), for its toast.
    swapped_filed: typing.Dict[str, str] = {}
    to_buffer: typing.List[typing.Dict[str, typing.Any]] = []
    # The archived spools the head write un-archived (step 4's rule), for the answer.
    unarchived: typing.List[typing.Dict[str, typing.Any]] = []
    # The stored spools a Swap (`swap_out`) took out of the slot, in order.
    displaced_out: typing.List[typing.Any] = []

    # --- SMART LOAD LOGIC (Auto-Eject Resident) ---
    if residents:
        # 2026-09-12: the head must really be empty before the incoming spool is
        # written, or it holds two (Derek's bulk-move active-print testing). The
        # old `if perform_smart_eject(rid):` read the eject's refusals as
        # success: the active-print dict and the "REQUIRE_CONFIRM" string are
        # both truthy, so the resident stayed and the incoming spool landed on
        # top of it.
        #  - `residents` (step 4) holds only spools whose OWN record puts them on
        #    this head; "ejecting" a ghost or another head's prefix hit pulled
        #    spools off other heads.
        #  - The eject carries the caller's confirm (the pre-flight above probed
        #    this head) and a decided home for a resident with none: the Room
        #    its printer sits in, else Unassigned (Derek, 2026-09-12).
        #  - Only True counts. A resident that cannot be moved, or read, refuses
        #    the whole move.
        homeless_dest = None
        stuck: typing.Dict[typing.Any, str] = {}
        for rid in residents:
            before = spoolman_api.get_spool(rid)
            if not before:
                stuck[rid] = "it could not be read from Spoolman"
                continue
            if str(before.get('location') or '').strip().upper() != target:
                continue  # it left the head between the two reads
            if homeless_dest is None:
                homeless_dest = _known_room_of(target, loc_list)
            before_extra = dict(before.get('extra') or {})
            # Group 40, the same-slot swap (Derek, 2026-10-15): the slot's OWN
            # spool, coming off the head because the chain is loading that very
            # slot's new spool, is in the user's hand. It goes to the scan
            # buffer: "home" was the slot the new spool now holds, so it landed
            # in the box with no slot (5/4, and no Quick-Swap tile).
            own_slot_swap = bool(swap_slot) and _same_feed(before, swap_slot[0], swap_slot[1], loc_info_map)
            # perform_smart_eject takes a boolean: covered when the confirm
            # covers the head this resident is unloaded from (Group 39.1).
            _eject_report: typing.Dict[str, typing.Any] = {}
            ejected = perform_smart_eject(
                rid, confirm_active_print=_confirm_covers(confirm_active_print, target),
                homeless_destination=homeless_dest, report=_eject_report, to_buffer=own_slot_swap,
                # Swap option C: filed back where it sat before that slot.
                swapped_from=swap_slot if own_slot_swap else None,
            )
            if ejected is not True:
                stuck[rid] = _eject_refusal_reason(ejected)
                continue
            # Undo puts the resident back on this head, ghost trail included,
            # and re-attaches the box its eject released.
            undo_record['ejections'][rid] = target
            undo_record['ejection_extras'][rid] = {
                k: before_extra.get(k, '') for k in spoolman_api.SYSTEM_MANAGED_EXTRAS
            }
            undo_record['ejection_released'][str(rid)] = list(_eject_report.get('released_boxes') or [])
            # perform_smart_eject has already logged where it went.
            if own_slot_swap:
                # Undo takes it back out of the buffer when it puts it on the head.
                swapped_out.append(rid)
                swapped_filed[str(rid)] = str(_eject_report.get('filed') or '')
                _filed = swapped_filed[str(rid)]
                state.add_log_entry(
                    f"⚠️ <b>Smart Load:</b> unloaded #{rid} from {target} into the scan buffer"
                    f"{f' (filed back in {_filed})' if _filed else ''}: it came "
                    f"from {swap_slot[0]} slot {_norm_slot(swap_slot[1])}, which "
                    f"{_and_list('#' + str(s) for s in spools)} now takes", "WARNING")
            else:
                state.add_log_entry(f"⚠️ <b>Smart Load:</b> unloaded #{rid} from {target}", "WARNING")
        if swapped_out:
            to_buffer, _added = _put_in_buffer(swapped_out, off_head=target, filed=swapped_filed)
            # Only what the move added (Group 40.2 review): a spool the user had
            # already buffered stays buffered when the move is undone.
            undo_record['buffered'] = list(_added)
        if stuck:
            held = ", ".join(f"#{rid} ({why})" for rid, why in stuck.items())
            for sid in spools:
                failures[str(sid)] = f"{target} still holds {held}"
                state.add_log_entry(
                    f"❌ <b>Smart Load:</b> not loading Spool #{sid} onto {target} — it still holds {held}",
                    "ERROR", "ff4444")
            if undo_record['ejections']:
                # Nothing was loaded, but some residents were unloaded: keep that
                # undoable, under a summary that says what undo puts back.
                undo_record['summary'] = (
                    f"Unloaded {', '.join('#' + str(r) for r in undo_record['ejections'])} from {target}")
                _push_undo(undo_record)
            stuck_answer: typing.Dict[str, typing.Any] = {
                "status": "error", "msg": f"Not loaded: {target} still holds {held}.", "failures": failures}
            if to_buffer:
                stuck_answer["to_buffer"] = to_buffer
            return stuck_answer

    # L298 Phase 3 — per-spool failure attribution. Each write branch below
    # already reads spoolman_api.LAST_SPOOLMAN_ERROR ADJACENT to its own failing
    # call (the CLAUDE.md rule); this just keeps what it read, keyed by spool, so
    # a batch caller can say WHICH spool failed and WHY. Bulk move used to read
    # the module global once, AFTER the whole loop and two readbacks — by then a
    # later success had reset it to None (every failed row got the useless "see
    # Activity Log") or a second failure had overwritten it (both rows blamed on
    # the last error).
    for sid in spools:
        spool_data = spoolman_api.get_spool(sid)
        if not spool_data:
            # A FIXED string, deliberately: spoolman_api.get_spool swallows its
            # exception and does NOT touch LAST_SPOOLMAN_ERROR, so reading the
            # global here would attribute some OTHER spool's (or some other
            # request's) stale error to this one — reintroducing exactly the
            # mis-attribution this map exists to remove. The rule is "read it
            # ADJACENT to the failing call"; this call has no error channel.
            failures[str(sid)] = "could not read the spool from Spoolman"
            continue
        current_loc = spool_data.get('location', '').strip().upper()
        undo_record['moves'][sid] = current_loc
        current_extra: dict = dict(spool_data.get('extra') or {})
        # L298 Phase 0: snapshot the pre-move system-managed extras (absent → ''
        # so undo clears a key the move adds). perform_undo overlays these back.
        undo_record['extras'][sid] = {
            k: current_extra.get(k, '') for k in spoolman_api.SYSTEM_MANAGED_EXTRAS
        }
        info = spoolman_api.format_spool_display(spool_data)
        # Capture the rich display label now (already computed for the forward-
        # move log) so the Undo line can name the spool + source, not just a
        # count — see perform_undo's readable from→to rendering.
        undo_record['labels'][sid] = info['text']
        
        new_extra: typing.Dict[str, typing.Any] = dict(current_extra)
        
# Handle Slot Assignment
        # A head holds one spool, and Smart Load has already emptied it after a
        # strict read, so a head named with a slot (LOC:SOLO:SLOT:1) has nothing
        # to unseat. Reading it again, after that unload, could only fail the
        # load and leave the head empty (Group 41 review).
        seat_slot = target_slot
        if target_slot and not (is_printer or is_toolhead):
            # Group 41.6: read the slot STRICTLY, and seat nothing in a slot that
            # couldn't be cleared. The fail-open read answered [] on a timeout,
            # and a rejected unseat only logged, so the incoming spool was seated
            # anyway and two spools claimed one slot.
            try:
                existing_items = spoolman_api.get_spools_at_location_detailed_strict(target)
            except Exception as _slot_err:
                failures[str(sid)] = (f"couldn't read {target} from Spoolman to check slot "
                                      f"{target_slot} ({_slot_err})")
                state.add_log_entry(
                    f"❌ Not moving Spool #{sid} into {target} slot {target_slot}: couldn't read "
                    f"{target} from Spoolman ({_slot_err})", "ERROR", "ff4444")
                continue
            if expected_occupant is not None and not slot_was_picked:
                # Group 51.7: the user chose Swap / Overwrite for the spool the
                # screen showed in this slot (the grid's prompt, the slot picker).
                # Another spool filed there now was never shown, so it is not
                # swapped out or unseated: this spool is refused, nothing written.
                # A slot its spool left meanwhile is filled as asked.
                _moving = {str(s) for s in spools}
                _stored = [e for e in existing_items if not e.get('is_ghost') and str(e.get('id')) not in _moving
                           and str(e.get('location') or '').strip().strip('"').upper() == target]
                _now = [e.get('id') for e in _stored
                        if str(e.get('id')) != str(expected_occupant)
                        and _norm_slot(locations_db.effective_slot(tgt_info, e.get('slot', ''),
                                                                   occupants=len(_stored))) == target_slot]
                if _now:
                    failures[str(sid)] = (f"{target} slot {target_slot} holds "
                                          f"{_and_list('#' + str(t) for t in _now)} now, not #{expected_occupant} "
                                          f"as when you chose, so nothing moved: look at the slot again")
                    step6_refused[str(sid)] = 'occupant_changed'
                    state.add_log_entry(f"⚠️ Not moving Spool #{sid}: {failures[str(sid)]}", "WARNING", "ffaa00")
                    continue
            if slot_was_picked:
                # Group 40.0e: the engine chose this slot before the printer probe,
                # which can take seconds. A pick never unseats a spool that took
                # the slot meanwhile (in it, or deployed from it): a multi-slot box
                # refuses this spool and writes nothing, and a single-slot box takes
                # it unslotted, as 42.2 does. An explicit slot keeps Overwrite.
                _moving = {str(s) for s in spools}
                _others = [e for e in existing_items if str(e.get('id')) not in _moving]
                _took = [e.get('id') for e in _others if _norm_slot(locations_db.effective_slot(
                    tgt_info, e.get('slot', ''), occupants=len(_others))) == target_slot]
                if _took:
                    _who = _and_list('#' + str(t) for t in _took)
                    if locations_db._is_single_slot_dryer_box(tgt_info):
                        seat_slot = ''
                        state.logger.info(f"🪑 {target}: {_who} took slot 1 meanwhile — the spool goes in unslotted")
                    else:
                        _when = "while FCC was checking the printer" if probed else "meanwhile"
                        failures[str(sid)] = (f"{target} slot {target_slot} was filled by {_who} {_when}, "
                                              f"so nothing moved — try again")
                        state.add_log_entry(f"❌ Not moving Spool #{sid}: {failures[str(sid)]}",
                                            "ERROR", "ff4444")
                        continue
            else:
                # Group 40 review: a slot whose own spool is deployed (its ghost
                # claims the slot) still physically holds that spool. Only the
                # chain's Smart Load swaps it out, and only from the head the slot
                # feeds (Derek's same-slot swap). Anywhere else, seating another
                # spool there made two claim one slot: a store, an unbound slot, a
                # slot bound to something that isn't a head (40.3), or a slot
                # re-pointed while its own spool stayed on the head it used to
                # feed (Group 40.3 review, A1: the load, and a blind scan, took
                # the slot anyway). Refused, nothing written (a single-slot box
                # takes it unslotted, as 42.2 does). A trail whose spool is on
                # no head is stale (a Location edit keeps the trail): a load
                # ignores it, as it always did (Group 40.3 fix check, E1/S1:
                # Derek's blind slot scan was refused over a spool on a cart),
                # and a store still refuses, naming it.
                _moving = {str(s) for s in spools}
                _ghosts = [e for e in existing_items if e.get('is_ghost') and str(e.get('id')) not in _moving
                           and _norm_slot(e.get('slot', '')) == target_slot
                           and not (loads_head and (_ghost_head(e) == bound_th or not _holds_one_spool(
                               _ghost_head(e), printer_map, loc_info_map)))]
                if _ghosts:
                    if locations_db._is_single_slot_dryer_box(tgt_info):
                        seat_slot = ''
                    else:
                        failures[str(sid)] = _ghost_claim_refusal(target, target_slot, _ghosts[0], slot_feed,
                                                                  bound_th, loads_head, printer_map, loc_info_map)
                        step6_refused[str(sid)] = 'slot_claimed'
                        state.add_log_entry(f"❌ Not moving Spool #{sid}: {failures[str(sid)]}",
                                            "ERROR", "ff4444")
                        continue
            unseat_failed = None
            for existing in (existing_items if seat_slot else []):
                # A ghost (a spool deployed FROM this slot) is listed with its
                # trail's slot. Clearing its own container_slot never frees that
                # slot, and since 41.6 a failure of that pointless write refused
                # the incoming spool (Group 41 review), so ghosts are left alone.
                if existing.get('is_ghost'):
                    continue
                # Only a spool filed AT this location (Group 40 review, R1): the
                # read also lists first-segment prefix hits, so a slot move onto
                # a Room ("LR", slot 1) unseated slot 1 of every LR-* box.
                if str(existing.get('location') or '').strip().strip('"').upper() != target:
                    continue
                # [ALEX FIX] Improved comparison to catch string vs int mismatches
                # (and, since 40.0c, quoted or zero-padded slots: one slot form).
                if _norm_slot(existing.get('slot', '')) == seat_slot and existing['id'] != int(sid) and swap_out:
                    # Swap option C (Derek, 2026-10-15): the user chose Swap, so
                    # the slot's stored spool is in their hand. It goes to the scan
                    # buffer AND is filed back where it sat before this slot (a
                    # free slot it came from, else the plain place behind it, else
                    # Unassigned), never left in the box with no slot.
                    _out = _spool_record(existing['id'])
                    if _out is None:
                        unseat_failed = (f"couldn't read #{existing['id']} from Spoolman to swap it out of "
                                         f"slot {target_slot}")
                        state.add_log_entry(f"❌ Not swapping #{existing['id']} out of {target} slot "
                                            f"{target_slot}: couldn't read it from Spoolman", "ERROR", "ff4444")
                        break
                    _snap = {k: (_out.get('extra') or {}).get(k, '') for k in spoolman_api.SYSTEM_MANAGED_EXTRAS}
                    _landed_out, _floc, _fslot = _swap_out_write(existing['id'], _out, target, seat_slot,
                                                                 loc_info_map)
                    if not _landed_out:
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to swap Spool #{existing['id']} out of {target} slot {target_slot}: {err}",
                            "ERROR", "ff4444")
                        unseat_failed = f"couldn't swap #{existing['id']} out of slot {target_slot}: {err}"
                        break
                    undo_record['displaced'][str(existing['id'])] = {"location": target, "extras": _snap}
                    _ftxt = _filed_text(_floc, _fslot, loc_info_map)
                    displaced_out.append((existing['id'], _ftxt))
                    state.add_log_entry(
                        f"✋ Swapped #{existing['id']} out of {target} slot {target_slot} into the scan buffer; "
                        + (f"FCC files it back in {_ftxt}, where it sat before that slot." if _ftxt else
                           "it is Unassigned until it is scanned somewhere (FCC has no record of where it "
                           "sat before that slot)."), "WARNING")
                    continue
                if _norm_slot(existing.get('slot', '')) == seat_slot and existing['id'] != int(sid):
                    state.logger.info(f"🪑 Unseating Spool {existing['id']} from Slot {target_slot}")
                    # Load the existing spool's full extra and MERGE — Spoolman's
                    # PATCH replaces the entire `extra` object, so passing only
                    # {container_slot: ''} would wipe physical_source, spool_type,
                    # temps, etc. Read → clear just the slot → write whole extra.
                    _existing_full = spoolman_api.get_spool(existing['id']) or {}
                    _merged_extra = dict(_existing_full.get('extra') or {})
                    _merged_extra['container_slot'] = ''
                    if not spoolman_api.update_spool(existing['id'], {'extra': _merged_extra}):
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to unseat Spool #{existing['id']} from slot: {err}",
                            "ERROR", "ff4444"
                        )
                        unseat_failed = f"couldn't unseat #{existing['id']} from slot {target_slot}: {err}"
                        break
            if unseat_failed:
                failures[str(sid)] = unseat_failed
                state.add_log_entry(
                    f"❌ Not moving Spool #{sid} into {target} slot {target_slot}: {unseat_failed}",
                    "ERROR", "ff4444")
                continue

        # Moving to a non-slotted location clears the slot.
        new_extra['container_slot'] = str(seat_slot) if seat_slot else ""

        # Group 42.6 + Swap option C: the "before the box" note. Into a box (a
        # single-slot box, or a multi-slot box's slot) it records where the spool
        # sat; onto a head from a plain place, that place; a deploy, a Return to
        # its own slot, head to head or a re-scan carries it; any other move
        # uses it up (_note_after_move).
        follow_box = None
        _new_note = _note_after_move(current_loc, current_extra, target, seat_slot, tgt_info,
                                     bool(is_printer or is_toolhead), printer_map, loc_info_map)
        if _new_note is not None:
            new_extra[PRE_BOX_KEY] = _new_note

        # Step 4's rule (Derek, 2026-10-20): an archived spool with filament on its
        # record is un-archived by the PATCH that puts it on the head, whichever
        # branch writes it (the PRINTER branch, or the GENERIC one for a Tool Head
        # row no printer's toolheads[] lists: 2026-10-20 review, engine-3). Its
        # pre-archive note is used up once it is back in stock (Claude's call 22);
        # "" because the extras merge keeps an omitted key.
        _unarchive = str(sid) in unarchive_on_load
        if _unarchive:
            new_extra['fcc_pre_archive_location'] = ''

        def _note_unarchived():
            _left = unarchive_on_load[str(sid)]
            unarchived.append({"id": sid, "left_g": round(_left, 1), "head": target})
            state.add_log_entry(
                f"📤 #{sid} was archived with {_left:.0f} g left on its record: FCC un-archived it to "
                f"load it onto {target}. Weigh it if that's off.", "WARNING", "ffaa00")

        # PRINTER MOVE
        if target in printer_map:
            # Preserve ghost trail when the spool is already deployed to
            # this exact toolhead. Without this guard, re-scanning a spool
            # that's already on the toolhead would set physical_source to
            # the toolhead itself — physical_source == location means "not
            # a ghost," so the deployed indicator disappears and Return-
            # to-Slot loses its home. Only overwrite physical_source when
            # the spool is genuinely arriving from somewhere else.
            existing_source = str(current_extra.get('physical_source', '') or '').strip().strip('"')
            is_already_here = (current_loc == target) and bool(existing_source)
            _recorded_here = None   # the feed slot 13.6 records (40.0d), reported once written
            # Group 42.6 (Derek's Q-A, 2026-09-18): head to head, a spool from a
            # single-slot box keeps that box as its home and the box follows it
            # (attached to the new head below, once the old head has let go).
            # Every other head-sourced trail is still dropped (_ghost_trail_from).
            # Only from the head that box is attached to (Group 42 review): a
            # trail can name a PolyDryer running another spool on another head
            # (the pre-step-5 13.6 reverse-binding wrote such trails), and
            # following it took that box off its own spool's head.
            _old_src = existing_source.upper()
            _old_row = loc_info_map.get(_old_src)
            _follows = (not is_already_here and current_loc in printer_map and _old_src
                        and locations_db._is_single_slot_dryer_box(_old_row)
                        and str(locations_db.bindings_from_row(_old_row).get('1') or '').strip().upper()
                        == current_loc)
            if is_already_here:
                new_extra['physical_source'] = existing_source
                new_extra['physical_source_slot'] = current_extra.get('physical_source_slot')
            elif _follows:
                follow_box = _old_src
                new_extra['physical_source'] = _old_src
                new_extra['physical_source_slot'] = str(current_extra.get('physical_source_slot') or '').strip('"') or '1'
            else:
                new_extra['physical_source'], new_extra['physical_source_slot'] = \
                    _ghost_trail_from(current_loc, current_extra, printer_map, loc_info_map)

            # 13.6 Part A — if the destination toolhead is the value of some
            # dryer-box slot's `extra.slot_targets`, treat the spool as if
            # it came from that slot so the box card lists it as a ghost in
            # the bound slot (mirrors the slot→toolhead auto-deploy chain's
            # forward direction). Only kicks in when there's no genuine
            # source already (UNASSIGNED, buffer, room, etc.) — preserving
            # the existing physical_source when the spool actually came
            # from somewhere meaningful.
            current_source_meaningful = bool(
                str(new_extra.get('physical_source') or '').strip().strip('"')
            )
            if current_source_meaningful and record_source is not None:
                # Group 40.5: the spool arrives from somewhere (its trail), which
                # wins over a "came from" answer; the answer says so.
                record_ignored = True
                record_kept = str(new_extra.get('physical_source') or '').strip().strip('"').upper()
                state.logger.info(f"🔗 #{sid} -> {target}: kept its trail "
                                  f"{new_extra.get('physical_source')}; the named source was not used")
            elif record_source == '':
                # Group 40.5 (D3): "No box", the user's answer in the Printer picker.
                state.logger.info(f"🔗 #{sid} -> {target}: no box slot recorded (the user's choice)")
            elif record_named:
                # Group 40.5 (D3): the slot the user named, checked at step 4 and
                # again here (the printer probe can take seconds): a slot another
                # spool took meanwhile is not recorded, never a double claim.
                _r_box, _r_slot = record_named
                try:
                    _r_now = spoolman_api.get_spools_at_location_detailed_strict(_r_box) or []
                    _r_claims, _o, _g = box_slot_claims(loc_info_map.get(_r_box), _r_box, _r_now, [sid])
                    _r_free = _r_slot not in _r_claims
                except Exception as _r_err:
                    state.logger.warning(f"🔗 couldn't re-read {_r_box} for #{sid}'s source: {_r_err}")
                    _r_free = False
                if _r_free:
                    new_extra['physical_source'] = _r_box
                    new_extra['physical_source_slot'] = _r_slot
                    _recorded_here = f"{_r_box}:{_r_slot}"
                    state.logger.info(f"🔗 #{sid} -> {target}: recorded as from {_r_box} slot {_r_slot} "
                                      f"(the user's choice)")
                else:
                    state.add_log_entry(
                        f"⚠️ #{sid} -> {target}: not recorded as from {_r_box} slot {_r_slot}, which another "
                        f"spool took meanwhile (or couldn't be read): no box slot recorded", "WARNING", "ffaa00")
            elif not current_source_meaningful:
                # Group 40.0d (Derek's D3 rule, "one is pre-selected only when
                # exactly one free option exists"): record a feed slot only when
                # exactly ONE free slot feeds this head. The first match in
                # locations.json order used to win, a guess when two were free.
                # Never a slot another spool holds, directly or as its own ghost:
                # the double claim made a later Return unseat that spool
                # (2026-09-12 review). No trail beats a false one. The recorded
                # slot is reported (`recorded_source`) so the scan toast names it.
                _free, _why_none = _free_feed_slots(target, loc_list, sid)
                if len(_free) == 1:
                    bound_box, bound_slot = _free[0]
                    new_extra['physical_source'] = bound_box
                    new_extra['physical_source_slot'] = bound_slot
                    _recorded_here = f"{bound_box}:{bound_slot}"
                    state.logger.info(
                        f"🔗 Reverse-binding: toolhead {target} is fed by "
                        f"{bound_box} slot {bound_slot} — synthesizing ghost source."
                    )
                elif len(_free) > 1:
                    state.logger.info(
                        f"🔗 Reverse-binding: not guessing where #{sid} came from — "
                        f"{_and_list([f'{b} slot {s}' for b, s in _free])} "
                        f"{'both' if len(_free) == 2 else 'all'} feed {target}."
                    )
                elif _why_none:
                    state.logger.info(f"🔗 Reverse-binding skipped for #{sid}: {_why_none}.")

            if _move_write(sid, target, new_extra, unarchive=_unarchive):
                state.add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
                if _unarchive:
                    _note_unarchived()
                if _recorded_here:
                    recorded_sources[str(sid)] = _recorded_here
                # Group 20.2: a spool deployed FROM a single-slot dryer box
                # attaches that box to this toolhead so the box follows its
                # spool (Core One "missing box" aid). current_loc is where the
                # spool lived before this move. Best-effort — never fail the move.
                try:
                    _att, _ad = locations_db.attach_single_slot_box_to_toolhead(current_loc, target)
                    if _att and _ad != "already attached":
                        state.add_log_entry(f"🔗 Single-slot box auto-attached → {target} ({_ad})", "INFO")
                except Exception as _ae:
                    state.logger.warning(f"20.2 box auto-attach skipped: {_ae}")
            else:
                # Surface Spoolman rejection so slot-assignment failures are
                # visible. Pre-fix, Spoolman 400s here left the slot stuck
                # with no user-visible signal — a class of bug behind the
                # 2026-04-27 outage (Item 2 in Feature-Buglist).
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                failures[str(sid)] = err
                state.add_log_entry(
                    f"❌ Failed to slot Spool #{sid} -> {target}: {err}", "ERROR", "ff4444"
                )

        # DRYER MOVE
        elif target in loc_info_map and loc_info_map[target].get('Type') == 'Dryer Box':
            # Written as "", never pop()ed: update_spool read-merge-writes extras,
            # so an OMITTED key keeps its old value and the stale trail survived
            # (2026-09-12). The delete sentinel can't help either: the merge
            # refuses it for SYSTEM_MANAGED_EXTRAS.
            new_extra['physical_source'] = ""
            # [ALEX FIX] Clean up the source slot memory too, since we are home now.
            new_extra['physical_source_slot'] = ""

            if _move_write(sid, target, new_extra):
                slot_txt = f" [Slot {seat_slot}]" if seat_slot else ""
                state.add_log_entry(f"📦 {info['text']} -> Dryer {target}{slot_txt}", "INFO", info['color'])
            else:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                failures[str(sid)] = err
                state.add_log_entry(
                    f"❌ Failed to move Spool #{sid} -> Dryer {target}: {err}", "ERROR", "ff4444"
                )

        # GENERIC MOVE
        else:
            # [Universal Fallback Ghost Logic]
            if is_toolhead:
                new_extra['physical_source'], new_extra['physical_source_slot'] = \
                    _ghost_trail_from(current_loc, current_extra, printer_map, loc_info_map)
            else:
                # L130 fix: when forcing a spool to a Room/Cart/Shelf
                # (the typical Force-Location destinations), clear any
                # stale ghost trail so the "deployed" indicator computed
                # from physical_source (spoolman_api.search_inventory)
                # doesn't keep flagging the spool as still on a toolhead.
                # Mirrors the DRYER MOVE branch above: written as "", since a
                # pop()ed key is kept by update_spool's merge.
                new_extra['physical_source'] = ""
                new_extra['physical_source_slot'] = ""

            if _move_write(sid, target, new_extra, unarchive=_unarchive):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])
                if _unarchive:
                    _note_unarchived()
            else:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                failures[str(sid)] = err
                state.add_log_entry(
                    f"❌ Failed to move Spool #{sid} -> {target}: {err}", "ERROR", "ff4444"
                )

        # Group 42.1 (step 6 of the pre-write contract): a spool that left a head
        # releases its own single-slot box, whichever branch wrote it. Smart
        # Load's residents are released inside their own eject, never here.
        if str(sid) not in failures and current_loc != target and current_loc in printer_map:
            _released = _release_single_slot_box(sid, current_loc, current_extra, printer_map)
            if _released:
                undo_record['released'][str(sid)] = _released
            # Group 42.6: head to head, the box follows its spool to the new head,
            # once the old head has really let go of it (Group 42 review).
            if follow_box and _released == follow_box:
                try:
                    _att, _ad = locations_db.attach_single_slot_box_to_toolhead(follow_box, target, steal=False)
                    if _att and _ad != "already attached":
                        state.add_log_entry(f"🔗 {follow_box} follows its spool #{sid} to {target}", "INFO")
                except Exception as _fe:
                    state.logger.warning(f"42.6 box follow skipped: {_fe}")

    # Group 41.4: record only what landed. A spool whose write was rejected, or
    # that was skipped (an unseat that failed, an unreadable slot), never moved,
    # so "undoing" it would move it from where it is to where it already is.
    # A move where nothing landed pushes no record at all.
    for _sid in [s for s in list(undo_record['moves']) if str(s) in failures]:
        for _key in ('moves', 'extras', 'labels'):
            undo_record[_key].pop(_sid, None)
    if displaced_out:
        # Swap option C: the stored spools a Swap took out are in the user's
        # hand, so they join the scan buffer (behind the spools waiting there)
        # whether or not the incoming spool's own write then landed; their slot
        # is empty either way, and Undo puts them back in it.
        _d_items, _d_added = _put_in_buffer([d for d, _t in displaced_out],
                                            filed={str(d): t for d, t in displaced_out})
        to_buffer = to_buffer + _d_items
        undo_record['buffered'] = list(undo_record.get('buffered') or []) + list(_d_added)
    if undo_record['moves'] or undo_record['ejections'] or undo_record['displaced']:
        _push_undo(undo_record)

    # --- AUTO-DEPLOY CHAIN ---
    # If this move placed spool(s) into a Dryer Box slot that's bound to a
    # toolhead (extra.slot_targets[slot]), chain a second move so the spool
    # ends up ghost-deployed onto the toolhead. Previously this logic
    # lived only in api_identify_scan's assignment branch, so only scans
    # triggered it; callers like /api/manage_contents action='add' (assign
    # from buffer, deposit cards, etc.) silently skipped it. Centralizing
    # here gives every caller the same behavior for free.
    #
    # auto_deploy=False on the chained call prevents infinite recursion
    # (the toolhead move would try to auto-deploy onto its own printer).
    #
    # 2026-09-12: the chain is judged by what it actually did. It used to drop
    # the caller's confirm_active_print, so a confirmed move into a printing
    # head's bound slot bounced off the guard, and then it logged
    # "Auto-deployed" and reported auto_deployed_to for every spool whenever it
    # returned anything at all. Only spools whose box write landed are deployed;
    # anything not deployed is logged as a warning and reported in
    # auto_deploy_skipped.
    auto_deployed: typing.List[typing.Any] = []
    auto_deploy_skipped: typing.Dict[str, str] = {}
    # The head step 5 asked about (`bound_th`, read through _slot_binding):
    # PRINTER:<id> sentinels declare "this slot is staged for the named
    # printer's pool", so no toolhead is implied and auto-deploy is a no-op.
    # Group 40.3 (review tests:non-head-binding-chain-unpinned): only a real
    # head is loaded. A slot bound to something that isn't one (a deleted head,
    # a printer row, a hand edit) chained the spool OUT of the box to it and
    # reported "Auto-deployed → XL-9"; it now stays in its slot, and the answer
    # says why.
    bound_toolhead = bound_th if loads_head else None
    if bound_th and not loads_head:
        for sid in [s for s in spools if str(s) not in failures][-1:]:
            auto_deploy_skipped[str(sid)] = (
                f"{target} slot {target_slot} is bound to {bound_th}, which isn't a toolhead — "
                f"fix it in {target}'s 🔗 Slot → Toolhead Feeds")
            state.add_log_entry(
                f"⚠️ Spool #{sid} is in <b>{target}:SLOT:{target_slot}</b> but was NOT deployed → "
                f"<b>{bound_th}</b>: {auto_deploy_skipped[str(sid)]}", "WARNING", "ffaa00")
    if bound_toolhead:
        th = str(bound_toolhead).upper()
        placed = [sid for sid in spools if str(sid) not in failures]
        # One slot feeds one toolhead. Several spools sent to the same slot each
        # unseated the one before, so only the last is still in it.
        for sid in placed[:-1]:
            auto_deploy_skipped[str(sid)] = f"only the last spool placed in slot {target_slot} feeds {th}"
        to_deploy = placed[-1:]
        if to_deploy:
            chain_origin = f'auto_deploy_from_{origin or "smart_move"}'
            outer_sink = getattr(_chain_undo_sink, 'records', None)
            _chain_undo_sink.records = []
            try:
                chained = perform_smart_move(
                    th, to_deploy,
                    target_slot=None, origin=chain_origin,
                    auto_deploy=False,
                    # Scoped confirms pass through as-is (Group 39.1). Every
                    # chained slot is one step 5 asked about: since 40.0e an
                    # auto-picked slot is chosen at step 3, before the question,
                    # so the caller's confirm covers the chain.
                    confirm_active_print=confirm_active_print,
                    # Passed through for the chain's own guard; defensive while
                    # fed_check_from is None for a blanket-covered head. Never
                    # expected_feed: the target is a head, and the outer move
                    # checked the feed before any write (Group 40.3).
                    confirmed_fed_heads=confirmed_fed_heads,
                    fed_check_from=(target, target_slot, fed_seen) if fed_seen is not None else None,
                    # The slot whose own spool, if it runs on the head, comes off
                    # into the scan buffer (the same-slot swap; Derek, 2026-10-15).
                    swap_slot=(target, target_slot),
                    # A caller that keeps the spool archived keeps it so on the head
                    # the slot loads too (step 4 refuses it there).
                    keep_archived=keep_archived,
                )
            except Exception as _ad_err:
                state.logger.error(f"Auto-deploy failed for {target}:SLOT:{target_slot}: {_ad_err}")
                chained = {"status": "error", "msg": f"auto-deploy crashed: {_ad_err}"}
            finally:
                chained_undos = _chain_undo_sink.records or []
                _chain_undo_sink.records = outer_sink
            if not isinstance(chained, dict):
                chained = {"status": "error", "msg": "auto-deploy returned nothing"}
            # One user action, one undo: fold the record(s) the chained move
            # pushed (and any resident its Smart Load unloaded) into this move's
            # record, which already restores the spool to where it started.
            # Matched by identity, never by stack position: another request can
            # push a record with the same origin meanwhile (2026-09-12 review).
            for chained_undo in chained_undos:
                idx = next((i for i in range(len(state.UNDO_STACK) - 1, -1, -1)
                            if state.UNDO_STACK[i] is chained_undo), None)
                if idx is None:
                    continue  # already undone
                del state.UNDO_STACK[idx]
                undo_record['ejections'].update(chained_undo.get('ejections') or {})
                undo_record['ejection_extras'].update(chained_undo.get('ejection_extras') or {})
                undo_record['ejection_released'].update(chained_undo.get('ejection_released') or {})
                if chained_undo.get('buffered'):
                    undo_record['buffered'] = list(undo_record.get('buffered') or []) + list(chained_undo['buffered'])
            # The slot's own spool the chain swapped out into the scan buffer.
            to_buffer = to_buffer + [i for i in (chained.get('to_buffer') or []) if isinstance(i, dict)]
            # An archived spool the chained load un-archived (step 4's rule).
            unarchived = unarchived + [u for u in (chained.get('unarchived') or []) if isinstance(u, dict)]
            chained_failures = chained.get('failures') or {}
            for sid in to_deploy:
                if chained.get('status') == 'success' and str(sid) not in chained_failures:
                    auto_deployed.append(sid)
                    state.add_log_entry(
                        f"⚡ Auto-deployed Spool #{sid}{_spool_brand_color_suffix(sid)} → <b>{th}</b> "
                        f"(source: {target}:SLOT:{target_slot})",
                        "SUCCESS", "00ff00"
                    )
                else:
                    auto_deploy_skipped[str(sid)] = (
                        chained_failures.get(str(sid)) or chained.get('msg') or "not deployed")
        for sid, why in auto_deploy_skipped.items():
            state.add_log_entry(
                f"⚠️ Spool #{sid} is in <b>{target}:SLOT:{target_slot}</b> but was NOT "
                f"deployed → <b>{th}</b>: {why}",
                "WARNING", "ffaa00"
            )

    result: typing.Dict[str, typing.Any] = {
        "status": "success",
        # sid(str) -> the Spoolman error body captured NEXT TO the write that
        # failed. Empty on a fully-clean move. Additive: existing callers read
        # only `status` (a bare success even when some writes were rejected —
        # this is what lets a batch caller do better).
        "failures": failures,
    }
    _step6_why = {step6_refused.get(str(s)) for s in spools}
    if len(_step6_why) == 1 and None not in _step6_why:
        # Groups 51.3 / 51.7: every spool was refused over what the slot holds.
        result["blocked_reason"] = _step6_why.pop()
    if recorded_sources:
        # Group 40.0d: the feed slot the reverse-binding recorded as the spool's
        # home ("LR-MDB-1:1"), so the scan toast can name it. A head takes one
        # spool (42.3a), so one value.
        result["recorded_source"] = next(iter(recorded_sources.values()))
    if record_ignored:
        # Group 40.5: the spool arrived with its own trail, which was kept.
        result["record_source_ignored"] = True
        if record_kept:
            result["record_source_kept"] = record_kept
    if auto_deployed:
        result["auto_deployed_to"] = str(bound_toolhead).upper()
    if to_buffer:
        # Group 40, the same-slot swap: the spools taken off a head into the scan
        # buffer (Unassigned in Spoolman). The page adds them to its buffer.
        result["to_buffer"] = to_buffer
    if unarchived:
        # Step 4's rule (Derek, 2026-10-20): the archived spools this move (or its
        # chained deploy) un-archived to load them, [{id, left_g, head}]; every
        # door warns about them (window.noteUnarchived).
        result["unarchived"] = unarchived
    if auto_deploy_skipped:
        # sid(str) -> why it stayed in the box. The box placement itself stands.
        result["auto_deploy_skipped"] = auto_deploy_skipped
        result["auto_deploy_target"] = str(bound_toolhead or bound_th).upper()
    return result


# ---------------------------------------------------------------------------
# L298 Bulk Moves — the shared plan/execute core (Phase 1 endpoint + Phase 2
# scan session both call these, so the two entries can never drift apart).
# ---------------------------------------------------------------------------

BULK_MOVE_SINGLE_OCC_MSG = ("{dest} is a single-spool location — bulk move needs a "
                            "Room / Shelf / Cart / Dryer Box destination.")
# Group 40 item H (Claude's call 27, g40-q8): a Printer row that is not itself a
# head (XL, RCOI) stays refused, in printer words.
BULK_MOVE_PRINTER_ROW_MSG = ("{dest} is a printer, not a toolhead — bulk move needs a "
                             "Room / Shelf / Cart / Dryer Box destination.")


def can_start_bulk_move():
    """(ok, msg) — may a NEW bulk-move session start right now?

    Audit and bulk move are mutually exclusive scan modes sharing CMD:DONE /
    CMD:CANCEL, and api_identify_scan checks the AUDIT gate FIRST. So a bulk
    session armed during an audit is unreachable by any scan: every location
    scan is swallowed by the audit while the bulk panel still says "scan the
    SOURCE". Refuse up front instead of creating that stuck state.
    """
    if state.AUDIT_SESSION.get('active'):
        return False, ("An audit is in progress — finish or cancel it before "
                       "starting a bulk move.")
    return True, ""


def plan_bulk_move(source, dest):
    """DRY-RUN a bulk move: resolve the source fail-closed, decide who is
    movable, and run every pre-flight — WITHOUT writing anything.

    Returns a plan dict:
      {ok, msg, blocked_reason, source, dest, movable_ids, skipped:[{id,reason}]}

    `ok=False` means a guard blocked the whole batch (`blocked_reason` is the
    machine-readable cause). `ok=True` with an empty `movable_ids` is the benign
    "nothing to move" case.

    Group 41.7 (Q3 A, 2026-10-13): there is no "source is printing" confirm. A
    bulk move never moves a loaded spool: every head-loaded or deployed spool is
    a skip, so a printing source always ended as a skip or "Nothing to move"
    and the confirm could never fire on real data (it was only ever tested with
    a fake printing dryer box). Taking a spool off a printing head is a single
    move, which asks under D6.

    Shared by `/api/bulk_move` (Phase 1) and the CMD:BULKMOVE session preview
    (Phase 2) so the preview a user confirms is computed by the SAME code that
    guards the commit — a preview that can't disagree with the commit.
    """
    source = str(source or '').strip().upper()
    dest = str(dest or '').strip().upper()
    plan = {"ok": False, "msg": "", "blocked_reason": None, "source": source, "dest": dest,
            "movable_ids": [], "skipped": [], "source_feeds": [],
            # Phase 3 display-only fields (see the skip loop): `rows` is the
            # id -> {display,color,color_direction,slot,remaining_weight} cache
            # the panel renders from, `would_move_ids` the movable set even when
            # a guard blocks the batch. Seeded here so an EARLY block (same /
            # descendant / unknown dest / single-occupancy / unreadable source)
            # still returns the full key set.
            "rows": {}, "would_move_ids": []}

    if not source or not dest:
        plan["msg"] = "Both source and dest are required."
        plan["blocked_reason"] = "missing_args"
        return plan

    loc_list = locations_db.load_locations_list()
    loc_info_map = {str(r.get('LocationID', '')).upper(): r for r in loc_list}
    printer_map = locations_db.get_active_printer_map(loc_list)

    # --- Pre-flight 1: self / descendant (cheap topology reject) ------------
    # Moving a child's contents UP to an ancestor is legitimate; moving a
    # location into its own descendant is paradoxical (and on the flat
    # enumeration would re-sweep the just-moved spools).
    if dest == source:
        plan["msg"] = "Source and destination are the same location."
        plan["blocked_reason"] = "same"
        return plan
    if locations_db.is_descendant(dest, source, loc_list=loc_list):
        plan["msg"] = f"{dest} is inside {source} — can't bulk-move a location into its own descendant."
        plan["blocked_reason"] = "descendant"
        return plan

    # --- Pre-flight 2a: destination must be a KNOWN location ----------------
    # Symmetric with the fail-closed source resolve: the source can't silently
    # look empty, and the dest can't silently be nowhere. An unknown/stale/typo'd
    # dest would sail past the remaining guards (no row → not single-occ, Max
    # Spools 0 → no cap) and perform_smart_move's GENERIC branch would write that
    # string as a location verbatim to EVERY movable spool, orphaning them.
    dest_row = loc_info_map.get(dest)
    if dest_row is None:
        plan["msg"] = f"{dest} is not a known location — nothing moved."
        plan["blocked_reason"] = "unknown_dest"
        return plan

    # --- Pre-flight 2b: single-occupancy destination ------------------------
    # A head holds ONE spool; a bulk move onto it would chain-unseat every spool
    # but the last. A Printer row that is not itself a head takes no spool at all
    # (Group 40.0a), so it is refused in printer words (item H). One-spool is the
    # engine's rule (_holds_one_spool): a head, or a printer that is its own head.
    if locations_db.is_printer_row_not_head(dest, dest_row, printer_map):
        plan["msg"] = BULK_MOVE_PRINTER_ROW_MSG.format(dest=dest)
        plan["blocked_reason"] = "printer_row"
        return plan
    if _holds_one_spool(dest, printer_map, loc_info_map):
        plan["msg"] = BULK_MOVE_SINGLE_OCC_MSG.format(dest=dest)
        plan["blocked_reason"] = "single_occupancy"
        return plan

    # --- Resolve source, FAIL-CLOSED ----------------------------------------
    # A transient Spoolman outage must NOT make the source look empty (a silent
    # no-op that "succeeds" moving nothing). The _strict reader RAISES; we bail.
    try:
        contents = spoolman_api.get_spools_at_location_detailed_strict(source)
    except Exception as e:
        state.logger.error(f"bulk_move: source resolve failed for {source}: {e}")
        plan["msg"] = f"Could not read {source} from Spoolman — nothing moved."
        plan["blocked_reason"] = "source_unreadable"
        return plan

    # --- Skip rules (mirror clear_location; report as "left in place") ------
    buffer_ids = set()
    for b in (getattr(state, 'GLOBAL_BUFFER', None) or []):
        if isinstance(b, dict):
            try:
                buffer_ids.add(int(b.get('id') or 0))
            except (TypeError, ValueError):
                pass
    movable_ids = []
    skipped = []
    # L298 Phase 3 — carry the DISPLAY fields we already have. Every `contents`
    # row from _build_location_match already holds display/color/color_direction/
    # slot/remaining_weight; the plan used to discard all of it and keep only ids,
    # forcing bulk_move_session_snapshot to re-issue one GET /api/v1/spool/<id>
    # per row on EVERY 2s panel poll (an unbounded N+1 fan-out — the L3 slot-
    # assign latency class). Stashing it here makes the snapshot pure formatting
    # with zero Spoolman I/O. Display-only: nothing in the commit path reads it.
    rows = {}
    for sp in contents:
        sid = sp.get('id')
        rows[str(sid)] = {
            "display": sp.get('display') or f"#{sid}",
            "color": sp.get('color') or "888888",
            "color_direction": sp.get('color_direction') or "longitudinal",
            "slot": sp.get('slot'),
            "remaining_weight": sp.get('remaining_weight'),
        }
        if sp.get('is_ghost'):
            skipped.append({"id": sid, "reason": "deployed to a live toolhead"})
            continue
        if sp.get('archived'):
            skipped.append({"id": sid, "reason": "archived"})
            continue
        try:
            if int(sid or 0) in buffer_ids:
                skipped.append({"id": sid, "reason": "in the scan buffer"})
                continue
        except (TypeError, ValueError):
            pass
        # D2 flat-scope guard: a PRINTER source enumerates its toolhead spools as
        # DIRECT matches (their first segment IS the printer). Those are live
        # single-occupancy feeds — never yank them in a bulk sweep. A spool filed
        # on a multi-head Printer row itself is not loaded anywhere, so it moves
        # (Group 40 item H): Bulk Move can clean up what 40.0a now prevents.
        sp_loc = str(sp.get('location', '') or '').strip().upper()
        if _holds_one_spool(sp_loc, printer_map, loc_info_map):
            skipped.append({"id": sid, "reason": "loaded in a toolhead slot"})
            continue
        movable_ids.append(sid)

    plan["skipped"] = skipped
    plan["rows"] = rows
    # DISPLAY-ONLY twin of movable_ids. `movable_ids` stays empty on a BLOCKED
    # plan so execute_bulk_move can never act on one; `would_move_ids` survives
    # the block so the panel can still show the user WHICH spools the capacity
    # guard refused ("2 free of 4, source has 5" is far more actionable next to
    # the five tiles). Never read by the commit path.
    plan["would_move_ids"] = list(movable_ids)
    if not movable_ids:
        plan["ok"] = True
        plan["msg"] = f"Nothing to move from {source} ({len(skipped)} left in place)."
        return plan

    # --- Pre-flight 3: capacity (D3) — HARD BLOCK before any confirm --------
    # Bounded destinations (Dryer Box, Max Spools > 0): BLOCK the whole batch if
    # the movable count exceeds free capacity. Unbounded (Room/Shelf/Cart, Max
    # Spools 0/blank) = no cap. Occupancy counts every current occupant (direct +
    # ghost home) so a deployed spool still reserves its slot. Fail-closed too:
    # an unverifiable capacity blocks rather than risking an overflow. Ordered
    # before the active-print confirm so we never prompt only to then refuse.
    try:
        max_spools = int(str(dest_row.get('Max Spools', '0')).strip() or '0')
    except (TypeError, ValueError):
        max_spools = 0
    if max_spools > 0:
        try:
            occupancy = len(spoolman_api.get_spools_at_location_detailed_strict(dest) or [])
        except Exception as e:
            state.logger.error(f"bulk_move: dest capacity read failed for {dest}: {e}")
            plan["msg"] = f"Could not verify {dest} capacity from Spoolman — nothing moved."
            plan["blocked_reason"] = "dest_unreadable"
            return plan
        free = max_spools - occupancy
        if len(movable_ids) > free:
            plan["msg"] = (f"{dest} has {max(free, 0)} free of {max_spools}; source has "
                           f"{len(movable_ids)} to move — nothing moved.")
            plan["blocked_reason"] = "capacity"
            return plan

    plan["ok"] = True
    plan["movable_ids"] = movable_ids
    # Informational only — never blocks, never mutates the bindings. Set ONLY on
    # the committable exits: a BLOCKED plan moves nothing, so advertising feeds
    # it would have emptied is a warning about something that cannot happen.
    plan["source_feeds"] = _bound_feeds_for_move(contents, movable_ids, loc_info_map)
    return plan


def _slot_targets_for(loc_id, loc_info_map):
    """extra.slot_targets for a location, defensively. {} when absent/malformed.

    Owns only the id->row LOOKUP; the extraction itself delegates to the
    canonical `locations_db.bindings_from_row` so the two can't drift again.
    (They already had: this one guarded a non-dict `extra` and the shared one
    didn't, while the shared one normalized values and this one didn't. The
    guard moved into the shared helper; the normalization is harmless here —
    JSON object keys are always strings, and the sole consumer
    `_bound_feeds_for_move` collapses '' and None identically via
    `str(target or '')`.)
    """
    row = loc_info_map.get(str(loc_id or '').strip().upper()) or {}
    return locations_db.bindings_from_row(row)


def _bound_feeds_for_move(contents, movable_ids, loc_info_map):
    """Toolheads THIS MOVE would leave without a spool, via extra.slot_targets.

    Emptying a bound Dryer Box is legitimate and the bindings are deliberately
    LEFT ALONE — `slot_targets` describes the plumbing (slot 1 feeds XL-1), not
    the contents, so a move that emptied the box does not invalidate it, and
    silently clearing a user's slot→toolhead wiring as a side-effect of a move
    would be exactly the kind of hidden mutation this feature must not do.
    (The plan's original risk note said "flag/clear"; clearing is wrong.)
    So: INFORM, never mutate.

    Keyed off each moving spool's OWN location, NOT the source row. The source
    resolve is flat/first-segment, so a Room source sweeps every bound box whose
    id shares its prefix — reading only the source's own slot_targets meant a
    Room-level move emptied real printer feeds with no warning at all.

    Only reports a feed whose slot is actually occupied by a spool that WILL
    move: a box with 4 bound slots and 1 spool must not claim four feeds are
    about to run dry, and a slot whose spool is SKIPPED (a ghost already deployed
    to that very toolhead, an archived spool) keeps its feed.
    """
    movable = {str(m) for m in (movable_ids or [])}
    feeds = set()
    for sp in (contents or []):
        if str(sp.get('id')) not in movable:
            continue
        loc = str(sp.get('location', '') or '').strip().upper()
        targets = _slot_targets_for(loc, loc_info_map)
        if not targets:
            continue
        # A SINGLE-slot box used to record no container_slot (Group 20.2 auto-binds
        # exactly this class), so treating blank as "no slot" made the warning
        # permanently dead for the boxes most likely to feed a toolhead. Group
        # 42.2's one rule: its lone spool IS in slot 1 (locations_db.effective_slot).
        occupants = sum(1 for o in (contents or [])
                        if not o.get('is_ghost')
                        and str(o.get('location', '') or '').strip().upper() == loc)
        slot = locations_db.effective_slot(loc_info_map.get(loc), sp.get('slot'), occupants=occupants)
        if not slot:
            continue
        target = targets.get(slot) or targets.get(str(slot))
        t = str(target or '').strip().upper()
        # PRINTER:<id> sentinels stage a pool for a printer; no toolhead implied.
        if t and not locations_db.is_printer_sentinel(t):
            feeds.add(t)
    return sorted(feeds)


def execute_bulk_move(plan):
    """Commit an OK plan: ONE perform_smart_move + an honest per-spool tally.

    Returns {success, source, dest, moved, moved_ids, skipped, failed} — or a
    requires_confirm / error passthrough if the engine bails. NEVER hand-rolls a
    spool write (CLAUDE.md "Spool / Filament write surfaces"); the engine owns
    the read-merge-write + the single undo record.
    """
    source, dest = plan["source"], plan["dest"]
    movable_ids = list(plan["movable_ids"])
    skipped = plan["skipped"]

    # auto_deploy=False: a bulk move RELOCATES/parks a set of spools; it must NOT
    # chain-deploy a spool from a bound dryer-box slot onto a live toolhead the
    # way a deliberate single scan does. Confirmed by Derek 2026-07-11 —
    # auto-assigning filament to toolheads mid-bulk "would just make a mess",
    # especially when the source holds more than the destination can take.
    #
    # confirm_active_print=True (Group 39 review, engine-3): plan_bulk_move has
    # just re-planned from live state, skipping every head-loaded spool and
    # refusing a printer-head destination. So the engine's per-spool source
    # reads (39.4) have nothing to find, and their fail-closed refusal would
    # turn one Spoolman blip into "nothing moved" plus a reset armed session.
    # The engine therefore never answers requires_confirm here (Group 41.7
    # removed the backstop that relayed one).
    move_result = perform_smart_move(dest, movable_ids, origin='bulk_move',
                                     auto_deploy=False,
                                     confirm_active_print=True)
    if isinstance(move_result, dict) and move_result.get('status') == 'error':
        return {"success": False, "source": source, "dest": dest,
                "msg": move_result.get('msg', 'Move failed.')}

    # --- Honest tally via READBACK ------------------------------------------
    # perform_smart_move returns a bare {status:success} even if some per-spool
    # writes were rejected (it logs each ERROR but doesn't report which). Re-read
    # the source: any movable id STILL present as a DIRECT (non-ghost) match
    # never left — it failed. Best-effort: advisory only; the Activity Log is
    # authoritative for the per-spool outcome (per Derek 2026-07-11).
    # Per-spool attribution from the map perform_smart_move captured ADJACENT to
    # each failing write. Reading the LAST_SPOOLMAN_ERROR module global here
    # instead (the Phase-2 behaviour) was wrong twice over: a later SUCCESS
    # resets it to None, and a second failure overwrites the first — so a mixed
    # batch mislabelled every row. Group 41.5: those failures ALWAYS count. They
    # used to be read only when the readback found a spool still at the source,
    # so a rejected write plus a readback that missed it was tallied as moved.
    per_spool = (move_result or {}).get('failures') or {}
    failed_ids = {str(k) for k in per_spool}
    unverified = False
    try:
        # Group 41.5: strict, so a Spoolman blip reads as "couldn't verify", not
        # as an empty source that "proves" every spool left.
        still = spoolman_api.get_spools_at_location_detailed_strict(source) or []
        still_direct = {str(s.get('id')) for s in still if not s.get('is_ghost')}
        stuck = {str(m) for m in movable_ids} & still_direct
        if stuck:
            # The source readback matches by FLAT first-segment (location_prefix),
            # but the descendant guard uses the parent_id TREE. When a dest's ID
            # prefix collides with the source yet it's reparented elsewhere
            # (Group-34 NO-FORCED-RELABELING), a correctly-moved spool now at dest
            # still flat-matches the source and would be mis-counted as failed.
            # Subtract anything that actually landed at dest before deciding.
            at_dest = {str(s.get('id'))
                       for s in (spoolman_api.get_spools_at_location_detailed_strict(dest) or [])}
            stuck -= at_dest
        failed_ids |= stuck
    except Exception as e:
        unverified = True
        state.logger.warning(f"bulk_move: tally readback failed for {source}: {e}")
    moved_ids = [m for m in movable_ids if str(m) not in failed_ids]
    failed = [{"id": m, "err": per_spool.get(str(m)) or "see Activity Log"}
              for m in movable_ids if str(m) in failed_ids]

    # Per-spool INFO/ERROR lines already came from perform_smart_move; add one
    # aggregate summary line.
    quiet = not failed and not unverified
    level, color = ("SUCCESS", "00ff00") if quiet else ("WARNING", "ffaa00")
    moved_txt = (f"moved {len(moved_ids)} (couldn't verify with Spoolman)" if unverified
                 else f"moved {len(moved_ids)}")
    state.add_log_entry(
        f"🔀 Bulk move {source} → {dest}: {moved_txt}, "
        f"skipped {len(skipped)}, failed {len(failed)}", level, color)

    return {"success": len(failed) == 0, "source": source, "dest": dest,
            "moved": len(moved_ids), "moved_ids": moved_ids,
            "skipped": skipped, "failed": failed, "unverified": unverified}


def start_bulk_move_session(source_id=None):
    """Arm a CMD:BULKMOVE session. With `source_id` (the Location-Manager
    'Move all →' button) the source is pre-seeded and we jump straight to
    awaiting_dest; without it (a CMD:BULKMOVE scan) we await a source scan.

    Callers MUST refuse when a session (or an audit) is already running — see
    can_start_bulk_move; this function unconditionally resets.
    """
    state.reset_bulk_move()
    sess = state.BULK_MOVE_SESSION
    sess['active'] = True
    sess['last_activity_ts'] = time.time()
    # The armed session expires; say so in the log line that arms it, so the
    # Activity Log carries the same expectation the panel sets.
    idle_min = int(state.BULK_MOVE_IDLE_TIMEOUT_SECONDS // 60)
    if source_id:
        sess['source_id'] = str(source_id).strip().upper()
        sess['stage'] = 'awaiting_dest'
        state.add_log_entry(
            f"🔀 <b>BULK MOVE ARMED</b> — source <b>{sess['source_id']}</b>. "
            f"Scan the DESTINATION location. (Clears itself after {idle_min} min idle.)",
            "INFO", "00d4ff")
    else:
        sess['stage'] = 'awaiting_source'
        state.add_log_entry(
            f"🔀 <b>BULK MOVE STARTED</b> — scan the SOURCE location. "
            f"(Clears itself after {idle_min} min idle.)", "INFO", "00d4ff")
    return sess


def _apply_plan_to_session(sess, plan):
    """Store a freshly-computed plan on the session AND set the matching stage.

    The ONE place that decides "does this plan deserve the committable stage?".
    Only a plan that could actually be committed advances to `preview`; a BLOCKED
    dest (single-occupancy / unknown / capacity / unreadable) stays at
    awaiting_dest so the user is still prompted for a valid one. Without that,
    the stage rides the heartbeat and the deck tile goes GREEN "COMMIT" with a
    live CMD:DONE QR for a move that can never run.

    Factored out because commit_bulk_move_session's re-plan wrote sess['preview']
    WITHOUT the stage guard, so a commit that re-blocked (a spool landed in the
    dest between preview and commit, or a transient Spoolman blip) left the tile
    green and advertising a commit that every retry refused.
    """
    sess['preview'] = plan
    sess['stage'] = 'preview' if plan.get('ok') else 'awaiting_dest'
    return plan


def _refresh_bulk_move_preview():
    """(Re)compute the dry-run preview for a session that has both locations."""
    sess = state.BULK_MOVE_SESSION
    plan = plan_bulk_move(sess.get('source_id'), sess.get('dest_id'))
    return _apply_plan_to_session(sess, plan)


def set_bulk_move_dest(dest_id):
    """Set/re-target the destination and recompute the preview. (ok, plan|None, msg).

    Serialized against a running commit for the same reason cancel is: the
    commit reads sess['dest_id'] INSIDE the lock, but the two dest writers (the
    HTTP set_dest and a LOC scan) wrote it with none. So a stray destination
    scan landing between the user's Commit click and the commit thread's read
    RE-TARGETED the batch — spools moved to a location the user never previewed.
    A destructive op must only ever commit the destination that was on screen.

    Non-blocking: a re-target during a commit is REFUSED, not queued (queuing
    would apply it to a session the commit is about to clear anyway).
    """
    dest_id = str(dest_id or '').strip().upper()
    if not dest_id:
        return False, None, "A destination is required."
    if not _BULK_MOVE_COMMIT_LOCK.acquire(False):
        # Same wording family as the cancel refusal: state that a commit is
        # running, without claiming anything about how far along it is.
        return False, None, ("A bulk-move commit is already running — the "
                             "destination can't be changed until it finishes.")
    try:
        state.BULK_MOVE_SESSION['dest_id'] = dest_id
        plan = _refresh_bulk_move_preview()
        return True, plan, plan.get('msg') or ""
    finally:
        _BULK_MOVE_COMMIT_LOCK.release()


def bulk_move_session_snapshot(sess=None):
    """The JSON-safe view of the bulk-move session the frontend polls/renders.

    Returns {active:False} when idle (cheap), else the stage + both locations +
    a flattened preview (counts, the movable/skipped detail, and any block),
    with each row carrying the display label / colour /
    slot / remaining weight the panel renders as a spool tile.

    ⚡ ZERO Spoolman I/O — the panel polls this every 2s, so it formats the rows
    `plan_bulk_move` already captured (`plan['rows']`) instead of re-issuing a
    per-id GET. Phase 2 did the latter: an N+1 fan-out per tick, unbounded in the
    source size and multiplied by every open tab. Keep it I/O-free; a live
    re-read belongs in `_refresh_bulk_move_preview` (which re-plans anyway).
    """
    if sess is None:
        sess = state.BULK_MOVE_SESSION
    if not sess.get('active'):
        return {"active": False, "stage": "idle"}

    out = {
        "active": True,
        "stage": sess.get('stage') or 'idle',
        "source_id": sess.get('source_id'),
        "dest_id": sess.get('dest_id'),
        # Surfaced so the panel can TELL the user the session expires, instead of
        # them walking back to a dead armed move and reading it as a broken app.
        # Derived from the constant, never hard-coded in the UI text, so the
        # notice can't drift from the watchdog that enforces it.
        "idle_timeout_min": int(state.BULK_MOVE_IDLE_TIMEOUT_SECONDS // 60),
    }
    plan = sess.get('preview') or None
    if plan:
        rows = plan.get('rows') or {}

        def _row(sid, reason=None):
            cached = rows.get(str(sid)) or {}
            row = {
                "id": sid,
                "display": cached.get('display') or f"#{sid}",
                "color": cached.get('color') or "888888",
                "color_direction": cached.get('color_direction') or "longitudinal",
                "slot": cached.get('slot'),
                "remaining_weight": cached.get('remaining_weight'),
            }
            if reason:
                row["reason"] = reason
            return row

        # A blocked plan keeps an empty movable_ids (so the commit path can never
        # act on it) but still reports what it REFUSED, via would_move_ids.
        movable_src = plan.get('movable_ids') or plan.get('would_move_ids') or []
        movable = [_row(sid) for sid in movable_src]
        skipped = [_row(s.get('id'), s.get('reason')) for s in (plan.get('skipped') or [])]
        out["preview"] = {
            "ok": bool(plan.get('ok')),
            "msg": plan.get('msg') or "",
            "blocked_reason": plan.get('blocked_reason'),
            "movable": movable,
            "skipped": skipped,
            "source_feeds": plan.get('source_feeds') or [],
            "stats": {"movable": len(movable), "skipped": len(skipped)},
        }
    return out


def process_bulk_move_scan(scan_result):
    """Route a scan into the ACTIVE bulk-move session.

    Contract mirrors process_audit_scan: returns a bare dict; only
    {"status": "error"} is surfaced to the scanner UI, anything else answers
    cmd:'clear'. Scanning a destination NEVER auto-commits — it computes the
    preview and waits for an explicit CMD:DONE / button commit, because a bulk
    move is far too destructive to fire on a stray scan.
    """
    sess = state.BULK_MOVE_SESSION

    # 1. COMMANDS — commit / bail. (CMD:BULKMOVE while active is intercepted
    #    upstream in api_identify_scan, so it never reaches here.)
    if scan_result and scan_result.get('type') == 'command':
        cmd = scan_result.get('cmd')
        if cmd == 'cancel':
            # Routed through the shared primitive so a CMD:CANCEL scan racing an
            # in-flight commit is refused exactly like the HTTP cancel, instead
            # of reporting "nothing moved" over a move that is still running.
            ok, msg = cancel_bulk_move_session()
            return {"status": "success" if ok else "error", "msg": msg}
        if cmd == 'done':
            if sess.get('stage') != 'preview':
                state.add_log_entry(
                    "⚠️ Bulk move: scan a SOURCE and a DESTINATION before committing.",
                    "WARNING", "ffaa00")
                return {"status": "error", "msg": "Scan a source and destination first."}
            result = commit_bulk_move_session()
            if not result.get('success'):
                # A PARTIAL failure returns success=False with a `failed` list and
                # NO `msg` (execute_bulk_move's tally shape), so a `msg`-gated check
                # let it fall through and told the scanner the move succeeded —
                # exactly the "partial-failure reports success" class this feature
                # is meant to avoid. Synthesize a message from the tally.
                msg = result.get('msg')
                if not msg:
                    n_failed = len(result.get('failed') or [])
                    msg = (f"{n_failed} spool(s) failed to move — see the Activity Log."
                           if n_failed else "Bulk move failed.")
                return {"status": "error", "msg": msg}
            if result.get('unverified'):
                # Group 41.5: done, but Spoolman couldn't be read back to check it.
                return {"status": "warning",
                        "msg": (f"Bulk move done: moved {result.get('moved', 0)}, but FCC couldn't "
                                f"verify it with Spoolman. Check the Activity Log.")}
            return {"status": "success", "msg": "Bulk move complete"}
        return {"status": "error", "msg": "Command not allowed during a bulk move."}

    # 2. LOCATION scans — capture source, then dest.
    if scan_result and scan_result.get('type') == 'location':
        loc_id = str(scan_result.get('id') or '').strip().upper()
        if not loc_id:
            return {"status": "error", "msg": "Empty location code."}
        stage = sess.get('stage')
        if stage == 'awaiting_source':
            sess['source_id'] = loc_id
            sess['stage'] = 'awaiting_dest'
            state.add_log_entry(
                f"🔀 Bulk move source: <b>{loc_id}</b>. Now scan the DESTINATION.",
                "INFO", "00d4ff")
            return {"status": "success"}
        if stage in ('awaiting_dest', 'preview'):
            # Re-scanning at the preview stage RE-TARGETS the destination rather
            # than erroring — the user changed their mind before committing.
            # Routed through the shared setter so a scan can't re-target a batch
            # that is already being committed (see set_bulk_move_dest).
            ok, plan, msg = set_bulk_move_dest(loc_id)
            if not ok:
                state.add_log_entry(f"⚠️ Bulk move: {msg}", "WARNING", "ffaa00")
                return {"status": "error", "msg": msg}
            if not plan.get('ok'):
                state.add_log_entry(f"⚠️ Bulk move blocked: {plan.get('msg')}", "WARNING", "ffaa00")
                return {"status": "error", "msg": plan.get('msg')}
            n = len(plan.get('movable_ids') or [])
            k = len(plan.get('skipped') or [])
            state.add_log_entry(
                f"🔀 Bulk move preview: <b>{n}</b> spool(s) {sess.get('source_id')} → "
                f"<b>{loc_id}</b>" + (f", {k} left in place" if k else "") +
                ". Scan CMD:DONE (or press Commit) to move.", "INFO", "00d4ff")
            return {"status": "success"}
        return {"status": "error", "msg": "Bulk move is not awaiting a location."}

    # 3. Anything else (spool / filament / assignment) is not meaningful here.
    return {"status": "error", "msg": "Scan a LOCATION during a bulk move (or CMD:CANCEL)."}


# Serializes commit_bulk_move_session so a double-click / double-scan (or two
# tabs) can't run perform_smart_move twice for the same armed session — the
# second run would move an already-moved batch again AND bury the real undo
# record under a no-op one. Non-blocking acquire: the loser is REFUSED, not
# queued, because queuing would just replay the same batch a moment later.
_BULK_MOVE_COMMIT_LOCK = threading.Lock()

# The lock is held by BOTH commit_bulk_move_session and set_bulk_move_dest (the
# latter to stop a stray dest scan re-targeting a batch mid-commit), so "lock is
# held" does NOT mean "a commit is running" — a cancel arriving during a
# destination re-plan was told a commit was already running when none was.
# This flag says what the lock cannot: writes are actually happening.
_BULK_MOVE_WRITING = False


def cancel_bulk_move_session():
    """Clear the session — UNLESS a commit is mid-flight. Returns (ok, msg).

    The single cancel primitive for BOTH entries (the HTTP `action:'cancel'` and
    the CMD:CANCEL scan), because a cancel that races a running commit is a LIE,
    not a race we can win: `commit_bulk_move_session` captured source/dest into
    locals before calling perform_smart_move, so wiping the session dict does not
    stop a single spool write. The old unconditional reset answered "cancelled —
    nothing moved" while every spool kept moving, then the commit logged its own
    SUCCESS summary. Flask serves the two requests concurrently (threaded=True)
    and the panel's ❌ Cancel stays clickable through the whole multi-second
    commit (the processing overlay is z 9999, the panel z 20000), so this is
    reachable from ONE tab — no second tab required.

    Non-blocking acquire: a cancel that loses is REFUSED and says so, rather than
    queueing to wipe a session the commit already cleared.
    """
    if not _BULK_MOVE_COMMIT_LOCK.acquire(False):
        # The lock alone can't tell the user what's happening: it is ALSO held by
        # set_bulk_move_dest's re-plan, and even inside a commit it covers a
        # write-free pre-flight (a full Spoolman fetch, a capacity read, and a
        # PrusaLink active-print probe — not the "fraction of a second" an
        # earlier version of this comment claimed; on a slow Spoolman it can be
        # seconds). _BULK_MOVE_WRITING is what distinguishes "spools are moving"
        # from "something else holds the lock", so say only what is true.
        #
        # A cooperative pre-write abort (a cancel_requested flag the commit
        # checks between planning and writing) is still NOT built: it would turn
        # the most destructive path we have into a two-party protocol for a
        # narrow win. Being accurate is the proportionate fix.
        if _BULK_MOVE_WRITING:
            state.add_log_entry(
                "⚠️ Bulk move cancel IGNORED — spools are being moved right now. "
                "Check the Activity Log for what it did.", "WARNING", "ffaa00")
            return False, ("A bulk move is being written right now — it can no "
                           "longer be cancelled. Watch the Activity Log for the result.")
        state.add_log_entry(
            "⚠️ Bulk move cancel IGNORED — the session is busy (planning or "
            "re-targeting). Nothing has moved; try again in a moment.",
            "WARNING", "ffaa00")
        return False, ("The bulk move is busy planning — nothing has moved. "
                       "Try cancelling again in a moment.")
    try:
        was_active = bool(state.BULK_MOVE_SESSION.get('active'))
        was = state.BULK_MOVE_SESSION.get('source_id') or ''
        state.reset_bulk_move()
        # Only log a cancel that cancelled SOMETHING. A cancel against an idle
        # session is a legitimate no-op (a stale tab, a double-click, a
        # belt-and-braces client) and logging it would spam the Activity Log
        # with "cancelled — nothing moved" lines for moves that never existed.
        if was_active:
            state.add_log_entry(
                "🔀 Bulk move cancelled" + (f" (was {was})" if was else "") + " — nothing moved.",
                "INFO")
        return True, "Bulk move cancelled"
    finally:
        _BULK_MOVE_COMMIT_LOCK.release()


def commit_bulk_move_session():
    """Execute the active session's plan, then clear the session on success.

    Re-plans from the CURRENT world state rather than trusting the stored
    preview: a spool may have moved / been archived / a print may have started
    between the preview and the commit, and the commit must be guarded by
    live facts, not a stale snapshot.
    """
    global _BULK_MOVE_WRITING
    if not _BULK_MOVE_COMMIT_LOCK.acquire(False):
        return {"success": False, "msg": "A bulk-move commit is already running."}
    try:
        sess = state.BULK_MOVE_SESSION
        source, dest = sess.get('source_id'), sess.get('dest_id')
        if not sess.get('active') or not source or not dest:
            return {"success": False, "msg": "No bulk move is ready to commit."}

        plan = plan_bulk_move(source, dest)
        # Same helper the preview path uses, so a commit that RE-BLOCKS demotes
        # the stage instead of leaving the deck tile green + advertising a
        # CMD:DONE for a plan every retry refuses.
        _apply_plan_to_session(sess, plan)
        if not plan.get('ok'):
            return {"success": False, "msg": plan.get('msg'),
                    "blocked_reason": plan.get('blocked_reason'),
                    "source": source, "dest": dest}
        if not plan.get('movable_ids'):
            state.reset_bulk_move()
            return {"success": True, "moved": 0, "moved_ids": [], "failed": [],
                    "skipped": plan.get('skipped') or [], "msg": plan.get('msg'),
                    "source": source, "dest": dest}

        # From here on writes really are happening — everything above was
        # read-only guard work, and a cancel arriving during THAT deserves an
        # honest "nothing has moved" rather than "too late".
        _BULK_MOVE_WRITING = True
        result = execute_bulk_move(plan)
        state.reset_bulk_move()
        return result
    finally:
        _BULK_MOVE_WRITING = False
        _BULK_MOVE_COMMIT_LOCK.release()


def get_room_from_location(loc_id):
    if not loc_id:
        return ""
    loc_id = loc_id.strip().upper()
    if "-" not in loc_id:
        return ""

    # L271 Phase 3.5: walk to the TOP-LEVEL room. `parent_id` now stores each
    # row's IMMEDIATE parent, so resolve_parent (a single hop) no longer reaches
    # the room for a nested row (cart-row -> cart, toolhead -> printer);
    # resolve_room walks the chain to the topmost ancestor. On the pre-3.5 flat
    # tree this is byte-identical to the old single-hop split (a dashed row's
    # only ancestor IS its first-segment room). After the immediate-parent
    # migration, a toolhead's room correctly resolves to the printer's room
    # (XL-1 -> XL -> LR) instead of stopping at the printer.
    room = locations_db.resolve_room(loc_id) or ""

    # Exclude known non-room prefixes we don't want to spawn virtual rooms for
    # PM = Polymaker portable boxes, PJ = Project Carts, TST = System Tests.
    if room in locations_db.PSEUDO_ROOM_PREFIXES:
        return ""

    return room

def _eject_destination(spool_data, printer_map, homeless_destination=None):
    """Group 39.6 — where perform_smart_eject sends a spool, decided without
    writing anything or probing a printer (it reads locations.json). Returns
    {"home", "slot", "target", "needs_unassign_confirm"}:
      - `home`: the saved source (physical_source) when it is a real home, with
        `slot` its saved slot; None when there is none. Not a home: the place the
        spool sits now (the loop), anywhere beneath it (a room's own box), or a
        toolhead (a stale head -> head trail).
      - `target`: where a homeless spool goes: the caller-decided
        `homeless_destination`, else '' off a printer (a printer is not a Room),
        else its Room, else '' (Unassigned).
      - `needs_unassign_confirm`: the protected unassign. A homeless spool would
        leave a real location for Unassigned with no caller decision.
    perform_smart_eject runs this code, so the eject route's combined confirm
    (one prompt for "printing" + "no saved home") can't drift from it."""
    current_location = str(spool_data.get('location') or '').strip().upper()
    extra = spool_data.get('extra') or {}
    saved_source = extra.get('physical_source')

    # [ALEX FIX] Prevent Infinite Return Loop
    # If the database thinks we "came from" the place we are currently ejecting from,
    # we must clear that memory, otherwise we just 'return' to the same box.
    if saved_source and str(saved_source).strip().upper() == current_location:
        state.logger.info(f"🛑 Eject Loop Detected: Source is same as Location ({saved_source}). Clearing.")
        saved_source = None

    # [ALEX FIX] Room hierarchy bypass
    # If we are currently floating in a room, and the saved_source is a CHILD of this room,
    # we NEVER bounce back down to the child box. We break the loop and eject to Unassigned.
    # L271 Phase 3.5: "is saved_source anywhere BENEATH current_location" via
    # is_descendant instead of a single-hop resolve_parent equality. parent_id
    # now stores the immediate parent, so a one-hop check would only catch a
    # DIRECT child — but a saved_source can be a grandchild of the room we're
    # floating in (room -> cart -> cart-row). is_descendant walks the chain so
    # the loop-break fires for the whole subtree. On the pre-3.5 flat tree this
    # reduces to the old single-hop equality (a row's only ancestor is its
    # first-segment room), so it's byte-identical until the data flip.
    if current_location and saved_source:
        if locations_db.is_descendant(str(saved_source).strip('"'), current_location):
            state.logger.info(f"🛑 Bypassing Saved Source: {saved_source} is inside {current_location}. Ejecting to Unassigned.")
            saved_source = None

    # A toolhead is never a home. A trail naming one is stale (a head -> head
    # move used to record the old head), and "returning" there put the spool
    # onto whatever is loaded on that head now (2026-09-12).
    if saved_source:
        _src = str(saved_source).strip().strip('"').upper()
        if _src in printer_map or _is_single_occupancy(_src, printer_map, {
                str(r.get('LocationID', '')).strip().upper(): r
                for r in (locations_db.load_locations_list() or [])}):
            state.logger.info(
                f"🛑 Stale ghost trail: #{spool_data.get('id')}'s saved source {_src} is a toolhead — not returning there.")
            saved_source = None

    if saved_source:
        home = str(saved_source).strip('"')
        return {"home": home, "slot": str(extra.get('physical_source_slot', '') or '').strip('"'),
                "target": home, "needs_unassign_confirm": False}

    # Group 42.6: out of a single-slot box, back to where the spool sat before
    # it (its "before the box" note) instead of the "unassign?" prompt. A
    # remembered place that has since been deleted falls back to the prompt.
    pb_loc, pb_slot = _pre_box_place(extra.get(PRE_BOX_KEY))
    if pb_loc and pb_loc != current_location:
        _rows = {str(r.get('LocationID', '')).strip().upper(): r
                 for r in (locations_db.load_locations_list() or []) if isinstance(r, dict)}
        if locations_db._is_single_slot_dryer_box(_rows.get(current_location)) and pb_loc in _rows:
            return {"home": pb_loc, "slot": pb_slot, "target": pb_loc,
                    "needs_unassign_confirm": False, "pre_box": True}

    if homeless_destination is not None:
        # The caller already decided where a spool with no home goes.
        target_loc = str(homeless_destination or '').strip().upper()
    else:
        # Group 41.8 (Derek's Q1, option B, 2026-09-18): a spool with no saved
        # home goes to Unassigned after one "unassign?" prompt, from a printer
        # head as from a box, cart, drawer or shelf. It used to go UP to its
        # Room's loose pile, which made exactly the Room-only spools Derek finds
        # a pain to find. Smart Load's resident keeps the printer's Room through
        # homeless_destination (his 2026-09-12 rule). A Room-valued trail
        # ("CR") is still a saved home, handled above.
        target_loc = ""
    # Protected Unassign (a caller-decided destination needs no prompt)
    needs = target_loc == "" and current_location != "" and homeless_destination is None
    return {"home": None, "slot": "", "target": target_loc, "needs_unassign_confirm": needs}


def perform_smart_eject(spool_id, confirmed_unassign=False, confirm_active_print=False,
                        homeless_destination=None, report=None, to_buffer=False, swapped_from=None):
    """Remove `spool_id` from its current location.

    `homeless_destination`: where to send a spool with no saved home to return
    to ('' = Unassigned), for a caller that has already decided (Smart Load).
    It skips the protected-unassign prompt. None keeps the interactive
    behaviour: "REQUIRE_CONFIRM" for a spool with no saved home.

    `report` (Group 42.5a): a dict the caller passes in; on success it is filled
    with {"from", "to", "slot", "home", "released_boxes"} so the eject can say
    where the spool went and which single-slot box let go of the head. The
    return contract below does not change (callers test `is True`).

    `to_buffer` (Group 40, the same-slot swap; Derek, 2026-10-15): the spool is
    in the user's hand, headed for the scan buffer, not back into its box. A
    slot's own spool swapped out by the spool now taking that slot used to "go
    home" into a slot that is no longer its own, so it landed in the box with no
    slot (the box read 5/4 and the spool got no Quick-Swap tile). It goes to
    Unassigned with its trail cleared instead; the caller puts it in the buffer.
    `report` gains "buffer": True. With `swapped_from` (box, slot), the slot it
    is being swapped out of (Swap option C; Derek, 2026-10-15: "one rule" for
    both swaps), it is filed back where it sat before that slot instead
    (_swap_out_place), and `report["filed"]` says where ('' = Unassigned).

    Returns:
      - True on successful eject
      - False on any failure (load error, DB write error, etc.)
      - "REQUIRE_CONFIRM" if the spool is in a room and confirmed_unassign=False
      - {"status": "requires_confirm", "confirm_type": "active_print", ...}
        when the spool is currently on an actively-printing toolhead and the
        caller hasn't explicitly opted in via confirm_active_print=True.
    Every refusal is truthy, so callers must test `is True`, never truthiness.
    """
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False

    current_location = spool_data.get('location', '').strip().upper()
    extra = spool_data.get('extra', {})
    # The trail before this eject edits `extra`: it names the spool's own
    # single-slot box, the one that lets go of the head (Group 42.1).
    pre_extra = dict(extra or {})

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Active-print safety: ejecting a spool from a printing toolhead is
    # destructive. Bail with requires_confirm so the caller can prompt.
    if not confirm_active_print:
        ap = _active_print_info_for_location(current_location, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} — ejecting from this toolhead will disrupt the print.",
            }

    def _landed(to_loc, slot, home, buffered=False):
        """The eject's write landed. Release the spool's OWN single-slot box from
        the head it left (Group 42.1: only after the write, so a refused or
        rejected eject leaves it bound; and keyed on the spool, so ejecting a
        different spool from a doubled head no longer unbinds it), write ONE
        Activity Log sentence that says both (Derek, 2026-10-13: "a full
        sentence in the activity log"), and fill the caller's report (42.5a)."""
        released = _release_single_slot_box(spool_id, current_location, pre_extra, printer_map, log=False)
        from_txt = current_location or "Unassigned"
        filed = ""
        if buffered:
            filed = _filed_text(to_loc, slot, {str(r.get('LocationID', '')).strip().upper(): r
                                               for r in (locations_db.load_locations_list() or [])
                                               if isinstance(r, dict)}) if to_loc else ""
            where = (f"into the scan buffer; FCC files it back in {filed}, where it sat before that slot"
                     if filed else "into the scan buffer (Unassigned until it is scanned somewhere)")
        elif home:
            _row = next((r for r in (locations_db.load_locations_list() or [])
                         if isinstance(r, dict)
                         and str(r.get('LocationID', '')).strip().upper() == str(to_loc).strip().upper()), None)
            into = "into" if (_row or {}).get('Type') == locations_db.DRYER_BOX_TYPE else "to"
            # A single-slot box has one place: "back into PM-DB-2", not "slot 1".
            if locations_db._is_single_slot_dryer_box(_row):
                slot = ""
            where = f"back {into} {to_loc}" + (f" slot {slot}" if slot else "")
        else:
            where = f"to Room {to_loc}" if to_loc else "to Unassigned"
        sentence = f"⏏️ Ejected #{spool_id} from {from_txt} {where}"
        if released:
            sentence += f"; {released} is no longer attached to {current_location}"
        state.add_log_entry(sentence + ".", "WARNING")
        if isinstance(report, dict):
            report.update({"from": current_location, "to": to_loc, "slot": slot or "",
                           "home": bool(home), "released_boxes": [released] if released else []})
            if buffered:
                report["buffer"] = True
                report["filed"] = filed

    # [ALEX FIX] Explicitly overwrite the slot with empty string.
    # .pop() just removes the key, which causes PATCH to ignore it (keeping the old value).
    extra['container_slot'] = ""

    if to_buffer:
        # The same-slot swap (see the docstring): every trail key cleared, so the
        # spool is a ghost in no box. Swap option C: filed back where it sat
        # before the slot it is swapped out of (its note), else Unassigned; the
        # note is used up unless it went back into a slot (_swap_out_write).
        # The engine's re-reading write (Group 40.2 review): a PATCH Spoolman
        # committed but answered after update_spool's read timeout left the spool
        # Unassigned yet reported "XL-1 still holds #99", in no buffer and with no
        # undo record.
        if swapped_from:
            _rows = {str(r.get('LocationID', '')).strip().upper(): r
                     for r in (locations_db.load_locations_list() or []) if isinstance(r, dict)}
            _ok, _floc, _fslot = _swap_out_write(spool_id, spool_data, swapped_from[0], swapped_from[1], _rows)
            if _ok:
                _landed(_floc, _fslot, home=False, buffered=True)
                return True
        else:
            extra['physical_source'] = ""
            extra['physical_source_slot'] = ""
            if extra.get(PRE_BOX_KEY):
                extra[PRE_BOX_KEY] = ""
            if _move_write(spool_id, "", extra):
                _landed("", "", home=False, buffered=True)
                return True
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
        state.add_log_entry(
            f"❌ Failed to take Spool #{spool_id} off {current_location or 'its location'} "
            f"into the scan buffer: {err}", "ERROR", "ff4444")
        return False

    # Where it goes: its saved home, else the homeless fallback (Group 39.6's
    # _eject_destination, which the eject route's combined confirm also runs).
    dest = _eject_destination(spool_data, printer_map, homeless_destination)
    saved_source = dest['home']

    if saved_source:
        # The location rows, once, for the note's plain place (Group 40 review).
        eject_rows = {str(r.get('LocationID', '')).strip().upper(): r
                      for r in (locations_db.load_locations_list() or []) if isinstance(r, dict)}
        # [ALEX FIX] Retain the assignment slot when returning home.
        # Move the saved slot back into container_slot
        saved_slot_clean = dest['slot']
        home_row = next((r for r in (locations_db.load_locations_list() or [])
                         if isinstance(r, dict)
                         and str(r.get('LocationID', '')).strip().upper() == str(saved_source).strip().upper()),
                        None)
        if not saved_slot_clean and locations_db._is_single_slot_dryer_box(home_row):
            # Group 42.2: a single-slot box's spool is in slot 1 (a legacy
            # PolyDryer trail kept it blank).
            saved_slot_clean = '1'
        if saved_slot_clean:
            # 13.2 — Don't recreate a slot binding that's already claimed by
            # another spool (direct OR ghost from a different spool). The
            # auto-deploy chain can leave a ghost in our former slot moments
            # before we return; landing on top of it makes a 2/2-but-only-
            # one-visible collision in the dryer-box grid. When the slot is
            # already claimed by someone else, land unslotted — the user
            # can manually re-slot once the binding cycle settles.
            slot_taken_by_other = False
            try:
                here = spoolman_api.get_spools_at_location_detailed(saved_source) or []
                others = [o for o in here if int(o.get('id', 0)) != int(spool_id)]
                for other in others:
                    if locations_db.effective_slot(home_row, other.get('slot', ''),
                                                   occupants=len(others)) == saved_slot_clean:
                        slot_taken_by_other = True
                        state.logger.info(
                            f"🛑 Slot collision: {saved_source} slot {saved_slot_clean} "
                            f"already claimed by Spool #{other.get('id')} "
                            f"({'ghost' if other.get('is_ghost') else 'direct'}); "
                            f"landing #{spool_id} unslotted instead."
                        )
                        break
            except Exception as _slot_check_err:
                state.logger.warning(f"Slot-collision check failed: {_slot_check_err}")
            if slot_taken_by_other:
                extra['container_slot'] = ""
                _plain = _pre_box_plain(extra.get(PRE_BOX_KEY), eject_rows) if dest.get('pre_box') else ''
                # Only a place that still is a plain place (Group 40 review,
                # engine-2): never a cart deleted since, nor a head or a room a
                # hand-edited note names; those keep Claude's call 21 below.
                if (_plain and _plain != str(saved_source).strip().upper()
                        and _is_plain_place(_plain, eject_rows)):
                    # Swap option C's rule (Derek, 2026-10-15: "In the case that
                    # the old slot isn't empty, then a non slot ... like a cart"):
                    # the plain place it sat in before that slot, when the note
                    # remembers one, rather than the box with no slot (5/4).
                    state.add_log_entry(
                        f"⚠️ #{spool_id} went to {_plain}, where it sat before {saved_source}: slot "
                        f"{saved_slot_clean} holds another spool now.", "WARNING", "ffaa00")
                    saved_source = _plain
                elif dest.get('pre_box'):
                    # Claude's call 21: back into that box, unslotted, and say so.
                    state.add_log_entry(
                        f"⚠️ #{spool_id} went back into {saved_source} unslotted: slot {saved_slot_clean} "
                        f"holds another spool now.", "WARNING", "ffaa00")
            else:
                extra['container_slot'] = saved_slot_clean
            extra['physical_source_slot'] = ""
        else:
            extra['container_slot'] = ""

        # Clear the source memory so we don't bounce back again later
        extra['physical_source'] = ""
        # Group 42.6 + Swap option C: the "before the box" note rides along while
        # the spool goes back into the box it was deployed from (a single-slot
        # box, or its slot of a multi-slot box: the note still says where it sat
        # before that box, for a later Swap). Back to its NOTED place (out of a
        # single-slot box): into a box, the note becomes what it was there, the
        # plain place behind it (Group 40 review, engine-1: it used to be dropped,
        # so a later Swap filed the spool Unassigned); to the plain place itself,
        # or anywhere else, it is used up.
        if extra.get(PRE_BOX_KEY):
            lands_in_box = _is_dryer_box_row(eject_rows.get(str(saved_source).strip().strip('"').upper()))
            if dest.get('pre_box'):
                extra[PRE_BOX_KEY] = _pre_box_plain(extra.get(PRE_BOX_KEY), eject_rows) if lands_in_box else ""
            elif not lands_in_box:
                extra[PRE_BOX_KEY] = ""
        
        if spoolman_api.update_spool(spool_id, {"location": saved_source, "extra": extra}):
            _landed(saved_source, extra.get('container_slot', ''), home=True)
            return True
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
        state.add_log_entry(
            f"❌ Failed to return Spool #{spool_id} -> {saved_source}: {err}", "ERROR", "ff4444"
        )
    else:
        target_loc = dest['target']
        # Protected Unassign (a caller-decided destination needs no prompt)
        if dest['needs_unassign_confirm'] and not confirmed_unassign:
            return "REQUIRE_CONFIRM"

        # Strictly clear source bindings so it doesn't become a ghost in its old container
        extra['physical_source'] = ""
        extra['physical_source_slot'] = ""
        extra['container_slot'] = ""
        if extra.get(PRE_BOX_KEY):
            extra[PRE_BOX_KEY] = ""   # Group 42.6: any move elsewhere uses the note up

        if spoolman_api.update_spool(spool_id, {"location": target_loc, "extra": extra}):
            _landed(target_loc, "", home=False)
            return True
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
        state.add_log_entry(
            f"❌ Failed to eject Spool #{spool_id}: {err}", "ERROR", "ff4444"
        )
    return False


def perform_toolhead_delete_cascade(target, loc_list, confirm_active_print=False):
    """Group 20.3 — propagate a TOOLHEAD row deletion to the three drifting
    binding stores so nothing is left pointing at the now-gone toolhead.

    Spool side (Spoolman), per Derek's 20.3 decision = UNASSIGNED + breadcrumb:
      - DIRECT spools (Spoolman ``location`` == target): → UNASSIGNED
        (``location`` = ""), with the ghost-trail cleared so they don't resurrect
        as a ghost in their old box.
      - GHOST spools (physically in a box, only DEPLOYED to the toolhead via
        ``physical_source``): keep their box ``location`` and clear ONLY the
        deployment ghost-trail — deleting the toolhead must NOT yank a spool out
        of the box it actually lives in. (The pre-20.3 cascade blindly set
        ``location`` = "" for everything ``get_spools_at_location`` returned,
        which includes these ghosts.)
    FilaBridge: unmap the toolhead (best-effort) so the printer-side map doesn't
    stay pinned to a spool that's no longer assigned.
    locations.json: drop any dryer-box ``slot_targets`` feeding the toolhead, and
    prune the toolhead from any Printer row's ``toolheads[]`` (L271 Phase-4 store).

    MUTATES ``loc_list`` IN-PLACE for the locations.json cleanup; the caller owns
    removing the toolhead row itself + the single ``save_locations_list``.

    ``confirm_active_print=False`` + an ACTIVE print on this toolhead → returns
    ``{"status": "requires_confirm", ...}`` WITHOUT touching anything (mirrors
    ``perform_force_unassign``). Otherwise returns a summary dict
    ``{"status": "ok", "unassigned": [...], "undeployed": [...],
       "slot_bindings_cleared": [...], "toolhead_pruned_from": [...], "errors": [...]}``.
    """
    target_up = str(target).strip().strip('"').upper()
    printer_map = locations_db.get_active_printer_map(loc_list)  # target still present → resolvable for the active-print check

    # Active-print safety: deleting a toolhead mid-print orphans the running spool.
    if not confirm_active_print:
        ap = _active_print_info_for_location(target_up, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} on {target_up} — "
                       f"deleting this toolhead will orphan the running spool.",
            }

    summary = {"status": "ok", "unassigned": [], "undeployed": [],
               "slot_bindings_cleared": [], "toolhead_pruned_from": [], "errors": []}

    # --- Spoolman: re-home spools that reference the toolhead ---
    # Strictly (Group 41 review): the fail-open reader answered [] on a Spoolman
    # blip, so this except never fired, and the head was deleted with its spool
    # still filed on it. A read error keeps the row (the route checks errors).
    try:
        at_loc = spoolman_api.get_spools_at_location_detailed_strict(target_up)
    except Exception as e:
        at_loc = []
        summary["errors"].append(f"could not list spools at {target_up}: {e}")
    for item in at_loc:
        sid = item.get('id')
        spool = spoolman_api.get_spool(sid)
        if not spool:
            summary["errors"].append(f"could not fetch spool #{sid}")
            continue
        extra = dict(spool.get('extra') or {})
        # Read-merge-write: only touch the system-managed binding keys; preserve
        # every sibling extra (Spoolman PATCH replaces the whole extra dict).
        extra['physical_source'] = ""
        extra['physical_source_slot'] = ""
        if item.get('is_ghost'):
            # Only deployed to the dead toolhead → un-deploy, keep box location.
            if spoolman_api.update_spool(sid, {"extra": extra}):
                summary["undeployed"].append(sid)
            else:
                summary["errors"].append(
                    f"spool #{sid} un-deploy failed: {spoolman_api.LAST_SPOOLMAN_ERROR or 'unknown'}")
        else:
            # Physically ON the toolhead → UNASSIGNED, ghost-trail fully cleared.
            extra['container_slot'] = ""
            if spoolman_api.update_spool(sid, {"location": "", "extra": extra}):
                summary["unassigned"].append(sid)
            else:
                summary["errors"].append(
                    f"spool #{sid} unassign failed: {spoolman_api.LAST_SPOOLMAN_ERROR or 'unknown'}")

    # --- locations.json: drop dryer-box slot_targets feeding the toolhead ---
    for row in loc_list:
        if not isinstance(row, dict) or str(row.get('Type', '')).strip() != locations_db.DRYER_BOX_TYPE:
            continue
        # A non-dict `extra` holds no binding to drop, and must not abort the
        # cascade for the boxes after it (the write-back below needs the raw
        # dict, so this guards rather than going through bindings_from_row).
        extra_l = row.get('extra')
        if not isinstance(extra_l, dict):
            continue
        targets = extra_l.get('slot_targets')
        if not isinstance(targets, dict):
            continue
        kept, dropped = {}, []
        for slot, bound in targets.items():
            # Leave PRINTER:<prefix> pool sentinels alone — they bind a printer, not this toolhead.
            if bound and not locations_db.is_printer_sentinel(bound) and str(bound).strip().upper() == target_up:
                dropped.append(slot)
            else:
                kept[slot] = bound
        if dropped:
            extra_l['slot_targets'] = kept
            row['extra'] = extra_l
            for slot in dropped:
                summary["slot_bindings_cleared"].append(f"{row.get('LocationID')}:{slot}")

    # --- locations.json: prune the toolhead from any Printer row's toolheads[] ---
    for row in loc_list:
        if not isinstance(row, dict) or str(row.get('Type', '')).strip().lower() != 'printer':
            continue
        ths = row.get('toolheads')
        if not isinstance(ths, list):
            continue
        kept = [t for t in ths
                if not (isinstance(t, dict) and str(t.get('location_id', '')).strip().upper() == target_up)]
        if len(kept) != len(ths):
            row['toolheads'] = kept
            summary["toolhead_pruned_from"].append(row.get('LocationID'))

    return summary


def perform_force_unassign(spool_id, confirm_active_print=False):
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False
    extra = spool_data.get('extra', {})
    current_location = spool_data.get('location', '').strip().upper()

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Active-print safety: force-unassign from a printing toolhead disrupts
    # the print. Bail with requires_confirm unless the caller opted in.
    if not confirm_active_print:
        ap = _active_print_info_for_location(current_location, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} — force-unassigning from this toolhead will disrupt the print.",
            }

    # The trail before it is blanked below names the spool's own single-slot box.
    pre_extra = dict(extra or {})
    # [ALEX FIX] Explicitly overwrite slots and sources with empty strings
    # to guarantee Spoolman API removes them instead of ignoring dropped keys
    extra['container_slot'] = ""
    extra['physical_source'] = ""
    extra['physical_source_slot'] = ""
    if extra.get(PRE_BOX_KEY):
        extra[PRE_BOX_KEY] = ""   # Group 42.6: a move elsewhere uses the note up

    if spoolman_api.update_spool(spool_id, {"location": "", "extra": extra}):
        state.add_log_entry(f"🗑️ Force Unassigned #{spool_id}", "WARNING")
        # Group 42.1: leaving a head this way releases its own single-slot box
        # too (Force Location → Unassigned, an archive with weight left). A
        # weigh-out to 0 g is released earlier, by update_spool's archive edge.
        _release_single_slot_box(spool_id, current_location, pre_extra, printer_map)
        return True
    err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
    state.add_log_entry(
        f"❌ Failed to force-unassign Spool #{spool_id}: {err}", "ERROR", "ff4444"
    )
    return False

NOTHING_TO_UNDO_MSG = "Nothing to undo (Undo Last Move reverts spool moves only)."


def peek_undo():
    """Group 41.4 — the record Undo Last Move would reverse, without popping it."""
    return state.UNDO_STACK[-1] if state.UNDO_STACK else None


def _undo_get(mapping, sid):
    mapping = mapping or {}
    hit = mapping.get(sid)
    return mapping.get(str(sid)) if hit is None else hit


def _undo_place(loc, slot, printer_map):
    """'in LR-MDB-1 slot 2', 'on XL-2', 'in CR', 'in Unassigned'."""
    lid = str(loc or '').strip().strip('"').upper()
    if not lid:
        return "in Unassigned"
    if lid in (printer_map or {}):
        return f"on {lid}"
    slot = str(slot or '').strip().strip('"')
    return f"in {lid} slot {slot}" if slot else f"in {lid}"


def _undo_items(record, printer_map):
    """[(sid, place)] for every spool the record would put back: the moved
    spools first, then the residents a Smart Load had unloaded."""
    items = []
    for sid, loc in (record.get('moves') or {}).items():
        snap = _undo_get(record.get('extras'), sid) or {}
        items.append((sid, _undo_place(loc, snap.get('container_slot'), printer_map)))
    for sid, loc in (record.get('ejections') or {}).items():
        snap = _undo_get(record.get('ejection_extras'), sid) or {}
        items.append((sid, _undo_place(loc, snap.get('container_slot'), printer_map)))
    for sid, d in (record.get('displaced') or {}).items():
        snap = (d or {}).get('extras') or {}
        items.append((sid, _undo_place((d or {}).get('location'), snap.get('container_slot'), printer_map)))
    return items


def describe_undo(record, printer_map):
    """The question Undo Last Move asks: "Undo: put #57 back in LR-MDB-1 slot 2
    and #196 back on XL-2?" (Derek, 2026-10-13: it always asks first, naming
    the move it will reverse)."""
    items = _undo_items(record, printer_map)
    if not items:
        return f"Undo: {record.get('summary') or 'the last move'}?"
    return "Undo: put " + _and_list(f"#{sid} back {place}" for sid, place in items) + "?"


def _undo_current_heads(record, printer_map):
    """([(head, 'source', [sid])], unreadable ids): the printer heads the spools
    this undo would move sit on NOW, read from Spoolman. The record's target is
    not that: a box-slot move whose auto-deploy loaded the bound head keeps the
    BOX as its target, and a spool can have moved on since (Group 41 review)."""
    heads: typing.Dict[str, typing.List[typing.Any]] = {}
    unreadable = []
    for sid in (list((record.get('moves') or {}).keys()) + list((record.get('ejections') or {}).keys())
                + list((record.get('displaced') or {}).keys())):
        rec = spoolman_api.get_spool(sid)
        if not isinstance(rec, dict) or rec.get('id') is None:
            unreadable.append(sid)
            continue
        here = str(rec.get('location') or '').strip().strip('"').upper()
        if here in (printer_map or {}):
            heads.setdefault(here, []).append(sid)
    return [(head, 'source', sids) for head, sids in heads.items()], unreadable


def _undo_heads(record, printer_map, current_heads=()):
    """[(head, role, [sid])] — every printer head this undo would change: where
    the moved spools are now (`current_heads`, from _undo_current_heads) and
    every head it puts a spool back on."""
    touched = list(current_heads)
    for sid, loc in list((record.get('moves') or {}).items()) + list((record.get('ejections') or {}).items()):
        lid = str(loc or '').strip().strip('"').upper()
        if lid in (printer_map or {}):
            touched.append((lid, 'destination', [sid]))
    return touched


def undo_confirm_answer(record, confirmed_heads=None):
    """What /api/undo answers before it writes anything: the question naming the
    move, the record's number (the Yes must quote it), and, when a head it would
    change belongs to a printer that is printing, those heads with D6's
    call-out. A PAUSED printer isn't active, so it gets the plain question.
    Where the spools are now is read first; a spool that can't be read asks
    nothing (an error answer), since which heads to ask about is unknown."""
    printer_map = locations_db.get_active_printer_map()
    current, unreadable = _undo_current_heads(record, printer_map)
    if unreadable:
        names = _and_list(f"#{sid}" for sid in unreadable)
        msg = (f"Couldn't read {names} from Spoolman, so FCC can't tell whether this undo changes a "
               f"printing head. Nothing was undone; try again in a moment.")
        state.add_log_entry(f"❌ Undo not asked: {msg}", "ERROR", "ff4444")
        return {"success": False, "msg": msg}
    question = describe_undo(record, printer_map)
    active = []
    _pa = None
    try:
        import prusalink_api as _pa
        _pa.begin_probe_cache()
    except Exception:
        _pa = None
    try:
        active = _uncovered_active_heads(_undo_heads(record, printer_map, current),
                                         confirmed_heads or [], printer_map)
    finally:
        if _pa is not None:
            try:
                _pa.clear_probe_cache()
            except Exception:
                pass
    msg = question
    if active:
        heads = _and_list(sorted({a['toolhead'] for a in active}))
        printers = _and_list(sorted({f"{a['printer_name']} is {a['state']}" for a in active}))
        msg = (f"{printers}: this undo changes {heads} mid-print, and FCC charges the print "
               f"to whatever spool ends up loaded. {question}")
    return {"success": False, "requires_confirm": True, "undo_id": record.get('id'),
            "confirm_type": "active_print" if active else "undo",
            "active_prints": active, "msg": msg}


def perform_undo(expected_id=None):
    """Reverse the last move. Group 41.4: honest about what it did. Only the
    restores that land are reported (and logged) as undone; a rejected or
    blocked restore makes the answer success: False, naming the spool, with an
    ERROR line. `expected_id` is the record the user said Yes to; a different
    record on top (another move landed meanwhile) is refused, writing nothing."""
    if not state.UNDO_STACK:
        state.add_log_entry(f"↩️ {NOTHING_TO_UNDO_MSG}", "INFO")
        return {"success": False, "nothing": True, "msg": NOTHING_TO_UNDO_MSG}
    if expected_id is not None and str(state.UNDO_STACK[-1].get('id')) != str(expected_id):
        msg = "The last move changed since you pressed Undo. Press Undo Last Move again."
        state.add_log_entry(f"⚠️ Undo refused: {msg}", "WARNING", "ffaa00")
        return {"success": False, "stale": True, "msg": msg}
    last = state.UNDO_STACK.pop()
    moves = last['moves']
    target = last.get('target')
    origin = last.get('origin', '')
    printer_map = locations_db.get_active_printer_map()
    restored, failed = [], []

    # Reassign each moved spool back to its origin location in Spoolman, and
    # (L298 Phase 0) restore the pre-move system-managed extras so the undo is a
    # TRUE rollback — the spool returns to its exact slot + ghost trail, not just
    # its location. The write MUST go through spoolman_api.update_spool, NOT a raw
    # requests.patch: update_spool sanitizes each extra to Spoolman's JSON-string
    # wire form (`""` not ``) and read-merge-writes so siblings survive the
    # whole-`extra`-replace PATCH. A raw PATCH sent the snapshotted empties
    # unwrapped, so Spoolman 400'd the ENTIRE request (location included) and the
    # undo silently no-op'd while still reporting success — caught live 2026-07-11
    # (the Phase-0 mock-only tests couldn't see the wire-format rejection). It
    # also now surfaces a rejection to the Activity Log instead of dropping it
    # silently. A legacy record without 'extras' (pre-L298) restores location only.
    extras_by_sid = last.get('extras', {})
    undo_rows = {str(r.get('LocationID', '')).strip().upper(): r
                 for r in (locations_db.load_locations_list() or []) if isinstance(r, dict)}

    def _blocked(sid, loc):
        """Why `sid` can't go back onto `loc`, or ''. A one-spool head must
        really be free: the incoming spool's restore may have been rejected, or
        a writer that records no undo (auto-unarchive, the wizard, a direct
        edit) may have loaded something since; restoring blind stacked two
        spools on one head (2026-09-12 review for a Smart Load's resident;
        Group 42.3b, I5-10, for a moved spool). Logged at ERROR. One-spool is
        the engine's rule: a multi-head Printer row holds many (Group 42 review)."""
        if not loc or not _holds_one_spool(loc, printer_map, undo_rows):
            return ""
        head = str(loc).strip().strip('"').upper()
        try:
            occupants = strict_direct_occupants(head, exclude=[sid])
            why = ("it holds " + ", ".join(f"#{o}" for o in occupants)) if occupants else ""
        except Exception as _occ_err:
            why = f"it could not be read from Spoolman ({_occ_err})"
        if why:
            state.add_log_entry(f"❌ Undo: not putting Spool #{sid} back on {head} — {why}",
                                "ERROR", "ff4444")
        return why

    released = last.get('released') or {}
    ejection_released = last.get('ejection_released') or {}

    def _reattach(loc, box):
        """Group 42.3b: a spool put back onto a head brings back the single-slot
        box its leaving released from that head. The record names that box
        (Group 42 review): re-attaching from the spool's trail took a PolyDryer
        off the head its own spool runs on, or bound one that never was. A box
        attached to another head since stays there."""
        head = str(loc or '').strip().strip('"').upper()
        box = str(box or '').strip().strip('"').upper()
        if not head or head not in printer_map or not box:
            return
        try:
            _att, _detail = locations_db.attach_single_slot_box_to_toolhead(box, head, steal=False)
            if _att and _detail != "already attached":
                state.add_log_entry(f"🔗 Undo: {box} attached to {head} again — its spool is back on the head",
                                    "INFO")
            elif not _att:
                state.logger.info(f"42.3b undo re-attach of {box} to {head} skipped: {_detail}")
        except Exception as _ae:
            state.logger.warning(f"42.3b undo re-attach skipped: {_ae}")

    # Where each spool really was before this undo (the record's target is not
    # always it: an auto-deploy loads the box slot's head), for the log line.
    was_at: typing.Dict[str, str] = {}
    for sid, loc in moves.items():
        payload: typing.Dict[str, typing.Any] = {"location": loc}
        snap = extras_by_sid.get(sid)
        if snap is None:
            snap = extras_by_sid.get(str(sid))
        cur: typing.Dict[str, typing.Any] = {}
        if snap is not None:
            cur = spoolman_api.get_spool(sid) or {}
            was_at[str(sid)] = str(cur.get('location') or '').strip().strip('"').upper()
            merged = dict(cur.get('extra') or {})
            for k in spoolman_api.SYSTEM_MANAGED_EXTRAS:
                merged[k] = snap.get(k, '')
            payload["extra"] = merged
        why = _blocked(sid, loc)
        if why:
            failed.append(f"#{sid} ({why})")
            continue
        if spoolman_api.update_spool(sid, payload):
            restored.append(sid)
            # Group 42.1 / 42.3b: leaving a head releases its own single-slot
            # box (an undone PolyDryer deploy lets go of the head)...
            _now = was_at.get(str(sid), '')
            if _now and _now != str(loc or '').strip().strip('"').upper():
                _release_single_slot_box(sid, _now, cur.get('extra') or {}, printer_map)
            # ...and going back onto one brings back what the move released.
            _reattach(loc, released.get(str(sid)))
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            failed.append(f"#{sid} ({err})")
            state.add_log_entry(
                f"❌ Undo: failed to restore Spool #{sid} → {loc or 'UNASSIGNED'}: {err}",
                "ERROR", "ff4444")
    # [ALEX FIX] Revert Smart Ejections — same canonical write surface so a
    # rejection is surfaced rather than silently dropped (a location-only PATCH
    # was always accepted, but consistency + failure-visibility matter here too).
    # Smart Load records each resident's PRE-eject location and system-managed
    # extras. It used to record where the eject SENT the resident, so this
    # replay wrote the spool to where it already was and the head stayed empty
    # (2026-09-12). A record without 'ejection_extras' restores location only.
    ejections = last.get('ejections', {})
    ejection_extras = last.get('ejection_extras', {})
    restored_ejections = []
    for ejected_sid, original_loc in ejections.items():
        why = _blocked(ejected_sid, original_loc)
        if why:
            failed.append(f"#{ejected_sid} ({why})")
            continue
        eject_payload: typing.Dict[str, typing.Any] = {"location": original_loc}
        snap = ejection_extras.get(ejected_sid)
        if snap is None:
            snap = ejection_extras.get(str(ejected_sid))
        if snap is not None:
            cur = spoolman_api.get_spool(ejected_sid) or {}
            merged = dict(cur.get('extra') or {})
            for k in spoolman_api.SYSTEM_MANAGED_EXTRAS:
                merged[k] = snap.get(k, '')
            eject_payload["extra"] = merged
        if spoolman_api.update_spool(ejected_sid, eject_payload):
            restored_ejections.append(ejected_sid)
            for _box in ejection_released.get(str(ejected_sid)) or ():
                _reattach(original_loc, _box)
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            failed.append(f"#{ejected_sid} ({err})")
            state.add_log_entry(
                f"❌ Undo: failed to restore ejected Spool #{ejected_sid} → "
                f"{original_loc or 'UNASSIGNED'}: {err}", "ERROR", "ff4444")

    # Swap option C: a stored spool a Swap took out of its slot (filed back where
    # it sat before, and put in the scan buffer) goes back into that slot, after
    # the restores above have taken the spool that took the slot back out of
    # it. Never on top of a spool that claims the slot now (read strictly).
    displaced = last.get('displaced') or {}
    restored_displaced = []
    for d_sid, d in displaced.items():
        d_box = str((d or {}).get('location') or '').strip().strip('"').upper()
        d_snap = (d or {}).get('extras') or {}
        d_slot = _norm_slot(d_snap.get('container_slot'))
        why = ""
        if d_box and d_slot:
            try:
                _items = spoolman_api.get_spools_at_location_detailed_strict(d_box) or []
                _claims, _own, _ghost = box_slot_claims(undo_rows.get(d_box), d_box, _items, [d_sid])
                _holders = _claims.get(d_slot) or []
                if _holders:
                    why = f"{d_box} slot {d_slot} holds " + ", ".join(f"#{h}" for h in _holders)
            except Exception as _d_err:
                why = f"{d_box} could not be read from Spoolman ({_d_err})"
        if why:
            failed.append(f"#{d_sid} ({why})")
            state.add_log_entry(f"❌ Undo: not putting Spool #{d_sid} back in {d_box} slot {d_slot} — {why}",
                                "ERROR", "ff4444")
            continue
        d_cur = spoolman_api.get_spool(d_sid) or {}
        d_merged = dict(d_cur.get('extra') or {})
        for k in spoolman_api.SYSTEM_MANAGED_EXTRAS:
            d_merged[k] = d_snap.get(k, '')
        if spoolman_api.update_spool(d_sid, {"location": d_box, "extra": d_merged}):
            restored_displaced.append(int(d_sid) if str(d_sid).isdigit() else d_sid)
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            failed.append(f"#{d_sid} ({err})")
            state.add_log_entry(f"❌ Undo: failed to put Spool #{d_sid} back in {d_box} slot {d_slot}: {err}",
                                "ERROR", "ff4444")

    # Group 40, the same-slot swap: a spool the move took off its head into the
    # scan buffer is back on that head now, so it leaves the buffer (only the
    # ones whose restore landed). The page drops them too (`unbuffered`). So does
    # a spool a Swap took out of its slot, now back in it.
    restored_set = {str(s) for s in restored_ejections + restored_displaced}
    unbuffered = [sid for sid in (last.get('buffered') or []) if str(sid) in restored_set]
    if unbuffered:
        gone = {str(s) for s in unbuffered}
        state.GLOBAL_BUFFER = [b for b in (getattr(state, 'GLOBAL_BUFFER', None) or [])
                               if not (isinstance(b, dict) and str(b.get('id')) in gone)]

    # [ALEX FIX] Restore to Buffer Memory
    state.logger.info(f"UNDO RECORD TRIGGER: {last}")
    if origin == 'buffer':
        for sid in restored:
            spool_data = spoolman_api.get_spool(sid)
            if spool_data:
                info = spoolman_api.format_spool_display(spool_data)
                # Ensure we avoid duplicates
                if not any(s.get('id') == int(sid) for s in getattr(state, 'GLOBAL_BUFFER', [])):
                    if not hasattr(state, 'GLOBAL_BUFFER'): state.GLOBAL_BUFFER = []
                    # Prepend to buffer so it shows up first
                    state.GLOBAL_BUFFER.insert(0, {'id': int(sid), 'display': info['text'], 'color': info['color']})

    # Group 41.4: the line reads forwards and names only what really went back,
    # so a user can put the rest right by hand: "↩️ Undo: Spool A is back in
    # LR-MDB-1 slot 2 (it had been moved to XL-2)". Labels were captured at move
    # time (fall back to #sid for a legacy record or a deleted spool).
    labels = last.get('labels', {})
    extras = last.get('extras', {})

    def _label(sid):
        return labels.get(sid) or labels.get(str(sid)) or f"#{sid}"

    parts = []
    if restored:
        segs = [f"{_label(sid)} is back "
                f"{_undo_place(moves.get(sid), (_undo_get(extras, sid) or {}).get('container_slot'), printer_map)}"
                for sid in restored]
        note = f"{'it' if len(segs) == 1 else 'they'} had been moved to {target or 'UNASSIGNED'}"
        # Name a spool that was somewhere else, e.g. the head an auto-deploy
        # loaded it onto, so a user knows which head was just emptied.
        tgt = str(target or '').strip().upper()
        drift = [f"#{sid} was at {was_at[str(sid)]}" for sid in restored
                 if was_at.get(str(sid)) and was_at[str(sid)] != tgt]
        if drift:
            note += "; " + _and_list(drift)
        parts.append(f"{_and_list(segs)} ({note})")
    if restored_ejections:
        segs = [f"#{sid} is back "
                f"{_undo_place(ejections.get(sid), (_undo_get(ejection_extras, sid) or {}).get('container_slot'), printer_map)}"
                for sid in restored_ejections]
        parts.append(_and_list(segs))
    if restored_displaced:
        segs = []
        for sid in restored_displaced:
            d = _undo_get(displaced, sid) or {}
            segs.append(f"#{sid} is back "
                        f"{_undo_place(d.get('location'), (d.get('extras') or {}).get('container_slot'), printer_map)}")
        parts.append(_and_list(segs))
    if not moves and not ejections and not displaced:
        # Legacy / no-move record: its summary already reads "Moved N -> target".
        parts.append(last.get('summary', f"moved -> {target}"))
    if parts:
        state.add_log_entry(f"↩️ Undo: {'; '.join(parts)}", "WARNING")
    if failed:
        msg = f"Undo could not put back {', '.join(failed)}."
        state.add_log_entry(f"⚠️ Undo partly failed: {msg}", "ERROR", "ff4444")
        return {"success": False, "msg": msg, "restored": restored + restored_ejections + restored_displaced,
                "unbuffered": unbuffered}
    return {"success": True, "msg": f"↩️ Undo: {'; '.join(parts)}" if parts else "↩️ Undone",
            "restored": restored + restored_ejections + restored_displaced, "unbuffered": unbuffered}

def process_audit_scan(scan_result):
    """Handles scans when in Audit Mode."""
    session = state.AUDIT_SESSION
    
    # 1. COMMANDS
    if scan_result['type'] == 'command':
        cmd = scan_result['cmd']
        if cmd == 'done' or cmd == 'cancel':
            # Generate Report
            missing = [sid for sid in session['expected_items'] if sid not in session['scanned_items']]
            expected_loc = session.get('location_id') or ''

            # 18.2 follow-up — bare spool IDs aren't useful in the Activity
            # Log report ("Missing: 101, 102, 103" doesn't tell the user
            # which spools to look for). Resolve each id to a display label
            # via format_spool_display; fall back to "#N" on any lookup
            # miss so a missing record can't break the report.
            def _label(sid):
                try:
                    sd = spoolman_api.get_spool(sid)
                    if sd:
                        info = spoolman_api.format_spool_display(sd) or {}
                        text = info.get('text') or ''
                        if text:
                            return f"#{sid} {text}"
                except Exception:
                    pass
                return f"#{sid}"

            summary = "📝 <b>Audit Report:</b><br>"
            if not missing and not session['rogue_items']:
                summary += "✅ Perfect Match! All items accounted for."
                color = "00ff00" # Green
            else:
                color = "ffaa00" # Orange
                if missing: summary += f"❌ <b>Missing:</b> {', '.join(_label(sid) for sid in missing)}<br>"
                if session['rogue_items']: summary += f"⚠️ <b>Extra:</b> {', '.join(_label(sid) for sid in session['rogue_items'])}"

            state.add_log_entry(summary, "INFO", color)

            # 18.2 Part A — on `done` (not `cancel` — cancel is the user
            # explicitly bailing out, e.g. they realized they were
            # auditing the wrong location), auto-park each missing spool
            # at the virtual UNKNOWN bucket. Plant the audited location
            # on extra.fcc_pre_audit_location so a recovery scan can
            # route the spool home. SYSTEM_MANAGED_EXTRAS protects the
            # key from being clobbered by user-driven edit surfaces.
            if cmd == 'done' and missing and expected_loc:
                for sid in missing:
                    try:
                        existing = spoolman_api.get_spool(sid) or {}
                        cur_extra = dict(existing.get('extra') or {})
                        cur_extra['fcc_pre_audit_location'] = expected_loc
                        ok = spoolman_api.update_spool(
                            sid,
                            {"location": "UNKNOWN", "extra": cur_extra},
                        )
                        # 18.2 follow-up — log with the spool's display label
                        # so the Activity Log line is actually readable
                        # ("moved Spool #102 Hatchbox PLA Black → UNKNOWN"
                        # vs the prior bare "moved Spool #102 → UNKNOWN").
                        display = _label(sid)
                        if ok:
                            state.add_log_entry(
                                f"❓ Audit: moved Spool {display} → UNKNOWN "
                                f"(was expected at {expected_loc}, not scanned)",
                                "WARNING",
                                "ffaa00",
                            )
                        else:
                            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                            state.add_log_entry(
                                f"❌ Audit: failed to park Spool {display} at UNKNOWN: {err}",
                                "ERROR",
                                "ff4444",
                            )
                    except Exception as _e:
                        state.logger.error(f"Audit auto-park failed for #{sid}: {_e}")

            state.reset_audit()
            state.add_log_entry("Audit Mode Ended.", "INFO")
            return {"status": "success", "msg": "Audit Complete"}

        return {"status": "error", "msg": "Command not allowed in Audit"}

    # 2. LOCATION SCAN
    if scan_result['type'] == 'location':
        loc_id = scan_result['id']
        if session['location_id']:
            state.add_log_entry(f"⚠️ Already auditing {session['location_id']}. Finish first!", "WARNING")
            return {"status": "error"}
            
        session['location_id'] = loc_id
        expected = spoolman_api.get_spools_at_location(loc_id)
        session['expected_items'] = expected
        state.add_log_entry(f"🧐 Auditing <b>{loc_id}</b>. expecting {len(expected)} items. Start scanning!", "INFO", "00aaff")
        return {"status": "success"}

    # 3. SPOOL SCAN
    if scan_result['type'] == 'spool':
        if not session['location_id']:
            state.add_log_entry("⚠️ Scan a Location first!", "WARNING")
            return {"status": "error"}
            
        spool_id = scan_result['id']
        if spool_id in session['scanned_items']:
            return {"status": "success", "msg": "Already scanned"}
            
        session['scanned_items'].append(spool_id)
        
        if spool_id in session['expected_items']:
            rem = len(session['expected_items']) - len(session['scanned_items'])
            msg = f"✅ Found #{spool_id}"
            if rem > 0: msg += f" ({rem} left)"
            else: msg += " (All found!)"
            state.add_log_entry(msg, "INFO", "00ff00")
        else:
            session['rogue_items'].append(spool_id)
            data = spoolman_api.get_spool(spool_id)
            curr_loc = data.get('location', 'Unknown')
            state.add_log_entry(f"⚠️ Found #{spool_id}! (DB says: {curr_loc})", "WARNING")
            
        return {"status": "success"}

    return {"status": "error", "msg": "Unknown scan type"}

def get_live_spools_data(spool_ids):
    """
    Rapidly queries Spoolman for a specific list of Spool IDs and returns 
    their formatted display strings and colors.
    Used by the frontend to live-refresh the Dashboard Buffer and Location Manager UI.
    """
    results = {}
    for sid in spool_ids:
        try:
            spool_data = spoolman_api.get_spool(sid)
            if spool_data:
                info = spoolman_api.format_spool_display(spool_data)
                
                sloc = str(spool_data.get('location', '')).strip()
                extra = spool_data.get('extra', {})
                is_ghost = False
                p_source = str(extra.get('physical_source', '')).strip().replace('"', '')
                if p_source and sloc.upper() != p_source.upper():
                    is_ghost = True
                ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')
                
                final_slot = info.get('slot', '')
                if is_ghost and ghost_slot:
                    final_slot = ghost_slot

                results[str(sid)] = {
                    "display": info["text"],
                    "color": info["color"],
                    "color_direction": info.get("color_direction", "longitudinal"),
                    "remaining_weight": spool_data.get("remaining_weight"),
                    "details": info.get("details", {}),
                    "archived": spool_data.get("archived", False),
                    "location": p_source if is_ghost else sloc,
                    "is_ghost": is_ghost,
                    "slot": final_slot,
                    "deployed_to": sloc if is_ghost else None
                }
        except Exception as e:
            state.logger.error(f"Failed to live-refresh spool {sid}: {e}")

    return results


def spools_in_slot(box_loc_id, slot):
    """Ids of the spools FCC records in (box_loc_id, slot): direct occupants and
    ghosts whose trail names that slot. Normally one; two or more mean the
    records disagree (Group 42 review).

    Scans items at the location (including ghost items whose
    physical_source points back to this box) and matches the slot
    string loosely (Spoolman stores container_slot with JSON-string
    quoting — see spoolman_api.parse_inbound_data).
    """
    if not box_loc_id or not str(slot).strip():
        return []
    wanted = str(slot).strip().strip('"')
    items = spoolman_api.get_spools_at_location_detailed(box_loc_id) or []
    # Group 42.2: a single-slot box's lone spool is in slot 1 even when its slot
    # was stored blank (a legacy PolyDryer row), so Quick-Swap can find it.
    box_up = str(box_loc_id).strip().upper()
    row = next((r for r in (locations_db.load_locations_list() or [])
                if isinstance(r, dict) and str(r.get('LocationID', '')).strip().upper() == box_up), None)
    return [int(item['id']) for item in items
            if locations_db.effective_slot(row, item.get('slot', ''), occupants=len(items)) == wanted]


def find_spool_in_slot(box_loc_id, slot, claimants=None):
    """Return the spool id sitting in (box_loc_id, slot), or None. None too when
    two spools claim the slot: the Quick-Swap grid showed the last and this
    returned the first, so a tap moved a different spool than its card showed
    (Group 42 review). Pass a list as `claimants` to get every claimant back
    (/api/quickswap names them)."""
    ids = spools_in_slot(box_loc_id, slot)
    if isinstance(claimants, list):
        claimants.extend(ids)
    return ids[0] if len(ids) == 1 else None