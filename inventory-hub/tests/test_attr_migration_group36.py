"""Group 36 — the filament-attribute force_reset must stop losing data.

Background. Removing one choice from Spoolman's `filament_attributes` field is
impossible in place (`add_or_update_extra_field` raises "Cannot remove existing
choices"), so FCC deleted the whole field and PATCHed every attribute-bearing
record back. With no retry, a memory-only snapshot and a `success: True`
response regardless of outcome, a single transport blip was permanent,
invisible data loss. 26 of Derek's filaments drained over months and had to be
restored by diffing against the production Spoolman.

Blast radius, settled at source rather than by experiment (Spoolman v0.23.1,
`git_commit eafbc64`, matched against the live dev `/api/v1/info`): `extra` is
NOT a JSON blob but the child table `filament_field` with composite primary key
`(filament_id, key)`, and the field DELETE is `DELETE ... WHERE key = ?`. A
failed restore therefore loses exactly `filament_attributes` on that record;
siblings are structurally untouchable. The suspected "escalation to every
extra" filed in the task doc is FALSE. The sibling gaps still visible in dev
came from a different, already-fixed bug — the pre-2026-05-19 draft that PATCHed
a PARTIAL extras dict and so tripped Spoolman's replace-the-whole-sub-document
PATCH semantics.

Everything here is hermetic: `requests` is monkeypatched at the module object
the handlers resolve through, so no test touches the dev container or Spoolman.
"""
from __future__ import annotations

import json

import pytest
import requests as requests_module

import app as app_module  # noqa: F401  - registers the routes
import attr_migration
import http_retry
import routes_config_attrs as rca

SM_URL = "http://spoolman.test"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """A full 4-attempt failure otherwise sleeps 0.75+1.5+2.25 = 4.5 s."""
    monkeypatch.setattr(http_retry, "BACKOFF", 0)


class _Resp:
    def __init__(self, *, ok=True, status_code=200, payload=None, text=""):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _attr_field(choices):
    return {"key": "filament_attributes", "name": "Filament Attributes",
            "field_type": "choice", "multi_choice": True,
            "choices": list(choices)}


def _wire(monkeypatch, *, fields, filaments, patch_fn=None, delete_resp=None,
          post_resp=None, get_one=None):
    """Patch the four verbs on the shared `requests` module + get_api_urls.

    The handlers do a function-local `import requests as _req`, which resolves
    to this same singleton, so patching here intercepts every wire call —
    including the ones made through `http_retry`, which dispatches with
    `getattr(requests, verb)` precisely to keep this seam working.
    """
    calls = []

    def fake_get(url, **kw):
        calls.append(("GET", url, None))
        if url.endswith("/api/v1/field/filament"):
            return _Resp(payload=fields)
        if url.endswith("/api/v1/filament"):
            return _Resp(payload=filaments)
        # A per-record re-read: `/api/v1/filament/<id>`.
        if get_one is not None:
            return get_one(url)
        raise AssertionError(f"unexpected GET {url}")

    def fake_delete(url, **kw):
        calls.append(("DELETE", url, None))
        return delete_resp or _Resp(status_code=204)

    def fake_post(url, json=None, **kw):
        calls.append(("POST", url, json))
        return post_resp or _Resp()

    def fake_patch(url, json=None, **kw):
        calls.append(("PATCH", url, json))
        if patch_fn is not None:
            return patch_fn(url, json)
        return _Resp()

    monkeypatch.setattr(requests_module, "get", fake_get)
    monkeypatch.setattr(requests_module, "delete", fake_delete)
    monkeypatch.setattr(requests_module, "post", fake_post)
    monkeypatch.setattr(requests_module, "patch", fake_patch)
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: (SM_URL, SM_URL))
    return calls


def _logs(monkeypatch):
    entries = []
    monkeypatch.setattr(app_module.state, "add_log_entry",
                        lambda msg, *a, **k: entries.append((msg, a, k)))
    return entries


def _fixture():
    fields = [_attr_field(["Basic", "Doomed"])]
    filaments = [
        {"id": 1, "extra": {"filament_attributes": '["Basic","Doomed"]',
                            "product_url": '"http://x"'}},
        {"id": 2, "extra": {"filament_attributes": '["Basic"]'}},
        {"id": 3, "extra": {"product_url": '"y"'}},
    ]
    return fields, filaments


# ---------------------------------------------------------------------------
# 36.2 — the restore must RETRY, and only the retryable thing
# ---------------------------------------------------------------------------

def test_a_transport_blip_is_retried_and_recovers(client, monkeypatch):
    """The actual observed failure mode: a ReadTimeout under load.

    Proven by wall-clock arithmetic in hub.log — every restore failure cost
    almost exactly the loop's 10 s timeout, which an HTTP rejection (returned in
    milliseconds) cannot produce. Before this, one blip meant that record's
    attributes were gone forever, because the DELETE had already landed.
    """
    fields, filaments = _fixture()
    seen = {"n": 0}

    def flaky_patch(url, body):
        if url.endswith("/1"):
            seen["n"] += 1
            if seen["n"] < 3:
                raise requests_module.exceptions.ReadTimeout("stalled")
        return _Resp()

    calls = _wire(monkeypatch, fields=fields, filaments=filaments,
                  patch_fn=flaky_patch)
    logs = _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is True
    assert body["restore_failures"] == []
    assert body["restored"] == 2
    assert seen["n"] == 3, "the timeout must be retried, not accepted as loss"
    patched = [u.rsplit("/", 1)[-1] for (m, u, _j) in calls if m == "PATCH"]
    assert patched == ["1", "1", "1", "2"]
    assert logs[-1][1] == ("INFO", "00ccff"), "a recovered blip is not an error"


def test_one_casualty_does_not_abandon_the_rest_of_the_library(monkeypatch):
    """The restore loop must CONTINUE past a failure.

    This pins `restore_extras` directly because the endpoint-level pin that used
    to guard it lost its teeth: narrowing the restore set to attribute-bearing
    records left that fixture with a single record, so an
    abort-on-first-failure implementation would sail through the whole suite.
    Abandoning the loop mid-restore is the worst outcome available here — every
    remaining filament keeps the emptiness the DELETE left behind.
    """
    seen = []

    def patch_fn(url, **kw):
        fid = url.rsplit("/", 1)[-1]
        seen.append(fid)
        return _Resp(ok=False, status_code=500, text="nope") if fid == "1" else _Resp()

    monkeypatch.setattr(requests_module, "patch", patch_fn)
    monkeypatch.setattr(requests_module, "get",
                        lambda url, **kw: _Resp(payload={"extra": {"nope": 1}}))

    payloads = {1: {"filament_attributes": "[]"},
                2: {"filament_attributes": "[]"},
                3: {"filament_attributes": "[]"}}
    restored, failures, _recovered = attr_migration.restore_extras(SM_URL, payloads)

    assert seen == ["1", "2", "3"], "every record must be attempted"
    assert restored == 2
    assert [f["id"] for f in failures] == [1]


def test_an_http_rejection_is_NOT_retried(client, monkeypatch):
    """A status code is a real answer from a healthy server.

    Retrying a 400 "Unknown extra field" would just fail four times more slowly
    while pretending to be resilient. Only transport errors are ridden out.
    """
    fields, filaments = _fixture()
    attempts = {"n": 0}

    def rejecting_patch(url, body):
        if url.endswith("/1"):
            attempts["n"] += 1
            return _Resp(ok=False, status_code=400, text="Unknown extra field")
        return _Resp()

    _wire(monkeypatch, fields=fields, filaments=filaments,
          patch_fn=rejecting_patch)
    _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert attempts["n"] == 1, "an HTTP status must not be retried"
    assert body["success"] is False
    assert body["lost_ids"] == [1]


def test_a_timed_out_write_that_actually_LANDED_is_not_reported_as_loss(
        client, monkeypatch):
    """A ReadTimeout means the response was lost, not that the write failed.

    The restore payload is a fixed pre-computed snapshot, so it is idempotent
    and a re-read is safe. Without this check the endpoint declares data loss
    that never happened — and an operator then "recovers" by replaying stale
    extras over a record that was perfectly fine.
    """
    fields, filaments = _fixture()

    def always_timeout(url, body):
        if url.endswith("/1"):
            raise requests_module.exceptions.ReadTimeout("stalled")
        return _Resp()

    def get_one(url):
        # Spoolman DID apply it — the response just never came back.
        assert url.endswith("/api/v1/filament/1")
        return _Resp(payload={"id": 1, "extra": {
            "filament_attributes": '["Basic"]', "product_url": '"http://x"'}})

    _wire(monkeypatch, fields=fields, filaments=filaments,
          patch_fn=always_timeout, get_one=get_one)
    logs = _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is True
    assert body["restore_failures"] == []
    assert body["restored"] == 2
    assert body["recovered"] == 1, "the re-read rescue must be reported"
    assert "confirmed by re-read" in logs[-1][0]


# ---------------------------------------------------------------------------
# 36.3 — the logged recovery payload must be usable
# ---------------------------------------------------------------------------

def test_the_logged_payload_is_POST_filter_and_replayable(monkeypatch):
    """Logging the PRE-filter snapshot put the just-removed choice back into
    the "recovery" data. Replaying it verbatim re-introduces the choice — which
    is no longer a legal value in the recreated schema, so the replay 400s.

    Observable in Derek's own hub.log: `DATA LOSS in remove_choice('A') ...
    Recovery payload follows: {"filament_attributes": "[\\"A\\"]"}`.
    """
    errors = []
    monkeypatch.setattr(attr_migration.state, "logger",
                        type("L", (), {"error": staticmethod(lambda m: errors.append(m))})())

    post_filter = {63: {"filament_attributes": '["Blend"]',
                        "original_color": '"Azure"'}}
    ids = attr_migration.report_restore_failures(
        "remove_choice('Doomed')", [{"id": 63, "msg": "HTTP 500"}], post_filter)

    assert ids == [63]
    msg = errors[0]
    assert "Doomed" not in msg.split("Recovery payload follows:")[1], (
        "the removed choice must not appear in the recovery payload"
    )
    assert "Azure" in msg, "siblings are part of the replayable payload"
    payload = msg.split("Recovery payload follows: ", 1)[1]
    assert json.loads(payload) == post_filter[63], "the payload must round-trip"


def test_a_truncated_payload_says_so(monkeypatch):
    """Silent truncation does not merely shorten the JSON, it makes it
    unparseable — and someone recovering by hand cannot tell truncation from
    corruption. ASCII marker, because this line must survive a cp1252 console.
    """
    errors = []
    monkeypatch.setattr(attr_migration.state, "logger",
                        type("L", (), {"error": staticmethod(lambda m: errors.append(m))})())

    huge = {1: {"filament_attributes": json.dumps(["x" * 50] * 500)}}
    attr_migration.report_restore_failures("op", [{"id": 1, "msg": "boom"}], huge)

    msg = errors[0]
    assert msg.endswith("...TRUNCATED")
    assert msg.isascii(), "a non-ASCII byte here can drop the whole line"
    assert len(msg) < 6000


def test_a_non_ascii_spoolman_error_body_cannot_drop_the_line(monkeypatch):
    """`msg` is arbitrary Spoolman response text. If it carries a non-ASCII
    byte, a cp1252 StreamHandler raises UnicodeEncodeError and the record is
    lost along with the message that exists to preserve it."""
    errors = []
    monkeypatch.setattr(attr_migration.state, "logger",
                        type("L", (), {"error": staticmethod(lambda m: errors.append(m))})())

    attr_migration.report_restore_failures(
        "op", [{"id": 1, "msg": "café — naïve ☃"}], {1: {"a": "b"}})

    assert errors[0].isascii()
    assert "#1" in errors[0]


# ---------------------------------------------------------------------------
# The mass-loss guards
# ---------------------------------------------------------------------------

def test_remove_choice_refuses_a_transient_empty_filament_list(client, monkeypatch):
    """THE cheapest fix with the largest blast-radius reduction.

    `sweep_unused` has had this guard since it shipped; `remove_choice` never
    did. With an empty list `users` is empty (so the confirm gate is skipped)
    and the restore set is empty, so it would DELETE the field, recreate it,
    restore NOTHING and report success — wiping `filament_attributes` from
    EVERY record because Spoolman happened to blink.
    """
    calls = _wire(monkeypatch, fields=[_attr_field(["Basic", "Doomed"])],
                  filaments=[])

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is False
    assert "possibly-transient empty list" in body["msg"]
    assert "DELETE" not in [m for (m, _u, _j) in calls]


def test_purging_the_last_choice_is_refused(client, monkeypatch):
    """Spoolman's schema requires a non-empty `choices` array, so the recreate
    POST is rejected — AFTER the DELETE has landed. Field missing, restore loop
    never reached, every filament permanently loses its attributes."""
    calls = _wire(monkeypatch, fields=[_attr_field(["OnlyOne"])],
                  filaments=[{"id": 1, "extra": {"filament_attributes": '[]'}}])

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "OnlyOne", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is False
    assert "last remaining choice" in body["msg"]
    assert "DELETE" not in [m for (m, _u, _j) in calls]


def test_sweeping_every_remaining_choice_is_refused(client, monkeypatch):
    """Reachable from the UI, whose sweep checkboxes default to all-checked."""
    fields = [_attr_field(["A", "B"])]
    filaments = [{"id": 1, "extra": {"filament_attributes": '[]'}}]
    calls = _wire(monkeypatch, fields=fields, filaments=filaments)

    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True}).get_json()

    assert body["success"] is False
    assert "every remaining choice" in body["msg"]
    assert "DELETE" not in [m for (m, _u, _j) in calls]


def test_a_concurrent_migration_is_rejected_with_409(client, monkeypatch):
    """The migration rewrites the whole library inside one request and can run
    for minutes. Flask is threaded, so a second click could DELETE the field
    while the first run is still restoring."""
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments)

    rca._MIGRATION_LOCK.acquire()
    try:
        r = client.post("/api/filament_attributes/remove_choice",
                        json={"choice": "Doomed", "force": True, "purge": True})
    finally:
        rca._MIGRATION_LOCK.release()

    assert r.status_code == 409
    assert "already running" in r.get_json()["msg"]


# ---------------------------------------------------------------------------
# 36.4 — hide by default, purge only on explicit request
# ---------------------------------------------------------------------------

def test_remove_choice_HIDES_by_default_and_never_touches_the_schema(
        client, monkeypatch):
    """The headline fix. An 18x18px red X used to fire a production-shaped
    migration across every attribute-bearing record. The default now strips the
    tag from just the carriers, through `update_filament`'s safe
    read-merge-write, and suppresses the choice locally."""
    fields, filaments = _fixture()
    calls = _wire(monkeypatch, fields=fields, filaments=filaments)
    logs = _logs(monkeypatch)

    updates = []
    monkeypatch.setattr(app_module.spoolman_api, "update_filament",
                        lambda fid, body: updates.append((fid, body)) or {"id": fid})

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True}).get_json()

    assert body["success"] is True
    assert body["mode"] == "hidden"
    assert body["stripped"] == 1
    assert body["hidden_choices"] == ["Doomed"]
    # The whole point: nothing destructive happened.
    methods = [m for (m, _u, _j) in calls]
    assert "DELETE" not in methods and "POST" not in methods and "PATCH" not in methods
    # Only the carrier was written, via the merge-safe path.
    assert updates == [(1, {"extra": {"filament_attributes": '["Basic"]'}})]
    assert "hid choice 'Doomed'" in logs[-1][0]


def test_a_hidden_choice_disappears_from_the_report_but_is_not_rogue(
        client, monkeypatch):
    """Hidden choices must leave `choices` (or the picker still offers them)
    without being counted as rogue — they are deliberately suppressed, not
    orphaned values a record picked up from nowhere."""
    fields = [_attr_field(["Basic", "Doomed"])]
    filaments = [{"id": 1, "extra": {"filament_attributes": '["Basic","Doomed"]'}}]
    _wire(monkeypatch, fields=fields, filaments=filaments)
    attr_migration.save_hidden_choices(["Doomed"])

    body = client.get("/api/filament_attributes/report").get_json()

    assert body["choices"] == ["Basic"]
    assert body["counts"] == {"Basic": 1}
    assert body["hidden_choices"] == ["Doomed"]
    assert body["hidden_counts"] == {"Doomed": 1}
    assert body["rogue_counts"] == {}


def test_hiding_is_reversible(client, monkeypatch):
    """Hiding has to be undoable or it is just deletion with extra steps."""
    _logs(monkeypatch)
    attr_migration.save_hidden_choices(["Doomed"])

    body = client.post("/api/filament_attributes/unhide_choice",
                       json={"choice": "Doomed"}).get_json()

    assert body["success"] is True
    assert body["hidden_choices"] == []
    assert attr_migration.load_hidden_choices() == []


def test_sweep_ignores_hidden_choices(client, monkeypatch):
    """A hidden choice is zero-usage by construction, so it would show up in
    every sweep preview forever — and sweeping it fires the full destructive
    migration for no visible change."""
    fields = [_attr_field(["Basic", "Hidden1"])]
    filaments = [{"id": 1, "extra": {"filament_attributes": '["Basic"]'}}]
    _wire(monkeypatch, fields=fields, filaments=filaments)
    attr_migration.save_hidden_choices(["Hidden1"])

    body = client.post("/api/filament_attributes/sweep_unused", json={}).get_json()

    assert body["unused"] == []


def test_hide_refuses_when_every_strip_write_fails(client, monkeypatch):
    """Otherwise the tag vanishes from the UI while every record still has it —
    a silent divergence between what FCC shows and what Spoolman holds."""
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments)
    _logs(monkeypatch)
    monkeypatch.setattr(app_module.spoolman_api, "update_filament",
                        lambda fid, body: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "nope")

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True}).get_json()

    assert body["success"] is False
    assert body["stripped"] == 0
    assert attr_migration.load_hidden_choices() == [], "must not hide on failure"


# ---------------------------------------------------------------------------
# The on-disk recovery snapshot
# ---------------------------------------------------------------------------

def test_a_clean_purge_leaves_no_snapshot_behind(client, monkeypatch):
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments)
    _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is True
    assert attr_migration.pending_recovery_snapshots() == []


def test_a_failed_purge_KEEPS_the_snapshot_for_recovery(client, monkeypatch):
    """The snapshot is written BEFORE the DELETE and survives a failure. It is
    the durable half of the fix: hub.log is a ~6 MB rolling buffer that retains
    days, not months, and the reloader gives it two competing writers."""
    fields, filaments = _fixture()

    def fail_one(url, body):
        if url.endswith("/1"):
            return _Resp(ok=False, status_code=500, text="nope")
        return _Resp()

    _wire(monkeypatch, fields=fields, filaments=filaments, patch_fn=fail_one)
    _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is False
    pending = attr_migration.pending_recovery_snapshots()
    assert len(pending) == 1
    assert pending[0]["op"] == "remove_choice('Doomed')"
    # And it holds the POST-filter payload, ready to replay verbatim.
    with open(pending[0]["path"], encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved["payloads"]["1"] == {"filament_attributes": '["Basic"]',
                                      "product_url": '"http://x"'}


def test_a_TIMED_OUT_schema_delete_KEEPS_the_snapshot(client, monkeypatch):
    """The single most dangerous ambiguity in the whole flow.

    A returned status means Spoolman answered and the field is intact, so
    dropping the snapshot there is right. An EXCEPTION does not: a ReadTimeout
    is exactly the case where Spoolman may have committed
    `DELETE FROM filament_field WHERE key='filament_attributes'` and only the
    response was lost. Every attribute-bearing record is then stripped — and
    discarding the recovery payload at that moment reproduces the original bug
    in full: silent, unattributable, unrecoverable.
    """
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments)

    def timeout_delete(url, **kw):
        raise requests_module.exceptions.ReadTimeout("stalled")

    monkeypatch.setattr(requests_module, "delete", timeout_delete)
    logs = _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is False
    assert body["recovery_snapshot"], "the payload must survive an unknown outcome"
    pending = attr_migration.pending_recovery_snapshots()
    assert len(pending) == 1, "the snapshot must NOT be deleted on a timeout"
    assert logs and logs[-1][1] == ("ERROR", "ff4444")
    assert "UNKNOWN" in logs[-1][0]


def test_a_REJECTED_schema_delete_clears_the_snapshot(client, monkeypatch):
    """The counterpart: a real status code proves the field was never dropped,
    so keeping the snapshot would cry wolf at every future boot."""
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments,
          delete_resp=_Resp(ok=False, status_code=500, text="boom"))
    _logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is False
    assert attr_migration.pending_recovery_snapshots() == []


def test_hidden_choices_are_stripped_from_the_tag_PICKER_feed(client, monkeypatch):
    """`/api/external/fields` is what the wizard and the Edit Filament modal
    actually read. Filtering only the Choices-Manager report left a "removed"
    tag still offered everywhere it gets applied — so it kept coming back, and
    the manager could no longer see or strip it."""
    def fake_get(url, **kw):
        if url.endswith("/api/v1/field/filament"):
            return _Resp(payload=[_attr_field(["Basic", "Doomed"])])
        if url.endswith("/api/v1/field/spool"):
            return _Resp(payload=[])
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(requests_module, "get", fake_get)
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: (SM_URL, SM_URL))
    attr_migration.save_hidden_choices(["Doomed"])

    body = client.get("/api/external/fields").get_json()

    fil = [f for f in body["fields"]["filament"] if f["key"] == "filament_attributes"]
    assert fil and fil[0]["choices"] == ["Basic"], (
        "a hidden tag must not be offered by the pickers"
    )


def test_re_adding_a_hidden_tag_brings_it_back(client, monkeypatch):
    """Hiding leaves the choice in Spoolman's schema, so re-adding it by name
    is a no-op union that returns success. Without un-hiding, the user gets a
    green "added" toast for an action with no visible effect."""
    _logs(monkeypatch)
    attr_migration.save_hidden_choices(["Doomed"])
    monkeypatch.setattr(app_module.spoolman_api, "update_extra_field_choices",
                        lambda *a, **k: {"success": True})

    body = client.post("/api/filament_attributes/add_choice",
                       json={"choice": "Doomed"}).get_json()

    assert body["success"] is True
    assert body.get("unhidden") is True
    assert attr_migration.load_hidden_choices() == []


def test_a_purge_clears_the_now_meaningless_hidden_entry(client, monkeypatch):
    """Purge is only reachable FROM the hidden strip, so without this every
    purge leaves a hidden entry for a choice that no longer exists — which
    would silently suppress the name if it were ever re-added."""
    fields, filaments = _fixture()
    _wire(monkeypatch, fields=fields, filaments=filaments)
    _logs(monkeypatch)
    attr_migration.save_hidden_choices(["Doomed"])

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "Doomed", "force": True,
                             "purge": True}).get_json()

    assert body["success"] is True
    assert attr_migration.load_hidden_choices() == []


def test_the_report_drops_a_hidden_entry_that_left_the_schema(client, monkeypatch):
    """A dead name in the Hidden strip would offer an "unhide" button that can
    never bring anything back."""
    _wire(monkeypatch, fields=[_attr_field(["Basic"])],
          filaments=[{"id": 1, "extra": {"filament_attributes": '["Basic"]'}}])
    attr_migration.save_hidden_choices(["GoneFromSchema"])

    body = client.get("/api/filament_attributes/report").get_json()

    assert body["hidden_choices"] == []


def test_update_filament_REFUSES_when_the_pre_merge_read_fails(monkeypatch):
    """`_get_raw_extras` used to return `{}` on a read failure, which is
    indistinguishable from "this record has no extras". The merge then produced
    the caller's PARTIAL dict, and Spoolman replaces the whole `extra`
    sub-document on PATCH — so a read blip silently wiped every sibling. That
    is the 2026-05-19 wipe class returning through the back door, and the hide
    path made it the default route for removing a tag.

    Refusing is strictly better: a failed write is recoverable, a silent wipe
    is not.
    """
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: (SM_URL, SM_URL))

    def dead_get(url, **kw):
        raise requests_module.exceptions.ConnectTimeout("nope")

    patched = []
    monkeypatch.setattr(requests_module, "get", dead_get)
    monkeypatch.setattr(requests_module, "patch",
                        lambda url, **kw: patched.append(url) or _Resp())

    result = app_module.spoolman_api.update_filament(
        7, {"extra": {"filament_attributes": '["Basic"]'}})

    assert result is None, "a partial PATCH must not be sent blind"
    assert patched == [], "no write may reach Spoolman"
    assert "refusing to PATCH" in (app_module.spoolman_api.LAST_SPOOLMAN_ERROR or "")


def test_an_unfinished_migration_is_announced_at_boot(monkeypatch):
    """Announce, never auto-replay: a snapshot can be arbitrarily stale, and the
    restore PATCH writes each record's WHOLE extras dict, so a blind replay
    would revert every edit made to those filaments since the crash."""
    attr_migration.write_recovery_snapshot("remove_choice('X')", {7: {"a": "b"}})
    entries = []
    monkeypatch.setattr(attr_migration.state, "add_log_entry",
                        lambda msg, *a, **k: entries.append((msg, a)))
    monkeypatch.setattr(attr_migration.state, "logger",
                        type("L", (), {"error": staticmethod(lambda m: None)})())

    pending = attr_migration.surface_pending_recovery_snapshots()

    assert len(pending) == 1
    assert entries and entries[0][1] == ("ERROR", "ff4444")
    assert "did not finish" in entries[0][0]
