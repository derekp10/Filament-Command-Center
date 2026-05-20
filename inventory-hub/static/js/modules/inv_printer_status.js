// ---------------------------------------------------------------------------
// Printer Status Widget (Group 9.3)
//
// At-a-glance dashboard panel: one row per printer that has at least one
// bound toolhead. Each row shows a stylized schematic — color-tinted
// "toolhead blocks" with horizontal remaining-weight bars and a low-stock
// color cue (amber <100g, red ≤0g). Clicking a block opens the Location
// Manager focused on that toolhead (Quick-Swap is one click away).
//
// Read-only. Refreshes piggyback on `inventory:sync-pulse` so we never
// poll independently — same cadence as the buffer / search results.
//
// Project Color Loadout (L330) is the eventual richer view; this widget
// is V1 and intentionally avoids per-printer artwork. When Loadout lands,
// it can swap in printer photos with positioned overlays without changing
// the underlying aggregation surface.
// ---------------------------------------------------------------------------

(function () {
    const STORAGE_KEY = 'fcc.printerStatus.collapsed';
    const ORDER_KEY = 'fcc.printerStatus.order';
    const REFRESH_DEBOUNCE_MS = 250;

    const _state = {
        printers: null,       // cached printer_map
        rowsByPrinter: {},    // {printerName: {toolheads: [{id, position, item|null}]}}
        refreshTimer: null,
        inFlight: false,
        lastFingerprint: null,
    };

    const _isCollapsed = () => {
        try { return localStorage.getItem(STORAGE_KEY) === '1'; }
        catch (e) { return false; }
    };
    const _setCollapsed = (val) => {
        try { localStorage.setItem(STORAGE_KEY, val ? '1' : '0'); }
        catch (e) { /* private mode — ignore */ }
    };

    // User-managed printer ordering for the widget. Until the Config
    // system lands (Feature-Buglist L18), persisted client-side under
    // `fcc.printerStatus.order` as a JSON array of printer names. Names
    // not in the saved order land at the end (alphabetical fallback) so
    // newly-added printers don't disappear.
    const _loadOrder = () => {
        try {
            const raw = localStorage.getItem(ORDER_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed.filter(s => typeof s === 'string') : [];
        } catch (e) { return []; }
    };
    const _saveOrder = (arr) => {
        try { localStorage.setItem(ORDER_KEY, JSON.stringify(arr)); }
        catch (e) { /* noop */ }
    };
    const _sortedPrinterNames = (names) => {
        const saved = _loadOrder();
        const known = saved.filter(n => names.includes(n));
        const unknown = names.filter(n => !known.includes(n)).sort();
        return [...known, ...unknown];
    };
    const _movePrinter = (name, direction) => {
        const order = _sortedPrinterNames(Object.keys(_state.rowsByPrinter));
        const idx = order.indexOf(name);
        if (idx === -1) return;
        const swap = idx + direction;
        if (swap < 0 || swap >= order.length) return;
        [order[idx], order[swap]] = [order[swap], order[idx]];
        _saveOrder(order);
        _state.lastFingerprint = null;  // force re-render even if data unchanged
        _render(_state.rowsByPrinter);
    };
    window.movePrinterStatusRow = _movePrinter;

    // Fetch printer_map → for each printer, fetch its bindings → for each
    // toolhead, fetch its current contents. Returns a map keyed by printer
    // name. Aggregation lives here (not in inv_quickswap.js) so 9.1, 9.2,
    // and the widget all share one path.
    const _aggregate = async () => {
        let pmBody;
        try {
            const r = await fetch('/api/printer_map');
            pmBody = await r.json();
        } catch (e) {
            return {};
        }
        const printers = pmBody.printers || {};
        const out = {};
        await Promise.all(Object.entries(printers).map(async ([name, entries]) => {
            // Per-printer bindings (also exposes printer_pool for future use).
            let bindings;
            try {
                const r = await fetch(`/api/machine/${encodeURIComponent(name)}/toolhead_slots`);
                bindings = r.ok ? await r.json() : { toolheads: {} };
            } catch (e) {
                bindings = { toolheads: {} };
            }
            const toolheadIds = (entries || [])
                .slice()
                .sort((a, b) => (a.position || 0) - (b.position || 0))
                .map(e => ({ id: String(e.location_id).toUpperCase(), position: e.position || 0 }));
            // L140 fix: previously skipped any printer with zero bound source
            // slots — that hid Core One on prod entirely because Derek
            // hadn't wired any dryer-box slot_targets to CORE1-M*. Show
            // every registered printer now; flag unbound toolheads with
            // an `unbound: true` marker so the renderer can show a
            // "no bound slots yet" placeholder instead of a spool tile.
            // Bound toolheads still render with current contents; the
            // mix is fine (printer can be partially bound).
            const bound = toolheadIds.filter(th => (bindings.toolheads[th.id] || []).length > 0);
            const unbound = toolheadIds.filter(th => !((bindings.toolheads[th.id] || []).length > 0));
            // Resolve current contents of each bound toolhead.
            const filled = await Promise.all(bound.map(async th => {
                try {
                    const r = await fetch(`/api/get_contents?id=${encodeURIComponent(th.id)}`);
                    const items = r.ok ? await r.json() : [];
                    return { ...th, item: (items || [])[0] || null };
                } catch (e) {
                    return { ...th, item: null };
                }
            }));
            const unboundEntries = unbound.map(th => ({ ...th, item: null, unbound: true }));
            // Merge + re-sort by position so the visual order matches
            // printer layout regardless of bound/unbound mix.
            const allRows = [...filled, ...unboundEntries].sort((a, b) => (a.position || 0) - (b.position || 0));
            out[name] = { toolheads: allRows };
        }));
        return out;
    };

    // Fingerprint of the aggregation result so refresh can skip rerendering
    // identical state — keeps a tight sync-pulse cadence cheap.
    const _fingerprint = (rows) => {
        const parts = [];
        Object.entries(rows).sort().forEach(([name, info]) => {
            const stateFp = info.state === null ? 'offline'
                : info.state ? String(info.state.state || '') : '';
            parts.push(name + '@' + stateFp + '|' + info.toolheads.map(th => {
                const it = th.item;
                return th.id + ':' + (it ? `${it.id}:${it.color || ''}:${Math.round(it.remaining_weight || 0)}` : 'empty');
            }).join(','));
        });
        return parts.join('||');
    };

    // Map each toolhead to its remaining-weight palette in one place so
    // the expanded block, collapsed mini chip, and any future surface all
    // agree on what counts as low-stock.
    const _weightPalette = (weight) => {
        if (weight <= 0) return '#ff6b6b';
        if (weight < 100) return '#ffc107';
        return '#0dcaf0';
    };

    const _renderToolheadBlock = (th) => {
        const it = th.item;
        const positionAttr = `data-toolhead="${th.id}"`;
        // L140 fix — unbound toolheads (no dryer-box slot_targets points
        // at them) render with a distinct "no bound slots" placeholder
        // instead of being hidden, so the printer is visible on the
        // dashboard with an actionable hint instead of mysteriously
        // missing. Clicking still opens the toolhead in the Location
        // Manager so the user can either bind a slot or quick-swap.
        if (th.unbound) {
            return `
                <div class="fcc-ps-th fcc-ps-th-unbound" ${positionAttr}
                     style="cursor:pointer; border:1px dashed #ffd54a;"
                     title="${th.id} — no dryer-box slot is bound to this toolhead. Bind one in the Location Manager → Feeds editor for a dryer box.">
                    <div class="fcc-ps-th-bar"><div class="fcc-ps-th-bar-fill" style="width:0%;"></div></div>
                    <div class="fcc-ps-th-body fcc-ps-th-body-empty">
                        <div class="fcc-ps-th-id text-truncate">${th.id}</div>
                    </div>
                    <div class="fcc-ps-th-chip" style="font-size:0.72rem; color:#ffd54a;">🔗 no bound slot</div>
                </div>
            `;
        }
        if (!it) {
            // No text-muted here — Bootstrap's text-muted (#6c757d) sits
            // at ~1.4:1 against our dark widget bg. Use an explicit light
            // gray that meets WCAG AA. Pinned by test_contrast_guard.
            return `
                <div class="fcc-ps-th fcc-ps-th-empty" ${positionAttr}
                     style="cursor:pointer;"
                     title="${th.id} — empty">
                    <div class="fcc-ps-th-bar"><div class="fcc-ps-th-bar-fill" style="width:0%;"></div></div>
                    <div class="fcc-ps-th-body fcc-ps-th-body-empty">
                        <div class="fcc-ps-th-id text-truncate">${th.id}</div>
                    </div>
                    <div class="fcc-ps-th-chip" style="font-size:0.78rem; color: rgba(255,255,255,0.65);">empty</div>
                </div>
            `;
        }
        // Use getFilamentStyle's frame gradient so multi-color filaments
        // (CSV / coaxial) render properly across the body block instead
        // of just showing the first component color.
        let bodyBg;
        try {
            bodyBg = window.getFilamentStyle(it.color, it.color_direction || 'longitudinal').frame;
        } catch (e) {
            bodyBg = '#555555';
        }
        const weight = (it.remaining_weight !== undefined && it.remaining_weight !== null)
            ? Number(it.remaining_weight) : 0;
        // 1000g = full bar; widget caps at 100% so heavier spools just stay full.
        const pct = Math.max(0, Math.min(100, (weight / 1000) * 100));
        const barColor = _weightPalette(weight);
        const chipHtml = window.SpoolCardBuilder
            ? window.SpoolCardBuilder.buildCard(it, 'printer-status', {})
            : `<div class="fcc-ps-th-chip text-light">${weight}g</div>`;
        return `
            <div class="fcc-ps-th" ${positionAttr}
                 data-spool-id="${it.id}"
                 style="cursor:pointer;"
                 title="${th.id} — ${(it.display || `#${it.id}`).replace(/"/g, '&quot;')} — ${Math.round(weight)}g remaining (click to Quick-Swap)">
                <div class="fcc-ps-th-bar">
                    <div class="fcc-ps-th-bar-fill" style="width:${pct}%; background:${barColor};"></div>
                </div>
                <div class="fcc-ps-th-body" style="background:${bodyBg};">
                    <div class="fcc-ps-th-id text-truncate">${th.id}</div>
                </div>
                ${chipHtml}
            </div>
        `;
    };

    // Collapsed-mode chip: super-compact one-liner per toolhead with just
    // the swatch + ID + weight. Same click target as the full block so the
    // collapsed view is fully interactive. Routes the swatch through
    // makeSwatchHtml so multi-color filaments render as gradients (not
    // gray fallback) and contrast is consistent with all other chips.
    const _renderToolheadCompact = (th) => {
        const it = th.item;
        if (th.unbound) {
            // L140 fix companion — collapsed-mode chip for unbound toolheads.
            return `<span class="fcc-ps-mini fcc-ps-mini-empty"
                          data-toolhead="${th.id}"
                          style="border:1px dashed #ffd54a;"
                          title="${th.id} — no dryer-box slot bound (bind one in the Location Manager)">
                <span class="fcc-ps-mini-swatch fcc-ps-mini-swatch-empty"></span>
                <span class="fcc-ps-mini-id">${th.id}</span>
                <span class="fcc-ps-mini-weight" style="color:#ffd54a;">🔗</span>
            </span>`;
        }
        if (!it) {
            // "empty" text uses an explicit light color (not Bootstrap's
            // text-muted, which sits at ~#6c757d and disappears against
            // the dark widget background — recurring contrast pitfall).
            return `<span class="fcc-ps-mini fcc-ps-mini-empty"
                          data-toolhead="${th.id}"
                          title="${th.id} — empty">
                <span class="fcc-ps-mini-swatch fcc-ps-mini-swatch-empty"></span>
                <span class="fcc-ps-mini-id">${th.id}</span>
                <span class="fcc-ps-mini-weight" style="color: rgba(255,255,255,0.65);">empty</span>
            </span>`;
        }
        const swatch = window.makeSwatchHtml(it.color, it.color_direction, {
            size: 16,
            borderColor: 'rgba(255,255,255,0.5)',
            marginRight: 0,
        });
        const weight = (it.remaining_weight !== undefined && it.remaining_weight !== null)
            ? Number(it.remaining_weight) : 0;
        const wColor = _weightPalette(weight);
        const safeDisplay = (it.display || `#${it.id}`).replace(/"/g, '&quot;');
        return `<span class="fcc-ps-mini"
                      data-toolhead="${th.id}"
                      title="${th.id} — ${safeDisplay} — ${Math.round(weight)}g (click to Quick-Swap)">
            ${swatch}
            <span class="fcc-ps-mini-id">${th.id}</span>
            <span class="fcc-ps-mini-weight" style="color:${wColor};">${Math.round(weight)}g</span>
        </span>`;
    };

    // L56 — printer-state badge. Direct PrusaLink read (no dryer-box
    // dependency), so this renders for Core One in direct-feed setups
    // where the toolhead weight only ticks after FilaBridge auto-deduct
    // (which needs the dryer-box-mediated mapping). state === null means
    // the printer didn't answer; show "OFFLINE" so the user can tell
    // it's a probe failure vs. an actual idle printer.
    const _renderStateBadge = (state) => {
        if (state === undefined) return '';
        if (state === null) {
            return `<span class="fcc-ps-state fcc-ps-state-offline" title="Printer unreachable (offline, networked elsewhere, or cold-rebooting)">OFFLINE</span>`;
        }
        const raw = String(state.state || '').toUpperCase();
        if (!raw) return '';
        const isActive = !!state.is_active;
        // PRINTING/PAUSING/RESUMING → active (green-pop)
        // PAUSED → paused (amber)
        // FINISHED/STOPPED/IDLE/READY/OPERATIONAL → idle (muted)
        // anything else (BUSY, ATTENTION, ERROR) → attention (red)
        let cls = 'fcc-ps-state-idle';
        if (isActive) cls = 'fcc-ps-state-printing';
        else if (raw === 'PAUSED') cls = 'fcc-ps-state-paused';
        else if (['IDLE', 'READY', 'OPERATIONAL', 'FINISHED', 'STOPPED'].includes(raw)) cls = 'fcc-ps-state-idle';
        else cls = 'fcc-ps-state-attention';
        return `<span class="fcc-ps-state ${cls}" title="PrusaLink reports: ${raw}">${raw}</span>`;
    };

    const _renderRow = (name, info, idx, total) => {
        const safeName = name.replace(/"/g, '&quot;').replace(/'/g, "\\'");
        const upBtn = idx > 0
            ? `<button type="button" class="fcc-ps-reorder" title="Move up"
                    onclick="event.stopPropagation(); window.movePrinterStatusRow('${safeName}', -1)">▲</button>`
            : `<span class="fcc-ps-reorder-placeholder"></span>`;
        const downBtn = idx < total - 1
            ? `<button type="button" class="fcc-ps-reorder" title="Move down"
                    onclick="event.stopPropagation(); window.movePrinterStatusRow('${safeName}', 1)">▼</button>`
            : `<span class="fcc-ps-reorder-placeholder"></span>`;
        const stateBadge = _renderStateBadge(info.state);
        // Per-printer expanded row. The collapsed view is now a single
        // chip strip in the widget header (rendered separately in _render),
        // not per-row, so we don't include compact chips here anymore.
        return `
            <div class="fcc-ps-row" data-printer="${safeName}">
                <div class="fcc-ps-name-col d-flex align-items-center">
                    <div class="fcc-ps-reorder-stack d-flex flex-column">
                        ${upBtn}
                        ${downBtn}
                    </div>
                    <div class="fcc-ps-name-stack d-flex flex-column ms-2">
                        <div class="fcc-ps-name text-info fw-bold">${name}</div>
                        ${stateBadge}
                    </div>
                </div>
                <div class="fcc-ps-toolheads d-flex gap-2 flex-wrap">
                    ${info.toolheads.map(_renderToolheadBlock).join('')}
                </div>
            </div>
        `;
    };

    const _render = (rows) => {
        const widget = document.getElementById('printer-status-widget');
        if (!widget) return;
        const body = widget.querySelector('.fcc-ps-body');
        if (!body) return;
        // First successful render clears the loading skeleton class — the
        // widget transitions from "Loading…" placeholder to real content.
        widget.classList.remove('fcc-ps-loading');
        const printerNames = _sortedPrinterNames(Object.keys(rows));
        if (!printerNames.length) {
            // Hide the entire widget when no printers have bound toolheads
            // — the widget is opt-in by configuration, not a permanent
            // dashboard fixture.
            widget.style.display = 'none';
            return;
        }
        widget.style.display = '';
        body.innerHTML = printerNames
            .map((name, idx) => _renderRow(name, rows[name], idx, printerNames.length))
            .join('');
        // Header chip strip — every toolhead from every printer in the
        // user's printer order. Each printer's chips are wrapped in a
        // group div so CSS can add a vertical divider between groups,
        // making it clear at a glance which chips belong to which printer.
        const headerChips = widget.querySelector('.fcc-ps-header-chips');
        if (headerChips) {
            headerChips.innerHTML = printerNames.map(name => {
                const safeName = name.replace(/"/g, '&quot;');
                const chips = rows[name].toolheads.map(_renderToolheadCompact).join('');
                return `<div class="fcc-ps-printer-group" data-printer="${safeName}">${chips}</div>`;
            }).join('');
        }
        // Wire clicks AFTER innerHTML so listeners attach to the new DOM.
        // Same handler for expanded blocks AND header chips — both
        // open Quick-Swap on the toolhead.
        widget.querySelectorAll('.fcc-ps-th, .fcc-ps-mini').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const tid = el.dataset.toolhead;
                if (tid && window.openManage) window.openManage(tid);
            });
        });
    };

    const refresh = async () => {
        if (_state.inFlight) return;
        _state.inFlight = true;
        try {
            const rows = await _aggregate();
            // L56 — preserve printer `state` from the last bulk-pulse render
            // (refreshFromAggregate), since the per-printer fan-out here
            // doesn't include it. Without this merge, every sync-pulse
            // event would briefly wipe the PRINTING / IDLE / OFFLINE
            // badge by overriding the bulk-pulse data with stateless rows.
            Object.keys(rows).forEach(name => {
                const cached = _state.rowsByPrinter[name];
                if (cached && cached.state !== undefined && rows[name].state === undefined) {
                    rows[name].state = cached.state;
                }
            });
            _state.rowsByPrinter = rows;
            const fp = _fingerprint(rows);
            if (fp === _state.lastFingerprint) return;  // unchanged, skip render
            _state.lastFingerprint = fp;
            // Always render — CSS handles which form (expanded vs compact)
            // is visible based on the widget's `.collapsed` class.
            _render(rows);
        } finally {
            _state.inFlight = false;
        }
    };

    // Debounced wrapper — sync-pulse can fire multiple events per scan.
    const scheduleRefresh = () => {
        if (_state.refreshTimer) return;
        _state.refreshTimer = setTimeout(() => {
            _state.refreshTimer = null;
            refresh();
        }, REFRESH_DEBOUNCE_MS);
    };

    const _renderShell = () => {
        const widget = document.getElementById('printer-status-widget');
        if (!widget) return;
        const collapsed = _isCollapsed();
        widget.classList.toggle('collapsed', collapsed);
        const toggle = widget.querySelector('.fcc-ps-toggle');
        if (toggle) toggle.textContent = collapsed ? '▸' : '▾';
        // Body stays in the DOM — CSS swaps between expanded blocks and
        // collapsed mini chips. Hiding the body would defeat the
        // "super-truncated view when collapsed" contract.
    };

    window.togglePrinterStatusWidget = () => {
        _setCollapsed(!_isCollapsed());
        _renderShell();
    };

    document.addEventListener('inventory:sync-pulse', scheduleRefresh);
    document.addEventListener('inventory:locations-changed', scheduleRefresh);
    document.addEventListener('DOMContentLoaded', () => {
        _renderShell();
        // Fetch immediately — the widget's "Loading printer status…"
        // skeleton in dashboard.html holds the layout space, so the
        // populated render replaces the placeholder rather than the
        // whole widget popping in. No initial delay needed.
        refresh();
    });

    // L206 bulk-pulse hook: render from a pre-fetched aggregate without
    // hitting the per-printer fan-out. Same fingerprint/wiggle protection
    // as refresh(). Called by startSmartSync's dashboard_pulse dispatcher
    // when the response includes a printer_status section.
    const refreshFromAggregate = (rows) => {
        if (!rows || typeof rows !== 'object') return;
        _state.rowsByPrinter = rows;
        const fp = _fingerprint(rows);
        if (fp === _state.lastFingerprint) return;
        _state.lastFingerprint = fp;
        _render(rows);
    };
    window.refreshPrinterStatusWidgetFromAggregate = refreshFromAggregate;

    // Exposed for tests + manual debugging.
    window.refreshPrinterStatusWidget = refresh;
})();
