/* MODULE: LOW STOCK (Group 49.2a) — the ⚠️ Low-stock list */
console.log("🚀 Loaded Module: LOW STOCK");

// window.openLowStockPanel()
//
// Opened by the search panel's "⚠️ Low stock" button (offcanvas_search.html).
// One mountOverlay panel: Low (under the `low_stock_g` setting, fewest grams
// first) then Out (spools on record, none in stock), per filament across its
// in-stock spools, from GET /api/stock_report (stock_report.py). It asks the
// server only when it opens, never on the dashboard heartbeat (Group 45.8's
// lesson), and a failed read shows an error that says Spoolman didn't answer,
// never "Nothing is low".
//
// Each row: swatch (getFilamentStyle), Brand - Material - Color with the
// filament's attribute tags, grams and spools, a 🛒 Buy More link when one
// resolves (the server applies the filament window's rule), and a click / Enter
// that opens the filament window. Keyboard (standing order): ↑ / ↓ move the
// .kb-active row (wrapping), Enter opens it, Escape closes (mountOverlay owns
// Escape); an Enter that is a scanner's is left to the scan accumulator. Every
// piece of text is escaped: colour and vendor names are free text.

(function () {
    const OVERLAY_ID = 'fcc-low-stock-overlay';
    const STYLE_ID = 'fcc-low-stock-style';
    let _seq = 0;          // a newer load wins; an older answer never paints
    let _current = null;   // the open panel's handle

    const esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    // Own, overlay-scoped styles (never Bootstrap's colours): light text on the
    // dark panel, checked by the contrast guard (tests/test_contrast_guard.py).
    const P = `#${OVERLAY_ID}`;
    const CSS = `
${P} .fcc-stock-panel { background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px;
    padding:14px 16px 10px; width:min(600px, 94vw); max-height:84vh; display:flex; flex-direction:column;
    box-shadow:0 10px 40px rgba(0,0,0,.6); font-size:.95rem; outline:none; text-align:left; }
${P} .fcc-stock-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
${P} .fcc-stock-title { font-size:1.2em; font-weight:700; color:#fff; }
${P} .fcc-stock-close { background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:2px 10px; font-size:1em; line-height:1.4; cursor:pointer; }
${P} .fcc-stock-close:hover, ${P} .fcc-stock-close:focus-visible { border-color:#0dcaf0; outline:none; }
${P} .fcc-stock-sub { color:#ddd; font-size:.85em; margin:4px 0 6px; }
${P} .fcc-stock-body { overflow:auto; flex:1 1 auto; min-height:70px; padding-right:4px; }
${P} .fcc-stock-h { font-weight:700; margin:10px 0 6px; font-size:.95em; }
${P} .fcc-stock-h-low { color:#ffc107; }
${P} .fcc-stock-h-out { color:#ff8a8a; }
${P} .fcc-stock-row { display:flex; align-items:center; gap:10px; padding:7px 8px; border:1px solid #3a3a3a;
    border-radius:6px; margin-bottom:6px; cursor:pointer; background:#262626; color:#fff; outline:none; }
${P} .fcc-stock-row:hover { border-color:#777; }
${P} .fcc-stock-row.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.55); background:#16333a; }
${P} .fcc-stock-swatch { display:inline-block; width:22px; height:22px; border-radius:50%; flex:0 0 22px;
    border:1px solid #888; }
${P} .fcc-stock-main { flex:1 1 auto; min-width:0; }
${P} .fcc-stock-name { font-weight:600; color:#fff; overflow-wrap:anywhere; }
${P} .fcc-stock-meta { color:#ddd; font-size:.85em; }
${P} .fcc-stock-tag { display:inline-block; background:#3a3a3a; border:1px solid #666; color:#f1f1f1;
    border-radius:10px; padding:0 7px; margin-left:4px; font-size:.75em; font-weight:500; vertical-align:middle; }
${P} .fcc-stock-buy { flex:0 0 auto; color:#ffc107; border:1px solid #ffc107; border-radius:6px; padding:3px 9px;
    font-size:.85em; text-decoration:none; white-space:nowrap; background:transparent; }
${P} .fcc-stock-buy:hover, ${P} .fcc-stock-buy:focus-visible { background:#ffc107; color:#111; outline:none; }
${P} .fcc-stock-none { color:#ddd; font-style:italic; padding:0 4px 6px; }
${P} .fcc-stock-state { color:#fff; text-align:center; padding:22px 8px; }
${P} .fcc-stock-state-sub { color:#ddd; font-size:.88em; margin-top:4px; }
${P} .fcc-stock-error-title { color:#ff8a8a; font-weight:700; font-size:1.05em; margin-bottom:6px; }
${P} .fcc-stock-retry { margin-top:12px; background:transparent; color:#fff; border:1px solid #0dcaf0;
    border-radius:6px; padding:4px 12px; cursor:pointer; }
${P} .fcc-stock-retry:hover, ${P} .fcc-stock-retry:focus-visible { background:#0dcaf0; color:#111; outline:none; }
${P} .fcc-stock-foot { color:#ccc; font-size:.78em; margin-top:8px; border-top:1px solid #333; padding-top:6px; }
`;

    function _ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const st = document.createElement('style');
        st.id = STYLE_ID;
        st.textContent = CSS;
        document.head.appendChild(st);
    }

    const _plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

    // Only a web link is ever put in an href (the server answers nothing else
    // either; this is the belt to its braces).
    const _webLink = (url) => (typeof url === 'string' && /^https?:\/\//i.test(url.trim())) ? url.trim() : '';

    function _swatch(row) {
        // As the filament window paints its swatch (inv_details.js).
        let bg = '#333';
        let ring = '';
        try {
            const st = window.getFilamentStyle(row.color || '333', row.color_direction || 'longitudinal');
            bg = st.isSolid ? st.base : st.frame;
            if (st.border) ring = 'box-shadow:inset 0 0 0 2px #555;';
        } catch (_) { /* a malformed colour keeps the grey swatch */ }
        return `<span class="fcc-stock-swatch" style="background:${esc(bg)};${ring}"></span>`;
    }

    function _rowHtml(row, kind) {
        const grams = Math.round(Number(row.grams) || 0);
        const inStock = Number(row.spools) || 0;
        const total = Number(row.spools_total) || 0;
        const meta = kind === 'out'
            ? `0 g · none in stock (${_plural(total, 'spool', 'spools')} archived or empty)`
            : `${grams} g left in ${_plural(inStock, 'spool', 'spools')}`;
        const tags = (Array.isArray(row.attributes) ? row.attributes : [])
            .map((a) => `<span class="fcc-stock-tag">${esc(a)}</span>`).join('');
        const link = _webLink(row.buy_url);
        const buy = link
            ? `<a class="fcc-stock-buy" href="${esc(link)}" target="_blank" rel="noopener noreferrer"
                  title="Buy more ${esc(row.display)}">🛒 Buy More</a>`
            : '';
        return `<div class="fcc-stock-row" role="button" tabindex="-1" data-fid="${esc(row.filament_id)}"
                    data-kind="${kind}">
                ${_swatch(row)}
                <div class="fcc-stock-main">
                    <div class="fcc-stock-name">${esc(row.display)}${tags}</div>
                    <div class="fcc-stock-meta">${esc(meta)}</div>
                </div>
                ${buy}
            </div>`;
    }

    function _shellHtml() {
        return `<div class="fcc-stock-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-stock-title" tabindex="-1">
            <div class="fcc-stock-head">
                <div class="fcc-stock-title" id="fcc-stock-title">⚠️ Low stock</div>
                <button type="button" class="fcc-stock-close" data-stock-close aria-label="Close">✕</button>
            </div>
            <div class="fcc-stock-sub" data-stock-sub>Per filament, across its in-stock spools.</div>
            <div class="fcc-stock-body" data-stock-body data-stock-state="loading">
                <div class="fcc-stock-state">Reading your spools from Spoolman…</div>
            </div>
            <div class="fcc-stock-foot">↑ ↓ move · Enter opens the filament · Esc closes</div>
        </div>`;
    }

    function _body(handle) {
        return handle && handle.panel ? handle.panel.querySelector('[data-stock-body]') : null;
    }

    function _setBody(handle, html, stateName) {
        const body = _body(handle);
        if (!body) return null;
        body.innerHTML = html;
        body.dataset.stockState = stateName;
        return body;
    }

    function _errorHtml(data) {
        const ours = data && data.error === 'report_failed';
        const title = ours ? "⚠️ FCC couldn't build the list" : "⚠️ Spoolman didn't answer";
        const text = ours
            ? (data.msg || "Something went wrong building the Low-stock list.")
            : "FCC couldn't read your spools, so it can't tell what is low right now. This is not an empty list.";
        return `<div class="fcc-stock-state" role="alert">
                <div class="fcc-stock-error-title">${esc(title)}</div>
                <div>${esc(text)}</div>
                <button type="button" class="fcc-stock-retry" data-stock-retry>↻ Try again</button>
            </div>`;
    }

    function _section(kind, rows, threshold) {
        const head = kind === 'low'
            ? `Low: under ${esc(Math.round(threshold))} g (${rows.length})`
            : `Out: none left in stock (${rows.length})`;
        const none = kind === 'low' ? 'Nothing is low.' : 'Nothing is out.';
        return `<div class="fcc-stock-section" data-stock-section="${kind}">
                <div class="fcc-stock-h fcc-stock-h-${kind}">${head}</div>
                ${rows.length ? rows.map((r) => _rowHtml(r, kind)).join('') : `<div class="fcc-stock-none">${none}</div>`}
            </div>`;
    }

    function _rows(handle) {
        return handle && handle.panel ? Array.from(handle.panel.querySelectorAll('.fcc-stock-row')) : [];
    }

    function _highlight(handle, idx) {
        const rows = _rows(handle);
        rows.forEach((r) => { r.classList.remove('kb-active'); r.setAttribute('aria-selected', 'false'); });
        const row = rows[idx];
        if (!row) return;
        row.classList.add('kb-active');
        row.setAttribute('aria-selected', 'true');
        try { row.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        try { row.scrollIntoView({ block: 'nearest' }); } catch (_) { /* noop */ }
    }

    function _move(handle, delta) {
        const rows = _rows(handle);
        if (!rows.length) return;
        const cur = rows.findIndex((r) => r.classList.contains('kb-active'));
        const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1) : (cur + delta + rows.length) % rows.length;
        _highlight(handle, next);
    }

    function _render(handle, data) {
        const low = data.low, out = data.out;
        const threshold = Number.isFinite(Number(data.threshold_g)) ? Number(data.threshold_g) : 250;
        const sub = handle.panel.querySelector('[data-stock-sub]');
        if (sub) {
            sub.textContent = `Per filament, across its in-stock spools: low is under ${Math.round(threshold)} g `
                + '(⚙️ Settings → Behavior), out is none left.';
        }
        if (!low.length && !out.length) {
            _setBody(handle, `<div class="fcc-stock-state">
                    <div>✅ Nothing is low.</div>
                    <div class="fcc-stock-state-sub">No filament is under ${esc(Math.round(threshold))} g,
                        and none has run out.</div>
                </div>`, 'empty');
            try { handle.panel.focus({ preventScroll: true }); } catch (_) { /* noop */ }
            return;
        }
        _setBody(handle, _section('low', low, threshold) + _section('out', out, threshold), 'ready');
        _highlight(handle, 0);
    }

    async function _load(handle) {
        const token = ++_seq;
        _setBody(handle, '<div class="fcc-stock-state">Reading your spools from Spoolman…</div>', 'loading');
        let res = null;
        let data = null;
        try {
            res = await fetch('/api/stock_report', { cache: 'no-store' });
            try { data = await res.json(); } catch (_) { data = null; }
        } catch (_) {
            res = null;
        }
        if (token !== _seq || !handle.element || !handle.element.isConnected) return;   // closed or reopened
        const good = res && res.ok && data && data.success === true
            && Array.isArray(data.low) && Array.isArray(data.out);
        if (!good) {
            _setBody(handle, _errorHtml(data), 'error');
            const retry = handle.panel.querySelector('[data-stock-retry]');
            if (retry) { try { retry.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
            return;
        }
        _render(handle, data);
    }

    function _unlisten(handle) {
        if (handle && handle._stockKeys) {
            document.removeEventListener('keydown', handle._stockKeys, true);
            handle._stockKeys = null;
        }
        if (_current === handle) _current = null;
    }

    function _close(handle) {
        _unlisten(handle);
        try { handle.cleanup(); } catch (_) { /* noop */ }
    }

    function _openFilament(handle, fid) {
        const id = parseInt(fid, 10);
        if (!Number.isFinite(id)) return;
        _close(handle);
        // A details window is a Bootstrap modal: this panel (z 20000) would hide
        // it, so the panel closes first; showing the modal also closes the search
        // panel underneath (inv_core.js's show.bs.modal handler).
        if (typeof openFilamentDetails === 'function') openFilamentDetails(id);
        else if (typeof window.openFilamentDetails === 'function') window.openFilamentDetails(id);
    }

    function _onKey(handle, e) {
        if (!handle.element || !handle.element.isConnected) {
            // Closed by another path (its host closing): stop listening.
            _unlisten(handle);
            return;
        }
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!_rows(handle).length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            _move(handle, e.key === 'ArrowDown' ? 1 : -1);
            return;
        }
        if (e.key !== 'Enter') return;
        // A scanner's Enter belongs to the scan accumulator (scripts.html).
        if (typeof window.enterIsAScan === 'function' && window.enterIsAScan()) return;
        const active = document.activeElement;
        const onControl = active && handle.panel.contains(active)
            && (active.tagName === 'A' || active.tagName === 'BUTTON');
        const row = onControl ? null : handle.panel.querySelector('.fcc-stock-row.kb-active');
        if (!onControl && !row) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
        if (onControl) active.click();
        else _openFilament(handle, row.dataset.fid);
    }

    window.openLowStockPanel = function () {
        if (typeof window.mountOverlay !== 'function') return null;
        _ensureStyle();
        if (_current) _unlisten(_current);     // re-opening replaces the panel
        const host = document.getElementById('offcanvasSearch');
        const hostOpen = !!(host && host.classList.contains('show'));
        const handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: _shellHtml(),
            host: hostOpen ? host : undefined,      // closes with the search panel
            occlude: hostOpen ? ['#offcanvasSearch select'] : undefined,
            initialFocus: '.fcc-stock-panel',
            onBackdropClick: () => _close(handle),
            onEscape: () => _close(handle),
        });
        _current = handle;
        handle.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-stock-close]')) { _close(handle); return; }
            if (e.target.closest('[data-stock-retry]')) { _load(handle); return; }
            if (e.target.closest('a')) return;          // Buy More opens its own tab
            const row = e.target.closest('.fcc-stock-row');
            if (row) _openFilament(handle, row.dataset.fid);
        });
        handle._stockKeys = (e) => _onKey(handle, e);
        document.addEventListener('keydown', handle._stockKeys, true);
        _load(handle);
        return handle;
    };

    function _wireButton() {
        const btn = document.getElementById('global-search-low-stock');
        if (btn && !btn.dataset.lowStockWired) {
            btn.dataset.lowStockWired = '1';
            btn.addEventListener('click', () => window.openLowStockPanel());
        }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wireButton);
    else _wireButton();

    if (typeof window.registerShortcut === 'function') {
        window.registerShortcut({
            id: 'low-stock-arrows', scope: 'Low Stock List', keys: ['↑', '↓'],
            description: 'Move between filaments in the ⚠️ Low stock list (search panel). Wraps at the ends.'
        });
        window.registerShortcut({
            id: 'low-stock-enter', scope: 'Low Stock List', keys: ['Enter'],
            description: 'Open the highlighted filament.'
        });
        window.registerShortcut({
            id: 'low-stock-escape', scope: 'Low Stock List', keys: ['Esc'],
            description: 'Close the list.'
        });
    }
})();
