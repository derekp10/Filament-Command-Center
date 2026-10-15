"""Group 40 — offline source canary: every browser door that can complete a move
into a bound box slot hands the same-slot swap's old spool to this page's
buffer (window.takeIntoBuffer), so a new door can't silently drop it.

The doors are test_door_fed_heads_canary.TABLE's "sends" rows (the functions
that POST a move to /api/identify_scan, /api/smart_move or /api/manage_contents
add). processScan's slot scan and its replays share _slotScanOutcome, so that is
where the call sits. The behaviour is pinned in test_same_slot_swap_buffer_js.py.

HEAD proof (d8f6128): no function calls takeIntoBuffer there, so every row fails.
"""
import pytest

from test_door_fed_heads_canary import MODULES, SENDS, TABLE, _body, _read

# A door whose outcome handling lives in a shared helper: (file, door) -> helper.
DELEGATES = {("inv_cmd.js", "const processScan = "): "const _slotScanOutcome = "}

ROWS = [(f, header) for f, rows in TABLE.items() for header, cls, *_ in rows if cls == SENDS]


@pytest.mark.parametrize("filename, header", ROWS, ids=[h.split("=")[0].strip() for _, h in ROWS])
def test_every_move_door_takes_the_swapped_out_spool_into_the_buffer(filename, header):
    src = _read(MODULES / filename)
    helper = DELEGATES.get((filename, header))
    if helper:
        name = helper.replace("const ", "").replace(" = ", "")
        assert f"{name}(" in _body(src, header), f"{header} no longer uses {name}"
        header = helper
    assert "takeIntoBuffer(" in _body(src, header), (
        f"{filename}: {header.strip()} completes a move but never calls window.takeIntoBuffer, so a "
        f"same-slot swap's old spool would vanish from this page's buffer on its next save")


def test_the_helper_lives_in_inv_core_so_every_page_has_it():
    src = _read(MODULES / "inv_core.js")
    assert "window.takeIntoBuffer = " in src and "window.toastIntoBuffer = " in src
