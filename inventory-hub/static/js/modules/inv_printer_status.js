// ---------------------------------------------------------------------------
// Printer Status Widget (Group 9.3)
//
// At-a-glance dashboard panel: one row per printer that has at least one
// bound toolhead. Each row shows a stylized schematic — color-tinted
// "toolhead blocks" with horizontal remaining-weight bars and a low-stock
// color cue (amber <100g, red ≤0g). Clicking a block opens the Location
// Manager focused on that toolhead (Quick-Swap is one click away).
//
// Read-only. Never polls on its own: the dashboard heartbeat's printer_status
// section feeds it (refreshFromAggregate), and the client fan-out (refresh)
// runs only when something else changed, or as the fallback when a heartbeat
// came back without that section (Group 45.8).
//
// Project Color Loadout (L330) is the eventual richer view; this widget
// is V1 and intentionally avoids per-printer artwork. When Loadout lands,
// it can swap in printer photos with positioned overlays without changing
// the underlying aggregation surface.
// ---------------------------------------------------------------------------

(function () {
    const STORAGE_KEY = 'fcc.printerStatus.collapsed';
    const ORDER_KEY = 'fcc.printerStatus.order';
    const LABEL_KEY = 'fcc.printerStatus.toolheadLabel';
    const REFRESH_DEBOUNCE_MS = 250;
    // If nothing has rendered this long after load (the heartbeat keeps
    // failing), fetch once the old way so the widget doesn't sit on its
    // skeleton. Long enough that a merely SLOW first heartbeat on a loaded
    // machine doesn't add the very fan-out Group 45.8 removed.
    const LOAD_FALLBACK_MS = 15000;

    const _state = {
        printers: null,       // cached printer_map
        rowsByPrinter: {},    // {printerName: {toolheads: [{id, position, item|null}]}}
        refreshTimer: null,
        inFlight: false,
        lastFingerprint: null,
        pulseFed: false,      // the current heartbeat tick carried printer_status
        localAt: 0,           // last refresh asked for by a local change (ms)
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
            // Box-bounding fix (mirrors the backend _pulse_section_printer_status
            // change): resolve EVERY toolhead's contents, not just dryer-box-bound
            // ones. `unbound` is a pure binding hint — a directly-fed toolhead with
            // no bound slot must still surface the spool loaded on it (Core One's
            // direct-feed setup). The renderer prefers the spool over the
            // "🔗 no bound slot" placeholder when an item is present.
            // (L140 origin: this fan-out used to skip whole printers with zero
            // bound slots, hiding Core One entirely; that filter is long gone —
            // now even the per-toolhead contents fetch is binding-independent.)
            const allRows = await Promise.all(toolheadIds.map(async th => {
                const unbound = !((bindings.toolheads[th.id] || []).length > 0);
                let item = null;
                let loaded = [];
                let unread = false;
                try {
                    // reads-1: a STRICT read, so a Spoolman blip is the route's
                    // 502, never [] drawn as an empty head: the head is marked
                    // `unread` and keeps its last tile (_keepLastTiles).
                    const r = await fetch(`/api/get_contents?id=${encodeURIComponent(th.id)}&strict=1`);
                    const items = r.ok ? await r.json() : null;
                    if (Array.isArray(items)) {
                        // Group 42.4 (mirrors the pulse): the loaded spool, never a
                        // ghost while one exists; a doubled head carries both ids.
                        loaded = items.filter(i => !i.is_ghost);
                        item = loaded[0] || items[0] || null;
                    } else {
                        unread = true;
                    }
                } catch (e) {
                    unread = true;
                }
                const out = { ...th, item, unbound, loaded_count: loaded.length };
                if (loaded.length > 1) out.loaded_ids = loaded.map(i => i.id);
                if (unread) out.unread = true;
                return out;
            }));
            // Re-sort by position so the visual order matches printer layout.
            allRows.sort((a, b) => (a.position || 0) - (b.position || 0));
            out[name] = { toolheads: allRows };
        }));
        return out;
    };

    // Group 46.3 — how a toolhead tile is labelled (Settings → This Browser): its
    // full id (XL-3, the default), just its number (3), or "Tool 3". The number is
    // the head's position + 1: positions count from 0, the printer's own screen
    // and the Feeds/Quick-Swap pickers count from 1. Visible text only: the
    // data-toolhead attribute and the tooltips keep the full id, and the collapsed
    // strip keeps it too, because it puts every printer's heads side by side
    // (XL's and the INDX's first heads would both read "1").
    const _labelMode = () => {
        try { return localStorage.getItem(LABEL_KEY) || 'XL-3'; }
        catch (e) { return 'XL-3'; }
    };
    const _thLabel = (th) => {
        const mode = _labelMode();
        const n = Number(th.position);
        if (!Number.isFinite(n)) return th.id;
        if (mode === '3') return String(n + 1);
        if (mode === 'Tool 3') return `Tool ${n + 1}`;
        return th.id;
    };

    // Fingerprint of the aggregation result so refresh can skip rerendering
    // identical state — keeps a tight sync-pulse cadence cheap. The label mode
    // is part of it, so changing it in Settings repaints on the next pulse.
    const _fingerprint = (rows) => {
        const parts = ['label=' + _labelMode()];
        Object.entries(rows).sort().forEach(([name, info]) => {
            const stateFp = info.state === null ? 'offline'
                : info.state ? String(info.state.state || '') : '';
            parts.push(name + '@' + stateFp + '|' + info.toolheads.map(th => {
                const it = th.item;
                // Include the unbound flag so binding a/unbinding a slot while a
                // spool stays loaded still re-renders the 🔗 hint (occupancy no
                // longer toggles with binding now that contents are ungated).
                // 24.K — include rounded initial_weight so a correction that
                // changes the bar's denominator (e.g. an L200 weight fix) still
                // re-renders even if remaining happens to round the same.
                // 30.4 — include material so a material-only change (e.g. a
                // material correction, or a same-color/same-weight swap) still
                // repaints the new material line.
                // 42.4: a second loaded spool appearing or leaving repaints the chip.
                // reads-1: "? not read" and "empty" are different tiles.
                return th.id + (th.unbound ? '!u' : '') + (th.unread ? '!r' : '') + ((th.loaded_count || 0) > 1 ? `!n${th.loaded_count}` : '') + ':' + (it ? `${it.id}:${it.color || ''}:${(it.details && it.details.material) || ''}:${Math.round(it.remaining_weight || 0)}/${Math.round(it.initial_weight || 0)}` : 'empty');
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

    // Group 42.4 — a toolhead holds one spool (Derek: "If looking at the
    // toolhead, I should only ever see one in there"). When FCC's records put
    // two loaded spools on a head, the tile shows the first and says so. The
    // background is OPAQUE: the contrast guard mis-reads translucent ones. The
    // hover text uses the full head id whatever the label setting (call 23).
    const _doubledText = (th) => {
        const ids = (th.loaded_ids || []).map(i => `#${i}`);
        const who = ids.length > 2 ? `${ids.slice(0, -1).join(', ')} and ${ids[ids.length - 1]}` : ids.join(' and ');
        return `${th.id} holds ${who} — a toolhead holds one spool. Open ${th.id} and eject the one that isn't loaded.`;
    };
    const _doubledChip = (th) => ((th.loaded_count || 0) > 1
        ? `<div class="fcc-ps-th-chip fcc-ps-th-doubled" style="color:#ffd54a; background:#2b2200; border-radius:4px; padding:0 4px;" title="${_doubledText(th).replace(/"/g, '&quot;')}">⚠️ ${th.loaded_count} spools</div>`
        : '');
    window.fccDoubledHeadText = _doubledText;

    const _renderToolheadBlock = (th) => {
        const it = th.item;
        const positionAttr = `data-toolhead="${th.id}"`;
        if (th.unread && !it) {
            // reads-1: Spoolman didn't answer and FCC has no earlier answer for
            // this head, so it doesn't know what is loaded: "? not read", never
            // "empty" (and never the unbound placeholder, which reads as empty).
            return `
                <div class="fcc-ps-th fcc-ps-th-unread" ${positionAttr}
                     style="cursor:pointer;"
                     title="${th.id} — Spoolman didn't answer, so FCC couldn't check what is loaded here. It tries again every few seconds.">
                    <div class="fcc-ps-th-bar"><div class="fcc-ps-th-bar-fill" style="width:0%;"></div></div>
                    <div class="fcc-ps-th-body fcc-ps-th-body-empty">
                        <div class="fcc-ps-th-id text-truncate">${_thLabel(th)}</div>
                    </div>
                    <div class="fcc-ps-th-chip" style="color:#ffd54a;">? not read</div>
                </div>
            `;
        }
        // L140 fix — unbound toolheads (no dryer-box slot_targets points
        // at them) render with a distinct "no bound slots" placeholder
        // instead of being hidden, so the printer is visible on the
        // dashboard with an actionable hint instead of mysteriously
        // missing. Clicking still opens the toolhead in the Location
        // Manager so the user can either bind a slot or quick-swap.
        if (th.unbound && !it) {
            // Unbound AND empty → the L140 "no bound slot" placeholder. (An
            // unbound toolhead that DOES hold a spool falls through to the
            // occupied tile below — the box-bounding fix: occupancy is no
            // longer masked by the absence of a dryer-box binding.)
            return `
                <div class="fcc-ps-th fcc-ps-th-unbound" ${positionAttr}
                     style="cursor:pointer; border:1px dashed #ffd54a;"
                     title="${th.id} — no dryer-box slot is bound to this toolhead. Bind one in the Location Manager → Feeds editor for a dryer box.">
                    <div class="fcc-ps-th-bar"><div class="fcc-ps-th-bar-fill" style="width:0%;"></div></div>
                    <div class="fcc-ps-th-body fcc-ps-th-body-empty">
                        <div class="fcc-ps-th-id text-truncate">${_thLabel(th)}</div>
                    </div>
                    <div class="fcc-ps-th-chip" style="color:#ffd54a;">🔗 no bound slot</div>
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
                        <div class="fcc-ps-th-id text-truncate">${_thLabel(th)}</div>
                    </div>
                    <div class="fcc-ps-th-chip" style="color: rgba(255,255,255,0.65);">empty</div>
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
        // 24.K — scale the bar to the spool's OWN initial_weight (a 500g spool
        // full at 500g should read 100%, not 50%). Fall back to 1000g when
        // initial_weight is missing / zero / invalid so behavior is unchanged
        // for spools without it. The 100% cap keeps an over-measured spool
        // (remaining > initial) from overflowing the bar.
        const initial = (it.initial_weight !== undefined && it.initial_weight !== null && Number(it.initial_weight) > 0)
            ? Number(it.initial_weight) : 1000;
        const pct = Math.max(0, Math.min(100, (weight / initial) * 100));
        const barColor = _weightPalette(weight);
        const chipHtml = window.SpoolCardBuilder
            ? window.SpoolCardBuilder.buildCard(it, 'printer-status', {})
            : `<div class="fcc-ps-th-chip text-light">${weight}g</div>`;
        // A loaded toolhead that ALSO has no dryer-box slot bound keeps the
        // dashed accent + a 🔗 hint (preserves L140 discoverability) WHILE
        // showing its real spool. The 🔗 chip sits on the dark tile area
        // (not the colored body), so AA contrast holds — same #ffd54a the
        // empty-placeholder uses and the contrast guard already accepts.
        const unboundCls = th.unbound ? ' fcc-ps-th-unbound' : '';
        const unboundBorder = th.unbound ? ' border:1px dashed #ffd54a;' : '';
        const unboundHint = th.unbound
            ? `<div class="fcc-ps-th-chip" style="color:#ffd54a;" title="No dryer-box slot is bound to this toolhead. Auto-deduct still works (it follows the toolhead); bind a slot in the Location Manager → Feeds editor to also track it as box-fed.">🔗 no bound slot</div>`
            : '';
        return `
            <div class="fcc-ps-th${unboundCls}" ${positionAttr}
                 data-spool-id="${it.id}"
                 style="cursor:pointer;${unboundBorder}"
                 title="${th.id} — ${(it.display || `#${it.id}`).replace(/"/g, '&quot;')} — ${Math.round(weight)}g remaining (click to Quick-Swap)">
                <div class="fcc-ps-th-bar">
                    <div class="fcc-ps-th-bar-fill" style="width:${pct}%; background:${barColor};"></div>
                </div>
                <div class="fcc-ps-th-body" style="background:${bodyBg};">
                    <div class="fcc-ps-th-id text-truncate">${_thLabel(th)}</div>
                </div>
                ${chipHtml}
                ${unboundHint}
                ${_doubledChip(th)}
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
        if (th.unread && !it) {
            // reads-1: the collapsed form of "? not read" (see _renderToolheadBlock).
            return `<span class="fcc-ps-mini fcc-ps-mini-empty fcc-ps-mini-unread"
                          data-toolhead="${th.id}"
                          title="${th.id} — Spoolman didn't answer, so FCC couldn't check what is loaded here">
                <span class="fcc-ps-mini-swatch fcc-ps-mini-swatch-empty"></span>
                <span class="fcc-ps-mini-id">${th.id}</span>
                <span class="fcc-ps-mini-weight" style="color:#ffd54a;">? not read</span>
            </span>`;
        }
        if (th.unbound && !it) {
            // L140 companion — collapsed-mode placeholder for unbound AND empty
            // toolheads. An unbound toolhead that holds a spool falls through to
            // the occupied chip below (box-bounding fix).
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
        // Occupied chip; if the toolhead is also unbound, keep the dashed
        // accent + a trailing 🔗 hint while still showing the swatch + weight.
        const unboundMiniCls = th.unbound ? ' fcc-ps-mini-unbound' : '';
        const unboundMiniBorder = th.unbound ? 'border:1px dashed #ffd54a;' : '';
        const unboundMiniHint = (th.unbound
            ? ` <span class="fcc-ps-mini-unbound-hint" style="color:#ffd54a;" title="No dryer-box slot bound (auto-deduct still follows the toolhead)">🔗</span>`
            : '')
            // Group 42.4: the doubled-head warning, compact.
            + ((th.loaded_count || 0) > 1
                ? ` <span class="fcc-ps-mini-doubled" style="color:#ffd54a; background:#2b2200;" title="${_doubledText(th).replace(/"/g, '&quot;')}">⚠️${th.loaded_count}</span>`
                : '');
        return `<span class="fcc-ps-mini${unboundMiniCls}"
                      data-toolhead="${th.id}"
                      style="${unboundMiniBorder}"
                      title="${th.id} — ${safeDisplay} — ${Math.round(weight)}g (click to Quick-Swap)">
            ${swatch}
            <span class="fcc-ps-mini-id">${th.id}</span>
            <span class="fcc-ps-mini-weight" style="color:${wColor};">${Math.round(weight)}g</span>${unboundMiniHint}
        </span>`;
    };

    // L56 — printer-state vocabulary → badge {class,label,title}, in ONE
    // place so the expanded-row badge (_renderStateBadge) and the collapsed
    // chip strip (_renderStateChip) never drift on colors/vocabulary. Direct
    // PrusaLink read (no dryer-box dependency), so it renders for Core One in
    // direct-feed setups where the toolhead weight only ticks after the FCC
    // deduct. Returns null when there's nothing to show.
    //   state === undefined → not probed       → null (no badge)
    //   state === null      → printer didn't answer → OFFLINE badge
    const _stateMeta = (state) => {
        if (state === undefined) return null;
        if (state === null) {
            return {
                cls: 'fcc-ps-state-offline',
                label: 'OFFLINE',
                title: 'Printer unreachable (offline, networked elsewhere, or cold-rebooting)',
            };
        }
        const raw = String(state.state || '').toUpperCase();
        if (!raw) return null;
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
        // Escape before the value reaches the badge/chip innerHTML. Real
        // PrusaLink states are enumerated alphanumerics, but a spoofed printer
        // is an untrusted source and the chip now sits on the always-visible
        // collapsed strip — cheap defense, a no-op for normal states. `cls` is
        // chosen from the raw (compared, never rendered) value above.
        const safe = raw.replace(/[&<>"]/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
        return { cls, label: safe, title: `PrusaLink reports: ${safe}` };
    };

    // Expanded-row badge — sits after the printer name on its header line
    // (always visible in the expanded view).
    const _renderStateBadge = (state) => {
        const m = _stateMeta(state);
        if (!m) return '';
        return `<span class="fcc-ps-state ${m.cls}" title="${m.title}">${m.label}</span>`;
    };

    // Collapsed chip-strip badge — same color/vocab as the expanded badge,
    // rendered compact at the head of each printer's chip group so the user
    // can read live printer state WITHOUT expanding the widget (buglist
    // 2026-06-13 "show the printer state in the collapsed Printer Status bar").
    const _renderStateChip = (state) => {
        const m = _stateMeta(state);
        if (!m) return '';
        return `<span class="fcc-ps-state fcc-ps-state-chip ${m.cls}" title="${m.title}">${m.label}</span>`;
    };

    // A printer's name, escaped for the text and for its title attribute.
    const _esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    // --- A PRINTER: ITS HEADER LINE, THEN ITS TILES UNDER THE NAME ----------
    // Derek, 2026-10-23 (picture 13 / 14 of 2026-10-22, style S3): "name on top
    // of tool heads, probably reads better, especially if we indent in the
    // toolheads more so that they read as a sub thing of the printer name".
    // Each printer is a two-column grid (global.css .fcc-ps-row):
    //   [▲▼] [name · state badge · 🛑 N]      <- the header line
    //        [tile] [tile] [tile] ...          <- the tiles, under the name
    // The tiles share the name's column, so they start under the name's first
    // letter, a step in from the arrows, and take the row's width minus that
    // step. The name keeps to one line: when the line is too short it ends in
    // "…" (its full text is its title), and the badge and the review count
    // never shrink or wrap, so they stay on the name's line and a long name
    // can't reach the tiles. cancel_review.js puts the 🛑 N count at the end of
    // the header line (.fcc-ps-head), after the badge. The arrows stay a pair,
    // ▲ over ▼: side by side they would push the tiles in by 46 px instead of
    // 26, and a 412 px phone would fit one tile on a line instead of two.
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
        // The tiles' rows are laid out by _balanceRows after the render (no
        // Bootstrap d-flex here: its !important display would beat the grid).
        return `
            <div class="fcc-ps-row" data-printer="${safeName}">
                <div class="fcc-ps-reorder-stack d-flex flex-column">
                    ${upBtn}
                    ${downBtn}
                </div>
                <div class="fcc-ps-head">
                    <div class="fcc-ps-name text-info fw-bold" title="${_esc(name)}">${_esc(name)}</div>
                    ${stateBadge}
                </div>
                <div class="fcc-ps-toolheads">
                    ${info.toolheads.map(_renderToolheadBlock).join('')}
                </div>
            </div>
        `;
    };

    // --- EVEN ROWS OF TILES (Derek, 2026-10-22; under the name since 2026-10-23) ---
    // A printer's tiles sit under its name. When they don't all fit on one
    // line there, they split into the FEWEST rows with EQUAL counts: 8 -> 4 + 4,
    // 7 -> 4 + 3, 10 -> 5 + 5, never 7 + 1. Rows as equal as they can be, the
    // longer ones first (7 in three rows is 3 + 2 + 2). A row of one tile is
    // left only where at most two fit on a line and the count is odd (a phone:
    // 2 + 2 + 1). Until 2026-10-23 the tiles sat beside a 12.5rem name column
    // and went under the name only on a phone; that "beside" mode is gone.
    //
    // tileRows(n, fit) -> {cols, rows, sizes}: `fit` is how many tiles fit on
    // a line under the name (0 counts as 1). Pure (pinned by
    // tests/test_printer_status_even_rows.py).
    const tileRows = (n, fit) => {
        const count = Math.max(0, Math.floor(Number(n) || 0));
        if (!count) return { cols: 0, rows: 0, sizes: [] };
        const per = Math.max(1, Math.floor(Number(fit) || 0));
        const rows = Math.ceil(count / per);
        const big = count % rows;            // rows that get one tile more
        const base = Math.floor(count / rows);
        const sizes = [];
        for (let i = 0; i < rows; i++) sizes.push(base + (i < big ? 1 : 0));
        return { cols: sizes[0], rows, sizes };
    };
    window.fccPrinterStatusTileRows = tileRows;

    // Measures every printer's tile area (the row's width minus the step in
    // from the arrows) and lays its tiles out by tileRows: a grid of `cols`
    // columns (--fcc-ps-cols) whose rows each start in column 1, so 7 in
    // three rows reads 3 + 2 + 2 (a plain grid would fill 3 + 3 + 1). All
    // reads first, then all writes. Runs after every render, on a Text size
    // change and when the body's width changes; does nothing while the widget
    // is collapsed (the body has no width), and the body's width changing on
    // expand runs it again.
    //
    // Widths are read to the fraction of a px (review, 2026-10-22): at a
    // display scale of 110 % a width of 1439.83 px reads as 1440 in
    // clientWidth (a whole px), and one tile more than fits was counted. Then
    // what the browser drew is checked, all reads and then all writes again:
    // a line of tiles wider than its area is laid out again with one tile
    // fewer per line, so a rounding the sums don't see (a gap at another
    // scale, a margin) can't leave it wrong either.
    const _balanceRows = () => {
        const widget = document.getElementById('printer-status-widget');
        const body = widget && widget.querySelector('.fcc-ps-body');
        if (!body || typeof body.querySelectorAll !== 'function') return;
        const px = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
        // The tile area's content box, to the fraction of a px. It is the
        // grid's second column (minmax(0, 1fr)), so its width never follows
        // the tiles.
        const contentBox = (el) => {
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            const left = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft);
            const right = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
            return { left, right, width: right - left, gap: px(cs.columnGap) };
        };
        const rows = [];
        body.querySelectorAll('.fcc-ps-row').forEach((row) => {
            const heads = row.querySelector('.fcc-ps-toolheads');
            const tiles = heads ? Array.from(heads.children).filter(el => el.classList && el.classList.contains('fcc-ps-th')) : [];
            if (!heads || !tiles.length) return;
            const box = contentBox(heads);
            const tileW = tiles[0].getBoundingClientRect().width;
            if (!(box.width > 0) || !(tileW > 0)) return;
            // A twentieth of a px of slack, so k tiles and k - 1 gaps that fit
            // exactly don't lose a tile to a gap's rounding; the check below
            // catches the rare line it lets through.
            const fit = Math.max(0, Math.floor((box.width + box.gap + 0.05) / (tileW + box.gap)));
            rows.push({ heads, tiles, fit, plan: null });
        });
        const lay = (r) => {
            const plan = tileRows(r.tiles.length, r.fit);
            r.plan = plan;
            r.heads.classList.add('fcc-ps-balanced');
            r.heads.style.setProperty('--fcc-ps-cols', String(plan.cols));
            r.heads.dataset.rows = plan.sizes.join('+');
            let start = 0;
            const starts = new Set(plan.sizes.map((size) => { const at = start; start += size; return at; }));
            r.tiles.forEach((tile, i) => { tile.style.gridColumnStart = (i > 0 && starts.has(i)) ? '1' : ''; });
        };
        rows.forEach(lay);
        // Drawn as planned? The first, longest, line of tiles ends inside
        // the tile area.
        const drawnWrong = (r) => r.plan.cols > 0
            && r.tiles[r.plan.cols - 1].getBoundingClientRect().right > contentBox(r.heads).right + 0.01;
        for (let pass = 0; pass < 3; pass++) {
            const wrong = rows.filter(drawnWrong);
            if (!wrong.length) break;
            wrong.forEach((r) => { r.fit = Math.max(1, r.plan.cols - 1); lay(r); });
        }
    };
    window.balancePrinterStatusRows = _balanceRows;

    // The body's width: the window, a scrollbar coming or going, the widget
    // opening. Only a change of width lays the rows out again (their height
    // changes when they do, and must not start it over). Compared to the
    // fraction of a px: at a display scale such as 110 % a window one device
    // px narrower is 0.91 px narrower, which rounding could hide.
    let _bodyWidth = -1;
    let _widthFrame = 0;
    const _watchBodyWidth = (body) => {
        if (!body || body._fccPsWidthWatched || typeof ResizeObserver !== 'function') return;
        body._fccPsWidthWatched = true;
        new ResizeObserver((entries) => {
            const entry = entries && entries[entries.length - 1];
            const w = entry ? entry.contentRect.width : -1;
            if (w === _bodyWidth) return;
            _bodyWidth = w;
            // Out of the observer's callback: the layout it changes would
            // otherwise be reported again in the same frame.
            if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(_widthFrame);
            _widthFrame = requestAnimationFrame(() => _balanceRows());
        }).observe(body);
    };
    // A Text size change grows or shrinks every tile (rem), not the window.
    document.addEventListener('fcc:text-size', () => _balanceRows());

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
        // Even rows of tiles under each name (Derek, 2026-10-22 / 2026-10-23),
        // laid out before the browser paints the new rows.
        _balanceRows();
        _watchBodyWidth(body);
        // Header chip strip — every toolhead from every printer in the
        // user's printer order. Each printer's chips are wrapped in a
        // group div so CSS can add a vertical divider between groups,
        // making it clear at a glance which chips belong to which printer.
        const headerChips = widget.querySelector('.fcc-ps-header-chips');
        if (headerChips) {
            headerChips.innerHTML = printerNames.map(name => {
                const safeName = name.replace(/"/g, '&quot;');
                // Lead each group with a compact state badge so live printer
                // state (PRINTING / IDLE / PAUSED / OFFLINE …) is visible in
                // the collapsed strip without expanding the widget.
                const stateChip = _renderStateChip(rows[name].state);
                const chips = rows[name].toolheads.map(_renderToolheadCompact).join('');
                return `<div class="fcc-ps-printer-group" data-printer="${safeName}">${stateChip}${chips}</div>`;
            }).join('');
        }
        // Delegated click handler — bound ONCE on the stable widget root
        // (see _wireDelegation). Re-attaching per render lost clicks when
        // the widget re-rendered between Playwright's actionability check
        // and click, especially during active PRINTING when state/weight
        // ticks invalidated the fingerprint frequently (L361).
        _wireDelegation(widget);
        // Re-paint the cancelled-print "🛑 N" review chip onto each printer's
        // name (the widget just overwrote body.innerHTML, dropping any chips).
        if (window.cancelReviewDecorate) window.cancelReviewDecorate();
    };

    const _wireDelegation = (widget) => {
        if (widget._fccPsClicksWired) return;
        widget._fccPsClicksWired = true;
        widget.addEventListener('click', (e) => {
            const el = e.target.closest('.fcc-ps-th, .fcc-ps-mini');
            if (!el || !widget.contains(el)) return;
            e.stopPropagation();
            const tid = el.dataset.toolhead;
            if (tid && window.openManage) window.openManage(tid);
        });
    };

    // --- reads-1 (Group 52 review): "Spoolman didn't answer", never "empty" ---
    // A head's tile comes from Spoolman's spool list. When the heartbeat's one
    // read of it fails, its `spool_read` says ok: false and every head in its
    // printer_status is empty only because nothing was read; when the fan-out's
    // strict read of one head fails, that head comes back `unread`. Either way a
    // head keeps the spool its tile showed after the last read that worked, a
    // head with no earlier answer is drawn "? not read", and
    // #printer-status-read-notice says Spoolman didn't answer. Everything that
    // isn't read from Spoolman (the printer's state badge, the 🔗 binding hint)
    // still updates. The next good read redraws the tiles and hides the notice;
    // a heartbeat that says nothing either way draws as before.
    //
    // `everyHead`: the heartbeat's read failed, so every head is unread;
    // otherwise only the heads marked `unread`. `last` is what was drawn.
    const _keepLastTiles = (rows, last, everyHead) => {
        let kept = 0, unread = 0;
        const out = {};
        Object.keys(rows).forEach(name => {
            const info = rows[name];
            if (!info || typeof info !== 'object' || !Array.isArray(info.toolheads)) {
                out[name] = info;
                return;
            }
            const prev = new Map();
            ((last && last[name] && last[name].toolheads) || []).forEach(p => {
                if (p && p.id) prev.set(p.id, p);
            });
            out[name] = {
                ...info,
                toolheads: info.toolheads.map(th => {
                    if (!th || !(everyHead || th.unread)) return th;
                    const p = prev.get(th.id);
                    const head = { ...th };
                    delete head.loaded_ids;
                    if (p && !p.unread) {
                        kept++;
                        head.item = p.item || null;
                        head.loaded_count = p.loaded_count || 0;
                        if (p.loaded_ids) head.loaded_ids = p.loaded_ids;
                        delete head.unread;
                    } else {
                        unread++;
                        head.item = null;
                        head.loaded_count = 0;
                        head.unread = true;
                    }
                    return head;
                }),
            };
        });
        return { rows: out, kept, unread };
    };
    const _readNoticeEl = () => {
        let el = document.getElementById('printer-status-read-notice');
        if (el) return el;
        const widget = document.getElementById('printer-status-widget');
        const body = widget && widget.querySelector('.fcc-ps-body');
        if (!body || !body.parentNode) return null;
        // Above the body, not in it: _render rewrites the body, and the notice
        // must show in the collapsed view too (which hides the body). Same look
        // as #manage-read-notice (Group 52.1b), a little smaller for the band.
        el = document.createElement('div');
        el.id = 'printer-status-read-notice';
        el.className = 'fcc-ps-read-notice';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.style.cssText = 'display:none; background:#2b2200; color:#ffd54a; border:1px solid #ffd54a;'
            + ' border-radius:6px; padding:4px 10px; margin:4px 0; font-weight:bold; font-size:0.85rem;';
        body.parentNode.insertBefore(el, body);
        return el;
    };
    const _showReadFailure = (kept, why) => {
        const el = _readNoticeEl();
        if (!el) return;
        const text = "⚠️ Spoolman didn't answer, so FCC couldn't check what's loaded on the toolheads just now."
            + (kept ? ' These tiles are from its last answer.' : '')
            + ' It tries again every few seconds.';
        // Only on a change: an aria-live region re-announces a rewrite.
        if (el.textContent !== text) el.textContent = text;
        el.title = why ? String(why) : '';
        el.style.display = 'block';
    };
    const _clearReadFailure = () => {
        const el = document.getElementById('printer-status-read-notice');
        if (!el) return;
        el.style.display = 'none';
        el.textContent = '';
        el.title = '';
    };

    const refresh = async () => {
        if (_state.inFlight) return;
        _state.inFlight = true;
        try {
            let rows = await _aggregate();
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
            // reads-1: a head whose strict read failed keeps its last tile.
            const anyUnread = Object.keys(rows).some(name => {
                const heads = rows[name] && rows[name].toolheads;
                return Array.isArray(heads) && heads.some(th => th && th.unread);
            });
            if (anyUnread) {
                const kept = _keepLastTiles(rows, _state.rowsByPrinter, false);
                rows = kept.rows;
                _showReadFailure(kept.kept > 0, null);
            } else {
                _clearReadFailure();
            }
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
        // Opened: the rows are measured again (the window may have changed
        // size, or the Text size, while the body had no width).
        if (!_isCollapsed()) _balanceRows();
    };

    // Group 45.8: every heartbeat tick renders this widget from its
    // printer_status section (refreshFromAggregate, below) and THEN fires
    // inventory:sync-pulse. Answering that event with the client fan-out
    // re-read Spoolman's whole spool list once per toolhead per tick: 52
    // /api/get_contents calls in 21 idle seconds on dev's 13 heads, for data
    // the tick had just delivered. So a heartbeat event is skipped when its
    // tick fed the widget (inv_cmd.js skips it for the buffer the same way,
    // L206); a tick without the section still falls back to the fan-out, and
    // every other source (an eject, a details save, a review) refreshes at once.
    //
    // Except for LOCAL_SETTLE_MS after a local change. The server reads
    // Spoolman first and probes the printers after (2 s per offline printer),
    // so a tick whose snapshot predates a Quick-Swap or an eject can land after
    // the change's own refresh and repaint the old spool (review widget-1).
    // Within that window a tick's event still runs the fan-out, as before 45.8.
    const LOCAL_SETTLE_MS = 15000;
    const _localRefresh = () => { _state.localAt = Date.now(); scheduleRefresh(); };
    document.addEventListener('inventory:sync-pulse', (e) => {
        const fromPulse = !!(e && e.detail && e.detail.source === 'dashboard_pulse');
        const fed = _state.pulseFed;
        _state.pulseFed = false;
        if (!fromPulse) { _localRefresh(); return; }
        if (fed && Date.now() - _state.localAt > LOCAL_SETTLE_MS) return;
        scheduleRefresh();
    });
    document.addEventListener('inventory:locations-changed', _localRefresh);
    document.addEventListener('DOMContentLoaded', () => {
        _renderShell();
        // No fetch here: the heartbeat's first tick (100 ms after
        // DOMContentLoaded, inv_core.js) renders the widget, state badges
        // included; the "Loading printer status…" skeleton in dashboard.html
        // holds the layout space until then. Fetching here too doubled every
        // page load's Spoolman reads (Group 45.8).
        setTimeout(() => {
            if (_state.lastFingerprint === null) refresh();
        }, LOAD_FALLBACK_MS);
    });

    // L206 bulk-pulse hook: render from a pre-fetched aggregate without
    // hitting the per-printer fan-out. Same fingerprint/wiggle protection
    // as refresh(). Called by startSmartSync's dashboard_pulse dispatcher
    // when the response includes a printer_status section; `read` is the
    // heartbeat's `spool_read` ({ok, error}), or undefined when it has none.
    const refreshFromAggregate = (rows, read) => {
        if (!rows || typeof rows !== 'object') return;
        // A section the server couldn't build arrives as {error: "..."}
        // (routes_state_pulse.py). Treat it as missing so the tick's event takes
        // the fan-out fallback; rendering it threw in _fingerprint and aborted
        // the rest of the tick (review widget-2).
        if (typeof rows.error === 'string') return;
        // The tick's inventory:sync-pulse, fired right after this, needs no
        // fan-out: not even when Spoolman didn't answer (one more whole-list
        // read per head, just when it is slow).
        _state.pulseFed = true;
        // reads-1: the read failed, so every head keeps its last tile.
        if (read && read.ok === false) {
            const kept = _keepLastTiles(rows, _state.rowsByPrinter, true);
            rows = kept.rows;
            _showReadFailure(kept.kept > 0, read.error);
        } else {
            _clearReadFailure();
        }
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
