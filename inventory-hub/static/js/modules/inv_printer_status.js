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
    const NAME_KEY = 'fcc.printerStatus.printerName';
    const WEIGHT_KEY = 'fcc.printerStatus.stripWeight';
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
        // Group 50.1: each printer's ID, as the heartbeat gives it (`id`).
        const idByName = {};
        (pmBody.printer_rows || []).forEach((p) => {
            if (p && p.name && p.location_id && !idByName[p.name]) idByName[p.name] = String(p.location_id);
        });
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
            out[name] = { toolheads: allRows, id: idByName[name] || '' };
        }));
        return out;
    };

    // The Printer Status settings (Settings → 🖥️ This Browser; config_schema.py),
    // by the names their selects show. Group 46.3's toolhead labels: the head's
    // ID (the default), its number, or "Tool" and its number; the number is the
    // head's position + 1 (positions count from 0, a printer's own screen and the
    // Feeds / Quick-Swap pickers from 1). Group 50.1 (Derek, 2026-10-29): the
    // folded strip follows that setting too (each printer's heads sit behind its
    // own name now, so two printers' "1"s can't be confused), shows each printer
    // by its name or its ID, and shows each loaded head's grams beside it (the
    // default: "it's kind of the point for me"), under it, or not at all. The
    // labels' old names were what one head of Derek's read ("XL-3" / "3" /
    // "Tool 3"); a browser's old pick is stored under its new name at load, so
    // Settings shows it (it shows the default for a value its select lacks).
    // Visible text only: data-toolhead and the tooltips keep the full ID.
    const PREFS = Object.freeze({
        label: Object.freeze({ key: LABEL_KEY, def: 'By ID', label: 'Printer Status toolhead labels',
            choices: Object.freeze(['By ID', 'By number', 'By Tool + number']),
            legacy: Object.freeze({ 'XL-3': 'By ID', '3': 'By number', 'Tool 3': 'By Tool + number' }) }),
        name: Object.freeze({ key: NAME_KEY, def: 'By name', label: 'Printers in the folded Printer Status',
            choices: Object.freeze(['By name', 'By ID']) }),
        weight: Object.freeze({ key: WEIGHT_KEY, def: 'Beside each toolhead', label: 'Weights in the folded Printer Status',
            choices: Object.freeze(['Beside each toolhead', 'Under each toolhead', 'Off']) }),
    });
    // A pick this page couldn't store (private mode, blocked storage) still
    // shows until the page is reloaded.
    const _picked = {};
    const _pref = (which) => {
        const p = PREFS[which];
        if (_picked[which]) return _picked[which];
        let v = null;
        try { v = localStorage.getItem(p.key); } catch (e) { /* blocked storage: the default */ }
        if (p.legacy && typeof v === 'string' && Object.prototype.hasOwnProperty.call(p.legacy, v)) v = p.legacy[v];
        return p.choices.includes(v) ? v : p.def;
    };
    try {
        const old = localStorage.getItem(LABEL_KEY);
        if (old && Object.prototype.hasOwnProperty.call(PREFS.label.legacy, old)) {
            localStorage.setItem(LABEL_KEY, PREFS.label.legacy[old]);
        }
    } catch (e) { /* blocked storage: _pref reads the old name as the new one */ }
    const _thLabel = (th) => {
        const mode = _pref('label');
        const n = Number(th.position);
        if (!Number.isFinite(n)) return th.id;
        if (mode === 'By number') return String(n + 1);
        if (mode === 'By Tool + number') return `Tool ${n + 1}`;
        return th.id;
    };

    // Fingerprint of the aggregation result so refresh can skip rerendering
    // identical state — keeps a tight sync-pulse cadence cheap. The label mode
    // is part of it, so changing it in Settings repaints on the next pulse.
    const _fingerprint = (rows) => {
        const parts = ['label=' + _pref('label'), 'name=' + _pref('name'), 'weight=' + _pref('weight')];
        Object.entries(rows).sort().forEach(([name, info]) => {
            const stateFp = info.state === null ? 'offline'
                : info.state ? String(info.state.state || '') : '';
            parts.push(name + '#' + String(info.id || '') + '@' + stateFp + '|' + info.toolheads.map(th => {
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
        // Group 50.3: every tile is a tab stop and a button (Enter or Space
        // opens the head, _wireDelegation), as a click does.
        const positionAttr = `data-toolhead="${th.id}" tabindex="0" role="button"`;
        if (th.unread && !it) {
            // reads-1: Spoolman didn't answer and FCC has no earlier answer for
            // this head, so it doesn't know what is loaded: "? not read", never
            // "empty" (and never the unbound placeholder, which reads as empty).
            return `
                <div class="fcc-ps-th fcc-ps-th-unread" ${positionAttr}
                     style="cursor:pointer;"
                     title="${th.id} — Spoolman didn't answer, so FCC couldn't check what is loaded here. It tries again every few seconds. Click to open ${th.id}.">
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
                     title="${th.id} — no dryer-box slot is bound to this toolhead. Bind one in the Location Manager → Feeds editor for a dryer box. Click to open ${th.id}.">
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
                     title="${th.id} — empty. Click to open ${th.id}.">
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
                 title="${th.id} — ${(it.display || `#${it.id}`).replace(/"/g, '&quot;')} — ${Math.round(weight)}g remaining. Click to open ${th.id}: what it holds, and its Quick-Swap slots.">
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

    // --- THE FOLDED STRIP (Group 50.1; Derek, 2026-10-19 / 25 / 29) ----------
    // Each printer reads as it does open: its name (or its ID, the "Printers"
    // setting; hovering shows both), its state, its 🛑 count, then its heads.
    // A head is its label (the toolhead-label setting) on its spool's colour,
    // ringed in the colour of the tiles' weight bars (_weightPalette: cyan,
    // amber under 100 g, red at 0); a hollow grey ring holds no spool, a dashed
    // one has no box slot feeding it, a dotted amber one couldn't be read
    // (reads-1, "?"). With the weights setting on (the default) its grams sit
    // beside the ring or under it, in the ring's colour; off, they are in the
    // head's tooltip. A doubled head (Group 42.4) says ⚠️N beside it. The head
    // keeps the .fcc-ps-mini class, so the widget's one delegated click opens
    // it (L361), and data-toolhead keeps the full ID.
    const _renderToolheadCompact = (th) => {
        const it = th.item;
        const label = _esc(_thLabel(th));
        const shape = _pref('label') === 'By number' ? 'fcc-ps-ring' : 'fcc-ps-ring fcc-ps-ring-pill';
        const weightMode = _pref('weight');
        const unb = th.unbound ? ' fcc-ps-ring-unbound' : '';
        const feed = th.unbound ? ' No box slot feeds it.' : '';
        const open = ` Click to open ${th.id}.`;
        let ring;
        let tip;
        let below = '';
        if (th.unread && !it) {
            tip = `${th.id}: Spoolman didn't answer, so FCC couldn't check what is loaded here.${open}`;
            ring = `<span class="${shape} fcc-ps-ring-empty fcc-ps-ring-unread">${label}</span>`;
            below = '<span class="fcc-ps-mini-weight fcc-ps-strip-unread">?</span>';
        } else if (!it) {
            tip = `${th.id}: empty.${feed}${open}`;
            ring = `<span class="${shape} fcc-ps-ring-empty${unb}">${label}</span>`;
            // Under: an invisible line keeps the ring in line with its neighbours'.
            if (weightMode === 'Under each toolhead') {
                below = '<span class="fcc-ps-mini-weight fcc-ps-strip-w-none" aria-hidden="true">0g</span>';
            }
        } else {
            // A spool whose weight Spoolman doesn't know reads "---" (as its open
            // tile does) in a plain ring, never a red "0g" that says empty.
            const known = it.remaining_weight !== undefined && it.remaining_weight !== null
                && Number.isFinite(Number(it.remaining_weight));
            const weight = known ? Number(it.remaining_weight) : 0;
            const pal = known ? _weightPalette(weight) : null;
            const fill = typeof window.getFilamentStyle === 'function'
                ? window.getFilamentStyle(it.color, it.color_direction || 'longitudinal').frame
                : '#444';
            tip = `${th.id}: ${it.display || `#${it.id}`}, ${known ? `${Math.round(weight)} g left` : 'weight unknown'}.${feed}${open}`;
            ring = `<span class="${shape}${unb} text-pop" style="${pal ? `--fcc-ring:${pal}; ` : ''}background:${fill};">${label}</span>`;
            if (weightMode !== 'Off') {
                below = known
                    ? `<span class="fcc-ps-mini-weight" style="color:${pal};">${Math.round(weight)}g</span>`
                    : '<span class="fcc-ps-mini-weight fcc-ps-strip-w-unknown">---</span>';
            }
        }
        const doubled = (th.loaded_count || 0) > 1
            ? `<span class="fcc-ps-mini-doubled" title="${_esc(_doubledText(th))}">⚠️${th.loaded_count}</span>`
            : '';
        return `<span class="fcc-ps-mini fcc-ps-strip-head" data-toolhead="${_esc(th.id)}" tabindex="0" role="button" title="${_esc(tip)}">`
            + `<span class="fcc-ps-strip-stack">${ring}${below}</span>${doubled}</span>`;
    };

    // One printer's group in the folded strip. Its 🛑 count goes in its own slot
    // (cancel_review.js), between the state and the heads.
    const _renderStripGroup = (name, info) => {
        const id = String((info && info.id) || '').trim();
        const shown = (_pref('name') === 'By ID' && id) ? id : name;
        const tip = id ? `${name} · ID ${id}` : name;
        return `<div class="fcc-ps-printer-group" data-printer="${_esc(name)}">`
            + `<span class="fcc-ps-strip-name" title="${_esc(tip)}">${_esc(shown)}</span>`
            + `<span class="fcc-ps-strip-state">${_renderStateChip(info.state)}</span>`
            + '<span class="fcc-ps-strip-count"></span>'
            + `<span class="fcc-ps-strip-heads">${info.toolheads.map(_renderToolheadCompact).join('')}</span>`
            + '</div>';
    };

    // Beside the title while every printer's heads fit there (the strip takes
    // what the title leaves, at least 20rem); else under the title, where it has
    // the whole width (.fcc-ps-strip-under); a printer whose heads don't fit
    // even there scrolls them sideways (Derek's fallback). Two printers that
    // don't fit on one line take a line each, from the same edge. Measured,
    // never estimated, and only while the strip shows (the widget folded):
    // after a render, a resize, a Text size change, a 🛑 count change, folding.
    const _fitStrip = () => {
        const widget = document.getElementById('printer-status-widget');
        const strip = widget && widget.querySelector('.fcc-ps-header-chips');
        if (!strip || !widget.classList.contains('collapsed')) return;
        strip.classList.remove('fcc-ps-strip-under');
        const overflows = Array.from(strip.querySelectorAll('.fcc-ps-strip-heads'))
            .some((h) => h.scrollWidth > h.clientWidth + 1);
        if (overflows) strip.classList.add('fcc-ps-strip-under');
    };
    window.fitPrinterStatusStrip = _fitStrip;

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

    // Expanded-row badge — first on the printer's info line, under its name
    // and before the review count (Derek, 2026-10-24), in its slot (_renderRow).
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

    // A printer's name, escaped for the text and for an attribute (its title,
    // data-printer): the attribute then reads back as the plain name.
    const _esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
    // A value for an inline handler: a JS string first, then escaped for the
    // attribute (CLAUDE.md, SpoolCardBuilder.jsArg). The browser decodes the
    // attribute's entities before it compiles the handler, so an apostrophe
    // ("Derek's XL") ends up inside the string, never ending it.
    const _jsArg = (v) => ((window.SpoolCardBuilder && typeof window.SpoolCardBuilder.jsArg === 'function')
        ? window.SpoolCardBuilder.jsArg(v)
        : _esc(JSON.stringify(String(v == null ? '' : v))));

    // --- A PRINTER: ITS NAME, ITS INFO LINE, THEN ITS TILES ----------------
    // Derek, 2026-10-23 (picture 13 / 14 of 2026-10-22, style S3): "name on top
    // of tool heads, probably reads better, especially if we indent in the
    // toolheads more so that they read as a sub thing of the printer name".
    // Derek, 2026-10-24, after the state and the count went before the name:
    // "the printer name, then under it, the status and review, basically we
    // could treat that section as an information area about state and
    // issues, then the toolheads ... you now have to go hunting for the
    // printer name to know what those statuses apply to". Each printer is a
    // grid of two columns (global.css .fcc-ps-row):
    //   [▲▼] [name]                     <- the name's line
    //        [STATE] [🛑 N]             <- the info line (.fcc-ps-info)
    //        [tile] [tile] [tile] ...   <- the tiles
    // The name, the info line and the tiles start at the same place, a step
    // in from the arrows. The state and the count each have a slot of the
    // same width on every printer (the count's is there with no reviews too:
    // cancel_review.js puts the 🛑 N in it), so the states and the counts line
    // up down the page; more about a printer's state or its issues goes on
    // the info line, after the count. The name keeps to one line: when the
    // line is too short it ends in "…" (its full text is its title), so a long
    // name can't reach the info line or the tiles. The arrows stay a pair, ▲
    // over ▼, centred on the name's line and never making it taller (a
    // middle printer has both). Where fewer than two tiles fit under the
    // name (a phone) and more fit from the row's edge, they start there
    // (_balanceRows, .fcc-ps-edge).
    // data-printer holds the plain name (attribute-escaped), which
    // cancel_review.js matches to a review's printer_name; until 2026-10-24 it
    // held the handler's JS escape (Derek\'s XL), so a printer with an
    // apostrophe in its name never showed its count.
    const _renderRow = (name, info, idx, total) => {
        const nameArg = _jsArg(name);
        const upBtn = idx > 0
            ? `<button type="button" class="fcc-ps-reorder" data-dir="-1" title="Move up"
                    onclick="event.stopPropagation(); window.movePrinterStatusRow(${nameArg}, -1)">▲</button>`
            : `<span class="fcc-ps-reorder-placeholder"></span>`;
        const downBtn = idx < total - 1
            ? `<button type="button" class="fcc-ps-reorder" data-dir="1" title="Move down"
                    onclick="event.stopPropagation(); window.movePrinterStatusRow(${nameArg}, 1)">▼</button>`
            : `<span class="fcc-ps-reorder-placeholder"></span>`;
        const stateBadge = _renderStateBadge(info.state);
        // Per-printer expanded row. The collapsed view is now a single
        // chip strip in the widget header (rendered separately in _render),
        // not per-row, so we don't include compact chips here anymore.
        // The tiles' rows are laid out by _balanceRows after the render (no
        // Bootstrap d-flex here: its !important display would beat the grid;
        // the arrows' pair is laid out by global.css too).
        return `
            <div class="fcc-ps-row" data-printer="${_esc(name)}">
                <div class="fcc-ps-reorder-stack">
                    ${upBtn}
                    ${downBtn}
                </div>
                <div class="fcc-ps-name text-info fw-bold" title="${_esc(name)}">${_esc(name)}</div>
                <div class="fcc-ps-info">
                    <span class="fcc-ps-state-slot">${stateBadge}</span>
                    <span class="fcc-ps-count"></span>
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
    // a line (0 counts as 1). Pure (pinned by
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

    // Measures every printer's tile area (the row's width from the name's
    // first letter, a step in from the arrows) and lays
    // its tiles out by tileRows: a grid of `cols` columns (--fcc-ps-cols)
    // whose rows each start in column 1, so 7 in three rows reads 3 + 2 + 2 (a
    // plain grid would fill 3 + 3 + 1). All reads first, then all writes. Runs
    // after every render, on a Text size change and when the body's width
    // changes; does nothing while the widget is collapsed (the body has no
    // width), and the body's width changing on expand runs it again.
    //
    // A phone (review, 2026-10-23; the state and the count before the name
    // since 2026-10-24): where fewer than two tiles fit on a line under the
    // name and more fit across the row's whole width, the tiles start at the
    // row's edge instead (the row gets .fcc-ps-edge), under the arrows: two to
    // a line from 376 px at Standard (an iPhone 12 to 16 is 390 or 393 px, a
    // Pixel or a Galaxy 412) up to 568 px; from 569 px two fit under the name.
    // Where not even one fits under the name (below 369 px at Standard) the
    // one a line starts at the edge too. The state, the count and their gaps
    // are narrower than a tile, so the edge has room for one tile more than
    // under the name, never two; it takes at most two a line anyway, so a
    // wider state (OPERATIONAL) can't make a wider window show fewer.
    //
    // Widths are read to the fraction of a px (review, 2026-10-22): at a
    // display scale of 110 % a width of 1439.83 px reads as 1440 in
    // clientWidth (a whole px), and one tile more than fits was counted. The
    // count the measure made is the tile area's data-fit, so a test can tell
    // a measure that counted right from one the check below put right. Then
    // what the browser drew is checked, all reads and then all writes again:
    // a line of tiles wider than its area is laid out again with one tile
    // fewer per line, so a rounding the sums don't see (a gap at another
    // scale, a margin) can't leave it wrong either.
    const _balanceRows = () => {
        const widget = document.getElementById('printer-status-widget');
        const body = widget && widget.querySelector('.fcc-ps-body');
        if (!body || typeof body.querySelectorAll !== 'function') return;
        const px = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
        // An element's content box, to the fraction of a px. The tile area is
        // the grid's second column (minmax(0, 1fr)), or both columns at the
        // edge, so its width never follows the tiles.
        const contentBox = (el) => {
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            const left = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft);
            const right = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
            return { left, right, width: right - left };
        };
        const rows = [];
        body.querySelectorAll('.fcc-ps-row').forEach((row) => {
            const heads = row.querySelector('.fcc-ps-toolheads');
            const name = row.querySelector('.fcc-ps-name');
            const tiles = heads ? Array.from(heads.children).filter(el => el.classList && el.classList.contains('fcc-ps-th')) : [];
            if (!heads || !name || !tiles.length) return;
            // The row's own width, and the part of it under the name: from the
            // name's column (its left edge, which no mode moves: only the
            // arrows' column is before it, the same width on every printer)
            // to the row's right edge.
            const whole = contentBox(row);
            const under = whole.right - name.getBoundingClientRect().left;
            const gap = px(getComputedStyle(heads).columnGap);
            const tileW = tiles[0].getBoundingClientRect().width;
            if (!(whole.width > 0) || !(tileW > 0)) return;
            // A twentieth of a px of slack, so k tiles and k - 1 gaps that fit
            // exactly don't lose a tile to a gap's rounding; the check below
            // catches the rare line it lets through.
            const count = (w) => Math.max(0, Math.floor((w + gap + 0.05) / (tileW + gap)));
            const fitUnder = count(under);
            const fitWhole = count(whole.width);
            const edge = fitUnder < 2 && fitWhole > fitUnder;
            rows.push({ row, heads, tiles, edge, fitUnder, fit: edge ? Math.min(fitWhole, 2) : fitUnder, plan: null });
        });
        const lay = (r) => {
            const plan = tileRows(r.tiles.length, r.fit);
            r.plan = plan;
            r.row.classList.toggle('fcc-ps-edge', r.edge);
            r.heads.classList.add('fcc-ps-balanced');
            r.heads.style.setProperty('--fcc-ps-cols', String(plan.cols));
            r.heads.dataset.rows = plan.sizes.join('+');
            let start = 0;
            const starts = new Set(plan.sizes.map((size) => { const at = start; start += size; return at; }));
            r.tiles.forEach((tile, i) => { tile.style.gridColumnStart = (i > 0 && starts.has(i)) ? '1' : ''; });
        };
        rows.forEach((r) => { r.heads.dataset.fit = String(r.fit); lay(r); });
        // Drawn as planned? The first, longest, line of tiles ends inside
        // the tile area. One tile a line goes back under the name where one
        // fits there by measure: the edge is for the second tile, and for the
        // first only where none fits under the name.
        const drawnWrong = (r) => r.plan.cols > 0
            && r.tiles[r.plan.cols - 1].getBoundingClientRect().right > contentBox(r.heads).right + 0.01;
        for (let pass = 0; pass < 3; pass++) {
            const wrong = rows.filter(drawnWrong);
            if (!wrong.length) break;
            wrong.forEach((r) => {
                r.fit = Math.max(1, r.plan.cols - 1);
                if (r.fit < 2 && r.fitUnder >= 1) r.edge = false;
                lay(r);
            });
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
    // A Text size change grows or shrinks every tile (rem), not the window,
    // and every head in the folded strip.
    document.addEventListener('fcc:text-size', () => { _balanceRows(); _fitStrip(); });

    // A ▲ / ▼ reached by keyboard keeps the focus through a repaint (the
    // reorder draws the rows again, and so does a heartbeat that changed a
    // tile): on the same printer's arrow, the same one when it still has it
    // (▼ again moves the printer further down), else its other one. Without
    // this the focus fell to the page after every move (review, 2026-10-23).
    // An arrow clicked with the mouse lets it go, as before.
    const _focusedArrow = (body) => {
        const el = document.activeElement;
        if (!el || typeof body.contains !== 'function' || !body.contains(el)
            || !el.classList || !el.classList.contains('fcc-ps-reorder')) return null;
        let byKeyboard = true;
        try { byKeyboard = el.matches(':focus-visible'); } catch (e) { /* an old browser: keep it */ }
        const row = byKeyboard ? el.closest('.fcc-ps-row') : null;
        return row ? { printer: row.getAttribute('data-printer'), dir: el.getAttribute('data-dir') } : null;
    };
    const _refocusArrow = (body, kept) => {
        const row = Array.from(body.querySelectorAll('.fcc-ps-row'))
            .find((r) => r.getAttribute('data-printer') === kept.printer);
        const arrows = row ? Array.from(row.querySelectorAll('button.fcc-ps-reorder')) : [];
        const target = arrows.find((b) => b.getAttribute('data-dir') === kept.dir) || arrows[0];
        if (target) target.focus();
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
        const kept = _focusedArrow(body);
        // Group 50.3: a head that has the focus keeps it through a repaint (a
        // heartbeat that changed a tile draws them all again).
        const keptHead = (() => {
            const el = document.activeElement;
            if (!el || !widget.contains(el) || !el.dataset || !el.dataset.toolhead
                || !el.classList || !(el.classList.contains('fcc-ps-th') || el.classList.contains('fcc-ps-mini'))) return null;
            return { id: el.dataset.toolhead, strip: el.classList.contains('fcc-ps-mini') };
        })();
        body.innerHTML = printerNames
            .map((name, idx) => _renderRow(name, rows[name], idx, printerNames.length))
            .join('');
        // The 🛑 N counts first (the widget just overwrote body.innerHTML,
        // dropping them), so the rows are measured as they will be drawn.
        if (window.cancelReviewDecorate) window.cancelReviewDecorate();
        // Even rows of tiles under each name (Derek, 2026-10-22 / 2026-10-23),
        // laid out before the browser paints the new rows.
        _balanceRows();
        _watchBodyWidth(body);
        if (kept) _refocusArrow(body, kept);
        // The folded strip (Group 50.1): every printer in the user's order, each
        // its name, state, 🛑 count and heads (_renderStripGroup); the weights
        // setting picks where the grams go (global.css).
        const headerChips = widget.querySelector('.fcc-ps-header-chips');
        if (headerChips) {
            const weight = _pref('weight');
            headerChips.classList.toggle('fcc-ps-strip-wt-beside', weight === 'Beside each toolhead');
            headerChips.classList.toggle('fcc-ps-strip-wt-under', weight === 'Under each toolhead');
            headerChips.innerHTML = printerNames.map(name => _renderStripGroup(name, rows[name])).join('');
        }
        // Delegated click handler — bound ONCE on the stable widget root
        // (see _wireDelegation). Re-attaching per render lost clicks when
        // the widget re-rendered between Playwright's actionability check
        // and click, especially during active PRINTING when state/weight
        // ticks invalidated the fingerprint frequently (L361).
        _wireDelegation(widget);
        _watchHeaderWidth(widget);
        // The collapsed strip's groups get their 🛑 N counts too, before the
        // strip is measured (a count takes room).
        if (window.cancelReviewDecorate) window.cancelReviewDecorate();
        _fitStrip();
        if (keptHead) {
            const again = Array.from(widget.querySelectorAll(keptHead.strip ? '.fcc-ps-mini' : '.fcc-ps-th'))
                .find((el) => el.dataset.toolhead === keptHead.id);
            if (again) again.focus();
        }
    };

    // Draws the widget again from the rows it last drew: a Printer Status
    // setting changed (the strip's look, or every tile's label).
    const _repaint = () => {
        const rows = _state.rowsByPrinter;
        if (!rows || !Object.keys(rows).length) return;
        _state.lastFingerprint = _fingerprint(rows);
        _render(rows);
    };

    // The header's width (the window, a scrollbar): the strip may now fit
    // beside the title again, or no longer. Only a change of width measures it
    // again; the strip moving under the title changes the header's height.
    let _headerWidth = -1;
    let _headerFrame = 0;
    const _watchHeaderWidth = (widget) => {
        const header = widget && widget.querySelector('.fcc-ps-header');
        if (!header || header._fccPsWidthWatched || typeof ResizeObserver !== 'function') return;
        header._fccPsWidthWatched = true;
        new ResizeObserver((entries) => {
            const entry = entries && entries[entries.length - 1];
            const w = entry ? entry.contentRect.width : -1;
            if (w === _headerWidth) return;
            _headerWidth = w;
            if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(_headerFrame);
            _headerFrame = requestAnimationFrame(() => _fitStrip());
        }).observe(header);
    };

    // Settings: a pick applies at once and is kept in this browser, with no
    // Save (as Text size and the title bar's settings do). Delegated, so it
    // works on every redraw of the Settings card; a mouse pick and the arrow
    // keys both fire `change`.
    const _prefOf = (el) => {
        if (!el || typeof el.matches !== 'function') return null;
        return Object.keys(PREFS).find((w) => el.matches('.cfgset-input[data-key="' + PREFS[w].key + '"]')) || null;
    };
    document.addEventListener('change', (e) => {
        const which = _prefOf(e.target);
        if (!which) return;
        const name = e.target.value;
        if (!PREFS[which].choices.includes(name)) return;
        _picked[which] = name;
        let stored = true;
        try { localStorage.setItem(PREFS[which].key, name); } catch (err) { stored = false; }
        // Stored already, so "Save settings" has nothing left to do for it.
        if (stored) e.target.dataset.initial = name;
        else if (typeof window.showToast === 'function') {
            window.showToast(PREFS[which].label + ' changed, but this browser could not keep it (private mode or '
                + 'storage blocked): it goes back when the page reloads.', 'warning', 7000);
        }
        _repaint();
    });
    // A scan never picks a choice (text_size.js's rule): a scanner types into
    // whatever has the focus, and a select takes each character as type-ahead.
    // Not stopped, so the scan accumulator still reads the whole scan; the
    // arrow keys, Home / End and Page Up / Down still pick.
    document.addEventListener('keydown', (e) => {
        if (!_prefOf(e.target)) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (typeof e.key === 'string' && e.key.length === 1) e.preventDefault();
    }, true);

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
        // Enter on a focused ▲ / ▼ moves the printer, as a click does (review,
        // 2026-10-23). The dashboard's scan accumulator (scripts.html) cancels
        // every Enter outside a text field, a button's own press included, so
        // Enter never reached the arrows there (Space did). A scan ends in
        // Enter too: one still arriving (window.enterIsAScan) is left to the
        // accumulator, and the press clears the scan buffer it consumed.
        widget.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.altKey || e.metaKey) return;
            // Group 50.3 (the keyboard standing order): a head reached by Tab, a
            // tile or one in the folded strip, opens on Enter or Space, as a
            // click does. A scan's keys stay the scan's: an Enter while one is
            // arriving (window.enterIsAScan) and a Space inside a label
            // (window.scanIsArriving: a LocationID may hold one) go on to the
            // accumulator; the press clears the stray key a person may have left
            // in the scan buffer.
            const isSpace = e.key === ' ' || e.key === 'Spacebar';
            const head = (e.key === 'Enter' || isSpace) && e.target && e.target.getAttribute
                && e.target.getAttribute('role') === 'button' && typeof e.target.closest === 'function'
                ? e.target.closest('.fcc-ps-th, .fcc-ps-mini') : null;
            if (head && head === e.target && widget.contains(head)) {
                if (e.shiftKey) return;
                if (!isSpace && typeof window.enterIsAScan === 'function' && window.enterIsAScan()) return;
                if (isSpace && typeof window.scanIsArriving === 'function' && window.scanIsArriving()) return;
                e.preventDefault();
                e.stopImmediatePropagation();
                if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
                const tid = head.dataset.toolhead;
                if (tid && window.openManage) window.openManage(tid);
                return;
            }
            if (e.key !== 'Enter' || e.shiftKey) return;
            const btn = e.target && typeof e.target.closest === 'function'
                ? e.target.closest('button.fcc-ps-reorder') : null;
            if (!btn || !widget.contains(btn)) return;
            if (typeof window.enterIsAScan === 'function' && window.enterIsAScan()) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
            btn.click();
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
        // size, or the Text size, while the body had no width). Folded: the
        // strip is, for the same reason (it has no width while open).
        if (!_isCollapsed()) _balanceRows();
        else _fitStrip();
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

    // Group 50.3: the keyboard reach, in the shortcut list (the ? overlay).
    const _registerShortcuts = () => {
        if (typeof window.registerShortcut !== 'function') return;
        window.registerShortcut({
            id: 'printer-status-open-head', scope: 'Printer Status', keys: ['Tab', 'Enter'],
            description: 'Reach a toolhead (a tile, or one in the folded strip) with Tab; Enter or Space opens it, as a click does.',
        });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _registerShortcuts);
    else _registerShortcuts();

    // Exposed for tests + manual debugging.
    window.refreshPrinterStatusWidget = refresh;
})();
