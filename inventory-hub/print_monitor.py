"""Print-edge detection + cancel-monitor daemon (L316 step 11).

Moved verbatim from app.py: the module-global print latch (_PRINT_TRACKER +
_PRINT_TRACKER_LOCK) and state frozensets, the _CANCEL_DEDUCT_RUN_ASYNC
test seam, _fcc_owns_completion_deduct, the cancel/completion/ambiguous
edge handlers + dispatchers, _track_print_edge, the adaptive
_cancel_monitor_tick / _cancel_monitor_loop daemon, the deferred-fetch
retry queue, restart recovery, and the boot credential seed.

Wiring notes:
- Calls INTO print_deduct are module-qualified (print_deduct.deduct_completed_print
  etc.) so tests that patch symbols on print_deduct intercept them; this was
  the only text change in the move (bare names -> module-qualified).
- The credential seed calls startup_migrations._prune_locations_backups.
- NOTHING here starts at import time: the daemon spawn + creds seed remain
  under app.py's __main__ block (the whole unit suite depends on importing
  the app family without spawning the daemon).
- Tests patch/assign the mutable globals ON THIS MODULE (repointed from
  `app` in the same commit); app.py re-exports keep read paths working.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import time
import threading

import state  # type: ignore
import config_loader  # type: ignore
import locations_db  # type: ignore
import prusalink_api  # type: ignore
import print_deduct_ledger  # type: ignore
import cancel_review_store  # type: ignore
import cancel_fetch_store  # type: ignore
import print_tracker_store  # type: ignore

import print_deduct  # type: ignore
import startup_migrations  # type: ignore



# ---------------------------------------------------------------------------
# Cancelled-print detection — rides the dashboard-pulse printer-state probe
# (FilaBridge absorption design §9.3 / build slice 2a).
#
# _pulse_section_printer_status already probes every printer's PrusaLink state
# on each heartbeat. We piggyback on that probe: while a print is IN PROGRESS we
# latch its filename / job_id / monotonic byte-progress (PrusaLink tears the job
# block down the instant the print STOPS, so we MUST capture it beforehand),
# and on the →STOPPED/ERROR edge we fire deduct_cancelled_print with the latched
# values on a background thread. The persistent print_deduct_ledger keeps the
# deduct exactly-once across ticks and restarts.
#
# First ship is cancel-only (STOPPED/ERROR). FINISHED stays with FilaBridge
# until the Phase-2 atomic cutover — firing on FINISHED here would
# double-deduct prints FilaBridge already deducts.
# ---------------------------------------------------------------------------

# {printer_name: {"state": str, "job_id", "filename", "progress", "file_meta"}}
_PRINT_TRACKER = {}
_PRINT_TRACKER_LOCK = threading.Lock()

# A print is "running" (so we latch the job) in any of these states — a pause is
# still running. Mirrors the frontend Phase-0 _PRINT_INPROGRESS_STATES.
_INPROGRESS_PRINT_STATES = frozenset({"PRINTING", "PAUSING", "RESUMING", "PAUSED"})
# 22.3(b): a mid-print PAUSE/ATTENTION condition that a resume (→PRINTING) follows.
# An M600 / "Color Change" / filament runout parks the printer at ATTENTION (on
# /api/v1/status); a user pause shows PAUSED; RESUMING is the brief resume
# transient. When the SAME (already-snapshotted) job re-enters PRINTING from one
# of these, the loaded spool MAY have been swapped — that's the swap-event hook
# that captures the ordered swap_log for per-segment apportionment. A resume from
# any of these is a safe over-trigger (a no-op when the mapping didn't change).
_PAUSED_CONDITION_STATES = frozenset({"PAUSED", "PAUSING", "RESUMING", "ATTENTION"})
# Terminal states that, reached FROM an in-progress state, mean a CANCEL/abort.
# Cancel terminal states (reached FROM in-progress = a CANCEL/abort). This set
# ALSO doubles as the "file still download-locked, don't fetch yet" gate in
# _process_pending_cancel_fetches — do NOT add FINISHED here (it would break the
# retry queue); completions use the separate set below.
_CANCEL_TERMINAL_STATES = frozenset({"STOPPED", "ERROR"})

# Phase-2 cutover: COMPLETION terminal state. Kept SEPARATE from the cancel set
# (above) precisely because that one is reused as a lock gate. A FINISHED edge
# fires FCC's own completion deduct ONLY when the fcc_owns_completion_deduct flag
# is on — otherwise FilaBridge still owns completions and firing here would
# double-deduct. (Default off → this code ships DARK; flip it the same moment the
# FilaBridge container is stopped.)
_COMPLETE_TERMINAL_STATES = frozenset({"FINISHED"})

# Idle / ready states reached FROM an in-progress state WITHOUT our ever sampling
# the terminal STOPPED or FINISHED. This is the AMBIGUOUS edge (2026-06-13): a
# fast cancel→restart that slipped the poll, or a PRINTING→offline→IDLE printer
# power-cycle. We can't tell a cancel from a completion, so we NEVER auto-deduct
# — but we must NOT silently drop it either; it routes to the cancel-REVIEW
# pipeline flagged "couldn't confirm" with the retained progress as the hint.
# Deliberately an ALLOW-LIST (not "everything non-terminal") so a mid-print
# ATTENTION/BUSY (filament runout / heating) can NEVER masquerade as an
# end-of-print idle and fire a spurious review. The real fleet reports v1 "IDLE"
# / "READY"; "OPERATIONAL" covers legacy /api/printer firmware idle text.
_IDLE_READY_STATES = frozenset({"IDLE", "READY", "OPERATIONAL"})

# Tests flip this to False so the deduct runs synchronously + deterministically
# instead of on a daemon thread.
_CANCEL_DEDUCT_RUN_ASYNC = True


def _fcc_owns_completion_deduct():
    """The Phase-2 cutover flag (default False → FilaBridge owns completions, this
    code stays dark). Only consulted on an actual in-progress→FINISHED edge.

    27.4 — the value is PARSED, not bool()-coerced: a hand-edited config with the
    JSON string "false" must read as False. A naive bool() made any non-empty
    string (incl. "false") truthy, silently ENABLING the completion deduct — a
    safety flag that inverts on a string is dangerous. Accepts real bools,
    numerics, and the common string forms; anything unrecognized defaults safe."""
    try:
        raw = config_loader.load_config().get("fcc_owns_completion_deduct", False)
    except Exception:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes", "on")
    return False


def _on_cancel_edge(printer_name, filename, job_id, progress, fb_url):
    """Action taken when a cancel edge is detected. SLICE 5: compute the partial
    and stash it for preview-and-confirm (§9.7) — Derek reviews/nudges before it
    writes (automating the manual Connect-reading he does today). The detector
    reaches this only through _dispatch_cancel_edge, so the threading contract
    (off the heartbeat thread) is unchanged from slice 2a."""
    # INSTANT ACK (2026-06-13): log the moment the STOPPED edge fires, BEFORE the
    # slow async gcode download+decode. On a slow XL .bgcode download the review
    # line is 30-60s out; without this the user faces silence and thinks nothing
    # happened. INFO (no toast spam) — the actual review line below raises the
    # "🛑 Review" affordance.
    try:
        pct = max(0.0, min(1.0, float(progress or 0.0))) * 100
        state.add_log_entry(
            f"🛑 Cancel detected on {printer_name} (~{pct:.0f}%) — computing the partial…",
            "INFO")
    except Exception:
        pass
    try:
        print_deduct._create_pending_cancel_review(printer_name, filename, job_id, progress, fb_url=fb_url)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Cancelled-print review failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_cancel_edge(printer_name, filename, job_id, progress, fb_url):
    """Run the cancel-edge action OFF the heartbeat thread, so a slow gcode
    download never stalls the pulse. Synchronous when _CANCEL_DEDUCT_RUN_ASYNC
    is False (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_cancel_edge,
            args=(printer_name, filename, job_id, progress, fb_url),
            daemon=True).start()
    else:
        _on_cancel_edge(printer_name, filename, job_id, progress, fb_url)


def _on_completion_edge(printer_name, filename, job_id, fb_url, start_spools=None,
                        swap_log=None):
    """Action on a →FINISHED edge (Phase-2, flag-gated): compute + AUTO-APPLY the
    completion deduct from the slicer footer. No preview/confirm — the grams are
    exact for a completion. `start_spools` (22.3) is the print-start snapshot and
    `swap_log` (22.3(b)) the ordered mid-print swap history, both for spool-swap
    detection. Reaches here only through _dispatch_completion_edge so the
    off-heartbeat threading contract matches the cancel path."""
    try:
        print_deduct.deduct_completed_print(printer_name, filename, job_id, fb_url=fb_url,
                               start_spools=start_spools, swap_log=swap_log)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Completed-print deduct failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_completion_edge(printer_name, filename, job_id, fb_url, start_spools=None,
                              swap_log=None):
    """Run the completion-edge action OFF the heartbeat thread (mirrors
    _dispatch_cancel_edge). Synchronous when _CANCEL_DEDUCT_RUN_ASYNC is False
    (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_completion_edge,
            args=(printer_name, filename, job_id, fb_url),
            kwargs={"start_spools": start_spools, "swap_log": swap_log},
            daemon=True).start()
    else:
        _on_completion_edge(printer_name, filename, job_id, fb_url,
                            start_spools=start_spools, swap_log=swap_log)


def _on_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                       progress_unknown=False):
    """Action when a latched in-progress job reaches IDLE/READY WITHOUT our ever
    sampling the terminal STOPPED or FINISHED (2026-06-13): a fast cancel→restart
    that slipped the poll, or a PRINTING→offline→IDLE printer power-cycle. We
    can't tell a cancel from a completion, so route it to the cancel-REVIEW
    pipeline flagged ambiguous (compute the partial at the RETAINED progress as
    the confidence hint) — NEVER auto-deduct (that's FilaBridge's cancel
    over-deduct bug). Reaches here only through _dispatch_ambiguous_edge so the
    off-heartbeat threading contract matches the cancel/completion paths.

    progress_unknown=True (the back-to-back job change): we never sampled a real
    progress for this job, so its usage is unmeasurable — _create_pending_cancel_
    review short-circuits to a non-destructive "weigh the spool" review rather than
    computing a misleading 0g at 0%."""
    # Instant ack (the ambiguous analogue of the cancel instant-ack), so the user
    # isn't met with silence during the async download.
    try:
        if progress_unknown:
            state.add_log_entry(
                f"❓ Print on {printer_name} ('{filename}') was replaced before its "
                f"progress could be measured — surfacing a review (couldn't measure "
                f"usage)…", "INFO")
        else:
            pct = max(0.0, min(1.0, float(progress or 0.0))) * 100
            state.add_log_entry(
                f"❓ Print on {printer_name} reached idle without a clear cancel/finish "
                f"signal (~{pct:.0f}% reached) — computing a review (couldn't confirm "
                f"completed vs cancelled)…", "INFO")
    except Exception:
        pass
    try:
        print_deduct._create_pending_cancel_review(printer_name, filename, job_id, progress,
                                      fb_url=fb_url, ambiguous=True,
                                      progress_unknown=progress_unknown)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Ambiguous-print review failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                             progress_unknown=False):
    """Run the ambiguous-edge action OFF the heartbeat thread (mirrors
    _dispatch_cancel_edge). Synchronous when _CANCEL_DEDUCT_RUN_ASYNC is False
    (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_ambiguous_edge,
            args=(printer_name, filename, job_id, progress, fb_url),
            kwargs={"progress_unknown": progress_unknown},
            daemon=True).start()
    else:
        _on_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                           progress_unknown=progress_unknown)


def _track_print_edge(printer_name, state_info, fb_url):
    """Latch the active job while printing; fire the cancelled-print partial
    deduct on the →STOPPED/ERROR edge. Called once per printer per heartbeat
    from fetch_for_printer (best-effort — the caller wraps it so a failure never
    breaks the Printer Status widget). See the section header for the full
    rationale.

    `state_info is None` (offline/unreachable) is NOT treated as an edge — we
    leave any existing latch intact so a real STOPPED reached across a transient
    offline blip still deducts with the pre-blip latch.
    """
    if state_info is None:
        return
    cur = str(state_info.get('state', '')).upper()
    if not cur:
        # An empty state string can't happen from _probe_printer_state (it
        # returns None or a non-empty state), so this only guards a malformed
        # dict. Treat it like offline: don't update the latch, so a real
        # terminal state on the next poll still detects the edge.
        return

    if cur in _INPROGRESS_PRINT_STATES:
        # Latch the live job — the network call stays OUTSIDE the lock so a slow
        # printer doesn't serialize the other printers' tracker updates.
        job = None
        try:
            job = prusalink_api.get_printer_job(fb_url, printer_name)
        except Exception:
            job = None
        job_changed = None
        prev_job = None  # outgoing job's latched details, for the ambiguous review
        need_snapshot = False  # 22.3: flag a once-per-job start-spool snapshot
        snap_jid = None
        need_swap_snapshot = False  # 22.3(b): flag a resume-edge mid-print swap capture
        swap_jid = None
        swap_progress = None
        swap_runout = False
        with _PRINT_TRACKER_LOCK:
            entry = _PRINT_TRACKER.setdefault(printer_name, {})
            prev_state = entry.get('state')  # 22.3(b): pre-overwrite, for resume detection
            entry['state'] = cur
            if job:
                # Reject blank/zero ids (None/''/'0'/0) — same "blank job" set
                # print_deduct_ledger keys on, so the tracker and the ledger
                # agree on what can't be deduped restart-safely.
                new_jid = job.get('job_id')
                new_jid = new_jid if new_jid not in (None, '', '0', 0) else None
                old_jid = entry.get('job_id')
                # A different (valid) job_id while still in-progress means a NEW
                # print started without us sampling the previous one's terminal
                # state (cancel→reslice→restart faster than the poll, a missed
                # STOPPED, or a Connect auto-queue where the previous job COMPLETED
                # and the next one auto-started inside a single tick). Reset the
                # stale latch so the new job does NOT inherit the old progress
                # high-water (which would over-state its %, then over-deduct on its
                # own cancel) — but FIRST capture the outgoing job so we can route
                # it to the AMBIGUOUS REVIEW (the same "couldn't confirm cancel vs
                # complete" path the live active→IDLE edge uses). This used to be
                # logged INFO-only, which silently dropped a completed-then-requeued
                # job's deduct — the one true silent-loss path (2026-06-13). It
                # NEVER auto-deducts, and a reslice cancelled before extrusion folds
                # to no_usage in the compute (no review line), so this doesn't spam
                # reviews for normal cancel→reslice churn.
                if new_jid is not None and old_jid not in (None, '') and str(new_jid) != str(old_jid):
                    job_changed = (old_jid, new_jid)
                    if entry.get('filename'):
                        prev_job = {
                            'filename': entry.get('filename'),
                            'job_id': old_jid,
                            'progress': float(entry.get('progress', 0.0)),
                            # `progress` is set (5854-ish) only from a REAL job sample,
                            # so its presence tells us whether we ever measured this
                            # job's progress. Absent ⇒ replaced before any sample ⇒
                            # its usage is unmeasurable (route to a progress_unknown
                            # review, not a misleading 0g — the 1053 silent-loss bug).
                            'progress_sampled': 'progress' in entry,
                        }
                    entry.pop('progress', None)
                    entry.pop('filename', None)
                    entry.pop('file_meta', None)
                    # 22.3: drop the previous job's start-spool snapshot so the new
                    # job re-captures its OWN start mapping (the snapshot_job!=jid
                    # guard below would catch it anyway, but pop defensively so a
                    # replacement job can never inherit the old start spools).
                    entry.pop('start_spools', None)
                    entry.pop('snapshot_job', None)
                    # 22.3(b): and its mid-print swap history — a replacement job must
                    # never inherit the old job's swap_log (it's keyed to snapshot_job).
                    entry.pop('swap_log', None)
                    # 22.3(b): and the pending runout-progress markers, so a replacement
                    # job can't inherit the prior job's frozen pause position / flag.
                    entry.pop('pause_progress', None)
                    entry.pop('saw_attention', None)
                if job.get('filename'):
                    entry['filename'] = job['filename']
                if new_jid is not None:
                    entry['job_id'] = new_jid
                # file_meta (the slicer's per-tool 'filament used' estimate) is
                # latched for slice 5's preview UX, which shows the estimate
                # alongside the computed partial without re-fetching the job.
                if job.get('file_meta'):
                    entry['file_meta'] = job['file_meta']
                prog = job.get('progress')
                if isinstance(prog, (int, float)):
                    entry['progress'] = max(float(entry.get('progress', 0.0)), float(prog))
                # 22.3: flag a once-per-job start-spool snapshot — ONLY on a true
                # PRINTING tick (a job first SEEN mid-pause/runout must not capture the
                # post-swap mapping as 'start'). The snapshot_job!=jid clause makes it
                # fire exactly once per job; the Spoolman read happens AFTER the lock.
                if (cur == 'PRINTING' and new_jid is not None
                        and entry.get('snapshot_job') != str(new_jid)):
                    need_snapshot = True
                    snap_jid = new_jid
                # 22.3(b): a resume INTO printing from a pause/ATTENTION condition on
                # the SAME, already-snapshotted job → a mid-print spool swap MAY have
                # happened (M600 / Color-Change / runout, with an FCC eject/load at the
                # pause). Flag an off-lock snapshot to diff the mapping. Mutually
                # exclusive with the START snapshot above (that fires when snapshot_job
                # != jid; this requires ==), so it can't fire on the job's first
                # PRINTING tick nor after a job change (which popped snapshot_job).
                elif (cur == 'PRINTING' and new_jid is not None
                        and prev_state in _PAUSED_CONDITION_STATES
                        and entry.get('snapshot_job') == str(new_jid)):
                    need_swap_snapshot = True
                    swap_jid = new_jid
                    # The progress high-water at the resume ≈ where this segment ended
                    # (the print resumes from the pause point). Recorded as a COARSE HINT
                    # only — it can read slightly high (a PAUSED pause re-samples progress;
                    # an ATTENTION/M600 park doesn't) so the deferred per-segment math will
                    # take the authoritative cut from the gcode `;COLOR_CHANGE` byte
                    # boundary (parse_color_change_segments), not this %.
                    # 22.3(b) runout accuracy: PREFER the frozen pause progress (sampled
                    # during the ATTENTION park below — the true swap byte position) over
                    # the pre-runout PRINTING high-water, which lags by up to one poll
                    # (measured ~3 g off, 2026-07-02). `saw_attention` ⇒ this pause was a
                    # RUNOUT, so the split charges the run-out spool the path remnant.
                    swap_progress = max(float(entry.get('progress', 0.0)),
                                        float(entry.get('pause_progress', 0.0)))
                    swap_runout = bool(entry.get('saw_attention'))
        # 22.3 (off-lock, like get_printer_job): capture the start-spool snapshot for
        # mid-print swap detection. ONLY when FCC owns completions — deduct_completed_print
        # is the sole consumer, so it's dead weight (and a wasted Spoolman read) on
        # cancel-only prints. _snapshot_active_spools is best-effort ({} on failure), so a
        # blip leaves start_spools unset and the completion degrades to today's auto-apply.
        if need_snapshot and _fcc_owns_completion_deduct():
            snap = print_deduct._snapshot_active_spools(printer_name, fb_url)
            with _PRINT_TRACKER_LOCK:
                e = _PRINT_TRACKER.get(printer_name)
                # Store only if (a) the read returned something — an empty {} means a
                # transient Spoolman blip (or a genuinely empty fleet), so DON'T flag
                # snapshot_job, leaving the once-per-job guard open to retry on the
                # next PRINTING tick rather than permanently disabling detection for
                # this job; and (b) the SAME job is still latched (a fast job change
                # during the off-lock read would otherwise mis-key the snapshot).
                if snap and e is not None and str(e.get('job_id')) == str(snap_jid):
                    e['start_spools'] = {str(k): v for k, v in snap.items()}
                    e['snapshot_job'] = str(snap_jid)
        # 22.3(b) (off-lock, like the start snapshot): a resume from a pause/ATTENTION
        # MAY mean the loaded spool was swapped. Snapshot the live mapping and diff it
        # against the mapping in effect for the segment just printed (start_spools +
        # any prior swaps) — each clean 1→1 sid change appends an ordered swap_log
        # event. Best-effort: an empty/failed snapshot just skips (retries next resume).
        # Same flag gate + same-job re-check as the start snapshot. This release-then-
        # re-acquire is safe because _track_print_edge has a SINGLE sequential caller
        # (the _cancel_monitor daemon's per-printer loop) — the job_id re-check guards a
        # fast job change, not a concurrent same-job writer (none exists). If this is ever
        # re-attached to the dashboard pulse (it historically was), revisit the locking.
        if need_swap_snapshot and _fcc_owns_completion_deduct():
            snap = print_deduct._snapshot_active_spools(printer_name, fb_url)
            if snap:
                with _PRINT_TRACKER_LOCK:
                    e = _PRINT_TRACKER.get(printer_name)
                    if e is not None and str(e.get('job_id')) == str(swap_jid):
                        print_deduct._record_swap_events(e, snap, swap_progress,
                                                         runout=swap_runout)
                        # Consume the pause markers so a SUBSEQUENT pause/swap in the
                        # same job starts from a clean slate (next runout re-samples).
                        e.pop('pause_progress', None)
                        e.pop('saw_attention', None)
        if prev_job:
            # Surface the outgoing job as an ambiguous review (off-heartbeat,
            # idempotent via the (printer, job_id) ledger + review store) instead of
            # silently dropping it. Never auto-deducts. When we never measured the
            # outgoing job's progress (replaced before any sample), flag it
            # progress_unknown so the review is a non-destructive "weigh the spool"
            # prompt instead of a misleading 0g computed at 0% (the 1053 bug).
            progress_unknown = not prev_job.get('progress_sampled', False)
            try:
                detail = ("without measuring its progress — surfacing a review to weigh"
                          if progress_unknown else
                          "without a sampled end state — reviewing the previous job "
                          "(couldn't confirm completed vs cancelled)")
                state.add_log_entry(
                    f"❓ {printer_name}: print job changed ({job_changed[0]}→{job_changed[1]}) "
                    f"{detail}.", "INFO")
            except Exception:
                pass
            _dispatch_ambiguous_edge(printer_name, prev_job['filename'],
                                     prev_job['job_id'], prev_job['progress'], fb_url,
                                     progress_unknown=progress_unknown)
        elif job_changed:
            # job_changed but nothing was latched to review (the previous job_id had
            # no PRINTING sample → no filename). Preserve the original INFO log.
            try:
                state.add_log_entry(
                    f"ℹ️ {printer_name}: print job changed ({job_changed[0]}→{job_changed[1]}) "
                    f"without a sampled end state; previous job not auto-deducted.", "INFO")
            except Exception:
                pass
        return

    # Non-in-progress state: detect a CANCEL, a (Phase-2) COMPLETION, or an
    # AMBIGUOUS-idle edge against the latched prev state.
    fire = None
    cancel_without_latch = False
    # 22.3(b) runout accuracy: an ATTENTION park (filament runout / M600) FREEZES the job
    # at the pause byte position, and /api/v1/job reports that frozen progress. The
    # in-progress block is SKIPPED for ATTENTION (it's not an in-progress state), so
    # sample the frozen progress HERE (network OUTSIDE the lock) — the resume-edge swap
    # event then cuts at the TRUE runout point instead of the stale pre-runout PRINTING
    # high-water (the ~3 g lag measured 2026-07-02).
    pause_progress = None
    if cur == 'ATTENTION':
        try:
            _pj = prusalink_api.get_printer_job(fb_url, printer_name)
            if _pj and isinstance(_pj.get('progress'), (int, float)):
                pause_progress = float(_pj['progress'])
        except Exception:
            pause_progress = None
    with _PRINT_TRACKER_LOCK:
        entry = _PRINT_TRACKER.get(printer_name)
        prev = entry.get('state') if entry else None
        # `prev_active` = the printer was mid-something (a job in flight), NOT
        # already idle/ready and NOT a clean terminal we already handled. This is
        # BROADER than _INPROGRESS_PRINT_STATES (the LATCH set) on purpose: a
        # filament runout / M600 parks the printer at ATTENTION, and a hard reset
        # / power-cycle can surface BUSY on the way back up — neither is
        # "in-progress" for latching, but a print that ENDS from them (ATTENTION→
        # IDLE on a hard reset, ATTENTION→STOPPED on a cancel-from-the-prompt) is
        # still a real edge that today would be silently dropped (2026-06-13,
        # Derek's live Core One at ATTENTION 91%). A resolved cancel/complete
        # resets the latch (clearing `filename`), and prev is guarded against
        # idle/terminal here, so neither a bare idle→idle nor a second terminal
        # tick can re-fire — and the latch branch only ever sets `filename` during
        # a real printing state, so pre-print heating (IDLE→BUSY→IDLE) never has a
        # filename to fire on.
        prev_active = (prev is not None
                       and prev not in _IDLE_READY_STATES
                       and prev not in _CANCEL_TERMINAL_STATES
                       and prev not in _COMPLETE_TERMINAL_STATES)
        # Cancel = active → STOPPED/ERROR (always owned by FCC).
        is_cancel_edge = prev_active and cur in _CANCEL_TERMINAL_STATES
        # Completion = active → FINISHED, but ONLY when the cutover flag is on
        # (else FilaBridge still owns completions → firing here double-deducts).
        # `_COMPLETE_TERMINAL_STATES` is deliberately SEPARATE from the cancel set
        # (which doubles as the fetch lock-gate). Short-circuit AND so the config
        # read happens only on an actual active→FINISHED transition.
        is_complete_edge = (prev_active and cur in _COMPLETE_TERMINAL_STATES
                            and _fcc_owns_completion_deduct())
        # Ambiguous = active → IDLE/READY WITHOUT our ever sampling the terminal
        # STOPPED or FINISHED (2026-06-13): a fast cancel→restart that slipped the
        # poll, a PRINTING→offline→IDLE power-cycle, or a hard reset out of the
        # ATTENTION filament-prompt (prev=ATTENTION/BUSY → IDLE). We can't tell
        # cancel from completion, so route it to the REVIEW pipeline flagged
        # "couldn't confirm" — NEVER auto-deduct. Fires regardless of the cutover
        # flag (it's a safe review, not a write; the proven prod signature
        # `{state:IDLE, job_id:693, progress:0.26}` was captured pre-cutover, and
        # visibility beats a silent drop). A clean completion FCC actually
        # observed (PRINTING→FINISHED→…) is NOT ambiguous (prev=FINISHED is a
        # handled terminal → prev_active False), so this can't spam reviews for
        # normal prints; only a genuinely-missed terminal triggers it.
        is_ambiguous_edge = prev_active and cur in _IDLE_READY_STATES
        if is_cancel_edge:
            edge_kind = 'cancel'
        elif is_complete_edge:
            edge_kind = 'complete'
        elif is_ambiguous_edge:
            edge_kind = 'ambiguous'
        else:
            edge_kind = None
        if edge_kind and entry and entry.get('filename'):
            fire = {
                'kind': edge_kind,
                'filename': entry.get('filename'),
                'job_id': entry.get('job_id', ''),
                'progress': float(entry.get('progress', 0.0)),
                # Whether we ever sampled a REAL progress for this job (entry sets
                # 'progress' only from a job sample). Absent ⇒ a latched-but-unsampled
                # job (e.g. caught at ATTENTION before any PRINTING tick) → route the
                # ambiguous edge to a non-destructive progress_unknown review instead
                # of computing a misleading 0% partial (22.4(6); mirrors the
                # job-changed path's progress_sampled check).
                'progress_sampled': 'progress' in entry,
                # 22.3: the print-start spool snapshot rides the fire dict to the
                # completion handler (the latch is reset right below, so the entry's
                # copy is gone). _validated_start_spools re-checks snapshot_job==job_id.
                'start_spools': entry.get('start_spools'),
                'snapshot_job': entry.get('snapshot_job'),
                # 22.3(b): the ordered mid-print swap history rides along too (same
                # snapshot_job guard via _validated_swap_log).
                'swap_log': entry.get('swap_log'),
            }
            # Reset the latch to the terminal state so the edge can't re-fire.
            _PRINT_TRACKER[printer_name] = {'state': cur}
        else:
            if is_cancel_edge:
                cancel_without_latch = True
            if entry is not None:
                entry['state'] = cur
                # 22.3(b): during an ATTENTION runout park of a latched job, record the
                # frozen pause progress + that an ATTENTION was seen (so a swap on the
                # resume is treated as a RUNOUT). Keep the MAX across re-polls.
                if cur == 'ATTENTION' and entry.get('filename'):
                    entry['saw_attention'] = True
                    if pause_progress is not None:
                        entry['pause_progress'] = max(
                            float(entry.get('pause_progress', 0.0)), pause_progress)
            else:
                _PRINT_TRACKER[printer_name] = {'state': cur}

    if cancel_without_latch:
        state.add_log_entry(
            f"🛑 Cancel detected on {printer_name}, but no active job was latched "
            f"(print too short to sample between heartbeats) — no partial deduct.",
            "INFO")
    if fire:
        if fire['kind'] == 'complete':
            _dispatch_completion_edge(
                printer_name, fire['filename'], fire['job_id'], fb_url,
                start_spools=print_deduct._validated_start_spools(fire, fire['job_id']),
                swap_log=print_deduct._validated_swap_log(fire, fire['job_id']))
        elif fire['kind'] == 'ambiguous':
            _dispatch_ambiguous_edge(
                printer_name, fire['filename'], fire['job_id'], fire['progress'],
                fb_url, progress_unknown=not fire.get('progress_sampled', False))
        else:
            _dispatch_cancel_edge(printer_name, fire['filename'], fire['job_id'],
                                  fire['progress'], fb_url)


# ---------------------------------------------------------------------------
# Cancelled-print monitor — a dedicated server-side poller, INDEPENDENT of the
# dashboard pulse (Derek 2026-06-11). Detection must NOT depend on a browser
# having the dashboard open or focused: an unattended print is the common case,
# and FCC usually isn't in focus. So _track_print_edge no longer rides
# _pulse_section_printer_status; this daemon probes every printer on a fixed
# ~30s tick regardless of UI state. The frontend pulse still probes state for
# the widget, and its Phase-0 fast-poll burst still snaps the displayed weight
# after a deduct — but it's no longer load-bearing for catching cancels.
# ---------------------------------------------------------------------------

# ADAPTIVE poll cadence (2026-06-13, Derek wants the monitor more responsive).
# Poll FAST while anything is happening on the fleet, back off to the slow rate
# when every printer is idle. The cancel/poll-miss gap (a fast cancel→restart
# that slips a slow tick) closes the most by sampling often WHILE a print runs,
# so we can catch the STOPPED edge before the screen is cleared. Perf is fine:
# each state probe is ~30ms, runs in parallel with a bounded timeout, and the
# costly bgcode download fires only on an EDGE, never per tick — so a 10s tick
# doesn't hammer Buddy's tiny HTTP pool. "Busy" = any printer in-progress OR
# sitting on a terminal screen (STOPPED/ERROR/FINISHED), so the whole
# print→clear lifecycle (incl. waiting out the deferred-fetch lock) stays
# responsive; the fleet idles down to the slow rate only when truly nothing's up.
_CANCEL_MONITOR_FAST_S = 10
_CANCEL_MONITOR_IDLE_S = 30
# How long to keep retrying a deferred fetch before giving up (§9.10). The
# cancelled file stays download-LOCKED until Derek clears the cancel screen on
# the printer; he's usually at the printer, but this buffers a cancel-and-walk-
# away (e.g. over a weekend). Retrying is nearly free — it only hits the network
# once the printer leaves STOPPED — so the window is generous.
_CANCEL_FETCH_MAX_AGE_S = 72 * 3600
_cancel_monitor_started = False
_cancel_monitor_lock = threading.Lock()


def _cancel_monitor_tick():
    """One detection sweep: probe every printer's state + run the latch/edge
    detector, then service the deferred-fetch retry queue (§9.10) using the
    states just probed. Per-printer probes fan out so a slow/offline printer
    doesn't block the rest. Best-effort throughout.

    Returns True when the fleet is BUSY (any printer in-progress or on a terminal
    screen) so the loop can poll on the FAST cadence; False when everything is
    idle/offline (back off to the slow cadence). The return is the only signal
    the adaptive loop needs — it never raises."""
    from concurrent.futures import ThreadPoolExecutor
    try:
        printer_map = locations_db.get_active_printer_map()
        _, fb_url = config_loader.get_api_urls()
    except Exception:
        return False
    names = sorted({info.get('printer_name') for info in printer_map.values()
                    if info.get('printer_name')})
    if not names:
        return False

    probed = {}

    def _probe(name):
        try:
            state_info = prusalink_api.get_printer_state(fb_url, name)
        except Exception:
            state_info = None
        probed[name] = state_info  # distinct keys per thread → GIL-safe
        try:
            _track_print_edge(name, state_info, fb_url)
        except Exception as e:
            try:
                state.logger.debug(f"cancel-monitor probe failed for {name}: {e}")
            except Exception:
                pass

    workers = max(1, min(8, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_probe, names))

    # Prune tracker entries for printers no longer in the map so a removed /
    # renamed printer's stale latch can't linger or mis-fire on re-add.
    with _PRINT_TRACKER_LOCK:
        for stale in [p for p in _PRINT_TRACKER if p not in names]:
            _PRINT_TRACKER.pop(stale, None)
        snapshot = {k: dict(v) for k, v in _PRINT_TRACKER.items()}

    # Slice 7: persist the latch snapshot so an in-flight print survives an FCC /
    # host restart (reconciled on monitor start via _recover_print_tracker_on_
    # start). Best-effort — print_tracker_store.save swallows its own errors.
    print_tracker_store.save(snapshot)

    # Retry any cancels whose gcode was download-locked at the edge (§9.10).
    try:
        _process_pending_cancel_fetches(probed, fb_url)
    except Exception as e:
        try:
            state.logger.debug(f"cancel-fetch retry pass failed: {e}")
        except Exception:
            pass

    # Tell the loop whether to stay FAST: any reachable printer that is NOT
    # idle/ready is "busy" — printing, paused, ATTENTION (filament prompt), BUSY,
    # or sitting on a terminal STOPPED/ERROR/FINISHED screen. Poll fast across
    # that whole window so a cancel→restart is sampled in time and the deferred-
    # fetch lock drains soon after the screen clears. Offline (None/'') and
    # idle/ready → back off to the slow cadence.
    busy = False
    for st in probed.values():
        s = str((st or {}).get('state', '')).upper()
        if s and s not in _IDLE_READY_STATES:
            busy = True
            break
    return busy


def _process_pending_cancel_fetches(states, fb_url):
    """Service the deferred-fetch queue (§9.10): for each cancelled print whose
    gcode couldn't be downloaded at the edge (selected-file LOCK), re-attempt the
    compute ONCE the printer has left STOPPED (the file un-locks → IDLE), then
    stash the 🛑 Review and drop the queue entry. Gives up after
    _CANCEL_FETCH_MAX_AGE_S with a "weigh the spool" warning.

    `states` maps printer_name -> the state dict get_printer_state returned this
    tick (or None when offline). Best-effort per entry; one bad record never
    blocks the rest.
    """
    pendings = cancel_fetch_store.list_pending()
    if not pendings:
        return
    now = time.time()
    for rec in pendings:
        try:
            printer = rec.get("printer_name")
            job_id = rec.get("job_id")
            filename = rec.get("filename")
            progress = float(rec.get("progress", 0.0) or 0.0)
            kind = rec.get("kind", "cancel")  # 'cancel' (review) | 'complete' (auto-apply)
            ambiguous = bool(rec.get("ambiguous", False))  # cancel-review "couldn't confirm" flag
            start_spools = rec.get("start_spools")  # 22.3: carried for the deferred completion swap check
            swap_log = rec.get("swap_log")  # 22.3(b): ordered mid-print swap history
            if not printer or job_id in (None, ""):
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Resolved elsewhere (confirmed/dismissed, or a review already
            # stashed) → drop the queue entry. Keeps "ledger/review ⟹ no fetch".
            if (print_deduct_ledger.was_deducted(printer, job_id)
                    or cancel_review_store.has_pending(printer, job_id)):
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Give up after the max-age window so a deleted/abandoned file's
            # entry can't linger forever. Record grams=0 so it can't re-queue.
            first_seen = float(rec.get("first_seen", now) or now)
            if now - first_seen > _CANCEL_FETCH_MAX_AGE_S:
                pct = max(0.0, min(1.0, progress)) * 100
                hrs = _CANCEL_FETCH_MAX_AGE_S // 3600
                if kind == "complete":
                    state.add_log_entry(
                        f"✅ Gave up fetching the completed print's gcode on {printer} "
                        f"('{filename}') after {hrs}h — no deduct recorded. "
                        f"Weigh the spool to true it up.", "WARNING", "ffaa00")
                else:
                    state.add_log_entry(
                        f"🛑 Gave up fetching the cancelled print's gcode on {printer} "
                        f"('{filename}', ~{pct:.0f}%) after {hrs}h — no partial deduct. "
                        f"Weigh the spool to true it up.", "WARNING", "ffaa00")
                print_deduct_ledger.record_deduct(printer, job_id, filename=filename,
                                                  scale=progress, grams=0)
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Gate on state: the selected file is reliably download-UNLOCKED only
            # once the printer is genuinely IDLE/READY (the print cleared off the
            # screen). Any other reachable state means it's still busy/locked —
            # PRINTING (new job), the cancel screen (STOPPED/ERROR), the finish
            # screen (FINISHED), an ATTENTION filament-prompt, or a transient BUSY
            # — so wait. Offline (None/'') → wait. (Allow-list, not deny-list, so
            # we never hammer Buddy's tiny HTTP pool retrying a locked file mid-
            # ATTENTION — the live Core One @91% bug, 2026-06-13.)
            st = states.get(printer)
            cur = str((st or {}).get("state", "")).upper() if st else ""
            if cur not in _IDLE_READY_STATES:
                continue

            if kind == "complete":
                # Re-check the flag HERE, not just at the edge: a completion can
                # sit queued behind the finish-screen lock for up to 72h without a
                # ledger record. If the cutover is rolled back in that window (flag
                # OFF + FilaBridge restarted), FilaBridge owns completions again —
                # firing FCC's deduct now would double-bill (the ledger can't span
                # processes). Abandon the queued completion instead.
                if not _fcc_owns_completion_deduct():
                    cancel_fetch_store.pop_pending(printer, job_id)
                    continue
                # start_spools + swap_log (if captured before the finish-screen lock)
                # ride the fetch record so the deferred completion still detects a
                # mid-print spool swap (22.3/22.3(b)); None when not captured → auto-apply.
                result = print_deduct.deduct_completed_print(printer, filename, job_id, fb_url=fb_url,
                                                start_spools=start_spools, swap_log=swap_log)
            else:
                result = print_deduct._create_pending_cancel_review(
                    printer, filename, job_id, progress, fb_url=fb_url, ambiguous=ambiguous)
            status = (result or {}).get("status")
            if status == "awaiting_fetch":
                # Still couldn't fetch (the file 404'd despite a ready state — a
                # transient, or the file was deleted). Leave queued; the re-queue
                # already bumped attempts. The max-age window bounds the retries.
                continue
            # Any terminal outcome (pending review / pending_unresolved / no_usage /
            # skipped) resolves this entry.
            cancel_fetch_store.pop_pending(printer, job_id)
        except Exception as e:
            try:
                state.logger.debug(f"cancel-fetch retry failed for {rec}: {e}")
            except Exception:
                pass


def _recover_print_tracker_on_start():
    """Slice 7 — power-loss latch persistence. On monitor start, reconcile the
    persisted in-flight latch against each printer's CURRENT state so a cancel
    that happened (or a print that was running) during an FCC / host restart
    isn't silently lost. Resolution table (persisted = was in-progress + a
    latched job):

        now PRINTING, SAME job_id  → it resumed: restore the latch
        now PRINTING, DIFFERENT job → old outcome unknown: warn (manual), latch new
        now STOPPED / ERROR        → cancel/failure: fire the deduct at persisted %
        now FINISHED               → completed: leave to FilaBridge (no deduct)
        now IDLE / READY           → cleared during outage, ambiguous: warn (manual)
        offline (unreachable)      → restore the latch, defer to normal detection
        (no latched job)           → seed the baseline state only

    Idempotent: _dispatch_cancel_edge dedups via the (printer, job_id) ledger +
    review store, so a double restart can't double-deduct."""
    persisted = print_tracker_store.load()
    if not persisted:
        return
    try:
        _, fb_url = config_loader.get_api_urls()
    except Exception:
        fb_url = None
    recovered = 0
    for name, entry in list(persisted.items()):
        try:
            if _recover_one_print_latch(name, entry, fb_url):
                recovered += 1
        except Exception as e:
            try:
                state.logger.debug(f"print-latch recovery failed for {name}: {e}")
            except Exception:
                pass
    if recovered:
        try:
            state.logger.info(
                f"🛑 Reconciled {recovered} persisted print latch(es) after restart.")
        except Exception:
            pass


def _recover_one_print_latch(name, entry, fb_url):
    """Reconcile one persisted latch (see _recover_print_tracker_on_start for the
    table). Returns True if it acted, False for a no-op (bare entry / completion)."""
    job_id = entry.get('job_id')
    filename = entry.get('filename')
    progress = float(entry.get('progress', 0.0) or 0.0)
    # Whether a REAL progress was ever sampled for this latched job (the latch sets
    # 'progress' only from a job sample; print_tracker_store round-trips it verbatim).
    # Absent ⇒ unsampled → the ambiguous-idle branch routes to a non-destructive
    # progress_unknown review instead of recovering at a misleading 0% (22.4(6)).
    progress_sampled = 'progress' in entry
    if not (job_id and filename):
        # No latched job (a bare terminal/idle snapshot) — nothing to recover;
        # seed the baseline state so the first edge-detect has a `prev`.
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': str(entry.get('state', '')).upper()}
        return False

    cur_info = prusalink_api.get_printer_state(fb_url, name) if fb_url else None
    cur = str((cur_info or {}).get('state', '')).upper() if cur_info else None
    pct = max(0.0, min(1.0, progress)) * 100

    # Offline on restart → can't resolve; restore the latch and let normal
    # edge-detection handle it when the printer is reachable again (mirrors the
    # in-tick "offline preserves the latch" rule).
    if cur is None:
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = dict(entry)
        return True

    if cur in _INPROGRESS_PRINT_STATES:
        job = prusalink_api.get_printer_job(fb_url, name) or {}
        cur_jid = job.get('job_id')
        cur_jid = cur_jid if cur_jid not in (None, '', '0', 0) else None
        if cur_jid is not None and str(cur_jid) == str(job_id):
            # Same job still running → it RESUMED. Restore the latch (incl. the
            # progress high-water) so normal detection continues from here.
            with _PRINT_TRACKER_LOCK:
                _PRINT_TRACKER[name] = dict(entry)
            return True
        # A DIFFERENT job is printing → the old one ended during the outage and
        # we can't tell cancel from completion → manual review; latch the new job.
        state.add_log_entry(
            f"⚠️ {name}: a print ('{filename}', ~{pct:.0f}%) was in progress when FCC "
            f"restarted and a different job is printing now — its outcome is unknown, "
            f"not auto-deducted. Weigh the spool if that print was cancelled.",
            "WARNING", "ffaa00")
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {
                'state': cur, 'job_id': cur_jid, 'filename': job.get('filename'),
                'progress': float(job.get('progress') or 0.0),
                'file_meta': job.get('file_meta') or {}}
        return True

    if cur in _CANCEL_TERMINAL_STATES:
        # Did NOT resume — still STOPPED/ERROR → a real cancel/failure. Fire the
        # deduct from the persisted progress (Derek's "resolve from last pull
        # status if it doesn't resume").
        state.add_log_entry(
            f"🛑 Recovering a cancel missed during an FCC restart on {name} "
            f"('{filename}', ~{pct:.0f}%) — printer still {cur}.", "WARNING", "ffaa00")
        _dispatch_cancel_edge(name, filename, job_id, progress, fb_url)
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return True

    if cur == "FINISHED":
        if _fcc_owns_completion_deduct():
            # Phase-2: FCC owns completions → recover the completion deduct missed
            # during the restart. Still FINISHED = unambiguous (a completion, not a
            # cleared-then-reprinted job). Idempotent via the (printer, job_id)
            # ledger, so a double restart can't double-deduct.
            state.add_log_entry(
                f"✅ Recovering a completion missed during an FCC restart on {name} "
                f"('{filename}') — printer still FINISHED.", "INFO")
            # 22.3: the persisted entry round-trips start_spools/snapshot_job/swap_log,
            # so a restart AFTER the snapshot was captured still detects a mid-print
            # swap; a restart BEFORE capture has no snapshot → None → auto-apply.
            _dispatch_completion_edge(name, filename, job_id, fb_url,
                                      start_spools=print_deduct._validated_start_spools(entry, job_id),
                                      swap_log=print_deduct._validated_swap_log(entry, job_id))
            with _PRINT_TRACKER_LOCK:
                _PRINT_TRACKER[name] = {'state': cur}
            return True
        # Flag off → FilaBridge still owns completions → no deduct.
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return False

    if cur in _IDLE_READY_STATES:
        # in-progress → cleared during the outage. Can't tell a cancelled-then-
        # cleared print from a completed-then-cleared one → route it to the
        # AMBIGUOUS REVIEW (download the now-unlocked file, compute the partial at
        # the persisted progress, surface "couldn't confirm") instead of only
        # telling Derek to weigh. Same machinery + wording as the live ambiguous
        # edge; idempotent via the (printer, job_id) ledger + review store, so a
        # double restart can't double-surface. NEVER auto-deducts.
        state.add_log_entry(
            f"❓ A print ('{filename}', ~{pct:.0f}%) was in progress on {name} when FCC "
            f"restarted and it's now {cur or 'idle'} — surfacing a review (couldn't "
            f"confirm completed vs cancelled).", "WARNING", "ffaa00")
        _dispatch_ambiguous_edge(name, filename, job_id, progress, fb_url,
                                 progress_unknown=not progress_sampled)
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return True

    # Any OTHER state (ATTENTION filament-prompt, BUSY, or an unknown transient) =
    # the print is still mid-something, NOT ended. Restore the latch and defer to
    # live edge-detection (mirrors the offline case) — the live monitor fires the
    # cancel/ambiguous/completion edge when it actually reaches a terminal/idle.
    with _PRINT_TRACKER_LOCK:
        _PRINT_TRACKER[name] = dict(entry)
    return True


def _cancel_monitor_loop():
    # Slice 7: reconcile the persisted in-flight latch BEFORE the first tick so a
    # cancel missed during an FCC/host restart is recovered (or surfaced) up front.
    try:
        _recover_print_tracker_on_start()
    except Exception as e:
        try:
            state.logger.warning(f"print-latch recovery pass failed: {e}")
        except Exception:
            pass
    while True:
        busy = False
        try:
            busy = _cancel_monitor_tick()
        except Exception as e:
            try:
                state.logger.warning(f"cancel-monitor tick error: {e}")
            except Exception:
                pass
        # Adaptive cadence: fast while the fleet is busy, slow when idle.
        time.sleep(_CANCEL_MONITOR_FAST_S if busy else _CANCEL_MONITOR_IDLE_S)


def _seed_printer_credentials_from_filabridge():
    """FilaBridge Phase-2 cutover — credential gate. ONE-TIME, prime-only seed:
    relocate each printer's ip_address + api_key OFF FilaBridge `GET /printers`
    and ONTO its first-class Type:"Printer" row (printer_creds field), so the
    whole PrusaLink read path (state/job/MMU probe, cancel-deduct download) stops
    depending on FilaBridge being up. Pulls /printers ONLY when a Printer row is
    still missing creds, and never overwrites a row that already has them (a
    Settings edit wins). Idempotent — once every row has creds (or FilaBridge is
    gone) it does nothing. Lives in the SERVING-process launch path (not module
    import) because it makes a network call; mirrors the Phase-3/4 migrations'
    load→migrate→backup→save shape. Best-effort: never blocks startup."""
    try:
        _cred_locs = locations_db.load_locations_list()
    except Exception as _e:
        state.logger.warning(f"printer-creds seed: could not load locations: {_e}")
        return
    _needs_seed = any(
        isinstance(r, dict)
        and str(r.get('Type', '')).strip().lower() == 'printer'
        and not (isinstance(r.get(locations_db.PRINTER_CREDS_KEY), dict)
                 and str((r.get(locations_db.PRINTER_CREDS_KEY) or {}).get('ip_address', '') or '').strip())
        for r in (_cred_locs or [])
    )
    if not _needs_seed:
        return
    try:
        _, _cred_fb_url = config_loader.get_api_urls()
        _fb_printers = prusalink_api.fetch_all_filabridge_printers(_cred_fb_url)
    except Exception as _e:
        state.logger.warning(f"printer-creds seed: FilaBridge pull failed: {_e}")
        return
    if not _fb_printers:
        state.logger.info(
            "🔐 Printer-creds seed: FilaBridge /printers unreachable or empty; "
            "will retry next boot (rows still missing creds).")
        return
    try:
        _cred_migrated, _cred_changed = locations_db.seed_printer_credentials(
            _cred_locs, _fb_printers, prime_only=True)
    except Exception as _seed_err:
        # 27.2 — a raising seed must NOT propagate out of this best-effort boot
        # helper (docstring: "never blocks startup"). Degrade to a warning and
        # let the cancel monitor start; the seed retries next boot.
        state.logger.warning(
            f"printer-creds seed: seeding failed (boot continues, retries next "
            f"boot): {_seed_err}")
        return
    if not _cred_changed:
        return
    try:
        import shutil, time as _t
        _stamp = _t.strftime('%Y%m%d-%H%M%S')
        _backup = f"{locations_db.JSON_FILE}.pre-printer-creds-seed-{_stamp}.bak"
        shutil.copy2(locations_db.JSON_FILE, _backup)
        state.logger.info(f"📦 Backed up locations.json → {_backup}")
        startup_migrations._prune_locations_backups()
    except Exception as _bk_err:
        state.logger.warning(f"Could not write pre-printer-creds-seed backup: {_bk_err}")
    if locations_db.save_locations_list(_cred_migrated):
        state.logger.info(
            "🔐 Seeded printer credentials from FilaBridge onto Printer rows — "
            "FilaBridge Phase-2 credential gate primed (FCC now reaches PrusaLink "
            "without FilaBridge).")
    else:
        state.logger.error(
            "❌ Printer-creds seed save FAILED — locations.json left unchanged; "
            "will retry next boot.")


def _start_cancel_monitor():
    """Start the cancel-monitor daemon thread once per process. Called from the
    __main__ launch path only (never on a bare import, so tests don't spawn it).
    Idempotent."""
    global _cancel_monitor_started
    with _cancel_monitor_lock:
        if _cancel_monitor_started:
            return
        _cancel_monitor_started = True
    threading.Thread(target=_cancel_monitor_loop, name="cancel-monitor",
                     daemon=True).start()
    try:
        state.logger.info(
            f"🛑 Cancelled-print monitor started (adaptive poll: "
            f"{_CANCEL_MONITOR_FAST_S}s busy / {_CANCEL_MONITOR_IDLE_S}s idle, "
            f"dashboard-independent).")
    except Exception:
        pass
