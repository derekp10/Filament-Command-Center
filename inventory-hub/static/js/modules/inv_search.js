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
            const trig = ['global-search-query', 'global-search-color-hex', 'global-search-material', 'global-search-min-weight'];
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
                    const mw = document.getElementById('global-search-min-weight');
                    const s = document.getElementById('global-search-in-stock');

                    if (q) q.value = '';
                    if (h) h.value = '';
                    if (m) m.value = '';
                    if (c) c.value = '#000000';
                    if (mw) mw.value = '';
                    if (s) s.checked = true;

                    this.debounceTrigger();
                });
            }

            const refreshBtn = document.getElementById('global-search-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.executeSearch();
                });
            }

            // Cleanup on hide
            el.addEventListener('hidden.bs.offcanvas', () => {
                this.currentCallback = null;
                document.getElementById('global-search-context').style.display = 'none';
            });

            // React to universal synchronization events (e.g. edits saved in Wizard or other UI components)
            document.addEventListener('inventory:sync-pulse', (e) => {
                // Actively intercept and locally patch DOM arrays from other modules to bypass backend network delay
                const patch = e.detail?.updatedSpool;
                if (patch && this.lastResults) {
                    let changed = false;
                    this.lastResults.forEach(r => {
                        if (parseInt(r.id) === parseInt(patch.id)) {
                            if (patch.updates.remaining_weight !== undefined) {
                                r.remaining_weight = patch.updates.remaining_weight;
                                changed = true;
                            }
                            if (patch.updates.archived !== undefined) {
                                r.archived = patch.updates.archived;
                                changed = true;
                            }
                        }
                    });
                    
                    if (changed) {
                        this.renderResults(this.lastResults);
                        return; // Stop. We fully patched the UI visually, no need to trigger a heavy API search fetch.
                    }
                }

                // Background refresh only if panel is open to save API calls
                if (this.offcanvas && el.classList.contains('show')) {
                    // Normal server refresh
                    // Only reload if we aren't showing an empty state
                    const queryInput = document.getElementById('global-search-query');
                    const colorInput = document.getElementById('global-search-color-hex');
                    const matInput = document.getElementById('global-search-material');
                    const mwInput = document.getElementById('global-search-min-weight');
                    if (queryInput.value || colorInput.value || matInput.value || mwInput.value) {
                        this.executeSearch(true); // pass true for silent search
                    }
                }
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
        const mwInput = document.getElementById('global-search-min-weight');
        const hasState = queryInput.value || colorInput.value || matInput.value || mwInput.value;

        if (!hasState) {
            document.getElementById('global-search-in-stock').checked = true;

            const resBox = document.getElementById('global-search-results');
            resBox.innerHTML = `
                <div class="text-center text-light mt-5">
                    <h1 class="opacity-25 mb-3">💬</h1>
                    <p>Type to search your Spoolman inventory.</p>
                </div>
            `;
        }

        const ctxNode = document.getElementById('global-search-context');
        if (options.callback) {
            this.currentCallback = options.callback;
            ctxNode.innerText = "Select a spool to insert it into the form.";
            ctxNode.classList.remove('text-light');
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

    async executeSearch(silent = false) {
        const query = document.getElementById('global-search-query').value.trim();
        const material = document.getElementById('global-search-material').value;
        const colorHex = document.getElementById('global-search-color-hex').value.trim();
        const minWeight = document.getElementById('global-search-min-weight').value;
        const inStock = document.getElementById('global-search-in-stock').checked;
        const tgtTypeNode = document.querySelector('input[name="global-search-type"]:checked');
        const targetType = tgtTypeNode ? tgtTypeNode.value : 'spool';

        const resBox = document.getElementById('global-search-results');

        // If nothing is typed, don't execute a massive search, just show empty state
        if (!query && !material && !colorHex && !minWeight) {
            resBox.innerHTML = `
                <div class="text-center text-light mt-5">
                    <h1 class="opacity-25 mb-3">💬</h1>
                    <p>Type to search your Spoolman inventory.</p>
                </div>
            `;
            return;
        }

        if (!silent) resBox.innerHTML = `<div class="text-center text-info mt-4"><div class="spinner-border mb-2"></div><br><small>Searching Network...</small></div>`;

        try {
            const params = new URLSearchParams({
                q: query,
                material: material,
                hex: colorHex,
                min_weight: minWeight,
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
        this.lastResults = results; // Cache locally to support zero-latency patches
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
            let callbackTarget = '';
            if (this.currentCallback) {
                callbackTarget = 'SearchEngine.selectItem';
            }
            html += window.SpoolCardBuilder.buildCard(item, 'search', { callbackFn: callbackTarget });
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
