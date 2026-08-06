/* MODULE: Draggable corner affordances + global search shortcuts
 * ---------------------------------------------------------------------------
 * Wires the two floating corner affordances to the shared drag-to-park engine
 * (draggable_pill.js → window.makeDraggablePill) and adds keyboard search.
 *
 *   • 🔍 search FAB (buglist 21.1) — the primary search affordance; Derek uses
 *     it more than the navbar SEARCH button and relies on it staying reachable
 *     over modals (z-index 1080 > Bootstrap modal 1055). Hard-anchored it covered
 *     the bottom buffer card's weight readout, so it drag-to-parks instead.
 *   • 📡 Activity-Log "N new" pill (2026-06-15) — once the FAB became draggable
 *     the hard-anchored pill looked orphaned beside it; it now drags too, sharing
 *     the same engine. Its show/hide "unseen" gate stays owned by inv_core.js —
 *     the engine never touches `display`.
 *
 * Each affordance: tap → its action, drag (>6px) → move + persist, long-press →
 * reset to a data-free default, resize → re-clamp. Also adds keyboard search —
 * Ctrl/Cmd+K and '/' (there was none before) — so "search always available"
 * doesn't depend on finding the button.
 *
 * Storage: localStorage 'fcc.fab.pos' / 'fcc.logPill.pos' = {left, bottom} px.
 * See the CLAUDE.md "User preferences (pre-Config-system)" table.
 */
(function () {
    'use strict';

    function init() {
        const mk = window.makeDraggablePill;

        // --- Draggable 🔍 search FAB ------------------------------------------
        const fab = document.getElementById('fcc-fab-search');
        if (fab && mk) {
            mk(fab, {
                key: 'fcc.fab.pos',
                size: 65,                                      // matches .fcc-fab-search box
                defaultPos: () => ({ left: 30, bottom: 30 }),  // bottom-left deck band — clear of buffer weights + WEIGH QR
                draggingClass: 'fcc-fab-dragging',
                resetToast: '🔍 Search button reset to default position',
                onTap: () => { if (window.SearchEngine && typeof window.SearchEngine.open === 'function') window.SearchEngine.open(); },
            });
        }

        // --- Draggable 📡 Activity-Log "N new" pill ---------------------------
        const logPill = document.getElementById('fcc-log-pill');
        if (logPill && mk) {
            mk(logPill, {
                key: 'fcc.logPill.pos',
                // Default ≈ today's bottom-right resting place (lifted above the
                // cmd-deck band), expressed as {left,bottom}. The pill is hidden at
                // init so its width can't be measured — use a representative
                // estimate; the engine's ResizeObserver re-clamps to the real width
                // the instant the pill first shows. Diagonally opposite the FAB.
                defaultPos: () => {
                    const w = logPill.offsetWidth || 100;
                    const onDeck = !!document.querySelector('.cmd-deck');
                    return { left: Math.max(30, window.innerWidth - w - 30), bottom: onDeck ? 260 : 110 };
                },
                fallbackW: 100,   // representative width while hidden (offsetWidth 0)
                fallbackH: 44,    // representative height while hidden
                draggingClass: 'fcc-log-pill-dragging',
                resetToast: '📡 Activity-Log pill reset to default position',
                onTap: () => { if (window.openLogPillOverlay) window.openLogPillOverlay(); },
            });
        }

        // --- Draggable 🔀 BULK MOVE armed pill (L298 follow-up) ---------------
        // Shown for exactly as long as a session is armed, so a hidden preview
        // panel can never be lost. Visibility + label are owned by
        // updateBulkMoveVisuals (inv_cmd.js); this only makes it draggable and
        // wires the tap. Parks one lane above the log pill by default.
        const bulkPill = document.getElementById('fcc-bulkmove-pill');
        if (bulkPill && mk) {
            mk(bulkPill, {
                key: 'fcc.bulkMovePill.pos',
                defaultPos: () => {
                    const w = bulkPill.offsetWidth || 150;
                    const onDeck = !!document.querySelector('.cmd-deck');
                    return { left: Math.max(30, window.innerWidth - w - 30), bottom: onDeck ? 320 : 170 };
                },
                fallbackW: 150,   // representative width while hidden (offsetWidth 0)
                fallbackH: 44,
                draggingClass: 'fcc-bulkmove-pill-dragging',
                resetToast: '🔀 Bulk-move pill reset to default position',
                onTap: () => { if (window.openBulkMovePanel) window.openBulkMovePanel({ user: true }); },
            });
        }

        // --- Keyboard: open search from anywhere (none existed before) --------
        const openSearch = () => { if (window.SearchEngine && window.SearchEngine.open) window.SearchEngine.open(); };
        // Delegates to the canonical definition in inv_core.js — this was one of
        // three identical copy-pasted closures (2026-08-03 scan-path audit).
        const scanInFlight = () => !!(window.isScanInFlight && window.isScanInFlight());
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
                e.preventDefault();
                // preventDefault alone does NOT stop the scan accumulator — that
                // is a SEPARATE document-level listener registered later (the
                // inline block in scripts.html), so '/' still landed in
                // state.scanBuffer. The next scan within the 2s window then
                // dispatched "/LOC:PM-DB-A", which fails the prefix match and
                // reports "Unknown Code" on a perfectly good label — the exact
                // L298 Shift+B incident, in a different module.
                // stopImmediatePropagation reaches it because both listeners sit
                // on `document` in the bubble phase, and ours runs first
                // (fab_drag.js is loaded before that inline block).
                e.stopImmediatePropagation();
                openSearch();
            }
        });

        if (window.registerShortcut) {
            window.registerShortcut({ id: 'global-search-key', scope: 'Global', keys: ['Ctrl/Cmd', 'K'], description: 'Open global inventory search.' });
            window.registerShortcut({ id: 'global-search-slash', scope: 'Global', keys: ['/'], description: 'Open global inventory search (when not typing / scanning).' });
            window.registerShortcut({ id: 'fab-drag', scope: 'Global', keys: ['drag 🔍'], description: 'Drag the floating search button to move it anywhere; long-press it to reset its position.' });
            window.registerShortcut({ id: 'log-pill-drag', scope: 'Global', keys: ['drag 📡'], description: 'Drag the Activity-Log pill to move it anywhere; long-press it to reset its position.' });
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
