/* MODULE: PRINT QUEUE */
console.log("🚀 Loaded Module: QUEUE");

// Expose globally
window.labelQueue = [];
let labelQueue = window.labelQueue;

// Modal Instances & Data
let clearConfirmModal = null;
let multiSpoolModal = null;
let multiSpoolData = []; // Store search results here

window.updateQueueUI = () => {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
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
        }).catch(e => console.error("Could not set print flag:", e));
    }

    labelQueue.push(item);
    window.updateQueueUI();
    return true;
};

// Generic toast wrapper for single adds if needed
window.addToQueueWithToast = (item) => {
    if (addToQueue(item)) showToast(`Added ${item.type} to Print Queue`);
    else showToast("⚠️ Already in Queue", "warning");
}

window.openQueueModal = () => {
    const list = document.getElementById('queue-list-items');
    const emptyMsg = document.getElementById('queue-empty-msg');

    if (!list) return;
    list.innerHTML = "";

    if (labelQueue.length === 0) {
        if (emptyMsg) emptyMsg.style.display = 'block';
    } else {
        if (emptyMsg) emptyMsg.style.display = 'none';

        labelQueue.forEach((item, index) => {
            let icon = '🧵';
            if (item.type === 'filament') icon = '🧬';
            if (item.type === 'location') icon = '📍';

            list.innerHTML += `
                <li class="list-group-item bg-dark text-white border-secondary d-flex justify-content-between align-items-center">
                    <span>${icon} #${item.id} - ${item.display}</span>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeFromQueue(${index})">❌</button>
                </li>`;
        });
    }
    if (modals.queueModal) modals.queueModal.show();
};

window.removeFromQueue = (index) => {
    labelQueue.splice(index, 1);
    window.openQueueModal();
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
    window.openQueueModal();
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
                else { showToast(`❌ Error: ${res.msg}`, "error"); return false; }
            })
            .catch(e => { showToast("Connection Error", "error"); return false; });
    };

    const promises = [];
    if (spools.length > 0) promises.push(sendBatch(spools, 'spool'));
    if (filaments.length > 0) promises.push(sendBatch(filaments, 'filament'));
    if (locations.length > 0) promises.push(sendBatch(locations, 'location'));

    Promise.all(promises).then(results => {
        if (results.every(r => r === true)) {
            labelQueue.length = 0;
            window.openQueueModal();
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

/* --- PERSISTENCE LAYER --- */
const persistQueue = () => {
    fetch('/api/state/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queue: labelQueue })
    }).catch(e => console.warn("Queue Save Failed", e));
};

const loadQueue = () => {
    fetch('/api/state/queue')
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data)) {
                const currentStr = JSON.stringify(labelQueue);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    labelQueue.length = 0;
                    data.forEach(item => labelQueue.push(item));

                    const btn = document.getElementById('btn-queue-count');
                    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;

                    if (modals.queueModal && document.getElementById('queueModal').classList.contains('show')) {
                        window.openQueueModal();
                    }
                }
            }
        })
        .catch(e => console.warn("Queue Load Failed", e));
};

document.addEventListener('inventory:queue-updated', persistQueue);
setInterval(loadQueue, 2000);
document.addEventListener('DOMContentLoaded', loadQueue);