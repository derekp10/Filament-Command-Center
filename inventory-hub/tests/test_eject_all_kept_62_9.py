"""Group 62.9: Eject All stays as it is (Derek's answer (a), 2026-11-17), offline.

EJECT ALL empties the place whose Location Manager window is open, in one go. It is drawn
only in a dryer box's window, in the ☢️ DANGER ZONE under Unslotted Items while the box
holds spools with no slot; a cart's, a shelf's or a toolhead's window has none (a printed
CMD:EJECTALL label empties one). Derek kept it as it is: only the dead code went, the
list view's QR call for a target the template never had.

RED on the commit before 62.9 for the first; the second pins what stays.
"""
from __future__ import annotations

from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
LOC_MGR = HUB / "static" / "js" / "modules" / "inv_loc_mgr.js"


def test_the_list_view_draws_no_qr_into_a_target_that_does_not_exist():
    for path in list((HUB / "static" / "js").rglob("*.js")) + list((HUB / "templates").rglob("*.html")):
        assert "qr-eject-all-list" not in path.read_text(encoding="utf-8").replace(
            "Group 62.9", ""), f"{path.name} still names qr-eject-all-list"


def test_the_box_windows_danger_zone_stays():
    src = LOC_MGR.read_text(encoding="utf-8")
    assert 'id="qr-eject-all"' in src and 'generateSafeQR("qr-eject-all", "CMD:EJECTALL", 65)' in src
    assert "triggerEjectAll(document.getElementById('manage-loc-id').value)" in src
