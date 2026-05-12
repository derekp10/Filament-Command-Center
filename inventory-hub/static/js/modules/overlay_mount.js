/* MODULE: OVERLAY MOUNT — canonical helper for inline overlay surfaces (Group 15) */
//
// Replaces the ad-hoc createElement + focus-guard + escape-handler patterns
// scattered across weight_entry.js, weight_utils.js, duplicate_picker.js,
// inv_quickswap.js, and the force-location escape-confirm in inv_details.js.
// Every inline overlay should route through mountOverlay() so the next overlay
// author can't accidentally land underneath a modal, leak listeners, or break
// focus.
//
// Charter: Feature-Buglist.md L17 ("would-have-been Z-order incident #N") and
// docs/agent_docs/tasks/15-canonical-overlay-mount.md.
//
// API:
//   const handle = window.mountOverlay({
//       id: 'fcc-my-overlay',          // required
//       content: '<div>HTML or HTMLElement</div>',
//       tier: 'standard',              // 'standard' (20000) | 'confirm' (20100)
//       host: someModalElement,        // auto-cleanup on hidden.bs.modal/.offcanvas
//       backdrop: true,                // dark backdrop (default true)
//       backdropDismiss: false,        // click-outside cancels (default false)
//       focusGuard: true,              // capture-phase focusin neutralizer (default true)
//       initialFocus: '#my-input',     // selector or HTMLElement
//       onEscape: () => handle.cleanup(),  // default = handle.cleanup()
//       onBackdropClick: () => {},
//       occlude: ['select', '.fcc-offcanvas-search'],  // pointer-events:none while open
//       className: 'extra classes',    // applied to backdrop root
//   });
//   // handle = { element, panel, cleanup, setContent, id }
//
// Behaviors (each tied to a past incident — symptom checklist in CLAUDE.md):
//   - Mount target is ALWAYS document.body. 13.1 reverted mount-inside-modal in
//     89c6f39 because Bootstrap's modal subtree contains z-index, causing the
//     overlay to render below sibling modal chrome.
//   - Z-index ladder: 20000 (standard) / 20100 (confirm). Anything in the app
//     that needs to sit above a Bootstrap modal/offcanvas uses one of these.
//     Toast layer (11000) intentionally sits below — toasts shouldn't occlude
//     a confirm overlay.
//   - Focus guard: capture-phase focusin listener on document that
//     stopImmediatePropagation's events targeting the overlay subtree. Defeats
//     Bootstrap's modal _enforceFocus trap without subtree mounting.
//   - Host close cascade: if `host` is given (a Bootstrap modal or offcanvas),
//     subscribe to hidden.bs.modal / hidden.bs.offcanvas and run cleanup
//     automatically. No overlay outlives its parent.
//   - Occlusion: while open, any selector in `occlude` gets pointer-events:none
//     applied (and restored on cleanup). Buglist L233 lesson — <select> /
//     offcanvas elements under the host swallow clicks intended for overlay.
//   - Idempotent cleanup: calling cleanup() twice (or via host-close and then
//     manually) is a no-op.
//   - Mounting with an `id` that's already mounted tears down the prior
//     handle first (re-mount).

(function () {
    const Z = Object.freeze({ standard: 20000, confirm: 20100 });
    window.OVERLAY_Z = Z;

    const _registry = new Map();

    function _toElement(content) {
        if (content && content.nodeType === 1) return content;
        const tpl = document.createElement('template');
        tpl.innerHTML = String(content == null ? '' : content).trim();
        return tpl.content.firstElementChild
            || (() => { const d = document.createElement('div'); d.innerHTML = String(content || ''); return d; })();
    }

    function _applyOcclusion(selectors) {
        if (!selectors || !selectors.length) return () => {};
        const touched = [];
        selectors.forEach((sel) => {
            try {
                document.querySelectorAll(sel).forEach((el) => {
                    touched.push([el, el.style.pointerEvents]);
                    el.style.pointerEvents = 'none';
                });
            } catch (_) { /* invalid selector — ignore */ }
        });
        return () => touched.forEach(([el, prev]) => { el.style.pointerEvents = prev; });
    }

    function mountOverlay(opts) {
        const o = opts || {};
        const id = o.id;
        if (!id) throw new Error('mountOverlay: id is required');

        const tier = o.tier === 'confirm' ? 'confirm' : 'standard';
        const backdrop = o.backdrop !== false;
        const backdropDismiss = o.backdropDismiss === true;
        const focusGuard = o.focusGuard !== false;
        const className = o.className || '';
        const occludeList = Array.isArray(o.occlude)
            ? o.occlude
            : (typeof o.occlude === 'string' ? [o.occlude] : null);

        const existing = _registry.get(id);
        if (existing && typeof existing.cleanup === 'function') {
            existing.cleanup();
        } else {
            const stale = document.getElementById(id);
            if (stale && stale.remove) stale.remove();
        }

        const zIndex = Z[tier];

        const root = document.createElement('div');
        root.id = id;
        if (className) root.className = className;
        root.dataset.overlayMount = '1';
        root.dataset.overlayTier = tier;
        root.style.cssText = (
            'position:fixed;inset:0;'
            + 'background:' + (backdrop ? 'rgba(0,0,0,0.55)' : 'transparent') + ';'
            + 'display:flex;align-items:center;justify-content:center;'
            + 'z-index:' + zIndex + ';'
        );

        const panel = _toElement(o.content);
        root.appendChild(panel);
        document.body.appendChild(root);

        const disposers = [];
        let cleanedUp = false;

        const handle = {
            id,
            element: root,
            panel,
            tier,
            zIndex,
            cleanup,
            setContent,
        };

        if (o.onBackdropClick || backdropDismiss) {
            const onClick = (e) => {
                if (e.target !== root) return;
                if (typeof o.onBackdropClick === 'function') {
                    try { o.onBackdropClick(); } catch (_) { /* noop */ }
                } else if (backdropDismiss) {
                    cleanup();
                }
            };
            root.addEventListener('click', onClick);
            disposers.push(() => root.removeEventListener('click', onClick));
        }

        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            e.preventDefault();
            // stopImmediatePropagation prevents OTHER capture-phase listeners on
            // document (e.g. inv_loc_mgr.js's manage-modal Escape handler) from
            // also reacting — when an overlay handles Escape, the event is
            // fully consumed.
            e.stopImmediatePropagation();
            if (typeof o.onEscape === 'function') {
                try { o.onEscape(); } catch (_) { cleanup(); }
            } else {
                cleanup();
            }
        };
        document.addEventListener('keydown', onKey, true);
        disposers.push(() => document.removeEventListener('keydown', onKey, true));

        if (focusGuard) {
            const guard = (e) => {
                if (root.contains(e.target)) e.stopImmediatePropagation();
            };
            document.addEventListener('focusin', guard, true);
            disposers.push(() => document.removeEventListener('focusin', guard, true));
        }

        disposers.push(_applyOcclusion(occludeList));

        if (o.host && typeof o.host.addEventListener === 'function') {
            const onHostClose = () => cleanup();
            o.host.addEventListener('hidden.bs.modal', onHostClose);
            o.host.addEventListener('hidden.bs.offcanvas', onHostClose);
            disposers.push(() => {
                try { o.host.removeEventListener('hidden.bs.modal', onHostClose); } catch (_) { /* noop */ }
                try { o.host.removeEventListener('hidden.bs.offcanvas', onHostClose); } catch (_) { /* noop */ }
            });
        }

        function setContent(newContent) {
            const newPanel = _toElement(newContent);
            if (handle.panel && handle.panel.parentNode === root) {
                root.replaceChild(newPanel, handle.panel);
            } else {
                root.innerHTML = '';
                root.appendChild(newPanel);
            }
            handle.panel = newPanel;
            return newPanel;
        }

        function cleanup() {
            if (cleanedUp) return;
            cleanedUp = true;
            while (disposers.length) {
                const d = disposers.shift();
                try { d(); } catch (_) { /* noop */ }
            }
            try { root.remove(); } catch (_) { /* noop */ }
            if (_registry.get(id) === handle) _registry.delete(id);
        }

        _registry.set(id, handle);

        if (o.initialFocus) {
            setTimeout(() => {
                if (cleanedUp) return;
                let target = o.initialFocus;
                if (typeof target === 'string') target = root.querySelector(target);
                if (target && typeof target.focus === 'function') {
                    try { target.focus(); } catch (_) { /* noop */ }
                }
            }, 0);
        }

        return handle;
    }

    function getOverlay(id) {
        return _registry.get(id) || null;
    }

    function closeOverlay(id) {
        const h = _registry.get(id);
        if (h && typeof h.cleanup === 'function') h.cleanup();
    }

    function closeAllOverlays() {
        Array.from(_registry.values()).forEach((h) => {
            try { h.cleanup(); } catch (_) { /* noop */ }
        });
    }

    window.mountOverlay = mountOverlay;
    window.getOverlay = getOverlay;
    window.closeOverlay = closeOverlay;
    window.closeAllOverlays = closeAllOverlays;
})();
