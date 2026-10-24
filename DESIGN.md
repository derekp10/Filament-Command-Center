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
- **Nothing pushes the deck off the screen.** Because the page never scrolls, the open Printer Status takes at most 45 % of the window, and less on a short one, so the whole deck (its QR codes are scanned from the screen) and a 7rem strip of Live Activity and the Buffer Zone stay on screen; past that the widget scrolls inside itself. On a tall window (1600 × 1300) it never reaches the limit. It was 40 % until each printer's name got a line of its own (2026-10-23): that line made the widget taller, and on a 1280 × 800 laptop (a Framework 12 at 150 %) or a 1366 × 768 one, 40 % hid half of the second printer's tiles. At 45 %, with no gap between printers (each row's own padding puts the divider half way), dev's two printers show whole there at Small and Standard (and at Large on 1280 × 800). Where the deck and the 7rem strip leave less room (1280 × 720, or 1366 × 768 at Large) the widget still scrolls: that is the cost of the name's own line. Since the tiles sit under a name that starts past the state and the review count (2026-10-24), narrower windows need more rows, and it also scrolls on a 1024 × 768 window at Standard and a 1366 × 900 one at Extra Large, where it fitted.
- **Printer Status: each printer is a header line, its tiles under the name (Derek, 2026-10-23; the order and the step in, 2026-10-24).** The header line holds the ▲▼ reorder arrows, the state badge (IDLE / PRINTING / …), the 🛑 N count of print reviews, then the name, in that order and always on one line, so a glance down the left says which printer is idle, printing or needs attention (Derek: "all that data lines up so your eyes don't have to dart all over the place"). The state and the count have slots of the same width on every printer: the state's is as wide as ATTENTION, the widest state PrusaLink's status reports (each badge fills it, its text centred; a printer whose state isn't known yet keeps the empty slot), the count's as wide as "🛑 88" and kept with no reviews, so the states, the counts and the names each line up down the page and a review coming or going moves nothing. A wider state (OPERATIONAL, from the older `/api/printer` some firmware answers instead) or a count of 100 or more widens its own slot rather than being cut. The name gives way and ends in "…" when the line is short (its full text is its title), and the slots never shrink, so the 🛑 never parts from its number and a long name can never reach the tiles. The tiles start under the name's first letter, so they read as the printer's own. The layout is `.fcc-ps-row`, a four-column grid in `global.css` (the arrows, the state, the count and the name, whose column the tiles share), the header line a subgrid of the last three; the slots get their width from a hidden `::after` holding ATTENTION or "🛑 88" in the badge's or the count's own font, so they fit at every Text size and in every font.
  - **The printers step in under the title.** Each printer, its arrows first, starts 1.5rem in, under the title's first letter, so the printers read as the title's own and not as a numbered list (Derek: "so it reads more like a sub set, and less like an ordered list"); the divider between printers steps in with them. Only where the widget's body is 23rem wide or more (from 400 px at Standard): a narrower phone keeps them at the edge, as before, because there the step would cost the second tile on each line (two tiles beside each other are 21.5rem). A container query in rem, so it comes at the same point at every Text size.
  - **The arrows are a pair, ▲ over ▼, centred on the name's line, and never make the line taller.** The first printer shows only ▼ and the last only ▲; a printer between two others shows both, standing out of the line into the row's top padding and the gap over the tiles (each 0.875rem tall, 1px apart), so its tiles sit as far under its name as every other printer's (they sat 6.6 px lower while the pair set the line's height). A pair rather than side by side, because side by side they would push the name, and its tiles, 20 px further in.
  - **Enter on a focused arrow moves the printer, as a click does.** The dashboard's scan accumulator cancels every Enter outside a text field (a scan ends in Enter), a focused button's own included, so the arrows answer Enter themselves, unless it ends a scan (`window.enterIsAScan`). A printer moved by keyboard keeps the focus on its arrow (its other one when it no longer has the same), so Enter again moves it on; a click lets the focus go, as before.
  - **A phone too narrow for two tiles under the name starts them at the row's edge.** The name starts 169 px into the row at Standard (the arrows, the state, the count and their gaps), so under it a row has room for at most one tile below 569 px. Where more fit across the row, the tiles start at its edge instead, under the arrows (the row gets `.fcc-ps-edge`): two to a line from 376 px (an iPhone 12 to 16 at 390 or 393 px, a Pixel or a Galaxy at 412), never more than two, the most a window a little wider has under the name. Below 369 px, where none fits under the name, one a line from the edge; from 369 to 375 px one a line under the name.
  - **A printer's name is plain in the page.** `data-printer` holds the plain name, attribute-escaped (`cancel_review.js` matches it to a review's `printer_name`; with the arrows' JS escape in it, "Derek's XL" never showed its count), and the arrows' `onclick` takes the name as a JS string (`SpoolCardBuilder.jsArg`).
  - **The collapsed strip keeps every chip on the screen.** Each printer's chips are a group (its state first, its 🛑 N count last); a group wider than the window wraps its own chips onto another line, its divider running down beside them, so the last heads and the count never run off the right edge (they did at 1024 px, at 1280 px at Extra Large, and on a phone). Where it fits, the strip is one line per group, as before.
- **Printer Status tiles sit in even rows (Derek, 2026-10-22).** One row when all of a printer's tiles fit under its name; otherwise they split into the fewest rows with equal counts (8 → 4 + 4, 7 → 4 + 3, 10 → 5 + 5; never 7 + 1; sizes differ by at most one, the longer rows first). On Derek's 1600 × 1300 window the INDX's 8 heads are 4 + 4 at every size (one row at Small and Standard until the state and the count moved before the name, 2026-10-24: under the name they are 25 px short of one row) and the XL's 5 one row; a phone from 376 px wide fits two on a line at Standard (2 + 2 + 2 + 2, from the row's edge) and one at Large and Extra Large. Laid out by measuring the tile area to the fraction of a px (`inv_printer_status.js` `_balanceRows`; the count it made is the tile area's `data-fit`, the layout `data-rows`), then checked against what the browser drew; again on a resize, on a Text size change and when a review count changes its slot's width. A tile never shrinks to fit (`flex: none`), so what is measured is a whole tile. Kept by `tests/test_printer_status_even_rows.py` and its `_e2e` twin.
- **The title bar gives way in steps; no button's label ever wraps.** From 992 px up it is one line: as room runs out its spacing tightens, ADD INVENTORY reads ADD, the version badge goes, and last the title shortens with "…". Below 992 px Bootstrap puts the buttons on a line of their own, and a row too wide for the window moves its last buttons onto another line rather than off the screen; the bar grows to hold its lines. The steps are container queries in `rem`, so they come at the same point at every Text size.
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
