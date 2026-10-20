"""State/persistence routes + dashboard pulse + audit watchdog (L316 step 11).

Moved verbatim from app.py: /api/audit_session, the persistence routes
(/api/state/buffer, /api/state/queue, /api/spools/refresh, /api/log_event),
_check_audit_idle_timeout + /api/logs (the watchdog trio moves together —
audit_session and the logs heartbeat both drive the idle check), the pulse
section helpers (_pulse_section_logs keeps its api_get_logs_route()
call-through — the watchdog side effect is load-bearing), and the L206
/api/dashboard_pulse aggregator + _pulse_section_printer_status.

Wiring notes:
- _pulse_section_locations calls routes_locations.build_locations_response()
  (module-qualified), the body of /api/locations, handing it the tick's
  shared spool list (Group 52.1a).
- _pulse_section_label_backlog counts through routes_print_queue.backlog_count.
- state.GLOBAL_BUFFER / GLOBAL_QUEUE are read AND whole-replaced as
  attributes of the state module (never from-imported).
- No dependency on print_monitor (verified by scan) — the pulse
  printer-status section probes printers via prusalink_api directly.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import requests  # type: ignore
import time

import state  # type: ignore
import config_loader  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore
import prusalink_api  # type: ignore

import routes_locations  # type: ignore
import routes_print_queue  # type: ignore

from app_core import app

@app.route('/api/audit_session', methods=['GET'])
def api_audit_session():
    """L154 / 18.2 Part B — current audit session snapshot for the visual
    audit panel. Returns the location being audited plus enriched expected/
    scanned/rogue lists (each with the spool's display label, color,
    remaining weight, and slot if known) so the frontend can render a
    grid of tiles without doing per-id Spoolman lookups itself.

    Cheap when no audit is active (returns {active: False} immediately).

    Runs the idle-timeout watchdog first so even a direct poll heals a
    stale session — the dashboard's heartbeat hits /api/logs every 5s,
    but in case anything skips that path the same check here closes
    the loop."""
    _check_audit_idle_timeout()
    sess = state.AUDIT_SESSION
    if not sess.get('active'):
        return jsonify({"active": False})

    expected = list(sess.get('expected_items') or [])
    scanned = set(sess.get('scanned_items') or [])
    rogue = list(sess.get('rogue_items') or [])

    def _enrich(sid):
        try:
            sp = spoolman_api.get_spool(sid) or {}
        except Exception:
            sp = {}
        info = spoolman_api.format_spool_display(sp) if sp else {}
        fil = (sp.get('filament') or {})
        return {
            "id": int(sid),
            "display": info.get('text') or f"#{sid}",
            "color": fil.get('color_hex') or info.get('color') or '',
            "color_direction": fil.get('multi_color_direction') or 'longitudinal',
            "multi_color_hexes": fil.get('multi_color_hexes') or '',
            "remaining_weight": sp.get('remaining_weight'),
            "slot": (sp.get('extra') or {}).get('container_slot') or '',
        }

    expected_rows = []
    for sid in expected:
        row = _enrich(sid)
        row['found'] = (sid in scanned)
        expected_rows.append(row)
    rogue_rows = [{**_enrich(sid), 'found': True, 'rogue': True} for sid in rogue]

    return jsonify({
        "active": True,
        "location_id": sess.get('location_id'),
        # Same contract as the bulk-move snapshot (L298 Phase 3): tell the user
        # the session expires, DERIVED from the constant so the UI text can't
        # drift from the watchdog that enforces it. An audit that silently
        # vanishes mid-shelf reads as a broken app, not as a timeout.
        "idle_timeout_min": int(state.AUDIT_IDLE_TIMEOUT_SECONDS // 60),
        "expected": expected_rows,
        "rogue": rogue_rows,
        "stats": {
            "total_expected": len(expected),
            "found": sum(1 for r in expected_rows if r['found']),
            "missing": sum(1 for r in expected_rows if not r['found']),
            "rogue": len(rogue),
        },
    })


# --- PERSISTENCE ROUTES ---
@app.route('/api/state/buffer', methods=['GET', 'POST'])
def api_state_buffer():
    if request.method == 'POST':
        # 29.C1 — validate the payload is a list before persisting (mirrors
        # /api/spools/refresh). Without this, a malformed client write stored
        # ANY JSON type verbatim into GLOBAL_BUFFER and poisoned the buffer
        # served to every dashboard until the next good write.
        buf = (request.json or {}).get('buffer', [])
        if not isinstance(buf, list):
            return jsonify({"error": "buffer must be a list"}), 400
        state.GLOBAL_BUFFER = buf
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_BUFFER)

@app.route('/api/state/queue', methods=['GET', 'POST'])
def api_state_queue():
    if request.method == 'POST':
        # 29.C1 — same list-validation guard as the buffer above.
        q = (request.json or {}).get('queue', [])
        if not isinstance(q, list):
            return jsonify({"error": "queue must be a list"}), 400
        state.GLOBAL_QUEUE = q
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_QUEUE)

@app.route('/api/spools/refresh', methods=['POST'])
def api_spools_refresh():
    spools = request.json.get('spools', [])
    if not isinstance(spools, list):
        return jsonify({"error": "spools must be a list"}), 400
    if len(spools) == 0:
        return jsonify({})
    return jsonify(logic.get_live_spools_data(spools))

@app.route('/api/log_event', methods=['POST'])
def api_log_event():
    msg = request.json.get('msg', '')
    level = request.json.get('level', 'INFO')
    if msg: state.add_log_entry(msg, level)
    return jsonify({"success": True})

def _check_audit_idle_timeout():
    """Auto-cancel an audit session that's gone stale.

    A closed tab, browser crash, or server-restart-then-relaunch can
    leave AUDIT_SESSION.active=True with no real user behind the wheel.
    Without this watchdog the audit panel keeps auto-opening on every
    subsequent dashboard load until someone explicitly scans CMD:CANCEL
    or the process restarts. Checked on every /api/logs poll (every 5s
    from the dashboard heartbeat), so the recovery latency is ≤ 5s
    after the timeout window expires.
    """
    if not state.AUDIT_SESSION.get('active'):
        return
    last = float(state.AUDIT_SESSION.get('last_activity_ts') or 0.0)
    if last <= 0:
        # No timestamp at all (legacy session from before this watchdog
        # landed). Plant `now` so the timer starts NOW rather than
        # auto-cancelling immediately.
        state.AUDIT_SESSION['last_activity_ts'] = time.time()
        return
    if (time.time() - last) > state.AUDIT_IDLE_TIMEOUT_SECONDS:
        loc = state.AUDIT_SESSION.get('location_id') or ''
        state.add_log_entry(
            f"🕒 Audit auto-cancelled after "
            f"{state.AUDIT_IDLE_TIMEOUT_SECONDS // 60} min of inactivity"
            + (f" (was on {loc})" if loc else "")
            + " — no spools moved.",
            "WARNING", "ffaa00",
        )
        state.reset_audit()


def _check_bulk_move_idle_timeout():
    """Auto-cancel a bulk-move session that's gone stale (L298 Phase 2).

    Same rationale + shape as _check_audit_idle_timeout: a closed tab or a
    server restart can leave BULK_MOVE_SESSION.active=True with a SOURCE
    already armed — and a stale armed source is worse than a stale audit,
    because the next person's location scan would land as its destination.
    Lazily checked on every /api/logs poll (~5s heartbeat) and on the session
    poll itself; there is no background thread.
    """
    if not state.BULK_MOVE_SESSION.get('active'):
        return
    # Never wipe a session a commit is actively working on. The watchdog rides
    # the ~5s /api/logs heartbeat, so a long O(N) commit can cross the idle
    # deadline mid-flight; resetting there would log "auto-cancelled — no spools
    # moved" over a move that IS moving spools — the same lie the Phase-3 cancel
    # guard exists to prevent. The commit clears the session itself when it ends.
    if logic._BULK_MOVE_COMMIT_LOCK.locked():
        return
    last = float(state.BULK_MOVE_SESSION.get('last_activity_ts') or 0.0)
    if last <= 0:
        # No timestamp (a session predating this watchdog / hand-built in a
        # test). Plant `now` so the timer starts NOW rather than insta-cancelling.
        state.BULK_MOVE_SESSION['last_activity_ts'] = time.time()
        return
    if (time.time() - last) > state.BULK_MOVE_IDLE_TIMEOUT_SECONDS:
        src = state.BULK_MOVE_SESSION.get('source_id') or ''
        state.add_log_entry(
            f"🕒 Bulk move auto-cancelled after "
            f"{state.BULK_MOVE_IDLE_TIMEOUT_SECONDS // 60} min of inactivity"
            + (f" (was {src})" if src else "")
            + " — no spools moved.",
            "WARNING", "ffaa00",
        )
        state.reset_bulk_move()


@app.route('/api/bulk_move_session', methods=['GET'])
def api_bulk_move_session():
    """Poll the active bulk-move session for the deck-QR state + preview panel.

    Returns {active:False, stage:'idle'} when nothing is running (the frontend
    uses that to shapeshift the deck QR back to idle and close the panel).
    Runs the idle watchdog first so a direct poll also self-heals.
    """
    _check_bulk_move_idle_timeout()
    return jsonify(logic.bulk_move_session_snapshot())


@app.route('/api/logs', methods=['GET'])
def api_get_logs_route():
    # Cheap pre-flight: clear any abandoned audit session before the
    # frontend sees audit_active=True and auto-opens the panel.
    _check_audit_idle_timeout()
    _check_bulk_move_idle_timeout()
    sm_url, _ = config_loader.get_api_urls()
    sm_ok = False
    try: sm_ok = requests.get(f"{sm_url}/api/v1/health", timeout=3).ok
    except: pass

    return jsonify({
        "logs": state.RECENT_LOGS,
        "undo_available": len(state.UNDO_STACK) > 0,
        "audit_active": state.AUDIT_SESSION.get('active', False),
        "bulk_move_active": state.BULK_MOVE_SESSION.get('active', False),
        # The STAGE rides along so a reloaded page / second tab can paint the
        # deck tile correctly. Without it the tile fell back to 'idle' for an
        # ACTIVE session, and the deck button (which cancels while active) then
        # read as "arm a bulk move" but silently CANCELLED the armed one.
        "bulk_move_stage": state.BULK_MOVE_SESSION.get('stage', 'idle'),
        "status": {"spoolman": sm_ok}
    })


# ---------------------------------------------------------------------------
# L206 — Aggregated dashboard heartbeat
#
# startSmartSync used to fan out to ~6 separate endpoints every 5s
# (logs, locations, get_contents for an open manage modal, spools/refresh,
# printer_map + N x toolhead_slots + M x get_contents for printer status).
# At peak ~15 requests per heartbeat — the load that pushed L28 over the
# socket-buffer edge on 2026-05-18.
#
# This endpoint replaces that fan-out with a single bulk call. Callers
# specify which sections they need via `?include=logs,locations,...`,
# the backend assembles them in parallel via a ThreadPoolExecutor, and
# the frontend dispatches each section to its existing renderer. Net
# effect: ~12 requests/5s -> 1 request/5s, same data, lower overhead.
# ---------------------------------------------------------------------------

# Group 52.1a — ONE spool-list read per heartbeat. Every section that needs the
# spool list (locations, manage, printer_status, label_backlog) gets the same
# spoolman_api.SpoolListRead as `spools=`: it reads Spoolman on the first
# section's first use and every later section reuses that list. A busy tick
# used to read the whole list three times in the pulse, plus twice more for the
# label backlog's own /api/print_queue/pending poll. It lives for this one
# request only (no cross-request cache: a read right after a move must see it).
_VALID_PULSE_SECTIONS = frozenset({
    'logs', 'status', 'locations', 'buffer', 'manage', 'printer_status',
    'label_backlog',
})


def _pulse_section_logs():
    """Invoke the /api/logs handler and unwrap its JSON. Preserves the
    audit-idle-watchdog side effect because the bulk endpoint REPLACES the
    legacy heartbeat that used to drive it - losing it would silently break
    audit cancellation."""
    resp = api_get_logs_route()
    return resp.get_json()


def _pulse_section_locations(spools=None):
    """Build the /api/locations answer from the tick's shared spool list and
    unwrap. Handles the 500 locations-corrupt path by returning {'error': ...}
    so the caller can decide how to surface it; the bulk endpoint as a whole
    still returns 200 since other sections may have valid data."""
    rv = routes_locations.build_locations_response(spools=spools)
    if isinstance(rv, tuple):
        resp, status = rv[0], rv[1]
        return {'error': resp.get_json(), 'status': status}
    return rv.get_json()


def _pulse_section_manage(loc_id, spools=None):
    """Mirror of /api/get_contents for the open Location Manager view, from the
    tick's shared spool list.

    Group 52.1b — it tells "couldn't read" from "empty". A read that worked
    answers {'id', 'contents': [...], 'read_ok': True} (an empty box is
    `contents: []`); one that didn't answers {'id', 'read_ok': False,
    'read_error'} with NO `contents`, so the page keeps the cards it shows and
    says Spoolman didn't answer (a page from before 52 just skips the render).
    It used to answer `contents: []`, which painted a slow Spoolman as an empty
    box."""
    reader = spools if spools is not None else spoolman_api.SpoolListRead()
    listed = reader.get()
    if listed is None:
        return {'id': loc_id, 'read_ok': False,
                'read_error': f"couldn't read Spoolman ({reader.error})"}
    contents = spoolman_api.bucket_spools_by_location([loc_id], spools=listed)
    return {
        'id': loc_id,
        'contents': contents.get(str(loc_id).strip().upper(), []),
        'read_ok': True,
    }


def _pulse_section_label_backlog(spools=None):
    """The 🏷️ Backlog button's count (Group 52.1a), from the tick's shared spool
    list plus one filament read: the page used to poll
    /api/print_queue/pending on every tick for it, two more whole-list reads.
    Counted by routes_print_queue.backlog_count, the same flag filter the
    backlog list uses (in FCC: Spoolman ignores an `extra=` filter)."""
    reader = spools if spools is not None else spoolman_api.SpoolListRead()
    return routes_print_queue.backlog_count(reader.get(), reader.error)


def _pulse_section_printer_status(spools=None):
    """Server-side aggregator for the Printer Status widget. Replaces
    the client-side fan-out of printer_map + N x toolhead_slots +
    M x get_contents fetches with one server-side call. Toolhead
    occupancy for ALL toolheads is resolved in a single Spoolman fetch
    via `bucket_spools_by_location`; the per-printer work (bindings +
    PrusaLink state probe) then runs in its own thread (capped at 8) so
    a slow/offline printer doesn't serially block the rest.

    Occupancy keys off the toolhead LOCATION (the spool's own
    `location` / `physical_source`), NOT dryer-box `slot_targets`, so a
    dryer-box-less / direct-fed printer (Derek's Core One) shows the
    spool actually loaded on each toolhead. `unbound` is a pure binding
    hint (no dryer box feeds this toolhead) used only for the widget's
    "🔗 no bound slot" affordance — it never gates contents. (FilaBridge
    auto-deduct is likewise toolhead-driven, not box-mediated, so a
    direct-fed spool's weight still ticks after a print.)

    L56: each printer's payload also carries a `state` dict pulled
    directly from PrusaLink (`prusalink_api.get_printer_state`), which
    has no binding dependency. `state` is None when the printer is
    offline or unreachable so the widget can show an offline indicator.
    """
    from concurrent.futures import ThreadPoolExecutor

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    _, fb_url = config_loader.get_api_urls()
    grouped = {}
    for loc_id, info in printer_map.items():
        name = info.get('printer_name', 'Unknown')
        grouped.setdefault(name, []).append({
            'location_id': str(loc_id).upper(),
            'position': info.get('position', 0),
        })
    for entries in grouped.values():
        entries.sort(key=lambda e: (e['position'], e['location_id']))

    if not grouped:
        return {}

    # Box-bounding fix: a toolhead's `item` (the spool physically loaded on
    # it) must reflect ACTUAL occupancy at the toolhead location, NOT whether
    # a dryer box happens to feed it. Previously the contents lookup was gated
    # behind `is_bound` (a pure dryer-box slot_targets flag), so a directly-fed
    # toolhead with no bound box — e.g. Core One run dryer-box-less — showed
    # empty even with a spool loaded. We now bucket every printer_map toolhead's
    # occupancy in ONE Spoolman fetch (instead of one per bound toolhead, which
    # was both wrong AND an N-fetch fan-out) and keep `unbound` as a binding-only
    # display hint. Occupancy matches get_spools_at_location_detailed exactly
    # (direct location + physical_source ghost).
    all_tids = [str(loc_id).upper() for loc_id in printer_map.keys()]
    if spools is None:
        spools_by_tid = spoolman_api.bucket_spools_by_location(all_tids)
    else:
        # Group 52.1a: the tick's shared list. A failed read buckets nothing,
        # every head empty, as the fail-open read did before; answering
        # {'error'} instead would send the widget to its per-toolhead fan-out
        # (one more whole-list read per head) just when Spoolman is slow.
        spools_by_tid = spoolman_api.bucket_spools_by_location(all_tids, spools=spools.get() or [])

    def fetch_for_printer(item):
        name, entries = item
        bindings_result = locations_db.get_bindings_for_machine(name, printer_map)
        bindings = bindings_result.get('toolheads', {})
        toolheads = []
        for entry in entries:
            tid = entry['location_id']
            is_bound = bool(bindings.get(tid, []))
            contents = spools_by_tid.get(tid, [])
            # Group 42.4: the tile shows the one LOADED spool, a spool whose own
            # location is this head, never a ghost (a trail naming the head) while
            # a loaded one exists. A head holding two loaded spools (Derek: "If
            # looking at the toolhead, I should only ever see one in there") says
            # so instead of hiding the second.
            direct = [c for c in contents if not c.get('is_ghost')]
            item_data = (direct or contents)[0] if contents else None
            th_out = {
                'id': tid,
                'position': entry['position'],
                'item': item_data,
                'unbound': not is_bound,
                'loaded_count': len(direct),
            }
            if len(direct) > 1:
                th_out['loaded_ids'] = [c.get('id') for c in direct]
            toolheads.append(th_out)
        toolheads.sort(key=lambda t: (t['position'], t['id']))
        # Direct PrusaLink probe — runs regardless of dryer-box bindings,
        # so the widget ticks for dryer-box-less printers (L56). NOTE: cancel
        # DETECTION no longer rides this probe — it runs in the dashboard-
        # independent _cancel_monitor daemon (so an unattended print with FCC
        # unfocused/closed is still caught). This probe is widget-display only.
        try:
            state_info = prusalink_api.get_printer_state(fb_url, name)
        except Exception:
            state_info = None
        return name, {'toolheads': toolheads, 'state': state_info}

    out = {}
    max_workers = max(1, min(8, len(grouped)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for name, payload in ex.map(fetch_for_printer, grouped.items()):
            out[name] = payload
    return out


@app.route('/api/dashboard_pulse', methods=['GET', 'POST'])
def api_dashboard_pulse():
    """Aggregated heartbeat - see L206 docstring block above.

    Query params:
      include   comma-separated section names. Valid: logs, status,
                locations, buffer, manage, printer_status, label_backlog.
                Unknown names are silently ignored (forward-compat).
      manage_id required when 'manage' is in include - the LocationID
                whose contents to fetch.

    Group 52.1a: the sections that need Spoolman's spool list share ONE read
    (`tick_spools`, read lazily by the first section that asks), so a tick
    costs one whole-list read however many of them are on screen.
    Body (POST): {"refresh_spool_ids": [123, 124, ...]} - if present
                and non-empty, the response includes a "spools_refresh"
                section keyed by spool id, equivalent to a POST to
                /api/spools/refresh.

    Returns: {section_name: payload, ...}. Sections that error
    individually return {"error": "..."} in their slot; the response
    as a whole stays 200 so a partial failure doesn't blank the
    dashboard.
    """
    raw_include = (request.args.get('include') or '').strip()
    requested = set(s.strip().lower() for s in raw_include.split(',') if s.strip())
    include = requested & _VALID_PULSE_SECTIONS
    manage_id = (request.args.get('manage_id') or '').strip().upper()

    refresh_spool_ids = []
    if request.method == 'POST' and request.is_json:
        body = request.get_json(silent=True) or {}
        refresh_spool_ids = body.get('refresh_spool_ids') or []
        if not isinstance(refresh_spool_ids, list):
            refresh_spool_ids = []

    out = {}
    # One spool-list read for this tick, shared by every section below that
    # needs it (52.1a). Nothing is read until a section asks.
    tick_spools = spoolman_api.SpoolListRead()

    # logs and status share the underlying Spoolman+FilaBridge health
    # check, so we invoke the handler at most once per request.
    if 'logs' in include or 'status' in include:
        logs_error = None
        try:
            logs_payload = _pulse_section_logs()
        except Exception as e:
            logs_error = str(e)
            logs_payload = {'error': logs_error}
        if 'logs' in include:
            out['logs'] = logs_payload
        if 'status' in include:
            # 27.9 — the derived status section must honor the endpoint's
            # per-section isolation contract: when the shared logs health
            # check DIES, carry {'error': ...} in the status slot (so the
            # nav-bar dot gets a signal) instead of silently omitting it.
            if logs_error is not None:
                out['status'] = {'error': logs_error}
            elif isinstance(logs_payload, dict) and 'status' in logs_payload:
                out['status'] = {
                    'spoolman': logs_payload['status'].get('spoolman', False),
                    'audit_active': logs_payload.get('audit_active', False),
                    'undo_available': logs_payload.get('undo_available', False),
                    # L298 Phase 3 — the bulk-move signal must ride the DERIVED
                    # status section too. A paused Activity Log swaps 'logs' out
                    # for 'status' (inv_core.js _dashboardPulseTick), so without
                    # these two keys a paused tab got NO bulk-move signal at all:
                    # the idle watchdog could cancel the session server-side
                    # while the deck kept painting a live SCAN DEST / COMMIT tile.
                    'bulk_move_active': logs_payload.get('bulk_move_active', False),
                    'bulk_move_stage': logs_payload.get('bulk_move_stage', 'idle'),
                }

    if 'locations' in include:
        try:
            out['locations'] = _pulse_section_locations(spools=tick_spools)
        except Exception as e:
            out['locations'] = {'error': str(e)}

    if 'buffer' in include:
        out['buffer'] = state.GLOBAL_BUFFER

    if 'manage' in include and manage_id:
        try:
            out['manage'] = _pulse_section_manage(manage_id, spools=tick_spools)
        except Exception as e:
            out['manage'] = {'error': str(e), 'id': manage_id}

    if 'printer_status' in include:
        try:
            out['printer_status'] = _pulse_section_printer_status(spools=tick_spools)
        except Exception as e:
            out['printer_status'] = {'error': str(e)}

    if 'label_backlog' in include:
        try:
            out['label_backlog'] = _pulse_section_label_backlog(spools=tick_spools)
        except Exception as e:
            out['label_backlog'] = {'error': str(e), 'read_ok': False}

    if refresh_spool_ids:
        try:
            out['spools_refresh'] = logic.get_live_spools_data(refresh_spool_ids)
        except Exception as e:
            out['spools_refresh'] = {'error': str(e)}

    return jsonify(out)
