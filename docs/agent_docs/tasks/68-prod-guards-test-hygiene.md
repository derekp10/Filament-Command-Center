# Group 68: 🛡️ Prod Guards & Test Hygiene

**Branch name (when started):** `feature/group-68-prod-guards-test-hygiene`
**Estimated effort:** LARGE (~25–40 h, 4–6 sessions, plus one review round and the full run). Estimates here have run about 30% low, so plan on the upper half. The approved row said MEDIUM (~8–12 h). Grounding put most of the work in three members: 68.7's class fix (the page fixture owning the scan buffer by default), 68.9's seven parts, and 68.10's nine canary limits (five in the load-order canary, two each in the other two) plus a contrast model. Per member, before the overrun: 68.1 ~1.5–2.5 h · 68.2 ~1.5–2 h · 68.3 ~0.25 h (once unblocked) · 68.4 ~2.5–4 h · 68.5 ~1–1.5 h · 68.6 ~1.5–2.5 h · 68.7 ~3–5 h · 68.8 ~2–3 h · 68.9 ~4–6 h · 68.10 ~6–10 h · 68.11 ~1.5–2.5 h. Claude's call (for veto): build it in two halves that can each merge on their own, the prod side first (68.1–68.6 and 68.11, ~10–16 h), then the test side (68.7–68.10, ~15–24 h).
**Risk:** **MEDIUM**, though almost nothing here changes what a person sees. The hazards are:
- prod-adjacent scripts: each is read, never run, while it is changed, and every test loads it by path with its HTTP calls recorded and never sent;
- 68.4 moves the refresh script's path guard into a shared module, and `tests/test_reset_dev.py` pins every spelling it refuses;
- 68.6 adds a switch that, set on prod, would stop every charge (prod never reads the file that sets it, and FCC says so at start whenever it is off);
- 68.7 changes every browser test's buffer at once;
- 68.10's contrast model may find real offenders, and a fix that changes a look needs Derek's picture first.

No Spoolman write surface changes, except that 68.11's field-definition writes keep what they don't mean to change.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine"). Seventh in the recommended order, after 62, 63, 64 + 65, 66 and 67. **68.3 was pulled forward:** its fix landed on `dev` that night as one commit, `e918b3f`, and ships with the next release; only the stub's removal is left here. The group opens with four questions for Derek (Decisions), asked cold and one at a time; nothing else waits on him.
> **Grounded 2026-11-17**, read-only, on `dev` @ `95531a6`. No script, app, container, Spoolman or printer was run or asked. Every member is still live except 68.3. Three parts are only partly as written:
> - **68.6's picture of dev predates dev's 2026-11-13 refresh from prod.** Dev's review cards and fetch queue were emptied that day, and its records now hold spools on the heads, so the next print end would make dev charge its own copies (still never prod).
> - **68.1's "a 200 that isn't JSON raises"** in `migrate_filament_attributes.py` holds only for JSON of the wrong shape. Since requests 2.27 (this PC has 2.32 and 2.33) a decode error is a `RequestException`, which the script catches and calls a "Network error".
> - **68.10's "no surface FCC has today relies on" an opacity:** four `global.css` rules dim text with one. Whether any falls under 4.5:1 is what the new model will show.
>
> Grounding also found siblings. Those that share code are folded in, each marked so in the list at the end (among them: FCC's own field writers drop a field's order too, 68.11; a by-hand test script leaves records on dev, 68.8; `state.py`'s log handler has no encoding, 68.9); the rest are listed there for the refresh.
> As of the local refs, `main` and `origin/main` are still `102d234`: neither `e918b3f` (68.3) nor Group 45 (`bacedf9`) is on `main` yet. **Since 2026-11-17 both are: `main` `623f2dc`, deployed to prod that day at 13:05.**
> Line numbers drift; re-grep before editing.

**Read first.** Groups 64, 65 and 67 come earlier in the order and change the same code: 64 the fetch queue, `fetch_cancel_gcode` and restart recovery (68.6's gates); 65.4 `state.py:99` (68.9's handler encoding); 67.3 and 67.5 `ensure_extra_field` and `update_extra_field_choices` (68.11). Re-ground those anchors after they land. Group 62.4 checks Force Location, a SweetAlert2 pop-up, for Tab, against whatever 11.x the CDN serves then; when 68.10 pins the library, run that check again on the pinned version.

**Related, not a member:** the 🟠 standalone "Until `dev` ships, `main` and a hotfix branch cut from it can still write prod from `pytest .`, and reset dev to June" (buglist :418). It closes when `main` has Group 45; there is nothing to build for it here. 68.1 and 68.4 make the same scripts safe on `dev`'s line for good.

## Items covered (quoted from `Feature-Buglist.md`)

The quotes are from `dev` @ `95531a6`, without their routing tags; "…" marks a cut.

| # | Buglist item | Direction |
|---|---|---|
| **68.1** 🟠 | *"Old by-hand scripts still write prod, or wipe a field, with no guard (found 2026-11-15, Group 45's write-up). `8e1f7de` ("every by-hand script refuses prod") covered three scripts in `utilities/` (`test_assignment.py`, `debug_test.py`, `repair_db_fields.py`). These have no refusal and act as soon as they start. `setup-and-rebuild/migrate_inventory.py:9` and `_backup/sync_spoolman.py:7` hard-code prod's Spoolman: `migrate_inventory.py` finds its spreadsheet by climbing to its data folder (:13-27), which exists on this PC, and adds a new set of spools for every row on each run (:337-344); `sync_spoolman.py` overwrites each matched filament's name, colours, temps and comment from its sheet (:131-163). `clean_choices.py` (repo root) DELETEs and re-creates the `filament_attributes` field (:43-46), which wipes every filament's attributes (Group 36's data loss), on config.json's Spoolman (dev here; `127.0.0.1:7912` with no config.json). `utilities/update_from_csv.py` PATCHes location, comment, archived, used weight and the whole extra dict (:95-158) to config.json's Spoolman with no dry run, never says which Spoolman it wrote, and goes around FCC's move rules (slot and trail extras stay behind). `inventory-hub-scanner-unused/scanner.py:3` posts scans, moves and undos to prod FCC. The git-ignored copies in `review-samples/2026-11-11-group55/R3-scratch/` still hold the three utilities from before the fix. `utilities/dump_spoolman.py:5` names prod too, but only reads (no timeout, no `__main__` guard). Also `setup-and-rebuild/migrate_filament_attributes.py` (a by-hand one-off with a confirm prompt) calls `r.json()` on the field list and catches only `RequestException`, so a 200 that isn't JSON raises … Fix: remove the one-time scripts (git history keeps them), or put them on `utilities/project_config.dev_spoolman_url()` and `refuse_prod_spoolman` with a dry run; delete the R3-scratch copies."* | **Live**, every script as described, with two details: the scanner's Ctrl+Z undo goes out as a GET, which the POST-only `/api/undo` refuses (its scans and moves do reach prod FCC); and `sync_spoolman.py`'s spool POSTs can't run (its filament overwrite can). **Partly true** for the last sentence: a non-JSON 200 is caught (requests 2.27+) and misnamed a "Network error"; JSON whose entries aren't objects raises. Which scripts go is Derek's Call 1. |
| **68.2** 🟠 | *"`utilities/backup_database.py` asks one Spoolman for a backup and copies another's (found 2026-11-15, Group 45's write-up). It POSTs `/api/v1/backup` to config.json's Spoolman (dev, on this PC; :11, :35-46), then copies the newest backup from the folder beside config.json's `spoolman_db_path` (:13-14, :75-103), which names prod's database … So it saves prod's last midnight-or-deploy backup as `spoolman_backup_<now>.db` and reports success with prod's spool count; the dev backup it asked for is never copied, and dev and prod copies share one folder under names that can't be told apart. Fix: back up dev or prod by name, each with its own address and share folder (nothing else reads `spoolman_db_path`, so dev's config.json can name dev's folder); check the copy against the Spoolman that was asked (spool count, highest id) before reporting success; put dev or prod and the backup's own time in the file name; add a timeout. Each POST rotates that Spoolman's six backup copies, so never run it in a loop against prod."* | **Live.** Grounding adds one catch: dev is a byte copy of prod since 2026-11-13, so a spool count and highest id can't tell their backups apart. The proof of which folder is dev's is the refresh's marker file. |
| **68.3** | *"A one-time migration still rewrites prod at every deploy (found 2026-11-15, Group 45's write-up). Its fix landed on `dev` 2026-11-16 (`e918b3f`, one commit: the stub and the line's removal, with `update.sh` now stored executable) and reaches prod with the next release. Left for Group 68: delete the stub once a deploy has run an `update.sh` without the line, and once the TrueNAS cron job is known to run the repo's `update.sh` (Derek can read its Command when he presses play; a copy kept anywhere else would still call the stub). …"* (The rest of the item describes the bug before the fix, and why the stub had to stay for one deploy.) | **Partly fixed** (`e918b3f`, checked: the stub imports nothing, `update.sh` no longer calls it, and it is stored 100755). Left: delete the stub in a release after the one that carries `e918b3f` has deployed, once Call 4 says the cron runs the repo's `update.sh`. |
| **68.4** | *"Four prod guards that share no code, and none knows prod FCC (found 2026-11-15, Group 45's write-up). `utilities/project_config.py:13-53`, `setup-and-rebuild/reset_dev.py:123-210` (a copy of the first), `setup-and-rebuild/refresh_dev_from_prod.py:170-196, :350-553` (its own, and the only one that knows prod's share paths) and `inventory-hub/tests/conftest.py:262-277, :604-612` (the port only; a port it can't read passes). They agree on port 7912 in any spelling and differ on reads, unreadable ports, host spellings and the share. None names prod FCC (port 8000 on the NAS): conftest takes `INVENTORY_HUB_URL` unchecked (:261) … `project_config.dev_spoolman_url()` reads config.json, never `DEV_SPOOLMAN_URL` … A host test's unpatched backend call goes to config.json's Spoolman, which nothing checks … `test_large_spool_weight_tracking.py` makes its spool on `DEV_SPOOLMAN_URL` but writes it through `spoolman_api.update_spool` (:74-110). Fix: one small stdlib module at the repo root (`names_prod_spoolman(url)`, `names_prod_fcc(url)`, `is_prod_share_path(path)`), loaded by path from `utilities/`, `setup-and-rebuild/` and `tests/conftest.py` and tested against one table of spellings; conftest also refuses a config.json that names prod."* | **Live**, every anchor checked. One module, `prod_guard.py`, at the repo root. |
| **68.5** | *"The dev refresh's stage folder (found 2026-11-15, Group 45's write-up). `setup-and-rebuild/refresh_dev_from_prod.py` takes a stage folder inside a temp folder without a word (it refuses only prod's share and network paths, :2571-2578), yet the folder holds the refresh's only rollback copies, `dev-spoolman-before.db` (:1341-1353) and `dev-data-before/` (every file in `inventory-hub/data/`, printer logins and `config.json.bak` included; :1813-1839), and a full copy of prod's database (`prod-spoolman.db`, :1112-1147). A temp cleaner could empty it between phases, or during the swap's in-place copy. Nothing says when it may be deleted. The default folder is named for the day the run starts (:180-181), so a phase run after midnight looks in a new, empty folder and refuses until `--stage-dir` names the old one. Fix: refuse a stage folder under TEMP, TMP or `tempfile.gettempdir()`, or a drive root; keep one default folder per run, not per day; say in the docstring and `--help` what the folder holds, and to delete it once every phase has passed and dev has run for a while."* | **Live**, every anchor exact. (In an agent session TEMP and TMP are `D:\claude-tmp`, which is where Group 45's run kept its stage folder.) |
| **68.6** | *"Dev's FCC fetches the real printers' print files too (found 2026-11-13 at the print-end hotfix's live check). Dev's FCC watches the same printers as prod, so when a print ends both FCCs download its file from the printer at the same time. INDX job 1142 … prod's charge landed at 02:23, 33 min after the end, against 20 min for job 1141's file, which prod fetched alone … Dev's own fetch finished at 03:13. Dev charges nothing real: its records have no spool on the INDX heads, so its end read is set aside as a blip and it leaves a "couldn't be deducted" card in dev's data … Dev's queue also still holds 1141's cancel fetch … Options: (a) a dev-only setting that keeps dev's FCC from downloading print files, so it still shows printer states; (b) take the printers' logins out of dev, which then shows no live printer states; (c) leave it. Recommendation: (a), when convenient."* | **Live**: dev still downloads. **Its picture of dev is out of date.** The refresh's `locations` phase emptied dev's cards and fetch queue on 2026-11-13 (both files `{}` since 18:17), and dev's records have held prod's spools on the heads since then, so dev would now charge its own copies. Derek's Call 2. |
| **68.7** 🧪 | *"Browser tests can still write dev's shared scan buffer (found 2026-11-15, Group 45's write-up). The dashboard saves its whole buffer to the server on any render not marked as the server's … Tests that write it today without owning it: `test_buglist_group21.py::test_rebuffering_clears_assigned_out_mark` (:96-108 …), `test_slot_action_modal_removed.py` (:37-67, :88-121 …) and `test_buffer_race_protection.py` (:130-136, :194-200, :251-257). Seven slot-QR tests empty dev's buffer: two on purpose, since the server reads its own buffer to choose a load or a pickup … and five for nothing … their refused scans also log ERROR lines in dev's Activity Log on every run. `conftest.with_held_spool` (:1037-1049) assumes an `ID:` scan puts the spool in the server's buffer, which it no longer does; nothing uses it, and `test_weight_setting_dispatches_events.py:105-143` clears dev's buffer on that premise. Fix: `own_the_buffer` in the three files; drop `clean_buffer` from the four refused-scan tests, and move the clear-endpoint test to the Flask test client; for the two that need an empty server buffer, skip when dev's holds anything, or answer that one scan in the page. To close the class, have the page fixture give every page its own buffer by default, with an opt-out mark for a test that means the shared one (or add the fab test's write tripwire …)."* | **Live**, every anchor checked (dev's own log shows the refused scans' lines: "❌ Slot 99 out of range for LR-MDB-1 … scan dropped", 2026-11-14). Grounding adds: the API tests' four cases already have offline twins in `tests/test_assignment_logic.py`, and one of the two visual tests doesn't own its page's buffer. |
| **68.8** 🧪 | *"Throwaway Spoolman records can outlive a plain run, and one test changes a real dev vendor (found 2026-11-15, Group 45's write-up). Tests without the integration mark make `__fcc_test_` records on dev's Spoolman whenever it answers a ping (`require_spoolman`) … Their teardown deletes them, but a killed run, or a delete that times out (`conftest.py:1770-1775` ignores the answer), leaves them, and the leftover sweep runs only with RUN_INTEGRATION (`conftest.py:1936-1942`; it runs after the first test, not before, as its docstring says). Even then it misses spools made by `throwaway_spool_with_extras` (it matches spools by comment, :1950-1954, and those have none), archived spools, vendors, and records named without the prefix ('LARGE-SPOOL-TEST', 'BACKFILL-TEST', 'BACKFILL-TEST-NO-INHERIT', 'Pytest-PLA'). `test_backfill_spool_weights.py::test_backfill_rejects_filament_without_inheritable_weight` (:101-144, no integration mark) sets dev's first vendor's empty weight to 0 on every plain run and puts it back only when it had one (:139) … Fix: run the sweep on any run that isn't `--offline` and reaches dev's Spoolman; match spools by their filament's name too (or give the fixture a comment); list with `allow_archived=true`; sweep `__fcc_test_` vendors other than the shared `__fcc_test_vendor__`; log a teardown delete that failed; give the four names the prefix; make the backfill test integration-only, on a throwaway vendor."* | **Live**, every anchor checked. Grounding adds: the backfill test zeroes the vendor *before* its `try`, so a failed filament create leaves the vendor at 0 whatever it held; "Pytest-PLA" is the wizard test's Material, and the filament it makes is named by the Colour name box, "E2E Ruby Red" (`inv_wizard.js:4236`), so that is the name an interrupted run leaves; and `tests/debug_console.py` makes the same filament and a spool on dev and never deletes them. |
| **68.9** 🧪 | (1) *"Smaller test leftovers (filed 2026-11-16 from the pre-refresh audit). (1) Group 45.9's documented gaps (CLAUDE.md, Testing): the repo-root `.config_mtime`, an unpatched `save_config` (it would write dev's real `config.json`; no test does today), `__pycache__`, and an ad-hoc `python -c "import app"` that migrates whatever `data/` its working directory holds. (2) An empty `data/` and a 0-byte `hub.log` came back at the repo root on 2026-11-13 21:47 (git-ignored), after 45.9 deleted the old ones: find what re-creates them. (3) Two ordering tests pass without testing anything on a very slow run (their 900 ms holds; Group 57 round 3). (4) Group 54's notes: `SpoolmanHTTPFake` stores `remaining_weight` as sent; `tests/roundtrip_bridge.py` fails when named on the command line; dev Spoolman reuses deleted ids; 54.4's "kept" line prints the raw wire value."* | **Live**, all four parts. (2): both strays are still there, born 2026-11-13 21:47:16 (`hub.log`) and 21:47:17 (`data/`); grounding found a likely mechanism, not the culprit (see 68.9 under Design). (3): the two tests aren't named anywhere; the most likely pair is named under Today's code. |
| | *"A host unit test reads dev's whole spool list (found 2026-11-15, Group 45's write-up). `test_buffer_ejection_logic.py::test_smart_eject_restores_home_slot` (:71) doesn't patch `spoolman_api.get_spools_at_location_detailed`, so the eject's home-slot check (`logic.py:4434`) GETs `/api/v1/spool` from config.json's Spoolman on every plain run (up to 5 s on a busy Spoolman). It passes either way … Fix: patch it with `return_value=[]`, as the two tests after it do (:130, :170)."* | **Live** (`:71`, `logic.py:4434` and the two patches checked). |
| | *"Two fixtures take their routes off a live page (found 2026-11-15, Group 45's write-up). `test_quickswap_visual.py`'s `hermetic_grid` (:129-133) and `test_audit_double_click_58_e2e.py`'s `board` (:506-513) call `unroute_all` before the page or context closes … In the gap the page's polls reach dev … Under `--screenshot` the page fixture still un-routes before pytest-playwright closes the page, which opens the same gap for every browser test. Fix: drop `hermetic_grid`'s own unroute; have `board` close its context first."* | **Live** (`:129-133`; `board`'s `finally` at `:508-513`; the page fixture's `--screenshot` order at `conftest.py:744-753`). |
| | *"Watch: the audit double-click test's try-again case can time out under load (found 2026-11-14, Group 45's busy run). … `double_click_over` (`test_audit_double_click_58_e2e.py:451-465`) waits at most 600 ms (:460) for Find's rows to appear under the pointer after the first press on ↻ Try again, whose search the test's own Python route handler answers … If it comes back, don't raise the number: when the 600 ms runs out, wait a few seconds more for the rows and, if they come, skip the case with the measured time as the reason …; fail only if they never come. Answering `/api/search` inside the page would also remove most of the delay."* | **Live** (the wait is `:460-461`, the clock check `:462`; `/api/search` is answered by Python, `:203`). |
| **68.10** | *"🟡 sweetalert2 is loaded unpinned (found 2026-11-09, Group 53.3). `scripts.html` loads `cdn.jsdelivr.net/npm/sweetalert2@11`, so the page gets whatever 11.x is current, while bootstrap is pinned to `@5.3.0`. The load-order canary's `CDN_GLOBALS` were read from the 11.x bundle current on 2026-11-09 and wouldn't notice a later 11.x changing its globals. Pin it (Derek's call)."* | **Live** (`templates/components/scripts.html:2`). Derek's Call 3. |
| | *"🧪 The three Group 53 canaries' known limits, for a later pass … the ones worth doing first: the load-order stub's queries never find an element a script built …; its tuple assertion messages are cut at 240 characters by pytest's saferepr (make them strings); a name a zero-delay timer defines is filed under the script that queued it (stricter: after the next script); its pure-Python checks (the template reader's, and every `static/js` file loaded exactly once) skip too when node is missing; the shared `NODE_MISSING_MSG` names only the CORE1 checks. The one-list canary misses a words string kept in a const and split later, and reads a regex right after `)` as a division. The write-site canary sees only three ways of throwing a result away (a tuple unpacked with its failure part ignored passes) and over-counts any `.requests` / `.http_retry` chain."* | **Live**, each one checked in the canaries' own docstrings and code. |
| | *"🎨 The contrast guard reads no `opacity` and no filter but `brightness()` (found 2026-11-02, Group 58's review). `assert_contrast` / `contrast_offenders` (tests/conftest.py) score text on its computed colours through each `filter: brightness(n)` on it and its ancestors, but not an `opacity` below 1, nor `contrast()`, `grayscale()` or the rest, so dimmed text scores as if it were drawn at full strength. No surface FCC has today relies on one (two brightness rules exist), so it is a hole in the guard, not a known offender."* | **Live.** **Partly as written:** text with an `opacity` below 1 does exist (four `global.css` rules, `.btn-buffer-x` at 0.7 among them, plus, counted 2026-11-17, 16 inline values under 1 and 6 Bootstrap `opacity-*` classes in the templates and page scripts); whether any scores under 4.5:1 is what the model will show. The guard reads an element's own `opacity` only to skip text under 0.05. |
| **68.11** | *"🟡 Every deploy resets FCC's own Restore Field Order (found 2026-11-16 by the refresh's release check). `setup_fields.py` re-POSTs each field at every deploy, and a POST appends the field at the end of Spoolman's field order, which undoes what FCC's "Restore Field Order" button (`api_spoolman_restore_field_order`) set. Harmless today (prod's order is already the default), but a person who orders the fields by hand loses it at the next update. Fix: have setup_fields keep each field's `order`, or skip a field whose definition already matches."* | **Live, and wider:** three of FCC's own field writers drop `order` too, so a new tag or slicer profile typed in FCC resets that field's place. This is likely the "it got overwritten" Derek met with the button on 2026-05-28 (the route's docstring). |

## Decisions

### For Derek, at the group's start: four questions, asked cold and one at a time

**Call 1 (68.1): which old by-hand scripts go.**
- **What it is.** Thirteen small Python scripts sit in the repo from before FCC could do their jobs itself. Nothing in FCC runs them, and you don't run command-line tools, so one runs only when an agent follows an old note, or by a slip. Four name prod outright: three name its Spoolman (two of them write to it), and the old terminal scanner names its FCC. Most of the rest write to the Spoolman the repo's `config.json` names (dev on your PC); the three January probes write only to dev since 2026-11-13. Several act the moment they start.
- **Where.** `setup-and-rebuild/`, `utilities/`, `_backup/`, `inventory-hub-scanner-unused/`, and `clean_choices.py` at the top of the repo. They never show on a screen.
- **A real example.** Started on your PC, `setup-and-rebuild/migrate_inventory.py` finds your spreadsheet in `3D Print Data` and adds a whole new set of spools to prod's Spoolman: one for every unopened, refill and opened spool on every row. `clean_choices.py` deletes and re-creates the Filament Attributes field, which erases every filament's tags (Group 36's data loss).
- **The scripts, by kind.**
  - One-time jobs, done: `migrate_inventory.py` (the January spreadsheet import); `_backup/sync_spoolman.py` (a February sheet sync; the folder also holds old copies of three page files); `clean_choices.py` (a March tag repair); `migrate_filament_attributes.py` (a May tag clean-up). ⚙️ Settings → 🏷️ Filament Attributes now does that clean-up, keeping each filament's other tags, and FCC removes the retired tags itself at start.
  - January probes whose own notes say there is no reason left to run them: `utilities/test_assignment.py`, `debug_test.py` and `repair_db_fields.py` (made to refuse prod on 2026-11-13).
  - Unused: the old terminal scanner (`inventory-hub-scanner-unused/`), and `utilities/dump_spoolman.py`, which writes prod's filament list to a CSV.
  - Still useful: `utilities/backup_database.py` (68.2 fixes it); the spreadsheet round trip, `export_to_csv.py`, then an edit, then `update_from_csv.py`; and `audit_duplicates.py`, which reads a local sheet and never touches Spoolman.
- **Options.**
  - **(a)** Delete the first three kinds (nine scripts, with the `_backup/` and scanner folders), and keep and fix the four still useful.
  - **(b)** Keep all thirteen, each fixed the same way: dev unless told otherwise, prod refused before anything is sent, and a dry run unless told to write.
  - **(c)** Delete everything except `backup_database.py`.
- **Recommendation: (a).** Git keeps every deleted file, so any of them comes back with one command.
- **If you don't answer: (b).** Nothing is deleted, and every script is made safe.

**Call 2 (68.6): should dev's FCC download the printers' print files?**
- **What it is.** Dev's FCC on your PC watches the same two printers as prod's FCC (dev's data holds its own copies of the printer logins). When a print ends, both FCCs download its file from the printer to work out what to charge. The Core One INDX hands files out slowly (about 15 KB/s), so two downloads at once most likely slow prod's charge down (not measured).
- **Where.** You see it only as prod's charge landing late: INDX job 1142 ended at 01:50 on 2026-11-13, and prod charged it at 02:23. Job 1141's file, which prod fetched alone, took 20 minutes. Dev's own download of 1142 finished at 03:13.
- **What changed since it was filed.** Since dev became a copy of prod's data on 2026-11-13, dev's records have spools on the heads. At the next print end dev would charge its own copies of them: dev's data only, never prod.
- **Options.**
  - **(a)** A switch in dev's own setup, set by default: dev keeps showing printer states (Printer Status, the printing questions) but never downloads a print file, so it charges nothing and opens no review cards. For a live check of new print-end code, an agent turns downloads on for that session (one line in dev's Docker file, then a restart) and off again after.
  - **(b)** Take the printer logins out of dev's data. Dev then shows no live printer states at all, and the printing questions can't be tried on dev.
  - **(c)** Leave it as it is.
- **Recommendation: (a).** Prod's charges stop competing for the printer, dev's copies stop drifting from charges nobody meant, and the mid-print checks still work on dev (they need printer states, not files).
- **If you don't answer: (a)**, the recommendation in the refresh you approved.

**Call 3 (68.10): pin the pop-up library?**
- **What it is.** FCC's pages load a pop-up library, SweetAlert2, from a public CDN as "the newest version 11". It draws Force Location's box and seven other prompts in the spool and filament windows. Bootstrap, the other library, is pinned to one exact version (5.3.0).
- **Where.** Nowhere you'd notice, unless a new release changes something. The line is `templates/components/scripts.html:2`.
- **An example.** If a later 11.x changed how its pop-up handles Escape or Tab, Force Location's box could start behaving differently one morning with no change in FCC. The tests that passed the day before ran against the older copy.
- **Options.**
  - **(a)** Pin the exact version the page loads today. Nothing on screen changes, and an update becomes a deliberate step with its own test run.
  - **(b)** Leave it on "newest 11", so its fixes arrive on their own.
- **Recommendation: (a).**
- **If you don't answer: (a).** Nothing on screen changes.

**Call 4 (68.3): which `update.sh` does the TrueNAS deploy job run?** A fact to read, not a choice.
- **What it is.** A TrueNAS cron job deploys FCC by running `update.sh`. The fix that stopped an old one-time job from rewriting spools at every deploy (`e918b3f`) takes out the line that ran it, and leaves a do-nothing stub in the job's place. The stub is there because the deploy that brings the fix still runs the old `update.sh` to its end, and that old line calls the stub. The stub can go once FCC knows which `update.sh` the cron runs.
- **Where.** TrueNAS web page → System → Advanced Settings → Cron Jobs → the FCC update job → Edit. Read the Command, then press Cancel: nothing changes.
- **An example.** `bash /mnt/LeftBankPool1/App_Data/InventoryHub/update.sh` runs the repo's own copy. Something like `bash /root/fcc-update.sh` would be a copy kept elsewhere: it would still run the old line at every deploy.
- **Options.**
  - **(a)** It runs the repo's `update.sh`: the stub is deleted in the release after the one that carries the fix.
  - **(b)** It runs a copy kept elsewhere: change the job's Command to run the repo's `update.sh` (Claude gives the exact line), then (a).
  - **(c)** Not read yet: the stub stays.
- **Answered (Derek, 2026-11-17, at the release): (a).** The Command is `/mnt/LeftBankPool1/App_Data/InventoryHub/update.sh`, run as a file (so it must stay executable, as `e918b3f` stores it), and its schedule never fires (it shows "Daily", but every update in prod's history since June was a press of play). The release carrying `e918b3f` deployed 2026-11-17 13:05 (`main` `623f2dc`), so the stub can be deleted in the next release.
- **Recommendation:** read it when you press play on the next release, the one that carries the fix.
- **If you don't answer: (c).** The stub stays. Once the new `update.sh` runs, nothing calls it, and it is one small file.

### Claude's calls (for veto)

- **68.1, whatever Call 1 decides.**
  - A script that stays and writes keeps its work in `main()` under `if __name__ == "__main__":`, so importing it sends nothing. It takes dev's address from 68.4's guard, refuses prod before any request, prints the Spoolman it will write first, and does a dry run unless given `--apply`.
  - `update_from_csv.py` stops writing `location` and `archived`. A move or an archive goes through FCC, which keeps slots, trails and single-slot boxes right; today the slot and trail extras stay behind. It sends only the extras its sheet changed, never the whole `extra` it read, and ends by saying which Spoolman it wrote and how many spools.
  - `dump_spoolman.py`, if it stays: dev by default, a timeout, and `__main__`.
  - The three R3-scratch copies are deleted. They are local folders, never tracked.
  - `tests/test_spoolman_write_sites.py`'s list of scripts that write to Spoolman (`:128-135`) is brought up to date. It still names `migrate_spool_links.py`, and it lacks `refresh_dev_from_prod.py`.
- **68.2.** `backup_database.py` takes `dev` or `prod` as a required word. It proves which share folder is dev's by the refresh's marker file, not by counting spools (dev is a copy of prod). It makes one backup request per run and names the copy by Spoolman and by the backup's own time. A request that fails copies nothing: today's fallback, which copies the newest `.db` in the folder whatever made it (`:86-93`), goes. The four old copies in the backup folder stay as they are.
- **68.3.** Delete the stub only after both: the release carrying `e918b3f` has deployed, and Call 4's answer is (a). Both were met on 2026-11-17. Leave `update.sh` itself alone: rewriting it only to drop a comment that names the retired file would rewrite it on prod for nothing.
- **68.4.** The module is `prod_guard.py` at the repo root (stdlib only, no 3.10+ syntax), loaded by path. The four guards become thin wrappers of it and keep their names, because tests call them. An unreadable port refuses everywhere; today conftest lets one pass. Conftest also refuses an `INVENTORY_HUB_URL` that names prod FCC, or whose host isn't this PC's loopback (`localhost`, `127.0.0.1`, `::1`): `names_prod_fcc` can't refuse port 8000 on every host, because dev FCC is `localhost:8000`, so a NAS name it doesn't list (`truenas.lan:8000`) would pass it, and the suite only ever drives a local FCC (the README demo is `127.0.0.1:8100`). For a run that isn't `--offline`, it also refuses a `config.json` whose Spoolman names prod (its defaults included, so a missing `config.json`, which means `127.0.0.1:7912`, refuses too).
- **68.5.** Besides temp folders and drive roots, the refresh also refuses a stage folder inside the repo anywhere but under `.captures/`. The repo is public, and the stage holds prod's database and dev's printer logins.
- **68.6, if Call 2 is (a).** The switch is an environment variable set only in `inventory-hub/docker-compose.yml`, which prod never uses: `FCC_PRINT_FILE_DOWNLOADS=off`. Unset means downloads on, as prod has always been. Every print end says in one Activity Log line that nothing was charged on this FCC, and FCC's start says in hub.log that downloads are off.
- **68.7.** The page fixture owns the buffer by default, on the test's own browser context (so a harness that serves its own buffer keeps it), with an opt-out mark. The four API slot-scan tests are deleted, because the same route already runs offline in `tests/test_assignment_logic.py`. The visual and UI slot tests answer their scan in the page.
- **68.8.** The sweep runs at the start and the end of every run that isn't `--offline` and reaches dev's Spoolman. It deletes only what the prefix rules match, and only records registered an hour or more before the run began, so another run's live records stay. The run's summary lists what it deleted and what it couldn't. `tests/debug_console.py` is deleted.
- **68.9.** The host-side gaps close with `FCC_DATA_DIR` and a Windows-host guard, never with a change to what the containers do. `__pycache__` stays as it is: the host's `.pyc` files are tagged by interpreter (`cpython-314`), the container's by its own (`cpython-39`), and `update.sh` deletes them at every deploy.
- **68.10.** Every listed canary limit is closed, each proven red first. Pin SweetAlert2 per Call 3, with no integrity hash, as with Bootstrap.
- **68.11.** `setup_fields` skips a field that already matches, and otherwise echoes the field's `order`, `unit` and `default_value`. FCC's three field writers echo them too, through one helper.

## Today's code (anchors, `dev` @ `95531a6`)

Line numbers drift, so re-grep before editing.

### The old by-hand scripts (68.1)
- `setup-and-rebuild/migrate_inventory.py`. Prod's address is at `:9`. At import, `CSV_FILE = find_file(...)` (`:27`, which climbs `:13-25`) finds `3D Print Data/3D Print Supplies - Filament.csv` on this PC (checked: the folder and the file exist). Its POSTs: vendor `:146`, filament `:291`, spool `:314`. The loop runs at module level with no `__main__` (`:317-344`; the spools are made at `:337-344`).
- `_backup/sync_spoolman.py`. Prod's address is at `:7`. It GETs prod's vendors and filaments at import (`:17-31`). It PATCHes a matched filament (`:163`), POSTs new filaments (`:167`), and opens its CSV from the working folder (`:8`, `:177`). Its spool POSTs (`:195`, `:200`) can't run: `:190` tests a sheet id that `sync_filament` has just added to `ALL_FILAMENTS` (`:172`). Everything runs at module level.
- `clean_choices.py` (repo root). It reads `config_loader.get_api_urls()` at import (`:9`), so the repo-root `config.json` decides (dev here, `127.0.0.1:7912` without one). At module level it does a DELETE, then a POST of `filament/filament_attributes` (`:43-46`).
- `utilities/update_from_csv.py`. Its address is `config.json`'s (`:9-10`). Its helpers are `:36-54`. The payload is built at `:94-153`: location `:94-99`, comment `:101-106`, archived `:108-113`, used weight `:115-128`, and the whole `extra` from its read `:130-153` (`:132`, `:152`). The write is `:156-158`, and `__main__` is `:165`. Its own list of text extras to quote for the wire (`:15`, used by `sanitize_extra_field` `:17-34`) holds 5 of the 24 in `spoolman_api.JSON_STRING_FIELDS` (`spoolman_api.py:44-60`), so a sheet edit of `product_url` or `physical_source_slot` would go out unquoted, which Spoolman refuses for a text field.
- `inventory-hub-scanner-unused/scanner.py`. Prod FCC is at `:3`. It GETs `/api/status` as it starts (`:57`; FCC has no such route). It POSTs `identify_scan` (`:116`) and `smart_move` (`:131`, `:148`), which act on prod. Its Ctrl+Z `undo` (`:107`) goes out as a GET, because `api_call` sends a falsy payload (`{}`) as one (`:52`), and the POST-only `/api/undo` refuses it. It is started by `RunScanner.bat`.
- `utilities/dump_spoolman.py:5-8`: a GET of prod's filaments at import, with no timeout.
- `setup-and-rebuild/migrate_filament_attributes.py`. Its address is `config_loader`'s (`:74`). `_get_field_definition` is `:95-106`: `r.json()` is under `except requests.RequestException`, and an entry that isn't an object raises at `f.get`. `_list_filaments` is `:128-138`. The `yes` prompt is `:241`; the DELETE, POST and PATCH are `:248-299`. Its docstring tells a person to swap `config.json` to prod's to run it against prod (`:50-54`). FCC replaced it: `app.py:351-358` (the start-up clean-up "so we never have to find + run the standalone migration script"), and the attributes manager's Purge.
- The three fixed utilities call `project_config.refuse_prod_spoolman` (`utilities/test_assignment.py:24-28`, `debug_test.py:21`, `repair_db_fields.py:43` and `:80`). They are pinned by `tests/test_reset_dev.py:1287-1358`, which goes with them if they are deleted.
- `review-samples/2026-11-11-group55/R3-scratch/{base,head-mut,pre-buttons}/`: each is a whole copy of the repo from before the fix, so it holds every old script: the old `utilities/` (`test_assignment.py` with no refusal), `clean_choices.py`, `_backup/sync_spoolman.py`, `setup-and-rebuild/migrate_inventory.py` and the old, real `migrate_spool_links.py`. They are the working tree's only such copies (checked 2026-11-17). The rest of `R3-scratch/` (probe scripts, logs, diffs) is Group 55's review material. `review-samples/` is ignored through this clone's `.git/info/exclude`, not `.gitignore`.
- The root `pytest.ini:4-12` keeps a `pytest .` out of these folders (`norecursedirs`). A root file named `test_*.py` is still collected (`test_ddg.py`; see the end); `clean_choices.py` isn't.

### The backup script (68.2)
- `utilities/backup_database.py` reads `config.json` at import (`:9-15`). `trigger_remote_backup` (`:35-61`) POSTs with no timeout (`:41`, and `:46` for an older Spoolman's `/backup`), then takes the file name from the answer's `path` (`:52-53`). `main` (`:63-109`) looks for that name in `backups/` beside `spoolman_db_path` (`:75`, `:85`); when the request failed, it takes the newest `.db` there by creation time instead (`:86-93`). It copies the file as `spoolman_backup_<now>.db` (`:96-102`), and `verify_backup` (`:20-33`) counts the copy's spool rows and calls that success.
- The repo-root `config.json` names Spoolman `192.168.1.29:7913` (dev) and `spoolman_db_path` `\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db` (prod's). `config.prod.json` names `:7912` and the same path. The two share `backup_directory`. Nothing else reads `spoolman_db_path` (`tests/test_config_save.py:38` uses it as sample data only).
- Dev's database and marker: `setup-and-rebuild/refresh_dev_from_prod.py:176` (`\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db`), `:191-192` (`FCC_DEV_SPOOLMAN.marker`, its first line `FCC_DEV_SPOOLMAN marker v1`). `:1329-1331` already says that both configs name prod's database.
- Spoolman 0.27.1's backup, as the refresh's release check read its source (2026-11-16): the POST answers `{path, created}`. Within 5 minutes of the last rotation, or with the database unchanged, it hands back its newest backup with `created: false`. It keeps `spoolman.db` plus `.1` to `.5`, and makes one more at midnight.
- The four copies in `backup_directory` (2026-02-10 to 03-27) are all named alike. The last three carry a file time of exactly midnight: Spoolman's nightly backups, not a backup made when the script asked. That fits the item.

### The retired migration (68.3)
- `setup-and-rebuild/migrate_spool_links.py` is the 15-line stub (a docstring and one `print`; no import).
- `update.sh:62-64`: `setup_fields.py`, then two comment lines; nothing calls the stub. `git ls-files -s update.sh` reads 100755.
- `inventory-hub/tests/test_spoolman_write_sites.py:132` still lists the script among those that write.

### The four prod guards (68.4)
- `utilities/project_config.py`:
  - `PROD_SPOOLMAN_PORT` and `PROD_NETLOCS` are `:13-14`, `DEV_SPOOLMAN_DEFAULT` and `REPO_CONFIG` `:15-16`;
  - `dev_spoolman_url()` (`:19-29`) reads only `config.json`, never `DEV_SPOOLMAN_URL`;
  - `prod_spoolman_refusal` (`:32-44`) refuses an unreadable port, port 7912 on any host, and the three netlocs;
  - `refuse_prod_spoolman` (`:47-53`) exits 2.
- `setup-and-rebuild/reset_dev.py`: `SPOOLMAN_URL` at `:119`; the constants at `:125-126`; `prod_refusal` (`:181-194`) is a copy of the above; `_refuse_prod` and `_url` are `:197-210`.
- `setup-and-rebuild/refresh_dev_from_prod.py`:
  - the addresses are `:170-181`, the share folders `:184-187`, the netlocs `:195-196`;
  - the path canon (`_strip_device_prefix`, `_canon`, `_kind`, `_spellings`) is `:265-342`;
  - `is_prod_path` is `:356-371`, `_guard_write` `:379-400`;
  - the HTTP side is `_addr` / `_prod_addrs` / `_prod_ports` / `dev_spoolman_refusal` (`:474-510`) and `http()` (`:513-553`), which refuses any non-GET to a prod port and any address that isn't dev Spoolman, prod Spoolman or dev FCC;
  - `main` refuses a prod `DEV_SPOOLMAN_URL` (`:2566-2570`). `FCC_REFRESH_DEV_FCC_URL` (`:172`) is only ever read.
- `inventory-hub/tests/conftest.py`:
  - `DEFAULT_BASE_URL` takes `INVENTORY_HUB_URL` unchecked (`:261`). Two tests read the variable themselves (`test_printer_state_api.py:215`, `test_search_deployed_filter.py:132`), so the refusal reads the variable in `pytest_configure`, before collection, not `DEFAULT_BASE_URL` alone;
  - `names_prod_spoolman` (`:271-277`) checks the port only, and an unreadable port answers False;
  - `pytest_configure`'s prod check (`:604-612`) looks at `DEV_SPOOLMAN_URL` only.
- The `--offline` socket guard blocks ports 8000, 7912 and 7913 (`conftest.py:2400`). It is a port list, not a prod guard, and stays.
- Host backend calls use `config_loader.get_api_urls()` (`inventory-hub/config_loader.py:169-182`), whose defaults are `127.0.0.1` and `7912` (`:83-84`).
- `tests/test_large_spool_weight_tracking.py`: the fixture makes a filament and a spool on `require_spoolman` under dev's first real vendor (`:22-61`). The tests then read and write through `spoolman_api` (`:64-110`), which goes to `config.json`'s Spoolman.
- Prod FCC is `192.168.1.29:8000` (the never-GET-it note in `overnight-run-2026-10-13.md:27`). Dev FCC is `localhost:8000`, the same port, so a port-only rule can't tell the two apart.

### The refresh's stage folder (68.5)
- The default is `.captures/dev-refresh-<today>` (`refresh_dev_from_prod.py:180-181`); `--stage-dir` is read at `:2564-2565`.
- `main`'s only folder checks are prod's share and "not on this PC" (`:2571-2578`).
- What it holds:
  - the staged prod copy, `prod-spoolman.db` (`:1112-1147`);
  - the swap's backup, `dev-spoolman-before.db` (`:1341-1353`);
  - `backup_dev_data` (`:1813-1839`), every file in `inventory-hub/data/`, printer logins included;
  - the stage report and the locations copies (`:202-207`).
- The docstring's ROLLBACK (`:112-116`) names the files but never says when the folder may go.
- Not every phase uses the folder. The run order (`EPILOG`, `:2489-2506`) starts with `init-marker`, once per dev data folder and before `stage`, and it uses none; neither does `seeds` today (`:2401-2440`); `checklist` ("any time", read-only) writes one file there only with `--apply` (`:2478`). Yet `main` checks the folder for every phase (`:2571-2578`).
- The existing refusal test is `tests/test_reset_dev.py:504-511` (`test_main_refuses_a_stage_folder_on_prods_share_or_off_this_pc`).

### Dev's print-file downloads (68.6)
- The one download path: `print_deduct.py:1802` → `prusalink_api.fetch_cancel_gcode` (`:123`) → `_download_file_bytes` (`:87-101`, `timeout=60`). `download_gcode_content` (`:104`) has no caller outside tests.
- The end edges: `print_monitor._track_print_edge` (`:647`) sees the end and calls `_dispatch_cancel_edge` (`:451-463`), `_dispatch_completion_edge` (`:531-545`) or `_dispatch_ambiguous_edge` (`:629-644`), at `:877` and `:1022-1037`. Each dispatcher runs its `_on_*_edge` on a thread, which writes the print's fetch record first (`_hold_edge_fetch`, `:424`, `:490`, `:597`), then reads the heads (`_capture_end_heads`, `:338`; called at `:429`, `:495`, `:603`), then downloads.
- The deferred queue is `_process_pending_cancel_fetches` (`:1202`), which runs `_run_fetch_retry` (`:1436`). Restart recovery is `_recover_print_tracker_on_start` (`:1481`) and `_recover_one_print_latch` (`:1554`), which hands its edges to the same three dispatchers (`:1624`, `:1644`, `:1668`). The latch is saved by the monitor's tick (`print_tracker_store.save`, `:1136`), not by a dispatcher.
- `prusalink_api` imports nothing of FCC's (`:1-5`); `print_monitor` imports it (`:32`).
- Start: the monitor starts in `app.py:380-392`. The only dev signal today is `FCC_DEV=1` (`inventory-hub/docker-compose.yml:24`; read at `app.py:364`), which means the reloader. The file has no newline after that last line.
- Dev's data, read 2026-11-17:
  - `pending_cancel_deducts.json` and `pending_cancel_fetches.json` are `{}` (last written 2026-11-13 18:17, by the refresh);
  - the latch shows both printers IDLE;
  - dev's `hub.log` has job 1142's end read at 09:50:30 UTC on 2026-11-13 ("no spool on any head … the read isn't used") and 1141's queued cancel at 22:15:46 UTC that day, and no print-file line since.

### The shared scan buffer (68.7)
- The save path: `renderBuffer`'s save, `inv_cmd.js:77-88`, calls `persistBuffer` (`:4641-4647`). The grace window is `:4670-4673` and the pending save `:4695-4698`. The refresh 500 ms after a load is `:4690`, and a card repainted by a refresh saves at `:4790` (`window.renderBuffer()` with no server mark). The heartbeat's path is `inv_core.js:3533`.
- The fixtures:
  - `conftest.own_the_buffer` (`:886-908`);
  - `clean_buffer` (`:1027-1034`);
  - `with_held_spool` (`:1037-1050`; listed in `CONTAINER_FIXTURES` at `:352` and in `tests/test_offline_mode.py:43`);
  - the `page` fixture (`:705-753`).
- The unowned writers:
  - `test_buglist_group21.py` (`:96-108`; the two tests before it install their stub after `page.goto`, `:51-53`);
  - `test_slot_action_modal_removed.py` (`:33-78`, `:81-133`; it snapshots `state.heldSpools` before the first buffer load);
  - `test_buffer_race_protection.py` (`:132-136`, `:196-200`, `:253-257`).
- The slot-QR tests:
  - `test_slot_qr_scan_api_e2e.py`: `:15` no buffer, `:24` bad target, `:38` bad slot, `:53` the clear endpoint, and `:67` an opt-in happy path that moves a real spool;
  - `test_slot_qr_scan_ui_e2e.py:94` (the pickup; it owns the page's buffer but empties dev's server buffer);
  - `test_slot_qr_scan_visual.py:24` (bad target; its page doesn't own its buffer) and `:31` (bad slot).
- The server reads its own buffer for a slot scan (`routes_scan.py:1632`) only after the target and slot checks (`:1590-1626`). Each of those checks writes an ERROR line to the Activity Log.
- The offline twins already in `tests/test_assignment_logic.py`: no buffer `:125`, bad Type `:144`, missing target `:161`, slot range `:174` and `:188`, the clear endpoint `:240`. They pin what the E2E cases pin, except the no-buffer twin, which doesn't assert `type == "assignment"`.
- `test_weight_setting_dispatches_events.py:104-143` empties dev's buffer, reads dev's whole spool list, and passes on the heartbeat's own `sync-pulse` event whatever the scan did.
- The tripwire to copy is `test_fab_no_overlap_with_cmd_deck.py:62-91` (`dev_writes`). It passes on what it doesn't answer with `route.fallback()` (`:75`), so routes registered before it still get the request.
- Some tests do the opposite. Seven test files register a page-level catch-all (`**/*` or `**/api/**`, nine in all) whose handler sends what it doesn't answer to the network with `route.continue_()`, which skips every route registered before it: `test_printer_status_widget.py` (`:197`, `:520`, `:599`; its handler at `:194` passes `/api/state/buffer`, a GET or a save, to dev), `test_quickswap_visual.py:123` (`continue_` at `:114`), `test_text_size_guard.py:84`, `test_max_attribute_chips_e2e.py:188`, and three that pass on GETs only and answer every write in the page (`test_audit_double_click_58_e2e.py:193`, `test_audit_find_and_tiles_58_e2e.py:46`, `test_audit_file_extras_page_58_e2e.py:48`). The 13 catch-alls registered on the context instead (`test_confirm_chain_reshow_e2e.py:153` among them) lose to any page route. Eight of those context harnesses answer `/api/state/buffer` themselves, from an in-page fake, and most also record the page's saves: `test_core1_return_ejectall_e2e.py` (`:121`, `:160`), `test_slot_picker_e2e.py` (`:146`, `:156`), `test_deposit_card_race_e2e.py` (`:109`, `:138`), `test_cancel_review_picker_e2e.py`, `test_head_load_confirm_e2e.py`, `test_honest_empties_e2e.py`, `test_loc_editor_enter_to_save_e2e.py` and `test_move_result_consumers_e2e.py`.

### Throwaway records (68.8)
- In `conftest.py`:
  - `require_spoolman` is `:1740-1753`;
  - `_delete_record` (`:1770-1775`) ignores the answer and swallows every request error;
  - `_ensure_test_vendor` (`:1778-1799`) makes `__fcc_test_vendor__`;
  - `throwaway_filament`, `throwaway_spool` and `throwaway_spool_with_extras` are `:1802-1921`; the last sends no comment (`:1899-1904`).
- The sweep, `_cleanup_orphan_test_records` (`:1924-1961`):
  - it yields first (`:1940`), so it runs at the first test's teardown;
  - it runs only with RUN_INTEGRATION (`:1936-1942`);
  - it lists spools without `allow_archived` (`:1950`), matches them by comment (`:1953`), and matches filaments by name (`:1958`); no vendors.
- The records:
  - `test_weigh_out_e2e.py:33` and `test_weigh_out_preserve_text_e2e.py:77`, `:130` (no integration mark);
  - `test_audit_no_label_58_e2e.py:207` and `test_audit_done_question_58_e2e.py:461` (spools with no comment, filed in a real empty dev box or cart);
  - `test_vendor_create_end_to_end.py:36` and `:160` (vendors `__fcc_test_e2e_vendor_*` and `__fcc_test_cascade_vendor_*`; dev's log shows a run making both on 2026-11-14);
  - `test_large_spool_weight_tracking.py:37` (`LARGE-SPOOL-TEST`);
  - `test_backfill_spool_weights.py:32` and `:119` (`BACKFILL-TEST`, `-NO-INHERIT`);
  - `test_wizard_e2e.py:46-47`: through the wizard, Material `Pytest-PLA` and Colour name `E2E Ruby Red`, which names the filament (`inv_wizard.js:4236`). Its `finally` deletes both records, so only a killed run leaves them.
- The vendor: `test_backfill_spool_weights.py:101-144`. It reads dev's first vendor (`:106-111`) and PATCHes its empty weight to 0 at `:112-114`, *before* `try:` at `:131`; so `assert fil.ok` at `:129` failing skips the restore. The restore runs only when the saved weight wasn't None (`:139-144`).
- `inventory-hub/tests/debug_console.py`: a by-hand Playwright script (not collected) that submits the same wizard form (`:18-19`) and deletes nothing.

### Smaller leftovers (68.9)
- **The unpatched read:** `tests/test_buffer_ejection_logic.py:71-93`; `logic.py:4434` (the non-strict `get_spools_at_location_detailed`); the patched siblings are at `:130` and `:170`.
- **The fixtures:**
  - `test_quickswap_visual.py:106-133` (`hermetic_grid`: `yield`, then its own `unroute_all` at `:129-133`);
  - `test_audit_double_click_58_e2e.py:495-513` (`board`: unroute at `:510`, then `context.close()`);
  - the page fixture's `--screenshot` branch, `conftest.py:744-753`.
- **The watch item:** `test_audit_double_click_58_e2e.py:451-465`; `SHIELD_S` `:68`; `/api/search` answered in Python, `:203` and `:284`; the case is driven at `:838-839`. `double_click_over` has two other callers, `:632` (Cancel Audit brought under the pointer) and `:728` (the report window's Close).
- **45.9's gaps:**
  - `config_loader.py:110` writes `.config_mtime` beside `BASE_DIR` (the repo root on the host);
  - `save_config` → `_write_merged_config` → `_write_config_atomic` (`:316`, `:353`, `:229`) writes `get_config_path()` (`:34-45`), which is dev's real, bind-mounted `config.json`. `_write_merged_config` first writes the rolling `config.json.bak` beside it with a plain `open` (`:404-411`; on the host that is the repo root), then calls `_write_config_atomic` (`:416`). It is the only path that writes the file;
  - `app.py:155-157` runs the start-up migrations and both re-surfaces at import;
  - `locations_db.py:67` falls back to `'data'` relative to the working folder, and `_ensure_data_dir` (`:110-119`) makes that folder at the first locations read or write.
- **The strays:** `<repo>/hub.log` (0 bytes, born 2026-11-13 21:47:16.50) and `<repo>/data/` (empty, born 0.8 s later, 21:47:17.30); `<repo>/.config_mtime` (rewritten 2026-11-17 00:11); `<repo>/__pycache__/test_ddg.cpython-314-pytest-9.0.3.pyc` (2026-11-13 19:49, a root `pytest .`).
  - `state.py:99` opens its handler with no `encoding`. On this PC, Python 3.14's default for it is cp1252, and a log line with an emoji can't be written there.
  - Reproduced in a scratch folder: the handler, its first line "✅ Loaded Prod Config", a 0-byte `hub.log` and a "--- Logging error ---" on stderr.
- **The ordering tests:** not named in Group 57's round-3 note (`57-low-stock-at-a-glance.md:98`). Most likely they are `test_low_stock_glance_57_js.py:576-588` (`test_the_lists_own_read_never_paints_over_a_newer_heartbeat`) and `:621-635` (`test_a_tick_sent_before_the_lists_read_never_paints_over_it`). Each holds an older answer for 900 ms (`_answer(..., delay=900)`, the helper at `:139-142`) while a newer one is made to land. On a run slow enough that the newer one takes over 900 ms, the older answer lands first, and the test passes without the ordering it pins. Four more `delay=900` holds (`:827`, `:849`, `:881`, `:953`) need the same look.
- **Group 54's notes** (`54-group36-leftovers.md:68`, `:117-118`):
  - `tests/spoolman_extra_fake.py:308-310` stores every non-`extra` key of a PATCH as sent, `remaining_weight` included;
  - `tests/roundtrip_bridge.py:26-28` reads `sys.argv[1]` and `[2]` at import, so `pytest tests/roundtrip_bridge.py` fails in collection;
  - `setup-and-rebuild/setup_fields.py:296-297` prints `extra.get('container_slot')!r`, the wire form (`'"4"'`).

### The canaries' limits (68.10)
- **SweetAlert2:** `templates/components/scripts.html:2` (`sweetalert2@11`). Its globals are `CDN_GLOBALS` (`tests/test_load_order_canary_js.py:216-224`), with a stand-in at `:1281` and a reader pin at `:3001-3012`. Bootstrap is pinned at `scripts.html:1` and `dashboard.html:43`, and qrcodejs is pinned too (`dashboard.html:45`).
- **The load-order canary:**
  - the stub's query limit is documented at `:92-94` and `:164-170` and coded at `:732`, `:1049` and `:1121`;
  - the zero-delay timer filing is `:123`;
  - the two tuple messages are `:2205` and `:2217` (`(_pinned(...), …)`);
  - the module-wide `pytestmark = skipif(NODE is None)` is `:197`, which also skips the pure-Python tests (`:2170-2198`, on the `page_scripts` fixture at `:2065-2068`) and the template reader's;
  - `NODE_MISSING_MSG` is `tests/test_core1_return_ejectall_js.py:43-52`.
- **The one-list canary** (`tests/test_toolhead_types_one_list.py`): a words string kept in a const and split later is in the docstring's "What the rules don't see" (`:76-78`), because `_SPLIT_AFTER` (`:330-332`) reads only a split right after the literal (`:31` and `:365` are the regex kept in a const, which the canary does catch); a regex right after `)` read as a division, `:80`, `:137` and `:161`.
- **The write-site canary** (`tests/test_spoolman_write_sites.py`): the three discard forms are `_discarded_calls`, `:561-580`; the chain over-count is described at `:156-157` and coded at `:716-720`.
- **The contrast guard:**
  - it is `CONTRAST_GUARD_JS`, `conftest.py:2009-2114`, with its header at `:1995-2008`;
  - brightness is read at `:2040-2057`, and an element's own opacity only to skip text under 0.05 (`:2083-2084`);
  - its own tests are `tests/test_contrast_guard_compositing.py` (hermetic on `isolated_page`; the brightness cases are `FILTER_CASES` from `:230` and the two tests after it, to `:309`);
  - text with opacity in `global.css`: `.loc-badge-hover` 0.85 (`:626`), `.btn-buffer-x` 0.7 (`:1042`), `#manage-empty-msg .empty-state-text` 0.9 (`:2220`), `.fcc-ps-skeleton` 0.7 (`:2817`). In the page code (counted 2026-11-17): 16 inline values under 1 (`inv_quickswap.js` and `inv_wizard.js` 4 each, `ui_builder.js` 3, one each in `inv_config.js`, `inv_core.js`, `inv_settings.js`, `modals_details.html` and `modals_wizard.html`) and 6 Bootstrap `opacity-*` classes (`inv_search.js` 3, `modals_weigh_out.html` 2, `offcanvas_search.html` 1);
  - the two brightness rules are `:633` and `:3181`.

### Field order (68.11)
- **`setup_fields.py`:**
  - `create_field` (`:36-138`) sends `{name, field_type}` plus `multi_choice` and the merged choices (`:106-118`), never `order`, `unit` or `default_value`, and POSTs it (`:121`);
  - it reads the field list only for choice fields (`:81-104`), with no timeout (`:84`, `:121`, and `:59` / `:144` for the deletes);
  - every call runs at module level (`:501-595`, then `print("…All Fields Configured Successfully!")` at `:597`);
  - `_read_field_definition` (`:164-190`) is the never-raising read to reuse.
- **Spoolman 0.27.1's field POST** (as the release check read its source) replaces the whole definition. An omitted `order` becomes 0, and the field moves to the end of Spoolman's list.
- **The button and its words:**
  - the route is `routes_inventory.api_spoolman_restore_field_order` (`:335-420`), which sets each field's `order` from `FIELD_ORDER` (`:245-283`) and echoes the rest;
  - the page is `inv_config.js:492-530`;
  - the Settings section is `modals_config.html:51-87`. Its words blame "edits" for the drift and name `order: 0` and `FIELD_ORDER`.
- **FCC's own writers that drop `order`:**
  - `spoolman_api.ensure_extra_field`'s label refresh (`:1834-1843`);
  - `update_extra_field_choices` (`:2313-2322`), reached from the add-a-choice routes, for example a new slicer profile typed in the spool window;
  - `ensure_filament_attributes_cleaned`'s rebuild (`:2182-2194`).
- **The one that keeps it:** `routes_config_attrs._recreate_field_payload` (`:412-436`).
- **Tests to extend:**
  - `tests/test_setup_fields_idempotent.py`, which loads the script with `requests` patched (`:26-55`);
  - `tests/test_setup_fields_migration_54_4.py`'s `FieldFake` (`:66-180`), whose POST already appends the field at the end (`:138-151`);
  - `tests/test_restore_field_order.py`.

## Design, by member

### 68.1: no old script writes by accident
- Delete what Call 1 deletes, in one commit per kind, so any one can be brought back alone. Take the deleted names out of `tests/test_spoolman_write_sites.py:128-135`. Drop `tests/test_reset_dev.py:1287-1358` with the three probes, or move its fixture to the kept scripts.
- A kept script that writes:
  - its work in `main(argv=None)` under `__main__`;
  - dev's address from 68.4's guard, and prod refused before any request;
  - the target printed first;
  - a dry run unless `--apply`;
  - `timeout=` on every request.
- `update_from_csv.py` writes only comment, used weight and the extras its sheet changed (each sent alone; the read-merge rule doesn't apply to a raw PATCH, but 0.27 merges key by key). Each extra goes out in its wire form by its type in Spoolman's field list (`GET /api/v1/field/spool`, read once), never by its stale five-key copy. A `Location` or `Archived` column that differs is listed as "change this in FCC" and not written.
- A kept script that only reads (`export_to_csv.py`, and `dump_spoolman.py` if it stays) defaults to dev, has a timeout and `__main__`, and may name prod only when asked.
- Delete the three R3-scratch folders.

### 68.2: back up the Spoolman that was asked, and say which
- `python utilities/backup_database.py dev|prod`; with no word, it prints how to use it and exits 2.
- Each name has its own address and share folder, taken from `prod_guard` (prod: port 7912 and `\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\`) and from 68.4's dev rule (dev: `DEV_SPOOLMAN_URL`, else `config.json`, else the default; the folder `\\TRUENAS\App_Data\Spoolman_Dev\`, with an environment override as the refresh has). `spoolman_db_path` is no longer read.
- Before the request:
  - dev's folder must hold `FCC_DEV_SPOOLMAN.marker` (first line `FCC_DEV_SPOOLMAN marker v1`) beside the database;
  - prod's folder must hold none;
  - both words check both rules, as the refresh's swap does, so `dev` refuses while prod's folder holds a marker and `prod` refuses while dev's lacks one. Nothing is asked of Spoolman until both hold.
- One POST, with a 30 s timeout. Read `path` and `created` from the answer. With `created: false`, say "Spoolman handed back its backup from <time> (it makes at most one every 5 minutes)". A request that fails, or an answer with no `path`, copies nothing (today's fallback to the newest `.db` goes).
- Copy `<folder>/backups/<name>` to `backup_directory/spoolman-<dev|prod>-<the backup file's own time>.db`, never over an existing file (exclusive create).
- Verify the copy read-only, as now. Then read the asked Spoolman's live count and highest id (`/api/v1/spool?allow_archived=true`) and print the two side by side. A copy whose highest id is above the live one gets a warning, never "success". The marker is the proof of which Spoolman; the counts are a sanity check.
- Its docstring says that each POST rotates that Spoolman's six copies, so the script makes one request per run. It also says that the pre-deploy backup can be up to 5 minutes old and ages out in about a week.

### 68.3: the stub goes, later
- When both conditions hold (Claude's calls), delete `setup-and-rebuild/migrate_spool_links.py`, take it out of `test_spoolman_write_sites.py:132`, and archive the buglist item. Until then this member is done except for that commit; say so at the group's merge if they don't hold yet.
- Add the deploy-script pins under Tests, so a later edit can't break the deploy.

### 68.4: one prod guard
- **`prod_guard.py` at the repo root** (stdlib only; loaded with `importlib.util.spec_from_file_location`, never by putting the root on `sys.path`, where `clean_choices.py` and `test_ddg.py` sit):
  - `PROD_HOSTS` (`192.168.1.29`, `truenas`, `truenas.local`), `PROD_SPOOLMAN_PORT` (7912), `PROD_FCC_PORT` (8000), `PROD_SPOOLMAN_URL`, `DEV_SPOOLMAN_DEFAULT`, `PROD_SHARE_FOLDERS`;
  - `names_prod_spoolman(url)` answers why, or None: port 7912 on any host, one of prod's addresses, or a port it can't read;
  - `names_prod_fcc(url)`: port 8000 on any spelling of prod's host (case, a trailing dot, the IPv4-mapped IPv6 form), or a port it can't read;
  - `is_prod_share_path(path, also=())`: the refresh's `_canon` / `_spellings` / `_kind` / `is_prod_path`, moved as they are, with the refresh's env-named folders passed as `also`.
- **The consumers keep their names as wrappers:**
  - `project_config.prod_spoolman_refusal` / `refuse_prod_spoolman`, and `dev_spoolman_url()`, which reads `DEV_SPOOLMAN_URL` first, then `config.json`, then the default;
  - `reset_dev.prod_refusal`;
  - the refresh's `dev_spoolman_refusal`, `_prod_ports`, `_prod_addrs` and `is_prod_path`, plus a refusal of an `FCC_REFRESH_DEV_FCC_URL` that names prod FCC;
  - `conftest.names_prod_spoolman`.
- **In `conftest.pytest_configure`:**
  - refuse an `INVENTORY_HUB_URL` that names prod FCC, or whose host isn't loopback (`localhost`, `127.0.0.1`, `::1`), with "the suite drives the FCC on this PC". It reads the variable itself, so the two tests that read it directly are covered too;
  - outside `--offline`, refuse a `config.json` whose Spoolman names prod. Read the file `config_loader.get_config_path()` names, with `json.load`, never `load_config()`, which writes `.config_mtime`. The URL is built as `get_api_urls` builds it, defaults included. Under `--offline` the socket guard already blocks 7912.
- **`test_large_spool_weight_tracking.py`:** its fixture patches `config_loader.get_api_urls` to answer `require_spoolman`, so every read and write goes to the Spoolman its spool is on. It uses the shared test vendor and the prefix (68.8).

### 68.5: a stage folder that lasts the whole run
- **Refused** (each spelling read through `_canon` and `_spellings`, so a junction or a mapped drive is caught too):
  - a stage folder under TEMP, TMP, `tempfile.gettempdir()`, `%LOCALAPPDATA%\Temp` or `%SystemRoot%\Temp`;
  - a drive root;
  - anywhere inside the repo but under `.captures/` (Claude's call).
- **One folder per run:**
  - `stage --apply` creates `.captures/dev-refresh-<YYYY-MM-DD-HHMMSS>/` and writes its path into `.captures/dev-refresh-current.txt` (a dry run writes nothing, as now);
  - every later phase that uses the folder (`swap`, `verify-spoolman`, `locations`, `fixtures`, `count`, and `checklist --apply`) takes its default from that file, refusing with "run `stage` first, or name the folder with `--stage-dir`" when the file is missing. `init-marker`, which runs before `stage`, uses no folder and never asks for one, so `main`'s folder checks apply only when a phase uses it;
  - `seeds`, the last phase, needs no folder for its own work. Once it passes with `--apply`, it records the finish in the stage report of the folder the pointer names (when there is one) and removes the pointer;
  - `--stage-dir` and `FCC_REFRESH_STAGE_DIR` work as today.
- **The docstring and `--help`** say what the folder holds: a full copy of prod's database, dev's database and data folder as they were (the only rollback copies, printer logins and `config.json.bak` included), and copies of prod's locations. They also say to delete it once every phase has passed and dev has run a few days. The repo is public, so the folder stays out of it.

### 68.6: dev keeps printer states and downloads no print file (if Call 2 is (a))
- **The switch:** `FCC_PRINT_FILE_DOWNLOADS`. `off`, `0`, `false` or `no` means off; anything else, unset included, means on, which is prod's behaviour. It is read at the call by one function, `prusalink_api.print_file_downloads_on()`, so tests can set it. It lives in `prusalink_api` because the backstop below sits there: `prusalink_api` imports nothing of FCC's and `print_monitor` already imports it, so a reader in `print_monitor` would make the backstop a circular import. The gates call it module-qualified. `inventory-hub/docker-compose.yml` sets it to `off`, with a comment saying how to turn it on for a live check (comment the line out, then `docker compose up -d`).
- **The gates, while off:**
  - the three dispatchers don't run their `_on_*_edge`, so nothing is recorded: no fetch record, no end-heads read, no review card, no ledger entry. They write one escaped INFO line in the Activity Log per print end, for example "🔕 Core One INDX: job 1142 ended (completed); print-file downloads are off on this FCC, so nothing was charged here." The print latch moves on as it does now: `_track_print_edge` updates the tracker before any dispatch, and the monitor's tick saves it (`:1136`);
  - restart recovery's edges go through the same three dispatchers (`:1624`, `:1644`, `:1668`), so the gate above covers them; `_process_pending_cancel_fetches` downloads nothing. An entry already queued stays queued and keeps its 72 h window;
  - a backstop in `prusalink_api._download_file_bytes` answers None, with one line and never a request.
- **At start,** a WARNING in hub.log: "Print-file downloads are off (FCC_PRINT_FILE_DOWNLOADS): this FCC charges no print." It is not in the Activity Log, because dev's reloader restarts on every save.
- **Unchanged:** Printer Status, the heartbeat's printer states, the print latch and the printing questions.
- **Backend rules apply:** module-qualified calls, Python 3.9 syntax, nothing started at import.
- **For (b):** a refresh option that drops `printer_creds`, plus a note in the refresh's docstring. **For (c):** nothing.

### 68.7: no browser test writes dev's shared buffer unless it says so
- **The class fix, in the `page` fixture:**
  - before yielding, it answers `/api/state/buffer` in the browser with a buffer of the page's own, starting empty (`own_the_buffer`'s handler), unless the test carries `@pytest.mark.shared_buffer` (registered with `config.addinivalue_line`);
  - it registers that route on the page's context (`page.context.route`; pytest-playwright makes a context per test), not on the page. Playwright asks page routes before any context route, so a test's own `own_the_buffer(page, initial)` still wins. Context routes are asked last-registered first, so the eight harnesses that answer `/api/state/buffer` themselves on the context, registered after the default, keep their own buffers and the saves they record (several assert on them; Today's code). A page-level default would have taken those requests from them;
  - a test marked `shared_buffer` reads dev's buffer first and leaves it as it found it;
  - a page-level catch-all's `route.continue_()` sends a request to the network past every route not yet asked, the default included. So each test's page-level catch-all handler (`**/*`, `**/api/**`; the seven files under Today's code) passes on what it doesn't answer with `route.fallback()`, which reaches the default and then the network as before. A source check in the 68.7 tests keeps it so.
- **The named files:**
  - `test_buglist_group21.py`, `test_slot_action_modal_removed.py` and `test_buffer_race_protection.py` call `own_the_buffer` themselves, so their intent shows in the file;
  - `test_slot_action_modal_removed.py` waits for the page's first buffer load before taking its snapshot.
- **The slot-QR tests:**
  - delete `test_slot_qr_scan_api_e2e.py`'s `:15`, `:24`, `:38` and `:53`. The same route runs offline in `test_assignment_logic.py` (`:125`, `:144` / `:161`, `:174` / `:188`, `:240`), with no dev buffer and no lines in dev's Activity Log. First check that each twin pins what its E2E case pinned (the status, `action`, `found_type`, `max_slots`, the cleared buffer), and extend the twin where it doesn't;
  - the opt-in happy path (`:67`) carries the mark and restores dev's buffer;
  - `test_slot_qr_scan_ui_e2e.py:94` and both visual tests (`test_slot_qr_scan_visual.py:24`, `:31`) answer their scan in the page with the route's own answer, a fixture whose shape the offline twin pins. They drop `clean_buffer`, and both visual tests own the page's buffer.
- **`with_held_spool`** goes, from `conftest.py:1037-1050`, `CONTAINER_FIXTURES` (`:352`) and `test_offline_mode.py:43`. `test_weight_setting_dispatches_events.py`'s live test is rewritten: it owns the buffer, answers its spool scan in the page, and checks that `inventory:buffer-updated` fires when the page adds the spool. It no longer reads dev's spool list.

### 68.8: every throwaway record is found, and no real record is touched
- **The sweep** becomes a session fixture that runs at the start and at the end of every run that isn't `--offline` and whose dev Spoolman answers its ping. It runs after `pytest_configure`'s prod check, on `DEFAULT_DEV_SPOOLMAN` only.
  - Spools: `?allow_archived=true`, matched by a prefix in the comment or in the spool's filament name.
  - Filaments: by name.
  - Vendors: `__fcc_test_` names, except `__fcc_test_vendor__`.
  - It deletes spools, then filaments, then vendors, and the terminal summary lists what it deleted and what Spoolman refused.
  - It never matches anything without the prefix.
  - It leaves a record registered (Spoolman's `registered`) less than an hour before the run began, so a second run going at the same time (another chat's) keeps its live records. A record this run's own teardown failed to delete is then swept by a later run.
- **`_delete_record`** reports a failure (a status that isn't 2xx, or a request error) as a `PytestWarning` naming the record.
- **`throwaway_spool_with_extras`** gives every spool a prefixed comment unless the test passes its own.
- **The four names** take the prefix (`__fcc_test_large_spool`, `__fcc_test_backfill`, `__fcc_test_backfill_no_inherit`, and the wizard test's filament, named by its Colour name box: `__fcc_test_E2E Ruby Red`, with a short random suffix as `_make_test_name` adds). Its Material can stay "Pytest-PLA". Both local fixtures use the shared test vendor instead of dev's first real one.
- **The backfill test** becomes `@pytest.mark.integration` and uses a throwaway vendor of its own with no empty weight (made and deleted by the test). No real vendor is read or written.
- **`tests/debug_console.py`** is deleted.

### 68.9: the smaller leftovers
- **(1) The unpatched read:** `test_smart_eject_restores_home_slot` patches `get_spools_at_location_detailed` with `return_value=[]`.
- **(2) The fixtures:**
  - `hermetic_grid` drops its own unroute;
  - `board` closes its context first, and the unroute goes;
  - under `--screenshot`, the page fixture closes the gap without un-routing first: for example, a last route that aborts every request, registered at teardown, so no request in the gap reaches dev. Prove on a slow route handler that the next test's setup doesn't meet the `TargetClosedError` the ignore-errors unroute fixed.
- **(3) The watch item:** when the 600 ms runs out, `double_click_over` waits up to 5 s more for what it waits on. If it comes, the case skips with the measured time ("the page took 1840 ms to draw Find's rows, longer than a double click: no real double click could be staged"). It fails only if it never comes. The change goes in the helper, so its other two callers (`:632`, `:728`) get the same rule, and the skip's reason names what was waited on. `/api/search` stays answered in Python unless the case reds again.
- **(4) 45.9's gaps:**
  - `config_loader.py:110` puts `.config_mtime` in `FCC_DATA_DIR` when it is set (read at the call). Containers are unchanged.
  - Conftest wraps `config_loader._write_merged_config` (patched on its defining module, where `save_config` looks it up at the call): when `get_config_path()` resolves to the repo's real `config.json` or `config.dev.json`, it calls `pytest.fail(...)` before anything is written. Wrapping `_write_config_atomic` alone would come too late: the rolling `config.json.bak` is written first (`:404-411`). `pytest.fail` raises an exception no `except Exception` swallows. The message says to patch `get_config_path` as `test_config_save.py` does (`:50`).
  - In `app.py`, the three start-up calls (`:155-157`) are skipped, with one printed line, when `os.name == 'nt'`, `FCC_DATA_DIR` is unset and the module isn't `__main__`. That is an ad-hoc `import app` on Windows. Prod and dev run Linux containers, and both start `app.py` as `__main__`.
  - `__pycache__` stays (Claude's calls).
- **(5) The repo-root strays:**
  - delete the empty `data/`, the 0-byte `hub.log` and the root `__pycache__/`;
  - give `state.py:99`'s handler `encoding='utf-8'` (coordinate with Group 65.4 on the same line). The python:3.9-slim image already runs with a UTF-8 locale, so the containers write the same bytes;
  - a conftest check between tests warns when a repo-root `data/` or `hub.log` appears that wasn't there when the run began, naming the test that made it. (A root `__pycache__` comes from collecting a root file, before any test runs, so it is left out.)
  - **The likely mechanism:** a backend import with the repo root as its working folder and no `FCC_DATA_DIR`. Its first log line, holding an emoji (`config_loader`'s "✅ Loaded Prod Config"), opens `hub.log` there (`delay=True`) and fails to encode, which leaves the 0-byte file; then the first locations read makes `data/` (`locations_db`'s relative fallback, `_ensure_data_dir`). The birth times fit that order: `hub.log` 0.8 s before `data/`. The 21:47 culprit isn't known; the check finds it if it is a test.
- **(6) The ordering tests:** replace each `delay=900` hold with a held answer the test releases (`hold: "list"`, then `window.__release("list")` once the newer answer has painted). Also assert that the older answer was still pending when the newer one painted, so the test can't pass without the ordering. Look at the other four 900 ms holds the same way.
- **(7) Group 54's notes:**
  - `SpoolmanHTTPFake.patch` turns a `remaining_weight` into `used_weight` as Spoolman 0.27 does (read its spool update in Spoolman's source first), and answers `remaining_weight` derived. Run every suite that uses the fake;
  - `roundtrip_bridge.py`'s body moves into `main()` under `__main__`;
  - a test's "deleted, reads 404" check by id also checks the record's name, since dev's Spoolman reuses ids. Find them and note the rule in CLAUDE.md;
  - the kept line prints the plain value (`json.loads` of the wire string when it parses).

### 68.10: the canaries see what they claim to
- **The pin (Call 3 (a)).** Read the version the page loads today (`Swal.version` on the dev dashboard). Pin the URL to that version and to the file the bare URL serves (the package's jsDelivr entry, `dist/sweetalert2.all.min.js`). Re-read `CDN_GLOBALS["sweetalert2"]` from that exact bundle's UMD line.
- **The load-order canary:**
  - the stub's queries walk elements a script built (`createElement`, `innerHTML`, `insertAdjacentHTML`) and the dummy's subtree;
  - the two tuple messages become strings;
  - a name a zero-delay timer defines is filed after the next script;
  - the pure-Python tests leave the module-wide `skipif` (the node tests carry it one by one, or the Python ones move to a sibling file);
  - `NODE_MISSING_MSG` names every node-vm check that didn't run.
- **The one-list canary:** a const holding a words string is tracked, and a later `.split(` on it is read as a split where written. A `/` right after a `)` that closes an `if`, `while` or `for` head starts a regex.
- **The write-site canary:**
  - the tuple forms join the discard check: `x, _ = writer(...)`, and a name bound and never read for a writer whose result says failure;
  - a `.requests` or `.http_retry` chain counts only when its root resolves to the imported module.
- **The contrast guard:**
  - `opacity` is modelled as group compositing: an element with opacity below 1 paints its whole subtree over what lies behind it, text and its own backgrounds alike, nested groups inside out;
  - the per-pixel filter functions (`contrast()`, `grayscale()`, `invert()`, `opacity()`, `saturate()`, `sepia()`, `hue-rotate()`) are applied in order, by the Filter Effects spec's formulas;
  - `blur()` and `drop-shadow()` stay unmodelled and are named so;
  - its header comment and CLAUDE.md's contrast paragraph are updated;
  - then the whole contrast suite runs once. An offender it finds is real: a fix that changes a look gets Derek's before / after picture first (standing order).

### 68.11: a deploy keeps a field's order
- **`setup_fields`** reads each entity's field list once per run, through `_read_field_definition`'s rule, and caches it.
  - **Skip:** a field whose definition already has the same name and type, the same `multi_choice`, and every merged choice prints "already set up" and is not POSTed.
  - **Otherwise** the POST echoes the existing `order`, `unit` and `default_value` when present and not None.
  - **A field list it can't read** falls back to today's POST, with one line saying so.
  - Add `timeout=` to its four bare requests, from the release check's notes.
- **FCC's writers:** one helper in `spoolman_api` builds a field POST from the existing definition plus the change (as `routes_config_attrs._recreate_field_payload` does), and `ensure_extra_field`'s label refresh, `update_extra_field_choices` and `ensure_filament_attributes_cleaned` use it. No new write call, so `WRITE_SITES` keeps its counts.
- **The Settings words** (`modals_config.html:61-80`) say plainly what the button does and that FCC now keeps the order. They name no code (`order: 0`, `FIELD_ORDER`).

## Tests

Every new test must fail on `95531a6` (check with `git archive` into a scratch folder). A test of a script loads it by path with every HTTP call recorded and never sent (the `utilities` fixture in `tests/test_reset_dev.py:1296-1312` is the pattern). Nothing here may run a script against a real address.

- **68.1:** a new `tests/test_by_hand_scripts_68_1.py` (offline). It checks:
  - every kept script imports with no request;
  - aimed at prod (by `DEV_SPOOLMAN_URL`, by a `config.json` naming prod, by an argument), each exits 2 before any request;
  - without `--apply` it writes nothing and says what it would write;
  - `update_from_csv.py` writes no `location` or `archived`, sends only the changed extras, and sends a text extra its old list lacked (`product_url`) as a JSON string;
  - a source canary over every tracked `.py` outside `inventory-hub/` (so `utilities/`, `setup-and-rebuild/`, the repo root and any kept old folder, but also `ptouch-data-pullers/`, `docs/` and any folder added later): a file that sends a write (`requests` post, patch, put or delete in any import form, or a `urllib.request.Request` with another method, the refresh's way) or names port 7912 or prod FCC must reach `prod_guard` (directly, or through `project_config`'s wrappers). Its allowances, each with its reason: `setup-and-rebuild/setup_fields.py` (the deploy writes prod on purpose), `ptouch-data-pullers/auto_generate_labels.py` (it reads prod on purpose: GETs only, with timeouts, `:8-11`) and `docs/readme-demo/seed.py` (it writes only the README demo's own Spoolman, asserted at `:8`). `refresh_dev_from_prod.py` needs no allowance once 68.4 makes its guards wrappers of `prod_guard`; its `http()` is not GET-only (it writes to dev Spoolman, and refuses only a write to prod's port and an address it doesn't know, `:513-529`).
- **68.2:** a new `tests/test_backup_database_68_2.py` (offline, temp folders standing in for the shares). It checks:
  - no word means exit 2;
  - `dev` refuses a folder without the marker, and `prod` a folder with one; each also refuses when the other folder breaks its rule;
  - one POST, with its timeout;
  - a failed request, or an answer with no `path`, copies nothing, though an older `.db` sits in the folder;
  - `created: false` is said;
  - the copy is named by Spoolman and backup time, never overwrites, and is checked read-only;
  - a highest-id mismatch is a warning, not success.
- **68.3:** a new `tests/test_update_sh_68_3.py` (offline). Every script `update.sh` runs exists in the repo. `update.sh` is 100755 with LF line ends in the index (`git ls-files -s`, `git ls-files --eol`; it skips without git).
- **68.4:** a new `tests/test_prod_guard_68_4.py` (offline). It checks:
  - one table of spellings: Spoolman at 7912 and 07912, on `192.168.1.29`, `TRUENAS`, `truenas.local.` and `[::ffff:192.168.1.29]`, with a path, an unreadable port; FCC at 8000 on each prod spelling, `localhost:8000` not; the share in every spelling `tests/test_reset_dev.py` already uses;
  - each of the four consumers answers the same table;
  - `dev_spoolman_url()` prefers `DEV_SPOOLMAN_URL`;
  - conftest's new refusals as functions: an `INVENTORY_HUB_URL` on each prod FCC spelling and on a host that isn't loopback (`truenas.lan:8000`) is refused, `localhost`, `127.0.0.1` and `[::1]` on any port pass; a `config.json` naming prod, with `config_loader.get_config_path` patched to a temp file, and a missing one, are refused outside `--offline` only;
  - the `INVENTORY_HUB_URL` refusal also through a `pytest --collect-only` subprocess with the bad env, which errors before collecting anything (the `config.json` one can't go that way without a file at the repo root);
  - `tests/test_reset_dev.py`'s existing cases stay green, unchanged (68.1 and 68.5 change only their own parts of it).
- **68.5:** extend `tests/test_reset_dev.py:504-511` with a temp folder (TEMP, TMP and `gettempdir()`), a drive root and a repo folder outside `.captures/`; add the pointer file's life (`stage --apply` writes it, later phases read it, `seeds` clears it, `--stage-dir` overrides it), that `init-marker` runs with no pointer and no stage folder, and the help words.
- **68.6:** a new `tests/test_print_downloads_switch_68_6.py` (offline, `_CANCEL_DEDUCT_RUN_ASYNC` False, the patterns of `tests/test_print_end_heads_hotfix.py`). With the switch off, a cancel, a completion, an ambiguous end, a queued fetch and a restart:
  - download nothing (`_download_file_bytes` patched to fail if called);
  - write no ledger entry or review card, and no new fetch record;
  - write one escaped Activity Log line per end.

  The backstop on its own: with the switch off, the real `_download_file_bytes` answers None and sends nothing (`prusalink_api.requests.get` patched to fail if called). The reader: each spelling of off, and anything else meaning on.

  With it unset, every existing print-end suite passes unchanged.
- **68.7:**
  - offline: the changed `test_offline_mode.py` list; a source check that no test's `**/*` or `**/api/**` route handler passes a request on with `route.continue_()`;
  - with the container: one test that the `page` fixture's default answers `/api/state/buffer` in the page (a POST never reaches dev), also under a later catch-all that passes requests on; one that a context harness answering the buffer itself still gets the page's saves; one that a marked test reaches dev's buffer, and the rewritten files, each run three times. Then one full browser run, where any test that relied on dev's buffer shows up red and gets `own_the_buffer(page, initial)` or the mark.
- **68.8:** a new `tests/test_throwaway_sweep_68_8.py` (offline, on `tests/spoolman_extra_fake.SpoolmanHTTPFake` with a vendor list). It checks:
  - it matches a prefixed comment, a prefixed filament name, an archived spool and a test vendor;
  - it never matches a real-looking record or `__fcc_test_vendor__`;
  - it leaves a prefixed record registered under an hour before the run began;
  - deletes go spools, then filaments, then vendors;
  - a refused delete is a warning.

  With dev's Spoolman (integration): the backfill test on its own vendor.
- **68.9:**
  - offline: the patched eject test, under a guard that fails on any connection; `.config_mtime` lands in `FCC_DATA_DIR`; a host `save_config` aimed at the real `config.json` fails the test before anything is written, its `.bak` included; a subprocess `import app` on Windows without `FCC_DATA_DIR` skips the start-up calls and writes nothing (the decoy pattern of `tests/test_host_data_dir_45_9.py:469-505`); the handler opens its file as UTF-8 (assert `state.f_handler.encoding == "utf-8"`, or write an emoji line through it in a subprocess run without `-X utf8` and without `PYTHONUTF8`: under either, the old code passes too, as the decoy test's own `-X utf8` subprocess would); the fake's `remaining_weight`; `pytest tests/roundtrip_bridge.py` collects nothing and errors on nothing; the kept line;
  - hermetic (`isolated_page`): the two ordering tests on released holds, each red when the hold is released early;
  - with the container: the two fixtures' order, and the watch item's skip branch on a page slowed in the test.
- **68.10:**
  - offline: each canary change proven red on its old form;
  - hermetic: `tests/test_contrast_guard_compositing.py` gains opacity cases (on the text, on a background, nested) and one case per filter function;
  - with the container, once: the whole contrast suite, and the load-order canary on the pinned URL.
- **68.11:**
  - offline: extend `tests/test_setup_fields_idempotent.py`, or add `tests/test_setup_fields_order_68_11.py`, on `FieldFake` taught Spoolman's rule (an omitted `order` becomes 0). A full module run keeps every field's `order`, `unit` and `default_value`, skips the fields that already match, still adds a missing choice, and creates a missing field;
  - the three `spoolman_api` writers echo the three settings;
  - `tests/test_restore_field_order.py` stays green.
- **Standing orders that apply:**
  - the write-surface table and `tests/test_spoolman_write_sites.py` for any changed write (68.11's helper adds no call);
  - the backend module rules (module-qualified calls, patch on the defining module, flat modules, Python 3.9 syntax);
  - Activity Log text escaped (68.6's line);
  - plain words in anything a person reads (68.6's line, 68.11's Settings words);
  - the contrast guard and the named sizes, for 68.11's changed words only.
- **The full run before merging**, since 68.7, 68.9 and 68.10 change the browser harness. Then one review round with the checklist's lenses "real runs and old-code proofs", "honest reads and writes" and "ordering and staleness" (`docs/agent_docs/review-checklist.md`).

## Done when

- No script in the repo can write prod by accident. A deliberate prod action names prod (`backup_database.py prod`, the deploy's `setup_fields`), and the scripts Derek let go are gone.
- `backup_database.py` copies the backup of the Spoolman it asked, proves which, and says so.
- The stub is gone, or the group's merge note says which condition still holds it.
- One prod guard serves every script and the tests, and knows prod FCC; the tests refuse a prod FCC address and a `config.json` naming prod.
- The refresh's stage folder can't sit where a cleaner empties it, lasts the whole run, and says what it holds.
- Dev's FCC downloads no print file unless switched on (per Call 2).
- No browser test writes dev's shared buffer or empties it without saying so, and refused slot scans no longer reach dev's Activity Log.
- Every throwaway record a plain run makes is found by the sweep, and no test changes a real dev vendor.
- 68.9's parts are each fixed, or recorded with why not.
- SweetAlert2 is as Call 3 says; each listed canary limit is closed; the contrast guard models opacity and the filters.
- A deploy, and FCC's own choice and label writes, leave Spoolman's field order as they found it.

## Risks

- **Prod-adjacent code.** Every script is changed by reading, and tested only with its requests recorded. A script under test must never be pointed at a real address, even dev's.
- **68.4's move of the path guard.** `tests/test_reset_dev.py` pins many spellings through the refresh's own names. Keep those names as wrappers that read the refresh's globals at the call, because the tests monkeypatch them.
- **68.6's switch on prod.** Set there by mistake, every charge would stop. Prod never reads `docker-compose.yml`, unset means on, and FCC's start says so whenever it is off.
- **68.7's default.** Every browser test's buffer changes at once. A test that seeded dev's buffer and expected the page to show it goes red until it owns its buffer with that content or carries the mark. The full run finds them. On the page instead of the context, the default would also have broken the eight harnesses that serve their own buffer on the context.
- **68.8's wider sweep** deletes more. It matches only the prefix rules, runs only on dev's address after the prod check, and its unit test pins that a real-looking record is never matched. Run at every start, it could also delete the live records of another run going at the same time; the hour's age rule keeps them.
- **68.9's Windows guard** skips the start-up migrations for an ad-hoc import on Windows. Nothing in the containers changes; a person running `python app.py` on Windows still gets them (`__main__`).
- **68.10's contrast model** may find real offenders. A fix that changes a look waits for Derek's picture.
- **68.11's skip** changes the deploy's printout ("already set up" in place of "Created/Updated."). Nothing in the repo reads those lines, but the release notes' post-deploy checks should name the new words.
- **68.1's deletions.** Git keeps every file. Check that no doc or test names a deleted file (`tests/test_reset_dev.py:1287-1358`, the write-site canary's docstring).

## Owed to CLAUDE.md at the merge

- **Testing, "A plain `pytest tests/` run is NOT offline":** the throwaway sweep now runs at the start and end of every run that reaches dev's Spoolman (no longer only with `RUN_INTEGRATION`), and covers archived spools, spools with no comment and test vendors (68.8).
- **Testing, the scripted-modal bullet ("a test that fills `state.heldSpools` calls `conftest.own_the_buffer`"):** the `page` fixture owns the buffer by default; `@pytest.mark.shared_buffer` is for a test that means dev's (68.7). The "Shared fixtures" bullet loses `with_held_spool`.
- **Testing, "Host test runs get their own data folder (Group 45.9)":** its "Still not covered" list shrinks to what 68.9 left: `.config_mtime` follows `FCC_DATA_DIR`; a host write to the real `config.json` fails the test; an ad-hoc `import app` on Windows skips the migrations; `__pycache__` stays, and why.
- **Testing, "Dev is a copy of prod":** the stage folder rules (68.5). `conftest.py`'s prod refusals are now one guard, `prod_guard.py`, and conftest also refuses an `INVENTORY_HUB_URL` that names prod FCC or isn't on this PC, and a `config.json` naming prod (68.4).
- **Architecture & Environment:** dev's FCC downloads no print file (`FCC_PRINT_FILE_DOWNLOADS=off` in `docker-compose.yml`), and how to turn it on for a live check (68.6).
- **Write surfaces, "Don't add `force_reset=True` to `setup_fields.py` lightly":** steady-state runs are also order-preserving, and they skip a field that already matches (68.11).
- **Project Conventions, the contrast standing order:** what the guard now models (68.10). **Testing, the three canaries' paragraph:** the closed limits (68.10).
- **Testing:** a "deleted, reads 404" check by id also checks the name, since dev's Spoolman reuses ids (68.9).

## Prod facts (read-only, optional)

None blocks the build.
- **Has the release carrying `e918b3f` deployed?** It gates 68.3. Prod FCC's version badge says so: its date, and its commit in the badge's tooltip. An agent can first check that `origin/main` holds `e918b3f` (`git merge-base --is-ancestor e918b3f origin/main`), which means the release was cut; only a deploy after that, which Derek starts, puts it on prod.
- **The cron job's Command** (Call 4).
- **Prod's field `order`, `unit` and `default_value`:** read-only `GET http://192.168.1.29:7912/api/v1/field/{spool,filament,vendor}`, with Derek's OK. Dev's 2026-11-13 copy shows every field at order 0 with no unit or default, so 68.11 loses nothing on prod today.
- **The share folders 68.2 relies on:** prod's `\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\backups\`, and dev's `\\TRUENAS\App_Data\Spoolman_Dev\` holding `FCC_DEV_SPOOLMAN.marker` (written by the refresh's `init-marker` on 2026-11-13). These are read-only share reads; follow the "no approval prompts while Derek is away" note for how.

## Found while grounding (not in this group's items; for the refresh to file)

> **Filed 2026-11-17 by the refresh:** 1 (b) and (d) joined 68.11's item; (c) joined 68.3's; (e) 68.8's; 4, with `export_to_csv.py`'s archived-spools question, 68.1's; 9 68.4's; 10 is a dated note on 68.6's. 1 (a), (f) and 2, 3, 5-8 were already folded into this file's design.

1. **The refresh's release-check notes that no item holds** (its `schema.json` and `deploy.json`, 2026-11-16, kept in that session's scratchpad, not in the repo). Each point about this repo's code was checked here; what Spoolman does is the check's own reading of Spoolman's source:
   - (a) `setup_fields`' field writes have no timeouts (`setup_fields.py:59`, `:84`, `:121`, `:144`; marked should-fix). Fits 68.11, and its design already adds them.
   - (b) Three field DELETEs run at every deploy (`:527-529`), expected to answer 404. A field of those names that ever came back would be erased. Fits 68.11.
   - (c) `setup_fields` prints its success line after errors, and `update.sh` checks nothing after the backup and prints COMPLETE even when a step failed. Fits 68.3 (deploy hygiene).
   - (d) Four system-managed spool extras (`container_slot`, `physical_source`, `physical_source_slot`, `fcc_pre_archive_location`) are registered only by `setup_fields`, not by FCC's start-up (`spoolman_api.py:1127-1145` against `:1897-1917`). Fits 68.11.
   - (e) `tests/test_spoolman_integration.py`'s `_ensure_extra_field` (`:53-66`) re-POSTs dev's field definitions under test labels (`:141`, `:241`). That relabels them, so FCC's start-up relabels them back, and it resets their order. Fits 68.8.
   - (f) The pre-deploy backup can be up to 5 minutes old and ages out of Spoolman's six copies in about a week. Fits 68.2's docstring; TrueNAS snapshots are already a PENDING DEREK item.
2. **`state.py:99`'s handler has no encoding,** so on a Windows host a log line with an emoji isn't written. Reproduced here; folded into 68.9 as the likely way a 0-byte `hub.log` is left.
3. **`inventory-hub/tests/debug_console.py`** makes a "Pytest-PLA" filament and spool on dev and never deletes them. Folded into 68.8 (delete it).
4. **`test_ddg.py`, `ddg_out.html` and `temp_amazon.html` at the repo root** are tracked scratch from Group 11's parser work. A root `pytest .` imports `test_ddg.py` (its `.pyc` at the root dates from 2026-11-13 19:49). It is harmless, with no network and no test. Fits 68.1 as a tidy-up, Derek's call.
5. **`ptouch-data-pullers/auto_generate_labels.py:8-11`** reads prod's Spoolman (GETs only, with timeouts) and writes QR text pointing at prod FCC's `/scan/<id>`. It is a deliberate prod reader. Folded into 68.1 as one of its canary's allowances; nothing else to fix.
6. **FCC's own field writers drop `order`** (`ensure_extra_field`'s label refresh, `update_extra_field_choices`, `ensure_filament_attributes_cleaned`'s rebuild). Folded into 68.11.
7. **The write-site canary's list of scripts that write** (`tests/test_spoolman_write_sites.py:128-135`) still names `migrate_spool_links.py` and lacks `refresh_dev_from_prod.py`. Folded into 68.1 and 68.3.
8. **The Settings "🔢 Restore Spoolman Field Order" words** name code and blame the wrong cause (`modals_config.html:61-80`). Folded into 68.11.
9. **Dev's FCC has no guard against a `config.json` that names prod's Spoolman.** Dev's container reads the same repo-root file, so a copy of `config.prod.json` over it makes dev's FCC write prod. `migrate_filament_attributes.py`'s docstring tells a person to do exactly that swap (`:50-54`). Fits 68.4: with `FCC_DEV=1`, refuse to start against port 7912. The conftest refusal covers only test runs.
10. **68.6's description of dev** is out of date since the 2026-11-13 refresh (see the Status). The buglist item's text should change with this group.
