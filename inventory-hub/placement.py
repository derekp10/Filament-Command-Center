"""Group 40.1 — the placement model behind the slot picker.

Derek's D2 / D3 / D5 decisions (2026-09-13) put one picker in front of every
door that places a spool without naming a slot or a head: a multi-slot box's
own label, Force Location, `LOC:XL`, Return with no usable slot, and the
wizard. This module builds what that picker shows. It writes nothing.

  box      a Dryer Box with Max Spools > 1: each slot's spool, the toolhead it
           feeds and what that head runs now, and the ⭐ recommendation;
  printer  a Printer row: its heads (what each runs, which box slots feed it)
           and its Printer Pool slots;
  return   box mode for the box a head's spool goes back to, with the D5
           recommendation (Return, 40.6).

Read once and strictly: one GET of the spool list
(spoolman_api.get_all_spools_strict), bucketed per location by the matcher
every grid uses (spoolman_api.bucket_spools_by_location). A Spoolman blip
answers `read_ok: false`, so the picker says it couldn't read Spoolman instead
of drawing a box of empty slots. A head's residents are the spools whose OWN
record is on it, never the flat prefix hits or ghosts, so Group 37's matcher
change can't move what the picker shows. No printer probe: the picker opens at
once and asks each printer itself (/api/printer_state).

The ⭐ is logic.recommend_box_slot over logic.box_slot_claims and
logic.slot_would_prompt, the rule the engine's auto-slot uses (40.0e), read the
same way, so the slot the picker stars is the slot a slotless move would take.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import typing

import state  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore


RECOMMEND_TEXT = {
    # box mode: logic.recommend_box_slot's reasons
    'own_slot': "the slot it already sits in",
    'no_prompt': "the lowest free slot that loads no busy toolhead",
    'lowest_empty': "the lowest free slot",
    'full': "every slot is taken",
    # return mode (D5)
    'recorded_slot': "the slot it came from",
    'head_slot': "the free slot that feeds {head}",
    'spare_slot': "a free slot that feeds no toolhead",
    'no_free_slot': "no free slot fits, so it would go in without a slot",
    # printer mode (D3: pre-select only when exactly one free option exists)
    'only_free': "the only free choice",
    'several_free': "",
    'nothing_free': "every toolhead and Printer Pool slot holds a spool",
}


def _u(v):
    return str(v if v is not None else '').strip().strip('"').upper()


def _bound(v):
    """A slot binding the way the engine reads it (logic._feed_token's rule, Group
    40.3 fix check, E2): a hand-edited "None" / "null" is unbound, and quotes
    with spaces inside them are trimmed. A PRINTER:<id> pool sentinel is kept."""
    t = str(v if v is not None else '').strip().strip('"').strip().upper()
    return '' if t in ('NONE', 'NULL') else t


def _max_slots(row):
    try:
        return int(str((row or {}).get('Max Spools', '0')).strip() or '0')
    except (TypeError, ValueError):
        return 0


def _card(item):
    """A spool as a picker tile shows it: the grid's own item fields."""
    if not item:
        return None
    return {
        "id": item.get('id'),
        "display": item.get('display') or f"#{item.get('id')}",
        "color": item.get('color'),
        "color_direction": item.get('color_direction') or 'longitudinal',
        "remaining_weight": item.get('remaining_weight'),
        "details": item.get('details') or {},
        "archived": bool(item.get('archived')),
        "is_ghost": bool(item.get('is_ghost')),
        "deployed_to": item.get('deployed_to') or None,
    }


def _direct(items, loc_id, exclude=()):
    """The bucket items whose OWN record is at `loc_id`: no ghosts (a trail
    naming it), no first-segment prefix hits (a Printer row's heads)."""
    lid = _u(loc_id)
    skip = {str(x) for x in (exclude or ())}
    return [i for i in (items or []) if not i.get('is_ghost') and _u(i.get('location')) == lid
            and str(i.get('id')) not in skip]


def _resident(item, head, raw_by_id, printer_map, loc_list, loc_info_map):
    """A spool running on `head`, with where it came from ("XL-1 runs #99 (from
    PM-DB-2)"), worded by the same helper as the "already running" question."""
    card = _card(item)
    rec = raw_by_id.get(str(item.get('id')))
    card.update({"from": "", "trail": None})
    if rec:
        try:
            fed = logic._fed_resident(rec, head, printer_map, loc_list, loc_info_map)
            card.update({"from": fed.get('from') or '', "trail": fed.get('trail')})
        except Exception as e:   # the line is a courtesy; never fail the model on it
            state.logger.warning(f"placement: couldn't word #{item.get('id')}'s origin on {head}: {e}")
    return card


def _printer_prefixes(printer_id, loc_list):
    """The PRINTER:<id> sentinel suffixes that mean this printer: its heads'
    prefixes (validate_slot_targets' rule) and the row's own id."""
    pid = _u(printer_id)
    out = {pid} if pid else set()
    for h in locations_db.printer_row_toolheads(loc_list, pid):
        out.add(h.split('-', 1)[0] if '-' in h else h)
    return out


def _printer_label(printer_id, loc_info_map, printer_map):
    """A printer's display name from its id or a pool sentinel's suffix."""
    pid = _u(printer_id)
    row = loc_info_map.get(pid)
    if isinstance(row, dict) and str(row.get('Type', '')).strip().lower() == 'printer':
        return str(row.get('Name') or pid)
    for key, info in (printer_map or {}).items():
        k = _u(key)
        if (k.split('-', 1)[0] if '-' in k else k) == pid and (info or {}).get('printer_name'):
            return str(info.get('printer_name'))
    return pid


def _slot_feed(row, slot, printer_map, loc_info_map, moving_from):
    """What `slot` feeds, as a tile names it: a toolhead, a Printer Pool, a
    binding to something that isn't a head (the chain would still move the
    spool there; the tile says so), or None (a storage slot)."""
    raw = None
    for key, bound in locations_db.bindings_from_row(row).items():
        if logic._norm_slot(key) == slot:
            raw = bound
            break
    target = _bound(raw)
    if not target:
        return None
    if locations_db.is_printer_sentinel(target):
        pid = target.split(':', 1)[1]
        return {"kind": "pool", "printer": pid,
                "printer_name": _printer_label(pid, loc_info_map, printer_map)}
    if logic._holds_one_spool(target, printer_map, loc_info_map):
        info = (printer_map or {}).get(target) or {}
        return {"kind": "toolhead", "id": target,
                "printer": str(info.get('printer_name') or target),
                "position": info.get('position'),
                # The spool sits on this head now: the move stores it, not loads it.
                "is_source": bool(moving_from) and target == moving_from}
    return {"kind": "other", "id": target}


def _unreadable(model, err):
    model.update({"read_ok": False,
                  "read_error": f"couldn't read Spoolman ({err})",
                  "recommended": None, "recommend_reason": None, "recommend_text": ""})
    state.logger.warning(f"placement options for {model.get('location')}: Spoolman unreadable ({err})")
    return model


def _spool_line(rec):
    if not rec:
        return None
    try:
        return spoolman_api.format_spool_display(rec).get('text') or f"#{rec.get('id')}"
    except Exception:
        return f"#{rec.get('id')}"


def _box_model(row, box, sid, toolhead, mode, loc_list, loc_info_map, printer_map):
    max_slots = _max_slots(row)
    extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
    order = 'rtl' if str(extra.get('slot_order') or '').strip().lower() == 'rtl' else 'ltr'
    slot_ids = [str(i) for i in range(1, max_slots + 1)]
    model: typing.Dict[str, typing.Any] = {
        "mode": mode, "location": box, "name": row.get('Name') or box, "type": row.get('Type'),
        "spool": sid, "spool_display": None, "spool_location": "",
        "toolhead": _u(toolhead) or None,
        "read_ok": True, "read_error": None,
        "max_slots": max_slots, "slot_order": order,
        "slots": [], "unslotted": [], "printers": [],
        "allow_none": mode == 'return',
        "recommended": None, "recommend_reason": None, "recommend_text": "",
    }
    # Every one-spool target a slot is bound to: printer_map heads, and any other
    # toolhead-type row (slot_would_prompt reads those too).
    heads: typing.List[str] = []
    for s in slot_ids:
        h = logic._slot_binding(row, s)
        if h and h not in heads and logic._holds_one_spool(h, printer_map, loc_info_map):
            heads.append(h)
    try:
        spools = spoolman_api.get_all_spools_strict()
    except Exception as e:
        return _unreadable(model, e)
    raw_by_id = {str(s.get('id')): s for s in (spools or []) if isinstance(s, dict)}
    buckets = spoolman_api.bucket_spools_by_location([box] + heads, spools=spools)
    in_box = buckets.get(box, [])
    moving = [sid] if sid is not None else []
    moving_ids = {str(m) for m in moving}
    claims, own_slot, ghost_slot = logic.box_slot_claims(row, box, in_box, moving)
    mover = raw_by_id.get(str(sid)) if sid is not None else None
    if sid is not None and mover is None:
        mover = logic._spool_record(sid)   # an archived spool isn't in the list
    moving_from = _u((mover or {}).get('location'))
    model["spool_display"] = _spool_line(mover)
    model["spool_location"] = moving_from
    residents = {h: _direct(buckets.get(h), h, exclude=moving) for h in heads}

    # Slots in the grid's own order (1..max; the picker reverses an rtl box).
    holders: typing.Dict[str, typing.List[dict]] = {}
    unslotted = []
    for item in in_box:
        # A multi-slot box reads every slot as stored (the one slot rule, 42.2).
        s = logic._norm_slot(locations_db.effective_slot(row, item.get('slot', ''), occupants=len(in_box)))
        if s in slot_ids:
            holders.setdefault(s, []).append(item)
        elif str(item.get('id')) not in moving_ids:
            # The other spools in the box with no slot (or one past Max Spools),
            # as the grid's Unslotted list shows them.
            unslotted.append(_card(item))
    printers_seen: typing.Dict[str, str] = {}
    for s in slot_ids:
        items = holders.get(s, [])
        mine = [i for i in items if str(i.get('id')) in moving_ids]
        others = [i for i in items if str(i.get('id')) not in moving_ids]
        # A direct occupant before a deployed one, as the grid shows it.
        shown = sorted(others, key=lambda i: bool(i.get('is_ghost')))
        feed = _slot_feed(row, s, printer_map, loc_info_map, moving_from)
        if feed and feed['kind'] == 'toolhead':
            feed['residents'] = [_resident(i, feed['id'], raw_by_id, printer_map, loc_list, loc_info_map)
                                 for i in residents.get(feed['id'], [])]
            if feed['printer'] not in printers_seen:
                printers_seen[feed['printer']] = feed['id']
        free = s not in claims
        model["slots"].append({
            "slot": s,
            "spool": _card(shown[0]) if shown else None,
            # More than one spool claims it (the grid shows the rest unslotted).
            "claimants": [i.get('id') for i in shown],
            "current": bool(mine),
            "free": free,
            "feeds": feed,
            "would_prompt": bool(free and logic.slot_would_prompt(
                row, s, moving_from, printer_map, loc_info_map, lambda h: residents.get(h, []))),
        })
    model["unslotted"] = unslotted
    model["printers"] = [{"name": n, "head": h} for n, h in printers_seen.items()]

    if mode == 'return':
        pick, why = _return_recommendation(row, slot_ids, claims, ghost_slot, toolhead, loc_list, printer_map)
        model["recommended"] = {"kind": "slot", "box": box, "slot": pick} if pick else {"kind": "none", "box": box}
        model["recommend_reason"] = why
        model["recommend_text"] = RECOMMEND_TEXT.get(why, "").format(head=_u(toolhead))
        return model
    pick, why = logic.recommend_box_slot(
        max_slots, claims, own_slot,
        lambda s: logic.slot_would_prompt(row, s, moving_from, printer_map, loc_info_map,
                                          lambda h: residents.get(h, [])))
    model["recommended"] = {"kind": "slot", "box": box, "slot": pick} if pick else None
    model["recommend_reason"] = why
    model["recommend_text"] = RECOMMEND_TEXT.get(why, "")
    return model


def _return_recommendation(row, slot_ids, claims, ghost_slot, toolhead, loc_list, printer_map):
    """D5: the slot it came from while free; else a free slot bound to the head
    it leaves (`toolhead`); else a free Printer Pool slot of that head's printer
    or a free unbound slot; else none (no slot). Returns (slot or None, why)."""
    free = [s for s in slot_ids if s not in claims]
    if ghost_slot and ghost_slot in free:
        return ghost_slot, 'recorded_slot'
    th = _u(toolhead)
    for s in free:
        if th and logic._slot_binding(row, s) == th:
            return s, 'head_slot'
    owner = locations_db.printer_owning_toolhead(loc_list, th) if th else None
    pool_ids = _printer_prefixes(owner, loc_list) if owner else set()
    targets = {logic._norm_slot(k): _bound(v) for k, v in locations_db.bindings_from_row(row).items()}
    for s in free:
        t = targets.get(s, '')
        if not t or (locations_db.is_printer_sentinel(t) and t.split(':', 1)[1] in pool_ids):
            return s, 'spare_slot'
    return None, 'no_free_slot'


def _printer_model(row, printer_id, sid, loc_list, loc_info_map, printer_map):
    pid = _u(printer_id)
    heads = locations_db.printer_row_toolheads(loc_list, pid)
    name = str(row.get('Name') or pid)
    model: typing.Dict[str, typing.Any] = {
        "mode": "printer", "location": pid, "name": name, "type": row.get('Type'),
        "spool": sid, "spool_display": None, "spool_location": "",
        "read_ok": True, "read_error": None,
        # A dual-role printer that is its own (only) head, the old Core One: the
        # Printer picker skips the head list (40.5).
        "self_head": pid in (printer_map or {}),
        "heads": [], "pool": [],
        "printers": [{"name": name, "head": heads[0]}] if heads else [],
        "msg": "" if heads else logic.printer_row_refusal(pid, row, loc_list),
        "recommended": None, "recommend_reason": None, "recommend_text": "",
    }
    # Feeds per head (multi-slot boxes only: a single-slot box never feeds,
    # 42.1 step 5) and the Printer Pool (PRINTER:<id> sentinel slots).
    feeds = {h: logic._feed_slots_for(h, loc_list) for h in heads}
    prefixes = _printer_prefixes(pid, loc_list)
    pool: typing.List[typing.Tuple[str, str]] = []
    for r in loc_list or []:
        if not isinstance(r, dict) or r.get('Type') != locations_db.DRYER_BOX_TYPE:
            continue
        if locations_db._is_single_slot_dryer_box(r):
            continue
        for slot, target in locations_db.bindings_from_row(r).items():
            t = _bound(target)
            if t and locations_db.is_printer_sentinel(t) and t.split(':', 1)[1] in prefixes:
                pool.append((_u(r.get('LocationID')), logic._norm_slot(slot)))
    boxes = []
    for b in [b for fs in feeds.values() for b, _ in fs] + [b for b, _ in pool]:
        if b not in boxes:
            boxes.append(b)
    if not heads and not pool:
        return model
    try:
        spools = spoolman_api.get_all_spools_strict()
    except Exception as e:
        return _unreadable(model, e)
    raw_by_id = {str(s.get('id')): s for s in (spools or []) if isinstance(s, dict)}
    buckets = spoolman_api.bucket_spools_by_location(list(heads) + boxes, spools=spools)
    moving = [sid] if sid is not None else []
    mover = raw_by_id.get(str(sid)) if sid is not None else None
    if sid is not None and mover is None:
        mover = logic._spool_record(sid)
    model["spool_display"] = _spool_line(mover)
    model["spool_location"] = _u((mover or {}).get('location'))

    moving_ids = {str(m) for m in moving}

    def _slot_holders(box, slot):
        items = [i for i in buckets.get(box, []) if str(i.get('id')) not in moving_ids]
        brow = loc_info_map.get(box)
        return [i for i in items if logic._norm_slot(locations_db.effective_slot(
            brow, i.get('slot', ''), occupants=len(items))) == slot]

    free_options = []
    for h in heads:
        res = _direct(buckets.get(h), h, exclude=moving)
        entry_feeds = []
        for box, slot in feeds.get(h, []):
            held = sorted(_slot_holders(box, logic._norm_slot(slot)), key=lambda i: bool(i.get('is_ghost')))
            entry_feeds.append({"box": box, "slot": logic._norm_slot(slot),
                                "spool": _card(held[0]) if held else None,
                                "claimed_by": held[0].get('id') if held else None,
                                "free": not held})
        entry = {"id": h, "position": ((printer_map or {}).get(h) or {}).get('position'),
                 "resident": None, "residents": [],
                 "current": model["spool_location"] == h, "feeds": entry_feeds}
        if res:
            entry["residents"] = [_resident(i, h, raw_by_id, printer_map, loc_list, loc_info_map) for i in res]
            entry["resident"] = entry["residents"][0]
        elif not entry["current"]:
            # The head the spool already sits on is where it is now, never a
            # free choice for it (Group 40.3 review, D8: it was starred as "the
            # only free choice", and Enter re-scanned it onto its own head).
            free_options.append({"kind": "head", "head": h})
        model["heads"].append(entry)
    # The Printer Pool slot the spool already sits in is where it is now, never a
    # free choice for it either (Group 40.3 fix check, D8).
    mover_slot = logic._norm_slot(str(((mover or {}).get('extra') or {}).get('container_slot') or '').strip('"'))
    for box, slot in pool:
        held = sorted(_slot_holders(box, slot), key=lambda i: bool(i.get('is_ghost')))
        current = bool(mover_slot) and model["spool_location"] == box and mover_slot == slot
        model["pool"].append({"box": box, "slot": slot, "spool": _card(held[0]) if held else None,
                              "free": not held, "current": current})
        if not held and not current:
            free_options.append({"kind": "pool", "box": box, "slot": slot})
    if len(free_options) == 1:
        model["recommended"], why = free_options[0], 'only_free'
    else:
        why = 'nothing_free' if not free_options else 'several_free'
    model["recommend_reason"] = why
    model["recommend_text"] = RECOMMEND_TEXT.get(why, "")
    return model


def build_placement_options(location, spool=None, toolhead=None, mode=None):
    """The placement model for `location` (see the module docstring), as
    (model, http_status). `spool`: the spool being placed (for the ⭐, its
    current slot and the tile titles). `toolhead` + `mode='return'`: the head a
    Return empties, for the D5 recommendation. Errors: 404 for an unknown
    location, 400 for a location no picker opens on (a toolhead, a single-slot
    box, a shelf) or a return without a multi-slot box."""
    loc = _u(location)
    loc_list = locations_db.load_locations_list() or []
    loc_info_map = {_u(r.get('LocationID')): r for r in loc_list if isinstance(r, dict)}
    printer_map = locations_db.get_active_printer_map(loc_list)
    row = loc_info_map.get(loc)
    if not loc or not isinstance(row, dict):
        return {"error": "not_found", "location": loc,
                "msg": f"{loc or 'That location'} isn't in the location list."}, 404
    sid: typing.Optional[int] = None
    if spool not in (None, ''):
        try:
            sid = int(str(spool).strip())
        except (TypeError, ValueError):
            return {"error": "bad_spool", "location": loc, "msg": f"'{spool}' isn't a spool number."}, 400
    want = str(mode or '').strip().lower()
    is_multi_box = row.get('Type') == locations_db.DRYER_BOX_TYPE and _max_slots(row) > 1
    if want == 'return':
        if not is_multi_box:
            return {"error": "not_pickable", "location": loc, "type": row.get('Type'),
                    "msg": f"{loc} isn't a box with slots to return a spool into."}, 400
        return _box_model(row, loc, sid, toolhead, 'return', loc_list, loc_info_map, printer_map), 200
    if want not in ('', 'box', 'printer'):
        return {"error": "bad_mode", "location": loc, "msg": f"Unknown picker mode '{mode}'."}, 400
    if is_multi_box and want in ('', 'box'):
        return _box_model(row, loc, sid, toolhead, 'box', loc_list, loc_info_map, printer_map), 200
    if str(row.get('Type', '')).strip().lower() == 'printer' and want in ('', 'printer'):
        return _printer_model(row, loc, sid, loc_list, loc_info_map, printer_map), 200
    return {"error": "not_pickable", "location": loc, "type": row.get('Type'),
            "msg": f"{loc} doesn't need a picker: a spool goes straight there."}, 400
