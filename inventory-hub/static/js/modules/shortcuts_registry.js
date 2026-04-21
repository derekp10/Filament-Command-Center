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

    const _esc = (s) => String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const renderList = () => {
        const el = document.getElementById('fcc-shortcuts-list');
        if (!el) return;
        if (!shortcuts.length) {
            el.innerHTML = '<div class="text-warning fw-bold">No shortcuts registered yet.</div>';
            return;
        }
        const groups = {};
        shortcuts.forEach(s => {
            const g = s.scope || 'Global';
            if (!groups[g]) groups[g] = [];
            groups[g].push(s);
        });
        let html = '';
        Object.keys(groups).sort().forEach(scope => {
            html += `<div class="text-info fw-bold mt-3 mb-1" style="font-size:1.1rem;">${_esc(scope)}</div>`;
            html += '<table class="table table-sm table-dark mb-0" style="font-size:0.95rem;"><tbody>';
            groups[scope].forEach(s => {
                // HTML-escape the key text so things like LOC:<id> don't get parsed
                // as an <id> tag (swallowed by the browser and rendered invisibly).
                const keys = (s.keys || [])
                    .map(k => `<kbd style="background:#111; color:#0ff; font-weight:bold; padding:2px 6px;">${_esc(k)}</kbd>`)
                    .join(' ');
                html += `<tr><td style="width:38%;" class="text-light fw-bold">${keys}</td><td class="text-light">${_esc(s.description)}</td></tr>`;
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

    // Scan-command prefixes you can type into the scan input or encode on QR labels.
    window.registerShortcut({
        id: 'scan-loc', scope: 'Scan Commands',
        keys: ['LOC:<id>'],
        description: 'Open a location and drop the buffered spool there.'
    });
    window.registerShortcut({
        id: 'scan-loc-slot', scope: 'Scan Commands',
        keys: ['LOC:<id>:SLOT:<n>'],
        description: 'Drop the buffered spool into slot N of the location (auto-deploys to the bound toolhead if one is set).'
    });
    window.registerShortcut({
        id: 'scan-id', scope: 'Scan Commands',
        keys: ['ID:<n>'],
        description: 'Look up spool by Spoolman ID and add to buffer.'
    });
    window.registerShortcut({
        id: 'scan-fil', scope: 'Scan Commands',
        keys: ['FIL:<n>'],
        description: 'Open filament details for the given filament ID.'
    });
    window.registerShortcut({
        id: 'scan-leg', scope: 'Scan Commands',
        keys: ['LEG:<n>'],
        description: 'Look up a legacy / external ID.'
    });
    window.registerShortcut({
        id: 'scan-cmd-audit', scope: 'Scan Commands',
        keys: ['CMD:AUDIT'],
        description: 'Enter audit mode — scan locations to reconcile their contents.'
    });
    window.registerShortcut({
        id: 'scan-cmd-locations', scope: 'Scan Commands',
        keys: ['CMD:LOCATIONS'],
        description: 'Open the Locations manager modal.'
    });
    window.registerShortcut({
        id: 'scan-cmd-weigh', scope: 'Scan Commands',
        keys: ['CMD:WEIGH'],
        description: 'Open the Weigh-Out modal.'
    });
    window.registerShortcut({
        id: 'scan-cmd-drop', scope: 'Scan Commands',
        keys: ['CMD:DROP'],
        description: 'Toggle drop mode (scan a spool to remove it from the buffer).'
    });
    window.registerShortcut({
        id: 'scan-cmd-eject', scope: 'Scan Commands',
        keys: ['CMD:EJECT'],
        description: 'Toggle eject mode (scan a spool to send it back to its source / unassigned).'
    });
    window.registerShortcut({
        id: 'scan-cmd-ejectall', scope: 'Scan Commands',
        keys: ['CMD:EJECTALL'],
        description: 'Eject everything currently in the open location.'
    });
    window.registerShortcut({
        id: 'scan-cmd-undo', scope: 'Scan Commands',
        keys: ['CMD:UNDO'],
        description: 'Undo the last move.'
    });
    window.registerShortcut({
        id: 'scan-cmd-clear', scope: 'Scan Commands',
        keys: ['CMD:CLEAR'],
        description: 'Clear the buffer.'
    });
    window.registerShortcut({
        id: 'scan-cmd-prevnext', scope: 'Scan Commands',
        keys: ['CMD:PREV', 'CMD:NEXT'],
        description: 'Rotate through the items in the buffer.'
    });
    window.registerShortcut({
        id: 'scan-cmd-print', scope: 'Scan Commands',
        keys: ['CMD:PRINT:<n>'],
        description: 'Print a label for the given spool / filament ID.'
    });
    window.registerShortcut({
        id: 'scan-cmd-trash', scope: 'Scan Commands',
        keys: ['CMD:TRASH:<id>'],
        description: 'When managing a location, remove that item from it.'
    });
    window.registerShortcut({
        id: 'scan-cmd-done', scope: 'Scan Commands',
        keys: ['CMD:DONE'],
        description: 'Close the open location manager.'
    });
    window.registerShortcut({
        id: 'scan-cmd-slot', scope: 'Scan Commands',
        keys: ['CMD:SLOT:<n>'],
        description: 'Act on a specific slot inside the open location.'
    });
})();
