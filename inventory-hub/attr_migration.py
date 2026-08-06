"""Safety layer around the destructive `filament_attributes` schema migration.

Spoolman (0.23.1) cannot shrink a `choice` field's option list in place —
`add_or_update_extra_field` raises "Cannot remove existing choices". Removing a
single choice therefore forces a DELETE + recreate of the whole field, and
because the DELETE drops every record's row for that key, every
attribute-bearing filament then has to be PATCHed back. Three call sites do it:

  * `routes_config_attrs.api_filament_attributes_remove_choice`
  * `routes_config_attrs.api_filament_attributes_sweep_unused`
  * `spoolman_api.ensure_filament_attributes_cleaned`   (runs at BOOT)

Each one used to own a private copy of the restore loop: no retry, no durable
record of what it was about to write, and a snapshot that lived only in the
request handler's memory. That combination drained 26 of Derek's filaments over
months before anyone noticed. This module owns the shared primitives so the
three sites can no longer drift apart:

  * `write_recovery_snapshot` / `clear_recovery_snapshot` /
    `pending_recovery_snapshots` — the exact payload hits `data/` BEFORE the
    DELETE. A crash between the DELETE and the last restore used to be
    unbounded, untraced loss; in DEV that is a routine event, because editing
    any `.py` restarts the container mid-flight via `use_reloader`.
  * `restore_extras` — the restore loop, with a bounded transport retry and a
    verify-by-re-read before anything is declared lost.
  * the hidden-choice list — the mechanism that lets the common case avoid the
    destructive migration entirely (see `routes_config_attrs`' remove_choice).

BLAST RADIUS, settled at source for the deployed build (v0.23.1 / eafbc64):
Spoolman does not store `extra` as a JSON sub-document. It is a child table
`filament_field` with composite primary key `(filament_id, key)`, and the field
DELETE is `DELETE FROM filament_field WHERE key = ?`. So a failed restore loses
EXACTLY `filament_attributes` on that record — siblings (`product_url`,
`original_color`, `slicer_profile`, ...) are structurally untouchable by it.
The sibling losses still visible in dev came from a DIFFERENT bug that is
already fixed: the pre-2026-05-19 draft that PATCHed a PARTIAL extras dict and
so tripped Spoolman's replace-the-whole-sub-document PATCH semantics. See
`spoolman_api.ensure_filament_attributes_cleaned`'s comment for that history.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import json
import os
import tempfile
import time

import atomic_store  # type: ignore
import http_retry  # type: ignore
import state  # type: ignore

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_HIDDEN_PATH = os.path.join(_DATA_DIR, "attr_hidden_choices.json")

# Recovery snapshots are `data/attr_recovery_<stamp>.json`. The prefix is what
# `pending_recovery_snapshots` globs for, so keep the two in sync.
_RECOVERY_PREFIX = "attr_recovery_"


# --------------------------------------------------------------------------
# Atomic JSON write
# --------------------------------------------------------------------------

def _write_json_atomic(path, obj):
    """Write `obj` as JSON to `path` atomically (temp + fsync + replace).

    Mirrors the hardened `locations_db` recipe rather than the ledger one: a
    UNIQUE temp name (Flask is multi-threaded, and two writers sharing one
    fixed `.tmp` would corrupt each other) plus an explicit `fsync` before the
    swap, so a container kill can't leave a half-written recovery artifact —
    which would defeat the entire point of writing it.

    `data/` is a DIRECTORY bind-mount, so `os.replace` works here (this is NOT
    the `config.json` single-file-mount EBUSY case). `replace_with_retry`
    still earns its keep for the Windows host<->container sharing collision.
    """
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent, prefix=os.path.basename(path) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        atomic_store.replace_with_retry(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return default


# --------------------------------------------------------------------------
# Pre-migration recovery snapshot
# --------------------------------------------------------------------------

def write_recovery_snapshot(op, payloads):
    """Persist the exact restore payloads BEFORE the destructive DELETE.

    `payloads` maps filament id -> the full extras dict that will be written
    back. Returns the path written, or None if the write failed (a snapshot
    failure must never abort the caller — it is a safety net, not a gate;
    the caller logs and proceeds).

    Deliberately NOT the pre-filter snapshot: what is stored is what the
    restore will actually send, so replaying the file by hand cannot
    re-introduce the choice the user just removed.
    """
    if not payloads:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_DATA_DIR, "%s%s.json" % (_RECOVERY_PREFIX, stamp))
    body = {
        "op": str(op),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(payloads),
        # JSON object keys are strings; `load_recovery_snapshot` coerces back.
        "payloads": {str(k): v for k, v in payloads.items()},
    }
    try:
        _write_json_atomic(path, body)
        return path
    except Exception as e:  # pragma: no cover - disk failure
        state.logger.error(
            "attr_migration: could NOT write the pre-migration recovery "
            "snapshot for %s (%s). Proceeding WITHOUT a safety net." % (op, e)
        )
        return None


def clear_recovery_snapshot(path):
    """Delete a recovery snapshot once its migration fully succeeded."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def pending_recovery_snapshots():
    """Every recovery snapshot still on disk = a migration that did not finish.

    Returns a list of {path, op, created, count}, newest last. A file survives
    only when its migration failed or died partway, so a non-empty result is
    an unresolved-data-loss signal, not routine debris.
    """
    out = []
    try:
        names = sorted(os.listdir(_DATA_DIR))
    except OSError:
        return out
    for name in names:
        if not (name.startswith(_RECOVERY_PREFIX) and name.endswith(".json")):
            continue
        path = os.path.join(_DATA_DIR, name)
        body = _read_json(path, None)
        if not isinstance(body, dict):
            continue
        out.append({
            "path": path,
            "op": body.get("op") or "?",
            "created": body.get("created") or "?",
            "count": body.get("count") or len(body.get("payloads") or {}),
        })
    return out


def surface_pending_recovery_snapshots():
    """Announce unfinished migrations at boot. Called from startup_migrations.

    Deliberately does NOT auto-replay. A snapshot can be arbitrarily stale, and
    the restore PATCH writes the record's WHOLE extras dict — so a blind replay
    would silently revert every edit made to those filaments since the crash
    (a lost update on every extra key, not just the attribute). Surfacing it
    loudly and letting a human decide is the honest behavior; the file itself
    is the recovery data.
    """
    pending = pending_recovery_snapshots()
    for snap in pending:
        state.logger.error(
            "UNFINISHED filament-attribute migration: %s (%s) left %d record(s) "
            "unrestored. The exact restore payload is on disk at %s — replay it "
            "or diff it against Spoolman before deleting it."
            % (snap["op"], snap["created"], snap["count"], snap["path"])
        )
        state.add_log_entry(
            "⚠️ An earlier Filament Attributes migration (%s) did not finish — "
            "%d filament(s) may still be missing their attributes. Recovery data: %s"
            % (snap["op"], snap["count"], os.path.basename(snap["path"])),
            "ERROR", "ff4444",
        )
    return pending


# --------------------------------------------------------------------------
# The restore loop
# --------------------------------------------------------------------------

def _extras_match(sm_url, fid, expected):
    """Did the record end up with `expected` extras after all?

    A ReadTimeout does NOT mean the PATCH was rejected — it may well have been
    accepted and applied, with only the response lost. The restore payload is a
    fixed, pre-computed snapshot, so it is fully idempotent and this re-read is
    safe. Without it we report data loss that did not happen, and (worse) an
    operator "recovers" by replaying stale extras over a record that was fine.
    """
    try:
        r = http_retry.request_with_retry(
            "get", "%s/api/v1/filament/%s" % (sm_url, fid),
            timeout=10, attempts=2,
        )
        if not r.ok:
            return False
        live = (r.json() or {}).get("extra") or {}
    except Exception:
        return False
    return live == expected


def restore_extras(sm_url, payloads, *, timeout=15, attempts=None, verify=True):
    """PATCH each filament's FULL extras dict back after a schema rebuild.

    `payloads` maps filament id -> the exact extras dict to write (already
    filtered — see `write_recovery_snapshot`). Returns
    `(restored, failures, recovered)`:

      restored  int  — records confirmed written (including verify-recovered)
      failures  list — [{"id", "msg"}], the shape both endpoints already return
      recovered int  — of `restored`, how many only passed on the re-read

    Sending the WHOLE extras dict is what preserves siblings: Spoolman's PATCH
    replaces the entire `extra` sub-document, so a partial payload wipes them
    (CLAUDE.md "Spool / Filament write surfaces"). The values in `payloads`
    came straight off the wire already JSON-string-encoded, which is why this
    deliberately does NOT route through `spoolman_api.update_filament` — that
    would double-encode them.
    """
    restored, recovered, failures = 0, 0, []
    for fid, extras_out in payloads.items():
        msg = None
        try:
            # noqa: spoolman-extra-patch — `extras_out` is the FULL extras
            # snapshot, not a partial dict, so Spoolman's replace-on-PATCH
            # semantics preserve every sibling. test_no_direct_extra_patch
            # honors this marker as an audited exception.
            pr = http_retry.request_with_retry(  # noqa: spoolman-extra-patch
                "patch", "%s/api/v1/filament/%s" % (sm_url, fid),
                json={"extra": extras_out}, timeout=timeout, attempts=attempts,
            )
            if pr.ok:
                restored += 1
                continue
            msg = "HTTP %s: %s" % (pr.status_code, (pr.text or "")[:120])
        except Exception as e:
            # Any exception AFTER the schema was deleted + recreated must stay
            # visible in `failures` rather than escaping as an opaque 500 over
            # a half-migrated schema (the 29.A4 broadening, kept).
            msg = str(e)[:200]

        if verify and _extras_match(sm_url, fid, extras_out):
            restored += 1
            recovered += 1
            state.logger.warning(
                "attr_migration: filament #%s restore reported a failure (%s) but "
                "the record already holds the expected extras — treating as "
                "restored." % (fid, msg)
            )
            continue
        failures.append({"id": fid, "msg": msg})
    return restored, failures, recovered


def report_restore_failures(op, restore_failures, payloads):
    """Make a partial schema migration RECOVERABLE by hand.

    All three force_reset sites share this. A restore that fails leaves that
    filament without its `filament_attributes` — the field's rows were already
    dropped by the DELETE.

    Scope of the loss, settled at source (Spoolman v0.23.1 / eafbc64): `extra`
    is the child table `filament_field` keyed `(filament_id, key)`, and the
    field DELETE is `DELETE ... WHERE key = ?`. So exactly ONE key is lost, not
    the record's whole `extra`. Saying otherwise (as this message used to) sends
    a recovery operator to over-restore from a possibly-stale snapshot.

    Until 2026-08-05 the only trace was a COUNT ("restored 151/152 ... 1
    failure"). The filament id was never written anywhere, so the loss was both
    silent and unattributable, and 26 filaments in dev drained over months
    before anyone noticed. Recovering them required diffing against prod.

    ⚠️ Callers MUST pass the POST-filter payloads (what the PATCH actually
    sent), not the pre-filter snapshot. The pre-filter dict still contains the
    very choice the user just removed, so replaying it verbatim re-introduces
    it — and that value is no longer legal in the recreated schema, so the
    replay 400s.

    Returns a short id list for the caller's Activity-Log line.
    """
    if not restore_failures:
        return []
    ids = [f.get("id") for f in restore_failures]
    for f in restore_failures:
        fid = f.get("id")
        # An explicit marker matters more than the bytes saved: a silently
        # sliced JSON string is not merely shortened, it is unparseable, and
        # someone recovering by hand cannot tell truncation from corruption.
        try:
            payload = json.dumps(payloads.get(fid, {}))
        except Exception:
            payload = repr(payloads.get(fid))
        if len(payload) > 4000:
            payload = payload[:4000] + "...TRUNCATED"
        # Deliberately ASCII-only: this is the line someone reads to RECOVER a
        # lost record, so it must survive a cp1252 console handler on the
        # Windows host. An emoji here raises UnicodeEncodeError and the message
        # is dropped — losing exactly the data it exists to preserve. `msg` is
        # arbitrary Spoolman response text, so it gets the same coercion.
        safe_msg = str(f.get("msg")).encode("ascii", "backslashreplace").decode("ascii")
        payload = payload.encode("ascii", "backslashreplace").decode("ascii")
        state.logger.error(
            "DATA LOSS in %s: filament #%s was NOT restored after the schema "
            "reset (%s). Its `filament_attributes` is now missing from Spoolman "
            "(sibling extras are unaffected). Recovery payload follows: %s"
            % (op, fid, safe_msg, payload)
        )
    return ids


# --------------------------------------------------------------------------
# Hidden choices (the non-destructive alternative to removing one)
# --------------------------------------------------------------------------

def load_hidden_choices():
    """The choices FCC suppresses from its own UI without touching Spoolman.

    Removing a choice for real costs a full schema rebuild across every
    attribute-bearing record — a prod-shaped migration on an ordinary click.
    Hiding it costs nothing and is reversible, so it is the default path.
    """
    body = _read_json(_HIDDEN_PATH, None)
    if isinstance(body, dict):
        raw = body.get("hidden")
    else:
        raw = body  # tolerate a bare list from a hand-edit
    if not isinstance(raw, list):
        return []
    seen, out = set(), []
    for c in raw:
        s = str(c)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def save_hidden_choices(choices):
    """Persist the hidden-choice list. Returns the normalized list written."""
    seen, out = set(), []
    for c in choices or []:
        s = str(c).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    _write_json_atomic(_HIDDEN_PATH, {"hidden": sorted(out)})
    return sorted(out)


def hide_choice(choice):
    """Add `choice` to the hidden list. Returns the new list."""
    return save_hidden_choices(load_hidden_choices() + [str(choice)])


def unhide_choice(choice):
    """Remove `choice` from the hidden list. Returns the new list."""
    target = str(choice)
    return save_hidden_choices(
        [c for c in load_hidden_choices() if c != target]
    )


def visible_choices(choices, hidden=None):
    """`choices` minus the hidden ones, order preserved."""
    hide = set(load_hidden_choices() if hidden is None else hidden)
    return [c for c in (choices or []) if c not in hide]
