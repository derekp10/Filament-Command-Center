# L18 — Config System: Recommended Design

## TL;DR

Build the **Declarative Schema + Generic Renderer** as the base architecture: a single Python `config_schema.py` declares every setting (key/type/default/section/scope/validation), one generic JS renderer paints the Settings UI from it, and `GET/PUT /api/config` validate against the same schema — so adding the Nth setting six months out is a one-line `Field` edit, not UI + backend + persistence triplicate work. It won because it is the **only** persistence model that survives the real `config.json` (passthrough-preserves every on-disk key the schema doesn't own), its verify-after-write is genuinely stronger than the locations precedent (exact dict equality, not `isinstance(list)`), and it leaves the hot `load_config()` path and the four action-tool cards untouched. We graft the Pragmatic plan's **build ORDER** (ship `save_config` + a couple of safe scalar settings first, light up the full renderer second) and its **printer_map-out-of-v1** safety stance, plus the Hierarchical/Registry **section-as-export-granularity** and **TOOLS-host-mount** ideas for later phases. We **copy** the atomic writer into `config_loader` rather than extracting/re-homing the outage-hardened `locations_db` code — the data-integrity judge's tie-breaker against the base approach's one self-inflicted risk.

## Chosen base + grafted ideas

**Base: Declarative Schema + Generic Renderer.** Two of three judges crowned it (Architect 9, Data-integrity 9); the Pragmatist ranked it best among the "big design" options (6) and its only complaints were *front-loading* and the *atomic_json extraction refactor* — both addressed by the grafts below. It is the only design that satisfies the buglist's explicit L18 directive ("Full-schema design first / self-describing schema, UI renders any new entry automatically") while passing the data-integrity bar.

Grafted decisions, and why:

| Graft | From | Why |
|---|---|---|
| **Build ORDER: `save_config` + atomic writer + 2-3 safe scalar settings FIRST; generic renderer + import/export SECOND** | Pragmatic Incremental | All three judges converged on this. Validates the single dangerous new primitive (first-ever config write) before the framework rides on it. Turns "front-loaded big-bang" into incremental shipping behind the schema. |
| **COPY the atomic helper into `config_loader`; do NOT extract `locations_db`'s** | Data-integrity judge | The base proposed `atomic_json.py` extraction. Re-homing battle-tested, incident-scarred `locations.json` code for DRY adds regression risk to an outage-sensitive path for zero user value. Copy now; consolidate into a shared module only as a separately-verified follow-up if a third caller appears (YAGNI). |
| **`printer_map` is NOT editable in v1** (read-only display) | Pragmatic Incremental | The uppercase round-trip is the single highest-risk write. Defer its bespoke editor to Phase 3 behind its own tests. The schema *declares* it (`type=printer_map`, read-only flag) so it's visible, but the generic save path never writes it in v1. |
| **`save_config` returns `{ok, error, ...}` and NEVER silent-None** (stricter than `save_locations_list`) | Data-integrity judge | `save_locations_list` logs critical then *returns silently* after a failed retry — the caller already "got success." Config must surface `LAST_CONFIG_ERROR` and a hard failure instead. |
| **Section-as-export-granularity** (`?sections=connections,printers`) | Hierarchical Tree | Distinctive, extensibility-forward; clone just "Printers" into a sibling install. Phase 4. |
| **TOOLS-host-mount: refactor action cards to mount into a passed host element**, keyed by section | Hierarchical / Registry | Cure for Derek's "clunky attributes" complaint *without* forcing actions into the settings schema. Phase 5, optional. |
| **`scope: client` declared-but-localStorage-resident fields** | All four converged | The correct, zero-data-move way to absorb `fcc.weighEntry.defaultMode`. |
| **Secret allowlist + `__secret_set__` sentinel + masking test** | Declarative + Data-integrity | `SCRAPER_API_KEY` is a live plaintext key on prod disk; it must never leave the box via GET/export. |

**Explicitly rejected:** Hierarchical Tree's "reject unknown keys to keep the file clean" (FATAL — wipes `comment*`, `print_settings`, paths on first save) and Registry/Plugin's `run_migrations()`+`normalize` **inside `load_config()`** (weaponizes the ~40-call-site hot read path into a corruption vector). We keep *all* migration/normalize logic strictly inside the save/import boundary; a read can never mutate the file.

## Config schema model

New module `inventory-hub/config_schema.py`. The schema is the contract; `config.json` is just the persisted values. Defaults live here (single source of truth) — `load_config()`'s hard-coded defaults dict gets *derived* from the schema in Phase 2 so they can't drift.

A `Field` dataclass:

```python
@dataclass(frozen=True)
class Field:
    key: str                     # flat key in config.json (or fcc.* localStorage key for client scope)
    label: str
    type: str                    # string|int|float|bool|enum|url|ip|port|secret|printer_map|hidden
    default: Any
    section: str                 # groups into a card: "connection" | "behavior" | "client" | ...
    scope: str = "server"        # "server" -> config.json ; "client" -> localStorage (declared only)
    help: str | None = None
    choices: list | None = None  # for enum
    min: float | None = None     # for int/float/port
    max: float | None = None
    secret: bool = False         # masked in GET, excluded from export by default
    readonly: bool = False       # rendered disabled (e.g. printer_map v1, server_ip if we choose)
    restart_required: bool = False
    validate: Callable[[Any, dict], None] | None = None  # raises ValueError(msg); msg surfaced verbatim
```

`type` drives **both** the JS widget chosen by the renderer **and** the server-side coercion/validation on PUT — they cannot diverge. Supported types and their widget/coercion:

| type | widget | coercion / validation |
|---|---|---|
| `string` / `url` / `ip` | text input | str; `url`/`ip` get a format check |
| `int` / `port` | `<input type=number>` | int; `min`/`max` enforced (`port` defaults 1–65535) |
| `float` | number input | float; `min`/`max` |
| `bool` | Bootstrap switch | bool |
| `enum` | `<select>` from `choices` | membership in `choices` |
| `secret` | password input + reveal eye | str; masked on GET via `__secret_set__` sentinel; written only if user retypes |
| `printer_map` | bespoke key/value grid (read-only in v1) | dict; uppercase-canonical + case-collision reject (Phase 3) |
| `hidden` | not rendered | passthrough only |

**Passthrough law (mandatory):** any key on disk *not* in the schema is preserved verbatim on save — the config analogue of `compute_dirty_extras`. This is what protects `dryer_slots`, `SCRAPER_API_KEY`, `spoolman_db_path`, `backup_directory`, `export_directory`, `print_settings`, and any `comment*` divider keys that exist on the prod file but aren't (yet) modeled.

Worked entries (drop-in for real FCC settings):

```python
SECTIONS = [
    Section("connection", "🔌 Connection", help="Spoolman / FilaBridge endpoints"),
    Section("behavior",   "⚙️ Behavior"),
    Section("printers",   "🖨️ Printers"),
    Section("client",     "🖥️ This Browser", help="Stored per-device, not synced"),
]

CONFIG_SCHEMA = [
    # 1) server_ip — server-scope, hot-applies (get_api_urls re-reads live)
    Field("server_ip", "Server IP / Host", "ip", "127.0.0.1",
          section="connection", scope="server",
          help="Host running Spoolman + FilaBridge.",
          validate=_v_host),

    # 2) spoolman_port — server-scope int with bounds
    Field("spoolman_port", "Spoolman Port", "port", 7912,
          section="connection", scope="server", min=1, max=65535),

    Field("filabridge_port", "FilaBridge Port", "port", 5000,
          section="connection", scope="server", min=1, max=65535),

    Field("sync_delay", "FilaBridge Sync Delay (s)", "float", 0.5,
          section="behavior", scope="server", min=0, max=10,
          help="Debounce before re-polling FilaBridge after a write."),

    Field("auto_recover_filabridge_errors", "Auto-recover FilaBridge errors",
          "bool", True, section="behavior", scope="server"),

    # printer_map — DECLARED but read-only in v1 (highest-risk write, Phase 3)
    Field("printer_map", "Printer / Toolhead Map", "printer_map", {},
          section="printers", scope="server", readonly=True,
          help="Edited in the dedicated map editor (coming soon)."),

    # SCRAPER_API_KEY — secret, never leaves the box
    Field("SCRAPER_API_KEY", "Scraper API Key", "secret", "",
          section="connection", scope="server", secret=True),

    # 3) fcc.weighEntry.defaultMode — CLIENT scope, stays in localStorage
    Field("fcc.weighEntry.defaultMode", "Default weigh-entry mode", "enum",
          "additive", choices=["gross", "net", "additive", "set_used"],
          section="client", scope="client",
          help="Mode the WeightEntry overlay opens in (this browser only)."),
]
```

`validate` callables receive `(value, full_cfg)` and raise `ValueError(msg)`; the message surfaces verbatim to the toast. `dryer_slots` is intentionally NOT modeled (structured list, edited elsewhere) — passthrough keeps it safe.

## Persistence & write-safety

New in `config_loader.py`. The verified landmine: `load_config()` does `defaults.copy()` then `.update(loaded)` then uppercases `printer_map` — so saving off its output bakes 7 phantom defaults into the file and re-emits normalization. **The save source must be a raw read.**

```python
LAST_CONFIG_ERROR = None          # module-global, the LAST_SPOOLMAN_ERROR analogue
_CONFIG_WRITE_LOCK = threading.Lock()   # config writes are rare/admin-only

def load_config_raw() -> dict:
    """Read config.json fresh from get_config_path()[0]. NO defaults merge,
    NO printer_map uppercasing. The save/merge source of truth. {} if absent."""

def save_config(new_values: dict) -> dict:
    """Returns {"ok": bool, "error": str|None, "restart_required": bool}. NEVER None."""
```

Algorithm (inside `_CONFIG_WRITE_LOCK`):

1. **Validate first, write never on failure.** Coerce + validate every schema-owned `server`-scope key in `new_values`. Collect per-key errors; if any, set `LAST_CONFIG_ERROR`, return `{ok: False, error: ...}` — **no disk touch**.
2. **Read raw.** `existing = load_config_raw()`. Build `merged = {**existing}`; overwrite *only* validated schema-owned keys. Every other on-disk key is left byte-untouched (passthrough law).
3. **printer_map round-trip safety** (when its editor lands in Phase 3, not v1): uppercase keys once, reject two keys differing only by case (`XL-1` vs `xl-1`) with an explicit error, write the uppercased canonical form. Documented in *both* `load_config` and `save_config`: **"uppercase is the canonical persisted form for printer_map."** Since load already uppercases, writing-uppercase is idempotent. In v1 `printer_map` is `readonly` so this path is dormant.
4. **Atomic write — copied (not extracted) from `locations_db`.** New private `_write_config_atomic(merged)`: per-call `tempfile.NamedTemporaryFile(dir=parent, prefix='config.', suffix='.tmp', delete=False)` → `json.dump(indent=4)` → `flush` → `os.fsync` → `os.replace` onto `get_config_path()[0]`; unlink temp on failure. Writes the *env-correct* file (DEV→`config.dev.json`, PROD→`config.json`) — never cross-write.
5. **Verify-after-write — STRONGER than the precedent.** `_verify_config_file(merged)` re-reads + `json.loads` and asserts `parsed == merged` (exact dict equality — cheap because config is one dict, catches uppercase-drift and silent-truncation that `isinstance(list)` misses). On mismatch: log critical, **retry once**, re-verify.
6. **Explicit failure — stricter than `save_locations_list`.** If the retry still fails, set `LAST_CONFIG_ERROR` and return `{ok: False, error: ...}`. We do NOT inherit the locations writer's silent return-after-failed-retry. First write also drops a `config.json.bak` of the pre-write raw file (one-time safety net for the first-ever write surface).
7. **No cache to bust.** `load_config()` is called per-request (~40 sites, no in-process cache) so the next request sees fresh values. The one `_startup_cfg` snapshot (app.py:142) is only the legacy feeder_map migration — safe.

**Endpoints** (`app.py`):

- `GET /api/config` → `{schema, sections, values}`. `values` are the merged-with-defaults server values; **secrets masked** to `"__secret_set__"` (or `""` if unset) — plaintext never serialized. Enforced in one place (`schema_as_json`), guarded by a test.
- `PUT /api/config` → validate → `save_config` → on `ok:False` put `error` in the JSON response (renderer `showToast(err,"error",7000)`) **and** write an activity-log ERROR entry (`state.add_log_entry(..., "ERROR", "ff4444")`); on success write a success log entry.

This lands `save_config` on the official write-surface inventory in CLAUDE.md.

## UI & rendering

New module `inventory-hub/static/js/modules/inv_settings.js` owns *only* the generated Settings cards; the existing `inv_config.js` action-tool IIFE is left alone except one line.

- `modals_config.html`: insert `<div id="config-generated-settings"></div>` **above** the four existing static action cards inside `#config-sections`. Same dark chrome.
- On modal open, `inv_config.js:openConfigModal()` adds one call: `window.renderSettings()`. That's the only edit to that file; all action-tool wiring is untouched.
- `inv_settings.js`: fetch `GET /api/config`, then build one `.card.bg-black.border-secondary.mb-3` per section (visually consistent with the action cards), one labeled form-row per field. A `WIDGETS` table maps `type → {build(field,value), read(el)}`. The renderer has **zero knowledge of any specific key** — add a `Field` and it appears.
- **Save model:** one sticky-footer "Save changes" button, dirty-tracked (disabled until a field changes; per-field reset arrow on dirty rows). Client-side min/max/enum checks for instant feedback; **server is authoritative**, server messages surfaced verbatim.
- **Secret fields** render masked (`••••`) with a reveal eye; PUT sends the secret only if the user actually retyped it.
- `server_ip`/ports render normally (they hot-apply since `get_api_urls()` re-reads live). `printer_map` renders **read-only** in v1 with a "dedicated editor coming soon" note.
- **Dark-contrast convention:** no white-on-white; `bg-dark text-white border-secondary` inputs, verified visually.

**Action-tool coexistence — zero coupling.** The four cards (Reconcile, Filament Attributes, Restore Field Order, Build Info) stay bespoke, hand-wired by the `inv_config.js` IIFE *exactly as today* — they are one-shot OPERATIONS, explicitly NOT forced into the settings schema. Generated Settings render in their own div above the static cards; neither module imports the other. The settings-vs-action boundary is named and documented but not refactored in v1.

**Overlays:** every confirm (import dry-run, future destructive edits) routes through `window.mountOverlay()` (`tier:'standard'`, `occlude:['select']`), never `Swal`, never manual `appendChild`/`focusin` — per project convention.

## Import / export

Phase 4. Both replay through the *same* validated `save_config` path, so import inherits identical atomic-write + verify + passthrough guarantees — no new write machinery.

- **Export:** `GET /api/config/export` → downloads `fcc-config-<date>.json` = `{"_fcc_config_export": 1, "version": 1, "values": {<schema-known server values>}, "client": {<client-scope values browser supplies>}}`. **Secrets excluded** unless `?include_secrets=1`. Section-scoped export (`?sections=connection,printers`) grafted from the Hierarchical approach to clone a subset into a sibling install.
- **Import:** a button opens a `mountOverlay` file-picker + **DIFF PREVIEW** mirroring the L318 Restore-Field-Order dry-run Derek liked: parse → validate every value against the schema → table of `key | current → incoming | status (ok / invalid / unknown-key)`. Unknown keys are **skipped with a warning** (passthrough — not written, not destructive). Only on Confirm does it PUT the validated subset through `save_config`. Client-scope values write to localStorage after the server PUT succeeds, with **per-scope result reporting** (a localStorage write throwing must not show an all-green toast).

## localStorage migration

`fcc.weighEntry.defaultMode` becomes a first-class `Field(scope="client", type="enum", choices=["gross","net","additive","set_used"])`. **This is a declaration move, not a data move:**

- The value STAYS in localStorage under the unchanged key `fcc.weighEntry.defaultMode`. `weight_entry.js` needs **no change** — it keeps reading `DEFAULT_MODE_KEY` exactly as today (zero behavioral risk to the weigh-entry overlay).
- The renderer branches on `scope`: `client` fields read/write localStorage directly using the field key verbatim; `server` fields go through PUT. Both are discoverable and editable in one UI and both ride along in export/import.
- **General pattern for future client prefs** (e.g. printer-status order/collapse keys, label-queue): register one `scope:"client"` Field pointing at the existing localStorage key — done. A small `CLIENT_PREF_KEYS` export lets a one-time tidy-up validate stale values against declared `choices` on load.

## Phased build plan

### Phase 1 — Safe Writer + 2 scalar settings (MVP, ~1 day) — SHIPPABLE
The single dangerous primitive, proven before any framework rides on it.

- `config_schema.py` (NEW): `Field`/`Section` dataclasses, `CONFIG_SCHEMA` seeded with **only** `sync_delay` + `auto_recover_filabridge_errors` (server, low-stakes) + the client `fcc.weighEntry.defaultMode`; `coerce_and_validate`, `validate_payload`.
- `config_loader.py`: `load_config_raw()`, `_write_config_atomic()` (copied from locations_db), `_verify_config_file()` (exact-equality), `save_config()` (lock, validate-first, passthrough-merge, retry-once, `LAST_CONFIG_ERROR`, returns `{ok,error,...}`, first-write `.bak`).
- `app.py`: `GET /api/config`, `PUT /api/config` (surface error + activity log).
- `inv_settings.js` (NEW, minimal): fetch, render bool/float/enum via a small `WIDGETS` switch into `#config-generated-settings`, dirty-track, Save, toast.
- `modals_config.html`: add `#config-generated-settings` div.
- `inv_config.js`: one line — call `window.renderSettings()` in `openConfigModal()`.

**Acceptance criteria:**
1. Toggling `auto_recover_filabridge_errors` off + Save persists to the env-correct file; reload shows off; the four action cards still work.
2. `load_config_raw()` does NOT inject defaults or uppercase printer_map (unit test).
3. A `load → save → load` round-trip leaves the on-disk file's schema-unknown keys (incl. `printer_map`, `dryer_slots`, any `comment*`) **byte-identical** (unit test).
4. A bad value (`sync_delay = "abc"`) returns `{ok:False, error:...}`, touches no disk, toasts at 7s, writes an ERROR activity-log entry.
5. Editing the client weigh-mode writes localStorage; `weight_entry.js` reads it unchanged.
6. `git`/visual: no white-on-white in the new card.

### Phase 2 — Full generic renderer + schema-derived defaults (~1 day)
- Expand `WIDGETS` to all scalar types + secret (masked, `__secret_set__`, never plaintext on GET; masking test).
- Add `server_ip`/ports + `SCRAPER_API_KEY` to the schema (ports read-only-optional, secret masked).
- `config_loader.load_config()`: derive its defaults dict FROM `config_schema` so defaults live in one place (behavior-preserving; existing tests stay green).
- Per-field reset arrows, sticky footer polish.

### Phase 3 — printer_map editor (the high-risk write, isolated)
- Bespoke `printer_map` widget (name/printer/position repeater) in `inv_settings.js`.
- `save_config` printer_map branch: uppercase canonicalization + case-collision reject; `load(save(x)) == load(x)` + byte-identity tests. Flip the Field off `readonly`.

### Phase 4 — Import / export
- `GET /api/config/export` (+ `?sections=` + `?include_secrets=`), `POST /api/config/import`, `mountOverlay` dry-run diff table, per-scope result reporting.

### Phase 5 (optional) — Action-tool co-location
- Refactor `configReconcileScan`/`configAttrsScan`/`configRestoreFieldOrder` to mount into a passed host element; a `TOOLS` registry keys each to a section so the "clunky attributes" manager sits beside its prefs. No logic change to the tool endpoints.

## Files & functions to touch

| File | Change |
|---|---|
| `inventory-hub/config_schema.py` | **NEW** — `Field`/`Section` dataclasses, `CONFIG_SCHEMA`, `SECTIONS`, `coerce_and_validate`, `validate_payload`, `schema_as_json` (secret masking enforced here), `CLIENT_PREF_KEYS`, `SECRET_KEYS` |
| `inventory-hub/config_loader.py` | **ADD** `load_config_raw()`, `_write_config_atomic()` (copied from locations_db), `_verify_config_file()` (exact-equality), `save_config()` (lock + validate-first + passthrough-merge + retry + `LAST_CONFIG_ERROR` + `.bak`), `_CONFIG_WRITE_LOCK`; Phase 2: derive `load_config()` defaults from schema |
| `inventory-hub/app.py` | **NEW routes** `GET /api/config`, `PUT /api/config`; Phase 4 `GET /api/config/export`, `POST /api/config/import` |
| `inventory-hub/static/js/modules/inv_settings.js` | **NEW** — `renderSettings()`, `WIDGETS` table, dirty-tracking, Save, client-scope localStorage branch, error toast; Phase 4 import/export overlay; Phase 3 printer_map widget |
| `inventory-hub/static/js/modules/inv_config.js` | **One line** — call `window.renderSettings()` in `openConfigModal()` (action wiring untouched) |
| `inventory-hub/templates/components/modals_config.html` | Insert `<div id="config-generated-settings"></div>` above the static action cards |
| `inventory-hub/static/js/modules/weight_entry.js` | **NO change** (keeps its localStorage key) |
| `inventory-hub/tests/test_config_*.py` | **NEW** — atomic round-trip, byte-identity passthrough, validation-rejection, secret-masking, (Phase 3) printer_map case-collision |
| `CLAUDE.md` | Add `save_config` to the write-surface inventory table |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| **First-ever config WRITE on a previously read-only file; a bug bricks `server_ip`/ports → operator locked out of Spoolman.** | Copy the proven locations_db atomic+verify+retry verbatim; exact-equality verify; one-time `config.json.bak` on first write; `server_ip`/ports out of the v1 editable set (Phase 1 ships only `sync_delay`/`auto_recover`). |
| **printer_map uppercase round-trip drift / case-variant dup keys.** | `printer_map` is `readonly` in v1 (write path dormant). When enabled (Phase 3): canonical-uppercase rule documented in both load and save, case-collision reject, `load(save(x))==load(x)` + byte-identity tests. |
| **Silent loss of on-disk keys** (`dryer_slots`, `SCRAPER_API_KEY`, paths, `print_settings`, `comment*`) — the Hierarchical fatal flaw. | Passthrough law: merge only schema-owned keys onto a raw read; byte-identity test pins it. |
| **Secret leak via GET/export** (`SCRAPER_API_KEY` is live plaintext on prod). | `SECRET_KEYS` allowlist enforced in one place (`schema_as_json`); `__secret_set__` sentinel never returns plaintext; excluded from export unless `?include_secrets=1`; masking unit test. |
| **Concurrency: two PUTs interleave read-merge-write.** | `threading.Lock` around `save_config` (config writes are rare/admin-only; contention negligible). `os.replace` atomicity for the swap. |
| **Touching `load_config()` defaults (Phase 2).** | Behavior-preserving derivation only; existing tests must stay green; no migration/normalize logic ever on the read path. |
| **Reading the wrong env file.** | Always derive from `get_config_path()[0]`; test asserts DEV env writes `config.dev.json`. |
| **Validation divergence client vs server.** | Server authoritative, client advisory; server error messages surfaced verbatim. |

## Open questions for Derek

1. **`server_ip` / ports — editable from the UI, or read-only-display in v1?** They hot-apply (`get_api_urls()` re-reads live), so editing is technically safe, but a typo'd IP self-locks-out of Spoolman with no UI to recover until you fix the file. Recommendation: read-only in Phase 1, editable in Phase 2 once the writer has earned trust. Your call on the appetite.
2. **`printer_map` editor priority.** Confirmed deferred to Phase 3 behind its own tests. Is a UI editor for it actually wanted, or is editing the file + restart acceptable indefinitely? (Affects whether Phase 3 ever happens.)
3. **What lives on the *prod* `config.json` that's not in the dev `load_config()` defaults?** This checkout has no `config.json`/`.example` (gitignored, absent in dev tree). The judges cite `SCRAPER_API_KEY`, `spoolman_db_path`, `backup_directory`, `export_directory`, `print_settings`, and `comment*` keys on the prod file. Please confirm the real prod key list so the passthrough byte-identity test seeds from reality, and so we know which (if any) deserve to be promoted to first-class `Field`s vs. left as passthrough.
4. **Section taxonomy / labels.** Proposed: Connection / Behavior / Printers / This-Browser. Want different groupings or names before the schema hard-codes section order?
5. **Import overwrite semantics.** On import, should an incoming file *replace* the full server set (missing keys reset to default) or *patch* only the keys present in the file? Recommendation: patch-only (safer, matches passthrough philosophy) — confirm.

---

## Implemented (Phases 1–2, with adversarial review)

**Phase 1** (`a40f6b3`, +E2E `bcc412a`): safe writer (`save_config`: passthrough merge + atomic temp-file write + exact-equality verify-after-write + retry-once + rolling `.bak` + refuse-on-unreadable + `LAST_CONFIG_ERROR`), `load_config_raw()`, `GET`/`PUT /api/config`, schema-driven `inv_settings.js` Settings card. Reviewed (21 agents) → fixed 2 data-safety bugs (sparse-config wipe on unreadable file; NaN-to-disk).

**Phase 2** (`9d3fc2f` + hardening): connection settings **editable** (Q1 answered: editable in P2) — `server_ip`, ports, and a **masked/updatable `SCRAPER_API_KEY`** (`SECRET_SENTINEL` round-trip; plaintext never sent to the browser — review-confirmed no-leak). New field types `ip`/`port`/`secret`. Reviewed (18 agents) → verdict sound; fixed port-`Infinity`→500 + a sentinel-collision nit.

**Multi-host decoupling (Derek, 2026-05-31):** Spoolman and FilaBridge are NOT assumed to share a host. Added an **optional `filabridge_ip`** (blank ⇒ falls back to `server_ip`); `get_api_urls()` derives the FilaBridge host independently. Backward-compatible — existing single-host configs behave identically. Supersedes the single-`server_ip` assumption latent in `get_api_urls` pre-L18.

**Open-question status:** Q1 ✅ (editable in P2). Q3 ✅ (real keys confirmed: `SCRAPER_API_KEY`, `spoolman_db_path`, `backup_directory`, `export_directory`, `print_settings`, `printer_map`, `dryer_slots`, `comment*` — all preserved by passthrough). Q2 (`printer_map` editor) deferred → Phase 3. Q5 (import/export) deferred → Phase 4. Q4 current taxonomy: Connection / Behavior / This-Browser.