/* MODULE: LOOSE SPOOLS (Group 58.4) — every spool filed at a room or a cart itself */
console.log("🚀 Loaded Module: LOOSE SPOOLS");

// window.openLooseList(opts)
//
// One list of the spools with no more exact place than a room, a cart with rows
// or a place FCC has no row for (Derek's once-over: "a list of spools filed only
// at a cart or room"), grouped by place, from GET /api/loose_spools (the rule:
// locations_db.loose_place_ids; a spool counts by its own location, exactly). It
// reads when it opens and on Try again, never on the heartbeat, and it writes
// nothing. A failed read shows the yellow notice with Try again, never "no loose
// spools" (Group 52's rule).
//
// opts:
//   tier: 'standard' (default), or 'confirm' from inside another overlay. The
//         audit panel is a standard overlay, so its entry passes 'confirm'.
//   host: a Bootstrap window; the list closes with it. The Locations window's
//         button passes #locMgrModal.
//
// Keyboard (standing order): ↑ / ↓ move the .kb-active row (wrapping), Enter opens
// the row's place, Escape closes the list only (mountOverlay owns Escape), and Tab
// stays inside the list (mountOverlay's trapTab), between ✕ and the highlighted row.
// During an audit a row opens nothing, by Enter or a click: the place would open
// behind the audit panel. A scan's Enter is left to the scan accumulator
// (scripts.html), and a scan passes on as ever: this list answers none. A window a
// scan opens meanwhile closes the list, which would otherwise sit over it (the Low
// stock list's rule). The legacy picker a scan can open mounts over it instead (same
// tier, last mounted), and the list's keys stand down while it is up.

(function () {
    const OVERLAY_ID = 'fcc-loose-list';
    const STYLE_ID = 'fcc-loose-list-style';
    let _current = null;       // the open list's handle

    const esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    const _plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

    // `state` is a script-scope let in inv_core.js, not a window property.
    const _inAudit = () => !!(typeof state !== 'undefined' && state && state.auditActive);

    // Own, overlay-scoped styles: light text on the dark panel, checked by the
    // contrast guard. Named text sizes only (global.css), and widths in rem, so the
    // window keeps its proportions at every Text size. One size whatever it shows:
    // the list is the part that scrolls.
    const P = `#${OVERLAY_ID}`;
    const CSS = `
${P} .fcc-loose-panel { background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px;
    padding:14px 16px 10px; width:min(44rem, 94vw); height:min(40rem, 86vh); box-sizing:border-box;
    display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,.6); font-size:1rem;
    outline:none; text-align:left; }
${P} .fcc-loose-head { display:flex; align-items:center; justify-content:space-between; gap:8px; flex:0 0 auto; }
${P} .fcc-loose-title { font-size:1.2em; font-weight:700; color:#fff; }
${P} .fcc-loose-close { background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:2px 10px; font-size:1em; line-height:1.4; cursor:pointer; }
${P} .fcc-loose-close:hover, ${P} .fcc-loose-close:focus-visible { border-color:#0dcaf0; outline:none; }
${P} .fcc-loose-sub { color:#ddd; font-size:var(--fcc-fs-small); margin:4px 0 8px; flex:0 0 auto; }
${P} .fcc-loose-body { overflow:auto; flex:1 1 auto; min-height:0; padding-right:4px; }
${P} .fcc-loose-place { display:flex; align-items:center; gap:8px; margin:10px 0 4px; color:#fff;
    font-size:var(--fcc-fs-row); font-weight:700; }
${P} .fcc-loose-place:first-child { margin-top:0; }
${P} .fcc-loose-place-name { color:#ddd; font-weight:500; min-width:0; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; }
${P} .fcc-loose-tag { flex:0 0 auto; background:#3a3a3a; border:1px solid #666; color:#f1f1f1; border-radius:10px;
    padding:0 7px; font-size:var(--fcc-fs-label); font-weight:500; white-space:nowrap; }
${P} .fcc-loose-count { flex:0 0 auto; margin-left:auto; min-width:1.6em; padding:0 6px; border-radius:9px;
    background:#444; color:#fff; font-size:var(--fcc-fs-label); font-weight:600; text-align:center; }
${P} .fcc-loose-row { box-sizing:border-box; display:flex; align-items:center; gap:8px; padding:4px 8px;
    min-height:2.1rem; border:1px solid #3a3a3a; border-radius:6px; margin-bottom:4px; background:#262626; color:#fff;
    font-size:var(--fcc-fs-row); cursor:pointer; outline:none; }
${P} .fcc-loose-row:hover { border-color:#777; }
${P} .fcc-loose-row.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.55); background:#16333a; }
${P} .fcc-loose-row[aria-disabled="true"] { cursor:default; }
${P} .fcc-loose-swatch { display:inline-block; width:18px; height:18px; border-radius:50%; flex:0 0 18px;
    border:1px solid #888; }
${P} .fcc-loose-name { flex:1 1 auto; min-width:0; font-weight:600; color:#fff; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; }
${P} .fcc-loose-grams { flex:0 0 auto; color:#ddd; white-space:nowrap; }
${P} .fcc-loose-state { color:#fff; text-align:center; padding:22px 8px; font-size:var(--fcc-fs-row); }
${P} .fcc-loose-notice { background:#2b2200; color:#ffd54a; border:1px solid #ffd54a; border-radius:6px;
    padding:8px 12px; font-size:var(--fcc-fs-row); font-weight:bold; }
${P} .fcc-loose-notice-sub { font-weight:normal; margin-top:2px; }
${P} .fcc-loose-retry { margin-top:10px; background:transparent; color:#ffd54a; border:1px solid #ffd54a;
    border-radius:6px; padding:4px 12px; font-size:var(--fcc-fs-row); font-weight:600; cursor:pointer; }
${P} .fcc-loose-retry:hover, ${P} .fcc-loose-retry:focus-visible { background:#ffd54a; color:#111; outline:none; }
${P} .fcc-loose-foot { color:#ccc; font-size:var(--fcc-fs-small); margin-top:8px; border-top:1px solid #333;
    padding-top:6px; flex:0 0 auto; }
/* A very short window (a phone on its side): the list keeps room for its rows. */
@media (max-height: 480px) {
    ${P} .fcc-loose-sub, ${P} .fcc-loose-foot { display:none; }
}
`;

    function _ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const st = document.createElement('style');
        st.id = STYLE_ID;
        st.textContent = CSS;
        document.head.appendChild(st);
    }

    const WHAT = 'Spools filed at a room or a cart itself, with no more exact place.';

    // The keys that do something now: with no rows drawn, only Escape.
    function _footText(hasRows) {
        if (!hasRows) return 'Esc closes';
        return _inAudit() ? '↑ ↓ move · Esc closes' : '↑ ↓ move · Enter opens the place · Esc closes';
    }

    function _shellHtml() {
        return `<div class="fcc-loose-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-loose-title" tabindex="-1">
            <div class="fcc-loose-head">
                <div class="fcc-loose-title" id="fcc-loose-title">🧺 Loose spools</div>
                <button type="button" class="fcc-loose-close" data-loose-close aria-label="Close">✕</button>
            </div>
            <div class="fcc-loose-sub" data-loose-sub>${esc(WHAT)}</div>
            <div class="fcc-loose-body" data-loose-body data-loose-state="loading">
                <div class="fcc-loose-state">Reading your spools from Spoolman…</div>
            </div>
            <div class="fcc-loose-foot" data-loose-foot>${esc(_footText(false))}</div>
        </div>`;
    }

    function _body(handle) {
        return handle && handle.panel ? handle.panel.querySelector('[data-loose-body]') : null;
    }

    function _setBody(handle, html, stateName) {
        const body = _body(handle);
        if (!body) return null;
        body.innerHTML = html;
        body.dataset.looseState = stateName;
        const foot = handle.panel.querySelector('[data-loose-foot]');
        if (foot) foot.textContent = _footText(stateName === 'ready');
        return body;
    }

    function _rows(handle) {
        const body = _body(handle);
        return body ? Array.from(body.querySelectorAll('.fcc-loose-row')) : [];
    }

    function _activeRow(handle) {
        const body = _body(handle);
        return body ? body.querySelector('.fcc-loose-row.kb-active') : null;
    }

    function _highlight(handle, idx) {
        const rows = _rows(handle);
        rows.forEach((r) => {
            r.classList.remove('kb-active');
            r.setAttribute('aria-current', 'false');
            r.tabIndex = -1;
        });
        const row = rows[idx];
        if (!row) return;
        row.classList.add('kb-active');
        row.setAttribute('aria-current', 'true');
        row.tabIndex = 0;       // the one row Tab stops at, or Tab could never come back to the list
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

    function _swatch(spool) {
        // As the Low stock list paints its swatch (inv_stock.js).
        let bg = '#333';
        let ring = '';
        try {
            const st = window.getFilamentStyle(spool.color || '333', spool.color_direction || 'longitudinal');
            bg = st.isSolid ? st.base : st.frame;
            if (st.border) ring = 'box-shadow:inset 0 0 0 2px #555;';
        } catch (_) { /* a malformed colour keeps the grey swatch */ }
        return `<span class="fcc-loose-swatch" style="background:${esc(bg)};${ring}"></span>`;
    }

    function _gramsText(spool) {
        const g = spool.remaining_weight;
        if (g === null || g === undefined || g === '' || !Number.isFinite(Number(g))) return '? g';
        return `${Math.round(Number(g))} g`;
    }

    function _rowHtml(place, spool, audit) {
        const name = String(spool.display == null ? `#${spool.id}` : spool.display);
        const title = audit ? name : `${name}: opens ${place.id}`;
        return `<div class="fcc-loose-row" tabindex="-1" data-place="${esc(place.id)}" data-spool="${esc(spool.id)}"
                    ${audit ? 'aria-disabled="true"' : 'role="button"'} title="${esc(title)}">
                ${_swatch(spool)}
                <span class="fcc-loose-name">${esc(name)}</span>
                <span class="fcc-loose-grams">${esc(_gramsText(spool))}</span>
            </div>`;
    }

    function _placeHtml(place, audit) {
        const spools = Array.isArray(place.spools) ? place.spools : [];
        const id = String(place.id == null ? '' : place.id);
        const name = String(place.name == null ? '' : place.name);
        const named = name && name !== id ? `<span class="fcc-loose-place-name">${esc(name)}</span>` : '';
        const type = String(place.type == null ? '' : place.type);
        const tag = `<span class="fcc-loose-tag">${esc(type || 'not in Locations')}</span>`;
        return `<div class="fcc-loose-place" data-loose-place="${esc(id)}">
                <span>${esc(id)}</span>${named}${tag}<span class="fcc-loose-count">${spools.length}</span>
            </div>${spools.map((s) => _rowHtml(place, s, audit)).join('')}`;
    }

    function _noticeHtml(title, text) {
        return `<div class="fcc-loose-notice" role="alert" data-loose-notice>
                <div>⚠️ ${esc(title)}</div>
                <div class="fcc-loose-notice-sub">${esc(text)}</div>
                <button type="button" class="fcc-loose-retry" data-loose-retry>↻ Try again</button>
            </div>`;
    }

    function _setSub(handle, text) {
        const sub = handle.panel.querySelector('[data-loose-sub]');
        if (sub) sub.textContent = text;
    }

    function _showFailure(handle, title, text, why) {
        _setSub(handle, WHAT);
        const body = _setBody(handle, _noticeHtml(title, text), 'error');
        const notice = body && body.querySelector('[data-loose-notice]');
        if (notice && why) notice.title = String(why);
        const retry = handle.panel.querySelector('[data-loose-retry]');
        if (retry) { try { retry.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
    }

    function _render(handle, data) {
        const places = data.places;
        const audit = _inAudit();
        if (!places.length) {
            _setSub(handle, WHAT);
            _setBody(handle, `<div class="fcc-loose-state" role="status">
                    ✅ No loose spools: none is filed at a room or a cart itself.
                </div>`, 'empty');
            try { handle.panel.focus({ preventScroll: true }); } catch (_) { /* noop */ }
            return;
        }
        const n = places.reduce((sum, p) => sum + (Array.isArray(p.spools) ? p.spools.length : 0), 0);
        _setSub(handle, `${_plural(n, 'spool', 'spools')} in ${_plural(places.length, 'place', 'places')}, `
            + 'filed at a room or a cart itself, with no more exact place.');
        _setBody(handle, places.map((p) => _placeHtml(p, audit)).join(''), 'ready');
        _highlight(handle, 0);
    }

    async function _load(handle) {
        _setSub(handle, WHAT);
        _setBody(handle, '<div class="fcc-loose-state">Reading your spools from Spoolman…</div>', 'loading');
        try { handle.panel.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        let data = null;
        try {
            const res = await window.fetchT('/api/loose_spools', { cache: 'no-store' });
            data = await res.json();
        } catch (_) {
            data = null;
        }
        if (!handle.element || !handle.element.isConnected) return;   // closed or reopened meanwhile
        if (data && data.read_ok === false) {
            _showFailure(handle, "Spoolman didn't answer",
                "FCC couldn't read your spools, so it can't tell which are loose right now. This is not an empty list.",
                data.read_error);
            return;
        }
        if (!data || data.read_ok !== true || !Array.isArray(data.places)) {
            _showFailure(handle, "FCC didn't answer",
                "The page couldn't reach FCC just now, so it can't tell which spools are loose. This is not an empty list.");
            return;
        }
        _render(handle, data);
    }

    function _unlisten(handle) {
        if (handle && handle._looseKeys) {
            document.removeEventListener('keydown', handle._looseKeys, true);
            handle._looseKeys = null;
        }
        if (handle && handle._looseShows) {
            document.removeEventListener('show.bs.modal', handle._looseShows);
            document.removeEventListener('show.bs.offcanvas', handle._looseShows);
            handle._looseShows = null;
        }
        if (_current === handle) _current = null;
    }

    // `opts.keepFocus`: another window takes the focus next.
    function _close(handle, opts) {
        _unlisten(handle);
        try { handle.cleanup(); } catch (_) { /* noop */ }
        // Back to the button that opened it, when nothing else has taken the focus.
        const opener = handle._opener;
        handle._opener = null;
        const a = document.activeElement;
        if (!(opts && opts.keepFocus) && opener && opener.isConnected && (!a || a === document.body)) {
            try { opener.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        }
    }

    // The row's own spelling of the place, as /api/locations has it: openManage
    // finds its row by that, and a place it can't find would open nothing.
    function _knownPlace(id) {
        const rows = (typeof state !== 'undefined' && state && Array.isArray(state.allLocations)) ? state.allLocations : [];
        const want = String(id).toUpperCase();
        const row = rows.find((l) => l && String(l.LocationID).toUpperCase() === want);
        return row ? row.LocationID : null;
    }

    function _openPlace(handle, id) {
        if (!id || _inAudit() || typeof window.openManage !== 'function') return;
        // A first load of the location list still on its way: openManage parks the
        // open until it lands (Group 45.8).
        const loaded = !!(typeof state !== 'undefined' && state && state.locationsLoaded);
        const known = _knownPlace(id);
        if (loaded && !known) {
            if (typeof window.showToast === 'function') {
                window.showToast(`Couldn't open ${id}: it isn't in the location list.`, 'warning', 7000);
            }
            return;
        }
        // This panel (z 20000) would hide the window: it closes first.
        _close(handle, { keepFocus: true });
        window.openManage(known || id);
    }

    function _onKey(handle, e) {
        if (!handle.element || !handle.element.isConnected) { _unlisten(handle); return; }
        // Something over the list owns the keys.
        if (typeof window.isTopOverlay === 'function' && !window.isTopOverlay(handle.element)) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!_rows(handle).length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            _move(handle, e.key === 'ArrowDown' ? 1 : -1);
            return;
        }
        if (e.key !== 'Enter') return;
        // A scanner's Enter belongs to the scan accumulator (scripts.html), and a
        // focused button must not take it as a press either.
        if (typeof window.enterIsAScan === 'function' && window.enterIsAScan()) {
            e.preventDefault();
            return;
        }
        const active = document.activeElement;
        if (active && handle.panel.contains(active) && active.tagName === 'BUTTON') return;   // a person's press of it
        const row = _activeRow(handle);
        if (!row) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
        if (typeof window.personMayPress === 'function' && !window.personMayPress(e, row)) return;
        _openPlace(handle, row.dataset.place);
    }

    // The audit panel's own list goes with it, as a `host` window's does.
    window.closeLooseList = function (handle) {
        if (handle && handle === _current) _close(handle, { keepFocus: true });
    };

    window.openLooseList = function (opts) {
        if (typeof window.mountOverlay !== 'function') return null;
        const o = opts || {};
        _ensureStyle();
        if (_current) _unlisten(_current);          // re-opening replaces the list
        const opener = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
        const openedAt = Date.now();
        const handle = window.mountOverlay({
            id: OVERLAY_ID,
            tier: o.tier === 'confirm' ? 'confirm' : 'standard',
            content: _shellHtml(),
            host: o.host || undefined,
            trapTab: true,
            // No initialFocus: _load takes it now. mountOverlay's comes a tick later,
            // and would take it back from the row a quick answer had highlighted.
            // Not the second click of a double click on the button that opened it.
            onBackdropClick: () => { if (Date.now() - openedAt >= 400) _close(handle); },
            onEscape: () => _close(handle),
        });
        _current = handle;
        handle._opener = opener;
        handle.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-loose-close]')) { _close(handle); return; }
            if (e.target.closest('[data-loose-retry]')) { _load(handle); return; }
            const row = e.target.closest('.fcc-loose-row');
            if (!row) return;
            _highlight(handle, _rows(handle).indexOf(row));
            _openPlace(handle, row.dataset.place);
        });
        handle._looseKeys = (e) => _onKey(handle, e);
        document.addEventListener('keydown', handle._looseKeys, true);
        // A window opened meanwhile (by a scan, say) sits under this panel, where
        // nobody can see it: the list gives way.
        handle._looseShows = () => _close(handle, { keepFocus: true });
        document.addEventListener('show.bs.modal', handle._looseShows);
        document.addEventListener('show.bs.offcanvas', handle._looseShows);
        _load(handle);
        return handle;
    };

    if (typeof window.registerShortcut === 'function') {
        window.registerShortcut({
            id: 'loose-list-arrows', scope: 'Loose Spools List', keys: ['↑', '↓'],
            description: 'Move between spools in the 🧺 Loose spools list (Locations window). Wraps at the ends.'
        });
        window.registerShortcut({
            id: 'loose-list-enter', scope: 'Loose Spools List', keys: ['Enter'],
            description: "Open the highlighted spool's place. Not during an audit."
        });
        window.registerShortcut({
            id: 'loose-list-escape', scope: 'Loose Spools List', keys: ['Esc'],
            description: 'Close the list.'
        });
    }
})();
