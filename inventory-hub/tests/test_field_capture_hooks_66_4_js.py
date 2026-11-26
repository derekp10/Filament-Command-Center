"""Group 66.4, the shared field capture's new hooks (inv_core.js installFieldScanCapture).

The capture sends a label scanned into a box on to the scan path and puts the box's
text back. That is all it could put back: a label's keys land in the box one by one
before its Enter proves them a scan, and each key's events have already run the page's
listeners. The wizard needs more (its touched sets, its dirty flag, its marks, the
weight grid's sums), so the helper gains, each optional and leaving every existing
caller as it was:
  - `snapshot(el)`: called before a key that could start a scan lands (a run's first
    key, or one after a pause), and handed to `onScan` for the scan's first key;
  - `onScan(text, el, info)`: `info = {source, snapshot}`, the source the default path
    computes ('barcode' at scanner pace, else 'keyboard');
  - `keep(text, el)`: true lets the Enter reach the box untouched (a web address in a
    box that takes one);
  - `restoreEvent` (default true): false puts the box's text back with no `input` event,
    for a caller that puts its whole state back itself;
  - the consumed Enter's `keyup` no longer reaches the box (the wizard's weight boxes
    work out their sums on keyup);
  - a caller that gives no `isScanPayload` gets the page's rule (looksLikeScanPayload),
    not a TypeError inside the listener (the cross-check's C10).

Hermetic: overlay_mount.js and inv_core.js in `isolated_page`, the page's clock moved
only by the test, so a scanner's pace is exact. Each case marked RED fails on the
commit before this one for the reason it names.
"""
from __future__ import annotations

from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parents[1]
MODULES = HUB / "static" / "js" / "modules"

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<input id="labelled" type="text"><input id="plain" type="text"><input id="bare" type="text">
</body></html>"""

STUBS = r"""
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}), text: () => Promise.resolve('{}') });
window.__si = window.setInterval; window.setInterval = () => 0;
"""

INSTALL = r"""() => {
    window.setInterval = window.__si;
    window.__scans = [];
    window.__n = 0;
    window.processScan = (t, src) => { window.__scans.push(['default', t, src]); };
    const rec = (who) => (t, el, info) => { window.__scans.push([who, t,
        info ? info.source : 'no-info', info ? info.snapshot : 'no-info']); };
    window.installFieldScanCapture({
        match: (el) => el.id === 'labelled', isScanPayload: () => true, labels: true,
        snapshot: () => ++window.__n,
        keep: (t) => /^https?:/i.test(t),
        onScan: rec('labelled'),
        restoreEvent: false,
    });
    window.installFieldScanCapture({
        match: (el) => el.id === 'plain', isScanPayload: () => true,
        snapshot: () => ++window.__n,
        onScan: rec('plain'),
    });
    window.installFieldScanCapture({ match: (el) => el.id === 'bare', labels: true });
    window.__keyups = 0; window.__boxEnters = 0; window.__untrusted = 0;
    for (const id of ['labelled', 'plain', 'bare']) {
        const el = document.getElementById(id);
        el.addEventListener('keyup', (e) => { if (e.key === 'Enter') window.__keyups += 1; });
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.__boxEnters += 1; });
        el.addEventListener('input', (e) => { if (!e.isTrusted) window.__untrusted += 1; });
    }
}"""

# The page's clock moves only when a test says (Date.now), so a scanner's pace is exact.
FAKE_CLOCK = r"""() => { const base = Date.now(); window.__T = 0; Date.now = () => base + window.__T; }"""


@pytest.fixture
def boxes(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate(INSTALL)
    page.evaluate(FAKE_CLOCK)
    return page


def _type(page, box, text, gap):
    page.focus(box)
    for ch in text:
        page.evaluate("(g) => { window.__T += g; }", gap)
        page.keyboard.type(ch)


def _enter(page, gap=5):
    page.evaluate("(g) => { window.__T += g; }", gap)
    page.keyboard.press("Enter")


def _got(page):
    return page.evaluate("() => ({ scans: window.__scans, keyups: window.__keyups, enters: window.__boxEnters,"
                         " untrusted: window.__untrusted, errors: window.__errors })")


def test_on_scan_is_told_the_snapshot_at_the_labels_first_key(boxes):
    """A person's "q", a pause, then a label at scanner pace: the snapshot handed on is
    the one taken before the label's first key, not the run's. RED: no third argument."""
    _type(boxes, "#labelled", "q", 5)
    boxes.evaluate("() => { window.__T += 700; }")
    _type(boxes, "#labelled", "LOC:LR-MDB-1", 5)
    _enter(boxes)
    got = _got(boxes)
    assert got["scans"] == [["labelled", "LOC:LR-MDB-1", "barcode", 2]], got
    assert boxes.locator("#labelled").input_value() == "q"


@pytest.mark.parametrize("gap, source", [(5, "barcode"), (60, "keyboard")], ids=["scanner", "by-hand"])
def test_on_scan_is_told_the_source(boxes, gap, source):
    """RED: the custom onScan was never told it (Low stock hard-codes 'barcode')."""
    _type(boxes, "#labelled", "ID:57", gap)
    _enter(boxes, gap)
    assert [s[2] for s in _got(boxes)["scans"]] == [source]


@pytest.mark.parametrize("second", [False, True], ids=["one-enter", "cr-lf"])
def test_the_consumed_enters_keyup_never_reaches_the_box(boxes, second):
    """The box's own keyup hears no Enter of a scan (one Enter, or a CR LF scanner's two);
    a person's Enter a moment later is heard. RED: the scan's Enter keyups reached it."""
    _type(boxes, "#labelled", "ID:57", 5)
    _enter(boxes)
    if second:
        _enter(boxes, 3)
    got = _got(boxes)
    assert (len(got["scans"]), got["keyups"], got["enters"]) == (1, 0, 0), got
    _enter(boxes, 400)
    got = _got(boxes)
    assert (got["keyups"], got["enters"]) == (1, 1), got


def test_keep_lets_a_web_address_reach_the_box(boxes):
    """`keep` says the box takes it: the address and its Enter reach the box, nothing is
    sent on. A label in the same box is still a scan. RED: the address went to the scan
    path and the box was emptied."""
    url = "https://prusament.com/spool/17705/abc123def0/"
    _type(boxes, "#labelled", url, 5)
    _enter(boxes)
    got = _got(boxes)
    assert (got["scans"], got["enters"]) == ([], 1), got
    assert boxes.locator("#labelled").input_value() == url
    boxes.evaluate("() => { window.__T += 700; }")
    boxes.locator("#labelled").fill("")
    _type(boxes, "#labelled", "ID:57", 5)
    _enter(boxes)
    assert [s[1] for s in _got(boxes)["scans"]] == ["ID:57"]
    assert boxes.locator("#labelled").input_value() == ""


def test_restore_event_false_puts_the_text_back_quietly(boxes):
    """`restoreEvent: false`: the box gets its text back with no `input` event (its caller
    puts the rest back itself); the default still sends one (the location editor's pin,
    Group 61). RED: an event either way."""
    _type(boxes, "#labelled", "ID:57", 5)
    _enter(boxes)
    assert _got(boxes)["untrusted"] == 0
    boxes.evaluate("() => { window.__T += 700; }")
    _type(boxes, "#bare", "ID:57", 5)
    _enter(boxes)
    assert _got(boxes)["untrusted"] == 1


def test_the_old_burst_path_hands_on_its_snapshot(boxes):
    """A box with no labels mode: a burst after a person's "q" is put back to "q", and its
    onScan is told the snapshot taken as the burst began. RED: no third argument."""
    _type(boxes, "#plain", "q", 5)
    boxes.evaluate("() => { window.__T += 700; }")
    _type(boxes, "#plain", "ID:57", 5)
    _enter(boxes)
    got = _got(boxes)
    assert got["scans"] == [["plain", "ID:57", "barcode", 2]], got
    assert boxes.locator("#plain").input_value() == "q"


def test_a_capture_with_no_payload_rule_uses_the_pages(boxes):
    """The cross-check's C10: a caller that gives no isScanPayload. A label is still a
    scan, and nothing throws inside the listener. RED: a TypeError on the burst test, the
    scan lost and its Enter reaching the box."""
    _type(boxes, "#bare", "ID:57", 5)
    _enter(boxes)
    got = _got(boxes)
    assert got["scans"] == [["default", "ID:57", "barcode"]], got
    assert got["errors"] == [] and got["enters"] == 0, got
