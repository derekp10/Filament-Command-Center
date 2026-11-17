# Scoping: catch filament-accounting changes sooner (2026-11-03)

Three read-only scoping agents (workflow `wf_9771ff76-b3b`, 2026-11-03) on Derek's question after the INDX
`;EXCLUDE_E` hotfix (`main` `626a10e`): *"Is there any way to have FCC find and flag any bgcode that uses something
new … I'd like to try to prevent changes in how the systems perform from sneaking up on us like this in the future."*
and *"I'm beginning to wonder if we shouldn't keep [the logs] longer."* Filed as three Feature-Buglist.md items (New
and Unsorted, 2026-11-03) plus two ⏸️ PENDING DEREK items. File:line references are to `origin/dev` `bbc5ee7` and
will drift; the agents' measurements were taken on Derek's real print files (`.captures/indx-corrections-2026-11-03/`,
git-ignored). Each "open question" carries a default that stands if Derek doesn't answer.

## Catch print-file changes early: a per-printer print-file watch, and the 2% walk check on finished prints

Every print file FCC reads goes through one function, print_deduct._compute_cancel_usage (print_deduct.py:1055-1067 on origin/dev). That holds on every path: the live finished, cancelled and ambiguous edges, and the deferred retries. So both ideas hook in there and reuse the bytes the deduct has already downloaded and decoded, with no extra download. I replayed them on Derek's real files from all three printers (2026-06-13 to 11-03).

Idea 2, the walk-vs-footer check on finished prints, is silent on all 147 charged heads in 71 whole files with today's walker. With the walker from before the hotfix, it would have named all four heads of job 1135 (+132% to +205%). That print finished 3 hours after job 1134's cancel warnings, so in this incident idea 2 would not have been earlier. It never changes a charge.

Idea 1 has a cheap part: a scan for slicer tags FCC doesn't know, and for tag words written without their ';'. On the replay, that scan would have flagged the cause of the old INDX profile's over-charge on the INDX's first print (job 1095, 2026-09-30). With what FCC knew at the time, it would also have flagged the new ;EXCLUDE_E tags on 2026-10-22 (job 1130), against job 1134 on 2026-11-02.

The per-printer fingerprint (slicer version plus a hash of only the template lines that can move filament) logs 6 lines across 84 files in five months. A raw template hash would add 3 false alarms, each caused by nothing but the M115 firmware-version line.

The store goes in its own data/*.json via atomic_store, keyed by the Printer row's LocationID. Derek's end caps, clips and edge guards can't affect any of this: the 2% rule compares two numbers taken from the same file.

**Size:** M overall, about 10-14 hours of agent work in two steps that can each ship on their own:
- Step 1 (S, 3-4 h): the completion check plus the body tag check. No new data file.
- Step 2 (M, 7-10 h): the metadata hand-off, the per-printer store and its slicer-version / filament-move notices.

That includes one review round and an offline sweep (about 20 min). No container time and no printer time are needed.

**First step:** Step 1: S, about 3-4 h, no new data file and no metadata plumbing. All of it goes into _compute_cancel_usage (print_deduct.py:1067-1126):
- (a) Run the whole-file walk on finished prints too, and log one completion-worded line per print through _warn_parse_gap's 2% / 0.1 g rule. The charge stays untouched. This inverts the Group 56 pin at tests/test_deduct_accuracy_56.py:376-379.
- (b) Scan the decoded body for slicer tags FCC doesn't know, and for tag words written without their ';'. One WARNING per printer and word per FCC run.

Prove it on the real captures: silent on all 71 whole files except the 7 old-profile INDX files (bare EXCLUDE_E words), and naming all four heads of job 1135 with the walker from before the hotfix. Part (b) alone would have flagged the old INDX profile on job 1095 (2026-09-30) instead of the problem surfacing at job 1134 (2026-11-02).

Step 2 (the per-printer store, with its slicer-version and filament-move notices) follows in the same group.

### Findings

- One choke point. The only download and decode of a print file is prusalink_api.fetch_cancel_gcode (prusalink_api.py:123-148), and its only caller is print_deduct._compute_cancel_usage (print_deduct.py:1055-1056). The paths that reach it:
  - live completion edge: print_monitor.py:176, then print_deduct.py:1355
  - cancel edge: print_monitor.py:144, then print_deduct.py:2138
  - ambiguous end: print_monitor.py:238, then print_deduct.py:2138
  - deferred-fetch retries: print_monitor.py:745, then :942 or :947.
  The three edges each run on their own daemon thread (print_monitor.py:158-163, 192-197, 256-262). The deferred retries run inline on the monitor thread. Nothing else downloads a file except the swap split, which fetches the same file a second time (prusalink_api.py:477, called from print_deduct.py:1552). download_gcode_content (prusalink_api.py:104) has no caller. A progress_unknown ambiguous end reads no file at all (print_deduct.py:2119-2128).
- The fingerprint data is already decoded, then thrown away. decode_bgcode decompresses every metadata block and keeps only the 'filament used' footer (bgcode_decode.py:298-306). In Derek's files, all of the following comes before the first G-code block:
  - the file block holds Producer (e.g. 'PrusaSlicer 2.9.7') and 'Produced on'
  - the printer block holds printer_model (COREONE, COREONE_INDX8T, XL5IS)
  - the slicer block holds the whole config: 372-376 keys, including printer_settings_id and every template.
  The committed tests/fixtures/sample.bgcode has all three blocks (PrusaSlicer 2.9.4, COREONEMMU3, 'Prusa CORE One MMU3 0.4 nozzle').
- CPU cost on this PC (Python 3.11 / 3.14):
  - RACOON~3: 11.4 MB .bgcode, 27.1 MB of text. Decode 21.7 / 29.7 s, walk 3.0 / 3.8 s, tag scan 0.5 / 0.4 s.
  - RACOON~4 (XL): 12.8 MB, 31.9 MB of text. Decode 25.7 / 32.1 s, walk 4.0 / 4.9 s.
  - FLEXI-~2: 3.8 MB, 9.6 MB of text. Decode 10.5 s, walk 1.2-1.7 s.
  The whole 71-file census took 712 s. Every completion already pays the full decode, just to read a footer that sits in a metadata block, so the walk adds about 12-15%. Not measured: the container's Python 3.9, and the NAS CPU.
- The 2% rule applied to finished prints, with today's walker: 71 whole files and 147 charged heads (INDX 17 files / 56 heads, Core One 31 / 31, XL 23 / 60) give zero warnings.
  - XL: -20.0 mm (about 0.06 g) on every head except the one the print starts on (37 heads). It reaches -14.2% on PRUSAC~3's 0.42 g T4. The cause was not checked. The 0.1 g floor keeps it quiet.
  - Every other head is within 1.4%. This is the known last-retract gap (Feature-Buglist.md:3); the worst case is FLEXI-~2's T2 at -1.37%.
  The committed sample.bgcode (Core One MMU3 profile) walks about +1.3% and stays quiet too.
- Job 1135 (FLEXI-~2, finished 2026-11-03 00:17) with the walker from main 1d9cae4, before the hotfix:
  - RCOI-1: 7.50 g against 3.23 g (+132.2%)
  - RCOI-2: 4.63 against 1.90 (+143.7%)
  - RCOI-3: 1.07 against 0.35 (+204.5%)
  - RCOI-4: 1.14 against 0.41 (+176.9%)
  Today's walker is silent on it. Following the walk would have charged 14.34 g instead of the correct 5.89 g. The INDX ran nothing between 2026-10-22 18:28 and 2026-11-02, so in this incident a completion check would only have fired 3 h after job 1134's cancel warnings.
- The old INDX profile's cause was visible in the files themselves. Its tool-change template writes EXCLUDE_E_START / EXCLUDE_E_END as bare lines, with no ';'. That holds in all 25 INDX files sliced 2026-10-01 to 10-20. The decoded bodies carry those lines at every re-pick-up: 471 pairs in the raccoon capture (the first at racoon_decoded.gcode:15332-15334), 1000 pairs in SPIRIT~4. No other bare tag-shaped line appears in any template of 85 files, or in any of the 71 decoded bodies. PrusaSlicer reads a tag only after a ';', so the footer counted the moves between the words. A check for this would have fired on job 1095, the INDX's first print (review 2026-09-30 19:01). It flags the cause; the grams still need a scale, because Prusa's premise that the lock moves no filament has not been checked on a scale.
- INDX history, read from the files:
  - 2026-10-01 to 10-20: PrusaSlicer 2.9.6, the bare-word tool-change.
  - 2026-10-22, SPACER~1 (job 1130, cancel review at 13:26:48): tool-change rewritten, with 10 ;EXCLUDE_E tags and a new restore move. Start G-code changed only in its M115 firmware-version line.
  - SPACER~3, the same afternoon: M115 changed again, plus a fan-control regex in the layer G-code.
  - 2026-11-02, FLEXI-~1 (job 1134): PrusaSlicer 2.9.7 (released that day), same filament moves. The filament start G-code changed only pressure advance and E-motor current.
  The printer preset name changed three times ('… HF0.4 nozzle' → '… 7X ColorMix' → '… HF0.4 nozzle' → '… - All 0.25 nozzle'), so a preset name can't serve as a fingerprint.
- Noise check: I replayed 84 files in slicing order (INDX 30, Core One 31, XL 23). With a hash of only the template lines that can move filament, the replay gives:
  - 4 slicer-version lines: Core One 2.9.6 on 07-02, XL 2.9.6 on 07-03, XL 3.0.0-alpha11 on 09-12, INDX 2.9.7 on 11-02.
  - 2 'moves changed' lines: INDX tool-change on 10-22, and the XL alpha file on 09-12, where the tool-change script was gone and the colour-change gained 'G1 E0.3 F1500 ; prime after color change'.
  - 0 filament-template lines.
  A raw text hash adds 3 false 'moves changed' lines (Core One 07-02 and 09-12, INDX SPACER~3). Each one is nothing but the M115 line, plus the fan regex once. The XL going back to 2.9.6 after the alpha file raises nothing when FCC remembers every version it has seen.
- PrusaSlicer's tags. GCodeProcessor.cpp at version_2.9.6 and version_2.9.7 has the same lists:
  - Reserved_Tags: TYPE:, WIPE_START, WIPE_END, HEIGHT:, WIDTH:, LAYER_CHANGE, COLOR_CHANGE, PAUSE_PRINT, CUSTOM_GCODE, _GP_FIRST_LINE_M73_PLACEHOLDER, _GP_LAST_LINE_M73_PLACEHOLDER, _GP_ESTIMATED_PRINTING_TIME_PLACEHOLDER.
  - Custom_Tags, new in 2.9.6 and not in version_2.9.5's source: FLUSH_START, FLUSH_END, EXCLUDE_E_START, EXCLUDE_E_END.
  Each tag is matched as a prefix (boost::starts_with in process_tags). In process_G1 only m_exclude_e keeps E out of the count. m_flushing moves E to the per-extruder flush figure, which the footer still includes; every INDX footer equals a walk that counts flush. m_wiping only sets the move type.
  Derek's files also carry ;BEFORE_LAYER_CHANGE, ;AFTER_LAYER_CHANGE, ;Z: and, once at the first tool select, ;_TOOLCHANGE_TIME<n> and ;_TOOLCHANGE_END. The 2.9.7 release notes list only libbgcode security fixes. Not checked: the source of 3.0.0-alpha13 (not at the same path).
- A strict tag shape works on the real files. The shape: ';', then capitals or underscores right after it (a single capital only before ':'), optional digits, then end of line, ':' or a blank. With the lists above plus those five markers counted as known, a body scan finds no unknown tag in any of the 71 decoded bodies. The shape skips Derek's template comments, such as ';G29 P1 X150 …', ';PET-family …', ';low-temp …' and '; RETRACT AFTER TOOLCHANGE START'.
- Behavior pinned today, and what must change with it:
  - tests/test_deduct_accuracy_56.py:376-379 pins that a completion says nothing about the walk. The Group 56 task file records no reason for this.
  - 32 stubs of fetch_cancel_gcode in 8 test files return only {gcode, fraction}, so the hook must accept a result with no metadata.
  - tests/test_completion_deduct.py:271-291 walks 10 mm against a 20 mm footer, so it will start logging the completion line. It doesn't assert on logs.
  - conftest.py:2012-2040 is the precedent for keeping a store out of data/ during tests.
  - The escape canary covers only 4 modules (tests/test_deduct_accuracy_56.py:565-578).
- End caps, clips and edge guards (Derek's question). The 2% rule and the fingerprint never see a scale reading: _warn_parse_gap compares FCC's walk of a file with that same file's footer (print_deduct.py:1187-1192). Accessories on a weighed spool can't trip it or hide anything from it. They matter only to a weigh-in comparison (idea 3).
- Retention:
  - The Activity Log keeps 50 entries in memory (state.py:125).
  - hub.log keeps 5 x 1 MB (state.py:76).
  - A fingerprint store would keep 'since when, first file, first job' for each printer for good.
  PrusaLink's job file.meta is already latched (print_monitor.py:366-370, prusalink_api.py:610) but never read. Not checked: whether it names the slicer version.
  My replay scripts and their outputs are in D:\claude-tmp\claude\d--My-Documents-Documents-3D-Printing-Filament-Command-Center\d001fa7e-fe43-49c5-89fb-535d040ff533\scratchpad\fpscope (notice_sim_allow.py, body_census.py, completion_check_sim.py, gap_census.py, timeline.py). The Core One and XL files exist only in that session scratchpad (c1_dl, xl_dl), not in .captures.

### Design

- Where to hook. Hook once, in _compute_cancel_usage, right after the content arrives (print_deduct.py:1067). Put it before the walk warnings, so the log shows the cause first. Both checks are best-effort: each sits inside its own try, as _warn_parse_gap already does (print_deduct.py:1169/1203). Neither may change usage_map or the terminal answer.
- Idea 2, the completion check.
  - In the footer branch (print_deduct.py:1069-1071), also run measure_filament_usage(content, [1.0]) inside a try. Today a completion never walks, so a walk failure must not be able to stop one.
  - At :1125, call _warn_parse_gap in a completion mode.
  - Keep the rule as is: _PARSE_GAP_PCT 2.0 and _PARSE_GAP_MIN_G 0.1 (print_deduct.py:1136-1140), covering charged heads and footer heads the walk can't see.
  - Log one line per print listing every head, since what's wrong is the file, not a charge.
  - Open the line with today's words, "FCC's G-code walk of '<file>' came to…". That keeps the PENDING DEREK note (Feature-Buglist.md:22) and the test helper _gap_lines matching.
  - Close it with: 'This finished print was charged the slicer's figures, so its charge stands, but FCC reads this file differently from the slicer: a cancelled print like it would be charged wrong.'
- A completion WARNING never changes the charge and never opens a review. This is Group 56's rule (print_deduct.py:1161-1162). On a completion the footer is the slicer's own count. Every gap seen so far was FCC misreading the file: following the walk on job 1135 would have charged 14.34 g instead of 5.89 g. The one time the footer itself was wrong (the old INDX profile), the walk and the footer agreed and there was no gap.
- The tag check, the cheapest part of idea 1.
  - Scan the decoded body for two things: tag-shaped comments whose name FCC doesn't know, and tag-shaped words (capitals with an underscore) alone on a line with no ';'. Step 2 adds the templates to the scan.
  - The known list is the 2.9.6/2.9.7 lists plus the five markers above, each entry with a one-line reason.
  - A tag joins the list only together with a test of what the walk does with it. Copying 2.9.6's list wholesale would have marked EXCLUDE_E 'known' while the walk still counted it.
  - One WARNING per printer and word: kept in memory in step 1, in the store in step 2.
- Metadata (step 2).
  - decode_bgcode returns the metadata it already decompresses, as 'meta' (bgcode_decode.py:298-306, 330-331).
  - fetch_cancel_gcode passes it on (prusalink_api.py:138-145).
  - For plain .gcode, it reads the '; generated by …' first line and the '; prusaslicer_config = begin … end' block at the end.
  - The producer is normalised ('PrusaSlicer 2.9.6+win64' becomes 'PrusaSlicer 2.9.6'). Another slicer's name is kept as written.
- The fingerprint, per printer.
  - What it holds: producer, printer_model, and a short hash per template.
  - Which templates: start, end, tool-change, layer, before-layer, colour-change, pause, custom and between-objects, plus the filament start and end templates.
  - Which lines count: only lines that can move filament. That means an E word on G0-G3, or G92, M82/M83, G90/G91, G10/G11, M200, M221, M600, M701/M702, G27 with R, a tool select (a line or script string that starts with T), a tag-shaped comment, or a bare tag word.
  - The preset name is reported in the notice but not hashed.
- Notices: at most one line per file. Outside text is escaped with html.escape(…, quote=False); the new module can't import print_deduct._esc without a cycle.
  - A printer's first file is a silent baseline, unless the tag check finds something.
  - Filament lines never seen on this printer: a WARNING. It names the templates that changed against the last file, plus the file, slicer and profile, and says FCC's charges for this printer may need checking, so weigh a spool after its next print.
  - A slicer version never seen on this printer, with filament lines already known: an INFO line.
  - A version or fingerprint already seen: nothing.
  - A file made for another printer_model: a WARNING.
  - Unknown tags and bare words are named in whichever line fires.
- What it would have said on the real dates.
  - 2026-09-30 19:01, job 1095 (both steps): "⚠️ 🦝 Core One INDX: '/usb/RACOON~1.BGC' has EXCLUDE_E_START and EXCLUDE_E_END on lines of their own without the ';' that makes them PrusaSlicer tags, so the slicer counts the moves between them as filament used (and so does FCC). Check the printer profile's tool-change G-code."
  - 2026-10-22 13:26, job 1130 (step 2): "🔎 🦝 Core One INDX: '/usb/SPACER~1.BGC' moves filament differently from this printer's earlier files: its tool-change G-code changed (still PrusaSlicer 2.9.6; profile 'Prusa CORE One INDX 8T HF0.4 nozzle'). It uses slicer tags FCC doesn't read: ;EXCLUDE_E_START, ;EXCLUDE_E_END. FCC's charges for this printer may need checking." The sentence about tags appears only with what FCC knew then; today's list knows those tags.
  - 2026-11-02 21:23, job 1134 (step 2, INFO): "🔎 🦝 Core One INDX: '/usb/FLEXI-~1.BGC' is the first file on this printer from PrusaSlicer 2.9.7 (until now: PrusaSlicer 2.9.6); its filament moves match files FCC has read before." The existing three cancel warnings follow it.
  - 2026-11-03 00:17, job 1135 (idea 2, with the old walker): one line naming RCOI-1 to RCOI-4 with the figures above.
- The store.
  - A new flat module, print_file_watch.py, writing data/print_file_watch.json. data/* is already in .gitignore and .dockerignore.
  - Written via a tmp file and atomic_store.replace_with_retry (atomic_store.py:29-45), under its own threading.Lock. This is the print_deduct_ledger pattern (print_deduct_ledger.py:31-61).
  - Written only when something new is seen. At most 20 fingerprints per printer, each with its first file, job and time.
  - Not on the locations.json Printer rows. Those are user data under locations_db._WRITE_LOCK (locations_db.py:46), saved with verify and orphan checks, exported, and reset by reset-dev, and a write at every print end would churn them. Not in config.json either, because of the bind-mount EBUSY trap.
  - Keyed by the Printer row's LocationID, found the way the heartbeat finds it: the row that lists the printer's first head (locations_db.printer_owning_toolhead, locations_db.py:1335; routes_state_pulse.py:509-513). If no row lists it, fall back to the Name. A rename then keeps the history (cf. Group 44.2, Feature-Buglist.md:358).
- Failure handling.
  - An in-memory 'already said' set backs the store. Without it, an unwritable disk would repeat the line every time the deferred loop retries a raising deduct (once per tick).
  - An unreadable store logs one WARNING and starts again.
  - A result with no 'meta' skips the fingerprint and still runs the body check. That covers the 32 old test stubs and a decode that lost its blocks.
- Tests and docs that change with it.
  - An autouse conftest fixture redirects the store path, as conftest.py:2012-2040 does for attr_migration.
  - The new module joins the escape canary (tests/test_deduct_accuracy_56.py:565-578).
  - CLAUDE.md gets a backend-module-map row. The print_deduct write-surface row's 2% sentence is widened to cover completions.
  - atomic_store's docstring lists the fifth store.
  - Feature-Buglist.md:22 is broadened to cover finished prints, and a 🔎 watch-for line is added beside it.
- Optional, later: stamp the fingerprint key on the job's ledger entry (print_deduct.py:585). A future correction would then know which slicer and profile each charge came from without pulling the original file, as the 2026-11-03 corrections had to.

### Hook points

- `inventory-hub/print_deduct.py`:1067: Content in hand for every path that reads a file (completion, cancel, ambiguous, deferred). Call the file watch here, best-effort, before any walk warning.
- `inventory-hub/print_deduct.py`:1069-1071: Completion footer branch: add measure_filament_usage(content, [1.0]) inside a try, for the check only; usage_map stays the footer.
- `inventory-hub/print_deduct.py`:1125-1126: Existing _warn_parse_gap call: pass a completion mode when use_footer is set.
- `inventory-hub/print_deduct.py`:1136-1204: _PARSE_GAP_PCT, _PARSE_GAP_MIN_G and _warn_parse_gap: same rule; completion wording, one line per print, still opening with "FCC's G-code walk of".
- `inventory-hub/bgcode_decode.py`:298-306, 330-331: Metadata blocks are decompressed and dropped apart from the footer. Keep their key=value pairs and return them as 'meta' (step 2).
- `inventory-hub/prusalink_api.py`:138-145: fetch_cancel_gcode returns only gcode and fraction. Pass 'meta' on; for plain gcode, parse the '; generated by' line and the '; prusaslicer_config' block (step 2).
- `inventory-hub/print_deduct.py`:1355-1356, 2138-2140: deduct_completed_print and _create_pending_cancel_review call the compute. No change; these are the completion and cancel/ambiguous entry points the hook covers.
- `inventory-hub/print_monitor.py`:745, 942-948: Deferred fetches run inline on the monitor thread, so the added walk on a locked completion's retry lands here. Live edges run on daemon threads (158-163, 192-197, 256-262).
- `inventory-hub/locations_db.py`:1335: printer_owning_toolhead: the store key (Printer row LocationID), used as routes_state_pulse.py:509-513 does.
- `inventory-hub/atomic_store.py`:1-3, 29-45: replace_with_retry for the new store's write; the docstring lists the stores.
- `inventory-hub/print_deduct_ledger.py`:31-61: Pattern to copy: _PATH tests can monkeypatch, a module Lock, _load/_save, a bounded size.
- `inventory-hub/tests/conftest.py`:2012-2040: Autouse precedent for keeping a store out of data/. Add the new store's path.
- `inventory-hub/tests/test_deduct_accuracy_56.py`:376-379, 565-578: The pin idea 2 inverts on purpose, and the escape canary's module list (plus its floor count).
- `inventory-hub/print_deduct.py`:585: Optional: stamp the fingerprint key on the ledger entry in _record_applied_deduct.
- `Feature-Buglist.md`:22: PENDING DEREK 'FCC's G-code walk' line: say it now also appears after finished prints; add a 🔎 watch-for line.
- `CLAUDE.md`: Backend module map: new print_file_watch.py row. The print_deduct write-surface row's 2% sentence covers completions.

### Tests

- Invert tests/test_deduct_accuracy_56.py:376-379. Run _gap_file() (XL-2 walks +10%) through _cancel_usage(use_footer=True). Expect one completion-worded WARNING naming XL-2 (11.00g against 10.00g, +10.0%), with the file name escaped, and the charge still {0: 10.0, 1: 10.0}. Red on base: the base logs nothing (that is its pin).
- A completion inside the rule stays quiet. Cases: +1.5% on a head; a 29 mm (0.09 g) start-G-code gap on a 4 g print; the XL's 20 mm (0.06 g) on a 2.31 g head. Guard test; prove it can fail by dropping the 0.1 g floor.
- A footer head the walk can't see, on a completion: it is named ('a cancelled print like it would charge this head nothing') and is still charged its footer grams. Red on base.
- The check can never stop a charge. Patch measure_filament_usage to raise in the footer branch: expect the same usage_map, no terminal answer, and the footer charged. Guard; prove it by removing the try.
- Through the real deduct_completed_print, with Spoolman faked as test_completion_deduct.py does, on a file whose walk is 2.5x its footer. Expect applied grams equal to the footer, ledger grams equal to the footer, and no review card. Guard for the never-changes-the-charge rule.
- Capture test (skips when .captures is absent, as test_exclude_e_tags.py:239-240 does). Run FLEXI-~2.BGC with _EXCLUDE_E_TAG_RE patched to match nothing: expect one line naming RCOI-1 to RCOI-4 (7.50/3.23, 4.63/1.90, 1.07/0.35, 1.14/0.41). With the real walker: nothing. Red on base.
- Tag shapes, as a table of real lines.
  - Tags: '  ;EXCLUDE_E_START', ';TYPE:External perimeter', ';WIDTH:0.45', ';Z:0.2', ';_TOOLCHANGE_TIME12.500000', ';FLUSH_START'.
  - Not tags: ';G29 P1 X150 Y0 W100 H20 C ; probe near purge place', ';PET-family (PET/PETG/*-CF...)…', ';low-temp materials…', ';0.2', '; Change Tool0 -> Tool1 (layer 19)', ';-------Purge Station specific Gcode Start-----', '; RETRACT AFTER TOOLCHANGE START'.
  - Bare words: 'EXCLUDE_E_START' alone on a line, as at racoon_decoded.gcode:15332. Not 'G1E1.6F1200' or 'T0 S1 L0 D0'.
  Red on base: the function doesn't exist.
- Feed a made-up unknown tag (';PURGE_START'), or a bare 'EXCLUDE_E_START' line. Expect one WARNING for that printer, with the file name escaped. A second file on the same printer logs nothing; another printer logs it once. Red on base.
- Capture census (skips when absent). Run every whole file in .captures: INDX, raccoon, flexi, and the Core One and XL files once they are copied in from the session scratchpad. Expect no unknown tags, bare words only in the 7 old-profile INDX files, and the completion check silent on all. Red on base.
- (Step 2) decode_bgcode keeps the metadata. On sample.bgcode expect Producer 'PrusaSlicer 2.9.4', Produced on '2025-12-24 at 02:18:21 UTC', printer_model 'COREONEMMU3', printer_settings_id 'Prusa CORE One MMU3 0.4 nozzle', and the template keys. Red on base: no 'meta'.
- (Step 2) fetch_cancel_gcode passes the metadata on, for two inputs:
  - a synthetic .bgcode, built with test_bgcode_decode.py:89-92's _synth_bgcode plus file, printer and slicer blocks
  - a plain .gcode with '; generated by PrusaSlicer 2.9.6+win64 on …' and a '; prusaslicer_config = begin … end' block.
  Expect producer 'PrusaSlicer 2.9.6'. Red on base.
- (Step 2) Filament-line hash, as a table from the real diffs.
  - Unchanged by: 'M115 U6.9.2+16336' to 'U7.0.1+16905', 'M572 S0.052' to 'S0.038', 'M906 P2', the fan regex '(PET|CPE|PCTG)/' to '(PET|CPE|PCTG).*/', and M104/M109 lines with 'T{initial_tool}'.
  - Changed by: an edited 'G1 E{deretract_length}', an added ';EXCLUDE_E_START', bare EXCLUDE_E becoming tagged, 'G27 … R8', 'T{next_extruder}', a script string '"G1 E" + x', and 'G1 E0.3 F1500 ; prime after color change'.
  Red on base.
- (Step 2) Notice rules, with the store in tmp:
  - baseline: silent
  - the same file again: silent
  - filament lines changed: one WARNING naming the template
  - that fingerprint seen again: silent
  - a new slicer with the same lines: one INFO
  - back to an older slicer: silent
  - another printer_model: WARNING
  - two threads handing in the same new file: one line.
  Red on base.
- (Step 2) Capture replay of the 30 INDX files in slicing order. Expect exactly three lines:
  - a bare-word WARNING at the first file (RACOON~1)
  - one WARNING at SPACER~1 for the tool-change; with the pre-hotfix known list it also names ;EXCLUDE_E_START and ;EXCLUDE_E_END
  - one INFO at FLEXI-~1 for PrusaSlicer 2.9.7.
  Nothing else. Red on base.
- (Step 2) Store key and failures:
  - a renamed printer keeps its history
  - a printer no row lists is keyed by name
  - an unreadable store logs one WARNING
  - an unwritable store doesn't repeat the line on the next retry
  - a result with no 'meta' (the 32 existing stubs) raises nothing.
- Isolation canaries: during tests the store path is under tmp (red if the autouse fixture is removed), and the new module is in the escape canary list. Every test above runs under --offline; none needs the container or a printer.

### Risks

- Monitor-thread stall. A finished print locked behind its finish screen is retried on the monitor thread, and it would now also walk there. On this PC that adds 3-5 s for a 27-32 MB file, on top of the 22-32 s decode it already does; no printer is probed meanwhile. Live completions walk on their own daemon thread. NAS timing not measured.
- CPU and memory. The walk, like the decode, is pure Python under the GIL, so the dashboard shares the CPU for those seconds. Its line list is about the size of the decode's own (bgcode_decode.py:325), and it now runs on completions too, so finished prints on three printers at once stack up. Neither was measured.
- Test churn. The Group 56 pin (test_deduct_accuracy_56.py:376-379) must be inverted on purpose. Synthetic completion files whose footer doesn't match their body (test_completion_deduct.py:271-291) will log the new line. Audit any test that counts log lines in the offline run.
- False completion lines. The XL's constant -20 mm on later heads (0.06 g in PLA) stays under the 0.1 g floor. A filament denser than about 2.1 g/cm³ (metal-filled, say) used for a few grams would cross both limits and log a false line.
- Heuristic gaps.
  - The filament-line filter is an allow-list: a new firmware command that moves filament (as G27's R does) is missed until someone adds it.
  - The tag shape misses a lower-case or spaced tag.
  - The body scan sees only files FCC manages to download.
  - Bare words show in the body only where a tool is picked up again; step 2's template scan closes that gap.
- Store hazards.
  - A lost or reset store re-baselines silently, so a change made meanwhile is never announced.
  - Without the conftest redirect, tests would write the real data/ store.
  - Without the in-memory backup, an unwritable store would repeat a line every retry tick.
- Escaping. The slicer version, profile names and file names are outside text going into an HTML log (CLAUDE.md, Groups 49 and 56.4). The canary checks only the modules it lists, so the new module must be added to it.
- Derek's own edits. FCC can't tell his profile edits from Prusa's updates, so each edit that touches a filament move logs one line at its first print. That is intended.
- Name vs id. The ledger and the other deduct stores are keyed by printer Name (Group 44.2), while the new store is keyed by LocationID. After a rename they disagree about history. Harmless.

### Open questions (for Derek; defaults stand)

- [His call] How loud should "this printer's files changed" be?
  What: the first time a print file arrives from a slicer version FCC hasn't seen on that printer, or one whose printer profile moves filament differently, FCC writes one line.
  Where: the Activity Log and hub.log only.
  Real example: on 2026-11-02 the INDX's first PrusaSlicer 2.9.7 file had the same filament moves as before. On 2026-10-22 its first file from the new profile had a different tool-change.
  Options:
  (a) version-only as a plain info line, moves or tags in amber
  (b) both in amber
  (c) no line at all for version-only.
  Recommendation: (a). A version bump alone changed nothing in 4 of 4 cases on his printers, and the moves line is the one to act on.
  Default: (a).
- [His call] Should the first file FCC reads on each printer after this ships say anything?
  Example: the XL's next print after the release.
  Options:
  (a) silent, just remembered, unless the tag check finds something
  (b) one plain line per printer, e.g. 'FCC now knows how the XL's files are made: PrusaSlicer 2.9.6, profile …'.
  Recommendation: (a), less noise. The record is in the store either way.
  Default: (a).
- [Needs his OK] When a finished print's file reads differently from the slicer, how many lines?
  Option 1: one line per print naming every head. Job 1135 would have been one line covering RCOI-1 to RCOI-4.
  Option 2: one line per head, as cancels do today. Job 1135 would have been four lines.
  Recommendation: one per print, because the charge isn't affected and it's about one file.
  Default: one per print.
- [His call, can wait] Should what FCC knows about each printer's files show anywhere besides the log?
  Example: Settings → Printer Connections showing 'Files: PrusaSlicer 2.9.7, profile “… All 0.25 nozzle”, since 2026-11-02'.
  Options:
  (a) log only for now
  (b) a read-only line in Settings
  (c) a tooltip on the printer in Printer Status.
  Recommendation: (a), and revisit with the phone view.
  Default: (a).

### Derek's legwork

- None needed to build or test these two checks. They compare two numbers taken from the same file, and the replay runs on the 85 files already pulled off the printers. Claude copies the Core One and XL files from the session scratchpad into .captures before that scratchpad is cleared.
- After it ships (to add as a PENDING DEREK watch-for line): the next time you update PrusaSlicer or a printer profile, look in the Activity Log after the first print with it for the 🔎 line. Tell Claude if it was missing or didn't make sense.
- End caps, filament clips and edge guards don't touch these checks or the 2% rule, because no scale reading goes into them. They matter only for idea 3 (weigh-in drift). When that's built, weigh one end cap, each clip version and one set of edge guards once, and say which of them you usually leave on when you weigh.

## ⚖️ Weigh-in drift: each weighing says what FCC expected, and weighed spools become a per-printer accuracy check (with known accessory weights)

When Derek weighs a spool, FCC knows two numbers: what it expected the spool to hold and what the scale says. Today every weight write reaches the server as a bare used_weight: a scale reading, a hand charge like his +61.32 g, or a typed correction. All of them log the same '✏️ Weight updated' line. Per-spool charge history exists only in hub.log, and the deduct ledger keeps only a total per job, with no spool ids.

The recommendation has three steps:
(1) The page says what each write was: Gross or Net is a weighing, Additive or Set Used is a hand edit. This comes from Phase 2's own <WeightEntry> payload, which already has the mode. The log line then says 'FCC expected X g; the scale says Y g'.
(2) A small local journal (data/weigh_journal.json) records each weighing and the FCC charges between weighings, per toolhead. Two weighings of one spool then make a drift sample. A sample counts for a printer when that printer did all the charging. FCC warns when a printer's weighed spools drift more than ±5% over enough grams.
(3) Known accessory weights (cap and clip, edge guards) become settings, ticked per weighing in <WeightEntry>'s Gross mode.

On Derek's question: accessories cannot affect the 2% check, because it compares two figures read from the print file and never reads a scale. They do affect three things:
- a weighing's recorded remaining, by their full weight;
- the empty-spool weight saved after a run-out, which every later spool of that filament inherits;
- a drift sample, whenever they were on at one weighing and off at the other.

The old INDX over-charge (+126.29 g on 13 spools, up to +20.30 g on one) was well above the scale's ±1 g. But none of those spools had been weighed since their jobs, so this check only helps if spools get weighed.

**Size:** M overall, about 14-20 h in three steps:
- Step 1 (weighing vs edit, the 'FCC expected' line, the two prompts' accessory reminder): S, ~3-4 h.
- Step 1b (the wizard's two scale paths): S, ~1-2 h.
- Step 2 (journal, charge hooks, samples, /api/weigh_drift, the WARNING): M, ~6-8 h.
- Step 3 (accessory weights and buttons, after Derek's measurements and a picture): S-M, ~4-6 h.
- Later and optional (a window after a picture, weighing nudges, a cross-printer fit): +3-5 h.
Estimates here have run ~30% low before.

**First step:** Make each weighing say what it was and what FCC expected. This is S (~3-4 h), with no new file, no deduct change and no new UI:
- Quick Weigh (inv_weigh_out.js:1228-1238) and the weigh-out row (:975-982 and its Net fallback :907-920) pass weigh = {source, mode, reading, tare, tare_skipped} through saveSpoolWeight (:990), which posts {id, updates, weigh} (:1031-1038). tare_skipped is added to <WeightEntry>'s payload (weight_entry.js:385-426).
- api_spool_update (routes_inventory.py:1458-1489) validates the key and passes it to _log_manual_weight_change(spool_id, pre, post, weigh) (:987-1029).
- That function words a Gross or Net weighing as '⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). FCC expected 654.7 g: 0.3 g heavier.' and Additive or Set Used as '✏️ Weight edited by hand', so Derek's +61.32 g reads as a hand charge. A request without the key keeps today's line byte for byte.
- The two empty-spool prompts (weight_utils.js:248, inv_details.js:1566) say to take off any clip, cap or edge guards first.
It is useful the same day: every weighing shows how far off FCC's record was, and it leaves a structured trail in hub.log until step 2's journal takes over.

### Findings

- The 'Unified weight-entry component' that CLAUDE.md waits for has already shipped. Phase 2 landed 2026-04-27 as Group 12 (completed-archive.md:1327-1333), and Group 31 extended it on 2026-07-05 (completed-archive.md:645-649). That buglist item no longer exists on origin/dev. CLAUDE.md:176 (origin/dev) still says Phase 2 'will build' it and 'Don't add new weight-entry UI before Phase 2'. CLAUDE.md:174 also lists mark_printed as weight-touching, but it writes only extra.needs_label_print (routes_print_queue.py:146-148, 157-159). Read the rule as Group 31 did: new weight input goes through <WeightEntry> (weight_entry.js) and computeUsedWeight (weight_utils.js:130-224), never a new form.
- Where a weight enters FCC, and whether it is a measurement:
  (1) Quick Weigh: the ⚖️ on a spool card (ui_builder.js:251/271/553) → openQuickWeigh (inv_weigh_out.js:1189-1246) → <WeightEntry> → saveSpoolWeight → POST /api/spool/update (inv_weigh_out.js:1031-1038). Gross is a measurement (a scale reading with the spool); Net is a measurement if read off the scale; Additive and Set Used are edits.
  (2) Bulk Weigh-Out list (CMD:WEIGH, inv_cmd.js:1612; deck button dashboard.html:286): saveWeighOutRow (inv_weigh_out.js:863-988), one modal-level mode, Net by default (:11). Same split.
  (3) Wizard edit: the raw Scale box (wizardCalcUsedWeight, inv_wizard.js:1224-1254) is a gross measurement; '⚖️ Weigh from scale…' (wizardOpenWeightEntry :1316-1382) is <WeightEntry>; the Remaining / Used / Recent-usage boxes (:1256-1301) are edits. All of them collapse into used_weight (:3820) → /api/edit_spool_wizard (:4059-4065) → routes_inventory.py:1238, logged at :1262-1263.
  (4) Wizard create: a new spool's starting weights, possibly from a scale (31.1 derived_initial). It logs no weight line (routes_inventory.py:837-980; spoolman_api.create_spool :726-747).
  (5) Missing-tare prompt (weight_utils.js:242-360): measures an empty spool.
  (6) Post-archive '📦 Spool archived — record the empty weight?' (inv_details.js:1513-1701): a measured empty weight saved to the FILAMENT (:1659-1662) and optionally the brand (:1677-1680).
  (7) Prusament apply (routes_scan.py:38-104): the maker's capacity and empty weight, not a reading; it has its own log line (:97-100).
  (8) Backfill (print_deduct.py:200-269, write at :252): copies a filament's empty weight onto its spools; not a reading.
  (9) mark_printed: not a weight surface.
  (10) Edits made in Spoolman itself: invisible to FCC. Not checked: what Spoolman's own UI records for a weighing.
- The page knows the mode but drops it. <WeightEntry>'s onSubmit payload carries mode, raw_value, value, empty_spool_weight and capped (weight_entry.js:414-426). Quick Weigh sends only {used_weight} (inv_weigh_out.js:1229-1237). The weigh-out list sends {used_weight}, or {remaining_weight} on its fallback (:982, :919). saveSpoolWeight posts {id, updates} (:1031-1038), and the server writes one line for all of them (routes_inventory.py:1016-1020). So a scale reading and Derek's '+61.32 g twice' hand charges read the same in the log. That line already shows remaining before ➔ after, which for a weighing is expected ➔ measured. What it lacks: whether it was a weighing, the reading and empty-spool weight behind it, and anything since the previous weighing.
- Default modes: Quick Weigh opens in Additive (inv_weigh_out.js:1224; Settings 'Default weigh-in mode' defaults to 'additive', config_schema.py:109-112). A browser's stored default wins (weight_entry.js:128-131). The weigh-out list opens in Net (inv_weigh_out.js:11). Not checked: which modes Derek actually uses.
- 'Expected' is already available on the server. api_spool_update reads the spool right before the write (routes_inventory.py:1466). stock_report.remaining_g (stock_report.py:172-185) gives grams left with the fallbacks the Low stock list uses. The deduct test harness (tests/deduct_wire_harness.WeightWireSpoolman) does not derive Spoolman's remaining_weight, so the journal should use remaining_g, which falls back to capacity − used.
- A Gross reading above the spool's capacity is clamped on the page (weight_utils.js:212-222: used < 0 → 0, capped 'low'). An overfilled new spool's extra grams therefore never reach the server; only a raw reading sent from the page keeps the measurement.
- The deduct ledger can't attribute drift to a spool. It keeps one (printer, job) entry with a gram total: no spool ids, no time, the newest 200 entries only (print_deduct_ledger.py:31-33, 73-80; written at print_deduct.py:585-586, 2856-2858, 2905-2907). Per-spool charges exist only as Activity Log lines (print_deduct.py:466-469, 2726-2728). hub.log rolls over at 1 MB and keeps 5 old files (state.py:76).
- Every production charge passes one of two tails:
  - _record_applied_deduct (print_deduct.py:522-607), which follows each _apply_usage_to_printer call (1254→1276, 1441→1471, 2396→2413). Its details carry sid, grams, remaining, toolhead and position (:470-471).
  - _low_stock_after_review (:2878-2887; called at :2798, :2830, :2859) for a 🛑 Review Apply. Its applied rows carry sid, grams and remaining but no toolhead (:2669-2671, :2729-2733); the review's rows do (rec_rows, :2584).
  A deduct that raises after it began writing (CompletionMayHaveCharged, :53, :1445, :1476) reaches neither tail.
- The 2% rule is file-only. _warn_parse_gap (print_deduct.py:1157-1204; _PARSE_GAP_PCT = 2.0 and _PARSE_GAP_MIN_G = 0.1 at :1136-1140) compares FCC's whole-file G-code walk with the slicer's footer, per head, on cancels only. No scale reading enters it, so a cap, clip or edge guard can't change it.
- Where accessories do matter:
  (a) Gross mode subtracts only the empty spool (weight_utils.js:189-197), so anything else on the spool is recorded as filament.
  (b) The post-archive prompt asks for 'the now-empty spool' and saves it for every future spool of the filament (inv_details.js:1559-1567), optionally the brand's too. Edge guards left on there make every later Gross weighing of that filament read LOW by their weight. A near-empty spool can then read below the empty weight: used is clamped to the total and the spool is auto-archived with filament still on it (weight_utils.js:195, 217-219; inv_weigh_out.js:975-977, 1233-1234; read from code, not run).
  (c) Grams recorded as filament can keep a filament above the 250 g Low line (config_schema.py:101-108).
  (d) A drift sample cancels them out when the same things are on at both weighings, and is off by their weight otherwise.
- The missing-tare prompt says 'We'll use it as the tare for this and future weigh-ins' (weight_utils.js:248). Quick Weigh and the weigh-out list don't save it: they send only used_weight and keep the typed empty weight for that save and the post-archive prefill (inv_weigh_out.js:1229-1237, 962-963, 982, 1064-1066). Only the wizard's launcher puts it in the spool's field (inv_wizard.js:1365-1369). Two weighings of one spool can therefore use different empty weights. Read from code, not run.
- WeightEntry's 'Skip — save as Used Weight' turns a Gross reading into Net and reports mode 'net' (weight_entry.js:385-411). A weighing record must say the empty spool was skipped, or the spool's own weight counts as filament.
- Additive is computed from the used weight read when the window opened (weight_entry.js:121; inv_weigh_out.js:1191-1198; the weigh-out cache :44-73). A charge that lands while the window is open is therefore overwritten. This is pre-existing; read from code, not run. Gross, Net and Set Used write absolute values.
- Real figures from today's corrections (completed-archive.md:14). The old INDX rule over-charged 13 spools by +126.29 g in all: +1.29 to +20.30 g per spool, over 3,442 re-pick-ups, about 0.037 g each. Most of that is well above a whole-gram scale's ±1 g (weight_utils.js:52), so one weighing of an affected spool would have shown it. But 'no spool [was] weighed since its jobs', so a weigh-in check would have had no data. The completions' over-charge was invisible to every file check, because the footer itself counted the moves.
- Related existing items:
  - PENDING DEREK 'weigh the spools before and after one multi-slot INDX print' (Feature-Buglist.md:111-117) is this check's first calibration case.
  - path_filament_g (config_schema.py:83-92; 0 = off) is filament lost at a run-out that FCC doesn't charge, a known source of 'lighter than expected'.
  - SpoolJoin joins are undetectable (Feature-Buglist.md:118-121), so charges can land on the wrong spool.
  - SpoolmanScale (Feature-Buglist.md:288-295, Group 60.5) plans weigh-ins 'through FCC's rules': this journal's weighing entry point is what that stand-in would call.
  - Per-printer settings are flat scalars only (Feature-Buglist.md:411, Group 35).
  - Printers are keyed by display name in places (Feature-Buglist.md:358, Group 44.2).

### Design

- Tell a weighing from an edit where that is known: on the page, through Phase 2's own component, with no new UI. <WeightEntry>'s payload already has the mode (weight_entry.js:414-426); add tare_skipped. saveSpoolWeight posts {id, updates, weigh}, where weigh = {source: 'quick_weigh' | 'weigh_out' | 'wizard', mode, reading, tare, tare_from, tare_skipped}; accessories are added in step 3. Kinds:
  - Gross and Net are weighings (Net marked 'empty spool taken off by hand').
  - Additive and Set Used are hand edits.
  - A request with no weigh key (an older cached page, or an API script like the 2026-11-03 corrections) is an edit of unknown kind.
  The server checks the key: mode must be one of the four and the numbers finite and ≥ 0, otherwise the key is ignored and the write is unaffected.
- The log line (step 1). A weighing: '⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). FCC expected 654.7 g: 0.3 g heavier. (used 345.3g ➔ 345.0g)'. An edit: '✏️ Weight edited by hand — Spool #57: [654.7g ➔ 593.4g remaining] (used 345.3g ➔ 406.6g)'. No weigh key: today's line, byte for byte. Expected = stock_report.remaining_g(pre). Measured = the raw reading less the empty spool, unclamped; when the page clamped it, the line says so ('more than its 1000 g total, so FCC recorded 1000 g'). The low-stock hand-off is unchanged.
- The journal (step 2): a new flat module weigh_journal.py writing inventory-hub/data/weigh_journal.json, git-ignored by .gitignore:23. It follows the ledger and store pattern: _JOURNAL_PATH overridable, a threading.Lock, atomic_store.replace_with_retry, bounded size, never raising into a caller.
  Per spool it keeps:
  - the last weighing: at (UTC), mode, reading, tare, accessories, measured, used after, total;
  - what changed the spool since: FCC charges summed per toolhead, with the printer name, job ids and each job's progress fraction (so completions and cancels can be split later); hand edits, sized from the server's own before and after; capacity or empty-weight changes; FCC's last known used weight.
  It also keeps a bounded list (~2,000) of closed samples. No Spoolman write, so the write-surface table gains no row.
- A sample is two weighings of one spool:
  - use_measured = the earlier measured grams − this weighing's measured grams (for Gross, both computed on the newer empty-spool weight);
  - use_charged = the FCC charges between the two weighings;
  - gap = use_charged − use_measured. Plus means the spool came in heavier than expected, i.e. FCC charged more than the spool lost. Also shown as a % of use_charged.
  A sample counts for a printer only when all of these hold:
  - that printer did all the charging;
  - nothing changed outside FCC (used before this weighing equals FCC's last known value plus charges and edits, within 0.05 g);
  - no hand edit happened in between;
  - the same things were on the spool both times;
  - at least 20 g was charged.
  Otherwise the sample is kept with its reason. A spool's first weighing, with no earlier one (its remaining came from the label), is logged with its gap but never counted, because it measures the maker's fill and the empty-spool weight, not FCC's charges.
- Hooks (step 2):
  - FCC charges at _record_applied_deduct's tail, right after the ledger write and beside the low-stock check (print_deduct.py:599-606), where every production charge loop ends; and at _low_stock_after_review (print_deduct.py:2878-2887), adding each row's toolhead from rec_rows.
  - Weighings and edits at api_spool_update (routes_inventory.py:1488-1489) and the wizard edit (:1262-1263).
  - Capacity changes at the Prusament apply (routes_scan.py:96-100) and at any write that changes initial_weight or spool_weight.
  Every hook is wrapped so it can never delay, change or fail its caller.
- Report (step 2): a read-only GET /api/weigh_drift, per printer per month and over the last 30 days, giving counted samples, grams charged, gap in g and %, and the mixed or uncounted samples with their reasons. Plus one Activity Log WARNING per printer per week when its counted samples over 30 days reach at least 200 g charged and 3 weighings with |gap| ≥ 5%. Example: '⚠️ INDX: spools weighed in the last 30 days came in 21.7 g heavier than FCC charged them (412 g over 6 weighings, +5.3%): its prints may be over-charged.' Claude can read the journal read-only on prod. A window comes later, after a picture.
- Attribution when a spool moved between printers: only pure samples (one printer did all the charging since the last weighing) count toward a printer. Mixed samples are listed with their split, never split by grams for a warning, because that would smear one printer's error onto another. If pure samples turn out to be few, a least-squares fit across many samples can come later. Charges are keyed by the toolhead's LocationID, which survives a printer rename.
- Accessories (step 3, after Derek weighs them and sees a picture):
  - Weights as flat Behavior floats in config_schema.py, following the path_filament_g / low_stock_g pattern: e.g. 'Cap and clip (g)', 'Edge guards (g)'; 0 = not offered.
  - In <WeightEntry>'s Gross mode and in the weigh-out list's mode bar, an 'On the spool' row of toggle buttons, none pressed by default, safe against scanner input.
  - computeUsedWeight gains accessory_g, applied in Gross mode only: used = initial − (gross − tare − accessories).
  - The weighing record lists what was ticked.
  - The two empty-spool prompts (weight_utils.js:248, inv_details.js:1566) say to take off any clip, cap or edge guards first. This costs ~30 min and ships in step 1, since an empty weight measured with guards on is inherited by every later spool of that filament.
- Size of the accessory effect, for Derek. The 2% check never reads a scale, so accessories can't touch it. A weighing records their full weight as filament: cap and clip at 3 g (a guess) is 0.3% of a full 1 kg spool but 6% of a 50 g remnant; edge guards at 25 g (a guess) are 2.5% and 50%. In a drift sample they cancel when on both times. When on only once, 3 g reads as 6% / 3% / 0.6% on 50 / 100 / 500 g charged, and 25 g as 50% / 25% / 5%. That is why they need recording or removing, and why a sample needs at least 20 g charged.
- The wizard (step 1b): its two scale paths, the launcher's <WeightEntry> (inv_wizard.js:1362-1380) and the raw Scale box (:1224-1254), keep a pending weighing in wizardState. Save sends it beside the spool data only while wiz-spool-used still holds what the weighing set; any later hand change to Used or Remaining makes the Save an edit.

### Hook points

- `inventory-hub/static/js/modules/weight_entry.js`:414-426 (payload); 385-411 (Skip); 175-196 (tare line, mode tabs); 471-490 (D key): The onSubmit payload already carries mode, raw_value, value, empty_spool_weight and capped. Step 1 adds tare_skipped, because Skip rewrites mode to 'net'. Step 3 puts the 'On the spool' buttons under the tare line; their keys must follow the D handler's scan rules, and the window keeps data-fcc-weight-keys.
- `inventory-hub/static/js/modules/inv_weigh_out.js`:1228-1238: Quick Weigh's onSubmit sends only {used_weight}. Build weigh {source:'quick_weigh', mode, reading, tare, tare_skipped} from the payload.
- `inventory-hub/static/js/modules/inv_weigh_out.js`:975-982; 907-920; 11; 791: The weigh-out row's handoff and its details-unreadable Net fallback. The mode is window.weighOutMode (default 'net'). Pass weigh {source:'weigh_out', mode, reading, tare: details.empty}.
- `inventory-hub/static/js/modules/inv_weigh_out.js`:990; 1031-1038: saveSpoolWeight(idStr, newWeight, updatesObj, autoArchiveOpts, emptyPrefill): add a weigh argument and POST {id, updates, weigh}.
- `inventory-hub/static/js/modules/inv_weigh_out.js`:82-98: Step 3: the weigh-out mode bar gets the same 'On the spool' buttons, set for the whole window like its mode.
- `inventory-hub/static/js/modules/inv_wizard.js`:1316-1382 (onSubmit 1362-1380); 1224-1254; 3818-3822; 4059-4065: Step 1b: the launcher's payload and the raw Scale box set a pending weighing in wizardState. Save sends it beside the spool data only while wiz-spool-used still holds the weighed value.
- `inventory-hub/routes_inventory.py`:1458-1489 (pre read at 1466): api_spool_update: read and validate data['weigh'] (absent or malformed = ignored). Pass it to _log_manual_weight_change, and in step 2 to the journal.
- `inventory-hub/routes_inventory.py`:987-1029 (wording 1016-1020; low stock 1026-1029): _log_manual_weight_change(spool_id, pre, post): add weigh=None, with the 'Weighed … FCC expected' and 'edited by hand' wordings. Keep today's line exactly when weigh is None.
- `inventory-hub/routes_inventory.py`:1258-1263: The wizard edit's call to the same helper; it takes the wizard's weigh in step 1b.
- `inventory-hub/print_deduct.py`:599-606 (details at 470-471): Step 2: _record_applied_deduct's tail, after the ledger write and beside the low-stock check. Call weigh_journal.note_charges(printer_name, job_id, filename, scale, details), wrapped. Covers the production charge loops at 1254→1276, 1441→1471 and 2396→2413.
- `inventory-hub/print_deduct.py`:2878-2887 (called 2798, 2830, 2859; rows 2669-2671, 2729-2733; rec_rows 2584): Step 2: _low_stock_after_review covers a Review Apply's charges. Journal them here, taking each row's toolhead from rec_rows; journal the 43.6 'already applied' row once.
- `inventory-hub/print_deduct_ledger.py`:31-33; 73-80: Why the ledger can't serve: one (printer, job) total, no spool ids or time, 200 entries. Leave it alone.
- `inventory-hub/print_deduct.py`:1136-1140; 1157-1204: The 2% file check: compares the file with its footer, on cancels only. Nothing changes here; cite it when answering Derek.
- `inventory-hub/static/js/modules/weight_utils.js`:130-224 (gross 189-197, clamps 212-222); 242-248; 52: Step 3: computeUsedWeight gains accessory_g in Gross mode only. Step 1: the missing-tare prompt's helper text tells the user to take accessories off. Line 52 records that the scale reads whole grams.
- `inventory-hub/static/js/modules/inv_details.js`:1559-1567; 1659-1662; 1677-1680: The post-archive empty-weight prompt saves a measured empty weight to the filament and optionally the brand. Step 1 adds 'take off any clip, cap or edge guards first'.
- `inventory-hub/config_schema.py`:83-108: Step 3: accessory weights as flat Behavior floats, following the path_filament_g / low_stock_g pattern (0 = not offered).
- `inventory-hub/routes_scan.py`:96-100: Step 2: on a successful Prusament apply, call weigh_journal.note_capacity(sid, before, after). It is a capacity or empty-weight change, never a weighing.
- `inventory-hub/stock_report.py`:172-185: remaining_g(spool) gives the 'expected' figure at a weighing, with the Low stock list's fallbacks.
- `inventory-hub/weigh_journal.py (new, flat at inventory-hub/)`: Writes data/weigh_journal.json with _JOURNAL_PATH, a threading.Lock, atomic_store.replace_with_retry and a size bound. Functions: note_charges, note_edit, note_capacity, record_weigh, drift_report. Never raises.
- `inventory-hub/routes_inventory.py (step 2) + inventory-hub/tests/test_route_table_pin.py`: Add GET /api/weigh_drift (read-only JSON), re-exported in app.py, and update the route-table pin on purpose.
- `inventory-hub/tests/conftest.py`:2012: Precedent: _isolate_attr_migration_state, an autouse redirect of a data file. Add one for weigh_journal._JOURNAL_PATH so host-side unit tests never write dev's live data dir.
- `CLAUDE.md`:172-176 (origin/dev): Doc fix: Phase 2 shipped (completed-archive.md:1327-1333); mark_printed isn't a weight surface; describe the journal (no Spoolman write) in the weight-entry section.

### Tests

- Step 1, tests/test_weigh_kind_log.py (new; backend; Flask test_client and monkeypatched spoolman_api, as in tests/test_manual_weight_log.py; offline). POST /api/spool/update {id:57, updates:{used_weight:345}, weigh:{source:'quick_weigh', mode:'gross', reading:875, tare:220}}, with the read before the write giving remaining 654.7. Expect exactly one weight line, containing 'Weighed', '875', '220', '655.0', 'expected 654.7' and 'heavier'. Red on origin/dev: the line is '✏️ Weight updated…' with no expected figure.
- Step 1, same file: mode 'additive' → 'edited by hand' and no 'Weighed'. tare_skipped true → not worded as a weighing. A reading above the spool's total → the line says FCC recorded the total. Red on origin/dev: the words are absent.
- Step 1, same file, back-compat guards (green on origin/dev by design). With no weigh key the line is exactly today's, and tests/test_manual_weight_log.py and test_low_stock_warning.py:389-390 still pass. A malformed weigh (a string, an unknown mode, NaN, inf, a negative tare) also gives today's line, and the write is unchanged.
- Step 1, tests/test_weigh_kind_page_js.py (new; isolated_page, so it runs offline; it reuses the harness of tests/test_quick_weigh_scan_js.py and test_weigh_out_scan_focus_js.py on the real weight_entry.js, weight_utils.js and inv_weigh_out.js; fetch is stubbed to answer /api/spool_details and record each POST body). Checks:
  - Quick Weigh, Gross 875 with an empty weight of 220 → body.weigh = {mode:'gross', reading:875, tare:220};
  - Additive '+25' → mode 'additive';
  - the missing-tare prompt's Skip → tare_skipped true;
  - a weigh-out row in Net, and its details-unreadable fallback → mode 'net'.
  Red on origin/dev: the body is {id, updates} only.
- Step 1: the two empty-spool prompts (weight_utils.js:248, inv_details.js:1566) tell the user to take off any clip, cap or edge guards. Checked with an isolated_page render, or a source canary. Red on origin/dev.
- Step 2, tests/test_weigh_journal.py (new; offline; the real update_spool, _apply_usage_to_printer and _record_applied_deduct over tests/deduct_wire_harness.WeightWireSpoolman; journal path in tmp). Weigh #57 (Gross 875, empty 220), charge 30 g on RCOI-2 (job J-1), weigh again (Gross 846). GET /api/weigh_drift should show one counted sample: measured use 29 g, charged 30 g, +1.0 g heavier (+3.3%), credited to RCOI-2's printer. Red on origin/dev: 404, no route.
- Step 2, same file. The fake's used weight changed by +5 g with no FCC write between the weighings → the sample says 'changed outside FCC (+5.0 g)' and isn't counted. An Additive hand edit in between → the sample is listed but not counted for a printer. Red on origin/dev.
- Step 2, same file. Total 1000 → 1010 g through /api/spool/prusament_apply_weights between the weighings → the sample still counts and the gap is unchanged. Empty-spool weight 220 → 230 g between Gross weighings → the first weighing is recomputed on 230. A first weighing with no earlier one → logged, never counted. Red on origin/dev.
- Step 2, same file. A 🛑 Review Apply (api_cancel_deduct_confirm) journals its charge once with its toolhead, including the 43.6 'already applied by the earlier attempt' row (print_deduct.py:2669-2671), and never twice across a retry. Red on origin/dev.
- Step 2 guards. With the journal unwritable (atomic_store raising), the deduct's ledger entry, return value and log lines are unchanged, and the weigh route still answers success. A charge on another thread during a weighing → both are recorded. Red on origin/dev only by the missing module; the assertions that matter protect the deduct.
- Step 2 infrastructure. An autouse conftest fixture points weigh_journal._JOURNAL_PATH at tmp, plus a canary that a unit test's POST leaves inventory-hub/data/weigh_journal.json untouched. tests/test_route_table_pin.py is updated on purpose for /api/weigh_drift.
- Step 3. tests/test_compute_used_weight.py gains a case: Gross with accessory_g 3 → remaining = gross − empty − 3 (red on origin/dev: the parameter is ignored). An isolated_page test: pressing 'Cap and clip' changes the preview and puts the accessories in the POST body's weigh; a scan typed while that button has the focus goes to the scan path and presses nothing (red on origin/dev: no such control). The new row also passes tests/test_contrast_guard.py, tests/test_text_size_floor.py and the keyboard idiom.
- Full sweep only (E2E; writes to dev): a Quick Weigh on the dev container shows the 'Weighed … FCC expected' line in the Activity Log.

### Risks

- Most of the noise is one-sided and invisible to FCC: purges on load and unload, the run-out leftover while path_filament_g is 0 (config_schema.py:83-92), snipped ends, test extrusions, SpoolJoin joins FCC can't see (Feature-Buglist.md:118-121), drying (a dried spool reads lighter), and prints FCC never charged. Every printer will read a little 'lighter than expected'. So judge printers against each other and against a band, never against a single sample. Moisture figures: not checked.
- The check only works if spools get weighed. None of the 13 spools the old INDX profile over-charged had been weighed since their jobs (completed-archive.md:14), so this check would have had no data on them (hence the nudge question).
- Opposite-sign errors can cancel inside one sample. Between 2026-10-22 and the hotfix, the INDX's new-profile completions were right but its cancels were charged 2.6x too little at 2%; before that, completions were over-charged. Keep each charge's progress fraction so completions and cancels can be reported apart.
- Back-compat. tests/test_manual_weight_log.py and test_low_stock_warning.py:389-390 pin the 'Weight updated' line. A request without weigh (a cached old page, or an API script like the 2026-11-03 corrections) must keep it exactly.
- Two existing page behaviours would corrupt samples if trusted. These are pre-existing and read from code, not run:
  - Skip reports a Gross reading as Net (weight_entry.js:385-411), so a record without tare_skipped counts the empty spool as filament.
  - Additive is computed from the used weight read when the window opened, so a charge landing meanwhile is overwritten (weight_entry.js:121; inv_weigh_out.js:1191-1198, 44-73). The journal must size an edit from the server's own before and after.
- The missing-tare prompt's empty weight isn't saved by Quick Weigh or the weigh-out list (inv_weigh_out.js:1229-1237, 962-982), although its text says it is (weight_utils.js:248). Two weighings can therefore use different empty weights. Store reading and empty weight per weighing so a sample is computed on one of them.
- Host-side unit tests would write dev's live journal, because the dev container mounts the working tree (inventory-hub/docker-compose.yml './:/app'). An autouse tmp redirect is needed (precedent at conftest.py:2012). Dev's own journal is junk after E2E runs and --reset-dev: the continuity check marks those samples, and prod must never be inferred from dev.
- The deduct must never slow down or fail. The hook goes after the ledger write and is wrapped, like the low-stock check (print_deduct.py:599-606). A deduct that raises after it began writing (CompletionMayHaveCharged, print_deduct.py:53, 1445, 1476) never reaches the tail. Its charges show up only as 'changed outside FCC' at the next weighing, which leaves that sample out rather than making it wrong.
- Printer identity: some state is keyed by display name (Feature-Buglist.md:358, Group 44.2). Store each charge's toolhead LocationID and group by printer at report time. Group 44 may re-key printers later.
- Storage. The JSON lives on a Windows bind mount on dev, so it needs atomic_store.replace_with_retry (the Group 32 EBUSY lesson). FCC runs as one process (Dockerfile: CMD python app.py), so a threading.Lock is enough. A Spoolman extra was rejected: it would mean a Spoolman write per charge on the deduct path plus REQUIRED_SPOOL_EXTRAS, setup_fields.py, _FCC_EXTRA_FIELD_TYPES and JSON_STRING_FIELDS registration. The trade-off is that the history lives only in FCC's data folder; TrueNAS snapshots of it: not checked. The container runs Python 3.9 (no 3.10 syntax).
- Step 3's UI must follow the standing orders: readable contrast, the named small sizes, the keyboard idiom, scanner-safe keys (data-fcc-weight-keys; a scan's letters must never press a button), no setup's own names in labels, and a picture before the build.
- CLAUDE.md:176, read literally, says to wait for a Phase 2 that shipped on 2026-04-27. A builder could stall on it or add a form around <WeightEntry>. Fix the doc in the same work.

### Open questions (for Derek; defaults stand)

- Your call: does a Net reading come off the scale?
  - What: FCC must tell a weighing from a hand edit, so the accuracy check uses only real weighings.
  - Where: Quick Weigh (the ⚖️ on a spool card) and the Bulk Weigh-Out list, mode buttons Gross / Net / Additive / Set Used.
  - Example: the weigh-out list opens in Net, and you type 425 for #57. Did that come off the scale, with the empty spool taken off in your head or with the scale's TARE on an empty spool? Or from somewhere else?
  - Options: (a) Gross and Net both count as weighings, Additive and Set Used as hand edits; (b) only Gross counts; (c) Net gets a 'from the scale' tick.
  - Recommendation: (a).
  - Default if you don't answer: (a), with Net weighings marked 'empty spool taken off by hand' so they can be left out later.
- Needs your OK, after you've weighed the parts: how should FCC know what was on the spool?
  - What: a cap and clip (a few grams?) or edge guards (tens?) on a spool being weighed are recorded as filament.
  - Where: Gross mode in Quick Weigh and the weigh-out list.
  - Example: 'On the spool: [Cap and clip 3 g] [Edge guards 25 g]' buttons under the empty-spool line. The ones you press come off the reading, as the empty spool does.
  - Options: (a) those buttons, with weights set once in Settings → Behavior, nothing pressed by default; (b) one 'extras on the spool (g)' box you type into; (c) nothing: keep taking them off, and the check tolerates a few grams.
  - Recommendation: (a) once you've weighed them, with a picture first; (c) until then.
  - Default: (c).
- Your call, after weighing: one clip button, or one per clip version?
  - What: you have more than one clip design, and they may weigh differently.
  - Example: if the versions are within about 1 g of each other, the scale can't tell them apart (it reads whole grams), so one button is enough.
  - Options: (a) one 'Cap and clip' button; (b) a button per version.
  - Recommendation: (a) unless the versions differ by more than 1 g.
  - Default: one button, using the version you use most.
- Your call: a spool used on two printers between weighings, whose drift is it?
  - What: when two printers charged a spool between weighings, FCC can't tell which one was off.
  - Example: #57 took 40 g on the XL and 12 g on the INDX between two weighings and came in 5 g heavier than FCC charged.
  - Options: (a) count only weighings where one printer did all the charging, and list the mixed ones separately; (b) split the 5 g by grams (about 4 g XL, 1 g INDX), which smears one printer's error onto the other; (c) a fit across many weighings, once there are enough.
  - Recommendation: (a) now, (c) later if mixed ones turn out to be most of them.
  - Default: (a).
- Needs your OK: when should FCC warn?
  - What: how far a printer's weighed spools may drift before FCC puts a warning in the Activity Log.
  - Example: '⚠️ INDX: spools weighed in the last 30 days came in 21.7 g heavier than FCC charged them (412 g over 6 weighings, +5.3%): its prints may be over-charged.'
  - Options: a warning when a printer is off by more than (a) ±3%, (b) ±5% or (c) ±10%, each over at least 200 g charged and 3 weighings; or (d) no warnings, a monthly line only.
  - Recommendation: (b). It is tight enough to catch something like the old INDX profile, and loose enough that the grams FCC never sees (purges, run-out leftovers, drying) don't set it off.
  - Default: (b).
- Your call, later: should FCC ask you to weigh a spool?
  - What: the check only learns from spools that get weighed.
  - Example: '#296 has taken 92 g on the INDX since it was last weighed, from a print profile no weighing has checked yet: weigh it when it next comes off.'
  - Why: the 13 spools the old INDX profile over-charged hadn't been weighed since, so the check would have had nothing to go on.
  - Options: (a) no; (b) an Activity Log line; (c) a mark on the spool's card.
  - Recommendation: decide after step 2 shows how often you weigh.
  - Default: (a).

### Derek's legwork

- Weigh each accessory: the cap, each clip version, one edge guard and a pair (per spool size, if the guards differ). Weigh 5-10 of one kind together and divide, because FCC's notes say your scale reads whole grams (weight_utils.js:52), so one small part on its own is only good to ±0.5 g. Note which spools each part fits.
- Check the scale once: does it show whole grams or tenths, and what does a known weight read? For example, US nickels are 5.000 g each, so 10 should read 50 g.
- Weigh one empty spool of each kind you use most, with and without edge guards. This checks the empty-spool weights FCC already has; every spool of that filament, and of that brand where one is set, inherits them.
- Tell Claude:
  - which mode Quick Weigh opens in for you (it's Additive unless you set another default);
  - how you weigh in the weigh-out list (Net with the empty spool taken off in your head, or with the scale's TARE);
  - whether you ever change a weight in Spoolman itself;
  - whether the cap and clip usually go on before or after you weigh a spool you're shelving.
- Later, once step 2 is on prod: the existing PENDING DEREK 'weigh the spools before and after one multi-slot INDX print' (Feature-Buglist.md:111-117) becomes 'weigh them in FCC, in Gross mode, before and after', with accessories off or the same both times. A print with many tool changes also tests Prusa's claim, which no scale has checked yet (completed-archive.md:14), that the tool lock moves no filament. The two rules differ by about 0.037 g a re-pick-up, so ~300 re-pick-ups is about 11 g, far above the scale's ±1 g.
- Steps 1 and 2 don't wait for any of this; step 3 waits for the first item. The first four items would be filed under PENDING DEREK, and none of them blocks a release.

## Keep the history longer: a 100 MB hub.log now, then a permanent spool-history journal (data/history/<year>.jsonl) written at update_spool

Measured on prod (read-only, 2026-11-03): FCC's log grows only about 66 KB a month in normal use, so today's 6 MB would last about 7 years. But one repeated line filled four of the six files between 2026-02-16 and 02-19 (65,701 copies of "✅ Loaded Prod Config", 4.86 MB). Those four days pushed out everything logged before 2026-02-16 14:09. Nothing else FCC keeps is a history either:
- The deduct ledger keeps only the newest 200 jobs, with no dates and no per-spool rows.
- Spoolman 0.27 stores no change history. It pushes change events over a websocket, but keeps none.
- The NAS share doesn't offer Windows "Previous Versions", so whether ZFS snapshots exist is unknown until Derek checks.

The smallest change that keeps years of log is one line: state.py:76 to 20 files of 5 MB (100 MB). Nothing that reads the log changes: the dashboard reads memory, and the test harness's `.1` reader keeps working.

That line alone isn't safe. The log is text with no time zone and no reason for a change, and it can't see edits made straight in Spoolman. So the item's real build is an append-only journal with one JSON line per change and one file per year, never rotated. Its hook goes in spoolman_api.update_spool, the one place every FCC spool write passes, which already holds the before and after values. It also takes a print_charge line per job and, as step 3, an hourly "changed outside FCC" check. It is about 1 MB a year on prod.

The weigh-in drift item should read this same journal rather than parse log text. Size: S for the log change, M with the journal's write half, L in full.

**Size:** S for step 1, the bigger log: about 0.5–1 h. M for that plus the journal's write half (module, the four data-layer hooks, print_charge, sources, conftest redirect and tests): about 8–10 h. L for the whole item with the hourly outside-change check (about 4–6 h more), plus a later spool History view (about 6–10 h more, its own item): about 20–25 h. Past estimates have run about 30% low.

**First step:** Change state.py:76 to RotatingFileHandler('hub.log', maxBytes=5_000_000, backupCount=19) and add one offline pin test (red on base, which has 1,000,000 / 5). Also reword the '~6 MB rolling buffer' docstring at tests/test_attr_migration_group36.py:521. It is one line with no reader changes, and takes effect at the next deploy. Prod's log then goes from about 7 years at the normal rate (2 days at February's peak) to 100 MB, which the normal rate effectively never fills and February's peak would take about 38 days to roll. Step 2 is the journal's write half: history_journal.py, the update_spool, create_spool, delete_spool and update_filament hooks, print_charge, and the conftest redirect.

### Findings

- Log setup today: on origin/dev (bbc5ee7) the log handler is at state.py:76, not :97 as the brief said: RotatingFileHandler('hub.log', maxBytes=1000000, backupCount=5). That is six size-based files, about 6 MB. The line format (state.py:72/77) carries no time zone. Prod's container writes Pacific local time: its first line, 15:28:38, matches the file's 3:28:38 PM creation time. Dev's container writes UTC: 14:45:46 against 6:45:46 AM. So on prod, a line stamped in the 01:00–02:00 hour of 2026-11-01 (the DST change) could be either of two moments.
- Prod log files, read-only on 2026-11-03:
  - hub.log: 432,916 B, from 2026-04-24 15:28.
  - hub.log.1: 999,884 B, 2026-02-18 21:08 to 04-24.
  - hub.log.2 to .5: about 1 MB each, all covering 2026-02-16 14:09 to 02-18 21:07.

  Bytes per month: Feb 4,893,286 · Mar 36,030 · Apr 106,839 · May 122,225 · Jun 100,010 · Jul 14,882 · Aug 284 (2 lines; prod was nearly silent from mid-July to Sep 3) · Sep 86,862 · Oct 58,002 · Nov 1–3 14,244.

  The March–October average is about 66 KB a month, roughly 0.8 MB a year. The busiest normal day was 2026-05-14 at 47,487 B: a Spoolman outage that logged 262 'Error fetching pending print queue' lines. Scripts used, re-runnable and read-only: D:\claude-tmp\claude\d--My-Documents-Documents-3D-Printing-Filament-Command-Center\d001fa7e-fe43-49c5-89fb-535d040ff533\scratchpad\hublog_stats.ps1 and D:\claude-tmp\claude\d--My-Documents-Documents-3D-Printing-Filament-Command-Center\d001fa7e-fe43-49c5-89fb-535d040ff533\scratchpad\hublog_days.ps1
- How one noisy line rolled history out: 65,701 copies of the INFO line '✅ Loaded Prod Config: /app/config.json' came to 4,861,874 B. By day: 14,096 on 02-16, 8,890 on 02-17, 34,975 on 02-18 and 7,732 on 02-19; only 8 since. They pushed out everything before 2026-02-16 14:09. The repo dates from 2026-01-22; when prod first logged is not checked.

  The line comes from config_loader.py:121-132, guarded by a .config_mtime tracker that is written under 'except: pass'. Why the guard failed in February is not checked.

  What that means for capacity:
  - At the normal rate, 6 MB lasts about 7 years.
  - At February's peak day (2,593,770 B) it lasts about 2 days.
  - At 100 MB it would last about 38 days of that peak.
- Nothing at runtime reads hub.log:
  - /api/logs (routes_state_pulse.py:231-253) returns state.RECENT_LOGS, the last 50 entries kept in memory (state.py:124-125). A bigger file changes nothing on the dashboard.
  - No startup code reads it.
  - Only the 'InventoryHub' logger writes to it (state.py:67). Werkzeug is set to ERROR and goes to the console (app.py:160-161).

  The only reader is the test harness:
  - conftest.py:221 and :296-310, the failed-test request log. It reads from a byte offset, and reads hub.log.1 after a rollover.
  - tests/test_sweep_load_label.py:98-107 pins that rollover read.
  - tests/test_sweep_load_label.py:216-226 pins that the host holds no RotatingFileHandler (conftest.py:59-63 detaches it at import).

  On dev, test sweeps make 6 MB cover only 2026-10-13 to 11-03. tests/test_attr_migration_group36.py:521-522 already notes that dev's reloader gives hub.log two competing writers.
- The other durable records are not histories:
  - print_deduct_ledger.json keeps only the newest 200 jobs (print_deduct_ledger.py:33, trimmed at :54-55). Each entry has job, file, scale, total grams, confirmed and shortfall (:73-80), but no date and no per-spool or per-head rows. Prod holds 123 entries (18,012 B), from Core One Upgraded job 1047 to INDX job 1136. FCC's own deducts began 2026-06-13 (the first log line is 16:56:58), so at about 26 jobs a month the ledger starts dropping its oldest around early 2027 and from then on covers about 7–8 months.
  - pending_cancel_deducts.json holds only open reviews, capped at 100 (cancel_review_store.py:25-27); prod's is {}.
  - The locations.json .bak files are one-off copies taken before migrations.
- Spoolman keeps no change history. Checked on dev's Spoolman 0.27.1; prod was not contacted, and CLAUDE.md says it runs 0.27.0.
  - None of its 36 REST paths is a history or audit endpoint.
  - A spool carries only registered, first_used and last_used timestamps.
  - It does push change events over a websocket (SpoolEvent: added/updated/deleted/scanned, a UTC date, the whole spool; the root endpoint /api/v1/ hears every change). These are pushed, never stored.

  Its own backups are whole-database copies, made at midnight and on every POST /api/v1/backup. update.sh:37 calls that before each deploy. Both share one rotation of the newest copy plus 5 older ones (num_backups=5 in https://raw.githubusercontent.com/Donkie/Spoolman/master/spoolman/database/database.py; the endpoint is in https://raw.githubusercontent.com/Donkie/Spoolman/master/spoolman/api/v1/router.py). That is about a week of snapshots. This was read from the master branch and not checked against the 0.27.0 tag; where prod keeps them is not checked.
- TrueNAS snapshots: from Windows, the App_Data share offers no Previous Versions. I sent the same read-only query Explorer uses (FSCTL_SRV_ENUMERATE_SNAPSHOTS on \\TRUENAS\App_Data\InventoryHub\inventory-hub) and it answered 'Incorrect function'. That only says the share doesn't publish snapshots to Windows. Whether ZFS snapshots of the dataset exist is NOT known and needs Derek's look (see derek_legwork). Script: D:\claude-tmp\claude\d--My-Documents-Documents-3D-Printing-Filament-Command-Center\d001fa7e-fe43-49c5-89fb-535d040ff533\scratchpad\list_prev_versions.ps1. The share reports about 19 TB free, so 100 MB of logs costs nothing. ZFS compression on the dataset is not checked. Even if snapshots exist, they keep old files only for their lifetime: a backstop, not a history.
- Where prod's files live, and what survives a deploy:
  - Prod's checkout is /mnt/LeftBankPool1/App_Data/InventoryHub (update.sh:8). It is seen as /app in the container (the log names /app/config.json), so hub.log and data/ both sit on the App_Data dataset. Prod's compose file is not in the repo and was not checked.
  - update.sh runs 'git reset --hard origin/main' (:53-54), which leaves ignored files alone. Ignored here are inventory-hub/hub.log* (.gitignore:5) and inventory-hub/data/* (.gitignore:23), and the image excludes logs and data too (.dockerignore:21-22, :37). So a new file under data/ survives deploys, as the ledger does.
  - The image is python:3.9-slim with only flask and requests (Dockerfile:2, :8), so there is no websocket client. update.sh only pulls the code and stops and starts the app (:65-76). Whether TrueNAS rebuilds the image then is not checked.
- Every FCC spool write passes one function: spoolman_api.update_spool. It holds the app's only spool PATCH (spoolman_api.py:668); the only other spool calls are create_spool (:741) and delete_spool (:1319). It already reads the spool before writing (existing, :568) and gets the whole updated record back (out, :672). So before and after for used, remaining, initial, spool_weight, location, archived and the slot/trail extras are in hand with no extra read. About 25 call sites in six modules call it, against about 324 add_log_entry calls in 16 modules. The journal therefore belongs at the data layer, not in the Activity Log feed.
- What neither the log nor Spoolman can explain today:
  - The weigh-out sends only {id, updates} (inv_weigh_out.js:1031-1037). It never sends the reading, the gross/net mode or the empty-spool weight subtracted, so nothing can say 'gross 712 g minus a 212 g spool'.
  - A filament's weight edit (update_filament, spoolman_api.py:1222; it reads nothing first unless extras are sent) changes the remaining weight of every spool without its own initial_weight, with no spool write at all.
  - An edit made straight in Spoolman leaves no trace in FCC, and neither does a tool that writes to Spoolman directly, such as a scale using Spoolman's /spool/{id}/measure. These are today's 'unexplained jumps'.
- Derek's 2% question: caps, clips and edge guards can't move it. The 2% check (_warn_parse_gap, print_deduct.py:1157-1204) compares FCC's G-code walk with the slicer's own footer. Both numbers come from the file, and no scale reading enters it.

  Accessories matter only where a weigh-in is compared with FCC's numbers (the weigh-in drift idea), and for the remaining weight Spoolman shows. A spool weighed with them reads heavy, so FCC looks as if it over-charged by their weight. For example (made-up numbers), 5 g of cap and clip against 200 g printed since the last weigh-in reads as 2.5%: the size of effect a drift monitor would look for.

  The current hub.log's only parse-gap WARNINGs are job 1134's three (2026-11-02 21:23:44: +150.5%, +160.2%, +150.1%). Those numbers exist only in log text.
- CPython bugs that rule out daily rotation on the container's Python 3.9: TimedRotatingFileHandler's cleanup deletes the wrong files when two handlers share a name stem, or when a namer is set. These are gh-93205 (https://github.com/python/cpython/issues/93205, fixed by GH-93224) and gh-115809 (https://github.com/python/cpython/issues/115809, merged March 2024). Both fixes came after 3.9.

### Design

- Part (a), the log: keep size-based rotation, but 20 files of 5 MB. state.py:76 becomes RotatingFileHandler('hub.log', maxBytes=5_000_000, backupCount=19), plus Group 45.9's delay=True if that lands first.
  - That is a 100 MB cap. At 2026's normal rate it effectively never fills; a February-size burst would take about 38 days to empty it.
  - Nothing that reads it changes: the conftest `.1` reader and both pins keep working.
  - Rejected, daily files (TimedRotatingFileHandler, hub.log.YYYY-MM-DD): they break conftest.py:296-310 and the isinstance pin at test_sweep_load_label.py:224, and 3.9 has the cleanup bugs above.
  - Rejected, gzip of old files: it breaks the plain `.1` read, and ZFS probably compresses the dataset anyway (not checked).
  - Optional follow-up: a repeat filter in state.py. When one line comes again within a minute, write it once with '(repeated N times)', so one noisy line can't fill the log.
- Part (b), the journal: a new flat module, history_journal.py, writing data/history/<YYYY>.jsonl. One file per year, append-only, never renamed or rotated. That avoids the Windows bind-mount rename race, and the whole-file rewrite atomic_store would do per event.
  - Each line is one JSON object: "v":1, an ISO timestamp with its UTC offset, "kind", "spool", "op" (one id per request or per print, so the lines of one action group together) and "src".
  - Writing: open(path, 'a', encoding='utf-8') under a module lock, then one write, flush and fsync (prod makes about 10 a day; measure fsync on dev's bind mount). If the file's last byte isn't a newline (a line cut by a crash), write a newline first.
  - It never raises into the caller; at most one ERROR line per 10 minutes if it can't write.
  - The reader streams the files and skips any line that won't parse.
  - The path is module-relative (like cancel_review_store) with a _DIR attribute that tests override.
- What goes in the journal:
  - spool_write, from update_spool's success branch (spoolman_api.py:669-683): before and after, only for the tracked keys that changed (used_weight, remaining_weight, initial_weight, spool_weight, location, archived, container_slot, physical_source, physical_source_slot), plus the list of keys sent.
  - spool_created and spool_deleted, from create_spool and delete_spool.
  - filament_weight, from update_filament when weight or spool_weight is sent, because it shifts every spool that inherits its weight.
  - landed_after_error, where a write that reported failure is proved landed: logic.py:1699-1715 (_move_write) and print_deduct.py:445-450 (_write_landed).
  - print_charge, written beside the ledger write in _record_applied_deduct (print_deduct.py:585): printer, job, file, cancel or complete, scale, requested/applied/shortfall, and one row per spool and head, including failed rows. Also written for a review's Apply in api_cancel_deduct_confirm (:2474).
  - Optional, for the file-check items: parse_check, the walk-vs-footer numbers _warn_parse_gap logs.
- Where each line's source comes from, without touching the 324 Activity Log calls: a contextvars context, history_journal.context(via=..., **meta).
  - Inside a request the default source is the door itself, e.g. 'POST /api/spool/update' or 'POST /api/quickswap'.
  - Outside a request it is the thread's name.
  - The print paths run on the monitor thread, so they set {printer, job, file} themselves in deduct_completed_print and deduct_cancelled_print (print_deduct.py:1284 / :1207).
  - The weigh screens' raw reading is not added now: mode, reading, empty-spool weight and where it came from, and 'weighed with cap/clip'. CLAUDE.md's rule is no new weight-entry UI before Phase 2, so this goes into the Phase 2 component's design. The journal is built to accept those fields when the page sends them.
- Changes made outside FCC (step 3): an hourly check on the monitor thread, started under __main__ (app.py:378/390). Never at import, because dev's reloader parent runs import-time code.
  - It does one strict read of every spool, archived included, and compares it with data/history/last_seen.json (rewritten only when something changed).
  - A difference FCC didn't write becomes an 'observed' line, {was, now, since}: e.g. 'used 300 → 350 g, changed outside FCC between 13:00 and 14:00'.
  - A spool FCC began writing after the read started is skipped that round. A new state matching a recent FCC write that reported failure is recorded as landed_after_error instead. A failed read records nothing.
  - The first run writes a baseline of every spool.
  - Spoolman's websocket could give exact times later, but it needs a client the image doesn't have, and it would still miss whatever changed while FCC was down.
- Size: prod about 1 MB a year, ten years about 10–15 MB. This is an estimate from 2026's log, which has about 1,900 history-like lines from March to November (about 200 KB of text), with a JSON line about 1.5× a log line. Dev will be more because of test sweeps (not measured); per-year files keep that manageable. No pruning is needed: keep forever by default.
- Keeping tests off dev's data: on the host, the module-relative data/ is dev's real, bind-mounted data folder. conftest.py, next to its f_handler removal at :59-63, points history_journal._DIR at a temp folder before anything imports spoolman_api, and a canary pins that. Coordinate with Group 45.9's planned host-only data folder (Feature-Buglist.md:536).
- Share the journal with the weigh-in drift item: yes. Each weigh-in's spool_write holds FCC's expectation (before) and the scale's result (after), and the print_charge rows since the previous weigh-in say which printer, head and file the gap belongs to. Build the journal in this item and make drift its first reader. The finished-print self-check can add parse_check lines to the same journal. Building drift on hub.log text would repeat today's hand reconstruction.
- Not in this item:
  - A 'History' section in the spool window, and a download. That is a later item that reads the journal; a read route then updates tests/test_route_table_pin.py.
  - Seeding the journal from the old log text (fragile; optional).
  - Raising the ledger's 200 cap. It is a duplicate guard, and the journal is the history.

### Hook points

- `inventory-hub/state.py`:76: RotatingFileHandler('hub.log', maxBytes=1000000, backupCount=5): the one-line change for part (a). Group 45.9 plans delay=True on the same line.
- `inventory-hub/state.py`:72, 77, 120-125: The log format has no time zone. RECENT_LOGS is memory only, capped at 50.
- `inventory-hub/routes_state_pulse.py`:231-253: /api/logs serves state.RECENT_LOGS and never reads hub.log, so a bigger log doesn't affect the dashboard.
- `inventory-hub/tests/conftest.py`:59-63: The host detaches the container's log handler at import. The journal's _DIR redirect goes here too, before any test imports spoolman_api.
- `inventory-hub/tests/conftest.py`:221, 296-310: The request-log reader reads hub.log from a byte offset and hub.log.1 after a rollover. It keeps working with bigger size-based files; daily files would break it.
- `inventory-hub/tests/test_sweep_load_label.py`:98-107, 216-226: Pins the .1 rollover read, and that the host holds no RotatingFileHandler.
- `inventory-hub/spoolman_api.py`:568, 668-683: update_spool: existing (before) is read at :568, the only spool PATCH is at :668, and out (after) comes back at :672. This is the spool_write hook, with no extra read.
- `inventory-hub/spoolman_api.py`:726-747, 1222-1276, 1312-1328: create_spool, update_filament (a weight or spool_weight change shifts inherit-weight spools) and delete_spool: the journal's other data-layer hooks.
- `inventory-hub/logic.py`:1683-1715: _move_write: a move that reported failure but is proved landed (the WARNING at :1712). Journal it as landed_after_error.
- `inventory-hub/print_deduct.py`:439-471: The per-spool charge in _apply_usage_to_printer, with its landed re-read at :445-450. The details rows give spool, head, grams and remaining.
- `inventory-hub/print_deduct.py`:522-607: _record_applied_deduct: the ledger write at :585-586. The print_charge hook goes beside the 49.2b low-stock hook at :603-606.
- `inventory-hub/print_deduct.py`:1207, 1284, 2474: deduct_cancelled_print and deduct_completed_print run on the monitor thread, so they set the journal context (printer, job, file). api_cancel_deduct_confirm is the review Apply, which needs its own print_charge.
- `inventory-hub/print_deduct.py`:1157-1204: _warn_parse_gap: the check that caught job 1134. Its numbers live only in log text; an optional parse_check event.
- `inventory-hub/print_deduct_ledger.py`:31-33, 54-55, 73-80: The ledger keeps the newest 200 jobs, with no date and no per-spool rows: a duplicate guard, not a history.
- `inventory-hub/routes_inventory.py`:987-1029, 1441-1489: _log_manual_weight_change and /api/spool/update: the weigh doors, with pre and res in hand. Their source comes from the request automatically.
- `inventory-hub/static/js/modules/inv_weigh_out.js`:1031-1037: The weigh-out posts only {id, updates}, with no reading, mode or tare. That is a weight-entry Phase 2 requirement, not a change now.
- `inventory-hub/config_loader.py`:109-132: The 'Loaded Prod Config' line and its .config_mtime guard (except: pass), behind the February burst of 65,701 lines.
- `inventory-hub/app.py`:339, 378, 390: The __main__ block, the dev reloader's child-only check, and the monitor start: where an hourly reconcile may start. Never at import.
- `update.sh`:8, 37, 53-54, 65-76: Prod's dataset path, the Spoolman backup before each deploy, git reset --hard (ignored data/ and hub.log survive it), and the app stop/start (no image rebuild seen).
- `inventory-hub/Dockerfile`:2, 8: python:3.9-slim with only flask and requests: use the standard library only, no websocket client.

### Tests

- tests/test_hub_log_retention.py::test_hub_log_keeps_twenty_5mb_files (offline): state.f_handler is a logging.handlers.RotatingFileHandler with maxBytes == 5_000_000 and backupCount == 19. Red on base, which has 1,000,000 / 5. The existing test_sweep_load_label.py pins (.1 rollover read, host holds no handler) stay green.
- tests/test_history_journal.py::test_a_landed_spool_write_appends_one_line (offline): drive the real spoolman_api.update_spool over tests/spoolman_extra_fake.py:213 SpoolmanHTTPFake, with requests.get and patch replaced on spoolman_api.requests and _DIR pointed at tmp_path. A used_weight 300 → 312.4 write gives exactly one line: kind spool_write, v 1, a timestamp with an offset, and before/after used and remaining. Red on base, because history_journal doesn't exist. To prove it's red for the right reason, delete the hook line in a scratch copy and the test sees no line.
- ::test_a_refused_write_appends_nothing (the fake answers 422) and ::test_a_write_that_landed_after_a_timeout_is_journaled_once (the fake commits, then raises ReadTimeout). The second goes through logic._move_write and print_deduct._write_landed and expects exactly one landed_after_error line each. Red on base.
- ::test_the_journal_never_fails_the_write (offline): opening the journal raises OSError, yet update_spool still returns the spool and LAST_SPOOLMAN_ERROR is None. Three writes give one ERROR line, not three. Red on base.
- ::test_a_door_is_its_own_source: a Flask test client POST /api/spool/update gives src.via 'POST /api/spool/update'. A completion deduct through tests/deduct_wire_harness, on the monitor path with no request, gives src with printer, job and file. Red on base.
- ::test_print_charge_names_the_job_and_each_spool (offline, run under both FCC_FAKE_SPOOLMAN_EXTRA modes): deduct_completed_print, and a review Apply through api_cancel_deduct_confirm, each write one print_charge. It carries rows [{spool, head, grams, used_before, used_after}], requested/applied/shortfall, and failed rows flagged. Red on base.
- ::test_a_torn_last_line_is_skipped_and_the_next_write_starts_a_new_one, and ::test_events_go_to_the_file_of_their_year (a fake clock from 23:59:59 on Dec 31 to Jan 1). Both red on base.
- tests/test_history_journal_canary.py::test_the_host_never_writes_devs_journal: conftest has pointed history_journal._DIR outside inventory-hub/data, and a run that imports app and spoolman_api leaves inventory-hub/data/history untouched. Red on base (no module). Also proven by removing conftest's redirect in a scratch copy.
- Guard, green on base by design: ::test_every_spool_patch_goes_through_update_spool. Using tests/source_family.py:read_app_family(), exactly one requests.patch naming /api/v1/spool/ exists (in update_spool), so a future write can't skip the journal. Its red is shown by adding a stray PATCH in a scratch copy.
- Step 3, tests/test_history_reconcile.py (offline, over SpoolmanHTTPFake):
  - A change made in the fake is recorded once as observed.
  - A spool FCC began writing after the read started is not called outside.
  - A failed strict read records nothing.
  - The first run writes a baseline.
  - FCC's own writes never show as observed.
  All red on base.

### Risks

- Host tests writing dev's real journal: the module-relative data/ on the host is dev's bind-mounted data folder, and every SpoolmanHTTPFake test runs the real update_spool. Without conftest's redirect and its canary, unit tests would append junk to dev's history, and a host and container appending at once on the Windows bind mount could interleave lines. This touches the same area as Group 45.9 (host data folder, delay=True at state.py:76), so coordinate the order.
- A journal failure must never fail or slow a Spoolman write: wrap everything, and rate-limit its ERROR line. Measure fsync's cost on dev's bind mount during the build, because bulk moves write many spools. Drop to flush-only if sweeps slow down.
- A write that timed out but landed never reaches update_spool's success branch. The two re-read sites (_move_write, _write_landed) cover moves and charges. Any other surface's landed-timeout is caught only by the hourly check (step 3), which must match it against FCC's failed attempts, or it gets called 'outside FCC'.
- Stale reads in the hourly check: a list read that started before an FCC write landed would record a false 'outside FCC' change, or a false revert. Skip any spool FCC began writing after the read started, and never read a failed or partial read as a change or a deletion.
- Double counting: print_charge rows and the matching spool_write lines describe the same grams. Readers, including the drift report, must sum one or the other and link them by op.
- Growth on dev: test sweeps write many spools (not measured), and dev's reloader runs two processes (test_attr_migration_group36.py:521-522). Per-year files and streaming readers keep that manageable. The reloader's parent serves no requests, so only the child should ever write. Nothing may be journaled at import.
- Spools that inherit their weight from the filament: a filament's weight edit changes their remaining with no spool write. Without the filament_weight line, a history or drift reader would see a jump it can't explain.
- TrueNAS deploys: update.sh restarts the app without a rebuild that I could see (whether TrueNAS rebuilds is not checked). Any new pip package (for example a websocket client) might never reach prod, so use the standard library only. Files stay under the existing, git-ignored and docker-ignored data/. Never run git clean -x in the prod checkout, because it would delete data/ and hub.log.
- Time zones: dev writes UTC and prod writes Pacific local time. Every journal line must carry its offset, or a history read across the two (or across a DST change) is ambiguous.
- Until a repeat filter exists, a burst like February's still drains the bigger log, in about 38 days instead of about 2. The journal is immune to log noise either way.
- Outside text in the journal (file names, colour and printer names) is stored raw in JSON. Any future History view must escape it, as the Activity Log's HTML rule requires for its lines.

### Open questions (for Derek; defaults stand)

- [his call] Q1: How much of FCC's text log to keep.
  - What: FCC's own log file (every Activity Log line plus errors) keeps 6 files of 1 MB and deletes the oldest.
  - Where: InventoryHub\inventory-hub\hub.log on the NAS.
  - Example: from Feb 16 to 19 one repeated line filled four files in four days and pushed out everything before Feb 16. Since April the log has grown about 66 KB a month.
  - Options: (a) 20 files of 5 MB (100 MB): today's rate never fills it, and a February-size burst would take about 38 days. (b) One file per day, kept N days: needs test changes, and Python 3.9 has known cleanup bugs there. (c) Leave it at 6 MB.
  - Recommendation: (a). Default: (a).
- [needs his OK] Q2: A permanent spool history, separate from the log.
  - What: one line for every change FCC makes to a spool (charge, weigh-in, move, archive), in one file per year, never rotated.
  - Where: \\TRUENAS\App_Data\InventoryHub\inventory-hub\data\history\2026.jsonl.
  - Example: '#57 used 300.00 → 300.13 g, Core One INDX job 1134, cancelled at 2%' and '#57 weighed: FCC expected 652.1 g left, the scale said 654.7 g'.
  - Options: (a) yes; (b) no, rely on the bigger log.
  - Recommendation: (a). It is about 1 MB a year on prod, and it is what the weigh-in drift check would read. Default: (a).
- [his call] Q3: Record changes made outside FCC.
  - What: once an hour FCC compares every spool with what it last saw, and writes 'changed outside FCC' for anything it didn't do. That covers an edit on Spoolman's own page, or a scale or tool that writes to Spoolman directly.
  - Where: the same history file.
  - Example: today's 'unexplained jumps' would read 'used 300 → 350 g, changed outside FCC between 13:00 and 14:00'.
  - Options: (a) hourly; (b) also at every dashboard refresh while a page is open, to the minute, with more code and care about timing; (c) not now.
  - Recommendation: (a). Default: (a).
- [his call] Q4: Where to read the history.
  - What: how it is shown to you.
  - Options: (a) kept for Claude to read when something looks off, with nothing new on screen; (b) a 'History' section in the spool window; (c) a download per spool or per month.
  - Recommendation: (a) now, and (b) as a later item. Default: (a).
- [his call] Q5: How long to keep it.
  - What: whether the per-year history files are ever deleted.
  - Example: ten years on prod is about 10–15 MB.
  - Options: keep forever, or keep the last N years.
  - Recommendation: forever. Default: forever.
- [needs his OK; shared with the weigh-in drift item] Q6: Record the scale reading itself.
  - What: the weigh screens send only the result. They don't send the reading, whether it was gross or net, the empty-spool weight subtracted, or whether the cap or clip was on.
  - Where: the weigh-out list and Quick-Weigh.
  - Example: 'gross 712.4 g, empty spool 212 g, cap and clip on'.
  - Options: (a) put it into the planned one-weight-box (Phase 2) design, since FCC's rule is no new weight UI before then; (b) send the reading, mode and tare now with no screen change, without a cap/clip box.
  - Recommendation: (a), with the history ready to accept the fields. Default: (a).

### Derek's legwork

- Check whether the NAS already snapshots App_Data. This is about 5 minutes in the TrueNAS web page, with no shell. Go to Data Protection → Periodic Snapshot Tasks and look for a task on LeftBankPool1/App_Data, or on LeftBankPool1 with Recursive ticked. Note its schedule and how long it keeps snapshots. Then go to Datasets → App_Data → Data Protection → Manage Snapshots and note the oldest snapshot's date. Tell Claude what you see, and Claude will read any old hub.log in them, read-only. Windows can't show them: the share's Previous Versions query answered 'Incorrect function'. This goes under PENDING DEREK when the item is filed.
- If there are no snapshots: decide whether to add a task, for example daily and kept 4 weeks. It would also protect data/ (locations, the deduct ledger, the new history). It's your NAS and your call; nothing in FCC waits for it.
- Optional, for the weigh-in drift item (shared): weigh the end cap, each clip version, and one spool's set of edge guards on their own, to 0.1 g if your scale reads that finely. Also say which spools usually wear them. They can't affect the 2% file check, but they do affect any check that compares a weigh-in with FCC's numbers. This also goes under PENDING DEREK.
- Answer Q1–Q6 whenever it suits you; the defaults stand otherwise. Claude does the build, the tests and the read-only prod checks. Nothing here needs a command line from you.
