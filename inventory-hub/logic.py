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
        return None
    if not state_dict or not state_dict.get('is_active'):
        return None
    return {
        'toolhead': loc_up,
        'printer_name': printer_name,
        'state': state_dict.get('state', 'ACTIVE'),
    }


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


def _active_print_message(active_prints, target, residents=(), target_slot=None):
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
    sentence the overlays have always shown."""
    sources = [a for a in active_prints if a.get('role') == 'source']
    feeds = [a for a in active_prints if a.get('role') == 'feeds']
    told = {a['printer_name'] for a in sources}
    out = []
    if sources:
        loaded = [(sid, a['toolhead']) for a in sources for sid in (a.get('spools') or [])]
        if len(loaded) == 1:
            where, pronoun = f"#{loaded[0][0]} is loaded on {loaded[0][1]}", "it"
        else:
            where = _and_list([f"#{loaded[0][0]} is loaded on {loaded[0][1]}"]
                              + [f"#{s} on {h}" for s, h in loaded[1:]])
            pronoun = "them"
        if any(f['printer_name'] in told for f in feeds):
            out.append(f"{where}.")
        else:
            whose = ("this print" if len(loaded) == 1 else
                     f"this {sources[0]['printer_name']} print" if len(told) == 1 else "these prints")
            out.append(f"{where}. Moving {pronoun} to {target} means FCC stops charging {whose} to {pronoun}.")
        if residents:
            out.append(f"It also unloads {_and_list('#' + str(r) for r in residents)} from {target}.")
    for a in active_prints:
        role = a.get('role')
        if role == 'source':
            continue
        if role == 'feeds':
            moving = _and_list('#' + str(s) for s in a.get('spools') or []) if a.get('spools') else "the spool"
            slot = f"{target} slot {target_slot}" if target_slot not in (None, '') else target
            lead = "" if a['printer_name'] in told else f"{a['printer_name']} is {a['state']}. "
            told.add(a['printer_name'])
            out.append(f"{lead}{slot} feeds {a['toolhead']}, so this also loads {moving} onto "
                       f"{a['toolhead']} and unloads what {a['toolhead']} holds.")
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


def _requires_confirm_answer(active_prints, target, target_slot, residents=()):
    """Group 39.1 — the ONE shape every move confirm answers in. Groups 40-42
    extend it (40.0c fills fed_heads / can_store); none redefines it.
    `active_print` keeps the first entry's three original keys for existing
    consumers; a replay sends back the heads in `active_prints`."""
    first = active_prints[0]
    return {
        "status": "requires_confirm",
        "confirm_type": "active_print",
        "active_prints": active_prints,
        "active_print": {k: first[k] for k in ("toolhead", "printer_name", "state")},
        "fed_heads": [],
        "can_store": False,
        "target_slot": None if target_slot in (None, '') else str(target_slot),
        "msg": _active_print_message(active_prints, target, residents, target_slot),
    }


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


def _move_write(sid, target, new_extra):
    """The move engine's spool write: True when it landed.

    update_spool's timeout is a READ timeout, so a PATCH Spoolman committed but
    answered slowly comes back as a failure (Group 43.6's lesson). The move then
    reported the spool as failed, left it out of the undo record and tallied it
    as failed in a bulk move, although it had moved (Group 41 review). So a
    failed write is re-read, and counts as landed when the spool now sits at
    `target` with exactly the slot and trail this write set."""
    if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
        return True
    err = spoolman_api.LAST_SPOOLMAN_ERROR
    rec = spoolman_api.get_spool(sid)
    if not isinstance(rec, dict) or rec.get('id') is None:
        return False
    if str(rec.get('location') or '').strip().upper() != str(target).strip().upper():
        return False
    have = rec.get('extra') or {}
    for k in spoolman_api.SYSTEM_MANAGED_EXTRAS:
        if (str(have.get(k) or '').strip().strip('"')
                != str(new_extra.get(k) or '').strip().strip('"')):
            return False
    state.add_log_entry(
        f"⚠️ Spoolman answered an error moving Spool #{sid} -> {target} ({err or 'no detail'}), "
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


# Thread-local re-entry depth for perform_smart_move. The auto-deploy chain
# re-enters the wrapper synchronously on the same thread; depth 0 is the
# outermost move, which owns the per-move printer-state probe cache (L3 fix A).
_smart_move_depth = threading.local()


def perform_smart_move(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False):
    """Entry point for the slot-move pipeline.

    Owns the per-move printer-state probe cache (L3 fix A) so the auto-deploy
    recursion probes a given printer ONCE, not twice: a thread-local depth guard
    detects the OUTERMOST call and begins/clears the cache around it, while the
    recursive re-entry (depth > 0) leaves the outer cache untouched. All real
    work lives in _perform_smart_move_impl — this is a behaviour-neutral wrapper.
    """
    depth = getattr(_smart_move_depth, "n", 0)
    owns_move = depth == 0
    _smart_move_depth.n = depth + 1
    _pa = None
    if owns_move:
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
        )
    finally:
        _smart_move_depth.n = getattr(_smart_move_depth, "n", 1) - 1
        if owns_move and _pa is not None:
            try:
                _pa.clear_probe_cache()
            except Exception:
                pass


def _perform_smart_move_impl(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False):
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
    #   3. Slot choice: auto-slot for a slotless single spool into a multi-slot
    #      box (40.0e moves it up here).
    #   4. Strict reads, failing closed (status error, nothing written): the
    #      moving spools' own records (39.4), the target head's residents (39.7),
    #      the bound head's residents (40.0c).
    #   5. ONE confirm answer: _uncovered_active_heads over the destination /
    #      feeds / source heads (one probe per printer, through the memo), in the
    #      shape _requires_confirm_answer builds (40.0c adds fed_heads).
    #   6. Writes, per spool, in this order: Smart Load's resident ejects (from
    #      a fresh strict list of the head when step 5 could have probed); the
    #      slot unseat (41.6); the spool's own write (13.6 / record_source at a
    #      head, 40.0d; the single-slot box release, 42.1); then the chain.
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
    # spool on all of them.
    is_toolhead = bool(tgt_info) and tgt_info.get('Type') in locations_db.TOOLHEAD_TYPES
    if bool(tgt_info) and str(tgt_info.get('Type', '')).strip() == 'Printer':
        _own_heads = [str(t.get('location_id', '')).strip().upper()
                      for t in (tgt_info.get('toolheads') or []) if isinstance(t, dict)]
        try:
            _one_slot = int(str(tgt_info.get('Max Spools', '0')).strip() or '0') <= 1
        except (TypeError, ValueError):
            _one_slot = True
        is_toolhead = _one_slot and not any(h and h != target for h in _own_heads)

    # sid(str) -> why that spool did not move. Declared before the strict reads
    # and Smart Load, which can refuse the whole move; see the L298 Phase 3 note
    # at the write loop.
    failures: typing.Dict[str, str] = {}

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
    if not every_head_covered:
        unreadable = []
        here_count = 0
        for sid in spools:
            rec = spoolman_api.get_spool(sid)
            if not rec:
                unreadable.append(str(sid))
                continue
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

    residents: typing.List[typing.Any] = []
    if is_printer or is_toolhead:
        residents, refused = _strict_residents()
        if refused:
            return refused

    # Step 5. The heads the moving spools leave, the destination, and a named
    # slot's bound head (the auto-deploy chain loads it) are checked BEFORE any
    # Spoolman write, so the user is asked once, before anything moves, rather
    # than the chained call swallowing the answer. `confirm_active_print` is
    # True (covers every head), falsy (none) or the LocationIDs whose warning
    # the user saw.
    touched: typing.List[tuple] = [(head, 'source', sids) for head, sids in sources.items()]
    if not (all_here and not residents):
        touched.append((target, 'destination'))
    tgt_row = tgt_info
    # The bound head counts only when the chain will load it (I1-06): Return
    # parks a spool with auto_deploy=False, and must not ask about a head it
    # never touches.
    # A single-slot box's slot 1 binding records where its OWN spool is loaded
    # (the Group 20.2 lifecycle), not a feed, so it is never a feeds head and
    # never auto-deploys (Group 42.2).
    if (tgt_row and tgt_row.get('Type') == 'Dryer Box' and target_slot and auto_deploy
            and not locations_db._is_single_slot_dryer_box(tgt_row)):
        bound = locations_db.bindings_from_row(tgt_row)
        if str(target_slot).isdigit():
            bound_th = bound.get(str(target_slot)) or bound.get(str(int(target_slot)))
        else:
            bound_th = bound.get(str(target_slot))
        if bound_th and not locations_db.is_printer_sentinel(bound_th):
            touched.append((bound_th, 'feeds'))
    active_prints = _uncovered_active_heads(touched, confirm_active_print, printer_map, spools)
    if active_prints:
        return _requires_confirm_answer(active_prints, target, target_slot, residents)

    # Whether the CALLER named the slot, before auto-slot fills one in. The
    # pre-flight above probed only an explicit slot's bound toolhead, so only
    # then does the caller's confirm also cover the auto-deploy chain below.
    explicit_slot = bool(target_slot)

    # Auto-slot-pick: if the caller didn't specify a slot and the target is a
    # slotted container (Max Spools > 1) with at least one free slot, fill the
    # lowest-numbered free slot. Only fires for single-spool moves — in a bulk
    # move, a shared target_slot would make each spool unseat the previous
    # one, so a bulk slotless move stays slotless (rooms/shelves handle that
    # case correctly; slotted bulk moves should be explicit).
    tgt_info_auto = loc_info_map.get(target)
    if not target_slot and tgt_info_auto and len(spools) == 1:
        try:
            max_slots_auto = int(str(tgt_info_auto.get('Max Spools', '0')).strip() or '0')
        except (TypeError, ValueError):
            max_slots_auto = 0
        if max_slots_auto > 1:
            # Collect currently-occupied slot numbers at this target. Strictly
            # (Group 41 review): a fail-open read answered [] on a Spoolman blip,
            # so slot 1 was picked whoever held it, and the strict slot block
            # below then unseated that spool. Nothing has been written yet.
            try:
                existing_at_target = spoolman_api.get_spools_at_location_detailed_strict(target) or []
            except Exception as _pick_err:
                why = f"couldn't read {target} from Spoolman to pick a free slot ({_pick_err})"
                for sid in spools:
                    failures[str(sid)] = why
                state.add_log_entry(f"❌ Not moved to <b>{target}</b>: {why}", "ERROR", "ff4444")
                return {"status": "error", "msg": f"Not moved: {why}.", "failures": failures}
            occupied_slots = set()
            for existing in existing_at_target:
                # Skip the spool we're about to move — otherwise its own current slot
                # gets flagged as occupied and we miss the obvious re-slot case.
                if str(existing.get('id')) in [str(s) for s in spools]:
                    continue
                raw = str(existing.get('slot', '') or '').strip().strip('"')
                if raw and raw.isdigit():
                    occupied_slots.add(int(raw))
            # Pick lowest-numbered free slot.
            for i in range(1, max_slots_auto + 1):
                if i not in occupied_slots:
                    target_slot = str(i)
                    state.logger.info(
                        f"🪑 Auto-slot: {target} has free slot {i} — assigning spool there"
                    )
                    break
        elif locations_db._is_single_slot_dryer_box(tgt_info_auto):
            # Group 42.2: a single-slot box has one place, so its spool is in
            # slot 1. It used to be stored blank, which left a toolhead's
            # Quick-Swap tile for the box reading empty while its spool was
            # loaded. A spool already there is unseated to slotless (both still
            # sit in the box; a Max-1 box has never refused a second spool).
            target_slot = '1'

    # L298 Phase 0 — undo hardening: `extras` snapshots each moved spool's
    # system-managed extras (container_slot / physical_source /
    # physical_source_slot) as they were BEFORE the move, so perform_undo can
    # restore them — not just `location` — making an undo a TRUE rollback (the
    # spool returns to its exact slot + ghost state). Benefits single moves too;
    # a prerequisite for a trustworthy bulk-move undo.
    undo_record: typing.Dict[str, typing.Any] = {"target": target, "moves": {}, "extras": {}, "labels": {}, "ejections": {}, "ejection_extras": {}, "summary": f"Moved {len(spools)} -> {target}", "origin": origin}

    # Step 6 opens with a fresh strict list of the head (review engine-2): the
    # step-4 list was read BEFORE the source reads and the printer probe, which
    # take seconds when a printer is unreachable, and a spool another request
    # loads onto the head meanwhile must be unloaded too, or the head holds
    # two. The True path has no probe and no source reads, so it keeps one read.
    if (is_printer or is_toolhead) and not every_head_covered:
        residents, refused = _strict_residents()
        if refused:
            return refused

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
            # perform_smart_eject takes a boolean: covered when the confirm
            # covers the head this resident is unloaded from (Group 39.1).
            ejected = perform_smart_eject(
                rid, confirm_active_print=_confirm_covers(confirm_active_print, target),
                homeless_destination=homeless_dest,
            )
            if ejected is not True:
                stuck[rid] = _eject_refusal_reason(ejected)
                continue
            # Undo puts the resident back on this head, ghost trail included.
            undo_record['ejections'][rid] = target
            undo_record['ejection_extras'][rid] = {
                k: before_extra.get(k, '') for k in spoolman_api.SYSTEM_MANAGED_EXTRAS
            }
            # perform_smart_eject has already logged where it went.
            state.add_log_entry(f"⚠️ <b>Smart Load:</b> unloaded #{rid} from {target}", "WARNING")
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
            return {"status": "error", "msg": f"Not loaded: {target} still holds {held}.",
                    "failures": failures}

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
            unseat_failed = None
            for existing in existing_items:
                # A ghost (a spool deployed FROM this slot) is listed with its
                # trail's slot. Clearing its own container_slot never frees that
                # slot, and since 41.6 a failure of that pointless write refused
                # the incoming spool (Group 41 review), so ghosts are left alone.
                if existing.get('is_ghost'):
                    continue
                # [ALEX FIX] Improved comparison to catch string vs int mismatches
                if str(existing.get('slot', '')).strip('"') == str(target_slot) and existing['id'] != int(sid):
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
        new_extra['container_slot'] = str(target_slot) if target_slot else ""

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
            if is_already_here:
                new_extra['physical_source'] = existing_source
                new_extra['physical_source_slot'] = current_extra.get('physical_source_slot')
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
            if not current_source_meaningful:
                bound_box, bound_slot = _find_box_slot_feeding_toolhead(target, loc_list)
                # Never claim a slot another spool already holds, directly or as
                # its own ghost: the double claim made a later Return unseat that
                # spool (2026-09-12 review). No trail beats a false one.
                claimed_by = None
                if bound_box and bound_slot:
                    claimed_by = next((
                        o.get('id') for o in
                        (spoolman_api.get_spools_at_location_detailed(bound_box) or [])
                        if str(o.get('id')) != str(sid)
                        and str(o.get('slot', '')).strip('"') == str(bound_slot)), None)
                if bound_box and bound_slot and claimed_by is None:
                    new_extra['physical_source'] = bound_box
                    new_extra['physical_source_slot'] = bound_slot
                    state.logger.info(
                        f"🔗 Reverse-binding: toolhead {target} is fed by "
                        f"{bound_box} slot {bound_slot} — synthesizing ghost source."
                    )
                elif claimed_by is not None:
                    state.logger.info(
                        f"🔗 Reverse-binding skipped: {bound_box} slot {bound_slot} "
                        f"already holds Spool #{claimed_by}."
                    )

            if _move_write(sid, target, new_extra):
                state.add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
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
                slot_txt = f" [Slot {target_slot}]" if target_slot else ""
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

            if _move_write(sid, target, new_extra):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])
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
            _release_single_slot_box(sid, current_loc, current_extra, printer_map)

    # Group 41.4: record only what landed. A spool whose write was rejected, or
    # that was skipped (an unseat that failed, an unreadable slot), never moved,
    # so "undoing" it would move it from where it is to where it already is.
    # A move where nothing landed pushes no record at all.
    for _sid in [s for s in list(undo_record['moves']) if str(s) in failures]:
        for _key in ('moves', 'extras', 'labels'):
            undo_record[_key].pop(_sid, None)
    if undo_record['moves'] or undo_record['ejections']:
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
    bound_toolhead = None
    if (auto_deploy and target_slot and tgt_info and tgt_info.get('Type') == 'Dryer Box'
            and not locations_db._is_single_slot_dryer_box(tgt_info)):
        bindings = locations_db.bindings_from_row(tgt_info)
        bound_toolhead = bindings.get(str(target_slot))
        # PRINTER:<id> sentinels declare "this slot is staged for the named
        # printer's pool" — no toolhead is implied, so auto-deploy is a no-op.
        if bound_toolhead and locations_db.is_printer_sentinel(bound_toolhead):
            bound_toolhead = None
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
                    # Scoped confirms pass through as-is (Group 39.1): `confirm
                    # and explicit_slot` turned a head list into a blanket True.
                    confirm_active_print=confirm_active_print if explicit_slot else False,
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
    if auto_deployed:
        result["auto_deployed_to"] = str(bound_toolhead).upper()
    if auto_deploy_skipped:
        # sid(str) -> why it stayed in the box. The box placement itself stands.
        result["auto_deploy_skipped"] = auto_deploy_skipped
        result["auto_deploy_target"] = str(bound_toolhead).upper()
    return result


# ---------------------------------------------------------------------------
# L298 Bulk Moves — the shared plan/execute core (Phase 1 endpoint + Phase 2
# scan session both call these, so the two entries can never drift apart).
# ---------------------------------------------------------------------------

BULK_MOVE_SINGLE_OCC_MSG = ("{dest} is a single-spool location — bulk move needs a "
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
    single_occ_types = locations_db.TOOLHEAD_TYPES | {'Printer'}

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
    dest_type = dest_row.get('Type')

    # --- Pre-flight 2b: single-occupancy destination ------------------------
    # A Tool Head / MMU Slot / No MMU Direct Load / Printer holds ONE spool; a
    # bulk move onto it would chain-unseat every spool but the last.
    if dest in printer_map or (dest_type in single_occ_types):
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
        # single-occupancy feeds — never yank them in a bulk sweep.
        sp_loc = str(sp.get('location', '') or '').strip().upper()
        sp_type = (loc_info_map.get(sp_loc) or {}).get('Type')
        if sp_loc in printer_map or (sp_type in single_occ_types):
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
                        homeless_destination=None, report=None):
    """Remove `spool_id` from its current location.

    `homeless_destination`: where to send a spool with no saved home to return
    to ('' = Unassigned), for a caller that has already decided (Smart Load).
    It skips the protected-unassign prompt. None keeps the interactive
    behaviour: "REQUIRE_CONFIRM" for a spool with no saved home.

    `report` (Group 42.5a): a dict the caller passes in; on success it is filled
    with {"from", "to", "slot", "home", "released_boxes"} so the eject can say
    where the spool went and which single-slot box let go of the head. The
    return contract below does not change (callers test `is True`).

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

    def _landed(to_loc, slot, home):
        """The eject's write landed. Release the spool's OWN single-slot box from
        the head it left (Group 42.1: only after the write, so a refused or
        rejected eject leaves it bound; and keyed on the spool, so ejecting a
        different spool from a doubled head no longer unbinds it), write ONE
        Activity Log sentence that says both (Derek, 2026-10-13: "a full
        sentence in the activity log"), and fill the caller's report (42.5a)."""
        released = _release_single_slot_box(spool_id, current_location, pre_extra, printer_map, log=False)
        from_txt = current_location or "Unassigned"
        if home:
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

    # [ALEX FIX] Explicitly overwrite the slot with empty string.
    # .pop() just removes the key, which causes PATCH to ignore it (keeping the old value).
    extra['container_slot'] = ""

    # Where it goes: its saved home, else the homeless fallback (Group 39.6's
    # _eject_destination, which the eject route's combined confirm also runs).
    dest = _eject_destination(spool_data, printer_map, homeless_destination)
    saved_source = dest['home']

    if saved_source:
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
            else:
                extra['container_slot'] = saved_slot_clean
            extra['physical_source_slot'] = ""
        else:
            extra['container_slot'] = ""
            
        # Clear the source memory so we don't bounce back again later
        extra['physical_source'] = "" 
        
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
    for sid in list((record.get('moves') or {}).keys()) + list((record.get('ejections') or {}).keys()):
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
        Group 42.3b, I5-10, for a moved spool). Logged at ERROR."""
        if not loc or not _is_single_occupancy(loc, printer_map, undo_rows):
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

    def _reattach(loc, snap):
        """Group 42.3b: a spool put back onto a head brings its own single-slot
        box back with it (its snapshot trail), as the forward move attached it."""
        head = str(loc or '').strip().strip('"').upper()
        box = str((snap or {}).get('physical_source') or '').strip().strip('"').upper()
        if not head or head not in printer_map or not box:
            return
        try:
            _att, _detail = locations_db.attach_single_slot_box_to_toolhead(box, head)
            if _att and _detail != "already attached":
                state.add_log_entry(f"🔗 Undo: {box} attached to {head} again — its spool is back on the head",
                                    "INFO")
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
            # ...and going back onto one brings it back.
            _reattach(loc, snap)
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
            _reattach(original_loc, snap)
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            failed.append(f"#{ejected_sid} ({err})")
            state.add_log_entry(
                f"❌ Undo: failed to restore ejected Spool #{ejected_sid} → "
                f"{original_loc or 'UNASSIGNED'}: {err}", "ERROR", "ff4444")

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
    if not moves and not ejections:
        # Legacy / no-move record: its summary already reads "Moved N -> target".
        parts.append(last.get('summary', f"moved -> {target}"))
    if parts:
        state.add_log_entry(f"↩️ Undo: {'; '.join(parts)}", "WARNING")
    if failed:
        msg = f"Undo could not put back {', '.join(failed)}."
        state.add_log_entry(f"⚠️ Undo partly failed: {msg}", "ERROR", "ff4444")
        return {"success": False, "msg": msg, "restored": restored + restored_ejections}
    return {"success": True, "msg": f"↩️ Undo: {'; '.join(parts)}" if parts else "↩️ Undone",
            "restored": restored + restored_ejections}

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


def find_spool_in_slot(box_loc_id, slot):
    """Return the spool id sitting in (box_loc_id, slot), or None.

    Scans items at the location (including ghost items whose
    physical_source points back to this box) and matches the slot
    string loosely (Spoolman stores container_slot with JSON-string
    quoting — see spoolman_api.parse_inbound_data).
    """
    if not box_loc_id or not str(slot).strip():
        return None
    wanted = str(slot).strip().strip('"')
    items = spoolman_api.get_spools_at_location_detailed(box_loc_id) or []
    # Group 42.2: a single-slot box's lone spool is in slot 1 even when its slot
    # was stored blank (a legacy PolyDryer row), so Quick-Swap can find it.
    box_up = str(box_loc_id).strip().upper()
    row = next((r for r in (locations_db.load_locations_list() or [])
                if isinstance(r, dict) and str(r.get('LocationID', '')).strip().upper() == box_up), None)
    for item in items:
        if locations_db.effective_slot(row, item.get('slot', ''), occupants=len(items)) == wanted:
            return int(item['id'])
    return None