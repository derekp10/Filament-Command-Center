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

### 8.2 — Missing spool weight dialog Enter key  ✅ DONE
**Buglist ref:** L46
**Status:** Closed by Group 1 (`feature/weight-unification`, 2026-04-27). The post-archive empty-weight prompt (`showArchiveEmptyWeightPrompt` in `inv_details.js`) now binds Enter via a `didOpen` keydown handler with preConfirm validation. See completed-archive.md "[2026-04-27 Weight Handling Unification — Phase 1]" entry.

### 8.3 — "Display modal on display modal" stacking bug
**Buglist ref:** L20
**What:** Opening a filament details from within a spool details (or vice versa) may cause double-stacked modals. Needs reproduction first.

**Investigation:** Check `inv_details.js:304` interaction with silent-refresh paths at lines 386/395. Add `console.trace` wrapper around `openFilamentDetails` and `openSpoolDetails` if repro is difficult.

**Acceptance criteria:**
- [ ] Modal stacking behavior is defined (close previous? or stack with backdrop?)
- [ ] No unintended double-modal scenarios
- [ ] If stacking is intentional, z-index and backdrop are correct

### 8.4 — Suppress browser autofill on noisy text fields
**Buglist ref:** L146
**What:** "If possible, set certain text fields to only prompt with auto fill on some (perhaps none) fields. I think this might be a setible somewhere in the code to prevent a list of previously used values for showing up. Most of the time, this is just getting in the way for me."

**Approach:** Audit every `<input type="text">` / `<input type="search">` / `<textarea>` across the app's templates. Default policy is to suppress browser autofill suggestions on internal-state fields (location pickers, spool ID inputs, weight entries, search filters, etc.) where the dropdown of previous values is noise rather than help. Keep autofill ON only for fields where the user genuinely benefits (e.g. URL fields where pasting from history matters, free-form notes if Derek wants it).

**Recommended attribute conventions:**
- Most internal fields: `autocomplete="off"` (note: Chromium ignores this on some inputs — fall back to `autocomplete="new-password"` or a unique nonce token name when needed)
- Search/filter inputs: `autocomplete="off"` + consider `name="search-{unique}"` to avoid the browser linking history across instances
- Location ID / barcode inputs: definitely `autocomplete="off"` — these are scanner-driven, never typed
- Document the policy decisions in a short comment in `inv_wizard.js` or a CSS/template README so future fields default correctly

**Files to audit:**
- `inventory-hub/templates/components/modals_*.html` — every modal template
- `inventory-hub/templates/index.html` and other top-level pages — dashboard-level inputs
- `inventory-hub/static/js/modules/*.js` — any JS-injected `<input>` markup (location comboboxes, weight entry, duplicate picker, etc.)

**Acceptance criteria:**
- [ ] Browser autofill dropdown no longer appears on barcode/scanner inputs, location pickers, weight entries, search/filter boxes
- [ ] Verified manually in Chrome (Antigravity) — type into each affected surface and confirm no past-value dropdown surfaces
- [ ] Any field where Derek wants autofill kept ON is documented and intentionally left without `autocomplete="off"`

## Dependencies

- None. 8.2 already closed by Group 1; 8.1 / 8.3 / 8.4 can ship in any order on the same branch.
