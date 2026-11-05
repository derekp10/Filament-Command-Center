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

            // Never the printed label's ID: (inv_core.js fccSpoolCardQr): read off the
            // screen, it would count as a label read.
            state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, window.fccSpoolCardQr(s.id), 74));
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
// Armed during an audit, a mode would outlive it, and eject the first spool scanned
// after it. Turning one off is always fine.
const toggleDropMode = () => {
    if (!state.dropMode && window.auditPressRefused('CMD:DROP')) return;
    state.dropMode = !state.dropMode; state.ejectMode = false; updateDeckVisuals();
};
const toggleEjectMode = () => {
    if (!state.ejectMode && window.auditPressRefused('CMD:EJECT')) return;
    state.ejectMode = !state.ejectMode; state.dropMode = false; updateDeckVisuals();
};
window.resetCommandModes = () => { state.dropMode = false; state.ejectMode = false; updateDeckVisuals(); };

// --- AUDIT: the page's side (Group 58) --------------------------------------
// The session lives on the server. state.auditActive is what this page believes.
// toggleAudit believes a start from the press and takes it back on a refusal, so a
// double read or a second press only shows the panel. Everything else changes it
// from an answer (window.noteAuditEnded when one ended the audit, _auditScanAnswer
// when one proves it runs) or from the heartbeat (_syncAuditSignal, inv_core.js).
// Nothing flips it by negation: a toggle turned a double press into a new audit,
// and a failed Cancel into a press that did nothing.
const _auditClock = () => (window.fccPageClock ? window.fccPageClock() : Date.now());
const _auditChanged = () => { state.auditChangedAt = _auditClock(); };

// Done goes out in its turn, so it can sit in the scan queue behind scans already read
// (window.auditDone). Its buttons stay down until it has gone out and been answered,
// or a second press queues a second Done.
const _auditDoneQueued = () => (state.scanQueue || [])
    .some(q => String(q.text).trim().toUpperCase() === 'CMD:DONE');
const _auditButtonsFree = () => {
    if (!state.auditRequestsOut && !_auditDoneQueued() && window.auditPanelBusy) window.auditPanelBusy(false);
};

// This page's own requests on their way: a scan, a start, a Cancel (and the
// question's Yes). `delta`: +1 as one goes out, -1 once it is answered. While any
// is out, _syncAuditSignal won't call a "no audit" someone else's doing.
window.auditRequestOut = (delta) => {
    state.auditRequestsOut = Math.max(0, (state.auditRequestsOut || 0) + delta);
    _auditButtonsFree();
};

// scripts.html, after each queued scan: a queued Done that was dropped, or stopped
// short of the server, has no answer coming to free the buttons.
window.auditQueueMoved = _auditButtonsFree;

// A request of this page's own ended the audit (`audit_ended`: {id, why}): the
// server's word, so the panel closes now, and the heartbeat that follows stays
// quiet. `opts.quiet`: the caller has its own words for it.
const AUDIT_FINISHED_WORDS = 'Audit finished: its report is in the Activity Log.';
window.noteAuditEnded = (ended, opts = {}) => {
    if (!ended) return;
    state.auditEndedHere = ended.id;
    state.auditActive = false;
    state.lastAuditState = false;
    state.auditLocation = '';
    state.auditId = null;
    _auditChanged();
    window.updateAuditVisuals();
    if (!opts.quiet) {
        if (ended.why === 'cancel') showToast('Audit cancelled: nothing moved.', 'info', 4000);
        else showToast(AUDIT_FINISHED_WORDS, 'success', 4000);
    }
    if (typeof updateLogState === 'function') updateLogState(true);
};

// The deck tile and a CMD:AUDIT scan. Strictly non-destructive, as Bulk Move's
// (Decision 5, for Derek's veto; it replaces his 2026-05-16 one-click bail): during
// an audit it shows the panel and sends nothing, so a printed CMD:AUDIT label can't
// cancel an audit, and Hide has a way back. Cancelling is the panel's ❌ or a
// CMD:CANCEL scan, both labelled.
// Else it starts one and reads the answer. A refusal (a bulk move is armed) puts
// the page back, or the next press would have sent CMD:CANCEL at the bulk move.
const toggleAudit = () => {
    if (state.auditActive) { window.openAuditPanel(); return; }
    // Believed from here: a double read or a second press only shows the panel.
    state.auditActive = true;
    _auditChanged();
    const refused = (msg) => {
        state.auditActive = false;
        state.lastAuditState = false;
        _auditChanged();
        window.updateAuditVisuals();
        showToast(msg, 'error', 7000);
    };
    window.auditRequestOut(1);
    window.fetchT('/api/identify_scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'CMD:AUDIT' }),
    })
        .then(r => r.json())
        .then((res) => {
            if (!res || res.type === 'error') { refused((res && res.msg) || "Couldn't start the audit."); return; }
            state.lastAuditState = true;
            _auditChanged();
            window.updateAuditVisuals();
            if (typeof updateLogState === 'function') updateLogState(true);
        })
        .catch(() => refused("Couldn't start the audit: FCC didn't answer. Try again in a moment."))
        .finally(() => window.auditRequestOut(-1));
};

// A refusal, at the 7 s every refusal gets. The toast layer is under the panel, so
// the panel says it too.
const _auditSay = (msg, kind = 'error') => {
    showToast(msg, kind, 7000);
    if (window.auditPanelNotice) window.auditPanelNotice(msg);
};

// The panel's ❌: always CMD:CANCEL, whatever the page believes. Reads the answer,
// and a Cancel that didn't land says so with the audit still up.
let _auditCancelOut = false;
window.cancelAudit = () => {
    if (_auditCancelOut) return;
    _auditCancelOut = true;
    if (window.auditPanelBusy) window.auditPanelBusy(true);
    window.auditRequestOut(1);
    window.fetchT('/api/identify_scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'CMD:CANCEL' }),
    })
        .then(r => r.json())
        .then((res) => {
            if (res && res.audit_ended) { window.noteAuditEnded(res.audit_ended); return; }
            if (res && res.type === 'error') { _auditSay(res.msg || "Cancel didn't go through."); return; }
            // No audit took it, so none was running: the server says why.
            if (typeof updateLogState === 'function') updateLogState(true);
        })
        .catch(() => _auditSay("Cancel didn't go through: FCC didn't answer, so the audit is still running."))
        .finally(() => { _auditCancelOut = false; window.auditRequestOut(-1); });
};

// processScan stops a scan under a gating dialog without a word, so a press that
// goes through it says so here.
const _auditDialogBehind = () => {
    if (!state.activeModal) return false;
    _auditSay('A dialog behind this panel is still open: press Hide and answer it first.', 'warning');
    return true;
};

// The panel's Done: the scan path, so the button and all three QRs share one
// answer. Its source is 'keyboard': a press reads no label. In its turn behind any
// scan read before it: sent at once, the plan still had that spool as not scanned,
// the question listed it, and a Yes parked the spool in the person's hand.
window.auditDone = () => {
    if (_auditDialogBehind()) return;
    if (window.auditPanelBusy) window.auditPanelBusy(true);
    (window.sendInScanOrder || processScan)('CMD:DONE', 'keyboard');
    // Stopped short of the server (an open question says why itself): no answer comes.
    _auditButtonsFree();
};

// "Needs a label" on the last spool found (Group 58.2): the strip's button and key N.
// The scan path, as its QR is, in its turn behind any scan read before it: that
// scan's spool is the one the person means.
window.auditNeedLabel = () => {
    if (_auditDialogBehind()) return;
    (window.sendInScanOrder || processScan)('CMD:NEEDLABEL', 'keyboard');
};

// Commands the page runs itself never reach the server's audit gate, so it stops
// them here, with their reason. The toast sits under the panel, so the panel says
// it too. Hide exists so the page can be used during an audit: what opens a window
// or changes the buffer's view is refused only while the panel covers it. A mode
// armed here would outlive the audit, and eject the first spool scanned after it.
const _AUDIT_REFUSES = new Map([
    ['CMD:DROP', 'Drop mode waits until the audit is finished or cancelled.'],
    ['CMD:EJECT', 'Eject mode waits until the audit is finished or cancelled.'],
    ['CMD:EJECTALL', 'Eject All waits until the audit is finished or cancelled.'],
    ['CMD:CLEAR', 'The buffer is kept during an audit: finish or cancel it first.'],
    ['CMD:UNDO', 'Undo Last Move is off while an audit is running. Finish or cancel the audit first.'],
    ['CMD:BULKMOVE', 'A bulk move waits until the audit is finished or cancelled.'],
]);
const _AUDIT_PANEL_COVERS = ['CMD:LOCATIONS', 'CMD:WEIGH', 'CMD:PREV', 'CMD:NEXT'];
const _auditCommandRefusal = (upper) => {
    if (_AUDIT_REFUSES.has(upper)) return _AUDIT_REFUSES.get(upper);
    if (upper.startsWith('CMD:TRASH:')) return 'Eject waits until the audit is finished or cancelled.';
    const covered = _AUDIT_PANEL_COVERS.includes(upper) || upper.startsWith('CMD:PRINT:');
    if (covered && window.isAuditPanelOpen && window.isAuditPanelOpen()) {
        return 'The audit panel is on top: press Hide, then scan that again.';
    }
    return '';
};

// A press that does what `cmd` does, and is refused with its words during an audit: a
// deck tile, and the Location Manager's pickup (the buffer is kept during an audit, so
// a press must not count as a find). True when it was refused.
window.auditPressRefused = (cmd) => {
    if (!state.auditActive) return false;
    _auditSay(_AUDIT_REFUSES.get(cmd), 'warning');
    return true;
};

// A scan read during an audit never runs as a scan after that audit (Group 58
// review). The dim holds a scan read during the park, behind a Done or behind the
// scan a Cancel overtook, and the queue sent it on once the audit was over: a location
// label filed the whole buffer there, a slot label loaded it, and an ID: label cleared
// a reprint flag. `q`: a queued scan, stamped `auditOf` as it was read (scripts.html).
// True when that audit has gone, and the scan stops here. CMD:AUDIT goes on: it means
// the next audit.
// A scanner's second read of the scan read just before it (the same text within
// LOC_REPEAT_MS, processScan's double-read window) is no new scan, and is dropped with an
// INFO line only (review 3, R3-2): the first read of Done's QR, or of the question's "Scan to
// Park", ended the audit, and its second read, queued while the first was answered, was
// called a scan the audit outlived ("… CMD:DONE did nothing. Scan it again if you meant
// it."), on the report window that first read had just opened, and with the question's
// session id in it.
window.auditScanOutlived = (q) => {
    const text = String(q.text).trim();
    if (!q.auditOf || text.toUpperCase() === 'CMD:AUDIT') return false;
    const another = q.auditOf !== true && state.auditId != null && q.auditOf !== state.auditId;
    if (state.auditActive && !another) return false;
    const last = _lastScanRead;
    const at = q.capturedAt || Date.now();
    _lastScanRead = { text: text.toUpperCase(), at };
    if (last && last.text === text.toUpperCase() && Math.abs(at - last.at) < LOC_REPEAT_MS) {
        const escLog = window.escHtml || ((x) => x);
        if (window.logClientEvent) window.logClientEvent(
            `ℹ️ Scan "${escLog(text)}" ignored: the same label was read twice within ${LOC_REPEAT_MS / 1000} s`, 'INFO');
        return true;
    }
    const msg = `The audit has ended, so ${text} did nothing. Scan it again if you meant it.`;
    _auditSay(msg, 'warning');
    if (window.logClientEvent) window.logClientEvent(`⚠️ ${window.escHtml ? window.escHtml(msg) : msg}`, 'WARNING');
    return true;
};

// What a scan the audit took answers. `sentAt`: when the scan went out.
const _auditScanAnswer = (res, sentAt) => {
    if (res.audit_ended) {
        // A Done that ended the audit with nothing to ask carries its report: the window
        // opens where the panel was (Derek, 2026-11-03), once the panel has gone. It says
        // what Done did, so it stands for the "Audit finished" toast, which peeked out
        // around a short report (toasts sit under the overlays; Derek's look of
        // 2026-11-04). A Cancel's carries none, and an idle end's isn't shown.
        const report = !!res.report && res.audit_ended.why === 'done' && !!window.openAuditReport;
        window.noteAuditEnded(res.audit_ended, { quiet: report });
        if (report && !window.openAuditReport(res.report, { after: true })) showToast(AUDIT_FINISHED_WORDS, 'success', 4000);
        return;
    }
    // The audit took it: Find a spool, over the panel, would hide what it did.
    if (window.closeAuditFindForScan) window.closeAuditFindForScan();
    // `warning`: found, but its label couldn't be checked (toasted by the caller).
    if (window.auditPanelNotice) window.auditPanelNotice(res.warning || '');
    if (res.said) showToast(res.said, res.said_type || 'success', 4000);
    // An audit took it, so one runs, whatever this page believed: a scan right
    // after a reload lands before the first heartbeat.
    if (!state.auditActive && window._syncAuditSignal) window._syncAuditSignal({ audit_active: true }, { sentAt });
    // Every scan outcome is owed a toast, and the panel that shows this one is hidden.
    // Asked after the line above, which can bring the panel up.
    if (res.heard && !(window.isAuditPanelOpen && window.isAuditPanelOpen())) showToast(res.heard, 'info', 4000);
    if (window.refreshAuditSession) window.refreshAuditSession();
};

// An answer no running audit gives: the audit this page believes in has gone.
const _AUDIT_NEVER_ANSWERS = ['location', 'spool', 'assignment', 'filament', 'prusament_matched', 'prusament_new',
    'audit_gone'];
const _noAuditAnswered = (res) => _AUDIT_NEVER_ANSWERS.includes(res.type)
    || (res.type === 'command' && res.cmd !== 'audit_scan');

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
// Audit slot was the reference (idle: CMD:AUDIT/"AUDIT"  <->  active:
// CMD:DONE/"FINISH"); since Derek's 2026-11-03 look its two states differ only
// in their lit look (see auditShapeshift). Bulk Move's slot below is the one that
// still changes its command. This factory lets a multi-state deck command
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

// Audit slot on the shapeshift helper. During an audit the tile keeps its AUDIT label
// and its CMD:AUDIT QR (Derek, 2026-11-03: "drop the finish swap"), lit purple
// (btn-audit-active / label-active-audit), and its click or scan only shows the panel
// (toggleAudit): only the panel ends an audit, its Done… and Cancel Audit with their
// own QRs. It used to read FINISH over CMD:DONE, a second Done a person could scan
// from across the room with the panel hidden. The onEnter hooks preserve 18.2
// Part B's visual audit panel: open it when the session is active, close it when it
// ends — additive to the Activity Log, not a replacement (Derek 2026-05-15: "I still
// like the idea of having the activity log reference"). NOTE: audit is deliberately
// NOT wired into resetCommandModes — an audit session must survive opening other
// modals, unlike the drop/eject danger modes. The static idle QR is still seeded
// once in scripts.html; the first updateAuditVisuals() call (from the backend poll
// or toggleAudit) paints the correct state.
const auditShapeshift = window.registerShapeshiftQR({
    slot: 'audit',
    size: 85,
    default: 'idle',
    states: {
        idle:   { cmd: "CMD:AUDIT", label: "AUDIT", btnClass: '',                 labelClass: '',                   onEnter: () => { if (typeof window.closeAuditPanel === 'function') window.closeAuditPanel(); } },
        active: { cmd: "CMD:AUDIT", label: "AUDIT", btnClass: 'btn-audit-active', labelClass: 'label-active-audit', onEnter: () => { if (typeof window.openAuditPanel  === 'function') window.openAuditPanel();  } },
    },
});

window.updateAuditVisuals = () => {
    auditShapeshift.set(state.auditActive ? 'active' : 'idle');
    window.updateAuditPill();
};

// The audit pill (Group 58), Bulk Move's: shown for exactly as long as an audit
// runs, and the always-visible way back to a hidden panel. A hidden audit still
// takes every scan, so it names the place. Apart from updateAuditVisuals because
// that one opens the panel, and a new place mustn't undo a Hide.
window.updateAuditPill = () => {
    const pill = document.getElementById('fcc-audit-pill');
    if (!pill) return;
    if (!state.auditActive) { pill.style.display = 'none'; return; }
    const txt = pill.querySelector('#fcc-audit-pill-text');
    if (txt) txt.innerText = `audit: ${state.auditLocation || 'scan a location'}`;
    pill.style.display = 'inline-flex';
    pill.style.alignItems = 'center';
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
    // three identical copy-pasted closures (2026-08-03 scan-path audit). A
    // scan still arriving, however slow the scanner (window.scanIsArriving;
    // Group 57 review, round 4: "LOC:LR-MDB-1" at 75 ms a key, with nothing
    // open, armed a bulk move on its 'B' and reached processScan as "-1"; the
    // 'B' comes after the label's ':', and keys a person left don't hold
    // Shift+B off, round 5).
    const _scanInFlight = () => !!(window.scanIsArriving ? window.scanIsArriving()
        : (window.isScanInFlight && window.isScanInFlight()));
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
// found/missing tiles tick as the user scans (the server draws them from the rows
// it stored at each scan, so a poll reads no Spoolman), and right after a scan
// (window.refreshAuditSession). Closes when the audit ends (CMD:DONE / CMD:CANCEL).
// Hide and Escape only hide it: the 🕵️ pill and the deck tile bring it back.
(function () {
    let _handle = null;
    let _pollTimer = null;
    // Never let slow ticks stack, but coalesce, as the bulk panel does: a plain
    // drop would swallow the "re-read right now" after a scan.
    let _pollInflight = false;
    let _pollPending = false;
    // Bumped on every close, so an answer still out can't draw on what follows.
    let _panelGen = 0;
    // Done or Cancel is on its way (window.auditPanelBusy).
    let _busy = false;
    let _busyFocus = null;
    // "undo that" is on its way.
    let _undoOut = false;
    // When "undo that" was last answered (_undoJustPressed), and which spool the strip
    // showed last (_render, for where the keyboard goes).
    let _undoAnsweredAt = 0;
    let _stripSpool = null;
    // The audit whose Last found box has held a spool: once one has, an empty box says
    // nothing is selected, not that nothing was found (_renderNoStrip).
    let _selectedIn = null;
    // When Done's question was last answered: see _shieldClick.
    let _questionClosedAt = 0;
    // A double click's second press (see _shieldPage and _shieldClick). `_press`: the last
    // primary pointer press, anywhere {at, x, y, slop}. `_panelPress`: the last one made
    // while the panel was up, and whether it landed on something over the panel (`cover`:
    // Done's question, the 🧺 list, the legacy picker, the ⌨️ list) or on a tile or the
    // Last found strip (`strip`), with the spool the strip showed then (`stripWas`) and the
    // tile's (`tile`). `_eatPress`: when the press now under way began, if it is the
    // second of a double click and must reach nothing on the panel.
    let _press = null;
    let _panelPress = null;
    let _eatPress = 0;
    // The press the panel (or what it put up) went or came under, armed by _shieldPage.
    let _pageShield = null;
    // When the press now under way began, if the page shield took it whole.
    let _pageEating = 0;
    // Back brought a hidden panel back: Done takes the keyboard once it exists.
    let _focusDoneNext = false;
    // What this panel put on top of itself, closed with it: no overlay outlives its
    // parent. Done's question (window.confirmActivePrint's handle), the Loose
    // spools list and Find a spool. mountOverlay's `host` only hears a Bootstrap
    // window closing.
    let _question = null;
    let _loose = null;
    let _find = null;
    // When Find last closed on a pick: the keyboard goes back to 🔎, and a double
    // Enter or Space on a row would open it again (_openFind).
    let _findPickedAt = 0;
    // The session the panel drew last: Find tags its rows from it.
    let _lastData = null;
    // The session this page read last, the panel up or hidden (every scan the audit takes
    // reads it again, window.refreshAuditSession): the legacy picker's tags.
    let _lastSession = null;
    // Watches the scrolling part's size for _fitDock while the panel is up.
    let _dockFit = null;
    // The dock's columns are drawn once per panel, at its first answer (_render).
    let _dockDrawn = false;
    // Each tile's QR (Derek, 2026-11-03, A1), drawn once and kept by its text: a scan
    // changes the panel's hash, and the body is drawn again. For one audit only.
    const _tileQrs = new Map();
    let _tileQrsAudit = null;
    // When the strip's 🖨️ was last pressed (B): a double press is one press.
    let _queuePressedAt = 0;
    // 2026-05-16 — every-2s flicker fix: hash-skip the body innerHTML
    // rewrite when the audit payload hasn't actually changed. Same pattern
    // as updateLogState's lastLogHash. Without this the tile grid + the
    // two QR codes got destroyed and re-created on every tick even when
    // no scan had landed; Derek saw the panel "redraw" every 2-3s.
    let _lastRenderHash = null;
    const _escapeHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const PRESS_TIMEOUT_MS = 20000;     // an undo reads and writes a spool
    const DOUBLE_PRESS_MS = 700;
    // How far a double click's second press can land from its first: a mouse stays within
    // a few pixels, a finger's second tap less so.
    const DOUBLE_PRESS_SLOP_PX = { mouse: 16, other: 40 };

    const _TILES = {
        found: { bg: '#0a2a0a', border: '#0f0', badge: '<span style="color:#0f0; font-weight:bold;">✅ scanned</span>' },
        missing: { bg: '#1a1a1a', border: '#555', badge: '<span style="color:rgba(255,255,255,0.7);">⬜ not scanned</span>' },
        extra: { bg: '#2a2410', border: '#fc0', badge: '<span style="color:#fc0; font-weight:bold;">⚠️ extra</span>' },
        trail: { bg: '#0a2230', border: '#0cf', badge: '<span style="color:#7fe8ff; font-weight:bold;">🔗 loaded</span>' },
    };

    // A spool's name as a tile and the strip show it. The server's rows already
    // start with "#57" (a bare id is its fallback).
    const _spoolName = (row) => {
        const text = String(row.display == null ? '' : row.display);
        return text.startsWith(`#${row.id}`) ? text : `#${row.id} ${text}`;
    };

    // What a tile says about a spool's label (Group 58.2). A missing status on a spool
    // nobody has reached yet says nothing: that is most spools, as on the search cards
    // (58.5). A found spool with a real label read and no status: the check failed.
    const _labelWords = (row, found) => {
        const words = [];
        if (found && !row.label_read) words.push('✅ found, no label read');
        if (row.label_status === true) words.push('🏷️ needs a label');
        else if (found && row.label_read && row.label_status === null) words.push('label status unknown');
        return words;
    };

    // A tile's QR (Derek, 2026-11-03, A1): scanning it finds the spool as a press does
    // (logic.resolve_scan's CMD:FOUND). Only once the page knows the audit's id: a QR
    // without it would name no audit. The id goes as the server wrote it, and the
    // server reads it in any case (a scanner set to upper case sends it so).
    const _tileQrText = (row) => (state.auditId ? `CMD:FOUND:${state.auditId}:${Number(row.id)}` : '');

    // The 🏷️ drawn for the dark round backing (Derek, 2026-11-04: "that same label icon not
    // centered in circle thing"): the emoji is drawn on a slant, its yellow body low-left and
    // its string up-right, and the Windows one's grey string hardly shows on the dark, so even
    // centred by its box it read as off. A tag in the emoji's warm yellow and orange with its
    // dark hole and an orange ring of string, pointing up-right as the emoji does, symmetric
    // about that diagonal, its body and ring balanced about the circle's middle: its box and
    // its weight within 0.05 of the frame's 32 units, the same on every system. The frame is
    // the whole circle (.fcc-ico-svg is as big as its backing); test_icon_on_dark_circle_js.py
    // measures it on the screen at 1x and 2x.
    // Only on the backing: every other 🏷️, and the words beside this one, stay emoji.
    const TAG_ICON = '<svg class="fcc-ico-svg" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        + '<g transform="rotate(-45 16 16)">'
        + '<path d="M9.8 11.6H19.4L23.4 16L19.4 20.4H9.8Q8.8 20.4 8.8 19.4V12.6Q8.8 11.6 9.8 11.6Z" '
        + 'fill="#FFC83D" stroke="#E57C00" stroke-width="1.6" stroke-linejoin="round"/>'
        + '<circle cx="19.9" cy="16" r="1.6" fill="#2B1A08"/>'
        + '<circle cx="23.5" cy="16" r="2.6" fill="none" stroke="#E57C00" stroke-width="1.6"/>'
        + '</g></svg>';

    // A found tile's own 🏷️ (Derek, 2026-11-03, (a): "A sounds good"): one tap marks that
    // spool as needing a label without making it the last found (POST
    // /api/audit/needs_label); the tile then says "needs a label" and its 🏷️ shows the
    // mark is this audit's (`flagged_here`); a tap on it again, DOUBLE_PRESS_MS or more
    // after the last, takes the mark back (/api/audit/needs_label_undo). A spool flagged
    // before the audit shows as flagged already, and a tap is answered so. Its own
    // button, beside the tile's in one cell, never inside it: a button holds no button.
    const _tagButton = (row) => {
        const id = Number(row.id);
        const say = (mark, words, pressed) => `<button type="button" class="fcc-audit-tile-tag" data-audit-tag="${id}"
                data-audit-tag-state="${mark}"${pressed === null ? '' : ` aria-pressed="${pressed}"`}
                aria-label="${_escapeHtml(words)}" title="${_escapeHtml(words)}">${mark === 'marked'
            ? `<span class="fcc-ico-on-light" aria-hidden="true">${TAG_ICON}</span>` : '<span aria-hidden="true">🏷️</span>'}</button>`;
        if (row.flagged_here) return say('marked', `#${id} is marked as needing a label: press again to take the mark back`, true);
        if (row.label_status === true) return say('flagged', `#${id} is already flagged for a new label`, null);
        return say('none', `Needs a label: mark #${id}, and leave the last found as it is`, false);
    };

    // Expected tiles are real buttons (window.personMayPress's rule, through the scan
    // accumulator): a press finds a spool with nothing to scan, and takes that back.
    // An Extra's tile is one too (A3): a press takes it back off the found lists, for a
    // spool scanned or picked here by mistake, since Done acts on the Extras. A press
    // never makes an Extra, and a loaded-from-here tile stays a plain tile. A found tile,
    // on the list or an Extra, has its own 🏷️ (_tagButton).
    // Laid out again on Derek's look of 2026-11-04 ("move some of the stuff on the sides to
    // the top and bottom, like the label buttons, and the scanned notifications. That would
    // give us a little more room for the full name. Id also say let it wrap too. but we'd have
    // to try and keep the box size consistant among all of them"): each tile is a cell in its
    // kind's colours (global.css .fcc-audit-tile-cell); the name takes the tile's width and
    // wraps, two lines at most (its whole name in its title); under the name and its grams,
    // a row says what the audit knows of the spool (.fcc-audit-tile-status), a found tile's
    // 🏷️ at its end. That row is no part of a found tile's press button, so a tap a little off
    // the 🏷️ presses nothing: a press there took the find back, and its label read with it.
    // A tile not yet found has no 🏷️, and its whole tile, its QR at its side, stays its press
    // button. The grids give every tile in a group one height (global.css .fcc-audit-grid).
    const _renderTile = (row, kind) => {
        const look = _TILES[kind];
        const id = Number(row.id);
        const swatchBg = (typeof window.makeSwatchHtml === 'function')
            ? window.makeSwatchHtml(row.color, row.color_direction, { size: 28, borderColor: '#444' })
            : `<span style="display:inline-block;width:28px;height:28px;background:#${row.color || '333'};border-radius:4px;"></span>`;
        const weight = row.remaining_weight != null ? `${Math.round(row.remaining_weight)}g` : '';
        const slot = row.slot ? ` (slot ${_escapeHtml(row.slot)})` : '';
        const name = _spoolName(row);
        // Where FCC has it: an Extra's filed place, a loaded spool's head.
        const where = !row.where ? ''
            : (kind === 'extra' ? `📍 ${row.where}` : (kind === 'trail' ? `🔗 on ${row.where}` : ''));
        const found = kind !== 'missing';
        const words = _labelWords(row, found);
        const badge = (kind === 'found' && !row.label_read) ? '' : look.badge;
        const pressable = kind === 'found' || kind === 'missing' || kind === 'extra';
        const tagged = kind === 'found' || kind === 'extra';
        // Only a tile not yet found: a QR never takes a find back.
        const qr = kind === 'missing' ? _tileQrText(row) : '';
        const title = kind === 'extra' ? 'Press if it isn\'t here after all: it comes off the Extras'
            : (found ? 'Press if it isn\'t here after all'
                : (qr ? 'Press, or scan its QR, if it\'s here with no label to scan' : 'Press if it\'s here with no label to scan'));
        const statusId = `fcc-audit-tile-status-${id}`;
        const status = `<span id="${statusId}" class="fcc-audit-tile-status">${badge ? `<span class="fcc-audit-tile-badge">${badge}</span>` : ''}`
            + `${words.map(w => `<span class="fcc-audit-tile-word">${_escapeHtml(w)}</span>`).join('')}</span>`;
        const text = `<span class="fcc-audit-tile-swatch">${swatchBg}</span>`
            + '<span class="fcc-audit-tile-text">'
            + `<span class="fcc-audit-tile-name" title="${_escapeHtml(name)}">${_escapeHtml(name)}</span>`
            + `<span class="fcc-audit-tile-detail">${_escapeHtml(weight)}${slot}</span>`
            + `${where ? `<span class="fcc-audit-tile-where">${_escapeHtml(where)}</span>` : ''}</span>`;
        const press = `type="button" class="fcc-audit-tile-box fcc-audit-tile" data-audit-tile="${id}"
               data-audit-found="${found ? 1 : 0}" aria-pressed="${found}" title="${_escapeHtml(title)}"`;
        const cell = (inner) => `<div class="fcc-audit-tile-cell" data-audit-kind="${kind}"
               style="--fcc-tile-bg:${look.bg}; --fcc-tile-border:${look.border};">${inner}</div>`;
        if (kind === 'missing') {
            return cell(`<button ${press}>${text}${status}`
                + `${qr ? `<span class="fcc-audit-tile-qr" aria-hidden="true" data-audit-qr="${_escapeHtml(qr)}"></span>` : ''}</button>`);
        }
        // The press button says the row's words (aria-describedby): they sit outside it.
        const top = pressable ? `<button ${press} aria-describedby="${statusId}">${text}</button>`
            : `<div class="fcc-audit-tile-box">${text}</div>`;
        return cell(`${top}${status}${tagged ? _tagButton(row) : ''}`);
    };

    // The QR codes the tiles hold, each drawn once (the shared library, as generateSafeQR
    // calls it) and moved into its tile at every redraw. qrcode.js puts its text in a
    // tooltip on the box it draws in, and the tile says what the QR does.
    const TILE_QR_PX = 72;
    const _tileQrNode = (text) => {
        let node = _tileQrs.get(text);
        if (node) return node;
        node = document.createElement('span');
        node.className = 'fcc-audit-tile-qr-code';
        try {
            new QRCode(node, { text, width: TILE_QR_PX, height: TILE_QR_PX, correctLevel: QRCode.CorrectLevel.L });
        } catch (e) { /* no QR library: the tile can still be pressed */ }
        node.removeAttribute('title');
        _tileQrs.set(text, node);
        return node;
    };
    const _placeTileQrs = (body) => {
        if (_tileQrsAudit !== state.auditId) { _tileQrs.clear(); _tileQrsAudit = state.auditId; }
        body.querySelectorAll('[data-audit-qr]').forEach((slot) => {
            slot.appendChild(_tileQrNode(slot.dataset.auditQr));
        });
    };

    // A spool found here that isn't on the list, in a sentence: its tile can be below
    // the fold or under this strip, and a toast is under the panel. Nothing for a
    // spool the list expected. An Extra Spoolman wouldn't answer for has `where`
    // saying so (logic.AUDIT_WHERE_UNREAD), and FCC "has it at" no such place.
    const WHERE_UNREAD = "couldn't read where FCC has it";
    const _stripFoundHere = (row) => {
        const tag = `#${row.id}`;
        const where = String(row.where == null ? '' : row.where);
        if (row.trail) return where ? `${tag} is loaded on ${where} from here` : `${tag} is loaded from here`;
        if (!row.rogue) return '';
        if (!where) return `Extra: ${tag}${_atDoneWords(row.at_done)}`;
        return where === WHERE_UNREAD ? `Extra: ${tag}: ${where}` : `Extra: FCC has ${tag} at ${where}${_atDoneWords(row.at_done)}`;
    };

    // What Done will do with an Extra (Derek's C6, 2026-11-03, for his look): the row's
    // `at_done`, worked out by Done's own rule when the spool was scanned, so a poll
    // reads nothing. `files` true: filed here; false: it stays, and why; null: a fresh
    // read at Done decides (a place that holds one spool), and the sentence says so. No
    // key, or null (Spoolman didn't answer at the scan): nothing is said of Done. A stay
    // that depends on a fresh read is said at Done, in its question, never here.
    const _atDoneWords = (at) => {
        if (!at || typeof at !== 'object') return '';
        const why = String(at.why == null ? '' : at.why).trim();
        if (at.files === true) return '; Done files it here';
        if (at.files === false && why) return `; it stays: ${why}`;
        if (at.files === null && why) return `; ${why}`;
        return '';
    };

    // What FCC knows about this spool's label.
    const _stripLabel = (row) => {
        const tag = `#${row.id}`;
        if (row.flagged_here) return `${tag} is marked: it needs a label`;
        if (row.label_status === true) return `${tag} is still flagged for a new label`;
        if (!row.label_read) return `No label was read for ${tag}`;
        if (row.label_status === null) return `${tag}'s label was read, but FCC couldn't confirm it`;
        return `${tag}'s label was read`;
    };

    // The Last found strip's line.
    const _stripLine = (row) => {
        const here = _stripFoundHere(row);
        return here ? `${here}. ${_stripLabel(row)}` : _stripLabel(row);
    };

    // Is this spool's label in the 🛒 print queue (inv_queue.js's, this browser's copy
    // of the shared one)? Read as the queue reads an id, a number or its text.
    const _inPrintQueue = (id) => Array.isArray(window.labelQueue)
        && window.labelQueue.some(q => q && (q.type || 'spool') === 'spool' && String(q.id) === String(id));

    // The strip's 🖨️ (Derek, 2026-11-03, B: "just in case I decide to do some updating
    // while I'm auditing the row"): for a spool whose label is flagged, before the audit
    // or in it, and for one already queued, which it says. No QR: printing happens at
    // the desk, and "Needs a label" already puts the spool on the 🏷️ Backlog. Not
    // `disabled` once queued, which would drop the keyboard: a press does nothing.
    const _queueButton = (row) => {
        const queued = _inPrintQueue(row.id);
        if (!queued && row.label_status !== true && !row.flagged_here) return '';
        return queued
            ? '<button type="button" id="fcc-audit-label-queue" class="btn btn-sm btn-outline-info fcc-audit-queue" aria-disabled="true"'
                + ` title="#${Number(row.id)}'s label is in the print queue">✓ In the print queue</button>`
            : '<button type="button" id="fcc-audit-label-queue" class="btn btn-sm btn-outline-info fcc-audit-queue"'
                + ` title="Queue #${Number(row.id)}'s label to print at the desk">🖨️ Add to print queue</button>`;
    };

    // The Last found box: the spool "Needs a label" acts on, in the dock under the
    // scrolling list (Derek, 2026-11-03, sample 1b: "the placement of useful buttons and
    // last found on the panel"), so its words and the dock's buttons and QRs are there
    // however far the tiles scroll, when the spool in the person's hand has no label
    // worth scanning. Its name wraps rather than being cut: a touch screen can't show a
    // title. "undo that" has no QR, so a double read of the mark's own QR can't toggle it.
    const _renderStrip = (row) => {
        if (!row) return '';
        const swatch = (typeof window.makeSwatchHtml === 'function')
            ? window.makeSwatchHtml(row.color, row.color_direction, { size: 28, borderColor: '#444' }) : '';
        const name = _escapeHtml(_spoolName(row));
        // "↩ Put back" (P7): not for a spool loaded from here, whose tile is no button.
        const id = Number(row.id);
        const putBack = row.trail ? '' : `<button type="button" id="fcc-audit-put-back" class="btn btn-sm btn-outline-light fcc-audit-put-back"
                    title="${_escapeHtml(row.rogue ? `Not here after all: take #${id} off the Extras`
                        : `A mistaken find: put #${id} back on the not-scanned list`)}">↩ Put back</button>`;
        return `
            <div id="fcc-audit-last-found" class="fcc-audit-strip">
                <div class="fcc-audit-strip-head"><span class="fcc-audit-strip-title">Last found</span>${putBack}</div>
                <div class="fcc-audit-strip-spool">${swatch}<span class="fcc-audit-strip-name">${name}</span></div>
                <div class="fcc-audit-strip-status" role="status">
                    <span>${_escapeHtml(_stripLine(row))}</span>
                    ${row.flagged_here ? '<button type="button" id="fcc-audit-label-undo" class="btn btn-sm btn-outline-light">undo that</button>' : ''}
                    ${_queueButton(row)}
                </div>
            </div>
        `;
    };

    // The box with no spool in it: nothing found yet, or nothing selected (the last find
    // taken back, by "↩ Put back" or its tile, while others stay found, or once this audit
    // has had a spool in the box: Derek, "until the next find"), so a press of Needs a
    // label, or a scan of its QR, is answered by the server's "Nothing has been found yet"
    // / "No spool is selected". Its own id: #fcc-audit-last-found means a spool is in it.
    const _renderNoStrip = (data) => {
        const anyFound = (data.expected || []).some(r => r.found) || (data.rogue || []).length || (data.trail || []).length
            || (_selectedIn != null && _selectedIn === (data.audit_id != null ? data.audit_id : state.auditId));
        const words = anyFound ? 'Nothing is selected. The next spool you find shows here.'
            : "Nothing found yet. Scan a spool's label, press its tile, or use 🔎 Find a spool.";
        return `
            <div id="fcc-audit-last-none" class="fcc-audit-strip fcc-audit-strip-none">
                <div class="fcc-audit-strip-title">Last found</div>
                <div class="fcc-audit-strip-status" role="status"><span>${words}</span></div>
            </div>
        `;
    };

    // The dock's three columns, each a button over its QR, the three QRs in one row
    // (global.css lines them up): Needs a label beside the Last found box, then Done and
    // Cancel Audit, the exits a scanner needs, always in view. Drawn once per panel, so
    // their QRs never flicker at a redraw and the keyboard on one stays there; only the
    // Last found box is drawn again.
    const _dockHtml = () => `
        <div class="fcc-audit-dock-grid">
            <div id="fcc-audit-dock-found" class="fcc-audit-dock-info"></div>
            <div class="fcc-audit-dock-col fcc-audit-dock-need">
                <button type="button" id="fcc-audit-panel-needlabel" class="btn btn-sm btn-warning fw-bold"><span class="fcc-audit-dock-words"><span class="fcc-ico-on-light" aria-hidden="true">${TAG_ICON}</span> Needs a label</span></button>
                <div id="fcc-audit-panel-qr-needlabel" class="fcc-audit-strip-qr"></div>
                <div class="fcc-audit-strip-cap">📷 Scan to mark it</div>
            </div>
            <div class="fcc-audit-dock-col fcc-audit-dock-done">
                <button type="button" id="fcc-audit-panel-done" class="btn btn-success fw-bold"><span class="fcc-audit-dock-words">✅ Done…</span></button>
                <div id="fcc-audit-panel-qr-done" class="fcc-audit-dock-qr"></div>
                <div class="small fcc-audit-dock-cap">Asks before moving anything</div>
            </div>
            <div class="fcc-audit-dock-col fcc-audit-dock-cancel">
                <button type="button" id="fcc-audit-panel-cancel" class="btn btn-outline-danger fw-bold"><span class="fcc-audit-dock-words">❌ Cancel Audit</span></button>
                <div id="fcc-audit-panel-qr-cancel" class="fcc-audit-dock-qr"></div>
                <div class="small fcc-audit-dock-cap">Ends it, nothing moves</div>
            </div>
        </div>
    `;

    const _pressAnswered = (res) => {
        if (res && res.success) {
            // `left_alone`, `already` (a tile's 🏷️ on a spool flagged before the audit):
            // the press didn't do what it was asked, so the panel says so too. The toast
            // layer is under the panel, and the strip or the tile alone reads as a press
            // that worked.
            window.auditPanelNotice((res.left_alone || res.already) ? res.msg : '');
            if (res.msg) showToast(res.msg, res.already ? 'info' : 'success', 4000);
            window.refreshAuditSession();
            return;
        }
        _auditSay((res && res.msg) || "That didn't go through.");
        // The audit has gone: the heartbeat says why.
        if (res && res.stale && typeof updateLogState === 'function') updateLogState(true);
    };

    // `said`: the page's own words added to the answer's.
    const _pressPost = (url, body, said) => window.fetchT(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }, PRESS_TIMEOUT_MS)
        .then(r => r.json())
        .then((res) => _pressAnswered(said ? said(res) : res),
            () => _auditSay("That press didn't go through: FCC didn't answer. Press it again."));

    // The strip's 🖨️: inv_queue.js's 🛒 Queue, shared through /api/state/queue. Its
    // set_flag changes nothing on a spool already flagged. The toast is under the
    // panel, so the button says it too, from window.labelQueue (the redraw that
    // inventory:queue-updated asks for).
    const _queueLabel = (row) => {
        const now = Date.now();
        if (now - _queuePressedAt < DOUBLE_PRESS_MS) return;
        _queuePressedAt = now;
        if (!row || _inPrintQueue(row.id) || typeof window.addToQueue !== 'function') return;
        const tag = `#${Number(row.id)}`;
        const added = window.addToQueue({ id: Number(row.id), type: 'spool', display: _spoolName(row) });
        if (added) showToast(`Added ${tag}'s label to the print queue.`, 'success', 4000);
        else showToast(`${tag}'s label is already in the print queue.`, 'info', 4000);
        _redrawNow();
    };

    // "↩ Put back" in the Last found box (Derek, 2026-11-03: "put back into the unscanned
    // queue, so the user doesn't have to scroll to find that one, if they realize it was a
    // mistaken scan"): what a press on the last found's tile does (POST /api/audit/found,
    // found: false), here in the box, with no QR, so a double read can't take a find back.
    // An Extra comes off the Extras (A3). The server clears the last found, so the box
    // says nothing is selected until the next find. A second press under DOUBLE_PRESS_MS
    // does nothing, whatever the box shows by then: a scan answered between the two puts
    // another spool there, and the press was the first's.
    let _putBackAt = 0;
    const _putBack = (row) => {
        const now = Date.now();
        if (now - _putBackAt < DOUBLE_PRESS_MS) return;
        _putBackAt = now;
        if (!row || row.trail) return;
        const id = Number(row.id);
        const words = row.rogue ? `#${id} is off the Extras: it isn't here after all.`
            : `#${id} is back on the not-scanned list.`;
        _pressPost('/api/audit/found', { audit_id: state.auditId, id, found: false },
            (res) => ((res && res.success) ? Object.assign({}, res, { msg: words }) : res));
    };

    // Drawn again from the session it drew last when what this page knows of the print
    // queue changed it (the hash counts the strip's spool's place in the queue).
    const _redrawNow = () => { if (_lastData && _handle) _render(_lastData); };
    document.addEventListener('inventory:queue-updated', () => _redrawNow());

    // A double press of "undo that" must not mark the spool straight back: the keyboard
    // lands on Needs a label when "undo that" leaves, so its second Enter pressed that.
    const _undoJustPressed = () => _undoOut || Date.now() - _undoAnsweredAt < DOUBLE_PRESS_MS;

    // A tile's press says what the tile showed, never "the other one". A second press
    // of one tile under 700 ms is a double press and does nothing, as on the 🛑 review's
    // Discard: pressed apart, it takes the first one back.
    const _pressedAt = new Map();
    const _pressTile = (tile) => {
        const id = Number(tile.dataset.auditTile);
        const now = Date.now();
        if (now - (_pressedAt.get(id) || 0) < DOUBLE_PRESS_MS) return;
        _pressedAt.set(id, now);
        _pressPost('/api/audit/found', { audit_id: state.auditId, id, found: tile.dataset.auditFound !== '1' });
    };

    // A found tile's 🏷️ says what it showed: marked here, its tap takes the mark back;
    // else it marks (a flag already up is answered `already`, nothing written). A second
    // tap under DOUBLE_PRESS_MS is a double press and does nothing, as a tile's: a tap
    // apart takes the mark back. It never changes the last found.
    const _tagPressedAt = new Map();
    const _pressTag = (btn) => {
        const id = Number(btn.dataset.auditTag);
        const now = Date.now();
        if (now - (_tagPressedAt.get(id) || 0) < DOUBLE_PRESS_MS) return;
        _tagPressedAt.set(id, now);
        const undo = btn.dataset.auditTagState === 'marked';
        _pressPost(undo ? '/api/audit/needs_label_undo' : '/api/audit/needs_label', { audit_id: state.auditId, id });
    };

    // Delegated: the tiles are redrawn with the body.
    const _bodyClick = (e) => {
        const t = e.target && e.target.closest ? e.target : null;
        if (!t) return;
        const labelBtn = t.closest('[data-audit-tag]');
        if (labelBtn) { _pressTag(labelBtn); return; }
        const tile = t.closest('[data-audit-tile]');
        if (tile) _pressTile(tile);
    };

    // --- A double click's second press (Group 58 re-review) --------------------------
    // A press that takes away, or brings, what lies under the pointer hands the second
    // press of a double click to whatever lies beneath. A second press is one that starts
    // under DOUBLE_PRESS_MS after the last primary press, at its spot (within its slop): a
    // press elsewhere is a person's next press, and goes on.
    const _isSecondPress = (first, e, now) => !!first && now - first.at < DOUBLE_PRESS_MS
        && Math.abs(first.x - e.clientX) <= first.slop && Math.abs(first.y - e.clientY) <= first.slop;
    const _pressEaten = () => !!_eatPress && Date.now() - _eatPress < 2000;

    // Done's question closes on the first click of a double click, and the second lands
    // on whatever lies under its button: Cancel Audit, or a tile (a spool found that
    // nobody touched). "Back to the audit" should only go back. On the panel's root in
    // the capture phase, so it covers every button on it in one place. Any click for
    // DOUBLE_PRESS_MS after the question is answered, the keyboard's too (the keyboard
    // lands on Done, and a double Enter asked again). And a pointer's second press
    // (_eatPress), wherever on the panel it lands: one at the spot of a press on what sat
    // over the panel (Done's question, the 🧺 list, the legacy picker, the ⌨️ list, gone
    // with the first press), or of a press on a tile or the dock, which move what lies
    // under the pointer: a find moves its tile from Not scanned to Found and slides the
    // next one into its place, and changes the Last found box, which can grow the dock
    // over the tiles' last row (a tile's double click pressed Needs a label, and a
    // spool nobody asked about was flagged), or grows a short panel, which centres
    // itself again (the second press landed beside the tile and took the keyboard off
    // it); and the dock's own Needs a label marked twice.
    const _shieldClick = (e) => {
        const eat = Date.now() - _questionClosedAt < DOUBLE_PRESS_MS || (e.detail > 0 && _pressEaten());
        if (e.detail > 0) _eatPress = 0;
        if (!eat) return;
        e.preventDefault();
        e.stopImmediatePropagation();
    };

    // The same press's mousedown would move the keyboard to what lies under it, with no
    // ring to say so, and the next Enter pressed that (Cancel Audit, or a tile): Done
    // keeps the keyboard Back gave it.
    const _shieldMouse = (e) => {
        if (Date.now() - _questionClosedAt < DOUBLE_PRESS_MS || _pressEaten()) e.preventDefault();
    };

    // The panel went, or came, under the pointer (Done with nothing to park, Cancel
    // Audit, Hide, a park that answered fast; the deck tile or the 🕵️ pill bringing a
    // hidden panel up, its Cancel Audit under the tile's second click; Done's question or
    // the 🧺 list opening there). The second press would land on what lies under it now:
    // the deck behind the panel armed Drop or Eject mode, asked Undo, opened the weigh
    // window or started a new audit, and the panel's own Cancel Audit ended the audit
    // the tile had just shown. Armed only while the press that did it is under
    // DOUBLE_PRESS_MS old, so an audit ended from another window, a scan or the heartbeat
    // takes nobody's click. The next press that starts at its spot in DOUBLE_PRESS_MS then
    // reaches nothing, on the document: the panel's root is gone, or wasn't there for the
    // first press. Its pointerdown and pointerup too, which the floating pills act on. A
    // click from the keyboard (detail 0) is no double click, and goes on.
    const _shieldPage = () => {
        const now = Date.now();
        if (_press && now - _press.at < DOUBLE_PRESS_MS) _pageShield = Object.assign({}, _press, { at: now });
    };

    // Registered once. A primary press only: mouse, touch, pen.
    document.addEventListener('pointerdown', (e) => {
        if (e.button > 0) return;
        const now = Date.now();
        const shield = _pageShield;
        _pageShield = null;             // one press: this one, or one elsewhere ends it
        _pageEating = 0;
        _eatPress = 0;
        if (_isSecondPress(shield, e, now)) {
            _pageEating = now;
            e.stopImmediatePropagation();
            return;
        }
        const slop = e.pointerType === 'mouse' ? DOUBLE_PRESS_SLOP_PX.mouse : DOUBLE_PRESS_SLOP_PX.other;
        _press = { at: now, x: e.clientX, y: e.clientY, slop };
        if (!_handle) { _panelPress = null; return; }
        const t = e.target;
        const onPanel = !!(t && t.nodeType === 1 && _handle.element.contains(t));
        const first = _panelPress;
        // The strip moved to a spool the first press didn't bring (neither the tile's, nor
        // what it showed then): a scan read between them, so this press is a person's
        // next one (they mark #57, scan #99 and mark that one too, quickly).
        const moved = !!first && _stripSpool != null && _stripSpool !== first.stripWas && _stripSpool !== first.tile;
        if (onPanel && _isSecondPress(first, e, now) && (first.cover || (first.strip && !moved))) _eatPress = now;
        const tileEl = onPanel ? t.closest('[data-audit-tile]') : null;
        // A press on the dock counts as one on the strip (Derek, 2026-11-03, sample 1b): its
        // Needs a label sits in its own column there, outside the Last found box, and the
        // box's words can grow the dock under the pointer, or shrink it. So does a tap on a
        // found tile's 🏷️, which grows its tile ("needs a label") and moves those under it.
        _panelPress = Object.assign({}, _press, {
            cover: !onPanel,
            strip: onPanel && !!(tileEl || t.closest('[data-audit-tag]') || t.closest('#fcc-audit-panel-dock')),
            stripWas: _stripSpool,
            tile: tileEl ? Number(tileEl.dataset.auditTile) : null,
        });
    }, true);
    ['mousedown', 'pointerup', 'mouseup', 'click', 'dblclick'].forEach((type) => {
        document.addEventListener(type, (e) => {
            if (!_pageEating || Date.now() - _pageEating > 2000) return;
            if (type === 'click' && !e.detail) return;      // a key's click: not this press
            if (e.button > 0) return;
            if (type !== 'pointerup') e.preventDefault();  // mousedown: the keyboard stays put
            e.stopImmediatePropagation();
            if (type === 'click') {
                const was = _pageEating;
                setTimeout(() => { if (_pageEating === was) _pageEating = 0; }, 0);   // and its dblclick
            }
        }, true);
    });
    document.addEventListener('pointercancel', () => { _pageEating = 0; }, true);

    const _applyBusy = () => {
        if (!_handle) return;
        ['#fcc-audit-panel-done', '#fcc-audit-panel-cancel'].forEach((sel) => {
            const btn = _handle.element.querySelector(sel);
            if (btn) btn.disabled = _busy;
        });
    };

    // Disables Done and Cancel until the answer: both stay on screen for the whole
    // request. Only the buttons change: a redraw here would re-make the QRs. A
    // disabled button drops the keyboard's focus, so it comes back with the answer.
    window.auditPanelBusy = (on) => {
        const was = _busy;
        _busy = !!on;
        const active = document.activeElement;
        if (_busy && !was) {
            _busyFocus = (active && /^fcc-audit-panel-(done|cancel)$/.test(active.id || '')) ? active.id : null;
        }
        _applyBusy();
        if (!_busy && _busyFocus && _handle && (!active || active === document.body)) {
            const btn = _handle.element.querySelector(`#${_busyFocus}`);
            if (btn && btn.focus) btn.focus();
        }
        if (!_busy) _busyFocus = null;
    };

    // A scan's refusal, beside its toast: the toast layer is under the panel, and
    // the Activity Log behind it. Outside #fcc-audit-panel-body, so a redraw keeps
    // it. '' clears it: a good scan means the refusal has been dealt with.
    window.auditPanelNotice = (msg) => {
        // The panel gone and the report window up (a Done this page ended): it says it.
        if (!_handle) { if (window.auditReportNotice) window.auditReportNotice(msg); return; }
        // Find, over the panel, would hide it: it says it too.
        if (_find && window.auditFindNotice) window.auditFindNotice(_find, msg);
        const el = _handle.element.querySelector('#fcc-audit-panel-notice');
        if (!el) return;
        el.textContent = msg || '';
        el.style.display = msg ? 'block' : 'none';
    };

    const _render = (data) => {
        if (!_handle) return;
        const root = _handle.element;
        const body = root.querySelector('#fcc-audit-panel-body');
        if (!body) return;
        // Hash-skip when payload is unchanged so the 2s poll stops
        // re-rendering the tile grid (and re-generating QR codes) every
        // tick. Derek 2026-05-16 visible-flicker fix. The strip's 🖨️ reads the
        // print queue, which the poll's answer doesn't carry: another tab's queue
        // reaches this one every 2 s (inv_queue.js).
        _lastData = data;
        const queued = data.last_found ? _inPrintQueue(data.last_found.id) : false;
        const hash = `${JSON.stringify(data)}|${queued ? 1 : 0}`;
        if (hash === _lastRenderHash) return;
        _lastRenderHash = hash;
        // Find's tags say what this audit says of each spool now.
        if (_find && window.retagAuditFind) window.retagAuditFind(_find);
        // What this audit doesn't check: always in view, outside the scrolling body.
        const note = root.querySelector('#fcc-audit-panel-note');
        if (note) {
            note.textContent = data.note || '';
            note.style.display = data.note ? 'block' : 'none';
        }
        const s = data.stats || { total_expected: 0, found: 0, missing: 0, rogue: 0, trail: 0 };
        const expected = data.expected || [];
        const extras = data.rogue || [];
        const trail = data.trail || [];
        const extraTiles = extras.map(r => _renderTile(r, 'extra')).join('');
        const trailTiles = trail.map(r => _renderTile(r, 'trail')).join('');
        const loc = _escapeHtml(data.location_id || '(scan a location to start)');
        // Not scanned first (Derek, 2026-11-03, sample 5a(i): "keeping of unfound items at
        // the top"): the spools still to find, with their QRs, then the ones found, each
        // in the order the server sends (shelf order). A group with nothing in it has no
        // heading. A press moves a tile from one group to the other and the keyboard
        // goes with it (its tile is found by its id below), never to the tile that slid
        // into its place, whose next Enter would find a spool nobody pressed.
        const group = (key, title, rows, kind, gap) => (rows.length ? `
                <div class="fcc-audit-subhead">${title} (${rows.length})</div>
                <div data-audit-group="${key}" class="fcc-audit-grid" style="margin-bottom:${gap}px;">
                    ${rows.map(r => _renderTile(r, kind)).join('')}
                </div>` : '');
        const expectedTiles = group('missing', 'Not scanned', expected.filter(r => !r.found), 'missing', 10)
            + group('found', 'Found', expected.filter(r => r.found), 'found', 12);
        // A note says it already when the place's spools are all in places inside it.
        const nothing = data.location_id ? (data.note ? '' : 'Nothing is filed here.') : "Scan a location's label to start.";
        // A button or a tile the redraw is about to replace keeps the keyboard. The dock's
        // own columns (Needs a label, Done, Cancel Audit) are never replaced, so only the
        // Last found box's buttons and the tiles need it.
        const active = document.activeElement;
        const refocus = (active && /^fcc-audit-(label-(undo|queue)|put-back)$/.test(active.id || '')) ? active.id : null;
        const refocusTile = (active && active.dataset) ? active.dataset.auditTile : null;
        const refocusTag = (active && active.dataset) ? active.dataset.auditTag : null;
        const stripSpool = data.last_found ? data.last_found.id : null;
        const stripMoved = stripSpool !== _stripSpool;
        _stripSpool = stripSpool;
        if (stripSpool != null) _selectedIn = data.audit_id != null ? data.audit_id : state.auditId;
        // The tally, above the scrolling list and always in view (Derek, 2026-11-03,
        // sample 2a: "persistent status up top"), in the words and colours it had as the
        // body's first line.
        const tally = root.querySelector('#fcc-audit-panel-tally');
        if (tally) {
            tally.innerHTML = `
                Auditing <b style="color:#0ff;">${loc}</b> —
                <span style="color:#0f0; font-weight:bold;">${s.found}/${s.total_expected}</span> found,
                <span style="color:rgba(255,255,255,0.75); font-weight:bold;">${s.missing}</span> missing,
                <span style="color:#fc0; font-weight:bold;">${s.rogue}</span> extra${s.trail ? `,
                <span style="color:#7fe8ff; font-weight:bold;">${s.trail}</span> loaded from here` : ''}`;
        }
        body.innerHTML = `
            ${expected.length ? `
                <div style="margin-bottom:6px;">
                    <span style="font-weight:bold; color:#0ff;">Expected here</span>
                    <span class="small" style="color:rgba(255,255,255,0.75); margin-left:8px;">No label to scan? ${state.auditId && expected.some(r => !r.found) ? 'Press its tile, or scan its QR.' : 'Press its tile.'}</span>
                </div>
                ${expectedTiles}
            ` : (nothing ? `<div class="small" style="color:rgba(255,255,255,0.7);">${nothing}</div>` : '')}
            ${data.idle_timeout_min ? `
                <div class="small" style="color:rgba(255,255,255,0.55); margin-top:8px;">
                    ⏳ This audit stays open for <b>${_escapeHtml(data.idle_timeout_min)} min</b> of
                    inactivity, then clears itself with nothing moved.
                </div>` : ''}
            ${extras.length ? `
                <div style="margin:8px 0 6px;">
                    <span style="font-weight:bold; color:#fc0;">Extra (found here, filed elsewhere)</span>
                    <span class="small" style="color:rgba(255,255,255,0.75); margin-left:8px;">Not here after all? Press its tile.</span>
                </div>
                <div data-audit-group="extra" class="fcc-audit-grid">
                    ${extraTiles}
                </div>
            ` : ''}
            ${trail.length ? `
                <div style="font-weight:bold; color:#7fe8ff; margin:8px 0 6px;">Loaded from here</div>
                <div data-audit-group="trail" class="fcc-audit-grid">
                    ${trailTiles}
                </div>
            ` : ''}
        `;
        // Now, not two frames later: the tile is its full size before the keyboard's
        // tile is brought into view, and a QR already drawn doesn't flicker.
        _placeTileQrs(body);
        // The dock (Derek, 2026-11-03, sample 1b): its columns once per panel, the Last
        // found box at every redraw.
        const dock = root.querySelector('#fcc-audit-panel-dock');
        if (dock && !_dockDrawn) {
            _dockDrawn = true;
            dock.innerHTML = _dockHtml();
            const doneBtn = root.querySelector('#fcc-audit-panel-done');
            if (doneBtn) doneBtn.onclick = () => { if (!_busy) window.auditDone(); };
            const cancelBtn = root.querySelector('#fcc-audit-panel-cancel');
            if (cancelBtn) cancelBtn.onclick = () => { if (!_busy) window.cancelAudit(); };
            const markBtn = root.querySelector('#fcc-audit-panel-needlabel');
            if (markBtn) markBtn.onclick = () => { if (!_undoJustPressed()) window.auditNeedLabel(); };
            // `generateSafeQR` is a script-scope const in inv_core.js — accessible by bare
            // name (not on window). The wrong `window.generateSafeQR` guard once silently
            // dropped these calls, which is why no QR rendered (Derek 2026-05-16). Each box
            // holds its QR's size until it draws, two frames later (global.css).
            if (typeof generateSafeQR === 'function') {
                generateSafeQR('fcc-audit-panel-qr-done', 'CMD:DONE', 90);
                generateSafeQR('fcc-audit-panel-qr-cancel', 'CMD:CANCEL', 90);
                generateSafeQR('fcc-audit-panel-qr-needlabel', 'CMD:NEEDLABEL', 80);
            }
        }
        const found = root.querySelector('#fcc-audit-dock-found');
        if (found) found.innerHTML = _renderStrip(data.last_found) || _renderNoStrip(data);
        // The dock in the flow on a window too short for it, before the keyboard's tile
        // is brought into view.
        _fitDock();
        const undoBtn = root.querySelector('#fcc-audit-label-undo');
        if (undoBtn) {
            // Not `disabled`: that drops the keyboard's focus, and it goes to the
            // Needs a label button when this one leaves.
            const sid = data.last_found.id;
            undoBtn.onclick = () => {
                if (_undoJustPressed()) return;
                _undoOut = true;
                // It leaves the print queue alone (B), and says so when the label is there.
                _pressPost('/api/audit/needs_label_undo', { audit_id: state.auditId, id: sid },
                    (res) => ((res && res.success && _inPrintQueue(sid))
                        ? Object.assign({}, res, { msg: `${res.msg ? `${res.msg} ` : ''}#${Number(sid)} is still in the print queue.` })
                        : res))
                    .finally(() => { _undoOut = false; _undoAnsweredAt = Date.now(); });
            };
        }
        const queueBtn = root.querySelector('#fcc-audit-label-queue');
        if (queueBtn) queueBtn.onclick = () => _queueLabel(data.last_found);
        const putBackBtn = root.querySelector('#fcc-audit-put-back');
        if (putBackBtn) putBackBtn.onclick = () => _putBack(data.last_found);
        _applyBusy();
        if (refocus && !_busy) {
            // "undo that" goes with the mark it undid: the keyboard goes to Needs a label.
            // Not when another spool took the box: an Enter meant for the old spool must
            // write nothing on the new one (nor queue its label), so the keyboard stays
            // on the panel, where N and the arrows still work.
            const again = stripMoved ? null
                : (root.querySelector(`#${refocus}`) || root.querySelector('#fcc-audit-panel-needlabel'));
            if (again && again.focus) again.focus();
        }
        const tile = refocusTile ? body.querySelector(`[data-audit-tile="${refocusTile}"]`) : null;
        if (tile && tile.focus) tile.focus();
        const tagBtn = refocusTag ? body.querySelector(`[data-audit-tag="${refocusTag}"]`) : null;
        if (tagBtn && tagBtn.focus) tagBtn.focus();
        // Unless the person has gone somewhere on the panel since.
        if (_focusDoneNext) {
            _focusDoneNext = false;
            if (!root.contains(document.activeElement)) _focusDone();
        }
    };

    const _poll = async () => {
        if (_pollInflight) { _pollPending = true; return; }
        _pollInflight = true;
        const gen = _panelGen;
        const sentAt = _auditClock();
        try {
            // Explicit timeout: a wedged request would leave _pollInflight stuck
            // true and the panel frozen.
            const r = await window.fetchT('/api/audit_session', {}, 8000);
            const d = await r.json();
            // Read for a hidden panel too: the legacy picker tags its spools from it.
            _lastSession = (d && d.active) ? d : null;
            if (gen !== _panelGen) return;   // the panel closed meanwhile
            if (!d || !d.active) {
                // Seen here before any heartbeat, so the warning starts here too.
                if (window._syncAuditSignal) window._syncAuditSignal(d, { sentAt });
                if (!state.auditActive) window.closeAuditPanel();
                return;
            }
            state.auditId = d.audit_id != null ? d.audit_id : state.auditId;
            state.auditIdleMin = d.idle_timeout_min || state.auditIdleMin;
            if (state.auditActive && (d.location_id || '') !== state.auditLocation && !(sentAt < state.auditLocationAt)) {
                state.auditLocation = d.location_id || '';
                state.auditLocationAt = sentAt;
                window.updateAuditPill();
            }
            _render(d);
        } catch (e) { /* network hiccup — try again next tick */ }
        finally {
            _pollInflight = false;
            if (_pollPending) { _pollPending = false; _poll(); }
        }
    };

    window.openAuditPanel = () => {
        if (_handle) return;  // idempotent
        if (typeof window.mountOverlay !== 'function') return;
        // An audit started meanwhile: its panel takes the place of a report read.
        if (window.closeAuditReport) window.closeAuditReport();
        _lastRenderHash = null;  // force first render after open
        _lastData = null;        // nothing drawn yet: Find tags nothing until the first answer
        _lastSession = null;     // nor the legacy picker: it may be another audit's
        _dockDrawn = false;      // a new panel: its dock is drawn at the first answer
        // As tall as the window less 8 px above and below (Derek, 2026-11-03, sample 1b),
        // as a question that doesn't fit is: the dock under the list takes room, and the
        // deck under the panel is behind its backdrop and only shows this panel.
        const content = `
            <div class="fcc-audit-panel" style="background:#1e1e1e; color:#fff; border:2px solid #ff00ff;
                        border-radius:8px; padding:0.875rem 1rem;
                        width:min(51.25rem,94vw); display:flex; flex-direction:column;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div style="font-weight:bold; font-size:1.15em; color:#ff7eff;">
                        🕵️‍♀️ Audit in Progress
                    </div>
                    <div class="d-flex flex-wrap justify-content-end gap-2">
                        <button id="fcc-audit-panel-find" class="btn btn-sm btn-outline-info"
                                title="A spool here with no label to scan: find it by its name, colour, brand or number, and pick it (/).">🔎 Find a spool</button>
                        <button id="fcc-audit-panel-loose" class="btn btn-sm btn-outline-info"
                                title="Every spool filed at a room or a cart itself, with no more exact place. Read-only: it changes nothing in this audit.">🧺 Loose spools</button>
                        <button id="fcc-audit-panel-close" class="btn btn-sm btn-outline-light"
                                title="Hide the panel: the audit keeps running, and scans still go to it. The 🕵️ audit pill brings it back.">Hide</button>
                    </div>
                </div>
                <div id="fcc-audit-panel-notice" role="alert"
                     style="display:none; margin-bottom:8px; padding:6px 10px; border-radius:6px; background:#4a3200;
                            color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; overflow-wrap:anywhere;"></div>
                <div id="fcc-audit-panel-note"
                     style="display:none; margin-bottom:8px; font-size:var(--fcc-fs-row); color:#ffe08a;"></div>
                <div id="fcc-audit-panel-tally" style="flex:0 0 auto; margin-bottom:8px; font-size:0.95rem;"></div>
                <!-- The tiles scroll; the dock under them never does (global.css), unless the
                     window is too short for both (_fitDock). -->
                <div id="fcc-audit-panel-scroll" class="fcc-audit-scroll">
                    <div id="fcc-audit-panel-body" class="fcc-audit-body">
                        <div class="small" style="color:rgba(255,255,255,0.7);">Loading audit state…</div>
                    </div>
                    <div id="fcc-audit-panel-dock" class="fcc-audit-dock"></div>
                </div>
            </div>
        `;
        _handle = window.mountOverlay({
            id: 'fcc-audit-panel-overlay',
            content,
            tier: 'standard',
            backdrop: true,
            backdropDismiss: false,  // Audit is in progress; Hide is the explicit dismiss
            trapTab: true,           // the page behind it is out of reach, as for the mouse
            onEscape: () => window.closeAuditPanel(),
        });
        // Each time the panel opens: Back brings a hidden one back, under the pointer.
        _handle.element.addEventListener('click', _shieldClick, true);
        _handle.element.addEventListener('mousedown', _shieldMouse, true);
        // Brought up under the pointer (the deck tile, the 🕵️ pill, Back): its Cancel
        // Audit can lie under the second click.
        _shieldPage();
        const closeBtn = _handle.element.querySelector('#fcc-audit-panel-close');
        if (closeBtn) closeBtn.onclick = () => window.closeAuditPanel();
        // Over the panel, so the confirm tier. A row opens nothing during an audit.
        const looseBtn = _handle.element.querySelector('#fcc-audit-panel-loose');
        if (looseBtn) looseBtn.onclick = () => { _loose = window.openLooseList({ tier: 'confirm' }); _shieldPage(); };
        const findBtn = _handle.element.querySelector('#fcc-audit-panel-find');
        if (findBtn) findBtn.onclick = () => _openFind();
        const bodyEl = _handle.element.querySelector('#fcc-audit-panel-body');
        if (bodyEl) {
            bodyEl.addEventListener('click', _bodyClick);
            // `focus` in the capture phase: mountOverlay's focus guard stops focusin at
            // the document, before it reaches anything inside the overlay.
            bodyEl.addEventListener('focus', _tileFocused, true);
        }
        // A window resized, or a notice, the note or the tally above the list that grows.
        const scrollEl = _handle.element.querySelector('#fcc-audit-panel-scroll');
        if (scrollEl && typeof ResizeObserver === 'function') {
            _dockFit = new ResizeObserver(() => _fitDock());
            _dockFit.observe(scrollEl);
        }
        // Initial render + start the 2s poll.
        _poll();
        _pollTimer = setInterval(_poll, 2000);
    };

    // An audit that ends, or a panel that goes, takes what sits on it along: a Yes
    // left up would answer a question about an audit that has gone.
    window.closeAuditPanel = () => {
        // Gone from under the pointer: what lies beneath it must not take the second click.
        if (_handle) _shieldPage();
        _panelGen += 1;
        _focusDoneNext = false;
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_question) {
            const open = _question;
            _question = null;
            try { open.close(); } catch (_) { /* noop */ }
        }
        if (_loose) {
            const list = _loose;
            _loose = null;
            if (window.closeLooseList) window.closeLooseList(list);
        }
        if (_find) {
            const find = _find;
            _find = null;
            if (window.closeAuditFind) window.closeAuditFind(find);
        }
        if (_dockFit) { _dockFit.disconnect(); _dockFit = null; }
        if (_handle) { try { _handle.cleanup(); } catch (_) { /* noop */ } _handle = null; }
    };

    // --- Find a spool (Derek, 2026-11-03, A2) ----------------------------------------
    // "some spools are in the system, with a location, but no barcode": a window over
    // the panel finds one by its name and picks it (inv_audit_find.js). The pick goes
    // out as a search card's click does, ID:<id> with no label read, in its turn behind
    // scans already read, and the audit's own spool path makes it found or an Extra.
    // What this audit says of a spool now: on its list, or found already.
    const _findTag = (id) => {
        const d = _lastData;
        if (!d) return null;
        const hit = (rows) => (rows || []).find(r => r && String(r.id) === String(id));
        const listed = hit(d.expected);
        if (listed) return listed.found ? 'found' : 'listed';
        return (hit(d.rogue) || hit(d.trail)) ? 'found' : null;
    };

    // Where a spool stands in the audit that runs, for the legacy shared-label picker (Derek,
    // 2026-11-03: it "says which candidates are on this audit's list and whether they're
    // found yet"), from what the page already knows, the session it read last, with no
    // request of its own: {standing, place}, `standing` one of 'listed' (on the list, not
    // scanned yet), 'found' (on the list, found), 'extra' (found here, filed elsewhere),
    // 'trail' (loaded on a head from here) or 'none' (not on its list). null with no audit,
    // before its place is scanned, or when what the page read is another audit's.
    window.auditStandingOf = (id) => {
        const d = _lastSession;
        if (!state.auditActive || !d || !d.active || !d.location_id) return null;
        if (d.audit_id != null && String(d.audit_id) !== String(state.auditId)) return null;
        const hit = (rows) => (rows || []).find(r => r && String(r.id) === String(id));
        const listed = hit(d.expected);
        const standing = listed ? (listed.found ? 'found' : 'listed')
            : (hit(d.rogue) ? 'extra' : (hit(d.trail) ? 'trail' : 'none'));
        return { standing, place: String(d.location_id) };
    };

    const _openFind = () => {
        if (!_handle || typeof window.openAuditFind !== 'function') return;
        // A double Enter or Space on a row: the second lands on 🔎, where the keyboard
        // went back to.
        if (Date.now() - _findPickedAt < DOUBLE_PRESS_MS) return;
        if (window.isTopOverlay && !window.isTopOverlay(_handle.element)) return;
        _find = window.openAuditFind({
            tagOf: _findTag,
            // The keyboard comes back to 🔎, on the panel, however Find was opened.
            opener: _handle.element.querySelector('#fcc-audit-panel-find'),
            onClose: (handle, picked) => {
                if (_find === handle) _find = null;
                if (picked) _findPickedAt = Date.now();
            },
        });
        // Opened under the pointer that pressed 🔎: the second click lands on it.
        _shieldPage();
    };

    // A scan the audit took (or Done asking) is the spool in the person's hand: Find,
    // over the panel, would hide what it did.
    window.closeAuditFindForScan = () => {
        if (!_find) return;
        const find = _find;
        _find = null;
        if (window.closeAuditFind) window.closeAuditFind(find);
    };

    window.isAuditPanelOpen = () => !!_handle;

    // Poll once RIGHT NOW instead of waiting for the next 2s tick: called after a
    // scan lands, so its tile turns at once. Hidden, it still names the pill's place.
    window.refreshAuditSession = () => { _poll(); };

    // --- The panel's keys (Group 58.2) --------------------------------------------
    // N marks the last spool found, as the strip's button does; the arrows move
    // between the tiles, and Enter presses the one with the focus (a real button).
    // Only while the panel is on top: the question and the Loose spools list own their
    // keys, and the shortcut list is read, not pressed through.
    const NEED_LABEL_WAIT_MS = 150;     // the scan accumulator's burst figure (scripts.html)

    const _keyNeedLabel = (e) => {
        // A held key's repeats are no second press, and no scanner sends one.
        if (e.repeat) { e.preventDefault(); e.stopImmediatePropagation(); return; }
        if (window.scanIsArriving && window.scanIsArriving()) return;
        // The slot picker's rule, with a longer wait: its key only moves a highlight, and
        // this one writes. Left for the scan accumulator: a label may start with an N
        // (an old bare location id), and only the key after it can tell, a slow
        // scanner's up to the burst figure later (at the picker's 50 ms, 60 ms a key
        // marked the last spool and lost the label's first letter). Nothing followed:
        // the person's, so it goes from the buffer, or it sits in front of the next scan.
        const root = _handle.element;
        const left = `${state.scanBuffer || ''}${e.key}`;
        setTimeout(() => {
            if (!_handle || _handle.element !== root || state.scanBuffer !== left) return;
            if (window.isTopOverlay && !window.isTopOverlay(root)) return;
            if (window.clearScanBuffer) window.clearScanBuffer();
            window.auditNeedLabel();
        }, NEED_LABEL_WAIT_MS);
    };

    // What scrolls the tiles: the body, or with the dock in the flow (_fitDock) the part
    // that holds the body and the dock.
    const _scroller = () => {
        const root = _handle && _handle.element;
        if (!root) return null;
        const wrap = root.querySelector('#fcc-audit-panel-scroll');
        return (wrap && wrap.classList.contains('fcc-audit-scroll-flow')) ? wrap : root.querySelector('#fcc-audit-panel-body');
    };

    // A tile the keyboard reaches is seen whole, its focus ring too: clear of the
    // scrolling part's top and bottom edges. Nothing is drawn over the tiles since the
    // dock (Derek, 2026-11-03, sample 1b), which sits under the list; the browser's own
    // focus scroll would leave the ring cut at an edge.
    const TILE_AIR_PX = 6;              // the focus ring (2 px + 1 px offset) and a little
    const _tileClear = (tile) => {
        const sc = _scroller();
        if (!sc || !tile) return;
        const box = sc.getBoundingClientRect();
        const under = tile.getBoundingClientRect().bottom + TILE_AIR_PX - box.bottom;
        if (under > 0) sc.scrollTop += under;
        const over = box.top + TILE_AIR_PX - tile.getBoundingClientRect().top;
        if (over > 0) sc.scrollTop -= over;
    };

    // Tab into a tile, and the keyboard's tile drawn again after a redraw. Not a mouse's
    // focus: a click's own mousedown focuses the tile, and a tile pressed near the edge
    // and scrolled out from under the pointer would lose the click to the gap its
    // mouseup lands in.
    // The whole tile, its row under the name and its ring with it (the cell draws the ring).
    const _cellOf = (el) => (el && el.closest && el.closest('.fcc-audit-tile-cell')) || el;
    const _tileFocused = (e) => {
        const tile = e.target;
        if (!tile || !tile.matches) return;
        if (tile.matches('.fcc-audit-tile:focus-visible, .fcc-audit-tile-tag:focus-visible')) _tileClear(_cellOf(tile));
    };

    // The dock stays under the list, out of the scroll, while it leaves the tiles room:
    // at least DOCK_MIN_BODY_REM of the scrolling part (a tile row and its heading), or
    // the whole list when it is shorter than that. On a window too short for both (a
    // phone at Extra Large text, a phone held sideways, a laptop window pulled short;
    // measured, a phone at Large stays docked) it goes in the flow after the tiles
    // (.fcc-audit-scroll-flow): the list and
    // the dock scroll as one, and every tile can still be brought into view and pressed.
    // It replaces the Last found strip's sticky rule (review of 7e3720f, P-5), which the
    // dock retired. Measured after each render, as the scrolling part changes size (a
    // resize, a notice, the note or the tally above it) and on a Text size change. The
    // dock is the same height in the flow and out of it, and it comes back only with
    // DOCK_SLACK_PX to spare, so the measure never flips back by itself.
    const DOCK_MIN_BODY_REM = 7;
    const DOCK_SLACK_PX = 8;
    const _fitDock = () => {
        const root = _handle && _handle.element;
        if (!root || typeof window.getComputedStyle !== 'function') return;
        const wrap = root.querySelector('#fcc-audit-panel-scroll');
        const body = root.querySelector('#fcc-audit-panel-body');
        const dock = root.querySelector('#fcc-audit-panel-dock');
        if (!wrap || !body || !dock || !(wrap.clientHeight > 0)) return;
        const flow = wrap.classList.contains('fcc-audit-scroll-flow');
        const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const docked = dock.offsetHeight + (parseFloat(getComputedStyle(dock).marginTop) || 0);
        const room = wrap.clientHeight - docked;        // what the list keeps with the dock docked
        const need = Math.min(DOCK_MIN_BODY_REM * rem, body.scrollHeight);
        const goFlow = flow ? room < need + DOCK_SLACK_PX : room < need;
        if (goFlow !== flow) wrap.classList.toggle('fcc-audit-scroll-flow', goFlow);
    };
    document.addEventListener('fcc:text-size', () => _fitDock());

    const _keyArrow = (e) => {
        const tiles = Array.from(_handle.element.querySelectorAll('.fcc-audit-tile'));
        if (!tiles.length) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const back = e.key === 'ArrowLeft' || e.key === 'ArrowUp';
        // From a found tile's 🏷️ (reached by Tab): on to the next tile, or back to its own.
        const cur = document.activeElement;
        const own = (cur && cur.dataset && cur.dataset.auditTag)
            ? tiles.find(t => t.dataset.auditTile === cur.dataset.auditTag) : null;
        const at = own ? tiles.indexOf(own) : tiles.indexOf(cur);
        const next = at < 0 ? (back ? tiles.length - 1 : 0)
            : ((own && back) ? at : (at + (back ? tiles.length - 1 : 1)) % tiles.length);
        tiles.forEach(t => t.classList.remove('kb-active'));
        tiles[next].classList.add('kb-active');
        tiles[next].focus();
        _tileClear(_cellOf(tiles[next]));
    };

    // '/' opens Find a spool, as it opens the search elsewhere (fab_drag.js, which it
    // would open behind the panel): a person's, never the '/' of a URL a scan carries
    // (window.scanIsArriving). The keys a person left before it go with it, or they'd
    // start the next scan.
    const _keyFind = (e) => {
        if (e.repeat || (window.scanIsArriving && window.scanIsArriving())) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        if (window.clearScanBuffer) window.clearScanBuffer();
        _openFind();
    };

    document.addEventListener('keydown', (e) => {
        const isN = e.key === 'n' || e.key === 'N';
        const isFind = e.key === '/';
        if (!_handle || !(isN || isFind || /^Arrow(Up|Down|Left|Right)$/.test(e.key))) return;
        // Shift: a keyboard that types '/' with it, and a scanner's capitals, which N
        // and the arrows leave alone.
        if (e.ctrlKey || e.altKey || e.metaKey || (e.shiftKey && !isFind)) return;
        if (window.isTopOverlay && !window.isTopOverlay(_handle.element)) return;
        const shortcuts = document.getElementById('fcc-shortcuts-overlay');
        if (shortcuts && shortcuts.getClientRects().length) return;
        const tag = ((e.target && e.target.tagName) || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) return;
        if (isFind) _keyFind(e);
        else if (isN) _keyNeedLabel(e);
        else _keyArrow(e);
    }, true);

    if (window.registerShortcut) {
        window.registerShortcut({
            id: 'audit-need-label', scope: 'Audit Panel', keys: ['N'],
            description: 'The last spool found needs a label: raises it in the 🏷️ Backlog. "undo that" on the panel takes it back.',
        });
        window.registerShortcut({
            id: 'audit-tiles', scope: 'Audit Panel', keys: ['↑', '↓', '←', '→'],
            description: 'Move between the tiles of the spools expected here and the Extras. Wraps at the ends.',
        });
        window.registerShortcut({
            id: 'audit-tile-press', scope: 'Audit Panel', keys: ['Enter'],
            description: 'On a tile: found, with no label read. Pressed again, it goes back to not scanned. On an Extra: it isn\'t here after all. On a found tile\'s 🏷️ (Tab to it): it needs a label; pressed again, the mark comes off.',
        });
        window.registerShortcut({
            id: 'audit-find', scope: 'Audit Panel', keys: ['/'],
            description: 'Find a spool with no label to scan by its name, colour, brand or number, and pick it: it counts as found here.',
        });
    }

    // --- Done's question (Group 58, Build spec section 7) -------------------------
    // Done moves nothing until a person says so. It is window.confirmActivePrint's
    // three-way, the one dialog that draws above this panel (#confirmModal is z 1100
    // and the panel 20000) and holds every other scan off until it is answered. It
    // opens on Back to the audit, and Enter goes back: a scanner's Enter, a double
    // press and a held key all lose nothing. A mouse's double click loses nothing
    // either: the yes takes no click for DOUBLE_PRESS_MS (`armAfterMs`), and the panel
    // takes none for as long after the question goes (_shieldClick).
    const QUESTION_ID = 'fcc-audit-done-question';
    const PARK_TIMEOUT_MS = 120000;     // about six Spoolman calls a spool
    const _spools = (n) => `${n} spool${n === 1 ? '' : 's'}`;

    // Each list's spools as the panel's tiles (Derek, 2026-11-03: "display the spools like
    // we did in the audit window, that way a visual scan of the list isn't a tedious list
    // of spools with very little context, but more of a vibrant list of data where an out
    // of place color might spark a memory and help someone catch a possible mistake"):
    // every one of them, never "and N more", the heading counting them. A tile is the
    // spool's colour, its name, its grams (and slot, as the panel's tile says it), and
    // where it comes from or why it stays (`where`). The rows carry their look (section
    // H, S1: from the rows stored at each scan). Not pressable, no QR.
    const _grams = (r) => (r.remaining_weight != null ? `${Math.round(r.remaining_weight)}g` : '');
    const _tiles = (heading, rows, tone, where, slot = false) => ({
        heading: `${heading} (${rows.length})`,
        tiles: true,
        tone,
        lines: rows.map((r) => ({
            text: _spoolName(r),
            detail: `${_grams(r)}${slot && r.slot ? `${_grams(r) ? ' ' : ''}(slot ${r.slot})` : ''}`,
            where: where(r),
            color: r.color,
            color_direction: r.color_direction,
        })),
    });

    // Where the keyboard goes when the question leaves: its window has gone with it.
    const _focusDone = () => {
        const done = _handle && _handle.element.querySelector('#fcc-audit-panel-done');
        if (done && done.focus) done.focus();
    };

    // `show`: a hidden panel comes back for this, or nothing on screen would say the
    // audit still runs.
    const _parkRefused = (msg, show = true) => {
        if (show) window.openAuditPanel();
        _auditSay(msg);
    };

    const _parkAnswered = (res) => {
        if (res && res.audit_ended) {
            window.noteAuditEnded(res.audit_ended, { quiet: true });
            document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
            // The report itself, where the panel was (Derek, 2026-11-03): after the panel
            // has gone (noteAuditEnded), so it is the window on top.
            const shown = !!(res.report && window.openAuditReport(res.report, { after: true }));
            // `success` is false only when a write failed: its 7 s warning goes, and its
            // layer is under the window, so the window's notice line says it too. A Yes
            // that moved every spool raises no toast when the window opens: the window
            // says what it did, and the toast peeked out around a short report (Derek's
            // look of 2026-11-04). With no window (an answer with no report), the toast
            // says it, as before.
            if (!res.success) showToast(res.msg, 'warning', 7000);
            else if (!shown) showToast(res.msg, 'success', 4000);
            // The window lists each spool: its line drops the toast's pointer to the Activity
            // Log (`report_msg`; review 3, R3S-7). An older server sends `msg` alone.
            if (shown && !res.success && res.msg && window.auditReportNotice) window.auditReportNotice(res.report_msg || res.msg);
            return;
        }
        // Refused, with nothing written. The audit runs on (a failed read, a second
        // Yes), or has gone (`stale`), which the heartbeat says with its reason.
        const stale = !!(res && res.stale);
        _parkRefused((res && res.msg) || "The park didn't go through, so nothing was moved. Press Done again.", !stale);
        if (stale && typeof updateLogState === 'function') updateLogState(true);
    };

    // Past the timeout the server may well still be parking. Only for no answer: an
    // exception after a park landed must not read as this.
    const _parkNotAnswered = () => {
        const msg = "FCC didn't answer, so the park may not have finished. Check the Activity Log before moving anything.";
        _parkRefused(msg);
        if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
        if (typeof updateLogState === 'function') updateLogState(true);
    };

    // The Yes. Every id the question counted, not only the lines it drew: the spools it
    // parks, and (Derek's C, 2026-11-03, for his look) the Extras it files here, sent
    // as `file_ids` ([] files nothing) with where the question showed each,
    // `file_where` ({id: where}): a move sends what its screen showed, so one that
    // moved while the question sat open stays where it went.
    const _park = (auditId, ids, fileIds = [], fileWhere = {}) => {
        const words = (ids.length && fileIds.length) ? `Parking ${_spools(ids.length)} and filing ${fileIds.length}…`
            : (fileIds.length ? `Filing ${_spools(fileIds.length)}…` : `Parking ${_spools(ids.length)}…`);
        setProcessing(true, { label: `⏳ ${words}` });      // under the panel, when it is up
        // On Done, so a refusal hands the keyboard back there (auditPanelBusy).
        _focusDone();
        window.auditPanelBusy(true);
        window.auditPanelNotice(words);
        // Counted out, or the panel's 2 s poll sees the audit gone first and warns.
        window.auditRequestOut(1);
        window.fetchT('/api/audit/park', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audit_id: auditId, ids, file_ids: fileIds, file_where: fileWhere,
                today: window.fccLocalDay() }),
        }, PARK_TIMEOUT_MS)
            .then(r => r.json())
            .then(_parkAnswered, _parkNotAnswered)
            .catch(e => console.error(e))
            .finally(() => { setProcessing(false); window.auditRequestOut(-1); });
    };

    // What the question says, and its Yes: the park's words as they were; with Extras to
    // file (Derek's C, 2026-11-03, for his look; `file`, and `file_note` for a box whose
    // slot FCC never guesses) the filing's, or both. It names the audited place, never
    // "here" (Derek, 2026-11-03: a question is read away from the panel, and "File #64
    // here?" read as 64 spools): "File #57 in LR-MDB-1?".
    const _doneWords = (res, park, file) => {
        const n = park.length;
        const m = file.length;
        const place = String(res.location == null ? '' : res.location);
        // Counted against every spool not scanned (review 3, R3S-3: "1 of 16 found. The 12 not
        // scanned go to Unknown" read as 12 not scanned, with 15): the ones that stay (moved
        // off, deleted, in the scan buffer, on a head) are under Left where they are.
        const unscanned = Math.max(n, Number(res.expected || 0) - Number(res.found || 0));
        const parks = !n ? '' : ` ${n < unscanned ? `${n} of the ${unscanned} not scanned ${n === 1 ? 'goes' : 'go'}`
            : (n === 1 ? 'The one not scanned goes' : `The ${n} not scanned go`)} to Unknown, to find or clear later.`;
        const files = m ? ` ${m === 1 ? `The one found in ${place} that FCC had elsewhere is` : `The ${m} found in ${place} that FCC had elsewhere are`}`
            + ` filed there.${res.file_note ? ` ${res.file_note}` : ''}` : '';
        // A place FCC had nothing filed at asks only to file: "0 of 0 found" said
        // nothing (review of 7e3720f, R-4), so the tally is left out.
        const tally = res.expected ? `${res.found} of ${res.expected} found at ${place}.` : '';
        const msg = `${tally}${parks}${files} Undo Last Move puts ${n + m === 1 ? 'it' : 'them'} back.`.trim();
        if (!m) {
            return { msg, title: `Park ${_spools(n)} at Unknown?`, yes: n === 1 ? 'Park it' : 'Park them',
                verb: n === 1 ? 'parks it' : 'parks them', caption: 'Scan to Park' };
        }
        if (!n) {
            return { msg, title: m === 1 ? `File #${Number(file[0].id)} in ${place}?` : `File ${_spools(m)} in ${place}?`,
                yes: m === 1 ? 'File it' : 'File them', verb: m === 1 ? 'files it' : 'files them',
                caption: 'Scan to File' };
        }
        return { msg, title: `Park ${n} at Unknown and file ${m} in ${place}?`, yes: 'Do both', verb: 'does both',
            caption: 'Scan to Do both' };
    };

    // `res`: the route's audit_done_question answer. Nothing has moved yet.
    window.askAuditDone = (res) => {
        // Find would sit between the question and the panel, and Back goes to the panel.
        window.closeAuditFindForScan();
        const park = Array.isArray(res.park) ? res.park : [];
        const stays = Array.isArray(res.stays) ? res.stays : [];
        const file = Array.isArray(res.file) ? res.file : [];
        const words = _doneWords(res, park, file);
        const place = String(res.location == null ? '' : res.location);
        const sections = [];
        // Its slot as the panel's tile says it ("500g (slot 2)"): Done parks it from there. Named
        // for what Done does with them (review 3, R3S-3): "Not scanned (12)" read as every spool
        // not scanned, under a tally that counted 15.
        if (park.length) sections.push(_tiles('Not scanned, to park at Unknown', park, 'missing', () => '', true));
        // Where FCC has each now: Done moves it to the audited place.
        if (file.length) {
            sections.push(_tiles(`Found in ${place}, FCC had ${file.length === 1 ? 'it' : 'them'} elsewhere`, file, 'extra',
                (r) => (r.where ? `from ${r.where}` : '')));
        }
        // `why`, not `where`: a deleted spool is nowhere.
        if (stays.length) {
            sections.push(_tiles(stays.length === 1 ? 'Left where it is' : 'Left where they are', stays, 'stay',
                (r) => String(r.why == null ? '' : r.why)));
        }
        if (res.audit_id != null) state.auditId = res.audit_id;
        const asked = window.confirmActivePrint({
            title: words.title,
            msg: words.msg,
            sections,
            printing: true,
            ids: { overlay: QUESTION_ID },
            loadLabel: words.yes,
            loadVerb: words.verb,
            loadCaption: words.caption,
            cancelLabel: 'Back to the audit',
            cancelVerb: 'goes back',
            cancelCaption: 'Scan to go back',
            armAfterMs: DOUBLE_PRESS_MS,
            // The place it names stays whole ("SHELF-2- / R3" on a phone).
            keepWhole: true,
            onConfirm: () => {
                _question = null;
                _questionClosedAt = Date.now();
                _park(res.audit_id, park.map(r => r.id), file.map(r => r.id),
                    Object.fromEntries(file.map(r => [String(r.id), String(r.where || '')])));
            },
            onCancel: (info) => {
                // Closed with the panel, or replaced by a newer Done's question
                // (confirmActivePrint logged that): nobody answered this one.
                const answered = _question === asked && !(info && info.superseded);
                if (_question === asked) _question = null;
                if (!answered) return;
                _questionClosedAt = Date.now();
                showToast('Back to the audit: nothing moved.', 'info', 4000);
                if (window.logClientEvent) window.logClientEvent(`ℹ️ Done's question: back to the audit of ${window.escHtml(res.location)}, nothing moved`, 'INFO');
                // Hidden, the words on the button still have to be true. A panel just
                // brought back has no Done yet: its body comes with the first poll.
                _focusDoneNext = !_handle;
                window.openAuditPanel();
                if (!_focusDoneNext) _focusDone();
            },
        });
        _question = asked;
        // Opened under the pointer that pressed Done: its second click lands on the
        // question, where a mousedown off the buttons takes the keyboard from Back.
        _shieldPage();
    };

    // --- The audit's report window (Derek, 2026-11-03, section H) -------------------
    // "a window right after Done's Yes, and a 📝 Read the report button on the report's
    // Activity Log line": the server's report as data (section H, S3: each spool once,
    // under what the end did with it), each spool a colour tile as in Done's question
    // (window.fccSpoolTileHtml). It opens where the panel was after a Done this page ended
    // (the park's answer, or a Done with nothing to ask), and from the report's line
    // (GET /api/audit/report). Never after a Cancel or an idle end: their lines' button
    // opens theirs. A mountOverlay at the panel's tier, Tab kept inside it, Escape and
    // Close closing it, the keyboard on Close. It takes no scan: a scan read while it is
    // up goes to processScan as usual and closes it (the scan's toast or dialog would sit
    // under it), but for a scanner's second read of the CMD:DONE that ended the audit.
    const REPORT_ID = 'fcc-audit-report';
    // Where it can be read again: its line in the Activity Log, for as long as the log keeps
    // it, and the 📡 pill's list, which shows the same line, only while the pill is up (it
    // shows while an entry is unread, and hides once its list has been read; review 3, R3S-6).
    const AUDIT_REPORT_AGAIN = 'Its line in the Activity Log has a 📝 Read the report button that opens this window '
        + "again, and so does the 📡 pill's list while the pill shows.";
    const REPORT_TIMEOUT_MS = 8000;     // the route reads no Spoolman
    const REPORT_SECOND_READ_MS = 1500; // processScan's LOC_REPEAT_MS: a scanner's double read
    let _report = null;
    let _reportFit = null;
    let _reportAfterDoneAt = 0;
    let _reportAskedAt = 0;
    // When the window last closed: the keyboard goes back to the 📝 it was asked from, and a
    // double Enter or Space on Close pressed that and opened it again (review 3, R3-3).
    let _reportClosedAt = 0;
    let _reportOut = false;
    // Every scan processScan takes (closeAuditReportForScan): an answer to a 📝 press that a
    // scan has overtaken opens nothing (review 3, R3-5).
    let _reportScanSeq = 0;
    // Each kind of group (logic._audit_report_data): its icon (the report line's), its
    // tiles' look and what a tile says under its grams.
    const _at = (r) => (r.where ? `📍 ${r.where}` : '');
    const REPORT_KINDS = {
        parked: { icon: '❓', tone: 'missing', where: (r) => (r.where ? `from ${r.where}` : '') },
        filed: { icon: '📥', tone: 'extra', where: (r) => (r.where ? `from ${r.where}` : '') },
        stayed: { icon: '📌', tone: 'stay', where: (r) => r.why || _at(r) },
        failed: { icon: '🛑', tone: 'failed', where: (r) => r.why || _at(r) },
        missing: { icon: '❌', tone: 'missing', where: (r) => r.why || _at(r) },
        extra: { icon: '⚠️', tone: 'extra', where: (r) => r.why || _at(r) },
        trail: { icon: '🔗', tone: 'trail', where: (r) => (r.where ? `loaded on ${r.where}` : '') },
        needs_label: { icon: '🏷️', tone: 'found', where: _at },
    };

    // A row at the audited place itself (Derek's look of 2026-11-04: every parked tile of
    // SHELF-3-R1's report read "from SHELF-3-R1", which the title already says): its where
    // goes, and its slot, when it has one, goes on its small line as the panel's tile and
    // Done's question say it ("500g (slot 2)"). null: a row somewhere else, which keeps its
    // line; '': the place itself; else the slot. `where` is logic.audit_where's ("LR-MDB-1
    // slot 2"), compared without case.
    const _atThePlace = (where, place) => {
        const w = String(where == null ? '' : where).trim();
        const p = String(place == null ? '' : place).trim();
        if (!w || !p) return null;
        if (w.toUpperCase() === p.toUpperCase()) return '';
        const head = `${p} slot `;
        return w.toUpperCase().startsWith(head.toUpperCase()) ? w.slice(head.length).trim() : null;
    };

    // A place id stays whole in the title and the group headings (review 3, R3-6: on a phone the
    // title read "📝 Audit Report: SHELF-" / "2-R3", the complaint T4 fixed in the question just
    // before it), as window.fccKeepWhole keeps a button's; _fitReport lets an id longer than
    // the line itself break at its hyphens again.
    const _keepWhole = (text) => (typeof window.fccKeepWhole === 'function'
        ? window.fccKeepWhole(_escapeHtml(text)) : _escapeHtml(text));

    const _reportHtml = (rep, after) => {
        const place = String(rep.place == null ? '' : rep.place);
        const groups = (Array.isArray(rep.groups) ? rep.groups : []).filter(g => g && Array.isArray(g.rows) && g.rows.length);
        const count = (kind) => groups.filter(g => g.kind === kind).reduce((n, g) => n + g.rows.length, 0);
        const lists = groups.map((g) => {
            const kind = REPORT_KINDS[g.kind] || { icon: '', tone: '', where: (r) => r.why || _at(r) };
            const tiles = g.rows.map((r) => {
                const slot = _atThePlace(r.where, place);
                const grams = _grams(r);
                return { r, slot, detail: slot ? `${grams}${grams ? ' ' : ''}(slot ${slot})` : grams };
            }).map(({ r, slot, detail }) => window.fccSpoolTileHtml({
                text: _spoolName(r),
                detail,
                where: kind.where(slot === null ? r : Object.assign({}, r, { where: '' })),
                // Marked in this audit, wherever it is: the group of the marked holds only
                // the ones no other group lists. Its words say the audit marked it (review 3,
                // R3S-5): the panel's tile says "needs a label" for any flag up, one raised
                // before the audit too, which the report doesn't list.
                tag: (r.needs_label && g.kind !== 'needs_label') ? '🏷️ marked as needing a label' : '',
                color: r.color,
                color_direction: r.color_direction,
            }, kind.tone)).join('');
            return `<section class="fcc-audit-report-group" data-report-kind="${_escapeHtml(g.kind)}">`
                + `<div class="fcc-audit-report-head">${_keepWhole(`${kind.icon ? `${kind.icon} ` : ''}${g.title} (${g.rows.length})`)}</div>`
                + `<div class="fcc-spool-tiles">${tiles}</div></section>`;
        }).join('');
        const empty = !place ? 'No place was scanned in this audit, so there are no spools to list.'
            : (rep.perfect ? `Every spool FCC had at ${place} was found.` : 'There are no spools to list.');
        // Right after the Yes: where to read it again, and what Undo puts back.
        const parked = count('parked');
        const filed = count('filed');
        const undone = (parked && filed) ? 'the parked and filed spools'
            : (parked ? (parked === 1 ? 'the parked spool' : 'the parked spools')
                : (filed ? (filed === 1 ? 'the filed spool' : 'the filed spools') : ''));
        // Where to read it again: the Activity Log, and the list the 📡 log pill opens, which
        // is bigger on a phone (Derek's look of 2026-11-04), while the pill shows (R3S-6).
        const foot = !after ? '' : [
            place ? AUDIT_REPORT_AGAIN : '',
            undone ? `Undo Last Move puts ${undone} back.` : '',
        ].filter(Boolean).join(' ');
        return `
            <div class="fcc-audit-report-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-audit-report-title">
                <div class="fcc-audit-report-top">
                    <div id="fcc-audit-report-title">${_keepWhole(place ? `📝 Audit Report: ${place}` : '📝 Audit Report')}</div>
                    <button type="button" id="fcc-audit-report-close" class="btn btn-sm btn-outline-light">Close</button>
                </div>
                <div class="fcc-audit-report-summary">${_escapeHtml(rep.summary || '')}</div>
                ${rep.ended ? `<div class="fcc-audit-report-ended">${_escapeHtml(rep.ended)}</div>` : ''}
                <div id="fcc-audit-report-notice" class="fcc-audit-report-notice" role="alert" style="display:none;"></div>
                <div class="fcc-audit-report-body" tabindex="-1" role="region" aria-label="Each spool, by what the audit did with it">
                    ${lists || `<div class="fcc-audit-report-empty">${_escapeHtml(empty)}</div>`}
                </div>
                ${foot ? `<div class="fcc-audit-report-foot">${_escapeHtml(foot)}</div>` : ''}
            </div>`;
    };

    // Taller than the window, its body scrolls and the title, summary and Close stay
    // (.fcc-audit-report-scroll); only then, as a question (fccFitQuestion: a scroller
    // draws its text without ClearType), and then the body is a stop for Tab, whose arrow
    // and page keys scroll it.
    const _fitReport = (panel) => {
        if (!panel || !panel.isConnected || typeof panel.getBoundingClientRect !== 'function') return;
        // An id kept whole that is wider than its line breaks at its hyphens again
        // (.fcc-keep-whole-off), as fccFitQuestion and _fitConfirmMsg let it: nothing runs off.
        panel.classList.remove('fcc-keep-whole-off');
        const wide = Array.from(panel.querySelectorAll('#fcc-audit-report-title, .fcc-audit-report-head'))
            .some(el => el.querySelector('.fcc-keep-whole') && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1);
        if (wide) panel.classList.add('fcc-keep-whole-off');
        panel.classList.remove('fcc-audit-report-scroll');
        const scroll = panel.getBoundingClientRect().height > (window.innerHeight || 0) - 16 + 0.5;
        if (scroll) panel.classList.add('fcc-audit-report-scroll');
        const body = panel.querySelector('.fcc-audit-report-body');
        if (body) body.tabIndex = scroll ? 0 : -1;
    };
    document.addEventListener('fcc:text-size', () => { if (_report) _fitReport(_report.panel); });

    // `opts.after`: right after the Done this page ended (the Yes, or a Done with nothing
    // to ask); `opts.opener`: the button it was asked for from, which the keyboard goes
    // back to.
    window.openAuditReport = (rep, opts = {}) => {
        if (!rep || typeof window.mountOverlay !== 'function' || typeof window.fccSpoolTileHtml !== 'function') return null;
        window.closeAuditReport();
        const after = !!opts.after;
        const handle = window.mountOverlay({
            id: REPORT_ID,
            content: _reportHtml(rep, after),
            tier: 'standard',
            backdrop: true,
            trapTab: true,
            initialFocus: '#fcc-audit-report-close',
            onEscape: () => window.closeAuditReport(),
        });
        _report = handle;
        handle._opener = opts.opener || null;
        const close = handle.element.querySelector('#fcc-audit-report-close');
        if (close) close.onclick = () => window.closeAuditReport();
        const panel = handle.element.querySelector('.fcc-audit-report-panel');
        _fitReport(panel);
        if (typeof requestAnimationFrame === 'function') {
            requestAnimationFrame(() => requestAnimationFrame(() => { if (_report === handle) _fitReport(panel); }));
        }
        if (typeof window.addEventListener === 'function') {
            _reportFit = () => _fitReport(panel);
            window.addEventListener('resize', _reportFit);
        }
        _reportAfterDoneAt = after ? Date.now() : 0;
        // Opened under the pointer that asked for it (the Yes, Done, the line's button):
        // the second press of a double click reaches nothing, Close included.
        _shieldPage();
        return handle;
    };

    window.closeAuditReport = () => {
        if (!_report) return;
        // Gone from under the pointer, as the panel's Hide is (review 3, R3-1): the second
        // press of a double click on Close landed on the dashboard beneath it (a Printer
        // Status head opened the Location Manager, the title bar's 🛒 Queue its window).
        // Armed only while a pointer press is under DOUBLE_PRESS_MS old, so Escape, Enter
        // and a scan's close are as they were.
        _shieldPage();
        _reportClosedAt = Date.now();
        const handle = _report;
        _report = null;
        if (_reportFit && typeof window.removeEventListener === 'function') window.removeEventListener('resize', _reportFit);
        _reportFit = null;
        try { handle.cleanup(); } catch (_) { /* noop */ }
        // Back to the button it was asked for from, when nothing else has the keyboard: that
        // line's 📝 as the log draws it now, when a redraw while the window was up replaced
        // the one it was asked from (review 3: the keyboard fell to the page). The 📡 pill's
        // list first: open, it lies over the log, and the window was opened from it.
        let opener = handle._opener;
        if (opener && !opener.isConnected && opener.dataset && opener.dataset.auditReport) {
            const id = opener.dataset.auditReport;
            const find = (sel) => Array.from(document.querySelectorAll(sel)).find((b) => b.dataset.auditReport === id);
            opener = find('#fcc-log-pill-overlay .fcc-audit-report-open') || find('#live-logs .fcc-audit-report-open') || null;
        }
        const a = document.activeElement;
        if (opener && opener.isConnected && (!a || a === document.body) && opener.focus) {
            try { opener.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        }
    };

    window.isAuditReportOpen = () => !!_report;

    // What a scan's refusal says, on the window itself, beside its toast, as the panel's
    // notice does (auditPanelNotice hands it here while only this window is up): the toast
    // layer (z 11000) is under it. The one scan that can be refused with it up is one read
    // while the park was out and dropped once the audit was over (auditScanOutlived); any
    // scan processScan takes closes the window first. '' clears it.
    window.auditReportNotice = (msg) => {
        if (!_report) return;
        const el = _report.element.querySelector('#fcc-audit-report-notice');
        if (!el) return;
        el.textContent = msg || '';
        el.style.display = msg ? 'block' : 'none';
        // A line more: the window may not fit any more.
        _fitReport(_report.element.querySelector('.fcc-audit-report-panel'));
    };

    // processScan, for every scan: the window goes and the scan goes on. A scanner's second
    // read of the CMD:DONE that ended the audit (`at`: when it was read) leaves it up.
    window.closeAuditReportForScan = (upper, at) => {
        _reportScanSeq += 1;
        if (!_report) return;
        if (upper === 'CMD:DONE' && _reportAfterDoneAt && (at || Date.now()) - _reportAfterDoneAt < REPORT_SECOND_READ_MS) return;
        window.closeAuditReport();
    };

    // What is on screen, for a 📝 press's answer to be checked against: the overlay on top
    // (or none), a gating dialog, the Bootstrap windows up.
    const _reportScene = () => {
        const mounted = Array.from(document.querySelectorAll('[data-overlay-mount="1"]'));
        return {
            top: (window.isTopOverlay && mounted.find(el => window.isTopOverlay(el))) || null,
            gating: state.activeModal || null,
            windows: Array.from(document.querySelectorAll('.modal.show, .offcanvas.show')).map(el => el.id),
        };
    };
    // The answer came to a screen that has changed since the press (review 3, R3-5): a scan
    // read meanwhile (processScan closes the window for a scan, so a window that wasn't open
    // yet mustn't open after it), a dialog it opened ("Clear entire Buffer?", whose scans the
    // window would then hide), or any other window or overlay. The report over it would sit
    // on top while scans still went to what is under it.
    const _reportSceneChanged = (was, seq) => {
        if (_reportScanSeq !== seq) return true;
        const now = _reportScene();
        return now.top !== was.top || now.gating !== was.gating
            || now.windows.some(id => !was.windows.includes(id));
    };

    // The 📝 Read the report button the server puts in the report's line (section H, S3):
    // one delegated click, for Live Activity (redrawn by innerHTML, frozen while paused)
    // and the log pill's window, which draw the same line. A double press asks once.
    const _askReport = (btn) => {
        const now = Date.now();
        // A double press asks once, and so does a double Enter on Close, whose second
        // lands on this button (the keyboard goes back to it), as Find's 🔎 does.
        if (_reportOut || now - _reportAskedAt < DOUBLE_PRESS_MS || now - _reportClosedAt < DOUBLE_PRESS_MS) return;
        _reportAskedAt = now;
        _reportOut = true;
        const id = String((btn.dataset && btn.dataset.auditReport) || '');
        // Asked from the 📡 pill's list, the list is on top, and a toast's layer is under it:
        // the list says it too (review 3, R3-4).
        const say = (msg) => {
            showToast(msg, 'warning', 7000);
            if (btn.closest('#fcc-log-pill-overlay') && window.logPillNotice) window.logPillNotice(msg);
        };
        if (btn.closest('#fcc-log-pill-overlay') && window.logPillNotice) window.logPillNotice('');
        const scene = _reportScene();
        const seq = _reportScanSeq;
        window.fetchT(`/api/audit/report?id=${encodeURIComponent(id)}`, {}, REPORT_TIMEOUT_MS)
            .then(r => r.json())
            .then((res) => {
                if (res && res.success && res.report) {
                    if (_reportSceneChanged(scene, seq)) {
                        showToast("The report didn't open: the screen changed while FCC answered. "
                            + 'Press 📝 Read the report again to see it.', 'info', 4000);
                        if (window.logClientEvent) window.logClientEvent(
                            "ℹ️ An audit report wasn't opened: a scan or a window came up while FCC answered", 'INFO');
                        return;
                    }
                    window.openAuditReport(res.report, { opener: btn });
                    return;
                }
                // FCC no longer has it (it keeps the last 10, a restart clears them): the
                // server's words, which point to the line's own words.
                say((res && res.msg) || "FCC couldn't show that report.");
            }, () => say("FCC didn't answer, so the report couldn't be shown. Try again in a moment."))
            .catch(e => console.error(e))
            .finally(() => { _reportOut = false; });
    };
    document.addEventListener('click', (e) => {
        const t = e.target && e.target.closest ? e.target : null;
        const btn = t ? t.closest('.fcc-audit-report-open') : null;
        if (!btn || !btn.closest('#live-logs, #fcc-log-pill-overlay')) return;
        e.preventDefault();
        _askReport(btn);
    });
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
// The last scan processScan took, or the queue dropped as one an audit outlived: {text
// (upper case), at (when it was read)}. auditScanOutlived reads a queued scan of the same
// text read within LOC_REPEAT_MS of it as a scanner's double read.
let _lastScanRead = null;
window._fccLastLocScan = window._fccLastLocScan || null;
const _isLocRepeat = (key, capturedAt) => {
    const last = window._fccLastLocScan;
    if (!key.startsWith('LOC:') || !last || last.text !== key) return false;
    const at = capturedAt || Date.now();
    return last.doneAt == null || at < last.doneAt + LOC_REPEAT_MS;
};
// A label the slot picker held while it loaded and then refused (or never
// loaded) was no read either: scanned again, it acts (Group 57 review, round
// 9). `label`: as the picker held it (window.lastScanLabel's).
window.unreadLocScan = (label) => {
    const last = window._fccLastLocScan;
    if (last && last.text === String(label == null ? '' : label).trim().toUpperCase()) window._fccLastLocScan = null;
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

// When a bare CMD:CANCEL last closed an open question (processScan).
let _questionCancelledAt = 0;

// --- SCAN ROUTER ---
// `weighRead`: the weigh-out list's mark for this scan, made as it was read
// when the scan accumulator queued it behind another (weighOutScanStart); it
// is ended by the queue if the scan never goes out (Group 57 review, round 9).
// `auditOf`: the audit the queue's scan was read for, stamped as it was read
// (scripts.html; left out, a scan read now). It goes out as `audit_seen`.
const processScan = (text, source = 'keyboard', capturedAt = null, weighRead = null, auditOf = undefined) => {
    // Blanks around a scan are nobody's (the server strips them too); kept,
    // the exact matches below missed (Group 57 review, round 5).
    text = String(text == null ? '' : text).trim();
    if (!text) return;
    const upper = text.toUpperCase();
    const locKey = upper.trim();
    // The Activity Log draws its lines as HTML: a scan's text in one is escaped
    // (Group 61 review).
    const escLog = window.escHtml || ((s) => s);
    if (_isLocRepeat(locKey, capturedAt)) {
        showToast(`ℹ️ Ignored a second read of ${String(text).trim()}`, 'info', 3500);
        if (window.logClientEvent) window.logClientEvent(
            `ℹ️ Scan "${escLog(String(text).trim())}" ignored: the same label was read twice within ${LOC_REPEAT_MS / 1000} s`, 'INFO');
        return;
    }
    _lastScanRead = { text: locKey, at: capturedAt || Date.now() };
    // Answered at once unless it reaches the server below (every early return
    // here is an answer); in flight from the request until its answer.
    const locBefore = window._fccLastLocScan;
    const locScan = locKey.startsWith('LOC:') ? (window._fccLastLocScan = { text: locKey, doneAt: Date.now() }) : null;
    const locInFlight = () => { if (locScan) locScan.doneAt = null; };
    const locDone = () => { if (locScan && locScan.doneAt == null) locScan.doneAt = Date.now(); };
    // A read the open question or the slot picker took by its last label (a key
    // left in front of it, "qLOC:…", or another label glued before it,
    // "LOC:A…LOC:B:SLOT:2") counts as that label read, so its second read is
    // dropped too (Group 57 review, rounds 7 and 8: it acted again).
    const routed = () => {
        const last = window.lastScanLabel ? window.lastScanLabel(locKey) : locKey;
        if (last.startsWith('LOC:') && last !== locKey) window._fccLastLocScan = { text: last, doneAt: Date.now() };
        else locDone();
    };
    // A read they refused is no read: the label scanned again once they have
    // closed acts (round 8: it was dropped as a second read for 1.5 s).
    const unread = () => { if (locScan && window._fccLastLocScan === locScan) window._fccLastLocScan = locBefore; };
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
        // At the end of the text, as routeConfirmScan reads its QRs: a stray
        // key in front refused the question's own Cancel (round 5).
        if (/CMD:CANCEL(:[A-Z0-9_-]+)?$/.test(upper)) { openQuestion.cancel(); _questionCancelledAt = Date.now(); return; }
        // A question whose answers are labels (Group 40.5's "Record it as coming
        // from…": a feed slot's label picks it) routes them itself; 'refused'
        // (a held slot, round 9) is no read of the label.
        const answered = typeof openQuestion.route === 'function' ? openQuestion.route(text, source) : false;
        if (answered) { if (answered === 'refused') unread(); else routed(); return; }
        const why = openQuestion.hint || 'Answer the question on screen first: Load it instead, Just store it, or Cancel';
        showToast(why, 'warning', 7000);
        if (openQuestion.flash) openQuestion.flash(`${why}. (Ignored: ${text})`);
        if (window.logClientEvent) window.logClientEvent(
            `⚠️ Scan "${escLog(text)}" ignored: "${escLog(openQuestion.title)}" is still open`, 'WARNING');
        unread();
        return;
    }
    // Group 40.1: an open slot picker claims every scan next. A choice's label
    // picks it, CMD:CANCEL cancels, anything else is refused with a warning, so
    // a scan never acts behind the picker (slot_picker.js; 'refused' says so).
    const picker = window.routePickerScan ? window.routePickerScan(text) : false;
    if (picker) { if (picker === 'refused') unread(); else routed(); return; }
    // A session-scoped CMD:CONFIRM:<sid> that routeConfirmScan didn't claim
    // belongs to a dialog that has already closed. Never let it fall through to
    // the substring-matching routes below and answer whatever unrelated dialog
    // is up now (2026-09-12 review). A stale CMD:CANCEL:<sid> still falls
    // through: cancelling is safe, outside a session (below). A stale CMD:STORE:<sid> (Group 40.3's
    // "Just store it") is a choice too, so it is stopped the same way. Read
    // anywhere in the text: a stray key in front never lets one through (Group
    // 57 review, round 5), and neither does a later scan glued after it with a
    // Space in it (round 6; a live one alone was answered above, by
    // routeConfirmScan). A live dialog's own QR with a scan glued after it is
    // stopped too, and said so: it was called a closed dialog's (round 7), and
    // with no Space between them still was (round 8: its id read on into the
    // next scan's letters).
    if (/CMD:(CONFIRM|STORE):\S/.test(upper)) {
        const live = Object.keys(window._fccActiveConfirms || {}).some((sid) =>
            upper.includes(`CMD:CONFIRM:${sid}`.toUpperCase()) || upper.includes(`CMD:STORE:${sid}`.toUpperCase()));
        showToast(live ? 'That confirm QR was read together with another scan — ignored: scan it on its own'
            : 'That confirm QR belongs to a dialog that has closed — ignored', 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(live
            ? `⚠️ Confirm QR read together with another scan ("${escLog(text)}") — ignored`
            : '⚠️ Stale confirm QR scanned (its dialog had closed) — ignored', 'WARNING');
        return;
    }
    // Group 58: a stale CMD:CANCEL:<sid> is safe everywhere but in a session: "Scan to
    // go back" read twice cancelled the whole audit, every scan in it, until the
    // server's gate stopped it too (logic.is_closed_dialogs_cancel; here it says so in
    // a word, and asks nothing of the server). A bare CMD:CANCEL read twice did the
    // same, its first read having only closed a question or a gating dialog, and the
    // server can't tell that one: it is the session's own Cancel. It can be meant, so
    // it goes after the window a double read takes (LOC_REPEAT_MS).
    const staleCancel = /CMD:CANCEL:\S/.test(upper);
    const secondCancel = upper === 'CMD:CANCEL' && (capturedAt || Date.now()) - _questionCancelledAt < LOC_REPEAT_MS;
    if ((staleCancel || secondCancel) && (state.auditActive || state.bulkMoveActive)) {
        const said = staleCancel ? 'That cancel QR belongs to a dialog that has closed — ignored' : 'Ignored a second read of CMD:CANCEL';
        showToast(said, 'info', 4000);
        if (window.logClientEvent) window.logClientEvent(`ℹ️ Scan "${escLog(text)}" ignored: ${said}`, 'INFO');
        return;
    }
    // Group 58 (Derek, 2026-11-03): the audit's report window takes no scan. It goes, and
    // the scan goes on, its answer on top (a toast, or a dialog such as Undo's, would sit
    // under it). Below the guards above, so a closed dialog's QR read again leaves it up,
    // and so does a scanner's second read of the CMD:DONE that ended the audit.
    if (window.closeAuditReportForScan) window.closeAuditReportForScan(upper, capturedAt);

    // Group 58: the commands below never reach the server's audit gate.
    const auditRefusal = state.auditActive ? _auditCommandRefusal(upper) : '';
    if (auditRefusal) {
        _auditSay(auditRefusal, 'warning');
        if (window.logClientEvent) window.logClientEvent(`⚠️ Scan "${escLog(text)}" ignored: ${escLog(auditRefusal)}`, 'WARNING');
        return;
    }
    if (upper === 'CMD:AUDIT') { toggleAudit(); return; }
    // L298 Phase 2 — same client-side shape as CMD:AUDIT: arm when idle, show
    // the panel when running. Location scans + CMD:DONE / CMD:CANCEL are NOT
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
    // Group 58 review: the audit's panel (z 20000) covers a gating dialog (z 1100), so
    // a scan the dialog would swallow without a word is said on the panel. With the
    // panel hidden the dialog is on screen, and says it all itself. CONFIRM and CANCEL
    // still reach it. Its CANCEL counts as a question's, or a second read of it, with
    // no dialog left to take it, would be sent on and end the audit.
    if ((state.activeModal === 'safety' || state.activeModal === 'confirm')
        && !upper.includes('CONFIRM') && !upper.includes('CANCEL')
        && window.isAuditPanelOpen && window.isAuditPanelOpen()) {
        _auditDialogBehind();
        if (window.logClientEvent) window.logClientEvent(`⚠️ Scan "${escLog(text)}" ignored: a dialog behind the audit panel is still open`, 'WARNING');
        return;
    }
    if (state.activeModal && upper.includes('CANCEL')) _questionCancelledAt = Date.now();
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
    // The weigh-out list, open: where the person's keys were as the scan was
    // read (now, or when the scan accumulator queued it: weighRead). A spool
    // the answer names takes the focus, with what was typed meanwhile, and
    // until the answer Enter saves nothing there (Group 57 review, rounds 7 to
    // 9; inv_weigh_out.js).
    const weighFrom = weighRead || (window.weighOutScanStart ? window.weighOutScanStart() : null);
    if (weighFrom) weighFrom.sent = true;
    // `confirmed_fed_heads` (Group 40.3): this page can show the "already
    // running another spool" question, so a slot scan is asked it instead of
    // being refused as a stale page (logic.stale_fed_refusal). Empty: the user
    // has confirmed nothing yet. A blind scan never names a feed (no
    // expected_feed), so a first slot scan stays prompt-free. `audit_ask` (Group
    // 58): this page can show Done's question; a page that doesn't say so hears
    // "reload" and nothing moves. `audit_seen`: the audit this scan was read for, left
    // out with none. If it has gone the server moves nothing: a page can believe in an
    // audit that ended under it, and a slot label would load the buffered spool.
    const scanSentAt = _auditClock();
    const auditSeen = auditOf !== undefined ? auditOf : (state.auditActive ? (state.auditId || true) : null);
    window.auditRequestOut(1);
    window.fetchT('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, source: source, confirmed_fed_heads: [], audit_ask: true, audit_seen: auditSeen || undefined }) })
        .then(r => r.json())
        .then(res => {
            locDone();
            setProcessing(false);
            // The server has no audit, and this page hasn't heard yet: ask why now.
            if (state.auditActive && _noAuditAnswered(res) && typeof updateLogState === 'function') updateLogState(true);
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
                // Group 58: a scan the audit took, which may have ended it.
                if (res.cmd === 'audit_scan') { _auditScanAnswer(res, scanSentAt); return; }
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
                // Group 58: a location label in an audit moves nothing, and this
                // one was scanned as part of an audit the server no longer has, or
                // answered after one started here. Left to run on, it would file
                // the whole buffer there, unasked.
                if (state.auditActive) {
                    const msg = `The audit has ended, so ${res.id} did nothing. Scan it again if you meant it.`;
                    showToast(msg, 'warning', 7000);
                    if (window.logClientEvent) window.logClientEvent(`⚠️ ${escLog(msg)}`, 'WARNING');
                    return;
                }
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
                // Group 58: an audit lost this spool, and here it is. Above the
                // modes: drop and eject act on the spool, and the person holding
                // it should still hear. The server has logged it.
                if (res.lost_msg) showToast(res.lost_msg, 'warning', 7000);
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
                // The weigh-out list's flow is "scan a spool, type its weight": its
                // box takes the focus (Group 57 review, round 7: the reading was
                // saved to the spool whose box kept it).
                if (window.weighOutTakeScan) window.weighOutTakeScan(res.id, weighFrom);
            } else if (res.type === 'ambiguous') {
                // Item 3.6 — backend found multiple spools attached to this
                // legacy id. Prompt the user to disambiguate. "Use selected"
                // re-routes through processScan with explicit ID:NNN so the
                // normal spool path runs (buffer add, etc.).
                // "Print new label" is handled inside the picker module.
                // Group 61: with the pick's own source. A pick from the list
                // is no label scan ('keyboard'): sent as 'barcode', it marked
                // the spool's label as printed and verified, and the spool
                // left the label backlog, though the picker is there because
                // that spool has no label of its own. A listed spool's own
                // label scanned while it is open keeps the scan's source.
                if (typeof window.showLegacySpoolPicker === 'function') {
                    window.showLegacySpoolPicker(res, {
                        onSelect: (sid, source) => { processScan(`ID:${sid}`, source || 'keyboard'); },
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
            } else if (res.type === 'audit_done_question') {
                // Done found spools to park, and nothing has moved. An audit
                // answered, so one runs, whatever this page believed: a Done
                // right after a reload lands before the first heartbeat.
                if (!state.auditActive && window._syncAuditSignal) window._syncAuditSignal({ audit_active: true }, { sentAt: scanSentAt });
                if (window.auditPanelNotice) window.auditPanelNotice('');
                window.askAuditDone(res);
            } else if (res.type === 'audit_gone') {
                // The audit this scan was read for has gone, and the server moved
                // nothing and logged it. The heartbeat asked for above says why.
                _auditSay(res.msg, 'warning');
            } else if (res.type === 'error') {
                showToast(res.msg, 'error', 7000);
                // The toast sits under the panel.
                if (state.auditActive && window.auditPanelNotice) window.auditPanelNotice(res.msg);
            }
        })
        .catch((e) => {
            locDone();
            setProcessing(false);
            console.error(e);
            showToast("Scan Error", "error", 7000);
            if (state.auditActive && window.auditPanelNotice) window.auditPanelNotice("That scan didn't go through: FCC didn't answer. Scan it again.");
        })
        .finally(() => {
            window.auditRequestOut(-1);
            if (window.weighOutScanDone) window.weighOutScanDone(weighFrom);
        });
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
    // Unknown is a list, never a place a spool comes from (Group 58): the engine
    // gives a spool leaving it no trail, so it is asked about like one from Unassigned.
    if (from && from !== 'UNKNOWN' && !(fromRow && headTypes.includes(fromRow.Type))) return Promise.resolve(undefined);
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
        // The box id and "slot N" kept whole on a phone (window.fccKeepWhole,
        // review 2026-10-22: "LR-MDB- / 1 slot 1" at Extra Large).
        const whole = window.fccKeepWhole || String;
        const optBtn = (f, i) => (f.free
            ? `<button type="button" class="btn btn-sm btn-info fcc-rs-opt" data-rs-i="${i}">${whole(esc(`${f.box} slot ${f.slot}`))}<small style="display:block;font-weight:400;">free</small></button>`
            : `<button type="button" class="btn btn-sm btn-outline-secondary fcc-rs-opt" data-rs-i="${i}" disabled aria-disabled="true">${whole(esc(`${f.box} slot ${f.slot}`))}<small style="display:block;font-weight:400;">holds #${esc(f.claimed_by)}</small></button>`);
        // QR codes under their buttons (Derek, 2026-10-22): the buttons a QR
        // stands for (the pre-selected slot, No box, Cancel) share a row with
        // their QRs, each QR under its own button. The slots with no QR (held
        // ones; every slot when several are free) sit on a line above them,
        // in feed order, so the keys still go slots, No box, Cancel.
        const slotsAbove = feeds.map((f, i) => (f === pre ? '' : optBtn(f, i))).join('');
        // What each answer does later (Derek, 2026-10-23: "Return and eject
        // send it back there" read "back where?"; the spool was never in the
        // slot). A slot: ↩️ Return and ⏏️ Eject put the spool in it. No box:
        // Return asks for a slot unless only one free slot feeds the head
        // (routes_bindings._return_plan), and Eject leaves it Unassigned
        // after its own question (logic._eject_destination, Group 41.8).
        const msg = `${esc(Who)} isn't coming from a box, so pick a slot feeding ${esc(head)}: ↩️ Return and ⏏️ Eject`
            + ' will put it in that slot later. With No box, Return will ask which slot (or use the only free one),'
            + ' and Eject will leave it Unassigned.';
        handle = window.mountOverlay({
            id: 'fcc-record-source',
            tier: 'confirm',
            host: host || undefined,
            onEscape: () => finish(null),
            content: `
                <div class="fcc-rs-panel" style="background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px; padding:18px min(22px, 4vw); max-width:38.75rem; text-align:center;">
                    <div class="fcc-rs-title" style="font-size:1.15em; font-weight:bold; margin-bottom:6px;">🔗 Record ${esc(who)} as coming from…</div>
                    <div class="fcc-rs-msg" style="color:#ffc; margin-bottom:12px; text-align:left;">${msg}</div>
                    <div class="fcc-rs-status" role="alert" style="display:none; margin-bottom:10px; padding:6px 10px; border-radius:6px; background:#4a3200; color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; text-align:left;"></div>
                    ${slotsAbove ? `<div class="fcc-rs-slots" style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-bottom:10px;">${slotsAbove}</div>` : ''}
                    <div class="fcc-rs-btns" style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">${pre ? optBtn(pre, feeds.indexOf(pre)) : ''}<button type="button" class="btn btn-sm btn-purple fcc-rs-none">No box</button><button type="button" class="btn btn-sm btn-dark fcc-rs-cancel">Cancel</button></div>
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
                if (order.includes(ae)) {
                    e.preventDefault(); e.stopPropagation();
                    if (window.clearScanBuffer) window.clearScanBuffer();   // a key a person left starts no scan
                    ae.click();
                }
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
            // cyan (btn-info), No box purple (btn-purple: its own colour since
            // 2026-10-23, grey was too close to Cancel's), Cancel dark (btn-dark).
            qr = window.attachConfirmQRs({
                host: panel,
                // Each QR under its own button (2026-10-22).
                alignTo: ov.querySelector('.fcc-rs-btns'),
                onConfirm: pre ? () => choose(pre) : () => finish(''),
                onStore: pre ? () => finish('') : undefined,
                onCancel: () => finish(null),
                confirmLabel: pre ? `Scan: ${pre.box} slot ${pre.slot}` : 'Scan: No box',
                storeLabel: 'Scan: No box',
                cancelLabel: 'Scan to go Back', theme: 'info',
                confirmTone: pre ? 'info' : 'purple', storeTone: 'purple', cancelTone: 'dark',
            });
        }
        // Fitted to the screen (window.fccFitQuestion): box ids whole where they
        // fit, and taller than the window it scrolls inside itself.
        if (window.fccFitQuestion) window.fccFitQuestion(ov.querySelector('.fcc-rs-panel') || handle.panel);
        // Scans are held off while it is open (processScan); a feed slot's label
        // picks that slot.
        question = {
            title: `Record ${who} as coming from…`,
            element: ov,
            hint: 'Answer the question on screen first: pick a slot (or scan its label), No box, or Cancel',
            cancel: () => finish(null),
            flash,
            route: (text) => {
                // Its last label: a key a person left in front never stops it
                // (Group 57 review, round 6), and a box id ending in LOC stays
                // whole (round 7; window.lastScanLabel, inv_core.js).
                const m = /^LOC:(.+?):SLOT:(\d+)$/.exec(window.lastScanLabel(text));
                if (!m) return false;
                const f = feeds.find(x => String(x.box).toUpperCase() === m[1].trim() && String(x.slot) === String(parseInt(m[2], 10)));
                if (!f) return false;
                if (!f.free) {
                    flash(`${f.box} slot ${f.slot} holds #${f.claimed_by}: pick a free slot, No box, or Cancel`);
                    return 'refused';
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
const UNDO_TIMEOUT_MS = 120000;     // a big park's Undo reads and writes every spool in it

// Past the timeout the server may well still be putting spools back, and a second
// press would ask about whatever it hasn't reached. Only for no answer: an exception
// after an answer must not read as this.
const _undoNotAnswered = () => {
    const msg = "FCC didn't answer, so the Undo may not have finished. Check the Activity Log before pressing it again.";
    showToast(msg, 'error', 7000);
    if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
    if (typeof updateLogState === 'function') updateLogState(true);
};

// The first press only asks the question, and writes nothing: with no answer to it,
// nothing was undone and nothing began (Group 58 re-review: it said the Undo "may not
// have finished", and sent the person to an Activity Log that holds nothing about it).
const _undoNotAsked = () => {
    const msg = "FCC didn't answer, so nothing was undone. Try again in a moment.";
    showToast(msg, 'error', 7000);
    if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
};

const triggerUndo = (opts = {}) => {
    const body = {};
    if (opts.confirm) { body.confirm = true; body.undo_id = opts.undoId; body.confirmed_toolheads = opts.heads || []; }
    window.fetchT('/api/undo', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }, UNDO_TIMEOUT_MS)
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
            // An audit park's Undo leaves a spool that moved on since, and says so:
            // that is a sentence to read, so the longer toast.
            if (res && res.success) showToast(res.msg || '↩️ Undone', 'success', (res.left_alone || []).length ? 7000 : 4000);
            else if (res && res.nothing) showToast(res.msg, 'info', 4000);
            else showToast((res && res.msg) || 'Undo failed', 'error', 7000);
        }, opts.confirm ? _undoNotAnswered : _undoNotAsked)
        .catch(e => console.error(e));
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
// Asked for again while one was in flight: one more goes out once it is back.
let _liveRefreshAgain = false;
// The buffer's answers are kept in order by when each read was sent (Group 57
// review: since 57.5 a tick answers from the spool list it reads before its
// printer probes, seconds before it lands, and it painted a weigh-out's 40 g
// back to 120 g for a tick). An answer is painted only when it was sent after
// the page's latest change to what the cards show (liveRefreshBuffer's callers:
// a weigh-out, a move, a save) and after the read behind what they show now.
// Round 2: a refresh asked for while another was in flight sent nothing, the
// one in flight (read before the change) painted, and the heartbeat that would
// have mended it was dropped; now that one is dropped, and one more refresh
// goes out once it is back. Stamped on the page's own clock (performance.now),
// as the heartbeat is (inv_core.js), so a wall-clock step can't freeze them.
// Round 3: the read behind each card is its own (`_bufferReadAt`, by spool id),
// moved only by an answer that carries that spool: an answer with nothing in
// it (an outage tick's {}, a section's {error}) or with only some of the cards
// stopped an older, fuller refresh from painting the rest. A change still drops
// every older answer: the callers' signals don't say which cards changed.
// Hence too: while changes come faster than a refresh's round trip, the cards
// wait for the first answer sent after the last one (painting an older read is
// the round-2 revert, a weigh-out's 40 g back to 120 g).
let _bufferChangedAt = -Infinity;
const _bufferReadAt = new Map();
const _bufferNow = () => (typeof performance !== 'undefined' && performance && typeof performance.now === 'function'
    ? performance.now() : Date.now());
// L206: render path extracted so the bulk-pulse dispatcher can hand
// a spools_refresh payload (same {id: data} shape that /api/spools/refresh
// returns) directly into the diff/update loop without another fetch.
// `opts.sentAt`: when the read behind it was sent (a heartbeat, or this
// page's own refresh); without it, the payload is painted as it comes.
const _renderSpoolsRefreshPayload = (data, opts) => {
    if (!data || typeof data !== 'object') return;
    const sentAt = opts && Number.isFinite(opts.sentAt) ? opts.sentAt : null;
    if (sentAt !== null && sentAt < _bufferChangedAt) return;
    // Cards that left the buffer keep no stamp.
    if (_bufferReadAt.size > state.heldSpools.length) {
        const held = new Set(state.heldSpools.map(s => String(s.id)));
        Array.from(_bufferReadAt.keys()).forEach(k => { if (!held.has(k)) _bufferReadAt.delete(k); });
    }
    let changed = false;
    state.heldSpools.forEach(s => {
        const fresh = data[s.id];
        if (!fresh) return;
        if (sentAt !== null) {
            const key = String(s.id);
            if (_bufferReadAt.has(key) && sentAt < _bufferReadAt.get(key)) return;
            _bufferReadAt.set(key, sentAt);
        }
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

// One /api/spools/refresh for the buffer as it is now.
const _sendBufferRefresh = () => {
    if (!state.heldSpools || state.heldSpools.length === 0) return;
    const spoolIds = state.heldSpools.map(s => s.id);
    const sentAt = _bufferNow();
    _liveRefreshInflight = true;
    fetch('/api/spools/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spools: spoolIds })
    })
        .then(r => r.json())
        .then(data => _renderSpoolsRefreshPayload(data, { sentAt }))
        .catch(e => console.warn("Live Refresh Buffer Failed", e))
        .finally(() => {
            _liveRefreshInflight = false;
            if (_liveRefreshAgain) {
                _liveRefreshAgain = false;
                _sendBufferRefresh();
            }
        });
};

// Something the buffer's cards show has just changed here: read them again.
const liveRefreshBuffer = () => {
    if (!state.heldSpools || state.heldSpools.length === 0) return;
    _bufferChangedAt = _bufferNow();
    // The one in flight read the cards before this change: one more goes out
    // once it is back, never two at once (L28's guard).
    _liveRefreshAgain = _liveRefreshInflight;
    if (_liveRefreshInflight) return;
    _sendBufferRefresh();
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