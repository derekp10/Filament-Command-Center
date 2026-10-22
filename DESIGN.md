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
- **QR codes take their button's colour.** In a question with "📷 Scan to …" QR codes, each QR card's border and caption are the colour of the button it stands for (amber for a `btn-warning` like "Load it instead", cyan for `btn-info`, grey for `btn-secondary`), so it is clear at a glance which code matches which button. Pass the button's tone to `window.attachConfirmQRs` (`confirmTone` / `storeTone` / `cancelTone`).
- **The "Text Pop":** A signature element of the design system is the heavy text-shadow applied to critical data points (like slot numbers and spool metrics). This shadow (`2px 2px 4px rgba(0, 0, 0, 0.9), -1px -1px 2px rgba(0, 0, 0, 0.6), 0 0 8px rgba(0, 0, 0, 0.8)`) ensures text remains legible even if the background contains complex imagery (like QR codes or active visual elements).

## Layout & Spacing
The layout is optimized for a full-screen, unscrollable kiosk experience (`100vh`, `overflow: hidden`).

- **Flex & Grid Layouts:** The UI relies heavily on vertical stacking (`flex-direction: column`) with defined "zones" (e.g., Top Navigation, Main Content Row, Bottom Command Deck).
- **The Command Deck:** Anchored to the bottom (`height: 160px`), this acts as the primary interaction zone, featuring large, easily tappable buttons.
- **Nothing pushes the deck off the screen.** Because the page never scrolls, the open Printer Status takes at most 40 % of the window, and less on a short one, so the whole deck (its QR codes are scanned from the screen) and a 7rem strip of Live Activity and the Buffer Zone stay on screen; past that the widget scrolls inside itself. On a tall window (1600 × 1300) it never reaches the limit.
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
