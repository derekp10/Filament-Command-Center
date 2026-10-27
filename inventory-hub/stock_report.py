"""Per-filament stock (Group 49.2): the ⚠️ Low-stock list and the one Activity
Log warning when a write takes a filament under the line.

Stock is counted per FILAMENT: all of its in-stock spools added up. A spool is
in stock when it isn't archived and has grams left (remaining > 0). A spool
whose remaining Spoolman can't work out (no weight on the spool or its
filament) still counts as in stock, with unknown grams: FCC can't call it
empty, and a filament holding one is never judged low.

  low  a filament with stock whose in-stock spools add up to less than
       `low_stock_g` grams (config, ⚙️ Behavior, default 250);
  out  a filament with no spool in stock: its spools are all archived or
       empty, or it has no spool on record at all (Derek, 2026-10-20: "they are
       technically out"; on prod those are the first import's samples and
       filaments used up before he tracked them), listed after the others with
       `no_spools`;
  excluded  a filament left off Low and Out from the list, with why
       (Derek, 2026-10-20: it may be discontinued, a one-off, or one he didn't
       like, and he wants to write down why; 2026-10-21: called "Excluded", not
       "Not buying again", since one he can't get any more may be one he
       liked). It is never low or out, whatever its stock; it is listed here
       with its reason, its note, the day it was excluded and its stock. The
       mark is three text extras on the filament (`fcc_stock_excluded`: the
       reason, stored as its label so Spoolman's own page reads "Excluded From
       Low Stock: Discontinued"; `fcc_stock_excluded_note`;
       `fcc_stock_excluded_at`), written only by `exclude_filament` /
       `include_again` below, behind POST / DELETE
       /api/filament/<id>/stock_exclusion (the list's 🔕 and ✏️). Any reason
       text counts, one typed in Spoolman by hand too; a blank one is no mark.
       It replaced the "One-off" attribute rule, which only ever ran on dev.
       Clearing sends FCC's delete sentinel, which spoolman_api turns into the
       field's clear (a JSON null on Spoolman 0.26+, which drops the key; a
       blank on an older one): Spoolman 0.27 keeps a key a PATCH leaves out.

The list (`build_report`, behind GET /api/stock_report, routes_inventory.py)
reads Spoolman ONCE and strictly, every spool with the archived ones
(`spoolman_api.get_all_spools_strict(allow_archived=True)`): the fail-open
`get_all_spools` answers [] on a blip, which would read as "everything is out".
A read that fails raises StockReadError, and the route answers an error, never
an empty list. Each spool carries its full filament record (Spoolman nests the
same record /api/v1/filament returns: all 257 spools on dev matched on
2026-10-19); a second strict read, of every filament, finds the ones with no
spool on record. It runs only when the panel opens, never on the dashboard
heartbeat. The title bar's ⚠️ count (`glance`, Group 57.2) does ride the
heartbeat: it is worked out from the tick's own spool and filament reads by the
list's own rule (`_members`), and reads nothing of its own.

The warning (`check_after_deduct`, `check_after_weight_change`) logs ONE
Activity Log WARNING per filament when a write takes it across a line:
  - from at or above `low_stock_g` to under it, with stock left:
    "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools";
  - from in stock to none in stock (its last spool emptied: the 0 g
    auto-archive): "⚠️ ... is out: #99 was its last spool in stock".
Neither for an excluded filament: no news there.
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
import datetime
import html
import json
import math
import threading
import time
from urllib.parse import quote

import requests  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import spoolman_api  # type: ignore

DEFAULT_LOW_STOCK_G = 250.0

# Excluded from Low and Out: the filament extras (registered at startup through
# spoolman_api.REQUIRED_FILAMENT_EXTRAS, and in setup_fields.py) and the reasons
# the list offers, (code, label). The label is what is stored.
EXCLUDE_KEY = "fcc_stock_excluded"
EXCLUDE_NOTE_KEY = "fcc_stock_excluded_note"
EXCLUDE_AT_KEY = "fcc_stock_excluded_at"
EXCLUDE_KEYS = (EXCLUDE_KEY, EXCLUDE_NOTE_KEY, EXCLUDE_AT_KEY)
EXCLUDE_REASONS = (
    ("discontinued", "Discontinued"),
    ("cant_find", "Can't find it"),
    ("one_off", "One-off"),
    ("didnt_like", "Didn't like it"),
    ("other", "Other"),
)
EXCLUDE_NOTE_MAX = 500

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


class ExclusionError(Exception):
    """An exclusion change that was refused or failed, with nothing changed
    unless it says so: `status` is the HTTP status the route answers, `error`
    its code, `msg` the sentence for the page."""

    def __init__(self, status, error, msg):
        super().__init__(msg)
        self.status, self.error, self.msg = status, error, msg


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
    """(grams, in-stock spools, in-stock spools with unknown grams). The grams
    are summed with math.fsum, so the order the spools are listed in can never
    move a filament across the line (Group 57 review: 0.1 + 249.7 + 0.2 is
    249.99999999999997 one way round and 250.0 another, and the title bar's
    count and the list read two different lists)."""
    rems, count, unknown = [], 0, 0
    for s in spools or []:
        if not in_stock(s):
            continue
        count += 1
        rem = remaining_g(s)
        if rem is None:
            unknown += 1
        else:
            rems.append(rem)
    return math.fsum(rems), count, unknown


def under_line(grams, threshold):
    """A filament's grams are under the Low line: the one comparison behind the
    list, the title-bar count and the low-stock warning (Group 57 review, round
    2). On grams rounded to the microgram: spools of 136.2, 7.9, 69.6 and 36.3 g
    make 250 g, but their sum in binary is 249.99999999999997, which counted as
    Low under a 250 g line, and the warning (summed another way) said otherwise."""
    return round(grams, 6) < threshold


def _floor_tenth(grams):
    """Grams to the tenth below, on grams rounded to the microgram (so a binary
    249.89999999999998 is 249.9, not 249.8)."""
    return math.floor(round(grams, 6) * 10) / 10


def _row_grams(grams, threshold=None):
    """A row's grams, to the tenth: a Low row's never rounded up to the line it
    is under (249.96 g is 249.9, not 250.0), so the page can't show it at the
    line either (inv_stock.js's _stockText)."""
    tenth = round(grams, 1)
    if threshold is not None and tenth >= threshold and under_line(grams, threshold):
        return _floor_tenth(grams)
    return tenth


def grams_text(grams, threshold=None):
    """Grams as the list shows them: whole, except where rounding would put a
    total that is under the line at it or over it ("250 g left" under a 250 g
    line): then the tenth, never rounded up (inv_stock.js's _stockText)."""
    whole = round(grams)
    if threshold is not None and under_line(grams, threshold) and whole >= threshold:
        return f"{_floor_tenth(grams):.1f}"
    return f"{whole:.0f}"


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


def _squash(text):
    return ''.join(ch for ch in str(text).lower() if ch.isalnum())


def _reason_code(label):
    """The code of a stored reason ("Didn't like it" -> didnt_like). A reason
    typed in Spoolman by hand that matches none reads as "other"."""
    key = _squash(label)
    for code, lab in EXCLUDE_REASONS:
        if key in (_squash(code), _squash(lab)):
            return code
    return "other"


def _plain(v):
    """A decoded text extra as it was written: quotes inside a note are kept
    (`_text` strips them, which suits a name, not a note)."""
    if v is None or isinstance(v, (dict, list, bool)):
        return ''
    return str(v).strip()


def exclusion_of(fil):
    """{reason, code, note, at} when the filament is excluded from Low and
    Out, else None. Any reason that isn't blank counts."""
    extra = _dict(_dict(fil).get('extra'))
    reason = _plain(extra.get(EXCLUDE_KEY))
    if not reason:
        return None
    return {"reason": reason, "code": _reason_code(reason),
            "note": _plain(extra.get(EXCLUDE_NOTE_KEY)),
            "at": _plain(extra.get(EXCLUDE_AT_KEY))}


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
        "excluded": exclusion_of(fil),   # {reason, code, note, at}, or None
        "buy_url": buy_url(fil, template),
    }


def _group(spools, filaments):
    """({filament id: filament}, {filament id: {fil, spools}}) from a spool list
    and the filament list. The filament list's own record wins over the copy
    nested in a spool (the same record, read a moment apart)."""
    fil_by_id = {}
    for fil in filaments:
        try:
            fil_by_id[int((fil or {}).get('id'))] = fil
        except (TypeError, ValueError, AttributeError):
            continue
    by_fid = {}
    for s in spools:
        fid = _fid_of(s)
        if fid is None:
            continue
        entry = by_fid.setdefault(fid, {"fil": fil_by_id.get(fid) or s.get('filament'), "spools": []})
        entry["spools"].append(s)
    return fil_by_id, by_fid


def _members(fil_by_id, by_fid, threshold):
    """The list each filament is on: (kind, fid, fil, grams, in-stock spools,
    spools on record, unknown, no_spools) for every one that is 'low', 'out' or
    'excluded'. The one rule behind the list (build_report) and the title-bar
    count (low_out_count), so the count never disagrees with the list it opens.
    A filament with no spool on record at all is out (or excluded) too, after
    the others; no_spools says so."""
    for fid, entry in by_fid.items():
        grams, count, unknown = stock_of(entry["spools"])
        total = len(entry["spools"])
        if exclusion_of(entry["fil"]):
            yield "excluded", fid, entry["fil"], grams, count, total, unknown, False
        elif count == 0:
            yield "out", fid, entry["fil"], 0.0, 0, total, unknown, False
        elif not unknown and under_line(grams, threshold):
            yield "low", fid, entry["fil"], grams, count, total, unknown, False
    for fid, fil in fil_by_id.items():
        if fid not in by_fid:
            yield ("excluded" if exclusion_of(fil) else "out"), fid, fil, 0.0, 0, 0, 0, True


def low_out_count(spools, filaments, threshold):
    """(low, out): how many filaments the ⚠️ Low stock list shows on Low and on
    Out (Group 57.2's title-bar count), by the list's own rule (`_members`).

    `spools` may be the NON-archived list (the dashboard heartbeat's one read)
    as well as every spool (build_report's): an archived spool is never in
    stock (`in_stock`), so it never decides Low or Out. A filament whose spools
    are all archived has no spool in stock either way: it is Out through the
    "no spool on record" path instead of the "none in stock" one, which changes
    only its row's wording (`no_spools`), never the count. (The one way the two
    could differ: a filament missing from `filaments` whose spools are all
    archived, which the list counts Out from the spool's own copy. Spoolman
    refuses to delete a filament that has spools, so that needs a delete landing
    between one request's two reads.)"""
    fil_by_id, by_fid = _group(spools, filaments)
    low = out = 0
    for kind, *_ in _members(fil_by_id, by_fid, threshold):
        if kind == "low":
            low += 1
        elif kind == "out":
            out += 1
    return low, out


def glance(spools, spools_error=None, filaments_read=None):
    """The ⚠️ Low stock title-bar button's count for the dashboard heartbeat
    (Group 57.2), from the tick's own reads: `spools` is its non-archived spool
    list (None when that read failed) and `filaments_read` its shared
    spoolman_api.FilamentListRead, which the label_backlog section counts from
    too, so the count costs no Spoolman read of its own.

    Answers {'read_ok': True, 'count', 'low', 'out', 'threshold_g'}, or
    {'read_ok': False, 'read_error'} when either list couldn't be read (the
    filament list isn't asked for once the spool read failed), so the page
    keeps the count it shows and never draws a blip as 0. Excluded filaments
    never count."""
    if spools is None:
        return {'read_ok': False, 'read_error': f"couldn't read Spoolman's spools ({spools_error})"}
    reader = filaments_read if filaments_read is not None else spoolman_api.FilamentListRead()
    filaments = reader.get()
    if filaments is None:
        return {'read_ok': False, 'read_error': f"couldn't read Spoolman's filaments ({reader.error})"}
    threshold = low_stock_g()
    low, out = low_out_count(spools, filaments, threshold)
    return {'read_ok': True, 'count': low + out, 'low': low, 'out': out, 'threshold_g': threshold}


def build_report():
    """The ⚠️ Low-stock list: {success, threshold_g, low, out, excluded,
    filaments, spools}. `low` runs from the fewest grams up; `out` and
    `excluded` are by name. Raises StockReadError when Spoolman can't be
    read."""
    try:
        cfg = config_loader.load_config() or {}
    except Exception:
        cfg = {}
    threshold = _threshold_from(cfg)
    template = cfg.get('buy_more_url_template') or ''
    try:
        spools = spoolman_api.get_all_spools_strict(allow_archived=True)
        filaments = _all_filaments_strict()
    except Exception as e:
        raise StockReadError(str(e) or e.__class__.__name__)
    if not isinstance(spools, list):
        raise StockReadError("Spoolman's answer wasn't a spool list")
    if not isinstance(filaments, list):
        raise StockReadError("Spoolman's answer wasn't a filament list")

    fil_by_id, by_fid = _group(spools, filaments)
    lists = {"low": [], "out": [], "excluded": []}
    for kind, fid, fil, grams, count, total, unknown, no_spools in _members(fil_by_id, by_fid, threshold):
        row = _row(fid, fil, grams, count, total, template)
        if kind == "low":
            row["grams"] = _row_grams(grams, threshold)
        if no_spools:
            row["no_spools"] = True
        elif kind == "excluded":
            row["stock_unknown"] = unknown > 0   # a spool of unknown weight: grams is a floor
        lists[kind].append(row)
    low, out, excluded = lists["low"], lists["out"], lists["excluded"]
    low.sort(key=lambda r: (r["grams"], r["display"].lower(), r["filament_id"]))
    out.sort(key=lambda r: (bool(r.get("no_spools")), r["display"].lower(), r["filament_id"]))
    excluded.sort(key=lambda r: (r["display"].lower(), r["filament_id"]))
    return {"success": True, "threshold_g": threshold, "low": low, "out": out,
            "excluded": excluded,
            "filaments": len(set(by_fid) | set(fil_by_id)),
            "spools": len(spools)}


# --- excluded: the mark and its undo -----------------------------------------------

def _filament_for_change(fid):
    """The filament, read strictly before a change: ExclusionError when it doesn't
    exist (404) or Spoolman doesn't answer (502), so nothing is written blind."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{sm_url}/api/v1/filament/{int(fid)}", timeout=_READ_TIMEOUT)
    except Exception as e:
        raise ExclusionError(502, "spoolman_unreachable",
                             f"Spoolman didn't answer ({e.__class__.__name__}), so nothing was changed. "
                             "Try again in a moment.")
    if resp.status_code == 404:
        raise ExclusionError(404, "no_filament", f"There is no filament #{fid} in Spoolman.")
    if not resp.ok:
        raise ExclusionError(502, "spoolman_unreachable",
                             f"Spoolman answered HTTP {resp.status_code}, so nothing was changed. "
                             "Try again in a moment.")
    try:
        fil = spoolman_api.parse_inbound_data(resp.json())
    except ValueError:
        fil = None
    if not isinstance(fil, dict) or str(fil.get('id')) != str(fid):
        raise ExclusionError(502, "spoolman_unreachable",
                             "Spoolman's answer wasn't that filament, so nothing was changed.")
    return fil


def _exclusion_now(fid):
    """The filament's mark as Spoolman has it now, read again after a write that
    reported failure (its PATCH has a 2 s read timeout, and may have landed).
    "unknown" when it can't be read."""
    try:
        return exclusion_of(_filament_for_change(fid))
    except ExclusionError:
        return "unknown"


def _display(fil):
    brand, material, colour = filament_names(fil)
    return f"{brand} - {material} - {colour}"


def _server_day():
    return time.strftime("%Y-%m-%d")


def _exclusion_day(today):
    """The day a mark is made: the page's own date (`today`, YYYY-MM-DD) when
    it is a real date within two days of the server's, else the server's. The
    container's clock is often UTC (dev's is), so an evening mark in California
    would otherwise read as the next day."""
    server = datetime.date.fromisoformat(_server_day())
    try:
        day = datetime.date.fromisoformat(str(today).strip()) if today else None
    except ValueError:
        day = None
    if day is None or abs((day - server).days) > 2:
        day = server
    return day.isoformat()


def exclude_filament(fid, reason, note='', today=None):
    """Excludes filament `fid` from Low and Out with a reason code (one of
    EXCLUDE_REASONS) and an optional note (needed for "other"). Excluding it
    again changes the reason and note and keeps the day it was first excluded;
    a new mark takes the page's `today` (see _exclusion_day).
    One read-merge write of the three extras (siblings kept); the Activity Log
    says what happened. Returns {filament_id, display, excluded, was};
    raises ExclusionError (nothing written unless a write was reported failed
    and couldn't be read back)."""
    labels = dict(EXCLUDE_REASONS)
    code = str(reason or '').strip().lower()
    if code not in labels:
        raise ExclusionError(400, "bad_reason",
                             "Pick why: Discontinued, Can't find it, One-off, Didn't like it or Other.")
    if note is None:
        note = ''
    if not isinstance(note, str):
        raise ExclusionError(400, "bad_note", "The note must be text.")
    note = note.strip()
    if len(note) > EXCLUDE_NOTE_MAX:
        raise ExclusionError(400, "note_too_long",
                             f"The note is {len(note)} characters long; keep it to {EXCLUDE_NOTE_MAX}.")
    if code == "other" and not note:
        raise ExclusionError(400, "note_needed", "Say why in the note: Other needs one.")

    fil = _filament_for_change(fid)
    was = exclusion_of(fil)
    at = (was or {}).get("at") or _exclusion_day(today)
    label = labels[code]
    marked = {"reason": label, "code": code, "note": note, "at": at}
    # Pre-wrapped as JSON strings (the keys are JSON_STRING_FIELDS too), so a
    # note such as "true" or "123" stays text; a blank note clears an old one
    # (the delete sentinel: see the module docstring).
    extra = {EXCLUDE_KEY: json.dumps(label), EXCLUDE_AT_KEY: json.dumps(at),
             EXCLUDE_NOTE_KEY: json.dumps(note) if note else spoolman_api.DELETE_EXTRA_SENTINEL}
    name = html.escape(" ".join(filament_names(fil)), quote=False)
    res = spoolman_api.update_filament(int(fid), {"extra": extra})
    if res is None:
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the change"
        if _exclusion_now(fid) != marked:
            state.add_log_entry(f"❌ Couldn't exclude {name} from Low and Out: "
                                f"{html.escape(str(err), quote=False)}", "ERROR", "ff4444")
            raise ExclusionError(502, "write_failed", f"Spoolman didn't save it: {err}")
        state.logger.warning(f"Exclude: filament {fid}'s write reported {err!r} but landed")
    why = f"{label}: {html.escape(note, quote=False)}" if note else label
    state.add_log_entry(f"🔕 Excluded {name} from Low and Out ({why})", "INFO", _log_colour(fil))
    out = {"filament_id": int(fid), "display": _display(fil), "excluded": marked, "was": was}
    # An old note Spoolman kept (spoolman_api logged it): said, not a failure.
    if isinstance(res, dict) and res.get('fcc_uncleared_note'):
        out["warning"] = res['fcc_uncleared_note']
    return out


def include_again(fid):
    """Undoes the exclusion: filament `fid` is listed on Low and Out again when
    it is low or out, and its reason, note and day are cleared (one write
    through the delete sentinel: a JSON null each on Spoolman 0.26+). Nothing is
    written when it wasn't excluded. A reason Spoolman kept is a failure (the
    filament would stay excluded). Returns {filament_id, display, excluded:
    None, was, changed}; raises ExclusionError."""
    fil = _filament_for_change(fid)
    was = exclusion_of(fil)
    extra_now = _dict(fil.get('extra'))
    if not any(_plain(extra_now.get(k)) for k in EXCLUDE_KEYS):
        return {"filament_id": int(fid), "display": _display(fil), "excluded": None,
                "was": None, "changed": False}
    name = html.escape(" ".join(filament_names(fil)), quote=False)
    extra = {k: spoolman_api.DELETE_EXTRA_SENTINEL for k in EXCLUDE_KEYS}
    res = spoolman_api.update_filament(int(fid), {"extra": extra})
    if res is None:
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the change"
        if _exclusion_now(fid) is not None:
            state.add_log_entry(f"❌ Couldn't include {name} again: {html.escape(str(err), quote=False)}",
                                "ERROR", "ff4444")
            raise ExclusionError(502, "write_failed", f"Spoolman didn't save it: {err}")
        state.logger.warning(f"Include again: filament {fid}'s write reported {err!r} but landed")
    elif EXCLUDE_KEY in (res.get('fcc_uncleared_extras') or []):
        # spoolman_api logged the WARNING; the filament is still excluded.
        raise ExclusionError(502, "not_cleared",
                             res.get('fcc_uncleared_note') or "Spoolman kept the exclusion: try again.")
    it_was = f" (it was excluded: {html.escape(was['reason'], quote=False)})" if was else ''
    state.add_log_entry(f"↩️ {name} is included in Low and Out again{it_was}", "INFO", _log_colour(fil))
    return {"filament_id": int(fid), "display": _display(fil), "excluded": None,
            "was": was, "changed": True}


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


def _all_filaments_strict():
    """Every filament, one strict read: raises when Spoolman doesn't answer."""
    return _get_json("/api/v1/filament")


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
    before_parts = []
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
            before_parts.append(c["before_g"])
            before_n += 1
        if fresh_in:
            after_n += 1
        if before_in and not fresh_in:
            emptied.append(c["sid"])
        fil = fil or rec.get('filament')

    changed = {str(c["sid"]) for c in group}
    others = [s for k, s in by_id.items() if k not in changed]
    _, other_n, other_unknown = stock_of(others)
    if other_unknown:
        return None   # a spool of unknown weight: neither low nor out can be told
    # Summed as the list sums them (Group 57 review, round 2: the other spools'
    # sum plus the changed one's, added on, could land on the other side of the
    # line from the list's own sum): after the write, the filament's spools as
    # read now (stock_of, the list's rule); before it, the same spools with the
    # changed ones' grams from before the write.
    after_total = stock_of(list(by_id.values()))[0]
    before_total = math.fsum([remaining_g(s) for s in others if in_stock(s)] + before_parts)
    before_count, after_count = other_n + before_n, other_n + after_n
    if exclusion_of(fil):
        return None   # excluded: neither low nor out is news
    # The Activity Log renders a message as HTML, and these names are free text.
    name = html.escape(" ".join(filament_names(fil)), quote=False)
    if before_count > 0 and after_count == 0:
        ids = ", ".join(f"#{s}" for s in sorted(emptied, key=lambda s: (_num(s) is None, _num(s) or 0)))
        tail = "was its last spool" if len(emptied) == 1 else "were its last spools"
        return f"⚠️ {name} is out: {ids} {tail} in stock", _log_colour(fil), "out"
    if after_count > 0 and not under_line(before_total, threshold) and under_line(after_total, threshold):
        noun = "spool" if after_count == 1 else "spools"
        return (f"⚠️ {name} is running low: {grams_text(after_total, threshold)} g left in {after_count} {noun}",
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
