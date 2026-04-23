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

                    // Fetch live contents for each unique source box so the
                    // button can show WHAT spool is currently sitting in that
                    // slot. Without this, tapping "Slot 4" is a leap of faith.
                    const uniqueBoxes = [...new Set(entries.map(e => e.box))];
                    Promise.all(uniqueBoxes.map(b =>
                        fetch(`/api/get_contents?id=${encodeURIComponent(b)}`)
                            .then(r => r.ok ? r.json() : [])
                            .then(items => [b, items])
                            .catch(() => [b, []])
                    )).then(boxContents => {
                        const slotMap = {};
                        boxContents.forEach(([b, items]) => {
                            (items || []).forEach(it => {
                                const slotStr = String(it.slot || '').replace(/"/g, '').trim();
                                if (slotStr) slotMap[`${b}|${slotStr}`] = it;
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
                                        title="Open ${boxId} — Close returns here">${boxId}</a></div>`;
                            byBox[boxId].sort((a, b) => Number(a.slot) - Number(b.slot)).forEach(e => {
                                const th = e.toolhead || loc.LocationID;
                                const item = slotMap[`${e.box}|${e.slot}`];
                                const thLine = isPrinter
                                    ? `<div class="text-warning small" style="font-size:0.85rem;">→ ${th}</div>`
                                    : '';
                                let contentLines, borderCls, handler, titleAttr, disabledAttr;
                                if (item) {
                                    // Slot has a spool — tap loads it into the toolhead.
                                    const short = String(item.display || `#${item.id}`).replace(/"/g, '&quot;');
                                    const weight = item.remaining_weight != null
                                        ? `<div class="text-light small" style="font-size:0.9rem;">⚖️ ${Math.round(item.remaining_weight)}g</div>`
                                        : '';
                                    const swatch = item.color
                                        ? `<span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#${String(item.color).split(',')[0]};border:1px solid #fff;vertical-align:middle;margin-right:6px;"></span>`
                                        : '';
                                    contentLines = `
                                        <div class="fw-bold" style="font-size:0.95rem; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                            ${swatch}${short}
                                        </div>
                                        ${weight}`;
                                    borderCls = 'btn-outline-info';
                                    handler = 'window.quickSwapTap(this)';
                                    titleAttr = `Load ${item.display || `#${item.id}`} from ${e.box} slot ${e.slot} into ${th}`;
                                    disabledAttr = '';
                                } else if (bufferTopSpool) {
                                    // Empty slot + buffered spool — tap DEPOSITS
                                    // the buffered spool into the slot. Reuses
                                    // the scan-flow backend so auto-deploy to
                                    // the bound toolhead kicks in too.
                                    const bsDisplay = String(bufferTopSpool.display || `#${bufferTopSpool.id}`).replace(/"/g, '&quot;');
                                    const bsSwatch = bufferTopSpool.color
                                        ? `<span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#${String(bufferTopSpool.color).split(',')[0]};border:1px solid #fff;vertical-align:middle;margin-right:6px;"></span>`
                                        : '';
                                    contentLines = `
                                        <div class="text-success fw-bold" style="font-size:0.9rem;">⬇️ Deposit from buffer:</div>
                                        <div class="text-light" style="font-size:0.9rem; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                            ${bsSwatch}${bsDisplay}
                                        </div>`;
                                    borderCls = 'btn-outline-success';
                                    handler = 'window.quickSwapDeposit(this)';
                                    titleAttr = `Drop the buffered spool into ${e.box} slot ${e.slot} (auto-deploys to ${th})`;
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
                                        data-toolhead="${th}"
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
                        grid.innerHTML = html;
                    });
                });
        });
    };

    // Keeps a reference to the current overlay's teardown so external
    // callers (e.g. the manage modal's hidden.bs.modal handler) can
    // dismiss it cleanly — including removing the keydown listener —
    // instead of just hiding the element and leaking the listener.
    let _activeConfirmClose = null;

    // Helper: race the printer-state probe against a short timeout so a slow
    // or unreachable PrusaLink can't stall the confirm UI. Returns stateInfo
    // (truthy → active) or null (unknown → no banner).
    const _probeWithTimeout = (toolheadId, timeoutMs = 1000) => {
        if (!toolheadId || !window.fetchPrinterStateForToolhead) return Promise.resolve(null);
        return Promise.race([
            window.fetchPrinterStateForToolhead(toolheadId),
            new Promise(resolve => setTimeout(() => resolve(null), timeoutMs)),
        ]).catch(() => null);
    };

    const showConfirmOverlay = async (opts) => {
        const ov = document.getElementById('fcc-quickswap-confirm-overlay');
        const title = document.getElementById('fcc-quickswap-confirm-title');
        const body = document.getElementById('fcc-quickswap-confirm-body');
        const yes = document.getElementById('fcc-quickswap-yes');
        const no = document.getElementById('fcc-quickswap-no');
        if (!ov || !yes || !no) return;
        // If there's a previous overlay still active (paranoia), tear it
        // down before replacing its handlers.
        if (_activeConfirmClose) {
            try { _activeConfirmClose(); } catch (e) { /* noop */ }
        }

        // Active-print probe must complete BEFORE the overlay becomes visible —
        // otherwise a fast-clicking user can confirm before the banner lands
        // (the async-append pattern we tried first lost that race). 1s cap
        // keeps the delay bounded when the printer is offline. The probe
        // fails open — null means "unknown, show overlay normally."
        const stateInfo = await _probeWithTimeout(opts.toolhead);
        const warningBanner = stateInfo
            ? `<div class="alert alert-warning py-2 px-3 mb-2" style="font-size:0.95em;">`
                + `⚠️ <b>${stateInfo.printer_name} is ${stateInfo.state}</b> — loading a new spool now will disrupt the print.`
                + `</div>`
            : '';

        title.innerText = opts.title || `Swap ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`;
        const defaultBody = 'This moves the spool currently in that slot into the active toolhead. ' +
                            'Any spool already on the toolhead will be auto-ejected back to its source.';
        body.innerHTML = warningBanner + (opts.body || defaultBody);
        ov.style.display = 'block';

        const close = () => {
            ov.style.display = 'none';
            yes.onclick = null; no.onclick = null;
            document.removeEventListener('keydown', keyHandler, true);
            if (_activeConfirmClose === close) _activeConfirmClose = null;
        };
        _activeConfirmClose = close;
        const keyHandler = (e) => {
            if (e.key === 'Escape') { e.stopPropagation(); close(); }
            else if (e.key === 'Enter') { e.stopPropagation(); opts.onConfirm && opts.onConfirm(); close(); }
        };
        yes.onclick = () => { opts.onConfirm && opts.onConfirm(); close(); };
        no.onclick = close;
        document.addEventListener('keydown', keyHandler, true);
        yes.focus();
    };

    // Public teardown for the manage modal to call on hide.
    window.closeQuickswapConfirm = () => {
        if (_activeConfirmClose) {
            try { _activeConfirmClose(); } catch (e) { /* noop */ }
        } else {
            const ov = document.getElementById('fcc-quickswap-confirm-overlay');
            if (ov) ov.style.display = 'none';
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

    const performSwap = (opts) => {
        fetch('/api/quickswap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(opts),
        })
            .then(async r => ({ ok: r.ok, body: await r.json() }))
            .then(({ ok, body }) => {
                if (window.maybeWarnFilabridge) window.maybeWarnFilabridge(body);
                if (ok && body.action === 'quickswap_done') {
                    showToast(`⚡ Spool #${body.moved} → ${opts.toolhead}`, 'success', 2500);
                    _refreshAfterMove();
                } else if (body.action === 'quickswap_empty_slot') {
                    showToast(`⚠️ ${opts.box} slot ${opts.slot} is empty — nothing to swap`, 'warning', 4000);
                } else if (body.action === 'quickswap_not_bound') {
                    showToast(`❌ Binding is stale — refresh and try again`, 'error', 5000);
                } else {
                    showToast(`❌ Quick-swap failed: ${body.error || body.action || 'unknown'}`, 'error', 5000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Quick-swap — network error', 'error', 5000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Quick-swap network error: ${e && e.message ? e.message : 'connection failed'}`,
                    'ERROR'
                );
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
                if (window.maybeWarnFilabridge) window.maybeWarnFilabridge(body);
                if (ok && body.action === 'return_done') {
                    showToast(`↩️ Spool #${body.moved} → ${body.box}:SLOT:${body.slot}`, 'success', 2500);
                    _refreshAfterMove();
                } else if (body.action === 'return_no_spool') {
                    showToast(`⚠️ ${opts.toolhead} is empty — nothing to return`, 'warning', 4000);
                } else if (body.action === 'return_no_binding') {
                    showToast(`⚠️ ${opts.toolhead} has no bound slot to return to`, 'warning', 4000);
                } else {
                    showToast(`❌ Return failed: ${body.error || body.action || 'unknown'}`, 'error', 5000);
                }
            })
            .catch(e => {
                console.error(e);
                showToast('Return — network error', 'error', 5000);
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
        const held = (state.heldSpools || []);
        const buffered = held[0];
        if (!buffered) {
            showToast('Buffer is empty — scan a spool first', 'warning', 3500);
            return;
        }
        const box = btn.dataset.box;
        const slot = btn.dataset.slot;
        const toolhead = btn.dataset.toolhead;
        const bsDisplay = buffered.display || `#${buffered.id}`;
        showConfirmOverlay({
            toolhead, box, slot,
            title: `Deposit ${bsDisplay} into ${box} slot ${slot}?`,
            body: `<div class="text-warning fw-bold mb-2" style="font-size:1rem;">Spool: ${bsDisplay}</div>` +
                `<div class="text-light" style="font-size:1.05rem;">` +
                `Drops it into <b>${box}:SLOT:${slot}</b>. Because this slot is bound to ` +
                `<b>${toolhead}</b>, it auto-deploys to the toolhead once placed. ` +
                `If ${toolhead} currently has another spool, that one returns to its own origin box first.</div>`,
            onConfirm: () => {
                fetch('/api/identify_scan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: `LOC:${box}:SLOT:${slot}`,
                        source: 'quickswap_deposit',
                    }),
                })
                    .then(async r => ({ ok: r.ok, body: await r.json() }))
                    .then(({ ok, body }) => {
                        if (ok && (body.action === 'assignment_done' || body.action === 'assignment_partial')) {
                            const destNote = body.auto_deployed_to
                                ? ` → ${body.auto_deployed_to}`
                                : '';
                            showToast(`⬇️ ${bsDisplay} → ${box}:SLOT:${slot}${destNote}`, 'success', 2500);
                            // Mirror backend's buffer mutation on the frontend
                            // so the user doesn't briefly see the old spool.
                            if (body.moved != null) {
                                state.heldSpools = (state.heldSpools || []).filter(s => s.id !== body.moved);
                                if (window.renderBuffer) window.renderBuffer();
                            }
                            _refreshAfterMove();
                        } else if (body.action === 'assignment_no_buffer') {
                            showToast('Buffer is empty — scan a spool first', 'warning', 3500);
                        } else {
                            showToast(`❌ Deposit failed: ${body.action || body.error || 'unknown'}`, 'error', 5000);
                        }
                    })
                    .catch(e => {
                        console.error(e);
                        showToast('Deposit — network error', 'error', 5000);
                        if (window.logClientEvent) window.logClientEvent(
                            `❌ Deposit network error: ${e && e.message ? e.message : 'connection failed'}`,
                            'ERROR'
                        );
                    });
            },
        });
    };

    window.quickSwapTap = (btn) => {
        if (!btn) return;
        // Disabled buttons (empty slot) should be a no-op.
        if (btn.hasAttribute('disabled')) {
            showToast(`⚠️ ${btn.dataset.box} slot ${btn.dataset.slot} is empty — nothing to swap`, 'warning', 4000);
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
        const labelEl = btn.querySelector('.fw-bold + .fw-bold, div.fw-bold:nth-child(2)');
        const spoolLabel = labelEl ? labelEl.innerText.trim() : '';
        // Active-print banner is handled inside showConfirmOverlay itself
        // now (covers all 4 call sites). No pre-probe wrapper here.
        showConfirmOverlay({
            ...opts,
            title: `Load ${opts.box} slot ${opts.slot} into ${opts.toolhead}?`,
            body: (spoolLabel
                    ? `<div class="text-warning fw-bold mb-2">Spool: ${spoolLabel}</div>`
                    : '')
                + 'This moves that spool onto <b>' + opts.toolhead + '</b>. '
                + 'Any spool currently on the toolhead gets auto-returned to <em>its own</em> origin box — '
                + 'never re-routed into a different dryer box.',
            onConfirm: () => performSwap(opts),
        });
    };

    // Resolve which concrete toolhead a Return-to-Slot click is actually
    // going to act on. For a specific toolhead loc (e.g. XL-3) it's that
    // loc. For a virtual-printer loc (e.g. XL / CORE1) we check each
    // candidate toolhead's contents and return the first one that's
    // loaded — which mirrors the backend's own selection logic.
    const _resolveReturnTarget = (loc) => {
        if (!loc) return Promise.resolve(null);
        const up = String(loc.LocationID).toUpperCase();
        if (loc.Type !== PRINTER_TYPE) {
            return Promise.resolve(up);
        }
        const pm = state.printerMap || {};
        const prefix = up + '-';
        const candidates = [];
        for (const entries of Object.values(pm)) {
            (entries || []).forEach(e => {
                const v = String(e.location_id).toUpperCase();
                if (v.startsWith(prefix)) candidates.push(v);
            });
        }
        if (!candidates.length) return Promise.resolve(null);
        // Check each candidate in printer_map order; first one with
        // contents wins.
        const check = (i) => {
            if (i >= candidates.length) return null;
            return fetch(`/api/get_contents?id=${encodeURIComponent(candidates[i])}`)
                .then(r => r.ok ? r.json() : [])
                .then(items => (items && items.length) ? candidates[i] : check(i + 1))
                .catch(() => check(i + 1));
        };
        return Promise.resolve(check(0));
    };

    // Resolve the exact (box, slot) the return WILL target so the user
    // isn't asked to confirm an abstract "physical_source." Mirrors the
    // backend's /api/quickswap/return priority: spool.extra.physical_source
    // first, first bound slot of the toolhead second.
    const _resolveReturnDestination = (toolheadId) => {
        const th = String(toolheadId || '').toUpperCase();
        if (!th) return Promise.resolve(null);
        return fetch(`/api/get_contents?id=${encodeURIComponent(th)}`)
            .then(r => r.ok ? r.json() : [])
            .then(items => {
                const resident = (items || [])[0] || null;
                // Preferred: the spool's own recorded source.
                const preferred = resident && resident.location
                    ? {
                        box: String(resident.location).toUpperCase(),
                        slot: String(resident.slot || '').replace(/"/g, '').trim() || null,
                        source: 'physical_source',
                        spoolId: resident.id,
                        display: resident.display,
                    }
                    : null;
                if (preferred && preferred.box && preferred.box !== th) {
                    // location on a ghost entry points back at its source
                    // box; that's what we want here.
                    return preferred;
                }
                // Fallback: first bound slot of this toolhead.
                return fetch('/api/dryer_boxes/slots').then(r => r.json()).then(body => {
                    for (const s of body.slots || []) {
                        if (s.target && String(s.target).toUpperCase() === th) {
                            return {
                                box: s.box, slot: s.slot,
                                source: 'first_binding',
                                spoolId: resident && resident.id,
                                display: resident && resident.display,
                            };
                        }
                    }
                    return null;
                });
            })
            .catch(() => null);
    };

    window.returnToolheadToSlot = () => {
        if (!currentLoc) return;
        const vth = String(currentLoc.LocationID).toUpperCase();
        _resolveReturnTarget(currentLoc).then(resolvedTh => {
            const th = resolvedTh || vth;
            const isVirtual = currentLoc.Type === PRINTER_TYPE;

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

            _resolveReturnDestination(th).then(dest => {
                const resolvedNote = (isVirtual && resolvedTh)
                    ? `<div class="text-warning small mb-2" style="font-size:0.95rem;">`
                      + `(Resolved from the <b>${vth}</b> virtual printer — first toolhead with a loaded spool.)</div>`
                    : '';

                let destLine;
                if (!dest) {
                    destLine = `<div class="text-warning fw-bold mb-2" style="font-size:1.05rem;">`
                        + `<b>${th}</b> has no recorded source and no bound dryer box slot — nothing to return to.</div>`;
                } else {
                    const slotPart = dest.slot ? ` slot ${dest.slot}` : '';
                    const spoolLine = dest.spoolId
                        ? `<div class="text-light mb-2" style="font-size:1rem;">Spool: <b>${dest.display || ('#' + dest.spoolId)}</b></div>`
                        : '';
                    const sourceTag = dest.source === 'physical_source'
                        ? `<span class="text-success fw-bold">(original source)</span>`
                        : `<span class="text-warning fw-bold">(first bound slot — the spool has no recorded origin)</span>`;
                    destLine = spoolLine
                        + `<div class="text-light" style="font-size:1.05rem;">`
                        + `Sending back to: <span class="text-info fw-bold">${dest.box}${slotPart}</span> ${sourceTag}</div>`;
                }

                showConfirmOverlay({
                    toolhead: th,
                    title: `Return the spool on ${th}?`,
                    body: resolvedNote + destLine,
                    onConfirm: dest ? (() => performReturn({ toolhead: th })) : (() => { /* no-op */ }),
                });
            });
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
                showToast('Could not load dryer box slots', 'error', 5000);
                if (window.logClientEvent) window.logClientEvent(
                    `❌ Bind picker failed to load dryer box slots: ${e && e.message ? e.message : 'fetch failed'}`,
                    'ERROR'
                );
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

    // Keep empty-slot buttons in sync with buffer state — the "Deposit
    // from buffer" affordance only makes sense while a spool is held.
    document.addEventListener('inventory:buffer-updated', () => {
        if (currentLoc && window.renderQuickSwapSection) {
            window.renderQuickSwapSection(currentLoc);
        }
    });
})();
