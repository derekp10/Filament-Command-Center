"""L271 — location-tree frontend regression pins.

Phase 2.5 moved the tree off LocationID string-splitting onto `parent_id`
(then a flat first-segment prefix). **Phase 3.5 supersedes that**: parent_id is
now each row's IMMEDIATE parent, the renderer is a true recursive multi-level
tree (room → printer → toolhead, cart → rows), `hasChildren` migrated off the
startsWith descendant probe onto the parent_id child-map, and a pin-printers
toggle + nested collapse were added. These pins guard the Phase 3.5 shape; the
hierarchy-walk helpers + migration are pinned in test_l271_phase35_*.py.
"""
import os

import pytest
import requests

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PSEUDO = {"TST", "TEST", "PM", "PJ"}


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Backend — /api/locations parent_id write paths
# ---------------------------------------------------------------------------

def test_synthesized_rows_expose_parent_id():
    """The 3 synthesized /api/locations rows (synthetic Virtual Room,
    Unassigned, UNKNOWN) each carry parent_id:None so the frontend reads
    row.parent_id uniformly."""
    app = _read("app.py")
    assert app.count('"parent_id": None') >= 3


def test_post_stamps_immediate_parent():
    """Phase 3.5: api_save_location stamps the IMMEDIATE parent at write time
    (longest existing-row prefix), while the Spoolman-native synthesized row
    still derives the flat prefix."""
    app = _read("app.py")
    assert "locations_db.immediate_parent_for(" in app, (
        "api_save_location must stamp the immediate parent at write time"
    )
    assert "derive_parent_id_from_prefix" in app, (
        "the Spoolman-native synthesized row still derives a prefix parent_id"
    )


@pytest.mark.integration
def test_api_locations_parent_id_is_valid_tree(api_base_url, require_server):
    """Live nested invariant: every row carries parent_id; every non-null
    parent_id points to a real on-disk row OR a known pseudo-prefix
    (PM/PJ/TST); and the hierarchy is acyclic (every row walks to a root)."""
    rows = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
    assert rows, "no rows returned"
    ids = {str(r.get("LocationID", "")).upper() for r in rows}
    parent_of = {}
    for r in rows:
        lid = str(r.get("LocationID", "")).upper()
        assert "parent_id" in r, f"{lid} missing parent_id"
        pid = r.get("parent_id")
        parent_of[lid] = (str(pid).upper() if pid else None)
        if pid:
            pu = str(pid).upper()
            assert pu in ids or pu in _PSEUDO, f"{lid} parent_id {pu!r} is a dangling FK"
    # acyclic: every row reaches a root (None) without revisiting
    for start in parent_of:
        seen, cur, steps = set(), start, 0
        while cur and cur in parent_of and parent_of[cur] is not None:
            assert cur not in seen, f"cycle detected at {cur}"
            seen.add(cur)
            cur = parent_of[cur]
            steps += 1
            assert steps < 50, f"runaway chain from {start}"


@pytest.mark.integration
def test_api_locations_printers_nested_under_rooms(api_base_url, require_server):
    """Phase 3.5: printers are nested under a Room row (XL→LR, CORE1→CR)."""
    rows = {str(r.get("LocationID", "")).upper(): r for r in
            requests.get(f"{api_base_url}/api/locations", timeout=10).json()}
    for pid in ("XL", "CORE1"):
        if pid not in rows:
            continue
        parent = rows[pid].get("parent_id")
        assert parent, f"{pid} should be nested under a room (parent_id set)"
        room = rows.get(str(parent).upper())
        assert room and str(room.get("Type", "")).lower() == "room", (
            f"{pid} parent {parent!r} should be a Room row"
        )


@pytest.mark.integration
def test_api_locations_room_total_is_distinct_spool_count(api_base_url, dev_spoolman_url, require_server):
    """Phase 3.5 (review fix #2): a parent's OccupancyRaw equals the number of
    DISTINCT physical spools whose location OR ghost physical_source resolves
    into its subtree — NOT a naive sum (which double-counts a deployed spool
    that sits at a toolhead AND is ghost-reserved at a home box, both nesting
    under the same room). Independent oracle: re-walk parent_id from the payload
    and dedup by spool id."""
    rows = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
    by_id = {str(r.get("LocationID", "")).upper(): r for r in rows}
    parent = {
        str(r["LocationID"]).upper(): (str(r["parent_id"]).upper() if r.get("parent_id") else None)
        for r in rows
    }

    def _hop(x):
        # mirror locations_db._parent_of: on-disk parent, else first-segment prefix
        x = (x or "").upper()
        if x in parent:
            return parent[x]
        return x.split("-", 1)[0] if "-" in x else None

    def ancestors(x):
        out, seen, cur = [], {(x or "").upper()}, _hop(x)
        while cur and cur not in seen:
            if cur in _PSEUDO:
                break
            out.append(cur)
            seen.add(cur)
            cur = _hop(cur)
        return out

    spools = requests.get(f"{dev_spoolman_url}/api/v1/spool", timeout=10).json()
    distinct = {}
    for s in spools:
        sid = s["id"]
        loc = str(s.get("location") or "").upper().strip()
        if loc in ("UNASSIGNED", "UNKNOWN"):
            loc = ""
        ghost = str((s.get("extra") or {}).get("physical_source", "")).replace('"', "").upper().strip()
        touched = set()
        for base in (loc, ghost):
            if not base:
                continue
            touched.add(base)
            touched.update(ancestors(base))
        for t in touched:
            distinct.setdefault(t, set()).add(sid)

    for lid, row in by_id.items():
        if "Total" in str(row.get("Occupancy", "")):  # parent rows show a subtree Total
            assert row.get("OccupancyRaw") == len(distinct.get(lid, set())), (
                f"{lid}: OccupancyRaw {row.get('OccupancyRaw')} != distinct spool count "
                f"{len(distinct.get(lid, set()))} (double-count regression)"
            )


@pytest.mark.integration
def test_new_location_nests_under_immediate_parent(api_base_url, require_server):
    """A freshly POSTed row carries its IMMEDIATE parent right away: a cart-row
    created under an existing cart nests under the cart, not the room."""
    room, cart, row = "ZZL271T", "ZZL271T-CT-1", "ZZL271T-CT-1-R1"
    try:
        for lid, typ in ((room, "Room"), (cart, "Cart"), (row, "Cart")):
            requests.post(f"{api_base_url}/api/locations", json={
                "old_id": "", "new_data": {
                    "LocationID": lid, "Name": f"t {lid}", "Type": typ, "Max Spools": "1"}},
                timeout=10).raise_for_status()
        got = {str(x.get("LocationID")): x for x in
               requests.get(f"{api_base_url}/api/locations", timeout=10).json()}
        assert got[cart]["parent_id"] == room, f"cart should nest under room, got {got[cart]['parent_id']!r}"
        assert got[row]["parent_id"] == cart, f"cart-row should nest under cart, got {got[row]['parent_id']!r}"
    finally:
        for lid in (row, cart, room):
            requests.delete(f"{api_base_url}/api/locations", params={"id": lid}, timeout=10)


@pytest.mark.integration
def test_edit_preserves_parent_id_in_place(api_base_url, require_server):
    """Review fix #4: an in-place edit (same LocationID, no parent_id in the
    payload — what the edit modal sends) must PRESERVE the existing parent_id,
    not recompute it. Otherwise editing a printer's name un-nests it (recompute
    → None) and an operator override is silently reverted."""
    room, printer = "ZZRM", "ZZPRN"
    try:
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": room, "Name": "t room", "Type": "Room", "Max Spools": "0"}}, timeout=10).raise_for_status()
        # create with an explicit parent_id (api respects a supplied value)
        requests.post(f"{api_base_url}/api/locations", json={"old_id": "", "new_data": {
            "LocationID": printer, "Name": "t printer", "Type": "Printer",
            "Max Spools": "1", "parent_id": room}}, timeout=10).raise_for_status()
        # edit in place WITHOUT parent_id (the modal's payload shape)
        requests.post(f"{api_base_url}/api/locations", json={"old_id": printer, "new_data": {
            "LocationID": printer, "Name": "t printer RENAMED", "Type": "Printer",
            "Max Spools": "1"}}, timeout=10).raise_for_status()
        got = {str(x.get("LocationID")): x for x in
               requests.get(f"{api_base_url}/api/locations", timeout=10).json()}
        assert got[printer]["parent_id"] == room, (
            f"in-place edit must preserve parent_id, got {got[printer]['parent_id']!r}"
        )
    finally:
        for lid in (printer, room):
            requests.delete(f"{api_base_url}/api/locations", params={"id": lid}, timeout=10)


# ---------------------------------------------------------------------------
# Frontend — inv_core.js renders a recursive parent_id tree
# ---------------------------------------------------------------------------

def _js():
    return _read("static", "js", "modules", "inv_core.js")


def test_tree_built_from_parent_id_children_map():
    js = _js()
    assert "const childrenOf = new Map()" in js, "tree must group children by parent_id"
    assert "r.parent_id != null ? upper(r.parent_id)" in js, "tree must read row.parent_id"
    assert "const visit = (row, depth, ancestors)" in js, "must DFS-render with depth"


def test_has_children_uses_tree_not_startswith():
    """Phase 3.5: hasChildren migrated OFF the startsWith descendant probe onto
    the parent_id child-map (entry.hasKids). The old probe must be GONE."""
    js = _js()
    assert "hasKids: kids.length > 0" in js, "toggle must derive from the child-map"
    assert "startsWith(l.LocationID + '-')" not in js, (
        "the flat startsWith descendant probe must be retired in Phase 3.5"
    )
    assert ".loc-child-of-" not in js, "the flat loc-child-of class scheme is retired"


def test_nested_collapse_via_ancestors():
    js = _js()
    assert "data-ancestors" in js, "rows must carry their ancestor chain"
    assert "function applyLocCollapse()" in js, "nested collapse helper must exist"
    assert "state.locCollapsed" in js, "collapse state must persist across re-renders"


def test_pin_printers_toggle():
    js = _js()
    assert "fcc.locMgr.pinPrintersTop" in js, "pin state persisted in localStorage"
    assert "window.toggleLocPinPrinters" in js, "pin toggle handler must exist"
    html = _read("templates", "components", "modals_loc_mgr.html")
    assert "loc-pin-printers-btn" in html, "pin button must be in the loc-mgr header"


def test_tree_grouping_case_insensitive():
    """parent_id is uppercased but a LocationID may be mixed-case; the tree
    normalizes both sides via upper()."""
    js = _js()
    assert "const upper = (v) =>" in js and "toUpperCase()" in js


def test_row_markup_escapes_user_values():
    """Review fix #3/#8: LocationID/Name/Type are escaped into innerHTML, the
    ancestor chain is JSON-encoded (not space-joined), and the toggle/QR carry
    no inline onclick with a raw LocationID (delegated off data attributes)."""
    js = _js()
    assert "const escHtml = " in js, "escape helper must exist"
    assert "${escHtml(l.Name)}" in js and "${escHtml(l.Type)}" in js, "cells must be escaped"
    assert "escAttr(JSON.stringify(entry.ancestors" in js, "ancestors must be JSON-encoded + escaped"
    assert "toggleLocNode('${" not in js, "toggle must NOT inline a raw LocationID into onclick"
    assert "showGlobalQrModal('${" not in js, "QR must NOT inline a raw LocationID into onclick"
    html = _read("templates", "components", "scripts.html")
    assert ".loc-toggle" in html and "row.dataset.locid" in html, "toggle must be delegated"
    assert "JSON.parse(tr.dataset.ancestors" in js, "collapse must JSON-parse ancestors"
