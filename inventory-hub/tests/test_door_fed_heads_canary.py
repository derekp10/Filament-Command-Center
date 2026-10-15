"""Group 40.3 — offline source canary for the three move doors that can load a
bound box slot's toolhead: /api/identify_scan (its slot branch), /api/smart_move
and /api/manage_contents action add.

Every browser POST to them must either SEND `confirmed_fed_heads` and route the
server's questions through window.askMoveConfirm (so a head_fed answer gets the
three-way, never an invented "is PRINTING" yes / no), or sit on the EXEMPT list
below with the reason it can never load a head. A request without the key gets
logic.stale_fed_refusal's "reload the page" answer instead of the question,
and a handler that bypasses the dispatcher can't branch on head_fed.

Each door call is classified by the top-level function it sits in, and each
function's count of door calls is pinned, so a new call site fails here with
its file:line until it is classified. The behaviour itself is pinned per door
in test_head_load_confirm_js.py (bodies, dialogs, replays).

HEAD proof: on HEAD no function sends confirmed_fed_heads and askMoveConfirm
doesn't exist, so every "sends" row fails.
"""
import re
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
DOORS = ("/api/identify_scan", "/api/smart_move", "/api/manage_contents")
CALL_RE = re.compile(r"""\b(?:window\.)?fetch(?:T)?\(\s*(['"`])(%s)\1""" % "|".join(re.escape(d) for d in DOORS))

SENDS = "sends"
# file -> [(top-level function header, class, expected door calls, reason for an exemption)]
TABLE = {
    "inv_cmd.js": [
        ("const toggleAudit = ", "exempt", 1, "CMD:AUDIT / CMD:CANCEL: a command, never a slot label"),
        ("window.commitAuditWithAutoPark = ", "exempt", 1, "CMD:DONE: a command"),
        ("const processScan = ", SENDS, 2, None),           # the scan POST and a question's replay
        ("const performContextAssign = ", SENDS, 1, None),
    ],
    "inv_loc_mgr.js": [
        ("const _doAssignFinalize = ", SENDS, 1, None),      # grid taps, Swap / Overwrite, CMD:SLOT, ↩️
        ("window.ejectSpool = ", "exempt", 1, "the ✋ pickup: an ID: scan never moves a spool"),
        ("window.doEject = ", "exempt", 1, "action remove: an eject"),
        ("window.manualAddSpool = ", "exempt", 1,
         "ids only: LOC: / CMD: text goes through processScan (pinned in test_head_load_confirm_js)"),
        ("window.triggerEjectAll = ", "exempt", 1, "action clear_location (check_only)"),
        ("const _runEjectAll = ", "exempt", 1, "action clear_location"),
    ],
    "inv_quickswap.js": [
        ("window.quickSwapDeposit = ", SENDS, 1, None),
    ],
    "inv_details.js": [
        ("window.promptEditLocation = ", SENDS, 1, None),   # Force Location (add; force_unassign keeps its boolean)
    ],
    "inv_weigh_out.js": [
        ("window.saveSpoolWeight = ", "exempt", 1, "action force_unassign (the auto-archive)"),
    ],
}


def _read(path):
    return Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(src, header):
    """The function's text: from its header to the `};` at the header's indent."""
    start = src.index(header)
    line_start = src.rfind("\n", 0, start) + 1
    indent = src[line_start:start]
    end = src.find("\n" + indent + "};", start)
    assert end != -1, f"no end found for {header!r}"
    return src[start:end]


def _calls():
    """[(file, line, door, enclosing header or None)] for every door POST."""
    out = []
    files = sorted(MODULES.glob("*.js")) + sorted((HUB / "templates").rglob("*.html"))
    for path in files:
        src = _read(path)
        anchors = sorted((src.index(h), h) for h, *_ in TABLE.get(path.name, []) if h in src)
        for m in CALL_RE.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            owner = None
            for at, header in anchors:
                if at < m.start() and m.start() < at + len(_body(src, header)):
                    owner = header
            out.append((path.name, line, m.group(2), owner))
    return out


def test_every_door_call_is_classified_and_counted():
    calls = _calls()
    unclassified = [f"{f}:{ln} POST {d}" for f, ln, d, owner in calls if owner is None]
    assert not unclassified, ("door POSTs outside every classified function (send confirmed_fed_heads "
                              "and use askMoveConfirm, or add an exemption with its reason):\n"
                              + "\n".join(unclassified))
    for name, rows in TABLE.items():
        for header, _cls, expected, _why in rows:
            got = sum(1 for f, _ln, _d, owner in calls if f == name and owner == header)
            assert got == expected, f"{name} {header.strip()}: {got} door calls, the table says {expected}"


def test_the_canary_sees_every_door_call_site():
    """Guard the guard: a regex that stops matching would report green forever."""
    assert len(_calls()) == sum(r[2] for rows in TABLE.values() for r in rows) == 14


def test_every_sending_door_carries_the_key_and_asks_through_the_dispatcher():
    missing = []
    for name, rows in TABLE.items():
        src = _read(MODULES / name)
        for header, cls, _n, _why in rows:
            if cls != SENDS:
                continue
            body = _body(src, header)
            if "confirmed_fed_heads" not in body:
                missing.append(f"{name} {header.strip()}: sends no confirmed_fed_heads")
            if "askMoveConfirm(" not in body:
                missing.append(f"{name} {header.strip()}: its questions bypass window.askMoveConfirm")
    assert not missing, "\n".join(missing)


def test_every_exemption_says_why():
    for rows in TABLE.values():
        for header, cls, _n, why in rows:
            if cls != SENDS:
                assert why and len(why) > 10, header


def test_the_shared_question_api_exists():
    core = _read(MODULES / "inv_core.js")
    for name in ("window.unionConfirmFedHeads", "window.buildMoveReplay", "window.askMoveConfirm",
                 "window.confirmHeadLoad", "window.moveConfirmKind"):
        assert f"{name} =" in core, name
    route = _body(core, "window.routeConfirmScan = ")
    assert "STORE" in route
    # The three-way stays a mode of the one overlay: no second confirm overlay.
    head_load = _body(core, "window.confirmHeadLoad = ")
    assert "window.confirmActivePrint(" in head_load and "mountOverlay" not in head_load
