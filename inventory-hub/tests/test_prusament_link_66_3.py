"""Group 66.3 (Derek's (B)), the server half: which spools a Prusament QR is linked to.

Edit Spool's "📷 Per-spool Prusament scan" box showed a ✓ for a scanned QR and Save
sent none of it. Derek's pick (B): in Edit Spool the box links the spool to its QR (the
spool's 📄 Product Link and its blank Prusament details, saved by Save). Before it puts
the link in, the page asks whether another spool already holds that QR, so two spools
never share one (the dashboard scan matches the first in list order, archived spools
included). GET /api/prusament/linked_spools?url=… answers that, read-only, by the
dashboard scan's own rule, which is now one shared helper (_prusament_needles,
_spools_linked_to) instead of a loop inside _handle_prusament_url_scan.

A spool list FCC couldn't read answers 502 with words, never an empty list (CLAUDE.md:
a read says "couldn't read", never "none"): an empty list would let Edit Spool link a QR
another spool holds.

Hermetic: the Flask test client over tests/spoolman_extra_fake.SpoolmanHTTPFake.
"""
from __future__ import annotations

import pytest

import app as app_module
import routes_scan
import spoolman_api
from spoolman_extra_fake import SpoolmanHTTPFake

QR = "https://prusament.com/spool/17705/abc123def0/"


@pytest.fixture
def env(monkeypatch):
    fake = SpoolmanHTTPFake(version="0.27.0")
    monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client, fake


def _spool(fake, sid, product_url, archived=False, name="Galaxy Black"):
    fake.add("spool", sid, {"product_url": f'"{product_url}"'} if product_url else {},
             archived=archived, remaining_weight=500, location="",
             filament={"id": 7, "name": name, "material": "PLA", "vendor": {"name": "Prusament"}, "extra": {}})


def _ask(client, url):
    r = client.get("/api/prusament/linked_spools", query_string={"url": url})
    return r.status_code, r.get_json()


def test_the_spool_holding_the_qr_is_named(env):
    """The path form of the hash. RED on the base: no such route (404)."""
    client, fake = env
    _spool(fake, 57, "https://prusament.com/spool/17705/abc123def0/")
    _spool(fake, 58, "https://prusament.com/spool/17705/fff000aaa1/")   # a sibling: same product, its own spool
    _spool(fake, 59, "")
    code, body = _ask(client, QR)
    assert code == 200, body
    assert body["success"] is True
    assert (body["spool_id"], body["spool_hash"]) == ("17705", "abc123def0")
    assert [s["id"] for s in body["spools"]] == [57]
    assert body["spools"][0]["archived"] is False
    assert "#57" in body["spools"][0]["display"]


def test_the_query_form_and_an_archived_spool_count(env):
    """The query form some imports store, in any case, and an archived spool (the
    dashboard scan matches it too)."""
    client, fake = env
    _spool(fake, 60, "https://prusament.com/spool/?spoolId=ABC123DEF0", archived=True)
    code, body = _ask(client, "https://prusament.com/spool/17705/ABC123DEF0")
    assert code == 200
    assert [(s["id"], s["archived"]) for s in body["spools"]] == [(60, True)]


def test_no_spool_holds_it(env):
    client, fake = env
    _spool(fake, 58, "https://prusament.com/spool/17705/fff000aaa1/")
    code, body = _ask(client, QR)
    assert code == 200 and body["spools"] == []


def test_a_list_fcc_couldnt_read_is_said_never_none(env):
    """A Spoolman blip answers 502 with words, never success with no spools (which
    would let Edit Spool link a QR another spool holds)."""
    client, fake = env
    _spool(fake, 57, "https://prusament.com/spool/17705/abc123def0/")
    fake.list_reads_fail = True
    code, body = _ask(client, QR)
    assert code == 502, body
    assert body["success"] is False
    assert "couldn't read the spool list" in body["msg"]
    fake.list_reads_fail = False
    fake.down = True
    code, body = _ask(client, QR)
    assert code == 502 and body["success"] is False


@pytest.mark.parametrize("url", ["", "https://example.com/spool/1", "ID:57", "prusament.com/en/product/pla"])
def test_a_link_that_isnt_a_prusament_spools_is_refused(env, url):
    client, _fake = env
    code, body = _ask(client, url)
    assert code == 400 and body["success"] is False
    assert "isn't a Prusament spool's link" in body["msg"]


def test_the_shared_rule_is_the_dashboard_scans(env):
    """A pin: the dashboard scan reads the same rule (refactored, not changed). A
    hash-less link is matched at product granularity, as it always was."""
    _client, fake = env
    rows = [
        {"id": 1, "extra": {"product_url": '"https://prusament.com/spool/17705/abc123def0"'}},
        {"id": 2, "extra": {"product_url": '"https://prusament.com/spool/17705/fff000aaa1"'}},
        {"id": 3, "extra": {}},
        {"id": 4, "extra": None},
        "not a spool",
    ]
    hit = routes_scan._spools_linked_to(rows, routes_scan._prusament_needles("17705", "ABC123DEF0"))
    assert [s["id"] for s in hit] == [1]
    product = routes_scan._spools_linked_to(rows, routes_scan._prusament_needles("17705", None))
    assert [s["id"] for s in product] == [1, 2]
    # The scan itself: an unknown spool is still offered for onboarding.
    _spool(fake, 58, "https://prusament.com/spool/17705/fff000aaa1/")
    with app_module.app.test_request_context():
        out = routes_scan._handle_prusament_url_scan({"spool_id": "17705", "spool_hash": "abc123def0", "url": QR})
    assert out.get_json()["type"] == "prusament_new"
