"""Shared source-family reader for source-text canary tests (L316).

Several test files pin backend wiring by grepping app.py's SOURCE (not its
behavior). The L316 modularization moves blocks of app.py into flat sibling
modules (startup_migrations, labels_csv, routes_*, print_deduct,
print_monitor); reading the whole family keeps those canaries meaningful
regardless of which module a block landed in. Presence asserts stay valid;
absence asserts get STRICTER (must hold across the whole family) — both
desirable. Not a test module (no test_ prefix); imported by the canary
files via the tests-dir sys.path entry pytest provides.
"""
import glob
import os

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_FAMILY = [
    "app.py",
    "app_core.py",
    "startup_migrations.py",
    "labels_csv.py",
    "print_deduct.py",
    "print_monitor.py",
]


def read_app_family():
    """Concatenated source of app.py + every L316 carve module that exists."""
    names = list(_FAMILY)
    names += sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(_HUB, "routes_*.py"))
    )
    parts = []
    for name in names:
        path = os.path.join(_HUB, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f.read())
    return "\n".join(parts)
