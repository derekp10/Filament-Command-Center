/* MODULE: MISSING LABELS BACKLOG */
console.log("🚀 Loaded Module: MISSING LABELS BACKLOG");

window.openBacklogModal = () => {
    modals.backlogModal.show();
    window.fetchBacklog();
};

let lastBacklogHash = "";
// Group 52.1a: set once a heartbeat has delivered the count (label_backlog).
let _backlogCountFed = false;
// The count the button shows, once one is known.
let _backlogCount = null;

// Why a count is stale, in the ⚠️ Low stock count's words (inv_stock.js).
const _BACKLOG_WHY = {
    spoolman: "Spoolman didn't answer just now",
    fcc: "FCC couldn't count them just now",
    unreachable: "FCC didn't answer just now",
};

// The button: "🏷️ Backlog (53)". A count a later read couldn't refresh keeps
// its number with a "?" after it (drawn in the button's padding, taking no
// room) and a dashed border, as the ⚠️ Low stock count does (global.css; Group
// 57 review, round 2: on the same failed read one looked fresh, the other
// stale); "(?)" before any count, never a 0 (Group 52's rule). Its text is
// written only when it changed: the title bar fits itself again whenever a
// button's text changes (titlebar_fit.js), and the same count rewritten on
// every tick refitted it from scratch every 5 s.
const _paintBacklogCount = (why) => {
    const btn = document.getElementById('btn-backlog-count');
    if (!btn) return;
    const known = typeof _backlogCount === 'number';
    const n = known ? String(_backlogCount) : '?';
    const stale = known && !!why;
    const key = `${n}${stale ? '?' : ''}`;
    if (btn.dataset.countShown !== key) {
        btn.dataset.countShown = key;
        btn.innerHTML = `🏷️ Backlog <span class="fcc-count-num">(${n})${stale ? '<span class="fcc-stale-mark">?</span>' : ''}</span>`;
    }
    btn.dataset.read = why ? 'failed' : 'ok';
    if (why) {
        const said = _BACKLOG_WHY[why] || _BACKLOG_WHY.fcc;
        const words = known ? `Backlog (${n})?, the last count (${said}). Opens the label backlog.`
            : `Backlog (?), no count yet (${said}). Opens the label backlog.`;
        btn.title = words;
        btn.setAttribute('aria-label', words);
    } else {
        btn.removeAttribute('title');
        btn.removeAttribute('aria-label');
    }
};

// Group 52.1a: the dashboard heartbeat counts the backlog in its label_backlog
// section (from the tick's own spool-list read plus one filament read), so the
// button no longer re-reads Spoolman's whole spool and filament lists every 5 s.
// A section that couldn't read Spoolman (read_ok false) keeps the count shown,
// marked stale, and so does a heartbeat FCC didn't answer at all ({read_ok:
// false, unreachable: true}, inv_core.js; round 3). Returns whether it painted
// a count.
window._renderBacklogCount = (sec) => {
    if (!sec || typeof sec !== 'object') return false;
    if (sec.read_ok === true && typeof sec.count === 'number') {
        _backlogCountFed = true;
        _backlogCount = sec.count;
        _paintBacklogCount(null);
        return true;
    }
    _paintBacklogCount(sec.unreachable ? 'unreachable'
        : (sec.read_ok === false && sec.read_error && !sec.error ? 'spoolman' : 'fcc'));
    return false;
};

// Group 52.1a: a refresh that fails while the list shows rows keeps them and
// says so above the list. Replacing the rows with the error left it stuck: the
// next good answer matched lastBacklogHash and never redrew the list. Same look
// as the Location Manager's "Spoolman didn't answer" notice.
const _backlogNotice = (msg) => {
    const list = document.getElementById('backlog-list');
    let el = document.getElementById('backlog-read-notice');
    if (!el && msg && list && list.parentNode) {
        el = document.createElement('div');
        el.id = 'backlog-read-notice';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.style.cssText = 'background:#2b2200; color:#ffd54a; border:1px solid #ffd54a;'
            + ' border-radius:6px; padding:8px 12px; margin-bottom:10px; font-weight:bold;';
        list.parentNode.insertBefore(el, list);
    }
    if (!el) return;
    el.textContent = msg ? `⚠️ ${msg}` : '';
    el.style.display = msg ? 'block' : 'none';
};
const _backlogReadFailed = (msg) => {
    if (lastBacklogHash) {
        _backlogNotice(`${msg} Showing the last list; it tries again every few seconds.`);
        return;
    }
    const list = document.getElementById('backlog-list');
    if (!list) return;
    // Text, not HTML: the message carries Spoolman's own words.
    const div = document.createElement('div');
    div.className = 'text-danger p-3';
    div.textContent = msg;
    list.innerHTML = '';
    list.appendChild(div);
};

// Helper to safely stack from the Backlog modal to a Detail modal
window.openBacklogDetail = (id, isSpool) => {
    if (isSpool) openSpoolDetails(id);
    else openFilamentDetails(id);
};

window.fetchBacklog = () => {
    const filter = document.getElementById('backlog-filter').value;
    const sort = document.getElementById('backlog-sort').value;
    const list = document.getElementById('backlog-list');

    // Auto-show a loading message ONLY if the list is completely empty
    if (list.innerHTML.trim() === '') {
        list.innerHTML = `<div class="text-center text-light p-3">Loading backlog...</div>`;
    }

    fetch(`/api/print_queue/pending?filter=${filter}&sort=${sort}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                _backlogReadFailed(`Error loading backlog: ${data.msg}`);
                return;
            }
            _backlogNotice('');
            const items = data.items;
            _backlogCount = items.length;
            _paintBacklogCount(null);

            // --- HASH COMPARISON TO PREVENT UI WIGGLE ---
            const newHash = JSON.stringify(items);
            if (lastBacklogHash === newHash) return; // Data is identical, stop here.

            lastBacklogHash = newHash;
            // --------------------------------------------

            if (items.length === 0) {
                list.innerHTML = `<div class="text-center text-success p-3">All labels printed!</div>`;
                const selectAll = document.getElementById('backlog-select-all');
                if (selectAll) selectAll.checked = false;
                window.updateBacklogQueueBtn();
                return;
            }

            // --- Capture currently checked items before wipe ---
            const checkedIds = new Set();
            document.querySelectorAll('.backlog-chk:checked').forEach(chk => {
                checkedIds.add(`${chk.getAttribute('data-type')}-${chk.value}`);
            });

            let html = '';
            items.forEach(item => {
                const isSpool = item.type === 'spool';
                const f = isSpool ? item.filament : item;
                const icon = isSpool ? '🧵' : '🧬';

                // Color and Name Fallbacks
                const material = f?.material || '';
                const brand = f?.vendor?.name || 'Unknown';
                const colorOrName = f?.name || f?.color_name || f?.extra?.original_color || 'Unknown';
                const name = `${material} - ${colorOrName}`.trim();
                const date = item.registered ? new Date(item.registered).toLocaleDateString() : 'Unknown Date';

                // Color Logic Matching inv_details.js Priority
                const rawColor = f?.multi_color_hexes || f?.color_hex || f?.extra?.multi_color_hexes || f?.extra?.color_hex || "333";
                const direction = f?.multi_color_direction || f?.extra?.multi_color_direction || "longitudinal";
                const styles = getFilamentStyle(rawColor, direction);

                const typeIdKey = `${item.type}-${item.id}`;
                const isCheckedAttr = checkedIds.has(typeIdKey) ? 'checked' : '';

                // Safely close the backlog modal instantly to avoid z-index blocking the new modal
                const modalTarget = isSpool ? 'openSpoolDetails' : 'openFilamentDetails';

                html += `
                <div class="cham-card mb-2 backlog-row w-100" id="backlog-item-${item.id}-${item.type}" style="background: ${styles.frame};">
                    <div class="cham-body d-flex justify-content-between align-items-center w-100 p-2" style="background: ${styles.inner}; border-radius: 8px; min-height: 75px;">
                        
                        <div class="d-flex align-items-center flex-grow-1" style="min-width: 0;">
                            <input class="form-check-input mx-3 bg-dark shadow-sm border-secondary backlog-chk flex-shrink-0" style="transform: scale(1.5); cursor: pointer;" type="checkbox" value="${item.id}" data-type="${item.type}" data-display="${brand} - ${name}" onchange="window.updateBacklogQueueBtn()" ${isCheckedAttr}>
                            
                            <div class="d-flex align-items-center cursor-pointer flex-grow-1 text-truncate" onclick="window.openBacklogDetail(${item.id}, ${isSpool})" style="padding-left: 5px;">
                                <div class="rounded-circle flex-shrink-0 me-3 shadow" style="min-width: 32px; height: 32px; background: ${styles.frame}; box-shadow: ${styles.border ? 'inset 0 0 0 2px #555' : 'none'}; border: 2px solid rgba(255,255,255,0.2);"></div>
                                
                                <div class="cham-text-group d-flex flex-column align-items-start text-truncate w-100">
                                    <div class="d-flex align-items-center text-truncate w-100">
                                        
                                        <!-- Sharp Custom ID Badge -->
                                        <div class="px-2 py-1 rounded border border-secondary d-flex justify-content-center align-items-center shadow-sm flex-shrink-0 me-2" style="background: rgba(0,0,0,0.85); min-width: 105px; height: 28px;">
                                            <span style="font-size: 1.1rem; line-height: 1; margin-right: 5px;">${icon}</span>
                                            <span style="font-weight: 800; font-size: 0.85rem; color: ${isSpool ? '#4da6ff' : '#20c997'}; letter-spacing: 0.5px;">${isSpool ? 'SPOOL' : 'FILAM'}</span>
                                            <span class="ms-1 text-white" style="font-weight: 800; font-size: 0.85rem;">#${item.id}</span>
                                        </div>

                                        <div class="text-white mt-1" style="font-size:0.85rem; background: rgba(0,0,0,0.7); padding: 2px 8px; border-radius: 4px; display: inline-block;">
                                            <span style="color:#aaa;">Added:</span> <strong style="color:#ccc;">${date}</strong>
                                        </div>
                                    </div>
                                    <div class="cham-text text-white text-truncate mt-1 w-100 text-pop" title="${brand} - ${name}" style="font-weight: 800; font-size: 1.15rem; line-height: 1.2;">
                                        ${brand} - ${name}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="ms-2 me-3 flex-shrink-0" style="min-width: 140px; text-align: right;">
                            <button class="btn btn-success shadow-sm w-100" style="font-weight: bold; border: 1px solid rgba(255,255,255,0.2);" onclick="window.markPrinted(${item.id}, '${item.type}')">
                                ✔️ Mark Printed
                            </button>
                        </div>
                    </div>
                </div>`;
            });
            list.innerHTML = html;
            window.updateBacklogQueueBtn();
        })
        .catch(e => {
            console.error(e);
            _backlogReadFailed('Connection error fetching backlog.');
        });
};

window.toggleBacklogSelectAll = () => {
    const isChecked = document.getElementById('backlog-select-all').checked;
    document.querySelectorAll('.backlog-chk').forEach(chk => chk.checked = isChecked);
    window.updateBacklogQueueBtn();
};

window.updateBacklogQueueBtn = () => {
    const count = document.querySelectorAll('.backlog-chk:checked').length;
    const btn = document.getElementById('btn-backlog-queue-selected');
    if (btn) {
        btn.innerHTML = `🖨️ Queue Selected (${count})`;
        if (count > 0) btn.classList.remove('disabled');
        else btn.classList.add('disabled');
    }

    // Auto-uncheck "Select All" if not everything is checked
    const total = document.querySelectorAll('.backlog-chk').length;
    const selectAllChx = document.getElementById('backlog-select-all');
    if (selectAllChx) {
        if (count === 0 || count < total) selectAllChx.checked = false;
        if (count === total && total > 0) selectAllChx.checked = true;
    }
};

window.queueSelectedBacklog = () => {
    const checked = document.querySelectorAll('.backlog-chk:checked');
    if (checked.length === 0) return;

    let added = 0;
    checked.forEach(chk => {
        const id = parseInt(chk.value);
        const type = chk.getAttribute('data-type');
        const display = chk.getAttribute('data-display');

        // This relies on the updated addToQueue which safely skips duplicates
        const wasAdded = window.addToQueue({ id: id, type: type, display: display });
        if (wasAdded) added++;
    });

    // Uncheck everything
    document.querySelectorAll('.backlog-chk').forEach(c => c.checked = false);
    document.getElementById('backlog-select-all').checked = false;
    window.updateBacklogQueueBtn();

    if (added > 0) {
        showToast(`Added ${added} items to Print Queue`, "success");
        // Optionally open the print queue immediately?
        // modals.backlogModal.hide();
        // setTimeout(window.openQueueModal, 300);
    } else {
        showToast("Selected items are already in the Print Queue", "info");
    }
};

window.markPrinted = (id, type) => {
    setProcessing(true);
    fetch('/api/print_queue/mark_printed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id, type: type })
    })
        .then(r => r.json())
        .then(data => {
            setProcessing(false);
            if (data.success) {
                showToast(`Marked ${type} #${id} as printed`, "success");
                window.fetchBacklog(); // Refresh list
            } else {
                // Spoolman error body now arrives in data.msg/data.error;
                // 7s duration so blind-scanning failures don't slip past
                // (CLAUDE.md convention).
                showToast(data.msg || data.error || "Error", "error", 7000);
            }
        })
        .catch(e => {
            setProcessing(false);
            showToast("Connection Error", "error", 7000);
            console.error(e);
        });
};

// Initial count: the first heartbeat (100 ms after load) brings it. Fetch it here
// only if no heartbeat has by then (Group 52.1a; it used to fetch the whole
// backlog 1.5 s after every load, two more whole-list reads).
const BACKLOG_COUNT_FALLBACK_MS = 10000;
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => { if (!_backlogCountFed) window.fetchBacklog(); }, BACKLOG_COUNT_FALLBACK_MS);
});
// Refresh the open backlog when a new pulse comes through.
document.addEventListener('inventory:sync-pulse', () => {
    // We do NOT call window.fetchBacklog() here blindly, to prevent wiping out UI selections.
    // The open window refreshes its list (fetchBacklog keeps checked boxes).
    const modal = document.getElementById('backlogModal');
    if (modal && modal.classList.contains('show')) {
        window.fetchBacklog();
    }
    // Group 52.1a: with the window closed there is nothing to fetch. The count
    // comes with the heartbeat (window._renderBacklogCount); a pulse from
    // anything else (a scan, an eject, a save) is answered by the next tick, at
    // most 5 s later while you're active, instead of re-reading Spoolman's whole
    // spool and filament lists for every one of them.
});
