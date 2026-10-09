"""Meta-test: every outbound `requests.*` call in backend code must pass a timeout.

Background (2026-08-03):
  `spoolman_api.update_spool` PATCHed Spoolman with a bare
  `requests.patch(url, json=clean_data)` — no timeout. `requests` has NO
  default timeout, so that call blocks its worker thread until the OS
  gives up, which against an unreachable or wedged Spoolman is effectively
  forever.

Why this is worth a canary rather than a one-line fix:
  `update_spool` is the single highest-traffic write in the app — every
  smart move, every print deduct, every weigh-out, and once per spool of a
  bulk move. A hang there starves Flask's request threads, which is exactly
  the L28 "frontend locks up and stops taking barcodes" failure class
  (there: browser sockets exhausted by stacked un-guarded polls; here: the
  server side of the same coin).

  Every other one of the ~35 `requests` calls in `spoolman_api.py` already
  passed a timeout — this was a single missed kwarg that survived review
  precisely because it looks like all its neighbours. That is the signature
  of a defect class that recurs, so it gets a test instead of a fix.

Verified empirically against a real unresponsive server (2026-08-04, with
Derek's OK to break things in dev):
  - host unreachable (unroutable TEST-NET-1 address):  24.1s -> 8.0s
  - server ACCEPTS the connection and never replies:   hung past a 45s
    watchdog (i.e. forever) -> 5.0s ReadTimeout

That second case is the one that matters and the reason a connect-timeout alone
would not have been enough: the TCP connect SUCCEEDS against a wedged Spoolman,
so only a read timeout can ever release the worker. Pre-fix there was neither.

AST-based rather than regex: call sites in this repo span multiple lines
(see `ensure_filament_attributes_cleaned`), and a regex either misses those
or produces false positives on the surrounding kwargs.

If a call genuinely must block indefinitely (none currently do), give it an
explicit `timeout=None` — that is still an intentional, auditable choice and
this test accepts it, unlike a silently absent kwarg.
"""
from __future__ import annotations

import ast
from pathlib import Path

INV_HUB = Path(__file__).resolve().parent.parent

# Backend modules live FLAT at the inventory-hub root (CLAUDE.md "Backend
# module map"), so a non-recursive glob is the correct scope — it matches
# what test_no_direct_extra_patch.py scans.
BACKEND_GLOB = "*.py"

REQUEST_VERBS = {"get", "post", "patch", "put", "delete", "head", "options", "request"}


def _requests_aliases(tree: ast.AST) -> set[str]:
    """Every local name bound to the `requests` module in this file.

    Group 36/38.9 — the original canary hard-coded the receiver name
    `requests`, but `routes_config_attrs.py` does a function-local
    `import requests as _req` and issues ALL fourteen of its HTTP calls as
    `_req.<verb>(...)` — including the destructive PATCH loop that rewrites
    every attribute-bearing filament after deleting the schema field. The single
    most dangerous write loop in the app was therefore invisible to the one test
    whose whole job is catching a missing timeout there.

    `import requests` binds `requests`; `import requests as _req` binds `_req`.
    Both forms are collected, at any nesting depth, so a function-local alias
    counts exactly like a module-level one.
    """
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "requests":
                    aliases.add(a.asname or "requests")
    return aliases


def _timeoutless_calls(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, '<alias>.<verb>')] for calls missing a timeout kwarg."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:  # pragma: no cover - a broken module fails elsewhere, loudly
        return []

    aliases = _requests_aliases(tree)
    if not aliases:
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in REQUEST_VERBS:
            continue
        # Only a name bound to the `requests` module — not `self.session.get(...)`
        # or a local helper that already wraps a timeout.
        if not (isinstance(func.value, ast.Name) and func.value.id in aliases):
            continue
        # `**kwargs` splat could supply the timeout; don't flag those.
        if any(kw.arg is None for kw in node.keywords):
            continue
        if not any(kw.arg == "timeout" for kw in node.keywords):
            found.append((node.lineno, f"{func.value.id}.{func.attr}"))
    return found


def test_no_backend_requests_call_omits_a_timeout():
    violations = []
    for path in sorted(INV_HUB.glob(BACKEND_GLOB)):
        for lineno, call in _timeoutless_calls(path):
            violations.append(f"{path.name}:{lineno} — {call}(...) has no timeout=")

    assert not violations, (
        "Outbound HTTP call(s) with no timeout — these block a worker thread "
        "indefinitely when the remote is unreachable:\n  "
        + "\n  ".join(violations)
        + "\n\nPass an explicit timeout= (or timeout=None if blocking forever is "
          "genuinely intended)."
    )


def test_canary_detects_a_timeoutless_call(tmp_path):
    """The canary must actually catch the thing it claims to catch.

    A meta-test that can only ever pass is worthless — pin that the AST walk
    flags a bare call, accepts an explicit timeout, and accepts an explicit
    timeout=None.
    """
    sample = tmp_path / "sample_module.py"
    sample.write_text(
        "import requests\n"
        "def bare():\n"
        "    return requests.patch('http://x', json={})\n"
        "def guarded():\n"
        "    return requests.get('http://x', timeout=5)\n"
        "def explicitly_blocking():\n"
        "    return requests.post('http://x', timeout=None)\n"
        "def multiline_bare():\n"
        "    return requests.delete(\n"
        "        'http://x',\n"
        "        headers={},\n"
        "    )\n",
        encoding="utf-8",
    )

    hits = _timeoutless_calls(sample)
    calls = {call for _, call in hits}
    assert calls == {"requests.patch", "requests.delete"}, (
        f"expected the bare single-line and multi-line calls only, got {hits}"
    )


def test_canary_sees_through_an_import_alias(tmp_path):
    """`import requests as _req` must not blind the canary.

    This is the real-world shape: `routes_config_attrs.py` aliases the module
    function-locally and makes every call — including the destructive PATCH
    loop — as `_req.<verb>(...)`. Before Group 36 the canary matched only the
    literal receiver `requests`, so that whole module scanned clean while being
    entirely uncovered.
    """
    sample = tmp_path / "aliased_module.py"
    sample.write_text(
        "def handler():\n"
        "    import requests as _req\n"
        "    _req.patch('http://x', json={})\n"
        "    _req.get('http://x', timeout=5)\n"
        "    return _req.delete('http://x')\n",
        encoding="utf-8",
    )

    calls = {call for _, call in _timeoutless_calls(sample)}
    assert calls == {"_req.patch", "_req.delete"}, (
        f"the aliased timeout-less calls were not detected, got {calls}"
    )


def test_canary_ignores_a_lookalike_receiver(tmp_path):
    """Widening to aliases must not start flagging unrelated objects.

    A `session.get(...)` or a home-grown `_req` that is NOT the requests module
    manages its own timeouts; flagging it would be a false positive that
    trains people to ignore this canary.
    """
    sample = tmp_path / "lookalike_module.py"
    sample.write_text(
        "import some_other_lib as _req\n"
        "class C:\n"
        "    def go(self):\n"
        "        return self.session.get('http://x')\n"
        "def other():\n"
        "    return _req.patch('http://x')\n",
        encoding="utf-8",
    )

    assert _timeoutless_calls(sample) == [], (
        "a receiver that is not bound to the requests module must not be flagged"
    )


def test_update_spool_patch_carries_a_timeout():
    """The specific regression: spoolman_api.update_spool's PATCH.

    Pinned by name as well as by the module-wide sweep so the failure message
    points straight at the call that caused this test to exist.
    """
    spoolman_api = INV_HUB / "spoolman_api.py"
    tree = ast.parse(spoolman_api.read_text(encoding="utf-8", errors="replace"))

    patches_in_update_spool = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "update_spool"):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "patch"
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id == "requests"
            ):
                patches_in_update_spool.append(inner)

    assert patches_in_update_spool, "update_spool no longer PATCHes via requests — update this test"
    for call in patches_in_update_spool:
        assert any(kw.arg == "timeout" for kw in call.keywords), (
            f"spoolman_api.py:{call.lineno} — update_spool's PATCH must pass a "
            "timeout; a bare call hangs every move/deduct/weigh-out on an "
            "unreachable Spoolman."
        )
