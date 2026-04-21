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
        // Backend synthesizes virtual Printer locations keyed by the
        // toolhead prefix (e.g. LocationID="XL" aggregates XL-1, XL-2…).
        // Match by: any printer whose toolhead IDs start with <LocationID>-.
        const prefix = String(loc.LocationID || '').trim().toUpperCase() + '-';
        for (const [printerName, entries] of Object.entries(printerMap || {})) {
            if ((entries || []).some(e => String(e.location_id).toUpperCase().startsWith(prefix))) {
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
        const rows = _pickerState.filtered.map((s, i) => {
            const bound = s.target
                ? `<span class="text-warning ms-2">→ ${s.target}</span>`
                : '<span class="text-success fw-bold ms-2">◦ unbound</span>';
            const active = i === _pickerState.activeIdx ? ' kb-active bg-info text-dark' : '';
            return `
                <div class="fcc-bind-picker-item d-flex align-items-center justify-content-between py-2 px-3 border-bottom border-secondary${active}"
                     data-idx="${i}" style="cursor:pointer; font-size:1.05rem;">
                    <div>
                        <span class="fw-bold">${s.box}</span>
                        <span class="text-muted ms-2">slot ${s.slot}</span>
                    </div>
                    <div class="small">${bound}</div>
                </div>`;
        }).join('');
        el.innerHTML = rows;
        Array.from(el.querySelectorAll('.fcc-bind-picker-item')).forEach(row => {
            row.addEventListener('click', () => {
                _pickerState.activeIdx = parseInt(row.dataset.idx, 10);
                _pickerCommit();
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

    const _pickerCommit = () => {
        const pick = _pickerState.filtered[_pickerState.activeIdx];
        const th = _pickerState.targetToolhead;
        if (!pick || !th) return;
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
                    const warnTxt = warn ? ` ⚠️ ${warn} warning(s) — see log` : '';
                    showToast(`🔗 ${pick.box} slot ${pick.slot} → ${th}${warnTxt}`,
                        warn ? 'warning' : 'success', warn ? 8000 : 4000);
                    window.closeBindSlotPicker();
                    // Re-render Quick-Swap with the new binding visible.
                    if (window.refreshManageView && currentLoc) {
                        window.refreshManageView(currentLoc.LocationID);
                    }
                    if (window.renderQuickSwapSection && currentLoc) {
                        window.renderQuickSwapSection(currentLoc);
                    }
                } else {
                    const errs = (body.errors || []).map(e => `${e.slot}: ${e.reason}`).join('; ');
                    showToast(`❌ ${errs || body.error || 'Binding failed'}`, 'error', 8000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Bind — network error', 'error', 7000);
            });
    };

    const _updatePickerToolheadLabel = (value) => {
        _pickerState.targetToolhead = String(value || '').toUpperCase();
        const thSpan = document.getElementById('fcc-bind-picker-toolhead');
        if (thSpan) thSpan.innerText = _pickerState.targetToolhead;
    };

    window.openBindSlotPicker = () => {
        if (!currentLoc) {
            showToast('Open a toolhead first, then bind a slot.', 'warning', 5000);
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
            const pm = state.printerMap || {};
            const prefix = String(currentLoc.LocationID).toUpperCase() + '-';
            for (const [printerName, entries] of Object.entries(pm)) {
                (entries || []).forEach(e => {
                    if (String(e.location_id).toUpperCase().startsWith(prefix)) {
                        toolheadOptions.push({
                            value: String(e.location_id).toUpperCase(),
                            label: `${e.location_id} — Toolhead ${e.position + 1} on ${printerName}`,
                        });
                    }
                });
            }
            toolheadOptions.sort((a, b) => a.value.localeCompare(b.value));
        } else {
            toolheadOptions = [{
                value: String(currentLoc.LocationID).toUpperCase(),
                label: String(currentLoc.LocationID).toUpperCase(),
            }];
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
                showToast('Could not load dryer box slots', 'error', 7000);
            });

        search.oninput = () => _pickerFilter(search.value);
        search.onkeydown = (e) => {
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
            } else if (e.key === 'Escape') {
                e.preventDefault();
                window.closeBindSlotPicker();
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
            // openManage on the same modal re-renders cleanly; no need to
            // close first.
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
