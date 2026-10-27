/* MODULE: LOW STOCK (Group 49.2a) — the ⚠️ Low-stock list */
console.log("🚀 Loaded Module: LOW STOCK");

// window.openLowStockPanel()
//
// Opened by the title bar's ⚠️ button (#btn-low-stock-count, which shows how
// many filaments are low or out: Group 57.2, below) and the search panel's
// "⚠️ Low stock" button (offcanvas_search.html).
// One mountOverlay panel, per filament across its in-stock spools, from GET
// /api/stock_report (stock_report.py), in three lists: Low (under the
// `low_stock_g` setting, fewest grams first), Out (none in stock; the ones with
// no spool on record come last) and Excluded (left off both from this list,
// with why). It asks the server only when it opens or after a change made here,
// never on the dashboard heartbeat (Group 45.8's lesson), and a failed read
// shows an error that says Spoolman didn't answer, never "Nothing is low".
// The window keeps one size whatever it shows (Group 57.1, Derek 2026-10-25:
// "It jumps in size depending on its content's length"): a fixed height in
// rem, the list the only part that scrolls; the tabs, the filter, the line
// under the title and the key legend stay where they are on every list, a
// filter with no match, while it reads and after an error.
//
// Derek, 2026-10-20: a long list needed to be easier to read (tabs, a filter,
// one line per filament: a sample he tried, and liked, before it ships), a
// filament he can't get or won't buy again leaves Low and Out with the reason
// written down (🔕 on its row: POST /api/filament/<id>/stock_exclusion; ✏️ on
// the Excluded list changes why or includes it again: DELETE), and the list
// comes back where it was once the window opened from it is closed. 2026-10-21:
// "Excluded", not "Not buying again" ("just because it's discontinued, or I
// can't find it from the manufacturer, doesn't mean I didn't like it").
//
// Each row: swatch (getFilamentStyle), Brand - Material - Color with the
// filament's attribute tags, its stock, a 🛒 Buy link when one resolves (the
// server applies the filament window's rule; not on the Excluded list),
// and a click / Enter that opens the filament window. Keyboard (standing
// order): ↑ / ↓ move the .kb-active row (wrapping; from the filter, into the
// list), ← / → switch lists, / filters, Enter opens the row (from the filter
// too), Del asks why (or, on the Excluded list, opens its reason),
// Escape closes the reason dialog, else the list (mountOverlay owns Escape).
// Scanner safety: an Enter that is a scanner's is left to the scan
// accumulator, and a scan typed into the filter or the reason dialog's fields
// goes to the scan path with the field left as it was (installFieldScanCapture),
// never answering the dialog. Every piece of text is escaped: colour, vendor
// and note text is free text.

(function () {
    const OVERLAY_ID = 'fcc-low-stock-overlay';
    const DIALOG_ID = 'fcc-low-stock-reason';
    const STYLE_ID = 'fcc-low-stock-style';
    const TABS = [
        { key: 'low', label: 'Low' },
        { key: 'out', label: 'Out' },
        { key: 'excluded', label: 'Excluded' },
    ];
    // stock_report.EXCLUDE_REASONS, with a hint each.
    const REASONS = [
        { code: 'discontinued', label: 'Discontinued', hint: 'the maker stopped making it' },
        { code: 'cant_find', label: "Can't find it", hint: "the maker or your usual sellers don't have it" },
        { code: 'one_off', label: 'One-off', hint: 'bought once, on purpose' },
        { code: 'didnt_like', label: "Didn't like it", hint: '' },
        { code: 'other', label: 'Other', hint: 'say why in the note' },
    ];
    const NOTE_MAX = 500;      // stock_report.EXCLUDE_NOTE_MAX
    let _seq = 0;              // a newer load wins; an older answer never paints
    let _current = null;       // the open panel's handle
    let _count = null;         // the title-bar count: {low, out, threshold}, once one is known

    const esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    const toast = (msg, type, ms) => { if (typeof window.showToast === 'function') window.showToast(msg, type, ms); };

    // Own, overlay-scoped styles (never Bootstrap's colours): light text on the
    // dark panel, checked by the contrast guard (tests/test_contrast_guard.py).
    // Text sizes (Derek, 2026-10-21: readable on other screens and zoom levels):
    // the window is 1rem; nothing that is read is under .85 of it (13.6 px at
    // the browser's default), tags .8 (12.8 px), the rows' data .9. All em, so
    // browser zoom and a larger default font scale it.
    const P = `#${OVERLAY_ID}`;
    const D = `#${DIALOG_ID}`;
    const CSS = `
${P} .fcc-stock-panel { background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px;
    padding:14px 16px 10px; width:min(50rem, 94vw); height:min(40rem, 86vh); box-sizing:border-box;
    display:flex; flex-direction:column;
    box-shadow:0 10px 40px rgba(0,0,0,.6); font-size:1rem; outline:none; text-align:left; }
${P} .fcc-stock-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
${P} .fcc-stock-title { font-size:1.2em; font-weight:700; color:#fff; }
${P} .fcc-stock-close { background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:2px 10px; font-size:1em; line-height:1.4; cursor:pointer; }
${P} .fcc-stock-close:hover, ${P} .fcc-stock-close:focus-visible { border-color:#0dcaf0; outline:none; }
${P} .fcc-stock-sub { color:#ddd; font-size:.9em; margin:4px 0 6px; }
${P} .fcc-stock-tools { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:2px 0 8px; }
/* Not ready (reading, an error, nothing at all): the row keeps its room, so the
   list never moves when it arrives (57.1). A class, never the hidden attribute:
   Bootstrap's reboot makes [hidden] display:none !important (Group 57 review). */
${P} .fcc-stock-tools.fcc-stock-tools-wait { visibility:hidden; }
${P} .fcc-stock-tabs { display:flex; flex-wrap:wrap; gap:4px; }
${P} .fcc-stock-tab { background:#2a2a2a; color:#fff; border:1px solid #555; border-radius:6px; padding:3px 10px;
    font-size:.92em; line-height:1.5; cursor:pointer; }
${P} .fcc-stock-tab:hover { border-color:#999; }
${P} .fcc-stock-tab[aria-selected="true"] { background:#3d3000; border-color:#ffaa00; font-weight:600; }
${P} .fcc-stock-tab:focus-visible { outline:2px solid #0dcaf0; outline-offset:1px; }
${P} .fcc-stock-count { display:inline-block; min-width:1.6em; margin-left:5px; padding:0 6px; border-radius:9px;
    background:#444; color:#fff; font-size:.9em; text-align:center; font-weight:600; }
${P} .fcc-stock-filter { flex:1 1 180px; min-width:140px; background:#111; color:#fff; border:1px solid #666;
    border-radius:6px; padding:4px 8px; font-size:.92em; }
${P} .fcc-stock-filter::placeholder { color:#aaa; }
${P} .fcc-stock-filter:focus { border-color:#0dcaf0; outline:none; box-shadow:0 0 0 2px rgba(13,202,240,.35); }
${P} .fcc-stock-body { overflow:auto; flex:1 1 auto; min-height:0; padding-right:4px; }
${P} .fcc-stock-cap { color:#ddd; font-size:.9em; margin:0 0 6px; }
${P} .fcc-stock-row { box-sizing:border-box; display:flex; flex-wrap:wrap; align-items:center; column-gap:8px;
    row-gap:2px; padding:4px 8px; min-height:34px; border:1px solid #3a3a3a; border-radius:6px; margin-bottom:4px; cursor:pointer;
    background:#262626; color:#fff; outline:none; }
${P} .fcc-stock-row:hover { border-color:#777; }
${P} .fcc-stock-row.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.55); background:#16333a; }
${P} .fcc-stock-swatch { display:inline-block; width:18px; height:18px; border-radius:50%; flex:0 0 18px;
    border:1px solid #888; }
${P} .fcc-stock-name { flex:1 1 200px; min-width:0; font-weight:600; color:#fff; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; }
${P} .fcc-stock-tag { display:inline-block; background:#3a3a3a; border:1px solid #666; color:#f1f1f1;
    border-radius:10px; padding:0 7px; margin-left:4px; font-size:var(--fcc-fs-label); font-weight:500; vertical-align:middle; }
${P} .fcc-stock-meta { flex:0 0 auto; color:#ddd; font-size:.9em; white-space:nowrap; }
${P} .fcc-stock-why { flex:0 0 auto; background:#3a2323; border:1px solid #ff8a8a; color:#fff; border-radius:10px;
    padding:0 8px; font-size:.85em; white-space:nowrap; }
${P} .fcc-stock-note { flex:1 0 100%; color:#ddd; font-size:.88em; padding-left:26px; white-space:normal;
    overflow-wrap:anywhere; }
${P} .fcc-stock-buy { flex:0 0 auto; color:#ffc107; border:1px solid #ffc107; border-radius:6px; padding:0 8px;
    font-size:.88em; line-height:1.6; text-decoration:none; white-space:nowrap; background:transparent; }
${P} .fcc-stock-buy:hover, ${P} .fcc-stock-buy:focus-visible { background:#ffc107; color:#111; outline:none; }
${P} .fcc-stock-act { flex:0 0 auto; background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:0 7px; font-size:.92em; line-height:1.6; cursor:pointer; }
${P} .fcc-stock-act:hover, ${P} .fcc-stock-act:focus-visible { border-color:#ff8a8a; background:#3a2323; outline:none; }
${P} .fcc-stock-none { color:#ddd; font-style:italic; padding:0 4px 6px; }
${P} .fcc-stock-state { color:#fff; text-align:center; padding:22px 8px; }
${P} .fcc-stock-state-sub { color:#ddd; font-size:.9em; margin-top:4px; }
${P} .fcc-stock-error-title { color:#ff8a8a; font-weight:700; font-size:1.05em; margin-bottom:6px; }
${P} .fcc-stock-retry { margin-top:12px; background:transparent; color:#fff; border:1px solid #0dcaf0;
    border-radius:6px; padding:4px 12px; cursor:pointer; }
${P} .fcc-stock-retry:hover, ${P} .fcc-stock-retry:focus-visible { background:#0dcaf0; color:#111; outline:none; }
${P} .fcc-stock-foot { color:#ccc; font-size:.85em; margin-top:8px; border-top:1px solid #333; padding-top:6px;
    flex:0 0 auto; }
${P} .fcc-stock-head, ${P} .fcc-stock-sub, ${P} .fcc-stock-tools { flex:0 0 auto; }
@media (max-width: 520px) {
    ${P} .fcc-stock-name { flex-basis:calc(100% - 30px); white-space:normal; }
}
/* A very short window (a phone on its side): the list keeps room for its rows;
   the line under the title and the key legend go (Group 57 review). */
@media (max-height: 480px) {
    ${P} .fcc-stock-sub, ${P} .fcc-stock-foot { display:none; }
}
${D} .fcc-stock-dlg { background:#1e1e1e; color:#fff; border:2px solid #ff8a8a; border-radius:8px; padding:14px 16px;
    width:min(28.75rem, 92vw); max-height:90vh; overflow:auto; box-shadow:0 10px 40px rgba(0,0,0,.6);
    font-size:1rem; text-align:left; outline:none; }
${D} .fcc-stock-dlg-title { font-weight:700; font-size:1.1em; color:#fff; }
${D} .fcc-stock-dlg-name { color:#fff; font-weight:600; margin:2px 0 10px; overflow-wrap:anywhere; }
${D} .fcc-stock-dlg-was { color:#ddd; font-size:.9em; margin:-6px 0 10px; }
${D} fieldset { border:0; padding:0; margin:0 0 8px; min-width:0; }
${D} legend { float:none; width:auto; padding:0; margin:0 0 4px; font-size:.95em; color:#fff; }
${D} .fcc-stock-reason { display:flex; align-items:baseline; gap:8px; padding:4px 6px; border-radius:6px;
    cursor:pointer; color:#fff; margin:0; }
${D} .fcc-stock-reason:hover { background:#2a2a2a; }
${D} .fcc-stock-reason input { accent-color:#ff8a8a; margin:0; }
${D} .fcc-stock-reason-hint { color:#ddd; font-size:.88em; }
${D} .fcc-stock-note-label { display:block; color:#fff; font-size:1em; margin:4px 0 3px; }
${D} .fcc-stock-note-input { width:100%; background:#111; color:#fff; border:1px solid #666; border-radius:6px;
    padding:6px 8px; font-size:.95em; resize:vertical; }
${D} .fcc-stock-note-input::placeholder { color:#aaa; }
${D} .fcc-stock-note-input:focus { border-color:#0dcaf0; outline:none; }
${D} .fcc-stock-dlg-msg { color:#ff8a8a; min-height:1.2em; font-size:.9em; margin:6px 0 2px; }
${D} .fcc-stock-dlg-help { color:#ddd; font-size:.88em; margin-bottom:10px; }
${D} .fcc-stock-dlg-buttons { display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }
${D} .fcc-stock-dlg-btn { border:1px solid #777; background:transparent; color:#fff; border-radius:6px; padding:5px 12px;
    font-size:.92em; cursor:pointer; }
${D} .fcc-stock-dlg-btn:hover { border-color:#bbb; }
${D} .fcc-stock-dlg-btn:focus-visible { outline:2px solid #0dcaf0; outline-offset:2px; }
${D} .fcc-stock-dlg-save { background:#ff8a8a; border-color:#ff8a8a; color:#111; font-weight:700; }
${D} .fcc-stock-dlg-include { border-color:#0dcaf0; }
${D} .fcc-stock-dlg-btn[disabled] { cursor:default; }
`;

    function _ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const st = document.createElement('style');
        st.id = STYLE_ID;
        st.textContent = CSS;
        document.head.appendChild(st);
    }

    const _plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

    // A finite number, else null (Number(null) and Number('') are 0, not unknown).
    const _finite = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v));

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

    // --- the data ------------------------------------------------------------------

    function _lists(handle) {
        const d = (handle && handle._data) || {};
        return {
            low: Array.isArray(d.low) ? d.low : [],
            out: Array.isArray(d.out) ? d.out : [],
            excluded: Array.isArray(d.excluded) ? d.excluded : [],
        };
    }

    function _findRow(handle, fid) {
        const all = _lists(handle);
        const key = String(fid);
        for (const t of TABS) {
            const row = all[t.key].find((r) => String(r.filament_id) === key);
            if (row) return row;
        }
        return null;
    }

    const _tokens = (text) => String(text || '').toLowerCase().split(/\s+/).filter(Boolean);

    // A row matches when every word typed is somewhere in its name, tags,
    // reason or note.
    function _matches(row, tokens) {
        if (!tokens.length) return true;
        const nr = row.excluded || {};
        const hay = [row.display, ...(Array.isArray(row.attributes) ? row.attributes : []), nr.reason, nr.note]
            .filter((v) => v != null).join(' ').toLowerCase();
        return tokens.every((t) => hay.includes(t));
    }

    function _stockText(row) {
        const grams = Math.round(Number(row.grams) || 0);
        const inStock = Number(row.spools) || 0;
        const total = Number(row.spools_total) || 0;
        // A filament with no spool on record at all (Derek, 2026-10-20: "they are
        // technically out") says so; the server lists it after the used-up ones.
        if (row.no_spools) return '0 g · no spool on record';
        if (!inStock) return `0 g · ${_plural(total, 'spool', 'spools')} archived or empty`;
        const floor = row.stock_unknown ? '≥ ' : '';
        return `${floor}${grams} g · ${_plural(inStock, 'spool', 'spools')}`;
    }

    // --- rows -----------------------------------------------------------------------

    function _rowHtml(row, kind) {
        const name = String(row.display == null ? '' : row.display);
        const tags = (Array.isArray(row.attributes) ? row.attributes : [])
            .map((a) => `<span class="fcc-stock-tag">${esc(a)}</span>`).join('');
        let middle = '';
        let tail = '';
        let note = '';
        let title = name;
        if (kind === 'excluded') {
            const nr = row.excluded || {};
            const reason = String(nr.reason || 'Excluded');
            middle = `<span class="fcc-stock-why" data-stock-why>${esc(reason)}</span>`;
            const since = nr.at ? `since ${nr.at}` : '';
            const said = nr.note ? `“${nr.note}”` : '';
            const line = [since, said].filter(Boolean).join(' · ');
            if (line) note = `<div class="fcc-stock-note" data-stock-note>${esc(line)}</div>`;
            title = [name, reason, nr.note].filter(Boolean).join(' — ');
            tail = `<button type="button" class="fcc-stock-act" data-stock-edit
                        aria-label="${esc(`Change why, or include ${name} again`)}"
                        title="Change why, or include it again (Del)">✏️</button>`;
        } else {
            const link = _webLink(row.buy_url);
            if (link) {
                tail += `<a class="fcc-stock-buy" href="${esc(link)}" target="_blank" rel="noopener noreferrer"
                            title="${esc(`Buy more ${name}`)}">🛒 Buy</a>`;
            }
            tail += `<button type="button" class="fcc-stock-act" data-stock-exclude
                        aria-label="${esc(`Exclude ${name} from Low and Out…`)}"
                        title="Exclude it from Low and Out… (Del)">🔕</button>`;
        }
        return `<div class="fcc-stock-row" role="button" tabindex="-1" data-fid="${esc(row.filament_id)}"
                    data-kind="${kind}" title="${esc(title)}">
                ${_swatch(row)}
                <span class="fcc-stock-name">${esc(name)}${tags}</span>
                ${middle}
                <span class="fcc-stock-meta">${esc(_stockText(row))}</span>
                ${tail}
                ${note}
            </div>`;
    }

    // The line under the title. The same words before the list is read (the
    // threshold the dashboard's count last said, else "…"), so it never
    // changes length, nor moves the tabs below it, once the list arrives (57.1).
    function _subText(threshold) {
        const g = _finite(threshold) !== null ? `${Math.round(_finite(threshold))} g` : '… g';
        return `Per filament, across its in-stock spools: low is under ${g} (⚙️ Settings → Behavior).`;
    }

    function _shellHtml() {
        const tabs = TABS.map((t, i) => `<button type="button" class="fcc-stock-tab" role="tab"
                id="fcc-stock-tab-${t.key}" data-stock-tab="${t.key}" aria-controls="fcc-stock-list"
                aria-selected="${i === 0 ? 'true' : 'false'}" tabindex="${i === 0 ? 0 : -1}">${esc(t.label)}<span
                class="fcc-stock-count" data-stock-count="${t.key}">0</span></button>`).join('');
        return `<div class="fcc-stock-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-stock-title" tabindex="-1">
            <div class="fcc-stock-head">
                <div class="fcc-stock-title" id="fcc-stock-title">⚠️ Low stock</div>
                <button type="button" class="fcc-stock-close" data-stock-close aria-label="Close">✕</button>
            </div>
            <div class="fcc-stock-sub" data-stock-sub>${esc(_subText(_count ? _count.threshold : null))}</div>
            <div class="fcc-stock-tools fcc-stock-tools-wait" data-stock-tools aria-hidden="true">
                <div class="fcc-stock-tabs" role="tablist" aria-label="Lists">${tabs}</div>
                <input type="search" class="fcc-stock-filter" data-stock-filter
                       placeholder="Filter: brand, material, colour, reason… ( / )" aria-label="Filter the lists"
                       autocomplete="off" spellcheck="false">
            </div>
            <div class="fcc-stock-body" id="fcc-stock-list" role="tabpanel" data-stock-body data-stock-state="loading">
                <div class="fcc-stock-state">Reading your spools from Spoolman…</div>
            </div>
            <div class="fcc-stock-foot" data-stock-foot>↑ ↓ move · Enter opens the filament · Esc closes</div>
        </div>`;
    }

    function _body(handle) {
        return handle && handle.panel ? handle.panel.querySelector('[data-stock-body]') : null;
    }

    function _filterEl(handle) {
        return handle && handle.panel ? handle.panel.querySelector('[data-stock-filter]') : null;
    }

    function _setBody(handle, html, stateName) {
        const body = _body(handle);
        if (!body) return null;
        body.innerHTML = html;
        body.dataset.stockState = stateName;
        const tools = handle.panel.querySelector('[data-stock-tools]');
        if (tools) {
            const wait = stateName !== 'ready';
            tools.classList.toggle('fcc-stock-tools-wait', wait);
            if (wait) tools.setAttribute('aria-hidden', 'true');
            else tools.removeAttribute('aria-hidden');
        }
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

    function _rows(handle) {
        const body = _body(handle);
        return body ? Array.from(body.querySelectorAll('.fcc-stock-row')) : [];
    }

    function _activeRow(handle) {
        const body = _body(handle);
        return body ? body.querySelector('.fcc-stock-row.kb-active') : null;
    }

    function _highlight(handle, idx, focus) {
        const rows = _rows(handle);
        rows.forEach((r) => { r.classList.remove('kb-active'); r.setAttribute('aria-selected', 'false'); });
        const row = rows[idx];
        if (!row) return;
        row.classList.add('kb-active');
        row.setAttribute('aria-selected', 'true');
        if (focus !== false) { try { row.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        try { row.scrollIntoView({ block: 'nearest' }); } catch (_) { /* noop */ }
    }

    function _move(handle, delta) {
        const rows = _rows(handle);
        if (!rows.length) return;
        const cur = rows.findIndex((r) => r.classList.contains('kb-active'));
        const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1) : (cur + delta + rows.length) % rows.length;
        _highlight(handle, next);
    }

    // --- the tabs and the filter -------------------------------------------------------

    function _caption(handle, tab) {
        if (tab === 'low') return `Under ${Math.round(handle._threshold)} g in stock, fewest grams first.`;
        if (tab === 'out') return 'None left in stock. The ones with no spool on record come last.';
        return "Left off Low and Out: ones you can't get or won't restock. ✏️ changes why, or includes one again.";
    }

    function _noneText(tab) {
        if (tab === 'low') return 'Nothing is low.';
        if (tab === 'out') return 'Nothing is out.';
        return "None yet. 🔕 on a Low or Out row (or Del) leaves a filament you can't get or won't restock off "
            + 'those lists, with your reason.';
    }

    function _footText(tab) {
        const del = tab === 'excluded' ? 'Del change why or include again' : 'Del exclude…';
        return `↑ ↓ move · ← → lists · / filter · Enter opens the filament · ${del} · Esc closes`;
    }

    // Draws the current tab's rows (filtered) and the tab counts. `keep`: the
    // row to highlight ({fid}, else {index}) and the scroll to restore;
    // `focusRow: false` leaves the focus where it is (typing in the filter).
    function _paint(handle, keep, focusRow) {
        const all = _lists(handle);
        const tokens = _tokens(handle._filter);
        const shown = {};
        TABS.forEach((t) => { shown[t.key] = all[t.key].filter((r) => _matches(r, tokens)); });
        const tab = handle._tab;
        TABS.forEach((t) => {
            const btn = handle.panel.querySelector(`[data-stock-tab="${t.key}"]`);
            if (!btn) return;
            const on = t.key === tab;
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
            btn.tabIndex = on ? 0 : -1;
            const count = btn.querySelector('[data-stock-count]');
            if (count) {
                count.textContent = tokens.length ? `${shown[t.key].length}/${all[t.key].length}`
                    : String(all[t.key].length);
            }
        });
        const rows = shown[tab];
        const label = (TABS.find((t) => t.key === tab) || TABS[0]).label;
        let html = `<div class="fcc-stock-cap" data-stock-cap>${esc(_caption(handle, tab))}</div>`;
        if (!all[tab].length) html += `<div class="fcc-stock-none">${esc(_noneText(tab))}</div>`;
        else if (!rows.length) {
            html += `<div class="fcc-stock-none">${esc(`Nothing in ${label} matches “${handle._filter.trim()}”.`)}</div>`;
        } else html += rows.map((r) => _rowHtml(r, tab)).join('');
        const body = _setBody(handle, html, 'ready');
        const foot = handle.panel.querySelector('[data-stock-foot]');
        if (foot) foot.textContent = _footText(tab);
        let at = keep && keep.fid != null ? rows.findIndex((r) => String(r.filament_id) === String(keep.fid)) : -1;
        // Its row is gone: the old scroll would hide the row taking its place
        // (review browser-6), so that one is scrolled into view instead.
        const gone = !!(keep && keep.fid != null && at < 0);
        if (at < 0 && keep && Number.isFinite(Number(keep.index))) at = Math.min(Number(keep.index), rows.length - 1);
        if (at < 0) at = 0;
        if (rows.length) _highlight(handle, at, focusRow);
        else if (focusRow !== false) { try { handle.panel.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        if (body && keep && !gone && Number.isFinite(Number(keep.scrollTop))) body.scrollTop = Number(keep.scrollTop);
    }

    function _setTab(handle, key) {
        if (!TABS.some((t) => t.key === key)) return;
        handle._tab = key;
        _paint(handle, { index: 0 });
    }

    function _stepTab(handle, delta) {
        const i = TABS.findIndex((t) => t.key === handle._tab);
        _setTab(handle, TABS[(i + delta + TABS.length) % TABS.length].key);
    }

    function _render(handle, restore, quiet) {
        const all = _lists(handle);
        const threshold = handle._threshold;
        const sub = handle.panel.querySelector('[data-stock-sub]');
        if (sub) sub.textContent = _subText(threshold);
        // A re-read never takes the focus from an open reason dialog, and a
        // quiet one (after a change made here) not from wherever the user went
        // meanwhile either (2026-10-21 review, browser-4: it moved the focus out
        // of a note being typed onto a row behind the dialog).
        const active = document.activeElement;
        const away = !!handle._dialog || (!!quiet && !!active && active !== document.body
            && !handle.panel.contains(active));
        if (!all.low.length && !all.out.length && !all.excluded.length) {
            _setBody(handle, `<div class="fcc-stock-state">
                    <div>✅ Nothing is low.</div>
                    <div class="fcc-stock-state-sub">No filament is under ${esc(Math.round(threshold))} g,
                        and none has run out.</div>
                </div>`, 'empty');
            if (!away) { try { handle.panel.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
            return;
        }
        // The list it opens on: the one it was on (coming back, or after a
        // change made here), else the first with something in it.
        const wanted = restore && TABS.some((t) => t.key === restore.tab) ? restore.tab : null;
        handle._tab = wanted || (all.low.length ? 'low' : all.out.length ? 'out' : 'excluded');
        handle._filter = restore && typeof restore.filter === 'string' ? restore.filter : (handle._filter || '');
        const filter = _filterEl(handle);
        if (filter) filter.value = handle._filter;
        const typing = filter && document.activeElement === filter;
        _paint(handle, restore || { index: 0 }, !typing && !away);
    }

    async function _load(handle, restore, quiet) {
        const token = ++_seq;
        const sentAt = Date.now();
        // Try again after a failed read restores the same place (review browser-5).
        if (restore) handle._lastRestore = restore;
        if (!quiet) _setBody(handle, '<div class="fcc-stock-state">Reading your spools from Spoolman…</div>', 'loading');
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
            handle._data = null;
            _setBody(handle, _errorHtml(data), 'error');
            const retry = handle.panel.querySelector('[data-stock-retry]');
            if (retry) { try { retry.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
            return;
        }
        handle._data = data;
        handle._threshold = Number.isFinite(Number(data.threshold_g)) ? Number(data.threshold_g) : 250;
        // The list it just read is the newest count there is (after a change
        // made here too): the title bar says the same as the tabs, and a
        // heartbeat sent before this read began no longer paints over it.
        _listReadAt = Math.max(_listReadAt, sentAt);
        _setCount(data.low.length, data.out.length, handle._threshold);
        // A quiet re-read keeps the list, filter and row the user moved to while
        // it was on its way, not the ones it set out with (review browser-5).
        if (quiet && restore && (handle._tab !== restore.tab || (handle._filter || '') !== (restore.filter || ''))) {
            restore = _snapshot(handle);
        }
        _render(handle, restore, quiet);
    }

    // Where the list is: the tab, the filter, the highlighted row and the scroll.
    function _snapshot(handle, fid) {
        const active = _activeRow(handle);
        const body = _body(handle);
        return {
            fid: fid != null ? String(fid) : (active ? active.dataset.fid : null),
            // Where that row sat: if it is gone when the list is drawn again (it
            // was excluded, or stocked up), the next one takes its place.
            index: active ? Math.max(0, _rows(handle).indexOf(active)) : 0,
            tab: handle._tab || null,
            filter: handle._filter || '',
            scrollTop: body ? body.scrollTop : 0,
        };
    }

    // --- excluded: the reason dialog ----------------------------------------------------

    function _dialogHtml(row) {
        const name = String(row.display == null ? '' : row.display);
        const cur = row.excluded || null;
        const curCode = cur ? (REASONS.some((r) => r.code === cur.code) ? cur.code : 'other') : '';
        const radios = REASONS.map((r) => `<label class="fcc-stock-reason">
                <input type="radio" name="fcc-stock-reason" value="${r.code}" data-stock-reason-field
                    ${r.code === curCode ? 'checked' : ''}>
                <span>${esc(r.label)}${r.hint ? ` <span class="fcc-stock-reason-hint">— ${esc(r.hint)}</span>` : ''}</span>
            </label>`).join('');
        const was = cur ? `<div class="fcc-stock-dlg-was">${esc(cur.at ? `Excluded on ${cur.at}` : 'Excluded')}: ${esc(cur.reason)}.</div>` : '';
        // A reason typed in Spoolman by hand that matches none reads as Other
        // (stock_report._reason_code): its words go into the note, so a Save
        // keeps them.
        const handTyped = !!(cur && cur.code === 'other' && String(cur.reason || '').trim().toLowerCase() !== 'other');
        const note = !cur ? '' : (handTyped ? [cur.reason, cur.note].filter(Boolean).join(' — ') : (cur.note || ''));
        const buttons = cur
            ? `<button type="button" class="fcc-stock-dlg-btn fcc-stock-dlg-save" data-stock-dlg-save>Save</button>
               <button type="button" class="fcc-stock-dlg-btn fcc-stock-dlg-include" data-stock-dlg-include>↩️ Include again</button>`
            : `<button type="button" class="fcc-stock-dlg-btn fcc-stock-dlg-save" data-stock-dlg-save>🔕 Exclude</button>`;
        const help = cur
            ? 'Include again puts it back on Low and Out when it is low or out, and clears the reason.'
            : 'It leaves Low and Out, and their warnings, and goes on the Excluded list with your reason. '
              + 'Include again there undoes it.';
        return `<div class="fcc-stock-dlg" role="dialog" aria-modal="true" aria-labelledby="fcc-stock-dlg-title"
                    data-stock-dialog data-fid="${esc(row.filament_id)}" tabindex="-1">
                <div class="fcc-stock-dlg-title" id="fcc-stock-dlg-title">🔕 Exclude from Low and Out</div>
                <div class="fcc-stock-dlg-name">${esc(name)}</div>
                ${was}
                <fieldset><legend>Why?</legend>${radios}</fieldset>
                <label class="fcc-stock-note-label" for="fcc-stock-note">Note <span class="fcc-stock-reason-hint">(needed for Other)</span></label>
                <textarea id="fcc-stock-note" class="fcc-stock-note-input" data-stock-note-input data-stock-reason-field
                    rows="3" maxlength="${NOTE_MAX}" placeholder="e.g. Discontinued in 2025; the PETG one is close">${esc(note)}</textarea>
                <div class="fcc-stock-dlg-msg" role="alert" data-stock-dlg-msg></div>
                <div class="fcc-stock-dlg-help">${esc(help)}</div>
                <div class="fcc-stock-dlg-buttons">
                    ${buttons}
                    <button type="button" class="fcc-stock-dlg-btn" data-stock-dlg-cancel>Cancel</button>
                </div>
            </div>`;
    }

    function _dropDialog(handle) {
        const d = handle && handle._dialog;
        if (!d) return null;
        document.removeEventListener('keydown', d.keys, true);
        handle._dialog = null;
        return d;
    }

    function _closeDialog(handle) {
        const d = _dropDialog(handle);
        if (!d) return;
        try { d.overlay.cleanup(); } catch (_) { /* noop */ }
        // Back to the row it was opened from, if the list is still up.
        if (handle.element && handle.element.isConnected) {
            const rows = _rows(handle);
            const at = rows.findIndex((r) => r.classList.contains('kb-active'));
            if (at >= 0) _highlight(handle, at);
        }
    }

    function _dialogMsg(d, text, focusEl) {
        const msg = d.overlay.panel.querySelector('[data-stock-dlg-msg]');
        if (msg) msg.textContent = text || '';
        if (focusEl) { try { focusEl.focus(); } catch (_) { /* noop */ } }
    }

    function _busy(d, on) {
        d.busy = on;
        d.overlay.panel.querySelectorAll('button, input, textarea').forEach((el) => { el.disabled = on; });
    }

    async function _send(method, fid, body) {
        try {
            const res = await fetch(`/api/filament/${encodeURIComponent(fid)}/stock_exclusion`, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: body ? JSON.stringify(body) : undefined,
            });
            let data = null;
            try { data = await res.json(); } catch (_) { data = null; }
            if (res.ok && data && data.success === true) return { ok: true, data };
            return { ok: false, msg: (data && data.msg) || `FCC answered HTTP ${res.status}: nothing was changed.` };
        } catch (_) {
            return { ok: false, msg: "FCC didn't answer, so nothing was changed. Try again in a moment." };
        }
    }

    // After a change made here: read the list again, keeping the tab, the
    // filter and the place (the next row takes the changed one's place).
    function _reloadAfterChange(handle, fid) {
        if (!handle.element || !handle.element.isConnected) return;
        const rows = _rows(handle);
        const at = rows.findIndex((r) => r.dataset.fid === String(fid));
        const snap = _snapshot(handle);
        _load(handle, { tab: snap.tab, filter: snap.filter, index: at >= 0 ? at : 0, scrollTop: snap.scrollTop }, true);
    }

    // The page's own date for a new mark (the server's clock may be UTC).
    function _localDay() {
        const d = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    async function _saveDialog(handle) {
        const d = handle._dialog;
        if (!d || d.busy) return;
        const panel = d.overlay.panel;
        const picked = panel.querySelector('input[name="fcc-stock-reason"]:checked');
        const noteEl = panel.querySelector('[data-stock-note-input]');
        const note = (noteEl && noteEl.value ? noteEl.value : '').trim();
        if (!picked) {
            _dialogMsg(d, 'Pick why first.', panel.querySelector('input[name="fcc-stock-reason"]'));
            return;
        }
        if (picked.value === 'other' && !note) {
            _dialogMsg(d, 'Say why in the note: Other needs one.', noteEl);
            return;
        }
        _busy(d, true);
        _dialogMsg(d, 'Saving…');
        const res = await _send('POST', d.fid, { reason: picked.value, note, today: _localDay() });
        // The dialog may have closed meanwhile (its search panel closed): the
        // answer is still told, and the list read again if it is still up.
        const still = handle._dialog === d;
        if (!res.ok) {
            if (still) { _busy(d, false); _dialogMsg(d, res.msg, picked); }
            toast(res.msg, 'error', 7000);
            return;
        }
        if (still) _closeDialog(handle);
        const nr = res.data.excluded || {};
        toast(`🔕 ${res.data.display || d.name} is excluded from Low and Out (${nr.reason || picked.value}).`,
            'success', 4000);
        if (res.data.warning) toast(res.data.warning, 'warning', 7000);   // an old note Spoolman kept
        _reloadAfterChange(handle, d.fid);
    }

    async function _includeAgain(handle) {
        const d = handle._dialog;
        if (!d || d.busy) return;
        _busy(d, true);
        _dialogMsg(d, 'Saving…');
        const res = await _send('DELETE', d.fid, null);
        const still = handle._dialog === d;
        if (!res.ok) {
            if (still) { _busy(d, false); _dialogMsg(d, res.msg, d.overlay.panel.querySelector('[data-stock-dlg-include]')); }
            toast(res.msg, 'error', 7000);
            return;
        }
        if (still) _closeDialog(handle);
        toast(`↩️ ${res.data.display || d.name} is included again: it shows on Low or Out when it is low or out.`,
            'success', 4000);
        _reloadAfterChange(handle, d.fid);
    }

    function _dialogKey(handle, e) {
        const d = handle._dialog;
        if (!d) return;
        if (!d.overlay.element || !d.overlay.element.isConnected) { _dropDialog(handle); return; }
        if (e.key !== 'Enter' || e.altKey || e.metaKey) return;
        const t = e.target;
        // Enter in the note is a new line; Ctrl+Enter saves from anywhere.
        if (t && t.tagName === 'TEXTAREA' && !e.ctrlKey) return;
        // A scanner's Enter belongs to the scan accumulator (one typed into the
        // note or onto a reason was taken by the field scan capture already). It
        // still reaches the accumulator; only the focused button's own press is
        // cancelled (the accumulator cancels it too, this doesn't lean on that).
        if (!e.ctrlKey && typeof window.enterIsAScan === 'function' && window.enterIsAScan()) {
            e.preventDefault();
            return;
        }
        e.preventDefault();
        e.stopImmediatePropagation();
        if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
        if (d.busy) return;
        if (!e.ctrlKey && t && t.tagName === 'BUTTON' && d.overlay.panel.contains(t)) { t.click(); return; }
        _saveDialog(handle);
    }

    function _openDialog(handle, fid) {
        const row = _findRow(handle, fid);
        if (!row || typeof window.mountOverlay !== 'function') return;
        _closeDialog(handle);
        const openedAt = Date.now();
        // The reason it has (editing), else the first. (A selector list would
        // answer the first radio in the page's order, not the checked one.)
        const cur = row.excluded && REASONS.some((r) => r.code === row.excluded.code)
            ? row.excluded.code : (row.excluded ? 'other' : '');
        const overlay = window.mountOverlay({
            id: DIALOG_ID,
            tier: 'confirm',
            content: _dialogHtml(row),
            host: handle._host || undefined,     // closes with the search panel, as the list does
            initialFocus: cur ? `input[name="fcc-stock-reason"][value="${cur}"]` : 'input[name="fcc-stock-reason"]',
            // Not the second click of a double click on 🔕, which lands on this
            // dialog's backdrop (review browser-8).
            onBackdropClick: () => {
                if (Date.now() - openedAt < 400) return;
                if (!handle._dialog || !handle._dialog.busy) _closeDialog(handle);
            },
            onEscape: () => { if (!handle._dialog || !handle._dialog.busy) _closeDialog(handle); },
        });
        const d = { overlay, fid: String(row.filament_id), name: String(row.display || ''), busy: false };
        d.keys = (e) => _dialogKey(handle, e);
        handle._dialog = d;
        document.addEventListener('keydown', d.keys, true);
        // Now, not on mountOverlay's next tick: a key pressed straight after Del
        // must reach the reasons, not the row behind the dialog.
        const first = overlay.panel.querySelector(cur ? `input[name="fcc-stock-reason"][value="${cur}"]`
            : 'input[name="fcc-stock-reason"]');
        if (first) { try { first.focus(); } catch (_) { /* noop */ } }
        overlay.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-stock-dlg-cancel]')) { if (!d.busy) _closeDialog(handle); return; }
            if (e.target.closest('[data-stock-dlg-include]')) { _includeAgain(handle); return; }
            if (e.target.closest('[data-stock-dlg-save]')) _saveDialog(handle);
        });
        overlay.panel.addEventListener('change', () => _dialogMsg(d, ''));
    }

    // --- open, close, keys ---------------------------------------------------------------

    function _unlisten(handle) {
        if (handle && handle._stockKeys) {
            document.removeEventListener('keydown', handle._stockKeys, true);
            handle._stockKeys = null;
        }
        if (handle && handle._stockShows) {
            document.removeEventListener('show.bs.modal', handle._stockShows.modal);
            document.removeEventListener('show.bs.offcanvas', handle._stockShows.offcanvas);
            handle._stockShows = null;
        }
        if (_current === handle) _current = null;
    }

    // `opts.keepFocus`: another window takes the focus next (a filament window,
    // one opened over the list), so it isn't handed back.
    function _close(handle, opts) {
        _closeDialog(handle);
        _unlisten(handle);
        try { handle.cleanup(); } catch (_) { /* noop */ }
        // Back to the button that opened it (the title bar's ⚠️, opened with Space:
        // Enter is the scan accumulator's), not the top of the page (Group 57
        // review), when nothing else has taken the focus meanwhile.
        const opener = handle._opener;
        handle._opener = null;
        const a = document.activeElement;
        if (!(opts && opts.keepFocus) && opener && opener.isConnected && (!a || a === document.body)) {
            try { opener.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        }
    }

    // --- the list comes back (Derek, 2026-10-20) ---
    // Armed once the filament window opened from the list really shows (a read
    // that fails opens none, and must not leave an arm for some later, unrelated
    // window: 2026-10-20 review, browser-4). Then, once the window it opened (or
    // one opened from that: a spool, an edit, the wizard and its return to the
    // filament) closes and nothing else is up or on its way (no window, panel or
    // overlay, no read in progress, no window shown since that close: browser-2),
    // the list reopens on the same list, filter, row and scroll, reading Spoolman
    // again (an edit shows). Disarmed once it has come back, when the list is
    // opened another way, or after RETURN_TTL_MS (a window closing much later is
    // something else). A list that came back has no host, so a window opened
    // over it closes it and arms the come-back again (browser-3: it used to sit
    // over that window).
    const RETURN_TTL_MS = 10 * 60 * 1000;
    const OPEN_WAIT_MS = 15000;     // a filament read's ceiling (fetchT)
    const SETTLE_MS = 400;          // past Bootstrap's own hide and a window opened in its place
    let _return = null;    // {restore, at, lastShowAt, onHidden, onShow}
    let _pending = null;   // {onShow, timer}: armed once the filament window shows

    function _disarmReturn() {
        if (_return) {
            document.removeEventListener('hidden.bs.modal', _return.onHidden);
            document.removeEventListener('show.bs.modal', _return.onShow);
        }
        _return = null;
        if (_pending) {
            document.removeEventListener('show.bs.modal', _pending.onShow);
            clearTimeout(_pending.timer);
        }
        _pending = null;
    }

    function _nothingElseUp() {
        // A window still reading what it will show (openFilamentDetails,
        // openSpoolDetails and openManage hold the processing dim meanwhile).
        if (typeof state !== 'undefined' && state && state.processing) return false;
        return !document.querySelector('.modal.show, .modal-backdrop, .offcanvas.show, .offcanvas.showing, '
            + '[data-overlay-mount="1"]');
    }

    function _armReturn(restore) {
        _disarmReturn();
        const ret = { restore: restore || {}, at: Date.now(), lastShowAt: 0 };
        ret.onShow = () => { ret.lastShowAt = Date.now(); };
        ret.onHidden = () => {
            if (_return !== ret) return;
            if (Date.now() - ret.at > RETURN_TTL_MS) { _disarmReturn(); return; }
            const hiddenAt = Date.now();
            setTimeout(() => {
                if (_return !== ret || _current) return;
                // A window shown since that close, or one still opening: stay armed.
                if (ret.lastShowAt >= hiddenAt || !_nothingElseUp()) return;
                _disarmReturn();
                window.openLowStockPanel({ restore: ret.restore });
            }, SETTLE_MS);
        };
        document.addEventListener('hidden.bs.modal', ret.onHidden);
        document.addEventListener('show.bs.modal', ret.onShow);
        _return = ret;
    }

    // Arms the come-back once #filamentModal shows (now, if it is up already).
    function _armWhenShown(restore) {
        _disarmReturn();
        const modal = document.getElementById('filamentModal');
        if (modal && modal.classList.contains('show')) { _armReturn(restore); return; }
        const pend = {};
        pend.onShow = (e) => {
            if (_pending !== pend || !e || !e.target || e.target.id !== 'filamentModal') return;
            _armReturn(restore);
        };
        pend.timer = setTimeout(() => { if (_pending === pend) _disarmReturn(); }, OPEN_WAIT_MS);
        document.addEventListener('show.bs.modal', pend.onShow);
        _pending = pend;
    }

    function _openFilament(handle, fid) {
        const id = parseInt(fid, 10);
        if (!Number.isFinite(id)) return;
        _armWhenShown(_snapshot(handle, id));
        _close(handle, { keepFocus: true });
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
        if (handle._dialog) return;              // the reason dialog owns the keys while it is up
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const filter = _filterEl(handle);
        const inFilter = !!filter && e.target === filter;
        const ready = !!(_body(handle) && _body(handle).dataset.stockState === 'ready');
        // Tab onto a row's 🛒 / 🔕 / ✏️ moves the focus, not the highlight: Del
        // and the arrows act on the row the focus is in (review browser-7: Del
        // opened the highlighted row's dialog while Enter pressed the focused
        // button of another).
        if (!inFilter && ['ArrowDown', 'ArrowUp', 'Delete'].includes(e.key)) {
            const a = document.activeElement;
            const inRow = a && a !== handle.panel && handle.panel.contains(a) && a.closest ? a.closest('.fcc-stock-row') : null;
            if (inRow && !inRow.classList.contains('kb-active')) _highlight(handle, _rows(handle).indexOf(inRow), false);
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!_rows(handle).length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            _move(handle, e.key === 'ArrowDown' ? 1 : -1);     // from the filter: into the list
            return;
        }
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            if (inFilter || !ready) return;                    // the caret's keys in the filter
            e.preventDefault();
            e.stopImmediatePropagation();
            _stepTab(handle, e.key === 'ArrowRight' ? 1 : -1);
            return;
        }
        if (e.key === '/') {
            // Not mid-scan: a Prusament QR's URL carries '/' (fab_drag.js's rule).
            if (inFilter) return;
            if (typeof window.isScanInFlight === 'function' && window.isScanInFlight()) return;
            e.preventDefault();
            e.stopImmediatePropagation();       // nor the global search's '/', nor the scan buffer
            if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
            // Still reading (or an error, or nothing to filter): the key is the
            // list's, not the global search's, whose panel opening closed a list
            // opened from the title bar (Group 57 review).
            if (!ready || !filter) return;
            try { filter.focus(); filter.select(); } catch (_) { /* noop */ }
            return;
        }
        if (e.key === 'Delete') {
            const row = inFilter ? null : _activeRow(handle);
            if (!row) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            _openDialog(handle, row.dataset.fid);
            return;
        }
        if (e.key !== 'Enter') return;
        if (inFilter) {
            // A scanner's Enter in the filter was taken by the field scan
            // capture (registered first); this one is a person's.
            const row = _activeRow(handle);
            e.preventDefault();
            e.stopImmediatePropagation();
            if (row) _openFilament(handle, row.dataset.fid);
            return;
        }
        // A scanner's Enter belongs to the scan accumulator (scripts.html); a
        // focused button or link must not take it as a press either.
        if (typeof window.enterIsAScan === 'function' && window.enterIsAScan()) {
            e.preventDefault();
            return;
        }
        const active = document.activeElement;
        const onControl = active && handle.panel.contains(active)
            && (active.tagName === 'A' || active.tagName === 'BUTTON');
        const row = onControl ? null : _activeRow(handle);
        if (!onControl && !row) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        if (typeof window.clearScanBuffer === 'function') window.clearScanBuffer();
        if (onControl) active.click();
        else _openFilament(handle, row.dataset.fid);
    }

    // A scan typed into the filter or the reason dialog's fields goes to the
    // scan path, and the field keeps what was typed before it (the canonical
    // rule, inv_core.js). Installed once, before any panel's own key handler,
    // so it sees a scanner's Enter first.
    let _scanCaptureOn = false;
    function _installScanCapture() {
        if (_scanCaptureOn || typeof window.installFieldScanCapture !== 'function') return;
        _scanCaptureOn = true;
        window.installFieldScanCapture({
            // The filter and the note. A reason radio has its own guard (below):
            // it takes every scan typed onto a radio, Enter included, and this
            // capture's one buffer must not hold a radio's keys after it.
            match: (el) => !!(el && el.matches && el.matches('[data-stock-filter], [data-stock-note-input]')),
            isScanPayload: (txt) => (typeof window.looksLikeScanPayload === 'function'
                ? window.looksLikeScanPayload(txt) : /[:/]/.test(txt)),
            onScan: (txt, el) => {
                if (el && el.matches && el.matches('[data-stock-filter]') && _current) {
                    _current._filter = el.value || '';
                    _paint(_current, { index: 0 }, false);
                }
                if (typeof window.processScan === 'function') window.processScan(txt, 'barcode');
            },
        });
    }

    // --- the title-bar count (Group 57.2) ----------------------------------------------
    // #btn-low-stock-count (dashboard.html) says at a glance how many filaments
    // are on the Low and Out lists (Derek, 2026-10-25: "Move it to the title bar
    // beside 🏷️ Backlog and 🛒 Queue, with a count"). The count comes from the
    // dashboard heartbeat's low_stock section, worked out on the server from the
    // tick's own spool and filament reads by the list's own rule
    // (stock_report.glance: no Spoolman read of its own), and from the list
    // itself whenever this window reads it. Excluded filaments never count.
    // A read that failed keeps the count shown (Group 52's rule: a blip is never a
    // 0), with a "?" after it and a dashed border, so a stale count never looks
    // like a fresh one (Group 57 review); before any count it reads "?". The words
    // are in its tooltip and its accessible name, which starts with the number it
    // shows (the bar has no room for them at every Text size).
    // The two sources are kept in order: a heartbeat reads the spool list before
    // its printer probes, so it can land seconds after a fresher read by the list
    // itself; one sent before the list's latest read began is ignored.

    // What the button shows: one number, Low + Out (Group 57.2's option (a)).
    const _countLabel = (c) => String(c.low + c.out);
    let _listReadAt = 0;       // when the list's latest good read was sent

    // Why a count is stale: Spoolman didn't answer, FCC's own count failed, or the
    // answer had none (an FCC from before the count).
    const _WHY = {
        spoolman: "Spoolman didn't answer just now",
        fcc: "FCC couldn't count them just now",
        missing: "FCC didn't send a count",
    };

    function _countWords(c) {
        const under = _finite(c.threshold) !== null ? ` under ${Math.round(c.threshold)} g` : '';
        return `${c.low} low${under}, ${c.out} out`;
    }

    function _paintCount(why) {
        const btn = document.getElementById('btn-low-stock-count');
        if (!btn) return;
        const num = btn.querySelector('[data-low-stock-count]');
        const text = _count ? `${_countLabel(_count)}${why ? '?' : ''}` : '?';
        if (num && num.textContent !== text) num.textContent = text;
        let words;
        if (!_count) words = why ? `Low stock: ?, no count yet (${_WHY[why]}). Opens the list.` : 'Low stock: opens the list.';
        else if (why) words = `Low stock: ${text}, the last count (${_WHY[why]}): ${_countWords(_count)}. Opens the list.`;
        else words = `Low stock: ${text} (${_countWords(_count)}). Opens the list.`;
        btn.title = words;
        btn.setAttribute('aria-label', words);
        btn.dataset.read = why ? 'failed' : 'ok';
        if (_count) {
            btn.dataset.low = String(_count.low);
            btn.dataset.out = String(_count.out);
        }
    }

    function _setCount(low, out, threshold) {
        const n = (v) => (_finite(v) !== null && _finite(v) >= 0 ? Math.round(_finite(v)) : null);
        if (n(low) === null || n(out) === null) return false;
        const t = _finite(threshold) !== null ? _finite(threshold) : (_count ? _count.threshold : null);
        _count = { low: n(low), out: n(out), threshold: t };
        _paintCount(null);
        return true;
    }

    // The heartbeat's low_stock section: {read_ok: true, count, low, out,
    // threshold_g}, or {read_ok: false, read_error} (Spoolman), or {error,
    // read_ok: false} (the section itself failed); undefined when an answer that
    // was asked for one had none. `opts.sentAt`: when that heartbeat was sent.
    // Returns whether it painted a count.
    window._renderLowStockCount = function (sec, opts) {
        const sentAt = opts ? _finite(opts.sentAt) : null;
        if (sentAt !== null && sentAt < _listReadAt) return false;    // older than the list's own read
        if (!sec || typeof sec !== 'object') { _paintCount('missing'); return false; }
        if (sec.read_ok === true && _setCount(sec.low, sec.out, sec.threshold_g)) return true;
        _paintCount(sec.read_ok === false && sec.read_error && !sec.error ? 'spoolman' : 'fcc');
        return false;
    };

    window.openLowStockPanel = function (opts) {
        if (typeof window.mountOverlay !== 'function') return null;
        const restore = opts && opts.restore ? opts.restore : null;
        if (!restore) _disarmReturn();
        _ensureStyle();
        _installScanCapture();
        if (_current) { _closeDialog(_current); _unlisten(_current); }    // re-opening replaces the panel
        const host = document.getElementById('offcanvasSearch');
        const hostOpen = !!(host && host.classList.contains('show'));
        // What had the focus (the button that opened it), for _close to give it back.
        const opener = document.activeElement && document.activeElement !== document.body
            ? document.activeElement : null;
        const handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: _shellHtml(),
            host: hostOpen ? host : undefined,      // closes with the search panel
            occlude: hostOpen ? ['#offcanvasSearch select'] : undefined,
            initialFocus: '.fcc-stock-panel',
            onBackdropClick: () => _close(handle),
            // The reason dialog first: mountOverlay hands Escape to the overlay
            // that mounted first, this one. A dialog that is saving stays.
            onEscape: () => {
                if (!handle._dialog) _close(handle);
                else if (!handle._dialog.busy) _closeDialog(handle);
            },
        });
        _current = handle;
        handle._opener = opener;
        handle._host = hostOpen ? host : null;
        handle._data = null;
        handle._tab = null;
        handle._filter = '';
        handle._threshold = 250;
        handle._dialog = null;
        handle.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-stock-close]')) { _close(handle); return; }
            if (e.target.closest('[data-stock-retry]')) { _load(handle, handle._lastRestore || null); return; }
            const tab = e.target.closest('[data-stock-tab]');
            if (tab) { _setTab(handle, tab.dataset.stockTab); return; }
            if (e.target.closest('a')) return;          // Buy opens its own tab
            const row = e.target.closest('.fcc-stock-row');
            if (!row) return;
            if (e.target.closest('[data-stock-exclude], [data-stock-edit]')) {
                _highlight(handle, _rows(handle).indexOf(row));
                _openDialog(handle, row.dataset.fid);
                return;
            }
            _openFilament(handle, row.dataset.fid);
        });
        const filter = _filterEl(handle);
        if (filter) {
            filter.addEventListener('input', () => {
                handle._filter = filter.value || '';
                if (handle._data) _paint(handle, { index: 0 }, false);
            });
        }
        handle._stockKeys = (e) => _onKey(handle, e);
        document.addEventListener('keydown', handle._stockKeys, true);
        if (!hostOpen) {
            // No search panel to close it with (a list that came back): a window
            // opened over it closes it (2026-10-20 review, browser-3), and a modal
            // arms the come-back, so it returns where it was once that one closes.
            const shows = {
                modal: () => {
                    const at = _snapshot(handle);
                    _close(handle, { keepFocus: true });
                    _armReturn(at);
                },
                offcanvas: () => _close(handle, { keepFocus: true }),
            };
            handle._stockShows = shows;
            document.addEventListener('show.bs.modal', shows.modal);
            document.addEventListener('show.bs.offcanvas', shows.offcanvas);
        }
        _load(handle, restore);
        return handle;
    };

    function _wireButton() {
        ['global-search-low-stock', 'btn-low-stock-count'].forEach((id) => {
            const btn = document.getElementById(id);
            if (btn && !btn.dataset.lowStockWired) {
                btn.dataset.lowStockWired = '1';
                btn.addEventListener('click', () => window.openLowStockPanel());   // no event as opts
            }
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wireButton);
    else _wireButton();

    // A scan typed onto a reason radio (2026-10-21 review, browser-2): a radio is
    // an INPUT, so the scan accumulator ignores its keys, and a short label ("57")
    // or a slower scanner passes installFieldScanCapture's speed test, so its
    // Enter saved the dialog and the scan was lost. A person never types
    // characters onto a radio (Space and the arrows are the radios' own keys), so
    // characters typed onto one and then Enter are a scan: they go to the scan
    // path and the dialog stays. Registered before the field scan capture, so it
    // sees that Enter first.
    const _radioKeys = { buf: '', first: 0, last: 0 };
    document.addEventListener('keydown', (e) => {
        const t = e.target;
        if (!(t && t.matches && t.matches(`#${DIALOG_ID} input[type="radio"]`))) { _radioKeys.buf = ''; return; }
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const now = Date.now();
        if (e.key === 'Enter') {
            const buf = _radioKeys.buf;
            const elapsed = now - _radioKeys.first;
            _radioKeys.buf = '';
            if (!buf) return;                      // a person's Enter: the dialog saves
            e.preventDefault();
            e.stopImmediatePropagation();
            if (typeof window.processScan === 'function') window.processScan(buf, elapsed < 150 ? 'barcode' : 'keyboard');
            return;
        }
        if (e.key.length !== 1 || e.key === ' ') return;
        if (!_radioKeys.buf || now - _radioKeys.last > 2000) { _radioKeys.buf = ''; _radioKeys.first = now; }
        _radioKeys.buf += e.key;
        _radioKeys.last = now;
    }, true);
    _installScanCapture();

    if (typeof window.registerShortcut === 'function') {
        window.registerShortcut({
            id: 'low-stock-arrows', scope: 'Low Stock List', keys: ['↑', '↓'],
            description: "Move between filaments in the ⚠️ Low stock list (the title bar's ⚠️, or the search "
                + 'panel). Wraps at the ends; from the filter, into the list.'
        });
        window.registerShortcut({
            id: 'low-stock-tabs', scope: 'Low Stock List', keys: ['←', '→'],
            description: 'Switch lists: Low, Out, Excluded.'
        });
        window.registerShortcut({
            id: 'low-stock-filter', scope: 'Low Stock List', keys: ['/'],
            description: 'Filter the lists by brand, material, colour, tag, reason or note.'
        });
        window.registerShortcut({
            id: 'low-stock-enter', scope: 'Low Stock List', keys: ['Enter'],
            description: 'Open the highlighted filament (from the filter too).'
        });
        window.registerShortcut({
            id: 'low-stock-delete', scope: 'Low Stock List', keys: ['Del'],
            description: 'Exclude the highlighted filament from Low and Out: asks why first. On the Excluded '
                + 'list: change why, or include it again.'
        });
        window.registerShortcut({
            id: 'low-stock-reason-save', scope: 'Low Stock List', keys: ['Ctrl', 'Enter'],
            description: 'In the reason dialog: save (Enter does too, except in the note).'
        });
        window.registerShortcut({
            id: 'low-stock-escape', scope: 'Low Stock List', keys: ['Esc'],
            description: 'Close the reason dialog, else the list.'
        });
    }
})();
