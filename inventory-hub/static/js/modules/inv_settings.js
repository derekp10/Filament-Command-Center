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
 * The action-tool cards (attributes / restore field order / build info) are
 * untouched — this card simply slots in alongside them.
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

    // A printer's toolheads share its LocationID prefix (RCOI-1…RCOI-8 → printer
    // RCOI) — the same grouping PUT /api/printer_map uses.
    function pmPrefixOf(row) {
        const el = row && row.querySelector('.pm-loc');
        const v = ((el && el.value) || '').trim().toUpperCase();
        return v.indexOf('-') >= 0 ? v.split('-')[0] : v;
    }

    // Hotfix 2026-09-29 — the printer name belongs to the PRINTER, but the editor
    // shows it on every toolhead row and the save keeps the first row's value, so
    // renaming meant editing all eight INDX rows alike. Typing a name now mirrors
    // it to that printer's other rows; a new row typed under an existing prefix
    // takes that printer's name and its tool position.
    function pmOnInput(ev) {
        const t = ev.target;
        const host = document.getElementById(PM_HOST_ID);
        const row = t && t.closest ? t.closest('.pm-row') : null;
        if (!host || !row) return;
        const pfx = pmPrefixOf(row);
        const siblings = pfx ? Array.from(host.querySelectorAll('.pm-row'))
            .filter((o) => o !== row && pmPrefixOf(o) === pfx) : [];
        if (t.classList.contains('pm-name')) {
            siblings.forEach((o) => {
                const inp = o.querySelector('.pm-name');
                if (inp && inp.value !== t.value) inp.value = t.value;
            });
        } else if (t.classList.contains('pm-loc')) {
            // Fill only once the prefix is complete (a '-' typed): "XL" on the way
            // to "XL2-1" must not claim the XL's name and position. What gets
            // filled is remembered, so a changed prefix takes it back and a
            // later digit re-derives the position.
            const nameEl = row.querySelector('.pm-name');
            const posEl = row.querySelector('.pm-pos');
            const raw = (t.value || '').trim().toUpperCase();
            const complete = raw.indexOf('-') >= 0;
            const d = row.dataset;
            if (d.autoPfx && (!complete || d.autoPfx !== pfx)) {
                if (nameEl && nameEl.value === d.autoName) nameEl.value = '';
                if (posEl && posEl.value === d.autoPos) posEl.value = '0';
                delete d.autoPfx; delete d.autoName; delete d.autoPos;
            }
            if (!complete || !siblings.length) return;
            const donor = siblings.find((o) => (o.querySelector('.pm-name').value || '').trim());
            if (nameEl && donor && (!nameEl.value.trim() || nameEl.value === d.autoName)) {
                nameEl.value = donor.querySelector('.pm-name').value;
                d.autoName = nameEl.value;
            }
            // Position = the slicer tool index the deduct bills by: RCOI-9 → 8
            // when the id carries a tool number, else the next free one.
            if (posEl && (posEl.value === '' || posEl.value === '0' || posEl.value === d.autoPos)) {
                const suffix = raw.slice(pfx.length + 1);
                const used = siblings.map((o) => Math.trunc(Number(o.querySelector('.pm-pos').value)) || 0);
                posEl.value = /^[1-9][0-9]*$/.test(suffix)
                    ? String(Number(suffix) - 1)
                    : String(Math.max.apply(null, used) + 1);
                d.autoPos = posEl.value;
            }
            d.autoPfx = pfx;
        }
    }

    function pmRender(entries, creds, printerRows) {
        creds = creds || {};
        const host = document.getElementById(PM_HOST_ID);
        if (!host) return;
        let html = `<div class="small mb-2" style="color:rgba(255,255,255,0.55);">
            Toolheads keyed by LocationID. Add new ones (e.g. an MMU / indxx upgrade) or edit a name / position.
            A printer's toolheads share its ID prefix (RCOI-1 … RCOI-8 belong to printer RCOI); each toolhead gets its
            Location Manager row automatically, and renaming the printer on one row renames it on all of them.
            Existing LocationIDs can't be renamed; removing one a dryer-box slot or spool still uses is blocked.
        </div>`;
        html += `<div id="pm-rows">` + (entries || []).map((e) => pmRowHtml(e, false)).join('') + `</div>`;
        html += `<div class="d-flex align-items-center gap-2 mt-2">
            <button type="button" class="btn btn-sm btn-outline-info" id="pm-add">+ Add toolhead</button>
            <button type="button" class="btn btn-sm btn-info fw-bold" id="pm-save" title="Saves the toolheads and any printer connection edited below">Save toolheads</button>
            <span class="small" id="pm-status" style="color:rgba(255,255,255,0.6);"></span>
        </div>`;
        html += `<div id="pc-section">${pcSectionHtml(pcRowsFrom(printerRows, entries, creds))}</div>`;

        host.innerHTML = html;
        host.querySelectorAll('.pm-row').forEach(pmWireRow);
        host.querySelectorAll('.pc-row').forEach(pcWireRow);
        pcRenderMissing(host);
        if (!host._fccPmInputBound) {
            host.addEventListener('input', pmOnInput);
            host._fccPmInputBound = true;
        }
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
    // Hotfix 2026-09-29: one row per Printer ROW, addressed by its LocationID.
    // The grid used to be keyed by display Name, so a rename or two rows sharing
    // a Name showed one row's connection while the save wrote another's.
    function pcRowsFrom(printerRows, entries, creds) {
        const isSet = (k) => String(k || '') === SECRET_SENTINEL;
        if (Array.isArray(printerRows)) {
            return printerRows.map((p) => ({ id: p.location_id || '', name: p.name || '',
                ip: p.ip_address || '', keySet: isSet(p.api_key) }));
        }
        // Older server (no printer_rows): one row per printer name, as before.
        const names = [];
        (entries || []).forEach((e) => {
            const n = e.printer_name || '';
            if (n && names.indexOf(n) === -1) names.push(n);
        });
        Object.keys(creds || {}).forEach((n) => { if (n && names.indexOf(n) === -1) names.push(n); });
        return names.map((n) => {
            const c = (creds || {})[n] || {};
            return { id: '', name: n, ip: c.ip_address || '', keySet: isSet(c.api_key) };
        });
    }

    function pcSectionHtml(rows) {
        if (!rows.length) return '';
        // CSS grid so every row shares the SAME columns regardless of name
        // length (the long "Core One Upgraded" no longer shoves the inputs
        // out of alignment). Each .pc-row is display:contents so its cells
        // become items of this grid. Header row labels the columns.
        const pcGrid = 'display:grid;grid-template-columns:minmax(110px,160px) minmax(0,1fr) minmax(0,1fr) auto;column-gap:8px;row-gap:6px;align-items:center;';
        return `<hr class="my-3" style="border-color:rgba(255,255,255,0.15);">`
            + `<div class="small mb-2" style="color:rgba(255,255,255,0.55);">
                🔌 <b>Printer Connections</b> — the PrusaLink IP + API key FCC uses to read each printer's
                state and parse finished / cancelled prints (relocated off FilaBridge). Leave the key blank to keep the saved one; clear the IP to remove a connection.
                <b>Save toolheads</b> above also saves any connection you've edited here.
            </div>`
            + `<div class="small mb-2 pc-missing" style="color:#ffc107; display:none;"></div>`
            + `<div id="pc-rows" style="${pcGrid}">`
            + `<span class="small text-secondary">Printer</span>`
            + `<span class="small text-secondary">PrusaLink IP</span>`
            + `<span class="small text-secondary">API key</span>`
            + `<span></span>`
            + rows.map(pcRowHtml).join('')
            + `</div>`;
    }

    function pcRowHtml(p) {
        const nm = _esc(p.name || p.id);
        const id = _esc(p.id || '');
        const ip = _esc(p.ip || '');
        // display:contents → the 4 cells below become direct items of the
        // #pc-rows grid, so every row's columns line up with the header. (Exactly
        // 4 cells to match grid-template-columns; the action cell holds the
        // badge + Save + status so the count stays 4.)
        return `<div class="pc-row" data-location-id="${id}" data-printer="${_esc(p.name || '')}" data-key-set="${p.keySet ? '1' : '0'}" style="display:contents;">
            <span class="small text-white" title="${nm}${id ? ` (${id})` : ''}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${nm}${id ? ` <span style="color:rgba(255,255,255,0.45); font-size:.8em;">${id}</span>` : ''}</span>
            <input class="form-control form-control-sm pc-ip bg-dark text-white border-secondary" type="text" value="${ip}" data-initial="${ip}" placeholder="192.168.1.50" autocomplete="off" style="min-width:0;">
            <input class="form-control form-control-sm pc-key bg-dark text-white border-secondary" type="text" value="" placeholder="${p.keySet ? '•••••• blank keeps it' : 'API key'}" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" style="min-width:0; -webkit-text-security:disc;">
            <span class="d-flex align-items-center gap-2">
                <span class="badge bg-success pc-key-badge" title="An API key is saved" style="${p.keySet ? '' : 'display:none;'}">✓ key</span>
                <button type="button" class="btn btn-sm btn-info pc-save" title="Save this printer's connection">Save</button>
                <span class="small pc-status" style="color:rgba(255,255,255,0.6);"></span>
            </span>
        </div>`;
    }

    function pcWireRow(row) {
        const btn = row.querySelector('.pc-save');
        if (btn) btn.addEventListener('click', () => pcSave(row));
    }

    // A printer with no saved IP is invisible to FCC: no print state, no deduct.
    function pcRenderMissing(host) {
        const el = host && host.querySelector('.pc-missing');
        if (!el) return;
        const missing = Array.from(host.querySelectorAll('.pc-row'))
            .filter((r) => !(r.querySelector('.pc-ip').getAttribute('data-initial') || ''))
            .map((r) => r.getAttribute('data-printer') || r.getAttribute('data-location-id') || '?');
        el.style.display = missing.length ? '' : 'none';
        el.innerHTML = missing.length
            ? `⚠ No connection saved for ${missing.map((n) => `<b>${_esc(n)}</b>`).join(', ')} — FCC can't read `
              + `${missing.length === 1 ? 'its' : 'their'} print state or deduct filament until an IP (and API key) is saved.`
            : '';
    }

    function pcIsDirty(row) {
        const ipEl = row.querySelector('.pc-ip');
        const keyEl = row.querySelector('.pc-key');
        const ip = ((ipEl && ipEl.value) || '').trim();
        return ip !== ((ipEl && ipEl.getAttribute('data-initial')) || '') || !!(keyEl && keyEl.value !== '');
    }

    async function pcPut(row) {
        const id = row.getAttribute('data-location-id') || '';
        const ip = (row.querySelector('.pc-ip').value || '').trim();
        const keyRaw = row.querySelector('.pc-key').value;
        // A blank IP clears the connection; don't let a typed key ride along
        // with it (the server refuses the pair too).
        if (!ip && keyRaw !== '') {
            return { ok: false, msg: "Enter the printer's IP address too — an API key can't be saved without it." };
        }
        // Mirror the Config secret contract: an empty key field means "keep the
        // saved key" (send the sentinel); a typed value replaces it.
        const body = { printer_name: row.getAttribute('data-printer') || '', ip_address: ip,
                       api_key: (keyRaw === '' ? SECRET_SENTINEL : keyRaw) };
        if (id) body.location_id = id;
        const r = await fetch('/api/printer_creds', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        let d = {};
        try { d = await r.json(); } catch (_) { /* non-JSON error page */ }
        return { ok: !!(r.ok && d.ok), msg: (d && d.error) ? d.error : `Save failed (HTTP ${r.status})`,
                 sent: { ip, key: keyRaw } };
    }

    // Other views cache the printer map for the page's lifetime (Feeds dropdown,
    // Quick-Swap, return targets) and the Location Manager list; drop the cache
    // and tell them to refresh, so new toolheads, renamed printers and a newly
    // connected printer show without a page reload.
    function pmAnnounceChange() {
        try { if (typeof state !== 'undefined' && state) state.printerMap = null; } catch (_) { /* no shared state */ }
        document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
    }

    // Reflect a successful save in place. The server contract makes the result
    // predictable: a blank IP clears the connection, a typed key replaces the
    // stored one, a blank key keeps it. No re-render, so unsaved edits elsewhere
    // in the editor survive (the full re-render used to wipe them). Works from
    // what was SENT: anything typed while the request was in flight stays on
    // screen as an unsaved edit instead of being shown as saved.
    function pcMarkSaved(row, sent) {
        const ipEl = row.querySelector('.pc-ip');
        const keyEl = row.querySelector('.pc-key');
        const ip = sent.ip;
        const keySet = ip ? (sent.key !== '' || row.getAttribute('data-key-set') === '1') : false;
        ipEl.setAttribute('data-initial', ip);
        if ((ipEl.value || '').trim() === ip) {
            ipEl.value = ip;
            ipEl.classList.remove('border-warning');
        }
        if (keyEl.value === sent.key) keyEl.value = '';
        keyEl.placeholder = keySet ? '•••••• blank keeps it' : 'API key';
        row.setAttribute('data-key-set', keySet ? '1' : '0');
        const badge = row.querySelector('.pc-key-badge');
        if (badge) badge.style.display = keySet ? '' : 'none';
        pcRenderMissing(document.getElementById(PM_HOST_ID));
    }

    async function pcSave(row) {
        const name = row.getAttribute('data-printer') || row.getAttribute('data-location-id') || '';
        const statusEl = row.querySelector('.pc-status');
        const btn = row.querySelector('.pc-save');
        if (btn) btn.disabled = true;
        if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'Saving…'; }
        try {
            const res = await pcPut(row);
            if (res.ok) {
                pcMarkSaved(row, res.sent);
                if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                if (window.showToast) window.showToast(`Connection saved for ${name}`, 'success', 4000);
                pmAnnounceChange();
            } else {
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = res.msg; }
                if (window.showToast) window.showToast(res.msg, 'error', 8000);
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
                // but no LocationID is a mistake — don't silently drop it. A new
                // row starts at position 0, so 0 counts as blank.
                if (name || (posRaw !== '' && posRaw != null && posRaw !== '0')) incomplete = true;
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
        // Hotfix 2026-09-29: an edited connection with a key but no IP can't be
        // saved — say so before writing anything, so what was typed stays put.
        const credRows = Array.from(host.querySelectorAll('.pc-row')).filter(pcIsDirty);
        const keyNoIp = credRows.find((row) => !(row.querySelector('.pc-ip').value || '').trim()
            && row.querySelector('.pc-key').value !== '');
        if (keyNoIp) {
            const who = keyNoIp.getAttribute('data-printer') || keyNoIp.getAttribute('data-location-id');
            if (window.showToast) window.showToast(`Enter the IP address for ${who} too — an API key can't be saved without it.`, 'error', 8000);
            return;
        }
        if (btn) btn.disabled = true;
        if (statusEl) { statusEl.style.color = 'rgba(255,255,255,0.6)'; statusEl.textContent = 'Saving…'; }
        try {
            // Hotfix 2026-09-29: save any connection typed into the grid below
            // first. Its per-row Save was easy to miss, and the reload after this
            // save threw the typed IP + key away — how the INDX ended up on prod
            // with no connection at all. If one fails, stop before the toolhead
            // save: its reload would wipe what the user typed.
            let credSaved = 0;
            const credFailures = [];
            for (const row of credRows) {
                const res = await pcPut(row);
                if (res.ok) { credSaved += 1; pcMarkSaved(row, res.sent); }
                else credFailures.push(`${row.getAttribute('data-printer') || row.getAttribute('data-location-id')}: ${res.msg}`);
            }
            if (credFailures.length) {
                if (credSaved) pmAnnounceChange();
                const msg = `Connection not saved — ${credFailures.join('; ')}. Toolheads not saved either; fix the connection and save again.`;
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = 'Not saved'; }
                if (window.showToast) window.showToast(msg, 'error', 9000);
                return;
            }
            const r = await fetch('/api/printer_map', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ printer_map: map }),
            });
            const d = await r.json();
            if (r.ok && d.ok) {
                if (statusEl) { statusEl.style.color = '#7CFC00'; statusEl.textContent = '✓ Saved'; }
                const made = (d.created_toolhead_rows || []).length;
                const parts = ['Toolheads saved'];
                if (made) parts.push(`${made} toolhead location${made === 1 ? '' : 's'} created`);
                if (credSaved) parts.push(`${credSaved} connection${credSaved === 1 ? '' : 's'} saved`);
                if (window.showToast) window.showToast(parts.join(' · '), 'success', 4000);
                window.renderPrinterMap({ focusMissing: true });  // reload canonical from server
                pmAnnounceChange();
            } else {
                const msg = (d && d.error) ? d.error : 'Save failed';
                if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
                if (window.showToast) window.showToast(msg, 'error', 8000);  // long: block messages matter
                if (credSaved) pmAnnounceChange();  // the connections above did save
            }
        } catch (e) {
            const msg = 'Save error: ' + (e && e.message ? e.message : e);
            if (statusEl) { statusEl.style.color = '#ff6b6b'; statusEl.textContent = msg; }
            if (window.showToast) window.showToast(msg, 'error', 7000);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // opts.focusMissing (after a toolhead save): point the user at the first
    // printer still lacking a connection — typically the one just added.
    window.renderPrinterMap = async function (opts) {
        const host = document.getElementById(PM_HOST_ID);
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Loading toolheads…</div>`;
        try {
            const r = await fetch('/api/printer_map');
            const d = await r.json();
            pmRender(d.entries || [], d.printer_creds || {}, d.printer_rows);
            if (opts && opts.focusMissing) {
                const ip = Array.from(host.querySelectorAll('.pc-row .pc-ip')).find((el) => !el.value.trim());
                if (ip) {
                    ip.classList.add('border-warning');
                    ip.focus();
                }
            }
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
