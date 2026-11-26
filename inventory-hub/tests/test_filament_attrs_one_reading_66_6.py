"""Group 66.6: one reading of a filament's attribute tags, on the server and the page.

Since Group 54.3 the server reads an old record's text value ("Silk, Matte", or the
JSON string '"Silk, Matte"') as the tags Silk and Matte
(spoolman_api._parse_filament_attrs_value). Its other readers didn't:

  - the cards (format_spool_display), the search's filament cards and the label CSV's
    Type column (labels_csv.get_smart_type) read with json.loads only, so either old
    shape showed no tags ("PLA"), and a stray number in a list ('[5]') raised a
    TypeError out of the label export;
  - the page's parseFilamentAttributes (the spool and filament windows, Edit Filament)
    showed one chip, "Silk, Matte", and Edit Filament's Save baseline read the value as
    [], so every Save of such a filament sent ["Silk, Matte"], which Spoolman 0.27
    refuses: no edit of it could be saved;
  - the wizard's Edit Spool chips kept a value encoded twice as '"Silk' and 'Matte"'
    and a repeat as two chips; its label check (attrKey) saw one tag no chip list
    matched, so it flagged every spool's label at each Save of such a filament; and the
    Prusament backfill read it as no tags, so it wrote only the scanned tags over it.

Now one rule: window.fccFilamentAttrs (inv_core.js) mirrors the server exactly, and the
table below runs every shape through both. To make an exact mirror possible the server
rule was tightened where Python's str() has no JavaScript twin (Claude's call, offered
for veto): a list keeps only its text items, a JSON number is one tag as written ('1e5',
not '100000.0'), and JSON true / false / null or an object is none ('True', 'None' and
"{'a': 1}" were never tags, and Spoolman refuses them in a multi-choice list).

And the mend (Derek's (b), Claude's call): an Edit Filament Save that sends any extra
sends an old text value as the list the chips show, because Spoolman refuses the whole
write while it stays (the page copies every extra, and update_filament merges the stored
ones in), the shape the wizard's Edit Spool Save already writes. It stays out of the
Save's change set, so no label is flagged for a reprint.

Not covered: str.strip() and String.prototype.trim() disagree on a few exotic characters
(U+001C to U+001F and U+0085 are stripped only by Python, U+FEFF only by JavaScript);
no tag holds one. A value encoded twice in the raw wire form ('"\\"Silk, Matte\\""',
which no page receives: FCC decodes each extra once) reads with its quotes on both sides.

Hermetic: the server parts call the real functions with patched reads; the page parts run
the real modules under node (run_js) or in `isolated_page` (no network), so all of it runs
under --offline.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest

import labels_csv
import spoolman_api
from edit_filament_harness import (chips, errors, filament, load as load_details, open_form, posts_to,
                                   save)
from test_core1_return_ejectall_js import NODE, run_js
from test_search_api import _attr_filament, _attr_get
from test_wizard_label_status_58_5 import FIELDS as WIZ_FIELDS
from test_wizard_label_status_58_5 import _open_edit, _save, wizard  # noqa: F401  (the fixture)

needs_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

# (raw, the tags both sides read). `raw` as a reader receives it: the wire form, FCC's
# parsed form, or a stray type.
CASES = [
    (None, []),
    ("", []),
    ("[]", []),
    ('["Silk","Matte"]', ["Silk", "Matte"]),
    ('"Silk, Matte"', ["Silk", "Matte"]),                       # an old JSON string (the wire)
    ("Silk, Matte", ["Silk", "Matte"]),                         # the same, as FCC hands it on
    (json.dumps(json.dumps(["Silk", "Matte"])), ["Silk", "Matte"]),   # a string holding a list
    ("Silk,,Silk", ["Silk"]),
    (" Silk , Matte ", ["Silk", "Matte"]),
    (5, []),                                                    # a number itself is no tag
    ("7", ["7"]),                                               # a JSON number's text is one
    ('"5"', ["5"]),
    ('"true"', ["true"]),
    ('["Silk, Matte"]', ["Silk, Matte"]),                       # a list item is never split
    (["Silk, Matte", "Glow"], ["Silk, Matte", "Glow"]),
    ("  ", []),
    ('""', []),
    ('[" Silk ","Silk"]', [" Silk ", "Silk"]),                  # list items as they are
    (json.dumps('"Silk, Matte"'), ['"Silk', 'Matte"']),         # encoded twice, raw: no page gets it
    # The tightening (Claude's call): Python's str() of these has no JavaScript twin.
    ("true", []),
    ("null", []),
    ('{"a":1}', []),
    ("[5]", []),
    ("[null]", []),
    ('["Silk",5,null,"Matte"]', ["Silk", "Matte"]),
    (json.dumps(json.dumps(["Silk", 5])), ["Silk"]),
    ("1e5", ["1e5"]),
    ("NaN", ["NaN"]),
    ("-Infinity", ["-Infinity"]),
    (True, []),
    ({"Silk": True}, []),
]


@pytest.mark.parametrize("raw,want", CASES, ids=[repr(c[0])[:40] for c in CASES])
def test_the_server_reads_each_shape(raw, want):
    """RED on the base for the tightened rows only ('true' read ['True'], '[5]' ['5'],
    '1e5' ['100000.0'], ...); every other row is the 54.3 rule, green before and after."""
    assert spoolman_api._parse_filament_attrs_value(copy.deepcopy(raw)) == want


@needs_node
def test_the_page_reads_each_shape_the_same(tmp_path):
    """The page's window.fccFilamentAttrs gives exactly what the server gives, row by row.
    RED on the base: there was no helper (each page reader parsed in its own way)."""
    res = run_js(tmp_path, ["inv_core.js"], f"""
const CASES = {json.dumps([c for c, _ in CASES])};
return {{ out: (typeof window.fccFilamentAttrs === 'function') ? CASES.map((c) => window.fccFilamentAttrs(c)) : null }};
""")
    assert res["unhandled"] == []
    assert res["out"] == [w for _, w in CASES]


def _spool_with_attrs(raw):
    return {"id": 1, "remaining_weight": 500, "extra": {},
            "filament": {"id": 7, "name": "Red", "material": "PLA", "color_hex": "FF0000",
                         "vendor": {"name": "Acme"}, "extra": {"filament_attributes": raw}}}


@pytest.mark.parametrize("raw", ['"Silk, Matte"', "Silk, Matte"])
def test_a_card_shows_an_old_strings_tags(raw):
    """RED on the base: 'PLA' (json.loads only, so the old shapes showed no tags)."""
    assert spoolman_api.format_spool_display(_spool_with_attrs(raw))["details"]["material"] == "Silk Matte PLA"


@pytest.mark.parametrize("raw", ['["Silk","Matte"]', ["Silk", "Matte"]])
def test_a_cards_normal_list_is_unchanged(raw):
    """Control: a normal list reads exactly as it always did."""
    assert spoolman_api.format_spool_display(_spool_with_attrs(raw))["details"]["material"] == "Silk Matte PLA"


@pytest.mark.parametrize("raw", ['"Silk, Matte"', "Silk, Matte"])
@patch("spoolman_api.requests.get")
def test_a_search_filament_card_shows_an_old_strings_tags(mock_get, raw):
    """RED on the base: 'PLA'. The filament card's material carries the tags, as the
    spool cards' does."""
    fil = _attr_filament(401, "Comma", "PLA", raw)
    mock_get.side_effect = _attr_get(spools=[], filaments=[fil])
    got = spoolman_api.search_inventory(query="comma", target_type="filament")
    assert [r["id"] for r in got] == [401]
    assert got[0]["details"]["material"] == "Silk Matte PLA"


@pytest.mark.parametrize("raw", ['"Silk, Matte"', "Silk, Matte"])
def test_the_label_type_shows_an_old_strings_tags(raw):
    """RED on the base: 'PLA' (the label CSV's Type column dropped the old tags)."""
    assert labels_csv.get_smart_type("PLA", {"filament_attributes": raw}) == "Silk Matte PLA"


def test_a_stray_number_in_a_list_never_breaks_the_label_export():
    """RED on the base: a TypeError (clean_string's `if a` let 5 through, and ' '.join
    raised), which took down the whole label export for that spool."""
    assert labels_csv.get_smart_type("PLA", {"filament_attributes": "[5]"}) == "PLA"
    assert labels_csv.get_smart_type("PLA", {"filament_attributes": '["Silk", 5]'}) == "Silk PLA"


# --- The page: the details windows and Edit Filament -----------------------------------

OLD = "Silk, Matte"            # an old record's value as FCC's reads hand it to the page


@pytest.fixture
def details(isolated_page):
    return load_details(isolated_page)


def test_the_windows_read_an_old_string_as_its_tags(details):
    """The spool and filament windows draw their chip rows from parseFilamentAttributes.
    RED on the base: one chip, "Silk, Matte" (and a value encoded twice kept nothing
    apart). A normal list, and a cleaned item, read as before."""
    got = details.evaluate("""() => ({
        old: parseFilamentAttributes('Silk, Matte'),
        twice: parseFilamentAttributes('"Silk, Matte"'),
        list: parseFilamentAttributes(['Silk', ' Matte ', '', '"Glow"']),
        wire: parseFilamentAttributes('["Silk","Matte"]'),
        none: parseFilamentAttributes(null),
    })""")
    assert got == {"old": ["Silk", "Matte"], "twice": ["Silk", "Matte"], "list": ["Silk", "Matte", "Glow"],
                   "wire": ["Silk", "Matte"], "none": []}
    # The real row the windows show.
    details.evaluate("""() => renderReadonlyAttributeChips('fil-detail-attributes-row', 'fil-detail-attributes',
        parseFilamentAttributes('Silk, Matte'))""")
    assert details.evaluate("""() => Array.from(document.getElementById('fil-detail-attributes').children)
        .map((c) => c.textContent.trim())""") == ["Silk", "Matte"]


def test_edit_filament_shows_an_old_strings_tags_as_chips(details):
    """RED on the base: one chip, "Silk, Matte"."""
    open_form(details, filament(extra={"filament_attributes": OLD}))
    assert chips(details) == ["Silk", "Matte"]
    assert errors(details) == []


def test_an_untouched_save_of_an_old_string_sends_no_attributes(details):
    """A Save of the name alone sends the name alone. RED on the base: the chips read
    one tag and the baseline [], so it sent extra.filament_attributes '["Silk, Matte"]',
    which Spoolman refuses (no Save of such a filament could land)."""
    open_form(details, filament(extra={"filament_attributes": OLD}))
    details.locator("#editfil-name").fill("Red Two")
    save(details)
    sent = posts_to(details, "/api/update_filament")
    assert len(sent) == 1, sent
    assert sent[0]["body"] == {"id": 7, "data": {"name": "Red Two"}}
    assert errors(details) == []


def test_a_save_that_sends_an_extra_mends_an_old_string(details):
    """The mend (b): a Save that sends any extra (here the Product Link) sends the old
    text as the list the chips show, so Spoolman takes the write; the tags didn't change,
    so no label is flagged. RED on the base: '["Silk, Matte"]' went out (refused), with a
    label flag."""
    open_form(details, filament(extra={"filament_attributes": OLD}))
    details.locator("#editfil-tab-advanced-btn").click()
    details.locator("#editfil-product-url").fill("https://example.com/red")
    save(details)
    sent = posts_to(details, "/api/update_filament")
    assert len(sent) == 1, sent
    extra = sent[0]["body"]["data"]["extra"]
    assert extra["filament_attributes"] == '["Silk","Matte"]'
    assert extra["product_url"] == '"https://example.com/red"'
    details.wait_for_timeout(50)
    assert [p for p in details.evaluate("window.__posts") if "flag_spool_labels" in p["url"]] == []
    assert errors(details) == []


def test_a_normal_list_is_never_rewritten(details):
    """Control: a filament holding a real list keeps it as it was on an extras Save
    (the mend reads only a value that isn't a list)."""
    open_form(details, filament(extra={"filament_attributes": ["Silk", "Matte"]}))
    details.locator("#editfil-tab-advanced-btn").click()
    details.locator("#editfil-product-url").fill("https://example.com/red")
    save(details)
    extra = posts_to(details, "/api/update_filament")[0]["body"]["data"]["extra"]
    assert extra["filament_attributes"] == ["Silk", "Matte"]


def test_changed_chips_on_an_old_string_are_sent_as_the_person_left_them(details):
    """A chip removed is a change: the remaining tags go out as the list, and this time
    the label check does run (the tags did change)."""
    open_form(details, filament(extra={"filament_attributes": OLD}))
    details.locator("#editfil-attr-chips .editfil-chip[data-value='Matte'] .chip-x").click()
    assert chips(details) == ["Silk"]
    save(details)
    extra = posts_to(details, "/api/update_filament")[0]["body"]["data"]["extra"]
    assert extra["filament_attributes"] == '["Silk"]'
    # The label check ran (review round 1 of Group 66, R1-04: the docstring said so, and
    # nothing pinned it): the filament's spools' labels are flagged.
    details.wait_for_function("() => window.__posts.some((p) => p.url.split('?')[0] === '/api/filament/7/flag_spool_labels')")


# --- The wizard: Edit Spool's chips, its label check, the Prusament backfill ----------

ATTR_FIELD = {"entity_type": "filament", "field_type": "choice", "multi_choice": True,
              "key": "filament_attributes", "name": "Attributes", "choices": ["Silk", "Matte"], "order": 1}


def _with_attr_field(page):
    fields = copy.deepcopy(WIZ_FIELDS)
    fields["fields"]["filament"].insert(0, ATTR_FIELD)
    page.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", fields)


def _wiz_chips(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '#chip-container-fil-filament_attributes .dynamic-chip')).map((c) => c.getAttribute('data-value'))""")


@pytest.mark.parametrize("value,want", [
    ('"Silk, Matte"', ["Silk", "Matte"]),   # a value encoded twice, as the page receives it
    ("Silk,,Silk", ["Silk"]),
    ("Silk, Matte", ["Silk", "Matte"]),     # control: green on the base too
])
def test_the_wizards_edit_spool_chips_read_one_way(wizard, value, want):  # noqa: F811
    """RED on the base for the first two: chips '"Silk' and 'Matte"' (which its Save
    sends and Spoolman refuses), and Silk twice. The Save sends the chips as a list."""
    _with_attr_field(wizard)
    _open_edit(wizard, {"filament_attributes": value})
    assert _wiz_chips(wizard) == want
    assert _save(wizard, "/api/edit_spool_wizard")["filament_data"]["extra"]["filament_attributes"] == want


@needs_node
def test_the_wizards_label_check_and_backfill_read_an_old_string(tmp_path):
    """attrKey (the 23.3 label check) compares an old "Silk, Matte" with the chips
    Silk, Matte as equal; the Prusament backfill keeps the old tags and adds the scanned
    one. RED on the base: the label check flagged the spools' labels (one tag no chip list
    matched), and the backfill wrote ['Blend'] over Silk and Matte (it read no old tags)."""
    from test_head_load_confirm_js import PRELUDE
    res = run_js(tmp_path, ["inv_core.js", "inv_wizard.js"], PRELUDE + """
const label = window.wizardBuildFilamentLabelDiff(
    { extra: { filament_attributes: 'Silk, Matte' } },
    { extra: { filament_attributes: ['Matte', 'Silk'] } }).changedExtras;
const changed = window.wizardBuildFilamentLabelDiff(
    { extra: { filament_attributes: 'Silk, Matte' } },
    { extra: { filament_attributes: ['Silk'] } }).changedExtras;
const backfill = window.computeFilamentBackfillDiff(
    { id: 1, material: 'PC', extra: { filament_attributes: '"Silk, Matte"' } },
    { material: 'PC Blend', extra: {} }, ['Blend']);
return { label, changed, attrs: backfill.silent['extra.filament_attributes'] || null };
""")
    assert res["unhandled"] == []
    assert res["label"] == {}
    assert res["changed"] == {"filament_attributes": True}
    assert res["attrs"] == ["Silk", "Matte", "Blend"]
