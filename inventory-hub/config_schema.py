"""L18 Config System — declarative schema (Phase 1).

A single source of truth describing user-editable settings: key, label, type,
default, section, scope, and validation. The frontend renders the settings UI
from this schema and GET/PUT /api/config validate against the same definitions,
so adding the Nth setting later is a one-line `Field` edit — not UI + backend +
persistence triplicate work.

Phase 1 deliberately seeds only LOW-STAKES settings (sync_delay,
auto_recover_filabridge_errors, and the client-side weigh-entry default mode).
server_ip / ports / printer_map are intentionally NOT editable yet — they are
preserved untouched by save_config's passthrough merge. See
docs/agent_docs/tasks/L18-config-system-design.md for the phased plan.

`scope`:
  - "server"  -> persisted into the active config.json by save_config().
  - "client"  -> persisted in the browser's localStorage by the renderer; the
                 key is registered here only so it shows up in the same UI.
                 (e.g. fcc.weighEntry.defaultMode, read by weight_entry.js.)
"""
import math
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


SECTIONS = [
    Section("behavior", "⚙️ Behavior"),
    Section("client", "🖥️ This Browser", "Stored per-device in this browser, not synced."),
]

CONFIG_SCHEMA = [
    Field("sync_delay", "Sync delay (seconds)", "float", 0.5,
          section="behavior", scope="server", min=0, max=10,
          help="Pause between Spoolman sync operations."),
    Field("auto_recover_filabridge_errors", "Auto-recover FilaBridge errors", "bool", True,
          section="behavior", scope="server",
          help="Automatically retry FilaBridge writes that failed."),
    Field("fcc.weighEntry.defaultMode", "Default weigh-in mode", "select", "additive",
          section="client", scope="client",
          choices=["gross", "net", "additive", "set_used"],
          help="Which input mode the weight-entry overlay opens in."),
]

# Derived lookups
_BY_KEY = {f.key: f for f in CONFIG_SCHEMA}
SERVER_FIELDS = [f for f in CONFIG_SCHEMA if f.scope == "server"]
SERVER_KEYS = frozenset(f.key for f in SERVER_FIELDS)


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
        elif t == "int":
            # NOTE: no int Field ships in Phase 1. When one is added, decide the
            # contract explicitly — int(3.9)->3 and int(True)->1 coerce silently
            # today; reject non-integral / bool input here if that's unwanted.
            coerced = int(value)
        elif t == "float":
            coerced = float(value)
        elif t == "select":
            coerced = str(value)
            if f.choices is not None and coerced not in f.choices:
                raise ConfigValidationError(
                    f"{f.label}: '{coerced}' is not one of {f.choices}")
        else:  # string
            coerced = str(value)
    except ConfigValidationError:
        raise
    except (TypeError, ValueError):
        raise ConfigValidationError(f"{f.label}: '{value}' is not a valid {t}")

    if t in ("int", "float"):
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
            }
            for f in CONFIG_SCHEMA
        ],
    }
