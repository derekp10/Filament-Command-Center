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

    const resolvePrinterNameForPrinterLoc = (loc, printerMap) => {
        // A Printer-type location surfaces ALL of its toolheads. Match by
        // Device Identifier / Name against printer_map keys.
        const candidates = [loc.Name, loc.LocationID, loc['Device Type'], loc['Device Identifier']]
            .filter(Boolean).map(s => String(s).trim());
        for (const printerName of Object.keys(printerMap || {})) {
            if (candidates.some(c => printerName.includes(c) || c.includes(printerName))) {
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

    const renderQuickSwapSection = (loc) => {
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
            grid.innerHTML = '';
            if (!printerName) {
                empty.style.display = 'block';
                empty.innerHTML = '⚠️ This location is not registered in <code class="text-info">printer_map</code>. ' +
                    'Add it in config.json to enable Quick-Swap.';
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
                        // Printer view: flatten ALL toolheads, tag each entry with its toolhead id.
                        Object.keys(toolheadMap).forEach(thId => {
                            (toolheadMap[thId] || []).forEach(e => {
                                entries.push({ ...e, toolhead: thId });
                            });
                        });
                    }

                    if (!entries.length) {
                        empty.style.display = 'block';
                        return;
                    }
                    empty.style.display = 'none';

                    // Group by source box for readability.
                    const byBox = {};
                    entries.forEach(e => {
                        if (!byBox[e.box]) byBox[e.box] = [];
                        byBox[e.box].push(e);
                    });
                    let html = '';
                    Object.keys(byBox).sort().forEach(boxId => {
                        html += `<div class="w-100 fw-bold mt-2 mb-1" style="font-size:1.05rem;">` +
                                `📦 <span class="text-info">${boxId}</span></div>`;
                        byBox[boxId].sort((a, b) => Number(a.slot) - Number(b.slot)).forEach(e => {
                            const th = e.toolhead || loc.LocationID;
                            const thHint = isPrinter ? `<br><span class="text-warning">→ ${th}</span>` : '';
                            html += `
                                <button type="button" class="fcc-qs-slot btn btn-outline-info fw-bold"
                                    data-box="${e.box}" data-slot="${e.slot}"
                                    data-toolhead="${th}"
                                    style="min-width:110px; font-size:1.1rem; padding:10px 14px;"
                                    onclick="window.quickSwapTap(this)"
                                    title="Load ${e.box} slot ${e.slot} into ${th}">
                                    <span>Slot ${e.slot}</span>${thHint}
                                </button>`;
                        });
                    });
                    grid.innerHTML = html;
                });
        });
    };

    const showConfirmOverlay = (opts) => {
        const ov = document.getElementById('fcc-quickswap-confirm-overlay');
        const title = document.getElementById('fcc-quickswap-confirm-title');
        const body = document.getElementById('fcc-quickswap-confirm-body');
        const yes = document.getElementById('fcc-quickswap-yes');
        const no = document.getElementById('fcc-quickswap-no');
        if (!ov || !yes || !no) return;
        title.innerText = opts.title || `Swap ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`;
        body.innerHTML = opts.body || ('This moves the spool currently in that slot into the active toolhead. ' +
                        'Any spool already on the toolhead will be auto-ejected back to its source.');
        ov.style.display = 'block';
        const close = () => {
            ov.style.display = 'none';
            yes.onclick = null; no.onclick = null;
            document.removeEventListener('keydown', keyHandler, true);
        };
        const keyHandler = (e) => {
            if (e.key === 'Escape') { e.stopPropagation(); close(); }
            else if (e.key === 'Enter') { e.stopPropagation(); opts.onConfirm && opts.onConfirm(); close(); }
        };
        yes.onclick = () => { opts.onConfirm && opts.onConfirm(); close(); };
        no.onclick = close;
        document.addEventListener('keydown', keyHandler, true);
        yes.focus();
    };

    const performSwap = (opts) => {
        fetch('/api/quickswap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(opts),
        })
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (ok && body.action === 'quickswap_done') {
                    showToast(`⚡ Spool #${body.moved} → ${opts.toolhead}`, 'success', 4000);
                    if (window.refreshManageView && currentLoc) window.refreshManageView(currentLoc.LocationID);
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                } else if (body.action === 'quickswap_empty_slot') {
                    showToast(`⚠️ ${opts.box} slot ${opts.slot} is empty — nothing to swap`, 'warning', 7000);
                } else if (body.action === 'quickswap_not_bound') {
                    showToast(`❌ Binding is stale — refresh and try again`, 'error', 8000);
                } else {
                    showToast(`❌ Quick-swap failed: ${body.error || body.action || 'unknown'}`, 'error', 8000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Quick-swap — network error', 'error', 7000);
            });
    };

    const performReturn = (opts) => {
        fetch('/api/quickswap/return', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(opts),
        })
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (ok && body.action === 'return_done') {
                    showToast(`↩️ Spool #${body.moved} → ${body.box}:SLOT:${body.slot}`, 'success', 4000);
                    if (window.refreshManageView && currentLoc) window.refreshManageView(currentLoc.LocationID);
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                } else if (body.action === 'return_no_spool') {
                    showToast(`⚠️ ${opts.toolhead} is empty — nothing to return`, 'warning', 7000);
                } else if (body.action === 'return_no_binding') {
                    showToast(`⚠️ ${opts.toolhead} has no bound slot to return to`, 'warning', 7000);
                } else {
                    showToast(`❌ Return failed: ${body.error || body.action || 'unknown'}`, 'error', 8000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Return — network error', 'error', 7000);
            });
    };

    window.quickSwapTap = (btn) => {
        if (!btn) return;
        const opts = {
            toolhead: btn.dataset.toolhead,
            box: btn.dataset.box,
            slot: btn.dataset.slot,
        };
        showConfirmOverlay({
            ...opts,
            onConfirm: () => performSwap(opts),
        });
    };

    window.returnToolheadToSlot = () => {
        if (!currentLoc) return;
        const th = currentLoc.LocationID;
        showConfirmOverlay({
            toolhead: th,
            title: `Return the spool on ${th} to its dryer box slot?`,
            body: `This sends whatever is currently in <b>${th}</b> back to the first dryer box slot that's bound to this toolhead. If the toolhead is empty, or has no bound slot, nothing happens.`,
            onConfirm: () => performReturn({ toolhead: th }),
        });
    };

    window.editBindingsFromToolhead = () => {
        // Pick the first bound box that feeds this toolhead, or prompt for a
        // dryer-box-to-link. For now we just open Location Manager on the
        // first source box if one exists — otherwise open the full list.
        const grid = document.getElementById('quickswap-grid');
        const firstBtn = grid && grid.querySelector('.fcc-qs-slot');
        if (firstBtn && firstBtn.dataset.box) {
            if (window.openManage) window.openManage(firstBtn.dataset.box);
            return;
        }
        // No binding yet — fall back to opening the master Locations modal so
        // the user can pick any dryer box.
        if (window.openLocationsModal) window.openLocationsModal();
    };

    window.quickSwapTap = (btn) => {
        if (!btn) return;
        showConfirmOverlay({
            toolhead: btn.dataset.toolhead,
            box: btn.dataset.box,
            slot: btn.dataset.slot,
        });
    };

    // --- Keyboard navigation inside the Quick-Swap grid ---
    document.addEventListener('keydown', (e) => {
        const grid = document.getElementById('quickswap-grid');
        if (!grid || grid.childElementCount === 0) return;

        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;

        const modal = document.getElementById('manageModal');
        const modalOpen = modal && modal.classList.contains('show');
        if (!modalOpen) return;

        const buttons = Array.from(grid.querySelectorAll('.fcc-qs-slot'));
        if (!buttons.length) return;
        const currentIdx = buttons.findIndex(b => b.classList.contains('kb-active'));

        if (e.key === 'q' || e.key === 'Q') {
            // Jump focus into the grid on Q.
            e.preventDefault();
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
            if (currentIdx >= 0) {
                e.preventDefault();
                window.quickSwapTap(buttons[currentIdx]);
            }
        }
    });

    window.renderQuickSwapSection = renderQuickSwapSection;
})();
