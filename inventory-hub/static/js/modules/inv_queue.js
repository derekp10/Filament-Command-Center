/* MODULE: PRINT QUEUE */
console.log("🚀 Loaded Module: QUEUE");

// Expose globally
try {
    window.labelQueue = JSON.parse(localStorage.getItem('fcc_label_queue')) || [];
} catch (e) {
    window.labelQueue = [];
}
let labelQueue = window.labelQueue;

// Modal Instances & Data
let clearConfirmModal = null;
let multiSpoolModal = null;
let multiSpoolData = []; // Store search results here

// The title bar's 🛒 Queue count, written only when it changes: the bar fits
// itself again whenever a button's text changes (titlebar_fit.js). Its word
// and brackets are spans of their own, which the bar drops to show "🛒 0"
// (Group 57.3; Settings -> Title bar buttons); its tooltip and accessible
// name always say the words. From the
// page's load it shows this browser's queue (Group 57 review, round 3): the
// button kept the page's "(0)" until the server's queue differed from this
// browser's, so a browser whose queue matched the server's read "(0)" with
// labels queued.
const _paintQueueCount = () => {
    const btn = document.getElementById('btn-queue-count');
    if (!btn) return;
    const n = String(labelQueue.length);
    if (btn.dataset.countShown === n) return;
    btn.dataset.countShown = n;
    btn.innerHTML = '🛒<span class="fcc-tb-word"> Queue</span> <span class="fcc-count-num"><span class="fcc-tb-paren">('
        + `</span>${n}<span class="fcc-tb-paren">)</span></span>`;
    btn.title = `Queue (${n}). Opens the label print queue.`;
    btn.setAttribute('aria-label', btn.title);
};
_paintQueueCount();
document.addEventListener('DOMContentLoaded', _paintQueueCount);

window.updateQueueUI = () => {
    localStorage.setItem('fcc_label_queue', JSON.stringify(labelQueue));
    _paintQueueCount();
    document.dispatchEvent(new CustomEvent('inventory:queue-updated', { detail: { queue: labelQueue } }));
};

window.addToQueue = (item) => {
    if (labelQueue.find(s => s.id === item.id && s.type === item.type)) {
        // Silent return for bulk adds, generic toast handled by caller
        return false;
    }
    if (!item.type) item.type = 'spool';

    // Auto-patch Spoolman flag for Backlog
    if (item.type === 'spool' || item.type === 'filament') {
        fetch('/api/print_queue/set_flag', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: item.id, type: item.type })
        })
        .then(r => r.json())
        .then(data => {
            // Surface Spoolman rejection so users aren't blind to silent
            // failures — backend now populates data.msg with the error body.
            if (!data.success) {
                showToast(data.msg || data.error || "Failed to flag for label print", "error", 7000);
            }
        })
        .catch(e => {
            console.error("Could not set print flag:", e);
            showToast("Could not set print flag (connection error)", "error", 7000);
        });
    }

    labelQueue.push(item);
    window.updateQueueUI();
    return true;
};

// Generic toast wrapper for single adds if needed
window.addToQueueWithToast = (item) => {
    if (addToQueue(item)) showToast(`Added ${item.type} to Print Queue`);
    else showToast("Label already in queue", "info", 4000);
}

/* --- ONE ROW RENDERER (Group 48.1) ---
 *
 * Derek, 2026-10-08: every queued label should read like the backlog's ("Just
 * listing a spool id doesn't tell me what color it is"). Each spool or filament
 * row is a colour swatch + "Brand - Material - Color" + its #id, from live data
 * read when the queue window opens: ONE /api/spools/refresh for the queued
 * spools and one /api/filament_details per queued filament, never on a
 * heartbeat. The stored `display` (whatever the adding button sent: "Spool
 * #57", "#57 Brand MAT (Color)", a filament name…) is drawn first and stays
 * the fallback when a read fails, with a leading "#id" stripped (the row shows
 * the id itself). A location row is "📍 LOC-ID — Name". Printed labels are
 * unaffected: they print by id. Every piece of text is escaped (colour names
 * are free text).
 */
const _queueLive = new Map();   // 'spool:57' / 'filament:12' -> {brand, material, color, hex, direction} | {failed}
const _queueKey = (item) => `${item.type || 'spool'}:${item.id}`;
const _queueEsc = (s) => (window.escHtml ? window.escHtml(s) : String(s == null ? '' : s)
    .replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
const _unquote = (v) => String(v == null ? '' : v).trim().replace(/^"(.*)"$/, '$1');
const _storedQueueText = (item) => String(item.display || '').replace(/^\s*#\d+\s*(?:[-–:]\s*)?/, '').trim();

const _queueRowHtml = (item, index) => {
    const type = item.type || 'spool';
    let swatch = '';
    let text;
    if (type === 'location') {
        const row = (typeof state !== 'undefined' && Array.isArray(state.allLocations) ? state.allLocations : [])
            .find(l => String(l.LocationID || '').toUpperCase() === String(item.id).toUpperCase());
        const name = row && row.Name && String(row.Name).toUpperCase() !== String(item.id).toUpperCase() ? row.Name : '';
        text = `${item.id}${name ? ` — ${name}` : ''}`;
    } else {
        const live = _queueLive.get(_queueKey(item));
        if (live && !live.failed) {
            text = [live.brand, live.material, live.color].filter(Boolean).join(' - ') || _storedQueueText(item);
            // The shared swatch helper (multi-colour filaments drawn as on the cards).
            if (window.makeSwatchHtml) {
                swatch = `<span class="fcc-queue-swatch d-inline-flex flex-shrink-0 me-2" aria-hidden="true">${window.makeSwatchHtml(
                    live.hex || '333', live.direction || 'longitudinal',
                    { size: 22, borderColor: 'rgba(255,255,255,0.35)', borderWidth: 2, marginRight: 0 })}</span>`;
            }
        } else {
            text = _storedQueueText(item);
        }
    }
    const icon = type === 'filament' ? '🧬' : (type === 'location' ? '📍' : '🧵');
    const idTag = type === 'location' ? '' : `<span class="text-info fw-bold me-2">#${_queueEsc(item.id)}</span>`;
    return `
        <li class="list-group-item bg-dark text-white border-secondary d-flex justify-content-between align-items-center fcc-queue-row"
            data-queue-key="${_queueEsc(_queueKey(item))}">
            <span class="d-flex align-items-center text-truncate">${swatch}<span class="me-2">${icon}</span>${idTag}<span class="fcc-queue-text text-truncate">${_queueEsc(text)}</span></span>
            <button class="btn btn-sm btn-outline-danger flex-shrink-0 ms-2" onclick="removeFromQueue(${index})" title="Remove from the queue">❌</button>
        </li>`;
};

// Draws the list from what is known now (no reads).
const _renderQueueList = () => {
    const list = document.getElementById('queue-list-items');
    const emptyMsg = document.getElementById('queue-empty-msg');
    if (!list) return;
    if (labelQueue.length === 0) {
        list.innerHTML = "";
        if (emptyMsg) emptyMsg.style.display = 'block';
        return;
    }
    if (emptyMsg) emptyMsg.style.display = 'none';
    list.innerHTML = labelQueue.map((item, index) => _queueRowHtml(item, index)).join('');
};

// Reads what the open queue doesn't know yet, then redraws once.
const _fetchQueueLive = () => {
    const missing = (type) => labelQueue.filter(i => (i.type || 'spool') === type && !_queueLive.has(_queueKey(i))).map(i => i.id);
    const spoolIds = missing('spool');
    const filamentIds = missing('filament');
    const jobs = [];
    if (spoolIds.length) {
        jobs.push(fetch('/api/spools/refresh', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spools: spoolIds }),
        })
            .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
            .then(data => spoolIds.forEach(id => {
                const d = data && data[String(id)];
                const det = (d && d.details) || null;
                _queueLive.set(`spool:${id}`, det
                    ? { brand: det.brand, material: det.material, color: det.color_name, hex: d.color, direction: d.color_direction }
                    : { failed: true });
            }))
            .catch(() => spoolIds.forEach(id => _queueLive.set(`spool:${id}`, { failed: true }))));
    }
    filamentIds.forEach(id => jobs.push(fetch(`/api/filament_details?id=${encodeURIComponent(id)}`)
        .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(f => {
            const ex = (f && f.extra) || {};
            _queueLive.set(`filament:${id}`, (f && f.id != null) ? {
                brand: (f.vendor && f.vendor.name) || 'Unknown',
                material: f.material || '',
                color: f.name || _unquote(ex.original_color) || '',
                hex: f.multi_color_hexes || f.color_hex || _unquote(ex.multi_color_hexes) || '333',
                direction: f.multi_color_direction || _unquote(ex.multi_color_direction) || 'longitudinal',
            } : { failed: true });
        })
        .catch(() => _queueLive.set(`filament:${id}`, { failed: true }))));
    if (jobs.length) Promise.all(jobs).then(_renderQueueList);
};

window.openQueueModal = () => {
    // Opening the window reads every queued label afresh (a colour edited since
    // the last open shows); redraws while it is open read only what is new.
    _queueLive.clear();
    _renderQueueList();
    _fetchQueueLive();
    if (modals.queueModal) modals.queueModal.show();
};

window.removeFromQueue = (index) => {
    labelQueue.splice(index, 1);
    _renderQueueList();
    window.updateQueueUI();
};

/* --- CLEAR CONFIRMATION --- */
window.confirmClearQueueReq = () => {
    const el = document.getElementById('clearQueueConfirmModal');
    if (el) {
        clearConfirmModal = new bootstrap.Modal(el);
        clearConfirmModal.show();
    }
};

window.closeClearConfirm = () => {
    if (clearConfirmModal) clearConfirmModal.hide();
};

window.executeClearQueue = () => {
    labelQueue.length = 0;
    _renderQueueList();
    window.updateQueueUI();
    showToast("Queue Cleared");
    if (clearConfirmModal) clearConfirmModal.hide();
};

window.printQueueCSV = () => {
    if (labelQueue.length === 0) return;
    const overwrite = document.getElementById('chk-overwrite-csv').checked;

    const spools = labelQueue.filter(i => i.type === 'spool').map(i => i.id);
    const filaments = labelQueue.filter(i => i.type === 'filament').map(i => i.id);
    const locations = labelQueue.filter(i => i.type === 'location').map(i => i.id);

    const sendBatch = (ids, mode) => {
        return fetch('/api/print_batch_csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids, mode: mode, clear_old: overwrite })
        })
            .then(r => r.json())
            .then(res => {
                if (res.success) { showToast(`✅ ${mode} Batch Saved!`); return true; }
                // Error toasts ride ≥7s so a failed export — most often the CSV
                // locked by P-touch (or another program) — doesn't slip past
                // while the user is blind-scanning. res.msg already names the
                // file, so no mode prefix. The backend also logs it.
                else { showToast(`❌ ${res.msg}`, "error", 7000); return false; }
            })
            .catch(e => { showToast(`❌ Label export failed — connection error`, "error", 7000); return false; });
    };

    const promises = [];
    if (spools.length > 0) promises.push(sendBatch(spools, 'spool'));
    if (filaments.length > 0) promises.push(sendBatch(filaments, 'filament'));
    if (locations.length > 0) promises.push(sendBatch(locations, 'location'));

    Promise.all(promises).then(results => {
        if (results.every(r => r === true)) {
            labelQueue.length = 0;
            _renderQueueList();
            window.updateQueueUI();
            modals.queueModal.hide();
        }
    });
};

/* --- MULTI-SPOOL FEATURE (Modal Version) --- */
window.findMultiSpoolFilaments = () => {
    setProcessing(true);
    fetch('/api/get_multi_spool_filaments')
        .then(r => r.json())
        .then(data => {
            setProcessing(false);
            if (data.length === 0) { showToast("No Multi-Spool Filaments Found", "info"); return; }

            // Store data for the modal action
            multiSpoolData = data;

            // Populate Modal
            const totalSpools = data.reduce((acc, item) => acc + item.count, 0);

            const titleEl = document.getElementById('multi-spool-count');
            const msgEl = document.getElementById('multi-spool-msg');

            if (titleEl) titleEl.innerText = `Found ${data.length} Filaments`;
            if (msgEl) msgEl.innerHTML = `These filaments have multiple active spools.<br><strong>Total Spools: ${totalSpools}</strong><br><br>Add them all to the Print Queue?`;

            // Show Modal
            const el = document.getElementById('multiSpoolModal');
            if (el) {
                multiSpoolModal = new bootstrap.Modal(el);
                multiSpoolModal.show();
            }
        })
        .catch(() => { setProcessing(false); showToast("Search Error", "error"); });
};

window.executeMultiSpoolAdd = () => {
    if (!multiSpoolData || multiSpoolData.length === 0) return;

    let added = 0;
    multiSpoolData.forEach(fil => {
        fil.spool_ids.forEach(sid => {
            // Re-using addToQueue logic
            if (window.addToQueue({
                id: sid,
                type: 'spool',
                display: `${fil.display} (ID:${sid})`
            })) {
                added++;
            }
        });
    });

    showToast(`Added ${added} spools!`);

    // Close Multi Modal
    if (multiSpoolModal) multiSpoolModal.hide();

    // Refresh Queue Modal to show new items
    window.openQueueModal();
};

window.closeMultiSpoolModal = () => {
    if (multiSpoolModal) multiSpoolModal.hide();
};

/* --- PERSISTENCE LAYER ---
 *
 * L23 — without a suppression window the user-clear path lost a race:
 *   T-1.95s  loadQueue GET issued (server still has CR-CART-2)
 *   T+0      user clicks Clear → labelQueue=[], persistQueue POSTs []
 *   T+0.05s  the stale GET response arrives → labelQueue replaced with
 *            server's pre-clear payload → CR-CART-2 reappears.
 * Tracking the last-write timestamp lets loadQueue ignore any response
 * whose request was issued before the most recent local mutation.
 */
let lastPersistAt = 0;
const persistQueue = () => {
    lastPersistAt = Date.now();
    fetch('/api/state/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queue: labelQueue })
    }).catch(e => console.warn("Queue Save Failed", e));
};

let queueInitialLoad = true;
let _loadQueueInflight = false;
const loadQueue = () => {
    // In-flight guard (L28): loadQueue polls /api/state/queue every 2s — the
    // same socket-exhaustion vector as loadBuffer. A momentarily slow backend
    // could otherwise stack ticks until Chrome hit ERR_NO_BUFFER_SPACE. Skip a
    // tick while one is already outstanding; reset in .finally().
    if (_loadQueueInflight) return;
    _loadQueueInflight = true;
    const issuedAt = Date.now();
    fetch('/api/state/queue')
        .then(r => r.json())
        .then(data => {
            // Drop responses to requests that pre-date the most recent
            // local mutation — they reflect the server's old state and
            // would clobber the user's just-applied change.
            if (issuedAt < lastPersistAt) return;
            if (Array.isArray(data)) {
                const currentStr = JSON.stringify(labelQueue);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    // [ALEX BUGFIX]: If the server restarted, it sets GLOBAL_QUEUE to `[]`.
                    // If this client holds a localStorage queue on initial load, re-seed the server!
                    if (queueInitialLoad && serverStr === '[]' && labelQueue.length > 0) {
                        persistQueue();
                    } else {
                        labelQueue.length = 0;
                        data.forEach(item => labelQueue.push(item));

                        _paintQueueCount();

                        if (modals.queueModal && document.getElementById('queueModal').classList.contains('show')) {
                            // Group 48.1: redraw, reading only labels new to the open window.
                            _renderQueueList();
                            _fetchQueueLive();
                        }
                    }
                }
                queueInitialLoad = false;
            }
        })
        .catch(e => console.warn("Queue Load Failed", e))
        .finally(() => { _loadQueueInflight = false; });
};

document.addEventListener('inventory:queue-updated', persistQueue);
setInterval(loadQueue, 2000);
document.addEventListener('DOMContentLoaded', loadQueue);