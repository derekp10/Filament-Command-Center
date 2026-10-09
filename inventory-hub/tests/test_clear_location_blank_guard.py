"""A blank location is never a clear_location target (2026-09-13).

A CMD:EJECTALL scan with the Location Manager closed sent
/api/manage_contents {action: clear_location, location: ""} (closing the manager
blanks #manage-loc-id). The location matcher, spoolman_api._build_location_match,
treats "" == "" as a DIRECT hit for every spool with no location, so the route
ejected the whole Unassigned pile, and each spool still carrying a
physical_source trail was "returned" into that box.

The route now refuses a blank location before any Spoolman read. The matcher's
own semantics are deliberately unchanged: other callers use it, so the fix lives
at the destructive entry point.

Hermetic: every Spoolman / logic side effect is patched. The real-matcher test
runs spoolman_api's actual matcher over a fake spool list, so it proves the
hazard itself rather than a mock of it.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


BLANK_REQUESTS = [
    pytest.param({"location": ""}, id="empty"),
    pytest.param({"location": "   "}, id="whitespace"),
    pytest.param({"location": None}, id="null"),
    pytest.param({}, id="missing"),
    pytest.param({"location": "", "confirm_active_print": True}, id="empty-confirmed"),
]


@pytest.mark.parametrize("fields", BLANK_REQUESTS)
def test_clear_location_refuses_a_blank_location_before_any_read(client, fields):
    """FAILS on the old route. For empty / whitespace / missing / empty-confirmed
    it read the Spoolman contents for "", found nothing to eject in the mocked
    read, and answered {"success": True}, so the `success is False` assertion
    fails. For null it raised AttributeError on None.strip().

    The probe answers None (no active print), a real value. A bare MagicMock is
    truthy: the old route then built a require_confirm response Flask could not
    serialise, and those cases failed on a TypeError instead of on the
    assertions below."""
    with patch.object(spoolman_api, "get_spools_at_location_detailed") as contents, \
         patch.object(spoolman_api, "get_all_spools") as all_spools, \
         patch.object(logic, "_active_print_info_for_location", return_value=None) as probe, \
         patch.object(logic, "perform_smart_eject") as eject, \
         patch.object(state, "add_log_entry") as log:
        r = client.post("/api/manage_contents", json={"action": "clear_location", **fields})

    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is False, body
    assert "No location given" in body["msg"], body
    contents.assert_not_called()
    all_spools.assert_not_called()
    probe.assert_not_called()
    eject.assert_not_called()
    assert len(log.call_args_list) == 1, log.call_args_list
    msg, level, color = log.call_args_list[0].args
    assert "Eject All refused" in msg
    assert (level, color) == ("WARNING", "ffaa00")


# Spoolman's view: two spools with no location (one still carrying a trail back
# into PM-DB-1) and one spool sitting unslotted in PM-DB-1.
UNASSIGNED = {"id": 901, "location": "", "extra": {}}
UNASSIGNED_WITH_TRAIL = {"id": 902, "location": "",
                         "extra": {"physical_source": '"PM-DB-1"', "physical_source_slot": '"2"'}}
IN_BOX = {"id": 903, "location": "PM-DB-1", "extra": {}}


def _fake_spools():
    return [dict(s, extra=dict(s["extra"])) for s in (UNASSIGNED, UNASSIGNED_WITH_TRAIL, IN_BOX)]


def test_blank_clear_location_no_longer_ejects_the_unassigned_pile_through_the_real_matcher(client):
    """FAILS on the old route: perform_smart_eject ran for #901 and #902, the
    two spools with no location, and the answer was success."""
    # Precondition, pinned so this test keeps proving something: the matcher is
    # unchanged and still reads "" as every spool with no location.
    with patch.object(spoolman_api, "get_all_spools", return_value=_fake_spools()):
        hits = spoolman_api.get_spools_at_location_detailed("")
    assert sorted(h["id"] for h in hits if not h["is_ghost"]) == [901, 902]

    with patch.object(spoolman_api, "get_all_spools", return_value=_fake_spools()), \
         patch.object(logic, "_active_print_info_for_location", return_value=None), \
         patch.object(logic, "perform_smart_eject", return_value=True) as eject, \
         patch.object(state, "add_log_entry"):
        r = client.post("/api/manage_contents", json={"action": "clear_location", "location": ""})
    assert r.get_json()["success"] is False
    assert eject.call_args_list == [], "a blank Eject All still ejected spools"


def test_a_real_location_still_clears_through_the_real_matcher(client):
    """Control, PASSES on the old route too: the guard is blank-only. PM-DB-1
    ejects its own unslotted spool (#903) and skips #902, whose trail makes it
    a ghost of PM-DB-1 rather than a resident."""
    with patch.object(spoolman_api, "get_all_spools", return_value=_fake_spools()), \
         patch.object(logic, "_active_print_info_for_location", return_value=None), \
         patch.object(logic, "perform_smart_eject", return_value=True) as eject, \
         patch.object(state, "add_log_entry"):
        r = client.post("/api/manage_contents", json={"action": "clear_location", "location": "pm-db-1"})
    assert r.get_json() == {"success": True}
    assert [c.args[0] for c in eject.call_args_list] == [903]
    assert eject.call_args_list[0].kwargs == {"confirm_active_print": True}
