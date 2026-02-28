/**
 * SearchEngine - Global Reusable Search Component
 * Enables fuzzy searching and color proximity matching against the Spoolman DB.
 * Can be opened in "Select Mode" to return an ID to a calling form.
 */
const SearchEngine = {
    offcanvas: null,
    debounceTimer: null,
    currentCallback: null,

    init() {
        const el = document.getElementById('offcanvasSearch');
        if (el) {
            this.offcanvas = new bootstrap.Offcanvas(el, { backdrop: true });

            // Attach UI listeners
            const trig = ['global-search-query', 'global-search-color-hex', 'global-search-material'];
            trig.forEach(id => {
                const node = document.getElementById(id);
                if (node) {
                    node.addEventListener('input', () => this.debounceTrigger());
                }
            });

            // Search Type Toggle
            document.querySelectorAll('input[name="global-search-type"]').forEach(radio => {
                radio.addEventListener('change', () => this.debounceTrigger());
            });

            // Color picker sets the hex field implicitly
            const picker = document.getElementById('global-search-color-picker');
            const hexInput = document.getElementById('global-search-color-hex');
            if (picker && hexInput) {
                picker.addEventListener('input', (e) => {
                    hexInput.value = e.target.value;
                    this.debounceTrigger();
                });
            }

            const clearColorBtn = document.getElementById('global-search-clear-color');
            if (clearColorBtn && hexInput) {
                clearColorBtn.addEventListener('click', () => {
                    hexInput.value = '';
                    if (picker) picker.value = '#000000';
                    this.debounceTrigger();
                });
            }

            const inStock = document.getElementById('global-search-in-stock');
            if (inStock) {
                inStock.addEventListener('change', () => this.debounceTrigger());
            }

            const clearAllBtn = document.getElementById('global-search-clear-all');
            if (clearAllBtn) {
                clearAllBtn.addEventListener('click', () => {
                    const q = document.getElementById('global-search-query');
                    const h = document.getElementById('global-search-color-hex');
                    const m = document.getElementById('global-search-material');
                    const c = document.getElementById('global-search-color-picker');
                    const s = document.getElementById('global-search-in-stock');

                    if (q) q.value = '';
                    if (h) h.value = '';
                    if (m) m.value = '';
                    if (c) c.value = '#000000';
                    if (s) s.checked = true;

                    this.debounceTrigger();
                });
            }

            // Cleanup on hide
            el.addEventListener('hidden.bs.offcanvas', () => {
                this.currentCallback = null;
                document.getElementById('global-search-context').style.display = 'none';
            });

            this.fetchMaterials();
        }
    },

    /**
     * Open the search UI.
     * @param {Object} options - Configuration overrides e.g. { mode: 'select', callback: fn }
     */
    open(options = {}) {
        if (!this.offcanvas) this.init();

        // Refresh materials dynamically just in case new ones appeared while closed
        this.fetchMaterials();

        // Only clear the UI if there is truly no state being held
        const queryInput = document.getElementById('global-search-query');
        const colorInput = document.getElementById('global-search-color-hex');
        const matInput = document.getElementById('global-search-material');
        const hasState = queryInput.value || colorInput.value || matInput.value;

        if (!hasState) {
            document.getElementById('global-search-in-stock').checked = true;

            const resBox = document.getElementById('global-search-results');
            resBox.innerHTML = `
                <div class="text-center text-muted mt-5">
                    <h1 class="opacity-25 mb-3">💬</h1>
                    <p>Type to search your Spoolman inventory.</p>
                </div>
            `;
        }

        const ctxNode = document.getElementById('global-search-context');
        if (options.callback) {
            this.currentCallback = options.callback;
            ctxNode.innerText = "Select a spool to insert it into the form.";
            ctxNode.classList.remove('text-muted');
            ctxNode.classList.add('text-warning');
            ctxNode.style.display = 'block';
        } else {
            this.currentCallback = null;
            ctxNode.style.display = 'none';
        }

        this.offcanvas.show();
        // Auto-focus search box
        setTimeout(() => document.getElementById('global-search-query').focus(), 400);
    },

    debounceTrigger() {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => this.executeSearch(), 300);
    },

    async executeSearch() {
        const query = document.getElementById('global-search-query').value.trim();
        const material = document.getElementById('global-search-material').value;
        const colorHex = document.getElementById('global-search-color-hex').value.trim();
        const inStock = document.getElementById('global-search-in-stock').checked;
        const tgtTypeNode = document.querySelector('input[name="global-search-type"]:checked');
        const targetType = tgtTypeNode ? tgtTypeNode.value : 'spool';

        const resBox = document.getElementById('global-search-results');

        // If nothing is typed, don't execute a massive search, just show empty state
        if (!query && !material && !colorHex) {
            resBox.innerHTML = `
                <div class="text-center text-muted mt-5">
                    <h1 class="opacity-25 mb-3">💬</h1>
                    <p>Type to search your Spoolman inventory.</p>
                </div>
            `;
            return;
        }

        resBox.innerHTML = `<div class="text-center text-info mt-4"><div class="spinner-border mb-2"></div><br><small>Searching Network...</small></div>`;

        try {
            const params = new URLSearchParams({
                q: query,
                material: material,
                hex: colorHex,
                in_stock: inStock,
                type: targetType
            });

            const response = await fetch(`/api/search?${params.toString()}`);
            const data = await response.json();

            if (!data.success) {
                resBox.innerHTML = `<div class="text-danger p-3">${data.msg}</div>`;
                return;
            }

            this.renderResults(data.results);
        } catch (e) {
            resBox.innerHTML = `<div class="text-danger p-3">Connection error: ${e.message}</div>`;
        }
    },

    renderResults(results) {
        const resBox = document.getElementById('global-search-results');

        if (!results || results.length === 0) {
            resBox.innerHTML = `
                <div class="text-center text-warning mt-5">
                    <h1 class="opacity-25 mb-3">👻</h1>
                    <p>No matching spools found.</p>
                </div>
            `;
            return;
        }

        let html = '';
        results.forEach(item => {
            // Generate Chameleon Border/Inner styles via core gradient engine
            let styles;
            try {
                styles = getFilamentStyle(item.color);
            } catch (e) {
                styles = {
                    frame: '#' + (item.color || '555555'),
                    inner: (parseInt(item.color || '555555', 16) < 0x888888) ? `rgba(255,255,255,0.15)` : `rgba(0,0,0,0.6)`,
                    border: '1px solid #333'
                };
            }

            // Format ID routing depending on if we searched a Spool or a raw Filament
            let actionTarget = "";
            let interactiveCursor = "cursor:pointer;";

            if (this.currentCallback) {
                actionTarget = `SearchEngine.selectItem(${item.id}, '${item.type}')`;
            } else {
                if (item.type === 'filament') {
                    // Clicking a filament should open its details globally
                    actionTarget = `openFilamentDetails(${item.id})`;
                } else if (window.processScan) {
                    // [CONTEXTUAL SCANNING]
                    // If the user clicks a Spool globally, pretend they scanned its Barcode!
                    // This automatically routes it to the Buffer, Drop tray, or manages it globally!
                    actionTarget = `processScan('${item.id}', 'search')`;
                } else {
                    actionTarget = `openSpoolDetails(${item.id})`;
                }
            }

            // Format Type Icon for the ID Badge
            const typeIcon = item.type === 'filament' ? '🧬' : '🧵';

            let locBadge = '';
            if (item.type === 'filament') {
                // Filaments don't have physical locations or specific weights
                locBadge = `<span class="badge bg-secondary"><i class="bi bi-box"></i> Filament Template</span>`;
                item.remaining = '---';
            } else if (item.location) {
                // [ALEX UX FIX] Deep Links: Attach an onclick event to jump to Location Manager
                const badgeClick = `event.stopPropagation(); if(window.openManage) { window.openManage('${item.location}'); SearchEngine.offcanvas.hide(); }`;
                if (item.is_ghost) locBadge = `<span class="badge bg-warning text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 Deployed: ${item.location} (Slot ${item.slot})</span>`;
                else locBadge = `<span class="badge bg-info text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 ${item.location}</span>`;
            } else {
                locBadge = `<span class="badge bg-secondary"><i class="bi bi-question-circle"></i> Unassigned</span>`;
            }

            // [EPIC 4.2] Inline Action Buttons
            let actionButtons = '';
            if (!this.currentCallback) {
                // [EPIC 4.2] Inline Action Buttons
                let actionButtons = '';
                if (!this.currentCallback) {
                    const isFil = item.type === 'filament';
                    // Properly escape double and single quotes to avoid breaking the HTML onclick attribute!
                    const safeDisplay = item.display ? item.display.replace(/"/g, '&quot;').replace(/'/g, '&#39;') : '';
                    const btnStyle = "font-size: 1.4rem; cursor:pointer; line-height: 1; opacity: 0.8;";
                    // Simple opacity swaps completely bypass Chromium's GPU Rasterizer buffer.
                    const hoverOn = "this.style.opacity='1'";
                    const hoverOff = "this.style.opacity='0.8'";

                    actionButtons = `
                    <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                        ${!isFil && window.processScan ? `<div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); processScan('${item.id}', 'search')" title="Add to Buffer/Manage">📥</div>` : ''}
                        <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); ${isFil ? `openFilamentDetails(${item.id})` : `openSpoolDetails(${item.id})`}" title="View Details">🔍</div>
                        ${!isFil && window.addToQueue ? `<div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');" title="Add to Print Queue">🖨️</div>` : ''}
                    </div>
                `;
                }

                html += `
                <div class="cham-card mb-2" style="background: ${styles.frame}; border: ${styles.border || '1px solid #333'}; cursor:pointer;" onclick="${actionTarget}">
                    <div class="cham-body p-2" style="background:${styles.inner}; display: flex; flex-direction: column; align-items: stretch;">
                        <!-- Row 1: ID, Actions, Location -->
                        <div class="d-flex justify-content-between align-items-center mb-1 w-100">
                            <div class="d-flex align-items-center gap-3">
                                <div class="text-pop d-flex align-items-center gap-1 fs-5" style="font-family:monospace; color:#fff; background: rgba(0,0,0,0.5); padding: 2px 6px; border-radius: 6px;">
                                    <span>${typeIcon}</span><span>#${item.id}</span>
                                </div>
                                ${actionButtons}
                            </div>
                            <div>
                                ${locBadge}
                            </div>
                        </div>
                        <!-- Row 2: Name -->
                        <div class="d-flex justify-content-start text-start my-2 w-100">
                             <div class="text-pop" style="font-weight:900; color:#fff; font-size:1.4rem; line-height: 1.2; word-break: break-all;">${item.display}</div>
                        </div>
                        <!-- Row 3: Weight -->
                        <div class="d-flex justify-content-end align-items-end mt-auto pt-1 w-100">
                             <div class="text-pop text-nowrap" style="font-weight:bold; color:#fff; font-size: 1.2rem;"><i class="bi bi-mask"></i> ⚖️ ${item.remaining}g</div>
                        </div>
                    </div>
                </div>
            `;
            });

        resBox.innerHTML = html;
    },

    selectItem(id, type) {
        if (this.currentCallback) {
            this.currentCallback(id, type);
            this.offcanvas.hide();
        }
    },

    // Dynamically fetches unique materials from backend and populates the dropdown gracefully
    async fetchMaterials() {
        try {
            const response = await fetch('/api/materials');
            const data = await response.json();
            if (data.success && data.materials) {
                const select = document.getElementById('global-search-material');
                if (!select) return;

                const currentVal = select.value;
                const currentOpts = Array.from(select.options).map(o => o.value).filter(v => v !== "");
                const newOpts = data.materials;

                // Only redraw if options have structurally changed to prevent interrupting user state
                if (JSON.stringify(currentOpts) !== JSON.stringify(newOpts)) {
                    let opts = `<option value="">Any Mat</option>`;
                    newOpts.forEach(m => {
                        opts += `<option value="${m}">${m}</option>`;
                    });

                    select.innerHTML = opts;
                    // Retain previously selected value if it still exists
                    if (newOpts.includes(currentVal)) {
                        select.value = currentVal;
                    } else {
                        select.value = "";
                    }
                }
            }
        } catch (e) {
            console.error("Failed to fetch materials:", e);
        }
    }
};

window.SearchEngine = SearchEngine;

document.addEventListener('DOMContentLoaded', () => {
    SearchEngine.init();
});
