# Step 2 plan: named sizes and colors, the base for themes

_Written 2026-10-21 for Derek, to go through one decision at a time. It is a plan, not a build order. The numbers
come from a scan of `dev` at `6e6bdd4`, with code comments left out._

## In short

- FCC's look is typed by hand: **1,222 colors (257 different) and 364 text sizes**, spread over 33 files.
- Step 2 moves them onto **names kept in one file**, with **nothing changing on screen**. The readability build adds the first three.
- A sandbox test already did this for `global.css`: **0 differences** across 1,058 elements, and a pixel-identical screenshot.
- Then a new theme's look is just new values for the same names. Today's look becomes **"Classic"**, theme one, the default.
- Filament colors, QR codes and the print label stay outside every theme.
- Effort: about **8 build sessions** in small batches. The first small step is **one**.

## Words used here

- **Named value** (designers call these "design tokens"): a color or size written once, in one file, under a name
  such as `--fcc-accent`, and used by that name everywhere else. Change it in that one place and every screen
  follows. Browsers support these directly (CSS "custom properties"), with no extra library.
- **Theme**, in your sense: a whole alternative design you can pick. It has two layers:
  - its **look**: colors, text sizes, fonts, corners, shadows. Step 2 makes this layer swappable.
  - its **layout**: which screens exist and what goes where (a phone view, printer pictures). That is the step 3 doc.
- **Classic**: today's look, exactly as it is now.
- **Session**: one sitting of Claude's build work, tests included.

## What exists today

**DESIGN.md** (repo root) is a design sheet for the "Dark Mode Kiosk" look: 19 color names, 7 text styles, 5 corner
sizes, 6 spacing names and 5 shadows, plus a page of description.
- It was written once, on 2026-04-22, and not touched again until this week, when the readability build began
  adding the new size rule to its Typography section. No code or test reads it.
- Since then 300 commits have changed the frontend. `global.css` grew from 1,233 to 1,887 lines, and the
  JavaScript from 12 files (7,350 lines) to 26 files (29,455 lines).
- Today only 31% of the code's colors match it (23% if you leave out plain black and white). In April it was 50%.
- Its smallest text style, 0.85rem (13.6 px), happens to be exactly the reading floor you just approved.

**The code** has almost no names:
- 1,222 hand-typed colors: 339 in `global.css` (28%), 817 in JavaScript (66%), 76 in templates (6%). 120 of
  the values are used only once.
- One color, many shades and spellings. DESIGN.md's one cyan is 26 different cyans in the code. The title is
  `#00d4ff`, while the Backlog button and the Printer Status weight bars use Bootstrap's `#0dcaf0`. DESIGN.md's
  one warning orange is about 30 ambers and yellows: `#ffc107` is used 32 times, `#ff9900` itself twice.
  `#fff`, `#FFFFFF` and `#ffffff` are all the same white.
- 364 hand-typed text sizes with 53 different values. 274 of them are in JavaScript.
- Most of the look isn't in the style sheet at all. There are 760 `style="…"` attributes (646 of them built by
  JavaScript), 272 places where JavaScript sets a style directly, and 3 modules that carry their own style sheet
  (`inv_stock.js`, `slot_picker.js`, and one rule in `inv_details.js`).
- The backend types colors too: 246 of the 316 Activity Log calls pass a color, such as `ffaa00` (100 times) or
  `ff4444` (90). Each becomes a colored dot with a white border written into the log line.
- The only named value in the JavaScript is `window.OVERLAY_Z`, the layer numbers for pop-ups (20000 and 20100).
  38 other layer numbers are typed by hand, 20 different ones from 1 to 30000.

**Being built now:** the readability build adds FCC's first three named values, at the top of `global.css`:

| Name | Standard | Used for |
|---|---|---|
| `--fcc-fs-label` | 12.8 px | labels in a pill or box: badges, chips, IDLE / PRINTING, counts |
| `--fcc-fs-small` | 13.6 px | the floor for text you read: names, ids, notes, hints |
| `--fcc-fs-row` | 14.4 px | list rows and tile data |

Bootstrap's badges and small text are held to these names too. The Text size setting (Small, Standard, Large,
Extra Large) gives the names other values. That makes it FCC's first "mode switch": a theme will work the same way.

## Why names come first

Every later idea gets cheaper with names, and stays hard without them:
- **Text size:** the setting changes a few names, not 364 sizes in 26 files.
- **A second look:** change the values behind the color names, not 1,222 colors.
- **Phone and tablet views** (step 3): new screens use the same names, so they match Classic without copying values.
- **Tidying look-alikes:** merging two cyans means pointing two names at one value. You see a before/after picture
  first.
- **No more drift:** once names exist, a test can refuse new hand-typed colors.

## What it takes, batch by batch

Each batch swaps hand-typed values for names, proves nothing changed, and is committed on its own.

| # | Batch | Files (colors in each) | Colors | Sizes | Sessions |
|---|---|---|---|---|---|
| 1 | **The first small step** (below) | new names file, `global.css`, 2 new tests | the most-used | – | 1 |
| 2 | The rest of the style sheet | `global.css` | rest of 339 | 54 | ½ |
| 3 | Page templates | `modals_details.html` (34), `modals_config.html` (15), `dashboard.html` (7), 5 small | 67 | 32 | ½ |
| 4 | Core and cards | `inv_core.js` (128), `ui_builder.js` (52), `inv_printer_status.js` (24) | 204 | 66 | 1 |
| 5 | Windows that style themselves | `inv_stock.js` (90), `cancel_review.js` (66), `slot_picker.js` (45), `weight_entry.js` (27), 2 small | 239 | 90 | 1 |
| 6 | The big windows | `inv_details.js` (97), `inv_cmd.js` (90), `inv_loc_mgr.js` (47), `inv_wizard.js` (34) | 268 | 61 | 1½ |
| 7 | Settings and the rest | `inv_config.js` (46), `inv_settings.js` (36), `inv_backlog.js` (12), `inv_quickswap.js` (43 sizes), 6 small | 106 | 57 | 1 |
| 8 | Shadows, corners, layers (and some spacing) | everywhere | – | – | 1–2 |
| later | The Activity Log's colored dots, once a second look exists | `state.py` + 15 backend files | 246 calls | – | 1 |

Total: about 8 sessions, plus 1 later. Past estimates ran about 30% low, so plan for up to 10.

What a change looks like:
- In the style sheet, `color: #00d4ff` becomes `color: var(--fcc-accent)`.
- In JavaScript the same text works inside a `style="…"` string and in `el.style.color = …`, so the HTML each
  function builds keeps its shape. The readability build already writes small text sizes this way, for example
  `font-size:var(--fcc-fs-label)` in `dashboard.html`.
- See-through shades (85 of the 257 values) use a three-number name: `rgba(var(--fcc-accent-rgb), 0.4)`. The
  sandbox test proved this form too.
- The text sizes the readability build doesn't touch (about 290) move onto size names in the same pass, since each
  file is open anyway.
- The spool label page (`label_spool.html`, made for printing) is left alone.

**Spacing** is the least urgent part. There are 569 gaps and paddings with 35 different values, mostly in pixels
(`10px` 86 times, `6px` 79, `8px` 77). No theme needs them yet. They do matter for the bigger text sizes: text
grows, but pixel gaps and the 225 widths and heights typed in pixels don't. Examples are the 205×210 px slot
picker tiles, the 70 px title bar and the 160 px command deck. Spacing names written relative to the text size
would let the gaps grow with the text and keep the proportions you asked for. Batch 8 names the shadows (the
text-pop shadow is copy-pasted 9 times), the corners (15 values) and the layers (20 values). Spacing gets names
only where a bigger text size or a new view needs them.

## How it stays looking the same

You've seen the look drift every time this code changed hands, so this matters most. There are four guards,
three of them new:

1. **A measured fingerprint of every screen (new).** A sandbox browser draws each screen with made-up data and
   records 16 measured values on every element: colors, shadows, text sizes, layers. The test compares them
   before and after.
   - Tried already on the dashboard and its 11 templates: 1,058 elements, **0 differences** with `global.css`
     on names, and a pixel-identical screenshot. That trial left out Bootstrap's own styles and hover states; the
     real test includes them.
   - It is sensitive. Changing one shade by one step (`#00d4ff` to `#00d4fe`) showed up in 204 places. The
     picture checks allow 1% of pixels to differ (about 20,800 pixels), so a small badge could change color
     without them noticing.
   - It runs in the quick offline check (about 1.5 minutes), not only in the 21-minute sweep that changes dev data.
   - Pieces that JavaScript builds (spool cards, the slot picker, Printer Status, the weight entry) are drawn
     from made-up data the same way. The big windows that only run inside the live page (Location Manager, the
     wizard, spool details) get a before/after picture set for you as well.
2. **Every name must exist (new).** A misspelled name fails silently. The browser quietly falls back to a default
   and shows no error. A test lists every name used in CSS, JavaScript and templates, and fails on any name that
   isn't defined.
3. **No new hand-typed colors (new).** Each file has a count that may only go down, so new code has to use names.
   It works like the text-size floor test the readability build adds.
4. **The checks you already have:** the 25 picture baselines (reference screenshots at 1600×1300) and the
   contrast guard, in the full sweep before anything reaches `dev`.

Also: pin SweetAlert2, the pop-up dialog library, to today's exact version. It loads as "any 11.x", so its
dialogs can change look without any FCC change, out from under all of these checks.

## How a theme plugs in afterwards

- **A theme's look is one block of values for the names.** A marker on the page picks the block, for example
  `<html data-fcc-look="classic">`. Classic is today's exact values and stays the default.
- **It is chosen per browser**, like Text size (Settings → 🖥️ This Browser). The desk PC, a wall tablet and a
  phone can each have their own.
- **Three separate choices per browser:** Text size, Look, and (step 3) View. Any look works at any text size.
- **No flash of Classic.** FCC's scripts load at the end of the page. A stored choice must be applied by a tiny
  script at the top of the page, or the page draws Classic first and then flips. Text size needs this too.
- **A deeper redesign is also a layout.** A printer-pictures theme changes which screens exist and what goes on
  them. That is a view (step 3 doc). It uses the same names, so it can wear Classic's look or a look of its own.
- **Every new look starts from a sample you approve** (the standing order), and gets its own picture baselines.
- **A light look is a bigger job than another dark one.** FCC runs Bootstrap in its light mode and paints dark
  over it. 653 dark-color classes are written into the markup (`border-secondary` 182 times, `bg-dark` 147,
  `text-white` 143, `text-light` 111), and 31 rules restyle Bootstrap's own parts. A light look needs those moved
  onto names too.

## What stays outside every theme

- **Filament colors are data.** A spool's color shows the same in every look. That covers `getFilamentStyle`
  (12 places in 9 files), `makeSwatchHtml` (11 places in 7 files), the color readouts, and the swatches in
  Activity Log lines.
- **The frame around a filament color belongs to the look.** `getFilamentStyle` assumes a dark page. It uses a
  `#333` stand-in for a spool with no color, adds a grey rim to near-black filament so it doesn't vanish into the
  background, and draws dark overlays under the text. These become look names. The filament color itself is
  never touched.
- **Text on a filament color relies on the text-pop shadow** (`.text-pop`, a look you approved). Caution: the
  contrast guard can't score text over a filament gradient, because it treats gradients as see-through. A new
  look has to keep a text-pop and be checked by eye.
- **QR codes stay black on white.** The QR library draws them as pictures, and they must stay that way to scan.
- **The spool label page** (`label_spool.html`) is made for printing and keeps its print sizes and Arial.

## The first small step

One session, after the readability build lands on `dev`:
1. A **names file**, `static/css/tokens.css`, loaded before `global.css`. It holds the readability build's three
   size names, names for the most-used colors, and one name for the text-pop shadow. App-wide, the most-used
   colors are `#ffffff` (163 uses), `#444444` (41), `#ffc107` (32), `#00d4ff` (28), `#555555` (27) and
   `#1e1e1e` (27).
2. The **fingerprint test** and the **every-name-exists test**.
3. `global.css` switched to those names, including its 9 copies of the text-pop shadow.
4. SweetAlert2 pinned.

Result: nothing changes on screen, the guards are in place, and every later batch can follow one file at a time.

## Decisions for Derek

Your calls come first, then the ones that just need your OK, then my own calls (veto any of them).

1. **Look-alike colors: change nothing now, or tidy as we go?** (your call)
   Example: the title's cyan (`#00d4ff`) and the Backlog button's cyan (`#0dcaf0`) are slightly different.
   - (a) Step 2 gives every existing value its own name, so nothing you see changes. Merging look-alikes comes
     later, shown to you as before/after pictures.
   - (b) Merge them during step 2: fewer names, but small visible changes on many screens.
   - Recommendation: (a). If you don't answer: (a).
2. **What to call a whole alternative design.** (your call)
   The Color Loadout plan already uses "theme" and "palette" for saved filament color sets ("Watermelon Theme",
   "Zombie Colors", an "Apply Palette" menu). Both meanings would end up in the same app.
   - (a) "Look" for colors and sizes, "View" for screen layouts. The Loadout keeps "palette".
   - (b) "Theme" for whole designs, and the Loadout's sets become "palettes" only.
   - (c) Another word: "skin", "style", "layout".
   - Recommendation: (a). If you don't answer: the code says "look" and "view", and the Settings label can still
     change later.
3. **When to do it.** (your call)
   - (a) The first small step right after the readability build. The other batches (about 7 sessions) go as
     their own run when you have a quiet window.
   - (b) One batch at a time, fitted between other work.
   - (c) Wait until the phone or tablet work starts.
   - Recommendation: (a). The new-color count stops things getting worse in the meantime. If you don't answer:
     the first small step comes next, and the rest waits for your go.
4. **DESIGN.md: what happens to it?** (needs your OK)
   - (a) The names file becomes the one source. DESIGN.md's list of values is generated from it, and its
     description stays.
   - (b) Keep updating DESIGN.md by hand alongside.
   - (c) Leave it as a historical note.
   - Recommendation: (a), so it can't drift again. If you don't answer: (a).
5. **Fix the font on phones and tablets now?** (needs your OK)
   The page asks for 'Segoe UI', then any monospace font. Phones, iPads and Linux tablets have no Segoe UI, so
   every screen there turns monospace. Adding the usual system fonts after Segoe UI should leave your Windows PC
   looking the same, and the picture checks will confirm it.
   - (a) Include it in step 2. (b) Keep it for the phone and tablet work.
   - Recommendation: (a). If you don't answer: (a).
6. **My calls (veto any of them):**
   - Pin SweetAlert2 to today's exact version. Nothing visible changes.
   - Leave Bootstrap's built-in dark mode off for now. It would remove some hand-painting, but it visibly
     changes form fields, dialog borders and grey text, so it needs its own picture review later.
   - Name shadows, corners and layers in batch 8, and spacing only where a bigger text size or a new view needs it.
   - Leave the Activity Log's colored dots alone until a second look exists. Classic doesn't need them changed.
   - Keep the names in their own file (`tokens.css`) rather than at the top of `global.css`.
