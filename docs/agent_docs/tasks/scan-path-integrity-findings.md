# 🔍 Axis (a) — Scan-Path Integrity Audit: Findings

> **Run:** 2026-08-03, workflow `wf_f39fa966-b88`. **6 agents** (4 finder lenses + **2 batched
> verifiers**), **937K tokens**, 0 agent errors, 290 tool calls, ~19 min.
> **20 raw → 18 confirmed → 2 refuted → 11 DISTINCT** after deduping (several were found
> independently by 2–3 lenses, which is corroboration, not noise).
> Read-only audit — no file was edited and the live container was never touched.
> First axis of the **codebase-wide adversarial review** item in `Feature-Buglist.md`.

**The through-line:** FCC's primary input is a barcode scanner whose keystrokes are
accumulated by a global `document` listener that begins
`if (e.target.tagName === 'INPUT') return;`. Every defect below is some variant of *something
else got between the scanner and that accumulator* — a focused field, a competing Enter
handler, a latched modal flag, or a stray character left in the buffer. None of these are
feature bugs; they are house-wide invariants with no test and no lint, which is exactly the
case the review item was filed to make.

---

## 🔴 HIGH

### 1. `state.activeModal` leaks on Escape / backdrop dismiss — silently deafens the scanner
*(F1 + F16, two independent lenses — `inv_core.js:1105-1106`)*

`requestConfirmation` / `promptSafety` set `state.activeModal`, but the **only** code that
resets it is `closeModal()`. Escape and backdrop clicks hide the Bootstrap modal without
that hop (`#confirmModal` sets neither `data-bs-keyboard="false"` nor
`data-bs-backdrop="static"`, and the `inv_loc_mgr.js:319` Escape ladder calls `inst.hide()`
directly). No `hidden.bs.modal` handler resets it anywhere.

**Consequence:** after dismissing any confirm with Escape, `inv_cmd.js:1431` swallows every
spool and location scan — **no toast, no Activity Log line, no network call.** The scanner
looks dead until reload. `CMD:` codes still work (that ladder sits above the gate), which is
why this would be maddening to diagnose. Worse, `state.pendingConfirm` is left dangling, so a
later scan containing the substring `CONFIRM` fires **the action the user just declined**.

**Reachable from:** `CMD:CLEAR` deck QR → "Clear entire Buffer?" → Escape. Also
`triggerEjectAll` and `deleteLoc`.

**Fix:** reset `state.activeModal` (and `pendingConfirm`) from a `hidden.bs.modal` handler, so
every dismissal path is covered rather than just the button path. → **FIXING**

### 2. ⚠️ The "Scan to Cancel" QR performs **CONFIRM** — safety inversion during an active print
*(F2 — `inv_quickswap.js:422-433/460/485`, plus `inv_cmd.js:1725/1748` and `inv_loc_mgr.js:1281/1304`)*

The active-print confirm overlays render a QR pair — "📷 Scan to Confirm" / "📷 Scan to
Cancel" — and separately bind a **capture-phase** `keydown` on `document` that activates
whichever button is focused. `mountOverlay`'s `initialFocus` always focuses **YES**, and the
overlay's focus guard actively keeps it there.

So the Enter that terminates *any* scan — including the CANCEL QR the overlay itself
advertises — matches `activeElement === yes`, runs `onConfirm()`, and calls
`stopPropagation()`, which (fired during document-capture) also suppresses the document-bubble
accumulator. `processScan` / `routeConfirmScan` never run; `scanBuffer` isn't even cleared.

**Consequence: scanning "CANCEL" yanks the spool off a live toolhead — the precise outcome the
confirm exists to prevent.** Any other scan made while one of these overlays is up also
silently commits the pending action. Verifier found no mitigation: no scan-in-flight guard, no
blur, and no test pins it.

**Fix:** treat Enter as button activation only when **no scan is in flight** (empty
`scanBuffer`); otherwise let it fall through to the accumulator so the QR routes properly.
Preserves keyboard use, restores the QRs. → **FIXING (3 sites)**

### 3. Weigh-Out auto-focuses a weight input in a modal that tells you to scan
*(F3 + F7 + F13, three independent lenses — `inv_weigh_out.js:130`)*

`openWeighOutModal` focuses a weight `<input>` (500 ms after a `CMD:WEIGH` scan), which
disarms the scanner for the rest of the session — in the one modal whose own instructions say
to scan. Scans can also misroute *into* a weight field and be written as a weight.

**→ HOLDING FOR DEREK.** The fix is a genuine UX trade-off, not a mechanical change:
auto-focus is legitimately useful when you intend to *type* weights, so the options are
(a) drop the auto-focus, (b) keep it but blur on the first scanner-speed keystroke, or
(c) only auto-focus when the modal was opened by mouse rather than by a `CMD:WEIGH` scan.
That's your call, not mine.

---

## 🟠 MEDIUM

| # | Finding | Disposition |
|---|---|---|
| 4 | **Quick-Swap grid Enter fires a swap on an unrelated scan's terminating Enter** (F4, `inv_quickswap.js:1205`). Press `Q` to highlight a slot, then scan a spool — you get an unrequested "Load box slot N into toolhead?" confirm, which then compounds with finding 2. | **FIXING** — same scan-in-flight guard as 2 |
| 5 | **`manualAddSpool` re-focuses `#manual-spool-id` after every add** (F8 + F15, `inv_loc_mgr.js:1503`). The modal's **own** `CMD:DONE` QR then reports "Invalid Code", as does any location or slot label. | **HOLDING** — the field's re-focus is deliberate for repeated legacy entry; which behaviour wins is your call |
| 6 | **Weigh-out "Auto-Archive 0g" checkbox never blurs** (F9 + F14, `modals_weigh_out.html:42`). Ticking it kills the scanner for the rest of the session — a verbatim re-run of the L298 bulk-move ack-box incident, in a different modal. | **FIXING** — trivial, established pattern |
| 7 | **Slot-QR scan during an active print returns `assignment_requires_confirm`, which `processScan` doesn't handle** (F17, `inv_cmd.js:1524`). User gets a yellow *"Unknown assignment result: assignment_requires_confirm"*, no dialog, no move — **forever**, since the scan path has no way to send the confirm flag. | **HOLDING** — needs a real confirm flow; that's a feature, not a patch |

---

## 🟡 LOW — all the same defect class, all mechanical

| # | Finding | Disposition |
|---|---|---|
| 8 | **`/` and `Ctrl+K` poison `scanBuffer`** (F5 + F18, `fab_drag.js:103`) — `preventDefault` without `stopImmediatePropagation` or a deferred clear. Next scan arrives as `"/LOC:PM-DB-A"` → "Unknown Code" on a valid label. | **FIXING** — the exact L298 Phase-4 pattern |
| 9 | **Wizard `Shift+E` / `Shift+C` fire mid-scan** (F6, `inv_wizard.js:579`) — no scan-in-flight guard. | **FIXING** |
| 10 | **Slot Render Order `btn-check` radios hold focus** (F10, `modals_loc_mgr.html:257`) — they *render as buttons*, so there's no visual cue that a focus-holding input is active; scans afterwards vanish with no toast. | **FIXING** — blur on change |
| 11 | **Accumulator has no Ctrl/Alt/Meta guard** (F12 + F19, `scripts.html:261`) — `Ctrl+C` to copy a location id leaves `"c"` in the buffer; the next scan becomes `"cLOC:…"` → "Unknown Code" on a good label. | **FIXING** — one line |

> ⚠️ **Do NOT add `shiftKey` to the finding-11 guard.** Barcode scanners send Shift for
> uppercase characters, so excluding Shift would break every scan. `ctrlKey || altKey ||
> metaKey` only.

---

## ✅ Refuted by the verifiers (recorded so nobody re-raises them)

- **F11** — "the legacy duplicate picker consumes every Enter, so a scan while it's open
  confirms the wrong candidate." Did not survive source reading.
- **F20** — "the 150 ms barcode-vs-keyboard heuristic silently disables label verification on
  slow scanners or under UI jank." Did not survive source reading.

---

## Notes for whoever picks up the held items

- Findings 3, 5, 7 are **held for Derek** — each is a real defect, but each fix is a product
  decision rather than a mechanical correction. Don't guess them.
- Findings 2 and 4 share one root cause (Enter-as-activation racing Enter-as-scan-terminator)
  and should stay fixed by one shared guard, not two divergent ones.
- Findings 8, 9, 11 share a root cause with the L298 Phase-4 `Shift+B` incident. If a fourth
  instance ever appears, the accumulator itself should probably expose a
  `window.suppressNextScanKey()` helper so callers stop hand-rolling this.
- The whole class would be cheaper to prevent than to find: consider a lint/test that flags a
  `document` keydown listener registered without either a scan-in-flight guard or an explicit
  opt-out comment.
