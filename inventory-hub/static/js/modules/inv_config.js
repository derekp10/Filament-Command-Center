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
        // L18 Phase 1 — paint the schema-driven settings card on every open.
        if (window.renderConfigSettings) window.renderConfigSettings();
        // L18 Phase 3 — the printer_map (toolhead) editor.
        if (window.renderPrinterMap) window.renderPrinterMap();
        // L18 Phase 4 — wire the import/export controls (once).
        if (window.wireImportExport) window.wireImportExport();
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
    // In-module state:
    //   report   — cached /report payload (choices, filaments, counts)
    //   selected — checked-row filament ids (Set, survives table re-render
    //              within a scan, dropped on re-scan to drop stale ids)
    //   filter   — free-text search string for the filter bar; matches
    //              against id/vendor/material/name/attribute substrings
    const _attrs = { report: null, selected: new Set(), filter: '' };

    const _attrsMatchesFilter = (f, needle) => {
        if (!needle) return true;
        const hay = [
            String(f.id), f.vendor, f.material, f.name,
            (f.attributes || []).join(' '),
        ].join(' ').toLowerCase();
        return hay.includes(needle);
    };

    const _attrsRenderTable = () => {
        const host = document.getElementById('config-attrs-results');
        if (!host || !_attrs.report) return;
        const { choices, filaments, counts } = _attrs.report;
        const total = filaments.length;
        const needle = (_attrs.filter || '').toLowerCase();
        const filteredFilaments = needle
            ? filaments.filter(f => _attrsMatchesFilter(f, needle))
            : filaments;
        const visibleCount = filteredFilaments.length;
        // Choices manager — schema-level. Each chip carries a visible
        // red ✕ button so the "click to delete this tag from the system"
        // affordance is obvious. Background tone of the chip itself
        // scales with usage so unused (safe-to-remove) choices look
        // muted vs in-use (warn-on-remove) choices.
        const choiceChips = choices.map(c => {
            const n = counts[c] || 0;
            const usageTitle = n
                ? `${n} filament(s) carry this tag — removing will strip it from every record`
                : `unused — safe to remove`;
            const chipBg = n ? 'background:#0d6efd; color:#fff;' : 'background:#444; color:#bbb;';
            return `<span class="config-attrs-choice-chip d-inline-flex align-items-center me-2 mb-2"
                          title="${usageTitle}"
                          style="${chipBg} padding:0.25rem 0.5rem; border-radius:4px; font-size:0.85rem;">
                <span class="fw-bold">${_esc(c)}</span>
                <span class="ms-2" style="opacity:0.85;">${n}</span>
                <button type="button" class="btn btn-sm config-attrs-rm-choice ms-2 p-0 d-inline-flex align-items-center justify-content-center"
                        data-choice="${_esc(c)}" data-usage="${n}"
                        title="Remove this tag from the system"
                        style="width:18px; height:18px; line-height:1; background:#dc3545; color:#fff; border:none; border-radius:3px; font-weight:bold;">✕</button>
            </span>`;
        }).join('');
        const choiceOpts = choices.map(c => `<option value="${_esc(c)}">${_esc(c)}</option>`).join('');
        const selVisible = filteredFilaments.filter(f => _attrs.selected.has(f.id)).length;
        const allVisibleSelectedCls = selVisible === visibleCount && visibleCount > 0 ? 'checked' : '';
        const rows = filteredFilaments.map(f => {
            const checked = _attrs.selected.has(f.id) ? 'checked' : '';
            // Don't use Bootstrap's text-muted (#6c757d) — sits at ~1.4:1
            // against our dark backgrounds. Same WCAG-AA-bound contrast pitfall
            // pinned in inv_printer_status.js / test_contrast_guard.
            const archived = f.archived ? '<span class="badge bg-dark ms-1" style="color:rgba(255,255,255,0.65);">archived</span>' : '';
            const attrs = (f.attributes || []).map(a => `<span class="badge bg-info text-dark me-1">${_esc(a)}</span>`).join('') || '<span class="small" style="color:rgba(255,255,255,0.55);">—</span>';
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
        const selCount = _attrs.selected.size;
        host.innerHTML = `
            <!-- SECTION 1: Choices manager (schema-level add/remove). -->
            <div class="p-3 mb-3 border rounded" style="border-color:#0d6efd!important; background:rgba(13,110,253,0.08);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0 text-info fw-bold">🛠 Choices Manager <span class="badge bg-secondary ms-1">${choices.length}</span></h6>
                    <span class="small" style="color:rgba(255,255,255,0.7);">add a new tag or remove an existing one — propagates to every filament that carries it</span>
                </div>
                <div class="mb-2">${choiceChips || '<i class="small" style="color:rgba(255,255,255,0.6);">(no choices defined yet — add one below)</i>'}</div>
                <div class="d-flex flex-wrap align-items-center gap-2">
                    <input type="text" id="config-attrs-add-input" class="form-control form-control-sm bg-dark text-white border-secondary"
                           placeholder="Type a new tag name…" autocomplete="off" style="max-width: 280px;">
                    <button class="btn btn-sm btn-success fw-bold" id="config-attrs-add-btn">＋ Add new tag</button>
                    <button class="btn btn-sm btn-outline-warning" id="config-attrs-sweep-btn"
                            title="Find and remove every tag with zero usage (with confirm). Same logic the boot-time auto-cleanup used to run, now explicit.">🧹 Sweep unused</button>
                </div>
            </div>

            <!-- SECTION 2: Per-filament bulk editor. -->
            <div class="p-3 border rounded" style="border-color:#ffc107!important; background:rgba(255,193,7,0.06);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0 text-warning fw-bold">📋 Per-Filament Bulk Editor</h6>
                    <span class="small" style="color:rgba(255,255,255,0.7);"><b>${total}</b> filament(s) loaded</span>
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                    <input type="text" id="config-attrs-filter" class="form-control form-control-sm bg-dark text-white border-secondary"
                           placeholder="🔎 Filter by id / vendor / material / name / attribute…"
                           value="${_esc(_attrs.filter)}" autocomplete="off" style="max-width: 380px;">
                    <span class="small" style="color:rgba(255,255,255,0.7);">${visibleCount}/${total} visible${needle ? ` for "${_esc(_attrs.filter)}"` : ''}</span>
                    ${_attrs.filter ? '<button class="btn btn-sm btn-outline-secondary" id="config-attrs-filter-clear">clear</button>' : ''}
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2 p-2 rounded" style="background:rgba(0,0,0,0.35);">
                    <span class="small text-warning fw-bold">Apply to <span id="config-attrs-sel-count">${selCount}</span> selected:</span>
                    <select id="config-attrs-bulk-choice" class="form-select form-select-sm bg-dark text-white border-secondary" style="width: auto;">
                        ${choiceOpts}
                    </select>
                    <button class="btn btn-sm btn-success" id="config-attrs-bulk-add" ${selCount ? '' : 'disabled'}>＋ Add to selected</button>
                    <button class="btn btn-sm btn-warning" id="config-attrs-bulk-remove" ${selCount ? '' : 'disabled'}>− Remove from selected</button>
                </div>
                <div style="max-height: 40vh; overflow-y: auto;">
                    <table class="table table-sm table-dark table-hover align-middle mb-0">
                        <thead>
                            <tr>
                                <th style="width:32px;"><input type="checkbox" id="config-attrs-select-all" ${allVisibleSelectedCls}></th>
                                <th>ID</th>
                                <th>Vendor</th>
                                <th>Material</th>
                                <th>Name</th>
                                <th>Attributes</th>
                            </tr>
                        </thead>
                        <tbody>${rows || '<tr><td colspan="6" class="text-center small" style="color:rgba(255,255,255,0.6);">no matches</td></tr>'}</tbody>
                    </table>
                </div>
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
        // Select-all operates on the currently-visible (filtered) rows so
        // the user can narrow with the search box then check-all without
        // accidentally pulling in records they can't see.
        if (selAll) selAll.addEventListener('change', (e) => {
            if (e.target.checked) filteredFilaments.forEach(f => _attrs.selected.add(f.id));
            else filteredFilaments.forEach(f => _attrs.selected.delete(f.id));
            _attrsRenderTable();
        });

        // Search filter — re-renders on every keystroke. With ~200 rows
        // it's snappy enough not to need a debounce.
        const filterEl = document.getElementById('config-attrs-filter');
        if (filterEl) {
            filterEl.addEventListener('input', (e) => {
                _attrs.filter = e.target.value;
                _attrsRenderTable();
                // Restore focus + caret position after the re-render.
                const after = document.getElementById('config-attrs-filter');
                if (after) {
                    after.focus();
                    after.setSelectionRange(after.value.length, after.value.length);
                }
            });
        }
        const filterClear = document.getElementById('config-attrs-filter-clear');
        if (filterClear) filterClear.addEventListener('click', () => {
            _attrs.filter = '';
            _attrsRenderTable();
        });

        // Bulk add/remove on selected rows.
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

        // Schema-side: add new choice.
        const newInput = document.getElementById('config-attrs-add-input');
        const newBtn = document.getElementById('config-attrs-add-btn');
        const doAdd = () => {
            const val = (newInput && newInput.value || '').trim();
            if (!val) {
                window.showToast && window.showToast('Type a name first', 'warning', 4000);
                return;
            }
            window.configAttrsAddChoice(val);
        };
        if (newBtn) newBtn.addEventListener('click', doAdd);
        if (newInput) newInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
        });

        // Schema-side: sweep unused choices.
        const sweepBtn = document.getElementById('config-attrs-sweep-btn');
        if (sweepBtn) sweepBtn.addEventListener('click', () => {
            window.configAttrsSweepUnused();
        });

        // Schema-side: remove a choice from the field. Server gates with
        // a confirmation step when usage > 0 — we surface that as a
        // browser confirm() dialog rather than a SweetAlert/mountOverlay
        // here, since the Admin modal already owns the modal stack.
        host.querySelectorAll('.config-attrs-rm-choice').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const c = btn.dataset.choice;
                const usage = parseInt(btn.dataset.usage || '0', 10);
                if (!c) return;
                if (usage > 0) {
                    const ok = confirm(
                        `Remove choice "${c}" from the schema?\n\n` +
                        `${usage} filament(s) currently have this tag — they will lose it.\n` +
                        `This cannot be undone (besides re-adding the choice and re-tagging each filament).`
                    );
                    if (!ok) return;
                }
                window.configAttrsRemoveChoice(c, usage > 0);
            });
        });
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

    // --- RESTORE SPOOLMAN FIELD ORDER (L318) ---
    // Preview-then-apply flow. The Preview button hits the endpoint with
    // ?dry_run=true so the user sees the exact list of moves before any
    // write to Spoolman happens. Apply only fires after the user clicks
    // the second button. Derek 2026-05-28 explicitly wanted assurance
    // that this can't lose field data; the dry-run is the safety net.

    const _renderRestoreSummary = (d, mode) => {
        const sum = d.summary || { filament: {}, spool: {} };
        const renderEntityRow = (label, s) => {
            const errors = Array.isArray(s.errors) ? s.errors : [];
            const moved = mode === 'apply' ? (s.updated || 0) : (s.would_update || 0);
            const movedLabel = mode === 'apply' ? 'updated' : 'will move';
            const errHtml = errors.length
                ? `<ul class="small mb-0 mt-1" style="color:#ff8a8a;">${errors.map(e => `<li>${_esc(e)}</li>`).join('')}</ul>`
                : '';
            // Per-field change table — what's actually going to move, by name.
            const changes = Array.isArray(s.changes) ? s.changes : [];
            const changesHtml = changes.length
                ? `
                    <div class="small mt-1" style="color: rgba(255,255,255,0.85);">
                        <table class="table table-dark table-sm table-bordered mb-0" style="font-size:0.82rem;">
                            <thead>
                                <tr>
                                    <th>Field</th>
                                    <th style="width:5rem;">From</th>
                                    <th style="width:5rem;">To</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${changes.map(c => `
                                    <tr>
                                        <td>${_esc(c.name || c.key)} <span class="text-secondary">(<code>${_esc(c.key)}</code>)</span></td>
                                        <td><span class="badge bg-secondary">${c.from_order}</span></td>
                                        <td><span class="badge bg-info text-dark">${c.to_order}</span></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>`
                : '';
            return `
                <li class="mb-2">
                    <b>${_esc(label)}:</b>
                    ${moved} ${movedLabel} · ${s.skipped || 0} skipped · ${errors.length} error(s)
                    ${errHtml}
                    ${changesHtml}
                </li>`;
        };
        const movedTotal = mode === 'apply'
            ? ((sum.filament.updated || 0) + (sum.spool.updated || 0))
            : ((sum.filament.would_update || 0) + (sum.spool.would_update || 0));
        const alertClass = d.success
            ? (movedTotal > 0 ? (mode === 'apply' ? 'alert-success' : 'alert-warning') : 'alert-info')
            : 'alert-danger';
        let headline;
        if (!d.success) {
            headline = '⚠️ Errors encountered — see details below';
        } else if (movedTotal === 0) {
            headline = 'ℹ️ Already in canonical order — nothing to do';
        } else if (mode === 'apply') {
            headline = `✅ Restored — ${movedTotal} field(s) updated`;
        } else {
            headline = `👀 Preview — ${movedTotal} field(s) will move`;
        }
        const applyBtn = (mode === 'preview' && d.success && movedTotal > 0)
            ? `<div class="mt-2 d-flex gap-2">
                    <button class="btn btn-sm btn-warning fw-bold"
                            onclick="window.configRestoreFieldOrderApply()">
                        ✅ Apply ${movedTotal} change${movedTotal === 1 ? '' : 's'}
                    </button>
                    <button class="btn btn-sm btn-outline-light"
                            onclick="window.configRestoreFieldOrderReset()">
                        Cancel
                    </button>
               </div>`
            : '';
        return `
            <div class="alert ${alertClass} py-2 mb-0">
                <div class="fw-bold mb-1">${headline}</div>
                <ul class="small mb-0 ps-3">
                    ${renderEntityRow('Filament fields', sum.filament || {})}
                    ${renderEntityRow('Spool fields', sum.spool || {})}
                </ul>
                ${applyBtn}
            </div>`;
    };

    window.configRestoreFieldOrder = async () => {
        // Default click = PREVIEW (dry_run). Apply is a separate explicit
        // action after the user reviews the proposed changes.
        const host = document.getElementById('config-restore-field-order-results');
        const btn = document.getElementById('btn-config-restore-field-order');
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Loading preview…</div>`;
        if (btn) btn.disabled = true;
        try {
            const r = await fetch('/api/spoolman/restore_field_order?dry_run=true',
                                  { method: 'POST' });
            const d = await r.json();
            host.innerHTML = _renderRestoreSummary(d, 'preview');
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Preview failed: ${_esc(e.message || e)}</div>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.configRestoreFieldOrderApply = async () => {
        const host = document.getElementById('config-restore-field-order-results');
        if (!host) return;
        host.innerHTML = `<div class="text-info small"><span class="spinner-border spinner-border-sm me-2"></span>Applying changes to Spoolman…</div>`;
        try {
            const r = await fetch('/api/spoolman/restore_field_order',
                                  { method: 'POST' });
            const d = await r.json();
            host.innerHTML = _renderRestoreSummary(d, 'apply');
        } catch (e) {
            host.innerHTML = `<div class="alert alert-danger py-2 mb-0">Apply failed: ${_esc(e.message || e)}</div>`;
        }
    };

    window.configRestoreFieldOrderReset = () => {
        const host = document.getElementById('config-restore-field-order-results');
        if (host) {
            host.innerHTML = `<div class="small" style="color: rgba(255,255,255,0.6);">
                Click <b>Preview changes</b> to start.
            </div>`;
        }
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

    window.configAttrsAddChoice = async (choice) => {
        try {
            const r = await fetch('/api/filament_attributes/add_choice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ choice }),
            });
            const d = await r.json();
            if (!d.success) {
                window.showToast && window.showToast(`Add failed: ${d.msg || 'unknown'}`, 'error', 7000);
                return;
            }
            window.showToast && window.showToast(`Added choice "${choice}"`, 'success', 4000);
            // Refresh so the new choice appears in the bulk-set picker.
            window.configAttrsScan();
        } catch (e) {
            window.showToast && window.showToast(`Add error: ${e.message || e}`, 'error', 7000);
        }
    };

    // Sweep zero-usage choices. Two-step server round-trip: first call
    // (no force) returns the preview list; second call (force=true,
    // choices=[subset]) commits the DELETE+POST recreate for the
    // user-selected subset. The preview→select→commit flow lets the user
    // keep individual currently-unused tags (e.g. "For Infill" they're
    // about to re-apply but haven't yet).
    //
    // UI: mountOverlay-based styled dialog with per-tag checkboxes, NOT
    // a browser confirm(). CLAUDE.md "Inline overlays MUST route through
    // window.mountOverlay()" — same focus/z-index/host-cascade guarantees
    // every other inline overlay in the app gets.
    window.configAttrsSweepUnused = async () => {
        let unused = [];
        try {
            const r = await fetch('/api/filament_attributes/sweep_unused', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const d = await r.json();
            if (!d.success) {
                window.showToast && window.showToast(`Sweep preview failed: ${d.msg || 'unknown'}`, 'error', 7000);
                return;
            }
            unused = d.unused || [];
        } catch (e) {
            window.showToast && window.showToast(`Sweep preview error: ${e.message || e}`, 'error', 7000);
            return;
        }
        if (!unused.length) {
            window.showToast && window.showToast('All choices are in use — nothing to sweep.', 'info', 4000);
            return;
        }

        const rows = unused.map(c => `
            <label class="d-flex align-items-center px-3 py-2 border-bottom border-secondary"
                   style="cursor:pointer; user-select:none;">
                <input type="checkbox" class="form-check-input me-3 sweep-overlay-cb"
                       data-choice="${_esc(c)}" checked>
                <span class="fw-bold text-info">${_esc(c)}</span>
                <span class="ms-auto small" style="color:rgba(255,255,255,0.65);">0 filaments</span>
            </label>
        `).join('');

        const body = `
            <div style="background:#181818; color:#fff; border:2px solid #ffc107; border-radius:6px;
                        width:520px; max-width:92vw; max-height:80vh; display:flex; flex-direction:column;
                        box-shadow:0 0 24px rgba(255,193,7,0.35);">
                <div class="d-flex justify-content-between align-items-center px-3 py-2"
                     style="background:#1a1a1a; border-bottom:1px solid #ffc107;">
                    <h6 class="m-0 fw-bold text-warning">🧹 Sweep Unused Tags</h6>
                    <button type="button" class="btn-close btn-close-white" id="sweep-overlay-cancel-x"
                            aria-label="Close" style="filter: invert(0);"></button>
                </div>
                <div class="px-3 py-2 small" style="color:rgba(255,255,255,0.78); border-bottom:1px solid #333;">
                    Each tag below has <b>zero filaments</b> using it right now. Uncheck any you want
                    to keep — removal is irreversible (you'd have to re-add by name).
                </div>
                <div class="d-flex align-items-center px-3 py-2" style="background:#1f1f1f;">
                    <button type="button" class="btn btn-sm btn-outline-info" id="sweep-overlay-all">Select all</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary ms-2" id="sweep-overlay-none">Select none</button>
                    <span class="ms-auto small" style="color:rgba(255,255,255,0.7);">
                        <span id="sweep-overlay-count">${unused.length}</span> / ${unused.length} selected
                    </span>
                </div>
                <div id="sweep-overlay-rows" style="flex:1 1 auto; overflow-y:auto; background:#141414;">
                    ${rows}
                </div>
                <div class="d-flex justify-content-end gap-2 px-3 py-2"
                     style="background:#1a1a1a; border-top:1px solid #333;">
                    <button type="button" class="btn btn-sm btn-secondary" id="sweep-overlay-cancel">Cancel</button>
                    <button type="button" class="btn btn-sm btn-warning fw-bold" id="sweep-overlay-commit">
                        🧹 Sweep selected
                    </button>
                </div>
            </div>
        `;

        const configModal = document.getElementById('configModal');
        const handle = window.mountOverlay({
            id: 'fcc-sweep-unused-overlay',
            content: body,
            tier: 'confirm',  // sits above the configModal
            host: configModal,  // cleanup on host close
            initialFocus: '#sweep-overlay-commit',
            occlude: ['select'],
        });
        const root = handle.panel;

        const updateCount = () => {
            const n = root.querySelectorAll('.sweep-overlay-cb:checked').length;
            const lbl = root.querySelector('#sweep-overlay-count');
            if (lbl) lbl.textContent = String(n);
            const commit = root.querySelector('#sweep-overlay-commit');
            if (commit) commit.disabled = n === 0;
        };

        root.querySelectorAll('.sweep-overlay-cb').forEach(cb => {
            cb.addEventListener('change', updateCount);
        });
        root.querySelector('#sweep-overlay-all').addEventListener('click', () => {
            root.querySelectorAll('.sweep-overlay-cb').forEach(cb => { cb.checked = true; });
            updateCount();
        });
        root.querySelector('#sweep-overlay-none').addEventListener('click', () => {
            root.querySelectorAll('.sweep-overlay-cb').forEach(cb => { cb.checked = false; });
            updateCount();
        });
        root.querySelector('#sweep-overlay-cancel').addEventListener('click', () => handle.cleanup());
        root.querySelector('#sweep-overlay-cancel-x').addEventListener('click', () => handle.cleanup());
        root.querySelector('#sweep-overlay-commit').addEventListener('click', async () => {
            const chosen = Array.from(root.querySelectorAll('.sweep-overlay-cb:checked'))
                .map(cb => cb.dataset.choice);
            if (!chosen.length) return;
            const commit = root.querySelector('#sweep-overlay-commit');
            commit.disabled = true;
            commit.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Sweeping…';
            try {
                const r2 = await fetch('/api/filament_attributes/sweep_unused', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ force: true, choices: chosen }),
                });
                const d2 = await r2.json();
                if (!d2.success) {
                    window.showToast && window.showToast(`Sweep failed: ${d2.msg || 'unknown'}`, 'error', 7000);
                    commit.disabled = false;
                    commit.innerHTML = '🧹 Sweep selected';
                    return;
                }
                const removed = d2.removed || [];
                handle.cleanup();
                window.showToast && window.showToast(
                    `Swept ${removed.length} tag(s): ${removed.join(', ')}`,
                    'success', 5000,
                );
                window.configAttrsScan();
            } catch (e) {
                window.showToast && window.showToast(`Sweep error: ${e.message || e}`, 'error', 7000);
                commit.disabled = false;
                commit.innerHTML = '🧹 Sweep selected';
            }
        });
    };

    // `force` mirrors the server-side flag — true on the second call after
    // the user confirms a destructive remove (usage > 0). For unused
    // choices we still send `force: true` so the server doesn't need to
    // round-trip the "are you sure?" check.
    window.configAttrsRemoveChoice = async (choice, force) => {
        try {
            const r = await fetch('/api/filament_attributes/remove_choice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ choice, force: true }),
            });
            const d = await r.json();
            if (!d.success) {
                window.showToast && window.showToast(`Remove failed: ${d.msg || 'unknown'}`, 'error', 7000);
                return;
            }
            const stripped = d.stripped || 0;
            const msg = stripped
                ? `Removed choice "${choice}" — stripped from ${stripped} filament(s).`
                : `Removed unused choice "${choice}".`;
            window.showToast && window.showToast(msg, 'success', 4000);
            window.configAttrsScan();
        } catch (e) {
            window.showToast && window.showToast(`Remove error: ${e.message || e}`, 'error', 7000);
        }
    };
})();
