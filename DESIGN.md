---
name: Filament Command Center Kiosk
colors:
  background: "#000000"
  surface: "#111111"
  surface-variant: "#1a1a1a"
  surface-high: "#1f1f1f"
  surface-highest: "#222222"
  on-surface: "#ffffff"
  on-surface-variant: "#eeeeee"
  on-surface-muted: "#aaaaaa"
  primary: "#00d4ff"
  on-primary: "#000000"
  primary-container: "rgba(0, 212, 255, 0.1)"
  secondary: "#d633ff"
  secondary-container: "rgba(214, 51, 255, 0.2)"
  warning: "#ff9900"
  danger: "#ff4444"
  danger-container: "rgba(255, 68, 68, 0.1)"
  success: "#00ff00"
  log-info: "#00ff00"
  log-warning: "#ffcc00"
typography:
  display:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "2rem"
    fontWeight: "700"
  headline-lg:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "1.5rem"
    fontWeight: "700"
  headline-md:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "1.4rem"
    fontWeight: "900"
  body-lg:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "1.1rem"
    fontWeight: "800"
  body-md:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "0.9rem"
    fontWeight: "700"
  body-sm:
    fontFamily: "'Segoe UI', monospace"
    fontSize: "0.85rem"
    fontWeight: "700"
  row:
    fontSize: "var(--fcc-fs-row)"        # 0.9rem = 14.4 px: list rows and tile data
  small:
    fontSize: "var(--fcc-fs-small)"      # 0.85rem = 13.6 px: the floor for text you read
  label:
    fontSize: "var(--fcc-fs-label)"      # 0.8rem = 12.8 px: labels in a pill or box
  code:
    fontFamily: "'Consolas', monospace"
    fontSize: "1.1rem"
    fontWeight: "400"
rounded:
  sm: "4px"
  DEFAULT: "8px"
  md: "10px"
  lg: "12px"
  full: "50%"
spacing:
  gap-sm: "10px"
  gap-md: "15px"
  padding-sm: "5px"
  padding-md: "10px"
  padding-lg: "15px"
  padding-xl: "30px"
shadows:
  text-pop-heavy: "2px 2px 4px rgba(0, 0, 0, 0.9), -1px -1px 2px rgba(0, 0, 0, 0.6), 0 0 8px rgba(0, 0, 0, 0.8)"
  text-pop-light: "1px 1px 2px rgba(0, 0, 0, 0.8)"
  neon-primary: "0 0 15px rgba(0, 212, 255, 0.4)"
  neon-secondary: "0 0 15px rgba(214, 51, 255, 0.4)"
  card-elevation: "0 4px 10px rgba(0, 0, 0, 0.5)"
components:
  spool-card:
    backgroundColor: "rgba(0, 0, 0, 0.6)"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "0.5rem"
    boxShadow: "{shadows.card-elevation}"
  id-badge:
    backgroundColor: "rgba(0, 0, 0, 0.6)"
    textColor: "{colors.on-surface}"
    typography: "{typography.code}"
    border: "1px solid rgba(255, 255, 255, 0.2)"
    textShadow: "{shadows.text-pop-heavy}"
  cmd-deck:
    backgroundColor: "{colors.surface-variant}"
    borderTop: "1px solid #333333"
    height: "160px"
---

## Brand & Style
The Filament Command Center utilizes a "Dark Mode Kiosk" aesthetic specifically designed for high-contrast, at-a-glance readability in an active 3D printing lab environment. The design prioritizes stark neon highlights over a true-black and charcoal canvas to ensure critical information stands out from across the room.

The emotional intent is utilitarian and highly functional, mirroring a "mission control" interface. The layout relies on dense information packing with strict hierarchical boundaries, using glowing accents to draw attention to active tasks and alerts. 

## Colors
The color palette relies on heavy dark mode foundations to minimize screen glare, combined with high-saturation cyberpunk-esque neons for semantics.

- **Backgrounds:** Pure black (`#000000`) and extremely dark grays (`#111111`, `#1a1a1a`) act as the primary canvas. Pure black is often used behind cards to increase the pop of the neon shadows.
- **Accents:** Neon Cyan (`#00d4ff`) represents primary navigation and active states. Neon Purple (`#d633ff`) and Warning Orange (`#ff9900`) are used for specific functional modes (e.g., Auditing, Dropping).
- **Status Indicators:** Saturated Green (`#00ff00`) and Red (`#ff4444`) provide immediate visual confirmation of online/offline statuses and success/error logs.
- **Text:** White (`#ffffff`) is the default, with subtle muting (`#aaaaaa`, `#eeeeee`) applied strictly to secondary information to preserve contrast ratios in the dark environment.
- **Text on a filament's colour has one look (2026-10-30, Derek: "we should match the style if it's more readable and better"):** white in a dark halo (the `text-pop-heavy` shadow above), so a card reads on a white spool as on a black one. Its value is written once, `--fcc-text-halo` in `global.css`'s `:root`; `.text-pop` and every class for card text on a filament colour use it, and `getFilamentStyle` (inv_core.js), the helper every filament card takes its colours from, names the class (`text`), so a new card puts it on its text. Change the look there and every card follows. Text on a box of its own (a dark label, a badge) keeps that box. Pinned by `tests/test_text_on_filament_halo.py`.

## Typography
The system employs a dual-font strategy: standard sans-serif for UI elements and monospaced fonts for technical data.

- **Primary UI:** 'Segoe UI' (falling back to monospace) is used for its legible, straightforward geometric characteristics. Font weights are pushed high (700-900) to ensure readability on small kiosk screens.
- **Technical Data:** 'Consolas' is used for logs, spool IDs, and exact metrics where character alignment is crucial.
- **Small text has a floor (Derek, 2026-10-21).** Text you read is never under **13.6 px**; a label inside a pill or box (badges, tags, chips, IDLE / PRINTING, counts, the "📷 Scan to …" captions under QR codes, short ALL-CAPS labels) never under **12.8 px**; list rows and tile data are **14.4 px**, as in the Low stock window. Text already big enough, headings, buttons, spacing, colours and layouts are left alone.
  - **Use the named sizes, never a hand-typed one under the floor.** They live on `:root` in `global.css`: `--fcc-fs-label` (0.8rem, 12.8 px), `--fcc-fs-small` (0.85rem, 13.6 px) and `--fcc-fs-row` (0.9rem, 14.4 px). The per-browser Text size setting (Settings → 🖥️ This Browser, `fcc.textSize`) gives them other values, so a size typed by hand would not follow it: **Small** is the compact look FCC had before the rule (0.75 / 0.8 / 0.85 rem: a badge 12 px, a note 12.8 px), **Standard** is the rule (the default), and **Large** / **Extra Large** grow the root to 18 / 20 px so everything grows together. Sizes are in `rem`, never `px`, so they follow the browser's zoom and the root size; so are the widths of windows, panels and tiles that hold text (a `px` box stays put while its text grows, and cuts it short).
  - **Bootstrap's own sizes are held to it app-wide:** a `.badge` is `max(var(--fcc-fs-label), 0.75em)` (a badge in a heading keeps its bigger size) and `.small` / `small` / `code` / `kbd` are `max(var(--fcc-fs-small), 0.875em)`, so small text inside small text no longer drops to 12.25 px.
  - **Kept by two tests:** `tests/test_text_size_floor.py` (offline: fails on a hand-typed size under 13.6 px in any `.css`, `.js` module or template, except a short allowlist with reasons) and `tests/test_text_size_guard.py` (opens the screens in a browser and fails on any text under its floor). A new label style that should get the 12.8 px floor uses `--fcc-fs-label`, which is how the guard knows it is a label.
- **QR codes take their button's colour.** In a question with "📷 Scan to …" QR codes, each QR card's border and caption are the colour of the button it stands for (amber for a `btn-warning` like "Load it instead", cyan for `btn-info`, grey for `btn-secondary`, purple for `btn-purple`), so it is clear at a glance which code matches which button. Pass the button's tone to `window.attachConfirmQRs` (`confirmTone` / `storeTone` / `cancelTone`).
  - **"No box" has its own colour (Derek, 2026-10-23).** In "Record it as coming from…" it was `btn-secondary` beside Cancel's `btn-dark`, and the two QRs read alike. It is now `btn-purple`: FCC's own variant in `global.css` (Bootstrap's purple `#6f42c1`, which Bootstrap has no button for; white text 6.5:1), its QR the `purple` tone. `tests/test_qr_button_tones_js.py` keeps its QR at least ΔE 40 (CIE76) from Cancel's, the slot's cyan and the amber Load.
  - **Each QR sits under its own button (Derek, 2026-10-22).** Put the buttons the QRs stand for in one row, one `<button>` per QR in QR order (confirm, store, cancel), and pass that row as `alignTo`: the row becomes a grid of one column per button and the QR row joins it as a subgrid, so each column is as wide as its button or its QR, the button fills it and the QR is centred under it, at every Text size and on a phone. Buttons without a QR go on a line of their own (above, as in "Record it as coming from…"). Kept by `tests/test_qr_under_buttons_e2e.py` (each QR's centre within 1 px of its button's). The slot picker's Swap / Overwrite panel is not aligned yet (its redesign is pending).
  - **A button keeps a box id whole (review, 2026-10-22).** A label that wraps on a phone may break a line after any hyphen ("LR-MDB- / 1"), so a label naming a box goes through `window.fccKeepWhole` (each hyphenated word and "slot N" in a `.fcc-keep-whole` span that doesn't break), and the dialog calls `window.fccFitQuestion(panel)` once drawn, which lets an id too long for the screen break again rather than push the dialog past the screen's sides, and makes a question taller than the window scroll inside itself (`.fcc-question-scroll`: `max-height: calc(100dvh - 16px)`), so its top and bottom are never cut on a short phone. Only then: a scroller draws its text without the screen's sub-pixel smoothing (greyscale, not ClearType), even with nothing to scroll, so never make a question that fits a scroller. Kept by `tests/test_qr_under_buttons_e2e.py` (a 360 x 640 phone at every size) and `tests/test_qr_under_buttons_js.py`.
- **The "Text Pop":** A signature element of the design system is the heavy text-shadow applied to critical data points (like slot numbers and spool metrics). This shadow (`2px 2px 4px rgba(0, 0, 0, 0.9), -1px -1px 2px rgba(0, 0, 0, 0.6), 0 0 8px rgba(0, 0, 0, 0.8)`) ensures text remains legible even if the background contains complex imagery (like QR codes or active visual elements).

## Layout & Spacing
The layout is optimized for a full-screen, unscrollable kiosk experience (`100vh`, `overflow: hidden`).

- **Flex & Grid Layouts:** The UI relies heavily on vertical stacking (`flex-direction: column`) with defined "zones" (e.g., Top Navigation, Main Content Row, Bottom Command Deck).
- **The Command Deck:** Anchored to the bottom (`height: 160px`), this acts as the primary interaction zone, featuring large, easily tappable buttons.
- **Nothing pushes the deck off the screen.** Because the page never scrolls, the open Printer Status takes at most 45 % of the window, and less on a short one, so the whole deck (its QR codes are scanned from the screen) and a 7rem strip of Live Activity and the Buffer Zone stay on screen; past that the widget scrolls inside itself. On a tall window (1600 × 1300) it never reaches the limit. It was 40 % until each printer's name got a line of its own (2026-10-23): that line made the widget taller, and on a 1280 × 800 laptop (a Framework 12 at 150 %) or a 1366 × 768 one, 40 % hid half of the second printer's tiles. At 45 %, with no gap between printers (each row's own padding puts the divider half way), dev's two printers showed whole there at Small and Standard (and at Large on 1280 × 800). Since each printer's state and review count went onto an info line under its name (2026-10-24), every printer is a line taller: on 1280 × 800 dev's two printers still show whole at Small and Standard (353 and 358 px of the 360 px the widget may take), but at Large there (383 of 351) and on 1366 × 768 at Small and Standard (353 and 358 of 340) the widget scrolls inside itself, the first printer whole and the second's tiles a scroll away; it scrolled already on 1280 × 720, on 1366 × 768 at Large, on 1024 × 768 at Standard and on 1366 × 900 at Extra Large. Derek accepted the length ("It might make it a little longer, but it will probably read better in the long run"); the 45 % and the deck's room are unchanged. **Since 2026-10-30 (Group 50.7, Derek's pick of four)** a window too short for the open widget takes one step instead of scrolling: each printer's state and 🛑 count go beside its name, each tile's material moves up into its colour band, beside the head's label (Derek: "We could try putting it into the color section, where the toolhead name is listed"), with a little less air between printers and lines of tiles; dev's 13 heads show whole on 1280 × 800 at Large and 1366 × 768 at Standard, a spool waiting for a head and the INDX's "no bound slot" lines included, and the Buffer Zone and the Activity Log keep their room (Derek: "being able to see the buffer, if just a little bit, and the Activity log, is a good feature"). It is measured, never set by a breakpoint: the step is taken only when the widget would scroll without it, so a tall window never changes; a window too short even then still scrolls inside itself.
- **Printer Status: each printer is its name, an info line under it, then its tiles (Derek, 2026-10-23; the info line and the step in, 2026-10-24).** The first line holds the ▲▼ reorder arrows and the printer's name, always on one line: a long name ends in "…" (its full text is its title), so it never reaches the info line or the tiles. Under the name, the info line ("an information area about state and issues", Derek) holds the state badge (IDLE / PRINTING / …), then the 🛑 N count of print reviews. Then the tiles. The name, the info line and the tiles all start at the same place, a step in from the arrows, so the name comes first and the state, the reviews and the tiles read as its own. (For a few hours the state and the count came before the name, lined up in a column; Derek: "While having the status information first is nice, you now have to go hunting for the printer name to know what those statuses apply to.") The state and the count have slots of the same width on every printer: the state's is as wide as ATTENTION, the widest state PrusaLink's status reports (each badge fills it, its text centred; a printer whose state isn't known yet keeps the empty slot), the count's as wide as "🛑 88" and kept with no reviews, so the names, the states, the counts and the tiles each line up down the page and a review coming or going moves nothing. A wider state (OPERATIONAL, from the older `/api/printer` some firmware answers instead) or a count of 100 or more widens its own slot rather than being cut, and moves only what follows it on the info line, never a name or a tile. More about a printer's state or its issues goes on the info line, after the count, in a slot of its own (a fixed width where it should line up); the slots never shrink, so the 🛑 never parts from its number, and the line wraps only if a later item doesn't fit beside them. The layout is `.fcc-ps-row`, a two-column grid in `global.css`: the arrows, and the printer's own column, which holds the name (`.fcc-ps-name`), the info line (`.fcc-ps-info`, a flex row) and the tiles (`.fcc-ps-toolheads`), spaced by their own margins (the info line 0.15rem under the name, the tiles 0.35rem under the info line); the slots get their width from a hidden `::after` holding ATTENTION or "🛑 88" in the badge's or the count's own font, so they fit at every Text size and in every font.
  - **The printers step in under the title.** Each printer, its arrows first, starts 1.5rem in, under the title's first letter, so the printers read as the title's own and not as a numbered list (Derek: "so it reads more like a sub set, and less like an ordered list"); the divider between printers steps in with them. Only where the widget's body is 23rem wide or more (from 400 px at Standard): a narrower phone keeps them at the edge, as before, because there the step would cost the second tile on each line (two tiles beside each other are 21.5rem). A container query in rem, so it comes at the same point at every Text size.
  - **The arrows are a pair, ▲ over ▼, beside the name and centred on its line, and never make the line taller.** The first printer shows only ▼ and the last only ▲; a printer between two others shows both, standing out of the name's line into the row's top padding and beside the info line, where their column is empty (each 0.875rem tall, 1px apart), so its info line and its tiles sit as far under its name as every other printer's (they sat 6.6 px lower while the pair set the line's height). The pair stays in a zero-high box on purpose, which `tests/test_ui_structural.py` allows. A pair rather than side by side, because side by side they would push the name, the info line and the tiles 20 px further in.
  - **Enter on a focused arrow moves the printer, as a click does.** The dashboard's scan accumulator cancels every Enter outside a text field (a scan ends in Enter), a focused button's own included, so the arrows answer Enter themselves, unless it ends a scan (`window.enterIsAScan`). A printer moved by keyboard keeps the focus on its arrow (its other one when it no longer has the same), so Enter again moves it on; a click lets the focus go, as before.
  - **A phone too narrow for two tiles under the name starts them at the row's edge.** The name starts 26 px into the row at Standard (the arrows and their gap), so under it a row has room for one tile below 426 px. Where two fit across the row, the tiles start at its edge instead, under the arrows (the row gets `.fcc-ps-edge`; the name and the info line stay where they are): two to a line from 376 to 425 px at Standard (an iPhone 12 to 16 at 390 or 393 px, a Pixel or a Galaxy at 412), never more than two, the most a window a little wider has under the name. Below 376 px one a line, under the name, and so on a 390 or 412 px phone at Large and Extra Large (two don't fit there from the edge either); at Large the edge takes two from 423 to 479 px, at Extra Large from 470 to 532 px.
  - **A printer's name is plain in the page.** `data-printer` holds the plain name, attribute-escaped (`cancel_review.js` matches it to a review's `printer_name`; with the arrows' JS escape in it, "Derek's XL" never showed its count), and the arrows' `onclick` takes the name as a JS string (`SpoolCardBuilder.jsArg`).
  - **The folded strip reads per printer, as the open view does (Group 50.1; Derek, 2026-10-29: "I love every thing about this new redesign").** Each printer is its name (or its ID: Settings → This Browser, "Printers in the folded Printer Status"; hovering shows both), its state, its 🛑 N count, then its heads; no divider between printers, the names and the spacing part them. A head is its label (the toolhead-label setting: By ID, By number or By Tool + number) on its spool's colours, ringed in the colour of the open tiles' weight bars (cyan, amber under 100 g, red at 0 g); a hollow grey ring holds no spool, a dashed one has no box slot feeding it, a dotted amber "?" one couldn't be read, and a spool of unknown weight reads "---". Its grams sit beside the ring (the default, as the old strip had them), under it, or only in its tooltip ("Weights in the folded Printer Status"). The strip takes what the title leaves, at least 20rem; when a printer's heads don't fit there it goes under the title, two printers that don't fit on one line take a line each from the same edge, and a printer whose heads don't fit even then scrolls them sideways, so nothing runs off the window (it did at 1024 px, at 1280 px at Extra Large, and on a phone). Measured at 1600 px, Standard: one line (54 px) with number labels and the grams beside, a line per printer (88 px) with ID labels, one line (69 px) with the grams under; the old strip took 110 px. The labels' names say what they do, never one of Derek's own heads (they read "XL-3" / "3" / "Tool 3" until 2026-10-29; a browser's old pick moves to its new name).
- **Printer Status tiles sit in even rows (Derek, 2026-10-22).** One row when all of a printer's tiles fit under its name; otherwise they split into the fewest rows with equal counts (8 → 4 + 4, 7 → 4 + 3, 10 → 5 + 5; never 7 + 1; sizes differ by at most one, the longer rows first). On Derek's 1600 × 1300 window the INDX's 8 heads are one row at Small and Standard and 4 + 4 at Large and Extra Large (4 + 4 at every size while the state and the count sat before the name, 2026-10-24's first round), and the XL's 5 one row; at 1024 px the INDX is 4 + 4 and the XL one row at Small and Standard, 3 + 2 at Large and Extra Large; a phone from 376 px wide fits two on a line at Standard (2 + 2 + 2 + 2, from the row's edge) and one at Large and Extra Large. Laid out by measuring the tile area from the name's first letter, to the fraction of a px (`inv_printer_status.js` `_balanceRows`; the count it made is the tile area's `data-fit`, the layout `data-rows`), then checked against what the browser drew; again on a resize, on a Text size change and when a review count changes (no count moves a tile since the count went onto the info line, but the review poll still lays the rows out: it costs one measure and stays right whatever the info line comes to hold). A tile never shrinks to fit (`flex: none`), so what is measured is a whole tile. Kept by `tests/test_printer_status_even_rows.py` and its `_e2e` twin.
- **The title bar gives way in steps; no button's label ever wraps.** From 992 px up it is one line: as room runs out its spacing tightens, Backlog and Queue show their icon and number alone (Settings → This Browser → Title bar buttons on Automatic; Low stock too with One number, while Low and Out keep their words, which tell the two numbers apart), ADD INVENTORY reads ADD, the version badge shows its date and time alone, and last the title shortens with "…". The badge never goes (Group 57.3, Derek, 2026-10-28: he reads the build's date at a glance), and while the title is cut it keeps 1rem from the Spoolman light. With When the title bar is full on Take a second line (Settings → This Browser; Derek, 2026-10-29), the title is never shortened: the bar takes its second line instead. Each step is taken only while the title would otherwise be cut, so where it comes depends on the window, the Text size and the bar's live counts (🏷️ Backlog, 🛒 Queue, ⚠️ Low stock), not on a fixed width (`titlebar_fit.js`, Group 57 review); if the buttons still don't fit with every step taken, or the title is cut to nothing and the badge would run under them (review of 57.3: its date was drawn under the Spoolman light), the bar takes a second line rather than push ⚙️ off the screen or draw over the buttons; on two lines the badge is whole again. A load doesn't step and step back: until the counts' first answer the bar takes at least the steps it settled on last time at that window width, Text size and title-bar settings (each keeps its own), and the counts' placeholders are no wider than a count, so they never need a step the counts don't. A load at a width, Text size and settings the bar has seen, whose counts take the steps they took last time, takes no step when they come (the buttons still shift a little as the dashes become numbers); the first load at a width, Text size or setting, or one whose counts grew since, can take one then. Below 992 px Bootstrap puts the buttons on a line of their own and the spacing and ADD steps always apply; a row too wide for the window moves its last buttons onto another line rather than off the screen, and the bar grows to hold its lines.
- **A stale count looks stale.** A title-bar count that a later read couldn't refresh (⚠️ Low stock, 🏷️ Backlog) keeps its number with a "?" after it and a dashed border, and its tooltip says why ("Spoolman didn't answer just now", "FCC didn't answer just now"); before its first answer a count reads "–" ("(–)" on 🏷️ Backlog and 🛒 Queue), and "?" alone when that first read failed, never a 0 nobody read. A heartbeat that hasn't answered after 30 s counts as one that failed. A list and its count name the same cause. The "?" is drawn in the button's own padding, on the number's line, and takes no room, so a blip never moves the bar; a filled button (hovered, focused, or the filled 🏷️ Backlog) keeps its dashes, its fill stopping inside the border.
- **Bigger text, same fit.** At Large and Extra Large a width in `rem` grows too, so a `min-width` of 20rem or more is capped by the screen (`min(26.25rem, 94vw)`), or a dialog is wider than a phone and cut on both sides (`tests/test_text_size_floor.py` checks it).
- **Dense Data Cards:** Spools and filaments are displayed in tightly packed grids (`repeat(auto-fill, minmax(170px, 1fr))`) to maximize the number of items visible simultaneously.

## Elevation & Depth
Depth is simulated using a combination of subtle borders, dark drop shadows, and neon glows.

- **Structural Containers:** Main content areas (like logs and the buffer) use solid 1px charcoal borders (`#333333`) to separate them from the pure black background.
- **Floating Elements:** Modals and "Chameleon Cards" utilize a standard drop shadow (`0 4px 10px rgba(0, 0, 0, 0.5)`) to float above the interface. Modals also enforce a strict Z-index hierarchy (up to 15000 for SweetAlerts) to manage overlapping popups.
- **Active Glows:** Instead of relying entirely on background color changes, active states (like a selected slot or an active audit mode) apply a heavy box-shadow glow using the accent colors (e.g., `0 0 15px rgba(0, 212, 255, 0.4)`). 

## Components & Interaction
Interactions are tactile and immediate, providing clear feedback.

- **Buttons & Action Badges:** Interactive elements scale down slightly on click (`transform: scale(0.95)`) rather than pushing "down," creating a responsive, digital-button feel. Hover states increase brightness and scale up slightly.
- **QR Integrations:** QR codes are treated as primary navigation and interaction elements. They are explicitly styled with white backgrounds and 4px-6px border radii to ensure they remain scannable against the dark UI.
- **Live Overlays:** Critical processes trigger full-screen overlays with heavy alpha layers (`rgba(0,0,0,0.85)`) and large, glowing text to prevent accidental interactions during background tasks.
