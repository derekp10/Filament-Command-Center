"""Group 65.1 (3): say when PrusaLink, not the printer, is stuck. Offline (the badge
in `isolated_page`).

On 2026-11-09 Derek's printers answered ping while every TCP port timed out, and only
a reset brought PrusaLink back. When the monitor declares contact lost (65.1 (2)), and
every 5 minutes while it stays lost, it asks why: a refused connection proves the
printer is on the network with no ping; otherwise one ICMP echo with a 1 s limit
(prusalink_api.icmp_echo: the unprivileged datagram socket, then a raw one, the
standard library only). "XL is on the network, but PrusaLink isn't answering.
Restarting the printer brings it back, but a restart ends a print: wait until its
print is done." or "XL doesn't answer at all (off, or off the network)." in the lost
line, and again only when the verdict changes. When FCC can't tell (no socket opens,
no IP saved) it keeps today's words and never says a printer is off. The heartbeat
copies the verdict into that printer's own payload (`reach`), never as a key of
printer_status, and the OFFLINE badge words its tooltip and accessible name for it.

Dev's container (2026-11-23): both sockets open (root, ping_group_range 0-2147483647);
the gateway and the NAS answered and an unused address didn't. Prod's is Derek's
TrueNAS fact. Red on 08d3c2f9 (no icmp_echo, no verdict, no `reach`).
"""
from __future__ import annotations

import errno
import socket
import struct
from unittest.mock import patch

import pytest

import app as app_module  # noqa: F401  (route registration)
import print_monitor
import prusalink_api
import routes_state_pulse
from test_printer_contact_65_1 import NASTY_ESC, _monitor, _p, _tick, clock, logs  # noqa: F401  (fixtures)
from test_printer_status_even_rows import _size  # noqa: F401
from test_printer_status_strip_50 import _build, strip_page  # noqa: F401  (a fixture)


# --------------------------------------------------------------------------- #
# The ping                                                                    #
# --------------------------------------------------------------------------- #

def _reply(ip_header=False, kind=0):
    icmp = struct.pack("!BBHHH", kind, 0, 0, 1, 1) + b"fcc-reach"
    return (bytes([0x45]) + bytes(19) + icmp) if ip_header else icmp


class FakeSock:
    """An ICMP socket: `answers` is what recvfrom hands back in turn (a (data, addr)
    pair, or an exception to raise); `send_error` makes sendto raise."""

    def __init__(self, answers=(), send_error=None):
        self.answers = list(answers)
        self.send_error = send_error
        self.sent = []

    def settimeout(self, t):
        pass

    def sendto(self, packet, addr):
        if self.send_error:
            raise self.send_error
        self.sent.append((packet, addr))

    def recvfrom(self, n):
        if not self.answers:
            raise socket.timeout("timed out")
        nxt = self.answers.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    def close(self):
        pass


def _sockets(dgram=None, raw=None):
    """A stand-in for prusalink_api._icmp_socket: a FakeSock per kind, or the
    OSError a container without the capability raises."""
    def make(kind):
        sock = dgram if kind == socket.SOCK_DGRAM else raw
        if sock is None:
            raise PermissionError("Operation not permitted")
        return sock
    return make


@pytest.mark.parametrize("dgram,raw,want", [
    (FakeSock([(_reply(), ("10.0.0.9", 0))]), None, True),
    (None, FakeSock([(_reply(ip_header=True), ("10.0.0.9", 0))]), True),
    (None, None, None),
    (FakeSock([socket.timeout("timed out")]), None, False),
    (FakeSock(send_error=OSError(errno.EHOSTUNREACH, "No route to host")), None, False),
    (FakeSock([(_reply(), ("10.0.0.7", 0))]), None, False),                      # someone else's reply
    (None, FakeSock([(_reply(ip_header=True, kind=8), ("10.0.0.9", 0)),           # its own request seen raw
                     (_reply(ip_header=True), ("10.0.0.9", 0))]), True),
], ids=["datagram answered", "raw answered", "neither opens", "no answer", "no route", "another host",
        "own request then the reply"])
def test_one_echo_says_whether_the_printer_answers(dgram, raw, want):
    with patch.object(prusalink_api, "_icmp_socket", _sockets(dgram, raw)):
        assert prusalink_api.icmp_echo("10.0.0.9:80", timeout=0.2) is want
    sent = (dgram or raw).sent if (dgram or raw) else []
    assert all(addr == ("10.0.0.9", 0) for _p_, addr in sent), sent        # the port is ignored


def test_no_host_is_no_ping():
    assert prusalink_api.icmp_echo("") is None and prusalink_api.icmp_echo(None) is None


# --------------------------------------------------------------------------- #
# The verdict                                                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("echo,want", [(True, "prusalink"), (False, "none"), (None, None)])
def test_the_verdict_from_a_ping(monkeypatch, echo, want):
    asked = []
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials",
                        lambda fb, name: {"ip_address": "10.0.0.9", "api_key": "k"})
    monkeypatch.setattr(prusalink_api, "icmp_echo", lambda host, timeout=1.0: asked.append(host) or echo)
    prusalink_api._note_probe_failure("XL", "timeout")
    assert print_monitor._reach_verdict("XL") == want and asked == ["10.0.0.9"]


def test_a_refused_connection_proves_the_printer_is_there_with_no_ping(monkeypatch):
    monkeypatch.setattr(prusalink_api, "icmp_echo", lambda *a, **k: pytest.fail("pinged"))
    prusalink_api._note_probe_failure("XL", "refused")
    assert print_monitor._reach_verdict("XL") == "prusalink"


def test_no_ip_saved_cant_tell(monkeypatch):
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials", lambda fb, name: {"ip_address": ""})
    prusalink_api._note_probe_failure("XL", "timeout")
    assert print_monitor._reach_verdict("XL") is None


# --------------------------------------------------------------------------- #
# The monitor's lines                                                         #
# --------------------------------------------------------------------------- #

STUCK = ("XL is on the network, but PrusaLink isn't answering. Restarting the printer brings it back, but a "
         "restart ends a print: wait until its print is done.")
SILENT = "XL doesn't answer at all (off, or off the network)."


def _verdicts(monkeypatch, *seq):
    asked = []
    left = list(seq)

    def verdict(name):
        asked.append(name)
        return left.pop(0) if left else (seq[-1] if seq else None)
    monkeypatch.setattr(print_monitor, "_reach_verdict", verdict)
    return asked


def test_the_lost_line_says_why_while_printing(monkeypatch, logs):
    _verdicts(monkeypatch, "prusalink")
    _tick(monkeypatch, logs, _p("PRINTING"), None, None, None)
    assert logs == [(f"📡 Lost contact with XL: it was printing '{NASTY_ESC}' (~30%) when FCC last saw it. "
                     f"{STUCK}", "WARNING")]
    assert print_monitor.reach_of("XL") == "prusalink"


def test_an_idle_printer_that_doesnt_answer(monkeypatch, logs):
    _verdicts(monkeypatch, "none")
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)
    assert logs == [(f"📡 Lost contact with XL (it was idle). {SILENT}", "INFO")]


def test_an_idle_printer_with_prusalink_stuck_has_no_print_to_wait_for(monkeypatch, logs):
    _verdicts(monkeypatch, "prusalink")
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)
    assert logs[0][0].endswith("PrusaLink isn't answering. Restarting the printer brings it back."), logs


def test_when_fcc_cant_tell_it_keeps_todays_words(monkeypatch, logs):
    _verdicts(monkeypatch, None)
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)
    assert logs == [("📡 Lost contact with XL (it was idle).", "INFO")]
    assert print_monitor.reach_of("XL") is None


def test_a_change_of_verdict_is_said_once_and_asked_every_5_minutes(monkeypatch, logs, clock):
    asked = _verdicts(monkeypatch, "none", "prusalink", "prusalink")
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)          # lost: "none"
    clock["t"] += 120
    _tick(monkeypatch, logs, None)                                   # 2 min: not asked again
    assert len(asked) == 1
    clock["t"] += 200
    _tick(monkeypatch, logs, None)                                   # 5 min 20 s: asked, changed
    clock["t"] += 400
    _tick(monkeypatch, logs, None)                                   # asked again, the same: nothing
    assert len(asked) == 3
    assert [m for m, lvl in logs] == [f"📡 Lost contact with XL (it was idle). {SILENT}",
                                      "📡 XL is on the network, but PrusaLink isn't answering. Restarting the "
                                      "printer brings it back."]


def test_back_clears_the_verdict(monkeypatch, logs):
    _verdicts(monkeypatch, "none")
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None, _p("IDLE"))
    assert print_monitor.reach_of("XL") is None


# --------------------------------------------------------------------------- #
# The heartbeat and the badge                                                 #
# --------------------------------------------------------------------------- #

PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0}}


def _section(reach):
    with patch.object(routes_state_pulse.locations_db, "load_locations_list", return_value=[]), \
         patch.object(routes_state_pulse.locations_db, "get_active_printer_map", return_value=PRINTER_MAP), \
         patch.object(routes_state_pulse.config_loader, "load_config", return_value={}), \
         patch.object(routes_state_pulse.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(routes_state_pulse.spoolman_api, "bucket_spools_by_location", return_value={}), \
         patch.object(routes_state_pulse.spoolman_api, "get_all_spools", return_value=[]), \
         patch.object(routes_state_pulse.locations_db, "get_bindings_for_machine", return_value={"toolheads": {}}), \
         patch.object(routes_state_pulse.prusalink_api, "get_printer_state", return_value=None), \
         patch.object(print_monitor, "reach_of", lambda name: reach):
        return routes_state_pulse._pulse_section_printer_status()


def test_the_heartbeat_puts_reach_in_the_printers_own_payload():
    out = _section("prusalink")
    assert set(out) == {"XL"}, out                        # never a key of printer_status itself
    assert out["XL"]["reach"] == "prusalink" and out["XL"]["state"] is None, out
    assert "reach" not in _section(None)["XL"]


BADGES_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-state'))
    .map((b) => ({ chip: b.classList.contains('fcc-ps-state-chip'), printer: (b.closest('[data-printer]') || {}).dataset
        ? b.closest('[data-printer]').dataset.printer : null, label: b.textContent, title: b.title,
        aria: b.getAttribute('aria-label') }))"""


def test_the_offline_badge_says_why_in_its_tooltip_and_name(strip_page):
    page = strip_page
    page.set_viewport_size({"width": 1600, "height": 900})
    _build(page)
    fleet = {name: {"id": name, "state": None, "toolheads": [], **({"reach": reach} if reach else {})}
             for name, reach in (("A", "prusalink"), ("B", "none"), ("C", None))}
    page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", fleet)
    badges = [b for b in page.evaluate(BADGES_JS) if b["printer"]]
    by = {(b["printer"], b["chip"]): b for b in badges}
    stuck = ("On the network, but PrusaLink isn’t answering: restarting the printer brings it back, but wait "
             "until its print is done")
    for chip in (False, True):
        a, b, c = by[("A", chip)], by[("B", chip)], by[("C", chip)]
        assert a["label"] == b["label"] == c["label"] == "OFFLINE", badges
        assert (a["title"], a["aria"]) == (stuck, f"OFFLINE: {stuck}"), a
        assert (b["title"], b["aria"]) == ("Doesn’t answer at all (off, or off the network)",
                                           "OFFLINE: Doesn’t answer at all (off, or off the network)"), b
        assert (c["title"], c["aria"]) == ("Printer unreachable (offline, networked elsewhere, or cold-rebooting)",
                                           None), c
