/* MODULE: PRINT QUEUE */
console.log("🚀 Loaded Module: QUEUE");

let labelQueue = [];

function updateQueueUI() {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
}

function addToQueue(item) {
    if (labelQueue.find(s => s.id === item.id && s.type === item.type)) {
        showToast("⚠️ Already in Queue", "warning");
        return;
    }
    if (!item.type) item.type = 'spool';
    labelQueue.push(item);
    updateQueueUI();
    showToast(`Added ${item.type} to Print Queue`);
}

function openQueueModal() {
    const list = document.getElementById('queue-list-items');
    if (!list) return;
    list.innerHTML = "";
    if (labelQueue.length === 0) {
        list.innerHTML = "<li class='list-group-item'>Queue is empty</li>";
    } else {
        labelQueue.forEach((item, index) => {
            const icon = item.type === 'filament' ? '🧬' : '🧵';
            list.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <span>${icon} #${item.id} - ${item.display}</span>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeFromQueue(${index})">❌</button>
                </li>`;
        });
    }
    if (modals.queueModal) modals.queueModal.show();
}

function removeFromQueue(index) {
    labelQueue.splice(index, 1);
    openQueueModal(); 
    updateQueueUI();
}

function clearQueue() {
    requestConfirmation("⚠️ Clear the entire Print Queue?", () => {
        labelQueue = [];
        openQueueModal();
        updateQueueUI();
        showToast("Queue Cleared");
    });
}

function printQueueCSV() {
    if (labelQueue.length === 0) return;
    const overwrite = document.getElementById('chk-overwrite-csv').checked;
    const spools = labelQueue.filter(i => i.type === 'spool').map(i => i.id);
    const filaments = labelQueue.filter(i => i.type === 'filament').map(i => i.id);
    
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

    Promise.all(promises).then(results => {
        if (results.every(r => r === true)) {
            labelQueue = [];
            openQueueModal();
            updateQueueUI();
            modals.queueModal.hide();
        }
    });
}

const findMultiColorFilaments = () => {
    setProcessing(true);
    fetch('/api/get_multicolor_filaments')
    .then(r => r.json())
    .then(data => {
        setProcessing(false);
        if (data.length === 0) { showToast("No Multi-Color Filaments Found", "warning"); return; }
        if (confirm(`Found ${data.length} Multi-Color Filaments. Add to Queue?`)) {
            let added = 0;
            data.forEach(item => {
                if (!labelQueue.find(q => q.id === item.id && q.type === 'filament')) {
                    addToQueue({ id: item.id, type: 'filament', display: item.display });
                    added++;
                }
            });
            showToast(`Added ${added} swatches!`);
            openQueueModal();
        }
    })
    .catch(() => { setProcessing(false); showToast("Search Error", "error"); });
};