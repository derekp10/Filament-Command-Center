# Step 3 plan: other views beside the classic one

_Written 2026-10-21 for Derek, to go through one decision at a time. Nothing gets built before you approve a mockup.
Numbers: a scan of `dev` at `6e6bdd4`, plus a read-only look at dev sized like a phone and a tablet. Its screenshots:_
`review-samples/2026-10-21-views/` (on Derek's machine, git-ignored; not in the repo)

## In short

- A **view** is a different set of screens over the same data and move rules. Classic stays exactly as it is, the default.
- Four candidates: a **station view** for a wall tablet, a **pocket view** for a phone, **printer pictures**, a new **Location Manager**.
- The backend is ready: its answers are plain data any page can use. The browser code is wired into Classic.
- So the shared parts (scans, move questions, the heartbeat) come out of Classic first, proven by its pictures and tests.
- Each view gets its own address (`/station/XL`), its own picture checks, and starts from a mockup you approve.
- First milestone: **one mockup of the wall-tablet station view**, as pictures, before anything is built.

## Words used here

- **View**: a set of screens made for one kind of device or job (the desk, a wall tablet, a phone). Views share FCC's
  data, its move rules and the named colors from step 2. They differ in layout.
- **Shared core**: the parts every view needs, kept in one place so two views can't drift apart. That means what a
  scan means, how a move asks its questions, and the heartbeat.
- **Heartbeat**: the request every open FCC page makes every few seconds (5 s when active, 15 s when idle) to
  refresh what's on screen.
- **Mockup**: a picture of a screen with made-up data. Nothing is wired up.

## The four candidates

**1. Station view: a wall tablet by a printer.** One printer's heads, Quick-Swap, scanning and recent activity,
big and touchable.
- It is mostly a new layout of pieces that already exist. The head tiles come from the heartbeat. Quick-Swap and
  Return already have their own requests. Recent activity is the log. The slot picker and pop-up questions work as
  they are. A Bluetooth or USB scanner works with today's scan input, unchanged.
- Today's dashboard nearly fits a tablet held sideways (1280×800). Everything shows, but the log and buffer get
  only 170 px of height, and the 🔍 button covers LOCATIONS.
- It is the cheapest new view, so it goes first.

**2. Pocket view: a phone.** Scan, look up, weigh.
- It needs the most that's new: camera or NFC scanning, a phone layout, and scan rules that don't depend on the desk page.
- Camera, NFC, keep-screen-on and "add to home screen" all need HTTPS, a secure connection. FCC is plain HTTP on
  the home network today. A Bluetooth scanner works without it.
- Today's dashboard on a phone (390×844): the page is 702 px wide but cut off; 4 title-bar buttons and 5 of the 8
  command-deck buttons are off-screen; the deck sits below the bottom edge; the log and buffer row is 0 px tall;
  and the Locations table is 864 px wide inside a 374 px window.

**3. Printer pictures.** Each printer drawn as a picture, with each head's spool shown on the head.
- It uses the same data as the Printer Status panel (each head's spool, color, grams, the printer's state), drawn
  differently. It fits best as a style of the station view, once that exists.
- FCC doesn't know what a printer looks like yet. A Printer row holds its name, id, connection and its list of
  heads (the XL has 5, the Core One INDX 8), but no model, picture or head positions. The printer redesign notes
  list a `model` field that was promised and never built.
- The Printer Status code already expects this. Its header says the Color Loadout "can swap in printer photos with
  positioned overlays".

**4. Location Manager redesign.** This is the largest piece.
- Some of it is decided: contents shown at every level, grouped by the box or shelf they sit in, like today's Room view.
- The core question is open: is an id built from its parents (like `CR-CT-2-R1`) still the right way to name
  places? It is booked for one sit-down, together with "what identifies a printer".
- Some parts don't depend on that answer and could be mocked up earlier: the strip-card variants on `CR-CT-2-R1`,
  and an Unassigned list that scrolls inside its window.

The Color Loadout's screens (Project Library, Detail Editor, 4D Queue Editor) could become a view of their own
too (decision 9).

## What the backend already gives a new view

Everything comes back as plain data (JSON), not tied to any page:
- **The heartbeat**, `/api/dashboard_pulse`: log lines, printer status, locations, one box's contents. It makes one
  Spoolman read per tick, and says when that read failed.
- **Printers and their feeds**: `/api/printer_map`, `/api/machine/<printer>/toolhead_slots`, `/api/printer_state/<head>`.
- **Contents**: `/api/get_contents?ids=A&ids=B`, several places in one read.
- **Moves**: `/api/quickswap`, `/api/quickswap/return`, `/api/smart_move`, `/api/manage_contents`, `/api/undo`.
  The slot picker's model: `/api/placement_options`.
- **For a phone**: `/api/identify_scan`, `/api/search`, `/api/spool_details`, `/api/stock_report`, `/api/spool/update`.

The gaps:
- The heartbeat says only the printer's state (IDLE, PRINTING). The print monitor already reads the job's
  progress but doesn't pass it on. Whether your printers report time left and temperatures is unconfirmed.
- Each always-on page costs a full Spoolman spool read plus a check of every printer, every tick. An offline
  printer adds a 2-second wait. A wall tablet should ask about its own printer only.
- FCC serves one page today (`/`, the dashboard). A new view is a new page address, so the test that pins FCC's
  list of addresses gets a deliberate update.
- Printers are keyed by their display name (`🦝 XL`) in the heartbeat and in `/api/machine/…`. A tablet's bookmark
  should use the Printer row's id (`XL`, `RCOI`), so renaming a printer can't break it.

## What must be pulled apart in the browser first

The browser code was built as one page. Four things must be shared before a second view exists, or that view will
copy them and drift:
1. **What a scan means.** One function of about 480 lines (`processScan` in `inv_cmd.js`) decides nearly
   everything about a scan, and calls desk windows directly. For example, a `CMD:TRASH` scan reads the Location
   Manager's hidden box field. The server mostly just identifies the code.
2. **How a move asks.** Every move request must send today's full set of check fields (`confirmed_fed_heads`
   even when empty, `expected_feed`, `expected_spool`, and others). A client that leaves them out is told to
   reload the page, or silently loses safety checks. The old terminal scanner
   (`inventory-hub-scanner-unused/scanner.py`) shows how a second client falls behind.
3. **The heartbeat.** It decides what to fetch by looking at Classic's open windows, and hands each answer to
   Classic-only drawing code. A second view can't listen in on the data today.
4. **`inv_core.js`** mixes shared helpers with about 930 lines that only draw Classic (the Locations table, the
   log panel, the confirm dialogs). Any view that loads it gets all of it. Loading some modules also starts their
   2-second polls.

These are already reusable, and are the pattern to copy: `slot_picker.js` (the server sends its model; it writes
nothing), `weight_entry.js` (no requests, no writes of its own), `overlay_mount.js` (`mountOverlay`),
`inv_printer_status.js` (it only needs its place on the page passed in), and the move-question helpers in
`inv_core.js` (`askMoveConfirm`, `buildMoveReplay`, `confirmActivePrint`, `takeIntoBuffer`).

How this stays safe: Classic moves onto the shared core one piece at a time. Its 25 picture baselines (reference
screenshots) and the tests' 2,083 references to page elements prove nothing moved. New views use their own ids and
class names.

## Desk and scanner habits to design around

- **A fixed kiosk.** The page is exactly one screen tall and never scrolls. `global.css` has no rules for smaller
  screens, and there are 225 widths and heights typed in pixels.
- **QR codes as buttons.** 41 places draw a QR code (45–200 px): the command deck, cards, slot tiles, confirm
  dialogs. A phone can't scan its own screen. A wall tablet can keep them if a handheld scanner sits beside it.
  The confirm dialogs keep their QR codes in a separate row, so a touch view can hide them.
- **A keyboard-style scanner.** Scan input is ignored while a text box has focus. Whenever the window loses focus,
  a full-screen "SCANNER PAUSED / Click anywhere to resume" takes the next tap. On a phone or tablet that happens
  on every app switch.
- **Hover and keys.** 184 tooltips carry real meaning: the icon-only card buttons (🔍 ✏️ 🖨️ ⏏️) are named only by
  their tooltip, and touch has no hover. 57 keyboard shortcuts assume a keyboard is there.
- **One shared session.** The scan buffer, audit, bulk move and Undo are shared by every screen. Each browser saves
  its whole copy of the buffer every 2 seconds, and the last save wins. A phone, a tablet and the desk could
  overwrite each other's buffer.
- **Label checks expect a scanner.** A label only counts as verified when the scan arrives at scanner speed (every
  character within 150 ms). A camera or NFC scan must be sent the same way, or the server must accept the new
  kinds. Otherwise label checks silently stop on phones.
- **Internet for the libraries.** Bootstrap, the QR library and SweetAlert2 load from the internet, so a wall
  tablet needs internet access too.

## How you pick a view

- **Each view has its own address**: `/station/XL`, `/station/RCOI`, `/pocket`. `/` stays Classic. A wall tablet
  just bookmarks its address, so it doesn't depend on browser storage, which can get cleared.
- **A per-browser "Screen layout" setting** (Settings → 🖥️ This Browser, like Text size) chooses where `/` sends
  that browser.
- **There is always a way back.** Every other view has a "Classic view" link, and `?view=classic` always works,
  so a wrong setting can't trap you.
- Text size, Look (step 2) and View are three separate choices per browser.

## Keeping each view from drifting

- **Picture baselines per view and screen size.** Classic keeps its folder (`chromium-1600x1300/`), and no Classic
  baseline changes without your OK. New folders are added, such as `chromium-1280x800-station/`.
- **Drawn from made-up data**, as the Printer Status tests already do, so a baseline can't move when dev data
  changes. A missing element fails the check. Today's baseline tests skip instead.
- **Layout checks for touch views:** the contrast guard; every tap target at least 44×44 px; nothing scrolls
  sideways; no control that exists only as a QR code or only as a tooltip.
- **The same facts in every view.** Given the same heartbeat data, every view must show the same spool numbers,
  grams and "couldn't read" notices. This is checked offline through the shared core.
- **View code stays in `static/js/modules/`**, the only folder the existing move checks look in.
- **Only each view's default text size and look get pictures.** The other sizes get the layout checks, so the
  number of pictures doesn't multiply.

## Accessibility ideas for later

These aren't on any roadmap. They're noted so new views get them for free. The newer windows (the slot picker,
`WeightEntry`, the Low stock window) already follow most of them, so new views copy those, not the older code.
- **Text size**: the first one, being built now.
- **Real buttons with visible labels.** 83 clickable `div`/`span` elements can't be reached with Tab or read by a
  screen reader (card icons, deck buttons, Printer Status tiles); only about 2 can. Icon buttons are named only by
  tooltips.
- **Spoken updates.** Toasts and the Activity Log aren't announced to a screen reader.
- **Less motion.** There are 27 animations and no "reduce motion" option.
- **Bigger tap targets.** On the dashboard, 13 of 35 controls are under 44×44 px; the Printer Status ▲/▼ are 18×16.
- **Focus kept inside an open pop-up.** Today Tab can leave one.

## Milestones

Each one starts from a mockup you approve (the standing order). Effort is in sessions: one sitting of Claude's
build work, tests included. Past estimates ran about 30% low.

| # | Milestone | Needs first | Sessions |
|---|---|---|---|
| 1 | **One mockup of the wall-tablet station view**: pictures at 1280×800 with made-up data, nothing wired | your answers to decisions 1 and 4 | 1 |
| 2 | The shared core (scan meaning, move questions, heartbeat), behind Classic, with no visible change | step 2's first batches; the planned check on script load order | 3–4 |
| 3 | Build the station view: `/station/<printer>`, its own pictures and checks | 1 and 2 | 2–3 |
| 4 | Printer pictures, as a style of the station view: printer model, picture and head positions | 3; the printer-identity sit-down | 2–3 |
| 5 | The HTTPS decision, then a pocket view mockup, then its build | decision 2 | 3–5 |
| 6 | Location Manager mockups, then its build | the location-id sit-down | after that sit-down |

## Decisions for Derek

Your calls come first, then the ones that just need your OK, then the ones for a sit-down, then my own calls
(veto any of them).

1. **Which devices, and how will you scan on each?** (your call)
   iPhone or Android matters. On phones, NFC and the browser's built-in barcode reader exist only in Chrome on
   Android, while camera scanning through a library works on both (with HTTPS). For the tablet: will a handheld or Bluetooth
   scanner sit beside it, so its on-screen QR codes can stay, or is it touch only? NFC would mean new tags on
   spools or places (Android only); printed QR codes plus the phone camera work everywhere.
   - Recommendation: a scanner beside the tablet, and QR codes plus the camera on the phone, with no NFC for now.
   - If you don't answer: the station mockup assumes a scanner beside the tablet, and the phone waits.
2. **HTTPS on the home network?** (your call)
   A small app on TrueNAS (a reverse proxy, with a certificate) would give FCC a secure `https://` address.
   Without it, a phone can't use its camera, NFC, keep-screen-on or "add to home screen". A Bluetooth scanner works
   either way.
   - Recommendation: decide before any phone work. The station view doesn't need it.
   - If you don't answer: the phone view waits.
3. **One scan buffer for every device, or one per device?** (your call)
   Today every screen shares one buffer, audit and Undo: you could scan on the phone and drop at the desk. But two
   screens saving at once can overwrite each other.
   - (a) Keep it shared, fix the "last save wins" race, and show the shared buffer clearly on every view.
   - (b) One buffer per device.
   - Recommendation: (a). If you don't answer: (a).
4. **Wall tablet: one per printer or one for both? And print progress?** (your call)
   - One per printer (`/station/XL`, `/station/RCOI`), or one tablet showing both.
   - Besides heads, Quick-Swap, scanning and recent activity: print progress or time left? Progress needs a small
     backend addition. Time left depends on what your printers report, which is unconfirmed.
   - Recommendation: one per printer, with progress where available. If you don't answer: the mockup shows the XL
     alone, with a progress bar marked "if available".
5. **How a device picks its view.** (needs your OK)
   - (a) A bookmark per device. (b) A "Screen layout" setting per browser. (c) Both, with a "Classic view" link on
     every other view.
   - Recommendation: (c). If you don't answer: (c).
6. **The order of work.** (needs your OK)
   Station view, then printer pictures (as a station style), then the phone view (after HTTPS), then the
   Location Manager (after its sit-down).
   - Recommendation: this order. If you don't answer: this order.
7. **Printer pictures: your photos, or drawn pictures?** (sit-down)
   - (a) Your own photo of each printer. You drag a marker onto each head once.
   - (b) Drawn pictures per model (XL, Core One INDX) that ship with FCC, with nothing to set up.
   - Either way FCC must learn each printer's model, which the printer-identity sit-down already lists.
   - Recommendation: (a), with a plain outline for a printer that has no photo yet. If you don't answer: decided
     when the station mockup is reviewed.
8. **Location Manager: wait, or mock up the parts that don't depend on the sit-down?** (sit-down)
   - (a) Wait for the location-id and printer-identity sit-down.
   - (b) Mock up the view-only parts now, as pictures only: the strip-card variants on `CR-CT-2-R1`, and an
     Unassigned list that scrolls inside its window.
   - Recommendation: (b). If you don't answer: (a).
9. **The Color Loadout's screens: a view of their own?** (sit-down)
   The Project Library, Detail Editor and 4D Queue Editor could be their own view rather than more pop-ups on the
   dashboard. This belongs to the Loadout's own design sit-down.
   - Recommendation: their own view. If you don't answer: it waits for that sit-down.
10. **My calls (veto any of them):**
    - Station addresses use the Printer row's id (`XL`, `RCOI`), not its display name.
    - New views keep their code in `static/js/modules/`, so the existing move checks cover them.
    - A camera or NFC scan counts as a scanner scan for label checks, or the server learns the new kinds.
    - A station page asks the heartbeat about its own printer only.
    - Touch views have no control that exists only as a QR code or a tooltip.
    - Pin or bundle the libraries FCC loads from the internet, so a wall tablet's look can't change by itself and
      the tablet keeps working when the internet is down.
