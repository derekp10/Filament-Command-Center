/* MODULE: CONFIG / ADMIN — L324 scaffold
 *
 * First inhabitant is the FilaBridge ↔ Spoolman Reconcile tool. Future
 * config sections (user preferences, choice cleanup launcher, build-info
 * viewer, etc.) drop into modals_config.html and add their own openers
 * here. The Bootstrap modal itself is reusable — we just rewrite the
 * relevant card-body when the user opens a section.
 */
console.log("🚀 Loaded Module: CONFIG");

(function () {
    const _esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');

    window.openConfigModal = () => {
        const el = document.getElementById('configModal');
        if (!el) return;
        if (!window.modals) window.modals = {};
        if (!window.modals.configModal) {
            window.modals.configModal = new bootstrap.Modal(el);
        }
        // Populate the Build Info section every open (cheap, and it picks
        // up whatever .build_info is current — the version-badge re-read
        // we added in L42 round 2 already covers this server-side).
        const badge = document.getElementById('fcc-build-version');
        const buildBox = document.getElementById('config-build-info');
        if (buildBox && badge) {
            const sha = badge.dataset.buildCommitSha || '(unresolved)';
            const ts = parseInt(badge.dataset.buildCommitTs || '0', 10);
            const mtime = parseFloat(badge.dataset.buildMtime || '0');
            const fmtTs = (u) => {
                if (!u) return '(unknown)';
                const d = new Date(u * 1000);
                const pad = (n) => String(n).padStart(2, '0');
                return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
                    + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
            };
            buildBox.innerHTML = `
                <div>Commit SHA: <span style="color:#0ff;">${_esc(sha)}</span></div>
                <div>Commit time: ${_esc(fmtTs(ts))}</div>
                <div>Source mtime: ${_esc(fmtTs(mtime))}</div>
            `;
        }
        window.modals.configModal.show();
    };

    // --- RECONCILE SECTION ---
    window.configReconcileScan = async () => {
        const host = document.getElementById('config-reconcile-results');
        const btn = document.getElementById('btn-config-reconcile-scan');
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Scanning FilaBridge + Spoolman…</div>`;
        if (btn) btn.disabled = true;
        try {
            const r = await fetch('/api/filabridge/reconcile');
            const d = await r.json();
            if (!d.success) {
                host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Scan failed: ${_esc(d.msg)}</div>`;
                return;
            }
            const { matched, mismatches } = d;
            if (!mismatches || !mismatches.length) {
                host.innerHTML = `
                    <div class="alert alert-success py-2 mb-0">
                        ✅ Clean — ${matched} mapping(s) match between FilaBridge and Spoolman.
                    </div>`;
                return;
            }
            // Build a table: one row per mismatch with Trust-Spoolman /
            // Trust-FilaBridge action buttons.
            const rows = mismatches.map((m, i) => {
                const payload = encodeURIComponent(JSON.stringify(m));
                const display = m.spool_display || `#${m.spool_id}`;
                const fbLoc = m.fb_location || '<i>(unmapped position)</i>';
                const smLoc = m.sm_location || '<i>(empty)</i>';
                return `
                    <tr data-row="${i}">
                        <td><b>#${m.spool_id}</b><br><span class="small" style="color: rgba(255,255,255,0.75);">${_esc(display)}</span></td>
                        <td>${_esc(m.fb_printer)}<br><span class="small" style="color: rgba(255,255,255,0.75);">th ${m.fb_toolhead} → ${_esc(fbLoc)}</span></td>
                        <td><span style="color:#0ff;">${_esc(smLoc)}</span></td>
                        <td>
                            <div class="d-flex flex-column gap-1">
                                <button class="btn btn-sm btn-outline-info"
                                        onclick="window.configReconcileApply('${payload}', 'trust_spoolman', this)">
                                    Trust Spoolman<br><span class="small">(clear FilaBridge)</span>
                                </button>
                                <button class="btn btn-sm btn-outline-warning"
                                        onclick="window.configReconcileApply('${payload}', 'trust_filabridge', this)">
                                    Trust FilaBridge<br><span class="small">(update Spoolman)</span>
                                </button>
                            </div>
                        </td>
                    </tr>`;
            }).join('');
            host.innerHTML = `
                <div class="alert alert-warning py-2 mb-2">
                    Found <b>${mismatches.length}</b> mismatch${mismatches.length === 1 ? '' : 'es'}
                    (${matched} clean). Pick the source of truth per row.
                </div>
                <div class="table-responsive">
                <table class="table table-dark table-bordered table-sm align-middle mb-0">
                    <thead>
                        <tr>
                            <th>Spool</th>
                            <th>FilaBridge says</th>
                            <th>Spoolman says</th>
                            <th style="width: 12rem;">Resolve</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                </div>
            `;
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Scan failed: ${_esc(e.message || e)}</div>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.configReconcileApply = async (encodedPayload, action, btn) => {
        let payload;
        try {
            payload = JSON.parse(decodeURIComponent(encodedPayload));
        } catch (e) {
            if (window.showToast) window.showToast('Bad reconcile payload', 'error', 5000);
            return;
        }
        payload.action = action;
        if (btn) { btn.disabled = true; btn.innerText = 'Applying…'; }
        try {
            const r = await fetch('/api/filabridge/reconcile/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            if (!d.success) {
                if (window.showToast) window.showToast(`Reconcile failed: ${d.msg}`, 'error', 7000);
                if (btn) { btn.disabled = false; btn.innerText = btn.innerText.replace('Applying…', 'Retry'); }
                return;
            }
            if (window.showToast) {
                const verb = action === 'trust_spoolman' ? 'cleared FilaBridge' : 'updated Spoolman';
                window.showToast(`Reconcile: ${verb} for Spool #${payload.spool_id}`, 'success', 4000);
            }
            // Re-scan to refresh the table — the row we just fixed should
            // drop out, and any side-effects (a row whose FB unmap also
            // healed a duplicate elsewhere) are picked up too.
            window.configReconcileScan();
        } catch (e) {
            if (window.showToast) window.showToast(`Reconcile error: ${e.message || e}`, 'error', 7000);
            if (btn) { btn.disabled = false; }
        }
    };

    // --- FILAMENT ATTRIBUTES MANAGER (L58) ---
    // In-module state for the attributes table — selected filament ids
    // and the cached report so the bulk-set action doesn't have to
    // re-fetch before sending the PATCH. Re-scanning after a bulk-set
    // refreshes both.
    const _attrs = { report: null, selected: new Set() };

    const _attrsRenderTable = () => {
        const host = document.getElementById('config-attrs-results');
        if (!host || !_attrs.report) return;
        const { choices, filaments, counts } = _attrs.report;
        const total = filaments.length;
        const selCount = _attrs.selected.size;
        const choiceChips = choices.map(c => {
            const n = counts[c] || 0;
            return `<span class="badge bg-secondary me-1 mb-1" title="${n} filament(s) carry this flag">${_esc(c)} <span class="ms-1 text-info">${n}</span></span>`;
        }).join('');
        const choiceOpts = choices.map(c => `<option value="${_esc(c)}">${_esc(c)}</option>`).join('');
        const allSelectedCls = selCount === total && total > 0 ? 'checked' : '';
        const rows = filaments.map(f => {
            const checked = _attrs.selected.has(f.id) ? 'checked' : '';
            const archived = f.archived ? '<span class="badge bg-dark text-muted ms-1">archived</span>' : '';
            const attrs = (f.attributes || []).map(a => `<span class="badge bg-info text-dark me-1">${_esc(a)}</span>`).join('') || '<span class="text-muted small">—</span>';
            return `
                <tr data-fid="${f.id}">
                    <td><input type="checkbox" class="config-attrs-row-cb" data-fid="${f.id}" ${checked}></td>
                    <td><b>#${f.id}</b> ${archived}</td>
                    <td>${_esc(f.vendor)}</td>
                    <td>${_esc(f.material)}</td>
                    <td>${_esc(f.name)}</td>
                    <td>${attrs}</td>
                </tr>`;
        }).join('');
        host.innerHTML = `
            <div class="mb-2 small" style="color: rgba(255,255,255,0.85);">
                <b>${total}</b> filament(s) loaded. Flag usage:
                <div class="mt-1">${choiceChips || '<i class="text-muted">(no choices defined)</i>'}</div>
            </div>
            <div class="d-flex flex-wrap align-items-center gap-2 mb-2 p-2 border border-secondary rounded">
                <span class="small text-info fw-bold">Bulk action for <span id="config-attrs-sel-count">${selCount}</span> selected:</span>
                <select id="config-attrs-bulk-choice" class="form-select form-select-sm bg-dark text-white border-secondary" style="width: auto;">
                    ${choiceOpts}
                </select>
                <button class="btn btn-sm btn-success" id="config-attrs-bulk-add" ${selCount ? '' : 'disabled'}>＋ Add to selected</button>
                <button class="btn btn-sm btn-warning" id="config-attrs-bulk-remove" ${selCount ? '' : 'disabled'}>− Remove from selected</button>
            </div>
            <div style="max-height: 50vh; overflow-y: auto;">
                <table class="table table-sm table-dark table-hover align-middle mb-0">
                    <thead>
                        <tr>
                            <th style="width:32px;"><input type="checkbox" id="config-attrs-select-all" ${allSelectedCls}></th>
                            <th>ID</th>
                            <th>Vendor</th>
                            <th>Material</th>
                            <th>Name</th>
                            <th>Attributes</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;

        host.querySelectorAll('.config-attrs-row-cb').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const fid = parseInt(e.target.dataset.fid, 10);
                if (e.target.checked) _attrs.selected.add(fid);
                else _attrs.selected.delete(fid);
                _attrsUpdateSelCount();
            });
        });
        const selAll = document.getElementById('config-attrs-select-all');
        if (selAll) selAll.addEventListener('change', (e) => {
            _attrs.selected = new Set(e.target.checked ? filaments.map(f => f.id) : []);
            _attrsRenderTable();
        });
        const choiceEl = document.getElementById('config-attrs-bulk-choice');
        const apply = (which) => {
            const choice = choiceEl ? choiceEl.value : '';
            if (!choice) {
                window.showToast && window.showToast('Pick a choice to apply', 'warning', 4000);
                return;
            }
            window.configAttrsBulkApply(which, choice);
        };
        const addBtn = document.getElementById('config-attrs-bulk-add');
        const remBtn = document.getElementById('config-attrs-bulk-remove');
        if (addBtn) addBtn.addEventListener('click', () => apply('add'));
        if (remBtn) remBtn.addEventListener('click', () => apply('remove'));
    };

    const _attrsUpdateSelCount = () => {
        const lbl = document.getElementById('config-attrs-sel-count');
        if (lbl) lbl.textContent = String(_attrs.selected.size);
        const addBtn = document.getElementById('config-attrs-bulk-add');
        const remBtn = document.getElementById('config-attrs-bulk-remove');
        const hasSel = _attrs.selected.size > 0;
        if (addBtn) addBtn.disabled = !hasSel;
        if (remBtn) remBtn.disabled = !hasSel;
    };

    window.configAttrsScan = async () => {
        const host = document.getElementById('config-attrs-results');
        const btn = document.getElementById('btn-config-attrs-scan');
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Loading filament attributes report…</div>`;
        if (btn) btn.disabled = true;
        try {
            const r = await fetch('/api/filament_attributes/report');
            const d = await r.json();
            if (!d.success) {
                host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Load failed: ${_esc(d.msg)}</div>`;
                return;
            }
            _attrs.report = d;
            const stillValid = new Set(d.filaments.map(f => f.id));
            _attrs.selected = new Set([..._attrs.selected].filter(id => stillValid.has(id)));
            _attrsRenderTable();
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Load error: ${_esc(e.message || e)}</div>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.configAttrsBulkApply = async (which, choice) => {
        const ids = [..._attrs.selected];
        if (!ids.length) return;
        const body = { filament_ids: ids };
        body[which] = [choice];
        try {
            const r = await fetch('/api/filament_attributes/bulk_set', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const d = await r.json();
            if (!d.success) {
                window.showToast && window.showToast(`Bulk-set failed: ${d.msg || 'unknown'}`, 'error', 7000);
                return;
            }
            const verb = which === 'add' ? 'added to' : 'removed from';
            const errMsg = d.errors && d.errors.length ? ` — ${d.errors.length} error(s)` : '';
            window.showToast && window.showToast(
                `"${choice}" ${verb} ${d.updated} filament(s)` + (d.unchanged ? `, ${d.unchanged} unchanged` : '') + errMsg,
                d.errors && d.errors.length ? 'warning' : 'success',
                d.errors && d.errors.length ? 7000 : 4000,
            );
            window.configAttrsScan();
        } catch (e) {
            window.showToast && window.showToast(`Bulk-set error: ${e.message || e}`, 'error', 7000);
        }
    };
})();
