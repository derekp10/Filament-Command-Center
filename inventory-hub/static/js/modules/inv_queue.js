/* MODULE: PRINT QUEUE */
console.log("🚀 Loaded Module: QUEUE");

// Expose the queue globally so other modules (like Details) can check for duplicates
window.labelQueue = [];
let labelQueue = window.labelQueue; // Keep local reference for convenience

window.updateQueueUI = () => {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
};

window.addToQueue = (item) => {
    // Check for duplicates
    if (labelQueue.find(s => s.id === item.id && s.type === item.type)) {
        showToast("⚠️ Already in Queue", "warning");
        return;
    }
    if (!item.type) item.type = 'spool';
    
    labelQueue.push(item);
    window.updateQueueUI();
    showToast(`Added ${item.type} to Print Queue`);
};

window.openQueueModal = () => {
    const list = document.getElementById('queue-list-items');
    if (!list) return;
    list.innerHTML = "";
    if (labelQueue.length === 0) {
        list.innerHTML = "<li class='list-group-item'>Queue is empty</li>";
    } else {
        labelQueue.forEach((item, index) => {
            let icon = '🧵';
            if (item.type === 'filament') icon = '🧬';
            if (item.type === 'location') icon = '📍';
            
            list.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
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

window.clearQueue = () => {
    requestConfirmation("⚠️ Clear the entire Print Queue?", () => {
        labelQueue = [];
        window.openQueueModal();
        window.updateQueueUI();
        showToast("Queue Cleared");
    });
};

window.printQueueCSV = () => {
    if (labelQueue.length === 0) return;
    const overwrite = document.getElementById('chk-overwrite-csv').checked;
    
    const spools = labelQueue.filter(i => i.type === 'spool').map(i => i.id);
    const filaments = labelQueue.filter(i => i.type === 'filament').map(i => i.id);
    const locations = labelQueue.filter(i => i.type === 'location').map(i => i.id); // New Location Support
    
    const sendBatch = (ids, mode) => {
        return fetch('/api/print_batch_csv', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ids: ids, mode: mode, clear_old: overwrite })
        })
        .then(r => r.json())
        .then(res => {
            if(res.success) { showToast(`✅ ${mode} Batch Saved!`); return true; } 
            else { showToast(`❌ Error: ${res.msg}`, "error"); return false; }
        })
        .catch(e => { showToast("Connection Error", "error"); return false; });
    };

    const promises = [];
    if (spools.length > 0) promises.push(sendBatch(spools, 'spool'));
    if (filaments.length > 0) promises.push(sendBatch(filaments, 'filament'));
    // Note: If your backend api/print_batch_csv supports 'location', this will work. 
    // If not, we might need a separate endpoint for location labels later.
    if (locations.length > 0) promises.push(sendBatch(locations, 'location')); 

    Promise.all(promises).then(results => {
        if (results.every(r => r === true)) {
            labelQueue = [];
            window.openQueueModal();
            window.updateQueueUI();
            modals.queueModal.hide();
        }
    });
};

/* --- REPLACED: Multi-Spool Logic instead of Multi-Color --- */
window.findMultiSpoolFilaments = () => {
    setProcessing(true);
    // Call the new API endpoint we created
    fetch('/api/get_multi_spool_filaments')
    .then(r => r.json())
    .then(data => {
        setProcessing(false);
        if (data.length === 0) { showToast("No Multi-Spool Filaments Found", "info"); return; }
        
        // Calculate total spools to add
        const totalSpools = data.reduce((acc, item) => acc + item.count, 0);
        const msg = `Found ${data.length} Filaments with multiple spools.\n(Total ${totalSpools} spools).\n\nAdd ALL ${totalSpools} spools to Print Queue?`;
        
        if (confirm(msg)) {
            let added = 0;
            data.forEach(fil => {
                // Add each spool for this filament
                fil.spool_ids.forEach(sid => {
                    // Check for duplicates in queue
                    if (!window.labelQueue.find(q => q.id === sid && q.type === 'spool')) {
                        // We construct a display name for the queue
                        window.addToQueue({ 
                            id: sid, 
                            type: 'spool', 
                            display: `${fil.display} (ID:${sid})` 
                        });
                        added++;
                    }
                });
            });
            showToast(`Added ${added} spools!`);
            window.openQueueModal();
        }
    })
    .catch(() => { setProcessing(false); showToast("Search Error", "error"); });
};

/* --- PERSISTENCE LAYER: QUEUE (V2 Fixed) --- */

// 1. Redefine UpdateUI to emit an event (Matches the Buffer Strategy)
// We overwrite the original function to add the "Dispatch" signal.
window.updateQueueUI = () => {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
    
    // Dispatch the event so our persister hears it
    document.dispatchEvent(new CustomEvent('inventory:queue-updated', { detail: { queue: labelQueue } }));
};

/* --- PERSISTENCE LAYER: QUEUE (V3 Polling) --- */

// 1. Redefine UpdateUI to emit an event
window.updateQueueUI = () => {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
    document.dispatchEvent(new CustomEvent('inventory:queue-updated', { detail: { queue: labelQueue } }));
};

const persistQueue = () => {
    fetch('/api/state/queue', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({queue: labelQueue})
    }).catch(e => console.warn("Queue Save Failed", e));
};

const loadQueue = () => {
    fetch('/api/state/queue')
    .then(r => r.json())
    .then(data => {
        if (Array.isArray(data)) {
            // SMART SYNC: Only update if the server has DIFFERENT data than we do
            // We compare 'JSON stringified' versions to detect changes
            const currentStr = JSON.stringify(labelQueue);
            const serverStr = JSON.stringify(data);
            
            if (currentStr !== serverStr) {
                console.log("🔄 Syncing Queue from Server...");
                labelQueue.length = 0;
                data.forEach(item => labelQueue.push(item));
                
                // Update UI without triggering a save loop (we silence the event dispatch here)
                const btn = document.getElementById('btn-queue-count');
                if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
                
                if (window.openQueueModal && document.getElementById('queueModal')?.classList.contains('show')) {
                     window.openQueueModal(); // Refresh modal if open
                }
            }
        }
    })
    .catch(e => console.warn("Queue Load Failed", e));
};

// 2. Listen for local updates to save
document.addEventListener('inventory:queue-updated', persistQueue);

// 3. Start the Heartbeat (Checks every 2 seconds)
setInterval(loadQueue, 2000);

// 4. Initial Load
document.addEventListener('DOMContentLoaded', loadQueue);