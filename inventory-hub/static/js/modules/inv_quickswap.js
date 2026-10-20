// ---------------------------------------------------------------------------
// Quick-Swap UI (Phase 3)
//
// Rendered inside the Location Manager when the user opens a toolhead
// (Tool Head / MMU Slot / No MMU Direct Load). Aggregates every (box, slot)
// pair bound to the current toolhead across ALL Dryer Boxes, so split
// boxes (multiple boxes feeding one printer) show up side-by-side. Tapping
// or keyboard-activating a slot moves that spool into the toolhead via
// /api/quickswap, which reuses perform_smart_move under the hood.
// ---------------------------------------------------------------------------

(function () {
    // Toolhead types get the grid directly. Printer-type locations (e.g. the
    // "🦝 XL" virtual printer) also get it so binding edits / Quick-Swap work
    // from either view — the grid aggregates every toolhead that belongs to
    // that printer.
    const TOOLHEAD_TYPES = new Set(['Tool Head', 'MMU Slot', 'No MMU Direct Load']);
    const PRINTER_TYPE = 'Printer';

    // Group 42.5c — a single-slot box (a PolyDryer) is bound to a head because
    // its own spool is loaded there (the Group 20.2 lifecycle), not as a feed.
    // Derek's "is it attached?" (2026-09-12) is answered on its grid header:
    // "🔗 attached — follows #50" while that spool is on the head; a stale
    // attachment (its spool isn't there) says so and offers Unbind, since 42.1
    // never auto-releases a box another spool didn't take off the head.
    const _attachedLabel = (boxId, head, items) => {
        const follower = (items || []).find(it => it.is_ghost
            && String(it.deployed_to || '').replace(/"/g, '').trim().toUpperCase() === head);
        if (follower) {
            return ` <span class="fcc-qs-attached text-info" style="font-size:0.9rem;"
                         title="${boxId} follows its spool #${follower.id}, which is loaded on ${head}">🔗 attached — follows #${follower.id}</span>`;
        }
        return ` <span class="fcc-qs-attached text-warning" style="font-size:0.9rem;"
                       title="${boxId} is still attached to ${head}, but its spool isn't on ${head}">🔗 attached, but its spool isn't on ${head}</span>`
            + `<button type="button" class="fcc-qs-unbind btn btn-sm btn-outline-warning fw-bold ms-2"
                       data-box="${boxId}" data-toolhead="${head}"
                       onclick="window.quickSwapUnbindAttached(this)"
                       title="Detach ${boxId} from ${head}">🔗✖ Unbind</button>`;
    };
    // The same single-slot binding PUT the bind picker's Unbind uses. It names
    // the head this grid showed (Group 42 review): the grid repaints every 5-30 s,
    // and a box that has followed its spool onto another head meanwhile is
    // refused rather than detached from there.
    window.quickSwapUnbindAttached = (btn) => {
        const box = btn && btn.getAttribute('data-box');
        const head = btn && btn.getAttribute('data-toolhead');
        if (!box) return;
        fetch(`/api/dryer_box/${encodeURIComponent(box)}/bindings/1`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: null, expected_target: head }),
        })
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (ok) {
                    showToast(`🔗✖ ${box} detached from ${head}`, 'success', 4000);
                } else {
                    const errs = (body.errors || []).map(e => `${e.slot}: ${e.reason}`).join('; ');
                    showToast(`❌ ${body.msg || errs || body.error || 'Unbind failed'}`, 'error', 7000);
                }
                // Either way the grid repaints, so it never keeps offering a stale Unbind.
                if (window.renderQuickSwapSection && currentLoc) window.renderQuickSwapSection(currentLoc);
            })
            .catch(() => showToast('Unbind — network error', 'error', 7000));
    };

    const resolvePrinterNameForToolhead = (toolheadId, printerMap) => {
        // printerMap shape: { "🦝 XL": [{location_id, position}, ...], ... }
        const up = String(toolheadId || '').toUpperCase();
        for (const [printerName, entries] of Object.entries(printerMap || {})) {
            if (entries.some(e => String(e.location_id).toUpperCase() === up)) {
                return printerName;
            }
        }
        return null;
    };

    // L271: the Printer row, not the spelling of its id, says which toolheads
    // belong to it. A head can share the printer's own id: the Core One's row is
    // CORE1 with the single head CORE1, so the old "<ID>-" prefix match found
    // nothing there and Return on CORE1 never reached the server (2026-09-13).
    // Lookup order:
    //   1. the row's toolheads[] (on the object passed in, else its
    //      state.allLocations row) — the data /api/printer_map is built from;
    //   2. the printer_map group named after the row (the map is keyed by Name);
    //   3. the legacy "<ID>-" prefix, only when neither knows the row (kept
    //      until L271 Phase 5 retires prefix matching).
    // Returns uppercased toolhead ids in position order, without duplicates.
    const printerToolheadIds = (loc, printerMap) => {
        if (!loc) return [];
        const up = String(loc.LocationID || '').trim().toUpperCase();
        const inPositionOrder = (list) => {
            const pos = (e) => (Number.isFinite(Number(e.position)) ? Number(e.position) : Number.MAX_SAFE_INTEGER);
            const ids = (Array.isArray(list) ? list : [])
                .filter(e => e && String(e.location_id || '').trim())
                .map((e, i) => ({ id: String(e.location_id).trim().toUpperCase(), p: pos(e), i }))
                .sort((a, b) => (a.p - b.p) || (a.i - b.i))
                .map(e => e.id);
            return ids.filter((id, i) => ids.indexOf(id) === i);
        };
        const row = Array.isArray(loc.toolheads) ? loc
            : (state.allLocations || []).find(l => String(l.LocationID || '').trim().toUpperCase() === up);
        const fromRow = inPositionOrder(row && row.toolheads);
        if (fromRow.length) return fromRow;
        const fromGroup = inPositionOrder((printerMap || {})[loc.Name]);
        if (fromGroup.length) return fromGroup;
        const prefix = up + '-';
        const legacy = [];
        for (const entries of Object.values(printerMap || {})) {
            (entries || []).forEach(e => {
                const v = String(e.location_id).toUpperCase();
                if (v.startsWith(prefix) && !legacy.includes(v)) legacy.push(v);
            });
        }
        return legacy;
    };

    const resolvePrinterNameForPrinterLoc = (loc, printerMap) => {
        // The printer_map group that owns this Printer row's toolheads
        // (printerToolheadIds: toolheads[] first, the legacy prefix last).
        const heads = printerToolheadIds(loc, printerMap);
        for (const [printerName, entries] of Object.entries(printerMap || {})) {
            if ((entries || []).some(e => heads.includes(String(e.location_id).toUpperCase()))) {
                return printerName;
            }
        }
        // Fallback: loose name match.
        const candidates = [loc.Name, loc.LocationID, loc['Device Type'], loc['Device Identifier']]
            .filter(Boolean).map(s => String(s).trim());
        for (const printerName of Object.keys(printerMap || {})) {
            if (candidates.some(c => c && (printerName.includes(c) || c.includes(printerName)))) {
                return printerName;
            }
        }
        return null;
    };

    const clearKbActive = (root) => {
        root.querySelectorAll('.fcc-qs-slot.kb-active').forEach(el => el.classList.remove('kb-active'));
    };

    const focusSlot = (btn) => {
        if (!btn) return;
        const grid = document.getElementById('quickswap-grid');
        if (grid) clearKbActive(grid);
        btn.classList.add('kb-active');
        btn.focus({ preventScroll: true });
    };

    // Track the currently-viewed location so bindings edit / return-to-slot
    // know what to act on.
    let currentLoc = null;
    // Last grid HTML committed, so the heartbeat-driven silent refresh (L352)
    // can skip the DOM swap — and the flicker / focus loss — when nothing
    // actually changed since the previous tick.
    let _lastQsHtml = null;

    const renderQuickSwapSection = (loc, opts = {}) => {
        const silent = !!(opts && opts.silent);
        const section = document.getElementById('manage-quickswap-section');
        if (!section) return;

        const isToolhead = TOOLHEAD_TYPES.has(loc.Type);
        const isPrinter = loc.Type === PRINTER_TYPE;

        if (!isToolhead && !isPrinter) {
            section.style.display = 'none';
            currentLoc = null;
            return;
        }
        currentLoc = loc;
        section.style.display = 'block';

        // Need the printer_map (cached in state.printerMap by inv_loc_mgr.fetchPrinterMap).
        const ensurePM = state.printerMap
            ? Promise.resolve(state.printerMap)
            : fetch('/api/printer_map').then(r => r.json()).then(d => {
                state.printerMap = d.printers || {};
                return state.printerMap;
            });

        ensurePM.then(printerMap => {
            const printerName = isPrinter
                ? resolvePrinterNameForPrinterLoc(loc, printerMap)
                : resolvePrinterNameForToolhead(loc.LocationID, printerMap);
            const grid = document.getElementById('quickswap-grid');
            const empty = document.getElementById('quickswap-empty');
            // Silent (heartbeat) refreshes must NOT blank the grid up-front —
            // that's the flicker + focus-loss. They commit only the final HTML,
            // and only if it changed (see the content-hash guard below).
            if (!silent) grid.innerHTML = '';
            if (!printerName) {
                empty.style.display = 'block';
                empty.innerHTML = '⚠️ This location is not registered in ' +
                    '<span class="text-info fw-bold">printer_map</span>. ' +
                    'Add an entry for its toolhead LocationID(s) in ' +
                    '<span class="text-info fw-bold">config.json</span> to enable Quick-Swap.';
                return;
            }

            fetch(`/api/machine/${encodeURIComponent(printerName)}/toolhead_slots`)
                .then(r => r.ok ? r.json() : { toolheads: {} })
                .then(body => {
                    const toolheadMap = body.toolheads || {};
                    const currentUp = String(loc.LocationID).toUpperCase();

                    let entries = [];
                    if (isToolhead) {
                        entries = toolheadMap[currentUp] || [];
                    } else {
                        Object.keys(toolheadMap).forEach(thId => {
                            (toolheadMap[thId] || []).forEach(e => {
                                entries.push({ ...e, toolhead: thId });
                            });
                        });
                    }

                    // Printer Pool: dryer-box slots bound to PRINTER:<id>
                    // sentinel that affiliates with this printer. Surfaced
                    // separately so users can deposit from the toolhead view
                    // even when the destination slot isn't toolhead-bound.
                    const printerPool = body.printer_pool || [];

                    if (!entries.length && !printerPool.length) {
                        empty.style.display = 'block';
                        // Silent path skipped the up-front clear; if the view
                        // just transitioned to empty, clear the stale grid once.
                        if (silent && grid.innerHTML !== '') { grid.innerHTML = ''; _lastQsHtml = ''; }
                        return;
                    }
                    empty.style.display = 'none';

                    // Fetch live contents for each unique source box so the
                    // button can show WHAT spool is currently sitting in that
                    // slot. Without this, tapping "Slot 4" is a leap of faith.
                    const uniqueBoxes = [...new Set([
                        ...entries.map(e => e.box),
                        ...printerPool.map(p => p.box),
                    ])];
                    // Group 42.2/42.5c: a single-slot box (flagged by the
                    // server) has one place, so its lone spool is in slot 1
                    // even when its slot was stored blank; a box FCC thinks
                    // holds two stays unsorted (Claude's call 20).
                    const singleBoxes = new Set(entries.filter(e => e.single_slot).map(e => e.box));
                    // Group 42 review: a single-slot box is read strictly. Its
                    // header offers Unbind when its spool isn't on the head, and
                    // a Spoolman blip (the plain read answers []) looked just like
                    // that, so Unbind detached a box whose spool was loaded.
                    // Group 52.1c: ONE contents request for every box (it was one
                    // per box, each a whole spool-list read, again on every
                    // heartbeat while the view is open). That one read is strict
                    // for all of them: when Spoolman doesn't answer, no box is
                    // drawn empty. A single-slot box keeps its "couldn't read"
                    // header; every other slot says it couldn't be read.
                    const unreadable = new Set();
                    const idsQuery = uniqueBoxes.map(b => encodeURIComponent(b)).join('&ids=');
                    fetch(`/api/get_contents?ids=${idsQuery}`)
                        .then(r => (r.ok ? r.json() : null))
                        .catch(() => null)
                        .then(body => {
                            const readOk = !!(body && body.read_ok === true
                                && body.contents && typeof body.contents === 'object');
                            // A heartbeat refresh that couldn't read keeps the
                            // tiles it drew last instead of flipping them all.
                            if (!readOk && silent && _lastQsHtml) return null;
                            if (!readOk) uniqueBoxes.forEach(b => unreadable.add(b));
                            return uniqueBoxes.map(b => [b, readOk ? (body.contents[b] || []) : []]);
                        })
                    .then(boxContents => {
                        if (!boxContents) return;
                        const slotMap = {};
                        // Every item claiming a slot (Group 42 review): two claims
                        // showed the last card while /api/quickswap moved the first.
                        const slotClaims = {};
                        const itemsByBox = {};
                        boxContents.forEach(([b, items]) => {
                            const list = items || [];
                            itemsByBox[b] = list;
                            list.forEach(it => {
                                let slotStr = String(it.slot || '').replace(/"/g, '').trim();
                                if (slotStr === 'None' || slotStr === 'null') slotStr = '';
                                if (!slotStr && singleBoxes.has(b) && list.length === 1) slotStr = '1';
                                if (slotStr) {
                                    slotMap[`${b}|${slotStr}`] = it;
                                    (slotClaims[`${b}|${slotStr}`] = slotClaims[`${b}|${slotStr}`] || []).push(it);
                                }
                            });
                        });

                        const byBox = {};
                        entries.forEach(e => {
                            if (!byBox[e.box]) byBox[e.box] = [];
                            byBox[e.box].push(e);
                        });
                        // State of the user's scan buffer determines whether
                        // empty slots are interactive (deposit target) or
                        // inert (nothing to do).
                        const bufferTopSpool = (state.heldSpools && state.heldSpools[0]) || null;

                        let html = '';
                        Object.keys(byBox).sort().forEach(boxId => {
                            // Clickable box header so users can jump straight
                            // into the source box without hunting for it in
                            // the Locations list. closeManage's breadcrumb
                            // returns them here on X-close.
                            html += `<div class="w-100 fw-bold mt-3 mb-1" style="font-size:1.1rem;">` +
                                    `📦 <a href="#" onclick="event.preventDefault(); window.openManage('${boxId}');"
                                        class="text-info"
                                        style="text-decoration: underline dotted;"
                                        title="Open ${boxId} — Close returns here">${boxId}</a>` +
                                    (singleBoxes.has(boxId)
                                        ? (unreadable.has(boxId)
                                            ? ` <span class="fcc-qs-attached text-warning" style="font-size:0.9rem;"
                                                     title="FCC couldn't read ${boxId} from Spoolman just now, so it can't tell whether its spool is on the head">⚠️ couldn't read ${boxId} from Spoolman</span>`
                                            : _attachedLabel(boxId, String(byBox[boxId][0].toolhead || loc.LocationID).toUpperCase(),
                                                itemsByBox[boxId]))
                                        : '') +
                                    `</div>`;
                            byBox[boxId].sort((a, b) => Number(a.slot) - Number(b.slot)).forEach(e => {
                                const th = e.toolhead || loc.LocationID;
                                const claims = slotClaims[`${e.box}|${e.slot}`] || [];
                                const item = claims.length === 1 ? claims[0] : null;
                                const thLine = isPrinter
                                    ? `<div class="text-warning small" style="font-size:0.85rem;">→ ${th}</div>`
                                    : '';
                                let contentLines, borderCls, handler, titleAttr, disabledAttr;
                                let singleAttr = '';
                                if (claims.length > 1) {
                                    // Two spools claim one slot: no card to tap, since
                                    // either one could be the spool that gets loaded.
                                    const who = claims.map(c => `#${c.id}`);
                                    const whoTxt = who.length > 2
                                        ? `${who.slice(0, -1).join(', ')} and ${who[who.length - 1]}` : who.join(' and ');
                                    contentLines = `<div class="text-warning fw-bold" style="font-size:0.9rem; white-space:normal; max-width:240px;">⚠️ ${whoTxt} ${who.length > 2 ? 'all' : 'both'} claim slot ${e.slot} — open ${e.box} to sort them</div>`;
                                    borderCls = 'btn-outline-warning';
                                    handler = 'window.quickSwapTap(this)';
                                    titleAttr = `FCC's records put ${whoTxt} in ${e.box} slot ${e.slot}; move one of them, then swap`;
                                    singleAttr = `data-why="${titleAttr}"`;
                                    disabledAttr = 'disabled';
                                } else if (unreadable.has(e.box)) {
                                    contentLines = `<div class="text-warning fw-bold" style="font-size:0.9rem;">⚠️ couldn't read ${e.box}</div>`;
                                    borderCls = 'btn-outline-warning';
                                    handler = 'window.quickSwapTap(this)';
                                    titleAttr = `FCC couldn't read ${e.box} from Spoolman just now — reopen the view to try again`;
                                    singleAttr = `data-why="${titleAttr}"`;
                                    disabledAttr = 'disabled';
                                } else if (item) {
                                    // Slot has a spool — render via SpoolCardBuilder's
                                    // 'quickswap' variant so the user sees a real
                                    // filament card (color, brand, name, weight,
                                    // action footer) instead of a bare button.
                                    // The card returns its own HTML; skip the
                                    // shared button wrapper below by appending
                                    // here and continuing the loop.
                                    const titleText = `Load ${item.display || `#${item.id}`} from ${e.box} slot ${e.slot} into ${th}`;
                                    html += window.SpoolCardBuilder.buildCard(item, 'quickswap', {
                                        box: e.box,
                                        slot: e.slot,
                                        toolhead: th,
                                        showToolhead: isPrinter,
                                        handler: 'window.quickSwapTap(this)',
                                        titleAttr: titleText,
                                    });
                                    return;  // forEach callback — skip the button wrapper
                                } else if (bufferTopSpool) {
                                    // Empty slot + buffered spool — tap DEPOSITS
                                    // the buffered spool into the slot. Reuses
                                    // the scan-flow backend so auto-deploy to
                                    // the bound toolhead kicks in too.
                                    const bsDisplay = String(bufferTopSpool.display || `#${bufferTopSpool.id}`).replace(/"/g, '&quot;');
                                    const bsSwatch = window.makeSwatchHtml(bufferTopSpool.color, bufferTopSpool.color_direction, { size: 14, marginRight: 6 });
                                    contentLines = `
                                        <div class="text-success fw-bold" style="font-size:0.9rem;">⬇️ Deposit from buffer:</div>
                                        <div class="text-light" style="font-size:0.9rem; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                            ${bsSwatch}${bsDisplay}
                                        </div>`;
                                    borderCls = 'btn-outline-success';
                                    handler = 'window.quickSwapDeposit(this)';
                                    // A single-slot box is attached to the head for
                                    // its own spool, not as a feed: since 42.2 nothing
                                    // put in it is loaded onto the head (Group 42 review).
                                    if (e.single_slot) {
                                        singleAttr = 'data-single-slot="1"';
                                        titleAttr = `Put the buffered spool in ${e.box} (it is not loaded onto ${th})`;
                                    } else {
                                        titleAttr = `Drop the buffered spool into ${e.box} slot ${e.slot} (auto-deploys to ${th})`;
                                    }
                                    disabledAttr = '';
                                } else {
                                    // Empty slot + empty buffer — nothing to do.
                                    contentLines = `<div class="text-muted small fw-bold" style="font-size:0.9rem;">◦ empty slot</div>`;
                                    borderCls = 'btn-outline-secondary';
                                    handler = 'window.quickSwapTap(this)';
                                    titleAttr = `${e.box} slot ${e.slot} is empty — scan a spool into the buffer to deposit here`;
                                    disabledAttr = 'disabled';
                                }
                                html += `
                                    <button type="button" class="fcc-qs-slot btn ${borderCls} fw-bold d-flex flex-column align-items-start"
                                        data-box="${e.box}" data-slot="${e.slot}"
                                        data-toolhead="${th}" ${singleAttr}
                                        style="min-width:240px; font-size:1.05rem; padding:10px 14px;"
                                        onclick="${handler}"
                                        ${disabledAttr}
                                        title="${titleAttr}">
                                        <div class="text-warning fw-bold" style="font-size:1rem;">Slot ${e.slot}</div>
                                        ${contentLines}
                                        ${thLine}
                                    </button>`;
                            });
                        });

                        // Printer Pool section — staging slots bound to the
                        // PRINTER:<id> sentinel for this printer. Visually
                        // distinct from toolhead rows (yellow/amber theming
                        // vs. cyan) so users immediately see "this is a
                        // staging slot, not a feed."
                        if (printerPool.length) {
                            html += `<div class="w-100 mt-4 mb-1 fw-bold" style="font-size:1.1rem; border-top: 1px solid rgba(255,193,7,0.4); padding-top: 0.75rem;">` +
                                    `<span class="text-warning">🏭 Printer Pool</span>` +
                                    `<span class="text-light small ms-2" style="font-size:0.85rem; opacity:0.8;">staging / drying — not bound to a toolhead</span>` +
                                    `</div>`;
                            printerPool
                                .slice()
                                .sort((a, b) => (a.box + a.slot).localeCompare(b.box + b.slot))
                                .forEach(p => {
                                    const item = slotMap[`${p.box}|${p.slot}`];
                                    if (unreadable.has(p.box)) {
                                        // Group 52.1c: Spoolman didn't answer, so
                                        // FCC can't tell this slot is empty.
                                        html += `
                                            <button type="button" class="fcc-qs-slot fcc-qs-pool btn btn-outline-warning fw-bold d-flex flex-column align-items-start"
                                                data-box="${p.box}" data-slot="${p.slot}"
                                                data-toolhead=""
                                                data-pool="1"
                                                style="min-width:240px; font-size:1.05rem; padding:10px 14px;"
                                                disabled
                                                title="FCC couldn't read ${p.box} from Spoolman just now — reopen the view to try again">
                                                <div class="text-warning fw-bold" style="font-size:1rem;">Slot ${p.slot}</div>
                                                <div class="text-warning fw-bold" style="font-size:0.9rem;">⚠️ couldn't read ${p.box}</div>
                                            </button>`;
                                    } else if (item) {
                                        // Filled pool slot — show the spool
                                        // card. Tap opens the spool's details
                                        // (no toolhead to swap into).
                                        const titleText = `${item.display || `#${item.id}`} in ${p.box} slot ${p.slot} — printer pool (no toolhead bound)`;
                                        html += window.SpoolCardBuilder.buildCard(item, 'quickswap', {
                                            box: p.box,
                                            slot: p.slot,
                                            toolhead: '',
                                            showToolhead: false,
                                            handler: `event.stopPropagation(); openSpoolDetails(${item.id})`,
                                            titleAttr: titleText,
                                        });
                                    } else if (bufferTopSpool) {
                                        // Empty pool slot + buffered spool — deposit.
                                        const bsDisplay = String(bufferTopSpool.display || `#${bufferTopSpool.id}`).replace(/"/g, '&quot;');
                                        const bsSwatch = window.makeSwatchHtml(bufferTopSpool.color, bufferTopSpool.color_direction, { size: 14, marginRight: 6 });
                                        html += `
                                            <button type="button" class="fcc-qs-slot fcc-qs-pool btn btn-outline-success fw-bold d-flex flex-column align-items-start"
                                                data-box="${p.box}" data-slot="${p.slot}"
                                                data-toolhead=""
                                                data-pool="1"
                                                style="min-width:240px; font-size:1.05rem; padding:10px 14px;"
                                                onclick="window.quickSwapDeposit(this)"
                                                title="Drop the buffered spool into ${p.box} slot ${p.slot} (printer pool — no toolhead auto-deploy)">
                                                <div class="text-warning fw-bold" style="font-size:1rem;">Slot ${p.slot} <span class="text-secondary small ms-1" style="font-size:0.75rem;">${p.box}</span></div>
                                                <div class="text-success fw-bold" style="font-size:0.9rem;">⬇️ Deposit from buffer:</div>
                                                <div class="text-light" style="font-size:0.9rem; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                                    ${bsSwatch}${bsDisplay}
                                                </div>
                                            </button>`;
                                    } else {
                                        // Empty pool slot + empty buffer — inert.
                                        html += `
                                            <button type="button" class="fcc-qs-slot fcc-qs-pool btn btn-outline-warning fw-bold d-flex flex-column align-items-start"
                                                data-box="${p.box}" data-slot="${p.slot}"
                                                data-toolhead=""
                                                data-pool="1"
                                                style="min-width:240px; font-size:1.05rem; padding:10px 14px; opacity:0.7;"
                                                disabled
                                                title="${p.box} slot ${p.slot} is empty — scan a spool into the buffer to deposit here">
                                                <div class="text-warning fw-bold" style="font-size:1rem;">Slot ${p.slot} <span class="text-secondary small ms-1" style="font-size:0.75rem;">${p.box}</span></div>
                                                <div class="text-muted small fw-bold" style="font-size:0.9rem;">◦ empty staging slot</div>
                                            </button>`;
                                    }
                                });
                        }

                        // Non-silent always commits (preserves the open path).
                        // Silent commits only when the content actually changed,
                        // so an unchanged heartbeat tick is a no-op (no flicker).
                        if (!silent || html !== _lastQsHtml) grid.innerHTML = html;
                        _lastQsHtml = html;
                    });
                });
        });
    };

    // Keeps a reference to the current overlay's teardown so external
    // callers (e.g. the manage modal's hidden.bs.modal handler) can
    // dismiss it cleanly — including removing the keydown listener —
    // instead of just hiding the element and leaking the listener.
    let _activeConfirmClose = null;
    // Group 39 review (frontend-14): bumped by every showConfirmOverlay call, so
    // only the LATEST mounts. Two taps during the probe (up to 3 s) both passed
    // the _activeConfirmClose check and mounted two overlays; the remount dropped
    // the first one's DOM but not its document keydown handler, which then ate
    // every Tab on the page until a reload.
    let _overlayGen = 0;
    // Group 40.3 review (B2): one deposit at a time. When the tap was taken
    // (Date.now()), 0 when idle. The deposit probes the printer and reads the
    // head first (up to ~6 s), and a second tap meanwhile posted a second
    // deposit: two dialogs, and the unanswered one later said "Cancelled —
    // nothing moved" after a move that landed. Cleared when a dialog takes over
    // or the deposit ends; a flag older than 20 s no longer blocks a tap.
    let _depositBusyAt = 0;

    // Helper: race the printer-state probe against a short timeout so a slow
    // or unreachable PrusaLink can't stall the confirm UI. Returns stateInfo
    // (truthy → active) or null (unknown → no banner).
    //
    // Timeout is 3s by default — earlier 1s was too tight; some networks take
    // longer to round-trip through backend → filabridge credential lookup →
    // PrusaLink. Backend itself has a 2s per-endpoint timeout inside
    // `get_printer_state`, so 3s gives headroom plus network overhead.
    // Group 39.3: the detailed answer ({active, known, reason, ...}, or null with
    // no head), through the shared printer check: the "⏳ Checking XL…" pill and
    // the same timeout race every client probe gets.
    const _probeWithTimeout = (toolheadId, timeoutMs = 3000) => {
        const dbg = (...args) => { if (window.FCC_DEBUG_ACTIVE_PRINT) console.log('[active-print overlay]', ...args); };
        if (!toolheadId) { dbg('no toolhead id, skipping probe'); return Promise.resolve(null); }
        if (!window.checkPrinterForHead) { dbg('helper missing — stale cached JS?'); return Promise.resolve(null); }
        dbg('probing', toolheadId, 'with timeout', timeoutMs + 'ms');
        return window.checkPrinterForHead(toolheadId, { timeoutMs }).catch((e) => { dbg('probe error', e); return null; });
    };

    const _escapeHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

    const showConfirmOverlay = async (opts) => {
        // If there's a previous overlay still active, tear it down before
        // replacing its handlers. mountOverlay would also dedupe by id, but
        // we need to run qrSession cleanup attached to the prior close.
        if (_activeConfirmClose) {
            try { _activeConfirmClose(); } catch (e) { /* noop */ }
        }

        // Active-print probe must complete BEFORE the overlay becomes visible —
        // otherwise a fast-clicking user can confirm before the banner lands
        // (the async-append pattern we tried first lost that race). The 3 s cap
        // (_probeWithTimeout's default) keeps the delay bounded when the printer
        // is offline. The probe
        // fails open — null means "unknown, show overlay normally."
        // opts.knownState: the backend has just said the printer is active, so
        // show that banner without re-probing (the probe is what missed it).
        // opts.probed (Group 40.3): the caller already probed this head (the
        // deposit decides first whether to show this overlay at all).
        const gen = ++_overlayGen;
        const detail = opts.knownState ? null
            : (opts.probed !== undefined ? opts.probed : await _probeWithTimeout(opts.toolhead));
        if (gen !== _overlayGen) return;   // a later tap owns the overlay now
        const stateInfo = opts.knownState || (detail && detail.active
            ? { state: detail.state || 'ACTIVE', printer_name: detail.printer_name || opts.toolhead }
            : null);
        const warningBanner = stateInfo
            ? `<div class="alert alert-warning py-2 px-3 mb-2" style="font-size:0.95em;">`
                + `⚠️ <b>${_escapeHtml(stateInfo.printer_name)} is ${_escapeHtml(stateInfo.state)}</b> — loading a new spool now will disrupt the print.`
                + `</div>`
            : '';
        // Group 39.3: when FCC couldn't ask the printer (no login, unreachable, a
        // timeout), say so in one line instead of looking like an idle printer.
        const note = (!stateInfo && window.printerCheckNote) ? window.printerCheckNote(detail, opts.toolhead) : '';
        const noteHtml = note
            ? `<div class="fcc-printer-note text-info mb-2" style="font-size:0.95em;">${_escapeHtml(note)}</div>`
            : '';

        const titleText = opts.title || `Swap ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`;
        const defaultBody = 'This moves the spool currently in that slot into the active toolhead. ' +
                            'Any spool already on the toolhead will be auto-ejected back to its source.';
        const bodyHtml = warningBanner + noteHtml + (opts.body || defaultBody);

        const panelHtml = `
            <div class="bg-dark border border-info rounded p-4 shadow-lg"
                 style="min-width:420px; max-width:540px;">
                <div class="text-info fw-bold mb-3" style="font-size:1.25rem;"
                     id="fcc-quickswap-confirm-title">${_escapeHtml(titleText)}</div>
                <div class="text-light mb-3" style="font-size:1.05rem;"
                     id="fcc-quickswap-confirm-body">${bodyHtml}</div>
                <!-- Buttons mirror the QR row's flex layout exactly (gap:14px;
                     justify-content:center; from attachConfirmQRs in
                     inv_core.js). The CONFIRM QR's "📷 SCAN TO CONFIRM"
                     label is ~10px wider than CANCEL's, making the QR
                     columns asymmetric. Measured widths: CONFIRM ≈ 133px,
                     CANCEL ≈ 123px. We mirror those exactly so each
                     button center lands under its QR center. -->
                <div style="display:flex; gap:14px; justify-content:center; margin-top:14px;">
                    <div style="width:133px; display:flex; justify-content:center;">
                        <button type="button" id="fcc-quickswap-yes"
                            class="btn btn-info fw-bold w-100">Yes, swap</button>
                    </div>
                    <div style="width:123px; display:flex; justify-content:center;">
                        <button type="button" id="fcc-quickswap-no"
                            class="btn btn-outline-light fw-bold w-100">No, cancel</button>
                    </div>
                </div>
            </div>
        `;

        let qrSession = null;
        const close = () => {
            document.removeEventListener('keydown', keyHandler, true);
            if (qrSession) { try { qrSession.cleanup(); } catch (_) { /* noop */ } qrSession = null; }
            try { handle.cleanup(); } catch (_) { /* noop */ }
            if (_activeConfirmClose === close) _activeConfirmClose = null;
        };
        // ONE confirm path for Enter, the Yes button and the QR. onConfirm gets
        // the probe result, so a caller can tell the backend the user confirmed
        // an active-print warning (null = no banner was shown). Enter used to
        // call onConfirm() bare, so a keyboard deposit during a print never
        // carried the confirm (2026-09-12 review).
        const doConfirm = () => { opts.onConfirm && opts.onConfirm(stateInfo); close(); };

        // Keyboard contract:
        //   - Escape cancels (owned by mountOverlay's onEscape).
        //   - Enter activates whichever button is focused (yes → confirm+close,
        //     no → close only). Yes is focused by default.
        //   - Tab cycles between the two buttons; focus trap prevents escape
        //     to the page behind (otherwise Tab leaks to the Location
        //     Manager modal behind and eventually the browser chrome).
        const keyHandler = (e) => {
            if (e.key === 'Enter') {
                // ⚠️ SAFETY (axis-(a) audit, 2026-08-03): a scan in flight OWNS
                // this Enter — it is the scan TERMINATOR, not a button press.
                // This overlay renders a "📷 Scan to Cancel" QR while mountOverlay
                // focuses YES (and its focus guard KEEPS it there), so without
                // this check the CANCEL scan's own Enter matched `active === yes`
                // and performed the CONFIRM — yanking a spool off a live toolhead,
                // the exact outcome this dialog exists to prevent. The
                // stopPropagation below then also suppressed the accumulator, so
                // routeConfirmScan never ran at all.
                // Bail out and let it bubble so the CMD:CONFIRM / CMD:CANCEL
                // payload routes properly. Keyboard use is unaffected: pressing
                // Enter by hand leaves scanBuffer empty.
                if (window.isScanInFlight && window.isScanInFlight()) return;
                const active = document.activeElement;
                if (active === yes) {
                    e.preventDefault(); e.stopPropagation();
                    doConfirm();
                } else if (active === no) {
                    e.preventDefault(); e.stopPropagation();
                    close();
                }
                return;
            }
            if (e.key === 'Tab') {
                const focusables = [yes, no].filter(Boolean);
                if (focusables.length === 0) return;
                const active = document.activeElement;
                const idx = focusables.indexOf(active);
                if (idx === -1) {
                    e.preventDefault(); e.stopPropagation();
                    focusables[e.shiftKey ? focusables.length - 1 : 0].focus();
                    return;
                }
                if (e.shiftKey && idx === 0) {
                    e.preventDefault(); e.stopPropagation();
                    focusables[focusables.length - 1].focus();
                } else if (!e.shiftKey && idx === focusables.length - 1) {
                    e.preventDefault(); e.stopPropagation();
                    focusables[0].focus();
                }
            }
        };

        const handle = window.mountOverlay({
            id: 'fcc-quickswap-confirm-overlay',
            content: panelHtml,
            tier: 'confirm',  // sits above the Location Manager modal
            focusGuard: true,
            initialFocus: '#fcc-quickswap-yes',
            onEscape: close,
        });
        const ov = handle.element;
        const yes = ov.querySelector('#fcc-quickswap-yes');
        const no = ov.querySelector('#fcc-quickswap-no');
        const body = ov.querySelector('#fcc-quickswap-confirm-body');

        // Mount QR-confirm pair only when the active-print warning is
        // showing — Quick-Swap during a normal move doesn't need scan
        // confirmation since the user already had a card to scan to
        // initiate the swap. The active-print case is the safety-critical
        // one that benefits from "scan to confirm I really meant to
        // disrupt my print."
        if (stateInfo && warningBanner && window.attachConfirmQRs) {
            qrSession = window.attachConfirmQRs({
                host: body,
                onConfirm: doConfirm,
                onCancel: () => { close(); },
                theme: 'warning',
            });
        }

        yes.onclick = doConfirm;
        no.onclick = close;
        document.addEventListener('keydown', keyHandler, true);
        _activeConfirmClose = close;
    };

    // Public teardown for the manage modal to call on hide.
    window.closeQuickswapConfirm = () => {
        if (_activeConfirmClose) {
            try { _activeConfirmClose(); } catch (e) { /* noop */ }
        } else if (window.closeOverlay) {
            window.closeOverlay('fcc-quickswap-confirm-overlay');
        }
    };

    // Re-render every moving part of the manage modal after a move so the
    // user sees the new state without closing+reopening. Spoolman writes
    // can lag a few hundred ms after perform_smart_move returns, so we
    // also fire a delayed second refresh to catch the settled state.
    //
    // refreshManageView has a content-hash cache for anti-wiggle polling;
    // we bust it explicitly here because we *know* the contents changed.
    const _refreshAfterMove = () => {
        if (!currentLoc) return;
        const id = currentLoc.LocationID;
        const doRefresh = () => {
            try { if (typeof state !== 'undefined') state.lastLocRenderHash = null; } catch (e) { /* noop */ }
            if (window.refreshManageView) window.refreshManageView(id);
            if (window.renderQuickSwapSection && currentLoc) {
                window.renderQuickSwapSection(currentLoc);
            }
            document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
        };
        doRefresh();
        setTimeout(doRefresh, 450);
    };

    // Group 39.1/39.2 — the heads a Quick-Swap/Return/Deposit Yes confirms: the
    // probed head when the overlay showed its banner, plus any the server named
    // before (always the union; see unionConfirmHeads in inv_core.js).
    const _headsShown = (prior, stateInfo, head) => {
        const out = new Set((prior || []).map(h => String(h).toUpperCase()));
        if (stateInfo && head) out.add(String(head).toUpperCase());
        return [...out];
    };

    // The server re-checked and a printing head needs a confirm the overlay's
    // own probe missed (it fails open on a timeout): log it, re-open the confirm
    // with the server's answer as the banner, and replay with every head
    // confirmed so far.
    const _reaskFromServer = (body, sent, overlayOpts, replay) => {
        if (window.logClientEvent) window.logClientEvent(
            `⚠️ ${overlayOpts.title.replace(/\?$/, '')} needs an active-print confirm: ${body.msg || 'the printer is printing'}`,
            'WARNING');
        const heads = window.unionConfirmHeads(sent, body);
        showConfirmOverlay({
            ...overlayOpts,
            knownState: body.active_print || { printer_name: overlayOpts.toolhead, state: 'PRINTING' },
            body: `<div class="text-light" style="font-size:1.05rem;">${_escapeHtml(body.msg || '')}</div>`,
            onConfirm: () => replay(heads),
        });
    };

    // Group 39.8 — read an answer that may not be JSON (a proxy's HTML error
    // page): `r.json()` threw, and the catch toasted "network error" for a
    // server that did answer. Now it reads "server answered 502".
    const _readAnswer = async (r) => {
        const text = await r.text();
        try {
            return { ok: r.ok, body: JSON.parse(text) };
        } catch (_) {
            return { ok: false, body: { action: 'http_error', error: `server answered ${r.status}` } };
        }
    };

    const performSwap = (opts, stateInfo = null, prior = []) => {
        const sent = _headsShown(prior, stateInfo, opts.toolhead);
        fetch('/api/quickswap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...opts, confirmed_toolheads: sent }),
        })
            .then(_readAnswer)
            .then(({ ok, body }) => {
                if (ok && body.action === 'quickswap_done') {
                    showToast(`⚡ Spool #${body.moved} → ${opts.toolhead}`, 'success', 2500);
                    _refreshAfterMove();
                } else if (body.action === 'quickswap_requires_confirm') {
                    _reaskFromServer(body, sent, {
                        ...opts, title: `Load ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`,
                    }, (heads) => performSwap(opts, null, heads));
                } else if (body.action === 'quickswap_empty_slot') {
                    showToast(`⚠️ ${opts.box} slot ${opts.slot} is empty — nothing to swap`, 'warning', 4000);
                } else if (body.action === 'quickswap_not_bound') {
                    showToast(`❌ Binding is stale — refresh and try again`, 'error', 7000);
                } else {
                    // Includes quickswap_failed: a rejected write, or a loaded
                    // spool Smart Load could not unload (body.error says which).
                    showToast(`❌ Quick-swap failed: ${body.error || body.action || 'unknown'}`, 'error', 7000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Quick-swap — network error', 'error', 7000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Quick-swap network error: ${e && e.message ? e.message : 'connection failed'}`,
                    'ERROR'
                );
            });
    };

    // Group 40.6 (item D): where a Return puts the spool, as its toast and the
    // confirm say it: "LR-MDB-1 slot 2", or "LR-MDB-1 (no slot)". It used to
    // read "LR-MDB-1:SLOT:null" when the spool landed unslotted.
    const _returnWhere = (box, slot) => {
        const s = String(slot == null ? '' : slot).trim();
        return (s && s !== 'none' && s !== 'null') ? `${box} slot ${s}` : `${box} (no slot)`;
    };

    // `opts`: {toolhead, box, slot (a number or 'none'), expected_spool}, the
    // slot the confirm named (Group 40.6). `ctx`: the Return flow it belongs to
    // (_startReturn), so a slot taken meanwhile is picked again.
    const performReturn = (opts, stateInfo = null, prior = [], ctx = null) => {
        // The Return overlay probes the head it empties (opts.toolhead).
        const sent = _headsShown(prior, stateInfo, opts.toolhead);
        if (ctx) ctx.heads = sent;
        fetch('/api/quickswap/return', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...opts, confirmed_toolheads: sent }),
        })
            .then(_readAnswer)
            .then(({ ok, body }) => {
                if (ok && body.action === 'return_done') {
                    showToast(`↩️ #${body.moved} → ${_returnWhere(body.box, body.slot)}`, 'success', 4000);
                    _refreshAfterReturn(ctx);
                } else if (body.action === 'return_requires_confirm') {
                    _reaskFromServer(body, sent, {
                        toolhead: opts.toolhead, title: `Return the spool on ${opts.toolhead}?`,
                    }, (heads) => performReturn(opts, null, heads, ctx));
                } else if (body.action === 'return_slot_taken' || body.action === 'return_choose_slot') {
                    // Nothing was written: the slot the confirm named was taken
                    // meanwhile (or the server can't tell which slot without the
                    // user). Pick again, on fresh slots.
                    if (body.action === 'return_slot_taken') {
                        showToast(`⚠️ ${body.error || `${opts.box} slot ${opts.slot} was taken meanwhile`} — pick another slot`,
                            'warning', 7000);
                        if (window.logClientEvent) window.logClientEvent(
                            `⚠️ Return of #${body.spool || opts.expected_spool} off ${opts.toolhead}: `
                            + `${body.error || 'its slot was taken meanwhile'} — asked again`, 'WARNING');
                    }
                    _pickReturnSlot(ctx || { th: opts.toolhead, vth: opts.toolhead, heads: sent },
                        { ...body, spool: body.spool || opts.expected_spool, active_toolhead: body.active_toolhead || opts.toolhead });
                } else if (body.action === 'return_spool_mismatch') {
                    showToast(`⚠️ ${body.error || `${opts.toolhead} holds another spool now — nothing moved`}`, 'warning', 7000);
                    if (window.logClientEvent) window.logClientEvent(`⚠️ Return refused: ${body.error || 'another spool is on the head now'}`, 'WARNING');
                    _refreshAfterReturn(ctx);
                } else if (body.action === 'return_no_spool') {
                    showToast(`⚠️ ${opts.toolhead} is empty — nothing to return`, 'warning', 4000);
                } else if (body.action === 'return_no_binding') {
                    showToast(body.msg ? `⚠️ ${body.msg}` : `⚠️ ${opts.toolhead} has no bound slot to return to`,
                        'warning', body.msg ? 7000 : 4000);
                } else {
                    // Includes return_failed (the box write was rejected) and
                    // return_ambiguous (two spools on the head; eject one first).
                    showToast(`❌ Return failed: ${body.error || body.action || 'unknown'}`, 'error', 7000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Return — network error', 'error', 7000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Return network error: ${e && e.message ? e.message : 'connection failed'}`,
                    'ERROR'
                );
            });
    };

    // Deposit the top buffered spool into an empty slot. Reuses the
    // LOC:BOX:SLOT:N scan path on the backend so everything that flow
    // already does — auto-deploy if the slot is bound, Activity Log
    // entry, Filabridge map_toolhead notification — runs exactly once
    // per deposit without duplication.
    window.quickSwapDeposit = (btn) => {
        if (!btn) return;
        if (_depositBusyAt && Date.now() - _depositBusyAt < 20000) {
            showToast('⏳ Still working on the last deposit — one moment', 'info', 2500);
            return;
        }
        // Group 46 review — the spool this deposit names is the one it writes,
        // captured once: a server re-ask replays it rather than re-reading the
        // (possibly rotated) buffer.
        const buffered = (state.heldSpools || [])[0];
        if (!buffered) {
            showToast('Buffer is empty — scan a spool first', 'warning', 3500);
            return;
        }
        // Busy from the tap until a dialog takes over or the deposit ends; the
        // tile dims meanwhile, so the wait shows.
        _depositBusyAt = Date.now();
        const tileOpacity = btn.style ? btn.style.opacity : '';
        if (btn.style) btn.style.opacity = '0.55';
        const idle = () => {
            _depositBusyAt = 0;
            if (btn.style) btn.style.opacity = tileOpacity;
        };
        const gen = ++_overlayGen;
        const box = btn.dataset.box;
        const slot = btn.dataset.slot;
        const toolhead = btn.dataset.toolhead;
        const bsDisplay = buffered.display || `#${buffered.id}`;
        const title = `Deposit ${bsDisplay} into ${box} slot ${slot}?`;
        // Group 42 review: nothing deposited into a single-slot box (attached to
        // the head for its own spool, not as a feed; 42.2) or a printer-pool slot
        // is loaded onto a head, so neither promises it, and neither probes a
        // head it never touches. The server still asks about a printing head the
        // buffered spool LEAVES (_reaskFromServer).
        const notLoaded = btn.dataset.singleSlot === '1' || btn.dataset.pool === '1' || !toolhead;
        // The deposit as first sent (Group 40.3): every replay of a server
        // question is rebuilt from it (window.buildMoveReplay).
        //   - `spool_id` (Group 46 review): deposit the spool this deposit NAMED.
        //     Without it the server took the first spool of its buffer replica,
        //     which can differ by the time Yes is pressed: the overlay waits up to
        //     3 s on the printer probe while the carousel stays clickable.
        //   - `confirmed_toolheads` (Group 39.1): the heads whose warning the user
        //     saw, never a bare flag a stale grid could carry onto another head.
        //   - `confirmed_fed_heads`: this page can show the "already running
        //     another spool" question.
        //   - `expected_feed`: what the tile showed the slot feeding (its head, or
        //     "" for a Printer Pool slot), so a slot re-pointed while the deposit
        //     was being decided is asked about again. A single-slot box's binding
        //     is its own spool's attachment, never a feed: it names none.
        const original = {
            text: `LOC:${box}:SLOT:${slot}`,
            source: 'quickswap_deposit',
            confirmed_toolheads: [],
            confirmed_fed_heads: [],
            spool_id: buffered.id,
        };
        if (btn.dataset.singleSlot !== '1') original.expected_feed = notLoaded ? '' : String(toolhead).toUpperCase();
        const postDeposit = (payload, prior) => {
            _depositBusyAt = Date.now();
            window.fetchT('/api/identify_scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
                .then(async r => ({ ok: r.ok, body: await r.json() }))
                .then(({ ok, body }) => {
                    // The answer is in: it ends the deposit, or its dialog takes over.
                    idle();
                    if (ok && (body.action === 'assignment_done' || body.action === 'assignment_partial')) {
                        const destNote = body.auto_deployed_to
                            ? ` → ${body.auto_deployed_to}`
                            : '';
                        // Name what the server says it moved, never just what was asked.
                        const movedLabel = (body.moved != null && String(body.moved) !== String(buffered.id))
                            ? `#${body.moved}` : bsDisplay;
                        if (body.not_deployed) {
                            // In the box, but the chain did not deploy it.
                            showToast(`⚠️ ${movedLabel} → ${box}:SLOT:${slot}, but NOT deployed to ${body.not_deployed_target || toolhead}: ${body.not_deployed}`, 'warning', 7000);
                        } else if (prior && prior.store) {
                            // Group 40.3: "Just store it" put it in the slot and left the head alone.
                            showToast(`📦 ${movedLabel} stored in ${box} slot ${slot}`
                                + `${window.storeToastTail(prior)}`, 'success', 4000);
                        } else {
                            showToast(`⬇️ ${movedLabel} → ${box}:SLOT:${slot}${destNote}`, 'success', 2500);
                        }
                        // Mirror backend's buffer mutation on the frontend
                        // so the user doesn't briefly see the old spool.
                        if (body.moved != null) {
                            state.heldSpools = (state.heldSpools || []).filter(s => s.id !== body.moved);
                        }
                        // Group 40, the same-slot swap: the slot's old spool came
                        // off the head into the scan buffer. One render, one save.
                        const handedBack = window.takeIntoBuffer(body, { render: false });
                        if ((body.moved != null || handedBack.length) && window.renderBuffer) window.renderBuffer();
                        _refreshAfterMove();
                    } else if (body.action === 'assignment_no_buffer') {
                        showToast('Buffer is empty — scan a spool first', 'warning', 3500);
                    } else if (body.action === 'assignment_requires_confirm') {
                        // Group 40.3, Derek (2026-10-14): one dialog. The slot's
                        // head runs a spool from elsewhere, or its printer prints
                        // and the deposit could just store: the server's three-way
                        // (Load it instead / Just store it / Cancel) is the
                        // question, over the Location Manager.
                        if (window.moveConfirmKind && window.moveConfirmKind(body) === 'head_load'
                                && window.askMoveConfirm) {
                            window.askMoveConfirm(body, {
                                door: 'slot_scan', original, prior,
                                host: document.getElementById('manageModal'), box, slot,
                                send: (next, nextPrior) => postDeposit(next, nextPrior),
                            });
                            return;
                        }
                        // A printing head the overlay's probe missed (slow or
                        // unreachable printer), or one it couldn't know about (the
                        // spool LEAVING a printing head, D6). Re-ask with the
                        // server's own message, which names those heads (Group 39
                        // review, routes-wire-7: the re-open repeated this
                        // deposit's text, so its Yes covered heads the dialog
                        // never named), and replay the same spool.
                        _reaskFromServer(body, (prior && prior.heads) || [], { toolhead, box, slot, title },
                            (heads) => {
                                if (window.buildMoveReplay) {
                                    const r = window.buildMoveReplay('slot_scan', original, body,
                                        prior && prior.store ? 'store' : 'load', prior || {});
                                    postDeposit(r.body, r.prior);
                                } else {
                                    postDeposit(Object.assign({}, original, { confirmed_toolheads: heads }),
                                        Object.assign({}, prior || {}, { heads }));
                                }
                            });
                    } else {
                        // Includes assignment_failed: the spool stays in the buffer.
                        showToast(`❌ Deposit failed: ${body.msg || body.error || body.action || 'unknown'}`, 'error', 7000);
                    }
                })
                .catch(e => {
                    idle();
                    console.error(e);
                    showToast('Deposit — network error', 'error', 7000);
                    if (window.logClientEvent) window.logClientEvent(
                        `❌ Deposit network error: ${e && e.message ? e.message : 'connection failed'}`,
                        'ERROR'
                    );
                });
        };
        const spoolLine = `<div class="text-warning fw-bold mb-2" style="font-size:1rem;">Spool: ${bsDisplay}</div>`;
        let depositBody;
        if (btn.dataset.singleSlot === '1') {
            depositBody = spoolLine + `<div class="text-light" style="font-size:1.05rem;">` +
                `Puts it in <b>${box}</b>. It is not loaded onto <b>${toolhead}</b>: ${box} is attached to ` +
                `${toolhead} because its own spool runs there, not as a feed. To load it, scan ${toolhead}'s label.</div>`;
        } else if (notLoaded) {
            depositBody = spoolLine + `<div class="text-light" style="font-size:1.05rem;">` +
                `Drops it into <b>${box}:SLOT:${slot}</b> (printer pool). It is not loaded onto a toolhead.</div>`;
        } else {
            depositBody = spoolLine + `<div class="text-light" style="font-size:1.05rem;">` +
                `Drops it into <b>${box}:SLOT:${slot}</b>. Because this slot is bound to ` +
                `<b>${toolhead}</b>, it auto-deploys to the toolhead once placed. ` +
                `If ${toolhead} currently has another spool, that one goes back to its recorded source box first (or the printer’s room / Unassigned if it has none).</div>`;
        }
        // The overlay's probe of the slot's bound head: its banner is what Yes confirms.
        const confirmDeposit = (probed) => showConfirmOverlay({
            toolhead: notLoaded ? null : toolhead, box, slot, title,
            body: depositBody,
            probed,
            onConfirm: (stateInfo) => {
                const heads = notLoaded ? [] : _headsShown([], stateInfo, toolhead);
                postDeposit(Object.assign({}, original, { confirmed_toolheads: heads }), { heads });
            },
        });
        if (notLoaded || !window.askMoveConfirm) {
            idle();
            confirmDeposit(undefined);
            return;
        }
        // Group 40.3, Derek (2026-10-14): ONE dialog for a deposit. When the slot's
        // head runs a spool (it can't be this slot's own: the deposit tile exists
        // only while nothing claims the slot), or its printer is printing, FCC
        // asks anyway, so this overlay is skipped and the server's three-way is
        // the question (Enter stores: a toolhead isn't loaded mid-print). An
        // idle, empty head keeps this overlay. A head that couldn't be read keeps
        // it too; the server re-checks either way. The spool being deposited
        // isn't a resident (Group 40.3 review, C3): a head whose only spool is
        // that one is asked nothing by FCC, so it keeps this overlay.
        const headResidents = window.fetchT(`/api/get_contents?id=${encodeURIComponent(toolhead)}&strict=1`, {}, 6000)
            .then(r => (r.ok ? r.json() : null))
            .then(items => (Array.isArray(items)
                ? items.filter(it => it && !it.is_ghost && String(it.id) !== String(buffered.id)
                    && String(it.location || '').replace(/"/g, '').trim().toUpperCase() === String(toolhead).toUpperCase())
                : null))
            .catch(() => null);
        Promise.all([_probeWithTimeout(toolhead), headResidents]).then(([detail, residents]) => {
            if (gen !== _overlayGen) {
                // Another question took the screen meanwhile (a swap's re-ask, a
                // later tap): this deposit isn't sent, and says so (Group 40.3
                // fix check, W2: it used to vanish).
                idle();
                showToast(`Deposit of ${bsDisplay} not sent: another question took the screen — tap it again`,
                    'info', 4000);
                if (window.logClientEvent) window.logClientEvent(
                    `ℹ️ Deposit of ${bsDisplay} into ${box} slot ${slot} not sent: another question took the screen`, 'INFO');
                return;
            }
            const printing = !!(detail && detail.active);
            if (printing || (residents && residents.length)) {
                // The print this page saw goes with the request (Group 40.3
                // review, C1): if FCC's own printer check fails a moment later,
                // it still asks instead of loading mid-print unasked.
                if (printing) original.seen_printing = [String(toolhead).toUpperCase()];
                postDeposit(original, { heads: [] });
                return;
            }
            idle();
            confirmDeposit(detail);
        });
    };

    window.quickSwapTap = (btn) => {
        if (!btn) return;
        // A deposit in flight owns the screen until its answer (Group 40.3 fix
        // check, W1 / S2): a swap tapped meanwhile stacked a second dialog with
        // the deposit's question, and its Tab handler took the question's keys.
        if (_depositBusyAt && Date.now() - _depositBusyAt < 20000) {
            showToast('⏳ Still working on the last deposit — one moment', 'info', 2500);
            return;
        }
        // Disabled buttons (empty slot) should be a no-op. A tile that is
        // disabled for another reason (two spools claim it, its box couldn't
        // be read) carries that reason in data-why (Group 42 review).
        if (btn.hasAttribute('disabled')) {
            showToast(btn.dataset.why ? `⚠️ ${btn.dataset.why}`
                : `⚠️ ${btn.dataset.box} slot ${btn.dataset.slot} is empty — nothing to swap`, 'warning', 4000);
            return;
        }
        const opts = {
            toolhead: btn.dataset.toolhead,
            box: btn.dataset.box,
            slot: btn.dataset.slot,
        };
        // Pull the display label from the button so the confirm overlay names
        // the specific spool. Ask-before-you-commit matters more when the
        // button text tells you what you're committing to.
        // The 'quickswap' SpoolCardBuilder variant stores it on data-spool-label.
        // Older button-style cells (empty-slot fallbacks) carry the label in
        // their inner HTML — fall back to the DOM query for those.
        let spoolLabel = btn.dataset.spoolLabel || '';
        if (!spoolLabel) {
            const labelEl = btn.querySelector('.fw-bold + .fw-bold, div.fw-bold:nth-child(2)');
            spoolLabel = labelEl ? labelEl.innerText.trim() : '';
        }
        // Active-print banner is handled inside showConfirmOverlay itself
        // now (covers all 4 call sites). No pre-probe wrapper here.
        showConfirmOverlay({
            ...opts,
            title: `Load ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`,
            body: (spoolLabel
                    ? `<div class="text-warning fw-bold mb-2">Spool: ${spoolLabel}</div>`
                    : '')
                + 'This moves that spool onto <b>' + opts.toolhead + '</b>. '
                + 'Any spool currently on the toolhead goes back to <em>its own</em> recorded source box — '
                + 'or, if it has none, to the printer’s room (else Unassigned).',
            // The probe result says whether the banner showed: its Yes confirms
            // that head (Group 39.1; this used to be thrown away).
            onConfirm: (stateInfo) => performSwap(opts, stateInfo),
        });
    };

    // Resolve which concrete toolhead a Return-to-Slot click is actually
    // going to act on. For a specific toolhead loc (e.g. XL-3) it's that
    // loc. For a Printer loc (e.g. XL / CORE1) we check each of its
    // toolheads' contents and return the first one that's loaded — which
    // mirrors the backend's own selection logic. The toolheads come from the
    // row (printerToolheadIds), so CORE1's single head CORE1 is a candidate.
    const _resolveReturnTarget = (loc) => {
        if (!loc) return Promise.resolve(null);
        const up = String(loc.LocationID).toUpperCase();
        if (loc.Type !== PRINTER_TYPE) {
            return Promise.resolve(up);
        }
        const candidates = printerToolheadIds(loc, state.printerMap || {});
        if (!candidates.length) return Promise.resolve(null);
        // Check each candidate in the order printerToolheadIds returns them
        // (toolhead position order; printer_map order only on the legacy
        // prefix fallback); first one with contents wins.
        const check = (i) => {
            if (i >= candidates.length) return null;
            return fetch(`/api/get_contents?id=${encodeURIComponent(candidates[i])}`)
                .then(r => r.ok ? r.json() : [])
                // Only a spool really ON the head counts; a ghost is loaded elsewhere.
                .then(items => (items || []).some(it => !it.is_ghost) ? candidates[i] : check(i + 1))
                .catch(() => check(i + 1));
        };
        return Promise.resolve(check(0));
    };

    // --- Return (Group 40.6: Derek's D5, item D, item E) ---------------------
    // One flow for the toolhead view's ↩️ Return and a DEPLOYED slot card's ↩️:
    //   1. the server's dry run (POST /api/quickswap/return {dry_run: true})
    //      says where the spool goes, with the printer check beside it (the
    //      "⏳ Checking XL…" pill), so the confirm's banner is ready before
    //      anything moves;
    //   2. no usable slot (none recorded, the recorded one taken, or more than
    //      one obvious answer): the slot picker in return mode, with its ⭐ and
    //      a No slot tile;
    //   3. the confirm names the exact slot, or "no slot — LR-MDB-1 will show
    //      5/4";
    //   4. the Return sends that slot and the spool it showed
    //      ({toolhead, box, slot, expected_spool}); a slot taken meanwhile is
    //      picked again, nothing written.
    // `ctx`: {th: the head it empties, vth / isVirtual: the printer view it was
    // resolved from, expectedSpool, refreshId: a view to refresh when no head
    // view is open (the box a DEPLOYED card sits in), probe: the printer check
    // (a promise of its answer), heads: the heads confirmed so far}.

    const _postReturn = (payload) => fetch('/api/quickswap/return', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }).then(_readAnswer);

    // Refresh the view after a Return: the head view (currentLoc), else the view
    // the flow came from (the box a DEPLOYED card's ↩️ was tapped in).
    const _refreshAfterReturn = (ctx) => {
        if (currentLoc) { _refreshAfterMove(); return; }
        const id = ctx && ctx.refreshId;
        if (!id) return;
        const doRefresh = () => {
            try { if (typeof state !== 'undefined') state.lastLocRenderHash = null; } catch (e) { /* noop */ }
            if (window.refreshManageView) window.refreshManageView(id);
            document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
        };
        doRefresh();
        setTimeout(doRefresh, 450);
    };

    // What the box's count will read with the spool in it unslotted: the
    // server's own count, else the picker model's (its No slot tile's rule).
    const _occupancyAfter = (plan) => {
        const occ = plan && plan.occupancy;
        if (occ && occ.max) return occ;
        const m = plan && plan.options;
        if (!m || !m.max_slots) return null;
        const after = (m.slots || []).reduce((n, s) => n + (s.claimants || []).length, 0)
            + (m.unslotted || []).length + 1;
        return { after, max: m.max_slots };
    };

    // The dry run answered something other than a plan: say so where the user
    // looks (the overlay for "nothing to do here", a toast for a failure).
    const _returnRefused = (ctx, body) => {
        const th = body.active_toolhead || ctx.th;
        const nothing = (title, text) => showConfirmOverlay({
            toolhead: th,
            // Nothing will move, so no printer banner (and no second check).
            probed: null,
            title,
            body: `<div class="text-warning fw-bold" style="font-size:1.05rem;">${text}</div>`,
            onConfirm: () => { /* no-op: nothing the server would do */ },
        });
        if (body.action === 'return_no_spool') {
            nothing(`Nothing to return on ${ctx.th}`,
                `No spool is loaded on <b>${_escapeHtml(ctx.th)}</b> — nothing to return.`);
        } else if (body.action === 'return_ambiguous') {
            const n = (body.spools || []).length || 2;
            nothing(`${th} holds ${n} spools`,
                `<b>${_escapeHtml(th)}</b> holds ${n} spools — eject the wrong one first, then Return.`);
        } else if (body.action === 'return_no_binding') {
            // The server's reason when it has one (Group 40.6 review, R2: a box
            // that feeds the head but has no slot count, and how to fix it).
            nothing(`Return the spool on ${th}?`, body.msg
                ? `${_escapeHtml(body.msg)} — nothing was moved.`
                : `<b>${_escapeHtml(th)}</b> has no recorded source and no bound dryer box slot — nothing to return to.`);
        } else if (body.action === 'return_spool_mismatch') {
            showToast(`⚠️ ${body.error || `${th} holds another spool now — nothing moved`}`, 'warning', 7000);
            if (window.logClientEvent) window.logClientEvent(`⚠️ Return refused: ${body.error || 'another spool is on the head now'}`, 'WARNING');
            _refreshAfterReturn(ctx);
        } else if (body.action === 'return_bad_toolhead') {
            showToast(`⚠️ ${ctx.th} is not a registered toolhead — nothing to return`, 'warning', 7000);
        } else {
            showToast(`❌ Return failed: ${body.error || body.action || 'unknown'}`, 'error', 7000);
            if (window.logClientEvent) window.logClientEvent(
                `❌ Return off ${th} failed before anything moved: ${body.error || body.action || 'unknown'}`, 'ERROR');
        }
    };

    // The confirm before anything moves: it names the exact slot (or no slot)
    // and why, with the printer banner when the head's printer is printing.
    // `chosen`: the user picked it in the slot picker.
    const _confirmReturn = (ctx, plan, choice, chosen = false) => {
        const th = plan.active_toolhead || ctx.th;
        const box = choice.box || plan.box;
        const none = !choice.slot || String(choice.slot) === 'none';
        let where;
        if (none) {
            const occ = _occupancyAfter(plan);
            where = `<span class="text-info fw-bold">${_escapeHtml(box)}</span> — `
                + `<span class="text-warning fw-bold">no slot</span>`
                + (occ ? ` <span class="text-warning">(${_escapeHtml(box)} will show ${occ.after}/${occ.max})</span>` : '');
        } else {
            where = `<span class="text-info fw-bold">${_escapeHtml(box)} slot ${_escapeHtml(choice.slot)}</span>`;
        }
        let tag = '';
        if (!none && !chosen && plan.source === 'physical_source') {
            tag = ' <span class="text-success fw-bold">(original source)</span>';
        } else if (!none && !chosen && plan.source === 'feed_slot') {
            tag = ` <span class="text-info fw-bold">(the only free slot that feeds ${_escapeHtml(th)})</span>`;
        } else if (!none) {
            tag = ' <span class="text-info fw-bold">(your choice)</span>';
        }
        const resolvedNote = ctx.isVirtual
            ? `<div class="text-warning small mb-2" style="font-size:0.95rem;">`
              + `(Resolved from the <b>${_escapeHtml(ctx.vth)}</b> virtual printer — first toolhead with a loaded spool.)</div>`
            : '';
        const spoolLine = plan.spool != null
            ? `<div class="text-light mb-2" style="font-size:1rem;">Spool: <b>${_escapeHtml(plan.display || ('#' + plan.spool))}</b></div>`
            : '';
        const note = (!chosen && plan.note)
            ? `<div class="text-warning mt-2" style="font-size:0.95rem;">${_escapeHtml(plan.note)}.</div>`
            : '';
        const slot = none ? 'none' : String(choice.slot);
        // The printer check started beside the plan; the confirm waits for its
        // answer (it never rejects), so the banner is on it before anything moves.
        Promise.resolve(ctx.probe || null).then((detail) => showConfirmOverlay({
            toolhead: th,
            probed: detail,
            title: `Return the spool on ${th}?`,
            body: resolvedNote + spoolLine
                + `<div class="text-light" style="font-size:1.05rem;">Sending back to: ${where}${tag}</div>` + note,
            onConfirm: (stateInfo) => performReturn(
                { toolhead: th, box, slot, expected_spool: plan.spool }, stateInfo, ctx.heads || [], ctx),
        }));
    };

    // No usable slot: the slot picker in return mode (occupied slots greyed
    // out, a ⭐: a free slot feeding this head, else a spare one, else No slot).
    const _pickReturnSlot = (ctx, plan) => {
        if (typeof window.openSlotPicker !== 'function') {
            showToast('❌ The slot picker is missing — reload the page (Ctrl+F5) and try again', 'error', 7000);
            return;
        }
        const head = plan.active_toolhead || ctx.th;
        window.openSlotPicker({
            location: plan.box,
            spool: plan.spool,
            mode: 'return',
            toolhead: head,
            host: document.getElementById('manageModal') || undefined,
        }).then((pick) => {
            if (!pick) {
                if (window.logClientEvent) window.logClientEvent(
                    `ℹ️ Return of #${plan.spool} off ${head}: no slot chosen — nothing moved`, 'INFO');
                return;
            }
            const choice = pick.kind === 'none'
                ? { box: pick.box || plan.box, slot: 'none' }
                : { box: pick.box || plan.box, slot: String(pick.slot) };
            _confirmReturn(ctx, plan, choice, true);
        });
    };

    const _startReturn = (ctx) => {
        const dry = { toolhead: ctx.th, dry_run: true };
        if (ctx.expectedSpool != null) dry.expected_spool = ctx.expectedSpool;
        // The printer check starts beside the plan ("⏳ Checking XL…"): the
        // confirm shows its banner, and a slow printer never delays the plan or
        // the slot picker (whose own chips say how each printer is doing).
        ctx.probe = _probeWithTimeout(ctx.th);
        _postReturn(dry)
            .then(({ body }) => {
                if (body.action !== 'return_plan') { _returnRefused(ctx, body); return; }
                if (ctx.expectedSpool == null) ctx.expectedSpool = body.spool;
                if (body.needs_choice) _pickReturnSlot(ctx, body);
                else _confirmReturn(ctx, body, { box: body.box, slot: body.slot });
            })
            .catch(e => {
                console.error(e);
                showToast('Return — network error', 'error', 7000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Return network error: ${e && e.message ? e.message : 'connection failed'}`, 'ERROR');
            });
    };

    // A toolhead FCC knows: listed in a Printer row's toolheads[] (what the
    // printer map is built from) or in state.printerMap. A Printer row that
    // isn't its own head (XL) is not one.
    const _isRegisteredHead = (locId) => {
        const id = String(locId || '').replace(/"/g, '').trim().toUpperCase();
        if (!id) return false;
        const lists = (list) => (Array.isArray(list) ? list : [])
            .some(e => e && String(e.location_id || '').trim().toUpperCase() === id);
        if ((state.allLocations || []).some(r => r && r.Type === PRINTER_TYPE && lists(r.toolheads))) return true;
        return Object.values(state.printerMap || {}).some(lists);
    };

    window.returnToolheadToSlot = () => {
        if (!currentLoc) return;
        // The view the button was pressed on (the user may move on meanwhile).
        const loc = currentLoc;
        const vth = String(loc.LocationID).toUpperCase();
        _resolveReturnTarget(loc).then(resolvedTh => {
            const th = resolvedTh || vth;
            const isVirtual = loc.Type === PRINTER_TYPE;

            if (isVirtual && !resolvedTh) {
                // No toolhead of this printer has a loaded spool — don't
                // pretend there's anything to confirm.
                showConfirmOverlay({
                    toolhead: vth,
                    title: `Nothing to return on ${vth}`,
                    body: `<div class="text-warning fw-bold" style="font-size:1.05rem;">`
                        + `No toolhead on <b>${vth}</b> is currently loaded — nothing to return.</div>`,
                    onConfirm: () => { /* no-op */ },
                });
                return;
            }
            _startReturn({ th, vth, isVirtual: isVirtual && !!resolvedTh, expectedSpool: null,
                           refreshId: null, heads: [] });
        });
    };

    // Group 40.6, item E: the ↩️ RETURN SPOOL on a DEPLOYED slot card
    // (ui_builder.js). The card's spool is loaded on `deployedTo`: a toolhead
    // gets the canonical Return for that head, naming the spool the card showed
    // (`expected_spool`), with its printer check, slot rule and picker. It used
    // to post the slot straight back, so it emptied a printing head unasked and
    // repeated Return's slot logic. A stale trail (the spool is on no toolhead
    // FCC knows) puts it back in its box with no chain.
    // Group 40.6 review (R1): `box` is the spool's OWN box (its trail), and
    // `viewId` the view the card is in, refreshed after a Return. The stale
    // trail's slot goes as a picked slot, kept only while it is free: an
    // explicit slot was the engine's Overwrite, which unseated whatever spool
    // the slot held, unasked (in a Room view, slot N of every box in it).
    window.returnDeployedSpool = (box, spoolId, slot, deployedTo, viewId) => {
        const head = String(deployedTo || '').replace(/"/g, '').trim().toUpperCase();
        if (head && _isRegisteredHead(head)) {
            _startReturn({ th: head, vth: head, isVirtual: false, expectedSpool: Number(spoolId),
                           refreshId: viewId || box, heads: [] });
            return;
        }
        const picked = String(slot == null ? '' : slot).replace(/"/g, '').trim();
        const opts = { autoDeploy: false };
        if (picked && !['null', 'none', 'undefined'].includes(picked.toLowerCase())) opts.pickedSlot = picked;
        if (typeof window.doAssign === 'function') window.doAssign(box, spoolId, null, null, opts);
    };

    // --- Bind-a-Slot quick picker ---
    // Lightweight searchable list of every dryer box slot. Tapping a slot
    // writes one binding: slot → currentLoc.LocationID. For virtual printers,
    // the first toolhead of the printer is used as the bind target (user can
    // always refine via the full Feeds editor afterward).
    const _pickerState = { slots: [], filtered: [], activeIdx: -1, targetToolhead: null };

    const _pickerCloseOnOutside = (e) => {
        const ov = document.getElementById('fcc-bind-picker-overlay');
        if (!ov || ov.style.display === 'none') return;
        if (!ov.contains(e.target)) {
            const btn = e.target && e.target.closest && e.target.closest('[onclick*="openBindSlotPicker"]');
            if (btn) return;
            window.closeBindSlotPicker();
        }
    };

    const _renderPickerList = () => {
        const el = document.getElementById('fcc-bind-picker-list');
        if (!el) return;
        if (!_pickerState.filtered.length) {
            el.innerHTML = '<div class="text-warning py-3 fw-bold" style="font-size:1rem;">No matching slots.</div>';
            return;
        }
        const th = String(_pickerState.targetToolhead || '').toUpperCase();
        const rows = _pickerState.filtered.map((s, i) => {
            const targetUp = String(s.target || '').toUpperCase();
            const alreadyHere = targetUp === th;
            let statusHtml;
            if (!s.target) {
                statusHtml = '<span class="text-success fw-bold ms-2">◦ unbound</span>';
            } else if (alreadyHere) {
                statusHtml = '<span class="text-success fw-bold ms-2">✓ already feeds this toolhead</span>';
            } else {
                statusHtml = `<span class="text-warning ms-2">→ ${s.target}</span>`;
            }
            const active = i === _pickerState.activeIdx ? ' kb-active bg-info text-dark' : '';
            // Show an inline Unbind button whenever the slot is currently
            // bound to ANY toolhead — that way users don't have to go into
            // the full Feeds editor just to clear a slot.
            const unbindBtn = s.target
                ? `<button type="button" class="fcc-bind-picker-unbind btn btn-sm btn-outline-warning fw-bold ms-2"
                        data-idx="${i}" title="Clear this slot's binding without rebinding it">
                        🔗✖ Unbind
                    </button>`
                : '';
            return `
                <div class="fcc-bind-picker-item d-flex align-items-center justify-content-between py-2 px-3 border-bottom border-secondary${active}"
                     data-idx="${i}" style="cursor:pointer; font-size:1.05rem;">
                    <div>
                        <span class="fw-bold">${s.box}</span>
                        <span class="text-light ms-2" style="opacity:0.8;">slot ${s.slot}</span>
                    </div>
                    <div class="d-flex align-items-center small">
                        ${statusHtml}
                        ${unbindBtn}
                    </div>
                </div>`;
        }).join('');
        el.innerHTML = rows;
        Array.from(el.querySelectorAll('.fcc-bind-picker-item')).forEach(row => {
            row.addEventListener('click', (e) => {
                // Clicks on the Unbind button handle themselves — don't
                // also trigger the row's bind action.
                if (e.target && e.target.closest('.fcc-bind-picker-unbind')) return;
                _pickerState.activeIdx = parseInt(row.dataset.idx, 10);
                _pickerCommit();
            });
        });
        Array.from(el.querySelectorAll('.fcc-bind-picker-unbind')).forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.dataset.idx, 10);
                _pickerState.activeIdx = idx;
                _pickerUnbind();
            });
        });
    };

    const _pickerFilter = (q) => {
        const needle = (q || '').trim().toLowerCase();
        if (!needle) {
            _pickerState.filtered = _pickerState.slots.slice();
        } else {
            _pickerState.filtered = _pickerState.slots.filter(s =>
                s.box.toLowerCase().includes(needle)
                || s.slot.toString().includes(needle)
                || (s.box_name && s.box_name.toLowerCase().includes(needle))
                || (s.target && s.target.toLowerCase().includes(needle))
            );
        }
        _pickerState.activeIdx = _pickerState.filtered.length ? 0 : -1;
        _renderPickerList();
    };

    const _refreshPickerListing = () => {
        // Re-fetch the slot list so bound→unbound (or vice versa) changes
        // land immediately in the open picker.
        const search = document.getElementById('fcc-bind-picker-search');
        return fetch('/api/dryer_boxes/slots')
            .then(r => r.json())
            .then(body => {
                _pickerState.slots = body.slots || [];
                _pickerFilter(search ? search.value : '');
            })
            .catch(() => { /* best-effort */ });
    };

    const _pickerCommit = () => {
        const pick = _pickerState.filtered[_pickerState.activeIdx];
        const th = _pickerState.targetToolhead;
        if (!pick || !th) return;
        // If this slot already feeds the target toolhead, don't bother
        // round-tripping — tell the user it's a no-op.
        if (String(pick.target || '').toUpperCase() === String(th).toUpperCase()) {
            showToast(`✓ ${pick.box} slot ${pick.slot} already feeds ${th}`, 'info', 3000);
            return;
        }
        fetch(
            `/api/dryer_box/${encodeURIComponent(pick.box)}/bindings/${encodeURIComponent(pick.slot)}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: th }),
            }
        )
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (ok) {
                    const warn = (body.warnings || []).length;
                    const overwriteNote = pick.target
                        ? ` (was → ${pick.target})`
                        : '';
                    const warnTxt = warn ? ` ⚠️ ${warn} warning(s) — see log` : '';
                    showToast(`🔗 ${pick.box} slot ${pick.slot} → ${th}${overwriteNote}${warnTxt}`,
                        warn ? 'warning' : 'success', warn ? 8000 : 4000);
                    window.closeBindSlotPicker();
                    if (window.refreshManageView && currentLoc) {
                        window.refreshManageView(currentLoc.LocationID);
                    }
                    if (window.renderQuickSwapSection && currentLoc) {
                        window.renderQuickSwapSection(currentLoc);
                    }
                } else {
                    const errs = (body.errors || []).map(e => `${e.slot}: ${e.reason}`).join('; ');
                    showToast(`❌ ${errs || body.error || 'Binding failed'}`, 'error', 5000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Bind — network error', 'error', 5000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Bind network error: ${e && e.message ? e.message : 'connection failed'}`,
                    'ERROR'
                );
            });
    };

    // Clear a single slot's binding without closing the picker — the user
    // often wants to unbind and then pick a different slot in one visit.
    const _pickerUnbind = () => {
        const pick = _pickerState.filtered[_pickerState.activeIdx];
        if (!pick || !pick.target) return;
        fetch(
            `/api/dryer_box/${encodeURIComponent(pick.box)}/bindings/${encodeURIComponent(pick.slot)}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: null }),
            }
        )
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (ok) {
                    showToast(`🔗✖ ${pick.box} slot ${pick.slot} unbound (was → ${pick.target})`,
                        'success', 2500);
                    // Keep the picker open and refresh its listing so the
                    // now-unbound slot jumps to the top.
                    _refreshPickerListing();
                    // Also refresh the Quick-Swap grid behind us since that
                    // slot no longer appears there.
                    if (window.renderQuickSwapSection && currentLoc) {
                        window.renderQuickSwapSection(currentLoc);
                    }
                } else {
                    const errs = (body.errors || []).map(e => `${e.slot}: ${e.reason}`).join('; ');
                    showToast(`❌ ${errs || body.error || 'Unbind failed'}`, 'error', 5000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Unbind — network error', 'error', 5000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Unbind network error: ${e && e.message ? e.message : 'connection failed'}`,
                    'ERROR'
                );
            });
    };

    const _updatePickerToolheadLabel = (value) => {
        _pickerState.targetToolhead = String(value || '').toUpperCase();
        const thSpan = document.getElementById('fcc-bind-picker-toolhead');
        if (thSpan) thSpan.innerText = _pickerState.targetToolhead;
    };

    window.openBindSlotPicker = () => {
        if (!currentLoc) {
            showToast('Open a toolhead first, then bind a slot.', 'warning', 3500);
            return;
        }
        const ov = document.getElementById('fcc-bind-picker-overlay');
        const search = document.getElementById('fcc-bind-picker-search');
        const close = document.getElementById('fcc-bind-picker-close');
        const thRow = document.getElementById('fcc-bind-picker-toolhead-row');
        const thSelect = document.getElementById('fcc-bind-picker-toolhead-select');
        if (!ov || !search) return;

        // Figure out the target toolhead(s). Toolhead view: one option.
        // Virtual printer view: offer every toolhead of the printer so the
        // user picks explicitly rather than silently defaulting to the first.
        let toolheadOptions = [];
        if (currentLoc.Type === PRINTER_TYPE) {
            // Same toolhead resolution as Return (printerToolheadIds). The old
            // prefix-only match left this list empty on CORE1, whose single head
            // shares the printer's id, so toolheadOptions[0] below threw and the
            // picker never opened (2026-09-13).
            const pm = state.printerMap || {};
            printerToolheadIds(currentLoc, pm).forEach(id => {
                let label = id;
                for (const [printerName, entries] of Object.entries(pm)) {
                    const e = (entries || []).find(x => String(x.location_id).toUpperCase() === id);
                    if (e) { label = `${id} — Toolhead ${e.position + 1} on ${printerName}`; break; }
                }
                toolheadOptions.push({ value: id, label });
            });
            toolheadOptions.sort((a, b) => a.value.localeCompare(b.value));
        } else {
            toolheadOptions = [{
                value: String(currentLoc.LocationID).toUpperCase(),
                label: String(currentLoc.LocationID).toUpperCase(),
            }];
        }
        if (!toolheadOptions.length) {
            showToast(`${currentLoc.LocationID} has no toolheads registered — add them in the printer map, then bind a slot.`, 'warning', 7000);
            return;
        }

        if (thRow && thSelect) {
            if (toolheadOptions.length > 1) {
                thSelect.innerHTML = toolheadOptions.map(o =>
                    `<option value="${o.value}">${o.label}</option>`).join('');
                thSelect.value = toolheadOptions[0].value;
                thRow.style.display = 'block';
                thSelect.onchange = () => {
                    _updatePickerToolheadLabel(thSelect.value);
                    // Re-filter so "unbound" ordering is still respected for
                    // the freshly chosen toolhead.
                    _pickerFilter(search.value);
                };
            } else {
                thRow.style.display = 'none';
            }
        }
        _updatePickerToolheadLabel(toolheadOptions[0].value);
        search.value = '';

        fetch('/api/dryer_boxes/slots')
            .then(r => r.json())
            .then(body => {
                _pickerState.slots = body.slots || [];
                _pickerFilter('');
                ov.style.display = 'block';
                search.focus();
                document.addEventListener('click', _pickerCloseOnOutside, true);
            })
            .catch(e => {
                console.error(e);
                showToast('Could not load dryer box slots', 'error', 5000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Bind picker failed to load dryer box slots: ${e && e.message ? e.message : 'fetch failed'}`,
                    'ERROR'
                );
            });

        search.oninput = () => _pickerFilter(search.value);
        search.onkeydown = (e) => {
            if (e.key === 'Escape') {
                // Close the bind picker only — keep the Location Manager modal
                // open behind it. stopPropagation prevents the Escape from
                // bubbling to the modal where Bootstrap would dismiss the whole
                // thing. Handled BEFORE the empty-list guard so an empty filter
                // list can still be escaped out of.
                e.preventDefault();
                e.stopPropagation();
                window.closeBindSlotPicker();
                return;
            }
            const items = _pickerState.filtered;
            if (!items.length) return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                _pickerState.activeIdx = (_pickerState.activeIdx + 1) % items.length;
                _renderPickerList();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                _pickerState.activeIdx = (_pickerState.activeIdx - 1 + items.length) % items.length;
                _renderPickerList();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                _pickerCommit();
            }
        };
        close.onclick = window.closeBindSlotPicker;
    };

    window.closeBindSlotPicker = () => {
        const ov = document.getElementById('fcc-bind-picker-overlay');
        if (ov) ov.style.display = 'none';
        document.removeEventListener('click', _pickerCloseOnOutside, true);
    };

    window.editBindingsFromToolhead = () => {
        // Pick the first bound box that feeds this toolhead and jump into
        // its Feeds editor. If nothing is bound yet, close the current
        // manage modal and open the Locations modal so the user can pick
        // any dryer box to edit. Without the close step, Bootstrap stacks
        // the new modal behind the current one and it looks like a dead
        // click.
        const grid = document.getElementById('quickswap-grid');
        const firstBtn = grid && grid.querySelector('.fcc-qs-slot');
        const targetBox = firstBtn && firstBtn.dataset.box;

        const closeCurrent = () => {
            try {
                if (window.modals && window.modals.manageModal) {
                    window.modals.manageModal.hide();
                } else if (window.closeManage) {
                    window.closeManage();
                }
            } catch (e) { /* best effort */ }
        };

        if (targetBox) {
            // Tell renderFeedsSection to auto-expand + scroll the Feeds
            // body on the next render so the user lands where they want
            // to be without having to click Show.
            window._fccAutoExpandFeeds = true;
            if (window.openManage) window.openManage(targetBox);
            return;
        }

        closeCurrent();
        // Small delay so Bootstrap's backdrop finishes animating out
        // before the next modal opens.
        setTimeout(() => {
            if (window.openLocationsModal) {
                window.openLocationsModal();
                showToast('Pick a Dryer Box → "Manage/View" → Slot → Toolhead Feeds to bind this toolhead.',
                    'info', 8000);
            }
        }, 250);
    };

    // --- Keyboard navigation inside the Quick-Swap grid ---
    document.addEventListener('keydown', (e) => {
        const grid = document.getElementById('quickswap-grid');
        if (!grid || grid.childElementCount === 0) return;
        // An overlay on top (a confirm, the three-way load question, the slot
        // picker) owns the keys: `q` (scanned session ids contain it) or an arrow
        // used to move this grid's focus behind it, and a later Enter then ran
        // quickSwapTap on a tile nobody could see (Group 40.3 / 40.1 review).
        if (document.querySelectorAll('[data-overlay-mount="1"]').length) return;

        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;

        const modal = document.getElementById('manageModal');
        const modalOpen = modal && modal.classList.contains('show');
        if (!modalOpen) return;

        const buttons = Array.from(grid.querySelectorAll('.fcc-qs-slot'));
        if (!buttons.length) return;
        const currentIdx = buttons.findIndex(b => b.classList.contains('kb-active'));

        if (e.key === 'q' || e.key === 'Q') {
            // Jump focus into the grid on Q. Scroll the section into view
            // first — Quick-Swap often sits below the fold when a toolhead
            // also has a long Feeds editor / contents list above it. Without
            // the scroll the cyan kb-active focus glow appears off-screen.
            e.preventDefault();
            const section = document.getElementById('manage-quickswap-section');
            if (section && section.scrollIntoView) {
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            focusSlot(buttons[0]);
        } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            if (currentIdx === -1) return focusSlot(buttons[0]);
            e.preventDefault();
            focusSlot(buttons[(currentIdx + 1) % buttons.length]);
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            if (currentIdx === -1) return focusSlot(buttons[buttons.length - 1]);
            e.preventDefault();
            focusSlot(buttons[(currentIdx - 1 + buttons.length) % buttons.length]);
        } else if (e.key === 'Enter') {
            // A scan in flight owns this Enter (same rule as the confirm
            // overlays above). Press Q or an arrow to highlight a slot, then
            // scan a spool label, and without this the scan's terminating Enter
            // opened an unrequested "Load <box> slot N into <toolhead>?" confirm
            // — which then inherited the confirm-overlay Enter bug on top.
            if (window.isScanInFlight && window.isScanInFlight()) return;
            if (currentIdx >= 0) {
                e.preventDefault();
                window.quickSwapTap(buttons[currentIdx]);
            }
        }
    });

    window.renderQuickSwapSection = renderQuickSwapSection;

    // Keep empty-slot buttons in sync with buffer state — the "Deposit
    // from buffer" affordance only makes sense while a spool is held.
    document.addEventListener('inventory:buffer-updated', () => {
        if (currentLoc && window.renderQuickSwapSection) {
            window.renderQuickSwapSection(currentLoc);
        }
    });

    // L352 — heartbeat-driven SILENT refresh so the Quick-Swap cards' live
    // remaining-weight ticks while the view stays open. Without this, a spool
    // sitting in one of a toolhead's source slots that is weighed out /
    // filabridge-deducted / Prusament-corrected elsewhere shows a stale weight
    // for as long as the manage modal stays open with no buffer change.
    // Guards: only when a toolhead/printer manage view is actually open AND
    // visible, and NEVER while the user is mid keyboard-navigation inside the
    // grid (a re-render would yank focus). The silent mode + content-hash in
    // renderQuickSwapSection itself prevents flicker and skips the DOM swap
    // when nothing changed.
    document.addEventListener('inventory:sync-pulse', () => {
        if (!currentLoc || !window.renderQuickSwapSection) return;
        const mm = document.getElementById('manageModal');
        if (!mm || !mm.classList.contains('show')) return;
        const grid = document.getElementById('quickswap-grid');
        if (!grid) return;
        // Focus lives in the grid → user is navigating; don't disturb it.
        if (grid.contains(document.activeElement)) return;
        window.renderQuickSwapSection(currentLoc, { silent: true });
    });
})();
