/* MODULE: BULK WEIGH-OUT */
console.log("⚖️ Loaded Module: BULK WEIGH-OUT");

let processedWeighIds = new Set();

// Phase 2 (Group 12): modal-level weigh-out mode. Defaults to 'net' so the
// historical "input is remaining filament weight" UX is preserved. Switching
// to gross / additive / set_used routes the row's input through
// computeUsedWeight() with the spool's resolved cascade (initial / used /
// empty_spool_weight). Stored on window so the unit-test harness can inspect.
window.weighOutMode = 'net';

// Per-spool details cache populated on modal open and on buffer-updated.
// Keyed by spool id. Each entry: { initial, used, empty, cascade, context, fetchedAt }.
const weighOutDetailsCache = new Map();
const MODE_HINTS = {
    gross: 'used = initial − (gross − empty_tare)',
    net: 'used = initial − net',
    additive: 'used = current_used + delta',
    set_used: 'used = value (override)',
};
const MODE_PLACEHOLDERS = {
    gross: 'scale w/ spool',
    net: 'remaining',
    additive: '+25 / -10',
    set_used: 'used',
};
// Every box is a text box, with a number pad on a phone where the mode takes a
// plain reading (Group 57 review, round 8). A number box reads "645." as 645
// and can't say what was typed, so a redraw between the '.' and the next digit
// saved 6455 (in Set Used the spool read empty and was archived), and it kept
// only the digits of "0.645kg" or "6,45". A text box keeps what was typed, and
// a reading is read strictly (window.parseGramsReading): anything but grams is
// refused.
const MODE_INPUT_MODES = {
    gross: 'decimal',
    net: 'decimal',
    additive: 'text',
    set_used: 'decimal',
};

const fetchSpoolDetails = (id) => {
    return fetch(`/api/spool_details?id=${id}`)
        .then((r) => r.json())
        .then((d) => {
            if (!d || !d.id) return null;
            const cascade = {
                spoolWt: d.spool_weight,
                filamentWt: d.filament?.spool_weight,
                vendor: d.filament?.vendor,
            };
            const { value: empty } = window.resolveEmptySpoolWeightSource(cascade);
            const entry = {
                initial: Number(d.initial_weight) || Number(d.filament?.weight) || 0,
                used: Number(d.used_weight) || 0,
                empty,
                cascade,
                context: {
                    vendor: d.filament?.vendor?.name || '',
                    material: d.filament?.material || '',
                    color: d.filament?.name || '',
                    color_hex: d.filament?.color_hex || d.color_hex || null,
                },
                fetchedAt: Date.now(),
            };
            weighOutDetailsCache.set(d.id, entry);
            return entry;
        })
        .catch(() => null);
};

const refreshAllRowPreviews = () => {
    document.querySelectorAll('.weigh-row').forEach((row) => {
        const inp = row.querySelector('.weigh-input');
        if (inp) updateWeighRowPreview(inp);
    });
};

const setWeighOutMode = (mode) => {
    if (!['gross', 'net', 'additive', 'set_used'].includes(mode)) return;
    window.weighOutMode = mode;
    document.querySelectorAll('#weigh-out-mode [data-mode]').forEach((btn) => {
        const active = btn.dataset.mode === mode;
        btn.classList.toggle('btn-info', active);
        btn.classList.toggle('btn-outline-info', !active);
    });
    const hint = document.getElementById('weigh-out-mode-hint');
    if (hint) hint.innerText = MODE_HINTS[mode] || '';
    // Refresh placeholders + keyboards + previews on every visible row.
    document.querySelectorAll('.weigh-input').forEach((inp) => {
        inp.inputMode = MODE_INPUT_MODES[mode];
        inp.placeholder = MODE_PLACEHOLDERS[mode];
    });
    refreshAllRowPreviews();
};

window.openWeighOutModal = () => {
    // Sync UI to state.heldSpools but ignore processed ones for this session
    processedWeighIds.clear();
    fadeTimers.forEach((t) => clearTimeout(t));
    fadeTimers.clear();
    pendingScan = null;
    rescanAfterSave = null;
    // 31.3 review fix: start every session fresh. Closing the modal does NOT
    // clear #weigh-out-list, so rows (with any un-submitted text) linger in the
    // hidden DOM. Wipe them BEFORE the first render so the preserve-text
    // snapshot in renderWeighOutList captures nothing on open and can't
    // resurrect a stale reading into a perceived-fresh weigh-out session. The
    // in-session save / buffer-updated redraws still preserve text (the rows
    // exist at that point).
    const listEl = document.getElementById('weigh-out-list');
    if (listEl) listEl.innerHTML = '';
    renderWeighOutList();
    // The first row is the target until the person or a scan picks another.
    const firstBox = document.querySelector('#weigh-out-list .weigh-input:not(:disabled)');
    weighTargetId = firstBox ? firstBox.dataset.id : null;
    modals.weighOutModal.show();

    // Wire the mode selector exactly once per page lifetime.
    const modeBar = document.getElementById('weigh-out-mode');
    if (modeBar && !modeBar.dataset.fccBound) {
        modeBar.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-mode]');
            if (!btn) return;
            setWeighOutMode(btn.dataset.mode);
        });
        modeBar.dataset.fccBound = '1';
    }
    setWeighOutMode(window.weighOutMode || 'net');

    // Prefetch details for each held spool so previews can render eagerly.
    state.heldSpools
        .filter((s) => !processedWeighIds.has(s.id))
        .forEach((s) => {
            fetchSpoolDetails(s.id).then(() => {
                const inp = document.querySelector(`.weigh-input[data-id="${s.id}"]`);
                if (inp) updateWeighRowPreview(inp);
            });
        });

    // A weight key typed on the window's other controls (a mode button, the
    // Auto-Archive switch, the window itself) goes into the target's box, one
    // typed on a row's 💾 into that row's (inv_core.js's weight capture,
    // data-fcc-weight-keys; Group 57 review, rounds 7 and 8). With no box for
    // it while a scan is being answered, it is held for the spool the scan
    // names (an empty list: it stayed in the scan buffer, and the reading was
    // saved cut short).
    const modalEl = document.getElementById('weighOutModal');
    if (modalEl) {
        modalEl.fccWeightBox = (from) => {
            const row = from && from.closest ? from.closest('.weigh-row') : null;
            return row ? row.querySelector('.weigh-input:not(:disabled)') : currentWeighBox();
        };
        modalEl.fccWeightHold = (key) => {
            if (!pendingScan) return false;
            pendingScan.held += key;
            return true;
        };
        // The last `n` held keys, taken back: a scanner sent them (inv_core.js:
        // a scan never becomes a reading).
        modalEl.fccWeightUnhold = (n) => {
            if (!pendingScan || !n) return '';
            const keys = pendingScan.held.slice(-n);
            pendingScan.held = pendingScan.held.slice(0, -n);
            return keys;
        };
    }

    // Auto-focus the first empty input after modal shown, but never while a
    // scan is arriving (Group 57 review, round 6): the WEIGH QR and the first
    // spool's label scanned back to back were split between the scan buffer
    // and the box, and the label's digits that reached the box were saved as
    // that spool's weight. It waits for the scan to finish (the weight capture
    // in inv_core.js puts a split label back together too), and leaves a box
    // the person has already clicked into alone.
    let waited = 0;
    const focusFirst = () => {
        const ae = document.activeElement;
        if (ae && ae.classList && ae.classList.contains('weigh-input')) return;
        if (state.scanBuffer && waited < 3000) { waited += 150; setTimeout(focusFirst, 150); return; }
        if (!weighOutIsUp()) return;
        const box = currentWeighBox();
        if (box) box.focus();
    };
    setTimeout(focusFirst, 500);
};

// ---------------------------------------------------------------------------
// Scan capture while a weight field has focus (2026-08-03 scan-path audit)
//
// This modal advertises live scanning TWICE — "…or scan them now while this
// window is open!" and "Scan new items to add to this list." — and that really
// works: a scan lands in state.heldSpools and the buffer-updated listener below
// redraws the list. But openWeighOutModal auto-focuses the first weight input
// (deliberately: typing weights is the primary action here), and the global
// scan accumulator's first line is `if (e.target.tagName === 'INPUT') return;`.
// So the advertised feature was dead, and worse, the barcode was typed INTO the
// weight box — in 'additive' mode that box is type="text", so the terminating
// Enter tried to save the barcode AS A WEIGHT.
//
// Rather than drop the auto-focus (Derek wants the cursor there), each box is
// a weight box (class fcc-weight-box), and inv_core.js's weight capture hands
// a scan typed into it to the global scan path: a label is proved by its ':'
// or '/' at any speed, anything else a weight can't hold by scanner speed
// (Group 57 review, rounds 5 and 6: the whole payload had to arrive in under
// 150ms, so a slower scanner's label was typed in as a weight), and digits
// alone faster than a person types them, an old digits-only label (Derek,
// 2026-10-28: a scan must never add to a weight). A reading with a '.', a
// grams unit or a padding Space stays a weight at any speed, as a scale that
// types its reading sends it.
//
// Where the next reading goes (Group 57 review, rounds 7 and 8). The window's
// flow is "scan a spool, type its weight", and a scanned spool's row is drawn
// at the top. The list keeps a TARGET, the spool whose reading is being
// entered: its box taking the focus makes it the target (a click or Tab into
// it, a click on its row, the save moving on to the next row), and so does a
// scan that names a spool, even one answered while a dialog is over the list.
// A weight key typed on the window's other controls goes into the target's box
// (one typed on a row's 💾, into that row's), and the focus comes back to it
// when a dialog over the list closes. Round 7 sent both to the box that had
// had the focus last, which a scan under a prompt never changed, and round 6
// kept the focus there through a scan: each time the reading for the spool in
// the person's hand was saved to another spool (at 0 g that spool was
// archived and taken off its place).
// - A scanned spool's box takes the focus. One weighed this session (its row
//   faded away) is drawn again (round 8: the reading meant to weigh it again
//   went in the next spool's box).
// - What was typed while the scan was answered goes with it (processScan calls
//   weighOutScanStart as it sends a scan, weighOutTakeScan once the answer
//   names a spool, weighOutScanDone after any answer): a reading started in
//   the box that had the focus, or typed on another control (it went in the
//   target's box), or with no box to go in (an empty list: held for it).
//   Until the answer, Enter saves nothing (round 8: a reading and Enter typed
//   before the answer were saved to another spool).
// - The missing-tare and empty-weight prompts close when a spool is scanned
//   over them, and neither opens once a spool scan has been answered since
//   its Enter (round 8): the scanned spool's reading went in the prompt's box,
//   as an empty spool weight.
let weighTargetId = null;       // the target's spool id (a string), or null
let pendingScan = null;         // a scan sent while the window is open, not yet answered
let scanSeq = 0;                // weighOutScanStart's count: only the latest scan moves the focus
let scansTaken = 0;             // spool scans weighOutTakeScan took ("since" for the prompts)
let rescanAfterSave = null;     // a spool scanned while its own save was on its way
const fadeTimers = new Map();   // a saved row's fade, by spool id
document.addEventListener('focusin', (e) => {
    const t = e.target;
    if (t && t.classList && t.classList.contains('weigh-input')) weighTargetId = t.dataset.id;
});

const boxFor = (id) => (id == null ? null
    : document.querySelector(`#weigh-out-list .weigh-input[data-id="${id}"]:not(:disabled)`));

// The target's box (none while its save is on its way). With no target, or
// its row gone, the only box listed: never a guess among several spools.
const currentWeighBox = () => {
    const list = document.getElementById('weigh-out-list');
    if (!list) return null;
    if (weighTargetId != null && list.querySelector(`.weigh-row[data-id="${weighTargetId}"]`)) return boxFor(weighTargetId);
    const boxes = list.querySelectorAll('.weigh-input:not(:disabled)');
    return boxes.length === 1 ? boxes[0] : null;
};

const weighOutShown = () => {
    const modalEl = document.getElementById('weighOutModal');
    return !!(modalEl && modalEl.classList.contains('show'));
};
// Open, with no overlay over it (the prompts, a question): the person is here.
const weighOutIsUp = () => weighOutShown() && !document.querySelector('[data-overlay-mount="1"]');

// The focus back in the target's box after something over the window took
// it. True when a box has it.
window.weighOutRefocus = () => {
    if (!weighOutIsUp()) return false;
    const box = currentWeighBox();
    if (!box) return false;
    box.focus();
    return true;
};

// A saved spool's row drawn again for another reading: its box empty (the
// redraw keeps what a box held, the saved reading too) and its details read
// afresh (its used weight has changed).
const showAgain = (n) => {
    processedWeighIds.delete(n);
    weighOutDetailsCache.delete(n);
    renderWeighOutList();
    const box = boxFor(n);
    if (box && box.value) { box.value = ''; window.updateWeighRowPreview(box); }
    fetchSpoolDetails(n).then(() => { const b = boxFor(n); if (b) window.updateWeighRowPreview(b); });
};
const refocusAfterFailedSave = (n, inputEl) => {
    if (rescanAfterSave !== n) return;
    rescanAfterSave = null;
    if (inputEl && weighOutIsUp() && weighTargetId === String(n)) inputEl.focus();
};

// processScan, as it sends a scan: where the person's keys were. Null when the
// window isn't open.
window.weighOutScanStart = () => {
    if (!weighOutShown()) return null;
    const ae = document.activeElement;
    const el = ae && ae.classList && ae.classList.contains('fcc-weight-box') ? ae : null;
    const t = currentWeighBox();
    pendingScan = { seq: ++scanSeq, el, id: el && el.dataset.id != null ? el.dataset.id : null,
        value: el ? el.value : null, targetId: t ? t.dataset.id : null, targetValue: t ? t.value : null, held: '' };
    return pendingScan;
};

// After the scan's answer, whatever it was: a reading held for it that no
// spool took is said to be gone, never kept for a later scan.
window.weighOutScanDone = (from) => {
    if (!from || pendingScan !== from) return;
    pendingScan = null;
    if (from.held) showToast(`The reading typed while a scan was read ("${from.held}") wasn't kept: type it again`, 'warning', 7000);
};

// What was typed since the scan was read, taken out of where it went: the
// held keys, and what was added to the end of the box that had the focus or of
// the target's. Never from a box the person moved to meanwhile.
const takeTyped = (from, box) => {
    if (!from) return '';
    let typed = from.held;
    from.held = '';
    const ae = document.activeElement;
    if (!ae || ae === box || !ae.classList || !ae.classList.contains('fcc-weight-box')) return typed;
    let was = null;
    if (ae === from.el || (from.id != null && ae.dataset.id === from.id)) was = from.value;
    else if (from.targetId != null && ae.dataset.id === from.targetId) was = from.targetValue;
    if (was == null || ae.value.length <= was.length || !ae.value.startsWith(was)) return typed;
    typed += ae.value.slice(was.length);
    ae.value = was;
    ae.dispatchEvent(new Event('input', { bubbles: true }));
    return typed;
};

// The prompt on top of the list that closes when a spool is scanned over it
// (fccDismissForScan).
const topWeighPrompt = () => {
    const top = Array.from(document.querySelectorAll('[data-overlay-mount="1"]'))
        .find((m) => window.isTopOverlay && window.isTopOverlay(m));
    return top && typeof top.fccDismissForScan === 'function' ? top : null;
};

// A scan named spool `spoolId` (processScan; `from`, weighOutScanStart's): it
// is the target, and its box takes the focus with what was typed since the
// scan was read as its reading. With nothing typed, what its box holds is
// selected, so the reading typed next replaces it.
window.weighOutTakeScan = (spoolId, from) => {
    if (!weighOutShown() || (from && from.seq !== scanSeq)) return;   // a later scan has the say
    const id = String(spoolId);
    const n = Number(spoolId);
    weighTargetId = id;
    scansTaken += 1;
    // Weighed this session (its row has faded away, or is fading): drawn
    // again. Its own save still on its way: its box opens again once that has
    // landed.
    const fade = fadeTimers.get(n);
    if (fade) { clearTimeout(fade); fadeTimers.delete(n); }
    if (fade || processedWeighIds.has(n)) showAgain(n);
    const box = boxFor(id);
    if (!box && document.querySelector(`#weigh-out-list .weigh-row[data-id="${id}"]`)) rescanAfterSave = n;
    const modalEl = document.getElementById('weighOutModal');
    const prompt = topWeighPrompt();
    const ae = document.activeElement;
    // Another window over this one keeps the focus: the target's box gets it
    // when that window closes.
    if (!prompt && (!weighOutIsUp() || (ae && ae !== document.body && !modalEl.contains(ae)))) return;
    if (!box) {
        // Meanwhile no other spool's box keeps the focus.
        if (rescanAfterSave === n) {
            if (prompt) prompt.fccDismissForScan();
            modalEl.focus();
        }
        return;
    }
    const typed = takeTyped(from, box);
    if (from && pendingScan === from) pendingScan = null;
    if (prompt) prompt.fccDismissForScan();
    // Typed into its own box meanwhile (it had the focus, or was the target):
    // that is the reading, never selected for the next key to replace.
    const changed = !!from && ((from.id === id && box.value !== from.value)
        || (from.targetId === id && box.value !== from.targetValue));
    box.focus();
    if (typed) {
        box.value = typed;
        window.updateWeighRowPreview(box);
    } else if (!changed) {
        try { box.select(); } catch (_) { /* nothing to select */ }
    }
};

// Another window closed over this one: the focus back in the target's box.
// The weigh-out window itself closed: nothing is pending.
document.addEventListener('hidden.bs.modal', (e) => {
    if (e.target && e.target.id === 'weighOutModal') { pendingScan = null; rescanAfterSave = null; return; }
    const modalEl = document.getElementById('weighOutModal');
    const ae = document.activeElement;
    if (modalEl && ae && ae !== document.body && modalEl.contains(ae)) return;
    window.weighOutRefocus();
});

// A click on a row's card (its name, its "Current" line) picks that row: its
// box takes the focus (round 8: the focus went to the window itself, and the
// reading typed next to the box that had had it, another spool's).
document.addEventListener('click', (e) => {
    const t = e.target;
    const row = t && t.closest ? t.closest('#weigh-out-list .weigh-row') : null;
    if (!row || t.closest('input, button, a, select, textarea, label')) return;
    const sel = window.getSelection ? window.getSelection() : null;
    if (sel && !sel.isCollapsed) return;           // its text being selected
    const box = row.querySelector('.weigh-input:not(:disabled)');
    if (box) box.focus();
});

// Also refresh the UI any time the buffer updates while the modal is open
document.addEventListener('inventory:buffer-updated', () => {
    const weighModalEl = document.getElementById('weighOutModal');
    if (weighModalEl && weighModalEl.classList.contains('show')) {
        renderWeighOutList();
        // New spools may have appeared — fetch details for any uncached.
        state.heldSpools.forEach((s) => {
            if (!processedWeighIds.has(s.id) && !weighOutDetailsCache.has(s.id)) {
                fetchSpoolDetails(s.id).then(() => {
                    const inp = document.querySelector(`.weigh-input[data-id="${s.id}"]`);
                    if (inp) updateWeighRowPreview(inp);
                });
            }
        });
    }
});

const renderWeighOutList = () => {
    const container = document.getElementById('weigh-out-list');
    const emptyMsg = document.getElementById('weigh-out-empty');
    const countBadge = document.getElementById('weigh-out-count');

    // 31.3 — Saving one row (or any buffer-updated pulse) rebuilds this whole
    // list via innerHTML, which blows away the un-submitted text the user has
    // already keyed into the OTHER rows. Snapshot every row's current input
    // value (keyed by spool id) BEFORE the rebuild so we can restore the ones
    // whose spool is still in the list afterwards. Preserve-text is the
    // least-surprising fix (vs. a Save-All button or a data-loss warning).
    const preservedInputs = {};
    container.querySelectorAll('.weigh-input').forEach((inp) => {
        if (inp.value !== '') preservedInputs[inp.dataset.id] = inp.value;
    });
    // The box being typed into keeps the focus through the rebuild (Group 57
    // review, round 6): the redraw a scan or a heartbeat makes replaced it, the
    // focus fell to the page, and the person's next reading went to the scan
    // path as a spool id.
    const active = document.activeElement;
    const focusedId = (active && active.classList && active.classList.contains('weigh-input')
        && container.contains(active)) ? active.dataset.id : null;
    let caret = null;
    if (focusedId) { try { caret = [active.selectionStart, active.selectionEnd]; } catch (_) { caret = null; } }

    const activeSpools = state.heldSpools.filter(s => !processedWeighIds.has(s.id));

    countBadge.innerText = `${activeSpools.length} Spools Ready`;

    if (activeSpools.length === 0) {
        container.innerHTML = "";
        emptyMsg.style.display = "block";
        return;
    }

    emptyMsg.style.display = "none";

    const mode = window.weighOutMode || 'net';
    const inputMode = MODE_INPUT_MODES[mode];
    const placeholder = MODE_PLACEHOLDERS[mode];

    let html = "";
    activeSpools.forEach((spool) => {
        const styles = getFilamentStyle(spool.color, spool.color_direction || 'longitudinal');
        const nameParts = spool.display.split('-');
        let mainName = spool.display;
        if(nameParts.length > 2) {
            mainName = nameParts.slice(0, 2).join('-');
        }

        let currentWeightDisplay = spool.remaining_weight ? window.fmtGramsPrecise(spool.remaining_weight) : '';

        html += `
            <div class="card bg-dark border-secondary p-2 d-flex flex-row align-items-center gap-3 weigh-row" data-id="${spool.id}" style="border-left: 5px solid ${styles.frame};">
                <div style="width: 25px; height: 25px; border-radius: 5px; background: ${styles.inner}; border: 1px solid #555;"></div>
                <div class="flex-grow-1">
                    <div class="fw-bold text-light flex-wrap">ID:${spool.id} - ${mainName}</div>
                    <div class="small w-100 text-white-50 d-inline-block pb-1">Current: ${currentWeightDisplay ? currentWeightDisplay + 'g' : 'Unknown'}</div>
                    <div class="small text-info weigh-row-preview" data-id="${spool.id}" style="min-height:1em;"></div>
                </div>
                <div class="input-group" style="width: 150px;">
                    <input type="text" inputmode="${inputMode}" autocomplete="off" class="form-control bg-dark text-white border-secondary weigh-input fcc-weight-box"
                        data-id="${spool.id}" placeholder="${placeholder}"
                        oninput="window.updateWeighRowPreview(this)"
                        onkeydown="window.handleWeighInput(event, this)">
                    <span class="input-group-text bg-secondary text-light border-secondary">g</span>
                </div>
                <button class="btn btn-outline-success btn-sm weigh-save-btn" data-id="${spool.id}" onclick="window.saveWeighOutRow(${spool.id})">
                    💾
                </button>
            </div>
        `;
    });

    container.innerHTML = html;

    // 31.3 — Restore the values snapshotted above onto the rebuilt rows and
    // recompute each preview so the row reads exactly as the user left it
    // (the saved row is already dropped from activeSpools, so its value is
    // intentionally not restored). A row that just got its value cleared is
    // left blank; only non-empty entries were captured.
    Object.entries(preservedInputs).forEach(([id, value]) => {
        const inp = container.querySelector(`.weigh-input[data-id="${id}"]`);
        if (inp) {
            inp.value = value;
            window.updateWeighRowPreview(inp);
        }
    });
    if (focusedId) {
        const inp = container.querySelector(`.weigh-input[data-id="${focusedId}"]`);
        if (inp && !inp.disabled) {
            inp.focus();
            if (caret && caret[0] !== null) {
                try { inp.setSelectionRange(caret[0], caret[1]); } catch (_) { /* a number box has no caret to set */ }
            }
        }
    }
};

// Compute used_weight for a row given the modal-level mode + the cached
// spool details + the row's typed input. Returns the computeUsedWeight
// result object (or null when details aren't loaded yet / input is empty).
const computeRowResult = (id, rawInputValue) => {
    const details = weighOutDetailsCache.get(Number(id));
    if (!details) return null;
    const mode = window.weighOutMode || 'net';
    let value;
    if (mode === 'additive') {
        const parsed = window.parseAdditiveInput(rawInputValue);
        value = parsed.value;
    } else {
        if (rawInputValue === '' || rawInputValue === null || rawInputValue === undefined) return null;
        value = window.parseGramsReading(rawInputValue);
        if (Number.isNaN(value)) return { error: 'not_a_reading' };
    }
    if (value === null || Number.isNaN(value)) return null;
    return window.computeUsedWeight({
        mode,
        value,
        initial_weight: details.initial,
        current_used: details.used,
        empty_spool_weight: details.empty,
    });
};

// Live mini-preview under each row. Mirrors the WeightEntry overlay's
// preview semantics so users see the same numbers regardless of surface.
window.updateWeighRowPreview = (inputEl) => {
    if (!inputEl) return;
    const id = inputEl.dataset.id;
    const previewEl = document.querySelector(`.weigh-row-preview[data-id="${id}"]`);
    if (!previewEl) return;
    const raw = inputEl.value;
    if (raw === '' || raw === '+' || raw === '-') {
        previewEl.innerText = '';
        return;
    }
    const r = computeRowResult(id, raw);
    if (!r) {
        previewEl.innerText = ''; // details still loading
        return;
    }
    if (r.error) {
        previewEl.innerHTML = `<span style="color:#f88;">Invalid input</span>`;
        return;
    }
    if (r.requires_empty) {
        previewEl.innerHTML = `<span style="color:#f5b342;">⚠ missing tare — Save will prompt</span>`;
        return;
    }
    let cap = '';
    if (r.capped === 'high') cap = ' <span style="color:#f5b342;">(capped)</span>';
    else if (r.capped === 'low') cap = ' <span style="color:#f5b342;">(clamped to 0)</span>';
    previewEl.innerHTML = `→ used <strong>${window.fmtGramsPrecise(r.used_weight)}g</strong> · remaining <strong>${window.fmtGramsPrecise(r.remaining)}g</strong>${cap}`;
};

window.handleWeighInput = (e, inputEl) => {
    // If enter pressed, trigger save
    if (e.key === 'Enter') {
        e.preventDefault();
        const sid = inputEl.dataset.id;
        const weight = inputEl.value;
        if (weight !== '') {
            window.saveWeighOutRow(sid);
        } else {
            // Just skip to next if empty
            focusNextInput(inputEl);
        }
    }
};

// New per-row save path that runs the typed value through computeUsedWeight
// before handing off to saveSpoolWeight (which still owns the actual write,
// auto-archive flag, force-unassign chain, and sync-pulse dispatch).
window.saveWeighOutRow = async (idStr) => {
    const id = Number(idStr);
    const inputEl = document.querySelector(`.weigh-input[data-id="${id}"]`);
    if (!inputEl) return;
    const raw = inputEl.value;
    if (raw === '' || raw === '+' || raw === '-') return;
    // Not while a scan read in this window is being answered: its spool's
    // reading may still be on its way to its box (Group 57 review, round 8: a
    // reading and Enter typed before the answer were saved to another spool).
    if (pendingScan) {
        showToast('A scan is still being read: press Enter again in a moment', 'info', 4000);
        return;
    }
    const taken = scansTaken;
    const notAReading = () => showToast(`"${raw}" is not a weight in grams`, 'error', 7000);

    let details = weighOutDetailsCache.get(id);
    if (!details) details = await fetchSpoolDetails(id);
    if (!details) {
        // Fallback: backend treats `newWeight` as remaining_weight.
        const n = window.parseGramsReading(raw);
        if (Number.isNaN(n)) { notAReading(); return; }
        window.saveSpoolWeight(id, n);
        return;
    }

    let r = computeRowResult(id, raw);
    if (r && r.error === 'not_a_reading') { notAReading(); return; }
    if (!r || r.error) {
        showToast('Could not compute used weight', 'error');
        return;
    }
    if (r.requires_empty) {
        // Gross + missing tare. Use the shared inline overlay so the user
        // can fill it in without leaving the bulk flow. Not once a spool scan
        // has been answered since Enter (round 8): that spool is the one being
        // weighed now, and its reading would go in the prompt's box as a tare.
        // A spool scanned while the prompt is up closes it.
        const unsaved = () => showToast(`#${id} wasn't saved: it needs its empty spool weight`, 'warning', 7000);
        if (scansTaken !== taken) { unsaved(); return; }
        const tare = await window.promptMissingEmptyWeight(Object.assign({}, details.context || {},
            { onScanDismiss: unsaved }));
        // Cancelled: back to the target's box (round 7: the focus fell to the page).
        if (tare === null) { window.weighOutRefocus(); return; }
        details.empty = Number(tare);
        weighOutDetailsCache.set(id, details);
        r = computeRowResult(id, raw);
        if (!r || r.error || r.requires_empty) {
            showToast('Could not compute used weight', 'error');
            return;
        }
    }

    // Hand off to saveSpoolWeight with a precomputed used_weight payload.
    // saveSpoolWeight's auto-archive check inspects remaining_weight, but
    // we're submitting used_weight — so compute the auto-archive verdict
    // locally and pass it explicitly via the 4th arg.
    const remainingAfter = Math.max(0, details.initial - r.used_weight);
    const autoToggle = document.getElementById('weigh-auto-archive');
    const autoArchive = !!(autoToggle && autoToggle.checked && remainingAfter <= 0);
    // Forward this row's resolved empty-spool-weight (the just-entered tare when
    // the gross missing-tare prompt fired above, otherwise the spool/filament/
    // vendor cascade value) so the post-archive record prompt is pre-filled.
    window.saveSpoolWeight(id, null, { used_weight: r.used_weight }, autoArchive, details.empty);
};

window.saveSpoolWeight = (idStr, newWeight, updatesObj = null, autoArchiveOpts = null, emptyPrefill = null) => {
    let updates = updatesObj || {};
    if (newWeight !== null && newWeight !== "" && !isNaN(newWeight)) {
        updates.remaining_weight = parseFloat(newWeight);
    }

    if (Object.keys(updates).length === 0) return;

    const id = parseInt(idStr, 10);
    // The spool scans answered in the weigh-out list by the time the save lands:
    // after one, the empty-weight prompt isn't opened (round 8).
    const takenAtSave = scansTaken;

    // Check auto archive for the bulk weigh out modal specifically.
    // When a caller passes autoArchiveOpts explicitly (true/false), it owns
    // the decision — phase-2 used_weight flows pre-compute the verdict and
    // pass it in. When autoArchiveOpts is null, fall back to the modal-level
    // toggle + remaining_weight check (legacy bulk-weigh-out behavior).
    const autoToggle = document.getElementById('weigh-auto-archive');
    let shouldArchive = false;
    if (autoArchiveOpts !== null) {
        shouldArchive = !!autoArchiveOpts;
    } else if (autoToggle && autoToggle.checked && updates.remaining_weight !== undefined && updates.remaining_weight <= 0) {
        shouldArchive = true;
    }

    if (shouldArchive) {
        updates.archived = true;
    }

    setProcessing(true);
    
    // Find the input element to provide visual feedback
    const rowEl = document.querySelector(`.weigh-row[data-id="${id}"]`);
    const inputEl = document.querySelector(`.weigh-input[data-id="${id}"]`);
    const btnEl = document.querySelector(`.weigh-save-btn[data-id="${id}"]`);
    // The next box, found before this one is disabled: focusNextInput looks
    // only at enabled boxes, so it found nothing and the focus fell to the
    // page, where the person's next reading went to the scan path as a spool
    // id (Group 57 review, round 6).
    const nextInputEl = inputEl ? nextWeighInput(inputEl) : null;
    
    if (inputEl) inputEl.disabled = true;
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerText = "⏳";
    }

    fetch(`/api/spool/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: id,
            updates: updates
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.status === 'success') {
            const finalize = () => {
                setProcessing(false);
                showToast(`Updated Spool #${id}`, 'success');
                // Group 42.3c: a used-up spool weighed back above 0 g whose old
                // toolhead holds another spool now went to Unassigned instead.
                if (res && res.warning) showToast(res.warning, 'warning', 7000);
                // Spool just auto-archived (weight hit 0) AND its filament
                // has no empty_spool_weight yet — prompt the user to record
                // the now-empty spool's weight. Fires after the toast so it
                // doesn't stack on top of weigh-out success feedback.
                // `emptyPrefill` carries the tare the user already entered
                // during a Gross weigh so this is a one-click pre-filled
                // confirm rather than a second, redundant ask.
                // Not once a spool has been scanned in the weigh-out list since
                // the save began: that spool is the one being weighed now, and
                // its reading would go in the prompt's box as the filament's
                // empty weight (Group 57 review, round 8). A spool scanned while
                // the prompt is up closes it.
                if (res && res.needs_empty_weight_prompt && res.filament_id && window.showArchiveEmptyWeightPrompt) {
                    setTimeout(() => window.showArchiveEmptyWeightPrompt(id, res.filament_id, emptyPrefill,
                        { skipIf: () => scansTaken !== takenAtSave }), 400);
                }

                // Visual feedback that it's done
                if (rowEl && rescanAfterSave === id) {
                    // Scanned again while it saved: its row stays for the next
                    // reading, its details read afresh (round 8).
                    rescanAfterSave = null;
                    showAgain(id);
                    const again = boxFor(id);
                    if (again && weighOutIsUp() && weighTargetId === String(id)) again.focus();
                } else if (rowEl) {
                    rowEl.style.transition = 'opacity 0.3s';
                    rowEl.style.opacity = '0';
                    fadeTimers.set(id, setTimeout(() => {
                        fadeTimers.delete(id);
                        processedWeighIds.add(id);
                        renderWeighOutList();
                    }, 300));
                } else {
                    processedWeighIds.add(id);
                }
                if (btnEl) btnEl.innerText = "✅";
                
                // Also update the state buffer locally
                const s = state.heldSpools.find(x => x.id == id);
                if(s) {
                    if (updates.remaining_weight !== undefined) s.remaining_weight = parseFloat(updates.remaining_weight);
                    if (updates.archived) s.archived = true;
                    // Trigger instant local UI render so cards don't have to wait for the next heartbeat
                    if (window.renderBuffer) window.renderBuffer();
                }
                // Dispatch sync pulse to update other parts of the dashboard natively
                document.dispatchEvent(new CustomEvent('inventory:sync-pulse', {
                    detail: {
                        updatedSpool: {
                            id: id,
                            updates: updates
                        }
                    }
                }));
            };

            if (updates.archived) {
                fetch('/api/manage_contents', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'force_unassign', spool_id: id, location: '' })
                }).then(() => finalize()).catch(() => finalize());
            } else {
                finalize();
            }
            
        } else {
            setProcessing(false);
            showToast("Failed to update weight", "error");
            if (inputEl) inputEl.disabled = false;
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerText = "💾";
            }
            refocusAfterFailedSave(id, inputEl);
        }
    })
    .catch(e => {
        setProcessing(false);
        console.error("Weigh update failed", e);
        showToast("Error updating weight", "error");
        if (inputEl) inputEl.disabled = false;
        if (btnEl) {
            btnEl.disabled = false;
            btnEl.innerText = "💾";
        }
        refocusAfterFailedSave(id, inputEl);
    });

    // Move to the next input immediately so the user can keep working while it saves
    if (nextInputEl) nextInputEl.focus();
};

// The enabled box after this one, or the first other one after the last.
const nextWeighInput = (currentInput) => {
    const inputs = Array.from(document.querySelectorAll('.weigh-input:not(:disabled)'));
    const currentIndex = inputs.indexOf(currentInput);
    if (currentIndex === -1) return null;
    return inputs[currentIndex + 1] || inputs.find((x) => x !== currentInput) || null;
};
const focusNextInput = (currentInput) => {
    const next = nextWeighInput(currentInput);
    if (next) next.focus();
};

// Expose process scan specific to weigh out to capture commands if we want,
// but the global processScan handles adding items to state.heldSpools, which triggers the buffer-updated listener!

// Quick-Weigh — Phase 2 (Group 12) is backed by <WeightEntry>
// (modules/weight_entry.js). Renders an inline overlay (no nested Bootstrap
// modal stacking, no Swal). On submit, hands off to saveSpoolWeight()
// unchanged so the auto-archive + force-unassign chain and
// inventory:sync-pulse / buffer-updated dispatches continue to flow through
// the same authoritative call path.
window.openQuickWeigh = (spoolId) => {
    setProcessing(true);
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            setProcessing(false);
            if (!d || !d.id) { showToast("Spool Not Found", "error"); return; }

            const initial = Number(d.initial_weight) || Number(d.filament?.weight) || 0;
            const used = Number(d.used_weight) || 0;
            const cascade = {
                spoolWt: d.spool_weight,
                filamentWt: d.filament?.spool_weight,
                vendor: d.filament?.vendor,
            };
            const { value: empty, source: emptySource } = window.resolveEmptySpoolWeightSource(cascade);
            const display = d.filament
                ? [d.filament.vendor?.name, d.filament.material, d.filament.name]
                    .filter(Boolean).join(' - ') || (d.filament.name || 'Unknown')
                : 'Unknown';
            const colorHex = d.filament?.color_hex || d.color_hex || null;

            window.WeightEntry.openModal({
                title: 'Quick Weigh',
                spool: { id: d.id, initial_weight: initial, used_weight: used,
                         display, color_hex: colorHex },
                empty_spool_weight: empty,
                empty_source: emptySource,
                cascade,
                context: {
                    vendor: d.filament?.vendor?.name || '',
                    material: d.filament?.material || '',
                    color: d.filament?.name || '',
                    color_hex: colorHex,
                },
                defaultMode: 'additive',
                availableModes: ['gross', 'net', 'additive', 'set_used'],
                showAutoArchive: true,
                autoArchiveDefault: true,
                onSubmit: (payload) => {
                    const updates = { used_weight: payload.used_weight };
                    // Used == initial means remaining hits zero; auto-archive
                    // gate matches the legacy behavior (auto-archive only when
                    // the toggle is on AND the spool emptied).
                    const autoArchive = !!payload.auto_archive &&
                        Math.max(0, initial - payload.used_weight) <= 0;
                    // Forward the tare WeightEntry collected (Gross-mode missing-
                    // tare prompt) so the post-archive record prompt is pre-filled.
                    window.saveSpoolWeight(d.id, null, updates, autoArchive, payload.empty_spool_weight);
                },
            });
        })
        .catch(e => {
            setProcessing(false);
            console.error(e);
            showToast("Network Error", "error");
        });
};


