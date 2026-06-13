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
        // Returns true on success, false if storage is unavailable (private
        // mode / quota / disabled) so save() can be honest about what persisted.
        try { window.localStorage.setItem(key, String(val)); return true; }
        catch (e) { return false; }
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
        let clientAttempted = false, clientFailed = false;
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
                if (String(val) !== el.dataset.initial) {
                    clientAttempted = true;
                    if (!writeClient(key, val)) clientFailed = true;
                }
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
                const serverSaved = Array.isArray(d.saved) ? d.saved.length : 0;
                if (clientFailed) {
                    // server part (if any) succeeded, but the browser refused to
                    // store a client pref — don't claim a clean save.
                    const m = 'Saved, but a browser preference could not be stored (private mode / storage full).';
                    if (statusEl) { statusEl.style.color = '#ffcc66'; statusEl.textContent = m; }
                    if (window.showToast) window.showToast(m, 'warning', 7000);
                } else if (serverSaved === 0 && !clientAttempted) {
                    // genuine no-op (e.g. only the secret sentinel, or nothing changed)
                    if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'No changes'; }
                    if (window.showToast) window.showToast('No changes to save', 'info', 3000);
                } else {
                    if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                    if (window.showToast) window.showToast('Settings saved', 'success', 4000);
                }
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

    function pmRender(entries, creds) {
        creds = creds || {};
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

        // FilaBridge Phase-2: per-printer PrusaLink connection (ip + api_key),
        // relocated off FilaBridge onto the Printer rows. One row per distinct
        // printer name. The api_key is masked — blank keeps the saved one.
        const pcNames = [];
        (entries || []).forEach((e) => {
            const n = e.printer_name || '';
            if (n && pcNames.indexOf(n) === -1) pcNames.push(n);
        });
        Object.keys(creds).forEach((n) => { if (n && pcNames.indexOf(n) === -1) pcNames.push(n); });
        if (pcNames.length) {
            html += `<hr class="my-3" style="border-color:rgba(255,255,255,0.15);">`;
            html += `<div class="small mb-2" style="color:rgba(255,255,255,0.55);">
                🔌 <b>Printer Connections</b> — the PrusaLink IP + API key FCC uses to read each printer's
                state and parse finished / cancelled prints (relocated off FilaBridge). Leave the key blank to keep the saved one; clear the IP to remove a connection.
            </div>`;
            // CSS grid so every row shares the SAME columns regardless of name
            // length (the long "Core One Upgraded" no longer shoves the inputs
            // out of alignment). Each .pc-row is display:contents so its cells
            // become items of this grid. Header row labels the columns.
            const pcGrid = 'display:grid;grid-template-columns:minmax(110px,160px) minmax(0,1fr) minmax(0,1fr) auto;column-gap:8px;row-gap:6px;align-items:center;';
            html += `<div id="pc-rows" style="${pcGrid}">`
                + `<span class="small text-secondary">Printer</span>`
                + `<span class="small text-secondary">PrusaLink IP</span>`
                + `<span class="small text-secondary">API key</span>`
                + `<span></span>`
                + pcNames.map((n) => pcRowHtml(n, creds[n] || {})).join('')
                + `</div>`;
        }

        host.innerHTML = html;
        host.querySelectorAll('.pm-row').forEach(pmWireRow);
        host.querySelectorAll('.pc-row').forEach(pcWireRow);
        const addBtn = host.querySelector('#pm-add');
        if (addBtn) addBtn.addEventListener('click', () => {
            const rows = host.querySelector('#pm-rows');
            rows.insertAdjacentHTML('beforeend', pmRowHtml({ location_id: '', printer_name: '', position: 0 }, true));
            pmWireRow(rows.lastElementChild);
        });
        const saveBtn = host.querySelector('#pm-save');
        if (saveBtn) saveBtn.addEventListener('click', pmSave);
    }

    // ---- FilaBridge Phase-2: per-printer PrusaLink connection editor ----
    function pcRowHtml(name, c) {
        const nm = _esc(name);
        const ip = _esc(c.ip_address || '');
        const isSet = String(c.api_key || '') === SECRET_SENTINEL;
        return `<div class="d-flex align-items-center gap-2 py-1 pc-row" data-printer="${nm}">
            <span class="small text-white text-truncate" style="min-width:140px;max-width:160px;" title="${nm}">${nm}</span>
            <input class="form-control form-control-sm pc-ip bg-dark text-white border-secondary" type="text" value="${ip}" placeholder="PrusaLink IP (e.g. 192.168.1.50)" autocomplete="off" style="max-width:190px;">
            <input class="form-control form-control-sm pc-key bg-dark text-white border-secondary" type="password" value="" placeholder="${isSet ? '•••••• saved — blank keeps it' : 'API key'}" autocomplete="new-password" style="max-width:180px;">
            ${isSet ? '<span class="badge bg-success" title="An API key is saved">✓ key</span>' : ''}
            <button type="button" class="btn btn-sm btn-info pc-save" title="Save this printer's connection">Save</button>
            <span class="small pc-status" style="color:rgba(255,255,255,0.6);"></span>
        </div>`;
    }

    function pcWireRow(row) {
        const btn = row.querySelector('.pc-save');
        if (btn) btn.addEventListener('click', () => pcSave(row));
    }

    async function pcSave(row) {
        const name = row.getAttribute('data-printer') || '';
        const ip = (row.querySelector('.pc-ip').value || '').trim();
        const keyRaw = row.querySelector('.pc-key').value;
        // Mirror the Config secret contract: an empty key field means "keep the
        // saved key" (send the sentinel); a typed value replaces it.
        const api_key = (keyRaw === '' ? SECRET_SENTINEL : keyRaw);
        const statusEl = row.querySelector('.pc-status');
        const btn = row.querySelector('.pc-save');
        if (btn) btn.disabled = true;
        if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'Saving…'; }
        try {
            const r = await fetch('/api/printer_creds', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ printer_name: name, ip_address: ip, api_key }),
            });
            const d = await r.json();
            if (r.ok && d.ok) {
                if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                if (window.showToast) window.showToast(`Connection saved for ${name}`, 'success', 4000);
                window.renderPrinterMap();  // reload canonical (re-masks the key)
            } else {
                const msg = (d && d.error) ? d.error : 'Save failed';
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
                if (window.showToast) window.showToast(msg, 'error', 8000);
            }
        } catch (e) {
            const msg = 'Save error: ' + (e && e.message ? e.message : e);
            if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
            if (window.showToast) window.showToast(msg, 'error', 7000);
        } finally {
            if (btn) btn.disabled = false;
        }
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
            pmRender(d.entries || [], d.printer_creds || {});
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Failed to load toolheads: ${_esc(e && e.message ? e.message : e)}</div>`;
        }
    };

    // ---- L18 Phase 4: config import / export ----
    function showImportConfirm(parsed, dry) {
        const diff = dry.diff || [];
        const ignored = dry.ignored || [];
        const rows = diff.length
            ? diff.map((x) => `<div class="d-flex justify-content-between gap-3 py-1" style="border-bottom:1px solid #2a2a2a;">
                    <span class="text-light small">${_esc(x.label || x.key)}</span>
                    <span class="small"><span style="color:#ff8a8a;">${_esc(x.from)}</span> &rarr; <span style="color:#7CFC00;">${_esc(x.to)}</span></span>
                 </div>`).join('')
            : `<div class="small" style="color:rgba(255,255,255,0.6);">No setting changes — incoming values match the current config.</div>`;
        const ignoredHtml = ignored.length
            ? `<div class="small mt-2" style="color:rgba(255,255,255,0.5);">Ignored ${ignored.length} non-setting key(s) (printer_map / paths / etc. keep their own editors): ${_esc(ignored.join(', '))}</div>`
            : '';
        const body = `
            <div style="background:#1a1a1a; border:1px solid #333; border-radius:8px; max-width:560px; width:92vw; max-height:80vh; display:flex; flex-direction:column;">
                <div class="px-3 py-2 fw-bold text-info" style="background:#1f1f1f;">⬆ Import settings — review changes</div>
                <div class="px-3 py-2" style="flex:1 1 auto; overflow-y:auto;">${rows}${ignoredHtml}</div>
                <div class="d-flex justify-content-end gap-2 px-3 py-2" style="background:#1a1a1a; border-top:1px solid #333;">
                    <button type="button" class="btn btn-sm btn-secondary" id="cfgio-cancel">Cancel</button>
                    <button type="button" class="btn btn-sm btn-info fw-bold" id="cfgio-apply" ${diff.length ? '' : 'disabled'}>Apply ${diff.length} change(s)</button>
                </div>
            </div>`;
        const handle = window.mountOverlay({
            id: 'fcc-config-import-overlay',
            content: body,
            tier: 'confirm',
            host: document.getElementById('configModal'),
            initialFocus: '#cfgio-apply',
        });
        const root = handle.panel;
        root.querySelector('#cfgio-cancel').addEventListener('click', () => handle.cleanup());
        const applyBtn = root.querySelector('#cfgio-apply');
        if (applyBtn) applyBtn.addEventListener('click', async () => {
            applyBtn.disabled = true;
            applyBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Applying…';
            try {
                const r = await fetch('/api/config/import', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: parsed }),
                });
                const res = await r.json();
                handle.cleanup();
                if (r.ok && res.ok) {
                    if (window.showToast) window.showToast(`Imported ${(res.saved || []).length} setting(s)`, 'success', 4000);
                    if (window.renderConfigSettings) window.renderConfigSettings();  // refresh the cards
                } else if (window.showToast) {
                    window.showToast(res.error || 'Import failed', 'error', 8000);
                }
            } catch (e) {
                handle.cleanup();
                if (window.showToast) window.showToast('Import failed: ' + (e && e.message ? e.message : e), 'error', 7000);
            }
        });
    }

    window.wireImportExport = function () {
        const btn = document.getElementById('cfgio-import-btn');
        const fileInput = document.getElementById('cfgio-file');
        if (!btn || !fileInput || btn.dataset.wired) return;  // wire once
        btn.dataset.wired = '1';
        btn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async () => {
            const file = fileInput.files && fileInput.files[0];
            fileInput.value = '';  // allow re-selecting the same file
            if (!file) return;
            let parsed;
            try {
                parsed = JSON.parse(await file.text());
            } catch (e) {
                if (window.showToast) window.showToast('Not valid JSON: ' + (e && e.message ? e.message : e), 'error', 7000);
                return;
            }
            try {
                const r = await fetch('/api/config/import', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: parsed, dry_run: true }),
                });
                const d = await r.json();
                if (!d.ok) {
                    if (window.showToast) window.showToast(d.error || 'Import rejected', 'error', 8000);
                    return;
                }
                showImportConfirm(parsed, d);
            } catch (e) {
                if (window.showToast) window.showToast('Import preview failed: ' + (e && e.message ? e.message : e), 'error', 7000);
            }
        });
    };
})();
