"""FCC-native print-usage deduct engine (L316 step 10).

Moved verbatim from app.py: _resolve_active_locs_for_printer (MMU M0/M1
alias ordering — every deduct resolver depends on it), the deduct core
(_apply_usage_to_printer, _record_applied_deduct, snapshot/swap helpers,
_compute_cancel_usage, deduct_cancelled_print, deduct_completed_print,
review routing/stash/enqueue/create), the /api/cancel_deduct/* routes +
_confirm_no_spool_review, /api/smart_move, and the three adjacent read
endpoints (multi-spool filaments, spools_by_filament, backfill weights).

Contracts preserved verbatim (see the carve plan + CLAUDE.md):
- exactly-once via print_deduct_ledger; cancel_review_store.pop is the
  atomic claim; spoolman_api.LAST_SPOOLMAN_ERROR read stays adjacent to the
  failing write (attribute access, never from-imported).
- Activity-log message text is load-bearing (tests assert on it).
- Vestigial fb_url/filabridge params carried verbatim (separate cleanup item).

The cancel-monitor daemon (print_monitor.py) calls INTO this module
module-qualified; this module never imports print_monitor (one-way edge).
Tests patch these symbols ON THIS MODULE (repointed from `app` in the same
commit) so intra-module calls see the patches.

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
import print_deduct_ledger  # type: ignore
import cancel_review_store  # type: ignore
import cancel_fetch_store  # type: ignore

from app_core import app

def _resolve_active_locs_for_printer(printer_map, printer_name, filabridge_url):
    """Return [(loc_id, p_info)] for `printer_name`, ordered so the
    physically-active location for each position comes first.

    Background: printer_map can have two entries sharing the same position
    — e.g. CORE1-M0 (direct feed) and CORE1-M1 (MMU-routed). Only one is
    active per print. We query PrusaLink /api/v1/info.mmu to decide:
      - mmu=True  → M1-suffix aliases are preferred (MMU routed)
      - mmu=False → M0-suffix aliases are preferred (direct feed)
      - unknown   → printer_map insertion order is used (fallback)

    Downstream code iterates this ordering and deducts from the first
    location per position that actually has a spool assigned.
    """
    import prusalink_api  # local import keeps this helper usable at import time
    candidates = [
        (loc_id, p_info) for loc_id, p_info in printer_map.items()
        if p_info.get('printer_name') == printer_name
    ]
    if not candidates:
        return []

    positions_seen = {}
    for _, p_info in candidates:
        positions_seen[p_info.get('position', 0)] = positions_seen.get(p_info.get('position', 0), 0) + 1
    if not any(count > 1 for count in positions_seen.values()):
        return candidates  # no aliases — nothing to re-order

    mmu = None
    try:
        mmu = prusalink_api.get_printer_mmu_flag(filabridge_url, printer_name)
    except Exception:
        mmu = None
    if mmu is None:
        return candidates  # can't tell which is active — keep insertion order

    def _sort_key(item):
        loc_id = str(item[0]).upper()
        # Preferred alias sorts first (0), non-preferred second (1).
        if mmu:
            return (0 if loc_id.endswith('-M1') else 1, loc_id)
        return (0 if loc_id.endswith('-M0') else 1, loc_id)

    return sorted(candidates, key=_sort_key)


# --- REPLACED: Multi-Spool Logic instead of Multi-Color ---
@app.route('/api/get_multi_spool_filaments', methods=['GET'])
def api_get_multi_spool_filaments():
    sm_url, _ = config_loader.get_api_urls()
    try:
        # 1. Get ALL active spools
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=10)
        if not resp.ok: return jsonify([])
        all_spools = resp.json()
        
        # 2. Group by Filament ID
        fil_counts = {}
        fil_spools = {}
        fil_names = {}
        fil_vendors = {}
        
        if isinstance(all_spools, list):
            for s in all_spools:
                # 27.7 — per-spool guard: one malformed entry (missing 'id',
                # or filament/vendor present-but-null) previously raised inside
                # this loop, tripped the blanket except below, and poisoned the
                # WHOLE response to [] — hiding every valid candidate. Skip the
                # bad record (logged) and keep aggregating the rest.
                try:
                    if not isinstance(s, dict) or s.get('archived'): continue # Skip archived
                    fil = s.get('filament') or {}
                    fid = fil.get('id')
                    if not fid: continue

                    if fid not in fil_counts:
                        fil_counts[fid] = 0
                        fil_spools[fid] = []
                        fil_names[fid] = fil.get('name', '')
                        fil_vendors[fid] = (fil.get('vendor') or {}).get('name', '')

                    fil_counts[fid] += 1
                    fil_spools[fid].append(s['id'])
                except Exception as _spool_err:
                    state.logger.error(
                        f"Multi-Spool: skipping malformed spool entry: {_spool_err}")
                    continue
            
        # 3. Filter for > 1
        candidates = []
        for fid, count in fil_counts.items():
            if count > 1:
                display_name = f"{fil_vendors.get(fid, '')} - {fil_names.get(fid, '')}".strip(" -")
                candidates.append({
                    "id": fid,
                    "display": display_name,
                    "count": count,
                    "spool_ids": fil_spools.get(fid, [])
                })
        
        return jsonify(candidates)
    except Exception as e:
        state.logger.error(f"Multi-Spool Error: {e}")
        return jsonify([])

# --- NEW ROUTE: Fetch Active Spools for a specific Filament ---
@app.route('/api/spools_by_filament', methods=['GET'])
def api_get_spools_by_filament():
    fid = request.args.get('id')
    if not fid: return jsonify([])
    
    allow_archived = request.args.get('allow_archived', 'false').lower() == 'true'
    
    sm_url, _ = config_loader.get_api_urls()
    try:
        # Get spools filtered by filament_id
        # We ask Spoolman directly: "Give me all spools for Filament ID X"
        sm_req_url = f"{sm_url}/api/v1/spool?filament_id={fid}"
        if allow_archived:
            sm_req_url += "&allow_archived=true"
        resp = requests.get(sm_req_url, timeout=5)
        if resp.ok:
            if allow_archived:
                spools = resp.json()
            else:
                spools = [s for s in resp.json() if not s.get('archived')]
            return jsonify(spools)
        return jsonify([])
    except:
        return jsonify([])


@app.route('/api/backfill_spool_weights/<int:fid>', methods=['POST'])
def api_backfill_spool_weights(fid):
    """Backfill spool_weight on historical spools that saved as 0 before the
    inheritance chain landed. Resolves the inheritable empty-spool weight from
    the filament (then its vendor), then PATCHes every spool under this
    filament whose own spool_weight is null or <= 0. Archived spools are
    included so old empty-weight references stay accurate.
    """
    try:
        fil = spoolman_api.get_filament(fid)
        if not fil:
            return jsonify({"success": False, "msg": f"Filament #{fid} not found."}), 404

        def _positive(v):
            try: return v is not None and float(v) > 0
            except (TypeError, ValueError): return False

        fil_wt = fil.get('spool_weight')
        vendor_wt = (fil.get('vendor') or {}).get('empty_spool_weight')

        if _positive(fil_wt):
            target = float(fil_wt); source = 'filament'
        elif _positive(vendor_wt):
            target = float(vendor_wt); source = 'vendor'
        else:
            return jsonify({
                "success": False,
                "msg": "No inheritable empty-spool weight on this filament or its vendor — set one on the filament or the vendor first."
            }), 400

        sm_url, _ = config_loader.get_api_urls()
        resp = requests.get(f"{sm_url}/api/v1/spool?filament_id={fid}&allow_archived=true", timeout=5)
        if not resp.ok:
            return jsonify({"success": False, "msg": "Failed to fetch spools from Spoolman."}), 502
        spools = resp.json() or []

        updated_ids = []
        skipped = 0
        errors = []
        for sp in spools:
            sid = sp.get('id')
            sp_wt = sp.get('spool_weight')
            if _positive(sp_wt):
                skipped += 1
                continue
            res = spoolman_api.update_spool(sid, {'spool_weight': target})
            if res:
                updated_ids.append(sid)
            else:
                errors.append(sid)

        return jsonify({
            "success": True,
            "filament_id": fid,
            "target_weight": target,
            "source": source,
            "updated": len(updated_ids),
            "updated_ids": updated_ids,
            "skipped": skipped,
            "errors": errors,
        })
    except Exception as e:
        state.logger.error(f"api_backfill_spool_weights({fid}) failed: {e}")
        return jsonify({"success": False, "msg": str(e)}), 500


@app.route('/api/smart_move', methods=['POST'])
def api_smart_move():
    payload = request.json or {}
    return jsonify(logic.perform_smart_move(
        payload.get('location'),
        payload.get('spools'),
        target_slot=payload.get('slot'),
        origin=payload.get('origin', ''),
        confirm_active_print=bool(payload.get('confirm_active_print', False)),
    ))


def _apply_usage_to_printer(printer_name, usage_map, fb_url, strategy_label="",
                            active_locs=None):
    """Deduct per-toolhead grams from the spools currently mapped to
    `printer_name`'s toolheads. `usage_map` is {toolhead_position: grams}.

    The single canonical deduct loop, shared by the FilaBridge error-recovery
    aggressive parse (full-print estimate) and the cancelled-print PARTIAL
    deduct (prefix-parsed grams). MMU-alias positions (e.g. CORE1-M0 vs
    CORE1-M1 — same position in printer_map) are deduped via
    `processed_positions` so one usage slice isn't applied twice. Within a single
    toolhead, `spoolman_api.select_deduct_targets` drops a stale physical_source
    GHOST in favour of the directly-loaded spool so a leftover ghost trail can't
    double-charge the position (22.4(1)); a genuinely-ambiguous toolhead (2+
    distinct loaded spools, physically impossible at one-spool-per-head) is WARNed
    and SKIPPED — never silently over-deducted — so its grams surface as a
    shortfall the caller can true up (vs the interactive preview, which keeps both
    rows so the reviewer can pick). Writes ONLY `{used_weight}` per the CLAUDE.md
    write-surface contract — never bundles initial_weight/location/extra, so a
    partial deduct can't wipe siblings or silently archive a loaded spool. Surfaces
    LAST_SPOOLMAN_ERROR on rejection.

    `active_locs` may be passed pre-resolved (by a caller that already resolved it,
    e.g. the no_spool confirm) so an MMU printer's info.mmu ordering probe runs ONCE
    instead of per call (22.4(5)); None re-resolves it here.

    Returns (spools_updated, details, known_positions) where details is a list of
    {sid, grams, remaining} for each successful deduct and known_positions is the set
    of this printer's real toolhead positions — surfaced so the caller's shortfall
    (requested-but-not-applied) excludes orphan tool indices, which already got their
    own WARNING here, instead of double-warning them (22.4(3)).
    """
    if active_locs is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2
        active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    spools_updated = 0
    details = []
    processed_positions = set()
    for loc_id, p_info in active_locs:
        toolhead_idx = p_info.get('position', 0)
        if toolhead_idx in processed_positions:
            continue
        if toolhead_idx not in usage_map:
            continue
        weight_used = usage_map[toolhead_idx]
        loc_spools = spoolman_api.get_spools_at_location(loc_id)
        if not loc_spools:
            continue  # try the next alias for this position
        processed_positions.add(toolhead_idx)
        # >1 spool at one toolhead = a stale GHOST + the current load (or two
        # mis-assignments). Resolve to the directly-loaded spool; only fetch the
        # detailed/ghost info in this rare case so the single-spool common path is
        # untouched. 2+ distinct LOADED spools is unresolvable — warn + skip rather
        # than guess (which over-deducts or hits the wrong spool); the grams then
        # show up as a shortfall.
        if len(loc_spools) > 1:
            loc_spools, ambiguous = spoolman_api.select_deduct_targets(loc_id)
            if ambiguous:
                state.add_log_entry(
                    f"⚠️ {printer_name}: toolhead {str(loc_id).upper()} has "
                    f"{len(loc_spools)} spools assigned (sids {sorted(loc_spools)}) — "
                    f"can't tell which is loaded; {weight_used:.2f}g not deducted, "
                    f"weigh the spool to true up.", "WARNING", "ffaa00")
                continue
        for sid in loc_spools:
            spool_data = spoolman_api.get_spool(sid)
            if spool_data and weight_used > 0:
                used = float(spool_data.get('used_weight', 0))
                initial = float(spool_data.get('initial_weight', 0) or 0)
                remaining = max(0, initial - used)
                new_remaining = max(0, remaining - weight_used)
                new_used = used + weight_used
                if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                    spools_updated += 1
                    # Spoolman caps used_weight ≤ initial, so a near-empty spool
                    # absorbs only `remaining`, not the full `weight_used`. Record the
                    # ACTUALLY-absorbed grams (= remaining - new_remaining) so the
                    # ledger and the callers' shortfall math reflect reality — else an
                    # over-capacity deduct reads as fully applied and the gap is
                    # silently lost (the clamp the partial-confirm loop also guards).
                    actual_g = min(float(weight_used), remaining)
                    info = spoolman_api.format_spool_display(spool_data)
                    label = strategy_label or "Auto-deduct"
                    state.add_log_entry(
                        f"✔️ Auto-deducted {actual_g:.1f}g from Spool #{sid} ({label}): "
                        f"[{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]",
                        "SUCCESS", info['color'])
                    details.append({"sid": sid, "grams": actual_g, "remaining": new_remaining})
                else:
                    err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                    state.add_log_entry(
                        f"❌ Failed to auto-deduct from Spool #{sid}: {err}", "ERROR", "ff4444")
    # Surface gcode tool indices that don't correspond to ANY of this printer's
    # toolhead positions (a cross-machine gcode, or a tool↔position mismatch) —
    # those grams can't be deducted, so make the loss visible instead of
    # silently dropping it. (A position that exists but has no spool loaded is
    # benign and not flagged here.)
    known_positions = {p_info.get('position', 0) for _, p_info in active_locs}
    orphaned = {t: g for t, g in usage_map.items()
                if t not in known_positions and g > 0}
    if orphaned:
        lost = round(sum(orphaned.values()), 2)
        state.add_log_entry(
            f"⚠️ {printer_name}: {lost:.2f}g on tool index(es) {sorted(orphaned)} "
            f"map to no toolhead position on this printer — not deducted "
            f"(weigh the spool if this looks wrong).", "WARNING", "ffaa00")
    return spools_updated, details, known_positions


def _record_applied_deduct(printer_name, job_id, *, filename, scale, details,
                           usage_map, known_positions=None, confirmed=False):
    """Single source of truth for the tail of an auto-applied deduct: record the
    ACTUALLY-applied grams in the exactly-once ledger, then surface any shortfall
    (requested-but-not-applied grams) as a 2dp WARNING so it's never silently lost.
    Returns (applied, shortfall), both rounded to 2dp.

    Erases the drift the auto-apply sites had grown (22.4(2)/(4)):
      • the ledger records APPLIED (sum of `details`), not the requested estimate —
        deduct_cancelled_print used to record sum(usage_map) (the full requested),
        over-stating it and, via the single (printer,job_id) key, blocking an
        unbound position's later recovery; the completed/cancel-review paths already
        recorded applied, so this just aligns the three;
      • the shortfall WARN is 2dp here, matching the `shortfall_g` API field (the
        inline sites logged 1dp).
    `known_positions` (22.4(3)) restricts `requested` to tool indices on a real
    toolhead so an orphan index doesn't double-fire (its own orphan WARNING already
    fired inside _apply_usage_to_printer). None means "all indices are known".

    NOT for the api_cancel_deduct_confirm per-sid loop — that deducts user-chosen
    grams (no requested/usage_map concept), so a shortfall is meaningless there."""
    applied = round(sum(d['grams'] for d in details), 2)
    if known_positions is None:
        requested = round(sum(usage_map.values()), 2)
    else:
        requested = round(sum(g for t, g in usage_map.items()
                              if t in known_positions), 2)
    extra = {"confirmed": True} if confirmed else {}
    print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                      scale=scale, grams=applied, **extra)
    shortfall = round(max(0.0, requested - applied), 2)
    if shortfall > 0.05:
        state.add_log_entry(
            f"⚠️ {printer_name}: {shortfall:.2f}g of '{filename}' wasn't deducted "
            f"(no bound spool, a failed write, or a near-empty spool) — weigh that "
            f"spool to true up.", "WARNING", "ffaa00")
    return applied, shortfall


def _snapshot_active_spools(printer_name, fb_url, active_locs=None):
    """Resolve {toolhead_position: the single loaded sid, or None} for `printer_name`,
    using the SAME per-position alias-fallthrough + ghost-vs-current pick as
    _apply_usage_to_printer — so a print-START snapshot and a completion snapshot
    compare apples-to-apples (22.3 mid-print spool-swap detection). A position is
    None when it's EMPTY or AMBIGUOUS (2+ distinct loaded spools), so ONLY a clean
    1→1 sid change between two snapshots ever flags a swap.

    Best-effort: any failure (Spoolman blip, no printer_map) returns {}, so the
    caller degrades to today's auto-apply rather than crashing the deduct. Per-
    position cost mirrors the apply loop (one get_spools_at_location per position;
    select_deduct_targets only on the rare >1 case) — bounded, once per job at start
    and once at completion; bucket_spools_by_location could collapse it to one fetch
    later if it shows in a perf trace."""
    snap = {}
    try:
        if active_locs is None:
            printer_map = locations_db.get_active_printer_map()
            active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
        processed = set()
        for loc_id, p_info in active_locs:
            pos = p_info.get('position', 0)
            if pos in processed:
                continue
            sids = spoolman_api.get_spools_at_location(loc_id)
            if not sids:
                continue  # try the next alias for this position (mirror the apply loop)
            processed.add(pos)
            if len(sids) > 1:
                sids, _amb = spoolman_api.select_deduct_targets(loc_id)
            snap[pos] = sids[0] if len(sids) == 1 else None
    except Exception:
        return {}
    return snap


def _validated_start_spools(src, job_id):
    """Return src's `start_spools` snapshot ONLY if it belongs to `job_id`, else None.
    `src` is the tracker entry (restart) or the fire dict (live edge). Both job_id
    sides are str-coerced — get_printer_job can hand back an int job_id while
    `snapshot_job` is stored as a string, so a bare == would silently invalidate a
    good snapshot (int 9 != '9'). Guards a stale snapshot from a previous job."""
    if not src:
        return None
    if str(src.get('snapshot_job')) != str(job_id):
        return None
    return src.get('start_spools')


def _validated_swap_log(src, job_id):
    """22.3(b): return src's `swap_log` (ordered mid-print swap events) ONLY if its
    snapshot belongs to `job_id`. swap_log is captured under the same `snapshot_job`
    as start_spools and popped alongside it on a job change, so it shares the guard —
    a stale log from a previous job is never carried into a completion deduct."""
    if not src:
        return None
    if str(src.get('snapshot_job')) != str(job_id):
        return None
    return src.get('swap_log')


def _is_sid_swap(before, after):
    """True iff `before`→`after` is a confident, clean 1→1 spool change at one toolhead
    position: both sides present (a None = an EMPTY or ambiguous toolhead, never a
    confident swap) AND different. Compared as STRINGS so (a) a JSON int↔str round-trip
    can't make the same sid read as changed, and (b) a non-numeric sid can never raise —
    the bare `int(a) != int(b)` this replaces could throw a ValueError that the callers'
    best-effort `except` swallowed into a SILENT full-footer auto-apply (the exact
    mis-attribution the swap guard exists to prevent). Single source of truth for "did the
    spool at this position change", shared by the capture (_record_swap_events) and the
    completion-time detector (deduct_completed_print) so the two can't drift."""
    return before is not None and after is not None and str(before) != str(after)


def _record_swap_events(entry, end_snap, progress, runout=False):
    """22.3(b): append ordered mid-print spool-swap events to entry['swap_log'] by
    diffing a resume-time snapshot (`end_snap` = {position: loaded sid or None}) against
    the mapping in effect for the segment just printed — start_spools advanced by the
    destination (`to_sid`) of any prior swap at each position. Only a clean 1→1 sid
    change flags: None on EITHER side (an empty or ambiguous toolhead) is not a
    confident swap, mirroring the completion-time guard. Mutates `entry` in place; the
    caller holds the tracker lock. Returns the count of new events appended.

    Each event is {seq, position, progress, from_sid, to_sid}. `progress` is the
    boundary % at the pause (the segment that just ended reached it); `seq` is the
    append order so a downstream apportionment can align segment k → the spool loaded
    after the k-th resume. Detection only fires when the spool MAPPING changes — i.e.
    an FCC eject/load at the pause updates Spoolman `location`; a purely physical roll
    swap with no FCC action is invisible (documented limitation, same as 22.3(c))."""
    start = entry.get('start_spools') or {}
    log = list(entry.get('swap_log') or [])
    # Reconstruct what the just-printed segment was feeding from: the start mapping,
    # advanced by each prior swap's destination at that position.
    running = {str(k): v for k, v in start.items()}
    for ev in log:
        running[str(ev.get('position'))] = ev.get('to_sid')
    added = 0
    for pos, to_sid in end_snap.items():
        from_sid = running.get(str(pos))
        if not _is_sid_swap(from_sid, to_sid):
            continue  # empty/ambiguous on either side, or unchanged — not a swap
        log.append({
            "seq": len(log),
            "position": pos,
            "progress": float(progress or 0.0),
            "from_sid": from_sid,
            "to_sid": to_sid,
            # 22.3(b): True when this pause was an ATTENTION runout (sensor tripped) vs
            # a deliberate manual/PAUSED early swap — the split charges the run-out
            # spool the sensor→nozzle `path_filament_g` remnant only on a runout.
            "runout": bool(runout),
        })
        added += 1
    if added:
        entry['swap_log'] = log
    return added


def _log_cancel_uncomputable(printer_name, filename, reached_fraction, content):
    """Operator-facing log for a cancel whose partial we couldn't compute,
    distinguishing the three reasons so a cancel never goes SILENTLY
    un-deducted. Returns the status string the caller should surface.
      content is None      → download failed / binary .bgcode  → 'error' (WARNING)
      footer present        → genuine zero-extrusion cancel      → 'no_usage' (INFO)
      footer absent         → unrecognized gcode (non-Prusa?)    → 'no_usage' (WARNING)
    """
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    if not content:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"couldn't fetch/parse the gcode (binary .bgcode or printer "
            f"unreachable); no partial deduct. Weigh the spool to true it up.",
            "WARNING", "ffaa00")
        return "error"
    has_footer = ('filament used [g]' in content and 'filament used [mm]' in content)
    if has_footer:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"no partial usage to deduct (cancelled before any extrusion).",
            "INFO")
    else:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"gcode has no recognized per-tool 'filament used' footer "
            f"(non-Prusa slicer?); can't compute the partial. Weigh the spool.",
            "WARNING", "ffaa00")
    return "no_usage"


def _compute_cancel_usage(printer_name, filename, job_id, reached_fraction,
                          ip_address, api_key, use_footer=False):
    """Download + parse a print → (usage_map, terminal).
    On success: (usage_map, None). On a can't-compute outcome: (None, status
    dict). Shared by the cancel paths (auto-apply deduct_cancelled_print + preview
    _create_pending_cancel_review) AND the Phase-2 completion path
    (deduct_completed_print).

    use_footer=False (cancel/partial): prefix-parse the body up to the cancel
    point. use_footer=True (COMPLETED print): parse the full per-tool footer (the
    exact slicer estimate = what FilaBridge billed — the cancel prefix-parse's
    high-water-mark E omits the final wipe/ram tail, which a completion should
    keep). Both yield {tool_index: grams} in the same space, so the single-tool
    fold + downstream resolution are identical.

    fetch_cancel_gcode transparently decodes binary G-code (.bgcode — Derek's
    whole fleet) and remaps the progress fraction from compressed-file space to
    the decoded text, so the prefix-parse runs correctly on real prints. The
    decoded text also carries the footer, so use_footer reads it from the same
    download."""
    prepared = prusalink_api.fetch_cancel_gcode(
        ip_address, api_key, filename, reached_fraction)
    if not prepared or not prepared.get("gcode"):
        # Download failed. The dominant cause is NOT a permanent error: PrusaLink
        # 404s the raw-file download while the file is the SELECTED/active print
        # — i.e. while the printer sits in STOPPED with the cancel-summary screen
        # up, which is EXACTLY when we fire (confirmed live 2026-06-11; §9.10).
        # The file un-locks once the print is cleared (→ IDLE). So this is
        # RETRYABLE: return without a terminal "weigh the spool" log and let the
        # caller stash a deferred-fetch retry (the monitor re-attempts each tick
        # once the printer leaves STOPPED). (Was an immediate terminal error.)
        return None, {"status": "error", "reason": "download_failed", "job_id": job_id}
    content = prepared["gcode"]
    if use_footer:
        # Completion: the full per-tool slicer footer (exact, = FilaBridge).
        usage_map = prusalink_api.parse_footer_usage(content)
    else:
        usage_map = prusalink_api.parse_partial_filament_usage(content, prepared["fraction"])
    if not usage_map:
        if not use_footer:
            # Cancel-specific "weigh the spool" log. A completion with an empty
            # footer is a degenerate no-op — its caller logs its own line.
            _log_cancel_uncomputable(printer_name, filename, reached_fraction, content)
        return None, {"status": "no_usage", "job_id": job_id}

    # Single-toolhead printer + single-material print (Derek's Core One: one
    # head, one spool): the slicer's tool INDEX can differ from the printer's
    # toolhead POSITION (an MMU-profile file marks slot 1 even when one head
    # exists), so re-key that lone tool onto the sole position — otherwise it
    # orphans to a non-existent position and goes un-deducted. Guarded to a
    # SINGLE footer tool so a real multi-material MMU print (several spools
    # swapped through one head) is NOT summed onto one spool (over-deduct); that
    # genuinely-ambiguous case falls through to the orphan warning instead.
    # Multi-head printers (XL / future INDX toolchanger) keep their per-tool map
    # untouched — there the tool index IS the toolhead position (1:1).
    try:
        if len(usage_map) == 1:
            pm = locations_db.get_active_printer_map()
            positions = {info.get('position', 0) for info in pm.values()
                         if info.get('printer_name') == printer_name}
            if len(positions) == 1:
                sole = next(iter(positions))
                grams = next(iter(usage_map.values()))
                usage_map = {sole: grams}
    except Exception:
        pass

    return usage_map, None


def deduct_cancelled_print(printer_name, filename, job_id, reached_fraction,
                           fb_url=None, ip_address=None, api_key=None):
    """Compute + AUTO-APPLY the PARTIAL filament deduct for a CANCELLED print
    (FilaBridge absorption design §9). Exactly-once via the (printer, job_id)
    ledger; NEVER deducts the full estimate (that's the ~10x over-charge a
    cancel must avoid). Returns a status dict:

      status='skipped'   already deducted (ledger hit) — no-op
      status='no_usage'  cancelled before extrusion / no metadata — recorded, 0g
      status='deducted'  partial grams applied; carries spools_updated + details
      status='error'     credentials / gcode download failed (NOT recorded, so a
                         later retry can still deduct)

    NOTE: the live cancel-EDGE no longer calls this — slice 5 routes cancels
    through _create_pending_cancel_review (preview-and-confirm, §9.7). This
    remains the canonical "compute-and-apply-in-one-shot" primitive (a future
    opt-in auto-mode / recompute action can call it) and shares its compute half
    with the preview path via _compute_cancel_usage.
    """
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()

    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already deducted", "job_id": job_id}

    if not (ip_address and api_key):
        creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
        if not creds:
            return {"status": "error", "reason": "no credentials", "job_id": job_id}
        ip_address, api_key = creds.get('ip_address'), creds.get('api_key')

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, reached_fraction, ip_address, api_key)
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=reached_fraction, grams=0)
        elif terminal["status"] == "error":
            # This one-shot auto-apply primitive has no retry loop, so surface the
            # download failure (the live preview path defers/retries instead).
            _log_cancel_uncomputable(printer_name, filename, reached_fraction, None)
        return terminal

    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    spools_updated, details, known = _apply_usage_to_printer(
        printer_name, usage_map, fb_url, strategy_label="Cancel")
    if spools_updated == 0:
        # Usage WAS computed but no spool is bound to the toolhead — don't burn a
        # terminal grams=0 ledger entry (it permanently blocks recovery). Stash a
        # RECOVERABLE no_spool review carrying the usage_map, mirroring the completed
        # path's guard, so binding the toolhead later recovers it. (This one-shot
        # primitive isn't on the live edge today — the cancel edge routes through
        # _create_pending_cancel_review — but keep the three apply sites uniform.)
        return _stash_unresolved_review(printer_name, filename, job_id, reached_fraction,
                                        usage_map=usage_map, no_spool=True)
    total = round(sum(d["grams"] for d in details), 1)
    state.add_log_entry(
        f"🛑 Cancelled-print partial deduct on {printer_name}: {total:.1f}g across "
        f"{spools_updated} spool(s) at ~{pct:.0f}% progress ('{filename}').",
        "WARNING")
    # Record the APPLIED grams (was sum(usage_map) = the full requested — the drift
    # the completed/cancel-review paths didn't have; 22.4(2)) + surface any shortfall
    # over known positions (22.4(3)).
    _record_applied_deduct(
        printer_name, job_id, filename=filename, scale=reached_fraction,
        details=details, usage_map=usage_map, known_positions=known)
    return {"status": "deducted", "spools_updated": spools_updated,
            "details": details, "usage_map": usage_map, "job_id": job_id}


def deduct_completed_print(printer_name, filename, job_id, fb_url=None,
                           ip_address=None, api_key=None, start_spools=None,
                           swap_log=None):
    """Compute + AUTO-APPLY the full per-tool deduct for a COMPLETED (FINISHED)
    print — FCC's Phase-2 takeover of FilaBridge's completion deduct. Uses the
    slicer FOOTER (the full per-tool estimate, exact = what FilaBridge billed;
    neither side handles M486), NOT the cancel prefix-parse. Exactly-once via the
    (printer, job_id) ledger. Auto-applies SILENTLY with a ✅ log line — NO
    preview/confirm, because a completion's grams are exact (the cancel review
    exists to nudge the M486/partial over-estimate, which doesn't apply here).

    `start_spools` (22.3): the {position: sid} snapshot captured at print-START. If a
    USED toolhead's mapped spool CHANGED between start and completion (a mid-print
    runout/M600 replace), the full footer would dump the whole tool's usage on the
    REPLACEMENT spool and record 0g on the run-out spool — both wrong. In that case
    we route the completion to the cancel-REVIEW pipeline (for a manual split)
    instead of auto-applying. None (the deferred-fetch retry, a restart that lost
    the snapshot, a capture failure) → skip detection → today's auto-apply (safe).

    `swap_log` (22.3(b)): the ordered list of mid-print swap events captured at each
    resume (see _record_swap_events). It catches a swap the coarse start-vs-end diff
    MISSES — most importantly A→B→A (a spool ran out, was replaced, then the original
    re-loaded, so start==end) — and carries the per-segment history a future
    apportionment will split on. Today a non-empty swap_log at a USED position routes
    the completion to the same manual-split review (safe degrade); the validated
    automatic per-segment split lands once Derek's real M600 data confirms the math.

    On a download lock/blip returns 'awaiting_fetch' and queues a deferred fetch
    (kind='complete'): a Connect-STARTED finished print locks the file behind the
    finish screen, exactly like a cancel's cancel-screen lock — the monitor
    retries once the printer leaves FINISHED. Same status-dict shape as
    deduct_cancelled_print. Gated by the fcc_owns_completion_deduct flag at the
    EDGE (this primitive itself is unconditional, so the deferred-fetch retry can
    still finish a completion enqueued while the flag was on)."""
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already deducted", "job_id": job_id}
    if not (ip_address and api_key):
        creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
        if not creds:
            _enqueue_cancel_fetch(printer_name, filename, job_id, 1.0, kind="complete",
                                  start_spools=start_spools, swap_log=swap_log)
            return {"status": "awaiting_fetch", "reason": "no credentials", "job_id": job_id}
        ip_address, api_key = creds.get('ip_address'), creds.get('api_key')

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, 1.0, ip_address, api_key, use_footer=True)
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=1.0, grams=0)
            state.add_log_entry(
                f"✅ Completed print on {printer_name} ('{filename}') — no filament "
                f"usage in the footer; nothing to deduct.", "INFO")
        elif terminal["status"] == "error":
            # Download failed — the Connect finish-screen LOCK (the completion
            # analogue of the cancel-screen lock §9.10). Defer; the monitor
            # retries once the printer leaves FINISHED (→ IDLE, file unlocked).
            # Carry start_spools + swap_log so the retry still detects a mid-print
            # spool swap (the live latch is gone by then; 22.3 deferred-completion fix).
            _enqueue_cancel_fetch(printer_name, filename, job_id, 1.0, kind="complete",
                                  start_spools=start_spools, swap_log=swap_log)
            return {"status": "awaiting_fetch", "reason": terminal.get("reason"),
                    "job_id": job_id}
        return terminal

    # Resolve the printer's active toolheads ONCE and share it with both the swap
    # detection read and the apply, so an MMU printer's info.mmu ordering probe runs
    # once (22.4(5) pattern).
    printer_map = locations_db.get_active_printer_map()
    active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    # 22.3: mid-print spool-swap guard. If a USED toolhead's mapped spool changed
    # during the print, the full footer would mis-attribute the whole tool's usage to
    # the replacement — route to a manual-split review instead of auto-applying. Two
    # detectors, unioned: (22.3c) a coarse start-vs-END snapshot diff, and (22.3b) the
    # ordered swap_log captured at each resume. swap_log catches a swap the 2-point
    # diff misses — notably A→B→A (ran out, replaced, original re-loaded → start==end).
    # Best-effort: any detection error falls through to auto-apply (NEVER block/drop a
    # completion on a detection bug).
    if start_spools or swap_log:
        try:
            changed = set()
            used_positions = {p for p, g in usage_map.items() if g > 0}
            if start_spools:
                end_snap = _snapshot_active_spools(printer_name, fb_url, active_locs=active_locs)
                for pos in used_positions:
                    # Only a clean 1→1 sid change flags. None on EITHER side (empty/
                    # ambiguous/orphan at start or end) is NOT a confident swap signal —
                    # the no_spool/shortfall/ambiguous-skip machinery covers those. Shared
                    # _is_sid_swap predicate (string-compare; no int() so a non-numeric sid
                    # can't ValueError into a silently-swallowed auto-apply).
                    if _is_sid_swap(start_spools.get(str(pos)), end_snap.get(pos)):
                        changed.add(pos)
            if swap_log:
                # A captured resume swap at a USED position — already validated 1→1 at
                # capture time (_record_swap_events), so no re-snapshot needed.
                for ev in swap_log:
                    if ev.get('position') in used_positions:
                        changed.add(ev.get('position'))
            if changed:
                return _route_completion_to_review(
                    printer_name, filename, job_id, usage_map, fb_url, sorted(changed),
                    active_locs=active_locs, swap_log=swap_log,
                    ip_address=ip_address, api_key=api_key, start_spools=start_spools)
        except Exception:
            pass  # detection is best-effort; fall through to auto-apply

    spools_updated, details, known = _apply_usage_to_printer(
        printer_name, usage_map, fb_url, strategy_label="Complete", active_locs=active_locs)
    if spools_updated == 0:
        # Footer had usage but NO spool is bound at the active toolhead(s). Don't
        # burn a terminal grams=0 ledger entry (it permanently blocks recovery —
        # the 2026-06-13 silent-loss bug); stash a RECOVERABLE review carrying the
        # footer usage_map so the confirm path re-resolves + applies once a spool is
        # bound. apply wrote nothing when spools_updated==0, so there's nothing to
        # undo.
        return _stash_unresolved_review(printer_name, filename, job_id, 1.0,
                                        usage_map=usage_map, no_spool=True)
    # Record what was ACTUALLY deducted, not the full footer estimate: on a
    # multi-tool print where one toolhead has a spool and another doesn't,
    # _apply_usage_to_printer deducts only the bound one(s), so sum(usage_map) would
    # over-state the ledger and (single (printer,job_id) key) the unbound position's
    # grams can't be held pending alongside this recorded deduct. _record_applied_deduct
    # records the applied grams + surfaces any shortfall over KNOWN positions (an
    # orphan tool index already warned inside the apply loop, so it's excluded here
    # to avoid a double-warn — 22.4(2)/(3)).
    applied = round(sum(d["grams"] for d in details), 2)
    state.add_log_entry(
        f"✅ Completed-print deduct on {printer_name}: {applied:.1f}g across "
        f"{spools_updated} spool(s) ('{filename}').", "SUCCESS")
    _record_applied_deduct(
        printer_name, job_id, filename=filename, scale=1.0, details=details,
        usage_map=usage_map, known_positions=known)
    return {"status": "deducted", "spools_updated": spools_updated,
            "details": details, "usage_map": usage_map, "job_id": job_id}


def _tool_grams(cum, pos):
    """Grams at toolhead position `pos` from a per-tool prefix-parse/footer dict.
    Single-extruder prints fold onto one tool, so a sole entry IS this position."""
    if not cum:
        return 0.0
    if pos in cum:
        return float(cum[pos])
    if str(pos) in cum:
        return float(cum[str(pos)])
    if len(cum) == 1:
        return float(next(iter(cum.values())))
    return 0.0


def _compute_swap_split(ip_address, api_key, filename, usage_map, swap_log,
                        start_spools, path_filament_g=0.0):
    """22.3(b): compute the per-segment spool→grams split for a COMPLETED print whose
    toolhead spool changed mid-print (runout or a deliberate early swap). Returns
    ``{position: [ {sid, grams, segment, runout}, … ]}`` — one row per spool that fed
    the position, each charged only ITS segment's grams — or ``None`` on any failure so
    the caller degrades to the full-footer manual-split review.

    Per position: segment 0's spool = ``start_spools[pos]`` (the original / run-out);
    segment k's spool = the k-th swap's ``to_sid``. Segment grams = the prefix-parse
    cumulative diff at the swap boundaries; the LAST segment = footer − prior, so the
    per-spool grams sum EXACTLY to the slicer's per-tool total (no E-walk drift). On a
    segment whose ending swap is a RUNOUT (``ev['runout']``), ``path_filament_g`` (the
    sensor→nozzle remnant that leaves the spool but never deposits — pulled at the swap)
    is added to that run-out spool.
    """
    if not swap_log:
        return None
    # Fetch+decode ONCE; cumulative grams at every swap boundary (progress order).
    all_events = sorted(swap_log, key=lambda e: (e.get('position', 0),
                                                 float(e.get('progress') or 0.0)))
    progresses = [float(e.get('progress') or 0.0) for e in all_events]
    seg = prusalink_api.compute_segment_usage(ip_address, api_key, filename, progresses)
    if not seg:
        return None
    footer = seg.get('footer') or {}
    cums = seg.get('cums') or []
    if len(cums) != len(all_events):
        return None
    cum_by_id = {id(ev): cums[i] for i, ev in enumerate(all_events)}

    by_pos = {}
    for ev in swap_log:
        by_pos.setdefault(ev.get('position', 0), []).append(ev)

    start_spools = start_spools or {}
    result = {}
    for pos, evs in by_pos.items():
        evs = sorted(evs, key=lambda e: float(e.get('progress') or 0.0))
        footer_pos = _tool_grams(footer, pos)
        if footer_pos <= 0:
            return None  # no footer grams for a swapped position → don't guess
        seg_grams, prev = [], 0.0
        for ev in evs:
            c = _tool_grams(cum_by_id.get(id(ev)) or {}, pos)
            # Cumulative must be monotonic and within the footer; a bad remap/parse
            # that regresses or overshoots means we can't trust the split.
            if c < prev - 0.01 or c > footer_pos + 0.01:
                return None
            seg_grams.append(max(0.0, c - prev))
            prev = c
        seg_grams.append(max(0.0, footer_pos - prev))  # tail segment ties to the total
        seg_spools = [start_spools.get(str(pos)) or start_spools.get(pos)]
        for ev in evs:
            seg_spools.append(ev.get('to_sid'))
        rows = []
        for k, (sid, grams) in enumerate(zip(seg_spools, seg_grams)):
            if sid is None:
                continue
            is_runout = bool(k < len(evs) and evs[k].get('runout'))
            extra = path_filament_g if (is_runout and path_filament_g) else 0.0
            rows.append({'sid': sid, 'grams': round(grams + extra, 2),
                         'segment': k, 'runout': is_runout})
        if rows:
            result[pos] = rows
    return result or None


def _path_filament_g(printer_name):
    """Per-printer sensor->nozzle filament (grams) charged to a RUN-OUT spool: the
    remnant that leaves the spool but never deposits on the part (the user pulls it
    at the swap). Read from config `path_filament_g` — a {printer_name: grams} map
    (with an optional 'default'), or a scalar applied to all printers. 0.0 when
    unset, so the split is deposited-only (a couple grams light on the run-out
    spool, which usually gets run to empty anyway). Core One ~2 g, XL ~4 g."""
    try:
        cfg = config_loader.load_config() or {}
    except Exception:
        return 0.0
    pf = cfg.get('path_filament_g')
    if isinstance(pf, dict):
        v = pf.get(printer_name, pf.get('default', 0))
    elif isinstance(pf, (int, float)):
        v = pf
    else:
        v = 0
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return 0.0


def _split_to_review_rows(split):
    """Turn a :func:`_compute_swap_split` result (``{position: [{sid, grams, segment,
    runout}, …]}``) into cancel-review ``spools`` rows — one row per spool, charged its
    OWN segment's grams, with the current used/remaining snapshot for display. Archived
    run-out spools resolve by sid. Same-sid segments (an A→B→A re-load) are SUMMED so
    there is exactly one row per spool (the confirm loop keys by sid, so two same-sid
    rows would silently collapse to one deduct). Returns ``None`` if any spool can't be
    read, so the caller falls back to the full-footer manual review."""
    by_sid = {}
    for pos, seg_rows in split.items():
        for r in seg_rows:
            sid = r['sid']
            agg = by_sid.setdefault(sid, {'grams': 0.0, 'position': pos, 'runout': False})
            agg['grams'] += float(r.get('grams', 0) or 0)
            agg['runout'] = agg['runout'] or bool(r.get('runout'))
    rows = []
    for sid, agg in by_sid.items():
        spool = spoolman_api.get_spool(sid)
        if not spool:
            return None
        used = float(spool.get('used_weight', 0) or 0)
        initial = float(spool.get('initial_weight', 0) or 0)
        grams = round(agg['grams'], 2)
        remaining_before = max(0.0, initial - used)
        remaining_after = max(0.0, remaining_before - grams)
        disp = spoolman_api.format_spool_display(spool)
        rows.append({
            'sid': sid,
            'toolhead': '',
            'position': agg['position'],
            'grams': grams,
            'current_used': round(used, 2),
            'initial_weight': round(initial, 2),
            'remaining_before': round(remaining_before, 1),
            'remaining_after': round(remaining_after, 1),
            'display': disp.get('text', "#%s" % sid),
            'color': disp.get('color', '888888'),
            'ambiguous': False,
            'runout': agg['runout'],
            'auto_split': True,
        })
    rows.sort(key=lambda r: r['sid'])
    return rows or None


def _route_completion_to_review(printer_name, filename, job_id, usage_map, fb_url,
                               changed_positions, active_locs=None, swap_log=None,
                               ip_address=None, api_key=None, start_spools=None):
    """22.3 minimum-viable: a COMPLETED print where a used toolhead's mapped spool
    CHANGED mid-print is NOT auto-applied (the full footer would dump the whole
    tool's usage on the replacement spool, zeroing the run-out spool). Stash a
    'spool_changed' review carrying the completion-time preview rows so the user
    splits the grams manually — reusing the cancel-review confirm pipeline verbatim
    (api_cancel_deduct_confirm routes any kind with `spools` rows through the per-sid
    partial loop). Writes NO ledger (confirm/dismiss owns that), so exactly-once
    holds via the review store + ledger guards.

    `swap_log` (22.3(b)) is persisted on the review record for two reasons: it's the
    per-segment history a validated automatic apportionment will split on, and it lets
    the review surface "this spool ran during segment k" context. It does NOT change
    today's behavior (the user still splits manually) — it's carried, not yet consumed
    for the math."""
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        # Already settled — clear any stale pending so "ledger ⟹ no pending" holds.
        cancel_review_store.pop_pending(printer_name, job_id)
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}
    # 22.3(b) AUTO-SPLIT: when the gcode is fetchable, charge EACH spool that fed the
    # toolhead only its OWN segment's grams (run-out spool 0->swap, replacement
    # swap->end) so both are shown + settled together. Degrades to the full-footer
    # manual review when there's no swap_log (coarse start-vs-end diff only) or the
    # gcode can't be fetched/parsed. The confirm loop applies every `spools` row by
    # sid, so there's no confirm-side change either way.
    split_rows = None
    if swap_log and ip_address and api_key:
        split = _compute_swap_split(
            ip_address, api_key, filename, usage_map, swap_log,
            start_spools, path_filament_g=_path_filament_g(printer_name))
        if split:
            split_rows = _split_to_review_rows(split)
    auto_split = bool(split_rows)
    rows = split_rows or _resolve_usage_to_spools(
        printer_name, usage_map, fb_url, active_locs=active_locs)
    if not rows:
        # The replacement isn't bound right now — still recoverable via no_spool.
        # (Shouldn't usually reach here: a flagged position has a bound end spool.)
        return _stash_unresolved_review(printer_name, filename, job_id, 1.0,
                                        usage_map=usage_map, no_spool=True)
    # Claim the deferred-fetch slot too, so a queued kind='complete' retry (a prior
    # finish-screen lock) can't later auto-apply the full footer behind this review.
    cancel_fetch_store.pop_pending(printer_name, job_id)
    total = round(sum(r['grams'] for r in rows), 2)
    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": 1.0,
        "total_grams": total,
        "spools": rows,
        "ambiguous": False,
        "kind": "spool_changed",
        # 22.3(b): True when the per-segment grams were AUTO-computed (each row's
        # `grams` is that spool's OWN segment, pre-filled for one-tap confirm);
        # False = the legacy full-footer-on-current-spool manual split.
        "auto_split": auto_split,
        "changed_positions": sorted(changed_positions),
        # The ordered mid-print swap history (empty when only the coarse start-vs-end
        # diff fired) — the per-segment source + the review's context.
        "swap_log": list(swap_log) if swap_log else [],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    how = "auto-split proposed" if auto_split else "full footer NOT auto-applied"
    state.add_log_entry(
        f"🔁 {printer_name}: spool changed mid-print ('{filename}') at toolhead "
        f"position(s) {sorted(changed_positions)} — {how}; "
        f"review the split: {total:.2f}g across {len(rows)} spool(s).",
        "WARNING", rows[0]['color'],
        meta={"type": "cancel_deduct_pending",
              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending_spool_changed", "spools": len(rows),
            "job_id": str(job_id), "auto_split": auto_split}


def _resolve_usage_to_spools(printer_name, usage_map, fb_url, active_locs=None):
    """Read-only resolution of {toolhead_position: grams} → the per-spool rows a
    deduct WOULD touch — the cancel-review PREVIEW (no write). Mirrors
    _apply_usage_to_printer's MMU-alias/dedup AND ghost-vs-current resolution
    (`select_deduct_targets`), minus the write, so the preview is faithful to what
    a confirm will deduct. The one deliberate divergence: where the autonomous
    apply SKIPS a genuinely-ambiguous toolhead (2+ distinct loaded spools), this
    interactive preview KEEPS both rows flagged `ambiguous` so the reviewer can see
    the bad assignment and choose. Each row carries a snapshot of the spool's
    current used/remaining for display; the actual write (confirm) re-reads current
    used and applies additively, so a weigh-out between preview and confirm can't be
    clobbered. `active_locs` may be passed pre-resolved to share an MMU probe with a
    paired _apply_usage_to_printer call (22.4(5)); None re-resolves it here.
    """
    if active_locs is None:
        printer_map = locations_db.get_active_printer_map()
        active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    rows = []
    processed_positions = set()
    for loc_id, p_info in active_locs:
        pos = p_info.get('position', 0)
        if pos in processed_positions:
            continue
        if pos not in usage_map:
            continue
        grams = usage_map[pos]
        if grams <= 0:
            continue
        loc_spools = spoolman_api.get_spools_at_location(loc_id)
        if not loc_spools:
            continue  # try the next alias for this position
        processed_positions.add(pos)
        # Mirror the apply loop's ghost-vs-current resolution (22.4(1)); only the
        # rare >1 case fetches the detailed/ghost info, so the single-spool path is
        # unchanged. Preview keeps an ambiguous toolhead's rows (flagged) rather
        # than skipping, so the reviewer can resolve it.
        ambiguous = False
        if len(loc_spools) > 1:
            loc_spools, ambiguous = spoolman_api.select_deduct_targets(loc_id)
        for sid in loc_spools:
            spool = spoolman_api.get_spool(sid)
            if not spool:
                continue
            used = float(spool.get('used_weight', 0) or 0)
            initial = float(spool.get('initial_weight', 0) or 0)
            remaining_before = max(0.0, initial - used)
            remaining_after = max(0.0, remaining_before - grams)
            disp = spoolman_api.format_spool_display(spool)
            rows.append({
                'sid': sid,
                'toolhead': str(loc_id).upper(),
                'position': pos,
                'grams': round(float(grams), 2),
                'current_used': round(used, 2),
                'initial_weight': round(initial, 2),
                'remaining_before': round(remaining_before, 1),
                'remaining_after': round(remaining_after, 1),
                'display': disp.get('text', f"#{sid}"),
                'color': disp.get('color', '888888'),
                'ambiguous': bool(ambiguous),
            })

    # Merge rows that resolve to the SAME spool. One physical spool can feed more
    # than one toolhead position (a shared-spool config, or the dev XL-4/XL-5=
    # #230 case), producing two rows for one sid. The confirm path keys updates
    # by sid (frontend `updates[sid]` + backend `rec_rows={sid:row}`), so two
    # same-sid rows would COLLAPSE to a single deduct — a silent under-deduct
    # (found 2026-06-12: job 690 previewed 1.65g but only ~0.8g applied). Sum the
    # grams here so there's exactly one row per spool: the spool loses filament
    # once, totalled across every position it fed.
    merged = {}
    for r in rows:
        m = merged.get(r['sid'])
        if m is None:
            merged[r['sid']] = r
        else:
            m['grams'] = round(m['grams'] + r['grams'], 2)
            m['remaining_after'] = round(max(0.0, m['remaining_before'] - m['grams']), 1)
            if str(r['toolhead']) not in str(m['toolhead']).split(', '):
                m['toolhead'] = f"{m['toolhead']}, {r['toolhead']}"
            # Same-sid rows can't differ in `ambiguous` by construction (a 2+-distinct
            # case yields different sids that never merge), but OR defensively so the
            # flag can't be silently dropped if the row schema grows.
            m['ambiguous'] = bool(m.get('ambiguous')) or bool(r.get('ambiguous'))
    return list(merged.values())


def _stash_unresolved_review(printer_name, filename, job_id, reached_fraction,
                             usage_map=None, *, no_spool=False,
                             progress_unknown=False, ambiguous=False):
    """Stash a persistent, RECOVERABLE review for a print whose usage couldn't be
    finalized — INSTEAD of writing a destructive terminal grams=0 ledger entry that
    would permanently block recovery (the 2026-06-13 silent-loss bug). Two kinds:

      no_spool         — usage WAS computed (real grams in `usage_map`) but NO spool
                         is bound to the toolhead, so there's nowhere to deduct. The
                         confirm endpoint RE-RESOLVES `usage_map` to whatever spool is
                         bound at apply time, so binding the toolhead later recovers it.
      progress_unknown — the print was replaced (a back-to-back job change) before we
                         ever sampled a real progress, so its usage is genuinely
                         UNMEASURABLE (`usage_map` is None). Surfaced non-destructively
                         ("weigh the spool and adjust it directly, or Discard").

    Writes NO ledger entry — the review stays recoverable until confirm/dismiss.
    Idempotent: no-ops if a review is already pending or the job was already settled.
    Returns a status dict."""
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}

    usage_map = usage_map or {}
    total = round(sum(usage_map.values()), 2) if usage_map else 0.0
    # Binary on purpose: this helper ONLY stashes UNRESOLVED reviews. A neither-flag
    # call must NOT produce kind='partial' — that record (empty spools, no usage_map)
    # would route into the confirm partial loop and 0g-burn the ledger. Default the
    # (caller-error) neither case to the non-destructive progress_unknown kind.
    kind = "no_spool" if no_spool else "progress_unknown"

    if no_spool:
        msg = (f"⚠️ {printer_name}: print used ~{total:.2f}g ('{filename}') but it "
               f"couldn't be deducted (no spool bound to the toolhead, or the write was "
               f"rejected) — Review to apply once it's bound, or Discard.")
    else:  # progress_unknown
        msg = (f"❓ {printer_name}: couldn't measure how much '{filename}' used (replaced "
               f"before a progress reading) — Review to weigh the spool, or Discard.")

    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": float(reached_fraction or 0.0),
        "total_grams": total,
        "spools": [],
        "ambiguous": bool(ambiguous),
        "kind": kind,
        # usage_map drives the confirm RE-RESOLVE for a no_spool review. JSON
        # stringifies int keys on save, so store them as strings explicitly and let
        # the confirm path coerce back to int (the resolve keys on int positions).
        "usage_map": ({str(k): v for k, v in usage_map.items()}
                      if (no_spool and usage_map) else None),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    state.add_log_entry(msg, "WARNING", "ffaa00",
                        meta={"type": "cancel_deduct_pending",
                              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending_unresolved", "kind": kind, "total_grams": total,
            "job_id": str(job_id)}


def _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction, kind="cancel",
                          ambiguous=False, start_spools=None, swap_log=None):
    """Queue a print whose gcode couldn't be fetched yet (the selected-file
    download LOCK, §9.10) for the monitor to retry. `kind` is 'cancel' (default)
    or 'complete' — a COMPLETED Connect-started print locks behind the FINISH
    screen the same way a cancel locks behind the cancel screen; the kind is
    stashed on the record so _process_pending_cancel_fetches routes the retry to
    the right handler (cancel→review, complete→auto-apply). `ambiguous` (carried
    on the record, only meaningful for kind='cancel') means the edge couldn't
    confirm cancel vs completion, so the retried review stays flagged.
    `start_spools` (22.3, kind='complete' only) is the print-start spool snapshot —
    persisted on the record so the deferred completion retry still gets mid-print
    spool-swap detection (the live latch is gone by retry time). `swap_log` (22.3(b),
    kind='complete') is the ordered mid-print swap history, persisted the same way so a
    deferred completion still detects an A→B→A swap the start-vs-end diff would miss.
    Idempotent:
    re-queuing the same job bumps `attempts`, PRESERVES `first_seen` (so the
    max-age give-up window is measured from the FIRST sighting), and does NOT
    re-nudge. The nudge logs exactly ONCE, on first queue. Returns True if newly
    queued (nudged), False if it was already queued."""
    if cancel_fetch_store.has_pending(printer_name, job_id):
        rec = cancel_fetch_store.get_pending(printer_name, job_id) or {}
        rec.update({"printer_name": printer_name, "job_id": str(job_id),
                    "filename": filename, "progress": float(reached_fraction),
                    "kind": kind, "ambiguous": bool(ambiguous),
                    # Preserve an already-captured snapshot/log if this re-queue lacks one.
                    "start_spools": start_spools or rec.get("start_spools"),
                    "swap_log": swap_log or rec.get("swap_log"),
                    "attempts": int(rec.get("attempts", 0)) + 1})
        cancel_fetch_store.add_pending(rec)
        return False
    cancel_fetch_store.add_pending({
        "printer_name": printer_name, "job_id": str(job_id), "filename": filename,
        "progress": float(reached_fraction), "first_seen": time.time(),
        "kind": kind, "ambiguous": bool(ambiguous), "start_spools": start_spools,
        "swap_log": swap_log,
        "attempts": 1, "last_status": "awaiting_fetch",
    })
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    if ambiguous:
        # The ambiguous edge fires at IDLE (file already unlocked), so this path
        # is only a transient blip — use neutral wording (NOT "clear the screen").
        state.add_log_entry(
            f"❓ Print on {printer_name} (~{pct:.0f}%, '{filename}') ended without a "
            f"clear cancel/finish signal and its gcode isn't readable yet — I'll "
            f"retry and surface a review when it's readable.",
            "WARNING", "ffaa00",
            meta={"type": "cancel_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    elif kind == "complete":
        state.add_log_entry(
            f"✅ Completed print on {printer_name} ('{filename}') detected — the "
            f"printer is still showing the finish screen, so the gcode is locked. "
            f"Clear it on the printer and I'll record the deduct automatically.",
            "INFO",
            meta={"type": "complete_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    else:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} (~{pct:.0f}%, '{filename}') detected — "
            f"the printer is still showing the cancel screen, so the gcode is locked. "
            f"Clear it on the printer and I'll record the partial deduct automatically.",
            "WARNING", "ffaa00",
            meta={"type": "cancel_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    return True


def _create_pending_cancel_review(printer_name, filename, job_id, reached_fraction,
                                  fb_url=None, ambiguous=False, progress_unknown=False):
    """Compute the cancelled-print partial and STASH it for review instead of
    auto-writing (FilaBridge absorption design §9.7). Idempotent against the
    ledger (already confirmed/dismissed) and the pending store (already queued).
    On success raises a 'cancel_deduct_pending' activity-log line (with meta) so
    the dashboard shows a "🛑 Review" button. Returns a status dict.

    ambiguous=True (2026-06-13): the print reached idle WITHOUT an observed
    terminal state, so we couldn't confirm cancel vs completion. The compute is
    identical (the partial at `reached_fraction`, the retained progress = the
    confidence hint), but the record is flagged and the log/overlay reword to
    "couldn't confirm". Still NEVER auto-deducts — it's a review either way."""
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()

    if print_deduct_ledger.was_deducted(printer_name, job_id):
        # Already confirmed/dismissed. Clear any stale pending so the invariant
        # "ledger ⟹ no pending" holds even after an odd crash sequence.
        cancel_review_store.pop_pending(printer_name, job_id)
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}

    if progress_unknown:
        # We never sampled a real progress for this job (a back-to-back job change
        # replaced it before the monitor measured it). Prefix-parsing at 0% would
        # fold to a misleading no_usage 0g and permanently lose it; the footer would
        # massively over-deduct. So don't compute or download — stash a
        # non-destructive "couldn't measure usage — weigh the spool" review.
        return _stash_unresolved_review(printer_name, filename, job_id,
                                        reached_fraction, usage_map=None,
                                        progress_unknown=True, ambiguous=ambiguous)

    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
    if not creds:
        # No creds right now (FilaBridge blip / printer briefly unreachable) —
        # retryable, so queue a deferred fetch rather than telling Derek to weigh.
        _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction,
                              ambiguous=ambiguous)
        return {"status": "awaiting_fetch", "reason": "no credentials", "job_id": job_id}

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, reached_fraction,
        creds.get('ip_address'), creds.get('api_key'))
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=reached_fraction, grams=0)
        elif terminal["status"] == "error":
            # Download failed — almost always the selected-file LOCK (§9.10): the
            # file un-locks once Derek clears the cancel screen (→ IDLE). Queue a
            # deferred fetch; the monitor retries each tick once the printer
            # leaves STOPPED, then computes + pops the 🛑 Review automatically.
            # (For the ambiguous edge the file is already unlocked at IDLE, so
            # this is just a transient-blip safety net — but carry the flag so a
            # retried review stays flagged "couldn't confirm".)
            _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction,
                                  ambiguous=ambiguous)
            return {"status": "awaiting_fetch", "reason": terminal.get("reason"),
                    "job_id": job_id}
        return terminal

    rows = _resolve_usage_to_spools(printer_name, usage_map, fb_url)
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    lead = ("❓ Print on {p} reached idle (~{pct:.0f}%, couldn't confirm cancel vs "
            "complete)").format(p=printer_name, pct=pct) if ambiguous else \
           "🛑 Cancelled print on {p} (~{pct:.0f}%)".format(p=printer_name, pct=pct)
    if not rows:
        # The print extruded filament but NO spool is bound to the active
        # toolhead(s) — nothing to deduct from RIGHT NOW. Don't burn a terminal
        # grams=0 ledger entry (that permanently blocks recovery — the 2026-06-13
        # silent-loss bug); stash a RECOVERABLE review carrying the computed
        # usage_map so the confirm path can re-resolve + apply once Derek binds the
        # toolhead.
        return _stash_unresolved_review(printer_name, filename, job_id,
                                        reached_fraction, usage_map=usage_map,
                                        no_spool=True, ambiguous=ambiguous)

    # Re-check after the (slow) gcode download+parse — if the job was processed
    # in the meantime, don't stash a stale pending.
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}

    total = round(sum(r['grams'] for r in rows), 2)
    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": float(reached_fraction),
        "total_grams": total,
        "spools": rows,
        "ambiguous": bool(ambiguous),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    state.add_log_entry(
        f"{lead} — review {'computed' if ambiguous else 'partial'} "
        f"deduct: {total:.2f}g across {len(rows)} spool(s) ('{filename}').",
        "WARNING", rows[0]['color'],
        meta={"type": "cancel_deduct_pending",
              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending", "spools": len(rows), "total_grams": total,
            "job_id": str(job_id)}


@app.route('/api/cancel_deduct/pending', methods=['GET'])
def api_cancel_deduct_pending():
    """All pending cancelled-print partial-deduct reviews awaiting confirm/
    dismiss. Drives the preview overlay (§9.7) and survives log scroll-off /
    restart."""
    return jsonify({"pending": cancel_review_store.list_pending()})


def _confirm_no_spool_review(printer, job_id, rec):
    """Apply a `no_spool` review (the record was already popped = the claim). The
    usage was computed when the print ended but no spool was bound; RE-RESOLVE the
    stored usage_map against whatever spool is bound to the toolhead NOW and apply
    it additively (ONLY {used_weight}, archive-on-empty discipline, via the canonical
    _apply_usage_to_printer loop). If still unbound, RE-STASH the record so it stays
    recoverable and report `still_no_spool` — never a terminal 0g."""
    _, fb_url = config_loader.get_api_urls()
    # Resolve the printer's active toolheads ONCE and thread it to BOTH the preview
    # resolve and the apply, so an MMU printer's info.mmu ordering probe runs once,
    # not twice (22.4(5)). The apply returns the real toolhead positions (`known`)
    # so the shortfall excludes orphan tool indices (22.4(3)).
    printer_map = locations_db.get_active_printer_map()
    active_locs = _resolve_active_locs_for_printer(printer_map, printer, fb_url)
    # JSON stringified the int positions on save — coerce back so the resolve (which
    # keys on int positions from printer_map) matches. Without this the re-resolve
    # silently finds nothing and always says "still no spool".
    umap = {}
    for k, v in (rec.get("usage_map") or {}).items():
        try:
            umap[int(k)] = float(v)
        except (TypeError, ValueError):
            continue
    rows = _resolve_usage_to_spools(printer, umap, fb_url, active_locs=active_locs) if umap else []
    if not rows:
        cancel_review_store.add_pending(rec)  # re-stash UNCHANGED — still recoverable
        return jsonify({"status": "still_no_spool",
                        "msg": "No spool is bound to this printer's toolhead yet — "
                               "bind it in the Location Manager, then Apply."})
    # A monitor retry could have settled this job between the pop and now.
    if print_deduct_ledger.was_deducted(printer, job_id):
        return jsonify({"status": "already_handled"})
    spools_updated, details, known = _apply_usage_to_printer(
        printer, umap, fb_url, strategy_label="Cancel-review", active_locs=active_locs)
    if spools_updated == 0:
        cancel_review_store.add_pending(rec)
        return jsonify({"status": "still_no_spool",
                        "msg": "No spool is bound to this printer's toolhead yet."})
    total = round(sum(d["grams"] for d in details), 2)
    state.add_log_entry(
        f"✔️ Cancel-review deduct {total:.2f}g across {spools_updated} spool(s) on "
        f"{printer} (toolhead now bound).", "SUCCESS")
    # Record applied + surface any shortfall via the shared helper (records confirmed,
    # 2dp warn matching the shortfall_g field, orphan-excluded — 22.4(2)/(3)/(4)).
    _, shortfall = _record_applied_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        details=details, usage_map=umap, known_positions=known, confirmed=True)
    return jsonify({"status": "confirmed", "applied": details, "shortfall_g": shortfall})


@app.route('/api/cancel_deduct/confirm', methods=['POST'])
def api_cancel_deduct_confirm():
    """Apply a reviewed (optionally nudged) cancel partial-deduct. Body:
    {printer_name, job_id, updates: {sid: grams}}. Pops the pending record
    atomically (the CLAIM — a double-submit gets 'already_handled'), then
    deducts each spool ADDITIVELY against its CURRENT used_weight (re-read now,
    so a weigh-out between preview and confirm isn't clobbered) sending ONLY
    {used_weight} (archive-on-empty discipline)."""
    data = request.json or {}
    printer = data.get('printer_name')
    job_id = data.get('job_id')
    updates = data.get('updates') or {}
    if not printer or job_id is None:
        return jsonify({"status": "error", "msg": "missing printer_name/job_id"}), 400

    rec = cancel_review_store.pop_pending(printer, job_id)
    if rec is None:
        return jsonify({"status": "already_handled"})

    kind = rec.get("kind", "partial")
    if kind == "no_spool":
        # Usage was computed earlier but no spool was bound. RE-RESOLVE the stored
        # usage_map against whatever's bound NOW (Derek just bound the toolhead) and
        # apply. The pop above is the claim; _confirm_no_spool_review re-stashes if
        # still unbound so the review is never lost (no terminal 0g). Guard the whole
        # call: an UNEXPECTED raise (corrupt local JSON, a probe error) between the
        # pop and its controlled re-stash points would otherwise lose the popped
        # review with no ledger entry — a silent loss. Re-stash + surface on any raise.
        try:
            return _confirm_no_spool_review(printer, job_id, rec)
        except Exception as e:
            cancel_review_store.add_pending(rec)
            state.add_log_entry(
                f"❌ Cancel-review apply failed for {printer} (job {job_id}): {e} — "
                f"review kept for retry.", "ERROR", "ff4444")
            return jsonify({"status": "error", "msg": str(e)}), 500
    if kind == "progress_unknown":
        # No measured usage + no preview spools — nothing to auto-apply. Don't let
        # the partial loop below 0g-"confirm" it (that would re-lose it). Re-stash
        # and tell the user to weigh + adjust the spool directly, or Discard.
        cancel_review_store.add_pending(rec)
        return jsonify({"status": "manual_only",
                        "msg": "Usage couldn't be measured — weigh the spool and "
                               "adjust it directly, or Discard this review."})

    # Only spools that were in the reviewed preview may be deducted — a stray /
    # crafted update for an out-of-scope sid must never touch a different spool.
    rec_rows = {r["sid"]: r for r in rec.get("spools", [])}

    applied, errors = [], []
    failed_sids = set()
    for sid_raw, grams_raw in updates.items():
        try:
            sid = int(sid_raw)
            grams = float(grams_raw)
        except (TypeError, ValueError):
            continue
        if grams <= 0:
            continue
        if sid not in rec_rows:
            errors.append({"sid": sid, "error": "not in this review"})
            failed_sids.add(sid)
            continue
        spool = spoolman_api.get_spool(sid)
        if not spool:
            errors.append({"sid": sid, "error": "spool not found"})
            failed_sids.add(sid)
            continue
        # Re-read CURRENT used (a weigh-out between preview and confirm isn't
        # clobbered) and clamp grams to the spool's real remaining so the deduct
        # never exceeds capacity and the reported figures match what Spoolman
        # actually stores (update_spool silently caps used_weight ≤ initial).
        used = float(spool.get('used_weight', 0) or 0)
        initial = float(spool.get('initial_weight', 0) or 0)
        grams = min(grams, max(0.0, initial - used))
        if grams <= 0:
            # Spool already empty — nothing to deduct, but it's not a failure.
            applied.append({"sid": sid, "grams": 0.0, "remaining": 0.0})
            continue
        new_used = used + grams
        if spoolman_api.update_spool(sid, {"used_weight": new_used}):
            remaining = max(0.0, initial - new_used)
            info = spoolman_api.format_spool_display(spool)
            state.add_log_entry(
                f"✔️ Cancel-deduct {grams:.2f}g from Spool #{sid} (confirmed): "
                f"[➔ {remaining:.1f}g remaining]", "SUCCESS", info.get('color', '888888'))
            applied.append({"sid": sid, "grams": round(grams, 2), "remaining": round(remaining, 1)})
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            errors.append({"sid": sid, "error": err})
            failed_sids.add(sid)
            state.add_log_entry(
                f"❌ Cancel-deduct failed for Spool #{sid}: {err}", "ERROR", "ff4444")

    if errors:
        # Re-queue ONLY the spools that DIDN'T apply, so a retry can't double-
        # deduct the ones that did. Don't burn the ledger — the job isn't fully
        # done — so the edge stays blocked (has_pending) but a retry is possible.
        leftover = {r["sid"]: r for r in rec.get("spools", []) if r["sid"] in failed_sids}
        if leftover:
            retry_rec = dict(rec)
            retry_rec["spools"] = list(leftover.values())
            cancel_review_store.add_pending(retry_rec)
            # Re-emit the Review affordance so the retry is discoverable even if
            # the original cancel log line has scrolled off.
            state.add_log_entry(
                f"🛑 {len(leftover)} spool(s) still need a cancel-deduct review on "
                f"{printer} (a deduct failed) — Review to retry.",
                "WARNING", "ffaa00",
                meta={"type": "cancel_deduct_pending",
                      "printer_name": printer, "job_id": str(job_id)})
        status = "confirmed" if applied else "error"
        return jsonify({"status": status, "applied": applied, "errors": errors})

    # Full success — commit the ledger (exactly-once across restart/retry).
    print_deduct_ledger.record_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        grams=round(sum(a['grams'] for a in applied), 2), confirmed=True)
    return jsonify({"status": "confirmed", "applied": applied, "errors": errors})


@app.route('/api/cancel_deduct/dismiss', methods=['POST'])
def api_cancel_deduct_dismiss():
    """Dismiss a pending cancel review without deducting. Body:
    {printer_name, job_id}. Records the ledger (so it can't re-surface) and pops
    the pending record."""
    data = request.json or {}
    printer = data.get('printer_name')
    job_id = data.get('job_id')
    if not printer or job_id is None:
        return jsonify({"status": "error", "msg": "missing printer_name/job_id"}), 400
    rec = cancel_review_store.pop_pending(printer, job_id)
    if rec is None:
        return jsonify({"status": "already_handled"})
    print_deduct_ledger.record_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        grams=0, dismissed=True)
    state.add_log_entry(
        f"🚫 Dismissed cancel-deduct review for {printer} (job {job_id}) — "
        f"no weight deducted.", "INFO")
    return jsonify({"status": "dismissed"})
