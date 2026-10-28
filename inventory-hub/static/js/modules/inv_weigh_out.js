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

// With a timeout (Group 57 review, round 10): a save waits on this read with
// its row disabled, and a read that never answered kept it so.
const fetchSpoolDetails = (id) => {
    const url = `/api/spool_details?id=${id}`;
    return (window.fetchT ? window.fetchT(url, {}, 10000) : fetch(url))
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
    inFlight.clear();
    setPending(null);
    setRescan(null);
    deferredTake = null;
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
    // data-fcc-weight-keys; Group 57 review, rounds 7 and 8). While a scan is
    // being answered, any of them goes where the answer takes the reading
    // from: the box that had the focus as the scan was read, else the
    // target's then (round 9: one typed on another row's 💾 stayed in that
    // row's box, and the scanned spool got the rest of the reading). With no
    // box for it, it is held for the spool it is typed for (keyHolder: an
    // empty list, where it stayed in the scan buffer and the reading was saved
    // cut short; or a spool scanned again while its save is on its way, where
    // it went to the scan path as a spool id, round 9).
    const modalEl = document.getElementById('weighOutModal');
    if (modalEl) {
        modalEl.fccWeightBox = (from) => {
            if (pendingScan) return pendingBox(pendingScan);
            const row = from && from.closest ? from.closest('.weigh-row') : null;
            return row ? row.querySelector('.weigh-input:not(:disabled)') : currentWeighBox();
        };
        modalEl.fccWeightHold = (key) => {
            const h = keyHolder();
            if (!h) return false;
            h.held += key;
            return true;
        };
        // The last `n` held keys, taken back: a scanner sent them (inv_core.js:
        // a scan never becomes a reading), or a Backspace took the last back.
        modalEl.fccWeightUnhold = (n) => {
            const h = keyHolder();
            if (!h || !n || !h.held) return '';
            const keys = h.held.slice(-n);
            h.held = h.held.slice(0, -n);
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
// - What was typed while the scan was answered goes with it (weighOutScanStart
//   as the scan is read: processScan as it sends one, the scan accumulator as
//   it queues one read while another is answered; weighOutTakeScan once the
//   answer names a spool; weighOutScanDone after any answer): a reading started
//   in the box that had the focus, or typed on another control (it went in
//   that box, or the target's), or with no box to go in (an empty list: held
//   for it; a Backspace takes back the last key held). Until the answer, Enter
//   saves nothing, in the list or in a prompt over it (rounds 8 and 9: a
//   reading and Enter typed before the answer were saved to another spool, or
//   as an empty spool weight). Round 9: a scan read while another was answered
//   was queued, and until it went out the earlier answer counted as the
//   latest scan, moved the focus and took the reading.
// - Several scans being answered at once: the latest one read that names a
//   spool takes the focus. An earlier spool scan answered while a later one
//   is out is kept, and takes the focus after all if that one names no spool;
//   what was typed under a scan that named no spool goes to the scan before it
//   that may still take the reading. Enter waits while any of them may (round
//   10: a later scan that named no spool, answered first, freed Enter while
//   the earlier spool scan was still out, and a middle one's keys were said to
//   be gone, cutting the reading the earlier spool took).
// - The missing-tare and empty-weight prompts close when a spool is scanned
//   over them, and neither opens while a scan is being answered, nor once a
//   spool scan has been answered since its Enter (rounds 8 and 9): the scanned
//   spool's reading went in the prompt's box, as an empty spool weight.
// - A save that has to read its spool's details first moves the focus on at
//   once, its row waiting disabled and the page dimmed, as any save does; its
//   missing-tare prompt then opens only while the person hasn't typed or
//   moved since (round 10: it opened over the next row's reading, which
//   became this spool's tare, and a second one replaced the first, whose
//   spool was never saved and never said so). A save moves the focus only from
//   its own row (or from nowhere), and after the last box to the window, so
//   keys go on being held or sent to the target's box (round 9: the focus moved
//   when the details came, from the box a scan had picked, or fell to the page,
//   and the reading went to the scan path as a spool id). A saved row takes no
//   keys while it fades (round 10: the save's own redraw drew it enabled, and a
//   quick key and Enter saved that spool again with the digits joined).
let weighTargetId = null;       // the target's spool id (a string), or null
let pendingScan = null;         // the latest scan being answered that may still take the reading
let scanSeq = 0;                // weighOutScanStart's count: only the latest scan moves the focus
let scansTaken = 0;             // spool scans weighOutTakeScan took ("since" for the prompts)
let rescanAfterSave = null;     // a spool scanned while its own save was on its way
let rescanHold = { held: '' };  // the keys typed for it meanwhile
let deferredTake = null;        // { spoolId, from }: a spool scan answered while a later one is
let lastTakenSeq = 0;           // the latest scan whose spool took the focus
let settleWaiters = [];         // scanSettled's
const inFlight = new Set();     // every scan read in the window and not yet answered
const fadeTimers = new Map();   // a saved row's fade, by spool id
const savingIds = new Set();    // the spools whose save (or its details' read) is on its way
document.addEventListener('focusin', (e) => {
    const t = e.target;
    if (t && t.classList && t.classList.contains('weigh-input')) weighTargetId = t.dataset.id;
});

const setPending = (scan) => {
    pendingScan = scan;
    if (scan) return;
    const waiters = settleWaiters;
    settleWaiters = [];
    waiters.forEach((w) => w());
};
// The latest scan still being answered that may take the reading: none read
// before a spool scan that has taken the focus. While there is one, Enter
// saves nothing (round 10: a later scan that named no spool, answered first,
// let Enter save before the earlier spool scan's answer).
const latestLive = () => {
    let latest = null;
    inFlight.forEach((s) => { if (s.seq > lastTakenSeq && (!latest || s.seq > latest.seq)) latest = s; });
    return latest;
};
const refreshPending = () => setPending(latestLive());
// Resolves once no scan read in the window is being answered.
const scanSettled = async () => {
    while (pendingScan) await new Promise((r) => settleWaiters.push(r));
};
const setRescan = (n) => {
    rescanAfterSave = n;
    rescanHold = { held: '' };
};
// Who keeps a weight key that has no box to go in: the scan being answered,
// or the target scanned again while its own save is on its way.
const keyHolder = () => {
    if (pendingScan) return pendingScan;
    if (rescanAfterSave != null && weighTargetId === String(rescanAfterSave)) return rescanHold;
    return null;
};

const boxFor = (id) => (id == null ? null
    : document.querySelector(`#weigh-out-list .weigh-input[data-id="${id}"]:not(:disabled)`));

// Where a key typed while scan `p` is answered goes (fccWeightBox): the list
// box that had the focus as it was read (or the one drawn in its place), else
// the target's then; takeTyped takes it from there.
const pendingBox = (p) => {
    const el = p.el && p.el.isConnected && !p.el.disabled ? p.el : null;
    return el || boxFor(p.id) || boxFor(p.targetId);
};

// A row whose save (or the read of its details before one) is on its way: its
// box and 💾 disabled, ⏳, and drawn so again by a redraw meanwhile (round 9:
// a heartbeat drew it enabled, and a new reading typed after a scan of it
// vanished with the row when the old save landed).
const markSaving = (id, on) => {
    if (on) savingIds.add(id); else savingIds.delete(id);
    const box = document.querySelector(`.weigh-input[data-id="${id}"]`);
    const btn = document.querySelector(`.weigh-save-btn[data-id="${id}"]`);
    if (box) box.disabled = on;
    if (btn) { btn.disabled = on; btn.innerText = on ? '⏳' : '💾'; }
};

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
// Its save failed: the box is open again, holding the reading that wasn't
// saved; one typed after a scan of it meanwhile (held) takes its place.
const refocusAfterFailedSave = (n) => {
    if (rescanAfterSave !== n) return;
    const held = rescanHold.held;
    setRescan(null);
    const box = boxFor(n);
    if (!box) return;
    if (held) { box.value = held; window.updateWeighRowPreview(box); }
    if (weighOutIsUp() && weighTargetId === String(n)) box.focus();
};

// As a scan is read (processScan as it sends it; the scan accumulator as it
// queues one read while another is answered): where the person's keys were.
// Null when the window isn't open.
window.weighOutScanStart = () => {
    if (!weighOutShown()) return null;
    const ae = document.activeElement;
    const el = ae && ae.classList && ae.classList.contains('fcc-weight-box') ? ae : null;
    const t = currentWeighBox();
    const scan = { seq: ++scanSeq, el, id: el && el.dataset.id != null ? el.dataset.id : null,
        value: el ? el.value : null, targetId: t ? t.dataset.id : null, targetValue: t ? t.value : null, held: '' };
    inFlight.add(scan);
    setPending(scan);
    return scan;
};

// A reading held for scan `s` that no spool took is said to be gone, never
// kept for a later scan.
const dropHeld = (s) => {
    if (!s || !s.held) return;
    const held = s.held;
    s.held = '';
    showToast(`The reading typed while a scan was read ("${held}") wasn't kept: type it again`, 'warning', 7000);
};

// After the scan's answer, whatever it was. Once no later scan is being
// answered, the spool scan kept for the fallback (answered while a later one
// was still out) takes the focus after all, when this one named no spool
// (round 9: a scan queued behind it named no spool). A scan that named no
// spool while a later one is still out hands what was typed under it to the
// kept spool scan, read before it (round 10: it was said to be gone, and
// that spool's reading came out cut).
window.weighOutScanDone = (from) => {
    if (!from) return;
    inFlight.delete(from);
    // (A later spool scan has taken the focus, clearing the kept one, or is
    // itself the one kept: only a scan that named no spool gets here.)
    if (deferredTake && deferredTake.from.seq < from.seq) {
        const later = latestLive();
        if (!(later && later.seq > deferredTake.from.seq)) {
            const d = deferredTake;
            deferredTake = null;
            takeScan(d.spoolId, d.from, from);
        } else {
            deferredTake.from.held += from.held;
            from.held = '';
        }
    }
    refreshPending();
    if (!deferredTake || deferredTake.from !== from) dropHeld(from);
};

// What could be a reading as it is typed: a number and a grams unit, so far. A
// label's first letters, there until its ':' proves it, are not one (round 9:
// they were moved to the scanned spool's box, and the label reached the scan
// path as ":480").
const READING_SO_FAR = /^[\d\s.,+-]*(?:g(?:r(?:a(?:m(?:s)?)?)?)?)?\s*$/i;

// What was typed since the scan was read, taken out of where it went: the
// held keys, and what was added to the end of the box that had the focus or of
// the target's. Never from a box the person moved to meanwhile. `box`: the
// scanned spool's (null while its save is on its way).
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
    const added = ae.value.slice(was.length);
    if (!READING_SO_FAR.test(added)) return typed;
    typed += added;
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
// selected, so the reading typed next replaces it. A scan read later has the
// say: one that took the focus already leaves this one out, and while one is
// still being answered this one is kept in case it names no spool (the latest
// such: weighOutScanDone's fallback).
window.weighOutTakeScan = (spoolId, from) => {
    if (!weighOutShown()) return;
    if (from) {
        if (lastTakenSeq > from.seq) return;
        const later = latestLive();
        if (later && later.seq > from.seq) {
            if (deferredTake && deferredTake.from.seq > from.seq) { dropHeld(from); return; }
            if (deferredTake) dropHeld(deferredTake.from);
            deferredTake = { spoolId, from };
            return;
        }
    }
    if (deferredTake) { dropHeld(deferredTake.from); deferredTake = null; }
    takeScan(spoolId, from, null);
};

// The take itself: `from`, the spool's own scan; `then`, a later one that named
// no spool, whose read held off Enter (what was typed under it goes along).
// Every scan read up to it is out of play from now on (weighOutScanDone, which
// always follows, moves the pending scan on).
const takeScan = (spoolId, from, then) => {
    const froms = [from, then].filter(Boolean);
    lastTakenSeq = Math.max(lastTakenSeq, ...froms.map((f) => f.seq));
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
    if (!box && document.querySelector(`#weigh-out-list .weigh-row[data-id="${id}"]`) && rescanAfterSave !== n) setRescan(n);
    const modalEl = document.getElementById('weighOutModal');
    const prompt = topWeighPrompt();
    const ae = document.activeElement;
    // Another window over this one keeps the focus: the target's box gets it
    // when that window closes.
    if (!prompt && (!weighOutIsUp() || (ae && ae !== document.body && !modalEl.contains(ae)))) return;
    if (!box) {
        // Its save still on its way: what was typed for it is held until its
        // box opens, and meanwhile no other spool's box keeps the focus (round
        // 9: the keys stayed in another spool's box, and the empty-weight
        // prompt's close gave its own box the focus, and that spool the
        // target, so the reading was saved to it).
        if (rescanAfterSave === n) {
            rescanHold.held += froms.map((f) => takeTyped(f, null)).join('');
            if (prompt) prompt.fccDismissForScan();
            weighTargetId = id;
            modalEl.focus();
        }
        return;
    }
    const typed = froms.map((f) => takeTyped(f, box)).join('');
    if (prompt) prompt.fccDismissForScan();
    // Typed into its own box meanwhile (it had the focus, or was the target):
    // that is the reading, never selected for the next key to replace, and in
    // place of what the box held as the scan was read (round 9: '300' left
    // there and '425' typed before the answer saved 300425).
    const was = !from ? null : (from.id === id ? from.value : (from.targetId === id ? from.targetValue : null));
    const changed = was != null && box.value !== was;
    box.focus();
    if (typed) {
        box.value = typed;
        window.updateWeighRowPreview(box);
    } else if (changed) {
        if (was && box.value.startsWith(was) && READING_SO_FAR.test(box.value.slice(was.length))) {
            box.value = box.value.slice(was.length);
            window.updateWeighRowPreview(box);
        }
    } else {
        try { box.select(); } catch (_) { /* nothing to select */ }
    }
};

// Another window closed over this one: the focus back in the target's box.
// The weigh-out window itself closed: nothing is pending.
document.addEventListener('hidden.bs.modal', (e) => {
    if (e.target && e.target.id === 'weighOutModal') { inFlight.clear(); setPending(null); setRescan(null); deferredTake = null; return; }
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
        // A row whose save is on its way, or that has saved and is fading out,
        // takes no keys (round 10: the save's own redraw drew the fading row
        // enabled, a key typed on the window went into it as the target's, and
        // Enter saved that spool again with the digits joined).
        const busy = savingIds.has(spool.id) ? '⏳' : (fadeTimers.has(spool.id) ? '✅' : '');
        const saving = busy ? ' disabled' : '';

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
                        onkeydown="window.handleWeighInput(event, this)"${saving}>
                    <span class="input-group-text bg-secondary text-light border-secondary">g</span>
                </div>
                <button class="btn btn-outline-success btn-sm weigh-save-btn" data-id="${spool.id}" onclick="window.saveWeighOutRow(${spool.id})"${saving}>
                    ${busy || '💾'}
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
        } else if (!pendingScan) {
            // Just skip to next if empty. Not while a scan is answered: a
            // scanner's second Enter (a CR LF ending) moved the focus on, and
            // the reading typed before the answer stayed in the next spool's
            // box (Group 57 review, round 9).
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
    let movedTo = null;      // where the focus went on while its details were read, and what was there
    if (!details) {
        // Its details still to read (a slow Spoolman, a spool just scanned
        // in): its row waits, disabled, and the focus moves on now, as a
        // save's does (Group 57 review, round 9: it moved once they came, from
        // the box a scan had picked meanwhile, and the rest of that spool's
        // reading was saved to the next spool). The page is dimmed meanwhile,
        // as for a save (round 10: a click on the waiting row, to put its
        // reading right, moved no focus, and the correction was saved to the
        // next spool).
        const moveOn = focusOnFrom(inputEl);
        markSaving(id, true);
        moveOn();
        const ae = document.activeElement;
        movedTo = { el: ae, id: ae && ae.dataset ? ae.dataset.id : undefined, value: ae ? ae.value : undefined };
        setProcessing(true);
        try { details = await fetchSpoolDetails(id); } finally { setProcessing(false); }
        markSaving(id, false);
    }
    let handed = false;
    try {
        if (!details) {
            // Fallback: the backend treats `newWeight` as remaining_weight,
            // which a Net reading is. Any other mode's reading needs the
            // spool's details (round 9: Additive '+25' was saved as 25 g left,
            // Set Used '0' as an empty spool, which was archived).
            if ((window.weighOutMode || 'net') !== 'net') {
                showToast(`Couldn't read #${id}'s details, so its reading wasn't saved: press Enter in its box to try again`, 'warning', 7000);
                return;
            }
            const n = window.parseGramsReading(raw);
            if (Number.isNaN(n)) { notAReading(); return; }
            handed = true;
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
            // can fill it in without leaving the bulk flow. Not while a scan is
            // being answered, nor once a spool scan has been answered since
            // Enter (rounds 8 and 9): that spool is the one being weighed now,
            // and its reading would go in the prompt's box as a tare. A spool
            // scanned while the prompt is up closes it, and its Save waits
            // while one is being answered.
            const unsaved = () => showToast(`#${id} wasn't saved: it needs its empty spool weight`, 'warning', 7000);
            await scanSettled();
            if (scansTaken !== taken) { unsaved(); return; }
            // The focus moved on while its details were read, and the person
            // has gone on typing there, or moved: the prompt would take that
            // reading as this spool's tare, and a second such save's prompt
            // would replace this one, never to be answered (round 10). The row
            // waits for its Enter again instead.
            // (Still there: the same box, or the same spool's box drawn again.)
            const now = document.activeElement;
            const there = !!movedTo && (now === movedTo.el || (!!now && movedTo.id != null && !!now.classList
                && now.classList.contains('weigh-input') && now.dataset.id === movedTo.id));
            if (movedTo && (!there || (now && now.value !== movedTo.value))) {
                showToast(`#${id} wasn't saved: it needs its empty spool weight. Press Enter in its box again to give it`, 'warning', 7000);
                return;
            }
            const tare = await window.promptMissingEmptyWeight(Object.assign({}, details.context || {},
                { onScanDismiss: unsaved, scanPending: () => !!pendingScan }));
            // Cancelled: back to the target's box (round 7: the focus fell to
            // the page), where the person is: this spool's, unless the save
            // moved them on (round 10: it went back to this one, and the next
            // reading typed joined this spool's).
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
        handed = true;
        window.saveSpoolWeight(id, null, { used_weight: r.used_weight }, autoArchive, details.empty);
    } finally {
        // Not saved after all, and scanned again while its details were read:
        // its box is open for the new reading, with what was typed for it.
        if (!handed && rescanAfterSave === id) refocusAfterFailedSave(id);
    }
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

    // Its row shows the save on its way (markSaving). The focus moves on from
    // its box, worked out before the box is disabled: focusNextInput looks
    // only at enabled boxes, so it found nothing and the focus fell to the
    // page, where the person's next reading went to the scan path as a spool
    // id (Group 57 review, round 6).
    const inputEl = document.querySelector(`.weigh-input[data-id="${id}"]`);
    const moveOn = focusOnFrom(inputEl);
    markSaving(id, true);

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
                // Saved: a redraw from now on draws its row as any other (its
                // fade, or a scan of it, decides what comes next).
                savingIds.delete(id);
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
                // the save began, and not while a scan is being answered: that
                // spool is the one being weighed now, and its reading would go
                // in the prompt's box as the filament's empty weight (Group 57
                // review, rounds 8 and 9). A spool scanned while the prompt is up
                // closes it, and its Save waits while one is being answered.
                if (res && res.needs_empty_weight_prompt && res.filament_id && window.showArchiveEmptyWeightPrompt) {
                    setTimeout(() => window.showArchiveEmptyWeightPrompt(id, res.filament_id, emptyPrefill,
                        { settle: scanSettled, skipIf: () => scansTaken !== takenAtSave,
                          scanPending: () => !!pendingScan }), 400);
                }

                // Visual feedback that it's done, on its row as it is now (a
                // redraw may have drawn it again since the save went out).
                const rowEl = document.querySelector(`.weigh-row[data-id="${id}"]`);
                if (rowEl && rescanAfterSave === id) {
                    // Scanned again while it saved: its row stays for the next
                    // reading, its details read afresh (round 8), with what was
                    // typed for it meanwhile (round 9).
                    const held = rescanHold.held;
                    setRescan(null);
                    showAgain(id);
                    const again = boxFor(id);
                    if (again && held) { again.value = held; window.updateWeighRowPreview(again); }
                    if (again && weighOutIsUp() && weighTargetId === String(id)) again.focus();
                } else if (rowEl) {
                    rowEl.style.transition = 'opacity 0.3s';
                    rowEl.style.opacity = '0';
                    const btnEl = rowEl.querySelector('.weigh-save-btn');
                    if (btnEl) btnEl.innerText = "✅";
                    fadeTimers.set(id, setTimeout(() => {
                        fadeTimers.delete(id);
                        processedWeighIds.add(id);
                        renderWeighOutList();
                    }, 300));
                } else {
                    processedWeighIds.add(id);
                }

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
            markSaving(id, false);
            refocusAfterFailedSave(id);
        }
    })
    .catch(e => {
        setProcessing(false);
        console.error("Weigh update failed", e);
        showToast("Error updating weight", "error");
        markSaving(id, false);
        refocusAfterFailedSave(id);
    });

    // Move to the next input immediately so the user can keep working while it saves
    moveOn();
};

// The focus on from box `inputEl` as it is saved, worked out before the box is
// disabled: to the next box, or with none to the window, where keys go on
// being held for a scan or going in the target's box (Group 57 review, round
// 9: the focus fell to the page, and a reading typed before the next scan's
// answer went to the scan path as a spool id). Only from its row (its box, its
// 💾) or from nowhere (the window holding no keys for a scan): never from a
// box a scan or the person picked meanwhile (round 9: a save that read its
// details first took it from the box a scan had given it). Returns the move,
// to call once the box is disabled.
const focusOnFrom = (inputEl) => {
    const modalEl = document.getElementById('weighOutModal');
    const row = inputEl && inputEl.closest ? inputEl.closest('.weigh-row') : null;
    const ae = document.activeElement;
    const nowhere = !ae || ae === document.body || (ae === modalEl && !keyHolder());
    const here = !!inputEl && (nowhere || !!(row && row.contains(ae)));
    const next = here ? nextWeighInput(inputEl) : null;
    return () => {
        if (!here) return;
        if (next && next.isConnected && !next.disabled) next.focus();
        else if (modalEl && weighOutShown()) modalEl.focus();
    };
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


