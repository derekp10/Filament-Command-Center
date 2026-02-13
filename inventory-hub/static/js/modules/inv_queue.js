/* MODULE: PRINT QUEUE */
console.log("🚀 Loaded Module: QUEUE");

// Expose globally so inv_details.js can see it
window.labelQueue = [];
let labelQueue = window.labelQueue; 

window.updateQueueUI = () => {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
    // Dispatch event for persistence
    document.dispatchEvent(new CustomEvent('inventory:queue-updated', { detail: { queue: labelQueue } }));
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
    const emptyMsg = document.getElementById('queue-empty-msg');
    
    if (!list) return;
    list.innerHTML = "";

    // LOGIC FIX: Toggle the Empty Message Div
    if (labelQueue.length === 0) {
        if(emptyMsg) emptyMsg.style.display = 'block';
    } else {
        if(emptyMsg) emptyMsg.style.display = 'none';
        
        labelQueue.forEach((item, index) => {
            let icon = '🧵';
            if (item.type === 'filament') icon = '🧬';
            if (item.type === 'location') icon = '📍';
            
            // Added bg-black and text-white for list items
            list.innerHTML += `
                <li class="list-group-item bg-black text-white border-secondary d-flex justify-content-between align-items-center">
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
    // Simple confirm
    if(confirm("⚠️ Clear the entire Print Queue?")) {
        labelQueue.length = 0; // Clear array in place
        window.openQueueModal();
        window.updateQueueUI();
        showToast("Queue Cleared");
    }
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

/* --- NEW FEATURE: Find Multi-Spool Filaments --- */
window.findMultiSpoolFilaments = () => {
    setProcessing(true);
    fetch('/api/get_multi_spool_filaments')
    .then(r => r.json())
    .then(data => {
        setProcessing(false);
        if (data.length === 0) { showToast("No Multi-Spool Filaments Found", "info"); return; }
        
        const totalSpools = data.reduce((acc, item) => acc + item.count, 0);
        const msg = `Found ${data.length} Filaments with multiple spools.\n(Total ${totalSpools} spools).\n\nAdd ALL ${totalSpools} spools to Print Queue?`;
        
        if (confirm(msg)) {
            let added = 0;
            data.forEach(fil => {
                fil.spool_ids.forEach(sid => {
                    if (!labelQueue.find(q => q.id === sid && q.type === 'spool')) {
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

/* --- PERSISTENCE LAYER (Polling) --- */
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
            const currentStr = JSON.stringify(labelQueue);
            const serverStr = JSON.stringify(data);
            
            if (currentStr !== serverStr) {
                // Sync from Server
                labelQueue.length = 0;
                data.forEach(item => labelQueue.push(item));
                
                // Update UI manually to avoid loop
                const btn = document.getElementById('btn-queue-count');
                if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
                
                // Refresh modal if open
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