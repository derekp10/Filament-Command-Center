"""Group 65 review, round 1: the print watch (65.1 (1a), (2), (3), 65.2's line). Offline.

  - RW7 (red, older than the group): after lost contact, a FINISHED or STOPPED is the
    latched print's end only when a job read names it. Another job's end, or one FCC
    can't tie to it, opens the latched print's ❓ review (never its completion charge)
    and is said; the latched print's own end is charged as before.
  - OR5 (red): an end FCC saw after it lost sight of a parked print reads the heads when
    it saw the printer again, never the park's read; a lost stretch that ends at a park
    drops the park's read.
  - OR6: a tick back whose job read fails keeps the lost-contact facts, so a job change
    found later still says FCC lost sight of the print.
  - WD11 / OR4: a printer still silent at FCC's restart has its latch stamped as lost
    across the restart (the review says FCC last saw the print before it restarted),
    and its back line counts the gap from the loss, not from the restart.
  - WD2 / PR2: the lost line says "waiting at a prompt" for a prompt with no print, and a
    state FCC has no words for is escaped.
  - RW2 / RW3 / WD12: a PrusaLink that answers with an HTTP error is said as that (no
    ping, no restart advice, the key named for a 401); icmp_echo resolves a host name and
    counts the reply from its address; an echo it couldn't send is "can't tell", never
    "off".
  - WD8: the finished print's walk-gap line escapes the printer's name.

Red on 681601f6 (the reviewed head), all but one: the latched print's own end after lost
contact (test_the_latched_prints_own_end_after_lost_contact_is_charged_as_before) is a
guard that the fix leaves it charged, green there too.
"""
from __future__ import annotations

import errno
import socket
from unittest.mock import patch

import pytest

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import print_deduct
import print_monitor
import prusalink_api
import state
from test_lost_contact_65_1 import _iso, _latch, _miss, _printing, clock, dispatched  # noqa: F401
from test_printer_reach_65_1 import FakeSock, _reply, _sockets


@pytest.fixture(autouse=True)
def _contact():
    print_monitor._CONTACT.clear()
    prusalink_api._LAST_PROBE_FAILURE.clear()
    yield
    print_monitor._CONTACT.clear()
    prusalink_api._LAST_PROBE_FAILURE.clear()


@pytest.fixture
def words(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    return calls


@pytest.fixture
def completions(monkeypatch):
    calls = []
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(print_monitor, "_dispatch_completion_edge", lambda *a, **k: calls.append((a, k)))
    return calls


def _job(monkeypatch, answer):
    monkeypatch.setattr(prusalink_api, "get_printer_job", lambda fb, name: answer)


# --------------------------------------------------------------------------- #
# RW7: which print an end after lost contact is                                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("end,verb", [("FINISHED", "finished")])
def test_another_jobs_end_after_lost_contact_opens_the_latched_prints_review(monkeypatch, clock, dispatched,
                                                                             completions, words, end, verb):
    _latch()
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 1.0})
    print_monitor._track_print_edge("XL", {"state": end}, "fb")
    assert completions == [] and [(kind, a[2]) for kind, a, _k in dispatched] == [("ambiguous", 7)], dispatched
    assert dispatched[0][2]["lost_contact"]["why"] == "lost" and dispatched[0][2]["heads_when"] == "back"
    assert words == [f"📡 XL: the print that {verb} while FCC couldn't see the printer is job 8 ('/usb/B.BGC'), "
                     f"not '/usb/A.BGC' (job 7), the one FCC last saw. FCC never saw job 8 ('/usb/B.BGC') print, "
                     f"so it charged nothing for it (weigh its spools to true them up), and 🛑 Review asks about "
                     f"'/usb/A.BGC' (job 7)."], words


def test_an_end_fcc_cant_tie_to_the_latched_print_goes_to_its_review(monkeypatch, clock, dispatched, completions,
                                                                     words):
    _latch()
    _miss(3, clock)
    _job(monkeypatch, None)
    print_monitor._track_print_edge("XL", {"state": "FINISHED"}, "fb")
    assert completions == [] and [kind for kind, _a, _k in dispatched] == ["ambiguous"], dispatched
    assert words == ["📡 XL: FCC couldn't read which print finished while it couldn't see the printer, so "
                     "'/usb/A.BGC' (job 7) goes to 🛑 Review instead of being charged as finished."], words


def test_the_latched_prints_own_end_after_lost_contact_is_charged_as_before(monkeypatch, clock, dispatched,
                                                                            completions):
    _latch()
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 1.0})
    print_monitor._track_print_edge("XL", {"state": "FINISHED"}, "fb")
    assert dispatched == [] and [a[2] for a, _k in completions] == [7], (dispatched, completions)


# --------------------------------------------------------------------------- #
# OR5 / OR6: the park's read and a failed job read across a lost stretch      #
# --------------------------------------------------------------------------- #

PARK = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 57, "sids": [57]}], "source": "park",
        "job_id": "7", "progress": 0.31}


def test_an_end_after_lost_contact_at_a_park_reads_the_heads_again(clock, dispatched):
    _latch(state="ATTENTION", park_heads=dict(PARK), park_read=True)
    _miss(40, clock)
    print_monitor._track_print_edge("XL", {"state": "IDLE"}, "fb")
    ((kind, _a, k),) = dispatched
    assert kind == "ambiguous" and "park_heads" not in k and k["heads_when"] == "back", k


def test_a_lost_stretch_ended_at_another_park_drops_the_parks_read(monkeypatch, clock):
    # Group 65 fix review (WT5): only a park the print moved on from; the same park keeps
    # its read (test_print_watch_65_fr1.py).
    _latch(state="ATTENTION", park_heads=dict(PARK), park_read=True)
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 0.55})
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: None)
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert "park_heads" not in entry and "misses" not in entry, entry


def test_a_tick_back_whose_job_read_fails_keeps_the_lost_contact(monkeypatch, clock, dispatched):
    _latch()
    _miss(40, clock)
    _job(monkeypatch, None)
    print_monitor._track_print_edge("XL", {"state": "PRINTING", "is_active": True}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert entry["misses"] == 40 and entry["seen_at"] == 900.0, entry
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=8, progress=0.05), "fb")
    ((kind, a, k),) = dispatched
    assert kind == "ambiguous" and a[2] == 7 and k["lost_contact"]["seen_at"] == 900.0, (a, k)


# --------------------------------------------------------------------------- #
# WD11 / OR4: a printer silent at FCC's restart                                #
# --------------------------------------------------------------------------- #

def test_a_printer_silent_at_fccs_restart_is_lost_across_it(monkeypatch, clock, dispatched, words):
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: None)
    prusalink_api._note_probe_failure("XL", "timeout")
    latched = {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.3, "seen_at": 900.0}
    assert print_monitor._recover_one_print_latch("XL", dict(latched), "fb") is True
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert (entry["misses"], entry["lost_at"], entry["lost_why"]) == (3, 900.0, "restart"), entry
    clock["t"] = 5000.0
    print_monitor._track_print_edge("XL", {"state": "IDLE"}, "fb")
    ((kind, _a, k),) = dispatched
    assert kind == "ambiguous" and k["lost_contact"]["why"] == "restart" and k["heads_when"] == "back", k
    assert print_deduct._lost_contact_words(k["lost_contact"]) == " — FCC last saw it at ~30%, before FCC restarted"


def test_back_after_a_restart_counts_the_gap_from_the_loss(monkeypatch, clock, words):
    prusalink_api._note_probe_failure("XL", "timeout")
    clock["t"] = 10000.0
    print_monitor._note_silent_at_restart("XL", {"state": "PRINTING", "filename": "/usb/A.BGC", "progress": 0.3,
                                                 "seen_at": 900.0, "lost_at": 1000.0})
    clock["t"] = 10600.0
    print_monitor._note_contact("XL", {"state": "IDLE"})
    assert words[-1] == "📡 XL is back after 2 h 40 min (IDLE).", words


# --------------------------------------------------------------------------- #
# WD2 / PR2: the lost line's words                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("state_,said", [
    ("ATTENTION", "waiting at a prompt"),
    ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)&gt;"),
], ids=["a prompt", "a state FCC has no words for"])
def test_the_lost_line_for_a_printer_with_no_print(monkeypatch, words, state_, said):
    monkeypatch.setattr(print_monitor, "_reach_verdict", lambda name: None)
    print_monitor._note_contact("XL", {"state": state_})
    for _ in range(3):
        print_monitor._note_contact("XL", None)
    assert words == [f"📡 Lost contact with XL (it was {said})."], words


# --------------------------------------------------------------------------- #
# RW2 / RW3 / WD12: why FCC can't reach a printer                              #
# --------------------------------------------------------------------------- #

def test_an_http_error_is_prusalink_answering_never_a_stuck_one(monkeypatch):
    pings = []
    monkeypatch.setattr(prusalink_api, "icmp_echo", lambda *a, **k: pings.append(a) or True)
    prusalink_api._note_probe_failure("XL", "http 401")
    assert print_monitor._reach_verdict("XL") == "login" and pings == []
    assert print_monitor._reach_words("XL", "login", True) == (
        "XL's PrusaLink answers, but turns FCC's API key away (HTTP 401): check the key in Settings, "
        "🔌 Printer Connections.")
    prusalink_api._note_probe_failure("XL", "http 503")
    assert print_monitor._reach_verdict("XL") == "error" and pings == []
    assert print_monitor._reach_words("XL", "error", False) == "XL's PrusaLink answers, but with an error (HTTP 503)."


def test_a_host_name_is_resolved_and_its_reply_counts(monkeypatch):
    monkeypatch.setattr(prusalink_api.socket, "gethostbyname", lambda name: "10.0.0.9")
    sock = FakeSock([(_reply(), ("10.0.0.9", 0))])
    with patch.object(prusalink_api, "_icmp_socket", _sockets(sock, None)):
        assert prusalink_api.icmp_echo("xl.lan") is True
    assert sock.sent[0][1] == ("10.0.0.9", 0), sock.sent


def _unresolvable(name):
    raise socket.gaierror(-2, "Name or service not known")


@pytest.mark.parametrize("host,resolve,sock", [
    ("[fd00::5]", None, FakeSock([])),
    ("xl.lan", _unresolvable, FakeSock([])),
    ("10.0.0.9", None, FakeSock(send_error=OSError(errno.EINVAL, "Invalid argument"))),
], ids=["an IPv6 address", "a name FCC can't resolve", "a send the system refuses"])
def test_an_echo_fcc_couldnt_send_is_cant_tell_never_off(monkeypatch, host, resolve, sock):
    if resolve is not None:
        monkeypatch.setattr(prusalink_api.socket, "gethostbyname", resolve)
    with patch.object(prusalink_api, "_icmp_socket", _sockets(sock, None)):
        assert prusalink_api.icmp_echo(host) is None


# --------------------------------------------------------------------------- #
# WD8: the finished print's walk-gap line                                     #
# --------------------------------------------------------------------------- #

def test_the_finished_prints_walk_gap_line_escapes_the_printers_name(monkeypatch, words):
    monkeypatch.setattr(print_deduct.locations_db, "get_active_printer_map",
                        lambda: {"P-1": {"printer_name": "Core <b>X</b> & co", "position": 0}})
    measured = {"whole": {0: 7.5}, "footer": {0: 3.23}, "partials": [{}]}
    print_deduct._warn_parse_gap("Core <b>X</b> & co", "job.bgcode", measured, completion=True)
    assert words and words[0].startswith("⚠️ Core &lt;b&gt;X&lt;/b&gt; &amp; co: FCC's G-code walk"), words
