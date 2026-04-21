// ---------------------------------------------------------------------------
// Keyboard Shortcuts Registry — single source of truth for every app-wide
// keyboard interaction. Any new shortcut added anywhere in the codebase
// should also call window.registerShortcut(...) so the `?` help overlay
// stays complete.
// ---------------------------------------------------------------------------

(function () {
    const shortcuts = [];

    window.registerShortcut = function (shortcut) {
        // Defensive: don't double-register.
        if (shortcuts.some(s => s.id === shortcut.id)) return;
        shortcuts.push(shortcut);
        renderList();
    };

    const renderList = () => {
        const el = document.getElementById('fcc-shortcuts-list');
        if (!el) return;
        if (!shortcuts.length) {
            el.innerHTML = '<div class="text-muted">No shortcuts registered yet.</div>';
            return;
        }
        // Group by scope (Global, Quick-Swap, Force Location, etc.).
        const groups = {};
        shortcuts.forEach(s => {
            const g = s.scope || 'Global';
            if (!groups[g]) groups[g] = [];
            groups[g].push(s);
        });
        let html = '';
        Object.keys(groups).sort().forEach(scope => {
            html += `<div class="text-info fw-bold mt-2 mb-1">${scope}</div>`;
            html += '<table class="table table-sm table-dark mb-0"><tbody>';
            groups[scope].forEach(s => {
                const keys = (s.keys || []).map(k => `<kbd>${k}</kbd>`).join(' ');
                html += `<tr><td style="width:40%;">${keys}</td><td>${s.description}</td></tr>`;
            });
            html += '</tbody></table>';
        });
        el.innerHTML = html;
    };

    window.toggleShortcutsOverlay = function () {
        const ov = document.getElementById('fcc-shortcuts-overlay');
        if (!ov) return;
        const hidden = ov.style.display === 'none' || !ov.style.display;
        renderList();  // refresh in case new shortcuts were registered post-load
        ov.style.display = hidden ? 'block' : 'none';
    };

    // Bind `?` globally + `Escape` to close the overlay.
    document.addEventListener('keydown', (e) => {
        const ov = document.getElementById('fcc-shortcuts-overlay');
        if (!ov) return;
        // Don't hijack typing inside inputs.
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;
        if (e.key === '?') {
            e.preventDefault();
            window.toggleShortcutsOverlay();
        } else if (e.key === 'Escape' && ov.style.display === 'block') {
            window.toggleShortcutsOverlay();
        }
    });

    // Seed the registry with shortcuts we already know about.
    window.registerShortcut({
        id: 'help-overlay', scope: 'Global',
        keys: ['?'], description: 'Open this keyboard shortcut reference.'
    });
    window.registerShortcut({
        id: 'quickswap-focus', scope: 'Quick-Swap',
        keys: ['Q'],
        description: 'Focus the Quick-Swap grid when a toolhead is being managed.'
    });
    window.registerShortcut({
        id: 'arrow-nav', scope: 'Quick-Swap',
        keys: ['↑', '↓', '←', '→'],
        description: 'Move keyboard focus between slot buttons. Wraps at edges.'
    });
    window.registerShortcut({
        id: 'enter-confirm', scope: 'Quick-Swap',
        keys: ['Enter'],
        description: 'Trigger swap for the highlighted slot; then confirm overlay with Enter again.'
    });
    window.registerShortcut({
        id: 'escape-cancel', scope: 'Quick-Swap',
        keys: ['Esc'],
        description: 'Cancel the active confirm overlay.'
    });
    window.registerShortcut({
        id: 'force-loc-arrows', scope: 'Force Location Modal',
        keys: ['↑', '↓'],
        description: 'Navigate matching locations; Enter selects, Esc prompts before closing.'
    });
})();
