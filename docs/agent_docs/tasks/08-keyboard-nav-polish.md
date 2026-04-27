# Group 8: Keyboard Navigation & Dialog Polish

**Branch name:** `feature/keyboard-nav-polish`
**Estimated effort:** ~3 hours
**Risk:** Low — UX polish, no data-layer changes

## Goal

Audit and implement consistent keyboard navigation across all interactive UI elements.

## Items to Complete

### 8.1 — Keyboard navigation audit
**Buglist ref:** L88
**What:** Only force-location modal and wizard dropdowns support arrow keys/Enter/Escape. Every modal, dropdown, list, and interactive element needs unified keyboard patterns.

**Reference implementations:**
- Force Location modal: `#fcc-escape-confirm-overlay` pattern
- Quick-Swap grid: arrow keys + `.kb-active` class + Enter confirm
- Shortcuts registry: `inventory-hub/static/js/modules/shortcuts_registry.js`

**Keyboard pattern to implement everywhere:**
- Arrow keys: navigate between focusable items (wraps at edges)
- Enter: select/confirm
- Escape: dismiss/go back
- Tab: move between controls
- Auto-focus primary input when modal opens

**Files to audit:**
- All modals in `inventory-hub/templates/components/modals_*.html`
- All JS modules in `inventory-hub/static/js/modules/`

**Acceptance criteria:**
- [ ] Every modal auto-focuses its primary input on open
- [ ] Every dropdown supports arrow key navigation
- [ ] Escape dismisses the topmost modal/overlay
- [ ] All new shortcuts registered via `registerShortcut()`

### 8.2 — Missing spool weight dialog Enter key
**Buglist ref:** L46
**Note:** Also listed in Group 1. Fix here if Group 1 hasn't been done yet.

### 8.3 — "Display modal on display modal" stacking bug
**Buglist ref:** L20
**What:** Opening a filament details from within a spool details (or vice versa) may cause double-stacked modals. Needs reproduction first.

**Investigation:** Check `inv_details.js:304` interaction with silent-refresh paths at lines 386/395. Add `console.trace` wrapper around `openFilamentDetails` and `openSpoolDetails` if repro is difficult.

**Acceptance criteria:**
- [ ] Modal stacking behavior is defined (close previous? or stack with backdrop?)
- [ ] No unintended double-modal scenarios
- [ ] If stacking is intentional, z-index and backdrop are correct

## Dependencies

- None, but Group 1 may have already fixed item 8.2.
