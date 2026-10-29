# Group 59: 🎨 Design Samples

**Branch name (when started):** `feature/group-59-design-samples` (the samples themselves live in `review-samples/`, git-ignored)
**Estimated effort:** one picture session with Derek (~2–3 h of Claude's work to make the samples), then small builds (~1–3 h each) for the ones he picks.
**Risk:** **LOW–MEDIUM.** Display only, but the standing order applies: **never restyle without a sample first** (*"my main concern here is that we standing order the wrong look, refactor everything for that look, and then have to revert everything back"*).

> **Status: `TODO` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping"). Design-first: nothing is built before Derek picks from pictures.** Whenever Derek wants to look; it blocks nothing.
> Four looks Derek flagged on his 2026-10-22 text-size walk, plus the older strip-card refactor, made into before / after pictures in one sitting, one item at a time (his format: images in `review-samples/` as clickable links, never a long doc).
> Code anchors were read on `dev` @ `d4b1ad7` (2026-10-25). Line numbers drift, so re-grep before editing.
> **⏸️ 2026-10-29: 59.1 and 59.2 wait for the box sit-down** (Derek wants the box-to-toolhead system rethought first; the ⏸️ PENDING DEREK item in `Feature-Buglist.md`): the slot picker may change with it. 59.3–59.5 can go ahead.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **59.1** | 🎨 Design follow-ups (a), **the slot picker in printer mode**: *"it just looks scattered, and it's hard to tell what is what"; its slots break onto a second row and leave a lot of empty space after the head list.* His idea: *a 3×3 grid for the heads.* | Two or three layouts as pictures (his 3×3 among them), on dev's XL and RCOI. |
| **59.2** | (b) **the slot picker's Swap / Overwrite / Back panel**: *"the buttons are all over the place", their two-line labels make it hard to tell which QR does what ("Yellow to Yellow, but what does yellow button do again")*: *use the move questions' pattern, three short buttons each with its QR under it, and the details as one line of text.* | The move questions' pattern, as a picture first. |
| **59.3** | (c) **Settings as a side panel**: *section names (This Browser, Connection, Behavior, …) on the left, the open section's settings on the right.* | A picture at 1600×1300 and at a phone width. |
| **59.4** | (d) **Grey help text on black** *"might need a re-think later" (the 2026-10-22 build only lifted it to pass the contrast guard): with step 2's named colours.* | Two or three greys from step 2's named colours, side by side. |
| **59.5** | 🎨 *"Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird."* (2026-10-19: *"two variants, one row per spool with all three QR badges or with one, both keeping Group 40.6's ↩️ RETURN footer"*, on a real cart, e.g. `CR-CT-2-R1`.) | The two variants as pictures. |
| _(→ 57.3)_ | (e) the title bar at Extra Large | In [Group 57](57-low-stock-at-a-glance.md), because the Low stock button decides it. |

## Decisions

- **All Derek's, one at a time from pictures** (what / where / a real example / the options / a recommendation / what happens if he doesn't answer). Items he skips stay in this group.
- **Claude's calls (for veto):** samples on dev's real data (XL, RCOI, `LR-MDB-1`, `CR-CT-2-R1`), at Standard and Extra Large, 1600×1300; a before picture beside every after; nothing committed to the repo but the eventual build.

## Today's code (anchors, `dev` @ `d4b1ad7`)

- **The slot picker:** `static/js/modules/slot_picker.js` (1,135 lines). Printer mode: its prompt (`:469`), the Printer Pool slots drawn after the heads (`:551`), a head's `LOC:` scan in printer mode (`:1108`); the panel `.fcc-sp-panel { width:min(62.5rem,96vw); max-height:90vh }` (`:98`). The Swap / Overwrite / Back step (`~:636-690`, from `_choiceFor` at `:640`): each button carries a `<small>` second line (`:650`), the buttons and the QRs sit in separate rows (`.fcc-sp-choice-btns` / `.fcc-sp-choice-qrs`, `:659-660`; the button row's CSS at `:137`), and `attachConfirmQRs` is called without `alignTo` (`:669-680`). CLAUDE.md, "A row of "📷 Scan to …" QR codes sits under its buttons": *"The slot picker's own Swap / Overwrite panel is not aligned yet (its redesign is a buglist item)."* The pattern to copy: `attachConfirmQRs({..., alignTo: buttonRow})` + `window.FCC_QR_TONES` (`inv_core.js`), pinned by `tests/test_qr_under_buttons_js.py` / `_e2e.py`.
- **Settings:** `static/js/modules/inv_settings.js` (742 lines; `render(schema, values)` at `:86`), sections from `config_schema.SECTIONS`. [Group 35](35-config-cluster.md) (per-printer settings + L18 Phase 5, action tools beside their settings) changes the same section host: show 59.3's picture before 35 builds, or build 59.3 after it.
- **Grey help text:** the step 2 plan, [design-step2-named-sizes-colors-and-themes.md](design-step2-named-sizes-colors-and-themes.md) (named colours; 6 decisions). The contrast guard (`tests/test_contrast_guard.py`, WCAG AA 4.5:1) and the text-size floor stay in force.
- **Strip cards:** the Location Manager's list view (`#manage-list-view`, `inv_loc_mgr.js:1164`; toggled at `:195`, `:252`), cards from `ui_builder.js`. Keep the scanner QR badges and Group 40.6's ↩️ RETURN footer. Step 3 plan, decision 8(b), offers the same mock-up.

## Design

- One sample folder, e.g. `review-samples/2026-10-NN-design-samples/`, numbered per item, before / after pairs. Walk Derek through them one at a time in chat.
- Then one small build per pick, each with its contrast and text-size checks and a deliberate visual baseline recapture.

## Tests (per build)

- 59.2: `tests/test_qr_under_buttons_js.py` / `_e2e.py` extended to the slot picker's panel (each QR under its button, in QR order); the picker's keyboard idiom (←/→, Enter, Esc) and its scan handling unchanged (`window.enterIsAScan()`).
- 59.1 / 59.3 / 59.5: their existing E2E and visual baselines, recaptured after the look is approved; `tests/test_contrast_guard.py` and `tests/test_text_size_guard.py` on the new surfaces.
- The full sweep before each merge (frontend).

## Done when

- Derek has seen each sample, and each pick is built (or he has parked it).

## Risks

- Restyling ahead of a sample (the standing order).
- The slot picker carries a lot of move logic (Swap / Overwrite contract, refusals, `send`): a layout change must leave `send` and the scan handling alone.
