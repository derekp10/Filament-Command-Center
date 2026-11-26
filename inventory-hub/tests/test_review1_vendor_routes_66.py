"""Group 66, review round 1: the vendor routes (R1-02, R1-05).

R1-02: the vendor window always sends `name`. When the single-vendor read before a save
blipped, the save counted as a rename, and a weight edit of Sunlu #35 (which shares its
name with #4) was refused as a rename onto #4's name, with a false Activity Log line. The
list just read holds #35's own name: a save that keeps it is no rename.
R1-05: a rename refused because the vendor list couldn't be read left no Activity Log
line (the create's twin does).

Offline: the real routes over SpoolmanHTTPFake (tests/test_vendor_names_66_1.py's env).
Each case fails on the commit before the fix for the reason it names.
"""
from __future__ import annotations

import spoolman_api
from test_vendor_names_66_1 import env  # noqa: F401  (the fixture)


def test_a_weight_edit_of_a_duplicate_with_its_own_read_blipping_is_saved(env, monkeypatch):  # noqa: F811
    """RED: 409 "A manufacturer named "Sunlu" already exists (#4)", nothing saved."""
    client, fake, created, updated, logs = env
    monkeypatch.setattr(spoolman_api, "get_vendor", lambda vid: None)
    r = client.patch("/api/vendors/35", json={"data": {"name": "Sunlu", "empty_spool_weight": 167}})
    assert r.status_code == 200, r.get_json()
    assert updated and updated[0][0] in (35, "35")
    assert not [m for m, _a in logs if "Didn't rename" in m], logs


def test_a_real_rename_onto_a_duplicate_is_still_refused_with_the_read_blipping(env, monkeypatch):  # noqa: F811
    """A pin: #9 Prusament renamed "Sunlu" is still refused."""
    client, fake, created, updated, logs = env
    monkeypatch.setattr(spoolman_api, "get_vendor", lambda vid: None)
    r = client.patch("/api/vendors/9", json={"data": {"name": "Sunlu"}})
    assert r.status_code == 409 and not updated


def test_a_rename_fcc_couldnt_check_leaves_one_escaped_log_line(env):  # noqa: F811
    """R1-05. RED: no Activity Log line."""
    client, fake, created, updated, logs = env
    fake.down = True
    r = client.patch("/api/vendors/9", json={"data": {"name": "<b>New</b> & Co"}})
    assert r.status_code == 502 and not updated
    lines = [m for m, a in logs if "Didn't rename" in m]
    assert len(lines) == 1 and "&lt;b&gt;New&lt;/b&gt; &amp; Co" in lines[0], logs
