/* MODULE: Draggable search FAB + global search shortcuts (buglist 21.1)
 * ---------------------------------------------------------------------------
 * The floating 🔍 search button is the primary search affordance — Derek uses
 * it more than the navbar SEARCH button and relies on it staying reachable over
 * modals (it wins the z-index fight: 1080 > Bootstrap modal 1055). The only
 * defect was that, hard-anchored bottom-right, it covered the bottom buffer
 * card's weight readout. Every fixed corner of this dense dashboard collides
 * with live data, so instead of hiding or re-anchoring it we make it
 * DRAG-TO-PARK with its position remembered, defaulting to a data-free corner.
 *
 *   • tap (no drag)      → open search (SearchEngine.open)
 *   • drag (>6px)        → move it; position persisted to localStorage
 *   • long-press (650ms) → reset to the safe default (bottom-left deck band)
 *   • resize             → re-clamp so it can never strand off-screen
 *
 * Also adds keyboard search — Ctrl/Cmd+K and '/' (there was none before) — so
 * "search always available" doesn't depend on finding the button. Pointer
 * Events unify mouse + touch + stylus in one path; touch-action:none (CSS) lets
 * the drag own touch instead of the browser scrolling.
 *
 * Storage: localStorage 'fcc.fab.pos' = {left, bottom} distances in px. See the
 * CLAUDE.md "User preferences (pre-Config-system)" table.
 */
(function () {
    'use strict';

    const KEY = 'fcc.fab.pos';
    const SIZE = 65;            // matches .fcc-fab-search width/height
    const MARGIN = 8;           // keep at least this far from any viewport edge
    const DRAG_THRESHOLD = 6;   // px of movement before a press is a drag, not a click
    const LONGPRESS_MS = 650;   // hold still this long → reset to default

    function init() {
        const fab = document.getElementById('fcc-fab-search');
        if (!fab) return;

        const def = () => ({ left: 30, bottom: 30 }); // bottom-left deck band — clear of buffer weights + WEIGH QR
        const clamp = (p) => {
            const maxLeft = Math.max(MARGIN, window.innerWidth - SIZE - MARGIN);
            const maxBottom = Math.max(MARGIN, window.innerHeight - SIZE - MARGIN);
            return {
                left: Math.min(Math.max(Number(p.left), MARGIN), maxLeft),
                bottom: Math.min(Math.max(Number(p.bottom), MARGIN), maxBottom),
            };
        };
        const apply = (p) => {
            fab.style.left = p.left + 'px';
            fab.style.bottom = p.bottom + 'px';
            fab.style.right = 'auto';
            fab.style.top = 'auto';
        };
        const load = () => {
            try {
                const p = JSON.parse(localStorage.getItem(KEY));
                if (p && isFinite(p.left) && isFinite(p.bottom)) return clamp(p);
            } catch (_) { /* ignore malformed */ }
            return def();
        };
        const save = (p) => { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (_) { /* private mode / quota */ } };

        let pos = load();
        apply(pos);

        let down = null;        // { x, y, startLeft, startBottom }
        let moved = false;
        let longPressed = false;
        let longPressTimer = null;
        const clearLongPress = () => { if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; } };

        fab.addEventListener('pointerdown', (e) => {
            if (e.button != null && e.button !== 0) return; // primary / touch / pen only
            down = { x: e.clientX, y: e.clientY, startLeft: pos.left, startBottom: pos.bottom };
            moved = false; longPressed = false;
            try { fab.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
            fab.classList.add('fcc-fab-dragging');
            clearLongPress();
            longPressTimer = setTimeout(() => {
                if (down && !moved) {
                    longPressed = true;
                    pos = clamp(def());
                    apply(pos);
                    save(pos);
                    if (window.showToast) window.showToast('🔍 Search button reset to default position', 'info', 2500);
                }
            }, LONGPRESS_MS);
        });

        fab.addEventListener('pointermove', (e) => {
            if (!down) return;
            const dx = e.clientX - down.x, dy = e.clientY - down.y;
            if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
            moved = true; clearLongPress();
            // left grows rightward; bottom grows upward → subtract dy.
            pos = clamp({ left: down.startLeft + dx, bottom: down.startBottom - dy });
            apply(pos);
        });

        const endDrag = () => {
            if (!down) return;
            clearLongPress();
            fab.classList.remove('fcc-fab-dragging');
            const wasMoved = moved, wasLong = longPressed;
            down = null; moved = false; longPressed = false;
            if (wasLong) return;                 // long-press already reset; swallow the click
            if (wasMoved) { save(pos); return; } // a real drag → persist, don't open
            // a clean tap → open search
            if (window.SearchEngine && typeof window.SearchEngine.open === 'function') window.SearchEngine.open();
        };
        fab.addEventListener('pointerup', endDrag);
        fab.addEventListener('pointercancel', () => {
            clearLongPress();
            fab.classList.remove('fcc-fab-dragging');
            down = null; moved = false; longPressed = false;
        });

        // Keep on-screen across window resizes / kiosk rotation.
        window.addEventListener('resize', () => { pos = clamp(pos); apply(pos); });

        // --- Keyboard: open search from anywhere (none existed before) --------
        const openSearch = () => { if (window.SearchEngine && window.SearchEngine.open) window.SearchEngine.open(); };
        const scanInFlight = () => {
            const st = (typeof state !== 'undefined') ? state : window.state;
            return !!(st && typeof st.scanBuffer === 'string' && st.scanBuffer.length > 0
                && st.scanStartTime && (Date.now() - st.scanStartTime) < 500);
        };
        document.addEventListener('keydown', (e) => {
            const tag = (e.target && e.target.tagName) || '';
            const inField = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable);
            // Ctrl/Cmd+K — safe even mid-scan (a modifier combo never appears in a scan stream).
            if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) {
                e.preventDefault(); openSearch(); return;
            }
            // '/' — the common "focus search" key. Skip while typing in a field
            // or while a scan stream is in flight (Prusament URL QRs contain '/').
            if (e.key === '/' && !inField && !scanInFlight()) {
                e.preventDefault(); openSearch();
            }
        });

        if (window.registerShortcut) {
            window.registerShortcut({ id: 'global-search-key', scope: 'Global', keys: ['Ctrl/Cmd', 'K'], description: 'Open global inventory search.' });
            window.registerShortcut({ id: 'global-search-slash', scope: 'Global', keys: ['/'], description: 'Open global inventory search (when not typing / scanning).' });
            window.registerShortcut({ id: 'fab-drag', scope: 'Global', keys: ['drag 🔍'], description: 'Drag the floating search button to move it anywhere; long-press it to reset its position.' });
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
