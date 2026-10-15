/* MODULE: CORE (State & Helpers) */
console.log("🚀 Loaded Module: CORE");

// --- GLOBAL STATE ---
let wakeLock = null;
let modals = {};
let state = {
    // Core
    scanBuffer: "",
    bufferTimeout: null,
    processing: false,
    logsPaused: false,
    allLocations: [],

    // Command Center / Buffer
    heldSpools: [],
    ejectMode: false,
    dropMode: false,
    lastScannedLoc: null,
    auditActive: false,
    lastAuditState: null,
    // L298 Phase 2 — bulk-move scan session. `bulkMoveActive` mirrors the
    // backend's session flag from the /api/logs heartbeat; `bulkMoveStage`
    // (idle | awaiting_source | awaiting_dest | preview) drives the deck QR's
    // shapeshift and is refreshed by the panel's own session poll.
    bulkMoveActive: false,
    lastBulkMoveState: null,
    bulkMoveStage: 'idle',

    // Manager
    currentGrid: {},
    locSortBy: 'LocationID',
    locSortDir: 1,

    // Modals
    modalCallbacks: [],
    activeModal: null,
    pendingConfirm: null,
    pendingSafety: null
};

// --- SCAN-IN-FLIGHT (the one canonical definition) ---
// "Is a barcode scanner mid-payload right now?" A scanner types its payload as
// ordinary keydowns, so ANY key handler that fires on a bare letter, or that
// treats Enter as a button press, will steal characters out of a scan unless it
// asks this first.
//
// This lived as THREE identical copy-pasted closures (fab_drag.js,
// inv_cmd.js, shortcuts_registry.js) and the 2026-08-03 scan-path audit was
// about to add several more. One definition, on `state` so every module can
// reach it, is the fix — the audit's own recommendation.
//
// The 500ms window matters: `scanBuffer` alone is not enough. A buffer left by
// an abandoned keystroke lingers until the 2s accumulator timeout, and during
// that window a bare truthiness check would wrongly block real button presses.
// A scanner delivers its whole payload in well under 500ms.
const isScanInFlight = () => {
    const st = (typeof state !== 'undefined') ? state : window.state;
    return !!(st && typeof st.scanBuffer === 'string' && st.scanBuffer.length > 0
        && st.scanStartTime && (Date.now() - st.scanStartTime) < 500);
};
window.isScanInFlight = isScanInFlight;

// --- SCANNER BURST (the accumulator's barcode test, as a predicate) ---
// "Did what is in scanBuffer arrive at scanner speed?" The accumulator
// (scripts.html) calls a payload 'barcode' when it lands in under 150ms, and
// installFieldScanCapture below uses the same threshold with a 3-character
// floor. Narrower than isScanInFlight (500ms, any length): a typeahead letter
// followed by Enter is "in flight" for 500ms but is never a burst. For a key
// handler that owns a human's Enter yet must leave a real scan to the
// accumulator (Group 46.2, the location editor).
const isScannerBurst = () => {
    const st = (typeof state !== 'undefined') ? state : window.state;
    return !!(st && typeof st.scanBuffer === 'string' && st.scanBuffer.length >= 3
        && st.scanStartTime && (Date.now() - st.scanStartTime) < 150);
};
window.isScannerBurst = isScannerBurst;

// --- SCAN BUFFER RESET (now, and again after this tick) ---
// For a key handler that consumes a key the accumulator (scripts.html) would
// otherwise collect or submit. The deferred second clear doesn't depend on
// listener order (the L298 Shift+B lesson): if the accumulator still runs after
// the caller, the buffer ends up empty anyway.
const clearScanBuffer = () => {
    const st = (typeof state !== 'undefined') ? state : window.state;
    const clear = () => {
        if (!st) return;
        st.scanBuffer = '';
        st.scanStartTime = 0;
        try { clearTimeout(st.bufferTimeout); } catch (_) { /* noop */ }
    };
    clear();
    setTimeout(clear, 0);
};
window.clearScanBuffer = clearScanBuffer;

// --- CONFIRMED HEADS (Group 39.1) ---
// A move's active-print confirm names the heads whose warning the user saw
// (`confirmed_toolheads`); a bare `confirm_active_print: true` covers none.
// unionConfirmHeads(prior, answer) is what a Yes sends: the heads already
// confirmed plus the ones this answer showed (`active_prints`, else the legacy
// `active_print`). Always the UNION: replaying only the latest answer's heads
// would ping-pong the user between two printing heads forever.
const unionConfirmHeads = (prior, answer) => {
    const out = new Set((Array.isArray(prior) ? prior : []).map(h => String(h).toUpperCase()));
    const shown = (answer && Array.isArray(answer.active_prints) && answer.active_prints.length)
        ? answer.active_prints.map(a => a && a.toolhead)
        : [answer && answer.active_print && answer.active_print.toolhead];
    shown.forEach(h => { if (h) out.add(String(h).toUpperCase()); });
    return [...out];
};
window.unionConfirmHeads = unionConfirmHeads;

// --- CONFIRMED FED HEADS (Group 40.3) ---
// The fed-head twin of unionConfirmHeads: what "Load it instead" sends in
// `confirmed_fed_heads`, the confirm keys ("XL-1#99": the head AND the spools
// the question named) of every head_fed answer so far. A different spool on
// that head is asked about again. Always the UNION: an idle "already running"
// question followed by a print starting would otherwise ping-pong between two
// dialogs, each Yes forgetting the other.
const unionConfirmFedHeads = (prior, answer) => {
    const out = new Set((Array.isArray(prior) ? prior : []).map(k => String(k).toUpperCase()));
    const fed = (answer && Array.isArray(answer.fed_heads)) ? answer.fed_heads : [];
    fed.forEach(f => { if (f && f.confirm_key) out.add(String(f.confirm_key).toUpperCase()); });
    return [...out];
};
window.unionConfirmFedHeads = unionConfirmFedHeads;

// --- MOVE CONFIRM (Group 39.4; three-way mode Group 40.3) ---
// The one overlay every move door shows when the server asks a question
// (CLAUDE.md: a new door shows window.confirmActivePrint, never a new copy).
// Two modes:
//   - yes / no (39.4): a move touches a printing head. The server's `msg`
//     (Derek's D6 wording), Continue Anyway / Cancel.
//   - three-way (40.3, `title` given): loading a bound box slot's toolhead
//     needs a word (`confirm_type: 'head_fed'`, or a printing answer that can
//     store). `title` asks ("Load #57 onto XL-1?"), `msg` explains (the
//     server's `body`, with no "Continue?"), and the buttons are Load it
//     instead (the yes) · Just store it in <box> slot <n> (`onStore`) · Cancel
//     (the no). Nothing about printing is invented: a printing answer's body
//     says so itself. Enter stores (Derek, 2026-10-14: a toolhead can't be
//     loaded mid-print, and on the fed dialog too); with no store option it
//     cancels, never loads. While it is open, other scans are held off
//     (window._fccOpenMoveQuestion, read by processScan).
// Both: one answer only (a double click, or a click racing a scan, moves
// once); a scan in flight owns its Enter, and so does a slower scanner's
// buffered payload; Tab (and ←/→ in the three-way) cycles the buttons; Escape
// cancels through mountOverlay; the QR row mirrors the buttons (CMD:CONFIRM /
// CMD:STORE / CMD:CANCEL); and the host closing cancels it (its QR session used
// to stay armed after the host had gone).
// `host`: the Bootstrap modal it sits over. `ids`: {overlay, yes, no, store}, for
// a caller that keeps its proven DOM ids (the Location Manager and scan-assign
// overlays, and their tests).
// One unanswered question per overlay id (Group 40.3 review, B2 / B3): a dialog
// mounted on the same id over an unanswered one replaces it, and the older one
// is settled as superseded (`onCancel({superseded: true})`), so its host
// listener, QR session and scan hold-off never outlive its DOM.
const _openMoveConfirms = {};
window.confirmActivePrint = ({ activePrint = null, activePrints = [], msg = '', host = null,
                               ids = {}, onConfirm = null, onCancel = null,
                               title = '', onStore = null, storeLabel = '', loadLabel = '',
                               printing = null, noLoad = false } = {}) => {
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const threeWay = !!title;
    const first = activePrint || (Array.isArray(activePrints) && activePrints[0]) || {};
    const isPrinting = printing != null ? !!printing
        : !!(activePrint || (Array.isArray(activePrints) && activePrints.length));
    const hasStore = threeWay && typeof onStore === 'function';
    // A three-way question whose answer can't load (a slot that now feeds no
    // toolhead, 40.3's feed_changed) offers only the store and Cancel.
    const hasLoad = !(threeWay && noLoad && hasStore);
    const idAttr = (id) => (id ? `id="${esc(id)}" ` : '');
    const border = (!threeWay || isPrinting) ? '#ff8800' : '#0dcaf0';
    const header = threeWay
        ? `${isPrinting ? '⚠️' : '🔁'} ${esc(title)}`
        : `⚠️ ${esc(first.printer_name || 'A printer')} is ${esc(first.state || 'PRINTING')}`;
    const bodyText = threeWay ? msg : (msg || 'Moving a spool now will disrupt the print. Continue?');
    const buttons = threeWay
        ? (hasLoad ? `<button type="button" ${idAttr(ids.yes)}class="btn btn-warning btn-sm fcc-apc-yes" style="min-width:120px;">${esc(loadLabel || 'Load it instead')}</button>` : '')
          + (hasStore ? `<button type="button" ${idAttr(ids.store)}class="btn btn-info btn-sm fcc-apc-store" style="min-width:120px;">${esc(storeLabel || 'Just store it')}</button>` : '')
          + `<button type="button" ${idAttr(ids.no)}class="btn btn-secondary btn-sm fcc-apc-no" style="min-width:100px;">Cancel</button>`
        : `<button type="button" ${idAttr(ids.yes)}class="btn btn-warning btn-sm fcc-apc-yes" style="min-width:120px;">Continue Anyway</button>
                <button type="button" ${idAttr(ids.no)}class="btn btn-secondary btn-sm fcc-apc-no" style="min-width:120px;">Cancel</button>`;
    const extras = threeWay
        ? `<div class="fcc-apc-hint" style="font-size:0.8rem; color:#ccc; margin-top:8px;">Enter ${hasStore ? 'stores it' : 'cancels'} · Esc cancels</div>`
        : '';
    const status = threeWay
        ? `<div class="fcc-apc-status" role="alert" style="display:none; margin-bottom:10px; padding:6px 10px; border-radius:6px; background:#4a3200; color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; text-align:left;"></div>`
        : '';
    const content = `
        <div class="fcc-apc-panel" style="background:#1e1e1e; color:#fff; border:2px solid ${border}; border-radius:8px; padding:20px 24px; max-width:${threeWay ? 560 : 480}px; text-align:center;">
            <div class="fcc-apc-title" style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">${header}</div>
            <div class="fcc-apc-msg" style="color:#ffc; margin-bottom:14px;${threeWay ? ' text-align:left;' : ''}">${esc(bodyText)}</div>
            ${status}
            <div style="display:flex; gap:10px; justify-content:center;${threeWay ? ' flex-wrap:wrap;' : ''}">
                ${buttons}
            </div>
            ${extras}
        </div>`;
    const overlayId = ids.overlay || 'fcc-active-print-confirm-overlay';
    let handle = null;
    let qrSession = null;
    let settled = false;
    let hostOff = null;
    let question = null;
    let statusTimer = null;
    let superseded = null;
    const cleanup = () => {
        if (qrSession) { try { qrSession.cleanup(); } catch (_) { /* noop */ } qrSession = null; }
        if (handle) { try { handle.cleanup(); } catch (_) { /* noop */ } handle = null; }
        if (hostOff) { try { hostOff(); } catch (_) { /* noop */ } hostOff = null; }
        if (question) {
            // Scans are held off while ANY three-way is open (Group 40.3 fix
            // check, W3): answering the newer of two let a scan start a move
            // behind the older one.
            const open = (window._fccOpenMoveQuestions || []).filter(q => q !== question);
            window._fccOpenMoveQuestions = open;
            if (window._fccOpenMoveQuestion === question) {
                window._fccOpenMoveQuestion = open.length ? open[open.length - 1] : null;
            }
        }
        if (superseded && _openMoveConfirms[overlayId] === superseded) delete _openMoveConfirms[overlayId];
        clearTimeout(statusTimer);
    };
    // Once only: a double click, or a click racing a scan, must not move twice.
    const settle = (fn) => () => { if (settled) return; settled = true; cleanup(); if (fn) fn(); };
    const yes = settle(onConfirm);
    const store = settle(onStore);
    const no = settle(onCancel);
    superseded = () => {
        if (settled) return;
        settled = true;
        cleanup();
        // Logged here, whatever the caller (Group 40.3 fix check, W5: a
        // replaced yes / no left no trace); never toasted as "Cancelled".
        const said = threeWay ? title : `${first.printer_name || 'A printer'} is ${first.state || 'PRINTING'}`;
        if (window.logClientEvent) window.logClientEvent(
            `ℹ️ "${said}" was replaced by another question — nothing moved`, 'INFO');
        if (onCancel) onCancel({ superseded: true });
    };
    const prior = _openMoveConfirms[overlayId];
    if (prior) prior();
    handle = window.mountOverlay({
        id: overlayId,
        content,
        tier: 'confirm',
        host: host || undefined,
        initialFocus: threeWay ? (hasStore ? '.fcc-apc-store' : '.fcc-apc-no') : '.fcc-apc-yes',
        onEscape: no,
    });
    _openMoveConfirms[overlayId] = superseded;
    const ov = handle.element;
    const yesBtn = hasLoad ? ov.querySelector('.fcc-apc-yes') : null;
    const storeBtn = hasStore ? ov.querySelector('.fcc-apc-store') : null;
    const noBtn = ov.querySelector('.fcc-apc-no');
    if (yesBtn) yesBtn.onclick = yes;
    if (storeBtn) storeBtn.onclick = store;
    if (noBtn) noBtn.onclick = no;
    // mountOverlay removes the DOM when the host closes; the answer must close
    // too, or its QR session stays armed and a late CMD:CONFIRM still moves.
    if (host && typeof host.addEventListener === 'function') {
        const onHostGone = () => no();
        host.addEventListener('hidden.bs.modal', onHostGone);
        host.addEventListener('hidden.bs.offcanvas', onHostGone);
        hostOff = () => {
            host.removeEventListener('hidden.bs.modal', onHostGone);
            host.removeEventListener('hidden.bs.offcanvas', onHostGone);
        };
    }
    ov.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            // A scan in flight owns this Enter: it terminates the scan (a
            // "Scan to Cancel" QR must never perform the CONFIRM). So does a
            // slower scanner's buffered payload (a ':' no human types here):
            // its Enter used to answer the focused button, and in the
            // three-way that is "Just store it".
            if (window.isScanInFlight && window.isScanInFlight()) return;
            const st = (typeof state !== 'undefined') ? state : window.state;
            const buffered = st && typeof st.scanBuffer === 'string' ? st.scanBuffer : '';
            if (buffered && window.looksLikeScanPayload && window.looksLikeScanPayload(buffered)) return;
            const ae = document.activeElement;
            if (threeWay) {
                e.preventDefault(); e.stopPropagation();
                if (yesBtn && ae === yesBtn) yes();
                else if (storeBtn && ae === storeBtn) store();
                else if (ae === noBtn) no();
                else if (hasStore) store();
                else no();
                return;
            }
            if (ae === yesBtn) { e.preventDefault(); e.stopPropagation(); yes(); }
            else if (ae === noBtn) { e.preventDefault(); e.stopPropagation(); no(); }
            return;
        }
        const arrow = threeWay && (e.key === 'ArrowLeft' || e.key === 'ArrowRight');
        if (e.key === 'Tab' || arrow) {
            const order = [yesBtn, storeBtn, noBtn].filter(Boolean);
            const back = e.key === 'ArrowLeft' || (e.key === 'Tab' && e.shiftKey);
            const idx = order.indexOf(document.activeElement);
            const next = idx === -1 ? (back ? order.length - 1 : 0)
                : (idx + (back ? order.length - 1 : 1)) % order.length;
            e.preventDefault(); e.stopPropagation();
            order[next].focus();
        }
    }, true);
    if (window.attachConfirmQRs) {
        // Inside the dialog PANEL, so the QR row stacks below the buttons.
        // A three-way with no Load (it can only store) scans its store as the
        // CONFIRM QR, so there are never two cancel codes.
        const theme = isPrinting ? 'warning' : 'info';
        qrSession = window.attachConfirmQRs(!threeWay
            ? { host: handle.panel, onConfirm: yes, onCancel: no, theme: 'warning' }
            : hasLoad
                ? { host: handle.panel, onConfirm: yes, onCancel: no, onStore: hasStore ? store : undefined,
                    confirmLabel: 'Scan to Load', storeLabel: 'Scan to Store', cancelLabel: 'Scan to Cancel', theme }
                : { host: handle.panel, onConfirm: store, onCancel: no,
                    confirmLabel: 'Scan to Store', cancelLabel: 'Scan to Cancel', theme });
    }
    if (threeWay) {
        // The question on screen: processScan holds off every other scan until
        // it is answered (a second slot label used to start a second move
        // behind the dialog). The status line says why a scan did nothing:
        // the toast layer (z 11000) sits under this dialog.
        question = {
            title,
            // processScan drops a hold-off whose dialog is no longer on the page.
            element: ov,
            cancel: () => no(),
            flash: (text) => {
                const line = ov.querySelector('.fcc-apc-status');
                if (!line) return;
                line.textContent = text;
                line.style.display = 'block';
                clearTimeout(statusTimer);
                statusTimer = setTimeout(() => { line.style.display = 'none'; }, 7000);
            },
        };
        window._fccOpenMoveQuestions = (window._fccOpenMoveQuestions || []).concat([question]);
        window._fccOpenMoveQuestion = question;
    }
    return { close: no };
};

// --- HEAD-LOAD CONFIRM (Group 40.3, Derek's D2.2 / D2.3) ---
// A server answer about loading a bound box slot's toolhead, shown as the
// three-way above: `head_fed` (that head already runs a spool from somewhere
// else, printing or not; e.g. XL-1 running off a PolyDryer while LR-MDB-1 slot 1
// is prepped for later), a printing answer that can store (`can_store`), or a
// slot that changed its feed while the user decided (`feed_changed`). The
// title and body are the server's; the store button names the slot the
// question was about. `box` / `slot`: the door's own, for an answer that names
// neither.
window.confirmHeadLoad = ({ answer = {}, box = '', slot = '', host = null, ids = {},
                            onLoad = null, onStore = null, onCancel = null } = {}) => {
    const a = answer || {};
    const fed = (Array.isArray(a.fed_heads) && a.fed_heads[0]) || null;
    const feedsEntry = (Array.isArray(a.active_prints) ? a.active_prints : []).find(p => p && p.role === 'feeds') || null;
    const head = (fed && fed.toolhead) || (feedsEntry && feedsEntry.toolhead)
        || (typeof a.feed === 'string' ? a.feed : '');
    const spools = Array.isArray(a.spools) ? a.spools : [];
    const sid = spools.length ? spools[spools.length - 1] : (a.moved != null ? a.moved : null);
    const what = sid != null ? `#${sid}` : 'the spool';
    const title = a.title || (head ? `Load ${what} onto ${head}?` : `Load ${what}?`);
    const body = a.body || String(a.msg || '').replace(/\s*Continue\?\s*$/, '');
    const storeBox = (fed && fed.box) || a.target || box || a.location || '';
    const storeSlot = (fed && fed.slot) || a.target_slot || slot || a.slot || '';
    const where = (storeSlot !== '' && storeSlot != null) ? `${storeBox} slot ${storeSlot}` : storeBox;
    return window.confirmActivePrint({
        title, msg: body, host, ids,
        activePrints: Array.isArray(a.active_prints) ? a.active_prints : [],
        // The server's own word (Group 40.3 review, C4): a printing head the
        // caller already confirmed is not in active_prints, yet the body says
        // the XL is printing.
        printing: typeof a.printing === 'boolean' ? a.printing
            : (Array.isArray(a.active_prints) && a.active_prints.length > 0),
        loadLabel: 'Load it instead', onConfirm: onLoad,
        storeLabel: `Just store it in ${where}`,
        onStore: (a.can_store === true && typeof onStore === 'function') ? onStore : null,
        noLoad: a.can_load === false,
        onCancel,
    });
};

// --- MOVE QUESTIONS: what kind, and what a door sends back (Group 40.3) ---
// moveConfirmKind(answer): null (not a question), 'head_load' (the three-way:
// head_fed / feed_changed, or a printing answer that can store), 'active_print'
// (the yes / no; a missing confirm_type is still one, as every answer was
// before 40.0c) or 'unknown' (never shown as an invented printing yes / no).
window.moveConfirmKind = (answer) => {
    const a = answer || {};
    const asking = a.status === 'requires_confirm' || /_requires_confirm$/.test(String(a.action || ''));
    if (!asking) return null;
    const type = (a.confirm_type == null || a.confirm_type === '') ? 'active_print' : String(a.confirm_type);
    if (type === 'head_fed' || type === 'feed_changed') return 'head_load';
    if (type === 'active_print') return a.can_store === true ? 'head_load' : 'active_print';
    return 'unknown';
};

// buildMoveReplay(door, original, answer, choice, prior) -> {body, prior}: the
// request a door sends after the user answered `answer`, from the request it
// first sent (`original`) and what earlier rounds confirmed (`prior`). Pure.
//   door:   'slot_scan' (identify_scan: the slot is in `text`), 'smart_move'
//           (`spools` + `slot`) or 'manage_add' (`spool_id` + `slot`).
//   choice: 'load' (Load it instead, or the yes / no's Yes) or 'store'.
// Load it instead adds every confirm key so far (`confirmed_fed_heads`) and
// every printing head so far (`confirmed_toolheads`). Just store it sends
// `auto_deploy: false`, and confirms only the printing heads it does NOT load
// (a spool leaving a printing head still asks about that head); a store stays
// a store in later rounds. Both send `expected_feed` (what the slot fed when
// the user decided: a slot re-pointed meanwhile is asked about again), the slot
// the engine picked for a slotless move (`picked_slot`: kept only while still
// free, never an Overwrite), and the spools the question named, never a
// re-read of a buffer that may have changed.
window.buildMoveReplay = (door, original, answer, choice, prior = {}) => {
    const a = answer || {};
    const p = prior || {};
    const store = choice === 'store' || !!p.store;
    const fedKeys = store ? (Array.isArray(p.fedKeys) ? p.fedKeys.slice() : [])
        : window.unionConfirmFedHeads(p.fedKeys, a);
    const prints = Array.isArray(a.active_prints) ? a.active_prints : [];
    const heads = store
        ? window.unionConfirmHeads(p.heads, { active_prints: prints.filter(x => x && x.role !== 'feeds') })
        : window.unionConfirmHeads(p.heads, a);
    const body = Object.assign({}, original || {}, { confirmed_toolheads: heads, confirmed_fed_heads: fedKeys });
    if (store) body.auto_deploy = false;
    let feed = null;
    if (typeof a.feed === 'string') feed = a.feed;
    else {
        const fed = (Array.isArray(a.fed_heads) && a.fed_heads[0]) || null;
        const feedsEntry = prints.find(x => x && x.role === 'feeds') || null;
        feed = (fed && fed.toolhead) || (feedsEntry && feedsEntry.toolhead) || (p.expectedFeed != null ? p.expectedFeed : null);
    }
    if (feed != null) body.expected_feed = String(feed).toUpperCase();
    const o = original || {};
    const noSlot = o.slot == null || String(o.slot).trim() === '';
    let picked = p.pickedSlot != null ? p.pickedSlot : null;
    if (a.slot_picked === true || (a.slot_picked === undefined && door !== 'slot_scan' && noSlot)) {
        if (a.target_slot != null && a.target_slot !== '') picked = String(a.target_slot);
    }
    if (door !== 'slot_scan' && picked != null) body.picked_slot = picked;
    const spools = Array.isArray(a.spools) ? a.spools : [];
    if (door === 'slot_scan') {
        const sid = a.moved != null ? a.moved : (spools.length ? spools[spools.length - 1] : null);
        if (sid != null) body.spool_id = sid;
    } else if (door === 'smart_move' && spools.length) {
        body.spools = spools.slice();
    }
    // The heads a moving spool leaves, as every round named them, for the store
    // toast (window.storeToastTail): the answer's `leaving` (printing or not),
    // and a printing answer's 'source' heads.
    const sources = Array.from(new Set([].concat(
        Array.isArray(p.sources) ? p.sources : [],
        (Array.isArray(a.leaving) ? a.leaving : []).map(x => String(x || '').toUpperCase()).filter(Boolean),
        prints.filter(x => x && x.role === 'source').map(x => String(x.toolhead || '').toUpperCase()).filter(Boolean))));
    return { body, prior: { heads, fedKeys, store, expectedFeed: feed, pickedSlot: picked, sources } };
};

// The end of a "Just store it" toast (Group 40.3 review, B4): " — XL-1 left as it
// was", unless the stored spool came off that very head (a spool on XL-1 scanned
// into the slot that feeds XL-1, mid-print), where it says " — taken off XL-1".
// '' when the question named no head. `prior`: a buildMoveReplay prior.
window.storeToastTail = (prior) => {
    const p = prior || {};
    const head = p.expectedFeed ? String(p.expectedFeed).toUpperCase() : '';
    if (!head) return '';
    return (Array.isArray(p.sources) && p.sources.includes(head)) ? ` — taken off ${head}` : ` — ${head} left as it was`;
};

// --- THE SAME-SLOT SWAP'S OLD SPOOL (Group 40; Derek, 2026-10-15) ---
// A move that filled a box slot whose own spool was running on the slot's head
// took that spool off the head into the scan buffer: it is in your hand (Derek
// swaps a slot once its spool has run out, so it usually needs zeroing). The
// server put it at the END of its buffer replica, Unassigned in Spoolman, and
// names it in the answer's `to_buffer` (a slot scan's own `smart_move` too). This
// page adds it to its buffer as well, behind the spools already waiting (its
// next save replaces the replica whole, so the server's copy alone would be
// lost), and toasts it in short arrows. Every door that can complete a move
// calls it with the answer. A door that edits the buffer itself passes
// {render: false} and renders ONCE after both edits: two saves in a row can
// reach the server out of order, and the one without this spool would win.
// {toast: false} leaves the toast to window.toastIntoBuffer(items). Returns the
// entries it was told about.
window.toastIntoBuffer = (items) => {
    (items || []).forEach(i => {
        const off = i && i.off_head ? ` (taken off ${i.off_head})` : '';
        if (i && typeof showToast === 'function') showToast(`✋ #${i.id} → your buffer${off}`, 'info', 5000);
    });
};
window.takeIntoBuffer = (answer, { render = true, toast = true } = {}) => {
    const a = answer || {};
    const list = Array.isArray(a.to_buffer) ? a.to_buffer
        : ((a.smart_move && Array.isArray(a.smart_move.to_buffer)) ? a.smart_move.to_buffer : []);
    const items = list.filter(i => i && i.id != null);
    if (!items.length) return [];
    const st = (typeof state !== 'undefined') ? state : window.state;
    let added = false;
    items.forEach(i => {
        if (!st.heldSpools.some(s => String(s.id) === String(i.id))) {
            const entry = Object.assign({}, i);
            delete entry.off_head;
            st.heldSpools.push(entry);
            added = true;
        }
    });
    if (render && added && window.renderBuffer) window.renderBuffer();
    if (toast) window.toastIntoBuffer(items);
    return items;
};

// askMoveConfirm(answer, ctx): the one place a door shows a move question and
// sends its replay. ctx: {door, original, prior, host, ids, box, slot,
// send(body, nextPrior, choice), askYesNo?(answer, yes), onCancel?}. A
// `head_load` answer gets the three-way; an `active_print` one the door's own
// yes / no (`askYesNo`, which keeps its proven ids and wording) or the shared
// one. Cancel moves nothing and says so.
window.askMoveConfirm = (answer, ctx = {}) => {
    const kind = window.moveConfirmKind(answer);
    const prior = ctx.prior || {};
    const replay = (choice) => {
        const r = window.buildMoveReplay(ctx.door, ctx.original, answer, choice, prior);
        ctx.send(r.body, r.prior, choice);
    };
    const toast = (m, type, ms) => { if (typeof showToast === 'function') showToast(m, type, ms); };
    if (kind === 'head_load') {
        const cancelled = (info) => {
            if (info && info.superseded) {
                // Another question took its place (Group 40.3 review, B2): the
                // user never answered this one, and a toast here read as if the
                // move they did answer had been cancelled. confirmActivePrint
                // logged it.
            } else {
                toast('Cancelled — nothing moved', 'info', 4000);
                if (window.logClientEvent) window.logClientEvent(
                    `ℹ️ Cancelled "${answer.title || 'a load question'}" — nothing moved`, 'INFO');
            }
            if (ctx.onCancel) ctx.onCancel(info);
        };
        // `ctx.noStore` (Group 40.2 review): the door knows a store would be
        // refused (the box picker's slot holds a stale record), so no "Just
        // store it"; Enter then cancels, as in any three-way with no store.
        return window.confirmHeadLoad({ answer, host: ctx.host, ids: ctx.ids || {}, box: ctx.box, slot: ctx.slot,
            onLoad: () => replay('load'), onStore: ctx.noStore ? null : () => replay('store'), onCancel: cancelled });
    }
    if (kind === 'active_print') {
        const yes = () => replay(prior.store ? 'store' : 'load');
        if (typeof ctx.askYesNo === 'function') return ctx.askYesNo(answer, yes);
        return window.confirmActivePrint({ activePrint: answer.active_print, activePrints: answer.active_prints || [],
            msg: answer.msg, host: ctx.host, ids: ctx.ids || {}, onConfirm: yes, onCancel: ctx.onCancel });
    }
    const what = (answer && answer.msg) || 'FCC asked a question this page cannot show';
    toast(`${what} — nothing moved. Reload the page if this keeps happening.`, 'warning', 7000);
    if (window.logClientEvent) window.logClientEvent(
        `⚠️ Unrecognised move question (${answer && answer.confirm_type}) — nothing moved`, 'WARNING');
    // `unknown`: nobody answered anything (Group 40.2: the box picker's loop ends
    // here instead of reopening the picker on the same unanswerable question).
    if (ctx.onCancel) ctx.onCancel({ unknown: true });
    return null;
};

// --- SCAN CAPTURE FROM A FOCUSED FIELD ---
// The global accumulator bails on `e.target.tagName === 'INPUT'`, so any modal
// that focuses a text field disarms the scanner. Sometimes dropping the
// auto-focus is right; sometimes the field genuinely wants the cursor AND the
// modal genuinely wants to accept scans (Weigh-Out says "scan them now while
// this window is open" while focusing a weight box; Manage Contents re-focuses
// its ID field after every add while its own CMD:DONE QR sits below).
//
// This lets such a field keep focus and still hand scanner input to the scan
// path. Two conditions, BOTH required, so ordinary typing is never hijacked:
//   1. scanner SPEED — the payload lands in under 150ms, the same threshold the
//      global accumulator uses to classify barcode vs keyboard;
//   2. the text does not look like something a human would type HERE — supplied
//      per-caller, because "not a weight" and "not a spool id" differ.
//
// One implementation, not one per modal: the 2026-08-03 audit found the same
// scan-path defect re-written in four separate places, so new copies of this
// logic are exactly what to avoid.
//
//   match(el)          -> is this the field we care about?
//   isScanPayload(txt) -> is this a scan rather than typing?
//   onScan(txt, el)    -> what to do with it (default: window.processScan)
const installFieldScanCapture = ({ match, isScanPayload, onScan }) => {
    let buf = '';
    let startedAt = 0;
    let lastAt = 0;
    let preScanValue = '';   // what the user had typed BEFORE the burst began
    document.addEventListener('keydown', (e) => {
        const el = e.target;
        if (!el || !match(el)) return;
        const now = Date.now();

        if (e.key === 'Enter') {
            const fast = buf.length >= 3 && startedAt && (now - startedAt) < 150;
            const looksScanned = fast && isScanPayload(buf);
            const payload = buf;
            const restore = preScanValue;
            buf = ''; startedAt = 0; preScanValue = '';
            if (!looksScanned) return;   // a real entry — let the field's own handler run
            e.preventDefault();
            e.stopImmediatePropagation();
            // RESTORE what the user had typed, don't blank the field. The
            // scanner's characters were appended to their in-progress value
            // (this handler doesn't preventDefault on character keys), so
            // clearing outright silently destroyed an un-submitted weight —
            // and the Group 31.3 preserve-text snapshot in renderWeighOutList
            // then captured an already-empty field, so the buffer-updated
            // redraw could not bring it back either.
            el.value = restore;
            if (onScan) onScan(payload, el);
            else if (window.processScan) window.processScan(payload, 'barcode');
            return;
        }

        if (e.key.length !== 1 || e.ctrlKey || e.altKey || e.metaKey) return;
        // A gap longer than the scanner threshold means a human — start over,
        // and re-snapshot what is in the field at the moment a burst begins.
        if (!buf || (now - lastAt) > 150) {
            buf = '';
            startedAt = now;
            preScanValue = el.value || '';
        }
        buf += e.key;
        lastAt = now;
    }, true);   // capture: must beat the field's own Enter handler
};
window.installFieldScanCapture = installFieldScanCapture;

// A scan payload always carries a prefix marker (`ID:`, `LOC:`, `CMD:`,
// `FIL:`, `SPOOL:`) or is a URL (Prusament QRs). Nothing a user types into an
// id/weight box looks like that, which is what makes the distinction safe.
window.looksLikeScanPayload = (txt) =>
    /[:/]/.test(txt) || /^https?/i.test(txt);

// --- INITIALIZATION HELPERS ---
const acquireLock = async () => {
    if ('wakeLock' in navigator) {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            console.log("🔌 Native WakeLock acquired.");
        } catch (err) {
            console.log("Native WakeLock failed.", err);
        }
    }
};

let noSleepInstance = null;
const enableWakeLocks = async () => {
    await acquireLock(); // Fire native lock again now that we have a gesture!
    if (window.NoSleep && !noSleepInstance) {
        noSleepInstance = new window.NoSleep();
        noSleepInstance.enable();
        console.log("🎬 NoSleep.js armed via user interaction.");
    }
};

const requestWakeLock = async () => {
    // 1. Try to acquire immediately (works on some mobile browsers without gesture)
    await acquireLock();

    // 2. Setup NoSleep.js fallback AND Native WakeLock via explicit user interaction.
    // Modern desktop browsers (Chrome/Edge on laptops) strictly block both WakeLock and Autoplay Video (NoSleep) 
    // unless the user has physically clicked the page first.
    const firstInteract = async () => {
        await enableWakeLocks();
        // We only need to catch the *first* interaction to bypass the security wall.
        document.removeEventListener('click', firstInteract, false);
        document.removeEventListener('touchstart', firstInteract, false);
        document.removeEventListener('keydown', firstInteract, false);
    };

    document.addEventListener('click', firstInteract, false);
    document.addEventListener('touchstart', firstInteract, false);
    document.addEventListener('keydown', firstInteract, false);
};

// --- UI HELPERS ---
// Fire-and-forget client-side Activity Log write. Use this for toasts
// raised by paths that DIDN'T go through a backend endpoint that already
// logs — e.g. network errors, frontend-only validation, fallback flows.
// The Activity Log is now the authoritative record of what happened; if
// a toast isn't mirrored there, shortening toast durations would actively
// hide information from the user.
const logClientEvent = (msg, level = 'INFO') => {
    try {
        fetch('/api/log_event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ msg, level }),
        }).catch(() => { /* best effort */ });
    } catch (e) { /* best effort */ }
};
window.logClientEvent = logClientEvent;

// L271 Phase 3.5 (review fix #3): HTML/attribute escape for any user-controlled
// value interpolated into innerHTML (LocationID + Name come from free-text edit
// fields and from Spoolman-native location names — stored-XSS sources). Escapes
// both text and attribute contexts; for JS-string contexts (onclick) we use
// delegated listeners instead (see scripts.html location-table handler).
const escHtml = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));
const escAttr = escHtml;
window.escHtml = escHtml;
// Export escAttr too — cross-module callers (e.g. the Group-34 parent tree
// picker in inv_loc_mgr.js) reach it via window; without this a
// `window.escAttr || identity` fallback silently disables attribute escaping
// (stored-XSS via a LocationID interpolated into a data-* attribute).
window.escAttr = escAttr;

// 23.4 — Shared delete-sentinel for clearing a Spoolman `extra` field. The
// backend merge (spoolman_api._merge_extras_with_existing) treats an OMITTED
// key as "keep" so partial PATCHes don't wipe siblings; a key whose value is
// THIS sentinel is the explicit "delete this extra" signal (the merge pops it,
// never forwards it to Spoolman). Every edit surface that lets the user blank
// an extra (edit-filament, wizard spool-edit, vendor edit) sends this instead
// of dropping the key client-side. MUST match spoolman_api.DELETE_EXTRA_SENTINEL.
window.FCC_DELETE_EXTRA = '__FCC_DELETE_EXTRA__';

const showToast = (msg, type = 'info', duration = 2000) => {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id = 'toast-container'; document.body.appendChild(c); }
    const el = document.createElement('div');
    el.className = 'toast-msg toast-' + type;
    el.innerText = msg;
    const borderByType = { error: '#f44', warning: '#fc0', success: '#0f0', info: '#00d4ff' };
    el.style.borderColor = borderByType[type] || borderByType.info;
    el.style.cursor = 'pointer';
    el.title = 'Click to dismiss';
    // Click anywhere on the toast dismisses it immediately. The Activity
    // Log is the durable record — toasts are just "here, now" feedback,
    // so getting them out of the way on a click is a clean UX.
    const dismiss = () => {
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
    };
    el.addEventListener('click', dismiss, { once: true });
    c.appendChild(el);
    setTimeout(dismiss, duration);
};
// `showToast` is a top-level `const` in this classic (non-module) script, so it
// lives in the global LEXICAL environment — bare `showToast(...)` resolves, but
// `window.showToast` did NOT, silently no-op'ing every guarded
// `if (window.showToast) window.showToast(...)` caller (inv_config.js,
// inv_settings.js, duplicate_picker.js). Publish it so those toasts actually fire.
window.showToast = showToast;

// --- Escape-to-dismiss for toasts (buglist 2026-05-30 wizard/attribute bullet:
// "hitting escape on a toast should cancel the toast"). Escape priority ladder:
//   1. an open mountOverlay owns Escape (it closes itself via its OWN
//      capture-phase handler — we yield to it),
//   2. otherwise a visible toast intercepts Escape and dismisses the newest one,
//   3. otherwise Escape falls through untouched to whatever else handles it
//      (a Bootstrap modal's Escape-to-close, the Location Manager handler, etc).
//
// We register a single capture-phase listener on `document` so it runs BEFORE
// Bootstrap's bubble-phase modal keydown — that's what lets a toast win over a
// modal-close when both are on screen (Derek's case: an info/error toast raised
// from inside the open wizard). The event is only consumed when we actually
// dismiss a toast, so overlays and modals keep their normal Escape behavior
// whenever no toast is up. inv_core loads before any overlay mounts, so this
// capture handler is ordered ahead of overlay ones — the overlay-present
// early-return below correctly yields the still-propagating event to the
// overlay's own (later-registered) capture handler.
if (!window.__fccToastEscapeBound) {
    window.__fccToastEscapeBound = true;
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        // A mountOverlay is the foreground dialog — let its handler close it.
        if (document.querySelector('[data-overlay-mount="1"]')) return;
        const c = document.getElementById('toast-container');
        if (!c) return;
        // If ANY toast element is still on screen — INCLUDING one mid fade-out
        // (opacity 0 but not yet removed) — Escape belongs to the toasts, not the
        // background modal. This closes the race Derek flagged: an Escape pressed
        // "just as a toast cleared" must NOT leak through and dismiss a background
        // modal. We consume the keypress for the whole ~300ms fade window; once
        // the DOM node is gone, Escape falls through to the modal as normal.
        const toasts = Array.from(c.querySelectorAll('.toast-msg'));
        if (!toasts.length) return;  // none present → don't swallow Escape
        e.preventDefault();
        e.stopImmediatePropagation();  // keep the underlying modal open
        // Dismiss the newest toast that isn't already fading. If every toast is
        // mid-fade there's nothing left to dismiss — but we've still safely
        // consumed the keypress so it can't reach the modal.
        const live = toasts.filter((t) => t.style.opacity !== '0');
        if (live.length) live[live.length - 1].click();
    }, true);
}

// --- PRINTER CHECK (Group 39.3) ---
// "⏳ Checking XL…" whenever FCC waits on a printer. The probe can take ~2 s for a
// powered-down printer and ~4 s for a wrong key, and the screen used to show
// nothing new. One pinned pill for clicks and scans alike (a scan has no pressed
// control to spin): it shows after PRINTER_CHECK_DELAY_MS (a fast answer never
// flashes it), goes when the probe settles, and on a client timeout says the
// printer didn't answer and logs a WARNING. Deliberately NOT a .toast-msg:
// Escape dismisses the newest toast, and the pill must never swallow an Escape
// meant for a modal. Server-side waits label the processing dim instead
// (setProcessing's `label`, from printerLabelForTarget).
const PRINTER_CHECK_DELAY_MS = 300;
const PRINTER_CHECK_TIMEOUT_MS = 3000;
window.PRINTER_CHECK_DELAY_MS = PRINTER_CHECK_DELAY_MS;
window.PRINTER_CHECK_TIMEOUT_MS = PRINTER_CHECK_TIMEOUT_MS;
let _printerPillGen = 0;
const _printerCheckPill = (text, tone) => {
    let pill = document.getElementById('fcc-printer-check-pill');
    if (!text) { if (pill) pill.remove(); return; }
    if (!pill) {
        pill = document.createElement('div');
        pill.id = 'fcc-printer-check-pill';
        pill.setAttribute('role', 'status');
        pill.style.cssText = 'position:fixed; top:14px; left:50%; transform:translateX(-50%); z-index:11000;'
            + ' padding:6px 16px; border-radius:16px; font-weight:bold; font-size:0.95rem;'
            + ' box-shadow:0 2px 10px rgba(0,0,0,0.5); pointer-events:none;';
        document.body.appendChild(pill);
    }
    const warn = tone === 'warn';
    pill.textContent = text;
    pill.style.background = warn ? '#4a3200' : '#1f3b57';
    pill.style.color = warn ? '#ffd27a' : '#cfe6ff';
    pill.style.border = warn ? '1px solid #ffb74d' : '1px solid #5ba7e8';
};

// Resolve to what `promise` resolves to, or to `fallback` when it rejects or
// the client gives up after `timeoutMs` (then the pill warns and a WARNING is
// logged). The probe fails open either way: callers never block a move on it.
window.withPrinterCheck = (printerName, promise, { timeoutMs = PRINTER_CHECK_TIMEOUT_MS, fallback = null } = {}) => {
    const name = printerName || 'the printer';
    const gen = ++_printerPillGen;
    const showTimer = setTimeout(() => { if (gen === _printerPillGen) _printerCheckPill(`⏳ Checking ${name}…`); },
        PRINTER_CHECK_DELAY_MS);
    let giveUpTimer = null;
    const giveUp = new Promise((resolve) => { giveUpTimer = setTimeout(() => resolve({ __timedOut: true }), timeoutMs); });
    return Promise.race([Promise.resolve(promise).catch(() => fallback), giveUp]).then((v) => {
        clearTimeout(showTimer);
        clearTimeout(giveUpTimer);
        if (v && v.__timedOut) {
            if (gen === _printerPillGen) {
                _printerCheckPill(`⚠️ ${name} didn't answer — FCC couldn't check whether it is printing`, 'warn');
                setTimeout(() => { if (gen === _printerPillGen) _printerCheckPill(null); }, 4000);
            }
            if (window.logClientEvent) window.logClientEvent(
                `⚠️ ${name} didn't answer within ${Math.round(timeoutMs / 1000)} s — FCC couldn't check whether it is printing`,
                'WARNING');
            return fallback;
        }
        if (gen === _printerPillGen) _printerCheckPill(null);
        return v;
    });
};

// /api/printer_state, telling "idle" apart from "couldn't ask":
// {active, known, reason, state, printer_name}. `reason` is the route's
// (no_credentials, prusalink_unreachable, not_in_printer_map, ...).
window.fetchPrinterStateDetailed = (toolheadLocId) => {
    const none = (reason) => ({ active: false, known: false, reason, state: null, printer_name: null });
    if (!toolheadLocId) return Promise.resolve(none('no_toolhead'));
    return fetch(`/api/printer_state/${encodeURIComponent(toolheadLocId)}`)
        .then(r => (r.ok ? r.json() : null))
        .then(d => (d ? {
            active: !!(d.known && d.is_active),
            known: !!d.known,
            reason: d.reason || null,
            state: d.state || null,
            printer_name: d.printer_name || null,
        } : none('http_error')))
        .catch(() => none('unreachable'));
};

// The printer that owns a head, so the pill can name it before the probe
// answers: state.printerMap ({name: [{location_id}]}) when a view loaded it,
// else the Printer rows in state.allLocations (Group 39 review, frontend-13:
// only the Feeds editor and a toolhead's Quick-Swap view fill printerMap, so a
// fresh dashboard's dim named no printer). A Printer row carries Name and
// toolheads[].location_id; a dual-role printer (the Core One) is its own head.
// null when unknown.
window.printerNameForHead = (locId) => {
    const id = String(locId || '').toUpperCase();
    if (!id) return null;
    const pm = (typeof state !== 'undefined' && state && state.printerMap) || null;
    if (pm) {
        for (const [name, heads] of Object.entries(pm)) {
            if ((heads || []).some(h => String((h && h.location_id) || '').toUpperCase() === id)) return name;
        }
    }
    const rows = (typeof state !== 'undefined' && state && Array.isArray(state.allLocations)) ? state.allLocations : [];
    for (const row of rows) {
        if (!row || row.Type !== 'Printer') continue;
        const heads = Array.isArray(row.toolheads) ? row.toolheads : [];
        if (String(row.LocationID || '').toUpperCase() === id
            || heads.some(h => String((h && h.location_id) || '').toUpperCase() === id)) {
            return row.Name || row.LocationID;
        }
    }
    return null;
};

// A client probe of a head, with the pill and the timeout race (every client
// probe gets it; doAssign's used to wait on the server with no cap).
window.checkPrinterForHead = (locId, { timeoutMs = PRINTER_CHECK_TIMEOUT_MS } = {}) => {
    const name = window.printerNameForHead(locId) || locId;
    return window.withPrinterCheck(name, window.fetchPrinterStateDetailed(locId), {
        timeoutMs,
        fallback: { active: false, known: false, reason: 'timeout', state: null, printer_name: name },
    });
};

// The one line an overlay adds when FCC couldn't ask the printer, or '' when it
// could (or the target isn't a printer head). No login is not "unreachable":
// the fix is entering it, not checking the network.
window.printerCheckNote = (detail, fallbackName) => {
    if (!detail || detail.known || detail.reason === 'not_in_printer_map' || detail.reason === 'no_toolhead') return '';
    const name = detail.printer_name || fallbackName || 'the printer';
    if (detail.reason === 'no_credentials') {
        return `ℹ️ FCC has no login for ${name} — add it in Config's printer credentials.`;
    }
    return `ℹ️ Couldn't reach ${name} — FCC can't tell whether it is printing.`;
};

// The dim's label for a server-side wait that implies a printer: a toolhead
// gives its printer; a Dryer Box slot gives its bound head's printer. null
// (no label, the dim exactly as before) when no printer is implied.
window.printerLabelForTarget = (locId, slot = null) => {
    const id = String(locId || '').toUpperCase();
    if (!id) return null;
    let head = id;
    const rows = (typeof state !== 'undefined' && state && state.allLocations) || [];
    const row = rows.find(l => String(l.LocationID || '').toUpperCase() === id);
    if (row && row.Type === 'Dryer Box') {
        const extra = (row.extra && typeof row.extra === 'object') ? row.extra : {};
        const targets = (extra.slot_targets && typeof extra.slot_targets === 'object') ? extra.slot_targets : {};
        head = slot != null ? (targets[String(slot)] || null) : null;
    }
    const name = head ? window.printerNameForHead(head) : null;
    return name ? `⏳ Checking ${name}…` : null;
};

// `opts.label` (Group 39.3): a label centred on the dim after
// PRINTER_CHECK_DELAY_MS, naming the printer FCC waits on. No label leaves the
// dim exactly as before; the old one-argument call still works.
const setProcessing = (s, opts = {}) => {
    let ov = document.getElementById('processing-overlay');
    if (!ov) { ov = document.createElement('div'); ov.id = 'processing-overlay'; ov.style.cssText = "display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:9999;"; document.body.appendChild(ov); }
    state.processing = s; ov.style.display = s ? 'block' : 'none';
    clearTimeout(setProcessing._labelTimer);
    const old = ov.querySelector('.fcc-processing-label');
    if (old) old.remove();
    if (s && opts && opts.label) {
        setProcessing._labelTimer = setTimeout(() => {
            if (!state.processing) return;
            const el = document.createElement('div');
            el.className = 'fcc-processing-label';
            el.setAttribute('role', 'status');
            el.textContent = opts.label;
            el.style.cssText = 'position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);'
                + ' background:#1f3b57; color:#cfe6ff; border:1px solid #5ba7e8; padding:10px 18px;'
                + ' border-radius:18px; font-weight:bold; font-size:1.05rem;';
            ov.appendChild(el);
        }, PRINTER_CHECK_DELAY_MS);
    }
};

// UI-lockout guard (2026-06-12): fetch with a hard wall-clock timeout so a hung
// request — the only way an overlay-clearing .catch can be skipped — can't
// strand the z-index:9999 #processing-overlay (which gates ALL input). On
// timeout AbortSignal.timeout rejects the promise, so the caller's existing
// .catch / .finally clears state. ~15s is well above a healthy Spoolman /
// PrusaLink write. Use for any fetch whose handler toggles setProcessing.
window.fetchT = (url, opts = {}, ms = 15000) =>
    fetch(url, { ...opts, signal: opts.signal || AbortSignal.timeout(ms) });

// L286 final: the click-to-toggle indicator is the only pause path. The
// old onmouseenter/onmouseleave hover-pause was removed in the dashboard
// template — it caused accidental pauses Derek didn't realize were active.
// `window.logsStickyPaused` mirrors `state.logsPaused`; kept as a separate
// flag so tests + future callers can probe the "user explicitly paused"
// signal without coupling to the polling internal.
window.logsStickyPaused = false;
const pauseLogs = (isPaused) => {
    state.logsPaused = isPaused;
    window.logsStickyPaused = isPaused;
    if (!isPaused) {
        // Resuming: the paused ticks kept storing the content hash without
        // rewriting the list, so an unchanged-hash payload would short-circuit
        // and leave the frozen DOM on screen. Drop the hash and force one
        // render so resume snaps straight to current state.
        state.lastLogHash = null;
        if (typeof updateLogState === 'function') updateLogState(true);
    }
    const el = document.getElementById('log-status');
    if (el) {
        if (isPaused) { el.innerText = "PAUSED ⏸ (click to resume)"; el.style.color = "#fc0"; el.classList.remove('text-light'); }
        else { el.innerText = "Auto-Refresh ON (click to pause)"; el.style.color = "#0f0"; el.classList.remove('text-light'); }
    }
};

// Click-to-toggle from the log-status indicator. RECENT_LOGS is bounded
// at 50 server-side, so resume always backfills with whatever ticked while
// the user was reading.
window.toggleLogsStickyPause = () => {
    pauseLogs(!state.logsPaused);
};

// --- GRAPHICS HELPERS ---
const generateSafeQR = (elementId, text, size) => {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            const el = document.getElementById(elementId);
            if (el) {
                el.innerHTML = "";
                try {
                    new QRCode(el, { text: text, width: size, height: size, correctLevel: QRCode.CorrectLevel.L });
                } catch (e) { }
            }
        });
    });
};

// --- Scan-confirmable dialog registry ----------------------------------------
// When a confirm overlay (active-print warning, etc.) wants to accept QR-code
// confirmations alongside its mouse/keyboard buttons, it registers itself here
// with a unique session id. Two QR codes are rendered in the dialog encoding
// `CMD:CONFIRM:<sid>` and `CMD:CANCEL:<sid>`. The scan handler in inv_cmd.js
// looks up the session and fires the appropriate callback, then clears the
// entry so a stale QR scanned later can't re-fire.
//
// Why session ids: prevents a printed QR or one captured from another browser
// session firing into a different dialog. The id is rotated on every dialog
// open and torn down on close.
window._fccActiveConfirms = window._fccActiveConfirms || {};
let _fccConfirmSeq = 0;

/**
 * Mount two QR codes (~70px each) inside `host` element next to the existing
 * Yes / No buttons. The QRs encode CMD:CONFIRM / CMD:CANCEL with a session id
 * so a scan triggers the same callback as clicking the matching button.
 *
 * @param {Object} opts
 *   host:   DOM node to mount the QR row into (typically the dialog body).
 *   onConfirm: () => void  — fired on CMD:CONFIRM scan or [Yes] click.
 *   onCancel:  () => void  — fired on CMD:CANCEL scan or [No] click.
 *   confirmLabel: string, default "Scan to Confirm"
 *   cancelLabel:  string, default "Scan to Cancel"
 *   onStore: () => void — optional (Group 40.3): a third QR between the two,
 *     encoding CMD:STORE:<sid>, for the "Just store it" answer.
 *   storeLabel: string, default "Scan to Store"
 *   theme: 'warning' | 'info' | 'danger' — drives the QR card border tint.
 *
 * @returns {{sessionId: string, cleanup: function}} cleanup() removes the QR
 *   row from the DOM and unregisters the session. Call from your dialog's
 *   close handler so a late scan can't re-fire after the user dismissed.
 */
window.attachConfirmQRs = (opts) => {
    if (!opts || !opts.host) return { sessionId: '', cleanup: () => {} };
    const host = opts.host;
    const sid = `fcc-cqr-${++_fccConfirmSeq}-${Date.now().toString(36)}`;
    const theme = opts.theme || 'warning';
    const palette = {
        warning: { border: '#ff8800', tint: 'rgba(255,136,0,0.12)', confirmBg: '#1a1208', cancelBg: '#0f1014' },
        info:    { border: '#4fa2c9', tint: 'rgba(79,162,201,0.12)', confirmBg: '#0d1a20', cancelBg: '#0f1014' },
        danger:  { border: '#dc3545', tint: 'rgba(220,53,69,0.12)', confirmBg: '#1c0c0e', cancelBg: '#0f1014' },
    }[theme] || { border: '#ff8800', tint: 'rgba(255,136,0,0.12)', confirmBg: '#1a1208', cancelBg: '#0f1014' };

    const hasStore = typeof opts.onStore === 'function';
    const row = document.createElement('div');
    row.id = `${sid}-row`;
    row.className = 'fcc-confirm-qr-row';
    row.style.cssText = 'display:flex; gap:14px; justify-content:center; margin-top:14px; padding-top:12px; border-top:1px dashed #444;';
    const storeCell = hasStore ? `
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
            <div style="background:#0d1a20; border:2px solid #4fa2c9; border-radius:6px; padding:6px;">
                <div id="${sid}-store-qr" style="background:#fff; padding:4px; border-radius:3px; line-height:0;"></div>
            </div>
            <div style="font-size:0.72rem; color:#8fd3f0; font-weight:700; letter-spacing:0.5px; text-transform:uppercase;">📷 ${opts.storeLabel || 'Scan to Store'}</div>
        </div>` : '';
    row.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
            <div style="background:${palette.confirmBg}; border:2px solid ${palette.border}; border-radius:6px; padding:6px;">
                <div id="${sid}-yes-qr" style="background:#fff; padding:4px; border-radius:3px; line-height:0;"></div>
            </div>
            <div style="font-size:0.72rem; color:${palette.border}; font-weight:700; letter-spacing:0.5px; text-transform:uppercase;">📷 ${opts.confirmLabel || 'Scan to Confirm'}</div>
        </div>${storeCell}
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
            <div style="background:${palette.cancelBg}; border:2px solid #6c757d; border-radius:6px; padding:6px;">
                <div id="${sid}-no-qr" style="background:#fff; padding:4px; border-radius:3px; line-height:0;"></div>
            </div>
            <div style="font-size:0.72rem; color:#adb5bd; font-weight:700; letter-spacing:0.5px; text-transform:uppercase;">📷 ${opts.cancelLabel || 'Scan to Cancel'}</div>
        </div>
    `;
    host.appendChild(row);

    // Generate the QR codes themselves (uses the same lib generateSafeQR uses).
    generateSafeQR(`${sid}-yes-qr`, `CMD:CONFIRM:${sid}`, 70);
    if (hasStore) generateSafeQR(`${sid}-store-qr`, `CMD:STORE:${sid}`, 70);
    generateSafeQR(`${sid}-no-qr`, `CMD:CANCEL:${sid}`, 70);

    // Register the callbacks. All fire-then-clear so a duplicate scan can't
    // re-trigger after the dialog closed.
    window._fccActiveConfirms[sid] = {
        onConfirm: () => {
            const entry = window._fccActiveConfirms[sid];
            if (!entry) return;
            delete window._fccActiveConfirms[sid];
            try { opts.onConfirm && opts.onConfirm(); } catch (e) { console.error('[confirm-qr]', e); }
        },
        onStore: hasStore ? () => {
            const entry = window._fccActiveConfirms[sid];
            if (!entry) return;
            delete window._fccActiveConfirms[sid];
            try { opts.onStore(); } catch (e) { console.error('[confirm-qr]', e); }
        } : null,
        onCancel: () => {
            const entry = window._fccActiveConfirms[sid];
            if (!entry) return;
            delete window._fccActiveConfirms[sid];
            try { opts.onCancel && opts.onCancel(); } catch (e) { console.error('[confirm-qr]', e); }
        },
    };

    return {
        sessionId: sid,
        cleanup: () => {
            delete window._fccActiveConfirms[sid];
            try { row.remove(); } catch (_) { /* noop */ }
        },
    };
};

/**
 * Looked up by the scan handler when a CMD:CONFIRM:<sid> or CMD:CANCEL:<sid>
 * scan arrives. Returns true if the scan was handled (matched an active
 * dialog), false otherwise so the caller can fall through to normal scan
 * dispatch.
 */
window.routeConfirmScan = (text) => {
    if (!text) return false;
    // Match the prefix case-insensitively but preserve the session id's
    // case verbatim — sid contains base-36 digits/letters that uppercase
    // would mangle (broke registry lookup in earlier draft).
    const m = String(text).match(/^[Cc][Mm][Dd]:(CONFIRM|CANCEL|STORE|confirm|cancel|store):(.+)$/);
    if (!m) return false;
    const action = m[1].toUpperCase();
    const sid = m[2].trim();
    // Match either the exact sid OR — if the user printed an unscoped QR —
    // the most-recently-registered active confirm. The exact-sid path is the
    // safe one. Unscoped matches are NOT supported intentionally so a stale
    // printed QR can't accidentally fire.
    const entry = window._fccActiveConfirms && window._fccActiveConfirms[sid];
    if (!entry) return false;
    if (action === 'CONFIRM') entry.onConfirm();
    else if (action === 'STORE') {
        // Group 40.3: only a dialog that offered "Just store it" has a STORE QR.
        if (entry.onStore) entry.onStore();
    }
    else entry.onCancel();
    return true;
};

const getHexDark = (hex, opacity = 0.3) => {
    if (!hex) return 'rgba(0,0,0,0.5)';
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    const r = parseInt(hex.substring(0, 2), 16), g = parseInt(hex.substring(2, 4), 16), b = parseInt(hex.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
};


/* [Search Anchor] */
const getFilamentStyle = (colorStr, direction = 'longitudinal') => {
    // [ALEX FIX] Robust Color Parsing (Shared by Buffer & Modals)
    if (!colorStr) colorStr = "333";

    // 1. Scrub the input (remove quotes, extra spaces)
    let cleanStr = colorStr.toString().replace(/['"]/g, '').trim();
    if (!cleanStr) cleanStr = "333";

    let colors = [];

    // 2. Handle Lists (JSON or CSV)
    if (cleanStr.startsWith('[')) {
        try { colors = JSON.parse(cleanStr); }
        catch (e) { colors = [cleanStr]; }
    } else {
        colors = cleanStr.split(',').map(c => c.trim());
    }

    // 3. Normalize Hex Codes
    colors = colors.map(c => {
        // If it's already a valid hex format like #FFF or #112233, keep it
        // Otherwise, strip non-hex chars and add hash
        if (c.startsWith('#') && (c.length === 4 || c.length === 7)) return c;
        let hex = c.replace(/[^a-fA-F0-9]/g, '');
        return hex ? '#' + hex : '#333';
    });

    // Save full colors before capping for coaxial rendering
    const fullColors = [...colors];

    // No artificial limit! Let linear-gradient sweep display all assigned colors

    // 4. Force at least 2 colors for interpolation
    const isSolid = colors.length === 1 || (colors.length > 1 && colors[0] === colors[1]);
    if (colors.length === 1) colors.push(colors[0]);

    // 5. Generate Physical Frame Gradients (Buttons)
    let frameGrad;
    let innerGrad;

    if (direction === 'coaxial' && !isSolid) {
        if (fullColors.length === 1) fullColors.push(fullColors[0]);
        const sliceSize = 100.0 / fullColors.length;
        const conicStops = fullColors.map((c, i) => `${c} ${i === 0 ? "0%" : (i * sliceSize).toFixed(2) + "%"} ${((i + 1) * sliceSize).toFixed(2) + "%"}`).join(', ');
        frameGrad = `conic-gradient(${conicStops})`;
        
        const darkStops = fullColors.map((c, i) => `${getHexDark(c, 0.8)} ${i === 0 ? "0%" : (i * sliceSize).toFixed(2) + "%"} ${((i + 1) * sliceSize).toFixed(2) + "%"}`).join(', ');
        innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), conic-gradient(${darkStops})`;
    } else {
        if (isSolid) {
            let hex = colors[0].replace('#', '');
            if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
            const r = parseInt(hex.substring(0, 2), 16) || 0;
            const g = parseInt(hex.substring(2, 4), 16) || 0;
            const b = parseInt(hex.substring(4, 6), 16) || 0;
            // Smoothly fade the base color into partial transparency to create a deeply rich vibrant bottom
            frameGrad = `linear-gradient(to bottom, rgba(${r},${g},${b},1) 0%, rgba(${r},${g},${b},0.6) 100%)`;
            innerGrad = `linear-gradient(to bottom, rgba(${r},${g},${b},0.4) 0%, rgba(${r},${g},${b},0.1) 100%)`;
        } else {
            // Multi-color filaments use a diagonal stripe or sweep to showcase all components
            frameGrad = `linear-gradient(135deg, ${colors.join(', ')})`;
            const gradColors = colors.map(c => getHexDark(c, 0.8));
            innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), linear-gradient(135deg, ${gradColors.join(', ')})`;
        }
    }

    // 6. Black border fix & Texture
    let borderStyle = "";
    if (colors.length > 0) {
        let isAllDark = true;
        for (let c of colors) {
            let hex = c.replace('#', '');
            if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
            const r = parseInt(hex.substring(0, 2), 16), g = parseInt(hex.substring(2, 4), 16), b = parseInt(hex.substring(4, 6), 16);
            if (r > 55 || g > 55 || b > 55) { isAllDark = false; break; }
        }
        if (isAllDark) {
            borderStyle = true; // Boolean flag legacy passthrough
            // Explicit override for pure black colors to guarantee contrast rim (fades #555 to deep black)
            frameGrad = `linear-gradient(to bottom, #555555 0%, #1a1a1a 100%)`;
            innerGrad = `linear-gradient(to bottom, rgba(30,30,30,0.95) 0%, rgba(5,5,5,0.9) 100%)`;
        }
    }

    return { frame: frameGrad, inner: innerGrad, border: borderStyle, base: colors[0], isSolid: isSolid };
};
window.getFilamentStyle = getFilamentStyle;

// Render a small color swatch <span> that respects multi-color filaments
// (CSV / JSON list / coaxial). Routes through getFilamentStyle so the
// gradient logic is the SAME as the cards' frame backgrounds — fixes the
// "split(',')[0]" bug class where coextruded spools showed only the first
// component color in chips/swatches. Use this helper for any new swatch
// rather than inlining `background:#${color.split(',')[0]}`.
const makeSwatchHtml = (color, direction = 'longitudinal', opts = {}) => {
    const size = opts.size || 14;
    const borderColor = opts.borderColor || '#fff';
    const borderWidth = opts.borderWidth != null ? opts.borderWidth : 1;
    const margin = opts.marginRight != null ? opts.marginRight : 4;
    const extra = opts.extraStyle || '';
    let bg;
    try {
        bg = getFilamentStyle(color, direction).frame;
    } catch (e) {
        // getFilamentStyle handles every reasonable input; this catch is
        // a belt-and-suspenders fallback for truly malformed colors so a
        // single bad row never breaks an entire grid render.
        const safe = String(color || '555555').split(',')[0].replace(/[^a-fA-F0-9]/g, '') || '555555';
        bg = '#' + safe;
    }
    return `<span style="display:inline-block;width:${size}px;height:${size}px;border-radius:50%;background:${bg};border:${borderWidth}px solid ${borderColor};vertical-align:middle;margin-right:${margin}px;flex-shrink:0;${extra}"></span>`;
};
window.makeSwatchHtml = makeSwatchHtml;

// Normalize a raw hex string to canonical `#rrggbb`, or null if it isn't a
// valid color. Single source of truth for the color surfaces (30.1 details-
// modal RGB display, 30.2 search-box live sync) — folds in the Group 23.1
// import-apply hardening: trim, optional leading '#', lowercase, expand a
// 3-digit shorthand (`fff` → `ffffff`), strict 6-digit validate. Returns null
// for garbage so callers can reject without clobbering.
const normalizeHex = (raw) => {
    let h = String(raw == null ? '' : raw).trim().replace(/^#/, '').toLowerCase();
    if (/^[0-9a-f]{3}$/.test(h)) h = h.split('').map(c => c + c).join('');
    return /^[0-9a-f]{6}$/.test(h) ? `#${h}` : null;
};
window.normalizeHex = normalizeHex;

const hexToRgb = (hex) => {
    // 30.1 — route through normalizeHex so 3-digit shorthand expands and
    // garbage rejects. The old bare `parseInt(hex,16)` mis-parsed shorthand
    // (`fff` → 4095) and returned NaN channels for invalid input.
    const norm = normalizeHex(hex);
    if (!norm) return { r: '', g: '', b: '' };
    const i = parseInt(norm.slice(1), 16);
    return { r: (i >> 16) & 255, g: (i >> 8) & 255, b: i & 255 };
};
window.hexToRgb = hexToRgb;

// Human-readable "rgb(r, g, b)" for a hex, or '' when the hex is blank/invalid.
// Shared by the details-modal RGB line (30.1) and the search-box readout (30.2).
const rgbText = (hex) => {
    const { r, g, b } = hexToRgb(hex);
    return r === '' ? '' : `rgb(${r}, ${g}, ${b})`;
};
window.rgbText = rgbText;

// Group-34 Phase 0 — the shared parent_id tree primitive. The
// LocationID→parent_id walk was duplicated across _renderLocationsPayload (the
// LM render), _locDescendants (cycle guard) and _locBreadcrumbChain (the Edit
// modal breadcrumb); extract it once so those three — and the Phase-2
// add-redesign tree picker — all read identical structure. Returns:
//   byId       Map(UC id -> row)
//   parentOf   Map(UC id -> UC parent id | null) — null when the parent isn't a
//              real row (orphan floats to root); independent of shouldFloat
//   childrenOf Map(UC parent id -> [rows]) — attached only under real-row
//              parents, minus any row shouldFloat() pulls to root
//   roots      [rows] with no real parent (or floated)
// `uc` defaults to the toUpperCase() both existing call sites already use (no
// trim, so re-wiring them is byte-identical). `shouldFloat(row)` optionally
// forces a row to root even under a real parent (the render's pin-printers
// mode) WITHOUT disturbing parentOf. No sorting — callers order as they need.
window.buildLocationTree = function buildLocationTree(rows, opts) {
    opts = opts || {};
    const uc = opts.uc || ((v) => String(v == null ? '' : v).toUpperCase());
    const shouldFloat = opts.shouldFloat || null;
    const list = Array.isArray(rows) ? rows : [];
    const byId = new Map();
    list.forEach(r => byId.set(uc(r.LocationID), r));
    const parentOf = new Map();
    const childrenOf = new Map();
    const roots = [];
    list.forEach(r => {
        const pid = r.parent_id != null ? uc(r.parent_id) : null;
        const realParent = !!(pid && byId.has(pid));
        parentOf.set(uc(r.LocationID), realParent ? pid : null);
        if (realParent && !(shouldFloat && shouldFloat(r))) {
            if (!childrenOf.has(pid)) childrenOf.set(pid, []);
            childrenOf.get(pid).push(r);
        } else {
            roots.push(r);
        }
    });
    return { byId, parentOf, childrenOf, roots };
};

// --- DATA FETCHERS ---
// L28 polling guard: see updateLogState for rationale. Same pattern.
// L206: split fetch + render so the bulk-pulse dispatcher can hand
// pre-fetched data into _renderLocationsPayload without another round-trip.
let _fetchLocationsInflight = false;
const _renderLocationsPayload = (d) => {
    if (!d) return;
    // The bulk endpoint can pass {error: ...} when locations.json is
    // corrupt — surface to console and bail out (the locations table
    // will simply not update this tick).
    if (!Array.isArray(d)) {
        if (d && d.error) console.warn("locations payload error:", d.error);
        return;
    }
    // The body below was previously the entire .then() callback of
    // fetchLocations. Pulled out as-is so the legacy fetch path and the
    // bulk-pulse path produce identical DOM.
            // [ALEX FIX] Ensure Unassigned is in the list
            let hasUnassigned = d.some(l => l.LocationID === 'Unassigned');
            if(!hasUnassigned) {
                d.unshift({
                    LocationID: 'Unassigned',
                    Name: 'Unassigned Spools',
                    Type: 'Virtual',
                    Occupancy: '--',
                    Synthesized: true
                });
            }

            // L271 Phase 3.5 — TRUE multi-level tree. parent_id now stores each
            // row's IMMEDIATE parent, so the table renders a recursive tree
            // (room → printer → toolhead, cart → rows) instead of the old flat
            // 2-level list. Tree mode applies only when sorting by LocationID;
            // the other sort columns stay a flat sorted list.
            if (!state.locCollapsed) state.locCollapsed = new Set();
            const pinPrinters = _readPinPrinters();
            const upper = (v) => String(v == null ? '' : v).toUpperCase();
            const isPrinterRow = (r) => String(r.Type || '').toLowerCase() === 'printer';
            // Group-34: the per-row "➕ Add child" affordance is offered on shelf/leaf
            // kinds only. Suppressed on printer topology (Printer + toolhead types —
            // their source of truth is the printer-map editor, not the parent_id tree,
            // so a toolhead created via api_save_location would be invisible to
            // Quick-Swap + print-deduct) and on synthetic/virtual rows.
            const NO_ADD_CHILD_TYPES = new Set(['printer', 'tool head', 'mmu slot',
                'no mmu direct load', 'virtual', 'virtual room', 'unknown',
                'spoolman native', 'unassigned']);
            const canAddChild = (r) => {
                // The synthetic Unassigned/UNKNOWN buckets are identified by id (the
                // UNKNOWN row can carry a non-'Unknown' Type), so guard the id too —
                // not just the Type suppress-set.
                const idU = String(r.LocationID || '').trim().toUpperCase();
                if (idU === 'UNASSIGNED' || idU === 'UNKNOWN') return false;
                const t = String(r.Type || '').trim().toLowerCase();
                return !!t && !NO_ADD_CHILD_TYPES.has(t);
            };

            // The always-pinned virtual rows live OUTSIDE the tree.
            const unassignedRow = d.find(l => upper(l.LocationID) === 'UNASSIGNED');
            const unknownRow = d.find(l => l !== unassignedRow && (upper(l.Type) === 'UNKNOWN' || upper(l.LocationID) === 'UNKNOWN'));
            const bodyRows = d.filter(l => l !== unassignedRow && l !== unknownRow);

            // Sibling / flat comparator: printers first (LocationID mode), then
            // by the active column.
            const cmp = (a, b) => {
                if (state.locSortBy === 'LocationID') {
                    const ap = isPrinterRow(a), bp = isPrinterRow(b);
                    if (ap !== bp) return (ap ? -1 : 1) * state.locSortDir;
                }
                let valA = a[state.locSortBy] || '';
                let valB = b[state.locSortBy] || '';
                if (state.locSortBy === 'Occupancy') {
                    const parseOcc = (v) => {
                        if (v == null || v === '--' || v === '') return -1;
                        if (typeof v === 'string') return parseInt(v.split('/')[0]) || 0;
                        return v;
                    };
                    valA = parseOcc(a.OccupancyRaw != null ? a.OccupancyRaw : valA);
                    valB = parseOcc(b.OccupancyRaw != null ? b.OccupancyRaw : valB);
                } else {
                    if (typeof valA === 'string') valA = valA.toLowerCase();
                    if (typeof valB === 'string') valB = valB.toLowerCase();
                }
                if (valA < valB) return -1 * state.locSortDir;
                if (valA > valB) return 1 * state.locSortDir;
                return 0;
            };

            // Build the display order: tree DFS (LocationID) or flat (others).
            // Each entry is {row, depth, ancestors:[upperIds], hasKids} or
            // {divider: label}.
            const display = [];
            if (state.locSortBy === 'LocationID') {
                // A row attaches to its parent UNLESS the parent isn't a real
                // row (orphan → root) or pin-mode floats printers to the top.
                // buildLocationTree (inv_core Phase-0 helper) owns the walk; the
                // pin-float is passed as shouldFloat so behavior is unchanged.
                const { childrenOf, roots } = window.buildLocationTree(bodyRows, {
                    uc: upper,
                    shouldFloat: (r) => pinPrinters && isPrinterRow(r),
                });
                const visited = new Set();
                const visit = (row, depth, ancestors) => {
                    const id = upper(row.LocationID);
                    if (visited.has(id)) return;  // cycle / dup guard
                    visited.add(id);
                    const kids = (childrenOf.get(id) || []).slice().sort(cmp);
                    display.push({ row, depth, ancestors, hasKids: kids.length > 0 });
                    const childAnc = ancestors.concat([id]);
                    kids.forEach(k => visit(k, depth + 1, childAnc));
                };
                if (pinPrinters) {
                    const printerRoots = roots.filter(isPrinterRow).sort(cmp);
                    const otherRoots = roots.filter(r => !isPrinterRow(r)).sort(cmp);
                    if (printerRoots.length) {
                        display.push({ divider: '🖨️ Printers' });
                        printerRoots.forEach(r => visit(r, 0, []));
                        display.push({ divider: '📍 Rooms & Storage' });
                    }
                    otherRoots.forEach(r => visit(r, 0, []));
                } else {
                    roots.sort(cmp).forEach(r => visit(r, 0, []));
                }
                // Safety net: a cycle would orphan its members from every root.
                // Append anything unvisited as a flat root so no row vanishes.
                bodyRows.forEach(r => { if (!visited.has(upper(r.LocationID))) visit(r, 0, []); });
            } else {
                bodyRows.slice().sort(cmp).forEach(r => display.push({ row: r, depth: 0, ancestors: [] }));
            }

            // Assemble: Unassigned (top) → body → UNKNOWN (bottom).
            const ordered = [];
            if (unassignedRow) ordered.push({ row: unassignedRow, depth: 0, ancestors: [] });
            ordered.push(...display);
            if (unknownRow) ordered.push({ row: unknownRow, depth: 0, ancestors: [] });

            const rowOnly = ordered.filter(e => e.row).map(e => e.row);
            state.allLocations = rowOnly;
            // Group 45.8: an openManage() that came before this first load (a
            // Printer Status tile clicked in the first seconds; the widget paints
            // from the first heartbeat) was parked; open it now.
            if (!state.locationsLoaded) {
                state.locationsLoaded = true;
                const parked = window._fccPendingManageId;
                window._fccPendingManageId = null;
                if (parked && window.openManage) setTimeout(() => window.openManage(parked), 0);
            }

            // L271 Phase 3.5 (review fix #15): prune collapse state to live parent
            // nodes so a deleted/renamed id can't resurrect as collapsed on a
            // later row that reuses the same id.
            const _liveParents = new Set(display.filter(e => e.hasKids).map(e => upper(e.row.LocationID)));
            state.locCollapsed = new Set([...state.locCollapsed].filter(id => _liveParents.has(id)));

            // --- NO WIGGLE CHECK (include tree-affecting UI state) ---
            const contentHash = JSON.stringify(rowOnly) + "|" + state.locSortBy + "|" + state.locSortDir + "|pin:" + pinPrinters;
            if (state.lastLocationsHash === contentHash) { applyLocCollapse(); _syncPinPrintersBtn(); return; }
            state.lastLocationsHash = contentHash;
            // -----------------------

            // 2. Update Total Count with Pop Style
            const countEl = document.getElementById('loc-count');
            // Subtract the virtual Unassigned/UNKNOWN so they don't inflate the count.
            if (countEl) countEl.innerText = "Total Locations: " + Math.max(0, rowOnly.length - (unassignedRow ? 1 : 0) - (unknownRow ? 1 : 0));

            const table = document.getElementById('location-table');
            if (table) {
                table.innerHTML = ordered.map(entry => {
                    if (entry.divider) {
                        return `<tr class="loc-divider"><td colspan="5" style="background:#15151f; color:#9aa; font-weight:800; letter-spacing:1px; padding:6px 14px; border-top:2px solid #444; border-bottom:1px solid #2a2a3a; font-size:0.8rem; text-transform:uppercase;">${entry.divider}</td></tr>`;
                    }
                    const l = entry.row;
                    // 3. Status Pop Logic (Red/Green/White)
                    let statusHtml = '';
                    let occColor = '#fff'; // Default White (Under Capacity)

                    if (l.Occupancy && l.Occupancy !== '--') {
                        const parts = l.Occupancy.split('/');
                        if (parts.length === 2) {
                            const cur = parseInt(parts[0]);
                            const max = parseInt(parts[1]);

                            if (!isNaN(cur) && !isNaN(max)) {
                                if (cur >= max) occColor = '#ff4444';      // Red (Full or Overfilled)
                                else if (cur === 0) occColor = '#ffc107'; // Yellow (Empty)
                                else occColor = '#fff'; // White (Default)
                            }
                        }
                        // GOLD STANDARD: High Contrast Pop
                        statusHtml = `<div class="d-flex align-items-center"><span class="text-pop" style="font-weight:900; font-size:1.1rem; color:${occColor};">${l.Occupancy}</span>`;
                        if (occColor === '#ffc107') {
                            statusHtml += `<span class="text-pop" title="Empty Capacity" style="font-size:1.3rem; margin-left: 6px; line-height: 1;">⚠️</span>`;
                        }
                        statusHtml += `</div>`;
                    } else {
                        statusHtml = `<span style="color:#666; font-style:italic; font-weight:bold;">--</span>`;
                    }

                    // 4. Type Badge (Rainbow Logic + Visible Virtual)
                    let badgeClass = 'bg-secondary';
                    let badgeStyle = 'border:1px solid #555;';

                    // Color Mapping
                    const t = l.Type || '';
                    if (t.includes('Dryer')) { badgeClass = 'bg-warning text-dark'; badgeStyle = 'border:1px solid #fff;'; }
                    else if (t.includes('Storage')) { badgeClass = 'bg-primary'; badgeStyle = 'border:1px solid #88f;'; }
                    else if (t.includes('MMU')) { badgeClass = 'bg-danger'; badgeStyle = 'border:1px solid #f88;'; }
                    // L271 Phase 5 — Room > Wall Shelf > Row > Section. Wall Shelf
                    // + Row are structural groupings; Section is the spool leaf.
                    // Exact matches MUST precede the generic 'Shelf' includes
                    // ('Wall Shelf' contains 'Shelf').
                    else if (t === 'Wall Shelf') { badgeClass = 'bg-secondary'; badgeStyle = 'border:1px solid #6dd5c9; background-color:#1f5a52 !important; color:#fff;'; }
                    else if (t === 'Row') { badgeClass = 'bg-secondary'; badgeStyle = 'border:1px solid #9ad0ff; background-color:#34506e !important; color:#fff;'; }
                    else if (t === 'Section') { badgeClass = 'bg-success'; badgeStyle = 'border:1px solid #8f8;'; }
                    else if (t.includes('Shelf')) { badgeClass = 'bg-success'; badgeStyle = 'border:1px solid #8f8;'; }
                    else if (t.includes('Cart')) { badgeClass = 'bg-info text-dark'; badgeStyle = 'border:1px solid #fff;'; }
                    else if (t.includes('Printer') || t.includes('Toolhead')) { badgeClass = 'bg-dark'; badgeStyle = 'border:1px solid #f0f; background-color: #aa00ff !important; color: #fff;'; }
                    else if (t.includes('Room')) { badgeClass = 'bg-light text-dark'; badgeStyle = 'border:1px solid #fff; box-shadow: 0 0 5px rgba(255,255,255,0.5);'; }
                    // [ALEX FIX] Ghostly, Hollow Look for Virtual
                    else if (t.includes('Virtual')) { badgeClass = 'bg-transparent text-light'; badgeStyle = 'border:2px dashed #aaa; box-shadow: inset 0 0 5px rgba(255,255,255,0.2);'; }
                    // 18.1 — Unknown bucket: yellow caution band so the row
                    // stands out at the bottom of the table.
                    else if (t.includes('Unknown')) { badgeClass = 'bg-warning text-dark'; badgeStyle = 'border:1px solid #ffd54a; box-shadow: 0 0 6px rgba(255,193,7,0.6);'; }

                    const typeBadge = `<span class="badge ${badgeClass}" style="box-shadow: 1px 1px 3px rgba(0,0,0,0.5); ${badgeStyle}">${escHtml(l.Type)}</span>`;

                    // L271 Phase 3.5: depth-based indent + a real expand/collapse
                    // toggle driven by the tree (entry.hasKids), replacing the
                    // flat startsWith descendant probe. data-locid + data-ancestors
                    // let applyLocCollapse() hide a whole subtree when any ancestor
                    // is collapsed (nested collapse), independent of re-renders.
                    const lidUC = upper(l.LocationID);
                    const depth = entry.depth || 0;
                    const hasKids = !!entry.hasKids;
                    let indent = '';
                    if (state.locSortBy === 'LocationID') {
                        const pad = depth * 22;
                        let knob;
                        if (hasKids) {
                            // L271 Phase 3.5 (review fix #3): no inline onclick — the
                            // toggle is delegated off .loc-toggle + the row's data-locid
                            // (see scripts.html), so a quote in a LocationID can't break
                            // out into script.
                            knob = `<span class="loc-toggle" title="Collapse / expand" style="cursor:pointer; font-family: monospace; border: 1px solid #555; border-radius: 3px; padding: 0 4px; margin-right: 6px; color:#aaa; background:#222; user-select:none; font-size:1rem; box-shadow:inset 0 0 3px #000;">-</span>`;
                        } else if (depth > 0) {
                            knob = `<span style="display:inline-block; width: 20px; border-left: 2px solid #555; border-bottom: 2px solid #555; height: 16px; margin-right: 8px; margin-bottom: 6px;"></span>`;
                        } else {
                            knob = `<span style="display:inline-block; width: 22px;"></span>`;
                        }
                        indent = `<span style="display:inline-block; width:${pad}px;"></span>${knob}`;
                    }

                    // L271 Phase 3.5 (review fix #3/#8): JSON-encode the ancestor
                    // chain (escaped for the attribute) so a LocationID containing a
                    // space — Spoolman-native names can — survives round-trip
                    // (split(' ') would have shredded it), and a quote can't break the
                    // attribute. Every interpolated user value is escaped (stored XSS
                    // via Name / LocationID).
                    const ancAttr = escAttr(JSON.stringify(entry.ancestors || []));
                    const lidEsc = escAttr(l.LocationID);
                    // Group 41.3 (Claude's call 12): the built-in lists and a
                    // "(Room)" FCC only knows from its spools have no row to edit
                    // or delete, and the server refuses a delete of any id with no
                    // row, so a Spoolman-native row keeps only its ✏️ (saving it
                    // there makes it an FCC location). Keyed on the server's
                    // Synthesized flag, never the Type (Group 41 review): a real
                    // "Virtual Room / Zone" row, prod's blank-id "Unknown
                    // Location" row and a promoted blank-Type parent share Types
                    // with synthesized rows, and lost their buttons.
                    const synth = !!l.Synthesized;
                    const canEdit = !synth || l.Type === 'Spoolman Native';

                    return `
                <tr data-locid="${escAttr(lidUC)}" data-ancestors="${ancAttr}" id="loc-row-${lidEsc}">
                    <td class="col-id" style="font-weight:bold; color:#00d4ff; font-size:1.1rem; white-space: nowrap;">${indent}${escHtml(l.LocationID)}</td>
                    <td class="col-name text-pop-light" style="font-weight:800; font-size:1.1rem; color:#fff;">${escHtml(l.Name)}</td>
                    <td class="col-type">${typeBadge}</td>
                    <td class="col-status">${statusHtml}</td>
                    <td class="col-actions text-end" style="white-space: nowrap;">
                        <button class="btn btn-sm btn-outline-light me-1 btn-qr" data-id="${lidEsc}" title="Show QR">📱 QR</button>
                        ${canAddChild(l) ? `<button class="btn btn-sm btn-outline-success me-1 btn-add-child" data-id="${lidEsc}" title="Add a child location here">➕</button>` : ''}
                        ${canEdit ? `
                        <button class="btn btn-sm btn-outline-warning me-1 btn-edit" data-id="${lidEsc}">✏️</button>` : ''}
                        ${!synth ? `
                        <button class="btn btn-sm btn-outline-danger me-1 btn-delete" data-id="${lidEsc}">🗑️</button>` : ''}
                        <button class="btn btn-sm btn-info btn-manage fw-bold" data-id="${lidEsc}">Manage</button>
                    </td>
                </tr>`;
                }).join('');
                applyLocCollapse();
                _syncPinPrintersBtn();
            }
};

// L271 Phase 3.5 — pin-printers-to-top toggle (persisted, per the
// pre-Config-system localStorage convention). When ON, printer subtrees float
// to a pinned group at the top of the Location Manager tree for quick access.
const PIN_PRINTERS_KEY = 'fcc.locMgr.pinPrintersTop';
const _readPinPrinters = () => {
    try { return localStorage.getItem(PIN_PRINTERS_KEY) === '1'; } catch (_) { return false; }
};
const _syncPinPrintersBtn = () => {
    const btn = document.getElementById('loc-pin-printers-btn');
    if (!btn) return;
    const on = _readPinPrinters();
    // L271 Phase 3.5 (review fix #16): pin only affects the LocationID tree
    // view. In any other sort, disable + grey the button (and don't show the
    // lit "Pinned" state) so it isn't a confusing no-op.
    const treeMode = state.locSortBy === 'LocationID';
    btn.disabled = !treeMode;
    btn.style.opacity = treeMode ? '' : '0.5';
    btn.title = treeMode
        ? 'Float printers to the top of the tree for quick access'
        : 'Sort by ID to pin printers';
    const lit = on && treeMode;
    btn.classList.toggle('active', lit);
    btn.classList.toggle('btn-warning', lit);
    btn.classList.toggle('btn-outline-warning', !lit);
    btn.setAttribute('aria-pressed', lit ? 'true' : 'false');
    btn.innerHTML = on ? '📌 Printers Pinned' : '📌 Pin Printers';
};
window.toggleLocPinPrinters = () => {
    if (state.locSortBy !== 'LocationID') return;  // no-op outside the tree view
    const next = _readPinPrinters() ? '0' : '1';
    try { localStorage.setItem(PIN_PRINTERS_KEY, next); } catch (_) { /* private mode */ }
    state.lastLocationsHash = null;  // force a full re-render (tree shape changes)
    _syncPinPrintersBtn();
    fetchLocations();
};

const fetchLocations = () => {
    if (_fetchLocationsInflight) return;
    _fetchLocationsInflight = true;
    fetch('/api/locations')
        .then(r => r.json())
        .then(_renderLocationsPayload)
        .catch(e => console.warn("fetchLocations failed:", e))
        .finally(() => { _fetchLocationsInflight = false; });
};
window._renderLocationsPayload = _renderLocationsPayload;
window.fetchLocations = fetchLocations;

window.sortLocations = (col) => {
    if (state.locSortBy === col) {
        state.locSortDir *= -1;
    } else {
        state.locSortBy = col;
        state.locSortDir = 1;
    }
    state.lastLocationsHash = null; // Force DOM re-render
    fetchLocations();
};

// L271 Phase 3.5: nested collapse. State lives in state.locCollapsed (a Set of
// uppercased LocationIDs) so it survives the periodic re-render. A row is hidden
// when ANY of its ancestors is collapsed — so collapsing a room hides its
// printer AND that printer's toolheads, and re-expanding the room restores each
// descendant to its own collapsed/expanded state. function-declared (hoisted)
// so _renderLocationsPayload can call it regardless of source order.
function applyLocCollapse() {
    if (!state.locCollapsed) state.locCollapsed = new Set();
    const collapsed = state.locCollapsed;
    document.querySelectorAll('#location-table tr[data-locid]').forEach(tr => {
        // L271 Phase 3.5 (review fix #8): ancestors are JSON-encoded so a
        // LocationID containing a space round-trips intact (a space delimiter
        // would have split it and broken collapse).
        let anc = [];
        try { anc = JSON.parse(tr.dataset.ancestors || '[]'); } catch (_) { anc = []; }
        tr.style.display = anc.some(a => collapsed.has(a)) ? 'none' : '';
        const btn = tr.querySelector('.loc-toggle');
        if (btn) {
            const isColl = collapsed.has(tr.dataset.locid);
            btn.textContent = isColl ? '+' : '-';
            btn.style.color = isColl ? '#fff' : '#aaa';
            btn.style.background = isColl ? '#444' : '#222';
        }
    });
}

window.toggleLocNode = (locId) => {
    if (!state.locCollapsed) state.locCollapsed = new Set();
    const id = String(locId).toUpperCase();
    if (state.locCollapsed.has(id)) state.locCollapsed.delete(id);
    else state.locCollapsed.add(id);
    applyLocCollapse();
};

window.showGlobalQrModal = (locId) => {
    if (!locId) return;
    const safeStr = String(locId).replace(/['"]/g, '');
    generateSafeQR('loc-qr-view-container', "LOC:" + safeStr, 200);
    const labelEl = document.getElementById('loc-qr-view-label');
    if (labelEl) labelEl.innerText = "LOC:" + safeStr;
    
    if (!modals.locQrViewModal) {
        const el = document.getElementById('locQrViewModal');
        if(el) modals.locQrViewModal = new bootstrap.Modal(el);
    }
    if (modals.locQrViewModal) modals.locQrViewModal.show();
};

// L184 — log-pill state. Tracks the time of the newest entry the user
// has "seen" (i.e. that was current the last time the dashboard log
// panel was visible OR the pill overlay was opened/dismissed). Anything
// newer counts as unread. Persisted across page reloads via localStorage
// so a sticky modal stack doesn't reset the count on every refresh.
const LOG_PILL_KEY = 'fcc.logPill.lastSeenTime';
const _readLastSeenTime = () => {
    try {
        const v = localStorage.getItem(LOG_PILL_KEY);
        return v || '';
    } catch (_) { return ''; }
};
const _writeLastSeenTime = (t) => {
    try { localStorage.setItem(LOG_PILL_KEY, t || ''); } catch (_) { /* private mode */ }
};
const _updateLogPill = (logs) => {
    const pill = document.getElementById('fcc-log-pill');
    if (!pill) return;
    const lastSeen = _readLastSeenTime();
    const unseen = (logs || []).filter(l => (l.time || '') > lastSeen);
    if (unseen.length === 0) {
        pill.style.display = 'none';
        return;
    }
    const countEl = document.getElementById('fcc-log-pill-count');
    if (countEl) countEl.innerText = String(unseen.length);
    // Use !important via inline style to override any CSS display:none.
    pill.style.setProperty('display', 'inline-flex', 'important');
    pill.style.alignItems = 'center';
    // Brief flash to draw the eye to a fresh entry.
    pill.classList.remove('fcc-log-pill-flash');
    void pill.offsetWidth;  // force reflow so re-adding restarts the animation
    pill.classList.add('fcc-log-pill-flash');
};

window.openLogPillOverlay = () => {
    // Snapshot the latest logs and render them in a mountOverlay so the
    // panel sits above any modal stack. Closing marks every entry as seen.
    fetch('/api/logs').then(r => r.json()).then(d => {
        const logs = (d && d.logs) || [];
        if (logs.length) _writeLastSeenTime(logs[0].time || '');
        // Contrast note: avoid Bootstrap's `text-muted` (#6c757d) — it
        // hits ~1.4:1 against the dark overlay bg and reads as gray-on-gray.
        // Use explicit rgba(255,255,255,0.7) for low-emphasis text instead.
        const rows = logs.map(l =>
            `<div class="log-${l.type}" style="padding:2px 4px; border-bottom:1px solid #222;">[${l.time}] ${l.msg}</div>`
        ).join('') || '<div class="small p-3" style="color: rgba(255,255,255,0.7);">Activity Log is empty.</div>';
        const html = `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #0ff;
                        border-radius:8px; padding:14px 16px; min-width:420px; max-width:90vw;
                        max-height:80vh; display:flex; flex-direction:column;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div style="font-weight:bold; font-size:1.1em; color:#0ff;">📡 Activity Log</div>
                    <button id="fcc-log-pill-close" class="btn btn-sm btn-outline-info">Close</button>
                </div>
                <div style="overflow-y:auto; font-family:monospace; font-size:0.85rem;
                            background:#0a0a0a; padding:8px; border:1px solid #333; flex:1 1 auto;">
                    ${rows}
                </div>
                <div class="mt-2 small" style="color: rgba(255,255,255,0.7);">Press <kbd style="background:#111; color:#0ff; padding:1px 5px;">Esc</kbd> to close. New entries are marked read when this panel opens.</div>
            </div>
        `;
        const handle = window.mountOverlay({
            id: 'fcc-log-pill-overlay',
            content: html,
            tier: 'standard',
            backdrop: true,
            backdropDismiss: true,
        });
        const closeBtn = handle.element.querySelector('#fcc-log-pill-close');
        if (closeBtn) closeBtn.onclick = () => handle.cleanup();
        // Hide the pill now that the user has acknowledged.
        const pill = document.getElementById('fcc-log-pill');
        if (pill) pill.style.display = 'none';
    });
};

// L28 root cause: this poll fired on a 5s heartbeat without an in-flight
// guard and without a .catch(), so a slow backend (e.g. mid-PATCH) would
// pile fetches up until Chrome hit net::ERR_NO_BUFFER_SPACE — at which
// point every poll started rejecting and the unhandled rejections cascaded
// into a "frozen" frontend. Guard + catch keep the poll well-behaved under
// load: ticks back off automatically while a request is still pending.
//
// L206: render path extracted to _renderLogsPayload so the bulk-pulse
// dispatcher can hand pre-fetched data directly into the renderer without
// triggering another /api/logs round-trip.
const _renderLogsPayload = (d, force = false) => {
    if (!d) return;
    // --- NO WIGGLE CHECK ---
    const contentHash = JSON.stringify(d);
    if (!force && state.lastLogHash === contentHash) return;
    state.lastLogHash = contentHash;
    // -----------------------

    // THE PAUSE. Everything below this — the pill, the Spoolman dot, the audit
    // and bulk-move syncs — must keep running while paused; only the visible
    // list is frozen, so text stays selectable mid-copy. (On resume, pauseLogs
    // clears lastLogHash and forces a refresh, otherwise the hash check above
    // would skip the catch-up render and leave the panel stale.)
    const logsEl = state.logsPaused ? null : document.getElementById('live-logs');
    if (logsEl && d.logs) {
        logsEl.innerHTML = d.logs.map(l => {
            let extraHtml = '';
            let extraClass = '';
            if (l.meta && l.meta.type === 'cancel_deduct_pending') {
                // Cancelled-print partial deduct awaiting preview/confirm (§9.7).
                // openCancelReview() takes no args (it lists ALL pending), so no
                // meta is interpolated — nothing to inject.
                extraClass = ' cancel-review-log';
                extraHtml = `<button class="btn btn-sm btn-outline-warning ms-2 py-0 px-1" onclick="window.openCancelReview()">🛑 Review</button>`;
            }
            return `<div class="log-${l.type}${extraClass}">[${l.time}] ${l.msg}${extraHtml}</div>`;
        }).join('');
    }
    _updateLogPill(d.logs || []);

    const sSpool = document.getElementById('st-spoolman');
    if (d.status) {
        if (sSpool) sSpool.className = `status-dot ${d.status.spoolman ? 'status-on' : 'status-off'}`;
    }

    if (d.audit_active !== undefined && d.audit_active !== state.lastAuditState) {
        state.lastAuditState = d.audit_active;
        state.auditActive = d.audit_active;
        if (window.updateAuditVisuals) window.updateAuditVisuals();
    }

    _syncBulkMoveSignal(d);
};

// L298 Phase 2/3 — sync the bulk-move session so a session started/ended
// ANYWHERE (another tab, a page reload, the idle watchdog) repaints this tab's
// deck QR. Keyed on active+stage together, not just `active`: an active-only
// edge left a reloaded tab painting 'idle' over a live session, turning the deck
// button into a disguised Cancel.
//
// Phase 3 factored this out of _renderLogsPayload because BOTH heartbeat shapes
// must apply it. When the Activity Log is paused, _dashboardPulseTick drops the
// 'logs' section and asks for 'status' instead — so the logs-only sync left a
// paused tab with no bulk-move signal at all while the server-side idle watchdog
// (which rides /api/logs) could still cancel the session underneath it.
const _syncBulkMoveSignal = (src) => {
    if (!src || src.bulk_move_active === undefined) return;
    const stage = src.bulk_move_active ? (src.bulk_move_stage || 'awaiting_source') : 'idle';
    const sig = `${src.bulk_move_active}|${stage}`;
    if (sig === state.lastBulkMoveState) return;
    state.lastBulkMoveState = sig;
    state.bulkMoveActive = src.bulk_move_active;
    state.bulkMoveStage = stage;
    if (window.updateBulkMoveVisuals) window.updateBulkMoveVisuals();
};
window._syncBulkMoveSignal = _syncBulkMoveSignal;
window._renderLogsPayload = _renderLogsPayload;

let _updateLogStateInflight = false;
const updateLogState = (force = false) => {
    // PAUSE IS A RENDER-FREEZE, NOT A FETCH-FREEZE (2026-08-05).
    // Pause exists so the displayed list stops moving while you copy an error
    // out of it — not so the tab goes deaf. It used to early-return here, which
    // stopped polling entirely, so: the "N new" pill never appeared (its only
    // call site is inside the render path), and every flag riding this payload
    // (audit_active, bulk_move_active/stage, undo_available) stopped arriving,
    // leaving deck tiles stale against sessions the server had already ended.
    // Keep fetching; _renderLogsPayload skips only the list rewrite.
    // Load is unchanged — this is the rate an unpaused dashboard already polls.
    if (_updateLogStateInflight) return;
    _updateLogStateInflight = true;
    fetch('/api/logs').then(r => r.json()).then(d => _renderLogsPayload(d, force))
        .catch(e => console.warn("updateLogState failed:", e))
        .finally(() => { _updateLogStateInflight = false; });
};

// --- MODAL HELPERS ---
// Bumped every time a gating dialog ARMS. The hidden.bs.modal scan-gate
// release compares against it so a dialog re-shown from inside a previous
// dialog's callback can't be torn down by the previous one's `hidden` event.
let _confirmGeneration = 0;

// --- GATING-DIALOG LIFECYCLE (eject re-prompt drop, 2026-09-12) ---
// #confirmModal / #safetyModal / #actionModal are single Bootstrap instances
// that FCC re-shows from inside their OWN callbacks (eject -> active-print
// re-prompt -> "true unassign"). Bootstrap 5.3 silently IGNORES show() while a
// modal is still fading out, and hide() while it is still fading in — by
// design, no event, no error. confirmAction runs its callback in the same tick
// as hide(), so a backend that answered require_confirm inside the fade had its
// re-prompt DROPPED: no dialog, no toast, no request, and a still-armed
// pendingConfirm that a later CMD:CONFIRM scan fired with nothing on screen.
// The defect is FCC's call order, so respect the lifecycle: track each gating
// modal's phase from Bootstrap's PUBLIC events (never the private
// _isTransitioning) and queue the one call Bootstrap would have dropped.
const SCAN_GATING_MODALS = ['confirmModal', 'safetyModal', 'actionModal'];
const _gatingPhase = {};    // id -> 'showing' | 'shown' | 'hiding' | 'hidden'
const _deferredShow = {};   // id -> token of the ONE show queued for hidden.bs.modal
const _deferredHide = {};   // id -> token of the ONE hide queued for shown.bs.modal
// The phase is mirrored onto the dialog as data-fcc-phase so global.css can keep
// a dialog that is still fading in from taking clicks (Group 41.2).
const _setGatingPhase = (el, id, phase) => {
    _gatingPhase[id] = phase;
    if (phase) el.dataset.fccPhase = phase;
    else delete el.dataset.fccPhase;
};
[['show.bs.modal', 'showing'], ['shown.bs.modal', 'shown'],
 ['hide.bs.modal', 'hiding'], ['hidden.bs.modal', 'hidden']].forEach(([evt, phase]) => {
    // Capture phase: the phase is current before ANY element- or document-level
    // listener (including the queued show/hide below) runs for this event.
    document.addEventListener(evt, (ev) => {
        const id = ev.target && ev.target.id;
        if (!SCAN_GATING_MODALS.includes(id)) return;
        // A `hidden` from an OLD hide can land after a newer show() already
        // started (Bootstrap accepts show() during the backdrop-fade tail).
        if (phase === 'hidden' && _gatingPhase[id] !== 'hiding') return;
        const prev = _gatingPhase[id];
        _setGatingPhase(ev.target, id, phase);
        // show/hide are cancelable and capture runs first, so re-check after the
        // dispatch: a later preventDefault() means the transition never started.
        if (phase === 'showing' || phase === 'hiding') {
            queueMicrotask(() => { if (ev.defaultPrevented && _gatingPhase[id] === phase) _setGatingPhase(ev.target, id, prev); });
        }
    }, true);
});
// Genuinely ON SCREEN: fully faded in and not yet dismissed. The scan router
// (inv_cmd.js) requires this before a CONFIRM scan may fire a callback.
const isGatingModalOnScreen = (id) => {
    const el = document.getElementById(id);
    if (_gatingPhase[id] !== 'shown' || !el || !el.classList.contains('show')) return false;
    // Shown is not visible: a mountOverlay panel (z 20000) can sit on top of a
    // Bootstrap modal (z 1100), e.g. "Clear entire Buffer?" behind the bulk-move
    // panel. Hit-test the dialog's centre so a CONFIRM scan never fires a dialog
    // nobody can see (2026-09-12 review).
    const content = el.querySelector('.modal-content');
    if (!content) return true;
    const r = content.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && el.contains(hit);
};
window.isGatingModalOnScreen = isGatingModalOnScreen;
// Showing, shown, or queued to show — lets the scan router tell "not on screen
// YET" apart from "dismissed".
window.isGatingModalPending = (id) => _gatingModalPending(id);
// Still owns the scan gate: showing, shown, or queued to show.
const _gatingModalPending = (id) => {
    const el = document.getElementById(id);
    return !!_deferredShow[id] || _gatingPhase[id] === 'showing' || _gatingPhase[id] === 'shown'
        || (!!el && el.classList.contains('show'));
};
const _showGatingModal = (id) => {
    const inst = modals[id];
    const el = document.getElementById(id);
    if (!inst || !el) return;
    // A fresh prompt supersedes a hide closeModal queued during the fade-in: the
    // dialog is already on its way up, so it stays up showing the new text.
    _deferredHide[id] = null;
    // `.show` is removed synchronously once a hide really starts, so a stale
    // 'hiding' (hide prevented) never parks a prompt forever.
    if (_gatingPhase[id] !== 'hiding' || el.classList.contains('show')) { inst.show(); return; }
    // Mid-hide: show() would be dropped. Queue exactly ONE show for hidden.bs.modal.
    // The caller has already re-armed msg + callback synchronously, so if another
    // prompt arrives before then, the newest text and callback win.
    if (_deferredShow[id]) return;
    const token = {};
    _deferredShow[id] = token;
    // Element-level, so it runs BEFORE the document-level scan-gate release below
    // (pinned by tests/test_confirm_chain_reshow_e2e.py).
    el.addEventListener('hidden.bs.modal', () => {
        if (_deferredShow[id] !== token) return;   // cancelled by closeModal / superseded
        _deferredShow[id] = null;
        inst.show();
    }, { once: true });
};
const closeModal = (id) => {
    const inst = modals[id];
    if (inst) {
        // A queued re-show must not resurrect a prompt that was just closed.
        _deferredShow[id] = null;
        const el = document.getElementById(id);
        if (_gatingPhase[id] === 'showing' && el) {
            // Mid-fade-in: hide() would be dropped, leaving a dialog on screen
            // whose callback already ran. Queue ONE hide for shown.bs.modal.
            if (!_deferredHide[id]) {
                const token = {};
                _deferredHide[id] = token;
                el.addEventListener('shown.bs.modal', () => {
                    if (_deferredHide[id] !== token) return;   // a new prompt re-armed it
                    _deferredHide[id] = null;
                    inst.hide();
                }, { once: true });
            }
        } else {
            inst.hide();
        }
    }
    state.activeModal = null;
};
const requestConfirmation = (msg, cb) => { document.getElementById('confirm-msg').innerText = msg; state.pendingConfirm = cb; _confirmGeneration++; _showGatingModal('confirmModal'); state.activeModal = 'confirm'; };
// Take the callback and null it BEFORE running it: a callback that re-prompts
// synchronously arms a NEW pendingConfirm, which a trailing null would wipe.
const confirmAction = (y) => { const cb = state.pendingConfirm; state.pendingConfirm = null; closeModal('confirmModal'); if (y && cb) cb(); };
const promptSafety = (msg, cb) => { document.getElementById('safety-msg').innerText = msg; state.pendingSafety = cb; _confirmGeneration++; _showGatingModal('safetyModal'); state.activeModal = 'safety'; };
const confirmSafety = (y) => { const cb = state.pendingSafety; state.pendingSafety = null; closeModal('safetyModal'); if (y && cb) cb(); };
const promptAction = (t, m, btns) => {
    document.getElementById('action-title').innerText = t;
    document.getElementById('action-msg').innerHTML = m;
    state.modalCallbacks = [];
    document.getElementById('action-buttons').innerHTML = btns.map((b, i) => {
        state.modalCallbacks.push(b.action);
        return `<div class="modal-action-card" onclick="closeModal('actionModal');state.modalCallbacks[${i}]()"><div id="qr-act-${i}" class="bg-white p-1 rounded mb-2"></div><button class="btn btn-primary modal-action-btn">${b.label}</button></div>`;
    }).join('');
    btns.forEach((_, i) => generateSafeQR(`qr-act-${i}`, `CMD:MODAL:${i}`, 100));
    _confirmGeneration++; _showGatingModal('actionModal'); state.activeModal = 'action';
};

// --- SMART SYNC PROTOCOL (Heartbeat) ---
//
// L206: replaced fan-out (~12 reqs/5s) with a single `/api/dashboard_pulse`
// call per tick. Each section's renderer was extracted upstream so the
// dispatcher can hand pre-fetched data in without an extra round-trip.
// Adaptive cadence: 5s when active, 15s after 60s idle, 30s when the tab
// is hidden. Visibility/idle changes don't force a re-poll — the next
// scheduled tick just lands sooner or later than it otherwise would.

// Cadence buckets (ms). Tunable in one place if needed.
const PULSE_INTERVAL_ACTIVE = 5000;
const PULSE_INTERVAL_IDLE = 15000;
const PULSE_INTERVAL_HIDDEN = 30000;
const PULSE_IDLE_THRESHOLD_MS = 60000;

// L25 / FilaBridge Phase 0 — fast-poll on a print-finish/cancel edge.
//
// The filament deduct (FilaBridge today; FCC's own cancel detector soon)
// fires on a clock independent of the dashboard pulse. During an UNATTENDED
// print the user is idle and the tab may be hidden, so the pulse sits in the
// 15s/30s bucket and the post-finish weight can lag a full bucket behind the
// deduct. (NOTE: this is NOT the old "cadence drops when the printer goes
// idle" theory — that was wrong; cadence keys on USER inactivity + tab
// visibility, never printer state.) Fix: watch the printer_status section of
// each pulse for a "print just ended" transition (in-progress -> ended) and
// force a short ACTIVE-cadence burst so the fresh weight shows up within ~5s.
// This burst is also the event hook the cancelled-print detector rides.
const PULSE_FAST_POLL_WINDOW_MS = 30000;
const _PRINT_INPROGRESS_STATES = new Set(['PRINTING', 'PAUSED', 'PAUSING', 'RESUMING']);
const _PRINT_ENDED_STATES = new Set(['FINISHED', 'STOPPED', 'IDLE', 'ERROR', 'READY', 'OPERATIONAL']);
let _fastPollUntil = 0;
let _lastPrinterState = {};   // {printerName: 'PRINTING'|... |null} last-seen raw state

let _lastUserActivity = Date.now();
const _bumpUserActivity = () => { _lastUserActivity = Date.now(); };
// Activity bumpers. Notes on coverage:
// - `keydown` covers USB / Bluetooth barcode scanners — they emit
//   synthetic keystrokes to the focused window, so a scan bumps activity
//   the same way a keyboard press does. Only caveat: if the tab is
//   hidden, the scanner's keystrokes go to whatever IS focused (OS
//   shell, another app), not the browser. That's not a cadence problem
//   — there's no way to handle a scan on a hidden tab regardless.
// - `pointerdown` covers both mouse + touch via the unified Pointer
//   Events API; `touchstart` is kept as a belt-and-suspenders for older
//   mobile browsers that fire touch* but not pointer*.
// - When the mobile mode lands (Feature-Buglist L315 — large mobile
//   architectural effort), the cadence buckets themselves may want
//   revisiting (mobile backgrounding fires visibilitychange far more
//   often than desktop tab-switching does, so the 30s "hidden" bucket
//   could be either too aggressive or too conservative depending on
//   battery/cellular use). The activity list itself should already
//   carry over — touchstart + pointerdown is already mobile-correct.
['keydown', 'mousedown', 'pointerdown', 'wheel', 'touchstart'].forEach(ev =>
    document.addEventListener(ev, _bumpUserActivity, { passive: true, capture: true })
);

const _pulseInterval = () => {
    // A recent print-finish/cancel edge forces a short-cadence burst that
    // overrides the idle + hidden buckets, so the deduct's weight update
    // isn't stuck behind the 15s/30s gap (L25).
    if (Date.now() < _fastPollUntil) return PULSE_INTERVAL_ACTIVE;
    if (document.hidden) return PULSE_INTERVAL_HIDDEN;
    if (Date.now() - _lastUserActivity > PULSE_IDLE_THRESHOLD_MS) return PULSE_INTERVAL_IDLE;
    return PULSE_INTERVAL_ACTIVE;
};

// Inspect a dashboard_pulse `printer_status` payload and arm the fast-poll
// burst when any printer transitions from an in-progress state (PRINTING /
// PAUSED / PAUSING / RESUMING) to an ended state (FINISHED / STOPPED / IDLE /
// ERROR / READY / OPERATIONAL) — i.e. a print just completed or was
// cancelled. `state === null` means the printer is offline/unreachable; we
// skip it so an offline blip isn't mistaken for a finish edge.
const _notePrinterStatesForFastPoll = (printerStatus) => {
    if (!printerStatus || typeof printerStatus !== 'object') return;
    for (const name of Object.keys(printerStatus)) {
        const info = printerStatus[name];
        const st = info && info.state;
        if (!st) { _lastPrinterState[name] = null; continue; }
        const now = String(st.state || '').toUpperCase();
        const prev = _lastPrinterState[name];
        if (prev && _PRINT_INPROGRESS_STATES.has(prev) && _PRINT_ENDED_STATES.has(now)) {
            _fastPollUntil = Date.now() + PULSE_FAST_POLL_WINDOW_MS;
        }
        _lastPrinterState[name] = now;
    }
};

// Build the include= list based on what the user can actually see this
// tick. There's no point asking for `locations` if the table isn't on
// screen — saves the backend a Spoolman+locations.json round-trip.
const _computePulseInclude = () => {
    const sections = ['logs'];  // always — needed for status dots + audit watchdog
    const locTable = document.getElementById('location-table');
    if (locTable && locTable.offsetParent !== null) sections.push('locations');
    const manageModal = document.getElementById('manageModal');
    let manageId = null;
    if (manageModal && manageModal.classList.contains('show')) {
        const manageLocId = document.getElementById('manage-loc-id');
        if (manageLocId && manageLocId.value) {
            sections.push('manage');
            manageId = manageLocId.value;
        }
    }
    // Always include printer_status — the widget is on the dashboard and
    // is one of the most useful at-a-glance surfaces. Aggregation cost
    // lives server-side (parallelized) so the network cost is one section
    // in the bulk payload, not N separate fetches.
    sections.push('printer_status');
    return { sections, manageId };
};

let _pulseInflight = false;
let _pulseNextTimer = null;
// _scheduleNextPulse owns every setTimeout we use to drive ticks so the
// visibilitychange handler can cancel-and-reschedule when the tab comes
// back to focus (otherwise the user would wait up to 30s — the hidden-
// bucket scheduled gap — for fresh data after switching back).
const _scheduleNextPulse = (delayMs) => {
    if (_pulseNextTimer !== null) {
        clearTimeout(_pulseNextTimer);
        _pulseNextTimer = null;
    }
    _pulseNextTimer = setTimeout(() => {
        _pulseNextTimer = null;
        _dashboardPulseTick();
    }, delayMs);
};

const _dashboardPulseTick = () => {
    if (_pulseInflight) {
        // Guard: don't stack pulses if the backend is slow. Schedule the
        // next attempt at the current cadence — we'll re-evaluate when
        // the in-flight one returns.
        _scheduleNextPulse(_pulseInterval());
        return;
    }
    _pulseInflight = true;

    const { sections, manageId } = _computePulseInclude();
    // Logs stay in the heartbeat even while paused (2026-08-05). Dropping the
    // section used to starve the "N new" pill and every flag riding that
    // payload; the freeze now happens at the render, not the fetch.
    const include = sections;
    let url = `/api/dashboard_pulse?include=${encodeURIComponent(include.join(','))}`;
    if (manageId) url += `&manage_id=${encodeURIComponent(manageId)}`;

    // POST body carries refresh_spool_ids when the buffer has held spools,
    // replacing the old liveRefreshBuffer fetch.
    const heldIds = (state.heldSpools || []).map(s => s.id);
    const fetchOpts = heldIds.length > 0
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_spool_ids: heldIds }),
        }
        : { method: 'GET' };

    fetch(url, fetchOpts)
        .then(r => r.json())
        .then(payload => {
            if (!payload || typeof payload !== 'object') return;

            // logs / status renderer — handles status dots + audit visuals + log entries
            if (payload.logs) {
                _renderLogsPayload(payload.logs);
            } else if (payload.status) {
                // No log entries but still got status — repaint the dot only.
                const sSpool = document.getElementById('st-spoolman');
                if (sSpool) sSpool.className = `status-dot ${payload.status.spoolman ? 'status-on' : 'status-off'}`;
                if (payload.status.audit_active !== undefined && payload.status.audit_active !== state.lastAuditState) {
                    state.lastAuditState = payload.status.audit_active;
                    state.auditActive = payload.status.audit_active;
                    if (window.updateAuditVisuals) window.updateAuditVisuals();
                }
                // Same bulk-move sync the logs branch runs — this is the branch a
                // PAUSED Activity Log takes, and it's the only bulk-move signal
                // such a tab receives (updateLogState early-returns while paused).
                _syncBulkMoveSignal(payload.status);
            }
            if (payload.locations) _renderLocationsPayload(payload.locations);
            if (payload.manage && payload.manage.contents && window._renderManagePayload) {
                window._renderManagePayload(payload.manage.id, payload.manage.contents);
            }
            if (payload.printer_status) {
                // L25 — note finish/cancel edges to arm the fast-poll burst
                // (runs even if the widget renderer isn't mounted this tick).
                _notePrinterStatesForFastPoll(payload.printer_status);
                if (window.refreshPrinterStatusWidgetFromAggregate) {
                    window.refreshPrinterStatusWidgetFromAggregate(payload.printer_status);
                }
            }
            if (payload.spools_refresh && window._renderSpoolsRefreshPayload) {
                window._renderSpoolsRefreshPayload(payload.spools_refresh);
            }

            // Broadcast for listeners that still poll independently
            // (inv_backlog, inv_details modal sync, inv_search results).
            // These do NOT include liveRefreshBuffer — that's now driven
            // directly by the spools_refresh payload above.
            document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'dashboard_pulse' } }));
        })
        .catch(e => console.warn("dashboard_pulse failed:", e))
        .finally(() => {
            _pulseInflight = false;
            _scheduleNextPulse(_pulseInterval());
        });
};

window.startSmartSync = () => {
    if (window._smartSyncRunning) return;
    window._smartSyncRunning = true;
    console.log("🔄 Smart Sync Protocol Initiated (adaptive: 5s active / 15s idle / 30s hidden)");
    // Kick the first tick off immediately so the dashboard populates
    // without waiting 5s on cold load.
    _scheduleNextPulse(100);
    // When the user comes back to a tab that was in the 30s hidden
    // bucket, cancel the far-future tick and fire one immediately so
    // they don't see stale data on switch-back. The bump_activity
    // listener fires on the same event but only updates the timestamp;
    // without this re-schedule, the staleness gap could be up to 30s.
    document.addEventListener('visibilitychange', () => {
        _bumpUserActivity();
        if (!document.hidden && !_pulseInflight) {
            _scheduleNextPulse(50);
        }
    });
};

// Test/debug hook: expose the tick directly so a test can fire it
// without waiting on setTimeout.
window._dashboardPulseTickOnce = () => {
    _pulseInflight = false;  // reset in case a prior tick is stuck
    _dashboardPulseTick();
};
// Expose the current-cadence reader for the cadence test.
window._pulseInterval = _pulseInterval;
// L25 fast-poll test hooks — feed synthetic printer_status transitions,
// read whether the burst is armed, and reset state between tests.
window._notePrinterStatesForFastPoll = _notePrinterStatesForFastPoll;
window._fastPollActive = () => Date.now() < _fastPollUntil;
window._resetFastPollForTest = () => { _fastPollUntil = 0; _lastPrinterState = {}; };

// --- GLOBAL MODAL / WINDOW MANAGER ---
document.addEventListener('DOMContentLoaded', () => {
    // Start Heartbeat
    window.startSmartSync();
    // L184 — fire the log poll once immediately so the corner pill can
    // populate without waiting ~5s for the first heartbeat tick.
    updateLogState(true);

    // Prime state.allLocations on cold load. The L206 adaptive pulse only
    // fetches /api/locations when the Location Manager TABLE is visible
    // (see _buildPulseInclude), so on the bare dashboard allLocations would
    // stay []. That silently broke openManage() from every dashboard surface
    // (Printer Status widget tiles, spool-card location badges): openManage
    // looks the id up in state.allLocations and returns early if it's missing,
    // so clicks did nothing with no error. Pre-L206 the unconditional
    // fetchLocations poll kept it populated — restore that guarantee here,
    // and refresh whenever locations change so the cache can't go stale.
    fetchLocations();
    document.addEventListener('inventory:locations-changed', () => fetchLocations());

    // Initialize Wake Lock Handlers
    requestWakeLock();

    // 1. When a modal starts showing
    document.addEventListener('show.bs.modal', function (event) {
        // Auto-collapse Search Offcanvas if open to reduce clicks
        const offcanvasEl = document.getElementById('offcanvasSearch');
        if (offcanvasEl && offcanvasEl.classList.contains('show')) {
            const os = bootstrap.Offcanvas.getInstance(offcanvasEl);
            if (os) os.hide();
        }

        // Calculate and apply stacking z-index for the modal wrapper
        const openModals = document.querySelectorAll('.modal.show').length;
        // BS5 default modal z-index is 1055. Add 10 per subsequent tier.
        const newModalZ = 1055 + (openModals * 10);
        event.target.style.setProperty('z-index', newModalZ, 'important');
    });

    // 2. When modal finishes animating (backdrop is strictly in the DOM)
    document.addEventListener('shown.bs.modal', function () {
        // Find the last added backdrop and stack it purely behind our new modal
        const backdrops = document.querySelectorAll('.modal-backdrop');
        if (backdrops.length > 0) {
            const baseBackdropZIndex = 1050; // BS5 default backdrop z-index
            const newBackdropZ = baseBackdropZIndex + ((backdrops.length - 1) * 10);
            backdrops[backdrops.length - 1].style.setProperty('z-index', newBackdropZ, 'important');
        }
    });

    // 3. When a modal finishes hiding
    document.addEventListener('hidden.bs.modal', function (ev) {
        // Bootstrap aggressively strips '.modal-open' from body when *any* modal hides.
        // We must forcefully restore it if there are other modals still 'underneath' it.
        if (document.querySelectorAll('.modal.show').length > 0) {
            document.body.classList.add('modal-open');
        }

        // --- Scan-gate release (axis-(a) audit, 2026-08-03) ---
        // `state.activeModal` gates processScan: while it is set, inv_cmd's
        // router answers only CONFIRM/CANCEL and silently DROPS every spool and
        // location scan — no toast, no Activity Log line, no request.
        // It used to be cleared ONLY by closeModal(), i.e. only by the dialogs'
        // own buttons. Escape and backdrop clicks bypass that (#confirmModal
        // sets neither data-bs-keyboard="false" nor data-bs-backdrop="static",
        // and the inv_loc_mgr Escape ladder calls inst.hide() directly), so
        // cancelling any confirm that way left the flag latched and the scanner
        // looked DEAD until a page reload.
        // Releasing here covers every dismissal path at once.
        // (SCAN_GATING_MODALS + the phase tracker live with the modal helpers.)
        const hiddenId = ev && ev.target && ev.target.id;
        if (SCAN_GATING_MODALS.includes(hiddenId)) {
            // ⚠️ Generation counter, NOT just a `.show` check. A confirm whose
            // callback raises a SECOND confirm (eject -> "true unassign", or the
            // active-print re-prompt) re-shows the same element, and Bootstrap
            // re-adds `.show` ~155ms after show() while this `hidden` event
            // fires ~310ms after hide(). A plain `.show` test therefore sees
            // "nothing open" and tore down the dialog that had just re-armed —
            // its YES button became silently dead. Compare the generation we
            // captured when this modal was shown against the current one:
            // if something re-armed since, that newer dialog owns the state.
            const gen = _confirmGeneration;
            setTimeout(() => {
                if (_confirmGeneration !== gen) return;   // re-armed — leave it alone
                // "Still open" also covers a prompt that is fading in or queued
                // behind this very hide (_showGatingModal re-arms BEFORE hidden,
                // so the generation above can't see it). `.show` alone lags:
                // Bootstrap adds it only after the backdrop fade.
                if (SCAN_GATING_MODALS.some(_gatingModalPending)) return;
                // Release the scan gate. Only activeModal — deliberately NOT
                // pendingConfirm/pendingSafety: clearing those is what killed
                // the chained re-prompt, and confirmAction/confirmSafety
                // already null them on the button path. The stale-callback
                // hazard is handled by the generation bump in
                // requestConfirmation/promptSafety instead.
                state.activeModal = null;
            }, 400);
        }
    });
});

// [Code Guardian] Wake Lock Persistence
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
        await acquireLock();
    }
});