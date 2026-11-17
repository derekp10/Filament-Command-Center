# Group 59: 🎨 Design Samples

**Branch name (when started):** `feature/group-59-design-samples` (the samples themselves live in `review-samples/`, git-ignored)
**Estimated effort:** one picture session with Derek (~2–3 h of Claude's work to make the samples), then small builds (~1–3 h each) for the ones he picks.
**Risk:** **LOW–MEDIUM.** Display only, but the standing order applies: **never restyle without a sample first** (*"my main concern here is that we standing order the wrong look, refactor everything for that look, and then have to revert everything back"*).

> **Status: `TODO` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping"). Design-first: nothing is built before Derek picks from pictures.** Whenever Derek wants to look; it blocks nothing.
> Four looks Derek flagged on his 2026-10-22 text-size walk, plus the older strip-card refactor (59.1–59.5), and since 2026-11-16 six more looks (59.6–59.11, a second sitting), made into before / after pictures, one item at a time (his format: images in `review-samples/` as clickable links, never a long doc).
> Code anchors were read on `dev` @ `d4b1ad7` (2026-10-25). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **59.1** | 🎨 Design follow-ups (a), **the slot picker in printer mode**: *"it just looks scattered, and it's hard to tell what is what"; its slots break onto a second row and leave a lot of empty space after the head list.* His idea: *a 3×3 grid for the heads.* | Two or three layouts as pictures (his 3×3 among them), on dev's XL and RCOI. |
| **59.2** | (b) **the slot picker's Swap / Overwrite / Back panel**: *"the buttons are all over the place", their two-line labels make it hard to tell which QR does what ("Yellow to Yellow, but what does yellow button do again")*: *use the move questions' pattern, three short buttons each with its QR under it, and the details as one line of text.* | The move questions' pattern, as a picture first. |
| **59.3** | (c) **Settings as a side panel**: *section names (This Browser, Connection, Behavior, …) on the left, the open section's settings on the right.* | A picture at 1600×1300 and at a phone width. |
| **59.4** | (d) **Grey help text on black** *"might need a re-think later" (the 2026-10-22 build only lifted it to pass the contrast guard): with step 2's named colours.* | Two or three greys from step 2's named colours, side by side. |
| **59.5** | 🎨 *"Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird."* (2026-10-19: *"two variants, one row per spool with all three QR badges or with one, both keeping Group 40.6's ↩️ RETURN footer"*, on a real cart, e.g. `CR-CT-2-R1`.) | The two variants as pictures. |
| _(→ 57.3)_ | (e) the title bar at Extra Large | In [Group 57](57-low-stock-at-a-glance.md), because the Low stock button decides it. |
| **59.6** | 🎨 *"Two older dialogs fail the contrast rule (found 2026-11-03 by Group 58's pictures). The ⛔ SAFETY INTERLOCK dialog's message is Bootstrap's danger red (rgb 220, 53, 69) on #1a1a1a at 28 px bold, 3.84:1 against FCC's 4.5:1, and its ⛔ blends into the red header … The 🧵 Multi-Spool Search's ✕ close button is white on cyan (about 2.0:1)."* Added 2026-11-16, with *"The wizard section chevron ▾ is 3.71:1 on its dark ground (found 2026-11-09, Group 54's review, optional)."* | A lighter red for the message; for the ✕, the dark one Derek picked for the Print Queue (Group 55); the ▾ lifted to 4.5:1. Each before / after, then the contrast guard extended to them. |
| **59.7** | 🎨 *"Where the floating 🔍 search button and 📡 log pill sit (Derek, 2026-11-11, from the README's dashboard picture)… 'the search badge is just kind of blocking the location manager barcode… having those two there does block some of the spool information in the buffer. So I guess it's more of a design/layout question more than anything.'"* Measured at four window sizes (`review-samples/2026-11-11-group55/badges/`, `L2-badges.json`): no single fixed spot is clear at every size; the gaps between deck tiles are. | Candidate default spots as pictures at 1366×768, 1600×1300, 1920×1080 and 2560×1440, and whether a parked spot is kept per window width. |
| **59.8** | 🎨 *"The filament cards have drifted apart: shore the older ones up with the newer cards' changes (Derek, 2026-10-30)… 'Wow, the search/buffer card doesn't take too well to being squished. I see a little bit of drift in the design between the versions… try and shore up older cards with more newer cards changes.'"* Five card designs draw a spool (`SpoolCardBuilder` in ui_builder.js, the Printer Status tile, the backlog rows). | A picture of each card today beside one shared design, then his pick, then the build. Pairs with 59.5 (the strip cards). |
| **59.9** | 🎨 *"The app-wide `.btn-outline-danger:hover` is 3.41:1, under AA (found 2026-11-02, Group 58; Derek's eye first). White on `#ff4444` (global.css), on 11 buttons or so… Group 58 fixed only its own button (Bootstrap's own `#dc3545`, 4.53:1). One line in global.css would fix them all, but it changes a look."* | Before / after of two or three of those buttons with Bootstrap's `#dc3545`. |
| **59.10** | 🟡 *"The vendor editor is hard to find (found 2026-11-11, Derek: 'I completely didn't even see that when I was going in to update an empty weight'). It is a small borderless ✏️ in three places… Its tooltip says 'Edit Manufacturer' while those windows say 'Brand' and 'Vendor'. Wanted: one name everywhere (Derek says 'vendor'), a ✏️ that looks like a button, and maybe a vendor list in Settings."* | The three places as pictures with a button-looking ✏️ and one name; a Settings vendor list as a sketch. Its behaviour bug (an edit not reaching the open windows) is [Group 66](66-wizard-vendor-windows.md) 66.1. |
| **59.11** | 🎨 *"One mark for 'might not be current', used everywhere (Derek, 2026-10-28)… the dashed border also means 'no box feeds this toolhead'… Wanted: one definitive mark for out of sync / couldn't read / might not be current, used by the stale counts, Group 52's 'couldn't read' notices and Printer Status' '? not read' tiles alike."* Later and optional, the same picture: *"A spinner instead of the dash before a count's first answer (Derek, 2026-10-28: 'Keep the dashes, but a spinner sounds cool too')."* | Two or three candidate marks on each of the three surfaces. |
| _(pictures for other groups)_ | Looks that other groups build, shown in this session so Derek picks once: [Group 66](66-wizard-vendor-windows.md) 66.7 (the filament's Spool Wt box marks a brand's value as inherited), [Group 71](71-cards-types-toasts.md) 71.5 (the Type badge colours) and 71.7 (a toast holding an unbroken string). | Each picture goes to its own group's build. |

> **🔄 2026-11-16 (`/refresh-groups`): 59.6–59.11 added**, so the picture session is now **two sittings** (59.1–59.5, then 59.6–59.11 and the other groups' pictures). The Low stock button's icons instead of words went to the themes ([Group 60](60-phone-and-tags.md) 60.1).

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
