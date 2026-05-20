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
        const selCount = _attrs.selected.size;
        host.innerHTML = `
            <!-- SECTION 1: Choices manager (schema-level add/remove). -->
            <div class="p-3 mb-3 border rounded" style="border-color:#0d6efd!important; background:rgba(13,110,253,0.08);">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0 text-info fw-bold">🛠 Choices Manager <span class="badge bg-secondary ms-1">${choices.length}</span></h6>
                    <span class="small text-muted">add a new tag or remove an existing one — propagates to every filament that carries it</span>
                </div>
                <div class="mb-2">${choiceChips || '<i class="text-muted small">(no choices defined yet — add one below)</i>'}</div>
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
                    <span class="small text-muted"><b>${total}</b> filament(s) loaded</span>
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                    <input type="text" id="config-attrs-filter" class="form-control form-control-sm bg-dark text-white border-secondary"
                           placeholder="🔎 Filter by id / vendor / material / name / attribute…"
                           value="${_esc(_attrs.filter)}" autocomplete="off" style="max-width: 380px;">
                    <span class="small text-muted">${visibleCount}/${total} visible${needle ? ` for "${_esc(_attrs.filter)}"` : ''}</span>
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
                        <tbody>${rows || '<tr><td colspan="6" class="text-center text-muted small">no matches</td></tr>'}</tbody>
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

    // Sweep all zero-usage choices. Two-step server round-trip: first
    // call (no force) returns the preview list; second call (force=true)
    // commits the DELETE+POST recreate. The preview lets us show the
    // user the exact list before they confirm — important because the
    // operation is irreversible (besides re-adding each choice).
    window.configAttrsSweepUnused = async () => {
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
            const unused = d.unused || [];
            if (!unused.length) {
                window.showToast && window.showToast('All choices are in use — nothing to sweep.', 'info', 4000);
                return;
            }
            const ok = confirm(
                `Sweep ${unused.length} unused tag(s) from the system?\n\n` +
                unused.map(c => `  • ${c}`).join('\n') +
                `\n\n` +
                `Each tag currently has zero filaments using it. Removal is irreversible ` +
                `(besides re-adding each name).`
            );
            if (!ok) return;
            const r2 = await fetch('/api/filament_attributes/sweep_unused', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: true }),
            });
            const d2 = await r2.json();
            if (!d2.success) {
                window.showToast && window.showToast(`Sweep failed: ${d2.msg || 'unknown'}`, 'error', 7000);
                return;
            }
            const removed = d2.removed || [];
            window.showToast && window.showToast(
                `Swept ${removed.length} unused tag(s): ${removed.join(', ')}`,
                'success', 5000,
            );
            window.configAttrsScan();
        } catch (e) {
            window.showToast && window.showToast(`Sweep error: ${e.message || e}`, 'error', 7000);
        }
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
