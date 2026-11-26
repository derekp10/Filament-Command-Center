/* MODULE: WIZARD (Add Inventory) */
console.log("🚀 Loaded Module: WIZARD");

let wizardState = {
    mode: 'manual', // 'existing', 'external', 'manual'
    vendors: [],
    selectedFilamentId: null,
    externalMetaData: null,
    editSpoolId: null,
    returnToSpoolId: null, // Track which spool detail modal to re-open after wizard closes
    returnToFilamentId: null, // Track which filament detail modal to re-open after wizard closes
    isDirty: false,    // true when the user has modified any form field or chip
    forceClose: false, // set true to bypass the dirty guard when we want to programmatically close
    // Group 40.7 — where Save places the spool when a picker chose it (the
    // Location combobox's box / printer pickers fill it); null when the user
    // typed a plain location, which is then sent as a plain move (the engine
    // picks a free slot of a box itself). Shape:
    //   { location: 'LR-MDB-1',  // the LocationID the pick belongs to: used only
    //                            // while it is still the Location field's value
    //     slot: null,            // an explicit slot: the picker's Swap / Overwrite
    //     picked_slot: '2',      // a free slot the picker chose (kept only while free)
    //     expected_feed: 'XL-2', // what that slot fed when chosen ('' = no toolhead)
    //     auto_deploy: true }    // false: "stored here, not loaded back"
    // window.wizardPlacementFor / wizardCreatePlacements turn it into the request.
    // Dropped as soon as the Location field's value stops matching it
    // (window.wizardWatchLocationPick), and used up by a create.
    pendingPlacement: null,
    // Group 40.7 review: where the edited spool is filed now, as this page knows
    // it (the edit's pre-fill, then each move that landed); null when not editing.
    // Save opens the picker for a box or printer only when the Location differs.
    editSpoolLocation: null,
    // Group 40.7: every /api/locations row, toolheads and printers included (the
    // Location list hides those), for Clone's "starts blank on a head" rule.
    allLocationRows: [],
    // The dynamic extras the user changed in this session ("fil:<key>",
    // "spool:<key>"): edit mode sends a blank one as cleared only when it is
    // here, so a field drawn blank by the page itself never clears the record
    // (2026-10-21 review: a clear now really clears on Spoolman 0.27), and the
    // filament's label status box is sent only when it is here (Group 58.5).
    touchedExtras: new Set(),
    // The plain number boxes the user changed in this session ("spool:price",
    // "fil:settings_bed_temp", … WIZ_NATIVE_CLEARABLE has all five), read per key
    // through wizardNativeTouched: edit mode sends one left empty as null, which
    // clears the field, and only then (Group 54.5).
    touchedNative: new Set(),
    // Group 54.8: 'filament' while the price box shows the filament's price, the
    // spool having none of its own (wizardPrefillSpoolPrice); null for the spool's
    // own price or none. Typed over, the price is the spool's own
    // (wizardSpoolPriceIsFilaments), and Save sends a price only then.
    spoolPriceFrom: null,
    // Group 54.8: 'filament' / 'vendor' while the spool's empty-weight box shows an
    // inherited value (wizardSetSpoolEmptyWeightInherited); null for its own or
    // none. Edit Spool doesn't save an inherited one untouched
    // (wizardSpoolEmptyWeightIsInherited).
    spoolEmptyWeightFrom: null,
    // Group 54 review (R2-1, R2-3): true once New Spool or Clone has filled the
    // spool's price and empty weight from its filament; those boxes then follow a
    // filament picked afterwards (wizardFollowFilament). Reset by wizardReset.
    spoolBoxesFollowFilament: false,
    // The filaments wizardSearchExisting listed last (/api/filaments' records), so a
    // pick from that list knows the picked filament's price and empty weight.
    existingFilaments: [],
};

// Empty-spool-weight inheritance helper (resolveEmptySpoolWeight) lives in
// modules/weight_utils.js — loaded before this module in scripts.html and
// exposed as window.resolveEmptySpoolWeight so the bare calls below resolve
// against the global. See weight_utils.js for the cascade rules.

// --- INHERITANCE BADGE FOR wiz-spool-empty_weight FIELD ---
// Phase 2 (Group 12): the input is now bound to <EmptyWeightField>
// (modules/empty_weight_field.js) so it shares the auto-clear-on-input
// behavior with Edit-Filament Specs and the post-archive prompt. The wizard
// keeps its imperative `wizardSetSpoolEmptyWeightInherited` API — that's
// what the three wizard open flows already call after running their own
// cascade resolution, and it stays the simplest direct-DOM path. The shared
// component only owns the listener that hides the badge as soon as the user
// types over the inherited value.
(function () {
    const inputEl = document.getElementById('wiz-spool-empty_weight');
    if (!inputEl || typeof window.bindEmptyWeightField !== 'function') return;
    window.bindEmptyWeightField({
        input: inputEl,
        badge: document.getElementById('wiz-spool-empty-inherited-badge'),
        sourceLabel: document.getElementById('wiz-spool-empty-inherited-source'),
        // No copyVendorBtn in the wizard — the wizard auto-prefills via the
        // cascade so the affordance is redundant. The Specs tab in the
        // edit-filament modal IS the surface that uses copyVendorBtn.
    });
})();

window.wizardSetSpoolEmptyWeightInherited = (value, source, vendor = null) => {
    const inputEl = document.getElementById('wiz-spool-empty_weight');
    const badge = document.getElementById('wiz-spool-empty-inherited-badge');
    const sourceEl = document.getElementById('wiz-spool-empty-inherited-source');
    if (!inputEl) return;
    inputEl.value = (value !== null && value !== undefined) ? value : '';
    // Group 54.8: where the value came from, for Edit Spool's Save.
    const inherited = (source === 'filament' || source === 'vendor') && inputEl.value !== '';
    wizardState.spoolEmptyWeightFrom = inherited ? source : null;
    // Group 66.1: whose weight a "↩ from vendor" box shows, so a save of that
    // manufacturer while the wizard is open reaches it (window.wizardVendorSaved).
    wizardState.spoolEmptyWeightVendorId = (inherited && source === 'vendor' && vendor && vendor.id != null)
        ? String(vendor.id) : null;
    if (badge && sourceEl && (source === 'filament' || source === 'vendor')) {
        sourceEl.textContent = source;
        badge.style.display = '';
    } else if (badge) {
        badge.style.display = 'none';
    }
    if (window.wizardRecheckScale) window.wizardRecheckScale();
};

// The box holds a value of the spool's own from here on (or nothing): the badge
// goes, and so does the mark Edit Spool's Save reads (Group 54.8).
window.wizardClearSpoolEmptyWeightBadge = () => {
    const badge = document.getElementById('wiz-spool-empty-inherited-badge');
    if (badge) badge.style.display = 'none';
    wizardState.spoolEmptyWeightFrom = null;
    wizardState.spoolEmptyWeightVendorId = null;
};

// --- THE FILAMENT'S SPOOL WT: ITS OWN, OR ITS BRAND'S (Group 66.7) ---
// The filament's Spool Wt box (#wiz-fil-empty_weight) shows its brand's empty weight
// when the filament has none of its own (Edit Spool's open, a manufacturer saved while
// the wizard is open). It looked like the filament's own, and every Edit Spool Save
// wrote it as such, whatever was edited, so the filament stopped following its brand.
// wizardState.filEmptyWeightFrom is 'vendor' while the box shows the brand's (set in
// wizardReset, kept out of the state's literal, whose lines the load-order canary
// pins); typed over or emptied, the box is the filament's own (Group 54.5's touched
// set). Edit Spool's Save leaves an inherited one out; a create still saves what the
// box shows as the new filament's (the cross-check's C15: today's outcome). A function
// declaration reading the touched set itself: a summary may ask before the module's
// later consts exist.
// Review round 2 of Group 66 (Q2-02, Q2-03): 'vendor' also while the brand gives nothing
// (the box empty, with no badge), so the box goes on following the brand. It used to lose
// the mark there: a key typed in the Vendor box that matched no manufacturer emptied it for
// good, and the brand the person then picked never filled it (Save's cross-inherit wrote
// that brand's weight as the filament's own). Edit Spool's open marks a filament with none
// of its own so, whatever its brand gives.
function wizardFilEmptyWeightIsInherited() {
    return wizardState.filEmptyWeightFrom === 'vendor'
        && !(wizardState.touchedNative && wizardState.touchedNative.has('fil:spool_weight'));
}

// Shows or hides the box's "↩ from vendor" badge (Derek's D2 (a), the spool box's look):
// only while it shows the brand's weight. Its words say what Save does with it (review
// round 2 of Group 66, Q2-04): a create saves it as the new filament's own (C15), which the
// words used to deny.
const WIZ_FIL_BADGE_EDIT = "The manufacturer's empty weight: this filament has none of its own. Type a weight to give the filament its own.";
const WIZ_FIL_BADGE_CREATE = "The manufacturer's empty weight: Create saves it as the new filament's own. Type a weight to give it another.";
window.wizardRefreshFilEmptyWeightMark = () => {
    const badge = document.getElementById('wiz-fil-empty-inherited-badge');
    if (!badge) return;
    const box = document.getElementById('wiz-fil-empty_weight');
    const shows = !!(box && String(box.value || '') !== '');
    badge.style.display = wizardFilEmptyWeightIsInherited() && shows ? '' : 'none';
    badge.title = wizardState.mode === 'edit_spool' ? WIZ_FIL_BADGE_EDIT : WIZ_FIL_BADGE_CREATE;
};

// Puts `value` in the box: the brand's when `source` is 'vendor' (marked while it shows a
// value; still the brand's, unmarked, while the brand gives nothing), else the filament's
// own. Code, not the person: no event, so no touch.
window.wizardSetFilEmptyWeightInherited = (value, source) => {
    const box = document.getElementById('wiz-fil-empty_weight');
    if (!box) return;
    box.value = (value !== null && value !== undefined) ? String(value) : '';
    wizardState.filEmptyWeightFrom = source === 'vendor' ? 'vendor' : null;
    window.wizardRefreshFilEmptyWeightMark();
    if (window.wizardRecheckScale) window.wizardRecheckScale();
};

// --- WIZARD CLOSE → RE-OPEN DETAIL MODAL ---
// Register immediately — this script loads after the DOM is fully parsed.
(function() {
    const wizEl = document.getElementById('wizardModal');
    if (wizEl) {
        wizEl.addEventListener('hidden.bs.modal', () => {
            // Filament takes priority (it's the parent context when editing spools from filament view)
            if (wizardState.returnToFilamentId) {
                const fid = wizardState.returnToFilamentId;
                wizardState.returnToFilamentId = null;
                wizardState.returnToSpoolId = null; // Clear spool too
                setTimeout(() => {
                    if (typeof openFilamentDetails === 'function') openFilamentDetails(fid);
                }, 200);
            } else if (wizardState.returnToSpoolId) {
                const sid = wizardState.returnToSpoolId;
                wizardState.returnToSpoolId = null;
                setTimeout(() => {
                    if (typeof openSpoolDetails === 'function') openSpoolDetails(sid);
                }, 200);
            }
        });
        console.log("✅ Wizard close → re-open detail modal listener registered.");

        // --- UNSAVED CHANGES GUARD ---
        // hide.bs.modal fires before the modal closes and supports preventDefault().
        // Group 66.2: the question is wizardAskDiscard's (one for this close and for
        // anything that would start the wizard over), and the bypass flag is set and
        // cleared around the synchronous hide(): a hide Bootstrap drops while the window
        // fades never leaves it set for the person's next close (the grounding's C18).
        wizEl.addEventListener('hide.bs.modal', (event) => {
            if (wizardState.forceClose) return;
            if (!wizardState.isDirty) return;
            event.preventDefault();
            window.wizardAskDiscard({
                title: '⚠️ Unsaved Changes',
                body: 'You have unsaved changes. Discard them and close?',
                discardLabel: 'Discard & Close',
            }).then((discard) => {
                if (!discard) return;
                wizardState.isDirty = false;
                wizardState.forceClose = true;
                try { window.modals.wizardModal.hide(); } finally { wizardState.forceClose = false; }
            });
        });

        // Track dirty state from any form input/change inside the wizard (delegated).
        // Also lift the post-success submit lock here: once the user edits anything
        // after a successful create, the wizard is fair game again. Without this,
        // a second click on Create would silently rebuild the same spools.
        const _onDirty = () => {
            wizardState.isDirty = true;
            if (wizardState.lockedAfterSuccess) {
                wizardState.lockedAfterSuccess = false;
                const submitBtn = document.getElementById('btn-wiz-submit');
                if (submitBtn) submitBtn.disabled = false;
                const msg = document.getElementById('wiz-status-msg');
                if (msg) msg.innerHTML = '';
            }
        };
        // For code that puts a person's result in the form (review round 1 of Group 66,
        // R3-05): a value set by code fires no event, so nothing counted it.
        window.wizardMarkChanged = _onDirty;
        // A dialog drawn inside the wizard (Force Location's list, from the refill
        // question's Pick a place…: Group 63 review, round 2) is no edit of the form:
        // typing its search marked the wizard changed, and closing it asked.
        const _inDialog = (e) => !!(e && e.target && e.target.closest && e.target.closest('.swal2-container'));
        // Group 66.2 (the grounding's 66.4 step 9): a text box that kept the focus
        // through wizardReset fires its `change` at blur, in the NEW session, and that
        // marked a fresh wizard changed (66.2's guard then asked over nothing). A typed
        // box always fires `input` first, so a text box's `change` counts only when the
        // box had an `input` since the last reset (wizardState.typedSinceReset). Hidden
        // ids (a combobox pick), selects and checkboxes count as before.
        const _textLike = (t) => !!t && ((t.tagName === 'INPUT' && t.type !== 'hidden'
            && t.type !== 'checkbox' && t.type !== 'radio') || t.tagName === 'TEXTAREA');
        wizEl.addEventListener('input', (e) => {
            if (_inDialog(e)) return;
            if (_textLike(e.target)) {
                if (!wizardState.typedSinceReset) wizardState.typedSinceReset = new WeakSet();
                wizardState.typedSinceReset.add(e.target);
            }
            _onDirty();
        });
        wizEl.addEventListener('change', (e) => {
            if (_inDialog(e)) return;
            if (_textLike(e.target) && !(wizardState.typedSinceReset && wizardState.typedSinceReset.has(e.target))) return;
            _onDirty();
        });
        // Which extras the user changed (window.wizardNoteExtraTouched). A chip's
        // own onclick removes it, so its click is read in the capture phase,
        // while the chip still sits in its box. `input` only (Group 66.4, as 54.5's
        // plain boxes): a person's pick in a select and a checkbox's tick fire it
        // before their `change`, while a text box that kept the focus through a reset
        // fires a `change` at blur for an edit made in the last session (a blank extra
        // then went out as a clear). The single-choice ➕ notes its own touch
        // (wizardOnNewChoiceAdded).
        wizEl.addEventListener('input', (e) => { if (!_inDialog(e)) window.wizardNoteExtraTouched(e.target); });
        // Which plain boxes the user changed (window.wizardNoteNativeTouched,
        // Group 54.5): `input` only. A number box fires `input` for every change a
        // person makes (a key, a paste, the spinner, the wheel); its `change` comes
        // at blur, and Chromium still fires it for an edit made before the wizard
        // was reset for the next spool when the box kept the focus (the open moves
        // the focus after the reset), which read as a touch of the new spool's box.
        wizEl.addEventListener('input', (e) => { if (!_inDialog(e)) window.wizardNoteNativeTouched(e.target); });
        // Group 54.8: a price typed over the filament's is the spool's own, so its
        // "↩ from filament" goes (after the line above has noted the touch).
        wizEl.addEventListener('input', (e) => {
            if (e.target && e.target.id === 'wiz-spool-price') window.wizardRefreshSpoolPriceMark();
        });
        wizEl.addEventListener('click', (e) => {
            const chip = e.target && e.target.closest ? e.target.closest('.dynamic-chip') : null;
            if (chip) window.wizardNoteExtraTouched(chip);
        }, true);

        // Chip removal uses onclick="this.remove()" which bypasses input/change events.
        wizEl.addEventListener('click', (e) => {
            if (e.target.classList.contains('dynamic-chip')) wizardState.isDirty = true;
        });
    }
})();

// --- A KEY A NUMBER BOX CAN'T TAKE IS NO EDIT (Group 54 review, R2-2) ---
// With a number box's value selected (the focus came by Tab), Chromium deletes the
// selection for a key the box rejects (a letter, ':') and fires one `input` that
// inserted nothing: insertText, the box now '' with no badInput. A scanner's label
// typed there (LOC:XL, CMD:UNDO: none of 0-9 e E + - . in it) emptied the box, and
// that counted as the person's: 54.5's touched set made it a clear at Edit Spool's
// Save, the price's and empty weight's "↩ from …" marks went, and an emptied Total
// Used went out as 0. Every number box in the wizard now gets back the value it had
// just before, still selected, and the event goes no further (this listener is the
// first to hear it): nothing counts it as touched, takes a mark off, copies it or
// marks the wizard changed. A person's Delete or Backspace, and a key the box takes,
// are edits as before. The scan itself still goes nowhere: the scan accumulator
// leaves a box's keys to the box, and this routes them nowhere new.
(function () {
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl) return;
    const isNumberBox = (t) => !!t && t.tagName === 'INPUT' && t.type === 'number';
    const valueBeforeKey = new WeakMap();   // box → its value when a key was typed in it
    wizEl.addEventListener('beforeinput', (e) => {
        if (!isNumberBox(e.target)) return;
        if (e.inputType === 'insertText' && e.data) valueBeforeKey.set(e.target, e.target.value);
        else valueBeforeKey.delete(e.target);
    }, true);
    wizEl.addEventListener('input', (e) => {
        const box = e.target;
        if (!isNumberBox(box)) return;
        const before = valueBeforeKey.get(box);
        valueBeforeKey.delete(box);
        if (before === undefined || before === '' || e.inputType !== 'insertText') return;
        if (box.value !== '' || (box.validity && box.validity.badInput)) return;
        box.value = before;
        try { box.select(); } catch (_) { /* a box that can't select keeps its caret */ }
        // The key journal's input phase for this key ends here: nothing after this hears
        // the event (review round 3 of Group 66, R3-01).
        if (window.wizardKeyInputStopped) window.wizardKeyInputStopped();
        e.stopImmediatePropagation();
    }, true);
})();

// --- A LABEL SCANNED ON ONE OF THE WIZARD'S DROPDOWNS (review round 3 of Group 66, R3-02) ---
// A dropdown's keys go to the scan accumulator (scripts.html reads them; the field capture
// takes boxes only), and the browser's type-ahead moved the dropdown by the label's first
// letters: on Existing Filament's list "ID:57" picked the first filament starting with I, its
// change made that the filament Save uses, and Create made the new spool under it. The
// location editor's dropdowns have had the rule since Group 61 (_installLocEditorEnterToSave,
// inv_loc_mgr.js): the keys typed on the dropdown that has the keyboard are judged at the
// Enter; a burst, a ':' or '/', or a search that starts none of its options is a scan; the
// dropdown goes back to what it held before the scan's first key (a person's jump just
// before it stays), its change runs again for that pick, and a toast says so; the scan goes
// on without that jump glued in front. Here the changed flag, the post-create lock (Save and
// its status line) and the touched sets go back too: a scan is no edit. Older than Group 66.
(function () {
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl) return;
    const BURST_MS = 150, TYPEAHEAD_MS = 1000, RESET_MS = 2000;
    const PERSON_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Tab', 'Home', 'End',
        'PageUp', 'PageDown', 'Backspace', 'Delete', 'Escape'];
    const isWizSelect = (el) => !!el && el.tagName === 'SELECT' && !!el.closest
        && !!el.closest('#wizardModal') && !el.closest('.swal2-container');
    const payload = (txt) => !!(txt && window.looksLikeScanPayload && window.looksLikeScanPayload(txt));
    // Do these keys jump to one of the dropdown's options (the start of its text, or one
    // letter again and again), as the browser's type-ahead reads them?
    const jumps = (sel, typed) => {
        const t = String(typed || '').trim().toLowerCase();
        if (!t) return false;
        const texts = Array.from(sel.options || []).map((o) => String(o.textContent || '').trim().toLowerCase());
        if (texts.some((x) => x.startsWith(t))) return true;
        return /^(.)\1+$/.test(t) && texts.some((x) => x.startsWith(t[0]));
    };
    let run = null;   // { el, keys: [{ k, t, was }] }: the keys typed on the dropdown with the keyboard
    const keysOn = (el, now) => (run && run.el === el && run.keys.length
        && now - run.keys[run.keys.length - 1].t <= RESET_MS) ? run.keys : [];
    const textOf = (keys) => keys.map((x) => x.k).join('');
    const burstAt = (keys, now) => {
        let i = keys.length - 1;
        while (i > 0 && keys[i].t - keys[i - 1].t < BURST_MS) i--;
        return keys.length - i >= 3 && now - keys[i].t < BURST_MS;
    };
    // The search the type-ahead holds after keys[end - 1]: the keys since its 1 s reset.
    const searchOf = (keys, end) => {
        let i = end - 1;
        while (i > 0 && keys[i].t - keys[i - 1].t <= TYPEAHEAD_MS) i--;
        return textOf(keys.slice(Math.max(0, i), end));
    };
    // Where the scan starts: after a pause (longer than its own keys, twice over, and than
    // a burst) that ends a person's jump to an option, else at the first key.
    const scanFrom = (sel, keys) => {
        for (let k = keys.length - 1; k > 0; k--) {
            let pace = 0;
            for (let j = k + 1; j < keys.length; j++) pace = Math.max(pace, keys[j].t - keys[j - 1].t);
            if (keys[k].t - keys[k - 1].t <= Math.max(BURST_MS, 2 * pace)) continue;
            const theirs = searchOf(keys, k);
            if (!payload(theirs) && jumps(sel, theirs)) return k;
        }
        return 0;
    };
    // What a key found, to put back if it turns out to be a scan's.
    const formNow = (sel) => {
        const msg = document.getElementById('wiz-status-msg');
        const btn = document.getElementById('btn-wiz-submit');
        return { value: sel.value, dirty: wizardState.isDirty, locked: wizardState.lockedAfterSuccess,
            touchedExtras: new Set(wizardState.touchedExtras || []),
            touchedNative: new Set(wizardState.touchedNative || []),
            status: msg ? msg.innerHTML : null, saveOff: btn ? btn.disabled : null };
    };
    wizEl.addEventListener('keydown', (e) => {
        if (e.isComposing || !isWizSelect(e.target)) return;
        const sel = e.target;
        const now = Date.now();
        if (e.ctrlKey || e.altKey || e.metaKey || (e.key !== 'Enter' && (e.repeat || PERSON_KEYS.includes(e.key)))) {
            run = null;
            return;
        }
        if (e.key.length === 1) {
            const keys = keysOn(sel, now);
            if (!keys.length) run = { el: sel, keys: [] };
            run.keys.push({ k: e.key, t: now, was: formNow(sel) });
            return;
        }
        if (e.key !== 'Enter') return;
        const keys = keysOn(sel, now);
        run = null;
        if (!keys.length) return;
        const scan = burstAt(keys, now) || payload(textOf(keys)) || !jumps(sel, searchOf(keys, keys.length));
        if (!scan) return;
        const from = scanFrom(sel, keys);
        const was = keys[from].was;
        if (sel.value !== was.value) {
            sel.value = was.value;
            sel.dispatchEvent(new Event('change', { bubbles: true }));   // its pick's handler again
            const opt = sel.options[sel.selectedIndex];
            if (window.showToast) window.showToast(
                `The list is back to "${opt ? opt.textContent.trim() : was.value}": the scan's letters had changed it`, 'info', 4000);
        }
        wizardState.isDirty = was.dirty;
        wizardState.touchedExtras = was.touchedExtras;
        wizardState.touchedNative = was.touchedNative;
        if (was.locked && !wizardState.lockedAfterSuccess) {
            wizardState.lockedAfterSuccess = true;
            const btn = document.getElementById('btn-wiz-submit');
            if (btn && was.saveOff !== null) btn.disabled = was.saveOff;
            const msg = document.getElementById('wiz-status-msg');
            if (msg && was.status !== null) msg.innerHTML = was.status;
        }
        // The scan the accumulator sends at this Enter is this dropdown's own keys from the
        // scan's first: a person's jump just before it is no part of it.
        const st = (typeof state !== 'undefined') ? state : window.state;
        const own = textOf(keys.slice(from));
        if (st && typeof st.scanBuffer === 'string' && st.scanBuffer !== own && st.scanBuffer.endsWith(own)) {
            st.scanBuffer = own;
            st.scanStartTime = keys[from].t;
        }
    });   // the modal's bubble phase: before the accumulator, on the document, hears the Enter
})();

// --- "UNSAVED CHANGES" (Group 66.2): one question for every way the wizard's edits
// would be lost: its close, and anything that would start it over (a new Prusament
// spool's QR, the legacy picker's Add new spool, an Edit / Clone / New Spool opened over
// it). Resolves true for Discard, false otherwise (Keep Editing, Escape, its host closing,
// a newer question on the same id). A mountOverlay hosted by the wizard, opening on Keep
// Editing (the safe answer: CLAUDE.md "a dialog whose yes is hard to undo opens on its safe
// answer"); Discard takes no mouse click until a double click has passed (62.3), and both
// answers shield the next press. While it is up it holds scans: a bare CMD:CANCEL keeps
// editing, any other scan is refused on its own line.
window.wizardAskDiscard = ({ title, body, discardLabel }) => new Promise((resolve) => {
    const wizEl = document.getElementById('wizardModal');
    let handle = null;
    let release = null;
    let settled = false;
    const onClosed = (e) => {
        if (handle && e && e.detail && e.detail.element === handle.element) { handle = null; settle(false); }
    };
    const settle = (answer) => {
        if (settled) return;
        settled = true;
        document.removeEventListener('fcc:overlay-closed', onClosed);
        if (release) { release(); release = null; }
        if (handle) { const h = handle; handle = null; h.cleanup(); }
        resolve(answer);
    };
    const esc = window.escHtml || _wizEscape;
    handle = window.mountOverlay({
        id: 'fcc-wiz-unsaved-changes',
        host: wizEl,
        initialFocus: '#fcc-wiz-dirty-cancel',
        onEscape: () => settle(false),
        content: `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #dc3545; border-radius:8px; padding:20px 24px; max-width:28.75rem; width:92%;">
                <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">${esc(title)}</div>
                <div style="color:#ffc; margin-bottom:16px;">${esc(body)}</div>
                <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                    <button id="fcc-wiz-dirty-cancel" class="btn btn-secondary btn-sm" style="min-width:120px;">Keep Editing</button>
                    <button id="fcc-wiz-dirty-confirm" class="btn btn-danger btn-sm" style="min-width:140px;">${esc(discardLabel)}</button>
                </div>
                <div id="fcc-wiz-dirty-flash" role="alert" style="color:#ffc107; font-size:var(--fcc-fs-small); margin-top:10px;"></div>
            </div>`,
    });
    document.addEventListener('fcc:overlay-closed', onClosed);
    const ov = handle.element;
    const shield = () => { if (window.fccShieldNextPress) window.fccShieldNextPress(); };
    const arm = window.armedClick || ((fn) => fn);
    ov.querySelector('#fcc-wiz-dirty-cancel').addEventListener('click', () => { shield(); settle(false); });
    ov.querySelector('#fcc-wiz-dirty-confirm').addEventListener('click',
        arm(() => { shield(); settle(true); }, window.questionArmMs ? window.questionArmMs() : 0));
    const flash = (msg) => { const f = ov.querySelector('#fcc-wiz-dirty-flash'); if (f) f.textContent = msg; };
    if (window.fccHoldScans) {
        release = window.fccHoldScans({
            title: String(title || 'Unsaved Changes').replace(/^\W+\s*/, ''),
            element: ov,
            hint: `Answer the question on screen first: Keep Editing, or ${discardLabel}`,
            cancel: () => settle(false),
            flash,
        });
    }
});

// Group 66.2: is the wizard on screen with a Save on its way (wizardSubmit's session) or
// with edits nobody saved? `opts.why` leads the question's words.
// Returns true when the wizard may start over (or open), false when it was kept as it was.
window.openWizardModal = async (opts = {}) => {
    const wizShown = (() => { const w = document.getElementById('wizardModal'); return !!(w && w.classList.contains('show')); })();
    if (wizShown && wizardState.saving != null) {
        const words = 'The wizard is saving: wait for it to finish, then try again.';
        if (window.showToast) window.showToast(words, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ ${_wizEscape(words)}`, 'WARNING');
        return false;
    }
    if (wizShown && wizardState.isDirty) {
        const editing = wizardState.mode === 'edit_spool' && wizardState.editSpoolId != null;
        const why = opts && opts.why ? `${opts.why} ` : '';
        const discard = await window.wizardAskDiscard({
            title: '⚠️ Unsaved Changes',
            body: `${why}You have unsaved changes${editing ? ` to Spool #${wizardState.editSpoolId}` : ''}. Discard them and start over?`,
            discardLabel: 'Discard & Start Over',
        });
        if (!discard) return false;
        // Asked and answered meanwhile: a Save that began since keeps its form.
        if (wizardState.saving != null) return false;
    }
    // L26 follow-up: close any open details modal before launching the
    // wizard. The 2026-04-29 lock-up Derek reproed was wizard-on-top-of-
    // details — the silent-refresh path's promise can land mid-wizard-
    // open and leave state.processing stuck true. Closing the siblings
    // first mirrors the details↔details pattern shipped 2026-05-12.
    if (typeof window.hideAllDetailsModals === 'function') {
        window.hideAllDetailsModals();
    }
    wizardReset();
    // Review round 1 of Group 66 (R3-06): an opener's prefill is loading from here, through
    // the lists read below (a QR fed into a Spool box meanwhile was wiped by the prefill).
    if (opts && opts.prefilling) wizardState.prefilling = opts.prefilling;
    if (window.modals && window.modals.wizardModal) {
        window.modals.wizardModal.show();
    } else {
        const m = new bootstrap.Modal(document.getElementById('wizardModal'));
        if (!window.modals) window.modals = {};
        window.modals.wizardModal = m;
        m.show();
    }
    // Group 10.1 SC round-6: when the wizard launches on top of another
    // modal (spool/filament details), focus stays on the launching button
    // and Bootstrap's keyboard-dismiss handler (bound to the modal
    // element) never receives Escape until the user clicks the wizard
    // first. Force focus into the wizard after show finishes so Escape
    // works immediately.
    const _wizModalEl = document.getElementById('wizardModal');
    if (_wizModalEl) {
        const _focusFirst = () => {
            const focusables = _wizModalEl.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]),'
                + ' select:not([disabled]), textarea:not([disabled]),'
                + ' [tabindex]:not([tabindex="-1"])'
            );
            for (const el of focusables) {
                // The header's ? (Group 55.3) sits before the ✕; the ✕ keeps the
                // first focus it had before the ? came.
                if (el.matches && el.matches('[data-fcc-help]')) continue;
                if (el.offsetParent !== null) { el.focus(); return; }
            }
            _wizModalEl.focus();
        };
        // shown.bs.modal fires once Bootstrap finishes its own focus
        // management — override after that so we win the focus war.
        _wizModalEl.addEventListener('shown.bs.modal', _focusFirst, { once: true });
    }
    // Group 66.2: a list read that fails leaves the wizard open and its opener going (it
    // rejected the whole open, and an opener awaiting it stopped half-way).
    await Promise.all([
        wizardFetchVendors(),
        wizardFetchLocations(),
        wizardFetchExtraFields(),
        wizardFetchMaterials()
    ].map((p) => Promise.resolve(p).catch((e) => { console.warn('Wizard list read failed', e); return null; })));
    if (window.wizardSyncSpoolRows) window.wizardSyncSpoolRows();
    if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('create');
    return true;
};

// Group 10.1 (Session C) — applies the wizard's section-collapse defaults.
// Called from openWizardModal with 'create' (collapse all optional panels),
// and from each edit-context entry point (openEditWizard, openCloneWizard,
// openNewSpoolFromFilamentWizard) with 'edit' after the prefill chain has
// filled the form — sections with any user-entered data auto-expand so the
// user sees what's actually filled in without clicking each toggle.
window.wizardApplyCollapseDefaults = (context) => {
    if (!window.bootstrap || !window.bootstrap.Collapse) return;
    const hasAnyValue = (panelEl) => {
        if (!panelEl) return false;
        const inputs = panelEl.querySelectorAll('input, select, textarea');
        for (const el of inputs) {
            if (el.type === 'checkbox' || el.type === 'radio') {
                if (el.checked) return true;
            } else if ((el.value == null ? '' : String(el.value)).trim() !== '') {
                return true;
            }
        }
        return false;
    };
    // 'always-open' stays expanded in both contexts; 'optional' obeys the
    // create=collapsed / edit=smart-on-content rule.
    const sections = [
        // Group 10.1 SC round-6: Physical Specs is collapsible like the
        // others. Chip shows the defaults at a glance so user can verify
        // by expanding only when they need to deviate from 1.75mm / 1.24.
        ['wiz-fil-color-panel',      'optional'],
        ['wiz-fil-physical-panel',   'optional'],
        ['wiz-fil-temps-panel',      'optional'],
        ['wiz-fil-extras-panel',     'optional'],
        ['wiz-spool-weight-panel',   'optional'],
        ['wiz-spool-metadata-panel', 'optional'],
        ['wiz-spool-extras-panel',   'optional'],
    ];
    // Suppress the shown.bs.collapse scroll-into-view side effect while
    // we batch-apply panel state — otherwise an edit-mode wizard with
    // 5+ panels to expand cascades through scroll animations, jumping
    // the view around. The flag is cleared right after the loop.
    window._wizSuppressScroll = true;
    sections.forEach(([id, kind]) => {
        const panelEl = document.getElementById(id);
        if (!panelEl) return;
        const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
        let open;
        if (kind === 'always-open') {
            open = true;
        } else {
            // Both 'create' and 'edit' now default to collapsed for optional
            // panels. The summary chips show what's filled in already, so
            // the user can expand only what they actually want to change.
            // Smart-expand-on-edit was dropped per Session C round-4 feedback —
            // it caused too many panels to fan open at once, with cascading
            // scrolls. Chips give the at-a-glance view that auto-expand was
            // trying to provide.
            open = false;
        }
        // Apply state synchronously WITHOUT triggering Bootstrap's animation
        // (and thus without the shown/hidden events that would re-fire scroll
        // logic). Direct class manipulation matches what Bootstrap ends up
        // with after the transition finishes.
        panelEl.classList.remove('collapsing');
        if (open) {
            panelEl.classList.add('show');
            panelEl.style.height = '';
            if (btn) btn.setAttribute('aria-expanded', 'true');
        } else {
            panelEl.classList.remove('show');
            panelEl.style.height = '';
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    });
    window._wizSuppressScroll = false;
    // Refresh summaries now that aria-expanded / .show are settled.
    if (window.wizardRefreshAllSectionSummaries) {
        window.wizardRefreshAllSectionSummaries();
    }
    // Reset the modal-body's scroll position to the top so the user always
    // lands at Step 1 regardless of how the previous session left it.
    const modalBody = document.querySelector('#wizardModal .modal-body');
    if (modalBody) modalBody.scrollTop = 0;
};

// Group 10.1 (Session C polish) — section-summary rendering for collapsed
// panels. The collapsed toggle button shows a compact preview of the
// section's values (color swatch + name, weight chain, price, etc.) so the
// user can see what's filled in without expanding. Templated on the
// printer-status toolhead card pattern (uses getFilamentStyle/makeSwatchHtml
// for color rendering so multi-color gradients render correctly).
//
// Also handles two related UX behaviors:
//   - Auto-scroll: on `shown.bs.collapse`, scrolls the section toggle into
//     view at the top of the modal-body so the user sees the section they
//     just opened.
//   - Clears the summary span when expanded; re-renders when collapsed.
const _wizEscape = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Group 54 review (L1): " ↩ from filament" (or "vendor") while the spool's
// empty-weight badge shows, for the closed Weight & Scale summary; '' otherwise.
const _wizEmptyWeightSummaryMark = () => {
    const badge = document.getElementById('wiz-spool-empty-inherited-badge');
    if (!badge || badge.style.display === 'none') return '';
    const source = (document.getElementById('wiz-spool-empty-inherited-source')?.textContent || '').trim();
    return source ? ` <span class="text-info">↩ from ${_wizEscape(source)}</span>` : '';
};

const _wizSectionSummarizers = {
    'wiz-fil-physical-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const dia = v('wiz-fil-diameter');
        const den = v('wiz-fil-density');
        const wt = v('wiz-fil-weight');
        const empty = v('wiz-fil-empty_weight');
        const parts = [];
        if (dia) parts.push(`${dia}mm Ø`);
        if (den) parts.push(`${den} g/cm³`);
        if (wt) parts.push(`${wt}g net`);
        // Group 66.7: the brand's weight, marked as Weight & Scale marks the spool's (L1).
        if (empty) {
            parts.push(`${empty}g tare` + (wizardFilEmptyWeightIsInherited()
                ? ' <span class="text-info">↩ from vendor</span>' : ''));
        }
        return parts.join(' · ');
    },
    'wiz-fil-color-panel': () => {
        const name = (document.getElementById('wiz-fil-color_name')?.value || '').trim();
        const hex0 = (document.getElementById('wiz-fil-color_hex_0')?.value || '').trim();
        const extras = Array.from(document.querySelectorAll('#wiz-fil-color-extra-container input[type="text"]'))
            .map(el => (el.value || '').trim()).filter(Boolean);
        const allHexes = [hex0, ...extras].filter(h => h && h !== '#FFFFFF');
        if (!name && allHexes.length === 0) return '';
        const dir = document.getElementById('wiz-fil-color-direction')?.value || 'longitudinal';
        const colorStr = allHexes.length > 0 ? allHexes.join(',') : (hex0 || '#FFFFFF');
        const swatch = window.makeSwatchHtml
            ? window.makeSwatchHtml(colorStr, dir, { size: 16, marginRight: 6 })
            : '';
        const label = name || (allHexes[0] || hex0 || '');
        const hexTag = allHexes.length > 1
            ? ` <span class="font-monospace text-info ms-2">${allHexes.length} colors</span>`
            : (allHexes[0] ? ` <span class="font-monospace text-muted ms-2">${allHexes[0]}</span>` : '');
        return `<span class="d-inline-flex align-items-center">${swatch}<span class="text-light">${_wizEscape(label)}</span>${hexTag}</span>`;
    },
    'wiz-fil-temps-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const nMin = v('wiz-fil-settings_extruder_temp'), nMax = v('wiz-fil-nozzle_temp_max');
        const bMin = v('wiz-fil-settings_bed_temp'),     bMax = v('wiz-fil-bed_temp_max');
        const parts = [];
        if (nMin || nMax) parts.push(`Nozzle ${nMin || '?'}–${nMax || '?'}°`);
        if (bMin || bMax) parts.push(`Bed ${bMin || '?'}–${bMax || '?'}°`);
        return parts.join(' · ');
    },
    'wiz-fil-extras-panel': () => {
        const inputs = document.querySelectorAll('#wiz-fil-dynamic-extra-fields input, #wiz-fil-dynamic-extra-fields select, #wiz-fil-dynamic-extra-fields textarea');
        let filled = 0;
        inputs.forEach(el => {
            if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) filled++; }
            else if ((el.value || '').toString().trim() !== '') filled++;
        });
        return filled === 0 ? '' : `${filled} field${filled === 1 ? '' : 's'} set`;
    },
    'wiz-spool-weight-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const empty = v('wiz-spool-empty_weight');
        const initial = v('wiz-spool-initial_weight');
        const remaining = v('wiz-spool-remaining');
        const used = v('wiz-spool-used');
        const parts = [];
        if (remaining) parts.push(`<span class="text-success">${remaining}g left</span>`);
        if (used && used !== '0') parts.push(`${used}g used`);
        if (initial) parts.push(`net ${initial}g`);
        // Group 54 review (L1): an inherited empty weight says so, as the open
        // section's badge does and exactly while it shows, in the price summary's
        // look ("tare 200g ↩ from filament"; the badge's own word, filament or vendor).
        if (empty) parts.push(`tare ${empty}g${_wizEmptyWeightSummaryMark()}`);
        return parts.join(' · ');
    },
    'wiz-spool-metadata-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const price = v('wiz-spool-price');
        const comment = v('wiz-spool-comment');
        const url = v('wiz-spool-purchase_url');
        const purl = v('wiz-spool-product_url');
        const archived = document.getElementById('wiz-spool-archived')?.checked;
        const parts = [];
        // Group 54.8: the filament's price says so, as the box's badge does.
        if (price) parts.push(wizardSpoolPriceIsFilaments()
            ? `$${price} <span class="text-info">↩ from filament</span>` : `$${price}`);
        if (archived) parts.push('<span class="text-warning">archived</span>');
        // 23.5 — mirror the purchase-link chip for the product link so the
        // summary shows BOTH are filled. Icons match the form labels:
        // 🔗 Purchase Link / 📄 Product Link (modals_wizard.html).
        if (url) parts.push('<span class="text-info">🔗 link</span>');
        if (purl) parts.push('<span class="text-info">📄 product</span>');
        if (comment) parts.push(`💬 ${_wizEscape(comment.slice(0, 28))}${comment.length > 28 ? '…' : ''}`);
        return parts.join(' · ');
    },
    'wiz-spool-extras-panel': () => {
        const inputs = document.querySelectorAll('#wiz-spool-dynamic-extra-fields input, #wiz-spool-dynamic-extra-fields select, #wiz-spool-dynamic-extra-fields textarea');
        let filled = 0;
        inputs.forEach(el => {
            if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) filled++; }
            else if ((el.value || '').toString().trim() !== '') filled++;
        });
        return filled === 0 ? '' : `${filled} field${filled === 1 ? '' : 's'} set`;
    },
    // Physical Specs is always-open; no summary needed.
};

window.wizardRefreshSectionSummary = (panelId) => {
    const gen = _wizSectionSummarizers[panelId];
    if (!gen) return;
    const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${panelId}"]`);
    if (!btn) return;
    const summarySpan = btn.querySelector('.fcc-wiz-section-summary');
    if (!summarySpan) return;
    // Chips render regardless of expanded state — they're a glance-able
    // summary of the section's values, so they should also be visible
    // while the user is editing (and confirm the values they just typed).
    const html = gen();
    summarySpan.innerHTML = html || '';
    summarySpan.style.display = html ? '' : 'none';
};

window.wizardRefreshAllSectionSummaries = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => window.wizardRefreshSectionSummary(id));
};

// One-shot wiring at script load: every collapsible panel gets listeners
// for show/hide so summaries refresh and the modal scrolls to the toggle
// the user just clicked. Idempotent — runs once.
(function() {
    if (window._wizCollapseWired) return;
    window._wizCollapseWired = true;
    const panelIds = Object.keys(_wizSectionSummarizers);
    panelIds.forEach(id => {
        const panel = document.getElementById(id);
        if (!panel) return;
        // Bootstrap's default Enter/Space-clicks-focused-button behavior
        // doesn't reliably fire for these toggles, so we synthesize a click
        // on keydown. BUT the browser sometimes ALSO dispatches a native
        // click on keyup (Space) or independently (Enter), causing a
        // expand+collapse double-fire — user has to press twice to land
        // on "expanded". Fix: track the last keyboard-induced click and
        // suppress any native click that arrives within 300ms.
        const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
        if (btn) {
            let lastKbAt = 0;
            // Group 10.1 SC round-5: toggle Bootstrap's Collapse instance
            // directly instead of synthesizing btn.click(). The click()
            // path goes through Bootstrap's data-bs-toggle handler — and
            // the browser ALSO dispatches a native click on keyup (Space)
            // or shortly after (Enter), causing intermittent double-fire
            // even with the round-4 debounce. Going through the API
            // directly bypasses the click handler entirely; even if a
            // native click leaks through, Bootstrap's own _isTransitioning
            // lock blocks the redundant toggle.
            btn.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                    // A scan's Enter, and a Space inside a scan, are the scan's
                    // (Group 61): its Enter collapsed the section and the scan
                    // stayed in the buffer, glued to the next one. The scan
                    // accumulator reads them (its Enter takes the button's own
                    // press away), and a Space inside a scan presses nothing.
                    if (e.key === 'Enter' ? (window.enterIsAScan && window.enterIsAScan())
                        : (window.scanIsArriving && window.scanIsArriving())) {
                        if (e.key !== 'Enter') e.preventDefault();
                        return;
                    }
                    e.preventDefault();
                    e.stopPropagation();
                    // A person's key: a key they left in the scan buffer goes with it.
                    if (window.clearScanBuffer) window.clearScanBuffer();
                    const now = Date.now();
                    if (now - lastKbAt < 400) return;
                    lastKbAt = now;
                    if (window.bootstrap && window.bootstrap.Collapse) {
                        bootstrap.Collapse.getOrCreateInstance(panel, { toggle: false }).toggle();
                    }
                }
            });
            // Backstop: drop any native click that arrives within 400ms of a
            // keyboard toggle. Covers the (rare) case where the browser's
            // synthesized click still reaches Bootstrap despite preventDefault.
            btn.addEventListener('click', (e) => {
                if (e.isTrusted && (Date.now() - lastKbAt < 400)) {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                }
            }, true);
        }
        panel.addEventListener('shown.bs.collapse', (e) => {
            if (e.target !== panel) return;
            window.wizardRefreshSectionSummary(id);
            // Suppress when wizardApplyCollapseDefaults is batch-applying —
            // it sets state synchronously and doesn't need the scroll.
            if (window._wizSuppressScroll) return;
            // Smart-scroll: only scroll if the expansion pushed the panel's
            // bottom below the visible modal-body viewport. If the section
            // already fits entirely on screen, leave the user's scroll
            // position alone (per user feedback — only scroll if the
            // expansion would otherwise be invisible).
            const modalBody = document.querySelector('#wizardModal .modal-body');
            const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
            if (!modalBody || !btn) return;
            const modalRect = modalBody.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            // Bottom-of-panel below bottom-of-modal? Or top-of-toggle
            // already above top-of-modal? Either way, scroll the toggle
            // to the top so the panel becomes fully visible.
            const overflowsBottom = panelRect.bottom > modalRect.bottom - 4;
            const togglesOffTop = btn.getBoundingClientRect().top < modalRect.top + 4;
            if (overflowsBottom || togglesOffTop) {
                btn.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        panel.addEventListener('hidden.bs.collapse', (e) => {
            if (e.target !== panel) return;
            window.wizardRefreshSectionSummary(id);
        });
    });
    // Refresh all CLOSED-section summaries on any input/change inside the
    // modal so collapsed sections stay accurate as the user types in
    // expanded ones (then re-collapses them).
    const wizEl = document.getElementById('wizardModal');
    if (wizEl) {
        const refreshAll = () => {
            panelIds.forEach(id => window.wizardRefreshSectionSummary(id));
        };
        wizEl.addEventListener('input', refreshAll);
        wizEl.addEventListener('change', refreshAll);
    }
})();

// Group 10.1 (Session C polish) — Original Color routing. The
// `original_color` extra field is logically a Color field, not a Custom
// Filament Attribute. wizardFetchExtraFields normally renders it into
// `#wiz-fil-dynamic-extra-fields`; this helper moves it into the Color
// panel's dedicated slot if present. Called from wizardFetchExtraFields
// after the dynamic-extras grid is built.
window.wizardRelocateOriginalColorField = () => {
    const slot = document.getElementById('wiz-fil-original-color-slot');
    if (!slot) return;
    // Clear any prior render: wizardFetchExtraFields runs on every wizard
    // open AND on schema refresh, so without this the slot accumulated a
    // new copy each time (original_color appeared 2x, 3x, ... after
    // multiple opens in the same page session).
    slot.innerHTML = '';
    const extrasGrid = document.getElementById('wiz-fil-dynamic-extra-fields');
    if (!extrasGrid) return;
    const col = extrasGrid.querySelector('[data-extra-key="original_color"]');
    if (col && col.parentElement === extrasGrid) {
        slot.appendChild(col);
        col.className = 'col-md-12';
    }
};

// Group 10.1 (Session C polish) — TPU-only shore_hardness. Hide the
// shore_hardness extra unless the material is TPU-family. Wires a listener
// on the material input + an initial sync, and is re-run after every
// extras render. Material list as of 2026-05: TPU, TPE, TPC are the
// common shore-hardness-relevant flexibles.
const _TPU_FAMILY = ['TPU', 'TPE', 'TPC', 'FLEX'];
window.wizardApplyShoreHardnessGate = () => {
    const matEl = document.getElementById('wiz-fil-material');
    const target = document.querySelector('[data-extra-key="shore_hardness"]');
    if (!target) return;
    const mat = (matEl?.value || '').trim().toUpperCase();
    const isTpu = _TPU_FAMILY.some(prefix => mat.startsWith(prefix));
    target.style.display = isTpu ? '' : 'none';
};

(function() {
    if (window._wizTpuGateWired) return;
    window._wizTpuGateWired = true;
    const matEl = document.getElementById('wiz-fil-material');
    if (matEl) {
        ['input', 'change', 'blur'].forEach(evt => {
            matEl.addEventListener(evt, () => window.wizardApplyShoreHardnessGate());
        });
    }
})();

// Group 10.1 (Session C polish) — Expand / collapse all wizard sections.
// Bound to Shift+E / Shift+C while the wizard modal is open. Registered
// via the shortcuts registry so it appears in the global `?` overlay.
window.wizardExpandAllSections = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => {
        const el = document.getElementById(id);
        if (!el || !window.bootstrap || !window.bootstrap.Collapse) return;
        bootstrap.Collapse.getOrCreateInstance(el, { toggle: false }).show();
    });
};
window.wizardCollapseAllSections = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => {
        const el = document.getElementById(id);
        if (!el || !window.bootstrap || !window.bootstrap.Collapse) return;
        bootstrap.Collapse.getOrCreateInstance(el, { toggle: false }).hide();
    });
};

(function() {
    if (window._wizExpandShortcutWired) return;
    window._wizExpandShortcutWired = true;
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl) return;
    // Modal-scoped capture listener: only fires when the wizard is shown.
    wizEl.addEventListener('keydown', (e) => {
        if (!wizEl.classList.contains('show')) return;
        // Skip if the user is typing into an input/textarea/select — Shift+E
        // is a perfectly valid character keystroke in those contexts.
        const tag = (document.activeElement?.tagName || '').toUpperCase();
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
        if (!e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
        // ⚠️ A barcode scanner sends Shift for EVERY uppercase character, so a
        // scanned label containing 'E' or 'C' looks exactly like Shift+E /
        // Shift+C. Without this guard, scanning while the wizard is open (focus
        // on the modal rather than a field) fired expand/collapse once per such
        // character AND left those characters in state.scanBuffer, corrupting
        // the scan. Bail while a scan is in flight and let the accumulator have
        // the keystroke: one still arriving, however slow the scanner
        // (window.scanIsArriving; Group 57 review, round 4). The keys this
        // leaves in the buffer don't look like a scan, so they no longer stop
        // the next toggle (round 5: E, C, then E did nothing).
        if (window.scanIsArriving ? window.scanIsArriving()
            : (window.isScanInFlight && window.isScanInFlight())) return;
        // ⚠️ preventDefault ONLY — deliberately NOT stopImmediatePropagation.
        // The guard above CANNOT fire on the FIRST character of a scan:
        // scanBuffer is still empty because the accumulator hasn't seen that
        // character yet. This listener sits on wizEl (inside document), so
        // stopping propagation swallowed char #1 — every command QR scanned
        // with the wizard open arrived mangled ('CMD:DONE' -> 'MD:DONE') and
        // failed as an unknown code. Letting the character through costs at
        // worst one spurious expand/collapse, which is harmless and
        // idempotent; eating it breaks the scan outright.
        if (e.key === 'E' || e.key === 'e') {
            e.preventDefault();
            window.wizardExpandAllSections();
        } else if (e.key === 'C' || e.key === 'c') {
            e.preventDefault();
            window.wizardCollapseAllSections();
        }
    });
    // Register with the shortcuts registry so the `?` overlay shows them.
    // The registry script (shortcuts_registry.js) is loaded AFTER this
    // wizard module in scripts.html, so window.registerShortcut may not
    // exist yet. Poll briefly until it shows up.
    const _registerWizardShortcuts = () => {
        if (typeof window.registerShortcut !== 'function') return false;
        window.registerShortcut({
            id: 'wizard-expand-all',
            scope: 'Wizard',
            keys: ['Shift', 'E'],
            description: 'Expand all collapsed sections in the wizard',
        });
        window.registerShortcut({
            id: 'wizard-collapse-all',
            scope: 'Wizard',
            keys: ['Shift', 'C'],
            description: 'Collapse all optional sections in the wizard',
        });
        return true;
    };
    if (!_registerWizardShortcuts()) {
        const start = Date.now();
        const tick = () => {
            if (_registerWizardShortcuts()) return;
            if (Date.now() - start > 5000) return;  // give up after 5s
            setTimeout(tick, 100);
        };
        setTimeout(tick, 100);
    }
})();

// Group 10.4 — populates the spool's purchase_url input with the smart-fallback
// pattern: if the spool already has its own URL, fill the input. If not, leave
// it empty and surface the filament-inherited URL as ghost placeholder text so
// the user can see what details modal will fall back to without unintentionally
// upgrading the inherited link to a spool-level override.
const wizardApplyPurchaseLinkFallback = (spoolUrl, filamentUrl) => {
    const el = document.getElementById('wiz-spool-purchase_url');
    if (!el) return;
    const stripQuotes = (s) => typeof s === 'string' ? s.replace(/^"|"$/g, '') : '';
    const sUrl = stripQuotes(spoolUrl).trim();
    const fUrl = stripQuotes(filamentUrl).trim();
    if (sUrl) {
        el.value = sUrl;
        el.placeholder = 'https://...';
    } else {
        el.value = '';
        if (fUrl) {
            const truncated = fUrl.length > 40 ? fUrl.slice(0, 37) + '…' : fUrl;
            el.placeholder = `${truncated} (inherited from filament)`;
        } else {
            el.placeholder = 'https://...';
        }
    }
};

// L351: same smart-fallback pattern as purchase_url, for the per-spool
// product_url input. Prefill the spool's OWN product_url; if it has none but
// the filament does, advertise the filament URL as ghost placeholder so saving
// without typing leaves the spool override blank (the details modal then falls
// back to the filament's value — inv_details.js:218).
const wizardApplyProductLinkFallback = (spoolUrl, filamentUrl) => {
    const el = document.getElementById('wiz-spool-product_url');
    if (!el) return;
    const stripQuotes = (s) => typeof s === 'string' ? s.replace(/^"|"$/g, '') : '';
    const sUrl = stripQuotes(spoolUrl).trim();
    const fUrl = stripQuotes(filamentUrl).trim();
    if (sUrl) {
        el.value = sUrl;
        el.placeholder = 'https://...';
    } else {
        el.value = '';
        if (fUrl) {
            const truncated = fUrl.length > 40 ? fUrl.slice(0, 37) + '…' : fUrl;
            el.placeholder = `${truncated} (inherited from filament)`;
        } else {
            el.placeholder = 'https://...';
        }
    }
};

// L349: cascade the filament's native price down to a new / cloned / edited
// spool that has none of its own (mirrors the empty-weight cascade). BLANK-GATED
// — only fills when the spool price field is empty AND the spool has no own
// price, so it NEVER overwrites an explicit spool price. `ownPrice` is the
// spool's own price (null for a brand-new spool); `filamentPrice` is the
// filament-level fallback.
//
// Group 54.8 (Derek, 2026-11-07, (a)): the filament's price is shown marked as
// the filament's ("↩ from filament" beside the label, and in the section's
// summary), and it is never saved as the spool's own: a filament's price may not
// be what this spool cost (a sale, a later price). The spool's own price (an
// edit's, or a clone's source spool's) shows plain and saves as before.
window.wizardPrefillSpoolPrice = (ownPrice, filamentPrice) => {
    const el = document.getElementById('wiz-spool-price');
    if (!el) return;
    if (el.value !== '' && el.value != null) return;  // never clobber a typed/own value
    if (ownPrice != null) {
        el.value = ownPrice;
        wizardState.spoolPriceFrom = null;
    } else if (filamentPrice != null) {
        el.value = filamentPrice;
        wizardState.spoolPriceFrom = 'filament';
    }
    window.wizardRefreshSpoolPriceMark();
};

// Group 54.8: whether the price box shows the filament's price, not the spool's
// own: put there by wizardPrefillSpoolPrice and not typed over since (54.5's
// touched set). Save leaves such a price out, so a new spool is created with no
// price and an edited spool keeps none.
const wizardSpoolPriceIsFilaments = () =>
    wizardState.spoolPriceFrom === 'filament' && !wizardNativeTouched('spool', 'price');

// Shows or hides the price box's "↩ from filament" badge to match.
window.wizardRefreshSpoolPriceMark = () => {
    const badge = document.getElementById('wiz-spool-price-inherited-badge');
    if (badge) badge.style.display = wizardSpoolPriceIsFilaments() ? '' : 'none';
};

// Group 54.8, the empty weight's twin (Claude's call): whether the spool's
// empty-weight box shows a value it inherits (its filament's or its brand's, the
// open's cascade, with its badge), not typed over since. Edit Spool's Save leaves
// it out, so the spool keeps having none of its own (or 54.5's clear stays a
// clear). New spools and clones still take it as their own (L34).
const wizardSpoolEmptyWeightIsInherited = () =>
    (wizardState.spoolEmptyWeightFrom === 'filament' || wizardState.spoolEmptyWeightFrom === 'vendor')
    && !wizardNativeTouched('spool', 'spool_weight');

// Group 54 review (R2-1, R2-3): New Spool and Clone fill the spool's price and
// empty weight from its filament, marked as inherited, and the person can still
// pick another filament before Save (the Existing Filament list, 🔍 Advanced
// Search, a scan that recognises one, New Manual Form, Import Database). The boxes
// kept the first filament's: "$25 ↩ from filament" under a filament with no price,
// and its 200 g, which Create then saved as the new spool's own (L34). A box that
// still shows what its filament gives (marked, or empty where that filament gave
// nothing) and that the person hasn't typed in now follows the filament Save will
// use. A clone's own values (its source spool's) stay, and so does a typed one.
// Only those two openers fill the boxes from a filament, so only theirs follow one
// (wizardState.spoolBoxesFollowFilament): the plain wizard's never filled from a
// filament, and don't start now.
const _wizBoxValue = (id) => {
    const el = document.getElementById(id);
    return el && el.value != null ? String(el.value) : '';
};
// The brand picked in the filament's Vendor field, as the wizard read it (its
// empty_spool_weight is the cascade's last step), or null.
const _wizSelectedVendor = () => {
    const vid = _wizBoxValue('wiz-fil-vendor-sel');
    return vid ? ((wizardState.vendors || []).find(v => String(v.id) === String(vid)) || null) : null;
};
const _wizPriceFollowsFilament = () => !wizardNativeTouched('spool', 'price')
    && (wizardState.spoolPriceFrom === 'filament' || _wizBoxValue('wiz-spool-price') === '');
const _wizEmptyWeightFollowsFilament = () => !wizardNativeTouched('spool', 'spool_weight')
    && (wizardState.spoolEmptyWeightFrom === 'filament' || wizardState.spoolEmptyWeightFrom === 'vendor'
        || _wizBoxValue('wiz-spool-empty_weight') === '');

// Group 66 (the cross-check's C11: one helper for every path that redraws the spool's
// empty-weight box from what it inherits): `filamentWt` when it is the filament's own,
// else `vendor`'s, with its badge, or nothing. The caller checks first that the box
// follows (_wizEmptyWeightFollowsFilament). A gross reading in the scale box was worked
// out against the old empty weight: it is worked out again against this one.
const _wizSpoolEmptyWeightFrom = ({ filamentWt = null, vendor = null } = {}) => {
    const { value, source } = resolveEmptySpoolWeightSource({ filamentWt, vendor });
    window.wizardSetSpoolEmptyWeightInherited(value, source, vendor);
    if (_wizBoxValue('wiz-spool-scale').trim() !== '') window.wizardCalcUsedWeight();
    if (window.wizardRefreshSectionSummary) window.wizardRefreshSectionSummary('wiz-spool-weight-panel');
};

// Puts what `fil` gives ({price, spool_weight, vendor}, a filament's record) into
// the boxes that follow it: its price marked "↩ from filament", its empty weight
// (else its brand's) with its badge, or nothing where it has none. `fil` null means
// nothing is known of it (its read failed or is on its way): those boxes then show
// nothing, never the last filament's, and Save sends neither.
const _wizFollowApply = (fil) => {
    let changed = false;
    if (_wizPriceFollowsFilament()) {
        const el = document.getElementById('wiz-spool-price');
        const price = fil && fil.price != null && fil.price !== '' ? fil.price : null;
        if (el) el.value = price != null ? price : '';
        wizardState.spoolPriceFrom = price != null ? 'filament' : null;
        window.wizardRefreshSpoolPriceMark();
        changed = true;
    }
    if (_wizEmptyWeightFollowsFilament()) {
        _wizSpoolEmptyWeightFrom({
            filamentWt: fil ? fil.spool_weight : null,
            vendor: fil ? fil.vendor : null,
        });
        changed = true;
    }
    if (changed && window.wizardRefreshSectionSummary) {
        window.wizardRefreshSectionSummary('wiz-spool-metadata-panel');
        window.wizardRefreshSectionSummary('wiz-spool-weight-panel');
    }
};

// Claude's call 6b (Group 66.5): the plain wizard's boxes never fill from a pick (only New
// Spool and Clone follow a filament), but since 66.5 its spool box shows New Manual Form's
// filament value, marked. After a switch to Existing Filament that filament isn't the one
// Save uses: the box is emptied, as a direct pick leaves it (it showed the stale value
// unmarked, and Create saved it as the new spool's own). Back in New Manual Form or Import
// Database it shows that form's value again. A value the person typed stays, and Edit
// Spool has its own rule.
const _wizPlainFollow = () => {
    const mode = wizardState.mode;
    if (mode === 'edit_spool' || wizardNativeTouched('spool', 'spool_weight')) return;
    const from = wizardState.spoolEmptyWeightFrom;
    if (mode === 'existing') {
        if (from !== 'filament' && from !== 'vendor') return;
        window.wizardSetSpoolEmptyWeightInherited(null, null);
        if (window.wizardRefreshSectionSummary) window.wizardRefreshSectionSummary('wiz-spool-weight-panel');
    } else if (mode === 'manual' || mode === 'external') {
        window.wizardFilamentEmptyWeightChanged(_wizBoxValue('wiz-fil-empty_weight'));
    }
};

const _wizKnownFilament = (id) => {
    const key = String(id);
    for (const list of [wizardState.existingFilaments, wizardState.allFilaments]) {
        const hit = Array.isArray(list) ? list.find(f => f && String(f.id) === key) : null;
        if (hit) return hit;
    }
    return null;
};

// The wizard's filament may have changed: the boxes that follow it show what the
// filament Save will use gives. In Existing Filament mode that is the selected
// filament (`record` when the caller has it, else the lists the wizard read, else
// a read of its own); in New Manual Form and Import Database it is a new filament,
// which has no price (the wizard has no price box for one) and the empty weight
// its own form shows, else its brand's.
window.wizardFollowFilament = (record = null) => {
    if (!wizardState.spoolBoxesFollowFilament) { _wizPlainFollow(); return; }
    const mode = wizardState.mode;
    if (mode === 'manual' || mode === 'external') {
        // Group 66.7: a filament box showing its brand's weight is no value of the
        // filament's: the spool's box then says "↩ from vendor".
        _wizFollowApply({
            price: null,
            spool_weight: wizardFilEmptyWeightIsInherited() ? '' : _wizBoxValue('wiz-fil-empty_weight'),
            vendor: _wizSelectedVendor(),
        });
        return;
    }
    if (mode !== 'existing') return;
    const id = wizardState.selectedFilamentId;
    if (id == null || String(id) === '') return;
    const rec = (record && String(record.id) === String(id)) ? record : _wizKnownFilament(id);
    if (rec) { _wizFollowApply(rec); return; }
    _wizFollowApply(null);
    fetch(`/api/filaments/${encodeURIComponent(id)}`)
        .then(r => r.json())
        .then(d => window.wizardAfterLabel(() => {
            // Only while it is still the filament Save will use, in this session.
            if (!wizardState.spoolBoxesFollowFilament || wizardState.mode !== 'existing'
                || String(wizardState.selectedFilamentId) !== String(id)) return;
            if (d && d.success && d.data && String(d.data.id) === String(id)) _wizFollowApply(d.data);
        }))
        .catch(() => {});
};

const wizardReset = () => {
    // Group 64 fix review 4 (UP5): each open is a session of its own, so a Save's
    // answer that comes after the wizard was opened again (for another spool, or the
    // same one read afresh) leaves the new form alone.
    wizardState.session = (wizardState.session || 0) + 1;
    // Group 64 fix review 5 (VP5): set when Edit Spool couldn't load its spool, so this
    // session's form (still a create form) offers no Save until the wizard is opened again.
    wizardState.editLoadFailed = false;
    wizardState.mode = 'manual';
    wizardState.touchedExtras = new Set();
    wizardState.touchedNative = new Set();
    // Group 66.2 (kept out of the state's literal, whose lines the load-order canary
    // pins): `prefilling`, an opener's prefill still loading ('edit' | 'clone' | 'new');
    // `typedSinceReset`, the text boxes typed in this session (their blur `change` is
    // the person's). `saving` (a Save's session on its way) is wizardSubmit's: a Save
    // that began before this reset still clears it when it lands.
    wizardState.prefilling = null;
    wizardState.typedSinceReset = new WeakSet();
    // Group 64 review (S2 / S3): what Edit Spool's Total Used box showed when it
    // was filled from the record, so Save sends the used weight only when the box
    // changed.
    wizardState.usedShown = null;
    // Group 64 fix review (FP2 / FP3): Total Used worked out as an addition ("+ Add
    // Printed Wt", or Weigh from Scale's Additive mode): {base, shown}, the used
    // weight it was added to and the box's text it gave. Save sends the base, so the
    // server refuses it if a print's charge moved that weight meanwhile, and stamps
    // no weighing for it (typed grams are no reading of the scale).
    wizardState.usedAdd = null;
    // Group 64 full review (PI2): {shown} when the used weight is a scale reading
    // (Weigh from Scale's Gross, Net or Set Used, or the Scale box): only then does
    // Edit Spool's Save tell FCC it weighed the spool.
    wizardState.usedRead = null;
    // Group 54.8: nothing is shown from the filament until an open puts it there.
    wizardState.spoolPriceFrom = null;
    wizardState.spoolEmptyWeightFrom = null;
    // Group 66 (kept out of the state's literal, as 66.2's keys are): whose weight the
    // spool's box shows when it shows its brand's (66.1), and whether the filament's
    // Spool Wt box shows its brand's ('vendor', 66.7).
    wizardState.spoolEmptyWeightVendorId = null;
    wizardState.filEmptyWeightFrom = null;
    // Review round 1 (R3-03): what an edit's link boxes showed at its open (and, since
    // Group 66.9 review round 2, what the last Save that landed sent).
    wizardState.linkShown = null;
    // Group 66.9 review round 2 (R2X-1): a Save whose filament write may have landed with
    // its answer lost leaves the manufacturer's baseline unknown: the next Save sends the
    // Vendor box's manufacturer whatever it shows.
    wizardState.vendorUnsure = false;
    // Group 66.9 review round 3 (R3W6): the manufacturers merged while this window is open,
    // {gone: kept}, so a Save's baseline names the kept one whatever a merge re-pointed.
    wizardState.vendorMerges = {};
    wizardState.spoolBoxesFollowFilament = false;
    wizardState.selectedFilamentId = null;
    wizardState.externalMetaData = null;
    wizardState.lockedAfterSuccess = false;
    // Group 48.4: the last session's profile suggestion (its note, its pending
    // new choice, and who set the field) doesn't carry over.
    wizardState.profileSuggestion = null;
    const _profileSel = document.getElementById('wiz_fil_ef_slicer_profile');
    if (_profileSel) {
        if (_profileSel.dataset) { delete _profileSel.dataset.fccSuggested; delete _profileSel.dataset.fccUserSet; }
        if (typeof _profileSel.querySelectorAll === 'function') {
            _profileSel.querySelectorAll('option[data-fcc-new-choice]').forEach(o => o.remove());
        }
    }
    const _profileNoteEl = document.getElementById('wiz-fil-profile-note');
    if (_profileNoteEl) { _profileNoteEl.textContent = ''; _profileNoteEl.style.display = 'none'; }

    // 17.3 follow-up: clear stale queue-label chips from the prior
    // success so a fresh wizard open doesn't show last-run's spool IDs.
    const _actionRow = document.getElementById('wiz-postcreate-actions');
    if (_actionRow) _actionRow.innerHTML = '';
    // Note: returnToSpoolId is NOT cleared here — it persists across reset so that
    // after a clone/edit completes, the original spool detail modal can re-open.

    // Clear Form. `input[type="url"]` was missing here, which caused
    // wiz-spool-purchase_url to bleed between wizard sessions (Group 10.4).
    document.querySelectorAll('#wizardModal input[type="text"], #wizardModal input[type="number"], #wizardModal input[type="url"]').forEach(i => i.value = '');
    document.querySelectorAll('#wizardModal input[type="checkbox"]').forEach(i => i.checked = false);
    // Reset the spool purchase_url placeholder to its static default — clone
    // and edit flows mutate it to advertise the inherited filament URL, and
    // we don't want that to bleed into the next session either.
    const purchUrlReset = document.getElementById('wiz-spool-purchase_url');
    if (purchUrlReset) purchUrlReset.placeholder = 'https://...';
    const productUrlReset = document.getElementById('wiz-spool-product_url');
    if (productUrlReset) productUrlReset.placeholder = 'https://...';
    document.querySelectorAll('#wizardModal select').forEach(i => i.selectedIndex = 0);
    if (window.wizardClearSpoolEmptyWeightBadge) window.wizardClearSpoolEmptyWeightBadge();
    if (window.wizardRefreshFilEmptyWeightMark) window.wizardRefreshFilEmptyWeightMark();
    if (window.wizardRefreshSpoolPriceMark) window.wizardRefreshSpoolPriceMark();
    if (window.wizardRecheckScale) window.wizardRecheckScale();

    // Reset Color UI
    document.getElementById('wiz-fil-color-extra-container').innerHTML = '';
    document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
    document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
    const dirEl = document.getElementById('wiz-fil-color-direction');
    if (dirEl) dirEl.value = 'longitudinal';
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'none';

    document.getElementById('wiz-spool-qty').value = 1;
    // Restore HTML factory defaults that the type=number bulk-wipe above
    // cleared. Without this, the Physical Specs chip has nothing to show
    // on a fresh wizard open even though the HTML <input value="..."> would
    // normally populate them. (Group 10.1 SC round-3 fix.)
    document.getElementById('wiz-fil-diameter').value = '1.75';
    document.getElementById('wiz-fil-density').value = '1.24';

    // Group 10.1 SC round-5: reset collapse-panel classes to HTML defaults
    // so prior-session expand/collapse state doesn't bleed into the new
    // modal session. Previously, pressing Shift+E to expand all sections
    // then closing the wizard left the .show classes on those panels;
    // re-opening flashed them visible until wizardApplyCollapseDefaults
    // ran (which is async, after Promise.all of fetches — ~500ms+ later).
    const _wizOptionalPanels = [
        'wiz-fil-color-panel', 'wiz-fil-physical-panel', 'wiz-fil-temps-panel',
        'wiz-fil-extras-panel', 'wiz-spool-weight-panel',
        'wiz-spool-metadata-panel', 'wiz-spool-extras-panel',
    ];
    _wizOptionalPanels.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove('show', 'collapsing');
            el.style.height = '';
            const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    });

    if (window.wizardResetSpoolRows) window.wizardResetSpoolRows();
    if (window.wizardClearFilamentMismatchPanel) window.wizardClearFilamentMismatchPanel();
    if (window.wizardClearDuplicatePicker) window.wizardClearDuplicatePicker();

    document.getElementById('wiz-spool-used').value = 0;
    
    wizardState.original_used_weight = 0;
    const usageContainer = document.getElementById('container-wiz-spool-recent-usage');
    if (usageContainer) usageContainer.style.display = 'none';
    const recentInput = document.getElementById('wiz-spool-recent-usage');
    if (recentInput) recentInput.value = '';

    // Reset Edit State button styles
    const submitBtn = document.getElementById('btn-wiz-submit');
    if (submitBtn) {
        submitBtn.innerText = "CREATE INVENTORY";
        submitBtn.classList.remove('btn-primary');
        submitBtn.classList.add('btn-success');
    }
    const step1 = document.getElementById('step-1-material');
    if (step1) step1.style.display = 'block';
    const qtyBox = document.getElementById('wiz-spool-qty');
    if (qtyBox && qtyBox.parentElement) qtyBox.parentElement.style.display = 'flex';
    // Group 66.3 (B): the Prusament box is the Add wizard's per-spool scan again.
    const rowsLabel = document.getElementById('wiz-spool-rows-label');
    if (rowsLabel) rowsLabel.textContent = WIZ_ROWS_LABEL_ADD;
    if (window.wizardRenderLinkNote) window.wizardRenderLinkNote();

    // Reset vendor combobox (visible search field + hidden id). Before the view's reset
    // below (review round 2 of Group 66, Q2-01): wizardSelectType('manual') draws the
    // spool's empty weight from the brand this box holds, and the last session's brand
    // (an Edit Spool's) was still in it: a plain Add opened with that brand's weight in the
    // spool box, "↩ from vendor", and Create saved it as the new spool's and filament's own.
    const vSearch = document.getElementById('wiz-fil-vendor-search');
    if (vSearch) vSearch.value = '';
    const vSel = document.getElementById('wiz-fil-vendor-sel');
    if (vSel) {
        vSel.value = '';
        // Non-bubbling so the dirty-flag tracker doesn't pick up this
        // programmatic reset (matches wizardComboboxSet's policy).
        vSel.dispatchEvent(new Event('change', { bubbles: false }));
    }

    // Reset View
    wizardSelectType('manual');
    document.getElementById('wiz-status-msg').innerText = "";
    // Reset location combobox too. Its hidden id field is an <input type="hidden">,
    // which neither the text-input nor the select loop above clears (it was a
    // <select> once), so an Add opened after an Edit used to send the edited
    // spool's Location while the field showed "Unassigned". Since Group 40.7 a
    // create places the spool there through the move engine (a toolhead's spool
    // unloaded), so clear both halves.
    const lSearch = document.getElementById('wiz-spool-location-search');
    if (lSearch) lSearch.value = '';
    const lHidden = document.getElementById('wiz-spool-location');
    if (lHidden) lHidden.value = '';
    wizardState.pendingPlacement = null;
    wizardState.editSpoolLocation = null;
    wizardSetContextLabel();
    wizardState.isDirty = false;
};

// Paints three coordinated chips: an action word next to the wizard title plus
// bootstrap-badge Spool / Filament chips (also mirrored into the Step 2 and
// Step 3 section headers). Call with `{}` or no arg to clear.
//   wizardSetContextLabel({ action: 'Editing', spoolId: 42, filamentId: 7 })
//   wizardSetContextLabel({ action: 'New Spool for', filamentId: 7 })
//   wizardSetContextLabel()  // clears everything
window.wizardSetContextLabel = (ctx) => {
    ctx = ctx || {};
    const { action, spoolId, filamentId } = ctx;
    const title = document.getElementById('wiz-context-label');
    const step2Ctx = document.getElementById('wiz-step2-fil-context');
    const step2Badge = document.getElementById('wiz-step2-fil-badge');
    const step3Ctx = document.getElementById('wiz-step3-spl-context');
    const step3Badge = document.getElementById('wiz-step3-spl-badge');

    if (title) {
        const parts = [];
        if (action) {
            parts.push(`<span class="fw-semibold text-light" style="font-size: 0.9rem;">${action}</span>`);
        }
        if (spoolId != null && spoolId !== '') {
            parts.push(`<span class="badge text-bg-info" style="font-size: 0.85rem;">🧵 Spool #${spoolId}</span>`);
        }
        if (filamentId != null && filamentId !== '') {
            parts.push(`<span class="badge text-bg-warning text-dark" style="font-size: 0.85rem;">🧬 Filament #${filamentId}</span>`);
        }
        title.innerHTML = parts.join('');
    }

    // Bootstrap's `d-inline-flex` carries `!important`, so inline display:none
    // would lose to it. Toggle between `d-none` and `d-inline-flex` classes.
    if (step2Ctx && step2Badge) {
        if (filamentId != null && filamentId !== '') {
            step2Badge.textContent = `🧬 Filament #${filamentId}`;
            step2Ctx.classList.remove('d-none');
            step2Ctx.classList.add('d-inline-flex');
        } else {
            step2Badge.textContent = '';
            step2Ctx.classList.remove('d-inline-flex');
            step2Ctx.classList.add('d-none');
        }
    }

    if (step3Ctx && step3Badge) {
        if (spoolId != null && spoolId !== '') {
            step3Badge.textContent = `🧵 Spool #${spoolId}`;
            step3Ctx.classList.remove('d-none');
            step3Ctx.classList.add('d-inline-flex');
        } else {
            step3Badge.textContent = '';
            step3Ctx.classList.remove('d-inline-flex');
            step3Ctx.classList.add('d-none');
        }
    }
};

// Wires a text-input + hidden-value + dropdown triple into a keyboard-searchable
// combobox. Mirrors the material-autocomplete pattern (focus/blur/filter/keydown)
// so users get a compact, type-to-filter list with arrow + Enter nav instead of a
// native <select> that takes over the screen. `items` is [{value, label}].
// Re-binding an already-bound input replaces prior listeners via a reset flag.
// `onPick(value, label, before)` (Group 40.7): called after the user picks an
// item with the mouse or Enter (the Location field opens the slot / Printer
// picker from it); `before` is {value, label} as the field stood when the user
// started on it, so a cancelled picker can put it back.
// Group 40.7 review (wizard-tab-resets-head-to-unassigned): the field's text is
// a typed query only when the user typed since focusing it. A value the list
// doesn't show (a toolhead: the Printer picker's "XL-3 (via XL)", or an edited
// spool's "XL-1") is never highlighted, so its label used to read as a query and
// a Tab or Enter through the field confirmed the first item ("-- Unassigned
// --"); Save then took the spool off its head. Now Tab and Enter leave such a
// value alone unless the user typed or highlighted something.
window.wizardBindCombobox = ({ searchId, hiddenId, dropdownId, items, placeholder, onPick = null }) => {
    const search = document.getElementById(searchId);
    const hidden = document.getElementById(hiddenId);
    const dropdown = document.getElementById(dropdownId);
    if (!search || !hidden || !dropdown) return;

    // Replace the node with a clone to drop any previously-attached listeners,
    // then re-grab the fresh reference. This lets wizardBindCombobox be called
    // again (e.g. after wizardFetchVendors refreshes the list).
    const freshSearch = search.cloneNode(true);
    search.parentNode.replaceChild(freshSearch, search);

    if (placeholder) freshSearch.placeholder = placeholder;

    const escape = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));

    // Group 10.2/10.10: on focus (re-entry into an already-populated combobox)
    // render the FULL list and highlight the current selection — without this,
    // the typed query (which is the previously-selected label) filters the
    // list down to one item and the user has to delete text to see anything
    // else. When the user actually types, the input handler swaps to filtered
    // render. `forceAll=true` is passed by focus/keydown-when-closed paths.
    const render = (forceAll = false) => {
        const qs = forceAll ? '' : freshSearch.value.toLowerCase();
        const filtered = qs
            ? items.filter(it => (it.label || '').toLowerCase().includes(qs))
            : items;
        const currentVal = hidden.value;
        dropdown.innerHTML = filtered.map(it => {
            const selectedCls = (forceAll && currentVal && String(it.value) === String(currentVal))
                ? ' active bg-primary' : '';
            return `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option${selectedCls}"
                  data-value="${escape(it.value)}"
                  data-label="${escape(it.label)}">${escape(it.label)}</div>`;
        }).join('');
        dropdown.querySelectorAll('.autocomplete-option').forEach(opt => {
            opt.addEventListener('mousedown', (e) => {
                e.preventDefault();
                freshSearch.value = opt.dataset.label;
                hidden.value = opt.dataset.value;
                dropdown.style.display = 'none';
                // Mirror native change so the wizard's dirty flag listener fires.
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
                picked(opt.dataset.value, opt.dataset.label);
            });
        });
        // If the currently-selected row is rendered, scroll it into view so the
        // user can see (and hit Enter to confirm) without scrolling manually.
        if (forceAll && currentVal) {
            const sel = dropdown.querySelector('.autocomplete-option.active');
            if (sel) {
                const dr = dropdown.getBoundingClientRect();
                const sr = sel.getBoundingClientRect();
                if (sr.bottom > dr.bottom) dropdown.scrollTop += (sr.bottom - dr.bottom);
                else if (sr.top < dr.top) dropdown.scrollTop -= (dr.top - sr.top);
            }
        }
    };

    let before = null;
    // Whether the user typed since the field was focused (or its list reopened).
    let typed = false;
    const remember = () => { before = { value: hidden.value, label: freshSearch.value }; typed = false; };
    // The hidden value has an item in the list ('' is the "-- Unassigned --" /
    // "-- Generic --" item).
    const listed = () => items.some(it => String(it.value) === String(hidden.value));
    const picked = (value, label) => {
        if (typeof onPick === 'function') onPick(value, label, before || { value: '', label: '' });
    };
    // Group 66.1: two items can share a label (two manufacturers of one name: Derek's data
    // has three such pairs). With no row highlighted, Enter and Tab keep the row of the
    // value the field holds when its label is the text typed, not the first of that name.
    const heldRow = (rows) => {
        const text = freshSearch.value.trim().toLowerCase();
        if (hidden.value === '') return null;
        return rows.find(el => String(el.dataset.value) === String(hidden.value)
            && (el.dataset.label || '').toLowerCase() === text) || null;
    };
    // Review round 3 of Group 66 (weights-vendor R3-02): part of a name two items share, then
    // Enter or Tab. Typing blanks the held value (only a whole name is looked up), so the
    // first row of that name won, the lowest id, and Edit Spool's Save moved the filament
    // onto it. The field's own item from before the typing (`before`, taken at the focus)
    // wins when it is listed under the first row's name; any other search keeps the first.
    const tieRow = (rows) => {
        if (!before || before.value === '' || !rows.length) return null;
        const first = (rows[0].dataset.label || '').toLowerCase();
        return rows.find(el => String(el.dataset.value) === String(before.value)
            && (el.dataset.label || '').toLowerCase() === first) || null;
    };
    // Group 66.4: the wizard's scan capture reaches the closure through the box. Its
    // snapshot keeps `typed` (a label's keys set it, and a Tab through the field then
    // confirmed the list's first item), and a place's label scanned into Location picks
    // through `pick`, as Enter's pick does (onPick gets the field as it stood at focus).
    freshSearch._fccCombo = {
        get typed() { return typed; },
        set typed(v) { typed = !!v; },
        pick: (value, label) => {
            freshSearch.value = label;
            dropdown.style.display = 'none';
            typed = false;
            if (String(hidden.value) !== String(value)) {
                hidden.value = String(value);
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            picked(String(value), label);
        },
    };
    // The blur's late hide of the list (below), so a focus back before it fires keeps the
    // list it shows: it hid the list a quick return had just shown, and Tab then confirmed
    // nothing (Group 55 review).
    let hideTimer = null;
    freshSearch.addEventListener('focus', () => {
        clearTimeout(hideTimer);
        hideTimer = null;
        // A search in progress stays one when the field gets the keyboard back (Group 55
        // review, R1-2): the help window closing, or a return from another app. Re-entry
        // reset it to the whole list with nothing typed, so Enter took the list's first
        // item (-- Unassigned --) and Tab took nothing, and Save sent no location.
        // In progress: typed since it was focused, and its text isn't the picked item's.
        const pickedItem = items.find(it => String(it.value) === String(hidden.value));
        if (typed && freshSearch.value.trim() && !(pickedItem && pickedItem.label === freshSearch.value)) {
            render();
            dropdown.style.display = 'block';
            return;
        }
        remember(); render(true); dropdown.style.display = 'block';
    });
    // Group 10.2/10.10: also handle click-while-already-focused. After
    // picking an option, mousedown.preventDefault keeps focus on the input,
    // so a subsequent click never fires `focus` again. Without this, the
    // user has to blur and re-focus to see the full list. Only re-opens the
    // dropdown when it's hidden — a click during active filtering shouldn't
    // wipe the typed query.
    freshSearch.addEventListener('click', () => {
        if (dropdown.style.display === 'none') {
            remember();
            render(true);
            dropdown.style.display = 'block';
        }
    });
    freshSearch.addEventListener('blur', () => {
        // Short delay so mousedown on a list item can fire before we tear it down.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => { hideTimer = null; dropdown.style.display = 'none'; }, 150);
    });
    freshSearch.addEventListener('input', () => {
        typed = true;
        render();
        // If typed text exactly matches a label, capture its value; otherwise clear
        // so partial typing doesn't leak a stale id into the form payload.
        const query = freshSearch.value.trim().toLowerCase();
        // Group 66.1: under a label two items share, the one the field held when the
        // person started on it (else the first, the lowest id for the vendor list).
        const exacts = items.filter(it => (it.label || '').toLowerCase() === query);
        const exact = exacts.find(it => before && String(it.value) === String(before.value)) || exacts[0];
        hidden.value = exact ? exact.value : '';
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
        dropdown.style.display = 'block';
    });
    freshSearch.addEventListener('keydown', (e) => {
        if (dropdown.style.display === 'none') {
            if (e.key === 'ArrowDown') { render(true); dropdown.style.display = 'block'; }
            return;
        }
        const visible = Array.from(dropdown.children);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!visible.length) return;
            e.preventDefault();
            let idx = visible.findIndex(el => el.classList.contains('active'));
            visible.forEach(el => el.classList.remove('active', 'bg-primary'));
            idx = e.key === 'ArrowDown'
                ? (idx + 1 >= visible.length ? 0 : idx + 1)
                : (idx - 1 < 0 ? visible.length - 1 : idx - 1);
            const next = visible[idx];
            next.classList.add('active', 'bg-primary');
            const dr = dropdown.getBoundingClientRect();
            const ir = next.getBoundingClientRect();
            if (ir.bottom > dr.bottom) dropdown.scrollTop += (ir.bottom - dr.bottom);
            else if (ir.top < dr.top) dropdown.scrollTop -= (dr.top - ir.top);
            return;
        }
        if (e.key === 'Enter') {
            e.preventDefault();
            const active = visible.find(el => el.classList.contains('active'));
            if (!active && !typed && !listed()) {
                // A value the list doesn't show (a toolhead), untouched: keep it.
                dropdown.style.display = 'none';
                return;
            }
            const pick = active || heldRow(visible) || tieRow(visible) || visible[0];
            if (pick) {
                freshSearch.value = pick.dataset.label;
                dropdown.style.display = 'none';
                // Only fire change when the value actually changed, so confirming
                // an already-selected value doesn't spuriously flip the wizard's
                // dirty flag (mirrors wizardComboboxSet's bubbles:false rationale).
                if (hidden.value !== pick.dataset.value) {
                    hidden.value = pick.dataset.value;
                    hidden.dispatchEvent(new Event('change', { bubbles: true }));
                }
                // Even when unchanged: picking a box the spool already floats in
                // again is how it gets a slot (Group 40.7).
                picked(pick.dataset.value, pick.dataset.label);
            }
            return;
        }
        if (e.key === 'Tab') {
            // 25.I — Tab confirms the highlighted/typed match like Enter, but does
            // NOT preventDefault so focus advances naturally ("confirm and move
            // on"). Shared helper → covers BOTH the location and vendor comboboxes.
            // Guard a pass-through Tab on an UNTOUCHED field: confirm ONLY when an
            // item is highlighted OR the user typed a query — otherwise a bare
            // tab-through would write the sentinel (visible[0], e.g. "-- Generic
            // --") into the box AND spuriously flip wizardState.isDirty via the
            // bubbling change (false "Unsaved Changes" prompt). Also skip the
            // dispatch when the value is unchanged. Group 40.7 review: "typed" means
            // typed since focus, not "the field has text": a pre-filled label the
            // list doesn't show (a toolhead) is not a query.
            const active = visible.find(el => el.classList.contains('active'));
            const pick = active || (typed && freshSearch.value.trim()
                ? (heldRow(visible) || tieRow(visible) || visible[0]) : null);
            if (pick && hidden.value !== pick.dataset.value) {
                freshSearch.value = pick.dataset.label;
                hidden.value = pick.dataset.value;
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            dropdown.style.display = 'none';
            return;
        }
        if (e.key === 'Escape') {
            // Swallow Escape when the dropdown is open so it closes the
            // dropdown ONLY — without preventDefault + stopPropagation the
            // Escape bubbles to the wizard modal and Bootstrap dismisses it.
            // Matches inv_details.js combobox pattern.
            e.preventDefault();
            e.stopPropagation();
            dropdown.style.display = 'none';
        }
    });
};

// Sets the combobox's visible text + hidden id from a {value, label} pair.
// Pass null/undefined to clear. Used by edit/clone auto-fill paths.
window.wizardComboboxSet = (searchId, hiddenId, value, label) => {
    const s = document.getElementById(searchId);
    const h = document.getElementById(hiddenId);
    if (s) s.value = label || '';
    if (h) {
        h.value = value == null ? '' : value;
        // Fire a NON-BUBBLING change event so direct listeners (the vendor
        // edit-button visibility hook installed in wizardFetchVendors)
        // refresh — but the wizard-level dirty-flag tracker (which listens
        // on the wizardModal wrapper) does NOT mistake this programmatic
        // write for user input. Clone / edit / external-import auto-fill
        // all funnel through this function and the dirty-flag spuriously
        // flipping to true was making Cancel pop the unsaved-changes Swal.
        h.dispatchEvent(new Event('change', { bubbles: false }));
    }
};

window.wizardAutoUpdateDensity = () => {
    const matInput = document.getElementById('wiz-fil-material');
    const densInput = document.getElementById('wiz-fil-density');

    // Only auto-update if the user is typing a new material and hasn't manually overridden it, or if it's basically the default
    const val = (matInput.value || '').toUpperCase();

    let density = 1.24; // Default PLA
    if (val.includes('PETG') || val.includes('PET')) density = 1.27;
    else if (val.includes('ABS')) density = 1.04;
    else if (val.includes('ASA')) density = 1.07;
    else if (val.includes('TPU') || val.includes('TPE') || val.includes('FLEX')) density = 1.21;
    else if (val.includes('NYLON') || val.includes('PA')) density = 1.14;
    else if (val.includes('PC') || val.includes('POLYCARBONATE')) density = 1.20;
    else if (val.includes('HIPS')) density = 1.04;
    else if (val.includes('PVA')) density = 1.19;
    else if (val.includes('PVB')) density = 1.08;

    densInput.value = density.toFixed(2);
};

window.wizardSelectType = (mode, skipSearch = false) => {
    wizardState.mode = mode;

    // Update active button styling
    document.querySelectorAll('.type-selector').forEach(el => el.classList.remove('wiz-active-card'));
    document.getElementById(`btn-type-${mode}`).classList.add('wiz-active-card');

    // Show/Hide Dynamic Areas
    const dynamicArea = document.getElementById('material-dynamic-area');
    const areaExt = document.getElementById('area-existing');
    const areaWeb = document.getElementById('area-external');
    const filConfig = document.getElementById('step-2-filament');
    const spoolConfig = document.getElementById('step-3-spool');

    spoolConfig.style.opacity = '1';
    spoolConfig.style.display = 'block';

    if (mode === 'manual') {
        dynamicArea.style.display = 'none';
        filConfig.style.display = 'block';
        // Group 64 fix review 5 (VP5): never on an Edit Spool form that didn't load.
        document.getElementById('btn-wiz-submit').disabled = !!wizardState.editLoadFailed;
    } else {
        dynamicArea.style.display = 'block';
        areaExt.style.display = (mode === 'existing') ? 'block' : 'none';
        areaWeb.style.display = (mode === 'external') ? 'block' : 'none';

        if (mode === 'existing') {
            filConfig.style.display = 'none';
            if (!skipSearch) wizardSearchExisting();
        } else {
            filConfig.style.display = 'block';
        }

        wizardValidateSubmit();
    }
    // Group 54 review (R2-1, R2-3): New Manual Form and Import Database make a new
    // filament, and Existing Filament goes back to the one selected there.
    window.wizardFollowFilament();
};

window.wizardValidateSubmit = () => {
    const btn = document.getElementById('btn-wiz-submit');
    if (wizardState.lockedAfterSuccess || wizardState.editLoadFailed) {
        btn.disabled = true;
        return;
    }
    if (wizardState.mode === 'existing' && !wizardState.selectedFilamentId) {
        btn.disabled = true;
    } else {
        btn.disabled = false;
    }
};

// Group 63 review (K37): the Scale box's note follows the box: it goes with the
// reading (reset, a weight worked out another way, Clear), and the used weight is
// worked out again when the empty weight it waited for arrives (the filament's box,
// a filament picked), as a keyup in those boxes does.
window.wizardRecheckScale = () => {
    const scale = document.getElementById('wiz-spool-scale');
    if (scale && String(scale.value || '').trim() !== '') { window.wizardCalcUsedWeight(); return; }
    const note = document.getElementById('wiz-spool-scale-note');
    if (note) { note.textContent = ''; note.style.display = 'none'; }
};

window.wizardCalcUsedWeight = () => {
    const note = document.getElementById('wiz-spool-scale-note');
    const say = (words) => { if (note) { note.textContent = words; note.style.display = words ? '' : 'none'; } };
    const scaleWt = parseFloat(document.getElementById('wiz-spool-scale').value);
    if (isNaN(scaleWt)) { say(''); return; }

    let emptyWt = parseFloat(document.getElementById('wiz-spool-empty_weight').value);
    if (isNaN(emptyWt)) {
        emptyWt = parseFloat(document.getElementById('wiz-fil-empty_weight').value);
    }
    // Group 63.9(c): with no empty weight known at any level (the spool's box
    // shows its filament's or its brand's when it inherits one), a gross reading
    // can't be told from the spool's own weight: it used to count a missing tare
    // as 0 g, so the empty spool read as filament. Compute nothing, and say why.
    if (isNaN(emptyWt)) {
        say("Enter the spool's empty weight first: FCC needs it to tell the filament from the spool.");
        return;
    }
    say('');

    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value);
    }
    // 24.K — don't silently assume 1kg when no net weight is known anywhere.
    // Abort the derivation so the user supplies a real net weight first (a
    // defaulted-weight Prusament scan now leaves wiz-fil-weight blank).
    if (isNaN(netWt)) return;

    let used = (netWt + emptyWt) - scaleWt;
    if (used < 0) used = 0;
    if (used > netWt) used = netWt; // [ALEX FIX] Spoolman crashes if used > initial_weight

    // buglist L51: 1-decimal (PRECISE tier) instead of .toFixed(0). The field
    // value is what gets PERSISTED to Spoolman on submit, so rounding to a
    // whole gram here silently lost the sub-gram tare component AND made `used`
    // (shown raw on edit-load) disagree with the rounded `remaining`. Deriving
    // both from the same exact `used` and trimming to 0.1g keeps them
    // reconciled (used + remaining == netWt).
    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(used);
    document.getElementById('wiz-spool-remaining').value = window.fmtGramsPrecise(netWt - used);
    // Group 64 fix review 2 (CP1 / CX2): the Scale box is a number box with no scan
    // capture, so a spool label scanned into it leaves its digits there (ID:57 reads
    // 57) and they are worked out as a gross reading: no reading FCC can vouch for, so
    // never stamped as its weighing. Weigh from Scale's boxes take the weight capture.
    wizardState.usedRead = null;
    wizardState.usedAdd = null;
};

window.wizardCalcUsedFromRemaining = () => {
    const remaining = parseFloat(document.getElementById('wiz-spool-remaining').value);
    if (isNaN(remaining)) return;
    
    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value);
    }
    if (isNaN(netWt)) return;  // 24.K — no known net weight; don't assume 1kg

    let used = netWt - remaining;
    if (used < 0) used = 0;
    if (used > netWt) used = netWt;

    wizardState.usedRead = null;      // PI2: a figure typed in Remaining is no reading
    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(used);
    document.getElementById('wiz-spool-scale').value = '';
    window.wizardRecheckScale();
};

window.wizardCalcRemainingFromUsed = () => {
    const used = parseFloat(document.getElementById('wiz-spool-used').value);
    if (isNaN(used)) return;
    
    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value);
    }
    if (isNaN(netWt)) return;  // 24.K — no known net weight; don't assume 1kg

    let remaining = netWt - used;
    if (remaining < 0) remaining = 0;

    document.getElementById('wiz-spool-remaining').value = window.fmtGramsPrecise(remaining);
    document.getElementById('wiz-spool-scale').value = '';
    window.wizardRecheckScale();
};

window.wizardCalcFromRecentUsage = () => {
    let recent = parseFloat(document.getElementById('wiz-spool-recent-usage').value);
    if (isNaN(recent)) recent = 0;
    
    let baseUsed = wizardState.original_used_weight || 0;
    let newTotal = baseUsed + recent;
    if (newTotal < 0) newTotal = 0;

    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(newTotal);
    wizardState.usedAdd = recent ? { base: baseUsed, shown: document.getElementById('wiz-spool-used').value } : null;
    wizardState.usedRead = null;      // PI2
    window.wizardCalcRemainingFromUsed();
};

window.wizardClearScaleWeight = () => {
    document.getElementById('wiz-spool-scale').value = '';
    window.wizardRecheckScale();
    window.wizardCalcRemainingFromUsed();
};

// 31.1 — Guided scale entry for the wizard weight grid. Derek's pain: with a
// gross scale reading + a known empty-spool tare he couldn't tell which of the
// six fields to fill to get the tare deducted into remaining/total. This opens
// the shared <WeightEntry> overlay (gross/net + live preview + missing-tare
// prompt) and writes the computed values back into the grid — no more hunting.
// When no original net weight is known anywhere (the reason we dropped the
// hard-coded 1000g), it catalogs "what's on the spool now" (gross − tare) as
// the spool's full capacity via WeightEntry's allowUnknownInitial path.
window.wizardOpenWeightEntry = () => {
    if (!window.WeightEntry || typeof window.WeightEntry.openModal !== 'function') return;

    const num = (id) => {
        const el = document.getElementById(id);
        const raw = (el && el.value != null ? el.value : '').trim();
        if (raw === '') return null;
        const n = parseFloat(raw);
        return Number.isNaN(n) ? null : n;
    };

    // Tare: the spool's own empty weight, else the filament's (inherited).
    let tare = num('wiz-spool-empty_weight');
    if (tare === null) tare = num('wiz-fil-empty_weight');
    // Net (initial): spool override, else the filament net weight. May be unknown.
    let net = num('wiz-spool-initial_weight');
    if (net === null) net = num('wiz-fil-weight');
    const currentUsed = num('wiz-spool-used') || 0;
    // FP2 / FP3: what an Additive reading adds to. The box shows the record's used
    // weight to 0.1 g; while it is untouched, the record's own figure is the base.
    const usedBox = document.getElementById('wiz-spool-used');
    const usedBase = (usedBox && wizardState.usedShown != null && usedBox.value === wizardState.usedShown)
        ? (wizardState.original_used_weight || 0) : currentUsed;
    const initialKnown = net !== null && net > 0;

    // Context for the header + missing-tare prompt. The human-readable vendor
    // name lives in the visible search box; `wiz-fil-vendor-sel` is a hidden
    // <input> holding only the numeric id (no selectedIndex).
    const vendorName = (document.getElementById('wiz-fil-vendor-search')?.value || '').trim();
    const material = document.getElementById('wiz-fil-material')?.value || '';
    const color = document.getElementById('wiz-fil-color_name')?.value || '';
    const colorHexEl = document.querySelector('input[id^="wiz-fil-color_hex_"]');
    const colorHex = colorHexEl ? colorHexEl.value.replace('#', '') : null;
    const display = [vendorName, material, color].filter(Boolean).join(' - ') || 'New Spool';

    window.WeightEntry.openModal({
        title: 'Weigh from Scale',
        spool: {
            id: wizardState.editSpoolId || '',
            initial_weight: initialKnown ? net : 0,
            used_weight: currentUsed,
            display,
            color_hex: colorHex,
        },
        empty_spool_weight: tare,
        context: { vendor: vendorName, material, color, color_hex: colorHex },
        defaultMode: 'gross',
        // additive / set_used need a known original net — only offer them then.
        availableModes: initialKnown ? ['gross', 'net', 'additive', 'set_used'] : ['gross', 'net'],
        allowUnknownInitial: !initialKnown,
        showAutoArchive: false,  // 31.2 — archive stays a save-time decision, not a live toggle.
        onSubmit: (payload) => {
            const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
            // Persist the tare the user entered/confirmed if the field was blank.
            const emptyEl = document.getElementById('wiz-spool-empty_weight');
            if (payload.empty_spool_weight != null &&
                (emptyEl && emptyEl.value != null ? emptyEl.value : '').trim() === '') {
                setVal('wiz-spool-empty_weight', window.fmtGramsPrecise(payload.empty_spool_weight));
                // The tare the person gave is the spool's own, even in a box marked
                // as inherited (the filament's emptied, and the spool's with it):
                // its badge goes, and Edit Spool saves it (Group 54.8).
                window.wizardClearSpoolEmptyWeightBadge();
            }
            if (payload.derived_initial != null) {
                // Unknown-net path: record what's on the spool now as its full capacity.
                setVal('wiz-spool-initial_weight', window.fmtGramsPrecise(payload.derived_initial));
                setVal('wiz-spool-used', '0');
                wizardState.usedAdd = null;
                wizardState.usedRead = { shown: document.getElementById('wiz-spool-used').value };   // PI2
            } else {
                setVal('wiz-spool-used', window.fmtGramsPrecise(payload.used_weight));
                // FP2 / FP3: Additive adds grams to the used weight; any other mode is a reading.
                wizardState.usedAdd = payload.mode === 'additive'
                    ? { base: usedBase, shown: document.getElementById('wiz-spool-used').value } : null;
                wizardState.usedRead = payload.mode === 'additive'
                    ? null : { shown: document.getElementById('wiz-spool-used').value };          // PI2
            }
            // Recompute remaining from the freshly-set net + used; clear the raw scale field.
            window.wizardCalcRemainingFromUsed();
            setVal('wiz-spool-scale', '');
            window.wizardRecheckScale();
            // The person's reading is their change (review round 1 of Group 66, R3-05): set by
            // code, it marked nothing, and 66.2's guard started an Edit over with no question.
            if (window.wizardMarkChanged) window.wizardMarkChanged();
        },
    });
};

// --- A LABEL SCANNED INTO A WIZARD BOX (Group 66.4) ---
// A label scanned while one of the wizard's boxes had the keyboard was typed there, and
// its keys ran the wizard's listeners as a person's typing does: Bed Min read 57, the
// box counted as the person's (54.5's touched set: an emptied one became a clear), the
// inherited empty weight and the filament's price lost their marks and were saved as
// the spool's own (54.8), a label in Scale Gross worked out a used weight from its
// digits (Save wrote it), one in Location blanked the place the field held (Save moved
// the spool to Unassigned), and the form counted as changed. The shared capture
// (installFieldScanCapture) now sends such a label on as a scan, and wizardTookScan
// undoes what the label's keys changed: every box (values, ticks, hidden ids), the
// state below, the Save button, the status line, what the marks and summaries are
// drawn from, each combobox's "typed", the Spool rows and a slicer profile FCC
// suggested.
// Review round 2 of Group 66: it put back a snapshot of the whole form taken at the
// label's first key. An answer that landed while the label was being typed (a
// Prusament QR's lookup, filling Step 2 and freeing Save) was undone with it, and what
// the snapshot didn't hold stayed as the keys left it: Quantity's Spool rows (the box
// read 3 again while Save made 357 spools, or 1) and a slicer profile FCC suggested
// (the brand box's keys dropped it). Now each key typed into a wizard box is journaled
// with what its own listeners changed (from its keydown to the end of its `input`, and
// through its `keyup`), the capture's snapshot hook marks where the label's first key
// is in that journal, and the undo puts each thing back, the label's last key first,
// only while it still holds what that key left it: what an answer wrote meanwhile stays.
// The key canary (tests/test_wizard_scan_capture_66_4.py) holds every wizardState key to
// one of these two lists: a new key fails it until someone decides.
// What a label's keys can change, put back:
window.WIZ_SCAN_STATE_KEYS = ['isDirty', 'lockedAfterSuccess', 'touchedExtras', 'touchedNative',
    'spoolPriceFrom', 'spoolEmptyWeightFrom', 'spoolEmptyWeightVendorId', 'filEmptyWeightFrom',
    'usedRead', 'usedAdd', 'pendingPlacement', 'selectedFilamentId', 'spoolRows', 'profileSuggestion'];
// What they can't (set by an open, a pick, a Save or a read), or what is put back
// another way (typedSinceReset: the scanned box's own entry). A key that changes one of
// these all the same is noted in window.wizardScanUntracked, which the scan tests read.
window.WIZ_SCAN_STATE_SKIPS = ['mode', 'session', 'saving', 'prefilling', 'typedSinceReset',
    'vendors', 'existingFilaments', 'allFilaments', 'allLocationRows', 'locations', 'materials',
    'extraFields', 'editSpoolId', 'editSpoolLocation', 'editFilamentOriginal',
    'editLoadFailed', 'externalMetaData', 'returnToSpoolId', 'returnToFilamentId', 'forceClose',
    'spoolBoxesFollowFilament', 'filamentLockedFromScan', 'original_used_weight', 'usedShown',
    '_dupPicker', '_mismatches', 'linkShown', 'vendorUnsure', 'vendorMerges'];
window.wizardScanUntracked = [];
const _wizScanFields = () => {
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl) return [];
    return Array.from(wizEl.querySelectorAll('input, select, textarea'))
        .filter((f) => !(f.closest && f.closest('.swal2-container')));
};
// A Set is copied; a list (the Spool rows) is copied as the same rows, so a lookup still
// on its way writes into a row the undo puts back.
const _wizScanCopy = (v) => (v instanceof Set ? new Set(v) : (Array.isArray(v) ? v.slice() : v));
const _wizScanEq = (a, b) => {
    if (a === b) return true;
    if (a instanceof Set || b instanceof Set) {
        if (!(a instanceof Set) || !(b instanceof Set) || a.size !== b.size) return false;
        for (const x of a) if (!b.has(x)) return false;
        return true;
    }
    if (Array.isArray(a) || Array.isArray(b)) {
        return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => x === b[i]);
    }
    if (a && b && typeof a === 'object' && typeof b === 'object') {
        try { return JSON.stringify(a) === JSON.stringify(b); } catch (_) { return false; }
    }
    return false;
};
const WIZ_SCAN_SHOWS = ['wiz-spool-empty-inherited-badge', 'wiz-spool-scale-note', 'wiz-fil-vendor-edit-btn'];
const WIZ_SCAN_TEXTS = ['wiz-spool-empty-inherited-source', 'wiz-spool-scale-note'];
// Everything a key can change, each { get, set, rank }: rank 0 is put back first (the
// Spool rows and the profile list's options, whose boxes and value come after), then the
// boxes, then the rest. A `watch` item is never put back: a change to it is noted.
const _wizScanItems = (target) => {
    const items = new Map();
    const add = (id, get, set, rank, extra = {}) => items.set(id, Object.assign({ get, set, rank }, extra));
    add('rows', () => (wizardState.spoolRows || []).slice(), (v) => {
        wizardState.spoolRows = v.slice();
        wizardState.spoolRows.forEach((r, i) => { r.idx = i; });
    }, 0, { rows: true });
    const sel = _profileSelect();
    if (sel) {
        add('profile-options', () => Array.from(sel.options), (v) => {
            const keep = new Set(v);
            Array.from(sel.options).forEach((o) => { if (!keep.has(o)) o.remove(); });
            v.forEach((o) => sel.appendChild(o));
        }, 0, { alive: () => sel.isConnected });
        add('profile-marks', () => JSON.stringify([sel.dataset.fccSuggested ?? null, sel.dataset.fccUserSet ?? null]),
            (v) => {
                const [suggested, userSet] = JSON.parse(v);
                if (suggested == null) delete sel.dataset.fccSuggested; else sel.dataset.fccSuggested = suggested;
                if (userSet == null) delete sel.dataset.fccUserSet; else sel.dataset.fccUserSet = userSet;
            }, 2, { alive: () => sel.isConnected });
    }
    add('profile-note', () => {
        const n = document.getElementById('wiz-fil-profile-note');
        return n ? JSON.stringify([n.textContent, n.style.display]) : null;
    }, (v) => {
        const n = document.getElementById('wiz-fil-profile-note');
        if (!n) return;
        const [text, display] = v == null ? ['', 'none'] : JSON.parse(v);
        n.textContent = text;
        n.style.display = display;
    }, 2);
    _wizScanFields().forEach((f) => {
        const tick = f.type === 'checkbox' || f.type === 'radio';
        add(f, () => (tick ? f.checked : f.value), (v) => { if (tick) f.checked = v; else f.value = v; }, 1,
            { alive: () => f.isConnected });
        if (f._fccCombo) {
            const c = f._fccCombo;
            add(c, () => c.typed, (v) => { c.typed = v; }, 2, { alive: () => f.isConnected });
        }
    });
    window.WIZ_SCAN_STATE_KEYS.forEach((k) => {
        if (k === 'spoolRows') return;          // 'rows' above
        add(`state:${k}`, () => _wizScanCopy(wizardState[k]), (v) => { wizardState[k] = _wizScanCopy(v); }, 2);
    });
    window.WIZ_SCAN_STATE_SKIPS.forEach((k) => {
        if (k === 'typedSinceReset') return;    // 'typed' below
        add(`skip:${k}`, () => wizardState[k], null, 3, { watch: k, eq: (a, b) => a === b });
    });
    if (target) {
        add('typed', () => !!(wizardState.typedSinceReset && wizardState.typedSinceReset.has(target)), (v) => {
            if (!wizardState.typedSinceReset) return;
            if (v) wizardState.typedSinceReset.add(target); else wizardState.typedSinceReset.delete(target);
        }, 2);
    }
    WIZ_SCAN_SHOWS.forEach((id) => {
        const n = document.getElementById(id);
        if (n) add(`show:${id}`, () => n.style.display, (v) => { n.style.display = v; }, 2);
    });
    WIZ_SCAN_TEXTS.forEach((id) => {
        const n = document.getElementById(id);
        if (n) add(`text:${id}`, () => n.innerHTML, (v) => { n.innerHTML = v; }, 2);
    });
    const save = document.getElementById('btn-wiz-submit');
    if (save) add('save', () => save.disabled, (v) => { save.disabled = v; }, 2);
    const status = document.getElementById('wiz-status-msg');
    if (status) add('status', () => status.innerHTML, (v) => { status.innerHTML = v; }, 2);
    return items;
};
const _wizScanImage = (target) => {
    const img = new Map();
    _wizScanItems(target).forEach((item, id) => {
        try { img.set(id, { item, v: item.get() }); } catch (_) { /* unreadable now */ }
    });
    return img;
};
// The journal: one record per key typed into a wizard box, of what that key changed.
const WIZ_KEY_JOURNAL_MAX = 400;
let _wizKeyJournal = [];
let _wizKeySeq = 0;
let _wizKeyDown = null;     // { rec, target, img }: a key whose keydown is being journaled
let _wizKeyInput = null;    // { rec, target, img }: that key's text going into its box
let _wizKeyUp = null;       // { rec, target, img }: a keyup being journaled

// --- AN ANSWER WAITS WHILE A LABEL ARRIVES (review round 3 of Group 66) ---
// The journal puts back what a label's keys changed, but an answer landing while the label
// was in a box still went wrong: it worked things out from the box (Scale Gross holding the
// label's digit: Total Used from it, and Create made the spool empty, R3-02), its write into
// the box being scanned was put back with the box (R3-03), and one queued inside a key's
// record was undone as that key's (R3-01). So the wizard's answers that fill its form (the
// Prusament lookups, the filament follow, the vendor, location and extra-field lists, the
// global search's pick) wait while keys are arriving in one of its boxes: a key in the last
// 300 ms, or a ':' or '/' typed within 2 s with no Enter, Tab or scan since (a scanner can
// stall inside a label), and 2.5 s at most. A label's scan, an Enter, a Tab, Escape or a
// click away ends the wait, and the answer fills the form as the label left it.
const WIZ_KEYS_QUIET_MS = 300;
const WIZ_LABEL_STALL_MS = 2000;
const WIZ_ANSWER_WAIT_MAX_MS = 2500;
const _wizNow = () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
let _wizKeysAt = 0;         // when the last key was typed into a wizard box (0: none since the last end)
let _wizKeysText = '';      // the keys typed since then
const _wizKeysDone = () => { _wizKeysAt = 0; _wizKeysText = ''; };
const _wizNoteKey = (key) => {
    if (key === 'Enter' || key === 'Tab' || key === 'Escape') { _wizKeysDone(); return; }
    if (typeof key !== 'string' || key.length !== 1) return;
    const now = _wizNow();
    if (!_wizKeysAt || now - _wizKeysAt > WIZ_LABEL_STALL_MS) _wizKeysText = '';
    _wizKeysText += key;
    _wizKeysAt = now;
};
window.wizardLabelArriving = () => {
    if (!_wizKeysAt) return false;
    const since = _wizNow() - _wizKeysAt;
    if (since < WIZ_KEYS_QUIET_MS) return true;
    return since < WIZ_LABEL_STALL_MS && /[:/]/.test(_wizKeysText);
};
// Runs fn once no label is arriving (now, when none is), and answers what it answers.
window.wizardAfterLabel = (fn) => new Promise((resolve, reject) => {
    const started = _wizNow();
    const go = () => {
        if (window.wizardLabelArriving() && _wizNow() - started < WIZ_ANSWER_WAIT_MAX_MS) {
            setTimeout(go, 50);
            return;
        }
        try { resolve(typeof fn === 'function' ? fn() : undefined); } catch (err) { reject(err); }
    };
    go();
});
const _wizScanDiff = (rec, a, b) => {
    a.forEach((was, id) => {
        const now = b.get(id);
        if (!now) return;
        if ((was.item.eq || _wizScanEq)(was.v, now.v)) return;
        if (was.item.watch) {
            if (window.wizardScanUntracked.length < 50) window.wizardScanUntracked.push(was.item.watch);
            return;
        }
        rec.changes.push({ item: was.item, before: was.v, after: now.v });
    });
};
const _wizKeyDownEnd = () => {
    const o = _wizKeyDown;
    _wizKeyDown = null;
    if (o) _wizScanDiff(o.rec, o.img, _wizScanImage(o.target));
};
const _wizKeyInputEnd = () => {
    const o = _wizKeyInput;
    _wizKeyInput = null;
    if (o) _wizScanDiff(o.rec, o.img, _wizScanImage(o.target));
};
// Group 54 review R2-2's guard stops a rejected key's `input` before the window hears it, so it
// ends that key's input phase itself (review round 3, R3-01).
window.wizardKeyInputStopped = () => _wizKeyInputEnd();
// The capture's snapshot hook: where the label's first key is in the journal (the
// record that key is about to open).
window.wizardScanSnapshot = (el = null) => ({ seq: _wizKeySeq, el });
// Undoes what the keys from the snapshot's on changed, the last key first, each thing
// only while it holds what that key left it.
window.wizardScanRestore = (snap) => {
    _wizKeysDone();             // the label has ended: an answer waiting for it goes on
    if (!snap || typeof snap.seq !== 'number') return;
    _wizKeyDownEnd();
    _wizKeyInputEnd();
    let rows = false;
    const recs = _wizKeyJournal.filter((r) => r.seq >= snap.seq);
    for (let i = recs.length - 1; i >= 0; i--) {
        recs[i].changes.slice().sort((x, y) => x.item.rank - y.item.rank).forEach((c) => {
            if (c.item.alive && !c.item.alive()) return;
            let now;
            try { now = c.item.get(); } catch (_) { return; }
            if (!_wizScanEq(now, c.after)) return;       // changed again since: what changed it stays
            try { c.item.set(c.before); } catch (_) { return; }
            if (c.item.rows) rows = true;
        });
    }
    _wizKeyJournal = [];
    // What is drawn from the state follows it.
    if (rows) {
        window.wizardRenderSpoolRows();
        window.wizardUpdateSubmitGate();
    }
    if (window.wizardRefreshSpoolPriceMark) window.wizardRefreshSpoolPriceMark();
    if (window.wizardRefreshFilEmptyWeightMark) window.wizardRefreshFilEmptyWeightMark();
    if (window.wizardApplyShoreHardnessGate) window.wizardApplyShoreHardnessGate();
    if (window.wizardRefreshAllSectionSummaries) window.wizardRefreshAllSectionSummaries();
    document.querySelectorAll('#wizardModal [id^="dropdown-"]').forEach((d) => { d.style.display = 'none'; });
};

// A place's label scanned into Location (its scan's last label, any case): the place
// it names is picked as a pick from the list is (a box with slots, or a printer, opens
// its picker; a slot's label picks its box, whose picker reads the slot's label in
// turn). A place the list doesn't offer (a head, an unknown id) is refused, on the
// status line, in a warning toast and one Activity Log line, as the location editor's
// parent picker refuses one; nothing goes to the scan path.
const _wizLocationLabel = (lab, id, text, el) => {
    const key = _wizLocKey(id);
    const row = key === '' ? { LocationID: '', Name: '' }
        : (wizardState.locations || []).find((l) => l && _wizLocKey(l.LocationID) === key);
    if (row && el && el._fccCombo) {
        const label = row.LocationID === '' ? '-- Unassigned --'
            : (row.Name ? `${row.Name} (${row.LocationID})` : row.LocationID);
        el._fccCombo.pick(row.LocationID, label);
        return;
    }
    const why = `${lab} isn't a place this list offers. Pick one from the list.`;
    const status = document.getElementById('wiz-status-msg');
    if (status) status.textContent = why;
    if (window.showToast) window.showToast(why, 'warning', 7000);
    if (window.logClientEvent) window.logClientEvent(`⚠️ Scan "${_wizEscape(text)}" ignored: ${_wizEscape(why)}`, 'WARNING');
};

// The shared capture's onScan: the wizard as it was before the label's first key, then
// the label goes on (a place's label in Location picks it).
window.wizardTookScan = (text, el, info) => {
    window.wizardScanRestore(info && info.snapshot);
    if (el && el.id === 'wiz-search-existing' && window.wizardSearchExisting) window.wizardSearchExisting();
    if (el && el.id === 'wiz-spool-location-search') {
        const lab = window.lastScanLabel ? window.lastScanLabel(text) : String(text || '').trim().toUpperCase();
        const m = /^LOC:([^:]+?)(?::SLOT:\d+)?$/.exec(lab || '');
        if (m) { _wizLocationLabel(lab, m[1], text, el); return; }
    }
    if (typeof window.processScan === 'function') window.processScan(text, (info && info.source) || 'barcode');
};

// Installed once at load (inv_core.js, loaded before this module, defines the capture).
// Every text, number and link box of the wizard, not a dialog drawn inside it (Force
// Location's list). A box that takes a web address (the Spool boxes, Purchase Link,
// Product Link, Import Database's search) keeps one, and an FCC label there is a scan
// (Claude's call (c)). The page's payload rule (the cross-check's C9): a prefixed label
// is a scan at any pace (labels mode), digits alone at scanner pace too, and a fast
// "PLA" + Enter in Material stays the person's.
(function () {
    if (typeof window.installFieldScanCapture !== 'function') return;
    const takesLinks = (el) => el.type === 'url' || el.id === 'wiz-search-external';
    const fccLabel = (t) => !!(window.fccIsLabel && window.fccIsLabel(t)) && !/^https?:\/\//i.test(t);
    const match = (el) => !!el && el.tagName === 'INPUT' && ['text', 'number', 'search', 'url'].includes(el.type)
        && !!el.closest && !!el.closest('#wizardModal') && !el.closest('.swal2-container');
    window.installFieldScanCapture({
        labels: true,
        match,
        isScanPayload: (t) => (typeof window.looksLikeScanPayload === 'function'
            ? window.looksLikeScanPayload(t) : /[:/]/.test(t)),
        snapshot: (el) => window.wizardScanSnapshot(el),
        keep: (text, el) => takesLinks(el) && !fccLabel(text),
        restoreEvent: false,
        onScan: (text, el, info) => window.wizardTookScan(text, el, info),
    });
    // The key journal (review round 2 of Group 66). Its keydown listener is added after
    // the capture's, on the same node and phase, so it runs after it: a scan's Enter,
    // which the capture takes, opens no record, and the snapshot the capture asked for at
    // this key names the record this key opens.
    const MODIFIERS = ['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'NumLock', 'AltGraph'];
    // The window hears an event last, in the bubble phase (a page with no window events,
    // the node harnesses' stub: the document).
    const lastNode = typeof window.addEventListener === 'function' ? window : document;
    let keyRec = null;          // { rec, target }: the key being typed now, until its keyup
    document.addEventListener('keydown', (e) => {
        if (!match(e.target) || MODIFIERS.includes(e.key)) return;
        _wizNoteKey(e.key);
        _wizKeyDownEnd();
        _wizKeyInputEnd();
        const rec = { seq: _wizKeySeq++, changes: [] };
        _wizKeyJournal.push(rec);
        if (_wizKeyJournal.length > WIZ_KEY_JOURNAL_MAX) _wizKeyJournal.splice(0, _wizKeyJournal.length - WIZ_KEY_JOURNAL_MAX);
        keyRec = { rec, target: e.target };
        const open = { rec, target: e.target, img: _wizScanImage(e.target) };
        _wizKeyDown = open;
        // Only for a keydown whose dispatch a handler stopped before the window heard it.
        setTimeout(() => { if (_wizKeyDown === open) _wizKeyDownEnd(); }, 0);
    }, true);
    // What a key's keydown did ends with its own dispatch, once every listener has heard it
    // (review round 3, R3-01: it ended at a 0 ms timer for a key the box took nothing from,
    // and an answer queued meanwhile was journaled as that key's, and undone).
    lastNode.addEventListener('keydown', (e) => {
        if (_wizKeyDown && e.target === _wizKeyDown.target) _wizKeyDownEnd();
    });
    // The key's text going into its box: a phase of its own, from its beforeinput (heard
    // first here) to its input (heard last), into the key's record. A real keyboard can
    // deliver it in a task of its own; anything that lands between the two isn't the key's.
    lastNode.addEventListener('beforeinput', (e) => {
        if (!keyRec || e.target !== keyRec.target) return;
        _wizKeyDownEnd();
        _wizKeyInputEnd();
        const open = { rec: keyRec.rec, target: e.target, img: _wizScanImage(e.target) };
        _wizKeyInput = open;
        setTimeout(() => { if (_wizKeyInput === open) _wizKeyInputEnd(); }, 0);
    }, true);
    // An `input` with no beforeinput before it (a key sent by a script, which fires none)
    // opens the phase as it starts, before any listener of the page has heard it: the box's
    // own text has changed by then (the scan capture puts that box back itself), what the
    // page's listeners do (the changed flag, the post-create lock, the touched sets) is
    // still the key's.
    lastNode.addEventListener('input', (e) => {
        if (_wizKeyInput || !keyRec || e.target !== keyRec.target) return;
        _wizKeyDownEnd();
        const open = { rec: keyRec.rec, target: e.target, img: _wizScanImage(e.target) };
        _wizKeyInput = open;
        setTimeout(() => { if (_wizKeyInput === open) _wizKeyInputEnd(); }, 0);
    }, true);
    lastNode.addEventListener('input', (e) => {
        if (_wizKeyInput && e.target === _wizKeyInput.target) _wizKeyInputEnd();
        if (_wizKeyDown && e.target === _wizKeyDown.target) _wizKeyDownEnd();
    });
    // A keyup's own listeners (the weight grid works its sums out on keyup), journaled
    // into the last key's record.
    document.addEventListener('keyup', (e) => {
        if (!match(e.target) || MODIFIERS.includes(e.key)) return;
        _wizKeyDownEnd();
        _wizKeyInputEnd();
        const rec = _wizKeyJournal[_wizKeyJournal.length - 1];
        _wizKeyUp = rec ? { rec, target: e.target, img: _wizScanImage(e.target) } : null;
    }, true);
    lastNode.addEventListener('keyup', () => {
        const o = _wizKeyUp;
        _wizKeyUp = null;
        keyRec = null;
        if (o) _wizScanDiff(o.rec, o.img, _wizScanImage(o.target));
    });
    // A click away from the box ends a label's ':' rule (its keys went elsewhere).
    document.addEventListener('focusout', (e) => { if (match(e.target)) _wizKeysText = ''; }, true);
})();

// --- DATA FETCHERS ---
const wizardFetchMaterials = () => {
    return fetch('/api/filaments')
        .then(r => r.json())
        .then(d => {
            if (d.success && d.filaments) {
                // Cache the full filament list for the duplicate-detection check in
                // the per-spool Prusament scan flow (see findFilamentMatches).
                wizardState.allFilaments = d.filaments;
                const materials = [...new Set(d.filaments.map(f => f.material).filter(Boolean))].sort(function (a, b) {
                    return a.toLowerCase().localeCompare(b.toLowerCase());
                });
                wizardState.materials = materials;
                const dropdown = document.getElementById('dropdown-material');
                if (dropdown) {
                    // A material is Spoolman's free text: HTML text here, and the pick
                    // reads it back from data-value, never from a JS string in the
                    // handler (Group 54 review, S2: a quote or '<' cut it short).
                    dropdown.innerHTML = materials.map(m =>
                        `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option"
                              data-value="${_wizEscape(m)}"
                              onmousedown="window.wizardMaterialSelect(event, this.dataset.value)">${_wizEscape(m)}</div>`
                    ).join('');
                }
            }
        });
};

window.wizardMaterialFocus = () => {
    const dropdown = document.getElementById('dropdown-material');
    if (dropdown) {
        dropdown.style.display = 'block';
        if (window.wizardMaterialFilter) window.wizardMaterialFilter();
    }
};

window.wizardMaterialBlur = () => {
    setTimeout(() => {
        const dropdown = document.getElementById('dropdown-material');
        if (dropdown) dropdown.style.display = 'none';
    }, 150);
};

window.wizardMaterialFilter = () => {
    const input = document.getElementById('wiz-fil-material');
    const dropdown = document.getElementById('dropdown-material');
    if (!input || !dropdown) return;
    const qs = input.value.toLowerCase();
    
    let hasVisible = false;
    Array.from(dropdown.children).forEach(option => {
        option.classList.remove('active', 'bg-primary');
        if (option.innerText.toLowerCase().includes(qs)) {
            option.style.display = 'block';
            hasVisible = true;
        } else {
            option.style.display = 'none';
        }
    });
    dropdown.style.display = hasVisible ? 'block' : 'none';
};

window.wizardMaterialKeydown = (event) => {
    const input = document.getElementById('wiz-fil-material');
    const dropdown = document.getElementById('dropdown-material');
    if (!input || !dropdown || dropdown.style.display === 'none') {
        if (event.key === 'Enter') event.preventDefault();
        return;
    }

    // Escape closes the suggestion dropdown only — without stopPropagation it
    // bubbles to the wizard modal and Bootstrap dismisses the whole wizard,
    // discarding in-progress data. Matches inv_details.js combobox pattern.
    if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        dropdown.style.display = 'none';
        return;
    }

    let visibleOptions = Array.from(dropdown.children).filter(el => el.style.display !== 'none');

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!visibleOptions.length) return;
        event.preventDefault();

        let currentIndex = visibleOptions.findIndex(el => el.classList.contains('active'));
        visibleOptions.forEach(el => el.classList.remove('active', 'bg-primary'));

        if (event.key === 'ArrowDown') {
            currentIndex = currentIndex + 1 >= visibleOptions.length ? 0 : currentIndex + 1;
        } else {
            currentIndex = currentIndex - 1 < 0 ? visibleOptions.length - 1 : currentIndex - 1;
        }

        const nextActive = visibleOptions[currentIndex];
        nextActive.classList.add('active', 'bg-primary');

        const dropRect = dropdown.getBoundingClientRect();
        const itemRect = nextActive.getBoundingClientRect();
        if (itemRect.bottom > dropRect.bottom) {
            dropdown.scrollTop += (itemRect.bottom - dropRect.bottom);
        } else if (itemRect.top < dropRect.top) {
            dropdown.scrollTop -= (dropRect.top - itemRect.top);
        }
        return;
    }

    if (event.key === 'Enter') {
        event.preventDefault();
        if (visibleOptions.length > 0) {
            let selected = visibleOptions.find(el => el.classList.contains('active')) || visibleOptions[0];
            window.wizardMaterialSelect(event, selected.innerText);
        }
    }
};

window.wizardMaterialSelect = (event, value) => {
    event.preventDefault();
    const input = document.getElementById('wiz-fil-material');
    if (input) {
        input.value = value;
        input.focus();
        if (window.wizardAutoUpdateDensity) window.wizardAutoUpdateDensity();
    }
    const dropdown = document.getElementById('dropdown-material');
    if (dropdown) dropdown.style.display = 'none';
};

// --- DATA FETCHERS ---
// Group 66.1: the newest read sent wins (a manufacturer saved over the wizard reads the
// list again, and an older answer arriving last put the old record back), and a read
// that fails (FCC's 502, or no answer) keeps the list as it was. Answers whether this
// read set the list.
let _wizVendorReadSeq = 0;
const wizardFetchVendors = () => {
    const seq = ++_wizVendorReadSeq;
    return fetch('/api/external/vendors')
        .then(r => r.json())
        .then(d => window.wizardAfterLabel(() => {
            if (seq !== _wizVendorReadSeq) return false;
            if (!d || !d.success || !Array.isArray(d.vendors)) return false;
            wizardState.vendors = d.vendors;
            _wizBindVendorCombobox();
            return true;
        }));
};

// The Vendor box's list, drawn from wizardState.vendors.
const _wizBindVendorCombobox = () => {
    const items = [{ value: '', label: '-- Generic --' }].concat(
        (wizardState.vendors || []).filter(v => v && v.id != null)
            .map(v => ({ value: String(v.id), label: v.name || '' }))
    );
    window.wizardBindCombobox({
        searchId: 'wiz-fil-vendor-search',
        hiddenId: 'wiz-fil-vendor-sel',
        dropdownId: 'dropdown-vendor',
        items,
        placeholder: '-- Generic --'
    });
    // Group 6.2: show ✏️ (open Vendor Edit modal) only when an
    // existing vendor is selected; the ➕ (toggle add-new mode)
    // button stays visible always. wizardBindCombobox + the change
    // dispatch added to wizardComboboxSet both fire on the hidden
    // input, so a single listener covers user picks AND
    // programmatic writes (external import, edit-mode auto-fill,
    // clone). The hidden input survives wizardBindCombobox's clone
    // dance (only wiz-fil-vendor-search is cloned), so this
    // listener stays bound across re-fetches.
    _wizardBindVendorEditBtn();
};

// Group 66.1: names compare as the server's do (spoolman_api.vendor_name_key: trimmed,
// inner spaces made one, any case); a name two manufacturers share gives the lowest id.
const _wizVendorKey = (s) => String(s == null ? '' : s).split(/\s+/).filter(Boolean).join(' ').toLowerCase();
const _wizVendorNamed = (name) => {
    const key = _wizVendorKey(name);
    if (!key) return null;
    return (wizardState.vendors || []).filter(v => v && v.id != null && _wizVendorKey(v.name) === key)
        .reduce((low, v) => (!low || Number(v.id) < Number(low.id) ? v : low), null);
};

const _wizardBindVendorEditBtn = () => {
    const hidden = document.getElementById('wiz-fil-vendor-sel');
    const editBtn = document.getElementById('wiz-fil-vendor-edit-btn');
    if (!hidden || !editBtn) return;
    const refresh = () => {
        editBtn.style.display = hidden.value ? 'inline-block' : 'none';
    };
    if (!hidden.dataset.editBtnBound) {
        hidden.addEventListener('change', refresh);
        hidden.dataset.editBtnBound = '1';
    }
    refresh();
};

// The filament's Spool Wt box shows what `vendor` gives (Group 66.7): its empty weight,
// marked "↩ from vendor", or nothing; the spool's box follows the filament's where it
// follows, and both summaries are drawn again. Code, never the person: this used to
// dispatch a synthetic `input`, which the wizard counted as the person's edit (54.5's
// touched set, so Edit Spool saved the brand's weight as the filament's own) and as an
// unsaved change. The spool's box follows by wizardFilamentEmptyWeightChanged's one rule.
const _wizFilEmptyWeightFromVendor = (vendor) => {
    const { value } = resolveEmptySpoolWeightSource({ vendor });
    window.wizardSetFilEmptyWeightInherited(value, 'vendor');
    window.wizardFilamentEmptyWeightChanged(_wizBoxValue('wiz-fil-empty_weight'));
    if (window.wizardRefreshSectionSummary) {
        window.wizardRefreshSectionSummary('wiz-fil-physical-panel');
        window.wizardRefreshSectionSummary('wiz-spool-weight-panel');
    }
};

// A manufacturer saved or made while the wizard is open (wizardVendorSaved), held by the
// Vendor box: the filament box shows its weight when the box is empty, or shows the
// brand's weight already, and the person hasn't typed in it. A value of the filament's
// own stays, and an empty box stays empty when the brand gives nothing.
const _wizardCascadeVendorEmptyWeight = (vendor) => {
    if (!vendor || !document.getElementById('wiz-fil-empty_weight')) return;
    if (wizardNativeTouched('fil', 'spool_weight')) return;
    const inherited = wizardFilEmptyWeightIsInherited();
    if (!inherited && _wizBoxValue('wiz-fil-empty_weight') !== '') return;
    if (!inherited && resolveEmptySpoolWeight({ vendor }) === null) return;
    _wizFilEmptyWeightFromVendor(vendor);
};

// Group 66.7: a filament box showing its brand's weight follows the manufacturer the
// Vendor box holds (the person's pick, Generic, or a code write: the open, a save). A
// pick never fills an empty box the filament doesn't inherit (a create's Save fills it
// from the brand, as before), and a value of the filament's own, or one the person typed,
// stays. Edit Spool's filament with none of its own inherits even while its brand gives
// nothing, so it follows a pick there too (review round 2 of Group 66, Q2-03), and a key
// typed in the Vendor box that matches no manufacturer (Generic for a moment) no longer
// ends the following (Q2-02).
(function () {
    const hidden = document.getElementById('wiz-fil-vendor-sel');
    if (!hidden) return;
    hidden.addEventListener('change', () => {
        if (!wizardFilEmptyWeightIsInherited()) return;
        _wizFilEmptyWeightFromVendor(_wizSelectedVendor());
    });
})();

// A manufacturer saved or made while the wizard is open (Group 66.1; Derek, 2026-11-11:
// "you have to close out of the modals before updating the vendor data (spool weight)
// gets propagated into the auto fills"). The Vendor Edit window dispatches
// `vendor:updated` ({id, vendor}) after a save and `vendor:created` ({vendor}) after a
// create, and the post-archive prompt's "also the brand's default" dispatches
// `vendor:updated` too. It was heard only when the Vendor box held that manufacturer,
// and then filled only an empty filament box: a new name never reached the box, a new
// weight never reached a box that showed the old one, and New Spool and Clone (whose
// filament form is hidden) never heard it. Now, whatever the Vendor box holds:
//   - the list takes the record at once (the re-read below can fail), and so do the
//     filament records the wizard read (New Spool and Clone follow them);
//   - the Vendor box takes its new name when it holds it, and a create picks it (the ➕
//     made it for this filament);
//   - the filament's Spool Wt box follows it when it shows the brand's weight or is
//     empty, and the spool's box when it shows that manufacturer's weight;
//   - then the list is read again, the newest read winning.
// All of it is code: no box counts as typed in, and a save isn't marked as a change (a
// create the ➕ made is: the person chose it for this filament). The record replaces the
// old one whole: a weight cleared is a key Spoolman leaves out.
window.wizardVendorSaved = (vendor, { created = false } = {}) => {
    if (!vendor || vendor.id == null) return;
    const wizModalEl = document.getElementById('wizardModal');
    if (!wizModalEl || !wizModalEl.classList.contains('show')) return;
    const vid = String(vendor.id);
    const rec = Object.assign({}, vendor);
    const list = Array.isArray(wizardState.vendors) ? wizardState.vendors.slice() : [];
    const at = list.findIndex(x => x && String(x.id) === vid);
    if (at >= 0) list[at] = rec; else list.push(rec);
    wizardState.vendors = list;
    [wizardState.existingFilaments, wizardState.allFilaments].forEach((fl) => {
        if (!Array.isArray(fl)) return;
        fl.forEach((f) => { if (f && f.vendor && String(f.vendor.id) === vid) f.vendor = Object.assign({}, rec); });
    });
    _wizBindVendorCombobox();
    const hidden = document.getElementById('wiz-fil-vendor-sel');
    if (created || (hidden && hidden.value === vid)) {
        window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', vid, rec.name || '');
        _wizardCascadeVendorEmptyWeight(rec);
    }
    // A manufacturer made with the ➕ and picked here is the person's choice for this
    // filament (review round 2 of Group 66, Q4-05): the form has an unsaved change, so a
    // close or an opener asks first. Its weight still fills as code (no box touched).
    if (created && window.wizardMarkChanged) window.wizardMarkChanged();
    if (wizardState.spoolEmptyWeightFrom === 'vendor' && wizardState.spoolEmptyWeightVendorId === vid
            && !wizardNativeTouched('spool', 'spool_weight')) {
        _wizSpoolEmptyWeightFrom({ filamentWt: null, vendor: rec });
    }
    wizardFetchVendors().catch(() => false);
};

document.addEventListener('vendor:created', (e) => {
    window.wizardVendorSaved(e && e.detail ? e.detail.vendor : null, { created: true });
});
document.addEventListener('vendor:updated', (e) => {
    const d = (e && e.detail) || {};
    if (!d.vendor) return;
    window.wizardVendorSaved(Object.assign({}, d.vendor, { id: d.vendor.id != null ? d.vendor.id : d.id }));
});

// Group 66.9: a manufacturer merged away while the wizard is open (vendor:merged
// {from, into, vendor}, inv_vendor_merge.js). The one merged is deleted from Spoolman and
// its filaments are the kept one's now, so nothing in the wizard may hold its id (Edit
// Spool sends its filament whole, with the Vendor box's id): the list drops it and takes
// the kept record; the filament records the wizard read take the kept one; the Vendor box
// holding it holds the kept one; and the edit's baselines follow (editFilamentOriginal's
// vendor_id, spoolEmptyWeightVendorId), so Save sends no manufacturer change and asks no
// label reprint for a filament the merge already moved. All of it is code (no box counts
// as typed in). The vendor:updated sent after it redraws what comes from the kept one.
window.wizardVendorMerged = (detail) => {
    const d = detail || {};
    const gone = d.from != null ? String(d.from) : '';
    const kept = d.into != null ? String(d.into) : '';
    if (!gone || !kept || gone === kept) return;
    const wizModalEl = document.getElementById('wizardModal');
    if (!wizModalEl || !wizModalEl.classList.contains('show')) return;
    const rec = d.vendor && d.vendor.id != null ? Object.assign({}, d.vendor) : null;
    const list = (Array.isArray(wizardState.vendors) ? wizardState.vendors : []).filter(x => !x || String(x.id) !== gone);
    if (rec) {
        const at = list.findIndex(x => x && String(x.id) === kept);
        if (at >= 0) list[at] = rec; else list.push(rec);
    }
    wizardState.vendors = list;
    [wizardState.existingFilaments, wizardState.allFilaments].forEach((fl) => {
        if (!Array.isArray(fl)) return;
        fl.forEach((f) => {
            if (f && f.vendor && String(f.vendor.id) === gone) {
                f.vendor = rec ? Object.assign({}, rec) : Object.assign({}, f.vendor, { id: Number(kept) });
            }
        });
    });
    const merges = wizardState.vendorMerges || (wizardState.vendorMerges = {});
    Object.keys(merges).forEach((k) => { if (merges[k] === gone) merges[k] = kept; });
    merges[gone] = kept;
    const orig = wizardState.editFilamentOriginal;
    if (orig && String(orig.vendor_id) === gone) {
        wizardState.editFilamentOriginal = Object.assign({}, orig, { vendor_id: kept });
    }
    if (wizardState.spoolEmptyWeightVendorId === gone) wizardState.spoolEmptyWeightVendorId = kept;
    _wizBindVendorCombobox();
    const hidden = document.getElementById('wiz-fil-vendor-sel');
    if (hidden && hidden.value === gone) {
        const search = document.getElementById('wiz-fil-vendor-search');
        window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', kept,
            rec && rec.name ? rec.name : (search ? search.value : ''));
    }
    wizardFetchVendors().catch(() => false);
};
document.addEventListener('vendor:merged', (e) => window.wizardVendorMerged(e && e.detail));

const wizardFetchLocations = () => {
    return fetch('/api/locations')
        .then(r => r.json())
        .then(d => window.wizardAfterLabel(() => {
            if (!Array.isArray(d)) return;
            wizardState.allLocationRows = d.filter(loc => loc && typeof loc === 'object');
            // Same filter the select used to apply: hide toolheads (window.isToolheadType:
            // a custom Type that only holds a head's word, "Toolbox", is offered) and the
            // virtual "Unassigned" row (that's the empty-string default).
            const valid = d.filter(loc => {
                const type = (loc.Type || '').toLowerCase();
                if (window.isToolheadType(loc.Type) || type === 'virtual') return false;
                // L271 Phase 5: Wall Shelf/Row are structural grouping nodes —
                // they nest children but never hold spools, so don't offer them
                // as spool-assignment targets (Section, the leaf, IS offered).
                if (type === 'wall shelf' || type === 'row') return false;
                if (loc.LocationID === 'Unassigned') return false;
                return true;
            });
            wizardState.locations = valid;
            // 13.4 — include LocationID in the visible label so typing a LOC
            // value (e.g. "LR-MDB-1") matches via wizardBindCombobox's
            // label-substring filter. Mirrors the force-location modal's
            // `Name (LocationID)` convention so the dashboard's location
            // pickers stay visually consistent.
            const items = [{ value: '', label: '-- Unassigned --' }].concat(
                valid.map(loc => ({
                    value: loc.LocationID,
                    label: loc.Name ? `${loc.Name} (${loc.LocationID})` : loc.LocationID,
                }))
            );
            window.wizardBindCombobox({
                searchId: 'wiz-spool-location-search',
                hiddenId: 'wiz-spool-location',
                dropdownId: 'dropdown-location',
                items,
                placeholder: 'Unassigned (default)',
                // Group 40.7 (Derek's answer 7): a multi-slot box or a printer
                // opens its picker; its answer waits for Save.
                onPick: (value, label, before) => window.wizardLocationPicked(value, before),
            });
            window.wizardWatchLocationPick();
        }));
};

// Group 40.7 review (wizard-stale-pick-via-reopens-picker): a held picker choice
// lives only while the Location field's value is its place. Typing, backspacing
// or a Tab to another item changes the value without a pick (onPick isn't
// called), and the choice used to survive: a create with the field emptied then
// opened the abandoned box's picker for every new spool. Bound once on the
// hidden input, which survives wizardBindCombobox's clone of the text input;
// every writer of the value dispatches `change` on it.
window.wizardWatchLocationPick = () => {
    const hidden = document.getElementById('wiz-spool-location');
    if (!hidden || (hidden.dataset && hidden.dataset.pickWatch)) return;
    if (hidden.dataset) hidden.dataset.pickWatch = '1';
    hidden.addEventListener('change', () => {
        const p = wizardState.pendingPlacement;
        if (p && _wizLocKey(p.location) !== _wizLocKey(hidden.value)) wizardState.pendingPlacement = null;
    });
};

// Spool extras the wizard edits through inputs of its own: the Purchase and
// Product Link fields in Metadata (#wiz-spool-purchase_url / -product_url).
// Never rendered as a dynamic Spool Extras field as well, and never collected
// from one: the collector read the dynamic copy AFTER the dedicated input, so a
// link the user emptied (or a new one typed) was overwritten by the copy's old
// value, and the save changed nothing (2026-10-21).
const WIZ_SPOOL_EXTRAS_OWN_INPUT = ['purchase_url', 'product_url'];
// Spool extras the dynamic Spool Extras section never shows: the ones above,
// plus the label flag and the move engine's own slot / trail keys.
const WIZ_SPOOL_EXTRAS_HIDDEN = ['needs_label_print', 'physical_source', 'physical_source_slot',
    'container_slot', ...WIZ_SPOOL_EXTRAS_OWN_INPUT];
window.wizardSpoolExtraShown = (key) => !WIZ_SPOOL_EXTRAS_HIDDEN.includes(key);

// Records that the user changed a dynamic extra: an input or select of the
// Filament Extras (.dynamic-extra-field) or Spool Extras (.dynamic-extra-spool-
// field), or a chip (its box says which entity). Edit mode clears only these.
window.wizardNoteExtraTouched = (el) => {
    if (!el || typeof el.getAttribute !== 'function' || !el.classList) return;
    const key = el.getAttribute('data-key');
    if (!key) return;
    let entity = null;
    if (el.classList.contains('dynamic-extra-field')) entity = 'fil';
    else if (el.classList.contains('dynamic-extra-spool-field')) entity = 'spool';
    else if (el.classList.contains('dynamic-chip')) {
        const box = el.closest ? el.closest('[id^="chip-container-"]') : null;
        const m = box ? /^chip-container-(fil|spool)-/.exec(box.id) : null;
        entity = m ? m[1] : null;
    }
    if (entity) wizardState.touchedExtras.add(`${entity}:${key}`);
};
const wizardExtraTouched = (entity, key) =>
    !!(wizardState.touchedExtras && wizardState.touchedExtras.has(`${entity}:${key}`));

// Group 54.5: the plain (not extra) number boxes Edit Spool can clear: box id →
// "<entity>:<key>", the payload key it fills. Spoolman takes a JSON null for each
// and drops the value (dev's 0.27.1, 2026-11-09). Initial and used weight stay out
// on purpose: an emptied initial weight would be a weight write (update_spool's
// archive edge reads it), and an emptied used weight already sends 0.
const WIZ_NATIVE_CLEARABLE = {
    'wiz-spool-price': 'spool:price',
    'wiz-spool-empty_weight': 'spool:spool_weight',
    'wiz-fil-empty_weight': 'fil:spool_weight',
    'wiz-fil-settings_extruder_temp': 'fil:settings_extruder_temp',
    'wiz-fil-settings_bed_temp': 'fil:settings_bed_temp',
    // Review round 1 of Group 66 (R3-03): the two max temps (extras), so Edit Spool clears one
    // only when the person emptied it. Sent for every blank box, the clear undid a matched
    // Prusament scan's fill made while the wizard was open.
    'wiz-fil-nozzle_temp_max': 'fil:nozzle_temp_max',
    'wiz-fil-bed_temp_max': 'fil:bed_temp_max',
};
// Records that the user changed one of those boxes (the wizard's `input`
// listener). A value set by code fires no event, so a box the page filled or
// blanked itself (the edit's prefill, the filament empty weight's copy into the
// spool's) is never touched. The vendor push's own input event only ever fills a
// blank box with a value, so it can't make a clear.
window.wizardNoteNativeTouched = (el) => {
    const id = el && el.id;
    if (id && Object.prototype.hasOwnProperty.call(WIZ_NATIVE_CLEARABLE, id)) {
        wizardState.touchedNative.add(WIZ_NATIVE_CLEARABLE[id]);
    }
};
// Whether the user changed that box in this session ('spool', 'price'): the plain
// boxes' twin of wizardExtraTouched.
const wizardNativeTouched = (entity, key) =>
    !!(wizardState.touchedNative && wizardState.touchedNative.has(`${entity}:${key}`));
// Edit mode: the user emptied that box, so Save sends null and the field is
// cleared. Never for a box holding a number half typed ("-", "1e"): a number box
// reads '' while it shows that text (validity.badInput), and the field is left
// as it is, as before.
const wizardNativeCleared = (entity, key) => {
    if (wizardState.mode !== 'edit_spool' || !wizardNativeTouched(entity, key)) return false;
    const id = Object.keys(WIZ_NATIVE_CLEARABLE).find(k => WIZ_NATIVE_CLEARABLE[k] === `${entity}:${key}`);
    const el = id ? document.getElementById(id) : null;
    return !!el && el.value === '' && !(el.validity && el.validity.badInput);
};

// Edit mode: every multi-choice (chip) Filament Extras field the form shows
// that the user emptied is sent as cleared (window.FCC_DELETE_EXTRA). The chip
// collector sends only fields that still have chips, and a key left out keeps
// its old list, so removing the last chip changed nothing (2026-10-21). A field
// the form doesn't show (no chip box), or one the user didn't touch (a box the
// page drew empty), is left alone.
window.wizardClearEmptyChipFields = (extra) => {
    (wizardState.extraFields?.filament || []).forEach(f => {
        if (!f || f.field_type !== 'choice' || !f.multi_choice) return;
        if (Object.prototype.hasOwnProperty.call(extra, f.key)) return;
        if (!document.getElementById(`chip-container-fil-${f.key}`)) return;
        if (!wizardExtraTouched('fil', f.key)) return;
        extra[f.key] = window.FCC_DELETE_EXTRA;
    });
    return extra;
};

const wizardFetchExtraFields = () => {
    return fetch('/api/external/fields')
        .then(r => r.json())
        .then(d => window.wizardAfterLabel(() => {
            if (d.success && d.fields) {
                wizardState.extraFields = d.fields;

                // --- FILAMENT CUSTOM FIELDS ---
                const fContainer = document.getElementById('wiz-fil-dynamic-extra-fields');
                fContainer.innerHTML = '';

                if (d.fields.filament) {
                    d.fields.filament.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.filament.forEach(field => {
                        // Hide legacy/system fields, plus the two max-temp keys —
                        // those have dedicated static inputs (#wiz-fil-nozzle_temp_max
                        // and #wiz-fil-bed_temp_max) so a second dynamic input would
                        // race the static one on save and re-send a raw numeric value
                        // that Spoolman rejects.
                        // Group 10.4 — purchase_url is intentionally hidden from
                        // the wizard's filament tab. The user edits the spool's
                        // purchase_url instead, which falls back to the filament's
                        // value on read when blank (inv_details.js:168). To edit
                        // the filament-level value directly, use the Edit
                        // Filament modal.
                        //
                        // L144 / 17.1 round 2: `needs_label_print` UN-hidden so it
                        // surfaces alongside `sample_printed` as a boolean checkbox
                        // in the wizard's Filament Extras section. Both flags are
                        // already registered in setup_fields.py (filament_standards)
                        // so the dynamic-field renderer turns them into proper
                        // toggle inputs without bespoke per-field UI. The display
                        // side (badges on Filament Details modal) shipped in
                        // 17.1 round 1. `label_printed` (the legacy retired key)
                        // stays hidden — it's gone in M7+ data.
                        // "Excluded" (2026-10-20) is set from the ⚠️ Low
                        // stock list, which checks the reason and keeps the day.
                        if (['sheet_link', 'price_total', 'spoolman_reprint', 'label_printed',
                             'nozzle_temp_max', 'bed_temp_max', 'purchase_url',
                             'fcc_stock_excluded', 'fcc_stock_excluded_note', 'fcc_stock_excluded_at'].includes(field.key)) return;

                        let html = wizardGenerateFieldHTML(field, 'fil');
                        if (html) fContainer.innerHTML += html;
                    });
                }

                // --- SPOOL CUSTOM FIELDS ---
                const sContainer = document.getElementById('wiz-spool-dynamic-extra-fields');
                if (sContainer && d.fields.spool) {
                    sContainer.innerHTML = '';
                    d.fields.spool.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.spool.forEach(field => {
                        if (!window.wizardSpoolExtraShown(field.key)) return;

                        // If Temp Resistance is still 'text' in Spoolman, hide it so they can change it to Choice later
                        if (field.key === 'spool_temp' && field.field_type === 'text') return;

                        let html = wizardGenerateFieldHTML(field, 'spool');
                        if (html) sContainer.innerHTML += html;
                    });
                }

                // 🌟 After DOM generation, initialize the live Sync Bindings
                wizardSetupFieldSync();
                // Group 10.1 Session C polish: move original_color into the
                // Color panel and hide shore_hardness unless material is TPU.
                if (window.wizardRelocateOriginalColorField) window.wizardRelocateOriginalColorField();
                if (window.wizardApplyShoreHardnessGate) window.wizardApplyShoreHardnessGate();
                if (window.wizardRefreshAllSectionSummaries) window.wizardRefreshAllSectionSummaries();
            }
        }));
};

// The filament's Spool Wt box changed (typed, emptied, or filled by code): the spool's
// box shows it, by one rule in every mode (Group 54 review's S1 for Edit Spool; Group
// 66.5 for the rest, which made a plain copy). Never over a value of the spool's own (an
// edit's, a clone's source spool's, the weigh window's tare), which a correction of its
// filament's used to replace (Derek, L349: "as long as we aren't overwriting
// filaments/spools that have data for that field"), or over a box the person typed in or
// emptied. A box that shows what the spool inherits (its badge), or nothing, shows what
// it inherits now: the filament's value "↩ from filament", else its brand's "↩ from
// vendor", or nothing. New spools still take what their box shows as their own (L34),
// and Edit Spool's Save still leaves an inherited one out (54.8). Under Existing Filament
// the filament form is hidden and Save doesn't use it: the selected filament drives the
// box there (wizardFollowFilament).
window.wizardFilamentEmptyWeightChanged = (value) => {
    const spoolEmptyWt = document.getElementById('wiz-spool-empty_weight');
    if (!spoolEmptyWt) return;
    if (wizardState.mode === 'existing') return;
    if (!_wizEmptyWeightFollowsFilament()) return;     // typed in, emptied, or the spool's own
    // Group 66.7: a filament box that shows its brand's weight is no value of the
    // filament's: the spool's box says "↩ from vendor", as Edit Spool's open does.
    _wizSpoolEmptyWeightFrom({
        filamentWt: wizardFilEmptyWeightIsInherited() ? null : value,
        vendor: _wizSelectedVendor(),
    });
};

window.wizardSetupFieldSync = () => {
    // Empty weight static propagation (wizardFilamentEmptyWeightChanged). Bound once:
    // wizardFetchExtraFields runs this at every open, and both boxes are the
    // template's own, so each open used to add another copy of the listener.
    const filEmptyWt = document.getElementById('wiz-fil-empty_weight');
    if (filEmptyWt && filEmptyWt.dataset && !filEmptyWt.dataset.fccEmptyWeightSync) {
        filEmptyWt.dataset.fccEmptyWeightSync = '1';
        // Group 66.7: the person's edit is noted first. This listener, on the box itself,
        // runs before the wizard's delegated one that notes it, and the copy reads the
        // marks: one `input` over the brand's weight (a paste) still read as the brand's.
        // `input` only (Group 66.5, as 54.5's touched set): a number box fires it for every
        // change a person makes, and its `change` at blur only repeats one, while Chromium
        // still fires it in the next session for an edit made before the reset when the box
        // kept the focus, which ran the copy against the new spool's box (emptying New
        // Spool's inherited weight).
        filEmptyWt.addEventListener('input', (e) => {
            window.wizardNoteNativeTouched(e.target);
            window.wizardRefreshFilEmptyWeightMark();
            window.wizardFilamentEmptyWeightChanged(e.target.value);
        });
    }

    // Lock all auto-synced Spool fields on initial render
    document.querySelectorAll('.wizard-sync-btn.active-sync').forEach(btn => {
        const spoolKey = btn.getAttribute('data-sync-target');
        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
        if (targetEl) {
            targetEl.setAttribute('readonly', 'true');
            targetEl.style.opacity = '0.7';
        }
    });

    // Find all Filament inputs that could act as Sync Sources
    const sources = document.querySelectorAll('.sync-source-fil');

    sources.forEach(sourceEl => {
        // We listen to input (typing) and change (select dropdowns/checkboxes/chips)
        ['input', 'change'].forEach(evtType => {
            sourceEl.addEventListener(evtType, (e) => {
                const filKey = e.target.getAttribute('data-key');
                if (!filKey) return;

                // Find ALL active Spool sync buttons that are linked to this filament key
                const syncBtns = document.querySelectorAll('.wizard-sync-btn.active-sync');

                syncBtns.forEach(btn => {
                    const linkedTo = btn.getAttribute('data-linked-fil-key');
                    if (linkedTo === filKey) {
                        const spoolKey = btn.getAttribute('data-sync-target');
                        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
                        if (targetEl) {
                            // Mirror the value based on input type
                            if (e.target.type === 'checkbox') {
                                targetEl.checked = e.target.checked;
                            } else {
                                targetEl.value = e.target.value;
                            }
                        }
                    }
                });
            });
        });
    });
};

window.wizardToggleFieldSync = (spoolKey) => {
    const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
    const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);

    if (!btn || !targetEl) return;

    let spoolName = spoolKey;
    if (wizardState.extraFields?.spool) {
        const schema = wizardState.extraFields.spool.find(f => f.key === spoolKey);
        if (schema) spoolName = schema.name;
    }

    if (btn.classList.contains('active-sync')) {
        // BREAK THE LINK
        btn.classList.remove('active-sync');
        btn.classList.replace('btn-outline-info', 'btn-outline-secondary');
        btn.innerText = '🔗';
        btn.style.opacity = '0.5';
        btn.title = "Unlinked. Click to sync with a Filament field.";

        targetEl.removeAttribute('readonly');
        targetEl.style.opacity = '1';

        showToast(`Unlinked ${spoolName}`, "info");
    } else {
        // RESTORE OR CREATE THE LINK
        const filKey = btn.getAttribute('data-linked-fil-key');
        if (!filKey) {
            // Prompt user to select a field
            window.wizardPromptFieldSync(spoolKey);
            return;
        }

        btn.classList.add('active-sync');
        btn.classList.replace('btn-outline-secondary', 'btn-outline-info');
        btn.innerText = '🔗';
        btn.style.opacity = '1';

        targetEl.setAttribute('readonly', 'true');
        targetEl.style.opacity = '0.7';

        // Find the source filament element to pull initial value
        const sourceEl = document.getElementById(`wiz_fil_ef_${filKey}`);
        if (sourceEl) {
            if (sourceEl.type === 'checkbox') targetEl.checked = sourceEl.checked;
            else targetEl.value = sourceEl.value;
        }

        let filName = filKey;
        if (wizardState.extraFields?.filament) {
            const schema = wizardState.extraFields.filament.find(f => f.key === filKey);
            if (schema) filName = schema.name;
        }

        btn.title = `Synced with Filament's ${filName}. Click to unlink.`;
        showToast(`Synced ${spoolName} with ${filName}`, "success");
    }
};

window.wizardPromptFieldSync = (spoolKey) => {
    let inputOptions = {};
    if (wizardState.extraFields && wizardState.extraFields.filament) {
        wizardState.extraFields.filament.forEach(f => {
            inputOptions[f.key] = f.name;
        });
    }

    // Group 10.8 — was nested Swal.fire; now mountOverlay so it survives
    // Bootstrap's focus trap and doesn't shift the wizard scrollbar comp.
    const wizModalEl = document.getElementById('wizardModal');
    const optsHtml = Object.entries(inputOptions)
        .map(([k, v]) => `<option value="${String(k).replace(/"/g, '&quot;')}">${String(v).replace(/</g, '&lt;')}</option>`)
        .join('');
    const panelHtml = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #17a2b8; border-radius:8px; padding:20px 24px; max-width:32.5rem; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">🔗 Link Field</div>
            <div style="color:#ffc; margin-bottom:12px;">Select a Filament field to synchronize with this Spool field:</div>
            <select id="fcc-wiz-fieldsync-sel" class="form-select form-select-sm bg-dark text-white border-secondary mb-3" style="width:100%;">
                <option value="" disabled selected>-- Select a Field --</option>
                ${optsHtml}
            </select>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-fieldsync-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-fieldsync-confirm" class="btn btn-info btn-sm" style="min-width:120px;">Link</button>
            </div>
        </div>
    `;
    const handle = window.mountOverlay({
        id: 'fcc-wiz-fieldsync',
        content: panelHtml,
        host: wizModalEl,
        initialFocus: '#fcc-wiz-fieldsync-sel',
    });
    const sel = handle.element.querySelector('#fcc-wiz-fieldsync-sel');
    const commit = () => {
        const val = sel?.value;
        handle.cleanup();
        if (!val) return;
        const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
        if (btn) {
            btn.setAttribute('data-linked-fil-key', val);
            window.wizardToggleFieldSync(spoolKey);
        }
    };
    handle.element.querySelector('#fcc-wiz-fieldsync-confirm')?.addEventListener('click', commit);
    handle.element.querySelector('#fcc-wiz-fieldsync-cancel')?.addEventListener('click', () => handle.cleanup());
    sel?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
};

const wizardGenerateFieldHTML = (field, entityType) => {
    let syncHtml = '';
    // If we're rendering a Spool field, check if a Filament field with the exact same key exists
    if (entityType === 'spool' && wizardState.extraFields?.filament) {
        const hasMatchingFilamentField = wizardState.extraFields.filament.some(f => f.key === field.key);
        if (hasMatchingFilamentField) {
            // Default to synced (active) state
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-info p-0 ms-2 border-0 wizard-sync-btn active-sync" 
                            data-sync-target="${field.key}" 
                            data-linked-fil-key="${field.key}"
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Synced with Filament's ${field.name}. Click to unlink."
                            style="font-size: var(--fcc-fs-label); line-height: 1;">🔗</button>`;
        } else {
            // Unsynced state, user can click to map it manually
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-secondary p-0 ms-2 border-0 wizard-sync-btn" 
                            data-sync-target="${field.key}"
                            data-linked-fil-key=""
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Click to link this field to a Filament field."
                            style="font-size: var(--fcc-fs-label); line-height: 1; opacity: 0.5;">🔗</button>`;
        }
    }

    // data-extra-key lets the Session-C polish hooks (TPU gate on
    // shore_hardness, original_color relocation into the Color panel) find
    // the wrapper without grepping the inner input id.
    let html = `<div class="col-md-6 mb-2" data-extra-key="${field.key}"><label class="form-label small text-secondary mb-1 d-flex align-items-center">${field.name}${syncHtml}</label>`;
    const dataClass = entityType === 'fil' ? 'dynamic-extra-field' : 'dynamic-extra-spool-field';
    // Add an ID for easy targeting by the sync logic
    const inputId = `wiz_${entityType}_ef_${field.key}`;

    if (field.field_type === 'choice' && field.multi_choice) {
        // Custom Searchable Tag/Chip System (Replaces Native Datalist).
        // Wrapped in a flex row so the ➕ "add new option" button sits to the
        // RIGHT of the chip box — parity with the single-choice path below,
        // which always had a ➕ while the multi-choice path was missing it (the
        // widget's own suggestion toast already told users to "use the ➕
        // button"). The ➕ opens wizardPromptNewChoice, which is multi-choice
        // aware: it drops a chip in place on success instead of refetching the
        // schema (a refetch would wipe the in-progress wizard DOM).
        html += `<div class="d-flex align-items-stretch gap-1">
                    <div class="position-relative wizard-chip-multiselect flex-grow-1" id="wizard-ms-${entityType}-${field.key}">
                    <div class="form-control bg-dark text-white border-secondary d-flex flex-wrap align-items-center gap-1 p-1" style="min-height: 38px; cursor: text;" onclick="document.getElementById('${inputId}').focus()">
                        <div class="chip-container d-flex flex-wrap gap-1" id="chip-container-${entityType}-${field.key}"></div>
                        <input type="text"
                               class="border-0 bg-transparent text-white flex-grow-1 chip-input sync-source-${entityType}"
                               id="${inputId}"
                               data-key="${field.key}"
                               placeholder="Search or type new..."
                               autocomplete="off"
                               style="outline: none; min-width: 120px;"
                               onfocus="wizardMultiselectFocus('${entityType}', '${field.key}')"
                               onblur="wizardMultiselectBlur('${entityType}', '${field.key}')"
                               oninput="wizardMultiselectFilter('${entityType}', '${field.key}')"
                               onkeydown="wizardMultiselectKeydown(event, '${entityType}', '${field.key}')">
                    </div>
                    <div class="autocomplete-dropdown position-absolute w-100 bg-dark border border-secondary rounded shadow-lg"
                         id="dropdown-${entityType}-${field.key}"
                         style="display: none; top: 100%; left: 0; z-index: 1050; max-height: 200px; overflow-y: auto;">`;

        // Populate the dropdown with initial options. A pick reads its option back by
        // its text, so each choice is HTML text here, never markup (Group 54 review,
        // S2: a choice holding a quote or '<' came back cut, or with its tags gone).
        field.choices.forEach(c => {
            html += `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option"
                          onmousedown="wizardMultiselectSelect(event, '${entityType}', '${field.key}', this.innerText)">${_wizEscape(c)}</div>`;
        });

        html += `   </div>
                    </div>
                    <button type="button" class="btn btn-outline-secondary wizard-multichoice-add"
                            onmousedown="event.preventDefault()"
                            onclick="wizardPromptNewChoice('${entityType}', '${field.key}')"
                            title="Add a new option to the Spoolman database"
                            aria-label="Add new option"
                            style="flex:0 0 auto;">➕</button>
                 </div>`;

    } else if (field.field_type === 'choice' && !field.multi_choice) {
        html += `<div class="input-group input-group-sm" style="position: relative; z-index: 1;">
                    <select class="form-select bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}">
                        <option value="">-- None --</option>`;
        field.choices.forEach(c => {
            // Escaped (Group 54 review, S2): a quote in a choice cut its value short.
            html += `<option value="${_wizEscape(c)}">${_wizEscape(c)}</option>`;
        });
        html += `   </select>
                    <button class="btn btn-outline-secondary" type="button" 
                            onclick="wizardPromptNewChoice('${entityType}', '${field.key}')" 
                            title="Add new option to Spoolman Database">➕</button>
                 </div>`;

    } else if (field.field_type === 'boolean') {
        html += `<div class="form-check mt-1">
                    <input class="form-check-input ${dataClass} sync-source-${entityType}" type="checkbox" data-key="${field.key}" id="${inputId}">
                    <label class="form-check-label text-white small" for="${inputId}">Enable</label>
                 </div>`;
    } else {
        // Standard text/number input
        html += `<input type="text" class="form-control bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}" autocomplete="off">`;
    }

    html += `</div>`;
    return html;
};

window.wizardAddMultiChoiceChip = (entityType, key, directVal = null) => {
    const inputId = `wiz_${entityType}_ef_${key}`;
    const input = document.getElementById(inputId);
    if (!input) return;
    const rawVal = (directVal !== null ? directVal : input.value).trim();
    if (!rawVal) return;

    const container = document.getElementById(`chip-container-${entityType}-${key}`);
    const apiEntity = entityType === 'fil' ? 'filament' : 'spool';
    const schemas = wizardState.extraFields?.[apiEntity];
    const fieldObj = schemas?.find(f => f.key === key);
    const existingChoices = fieldObj?.choices || [];
    const isExistingExact = existingChoices.includes(rawVal);

    // Group 10.9 — gate new (unknown) values through validateNewChoice.
    // Direct picks from the dropdown bypass the gate (directVal !== null) so
    // existing-choice selections always go through unimpeded.
    let val = rawVal;
    if (directVal === null && !isExistingExact && typeof window.validateNewChoice === 'function') {
        const result = window.validateNewChoice(rawVal, existingChoices);
        if (!result.ok) {
            if (typeof showToast === 'function') {
                showToast(result.error || 'Invalid value', 'warning', 5000);
            }
            return;
        }
        if (result.suggestion) {
            // Silent path (blur/Enter on multiselect) — surface as toast and
            // refuse to commit; user can click the suggested existing choice
            // from the dropdown or use the +Add modal for explicit confirm.
            if (typeof showToast === 'function') {
                showToast(`Did you mean "${result.suggestion}"? — pick it from the list, or use the ➕ button to add "${result.canonical}" as a new value.`, 'info', 7000);
            }
            return;
        }
        val = result.canonical;
    }

    // Duplicate-chip guard after normalization.
    const escapedVal = CSS.escape(val);
    if (container.querySelector(`[data-value="${escapedVal}"]`)) {
        input.value = '';
        return;
    }
    wizardState.isDirty = true;

    const isKnown = existingChoices.includes(val) || isExistingExact;
    if (!isKnown) {
        // Silently push new choice to Spoolman backend config.
        fetch('/api/external/fields/add_choice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: apiEntity, key: key, new_choice: val })
        });
        // We do NOT call wizardFetchExtraFields() here because it would wipe the unsaved modal DOM. The chip is already visually rendering below!
    }

    // Append Chip visually. The value is HTML text in both places (Group 54 review,
    // S2): Save reads it back from data-value, and an attribute holding a quote or
    // '<' ('Odd "Quote" <b>Tag</b> & Co') read "Odd" here and was sent as "Odd ",
    // which Spoolman refuses as no choice of the field.
    const chipHtml = `<span class="badge rounded-pill text-bg-primary border border-primary cursor-pointer dynamic-chip"
                           onclick="this.remove()"
                           data-key="${key}"
                           data-selected="true"
                           data-value="${_wizEscape(val)}">${_wizEscape(val)} &times;</span>`;
    container.insertAdjacentHTML('beforeend', chipHtml);
    input.value = '';

    // Reset Filtering
    if (window.wizardMultiselectFilter) window.wizardMultiselectFilter(entityType, key);
};

// --- Group 10.5: when the user adds a new single-choice value (e.g. slicer
// profile) from inside the wizard, auto-select it on the currently-edited
// filament/spool so they don't have to re-pick it after the schema refresh.
// Also handles the "Use existing" branch from the suggestion swap (wasNew=false).
window.wizardOnNewChoiceAdded = (apiEntity, key, value, info) => {
    const entityPrefix = apiEntity === 'filament' ? 'fil' : 'spool';
    const inputId = `wiz_${entityPrefix}_ef_${key}`;
    const input = document.getElementById(inputId);
    if (!input) return;
    if (input.tagName === 'SELECT') {
        // The ➕ path just added the new value to this select's options (or
        // it was there already). Pick it and trigger change so dirty-tracking
        // / sync handlers fire.
        input.value = value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        // Picking it is the person's change (Group 66.4: the touched set no longer
        // hears `change`, which is all this pick fires).
        window.wizardNoteExtraTouched(input);
        wizardState.isDirty = true;
    } else if (input.tagName === 'INPUT' && info && info.wasNew) {
        // Multi-choice path (chips) — wizardAddMultiChoiceChip already handles
        // chip creation, so nothing to do here. Kept as a no-op branch for
        // future expansion.
    }
};

// --- Group 10.9: stateful content swaps inside the SAME add-new overlay.
// We avoid nested overlays because nested mountOverlay handles compete for
// Escape in capture-phase registration order (oldest wins), so the inner
// overlay can't reliably reclaim Escape. Swapping content inside the existing
// overlay sidesteps the race and keeps the workflow visually continuous.
// `wizardSwapNewChoiceTo*` are called by wizardPromptNewChoice's commit path.
window.wizardSwapNewChoiceToSuggestion = (handle, suggestion, canonical, fieldLabel, callbacks) => {
    const cb = callbacks || {};
    const safeSugg = String(suggestion).replace(/</g, '&lt;');
    const safeCanon = String(canonical).replace(/</g, '&lt;');
    const safeLabel = String(fieldLabel || 'value').replace(/</g, '&lt;');
    handle.element.dataset.stage = 'suggestion';
    handle.setContent(`
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; max-width:32.5rem; width:92%;" data-stage-panel="suggestion">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:10px;">🤔 Did you mean <span style="color:#ffd700;">${safeSugg}</span>?</div>
            <div style="color:#ffc; margin-bottom:14px;">A similar ${safeLabel} already exists. Pick the existing one (recommended) or add "<strong>${safeCanon}</strong>" as a brand-new value.</div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-sugg-add" class="btn btn-outline-warning btn-sm" style="min-width:160px;">Add "${safeCanon}" as new</button>
                <button id="fcc-wiz-sugg-use" class="btn btn-success btn-sm" style="min-width:160px;">Use "${safeSugg}"</button>
            </div>
        </div>
    `);
    handle.element.querySelector('#fcc-wiz-sugg-use')?.addEventListener('click', () => {
        handle.cleanup();
        if (typeof cb.useExisting === 'function') cb.useExisting();
    });
    handle.element.querySelector('#fcc-wiz-sugg-add')?.addEventListener('click', () => {
        if (typeof cb.addAnyway === 'function') cb.addAnyway();
    });
    setTimeout(() => handle.element.querySelector('#fcc-wiz-sugg-use')?.focus(), 0);
};

window.wizardSwapNewChoiceToConfirm = (handle, canonical, fieldLabel, onConfirm) => {
    const safeCanon = String(canonical).replace(/</g, '&lt;');
    const safeLabel = String(fieldLabel || 'value').replace(/</g, '&lt;');
    handle.element.dataset.stage = 'confirm';
    handle.setContent(`
        <div style="background:#1e1e1e; color:#fff; border:2px solid #dc3545; border-radius:8px; padding:20px 24px; max-width:32.5rem; width:92%;" data-stage-panel="confirm">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:10px;">⚠️ Add permanent new ${safeLabel}?</div>
            <div style="color:#ffc; margin-bottom:14px;">Add "<strong>${safeCanon}</strong>" as a permanent new ${safeLabel}? Spoolman doesn't expose UI to remove choices once added.</div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-addnew-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-addnew-confirm" class="btn btn-danger btn-sm" style="min-width:160px;">Add Permanently</button>
            </div>
        </div>
    `);
    handle.element.querySelector('#fcc-wiz-addnew-confirm')?.addEventListener('click', () => {
        if (typeof onConfirm === 'function') onConfirm();
    });
    handle.element.querySelector('#fcc-wiz-addnew-cancel')?.addEventListener('click', () => handle.cleanup());
    setTimeout(() => handle.element.querySelector('#fcc-wiz-addnew-cancel')?.focus(), 0);
};

// --- CHIP MULTISELECT LOGIC ---
window.wizardMultiselectFocus = (entityType, key) => {
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (dropdown) {
        dropdown.style.display = 'block';
        wizardMultiselectFilter(entityType, key); // Filter initial list
    }
};

window.wizardMultiselectBlur = (entityType, key) => {
    setTimeout(() => {
        const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
        if (dropdown) dropdown.style.display = 'none';

        // Auto-commit on blur if typed text exists
        const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
        if (input && input.value.trim().length > 0) {
            wizardAddMultiChoiceChip(entityType, key);
        }
    }, 150); // Delay allows click event on dropdown to fire first
};

window.wizardMultiselectFilter = (entityType, key) => {
    const qs = document.getElementById(`wiz_${entityType}_ef_${key}`).value.toLowerCase();
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (!dropdown) return;

    let hasVisible = false;
    Array.from(dropdown.children).forEach(option => {
        option.classList.remove('active', 'bg-primary'); // Clear selections on filter
        if (option.innerText.toLowerCase().includes(qs)) {
            option.style.display = 'block';
            hasVisible = true;
        } else {
            option.style.display = 'none';
        }
    });

    dropdown.style.display = hasVisible ? 'block' : 'none';
};

window.wizardMultiselectKeydown = (event, entityType, key) => {
    const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (!input) return;

    let visibleOptions = [];
    if (dropdown && dropdown.style.display !== 'none') {
        visibleOptions = Array.from(dropdown.children).filter(el => el.style.display !== 'none');
    }

    // Escape closes the multi-choice dropdown only (when open) — keep the
    // wizard modal open (Escape would otherwise bubble to Bootstrap's modal
    // dismiss and discard the wizard). Matches inv_details.js attribute picker.
    if (event.key === 'Escape' && dropdown && dropdown.style.display !== 'none') {
        event.preventDefault();
        event.stopPropagation();
        dropdown.style.display = 'none';
        return;
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!visibleOptions.length) return;
        event.preventDefault();

        let currentIndex = visibleOptions.findIndex(el => el.classList.contains('active'));

        // Remove active class from all
        visibleOptions.forEach(el => el.classList.remove('active', 'bg-primary'));

        if (event.key === 'ArrowDown') {
            currentIndex = currentIndex + 1 >= visibleOptions.length ? 0 : currentIndex + 1;
        } else {
            currentIndex = currentIndex - 1 < 0 ? visibleOptions.length - 1 : currentIndex - 1;
        }

        const nextActive = visibleOptions[currentIndex];
        nextActive.classList.add('active', 'bg-primary');

        // Ensure visible in scroll view
        const dropRect = dropdown.getBoundingClientRect();
        const itemRect = nextActive.getBoundingClientRect();
        if (itemRect.bottom > dropRect.bottom) {
            dropdown.scrollTop += (itemRect.bottom - dropRect.bottom);
        } else if (itemRect.top < dropRect.top) {
            dropdown.scrollTop -= (dropRect.top - itemRect.top);
        }
        return;
    }

    if (event.key === 'Enter') {
        event.preventDefault(); // Prevent modal form submission on enter

        if (visibleOptions.length > 0) {
            // Find active option, if none, use first visible
            let selected = visibleOptions.find(el => el.classList.contains('active')) || visibleOptions[0];
            wizardAddMultiChoiceChip(entityType, key, selected.innerText);
            return;
        }
        wizardAddMultiChoiceChip(entityType, key); // Fallback to current text
    } else if (event.key === 'Backspace' && input.value === '') {
        // Find last chip and remove it
        const container = document.getElementById(`chip-container-${entityType}-${key}`);
        if (container && container.lastElementChild) {
            container.removeChild(container.lastElementChild);
        }
    }
};

window.wizardMultiselectSelect = (event, entityType, key, value) => {
    event.preventDefault(); // Prevent blur trigger
    wizardAddMultiChoiceChip(entityType, key, value);
    const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
    if (input) input.focus(); // Keep focus after click
};

window.wizardPromptNewChoice = (entityType, key) => {
    // Determine the absolute entity mapping Spoolman uses ('filament' or 'spool')
    const apiEntity = entityType === 'fil' ? 'filament' : 'spool';

    // Multi-choice fields (e.g. filament_attributes) now expose a ➕ button too.
    // They render the chip widget, so the success path must drop a chip IN PLACE
    // rather than refetch the schema (wizardFetchExtraFields wipes the
    // in-progress wizard DOM). Pre-seed the overlay with whatever the user
    // already typed into the chip input, and clear that input so the pending
    // blur-commit (wizardMultiselectBlur) doesn't double-add the same value.
    const fieldDef = (wizardState.extraFields?.[apiEntity] || []).find((f) => f.key === key);
    const isMultiChoice = !!(fieldDef && fieldDef.multi_choice);
    let seedValue = '';
    if (isMultiChoice) {
        const chipInput = document.getElementById(`wiz_${entityType}_ef_${key}`);
        if (chipInput) { seedValue = (chipInput.value || '').trim(); chipInput.value = ''; }
    }

    // Group 10.8 — was nested Swal.fire; now mountOverlay.
    // Group 10.9 hooks `validateNewChoice` into the submit path for length /
    // punctuation / fuzzy-duplicate guards. Group 10.5 hooks the post-success
    // auto-assign for `slicer_profile`.
    const wizModalEl = document.getElementById('wizardModal');
    const existingChoices = (() => {
        const list = wizardState.extraFields?.[apiEntity] || [];
        const field = list.find((f) => f.key === key);
        const raw = field?.choices;
        if (Array.isArray(raw)) return raw;
        if (typeof raw === 'string') {
            try { const parsed = JSON.parse(raw); return Array.isArray(parsed) ? parsed : []; }
            catch (_) { return raw.replace(/[\[\]"]/g, '').split(',').map(s => s.trim()).filter(Boolean); }
        }
        return [];
    })();
    const fieldLabel = (() => {
        const list = wizardState.extraFields?.[apiEntity] || [];
        const field = list.find((f) => f.key === key);
        return field?.name || key;
    })();

    const panelHtml = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #28a745; border-radius:8px; padding:20px 24px; max-width:32.5rem; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">➕ Add New ${String(fieldLabel).replace(/</g, '&lt;')}</div>
            <div style="color:#ffc; margin-bottom:10px;">Enter the new value to permanently add it to the Spoolman database.</div>
            <input id="fcc-wiz-newchoice-input" type="text" class="form-control form-control-sm bg-dark text-white border-secondary mb-2" autocomplete="off" autocapitalize="off" spellcheck="false" />
            <div id="fcc-wiz-newchoice-preview" style="color:#9cf; font-size:0.85em; min-height:1.2em; margin-bottom:4px;"></div>
            <div id="fcc-wiz-newchoice-msg" style="color:#ff8080; font-size:0.9em; min-height:1.2em; margin-bottom:10px;"></div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-newchoice-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-newchoice-confirm" class="btn btn-success btn-sm" style="min-width:120px;">Add Option</button>
            </div>
        </div>
    `;
    const handle = window.mountOverlay({
        id: 'fcc-wiz-newchoice',
        content: panelHtml,
        host: wizModalEl,
        initialFocus: '#fcc-wiz-newchoice-input',
    });
    handle.element.dataset.stage = 'input';
    const input = handle.element.querySelector('#fcc-wiz-newchoice-input');
    const preview = handle.element.querySelector('#fcc-wiz-newchoice-preview');
    const msg = handle.element.querySelector('#fcc-wiz-newchoice-msg');
    const confirmBtn = handle.element.querySelector('#fcc-wiz-newchoice-confirm');
    const cancelBtn = handle.element.querySelector('#fcc-wiz-newchoice-cancel');

    const validate = (raw) => {
        if (typeof window.validateNewChoice === 'function') {
            return window.validateNewChoice(raw, existingChoices);
        }
        // Fallback: legacy minimum (non-empty after trim).
        const t = String(raw || '').trim();
        return t ? { ok: true, canonical: t } : { ok: false, canonical: '', error: 'Cannot be empty' };
    };

    const renderPreview = () => {
        const v = validate(input.value);
        preview.textContent = v.canonical && v.canonical !== input.value
            ? `Stored as: ${v.canonical}`
            : '';
        msg.textContent = '';
    };
    input?.addEventListener('input', renderPreview);
    // Pre-fill from the chip input when the ➕ was clicked after typing.
    if (seedValue && input) { input.value = seedValue; renderPreview(); }

    const commit = async () => {
        if (!input || (confirmBtn && confirmBtn.disabled)) return;
        const v = validate(input.value);
        if (!v.ok) {
            const liveMsg = handle.element.querySelector('#fcc-wiz-newchoice-msg');
            if (liveMsg) liveMsg.textContent = v.error || 'Invalid value';
            return;
        }
        if (v.suggestion) {
            // 10.9 fuzzy-match path: swap the overlay's content to a
            // suggestion panel. Single overlay = Escape-race-free.
            window.wizardSwapNewChoiceToSuggestion?.(handle, v.suggestion, v.canonical, fieldLabel, {
                useExisting: () => {
                    if (typeof window.wizardOnNewChoiceAdded === 'function') {
                        window.wizardOnNewChoiceAdded(apiEntity, key, v.suggestion, { wasNew: false });
                    }
                },
                addAnyway: () => {
                    window.wizardSwapNewChoiceToConfirm?.(handle, v.canonical, fieldLabel,
                        () => doSubmitFromStage(v.canonical));
                },
            });
            return;
        }
        // 10.9 two-step confirm for clean new values:
        if (typeof window.wizardSwapNewChoiceToConfirm === 'function') {
            window.wizardSwapNewChoiceToConfirm(handle, v.canonical, fieldLabel,
                () => doSubmitFromStage(v.canonical));
        } else {
            doSubmit(v.canonical);
        }
    };

    // Stage-agnostic submit: disables whatever buttons currently exist on the
    // active panel (input / suggestion / confirm) and surfaces errors inline.
    const doSubmitFromStage = (canonical) => doSubmit(canonical);

    const doSubmit = (canonical) => {
        const buttons = handle.element.querySelectorAll('button');
        buttons.forEach(b => { b.disabled = true; });
        fetch('/api/external/fields/add_choice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: apiEntity, key: key, new_choice: canonical })
        })
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.msg || 'Add failed');
                handle.cleanup();
                if (typeof showToast === 'function') {
                    showToast(`"${canonical}" added to the database.`, 'success', 3000);
                }
                if (isMultiChoice) {
                    // Multi-choice chip widget: do NOT refetch the schema —
                    // wizardFetchExtraFields wipes the in-progress wizard DOM.
                    // Register the new value in the live in-memory schema + the
                    // dropdown, then drop the chip in place.
                    if (fieldDef && Array.isArray(fieldDef.choices) && !fieldDef.choices.includes(canonical)) {
                        fieldDef.choices.push(canonical);
                    }
                    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
                    if (dropdown && !Array.from(dropdown.children).some((o) => o.innerText === canonical)) {
                        const opt = document.createElement('div');
                        opt.className = 'dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option';
                        opt.setAttribute('onmousedown', `wizardMultiselectSelect(event, '${entityType}', '${key}', this.innerText)`);
                        opt.innerText = canonical;
                        dropdown.appendChild(opt);
                    }
                    // canonical is now a "known" choice, so the directVal path
                    // appends the chip and skips a duplicate add_choice POST.
                    if (typeof window.wizardAddMultiChoiceChip === 'function') {
                        window.wizardAddMultiChoiceChip(entityType, key, canonical);
                    }
                    return undefined;
                }
                // Single-choice: in place too, never wizardFetchExtraFields,
                // which draws every extra again, blank, and in Edit Spool a
                // blank extra was then cleared on Save (2026-10-21 review).
                // Register the value, add its <option>, then the auto-assign
                // hook picks it (Group 10.5).
                if (fieldDef && Array.isArray(fieldDef.choices) && !fieldDef.choices.includes(canonical)) {
                    fieldDef.choices.push(canonical);
                }
                const select = document.getElementById(`wiz_${entityType}_ef_${key}`);
                if (select && select.tagName === 'SELECT'
                    && !Array.from(select.options).some((o) => o.value === canonical)) {
                    select.appendChild(new Option(canonical, canonical));
                }
                if (typeof window.wizardOnNewChoiceAdded === 'function') {
                    window.wizardOnNewChoiceAdded(apiEntity, key, canonical, { wasNew: true });
                }
                return undefined;
            })
            .catch(err => {
                buttons.forEach(b => { b.disabled = false; });
                if (typeof showToast === 'function') {
                    showToast(`Add failed: ${err.message || err}`, 'error', 7000);
                }
            });
    };

    confirmBtn?.addEventListener('click', commit);
    cancelBtn?.addEventListener('click', () => handle.cleanup());
    input?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
};

// --- COLOR GRADIENT LOGIC ---
window.wizardAddColorHex = () => {
    const container = document.getElementById('wiz-fil-color-extra-container');
    const idx = container.children.length + 1;
    const html = `
        <div class="input-group input-group-sm mb-1 mt-1">
            <input type="color" class="form-control form-control-color bg-dark border-secondary px-1" value="#000000" oninput="this.nextElementSibling.value = this.value.toUpperCase()">
            <input type="text" class="form-control bg-dark text-white border-secondary font-monospace pb-wiz-color" placeholder="#Hex" value="#000000" id="wiz-fil-color_hex_${idx}" autocomplete="off" oninput="this.previousElementSibling.value = (this.value.startsWith('#') ? this.value : '#' + this.value).padEnd(7, '0').substring(0,7)">
            <button class="btn btn-outline-danger" type="button" onclick="this.parentElement.remove(); if(document.getElementById('wiz-fil-color-extra-container').children.length === 0) { const w = document.getElementById('wiz-fil-color-direction-wrapper'); if (w) w.style.display='none'; }" title="Remove color">🗑️</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'block';
};

window.wizardPopulateColors = (hexString, direction) => {
    const container = document.getElementById('wiz-fil-color-extra-container');
    container.innerHTML = '';
    
    const dirEl = document.getElementById('wiz-fil-color-direction');
    if (dirEl) dirEl.value = direction || 'longitudinal';
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'none';

    if (!hexString) {
        document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
        document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
        return;
    }

    const hexes = hexString.split(',').map(h => h.trim().replace('#', '').toUpperCase()).filter(h => h.length >= 3);
    if (hexes.length === 0) {
        document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
        document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
        return;
    }

    // Set first hex
    document.getElementById('wiz-fil-color_hex_0').value = `#${hexes[0]}`;
    document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = `#${hexes[0]}`;

    // Add remaining hexes
    for (let i = 1; i < hexes.length; i++) {
        window.wizardAddColorHex();
        // wizardAddColorHex injects HTML inside container. Find the last added element.
        const inputs = container.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) {
            const lastInput = inputs[inputs.length - 1];
            lastInput.value = `#${hexes[i]}`;
            lastInput.previousElementSibling.value = `#${hexes[i]}`;
        }
    }

    if (hexes.length > 1) {
        // wizardAddColorHex already shows the wrapper, but be defensive
        // in case populateColors is called without any wizardAddColorHex
        // invocation (e.g. legacy single-call paths).
        if (dirWrap) dirWrap.style.display = 'block';
    }
};

// --- EXISTING FILAMENT LOGIC ---
// Group 66.4: the newest search paints. Each key typed in the box searches (its keyup),
// a scanner's label included, and an older answer landing last painted the list for
// text the box no longer holds.
let _wizExistingSearchSeq = 0;
window.wizardSearchExisting = () => {
    // Basic frontend filter based on standard filament pool
    // In a production environment this should likely ping a dedicated /api/v1/filament?query endpoint
    const seq = ++_wizExistingSearchSeq;
    const term = document.getElementById('wiz-search-existing').value.toLowerCase();
    const sel = document.getElementById('wiz-existing-results');
    sel.innerHTML = '<option disabled>Searching...</option>';

    fetch('/api/filaments')
        .then(r => r.json())
        .then(d => {
            if (seq !== _wizExistingSearchSeq) return;
            sel.innerHTML = "";
            let count = 0;
            if (d.success && d.filaments) {
                // Kept for a pick from this list (wizardFollowFilament).
                wizardState.existingFilaments = d.filaments;
                const terms = term.split(' ').map(t => t.trim()).filter(t => t.length > 0);

                d.filaments.forEach(f => {
                    const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
                    const target = name.toLowerCase();
                    const isMatch = terms.length === 0 || terms.every(t => target.includes(t));

                    if (isMatch) {
                        sel.innerHTML += `<option value="${f.id}">${name} (ID: ${f.id})</option>`;
                        count++;
                    }
                });
                if (count === 0) sel.innerHTML = '<option disabled>No matches found</option>';
            } else {
                sel.innerHTML = '<option disabled>Error loading filaments</option>';
            }
        })
        .catch(e => {
            console.error("Filament fetch failed", e);
            if (seq !== _wizExistingSearchSeq) return;
            sel.innerHTML = '<option disabled>Network Error</option>';
        });
};

// `filament`: the picked filament's record when the caller has it (a scan that
// recognised one); the list's own pick passes none.
window.wizardExistingSelected = (filament = null) => {
    const sel = document.getElementById('wiz-existing-results');
    if (sel.value) {
        wizardState.selectedFilamentId = sel.value;
        document.getElementById('wiz-status-msg').innerHTML = `Selected Existing Filament ID: <strong>${sel.value}</strong>`;
        wizardValidateSubmit();
        // Group 54 review (R2-1, R2-3): the spool's boxes follow the pick.
        window.wizardFollowFilament(filament);
    }
};

// Group 66.8 (ii): the newest Advanced Search pick (an older pick's answer that lands
// later changes nothing).
let _wizAdvancedPick = 0;

// The wizard's 🔍 Advanced Search: the search panel in select mode, asked for filaments,
// in the wizard's own words. A pick is used only while it is the newest, in the same
// wizard (its session) and the same mode. A spool is used only when the answer is that
// spool with its filament; anything else (a 404, Spoolman's 5xx body handed on as data,
// no answer) is refused in words, on the status line and in a 7 s toast: it used to be
// the browser's own alert(), and a failed fetch an unhandled rejection with the pick
// silently lost. A filament is used when the answer is that filament; otherwise it stays
// picked by its id, as it always was (Group 54.8 pins that its boxes then show nothing),
// in words saying its details couldn't be read (it read as "Generic Unknown - Unnamed").
// Names go in as text (CLAUDE.md: Spoolman's free text in the page is text).
window.wizardOpenGlobalSearch = () => {
    if (!window.SearchEngine) return;
    window.SearchEngine.open({
        mode: 'select',
        type: 'filament',
        prompts: {
            filament: 'Pick a filament to use it in the form.',
            spool: 'Pick a spool to use its filament in the form.',
        },
        callback: (id, type) => {
            const ask = ++_wizAdvancedPick;
            const session = wizardState.session;
            const mode = wizardState.mode;
            const current = () => ask === _wizAdvancedPick && wizardState.session === session && wizardState.mode === mode;
            const statusEl = () => document.getElementById('wiz-status-msg');
            const say = (words) => {
                const el = statusEl();
                if (el) el.innerHTML = `<span class="text-warning">${_wizEscape(words)}</span>`;
                if (window.showToast) window.showToast(words, 'warning', 7000);
            };
            const processFilament = (filId, filData = null) => {
                wizardState.selectedFilamentId = filId;
                let text = `Filament #${filId}`;
                if (filData) {
                    const vendor = filData.vendor ? filData.vendor.name : 'Generic';
                    const mat = filData.material || 'Unknown';
                    const name = filData.name || 'Unnamed';
                    text = `${vendor} ${mat} - ${name} (ID: ${filId})`;
                }
                const el = statusEl();
                if (el) el.innerHTML = `Selected via Advanced Search: <strong>${_wizEscape(text)}</strong>`;
                // Spoof the native select box so the UI knows (its words as text).
                const sel = document.getElementById('wiz-existing-results');
                if (sel) sel.replaceChildren(new Option(text, String(filId), true, true));
                wizardValidateSubmit();
                // Group 54 review (R2-1, R2-3): the spool's boxes follow the pick.
                window.wizardFollowFilament(filData);
            };
            if (type === 'spool') {
                const refused = () => say(`Couldn't read spool #${id}'s filament from Spoolman, so nothing was picked. `
                    + 'Pick it again in a moment, or pick its filament.');
                fetch(`/api/spools/${encodeURIComponent(id)}`)
                    .then(r => r.json())
                    .then(d => window.wizardAfterLabel(() => {
                        if (!current()) return;
                        const sp = d && d.success ? d.data : null;
                        if (sp && String(sp.id) === String(id) && sp.filament && sp.filament.id != null) {
                            processFilament(sp.filament.id, sp.filament);
                        } else {
                            refused();
                        }
                    }))
                    .catch(() => { if (current()) refused(); });
            } else {
                const unread = () => {
                    processFilament(id);
                    say(`Picked filament #${id}, but FCC couldn't read its details just now, `
                        + 'so its name isn\'t shown and nothing is filled in from it.');
                };
                fetch(`/api/filaments/${encodeURIComponent(id)}`)
                    .then(r => r.json())
                    .then(d => window.wizardAfterLabel(() => {
                        if (!current()) return;
                        const f = d && d.success ? d.data : null;
                        if (f && String(f.id) === String(id)) processFilament(id, f);
                        else unread();
                    }))
                    .catch(() => { if (current()) unread(); });
            }
        },
    });
};

// --- EXTERNAL DATABASE LOGIC ---
window.wizardSearchExternal = (autoApplyIfSingle = false) => {
    let term = document.getElementById('wiz-search-external').value.trim();
    let source = document.getElementById('wiz-external-source').value;
    const sel = document.getElementById('wiz-external-results');

    // Auto-detect Prusament URLs
    if (term.includes('prusament.com/spool/')) {
        document.getElementById('wiz-external-source').value = 'prusament';
        source = 'prusament';
    }

    // Auto-detect Amazon URLs
    if (term.includes('amazon.com') || term.includes('/dp/')) {
        document.getElementById('wiz-external-source').value = 'amazon';
        source = 'amazon';
    }

    // Auto-detect 3D Filament Profiles URLs
    if (term.includes('3dfilamentprofiles.com')) {
        document.getElementById('wiz-external-source').value = '3dfp';
        source = '3dfp';
    }

    if (term.length < 2) return;

    sel.innerHTML = '<option disabled>Querying ' + source + '...</option>';
    document.getElementById('wiz-status-msg').innerText = "Fetching external templates...";

    fetch(`/api/external/search?source=${source}&q=${encodeURIComponent(term)}`)
        .then(r => r.json())
        .then(d => {
            sel.innerHTML = "";
            if (d.success && d.results.length > 0) {
                document.getElementById('wiz-status-msg').innerText = `Found ${d.results.length} templates.`;
                d.results.forEach(f => {
                    // Extract safe display name
                    const brand = f.manufacturer || f.vendor?.name || 'Generic';
                    const mat = f.material || '?';
                    const color = f.color_name || f.name || 'Unknown Color';
                    const wt = f.weight ? ` - ${f.weight}g` : '';
                    const diam = f.diameter || f.settings_extrusion_diameter ? ` (${f.diameter || f.settings_extrusion_diameter}mm)` : '';

                    const opt = document.createElement('option');
                    opt.value = JSON.stringify(f); // Store the full payload in the value
                    opt.innerText = `${brand} ${mat} - ${color}${wt}${diam}`;
                    sel.appendChild(opt);
                });
                // Auto-apply a lone result (e.g. a scanned/pasted Prusament URL
                // resolves to exactly one spool) so the form pre-populates without
                // a manual pick. Opt-in — the legacy "Import from External" button
                // calls wizardSearchExternal() with no arg, so it's unchanged.
                if (autoApplyIfSingle && d.results.length === 1 && typeof window.wizardExternalSelected === 'function') {
                    sel.selectedIndex = 0;
                    window.wizardExternalSelected();
                }
            } else {
                sel.innerHTML = '<option disabled>No external templates found.</option>';
                document.getElementById('wiz-status-msg').innerText = "Search returned 0 results.";
            }
        })
        .catch(e => {
            console.error("External DB fetch failed", e);
            sel.innerHTML = '<option disabled>Error fetching from database.</option>';
            document.getElementById('wiz-status-msg').innerText = "Network Error.";
        });
};

// Filament-level fill — material/color/temps/vendor/template weights.
// Extracted from wizardExternalSelected so the per-spool scan flow can call
// just the spool half without re-touching Step 2.
window.applyFilamentFieldsFromTemplate = (temp) => {
    wizardState.externalMetaData = temp;

    // Split the parser's "full" material string ("PC Blend Carbon Fiber")
    // into a base material ("PC") + canonical filament_attributes
    // (["Blend", "Carbon Fiber"]). Spoolman's filtering only works on the
    // native material field, so the base is what should land there;
    // modifiers ride along as multi-choice extras for downstream display
    // and to satisfy the duplicate-detection matcher.
    const known = _knownFilamentAttributes();
    const split = window.splitMaterialAndAttributes(temp.material || '', known);
    document.getElementById('wiz-fil-material').value = split.base || temp.material || '';

    // Replace any existing chips for filament_attributes with the parsed
    // set. Keeps applyFilamentFieldsFromTemplate idempotent — calling it
    // again with different scan data fully replaces the form state instead
    // of accumulating attrs from prior scans.
    const chipContainer = document.getElementById('chip-container-fil-filament_attributes');
    if (chipContainer) {
        chipContainer.querySelectorAll('.dynamic-chip[data-key="filament_attributes"]').forEach(c => c.remove());
        wizardState.touchedExtras.add('fil:filament_attributes');   // the user applied it
    }
    if (window.wizardAddMultiChoiceChip) {
        split.attrs.forEach(attr => {
            window.wizardAddMultiChoiceChip('fil', 'filament_attributes', attr);
        });
    }

    document.getElementById('wiz-fil-color_name').value = temp.color_name || temp.name || '';

    let colorPayload = temp.multi_color_hexes || temp.color_hexes || temp.color_hex || 'FFFFFF';
    let colorDirection = temp.multi_color_direction || 'longitudinal';
    if (window.wizardPopulateColors) window.wizardPopulateColors(colorPayload, colorDirection);

    document.getElementById('wiz-fil-diameter').value = temp.diameter || temp.settings_extrusion_diameter || 1.75;
    document.getElementById('wiz-fil-density').value = temp.density || temp.settings_density || 1.24;
    // 24.K — when the parser only DEFAULTED the net weight (weight_is_default),
    // leave the field blank with a prompt instead of prefilling a fabricated
    // 1kg, so the user supplies the real weight rather than silently inheriting
    // 1000g. A real scraped weight still prefills as before.
    const _filWeightEl = document.getElementById('wiz-fil-weight');
    if (_filWeightEl) {
        if (temp.weight_is_default) {
            _filWeightEl.value = '';
            _filWeightEl.placeholder = 'Net weight unknown — enter grams';
        } else {
            _filWeightEl.value = temp.weight || 1000;
        }
    }
    // The template's own (Group 66.7: no mark).
    window.wizardSetFilEmptyWeightInherited(temp.spool_weight || '', 'filament');

    if (document.getElementById('wiz-fil-settings_extruder_temp')) {
        document.getElementById('wiz-fil-settings_extruder_temp').value = temp.settings_extruder_temp || '';
    }
    if (document.getElementById('wiz-fil-settings_bed_temp')) {
        document.getElementById('wiz-fil-settings_bed_temp').value = temp.settings_bed_temp || '';
    }
    if (document.getElementById('wiz-fil-nozzle_temp_max')) {
        const nozMax = (temp.extra && temp.extra.nozzle_temp_max) || temp.nozzle_temp_max || '';
        document.getElementById('wiz-fil-nozzle_temp_max').value = nozMax;
    }
    if (document.getElementById('wiz-fil-bed_temp_max')) {
        const bedMax = (temp.extra && temp.extra.bed_temp_max) || temp.bed_temp_max || '';
        document.getElementById('wiz-fil-bed_temp_max').value = bedMax;
    }

    // The wizard's filament extras (product_url, purchase_url) are rendered
    // by wizardFetchExtraFields as dynamic inputs with IDs of the shape
    // wiz_fil_ef_<key> (underscores). Writing to legacy `wiz-fil-product_url`
    // (hyphens) was a no-op — the static element has been gone for ages and
    // the wizardSubmit collector at line ~1610 only picks up `.dynamic-extra-field`
    // values. Hit the dynamic IDs directly so the URL actually rides along
    // when the wizard saves.
    if (temp.external_link) {
        const filUrlNode = document.getElementById('wiz_fil_ef_product_url');
        if (filUrlNode) filUrlNode.value = temp.external_link;
        // L351: also preload the spool's OWN product_url input so the scraped
        // product link is visible + editable per-spool (parity with the
        // purchase_url preload below).
        const spProductNode = document.getElementById('wiz-spool-product_url');
        if (spProductNode) { spProductNode.value = temp.external_link; spProductNode.placeholder = 'https://...'; }
    }
    if (temp.purchase_link) {
        // Group 10.4 — purchase_url is no longer rendered on the filament
        // tab. Preload the spool's purchase_url input instead so the user
        // sees the parser-scraped URL and can edit / clear it before save.
        // (The filament-side silent fill on save in computeFilamentSilentExtras
        // also handles the filament-level persist; this just adds the UI side.)
        const spPurchaseNode = document.getElementById('wiz-spool-purchase_url');
        if (spPurchaseNode) {
            spPurchaseNode.value = temp.purchase_link;
            spPurchaseNode.placeholder = 'https://...';
        }
    }

    const vName = temp.manufacturer || temp.vendor?.name;
    if (vName) {
        // Group 66.1: a name two manufacturers share gives the lowest id.
        const match = _wizVendorNamed(vName);
        if (match) {
            window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', String(match.id), match.name);
        } else {
            // Parser returned a vendor we don't have yet. Leave the name in the
            // search input so the user can either pick a close match from the
            // dropdown or click ➕ (the create button pre-fills from this
            // input's value). The legacy add-new toggle path was retired
            // with the Group 6.2 cleanup.
            const searchEl = document.getElementById('wiz-fil-vendor-search');
            if (searchEl) searchEl.value = vName;
            const hidden = document.getElementById('wiz-fil-vendor-sel');
            if (hidden) {
                hidden.value = '';
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    }

    // Group 48.4: a blank Slicer Profile takes the one this source names (the
    // Prusament spool page's product line); nothing else fills it.
    window.wizardSuggestSlicerProfile({ lookup: temp.slicer_profile, source: temp.slicer_profile_source });
    // Group 54 review (R2-3): the template is the new filament, so a spool box that
    // follows the filament shows its empty weight now.
    window.wizardFollowFilament();
};

// --- Group 48.4: fill a blank Slicer Profile --------------------------------------------
// Derek, 2026-10-19: for Prusament "it be perfered if we could just source that
// from the site". Only ever into a BLANK Slicer Profile while a NEW filament is
// being made (the 'manual' and 'external' modes): a profile the user picked, or
// one an existing filament has, is never replaced, and nothing is written
// before the wizard's own Save. The one source is a lookup that names a
// profile (an external parser's `slicer_profile`: the Prusament page's product
// line, "Prusament PLA Blend"): his own spelling when it is one of his profiles
// already; otherwise a new choice, which Save adds to Spoolman's list first
// (wizardCommitSuggestedChoices). Any later lookup that returns
// `slicer_profile` works the same way. A note under the field says where it
// came from.
// Derek, 2026-10-20: never a guess from his own filaments. The profile he
// records is one he confirmed prints well (a brand's own, a sister brand's like
// Jayo → Sunlu, else a Generic one), and a variant's attributes needn't match
// a profile name, so the brand + material guess the first build had is gone. A
// brand or material change after a lookup clears the name it gave (it was
// confirmed for the lookup's filament, not this one).
const _PROFILE_KEY = 'slicer_profile';
let _settingProfile = false;
const _profileSelect = () => document.getElementById(`wiz_fil_ef_${_PROFILE_KEY}`);
const _profileField = () => ((wizardState.extraFields || {}).filament || []).find(f => f && f.key === _PROFILE_KEY) || null;
const _profileChoices = () => {
    const raw = (_profileField() || {}).choices;
    if (Array.isArray(raw)) return raw.map(String);
    if (typeof raw === 'string') {
        try { const p = JSON.parse(raw); return Array.isArray(p) ? p.map(String) : []; } catch (_) { return []; }
    }
    return [];
};
const _unquoteProfile = (v) => String(v == null ? '' : v).trim().replace(/^"(.*)"$/, '$1').trim();

const _setProfileNote = (text) => {
    let note = document.getElementById('wiz-fil-profile-note');
    if (!note) {
        const sel = _profileSelect();
        const wrap = sel && typeof sel.closest === 'function' ? sel.closest('[data-extra-key]') : null;
        if (!wrap) return;
        note = document.createElement('div');
        note.id = 'wiz-fil-profile-note';
        note.className = 'small mt-1 fcc-wiz-profile-note';
        wrap.appendChild(note);
    }
    note.textContent = text || '';
    note.style.display = text ? '' : 'none';
};

// Drops the options FCC added for earlier suggestions ("… (new, from …)"),
// except `keep`'s: a suggestion that no longer applies takes its option along.
const _dropNewChoiceOptions = (sel, keep = null) => {
    Array.from((sel && sel.options) || []).forEach(o => {
        if (o.dataset && o.dataset.fccNewChoice === '1' && o.value !== keep) o.remove();
    });
};

const _selectProfile = (sel, value, isNew, source) => {
    _dropNewChoiceOptions(sel, isNew ? value : null);
    if (isNew && !Array.from(sel.options || []).some(o => o.value === value)) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = `${value} (new, from ${source})`;
        opt.dataset.fccNewChoice = '1';
        sel.appendChild(opt);
    }
    _settingProfile = true;
    try { sel.value = value; } finally { _settingProfile = false; }
    sel.dataset.fccSuggested = value;
};

// Returns what it suggested ({value, isNew, from, vendor, material}) or null.
window.wizardSuggestSlicerProfile = ({ lookup = '', source = '' } = {}) => {
    const sel = _profileSelect();
    if (!sel || !['manual', 'external'].includes(wizardState.mode)) return null;
    const ds = sel.dataset || {};
    const current = String(sel.value || '').trim();
    if (ds.fccUserSet === '1' || (current && current !== ds.fccSuggested)) return null;
    const want = _unquoteProfile(lookup);
    if (!want) return null;
    const match = _profileChoices().find(c => c.toLowerCase() === want.toLowerCase()) || null;
    const from = String(source || '').trim() || 'the lookup';
    _selectProfile(sel, match || want, !match, from);
    _setProfileNote(match ? `🎚️ From ${from}: ${match}.`
        : `🎚️ ${from} names this ${want}, which isn't in your profile list yet: Save adds it.`);
    wizardState.profileSuggestion = { value: match || want, isNew: !match, from,
                                      vendor: _profileVendorNow(), material: _profileMaterialNow() };
    return wizardState.profileSuggestion;
};

const _profileVendorNow = () => String((document.getElementById('wiz-fil-vendor-search') || {}).value || '').trim();
const _profileMaterialNow = () => String((document.getElementById('wiz-fil-material') || {}).value || '').trim();

// A brand or material change after a lookup named the profile: the name was
// confirmed for the lookup's filament, so a different brand or material clears
// it (only while it is still FCC's own suggestion), with a note saying why.
const _dropStaleProfileSuggestion = () => {
    const s = wizardState.profileSuggestion;
    const sel = _profileSelect();
    if (!s || !sel) return;
    const ds = sel.dataset || {};
    if (ds.fccUserSet === '1' || String(sel.value || '').trim() !== ds.fccSuggested) return;
    const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
    if (same(_profileVendorNow(), s.vendor) && same(_profileMaterialNow(), s.material)) return;
    _settingProfile = true;
    try { sel.value = ''; } finally { _settingProfile = false; }
    delete sel.dataset.fccSuggested;
    _dropNewChoiceOptions(sel);
    wizardState.profileSuggestion = null;
    _setProfileNote(`🎚️ The brand or material changed after ${s.from} named ${s.value}, so FCC cleared it: `
        + `pick a profile.`);
};

// Save's step before it writes (Group 48.4): a suggested profile that isn't one
// of the choices yet is added to Spoolman's list first (a choice field refuses
// an unknown value). False when that failed: the save stops and says why.
// Decided from what Save SENDS (Group 51 review, browser-3): the value is one
// FCC offered as new (its option says "(new, from …)") and still isn't a
// choice. Keyed on the suggestion, a "(new, …)" option picked again by hand
// after the user had picked another (which drops the suggestion) was sent
// without being added, and Spoolman refused every Save.
window.wizardCommitSuggestedChoices = async (fPayload) => {
    const sent = fPayload && fPayload.extra ? _unquoteProfile(fPayload.extra[_PROFILE_KEY]) : '';
    if (!sent || _profileChoices().some(c => c.toLowerCase() === sent.toLowerCase())) return true;
    const sel = _profileSelect();
    const offered = Array.from((sel && sel.options) || [])
        .find(o => o.value === sent && o.dataset && o.dataset.fccNewChoice === '1');
    if (!offered) return true;
    try {
        const r = await fetch('/api/external/fields/add_choice', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: 'filament', key: _PROFILE_KEY, new_choice: sent }),
        });
        const d = await r.json();
        if (!r.ok || !d || d.success === false) throw new Error((d && (d.msg || d.error)) || `HTTP ${r.status}`);
        const field = _profileField();
        if (field && Array.isArray(field.choices) && !field.choices.includes(sent)) field.choices.push(sent);
        // A choice now: its option is an ordinary one.
        delete offered.dataset.fccNewChoice;
        offered.textContent = sent;
        const s = wizardState.profileSuggestion;
        if (s && s.value === sent) s.isNew = false;
        return true;
    } catch (e) {
        const msg = `Couldn't add the slicer profile "${sent}" to Spoolman's list (${(e && e.message) || e}), `
            + `so nothing was saved. Pick a profile from the list, or Save again.`;
        if (typeof showToast === 'function') showToast(`❌ ${msg}`, 'error', 7000);
        const status = document.getElementById('wiz-status-msg');
        if (status) status.innerText = msg;
        return false;
    }
};

// The user's own pick is never replaced; a brand or material change clears a
// lookup's name that no longer applies.
document.addEventListener('change', (e) => {
    const t = e && e.target;
    if (!t || !t.id) return;
    if (t.id === `wiz_fil_ef_${_PROFILE_KEY}`) {
        if (_settingProfile) return;
        if (t.dataset) t.dataset.fccUserSet = '1';
        wizardState.profileSuggestion = null;
        _setProfileNote('');
    } else if (t.id === 'wiz-fil-vendor-sel' || t.id === 'wiz-fil-material') {
        _dropStaleProfileSuggestion();
    }
}, true);

// Spool-level extract — returns the per-spool override dict the wizard
// will merge onto each created spool. Does NOT touch the DOM.
window.extractSpoolFieldsFromTemplate = (temp) => {
    const override = { extra: {} };
    // 24.K — honor the parser's `weight_is_default` flag. When the source page
    // omitted net weight the parser substitutes 1000g and sets the flag; baking
    // that into the per-spool initial_weight records a FABRICATED measured value
    // (the "legacy 1000g leak"). Skip it so the spool inherits the filament's
    // canonical weight instead of a bogus per-spool initial — the user can still
    // type a real weight in Step 3 before submit.
    if (!temp.weight_is_default
        && temp.weight !== undefined && temp.weight !== null && !Number.isNaN(Number(temp.weight))) {
        override.initial_weight = Number(temp.weight);
    }
    if (temp.spool_weight !== undefined && temp.spool_weight !== null && Number(temp.spool_weight) > 0) {
        override.spool_weight = Number(temp.spool_weight);
    }
    // Spoolman text-type extras must arrive as JSON-quoted strings (e.g. the
    // 5 bytes `"348"` including literal quote chars). sanitize_outbound_data
    // runs json.loads on each value and `"348"` parses as the integer 348,
    // which Spoolman then rejects with "Value is not a string." Wrap in
    // literal quotes here, matching the inv_details.js Edit Filament pattern
    // and the nozzle_temp_max handling in wizardSubmit at line ~1493.
    if (temp.external_link) {
        // product_url is a Spoolman *extra* on Spool, not a native field —
        // sending it at top-level made Spoolman silently drop it. Send the
        // raw URL — sanitize_outbound_data wraps JSON_STRING_FIELDS (which
        // includes product_url and purchase_url) via json.dumps for us.
        // Pre-wrapping here would double-wrap and the literal quote chars
        // would leak into the UI on read-back.
        override.extra.product_url = temp.external_link;
    }
    // purchase_url is the canonical Prusa3D storefront link — scraped by
    // the parser from a "Buy now" link on the spool page. Falls back to
    // the per-spool URL only when the scrape didn't find anything, so
    // the field is never blank for a successful Prusament scan.
    if (temp.purchase_link) {
        override.extra.purchase_url = temp.purchase_link;
    } else if (temp.external_link) {
        override.extra.purchase_url = temp.external_link;
    }
    const mfgDate = temp.extra && temp.extra.prusament_manufacturing_date;
    if (mfgDate) override.extra.prusament_manufacturing_date = `"${mfgDate}"`;
    const lengthM = temp.extra && temp.extra.prusament_length_m;
    if (lengthM !== undefined && lengthM !== null && lengthM !== '') {
        override.extra.prusament_length_m = `"${lengthM}"`;
    }
    if (Object.keys(override.extra).length === 0) delete override.extra;
    return override;
};

window.wizardExternalSelected = () => {
    const sel = document.getElementById('wiz-external-results');
    if (sel.value) {
        try {
            const temp = JSON.parse(sel.value);

            // Same duplicate-detect + auto-switch + backfill flow used by
            // the per-spool Prusament scan. Without this, a user who hit
            // the legacy Step-2 "Import from External" button instead of
            // the Step-3 row scan would skip every safeguard we added —
            // duplicate filaments would still get created, existing
            // filaments wouldn't get their missing fields filled in.
            //
            // The gate accepts BOTH 'manual' (fresh wizard, user typing a
            // new filament) AND 'external' (the user clicked "Import from
            // External Database" — which sets mode='external' via
            // wizardSelectType). Both paths land here and both can lead
            // to a duplicate-filament create if we don't run the matcher.
            const canMatch = (wizardState.mode === 'manual' || wizardState.mode === 'external');
            if (!wizardState.filamentLockedFromScan && canMatch) {
                const matches = window.findFilamentMatches(temp);
                if (matches.length === 0) {
                    window.applyFilamentFieldsFromTemplate(temp);
                } else if (matches.definitive) {
                    window.wizardAutoSwitchToExisting(matches[0], temp);
                } else {
                    // Multiple basic-gate matches with no Tier-1 product-ID
                    // disambiguator — defer to the user via the picker.
                    window.wizardRenderDuplicatePicker(matches, temp);
                }
                wizardState.filamentLockedFromScan = true;
            } else {
                window.applyFilamentFieldsFromTemplate(temp);
            }

            // Legacy "Import from External" button also drops the source URL into
            // the Spool's product_url field as a default for non-per-spool flows.
            if (temp.external_link) {
                const spoolUrlNode = document.getElementById('wiz-spool-product_url');
                if (spoolUrlNode) spoolUrlNode.value = temp.external_link;
            }

            wizardValidateSubmit();
        } catch (e) { console.error("Could not parse external data payload", e); }
    }
};

// 25.3 — pure change-diff for "which FILAMENT fields flag a label reprint",
// extracted from the edit_spool submit path so the fields it detects can't
// silently drift from the primary Edit-Filament path. Returns
// { changedNative, changedExtras } keyed EXACTLY as _maybePromptLabelReprint
// (inv_details.js) expects. Previously the wizard diffed only name/…/color +
// filament_attributes and OMITTED original_color, so a Color-NAME (manufacturer
// original_color) change through the wizard didn't flag the spools for reprint
// while the primary path did (Group 23.3 parity gap).
window.wizardBuildFilamentLabelDiff = (orig, fPayload) => {
    orig = orig || {};
    fPayload = fPayload || {};
    const norm = (s) => String(s == null ? '' : s);
    const changedNative = {};
    if (norm(fPayload.name) !== norm(orig.name)) changedNative.name = fPayload.name;
    if (norm(fPayload.material) !== norm(orig.material)) changedNative.material = fPayload.material;
    const newVendor = (fPayload.vendor_id != null) ? String(fPayload.vendor_id) : '';
    if (newVendor !== norm(orig.vendor_id)) changedNative.vendor_id = fPayload.vendor_id;
    const newHex = String(fPayload.color_hex || '').replace(/^#/, '').toLowerCase();
    const newMulti = String(fPayload.multi_color_hexes || '').replace(/[#\s]/g, '').toLowerCase();
    const newDir = String(fPayload.multi_color_direction || '').toLowerCase();
    if (newHex !== orig.color_hex) changedNative.color_hex = newHex;
    if (newMulti !== orig.multi_color_hexes) changedNative.multi_color_hexes = newMulti;
    if (newDir !== orig.multi_color_direction) changedNative.multi_color_direction = newDir;

    const changedExtras = {};
    const origExtra = orig.extra || {};
    const newExtra = fPayload.extra || {};
    // Group 66.6: the server's one reading (window.fccFilamentAttrs), so an old
    // "Silk, Matte" compares as Silk and Matte, not as one tag that no chip list
    // matches (which flagged every spool's label at each Save of such a filament).
    const attrKey = (a) => {
        const arr = (a === window.FCC_DELETE_EXTRA) ? [] : window.fccFilamentAttrs(a);   // every chip removed (cleared)
        return arr.map(x => String(x).trim().toLowerCase()).filter(Boolean).sort().join('|');
    };
    if (attrKey(origExtra.filament_attributes) !== attrKey(newExtra.filament_attributes)) {
        changedExtras.filament_attributes = true;
    }
    // 25.3 — original_color (manufacturer Color-NAME) prints on the spool label,
    // so a change must flag the spools for reprint. Only compare when the wizard
    // actually COLLECTED the field (it's a .dynamic-extra-field relocated into
    // the Color panel; in edit mode a rendered field always lands in extra —
    // value, or the delete-sentinel when cleared) so an unchanged edit can't
    // false-flag. Strip the JSON quote-wrap on both sides (stored values are
    // wrapped; the raw form value is not); the sentinel/blank both normalize to
    // "" so clearing the name correctly counts as a change.
    const ocNorm = (v) => (v == null || v === window.FCC_DELETE_EXTRA)
        ? '' : String(v).replace(/^"|"$/g, '').trim();
    if (Object.prototype.hasOwnProperty.call(newExtra, 'original_color')
            && ocNorm(origExtra.original_color) !== ocNorm(newExtra.original_color)) {
        changedExtras.original_color = true;
    }
    return { changedNative, changedExtras };
};

// 25.H — render post-save "Queue label" affordances into #wiz-postcreate-actions.
// One chip per spool (dedups vs window.labelQueue, turns green once queued);
// CREATE mode adds a "Queue All" for multi-spool rounds (an 8-spool round used to
// need 8 individual clicks); EDIT mode renders a chip for the edited spool (it
// previously had none). The wizard modal stays open across all modes, so these
// are visible post-save. Extracted from wizardSubmit so it's unit-testable.
window.wizardRenderPostSaveQueueActions = (mode, createdSpoolsArg, editSpoolId) => {
    const actionRow = document.getElementById('wiz-postcreate-actions');
    if (!actionRow) return;
    actionRow.innerHTML = '';

    // Group 48.1: the queue row's text, "Brand - Material - Color" from the
    // filament the wizard holds (the backlog's look), so a queued label reads
    // like one before the queue window reads it live; "Spool #N" without one.
    const fieldVal = (id) => { const el = document.getElementById(id); return el ? String(el.value || '').trim() : ''; };
    const filamentText = [fieldVal('wiz-fil-vendor-search'), fieldVal('wiz-fil-material'), fieldVal('wiz-fil-color_name')]
        .filter(Boolean).join(' - ');
    const queueText = (sid) => filamentText || `Spool #${sid}`;

    const makeQueueChip = (sid) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-sm btn-outline-info fw-bold fcc-wiz-queue-label';
        btn.dataset.spoolId = String(sid);
        btn.title = `Queue a print label for Spool #${sid}`;
        btn.innerText = `🖨️ #${sid}`;
        const markQueued = () => {
            btn.classList.remove('btn-outline-info');
            btn.classList.add('btn-success');
            btn.disabled = true;
        };
        btn.addEventListener('click', (ev) => {
            ev.preventDefault();
            if (typeof window.addToQueue !== 'function') return;
            if (Array.isArray(window.labelQueue) && window.labelQueue.find(q => q.id === sid && q.type === 'spool')) {
                if (typeof showToast === 'function') showToast(`Spool #${sid} already in queue`, 'info', 2000);
                markQueued();
                return;
            }
            window.addToQueue({ id: sid, type: 'spool', display: queueText(sid) });
            if (typeof showToast === 'function') showToast(`Queued label for Spool #${sid}`, 'success', 2500);
            markQueued();
        });
        return { btn, markQueued };
    };

    const isEdit = mode === 'edit_spool';
    const createdSpools = (!isEdit && Array.isArray(createdSpoolsArg)) ? createdSpoolsArg : [];
    const editSid = (isEdit && editSpoolId) ? editSpoolId : null;
    if (!createdSpools.length && !editSid) return;

    const labelEl = document.createElement('span');
    labelEl.className = 'small text-light fw-bold me-2';
    labelEl.innerText = 'Queue label:';
    actionRow.appendChild(labelEl);

    const chips = [];
    createdSpools.forEach(sid => {
        if (!sid) return;
        const c = makeQueueChip(sid);
        chips.push(c);
        actionRow.appendChild(c.btn);
    });
    if (editSid) {
        const c = makeQueueChip(editSid);
        chips.push(c);
        actionRow.appendChild(c.btn);
    }

    // "Queue All" — only worthwhile for a multi-spool CREATE round. Dedups via
    // the same window.labelQueue check + reports how many were newly added.
    if (createdSpools.length > 1) {
        const allBtn = document.createElement('button');
        allBtn.type = 'button';
        allBtn.className = 'btn btn-sm btn-info fw-bold ms-1 fcc-wiz-queue-all';
        allBtn.title = 'Queue print labels for every spool just created';
        allBtn.innerText = `🖨️ Queue All (${createdSpools.length})`;
        allBtn.addEventListener('click', (ev) => {
            ev.preventDefault();
            if (typeof window.addToQueue !== 'function') return;
            let added = 0, already = 0;
            createdSpools.forEach(sid => {
                if (!sid) return;
                if (Array.isArray(window.labelQueue) && window.labelQueue.find(q => q.id === sid && q.type === 'spool')) {
                    already++;
                    return;
                }
                window.addToQueue({ id: sid, type: 'spool', display: queueText(sid) });
                added++;
            });
            chips.forEach(c => c.markQueued());
            allBtn.classList.remove('btn-info');
            allBtn.classList.add('btn-success');
            allBtn.disabled = true;
            if (typeof showToast === 'function') {
                const extra = already ? ` (${already} already queued)` : '';
                showToast(`Queued ${added} label${added === 1 ? '' : 's'}${extra}`, 'success', 3000);
            }
        });
        actionRow.appendChild(allBtn);
    }
};

// --- Group 40.7: the wizard's Location goes through the move engine ---
// Derek, 2026-10-19 (answer 7): a Location change behaves like Force Location.
// Save saves the other edits, then the server moves the spool through the
// engine, which may ask first (a printing head, a head already fed from
// elsewhere): those questions are shown here through window.askMoveConfirm and
// answered on /api/smart_move, the existing door. A refused move says why, and
// the other edits stay saved.

// A Location in the one form the server compares ('' = Unassigned).
const _wizLocKey = (v) => {
    const s = String(v == null ? '' : v).trim().replace(/^"+|"+$/g, '').trim().toUpperCase();
    return s === 'UNASSIGNED' ? '' : s;
};
const _wizEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

// The pending placement's request fields ({slot | picked_slot, expected_feed,
// auto_deploy}) for a Save to `location`, or {} when none applies: no pick, or
// the user typed another place after picking.
window.wizardPlacementFor = (location, placement = wizardState.pendingPlacement) => {
    const p = placement || null;
    const loc = _wizLocKey(location);
    if (!p || !loc || _wizLocKey(p.location) !== loc) return {};
    const out = {};
    const has = (v) => v != null && String(v).trim() !== '';
    if (has(p.slot)) out.slot = String(p.slot).trim();
    else if (has(p.picked_slot)) out.picked_slot = String(p.picked_slot).trim();
    if (p.expected_feed != null) out.expected_feed = String(p.expected_feed).trim().toUpperCase();
    if (p.auto_deploy === false) out.auto_deploy = false;
    // Group 40.7 with 40.5 / Swap option C: what the picker chose for a head (the
    // "came from" answer, '' = No box) and for an occupied slot (Swap).
    if (p.record_source !== undefined && p.record_source !== null) out.record_source = p.record_source;
    if (p.swap === true) out.swap = true;
    // Group 51.6 / 51.7: what the picker showed on the head picked, and in the
    // slot chosen for Swap / Overwrite. A choice held until Save can be old by
    // then: the server refuses it if another spool is there now.
    if (Array.isArray(p.expected_residents)) out.expected_residents = p.expected_residents.slice();
    if (p.expected_occupant != null) out.expected_occupant = p.expected_occupant;
    return out;
};

// The create's `placements`, one entry per new spool (null = left Unassigned). A
// picker's choice (a box slot, a head or a Printer Pool slot) places only the
// first: the rest are the per-spool picker loop's (Claude's call 29;
// window.wizardPlaceRemaining). A typed place takes every spool, one engine
// move each; the server refuses several onto a place that holds one. A blank
// Location places none.
window.wizardCreatePlacements = (count, location, placement = wizardState.pendingPlacement) => {
    const n = Math.max(0, parseInt(count, 10) || 0);
    const loc = _wizLocKey(location);
    if (!loc) return Array.from({ length: n }, () => null);
    const fields = window.wizardPlacementFor(location, placement);
    const picked = !!(placement && _wizLocKey(placement.location) === loc);
    return Array.from({ length: n }, (_, i) =>
        (picked && i > 0) ? null : Object.assign({ location: loc }, fields));
};

// Group 40.7 review — puts `loc` in the Location field the way the edit's
// pre-fill does: a listed place by its "Name (ID)" label, anything else (a
// toolhead, which the list hides) by its id, '' for Unassigned. Programmatic
// (wizardComboboxSet's non-bubbling change), so it never marks the form dirty.
window.wizardShowLocation = (loc) => {
    const key = _wizLocKey(loc);
    const rec = key ? (wizardState.locations || []).find(l => l && _wizLocKey(l.LocationID) === key) : null;
    const label = rec ? (rec.Name ? `${rec.Name} (${rec.LocationID})` : rec.LocationID) : key;
    window.wizardComboboxSet('wiz-spool-location-search', 'wiz-spool-location', rec ? rec.LocationID : key, label);
};

// Group 40.7 review (wizard-slotless-create-loads-empty-head) — whether Save
// must open the picker before it posts: the Location is a multi-slot Dryer Box
// or a Printer row that isn't its own toolhead, and no held choice is for it.
// That is a box confirmed with Tab or typed, a Clone's pre-filled box, or the
// next create after a pick was used up. Without a slot the engine took the
// lowest free slot that "loads no busy toolhead", and a slot bound to an EMPTY
// head qualifies, so a sealed new spool was loaded onto that head unasked. An
// edit asks only when the Location changes: a spool already in that box keeps
// its place on every other Save. Needs the picker (inv_cmd.js) on the page.
window.wizardSaveNeedsPicker = (location, placement = wizardState.pendingPlacement) => {
    const loc = _wizLocKey(location);
    if (!loc || !window.placeOneWithPicker || !window.openSlotPicker) return false;
    if (placement && _wizLocKey(placement.location) === loc) return false;
    if (wizardState.mode === 'edit_spool') {
        const now = wizardState.editSpoolLocation;
        if (typeof now !== 'string' || _wizLocKey(now) === loc) return false;
    }
    const rows = wizardState.allLocationRows || [];
    const row = rows.find(r => r && _wizLocKey(r.LocationID) === loc) || null;
    return !!row && ((window.isMultiSlotBox && window.isMultiSlotBox(row))
        || (window.isPrinterRowNotHead && window.isPrinterRowNotHead(row, rows)));
};

// Group 40.7 review (wizard-refused-pick-resent) — whether an edit's move was
// refused over the held picker choice itself, so sending it again can only be
// refused again: the slot was taken meanwhile, the head's "came from" slot
// can't be recorded, or the server says so (`pick_refused`: also a slot still
// claimed by a spool deployed from it). Any other refusal keeps the choice.
window.wizardPickRefused = (data) => {
    const d = data || {};
    if (d.pick_refused === true) return true;
    const lr = d.location_result;
    // Groups 51.3 / 51.6 / 51.7: a slot still claimed, or a head or slot that
    // holds a spool the picker never showed, refuses the held choice too.
    return !!(lr && typeof lr === 'object' && ['picked_slot_taken', 'record_source', 'slot_claimed',
        'residents_changed', 'occupant_changed'].includes(lr.blocked_reason));
};

// Group 40.7 (Derek's answer 7: the wizard's Location behaves like Force
// Location; 40.4 / 40.5): picking a multi-slot Dryer Box or a Printer row that
// isn't its own toolhead opens the slot or Printer picker (the same flow as
// Force Location and the box / printer labels, window.placeOneWithPicker), and
// the choice waits for Save as wizardState.pendingPlacement ("LR-MDB-1 slot 2";
// "XL-3 (via XL)" for a head, whose Location becomes the head). Escape in the
// picker puts the Location back as it was. Any other pick clears a held choice.
// Returns the picker's promise ({outcome: 'moved' | 'stopped', placement}), or
// null when the place needs no picker. `quiet` (Group 40.7 review: Save opens
// it too, window.wizardSaveNeedsPicker): no "picker was closed" toast, because
// Save's status line says what happened.
window.wizardLocationPicked = (value, before = null, { quiet = false } = {}) => {
    const rows = wizardState.allLocationRows || [];
    const loc = _wizLocKey(value);
    const row = rows.find(r => r && _wizLocKey(r.LocationID) === loc) || null;
    const search = document.getElementById('wiz-spool-location-search');
    const hidden = document.getElementById('wiz-spool-location');
    const prior = wizardState.pendingPlacement;
    wizardState.pendingPlacement = null;
    const needs = row && window.placeOneWithPicker && window.openSlotPicker
        && ((window.isMultiSlotBox && window.isMultiSlotBox(row))
            || (window.isPrinterRowNotHead && window.isPrinterRowNotHead(row, rows)));
    if (!needs) return null;
    const editing = wizardState.mode === 'edit_spool';
    const was = before || { value: '', label: '' };
    const host = document.getElementById('wizardModal');
    const rowLabel = row.Name ? `${row.Name} (${row.LocationID})` : row.LocationID;
    return window.placeOneWithPicker({
        loc: row.LocationID, sid: editing ? wizardState.editSpoolId : null, host,
        // Hold, don't send: Save sends it with the other edits.
        send: (pl, done) => {
            wizardState.pendingPlacement = {
                location: pl.location, slot: pl.slot, picked_slot: pl.picked_slot,
                expected_feed: pl.expected_feed, auto_deploy: pl.auto_deploy, swap: pl.swap === true,
                record_source: pl.record_source, noStore: !!pl.noStore,
                expected_residents: pl.expected_residents, expected_occupant: pl.expected_occupant,
                label: pl.label, via: row.LocationID,
            };
            if (hidden) hidden.value = pl.location;
            if (search) search.value = _wizLocKey(pl.location) === _wizLocKey(row.LocationID)
                ? `${rowLabel} — ${pl.label}` : `${pl.label} (via ${row.LocationID})`;
            if (hidden) hidden.dispatchEvent(new Event('change', { bubbles: true }));
            done({ outcome: 'moved' });
        },
    }).then((out) => {
        if (out && out.outcome === 'stopped') {
            // Put the field back as it stood (and the choice it held).
            if (hidden) hidden.value = was.value;
            if (search) search.value = was.label;
            if (hidden) hidden.dispatchEvent(new Event('change', { bubbles: true }));
            wizardState.pendingPlacement = prior && _wizLocKey(prior.location) === _wizLocKey(was.value) ? prior : null;
            if (!quiet && typeof showToast === 'function') showToast('Location not changed — the picker was closed', 'info', 4000);
        }
        return out;
    });
};

// Group 40.7 (Claude's call 29): the new spools a picker's choice left
// Unassigned (it placed the first) each get their own picker, one at a time,
// for the place the user picked (`placement.via`: the box, or the printer whose
// head the first one went on); Escape stops and the rest stay Unassigned.
// Group 40.7 review: `location` is the Location the create saved. A blank one
// places nothing (the user wanted the spools Unassigned), and `placement.via`
// counts only while the choice is for that Location (wizardPlacementFor's rule;
// a head's choice: `location` the head, `via` its printer). An abandoned choice
// used to open its box's picker for spools meant to stay Unassigned. Each move
// goes as `origin: 'wizard_create'` (wizard-loop-undo-buffer-top): performContextAssign
// sends 'buffer' by default, and Undo of a 'buffer' move puts the spool at the
// top of the scan buffer, which these new spools were never in.
window.wizardPlaceRemaining = async ({ spoolIds = [], location = '', placement = null } = {}) => {
    const saved = _wizLocKey(location);
    if (!saved) return;
    const ours = !!(placement && _wizLocKey(placement.location) === saved);
    const loc = (ours && placement.via) || location;
    if (!loc || !window.placeOneWithPicker || typeof performContextAssign !== 'function') return;
    const host = document.getElementById('wizardModal');
    const left = [];
    for (let i = 0; i < spoolIds.length; i++) {
        const sid = spoolIds[i];
        const out = await window.placeOneWithPicker({
            loc, sid, host, step: spoolIds.length > 1 ? `${i + 1} of ${spoolIds.length} left` : '',
            send: (pl, done) => performContextAssign(pl.location, pl.slot != null ? pl.slot : null, [], [sid],
                pl.picked_slot != null ? pl.picked_slot : null,
                { expectedFeed: pl.expected_feed, swapDisplaced: pl.swap ? (pl.displaced || { id: null }) : null,
                  autoDeploy: pl.auto_deploy === false ? false : undefined, noStore: !!pl.noStore,
                  recordSource: pl.record_source, origin: 'wizard_create',
                  // Group 51.6 / 51.7: what the picker showed.
                  expectedResidents: pl.expected_residents, expectedOccupant: pl.expected_occupant,
                  onOutcome: done }),
        });
        if (!out || out.outcome !== 'moved') {
            left.push(...spoolIds.slice(i));
            break;
        }
    }
    if (left.length && typeof showToast === 'function') {
        showToast(`${left.length} new spool${left.length === 1 ? ' stays' : 's stay'} Unassigned `
            + `(${left.map(id => '#' + id).join(', ')}): scan or Force Location `
            + `${left.length === 1 ? 'it' : 'them'} into place.`, 'info', 7000);
    }
};

// Group 40.7 (Claude's call 28): a clone of a spool loaded on a toolhead, or
// filed on a Printer row, starts with a blank Location (Unassigned), so its
// Save never unloads the original or files the copy on the printer; a clone of
// a spool on a shelf, cart or box keeps the original's Location. `rows`: every
// /api/locations row (the wizard's own list hides toolheads).
window.wizardIsHeadOrPrinterRow = (locId, rows) => {
    const id = _wizLocKey(locId);
    if (!id) return false;
    return (Array.isArray(rows) ? rows : []).some(r => {
        if (!r) return false;
        const type = String(r.Type || '').trim().toLowerCase();
        if (_wizLocKey(r.LocationID) === id && (type === 'printer' || window.isToolheadType(r.Type))) return true;
        return type === 'printer' && Array.isArray(r.toolheads)
            && r.toolheads.some(h => _wizLocKey(h && h.location_id) === id);
    });
};
window.wizardCloneStartsBlank = (spool, rows) => {
    const loc = _wizLocKey(spool && spool.location);
    if (!loc) return false;
    if (Array.isArray(rows) && rows.length) return window.wizardIsHeadOrPrinterRow(loc, rows);
    // No location list to check: a record whose trail names another place is
    // deployed on a head, so start blank rather than risk it.
    const src = _wizLocKey(spool && spool.extra && spool.extra.physical_source);
    return !!src && src !== loc;
};

// A Location move the server asked about (an edit's `location_result`, or one new
// spool's placement), shown through the one move dispatcher and replayed on
// /api/smart_move, whose bodies window.buildMoveReplay builds. ctx: {spoolId,
// location, fields: {slot, picked_slot, expected_feed, auto_deploy}, origin,
// host, onDone(outcome, res)}, outcome 'moved' | 'cancelled' | 'failed'.
const _wizardMoveQuestion = (answer, ctx) => {
    const f = ctx.fields || {};
    const sid = ctx.spoolId;
    const loc = ctx.location;
    // The /api/smart_move request this move would have been. `confirmed_fed_heads`:
    // this page can show the "already running another spool" question.
    const original = {
        location: loc, spools: [sid], slot: (f.slot != null && f.slot !== '') ? String(f.slot) : null,
        origin: ctx.origin || 'wizard_edit', confirmed_toolheads: [], confirmed_fed_heads: [],
    };
    if (f.auto_deploy === false) original.auto_deploy = false;
    // Group 40.7: the picker's "came from" answer and Swap, kept by every replay.
    if (f.record_source !== undefined && f.record_source !== null) original.record_source = f.record_source;
    if (f.swap === true) original.swap = true;
    // Group 51.6 / 51.7: every replay still checks what the picker showed.
    if (Array.isArray(f.expected_residents)) original.expected_residents = f.expected_residents.slice();
    if (f.expected_occupant != null) original.expected_occupant = f.expected_occupant;
    let ended = false;
    const end = (how, res = null) => {
        if (ended) return;
        ended = true;
        if (typeof ctx.onDone === 'function') {
            try { ctx.onDone(how, res); } catch (e) { console.error(e); }
        }
    };
    // A replaced question, or one this page can't show, moved nothing either.
    const cancelled = (info) => end(info && (info.superseded || info.unknown) ? 'failed' : 'cancelled');
    let post = null;
    const ask = (res, prior) => window.askMoveConfirm(res, {
        door: 'smart_move', original, prior, host: ctx.host, box: loc, slot: original.slot,
        // The picker knew the slot holds a record a store would be refused over.
        noStore: !!ctx.noStore,
        send: (body, next) => post(body, next), onCancel: cancelled,
    });
    post = (payload, prior) => {
        const filling = (payload.slot != null && payload.slot !== '') ? payload.slot : payload.picked_slot;
        if (typeof setProcessing === 'function') setProcessing(true, {
            label: window.printerLabelForTarget ? window.printerLabelForTarget(loc, filling) : null });
        window.fetchT('/api/smart_move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then(r => r.json())
            .then(res => {
                if (typeof setProcessing === 'function') setProcessing(false);
                const a = res || {};
                if (a.status === 'requires_confirm') { ask(a, prior); return; }
                // The same-slot swap's old spool came off its head into the buffer.
                window.takeIntoBuffer(a);
                const why = a.status === 'success' ? (a.failures || {})[String(sid)] : (a.msg || 'not moved');
                if (why) {
                    showToast(`❌ #${sid} was NOT moved to ${loc}: ${why}`, 'error', 7000);
                    end('failed', a);
                    return;
                }
                const slotTxt = (filling != null && filling !== '') ? ` slot ${filling}` : '';
                if ((prior && prior.store) || payload.auto_deploy === false) {
                    showToast(`📦 #${sid} stored in ${loc}${slotTxt}${prior && prior.store ? window.storeToastTail(prior) : ''}`,
                        'success', 4000);
                } else {
                    showToast(`✅ #${sid} → ${loc}${slotTxt}${a.auto_deployed_to ? ` → ${a.auto_deployed_to}` : ''}`,
                        'success', 4000);
                }
                Object.entries(a.auto_deploy_skipped || {}).forEach(([id, w]) => showToast(
                    `⚠️ #${id} is in ${loc} but was NOT deployed to ${a.auto_deploy_target || 'its toolhead'}: ${w}`,
                    'warning', 7000));
                document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                end('moved', a);
            })
            .catch((e) => {
                if (typeof setProcessing === 'function') setProcessing(false);
                showToast(`❌ #${sid} was NOT moved to ${loc}: ${(e && e.message) || 'network error'}`, 'error', 7000);
                end('failed');
            });
    };
    ask(answer, {
        heads: [],
        pickedSlot: (f.picked_slot != null && f.picked_slot !== '') ? String(f.picked_slot) : null,
        expectedFeed: f.expected_feed != null ? String(f.expected_feed).toUpperCase() : null,
    });
};

// The wizard's Location → Unassigned asked first (the spool is on a printing
// head): Force Location's own yes / no, and its replay, the force_unassign
// action with its boolean confirm (39.1). ctx as _wizardMoveQuestion's.
const _wizardUnassignQuestion = (answer, ctx) => {
    const sid = ctx.spoolId;
    let ended = false;
    const end = (how, res = null) => {
        if (ended) return;
        ended = true;
        if (typeof ctx.onDone === 'function') {
            try { ctx.onDone(how, res); } catch (e) { console.error(e); }
        }
    };
    window.confirmActivePrint({
        activePrint: answer.active_print, activePrints: answer.active_prints || [], msg: answer.msg,
        host: ctx.host,
        onConfirm: () => {
            if (typeof setProcessing === 'function') setProcessing(true);
            window.fetchT('/api/manage_contents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'force_unassign', location: '', spool_id: sid,
                                       origin: ctx.origin || 'wizard_edit', confirm_active_print: true }),
            })
                .then(r => r.json())
                .then(res => {
                    if (typeof setProcessing === 'function') setProcessing(false);
                    if (res && res.success) {
                        showToast(`✅ #${sid} → Unassigned`, 'success', 4000);
                        document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                        end('moved', res);
                    } else {
                        showToast(`❌ #${sid} was NOT unassigned: ${(res && res.msg) || 'Spoolman refused it'}`, 'error', 7000);
                        end('failed', res);
                    }
                })
                .catch((e) => {
                    if (typeof setProcessing === 'function') setProcessing(false);
                    showToast(`❌ #${sid} was NOT unassigned: ${(e && e.message) || 'network error'}`, 'error', 7000);
                    end('failed');
                });
        },
        onCancel: (info) => {
            if (!(info && info.superseded)) showToast('Cancelled — nothing moved', 'info', 4000);
            end(info && info.superseded ? 'failed' : 'cancelled');
        },
    });
};

// Group 40.7 review (wizard-refused-pick-resent): a refusal of the held picker
// choice itself (the slot was taken meanwhile, …) would come back on every
// Save, so the choice is dropped and the field shows its place again; the next
// Save opens that place's picker (window.wizardSaveNeedsPicker). Returns the
// status line's tail, or '' when no choice was held and sent.
const _wizDropRefusedPick = (ctx) => {
    const held = ctx.placement || null;
    const sent = !!(ctx.fields && Object.keys(ctx.fields).length);
    if (!held || !sent) return '';
    const place = held.via || held.location;
    if (wizardState.pendingPlacement === held) {
        wizardState.pendingPlacement = null;
        window.wizardShowLocation(place);
    }
    // A box's slot, or a printer's toolhead (a head's choice is held via its printer).
    const what = _wizLocKey(held.location) === _wizLocKey(place) ? 'a slot' : 'a toolhead';
    return ` Pick ${what} again: Save opens the picker for ${place}.`;
};

// An edit whose other changes saved but whose Location didn't move yet: the
// server's question (asked here, then replayed on its door) or its refusal
// (a 7 s error). `ctx`: {spoolId, location, fields, placement, host,
// onDone(outcome, res, info)}: 'moved' | 'cancelled' | 'failed' (the replay
// didn't land) | 'refused' (info.repick: the held choice was dropped).
window.wizardEditLocationNotMoved = (data, ctx) => {
    // Group 40.7 review (wizard-not-moved-drops-to-buffer): a Swap takes the
    // slot's old spool out into the scan buffer whether or not the incoming
    // spool's own write then lands (Swap option C), so this page's buffer takes
    // it on every path, or its next save would drop it from the server's copy.
    window.takeIntoBuffer(data);
    const lr = data && data.location_result;
    const asks = lr && typeof lr === 'object' && lr.status === 'requires_confirm' && !data.stale_page;
    if (asks) {
        const q = Object.assign({ origin: 'wizard_edit' }, ctx);
        if (_wizLocKey(ctx.location) === '') _wizardUnassignQuestion(lr, q);
        else {
            // Group 51 review (browser-6): the answered question's replay refused
            // over the held choice itself (a head or slot that changed since the
            // pick) drops it too, or the next Save is refused the same way.
            q.onDone = (outcome, res, info) => {
                if (outcome === 'failed' && res && window.wizardPickRefused({ location_result: res })) {
                    const why = res.status === 'success' ? (res.failures || {})[String(ctx.spoolId)] : res.msg;
                    const tail = _wizDropRefusedPick(ctx);
                    if (typeof ctx.onDone === 'function') ctx.onDone('refused', {
                        msg: `Saved your other changes, but #${ctx.spoolId} was not moved: `
                            + `${String(why || 'refused').replace(/\.\s*$/, '')}.`,
                    }, { repick: !!tail, tail });
                    return;
                }
                if (typeof ctx.onDone === 'function') ctx.onDone(outcome, res, info);
            };
            _wizardMoveQuestion(lr, q);
        }
        return 'asking';
    }
    const tail = window.wizardPickRefused(data) ? _wizDropRefusedPick(ctx) : '';
    const repick = !!tail;
    showToast(`❌ ${(data && data.msg) || `#${ctx.spoolId} was not moved`}${tail}`, 'error', 7000);
    if (window.logClientEvent) window.logClientEvent(`❌ Wizard edit: ${(data && data.msg) || 'not moved'}`, 'ERROR');
    if (typeof ctx.onDone === 'function') ctx.onDone('refused', data, { repick, tail });
    return 'refused';
};

// A create's placements: a toast per new spool placed, a 7 s error per one
// refused, and the questions one at a time (a dialog replaces an open one on
// the same overlay, so they can't be shown together). `onDone(remaining,
// {unanswered})` runs once every question is settled, with the new spools that
// had no placement (the per-spool picker loop's, Claude's call 29) and those
// whose question didn't end in a move. Returns the questions asked.
// Group 40.7 review: a question that ends in anything but a move (Cancel, or a
// replay that failed) leaves its new spool Unassigned, and one 7 s toast says so
// once they are all answered (wizard-create-cancel-silent: the shared yes / no
// said nothing, and the server's summary is for older pages). `pick`: the held
// picker choice the create used; the first new spool's question keeps its
// `noStore` (wizard-create-question-drops-nostore: over a stale record the
// engine refuses a store, so no "Just store it").
window.wizardSettleCreatePlacements = (data, { host = null, onDone = null, pick = null } = {}) => {
    const d = data || {};
    const results = d.location_results || {};
    const tried = d.placement_requests || {};
    const placed = d.placed || {};
    window.takeIntoBuffer(d);
    const questions = [];
    (d.created_spools || []).forEach(id => {
        const key = String(id);
        if (!(key in results)) return;
        const res = results[key] || {};
        const where = (tried[key] || {}).location || 'its location';
        if (key in placed) {
            showToast(`✅ New spool #${id} → ${placed[key]}`, 'success', 4000);
            const skipped = (res.auto_deploy_skipped || {})[key];
            if (skipped) showToast(`⚠️ #${id} is in ${where} but was NOT deployed to ${res.auto_deploy_target || 'its toolhead'}: ${skipped}`, 'warning', 7000);
            return;
        }
        if (res.status === 'requires_confirm') { questions.push(id); return; }
        const why = (res.failures || {})[key] || res.msg || 'not placed';
        showToast(`❌ New spool #${id} was not placed in ${where}, so it is Unassigned: ${why}`, 'error', 7000);
    });
    const remaining = (d.unplaced || []).filter(id => !(String(id) in results));
    const asked = questions.slice();
    const unanswered = [];
    // The held choice placed the first new spool only (window.wizardCreatePlacements).
    const first = (d.created_spools || [])[0];
    const next = () => {
        const id = questions.shift();
        if (id == null) {
            if (unanswered.length && typeof showToast === 'function') {
                const many = unanswered.length > 1;
                const names = unanswered.map(n => '#' + n);
                const list = many ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0];
                showToast(`${list} ${many ? 'were' : 'was'} created and ${many ? 'stay' : 'stays'} Unassigned: `
                    + `scan or Force Location ${many ? 'them' : 'it'} into place.`, 'warning', 7000);
            }
            if (typeof onDone === 'function') onDone(remaining, { unanswered: unanswered.slice() });
            return;
        }
        const key = String(id);
        const want = tried[key] || {};
        const fromPick = !!(pick && String(id) === String(first) && _wizLocKey(pick.location) === _wizLocKey(want.location));
        _wizardMoveQuestion(results[key], {
            spoolId: id, location: want.location, fields: want, origin: 'wizard_create', host,
            noStore: fromPick && !!pick.noStore,
            onDone: (outcome) => {
                if (outcome !== 'moved') unanswered.push(id);
                next();
            },
        });
    };
    next();
    return asked;
};

// Group 64 review (S3), fix review 2 (CP6), 3 (TP5) and 4 (UP4): once a Save's spool
// write landed, Total Used's baseline is the figure that Save sent (a figure typed while
// it was out still differs, so the next Save sends it; read from the box at the answer,
// it was never sent). The addition or reading that Save sent is spent, and only that
// one: a new one taken while it was out is another object, and keeps its own.
function wizardSavedUsed(sent, addSent, readSent) {
    wizardState.usedShown = sent;
    if (addSent && wizardState.usedAdd === addSent) wizardState.usedAdd = null;
    if (readSent && wizardState.usedRead === readSent) wizardState.usedRead = null;
}

// A manufacturer id as it stands after this window's merges (wizardState.vendorMerges).
function _wizVendorMapped(id) {
    let v = String(id);
    const merges = wizardState.vendorMerges || {};
    for (let hops = 0; hops < 20 && Object.prototype.hasOwnProperty.call(merges, v); hops += 1) v = String(merges[v]);
    return v;
}

// Group 66.9 review round 2 (R2P2 / R2X-1): once a Save's filament write landed, the
// manufacturer's baseline is what that Save stood for (the Vendor box's), as Total Used's
// is above. Kept at the open's, a change back in the same window (Sunlu #4, Save, then
// Sunlu #35 again, Save) was left out as "unchanged", and the filament stayed on #4 under
// "Success! Spool Updated.". Round 3: so is every field the label check reads (R3W7, older
// than 66.9: compared with the open's at every later Save, a renamed filament's labels
// were flagged again and the swatch question asked again), normalised as the open
// normalises them; the manufacturer through this window's merges (R3W6: a merge while the
// Save was out left the deleted id there, or kept the merge's re-point over the Save's
// own write); and the doubt of a lost answer ends only for a Save that carried a
// manufacturer (R3W5: a Generic Save, which sends none, cleared it).
function wizardSavedFilament(origSent, shown, fPayload) {
    if (!fPayload || !origSent) return;
    const cur = wizardState.editFilamentOriginal || origSent;
    const sentExtra = fPayload.extra || {};
    const extra = Object.assign({}, cur.extra || {});
    const has = (k) => Object.prototype.hasOwnProperty.call(sentExtra, k);
    if (has('filament_attributes')) {
        extra.filament_attributes = sentExtra.filament_attributes === window.FCC_DELETE_EXTRA ? [] : sentExtra.filament_attributes;
    }
    if (has('original_color')) {
        extra.original_color = sentExtra.original_color === window.FCC_DELETE_EXTRA ? '' : sentExtra.original_color;
    }
    const next = Object.assign({}, cur, {
        name: fPayload.name || '',
        material: fPayload.material || '',
        color_hex: String(fPayload.color_hex || '').replace(/^#/, '').toLowerCase(),
        multi_color_hexes: String(fPayload.multi_color_hexes || '').replace(/[#\s]/g, '').toLowerCase(),
        multi_color_direction: String(fPayload.multi_color_direction || '').toLowerCase(),
        extra,
    });
    if (shown != null) {
        next.vendor_id = _wizVendorMapped(shown);
        wizardState.vendorUnsure = false;
    }
    wizardState.editFilamentOriginal = next;
}

// Group 66.9 review round 2 (R2X-3; older than 66.9, from Group 66's R3-03): once a
// Save's spool write landed, the link boxes' baseline is what that Save's boxes held, so
// a link saved and then emptied in the same window is cleared (it was compared with the
// open's blank, and kept).
function wizardSavedLinks(sent) {
    if (sent) wizardState.linkShown = Object.assign({}, sent);
}

// A link box's baseline after a Save that went out with no answer FCC could read, for a
// box that Save sent: no box can equal it, so the next Save sends the box as it is (the
// Save may have landed). A box it didn't send keeps its baseline (Group 66.9 review round
// 3, R3W3: every box went out as drawn, and an old link was written over the canonical
// one a dashboard scan had saved meanwhile).
const WIZ_LINK_UNSURE = '\u0000unsure';

const _wizardSubmitInner = async () => {
    // Fix review 4 (UP5) and 5 (VP4): the session this Save belongs to, and its spool,
    // noted first, so an answer (or no answer) after the wizard was opened again is told
    // apart and said in a toast naming the spool, never on the form opened since.
    const session = wizardState.session;
    const editAtSave = wizardState.mode === 'edit_spool';
    const sidAtSave = wizardState.editSpoolId;
    document.getElementById('btn-wiz-submit').disabled = true;
    const msg = document.getElementById('wiz-status-msg');
    if (wizardState.editLoadFailed) {
        // Fix review 5 (VP5): whatever pressed it (a key, a script), a form that never
        // loaded saves nothing.
        msg.innerHTML = '<span class="text-danger">This spool never loaded: close this window and open Edit Spool again.</span>';
        return;
    }
    msg.innerText = "Processing...";

    const getVal = (id) => {
        const el = document.getElementById(id);
        if (!el) throw new Error(`Missing DOM Element: ${id}`);
        return el.value;
    };

    // What this Save sent, and how far it got: only a request that went out and got no
    // answer FCC could read leaves anything unsure, and only what it sent (Group 66.9 review
    // round 3, R3W3 / R3W4: any throw marked both, a throw before the request or after a
    // clean answer included).
    let posted = false;
    let answered = false;
    let vendorSentId = null;
    let linkKeysSent = [];
    try {
        const qty = parseInt(getVal('wiz-spool-qty')) || 1;

        // 23.4 — only EDIT mode (→ /api/edit_spool_wizard, a partial PATCH that
        // merges against the live record) may emit the delete-sentinel for a
        // blanked extra. CREATE modes build a fresh record, so a blank is simply
        // omitted (sending the sentinel on create would store a literal token).
        // The edit_spool prefill loads every shown extra from the live record,
        // so a blank field here genuinely means "user cleared it".
        const isWizardEdit = wizardState.mode === 'edit_spool';

        // Construct Spool Payload
        let sp_payload = {
            used_weight: getVal('wiz-spool-used') !== "" ? parseFloat(getVal('wiz-spool-used')) : 0,
            spool_weight: getVal('wiz-spool-empty_weight') !== "" ? parseFloat(getVal('wiz-spool-empty_weight')) : null,
            initial_weight: getVal('wiz-spool-initial_weight') !== "" ? parseFloat(getVal('wiz-spool-initial_weight')) : null,
            location: getVal('wiz-spool-location') || '',
            comment: getVal('wiz-spool-comment') || '',
            price: getVal('wiz-spool-price') !== "" ? parseFloat(getVal('wiz-spool-price')) : null,
            archived: document.getElementById('wiz-spool-archived')?.checked || false,
            extra: {}
        };

        // Group 64 review (S2 / S3): Edit Spool sends Total Used only when the box
        // changed from what the record filled in (typed, or worked out by the weigh
        // boxes). Sent as drawn, it rewrote 100.37 as the box's 100.4 on a comment
        // save, and a form opened before a print's charge and saved after it wrote
        // the old used weight back over the charge; either was stamped as a weighing.
        if (isWizardEdit && wizardState.usedShown != null && getVal('wiz-spool-used') === wizardState.usedShown) {
            delete sp_payload.used_weight;
        }
        // Group 64 fix review (FP2 / FP3): a Total Used the box still shows as an
        // addition's result goes with the used weight it was added to.
        // Group 64 full review (PI2): one a scale reading set says so; a figure typed in
        // the box (or a label's digits a scan left there) says nothing, and isn't stamped
        // as FCC's weighing.
        const usedSent = isWizardEdit && 'used_weight' in sp_payload;
        // Group 64 fix review 3 (TP5): what Total Used showed when this Save went out,
        // the figure its baseline becomes once the spool's write lands.
        const usedBoxSent = getVal('wiz-spool-used');
        // Fix review 4 (UP4): what this Save sent. Fix review 5 (VP1): and the filament as
        // the form opened it, which the label check compares against in any session.
        const usedAddSent = wizardState.usedAdd;
        const usedReadSent = wizardState.usedRead;
        const filOrigSent = wizardState.editFilamentOriginal;
        const usedBasedOn = (usedSent && wizardState.usedAdd && getVal('wiz-spool-used') === wizardState.usedAdd.shown)
            ? { mode: 'additive', used: wizardState.usedAdd.base }
            : (usedSent && wizardState.usedRead && getVal('wiz-spool-used') === wizardState.usedRead.shown)
                ? { mode: 'reading' } : null;

        // Purchase Link (Spool Extra)
        const purchaseUrl = document.getElementById('wiz-spool-purchase_url')?.value?.trim();
        // Review round 1 of Group 66 (R3-03): in an edit a link box goes out only when it
        // changed from what the edit opened with (a person's edit, or the link box's fill).
        // Sent as drawn, it wrote the old link over one a matched Prusament scan saved while
        // the wizard was open, and a blank one cleared it.
        const linkChanged = (key, v) => !isWizardEdit || !wizardState.linkShown
            || String(v || '') !== String(wizardState.linkShown[key] || '');
        if (purchaseUrl) { if (linkChanged('purchase_url', purchaseUrl)) sp_payload.extra.purchase_url = purchaseUrl; }
        else if (isWizardEdit && linkChanged('purchase_url', '')) sp_payload.extra.purchase_url = window.FCC_DELETE_EXTRA;  // 23.4 — blank-to-clear on edit

        // Product Link (Spool Extra). L351 — on CREATE, gated on a truthy typed
        // value so an empty input never clobbers a product_url supplied by a
        // Prusament-scan override or inherited via the filament fallback (ghost
        // placeholder). On EDIT the field holds the spool's OWN value, so a
        // cleared input is a real delete intent → send the sentinel (23.4).
        const productUrl = document.getElementById('wiz-spool-product_url')?.value?.trim();
        if (productUrl) { if (linkChanged('product_url', productUrl)) sp_payload.extra.product_url = productUrl; }
        else if (isWizardEdit && linkChanged('product_url', '')) sp_payload.extra.product_url = window.FCC_DELETE_EXTRA;
        // What the two link boxes held as this Save compared them: their baseline once the
        // spool's write lands (Group 66.9 review round 2, R2X-3: wizardSavedLinks).
        const linksSent = { purchase_url: purchaseUrl || '', product_url: productUrl || '' };
        linkKeysSent = ['purchase_url', 'product_url'].filter((k) => Object.prototype.hasOwnProperty.call(sp_payload.extra, k));

        // Extract Dynamic Spool Fields (never a key with its own input above:
        // its copy would overwrite what the user typed there).
        document.querySelectorAll('.dynamic-extra-spool-field').forEach(el => {
            const key = el.getAttribute('data-key');
            if (!key || WIZ_SPOOL_EXTRAS_OWN_INPUT.includes(key)) return;
            if (el.type === 'checkbox') {
                sp_payload.extra[key] = el.checked;
            } else if (el.value) {
                sp_payload.extra[key] = el.value;
            } else if (isWizardEdit && wizardExtraTouched('spool', key)) {
                // 23.4 — blank-to-clear on edit, only a field the user emptied
                sp_payload.extra[key] = window.FCC_DELETE_EXTRA;
            }
        });

        // Group 54.5: in edit mode a plain box the user emptied is a clear, sent as
        // null; every other null is left out, as before, so the record keeps what
        // it has.
        Object.keys(sp_payload).forEach(k => {
            if (sp_payload[k] === null && wizardNativeCleared('spool', k)) return;
            if (sp_payload[k] === undefined || sp_payload[k] === null || Number.isNaN(sp_payload[k])) delete sp_payload[k];
        });
        // Group 54.8 (Derek, 2026-11-07, (a)): a price the box shows from the
        // filament is not this spool's, so it is never saved as its own: a new
        // spool is created with no price, an edited spool keeps none. Typed over
        // (or emptied, 54.5's clear in edit mode), it is the spool's own.
        if (wizardSpoolPriceIsFilaments()) delete sp_payload.price;
        // Its twin (Claude's call, Edit Spool only): an empty weight the spool only
        // inherits, untouched, isn't written as its own either. The empty-weight
        // cross-inherit below then reads the filament's box, then the brand, where
        // that value came from. New spools and clones take it as their own (L34).
        if (isWizardEdit && wizardSpoolEmptyWeightIsInherited()) delete sp_payload.spool_weight;

        let f_payload = null;
        // The manufacturer the Vendor box showed at this Save (Group 66.9 review): Edit
        // Spool leaves an unchanged one out of f_payload, and the label diff still compares
        // what the box showed, so an unchanged one reads as no change.
        let vendorShown = null;
        let target_fid = null;

        if (wizardState.mode === 'existing') {
            target_fid = wizardState.selectedFilamentId;
        } else {
            if (wizardState.mode === 'edit_spool') {
                target_fid = wizardState.selectedFilamentId; // Pass through ID so backend knows which Filament to update
            }
            // Hex Parsing for Multiple Colors
            const colorInputs = Array.from(document.querySelectorAll('input[id^="wiz-fil-color_hex_"]'));
            const colors = colorInputs.map(i => i.value.replace('#', '').toUpperCase()).filter(c => c.length === 6);

            f_payload = {
                name: getVal('wiz-fil-color_name') || 'Unknown',
                material: getVal('wiz-fil-material') || 'PLA',
                weight: getVal('wiz-fil-weight') !== "" ? parseFloat(getVal('wiz-fil-weight')) : 1000,
                spool_weight: getVal('wiz-fil-empty_weight') !== "" ? parseFloat(getVal('wiz-fil-empty_weight')) : null,
                diameter: getVal('wiz-fil-diameter') !== "" ? parseFloat(getVal('wiz-fil-diameter')) : 1.75,
                density: getVal('wiz-fil-density') !== "" ? parseFloat(getVal('wiz-fil-density')) : 1.24,
                color_hex: colors.length > 0 ? colors[0] : 'FFFFFF',
                settings_extruder_temp: getVal('wiz-fil-settings_extruder_temp') !== "" ? parseInt(getVal('wiz-fil-settings_extruder_temp')) : null,
                settings_bed_temp: getVal('wiz-fil-settings_bed_temp') !== "" ? parseInt(getVal('wiz-fil-settings_bed_temp')) : null,
                extra: {}
            };

            // Spoolman extras of type "text" must arrive as JSON-quoted strings
            // (`"245"` — 5 bytes including literal quote chars). spoolman_api's
            // sanitize_outbound_data runs json.loads on each value: a raw "245"
            // parses as the integer 245 and Spoolman rejects with
            // "Value is not a string." Match the Edit Filament pattern at
            // inv_details.js:1617 by wrapping in literal quotes.
            if (getVal('wiz-fil-nozzle_temp_max') !== "") {
                f_payload.extra.nozzle_temp_max = `"${getVal('wiz-fil-nozzle_temp_max')}"`;
            } else if (isWizardEdit && wizardNativeTouched('fil', 'nozzle_temp_max')) {
                f_payload.extra.nozzle_temp_max = window.FCC_DELETE_EXTRA;  // 23.4 — blank-to-clear on edit (emptied: R3-03)
            }
            if (getVal('wiz-fil-bed_temp_max') !== "") {
                f_payload.extra.bed_temp_max = `"${getVal('wiz-fil-bed_temp_max')}"`;
            } else if (isWizardEdit && wizardNativeTouched('fil', 'bed_temp_max')) {
                f_payload.extra.bed_temp_max = window.FCC_DELETE_EXTRA;  // 23.4 — blank-to-clear on edit (emptied: R3-03)
            }

            // Cross-Inherit empty-spool-weight along the chain: Spool → Filament → Vendor.
            // Resolves the selected vendor from wizardState so a manufacturer-level weight
            // flows down even when both Filament and Spool fields are left blank.
            //
            // It fills the FILAMENT's side only. The spool's nulls are taken out of
            // sp_payload above, so a blank spool box reaches here as undefined, and the
            // spool line this block had (`if (sp_payload.spool_weight === null) …`)
            // could never fire (not since 13654bb, 2026-04-06; found by Group 54.5). A
            // new spool's box copies the filament's (wizardSetupFieldSync), and an
            // edited spool's shows its inherited value from the open, so the spool's
            // empty weight comes from its box; in Edit Spool an inherited value left
            // untouched is no longer sent at all (Group 54.8). Edit mode never refills
            // a box the user emptied: that is a clear (Group 54.5).
            {
                // Review round 2 of Group 66 (Q2-03 / Q5-03): Edit Spool's filament inherits
                // its brand's weight by itself, so its Save never takes the brand's weight for
                // it (a brand picked over an empty box was written as the filament's own).
                // Only a create's new filament takes it (the cross-check's C15).
                const selectedVendorId = isWizardEdit ? '' : document.getElementById('wiz-fil-vendor-sel')?.value;
                const vendor = selectedVendorId
                    ? (wizardState.vendors || []).find(v => String(v.id) === String(selectedVendorId))
                    : null;
                const resolved = resolveEmptySpoolWeight({
                    spoolWt: sp_payload.spool_weight,
                    filamentWt: f_payload.spool_weight,
                    vendor,
                });
                if (resolved !== null && f_payload.spool_weight === null
                        && !wizardNativeCleared('fil', 'spool_weight')) {
                    f_payload.spool_weight = resolved;
                }
            }
            // Group 66.7: the filament box showing its brand's weight (untouched) is no
            // value of the filament's own: Edit Spool leaves it out, so the filament keeps
            // having none (every Save wrote the brand's weight as the filament's). A create
            // still takes it, as the new filament's (the cross-check's C15). An inherited box
            // the brand leaves empty keeps the cross-inherit's old rule: the spool's own
            // empty weight goes to a filament that has none.
            if (isWizardEdit && wizardFilEmptyWeightIsInherited() && getVal('wiz-fil-empty_weight') !== '') {
                delete f_payload.spool_weight;
            }

            // Note: Spoolman 0.19.1 natively supports `multi_color_hexes` 
            if (colors.length > 1) {
                f_payload.multi_color_direction = document.getElementById('wiz-fil-color-direction').value;
                f_payload.multi_color_hexes = colors.join(',');
                delete f_payload.color_hex; // FATAL ERROR PREVENTION: Spoolman schema prevents both
            } else {
                f_payload.multi_color_hexes = null;
                f_payload.multi_color_direction = null;
            }
            // Extract Custom Dynamic Fields (Standard and Checkboxes)
            document.querySelectorAll('.dynamic-extra-field').forEach(el => {
                const key = el.getAttribute('data-key');
                if (!key) return;

                // The label status has three states and a checkbox two: a box the
                // user didn't touch says nothing. Sent as drawn, it wrote "confirmed"
                // on a filament with no status at every Save (Group 58.5), and kept a
                // new filament out of the Backlog (the server flags one only when
                // the key is left out). The swatch status is the same: "No" on a
                // filament whose status is "unknown" (Group 58 review).
                if (['needs_label_print', 'sample_printed'].includes(key) && !wizardExtraTouched('fil', key)) return;

                if (el.type === 'checkbox') {
                    f_payload.extra[key] = el.checked;
                } else if (el.value) {
                    f_payload.extra[key] = el.value;
                } else if (isWizardEdit && wizardExtraTouched('fil', key)) {
                    // 23.4 — blank-to-clear on edit, only a field the user emptied
                    f_payload.extra[key] = window.FCC_DELETE_EXTRA;
                }
            });

            // Extract Custom Dynamic Fields (Chips)
            document.querySelectorAll('.dynamic-chip[data-selected="true"]').forEach(el => {
                const key = el.getAttribute('data-key');
                const val = el.getAttribute('data-value');
                if (!key || !val) return;

                if (!f_payload.extra[key]) f_payload.extra[key] = [];
                f_payload.extra[key].push(val);
            });
            // A chip field whose chips were all removed sent nothing above, and a
            // key left out keeps its old list (2026-10-21): on edit, clear it.
            if (isWizardEdit) window.wizardClearEmptyChipFields(f_payload.extra);

            // Vendor selection. The ➕ button now opens the Vendor Edit modal
            // in create mode and auto-selects the new vendor on save, so by the
            // time the user reaches submit there's always either a real
            // vendor_id selected or nothing (deliberate Generic). The legacy
            // extras.external_vendor_name path was retired in Group 6.2.
            if (getVal('wiz-fil-vendor-sel')) {
                const vid = parseInt(getVal('wiz-fil-vendor-sel'));
                vendorShown = vid;
                // Group 66.9 review (listeners S3): Edit Spool sends its filament's
                // manufacturer only when the person changed it, as Edit Filament does. Sent at
                // every Save, a box still holding one the filament had left (a merge that
                // stopped half-way, or one made in another tab) moved it back; and in the
                // moment before a merge's delete, onto the one being deleted, which Spoolman
                // then cleared. Left out, the filament keeps the one Spoolman has. The
                // baseline is the last Save's that landed (review round 2, R2P2 / R2X-1:
                // wizardSavedFilament); after a Save that carried one and whose filament
                // answer was lost, or that got no answer, the box's goes out whatever it shows
                // (`vendorUnsure`).
                if (!(isWizardEdit && filOrigSent && !wizardState.vendorUnsure
                        && String(filOrigSent.vendor_id) === String(vid))) {
                    f_payload.vendor_id = vid;
                }
            }

            if (wizardState.mode === 'external' && wizardState.externalMetaData) {
                const t = wizardState.externalMetaData;
                if (t.extruder_temp && !getVal('wiz-fil-settings_extruder_temp')) f_payload.settings_extruder_temp = t.extruder_temp;
                if (t.bed_temp && !getVal('wiz-fil-settings_bed_temp')) f_payload.settings_bed_temp = t.bed_temp;
                const extNozMax = (t.extra && t.extra.nozzle_temp_max) || t.nozzle_temp_max;
                const extBedMax = (t.extra && t.extra.bed_temp_max) || t.bed_temp_max;
                if (extNozMax && !getVal('wiz-fil-nozzle_temp_max')) f_payload.extra.nozzle_temp_max = `"${String(extNozMax)}"`;
                if (extBedMax && !getVal('wiz-fil-bed_temp_max')) f_payload.extra.bed_temp_max = `"${String(extBedMax)}"`;
                if (t.article_number) f_payload.article_number = t.article_number;
            }

            // A null is left out, except the two multi-colour keys (which clear a
            // single colour's old list) and, in edit mode, a plain box the user
            // emptied (a clear, Group 54.5).
            Object.keys(f_payload).forEach(k => {
                if (f_payload[k] === undefined || Number.isNaN(f_payload[k])) delete f_payload[k];
                else if (f_payload[k] === null && k !== 'multi_color_hexes' && k !== 'multi_color_direction'
                         && !wizardNativeCleared('fil', k)) delete f_payload[k];
            });
        }

        // Per-spool overrides from the Step-3 Prusament scan rows. When at least
        // one row scanned successfully, the backend uses the override list to drive
        // the spool count + per-spool field merge instead of `quantity`.
        let spool_overrides = null;
        if (wizardState.spoolRows && wizardState.spoolRows.length > 0) {
            const blocking = wizardState.spoolRows.some(r => r.status === 'pending' || r.status === 'error');
            if (blocking) {
                // Group 66.3 (B): Edit Spool's link check is still loading (a refusal never blocks).
                msg.innerHTML = wizardState.mode === 'edit_spool'
                    ? '<span class="text-danger fw-bold">⚠ The Prusament QR is still being checked. Save again in a moment.</span>'
                    : '<span class="text-danger fw-bold">⚠ One or more spool scans failed or are still loading. Fix or clear them before creating.</span>';
                document.getElementById('btn-wiz-submit').disabled = false;
                return;
            }
            const anyOk = wizardState.spoolRows.some(r => r.status === 'ok');
            if (anyOk && wizardState.mode !== 'edit_spool') {
                spool_overrides = wizardState.spoolRows.map(r => r.override || {});
            }
        }

        // Group 40.7 review (wizard-slotless-create-loads-empty-head): a box or a
        // printer the picker never opened for (Tab, typed, a Clone's pre-fill,
        // the next create after a pick was used up) opens it now, and nothing is
        // posted until the user picks. Derek's answer 7: the wizard's Location
        // behaves like Force Location, which always asks for the slot or head.
        if (window.wizardSaveNeedsPicker(sp_payload.location)) {
            const place = _wizLocKey(sp_payload.location);
            const rows = wizardState.allLocationRows || [];
            const row = rows.find(r => r && _wizLocKey(r.LocationID) === place) || null;
            const what = (window.isPrinterRowNotHead && window.isPrinterRowNotHead(row, rows)) ? 'toolhead' : 'slot';
            const search = document.getElementById('wiz-spool-location-search');
            msg.innerHTML = `<span class="text-info">Pick the ${what} in ${_wizEsc(place)}…</span>`;
            const out = await window.wizardLocationPicked(sp_payload.location,
                { value: sp_payload.location, label: search ? search.value : '' }, { quiet: true });
            if (!out || out.outcome !== 'moved') {
                msg.innerHTML = `<span class="text-warning fw-bold">Nothing was saved: pick a ${what} in `
                    + `${_wizEsc(place)} (or another Location), then Save again.</span>`;
                document.getElementById('btn-wiz-submit').disabled = false;
                return;
            }
            // A head the Printer picker chose is the Location now ("XL-3 (via XL)").
            sp_payload.location = getVal('wiz-spool-location') || '';
        }

        const payload = {
            spool_id: wizardState.editSpoolId, // Used by Edit router
            filament_id: target_fid,
            filament_data: f_payload,
            spool_data: sp_payload,
            quantity: qty,
            // Group 40.7: a Location is a move through the engine, which may ask
            // first; this page answers its questions (window.askMoveConfirm), so
            // every save carries the move doors' contract.
            confirmed_toolheads: [],
            confirmed_fed_heads: [],
        };
        if (spool_overrides) payload.spool_overrides = spool_overrides;
        if (usedBasedOn) payload.used_based_on = usedBasedOn;
        // The picker's choice for the Location (wizardState.pendingPlacement): an
        // edit sends its fields; a create sends one placement per new spool.
        const placement = wizardState.pendingPlacement;
        const editFields = isWizardEdit ? window.wizardPlacementFor(sp_payload.location, placement) : {};
        if (isWizardEdit) {
            Object.assign(payload, editFields);
        } else {
            payload.placements = window.wizardCreatePlacements(
                spool_overrides ? spool_overrides.length : qty, sp_payload.location, placement);
        }

        // Group 48.4: a suggested slicer profile that isn't a choice yet (a new
        // variant a Prusament page names) joins Spoolman's list before the
        // filament that uses it; if that fails, nothing is saved.
        if (!(await window.wizardCommitSuggestedChoices(f_payload))) {
            document.getElementById('btn-wiz-submit').disabled = false;
            return;
        }

        const endpoint = wizardState.mode === 'edit_spool' ? '/api/edit_spool_wizard' : '/api/create_inventory_wizard';

        vendorSentId = (f_payload && f_payload.vendor_id != null) ? String(f_payload.vendor_id) : null;
        posted = true;
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        answered = true;
        // Group 40.7: an edit whose other changes saved but whose Location didn't
        // move (the server asks first, or refused it) is a partial save: the
        // post-save steps below still run for what was saved.
        const partial = isWizardEdit && !data.success && data.spool_saved === true
            && Object.prototype.hasOwnProperty.call(data, 'location_result');
        const wizModal = document.getElementById('wizardModal');
        // Group 64 fix review 4 (UP5): the answer's per-form updates (the Archived box,
        // the Location field, Total Used's baseline, the dirty flag, the status line, the
        // label chip) only in the session that sent it: one opened since for another
        // spool took #57's figures as its own. What is about the spool itself (a move's
        // toast, the scan buffer, a refill's question, a create's placements) still runs.
        const sameForm = wizardState.session === session;
        const editSid = isWizardEdit ? (payload.spool_id != null ? payload.spool_id : wizardState.editSpoolId)
            : wizardState.editSpoolId;
        const savedLoc = _wizLocKey(sp_payload.location);

        if (data.success || partial) {
            // A partial save leaves the Location unsaved, so closing still warns.
            if (sameForm) wizardState.isDirty = partial;
            // 2026-10-20 review (engine-1): the Archived box follows the server. A box
            // still ticked after the spool came back into stock (a weight fix with a
            // move) sent archived: true on the next Save and archived it ON its head.
            if (isWizardEdit && sameForm && Object.prototype.hasOwnProperty.call(data, 'archived_now')) {
                const box = document.getElementById('wiz-spool-archived');
                if (box) box.checked = !!data.archived_now;
            }
            if (sameForm) {
                msg.innerHTML = partial
                    ? `<span class="text-warning fw-bold">Saved your other changes. #${_wizEsc(editSid)} was not moved yet.</span>`
                    : `<span class="text-success fw-bold">Success! ${isWizardEdit ? 'Spool Updated' : 'Spool(s) Generated'}.</span>`;
            } else if (!partial && typeof showToast === 'function') {
                // (A partial answer says its own words below: VP2.)
                showToast(isWizardEdit ? `Spool #${editSid} saved.` : 'New spool(s) created.', 'success', 4000);
            }
            // Group 42.3c: see inv_weigh_out.js (a weight fix that brought an
            // archived spool back, but its old toolhead holds another one now).
            // Group 40.7: a create's placements are reported spool by spool below
            // (`warning` sums them up for a page from before 40.7).
            const placementsReported = !isWizardEdit && data.location_results;
            if (data.warning && !placementsReported && typeof showToast === 'function') showToast(data.warning, 'warning', 7000);
            // Group 63.1: the Save weighed the spool back into stock (or unticked Archived)
            // after it left a toolhead, and the server moved it nowhere: ask where it goes,
            // over the wizard, and show where a move put it in the Location field, so the
            // next Save moves nothing (wizardAfterOwnWrite, below).
            if (isWizardEdit) wizardAfterOwnWrite(data, editSid, wizModal);
            // Group 64 review (S3): the box shows what this Save wrote, so the next
            // Save in this session sends it only if it changes again.
            if (isWizardEdit && sameForm) wizardSavedUsed(usedBoxSent, usedAddSent, usedReadSent);
            // Group 66.9 review round 2: the manufacturer's and the links' baselines are what
            // this Save sent (its filament write ran before any move, so a partial landed it).
            if (isWizardEdit && sameForm) {
                wizardSavedFilament(filOrigSent, vendorShown, f_payload);
                wizardSavedLinks(linksSent);
            }
            // Review round 1 (R4-02): the spool's link is saved; the row says so. Only the
            // link this Save carried (Group 66.9 review round 3, R3W8, older than 66.9: a QR
            // checked while the Save was out was marked saved, and its fills read as no
            // change: the form is still changed while the row waits for a Save).
            if (isWizardEdit && sameForm) {
                window.wizardSettleLinkRow(linksSent);
                const row0 = (wizardState.spoolRows || [])[0];
                if (row0 && row0.status === 'linked-new') wizardState.isDirty = true;
            }
            if (isWizardEdit && data.location_moved) {
                // Group 40.7: where the Location move put it, in short arrows.
                const lr = data.location_result;
                const rec = (lr && typeof lr === 'object' && lr.recorded_source)
                    ? String(lr.recorded_source).split(':') : null;
                showToast(`✅ #${editSid} → ${data.location_where || savedLoc || 'Unassigned'}`
                    + `${rec && rec.length === 2 ? ` (recorded as from ${rec[0]} slot ${rec[1]})` : ''}`, 'success', 4000);
                window.takeIntoBuffer(data);
                // Group 40.7 review (wizard-resave-unloads-head): the field shows
                // where the spool is now (the head its slot loaded, say), so a
                // second Save in this session moves nothing. It kept the box, and
                // a second Save stored the spool back in it, unloading the head.
                const now = Object.prototype.hasOwnProperty.call(data, 'location_now') ? data.location_now
                    : (savedLoc ? ((lr && typeof lr === 'object' && lr.auto_deployed_to) || savedLoc) : '');
                if (sameForm) {
                    wizardState.pendingPlacement = null;
                    window.wizardShowLocation(now);
                    wizardState.editSpoolLocation = _wizLocKey(now);
                }
                document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
            }
            // Group 40.7 review: a create used the held choice up. The field shows
            // its place again (the box, or the printer whose head it was), so
            // the next create opens the picker instead of reusing a slot label
            // ("— LR-MDB-1 slot 2") it would no longer send.
            if (!isWizardEdit && sameForm && placement && _wizLocKey(placement.location) === savedLoc) {
                wizardState.pendingPlacement = null;
                window.wizardShowLocation(placement.via || placement.location);
            }
            if (!partial && sameForm) wizardState.pendingPlacement = null;
            // 17.3 follow-up: render queue-label chips into the dedicated
            // `wiz-postcreate-actions` row in the modal footer (alongside
            // Cancel + Create Inventory) so subsequent status-message
            // overwrites — like the post-success "Make a change to add
            // more..." auto-prompt three seconds later — can't clobber
            // them before the user gets a chance to click. Only fires
            // on create (edit-spool mode doesn't carry created_spools).
            // 25.H — render the post-save queue-label affordances (per-spool
            // chips + "Queue All" for multi-create; a chip for the edited spool
            // in edit mode). Extracted to a helper so it's unit-testable.
            if (sameForm) {
                window.wizardRenderPostSaveQueueActions(
                    wizardState.mode, data.created_spools, wizardState.editSpoolId);
            }
            document.dispatchEvent(new CustomEvent('inventory:sync-pulse')); // Instantly trigger UI rebinding across all open panels

            // 23.3 — if this edit_spool save changed a label-bearing FILAMENT
            // field (color/RGB, Name, Vendor, Material, Type), the printed swatch
            // is now stale. Reuse the Edit-Filament reprint nudge (it self-gates
            // on the prior needs_label_print === false).
            // Fix review 5 (VP1): in any session, from the filament as this Save's form
            // opened it: the spools' labels are the filament's, and the nudge names it.
            if (isWizardEdit && f_payload && target_fid && filOrigSent
                    && typeof window._maybePromptLabelReprint === 'function') {
                const orig = filOrigSent;
                // 25.3 — shared diff (includes original_color now); see
                // window.wizardBuildFilamentLabelDiff.
                const shownPayload = (vendorShown != null && f_payload.vendor_id == null)
                    ? Object.assign({}, f_payload, { vendor_id: vendorShown }) : f_payload;
                const { changedNative, changedExtras } =
                    window.wizardBuildFilamentLabelDiff(orig, shownPayload);
                window._maybePromptLabelReprint(
                    target_fid,
                    f_payload.name || `Filament #${target_fid}`,
                    changedNative, changedExtras, orig.extra,
                );
            }

            // Reset Weigh-Out Protocol tracking on save so subsequent saves don't double-dip
            if (isWizardEdit && sameForm) {
                const recentInput = document.getElementById('wiz-spool-recent-usage');
                if (recentInput && recentInput.value) {
                    recentInput.value = '';
                    wizardState.original_used_weight = parseFloat(document.getElementById('wiz-spool-used').value) || 0;
                    
                    // Visual feedback flash (accounting for Bootstrap !important classes)
                    const remInput = document.getElementById('wiz-spool-remaining');
                    if (remInput) {
                        remInput.style.transition = "background-color 0.4s ease-out";
                        remInput.classList.remove('bg-dark');
                        remInput.classList.add('bg-success', 'text-white');
                        setTimeout(() => { 
                            remInput.classList.remove('bg-success', 'text-white');
                            remInput.classList.add('bg-dark'); 
                        }, 800);
                    }
                }
            }

            // Keep modal open across all modes so user can rapidly create subsequent items —
            // but don't let them accidentally re-submit the same spools. After a non-edit
            // success, clear the per-spool scan URLs + reset bulk quantity to 1 + leave
            // submit disabled until the user makes a change. The existing input/change
            // listener flips lockedAfterSuccess off and re-enables submit on next edit.
            if (!isWizardEdit) {
                if (sameForm) {
                    wizardState.lockedAfterSuccess = true;
                    // Reset quantity FIRST so the row reset rebuilds at the new size.
                    // Reversed order rebuilt rows at the OLD count and left submit
                    // enabled because the row sync re-ran wizardValidateSubmit.
                    const qtyEl = document.getElementById('wiz-spool-qty');
                    if (qtyEl) qtyEl.value = 1;
                    if (window.wizardResetSpoolRows) window.wizardResetSpoolRows();
                    setTimeout(() => {
                        if (wizardState.lockedAfterSuccess) {
                            msg.innerHTML = `<span class="text-info">Make a change to add more — submit is locked until you scan, edit, or pick a new filament.</span>`;
                        }
                    }, 3000);
                }
                // Submit stays disabled. The dirty-listener below re-enables it when
                // the user edits any field in the wizard.
                // Group 40.7: what each new spool's placement did, questions one at
                // a time; then the spools a picked box slot left Unassigned go to
                // the per-spool picker loop (Claude's call 29) when one is installed.
                // Group 40.7 review (wizard-stale-pick-via-reopens-picker): only a
                // choice made for the saved Location counts (wizardPlacementFor's
                // rule), and a blank Location places nothing: those spools were
                // meant to stay Unassigned.
                const usedPick = (placement && _wizLocKey(placement.location) === savedLoc) ? placement : null;
                if (data.location_results) {
                    window.wizardSettleCreatePlacements(data, {
                        host: wizModal,
                        pick: usedPick,
                        onDone: (remaining) => {
                            if (!remaining.length || !savedLoc) return;
                            if (typeof window.wizardPlaceRemaining === 'function') {
                                window.wizardPlaceRemaining({ spoolIds: remaining, location: savedLoc, placement: usedPick, data });
                            } else {
                                showToast(`${remaining.length} new spool${remaining.length === 1 ? ' is' : 's are'} `
                                    + `Unassigned (${remaining.map(id => '#' + id).join(', ')}): scan or Force Location `
                                    + `${remaining.length === 1 ? 'it' : 'them'} into place.`, 'info', 7000);
                            }
                        },
                    });
                }
            } else if (partial && !sameForm) {
                // Fix review 4 (UP5): no question over the form of a spool opened since. Fix
                // review 5 (VP2): what is about the spool itself still runs: a Swap's old
                // spool into this page's scan buffer (its next buffer save would drop it
                // otherwise), and a refusal's own words, as wizardEditLocationNotMoved says them.
                window.takeIntoBuffer(data);
                const lr = data.location_result;
                const asks = lr && typeof lr === 'object' && lr.status === 'requires_confirm' && !data.stale_page;
                if (typeof showToast === 'function') {
                    showToast(asks
                        ? `Saved your other changes to #${editSid}, but it was not moved: open it in Edit Spool and Save again to move it.`
                        : `❌ ${data.msg || `Saved your other changes, but #${editSid} was not moved.`}`,
                        asks ? 'warning' : 'error', 7000);
                }
                if (!asks && window.logClientEvent) window.logClientEvent(`❌ Wizard edit: ${data.msg || 'not moved'}`, 'ERROR');
            } else if (partial) {
                // Group 40.7: the other edits are saved; the Location needs an answer,
                // or was refused (7 s error). Submit stays usable to try again.
                const btn = document.getElementById('btn-wiz-submit');
                window.wizardEditLocationNotMoved(data, {
                    spoolId: editSid, location: savedLoc, fields: editFields, host: wizModal,
                    placement: Object.keys(editFields).length ? placement : null,
                    noStore: !!(placement && placement.noStore),
                    onDone: (outcome, res, info) => {
                        if (outcome === 'moved') {
                            wizardState.isDirty = false;
                            wizardState.pendingPlacement = null;
                            // Group 40.7 review (wizard-resave-unloads-head): where
                            // the answered move put it (the head its slot loaded, or
                            // the place itself), so a second Save moves nothing.
                            const now = savedLoc ? ((res && res.auto_deployed_to) || savedLoc) : '';
                            window.wizardShowLocation(now);
                            wizardState.editSpoolLocation = _wizLocKey(now);
                            msg.innerHTML = `<span class="text-success fw-bold">Success! Spool Updated.</span>`;
                            document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
                            setTimeout(() => { msg.innerHTML = ""; if (btn) btn.disabled = false; }, 3000);
                        } else {
                            const why = outcome === 'refused'
                                ? ((res && res.msg) || data.msg || `Saved your other changes, but #${editSid} was not moved.`)
                                    + ((info && info.tail) || '')
                                : outcome === 'cancelled'
                                    ? `Saved your other changes. #${editSid} was not moved: Save again to move it.`
                                    : `Saved your other changes, but #${editSid} was not moved (see the error). Save again to retry.`;
                            msg.innerHTML = `<span class="text-${outcome === 'cancelled' ? 'warning' : 'danger'}">${_wizEsc(why)}</span>`;
                            if (btn) btn.disabled = false;
                        }
                    },
                });
            } else if (sameForm) {
                setTimeout(() => {
                    msg.innerHTML = "";
                    document.getElementById('btn-wiz-submit').disabled = false;
                }, 3000);
            }

        } else {
            if (sameForm) {
                msg.innerHTML = `<span class="text-danger">Error: ${_wizEsc(data.msg)}</span>`;
                document.getElementById('btn-wiz-submit').disabled = false;
            } else if (typeof showToast === 'function') {
                // Fix review 4 (UP5): the form shows another spool now. Fix review 5 (VP3): an
                // answer whose spool write landed (the filament's refused) says the server's
                // own words, never that the spool wasn't saved (a person told so does it again).
                // Its own words whatever they say (a lost answer's "Couldn't tell whether
                // Spool #57 saved" too), as the form's status line would have shown them.
                showToast(data.msg
                    ? `${isWizardEdit ? `Spool #${editSid}` : 'New spool(s)'}: ${data.msg}`
                    : `${isWizardEdit ? `Spool #${editSid} wasn't saved` : "The new spool(s) weren't created"}: `
                      + 'see the Activity Log', 'error', 7000);
            }
            // Group 63 review (C4): the spool's own write landed before the filament
            // was refused: the Archived box, the Location field and a refill's
            // question follow what it did (its note is used up: nobody asks later).
            if (isWizardEdit && data.spool_saved === true) {
                if (sameForm && Object.prototype.hasOwnProperty.call(data, 'archived_now')) {
                    const box = document.getElementById('wiz-spool-archived');
                    if (box) box.checked = !!data.archived_now;
                }
                wizardAfterOwnWrite(data, editSid, wizModal);
                // Group 64 fix review 2 (CP6): the spool's own write landed, its Total Used
                // with it, so the box shows what is saved (S3's rule, which only a Save that
                // succeeded kept): the retry sends the used weight only if it changes again,
                // never this one over a print's charge that landed in between, nor a second
                // weighing's stamp.
                if (sameForm) wizardSavedUsed(usedBoxSent, usedAddSent, usedReadSent);
                // Group 66.9 review round 2: the links went with the spool's write (R2X-3),
                // and the row says so (round 3, R3W2: it still read "Links at Save", its ✕
                // put the boxes back, and the next Save cleared the saved links).
                if (sameForm) {
                    wizardSavedLinks(linksSent);
                    window.wizardSettleLinkRow(linksSent);
                }
            }
            // The filament's answer was lost (it may have landed): the next Save sends the
            // Vendor box's manufacturer, when this one carried one, whatever the spool's write
            // did (Group 66.9 review round 3, R3S1 / R3W1: a manufacturer-only Save writes no
            // spool, answers spool_saved false, and its doubt went unnoticed).
            if (isWizardEdit && sameForm && data.filament_may_have_saved && vendorSentId != null) {
                wizardState.vendorUnsure = true;
            }
        }
    } catch (e) {
        console.error("Wizard Submit Error:", e);
        if (wizardState.session !== session) {
            // Fix review 5 (VP4): the form shows another spool now: no word of this Save on
            // it, and no button of it touched. Its spool's write may have landed.
            if (typeof showToast === 'function') {
                showToast(editAtSave
                    ? `FCC didn't answer #${sidAtSave}'s Save, so it may or may not have landed: open it in Edit Spool to check.`
                    : "FCC didn't answer the Save of the new spool(s), so they may or may not have been created: search for them before creating them again.",
                    'error', 7000);
            }
            return;
        }
        const why = _wizEsc(e && e.message ? e.message : e);
        msg.innerHTML = !posted
            ? `<span class="text-danger">Frontend Error: ${why}. Nothing was sent.</span>`
            : (answered
                ? `<span class="text-danger">FCC answered the Save, but this page hit an error showing it (${why}): open the spool again to check it.</span>`
                : `<span class="text-danger">FCC didn't answer this Save, so it may or may not have landed (${why}). Save again to send it again.</span>`);
        document.getElementById('btn-wiz-submit').disabled = false;
        // Group 66.9 review rounds 2-3: a Save that went out and got no answer FCC could
        // read may have landed, so what it sent (and only that) goes out at the next Save
        // whatever the boxes show: its manufacturer (vendorUnsure) and its link boxes.
        if (editAtSave && posted && !answered) {
            if (vendorSentId != null) wizardState.vendorUnsure = true;
            if (linkKeysSent.length && wizardState.linkShown) {
                const ls = Object.assign({}, wizardState.linkShown);
                linkKeysSent.forEach((k) => { ls[k] = WIZ_LINK_UNSURE; });
                wizardState.linkShown = ls;
            }
        }
    }
};

// Group 66.2: a Save on its way, by its session, for the opener's guard (openWizardModal
// says "the wizard is saving" and starts nothing over under it). Cleared when the Save
// is answered (or fails), whatever the form shows by then.
window.wizardSubmit = async () => {
    const session = wizardState.session;
    wizardState.saving = session;
    try {
        return await _wizardSubmitInner();
    } finally {
        if (wizardState.saving === session) wizardState.saving = null;
    }
};

// Group 63 review (K01 / K02 / C4): what an Edit Spool Save's own write did to where
// the spool is, shown in the Location field (`location_now`, sent when no Location
// move was asked: a refill took the spool off the head it was archived on, or put it
// back where its note says; an archive took it off its place), and a refill's
// question asked over the wizard. The field kept the old place, and the next Save,
// which sends the field, moved the spool back: onto its head, unloading the spool
// loaded there since. Where a move the question made landed (the head a slot loaded,
// the slot's box, the place) goes in the field too, so a second Save moves nothing.
const wizardAfterOwnWrite = (data, editSid, wizModal) => {
    const showHere = (where) => {
        if (String(wizardState.editSpoolId) !== String(editSid)) return;
        window.wizardShowLocation(where || '');
        wizardState.editSpoolLocation = _wizLocKey(where || '');
    };
    if (!data.location_moved && Object.prototype.hasOwnProperty.call(data, 'location_now')) {
        showHere(data.location_now);
    }
    if (data.refill_ask && typeof data.refill_ask === 'object' && typeof window.askRefillPlace === 'function') {
        window.askRefillPlace(editSid, data.refill_ask, { host: wizModal, onMoved: (where) => showHere(where) });
    }
};

// --- SPOOL CLONE LOGIC ---
// Group 10.11: source-aware return-id — only set when an actual details modal is visible
// at launch. Opened from search / grid / location manager it leaves both null, so the
// wizard closes silently on cancel rather than popping an unexpected details modal.
// Group 66.2: read before openWizardModal (which hides those windows) and applied only
// once it answers true: kept editing, the open wizard keeps its own return target.
const _wizReturnTarget = (spoolId) => {
    const filModal = document.getElementById('filamentModal');
    const spoolModal = document.getElementById('spoolModal');
    if (filModal && filModal.classList.contains('show')) {
        const fid = document.getElementById('fil-detail-id')?.innerText;
        if (fid) return { returnToFilamentId: fid, returnToSpoolId: null };
        return {};
    }
    if (spoolModal && spoolModal.classList.contains('show')) return { returnToSpoolId: spoolId, returnToFilamentId: null };
    return { returnToSpoolId: null, returnToFilamentId: null };
};

// Group 66.2: each opener answers false, having changed nothing, when the open wizard was
// kept as it was (Keep Editing, a Save on its way); its prefill belongs to its own
// session (an answer that lands after the wizard was opened again changes nothing), and
// wizardState.prefilling says one is loading (a Prusament QR then feeds no Spool box).
window.openCloneWizard = async (spoolId) => {
    const ret = _wizReturnTarget(spoolId);
    // Reset and Open Wizard (Wait for Extrad fields DOM injection!)
    if (!(await openWizardModal({ prefilling: 'clone' }))) return false;
    Object.assign(wizardState, ret);
    const session = wizardState.session;
    const mine = () => wizardState.session === session;
    wizardState.prefilling = 'clone';
    wizardSetContextLabel({ action: 'Cloning', spoolId });

    // Temporarily disable submit while fetching clone data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Cloning spool data...</span>';

    // Fetch Spool data to clone
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            if (!mine()) return;
            if (!d || !d.filament) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch clone data.</span>';
                return;
            }

            // Switch to Existing Filament Mode without wiping
            wizardSelectType('existing', true);

            // Inject Filament into Dropdown & Auto-Select
            const f = d.filament;
            wizardSetContextLabel({ action: 'Cloning from', spoolId, filamentId: f.id });
            const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
            const sel = document.getElementById('wiz-existing-results');
            sel.innerHTML = `<option value="${f.id}" selected>${name} (ID: ${f.id})</option>`;
            wizardExistingSelected();

            // Pre-fill Spool parameters that usually carry over when cloning.
            // Group 40.7 (Claude's call 28): not the Location of a spool loaded on a
            // toolhead or filed on a Printer row. Save now moves the copy through
            // the engine, which would unload the original to load the copy (or
            // refuse a printer row); the copy starts Unassigned instead.
            let cloneLocBlanked = '';
            {
                const rows = (wizardState.allLocationRows && wizardState.allLocationRows.length)
                    ? wizardState.allLocationRows
                    : ((typeof state !== 'undefined' && state && Array.isArray(state.allLocations)) ? state.allLocations : []);
                const blank = window.wizardCloneStartsBlank(d, rows);
                if (blank) cloneLocBlanked = String(d.location || '');
                const locId = blank ? "" : (d.location || "");
                const locRec = (wizardState.locations || []).find(l => l.LocationID === locId);
                window.wizardComboboxSet(
                    'wiz-spool-location-search', 'wiz-spool-location', locId,
                    locRec ? (locRec.Name ? `${locRec.Name} (${locRec.LocationID})` : locRec.LocationID) : locId
                );
            }
            // Spool Weight: walk Spool → Filament → Vendor so a clone picks up whichever level is populated.
            {
                const { value, source } = resolveEmptySpoolWeightSource({
                    spoolWt: d.spool_weight,
                    filamentWt: d.filament?.spool_weight,
                    vendor: d.filament?.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source, d.filament?.vendor);
            }
            document.getElementById('wiz-spool-used').value = 0; // Fresh spool is usually 0
            document.getElementById('wiz-spool-comment').value = d.comment || "";
            // Price & Purchase Link
            window.wizardPrefillSpoolPrice(d.price, d.filament && d.filament.price);
            // Group 54 review (R2-1, R2-3): what the boxes show from the filament
            // follows a filament picked from here on (never the source spool's own).
            wizardState.spoolBoxesFollowFilament = true;
            // Group 10.4 smart fallback: only prefill with the spool's OWN
            // purchase_url. If the spool has none but the filament does,
            // surface the filament URL as ghost placeholder text — saving
            // without typing leaves the spool override blank so the details
            // modal continues to fall back to the filament's value.
            wizardApplyPurchaseLinkFallback(d.extra?.purchase_url, d.filament?.extra?.purchase_url);
            wizardApplyProductLinkFallback(d.extra?.product_url, d.filament?.extra?.product_url);
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = false;
            }
            window.wizardCalcRemainingFromUsed();

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Wizard successfully pre-filled from Spool #${spoolId}.</span>`
                + (cloneLocBlanked
                    ? ` <span class="text-info">Location left blank: #${_wizEsc(spoolId)} is on ${_wizEsc(cloneLocBlanked)}, so pick where the copy goes.</span>`
                    : '');
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            if (!mine()) return;
            console.error("Clone Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect for clone.</span>';
            document.getElementById('btn-wiz-submit').disabled = false;
        })
        .finally(() => { if (mine()) wizardState.prefilling = null; });
    return true;
};

// --- NEW SPOOL FROM FILAMENT LOGIC ---
window.openNewSpoolFromFilamentWizard = async (filamentId) => {
    // Reset and Open Wizard (Wait for Extra fields DOM injection!)
    if (!(await openWizardModal({ prefilling: 'new' }))) return false;
    // Track filament for re-opening detail modal after wizard closes
    wizardState.returnToFilamentId = filamentId;
    wizardState.returnToSpoolId = null;
    const session = wizardState.session;
    const mine = () => wizardState.session === session;
    wizardState.prefilling = 'new';
    wizardSetContextLabel({ action: 'New Spool for', filamentId });

    // Temporarily disable submit while fetching data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Loading filament data...</span>';

    fetch(`/api/filament_details?id=${filamentId}`)
        .then(r => r.json())
        .then(d => {
            if (!mine()) return;
            if (!d || !d.id) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch filament data.</span>';
                return;
            }

            // Switch to Existing Filament Mode without wiping
            wizardSelectType('existing', true);

            // Inject Filament into Dropdown & Auto-Select
            const name = `${d.vendor?.name || 'Generic'} ${d.material} - ${d.name || 'Unknown'}`;
            const sel = document.getElementById('wiz-existing-results');
            sel.innerHTML = `<option value="${d.id}" selected>${name} (ID: ${d.id})</option>`;
            wizardExistingSelected();

            // Smart defaults for fresh spool
            document.getElementById('wiz-spool-used').value = 0;
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = false;
            }

            // L34: pre-fill spool empty-weight from filament/vendor cascade on
            // open. New spools have no spool_weight of their own yet, so the
            // resolved source will be 'filament' or 'vendor' — show the badge
            // so the user knows where the value came from.
            {
                const { value, source } = resolveEmptySpoolWeightSource({
                    filamentWt: d.spool_weight,
                    vendor: d.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source, d.vendor);
            }
            // L349: a brand-new spool has no price of its own — inherit the
            // filament's (d is the filament here, so d.price is the fallback).
            window.wizardPrefillSpoolPrice(null, d.price);
            // Group 54 review (R2-1, R2-3): what the boxes show from the filament
            // follows a filament picked from here on.
            wizardState.spoolBoxesFollowFilament = true;
            // L351: show the filament's product link as inherited ghost text.
            wizardApplyProductLinkFallback(null, d.extra?.product_url);

            window.wizardCalcRemainingFromUsed();

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Wizard successfully pre-filled from Filament #${filamentId}.</span>`;
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            if (!mine()) return;
            console.error("New Spool from Filament Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect.</span>';
            document.getElementById('btn-wiz-submit').disabled = false;
        })
        .finally(() => { if (mine()) wizardState.prefilling = null; });
    return true;
};

// --- SPOOL EDIT LOGIC ---
window.openEditWizard = async (spoolId) => {
    // Group 10.11: only re-open a details modal on cancel/close if one was ACTUALLY
    // visible at launch (_wizReturnTarget; Group 66.2: applied only once the wizard opens).
    const ret = _wizReturnTarget(spoolId);
    // Reset and Open Wizard (Wait for dynamically mapped DOM structures first!)
    if (!(await openWizardModal({ prefilling: 'edit' }))) return false;
    Object.assign(wizardState, ret);
    const session = wizardState.session;
    const mine = () => wizardState.session === session;
    wizardState.prefilling = 'edit';
    wizardSetContextLabel({ action: 'Editing', spoolId });

    // Temporarily disable submit while fetching edit data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Loading spool data for edit...</span>';

    // Change Button Text
    const submitBtn = document.getElementById('btn-wiz-submit');
    submitBtn.innerText = "SAVE CHANGES";
    submitBtn.classList.replace('btn-success', 'btn-primary');

    // Fetch Spool data to edit
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            if (!mine()) return;
            if (!d || !d.filament) {
                // Fix review 5 (VP5): no Save on a form that never loaded (see the catch).
                wizardState.editLoadFailed = true;
                submitBtn.disabled = true;
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch spool data: '
                    + 'close this window and open Edit Spool again.</span>';
                return;
            }

            // Custom UI State for Edit
            wizardState.mode = 'edit_spool';
            wizardState.editSpoolId = spoolId;
            wizardState.selectedFilamentId = d.filament.id;
            wizardSetContextLabel({ action: 'Editing', spoolId, filamentId: d.filament.id });

            // Hide Step 1 completely
            const step1 = document.getElementById('step-1-material');
            if (step1) step1.style.display = 'none';
            // Show Step 2 and Step 3
            document.getElementById('step-2-filament').style.display = 'block';
            document.getElementById('step-3-spool').style.display = 'block';
            document.getElementById('step-3-spool').style.opacity = '1';

            // Hide the Bulk Quantity box
            const qtyBox = document.getElementById('wiz-spool-qty');
            if (qtyBox && qtyBox.parentElement) qtyBox.parentElement.style.display = 'none';
            if (qtyBox) qtyBox.value = 1;
            // Group 66.3 (Derek's (B)): the Prusament box links this spool to its QR.
            const rowsLabel = document.getElementById('wiz-spool-rows-label');
            if (rowsLabel) rowsLabel.textContent = WIZ_ROWS_LABEL_EDIT;
            if (window.wizardResetSpoolRows) window.wizardResetSpoolRows();
            if (window.wizardRenderLinkNote) window.wizardRenderLinkNote();

            const f = d.filament;
            // 23.3 — snapshot the label-bearing filament fields at edit-open so
            // the save can detect a swatch-invalidating change and reuse the
            // reprint nudge (same prompt + needs_label_print gate as the
            // Edit-Filament modal). Values are normalized to match the diff done
            // against f_payload at submit time.
            wizardState.editFilamentOriginal = {
                name: f.name || '',
                material: f.material || '',
                vendor_id: (f.vendor && f.vendor.id != null) ? String(f.vendor.id) : '',
                color_hex: String(f.color_hex || '').replace(/^#/, '').toLowerCase(),
                multi_color_hexes: String(f.multi_color_hexes || '').replace(/[#\s]/g, '').toLowerCase(),
                multi_color_direction: String(f.multi_color_direction || '').toLowerCase(),
                extra: f.extra || {},
            };
            // Pre-fill Filament
            if (f.vendor) {
                // Group 66.1: the filament's own manufacturer, by its id. By name, the first
                // in the list took the box, and a Save of a filament on Sunlu #35 moved it
                // onto Sunlu #4. A list that couldn't be read still knows it, from the
                // filament's record. Only a record with no id is looked up by name.
                let match = null;
                if (f.vendor.id != null) {
                    match = (wizardState.vendors || []).find(v => v && String(v.id) === String(f.vendor.id)) || null;
                    if (!match) {
                        match = f.vendor;
                        wizardState.vendors = (wizardState.vendors || []).concat([f.vendor]);
                        _wizBindVendorCombobox();
                    }
                } else {
                    match = _wizVendorNamed(f.vendor.name);
                }
                if (match) {
                    window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', String(match.id), match.name || '');
                } else {
                    // Vendor on the source record isn't in the local cache.
                    // Leave the name in the search box so the user can either
                    // pick a close match or click ➕ to create. (Legacy
                    // add-new toggle was retired with Group 6.2 cleanup.)
                    const searchEl = document.getElementById('wiz-fil-vendor-search');
                    if (searchEl) searchEl.value = f.vendor.name || '';
                    window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '', f.vendor.name || '');
                }
            } else {
                window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '', '');
            }

            document.getElementById('wiz-fil-material').value = f.material || '';
            document.getElementById('wiz-fil-color_name').value = f.name || '';
            
            let colorPayload = f.multi_color_hexes || (f.extra && f.extra.color_hexes) || f.color_hex || 'FFFFFF';
            let colorDirection = f.multi_color_direction || (f.extra && f.extra.multi_color_direction) || 'longitudinal';
            if (window.wizardPopulateColors) window.wizardPopulateColors(colorPayload, colorDirection);
            
            document.getElementById('wiz-fil-diameter').value = f.diameter || 1.75;
            document.getElementById('wiz-fil-density').value = f.density || 1.24;
            document.getElementById('wiz-fil-weight').value = f.weight || 1000;
            {
                // The filament's own empty weight, else its brand's (blank and 0 are none),
                // marked "↩ from vendor" (Group 66.7): Save leaves the brand's out, so the
                // filament keeps having none of its own. The brand is the record the Vendor
                // box holds (the list's, read at this open). A filament with none of its own
                // follows its brand even while the brand gives nothing (review round 2, Q2-03).
                const { value, source } = resolveEmptySpoolWeightSource({
                    filamentWt: f.spool_weight,
                    vendor: _wizSelectedVendor() || f.vendor,
                });
                window.wizardSetFilEmptyWeightInherited(value, source === 'filament' ? 'filament' : 'vendor');
            }

            // Map Temperatures
            if (document.getElementById('wiz-fil-settings_extruder_temp')) {
                document.getElementById('wiz-fil-settings_extruder_temp').value = f.settings_extruder_temp || '';
            }
            if (document.getElementById('wiz-fil-settings_bed_temp')) {
                document.getElementById('wiz-fil-settings_bed_temp').value = f.settings_bed_temp || '';
            }
            if (document.getElementById('wiz-fil-nozzle_temp_max')) {
                const nozMax = f.extra && f.extra.nozzle_temp_max;
                document.getElementById('wiz-fil-nozzle_temp_max').value = typeof nozMax === 'string' ? nozMax.replace(/^"|"$/g, '') : (nozMax || '');
            }
            if (document.getElementById('wiz-fil-bed_temp_max')) {
                const bedMax = f.extra && f.extra.bed_temp_max;
                document.getElementById('wiz-fil-bed_temp_max').value = typeof bedMax === 'string' ? bedMax.replace(/^"|"$/g, '') : (bedMax || '');
            }

            // Filament Extra
            if (f.extra) {
                Object.entries(f.extra).forEach(([k, v]) => {
                    const input = document.getElementById(`wiz_fil_ef_${k}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = v === true || v === 'true';
                        } else if (input.classList.contains('sync-source-fil') && document.getElementById(`chip-container-fil-${k}`)) {
                            // Populate chips by the server's one reading (Group 66.6,
                            // window.fccFilamentAttrs): a value encoded twice kept its quotes
                            // here ('"Silk' and 'Matte"'), and a repeat made two chips.
                            const parsedArr = window.fccFilamentAttrs(v);

                            const cContainer = document.getElementById(`chip-container-fil-${k}`);
                            cContainer.innerHTML = '';
                            parsedArr.forEach(val => {
                                // HTML text, as wizardAddMultiChoiceChip's (Group 54 review, S2).
                                const chipHtml = `<span class="badge rounded-pill text-bg-primary border border-primary cursor-pointer dynamic-chip"
                                                       onclick="this.remove()" data-key="${k}" data-selected="true" data-value="${_wizEscape(val)}">${_wizEscape(val)} &times;</span>`;
                                cContainer.insertAdjacentHTML('beforeend', chipHtml);
                            });
                        } else {
                            input.value = v;
                        }
                    }
                });
            }

            // Pre-fill Spool
            {
                const locId = d.location || "";
                const locRec = (wizardState.locations || []).find(l => l.LocationID === locId);
                window.wizardComboboxSet(
                    'wiz-spool-location-search', 'wiz-spool-location', locId,
                    locRec ? (locRec.Name ? `${locRec.Name} (${locRec.LocationID})` : locRec.LocationID) : locId
                );
                // Group 40.7 review: where it is now, for Save's picker rule.
                wizardState.editSpoolLocation = _wizLocKey(locId);
            }
            {
                // Walk the chain: spool → filament → vendor. A blank spool inherits
                // from its filament, then its manufacturer's empty_spool_weight.
                const { value, source } = resolveEmptySpoolWeightSource({
                    spoolWt: d.spool_weight,
                    filamentWt: d.filament?.spool_weight,
                    vendor: d.filament?.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source, d.filament?.vendor);
            }
            document.getElementById('wiz-spool-initial_weight').value = d.initial_weight !== null ? d.initial_weight : "";
            // buglist L51: format the prefilled used to the PRECISE tier so it
            // (a) doesn't show float noise like "150.40000001" and (b) reconciles
            // with the remaining field derived by wizardCalcRemainingFromUsed below.
            document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(d.used_weight || 0);
            wizardState.usedShown = document.getElementById('wiz-spool-used').value;
            
            // WEIGH-OUT PROTOCOL: Store original value and show input
            wizardState.original_used_weight = d.used_weight || 0;
            const usageContainer = document.getElementById('container-wiz-spool-recent-usage');
            if (usageContainer) usageContainer.style.display = 'block';

            document.getElementById('wiz-spool-comment').value = d.comment || "";
            // Price & Purchase Link
            window.wizardPrefillSpoolPrice(d.price, d.filament && d.filament.price);
            // Group 10.4 smart fallback (same as clone path above).
            wizardApplyPurchaseLinkFallback(d.extra?.purchase_url, d.filament?.extra?.purchase_url);
            wizardApplyProductLinkFallback(d.extra?.product_url, d.filament?.extra?.product_url);
            // What the link boxes showed, for Save (review round 1 of Group 66, R3-03).
            wizardState.linkShown = {
                purchase_url: (document.getElementById('wiz-spool-purchase_url') || {}).value || '',
                product_url: (document.getElementById('wiz-spool-product_url') || {}).value || '',
            };
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = d.archived || false;
            }
            window.wizardCalcRemainingFromUsed();

            // Spool Extra
            if (d.extra) {
                Object.entries(d.extra).forEach(([k, v]) => {
                    const input = document.getElementById(`wiz_spool_ef_${k}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = v === true || v === 'true';
                        } else {
                            input.value = v;
                        }
                    }
                });
            }

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Editing Spool #${spoolId}.</span>`;
            submitBtn.disabled = false;
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            if (!mine()) return;
            console.error("Edit Wizard Error:", err);
            // Group 64 fix review 5 (VP5): the form never loaded (it is still wizardReset's
            // create form under a SAVE CHANGES label, or half filled), so it offers no Save:
            // enabled here, a press after "Failed to connect" created an "Unknown" filament
            // and spool. Opening the wizard again starts afresh.
            wizardState.editLoadFailed = true;
            submitBtn.disabled = true;
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect for edit: '
                + 'close this window and open Edit Spool again.</span>';
        })
        .finally(() => { if (mine()) wizardState.prefilling = null; });
    return true;
};

// --- PER-SPOOL PRUSAMENT SCAN (Step 3) ---
// One row per spool, driven by `wiz-spool-qty`. Each row holds an optional
// Prusament URL; a successful scan provides per-spool overrides that ride
// alongside spool_data when the wizard submits. The first scan in `manual`
// mode also fills Step 2 (filament template) — unless a matching filament
// already exists in Spoolman, in which case the wizard auto-switches into
// `existing` mode against the match. Failed scans block submit until cleared.

wizardState.spoolRows = [];
wizardState.filamentLockedFromScan = false;

const _normalizeStr = (s) => (s || '').toString().trim().toLowerCase();

// Pull the canonical filament_attributes choice list from the cached
// Spoolman field config. Returns [] when the wizard's extraFields
// fetch hasn't completed yet — callers fall back gracefully.
const _knownFilamentAttributes = () => {
    const fields = wizardState.extraFields && wizardState.extraFields.filament;
    if (!fields) return [];
    const fa = fields.find(f => f.key === 'filament_attributes');
    return (fa && fa.choices) || [];
};

// Split a Prusament-style "full" material string ("PC Blend Carbon Fiber")
// into a base material and a list of attributes. Greedy longest-first
// match against the canonical Spoolman filament_attributes choices so
// multi-word attrs like "Carbon Fiber" win over their substrings.
// Word-boundary aware so the match is exact ("PE" won't pull from
// "PETG"). Anything left after attrs are stripped is the base material.
window.splitMaterialAndAttributes = (rawMaterial, knownAttrs) => {
    if (!rawMaterial) return { base: '', attrs: [] };
    const list = Array.isArray(knownAttrs) ? knownAttrs : [];
    if (list.length === 0) return { base: rawMaterial.trim(), attrs: [] };
    const sorted = [...list].sort((a, b) => b.length - a.length);
    let remaining = ` ${rawMaterial} `;
    const matched = [];
    for (const attr of sorted) {
        const escaped = attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(`(^|[^A-Za-z0-9])${escaped}(?=$|[^A-Za-z0-9])`, 'i');
        if (re.test(remaining)) {
            remaining = remaining.replace(re, '$1 ');
            matched.push(attr);
        }
    }
    const base = remaining.trim().replace(/\s+/g, ' ');
    return { base, attrs: matched };
};

// Material match strategy, in order of preference:
//   1. Strip known attributes off the parser side, exact-match the
//      remaining base against stored material. This is the right answer
//      whenever extraFields is loaded — handles "PC Blend Carbon Fiber"
//      vs stored "PC".
//   2. Token-subset fallback when the canonical attribute list isn't
//      available yet (wizard race or older deployment). Word-aware so
//      "PE" still won't match "PETG".
const _materialMatches = (storedMat, parsedMat) => {
    if (!storedMat || !parsedMat) return false;
    if (storedMat === parsedMat) return true;
    const known = _knownFilamentAttributes().map(_normalizeStr);
    if (known.length > 0) {
        const split = window.splitMaterialAndAttributes(parsedMat, known);
        if (_normalizeStr(split.base) === storedMat) return true;
        // And the reverse — stored side may itself be a "full" string on
        // older filaments that pre-date the base/attrs split convention.
        const splitStored = window.splitMaterialAndAttributes(storedMat, known);
        if (_normalizeStr(splitStored.base) === _normalizeStr(split.base)
                && splitStored.base) {
            return true;
        }
    }
    // Token-subset fallback (race / no canonical list available).
    const tokens = (s) => new Set(s.split(/[\s\-_,;()/]+/).filter(Boolean));
    const a = tokens(storedMat);
    const b = tokens(parsedMat);
    if (a.size === 0 || b.size === 0) return false;
    const [smaller, larger] = a.size <= b.size ? [a, b] : [b, a];
    for (const t of smaller) {
        if (!larger.has(t)) return false;
    }
    return true;
};

// Pull the Prusament product ID out of a /spool/<product_id>/<serial> URL.
// Strips any wrapping JSON-encoded quote chars first since /api/filaments
// doesn't run parse_inbound_data — text-type extras arrive as `"https://..."`
// (literal quote chars). Same product, different physical box = same id.
const _extractPrusamentProductId = (url) => {
    if (!url) return null;
    const s = String(url).replace(/^"|"$/g, '');
    const m = s.match(/prusament\.com\/spool\/(\d+)/i);
    return m ? m[1] : null;
};

// Returns the matched filament list (sorted with the best pick at [0]).
// The array carries an extra `.definitive` property:
//   true  — single match OR a Tier-1 product-ID winner; caller should
//           silently auto-switch.
//   false — multiple candidates, ambiguous; caller should surface the
//           duplicate picker so the user decides rather than gambling
//           on lowest-id.
// Returning an array keeps backward compatibility with existing
// `matches.length` / `matches[0]` consumers; the property is read by
// the new picker-aware callers.
window.findFilamentMatches = (temp) => {
    const _wrap = (arr, definitive) => {
        arr.definitive = definitive;
        return arr;
    };
    const all = wizardState.allFilaments || [];
    const vName = _normalizeStr((temp.vendor && temp.vendor.name) || temp.manufacturer);
    const mat = _normalizeStr(temp.material);
    const parsedColor = _normalizeStr(temp.color_name || temp.name);
    if (!vName || !mat || !parsedColor) return _wrap([], true);
    const matches = all.filter(f => {
        const fv = _normalizeStr(f.vendor && f.vendor.name);
        const fm = _normalizeStr(f.material);
        if (fv !== vName) return false;
        if (!_materialMatches(fm, mat)) return false;
        // Fuzzy color match: a Prusament filament might be stored with no
        // dedicated color_name (just a `name` like "Silver (Pearl Mouse)"),
        // while the scan returns color_name "Pearl Mouse". Accept any of:
        //   1. exact equality on the filament's color_name field
        //   2. parsed color appears anywhere in the filament's name
        //   3. filament's color_name appears in the parsed color (only when
        //      color_name is non-empty — the truthy guard prevents the
        //      empty-string substring trap from matching everything)
        const fColorName = _normalizeStr(f.color_name);
        const fName = _normalizeStr(f.name);
        if (fColorName && fColorName === parsedColor) return true;
        if (fName && fName.includes(parsedColor)) return true;
        if (fColorName && parsedColor.includes(fColorName)) return true;
        return false;
    });
    if (matches.length === 0) return _wrap([], true);
    if (matches.length === 1) return _wrap(matches, true);
    // Tier 1: prefer candidates already tagged with the SAME Prusament
    // product ID as the scan. Same /spool/<id>/ in both URLs means
    // "same product, different physical box" — the strongest possible
    // identity signal. Without this, two Prusament PC Black filaments
    // (one tagged from a prior scan, one a stray duplicate) would tie
    // on the basic gate and we'd silently pick the wrong one.
    const parsedProductId = _extractPrusamentProductId(temp.external_link);
    if (parsedProductId) {
        const tier1 = matches.filter(f => {
            const fpid = _extractPrusamentProductId((f.extra || {}).product_url);
            return fpid === parsedProductId;
        });
        if (tier1.length >= 1) {
            tier1.sort((a, b) => Number(a.id) - Number(b.id));
            // Definitive even when multiple tier1 hits — those are literal
            // duplicates of the same canonical product (same product_url),
            // oldest-wins is the right call within that subset.
            return _wrap(tier1, true);
        }
    }
    // Multiple basic-gate matches with no Tier-1 disambiguation = truly
    // ambiguous. Caller should surface the picker so the user decides
    // rather than gambling on lowest-id. We still sort lowest-id-first
    // so [0] is a sensible default if the caller chooses not to prompt.
    matches.sort((a, b) => Number(a.id) - Number(b.id));
    return _wrap(matches, false);
};

window.wizardSyncSpoolRows = () => {
    const qtyInput = document.getElementById('wiz-spool-qty');
    const qty = Math.max(1, parseInt(qtyInput && qtyInput.value) || 1);
    while (wizardState.spoolRows.length < qty) {
        wizardState.spoolRows.push({
            idx: wizardState.spoolRows.length,
            url: '',
            status: 'empty',
            errorMsg: '',
            override: null,
        });
    }
    if (wizardState.spoolRows.length > qty) {
        wizardState.spoolRows = wizardState.spoolRows.slice(0, qty);
    }
    wizardState.spoolRows.forEach((r, i) => { r.idx = i; });
    window.wizardRenderSpoolRows();
    window.wizardUpdateSubmitGate();
};

// Build the badge HTML for a single row — pure function, no DOM access.
// Error badges double as a click-to-clear affordance: the user can tap
// the red badge to reset the row in one click instead of selecting all
// the failed URL text and deleting. Useful when a hardware QR scanner
// caught the wrong barcode or got interrupted mid-stream.
const _spoolRowBadgeHtml = (row) => {
    if (row.status === 'pending') {
        return `<span class="badge bg-secondary">⏳ Scanning…</span>`;
    }
    if (row.status === 'ok') {
        const o = row.override || {};
        const parts = [];
        if (o.initial_weight !== undefined) parts.push(`${o.initial_weight}g`);
        if (o.spool_weight !== undefined) parts.push(`${o.spool_weight}g empty`);
        if (o.extra && o.extra.prusament_manufacturing_date) {
            // Strip the literal-quote wrapper for display.
            parts.push(String(o.extra.prusament_manufacturing_date).replace(/^"|"$/g, ''));
        }
        return `<span class="badge bg-success">✓ ${parts.join(' · ') || 'Scanned'}</span>`;
    }
    // A badge that takes a click clears the row as its ✕ does (Group 66's picture walk,
    // 2026-11-25): wizardClearSpoolRow empties the box, then runs the row's check with no
    // link. The click ran only the check, which left the link's text in the box with no
    // badge, and the next Tab through it checked the same text again (round 1's R4-04, the
    // ✕'s own, on the badge).
    if (row.status === 'error') {
        return `<span class="badge bg-danger" role="button" style="cursor: pointer;"
                       title="Click to clear this row and retry"
                       onclick="window.wizardClearSpoolRow(${row.idx})">✗ ${_wizEscape(row.errorMsg || 'Scan failed')} ✕</span>`;
    }
    // Group 66.3 (B), Edit Spool's link: its words are text (a spool's name can be in them).
    if (row.status === 'linked-new' || row.status === 'linked') {
        return `<span class="badge bg-success">🔗 ${_wizEscape(row.errorMsg || 'Linked')}</span>`;
    }
    if (row.status === 'refused') {
        return `<span class="badge bg-warning text-dark" role="button" style="cursor: pointer;"
                       title="Click to clear this row"
                       onclick="window.wizardClearSpoolRow(${row.idx})">✗ ${_wizEscape(row.errorMsg || 'Not linked')} ✕</span>`;
    }
    return '';
};

// Is there anything in the row to clear (its ✕ shows)?
const _spoolRowClearable = (row) => ['ok', 'error', 'linked', 'linked-new', 'refused'].includes(row.status);

// "Clear this row" button — sits between the URL input and the status
// badge. Only relevant when the row has a value to clear (status is
// 'ok' or 'error'); hidden in 'empty' or 'pending' states.
const _spoolRowClearBtnHtml = (row) => {
    const visible = _spoolRowClearable(row);
    const display = visible ? '' : 'display: none;';
    return `<button type="button" class="btn btn-sm btn-link p-0 px-1 text-secondary wiz-row-clear-btn"
                    style="font-size: 1.1em; line-height: 1; ${display}"
                    title="Clear this row"
                    onclick="window.wizardClearSpoolRow(${row.idx})">✕</button>`;
};

// Review round 1 of Group 66 (R4-04, R3-08): ✕ empties the box as well. Its text stayed, so
// the box's next blur (a Tab through the form) ran the whole scan, or link, again.
window.wizardClearSpoolRow = (idx) => {
    const row = wizardState.spoolRows[idx];
    const input = document.querySelector(`[data-spool-row-idx="${idx}"] input[type='url']`);
    // Review round 3 of Group 66 (R3-05): in Edit Spool, a refusal over a link waiting for Save
    // left that link (round 1's R5-01), and this ✕ dropped it too, unsaid. It clears only the
    // refused QR: the row goes back to the waiting link; a second ✕ clears that.
    if (row && wizardState.mode === 'edit_spool' && row.status === 'refused' && row.linkValue && row.linkedText) {
        row.linkToken = (row.linkToken || 0) + 1;      // nothing of the refused QR's lands now
        row.url = row.linkedText;
        if (input) input.value = row.linkedText;
        row.status = 'linked-new';
        row.errorMsg = 'Links at Save';
        row.linkNote = row.linkedNote || '';
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardRenderLinkNote();
        window.wizardUpdateSubmitGate();
    } else {
        if (input) input.value = '';
        window.wizardScanSpoolRow(idx, '');
    }
    // R3-07: the row's box takes the keyboard ("clear this row and retry"): in a batch of blind
    // scans the next QR went the dashboard's way, and asked "Unsaved Changes", instead of
    // going into the row just cleared.
    const box = document.querySelector(`[data-spool-row-idx="${idx}"] input[type='url']`);
    if (box && typeof box.focus === 'function') box.focus();
};

const _spoolRowSummaryHtml = () => {
    // Group 66.3 (B): in Edit Spool the box links one spool; it has no count to show.
    if (wizardState.mode === 'edit_spool') return '';
    const okCount = wizardState.spoolRows.filter(r => r.status === 'ok').length;
    const total = wizardState.spoolRows.length;
    const errCount = wizardState.spoolRows.filter(r => r.status === 'error').length;
    if (errCount > 0) {
        return `<span class="text-danger fw-bold">⚠ ${errCount} of ${total} spool scans failed — fix or clear before creating.</span>`;
    }
    return `${okCount} of ${total} spools have scan data — others use defaults above.`;
};

// Update only the changed row's badge + outline class. Critically does NOT
// touch the URL input or any neighbor row. Without this, every status
// transition (pending → ok) used to blow away the entire rows container
// via innerHTML, destroying any input the user was actively typing into
// in another row — broke rapid-fire blind scanning of multiple boxes.
window.wizardRenderSpoolRowBadge = (idx) => {
    const row = wizardState.spoolRows[idx];
    if (!row) return;
    const rowEl = document.querySelector(`[data-spool-row-idx="${idx}"]`);
    if (rowEl) {
        // Replace just the trailing badge span (last child) to avoid touching
        // siblings (label, input, clear button). If no badge yet, append one.
        const lastChild = rowEl.lastElementChild;
        if (lastChild && lastChild.classList && lastChild.classList.contains('badge')) {
            lastChild.outerHTML = _spoolRowBadgeHtml(row) || '';
        } else {
            rowEl.insertAdjacentHTML('beforeend', _spoolRowBadgeHtml(row));
        }
        // Toggle the clear-row × button visibility based on whether the row
        // currently has a value worth clearing. Don't replace the element —
        // just flip its display so any focus state stays intact.
        const clearBtn = rowEl.querySelector('.wiz-row-clear-btn');
        if (clearBtn) {
            clearBtn.style.display = _spoolRowClearable(row) ? '' : 'none';
        }
        // Outline class for error state.
        rowEl.classList.toggle('border', row.status === 'error');
        rowEl.classList.toggle('border-danger', row.status === 'error');
        rowEl.classList.toggle('rounded', row.status === 'error');
        rowEl.classList.toggle('p-1', row.status === 'error');
    }
    const summary = document.getElementById('wiz-spool-rows-summary');
    if (summary) summary.innerHTML = _spoolRowSummaryHtml();
};

// Full re-render — only used when the row count changes (qty change or
// reset). Blows away inputs, so do not call this on a status transition.
window.wizardRenderSpoolRows = () => {
    const container = document.getElementById('wiz-spool-rows-container');
    if (!container) return;
    const summary = document.getElementById('wiz-spool-rows-summary');

    container.innerHTML = wizardState.spoolRows.map(row => {
        const rowCls = row.status === 'error' ? 'border border-danger rounded p-1' : '';
        const valAttr = row.url ? `value="${row.url.replace(/"/g, '&quot;')}"` : '';
        return `
        <div class="d-flex align-items-center gap-2 mb-1 ${rowCls}" data-spool-row-idx="${row.idx}">
            <span class="text-secondary small" style="min-width: 64px;">Spool ${row.idx + 1}</span>
            <input type="url" class="form-control form-control-sm bg-dark text-white border-secondary"
                placeholder="📷 Scan/paste Prusament URL — optional"
                ${valAttr}
                onblur="window.wizardScanSpoolRow(${row.idx}, this.value)"
                onkeydown="if (event.key === 'Enter') { event.preventDefault(); this.blur(); }">
            ${_spoolRowClearBtnHtml(row)}
            ${_spoolRowBadgeHtml(row)}
        </div>`;
    }).join('');

    if (summary) summary.innerHTML = _spoolRowSummaryHtml();
};

window.wizardUpdateSubmitGate = () => {
    const submitBtn = document.getElementById('btn-wiz-submit');
    if (!submitBtn) return;
    const blocking = wizardState.spoolRows.some(r => r.status === 'pending' || r.status === 'error');
    if (blocking) {
        submitBtn.disabled = true;
    } else {
        // Defer to wizardValidateSubmit's own logic (existing-mode + selection check).
        wizardValidateSubmit();
    }
};

window.wizardScanSpoolRow = async (idx, rawUrl) => {
    // Group 66.3 (Derek's (B)): in Edit Spool the box links the spool to its QR.
    if (wizardState.mode === 'edit_spool') return window.wizardLinkPrusament(idx, rawUrl);
    const row = wizardState.spoolRows[idx];
    if (!row) return;
    const url = (rawUrl || '').trim();
    row.url = url;

    if (!url) {
        row.status = 'empty';
        row.errorMsg = '';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        return;
    }

    if (!url.includes('prusament.com/spool/')) {
        row.status = 'error';
        row.errorMsg = 'Not a Prusament URL';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        return;
    }

    // Review round 1 of Group 66 (R3-11): a QR another Spool box holds already (a scanner's
    // second read lands in the next box, which the eager focus advance below gives the
    // keyboard). Save made two records of one spool. This box goes back to empty, and says
    // where the QR is.
    const qrKey = _wizQrKey(url);
    const twin = wizardState.spoolRows.find((r) => r !== row && r.status !== 'empty' && r.url && _wizQrKey(r.url) === qrKey);
    if (twin) {
        const input = document.querySelector(`[data-spool-row-idx="${idx}"] input[type='url']`);
        if (input) input.value = '';
        row.url = '';
        row.status = 'empty';
        row.errorMsg = '';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        if (window.showToast) window.showToast(`That spool's QR is in Spool ${twin.idx + 1} already.`, 'info', 4000);
        return;
    }

    // EAGER FOCUS ADVANCE — before the slow fetch begins, hop focus to
    // the next still-empty row. Hardware QR scanners send Enter at the
    // end of the scan, which blurs row N; the very next keystroke from
    // the scanner for row N+1 arrives within milliseconds. If we wait
    // until the fetch resolves to advance focus, those early keystrokes
    // land on document.body or wherever and get lost — the user sees
    // a partial URL on row N+1, or worse, the global scan handler picks
    // up the URL prefix and 400s with "Unknown/Invalid Link". Move
    // focus NOW so the scanner's row N+1 stream has a target.
    const eagerNext = wizardState.spoolRows.find(r => r.idx > idx && r.status === 'empty');
    if (eagerNext) {
        const eagerInput = document.querySelector(
            `[data-spool-row-idx="${eagerNext.idx}"] input[type='url']`
        );
        if (eagerInput) eagerInput.focus();
    }

    row.status = 'pending';
    row.errorMsg = '';
    window.wizardRenderSpoolRowBadge(idx);
    window.wizardUpdateSubmitGate();

    // Review round 3 of Group 66: the answer waits while a label arrives in a wizard box,
    // and fills nothing once its row moved on (another QR scanned into it, the row cleared
    // or gone, or the wizard opened again): it overwrote the row's newer scan.
    const session = wizardState.session;
    const movedOn = () => wizardState.session !== session || !wizardState.spoolRows.includes(row) || row.url !== url;
    try {
        const r = await fetch(`/api/external/search?source=prusament&q=${encodeURIComponent(url)}`);
        const data = await r.json();
        await window.wizardAfterLabel();
        if (movedOn()) return;
        if (!data.success || !data.results || data.results.length === 0) {
            row.status = 'error';
            row.errorMsg = 'Prusament URL not recognized';
            row.override = null;
            window.wizardRenderSpoolRowBadge(idx);
            window.wizardUpdateSubmitGate();
            return;
        }

        const temp = data.results[0];
        row.override = window.extractSpoolFieldsFromTemplate(temp);
        row.status = 'ok';
        row.errorMsg = '';

        // First successful scan in the session: maybe fill Step 2. If any
        // existing filament fuzzy-matches AND the matcher is confident
        // (single match OR Tier-1 product-ID winner), silently auto-switch.
        // If multiple basic-gate matches are ambiguous, surface the picker
        // so the user picks (or chooses "Create new"). Gate accepts both
        // 'manual' and 'external' (Import from External Database) since
        // both paths can result in a fresh filament create.
        const canMatch = (wizardState.mode === 'manual' || wizardState.mode === 'external');
        if (!wizardState.filamentLockedFromScan && canMatch) {
            const matches = window.findFilamentMatches(temp);
            if (matches.length === 0) {
                window.applyFilamentFieldsFromTemplate(temp);
            } else if (matches.definitive) {
                window.wizardAutoSwitchToExisting(matches[0], temp);
            } else {
                window.wizardRenderDuplicatePicker(matches, temp);
            }
            wizardState.filamentLockedFromScan = true;
        }

        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        // Note: focus-next is no longer fired here — done eagerly before
        // the fetch above so the QR scanner's next-box stream has a
        // landing target as soon as possible. Firing it again here
        // would steal focus from a user who's already typing into row N+2.
    } catch (e) {
        console.error('wizardScanSpoolRow error', e);
        await window.wizardAfterLabel();
        if (movedOn()) return;
        row.status = 'error';
        row.errorMsg = 'Network error';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
    }
};

// --- EDIT SPOOL LINKS THE SPOOL TO ITS PRUSAMENT QR (Group 66.3, Derek's (B)) ---
// The "📷 Per-spool Prusament scan" box showed a ✓ in Edit Spool and Save sent none of
// it (only a create reads spool_overrides). Now a QR scanned (or pasted) there links the
// spool being edited: its 📄 Product Link gets the QR's own link, and its BLANK
// Prusament details (purchase link, manufacturing date, length) are filled, all as if
// typed, so Save sends them through the edit's own diff (no new write). Prusament's
// weights are shown, never sent: the dashboard scan of the QR offers them, checked
// against the live spool first (/api/spool/prusament_apply_weights).
// It changes nothing, and says why on the row and its note line, when:
//   - the link isn't a Prusament spool's, or names no one spool (no spool code);
//   - the spool's own Product Link holds another link (clear it first);
//   - another spool already holds this QR (/api/prusament/linked_spools, the dashboard
//     scan's own rule, archived spools included), or FCC couldn't check;
//   - FCC couldn't read the QR's Prusament page;
//   - the QR names a different product than the spool's filament (vendor or material,
//     or a colour neither name contains).
// A refusal never blocks Save (its own status, 'refused'); a check in flight does
// ('pending'), briefly. A new scan, or the row's ✕, first puts back what an earlier link
// filled in (each box only while it still shows the value put there). An answer that
// lands after the wizard moved on (reset, another spool, another mode) changes nothing.
const WIZ_ROWS_LABEL_ADD = '📷 Per-spool Prusament scan (optional)';
const WIZ_ROWS_LABEL_EDIT = "📷 Link this spool to its Prusament QR (optional)";
const _wizPrusamentLink = (url) => /prusament\.com\/spool\/(\d+)(?:\/([0-9a-z]+))?/i.exec(String(url || ''));
const _wizLinkHolds = (link, pid, hash) => {
    const s = String(link || '').replace(/^"+|"+$/g, '').trim().toLowerCase();
    if (!s) return false;
    return s.includes(`/spool/${pid}/${hash}`) || s.includes(`spoolid=${hash}`);
};

// The row's note line (its words, as text).
window.wizardRenderLinkNote = () => {
    const el = document.getElementById('wiz-spool-link-note');
    if (!el) return;
    const row = wizardState.mode === 'edit_spool' ? (wizardState.spoolRows || [])[0] : null;
    const words = row && row.linkNote ? row.linkNote : '';
    el.textContent = words;
    el.style.display = words ? '' : 'none';
};

// Put back what an earlier link of this row filled in (each box only while it still
// shows the value put there: a box the person changed since stays theirs).
const _wizUndoLink = (row) => {
    for (const f of (row.linkFills || [])) {
        const el = document.getElementById(f.id);
        if (el && el.value === f.value) el.value = f.before;
    }
    row.linkFills = [];
    row.linkValue = '';
    row.linkedText = '';
    row.linkedNote = '';
};

// Does the QR's product disagree with the spool's filament? Words when it clearly does.
const _wizLinkMismatch = (temp, sid) => {
    const orig = wizardState.editFilamentOriginal || {};
    const vendorName = (() => {
        const v = (wizardState.vendors || []).find((x) => String(x.id) === String(orig.vendor_id));
        return v ? v.name : '';
    })();
    const qrVendor = (temp.vendor && temp.vendor.name) || 'Prusament';
    const qrWhat = `${qrVendor} ${temp.material || ''} ${temp.color_name || temp.name || ''}`.replace(/\s+/g, ' ').trim();
    const ourWhat = `${vendorName} ${orig.material || ''} ${orig.name || ''}`.replace(/\s+/g, ' ').trim();
    const say = `That QR is ${qrWhat}, and #${sid} is ${ourWhat}: scan #${sid}'s own QR.`;
    if (vendorName && _normalizeStr(vendorName) !== _normalizeStr(qrVendor)) return say;
    if (orig.material && temp.material && !_materialMatches(_normalizeStr(orig.material), _normalizeStr(temp.material))) return say;
    // Colours by their words (review round 1 of Group 66, R4-06): Derek's Prusament filaments
    // are named "Black (Galaxy Black)", and Prusament's page can say "Prusa Galaxy Black" or
    // "Goldfish Orange"; neither text held the other, and the spool's own QR was refused.
    // Every word of one is in the other (Prusa and Prusament left out), else a mismatch.
    const words = (s) => String(s || '').toLowerCase().split(/[^a-z0-9]+/)
        .filter((w) => w && w !== 'prusa' && w !== 'prusament');
    const qrWords = words(temp.color_name);
    const ourWords = words(orig.name);
    const within = (a, b) => a.every((w) => b.includes(w));
    if (qrWords.length && ourWords.length && !within(qrWords, ourWords) && !within(ourWords, qrWords)) return say;
    return '';
};

// Review round 1 of Group 66 (R4-02): once an Edit Spool Save lands, its link is the
// spool's: the row says so, and its ✕ (or another scan) no longer puts back what the
// boxes held before the link (that cleared the saved link at the next Save).
// `sent`: the link boxes as the Save that landed sent them (Group 66.9 review round 3,
// R3W8): a row whose link that Save didn't carry (checked while it was out) waits for the
// next Save, still "Links at Save". Called with none, it settles as before.
window.wizardSettleLinkRow = (sent) => {
    if (wizardState.mode !== 'edit_spool') return;
    const row = (wizardState.spoolRows || [])[0];
    if (!row || row.status !== 'linked-new') return;
    if (sent && String(sent.product_url || '').trim() !== String(row.linkValue || '')) return;
    row.linkFills = [];
    row.linkValue = '';
    row.linkedText = '';
    row.linkedNote = '';
    row.status = 'linked';
    row.errorMsg = 'Linked to this QR';
    row.linkNote = '';
    window.wizardRenderSpoolRowBadge(0);
    window.wizardRenderLinkNote();
    window.wizardUpdateSubmitGate();
};

window.wizardLinkPrusament = async (idx, rawUrl) => {
    const row = wizardState.spoolRows[idx];
    if (!row) return;
    const url = String(rawUrl || '').trim();
    // Review round 1 of Group 66: the row's text unchanged since its link (or its check on
    // its way) is checked again for nothing (R5-01: a Tab through the row re-ran it, and a
    // refusal then emptied the boxes the link filled; R4-03: two checks of one link raced).
    if (url && row.url === url && ['linked', 'linked-new', 'pending'].includes(row.status)) return;
    // Each check has its own token: only the newest may fill or record (R4-03).
    const token = row.linkToken = (row.linkToken || 0) + 1;
    // An earlier link's fills are put back only once this one is decided (R5-01): a ✕ (no
    // text) now; a new link right before its own fills; a refusal leaves them as they were.
    if (!url) _wizUndoLink(row);
    row.url = url;
    row.override = null;           // an edit never sends a spool override
    const done = (status, msg, note) => {
        row.status = status;
        row.errorMsg = msg || '';
        // Review round 3 of Group 66 (R3-05): a refusal over a link waiting for Save leaves that
        // link, and says so; its ✕ goes back to it (wizardClearSpoolRow).
        const waiting = status === 'refused' && row.linkValue && row.linkedText;
        row.linkNote = waiting
            ? `${note ? `${note} ` : ''}The QR scanned before this one still links at Save: ✕ goes back to it.`
            : (note || '');
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardRenderLinkNote();
        window.wizardUpdateSubmitGate();
    };
    if (!url) return done('empty');
    const m = _wizPrusamentLink(url);
    if (!m) return done('refused', "Not a Prusament spool's link", '');
    if (!m[2]) {
        return done('refused', 'No spool code in it',
            "A Prusament spool's QR ends in its own spool code; this link has none, so it could be any spool of the product.");
    }
    const pid = m[1];
    const hash = m[2].toLowerCase();
    const canonical = `https://prusament.com/spool/${pid}/${hash}/`;
    const sid = wizardState.editSpoolId;
    const session = wizardState.session;
    const stale = () => wizardState.session !== session || String(wizardState.editSpoolId) !== String(sid)
        || wizardState.mode !== 'edit_spool' || row.url !== url || row.linkToken !== token;

    // The spool's own Product Link (not this row's own unsaved fill, which a new link
    // replaces).
    const productBox = document.getElementById('wiz-spool-product_url');
    const shown = productBox ? productBox.value.trim() : '';
    const own = row.linkValue && shown === row.linkValue ? '' : shown;
    if (own && _wizLinkHolds(own, pid, hash)) return done('linked', 'Already linked to this QR', '');
    if (own) {
        return done('refused', 'Its Product Link holds another link',
            `#${sid}'s 📄 Product Link holds another link. Clear it first if this QR is #${sid}'s.`);
    }

    done('pending');
    // Another spool holding this QR?
    let owners = null;
    try {
        const r = await fetch(`/api/prusament/linked_spools?url=${encodeURIComponent(canonical)}`);
        const d = await r.json();
        if (stale()) return;
        if (d && d.success && Array.isArray(d.spools)) owners = d.spools.filter((s) => String(s.id) !== String(sid));
    } catch (_) { if (stale()) return; }
    await window.wizardAfterLabel();
    if (stale()) return;
    if (owners === null) {
        return done('refused', "Couldn't check this QR",
            "FCC couldn't check whether another spool has this QR, so nothing changed. Try again in a moment.");
    }
    if (owners.length) {
        const o = owners[0];
        return done('refused', `Linked to #${o.id}`,
            `That QR is already linked to ${o.display || '#' + o.id}${o.archived ? ' (archived)' : ''}. If it is #${sid}'s, clear #${o.id}'s 📄 Product Link first (Edit Spool #${o.id}), then scan it here again.`);
    }

    // What Prusament says the spool is.
    let temp = null;
    try {
        // The canonical link (review round 1, R4-05): Prusament's lookup reads a lower-case
        // link only, and an upper-cased QR (Caps Lock, a scanner set so) was "couldn't read".
        const r = await fetch(`/api/external/search?source=prusament&q=${encodeURIComponent(canonical)}`);
        const d = await r.json();
        if (stale()) return;
        temp = d && d.success && Array.isArray(d.results) ? d.results[0] || null : null;
    } catch (_) { if (stale()) return; }
    await window.wizardAfterLabel();
    if (stale()) return;
    if (!temp) {
        return done('refused', "Couldn't read its Prusament page",
            "FCC couldn't read this spool's Prusament page, so nothing changed. Try again in a moment.");
    }
    const mismatch = _wizLinkMismatch(temp, sid);
    if (mismatch) return done('refused', 'A different product', mismatch);
    // Read again (review round 1, R4-07): a link typed into it while the checks were out is
    // the person's, and the QR links nothing then (it filled the other boxes, and said
    // "Links at Save").
    const nowShown = productBox ? productBox.value.trim() : '';
    const nowOwn = row.linkValue && nowShown === row.linkValue ? '' : nowShown;
    if (nowOwn && _wizLinkHolds(nowOwn, pid, hash)) return done('linked', 'Already linked to this QR', '');
    if (nowOwn) {
        return done('refused', 'Its Product Link holds another link',
            `#${sid}'s 📄 Product Link holds another link. Clear it first if this QR is #${sid}'s.`);
    }

    // Link: the QR's own link, and the spool's blank Prusament details, as if typed. An
    // earlier link of this row goes first (its boxes back as they were).
    _wizUndoLink(row);
    const o = window.extractSpoolFieldsFromTemplate(temp) || {};
    const ex = o.extra || {};
    const unq = (v) => String(v == null ? '' : v).replace(/^"|"$/g, '');
    const fills = [];
    const fill = (id, value) => {
        const el = document.getElementById(id);
        if (!el || value == null || String(value).trim() === '' || el.value.trim() !== '') return;
        fills.push({ id, before: el.value, value: String(value) });
        el.value = String(value);
    };
    fill('wiz-spool-product_url', canonical);
    if (temp.purchase_link) fill('wiz-spool-purchase_url', temp.purchase_link);
    if (ex.prusament_manufacturing_date) fill('wiz_spool_ef_prusament_manufacturing_date', unq(ex.prusament_manufacturing_date));
    const len = unq(ex.prusament_length_m);
    if (len && len !== '0') fill('wiz_spool_ef_prusament_length_m', len);
    row.linkFills = fills;
    row.linkValue = canonical;
    wizardState.isDirty = true;
    const bits = [];
    if (o.initial_weight !== undefined) bits.push(`${o.initial_weight} g of filament`);
    if (o.spool_weight !== undefined) bits.push(`${o.spool_weight} g empty`);
    const weights = bits.length ? `Prusament says ${bits.join(', ')}. ` : '';
    const linkNote = `${weights}To use its weights, Save and close the wizard, then scan this QR on the dashboard: FCC checks them against the spool first.`;
    row.linkedText = url;          // what a refusal's ✕ goes back to (R3-05)
    row.linkedNote = linkNote;
    return done('linked-new', 'Links at Save', linkNote);
};

// --- A NEW PRUSAMENT SPOOL'S QR WHILE THE WIZARD IS OPEN (Group 66.2) ---
// The dashboard's prusament_new answer used to call openWizardModal unasked, which reset an
// open wizard (an Edit silently became an Add). In an Add (New Manual Form, Existing
// Filament, Import Database) whose Spool boxes have an empty one, the QR goes into that box
// instead, as if scanned there, with no question. Never while an opener's prefill is still
// loading, a Save is on its way, or the form never loaded; never in Edit Spool, whose box
// links its own spool only through the box itself (the grounding's C4: a QR read from
// outside it may be another spool's). Answers {row} when it took the link, else false.
// Review round 1 of Group 66 (R3-01, R5-02, R3-02, R3-11): the feed took a QR into any Add's
// empty Spool box. With a filament already picked (Existing Filament, the batch flow after a
// create) the spool was created as THAT filament carrying another product's link, weights
// and date, so every later scan of its QR matched the wrong spool; with one typed in New
// Manual Form the QR's product page wrote over it, unasked. And a scanner's second read of
// one QR filled a second box (two records of one spool), or asked to start over. Now:
//   - a QR a Spool box (or Edit Spool's link box) holds already, by its spool id and hash,
//     is a second read: answered `{already: idx}` and said, nothing more;
//   - the QR goes into a box only in New Manual Form with nothing typed or picked for the
//     filament (the QR names it, as in a fresh Add); otherwise the open asks first when the
//     wizard holds changes, and starts a fresh Add for the QR when it doesn't.
const _wizQrKey = (url) => {
    const m = _wizPrusamentLink(url);
    return m ? `${m[1]}/${String(m[2] || '').toLowerCase()}` : String(url || '').trim().toLowerCase();
};
const _wizStep2Untouched = () => wizardState.mode === 'manual'
    && (wizardState.selectedFilamentId == null || String(wizardState.selectedFilamentId) === '')
    && !wizardState.filamentLockedFromScan
    && ['wiz-fil-color_name', 'wiz-fil-material', 'wiz-fil-vendor-search', 'wiz-fil-vendor-sel']
        .every((id) => _wizBoxValue(id).trim() === '');
window.wizardTakePrusamentLink = (url) => {
    const link = String(url || '').trim();
    const wizEl = document.getElementById('wizardModal');
    if (!link || !wizEl || !wizEl.classList.contains('show')) return false;
    const key = _wizQrKey(link);
    for (const row of (wizardState.spoolRows || [])) {
        const input = document.querySelector(`[data-spool-row-idx="${row.idx}"] input[type='url']`);
        const held = ((input && input.value) || row.url || '').trim();
        if (held && row.status !== 'empty' && _wizQrKey(held) === key) return { already: row.idx };
    }
    if (!['manual', 'existing', 'external'].includes(wizardState.mode)) return false;
    if (wizardState.prefilling || wizardState.saving != null || wizardState.editLoadFailed) return false;
    if (!_wizStep2Untouched()) return false;
    const box = document.getElementById('wiz-spool-rows-box');
    if (box && box.getClientRects().length === 0) return false;
    for (const row of (wizardState.spoolRows || [])) {
        const input = document.querySelector(`[data-spool-row-idx="${row.idx}"] input[type='url']`);
        if (row.status !== 'empty' || !input || input.value.trim() !== '') continue;
        input.value = link;
        // As a scanner typing there would: the form is changed (and a create's lock lifts).
        input.dispatchEvent(new Event('input', { bubbles: true }));
        window.wizardScanSpoolRow(row.idx, link);
        return { row: row.idx };
    }
    return false;
};

// Review round 1 of Group 66 (R3-07): the wizard on screen with a Save on its way.
window.wizardIsSaving = () => {
    const w = document.getElementById('wizardModal');
    return !!(w && w.classList.contains('show')) && wizardState.saving != null;
};

// Review round 1 of Group 66 (R3-04, R4-10, R5-03): a new Prusament spool's QR read while Edit
// Spool is open, from outside its link box (the open gives the keyboard to the window's ✕,
// so the first scan after opening goes the dashboard's way, and a link box's Enter leaves the
// keyboard on the page). An unchanged edit started over as an Add, unasked, and one press of
// CREATE INVENTORY made a second record of the spool being edited, holding its QR. Now it
// asks what the QR is: the edited spool's (it goes into the link box, whose own checks run:
// another spool holding it, a different product), a new spool's (an Add starts: the edit
// closes, and its changes are lost, as the words say), or neither (Keep Editing, the safe
// answer, where the keyboard starts). Scans are held while it is up, and a bare CMD:CANCEL
// keeps editing. Answers 'link', 'add' or 'keep'.
window.wizardAskQrInEdit = (url) => new Promise((resolve) => {
    const wizEl = document.getElementById('wizardModal');
    const sid = wizardState.editSpoolId;
    const changed = !!wizardState.isDirty;
    let handle = null;
    let release = null;
    let settled = false;
    const onClosed = (e) => {
        if (handle && e && e.detail && e.detail.element === handle.element) { handle = null; settle('keep'); }
    };
    const settle = (answer) => {
        if (settled) return;
        settled = true;
        document.removeEventListener('fcc:overlay-closed', onClosed);
        if (release) { release(); release = null; }
        if (handle) { const h = handle; handle = null; h.cleanup(); }
        if (answer === 'link') {
            const input = document.querySelector("[data-spool-row-idx='0'] input[type='url']");
            if (input) {
                input.value = url;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                window.wizardScanSpoolRow(0, url);
            }
        } else if (answer === 'add') {
            wizardState.isDirty = false;     // the person chose to drop the edit
        }
        resolve(answer);
    };
    const esc = window.escHtml || _wizEscape;
    const lost = changed ? ' Its unsaved changes are lost.' : '';
    handle = window.mountOverlay({
        id: 'fcc-wiz-qr-in-edit',
        host: wizEl,
        initialFocus: '#fcc-wiz-qr-keep',
        onEscape: () => settle('keep'),
        content: `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px; padding:20px 24px; max-width:34rem; width:92%;">
                <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">📷 A Prusament QR was scanned</div>
                <div style="color:#ffc; margin-bottom:16px;">Spool #${esc(sid)} is open in Edit Spool. Is this QR #${esc(sid)}'s own? Linking it runs the link box's checks. An Add for a new spool closes this edit.${esc(lost)}</div>
                <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                    <button id="fcc-wiz-qr-keep" class="btn btn-secondary btn-sm">Keep Editing</button>
                    <button id="fcc-wiz-qr-add" class="btn btn-warning btn-sm">Start an Add for a new spool</button>
                    <button id="fcc-wiz-qr-link" class="btn btn-info btn-sm">Link it to #${esc(sid)}</button>
                </div>
                <div id="fcc-wiz-qr-flash" role="alert" style="color:#ffc107; font-size:var(--fcc-fs-small); margin-top:10px;"></div>
            </div>`,
    });
    document.addEventListener('fcc:overlay-closed', onClosed);
    const ov = handle.element;
    const shield = () => { if (window.fccShieldNextPress) window.fccShieldNextPress(); };
    const arm = window.armedClick || ((fn) => fn);
    const armMs = window.questionArmMs ? window.questionArmMs() : 0;
    ov.querySelector('#fcc-wiz-qr-keep').addEventListener('click', () => { shield(); settle('keep'); });
    ov.querySelector('#fcc-wiz-qr-add').addEventListener('click', arm(() => { shield(); settle('add'); }, armMs));
    ov.querySelector('#fcc-wiz-qr-link').addEventListener('click', arm(() => { shield(); settle('link'); }, armMs));
    const flash = (msg) => { const f = ov.querySelector('#fcc-wiz-qr-flash'); if (f) f.textContent = msg; };
    if (window.fccHoldScans) {
        release = window.fccHoldScans({
            title: 'A Prusament QR was scanned',
            element: ov,
            hint: `Answer the question on screen first: Keep Editing, Link it to #${sid}, or Start an Add`,
            cancel: () => settle('keep'),
            flash,
        });
    }
});

// Group 66.2 (the grounding's C5): the spool open in Edit Spool, if any. The dashboard's
// matched-spool question holds its weight correction for it: applied while the wizard is
// open, the wizard's next Save would write its old weights back over it unseen.
window.wizardEditingSpool = () => {
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl || !wizEl.classList.contains('show') || wizardState.mode !== 'edit_spool') return null;
    return wizardState.editSpoolId != null ? String(wizardState.editSpoolId) : null;
};

window.wizardAutoSwitchToExisting = (filament, parsedTemplate) => {
    window.wizardSelectType('existing', true);
    const sel = document.getElementById('wiz-existing-results');
    if (sel) {
        const name = `${filament.vendor?.name || 'Generic'} ${filament.material} - ${filament.name || 'Unknown'}`;
        sel.innerHTML = `<option value="${filament.id}" selected>${name} (ID: ${filament.id})</option>`;
        window.wizardExistingSelected(filament);
    }
    const msg = document.getElementById('wiz-status-msg');
    if (msg) {
        msg.innerHTML = `<span class="text-success">✅ Recognized existing Prusament Filament #${filament.id} — switched to new-spool mode.</span>`;
    }
    // Opportunistic backfill: silently fill any field the existing record
    // is missing, surface mismatches as an opt-in panel. Skipped when the
    // caller didn't pass the parser template (e.g. clone flow).
    if (parsedTemplate && window.computeFilamentBackfillDiff) {
        const known = _knownFilamentAttributes();
        const diff = window.computeFilamentBackfillDiff(filament, parsedTemplate, known);
        if (diff.silent && Object.keys(diff.silent).length > 0) {
            window.applyFilamentBackfillSilent(filament.id, diff.silent);
        }
        if (diff.mismatches && diff.mismatches.length > 0) {
            window.wizardRenderFilamentMismatchPanel(filament.id, diff.mismatches);
        } else {
            window.wizardClearFilamentMismatchPanel();
        }
    }
};

// Treat null / undefined / '' / 0 (numeric only) all as "unset" so the
// backfill detector can fairly say "this slot is empty, fill it." Matches
// the inv_details.js Edit Filament dirty-diff `same()` helper convention.
const _isUnset = (v) => v === null || v === undefined || v === '' || v === 0 || v === '0';

// Group 66.6: the server's one reading (window.fccFilamentAttrs). An old "Silk, Matte"
// read as no tags here, so a Prusament backfill wrote only the scanned tags over it.
const _normalizeFilamentAttrs = (raw) => window.fccFilamentAttrs(raw);

// Pure function — given an existing filament record and a fresh parser
// template, decide what to silently backfill vs surface as a mismatch
// for opt-in. See plan: "Backfill Existing Filament From Prusament Scan
// Data" for the field-by-field rule table this implements.
window.computeFilamentBackfillDiff = (existing, parsedTemplate, knownAttrs) => {
    const out = { silent: {}, mismatches: [] };
    if (!existing || !parsedTemplate) return out;
    const ex = existing;
    const tp = parsedTemplate;

    // Native scalar fields with simple "fill if unset, mismatch if differs"
    // semantics. Each entry: [key, parsed value, mismatch threshold (number),
    // human label, kind hint for renderer].
    const tempExtra = (tp.extra || {});
    const exExtra = (ex.extra || {});

    const split = (window.splitMaterialAndAttributes || ((m) => ({ base: m, attrs: [] })))(
        tp.material || '', knownAttrs || []
    );
    const parsedBase = split.base || tp.material || '';

    const pushMismatch = (key, label, stored, scanned, kind) => {
        out.mismatches.push({ key, label, stored, scanned, kind });
    };

    // material: never silent. Mismatch only when parsed-base differs from
    // the user's stored value (the common case — user keeps "PC", parser
    // returned "PC Blend Carbon Fiber" → base "PC" → no mismatch).
    if (parsedBase && ex.material && parsedBase !== ex.material) {
        pushMismatch('material', 'Material', ex.material, parsedBase, 'text');
    } else if (parsedBase && _isUnset(ex.material)) {
        out.silent.material = parsedBase;
    }

    // diameter / density / weight / spool_weight — fill when unset,
    // mismatch when meaningfully different.
    const numericFields = [
        ['diameter', 'Diameter (mm)', 0.05],
        ['density', 'Density (g/cm³)', 0.05],
        ['weight', 'Weight (g)', 10],
        ['spool_weight', 'Spool weight (g)', 5],
    ];
    for (const [key, label, threshold] of numericFields) {
        const stored = ex[key];
        const scanned = tp[key];
        if (_isUnset(scanned)) continue;
        // 24.K — never import a parser's DEFAULTED 1000g net weight into an
        // existing filament. When the scrape only assumed the weight
        // (weight_is_default), skip the 'weight' field so it neither
        // silent-fills nor overwrites a real stored weight — parity with the
        // wizard create-path guard in extractSpoolFieldsFromTemplate /
        // applyFilamentFieldsFromTemplate. (spool_weight is a real tare reading,
        // unaffected by weight_is_default.)
        if (key === 'weight' && tp.weight_is_default) continue;
        if (_isUnset(stored)) {
            out.silent[key] = scanned;
        } else if (Math.abs(Number(stored) - Number(scanned)) > threshold) {
            const kind = (key === 'spool_weight') ? 'spool_weight' : 'number';
            pushMismatch(key, label, Number(stored), Number(scanned), kind);
        }
    }

    // settings_extruder_temp / settings_bed_temp — fill if unset, mismatch
    // if differs (no threshold; temps are integers in Spoolman).
    const tempFields = [
        ['settings_extruder_temp', 'Extruder Temp Min (°C)'],
        ['settings_bed_temp', 'Bed Temp Min (°C)'],
    ];
    for (const [key, label] of tempFields) {
        const stored = ex[key];
        const scanned = tp[key];
        if (_isUnset(scanned)) continue;
        if (_isUnset(stored)) {
            out.silent[key] = scanned;
        } else if (Number(stored) !== Number(scanned)) {
            pushMismatch(key, label, Number(stored), Number(scanned), 'number');
        }
    }

    // color_hex — never silent. Mismatch only with a 'color' kind hint so
    // the renderer can show swatches.
    if (tp.color_hex && ex.color_hex
            && String(tp.color_hex).replace('#', '').toLowerCase() !== String(ex.color_hex).replace('#', '').toLowerCase()) {
        pushMismatch('color_hex', 'Color hex',
            String(ex.color_hex).replace('#', ''),
            String(tp.color_hex).replace('#', ''),
            'color');
    } else if (tp.color_hex && _isUnset(ex.color_hex)) {
        out.silent.color_hex = String(tp.color_hex).replace('#', '');
    }

    // Extras (text-type max-temps): JSON-quote-wrap before sending so the
    // backend's sanitize_outbound_data doesn't reject "225" as an int.
    const extraTextFields = [
        ['nozzle_temp_max', 'Nozzle Temp Max (°C)'],
        ['bed_temp_max', 'Bed Temp Max (°C)'],
    ];
    for (const [key, label] of extraTextFields) {
        const stored = exExtra[key];
        const scanned = tempExtra[key];
        if (_isUnset(scanned)) continue;
        // The parser sometimes returns these wrapped (`'"225"'`) and
        // sometimes raw ('225'). Normalize for comparison.
        const unwrap = (v) => {
            if (v === null || v === undefined) return v;
            const s = String(v);
            return s.replace(/^"|"$/g, '');
        };
        const storedNorm = unwrap(stored);
        const scannedNorm = unwrap(scanned);
        if (_isUnset(storedNorm)) {
            out.silent['extra.' + key] = `"${scannedNorm}"`;
        } else if (storedNorm !== scannedNorm) {
            pushMismatch('extra.' + key, label, storedNorm, scannedNorm, 'number');
        }
    }

    // filament_attributes — set-union, only ever ADD missing canonical
    // attrs (never remove existing). Drives the user's PC → PC + "Blend"
    // upgrade silently after a scan that splits to ["Blend", "Carbon Fiber"].
    const exAttrs = _normalizeFilamentAttrs(exExtra.filament_attributes);
    const exAttrsLc = new Set(exAttrs.map(s => s.toLowerCase()));
    const newAttrs = (split.attrs || []).filter(a => !exAttrsLc.has(a.toLowerCase()));
    if (newAttrs.length > 0) {
        out.silent['extra.filament_attributes'] = [...exAttrs, ...newAttrs];
    }

    // product_url + purchase_url — silent fill when the existing record
    // has no value. Tagging the filament with the canonical Prusament
    // product link makes the matcher's Tier-1 product-ID rule work on
    // future scans (otherwise the matcher would only have name + material
    // + color to disambiguate, which is fuzzy when the user has
    // accidental duplicates). Sent RAW — both keys are in
    // spoolman_api.JSON_STRING_FIELDS so sanitize_outbound_data wraps
    // them via json.dumps. Pre-wrapping would double-wrap.
    const _isSetUrl = (v) => v !== null && v !== undefined && String(v).replace(/^"|"$/g, '') !== '';
    if (tp.external_link && !_isSetUrl(exExtra.product_url)) {
        out.silent['extra.product_url'] = tp.external_link;
    }
    if ((tp.purchase_link || tp.external_link) && !_isSetUrl(exExtra.purchase_url)) {
        out.silent['extra.purchase_url'] = tp.purchase_link || tp.external_link;
    }

    // original_color — silent overwrite when the parser has a value.
    // This field's whole purpose is to capture the manufacturer's name
    // for the filament (e.g. "Pearl Mouse"), distinct from the user's
    // filter-friendly color_name ("Black"). The parser's color_name is
    // the authoritative source by definition, so prefer it whenever
    // present. Only skip the silent update when the values already match
    // (avoid a no-op PATCH).
    //
    // CRITICAL: original_color is in spoolman_api.JSON_STRING_FIELDS, so
    // sanitize_outbound_data wraps the value via json.dumps before send.
    // Pre-wrapping here would double-wrap and the literal quote chars
    // would leak in — every subsequent scan would compare "X" ≠ X and
    // add ANOTHER layer of quotes. Acceptable canonical forms for the
    // RAW value (as served by /api/filaments without parse_inbound_data,
    // OR by /api/filaments/<id> WITH parse_inbound_data) are exactly two:
    // the JSON-quoted form `"X"` and the raw unwrapped `X`. Anything
    // else means an earlier buggy version corrupted the field — fire
    // an update with the clean value to repair it (sanitize wraps once
    // and we're back to canonical).
    const exOrigColor = exExtra.original_color;
    const scannedOrigColor = tp.color_name;
    if (scannedOrigColor) {
        const acceptable = [scannedOrigColor, `"${scannedOrigColor}"`];
        if (!acceptable.includes(exOrigColor)) {
            out.silent['extra.original_color'] = scannedOrigColor;
        }
    }

    return out;
};

// Apply a silent backfill diff against an existing filament. Splits any
// "extra.<key>" entries in the diff into a nested {extra: {...}} dict
// since /api/update_filament expects the same shape Spoolman uses.
window.applyFilamentBackfillSilent = async (existingId, silentDiff, opts = {}) => {
    if (!silentDiff || Object.keys(silentDiff).length === 0) return null;
    const data = {};
    for (const [k, v] of Object.entries(silentDiff)) {
        if (k.startsWith('extra.')) {
            if (!data.extra) data.extra = {};
            data.extra[k.slice(6)] = v;
        } else {
            data[k] = v;
        }
    }
    try {
        const res = await fetch('/api/update_filament', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: existingId, data }),
        });
        const body = await res.json();
        if (!body.success) {
            console.error('backfill update rejected', body);
            return body;
        }
        // Refresh wizardState.allFilaments so a follow-up scan in the
        // same session sees the upgraded record (otherwise the next
        // computeFilamentBackfillDiff would think the same fields are
        // still missing).
        if (Array.isArray(wizardState.allFilaments)) {
            const idx = wizardState.allFilaments.findIndex(f => String(f.id) === String(existingId));
            if (idx >= 0 && body.filament) {
                wizardState.allFilaments[idx] = body.filament;
            }
        }
        if (!opts.suppressBanner) {
            const msg = document.getElementById('wiz-status-msg');
            if (msg) {
                const summary = Object.keys(silentDiff).map(k => k.replace(/^extra\./, '')).join(', ');
                msg.innerHTML = `<span class="text-success">✨ Updated existing Filament #${existingId} from scan: ${summary}.</span>`;
            }
        }
        return body;
    } catch (e) {
        console.error('backfill fetch failed', e);
        return null;
    }
};

const _formatSpoolWeightHint = (stored, scanned) => {
    // Heuristic: NFC Prusament spools are roughly 30-50g heavier than
    // legacy plastic. Hint only when the SCAN reports a heavier tare
    // than what's stored — i.e. the user is being offered an upgrade
    // from legacy to NFC. Earlier the hint fired in both directions,
    // which incorrectly tagged a lighter (older) replacement as NFC.
    const delta = Number(scanned) - Number(stored);
    if (delta >= 25 && delta <= 75) return ' (NFC?)';
    return '';
};

window.wizardRenderFilamentMismatchPanel = (existingId, mismatches) => {
    const host = document.getElementById('wiz-fil-mismatch-panel');
    if (!host) return;
    if (!mismatches || mismatches.length === 0) {
        host.innerHTML = '';
        host.style.display = 'none';
        return;
    }
    const rowsHtml = mismatches.map((m, i) => {
        const swatch = (val) => `<span style="display:inline-block;width:14px;height:14px;background:#${String(val).replace('#','')};border:1px solid #555;vertical-align:middle;margin-left:4px;"></span>`;
        const storedDisplay = m.kind === 'color'
            ? `#${m.stored}${swatch(m.stored)}`
            : escapeHtml(String(m.stored));
        let scannedDisplay = m.kind === 'color'
            ? `#${m.scanned}${swatch(m.scanned)}`
            : escapeHtml(String(m.scanned));
        if (m.kind === 'spool_weight') {
            scannedDisplay += `<span class="text-warning small">${_formatSpoolWeightHint(m.stored, m.scanned)}</span>`;
        }
        return `
            <tr data-mismatch-row="${i}" data-mismatch-key="${escapeHtml(m.key)}">
                <td class="text-secondary small">${escapeHtml(m.label)}</td>
                <td class="font-monospace">${storedDisplay}</td>
                <td class="font-monospace">${scannedDisplay}</td>
                <td>
                    <button type="button" class="btn btn-sm btn-outline-warning"
                        onclick="window.wizardApplyMismatchRow(${existingId}, ${i})">Use Scanned</button>
                </td>
            </tr>`;
    }).join('');
    host.innerHTML = `
        <div class="alert alert-warning my-2">
            <div class="mb-2"><strong>⚠ Scan data differs from Filament #${existingId}</strong> — pick what to keep:</div>
            <table class="table table-sm table-dark mb-2" style="font-size: 0.9em;">
                <thead><tr><th>Field</th><th>Stored</th><th>Scanned</th><th></th></tr></thead>
                <tbody id="wiz-fil-mismatch-rows">${rowsHtml}</tbody>
            </table>
            <button type="button" class="btn btn-sm btn-secondary"
                onclick="window.wizardClearFilamentMismatchPanel()">Dismiss</button>
        </div>
    `;
    host.style.display = 'block';
    wizardState._mismatches = mismatches;
};

window.wizardApplyMismatchRow = async (existingId, rowIdx) => {
    const list = wizardState._mismatches || [];
    const m = list[rowIdx];
    if (!m) return;
    const diff = {};
    if (m.key.startsWith('extra.')) {
        // Wrap text-type extras for sanitize_outbound_data.
        diff[m.key] = `"${m.scanned}"`;
    } else {
        diff[m.key] = m.scanned;
    }
    const res = await window.applyFilamentBackfillSilent(existingId, diff, { suppressBanner: true });
    if (res && res.success) {
        const tr = document.querySelector(`#wiz-fil-mismatch-rows tr[data-mismatch-row="${rowIdx}"]`);
        if (tr) {
            tr.innerHTML = `<td colspan="4" class="text-success small">✓ Updated ${escapeHtml(m.label)} → ${escapeHtml(String(m.scanned))}</td>`;
        }
    }
};

window.wizardClearFilamentMismatchPanel = () => {
    const host = document.getElementById('wiz-fil-mismatch-panel');
    if (host) {
        host.innerHTML = '';
        host.style.display = 'none';
    }
    wizardState._mismatches = null;
};

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

// --- Duplicate-filament picker (ambiguous matcher result) ---------------
// Reinstated after the user's request: when findFilamentMatches returns
// `definitive: false` (multiple basic-gate candidates with no Tier-1
// product-ID winner), defer to the user instead of silently picking
// lowest-id. The user explicitly wanted: "fall back to letting the user
// decide if we can't after all the matching attempts."
window.wizardRenderDuplicatePicker = (candidates, parsedTemplate) => {
    const host = document.getElementById('wiz-duplicate-picker');
    if (!host) return;
    if (!candidates || candidates.length === 0) {
        host.innerHTML = '';
        host.style.display = 'none';
        return;
    }
    const opts = candidates.map(f => {
        const v = (f.vendor && f.vendor.name) || 'Generic';
        const m = f.material || '?';
        const c = f.color_name || f.name || 'Unknown';
        return `<option value="${escapeHtml(String(f.id))}">${escapeHtml(`${v} ${m} - ${c} (ID: ${f.id})`)}</option>`;
    }).join('');
    host.innerHTML = `
        <div class="alert alert-warning d-flex flex-column gap-2 my-2">
            <div><strong>⚠ Multiple existing filaments match this scan</strong> — pick the right one to use, or create a fresh filament if none of these is correct:</div>
            <div class="d-flex gap-2 align-items-center flex-wrap">
                <select class="form-select form-select-sm bg-dark text-white border-secondary flex-grow-1" id="wiz-duplicate-picker-sel" style="min-width: 200px;">${opts}</select>
                <button type="button" class="btn btn-sm btn-success" onclick="window.wizardDuplicatePickerConfirm()">✓ Use selected</button>
                <button type="button" class="btn btn-sm btn-warning" onclick="window.wizardDuplicatePickerDismiss()">+ Create new filament</button>
            </div>
        </div>
    `;
    host.style.display = 'block';
    // Stash both candidates and parser template; confirm/dismiss both
    // need to know which template to feed downstream.
    wizardState._dupPicker = { candidates, parsedTemplate };
};

window.wizardDuplicatePickerConfirm = () => {
    const sel = document.getElementById('wiz-duplicate-picker-sel');
    const stash = wizardState._dupPicker || {};
    if (!sel || !stash.candidates) {
        window.wizardClearDuplicatePicker();
        return;
    }
    const id = sel.value;
    const match = stash.candidates.find(f => String(f.id) === String(id));
    if (match) {
        window.wizardAutoSwitchToExisting(match, stash.parsedTemplate);
    }
    window.wizardClearDuplicatePicker();
};

window.wizardDuplicatePickerDismiss = () => {
    const stash = wizardState._dupPicker || {};
    if (stash.parsedTemplate) {
        // User chose to create new — fill Step 2 from the parser template
        // so the wizard can proceed in manual create mode.
        window.applyFilamentFieldsFromTemplate(stash.parsedTemplate);
    }
    window.wizardClearDuplicatePicker();
};

window.wizardClearDuplicatePicker = () => {
    const host = document.getElementById('wiz-duplicate-picker');
    if (host) {
        host.innerHTML = '';
        host.style.display = 'none';
    }
    wizardState._dupPicker = null;
};

window.wizardResetSpoolRows = () => {
    wizardState.spoolRows = [];
    wizardState.filamentLockedFromScan = false;
    window.wizardSyncSpoolRows();
};
