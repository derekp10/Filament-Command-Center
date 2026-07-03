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

const setProcessing = (s) => {
    let ov = document.getElementById('processing-overlay');
    if (!ov) { ov = document.createElement('div'); ov.id = 'processing-overlay'; ov.style.cssText = "display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:9999;"; document.body.appendChild(ov); }
    state.processing = s; ov.style.display = s ? 'block' : 'none';
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

    const row = document.createElement('div');
    row.id = `${sid}-row`;
    row.className = 'fcc-confirm-qr-row';
    row.style.cssText = 'display:flex; gap:14px; justify-content:center; margin-top:14px; padding-top:12px; border-top:1px dashed #444;';
    row.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
            <div style="background:${palette.confirmBg}; border:2px solid ${palette.border}; border-radius:6px; padding:6px;">
                <div id="${sid}-yes-qr" style="background:#fff; padding:4px; border-radius:3px; line-height:0;"></div>
            </div>
            <div style="font-size:0.72rem; color:${palette.border}; font-weight:700; letter-spacing:0.5px; text-transform:uppercase;">📷 ${opts.confirmLabel || 'Scan to Confirm'}</div>
        </div>
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
    generateSafeQR(`${sid}-no-qr`, `CMD:CANCEL:${sid}`, 70);

    // Register the callbacks. Both fire-then-clear so a duplicate scan can't
    // re-trigger after the dialog closed.
    window._fccActiveConfirms[sid] = {
        onConfirm: () => {
            const entry = window._fccActiveConfirms[sid];
            if (!entry) return;
            delete window._fccActiveConfirms[sid];
            try { opts.onConfirm && opts.onConfirm(); } catch (e) { console.error('[confirm-qr]', e); }
        },
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
    const m = String(text).match(/^[Cc][Mm][Dd]:(CONFIRM|CANCEL|confirm|cancel):(.+)$/);
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

const hexToRgb = (hex) => {
    if (!hex) return { r: '', g: '', b: '' };
    hex = hex.replace('#', '');
    const i = parseInt(hex, 16);
    return { r: (i >> 16) & 255, g: (i >> 8) & 255, b: i & 255 };
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
                    Occupancy: '--'
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
                const byId = new Map();
                bodyRows.forEach(r => byId.set(upper(r.LocationID), r));
                const childrenOf = new Map();
                const roots = [];
                bodyRows.forEach(r => {
                    const pid = r.parent_id != null ? upper(r.parent_id) : null;
                    // A row attaches to its parent UNLESS the parent isn't a real
                    // row (orphan → root) or pin-mode floats printers to the top.
                    const attach = pid && byId.has(pid) && !(pinPrinters && isPrinterRow(r));
                    if (attach) {
                        if (!childrenOf.has(pid)) childrenOf.set(pid, []);
                        childrenOf.get(pid).push(r);
                    } else {
                        roots.push(r);
                    }
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

                    return `
                <tr data-locid="${escAttr(lidUC)}" data-ancestors="${ancAttr}" id="loc-row-${lidEsc}">
                    <td class="col-id" style="font-weight:bold; color:#00d4ff; font-size:1.1rem; white-space: nowrap;">${indent}${escHtml(l.LocationID)}</td>
                    <td class="col-name text-pop-light" style="font-weight:800; font-size:1.1rem; color:#fff;">${escHtml(l.Name)}</td>
                    <td class="col-type">${typeBadge}</td>
                    <td class="col-status">${statusHtml}</td>
                    <td class="col-actions text-end" style="white-space: nowrap;">
                        <button class="btn btn-sm btn-outline-light me-1 btn-qr" data-id="${lidEsc}" title="Show QR">📱 QR</button>
                        ${l.Type !== 'Virtual' ? `
                        <button class="btn btn-sm btn-outline-warning me-1 btn-edit" data-id="${lidEsc}">✏️</button>
                        <button class="btn btn-sm btn-outline-danger me-1 btn-delete" data-id="${lidEsc}">🗑️</button>
                        ` : ''}
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

    const logsEl = document.getElementById('live-logs');
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
};
window._renderLogsPayload = _renderLogsPayload;

let _updateLogStateInflight = false;
const updateLogState = (force = false) => {
    if (state.logsPaused && !force) return;
    if (_updateLogStateInflight) return;
    _updateLogStateInflight = true;
    fetch('/api/logs').then(r => r.json()).then(d => _renderLogsPayload(d, force))
        .catch(e => console.warn("updateLogState failed:", e))
        .finally(() => { _updateLogStateInflight = false; });
};

// --- MODAL HELPERS ---
const closeModal = (id) => { if (modals[id]) modals[id].hide(); state.activeModal = null; };
const requestConfirmation = (msg, cb) => { document.getElementById('confirm-msg').innerText = msg; state.pendingConfirm = cb; modals.confirmModal.show(); state.activeModal = 'confirm'; };
const confirmAction = (y) => { closeModal('confirmModal'); if (y && state.pendingConfirm) state.pendingConfirm(); state.pendingConfirm = null; };
const promptSafety = (msg, cb) => { document.getElementById('safety-msg').innerText = msg; state.pendingSafety = cb; modals.safetyModal.show(); state.activeModal = 'safety'; };
const confirmSafety = (y) => { closeModal('safetyModal'); if (y && state.pendingSafety) state.pendingSafety(); state.pendingSafety = null; };
const promptAction = (t, m, btns) => {
    document.getElementById('action-title').innerText = t;
    document.getElementById('action-msg').innerHTML = m;
    state.modalCallbacks = [];
    document.getElementById('action-buttons').innerHTML = btns.map((b, i) => {
        state.modalCallbacks.push(b.action);
        return `<div class="modal-action-card" onclick="closeModal('actionModal');state.modalCallbacks[${i}]()"><div id="qr-act-${i}" class="bg-white p-1 rounded mb-2"></div><button class="btn btn-primary modal-action-btn">${b.label}</button></div>`;
    }).join('');
    btns.forEach((_, i) => generateSafeQR(`qr-act-${i}`, `CMD:MODAL:${i}`, 100));
    modals.actionModal.show(); state.activeModal = 'action';
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
    // If logs are paused (user explicitly paused the activity log), still
    // pull everything else but skip the logs section.
    const include = state.logsPaused
        ? sections.filter(s => s !== 'logs').concat('status')
        : sections;
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
    document.addEventListener('hidden.bs.modal', function () {
        // Bootstrap aggressively strips '.modal-open' from body when *any* modal hides.
        // We must forcefully restore it if there are other modals still 'underneath' it.
        if (document.querySelectorAll('.modal.show').length > 0) {
            document.body.classList.add('modal-open');
        }
    });
});

// [Code Guardian] Wake Lock Persistence
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
        await acquireLock();
    }
});