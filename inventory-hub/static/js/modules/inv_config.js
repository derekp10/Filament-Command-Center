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
})();
