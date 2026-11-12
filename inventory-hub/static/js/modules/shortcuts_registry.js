// ---------------------------------------------------------------------------
// Keyboard Shortcuts Registry — single source of truth for every app-wide
// keyboard interaction. Any new shortcut added anywhere in the codebase
// should also call window.registerShortcut(...) so the `?` help overlay
// stays complete.
//
// Group 55.3: the same window is the in-app help. A dialog's help (its words,
// from help_texts.js, then the keys of its shortcut scopes) opens from the ?
// button in the dialog's header (data-fcc-help="<key>", one delegated click
// below) or from the ? key while that dialog is on top; with no dialog that has
// help on top, ? opens the full list as before. The help closes with its dialog.
// A ? button is drawn in a template's header, or by the script that draws the
// dialog (weight_entry.js's helpKey, slot_picker.js's header, confirmActivePrint's
// `help`, which by default asks window.fccHelpKeyForOverlayId).
// ---------------------------------------------------------------------------

(function () {
    const shortcuts = [];
    const helps = new Map();   // key -> one dialog's help (window.registerHelp)

    window.registerShortcut = function (shortcut) {
        // Defensive: don't double-register.
        if (!shortcut || shortcuts.some(s => s.id === shortcut.id)) return;
        shortcuts.push(shortcut);
        renderList();
    };

    // One dialog's help (Group 55.3; the words live in help_texts.js):
    //   {key, title, match, lines, scopes, sections}
    //   match: what the dialog is on screen. {modal: 'id'} a Bootstrap modal,
    //     {overlay: 'id' or ['id', ...]} a mountOverlay root, {overlayHas: 'selector'}
    //     a mountOverlay whose root is or holds a match; an entry may name several.
    //   lines: plain sentences. scopes: shortcut scopes whose keys are listed under them.
    //   sections: [{title, lines, scopes, when: 'selector'}], each shown only while
    //     an element matching `when` is on screen in the dialog (the Quick-Swap grid in
    //     a toolhead's window).
    window.registerHelp = function (entry) {
        if (!entry || !entry.key || helps.has(entry.key)) return;
        helps.set(entry.key, entry);
    };
    // Read by tests and canaries.
    window.fccHelpFor = (key) => helps.get(key) || null;
    window.fccHelpKeys = () => Array.from(helps.keys());
    // The help of a mountOverlay by its id ({overlay: ...} in its entry's `match`), or
    // null: a dialog drawn by a shared helper (inv_core.js's confirmActivePrint) shows
    // its ? button exactly where the ? key would show its help. Read when the dialog
    // opens, never while a module loads.
    window.fccHelpKeyForOverlayId = (id) => {
        if (!id) return null;
        for (const entry of helps.values()) {
            if ([].concat((entry.match || {}).overlay || []).includes(id)) return entry.key;
        }
        return null;
    };


    const _esc = (s) => String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // One scope's heading and table: the full list and a dialog's help draw them alike.
    const _scopeHtml = (scope, rows) => {
        let html = `<div class="text-info fw-bold mt-3 mb-2" style="font-size:1.25rem;">${_esc(scope)}</div>`;
        html += '<table class="table table-dark mb-0" style="font-size:1.05rem;"><tbody>';
        rows.forEach(s => {
            const keys = (s.keys || [])
                .map(k => `<kbd style="background:#111; color:#0ff; font-weight:bold; padding:3px 8px; font-size:1rem;">${_esc(k)}</kbd>`)
                .join(' ');
            html += `<tr><td style="width:38%;" class="text-light fw-bold align-middle">${keys}</td><td class="text-light align-middle">${_esc(s.description)}</td></tr>`;
        });
        html += '</tbody></table>';
        return html;
    };

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
            html += _scopeHtml(scope, groups[scope]);
        });
        el.innerHTML = html;
    };

    // What the window shows (Group 55.3): the full list ('all') or one dialog's help
    // ('dialog'). `ctx` is the dialog the help was opened for, {entry, el}; it stays
    // set while the full list is shown from that help, so the window closes with that
    // dialog either way, and "← Back" can return to it.
    let view = 'all';
    let ctx = null;
    let _titleAll = null;
    let _footAll = null;
    const _overlay = () => document.getElementById('fcc-shortcuts-overlay');
    const _isUp = () => { const ov = _overlay(); return !!ov && ov.style.display === 'block'; };

    const _kbd = (k) => `<kbd style="background:#111; color:#0ff; font-weight:bold; padding:2px 6px;">${k}</kbd>`;

    function _linesHtml(lines) {
        const list = (lines || []).filter((l) => typeof l === 'string' && l.trim());
        if (!list.length) return '';
        return '<ul class="fcc-help-lines">' + list.map((l) => `<li>${_esc(l)}</li>`).join('') + '</ul>';
    }

    // A section's `when` is on screen: in the dialog's own element first, then anywhere
    // (a question a window raised is an overlay of its own, outside the window).
    function _sectionShows(sec, el) {
        if (!sec.when) return true;
        let hit = null;
        try {
            hit = ((el && el.isConnected) ? el.querySelector(sec.when) : null) || document.querySelector(sec.when);
        } catch (_) { return false; }
        return !!hit && hit.getClientRects().length > 0;
    }

    function _helpHtml(c) {
        const e = c.entry;
        let html = _linesHtml(e.lines);
        const scopes = [].concat(e.scopes || []);
        (e.sections || []).forEach((sec) => {
            if (!_sectionShows(sec, c.el)) return;
            html += `<div class="fcc-help-sub">${_esc(sec.title || '')}</div>` + _linesHtml(sec.lines);
            [].concat(sec.scopes || []).forEach((sc) => { if (!scopes.includes(sc)) scopes.push(sc); });
        });
        scopes.forEach((sc) => {
            const rows = shortcuts.filter((s) => (s.scope || 'Global') === sc);
            if (rows.length) html += _scopeHtml(sc, rows);
        });
        html += '<div class="mt-3"><button type="button" class="btn btn-outline-info fw-bold" data-fcc-help-all>'
            + '⌨️ All shortcuts</button></div>';
        return html;
    }

    function _paint() {
        const ovNow = _overlay();
        // A switch between the help and the full list redraws the button that had the
        // keyboard: it goes to the new All shortcuts / ← Back, not to the page.
        const hadFocus = !!(ovNow && _isUp() && ovNow.contains(document.activeElement));
        renderList();  // refresh in case new shortcuts were registered post-load
        const title = document.getElementById('fcc-shortcuts-title');
        const helpEl = document.getElementById('fcc-help-view');
        const list = document.getElementById('fcc-shortcuts-list');
        const foot = document.getElementById('fcc-shortcuts-foot');
        if (title && _titleAll === null) _titleAll = title.textContent;
        if (foot && _footAll === null) _footAll = foot.innerHTML;
        const dialog = view === 'dialog' && ctx && ctx.entry;
        if (title) title.textContent = dialog ? ('❓ ' + ctx.entry.title) : _titleAll;
        if (helpEl) {
            if (dialog) {
                helpEl.innerHTML = _helpHtml(ctx);
            } else if (ctx && ctx.entry) {
                helpEl.innerHTML = '<button type="button" class="btn btn-outline-info fw-bold" data-fcc-help-back>'
                    + '← ' + _esc(ctx.entry.title) + '</button>';
            } else {
                helpEl.innerHTML = '';
            }
            helpEl.style.display = helpEl.innerHTML ? 'block' : 'none';
        }
        if (list) list.style.display = dialog ? 'none' : '';
        if (foot) {
            foot.innerHTML = dialog
                ? `Press ${_kbd('?')} for every shortcut, or ${_kbd('Esc')} to close.`
                : _footAll;
        }
        const ov = _overlay();
        if (ov) ov.scrollTop = 0;
        if (ov && hadFocus && !ov.contains(document.activeElement)) {
            const toggle = ov.querySelector('[data-fcc-help-back], [data-fcc-help-all]');
            try { (toggle || ov).focus({ preventScroll: true }); } catch (_) { /* a stub page */ }
        }
    }

    // The pointer press that opened the window, so the second press of a double click
    // (on the backdrop now where the ? button was) doesn't close it straight away.
    let _press = null;
    function _notePress(ev) {
        _press = (ev && ev.detail > 0 && typeof ev.clientX === 'number')
            ? { t: performance.now(), x: ev.clientX, y: ev.clientY,
                coarse: ev.pointerType === 'touch' || ev.pointerType === 'pen' }
            : null;
    }

    // What had the keyboard when the list opened (Group 58 re-review): a click on its ✕
    // or its backdrop takes the focus off it, and Done's question, whose keys sit on its
    // own overlay, then heard nothing, its Enter dead with its hint still saying what
    // Enter does.
    let _focusBefore = null;
    function _open(nextView, nextCtx, ev) {
        const ov = _overlay();
        if (!ov) return;
        const bd = document.getElementById('fcc-shortcuts-overlay-backdrop');
        view = nextView;
        ctx = nextCtx;
        _paint();
        if (_isUp()) return;
        _focusBefore = document.activeElement;
        _notePress(ev);
        ov.style.display = 'block';
        if (bd) bd.style.display = 'block';
        // A scan's outcome is still read over the list (global.css): its toast is 7 s
        // when it fails, and every scan outcome is owed one. The class on <body>, so a
        // toast container made later (showToast makes it on first use) is in it too.
        if (document.body) document.body.classList.add('fcc-shortcuts-up');
        // The keyboard comes with it (Group 55.3): a person's keys then land on the
        // window, not on a dialog's control nobody can see (a Quick-Weigh's Enter saved,
        // a question's Enter stored the spool), and Tab reaches its own buttons. Its
        // focus guard keeps a Bootstrap window under it from pulling the focus back;
        // _close gives it back to what had it.
        try { ov.focus({ preventScroll: true }); } catch (_) { /* a stub page */ }
    }

    // A double click's second press: under DOUBLE_PRESS_MS after the first, within 16 px
    // of it (40 for a finger or a pen). Group 58's rule.
    const DOUBLE_PRESS_MS = 700;
    function _isSecondPress(first, ev, now) {
        if (!first || !ev || typeof ev.clientX !== 'number' || now - first.t >= DOUBLE_PRESS_MS) return false;
        const r = first.coarse ? 40 : 16;
        return Math.abs(ev.clientX - first.x) <= r && Math.abs(ev.clientY - first.y) <= r;
    }

    // The click that closed the window (its ✕, its backdrop), and the second press of
    // that double click while it is being eaten (Group 55 review, R1-3 / R4-1): the second
    // press landed on whatever lay under the pointer once the window was gone, a location
    // window's Print Location Label, a picker's tile, a slot, or Bootstrap's backdrop,
    // which closed the window the help was opened over.
    let _closedBy = null;
    let _eating = 0;

    // `ev`: the click that closed it, when a pointer did. `gone`: its dialog closed, or
    // another opened over it, rather than the person closing it.
    function _close(ev, gone) {
        const ov = _overlay();
        if (!ov) return;
        const bd = document.getElementById('fcc-shortcuts-overlay-backdrop');
        const was = ctx && ctx.el;
        ov.style.display = 'none';
        if (bd) bd.style.display = 'none';
        if (document.body) document.body.classList.remove('fcc-shortcuts-up');
        view = 'all';
        ctx = null;
        _press = null;
        _closedBy = (ev && ev.detail > 0 && typeof ev.clientX === 'number')
            ? { t: performance.now(), x: ev.clientX, y: ev.clientY,
                coarse: ev.pointerType === 'touch' || ev.pointerType === 'pen' }
            : null;
        let back = _focusBefore;
        // Drawn again under the help (a list redraws on the heartbeat): the control with
        // its id now.
        if (back && !back.isConnected && back.id) back = document.getElementById(back.id);
        const now = document.activeElement;
        _focusBefore = null;
        // Only where the list left it nowhere: the ✕ (inside the list) or the page
        // (a click on the backdrop). A focus put somewhere since stays there.
        if (back && back.isConnected && back !== document.body && typeof back.focus === 'function'
            && (!now || now === document.body || ov.contains(now))) {
            back.focus();
        }
        // Said once it is closed (Group 55 review, R1-1), for a dialog that keeps a place
        // of its own for the keyboard: the weigh-out list gives it to the box the next
        // reading is for, which a redraw under the help replaced, or a scan under it moved.
        try {
            document.dispatchEvent(new CustomEvent('fcc:help-closed', { detail: { element: was || null, person: !gone } }));
        } catch (_) { /* a page without CustomEvent: nothing listens there */ }
    }

    // The title bar's ? button, the list's ✕ and its backdrop: the full list, or close.
    window.toggleShortcutsOverlay = function (ev) {
        if (_isUp()) {
            // The second press of the double click that opened it, on its ✕ (on a phone
            // the ✕ can sit within a finger's reach of the dialog's ?).
            if (_isSecondPress(_press, ev, performance.now())) return;
            _close(ev);
        } else _open('all', null, ev);
    };

    // The backdrop: a click closes the window, except the second press of the double
    // click that opened it (Group 58's rule: under 700 ms, within 16 px, 40 for a finger).
    window.fccShortcutsBackdropClick = function (ev) {
        if (_isSecondPress(_press, ev, performance.now())) return;
        _close(ev);
    };

    // The help, closed when the dialog it was opened for changes what it shows (a scan
    // under it opened another place in the location window; Group 55 review, R1-8): its
    // words, and the sections they showed, were about what was there.
    window.fccCloseHelpFor = function (el) {
        if (_isUp() && ctx && el && ctx.el === el) _close(null, true);
    };

    // The dialog that is on top and has help, or null (then ? opens the full list).
    // A mountOverlay sits above every Bootstrap modal, so the top one decides when one
    // is mounted: one without help (the audit panel, the log list) gets the full list.
    const _shownOrder = [];
    function _entryForOverlay(root) {
        for (const entry of helps.values()) {
            const m = entry.match || {};
            if ([].concat(m.overlay || []).includes(root.id)) return entry;
            if (m.overlayHas) {
                try {
                    if (root.matches(m.overlayHas) || root.querySelector(m.overlayHas)) return entry;
                } catch (_) { /* a bad selector matches nothing */ }
            }
        }
        return null;
    }
    function _entryForModal(modal) {
        for (const entry of helps.values()) {
            if ((entry.match || {}).modal === modal.id) return entry;
        }
        return null;
    }
    function _topModal() {
        const shown = Array.from(document.querySelectorAll('.modal.show'));
        if (!shown.length) return null;
        const z = (el) => parseInt(getComputedStyle(el).zIndex, 10) || 0;
        shown.sort((a, b) => (z(a) - z(b)) || (_shownOrder.indexOf(a) - _shownOrder.indexOf(b)));
        return shown[shown.length - 1];
    }
    function _helpContext() {
        if (window.Swal && typeof window.Swal.isVisible === 'function' && window.Swal.isVisible()) return null;
        const roots = Array.from(document.querySelectorAll('[data-overlay-mount="1"]'));
        if (roots.length) {
            const top = roots.find((el) => window.isTopOverlay && window.isTopOverlay(el)) || roots[roots.length - 1];
            const entry = _entryForOverlay(top);
            return entry ? { entry, el: top } : null;
        }
        const modal = _topModal();
        if (!modal) return null;
        const entry = _entryForModal(modal);
        return entry ? { entry, el: modal } : null;
    }
    // Read by tests: the help ? would open now (its key), or null for the full list.
    window.fccHelpContextKey = () => { const c = _helpContext(); return c ? c.entry.key : null; };

    // One dialog's help, from its ? button (opts.el: the dialog it sits in).
    window.openHelp = function (key, opts) {
        const o = opts || {};
        const entry = helps.get(key);
        if (!entry) { _open('all', null, o.event); return; }
        let el = o.el || null;
        if (!el) { const c = _helpContext(); if (c && c.entry === entry) el = c.el; }
        _open('dialog', { entry, el }, o.event);
    };

    // The ? key: closes the window when it is up (a dialog's help goes to the full list
    // first), else opens the help of the dialog on top, else the full list.
    function _questionMark() {
        if (_isUp()) {
            if (view === 'dialog') { view = 'all'; _paint(); }
            else _close();
            return;
        }
        const c = _helpContext();
        if (c) _open('dialog', c);
        else _open('all', null);
    }

    // The order Bootstrap modals were shown in (two shown at once: the later is on top),
    // and the help closing with the dialog it was opened for.
    document.addEventListener('show.bs.modal', (e) => {
        const i = _shownOrder.indexOf(e.target);
        if (i !== -1) _shownOrder.splice(i, 1);
        _shownOrder.push(e.target);
    });
    document.addEventListener('hidden.bs.modal', (e) => {
        const i = _shownOrder.indexOf(e.target);
        if (i !== -1) _shownOrder.splice(i, 1);
        if (_isUp() && ctx && ctx.el === e.target) _close(null, true);
    });
    // overlay_mount.js says when a mountOverlay is cleaned up (Group 55.3).
    document.addEventListener('fcc:overlay-closed', (e) => {
        const gone = e && e.detail && e.detail.element;
        if (_isUp() && ctx && gone && ctx.el === gone) _close(null, true);
    });
    // A dialog's help goes when another dialog opens over that dialog (a scan goes on
    // under the help, and a window or question it opened was drawn under the help,
    // unseen). The full list from the title bar stays up as it always has.
    document.addEventListener('show.bs.modal', (e) => {
        if (_isUp() && ctx && ctx.el !== e.target) _close(null, true);
    });
    document.addEventListener('fcc:overlay-opened', (e) => {
        const el = e && e.detail && e.detail.element;
        if (_isUp() && ctx && el && ctx.el !== el) _close(null, true);
    });
    // The help keeps the keyboard while it is up: a focus moving into it is no
    // Bootstrap window's business (its focus trap pulled the focus back to the window
    // under the help, and after a close a person's Enter pressed that window's first
    // button). mountOverlay guards its overlays the same way.
    document.addEventListener('focusin', (e) => {
        const ov = _overlay();
        if (ov && _isUp() && ov.contains(e.target)) e.stopImmediatePropagation();
    }, true);
    // Read by every dialog key handler that must stand down while the window is up.
    window.fccShortcutsUp = _isUp;

    // A press on a dialog's ? button leaves the keyboard where it was (in a weight box,
    // on a question's Just store it), so closing the help gives it back there: on the ?
    // itself, a person's next Enter opened the help again while the question's hint
    // said "Enter stores it". A ? reached by Tab keeps the keyboard, and gets it back.
    document.addEventListener('mousedown', (e) => {
        const t = e.target;
        if (e.button === 0 && t && typeof t.closest === 'function' && t.closest('[data-fcc-help]')) e.preventDefault();
    }, true);

    // The second press of the double click that closed the window (_closedBy, set by
    // _close) reaches nothing: its pointerdown, mousedown, pointerup, mouseup, click and
    // dblclick, the events Group 58's _shieldPage stops for the audit (the floating pills
    // act on pointerup). A primary press only; a click from the keyboard (detail 0) is no
    // press. Any press ends the shield: this one, or one somewhere else.
    document.addEventListener('pointerdown', (e) => {
        if (e.button > 0) return;
        const first = _closedBy;
        _closedBy = null;
        _eating = 0;
        if (_isSecondPress(first, e, performance.now())) {
            _eating = performance.now();
            e.stopImmediatePropagation();
        }
    }, true);
    ['mousedown', 'pointerup', 'mouseup', 'click', 'dblclick'].forEach((type) => {
        document.addEventListener(type, (e) => {
            if (!_eating || performance.now() - _eating > 2000) return;
            if (type === 'click' && !e.detail) return;
            if (e.button > 0) return;
            if (type !== 'pointerup') e.preventDefault();   // mousedown: the keyboard stays put
            e.stopImmediatePropagation();
            if (type === 'click') {
                const was = _eating;
                setTimeout(() => { if (_eating === was) _eating = 0; }, 0);   // and its dblclick
            }
        }, true);
    });
    document.addEventListener('pointercancel', () => { _eating = 0; }, true);

    // A dialog's ? button, and the window's own All shortcuts / ← Back.
    document.addEventListener('click', (e) => {
        const t = e.target;
        if (!t || typeof t.closest !== 'function') return;
        const all = t.closest('[data-fcc-help-all]');
        if (all) {
            e.preventDefault();
            view = 'all';
            _paint();
            return;
        }
        const back = t.closest('[data-fcc-help-back]');
        if (back) {
            e.preventDefault();
            if (ctx && ctx.entry) { view = 'dialog'; _paint(); }
            return;
        }
        const btn = t.closest('[data-fcc-help]');
        if (!btn) return;
        e.preventDefault();
        const el = btn.closest('[data-overlay-mount="1"]') || btn.closest('.modal');
        window.openHelp(btn.getAttribute('data-fcc-help'), { el, event: e });
    });

    // Bind `?` globally + `Escape` to close the overlay.
    // Capture phase so we can stopImmediatePropagation before Bootstrap's
    // modal-level Escape handler (also bound on document) fires.
    // L40 round 2 — defer-the-help mechanism. Round 1 detected `?` mid-stream
    // via state.scanBuffer + scanStartTime, but failed when the legacy QR
    // STARTED with `?` (buffer empty at capture-phase, no scanStartTime yet).
    // Round 2 schedules the help-toggle on a short timer; if any other
    // character arrives in that window we cancel — that's a scan stream,
    // not a deliberate help press. Cost is ~120ms of latency on intentional
    // `?` presses — well below human-perceptible.
    let _pendingHelpTimer = null;
    const HELP_DEFER_MS = 120;

    // What Tab can land on in the window: its ✕ and its own buttons, on screen.
    const _tabStops = (ov) => Array.from(ov.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])'))
        .filter((el) => !el.disabled && el.getClientRects().length > 0);

    document.addEventListener('keydown', (e) => {
        const ov = document.getElementById('fcc-shortcuts-overlay');
        if (!ov) return;
        const t = e.target;
        const tag = (t && t.tagName) || '';
        // A field keeps its typing, a '?' included. A checkbox holds no text: a ? on
        // it is a person's (it opened nothing, and the '?' waited in the scan buffer).
        const typing = tag === 'TEXTAREA' || (tag === 'INPUT' && String(t.type).toLowerCase() !== 'checkbox')
            || !!(t && t.isContentEditable);

        // If a deferred help-open is pending and ANY printable char (other
        // than `?` itself, which restarts the timer) arrives within the
        // window, this is a scan stream — cancel the open.
        if (_pendingHelpTimer && e.key.length === 1 && e.key !== '?') {
            clearTimeout(_pendingHelpTimer);
            _pendingHelpTimer = null;
        }

        const up = ov.style.display === 'block';
        if (e.key === '?' && typing) return;
        // While the window is up it has the keyboard (Group 55.3): what it covers holds
        // its keys, wherever the focus is (a weight box under it saved on Enter, its
        // Escape closed the dialog under the help). A scan's keys go on: scans work
        // under it. Letters and digits are a scan's too, so the hotkeys of the dialogs
        // it covers ask window.fccShortcutsUp themselves.
        if (up && e.key === 'Tab' && !e.ctrlKey && !e.altKey && !e.metaKey) {
            e.preventDefault();
            e.stopImmediatePropagation();
            const stops = _tabStops(ov);
            if (!stops.length) { ov.focus({ preventScroll: true }); return; }
            const at = stops.indexOf(document.activeElement);
            const next = at === -1 ? (e.shiftKey ? stops[stops.length - 1] : stops[0])
                : stops[(at + (e.shiftKey ? stops.length - 1 : 1)) % stops.length];
            next.focus();
            return;
        }
        if (up && (/^Arrow/.test(e.key) || ['PageUp', 'PageDown', 'Home', 'End'].includes(e.key))) {
            // The window's own scrolling, when it has the focus; nothing under it moves.
            e.stopImmediatePropagation();
            if (!ov.contains(t)) e.preventDefault();
            return;
        }
        if (up && e.key === ' ' && !(window.scanIsArriving && window.scanIsArriving())) {
            // A person's Space presses the window's own button, or scrolls it; nothing
            // under it hears it (a scan's Space is the scan's: it goes on).
            e.stopImmediatePropagation();
            if (!ov.contains(t)) e.preventDefault();
            return;
        }

        if (e.key === '?') {
            // Mid-stream `?` (round-1 path): if we're clearly in a scan,
            // yield to the scan accumulator immediately without the 120ms
            // detour. A scan still arriving, however slow the scanner: a
            // legacy Google Sheets label is a URL with a '?' after its
            // "https:" (window.scanIsArriving; Group 57 review, round 5).
            // Canonical definition lives in inv_core.js — this was one of three
            // identical copy-pasted variants (2026-08-03 scan-path audit).
            if (window.scanIsArriving ? window.scanIsArriving()
                : (window.isScanInFlight && window.isScanInFlight())) return;
            // Defer the help open — if more chars arrive within 120ms,
            // we'll cancel it above and let the scan accumulator handle
            // the `?`. The browser's default for `?` is no-op, so
            // skipping preventDefault is fine.
            if (_pendingHelpTimer) clearTimeout(_pendingHelpTimer);
            _pendingHelpTimer = setTimeout(() => {
                _pendingHelpTimer = null;
                _questionMark();
                // Nothing followed: the '?' was a person's, and so is whatever
                // is in the scan buffer with it. Left there, opening and
                // closing the list put "??" in front of the next scan and made
                // a person's next Enter in a dialog a scan of it (round 5).
                if (window.clearScanBuffer) window.clearScanBuffer();
            }, HELP_DEFER_MS);
        } else if (e.key === 'Escape' && up) {
            // Group 10.1 SC round-3 fix: Escape used to bubble to whichever
            // Bootstrap modal was open underneath the shortcuts overlay,
            // dismissing the wizard at the same time as the overlay. Stop
            // immediate propagation so neither Bootstrap nor any sibling
            // listener fires — overlay consumes Escape exclusively. Wherever
            // the focus is: in a field under the help it closed the dialog too.
            e.preventDefault();
            e.stopImmediatePropagation();
            _close();
        } else if (e.key === 'Enter' && up && !(window.enterIsAScan && window.enterIsAScan())) {
            // The list is read, not pressed through. It sits above every overlay, so a
            // person's Enter here can't be meant for what it covers, and a dialog's
            // own Enter handler would answer a question they can't see (Group 58
            // review: a Yes with the focus on it). A scan's Enter goes on: scans work
            // under the list. On the window's own button the browser still presses it
            // (no preventDefault); the dialogs under it don't hear it (a Quick-Weigh's
            // Enter saved on any Enter not on its own buttons, Group 55.3).
            if (!ov.contains(t)) e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
        }
    }, true);  // capture phase — beats Bootstrap's bubble-phase handler

    // Seed the registry with shortcuts we already know about.
    window.registerShortcut({
        id: 'help-overlay', scope: 'Global',
        keys: ['?'], description: 'Open this keyboard shortcut reference. In a window with a ? button, it opens that window\'s help first; press ? again for every shortcut. In a text box (a weight box too) it types a ?: use the window\'s ? button there.'
    });
    window.registerShortcut({
        id: 'quickswap-focus', scope: 'Quick-Swap',
        keys: ['Q'],
        description: 'Put the keyboard on the Quick-Swap grid while a toolhead\'s window is open.'
    });
    window.registerShortcut({
        id: 'arrow-nav', scope: 'Quick-Swap',
        keys: ['↑', '↓', '←', '→'],
        description: 'Move keyboard focus between slot buttons. Wraps at edges.'
    });
    window.registerShortcut({
        id: 'enter-confirm', scope: 'Quick-Swap',
        keys: ['Enter'],
        description: 'Open the swap question for the highlighted slot. On an idle toolhead it opens on Yes, swap (Enter again swaps); while its printer prints, or FCC couldn\'t check it, it opens on No, cancel.'
    });
    window.registerShortcut({
        id: 'escape-cancel', scope: 'Quick-Swap',
        keys: ['Esc'],
        description: 'Close the swap question; nothing moves.'
    });
    window.registerShortcut({
        id: 'bind-picker-unbind', scope: 'Quick-Swap',
        keys: ['Shift', 'Del'],
        description: 'In "Bind a Slot": clear the highlighted slot\'s binding.'
    });
    window.registerShortcut({
        id: 'force-loc-arrows', scope: 'Force Location',
        keys: ['↑', '↓'],
        description: 'Navigate matching locations; Enter selects, Esc prompts before closing.'
    });
    window.registerShortcut({
        id: 'weigh-entry-arrows', scope: 'Weigh window',
        keys: ['←', '→'],
        description: 'Swap between Gross / Net / Additive / Set Used modes.'
    });
    window.registerShortcut({
        id: 'weigh-entry-enter', scope: 'Weigh window',
        keys: ['Enter'],
        description: 'Save the weight update.'
    });
    window.registerShortcut({
        id: 'weigh-entry-escape', scope: 'Weigh window',
        keys: ['Esc'],
        description: 'Close without saving.'
    });
    window.registerShortcut({
        id: 'weigh-entry-set-default', scope: 'Weigh window',
        keys: ['D'],
        description: 'Make the mode you are on the one this window opens in next time.'
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
        description: 'Drop the buffered spool into slot N of the location (auto-deploys to the bound toolhead if one is set). Asks first when that toolhead runs a spool from somewhere else or its printer is printing: Load it instead / Just store it / Cancel.'
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
        description: 'Enter audit mode — scan locations to reconcile their contents. During an audit it shows the panel.'
    });
    window.registerShortcut({
        id: 'scan-cmd-bulkmove', scope: 'Scan Commands',
        keys: ['CMD:BULKMOVE'],
        description: 'Bulk move — scan a SOURCE location, then a DESTINATION, then CMD:DONE to move everything.'
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
        description: 'Eject everything unslotted in the location open in the Location Manager (ignored when none is open).'
    });
    window.registerShortcut({
        id: 'scan-cmd-undo', scope: 'Scan Commands',
        keys: ['CMD:UNDO'],
        description: 'Undo Last Move: asks first, naming the move it will reverse.'
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
        description: 'Close the open location manager, or finish an audit: it asks before moving anything.'
    });
    window.registerShortcut({
        id: 'scan-cmd-cancel', scope: 'Scan Commands',
        keys: ['CMD:CANCEL'],
        description: 'Cancel without moving anything: an active audit (safe bail; opposite of CMD:DONE), the slot picker, or the load question on screen.'
    });
    window.registerShortcut({
        id: 'scan-cmd-needlabel', scope: 'Scan Commands',
        keys: ['CMD:NEEDLABEL'],
        description: 'During an audit: the last spool found needs a label. Reading it twice marks it once.'
    });
    window.registerShortcut({
        id: 'scan-cmd-store', scope: 'Scan Commands',
        keys: ['CMD:STORE:<id>'],
        description: '"Just store it" on the load question on screen (scan its own QR): the spool goes in the slot and the toolhead is left alone.'
    });

    // Group 40.3 — the load question ("Load #57 onto XL-1?"), asked when a box
    // slot's toolhead already runs a spool from somewhere else, or its printer
    // is printing.
    window.registerShortcut({
        id: 'load-question-enter', scope: 'Load / Store Question',
        keys: ['Enter'],
        description: 'Just store it (the highlighted answer: a toolhead is never loaded by a stray Enter). With no store option, Enter cancels.'
    });
    window.registerShortcut({
        id: 'load-question-move', scope: 'Load / Store Question',
        keys: ['←', '→', 'Tab'],
        description: 'Move between Load it instead, Just store it and Cancel.'
    });
    window.registerShortcut({
        id: 'load-question-cancel', scope: 'Load / Store Question',
        keys: ['Esc'],
        description: 'Cancel: nothing moves, and the QR under Cancel does the same. A question with Load it instead or Just store it holds off other scans until it is answered; the shorter Continue Anyway question doesn\'t.'
    });
    window.registerShortcut({
        id: 'scan-cmd-slot', scope: 'Scan Commands',
        keys: ['CMD:SLOT:<n>'],
        description: 'Act on a specific slot inside the open location.'
    });

    // Drain anything registered BEFORE this module loaded. Modules above this
    // one in scripts.html (inv_cmd, inv_wizard, inv_stock, inv_loose and
    // inv_audit_find in 2026-11; tests/test_load_order_canary_js.py names them)
    // register at eval time, and their `if (window.registerShortcut)` guard
    // used to swallow the call entirely — the shortcut still worked, it was
    // just invisible in the `?` overlay. The shim at the top of scripts.html
    // queues them; this empties the queue, so nothing registers twice and
    // load order stops mattering.
    //
    // MUST be last: registerShortcut calls renderList(), which is a `const`
    // declared partway down this IIFE. Draining right after registerShortcut
    // was defined threw a temporal-dead-zone ReferenceError and wiped out
    // EVERY shortcut, including this module's own — caught by
    // test_bulk_move_shortcuts_are_listed_in_the_help_overlay.
    const _pending = window.__pendingShortcuts;
    if (Array.isArray(_pending)) {
        _pending.splice(0).forEach(s => window.registerShortcut(s));
    }
})();
