"""Canary: every place the backend writes to Spoolman is listed here (Group 53.2).

Background:
  The 2026-04-26 / 2026-04-27 prod outages were two write-surface bugs: a
  partial `extra` that wiped its siblings, and a write Spoolman rejected whose
  `None` return nobody read. CLAUDE.md "Spool / Filament write surfaces" holds
  the rules every write follows and a table of the surfaces, but nothing
  noticed a NEW write: it passed review because it looked like its neighbours,
  and the same class of bug was found again one feature at a time (Derek,
  2026-08-03). So every Spoolman write call site in the backend is listed
  below, by module and function, and a new one fails here until someone has
  checked it against those rules and registered it.

Three checks:
  1. The registry is exact. Every write site found is in WRITE_SITES with its
     count, and every registered site still exists. A new or grown site fails
     with the rules to check before registering it; a stale one fails with
     "remove it from the registry".
  2. No silent failure. A call of a helper that reports a failed write only by
     what it returns (FAILS_BY_RETURN_VALUE) must not have that result thrown
     away as a bare statement, an `await` of it as a statement, or an
     assignment only to `_`, unless ALLOWED_DISCARDS allows that call. Those
     helpers are spoolman_api's record updates, creates and deletes (None from
     update_spool / update_filament / update_vendor and create_*, False from
     delete_*, each with a hub.log line only), update_extra_field_choices
     (`{"success": False, "msg": ...}`, which it logs nowhere for a refused
     field-list read, a key that isn't there or has no choices, or a refused
     POST; only an exception reaches hub.log), ensure_extra_field (False when
     it couldn't register a field, with one hub.log WARNING and no
     LAST_SPOOLMAN_ERROR: the record helpers' shape), and FCC's own write
     wrappers (WRAPPER_WRITERS, below). Left out: the `_or_raise` forms
     (RAISING_UPDATES), which raise, and the two field-schema helpers that
     return nothing on any path (RETURNS_NOTHING: ensure_required_extras and
     ensure_filament_attributes_cleaned), which leave a caller no result to
     check. A direct HTTP call is outside it too, because its failure is the
     caller's own check of the response.
     ALLOWED_DISCARDS names each site whose calls drop such a result on
     purpose, with how many and why: today only the boot registration,
     ensure_required_extras' three ensure_extra_field calls (best effort at
     startup: a field it can't register is that WARNING, and FCC starts
     anyway). A site with more thrown-away calls than its entry allows has
     every one of them reported.
     Only those three shapes of a thrown-away result (a bare statement, an
     awaited one, `_ =`) are seen, and only on a call the
     scanner reads as a write; everything else passes, such as a result
     stored and never read, a tuple unpacked with its failure part ignored,
     `__ = ...`, `ok and update_spool(...)`, a list or a conditional
     expression of writes as a statement, a write in a lambda or handed to a
     thread, and a call through a local alias (`upd = spoolman_api.update_spool`,
     registered as a value, then `upd(...)`).
  3. The section holds each anchor. A site may carry a doc anchor, a string
     CLAUDE.md's write-surface section must hold (from the line
     "## Spool / Filament write surfaces" to "### Weight-entry surfaces"):
     normally the enclosing function's name, or its endpoint as the table
     writes it. A site of update_spool / update_filament / update_vendor or
     their `_or_raise` forms must carry one; any other site's anchor is
     optional, and checked when it is given. A write helper's or a wrapper's
     own name names what a site calls, and the section may hold it for other
     sites, so it anchors only a site inside that very function. The check is
     a substring test over the whole
     section, its rows, their notes and its prose alike: it fails when a
     site's anchor is nowhere in the section (a write in a function the
     section doesn't name, or a function renamed under it). A row deleted
     while its anchor still appears elsewhere in the section (another row's
     notes, or the prose) is not seen, and neither is a new call in a function
     the section already names (check 1 reports that one). This is the first
     test that reads CLAUDE.md (Derek's OK, 2026-11-09).
  And four lists are kept honest: WRITE_FUNCTIONS equals the spoolman_api
  functions that write, so a new writer there is watched from its first call;
  each of them is in exactly one of check 2's groups (FAILS_BY_RETURN_VALUE,
  RAISING_UPDATES, RETURNS_NOTHING), a RETURNS_NOTHING one with no `return
  <value>` in its own body, so none is left out of check 2 for a reason the
  code doesn't bear out; every WRAPPER_WRITERS entry is still a function of
  its module that writes, so a renamed wrapper can't stop watching its
  callers unnoticed; and every ALLOWED_DISCARDS entry still matches the code
  (as many thrown-away calls at its site, of a helper check 2 reports), so a
  stale one can't let a new call there drop its result unseen.

What counts as a write call site:
  * A use of one of spoolman_api's write helpers (WRITE_FUNCTIONS): the record
    updates (update_spool / update_filament / update_vendor and their
    `_or_raise` forms), the record creates and deletes, and the field-schema
    writes. It is seen as `spoolman_api.<name>(...)`, through any other
    receiver (an alias by import or by assignment), as a bare `<name>(...)`
    (inside spoolman_api itself; anywhere else that would be a
    `from spoolman_api import <name>`, which CLAUDE.md forbids, so it is still
    seen rather than left to hide), under a `from spoolman_api import <name>
    as <alias>` alias, and as a value handed on uncalled (a thread's target,
    or a local alias by assignment): callee "<name> (as a value)".
  * A use of one of FCC's own write wrappers (WRAPPER_WRITERS): a backend
    function that writes to Spoolman, directly or through another of them,
    and reports a failed write only by what it returns, with no log line of
    its own (a record helper under it may write hub.log, which nobody reads in
    the moment). Its callee is its module-qualified name, "logic._move_write".
    It is seen as a bare `<name>(...)` inside its own module, as
    `<anything>.<name>(...)` (`logic._move_write(...)`, a module alias by
    import or by assignment), under a `from <module> import <name> [as
    <alias>]` name, and as a value handed on uncalled. A bare `<name>(...)` in
    another module that didn't import it is that module's own function, and
    is not counted.
  * A direct HTTP write in any module, spoolman_api included:
    `<requests>.post / patch / put / delete(...)`, `<requests>.request(<verb>,
    ...)` with anything but a read verb, `<http_retry>.request_with_retry(<verb>,
    ...)` likewise, and `getattr(<requests>, <verb>)(...)`; and the same verbs,
    `request` and `request_with_retry` called by the name an import gave them
    (`from requests import post [as p]`, from requests.api too, or `*`; `from
    http_retry import request_with_retry [as r]`, or `*`). <requests> is
    exactly: a name bound by `import requests [as x]`, `import
    requests.<sub>` (which binds `requests`), `import requests.api as x` or
    `from requests import api [as x]`; any attribute chain ending in
    `.requests` (`spoolman_api.requests`, which needs no import of its own);
    or either of those followed by `.api` (`requests.api`). <http_retry> is a
    name bound by `import http_retry [as x]`, or any chain ending in
    `.http_retry`. A name bound any other way is neither (see "Not seen").
    The callee reads
    "HTTP <VERB> <target>", the verb "?" when it isn't written as a literal and
    the target taken from the URL argument's text: spool / filament / vendor /
    field / other (a URL held in a variable reads as other).
  A site is keyed by (module file, enclosing function's qualified name, callee)
  and mapped to how many such calls it holds: `outer.inner` for a nested def,
  `Class.method`, `<module>` at module level. Never by line number, which
  drifts with every edit above it.

Scope: the flat backend modules, inventory-hub/*.py, non-recursive (CLAUDE.md
"Backend module map"), as test_requests_timeout_canary.py and
test_no_direct_extra_patch.py scan; test_*.py and conftest.py there are left
out, as the image's .dockerignore leaves them out. Every other Python file is
out of scope. Those that write to Spoolman (2026-11-09):
setup-and-rebuild/setup_fields.py, a deploy tool with its own tests
(test_setup_fields_migration_54_4.py, test_setup_fields_idempotent.py); the
other setup-and-rebuild scripts (migrate_filament_attributes.py,
migrate_inventory.py, migrate_spool_links.py, reset_dev.py); the hand-run
utilities/ scripts (backup_database.py, debug_test.py, repair_db_fields.py,
test_assignment.py, update_from_csv.py); clean_choices.py at the repo root;
and _backup/sync_spoolman.py.

Not seen, so no check can see it either:
  * an HTTP verb chosen into a variable (`send = requests.post if new else
    requests.patch`, then `send(...)`). In spoolman_api.py that would also hide
    a new writer from test_every_spoolman_api_writer_is_listed;
  * requests or http_retry bound any other way: by assignment (`rq =
    spoolman_api.requests` or `http = requests`, then `rq.patch(...)`), or
    imported from another backend module (`from spoolman_api import
    requests`, `from attr_migration import http_retry`); and the retry helper
    aliased by assignment (`rr = http_retry.request_with_retry`, then
    `rr("patch", ...)`);
  * a requests Session (none in the backend; a test's patch of
    `requests.<verb>` can't reach one either), urllib and http.client;
  * a write helper or wrapper reached through getattr (`getattr(spoolman_api,
    "update_spool")(...)`);
  * a NEW function of the wrappers' kind: its callers are watched only once it
    is in WRAPPER_WRITERS. Its own write is a new site (check 1), and the
    registration message asks whether it belongs there.

Counted, though it may not be a Spoolman write at all: any attribute chain
ending in `.requests` or `.http_retry` is read as that module, so an unrelated
`self.requests.delete(rid)` registers as "HTTP DELETE other"; and any
`<anything>.<name>(...)` of a write helper's or a wrapper's name is read as
that helper, so `cache.update_spool(sid, x)` registers as update_spool, and
another object's `backup.restore_extras(rows)` as
attr_migration.restore_extras, with check 2 on its result. None is in the
backend today (2026-11-09). Such a call fails check 1 like any new site:
rename it, or register it with a comment saying what it really is (and, for a
result it drops, an ALLOWED_DISCARDS entry saying the same).
test_a_documented_blind_spot_is_not_seen and
test_a_documented_over_count_is_counted pin every shape both lists name (all
but a new wrapper, which no snippet can show), so a scanner that learns to see
more fails there until these words are brought up to date.

test_no_direct_extra_patch.py already forbids a direct PATCH that carries
`extra`; this test doesn't repeat it.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

INV_HUB = Path(__file__).resolve().parent.parent
CLAUDE_MD = INV_HUB.parent / "CLAUDE.md"
SECTION_START = "## Spool / Filament write surfaces"
SECTION_END = "### Weight-entry surfaces"
THIS_FILE = "inventory-hub/tests/test_spoolman_write_sites.py"

# spoolman_api's write helpers. test_every_spoolman_api_writer_is_listed keeps
# this set equal to the functions in spoolman_api.py that write.
RECORD_UPDATES = frozenset({"update_spool", "update_filament", "update_vendor"})
RAISING_UPDATES = frozenset({
    "update_spool_or_raise", "update_filament_or_raise", "update_vendor_or_raise",
})
CREATES_AND_DELETES = frozenset({
    "create_spool", "create_filament", "create_vendor",
    "delete_spool", "delete_filament",
})
FIELD_SCHEMA_WRITERS = frozenset({
    "ensure_extra_field", "update_extra_field_choices",
    "ensure_filament_attributes_cleaned", "ensure_required_extras",
})
WRITE_FUNCTIONS = RECORD_UPDATES | RAISING_UPDATES | CREATES_AND_DELETES | FIELD_SCHEMA_WRITERS

# FCC's own write wrappers, module-qualified, each with how it reports a failed
# write. Every one writes to Spoolman (directly, or through another of these) and
# reports a failed write ONLY by what it returns: neither it nor anything it calls
# puts that failure in the Activity Log (a record helper under it may write
# hub.log, which nobody reads in the moment). So each caller is a registered write
# site (check 1), and check 2 reports one whose result is thrown away.
# test_every_watched_wrapper_still_writes keeps each entry a function of its module
# that writes. spoolman_api's own write helpers are never entries here: they are
# WRITE_FUNCTIONS, each in one of check 2's groups (FAILS_BY_RETURN_VALUE,
# RAISING_UPDATES, RETURNS_NOTHING). Surveyed 2026-11-09: every other backend
# function outside spoolman_api.py that writes and that other backend code calls
# puts its own failed writes in the Activity Log (itself, or through a function it
# calls), except http_retry.request_with_retry, the transport, whose every write
# call is an HTTP site of its own.
WRAPPER_WRITERS = {
    "logic._move_write":
        "returns False when the write failed and a re-read doesn't show it landed",
    "logic._swap_out_write":
        "returns (landed, location, slot); landed is False when its _move_write failed",
    "logic._audit_park_one":
        "returns (stay why, fail why, record); a failed write's reason is the fail why",
    "logic._audit_file_one":
        "returns (stay why, fail why, record); a failed write's reason is the fail why",
    "logic._undo_filed":
        "returns a dict; a write that failed and isn't proved landed is only in its "
        "retry / retry_why",
    "logic.perform_toolhead_delete_cascade":
        "returns {\"status\": \"requires_confirm\", ...} having written nothing, or a "
        "summary whose errors list holds each refused write",
    "attr_migration.restore_extras":
        "returns (restored, failures, recovered); a filament it couldn't restore is "
        "only in failures",
    "routes_config_attrs._strip_choice_from_carriers":
        "returns (stripped, errors); each refused write is only in errors",
}
# Their bare names, for a call inside their own module: {"_move_write": "logic._move_write"}.
_WRAPPER_BY_NAME = {q.split(".", 1)[1]: q for q in WRAPPER_WRITERS}

# Check 2: these report a failed write only by what they return: None from
# update_spool / update_filament / update_vendor and create_*, False from delete_*
# (each writes only hub.log), {"success": False, "msg": ...} from
# update_extra_field_choices (it logs none of its refusals: a refused field-list
# read, a key that isn't there or has no choices, a refused POST), False from
# ensure_extra_field (one hub.log WARNING and no LAST_SPOOLMAN_ERROR, the record
# helpers' shape), and each wrapper's shape in WRAPPER_WRITERS. A call may drop
# such a result only where ALLOWED_DISCARDS says so.
FAILS_BY_RETURN_VALUE = (RECORD_UPDATES | CREATES_AND_DELETES
                         | {"update_extra_field_choices", "ensure_extra_field"}
                         | frozenset(WRAPPER_WRITERS))
# Left out of check 2, each for a reason the code bears out: the _or_raise forms
# (RAISING_UPDATES), which raise spoolman_api.SpoolmanRejection, and these
# field-schema helpers, which return nothing on any path, so a caller has no
# result to check (a failure of theirs is a hub.log WARNING or ERROR, and
# ensure_filament_attributes_cleaned puts a restore's losses in the Activity Log).
# test_every_write_helper_is_checked_raises_or_returns_nothing keeps every write
# helper in exactly one of FAILS_BY_RETURN_VALUE, RAISING_UPDATES and this set, and
# each of these free of a `return <value>`.
RETURNS_NOTHING = frozenset({"ensure_required_extras", "ensure_filament_attributes_cleaned"})
# Check 3: these sites must carry a doc anchor that CLAUDE.md's write-surface
# section holds. Every other site's anchor is optional, and checked when given.
NEEDS_DOC_ANCHOR = RECORD_UPDATES | RAISING_UPDATES

# What check 2's message says about each helper it can report: how the helper
# reports a failed write, and what its caller must do with that.
_READ_LAST_ERROR = ("read spoolman_api.LAST_SPOOLMAN_ERROR right after the call and log it "
                    "(state.add_log_entry(..., \"ERROR\", \"ff4444\")) or return it so the page "
                    "toasts it at 7 s")
HOW_IT_FAILS = {
    **{name: (f"returns None when Spoolman refused it or didn't answer: {_READ_LAST_ERROR}; "
              f"or call {name}_or_raise, which raises spoolman_api.SpoolmanRejection")
       for name in RECORD_UPDATES},
    **{name: f"returns None when Spoolman refused it or didn't answer: {_READ_LAST_ERROR}"
       for name in ("create_spool", "create_filament", "create_vendor")},
    **{name: f"returns False when Spoolman refused it or didn't answer: {_READ_LAST_ERROR}"
       for name in ("delete_spool", "delete_filament")},
    "update_extra_field_choices": (
        "returns {\"success\": False, \"msg\": ...} on a refused field-list read, a key that "
        "isn't there or has no choices, or a refused POST, and logs none of them: check "
        "res.get(\"success\") and pass res (its msg) back to the page, or log the msg"),
    "ensure_extra_field": (
        "returns False when the field isn't registered and Spoolman refused it or didn't "
        "answer, with one hub.log WARNING and no Activity Log line, and sets no "
        "LAST_SPOOLMAN_ERROR (a refused label update of a field that is there still returns "
        "True): check the result and say so yourself, naming the field, in an ERROR line "
        "(state.add_log_entry(..., \"ERROR\", \"ff4444\")) or in an answer the page toasts "
        "at 7 s"),
    "logic._move_write": (
        f"{WRAPPER_WRITERS['logic._move_write']}, with no log line: {_READ_LAST_ERROR}"),
    "logic._swap_out_write": (
        f"{WRAPPER_WRITERS['logic._swap_out_write']}, with no log line: check landed, then "
        f"{_READ_LAST_ERROR}"),
    "logic._audit_park_one": (
        f"{WRAPPER_WRITERS['logic._audit_park_one']}, with no log line: log a fail why "
        "(\"ERROR\") and list its spool as failed, as _audit_park_locked does"),
    "logic._audit_file_one": (
        f"{WRAPPER_WRITERS['logic._audit_file_one']}, with no log line: log a fail why "
        "(\"ERROR\") and list its spool as failed, as _audit_file_extras does"),
    "logic._undo_filed": (
        f"{WRAPPER_WRITERS['logic._undo_filed']}, with no log line: fold its failed, retry and "
        "retry_why into the Undo's answer, which says each reason in an ERROR line, as "
        "perform_undo does"),
    "logic.perform_toolhead_delete_cascade": (
        f"{WRAPPER_WRITERS['logic.perform_toolhead_delete_cascade']}, with no log line: ask "
        "the question on requires_confirm, and on any errors keep the row and log them "
        "(\"ERROR\"), as api_delete_location does"),
    "attr_migration.restore_extras": (
        f"{WRAPPER_WRITERS['attr_migration.restore_extras']}, with no log line: hand failures "
        "to attr_migration.report_restore_failures (it logs each one's recovery payload), "
        "keep the recovery snapshot, and log the loss (\"ERROR\"), as the three rebuilds do"),
    "routes_config_attrs._strip_choice_from_carriers": (
        f"{WRAPPER_WRITERS['routes_config_attrs._strip_choice_from_carriers']}, with no log "
        "line: count them and log them (\"ERROR\" when none landed, \"WARNING\" when some "
        "did), as api_filament_attributes_remove_choice does"),
}

# Check 2's deliberate exceptions: each site, keyed like WRITE_SITES, whose calls
# drop a FAILS_BY_RETURN_VALUE result on purpose, with how many such calls it
# allows and why. The failure must reach someone another way, or need no one to
# hear of it. A site with more thrown-away calls than its entry allows has every
# one of them reported. test_every_allowed_discard_is_still_used keeps each entry
# matching the code, so a stale one can't let a new call there drop its result
# unseen.
ALLOWED_DISCARDS = {
    # Its filament, spool and vendor loops, run once at startup (app.py, under
    # __main__).
    ("spoolman_api.py", "ensure_required_extras", "ensure_extra_field"): (
        3, "the boot registration is best effort, as its docstring says: a field it can't "
           "register is the WARNING ensure_extra_field writes to hub.log, FCC starts anyway, "
           "and Spoolman refuses a later write that carries that extra, which that write's "
           "own surface reports; there is no request to answer"),
}

HTTP_READ_VERBS = frozenset({"get", "head", "options"})
HTTP_VERB_FUNCS = frozenset({"get", "head", "options", "post", "patch", "put", "delete"})
AS_VALUE = " (as a value)"

Site = collections.namedtuple("Site", "module function callee line discarded")


# ---------------------------------------------------------------------------
# The registry: (module, function, callee): (count, doc anchor).
#
# The doc anchor is a string CLAUDE.md's write-surface section must hold
# (check 3), so a write in a function the section doesn't name can't be
# registered unnoticed. It is a substring test over the whole section: a row
# deleted while its anchor still appears elsewhere there (another row's notes,
# or the prose) is not seen. Every update_spool / update_filament /
# update_vendor site, and every `_or_raise` one, has an anchor; a create,
# delete, field-schema, HTTP or wrapper site has one where the section already
# names its function, else None.
# ---------------------------------------------------------------------------
WRITE_SITES = {
    # --- app.py: the startup field registration, under __main__ ---
    ("app.py", "<module>", "ensure_required_extras"): (1, None),
    ("app.py", "<module>", "ensure_filament_attributes_cleaned"): (1, None),

    # --- attr_migration.py: the restore loop after a filament_attributes
    #     schema rebuild PATCHes each record's WHOLE extras dict back ---
    ("attr_migration.py", "restore_extras", "HTTP PATCH filament"): (1, None),

    # --- http_retry.py: getattr(requests, verb)(...), the transport behind
    #     request_with_retry; each caller is registered with its own verb ---
    ("http_retry.py", "request_with_retry", "HTTP ? other"): (1, None),

    # --- logic.py: the move engine, eject, undo, the audit's label marks ---
    ("logic.py", "_audit_mark_label", "update_spool"): (1, "_audit_mark_label"),
    ("logic.py", "_move_write", "update_spool"): (1, "_move_write"),
    # The unseat of a slot's occupant; the branch writes go through _move_write.
    ("logic.py", "_perform_smart_move_impl", "update_spool"): (1, "_perform_smart_move_impl"),
    ("logic.py", "audit_undo_need_label", "update_spool"): (1, "audit_undo_need_label"),
    ("logic.py", "perform_force_unassign", "update_spool"): (1, "perform_force_unassign"),
    # Return-home and relocate.
    ("logic.py", "perform_smart_eject", "update_spool"): (2, "perform_smart_eject"),
    # A spool deployed to the deleted head is un-deployed; one on it is unassigned.
    ("logic.py", "perform_toolhead_delete_cascade", "update_spool"):
        (2, "perform_toolhead_delete_cascade"),
    # A move's restore, a Smart Load ejection's, and a Swap's displaced spool.
    ("logic.py", "perform_undo", "update_spool"): (3, "perform_undo"),
    # The writes through FCC's own wrappers (WRAPPER_WRITERS). The audit's park
    # and file loops (_audit_park_locked, _audit_file_extras) are named nowhere
    # in the section, so their anchors are None.
    ("logic.py", "_audit_file_extras", "logic._audit_file_one"): (1, None),
    ("logic.py", "_audit_file_one", "logic._move_write"): (1, "_audit_file_one"),
    ("logic.py", "_audit_park_locked", "logic._audit_park_one"): (1, None),
    ("logic.py", "_audit_park_one", "logic._move_write"): (1, "_audit_park_one"),
    # The toolhead, dryer and generic branches' writes.
    ("logic.py", "_perform_smart_move_impl", "logic._move_write"): (3, "_perform_smart_move_impl"),
    # A Swap's stored occupant, filed where it sat before the slot (Swap option C).
    ("logic.py", "_perform_smart_move_impl", "logic._swap_out_write"):
        (1, "_perform_smart_move_impl"),
    ("logic.py", "_swap_out_write", "logic._move_write"): (1, "_swap_out_write"),
    ("logic.py", "_undo_filed", "logic._move_write"): (1, "_undo_filed"),
    # Smart Load's same-slot swap takes the resident into the scan buffer: filed
    # where it sat before that slot, or Unassigned.
    ("logic.py", "perform_smart_eject", "logic._move_write"): (1, "perform_smart_eject"),
    ("logic.py", "perform_smart_eject", "logic._swap_out_write"): (1, "perform_smart_eject"),
    # An audit park's restore, and its filed group's.
    ("logic.py", "perform_undo", "logic._move_write"): (1, "perform_undo"),
    ("logic.py", "perform_undo", "logic._undo_filed"): (1, "perform_undo"),

    # --- print_deduct.py: print usage and the 🛑 review ---
    ("print_deduct.py", "_apply_usage_to_printer", "update_spool"): (1, "_apply_usage_to_printer"),
    ("print_deduct.py", "api_backfill_spool_weights", "update_spool"):
        (1, "/api/backfill_spool_weights"),
    ("print_deduct.py", "api_cancel_deduct_confirm", "update_spool"): (1, "api_cancel_deduct_confirm"),

    # --- routes_config_attrs.py: the filament-attributes manager ---
    ("routes_config_attrs.py", "_strip_choice_from_carriers", "update_filament"):
        (1, "_strip_choice_from_carriers"),
    ("routes_config_attrs.py", "api_filament_attributes_bulk_set", "update_filament"):
        (1, "api_filament_attributes_bulk_set"),
    ("routes_config_attrs.py", "api_filament_attributes_add_choice", "update_extra_field_choices"):
        (1, None),
    # Purge and Sweep Unused rebuild the field: DELETE it, POST it back, then
    # attr_migration.restore_extras. The DELETE wipes the extra on every record.
    # No row describes the rebuild (the section's remove_choice row is the HIDE
    # path), so its sites have no anchor.
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice", "HTTP DELETE field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice", "HTTP POST field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice", "attr_migration.restore_extras"):
        (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_sweep_unused", "HTTP DELETE field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_sweep_unused", "HTTP POST field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_sweep_unused", "attr_migration.restore_extras"):
        (1, None),
    # The HIDE path, the default.
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice",
     "routes_config_attrs._strip_choice_from_carriers"): (1, "/api/filament_attributes/remove_choice"),

    # --- routes_inventory.py: the wizard, vendors, creates, /api/spool/update ---
    ("routes_inventory.py", "_take_archived_off", "update_spool"): (1, "_take_archived_off"),
    ("routes_inventory.py", "api_create_filament", "create_filament"): (1, None),
    ("routes_inventory.py", "api_create_inventory_wizard", "create_filament"):
        (1, "api_create_inventory_wizard"),
    ("routes_inventory.py", "api_create_inventory_wizard", "create_spool"):
        (1, "api_create_inventory_wizard"),
    ("routes_inventory.py", "api_create_vendor", "create_vendor"): (1, None),
    ("routes_inventory.py", "api_edit_spool_wizard", "update_filament"): (1, "api_edit_spool_wizard"),
    ("routes_inventory.py", "api_edit_spool_wizard", "update_spool"): (1, "api_edit_spool_wizard"),
    ("routes_inventory.py", "api_external_fields_add_choice", "update_extra_field_choices"): (1, None),
    # With and without the archive edge (the weigh screens' Auto-Archive switch).
    ("routes_inventory.py", "api_spool_update", "update_spool"): (2, "/api/spool/update"),
    # Re-orders the field definitions, echoing every other property back.
    ("routes_inventory.py", "api_spoolman_restore_field_order", "HTTP POST field"): (1, None),
    ("routes_inventory.py", "api_update_vendor", "update_vendor_or_raise"): (1, "PATCH /api/vendors/<id>"),

    # --- routes_locations.py: location delete, record deletes, Merge Filament ---
    ("routes_locations.py", "api_delete_filament", "delete_filament"): (1, None),
    ("routes_locations.py", "api_delete_filament", "delete_spool"): (1, None),
    ("routes_locations.py", "api_delete_location", "update_spool"): (1, "`/api/locations` DELETE cascade"),
    # A toolhead row's delete: its spools unassigned or un-deployed.
    ("routes_locations.py", "api_delete_location", "logic.perform_toolhead_delete_cascade"):
        (1, "`/api/locations` DELETE cascade"),
    ("routes_locations.py", "api_delete_spool", "delete_spool"): (1, None),
    ("routes_locations.py", "api_merge_filament", "delete_filament"): (1, "api_merge_filament"),
    ("routes_locations.py", "api_merge_filament", "update_spool_or_raise"): (1, "api_merge_filament"),

    # --- routes_print_queue.py: label flags ---
    ("routes_print_queue.py", "api_flag_spool_labels", "update_spool"):
        (1, "/api/filament/<id>/flag_spool_labels"),
    ("routes_print_queue.py", "api_print_queue_mark_printed", "update_filament"):
        (1, "/api/print_queue/mark_printed"),
    ("routes_print_queue.py", "api_print_queue_mark_printed", "update_spool"):
        (1, "/api/print_queue/mark_printed"),
    ("routes_print_queue.py", "api_print_queue_set_flag", "update_filament"):
        (1, "/api/print_queue/set_flag"),
    ("routes_print_queue.py", "api_print_queue_set_flag", "update_spool"):
        (1, "/api/print_queue/set_flag"),

    # --- routes_scan.py: scans and quick edits ---
    ("routes_scan.py", "_handle_prusament_url_scan", "update_filament_or_raise"):
        (1, "_handle_prusament_url_scan"),
    ("routes_scan.py", "_handle_prusament_url_scan", "update_spool"): (1, "_handle_prusament_url_scan"),
    ("routes_scan.py", "_verify_spool_label", "update_spool"): (1, "_verify_spool_label"),
    # The filament label-confirm scan.
    ("routes_scan.py", "api_identify_scan", "update_filament"): (1, "api_identify_scan"),
    ("routes_scan.py", "api_prusament_apply_weights", "update_spool_or_raise"):
        (1, "/api/spool/prusament_apply_weights"),
    ("routes_scan.py", "api_update_filament", "update_filament"): (1, "/api/update_filament"),

    # --- spoolman_api.py: the helpers themselves ---
    ("spoolman_api.py", "create_filament", "HTTP POST filament"): (1, None),
    ("spoolman_api.py", "create_spool", "HTTP POST spool"): (1, None),
    ("spoolman_api.py", "create_vendor", "HTTP POST vendor"): (1, None),
    ("spoolman_api.py", "delete_filament", "HTTP DELETE filament"): (1, None),
    ("spoolman_api.py", "delete_spool", "HTTP DELETE spool"): (1, None),
    ("spoolman_api.py", "ensure_extra_field", "HTTP POST field"): (2, None),
    ("spoolman_api.py", "ensure_filament_attributes_cleaned", "HTTP DELETE field"): (1, None),
    ("spoolman_api.py", "ensure_filament_attributes_cleaned", "HTTP POST field"): (1, None),
    ("spoolman_api.py", "ensure_filament_attributes_cleaned", "attr_migration.restore_extras"): (1, None),
    ("spoolman_api.py", "ensure_required_extras", "ensure_extra_field"): (3, None),
    ("spoolman_api.py", "update_extra_field_choices", "HTTP POST field"): (1, None),
    ("spoolman_api.py", "update_filament", "HTTP PATCH filament"): (1, None),
    ("spoolman_api.py", "update_filament_or_raise", "update_filament"): (1, "update_filament_or_raise"),
    ("spoolman_api.py", "update_spool", "HTTP PATCH spool"): (1, None),
    ("spoolman_api.py", "update_spool_or_raise", "update_spool"): (1, "update_spool_or_raise"),
    ("spoolman_api.py", "update_vendor", "HTTP PATCH vendor"): (1, None),
    ("spoolman_api.py", "update_vendor_or_raise", "update_vendor"): (1, "update_vendor_or_raise"),

    # --- stock_report.py: Low stock's Excluded mark ---
    ("stock_report.py", "exclude_filament", "update_filament"): (1, "exclude_filament"),
    ("stock_report.py", "include_again", "update_filament"): (1, "include_again"),
}


# ---------------------------------------------------------------------------
# The scanner
# ---------------------------------------------------------------------------

class _Bindings:
    """The names one module binds to requests, http_retry, spoolman_api's writers
    and FCC's write wrappers."""

    def __init__(self, tree):
        self.requests = set()        # import requests [as x], import requests.api as x,
                                     # from requests import api [as x]
        self.requests_funcs = {}     # from requests[.api] import post [as p] -> {"p": "post"}
        self.retry = set()           # import http_retry [as x]
        self.retry_funcs = set()     # from http_retry import request_with_retry [as r]
        self.writers = {}            # from spoolman_api import update_spool [as us] -> {"us": "update_spool"}
        self.wrappers = {}           # from logic import _move_write [as mw] -> {"mw": "logic._move_write"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "requests":
                        self.requests.add(a.asname or "requests")
                    elif a.name == "requests.api" and a.asname:
                        self.requests.add(a.asname)     # binds the api module itself
                    elif a.name.startswith("requests.") and not a.asname:
                        self.requests.add("requests")   # `import requests.x` binds `requests`
                    elif a.name == "http_retry":
                        self.retry.add(a.asname or "http_retry")
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    local = a.asname or a.name
                    if node.module in ("requests", "requests.api"):
                        if a.name == "*":
                            self.requests_funcs.update({v: v for v in HTTP_VERB_FUNCS | {"request"}})
                        elif a.name in HTTP_VERB_FUNCS or a.name == "request":
                            self.requests_funcs[local] = a.name
                        elif node.module == "requests" and a.name == "api":
                            self.requests.add(local)    # `from requests import api [as x]`
                    elif node.module == "http_retry":
                        if a.name in ("request_with_retry", "*"):
                            self.retry_funcs.add("request_with_retry" if a.name == "*" else local)
                    elif node.module == "spoolman_api" and a.name in WRITE_FUNCTIONS:
                        self.writers[local] = a.name
                    else:
                        for qual in WRAPPER_WRITERS:
                            module, name = qual.split(".", 1)
                            if node.module != module:
                                continue
                            if a.name == name:
                                self.wrappers[local] = qual
                            elif a.name == "*" and not name.startswith("_"):
                                self.wrappers[name] = qual   # a star import binds public names only


def _discarded_calls(tree):
    """ids of the Call nodes whose result is thrown away: a bare statement, an
    `await` of the call as a statement, or an assignment only to `_`."""
    out = set()
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Expr):
            value = node.value
        elif isinstance(node, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id == "_" for t in node.targets):
            value = node.value
        elif (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
              and node.target.id == "_"):
            value = node.value
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call):
            out.add(id(value))
    return out


def _arg(call, position, keyword):
    """The call's argument at `position`, else its `keyword=` argument, else None."""
    if len(call.args) > position and not any(
            isinstance(a, ast.Starred) for a in call.args[:position + 1]):
        return call.args[position]
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _verb(node):
    """A verb written as a string literal, lower case; '?' for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip().lower() or "?"
    return "?"


def _target(url):
    """What an HTTP write is aimed at, from the URL argument's own text."""
    if url is None:
        return "other"
    text = "".join(
        n.value for n in ast.walk(url)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )
    # Field first: a field URL names its entity too (/api/v1/field/spool/...).
    for marker, target in (("/api/v1/field", "field"), ("/api/v1/spool", "spool"),
                           ("/api/v1/filament", "filament"), ("/api/v1/vendor", "vendor")):
        if marker in text:
            return target
    return "other"


def _writer(callee):
    """The spoolman_api helper or FCC wrapper a callee names (a wrapper by its
    module-qualified name), or None for an HTTP site."""
    name = callee[:-len(AS_VALUE)] if callee.endswith(AS_VALUE) else callee
    return name if name in WRITE_FUNCTIONS or name in WRAPPER_WRITERS else None


def _own_name(anchor):
    """The function an anchor names when it is a write helper's or a wrapper's
    own name (a wrapper's bare or module-qualified name), else None."""
    if anchor in WRITE_FUNCTIONS:
        return anchor
    if anchor in WRAPPER_WRITERS:
        return anchor.split(".", 1)[1]
    return anchor if anchor in _WRAPPER_BY_NAME else None


class _SiteFinder(ast.NodeVisitor):
    """Collects one module's write call sites, each with the qualified name of
    the function it sits in."""

    def __init__(self, module, tree):
        self.module = module
        self.sites = []
        self._scope = []
        self._called = set()       # ids of the func nodes already recorded as a call
        self._discarded = _discarded_calls(tree)
        self._b = _Bindings(tree)

    # -- where we are --------------------------------------------------------
    def _scoped(self, name, node):
        self._scope.append(name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node):
        self._scoped(node.name, node)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self._scoped("<lambda>", node)

    def _add(self, callee, node, discarded=False):
        self.sites.append(Site(self.module, ".".join(self._scope) or "<module>",
                               callee, node.lineno, discarded))

    # -- spoolman_api's writers and FCC's wrappers ---------------------------
    def _writer_named(self, node):
        """The callee text `node` names: a write helper's name, a wrapper's
        module-qualified name, or None."""
        if isinstance(node, ast.Attribute):
            if node.attr in WRITE_FUNCTIONS:
                return node.attr
            if node.attr in _WRAPPER_BY_NAME:
                return _WRAPPER_BY_NAME[node.attr]          # logic._move_write(...), any receiver
        if isinstance(node, ast.Name):
            if node.id in self._b.writers:
                return self._b.writers[node.id]
            if node.id in WRITE_FUNCTIONS:
                return node.id
            if node.id in self._b.wrappers:
                return self._b.wrappers[node.id]            # from logic import _move_write [as x]
            qual = _WRAPPER_BY_NAME.get(node.id)
            if qual and qual.split(".", 1)[0] + ".py" == self.module:
                return qual                                 # a bare call inside its own module
        return None

    def visit_Attribute(self, node):
        self._value_use(node)
        self.generic_visit(node)

    def visit_Name(self, node):
        self._value_use(node)

    def _value_use(self, node):
        """A write helper or wrapper named without being called: handed on as a value."""
        if id(node) in self._called or not isinstance(node.ctx, ast.Load):
            return
        writer = self._writer_named(node)
        if writer:
            self._add(writer + AS_VALUE, node)

    # -- calls ---------------------------------------------------------------
    def visit_Call(self, node):
        writer = self._writer_named(node.func)
        if writer:
            self._called.add(id(node.func))
            self._add(writer, node, id(node) in self._discarded)
        else:
            http = self._http_call(node)
            if http and http[0] not in HTTP_READ_VERBS:
                verb, url = http
                self._add(f"HTTP {verb.upper()} {_target(url)}", node,
                          id(node) in self._discarded)
        self.generic_visit(node)

    def _is_requests(self, node):
        """Does `node` name the requests module (or requests.api)? A name an
        import bound to it, any attribute chain ending in `.requests`
        (`spoolman_api.requests`, which a module can use with no import of its
        own), or either of those followed by `.api`."""
        if isinstance(node, ast.Name):
            return node.id in self._b.requests
        if isinstance(node, ast.Attribute):
            if node.attr == "requests":
                return True
            if node.attr == "api":
                return self._is_requests(node.value)
        return False

    def _is_retry(self, node):
        """Does `node` name the http_retry module? A name an import bound to it,
        or any attribute chain ending in `.http_retry`."""
        if isinstance(node, ast.Name):
            return node.id in self._b.retry
        return isinstance(node, ast.Attribute) and node.attr == "http_retry"

    def _http_call(self, node):
        """(verb, URL node) when `node` is an HTTP call, else None."""
        func, b = node.func, self._b
        if isinstance(func, ast.Attribute):
            if self._is_requests(func.value):
                if func.attr in HTTP_VERB_FUNCS:
                    return func.attr, _arg(node, 0, "url")
                if func.attr == "request":
                    return _verb(_arg(node, 0, "method")), _arg(node, 1, "url")
            if func.attr == "request_with_retry" and self._is_retry(func.value):
                return _verb(_arg(node, 0, "method")), _arg(node, 1, "url")
        if isinstance(func, ast.Name):
            if func.id in b.requests_funcs:
                verb = b.requests_funcs[func.id]
                if verb == "request":
                    return _verb(_arg(node, 0, "method")), _arg(node, 1, "url")
                return verb, _arg(node, 0, "url")
            if func.id in b.retry_funcs:
                return _verb(_arg(node, 0, "method")), _arg(node, 1, "url")
        # getattr(requests, verb)(url, ...): http_retry's own dispatch.
        if (isinstance(func, ast.Call) and isinstance(func.func, ast.Name)
                and func.func.id == "getattr" and len(func.args) >= 2
                and self._is_requests(func.args[0])):
            return _verb(func.args[1]), _arg(node, 0, "url")
        return None


def find_write_sites(module, source):
    """Every write call site in one module's source text, as Site tuples."""
    tree = ast.parse(source)
    finder = _SiteFinder(module, tree)
    finder.visit(tree)
    return finder.sites


def count_sites(sites):
    return collections.Counter((s.module, s.function, s.callee) for s in sites)


def backend_modules():
    """The flat backend modules: inventory-hub/*.py less test_*.py and conftest.py."""
    return [p for p in sorted(INV_HUB.glob("*.py"))
            if not p.name.startswith("test_") and p.name != "conftest.py"]


def scan_backend():
    sites = []
    for path in backend_modules():
        sites += find_write_sites(path.name, path.read_text(encoding="utf-8-sig"))
    return sites


# ---------------------------------------------------------------------------
# The checks, as functions over the scanner's output and CLAUDE.md's text
# ---------------------------------------------------------------------------

def _key_text(key):
    module, function, callee = key
    return f"{module}  {function}  -> {callee}"


def _entries(registry):
    """The registry's entries, each checked for its shape first, then sorted:
    (module, function, callee): (count of 1 or more, doc anchor or None)."""
    for key, value in registry.items():
        ok = (isinstance(key, tuple) and len(key) == 3 and all(isinstance(k, str) for k in key)
              and isinstance(value, tuple) and len(value) == 2
              and isinstance(value[0], int) and not isinstance(value[0], bool) and value[0] >= 1
              and (value[1] is None or (isinstance(value[1], str) and value[1].strip())))
        if not ok:
            raise ValueError(
                f"WRITE_SITES entry {key!r}: {value!r} has the wrong shape. Write it as "
                '("module.py", "function", "callee"): (count, "doc anchor" or None), '
                "with a count of 1 or more.")
    return sorted(registry.items())


def registry_problems(found, registry):
    """([new or grown sites], [stale or shrunk entries]), each a line of text."""
    entries = dict(_entries(registry))
    new, stale = [], []
    for key, n in sorted(found.items()):
        want = entries.get(key, (0, None))[0]
        if n > want:
            new.append(f"{_key_text(key)}: {n} found, {want} registered")
    for key, (want, _doc) in entries.items():
        n = found.get(key, 0)
        if n < want:
            stale.append(f"{_key_text(key)}: {want} registered, {n} found")
    return new, stale


def _allowances(allowed):
    """ALLOWED_DISCARDS-shaped entries, each checked for its shape first:
    (module, function, callee): (count of 1 or more, a reason that isn't blank)."""
    for key, value in allowed.items():
        ok = (isinstance(key, tuple) and len(key) == 3 and all(isinstance(k, str) for k in key)
              and isinstance(value, tuple) and len(value) == 2
              and isinstance(value[0], int) and not isinstance(value[0], bool) and value[0] >= 1
              and isinstance(value[1], str) and value[1].strip())
        if not ok:
            raise ValueError(
                f"ALLOWED_DISCARDS entry {key!r}: {value!r} has the wrong shape. Write it as "
                '("module.py", "function", "callee"): (count, "why its result may be thrown '
                'away"), with a count of 1 or more and a reason that isn\'t blank.')
    return sorted(allowed.items())


def _thrown_away(sites):
    """The sites' calls of a FAILS_BY_RETURN_VALUE helper whose result is thrown
    away as a bare statement, an awaited statement or `_ =`."""
    return [s for s in sites if s.discarded and s.callee in FAILS_BY_RETURN_VALUE]


def silent_failures(sites, allowed=None):
    """The calls of a FAILS_BY_RETURN_VALUE helper (a record helper,
    update_extra_field_choices, ensure_extra_field or a wrapper) whose result is
    thrown away as a bare statement, an awaited statement or `_ =`, less what
    `allowed` (ALLOWED_DISCARDS unless given) allows: a site's thrown-away calls
    pass while there are no more of them than its entry allows, and are all
    reported, with both counts, when there are more."""
    allows = {key: n for key, (n, _why) in _allowances(
        ALLOWED_DISCARDS if allowed is None else allowed)}
    thrown = _thrown_away(sites)
    per_site = count_sites(thrown)
    out = []
    for s in thrown:
        key = (s.module, s.function, s.callee)
        n, ok = per_site[key], allows.get(key, 0)
        if n <= ok:
            continue
        note = f" ({n} thrown away here, ALLOWED_DISCARDS allows {ok})" if ok else ""
        out.append(f"{s.module}:{s.line}  {s.function}  -> {s.callee}(...), its result "
                   f"thrown away{note}")
    return out


def allowance_problems(sites, allowed):
    """The `allowed` (ALLOWED_DISCARDS) entries that no longer match `sites`, each
    a line of text: an entry for a callee check 2 doesn't report, or one that
    allows more thrown-away calls than its site has (its calls gone, or keeping
    their result now). An entry of the wrong shape, or with no reason, raises."""
    thrown = count_sites(_thrown_away(sites))
    out = []
    for key, (want, _why) in _allowances(allowed):
        if key[2] not in FAILS_BY_RETURN_VALUE:
            out.append(f"{_key_text(key)}: check 2 doesn't report this callee (it isn't in "
                       "FAILS_BY_RETURN_VALUE): remove it")
            continue
        n = thrown.get(key, 0)
        if n < want:
            out.append(f"{_key_text(key)}: ALLOWED_DISCARDS allows {want} thrown-away call(s), "
                       f"{n} found: " + ("remove it" if n == 0 else f"lower its count to {n}"))
    return out


def _value_returns(func):
    """The lines of `func`'s own `return <value>` statements. A bare `return` and
    `return None` return nothing, and a nested def's or class's returns are its
    own."""
    out, todo = [], list(ast.iter_child_nodes(func))
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            out.append(node.lineno)
        todo.extend(ast.iter_child_nodes(node))
    return sorted(out)


def helper_group_problems(source, helpers=WRITE_FUNCTIONS, returns_nothing=RETURNS_NOTHING):
    """For spoolman_api.py's source: each write helper (`helpers`) that isn't in
    exactly one of check 2's groups, FAILS_BY_RETURN_VALUE (it reports a failed
    write by what it returns), RAISING_UPDATES (it raises) or `returns_nothing`
    (it returns nothing, so there is nothing to check); each `returns_nothing`
    helper with a `return <value>` in its own body; and each `returns_nothing`
    name that isn't a write helper. Each a line of text."""
    groups = (("FAILS_BY_RETURN_VALUE", FAILS_BY_RETURN_VALUE),
              ("RAISING_UPDATES", RAISING_UPDATES), ("RETURNS_NOTHING", returns_nothing))
    defined = {n.name: n for n in ast.parse(source).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    out = []
    for name in sorted(set(helpers) | set(returns_nothing)):
        if name not in helpers:
            out.append(f"{name}: in RETURNS_NOTHING, but it isn't a write helper (WRITE_FUNCTIONS)")
            continue
        found_in = [label for label, members in groups if name in members]
        if not found_in:
            out.append(f"{name}: in none of FAILS_BY_RETURN_VALUE, RAISING_UPDATES and "
                       "RETURNS_NOTHING")
        elif len(found_in) > 1:
            out.append(f"{name}: in {' and '.join(found_in)}")
        elif found_in == ["RETURNS_NOTHING"] and name in defined:
            lines = _value_returns(defined[name])
            if lines:
                out.append(f"{name}: in RETURNS_NOTHING, but it returns a value "
                           f"(spoolman_api.py:{', '.join(map(str, lines))})")
    return out


class SectionMissing(LookupError):
    pass


def write_surface_section(claude_md):
    """The text of CLAUDE.md's write-surface section, its heading line to the
    line before its end marker."""
    lines = claude_md.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == SECTION_START), None)
    if start is None:
        raise SectionMissing(
            f'CLAUDE.md has no line "{SECTION_START}": the write-surface section moved or '
            f"was renamed. Point SECTION_START in {THIS_FILE} at its new heading.")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip().startswith(SECTION_END)), None)
    if end is None:
        raise SectionMissing(
            f'CLAUDE.md has no line starting "{SECTION_END}" after "{SECTION_START}": the '
            f"line that ends the write-surface section moved or was renamed. Point "
            f"SECTION_END in {THIS_FILE} at the heading that now follows the section.")
    return "\n".join(lines[start:end])


def anchor_problems(registry, section):
    """The registered sites whose doc anchor the section doesn't hold, the
    NEEDS_DOC_ANCHOR sites with no anchor at all, and the anchors that name
    what a site calls rather than the site: a write helper's own name is in
    the section's opening lines, and a wrapper's sits in the rows of functions
    that call it, so either is an anchor only for a site inside that very
    function (the `_or_raise` forms' own calls, a wrapper's own write).

    A substring test over the whole section, rows, notes and prose alike: an
    anchor found anywhere there passes, so a site's row deleted while its
    anchor still appears elsewhere in the section is not reported."""
    out = []
    for key, (_n, doc) in _entries(registry):
        if doc is None:
            if _writer(key[2]) in NEEDS_DOC_ANCHOR:
                out.append(f"{_key_text(key)}: no doc anchor")
        elif _own_name(doc) and _own_name(doc) != key[1]:
            if doc in WRITE_FUNCTIONS:
                what = ("a write helper's name, which the section holds for every site; anchor it "
                        "to its function or endpoint")
            else:
                what = ("a wrapper's own name, not the site's; anchor it to its function or "
                        "endpoint")
            if _writer(key[2]) not in NEEDS_DOC_ANCHOR:
                what += ", or give it None (its anchor is optional)"
            out.append(f"{_key_text(key)}: {doc!r} is {what}")
        elif doc not in section:
            out.append(f"{_key_text(key)}: {doc!r} is not in the section")
    return out


def writer_set_problems(source, listed):
    """For spoolman_api.py's source: ([writers missing from `listed`, with what
    each writes through], [listed names that aren't writers there]). A writer is
    a top-level function with a write in it: an HTTP write, or a use of one of
    WRITE_FUNCTIONS or WRAPPER_WRITERS."""
    writes = collections.defaultdict(set)
    for s in find_write_sites("spoolman_api.py", source):
        writes[s.function.split(".")[0]].add(s.callee)
    defined = {n.name for n in ast.parse(source).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    unlisted = [f"{f} ({', '.join(sorted(writes[f]))})" for f in sorted(set(writes) - listed)]
    not_writers = [f if f in defined else f"{f} (not defined)" for f in sorted(listed - set(writes))]
    return unlisted, not_writers


def wrapper_set_problems(sources, wrappers):
    """For the backend's {module file: source}: the `wrappers` entries
    ("module.function") that no longer hold, each a line of text. Its module
    must be a backend module that defines it as a top-level function, the
    function must still write (a write site inside it, a call of another
    wrapper included), and its bare name must be its own: shared with another
    entry or a spoolman_api write helper, a bare call couldn't be told apart."""
    out = []
    bare = collections.Counter(q.split(".", 1)[1] for q in wrappers)
    for qual in sorted(wrappers):
        module, _, name = qual.partition(".")
        path = module + ".py"
        if bare[name] > 1 or name in WRITE_FUNCTIONS:
            out.append(f"{qual}: its bare name {name!r} is also another write helper's or wrapper's")
        if path not in sources:
            out.append(f"{qual}: {path} is not a backend module (inventory-hub/*.py)")
            continue
        tree = ast.parse(sources[path])
        if name not in {n.name for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}:
            out.append(f"{qual}: {path} defines no top-level function {name} (renamed or removed?)")
            continue
        if not any(s.function.split(".")[0] == name for s in find_write_sites(path, sources[path])):
            out.append(f"{qual}: {name} has no write site inside it any more: it no longer "
                       "writes, or writes only through a helper this file doesn't watch (a "
                       "renamed wrapper?)")
    return out


# ---------------------------------------------------------------------------
# Failure messages
# ---------------------------------------------------------------------------

REGISTER_RULES = f"""
Before you register a write, check it against CLAUDE.md "Spool / Filament write surfaces":
  - A partial `extra` on a user-driven edit surface goes through
    spoolman_api.compute_dirty_extras(existing, requested,
    system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS).
  - A write that reports a rejection by returning None (False from delete_*): read
    spoolman_api.LAST_SPOOLMAN_ERROR right after the call, and log it
    (state.add_log_entry(..., "ERROR", "ff4444")) or return it so the page toasts it at 7 s.
  - High-stakes paths (slot assignment, label-confirm, force-move, weigh-out) use the
    _or_raise form (update_spool_or_raise / update_filament_or_raise / update_vendor_or_raise).
  - Clear an extra only with spoolman_api.DELETE_EXTRA_SENTINEL, never by leaving the key
    out or sending None.
  - A write reported failed may still have landed (update_spool's timeout is a read
    timeout): re-read the record before calling it failed where that matters.
  - A field-schema DELETE wipes that extra on every record (Group 36): never add one lightly.
  - Add a row for it to the write-surface table in CLAUDE.md (or extend the row that covers it).
  - If the write is in a helper other backend code calls, and that helper reports a failed write
    only by what it returns (no log line of its own), add the helper to WRAPPER_WRITERS in
    {THIS_FILE}: then each call of it is a site here, and check 2 reports one whose result
    is thrown away.
Then register it in WRITE_SITES in {THIS_FILE}, under its module:
    ("module.py", "function", "callee"): (count, "doc anchor"),
where the doc anchor is a string the write-surface section holds (the function's name, or its
endpoint as the table writes it). It is required for update_spool / update_filament /
update_vendor and their _or_raise forms; for any other site give one where the section already
names the function, else None.
"""


def registry_message(new, stale):
    parts = []
    if new:
        parts.append("New Spoolman write call site(s), or more calls than registered:\n  "
                     + "\n  ".join(new) + "\n" + REGISTER_RULES)
    if stale:
        parts.append("Registered write site(s) the code no longer has, or has fewer of:\n  "
                     + "\n  ".join(stale)
                     + f"\nRemove it from the registry (WRITE_SITES in {THIS_FILE}), or lower "
                       "its count. If the write surface itself is gone, take its row out of "
                       "CLAUDE.md's write-surface table too.")
    return "\n\n".join(parts)


def _offender_callee(offender):
    """The callee in one of silent_failures' lines."""
    return offender.rsplit("-> ", 1)[-1].rsplit("(...)", 1)[0]


def silent_failure_message(offenders):
    helpers = sorted({_offender_callee(o) for o in offenders} & set(HOW_IT_FAILS))
    over = any("ALLOWED_DISCARDS allows" in o for o in offenders)
    return (
        "A Spoolman write's result is thrown away, so a failed write goes unseen (the class of "
        "bug behind the 2026-04-26/27 prod outages):\n  " + "\n  ".join(offenders)
        + "\n\nEach of these reports a failed write only by what it returns. Keep the result and "
          "check it:\n" + "\n".join(f"  - {h} {HOW_IT_FAILS[h]}." for h in helpers)
        + ("\n\nA site listed with two counts has more thrown-away calls than ALLOWED_DISCARDS "
           "allows there: keep the new call's result, or raise its count only when the new call "
           "drops it for the same reason." if over else "")
        + "\n\nOnly a call that drops the result on purpose, its failure reaching someone another "
          "way (or needing no one to hear of it), may stay as it is: add its site to "
          f"ALLOWED_DISCARDS in {THIS_FILE}, (\"module.py\", \"function\", \"callee\"): (how many "
          "such calls, \"why\")."
    )


def allowance_message(problems):
    return (
        "ALLOWED_DISCARDS entries that no longer match the code:\n  " + "\n  ".join(problems)
        + f"\nIn {THIS_FILE}, an entry allows that many thrown-away calls of its callee in its "
          "function, and no more. Remove one whose calls are gone or keep their result now, "
          "lower a count that is above what the site has, and remove one for a callee check 2 "
          "doesn't report: a stale entry would let a new call there drop its result unseen."
    )


def helper_group_message(problems):
    return (
        "spoolman_api write helpers check 2 can't place:\n  " + "\n  ".join(problems)
        + f"\nIn {THIS_FILE}, put each write helper in exactly one group: FAILS_BY_RETURN_VALUE "
          "when it reports a failed write by what it returns (with a HOW_IT_FAILS line saying "
          "what its caller must do, and an ALLOWED_DISCARDS entry for each site that drops the "
          "result on purpose), RAISING_UPDATES when it raises on a failed write (the _or_raise "
          "forms), or RETURNS_NOTHING when it returns nothing on any path. A helper that "
          "returns a value isn't RETURNS_NOTHING: its callers can check it. Take a name that "
          "isn't a write helper out of RETURNS_NOTHING."
    )


def anchor_message(problems):
    return (
        "These registered sites' doc anchors are missing, not in CLAUDE.md's write-surface "
        "section, or name a write helper or wrapper instead of the site:\n  "
        + "\n  ".join(problems)
        + "\n\nAdd a row to the table in the section from \"" + SECTION_START + "\" to \""
        + SECTION_END + "\" (| Module | Endpoint / Function | Notes |: what it writes, whether "
          "it merges against the live record, how a failure is surfaced), or extend the row "
          "that covers it, so the section holds the site's doc anchor. Or, if the anchor is "
          f"wrong, give the site in WRITE_SITES ({THIS_FILE}) the name or endpoint the table "
          "already uses for it."
    )


# ---------------------------------------------------------------------------
# The checks on the real tree
# ---------------------------------------------------------------------------

def test_every_write_site_is_registered():
    new, stale = registry_problems(count_sites(scan_backend()), WRITE_SITES)
    assert not (new or stale), registry_message(new, stale)


def test_no_write_result_is_thrown_away():
    offenders = silent_failures(scan_backend())
    assert not offenders, silent_failure_message(offenders)


def test_every_allowed_discard_is_still_used():
    """Each ALLOWED_DISCARDS entry still matches the code: as many calls there,
    each still dropping its result, of a helper check 2 reports. A stale entry
    would let a new call there drop its result unseen."""
    problems = allowance_problems(scan_backend(), ALLOWED_DISCARDS)
    assert not problems, allowance_message(problems)


def test_the_write_surface_section_holds_every_doc_anchor():
    """Check 3: each registered anchor is somewhere in the section, and every
    update_spool / update_filament / update_vendor (and _or_raise) site has one.
    It can't tell which row holds an anchor: a row deleted while its anchor
    still appears elsewhere in the section passes."""
    try:
        section = write_surface_section(CLAUDE_MD.read_text(encoding="utf-8"))
    except SectionMissing as e:
        pytest.fail(str(e))
    problems = anchor_problems(WRITE_SITES, section)
    assert not problems, anchor_message(problems)


def test_every_spoolman_api_writer_is_listed():
    """WRITE_FUNCTIONS is exactly the set of spoolman_api functions that write,
    so a new writer there is watched at every call from its first one."""
    source = (INV_HUB / "spoolman_api.py").read_text(encoding="utf-8-sig")
    unlisted, not_writers = writer_set_problems(source, WRITE_FUNCTIONS)
    assert not unlisted, (
        "spoolman_api function(s) that write to Spoolman but aren't in WRITE_FUNCTIONS: "
        + ", ".join(unlisted)
        + f"\nAdd each to the set it belongs to in {THIS_FILE} (RECORD_UPDATES, RAISING_UPDATES, "
          "CREATES_AND_DELETES or FIELD_SCHEMA_WRITERS), so every call of it is a registered "
          "write site, and to one of check 2's groups (FAILS_BY_RETURN_VALUE with a HOW_IT_FAILS "
          "line when it reports a failed write by what it returns, RAISING_UPDATES when it "
          "raises, RETURNS_NOTHING when it returns nothing)."
    )
    assert not not_writers, (
        "WRITE_FUNCTIONS names function(s) spoolman_api.py doesn't define, or that no longer "
        "write: " + ", ".join(not_writers) + f"\nTake them out of their set in {THIS_FILE}."
    )


def test_every_write_helper_is_checked_raises_or_returns_nothing():
    """Each spoolman_api write helper is in exactly one of check 2's groups, and
    a RETURNS_NOTHING one has no `return <value>`: a helper is never left out of
    check 2 for a reason the code doesn't bear out (review rb-1)."""
    source = (INV_HUB / "spoolman_api.py").read_text(encoding="utf-8-sig")
    problems = helper_group_problems(source)
    assert not problems, helper_group_message(problems)


def test_every_watched_wrapper_still_writes():
    """Every WRAPPER_WRITERS entry is a top-level function of its backend module
    that writes, with a bare name of its own: a renamed wrapper would otherwise
    stop watching its callers with every check still green."""
    sources = {p.name: p.read_text(encoding="utf-8-sig") for p in backend_modules()}
    problems = wrapper_set_problems(sources, WRAPPER_WRITERS)
    assert not problems, (
        "WRAPPER_WRITERS entries that no longer hold:\n  " + "\n  ".join(problems)
        + f"\nIn {THIS_FILE}: point a renamed or moved wrapper's entry at its new "
          "\"module.function\" (and its callers' WRITE_SITES keys at the new callee). Take an "
          "entry out only when the function no longer writes, or now puts a failed write in "
          "the Activity Log itself; its callers' sites then go stale in WRITE_SITES, so remove "
          "them too."
    )


# ---------------------------------------------------------------------------
# Proofs: the scanner and the checks, fed synthetic input
# ---------------------------------------------------------------------------

def _sites(source, module="synthetic.py"):
    return find_write_sites(module, source)


def _keys(source, module="synthetic.py"):
    return count_sites(_sites(source, module))


def test_a_new_call_site_is_reported_as_unregistered():
    found = _keys(
        "import spoolman_api\n"
        "def handler(sid):\n"
        "    if not spoolman_api.update_spool(sid, {'location': ''}):\n"
        "        return spoolman_api.LAST_SPOOLMAN_ERROR\n"
    )
    new, stale = registry_problems(found, {})
    assert new == ["synthetic.py  handler  -> update_spool: 1 found, 0 registered"]
    assert stale == []
    message = registry_message(new, stale)
    for rule in ("compute_dirty_extras", "SYSTEM_MANAGED_EXTRAS", "LAST_SPOOLMAN_ERROR",
                 "_or_raise", "DELETE_EXTRA_SENTINEL", "re-read", "field-schema DELETE",
                 "write-surface table", "WRITE_SITES"):
        assert rule in message, f"the new-site message no longer mentions {rule!r}"
    # Registered, it passes.
    assert registry_problems(found, {("synthetic.py", "handler", "update_spool"): (1, "x")}) == ([], [])


def test_a_grown_site_is_reported_and_a_shrunk_one_is_stale():
    found = _keys(
        "import spoolman_api\n"
        "def handler(a, b):\n"
        "    ok = spoolman_api.update_spool(a, {}) and spoolman_api.update_spool(b, {})\n"
        "    return ok\n"
    )
    key = ("synthetic.py", "handler", "update_spool")
    assert found[key] == 2
    assert registry_problems(found, {key: (1, "x")})[0] == [
        "synthetic.py  handler  -> update_spool: 2 found, 1 registered"]
    assert registry_problems(found, {key: (3, "x")})[1] == [
        "synthetic.py  handler  -> update_spool: 3 registered, 2 found"]


def test_a_registered_site_missing_from_the_source_is_stale():
    found = _keys("import spoolman_api\ndef handler():\n    return spoolman_api.get_spool(1)\n")
    gone = ("synthetic.py", "handler", "update_filament")
    new, stale = registry_problems(found, {gone: (1, "handler")})
    assert new == []
    assert stale == ["synthetic.py  handler  -> update_filament: 1 registered, 0 found"]
    assert "Remove it from the registry" in registry_message(new, stale)


@pytest.mark.parametrize("value", [1, (0, "x"), (1,), (1, ""), ("1", "x"), (1, 2), (True, "x")])
def test_a_registry_entry_of_the_wrong_shape_says_how_to_write_it(value):
    key = ("synthetic.py", "handler", "update_spool")
    with pytest.raises(ValueError, match=r"Write it as .*count, \"doc anchor\" or None"):
        registry_problems({key: 1}, {key: value})
    with pytest.raises(ValueError, match="wrong shape"):
        anchor_problems({key: value}, "## Spool / Filament write surfaces\n")


def test_a_registry_key_of_the_wrong_shape_says_how_to_write_it():
    registry = {("synthetic.py", "handler", "update_spool"): (1, "handler"),
                "synthetic.py handler update_filament": (1, "handler")}
    with pytest.raises(ValueError, match="wrong shape"):
        registry_problems({}, registry)


def test_a_discarded_update_result_is_reported():
    offenders = silent_failures(_sites(
        "import spoolman_api\n"
        "def handler(sid):\n"
        "    spoolman_api.update_spool(sid, {'extra': {'a': 1}})\n"
    ))
    assert offenders == ["synthetic.py:3  handler  -> update_spool(...), its result thrown away"]
    message = silent_failure_message(offenders)
    assert "LAST_SPOOLMAN_ERROR" in message and "update_spool_or_raise" in message


def test_a_result_assigned_only_to_underscore_is_reported():
    offenders = silent_failures(_sites(
        "import spoolman_api\n"
        "def handler():\n"
        "    _ = spoolman_api.delete_spool(1)\n"
    ))
    assert offenders == ["synthetic.py:3  handler  -> delete_spool(...), its result thrown away"]


def test_an_awaited_result_thrown_away_is_reported():
    offenders = silent_failures(_sites(
        "import spoolman_api\n"
        "async def handler():\n"
        "    await spoolman_api.create_spool({})\n"
    ))
    assert offenders == ["synthetic.py:3  handler  -> create_spool(...), its result thrown away"]


def test_a_kept_or_raising_result_is_not_reported():
    sites = _sites(
        "import spoolman_api\n"
        "def handler(fid, sid):\n"
        "    spoolman_api.update_filament_or_raise(fid, {})\n"   # raises: fine as a statement
        "    spoolman_api.ensure_required_extras()\n"           # returns nothing: nothing to check
        "    res = spoolman_api.update_spool(sid, {})\n"
        "    if not spoolman_api.delete_spool(sid):\n"
        "        return res\n"
        "    return spoolman_api.update_vendor(1, {})\n"
    )
    assert len(sites) == 5
    assert silent_failures(sites) == []


def test_an_alias_a_from_import_and_a_bare_call_are_all_seen():
    found = _keys(
        "import spoolman_api as sa\n"
        "from spoolman_api import update_spool\n"
        "from spoolman_api import delete_filament as drop_filament\n"
        "def handler(fid, sid):\n"
        "    sa.update_filament(fid, {})\n"
        "    update_spool(sid, {})\n"
        "    return drop_filament(fid)\n"
    )
    assert found == {
        ("synthetic.py", "handler", "update_filament"): 1,
        ("synthetic.py", "handler", "update_spool"): 1,
        ("synthetic.py", "handler", "delete_filament"): 1,
    }


def test_a_writer_handed_on_as_a_value_is_seen():
    sites = _sites(
        "import threading\n"
        "import spoolman_api\n"
        "def handler(sid):\n"
        "    threading.Thread(target=spoolman_api.update_spool, args=(sid, {})).start()\n"
    )
    assert count_sites(sites) == {("synthetic.py", "handler", "update_spool (as a value)"): 1}
    assert _writer(sites[0].callee) == "update_spool"


def test_direct_http_writes_are_seen_with_their_target():
    found = _keys(
        "import requests\n"
        "import http_retry\n"
        "def handler(u, i, sm):\n"
        "    requests.patch(f\"{u}/api/v1/spool/{i}\", json={}, timeout=5)\n"
        "    http_retry.request_with_retry('patch', '%s/api/v1/filament/%s' % (sm, i), json={})\n"
        "    requests.request('DELETE', u + '/api/v1/vendor/' + str(i), timeout=5)\n"
        "    requests.post(f'{u}/api/v1/field/spool/key', json={}, timeout=5)\n"
        "    getattr(requests, 'put')('http://printer/api/job', timeout=5)\n"
        "    requests.get(f'{u}/api/v1/spool/{i}', timeout=5)\n"                       # a read
        "    http_retry.request_with_retry('get', f'{u}/api/v1/filament', timeout=5)\n" # a read
    )
    assert found == {
        ("synthetic.py", "handler", "HTTP PATCH spool"): 1,
        ("synthetic.py", "handler", "HTTP PATCH filament"): 1,
        ("synthetic.py", "handler", "HTTP DELETE vendor"): 1,
        ("synthetic.py", "handler", "HTTP POST field"): 1,
        ("synthetic.py", "handler", "HTTP PUT other"): 1,
    }


def test_an_aliased_requests_and_a_verb_it_cant_read_are_seen():
    found = _keys(
        "def handler(verb, url):\n"
        "    import requests as _req\n"
        "    from http_retry import request_with_retry as retry\n"
        "    _req.delete(url, timeout=5)\n"
        "    retry(verb, url, timeout=5)\n"
        "    return getattr(_req, verb)(url, timeout=5)\n"
    )
    assert found == {
        ("synthetic.py", "handler", "HTTP DELETE other"): 1,
        ("synthetic.py", "handler", "HTTP ? other"): 2,
    }


def test_a_lookalike_receiver_is_not_an_http_write():
    assert _keys(
        "import some_other_lib as _req\n"
        "def handler(session):\n"
        "    _req.patch('http://x/api/v1/spool/1')\n"
        "    session.post('http://x/api/v1/spool')\n"
    ) == {}


def test_qualified_names_name_the_enclosing_function():
    found = _keys(
        "import spoolman_api\n"
        "spoolman_api.ensure_required_extras()\n"
        "def outer(sid):\n"
        "    def inner():\n"
        "        return spoolman_api.update_spool(sid, {})\n"
        "    return inner()\n"
        "class Writer:\n"
        "    def save(self, fid):\n"
        "        return spoolman_api.update_filament(fid, {})\n"
        "    keep = lambda self, vid: spoolman_api.update_vendor(vid, {})\n"
    )
    assert set(found) == {
        ("synthetic.py", "<module>", "ensure_required_extras"),
        ("synthetic.py", "outer.inner", "update_spool"),
        ("synthetic.py", "Writer.save", "update_filament"),
        ("synthetic.py", "Writer.<lambda>", "update_vendor"),
    }


def test_an_anchor_missing_from_the_section_is_reported():
    section = write_surface_section(
        "# Intro\n"
        "## Spool / Filament write surfaces\r\n"
        "| `logic.py` | `known_writer` | Notes |\r\n"
        "### Weight-entry surfaces (known fragmentation hot-spot)\r\n"
        "| `x.py` | `after_the_section` | not part of it |\n"
    )
    registry = {
        ("logic.py", "known_writer", "update_spool"): (1, "known_writer"),
        ("logic.py", "unknown_writer", "update_spool"): (1, "unknown_writer"),
        ("logic.py", "after_the_section", "update_spool"): (1, "after_the_section"),
        ("logic.py", "unanchored", "update_filament_or_raise"): (1, None),
        ("logic.py", "a_create", "create_spool"): (1, None),      # optional: fine
        ("logic.py", "a_named_delete", "delete_spool"): (1, "nowhere"),  # given: checked
    }
    assert anchor_problems(registry, section) == [
        "logic.py  a_named_delete  -> delete_spool: 'nowhere' is not in the section",
        "logic.py  after_the_section  -> update_spool: 'after_the_section' is not in the section",
        "logic.py  unanchored  -> update_filament_or_raise: no doc anchor",
        "logic.py  unknown_writer  -> update_spool: 'unknown_writer' is not in the section",
    ]
    assert "Add a row to the table" in anchor_message(["x"])


def test_a_write_helpers_own_name_anchors_only_a_site_inside_that_helper():
    # The section's opening lines name update_spool for every site, so as an
    # anchor it would hold whatever the table says.
    section = write_surface_section(
        "## Spool / Filament write surfaces\n"
        "Every code path that calls `spoolman_api.update_spool` or `update_filament` ...\n"
        "- `update_spool_or_raise` raises instead of returning None.\n"
        "### Weight-entry surfaces\n"
    )
    registry = {
        ("routes_x.py", "api_new_thing", "update_spool"): (1, "update_spool"),
        ("spoolman_api.py", "update_spool_or_raise", "update_spool"): (1, "update_spool_or_raise"),
    }
    assert anchor_problems(registry, section) == [
        "routes_x.py  api_new_thing  -> update_spool: 'update_spool' is a write helper's name, "
        "which the section holds for every site; anchor it to its function or endpoint",
    ]


def test_a_moved_or_renamed_section_fails_with_where_to_point():
    with pytest.raises(SectionMissing, match="moved or was renamed"):
        write_surface_section("## Spool and Filament writes\n### Weight-entry surfaces\n")
    with pytest.raises(SectionMissing, match="SECTION_END"):
        write_surface_section("## Spool / Filament write surfaces\n| a | b | c |\n## Next\n")


def test_a_new_writer_in_spoolman_api_must_be_listed():
    source = (
        "import requests\n"
        "def update_spool(sid, data):\n"
        "    return requests.patch(f'u/api/v1/spool/{sid}', json=data, timeout=5)\n"
        "def update_spool_or_raise(sid, data):\n"
        "    return update_spool(sid, data)\n"
        "def archive_spool(sid):\n"
        "    return requests.put(f'u/api/v1/spool/{sid}', json={}, timeout=5)\n"
        "def get_spool(sid):\n"
        "    return requests.get(f'u/api/v1/spool/{sid}', timeout=5)\n"
    )
    listed = frozenset({"update_spool", "update_spool_or_raise", "update_filament"})
    unlisted, not_writers = writer_set_problems(source, listed)
    assert unlisted == ["archive_spool (HTTP PUT spool)"]
    assert not_writers == ["update_filament (not defined)"]


# --- update_extra_field_choices is under check 2 (review r4-1) ----------------

def test_a_thrown_away_field_choices_result_is_reported():
    # It answers {"success": False, "msg": ...} on a refused field-list read, a
    # key with no choices and a refused POST, and logs none of them, so a route
    # that drops it answers success over a choice that was never added.
    offenders = silent_failures(_sites(
        "import spoolman_api\n"
        "def api_new_choice(choice):\n"
        "    spoolman_api.update_extra_field_choices('filament', 'filament_attributes', [choice])\n"
        "    return {'success': True}\n"
    ))
    assert offenders == [
        "synthetic.py:3  api_new_choice  -> update_extra_field_choices(...), its result thrown away"]
    assert 'res.get("success")' in silent_failure_message(offenders)
    # The two field-schema helpers that return nothing leave a caller nothing to
    # check: a bare call is fine. (ensure_extra_field returns False: review rb-1,
    # below.)
    assert silent_failures(_sites(
        "import spoolman_api\n"
        "def boot():\n"
        "    spoolman_api.ensure_required_extras()\n"
        "    spoolman_api.ensure_filament_attributes_cleaned()\n"
    )) == []


def test_check_2_says_what_to_do_for_each_helper_it_reports():
    assert set(HOW_IT_FAILS) == set(FAILS_BY_RETURN_VALUE)
    offenders = [f"synthetic.py:1  handler  -> {name}(...), its result thrown away"
                 for name in sorted(FAILS_BY_RETURN_VALUE)]
    message = silent_failure_message(offenders)
    for name in FAILS_BY_RETURN_VALUE:
        assert f"  - {name} {HOW_IT_FAILS[name]}." in message
    # Only the helpers it reports: one offender, one line of advice.
    one = silent_failure_message(["x.py:1  f  -> logic._move_write(...), its result thrown away"])
    assert "  - logic._move_write " in one and "restore_extras" not in one


# --- FCC's own write wrappers (review r5-3, r3-7) ------------------------------

def test_a_wrappers_calls_are_write_sites_wherever_they_are():
    # Inside its own module: a bare call.
    assert _keys(
        "import spoolman_api\n"
        "def _move_write(sid, target, extra):\n"
        "    return spoolman_api.update_spool(sid, {'location': target, 'extra': extra})\n"
        "def _new_surface(sid):\n"
        "    return _move_write(sid, 'UNKNOWN', {})\n",
        module="logic.py") == {
        ("logic.py", "_move_write", "update_spool"): 1,
        ("logic.py", "_new_surface", "logic._move_write"): 1,
    }
    # Elsewhere: through the module, an alias of it, a from-import (a star import
    # binds only public names), and handed on as a value.
    assert _keys(
        "import threading\n"
        "import logic\n"
        "import logic as lg\n"
        "import attr_migration\n"
        "from logic import _swap_out_write as swap_out\n"
        "from logic import *\n"
        "def handler(sid, url, payloads, rec, rows):\n"
        "    ok = logic._move_write(sid, '', {})\n"
        "    parked = lg._audit_park_one(sid, 'BOX', '2026-11-09', {}, {})\n"
        "    out = attr_migration.restore_extras(url, payloads)\n"
        "    moved = swap_out(sid, rec, 'BOX', '1', {})\n"
        "    cascade = perform_toolhead_delete_cascade('HEAD', rows)\n"
        "    threading.Thread(target=logic._undo_filed, args=({}, {}, [])).start()\n"
        "    return ok, parked, out, moved, cascade\n",
        module="routes_x.py") == {
        ("routes_x.py", "handler", "logic._move_write"): 1,
        ("routes_x.py", "handler", "logic._audit_park_one"): 1,
        ("routes_x.py", "handler", "attr_migration.restore_extras"): 1,
        ("routes_x.py", "handler", "logic._swap_out_write"): 1,
        ("routes_x.py", "handler", "logic.perform_toolhead_delete_cascade"): 1,
        ("routes_x.py", "handler", "logic._undo_filed (as a value)"): 1,
    }


def test_a_wrappers_bare_name_elsewhere_is_that_modules_own_function():
    # No import binds it, so it is routes_x.py's own _move_write, not logic's;
    # and `from logic import *` doesn't bind a name that starts with "_".
    assert _keys(
        "from logic import *\n"
        "def _move_write(sid):\n"
        "    return sid\n"
        "def handler(sid):\n"
        "    _move_write(sid)\n"
        "    return _audit_file_one(sid, 'BOX', 'X', {}, {})\n",
        module="routes_x.py") == {}


def test_a_thrown_away_wrapper_result_is_reported_and_a_kept_one_is_not():
    sites = _sites(
        "import logic\n"
        "import attr_migration\n"
        "def handler(sid, url, payloads, rows):\n"
        "    logic._move_write(sid, 'UNKNOWN', {})\n"
        "    _ = attr_migration.restore_extras(url, payloads)\n"
        "    if not logic._move_write(sid, '', {}):\n"
        "        return 'failed'\n"
        "    result = logic.perform_toolhead_delete_cascade('HEAD', rows)\n"
        "    return result['errors']\n",
        module="routes_x.py")
    assert count_sites(sites) == {
        ("routes_x.py", "handler", "logic._move_write"): 2,
        ("routes_x.py", "handler", "attr_migration.restore_extras"): 1,
        ("routes_x.py", "handler", "logic.perform_toolhead_delete_cascade"): 1,
    }
    offenders = silent_failures(sites)
    assert offenders == [
        "routes_x.py:4  handler  -> logic._move_write(...), its result thrown away",
        "routes_x.py:5  handler  -> attr_migration.restore_extras(...), its result thrown away",
    ]
    message = silent_failure_message(offenders)
    assert "report_restore_failures" in message and "LAST_SPOOLMAN_ERROR" in message
    assert "perform_toolhead_delete_cascade" not in message


def test_a_wrappers_own_name_anchors_only_a_site_inside_that_wrapper():
    # The section names _move_write in the rows of the functions that call it,
    # so as an anchor it would hold for any new caller.
    section = write_surface_section(
        "## Spool / Filament write surfaces\n"
        "| `logic.py` | `_perform_smart_move_impl` | its writes go through `_move_write` |\n"
        "### Weight-entry surfaces\n"
    )
    registry = {
        ("logic.py", "_move_write", "update_spool"): (1, "_move_write"),          # inside it: fine
        ("logic.py", "_new_thing", "logic._move_write"): (1, "_move_write"),
        ("logic.py", "_newer_thing", "logic._move_write"): (1, "logic._move_write"),
        ("logic.py", "_perform_smart_move_impl", "logic._move_write"): (3, "_perform_smart_move_impl"),
        ("logic.py", "_unnamed", "logic._move_write"): (1, None),                  # optional: fine
    }
    held = ("is a wrapper's own name, not the site's; anchor it to its function or endpoint, "
            "or give it None (its anchor is optional)")
    assert anchor_problems(registry, section) == [
        f"logic.py  _new_thing  -> logic._move_write: '_move_write' {held}",
        f"logic.py  _newer_thing  -> logic._move_write: 'logic._move_write' {held}",
    ]
    # On a site that must have an anchor, a wrapper's name is refused the same
    # way, and None isn't offered.
    assert anchor_problems(
        {("logic.py", "_new_thing", "update_spool"): (1, "_move_write")}, section) == [
        "logic.py  _new_thing  -> update_spool: '_move_write' is a wrapper's own name, not the "
        "site's; anchor it to its function or endpoint"]


def test_a_renamed_or_stale_wrapper_is_reported():
    sources = {
        "logic.py": (
            "import spoolman_api\n"
            "def _move_write(sid, target, extra):\n"
            "    return spoolman_api.update_spool(sid, {'location': target, 'extra': extra})\n"
            "def _audit_park_one(sid):\n"
            "    return _move_write(sid, 'UNKNOWN', {})\n"   # writes through another wrapper
            "def _undo_filed(record):\n"
            "    return {}\n"),                              # no longer writes
        "attr_migration.py": "def restore_extras_v2(url, payloads):\n    return 0, [], 0\n",
    }
    wrappers = {
        "logic._move_write": "", "logic._audit_park_one": "", "logic._undo_filed": "",
        "attr_migration.restore_extras": "",              # renamed
        "gone.helper": "",                                # its module is gone
        "logic.update_spool": "",                         # a spoolman_api helper's bare name
    }
    assert wrapper_set_problems(sources, wrappers) == [
        "attr_migration.restore_extras: attr_migration.py defines no top-level function "
        "restore_extras (renamed or removed?)",
        "gone.helper: gone.py is not a backend module (inventory-hub/*.py)",
        "logic._undo_filed: _undo_filed has no write site inside it any more: it no longer "
        "writes, or writes only through a helper this file doesn't watch (a renamed wrapper?)",
        "logic.update_spool: its bare name 'update_spool' is also another write helper's or wrapper's",
        "logic.update_spool: logic.py defines no top-level function update_spool (renamed or removed?)",
    ]


# --- requests reached through another module, and requests.api (review r4-4) --

def test_requests_through_another_module_and_requests_api_are_seen():
    found = _keys(
        "import requests\n"
        "import requests.api as rapi\n"
        "from requests import api as api2\n"
        "from requests.api import put as api_put\n"
        "import spoolman_api\n"
        "import attr_migration\n"
        "def handler(u, i):\n"
        "    spoolman_api.requests.patch(f'{u}/api/v1/spool/{i}', json={}, timeout=5)\n"
        "    spoolman_api.requests.request('DELETE', f'{u}/api/v1/vendor/{i}', timeout=5)\n"
        "    getattr(spoolman_api.requests, 'post')(f'{u}/api/v1/field/spool/k', json={}, timeout=5)\n"
        "    requests.api.post(f'{u}/api/v1/filament', json={}, timeout=5)\n"
        "    spoolman_api.requests.api.delete(f'{u}/api/v1/spool/{i}', timeout=5)\n"
        "    rapi.patch(f'{u}/api/v1/filament/{i}', json={}, timeout=5)\n"
        "    api2.post(f'{u}/api/v1/vendor', json={}, timeout=5)\n"
        "    api_put('http://printer/api/job', timeout=5)\n"
        "    attr_migration.http_retry.request_with_retry('patch', f'{u}/api/v1/filament/{i}', json={})\n"
        "    spoolman_api.requests.get(f'{u}/api/v1/spool/{i}', timeout=5)\n"          # a read
        "    requests.api.get(f'{u}/api/v1/spool', timeout=5)\n"                       # a read
    )
    assert found == {
        ("synthetic.py", "handler", "HTTP PATCH spool"): 1,
        ("synthetic.py", "handler", "HTTP DELETE vendor"): 1,
        ("synthetic.py", "handler", "HTTP POST field"): 1,
        ("synthetic.py", "handler", "HTTP POST filament"): 1,
        ("synthetic.py", "handler", "HTTP DELETE spool"): 1,
        ("synthetic.py", "handler", "HTTP PATCH filament"): 2,
        ("synthetic.py", "handler", "HTTP POST vendor"): 1,
        ("synthetic.py", "handler", "HTTP PUT other"): 1,
    }
    # An `api` or `session` attribute that isn't reached through requests is not one.
    assert _keys(
        "class Client:\n"
        "    def go(self, u):\n"
        "        self.api.post(u + '/api/v1/spool')\n"
        "        return self.session.patch(u + '/api/v1/spool/1')\n"
    ) == {}


# --- ensure_extra_field is under check 2; the boot's drops are allowed (review rb-1) --

def test_a_thrown_away_ensure_extra_field_result_is_reported():
    # It answers False when the field isn't registered and Spoolman refused it or
    # didn't answer, with one hub.log WARNING and no LAST_SPOOLMAN_ERROR: the
    # record helpers' shape. A route that drops it answers success over a field
    # Spoolman doesn't have, and every later write carrying that extra is refused.
    offenders = silent_failures(_sites(
        "import spoolman_api\n"
        "def api_register_field(key):\n"
        "    spoolman_api.ensure_extra_field('spool', key, key)\n"
        "    return {'success': True}\n"
    ))
    assert offenders == [
        "synthetic.py:3  api_register_field  -> ensure_extra_field(...), its result thrown away"]
    message = silent_failure_message(offenders)
    assert f"  - ensure_extra_field {HOW_IT_FAILS['ensure_extra_field']}." in message
    assert "sets no LAST_SPOOLMAN_ERROR" in HOW_IT_FAILS["ensure_extra_field"]
    assert "ALLOWED_DISCARDS" in message
    # Kept and checked, it passes.
    assert silent_failures(_sites(
        "import spoolman_api\n"
        "def api_register_field(key):\n"
        "    if not spoolman_api.ensure_extra_field('spool', key, key):\n"
        "        return {'success': False, 'msg': f'Spoolman would not register {key}'}\n"
        "    return {'success': True}\n"
    )) == []


BOOT_KEY = ("spoolman_api.py", "ensure_required_extras", "ensure_extra_field")


def _boot_sites(dropped, kept=0, module="spoolman_api.py"):
    """A boot registration with `dropped` bare ensure_extra_field calls, then
    `kept` more whose result it keeps."""
    return _sites(
        "def ensure_extra_field(entity, key, name):\n"
        "    return False\n"
        "def ensure_required_extras():\n"
        + "".join(f"    ensure_extra_field('spool', 'k{i}', 'K{i}')\n" for i in range(dropped))
        + "".join(f"    ok{i} = ensure_extra_field('vendor', 'v{i}', 'V{i}')\n" for i in range(kept)),
        module=module)


def test_an_allowed_discard_passes_and_one_more_is_reported():
    allowed = {BOOT_KEY: (3, "the boot registration's best effort")}
    assert silent_failures(_boot_sites(3), allowed) == []
    assert silent_failures(_boot_sites(3, kept=2), allowed) == []
    # One more than allowed: every one at that site is listed, with both counts.
    offenders = silent_failures(_boot_sites(4), allowed)
    assert offenders == [
        f"spoolman_api.py:{4 + i}  ensure_required_extras  -> ensure_extra_field(...), its result "
        "thrown away (4 thrown away here, ALLOWED_DISCARDS allows 3)" for i in range(4)]
    message = silent_failure_message(offenders)
    assert "  - ensure_extra_field returns False" in message
    assert "raise its count only" in message
    # Without the entry each one is reported; and an entry is for its own site only.
    assert len(silent_failures(_boot_sites(3), {})) == 3
    assert len(silent_failures(_boot_sites(3, module="routes_x.py"), allowed)) == 3
    # The real ALLOWED_DISCARDS is the default.
    assert silent_failures(_boot_sites(ALLOWED_DISCARDS[BOOT_KEY][0])) == []


def test_a_stale_allowance_is_reported():
    sites = _boot_sites(2, kept=1)
    assert allowance_problems(sites, {BOOT_KEY: (2, "boot")}) == []
    assert allowance_problems(sites, {BOOT_KEY: (3, "boot")}) == [
        "spoolman_api.py  ensure_required_extras  -> ensure_extra_field: ALLOWED_DISCARDS allows 3 "
        "thrown-away call(s), 2 found: lower its count to 2"]
    gone = ("routes_x.py", "api_old", "ensure_extra_field")
    not_checked = ("spoolman_api.py", "ensure_required_extras", "update_spool_or_raise")
    assert allowance_problems(sites, {BOOT_KEY: (2, "boot"), gone: (1, "it was here"),
                                      not_checked: (1, "it raises")}) == [
        "routes_x.py  api_old  -> ensure_extra_field: ALLOWED_DISCARDS allows 1 thrown-away "
        "call(s), 0 found: remove it",
        "spoolman_api.py  ensure_required_extras  -> update_spool_or_raise: check 2 doesn't report "
        "this callee (it isn't in FAILS_BY_RETURN_VALUE): remove it",
    ]
    # Calls that keep their result now leave the entry nothing to allow.
    assert allowance_problems(_boot_sites(0, kept=3), {BOOT_KEY: (3, "boot")}) == [
        "spoolman_api.py  ensure_required_extras  -> ensure_extra_field: ALLOWED_DISCARDS allows 3 "
        "thrown-away call(s), 0 found: remove it"]
    assert "Remove one whose calls are gone" in allowance_message(["x"])


@pytest.mark.parametrize("value", [(3, ""), (3, "   "), (3, None), 3, (0, "why"), (True, "why"),
                                   ("3", "why"), (3,), (3, "why", "more")])
def test_an_allowance_of_the_wrong_shape_or_with_no_reason_says_how_to_write_it(value):
    with pytest.raises(ValueError, match=r"Write it as .*why its result may be thrown away"):
        allowance_problems(_boot_sites(3), {BOOT_KEY: value})
    with pytest.raises(ValueError, match="wrong shape"):
        silent_failures(_boot_sites(3), {BOOT_KEY: value})


def test_an_allowance_key_of_the_wrong_shape_says_how_to_write_it():
    with pytest.raises(ValueError, match="wrong shape"):
        allowance_problems([], {"spoolman_api.py ensure_required_extras ensure_extra_field": (3, "why")})


def test_a_helper_check_2_cannot_place_is_reported():
    source = (
        "def ensure_a():\n"
        "    for k in ('a', 'b'):\n"
        "        if not k:\n"
        "            return\n"
        "    def inner():\n"
        "        return True\n"              # a nested def's return is its own
        "    return None\n"
        "def ensure_b(key):\n"
        "    if key:\n"
        "        return False\n"
        "    return\n"
        "def new_writer():\n"
        "    return True\n"
    )
    helpers = {"ensure_a", "ensure_b", "new_writer", "update_spool", "update_spool_or_raise"}
    assert helper_group_problems(source, helpers, returns_nothing={"ensure_a", "ensure_b", "gone"}) == [
        "ensure_b: in RETURNS_NOTHING, but it returns a value (spoolman_api.py:10)",
        "gone: in RETURNS_NOTHING, but it isn't a write helper (WRITE_FUNCTIONS)",
        "new_writer: in none of FAILS_BY_RETURN_VALUE, RAISING_UPDATES and RETURNS_NOTHING",
    ]
    assert helper_group_problems(source, {"update_spool"}, returns_nothing={"update_spool"}) == [
        "update_spool: in FAILS_BY_RETURN_VALUE and RETURNS_NOTHING"]
    assert "HOW_IT_FAILS" in helper_group_message(["x"])


# --- What the docstring says the scanner can't see, and counts anyway (review rb-5) --

LIMITS_CHANGED = (
    "The scanner's limits changed. Bring the docstring's \"Not seen\" list and its "
    f"\"Counted, though ...\" paragraph in {THIS_FILE} up to date, and CLAUDE.md's write-site "
    "bullet under Testing (its \"It can't see\" and over-count sentences), then this case.")


@pytest.mark.parametrize("source", [
    "import spoolman_api\ndef h(u, i):\n    rq = spoolman_api.requests\n"
    "    rq.patch(f'{u}/api/v1/spool/{i}')\n",
    "import requests\nhttp = requests\ndef h(u, i):\n    http.delete(f'{u}/api/v1/spool/{i}')\n",
    "from spoolman_api import requests\ndef h(u, i):\n    requests.patch(f'{u}/api/v1/spool/{i}')\n",
    "from attr_migration import http_retry\ndef h(u, i):\n"
    "    http_retry.request_with_retry('patch', f'{u}/api/v1/spool/{i}')\n",
    "import http_retry\ndef h(u, i):\n    rr = http_retry.request_with_retry\n"
    "    rr('patch', f'{u}/api/v1/spool/{i}')\n",
    "import requests\ndef h(u, new):\n    send = requests.post if new else requests.patch\n"
    "    send(u + '/api/v1/spool')\n",
    "import requests\ndef h(u):\n    s = requests.Session()\n    s.patch(u + '/api/v1/spool/1')\n",
    "import urllib.request\ndef h(u):\n"
    "    urllib.request.urlopen(urllib.request.Request(u + '/api/v1/spool/1', method='PATCH'))\n",
    "import http.client\ndef h(host):\n    c = http.client.HTTPConnection(host)\n"
    "    c.request('PATCH', '/api/v1/spool/1')\n",
    "import spoolman_api\ndef h(i):\n    getattr(spoolman_api, 'update_spool')(i, {})\n",
], ids=["requests-by-assignment", "module-alias-by-assignment", "requests-from-a-backend-module",
        "http_retry-from-a-backend-module", "retry-helper-by-assignment", "verb-in-a-variable",
        "session", "urllib", "http-client", "getattr-on-spoolman_api"])
def test_a_documented_blind_spot_is_not_seen(source):
    assert _keys(source, module="routes_x.py") == {}, LIMITS_CHANGED


@pytest.mark.parametrize("source,callee", [
    ("class Registry:\n    def drop(self, rid):\n        return self.requests.delete(rid)\n",
     "HTTP DELETE other"),
    ("def h(cache, u):\n    return cache.http_retry.request_with_retry('post', u)\n", "HTTP POST other"),
    ("def h(cache, sid, x):\n    return cache.update_spool(sid, x)\n", "update_spool"),
    ("def h(backup, rows):\n    return backup.restore_extras(rows)\n", "attr_migration.restore_extras"),
], ids=["a-requests-attribute", "an-http_retry-attribute", "a-write-helpers-name",
        "a-wrappers-name"])
def test_a_documented_over_count_is_counted(source, callee):
    assert [s.callee for s in _sites(source, module="routes_x.py")] == [callee], LIMITS_CHANGED
