/* MODULE: Generic drag-to-park engine for floating corner affordances.
 * ---------------------------------------------------------------------------
 * Extracted from fab_drag.js (buglist 21.1) so more than one fixed-corner
 * affordance can share ONE engine: the 🔍 search FAB and the 📡 Activity-Log
 * "N new" pill (2026-06-15). Every fixed corner of this dense dashboard collides
 * with live data, so rather than hide/re-anchor an affordance we make it
 * drag-to-park with its position remembered.
 *
 *   • tap (no drag)      → opts.onTap()
 *   • drag (>6px)        → move it; position persisted to localStorage[opts.key]
 *   • long-press (650ms) → reset to opts.defaultPos() (+ optional toast)
 *   • resize             → re-clamp so it can never strand off-screen
 *
 * The engine writes ONLY left/bottom/right/top — NEVER `display` — so a caller
 * that toggles its element's visibility (the log pill's "unseen" gate in
 * inv_core.js) keeps full ownership of show/hide. The stored position is applied
 * on init even while the element is display:none, so it's already parked before
 * it ever flashes visible.
 *
 * Pointer Events unify mouse + touch + stylus in one path; the element needs
 * `touch-action:none` in CSS so the drag owns touch instead of the browser
 * scrolling. Stored value: localStorage[key] = {left, bottom} px from the
 * viewport's left / bottom edges. See the CLAUDE.md "User preferences
 * (pre-Config-system)" table.
 */
(function () {
    'use strict';

    const MARGIN = 8;           // keep at least this far from any viewport edge
    const DRAG_THRESHOLD = 6;   // px of movement before a press is a drag, not a click
    const LONGPRESS_MS = 650;   // hold still this long → reset to default

    /**
     * @param {HTMLElement} el  element to make draggable (no-op if falsy)
     * @param {Object} opts
     *   @param {string}   opts.key          localStorage key for {left,bottom}
     *   @param {Function} opts.defaultPos   () => ({left,bottom}) — fallback + long-press target
     *   @param {Function} [opts.onTap]      () => void — clean-tap action
     *   @param {string}   [opts.draggingClass='fcc-dragging']  class toggled during a drag
     *   @param {string}   [opts.resetToast] info-toast text shown on long-press reset
     *   @param {number}   [opts.size]       fixed box size (px) for clamping; omit to measure el live
     */
    function makeDraggablePill(el, opts) {
        if (!el || !opts || !opts.key || typeof opts.defaultPos !== 'function') return;
        const draggingClass = opts.draggingClass || 'fcc-dragging';
        // Clamp box: a fixed `size` (the FAB), else the element's live rendered
        // box. The pill varies with its count text, so measure live; while hidden
        // (offsetWidth 0) fall back to a caller `fallbackW`/`fallbackH` estimate
        // (then a conservative constant). The ResizeObserver below re-clamps to
        // the true width the moment the pill shows.
        const boxW = () => opts.size || el.offsetWidth || opts.fallbackW || 48;
        const boxH = () => opts.size || el.offsetHeight || opts.fallbackH || 48;
        // Optional w/h reuse a box measured once at pointerdown — avoids a forced
        // reflow (reading offsetWidth right after each apply() write) during a drag.
        const clamp = (p, w, h) => {
            const maxLeft = Math.max(MARGIN, window.innerWidth - (w || boxW()) - MARGIN);
            const maxBottom = Math.max(MARGIN, window.innerHeight - (h || boxH()) - MARGIN);
            return {
                left: Math.min(Math.max(Number(p.left), MARGIN), maxLeft),
                bottom: Math.min(Math.max(Number(p.bottom), MARGIN), maxBottom),
            };
        };
        const apply = (p) => {
            el.style.left = p.left + 'px';
            el.style.bottom = p.bottom + 'px';
            el.style.right = 'auto';
            el.style.top = 'auto';
        };
        const load = () => {
            try {
                const p = JSON.parse(localStorage.getItem(opts.key));
                if (p && Number.isFinite(p.left) && Number.isFinite(p.bottom)) return clamp(p);
            } catch (_) { /* ignore malformed */ }
            return clamp(opts.defaultPos());
        };
        const save = (p) => { try { localStorage.setItem(opts.key, JSON.stringify(p)); } catch (_) { /* private mode / quota */ } };

        let pos = load();
        apply(pos);   // park before first paint, even while display:none

        let down = null;        // { x, y, startLeft, startBottom }
        let moved = false;
        let longPressed = false;
        let longPressTimer = null;
        const clearLongPress = () => { if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; } };

        el.addEventListener('pointerdown', (e) => {
            if (e.button != null && e.button !== 0) return; // primary / touch / pen only
            down = { x: e.clientX, y: e.clientY, startLeft: pos.left, startBottom: pos.bottom, w: boxW(), h: boxH() };
            moved = false; longPressed = false;
            try { el.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
            el.classList.add(draggingClass);
            clearLongPress();
            longPressTimer = setTimeout(() => {
                if (down && !moved) {
                    longPressed = true;
                    pos = clamp(opts.defaultPos());
                    apply(pos);
                    save(pos);
                    if (opts.resetToast && window.showToast) window.showToast(opts.resetToast, 'info', 2500);
                }
            }, LONGPRESS_MS);
        });

        el.addEventListener('pointermove', (e) => {
            if (!down) return;
            const dx = e.clientX - down.x, dy = e.clientY - down.y;
            if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
            moved = true; clearLongPress();
            // left grows rightward; bottom grows upward → subtract dy.
            pos = clamp({ left: down.startLeft + dx, bottom: down.startBottom - dy }, down.w, down.h);
            apply(pos);
        });

        const endDrag = () => {
            if (!down) return;
            clearLongPress();
            el.classList.remove(draggingClass);
            const wasMoved = moved, wasLong = longPressed;
            down = null; moved = false; longPressed = false;
            if (wasLong) return;                 // long-press already reset; swallow the click
            if (wasMoved) { save(pos); return; } // a real drag → persist, don't fire onTap
            if (typeof opts.onTap === 'function') opts.onTap();  // a clean tap
        };
        el.addEventListener('pointerup', endDrag);
        el.addEventListener('pointercancel', () => {
            clearLongPress();
            el.classList.remove(draggingClass);
            down = null; moved = false; longPressed = false;
        });

        // Keyboard activation: pointer tap replaced the element's inline onclick,
        // so a focused affordance must still fire onTap on Enter/Space to keep
        // <button> semantics for keyboard/AT users.
        el.addEventListener('keydown', (e) => {
            if ((e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') && typeof opts.onTap === 'function') {
                e.preventDefault();
                opts.onTap();
            }
        });

        // Keep on-screen across window resizes / kiosk rotation.
        window.addEventListener('resize', () => { pos = clamp(pos); apply(pos); });

        // Re-clamp when the ELEMENT's own box changes: a display:none → visible
        // transition (offsetWidth 0 → real width) or a count-driven width change.
        // The window 'resize' handler never catches these, so a position parked
        // while hidden (measured at fallback width) is corrected the instant the
        // pill shows. apply() only writes position, never size, so this can't loop.
        if (typeof ResizeObserver !== 'undefined') {
            try {
                new ResizeObserver(() => { pos = clamp(pos); apply(pos); }).observe(el);
            } catch (_) { /* unsupported — window resize still covers viewport changes */ }
        }
    }

    window.makeDraggablePill = makeDraggablePill;
})();
