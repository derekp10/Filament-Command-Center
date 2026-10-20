import pytest
import requests
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
import spoolman_api

# Mock spoolman response data
MOCK_SPOOLS = [
    {
        "id": 1,
        "remaining_weight": 1000,
        "location": "Shelf A",
        "filament": {
            "name": "Standard PLA",
            "material": "PLA",
            "color_hex": "FF0000",
            "vendor": {"name": "Prusament"},
            "extra": {"original_color": "Lipstick Red"}
        }
    },
    {
        "id": 2,
        "remaining_weight": 0,
        "location": "Trash",
        "filament": {
            "name": "Galaxy Black",
            "material": "PETG",
            "color_hex": "000000",
            "vendor": {"name": "Prusament"},
            "extra": {"original_color": "Space Black"}
        }
    },
    {
        "id": 3,
        "remaining_weight": 500,
        "location": "Shelf B",
        "filament": {
            "name": "Silk White",
            "material": "PLA",
            "color_hex": "FFFFFF",
            "multi_color_hexes": "00FF00,0000FF",  # Gradient for testing (No Red)
            "vendor": {"name": "Generic"},
            "extra": {"original_color": "Bone White"}
        }
    }
]

MOCK_FILAMENTS = [
    {
        "id": 99,
        "name": "Silk White",
        "material": "PLA",
        "color_hex": "FFFFFF",
        "vendor": {"name": "Generic"},
        "extra": {"original_color": "Bone White"}
    }
]

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

@patch('spoolman_api.requests.get')
def test_search_spools_basic_query(mock_get):
    """Test tokenized fuzzy matching by text fields."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    # Strict token search matching "PLA" and "Black" in id 2 context
    results = spoolman_api.search_inventory(query="black petg")
    assert len(results) == 1
    assert results[0]['id'] == 2
    
    # Assert Order doesn't matter (tokenization)
    results = spoolman_api.search_inventory(query="petg black")
    assert len(results) == 1
    assert results[0]['id'] == 2
    
    results = spoolman_api.search_inventory(query="PLA")
    assert len(results) == 2

@patch('spoolman_api.requests.get')
def test_search_spools_color_hex(mock_get):
    """Test Euclidean distance sorting for colors, including multi-color gradient support."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    # #FEEFEF is very close to white (FFFFFF), however ID 3 defines a multi_color_hexes of RED, GREEN, BLUE.
    # So if we search for Pure Green (#00FF00), ID 3 should win because its multi_color gradient contains Green.
    results = spoolman_api.search_inventory(color_hex="#00FF00")
    assert len(results) == 3
    assert results[0]['id'] == 3 # ID 3 contains the exact green in its gradient

    # #880000 is closest to red (FF0000), ID 1 should be first
    results = spoolman_api.search_inventory(color_hex="#880000")
    assert len(results) == 3
    assert results[0]['id'] == 1

@patch('spoolman_api.requests.get')
def test_search_spools_stock_filters(mock_get):
    """Test only_in_stock and empty parameters for spools."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    results = spoolman_api.search_inventory(only_in_stock=True)
    assert len(results) == 2
    assert 2 not in [r['id'] for r in results]

    results = spoolman_api.search_inventory(empty=True)
    assert len(results) == 1
    assert results[0]['id'] == 2

@patch('spoolman_api.requests.get')
def test_search_filament_target_type(mock_get):
    """Test searching raw filaments instead of spools."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_FILAMENTS
    mock_get.return_value = mock_response

    results = spoolman_api.search_inventory(query="Silk", target_type="filament")
    assert len(results) == 1
    assert results[0]['id'] == 99
    assert results[0]['type'] == 'filament'

def test_api_endpoint(client):
    """Test the Flask API endpoint wrapper."""
    with patch('spoolman_api.search_inventory') as mock_search:
        mock_search.return_value = [{"id": 99, "display": "Mock Spool"}]
        
        response = client.get('/api/search?q=test&material=PLA&in_stock=true&type=filament')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == 99
        
        # Verify the arguments were passed to the logic layer correctly.
        # min_weight was added to search_inventory; tests must include it.
        mock_search.assert_called_once_with(
            query="test",
            material="PLA",
            vendor="",
            color_hex="",
            only_in_stock=True,
            empty=False,
            target_type="filament",
            min_weight="",
            max_weight="",
            deployed_state="",
            sort="",
        )


@patch('spoolman_api.requests.get')
def test_search_filaments_sort_by_spool_count(mock_get):
    """L21 — filament results can be sorted by spool count (most or
    fewest available). The endpoint already populates `spools_count`
    on every filament result by counting matching spools; the sort
    just orders by it. Spool-side results ignore the sort token."""
    mock_filaments = [
        {"id": 1, "name": "Alpha", "material": "PLA", "color_hex": "111111",
         "vendor": {"name": "Acme"}, "extra": {}},
        {"id": 2, "name": "Beta",  "material": "PLA", "color_hex": "222222",
         "vendor": {"name": "Acme"}, "extra": {}},
        {"id": 3, "name": "Gamma", "material": "PLA", "color_hex": "333333",
         "vendor": {"name": "Acme"}, "extra": {}},
    ]
    # Spool list: filament 2 has 3 spools, filament 3 has 1, filament 1 has 0.
    mock_spools = [
        {"id": 10, "remaining_weight": 100, "filament": {"id": 2, "vendor": {}}},
        {"id": 11, "remaining_weight": 200, "filament": {"id": 2, "vendor": {}}},
        {"id": 12, "remaining_weight": 300, "filament": {"id": 2, "vendor": {}}},
        {"id": 13, "remaining_weight": 50,  "filament": {"id": 3, "vendor": {}}},
    ]

    def _fake_get(url, timeout=10):
        resp = MagicMock()
        resp.ok = True
        if 'filament' in url:
            resp.json.return_value = mock_filaments
        else:
            resp.json.return_value = mock_spools
        return resp
    mock_get.side_effect = _fake_get

    desc = spoolman_api.search_inventory(target_type="filament", sort="spools_desc")
    assert [r['id'] for r in desc] == [2, 3, 1]
    assert desc[0]['spools_count'] == 3
    assert desc[1]['spools_count'] == 1
    assert desc[2]['spools_count'] == 0

    asc = spoolman_api.search_inventory(target_type="filament", sort="spools_asc")
    assert [r['id'] for r in asc] == [1, 3, 2]


# --- Group 49.1: filament attributes are searchable text ---------------------
#
# Spoolman stores filament_attributes as a JSON-encoded list on the wire
# ('["For Infill"]'); parse_inbound_data decodes it. The cards print the tags
# in front of the material ("For Infill PLA"), so a tag you can see on a card
# must be findable by typing it.

def _attr_filament(fid, name, material, attrs_wire, color="Grey"):
    return {"id": fid, "name": name, "material": material, "color_hex": "888888",
            "vendor": {"name": "Acme"},
            "extra": {"original_color": f'"{color}"', "filament_attributes": attrs_wire}}


ATTR_FILAMENTS = [
    _attr_filament(175, "Transition Spool", "PLA", '["For Infill"]', color="Mixed"),
    _attr_filament(176, "Plain Jane", "PLA", '[]', color="White"),
    _attr_filament(177, "Velvet", "PLA", '["Matte"]', color="Black"),
    _attr_filament(178, "Shiny", "PETG", '["Matte", "Silk"]', color="Gold"),
    # No filament_attributes key at all.
    {"id": 179, "name": "Bare", "material": "ABS", "color_hex": "111111",
     "vendor": {"name": "Acme"}, "extra": {}},
]

ATTR_SPOOLS = [
    {"id": 501, "remaining_weight": 300, "location": "Shelf A", "filament": ATTR_FILAMENTS[0]},
    {"id": 502, "remaining_weight": 800, "location": "Shelf A", "filament": ATTR_FILAMENTS[1]},
    {"id": 503, "remaining_weight": 120, "location": "Shelf B", "filament": ATTR_FILAMENTS[2]},
    {"id": 504, "remaining_weight": 950, "location": "Shelf B", "filament": ATTR_FILAMENTS[3]},
    {"id": 505, "remaining_weight": 410, "location": "Shelf C", "filament": ATTR_FILAMENTS[4]},
]


def _attr_get(spools=None, filaments=None):
    """A fake requests.get answering the spool and filament lists (fresh copies,
    since parse_inbound_data decodes the extras in place)."""
    import copy

    def _fake_get(url, timeout=10):
        resp = MagicMock()
        resp.ok = True
        if '/filament' in url:
            resp.json.return_value = copy.deepcopy(filaments if filaments is not None else ATTR_FILAMENTS)
        else:
            resp.json.return_value = copy.deepcopy(spools if spools is not None else ATTR_SPOOLS)
        return resp
    return _fake_get


@patch('spoolman_api.requests.get')
def test_attribute_word_finds_the_tagged_filament(mock_get):
    """49.1 — "infill" finds Derek's For Infill filament in filament mode."""
    mock_get.side_effect = _attr_get()
    results = spoolman_api.search_inventory(query="infill", target_type="filament")
    assert [r['id'] for r in results] == [175]


@patch('spoolman_api.requests.get')
def test_attribute_word_finds_the_spools_of_the_tagged_filament(mock_get):
    """49.1 — and its spools in spool mode."""
    mock_get.side_effect = _attr_get()
    results = spoolman_api.search_inventory(query="infill")
    assert [r['id'] for r in results] == [501]


@patch('spoolman_api.requests.get')
def test_multi_word_tag_works_through_the_every_token_rule(mock_get):
    """49.1 — "for infill" (a two-word tag) matches, in either order."""
    mock_get.side_effect = _attr_get()
    assert [r['id'] for r in spoolman_api.search_inventory(query="for infill")] == [501]
    assert [r['id'] for r in spoolman_api.search_inventory(query="infill for")] == [501]


@patch('spoolman_api.requests.get')
def test_a_query_can_cross_a_tag_and_a_material(mock_get):
    """49.1 — "matte pla": "matte" is a tag, "pla" the material. The Matte PETG
    (#178) has the tag but not the material, so only the Matte PLA matches."""
    mock_get.side_effect = _attr_get()
    assert [r['id'] for r in spoolman_api.search_inventory(query="matte pla")] == [503]
    fil = spoolman_api.search_inventory(query="matte pla", target_type="filament")
    assert [r['id'] for r in fil] == [177]
    # Both Matte filaments when only the tag is asked for (newest id first).
    both = spoolman_api.search_inventory(query="matte", target_type="filament")
    assert [r['id'] for r in both] == [178, 177]


@patch('spoolman_api.requests.get')
def test_untagged_filaments_are_unaffected(mock_get):
    """49.1 — a filament with no tags (an empty list, or no key at all) still
    matches on what it always matched, and never on a tag word."""
    mock_get.side_effect = _attr_get()
    assert 176 not in [r['id'] for r in spoolman_api.search_inventory(query="infill", target_type="filament")]
    assert [r['id'] for r in spoolman_api.search_inventory(query="plain jane", target_type="filament")] == [176]
    assert [r['id'] for r in spoolman_api.search_inventory(query="bare abs", target_type="filament")] == [179]
    assert [r['id'] for r in spoolman_api.search_inventory(query="abs")] == [505]
    # A tag never changes what an untagged item's card shows.
    plain = spoolman_api.search_inventory(query="plain", target_type="filament")[0]
    assert plain['details']['material'] == "PLA"


@patch('spoolman_api.requests.get')
def test_a_non_json_attribute_value_does_not_crash_and_is_searchable(mock_get):
    """49.1 — a non-JSON attribute string ("Silk, Matte", which Group 54.3 will
    split) and odd types (a number, a dict) never break the search: the string
    is still searchable text, the odd values are ignored, and every other
    filament still comes back."""
    odd = [
        _attr_filament(301, "Comma", "PLA", 'Silk, Matte'),
        _attr_filament(302, "Number", "PLA", 42),
        _attr_filament(303, "Dict", "PLA", {"weird": True}),
        _attr_filament(304, "Quoted", "PLA", '"For Infill"'),
    ]
    spools = [{"id": 600 + i, "remaining_weight": 100, "location": "", "filament": f}
              for i, f in enumerate(odd)]
    mock_get.side_effect = _attr_get(spools=spools, filaments=odd)

    assert [r['id'] for r in spoolman_api.search_inventory(query="silk", target_type="filament")] == [301]
    assert [r['id'] for r in spoolman_api.search_inventory(query="matte")] == [600]
    # A JSON-quoted scalar is one tag.
    assert [r['id'] for r in spoolman_api.search_inventory(query="infill", target_type="filament")] == [304]
    # Nothing crashed: a plain query still sees all four.
    assert len(spoolman_api.search_inventory(query="pla", target_type="filament")) == 4
    assert len(spoolman_api.search_inventory(query="pla")) == 4


def test_filament_attribute_list_cleans_like_the_cards():
    """49.1 — the shared helper trims spaces and stray quotes, drops blanks, keeps
    case, and degrades to [] for anything it can't read."""
    f = spoolman_api.filament_attribute_list
    assert f({"extra": {"filament_attributes": [" For Infill ", "'Silk'", '"Matte"', "", "  "]}}) \
        == ["For Infill", "Silk", "Matte"]
    assert f({"extra": {"filament_attributes": '["One-off"]'}}) == ["One-off"]
    assert f({"extra": {"filament_attributes": "Silk, Matte"}}) == ["Silk, Matte"]
    assert f({"extra": {}}) == []
    assert f({"extra": None}) == []
    assert f({"extra": "nope"}) == []
    assert f(None) == []
    assert f({"extra": {"filament_attributes": 7}}) == []


@patch('spoolman_api.requests.get')
def test_search_unknown_sort_falls_through(mock_get):
    """Garbage sort tokens are ignored — results fall back to default
    ordering (id desc) so the endpoint never errors on bad input."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_FILAMENTS
    mock_get.return_value = mock_response

    results = spoolman_api.search_inventory(
        target_type="filament", sort="bogus_axis"
    )
    # MOCK_FILAMENTS has one entry; default sort returns it unchanged.
    assert len(results) == 1
    assert results[0]['id'] == 99
