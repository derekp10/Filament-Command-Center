# 🔁 Session Handoff — 2026-09-12 (Bulk Move manual sign-off → release)

> For a fresh context window. Supersedes [session-handoff-2026-08-06.md](session-handoff-2026-08-06.md) —
> everything it listed as open is now either merged to `dev` or re-filed below.

## ⚠️ First thing: the active-print testing report (triaged 2026-09-12)

Derek's newest buglist item — a report from testing Bulk Move during an active print — is saved
verbatim (`4c9e085`) and triaged into two entries at the top of `Feature-Buglist.md`:

- **🔴 Auto-deploy skips the toolhead during an active print, but logs success.** Code-confirmed
  (`logic.py:692-726`): the dryer-box bound-slot chain doesn't forward `confirm_active_print`, and
  both the ⚡ log and `auto_deployed_to` ignore the chained result. The most concrete fix in the
  queue — pin it with a hermetic test first.
- **🔀 Remaining findings.** Slot-card eject dead after a bulk-move timeout, and a two-spools-on-one-
  toolhead eject that silently no-opped — both need repro, suspected shared cause a Bootstrap
  confirm rendering behind a still-mounted overlay — plus bulk-move discoverability polish.

**Check 4 (active print) below is still untested** — the print finished first — and on a bound box
it will hit the auto-deploy bug, so fix or account for that before judging it.

## Git state (2026-09-12)

| Ref | State |
|---|---|
| `dev` | `a6e5d21` + this handoff; pushed. **78+ commits ahead of `main`.** |
| `main` | `b49158b` (2026-07-07). **Release HELD** on Derek's Bulk Move sign-off (below). |
| Merged, not yet deleted | `feature/group-36-attribute-force-reset-data-loss`, `feature/group-38-hermeticity-residuals`, `fix/locations-json-write-lock` — local AND origin. Safe to delete on Derek's OK. |

Merged to `dev` 2026-08-13: **Group 36** (`415822b`), **Group 38** (`367e9c9`), **locations.json write
lock** (`ddbcdd9`). Group 38's acceptance bar is met — final `RUN_INTEGRATION=1` sweep
**2 failed / 2420 passed / 25 skipped**, both reds being Derek's blank-`LocationID` `TestCart` row,
kept on purpose as the Group 37.1 repro.

## 🧪 Remaining Bulk Move (L298) manual checks — Derek, on dev

**Already passed:** a row→row move and back, `CR-CT-2-R3` ⇄ `CR-TC-2-R1`.

**Starting state, verified 2026-09-12 straight from Spoolman:** `CR-TC-2` and its three rows = 0;
`CR-CT-2-R1/R2/R3` = 3 / 3 / 2; `LR-MDB-2` = 2 slots, 0 used; `CR-MDB-1` = 4 slots, 1 ghost (a
deployed spool reserving its slot); `LR-MDB-1` = 1 direct spool.
**Empty the scan buffer first** — bulk move skips any spool sitting in it.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 1 | **Undo** | `CR-CT-2-R3` → `CR-TC-2-R1`, commit, then `CMD:UNDO` | Both spools back in `CR-CT-2-R3`. Stronger version: move `LR-MDB-1`'s spool out, then undo — it must land back in the **same box AND the same slot** (Phase 0 made undo restore system-managed extras). |
| 2 | **Capacity block (D3)** | `CR-CT-2-R1` (3 spools) → `LR-MDB-2` (2 free) | The whole batch is refused with a capacity message and **nothing moves**. Only a Dryer Box can exercise this — every cart and cart-row has blank `Max Spools`. |
| 3 | **Deployed-spool skip** | `CR-MDB-1` → `CR-TC-2-R2` | The deployed spool is listed as **skipped, with a reason** — not moved. |
| 4 | **Active print** | Only while a printer is printing: a move that touches its loaded spool | An explicit in-panel confirm appears before anything moves. |

Optional quick sanity: source == destination → blocked; destination *inside* the source
(`CR-CT-2` → `CR-CT-2-R1`) → blocked; a toolhead as destination → blocked; reload the page while
armed → the 🔀 pill and session come back.

**Known, NOT a failure:** scanning a cart *parent* such as `CR-CT-2` as the source finds only its
direct spools (0) — that is Group 37.4, the cart-subtree bug. Test at row level.

**When all four pass → `dev`→`main` release** (explicit `--no-ff`), then Derek's TrueNAS prod pull.

## Open threads

- **Group 37 — location redesign** gets its own chat. The LocationID-model fork is still open. It
  carries 37.4 (cart-subtree; test against `CR-CT-2`, not `CR-CT-1`) and the note that cart-level
  spools are legacy data, not corruption. Landing 37.1 + cleaning Derek's `TestCart` row ends the
  two known sweep reds.
- **New standalone buglist items, unbuilt:** PolyDryer unattach feedback (eject gives only
  `"Ejected"`; eject mode ignores location scans), and the bulk-move empty-source dead end — build
  that one together with the Group 37 interim "N spools sit in sub-locations" preview message.
- Group 34 `PARTIAL`, Group 35 `TODO`, Group 22 `PARTIAL` (M600, blocked on data), README
  documentation item.
- **Test artifact on dev:** `CR-TC-2` + `-R1/-R2/-R3` ("Test Cart 2"). Remove once bulk-move testing
  is finished — Derek's call.

## Conventions worth carrying forward

- **pytest here is SERIAL and deterministic**, and run position ≠ alphabetical file order. Derive
  positions with `pytest --collect-only -q --offline`; a victim at position P can only be polluted by
  1..P.
- **A flake that "just needs longer" is usually a test asserting on state the app is entitled to
  change.** None of Group 38's eight members wanted a bigger timeout.
- **Derek's buglist edits are often unsaved or uncommitted when he mentions them.** Check
  `git diff`, and commit his lines separately, attributed to him.
- **Docker Desktop may not be running after a reboot.** `inventory_hub` has
  `restart: unless-stopped`, so it returns when Docker starts; otherwise
  `docker compose -f inventory-hub/docker-compose.yml up -d`.
