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
  2. No silent failure. A record helper that reports a rejection only by its
     return value (update_* / create_* / delete_*, not the `_or_raise` forms,
     which raise) must not have that result thrown away: a bare statement, an
     `await` of it as a statement, or an assignment only to `_`. The
     field-schema helpers are outside this rule because they handle and log
     their own failures inside; a direct HTTP call is too, because its
     failure is the caller's own check of the response.
  3. The table is honest. Every record-update site carries a doc anchor, a
     string CLAUDE.md's write-surface section must hold (from the line
     "## Spool / Filament write surfaces" to "### Weight-entry surfaces"):
     normally the enclosing function's name, or its endpoint as the table
     writes it. This is the first test that reads CLAUDE.md (Derek's OK,
     2026-11-09).
  And WRITE_FUNCTIONS is kept equal to the spoolman_api functions that write,
  so a new writer there is watched from its first call.

What counts as a write call site:
  * A use of one of spoolman_api's write helpers (WRITE_FUNCTIONS): the record
    updates (update_spool / update_filament / update_vendor and their
    `_or_raise` forms), the record creates and deletes, and the field-schema
    writes. It is seen as `spoolman_api.<name>(...)`, through any other
    receiver (an alias by import or by assignment), as a bare `<name>(...)`
    (inside spoolman_api itself; anywhere else that would be a
    `from spoolman_api import <name>`, which CLAUDE.md forbids, so it is still
    seen rather than left to hide), under a `from spoolman_api import <name>
    as <alias>` alias, and as a value handed on uncalled (a thread's target):
    callee "<name> (as a value)".
  * A direct HTTP write in any module, spoolman_api included:
    `<requests alias>.post / patch / put / delete(...)`, `.request(<verb>, ...)`
    with anything but a read verb, `http_retry.request_with_retry(<verb>, ...)`
    likewise, and `getattr(<requests alias>, <verb>)(...)`. The callee reads
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
out, as the image's .dockerignore leaves them out. Out of scope:
setup-and-rebuild/setup_fields.py, a deploy tool with its own tests
(test_setup_fields_migration_54_4.py, test_setup_fields_idempotent.py), and
the repo-root scripts.

Not seen: a requests Session (none in the backend; a test's patch of
`requests.<verb>` can't reach one either), urllib / http.client, a URL built
outside the call, and a helper reached through getattr(spoolman_api, ...). A
wrapper outside spoolman_api (logic._move_write, attr_migration.restore_extras)
is registered at the write inside it; its callers are not listed.

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
# Check 2: these report a rejection only by their return value (None, or
# False from delete_*).
FAILS_BY_RETURN_VALUE = RECORD_UPDATES | CREATES_AND_DELETES
# Check 3: these sites must be named in CLAUDE.md's write-surface table.
NEEDS_DOC_ANCHOR = RECORD_UPDATES | RAISING_UPDATES

HTTP_READ_VERBS = frozenset({"get", "head", "options"})
HTTP_VERB_FUNCS = frozenset({"get", "head", "options", "post", "patch", "put", "delete"})
AS_VALUE = " (as a value)"

Site = collections.namedtuple("Site", "module function callee line discarded")


# ---------------------------------------------------------------------------
# The registry: (module, function, callee): (count, doc anchor).
#
# The doc anchor is a string CLAUDE.md's write-surface section holds, so the
# table can't lose a surface unnoticed (check 3). Every update_* site has one;
# a create, delete, field-schema or HTTP site has one where a row names it,
# else None.
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
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice", "HTTP DELETE field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_remove_choice", "HTTP POST field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_sweep_unused", "HTTP DELETE field"): (1, None),
    ("routes_config_attrs.py", "api_filament_attributes_sweep_unused", "HTTP POST field"): (1, None),

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
    """The names one module binds to requests, http_retry and spoolman_api's writers."""

    def __init__(self, tree):
        self.requests = set()        # import requests [as x]
        self.requests_funcs = {}     # from requests import post [as p] -> {"p": "post"}
        self.retry = set()           # import http_retry [as x]
        self.retry_funcs = set()     # from http_retry import request_with_retry [as r]
        self.writers = {}            # from spoolman_api import update_spool [as us] -> {"us": "update_spool"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "requests":
                        self.requests.add(a.asname or "requests")
                    elif a.name.startswith("requests.") and not a.asname:
                        self.requests.add("requests")   # `import requests.x` binds `requests`
                    elif a.name == "http_retry":
                        self.retry.add(a.asname or "http_retry")
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    local = a.asname or a.name
                    if node.module == "requests":
                        if a.name == "*":
                            self.requests_funcs.update({v: v for v in HTTP_VERB_FUNCS | {"request"}})
                        elif a.name in HTTP_VERB_FUNCS or a.name == "request":
                            self.requests_funcs[local] = a.name
                    elif node.module == "http_retry":
                        if a.name in ("request_with_retry", "*"):
                            self.retry_funcs.add("request_with_retry" if a.name == "*" else local)
                    elif node.module == "spoolman_api" and a.name in WRITE_FUNCTIONS:
                        self.writers[local] = a.name


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
    """The spoolman_api helper a callee names, or None for an HTTP site."""
    name = callee[:-len(AS_VALUE)] if callee.endswith(AS_VALUE) else callee
    return name if name in WRITE_FUNCTIONS else None


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

    # -- spoolman_api's writers ----------------------------------------------
    def _writer_named(self, node):
        if isinstance(node, ast.Attribute) and node.attr in WRITE_FUNCTIONS:
            return node.attr
        if isinstance(node, ast.Name):
            if node.id in self._b.writers:
                return self._b.writers[node.id]
            if node.id in WRITE_FUNCTIONS:
                return node.id
        return None

    def visit_Attribute(self, node):
        self._value_use(node)
        self.generic_visit(node)

    def visit_Name(self, node):
        self._value_use(node)

    def _value_use(self, node):
        """A writer named without being called: handed on as a value."""
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

    def _http_call(self, node):
        """(verb, URL node) when `node` is an HTTP call, else None."""
        func, b = node.func, self._b
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            receiver = func.value.id
            if receiver in b.requests:
                if func.attr in HTTP_VERB_FUNCS:
                    return func.attr, _arg(node, 0, "url")
                if func.attr == "request":
                    return _verb(_arg(node, 0, "method")), _arg(node, 1, "url")
            if receiver in b.retry and func.attr == "request_with_retry":
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
                and isinstance(func.args[0], ast.Name) and func.args[0].id in b.requests):
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
    """The registry's entries, sorted, each checked for its shape:
    (module, function, callee): (count of 1 or more, doc anchor or None)."""
    for key, value in sorted(registry.items()):
        ok = (isinstance(key, tuple) and len(key) == 3 and all(isinstance(k, str) for k in key)
              and isinstance(value, tuple) and len(value) == 2
              and isinstance(value[0], int) and value[0] >= 1
              and (value[1] is None or (isinstance(value[1], str) and value[1].strip())))
        if not ok:
            raise ValueError(
                f"WRITE_SITES entry {key!r}: {value!r} has the wrong shape. Write it as "
                '("module.py", "function", "callee"): (count, "doc anchor" or None), '
                "with a count of 1 or more.")
        yield key, value


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


def silent_failures(sites):
    """The calls of a return-value-failing record helper whose result is thrown away."""
    return [
        f"{s.module}:{s.line}  {s.function}  -> {s.callee}(...), its result thrown away"
        for s in sites
        if s.discarded and s.callee in FAILS_BY_RETURN_VALUE
    ]


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


def missing_anchors(registry, section):
    """The registered sites whose doc anchor the section doesn't hold, and the
    record-update sites with no anchor at all."""
    out = []
    for key, (_n, doc) in _entries(registry):
        if doc is None:
            if _writer(key[2]) in NEEDS_DOC_ANCHOR:
                out.append(f"{_key_text(key)}: no doc anchor")
        elif doc not in section:
            out.append(f"{_key_text(key)}: {doc!r} is not in the section")
    return out


def writer_set_problems(source, listed):
    """For spoolman_api.py's source: ([writers missing from `listed`, with what
    each writes through], [listed names that aren't writers there]). A writer is
    a top-level function with a write in it: an HTTP write, or a use of one of
    WRITE_FUNCTIONS."""
    writes = collections.defaultdict(set)
    for s in find_write_sites("spoolman_api.py", source):
        writes[s.function.split(".")[0]].add(s.callee)
    defined = {n.name for n in ast.parse(source).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    unlisted = [f"{f} ({', '.join(sorted(writes[f]))})" for f in sorted(set(writes) - listed)]
    not_writers = [f if f in defined else f"{f} (not defined)" for f in sorted(listed - set(writes))]
    return unlisted, not_writers


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
Then register it in WRITE_SITES in {THIS_FILE}, under its module:
    ("module.py", "function", "callee"): (count, "doc anchor"),
where the doc anchor is a string the table holds (the function's name, or its endpoint as the
table writes it); it is required for update_* sites and may be None for the others.
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


def silent_failure_message(offenders):
    return (
        "A Spoolman write's result is thrown away, so a rejection goes unseen (the class of "
        "bug behind the 2026-04-26/27 prod outages):\n  " + "\n  ".join(offenders)
        + "\n\nThese helpers report a rejection only by returning None (False from delete_*). "
          "Keep the result and check it: on a falsy answer read spoolman_api.LAST_SPOOLMAN_ERROR "
          "and log it (state.add_log_entry(..., \"ERROR\", \"ff4444\")) or return it so the page "
          "toasts it at 7 s. Or call the _or_raise form (update_spool_or_raise / "
          "update_filament_or_raise / update_vendor_or_raise), which raises "
          "spoolman_api.SpoolmanRejection."
    )


def anchor_message(missing):
    return (
        "CLAUDE.md's write-surface table doesn't name these registered sites:\n  "
        + "\n  ".join(missing)
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


def test_the_write_surface_table_names_every_update_site():
    try:
        section = write_surface_section(CLAUDE_MD.read_text(encoding="utf-8"))
    except SectionMissing as e:
        pytest.fail(str(e))
    missing = missing_anchors(WRITE_SITES, section)
    assert not missing, anchor_message(missing)


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
          "write site."
    )
    assert not not_writers, (
        "WRITE_FUNCTIONS names function(s) spoolman_api.py doesn't define, or that no longer "
        "write: " + ", ".join(not_writers) + f"\nTake them out of their set in {THIS_FILE}."
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


@pytest.mark.parametrize("value", [1, (0, "x"), (1,), (1, ""), ("1", "x"), (1, 2)])
def test_a_registry_entry_of_the_wrong_shape_says_how_to_write_it(value):
    key = ("synthetic.py", "handler", "update_spool")
    with pytest.raises(ValueError, match=r"Write it as .*count, \"doc anchor\" or None"):
        registry_problems({key: 1}, {key: value})
    with pytest.raises(ValueError, match="wrong shape"):
        missing_anchors({key: value}, "## Spool / Filament write surfaces\n")


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
        "    spoolman_api.ensure_required_extras()\n"           # field schema: logs its own failure
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
    assert missing_anchors(registry, section) == [
        "logic.py  a_named_delete  -> delete_spool: 'nowhere' is not in the section",
        "logic.py  after_the_section  -> update_spool: 'after_the_section' is not in the section",
        "logic.py  unanchored  -> update_filament_or_raise: no doc anchor",
        "logic.py  unknown_writer  -> update_spool: 'unknown_writer' is not in the section",
    ]
    assert "Add a row to the table" in anchor_message(["x"])


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
