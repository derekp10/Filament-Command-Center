"""Group 54.2: a filament carrying all 28 attributes, on every window that shows them.

Derek (2026-08-03, the attribute suite's residual 2): "Highly unlikely in reality,
but we should make sure that having that many attributes doesn't break things like
it might be doing right now, so we should probably put in some tests for this kind
of thing, so that it's supported, even though it might not currently be possible."

Four windows draw a filament's attributes as chips:
  1. the spool window (#spool-detail-attributes, read-only chips),
  2. the filament window (#fil-detail-attributes, read-only chips),
  3. the Edit Filament form, the filament window's ✏️ Edit Filament
     (#editfil-attr-chips, each chip with its ×),
  4. the wizard's Edit Spool, its Custom Filament Attributes section
     (#chip-container-fil-filament_attributes).
The fifth surface, search, is checked offline: TestSearchWithAMaxAttributeFilament
in test_max_attributes_supported.py.

For each window, with all 28 chips drawn: there are 28, in the filament's order;
each chip is inside its box and inside the window; they take more than one row
(they wrap); neither the box, the window's body nor the window's frame scrolls
sideways, and nor does the page; the window fits the screen; and the controls
after the chips can still be reached (scrolled to, inside the window, on the
screen and not covered): the next field and the window's last button.

At 1600x1300, and on a small laptop (1366x768) at Text size Extra Large, every
check holds. At a 390 px phone the chips hold too; what fails there is two
windows' footers, the same with one attribute as with 28, so it is recorded for
the phone-view work (PHONE_KNOWN) rather than fixed here. A finding that isn't on
that list fails the phone run, and so does an entry that no longer happens (take
it off the list once the phone view is fixed).

The real dashboard on the dev container, with real Bootstrap: a hermetic page has
none, since it loads from a CDN, and a stand-in would prove only the stand-in.
Every read the windows make is answered in the browser from the made-up records
below, every request that isn't a read is answered in the browser too, and the
dashboard's own heartbeat and log polls are cut off (conftest.quiet_heartbeat:
nothing live repaints a window while it is measured, and no "N new" log pill
floats over it). Nothing reaches dev's Spoolman or its shared buffer, and nothing
is saved.

The proof that the checks bite (Group 54.2's build log): the same run with the
stub cut to one attribute (ATTRS) fails on the count and the rows, with the 28 in
reverse order on the order, with the chip boxes made not to wrap
(EXTRA_CSS = NOWRAP_CSS) on the overflow and reach checks, and with them also
held to their line's width on the box checks.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page

import conftest
from test_max_attributes_supported import ALL_CHOICES

pytestmark = pytest.mark.usefixtures("require_server")

# What the stub's filament carries, and CSS added after the page loads. The proof
# that the checks bite sets these from a scratch plugin; a normal run leaves them.
ATTRS = list(ALL_CHOICES)
EXTRA_CSS = ""
NOWRAP_CSS = ("#spool-detail-attributes, #fil-detail-attributes, #editfil-attr-chips,"
              " #chip-container-fil-filament_attributes { flex-wrap: nowrap !important; }")

SPOOL_ID, FIL_ID, VENDOR_ID = 9541, 9542, 9543
DESKTOP = {"width": 1600, "height": 1300}
LAPTOP = {"width": 1366, "height": 768}
PHONE = {"width": 390, "height": 844}

# At a 390 px phone two windows' footers don't fit: each footer's row of buttons
# doesn't wrap, so its Close sticks out past the window's right edge and the
# window's frame scrolls sideways (the spool window's 435 px of content in 390 px,
# the filament window's 392). It is exactly the same with one attribute as with 28
# (Group 54.2's build log), so it is the phone view's, not the attributes': it is
# recorded here for the phone-view work rather than fixed. Per window, the first
# entry (its Close sticking out) must still happen; the rest may.
PHONE_KNOWN = {
    "the spool window": ("#btn-spool-close sticks out of the window", "the window's frame scrolls sideways"),
    "the filament window": ("#btn-fil-close sticks out of the window", "the window's frame scrolls sideways"),
}

# POSTs that only read (the buffer cards' refresh). Every other request that
# isn't a GET is answered in the page.
READ_POSTS = {"/api/spools/refresh"}


def _vendor():
    return {"id": VENDOR_ID, "name": "Example Brand", "empty_spool_weight": 200.0, "comment": "",
            "external_id": "", "registered": "2026-01-01T00:00:00Z", "extra": {}}


def _filament():
    return {
        "id": FIL_ID, "name": "Ocean Blue", "material": "PLA", "color_hex": "1E6FD9",
        "density": 1.24, "diameter": 1.75, "weight": 1000.0, "spool_weight": 200.0, "price": 25.0,
        "settings_extruder_temp": 215, "settings_bed_temp": 60, "comment": "", "tags": [],
        "external_id": "", "registered": "2026-01-01T00:00:00Z", "vendor": _vendor(),
        # Spoolman's wire form of a multi-choice extra: a JSON list in a string.
        "extra": {"filament_attributes": json.dumps(ATTRS), "original_color": '"Ocean Blue"'},
    }


def _spool():
    return {"id": SPOOL_ID, "archived": False, "location": "TEST-SHELF", "comment": "",
            "used_weight": 250.0, "initial_weight": 1000.0, "remaining_weight": 750.0,
            "spool_weight": 196.0, "price": 30.0, "tags": [], "registered": "2026-01-01T00:00:00Z",
            "extra": {}, "filament": _filament()}


def _field(key, name, field_type, order, choices=None, multi=None, entity="filament"):
    f = {"entity_type": entity, "key": key, "name": name, "field_type": field_type, "order": order}
    if choices is not None:
        f["choices"] = list(choices)
        f["multi_choice"] = bool(multi)
    return f


def _fields():
    """The extra fields, shaped like Spoolman's, with every attribute a choice."""
    return {
        "filament": [
            _field("filament_attributes", "Filament Attributes", "choice", 0, ALL_CHOICES, multi=True),
            _field("shore_hardness", "Shore Hardness", "choice", 1, ["95A"]),
            _field("slicer_profile", "Slicer Profile", "choice", 2, ["Generic PLA", "Generic PETG"]),
            _field("product_url", "Product Link", "text", 3),
            _field("purchase_url", "Purchase Link", "text", 4),
            _field("original_color", "Original Color", "text", 7),
            _field("drying_temp", "Drying Temp", "text", 10),
            _field("drying_time", "Drying Time", "text", 11),
            _field("needs_label_print", "Needs Label Print", "boolean", 14),
            _field("sample_printed", "Sample Printed", "boolean", 15),
        ],
        "spool": [
            _field("spool_type", "Spool Type", "choice", 0, ["Cardboard", "Plastic"], entity="spool"),
            _field("container_slot", "Container / MMU Slot", "text", 2, entity="spool"),
            _field("product_url", "Product Link", "text", 5, entity="spool"),
            _field("purchase_url", "Purchase Link", "text", 6, entity="spool"),
            _field("needs_label_print", "Needs Label Print", "boolean", 13, entity="spool"),
        ],
    }


LOCATIONS = [
    {"LocationID": "Unassigned", "Name": "Workbench / Unsorted", "Type": "Virtual", "Max Spools": 0,
     "Occupancy": "0 items", "Synthesized": True, "parent_id": None},
    {"LocationID": "TEST-ROOM", "Name": "Test Room", "Type": "Room", "Max Spools": "0",
     "Occupancy": "1 Total", "OccupancyRaw": 1, "parent_id": None},
    {"LocationID": "TEST-SHELF", "Name": "Test Shelf", "Type": "Shelf", "Max Spools": "0",
     "Occupancy": "1 Total", "OccupancyRaw": 1, "parent_id": "TEST-ROOM"},
]


def _stub_reads(page: Page) -> None:
    """Every read the four windows make, answered in the browser; every request
    that isn't a read answered there too. Install before page.goto."""
    fil, spool = _filament(), _spool()
    listed = {k: v for k, v in spool.items() if k != "filament"}
    listed["filament"] = {"id": FIL_ID}
    served = {
        "/api/spool_details": spool,
        "/api/filament_details": fil,
        "/api/spools_by_filament": [listed],
        "/api/external/fields": {"success": True, "fields": _fields()},
        "/api/materials": {"success": True, "materials": ["PETG", "PLA"]},
        "/api/vendors": {"success": True, "vendors": [_vendor()]},
        "/api/external/vendors": {"success": True, "vendors": [_vendor()]},
        "/api/filaments": {"success": True, "filaments": [fil]},
        "/api/locations": LOCATIONS,
    }

    def handle(route, request):
        path = urlparse(request.url).path
        method = request.method.upper()
        if method == "GET":
            if path in served:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(served[path]),
                              headers={"X-FCC-Spool-Read": "ok"})
            else:
                route.continue_()
            return
        if method == "POST" and path in READ_POSTS:
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json", body="{}")

    page.route("**/api/**", handle)
    # Later routes win over the one above: the page's own scan buffer, empty, and
    # no heartbeat or log poll.
    conftest.own_the_buffer(page, [])
    conftest.quiet_heartbeat(page)


# What each window is: its chips, their box, the window (.modal-content), its body,
# its frame (the .modal, which scrolls a dialog that isn't scrollable itself), and
# the controls after the chips that must still be reachable.
WINDOWS = {
    "the spool window": {
        "host": "#spool-detail-attributes", "chip": ".fcc-attr-chip",
        "window": "#spoolModal .modal-content", "body": "#spoolModal .modal-body", "frame": "#spoolModal",
        "next": ["#detail-comment", "#btn-spool-close"],
    },
    "the filament window": {
        "host": "#fil-detail-attributes", "chip": ".fcc-attr-chip",
        "window": "#filamentModal .modal-content", "body": "#filamentModal .modal-body",
        "frame": "#filamentModal",
        "next": ["#fil-detail-comment", "#btn-fil-edit", "#btn-fil-close"],
    },
    "the Edit Filament form": {
        "host": "#editfil-attr-chips", "chip": ".editfil-chip",
        "window": "#editFilamentModal .modal-content", "body": "#editFilamentModal .modal-body",
        "frame": "#editFilamentModal",
        "next": ["#editfil-attr-input", "#editfil-comment", "#editfil-save"],
    },
    "the wizard's Edit Spool": {
        "host": "#chip-container-fil-filament_attributes", "chip": ".dynamic-chip",
        "window": "#wizardModal .modal-content", "body": "#wizardModal .modal-body", "frame": "#wizardModal",
        "next": ["#wiz_fil_ef_filament_attributes",
                 "[data-extra-key='filament_attributes'] .wizard-multichoice-add",
                 "#wiz_fil_ef_slicer_profile", "#btn-wiz-submit"],
    },
}

MEASURE_JS = """(spec) => {
    const q = (s) => document.querySelector(s);
    const px = (n) => Math.round(n * 10) / 10;
    const out = {count: 0, names: [], rows: 0, problems: []};
    const host = q(spec.host), win = q(spec.window), body = q(spec.body), frame = q(spec.frame);
    for (const [el, sel] of [[host, spec.host], [win, spec.window], [body, spec.body], [frame, spec.frame]]) {
        if (!el) { out.problems.push(`${sel} isn't on the page`); return out; }
    }
    const chips = Array.from(host.querySelectorAll(spec.chip));
    out.count = chips.length;
    out.names = chips.map(c => (c.getAttribute('data-value') || c.textContent).replace('\\u00d7', '').trim());
    const hr = host.getBoundingClientRect(), wr = win.getBoundingClientRect();
    const tops = [];
    chips.forEach((c, i) => {
        const r = c.getBoundingClientRect();
        const name = out.names[i];
        if (r.width < 1 || r.height < 1) { out.problems.push(`"${name}" isn't drawn`); return; }
        tops.push(r.top);
        if (r.left < hr.left - 0.5 || r.right > hr.right + 0.5 || r.top < hr.top - 0.5 || r.bottom > hr.bottom + 0.5)
            out.problems.push(`"${name}" sticks out of its box (chip x ${px(r.left)} to ${px(r.right)},`
                + ` y ${px(r.top)} to ${px(r.bottom)}; box x ${px(hr.left)} to ${px(hr.right)},`
                + ` y ${px(hr.top)} to ${px(hr.bottom)})`);
        if (r.left < wr.left - 0.5 || r.right > wr.right + 0.5)
            out.problems.push(`"${name}" sticks out of the window (chip x ${px(r.left)} to ${px(r.right)};`
                + ` window x ${px(wr.left)} to ${px(wr.right)})`);
    });
    tops.sort((a, b) => a - b);
    out.rows = tops.length ? 1 + tops.slice(1).filter((t, i) => t - tops[i] > 2).length : 0;
    const sideways = (el, what) => {
        if (el.scrollWidth > el.clientWidth + 1)
            out.problems.push(`${what} scrolls sideways (${el.scrollWidth} px of content in ${el.clientWidth} px)`);
    };
    sideways(host, 'the chips box');
    sideways(body, "the window's body");
    sideways(frame, "the window's frame");
    const page = document.documentElement;
    if (page.scrollWidth > Math.max(page.clientWidth, spec.pageWidth) + 1)
        out.problems.push(`the page scrolls sideways (${page.scrollWidth} px of content in ${page.clientWidth} px)`);
    if (wr.left < -0.5 || wr.right > innerWidth + 0.5)
        out.problems.push(`the window is wider than the screen (x ${px(wr.left)} to ${px(wr.right)} of ${innerWidth})`);
    return out;
}"""

# Scrolls `sel` to the middle of whatever scrolls it up and down (never sideways:
# a person can't scroll a dialog's frame sideways), then says why it can't be
# reached, or '' when it can.
REACH_JS = """({sel, win}) => {
    const el = document.querySelector(sel);
    if (!el) return `${sel} isn't on the page`;
    const px = (n) => Math.round(n * 10) / 10;
    for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
        const oy = getComputedStyle(a).overflowY;
        if ((oy !== 'auto' && oy !== 'scroll') || a.scrollHeight <= a.clientHeight + 1) continue;
        const ar = a.getBoundingClientRect(), r0 = el.getBoundingClientRect();
        a.scrollTop += (r0.top + r0.height / 2) - (ar.top + ar.height / 2);
    }
    const r = el.getBoundingClientRect(), w = document.querySelector(win).getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return `${sel} isn't drawn`;
    if (r.left < w.left - 0.5 || r.right > w.right + 0.5)
        return `${sel} sticks out of the window (x ${px(r.left)} to ${px(r.right)}; window x ${px(w.left)} to ${px(w.right)})`;
    if (r.left < -0.5 || r.right > innerWidth + 0.5 || r.top < -0.5 || r.bottom > innerHeight + 0.5)
        return `${sel} is off the screen (x ${px(r.left)} to ${px(r.right)}, y ${px(r.top)} to ${px(r.bottom)})`;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || !(hit === el || el.contains(hit))) {
        const what = hit ? (hit.tagName.toLowerCase() + (hit.id ? '#' + hit.id : '')
            + (hit.className && typeof hit.className === 'string' ? '.' + hit.className.trim().split(/ +/).join('.') : '')) : 'nothing';
        return `${sel} is covered by ${what}`;
    }
    return '';
}"""


def _shown(page: Page, modal_id: str, opener_js: str) -> None:
    """Run `opener_js` and wait for Bootstrap's shown.bs.modal on `modal_id`."""
    page.evaluate("""(id) => { window.__fccShown = window.__fccShown || {};
        const el = document.getElementById(id);
        el.addEventListener('shown.bs.modal', () => { window.__fccShown[id] = true; }, { once: true });
        window.__fccShown[id] = false; }""", modal_id)
    page.evaluate(opener_js)
    page.wait_for_function("(id) => window.__fccShown[id] === true", arg=modal_id, timeout=15_000)
    page.wait_for_timeout(300)


def _hide(page: Page, modal_id: str) -> None:
    conftest.wait_modal_settled(page, modal_id)
    page.evaluate("""(id) => { const m = bootstrap.Modal.getInstance(document.getElementById(id));
        if (m) m.hide(); }""", modal_id)
    page.wait_for_function("(id) => { const el = document.getElementById(id);"
                           " return !el.classList.contains('show') && getComputedStyle(el).display === 'none'; }",
                           arg=modal_id, timeout=10_000)


def _check(page: Page, spec: dict, page_width: int) -> list:
    m = page.evaluate(MEASURE_JS, {**spec, "pageWidth": page_width})
    problems = list(m["problems"])
    if m["count"] != len(ALL_CHOICES):
        problems.append(f"{m['count']} chips, not {len(ALL_CHOICES)}")
    elif m["names"] != ALL_CHOICES:
        problems.append(f"the chips read {m['names']}, not the filament's {ALL_CHOICES}")
    if m["rows"] < 2:
        problems.append(f"the chips take {m['rows']} row(s): they don't wrap")
    for sel in spec["next"]:
        why = page.evaluate(REACH_JS, {"sel": sel, "win": spec["window"]})
        if why:
            problems.append(why)
    return problems


def _walk(page: Page, base_url: str, viewport: dict, text_size: str = "") -> dict:
    """Open the four windows one after another, as a person would, and check each.
    `text_size`: the Text size setting's name ("Extra Large"), or '' for the
    default. Answers {window: [problems]}."""
    page.set_viewport_size(viewport)
    if text_size:
        page.add_init_script(f"try {{ localStorage.setItem('fcc.textSize', {json.dumps(text_size)}); }}"
                             " catch (e) {}")
    _stub_reads(page)
    page.goto(base_url)
    page.wait_for_function("() => typeof openSpoolDetails === 'function' && typeof openFilamentDetails === 'function'"
                           " && typeof window.openEditWizard === 'function' && typeof state !== 'undefined'"
                           " && state.locationsLoaded", timeout=45_000)
    if text_size:
        # The root grows with Large / Extra Large (112.5 % / 125 %): the setting took.
        expect_px = {"Standard": 16, "Large": 18, "Extra Large": 20}[text_size]
        assert page.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)") == expect_px
    if EXTRA_CSS:
        page.add_style_tag(content=EXTRA_CSS)
    # The page's own width before any window opens: a window may not widen it.
    page_width = page.evaluate("() => document.documentElement.scrollWidth")
    found = {}

    _shown(page, "spoolModal", f"() => openSpoolDetails({SPOOL_ID})")
    found["the spool window"] = _check(page, WINDOWS["the spool window"], page_width)
    _hide(page, "spoolModal")

    _shown(page, "filamentModal", f"() => openFilamentDetails({FIL_ID})")
    found["the filament window"] = _check(page, WINDOWS["the filament window"], page_width)
    # The filament window's ✏️ Edit Filament opens the form over it.
    _shown(page, "editFilamentModal", "() => document.getElementById('btn-fil-edit').click()")
    found["the Edit Filament form"] = _check(page, WINDOWS["the Edit Filament form"], page_width)
    _hide(page, "editFilamentModal")
    _hide(page, "filamentModal")

    page.evaluate(f"() => {{ window.openEditWizard({SPOOL_ID}); }}")
    page.wait_for_function("() => { const m = document.getElementById('wizardModal');"
                           " return m.classList.contains('show') && wizardState.mode === 'edit_spool'"
                           " && document.getElementById('wiz-status-msg').innerText.includes('Editing Spool')"
                           " && !document.getElementById('btn-wiz-submit').disabled; }", timeout=20_000)
    conftest.wait_modal_settled(page, "wizardModal")
    # Every optional section opens closed: open Custom Filament Attributes as a
    # person does, by its toggle.
    page.locator("button.fcc-wiz-section-toggle[data-bs-target='#wiz-fil-extras-panel']").click()
    page.wait_for_function("() => { const p = document.getElementById('wiz-fil-extras-panel');"
                           " return p.classList.contains('show') && !p.classList.contains('collapsing'); }",
                           timeout=10_000)
    page.wait_for_timeout(700)      # the section's own smooth scroll, when it takes one
    found["the wizard's Edit Spool"] = _check(page, WINDOWS["the wizard's Edit Spool"], page_width)
    conftest.close_wizard(page)
    return found


def _listed(found: dict) -> str:
    return "\n".join(f"{w}:\n  " + "\n  ".join(p) for w, p in found.items())


@pytest.mark.parametrize("viewport, text_size", [(DESKTOP, ""), (LAPTOP, "Extra Large")],
                         ids=["1600x1300", "1366x768-extra-large"])
def test_28_attributes_fit_every_window(page: Page, base_url: str, viewport, text_size):
    found = _walk(page, base_url, viewport, text_size)
    bad = {w: p for w, p in found.items() if p}
    assert not bad, _listed(bad)


def test_28_attributes_fit_every_window_on_a_phone_but_two_footers(page: Page, base_url: str):
    """390 px: everything holds but PHONE_KNOWN (the phone view's, not the attributes')."""
    found = _walk(page, base_url, PHONE)
    new = {w: [p for p in ps if not p.startswith(PHONE_KNOWN.get(w, ()))] for w, ps in found.items()}
    new = {w: ps for w, ps in new.items() if ps}
    assert not new, "new at a phone's width:\n" + _listed(new)
    gone = [w for w, known in PHONE_KNOWN.items() if not any(p.startswith(known[0]) for p in found[w])]
    assert not gone, (f"{gone}: its Close no longer sticks out at a phone's width. If the phone view"
                      " fixed its footer, take it off PHONE_KNOWN. What it found:\n" + _listed(found))
