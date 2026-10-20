"""Per-filament stock (Group 49.2): the ⚠️ Low-stock list and the one Activity
Log warning when a write takes a filament under the line.

Stock is counted per FILAMENT: all of its in-stock spools added up. A spool is
in stock when it isn't archived and has grams left (remaining > 0). A spool
whose remaining Spoolman can't work out (no weight on the spool or its
filament) still counts as in stock, with unknown grams: FCC can't call it
empty, and a filament holding one is never judged low.

  low  a filament with stock whose in-stock spools add up to less than
       `low_stock_g` grams (config, ⚙️ Behavior, default 250);
  out  a filament with spools on record but none in stock. A filament with no
       spools at all was never stocked and is never listed. A filament tagged
       with a "One-off" attribute (any case, with or without the dash or a
       space) is one Derek won't rebuy: it stays off "out" (it can still be
       low, with its tag showing, so he can see why it won't be on "out").

The list (`build_report`, behind GET /api/stock_report, routes_inventory.py)
reads Spoolman ONCE and strictly, every spool with the archived ones
(`spoolman_api.get_all_spools_strict(allow_archived=True)`): the fail-open
`get_all_spools` answers [] on a blip, which would read as "everything is out".
A read that fails raises StockReadError, and the route answers an error, never
an empty list. Each spool carries its full filament record (Spoolman nests the
same record /api/v1/filament returns: all 257 spools on dev matched on
2026-10-19), and a filament with no spools is never listed, so the filament
list needs no second read. It runs only when the panel opens, never on the
dashboard heartbeat.

The warning (`check_after_deduct`, `check_after_weight_change`) logs ONE
Activity Log WARNING per filament when a write takes it across a line:
  - from at or above `low_stock_g` to under it, with stock left:
    "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools";
  - from in stock to none in stock (its last spool emptied: the 0 g
    auto-archive): "⚠️ ... is out: #99 was its last spool in stock". Not for a
    One-off filament.
A filament already under the line stays quiet until it runs out, so a print on
a low filament doesn't log every time, and the same warning for one filament is
logged once a minute at most (two writes landing together can each see the
crossing). "Before" is the written spool's own grams before and after the write
plus the filament's other in-stock spools, from one strict read of that
filament's spools after the write.

It never gets in the way of the write that called it: it is called only after
the write landed (for a print, after the exactly-once ledger write, so a crash
can never re-run a deduct), it runs on its own thread (`_RUN_ASYNC`; tests turn
that off), and any failure logs a debug line and nothing else. It also says
nothing when the fresh read doesn't show the spool where the write left it
(another write came in between): a guess is worse than silence.

Python 3.9 runtime (the container image): keep syntax 3.9-safe.
"""
import html
import math
import threading
import time
from urllib.parse import quote

import requests  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import spoolman_api  # type: ignore

DEFAULT_LOW_STOCK_G = 250.0

# An attribute that marks a filament Derek won't rebuy, compared on its letters
# and digits only, lower-cased: "One-off", "One Off" and "oneoff" all match.
NO_REBUY_TAGS = frozenset({"oneoff"})

# How far (grams) the fresh read of a just-written spool may sit from where the
# write left it before the warning gives up: further means something else wrote
# to it in between, so the before/after can't be trusted.
_MATCH_G = 0.5

_READ_TIMEOUT = 5

# The warning check runs on its own short-lived thread so it never delays the
# deduct or the weight write. Tests set this False to run it inline.
_RUN_ASYNC = True

# One warning per crossing: two writes to one filament landing together (a
# print's deduct and a weigh-out) each read the other's write too, and both
# could see the same crossing. The same warning for the same filament within
# _REPEAT_S is logged once. {(filament id, "low" | "out"): time.monotonic()}.
_REPEAT_S = 60.0
_RECENT = {}
_RECENT_LOCK = threading.Lock()


class StockReadError(Exception):
    """Spoolman couldn't be read: a blip, an HTTP error, or an answer that isn't
    a spool list. The Low-stock list answers an error, never an empty list."""


# --- settings ----------------------------------------------------------------

def _threshold_from(cfg):
    try:
        v = float((cfg or {}).get('low_stock_g', DEFAULT_LOW_STOCK_G))
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_LOW_STOCK_G
    return v if math.isfinite(v) and v >= 0 else DEFAULT_LOW_STOCK_G


def low_stock_g():
    """The `low_stock_g` setting (grams): the default for a missing, broken or
    negative value, as `print_deduct._shortfall_review_min_g` does."""
    try:
        return _threshold_from(config_loader.load_config())
    except Exception:
        return DEFAULT_LOW_STOCK_G


# --- one spool, one filament ---------------------------------------------------

def _num(v):
    """A finite float, or None (bools are not weights)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def remaining_g(spool):
    """A spool's remaining grams: Spoolman's `remaining_weight`, else its
    effective capacity (its own initial weight, else its filament's) minus what
    it used. None when unknown."""
    if not isinstance(spool, dict):
        return None
    rem = _num(spool.get('remaining_weight'))
    if rem is not None:
        return rem
    cap = spoolman_api.effective_initial_weight(spool)
    if cap is None:
        return None
    return cap - (_num(spool.get('used_weight')) or 0.0)


def in_stock(spool):
    """Not archived, with grams left (or an unknown remaining: FCC can't call
    that spool empty)."""
    if not isinstance(spool, dict) or spool.get('archived'):
        return False
    rem = remaining_g(spool)
    return rem is None or rem > 0


def stock_of(spools):
    """(grams, in-stock spools, in-stock spools with unknown grams)."""
    grams, count, unknown = 0.0, 0, 0
    for s in spools or []:
        if not in_stock(s):
            continue
        count += 1
        rem = remaining_g(s)
        if rem is None:
            unknown += 1
        else:
            grams += rem
    return grams, count, unknown


def _fid_of(spool):
    fil = spool.get('filament') if isinstance(spool, dict) else None
    if not isinstance(fil, dict):
        return None
    try:
        return int(fil.get('id'))
    except (TypeError, ValueError):
        return None


def _text(v, default=''):
    s = str(v).strip().strip('"').strip() if v is not None else ''
    return s or default


def _dict(v):
    return v if isinstance(v, dict) else {}


def filament_names(fil):
    """(brand, material, colour) as the spool cards print them
    (format_spool_display): the vendor, else Generic; the material in capitals,
    else PLA; the colour name (original_color, else the filament's name) in
    title case, else Unknown."""
    fil = _dict(fil)
    extra = _dict(fil.get('extra'))
    brand = _text(_dict(fil.get('vendor')).get('name'), 'Generic')
    material = _text(fil.get('material'), 'PLA').upper()
    colour = _text(extra.get('original_color')) or _text(fil.get('name'), 'Unknown')
    return brand, material, colour.title()


def is_one_off(attrs):
    """True when one of a filament's attributes marks it as never rebought."""
    for a in attrs or []:
        if ''.join(ch for ch in str(a).lower() if ch.isalnum()) in NO_REBUY_TAGS:
            return True
    return False


def _colours(fil):
    """The filament's colour string (multi_color_hexes, else color_hex) and its
    direction, as the cards pass them to getFilamentStyle."""
    fil = _dict(fil)
    hexes = fil.get('multi_color_hexes') or fil.get('color_hex') or ''
    direction = (fil.get('multi_color_direction')
                 or _dict(fil.get('extra')).get('multi_color_direction') or 'longitudinal')
    return str(hexes), str(direction)


def _is_web_link(url):
    return str(url).lower().startswith(('http://', 'https://'))


def _encode(v):
    # JavaScript's encodeURIComponent, which the details windows use.
    return quote(str(v), safe="!~*'()")


def buy_url(fil, template=''):
    """The filament window's Buy More rule (inv_details.js): the filament's own
    purchase_url when it is a web link, else `buy_more_url_template` (config)
    with {{vendor}}, {{material}} and {{color}} filled in, else None. Only an
    http(s) link is ever answered."""
    fil = _dict(fil)
    extra = _dict(fil.get('extra'))
    own = _text(extra.get('purchase_url'))
    if _is_web_link(own):
        return own
    template = str(template or '').strip()
    if not template:
        return None
    url = (template
           .replace('{{vendor}}', _encode(_dict(fil.get('vendor')).get('name') or 'Generic'))
           .replace('{{material}}', _encode(fil.get('material') or 'PLA'))
           .replace('{{color}}', _encode(extra.get('original_color') or fil.get('name') or '')))
    return url if _is_web_link(url) else None


# --- the list -------------------------------------------------------------------

def _row(fid, fil, grams, count, total, template):
    brand, material, colour = filament_names(fil)
    attrs = spoolman_api.filament_attribute_list(fil)
    hexes, direction = _colours(fil)
    return {
        "filament_id": fid,
        "brand": brand,
        "material": material,
        "color_name": colour,
        "display": f"{brand} - {material} - {colour}",
        "color": hexes,
        "color_direction": direction,
        "grams": round(grams, 1),
        "spools": count,            # in stock
        "spools_total": total,      # every spool on record, archived ones too
        "attributes": attrs,
        "one_off": is_one_off(attrs),
        "buy_url": buy_url(fil, template),
    }


def build_report():
    """The ⚠️ Low-stock list: {success, threshold_g, low, out, filaments,
    spools}. `low` runs from the fewest grams up; `out` is by name. Raises
    StockReadError when Spoolman can't be read."""
    try:
        cfg = config_loader.load_config() or {}
    except Exception:
        cfg = {}
    threshold = _threshold_from(cfg)
    template = cfg.get('buy_more_url_template') or ''
    try:
        spools = spoolman_api.get_all_spools_strict(allow_archived=True)
    except Exception as e:
        raise StockReadError(str(e) or e.__class__.__name__)
    if not isinstance(spools, list):
        raise StockReadError("Spoolman's answer wasn't a spool list")

    by_fid = {}
    for s in spools:
        fid = _fid_of(s)
        if fid is None:
            continue
        entry = by_fid.setdefault(fid, {"fil": s.get('filament'), "spools": []})
        entry["spools"].append(s)

    low, out = [], []
    for fid, entry in by_fid.items():
        grams, count, unknown = stock_of(entry["spools"])
        if count == 0:
            row = _row(fid, entry["fil"], 0.0, 0, len(entry["spools"]), template)
            if not row["one_off"]:
                out.append(row)
        elif not unknown and grams < threshold:
            low.append(_row(fid, entry["fil"], grams, count, len(entry["spools"]), template))
    low.sort(key=lambda r: (r["grams"], r["display"].lower(), r["filament_id"]))
    out.sort(key=lambda r: (r["display"].lower(), r["filament_id"]))
    return {"success": True, "threshold_g": threshold, "low": low, "out": out,
            "filaments": len(by_fid), "spools": len(spools)}


# --- the warning ------------------------------------------------------------------

def _debug(msg):
    try:
        state.logger.debug(f"49.2b low-stock check: {msg}")
    except Exception:
        pass


def _get_json(path):
    sm_url, _ = config_loader.get_api_urls()
    resp = requests.get(f"{sm_url}{path}", timeout=_READ_TIMEOUT)
    resp.raise_for_status()
    return spoolman_api.parse_inbound_data(resp.json())


def _spool_strict(sid):
    sid = int(sid)
    rec = _get_json(f"/api/v1/spool/{sid}")
    if not isinstance(rec, dict) or str(rec.get('id')) != str(sid):
        raise StockReadError(f"Spoolman's answer for #{sid} wasn't that spool")
    return rec


def _filament_spools_strict(fid):
    """Every spool of filament `fid`, archived ones too: one strict read.
    Spoolman 0.27 honours `filament.id` (checked read-only on dev 2026-10-19: it
    answered exactly that filament's spools, the archived ones only with
    allow_archived), and FCC filters again anyway: Spoolman silently ignores a
    filter it doesn't know (its `extra=` filters are ignored), so a filter is
    never trusted on its own."""
    fid = int(fid)
    data = _get_json(f"/api/v1/spool?filament.id={fid}&allow_archived=true")
    if not isinstance(data, list):
        raise StockReadError(f"Spoolman's answer for filament {fid} wasn't a spool list")
    return [s for s in data if isinstance(s, dict) and _fid_of(s) == fid]


def _changes_from_details(details):
    """A print deduct's charges ({sid, grams, remaining}: what it took and what
    it left) as changes. A charge with no known remaining, or no grams, can't
    move a filament across a line. Two charges of one spool count as one.

    A charge may say `was_archived` (the spool's archived flag before it): a
    review Apply can charge a spool archived by hand (Group 43.2), and that
    spool was no stock before the charge. Without it, the spool's record after
    the charge tells (`_crossing`); on the automatic deduct a charged spool was
    always in stock, since a head's spools are read from the non-archived list."""
    merged = {}
    for d in details or []:
        if not isinstance(d, dict):
            continue
        try:
            sid = int(d.get('sid'))
        except (TypeError, ValueError):
            continue
        grams, after = _num(d.get('grams')), _num(d.get('remaining'))
        if grams is None or after is None or grams <= 0 or after < 0:
            continue
        was_archived = d.get('was_archived')
        c = merged.get(sid)
        if c is None:
            merged[sid] = {"sid": sid, "fid": None, "grams": grams, "after_g": after,
                           "was_archived": was_archived}
        else:
            c["grams"] += grams
            c["after_g"] = min(c["after_g"], after)
    out = []
    for c in merged.values():
        before_g = c["after_g"] + c["grams"]
        before_in = None if c["was_archived"] is None else (not c["was_archived"] and before_g > 0)
        out.append({"sid": c["sid"], "fid": None, "before_g": before_g, "after_g": c["after_g"],
                    "before_in": before_in, "after_in": None})
    return out


def _change_from_records(sid, pre, post):
    """A manual weight write as a change, from the spool's records before and
    after it, or None when it can't take its filament's stock down (or the
    records can't say)."""
    if not isinstance(pre, dict) or not isinstance(post, dict):
        return None
    if pre.get('id') is None or str(pre.get('id')) != str(sid) or str(post.get('id')) != str(sid):
        return None   # a read blip, or Spoolman's 404 body
    fid_pre, fid_post = _fid_of(pre), _fid_of(post)
    if fid_pre is not None and fid_post is not None and fid_pre != fid_post:
        return None
    fid = fid_post if fid_post is not None else fid_pre
    before_g, after_g = remaining_g(pre), remaining_g(post)
    if fid is None or before_g is None or after_g is None:
        return None
    before_in, after_in = in_stock(pre), in_stock(post)
    if not before_in or (after_in and after_g >= before_g):
        return None   # no drop: nothing can cross a line downwards
    return {"sid": post.get('id'), "fid": fid, "before_g": before_g, "after_g": after_g,
            "before_in": True, "after_in": after_in}


def _log_colour(fil):
    hexes, _ = _colours(fil)
    clean = ''.join(ch for ch in hexes if ch in '0123456789abcdefABCDEF,')
    return clean.strip(',') or "ffaa00"


def _first_in_a_while(fid, kind):
    """True unless this filament logged this kind of warning in the last
    _REPEAT_S seconds (and then records it)."""
    now = time.monotonic()
    with _RECENT_LOCK:
        last = _RECENT.get((fid, kind))
        if last is not None and now - last < _REPEAT_S:
            return False
        _RECENT[(fid, kind)] = now
        return True


def _crossing(group, spools, threshold):
    """(message, swatch colour, kind) for the line one filament's write took it
    across, or None. `group`: the changes on this filament; `spools`: its
    spools as read after the write."""
    by_id = {str(s.get('id')): s for s in spools or []
             if isinstance(s, dict) and s.get('id') is not None}
    fil = None
    before_g = after_g = 0.0
    before_n = after_n = 0
    emptied = []
    for c in group:
        rec = by_id.get(str(c["sid"]))
        if rec is None:
            _debug(f"#{c['sid']} isn't among its filament's spools")
            return None
        now = remaining_g(rec)
        if now is None or abs(now - c["after_g"]) > _MATCH_G:
            _debug(f"#{c['sid']} has moved on since the write ({now} g, not {c['after_g']} g)")
            return None
        fresh_in = in_stock(rec)
        if c.get("after_in") is not None and c["after_in"] != fresh_in:
            _debug(f"#{c['sid']}'s archived state changed since the write")
            return None
        before_in = c.get("before_in")
        if before_in is None:
            # A charge never archives a spool it leaves grams on, so a spool
            # archived with grams left was archived before the charge too.
            before_in = c["before_g"] > 0 and (fresh_in or c["after_g"] <= 0)
        if before_in:
            before_g += c["before_g"]
            before_n += 1
        if fresh_in:
            after_g += c["after_g"]
            after_n += 1
        if before_in and not fresh_in:
            emptied.append(c["sid"])
        fil = fil or rec.get('filament')

    changed = {str(c["sid"]) for c in group}
    other_g, other_n, other_unknown = stock_of([s for k, s in by_id.items() if k not in changed])
    if other_unknown:
        return None   # a spool of unknown weight: neither low nor out can be told
    before_total, after_total = other_g + before_g, other_g + after_g
    before_count, after_count = other_n + before_n, other_n + after_n
    # The Activity Log renders a message as HTML, and these names are free text.
    name = html.escape(" ".join(filament_names(fil)), quote=False)
    if before_count > 0 and after_count == 0:
        if is_one_off(spoolman_api.filament_attribute_list(fil)):
            return None
        ids = ", ".join(f"#{s}" for s in sorted(emptied, key=lambda s: (_num(s) is None, _num(s) or 0)))
        tail = "was its last spool" if len(emptied) == 1 else "were its last spools"
        return f"⚠️ {name} is out: {ids} {tail} in stock", _log_colour(fil), "out"
    if after_count > 0 and before_total >= threshold > after_total:
        noun = "spool" if after_count == 1 else "spools"
        return (f"⚠️ {name} is running low: {after_total:.0f} g left in {after_count} {noun}",
                _log_colour(fil), "low")
    return None


def _check(changes):
    """Group the changes by filament, read each filament's spools once, and log
    a crossing. Never raises."""
    try:
        threshold = low_stock_g()
        groups = {}
        for c in changes:
            fid = c.get("fid")
            if fid is None:
                try:
                    fid = _fid_of(_spool_strict(c["sid"]))
                except Exception as e:
                    _debug(f"couldn't read #{c.get('sid')}: {e}")
                    continue
            if fid is None:
                _debug(f"#{c.get('sid')} has no filament")
                continue
            groups.setdefault(fid, []).append(c)
        for fid, group in groups.items():
            try:
                found = _crossing(group, _filament_spools_strict(fid), threshold)
            except Exception as e:
                _debug(f"filament {fid}: {e}")
                continue
            if found and _first_in_a_while(fid, found[2]):
                state.add_log_entry(found[0], "WARNING", found[1])
    except Exception as e:
        _debug(f"skipped: {e}")


def _dispatch(changes):
    if not changes:
        return
    if not _RUN_ASYNC:
        _check(changes)
        return
    try:
        threading.Thread(target=_check, args=(changes,), name="fcc-low-stock-check",
                         daemon=True).start()
    except Exception as e:
        _debug(f"couldn't start: {e}")


def check_after_deduct(details):
    """After a print deduct's exactly-once ledger write (print_deduct's
    `_record_applied_deduct`): `details` are its charges, {sid, grams,
    remaining} each. Never raises."""
    try:
        _dispatch(_changes_from_details(details))
    except Exception as e:
        _debug(f"skipped: {e}")


def check_after_weight_change(sid, pre, post):
    """After a manual weight write landed (routes_inventory's
    `_log_manual_weight_change`, the funnel the wizard and /api/spool/update
    share): `pre` / `post` are the spool's records before and after. Never
    raises."""
    try:
        change = _change_from_records(sid, pre, post)
        if change:
            _dispatch([change])
    except Exception as e:
        _debug(f"skipped: {e}")
