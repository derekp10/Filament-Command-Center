# Group 3: Print Queue & Label Management

**Branch name:** `feature/print-queue-labels`
**Estimated effort:** ~2–3 hours
**Risk:** Low-Medium — print queue is a small module but label status touches scan paths

## Goal

Fix print queue state management bugs and enhance label-related workflows.

## Items to Complete

### 3.1 — Label queue doesn't notify if label already exists
**Buglist ref:** L60
**What:** Adding a location label to the print queue doesn't notify the user if that label is already queued. The notification may be a hidden toast or missing entirely.

**Files:**
- `inventory-hub/static/js/modules/inv_queue.js` — add-to-queue logic
- `inventory-hub/app.py` — `/api/print_queue` endpoint

**Acceptance criteria:**
- [ ] Attempting to add a duplicate label shows a visible toast: "Label already in queue"
- [ ] Toast type: `info`, duration: 4s

### 3.2 — Scan to update label-printed / filament-printed status
**Buglist ref:** L142–144
**What:** Scanning a spool/filament barcode should be able to update the `label_printed` status and handle Spoolman's `Reprint` field.

**Acceptance criteria:**
- [ ] Scanning a spool barcode can flip `needs_label_print` to false (label confirmed)
- [ ] Spoolman `Reprint` field set to "Yes" flags the spool for reprinting
- [ ] Activity log records the status change

### 3.3 — Add label print button to filament sample cards
**Buglist ref:** L146
**What:** Filament sample cards (the small cards shown in search results, etc.) should have a button to add that filament's label to the print queue.

**Files:**
- `inventory-hub/static/js/modules/ui_builder.js` — card builder, add print action

**Acceptance criteria:**
- [ ] Sample cards show a small print/label icon button
- [ ] Clicking adds the filament label to the print queue
- [ ] Toast confirms addition

### 3.4 — Print queue values inconsistently set to yes vs null
**Buglist ref:** L148
**What:** Some values in the print queue are "yes" while most are null. Need to clarify and fix the process that sets them.

**Investigation:** Check `/api/print_queue/mark_printed` and `/api/print_queue/set_flag` — are they writing consistent values? Is there a race with the poll loop?

**Acceptance criteria:**
- [ ] All print queue boolean fields use consistent values (true/false, not "yes"/null)
- [ ] Document the intended state machine for queue items

### 3.5 — Refresh ticks clearing the print queue / search broke
**Buglist ref:** L149
**What:** The auto-refresh polling may be clearing or resetting the print queue state. The search button in the queue also broke at some point.

**Root cause hypothesis:** This is likely the same bug as 3.4 — the poll loop re-fetches queue data and overwrites local state.

**Files:**
- `inventory-hub/static/js/modules/inv_queue.js` — poll/refresh handler
- `inventory-hub/static/js/modules/inv_search.js` — if search is integrated with queue

**Acceptance criteria:**
- [ ] Auto-refresh does NOT clear user's queue or reset filters
- [ ] Search within the print queue works correctly
- [ ] Queue state persists across poll ticks

### 3.6 — Legacy spools with ambiguous IDs — prompt user
**Buglist ref:** L145
**What:** When scanning a legacy barcode that maps to multiple spools, the system could be assigning the wrong one. Add a prompt asking the user to disambiguate or reprint a new unique label.

**Acceptance criteria:**
- [ ] Scanning a legacy barcode with >1 matching spool shows a disambiguation dialog
- [ ] Dialog lists all matching spools with identifying details
- [ ] User can pick the correct one or choose to reprint a new label
- [ ] Single-match scans continue to work without prompt

## Testing Checklist

- [ ] Add a label to queue → add same label again → verify notification
- [ ] Scan a spool barcode → verify label status updates
- [ ] Check print queue after multiple auto-refresh ticks → verify state persists
- [ ] Test search within print queue
- [ ] Scan a legacy barcode that maps to 2+ spools → verify prompt

## Dependencies

- None.
