# Group 52: 🐢 Spoolman Read Load & Honest Empties

**Branch name (when started):** `feature/group-52-spoolman-read-load`
**Estimated effort:** MEDIUM (~5–9 h, 1 session). One read per heartbeat ~2–3 h · honest empties ~1–2 h · the Quick-Swap batch ~1–2 h · the extras-read retry ~1 h · tests throughout.
**Risk:** **MEDIUM.** The heartbeat feeds every open page, and the extras read guards every extras write (`update_spool`, `update_filament`, `update_vendor`).

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`) from the 🐢 spool-list item and Group 36's follow-up (1). No Derek decision needed.** Planned LAST in the bundle run with Groups 48, 49 and 51 ([bundle-2026-10-19.md](bundle-2026-10-19.md)), or as a background builder.
> How FCC reads Spoolman when Spoolman is slow: fewer whole-list reads, and "Spoolman didn't answer" instead of an empty box. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **52.1** | 🐢 Found 2026-10-13 from `hub.log`: *"FCC re-reads Spoolman's whole spool list for every Location Manager open, Quick-Swap grid box and dashboard-pulse section… After a timeout the read silently fails open to an empty list, so in daily use a slow Spoolman shows an empty box or toolhead instead of an error."* (That day's sweeps logged 8,577 five-second read timeouts; Group 45.8 already removed the per-toolhead reads.) | One spool-list read per heartbeat; the Location Manager tells "couldn't read" from "empty"; one batched read for the Quick-Swap grid. |
| **52.2** | Group 36 follow-up (1): *"The pre-merge extras read has no retry… a Spoolman blip now produces a false refusal. A retry would cut those, but it has to stay inside the `spoolman_api.requests` seam…"* | Two attempts with a short backoff, inside the seam. |
| _(note)_ | From the "🟡 Group 40 leftovers" (5): the extra full spool-list read per bound-slot scan. | Measure it; share one strict read within one move only if every strict read stays strict. |

## Decisions

- **No Derek decision.** Out of scope by design: a cross-request cache (it would show stale contents right after a move: "I scanned it and it didn't show up"). The move engine's strict reads are never fed from anything shared.

## Today's code (anchors, `dev` @ `c5c5aa6`; the backlog lines at `08c4b10`)

- **No read cache anywhere.** Every 5 s the dashboard asks for its sections (`_computePulseInclude`, `inv_core.js:2217-2237`), and `api_dashboard_pulse` (`routes_state_pulse.py:403`) does up to three whole-list reads:
  - `printer_status`: `bucket_spools_by_location` (`routes_state_pulse.py:354`);
  - the locations table, when visible: its own full read (`routes_locations.py:88`);
  - the open Location Manager: `get_spools_at_location_detailed` (`routes_state_pulse.py:296`).
- **Plus the label backlog's count, on every pulse:** each `inventory:sync-pulse` (the dashboard pulse dispatches one per tick, `inv_core.js:2326`) re-fetches `/api/print_queue/pending?filter=all` (`inv_backlog.js:215-231`), and since the 2026-10-19 backlog fix (`afdd509`) that route reads the **whole** spool list and the **whole** filament list and filters in FCC (`routes_print_queue.py:46`, `:57`, 2 s timeouts). They were always whole lists, because Spoolman ignores the `extra=` filter the route used to send. So a busy tick is up to five whole-list reads.
- **Quick-Swap grid:** one `/api/get_contents` per feeding box, strict only for single-slot boxes (`inv_quickswap.js:247-261`); each is a whole-list read.
- **Fail-open:** `get_all_spools` answers `[]` on any error (`spoolman_api.py:94-107`); `get_spools_at_location_detailed` passes it on (`spoolman_api.py:1681`); the heartbeat hands it to `_renderManagePayload` (`inv_core.js:2307-2308`), so a slow Spoolman paints an empty box. `/api/get_contents` already has a strict mode that answers 502 (`routes_locations.py:1013-1018`). `get_all_spools_strict` raises instead of answering `[]` (`spoolman_api.py:109`).
- `bucket_spools_by_location` already accepts a `spools=` list (`spoolman_api.py:1744`).
- **The extras read:** `_get_raw_extras` makes one bare `requests.get` with a 3 s timeout and answers `None` on failure (`spoolman_api.py:608-643`); `update_spool`, `update_filament` and `update_vendor` refuse the write on `None`. Its docstring records why `http_retry` was rejected: it escapes the `spoolman_api.requests` seam that 21 test files patch.

## Design, by sub-task

### 52.1a — one spool-list read per heartbeat
- Inside `api_dashboard_pulse`, read the spool list once and hand it to the locations, manage and `printer_status` sections (`spools=`). Three reads per tick become one.
- The backlog count: serve it from the same tick (count flagged spools from that list, plus one filament read), or stop re-fetching it on every pulse (e.g. only when the backlog window is open, or every Nth pulse). Builder's call; keep the count honest (the 2026-10-19 fix filters on the flag in FCC).

### 52.1b — honest empties
- The manage section and the Location Manager's open tell "couldn't read" from "empty" (a strict read, or a `read_ok` flag like the slot picker's). The page keeps its last cards and shows "Spoolman didn't answer" instead of blanking. A genuinely empty box still renders empty.

### 52.1c — one batched read for the Quick-Swap grid
- One contents call for all feeding boxes, keeping the strict read for single-slot boxes: a new route or a multi-id parameter (update `tests/test_route_table_pin.py` deliberately).

### 52.2 — retry the extras read
- Two attempts with a short backoff inside `_get_raw_extras`, calling `requests.get` from `spoolman_api` itself (not `http_retry`), so every test seam keeps intercepting.

### The bound-slot scan note
- Count the whole-list reads in one slot-label scan into a bound slot; share one strict read within that move only where every strict read stays strict.

## Tests

- Count Spoolman GETs per heartbeat with the locations table and the Location Manager open: 3 → 1 (and the backlog count's two, if moved).
- A failed read keeps the Location Manager's cards and shows the notice (Playwright, routed error); a genuinely empty box still renders empty.
- The Quick-Swap grid makes one contents request for two feeding boxes and keeps strict reads for a PolyDryer.
- `_get_raw_extras`: fails once then succeeds → the write goes through; fails twice → refused as today. Tests that count GETs are updated deliberately.

## Risks

- The section payload shapes the frontend renderers depend on.
- The retry adds up to ~3 s before a refusal.
- Test seams: keep `requests.get` resolved from `spoolman_api`.
