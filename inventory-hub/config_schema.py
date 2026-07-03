"""L18 Config System — declarative schema (Phase 1).

A single source of truth describing user-editable settings: key, label, type,
default, section, scope, and validation. The frontend renders the settings UI
from this schema and GET/PUT /api/config validate against the same definitions,
so adding the Nth setting later is a one-line `Field` edit — not UI + backend +
persistence triplicate work.

Phase 2 adds the connection settings (server_ip, filabridge_ip, ports) and a
masked SCRAPER_API_KEY secret. printer_map / dryer_slots remain NOT editable
(preserved untouched by save_config's passthrough merge). See
docs/agent_docs/tasks/L18-config-system-design.md for the phased plan.

`scope`:
  - "server"  -> persisted into the active config.json by save_config().
  - "client"  -> persisted in the browser's localStorage by the renderer; the
                 key is registered here only so it shows up in the same UI.
                 (e.g. fcc.weighEntry.defaultMode, read by weight_entry.js.)
"""
import math
import re
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    help: str = ""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str                       # 'bool' | 'int' | 'float' | 'string' | 'select'
    default: Any
    section: str
    scope: str = "server"           # 'server' | 'client'
    help: str = ""
    choices: Optional[List[str]] = None   # required for type='select'
    min: Optional[float] = None
    max: Optional[float] = None
    optional: bool = False                 # type='ip': blank allowed (falls back elsewhere)


# Sentinel returned by GET /api/config for secret fields, and accepted by PUT to
# mean "leave the stored secret unchanged". The plaintext secret is NEVER sent to
# the browser; a real new value replaces it.
SECRET_SENTINEL = "__secret_set__"

# Lenient IPv4 / hostname charset check (rejects spaces and junk).
_IP_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")

SECTIONS = [
    Section("connection", "🔌 Connection",
            "Spoolman / FilaBridge endpoints. Changes apply immediately — a wrong "
            "value drops the connection until you fix it back here."),
    Section("behavior", "⚙️ Behavior"),
    Section("client", "🖥️ This Browser", "Stored per-device in this browser, not synced."),
]

CONFIG_SCHEMA = [
    # Connection — defaults MUST mirror config_loader.load_config()'s defaults.
    Field("server_ip", "Spoolman host / IP", "ip", "127.0.0.1",
          section="connection", scope="server",
          help="Host running Spoolman (and FilaBridge too, unless overridden below)."),
    Field("spoolman_port", "Spoolman port", "port", 7912,
          section="connection", scope="server", min=1, max=65535),
    Field("filabridge_ip", "FilaBridge host / IP", "ip", "",
          section="connection", scope="server", optional=True,
          help="Leave blank if FilaBridge runs on the same host as Spoolman."),
    Field("filabridge_port", "FilaBridge port", "port", 5000,
          section="connection", scope="server", min=1, max=65535),
    Field("SCRAPER_API_KEY", "Scraper API key", "secret", "",
          section="connection", scope="server",
          help="Stored server-side; never sent to the browser. Leave blank to keep the current value."),
    Field("sync_delay", "Sync delay (seconds)", "float", 0.5,
          section="behavior", scope="server", min=0, max=10,
          help="Pause between Spoolman sync operations."),
    Field("auto_recover_filabridge_errors", "Auto-recover FilaBridge errors", "bool", True,
          section="behavior", scope="server",
          help="Automatically retry FilaBridge writes that failed."),
    Field("fcc_owns_completion_deduct", "FCC owns completed-print deduct", "bool", False,
          section="behavior", scope="server",
          help="Phase-2 cutover: when ON, FCC deducts filament on FINISHED prints "
               "(the slicer footer, same as FilaBridge billed). Turn this ON the "
               "SAME moment you stop the FilaBridge container — otherwise completed "
               "prints double-deduct (FilaBridge + FCC)."),
    Field("path_filament_g", "Runout path filament (g)", "float", 0,
          section="behavior", scope="server", min=0, max=50,
          help="Grams of filament between the runout SENSOR and the nozzle that you pull "
               "out (never printed) when swapping a run-out spool. On a mid-print runout, "
               "FCC adds this to the RUN-OUT spool's automatic deduct so its weight lands "
               "at the now-empty spool; the replacement spool is never affected, and a "
               "deliberate (non-runout) swap doesn't add it. 0 = off — the run-out spool "
               "just reads a couple grams heavy until you zero it (usually fine, it's "
               "empty). Typical: ~2 g short-path (Core One), ~4 g longer-path (XL). One "
               "value covers all printers for now; a per-printer version is planned."),
    Field("fcc.weighEntry.defaultMode", "Default weigh-in mode", "select", "additive",
          section="client", scope="client",
          choices=["gross", "net", "additive", "set_used"],
          help="Which input mode the weight-entry overlay opens in."),
]

# Derived lookups
_BY_KEY = {f.key: f for f in CONFIG_SCHEMA}
SERVER_FIELDS = [f for f in CONFIG_SCHEMA if f.scope == "server"]
SERVER_KEYS = frozenset(f.key for f in SERVER_FIELDS)
SECRET_KEYS = frozenset(f.key for f in CONFIG_SCHEMA if f.type == "secret")


class ConfigValidationError(ValueError):
    """Raised when a submitted value fails schema validation."""


def get_field(key):
    return _BY_KEY.get(key)


def coerce_and_validate(key, value):
    """Coerce a raw submitted value to its field's type and validate
    choices/range. Returns the coerced value. Raises ConfigValidationError
    on unknown key or bad input."""
    f = _BY_KEY.get(key)
    if f is None:
        raise ConfigValidationError(f"Unknown config key: {key}")
    t = f.type
    try:
        if t == "bool":
            if isinstance(value, bool):
                coerced = value
            elif isinstance(value, str):
                coerced = value.strip().lower() in ("true", "1", "yes", "on")
            else:
                coerced = bool(value)
        elif t in ("int", "port"):
            # Reject booleans explicitly — int(True)==1 would otherwise let a
            # JSON bool through as port 1. int(3.9)->3 truncation still applies.
            if isinstance(value, bool):
                raise ConfigValidationError(f"{f.label}: expected a number, not a boolean")
            coerced = int(value)
        elif t == "float":
            coerced = float(value)
        elif t == "select":
            coerced = str(value)
            if f.choices is not None and coerced not in f.choices:
                raise ConfigValidationError(
                    f"{f.label}: '{coerced}' is not one of {f.choices}")
        elif t == "ip":
            coerced = str(value).strip()
            if not coerced:
                if f.optional:
                    coerced = ""  # blank allowed (e.g. filabridge_ip -> falls back to server_ip)
                else:
                    raise ConfigValidationError(f"{f.label}: required")
            elif not _IP_HOST_RE.match(coerced):
                raise ConfigValidationError(f"{f.label}: '{value}' is not a valid IP / hostname")
        else:  # string, secret
            coerced = str(value)
    except ConfigValidationError:
        raise
    except (TypeError, ValueError, OverflowError):
        # OverflowError: e.g. int(float('inf')) for a port from a crafted JSON
        # body — normalize to a clean validation error (400) instead of a 500.
        raise ConfigValidationError(f"{f.label}: '{value}' is not a valid {t}")

    if t in ("int", "float", "port"):
        # Reject NaN/inf BEFORE the range checks: NaN compares False against
        # BOTH bounds, so it would otherwise slip through and json.dump would
        # write the invalid bare token `NaN`/`Infinity` into config.json.
        if isinstance(coerced, float) and not math.isfinite(coerced):
            raise ConfigValidationError(f"{f.label}: '{value}' is not a finite number")
        if f.min is not None and coerced < f.min:
            raise ConfigValidationError(f"{f.label}: must be ≥ {f.min}")
        if f.max is not None and coerced > f.max:
            raise ConfigValidationError(f"{f.label}: must be ≤ {f.max}")
    return coerced


def validate_payload(values):
    """Validate + coerce a {key: value} dict for SERVER-scope fields only.
    Returns (coerced_dict, errors_list). Client-scope keys are ignored
    (they're persisted in the browser, never written to config.json).
    Unknown keys are reported as errors."""
    coerced = {}
    errors = []
    if not isinstance(values, dict):
        values = {}
    for key, value in values.items():
        f = _BY_KEY.get(key)
        if f is None:
            errors.append(f"Unknown config key: {key}")
            continue
        if f.scope != "server":
            continue
        # A secret submitted as the sentinel means "leave unchanged" — skip it so
        # save_config's passthrough preserves the existing stored secret (the
        # plaintext is never sent to the browser, so this is how it round-trips).
        if f.type == "secret" and value == SECRET_SENTINEL:
            continue
        try:
            coerced[key] = coerce_and_validate(key, value)
        except ConfigValidationError as e:
            errors.append(str(e))
    return coerced, errors


def schema_for_ui():
    """Serialize the schema + sections for the frontend renderer."""
    return {
        "sections": [
            {"key": s.key, "label": s.label, "help": s.help} for s in SECTIONS
        ],
        "fields": [
            {
                "key": f.key, "label": f.label, "type": f.type, "default": f.default,
                "section": f.section, "scope": f.scope, "help": f.help,
                "choices": f.choices, "min": f.min, "max": f.max,
                "optional": f.optional,
            }
            for f in CONFIG_SCHEMA
        ],
    }
