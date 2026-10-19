/* MODULE: SLOT PICKER — Group 40.1 (Derek's D2 / D3 / D5, 2026-09-13) */
//
// One picker in front of every door that places a spool without naming a slot
// or a head: a multi-slot box's own label (40.2), Force Location (40.4),
// `LOC:XL` (40.5), Return with no usable slot (40.6) and the wizard (40.7). It
// shows what GET /api/placement_options builds (placement.py): each slot's
// spool, the toolhead it feeds and what that head runs now, and the ⭐ (the
// same rule the engine's auto-slot uses, so the star is the slot a slotless
// move would take).
//
// API:
//   window.openSlotPicker({
//       location: 'LR-MDB-1',   // required: a multi-slot box, or a Printer row
//       spool: 42,              // the spool being placed (⭐, its own slot, the title)
//       mode: 'return',         // Return only (40.6); box / printer come from the row
//       toolhead: 'XL-3',       // return mode: the head the spool leaves
//       host: modalEl,          // a Bootstrap modal/offcanvas: closing it cancels the picker
//       title: '…',             // optional heading
//       step: '1 of 3',         // optional: where a caller's loop is (40.2's several spools)
//       allowNone: true,        // a "No slot" tile (return mode shows one by default)
//       preselect: {slot: '2'} | {head: 'XL-4'},  // the first highlight (else the ⭐)
//   }) -> Promise<null
//              | {kind: 'slot', box, slot, occupant, claimants, feeds, free, current, recommended, via,
//                 send, expected_feed, choice, swap, displaced}
//              | {kind: 'pool', ...the same fields as 'slot' (Group 40.5: a Printer Pool slot is a box slot)}
//              | {kind: 'head', head, printer, resident, residents, feeds, spool_location, recommended, via}
//              | {kind: 'none', box, recommended, via}>
//   null = cancelled: Escape, ✕, a CMD:CANCEL scan, "Edit feeds", the host
//   closing, a bulk move or an audit starting, or an open refused (D2: another
//   dialog is up, a bulk move or an audit runs, FCC is busy). The picker writes
//   nothing: callers own the move and every confirm after it.
//
//   What a box-slot pick tells its caller to send (Group 40.2, D4): `send` is
//   {picked_slot: n} for a free slot (or the spool's own: kept only while still
//   free, and a slot feeding the head the spool is leaving stores it there, as
//   the tile says), and {slot: n} only after the user chose what happens to the
//   slot's spool (Swap / Overwrite, or the same-slot swap's "Swap it out"):
//   `slot` is the engine's Overwrite. `expected_feed` is what the tile showed the
//   slot feeding (a head id, or '' for a pool or storage slot), so a slot
//   re-pointed meanwhile is asked about again. `swap` / `displaced`: the user
//   chose Swap, so the caller sends `swap: true` (Swap option C): the server
//   files the slot's old spool back where it sat before the slot and hands it
//   to the buffer (`to_buffer`). Greyed-out slots (the model's `blocked`: two
//   spools claim it, it is bound to something that isn't a toolhead, its own
//   spool runs on another head, a stale record where nothing loads, and any
//   occupied slot in return mode) say why and are never picked.
//
//   window.routePickerScan(text) -> bool. processScan calls it right after
//   routeConfirmScan. While a picker is open it claims EVERY scan: a choice's
//   label picks it (LOC:<box>:SLOT:<n> or CMD:SLOT:<n> for a box; LOC:<head> or
//   a Printer Pool slot label for a printer), CMD:CANCEL cancels, and anything
//   else is refused with a 7 s warning, an Activity Log line and the panel's
//   own status line (toasts sit under the panel). It never falls through and
//   acts. A choice's label scanned while the picker is still loading is kept
//   and applied once the slots are drawn.
//   window.isSlotPickerOpen() -> bool.
//
// Keys (listed in the ? overlay): ←/→/↑/↓ move the highlight (wraps), 1–9
// highlight that slot (or the Nth choice), Enter picks the highlight, Escape
// cancels (mountOverlay owns it). A scanner burst stays the scan accumulator's
// (D1): an Enter while a scan is in flight is the scan's, and a digit is a
// hotkey only when the scan buffer was empty and nothing followed it within
// 50 ms (a 1–2 digit spool label is a scan, not two jumps and a pick). Focus in
// a field behind the picker never drives it. No text <input> anywhere: a
// focused input disarms the hardware scanner (the L298 lesson).
//
// Printers: the picker opens at once and asks each printer it touches itself
// (fetchPrinterStateDetailed through withPrinterCheck); its chip and every
// tile feeding one of its heads say "checking…", then printing / idle /
// couldn't reach / no login. withPrinterCheck's global pill sits under the
// picker's backdrop; the chips are what you see here.

(function () {
    const OVERLAY_ID = 'fcc-slot-picker';
    let _session = null;   // the open picker (one at a time)
    let _seq = 0;

    const _st = () => ((typeof state !== 'undefined') ? state : window.state) || {};
    const _esc = (s) => (window.escHtml ? window.escHtml(s) : String(s == null ? '' : s));
    const _u = (s) => String(s == null ? '' : s).replace(/"/g, '').trim().toUpperCase();
    const _normSlot = (s) => {
        const t = String(s == null ? '' : s).replace(/"/g, '').trim();
        return /^\d+$/.test(t) ? String(parseInt(t, 10)) : t;
    };
    const _warn = (msg) => {
        if (typeof showToast === 'function') showToast(msg, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
    };

    const _injectStyle = () => {
        if (document.getElementById('fcc-slot-picker-style')) return;
        const css = document.createElement('style');
        css.id = 'fcc-slot-picker-style';
        css.textContent = `
#${OVERLAY_ID} .fcc-sp-panel { width:min(1000px,96vw); max-height:90vh; display:flex; flex-direction:column; border:1px solid #0dcaf0; }
#${OVERLAY_ID} .fcc-sp-scroll { overflow:auto; }
#${OVERLAY_ID} .fcc-sp-grid { display:flex; flex-wrap:wrap; gap:10px; justify-content:center; padding:12px; }
#${OVERLAY_ID} .fcc-sp-section { width:100%; color:#9fe8ff; font-weight:800; font-size:0.85rem; letter-spacing:0.4px; margin:2px 4px -4px; }
#${OVERLAY_ID} .fcc-sp-tile { width:205px; min-height:210px; display:flex; flex-direction:column; gap:6px; align-items:stretch; text-align:left;
    background:#1b1b1b; color:#eee; border:2px solid #4a4a4a; border-radius:8px; padding:8px; cursor:pointer; }
#${OVERLAY_ID} .fcc-sp-tile:hover { border-color:#8a939b; }
#${OVERLAY_ID} .fcc-sp-tile.is-star { border-color:#ffc107; }
#${OVERLAY_ID} .fcc-sp-tile.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 3px rgba(13,202,240,0.55); outline:none; }
#${OVERLAY_ID} .fcc-sp-tile:focus { outline:none; }
#${OVERLAY_ID} .fcc-sp-top { display:flex; justify-content:space-between; align-items:center; gap:6px; }
#${OVERLAY_ID} .fcc-sp-num { font-weight:900; color:#ffd36b; letter-spacing:0.5px; font-size:0.95rem; }
#${OVERLAY_ID} .fcc-sp-star { font-size:0.72rem; font-weight:800; color:#111; background:#ffc107; border-radius:10px; padding:1px 7px; white-space:nowrap; }
#${OVERLAY_ID} .fcc-sp-empty { color:#c4c9ce; font-weight:800; font-size:1.05rem; text-align:center; padding:12px 0; border:1px dashed #5a5a5a; border-radius:6px; }
#${OVERLAY_ID} .fcc-sp-feed { font-size:0.85rem; color:#8fe3ff; font-weight:700; }
#${OVERLAY_ID} .fcc-sp-feed.is-other { color:#ffc27a; }
#${OVERLAY_ID} .fcc-sp-feed.is-storage { color:#c4c9ce; font-weight:600; }
#${OVERLAY_ID} .fcc-sp-res { font-size:0.8rem; color:#e6e6e6; }
#${OVERLAY_ID} .fcc-sp-note { font-size:0.78rem; color:#d0d0d0; }
#${OVERLAY_ID} .fcc-sp-warn { font-size:0.78rem; color:#ffc27a; font-weight:700; }
#${OVERLAY_ID} .fcc-sp-pstate { font-weight:800; }
#${OVERLAY_ID} .fcc-sp-pstate.is-printing { color:#ffa94d; }
#${OVERLAY_ID} .fcc-sp-pstate.is-idle { color:#69db7c; }
#${OVERLAY_ID} .fcc-sp-pstate.is-unknown { color:#ced4da; }
#${OVERLAY_ID} .fcc-sp-pchip { font-size:0.82rem; background:#26313a; border:1px solid #4f6b80; border-radius:12px; padding:2px 9px; white-space:nowrap; }
#${OVERLAY_ID} .fcc-sp-qr { align-self:center; background:#fff; padding:3px; border-radius:3px; line-height:0; margin-top:auto; }
#${OVERLAY_ID} .fcc-sp-footer { font-size:0.85rem; color:#e0e0e0; display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; justify-content:space-between; }
#${OVERLAY_ID} .fcc-sp-keys { color:#c8c8c8; font-size:0.8rem; }
#${OVERLAY_ID} .fcc-sp-msg { padding:14px 18px; font-size:1rem; }
#${OVERLAY_ID} .fcc-sp-link { color:#8fe3ff; text-decoration:underline; background:none; border:0; padding:0; font-size:0.85rem; }
#${OVERLAY_ID} .fcc-sp-tile.is-blocked { border-style:dashed; border-color:#6b5a3a; background:#151515; }
#${OVERLAY_ID} .fcc-sp-tile.is-blocked .fcc-sp-num { color:#b9a77f; }
#${OVERLAY_ID} .fcc-sp-tile.is-blocked.kb-active { border-color:#ffb74d; box-shadow:0 0 0 3px rgba(255,183,77,0.45); }
#${OVERLAY_ID} .fcc-sp-block { font-size:0.78rem; color:#ffd27a; font-weight:700; }
#${OVERLAY_ID} .fcc-sp-status { display:none; margin:10px 12px 0; padding:6px 10px; border-radius:6px; background:#4a3200; color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; }
#${OVERLAY_ID} .fcc-sp-step { font-size:0.8rem; font-weight:800; color:#111; background:#9fe8ff; border-radius:10px; padding:1px 8px; margin-left:8px; white-space:nowrap; }
#${OVERLAY_ID} .fcc-sp-choice { display:flex; gap:16px; padding:14px 18px; align-items:flex-start; flex-wrap:wrap; }
#${OVERLAY_ID} .fcc-sp-choice-card { width:205px; }
#${OVERLAY_ID} .fcc-sp-choice-text { flex:1; min-width:240px; font-size:1rem; color:#f1f1f1; }
#${OVERLAY_ID} .fcc-sp-choice-btns { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
#${OVERLAY_ID} .fcc-sp-choice-btn { display:flex; flex-direction:column; align-items:flex-start; min-width:150px; text-align:left; }
#${OVERLAY_ID} .fcc-sp-choice-btn small { font-weight:400; font-size:0.78rem; }
#${OVERLAY_ID} .fcc-sp-choice-btn:focus { box-shadow:0 0 0 3px rgba(13,202,240,0.6); }
`;
        document.head.appendChild(css);
    };

    // ---- session lifecycle -------------------------------------------------------

    const _dropChoiceQR = (s) => {
        if (s && s.choiceQR) { try { s.choiceQR.cleanup(); } catch (_) { /* noop */ } s.choiceQR = null; }
    };

    const _finish = (s, result) => {
        if (!s || s.settled) return;
        s.settled = true;
        _dropChoiceQR(s);
        clearTimeout(s.statusTimer);
        (s.disposers || []).forEach((d) => { try { d(); } catch (_) { /* noop */ } });
        s.disposers = [];
        if (s.handle) { try { s.handle.cleanup(); } catch (_) { /* noop */ } }
        if (_session === s) _session = null;
        try { s.resolve(result); } catch (_) { /* noop */ }
    };

    // D3: what a refusal says, said INSIDE the panel too (role=alert). The toast
    // layer (z 11000) sits under the picker (z 20000+), so a toast alone was
    // feedback nobody saw.
    const _flash = (s, text) => {
        if (!s || !s.handle || s.settled) return;
        const line = s.handle.element.querySelector('.fcc-sp-status');
        if (!line) return;
        line.textContent = text;
        line.style.display = 'block';
        clearTimeout(s.statusTimer);
        s.statusTimer = setTimeout(() => { line.style.display = 'none'; }, 7000);
    };

    // A refusal: the panel's status line, a 7 s warning toast and an Activity Log line.
    const _refuse = (s, text, logText) => {
        _flash(s, text);
        if (typeof showToast === 'function') showToast(text, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ ${logText || text}`, 'WARNING');
    };

    // D2: a bulk move or an audit started while the picker was open. Location
    // scans belong to that session now, so the picker gets out of the way.
    const _sessionStarted = () => {
        const st = _st();
        if (st.bulkMoveActive) return 'a bulk move';
        if (st.auditActive) return 'an audit';
        return '';
    };
    const _closeForSession = (s, what) => {
        if (!s || s.settled) return;
        const msg = `Slot picker closed: ${what} started, so nothing was placed`;
        if (typeof showToast === 'function') showToast(msg, 'warning', 7000);
        if (window.logClientEvent) window.logClientEvent(`⚠️ ${msg}`, 'WARNING');
        _finish(s, null);
    };

    const _isTopmost = (s) => {
        const mounts = document.querySelectorAll('[data-overlay-mount="1"]');
        return !!(mounts.length && s.handle && mounts[mounts.length - 1] === s.handle.element);
    };

    const _tileEls = (s) => (s.handle ? Array.from(s.handle.element.querySelectorAll('.fcc-sp-tile')) : []);

    const _setActive = (s, idx, focus = true) => {
        const els = _tileEls(s);
        if (!els.length) return;
        const i = ((idx % els.length) + els.length) % els.length;
        els.forEach((el) => el.classList.remove('kb-active'));
        els[i].classList.add('kb-active');
        s.activeIdx = i;
        if (focus) {
            try { els[i].focus({ preventScroll: true }); } catch (_) { try { els[i].focus(); } catch (__) { /* noop */ } }
            if (els[i].scrollIntoView) els[i].scrollIntoView({ block: 'nearest' });
        }
    };

    const _move = (s, delta) => {
        const els = _tileEls(s);
        if (!els.length) return;
        const cur = els.findIndex((el) => el.classList.contains('kb-active'));
        _setActive(s, cur < 0 ? (delta > 0 ? 0 : els.length - 1) : cur + delta);
    };

    // 1–9: that slot of a box; the Nth choice of a printer.
    const _jump = (s, n) => {
        const els = _tileEls(s);
        let i = -1;
        if (s.model && s.model.mode !== 'printer') {
            i = els.findIndex((el) => el.dataset.spKind === 'slot' && el.dataset.spSlot === String(n));
        } else if (n <= els.length) {
            i = n - 1;
        }
        if (i >= 0) _setActive(s, i);
    };

    // What a slot tile showed it feeds, as the engine's `feed` token (D4): a
    // head id, or '' for a Printer Pool or storage slot.
    const _feedToken = (feeds) => (feeds && feeds.kind === 'toolhead' ? _u(feeds.id) : '');

    // `choice`: what the user chose for an occupied slot ('swap', 'overwrite',
    // 'swap_out', 'put'); none for a free slot.
    const _resultFor = (s, t, via, choice = null) => {
        const d = t.data || {};
        const base = { kind: t.kind, recommended: !!t.star, via };
        // A Printer Pool slot (printer mode) is a box slot like any other (Group
        // 40.5): the same `send`, Swap / Overwrite and refusals.
        if (t.kind === 'slot' || t.kind === 'pool') {
            const occupant = d.spool || null;
            const swap = choice === 'swap';
            return Object.assign(base, { box: t.box, slot: t.slot, occupant,
                claimants: d.claimants || [], feeds: d.feeds || null, free: !!d.free, current: !!d.current,
                // D4: a free slot is a pick (kept only while still free); an
                // occupied one is the engine's Overwrite, sent only after a choice.
                // A slot that only stores the spool (stores_only) stays a store
                // after the choice too: an explicit slot otherwise loads it back
                // onto the head it is leaving (Group 40.2 review).
                send: d.free ? { picked_slot: t.slot }
                    : (d.stores_only ? { slot: t.slot, auto_deploy: false } : { slot: t.slot }),
                expected_feed: _feedToken(d.feeds),
                // A stale record in the slot: the engine refuses a store over it,
                // so the door's question offers none.
                store_ok: d.occupant_state !== 'stale',
                choice, swap,
                displaced: (swap && occupant) ? { id: occupant.id, display: occupant.display, color: occupant.color,
                    color_direction: occupant.color_direction, remaining_weight: occupant.remaining_weight,
                    details: occupant.details, archived: occupant.archived } : null });
        }
        if (t.kind === 'head') {
            // `spool_location`: where the spool is now, so the caller knows
            // whether it arrives from a box (its trail) or needs the "came from"
            // question (Group 40.5, D3).
            return Object.assign(base, { head: t.head, printer: s.model.location, resident: d.resident || null,
                residents: d.residents || [], feeds: d.feeds || [], spool_location: s.model.spool_location || '' });
        }
        return Object.assign(base, { box: t.box });
    };

    const _pick = (s, t, via) => {
        if (!s || s.settled || !t) return;
        const started = _sessionStarted();
        if (started) { _closeForSession(s, started); return; }
        const d = t.data || {};
        const boxSlot = t.kind === 'slot' || t.kind === 'pool';
        if (boxSlot && d.blocked) {
            // D4: greyed out, never picked; the panel says why.
            _refuse(s, `${t.box} slot ${t.slot}: ${d.blocked}`,
                `Slot picker: ${t.box} slot ${t.slot} can't take #${s.model && s.model.spool}: ${d.blocked}`);
            return;
        }
        if (boxSlot && !d.free && s.model && s.model.mode !== 'return') {
            // Q2 (decided 2026-10-13): an occupied slot asks what happens to its
            // spool, as the grid's Swap / Overwrite does, so the incoming spool
            // always gets a real slot.
            _openChoice(s, t, via);
            return;
        }
        _finish(s, _resultFor(s, t, via));
    };

    const _editFeeds = (s) => {
        const box = s.model && s.model.location;
        _finish(s, null);
        if (!box) return;
        // The Location Manager opens the box with its Feeds section expanded
        // (the Quick-Swap "Edit Full Bindings" one-shot). Re-mapping inside the
        // picker is left to Group 37.
        window._fccAutoExpandFeeds = true;
        if (window.openManage) window.openManage(box);
    };

    // ---- rendering ---------------------------------------------------------------

    const _card = (spool) => (window.SpoolCardBuilder
        ? window.SpoolCardBuilder.buildCard(spool, 'picker')
        : `<div>#${_esc(spool.id)}</div>`);

    const _ids = (list) => list.map((r) => `#${_esc(r.id)}`).join(' and ');

    const _runsLine = (head, residents) => {
        if (!residents || !residents.length) return `<div class="fcc-sp-res">${_esc(head)} is empty</div>`;
        if (residents.length > 1) {
            return `<div class="fcc-sp-warn">⚠️ ${_esc(head)} holds ${_ids(residents)}</div>`;
        }
        const r = residents[0];
        const from = r.from ? `from ${_esc(r.from)}` : "FCC doesn't know where it came from";
        return `<div class="fcc-sp-res">${_esc(head)} runs #${_esc(r.id)} (${from})</div>`;
    };

    const _pstate = (printer) => `<span class="fcc-sp-pstate is-unknown" data-sp-printer="${_esc(printer)}">checking…</span>`;

    const _slotTile = (s, t, i) => {
        const m = s.model;
        const d = t.data;
        const f = d.feeds;
        let feed = '<div class="fcc-sp-feed is-storage">Storage slot (feeds no toolhead)</div>';
        let extra = '';
        if (f && f.kind === 'toolhead') {
            // The engine's store_only rule (placement's stores_only; Group 40.2
            // review): the slot feeds the head the spool is leaving, or it is the
            // slot the spool was deployed from. Either way it is not loaded.
            const storesOnly = d.stores_only != null ? !!d.stores_only : !!f.is_source;
            feed = `<div class="fcc-sp-feed">→ ${_esc(f.id)} · ${_pstate(f.printer)}</div>`;
            if (storesOnly) {
                feed += f.is_source
                    ? `<div class="fcc-sp-note">#${_esc(m.spool)} is on ${_esc(f.id)} now: it is stored here, not loaded back</div>`
                    : `<div class="fcc-sp-note">#${_esc(m.spool)} came from this slot: it goes back in, stored, not loaded onto ${_esc(f.id)}</div>`;
            }
            extra = _runsLine(f.id, f.residents);
        } else if (f && f.kind === 'pool') {
            feed = `<div class="fcc-sp-feed">🏭 Printer Pool (${_esc(f.printer_name || f.printer)})</div>`;
        } else if (f && f.kind === 'other') {
            feed = `<div class="fcc-sp-feed is-other">→ ${_esc(f.id)} (not a toolhead)</div>`;
        }
        const body = d.spool ? _card(d.spool) : '<div class="fcc-sp-empty">EMPTY</div>';
        const more = (d.claimants || []).length > 1
            ? `<div class="fcc-sp-warn">⚠️ ${d.claimants.length} spools claim this slot (${d.claimants.map((c) => '#' + _esc(c)).join(', ')})</div>` : '';
        const here = d.current
            ? `<div class="fcc-sp-note">📍 #${_esc(m.spool)} ${_u(m.spool_location) === _u(m.location) ? 'sits here now' : 'came from here'}</div>` : '';
        // D4: a slot the picker can't take says why on the tile (and again, in
        // the status line, if it is picked anyway).
        const block = d.blocked ? `<div class="fcc-sp-block">⛔ ${_esc(d.blocked)}</div>` : '';
        const label = `${t.box} slot ${t.slot}${d.blocked ? ` (unavailable: ${d.blocked})` : ''}`;
        return `
            <button type="button" class="fcc-sp-tile${t.star ? ' is-star' : ''}${d.blocked ? ' is-blocked' : ''}" role="option"
                    data-sp-idx="${i}" data-sp-kind="slot" data-sp-box="${_esc(t.box)}" data-sp-slot="${_esc(t.slot)}"
                    ${d.blocked ? 'aria-disabled="true" data-sp-blocked="1"' : ''} aria-label="${_esc(label)}">
                <div class="fcc-sp-top"><span class="fcc-sp-num">SLOT ${_esc(t.slot)}</span>${t.star ? '<span class="fcc-sp-star">⭐ Recommended</span>' : ''}</div>
                ${body}${more}${feed}${extra}${here}${block}
                <div class="fcc-sp-qr" id="fcc-sp-qr-${s.id}-${i}"></div>
            </button>`;
    };

    const _noneTile = (s, t, i) => {
        const m = s.model;
        // Every other spool in the box (slotted or not), plus this one unslotted.
        const n = (m.slots || []).reduce((acc, sl) => acc + (sl.claimants || []).length, 0)
            + (m.unslotted || []).length + 1;
        return `
            <button type="button" class="fcc-sp-tile${t.star ? ' is-star' : ''}" role="option"
                    data-sp-idx="${i}" data-sp-kind="none" data-sp-box="${_esc(t.box)}" aria-label="No slot">
                <div class="fcc-sp-top"><span class="fcc-sp-num">NO SLOT</span>${t.star ? '<span class="fcc-sp-star">⭐ Recommended</span>' : ''}</div>
                <div class="fcc-sp-empty">—</div>
                <div class="fcc-sp-feed is-storage">In ${_esc(t.box)} without a slot</div>
                <div class="fcc-sp-warn">${_esc(t.box)} will show ${n}/${_esc(m.max_slots)}</div>
            </button>`;
    };

    const _headTile = (s, t, i) => {
        const h = t.data;
        const body = h.resident ? _card(h.resident) : '<div class="fcc-sp-empty">EMPTY</div>';
        const feeds = (h.feeds || []).length
            ? `<div class="fcc-sp-note">Fed by ${(h.feeds || []).map((f) => `${_esc(f.box)} slot ${_esc(f.slot)} ${f.free ? '(free)' : `(#${_esc(f.claimed_by)})`}`).join(' · ')}</div>`
            : '<div class="fcc-sp-note">No box slot feeds it</div>';
        const here = h.current ? `<div class="fcc-sp-note">📍 #${_esc(s.model.spool)} is on it now</div>` : '';
        return `
            <button type="button" class="fcc-sp-tile${t.star ? ' is-star' : ''}" role="option"
                    data-sp-idx="${i}" data-sp-kind="head" data-sp-head="${_esc(t.head)}" aria-label="${_esc(t.head)}">
                <div class="fcc-sp-top"><span class="fcc-sp-num">${_esc(t.head)}</span>${t.star ? '<span class="fcc-sp-star">⭐ Recommended</span>' : ''}</div>
                ${body}
                <div class="fcc-sp-feed">${_pstate(s.model.name)}</div>
                ${h.resident ? _runsLine(t.head, h.residents) : ''}${feeds}${here}
                <div class="fcc-sp-qr" id="fcc-sp-qr-${s.id}-${i}"></div>
            </button>`;
    };

    const _poolTile = (s, t, i) => {
        const p = t.data;
        const body = p.spool ? _card(p.spool) : '<div class="fcc-sp-empty">EMPTY</div>';
        // Group 40.5: the engine's refusals grey a pool slot out too.
        const block = p.blocked ? `<div class="fcc-sp-block">⛔ ${_esc(p.blocked)}</div>` : '';
        const label = `${t.box} slot ${t.slot}${p.blocked ? ` (unavailable: ${p.blocked})` : ''}`;
        return `
            <button type="button" class="fcc-sp-tile${t.star ? ' is-star' : ''}${p.blocked ? ' is-blocked' : ''}" role="option"
                    data-sp-idx="${i}" data-sp-kind="pool" data-sp-box="${_esc(t.box)}" data-sp-slot="${_esc(t.slot)}"
                    ${p.blocked ? 'aria-disabled="true" data-sp-blocked="1"' : ''} aria-label="${_esc(label)}">
                <div class="fcc-sp-top"><span class="fcc-sp-num">🏭 ${_esc(t.box)} slot ${_esc(t.slot)}</span>${t.star ? '<span class="fcc-sp-star">⭐</span>' : ''}</div>
                ${body}${block}
                <div class="fcc-sp-feed is-storage">Printer Pool: stages it, loads no toolhead</div>
                <div class="fcc-sp-qr" id="fcc-sp-qr-${s.id}-${i}"></div>
            </button>`;
    };

    // The choices, in the order they render: a box's slots in its grid's order
    // (an rtl box right-to-left), then No slot; a printer's heads, then its pool.
    const _buildTiles = (s) => {
        const m = s.model;
        const rec = m.recommended || null;
        const tiles = [];
        if (m.mode === 'printer') {
            (m.heads || []).forEach((h) => tiles.push({ kind: 'head', head: _u(h.id), data: h,
                star: !!(rec && rec.kind === 'head' && _u(rec.head) === _u(h.id)) }));
            (m.pool || []).forEach((p) => tiles.push({ kind: 'pool', box: _u(p.box), slot: _normSlot(p.slot), data: p,
                star: !!(rec && rec.kind === 'pool' && _u(rec.box) === _u(p.box) && _normSlot(rec.slot) === _normSlot(p.slot)) }));
            return tiles;
        }
        const slots = (m.slots || []).slice();
        if (m.slot_order === 'rtl') slots.reverse();
        slots.forEach((sl) => tiles.push({ kind: 'slot', box: _u(m.location), slot: _normSlot(sl.slot), data: sl,
            star: !!(rec && rec.kind === 'slot' && _normSlot(rec.slot) === _normSlot(sl.slot)) }));
        const allowNone = s.opts.allowNone != null ? !!s.opts.allowNone : !!m.allow_none;
        if (allowNone) tiles.push({ kind: 'none', box: _u(m.location), data: {}, star: !!(rec && rec.kind === 'none') });
        return tiles;
    };

    const _qrText = (t) => {
        if (t.kind === 'slot') return `CMD:SLOT:${t.slot}`;
        if (t.kind === 'pool') return `LOC:${t.box}:SLOT:${t.slot}`;
        if (t.kind === 'head') return `LOC:${t.head}`;
        return null;
    };

    const _title = (s) => {
        const m = s.model || {};
        if (s.opts.title) return s.opts.title;
        const who = (m.spool != null || s.opts.spool != null) ? `#${m.spool != null ? m.spool : s.opts.spool}` : 'the spool';
        if (m.mode === 'return') return `Return ${who} to which slot of ${m.location}?`;
        if (m.mode === 'printer') return `Where on ${m.name || m.location} should ${who} go?`;
        return `Which slot of ${m.location || s.location} should ${who} go in?`;
    };

    const _footer = (s) => {
        const m = s.model;
        const rec = m.recommended;
        let line = '';
        if (rec && rec.kind === 'slot') line = `⭐ Slot ${_esc(rec.slot)}: ${_esc(m.recommend_text)}`;
        else if (rec && rec.kind === 'none') line = `⭐ No slot: ${_esc(m.recommend_text)}`;
        else if (rec && rec.kind === 'head') line = `⭐ ${_esc(rec.head)}: ${_esc(m.recommend_text)}`;
        else if (rec && rec.kind === 'pool') line = `⭐ ${_esc(rec.box)} slot ${_esc(rec.slot)}: ${_esc(m.recommend_text)}`;
        else if (m.recommend_text) line = `No ⭐: ${_esc(m.recommend_text)}`;
        const feeds = m.mode !== 'printer'
            ? `<button type="button" class="fcc-sp-link" data-sp-act="feeds" title="Open ${_esc(m.location)} with its Feeds section">🔗 Edit feeds</button>` : '';
        return `
            <div class="d-flex flex-column gap-1">
                <div>${line}</div>
                <div class="fcc-sp-keys">←/→ move · 1–9 jump · Enter picks · Esc cancels · or scan a choice's label</div>
                <div>${feeds}</div>
            </div>
            <div class="d-flex align-items-center gap-3">
                <div class="d-flex flex-column align-items-center" title="Scan to cancel">
                    <div class="fcc-sp-qr" id="fcc-sp-qr-${s.id}-cancel"></div>
                    <div style="font-size:0.66rem; color:#c8c8c8; font-weight:700;">📷 CANCEL</div>
                </div>
                <button type="button" class="btn btn-sm btn-secondary" data-sp-act="cancel">Cancel</button>
            </div>`;
    };

    const _header = (s, chips) => {
        const m = s.model || {};
        const sub = m.spool_display ? `<div class="small" style="color:#e0e0e0;">${_esc(m.spool_display)}</div>` : '';
        const step = s.opts.step ? `<span class="fcc-sp-step">${_esc(s.opts.step)}</span>` : '';
        return `
            <div class="card-header d-flex align-items-start justify-content-between gap-2">
                <div><div class="fw-bold text-info" style="font-size:1.1rem;">🎯 ${_esc(_title(s))}${step}</div>${sub}</div>
                <div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">${chips || ''}
                    <button type="button" class="btn-close btn-close-white" data-sp-act="cancel" title="Cancel (Esc)" aria-label="Cancel"></button>
                </div>
            </div>
            <div class="fcc-sp-status" role="alert"></div>`;
    };

    const _setContent = (s, html) => {
        if (!s.handle || s.settled) return;
        s.handle.setContent(html);
    };

    const _renderLoading = (s) => {
        _setContent(s, `
            <div class="card bg-dark text-light shadow-lg fcc-sp-panel" data-sp-state="loading" tabindex="-1">
                ${_header(s)}
                <div class="fcc-sp-msg">⏳ Loading ${_esc(s.location)}…</div>
            </div>`);
        // D1: the panel takes the focus at once, so a field behind it (the
        // Location Manager's ID box, say) no longer receives a scanner's keys.
        const panel = s.handle && s.handle.element.querySelector('.fcc-sp-panel');
        if (panel) { try { panel.focus({ preventScroll: true }); } catch (_) { try { panel.focus(); } catch (__) { /* noop */ } } }
    };

    const _renderMessage = (s, text, retry) => {
        _setContent(s, `
            <div class="card bg-dark text-light shadow-lg fcc-sp-panel" data-sp-state="message">
                ${_header(s)}
                <div class="fcc-sp-msg">${_esc(text)}</div>
                <div class="card-footer d-flex justify-content-end gap-2">
                    ${retry ? '<button type="button" class="btn btn-sm btn-info" data-sp-act="retry">Retry</button>' : ''}
                    <button type="button" class="btn btn-sm btn-secondary" data-sp-act="cancel">Cancel</button>
                </div>
            </div>`);
        const first = s.handle && s.handle.element.querySelector('[data-sp-act="retry"], [data-sp-act="cancel"]');
        if (first) { try { first.focus(); } catch (_) { /* noop */ } }
    };

    const _render = (s) => {
        const m = s.model;
        s.tiles = _buildTiles(s);
        const chips = (m.printers || []).map((p) =>
            `<span class="fcc-sp-pchip">🖨️ ${_esc(p.name)} · ${_pstate(p.name)}</span>`).join('');
        let grid = '';
        s.tiles.forEach((t, i) => {
            if (m.mode === 'printer' && t.kind === 'pool' && (i === 0 || s.tiles[i - 1].kind !== 'pool')) {
                grid += '<div class="fcc-sp-section">🏭 PRINTER POOL (stages a spool, loads no toolhead)</div>';
            }
            if (t.kind === 'slot') grid += _slotTile(s, t, i);
            else if (t.kind === 'none') grid += _noneTile(s, t, i);
            else if (t.kind === 'head') grid += _headTile(s, t, i);
            else grid += _poolTile(s, t, i);
        });
        const msg = m.msg ? `<div class="fcc-sp-msg">${_esc(m.msg)}</div>` : '';
        const empty = !s.tiles.length && !m.msg ? '<div class="fcc-sp-msg">Nothing to pick here.</div>' : '';
        s.view = 'grid';
        _setContent(s, `
            <div class="card bg-dark text-light shadow-lg fcc-sp-panel" data-sp-state="ready" data-sp-mode="${_esc(m.mode)}" tabindex="-1">
                ${_header(s, chips)}
                <div class="card-body p-0 fcc-sp-scroll">${msg}${empty}<div class="fcc-sp-grid" role="listbox">${grid}</div></div>
                <div class="card-footer fcc-sp-footer">${_footer(s)}</div>
            </div>`);
        // QR codes: each choice's own label, so the screen can be scanned too.
        if (typeof generateSafeQR === 'function') {
            s.tiles.forEach((t, i) => { const q = _qrText(t); if (q) generateSafeQR(`fcc-sp-qr-${s.id}-${i}`, q, 56); });
            generateSafeQR(`fcc-sp-qr-${s.id}-cancel`, 'CMD:CANCEL', 48);
        }
        // First highlight: the caller's preselect (or the tile a Back returned
        // from), else the ⭐, else the first slot the picker can take.
        const pre = s.returnTo || s.opts.preselect || {};
        s.returnTo = null;
        let idx = s.tiles.findIndex((t) => (pre.slot != null && (t.kind === 'slot' || t.kind === 'pool')
            && t.slot === _normSlot(pre.slot) && (!pre.box || _u(pre.box) === t.box))
            || (pre.head && t.kind === 'head' && t.head === _u(pre.head)));
        if (idx < 0) idx = s.tiles.findIndex((t) => t.star && !(t.data && t.data.blocked));
        if (idx < 0) idx = s.tiles.findIndex((t) => !(t.data && t.data.blocked));
        if (s.tiles.length) _setActive(s, idx < 0 ? 0 : idx);
        else {
            const c = s.handle.element.querySelector('[data-sp-act="cancel"]');
            if (c) { try { c.focus(); } catch (_) { /* noop */ } }
        }
        // Re-apply printer answers that came in before this render.
        Object.keys(s.printerState).forEach((name) => _paintPrinter(s, name));
    };

    // ---- an occupied slot: what happens to its spool (Q2, D4) -------------------------

    // The actions for an occupied slot's spool, by what it is (placement's
    // occupant_state). A stored spool gets the grid's Swap / Overwrite. The
    // slot's own spool running on the head the slot feeds is the same-slot swap
    // (it comes off into the scan buffer either way, so there is one action). A
    // stale record on a slot that loads a head is ignored by the load.
    const _choiceFor = (s, t) => {
        const d = t.data || {};
        const occ = d.spool || {};
        const feed = d.feeds || null;
        const who = `#${occ.id}${occ.display ? ` (${occ.display})` : ''}`;
        const incoming = s.model && s.model.spool != null ? `#${s.model.spool}` : 'the spool';
        const storesOnly = d.stores_only != null ? !!d.stores_only : !!(feed && feed.is_source);
        const loads = !!(feed && feed.kind === 'toolhead' && !storesOnly);
        const onto = loads ? ` and onto ${feed.id}` : '';
        if (d.occupant_state === 'on_feed') {
            return {
                text: `Slot ${t.slot}'s spool ${who} is loaded on ${_u(occ.deployed_to)}. ${incoming} goes in slot ${t.slot}${onto}, `
                    + `and #${occ.id} comes off into your scan buffer.`,
                actions: [{ key: 'swap_out', label: 'Swap it out', sub: `#${occ.id} → your scan buffer`, qr: 'Scan to Swap it out' }],
            };
        }
        if (d.occupant_state === 'stale') {
            const dep = _u(occ.deployed_to);
            return {
                text: `#${occ.id}'s record still names slot ${t.slot}, though it is ${dep ? `on ${dep}` : 'in Unassigned'}. `
                    + `${incoming} goes in slot ${t.slot}${onto}; #${occ.id}'s record is left as it is.`,
                actions: [{ key: 'put', label: `Put it in slot ${t.slot}`, sub: `#${occ.id} isn't moved`, qr: 'Scan to put it there' }],
            };
        }
        const stored = (storesOnly && feed && feed.kind === 'toolhead') ? ` It is stored there, not loaded onto ${feed.id}.` : '';
        // Swap option C: a Swap hands the old spool to your buffer AND files it
        // back where it sat before this slot (the model's `swap_to`, by the
        // engine's own rule; '' when FCC has no record, so it is Unassigned).
        const swapSub = typeof d.swap_to === 'string'
            ? (d.swap_to ? `#${occ.id} → your buffer, filed back in ${d.swap_to}`
                : `#${occ.id} → your buffer (Unassigned until you scan it somewhere)`)
            : `#${occ.id} → your scan buffer`;
        return {
            text: `Slot ${t.slot} holds ${who}. Put ${incoming} in slot ${t.slot}${onto}?${stored}`,
            actions: [
                { key: 'swap', label: 'Swap', sub: swapSub, qr: 'Scan to Swap' },
                { key: 'overwrite', label: 'Overwrite', sub: `#${occ.id} stays in ${t.box} without a slot`, qr: 'Scan to Overwrite' },
            ],
        };
    };

    const _openChoice = (s, t, via) => {
        const c = _choiceFor(s, t);
        const actions = c.actions.concat([{ key: 'back', label: 'Back', sub: 'pick another slot' }]);
        s.view = 'choice';
        s.choice = { tile: t, via, actions };
        const occ = (t.data && t.data.spool) || null;
        const btns = actions.map((a, i) => `
            <button type="button" class="btn btn-sm ${a.key === 'back' ? 'btn-secondary' : (i === 0 ? 'btn-warning' : 'btn-info')} fcc-sp-choice-btn"
                    data-sp-choice="${_esc(a.key)}">${_esc(a.label)}<small>${_esc(a.sub || '')}</small></button>`).join('');
        _setContent(s, `
            <div class="card bg-dark text-light shadow-lg fcc-sp-panel" data-sp-state="choice" data-sp-slot="${_esc(t.slot)}" tabindex="-1">
                ${_header(s)}
                <div class="fcc-sp-choice">
                    <div class="fcc-sp-choice-card">${occ ? _card(occ) : ''}</div>
                    <div class="fcc-sp-choice-text">
                        <div class="fw-bold" style="color:#ffd36b;">${_esc(t.box)} slot ${_esc(t.slot)}</div>
                        <div class="fcc-sp-choice-msg">${_esc(c.text)}</div>
                        <div class="fcc-sp-choice-btns">${btns}</div>
                        <div class="fcc-sp-choice-qrs"></div>
                    </div>
                </div>
                <div class="card-footer fcc-sp-footer"><div class="fcc-sp-keys">←/→ move · Enter chooses · Back returns to the slots · Esc cancels · or scan a choice's QR</div></div>
            </div>`);
        // Scannable choices (session-scoped, so a stale printout can't fire):
        // the first action, Overwrite as the third QR, and Back as the cancel.
        if (window.attachConfirmQRs) {
            const host = s.handle.element.querySelector('.fcc-sp-choice-qrs');
            const first = c.actions[0];
            const over = c.actions.find((a) => a.key === 'overwrite');
            s.choiceQR = window.attachConfirmQRs({
                host,
                onConfirm: () => _choose(s, first.key),
                onStore: over ? () => _choose(s, over.key) : undefined,
                onCancel: () => _choose(s, 'back'),
                confirmLabel: first.qr, storeLabel: over ? over.qr : undefined, cancelLabel: 'Scan to go Back',
                theme: 'info',
            });
        }
        const btn = s.handle.element.querySelector('[data-sp-choice]');
        if (btn) { try { btn.focus(); } catch (_) { /* noop */ } }
    };

    const _choose = (s, key) => {
        if (!s || s.settled || s.view !== 'choice' || !s.choice) return;
        const { tile, via } = s.choice;
        _dropChoiceQR(s);
        if (key === 'back') {
            s.view = 'grid';
            s.choice = null;
            s.returnTo = { slot: tile.slot, box: tile.box };
            _render(s);
            return;
        }
        const started = _sessionStarted();
        if (started) { _closeForSession(s, started); return; }
        _finish(s, _resultFor(s, tile, via, key));
    };

    // ---- printer state ---------------------------------------------------------------

    const _paintPrinter = (s, name) => {
        const d = s.printerState[name];
        if (!d || !s.handle) return;
        let text = "couldn't reach";
        let cls = 'is-unknown';
        if (d.known && d.active) { text = String(d.state || 'PRINTING').toLowerCase(); cls = 'is-printing'; }
        else if (d.known) { text = 'idle'; cls = 'is-idle'; }
        else if (d.reason === 'no_credentials') text = 'no login';
        s.handle.element.querySelectorAll('[data-sp-printer]').forEach((el) => {
            if (el.getAttribute('data-sp-printer') !== name) return;
            el.textContent = text;
            el.classList.remove('is-printing', 'is-idle', 'is-unknown');
            el.classList.add(cls);
        });
    };

    const _probe = (s) => {
        const printers = (s.model && s.model.printers) || [];
        printers.forEach((p) => {
            if (!p || !p.head || !window.fetchPrinterStateDetailed) return;
            const fallback = { active: false, known: false, reason: 'timeout', state: null, printer_name: p.name };
            const probe = window.withPrinterCheck
                ? window.withPrinterCheck(p.name, window.fetchPrinterStateDetailed(p.head), { fallback })
                : window.fetchPrinterStateDetailed(p.head);
            Promise.resolve(probe).then((d) => {
                if (s.settled) return;
                s.printerState[p.name] = d || fallback;
                _paintPrinter(s, p.name);
            }).catch(() => {
                if (s.settled) return;
                s.printerState[p.name] = fallback;
                _paintPrinter(s, p.name);
            });
        });
    };

    // ---- load ---------------------------------------------------------------------

    // D3: a choice's label scanned while the slots were loading, applied once
    // they are drawn (or refused, if they never are).
    const _applyPendingScan = (s, ok) => {
        const text = s.pendingScan;
        s.pendingScan = null;
        if (!text || s.settled) return;
        if (ok) { window.routePickerScan(text); return; }
        _refuse(s, `"${text}" wasn't applied: the slot picker couldn't load ${s.location}`);
    };

    const _load = (s) => {
        if (s.settled) return;
        const gen = ++s.loadGen;
        s.model = null;   // loading: a choice's label scanned now waits for the slots
        s.tiles = [];
        s.view = 'loading';
        _renderLoading(s);
        const q = new URLSearchParams({ location: s.location });
        if (s.opts.spool != null && s.opts.spool !== '') q.set('spool', String(s.opts.spool));
        if (s.opts.toolhead) q.set('toolhead', String(s.opts.toolhead));
        if (s.opts.mode) q.set('mode', String(s.opts.mode));
        const url = `/api/placement_options?${q.toString()}`;
        const req = window.fetchT ? window.fetchT(url, {}, 10000) : fetch(url);
        req.then((r) => r.json().then((body) => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (s.settled || gen !== s.loadGen) return;
                if (!ok) {
                    const why = (body && body.msg) || 'The slot picker could not open here.';
                    if (window.logClientEvent) window.logClientEvent(`⚠️ Slot picker for ${s.location}: ${why}`, 'WARNING');
                    s.model = body || {};
                    s.view = 'message';
                    _renderMessage(s, why, false);
                    _applyPendingScan(s, false);
                    return;
                }
                s.model = body || {};
                if (s.model.read_ok === false) {
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Slot picker for ${s.location}: ${s.model.read_error || "couldn't read Spoolman"}`, 'WARNING');
                    s.view = 'message';
                    _renderMessage(s, `⚠️ Couldn't read Spoolman, so FCC can't tell which places are free. Retry in a moment, or cancel.`, true);
                    _applyPendingScan(s, false);
                    return;
                }
                _render(s);
                _probe(s);
                _applyPendingScan(s, true);
            })
            .catch((e) => {
                if (s.settled || gen !== s.loadGen) return;
                const why = (e && e.message) || 'network error';
                if (window.logClientEvent) window.logClientEvent(`⚠️ Slot picker for ${s.location} didn't load: ${why}`, 'WARNING');
                s.model = { read_ok: false };
                s.view = 'message';
                _renderMessage(s, `⚠️ The slot picker couldn't load (${why}). Retry, or cancel.`, true);
                _applyPendingScan(s, false);
            });
    };

    // ---- keys ---------------------------------------------------------------------

    // D1, a digit as a hotkey: nothing may follow it within HOTKEY_WAIT_MS (a
    // scanner types its next key in a few ms), and a key that follows it within
    // HOTKEY_HOLD_MS still makes it a scan (a slower scanner, Group 40.2 review).
    const HOTKEY_WAIT_MS = 50;
    const HOTKEY_HOLD_MS = 300;

    // A scan owns its Enter (D1): two or more characters in the scan buffer (a
    // slow scanner's 2-digit label still in it; a digit hotkey no longer clears
    // it), one in flight (under 500 ms), a scanner-speed burst, or a buffer that
    // looks like a scan payload. That Enter reaches processScan, then
    // routePickerScan, which refuses it. Only the lone digit just taken as a
    // hotkey, then Enter, is a person picking.
    const _enterIsAScans = (s) => {
        const buf = String(_st().scanBuffer || '');
        if (s && s.hotkey && buf === s.hotkey.digit) return false;
        if (buf.length >= 2) return true;
        if (window.isScanInFlight && window.isScanInFlight()) return true;
        if (window.isScannerBurst && window.isScannerBurst()) return true;
        return !!(buf && window.looksLikeScanPayload && window.looksLikeScanPayload(buf));
    };

    // A digit key, in any view (the digit is collected by the scan accumulator
    // meanwhile). In the grid it highlights that slot once nothing followed it;
    // a digit that follows a hotkey within HOTKEY_HOLD_MS puts the highlight back
    // (the two were a slow scanner's label). A lone digit nothing followed is
    // dropped from the scan buffer in every view, so the next scan isn't read as
    // "2LOC:…" (Group 40.2 review: the loading view and the Swap / Overwrite step
    // used to keep it).
    const _digitKey = (s, k) => {
        if (window.isScannerBurst && window.isScannerBurst()) return;
        if (String(_st().scanBuffer || '')) {
            if (s.hotkey && Date.now() - s.hotkey.at < HOTKEY_HOLD_MS) {
                if (s.view === 'grid' && s.hotkey.from >= 0) _setActive(s, s.hotkey.from);
                s.hotkey = null;
            }
            return;
        }
        setTimeout(() => {
            if (s.settled || _session !== s) return;
            if (_st().scanBuffer !== k) return;   // more keys came: a scan, not a hotkey
            if (s.view === 'grid') {
                s.hotkey = { digit: k, at: Date.now(), from: s.activeIdx };
                _jump(s, parseInt(k, 10));
            }
            setTimeout(() => {
                if (_st().scanBuffer === k && window.clearScanBuffer) window.clearScanBuffer();
                if (s.hotkey && s.hotkey.digit === k) s.hotkey = null;
            }, HOTKEY_HOLD_MS);
        }, HOTKEY_WAIT_MS);
    };

    const _choiceKeys = (s, e, k) => {
        const btns = Array.from(s.handle.element.querySelectorAll('[data-sp-choice]'));
        if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'ArrowLeft' || k === 'ArrowUp' || k === 'Tab') {
            e.preventDefault();
            e.stopImmediatePropagation();
            const back = k === 'ArrowLeft' || k === 'ArrowUp' || (k === 'Tab' && e.shiftKey);
            const at = btns.indexOf(document.activeElement);
            const next = at < 0 ? (back ? btns.length - 1 : 0) : (at + (back ? btns.length - 1 : 1)) % btns.length;
            if (btns[next]) { try { btns[next].focus(); } catch (_) { /* noop */ } }
            return;
        }
        if (k === 'Enter') {
            if (_enterIsAScans(s)) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
            const ae = document.activeElement;
            if (ae && ae.matches && ae.matches('[data-sp-act]')) { ae.click(); return; }
            const btn = btns.includes(ae) ? ae : btns[0];
            if (btn) _choose(s, btn.getAttribute('data-sp-choice'));
            return;
        }
        // A digit jumps nowhere here, but a lone one is still dropped from the
        // scan buffer.
        if (/^[1-9]$/.test(k)) _digitKey(s, k);
    };

    const _keyHandler = (s) => (e) => {
        if (_session !== s || s.settled || !_isTopmost(s)) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        // D1: a key aimed at a field behind the picker (focus outside its panel)
        // never drives it: a scan typed into that field used to pick a slot.
        const ae = document.activeElement;
        if (ae && ae !== document.body && s.handle && !s.handle.element.contains(ae)) return;
        const k = e.key;
        if (s.view === 'choice') { _choiceKeys(s, e, k); return; }
        if (k === 'Tab') {
            // Tab stays inside the panel (its tiles and buttons): focus that
            // left it would leave every key above ignored.
            const items = Array.from(s.handle.element.querySelectorAll('.fcc-sp-tile, [data-sp-act]'));
            if (!items.length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            const at = items.indexOf(ae);
            const next = at < 0 ? (e.shiftKey ? items.length - 1 : 0)
                : (at + (e.shiftKey ? items.length - 1 : 1)) % items.length;
            try { items[next].focus(); } catch (_) { /* noop */ }
            return;
        }
        if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'ArrowLeft' || k === 'ArrowUp') {
            e.preventDefault();
            e.stopImmediatePropagation();
            _move(s, (k === 'ArrowRight' || k === 'ArrowDown') ? 1 : -1);
            return;
        }
        if (k === 'Enter') {
            if (_enterIsAScans(s)) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
            s.hotkey = null;
            if (ae && s.handle && s.handle.element.contains(ae) && ae.matches && ae.matches('[data-sp-act]')) {
                ae.click();
                return;
            }
            const els = _tileEls(s);
            const el = els.find((x) => x.classList.contains('kb-active'));
            if (el) _pick(s, s.tiles[parseInt(el.dataset.spIdx, 10)], 'key');
            return;
        }
        // D1: a scan may start with a digit, and a short spool label is all
        // digits (_digitKey says when a digit is a person's hotkey).
        if (/^[1-9]$/.test(k)) _digitKey(s, k);
    };

    // ---- mount --------------------------------------------------------------------

    const _mount = (s) => {
        _injectStyle();
        const overlayOpen = !!document.querySelector('[data-overlay-mount="1"]');
        s.handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: '<div class="card bg-dark text-light fcc-sp-panel"></div>',
            // Above another overlay when opened from one; a Bootstrap modal sits below either tier.
            tier: overlayOpen ? 'confirm' : 'standard',
            host: s.opts.host || undefined,
            backdrop: true,
            occlude: ['select'],
            onEscape: () => _finish(s, null),
        });
        const root = s.handle.element;
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-label', 'Slot picker');
        // Delegated on the root, so a re-render (setContent) keeps them.
        const onClick = (e) => {
            if (s.settled) return;
            const act = e.target.closest && e.target.closest('[data-sp-act]');
            if (act) {
                e.preventDefault();
                const a = act.getAttribute('data-sp-act');
                if (a === 'cancel') _finish(s, null);
                else if (a === 'retry') _load(s);
                else if (a === 'feeds') _editFeeds(s);
                return;
            }
            const choice = e.target.closest && e.target.closest('[data-sp-choice]');
            if (choice) {
                e.preventDefault();
                _choose(s, choice.getAttribute('data-sp-choice'));
                return;
            }
            const tile = e.target.closest && e.target.closest('.fcc-sp-tile');
            if (tile) _pick(s, s.tiles[parseInt(tile.dataset.spIdx, 10)], 'click');
        };
        const onFocus = (e) => {
            const tile = e.target.closest && e.target.closest('.fcc-sp-tile');
            if (!tile || tile.classList.contains('kb-active')) return;
            _tileEls(s).forEach((el) => el.classList.remove('kb-active'));
            tile.classList.add('kb-active');
        };
        root.addEventListener('click', onClick);
        root.addEventListener('focusin', onFocus);
        const keys = _keyHandler(s);
        document.addEventListener('keydown', keys, true);
        s.disposers.push(() => document.removeEventListener('keydown', keys, true));
        // mountOverlay cleans the DOM when the host closes; the caller's promise
        // must hear about it too (as a cancel).
        const host = s.opts.host;
        if (host && typeof host.addEventListener === 'function') {
            const onHostClose = () => _finish(s, null);
            host.addEventListener('hidden.bs.modal', onHostClose);
            host.addEventListener('hidden.bs.offcanvas', onHostClose);
            s.disposers.push(() => {
                host.removeEventListener('hidden.bs.modal', onHostClose);
                host.removeEventListener('hidden.bs.offcanvas', onHostClose);
            });
        }
        // D2: a bulk move or an audit that starts while the picker is open (in
        // another tab, say: the heartbeat brings it) owns the location scans, so
        // the picker closes itself.
        const onPulse = () => {
            const started = _sessionStarted();
            if (started) _closeForSession(s, started);
        };
        document.addEventListener('inventory:sync-pulse', onPulse);
        s.disposers.push(() => document.removeEventListener('inventory:sync-pulse', onPulse));
    };

    // D2: why the picker must not open now, or ''. It never stacks over another
    // dialog (one Escape cancelled the dialog underneath, a second the picker),
    // never runs over an audit or a gating dialog, and never starts while FCC is
    // still handling the last scan.
    const _openBlockedBy = () => {
        const st = _st();
        if (st.auditActive) return 'The slot picker waits until the audit is finished or cancelled';
        if (st.activeModal) return 'Answer the dialog on screen first, then try again';
        if (st.processing) return 'FCC is still handling the last scan: try again in a moment';
        const mine = _session && _session.handle ? _session.handle.element : null;
        const other = Array.from(document.querySelectorAll('[data-overlay-mount="1"]')).find((el) => el !== mine);
        if (other) return 'Finish or close the dialog on screen first: the slot picker won\'t open over it';
        return '';
    };

    // ---- public -------------------------------------------------------------------

    window.openSlotPicker = (opts = {}) => {
        const o = opts || {};
        const loc = _u(o.location);
        if (!loc) return Promise.resolve(null);
        // Location scans belong to a bulk-move session while one is armed.
        if (_st().bulkMoveActive) {
            if (typeof showToast === 'function') showToast('The slot picker waits until the bulk move is finished or cancelled', 'info', 4000);
            if (window.logClientEvent) window.logClientEvent(`ℹ️ Slot picker for ${loc} not opened: a bulk move is armed`, 'INFO');
            return Promise.resolve(null);
        }
        const blocked = _openBlockedBy();
        if (blocked) {
            if (typeof showToast === 'function') showToast(blocked, 'warning', 7000);
            if (window.logClientEvent) window.logClientEvent(`⚠️ Slot picker for ${loc} not opened: ${blocked}`, 'WARNING');
            return Promise.resolve(null);
        }
        if (_session) _finish(_session, null);   // one picker at a time
        return new Promise((resolve) => {
            const s = { id: ++_seq, opts: o, location: loc, resolve, settled: false, model: null,
                tiles: [], printerState: {}, disposers: [], loadGen: 0, activeIdx: -1,
                view: 'loading', choice: null, choiceQR: null, pendingScan: null, statusTimer: null, returnTo: null };
            _session = s;
            _mount(s);
            _load(s);
        });
    };

    window.isSlotPickerOpen = () => !!(_session && !_session.settled);

    // A choice's label (what the picker could pick once loaded): a slot label,
    // CMD:SLOT:<n>, or another location's LOC: label (a printer's head). The
    // label of the place the picker is for is not one.
    const _looksLikeAChoice = (up, s) => /^LOC:.+:SLOT:\d+$/.test(up) || /^CMD:SLOT:\d+$/.test(up)
        || (up.startsWith('LOC:') && !up.includes(':SLOT:') && up.slice(4).trim() !== s.location);

    window.routePickerScan = (text) => {
        const s = _session;
        if (!s || s.settled) return false;
        const up = String(text == null ? '' : text).trim().toUpperCase();
        if (!up) return false;
        if (up === 'CMD:CANCEL') {
            // D3: said, not silent.
            if (typeof showToast === 'function') showToast('Slot picker cancelled — nothing moved', 'info', 4000);
            if (window.logClientEvent) window.logClientEvent(
                `ℹ️ Slot picker for ${s.location} cancelled by a CMD:CANCEL scan — nothing moved`, 'INFO');
            _finish(s, null);
            return true;
        }
        if (up.startsWith('CMD:CANCEL:')) {
            // A session's cancel QR whose dialog has gone (routeConfirmScan
            // answers a live one first): the second read of "Back", or of a load
            // question's Cancel the loop stepped back from. It used to cancel the
            // whole picker (Group 40.2 review); only the picker's own CMD:CANCEL does.
            _flash(s, 'That cancel QR belongs to a step that has closed: ignored');
            if (window.logClientEvent) window.logClientEvent(
                `ℹ️ Stale cancel QR "${String(text).trim()}" ignored by the slot picker for ${s.location}`, 'INFO');
            return true;
        }
        if (s.view === 'choice') {
            // Its own choices have session QRs (routeConfirmScan answers them
            // first); any other label waits.
            _refuse(s, `Choose what happens to slot ${s.choice && s.choice.tile ? s.choice.tile.slot : ''}'s spool first, or Back. (Ignored: ${text})`,
                `Scan "${text}" ignored: the slot picker is asking what happens to a slot's spool`);
            return true;
        }
        if (s.view === 'loading' && !s.model && _looksLikeAChoice(up, s)) {
            // D3: scanned before the slots were drawn: kept, and applied once they are.
            s.pendingScan = String(text).trim();
            const msgEl = s.handle && s.handle.element.querySelector('.fcc-sp-msg');
            if (msgEl) msgEl.textContent = `⏳ Loading ${s.location}… (${s.pendingScan} is picked once it has loaded)`;
            return true;
        }
        const ready = !!(s.model && s.model.read_ok !== false && s.tiles.length);
        if (ready) {
            let m = /^LOC:(.+?):SLOT:(\d+)$/.exec(up);
            if (m) {
                const box = m[1].trim();
                const slot = _normSlot(m[2]);
                const t = s.tiles.find((x) => (x.kind === 'slot' || x.kind === 'pool') && x.box === box && x.slot === slot);
                if (t) { _pick(s, t, 'scan'); return true; }
            }
            m = /^CMD:SLOT:(\d+)$/.exec(up);
            if (m && s.model.mode !== 'printer') {
                const t = s.tiles.find((x) => x.kind === 'slot' && x.slot === _normSlot(m[1]));
                if (t) { _pick(s, t, 'scan'); return true; }
            }
            if (s.model.mode === 'printer' && up.startsWith('LOC:') && !up.includes(':SLOT:')) {
                const t = s.tiles.find((x) => x.kind === 'head' && x.head === up.slice(4).trim());
                if (t) { _pick(s, t, 'scan'); return true; }
            }
        }
        _warn('Finish or cancel the slot picker first');
        _flash(s, `Finish or cancel the slot picker first. (Ignored: ${text})`);
        return true;
    };

    // After load: scripts.html loads this file BEFORE shortcuts_registry.js.
    const _registerShortcuts = () => {
        if (!window.registerShortcut) return;
        window.registerShortcut({ id: 'slot-picker-move', scope: 'Slot Picker', keys: ['←', '→', '↑', '↓'],
            description: 'Move between the slots (or toolheads); wraps at the ends.' });
        window.registerShortcut({ id: 'slot-picker-jump', scope: 'Slot Picker', keys: ['1–9'],
            description: 'Highlight that slot of the box (or the Nth toolhead / pool slot).' });
        window.registerShortcut({ id: 'slot-picker-pick', scope: 'Slot Picker', keys: ['Enter'],
            description: 'Pick the highlighted slot. Scanning a slot label (or the tile\'s QR) picks it too.' });
        window.registerShortcut({ id: 'slot-picker-cancel', scope: 'Slot Picker', keys: ['Esc'],
            description: 'Cancel the picker; nothing moves. CMD:CANCEL does the same.' });
        window.registerShortcut({ id: 'slot-picker-choice', scope: 'Slot Picker', keys: ['←', '→', 'Enter'],
            description: 'A slot that holds a spool asks what happens to it (Swap / Overwrite, or Swap it out): '
                + '←/→ choose, Enter confirms, Back returns to the slots. Each answer has a QR too.' });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _registerShortcuts);
    else _registerShortcuts();
})();
