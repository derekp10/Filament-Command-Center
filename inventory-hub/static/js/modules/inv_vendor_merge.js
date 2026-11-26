/* MODULE: MERGE MANUFACTURERS (Group 66.9; Derek's D1 pick, 2026-11-24) */
console.log("🚀 Loaded Module: VENDOR MERGE");

// window.openVendorMerge({vid, opener}) -> handle
//
// Derek's data holds three manufacturers twice (Sunlu, Prusament, Jessie Premium), and
// Spoolman takes a second one of a name in use. The manufacturer editor's 🔗 Merge… opens
// this window over it (a mountOverlay at the standard tier, hosted by the editor): a box
// that filters, the possible duplicates in the data first (the same name ignoring case,
// spaces and punctuation, then names that look alike; the open manufacturer's own groups
// at the top), each with both manufacturers' filament counts and empty weights, then every
// manufacturer, to merge any of them with the one open in the editor (Derek's 2026-11-24
// ask: "I assume the merge will have a list that looks for or lists possible duplicates?";
// a manufacturer with no filaments, which no filament's ✏️ reaches, is listed too).
//
// A row opens the question (a mountOverlay at the confirm tier): which one is kept (by
// default the one with more filaments, then the one with an empty weight, then the older:
// the server's dry run says), ⇄ to keep the other one, and what the merge does, from the
// server's own plan (POST /api/vendors/<src>/merge_into/<dst> with {"dry_run": true}):
// the filaments that move, the fields the kept one takes where its own is blank, a field
// it keeps its own of, labels whose Brand changes, empty weights that change. A merge
// can't be undone, so it opens on Cancel, its yes waits out a double click (Group 62.3),
// and it holds scans while it is up (a bare CMD:CANCEL is its Cancel). It writes nothing
// itself: the yes posts the merge, and the server reads before every write.
//
// After a merge: vendor:merged {from, into, vendor, moved} goes out first, then
// vendor:updated {id: into, vendor} and inventory:sync-pulse, so an open Filament window,
// Edit Filament, the wizard and the weigh-out list stop holding the deleted id (each
// listens for vendor:merged), and the editor shows the kept one. The window reads its list
// again and says the server's words on its own line, which stands for the toast (toasts
// sit under the overlays); a refusal or a partial merge stays on the question's line with
// a 7 s toast, and a press again finishes it.
//
// Keyboard (standing order): the box has the focus on open; ↓ / ↑ go to the rows and move
// between them across both lists (wrapping), the highlighted row being the rows' one Tab
// stop; Enter on a row opens its question (rows are real buttons, pressed through the scan
// accumulator's rules: a scan's Enter presses nothing); Enter in the box picks nothing; /
// goes back to the box. Escape closes only the window on top (mountOverlay owns it). A
// label scanned into the box goes to the scan path. The window takes no scan: processScan
// closes it for one (window.closeVendorMergeForScan, the audit report's rule) and the scan
// goes on, its answer on top; while its question is up, the question holds every scan.

(function () {
    const STYLE_ID = 'fcc-vendor-merge-style';
    const READ_TIMEOUT_MS = 20000;
    // A merge of a manufacturer with dozens of filaments is a write each, each up to a
    // couple of seconds on a slow Spoolman: Undo's figure (FCC's slowest request).
    const MERGE_TIMEOUT_MS = 120000;
    // A double click's second press (Group 58's figures).
    const DOUBLE_PRESS_MS = 700;
    const DOUBLE_PRESS_SLOP_PX = { mouse: 16, other: 40 };
    const BOX_HINT = 'Find a manufacturer by name or #number';
    let _current = null;      // the window
    let _question = null;     // its question, while one is up
    let _captureOn = false;

    // Merges sent and not accounted for (no answer, one FCC couldn't read, a delete it
    // couldn't confirm), page-wide: {src, dst}, the newest last. Kept on the question, a ⇄
    // or a Cancel and the same row again lost it, and a merge that finished dead-ended in
    // "Couldn't check the merge" (review round 3, R3P4). Dropped once that merge is told as
    // finished, and once an answer shows the one merged was there with no merge of it
    // running (review round 4, R4P1): the server's `source_kept` (any refusal made inside
    // the lock after it read the one merged), and a merge that kept it (`_merged`'s
    // `into`).
    const _unsure = [];
    const _noteUnsure = (src, dst) => {
        const at = _unsure.findIndex((u) => u.src === String(src) && u.dst === String(dst));
        if (at >= 0) _unsure.splice(at, 1);
        _unsure.push({ src: String(src), dst: String(dst) });
    };
    // The merge a `gone` of `gone` finishes: the question's own pair, either way round,
    // when it is one; else the only pair of that source. Two pairs of one source and none
    // the question's: FCC can't tell which finished, and says only that it is gone (review
    // round 4, R4P2: the oldest pair was told, and every window re-pointed to its keeper).
    const _unsureGone = (gone, q) => {
        const all = _unsure.filter((u) => u.src === String(gone));
        if (q) {
            const own = all.find((u) => u.dst === String(q.dst) || u.dst === String(q.src));
            if (own) return own;
        }
        return all.length === 1 ? all[0] : null;
    };
    const _forgetUnsure = (src) => {
        for (let i = _unsure.length - 1; i >= 0; i -= 1) if (_unsure[i].src === String(src)) _unsure.splice(i, 1);
    };

    // Words of a manufacturer (vendor:updated, vendor:merged, vendor:unread, whoever sent
    // them) and the module's own reads, in the order they were SENT: each takes a number
    // when it goes out, a word dispatched elsewhere when it is dispatched, and a read says
    // something only when nothing newer was told of that manufacturer (review round 3,
    // R3P3: a slow read held the record from before a merge's carry and refilled the
    // editor over the merge's; round 4, R4P3: counted by landing, an older read that landed
    // first silenced a newer one). A read's own word carries its number (`fccSeq`).
    let _seq = 0;
    const _toldSeq = {};
    // Reads of a kept manufacturer sent after a merge that may have changed it, still out
    // (review round 5, R5P1: the manufacturer editor's Save went out meanwhile with the boxes
    // from before the carry, and cleared it). The editor's Save waits while one is out.
    const _readsOut = {};
    const _readOut = (id, d) => {
        const k = String(id);
        _readsOut[k] = Math.max(0, (_readsOut[k] || 0) + d);
    };
    window.vendorMergeReading = (id) => (_readsOut[String(id)] || 0) > 0;
    const _noteTold = (id, n) => {
        if (id == null || id === '') return;
        const k = String(id);
        if (!(n <= (_toldSeq[k] || 0))) _toldSeq[k] = n;
    };
    const _toldNewer = (id, n) => (_toldSeq[String(id)] || 0) > n;
    const _wordSeq = (e) => (e && e.detail && typeof e.detail.fccSeq === 'number' ? e.detail.fccSeq : ++_seq);
    document.addEventListener('vendor:updated', (e) => { if (e && e.detail) _noteTold(e.detail.id, _wordSeq(e)); });
    document.addEventListener('vendor:unread', (e) => { if (e && e.detail) _noteTold(e.detail.id, _wordSeq(e)); });
    document.addEventListener('vendor:merged', (e) => {
        const d = (e && e.detail) || {};
        const n = _wordSeq(e);
        _noteTold(d.from, n);
        _noteTold(d.into, n);
    });

    const esc = (v) => (typeof window.escHtml === 'function'
        ? window.escHtml(v)
        : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

    // A manufacturer in words: "Sunlu #35" (the server's _vendor_label).
    const label = (row) => {
        const name = String((row && row.name) || '').split(/\s+/).filter(Boolean).join(' ');
        return name ? `${name} #${row.id}` : `Manufacturer #${row && row.id}`;
    };
    const nFilaments = (n) => `${n} filament${n === 1 ? '' : 's'}`;
    const grams = (g) => `${Number(g)} g`;
    const facts = (row) => `${nFilaments(Number(row.filaments) || 0)} · `
        + (row.empty_spool_weight ? `${grams(row.empty_spool_weight)} empty` : 'no empty weight');

    // Overlay-scoped styles, the audit Find's look: light text on the dark panel (the
    // contrast guard checks it), named text sizes only, widths in rem.
    const P = '#fcc-vendor-merge';
    const Q = '#fcc-vendor-merge-confirm';
    const CSS = `
${P} .fcc-vm-panel { background:#1e1e1e; color:#fff; border:2px solid #0dcaf0; border-radius:8px;
    padding:14px 16px 10px; width:min(40rem, 94vw); height:min(40rem, 86vh); box-sizing:border-box;
    display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,.6); font-size:1rem;
    outline:none; text-align:left; container:fcc-vm-panel / inline-size; }
${P} .fcc-vm-head { display:flex; align-items:center; gap:8px; flex:0 0 auto; }
${P} .fcc-vm-title { font-size:1.2em; font-weight:700; color:#fff; flex:1 1 auto; min-width:0; }
${P} .fcc-vm-head .fcc-help-corner { position:static; }
${P} .fcc-vm-close { background:transparent; border:1px solid #777; color:#fff; border-radius:6px;
    padding:2px 10px; font-size:1em; line-height:1.4; cursor:pointer; flex:0 0 auto; }
${P} .fcc-vm-close:hover, ${P} .fcc-vm-close:focus-visible { border-color:#0dcaf0; outline:none; }
${P} .fcc-vm-sub { color:#ddd; font-size:var(--fcc-fs-small); margin:4px 0 8px; flex:0 0 auto; }
${P} .fcc-vm-box { flex:0 0 auto; box-sizing:border-box; width:100%; background:#111; color:#fff;
    border:1px solid #777; border-radius:6px; padding:6px 10px; font-size:var(--fcc-fs-row); outline:none; }
${P} .fcc-vm-box::placeholder { color:#bbb; opacity:1; }
${P} .fcc-vm-box:focus { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.45); }
${P} .fcc-vm-notice { flex:0 0 auto; margin-top:8px; padding:6px 10px; border-radius:6px; background:#0a2a0a;
    color:#b6f5b6; border:1px solid #3fbf3f; font-weight:bold; font-size:var(--fcc-fs-row); overflow-wrap:anywhere; }
${P} .fcc-vm-notice[data-tone="warn"] { background:#4a3200; color:#ffd27a; border-color:#ffb74d; }
${P} .fcc-vm-notice[hidden] { display:none; }
${P} .fcc-vm-body { overflow:auto; flex:1 1 auto; min-height:0; margin-top:8px; padding-right:4px; }
${P} .fcc-vm-heading { color:#fff; font-weight:700; font-size:var(--fcc-fs-row); margin:6px 0 4px; }
${P} .fcc-vm-row { box-sizing:border-box; display:flex; align-items:center; gap:8px; width:100%; padding:6px 8px;
    min-height:2.6rem; border:1px solid #3a3a3a; border-radius:6px; margin:0 0 4px; background:#262626; color:#fff;
    font:inherit; font-size:var(--fcc-fs-row); text-align:left; cursor:pointer; outline:none; }
${P} button.fcc-vm-row:hover { border-color:#777; }
${P} .fcc-vm-row.kb-active { border-color:#0dcaf0; box-shadow:0 0 0 2px rgba(13,202,240,.55); background:#16333a; }
${P} .fcc-vm-row-open { cursor:default; background:#1a1a1a; border-style:dashed; }
${P} .fcc-vm-main { flex:1 1 0; min-width:0; display:block; }
${P} .fcc-vm-line { display:block; overflow-wrap:anywhere; }
${P} .fcc-vm-name { font-weight:600; color:#fff; }
${P} .fcc-vm-facts { color:#ddd; font-size:var(--fcc-fs-small); }
${P} .fcc-vm-tag { display:inline-block; border-radius:10px; padding:0 7px; margin-right:6px; font-size:var(--fcc-fs-label);
    font-weight:600; white-space:nowrap; vertical-align:baseline; }
${P} .fcc-vm-tag-keep { background:#0a2a0a; border:1px solid #3fbf3f; color:#b6f5b6; }
${P} .fcc-vm-tag-merge { background:#3a0d0d; border:1px solid #ff6b6b; color:#ffd0d0; }
${P} .fcc-vm-tag-open { background:#073b4c; border:1px solid #0dcaf0; color:#bff3ff; }
${P} .fcc-vm-tag-kind { background:#2b2b2b; border:1px solid #888; color:#eee; }
${P} .fcc-vm-go { flex:0 0 auto; color:#bff3ff; font-weight:600; font-size:var(--fcc-fs-label); white-space:nowrap; }
${P} .fcc-vm-state { color:#fff; text-align:center; padding:18px 8px; font-size:var(--fcc-fs-row); }
${P} .fcc-vm-fail { background:#2b2200; color:#ffd54a; border:1px solid #ffd54a; border-radius:6px;
    padding:8px 12px; font-size:var(--fcc-fs-row); font-weight:bold; overflow-wrap:anywhere; }
${P} .fcc-vm-retry { margin-top:10px; background:transparent; color:#ffd54a; border:1px solid #ffd54a;
    border-radius:6px; padding:4px 12px; font-size:var(--fcc-fs-row); font-weight:600; cursor:pointer; }
${P} .fcc-vm-retry:hover, ${P} .fcc-vm-retry:focus-visible { background:#ffd54a; color:#111; outline:none; }
${P} .fcc-vm-foot { color:#ccc; font-size:var(--fcc-fs-small); margin-top:8px; border-top:1px solid #333;
    padding-top:6px; flex:0 0 auto; }
@container fcc-vm-panel (max-width: 30rem) {
    ${P} .fcc-vm-row { flex-wrap:wrap; row-gap:2px; }
    ${P} .fcc-vm-go { flex:1 0 100%; text-align:right; }
}
@media (max-height: 480px) {
    ${P} .fcc-vm-sub, ${P} .fcc-vm-foot { display:none; }
}
${Q} .fcc-vmq-panel { position:relative; background:#1e1e1e; color:#fff; border:2px solid #dc3545; border-radius:8px;
    padding:18px 22px 16px; width:min(34rem, 94vw); max-height:86vh; overflow:auto; box-sizing:border-box;
    text-align:left; }
${Q} .fcc-vmq-title { font-size:1.2em; font-weight:bold; margin:0 2.6rem 10px 0; overflow-wrap:anywhere; }
${Q} .fcc-vmq-lines { margin:0 0 12px; padding:0; list-style:none; }
${Q} .fcc-vmq-lines li { margin:0 0 6px; color:#f8f9fa; font-size:var(--fcc-fs-row); overflow-wrap:anywhere; }
${Q} .fcc-vmq-lines li[data-tone="warn"] { color:#ffd27a; }
${Q} .fcc-vmq-final { color:#ffc; font-weight:600; font-size:var(--fcc-fs-row); margin:0 0 14px; }
${Q} .fcc-vmq-buttons { display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap; }
${Q} .fcc-vmq-buttons .btn { min-width:7.5rem; }
${Q} .fcc-vmq-flash { color:#ffc107; font-size:var(--fcc-fs-small); margin-top:10px; overflow-wrap:anywhere; }
${Q} .fcc-vmq-flash:empty { display:none; }
`;

    function _ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const st = document.createElement('style');
        st.id = STYLE_ID;
        st.textContent = CSS;
        document.head.appendChild(st);
    }

    // A label scanned into the box is a scan, never a filter (Group 61's rule for a box no
    // scan belongs in): the shared capture sends it to the scan path and gives the box its
    // text back. Installed once, before the window's own key listener.
    function _ensureScanCapture() {
        if (_captureOn || typeof window.installFieldScanCapture !== 'function') return;
        _captureOn = true;
        window.installFieldScanCapture({
            match: (el) => !!(el && el.matches && el.matches('[data-vm-box]')),
            isScanPayload: (txt) => (typeof window.looksLikeScanPayload === 'function'
                ? window.looksLikeScanPayload(txt) : /[:/]/.test(txt)),
            labels: true,
        });
    }

    const editorEl = () => document.getElementById('vendorEditModal');
    const _alive = (h) => !!(h && !h._closed && h.element && h.element.isConnected);
    const _box = (h) => h.panel.querySelector('[data-vm-box]');
    const _bodyEl = (h) => h.panel.querySelector('[data-vm-body]');
    const _rows = (h) => Array.from(_bodyEl(h).querySelectorAll('button.fcc-vm-row'));
    const shield = () => { if (window.fccShieldNextPress) window.fccShieldNextPress(); };
    const shortcutsUp = () => {
        const s = document.getElementById('fcc-shortcuts-overlay');
        return !!(s && s.getClientRects().length);
    };

    function _windowHtml() {
        const help = window.fccCornerHelpHtml ? window.fccCornerHelpHtml('fcc-vendor-merge', 'window') : '';
        return `<div class="fcc-vm-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-vm-title" tabindex="-1">
            <div class="fcc-vm-head">
                <div class="fcc-vm-title" id="fcc-vm-title">🔗 Merge manufacturers</div>
                ${help}
                <button type="button" class="fcc-vm-close" data-vm-close aria-label="Close">✕</button>
            </div>
            <div class="fcc-vm-sub">Two manufacturers that are one maker: every filament of the one merged moves to the one kept, its spools with it, and the merged one is deleted. Nothing changes until you answer the question a row opens.</div>
            <input type="text" class="fcc-vm-box" data-vm-box autocomplete="off" spellcheck="false"
                   placeholder="${esc(BOX_HINT)}" aria-label="${esc(BOX_HINT)}">
            <div class="fcc-vm-notice" role="status" data-vm-notice hidden></div>
            <div class="fcc-vm-body" data-vm-body data-vm-state="loading">
                <div class="fcc-vm-state" role="status">Reading the manufacturers…</div>
            </div>
            <div class="fcc-vm-foot">↑↓ move · Enter opens the merge question · / to the box · Esc closes</div>
        </div>`;
    }

    function _notice(h, msg, tone) {
        if (!_alive(h)) return;
        const el = h.panel.querySelector('[data-vm-notice]');
        if (!el) return;
        el.textContent = msg || '';
        el.hidden = !msg;
        if (tone) el.dataset.tone = tone; else delete el.dataset.tone;
    }

    // The highlighted row: the rows' one stop in the Tab order. `focus`: the keyboard goes there.
    function _highlight(h, idx, focus) {
        const rows = _rows(h);
        rows.forEach((r) => { r.classList.remove('kb-active'); r.tabIndex = -1; r.setAttribute('aria-current', 'false'); });
        const row = rows[idx];
        if (!row) return;
        row.classList.add('kb-active');
        row.tabIndex = 0;
        row.setAttribute('aria-current', 'true');
        if (focus) { try { row.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        try { row.scrollIntoView({ block: 'nearest' }); } catch (_) { /* noop */ }
    }

    function _move(h, delta) {
        const rows = _rows(h);
        if (!rows.length) return;
        const cur = rows.indexOf(document.activeElement);
        const next = cur < 0
            ? Math.max(0, rows.findIndex((r) => r.classList.contains('kb-active')))
            : (cur + delta + rows.length) % rows.length;
        _highlight(h, next, true);
    }

    function _focusBox(h) {
        try { _box(h).focus({ preventScroll: true }); } catch (_) { /* noop */ }
    }

    // Does a manufacturer row show for the box's text? Its name, or its number (#35 or 35).
    function _matches(row, text) {
        if (!text) return true;
        const t = text.toLowerCase().replace(/^#/, '');
        return String(row.name || '').toLowerCase().includes(t) || String(row.id) === t;
    }

    function _pairHtml(h, kind, keep, other) {
        const openId = String(h._vid);
        // Real spaces between the tags and the words (a margin alone reads "keepSunlu #4"
        // to a screen reader and in copied text).
        const tagFor = (row) => (String(row.id) === openId ? '<span class="fcc-vm-tag fcc-vm-tag-open">open in the editor</span> ' : '');
        const kindWords = kind === 'same_name' ? 'same name' : 'similar name';
        const line = (tag, tagCls, row) => `<span class="fcc-vm-line"><span class="fcc-vm-tag ${tagCls}">${tag}</span> `
            + `<span class="fcc-vm-name">${esc(label(row))}</span> ${tagFor(row)}<span class="fcc-vm-facts">· ${esc(facts(row))}</span></span>`;
        return `<button type="button" class="fcc-vm-row" tabindex="-1" data-vm-src="${esc(other.id)}" data-vm-dst="${esc(keep.id)}"
                    title="${esc(`Merge ${label(other)} into ${label(keep)}`)}">
                <span class="fcc-vm-main">${line('keep', 'fcc-vm-tag-keep', keep)}${line('merge', 'fcc-vm-tag-merge', other)}</span>
                <span class="fcc-vm-go"><span class="fcc-vm-tag fcc-vm-tag-kind">${esc(kindWords)}</span> Merge…</span>
            </button>`;
    }

    function _vendorRowHtml(h, row) {
        if (String(row.id) === String(h._vid)) {
            return `<div class="fcc-vm-row fcc-vm-row-open"><span class="fcc-vm-main">
                    <span class="fcc-vm-line"><span class="fcc-vm-name">${esc(label(row))}</span> <span class="fcc-vm-tag fcc-vm-tag-open">open in the editor</span></span>
                    <span class="fcc-vm-line fcc-vm-facts">${esc(facts(row))}</span></span></div>`;
        }
        return `<button type="button" class="fcc-vm-row" tabindex="-1" data-vm-src="${esc(row.id)}" data-vm-dst="${esc(h._vid)}"
                    title="${esc(`Merge ${label(row)} and ${label(h._data.vendor)}: the question says which is kept`)}">
                <span class="fcc-vm-main">
                    <span class="fcc-vm-line fcc-vm-name">${esc(label(row))}</span>
                    <span class="fcc-vm-line fcc-vm-facts">${esc(facts(row))}</span>
                </span>
                <span class="fcc-vm-go">Merge…</span>
            </button>`;
    }

    // The two lists, filtered by the box. The keyboard on a row stays on the same pair or
    // manufacturer while the new list holds it; else it goes to the box, never to a row the
    // person didn't reach.
    function _paint(h) {
        const d = h._data;
        if (!d) return;
        const body = _bodyEl(h);
        const text = String(_box(h).value || '').trim();
        const a = document.activeElement;
        const was = a && body.contains(a) && a.dataset ? `${a.dataset.vmSrc || ''}:${a.dataset.vmDst || ''}` : null;
        const byId = {};
        (d.vendors || []).forEach((v) => { byId[String(v.id)] = v; });
        const pairs = [];
        // Each pair once (review round 1, S7): a pair two groups hold is drawn with the
        // first group's kind, and the server lists same-name groups first.
        const seen = new Set();
        (d.groups || []).forEach((g) => {
            const keep = byId[String(g.keep)];
            if (!keep) return;
            (g.ids || []).forEach((id) => {
                if (String(id) === String(g.keep)) return;
                const other = byId[String(id)];
                const key = `${id}:${g.keep}`;
                if (!other || seen.has(key)) return;
                seen.add(key);
                if (_matches(keep, text) || _matches(other, text)) pairs.push(_pairHtml(h, g.kind, keep, other));
            });
        });
        const others = (d.vendors || []).filter((v) => _matches(v, text));
        let html = `<div class="fcc-vm-heading">Possible duplicates (${pairs.length})</div>`;
        html += pairs.length ? pairs.join('')
            : `<div class="fcc-vm-state" role="status">${text ? `No possible duplicate matches “${esc(text)}”.`
                : 'No two manufacturers share a name or look alike.'}</div>`;
        html += `<div class="fcc-vm-heading">Merge ${esc(label(d.vendor))} with another manufacturer</div>`;
        html += others.length ? others.map((v) => _vendorRowHtml(h, v)).join('')
            : `<div class="fcc-vm-state" role="status">No manufacturer matches “${esc(text)}”.</div>`;
        body.innerHTML = html;
        body.dataset.vmState = 'ready';
        const rows = _rows(h);
        const keep = was ? rows.findIndex((r) => `${r.dataset.vmSrc}:${r.dataset.vmDst}` === was) : -1;
        if (keep >= 0) { _highlight(h, keep, true); return; }
        _highlight(h, 0, false);
        if (was !== null) _focusBox(h);
    }

    // A read that failed: its words and Try again. The list read before it is dropped
    // (review round 1, P-S3: the next key in the box drew it again, a manufacturer the
    // merge had just deleted included, and the failure line went).
    // `final`: the manufacturer open isn't in Spoolman any more, which asking again can't
    // change (review round 3, R3P4): no Try again.
    function _fail(h, why, final) {
        const body = _bodyEl(h);
        const hadKeys = body.contains(document.activeElement);
        h._data = null;
        body.innerHTML = `<div class="fcc-vm-fail" role="alert" data-vm-fail>
                <div>⚠️ Couldn't read the manufacturers: ${esc(why)}</div>
                ${final ? '' : '<button type="button" class="fcc-vm-retry" data-vm-retry>↻ Try again</button>'}
            </div>`;
        body.dataset.vmState = 'error';
        if (hadKeys) _focusBox(h);
    }

    // Only the newest read paints. `then`: run after a good paint (the keyboard's next stop
    // after a merge).
    function _read(h, then) {
        h._seq += 1;
        const seq = h._seq;
        if (!h._data) {
            // A keyboard press on ↻ Try again: the body it was in is redrawn, and the keyboard
            // goes to the box, never the page (review round 3, R3P5: letters typed next went
            // to the scan path, and their Enter sent a number as a spool scan).
            const hadKeys = _bodyEl(h).contains(document.activeElement);
            _bodyEl(h).innerHTML = '<div class="fcc-vm-state" role="status">Reading the manufacturers…</div>';
            _bodyEl(h).dataset.vmState = 'loading';
            if (hadKeys) _focusBox(h);
        }
        const url = `/api/vendors/${encodeURIComponent(h._vid)}/merge_options`;
        return window.fetchT(url, { cache: 'no-store' }, READ_TIMEOUT_MS)
            .then((res) => res.json().then((data) => ({ res, data }), () => ({ res, data: null })))
            .then(({ res, data }) => {
                if (seq !== h._seq || !_alive(h)) return;
                if (!data || typeof data !== 'object') { _fail(h, `FCC's answer couldn't be read (HTTP ${res.status}).`); return; }
                if (data.success !== true || !data.vendor || !Array.isArray(data.vendors)) {
                    const why = String(data.msg || `FCC answered with an error (HTTP ${res.status}).`);
                    // The manufacturer open is gone: the merge an earlier press sent of it,
                    // finished, is told as one (review round 3, R3P4); else said for good.
                    if (data.gone != null) {
                        const pair = _unsureGone(data.gone, null);
                        if (pair) _settleUnsure(h, null, pair, why); else _fail(h, why, true);
                        return;
                    }
                    _fail(h, why);
                    return;
                }
                h._data = data;
                _paint(h);
                if (typeof then === 'function') then();
            }, () => {
                if (seq !== h._seq || !_alive(h)) return;
                _fail(h, "FCC didn't answer.");
            });
    }

    // ↻ Try again's press, for _secondPress.
    function _notePress(h, e) {
        h._lastPress = e && e.detail > 0
            ? { at: Date.now(), x: e.clientX, y: e.clientY, slop: DOUBLE_PRESS_SLOP_PX[e.pointerType === 'mouse' ? 'mouse' : 'other'] }
            : null;
    }

    // A row's click that is the second press of a double click opens nothing: the click
    // count, or a pointer press near Try again's under 700 ms ago (its answer paints the
    // rows where the button was). A keyboard's click (detail 0) always opens.
    function _secondPress(h, e) {
        if (e.detail > 1) return true;
        const p = h._lastPress;
        if (!p || e.detail === 0 || Date.now() - p.at >= DOUBLE_PRESS_MS) return false;
        return Math.abs(e.clientX - p.x) <= p.slop && Math.abs(e.clientY - p.y) <= p.slop;
    }

    function _onKey(h, e) {
        if (!_alive(h)) return;
        if (typeof window.isTopOverlay === 'function' && !window.isTopOverlay(h.element)) return;
        if (shortcutsUp()) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const box = _box(h);
        const inBox = e.target === box;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            const rows = _rows(h);
            if (!rows.length) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (!inBox) { _move(h, e.key === 'ArrowDown' ? 1 : -1); return; }
            const marked = rows.findIndex((r) => r.classList.contains('kb-active'));
            _highlight(h, e.key === 'ArrowDown' ? Math.max(0, marked) : rows.length - 1, true);
            return;
        }
        if (e.key === '/' && !inBox) {
            if (e.repeat || (window.scanIsArriving && window.scanIsArriving())) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
            try { box.focus({ preventScroll: true }); box.select(); } catch (_) { /* noop */ }
            return;
        }
        // A person's Enter in the box filters nothing more and picks nothing.
        if (e.key === 'Enter' && inBox) e.preventDefault();
    }

    function _unlisten(h) {
        if (h._keys) { document.removeEventListener('keydown', h._keys, true); h._keys = null; }
        if (h._shows) {
            document.removeEventListener('show.bs.modal', h._shows);
            document.removeEventListener('show.bs.offcanvas', h._shows);
            h._shows = null;
        }
        if (h._closedListener) { document.removeEventListener('fcc:overlay-closed', h._closedListener); h._closedListener = null; }
    }

    // `keepFocus`: another window takes the keyboard.
    function _close(h, opts) {
        if (!h || h._closed) return;
        h._closed = true;
        h._seq += 1;
        _unlisten(h);
        if (_question && _question.win === h) _closeQuestion(_question, { keepFocus: true });
        try { h.cleanup(); } catch (_) { /* noop */ }
        if (_current === h) _current = null;
        const opener = h._opener;
        h._opener = null;
        const a = document.activeElement;
        if (!(opts && opts.keepFocus) && (!a || a === document.body)) {
            // The opener can't take it when a hold hid it (🔗 Merge…; review round 3,
            // R3P6): the editor's name box, else the editor, so its keys and Escape work.
            const canTake = (el) => !!(el && el.isConnected && !el.disabled && el.getClientRects().length);
            const ed = editorEl();
            const name = document.getElementById('vendoredit-name');
            const to = canTake(opener) ? opener
                : (ed && ed.classList.contains('show') ? (canTake(name) && ed.contains(name) ? name : ed) : null);
            if (to) { try { to.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        }
    }

    // ---------------------------------------------------------------- the question

    function _questionHtml() {
        const help = window.fccCornerHelpHtml ? window.fccCornerHelpHtml('fcc-vendor-merge-confirm') : '';
        return `<div class="fcc-vmq-panel" role="dialog" aria-modal="true" aria-labelledby="fcc-vmq-title">
            ${help}
            <div class="fcc-vmq-title" id="fcc-vmq-title" data-vmq-title>🔗 Merge manufacturers?</div>
            <ul class="fcc-vmq-lines" data-vmq-lines><li role="status">Checking what moves…</li></ul>
            <div class="fcc-vmq-final">A merge can't be undone.</div>
            <div class="fcc-vmq-buttons">
                <button type="button" class="btn btn-secondary btn-sm" data-vmq="cancel">Cancel</button>
                <button type="button" class="btn btn-outline-info btn-sm" data-vmq="swap" disabled>⇄ Keep the other</button>
                <button type="button" class="btn btn-danger btn-sm" data-vmq="yes" disabled>🔗 Merge</button>
            </div>
            <div class="fcc-vmq-flash" role="alert" data-vmq-flash></div>
        </div>`;
    }

    const _qAlive = (q) => !!(q && !q.closed && q.handle && q.handle.element && q.handle.element.isConnected);
    const _qBtn = (q, which) => q.handle.element.querySelector(`[data-vmq="${which}"]`);

    function _qFlash(q, msg) {
        if (!_qAlive(q)) return;
        const el = q.handle.element.querySelector('[data-vmq-flash]');
        if (el) el.textContent = msg || '';
    }

    function _closeQuestion(q, opts) {
        if (!q || q.closed) return;
        q.closed = true;
        q.seq += 1;
        if (q.release) { q.release(); q.release = null; }
        if (q.onClosed) { document.removeEventListener('fcc:overlay-closed', q.onClosed); q.onClosed = null; }
        if (q.handle) { const hd = q.handle; try { hd.cleanup(); } catch (_) { /* noop */ } }
        if (_question === q) _question = null;
        if ((opts && opts.keepFocus) || !_alive(q.win)) return;
        // Back to the row the question came from, lit (review round 1, P-S4: the keyboard
        // went back to an unlit row while another stayed lit, and Enter opened that one's;
        // and a list read again under the question had replaced the row): found again by
        // its pair in the list as it is now, else the box.
        const rows = _rows(q.win);
        const at = q.rowKey ? rows.findIndex((r) => `${r.dataset.vmSrc}:${r.dataset.vmDst}` === q.rowKey) : -1;
        if (at >= 0) _highlight(q.win, at, true);
        else _focusBox(q.win);
    }

    // `e`: the click that answered, when one did. Only a pointer's press shields the next
    // press (the wizard's question's rule): an Escape or a scan's cancel took no press, and
    // shielding then ate the person's next click at the spot of their last one. Answers
    // false when it closed nothing (a merge on its way), so processScan doesn't take a
    // bare CMD:CANCEL for one that answered a question (review round 1, P-S8).
    // `scanned`: a bare CMD:CANCEL scan, refused while the merge is on its way and logged as
    // every scan outcome is (review round 2, R2P6).
    function _qCancel(q, e, scanned) {
        if (!_qAlive(q)) return false;
        if (q.inFlight) {
            _qFlash(q, 'The merge is on its way: wait for its answer.');
            if (scanned && window.logClientEvent) {
                window.logClientEvent('⚠️ Scan "CMD:CANCEL" ignored: the manufacturer merge is on its way', 'WARNING');
            }
            return false;
        }
        if (e && e.detail > 0) shield();
        _closeQuestion(q);
        return true;
    }

    function _qSetButtons(q, on) {
        ['cancel', 'swap', 'yes'].forEach((w) => { const b = _qBtn(q, w); if (b) b.disabled = !on; });
    }

    // The plan's lines, in the server's words where it gives them.
    function _qLines(plan) {
        const src = plan.source;
        const dst = plan.target;
        const lines = [];
        lines.push({ text: `✓ Keep ${label(dst)}: ${nFilaments(dst.filaments)}, `
            + (dst.empty_spool_weight ? `${grams(dst.empty_spool_weight)} empty.` : 'no empty spool weight.') });
        const fils = plan.filaments || [];
        const one = fils.length === 1;
        if (fils.length) {
            const named = fils.slice(0, 3).map((f) => `#${f.id} ${[f.material, f.name].filter(Boolean).join(' ')}`.trim());
            const more = fils.length - named.length;
            lines.push({ text: `🗑️ Delete ${label(src)}: its ${nFilaments(fils.length)} ${one ? 'moves' : 'move'} to ${label(dst)} (${named.join(', ')}`
                + (more > 0 ? ` and ${more} more` : '') + `), ${one ? 'its spools with it' : 'their spools with them'}.` });
        } else {
            lines.push({ text: `🗑️ Delete ${label(src)}: it has no filaments.` });
        }
        (plan.carry_words || []).forEach((w) => lines.push({ text: `↪ ${label(dst)} takes ${label(src)}'s ${w} (its own is blank).` }));
        (plan.kept_own_words || []).forEach((w) => lines.push({ text: w }));
        if (plan.label_change && fils.length) {
            lines.push({ tone: 'warn', text: `🏷️ ${one ? 'Its labels print' : 'Their labels print'} “${String(dst.name || '').trim()}” as the Brand from now on: ${one ? 'its' : 'their'} spools' labels, and any swatch already printed, go on the 🏷️ Backlog for a reprint.` });
        }
        // Singular where one filament is meant (review round 1, P-S6).
        const w = plan.weight_note;
        const g = (x) => (x ? grams(x) : 'none');
        if (w && Array.isArray(w.moved_without_own) && w.moved_without_own.length) {
            const n = w.moved_without_own.length;
            const who = n === fils.length ? (n === 1 ? 'It has' : 'They have') : (n === 1 ? '1 of them has' : `${n} of them have`);
            const own = n === 1 ? 'its own' : 'their own';
            const them = n === 1 ? 'it' : 'them';
            lines.push({ tone: 'warn', text: `⚖️ ${who} no empty spool weight of ${own}: FCC reads ${g(w.to_g)} for ${them} from now on (${g(w.from_g)} before), and a Gross weighing takes it off.` });
        }
        if (w && Array.isArray(w.kept_without_own) && w.kept_without_own.length) {
            const n = w.kept_without_own.length;
            lines.push({ tone: 'warn', text: n === 1
                ? `⚖️ ${label(dst)}'s 1 filament with no empty spool weight of its own reads ${g(w.to_g)} from now on.`
                : `⚖️ ${label(dst)}'s ${n} filaments with no empty spool weight of their own read ${g(w.to_g)} from now on.` });
        }
        return lines;
    }

    function _qPaint(q, data) {
        const plan = data.plan;
        q.plan = plan;
        q.lastPlan = plan;
        // The keyboard had nowhere to go back to (review round 2, R2P5: a keyboard press on
        // ↻ Try again, which the plan's lines replaced): Cancel, the safe answer. Where the
        // person moved it while the plan was out, it stays (review round 3, R3P7: ⇄ took it
        // back from Cancel, and their Enter swapped again).
        const lost = _qKeysLost(q);
        const el = q.handle.element;
        el.querySelector('[data-vmq-title]').textContent = `🔗 Merge ${label(plan.source)} into ${label(plan.target)}?`;
        el.querySelector('[data-vmq-lines]').innerHTML = _qLines(plan)
            .map((l) => `<li${l.tone ? ` data-tone="${esc(l.tone)}"` : ''}>${esc(l.text)}</li>`).join('');
        const swap = _qBtn(q, 'swap');
        swap.textContent = `⇄ Keep ${label(plan.source)} instead`;
        const yes = _qBtn(q, 'yes');
        yes.textContent = `🔗 Merge into ${label(plan.target)}`;
        // Armed again at each plan: the yes takes no click until a double click has passed.
        const arm = window.armedClick || ((fn) => fn);
        yes.onclick = arm((e) => _qYes(q, e), window.questionArmMs ? window.questionArmMs() : 0);
        _qSetButtons(q, true);
        // The button that had the keyboard before the plan was asked (⇄, or Cancel after a
        // refusal) lost it while disabled: it gets it back.
        if (q.refocus) {
            const b = _qBtn(q, q.refocus);
            q.refocus = null;
            if (lost && b) { try { b.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
        } else if (lost) _qFocus(q, 'cancel');
        if (window.fccFitQuestion) { try { window.fccFitQuestion(el.querySelector('.fcc-vmq-panel')); } catch (_) { /* noop */ } }
    }

    // The question had the keyboard and lost it (review round 2, R2P5): the button it was
    // on was redrawn away (↻ Try again) or turned off while a plan was asked (⇄), and the
    // focus went to the page, where Enter and Space did nothing until Tab.
    function _qKeysLost(q) {
        if (!_qAlive(q)) return false;
        if (typeof window.isTopOverlay === 'function' && !window.isTopOverlay(q.handle.element)) return false;
        const a = document.activeElement;
        return !a || a === document.body || (!!a.disabled && q.handle.element.contains(a));
    }

    function _qFocus(q, which) {
        const b = _qBtn(q, which);
        if (b && !b.disabled) { try { b.focus({ preventScroll: true }); } catch (_) { /* noop */ } }
    }

    // `final`: a manufacturer that isn't in Spoolman any more, which asking again can't
    // change (review round 2, R2S8: its ↻ Try again could only fail).
    function _qPlanFailed(q, why, final) {
        const el = q.handle.element;
        el.querySelector('[data-vmq-lines]').innerHTML = `<li data-tone="warn" role="alert">⚠️ Couldn't check the merge: ${esc(why)}</li>`
            + (final ? '' : '<li><button type="button" class="btn btn-outline-warning btn-sm" data-vmq="retry">↻ Try again</button></li>');
        _qBtn(q, 'cancel').disabled = false;
        _qBtn(q, 'swap').disabled = true;
        _qBtn(q, 'yes').disabled = true;
        // The plan ⇄ asked for failed: nothing to give the keyboard back to there.
        const lost = _qKeysLost(q);
        q.refocus = null;
        if (lost) _qFocus(q, final || !_qBtn(q, 'retry') ? 'cancel' : 'retry');
    }

    // A manufacturer of the pair in words, from what the page read last: the plan, else
    // the window's list, else its number.
    function _qName(q, id) {
        const p = q.plan || q.lastPlan;
        if (p && p.source && String(p.source.id) === String(id)) return label(p.source);
        if (p && p.target && String(p.target.id) === String(id)) return label(p.target);
        const d = q.win && q.win._data;
        const v = d && Array.isArray(d.vendors) ? d.vendors.find((x) => x && String(x.id) === String(id)) : null;
        return v ? label(v) : `Manufacturer #${id}`;
    }

    // The server's plan for the pair as it stands. A first ask that the server would keep
    // the other way round is asked again swapped, once, before anything is drawn; ⇄ is the
    // person's choice and is never swapped back.
    function _qPlan(q) {
        q.seq += 1;
        const seq = q.seq;
        q.plan = null;
        _qSetButtons(q, false);
        _qBtn(q, 'cancel').disabled = false;
        const el = q.handle.element;
        const linesEl = el.querySelector('[data-vmq-lines]');
        if (linesEl) linesEl.innerHTML = '<li role="status">Checking what moves…</li>';
        // The direction being asked, while it is asked (review round 2, R2P5: a ⇄ whose plan
        // failed kept the old direction's title and button words).
        el.querySelector('[data-vmq-title]').textContent = `🔗 Merge ${_qName(q, q.src)} into ${_qName(q, q.dst)}?`;
        _qBtn(q, 'swap').textContent = '⇄ Keep the other';
        _qBtn(q, 'yes').textContent = '🔗 Merge';
        const url = `/api/vendors/${encodeURIComponent(q.src)}/merge_into/${encodeURIComponent(q.dst)}`;
        window.fetchT(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dry_run: true }),
        }, READ_TIMEOUT_MS)
            .then((res) => res.json().then((data) => ({ res, data }), () => ({ res, data: null })))
            .then(({ res, data }) => {
                if (seq !== q.seq || !_qAlive(q)) return;
                if (!data || typeof data !== 'object') { _qPlanFailed(q, `FCC's answer couldn't be read (HTTP ${res.status}).`); return; }
                if (data.success !== true || !data.plan) {
                    const why = String(data.msg || `FCC answered with an error (HTTP ${res.status}).`);
                    if (data.gone != null) { _qSettleGone(q, why, data.gone); return; }
                    _qPlanFailed(q, why);
                    return;
                }
                if (!q.userSwapped && !q.triedSwap && data.default_keep != null && String(data.default_keep) !== String(q.dst)) {
                    q.triedSwap = true;
                    const s = q.src; q.src = q.dst; q.dst = s;
                    _qPlan(q);
                    return;
                }
                _qPaint(q, data);
            }, () => {
                if (seq !== q.seq || !_qAlive(q)) return;
                _qPlanFailed(q, "FCC didn't answer.");
            });
    }

    function _qSwap(q) {
        if (!_qAlive(q) || q.inFlight) return;
        q.userSwapped = true;
        const s = q.src; q.src = q.dst; q.dst = s;
        _qFlash(q, '');
        q.refocus = 'swap';
        _qPlan(q);
    }

    // A merge that landed: the events first (every open window stops holding the deleted
    // id), whether or not the question or the window is still up.
    // `pair`: the merge told, when it isn't the question's own pair (an earlier press's,
    // found finished; R3P4). `q` may be a bare stand-in for a window with no question.
    // `at`: the number of the read the merge is told from (_settleUnsure, _qCheckLanded),
    // so its words never outrank a word sent after that read; when a newer word of the kept
    // one was told since, the record it brings is older than what the windows show, and the
    // merge is told with no record, `stale` (the deleted id must still go; review round 5,
    // R5P2: told as the newest word, an older record refilled the editor over a newer
    // merge's carry, and silenced a newer read).
    function _merged(q, data, pair, at) {
        const from = String(pair ? pair.src : q.src);
        const into = String(pair ? pair.dst : q.dst);
        const fromRead = typeof at === 'number';
        const stale = fromRead && _toldNewer(into, at);
        const vendor = stale ? null : (data.vendor || null);
        const numbered = (detail) => (fromRead && !stale ? Object.assign(detail, { fccSeq: at }) : detail);
        _forgetUnsure(from);
        _forgetUnsure(into);
        const merged = { from, into, vendor, moved: Array.isArray(data.moved_filament_ids) ? data.moved_filament_ids : [] };
        if (stale) merged.stale = true;
        document.dispatchEvent(new CustomEvent('vendor:merged', { detail: numbered(merged) }));
        if (vendor) document.dispatchEvent(new CustomEvent('vendor:updated', { detail: numbered({ id: into, vendor }) }));
        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
        const msg = String(data.msg || `Merged ${from} into ${into}.`) + _labelTroubleWords(data);
        const trouble = !!_labelTroubleWords(data);
        const win = q.win;
        if (_qAlive(q)) { shield(); _closeQuestion(q, { keepFocus: true }); }
        // The editor shows the kept one now (inv_details.js's vendor:merged listener), and
        // the one merged is gone: the window follows.
        if (win && String(win._vid) === from) win._vid = into;
        if (_alive(win)) {
            // The window's line stands for the toast, which sits under it (review round 1,
            // P-S5): label trouble said there too, in the warning tone.
            _notice(win, msg, trouble ? 'warn' : '');
            // A read that fails leaves the keyboard in the box (P-S3), unless another
            // question has it (review round 3, R3P8: one opened while a gone answer's read
            // was out lost it to the box beneath).
            const a = document.activeElement;
            const another = !!(_question && _question !== q);
            // Never off a row the person arrowed to (review round 4, R4P4: any of the
            // window's elements counted, and the read's callback then lit row 0).
            const free = !a || a === document.body || !a.isConnected || a === _box(win)
                || !!(q.handle && q.handle.element && q.handle.element.contains(a));
            // Row 0 only when this merge put the keyboard in the box (review round 5, R5P3: a
            // person typing in the box lost it to row 0 once the list landed in a pause, and
            // the rest of the word went to the scan path).
            const moved = !another && free && a !== _box(win);
            if (!another && free) _focusBox(win);
            const typed = _box(win).value;
            _read(win, () => {
                if (!moved) return;
                // The first row takes the keyboard only while it is still where the merge
                // left it (review round 2, R2P4: a read slower than the person moved it from
                // the box they were typing in, whose next keys went to a row and on to the
                // scan path, or under a question opened meanwhile): no question up, the box
                // focused, its text as it was. Else _paint's own rule stands.
                if (_question || document.activeElement !== _box(win) || _box(win).value !== typed) return;
                if (_rows(win).length) _highlight(win, 0, true);
            });
        } else if (window.showToast) {
            window.showToast(msg, trouble ? 'warning' : 'success', trouble ? 7000 : 4000);
        }
    }

    // Labels whose Brand changed that the merge couldn't confirm it marked, in words.
    function _labelTroubleWords(data) {
        const f = data && data.labels_flagged;
        return f && Array.isArray(f.errors) && f.errors.length
            ? " FCC couldn't confirm that every label whose Brand changed is marked for a reprint: the Activity Log says which."
            : '';
    }

    // The manufacturers, read once: {read, vendors}.
    function _readVendors() {
        return window.fetchT('/api/vendors', { cache: 'no-store' }, READ_TIMEOUT_MS)
            .then((r) => r.json())
            .then((d) => (d && d.success === true && Array.isArray(d.vendors)
                ? { read: true, vendors: d.vendors } : { read: false, vendors: [] }),
            () => ({ read: false, vendors: [] }));
    }

    const _keptIn = (q, r) => (r.read ? r.vendors.find((v) => v && String(v.id) === String(q.dst)) || null : null);

    // A merge whose answer was lost, or that FCC couldn't read, or whose delete FCC couldn't
    // tell had landed (may_have_deleted): the manufacturers read again. The one merged gone
    // and the one kept there means the merge finished, and it is told as one that answered
    // (review round 1, P-S9: the re-plan said "nothing was merged", and no window heard the
    // merge). Resolves {landed, read, kept}: the read is handed on, so a merge that didn't
    // finish tells the windows the kept one's record from it.
    function _qCheckLanded(q, data) {
        const at = ++_seq;
        _readOut(q.dst, 1);
        return _readVendors().then((r) => {
            _readOut(q.dst, -1);
            const kept = _keptIn(q, r);
            const seen = { landed: false, read: r.read, kept, at };
            if (!r.read || !kept || r.vendors.some((v) => v && String(v.id) === String(q.src))) return seen;
            _merged(q, {
                vendor: kept,
                moved_filament_ids: (data && data.moved_filament_ids) || [],
                labels_flagged: data && data.labels_flagged,
                msg: `${_qName(q, q.src)} is gone from Spoolman: the merge into ${label(kept)} finished.`,
            }, null, at);
            seen.landed = true;
            return seen;
        });
    }

    // What a merge that didn't finish may have done to the kept one, told to every window
    // holding it: the record its answer carried (a carry that landed changed it), else the
    // one a read of the manufacturers found; when FCC can't read it, the manufacturer editor
    // saves nothing until it is opened again (vendor:unread; review round 2, R2P1: it kept
    // showing the fields from before the carry, and its Save cleared what the carry copied).
    function _qTellKept(q, data, seen) {
        const dst = String(q.dst);
        // The carry's answer was lost and FCC couldn't see it land: it may still land, so a
        // read now may come before it. The kept one's editor holds instead (review round 5,
        // R5S2: the record from before the carry was told as current).
        if (data && data.carry_unsure) {
            document.dispatchEvent(new CustomEvent('vendor:unread', { detail: { id: dst, fccSeq: ++_seq } }));
            return;
        }
        if (data && data.vendor && String(data.vendor.id) === dst) {
            document.dispatchEvent(new CustomEvent('vendor:updated', { detail: { id: dst, vendor: data.vendor } }));
            return;
        }
        // A read says something only when nothing newer was told of the kept one since it
        // was sent (R3P3, R4P3); its word carries its own number.
        const settle = (s, at) => {
            if (_toldNewer(dst, at)) return;
            if (s && s.read) {
                if (s.kept) document.dispatchEvent(new CustomEvent('vendor:updated', { detail: { id: dst, vendor: s.kept, fccSeq: at } }));
                return;
            }
            document.dispatchEvent(new CustomEvent('vendor:unread', { detail: { id: dst, fccSeq: at } }));
        };
        if (seen) { settle(seen, seen.at || 0); return; }
        const at = ++_seq;
        _readOut(dst, 1);
        _readVendors().then((r) => { _readOut(dst, -1); settle({ read: r.read, kept: _keptIn(q, r) }, at); });
    }

    // The server's 404 `gone` names a manufacturer of the pair that isn't in Spoolman any
    // more (review round 2, R2S8 / R2P3: nothing read it, so a merge that finished after
    // the page gave up ended in "Couldn't check the merge" with a Try again that could only
    // fail, and no window heard the merge). When it is the one merged by a merge FCC sent
    // and couldn't account for (`_unsure`, page-wide since review round 3, R3P4: on either
    // side of the question, after a ⇄, or in a question opened again), that merge finished:
    // the server deletes the one merged only once every filament is off it. It is told as
    // one that answered, so every window stops holding the deleted id. Otherwise it went
    // another way (another window's merge, Spoolman's own page), which the page can't name,
    // or it is the one to keep: the question says what the server said and offers nothing
    // to ask again.
    function _qSettleGone(q, why, gone) {
        const pair = _unsureGone(gone, q);
        if (!pair) {
            q.inFlight = false;
            if (_alive(q.win)) { _notice(q.win, why, 'warn'); _read(q.win); }
            if (!_qAlive(q)) return;
            _qFlash(q, '');
            _qPlanFailed(q, why, true);
            return;
        }
        _settleUnsure(q.win, q, pair, why);
    }

    // The merge of `pair` FCC sent and couldn't account for, found finished (its source
    // gone): told as one that answered, from a read of the manufacturers for the kept
    // one's record. `q`: the question that met it, or null (the window's own read).
    function _settleUnsure(win, q, pair, why) {
        const via = q || { win, src: pair.src, dst: pair.dst, plan: null, lastPlan: null, handle: null, closed: true };
        const srcName = _qName(via, pair.src);
        const dstName = _qName(via, pair.dst);
        const at = ++_seq;
        _readOut(pair.dst, 1);
        _readVendors().then((r) => {
            _readOut(pair.dst, -1);
            if (q) q.inFlight = false;
            const kept = r.read ? r.vendors.find((v) => v && String(v.id) === pair.dst) || null : null;
            if (r.read && !kept) {
                // The one kept is gone too: no window can be told to hold it.
                _forgetUnsure(pair.src);
                const both = `${why} ${dstName} isn't in Spoolman either.`;
                if (_alive(win)) { _notice(win, both, 'warn'); if (!q) _fail(win, both, true); else _read(win); }
                if (q && _qAlive(q)) { _qFlash(q, ''); _qPlanFailed(q, both, true); }
                return;
            }
            _merged(via, {
                vendor: kept,
                moved_filament_ids: [],
                msg: `${srcName} is gone from Spoolman: the merge into ${kept ? label(kept) : dstName} finished.`,
            }, pair, at);
        });
    }

    // A refusal, a partial merge or a merge FCC can't account for: said on the question's
    // line and on the window's (the toast sits under both), the windows told what changed,
    // and the question asked again from what is left. Its yes is armed again (_qPaint), so
    // a double click's second press posts nothing. `seen`: a read of the manufacturers
    // made since the answer (_qCheckLanded's), so it isn't read twice.
    function _qNotMerged(q, msg, data, seen) {
        const win = q.win;
        const words = msg + _labelTroubleWords(data);
        // A carry that landed changed the kept one; filaments may have moved. A refusal made
        // before any write (`nothing_written`) changed nothing, so it tells no window anything
        // (review round 3, R3P2: a read that failed then held the editor, "after a change").
        if (!(data && data.nothing_written === true)) _qTellKept(q, data, seen);
        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
        if (_alive(win)) { _notice(win, words, 'warn'); _read(win); }
        else if (window.showToast) window.showToast(words, 'error', 7000);
        if (!_qAlive(q)) return;
        _qFlash(q, words);
        _qPlan(q);        // what is left, in fresh words; the line keeps the refusal
        try { _qBtn(q, 'cancel').focus({ preventScroll: true }); } catch (_) { /* noop */ }
    }

    function _qYes(q, e) {
        if (!_qAlive(q) || q.inFlight || !q.plan) return;
        q.inFlight = true;
        _qSetButtons(q, false);
        const n = (q.plan.filaments || []).length;
        _qFlash(q, n ? `Merging…: moving ${nFilaments(n)}.` : 'Merging…');
        const pair = { src: q.src, dst: q.dst };
        const url = `/api/vendors/${encodeURIComponent(q.src)}/merge_into/${encodeURIComponent(q.dst)}`;
        // The merge asks for itself (review round 1, S5).
        window.fetchT(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ merge: true }),
        }, MERGE_TIMEOUT_MS)
            .then((res) => res.json().then((data) => ({ res, data }), () => ({ res, data: null })))
            .then(({ res, data }) => {
                if (data && data.success === true) { q.inFlight = false; _merged(q, data); return; }
                const msg = String((data && data.msg) || `FCC answered with an error (HTTP ${res.status}), so the merge may not have finished.`);
                // The server read the one merged inside the lock, so no merge of it was
                // running and it was there: any earlier one FCC couldn't account for has
                // ended without deleting it (review round 4, R4P1).
                if (data && data.source_kept) _forgetUnsure(pair.src);
                // ...and so does the kept one's, read after it inside the lock (review round 5,
                // R5P4: a ⇄'d press of it stayed, and a later gone of it read as that merge).
                if (data && data.target_kept) _forgetUnsure(pair.dst);
                if (data && data.gone != null) { _qSettleGone(q, msg, data.gone); return; }
                // An answer FCC couldn't read, or a delete it couldn't confirm: this pair's
                // merge may have run, or be running still (review round 2, R2S8).
                if (!data || data.may_have_deleted) {
                    _noteUnsure(pair.src, pair.dst);
                    _qCheckLanded(q, data).then((seen) => { q.inFlight = false; if (!seen.landed) _qNotMerged(q, msg, data, seen); });
                    return;
                }
                q.inFlight = false;
                _qNotMerged(q, msg, data);
            }, () => {
                _noteUnsure(pair.src, pair.dst);
                if (window.logClientEvent) {
                    window.logClientEvent(`⚠️ Manufacturer merge #${esc(q.src)} → #${esc(q.dst)}: FCC didn't answer, so it may not have finished.`, 'WARNING');
                }
                _qCheckLanded(q, null).then((seen) => {
                    q.inFlight = false;
                    if (!seen.landed) {
                        _qNotMerged(q, "FCC didn't answer, so the merge may not have finished. The question shows what is left: Merge carries on from there.", null, seen);
                    }
                });
            });
    }

    function _ask(h, src, dst, fromRow) {
        if (!_alive(h)) return;
        if (_question) _closeQuestion(_question, { keepFocus: true });
        const q = {
            win: h, src: String(src), dst: String(dst), from: fromRow || null,
            // The row it came from, by its pair, to find again in a list read since.
            rowKey: fromRow && fromRow.dataset ? `${fromRow.dataset.vmSrc}:${fromRow.dataset.vmDst}` : null,
            seq: 0, plan: null, lastPlan: null, inFlight: false,
            userSwapped: false, triedSwap: false, closed: false, release: null, onClosed: null, handle: null,
        };
        _question = q;
        q.handle = window.mountOverlay({
            id: 'fcc-vendor-merge-confirm',
            tier: 'confirm',
            host: editorEl(),
            content: _questionHtml(),
            initialFocus: '[data-vmq="cancel"]',
            onEscape: () => _qCancel(q),
        });
        const el = q.handle.element;
        el.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-vmq]');
            if (!btn || btn.disabled) return;
            const which = btn.dataset.vmq;
            if (which === 'cancel') _qCancel(q, e);
            else if (which === 'swap') {
                // A double click's second press swaps nothing back (review round 1, P-S1: the
                // plan repaints in ~50 ms, ⇄ enabled where it was, and the second press undid
                // the person's choice). The click count, and the shield for a second press
                // the browser doesn't count.
                if (e.detail > 1) return;
                if (e.detail > 0) shield();
                _qSwap(q);
            } else if (which === 'retry') _qPlan(q);
            // 'yes' is its armed onclick (_qPaint).
        });
        q.onClosed = (e) => {
            if (e && e.detail && e.detail.element === el && !q.closed) {
                // Closed another way (its host went): nothing more to say on it.
                q.closed = true;
                if (q.release) { q.release(); q.release = null; }
                document.removeEventListener('fcc:overlay-closed', q.onClosed);
                if (_question === q) _question = null;
            }
        };
        document.addEventListener('fcc:overlay-closed', q.onClosed);
        if (window.fccHoldScans) {
            q.release = window.fccHoldScans({
                title: 'Merge manufacturers',
                element: el,
                hint: 'Answer the merge question on screen first: Cancel, or Merge',
                cancel: () => _qCancel(q, null, true),
                flash: (m) => _qFlash(q, m),
                // While the merge is on its way, a scan is refused in those words, not with
                // the hint that names Cancel and Merge (both disabled then; P-S8), and the
                // Activity Log says so (review round 2, R2P6: the line went with the
                // question once the merge landed, and nothing else said the scan did nothing).
                route: (text) => {
                    if (!q.inFlight) return false;
                    _qFlash(q, `The merge is on its way: wait for its answer. (Ignored: ${text})`);
                    if (window.logClientEvent) {
                        window.logClientEvent(`⚠️ Scan "${esc(String(text).trim())}" ignored: the manufacturer merge is on its way`, 'WARNING');
                    }
                    return 'refused';
                },
            });
        }
        _qPlan(q);
    }

    // ---------------------------------------------------------------- the window

    window.isVendorMergeOpen = () => !!_current;
    window.closeVendorMerge = () => { if (_current) _close(_current); };
    // processScan, for a scan the window doesn't take (review round 2, R2P7, the audit
    // report's rule: a shelf label filed the scan buffer's spools behind it, its toast and
    // Activity Log line under it, and the window said nothing). The window goes and the scan
    // goes on, its answer on top. Never while its question is up: that holds every scan.
    window.closeVendorMergeForScan = () => { if (_current && !_question) _close(_current); };

    window.openVendorMerge = function (opts) {
        if (typeof window.mountOverlay !== 'function') return null;
        const o = opts || {};
        const vid = o.vid == null ? '' : String(o.vid).trim();
        if (!vid) return null;
        _ensureStyle();
        _ensureScanCapture();
        if (_current) _close(_current, { keepFocus: true });
        const active = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
        const opener = (o.opener && o.opener.nodeType === 1) ? o.opener : active;
        const openedAt = Date.now();
        let h = null;
        h = window.mountOverlay({
            id: 'fcc-vendor-merge',
            tier: 'standard',
            host: editorEl(),
            content: _windowHtml(),
            // Not the second click of a double click on the button that opened it.
            onBackdropClick: () => { if (Date.now() - openedAt >= 400) { shield(); _close(h); } },
            onEscape: () => _close(h),
        });
        _current = h;
        h._vid = vid;
        h._opener = opener;
        h._seq = 0;
        h._data = null;
        h._closed = false;
        h._lastPress = null;
        const box = _box(h);
        box.addEventListener('input', () => { if (h._data) _paint(h); });
        h.panel.addEventListener('click', (e) => {
            if (e.target.closest('[data-vm-close]')) { shield(); _close(h); return; }
            if (e.target.closest('[data-vm-retry]')) { _notePress(h, e); _read(h); return; }
            const row = e.target.closest('button.fcc-vm-row');
            if (!row) return;
            if (_secondPress(h, e)) { _focusBox(h); return; }
            // The ring follows a pointer's pick too (P-S4).
            _highlight(h, _rows(h).indexOf(row), false);
            shield();
            _ask(h, row.dataset.vmSrc, row.dataset.vmDst, row);
        });
        h._keys = (e) => _onKey(h, e);
        document.addEventListener('keydown', h._keys, true);
        // A Bootstrap window opening would sit under this one (the audit Find's rule).
        h._shows = (e) => { if (!e || e.target !== editorEl()) _close(h, { keepFocus: true }); };
        document.addEventListener('show.bs.modal', h._shows);
        document.addEventListener('show.bs.offcanvas', h._shows);
        // Closed another way (its host went): forget it.
        h._closedListener = (e) => {
            if (e && e.detail && e.detail.element === h.element && !h._closed) {
                h._closed = true;
                _unlisten(h);
                if (_question && _question.win === h) _closeQuestion(_question, { keepFocus: true });
                if (_current === h) _current = null;
            }
        };
        document.addEventListener('fcc:overlay-closed', h._closedListener);
        try { box.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        _read(h);
        return h;
    };

    if (typeof window.registerShortcut === 'function') {
        window.registerShortcut({
            id: 'vendor-merge-arrows', scope: 'Merge Manufacturers', keys: ['↑', '↓'],
            description: 'From the box to the rows, and between them across both lists. Wraps at the ends.'
        });
        window.registerShortcut({
            id: 'vendor-merge-enter', scope: 'Merge Manufacturers', keys: ['Enter'],
            description: 'On a row: open its merge question, which opens on Cancel. In the box: nothing.'
        });
        window.registerShortcut({
            id: 'vendor-merge-slash', scope: 'Merge Manufacturers', keys: ['/'],
            description: 'Back to the box.'
        });
        window.registerShortcut({
            id: 'vendor-merge-escape', scope: 'Merge Manufacturers', keys: ['Esc'],
            description: 'Close the question, or the window: nothing is merged.'
        });
    }
})();
