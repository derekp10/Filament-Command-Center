# Group 56: 🎯 Deduct Accuracy

**Branch name (when started):** `feature/group-56-deduct-accuracy`
**Estimated effort:** MEDIUM (~3–6 h, 1 session) for 56.1–56.5. 56.1 + 56.2 ~2–3 h (with the trimmed fixture) · 56.3 ~1 h · 56.4 ~0.5–1 h · 56.5 ~0.5 h. 56.6 and 56.7 are gated on hardware and not in that estimate.
**Risk:** **MEDIUM.** The deduct path charges real spools. Every change in 56.1–56.5 can be checked offline on file fixtures, and the same extrusion walk feeds the run-out / swap split (Group 22.3b), so its pins must stay green or change deliberately.

> **Status: `TODO` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping").** 56.1–56.5 are ready to build: no printer and no Derek decision needed, apart from one optional call (past cancels, below). 56.6 needs a printer and a real print; 56.7 runs itself after a printer's next firmware upgrade.
> Cancelled prints charge what they really used, a completed print FCC can't read asks instead of charging 0 g, and the deduct's log lines escape their filenames.
> Code anchors were read on `dev` @ `d4b1ad7` (2026-10-25). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **56.1** | 🐞 *"Cancelled prints are under-charged because the cancel parser skips arc moves (found 2026-10-23). FCC's prefix parser (the cancel / M73 path) walks the G-code's extrusion but ignores G2 / G3 arcs. Counting them takes Derek's raccoon INDX print (whole file) from 48.43 g to 52.26 g against the slicer footer's 52.27 g, so the "~7% under the footer" on cancelled multi-tool prints is FCC's own bug, not missing printer data; a raccoon print cancelled at 50% was 1.96 g short."* **Folds in** the 📉 *"cancel-path prefix parser lands ~7% BELOW the slicer footer on a multi-tool INDX print"* item (2026-10-08), whose *"Mechanism not yet pinned"* the arcs answer. | Count `G2` / `G3` extrusion exactly as `G0` / `G1` is counted. |
| **56.2** | Same item: *"log a warning when a whole-file parse and the footer differ by more than 2% for any head (FCC's Core One fixture parses ~1.3% OVER its footer for another reason, so keep scaling / clamping to the footer too)"*. The folded item's fix shape: *"one parse pass returns the partial and the whole-file total per tool; scale the partial by footer / total per tool and clamp to the footer."* | One pass, partial + whole-file total per tool; scale and clamp to the footer; one WARNING per head over 2%. |
| **56.3** | Same item: *"a completed print whose footer can't be read opens a review instead of recording 0 g."* | Route it to a review card; never burn the ledger at 0 g. |
| **56.4** | 📋 *"Older Activity Log lines put a print's filename into the page unescaped… a filename with `<` or `&` draws wrong. Group 49's own warnings escape their names with `html.escape`; do the same where those older lines are built."* | `html.escape(filename, quote=False)` in every deduct / monitor log line. |
| **56.5** | The vestigial `fb_url` item's narrow slice (Claude's call 2026-10-19, no veto): *"the next time `print_monitor` / `print_deduct` are touched: drop the boot seed that still GETs the retired FilaBridge `/printers`… and replace the `fb_url is not None` switch in the shortfall card… with an explicit flag. Keep `get_api_urls()`'s 2-tuple."* | Done here because this group touches both files. The rest of the plumbing stays parked. |
| **56.6** _(gated)_ | 🐞 *"A print re-mapped to another head on the printer is charged to the wrong spool (found 2026-10-23). FCC charges the file's tool N to head N… The printer's metrics stream (`M334`, UDP) sends `active_extruder` every second, the PHYSICAL head on the INDX and XL, which could show both… Next step when Derek wants it: a small listener on dev, then one short re-mapped print with metrics on (needs a printer and a real print)."* | Research spike only when Derek wants it. Until then the 🛑 review's spool picker (Group 43.3) is the recovery. |
| **56.7** _(gated)_ | ⚠️ *"After a printer moves to firmware 8.0, check FCC's first completed and first cancelled deduct (noted 2026-10-23)."* Long file names in PrusaLink downloads (prod's ledger holds 8.3 names like `/usb/MAIN-B~1.BGC`), a Runout Reaction setting (FCC's run-out split keys off the pause), tool-mapping changes; *"once a reader printer writes a tag, FCC's own tag writes must add deltas, never overwrite."* | A checklist for the first deducts after an upgrade. The tag-delta rule is for [Group 60](60-phone-and-tags.md)'s write-back. |

## Decisions

- **For Derek (optional; nothing waits on it): past cancels.** Since the INDX arrived, every cancelled multi-tool print was charged a few percent short (a raccoon print cancelled at 50% was 1.96 g short). Options:
  - (a) Leave them. Weigh any spool you doubt and true it up with the weigh-out.
  - (b) Claude lists each past cancel from prod's deduct ledger (read-only) with what it likely missed, so you can weigh just those spools.
  - Default if you don't answer: (a).
- **Claude's calls (for veto when the build is shown):**
  - The 2% warning is per head and per job, a WARNING Activity Log line only. It never blocks or changes a charge.
  - The partial is scaled to the footer even after arcs are counted (the Core One fixture still parses ~1.3% over), and clamped to the footer.
  - 56.3 uses the existing recoverable "couldn't measure" review (kind `progress_unknown`), with its own wording, not a new kind of card.
  - 56.6 stays a spike: no listener ships to prod without Derek's OK (it needs a UDP port on the TrueNAS app and an on-printer "Allow the changes?" confirm).

## Today's code (anchors, `dev` @ `d4b1ad7`)

- **The prefix parser:** `prusalink_api.parse_partial_filament_usage` (`prusalink_api.py:173-306`). It handles `T<n>` (`:252-256`), `M82` / `M83` (`:257-262`), `G92` resets (`:263-274`), then counts E only on `G0` / `G1`: `re.match(r'^G[01](?![0-9])', upper)` (`:275-277`). A `G2` / `G3` arc's `E` is never counted. Absolute E uses a per-tool high-water mark (`:286-292`), relative E sums signed (`:282-285`). mm become grams through the footer's own g/mm per tool (`:209-222`), so a file with no `[g]` / `[mm]` footer parses to `{}`.
- **The footer:** `parse_footer_usage` (`prusalink_api.py:91-101`).
- **Who calls them:** `print_deduct._compute_cancel_usage` (`print_deduct.py:~985-1051`) reads the footer for a completion (`:1017-1019`) and the prefix for a cancel (`:1020-1021`). An empty map answers `no_usage` (`:1022-1027`); a cancel logs its own "weigh the spool" line there. Multi-head printers keep the tool index as the head position (`:1037-1038`). The run-out / swap split prefix-parses too (`prusalink_api.compute_segment_usage`, `:379+`, `parse_partial_filament_usage` at `:411-414`); its last segment is tied to footer minus the earlier ones, so arcs move only its boundaries.
- **The 0 g completion:** `deduct_completed_print` (`print_deduct.py:1131+`) records `grams=0` in the ledger on `no_usage` and logs "no filament usage in the footer; nothing to deduct" (`:1181-1187`). That entry makes the job "processed" for good.
- **The cancel edge** goes through `_create_pending_cancel_review` (preview and confirm); `deduct_cancelled_print` (`:1054-1128`) is the one-shot primitive the review path shares its compute with.
- **Unescaped filenames:** `'{filename}'` sits in log lines on 17 lines of `print_deduct.py` (e.g. `:560`, `:569`, `:576`, `:627`, `:964-977`, `:1118`, `:1186`, `:1267`, `:1598`, `:1740-1744`, `:1820-1836`, `:1951`) and on 10 of `print_monitor.py` (by grep; check that each one is a log line). Group 49's lines escape with `html.escape(..., quote=False)` (`stock_report.py:498`); CLAUDE.md: "Activity Log messages are HTML".
- **The fb_url slice:** the boot creds seed `_seed_printer_credentials_from_filabridge` (`print_monitor.py:1040`) still GETs FilaBridge `/printers` (`:1067`, `prusalink_api.fetch_all_filabridge_printers`, `prusalink_api.py:51`); the shortfall card's head snapshot switches on `fb_url is not None` (`print_deduct.py:683-684`, in `_stash_shortfall_review`, `:660`). (The 2026-10-19 anchors were `:1040`, `:1067` and `:666-668`.)
- **Fixtures:** `.captures/indx-raccoon-2026-10-08/` (git-ignored; the 11 MB raw `.bgcode`, the 30 MB decoded text, `purge_attrib.py`, `purge_check.py`, `fetch_racoon.py`, a README; byte-checked 2026-10-19). `tests/fixtures/sample.bgcode` is the Core One fixture that parses ~1.3% over its footer. Tests: `tests/test_partial_filament_parse.py`, `tests/test_bgcode_decode.py`, `tests/test_spool_swap_22_3b.py`, `tests/test_runout_auto_split.py` (job 1078, validated to 0.08 g on the scale).

## Design, by sub-task

### 56.1 — count arcs
- Match `G0`–`G3` (`^G[0-3](?![0-9])`, so `G28`, `G29`, `G10` etc. stay out) and take their `E` through the same absolute / relative logic.
- Derive a **trimmed fixture** from the raccoon capture that keeps arcs on every tool, some tool changes, a purge block and the footer, small enough to commit; leave the big files git-ignored. Record in its header where it came from and what it should parse to.
- Re-measure the whole raccoon file: per tool and total against the footer (expected ~52.26 g against 52.27 g).

### 56.2 — scale, clamp, warn
- One parse pass returns, per tool, the partial up to the cancel point and the whole-file total.
- Charge `partial × footer / whole`, clamped to the footer, per tool.
- When `|whole − footer| / footer` is over 2% for a head, log ONE WARNING naming the printer, the head, both numbers and the (escaped) filename.
- Check the final wipe / ram tail: the prefix's high-water E leaves it out (the comment at `print_deduct.py:994-996`), so a cancel at 99% must not end up charged more than the footer.

### 56.3 — a completion FCC can't read asks
- On `no_usage` for a completion: stash the existing recoverable "couldn't measure" review, `_stash_unresolved_review(..., progress_unknown=True)` (`print_deduct.py:1707`; "weigh the spool, or Discard"; it writes no ledger entry), instead of `record_deduct(..., grams=0)`. Its message today says the job was "replaced before a progress reading" (`:1743-1745`), so give it a reason argument and a line of its own ("its file's filament footer couldn't be read"). The ledger is written when the review is applied or dismissed, as with every other review.
- A genuinely empty footer (a print that extruded nothing) stays rare; the review lets Derek dismiss it.

### 56.4 — escape filenames
- `html.escape(filename, quote=False)` where each line is built; no change to what is stored in the ledger or the review records. A source canary over `print_deduct.py` / `print_monitor.py` (via `tests/source_family.py:read_app_family()`) can keep new lines honest.

### 56.5 — the fb_url slice
- Drop the FilaBridge pull from the boot creds seed (rows without creds stay as they are; Settings is where creds are entered). Replace the `fb_url is not None` switch with an explicit `read_heads=` flag. Keep `config_loader.get_api_urls()`'s `(sm_url, fb_url)` 2-tuple (`setup_fields.py` and ~131 test references use it). "Nothing may start the cancel-monitor daemon at import" still holds.

### 56.6 — re-mapped prints (gated; a spike)
- When Derek wants it: a small UDP listener on dev only, metrics turned on at the printer (it asks "Allow the changes?"; the setting survives a restart; a parked INDX reports no tool), one short re-mapped print, and a look at whether `active_extruder` shows the physical head. Then decide with Derek.

### 56.7 — firmware 8.0 (gated; a checklist)
- After a printer's upgrade, read its first completed and first cancelled deduct: the downloaded path (long names now), the run-out split (the Runout Reaction setting), the head mapping. Fix what breaks; write the tag-delta rule into Group 60's write-back design.

## Tests

- **Offline (`--offline`), each pin proven red on the base first:** a `G2` / `G3` arc counts in absolute and relative E, with and without spaces (`G2X10Y10I1J0E.5`); `G28` / `G29` don't count; the trimmed INDX fixture's whole-file parse sits within 0.1 g of its footer per tool; the Core One fixture still scales and clamps; a head over 2% logs exactly one WARNING; a completion with no footer stashes a review and writes no `grams: 0` ledger entry; a filename with `<b>&` renders as text in each converted log line; the boot seed makes no FilaBridge request; the shortfall card's flag.
- `test_runout_auto_split.py` and `test_spool_swap_22_3b.py` stay green, or change deliberately with the reason in the commit.
- **Browser:** only if 56.3 changes what a review card shows (`cancel_review.js`); then the cancel-review E2E with stubbed data, and the full sweep before merging (CLAUDE.md: a full run before committing anything that touches the frontend).

## Done when

- 56.1–56.5 are merged with their pins; a cancelled raccoon print at 50% charges within a few tenths of a gram of the footer's share; no completion is ever recorded at 0 g without a review; the deduct's log lines escape filenames; the boot seed no longer calls FilaBridge.
- 56.6 and 56.7 stay open until their hardware moment, and can be split out then.

## Risks

- The swap split's boundaries move with arcs: re-check job 1078's 0.08 g after the change.
- Exactly-once: 56.3 must not leave a job that neither the ledger nor a review owns (the crash window `_shortfall_card_exists` already guards).
- The trimmed fixture must keep the arcs and the footer, or the test proves nothing.
