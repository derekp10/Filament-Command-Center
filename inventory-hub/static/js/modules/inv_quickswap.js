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
    const TOOLHEAD_TYPES = new Set(['Tool Head', 'MMU Slot', 'No MMU Direct Load']);

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

    const renderQuickSwapSection = (loc) => {
        const section = document.getElementById('manage-quickswap-section');
        if (!section) return;

        if (!TOOLHEAD_TYPES.has(loc.Type)) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';

        // Need the printer_map (cached in state.printerMap by inv_loc_mgr.fetchPrinterMap).
        const ensurePM = state.printerMap
            ? Promise.resolve(state.printerMap)
            : fetch('/api/printer_map').then(r => r.json()).then(d => {
                state.printerMap = d.printers || {};
                return state.printerMap;
            });

        ensurePM.then(printerMap => {
            const printerName = resolvePrinterNameForToolhead(loc.LocationID, printerMap);
            const grid = document.getElementById('quickswap-grid');
            const empty = document.getElementById('quickswap-empty');
            grid.innerHTML = '';
            if (!printerName) {
                empty.style.display = 'block';
                empty.innerHTML = '⚠️ This toolhead is not registered in <code>printer_map</code>. Link slots in Location Manager.';
                return;
            }

            fetch(`/api/machine/${encodeURIComponent(printerName)}/toolhead_slots`)
                .then(r => r.ok ? r.json() : { toolheads: {} })
                .then(body => {
                    const entries = (body.toolheads || {})[String(loc.LocationID).toUpperCase()] || [];
                    if (!entries.length) {
                        empty.style.display = 'block';
                        empty.innerHTML = 'No dryer box slots are bound to this toolhead yet. ' +
                            '<a href="#" onclick="window.openLocationsModal(); return false;" class="text-info">Link a slot…</a>';
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
                        html += `<div class="w-100 small text-muted mt-1">📦 <span class="text-info">${boxId}</span></div>`;
                        byBox[boxId].sort((a, b) => Number(a.slot) - Number(b.slot)).forEach(e => {
                            html += `
                                <button type="button" class="fcc-qs-slot btn btn-outline-info"
                                    data-box="${e.box}" data-slot="${e.slot}"
                                    data-toolhead="${loc.LocationID}"
                                    style="min-width:88px; font-size:1.0rem;"
                                    onclick="window.quickSwapTap(this)"
                                    title="Load ${e.box} slot ${e.slot} into ${loc.LocationID}">
                                    <span class="fw-bold">Slot ${e.slot}</span>
                                </button>`;
                        });
                    });
                    grid.innerHTML = html;

                    // Focus first slot only when the user opted in via the Q shortcut;
                    // don't steal focus from the default list view.
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
        title.innerText = `Swap ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`;
        body.innerHTML = 'This moves the spool currently in that slot into the active toolhead. ' +
                        'Any spool already on the toolhead will be auto-ejected back to its source.';
        ov.style.display = 'block';
        const close = () => {
            ov.style.display = 'none';
            yes.onclick = null; no.onclick = null;
            document.removeEventListener('keydown', keyHandler, true);
        };
        const keyHandler = (e) => {
            if (e.key === 'Escape') { e.stopPropagation(); close(); }
            else if (e.key === 'Enter') { e.stopPropagation(); performSwap(opts); close(); }
        };
        yes.onclick = () => { performSwap(opts); close(); };
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
                    // Refresh the manage view so the active filament updates.
                    if (window.refreshManageView) window.refreshManageView(opts.toolhead);
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
