# Group 55: 📖 README, In-App Help & Name Leftovers

**Branch name (when started):** `feature/group-55-readme-help`
**Estimated effort:** MEDIUM (~7–13 h, 1.5–2 sessions). 55.1 README ~3–6 h · 55.2 leftover text ~1 h · 55.3 in-app help ~3–6 h for the first dialogs.
**Risk:** **LOW.** 55.1 and 55.2 are docs and config-example text; 55.3 is frontend help panels. Never capture secrets in screenshots (Settings shows printer API keys), and a `?` inside a dialog must never eat scanner input.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). Derek's answers are in (2026-10-19); nothing waits on him.** Not in the 48 + 49 + 51 + 52 bundle.
> Documentation, in two places Derek will actually use: a short README for him, and help one click away inside each dialog. Every decision and his exact answers: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **55.1** | Filed 2026-08-13: *"Add readme documentation and images to the readme file for the Filament Command Center project."* | A short README **written for Derek**, with 4–6 fresh screenshots. |
| **55.2** | Derek, 2026-05-31: *"Rename inventory hub to Filament Command Center."* | **The leftover text only** ("Inventory Hub" in the config examples; the old Jan-2026 manual retired in favour of the README). **The full rename of every reference stays on the buglist as eventual work** (Derek's answer). |
| **55.3** | *"Help button to provide information on how to use a modal, and to try and store information about how things work in the code."* | **In-app help per dialog**, NOT folded into the README (Derek's answer). |

## Decisions

- **Derek (2026-10-19):**
  - **55.3, help per dialog: keep it, as in-app help.** *"No one really reads documentation… keeping the information available at a quick click is important."* Part of an eventual documentation overhaul.
  - **55.2, the name:** the README is written for him and the "Inventory Hub" text gets a text-only pass now, but **the full rename of every reference to Filament Command Center stays on the list as eventual work** (*"unless of course the entire scope and abilities of the project change, like the color picker or project manager"*).
- **Claude's calls (offered for veto on 2026-10-19; only the rename part was changed, above):** the README is written for Derek (what FCC is, the daily flows, how prod updates); only the leftover "Inventory Hub" text changes; the old Jan-2026 manual is retired; folders, containers and the TrueNAS app keep their names.

## Today's code and docs (anchors, `dev` @ `c5c5aa6`)

- **No README** at the repo root or in `inventory-hub/` (`git ls-files`: only `.githooks/README.md`, `inventory-hub/data/README.md` and the two `docs/agent_docs/phase-2-*/README.md`). The repo is `github.com/derekp10/Filament-Command-Center`; whether it is public is unclear from here.
- **Stale user docs** (last touched 2026-04-05) in `docs/Filament-Command-Center (FCC)/`: `INVENTORY_SYSTEM_MANUAL.md`, titled "📘 Inventory Hub - System Operator Manual" (it describes `scanner.py`, FilaBridge and a locations CSV), `SCANNER_STYLE_GUIDE.md`, plus `Notes.md`, `PromptRefinement.md` and `SPOOLMAN_API_RULES.md`.
- **The screen already says Filament Command Center** (`inventory-hub/templates/dashboard.html:7`, `:19`) and has since January. Leftover text: `inventory-hub/.env.example:1` ("# --- INVENTORY HUB CONFIGURATION ---"), `config.json.example:21` ("--- INVENTORY HUB SETTINGS ---"), the logger name `InventoryHub` (`state.py:67`; tests pin it, leave it).
- **Infrastructure names stay** (the eventual rename): the `inventory-hub/` folder, the compose service and container (`inventory-hub/docker-compose.yml:2-3`), the TrueNAS app (`update.sh:5` `APP_NAME`), the prod folder (`update.sh:8` `TARGET_DIR`), the P-touch puller's search path (`ptouch-data-pullers/generate_location_labels.py:6`).
- **Screenshots:** 25 UI screenshots exist as visual baselines (`inventory-hub/tests/__screenshots__/chromium-1600x1300/`), but they show test fixtures.
- **In-app help today:** only the global `?` button (`dashboard.html:50-53`) and the `?` key, both opening the keyboard-shortcuts overlay grouped by scope (`shortcuts_registry.js:52-116`; the key waits 120 ms, `HELP_DEFER_MS`, so a scanner stream isn't hijacked). Scopes registered today include Global, Quick-Swap, Force Location Modal, Weigh / Quick-Weigh Overlay and Scan Commands (`shortcuts_registry.js:120-261`); other dialogs register their own keys with `window.registerShortcut`. No dialog has its own "how this works" text. About 18 Bootstrap modals live in `templates/components/` (`modals_*.html`, `offcanvas_search.html`) beside the `mountOverlay` panels (slot picker, Printer picker, the move question, weigh entry, …).

## Design, by sub-task

### 55.1 — the README (written for Derek, short)
- What FCC is (one paragraph); the daily flows: scan a spool then a place; slot labels and Quick-Swap; Return; weigh; print labels through the P-touch CSVs; the ⏸️ PENDING DEREK idea in one line.
- How prod updates (`update.sh` on TrueNAS, the dev → main release) and where things live (dev `:8000`, dev Spoolman `:7913`, prod Spoolman `:7912`).
- Dev setup and the test commands: a pointer to CLAUDE.md's Testing section, not a copy.
- 4–6 fresh, read-only screenshots of dev at 1600×1300 (the dashboard, the Location Manager with a Quick-Swap grid, the slot picker, the spool window, Printer Status). **Never Settings** (printer API keys).
- A short "Help inside the app" paragraph pointing at 55.3.

### 55.2 — the leftover text
- Fix `.env.example:1` and `config.json.example:21`.
- Replace `INVENTORY_SYSTEM_MANUAL.md` with a pointer to the README (or delete it; it describes a FilaBridge and a `scanner.py` that no longer exist). Keep `SCANNER_STYLE_GUIDE.md` and the other files there only if still true; read each first.
- Don't rename the logger, folders, container, compose service, TrueNAS app or prod folder.

### 55.3 — help one click away in each dialog
- **One source of help text:** a small registry beside the shortcuts (e.g. `window.registerHelp({scope, title, lines})` in `shortcuts_registry.js`, or its own module loaded before the dialogs), keyed by the same scope names the shortcuts use, so a dialog's keys and its "how this works" lines show together.
- **How you reach it:** a small ❓ in each covered dialog's header, and the `?` key / button become context-aware: with a covered dialog open, they show that dialog's help first (its few lines, then its keys); with none open, the full shortcuts overlay as today.
- **Mount** through `window.mountOverlay` with `host` = the dialog (so it closes with it) and the tier above it; `mountOverlay` owns Escape. Keep the 120 ms defer for the `?` key so a scanner stream is never hijacked, and never handle `?` while a text field has focus.
- **First dialogs (the daily ones; Claude's call):** the Location Manager (including the Quick-Swap grid and the DEPOSIT card), the spool window, the filament window, the Add / Edit wizard, weigh-out and Quick Weigh, the move question (Load it instead / Just store it / Cancel), the slot picker and the Printer picker, the label queue and backlog. The rest follow in the documentation overhaul.
- **The words:** a few plain lines per dialog (what it is for, what each main button does, which scans work while it is open), written for Derek; no code paths. The README's flow section and the help may share wording.
- Keyboard and contrast standing orders apply to the help panel itself.

## Tests

- 55.1 / 55.2: a link check on the README; `test_save_locations_atomicity.py`'s logger pins stay green (don't rename the logger).
- 55.3: Playwright: the ❓ in a covered dialog opens its help above the dialog; Escape closes only the help; the help closes with its dialog; `?` with a covered dialog open shows that dialog's help, with none open the full overlay; a scanner stream starting with `?` is not hijacked (the existing defer test still passes); the contrast guard on the help panel.

## Risks

- Secrets in screenshots; screenshots age (date them in the README).
- A `?` handler that eats scanner input or a text field's `?`.
- Help text that drifts from the code: keep it short and keyed to the same scopes as the shortcuts, so a renamed dialog shows up in review.
