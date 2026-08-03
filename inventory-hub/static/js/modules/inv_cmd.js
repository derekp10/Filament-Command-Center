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

window.updateBulkMoveVisuals = () => {
    const stage = state.bulkMoveActive ? (state.bulkMoveStage || 'awaiting_source') : 'idle';
    bulkMoveShapeshift.set(stage);
};

// Deck-button toggle — THREE-WAY (Phase 3). Committing is still only ever the
// explicit panel button or a CMD:DONE scan; the tile is never the destructive
// path (toggleAudit's rule). But "active → always cancel" made the tile lie
// twice over: it reads a green "COMMIT" at the preview stage, and the Hide
// button's tooltip promised the deck button as the way to REOPEN the panel —
// following which silently discarded a plan built from two deliberate scans.
//   idle                   → arm a session
//   active + panel HIDDEN  → reopen the panel (the promised affordance)
//   active + panel OPEN    → safe bail (cancel; nothing moved)
// NOTE on that third arm: while the panel IS open its mountOverlay backdrop
// covers the deck, so the arm is not reachable by mouse — in practice the tile
// reads as "reopen the hidden panel". It is kept because the branch is correct
// for any programmatic caller and for a future backdrop-less variant, but the
// user-facing bail-outs are the panel's ❌ Cancel and a CMD:CANCEL scan. Say
// that in the tooltip; do NOT advertise the tile as a cancel.
const toggleBulkMove = () => {
    if (state.bulkMoveActive) {
        const isOpen = typeof window.isBulkMovePanelOpen === 'function'
            && window.isBulkMovePanelOpen();
        if (!isOpen) {
            // `user: true` also clears the "I hid this" latch, so the panel is
            // allowed to auto-follow stage changes again.
            window.openBulkMovePanel({ user: true });
            return;
        }
        window.cancelBulkMove();
        return;
    }
    window.fetchT('/api/bulk_move_session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' }),
    }).then(r => r.json()).then((d) => {
        // Mirror inv_loc_mgr.js's triggerBulkMove: the backend REFUSES a start
        // during an audit, and refuses to silently replace an already-armed
        // session. Ignoring those flags flashed the panel open and shut with no
        // explanation, because applyBulkMoveSession faithfully painted the
        // unchanged (idle, or someone else's) session back.
        if (d && d.already_active) {
            requestConfirmation(
                d.msg || 'A bulk move is already armed. Replace it?',
                () => {
                    window.fetchT('/api/bulk_move_session', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'start', replace: true }),
                    }).then(r2 => r2.json()).then((d2) => {
                        window.applyBulkMoveSession(d2 && d2.session);
                        if (typeof window.openBulkMovePanel === 'function') window.openBulkMovePanel({ user: true });
                    }).catch(() => showToast("Couldn't start bulk move", "error", 7000));
                }
            );
            return;
        }
        if (!d || !d.success) {
            showToast((d && d.msg) || "Couldn't start bulk move", "error", 7000);
            return;
        }
        window.applyBulkMoveSession(d && d.session);
        // user: true — the deck button IS the user asking for the panel, so it
        // must beat a Hide latch left over from an earlier session.
        if (typeof window.openBulkMovePanel === 'function') window.openBulkMovePanel({ user: true });
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
window.commitBulkMove = (confirmActivePrint = false) => {
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
        body: JSON.stringify({ action: 'commit', confirm_active_print: !!confirmActivePrint }),
    }, 120000).then(r => r.json()).then((res) => {
        _done();
        if (res && res.require_confirm && res.confirm_type === 'active_print') {
            // Phase 3: the confirm lives IN the panel now. The old
            // requestConfirmation hop opened Bootstrap's #confirmModal at
            // z-index ~1100 — BEHIND this panel's overlay at 20000 — and set
            // state.activeModal='confirm', which then swallowed scans: the
            // active-print safety path was effectively unreachable. The backend
            // stores the require_confirm plan on the session, so re-syncing +
            // re-rendering surfaces the acknowledgement strip inline.
            window.applyBulkMoveSession(res && res.session);
            window.openBulkMovePanel({ user: true });
            if (typeof window.refreshBulkMoveSession === 'function') window.refreshBulkMoveSession();
            const ap = res.active_print || {};
            showToast(res.msg || `${ap.printer_name || 'A printer'} is ${ap.state || 'ACTIVE'} — confirm in the Bulk Move panel to continue.`,
                      "warning", 7000);
            return;
        }
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
        showToast(msg, failed ? "warning" : "success", failed ? 7000 : 4000);
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
    const _scanInFlight = () => {
        const st = (typeof state !== 'undefined') ? state : window.state;
        return !!(st && typeof st.scanBuffer === 'string' && st.scanBuffer.length > 0
            && st.scanStartTime && (Date.now() - st.scanStartTime) < 500);
    };
    document.addEventListener('keydown', (e) => {
        if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.key !== 'B' && e.key !== 'b') return;
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) return;
        if (_scanInFlight()) return;
        e.preventDefault();
        const st = (typeof state !== 'undefined') ? state : window.state;
        if (st && st.bulkMoveActive) {
            // Already armed → SHOW, never cancel.
            if (typeof window.openBulkMovePanel === 'function') window.openBulkMovePanel({ user: true });
            return;
        }
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
    // Active-print acknowledgement (the in-panel confirm). Keyed to the printer
    // + locations + the exact movable set it was given for, so re-targeting the
    // destination, a different printer going live, OR the spool list changing
    // RESETS it — an ack can never carry silently onto a plan the user didn't
    // read. Also cleared on close and on session end (see _resetAck): these are
    // module-scoped, and relying on the key comparison alone let a ticked box
    // survive Hide→reopen and even a whole session boundary.
    let _apAck = false;
    let _apAckKey = null;
    const _resetAck = () => { _apAck = false; _apAckKey = null; };
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
                    <div style="font-size:0.75rem; color:rgba(255,255,255,0.75);">${_esc(meta)}</div>
                </div>
                <div style="font-size:0.8rem;">${badge}</div>
            </div>`;
    };

    const _grid = (html) => `
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
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

        // --- active-print acknowledgement bookkeeping -----------------------
        // Recomputed per render; a changed key (different dest, different
        // printer, printer state moved on) drops a stale tick.
        const ap = (p && p.require_confirm) ? (p.active_print || {}) : null;
        // The movable ids are part of the key: WHAT will move is as much a part
        // of what the user acknowledged as which printer is running. Re-scanning
        // the same destination after the source contents changed produces the
        // same source|dest|printer|state tuple but a different spool list.
        const apKey = ap
            ? `${d.source_id}|${d.dest_id}|${ap.printer_name || ''}|${ap.state || ''}`
              + `|${((p && p.movable) || []).map(r => r.id).join(',')}`
            : null;
        // ...but NOT while a commit is running: the commit re-plans with
        // confirm_active_print=true, which drops require_confirm from the stored
        // preview, so a mid-flight repaint would silently un-tick the box the
        // user is currently waiting on.
        if (apKey !== _apAckKey && !_commitInflight) { _apAckKey = apKey; _apAck = false; }

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
            if (!p.ok && !p.require_confirm) {
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
                // The in-panel active-print confirm. This REPLACES the Phase-2
                // requestConfirmation hop, which opened #confirmModal (z ~1100)
                // behind this overlay (z 20000) and set state.activeModal so the
                // next scan was swallowed — the safety path was unreachable.
                const apStrip = ap ? `
                    <div id="fcc-bulkmove-ap" style="padding:10px; border:1px solid #fc0; background:#241f10;
                                border-radius:6px; color:#ffe08a; margin-bottom:10px;">
                        <div style="font-weight:bold; margin-bottom:4px;">⚠️ ACTIVE PRINT</div>
                        <div style="font-size:0.88rem; margin-bottom:8px;">${_esc(p.msg)}</div>
                        <label style="display:flex; align-items:center; gap:8px; cursor:pointer;
                                      font-size:0.88rem; margin:0;">
                            <input type="checkbox" id="fcc-bulkmove-ap-ack" ${_apAck ? 'checked' : ''}
                                   style="width:18px; height:18px; cursor:pointer;">
                            <span>I understand a print is active — move anyway</span>
                        </label>
                    </div>` : '';
                previewHtml = `
                    ${apStrip}
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

        // require_confirm (active print on the source) is COMMITTABLE — it just
        // needs the opt-in, now collected by the in-panel checkbox above.
        const hasPlan = stage === 'preview' && p && (p.ok || p.require_confirm)
            && (p.movable || []).length > 0;
        const needAck = !!ap;
        // _commitInflight: the backend re-plans and stores the result BEFORE the
        // multi-second execute, so the 2s poll repaints mid-commit with an
        // ok/committable plan and used to paint a live, enabled Commit button
        // over a move already in progress. Clicking it was refused by the
        // backend lock — but the client had already cleared the processing
        // overlay, unfreezing the whole dashboard mid-write.
        const canCommit = hasPlan && (!needAck || _apAck) && !_commitInflight;
        const commitLabel = _commitInflight
            ? '⏳ Committing…' : (needAck ? '⚠️ Commit Anyway' : '🔀 Commit Move');
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
                    <button id="fcc-bulkmove-commit" class="btn ${needAck ? 'btn-warning' : 'btn-success'} fw-bold w-100 mb-2"
                            ${canCommit ? '' : 'disabled'}>${commitLabel}</button>
                    <div id="fcc-bulkmove-qr-done" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color:rgba(255,255,255,0.75);">${needAck
                        ? 'Tick the box above first — scanning CMD:DONE won’t bypass it'
                        : 'Moves everything listed above'}</div>
                </div>
                <div style="flex:1; text-align:center;">
                    <button id="fcc-bulkmove-cancel" class="btn btn-outline-danger fw-bold w-100 mb-2">❌ Cancel</button>
                    <div id="fcc-bulkmove-qr-cancel" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color:rgba(255,255,255,0.75);">Bail without moving anything</div>
                </div>
            </div>`;

        // --- wire up (listeners, not inline onclick — the handlers need to
        //     close over needAck, and a spool/location value must never be
        //     interpolated into JS source inside an attribute).
        const commitBtn = body.querySelector('#fcc-bulkmove-commit');
        if (commitBtn) commitBtn.onclick = () => {
            if (commitBtn.disabled || _commitInflight) return;
            // Disable IMMEDIATELY — the fetch is O(N) seconds and the button
            // sits at z 20000, well above the z-9999 processing overlay, so it
            // stays physically clickable for the whole commit.
            commitBtn.disabled = true;
            commitBtn.innerText = '⏳ Committing…';
            window.commitBulkMove && window.commitBulkMove(needAck && _apAck);
        };
        const cancelBtn = body.querySelector('#fcc-bulkmove-cancel');
        if (cancelBtn) cancelBtn.onclick = () => { window.cancelBulkMove && window.cancelBulkMove(); };
        const ackBox = body.querySelector('#fcc-bulkmove-ap-ack');
        if (ackBox) ackBox.onchange = () => {
            _apAck = !!ackBox.checked;
            // Toggle in place rather than re-rendering: a full repaint would
            // destroy + regenerate both QR codes on every tick of the box.
            if (commitBtn) commitBtn.disabled = !(hasPlan && _apAck && !_commitInflight);
            // ⚠️ BLUR IS LOAD-BEARING, not cosmetic. This is the panel's only
            // <input>, and the global scan handler bails on the FIRST line —
            // `if (e.target.tagName === 'INPUT' ...) return;`
            // (templates/components/scripts.html) — so leaving it focused kills
            // the barcode scanner for every subsequent scan, including the
            // CMD:DONE / CMD:CANCEL the panel's own QR codes advertise. Ticking
            // the safety box must not disarm the scanner.
            ackBox.blur();
        };
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
                        border-radius:8px; padding:14px 16px;
                        width:min(820px,94vw); max-height:80vh; display:flex; flex-direction:column;">
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
        // The acknowledgement dies with the view. It is module-scoped, so
        // without this a ticked box survived Hide→reopen (and even a whole
        // session boundary) and the safety gate was pre-satisfied the instant
        // the panel reappeared.
        _resetAck();
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
                    <div style="font-size:0.75rem; color:rgba(255,255,255,0.75);">${_escapeHtml(weight)}${_escapeHtml(slot)}</div>
                </div>
                <div style="font-size:0.8rem;">${badge}</div>
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
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:6px; margin-bottom:12px;">
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
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:6px;">
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
                        border-radius:8px; padding:14px 16px;
                        width:min(820px,94vw); max-height:80vh; display:flex; flex-direction:column;">
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
        <div class="p-3" style="max-width:420px; background:#1e1e1e; color:#fff; border:1px solid #444; border-radius:8px;">
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

// --- SCAN ROUTER ---
const processScan = (text, source = 'keyboard') => {
    const upper = text.toUpperCase();
    // Active-dialog confirm-by-scan (registered via window.attachConfirmQRs).
    // Must run BEFORE the regular CMD: branches so a CMD:CONFIRM:<sid> scan
    // routes to the dialog's callback instead of hitting the backend or the
    // generic CMD-routes below. Returns true on a matched session — fall
    // through to the rest of the dispatch otherwise.
    if (window.routeConfirmScan && window.routeConfirmScan(text)) return;

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
    if (upper === 'CMD:EJECTALL') { triggerEjectAll(document.getElementById('manage-loc-id').value); return; }
    if (upper === 'CMD:UNDO') { triggerUndo(); return; }
    if (upper === 'CMD:CLEAR') { requestClearBuffer(); return; }
    if (upper === 'CMD:PREV') { prevBuffer(); return; }
    if (upper === 'CMD:NEXT') { nextBuffer(); return; }
    if (upper.startsWith('CMD:PRINT:')) { const parts = upper.split(':'); if (parts[2]) window.printLabel(parts[2]); return; }
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if (parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }

    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? confirmSafety(true) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? confirmAction(true) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if (upper.includes('CANCEL')) { closeModal('actionModal'); return; } if (upper.startsWith('CMD:MODAL:')) { closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }

    setProcessing(true);
    window.fetchT('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, source: source }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (res.type === 'command') {
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
                else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);
                else if (res.cmd === 'slot') handleSlotInteraction(res.value);
                else if (res.cmd === 'ejectall') triggerEjectAll(document.getElementById('manage-loc-id').value);
            } else if (res.type === 'assignment') {
                // Backend now handles the load when the buffer is non-empty.
                // We switch on `action` and let the backend's Activity Log
                // cover success/error cases; the frontend only handles the
                // no-buffer fallback (treat as a slot pickup).
                state.lastScannedLoc = null;
                if (res.action === 'assignment_done' || res.action === 'assignment_partial') {
                    // Backend already moved the spool and logged it. Mirror by
                    // dropping the moved id out of heldSpools so the UI matches.
                    const movedId = res.moved;
                    if (movedId != null) {
                        state.heldSpools = state.heldSpools.filter(s => s.id !== movedId);
                        _markAssignedOut(movedId); // 21.6 — don't let a stale pulse resurrect it
                        renderBuffer();
                    }
                    const extraMsg = res.action === 'assignment_partial'
                        ? ` (${res.remaining_buffer} still in buffer)`
                        : '';
                    showToast(
                        `✅ Loaded #${movedId} into ${res.location}:${res.slot}${extraMsg}`,
                        res.action === 'assignment_partial' ? 'info' : 'success',
                        res.action === 'assignment_partial' ? 5000 : 4000
                    );
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
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
                } else {
                    // Unknown action code — shouldn't happen, but surface it.
                    showToast(`Unknown assignment result: ${res.action || 'none'}`, 'warning', 4000);
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Unknown assignment action from backend: ${res.action || 'none'}`,
                        'WARNING'
                    );
                }
            } else if (res.type === 'location') {
                if (!text.toUpperCase().startsWith('LOC:')) {
                    const msg = "⚠️ Legacy Location Label Scanned! Features may be limited. Print a new LOC: label when possible.";
                    showToast(msg, "warning", 3500);
                    fetch('/api/log_event', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg: "SCAN LOG: Legacy Location Barcode Scanned (" + text + ")", level: "WARNING"}) });
                }
                if (state.lastScannedLoc === res.id) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
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
                if ((!locData || parseInt(locData['Max Spools']) <= 1) && res.contents && res.contents.length > 0) {
                    const spool = res.contents[0];
                    state.heldSpools.unshift({ id: spool.id, display: spool.display, color: spool.color, color_direction: spool.color_direction, remaining_weight: spool.remaining_weight, details: spool.details, archived: spool.archived, location: spool.location, is_ghost: spool.is_ghost, slot: spool.slot, deployed_to: spool.deployed_to });
                    renderBuffer();
                    showToast("⚡ Quick Pick: #" + spool.id);
                    state.lastScannedLoc = res.id;
                    return;
                }
                // Empty-location scan (buglist: "if a legacy barcode has no spools
                // attached, warn + offer to add"). A location/legacy label that
                // resolves to ZERO spools used to open the manager SILENTLY, leaving
                // the user wondering why nothing happened. Warn + log + open the
                // manager (which carries the Add-Spool affordance) — mirrors the
                // empty-SLOT path above. Scoped to the truly-empty case so it never
                // fires for quick-pick or buffer-assign flows.
                if (!res.contents || res.contents.length === 0) {
                    showToast(`📭 ${res.id} is empty — no spools here. Use the manager to add one.`, 'info', 6000);
                    if (window.logClientEvent) window.logClientEvent(
                        `📭 Location scan ${res.id} — no spools attached (opened manager)`,
                        'WARNING'
                    );
                    openManage(res.id); state.lastScannedLoc = res.id;
                    return;
                }
                openManage(res.id); state.lastScannedLoc = res.id;
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
        .catch((e) => { setProcessing(false); console.error(e); showToast("Scan Error", "error"); });
};

// Inline confirm overlay for "bulk assign into an active toolhead" — same
// visual pattern as Location Manager's _confirmActivePrintAssign (no nested
// Swal). Mounts into body so it floats above the scan UI and any open modal.
const _confirmActivePrintScan = ({ tid, slot, stateInfo, onConfirm }) => {
    // L122 fix: previously rolled its own overlay (createElement +
    // appendChild + document keydown). Migrated to window.mountOverlay()
    // so it inherits the canonical z-index ladder, focus guard, and
    // host-close discipline documented in CLAUDE.md "Project Conventions".
    // The previous implementation could end up blocked/hidden behind
    // certain modal stacks (the buglist L122 symptom: "confirm change
    // modal is being blocked, canceled, or hidden").
    const escapeHtml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const content = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ff8800; border-radius:8px; padding:20px 24px; max-width:460px; text-align:center;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ ${escapeHtml(stateInfo.printer_name)} is ${escapeHtml(stateInfo.state)}</div>
            <div style="color:#ffc; margin-bottom:14px;">
                Assigning the buffered spool(s) to <b>${escapeHtml(tid)}</b> will disrupt the active print. Continue anyway?
            </div>
            <div style="display:flex; gap:10px; justify-content:center;">
                <button id="fcc-aps-yes" class="btn btn-warning btn-sm" style="min-width:120px;">Continue Anyway</button>
                <button id="fcc-aps-no" class="btn btn-secondary btn-sm" style="min-width:120px;">Cancel</button>
            </div>
        </div>
    `;
    let handle = null;
    let qrSession = null;
    const cleanup = () => {
        if (handle) { try { handle.cleanup(); } catch (_) { /* noop */ } handle = null; }
        if (qrSession) { try { qrSession.cleanup(); } catch (_) { /* noop */ } qrSession = null; }
    };
    const proceed = () => { cleanup(); onConfirm(); };
    handle = window.mountOverlay({
        id: 'fcc-active-print-scan-overlay',
        content,
        tier: 'confirm',
        initialFocus: '#fcc-aps-yes',
        onEscape: cleanup,
    });
    const ov = handle.element;
    const yesBtn = ov.querySelector('#fcc-aps-yes');
    const noBtn = ov.querySelector('#fcc-aps-no');
    if (yesBtn) yesBtn.onclick = proceed;
    if (noBtn) noBtn.onclick = cleanup;
    // Keyboard contract (matches _confirmActivePrintAssign in inv_loc_mgr):
    // Enter activates the focused button (Yes/No); Tab cycles between
    // them; Escape always cancels (owned by mountOverlay's onEscape).
    const keyHandler = (e) => {
        if (e.key === 'Enter') {
            const active = document.activeElement;
            if (active === yesBtn) { e.preventDefault(); e.stopPropagation(); proceed(); }
            else if (active === noBtn) { e.preventDefault(); e.stopPropagation(); cleanup(); }
            return;
        }
        if (e.key === 'Tab') {
            const focusables = [yesBtn, noBtn].filter(Boolean);
            if (focusables.length === 0) return;
            const active = document.activeElement;
            const idx = focusables.indexOf(active);
            if (idx === -1) {
                e.preventDefault(); e.stopPropagation();
                focusables[e.shiftKey ? focusables.length - 1 : 0].focus();
                return;
            }
            if (e.shiftKey && idx === 0) {
                e.preventDefault(); e.stopPropagation();
                focusables[focusables.length - 1].focus();
            } else if (!e.shiftKey && idx === focusables.length - 1) {
                e.preventDefault(); e.stopPropagation();
                focusables[0].focus();
            }
        }
    };
    ov.addEventListener('keydown', keyHandler, true);
    if (window.attachConfirmQRs && ov) {
        qrSession = window.attachConfirmQRs({
            // Mount the QR row inside the dialog PANEL, not the overlay root.
            // The root is a centered flex-ROW (overlay_mount.js), so appending
            // the QR row there lays it out BESIDE the panel (the "QR codes on
            // the right" bug). handle.panel makes it stack below the buttons,
            // matching the Quick-Swap confirm.
            host: handle.panel,
            onConfirm: proceed,
            onCancel: cleanup,
            theme: 'warning',
        });
    }
};

const performContextAssign = (tid, slot = null, confirmActivePrint = false, spoolIdsOverride = null) => {
    setProcessing(true);
    // L124: callers can pass an explicit `spoolIdsOverride` subset (e.g. the
    // single topmost id when the target is a toolhead) so the rest of the
    // buffer stays untouched. Default = entire buffer (the legacy bulk-assign
    // behavior).
    const spoolIds = Array.isArray(spoolIdsOverride) && spoolIdsOverride.length
        ? spoolIdsOverride.slice()
        : state.heldSpools.map(s => s.id);
    const payload = {
        location: tid,
        spools: spoolIds,
        slot: slot,
        origin: 'buffer',
        confirm_active_print: confirmActivePrint,
    };

    fetch('/api/smart_move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            // Backend safety net: target is an active toolhead. Prompt the
            // user and retry with confirmActivePrint=true on approval.
            if (res.status === 'requires_confirm' && res.confirm_type === 'active_print') {
                _confirmActivePrintScan({
                    tid, slot,
                    stateInfo: res.active_print || { printer_name: tid, state: 'ACTIVE' },
                    onConfirm: () => performContextAssign(tid, slot, true, spoolIdsOverride),
                });
                return;
            }
            if (res.status === 'success') {
                const movedCount = spoolIds.length;
                showToast("Assigned " + movedCount + " item" + (movedCount === 1 ? '' : 's') + "!", "success");
                // Drop only the spools we actually moved; preserve the rest.
                const movedSet = new Set(spoolIds.map(String));
                state.heldSpools = state.heldSpools.filter(s => !movedSet.has(String(s.id)));
                movedSet.forEach(id => _markAssignedOut(id)); // 21.6
                renderBuffer();
                if (document.getElementById('manage-loc-id').value === tid) refreshManageView(tid);
                // Dispatch the canonical "something moved" event instead of
                // calling fetchLocations directly — its listeners refresh
                // locations (inv_core) + printer status (inv_printer_status) +
                // the buffer cards' data immediately (no 5s pulse wait). Mirrors
                // the scan-assignment path above.
                document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
            } else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

const triggerUndo = () => fetch('/api/undo', { method: 'POST' }).then(() => { updateLogState(); loadBuffer(); if(window.fetchLocations) window.fetchLocations(); });

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