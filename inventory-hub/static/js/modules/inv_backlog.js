/* MODULE: MISSING LABELS BACKLOG */
console.log("🚀 Loaded Module: MISSING LABELS BACKLOG");

window.openBacklogModal = () => {
    modals.backlogModal.show();
    window.fetchBacklog();
};

let lastBacklogHash = "";

// Helper to safely transition from the Backlog modal to a Detail modal
window.openBacklogDetail = (id, isSpool) => {
    if (window.modals && window.modals.backlogModal) {
        window.modals.backlogModal.hide();
    }
    setTimeout(() => {
        if (isSpool) openSpoolDetails(id);
        else openFilamentDetails(id);
    }, 300);
};

window.fetchBacklog = () => {
    const filter = document.getElementById('backlog-filter').value;
    const sort = document.getElementById('backlog-sort').value;
    const list = document.getElementById('backlog-list');

    // Auto-show a loading message ONLY if the list is completely empty
    if (list.innerHTML.trim() === '') {
        list.innerHTML = `<div class="text-center text-muted p-3">Loading backlog...</div>`;
    }

    fetch(`/api/print_queue/pending?filter=${filter}&sort=${sort}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                list.innerHTML = `<div class="text-danger p-3">Error loading backlog: ${data.msg}</div>`;
                return;
            }
            const items = data.items;
            document.getElementById('btn-backlog-count').innerHTML = `🏷️ Backlog (${items.length})`;

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
                const icon = isSpool ? '🧵' : '🧪';

                // Color and Name Fallbacks
                const material = f?.material || '';
                const brand = f?.vendor?.name || 'Unknown';
                const colorOrName = f?.name || f?.color_name || f?.extra?.original_color || 'Unknown';
                const name = `${material} - ${colorOrName}`.trim();
                const date = item.registered ? new Date(item.registered).toLocaleDateString() : 'Unknown Date';

                // Color Logic Matching inv_details.js Priority
                const rawColor = f?.multi_color_hexes || f?.color_hex || f?.extra?.multi_color_hexes || f?.extra?.color_hex || "333";
                const styles = getFilamentStyle(rawColor);

                const typeIdKey = `${item.type}-${item.id}`;
                const isCheckedAttr = checkedIds.has(typeIdKey) ? 'checked' : '';

                // Safely close the backlog modal instantly to avoid z-index blocking the new modal
                const modalTarget = isSpool ? 'openSpoolDetails' : 'openFilamentDetails';

                html += `
                <div class="cham-card mb-2 backlog-row w-100" id="backlog-item-${item.id}-${item.type}" style="background: ${styles.frame}; ${styles.border ? 'box-shadow: inset 0 0 0 2px #555;' : ''}">
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
                                    <div class="cham-text text-white text-truncate mt-1 w-100" title="${brand} - ${name}" style="font-weight: 800; font-size: 1.15rem; line-height: 1.2; text-shadow: 2px 2px 4px #000;">
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
            list.innerHTML = `<div class="text-danger p-3">Connection error fetching backlog.</div>`;
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
                showToast(data.msg || "Error", "error");
            }
        })
        .catch(e => {
            setProcessing(false);
            showToast("Connection Error", "error");
            console.error(e);
        });
};

// Initial count fetch on load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(window.fetchBacklog, 1500);
});
// Refresh when a new pulse comes through
document.addEventListener('inventory:sync-pulse', () => {
    // We do NOT call window.fetchBacklog() here blindly, to prevent wiping out UI selections.
    // Instead, we just refresh the data in the background if the modal isn't open, 
    // or rely on the smart logic in fetchBacklog to abort if checkboxes are active.
    const modal = document.getElementById('backlogModal');
    if (modal && modal.classList.contains('show')) {
        window.fetchBacklog();
    } else {
        // Just update count in the background without refreshing whole list fetching all unfiltered
        fetch(`/api/print_queue/pending?filter=all&sort=created_newest`)
            .then(r => r.json())
            .then(data => {
                if (data.success && data.items) {
                    document.getElementById('btn-backlog-count').innerHTML = `🏷️ Backlog (${data.items.length})`;
                }
            }).catch(() => { });
    }
});
