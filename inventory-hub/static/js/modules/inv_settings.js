/* MODULE: CONFIG SETTINGS RENDERER — L18 Phase 1
 *
 * Renders the declarative config schema (GET /api/config) into the
 * #config-generated-settings host inside the Config (gear) modal. Adding a
 * new setting is a one-line Field edit in config_schema.py — this renderer
 * paints whatever the schema returns, by type.
 *
 *  - scope:"server" fields persist via PUT /api/config (validated server-side;
 *    errors surfaced as a 7s toast).
 *  - scope:"client" fields persist to localStorage under their own key and are
 *    read by their owning module unchanged (e.g. weight_entry.js reads
 *    'fcc.weighEntry.defaultMode').
 *
 * The action-tool cards (reconcile / attributes / restore field order / build
 * info) are untouched — this card simply slots in alongside them.
 */
(function () {
    const HOST_ID = 'config-generated-settings';
    const _esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const _domId = (key) => 'cfgset-' + String(key).replace(/[^a-zA-Z0-9_-]/g, '_');
    // Mirrors config_schema.SECRET_SENTINEL. GET returns this (not the plaintext)
    // for a set secret; sending it back on save means "leave unchanged".
    const SECRET_SENTINEL = '__secret_set__';

    function readClient(key, fallback) {
        try {
            const v = window.localStorage.getItem(key);
            return v == null ? fallback : v;
        } catch (e) { return fallback; }
    }
    function writeClient(key, val) {
        try { window.localStorage.setItem(key, String(val)); } catch (e) { /* private mode */ }
    }

    function inputFor(f, value) {
        const id = _domId(f.key);
        // Only id + data-* live in `data`; the class list is passed per-branch
        // so both the marker class (cfgset-input) and the dark-theme classes are
        // always present (no fragile string-replace). data-initial lets save()
        // tell whether a CLIENT pref actually changed.
        const data = `id="${id}" data-key="${_esc(f.key)}" data-type="${_esc(f.type)}" `
            + `data-scope="${_esc(f.scope)}" data-initial="${_esc(value)}" autocomplete="off"`;
        if (f.type === 'bool') {
            const checked = (value === true || value === 'true') ? 'checked' : '';
            return `<div class="form-check form-switch mb-0">
                <input class="form-check-input cfgset-input" type="checkbox" ${data} ${checked}>
            </div>`;
        }
        if (f.type === 'select') {
            const opts = (f.choices || []).map((c) =>
                `<option value="${_esc(c)}" ${String(value) === String(c) ? 'selected' : ''}>${_esc(c)}</option>`).join('');
            return `<select class="form-select form-select-sm cfgset-input bg-dark text-white border-secondary" ${data} style="max-width:240px;">${opts}</select>`;
        }
        if (f.type === 'secret') {
            // Rendered EMPTY (the plaintext never reaches the browser). The
            // placeholder reflects whether one is currently set; blank-on-save
            // keeps it. data-initial carries the sentinel, not the real key.
            // type="text" + -webkit-text-security (NOT type=password) so Chrome's
            // password manager never engages: no "save password?" prompt and no
            // username-pairing autofill into the adjacent ip fields. The eye flips
            // the CSS mask, not the input type. (Chromium/Edge/Safari mask; Firefox
            // would show plaintext — acceptable for this Chromium app.)
            const isSet = String(value) === SECRET_SENTINEL;
            return `<div class="d-flex align-items-center gap-1">
                <input class="form-control form-control-sm cfgset-input bg-dark text-white border-secondary"
                       type="text" ${data} value="" autocapitalize="off" autocorrect="off" spellcheck="false"
                       style="max-width:200px; -webkit-text-security:disc;"
                       placeholder="${isSet ? '•••••••• (set — blank keeps it)' : '(not set)'}">
                <button type="button" class="btn btn-sm btn-outline-secondary cfgset-eye" tabindex="-1" title="Show / hide">👁</button>
            </div>`;
        }
        // int / float / port -> number; ip / string -> text
        let typeAttrs = 'type="text"';
        if (f.type === 'int' || f.type === 'float' || f.type === 'port') {
            typeAttrs = `type="number" step="${f.type === 'float' ? 'any' : '1'}"`
                + (f.min != null ? ` min="${_esc(f.min)}"` : '')
                + (f.max != null ? ` max="${_esc(f.max)}"` : '');
        }
        return `<input class="form-control form-control-sm cfgset-input bg-dark text-white border-secondary" ${data} ${typeAttrs} value="${_esc(value)}" style="max-width:240px;">`;
    }

    function render(schema, values) {
        const host = document.getElementById(HOST_ID);
        if (!host || !schema) return;
        const bySection = {};
        (schema.fields || []).forEach((f) => {
            (bySection[f.section] = bySection[f.section] || []).push(f);
        });
        let html = '';
        (schema.sections || []).forEach((sec) => {
            const fields = bySection[sec.key] || [];
            if (!fields.length) return;
            html += `<div class="mb-3">
                <div class="fw-bold text-info mb-1">${_esc(sec.label)}</div>`;
            if (sec.help) {
                html += `<div class="small mb-2" style="color:rgba(255,255,255,0.55);">${_esc(sec.help)}</div>`;
            }
            fields.forEach((f) => {
                const value = (f.scope === 'client') ? readClient(f.key, values[f.key]) : values[f.key];
                html += `<div class="d-flex justify-content-between align-items-center py-1 gap-3">
                    <label class="text-light small mb-0" for="${_domId(f.key)}" style="flex:1;">
                        ${_esc(f.label)}
                        ${f.help ? `<div class="small" style="color:rgba(255,255,255,0.45);">${_esc(f.help)}</div>` : ''}
                    </label>
                    <div>${inputFor(f, value)}</div>
                </div>`;
            });
            html += `</div>`;
        });
        html += `<div class="d-flex align-items-center gap-2 mt-2">
            <button class="btn btn-sm btn-info fw-bold" id="cfgset-save" type="button">Save settings</button>
            <span class="small" id="cfgset-status" style="color:rgba(255,255,255,0.6);"></span>
        </div>`;
        host.innerHTML = html;
        const saveBtn = document.getElementById('cfgset-save');
        if (saveBtn) saveBtn.addEventListener('click', save);
        host.querySelectorAll('.cfgset-eye').forEach((btn) => {
            btn.addEventListener('click', () => {
                const inp = btn.parentElement.querySelector('.cfgset-input');
                if (!inp) return;
                // Toggle the CSS mask (the input stays type=text to dodge Chrome's
                // password manager) — disc = hidden, none = revealed.
                const masked = inp.style.webkitTextSecurity !== 'none';
                inp.style.webkitTextSecurity = masked ? 'none' : 'disc';
            });
        });
    }

    async function save() {
        const host = document.getElementById(HOST_ID);
        if (!host) return;
        const statusEl = document.getElementById('cfgset-status');
        const btn = document.getElementById('cfgset-save');
        const serverValues = {};
        let reservedHit = false;
        host.querySelectorAll('.cfgset-input').forEach((el) => {
            const key = el.dataset.key;
            const type = el.dataset.type;
            const scope = el.dataset.scope;
            if (type === 'secret') {
                // Blank = keep the existing secret (send the sentinel); anything
                // typed = the new value. Guard the (implausible) case where the
                // user literally types the internal sentinel string.
                if (el.value !== '' && el.value === SECRET_SENTINEL) { reservedHit = true; return; }
                serverValues[key] = (el.value === '' ? SECRET_SENTINEL : el.value);
                return;
            }
            const val = (type === 'bool') ? el.checked : el.value;
            if (scope === 'client') {
                // Only persist a client pref the user actually CHANGED. Writing
                // the displayed default unconditionally would pin it into
                // localStorage and override any caller that passes a different
                // defaultMode (weight_entry.js treats "unset" as "caller wins").
                if (String(val) !== el.dataset.initial) writeClient(key, val);
            } else {
                serverValues[key] = val;
            }
        });
        if (reservedHit) {
            if (window.showToast) window.showToast('That value is reserved — choose a different key.', 'error', 7000);
            if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = 'Reserved value — not saved.'; }
            return;
        }
        if (btn) btn.disabled = true;
        if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'Saving…'; }
        try {
            const r = await fetch('/api/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ values: serverValues }),
            });
            const d = await r.json();
            if (d && d.ok) {
                if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                if (window.showToast) window.showToast('Settings saved', 'success', 4000);
            } else {
                const msg = (d && d.error) ? d.error : 'Settings save failed';
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
                if (window.showToast) window.showToast(msg, 'error', 7000);
            }
        } catch (e) {
            const msg = 'Settings save error: ' + (e && e.message ? e.message : e);
            if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
            if (window.showToast) window.showToast(msg, 'error', 7000);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    window.renderConfigSettings = async function () {
        const host = document.getElementById(HOST_ID);
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Loading settings…</div>`;
        try {
            const r = await fetch('/api/config');
            const d = await r.json();
            render(d.schema, d.values || {});
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Failed to load settings: ${_esc(e && e.message ? e.message : e)}</div>`;
        }
    };

    // ---- L18 Phase 3: printer_map (toolhead) editor ----
    const PM_HOST_ID = 'config-printer-map';

    function pmRowHtml(entry, isNew) {
        const loc = _esc(entry.location_id || '');
        const name = _esc(entry.printer_name || '');
        const pos = entry.position == null ? 0 : entry.position;
        // Existing LocationIDs are read-only (renaming = remove+add, which the
        // backend guards); new rows get an editable LocationID.
        const locInput = isNew
            ? `<input class="form-control form-control-sm pm-loc bg-dark text-white border-secondary" type="text" value="${loc}" placeholder="LocationID (e.g. CORE1-M6)" autocomplete="off" style="max-width:170px;">`
            : `<input class="form-control form-control-sm pm-loc bg-dark text-white border-secondary" type="text" value="${loc}" readonly title="LocationID is fixed for existing toolheads — add or remove instead" style="max-width:170px; opacity:.7;">`;
        return `<div class="d-flex align-items-center gap-2 py-1 pm-row">
            ${locInput}
            <input class="form-control form-control-sm pm-name bg-dark text-white border-secondary" type="text" value="${name}" placeholder="Printer name" autocomplete="off" style="max-width:180px;">
            <input class="form-control form-control-sm pm-pos bg-dark text-white border-secondary" type="number" min="0" step="1" value="${_esc(pos)}" title="Position" style="max-width:90px;">
            <button type="button" class="btn btn-sm btn-outline-danger pm-remove" title="Remove toolhead">🗑</button>
        </div>`;
    }

    function pmWireRow(row) {
        const rm = row.querySelector('.pm-remove');
        if (rm) rm.addEventListener('click', () => row.remove());
    }

    function pmRender(entries) {
        const host = document.getElementById(PM_HOST_ID);
        if (!host) return;
        let html = `<div class="small mb-2" style="color:rgba(255,255,255,0.55);">
            Toolheads keyed by LocationID. Add new ones (e.g. an MMU / indxx upgrade) or edit a name / position.
            Existing LocationIDs can't be renamed; removing one a dryer-box slot or spool still uses is blocked.
        </div>`;
        html += `<div id="pm-rows">` + (entries || []).map((e) => pmRowHtml(e, false)).join('') + `</div>`;
        html += `<div class="d-flex align-items-center gap-2 mt-2">
            <button type="button" class="btn btn-sm btn-outline-info" id="pm-add">+ Add toolhead</button>
            <button type="button" class="btn btn-sm btn-info fw-bold" id="pm-save">Save toolheads</button>
            <span class="small" id="pm-status" style="color:rgba(255,255,255,0.6);"></span>
        </div>`;
        host.innerHTML = html;
        host.querySelectorAll('.pm-row').forEach(pmWireRow);
        const addBtn = host.querySelector('#pm-add');
        if (addBtn) addBtn.addEventListener('click', () => {
            const rows = host.querySelector('#pm-rows');
            rows.insertAdjacentHTML('beforeend', pmRowHtml({ location_id: '', printer_name: '', position: 0 }, true));
            pmWireRow(rows.lastElementChild);
        });
        const saveBtn = host.querySelector('#pm-save');
        if (saveBtn) saveBtn.addEventListener('click', pmSave);
    }

    async function pmSave() {
        const host = document.getElementById(PM_HOST_ID);
        if (!host) return;
        const statusEl = host.querySelector('#pm-status');
        const btn = host.querySelector('#pm-save');
        const map = {};
        let dupe = null;
        let incomplete = false;
        for (const row of host.querySelectorAll('.pm-row')) {
            const loc = (row.querySelector('.pm-loc').value || '').trim();
            const name = (row.querySelector('.pm-name').value || '').trim();
            const posRaw = row.querySelector('.pm-pos').value;
            if (!loc) {
                // A fully-blank row is fine to skip; a row with a name/position
                // but no LocationID is a mistake — don't silently drop it.
                if (name || (posRaw !== '' && posRaw != null)) incomplete = true;
                continue;
            }
            const key = loc.toUpperCase();
            if (map[key]) { dupe = key; break; }
            map[key] = {
                printer_name: name,
                position: Math.max(0, Math.trunc(Number(posRaw)) || 0),
            };
        }
        if (incomplete) {
            if (window.showToast) window.showToast('A toolhead row is missing its LocationID — fill it in or clear the row.', 'error', 7000);
            return;
        }
        if (dupe) {
            if (window.showToast) window.showToast(`Duplicate LocationID: ${dupe}`, 'error', 7000);
            return;
        }
        if (btn) btn.disabled = true;
        if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'Saving…'; }
        try {
            const r = await fetch('/api/printer_map', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ printer_map: map }),
            });
            const d = await r.json();
            if (r.ok && d.ok) {
                if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                if (window.showToast) window.showToast('Toolheads saved', 'success', 4000);
                window.renderPrinterMap();  // reload canonical from server
            } else {
                const msg = (d && d.error) ? d.error : 'Save failed';
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
                if (window.showToast) window.showToast(msg, 'error', 8000);  // long: block messages matter
            }
        } catch (e) {
            const msg = 'Save error: ' + (e && e.message ? e.message : e);
            if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
            if (window.showToast) window.showToast(msg, 'error', 7000);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    window.renderPrinterMap = async function () {
        const host = document.getElementById(PM_HOST_ID);
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Loading toolheads…</div>`;
        try {
            const r = await fetch('/api/printer_map');
            const d = await r.json();
            pmRender(d.entries || []);
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Failed to load toolheads: ${_esc(e && e.message ? e.message : e)}</div>`;
        }
    };
})();
