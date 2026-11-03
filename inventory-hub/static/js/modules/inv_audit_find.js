/* MODULE: FIND A SPOOL (Group 58; Derek's answers of 2026-11-03, A2) — a spool here with no label to scan */
console.log("🚀 Loaded Module: AUDIT FIND");

// window.openAuditFind(opts) -> handle
//
// Derek, 2026-11-03: "I think some spools are in the system, with a location, but no
// barcode. So the b part would be a way to manually search for the spool and select it
// for that location." The audit panel's 🔎 Find a spool button and its / key open this
// over the panel (a mountOverlay at the confirm tier; Tab stays inside it): a text box,
// focused, and the spools the search finds. A pick (Enter on the highlighted row, a
// click or a tap) closes it and sends ID:<id> with source 'search' through
// window.sendInScanOrder, in its turn behind scans already read: exactly what a search
// card's click does, so the audit's own spool path makes the spool found (on the list)
// or an Extra (not), with no label read, as the last found. It writes nothing itself.
//
// Searching: /api/search?q=…&type=spool&strict=1, debounced, and only the newest answer
// paints, by this window's own count. A search that fails says "Couldn't search: …",
// never "No matches": `strict` makes a Spoolman that didn't answer the route's
// success:false, where the search panel's own reads answer an empty list. An empty box
// shows a hint. Archived spools aren't listed.
//
// Each row is the swatch and "#id name"; where FCC has it (its place and slot, "loaded
// on" a head, "loaded from" its box for a spool on a printer, Unassigned, or the ❓ Lost
// words of a spool an audit parked at Unknown, window.auditLostWords); and a tag when it
// is on this audit's list ("on the list") or found already ("✅ found"), from opts.tagOf.
//
// Keyboard (standing order): the box has the focus on open. ↓ / ↑ go to the list and
// move the highlighted row (wrapping), which is the list's one stop in the Tab order, so
// Tab moves between the box and the list. Enter on a row picks it: rows are real buttons,
// pressed through the scan accumulator's rules (a scan's Enter presses nothing, nor does
// a Space inside a scan). Enter in the box searches now and picks nothing: a slow
// scanner's digits-only label typed there is a person's text, and its Enter (or the
// second Enter of a scanner set to CR LF) must not pick whatever the list shows. / goes
// back to the box. Escape closes only this window (mountOverlay owns it).
// A label scanned into the box goes to the scan path and never into the search
// (installFieldScanCapture), and the box gets its text back. The audit panel closes this
// on a scan the audit takes, and with itself; a Bootstrap window that opens meanwhile
// closes it too (the 🧺 list's rule: it would sit under this).
//
// opts:
//   tagOf(id): 'listed' | 'found' | null, what the audit says of the spool now.
//   onClose(handle, picked): told when it closes, and whether a pick closed it.
//   opener: where the keyboard goes when it closes (default: what had it).

(function () {
    const OVERLAY_ID = 'fcc-audit-find';
    const STYLE_ID = 'fcc-audit-find-style';
    const DEBOUNCE_MS = 250;
    // The search reads every spool from Spoolman, and the route waits up to 10 s for it.
    const SEARCH_TIMEOUT_MS = 20000;
    const MAX_ROWS = 30;
    // A double click's second press, inv_cmd.js's figures: under 700 ms after the
    // first, at its spot (16 px for a mouse, 40 for a finger).
    const DOUBLE_PRESS_MS = 700;
    const DOUBLE_PRESS_SLOP_PX = { mouse: 16, other: 40 };
    const HINT = 'Type a name, colour, brand or number.';
    const TOOLHEAD_TYPES = ['Tool Head', 'MMU Slot', 'No MMU Direct Load'];
    let _current = null;
    let _captureOn = false;

    const esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    // Own, overlay-scoped styles, the 🧺 list's look: light text on the dark panel,
    // checked by the contrast guard; named text sizes only, widths in rem, one size
    // whatever it shows (the list is the part that scrolls).
    const P = `#${OVERLAY_ID}`;
    const CSS = `
${P} .fcc-find-panel { background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px;
    padding:14px 16px 10px; width:min(40rem, 94vw); height:min(36rem, 86vh); box-sizing:border-box;
    display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,.6); font-size:1rem;
    outline:none; text-align:left; container:fcc-find-panel / inline-size; }
${P} .fcc-find-head { display:flex; align-items:center; justify-content:space-between; gap:8px; flex:0 0 auto; }
${P} .fcc-find-title { font-size:1.2em; font-weight:700; color:#fff; }
${P} .fcc-find-close { background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:2px 10px; font-size:1em; line-height:1.4; cursor:pointer; }
${P} .fcc-find-close:hover, ${P} .fcc-find-close:focus-visible { border-color:#0dcaf0; outline:none; }
${P} .fcc-find-sub { color:#ddd; font-size:var(--fcc-fs-small); margin:4px 0 8px; flex:0 0 auto; }
${P} .fcc-find-box { flex:0 0 auto; box-sizing:border-box; width:100%; background:#111; color:#fff;
    border:1px solid #777; border-radius:6px; padding:6px 10px; font-size:var(--fcc-fs-row); outline:none; }
${P} .fcc-find-box::placeholder { color:#bbb; opacity:1; }
${P} .fcc-find-box:focus { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.45); }
${P} .fcc-find-notice { flex:0 0 auto; margin-top:8px; padding:6px 10px; border-radius:6px; background:#4a3200;
    color:#ffd27a; border:1px solid #ffb74d; font-weight:bold; font-size:var(--fcc-fs-row); overflow-wrap:anywhere; }
${P} .fcc-find-notice[hidden] { display:none; }
${P} .fcc-find-body { overflow:auto; flex:1 1 auto; min-height:0; margin-top:8px; padding-right:4px; }
${P} .fcc-find-row { box-sizing:border-box; display:flex; align-items:center; gap:8px; width:100%; padding:4px 8px;
    min-height:2.6rem; border:1px solid #3a3a3a; border-radius:6px; margin:0 0 4px; background:#262626; color:#fff;
    font:inherit; font-size:var(--fcc-fs-row); text-align:left; cursor:pointer; outline:none; }
${P} .fcc-find-row:hover { border-color:#777; }
${P} .fcc-find-row.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.55); background:#16333a; }
${P} .fcc-find-swatch { display:inline-block; width:18px; height:18px; border-radius:50%; flex:0 0 18px;
    border:1px solid #888; }
${P} .fcc-find-main { flex:1 1 0; min-width:0; display:block; }
/* The name wraps, never cut: its colour is what tells two spools apart, and a touch
   screen can't show the row's title (review of 7e3720f, P-4: "#260 … (Glow G…" and
   "#270 … (Glow Gr…" on a phone). */
${P} .fcc-find-name { display:block; font-weight:600; color:#fff; overflow-wrap:anywhere; }
${P} .fcc-find-where { display:block; color:#ddd; font-size:var(--fcc-fs-small); overflow-wrap:anywhere; }
${P} .fcc-find-tag { flex:0 0 auto; border-radius:10px; padding:0 7px; font-size:var(--fcc-fs-label); font-weight:600;
    white-space:nowrap; }
${P} .fcc-find-tag-listed { background:#073b4c; border:1px solid #0dcaf0; color:#bff3ff; }
${P} .fcc-find-tag-found { background:#0a2a0a; border:1px solid #3fbf3f; color:#b6f5b6; }
${P} .fcc-find-state { color:#fff; text-align:center; padding:22px 8px; font-size:var(--fcc-fs-row); }
${P} .fcc-find-more { color:#ddd; text-align:center; padding:4px 8px 8px; font-size:var(--fcc-fs-small); }
${P} .fcc-find-fail { background:#2b2200; color:#ffd54a; border:1px solid #ffd54a; border-radius:6px;
    padding:8px 12px; font-size:var(--fcc-fs-row); font-weight:bold; overflow-wrap:anywhere; }
${P} .fcc-find-retry { margin-top:10px; background:transparent; color:#ffd54a; border:1px solid #ffd54a;
    border-radius:6px; padding:4px 12px; font-size:var(--fcc-fs-row); font-weight:600; cursor:pointer; }
${P} .fcc-find-retry:hover, ${P} .fcc-find-retry:focus-visible { background:#ffd54a; color:#111; outline:none; }
${P} .fcc-find-foot { color:#ccc; font-size:var(--fcc-fs-small); margin-top:8px; border-top:1px solid #333;
    padding-top:6px; flex:0 0 auto; }
/* A narrow window (a phone): the tag goes under the name, which keeps the row's width.
   In rem, so it comes at the same point at every Text size. */
@container fcc-find-panel (max-width: 30rem) {
    ${P} .fcc-find-row { flex-wrap:wrap; row-gap:2px; }
    ${P} .fcc-find-row [data-find-tag]:not(:empty) { flex:1 0 100%; padding-left:26px; }
}
/* A very short window (a phone on its side): the list keeps room for its rows. */
@media (max-height: 480px) {
    ${P} .fcc-find-sub, ${P} .fcc-find-foot { display:none; }
}
`;

    function _ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const st = document.createElement('style');
        st.id = STYLE_ID;
        st.textContent = CSS;
        document.head.appendChild(st);
    }

    // A label scanned into the box is a scan, never a search: the shared capture sends
    // it to the scan path and gives the box its text back (Group 61's rule for a box no
    // scan belongs in: a whole label at any speed, any burst, digits faster than a
    // person types). Installed once, before this window's own key listener, so a
    // scan's Enter never reaches it.
    function _ensureScanCapture() {
        if (_captureOn || typeof window.installFieldScanCapture !== 'function') return;
        _captureOn = true;
        window.installFieldScanCapture({
            match: (el) => !!(el && el.matches && el.matches('[data-find-box]')),
            isScanPayload: (txt) => (typeof window.looksLikeScanPayload === 'function'
                ? window.looksLikeScanPayload(txt) : /[:/]/.test(txt)),
            labels: true,
        });
    }

    const FOOT = '↓ to the list · Enter picks · / to the box · Esc closes';

    function _shellHtml() {
        return `<div class="fcc-find-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-find-title" tabindex="-1">
            <div class="fcc-find-head">
                <div class="fcc-find-title" id="fcc-find-title">🔎 Find a spool</div>
                <button type="button" class="fcc-find-close" data-find-close aria-label="Close">✕</button>
            </div>
            <div class="fcc-find-sub">A spool here with no label to scan: find it, and pick it. It counts as found here, with no label read.</div>
            <input type="text" class="fcc-find-box" data-find-box autocomplete="off" spellcheck="false"
                   placeholder="${esc(HINT)}" aria-label="Find a spool by its name, colour, brand or number">
            <div class="fcc-find-notice" role="alert" data-find-notice hidden></div>
            <div class="fcc-find-body" data-find-body data-find-state="hint">
                <div class="fcc-find-state">${esc(HINT)}</div>
            </div>
            <div class="fcc-find-foot">${esc(FOOT)}</div>
        </div>`;
    }

    const _alive = (handle) => !!(handle && !handle._closed && handle.element && handle.element.isConnected);
    const _body = (handle) => handle.panel.querySelector('[data-find-body]');
    const _box = (handle) => handle.panel.querySelector('[data-find-box]');
    const _rows = (handle) => Array.from(_body(handle).querySelectorAll('.fcc-find-row'));

    function _setBody(handle, html, stateName) {
        const body = _body(handle);
        body.innerHTML = html;
        body.dataset.findState = stateName;
        return body;
    }

    // One row highlighted, and the list's one stop in the Tab order. `focus`: the
    // keyboard goes to it (an arrow); a fresh answer only marks it, the box keeps it.
    function _highlight(handle, idx, focus) {
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
        row.tabIndex = 0;
        if (focus) { try { row.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        try { row.scrollIntoView({ block: 'nearest' }); } catch (_) { /* noop */ }
    }

    function _move(handle, delta) {
        const rows = _rows(handle);
        if (!rows.length) return;
        const cur = rows.indexOf(document.activeElement);
        const next = cur < 0
            ? Math.max(0, rows.findIndex((r) => r.classList.contains('kb-active')))
            : (cur + delta + rows.length) % rows.length;
        _highlight(handle, next, true);
    }

    function _swatch(spool) {
        // As the 🧺 list and the Low stock list paint theirs.
        let bg = '#333';
        let ring = '';
        try {
            const st = window.getFilamentStyle(spool.color || '333', spool.color_direction || 'longitudinal');
            bg = st.isSolid ? st.base : st.frame;
            if (st.border) ring = 'box-shadow:inset 0 0 0 2px #555;';
        } catch (_) { /* a malformed colour keeps the grey swatch */ }
        return `<span class="fcc-find-swatch" style="background:${esc(bg)};${ring}"></span>`;
    }

    // A place the page knows as a toolhead (the Locations list, or the printers' heads).
    // state.printerMap is /api/printer_map's `printers`, {"<printer name>": [{location_id,
    // position}, ...]}: its keys are printer names, so the heads are its entries' ids
    // (review of 7e3720f, P-6: the keys were read, and a head missing from the Locations
    // list read "📍 XL-1", not "🔗 loaded on XL-1").
    function _isHead(loc) {
        const want = String(loc).toUpperCase();
        const st = (typeof state !== 'undefined' && state) ? state : null;
        const rows = st && Array.isArray(st.allLocations) ? st.allLocations : [];
        const row = rows.find((l) => l && String(l.LocationID).toUpperCase() === want);
        if (row) return TOOLHEAD_TYPES.includes(row.Type);
        const map = st && st.printerMap && typeof st.printerMap === 'object' ? st.printerMap : {};
        return Object.values(map).some((heads) => Array.isArray(heads)
            && heads.some((h) => h && String(h.location_id).toUpperCase() === want));
    }

    // Where FCC has it, from the search's own row: `location` is the spool's own, or
    // its box for a spool on a printer with a trail (`is_ghost`, the search card's
    // "Deployed"), and `slot` that box's.
    function _whereWords(r) {
        const loc = String(r.location == null ? '' : r.location).trim();
        const slot = String(r.slot == null ? '' : r.slot).trim();
        if (!loc || loc.toUpperCase() === 'UNASSIGNED') return 'Unassigned';
        if (loc.toUpperCase() === 'UNKNOWN') {
            const lost = window.auditLostWords ? window.auditLostWords(r.details && r.details.lost_from) : null;
            return lost ? `❓ Lost: ${lost.where}` : '❓ Unknown';
        }
        const at = slot ? `${loc} slot ${slot}` : loc;
        if (r.is_ghost) return `🔗 loaded from ${at}`;
        if (_isHead(loc)) return `🔗 loaded on ${loc}`;
        return `📍 ${at}`;
    }

    const _name = (r) => {
        const text = String(r.display == null ? '' : r.display);
        return text.startsWith(`#${r.id}`) ? text : `#${r.id} ${text}`.trim();
    };

    function _tagHtml(tag) {
        if (tag === 'found') return '<span class="fcc-find-tag fcc-find-tag-found">✅ found</span>';
        if (tag === 'listed') return '<span class="fcc-find-tag fcc-find-tag-listed">on the list</span>';
        return '';
    }

    function _tagOf(handle, id) {
        try { return handle._tagOf ? handle._tagOf(id) : null; } catch (_) { return null; }
    }

    function _rowHtml(handle, r) {
        const name = _name(r);
        const where = _whereWords(r);
        return `<button type="button" class="fcc-find-row" tabindex="-1" data-find-id="${esc(Number(r.id))}"
                    title="${esc(`${name} · ${where}. Pick it: found here, no label read`)}">
                ${_swatch(r)}
                <span class="fcc-find-main"><span class="fcc-find-name">${esc(name)}</span><span class="fcc-find-where">${esc(where)}</span></span>
                <span data-find-tag>${_tagHtml(_tagOf(handle, r.id))}</span>
            </button>`;
    }

    function _showHint(handle) {
        _setBody(handle, `<div class="fcc-find-state">${esc(HINT)}</div>`, 'hint');
    }

    function _fail(handle, why) {
        _setBody(handle, `<div class="fcc-find-fail" role="alert" data-find-fail>
                <div>⚠️ Couldn't search: ${esc(why)}</div>
                <button type="button" class="fcc-find-retry" data-find-retry>↻ Try again</button>
            </div>`, 'error');
    }

    function _paint(handle, raw, results) {
        const want = raw.replace(/^#/, '');
        const live = results.filter((r) => r && r.id != null && !r.archived && (r.type || 'spool') === 'spool');
        // The spool whose number was typed comes first: the search matches "57" inside
        // #157 and #570 too, and lists the newest first.
        live.sort((a, b) => Number(String(b.id) === want) - Number(String(a.id) === want));
        const shown = live.slice(0, MAX_ROWS);
        if (!shown.length) {
            _setBody(handle, `<div class="fcc-find-state" role="status">No spool matches “${esc(raw)}”.</div>`, 'empty');
            return;
        }
        const more = live.length - shown.length;
        _setBody(handle, shown.map((r) => _rowHtml(handle, r)).join('')
            + (more > 0 ? `<div class="fcc-find-more">and ${more} more: type more to narrow it</div>` : ''), 'ready');
        _highlight(handle, 0, false);
    }

    function _run(handle, raw) {
        handle._seq += 1;
        const seq = handle._seq;
        const q = raw.replace(/#(\d)/g, '$1');
        if (!_rows(handle).length) _setBody(handle, '<div class="fcc-find-state" role="status">Searching…</div>', 'loading');
        const params = new URLSearchParams({ q, type: 'spool', strict: '1' });
        window.fetchT(`/api/search?${params.toString()}`, { cache: 'no-store' }, SEARCH_TIMEOUT_MS)
            .then((res) => res.json().then((data) => ({ res, data }), () => ({ res, data: null })))
            .then(({ res, data }) => {
                if (seq !== handle._seq || !_alive(handle)) return;
                if (!res.ok) { _fail(handle, `FCC answered with an error (HTTP ${res.status}).`); return; }
                if (!data || typeof data !== 'object') { _fail(handle, "FCC's answer couldn't be read."); return; }
                if (data.success !== true || !Array.isArray(data.results)) {
                    _fail(handle, String(data.msg || data.error || 'the search went wrong.'));
                    return;
                }
                _paint(handle, raw, data.results);
            }, () => {
                if (seq !== handle._seq || !_alive(handle)) return;
                _fail(handle, "FCC didn't answer.");
            });
    }

    // `now`: Enter or Try again, past the wait for more keys.
    function _search(handle, now) {
        clearTimeout(handle._timer);
        handle._timer = null;
        const raw = String(_box(handle).value || '').trim();
        if (!raw) {
            handle._seq += 1;      // an answer still out paints nothing
            _showHint(handle);
            return;
        }
        // A label on its way to the scan path (its Enter gives the box its text back).
        if (window.fccIsLabel && window.fccIsLabel(raw)) return;
        if (now) _run(handle, raw);
        else handle._timer = setTimeout(() => { handle._timer = null; if (_alive(handle)) _run(handle, raw); }, DEBOUNCE_MS);
    }

    function _unlisten(handle) {
        if (handle._findKeys) {
            document.removeEventListener('keydown', handle._findKeys, true);
            handle._findKeys = null;
        }
        if (handle._findShows) {
            document.removeEventListener('show.bs.modal', handle._findShows);
            document.removeEventListener('show.bs.offcanvas', handle._findShows);
            handle._findShows = null;
        }
        if (_current === handle) _current = null;
    }

    // `opts.picked`: a pick closed it. `opts.keepFocus`: another window takes the focus.
    function _close(handle, opts) {
        if (!handle || handle._closed) return;
        handle._closed = true;
        clearTimeout(handle._timer);
        handle._seq += 1;
        _unlisten(handle);
        try { handle.cleanup(); } catch (_) { /* noop */ }
        // Back to the button that opened it, when nothing else has taken the focus.
        const opener = handle._opener;
        handle._opener = null;
        const a = document.activeElement;
        if (!(opts && opts.keepFocus) && opener && opener.isConnected && (!a || a === document.body)) {
            try { opener.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        }
        if (typeof handle._onClose === 'function') {
            try { handle._onClose(handle, !!(opts && opts.picked)); } catch (_) { /* noop */ }
        }
    }

    function _pick(handle, row) {
        if (!_alive(handle) || !row) return;
        const sid = Number(row.dataset.findId);
        if (!Number.isFinite(sid)) return;
        _close(handle, { picked: true });
        (window.sendInScanOrder || window.processScan)(`ID:${sid}`, 'search');
    }

    function _focusBox(handle) {
        try { _box(handle).focus({ preventScroll: true }); } catch (_) { /* noop */ }
    }

    // ↻ Try again's press, for _secondPress: where and when, from a pointer.
    function _noteRetry(handle, e) {
        handle._retryPress = e.detail > 0
            ? { at: Date.now(), x: e.clientX, y: e.clientY, slop: DOUBLE_PRESS_SLOP_PX[e.pointerType === 'mouse' ? 'mouse' : 'other'] }
            : null;
    }

    // A row's click that is the second press of a double click picks nothing (review of
    // 7e3720f, P-1). A row's own first click picks it and closes Find, so a second click
    // only lands on a row the first click brought under the pointer: ↻ Try again's
    // answer paints the rows where the button was, often inside a person's double click
    // (a search answers in 85 to 190 ms), and the second click picked a spool nobody
    // chose, found here or an Extra that Done files here. The browser counts the clicks
    // (`detail`); a finger's second tap, or a mouse slower than the system's double
    // click, is caught by the time and spot of the Try again press. A keyboard's click
    // (detail 0) always picks.
    function _secondPress(handle, e) {
        if (e.detail > 1) return true;
        const p = handle._retryPress;
        if (!p || e.detail === 0 || Date.now() - p.at >= DOUBLE_PRESS_MS) return false;
        return Math.abs(e.clientX - p.x) <= p.slop && Math.abs(e.clientY - p.y) <= p.slop;
    }

    function _onKey(handle, e) {
        if (!_alive(handle)) { _unlisten(handle); return; }
        // Something over the window owns the keys (the ⌨️ list, a picker a scan opened).
        if (typeof window.isTopOverlay === 'function' && !window.isTopOverlay(handle.element)) return;
        const shortcuts = document.getElementById('fcc-shortcuts-overlay');
        if (shortcuts && shortcuts.getClientRects().length) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const box = _box(handle);
        const inBox = e.target === box;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            const rows = _rows(handle);
            if (!rows.length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (!inBox) { _move(handle, e.key === 'ArrowDown' ? 1 : -1); return; }
            const marked = rows.findIndex((r) => r.classList.contains('kb-active'));
            _highlight(handle, e.key === 'ArrowDown' ? Math.max(0, marked) : rows.length - 1, true);
            return;
        }
        if (e.key === '/' && !inBox) {
            // The '/' of a URL a scan carries is the scan's.
            if (e.repeat || (window.scanIsArriving && window.scanIsArriving())) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
            try { box.focus({ preventScroll: true }); box.select(); } catch (_) { /* noop */ }
            return;
        }
        // A person's Enter in the box: search now. A scan's never gets here (the field
        // capture, registered first, takes it), and nothing is picked from the box.
        if (e.key === 'Enter' && inBox) {
            e.preventDefault();
            if (!e.repeat) _search(handle, true);
        }
    }

    // The tags again, from what the audit says now (the panel calls it as it redraws).
    window.retagAuditFind = function (handle) {
        if (!_alive(handle)) return;
        _rows(handle).forEach((row) => {
            const slot = row.querySelector('[data-find-tag]');
            if (slot) slot.innerHTML = _tagHtml(_tagOf(handle, Number(row.dataset.findId)));
        });
    };

    // A refusal the panel says (its notice is under this window), or '' to clear it.
    window.auditFindNotice = function (handle, msg) {
        if (!_alive(handle)) return;
        const el = handle.panel.querySelector('[data-find-notice]');
        if (!el) return;
        el.textContent = msg || '';
        el.hidden = !msg;
    };

    window.closeAuditFind = function (handle) {
        const h = handle || _current;
        if (h && h === _current) _close(h);
    };

    window.isAuditFindOpen = () => !!_current;

    window.openAuditFind = function (opts) {
        if (typeof window.mountOverlay !== 'function') return null;
        const o = opts || {};
        _ensureStyle();
        _ensureScanCapture();
        if (_current) _close(_current, { keepFocus: true });      // one at a time
        // Where the keyboard goes back to: the caller's (the panel's 🔎, also for a / that
        // opened it with the keyboard behind the panel), else what had it.
        const active = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
        const opener = (o.opener && o.opener.nodeType === 1) ? o.opener : active;
        const openedAt = Date.now();
        let handle = null;
        handle = window.mountOverlay({
            id: OVERLAY_ID,
            tier: 'confirm',
            content: _shellHtml(),
            trapTab: true,
            // Not the second click of a double click on the button that opened it.
            onBackdropClick: () => { if (Date.now() - openedAt >= 400) _close(handle); },
            onEscape: () => _close(handle),
        });
        _current = handle;
        handle._opener = opener;
        handle._tagOf = typeof o.tagOf === 'function' ? o.tagOf : null;
        handle._onClose = typeof o.onClose === 'function' ? o.onClose : null;
        handle._seq = 0;
        handle._timer = null;
        handle._closed = false;
        handle._retryPress = null;
        const box = _box(handle);
        box.addEventListener('input', () => _search(handle, false));
        handle.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-find-close]')) { _close(handle); return; }
            if (e.target.closest('[data-find-retry]')) { _noteRetry(handle, e); _search(handle, true); return; }
            const row = e.target.closest('.fcc-find-row');
            if (!row) return;
            // Its mousedown put the keyboard on the row, which shows no ring until the
            // arrows reach it: back to the box, where an Enter picks nothing.
            if (_secondPress(handle, e)) { _focusBox(handle); return; }
            _pick(handle, row);
        });
        handle._findKeys = (e) => _onKey(handle, e);
        document.addEventListener('keydown', handle._findKeys, true);
        handle._findShows = () => _close(handle, { keepFocus: true });
        document.addEventListener('show.bs.modal', handle._findShows);
        document.addEventListener('show.bs.offcanvas', handle._findShows);
        // Now: mountOverlay's initialFocus comes a tick later.
        try { box.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        return handle;
    };

    if (typeof window.registerShortcut === 'function') {
        window.registerShortcut({
            id: 'audit-find-arrows', scope: 'Find a Spool', keys: ['↑', '↓'],
            description: 'From the box to the list, and between its spools. Wraps at the ends.'
        });
        window.registerShortcut({
            id: 'audit-find-enter', scope: 'Find a Spool', keys: ['Enter'],
            description: 'On a spool: pick it, found here with no label read. In the box: search now.'
        });
        window.registerShortcut({
            id: 'audit-find-slash', scope: 'Find a Spool', keys: ['/'],
            description: 'Back to the box.'
        });
        window.registerShortcut({
            id: 'audit-find-escape', scope: 'Find a Spool', keys: ['Esc'],
            description: 'Close it: the audit stays as it was.'
        });
    }
})();
