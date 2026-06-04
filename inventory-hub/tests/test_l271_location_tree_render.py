"""L271 Phase 2.5 — location-tree frontend migration regression pins.

Phase 2.5 moves the Location Manager tree (sort root + indent / child grouping)
off LocationID string-splitting onto the `parent_id` field that /api/locations
now exposes on EVERY row. In this phase parent_id is still the flat first-segment
prefix (Phase 1A derivation), so reading it is byte-for-byte equivalent to the
old `LocationID.split('-')[0]` — the migration is behavior-preserving and the
rendered tree must be visually identical (see test_visual_baseline.py
locations-modal-default).

These pins guard:
  1. the backend exposes parent_id on every row (incl. the 3 synthesized rows);
  2. the frontend reads row.parent_id (with a split fallback during rollout);
  3. line 564 hasChildren stays a startsWith descendant query — it is NOT a
     split('-')[0] parent derivation and parent_id (flat in this phase) cannot
     express it without diverging on synthesized descendant rows; it migrates
     in Phase 3 when hierarchy becomes truly multi-level.
"""
import os

import pytest
import requests

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _old_parent(lid):
    """The pre-migration frontend parentId derivation (the A/B oracle)."""
    return lid.split("-")[0] if "-" in lid else lid


# ---------------------------------------------------------------------------
# Backend — /api/locations exposes parent_id on every row
# ---------------------------------------------------------------------------

def test_synthesized_rows_expose_parent_id():
    """Cheap source canary: the 3 synthesized /api/locations rows (synthetic
    printer/room, Unassigned, UNKNOWN) must each carry parent_id so the frontend
    can read row.parent_id uniformly."""
    app = _read("app.py")
    assert app.count('"parent_id": None') >= 3, (
        "expected parent_id:None on all 3 synthesized /api/locations rows "
        "(synthetic printer/room, Unassigned, UNKNOWN)"
    )


@pytest.mark.integration
def test_api_locations_every_row_has_parent_id(api_base_url, require_server):
    """Live: every row carries parent_id, and the migrated frontend derivation
    `(parent_id ?? split-fallback)` equals the old split derivation for ALL rows
    — the behavior-preservation invariant for the tree sort + indent."""
    resp = requests.get(f"{api_base_url}/api/locations", timeout=10)
    resp.raise_for_status()
    rows = resp.json()
    assert rows, "no location rows returned"

    missing = [r.get("LocationID") for r in rows if "parent_id" not in r]
    assert not missing, f"rows missing parent_id: {missing}"

    for r in rows:
        lid = str(r.get("LocationID", ""))
        pid = r.get("parent_id")
        migrated = pid if pid is not None else _old_parent(lid)
        assert migrated == _old_parent(lid), (
            f"parentId divergence at {lid}: parent_id={pid!r} old={_old_parent(lid)!r}"
        )


# ---------------------------------------------------------------------------
# Frontend — inv_core.js tree derives parent from row.parent_id (not split)
# ---------------------------------------------------------------------------

def test_sort_comparator_reads_parent_id():
    """The LocationID sort comparator derives the tree root from row.parent_id
    (with a split fallback for an old payload), not a bare split('-')[0]."""
    js = _read("static", "js", "modules", "inv_core.js")
    assert "a.parent_id != null ? a.parent_id" in js, "sort rootA must read a.parent_id"
    assert "b.parent_id != null ? b.parent_id" in js, "sort rootB must read b.parent_id"


def test_tree_indent_reads_parent_id():
    """The tree-indent parentId derivation reads row.parent_id (with a split
    fallback), and isChild is derived from the resolved parent rather than a
    bare LocationID.split('-')[0]."""
    js = _read("static", "js", "modules", "inv_core.js")
    assert "l.parent_id != null ? l.parent_id" in js, "parentId must read l.parent_id"
    assert "isChild = (parentId !== l.LocationID)" in js, \
        "isChild must derive from the resolved parent, not LocationID.includes('-')"


def test_has_children_stays_descendant_query():
    """DELIBERATE Phase 2.5 scope guard: hasChildren must remain a startsWith
    descendant query. parent_id is the flat first-segment prefix this phase and
    synthesized descendant rows carry parent_id:null, so a `c.parent_id === l`
    rewrite would diverge (a printer could lose its expand toggle). It migrates
    in Phase 3 when hierarchy becomes truly nested."""
    js = _read("static", "js", "modules", "inv_core.js")
    assert "c.LocationID.startsWith(l.LocationID + '-')" in js, \
        "hasChildren must stay a startsWith descendant query until Phase 3"
