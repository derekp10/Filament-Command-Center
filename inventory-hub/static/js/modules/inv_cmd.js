/* MODULE: COMMAND CENTER (Dashboard & Buffer) - Polished v2 */
console.log("🚀 Loaded Module: COMMAND CENTER");

// --- BUFFER: recently-assigned-out guard (buglist 21.6) -------------------
// The buffer is shared server state (/api/state/buffer), reconciled by the 2s
// loadBuffer heartbeat with a whole-list, last-writer-wins overwrite. When a
// spool is scanned into a slot it's removed from heldSpools locally + persisted
// — but a stale server payload (a lost/slow persist, or another open client
// re-asserting its own buffer) can still carry that spool, and once the 3s
// time-grace window lapses loadBuffer would overwrite heldSpools with it,
// "returning" the just-assigned spool to the buffer. This registry records the
// ids we INTENTIONALLY assigned out so a heartbeat sync can filter them back
// out (and re-assert the corrected buffer so the server converges). Entries
// self-expire after a window longer than any pulse cadence; genuinely re-
// buffering a spool clears its entry (see renderBuffer) so a real re-pickup
// isn't suppressed. Full bidirectional multi-client sync remains L302.
window._recentlyAssignedOut = window._recentlyAssignedOut || new Map();
const ASSIGNED_OUT_TTL_MS = 12000;
const _markAssignedOut = (id) => {
    if (id == null) return;
    window._recentlyAssignedOut.set(String(id), Date.now());
};
const _filterRecentlyAssignedOut = (list) => {
    const now = Date.now();
    const m = window._recentlyAssignedOut;
    m.forEach((t, k) => { if (now - t > ASSIGNED_OUT_TTL_MS) m.delete(k); });
    return (Array.isArray(list) ? list : []).filter(s => !m.has(String(s.id)));
};

// --- BUFFER UI ---
const renderBuffer = () => {
    const z = document.getElementById('buffer-zone');
    const n = document.getElementById('buffer-nav-deck');

    // 21.6: any spool genuinely present in the buffer is, by definition, not
    // "assigned out" — clear its suppression entry so a real re-pickup/re-scan
    // back into the buffer isn't filtered out by the heartbeat guard.
    if (window._recentlyAssignedOut && window._recentlyAssignedOut.size) {
        state.heldSpools.forEach(s => window._recentlyAssignedOut.delete(String(s.id)));
    }

    // 1. Render Dashboard Buffer Zone
    if (z) {
        if (state.heldSpools.length === 0) {
            z.innerHTML = `<div class="buffer-empty-msg">Buffer Empty</div>`;
        } else {
            z.innerHTML = state.heldSpools.map((s, i) => {
                return window.SpoolCardBuilder.buildCard(s, 'buffer', { isFirst: i === 0, index: i });
            }).join('');

            state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, "ID:" + s.id, 74));
        }
    }

    // 2. Render Dashboard Nav Deck (If present on Dashboard)
    if (n) {
        if (state.heldSpools.length > 1) {
            const nextSpool = state.heldSpools[1];
            const prevSpool = state.heldSpools[state.heldSpools.length - 1];
            const prevStyles = getFilamentStyle(prevSpool.color, prevSpool.color_direction || 'longitudinal');
            const nextStyles = getFilamentStyle(nextSpool.color, nextSpool.color_direction || 'longitudinal');

            n.style.display = 'flex';
            n.innerHTML = 
                window.SpoolCardBuilder.buildCard(prevSpool, 'buffer_nav', { navDirection: 'prev', navAction: 'window.prevBuffer()' }) + 
                window.SpoolCardBuilder.buildCard(nextSpool, 'buffer_nav', { navDirection: 'next', navAction: 'window.nextBuffer()' });
            generateSafeQR("qr-nav-prev", "CMD:PREV", 74);
            generateSafeQR("qr-nav-next", "CMD:NEXT", 74);
        } else { n.style.display = 'none'; }
    }

    // 3. Dispatch Event for Location Manager
    document.dispatchEvent(new CustomEvent('inventory:buffer-updated', { detail: { spools: state.heldSpools } }));

    // 4. Save state if not currently syncing from server.
    //    Track local-change timestamp so a concurrent loadBuffer can skip its overwrite,
    //    and queue a retry persist if a sync is currently holding the lock.
    if (window.suppressBufferDirty) {
        // Server-driven render — neither dirty nor persist.
    } else if (!window.isBufferSyncing) {
        window.lastLocalBufferChange = Date.now();
        persistBuffer();
    } else {
        window.lastLocalBufferChange = Date.now();
        window.pendingPersist = true;
    }
};

const removeBufferItem = (id) => {
    const idx = state.heldSpools.findIndex(s => s.id == id);
    if (idx > -1) {
        state.heldSpools.splice(idx, 1);
        renderBuffer();
        showToast("Item Dropped 🗑️");
        if (state.dropMode && state.heldSpools.length === 0) toggleDropMode();
    } else { showToast("Item not in buffer", "warning"); }
};

const requestClearBuffer = () => { if (state.heldSpools.length === 0) return; requestConfirmation("Clear entire Buffer?", clearBuffer); };
const clearBuffer = () => { state.heldSpools = []; renderBuffer(); showToast("Buffer Cleared"); };
const nextBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.push(state.heldSpools.shift()); renderBuffer(); } };
const prevBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.unshift(state.heldSpools.pop()); renderBuffer(); } };

// --- MODES ---
const toggleDropMode = () => { state.dropMode = !state.dropMode; state.ejectMode = false; updateDeckVisuals(); };
const toggleEjectMode = () => { state.ejectMode = !state.ejectMode; state.dropMode = false; updateDeckVisuals(); };
window.resetCommandModes = () => { state.dropMode = false; state.ejectMode = false; updateDeckVisuals(); };
const toggleAudit = () => {
    // 18.2 Part B — the deck-button toggle is the user's SAFE bail. When
    // turning audit off via the button, send CMD:CANCEL (no moves) rather
    // than CMD:DONE (which auto-parks missing spools at UNKNOWN). The
    // panel's explicit "✅ Done & Auto-Park" button is the path for the
    // destructive commit; toggle stays purely additive/reversible.
    // Derek 2026-05-16: previously clicking the deck button while audit
    // was active triggered CMD:DONE and force-moved unscanned spools to
    // UNKNOWN, with no way to bail short of refresh.
    state.auditActive = !state.auditActive;
    updateLogState(true);
    const cmd = state.auditActive ? "CMD:AUDIT" : "CMD:CANCEL";
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: cmd }) });
};

// Explicit commit path — exposed for the panel button. Mirrors the
// CMD:DONE scan: closes audit, missing spools get auto-parked to UNKNOWN.
window.commitAuditWithAutoPark = () => {
    state.auditActive = false;
    updateLogState(true);
    fetch('/api/identify_scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'CMD:DONE' }),
    });
};

const updateDeckVisuals = () => {
    const dropBtn = document.getElementById('btn-deck-drop');
    const ejectBtn = document.getElementById('btn-deck-eject');
    const bufCol = document.querySelector('.col-buffer');

    if (dropBtn) dropBtn.classList.remove('drop-mode-active');
    if (ejectBtn) ejectBtn.classList.remove('eject-mode-active');
    if (bufCol) bufCol.classList.remove('drop-mode-active', 'eject-mode-active');

    if (state.dropMode) {
        if (dropBtn) dropBtn.classList.add('drop-mode-active');
        if (bufCol) bufCol.classList.add('drop-mode-active');
        showToast("DROP MODE: Scan to delete", "warning");
    } else if (state.ejectMode) {
        if (ejectBtn) ejectBtn.classList.add('eject-mode-active');
        if (bufCol) bufCol.classList.add('eject-mode-active');
        showToast("EJECT MODE: Scan to remove spool", "warning");
    }
};

// --- Reusable "shapeshift" deck QR (generalizes the Audit slot) -------------
// A single .deck-qr slot whose ENCODED command, label text, and active CSS
// classes change IN PLACE between named states, driven by a mode flag. The
// Audit slot is the reference (idle: CMD:AUDIT/"AUDIT"  <->  active:
// CMD:DONE/"FINISH"). This factory lets a future multi-state deck command
// (e.g. the backlog's Bulk Moves: arm -> set-dest -> commit) reuse the exact
// same recipe instead of hand-rolling another updateAuditVisuals.
//
// Config: { slot, size, default, states: { <name>: { cmd, label, btnClass,
// labelClass, onEnter } } }. The handle's set(name): (1) clears + re-renders
// the QR via generateSafeQR with the state's cmd; (2) rewrites the label
// innerText; (3) swaps the active classes on the deck button + label — it
// first removes the UNION of every state's classes, then adds the current
// state's, so N states stay clean AND the 2-state audit matches its old
// add/remove behavior exactly; (4) fires the state's onEnter side-effect.
// set() is idempotent — safe to call repeatedly from the backend poll, just
// like the original updateAuditVisuals. Ids follow the deck convention:
// qr-<slot> / lbl-<slot> / btn-deck-<slot>.
window.registerShapeshiftQR = (config) => {
    const cfg = config || {};
    const slot = cfg.slot;
    const size = cfg.size || 85;
    const states = cfg.states || {};
    const qrId = `qr-${slot}`;
    const labelId = `lbl-${slot}`;
    const btnId = `btn-deck-${slot}`;
    const _split = (s) => String(s || '').split(/\s+/).filter(Boolean);
    // Union of every state's active classes, so set() can clear them all first.
    const allBtnClasses = new Set();
    const allLabelClasses = new Set();
    Object.keys(states).forEach((k) => {
        const s = states[k] || {};
        _split(s.btnClass).forEach((c) => allBtnClasses.add(c));
        _split(s.labelClass).forEach((c) => allLabelClasses.add(c));
    });
    let currentName = null;
    const set = (name) => {
        const st = states[name];
        if (!st) return;
        currentName = name;
        const btn = document.getElementById(btnId);
        const lbl = document.getElementById(labelId);
        const qrDiv = document.getElementById(qrId);
        if (btn) {
            allBtnClasses.forEach((c) => btn.classList.remove(c));
            _split(st.btnClass).forEach((c) => btn.classList.add(c));
        }
        if (lbl) {
            allLabelClasses.forEach((c) => lbl.classList.remove(c));
            if (typeof st.label === 'string') lbl.innerText = st.label;
            _split(st.labelClass).forEach((c) => lbl.classList.add(c));
        }
        if (qrDiv) {
            // Always clear first. A state with NO cmd used to leave the previous
            // state's QR rendered under the new label — a scannable command that
            // no longer matches what the tile says (from a bulk-move `preview`
            // that would strand a live CMD:DONE over a half-armed session). No
            // shipped state is cmd-less today; this removes the trap for the
            // next one. (L298 Phase 3.)
            qrDiv.innerHTML = "";
            if (st.cmd) {
                generateSafeQR(qrId, st.cmd, size);
            } else {
                // A synchronous clear is not enough on its own: generateSafeQR
                // renders inside a DOUBLE requestAnimationFrame, so a previous
                // state's render can still be queued and would paint its command
                // back over this cmd-less state. Clear again on the SAME
                // schedule (and only if we're still the current state).
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    const el = document.getElementById(qrId);
                    if (el && currentName === name) el.innerHTML = "";
                }));
            }
        }
        if (typeof st.onEnter === 'function') st.onEnter();
    };
    return { set, reset: () => set(cfg.default), current: () => currentName };
};

// Audit slot migrated onto the shapeshift helper — behavior is identical to the
// former hand-rolled updateAuditVisuals (CMD:AUDIT/"AUDIT" <-> CMD:DONE/"FINISH"
// + the btn-audit-active / label-active-audit classes). The onEnter hooks
// preserve 18.2 Part B's visual audit panel: open it when the session is
// active, close it when it ends — additive to the Activity Log, not a
// replacement (Derek 2026-05-15: "I still like the idea of having the activity
// log reference"). NOTE: audit is deliberately NOT wired into
// resetCommandModes — an audit session must survive opening other modals,
// unlike the drop/eject danger modes. The static idle QR is still seeded once
// in scripts.html; the first updateAuditVisuals() call (from the backend poll
// or toggleAudit) paints the correct state.
const auditShapeshift = window.registerShapeshiftQR({
    slot: 'audit',
    size: 85,
    default: 'idle',
    states: {
        idle:   { cmd: "CMD:AUDIT", label: "AUDIT",  btnClass: '',                 labelClass: '',                   onEnter: () => { if (typeof window.closeAuditPanel === 'function') window.closeAuditPanel(); } },
        active: { cmd: "CMD:DONE",  label: "FINISH", btnClass: 'btn-audit-active', labelClass: 'label-active-audit', onEnter: () => { if (typeof window.openAuditPanel  === 'function') window.openAuditPanel();  } },
    },
});

window.updateAuditVisuals = () => {
    auditShapeshift.set(state.auditActive ? 'active' : 'idle');
};

// --- L298 Phase 2 — BULK MOVE deck slot ------------------------------------
// The 4-state shapeshift the helper's own comment was written for (arm ->
// set-dest -> commit). The LABEL says where the session is; the encoded QR is
// the scanner action available in that state:
//   idle            CMD:BULKMOVE  "BULK MOVE"  — arm a session
//   awaiting_source CMD:CANCEL    "SCAN SRC"   — scan the source LOC label;
//                                                 the QR is the BAIL-OUT
//   awaiting_dest   CMD:CANCEL    "SCAN DEST"  — scan the destination LOC label;
//                                                 the QR is the BAIL-OUT
//   preview         CMD:DONE      "COMMIT"     — explicit commit; a dest scan
//                                                 NEVER auto-commits.
// Both "scan a location label" states deliberately encode CMD:CANCEL: the next
// step there is a physical LOC: label the user walks to, so the useful thing to
// put on the tile is the scanner's way OUT. (An earlier version of this comment
// claimed they encode no cmd — they always have. Don't "restore" that: a state
// with a falsy cmd used to leave the PREVIOUS state's QR on screen, which from
// `preview` would strand a scannable CMD:DONE over a session that only has a
// source. registerShapeshiftQR now CLEARS the QR in that case, but the
// mismatched label would still lie.)
// Like audit, bulk move is NOT wired into resetCommandModes: a session must
// survive opening the Location Manager (that's how the LM button entry works).
const _openBulkPanel = () => {
    if (typeof window.openBulkMovePanel === 'function') window.openBulkMovePanel();
};
const bulkMoveShapeshift = window.registerShapeshiftQR({
    slot: 'bulkmove',
    size: 85,
    default: 'idle',
    states: {
        idle:            { cmd: "CMD:BULKMOVE", label: "BULK MOVE", btnClass: '',                   labelClass: '',                      onEnter: () => { if (typeof window.closeBulkMovePanel === 'function') window.closeBulkMovePanel(); } },
        awaiting_source: { cmd: "CMD:CANCEL",   label: "SCAN SRC",  btnClass: 'btn-bulkmove-active', labelClass: 'label-active-bulkmove', onEnter: _openBulkPanel },
        awaiting_dest:   { cmd: "CMD:CANCEL",   label: "SCAN DEST", btnClass: 'btn-bulkmove-active', labelClass: 'label-active-bulkmove', onEnter: _openBulkPanel },
        preview:         { cmd: "CMD:DONE",     label: "COMMIT",    btnClass: 'btn-bulkmove-ready',  labelClass: 'label-active-bulkmove', onEnter: _openBulkPanel },
    },
});

// Stage → the armed pill's wording. Deliberately says what to DO next, not the
// internal stage name, because this is the thing on screen when the panel is hidden.
const _BULK_PILL_TEXT = {
    awaiting_source: 'scan source',
    awaiting_dest: 'scan dest',
    preview: 'ready to commit',
};

window.updateBulkMoveVisuals = () => {
    const stage = state.bulkMoveActive ? (state.bulkMoveStage || 'awaiting_source') : 'idle';
    bulkMoveShapeshift.set(stage);

    // The armed pill (L298 follow-up, Derek 2026-08-03: "a hide button that makes
    // it go somewhere, but I don't know where to bring it back up"). It is the
    // ALWAYS-VISIBLE way back to the panel — the deck tile can't be that, because
    // its label is the stage and its meaning changes with state. Shown for exactly
    // as long as a session is armed; tapping it reopens the panel.
    const pill = document.getElementById('fcc-bulkmove-pill');
    if (!pill) return;
    if (stage === 'idle') {
        pill.style.display = 'none';
        return;
    }
    const txt = pill.querySelector('#fcc-bulkmove-pill-text');
    if (txt) txt.innerText = _BULK_PILL_TEXT[stage] || 'bulk move';
    pill.classList.toggle('fcc-bulkmove-pill-ready', stage === 'preview');
    // !important so a stale inline display:none (or CSS) can't keep it hidden —
    // the log pill uses the same trick.
    pill.style.setProperty('display', 'inline-flex', 'important');
    pill.style.alignItems = 'center';
};

// Deck-button toggle — STRICTLY NON-DESTRUCTIVE (Derek 2026-08-03).
//   idle    -> arm a session and show the panel
//   armed   -> show the panel
// It can NEVER cancel and NEVER replace. Cancelling is the panel's explicit
// ❌ button or a CMD:CANCEL scan; both are labelled and deliberate.
//
// Why the earlier "armed + panel open -> cancel" arm is gone: it was
// unreachable by mouse anyway (the panel's backdrop covers the deck), and it
// made a tile whose LABEL is the stage ("SCAN SRC", green "COMMIT") also a
// destructive control — so clicking around felt like it randomly reset things.
//
// The server GET is load-bearing, not defensive: local state is STALE-FALSE for
// the first few seconds after a page reload, and going straight to `start` there
// got `already_active` back and raised a "Replace it?" confirm whose Yes
// DISCARDS a plan built from two deliberate physical scans. Resolve the truth,
// then act.
const _showBulkPanel = () => {
    if (typeof window.openBulkMovePanel === 'function') window.openBulkMovePanel({ user: true });
};
const toggleBulkMove = () => {
    // Already-armed sessions stay reachable even with the flag off, so one
    // armed before it was turned off can still be opened and cancelled rather
    // than stranded. Only ARMING a new one is gated.
    if (state.bulkMoveActive) { _showBulkPanel(); return; }
    if (window.FCC_BULK_MOVE_ENABLED === false) {
        showToast('Bulk Moves is turned off. Enable it in ⚙️ Settings → Behavior.',
                  'warning', 7000);
        return;
    }
    fetch('/api/bulk_move_session').then(r => r.json()).then((live) => {
        if (live && live.active) {
            window.applyBulkMoveSession(live);
            _showBulkPanel();
            return;
        }
        return window.fetchT('/api/bulk_move_session', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'start' }),
        }).then(r => r.json()).then((d) => {
            // Someone armed one between our GET and our POST (another tab, a
            // scan). SHOW it rather than offering to replace it.
            if (d && d.already_active) {
                window.applyBulkMoveSession(d && d.session);
                _showBulkPanel();
                showToast("A bulk move is already armed — showing it.", "info");
                return;
            }
            if (!d || !d.success) {
                // e.g. an audit is running — the backend explains why.
                showToast((d && d.msg) || "Couldn't start bulk move", "error", 7000);
                return;
            }
            window.applyBulkMoveSession(d && d.session);
            _showBulkPanel();
        });
    }).catch(() => showToast("Couldn't start bulk move", "error", 7000));
};
window.toggleBulkMove = toggleBulkMove;

// Single place that maps a backend session snapshot onto local state + visuals,
// so the poll, the toggle, the LM button, and the commit all converge.
window.applyBulkMoveSession = (sess) => {
    const active = !!(sess && sess.active);
    state.bulkMoveActive = active;
    state.bulkMoveStage = active ? (sess.stage || 'awaiting_source') : 'idle';
    // Store the SAME "active|stage" signature _syncBulkMoveSignal compares
    // against (inv_core.js). This used to write a bare boolean, so the very next
    // heartbeat always saw a "change" and re-ran updateBulkMoveVisuals — a
    // harmless-but-real redundant repaint, and a drift waiting to matter.
    state.lastBulkMoveState = `${active}|${state.bulkMoveStage}`;
    window.updateBulkMoveVisuals();
    return sess;
};

window.cancelBulkMove = () => {
    window.fetchT('/api/bulk_move_session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' }),
    }).then(r => r.json()).then((d) => {
        window.applyBulkMoveSession(d && d.session);
        // The backend REFUSES a cancel that races an in-flight commit — it can't
        // stop the writes, so it must not claim to. Leave the panel open and say
        // so; the poll closes it when the commit finishes.
        if (d && d.commit_in_flight) {
            showToast((d && d.msg) || "A commit is in progress — it can no longer be cancelled.",
                      "warning", 7000);
            return;
        }
        if (typeof window.closeBulkMovePanel === 'function') window.closeBulkMovePanel();
        showToast("Bulk move cancelled — nothing moved.", "info");
    }).catch(() => showToast("Cancel failed", "error", 7000));
};

// Explicit commit — the panel button's path (the CMD:DONE scan reaches the same
// backend commit).
//
// TIMEOUT (Phase 3): an explicit 120s, not fetchT's 15s default. One commit is
// an O(N) Spoolman write — per spool, perform_smart_move does a get_spool plus
// an update_spool that itself re-reads the spool and its raw extras before the
// PATCH — bracketed by the plan's full spool fetch and one-to-two readbacks. A
// 15-spool sweep is dozens of sequential round-trips in ONE request, so the
// default abort fired over moves that had ALREADY SUCCEEDED and the user was
// told a completed move failed.
window.commitBulkMove = () => {
    // Re-entrancy guard. The panel button is disabled on click, but this is also
    // reachable programmatically, and a second commit would either be refused by
    // the backend lock (and then clear the FIRST commit's processing overlay) or
    // replay a batch that already moved.
    if (window.bulkMoveCommitInflight && window.bulkMoveCommitInflight()) return;
    if (window.bulkMoveCommitInflight) window.bulkMoveCommitInflight(true);
    const _done = () => {
        if (window.bulkMoveCommitInflight) window.bulkMoveCommitInflight(false);
        setProcessing(false);
    };
    setProcessing(true);
    window.fetchT('/api/bulk_move_session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'commit' }),
    }, 120000).then(r => r.json()).then((res) => {
        _done();
        window.applyBulkMoveSession(res && res.session);
        // A PARTIAL failure comes back success=false + a `failed` list + NO msg
        // (execute_bulk_move's tally shape). Bailing on !success therefore toasted
        // a flat "Bulk move failed" after e.g. 8 of 10 spools HAD moved, and
        // skipped the location refresh — while the scan path (already fixed)
        // reported it honestly. Only treat it as a hard failure when nothing was
        // attempted; otherwise fall through to the real tally message below.
        const isPartial = res && res.moved !== undefined && (res.failed || []).length > 0;
        if (!res || (!res.success && !isPartial)) {
            showToast((res && res.msg) || "Bulk move failed", "error", 7000);
            return;
        }
        const moved = res.moved || 0;
        const skipped = (res.skipped || []).length;
        const failed = (res.failed || []).length;
        let msg = `Moved ${moved} spool(s) → ${res.dest || ''}`;
        if (skipped) msg += `, ${skipped} left in place`;
        if (failed) msg += `, ${failed} FAILED`;
        // Group 41.5: the readback couldn't reach Spoolman, so "moved" is what
        // the writes answered, not what was checked afterwards.
        if (res.unverified) msg += ` (couldn't verify with Spoolman; check the Activity Log)`;
        const warn = failed || res.unverified;
        showToast(msg, warn ? "warning" : "success", warn ? 7000 : 4000);
        if (typeof window.closeBulkMovePanel === 'function') window.closeBulkMovePanel();
        if (window.fetchLocations) window.fetchLocations();
        state.lastLocRenderHash = null;
        document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
        if (typeof updateLogState === 'function') updateLogState(true);
    }, () => {
        // RECONCILE, don't assert failure. The request can drop (abort, reload,
        // proxy hiccup) while the server completes every write, logs its SUCCESS
        // summary and clears the session — telling the user "failed" there is a
        // lie that also skipped the location refresh, leaving a stale table.
        //
        // This is the two-argument .then(onFulfilled, onRejected), NOT .catch:
        // a trailing .catch would also swallow a THROW from the success handler
        // above and report a completed, correctly-tallied move as "may still be
        // running".
        _done();
        if (typeof window.refreshBulkMoveSession === 'function') window.refreshBulkMoveSession();
        if (window.fetchLocations) window.fetchLocations();
        state.lastLocRenderHash = null;
        document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
        if (typeof updateLogState === 'function') updateLogState(true);
        showToast("Lost contact during the commit — it may still be running. Check the Activity Log for the result.",
                  "warning", 7000);
    });
};

// --- L298 Phase 4 — keyboard entry (Shift+B) --------------------------------
// Deliberately NON-DESTRUCTIVE, unlike the deck tile's three-way toggle: idle
// arms a session, and an already-armed session just SHOWS its panel. A keyboard
// shortcut that could discard a plan built from two deliberate scans is a
// footgun — cancelling stays on the panel's explicit ❌ button and CMD:CANCEL.
//
// Shift+B rather than a bare letter: guarded against fields AND against a scan
// stream in flight (the `/` global-search key's idiom in fab_drag.js — a barcode
// scanner types its payload as ordinary keydowns, so an unguarded letter key
// fires in the middle of somebody scanning a label).
(function () {
    // Delegates to the canonical definition in inv_core.js — this was one of
    // three identical copy-pasted closures (2026-08-03 scan-path audit).
    const _scanInFlight = () => !!(window.isScanInFlight && window.isScanInFlight());
    document.addEventListener('keydown', (e) => {
        if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.key !== 'B' && e.key !== 'b') return;
        const tag = ((e.target && e.target.tagName) || '').toUpperCase();
        // SELECT belongs here too — inv_wizard.js:577 sets the precedent. A bare
        // letter is native <select> typeahead, and swallowing it breaks jumping
        // to an option by first letter.
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
            || (e.target && e.target.isContentEditable)) return;
        // Don't fire over someone else's overlay/modal. This panel mounts at
        // tier 'standard', so opening it on top of another standard-tier overlay
        // stacks two peers and Escape then closes whichever mountOverlay
        // happens to answer first. (Carve-out idiom from inv_loc_mgr.js.)
        if (document.querySelector('[data-overlay-mount="1"]')
            && !(typeof window.isBulkMovePanelOpen === 'function' && window.isBulkMovePanelOpen())) return;
        if (document.querySelector('.modal.show, .offcanvas.show')) return;
        if (_scanInFlight()) return;
        e.preventDefault();

        // ⚠️ NEUTRALISE THE SCAN ACCUMULATOR. The handler in scripts.html is a
        // SECOND bubble-phase keydown listener on `document` that appends any
        // one-character key, so without this the 'B' lands in state.scanBuffer —
        // and the very next scan of a printed source label arrives as
        // "BLOC:PM-DB-A". CMD codes are substring-matched and slot codes use a
        // regex, but the plain-location branch is PREFIX-matched
        // (`upper_text.startswith("LOC:")`), so it falls through to "Unknown
        // Code (Use LOC: prefix)" — on a perfectly valid label, for the exact
        // scan the panel we just opened is asking for. It would also leave this
        // shortcut's own scan-in-flight guard self-triggering, swallowing a
        // second Shift+B for 500 ms.
        //
        // BOTH mechanisms, deliberately. stopImmediatePropagation works because
        // this file is a plain <script src> (parse-time registration) while the
        // accumulator registers inside DOMContentLoaded — but that ordering is
        // an implicit dependency on scripts.html's layout. The deferred clear is
        // order-independent: it runs after the accumulator whichever way the
        // listeners end up sorted. A synchronous clear here would be useless —
        // it would wipe an empty buffer and the 'B' would land afterwards.
        e.stopImmediatePropagation();
        const st = (typeof state !== 'undefined') ? state : window.state;
        const _clearScanBuffer = () => {
            if (!st) return;
            st.scanBuffer = '';
            st.scanStartTime = 0;
            try { clearTimeout(st.bufferTimeout); } catch (_) { /* noop */ }
        };
        _clearScanBuffer();
        setTimeout(_clearScanBuffer, 0);

        // Same semantics as the deck tile now that the tile is strictly
        // non-destructive (arm-or-show, resolving server truth first), so just
        // delegate — one behaviour, one place to keep correct.
        if (typeof window.toggleBulkMove === 'function') window.toggleBulkMove();
    });
    // Register AFTER load, not at module eval. scripts.html loads inv_cmd.js
    // (line 41) BEFORE shortcuts_registry.js (line 50), so `window.registerShortcut`
    // is still undefined here at eval time and a bare `if (window.registerShortcut)`
    // guard silently skips — the shortcut works but never appears in the `?`
    // reference, quietly breaking the CLAUDE.md rule it exists to satisfy. This is
    // fab_drag.js's idiom (it registers inside its DOMContentLoaded init).
    const _registerBulkShortcuts = () => {
        if (!window.registerShortcut) return;
        window.registerShortcut({
            id: 'bulk-move-open', scope: 'Bulk Move', keys: ['Shift', 'B'],
            description: 'Arm a bulk move — or reopen its preview panel if one is already armed. Never cancels.',
        });
        window.registerShortcut({
            id: 'bulk-move-escape', scope: 'Bulk Move', keys: ['Esc'],
            description: 'Hide the preview panel. The bulk move stays armed; Shift+B brings it back.',
        });
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _registerBulkShortcuts);
    } else {
        _registerBulkShortcuts();
    }
})();

// --- L298 Phase 3 — BULK MOVE PREVIEW / CONFIRM PANEL ----------------------
// Same skeleton as the audit panel: mountOverlay (tier 'standard') + a 2s poll
// of /api/bulk_move_session + a render-hash flicker guard. Phase 2 kept the body
// deliberately lean (stage prompt + counts + flat lists); Phase 3 makes it the
// real review surface:
//   • proper spool tiles (swatch / weight / slot), the audit panel's _renderTile
//     grammar — copied rather than shared, because the two panels' badge
//     vocabularies differ (found/missing/rogue vs move/skip-by-reason);
//   • skipped rows GROUPED by reason, each group collapsible with a count;
//   • capacity / block messages inline, with the refused spools still shown;
//   • the active-print confirm INSIDE the panel (a checkbox that gates Commit)
//     instead of a requestConfirmation hop into a Bootstrap modal that renders
//     BEHIND this overlay and swallows scans.
(function () {
    let _handle = null;
    let _pollTimer = null;
    let _lastRenderHash = null;
    // Poll guard, mirroring inv_core.js's _pulseInflight / _updateLogStateInflight.
    // Without it a degraded backend lets 2s ticks stack on top of each other.
    // _pollPending coalesces a request that arrived while one was in flight, so
    // a post-scan refresh is deferred rather than dropped.
    let _pollInflight = false;
    let _pollPending = false;
    // Bumped whenever the panel closes or the session ends, so an in-flight poll
    // response can tell that it is answering a question nobody is asking now.
    let _panelGen = 0;
    // "The user pressed Hide." The panel auto-opens on every stage change (the
    // shapeshift onEnter), which used to yank a dismissed panel straight back
    // open. Latched here, cleared when the deck button reopens or the session ends.
    let _userHidPanel = false;
    // True from the moment Commit is fired until the response (or its failure)
    // lands. Blocks a second commit at the UI, keeps the button disabled across
    // the mid-commit repaints, and stops a refused duplicate from tearing down
    // the processing overlay that belongs to the real commit.
    let _commitInflight = false;
    // reason -> user's open/closed choice for that skipped group (absent = default).
    const _groupState = new Map();

    // Escapes QUOTES too — these values land inside title="…" attributes, and a
    // text-only escaper would let a spool name break out of the attribute.
    const _esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    // A colour reaches a STYLE attribute, where escaping isn't enough — anything
    // that isn't a bare hex (or a comma-separated multi-colour list) is dropped.
    const _hexOnly = (c) => (/^[0-9a-fA-F,]{3,}$/.test(String(c || '')) ? String(c) : '333');

    // Skip reasons are produced by logic.plan_bulk_move; the icons are cosmetic
    // and an unknown reason still renders with the neutral fallback.
    const _REASON_ICON = {
        'deployed to a live toolhead': '👻',
        'loaded in a toolhead slot': '🖨️',
        'in the scan buffer': '📥',
        'archived': '🗄️',
    };

    // kind: 'move' (green, will move) | 'skip' (amber, left in place)
    //     | 'blocked' (grey, would have moved but a guard refused the batch)
    const _tile = (r, kind) => {
        // Shared swatch renderer so multi-colour spools show their real conic
        // gradient (a hand-rolled `background:#<hex>` renders blank for a
        // comma-separated multi-colour value).
        const swatch = (typeof window.makeSwatchHtml === 'function')
            ? window.makeSwatchHtml(r.color, r.color_direction, { size: 28, borderColor: '#444' })
            : `<span style="display:inline-block;width:28px;height:28px;background:#${_hexOnly(r.color)};
                            border-radius:4px; border:1px solid #444;"></span>`;
        const weight = (r.remaining_weight != null && r.remaining_weight !== '')
            ? `${Math.round(Number(r.remaining_weight) || 0)}g` : '';
        const slot = r.slot ? `slot ${r.slot}` : '';
        const meta = [weight, slot].filter(Boolean).join(' · ');
        const border = kind === 'move' ? '#0f0' : (kind === 'skip' ? '#fc0' : '#666');
        const bg = kind === 'move' ? '#0a2a0a' : (kind === 'skip' ? '#241f10' : '#1a1a1a');
        const badge = kind === 'move'
            ? '<span style="color:#0f0; font-weight:bold;">➡️ move</span>'
            : (kind === 'skip'
                ? '<span style="color:#fc0; font-weight:bold;">⏸️ stays</span>'
                : '<span style="color:rgba(255,255,255,0.6);">🚫 refused</span>');
        // format_spool_display already prefixes its text with "#<id>", so
        // hard-coding another one printed "#48 #48 [Legacy: 42] Sunlu PLA…" and
        // ate width the truncated name needed. Only add the prefix when the
        // display doesn't already carry it.
        const label = String(r.display == null ? '' : r.display);
        const idPrefix = label.indexOf(`#${r.id}`) === 0 ? '' : `#${_esc(r.id)} `;
        return `
            <div class="fcc-bulk-tile" data-spool-id="${_esc(r.id)}" data-kind="${kind}"
                 style="display:flex; align-items:center; gap:10px; padding:8px;
                        background:${bg}; border:1px solid ${border}; border-radius:6px;">
                ${swatch}
                <div style="flex:1; min-width:0;">
                    <div class="text-truncate" style="color:#fff; font-weight:600; font-size:0.9rem;"
                         title="${_esc(label)}">${idPrefix}${_esc(label)}</div>
                    <div style="font-size:var(--fcc-fs-small); color:rgba(255,255,255,0.75);">${_esc(meta)}</div>
                </div>
                <div style="font-size:var(--fcc-fs-label);">${badge}</div>
            </div>`;
    };

    const _grid = (html) => `
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(16.25rem,1fr));
                    gap:6px;">${html}</div>`;

    // Group the skipped rows by reason, first-seen order (which follows
    // plan_bulk_move's own skip-rule order, so it reads consistently).
    const _groupSkipped = (rows) => {
        const groups = new Map();
        (rows || []).forEach((r) => {
            const key = r.reason || 'left in place';
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(r);
        });
        return Array.from(groups.entries());
    };

    const _skippedHtml = (rows) => {
        const groups = _groupSkipped(rows);
        if (!groups.length) return '';
        const total = rows.length;
        return `
            <div style="font-weight:bold; color:#fc0; margin:12px 0 6px;">
                Left in place (${total})
            </div>
            ${groups.map(([reason, items]) => {
                // Big groups start collapsed so a Room-sized skip list doesn't
                // bury the "will move" section; the user's own toggle wins.
                const dflt = items.length <= 5;
                const open = _groupState.has(reason) ? _groupState.get(reason) : dflt;
                const icon = _REASON_ICON[reason] || '⚠️';
                return `
                <details class="fcc-bulk-skip-group" data-reason="${_esc(reason)}" ${open ? 'open' : ''}
                         style="margin-bottom:6px; border:1px solid #4a4020; border-radius:6px;
                                background:#1c1a12;">
                    <summary style="cursor:pointer; padding:6px 8px; color:#ffe08a; font-size:0.85rem;">
                        ${icon} ${_esc(reason)}
                        <span style="color:#fc0; font-weight:bold;">(${items.length})</span>
                    </summary>
                    <div style="padding:6px 8px 8px;">${_grid(items.map(r => _tile(r, 'skip')).join(''))}</div>
                </details>`;
            }).join('')}`;
    };

    const _render = (d) => {
        if (!_handle) return;
        const body = _handle.element.querySelector('#fcc-bulkmove-body');
        if (!body) return;
        const hash = JSON.stringify(d);
        if (hash === _lastRenderHash) return;
        _lastRenderHash = hash;

        const stage = d.stage || 'idle';
        const p = d.preview || null;

        const src = d.source_id ? `<b style="color:#0ff;">${_esc(d.source_id)}</b>` : '<span style="color:#888;">—</span>';
        const dst = d.dest_id ? `<b style="color:#0ff;">${_esc(d.dest_id)}</b>` : '<span style="color:#888;">—</span>';
        const prompt = stage === 'awaiting_source'
            ? 'Scan the <b>SOURCE</b> location label.'
            : (stage === 'awaiting_dest'
                ? 'Scan the <b>DESTINATION</b> location label.'
                : 'Review below, then <b>Commit</b> (or scan CMD:DONE).');

        let previewHtml = `<div class="small" style="color:rgba(255,255,255,0.7);">${prompt}</div>`;
        if (p) {
            const movable = p.movable || [];
            const skipped = p.skipped || [];
            const st = p.stats || { movable: movable.length, skipped: skipped.length };
            if (!p.ok) {
                // BLOCKED. The block message names the constraint; the tiles name
                // the spools it refused, so "2 free of 4, source has 5" is
                // actionable without opening another screen. `movable` here is
                // the plan's display-only would_move set — the commit path still
                // sees an empty movable_ids, so nothing can act on it.
                previewHtml = `
                    <div id="fcc-bulkmove-block" style="padding:10px; border:1px solid #f44; background:#2a0f0f;
                                border-radius:6px; color:#ffb3b3;">🚫 ${_esc(p.msg)}</div>
                    ${movable.length ? `
                        <div style="font-weight:bold; color:rgba(255,255,255,0.7); margin:12px 0 6px;">
                            Would have moved (${movable.length}) — blocked
                        </div>
                        ${_grid(movable.map(r => _tile(r, 'blocked')).join(''))}` : ''}
                    ${_skippedHtml(skipped)}`;
            } else {
                // Heads-up when the SOURCE is a dryer box wired to toolheads.
                // The bindings are deliberately left intact (they describe the
                // plumbing, not the contents) — this only makes the consequence
                // visible: you are about to empty a box that feeds a printer.
                const feeds = (p.source_feeds || []);
                const feedNote = feeds.length ? `
                    <div style="padding:8px; border:1px solid #4a90d9; background:#0f1c2a;
                                border-radius:6px; color:#bcd9f5; margin-bottom:10px; font-size:0.88rem;">
                        🔗 This move empties ${feeds.length > 1 ? 'slots' : 'a slot'} wired to
                        <b>${feeds.map(f => _esc(f)).join(', ')}</b>.
                        The wiring stays — nothing is unwired — but
                        ${feeds.length > 1 ? 'those slots' : 'that slot'} will be empty until you refill
                        ${feeds.length > 1 ? 'them' : 'it'}.
                    </div>` : '';
                previewHtml = `
                    ${feedNote}
                    <div style="margin-bottom:8px;">
                        <span style="color:#0f0; font-weight:bold;">${st.movable}</span> will move,
                        <span style="color:#fc0; font-weight:bold;">${st.skipped}</span> left in place
                    </div>
                    ${movable.length ? `
                        <div style="font-weight:bold; color:#0f0; margin-bottom:6px;">Will move (${movable.length})</div>
                        ${_grid(movable.map(r => _tile(r, 'move')).join(''))}` : ''}
                    ${_skippedHtml(skipped)}
                    ${!movable.length && p.ok ? `<div class="small" style="color:rgba(255,255,255,0.7);">${_esc(p.msg)}</div>` : ''}`;
            }
        }

        // Group 41.7: no "source is printing" opt-in any more. A bulk move never
        // moves a loaded spool, so that strip could never appear on real data.
        const hasPlan = stage === 'preview' && p && p.ok && (p.movable || []).length > 0;
        // _commitInflight: the backend re-plans and stores the result BEFORE the
        // multi-second execute, so the 2s poll repaints mid-commit with an
        // ok/committable plan and used to paint a live, enabled Commit button
        // over a move already in progress. Clicking it was refused by the
        // backend lock — but the client had already cleared the processing
        // overlay, unfreezing the whole dashboard mid-write.
        const canCommit = hasPlan && !_commitInflight;
        const commitLabel = _commitInflight ? '⏳ Committing…' : '🔀 Commit Move';
        // Tell the user the session expires. The idle watchdog silently clears an
        // armed-but-idle session after N minutes; without this notice, walking
        // back to a dead SCAN DEST tile reads as "the app broke" rather than
        // "that timed out". Nothing is ever moved or un-moved by the expiry —
        // say that too, so the notice doesn't read as a data-loss warning.
        const idleMin = d.idle_timeout_min;
        const expiryNote = idleMin ? `
            <div class="small" style="color:rgba(255,255,255,0.55); margin-top:8px;">
                ⏳ This bulk move stays armed for <b>${_esc(idleMin)} min</b> of inactivity,
                then clears itself. Nothing moves either way — you'd just re-scan.
            </div>` : '';
        body.innerHTML = `
            <div style="margin-bottom:10px; font-size:0.95rem;">${src} → ${dst}</div>
            ${previewHtml}
            ${expiryNote}
            <div class="d-flex justify-content-between align-items-stretch gap-3 mt-3 pt-3 border-top border-secondary">
                <div style="flex:1; text-align:center;">
                    <button id="fcc-bulkmove-commit" class="btn btn-success fw-bold w-100 mb-2"
                            ${canCommit ? '' : 'disabled'}>${commitLabel}</button>
                    <div id="fcc-bulkmove-qr-done" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color:rgba(255,255,255,0.75);">Moves everything listed above</div>
                </div>
                <div style="flex:1; text-align:center;">
                    <button id="fcc-bulkmove-cancel" class="btn btn-outline-danger fw-bold w-100 mb-2">❌ Cancel</button>
                    <div id="fcc-bulkmove-qr-cancel" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color:rgba(255,255,255,0.75);">Bail without moving anything</div>
                </div>
            </div>`;

        // --- wire up (listeners, not inline onclick — a spool/location value
        //     must never be interpolated into JS source inside an attribute).
        const commitBtn = body.querySelector('#fcc-bulkmove-commit');
        if (commitBtn) commitBtn.onclick = () => {
            if (commitBtn.disabled || _commitInflight) return;
            // Disable IMMEDIATELY — the fetch is O(N) seconds and the button
            // sits at z 20000, well above the z-9999 processing overlay, so it
            // stays physically clickable for the whole commit.
            commitBtn.disabled = true;
            commitBtn.innerText = '⏳ Committing…';
            window.commitBulkMove && window.commitBulkMove();
        };
        const cancelBtn = body.querySelector('#fcc-bulkmove-cancel');
        if (cancelBtn) cancelBtn.onclick = () => { window.cancelBulkMove && window.cancelBulkMove(); };
        body.querySelectorAll('.fcc-bulk-skip-group').forEach((el) => {
            el.addEventListener('toggle', () => {
                _groupState.set(el.dataset.reason, el.open);
            });
        });

        // generateSafeQR is a script-scope const in inv_core.js — call it by bare
        // name, NOT window.generateSafeQR (that guard silently dropped the audit
        // panel's QRs, Derek 2026-05-16).
        if (typeof generateSafeQR === 'function') {
            generateSafeQR('fcc-bulkmove-qr-done', 'CMD:DONE', 90);
            generateSafeQR('fcc-bulkmove-qr-cancel', 'CMD:CANCEL', 90);
        }
    };

    const _poll = async () => {
        // Never let slow ticks stack — but COALESCE rather than drop: a plain
        // early return silently swallowed refreshBulkMoveSession()'s
        // "re-read right now" after a scan, leaving the panel a full 2s behind
        // the scan the user just made.
        if (_pollInflight) { _pollPending = true; return; }
        _pollInflight = true;
        // Captured so a response that lands AFTER the panel was closed (or the
        // session ended) can't re-mount the panel / re-green the deck tile over
        // a session that no longer exists.
        const gen = _panelGen;
        try {
            // Explicit timeout: without one, a wedged request leaves
            // _pollInflight stuck true and the panel frozen forever.
            const r = await window.fetchT('/api/bulk_move_session', {}, 8000);
            const d = await r.json();
            if (gen !== _panelGen) return;   // stale response — a newer state won
            if (!d || !d.active) {
                window.applyBulkMoveSession(d);
                window.closeBulkMovePanel();
                return;
            }
            // Keep the deck QR in step with the backend stage (idempotent set()).
            if (d.stage && d.stage !== state.bulkMoveStage) {
                state.bulkMoveStage = d.stage;
                state.bulkMoveActive = true;
                window.updateBulkMoveVisuals();
            }
            _render(d);
        } catch (e) { /* network hiccup — retry next tick */ }
        finally {
            _pollInflight = false;
            if (_pollPending) { _pollPending = false; _poll(); }
        }
    };

    // opts.user — an explicit user request (the deck button). It clears the
    // "I hid this" latch; an automatic open (a stage change firing the
    // shapeshift onEnter) respects it and stays closed.
    window.openBulkMovePanel = (opts) => {
        if (opts && opts.user) _userHidPanel = false;
        else if (_userHidPanel) return;
        if (_handle) return;  // idempotent
        if (typeof window.mountOverlay !== 'function') return;
        _lastRenderHash = null;
        const content = `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #00d4ff;
                        border-radius:8px; padding:0.875rem 1rem;
                        width:min(51.25rem,94vw); max-height:80vh; display:flex; flex-direction:column;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div style="font-weight:bold; font-size:1.15em; color:#7fe8ff;">🔀 Bulk Move</div>
                    <button id="fcc-bulkmove-close" class="btn btn-sm btn-outline-light"
                            title="Hide the panel — the bulk move stays armed. The BULK MOVE deck button brings it back. To bail out instead, use ❌ Cancel here or scan CMD:CANCEL.">Hide</button>
                </div>
                <div id="fcc-bulkmove-body" style="overflow-y:auto; flex:1 1 auto;">
                    <div class="small" style="color:rgba(255,255,255,0.7);">Loading…</div>
                </div>
            </div>`;
        _handle = window.mountOverlay({
            id: 'fcc-bulkmove-panel-overlay',
            content,
            tier: 'standard',
            backdrop: true,
            backdropDismiss: false,   // a move is armed; Hide is the explicit dismiss
            // Escape is a DISMISS, same as Hide — it must latch, or the next
            // stage change would drag the panel straight back open.
            onEscape: () => window.closeBulkMovePanel({ hidden: true }),
        });
        const closeBtn = _handle.element.querySelector('#fcc-bulkmove-close');
        if (closeBtn) closeBtn.onclick = () => window.closeBulkMovePanel({ hidden: true });
        _poll();
        _pollTimer = setInterval(_poll, 2000);
    };

    // opts.hidden — the USER dismissed it (Hide / Escape), so don't auto-reopen
    // on the next stage change. Every other caller (session ended, commit done,
    // the idle shapeshift state) closes WITHOUT the latch, which also clears a
    // previous Hide so the next session starts with a visible panel.
    window.closeBulkMovePanel = (opts) => {
        _userHidPanel = !!(opts && opts.hidden);
        _panelGen += 1;          // invalidate any poll response still in flight
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_handle) { try { _handle.cleanup(); } catch (_) { /* noop */ } _handle = null; }
    };

    window.isBulkMovePanelOpen = () => !!_handle;

    // Commit-in-flight accessor for window.commitBulkMove, which lives outside
    // this IIFE. Call with no argument to READ, with a boolean to SET.
    window.bulkMoveCommitInflight = (v) => {
        if (v === undefined) return _commitInflight;
        _commitInflight = !!v;
        _lastRenderHash = null;   // force the next poll to repaint the button state
        return _commitInflight;
    };

    // Poll once RIGHT NOW instead of waiting for the next 2s tick — called after
    // a scan lands so the stage prompt + preview update immediately.
    window.refreshBulkMoveSession = () => { _poll(); };
})();

// --- 18.2 Part B — VISUAL AUDIT PANEL --------------------------------------
// Lives as a mountOverlay (tier 'standard') so it sits above any modal
// stack. Polls /api/audit_session every 2s while audit is active so the
// found/missing tiles tick as the user scans. Closes automatically when
// the audit ends (CMD:DONE / CMD:CANCEL).
(function () {
    let _handle = null;
    let _pollTimer = null;
    // 2026-05-16 — every-2s flicker fix: hash-skip the body innerHTML
    // rewrite when the audit payload hasn't actually changed. Same pattern
    // as updateLogState's lastLogHash. Without this the tile grid + the
    // two QR codes got destroyed and re-created on every tick even when
    // no scan had landed; Derek saw the panel "redraw" every 2-3s.
    let _lastRenderHash = null;
    const _escapeHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const _renderTile = (row, kind) => {
        // kind: 'found' (green check), 'missing' (gray ?), 'rogue' (yellow !)
        const swatchBg = (typeof window.makeSwatchHtml === 'function')
            ? window.makeSwatchHtml(row.color, row.color_direction, { size: 28, borderColor: '#444' })
            : `<span style="display:inline-block;width:28px;height:28px;background:#${row.color || '333'};border-radius:4px;"></span>`;
        const weight = row.remaining_weight != null ? `${Math.round(row.remaining_weight)}g` : '';
        const slot = row.slot ? ` (slot ${_escapeHtml(row.slot)})` : '';
        const badge = kind === 'found'
            ? '<span style="color:#0f0; font-weight:bold;">✅ scanned</span>'
            : (kind === 'rogue'
                ? '<span style="color:#fc0; font-weight:bold;">⚠️ rogue</span>'
                : '<span style="color:rgba(255,255,255,0.7);">⬜ not scanned</span>');
        const border = kind === 'found' ? '#0f0' : (kind === 'rogue' ? '#fc0' : '#555');
        const bg = kind === 'found' ? '#0a2a0a' : (kind === 'rogue' ? '#2a2410' : '#1a1a1a');
        return `
            <div style="display:flex; align-items:center; gap:10px; padding:8px;
                        background:${bg}; border:1px solid ${border}; border-radius:6px;">
                ${swatchBg}
                <div style="flex:1; min-width:0;">
                    <div class="text-truncate" style="color:#fff; font-weight:600; font-size:0.9rem;"
                         title="${_escapeHtml(row.display)}">#${row.id} ${_escapeHtml(row.display)}</div>
                    <div style="font-size:var(--fcc-fs-small); color:rgba(255,255,255,0.75);">${_escapeHtml(weight)}${_escapeHtml(slot)}</div>
                </div>
                <div style="font-size:var(--fcc-fs-label);">${badge}</div>
            </div>
        `;
    };

    const _render = (data) => {
        if (!_handle) return;
        const root = _handle.element;
        const body = root.querySelector('#fcc-audit-panel-body');
        if (!body) return;
        // Hash-skip when payload is unchanged so the 2s poll stops
        // re-rendering the tile grid (and re-generating QR codes) every
        // tick. Derek 2026-05-16 visible-flicker fix.
        const hash = JSON.stringify(data);
        if (hash === _lastRenderHash) return;
        _lastRenderHash = hash;
        const s = data.stats || { total_expected: 0, found: 0, missing: 0, rogue: 0 };
        const expectedTiles = (data.expected || []).map(r => _renderTile(r, r.found ? 'found' : 'missing')).join('');
        const rogueTiles = (data.rogue || []).map(r => _renderTile(r, 'rogue')).join('');
        const loc = _escapeHtml(data.location_id || '(scan a location to start)');
        body.innerHTML = `
            <div style="margin-bottom:10px; font-size:0.95rem;">
                Auditing <b style="color:#0ff;">${loc}</b> —
                <span style="color:#0f0; font-weight:bold;">${s.found}/${s.total_expected}</span> found,
                <span style="color:rgba(255,255,255,0.75); font-weight:bold;">${s.missing}</span> missing,
                <span style="color:#fc0; font-weight:bold;">${s.rogue}</span> rogue
            </div>
            ${data.expected && data.expected.length ? `
                <div style="font-weight:bold; color:#0ff; margin-bottom:6px;">Expected here</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(16.25rem,1fr)); gap:6px; margin-bottom:12px;">
                    ${expectedTiles}
                </div>
            ` : `<div class="small" style="color:rgba(255,255,255,0.7);">Scan a location's QR to populate the expected list.</div>`}
            ${data.idle_timeout_min ? `
                <div class="small" style="color:rgba(255,255,255,0.55); margin-top:8px;">
                    ⏳ This audit stays open for <b>${_escapeHtml(data.idle_timeout_min)} min</b> of
                    inactivity, then clears itself. Nothing is moved either way.
                </div>` : ''}
            ${data.rogue && data.rogue.length ? `
                <div style="font-weight:bold; color:#fc0; margin-bottom:6px;">Rogue (scanned but expected elsewhere)</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(16.25rem,1fr)); gap:6px;">
                    ${rogueTiles}
                </div>
            ` : ''}
            <!-- 18.2 Part B follow-up: surface DONE + CANCEL as explicit
                 click-targets AND QR codes so the user has both keyboard/
                 mouse and scanner exits. Without these the only way out
                 was the deck button (used to auto-DONE; now CANCEL-only). -->
            <div class="d-flex justify-content-between align-items-stretch gap-3 mt-3 pt-3 border-top border-secondary">
                <div style="flex:1; text-align:center;">
                    <button class="btn btn-success fw-bold w-100 mb-2"
                            onclick="window.commitAuditWithAutoPark && window.commitAuditWithAutoPark()">
                        ✅ Done &amp; Auto-Park
                    </button>
                    <div id="fcc-audit-panel-qr-done" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color: rgba(255,255,255,0.75);">
                        Missing spools <b style="color:#fc0;">→ ❓ Unknown</b>
                    </div>
                </div>
                <div style="flex:1; text-align:center;">
                    <button class="btn btn-outline-danger fw-bold w-100 mb-2"
                            onclick="if (typeof toggleAudit==='function') toggleAudit(); else window.closeAuditPanel();">
                        ❌ Cancel Audit
                    </button>
                    <div id="fcc-audit-panel-qr-cancel" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color: rgba(255,255,255,0.75);">
                        Bail without moving anything
                    </div>
                </div>
            </div>
        `;
        // Generate QR codes after the placeholders are in the DOM.
        // `generateSafeQR` is a script-scope const in inv_core.js — accessible
        // by bare name (not on window). The wrong `window.generateSafeQR`
        // guard previously silently dropped these calls, which is why no
        // QR rendered (Derek 2026-05-16).
        if (typeof generateSafeQR === 'function') {
            generateSafeQR('fcc-audit-panel-qr-done', 'CMD:DONE', 90);
            generateSafeQR('fcc-audit-panel-qr-cancel', 'CMD:CANCEL', 90);
        }
    };

    const _poll = async () => {
        try {
            const r = await fetch('/api/audit_session');
            const d = await r.json();
            if (!d || !d.active) {
                window.closeAuditPanel();
                return;
            }
            _render(d);
        } catch (e) { /* network hiccup — try again next tick */ }
    };

    window.openAuditPanel = () => {
        if (_handle) return;  // idempotent
        if (typeof window.mountOverlay !== 'function') return;
        _lastRenderHash = null;  // force first render after open
        const content = `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #ff00ff;
                        border-radius:8px; padding:0.875rem 1rem;
                        width:min(51.25rem,94vw); max-height:80vh; display:flex; flex-direction:column;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div style="font-weight:bold; font-size:1.15em; color:#ff7eff;">
                        🕵️‍♀️ Audit in Progress
                    </div>
                    <button id="fcc-audit-panel-close" class="btn btn-sm btn-outline-light"
                            title="Hide the panel (audit stays active; reopen via the AUDIT deck button while running)">Hide</button>
                </div>
                <div id="fcc-audit-panel-body" style="overflow-y:auto; flex:1 1 auto;">
                    <div class="small" style="color:rgba(255,255,255,0.7);">Loading audit state…</div>
                </div>
            </div>
        `;
        _handle = window.mountOverlay({
            id: 'fcc-audit-panel-overlay',
            content,
            tier: 'standard',
            backdrop: true,
            backdropDismiss: false,  // Audit is in progress; Hide is the explicit dismiss
            onEscape: () => window.closeAuditPanel(),
        });
        const closeBtn = _handle.element.querySelector('#fcc-audit-panel-close');
        if (closeBtn) closeBtn.onclick = () => window.closeAuditPanel();
        // Initial render + start the 2s poll.
        _poll();
        _pollTimer = setInterval(_poll, 2000);
    };

    window.closeAuditPanel = () => {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_handle) { try { _handle.cleanup(); } catch (_) { /* noop */ } _handle = null; }
    };
})();

// --- Prusament matched-scan overlay (Stage 2c) -----------------------------
// Shown after a Prusament QR matches an existing spool: summarizes the blank
// temps the backend backfilled, lets the user accept Prusament's CURRENT spec
// for any temps that DIFFER (writes them via /api/update_filament), and offers
// to queue the spool's label. Built on mountOverlay per project convention
// (z-index / focus-guard / escape are handled there).
window.promptPrusamentMatched = (res) => {
    if (typeof window.mountOverlay !== 'function') {
        showToast(`✅ Matched ${res.filament_name || 'filament'}`, 'success', 4000);
        return;
    }
    const sid = res.spool_id, fid = res.filament_id;
    const name = res.filament_name || 'filament';
    const filled = res.filled || [];
    const conflicts = res.conflicts || [];
    const LABELS = {
        settings_extruder_temp: 'Nozzle (min)', nozzle_temp_max: 'Nozzle (max)',
        settings_bed_temp: 'Bed (min)', bed_temp_max: 'Bed (max)',
    };
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const filledHtml = filled.length
        ? `<div class="text-success small mb-2">🌡️ Backfilled: ${filled.map(f => esc(LABELS[f] || f)).join(', ')}</div>`
        : `<div class="text-muted small mb-2">Temps already current — nothing to backfill.</div>`;

    const conflictHtml = conflicts.length ? `
        <div id="pm-temp-section" class="border border-warning rounded p-2 mb-2" style="background:#2a2a2a;">
            <div class="text-warning small mb-1">⚠️ Prusament's current spec differs from your saved temps:</div>
            ${conflicts.map(c => `
                <div class="d-flex justify-content-between small text-light">
                    <span>${esc(c.label || LABELS[c.field] || c.field)}</span>
                    <span><span style="color:#adb5bd;">${esc(c.current)}°C</span> &rarr; <span class="text-info fw-bold">${esc(c.scanned)}°C</span></span>
                </div>`).join('')}
            <button id="pm-update-temps" class="btn btn-sm btn-warning w-100 mt-2">Update to Prusament's spec</button>
        </div>` : '';

    // L200 — spool weight-field corrections (total / tare), confirm-gated.
    // used_weight is preserved server-side; remaining is recomputed from the
    // corrected total. The `remaining` preview line makes the recompute
    // explicit so the user sees exactly what the print history maps to.
    const sw = res.spool_weight || null;
    const g = (v) => (v === null || v === undefined) ? '—' : `${Math.round(Number(v))}g`;
    let weightHtml = '';
    if (sw && (sw.rows && sw.rows.length || sw.blocked)) {
        const rowLines = (sw.rows || []).map(r => `
            <div class="d-flex justify-content-between small text-light">
                <span>${esc(r.label)}</span>
                <span><span style="color:#adb5bd;">${g(r.current)}</span> &rarr; <span class="text-info fw-bold">${g(r.scanned)}</span></span>
            </div>`).join('');
        const remLine = sw.remaining ? `
            <div class="d-flex justify-content-between small text-light border-top border-secondary mt-1 pt-1">
                <span>Remaining <span class="text-muted">(used ${g(sw.used)} kept)</span></span>
                <span><span style="color:#adb5bd;">${g(sw.remaining.current)}</span> &rarr; <span class="text-success fw-bold">${g(sw.remaining.new)}</span></span>
            </div>` : '';
        const blockedLine = sw.blocked
            ? `<div class="text-warning small mt-1">⚠️ ${esc(sw.blocked)}</div>` : '';
        const applyBtn = (sw.rows && sw.rows.length)
            ? `<button id="pm-update-weights" class="btn btn-sm btn-success w-100 mt-2">📦 Update spool weights</button>` : '';
        weightHtml = `
            <div id="pm-weight-section" class="border border-success rounded p-2 mb-2" style="background:#2a2a2a;">
                <div class="text-success small mb-1">📦 Prusament's spec differs from this spool's weights:</div>
                ${rowLines}
                ${remLine}
                ${blockedLine}
                ${applyBtn}
            </div>`;
    }

    const content = `
        <div class="p-3" style="max-width:26.25rem; background:#1e1e1e; color:#fff; border:1px solid #444; border-radius:8px;">
            <h6 class="text-info mb-1">🎯 Matched Prusament spool</h6>
            <div class="mb-2"><strong>${esc(name)}</strong> <span class="text-muted">— Spool #${esc(sid)}</span></div>
            ${filledHtml}
            ${conflictHtml}
            ${weightHtml}
            <div class="d-flex gap-2 mt-2">
                <button id="pm-queue-label" class="btn btn-sm btn-outline-info flex-fill">🏷️ Queue label</button>
                <button id="pm-done" class="btn btn-sm btn-secondary flex-fill">Done</button>
            </div>
        </div>`;

    const handle = window.mountOverlay({
        id: 'fcc-prusament-matched-overlay',
        content,
        tier: 'standard',
        backdrop: true,
        initialFocus: '#pm-done',
        onEscape: () => { try { handle.cleanup(); } catch (_) { /* noop */ } },
    });
    const ov = handle.element;
    const close = () => { try { handle.cleanup(); } catch (_) { /* noop */ } };

    const doneBtn = ov.querySelector('#pm-done');
    if (doneBtn) doneBtn.onclick = close;

    const queueBtn = ov.querySelector('#pm-queue-label');
    if (queueBtn) queueBtn.onclick = () => {
        if (typeof window.addToQueueWithToast === 'function') {
            window.addToQueueWithToast({ id: sid, type: 'spool', display: name });
        }
        close();
    };

    const updateBtn = ov.querySelector('#pm-update-temps');
    if (updateBtn) updateBtn.onclick = () => {
        const data = { extra: {} };
        conflicts.forEach(c => {
            if (c.native) data[c.field] = Number(c.scanned);
            else data.extra[c.field] = String(c.scanned);
        });
        if (!Object.keys(data.extra).length) delete data.extra;
        updateBtn.disabled = true;
        updateBtn.textContent = 'Updating…';
        fetch('/api/update_filament', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: fid, data }),
        }).then(r => r.json()).then(d => {
            if (d && d.success) {
                showToast(`🌡️ Updated ${conflicts.length} temp(s) on ${name} to Prusament's spec`, 'success', 4000);
                const section = ov.querySelector('#pm-temp-section');
                if (section && ov.querySelector('#pm-update-weights')) {
                    section.remove();   // leave the weight-correction section actionable
                } else {
                    close();
                }
            } else {
                showToast((d && d.msg) || 'Temp update rejected', 'error', 7000);
                updateBtn.disabled = false;
                updateBtn.textContent = "Update to Prusament's spec";
            }
        }).catch(() => {
            showToast('Temp update failed (network)', 'error', 7000);
            updateBtn.disabled = false;
            updateBtn.textContent = "Update to Prusament's spec";
        });
    };

    // L200 — apply the spool weight corrections. Sends the backend's computed
    // `updates` (used-preserving — never includes used_weight) to the dedicated
    // /api/spool/prusament_apply_weights, which RE-VALIDATES against the live
    // spool (refuses if it would archive/unassign or resurrect the spool) and
    // surfaces LAST_SPOOLMAN_ERROR on reject. Closes only the weight section if
    // a temp-conflict section is still pending, so a spool needing both fixes
    // isn't forced into a second scan.
    const weightBtn = ov.querySelector('#pm-update-weights');
    if (weightBtn && sw && sw.updates && Object.keys(sw.updates).length) {
        weightBtn.onclick = () => {
            weightBtn.disabled = true;
            weightBtn.textContent = 'Updating…';
            fetch('/api/spool/prusament_apply_weights', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spool_id: sid, updates: sw.updates }),
            }).then(r => r.json()).then(d => {
                if (d && d.status === 'success') {
                    showToast(`📦 Updated weights on Spool #${sid} from Prusament scan`, 'success', 4000);
                    // Nudge the live surfaces (buffer / details) to repaint with
                    // the corrected remaining without waiting for the next pulse.
                    try { document.dispatchEvent(new CustomEvent('inventory:sync-pulse')); } catch (_) { /* noop */ }
                    const section = ov.querySelector('#pm-weight-section');
                    if (section && ov.querySelector('#pm-update-temps')) {
                        section.remove();   // leave the temp-conflict section actionable
                    } else {
                        close();
                    }
                } else if (d && d.status === 'blocked') {
                    // Live re-validation refused (archived / would-archive). Not an
                    // error — surface the reason and disable the button.
                    showToast(d.msg || 'Weight update not applied', 'warning', 8000);
                    weightBtn.textContent = 'Not applied';
                } else {
                    showToast((d && (d.msg || d.error)) || 'Weight update rejected', 'error', 7000);
                    weightBtn.disabled = false;
                    weightBtn.textContent = '📦 Update spool weights';
                }
            }).catch(() => {
                showToast('Weight update failed (network)', 'error', 7000);
                weightBtn.disabled = false;
                weightBtn.textContent = '📦 Update spool weights';
            });
        };
    }
};

// CMD:EJECTALL empties the location open in the Location Manager, and nothing
// else. Closing the manager blanks #manage-loc-id, so a scan with it closed used
// to ask "Nuke all unslotted in ?", and FORCE EXECUTE sent clear_location for "",
// which ejected every Unassigned spool (2026-09-13). Same open-manager rule as
// CMD:TRASH. Both routes below (the exact client-side match and the backend's
// substring match) come through here.
const ejectAllFromScan = () => {
    const modal = document.getElementById('manageModal');
    const locEl = document.getElementById('manage-loc-id');
    const loc = locEl ? String(locEl.value || '').trim() : '';
    if (!modal || !modal.classList.contains('show') || !loc) {
        showToast('Eject All ignored: open a location in the Location Manager first', 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent('⚠️ CMD:EJECTALL scan ignored: no location is open in the Location Manager', 'WARNING');
        return;
    }
    triggerEjectAll(loc);
};

// Group 42.5b — a LOCATION label scanned in eject mode. Derek's Q-B answer
// (2026-09-18): a toolhead's label ejects that head's one loaded spool, with the
// eject button's confirms; a box, shelf or room, or a head holding 0 or 2
// spools, warns and does nothing. It used to assign the buffer to the head (or
// Quick-Pick its spool) while eject mode stayed on. Claude's call 18: no extra
// "Eject #N?" question (the eject-mode spool scan has none either; the printing
// and "no saved home" prompts still come from the eject itself); eject mode
// stays on and the buffer is left alone; only spools whose OWN location is the
// head count. Audits and bulk moves keep their own scan handling.
const _ejectModeOwnsScans = () => state.ejectMode && !state.auditActive && !state.bulkMoveActive;
const _ejectModeWarn = (msg) => {
    showToast(msg, 'warning', 7000);
    if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
};
const _isSingleHeadRow = (row, id) => {
    if (!row) return false;
    if (['Tool Head', 'MMU Slot', 'No MMU Direct Load'].includes(row.Type)) return true;
    // A dual-role printer that is its own (only) head, the old Core One shape.
    if (row.Type !== 'Printer') return false;
    const heads = (row.toolheads || []).map(t => String((t && t.location_id) || '').toUpperCase()).filter(Boolean);
    return heads.length > 0 && heads.every(h => h === id);
};
const _ejectModeLocationScan = (res) => {
    const id = String(res.id || '').toUpperCase();
    const rows = state.allLocations || [];
    const row = rows.find(l => String(l.LocationID || '').toUpperCase() === id);
    if (!_isSingleHeadRow(row, id)) {
        _ejectModeWarn(`Eject mode: ${id} isn't a toolhead, so nothing was ejected. Scan a spool or a toolhead label, or turn eject mode off.`);
        return;
    }
    // A read that failed is not an empty head (Group 42 review): it said "is
    // empty — PM-DB-4 is still attached; open RCOI-1 to unbind it" about a
    // loaded head, pointing at an Unbind of the box its spool runs from.
    if (res.contents_error) {
        _ejectModeWarn(`Couldn't read ${id} from Spoolman, so nothing was ejected. Scan it again in a moment.`);
        return;
    }
    const loaded = (res.contents || []).filter(c => !c.is_ghost
        && String(c.location || '').replace(/"/g, '').trim().toUpperCase() === id);
    if (loaded.length === 1) {
        window.doEject(loaded[0].id, id);
        return;
    }
    if (loaded.length > 1) {
        _ejectModeWarn(`${id} holds ${loaded.map(c => '#' + c.id).join(' and ')} — scan the label of the one to eject.`);
        return;
    }
    const attached = rows.find(l => l.Type === 'Dryer Box' && parseInt(l['Max Spools'], 10) <= 1
        && String(((l.extra || {}).slot_targets || {})['1'] || '').toUpperCase() === id);
    _ejectModeWarn(attached
        ? `${id} is empty — ${attached.LocationID} is still attached; open ${id} to unbind it.`
        : `${id} is empty — nothing to eject.`);
};

// Group 40.3 — what a slot scan's answer says happened, for a first answer and
// for a replay after a question (Load it instead, Just store it, or a yes):
// mirror the move in the buffer, toast it, and warn (7 s) when the spool landed
// in its slot but not on the head. A store says so ("📦 #57 stored in LR-MDB-1
// slot 1 — XL-1 left as it was"): "Loaded" would claim a load that never
// happened. False for an answer that is not an outcome.
const _slotScanOutcome = (r, { stored = false, head = null, prior = null } = {}) => {
    if (r && (r.action === 'assignment_done' || r.action === 'assignment_partial')) {
        const movedId = r.moved;
        if (movedId != null) {
            state.heldSpools = state.heldSpools.filter(s => s.id !== movedId);
            _markAssignedOut(movedId); // 21.6 — don't let a stale pulse resurrect it
        }
        // Group 40, the same-slot swap (Derek, 2026-10-15): the slot's old spool
        // came off its head into the scan buffer. One render, one save.
        const handedBack = window.takeIntoBuffer(r, { render: false, toast: false });
        if (movedId != null || handedBack.length) renderBuffer();
        const partial = r.action === 'assignment_partial';
        const extraMsg = partial ? ` (${r.remaining_buffer} still in buffer)` : '';
        const msg = stored
            ? `📦 #${movedId} stored in ${r.location} slot ${r.slot}${window.storeToastTail(prior || { expectedFeed: head })}${extraMsg}`
            : `✅ Loaded #${movedId} into ${r.location}:${r.slot}${extraMsg}`;
        showToast(msg, partial ? 'info' : 'success', partial ? 5000 : 4000);
        if (r.not_deployed) {
            // In the box, but the bound toolhead did not get it.
            showToast(`⚠️ #${movedId} is in ${r.location}:${r.slot} but was NOT deployed to ${r.not_deployed_target || 'its toolhead'}: ${r.not_deployed}`, 'warning', 7000);
        }
        window.toastIntoBuffer(handedBack);
        return true;
    }
    if (r && r.action === 'assignment_failed') {
        // A rejected write; the spool is still in the buffer.
        showToast(`❌ #${r.spool} was NOT loaded into ${r.location}:${r.slot}: ${r.msg}`, 'error', 7000);
        return true;
    }
    return false;
};

// The location-scan double-scan rule's memory: which label a scan left open (or
// Quick-Picked from) and the buffer as that scan left it (Group 40.2 review).
const _bufferSig = () => (state.heldSpools || []).map(s => String(s.id)).join(',');
const _noteScannedLoc = (id) => { state.lastScannedLoc = id; state.lastScannedBufferSig = _bufferSig(); };

// Group 40.2 review (s2-rescan-reverses-swap, queued-double-read-hits-next-picker):
// a location label read twice. The second read, queued while the first was being
// handled and replayed after it, reversed a same-slot swap (the spool it had
// just taken off went back onto the head), and in the box picker's loop it
// picked a slot for the NEXT spool. An identical LOC: scan read before the last
// one was answered, or within LOC_REPEAT_MS after, is dropped and said so. Only
// LOC: labels: CMD:NEXT / CMD:PREV are meant to repeat, and a spool read twice
// is already "Already in Buffer". `capturedAt`: when the scanner delivered it
// (scripts.html); a direct call counts as read now. A scan of the same label
// after that is meant, and acts: scanning a slot again right after a swap swaps
// the two straight back (Derek, 2026-10-15: fixing a wrong scan must not hit a
// hidden stop, so the server no longer holds the old spool back).
const LOC_REPEAT_MS = 1500;
window._fccLastLocScan = window._fccLastLocScan || null;
const _isLocRepeat = (key, capturedAt) => {
    const last = window._fccLastLocScan;
    if (!key.startsWith('LOC:') || !last || last.text !== key) return false;
    const at = capturedAt || Date.now();
    return last.doneAt == null || at < last.doneAt + LOC_REPEAT_MS;
};

// Group 40.5 item F (Derek's answer 8, 2026-10-13): what an empty-buffer scan of
// a location label grabs. Only a place that holds one spool grabs one, and only
// the spool really there: a toolhead (or a printer that is its own head) or a
// one-spool row grabs its DIRECT resident, never a ghost (LOC:XL used to grab a
// spool loaded on one of the XL's heads, which the matcher lists under XL, and a
// head scan could grab a stale trail's spool). A single-spool dryer box still
// grabs its own spool, even while it is loaded on a head ("also other single
// spool dryboxes": a scanner can't read a spool's label through a Prusa dry
// box's lid). Printers, rooms, sections and rows open their view instead. A
// label with no location row keeps the old first-spool rule. Returns the item
// or null.
const _quickPickItem = (locData, res) => {
    const contents = (res && Array.isArray(res.contents)) ? res.contents : [];
    if (!contents.length) return null;
    if (!locData) return contents[0];
    const id = String(res.id || '').toUpperCase();
    const direct = contents.find(c => c && !c.is_ghost && String(c.location || '').toUpperCase() === id) || null;
    if (window.isSingleSlotBox && window.isSingleSlotBox(locData)) return direct || contents[0];
    const type = String(locData.Type || '').toLowerCase();
    const headType = type.includes('tool') || type.includes('mmu') || type.includes('direct load');
    const ownHead = type === 'printer' && !(window.isPrinterRowNotHead && window.isPrinterRowNotHead(locData));
    const max = parseInt(locData['Max Spools'], 10);
    if (!(headType || ownHead || (type !== 'printer' && max === 1))) return null;
    return direct;
};

// --- SCAN ROUTER ---
const processScan = (text, source = 'keyboard', capturedAt = null) => {
    const upper = text.toUpperCase();
    const locKey = upper.trim();
    if (_isLocRepeat(locKey, capturedAt)) {
        showToast(`ℹ️ Ignored a second read of ${String(text).trim()}`, 'info', 3500);
        if (window.logClientEvent) window.logClientEvent(
            `ℹ️ Scan "${String(text).trim()}" ignored: the same label was read twice within ${LOC_REPEAT_MS / 1000} s`, 'INFO');
        return;
    }
    // Answered at once unless it reaches the server below (every early return
    // here is an answer); in flight from the request until its answer.
    const locScan = locKey.startsWith('LOC:') ? (window._fccLastLocScan = { text: locKey, doneAt: Date.now() }) : null;
    const locInFlight = () => { if (locScan) locScan.doneAt = null; };
    const locDone = () => { if (locScan && locScan.doneAt == null) locScan.doneAt = Date.now(); };
    // Active-dialog confirm-by-scan (registered via window.attachConfirmQRs).
    // Must run BEFORE the regular CMD: branches so a CMD:CONFIRM:<sid> scan
    // routes to the dialog's callback instead of hitting the backend or the
    // generic CMD-routes below. Returns true on a matched session — fall
    // through to the rest of the dispatch otherwise.
    if (window.routeConfirmScan && window.routeConfirmScan(text)) return;
    // Group 40.3: a load question on screen (the three-way "Load it instead /
    // Just store it / Cancel") holds off every other scan until it is answered.
    // Its own QRs were answered just above; CMD:CANCEL cancels it; anything else
    // is refused and does nothing (a second slot label used to start a second
    // move behind the dialog). The dialog says why too: toasts sit under it.
    let openQuestion = window._fccOpenMoveQuestion;
    while (openQuestion && openQuestion.element && openQuestion.element.isConnected === false) {
        // Its dialog left the page without being answered (Group 40.3 review,
        // B3): every scan was refused while nothing was on screen. The next
        // question still open, if any, holds scans off instead (W3).
        const open = (window._fccOpenMoveQuestions || []).filter(q => q !== openQuestion);
        window._fccOpenMoveQuestions = open;
        openQuestion = open.length ? open[open.length - 1] : null;
        window._fccOpenMoveQuestion = openQuestion;
    }
    if (openQuestion) {
        if (/^CMD:CANCEL(:.*)?$/.test(upper)) { openQuestion.cancel(); return; }
        // A question whose answers are labels (Group 40.5's "Record it as coming
        // from…": a feed slot's label picks it) routes them itself.
        if (typeof openQuestion.route === 'function' && openQuestion.route(text)) { locDone(); return; }
        const why = openQuestion.hint || 'Answer the question on screen first: Load it instead, Just store it, or Cancel';
        showToast(why, 'warning', 7000);
        if (openQuestion.flash) openQuestion.flash(`${why}. (Ignored: ${text})`);
        if (window.logClientEvent) window.logClientEvent(
            `⚠️ Scan "${text}" ignored: "${openQuestion.title}" is still open`, 'WARNING');
        locDone();
        return;
    }
    // Group 40.1: an open slot picker claims every scan next. A choice's label
    // picks it, CMD:CANCEL cancels, anything else is refused with a warning, so
    // a scan never acts behind the picker (slot_picker.js).
    if (window.routePickerScan && window.routePickerScan(text)) { locDone(); return; }
    // A session-scoped CMD:CONFIRM:<sid> that routeConfirmScan didn't claim
    // belongs to a dialog that has already closed. Never let it fall through to
    // the substring-matching routes below and answer whatever unrelated dialog
    // is up now (2026-09-12 review). A stale CMD:CANCEL:<sid> still falls
    // through: cancelling is always safe. A stale CMD:STORE:<sid> (Group 40.3's
    // "Just store it") is a choice too, so it is stopped the same way.
    if (/^CMD:(CONFIRM|STORE):.+/.test(upper)) {
        showToast('That confirm QR belongs to a dialog that has closed — ignored', 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent('⚠️ Stale confirm QR scanned (its dialog had closed) — ignored', 'WARNING');
        return;
    }

    if (upper === 'CMD:AUDIT') { toggleAudit(); return; }
    // L298 Phase 2 — same client-side toggle shape as CMD:AUDIT: arm when idle,
    // safe-bail when running. Location scans + CMD:DONE / CMD:CANCEL are NOT
    // intercepted here; they fall through to the backend, whose active-session
    // gate routes them into process_bulk_move_scan.
    if (upper === 'CMD:BULKMOVE') { toggleBulkMove(); return; }
    if (upper === 'CMD:LOCATIONS') { openLocationsModal(); return; }
    if (upper === 'CMD:WEIGH') { window.openWeighOutModal(); return; }
    if (upper === 'CMD:DROP') { toggleDropMode(); return; }
    if (upper === 'CMD:EJECT') { toggleEjectMode(); return; }
    if (upper === 'CMD:EJECTALL') { ejectAllFromScan(); return; }
    if (upper === 'CMD:UNDO') { triggerUndo(); return; }
    // Never mid-bulk-move: "Clear entire Buffer?" would open BEHIND the bulk panel
    // and swallow every later scan — the same deadlock the backend-answered
    // 'clear' guard below prevents (2026-09-12 review).
    if (upper === 'CMD:CLEAR') {
        if (state.bulkMoveActive) { showToast('The buffer is kept during a bulk move — finish or cancel the move first', 'info', 4000); return; }
        requestClearBuffer(); return;
    }
    if (upper === 'CMD:PREV') { prevBuffer(); return; }
    if (upper === 'CMD:NEXT') { nextBuffer(); return; }
    if (upper.startsWith('CMD:PRINT:')) { const parts = upper.split(':'); if (parts[2]) window.printLabel(parts[2]); return; }
    // Group 39.9 — the CMD:CLEAR guard above, for the eject: its confirm
    // (requestConfirmation, z 1100) would open BEHIND the bulk panel (z 20000)
    // and swallow the scans meant for the session.
    if (upper.startsWith('CMD:TRASH:') && state.bulkMoveActive) {
        showToast('Eject waits until the bulk move is finished or cancelled', 'info', 4000);
        if (window.logClientEvent) window.logClientEvent(`ℹ️ ${upper} ignored: a bulk move is armed — finish or cancel it first`, 'INFO');
        return;
    }
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if (parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }

    // A CONFIRM scan may fire a dialog's callback ONLY while that dialog is
    // genuinely on screen (fully shown, not dismissed). activeModal/pendingConfirm
    // can't say that: a backdrop/Escape dismissal deliberately leaves
    // pendingConfirm armed (the chained re-prompt needs it — see the
    // hidden.bs.modal release in inv_core.js), and a re-prompt queued behind a
    // fade-out is armed before it is visible, so a scanner double-read of the YES
    // QR would confirm a warning (e.g. the active-print override) nobody has read.
    // CANCEL stays unguarded: bailing out is always safe.
    // Say why a CONFIRM scan did nothing, but only when something was armed. A
    // double-read right after a successful confirm, or a stray label, stays quiet
    // as it always was (2026-09-12 review).
    const ignoredConfirm = (id, armed) => {
        const pending = !!(window.isGatingModalPending && window.isGatingModalPending(id));
        if (!armed && !pending) return;
        const why = pending ? "the dialog isn't on screen yet — scan again once it is visible"
                            : 'that confirmation was dismissed';
        showToast(`Confirm scan ignored: ${why}`, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ Confirm scan ignored: ${why}`, 'WARNING');
    };
    const onScreen = (id) => !!(window.isGatingModalOnScreen && window.isGatingModalOnScreen(id));
    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? (onScreen('safetyModal') ? confirmSafety(true) : ignoredConfirm('safetyModal', !!state.pendingSafety)) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? (onScreen('confirmModal') ? confirmAction(true) : ignoredConfirm('confirmModal', !!state.pendingConfirm)) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if (upper.includes('CANCEL')) { closeModal('actionModal'); return; } if (upper.startsWith('CMD:MODAL:')) { if (!onScreen('actionModal')) { ignoredConfirm('actionModal', true); return; } closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }

    // Group 39.3: a slot scan whose slot feeds a printer head waits on that
    // printer server-side; the dim says which ("⏳ Checking XL…").
    const slotScan = /^LOC:([^:]+):SLOT:(\d+)$/i.exec(String(text).trim());
    // Group 42.5b: in eject mode a box's SLOT label is stopped here, because the
    // server would load the buffered spool into the slot (and on to its head)
    // before the browser saw the answer.
    if (slotScan && _ejectModeOwnsScans()) {
        _ejectModeWarn(`Eject mode: a slot label loads your buffer into ${slotScan[1].toUpperCase()} slot ${slotScan[2]}, so nothing was loaded. Scan a spool or a toolhead label, or turn eject mode off.`);
        return;
    }
    setProcessing(true, { label: slotScan && window.printerLabelForTarget
        ? window.printerLabelForTarget(slotScan[1], slotScan[2]) : null });
    locInFlight();
    // `confirmed_fed_heads` (Group 40.3): this page can show the "already
    // running another spool" question, so a slot scan is asked it instead of
    // being refused as a stale page (logic.stale_fed_refusal). Empty: the user
    // has confirmed nothing yet. A blind scan never names a feed (no
    // expected_feed), so a first slot scan stays prompt-free.
    window.fetchT('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, source: source, confirmed_fed_heads: [] }) })
        .then(r => r.json())
        .then(res => {
            locDone();
            setProcessing(false);
            if (res.type === 'command') {
                // Group 41.5: a bulk-move commit the server couldn't verify.
                if (res.warning) showToast(res.warning, 'warning', 7000);
                // L298 Phase 2 — a scan the backend routed into the bulk-move
                // session answers cmd:'clear'. Refresh the panel immediately so
                // the stage prompt / preview updates now, not on the next tick.
                if (state.bulkMoveActive && typeof window.refreshBulkMoveSession === 'function') {
                    window.refreshBulkMoveSession();
                    // DEADLOCK GUARD: every session-routed scan answers cmd:'clear',
                    // but requestClearBuffer prompts "Clear entire Buffer?" when the
                    // buffer is non-empty — and #confirmModal (z 1100) renders BEHIND
                    // the bulk panel (z 20000), so the dialog is invisible while
                    // state.activeModal='confirm' swallows every later scan, including
                    // the destination and CMD:DONE. A non-empty buffer is EXPECTED
                    // here (plan_bulk_move has a dedicated "in the scan buffer" skip
                    // rule), so never clear the buffer mid-bulk-move: buffered spools
                    // are deliberately left in place, nothing consumed them.
                    if (res.cmd === 'clear') return;
                }
                const cmds = { 'clear': requestClearBuffer, 'undo': triggerUndo, 'eject': toggleEjectMode, 'done': closeManage };
                if (cmds[res.cmd]) cmds[res.cmd]();
                // Same on-screen rule as the activeModal routes above. This is the
                // route a dismissed-but-armed pendingConfirm and a stale
                // CMD:CONFIRM:<sid> (routeConfirmScan miss -> backend substring
                // match) both reach.
                else if (res.cmd === 'confirm') { if (state.pendingConfirm && onScreen('confirmModal')) confirmAction(true); else ignoredConfirm('confirmModal', !!state.pendingConfirm); }
                else if (res.cmd === 'slot') handleSlotInteraction(res.value);
                else if (res.cmd === 'ejectall') ejectAllFromScan();
            } else if (res.type === 'assignment') {
                // Backend now handles the load when the buffer is non-empty.
                // We switch on `action` and let the backend's Activity Log
                // cover success/error cases; the frontend only handles the
                // no-buffer fallback (treat as a slot pickup).
                state.lastScannedLoc = null;
                if (res.action === 'assignment_done' || res.action === 'assignment_partial') {
                    // Backend already moved the spool and logged it. The toast and
                    // the buffer mirror are _slotScanOutcome's, shared with the
                    // replays of a question below, so the two can't drift.
                    _slotScanOutcome(res);
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                } else if (res.action === 'assignment_failed') {
                    // The write was rejected (2026-09-12: this used to come back as
                    // assignment_done). The spool is still in the buffer.
                    _slotScanOutcome(res);
                } else if (res.action === 'assignment_no_buffer') {
                    // Buffer Empty → treat as pickup: read slot contents and
                    // put the spool in the buffer. Log explicitly on success
                    // so the user's Activity Log reflects what happened.
                    fetch(`/api/get_contents?id=${res.location}`)
                        .then(r => r.json())
                        .then(items => {
                            const item = items.find(i => String(i.slot) === String(res.slot));
                            if (item) {
                                if (state.heldSpools.some(s => s.id === item.id)) {
                                    showToast("Already in Buffer", "warning", 3500);
                                } else {
                                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color, color_direction: item.color_direction, remaining_weight: item.remaining_weight, details: item.details, archived: item.archived });
                                    renderBuffer();
                                    showToast(`✋ Picked up #${item.id} from ${res.location}:SLOT:${res.slot}`, 'success', 2500);
                                    fetch('/api/log_event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msg: `✋ Pickup: Spool #${item.id} from <b>${res.location}:SLOT:${res.slot}</b>`, level: 'INFO' }) });
                                }
                            } else {
                                showToast(`Slot ${res.slot} on ${res.location} is empty — opening manager`, 'info', 3000);
                                if (window.logClientEvent) window.logClientEvent(
                                    `⚠️ Slot scan ${res.location}:SLOT:${res.slot} — slot is empty (opened manager)`,
                                    'WARNING'
                                );
                                openManage(res.location);
                            }
                        })
                        .catch(e => {
                            console.error(e);
                            showToast("Error looking up slot", "error", 5000);
                            if (window.logClientEvent) window.logClientEvent(
                                `❌ Slot pickup failed for ${res.location}:SLOT:${res.slot}: ${e && e.message ? e.message : 'network error'}`,
                                'ERROR'
                            );
                        });
                } else if (res.action === 'assignment_bad_slot') {
                    const limit = res.max_slots != null ? ` (has ${res.max_slots} slots)` : '';
                    showToast(`❌ Slot ${res.slot} invalid for ${res.location}${limit}`, 'error', 5000);
                } else if (res.action === 'assignment_bad_target') {
                    showToast(`❌ ${res.location} isn't a valid load target`, 'error', 5000);
                } else if (res.action === 'assignment_requires_confirm') {
                    // The server asks before it loads: a printing head (the
                    // yes / no), or a bound slot's head already running a spool
                    // from somewhere else, or a printing head the slot could just
                    // store for (Group 40.3's three-way: Load it instead / Just
                    // store it / Cancel). The shared dispatcher shows the right
                    // one and builds the replay from the ORIGINAL scan: every
                    // head and confirm key confirmed so far (asked again on a
                    // replay, it re-asks with the union, Group 39 review
                    // engine-5), the feed the question named, and the spool it
                    // named (`moved`), never the buffer's top as it is now.
                    const original = { text: text, source: source, confirmed_toolheads: [], confirmed_fed_heads: [] };
                    const ask = (answer, prior) => window.askMoveConfirm(answer, {
                        door: 'slot_scan', original, prior,
                        box: answer.location || res.location,
                        slot: answer.slot != null ? answer.slot : res.slot,
                        ids: { overlay: 'fcc-active-print-scan-overlay', yes: 'fcc-aps-yes', no: 'fcc-aps-no', store: 'fcc-aps-store' },
                        askYesNo: (ans, yes) => _confirmActivePrintScan({
                            tid: ans.location || res.location,
                            slot: ans.slot != null ? ans.slot : res.slot,
                            stateInfo: ans.active_print
                                || { printer_name: ans.location || res.location, state: 'PRINTING' },
                            msg: ans.msg,
                            onConfirm: yes,
                        }),
                        send: (body, next) => {
                            setProcessing(true, { label: window.printerLabelForTarget
                                ? window.printerLabelForTarget(res.location, res.slot) : null });
                            window.fetchT('/api/identify_scan', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(body),
                            })
                                .then(r => r.json())
                                .then(r2 => {
                                    setProcessing(false);
                                    if (r2 && r2.action === 'assignment_requires_confirm') {
                                        ask(r2, next);
                                        return;
                                    }
                                    // The same outcome toasts as a first answer
                                    // (a confirmed load used to get no toast and
                                    // keep the spool in the buffer strip).
                                    if (!_slotScanOutcome(r2, { stored: next.store, head: next.expectedFeed, prior: next })) {
                                        if (r2 && r2.type === 'error' && r2.msg) {
                                            showToast(r2.msg, 'error', 7000);
                                        } else {
                                            // An answer this replay doesn't know is never a
                                            // success (it used to toast a confirm question
                                            // green for 3 s while nothing moved).
                                            const what = (r2 && (r2.msg || r2.action)) || 'no answer';
                                            showToast(`⚠️ Assign after confirm: ${what} — check the Activity Log`, 'warning', 7000);
                                            if (window.logClientEvent) window.logClientEvent(
                                                `⚠️ Slot-scan confirm replay got an unexpected answer: ${what}`, 'WARNING');
                                        }
                                    }
                                    document.dispatchEvent(
                                        new CustomEvent('inventory:locations-changed'));
                                })
                                .catch(e => {
                                    setProcessing(false);
                                    console.error(e);
                                    showToast('Assign failed after confirm', 'error', 7000);
                                });
                        },
                    });
                    ask(res, {});
                } else {
                    // Unknown action code — shouldn't happen, but surface it.
                    showToast(`Unknown assignment result: ${res.action || 'none'}`, 'warning', 4000);
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Unknown assignment action from backend: ${res.action || 'none'}`,
                        'WARNING'
                    );
                }
            } else if (res.type === 'location') {
                // Group 42.5b: eject mode decides first (the location-scan order
                // the Group 40 pickers build on: eject mode, then the legacy
                // label note, then the buffered / empty-buffer branches).
                if (_ejectModeOwnsScans()) { state.lastScannedLoc = null; _ejectModeLocationScan(res); return; }
                if (!text.toUpperCase().startsWith('LOC:')) {
                    const msg = "⚠️ Legacy Location Label Scanned! Features may be limited. Print a new LOC: label when possible.";
                    showToast(msg, "warning", 3500);
                    fetch('/api/log_event', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg: "SCAN LOG: Legacy Location Barcode Scanned (" + text + ")", level: "WARNING"}) });
                }
                // The double-scan rule: the same label again right after it opened
                // the manager or Quick-Picked its spool clears that and opens the
                // manager. Only while the buffer is as that scan left it (Group
                // 40.2 review): a spool buffered since by a pickup or the ID field
                // was silently dropped, and the box picker never opened.
                if (state.lastScannedLoc === res.id && state.lastScannedBufferSig === _bufferSig()) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
                state.lastScannedLoc = null;
                if (state.heldSpools.length > 0) {
                    // L124 fix: a toolhead / single-spool location can only hold
                    // one spool. Bulk-assigning the entire buffer to a toolhead
                    // sent every spool's Spoolman location to that toolhead,
                    // which broke filabridge's one-spool-one-toolhead invariant
                    // AND made all the buffered spools appear loaded on the
                    // printer. Detect single-occupancy targets up-front and
                    // pass only the topmost spool; keep the rest in the buffer
                    // so the user can scan their next destination.
                    const locData = state.allLocations.find(l => l.LocationID === res.id);
                    const locType = (locData && locData.Type) ? String(locData.Type).toLowerCase() : '';
                    // L271 Phase 5: Wall Shelf/Row are structural grouping nodes —
                    // never seat spools on them (keep the buffer so the user can rescan).
                    if (locType === 'wall shelf' || locType === 'row') {
                        showToast("That's a structural Wall Shelf/Row node — it can't hold spools. Scan a section or box instead.", "warning", 7000);
                        state.lastScannedLoc = null;
                        return;
                    }
                    const isSingleSpoolType = locType.includes('tool') || locType.includes('mmu') || locType.includes('direct load');
                    let maxSpools = 0;
                    if (locData) {
                        const raw = parseInt(locData['Max Spools'], 10);
                        if (!isNaN(raw)) maxSpools = raw;
                    }
                    // Group 40.2 (Derek's D2.1): a multi-slot box's own label opens
                    // the slot picker, once per buffered spool (Q1: loop), instead
                    // of filing the buffer with no slot. A single-slot box (a
                    // PolyDryer) and every other row keep the path below.
                    if (locType === 'dryer box' && maxSpools > 1 && window.openSlotPicker) {
                        state.lastScannedLoc = null;
                        _placeBufferWithPicker(res.id);
                        return;
                    }
                    // Group 40.5 (Derek's D3): a Printer row that isn't its own
                    // toolhead (LOC:XL, LOC:RCOI) opens the Printer picker, once per
                    // buffered spool (Q1: loop): a head, or a Printer Pool slot. It
                    // used to file the whole buffer on the printer row itself (the
                    // engine refuses that since 40.0a).
                    if (window.isPrinterRowNotHead && window.isPrinterRowNotHead(locData) && window.openSlotPicker) {
                        state.lastScannedLoc = null;
                        _placeBufferWithPicker(res.id);
                        return;
                    }
                    const singleOccupancy = isSingleSpoolType || (maxSpools > 0 && maxSpools <= 1);
                    if (singleOccupancy && state.heldSpools.length > 1) {
                        const top = state.heldSpools[0];
                        showToast(`Toolhead holds 1 spool — assigning #${top.id}; ${state.heldSpools.length - 1} stays in buffer`, "info", 5000);
                        performContextAssign(res.id, null, false, [top.id]);
                    } else {
                        performContextAssign(res.id);
                    }
                    state.lastScannedLoc = null;
                    return;
                }
                const locData = state.allLocations.find(l => l.LocationID === res.id);
                const spool = _quickPickItem(locData, res);
                if (spool) {
                    state.heldSpools.unshift({ id: spool.id, display: spool.display, color: spool.color, color_direction: spool.color_direction, remaining_weight: spool.remaining_weight, details: spool.details, archived: spool.archived, location: spool.location, is_ghost: spool.is_ghost, slot: spool.slot, deployed_to: spool.deployed_to });
                    renderBuffer();
                    showToast("⚡ Quick Pick: #" + spool.id);
                    _noteScannedLoc(res.id);
                    return;
                }
                // Empty-location scan (buglist: "if a legacy barcode has no spools
                // attached, warn + offer to add"). A location/legacy label that
                // resolves to ZERO spools used to open the manager SILENTLY, leaving
                // the user wondering why nothing happened. Warn + log + open the
                // manager (which carries the Add-Spool affordance) — mirrors the
                // empty-SLOT path above. Scoped to the truly-empty case so it never
                // fires for quick-pick or buffer-assign flows.
                if (res.contents_error) {
                    // Group 42 review: the server couldn't read the location, so
                    // "is empty" would be a guess. The manager re-reads it.
                    showToast(`Couldn't read ${res.id} from Spoolman — opening it so you can check.`, 'warning', 7000);
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Location scan ${res.id} — ${res.contents_error} (opened manager)`, 'WARNING');
                    openManage(res.id); _noteScannedLoc(res.id);
                    return;
                }
                if (!res.contents || res.contents.length === 0) {
                    showToast(`📭 ${res.id} is empty — no spools here. Use the manager to add one.`, 'info', 6000);
                    if (window.logClientEvent) window.logClientEvent(
                        `📭 Location scan ${res.id} — no spools attached (opened manager)`,
                        'WARNING'
                    );
                    openManage(res.id); _noteScannedLoc(res.id);
                    return;
                }
                openManage(res.id); _noteScannedLoc(res.id);
            } else if (res.type === 'spool') {
                if (state.dropMode) { removeBufferItem(res.id); return; }
                if (state.ejectMode) { ejectSpool(res.id, "Scan", false); return; }

                state.lastScannedLoc = null;
                if (!res.display) { showToast("Spool ID found but data missing!", "error"); return; }
                // L128 follow-up (2026-05-15): the "already verified"
                // toast was MORE noisy than the log line it replaced —
                // reverted to writing to Activity Log only. The
                // label_already_verified flag is still emitted for any
                // future surface that needs it; we just don't toast.
                if (state.heldSpools.some(s => s.id === res.id)) showToast("Already in Buffer", "warning");
                else { state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color, color_direction: res.color_direction, remaining_weight: res.remaining_weight, details: res.details, archived: res.archived, location: res.location, is_ghost: res.is_ghost, slot: res.slot, deployed_to: res.deployed_to }); renderBuffer(); }
            } else if (res.type === 'ambiguous') {
                // Item 3.6 — backend found multiple spools attached to this
                // legacy id. Prompt the user to disambiguate. "Use selected"
                // re-routes through processScan with explicit ID:NNN so the
                // normal spool path runs (label-verify, buffer add, etc.).
                // "Print new label" is handled inside the picker module.
                if (typeof window.showLegacySpoolPicker === 'function') {
                    window.showLegacySpoolPicker(res, {
                        onSelect: (sid) => { processScan(`ID:${sid}`, 'barcode'); },
                        onAbort: () => { /* user cancelled or chose to re-print */ },
                    });
                } else {
                    // Fallback: log and bail rather than silently auto-pick.
                    console.warn("[inv_cmd] showLegacySpoolPicker missing; ambiguous scan dropped");
                    showToast(`Multiple spools share legacy ID ${res.legacy_id} — open Backlog to print fresh labels`, "warning", 6000);
                }
            } else if (res.type === 'filament') {
                // L128 follow-up (2026-05-15): see spool branch — reverted
                // to Activity Log only; no per-scan toast.
                openFilamentDetails(res.id);
            } else if (res.type === 'prusament_matched') {
                // Matched an existing spool: the backend already backfilled blank
                // temps. The overlay summarizes that, resolves any differing-temp
                // conflicts (Update to Prusament's spec), and offers queue-label.
                if (res.status === 'error') {
                    showToast(res.msg || 'Prusament temp backfill failed', 'error', 7000);
                } else if (typeof window.promptPrusamentMatched === 'function') {
                    window.promptPrusamentMatched(res);
                } else {
                    showToast(`✅ Matched ${res.filament_name || 'filament'}`, 'success', 4000);
                }
            } else if (res.type === 'prusament_new') {
                // No existing spool matched — onboard by opening the Add wizard
                // and driving the Step-3 per-spool Prusament scan for the first
                // spool row. That single path fills BOTH halves: it matches (or
                // creates) the filament AND captures the spool's per-spool data.
                // (The old Step-2 "Import from External" did only the filament
                // half, so the spool came up empty whenever the filament already
                // existed — the bug Derek hit.)
                showToast('🆕 New Prusament spool — opening the Add wizard to onboard it', 'info', 4500);
                if (typeof window.openWizardModal === 'function') {
                    Promise.resolve(window.openWizardModal()).then(() => {
                        const rowEl = document.querySelector('[data-spool-row-idx]');
                        if (rowEl && typeof window.wizardScanSpoolRow === 'function') {
                            const idx = parseInt(rowEl.getAttribute('data-spool-row-idx'), 10) || 0;
                            // Show the URL in the row's field too — the badge-only
                            // render doesn't refresh the input — so the user can see
                            // and copy it. wizardScanSpoolRow still takes it by arg.
                            const urlInput = rowEl.querySelector("input[type='url']");
                            if (urlInput) urlInput.value = res.url || '';
                            window.wizardScanSpoolRow(idx, res.url || '');
                        } else if (typeof window.wizardSearchExternal === 'function') {
                            // Fallback (older markup): filament-half only.
                            const q = document.getElementById('wiz-search-external');
                            if (q) { q.value = res.url || ''; window.wizardSearchExternal(true); }
                        }
                    });
                }
            } else if (res.type === 'error') showToast(res.msg, 'error');
        })
        .catch((e) => { locDone(); setProcessing(false); console.error(e); showToast("Scan Error", "error"); });
};

// The active-print confirm for a scan assign: the shared one (inv_core.js,
// Group 39.4), with this overlay's proven ids (#fcc-active-print-scan-overlay,
// #fcc-aps-yes/no). It shows the server's message when the backend asked
// (`msg`: Derek's D6 wording), else this door's own sentence.
const _confirmActivePrintScan = ({ tid, slot, stateInfo, onConfirm, onCancel = null, msg = '' }) => {
    window.confirmActivePrint({
        activePrint: stateInfo,
        msg: msg || `Assigning the buffered spool(s) to ${tid} will disrupt the active print. Continue anyway?`,
        ids: { overlay: 'fcc-active-print-scan-overlay', yes: 'fcc-aps-yes', no: 'fcc-aps-no' },
        onConfirm,
        onCancel,
    });
};

// `confirmedHeads`: the heads whose active-print warning the user confirmed
// (Group 39.1); anything else (the old `false`) confirms none. `pickedSlot`
// (Group 40.0e): the slot the engine picked for this slotless move when it
// asked (`target_slot`), sent back as `picked_slot`: kept only while still free.
// `opts` (Group 40.2, the box picker): `expectedFeed`, what the picked tile
// showed the slot feeding (sent on the FIRST request, so a slot re-pointed
// meanwhile is asked about again); `swapDisplaced`, the slot's old spool the
// user chose to Swap into the buffer once the move lands (the grid's Swap);
// `onOutcome({outcome, res})`, called once when the move has ended: 'moved',
// 'cancelled' (the user cancelled a question it asked: nothing moved) or
// 'failed'. A callback, never a returned Promise: a caller (or a test's
// page.evaluate) that awaited one would wait on a question nobody can answer
// until it returns. `origin` (Group 40 review): what the undo record calls the
// move; 'buffer' (the default) makes Undo put the spools back at the TOP of the
// scan buffer, so a door placing spools that were never buffered (the wizard's
// new spools) names itself instead.
const performContextAssign = (tid, slot = null, confirmedHeads = [], spoolIdsOverride = null, pickedSlot = null,
                              opts = {}) => {
    let ended = false;
    const end = (how, res = null) => {
        if (ended) return;
        ended = true;
        if (opts && typeof opts.onOutcome === 'function') {
            try { opts.onOutcome({ outcome: how, res }); } catch (e) { console.error(e); }
        }
    };
    // L124: callers can pass an explicit `spoolIdsOverride` subset (e.g. the
    // single topmost id when the target is a toolhead) so the rest of the
    // buffer stays untouched. Default = entire buffer (the legacy bulk-assign
    // behavior).
    const spoolIds = Array.isArray(spoolIdsOverride) && spoolIdsOverride.length
        ? spoolIdsOverride.slice()
        : state.heldSpools.map(s => s.id);
    // The request as first sent: every replay of a question is rebuilt from it
    // (Group 40.3, window.buildMoveReplay). `confirmed_fed_heads`: this page can
    // show the "already running another spool" question.
    const original = {
        location: tid,
        spools: spoolIds,
        slot: slot,
        origin: (opts && opts.origin) || 'buffer',
        confirmed_toolheads: [],
        confirmed_fed_heads: [],
    };
    // `opts.autoDeploy === false` (Group 40.2 review): the picker's tile said the
    // spool is stored there, not loaded back (a slot feeding the head it is
    // leaving); an explicit `slot` would otherwise load it straight back. On
    // `original`, so every replay stays a store.
    if (opts && opts.autoDeploy === false) original.auto_deploy = false;
    // Swap option C: the picker's Swap. The server files the slot's old spool
    // back where it sat before the slot and names it in `to_buffer`; on
    // `original`, so every replay of a question is still a Swap.
    if (opts && opts.swapDisplaced) original.swap = true;
    // Group 40.5: the Printer picker's "came from" answer ('' = No box), on
    // `original` so a replay of the server's printing question keeps it.
    if (opts && opts.recordSource !== undefined) original.record_source = opts.recordSource;
    // Group 51.6 / 51.7: what the picker showed on the head picked, and in the
    // slot chosen for Swap / Overwrite; on `original`, so every replay checks it.
    if (opts && Array.isArray(opts.expectedResidents)) original.expected_residents = opts.expectedResidents.slice();
    if (opts && opts.expectedOccupant != null) original.expected_occupant = opts.expectedOccupant;
    const first = Object.assign({}, original, {
        confirmed_toolheads: Array.isArray(confirmedHeads) ? confirmedHeads : [],
    });
    if (pickedSlot != null) first.picked_slot = pickedSlot;
    const expectedFeed = (opts && opts.expectedFeed != null) ? String(opts.expectedFeed).toUpperCase() : null;
    if (expectedFeed != null) first.expected_feed = expectedFeed;

    const post = (payload, prior) => {
        // The slot this request fills, named or picked (Group 40.2 review: a
        // picker's free slot goes as picked_slot, and the dim lost its
        // "⏳ Checking XL…" while the chain asked the printer).
        const filling = (payload.slot != null && payload.slot !== '') ? payload.slot : payload.picked_slot;
        setProcessing(true, { label: window.printerLabelForTarget ? window.printerLabelForTarget(tid, filling) : null });
        // Only a request that got no answer says "failed": an exception in the
        // success handling below follows a move that landed, so it goes to the
        // console (as it always did) and never toasts a failure over it.
        const noAnswer = (e) => {
            setProcessing(false);
            showToast(`❌ Assign to ${tid} failed: ${(e && e.message) || 'network error'} — check the Activity Log`, 'error', 7000);
            if (window.logClientEvent) window.logClientEvent(
                `❌ Assign to ${tid} got no answer: ${(e && e.message) || 'network error'}`, 'ERROR');
            end('failed');
        };
        // A question the user cancelled moved nothing; a replaced one, or one
        // this page can't show, is the end of it too (nobody answered).
        const cancelled = (info) => end(info && (info.superseded || info.unknown) ? 'failed' : 'cancelled');
        // How a move that answered ended, decided before the screen updates, so
        // an exception while updating it can't report a landed move as failed.
        let landed = null;
        window.fetchT('/api/smart_move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(r => r.json())
            .then(x => x, (e) => { noAnswer(e); return null; })
            .then(res => {
                if (res === null) return;
                setProcessing(false);
                // The server asks before it loads: a printing head (the yes /
                // no), or a bound slot's head already running a spool from
                // elsewhere or printing (40.3's three-way). Group 40.0e: a
                // slotless move into a multi-slot box gets its slot BEFORE the
                // question (`target_slot`), so a replay names it (`picked_slot`:
                // kept only while still free, never unseating a spool that took
                // it meanwhile) and names the spools the question was about: the
                // buffer can change while the dialog is open.
                if (res.status === 'requires_confirm' && window.askMoveConfirm) {
                    window.askMoveConfirm(res, {
                        door: 'smart_move', original, prior, box: tid, slot,
                        ids: { overlay: 'fcc-active-print-scan-overlay', yes: 'fcc-aps-yes', no: 'fcc-aps-no', store: 'fcc-aps-store' },
                        askYesNo: (ans, yes) => _confirmActivePrintScan({
                            tid, slot,
                            stateInfo: ans.active_print || { printer_name: tid, state: 'ACTIVE' },
                            msg: ans.msg,
                            onConfirm: yes,
                            onCancel: cancelled,
                        }),
                        send: (body, next) => post(body, next),
                        onCancel: cancelled,
                        // The picker knew the slot holds a stale record the engine
                        // would refuse a store over (Group 40.2 review): no "Just
                        // store it" that would only be refused.
                        noStore: !!(opts && opts.noStore),
                    });
                    return;
                }
                if (res.blocked_reason === 'residents_changed' || res.blocked_reason === 'occupant_changed') {
                    // Group 51.6 / 51.7: the head or slot holds a spool the picker
                    // never showed. Nothing moved; 'cancelled' opens the picker
                    // again (window.placeOneWithPicker), drawn from fresh data.
                    // Checked before 'success': step 6's occupant_changed answers
                    // status 'success' with the spool in `failures` (review engine-2).
                    showToast(`⚠️ ${res.msg || ((res.failures || {})[String((payload.spools || spoolIds)[0])])
                        || 'That place changed since you picked it: pick again'}`, 'warning', 7000);
                    end('cancelled', res);
                    return;
                }
                if (res.status === 'success') {
                    // A rejected write still answers status 'success' and names the
                    // spool in res.failures. Every spool used to leave the buffer
                    // under "Assigned N items!" regardless (2026-09-12).
                    const moving = Array.isArray(payload.spools) && payload.spools.length ? payload.spools : spoolIds;
                    const failures = res.failures || {};
                    const movedIds = moving.filter(id => !failures[String(id)]);
                    const movedCount = movedIds.length;
                    landed = movedCount ? 'moved' : 'failed';
                    // Group 40.0d: a toolhead scan names the feed slot the engine
                    // recorded as the spool's home; the choice is silent, so the
                    // toast is where it shows.
                    const rec = (res.recorded_source && movedCount === 1)
                        ? String(res.recorded_source).split(':') : null;
                    const storedIn = payload.picked_slot != null ? payload.picked_slot : payload.slot;
                    const hasSlot = storedIn != null && storedIn !== '';
                    if (prior && prior.store && movedCount === 1) {
                        // Group 40.3: "Just store it" put it in the slot and left the head alone.
                        showToast(`📦 #${movedIds[0]} stored in ${tid}${hasSlot ? ` slot ${storedIn}` : ''}`
                            + `${window.storeToastTail(prior)}`, 'success', 4000);
                    } else if (payload.auto_deploy === false && movedCount === 1) {
                        // A store from the start (the picker's "stored here, not loaded back").
                        showToast(`📦 #${movedIds[0]} stored in ${tid}${hasSlot ? ` slot ${storedIn}` : ''}`,
                            'success', 4000);
                    } else if (rec && rec.length === 2) {
                        showToast(`#${movedIds[0]} → ${tid} (recorded as from ${rec[0]} slot ${rec[1]})`, "success");
                    } else if (movedCount === 1 && res.record_source_ignored) {
                        // Group 40 review (BD-3): the spool arrived with its own trail,
                        // so the "came from" answer was not used; say which home it kept.
                        showToast(`✅ #${movedIds[0]} → ${tid} (its home stays ${res.record_source_kept || 'its box'})`,
                            'success', 4000);
                    } else if (movedCount === 1 && payload.record_source === '') {
                        // Group 40.5: "No box" (or no free slot fed the head).
                        showToast(`✅ #${movedIds[0]} → ${tid} (no box slot recorded)`, 'success', 4000);
                    } else if (movedCount === 1 && hasSlot) {
                        // Group 40.2: a picked slot says where it went (and the head
                        // its slot loaded), in short arrows.
                        showToast(`✅ #${movedIds[0]} → ${tid} slot ${storedIn}`
                            + `${res.auto_deployed_to ? ` → ${res.auto_deployed_to}` : ''}`, 'success', 4000);
                    } else if (movedCount) {
                        showToast("Assigned " + movedCount + " item" + (movedCount === 1 ? '' : 's') + "!", "success");
                    }
                    moving.filter(id => failures[String(id)]).forEach(id =>
                        showToast(`❌ #${id} was NOT assigned to ${tid}: ${failures[String(id)]}`, 'error', 7000));
                    Object.entries(res.auto_deploy_skipped || {}).forEach(([id, why]) =>
                        showToast(`⚠️ #${id} is in ${tid} but was NOT deployed to ${res.auto_deploy_target || 'its toolhead'}: ${why}`, 'warning', 7000));
                    // Drop only the spools we actually moved; preserve the rest.
                    const movedSet = new Set(movedIds.map(String));
                    state.heldSpools = state.heldSpools.filter(s => !movedSet.has(String(s.id)));
                    movedSet.forEach(id => _markAssignedOut(id)); // 21.6
                    // The spools the move handed to the scan buffer (`to_buffer`):
                    // a Swap's old spool (Swap option C: filed back where it sat
                    // before the slot; this page used to push it itself while the
                    // server left it in the box with no slot) and a same-slot
                    // swap's spool off the head. One render, one save.
                    window.takeIntoBuffer(res, { render: false });
                    renderBuffer();
                    if (document.getElementById('manage-loc-id').value === tid) refreshManageView(tid);
                    // Dispatch the canonical "something moved" event instead of
                    // calling fetchLocations directly — its listeners refresh
                    // locations (inv_core) + printer status (inv_printer_status) +
                    // the buffer cards' data immediately (no 5s pulse wait). Mirrors
                    // the scan-assignment path above.
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                    end(landed, res);
                } else {
                    showToast(res.msg || 'Assign failed', 'error', 7000);
                    // A spool the move had already handed to the buffer (a head's
                    // swapped-out spool before Smart Load stopped) is in hand.
                    window.takeIntoBuffer(res);
                    end('failed', res);
                }
            })
            .catch((e) => { setProcessing(false); console.error(e); end(landed || 'failed'); });
    };
    post(first, {
        heads: first.confirmed_toolheads,
        pickedSlot: pickedSlot != null ? String(pickedSlot) : null,
        expectedFeed,
    });
};

// Group 40.2 (Derek's D2.1; Q1 answered 2026-10-13: loop) — a multi-slot box's
// own label scanned with spools in the buffer opens the slot picker (40.1) once
// per spool that was in the buffer when the label was scanned, top first: each
// slot's spool and feed, the ⭐, and a tap, a number, Enter or the slot's own
// label picks. It used to file the whole buffer with no slot (one spool: a slot
// the engine chose unseen). Iterating the scan-time list means a spool a Swap
// hands back is never offered again, so the loop always ends. Each pick is one
// move through /api/smart_move, with its own questions (40.3). Escape, ✕ or
// CMD:CANCEL stops the loop and the rest stay in the buffer; Cancel on a
// question steps back to this spool's picker; a failure ends the loop after its
// 7 s error (Claude's call 24). Several spools end with a summary.
// Group 40.5 (Derek's D3): a head picked in the Printer picker that holds a
// spool asks first, naming what happens to it ("Load #42 onto XL-3? XL-3 holds
// #99 (from LR-MDB-1 slot 3). Loading #42 sends #99 back to LR-MDB-1 slot 3."):
// Load it instead / Cancel, with no store (a head is not storage); Enter
// cancels. An empty head asks nothing here (a printing printer is the server's
// question, as on every door). Resolves true to load, false to step back.
// How a question names the spool: "#42", or "the new spool" for the wizard's
// create (Group 40.7: the spool doesn't exist yet when its picker opens).
const _spoolWord = (sid) => (sid != null && String(sid) !== '' ? `#${sid}` : 'the new spool');

// The spools the Printer picker showed on a picked head: what its question names
// and, as `expected_residents`, what the move sends (Group 51.6).
const _headResidents = (pick) => ((Array.isArray(pick.residents) && pick.residents.length) ? pick.residents
    : (pick.resident ? [pick.resident] : []));

const _confirmHeadPick = (pick, sid, host) => {
    const who = _spoolWord(sid);
    const residents = _headResidents(pick);
    if (!residents.length) return Promise.resolve(true);
    const and = (list) => (list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`);
    const runs = and(residents.map(r => `#${r.id}` + (r.from ? ` (from ${r.from})` : '')));
    const goes = and(residents.map(r => `#${r.id} ` + (r.from ? `back to ${r.from}` : (r.goes || 'to Unassigned'))));
    return new Promise((resolve) => window.confirmActivePrint({
        title: `Load ${who} onto ${pick.head}?`,
        msg: `${pick.head} holds ${runs}. Loading ${who} sends ${goes}.`,
        host, printing: false, loadLabel: 'Load it instead',
        ids: { overlay: 'fcc-head-pick-confirm' },
        onConfirm: () => resolve(true),
        onCancel: () => resolve(false),
    }));
};

// Group 40.5 (Derek's D3, item G): "Record it as coming from…" for a spool put
// on a head from no box (Unassigned, or another head): the box slots that feed
// the head, the free ones choosable and the held ones shown with their spool,
// plus No box. Pre-selected only when exactly one slot is free (D3); with
// several, No box has the focus, so Enter never guesses. A feed slot's label
// scanned picks it; CMD:CANCEL steps back. Asked only when there is something to
// choose. Resolves {box, slot} | '' (No box: also when no slot is free) |
// undefined (not asked: the spool arrives from somewhere, which stays its
// trail) | null (Cancel: back to the picker) | false (its host closed: stop).
const _askRecordSource = (pick, sid, host) => {
    const from = String(pick.spool_location || '').trim().toUpperCase();
    if (from && from === String(pick.head || '').toUpperCase()) return Promise.resolve(undefined);
    // Head to head, a spool whose own single-slot box is attached to the head it
    // is on keeps that box as its home (the engine's 42.6 follow; the model's
    // `spool_keeps_trail`), so an answer here would change nothing (Group 40
    // review, BD-3: it was asked, then silently not used).
    if (pick.spool_keeps_trail) return Promise.resolve(undefined);
    const fromRow = (state.allLocations || []).find(l => String(l.LocationID || '').toUpperCase() === from);
    const headTypes = ['Tool Head', 'MMU Slot', 'No MMU Direct Load', 'Printer'];
    if (from && !(fromRow && headTypes.includes(fromRow.Type))) return Promise.resolve(undefined);
    const feeds = (Array.isArray(pick.feeds) ? pick.feeds : []).filter(f => f && f.box);
    const free = feeds.filter(f => f.free);
    if (!free.length) return Promise.resolve('');
    const esc = window.escHtml || ((s) => String(s == null ? '' : s));
    const head = String(pick.head || '');
    const pre = free.length === 1 ? free[0] : null;
    const who = _spoolWord(sid);
    const Who = who.charAt(0).toUpperCase() + who.slice(1);
    return new Promise((resolve) => {
        let settled = false;
        let handle = null;
        let qr = null;
        let question = null;
        let statusTimer = null;
        let hostOff = null;
        const finish = (value) => {
            if (settled) return;
            settled = true;
            if (hostOff) { try { hostOff(); } catch (_) { /* noop */ } hostOff = null; }
            if (qr) { try { qr.cleanup(); } catch (_) { /* noop */ } qr = null; }
            if (handle) { try { handle.cleanup(); } catch (_) { /* noop */ } handle = null; }
            const open = (window._fccOpenMoveQuestions || []).filter(q => q !== question);
            window._fccOpenMoveQuestions = open;
            if (window._fccOpenMoveQuestion === question) window._fccOpenMoveQuestion = open.length ? open[open.length - 1] : null;
            clearTimeout(statusTimer);
            resolve(value);
        };
        const optBtns = feeds.map((f, i) => f.free
            ? `<button type="button" class="btn btn-sm btn-info fcc-rs-opt" data-rs-i="${i}">${esc(`${f.box} slot ${f.slot}`)}<small style="display:block;font-weight:400;">free</small></button>`
            : `<button type="button" class="btn btn-sm btn-outline-secondary fcc-rs-opt" data-rs-i="${i}" disabled aria-disabled="true">${esc(`${f.box} slot ${f.slot}`)}<small style="display:block;font-weight:400;">holds #${esc(f.claimed_by)}</small></button>`).join('');
        handle = window.mountOverlay({
            id: 'fcc-record-source',
            tier: 'confirm',
            host: host || undefined,
            onEscape: () => finish(null),
            content: `
                <div class="fcc-rs-panel" style="background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px; padding:18px 22px; max-width:38.75rem; text-align:center;">
                    <div class="fcc-rs-title" style="font-size:1.15em; font-weight:bold; margin-bottom:6px;">🔗 Record ${esc(who)} as coming from…</div>
                    <div class="fcc-rs-msg" style="color:#ffc; margin-bottom:12px; text-align:left;">${esc(Who)} isn't coming from a box. Which slot feeding ${esc(head)} is its home? Return and eject send it back there.</div>
                    <div class="fcc-rs-status" role="alert" style="display:none; margin-bottom:10px; padding:6px 10px; border-radius:6px; background:#4a3200; color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; text-align:left;"></div>
                    <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
                        ${optBtns}
                        <button type="button" class="btn btn-sm btn-secondary fcc-rs-none">No box</button>
                        <button type="button" class="btn btn-sm btn-dark fcc-rs-cancel">Cancel</button>
                    </div>
                    <div class="fcc-rs-hint" style="font-size:var(--fcc-fs-small); color:#ccc; margin-top:8px;">←/→ move · Enter chooses · scan a slot's label to choose it · Esc goes back</div>
                </div>`,
            initialFocus: pre ? `.fcc-rs-opt[data-rs-i="${feeds.indexOf(pre)}"]` : '.fcc-rs-none',
        });
        // The host closing settles the question too (Group 40 review, BD-1), as
        // it does confirmActivePrint's: mountOverlay only removes the DOM, which
        // left this promise, its QR session and the picker loop's lock waiting
        // until a reload. `false` stops the flow: no picker over a closed modal.
        if (host && typeof host.addEventListener === 'function') {
            const onHostGone = () => finish(false);
            host.addEventListener('hidden.bs.modal', onHostGone);
            host.addEventListener('hidden.bs.offcanvas', onHostGone);
            hostOff = () => {
                host.removeEventListener('hidden.bs.modal', onHostGone);
                host.removeEventListener('hidden.bs.offcanvas', onHostGone);
            };
        }
        const ov = handle.element;
        const flash = (text) => {
            const line = ov.querySelector('.fcc-rs-status');
            if (!line) return;
            line.textContent = text;
            line.style.display = 'block';
            clearTimeout(statusTimer);
            statusTimer = setTimeout(() => { line.style.display = 'none'; }, 7000);
        };
        const choose = (f) => finish({ box: String(f.box).toUpperCase(), slot: String(f.slot) });
        feeds.forEach((f, i) => {
            if (!f.free) return;
            const b = ov.querySelector(`.fcc-rs-opt[data-rs-i="${i}"]`);
            if (b) b.onclick = () => choose(f);
        });
        const noneBtn = ov.querySelector('.fcc-rs-none');
        const cancelBtn = ov.querySelector('.fcc-rs-cancel');
        noneBtn.onclick = () => finish('');
        cancelBtn.onclick = () => finish(null);
        ov.addEventListener('keydown', (e) => {
            const order = Array.from(ov.querySelectorAll('.fcc-rs-opt:not([disabled]), .fcc-rs-none, .fcc-rs-cancel'));
            if (e.key === 'Enter') {
                // A scan's Enter is the scan's (Group 40 review, BD-2): a slower
                // scanner's slot label still in the scan buffer used to answer the
                // focused button (No box, or the pre-selected slot) instead of
                // reaching processScan, which picks the scanned slot.
                if (window.enterIsAScan ? window.enterIsAScan() : (window.isScanInFlight && window.isScanInFlight())) return;
                const ae = document.activeElement;
                if (order.includes(ae)) { e.preventDefault(); e.stopPropagation(); ae.click(); }
                return;
            }
            if (e.key === 'Tab' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                const back = e.key === 'ArrowLeft' || (e.key === 'Tab' && e.shiftKey);
                const idx = order.indexOf(document.activeElement);
                const next = idx === -1 ? 0 : (idx + (back ? order.length - 1 : 1)) % order.length;
                e.preventDefault(); e.stopPropagation();
                order[next].focus();
            }
        }, true);
        if (window.attachConfirmQRs) {
            const panel = ov.querySelector('.fcc-rs-panel') || handle.panel;
            // With a slot pre-selected, No box gets its own code (Group 40
            // review, BD-6): a scan-only user could pick only that slot or Back.
            // Each code takes its button's colour (2026-10-21): the slot is
            // cyan (btn-info), No box grey (btn-secondary), Cancel dark (btn-dark).
            qr = window.attachConfirmQRs({
                host: panel,
                onConfirm: pre ? () => choose(pre) : () => finish(''),
                onStore: pre ? () => finish('') : undefined,
                onCancel: () => finish(null),
                confirmLabel: pre ? `Scan: ${pre.box} slot ${pre.slot}` : 'Scan: No box',
                storeLabel: 'Scan: No box',
                cancelLabel: 'Scan to go Back', theme: 'info',
                confirmTone: pre ? 'info' : 'secondary', storeTone: 'secondary', cancelTone: 'dark',
            });
        }
        // Scans are held off while it is open (processScan); a feed slot's label
        // picks that slot.
        question = {
            title: `Record ${who} as coming from…`,
            element: ov,
            hint: 'Answer the question on screen first: pick a slot (or scan its label), No box, or Cancel',
            cancel: () => finish(null),
            flash,
            route: (text) => {
                const m = /^LOC:(.+?):SLOT:(\d+)$/.exec(String(text || '').trim().toUpperCase());
                if (!m) return false;
                const f = feeds.find(x => String(x.box).toUpperCase() === m[1].trim() && String(x.slot) === String(parseInt(m[2], 10)));
                if (!f) return false;
                if (!f.free) {
                    flash(`${f.box} slot ${f.slot} holds #${f.claimed_by}: pick a free slot, No box, or Cancel`);
                    return true;
                }
                choose(f);
                return true;
            },
        };
        window._fccOpenMoveQuestions = (window._fccOpenMoveQuestions || []).concat([question]);
        window._fccOpenMoveQuestion = question;
    });
};

// What a pick becomes (Group 40.4 / 40.5): a placement the door sends,
// {location, slot?, picked_slot?, expected_feed?, auto_deploy?, swap?,
//  displaced?, noStore?, record_source?, label, short}; null to step back to
// the picker (a question was cancelled); false to stop.
const _placementFor = async (pick, sid, host, loc) => {
    if (pick.kind === 'slot' || pick.kind === 'pool') {
        const send = pick.send || (pick.free ? { picked_slot: pick.slot } : { slot: pick.slot });
        const p = { location: pick.box, label: `${pick.box} slot ${pick.slot}`,
            short: String(pick.box).toUpperCase() === String(loc).toUpperCase() ? `slot ${pick.slot}` : `${pick.box} slot ${pick.slot}`,
            expected_feed: pick.expected_feed != null ? pick.expected_feed : '' };
        if (send.slot != null) p.slot = send.slot;
        if (send.picked_slot != null) p.picked_slot = send.picked_slot;
        if (send.auto_deploy === false) p.auto_deploy = false;
        if (pick.swap) { p.swap = true; p.displaced = pick.displaced || null; }
        if (pick.store_ok === false) p.noStore = true;
        // Group 51.7: Swap / Overwrite named the slot's stored spool; another one
        // there by the time the move lands is refused, never unseated unseen.
        if ((pick.choice === 'swap' || pick.choice === 'overwrite') && pick.occupant && pick.occupant.id != null) {
            p.expected_occupant = pick.occupant.id;
        }
        return p;
    }
    if (pick.kind === 'head') {
        if (!(await _confirmHeadPick(pick, sid, host))) return null;
        const rec = await _askRecordSource(pick, sid, host);
        if (rec === null) return null;
        if (rec === false) return false;
        const p = { location: pick.head, label: pick.head, short: pick.head };
        if (rec !== undefined) p.record_source = rec;
        // Group 51.6: what the picker showed on the head ([] = empty). A spool
        // loaded there meanwhile is refused, not unloaded unasked.
        p.expected_residents = _headResidents(pick).map(r => r.id);
        return p;
    }
    return false;   // a pick these doors can't place (a return-mode "No slot"): stop
};

// Group 40.4 / 40.5 (Derek's D2.4, D3) — place ONE spool through a picker: a
// multi-slot Dryer Box opens the box picker, a Printer row that isn't its own
// toolhead the Printer picker (a head, or a Printer Pool slot). Every door that
// names such a row uses it: its label scanned with a buffer, the Location
// Manager's DEPOSIT card, Force Location. `send(placement, done)` performs the
// door's own request and calls done({outcome: 'moved' | 'cancelled' |
// 'failed', res}). Cancel on any question steps back to this spool's picker
// (Claude's call 24); Escape there ends it. Resolves {outcome: 'moved' |
// 'failed' | 'stopped', placement}. Its host closing ends it too (Group 40
// review, BD-1): a question that stepped back re-opened the picker over a modal
// that had gone.
const _placeOne = async ({ loc, sid, host = null, step = '', send }) => {
    const shown = (el) => !!(el && el.classList && el.classList.contains('show'));
    const hostWasShown = shown(host);
    for (;;) {
        if (hostWasShown && !shown(host)) return { outcome: 'stopped', placement: null };
        const pick = await window.openSlotPicker({ location: loc, spool: sid, host, step });
        if (!pick) return { outcome: 'stopped', placement: null };
        const placement = await _placementFor(pick, sid, host, loc);
        if (placement === false) return { outcome: 'stopped', placement: null };
        if (!placement) continue;
        const out = await new Promise((resolve) => {
            try { send(placement, resolve); } catch (e) { console.error(e); resolve({ outcome: 'failed' }); }
        });
        if (out && out.outcome === 'cancelled') continue;
        return Object.assign({ outcome: 'failed' }, out || {}, { placement });
    }
};
window.placeOneWithPicker = _placeOne;

let _pickerLoop = null;
// `ids` (Group 40.5): the spools to place (the DEPOSIT card's one), else the
// whole buffer as it is now.
const _placeBufferWithPicker = async (box, ids = null) => {
    if (_pickerLoop) {
        const why = `Still placing your buffer into ${_pickerLoop.box}: finish or cancel that first`;
        showToast(why, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ LOC:${box} ignored: ${why}`, 'WARNING');
        return;
    }
    const queue = (Array.isArray(ids) && ids.length ? ids : state.heldSpools.map(s => s.id)).map(id => ({ id }));
    const loop = _pickerLoop = { box, placed: [], stop: '' };
    const manage = document.getElementById('manageModal');
    const host = manage && manage.classList && manage.classList.contains('show') ? manage : null;
    try {
        for (let i = 0; i < queue.length && !loop.stop; i++) {
            const sid = queue[i].id;
            // It left the buffer meanwhile (dropped, or placed some other way).
            if (!state.heldSpools.some(s => String(s.id) === String(sid))) continue;
            const out = await _placeOne({
                loc: box, sid, host, step: queue.length > 1 ? `${i + 1} of ${queue.length}` : '',
                send: (pl, done) => performContextAssign(pl.location, pl.slot != null ? pl.slot : null, [], [sid],
                    pl.picked_slot != null ? pl.picked_slot : null,
                    { expectedFeed: pl.expected_feed,
                      // Swap option C: the server files the old spool back and buffers it.
                      swapDisplaced: pl.swap ? (pl.displaced || { id: null }) : null,
                      // What the tile promised (Group 40.2 review): "stored here,
                      // not loaded back" is a store; a stale record's slot can't
                      // take a store, so its question offers none.
                      autoDeploy: pl.auto_deploy === false ? false : undefined,
                      noStore: !!pl.noStore,
                      // Group 40.5: where a spool put on a head came from.
                      recordSource: pl.record_source,
                      // Group 51.6 / 51.7: what the picker showed.
                      expectedResidents: pl.expected_residents,
                      expectedOccupant: pl.expected_occupant,
                      onOutcome: done }),
            });
            if (out.outcome === 'moved') { loop.placed.push({ id: sid, short: out.placement.short }); continue; }
            loop.stop = out.outcome === 'stopped' ? 'stopped' : 'failed';
        }
    } finally {
        _pickerLoop = null;
        _summarizePickerLoop(loop, queue);
    }
};

// What the loop did, when the moves' own toasts don't already say it: several
// spools, or one that was never placed because the picker was cancelled.
const _summarizePickerLoop = (loop, queue) => {
    const held = (id) => state.heldSpools.some(s => String(s.id) === String(id));
    const placedIds = new Set(loop.placed.map(p => String(p.id)));
    const left = queue.filter(q => !placedIds.has(String(q.id)) && held(q.id)).map(q => `#${q.id}`);
    const and = (list) => (list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`);
    if (queue.length < 2) {
        if (loop.stop === 'stopped' && !loop.placed.length && left.length) {
            showToast(`Nothing placed in ${loop.box}: ${left[0]} stays in your buffer`, 'info', 4000);
            if (window.logClientEvent) window.logClientEvent(
                `ℹ️ Slot picker for ${loop.box} closed — ${left[0]} stays in the buffer, nothing moved`, 'INFO');
        }
        return;
    }
    const placed = loop.placed.map(p => `#${p.id} → ${p.short}`);
    const parts = [];
    if (placed.length) parts.push(placed.join(', '));
    if (left.length) parts.push(`${and(left)} ${left.length === 1 ? 'stays' : 'stay'} in your buffer`);
    const after = loop.stop === 'failed' ? ' (stopped after an error)' : '';
    const text = `📦 ${loop.box}: ${parts.join('; ') || 'nothing placed'}${after}`;
    showToast(text, (left.length || loop.stop) ? 'info' : 'success', 6000);
    if (window.logClientEvent) window.logClientEvent(
        `${loop.stop === 'failed' ? '⚠️' : 'ℹ️'} Box picker for ${loop.box}: ${parts.join('; ') || 'nothing placed'}${after}`,
        loop.stop === 'failed' ? 'WARNING' : 'INFO');
};
window._placeBufferWithPicker = _placeBufferWithPicker;

// Group 41.4 — Undo Last Move. The first press asks the server, which answers
// the question naming the move it would reverse ("Undo: put #57 back in
// LR-MDB-1 slot 2 and #196 back on XL-2?") and writes nothing. The Yes quotes
// that record's number (refused if another move landed meanwhile) and the heads
// it called out as printing (the shared confirm), else the plain yes/no dialog
// (Claude's call 9). The toast says what really went back; a failure names the
// spool at 7 s; "Nothing to undo" is an info toast.
const triggerUndo = (opts = {}) => {
    const body = {};
    if (opts.confirm) { body.confirm = true; body.undo_id = opts.undoId; body.confirmed_toolheads = opts.heads || []; }
    fetch('/api/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(r => r.json())
        .then((res) => {
            if (res && res.requires_confirm) {
                const heads = window.unionConfirmHeads ? window.unionConfirmHeads(opts.heads || [], res) : [];
                const yes = () => triggerUndo({ confirm: true, undoId: res.undo_id, heads });
                if ((res.active_prints || []).length && window.confirmActivePrint) {
                    window.confirmActivePrint({ activePrints: res.active_prints, msg: res.msg, onConfirm: yes });
                } else {
                    requestConfirmation(res.msg, yes);
                }
                return;
            }
            // Group 40, the same-slot swap: a spool the undone move had handed
            // into the scan buffer is back on its head, so it leaves the buffer
            // on screen at once. The server already dropped it from its replica
            // (and put back any spool the undo returns to the buffer), so this
            // render saves nothing: loadBuffer below adopts the server's list,
            // which a local save would have overwritten.
            const unbuffered = new Set(((res && res.unbuffered) || []).map(String));
            if (unbuffered.size) {
                state.heldSpools = state.heldSpools.filter(s => !unbuffered.has(String(s.id)));
                unbuffered.forEach(id => _markAssignedOut(id));
                window.suppressBufferDirty = true;
                try { renderBuffer(); } finally { window.suppressBufferDirty = false; }
            }
            updateLogState(); loadBuffer(); if (window.fetchLocations) window.fetchLocations();
            if (res && res.success) showToast(res.msg || '↩️ Undone', 'success', 4000);
            else if (res && res.nothing) showToast(res.msg, 'info', 4000);
            else showToast((res && res.msg) || 'Undo failed', 'error', 7000);
        })
        .catch(() => showToast('Undo failed: no answer from the server', 'error', 7000));
};

const printLabel = (sid) => {
    showToast("🖨️ Requesting Label...");
    setProcessing(true);
    fetch('/api/print_label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: sid })
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (!res.success) { showToast(res.msg || "Print Failed", "error"); return; }
            if (res.method === 'csv') { showToast(res.msg, "success"); return; }
            if (res.method === 'browser') {
                const data = res.data;
                if (!data || !data.filament) { showToast("Invalid Data", "error"); return; }
                const fil = data.filament;
                const extra = fil.extra || {};
                const colorHex = fil.color_hex || '000000';
                const rgb = hexToRgb(colorHex);
                let typeStr = fil.material || "Unknown";
                try {
                    let attrs = (typeof extra.filament_attributes === 'string') ? JSON.parse(extra.filament_attributes) : extra.filament_attributes;
                    if (Array.isArray(attrs) && attrs.length > 0) typeStr = attrs.join(' ') + ' ' + typeStr;
                } catch (err) { }
                const qrEl = document.getElementById('print-qr');
                if (qrEl) {
                    qrEl.innerHTML = "";
                    new QRCode(qrEl, { text: `ID:${sid}`, width: 120, height: 120, correctLevel: QRCode.CorrectLevel.L });
                }
                document.getElementById('lbl-brand').innerText = fil.vendor ? fil.vendor.name : "Generic";
                document.getElementById('lbl-color').innerText = extra.original_color ? extra.original_color.replace(/"/g, '') : fil.name;
                document.getElementById('lbl-type').innerText = typeStr;
                document.getElementById('lbl-hex').innerText = colorHex.toUpperCase();
                document.getElementById('lbl-id').innerText = sid;
                document.getElementById('lbl-rgb').innerText = `${rgb.r},${rgb.g},${rgb.b}`;
                setTimeout(() => window.print(), 500);
            }
        })
        .catch(e => { setProcessing(false); console.error(e); showToast("Connection Error", "error"); });
};

// EXPOSE GLOBALLY FOR LOC MANAGER
window.printLabel = printLabel;
window.renderBuffer = renderBuffer;
window.prevBuffer = prevBuffer;
window.nextBuffer = nextBuffer;
window.removeBufferItem = removeBufferItem;

// Hook into the render function to trigger saves automatically
window.isBufferSyncing = false; // Mutex for sync

/* --- PERSISTENCE LAYER: BUFFER (V3 Polling) --- */
const persistBuffer = () => {
    fetch('/api/state/buffer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buffer: state.heldSpools })
    }).catch(e => console.warn("Buffer Save Failed", e));
};

const loadBuffer = () => {
    // L28 polling guard: bail if a previous tick is still in flight.
    // isBufferSyncing was already used to block persistBuffer uploads
    // during a sync; reusing it here also gates the next poll from
    // piling up on top of an in-flight one — under a slow backend,
    // unguarded 2s ticks were a major contributor to socket-buffer
    // exhaustion (net::ERR_NO_BUFFER_SPACE).
    if (window.isBufferSyncing) return;
    window.isBufferSyncing = true; // Block uploads
    fetch('/api/state/buffer')
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data)) {
                const currentStr = JSON.stringify(state.heldSpools);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    // Grace window: a user-driven mutation in the last 3s wins over the server payload.
                    // Without this, manual entries (and barcode scans) added during an in-flight sync
                    // get wiped before persistBuffer lands.
                    const localAge = Date.now() - (window.lastLocalBufferChange || 0);
                    if (localAge < 3000) {
                        console.log(`⏸️ Skipping server overwrite — local change ${localAge}ms ago`);
                        window.pendingPersist = true;
                    } else {
                        console.log("🔄 Syncing Buffer from Server...");
                        // 21.6: drop any spool this client just assigned out of
                        // the buffer — a stale server payload (lost persist or a
                        // second client's clobber) must not resurrect it.
                        const cleaned = _filterRecentlyAssignedOut(data);
                        const wasStale = cleaned.length !== data.length;
                        window.suppressBufferDirty = true;
                        state.heldSpools = cleaned;
                        if (window.renderBuffer) window.renderBuffer();
                        window.suppressBufferDirty = false;
                        // If we filtered resurrected spools, the server is behind
                        // us — re-assert the corrected buffer so it converges
                        // (recovers a dropped persist) instead of fighting us on
                        // every heartbeat.
                        if (wasStale) persistBuffer();
                        // [ALEX FIX] Trigger a proactive backfill sync since old DB state didn't track remaining_weight
                        setTimeout(liveRefreshBuffer, 500);
                    }
                }
            }
            window.isBufferSyncing = false; // Unblock
            if (window.pendingPersist) {
                window.pendingPersist = false;
                persistBuffer();
            }
        })
        .catch(e => {
            console.warn("Buffer Load Failed", e);
            window.isBufferSyncing = false;
            if (window.pendingPersist) {
                window.pendingPersist = false;
                persistBuffer();
            }
        });
};

// --- LIVE REFRESH POLLING ---
// L28 polling guard: see updateLogState for rationale.
let _liveRefreshInflight = false;
// L206: render path extracted so the bulk-pulse dispatcher can hand
// a spools_refresh payload (same {id: data} shape that /api/spools/refresh
// returns) directly into the diff/update loop without another fetch.
const _renderSpoolsRefreshPayload = (data) => {
    if (!data || typeof data !== 'object') return;
    let changed = false;
    state.heldSpools.forEach(s => {
        const fresh = data[s.id];
        if (!fresh) return;
        // Diff covers every field the buffer card actually renders. Pre-2026-04-28
        // this list excluded location / is_ghost / slot / deployed_to, so a backend-
        // driven location move (Location Manager, Quick-Swap, force-unassign,
        // auto-archive-on-empty) would correctly update `archived` and the weight,
        // but leave the location badge stale until the user navigated away and
        // back — root cause of buglist L24 / L40.
        if (fresh.display !== s.display ||
            fresh.color !== s.color ||
            fresh.color_direction !== s.color_direction ||
            fresh.remaining_weight !== s.remaining_weight ||
            !s.details ||
            fresh.archived !== s.archived ||
            fresh.location !== s.location ||
            fresh.is_ghost !== s.is_ghost ||
            fresh.slot !== s.slot ||
            fresh.deployed_to !== s.deployed_to) {
            s.display = fresh.display;
            s.color = fresh.color;
            s.color_direction = fresh.color_direction;
            s.remaining_weight = fresh.remaining_weight;
            s.details = fresh.details;
            s.archived = fresh.archived;
            s.location = fresh.location;
            s.is_ghost = fresh.is_ghost;
            s.slot = fresh.slot;
            s.deployed_to = fresh.deployed_to;
            changed = true;
        }
    });
    if (changed && window.renderBuffer) window.renderBuffer();
};
window._renderSpoolsRefreshPayload = _renderSpoolsRefreshPayload;

const liveRefreshBuffer = () => {
    if (!state.heldSpools || state.heldSpools.length === 0) return;
    if (_liveRefreshInflight) return;

    const spoolIds = state.heldSpools.map(s => s.id);

    _liveRefreshInflight = true;
    fetch('/api/spools/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spools: spoolIds })
    })
        .then(r => r.json())
        .then(_renderSpoolsRefreshPayload)
        .catch(e => console.warn("Live Refresh Buffer Failed", e))
        .finally(() => { _liveRefreshInflight = false; });
};
window.liveRefreshBuffer = liveRefreshBuffer;

// L206: the dashboard_pulse heartbeat already refreshes buffer cards via
// its spools_refresh section; skip the duplicate /api/spools/refresh fetch
// when this event came from that source. Other dispatchers (wizard save,
// weigh-out, details modal saves) still trigger a fresh fetch.
document.addEventListener('inventory:sync-pulse', (e) => {
    if (e && e.detail && e.detail.source === 'dashboard_pulse') return;
    liveRefreshBuffer();
});

// Buffer-latency fix (buglist 2026-06-02): a local "something moved" signal
// (scan-assign, context-assign, quick-swap, eject) should refresh the buffer
// cards' underlying data IMMEDIATELY instead of waiting up to a full adaptive-
// cadence window (5s / 15s / 30s) for the next dashboard pulse — Derek's
// "changes in data to something in the active buffer should display almost
// instantly". `liveRefreshBuffer` no-ops on an empty buffer and carries its own
// in-flight guard, so fanning it out on every locations-changed is cheap.
// Quick-Swap (inv_quickswap.js) and the scan-assign path already dispatch this
// event; performContextAssign + doEject now do too (they used to call
// fetchLocations directly without signalling the buffer).
document.addEventListener('inventory:locations-changed', () => liveRefreshBuffer());

// Heartbeat (Checks every 2 seconds)
setInterval(loadBuffer, 2000);

// Initial Load
document.addEventListener('DOMContentLoaded', loadBuffer);

window.addSpoolToBuffer = (id) => {
    // [ALEX FIX] Reuse the Scanner Logic! 
    // Instead of manually fetching and building the object, we just tell the 
    // scanner router that this ID was "scanned". This ensures consistent behavior 
    // and data formatting between physical scans and UI clicks.
    // Must prefix with ID: so the Python backend doesn't think it's a legacy barcode
    console.log(`📥 Simulating Scan for Spool #${id}`);
    processScan('ID:' + id.toString());
};

window.processScan = processScan;