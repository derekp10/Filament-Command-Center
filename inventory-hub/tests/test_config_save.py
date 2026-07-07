"""L18 Config System — Phase 1 backend tests for the safe writer.

Covers design-doc acceptance criteria:
  #2  load_config_raw() injects NO defaults and does NOT uppercase printer_map.
  #3  load -> save -> load preserves every schema-unknown key exactly
      (secrets, paths, comments, nested print_settings, lowercase printer_map,
      dryer_slots).
  #4  a bad value returns {ok:False, error} and touches NO disk; LAST_CONFIG_ERROR set.

Plus: bool coercion, range/choice/unknown-key rejection, client-scope keys
ignored by save_config, and success clearing LAST_CONFIG_ERROR.

Pure unit tests — no running server. Monkeypatches config_loader.get_config_path
at a throwaway temp file so the real config.json is never touched.
"""
import errno
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config_loader  # noqa: E402
import config_schema  # noqa: E402


# A realistic config carrying keys the schema does NOT own — these must
# survive a save byte-for-byte. printer_map keys are intentionally LOWERCASE
# to prove the save round-trip doesn't re-case them (load_config uppercases at
# runtime; the on-disk write must not).
SEED = {
    "comment": "--- DEV CONFIGURATION ---",
    "server_ip": "192.168.1.29",
    "SCRAPER_API_KEY": "secret-key-123",
    "spoolman_port": 7913,
    "sync_delay": 0.5,
    "spoolman_db_path": "\\\\TRUENAS\\App_Data\\Spoolman\\spoolman.db",
    "print_settings": {"mode": "browser", "csv_path": "/output/test_queue.csv"},
    "buy_more_url_template": "https://www.amazon.com/s?k={{vendor}}",
    "printer_map": {"xl-1": {"printer_name": "🦝 XL", "position": 0}},
    "dryer_slots": ["PM-DB-1", "PM-DB-2"],
}


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(SEED, indent=4), encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    config_loader.LAST_CONFIG_ERROR = None
    return p


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


# --- Criterion #2 ---------------------------------------------------------

def test_load_config_raw_no_defaults_no_uppercase(cfg_file):
    raw = config_loader.load_config_raw()
    assert raw == SEED  # exact: nothing injected
    assert list(raw["printer_map"].keys()) == ["xl-1"]  # NOT uppercased


def test_load_config_raw_missing_file_returns_empty(tmp_path, monkeypatch):
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(missing), "TEST"))
    assert config_loader.load_config_raw() == {}


# --- Criterion #3 ---------------------------------------------------------

def test_save_preserves_unknown_keys(cfg_file):
    result = config_loader.save_config({"sync_delay": 1.5})
    assert result["ok"] is True
    assert result["saved"] == ["sync_delay"]

    on_disk = _read(cfg_file)
    expected = dict(SEED)
    expected["sync_delay"] = 1.5
    assert on_disk == expected  # only the edited key changed
    assert list(on_disk["printer_map"].keys()) == ["xl-1"]  # still lowercase
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"
    assert on_disk["print_settings"] == {"mode": "browser", "csv_path": "/output/test_queue.csv"}
    assert on_disk["comment"] == "--- DEV CONFIGURATION ---"
    # ensure_ascii=False: emoji printer name survives as real UTF-8, not \uXXXX
    raw_text = cfg_file.read_text(encoding="utf-8")
    assert "🦝 XL" in raw_text
    assert "\\ud83e" not in raw_text  # not escaped


def test_save_bool_coerces_and_persists(cfg_file):
    # fcc_owns_completion_deduct is the surviving server-scope bool field
    # (auto_recover_filabridge_errors was removed in the FilaBridge cleanup).
    result = config_loader.save_config({"fcc_owns_completion_deduct": "true"})
    assert result["ok"] is True
    assert _read(cfg_file)["fcc_owns_completion_deduct"] is True


# --- Criterion #4 ---------------------------------------------------------

def test_bad_value_rejected_no_disk_change(cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    result = config_loader.save_config({"sync_delay": "abc"})
    assert result["ok"] is False
    assert result["error"] and "sync delay" in result["error"].lower()
    assert config_loader.LAST_CONFIG_ERROR == result["error"]
    assert cfg_file.read_text(encoding="utf-8") == before  # untouched


def test_out_of_range_rejected_no_disk_change(cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    result = config_loader.save_config({"sync_delay": 999})
    assert result["ok"] is False
    assert result["error"] and ("10" in result["error"] or "sync delay" in result["error"].lower())
    assert config_loader.LAST_CONFIG_ERROR == result["error"]
    assert cfg_file.read_text(encoding="utf-8") == before


def test_unknown_key_rejected_no_disk_change(cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    result = config_loader.save_config({"totally_unknown": 1})
    assert result["ok"] is False
    assert "unknown" in result["error"].lower()
    assert cfg_file.read_text(encoding="utf-8") == before


# --- Client-scope + housekeeping -----------------------------------------

def test_client_scope_key_ignored_by_save(cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    result = config_loader.save_config({"fcc.weighEntry.defaultMode": "gross"})
    assert result["ok"] is True
    assert result["saved"] == []  # nothing written server-side
    assert cfg_file.read_text(encoding="utf-8") == before  # untouched


def test_success_clears_last_error(cfg_file):
    config_loader.LAST_CONFIG_ERROR = "stale"
    config_loader.save_config({"sync_delay": 2.0})
    assert config_loader.LAST_CONFIG_ERROR is None


# --- Schema-level unit tests (no disk) -----------------------------------

def test_validate_payload_ignores_client_scope():
    coerced, errors = config_schema.validate_payload(
        {"sync_delay": 1.0, "fcc.weighEntry.defaultMode": "net"})
    assert errors == []
    assert coerced == {"sync_delay": 1.0}  # client key not coerced server-side


def test_coerce_select_rejects_bad_choice():
    with pytest.raises(config_schema.ConfigValidationError):
        config_schema.coerce_and_validate("fcc.weighEntry.defaultMode", "bogus")


def test_coerce_select_accepts_valid_choice():
    assert config_schema.coerce_and_validate("fcc.weighEntry.defaultMode", "net") == "net"


# --- Review Must-fix #1: never clobber an unreadable/corrupt existing config ---

def test_load_config_raw_corrupt_returns_none(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text("{ this is not valid json ", encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    assert config_loader.load_config_raw() is None  # unreadable -> None, NOT {}


def test_load_config_raw_non_dict_returns_none(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text('["a", "b"]', encoding="utf-8")  # valid JSON, but a list
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    assert config_loader.load_config_raw() is None  # top-level non-dict -> None


def test_save_refuses_on_corrupt_existing_no_disk_change(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    original = "{ half-written corrupt config "
    p.write_text(original, encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    config_loader.LAST_CONFIG_ERROR = None
    result = config_loader.save_config({"sync_delay": 1.5})
    assert result["ok"] is False
    assert "refusing to save" in result["error"]
    assert config_loader.LAST_CONFIG_ERROR == result["error"]
    assert p.read_text(encoding="utf-8") == original  # byte-for-byte untouched


def test_save_refuses_on_non_dict_existing_no_disk_change(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    original = "[1, 2, 3]"
    p.write_text(original, encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    result = config_loader.save_config({"sync_delay": 1.5})
    assert result["ok"] is False
    assert p.read_text(encoding="utf-8") == original


def test_save_fresh_install_seeds_full_defaults(tmp_path, monkeypatch):
    missing = tmp_path / "config.json"  # genuinely absent
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(missing), "TEST"))
    result = config_loader.save_config({"sync_delay": 1.5})
    assert result["ok"] is True
    on_disk = _read(missing)
    assert on_disk["sync_delay"] == 1.5
    # complete file seeded from defaults, NOT a lone {"sync_delay": 1.5}
    for k in ("server_ip", "spoolman_port", "printer_map", "dryer_slots"):
        assert k in on_disk


# --- Review Must-fix #2: NaN / non-finite floats rejected, touch no disk ---

def test_coerce_rejects_nan_and_inf():
    for bad in ("nan", "inf", "-inf", "Infinity"):
        with pytest.raises(config_schema.ConfigValidationError):
            config_schema.coerce_and_validate("sync_delay", bad)


def test_save_rejects_nan_no_disk_change(cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    result = config_loader.save_config({"sync_delay": "nan"})
    assert result["ok"] is False
    assert "finite" in result["error"].lower()
    assert cfg_file.read_text(encoding="utf-8") == before


# --- Safety machinery: atomic-write failure, verify retry, verify-fails-twice ---

def test_atomic_write_failure_surfaces_error_no_disk_change(cfg_file, monkeypatch):
    before = cfg_file.read_text(encoding="utf-8")
    monkeypatch.setattr(config_loader, "_write_config_atomic",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    result = config_loader.save_config({"sync_delay": 1.5})
    assert result["ok"] is False
    assert "write failed" in result["error"].lower()
    assert config_loader.LAST_CONFIG_ERROR == result["error"]
    assert cfg_file.read_text(encoding="utf-8") == before


def test_verify_mismatch_retries_then_succeeds(cfg_file, monkeypatch):
    calls = {"n": 0}
    real_verify = config_loader._verify_config_file

    def flaky(expected, path):
        calls["n"] += 1
        if calls["n"] == 1:
            return (False, "transient mismatch")
        return real_verify(expected, path)

    monkeypatch.setattr(config_loader, "_verify_config_file", flaky)
    result = config_loader.save_config({"sync_delay": 3.0})
    assert result["ok"] is True
    assert calls["n"] >= 2  # retried at least once
    assert _read(cfg_file)["sync_delay"] == 3.0


def test_verify_fails_twice_returns_error(cfg_file, monkeypatch):
    monkeypatch.setattr(config_loader, "_verify_config_file", lambda e, p: (False, "always bad"))
    result = config_loader.save_config({"sync_delay": 4.0})
    assert result["ok"] is False
    assert "twice" in result["error"].lower()


# --- Single-file bind-mount fallback (os.replace -> EBUSY) -----------------
# config.json is mounted as an individual file (`../config.json:/config.json`),
# so it's a mount point os.replace can't rename over -> EBUSY (errno 16). The
# writer must fall back to an in-place overwrite rather than fail the save.

def test_ebusy_replace_falls_back_to_in_place_write(cfg_file, monkeypatch):
    def busy_replace(src, dst):
        raise OSError(errno.EBUSY, "Device or resource busy")
    monkeypatch.setattr(config_loader.os, "replace", busy_replace)

    result = config_loader.save_config({"sync_delay": 9.0})
    assert result["ok"] is True, result["error"]
    on_disk = _read(cfg_file)
    assert on_disk["sync_delay"] == 9.0
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"  # siblings preserved
    assert list(on_disk["printer_map"].keys()) == ["xl-1"]
    # the fallback removes its temp file — nothing orphaned beside the target
    leftovers = [f for f in os.listdir(cfg_file.parent) if f.endswith(".tmp")]
    assert leftovers == []


def test_non_bind_mount_replace_error_is_not_masked(cfg_file, monkeypatch):
    # A real disk error (ENOSPC) must NOT be swallowed by the bind-mount
    # fallback — it has to surface as a failed save with the disk untouched.
    before = cfg_file.read_text(encoding="utf-8")
    def enospc_replace(src, dst):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(config_loader.os, "replace", enospc_replace)

    result = config_loader.save_config({"sync_delay": 9.0})
    assert result["ok"] is False
    assert "write failed" in result["error"].lower()
    assert cfg_file.read_text(encoding="utf-8") == before  # no partial write


# --- Rolling .bak snapshot (last-known-good, refreshed every save) ---

def test_bak_holds_pre_edit_state_and_rolls(cfg_file):
    bak = str(cfg_file) + ".bak"
    config_loader.save_config({"sync_delay": 1.5})
    assert os.path.exists(bak)
    bak1 = json.loads(open(bak, encoding="utf-8").read())
    assert bak1 == SEED  # the state right before save #1
    config_loader.save_config({"sync_delay": 2.5})
    bak2 = json.loads(open(bak, encoding="utf-8").read())
    assert bak2["sync_delay"] == 1.5  # rolled forward to the pre-save-#2 state
    assert bak2 != SEED


# --- Durable backup + corrupt-primary recovery + write concurrency (post-audit) ---

def test_concurrent_writes_no_lost_update(cfg_file):
    # _CONFIG_WRITE_LOCK must serialize read-merge-write so concurrent saves of
    # DIFFERENT keys don't lose one another (the dropped-lock regression).
    import threading as _t
    N = 12
    errors = []

    def writer(i):
        ok, err = config_loader._write_merged_config({f"ck{i}": i})
        if not ok:
            errors.append(err)

    threads = [_t.Thread(target=writer, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    on_disk = _read(cfg_file)
    for i in range(N):
        assert on_disk.get(f"ck{i}") == i, f"lost update: ck{i} missing"
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"  # seed survived too


def test_load_recovers_from_backup_on_corrupt_primary(cfg_file):
    # A corrupt primary must NOT silently degrade to localhost defaults — it
    # recovers from the durable backup instead.
    good = dict(SEED)
    good["server_ip"] = "10.9.8.7"
    with open(config_loader.get_config_backup_path(), "w", encoding="utf-8") as f:
        json.dump(good, f)
    cfg_file.write_text("{ not valid json", encoding="utf-8")
    cfg = config_loader.load_config()
    assert cfg["server_ip"] == "10.9.8.7"  # from backup, NOT the 127.0.0.1 default


def test_save_repairs_corrupt_primary_from_backup(cfg_file):
    # A save against a corrupt primary repairs it from the backup + applies the
    # change, rather than locking the operator out of all saves.
    good = dict(SEED)
    good["sync_delay"] = 0.25
    with open(config_loader.get_config_backup_path(), "w", encoding="utf-8") as f:
        json.dump(good, f)
    cfg_file.write_text("CORRUPT", encoding="utf-8")
    result = config_loader.save_config({"sync_delay": 9.0})
    assert result["ok"] is True, result["error"]
    on_disk = _read(cfg_file)
    assert on_disk["sync_delay"] == 9.0                     # change applied
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"   # backup's keys restored


def test_save_refuses_when_corrupt_and_no_backup(cfg_file):
    # Corrupt primary AND no usable backup -> still refuse (don't drop keys).
    bak = config_loader.get_config_backup_path()
    if os.path.exists(bak):
        os.remove(bak)
    cfg_file.write_text("CORRUPT", encoding="utf-8")
    result = config_loader.save_config({"sync_delay": 9.0})
    assert result["ok"] is False
    assert "refus" in result["error"].lower()


def test_load_neutralizes_secret_sentinel_on_disk(cfg_file):
    # If a REDACTED export is copied into place (instead of imported), the literal
    # sentinel must NOT be served as the real key — load_config treats it as unset
    # so the scraper never authenticates with the placeholder string.
    raw = dict(SEED)
    raw["SCRAPER_API_KEY"] = config_schema.SECRET_SENTINEL
    cfg_file.write_text(json.dumps(raw), encoding="utf-8")
    cfg = config_loader.load_config()
    assert cfg["SCRAPER_API_KEY"] == ""  # neutralized, not the literal sentinel


# --- HTTP endpoints (GET/PUT /api/config) via app.test_client ---

@pytest.fixture
def client(cfg_file):
    try:
        import app as app_module  # noqa: E402
    except Exception as e:  # pragma: no cover - env without full app deps
        pytest.skip(f"app import unavailable: {e}")
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_get_config_endpoint(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    d = r.get_json()
    assert "schema" in d and "values" in d
    assert d["values"]["sync_delay"] == 0.5  # from SEED on disk
    assert d["values"]["fcc.weighEntry.defaultMode"] == "additive"  # client default


def test_put_config_good_value_logs_info(client, monkeypatch):
    import state
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: logs.append(a))
    r = client.put("/api/config", json={"values": {"sync_delay": 1.25}})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert any("INFO" in str(a) for a in logs)


def test_put_config_bad_value_400_logs_error(client, monkeypatch):
    import state
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: logs.append(a))
    r = client.put("/api/config", json={"values": {"sync_delay": "abc"}})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False
    assert any(("ERROR" in str(a) or "ff4444" in str(a)) for a in logs)


def test_put_config_non_dict_body_no_500(client):
    r = client.put("/api/config", json=[1, 2, 3])
    assert r.status_code != 500  # normalized to {} -> ok no-op, never crashes


def test_put_config_bare_body_accepted(client):
    r = client.put("/api/config", json={"sync_delay": 0.75})  # no "values" wrapper
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


# --- Static guard: the client localStorage key must not drift from WeightEntry ---

def test_client_key_shared_with_weight_entry():
    import pathlib
    mods = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "modules"
    weight_js = (mods / "weight_entry.js").read_text(encoding="utf-8")
    key = "fcc.weighEntry.defaultMode"
    assert key in weight_js, "weight_entry.js must reference the shared localStorage key"
    assert any(f["key"] == key for f in config_schema.schema_for_ui()["fields"]), \
        "config_schema must define the client key the WeightEntry reads"


# --- Phase 2: secret masking (never leak plaintext; sentinel = keep unchanged) ---

def test_get_endpoint_masks_secret(client):
    r = client.get("/api/config")
    body = r.get_data(as_text=True)
    d = r.get_json()
    assert d["values"]["SCRAPER_API_KEY"] == config_schema.SECRET_SENTINEL  # set -> sentinel
    assert "secret-key-123" not in body  # plaintext NEVER leaves the server


def test_save_secret_sentinel_preserves_existing(cfg_file):
    result = config_loader.save_config(
        {"SCRAPER_API_KEY": config_schema.SECRET_SENTINEL, "sync_delay": 1.5})
    assert result["ok"] is True
    on_disk = _read(cfg_file)
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"  # sentinel -> unchanged
    assert on_disk["sync_delay"] == 1.5  # sibling still saved


def test_save_secret_new_value_updates(cfg_file):
    result = config_loader.save_config({"SCRAPER_API_KEY": "brand-new-key"})
    assert result["ok"] is True
    assert _read(cfg_file)["SCRAPER_API_KEY"] == "brand-new-key"


def test_validate_payload_skips_secret_sentinel():
    coerced, errors = config_schema.validate_payload(
        {"SCRAPER_API_KEY": config_schema.SECRET_SENTINEL, "sync_delay": 2.0})
    assert errors == []
    assert "SCRAPER_API_KEY" not in coerced  # sentinel -> skipped (keep)
    assert coerced["sync_delay"] == 2.0


# --- Phase 2: ip + port field validation ---

def test_ip_field_validation():
    assert config_schema.coerce_and_validate("server_ip", "192.168.1.29") == "192.168.1.29"
    assert config_schema.coerce_and_validate("server_ip", "my-host.local") == "my-host.local"
    for bad in ("", "has space", "1.2.3.4; rm -rf"):
        with pytest.raises(config_schema.ConfigValidationError):
            config_schema.coerce_and_validate("server_ip", bad)


def test_port_field_validation():
    assert config_schema.coerce_and_validate("spoolman_port", "7913") == 7913
    # boundaries accepted
    assert config_schema.coerce_and_validate("spoolman_port", 1) == 1
    assert config_schema.coerce_and_validate("spoolman_port", 65535) == 65535
    # boundaries + junk rejected (65536 guards an off-by-one in the range check)
    for bad in (0, 65536, 70000, "abc", "nan"):
        with pytest.raises(config_schema.ConfigValidationError):
            config_schema.coerce_and_validate("spoolman_port", bad)


def test_port_rejects_bool():
    # int(True)==1 must NOT sneak a JSON boolean through as port 1
    with pytest.raises(config_schema.ConfigValidationError):
        config_schema.coerce_and_validate("spoolman_port", True)


def test_port_infinity_rejected_cleanly():
    # Phase 2 review: int(float('inf')) raises OverflowError — must normalize to
    # a clean ConfigValidationError (400), never escape as a 500.
    with pytest.raises(config_schema.ConfigValidationError):
        config_schema.coerce_and_validate("spoolman_port", float("inf"))
    coerced, errors = config_schema.validate_payload({"spoolman_port": float("inf")})
    assert errors and "spoolman_port" not in coerced


def test_save_connection_settings_persist(cfg_file):
    result = config_loader.save_config({"server_ip": "10.0.0.5", "spoolman_port": 7000})
    assert result["ok"] is True
    on_disk = _read(cfg_file)
    assert on_disk["server_ip"] == "10.0.0.5"
    assert on_disk["spoolman_port"] == 7000
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"  # untouched sibling preserved
    assert list(on_disk["printer_map"].keys()) == ["xl-1"]


# --- Spoolman host + vestigial fb_url (FilaBridge config keys removed post-cutover) ---

def test_server_ip_required_rejects_blank():
    # server_ip is NOT optional — blank is rejected. (It used to be paired with
    # an optional filabridge_ip field, removed in the FilaBridge cleanup.)
    with pytest.raises(config_schema.ConfigValidationError):
        config_schema.coerce_and_validate("server_ip", "")


def test_get_api_urls_vestigial_fb_url_derives_from_server_ip(tmp_path, monkeypatch):
    # Post-FilaBridge-decommission: filabridge_ip / filabridge_port were removed
    # from the schema. A config lacking them loads cleanly, sm_url is well-formed,
    # and fb_url is a vestigial server_ip-derived placeholder — kept only so the
    # (sm_url, fb_url) 2-tuple signature and its callers don't have to change.
    seed = {"server_ip": "10.0.0.1", "spoolman_port": 7000}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(seed), encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    sm, fb = config_loader.get_api_urls()
    assert sm == "http://10.0.0.1:7000"
    assert fb == "http://10.0.0.1:5000/api"


# --- Phase 2 review test-gaps: empty-secret GET + no-log-leak ---

def test_get_endpoint_empty_secret_returns_blank(tmp_path, monkeypatch):
    try:
        import app as app_module  # noqa: E402
    except Exception as e:  # pragma: no cover
        pytest.skip(f"app import unavailable: {e}")
    seed = dict(SEED)
    seed["SCRAPER_API_KEY"] = ""  # not set
    p = tmp_path / "config.json"
    p.write_text(json.dumps(seed), encoding="utf-8")
    monkeypatch.setattr(config_loader, "get_config_path", lambda: (str(p), "TEST"))
    d = app_module.app.test_client().get("/api/config").get_json()
    assert d["values"]["SCRAPER_API_KEY"] == ""  # unset -> "", NOT the sentinel


def test_put_secret_value_never_logged(client, monkeypatch):
    import state
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: logs.append((a, k)))
    r = client.put("/api/config", json={"values": {"SCRAPER_API_KEY": "super-secret-xyz"}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert "super-secret-xyz" not in " ".join(str(x) for x in logs)  # value never logged


# --- L18 Phase 3: printer_map canonicalization + guarded write ---

def test_canonicalize_printer_map_uppercases_keys():
    canon, err = config_loader._canonicalize_printer_map(
        {"xl-1": {"printer_name": "XL", "position": 0}})
    assert err is None
    assert list(canon.keys()) == ["XL-1"]
    assert canon["XL-1"] == {"printer_name": "XL", "position": 0}


def test_canonicalize_printer_map_case_collision_rejected():
    canon, err = config_loader._canonicalize_printer_map(
        {"xl-1": {"printer_name": "A", "position": 0},
         "XL-1": {"printer_name": "B", "position": 1}})
    assert canon is None and "collision" in err.lower()


def test_canonicalize_printer_map_shape_validation():
    _, e1 = config_loader._canonicalize_printer_map({"XL-1": {"position": 0}})  # no name
    assert e1 and "name" in e1.lower()
    _, e2 = config_loader._canonicalize_printer_map({"XL-1": {"printer_name": "X", "position": "abc"}})
    assert e2 and "position" in e2.lower()
    _, e3 = config_loader._canonicalize_printer_map({"XL-1": {"printer_name": "X", "position": -1}})
    assert e3 and "position" in e3.lower()


# NOTE (L271 Phase 4 step 4 — the cutover): the `save_printer_map` writer was
# RETIRED — printer_map is no longer written to config.json. Its on-disk-write
# tests (persists-uppercased-and-preserves-siblings / rejects-bad-shape-no-disk-
# change / refuses-on-corrupt-existing) were removed with it. The canonicalizer it
# used (`_canonicalize_printer_map`) is KEPT as the editor PUT's validator and is
# still covered by the three tests above; the row-write persistence is covered by
# the /api/printer_map PUT tests below.


def _ref_env(monkeypatch, slot_targets=None, spools_by_loc=None,
             spool_raises=False, locations_raises=False):
    """Stub the referential sources the PUT /api/printer_map guard consults.
    spool_raises / locations_raises simulate a dependency outage so the guard's
    fail-CLOSED behavior can be tested.

    L271 Phase 4 (step 4 — the cutover): the guard's `old_map` is now ROW-sourced
    via locations_db.get_active_printer_map() (was config:printer_map). So seed a
    first-class Type:"Printer" row carrying toolheads[]=[{XL-1, 0}] — the same
    single XL-* toolhead the pre-cutover config SEED exposed — so removing /
    renaming XL-1 is what the guard tests exercise. The Dryer Box row (added when
    slot_targets is given) carries the bindings the guard's slot scan reads; a
    single load_locations_list stub serves both the active-map read and the scan.
    The save_locations_list no-op isolates the PUT's authoritative row write from
    the real data/locations.json (the dev-data wipe documented in
    reference_fcc_e2e_sweep_pollution — the "rename/bindings test", 53→2)."""
    import locations_db
    import spoolman_api
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
             "toolheads": [{"location_id": "XL-1", "position": 0}]}]
    if slot_targets:
        rows.append({"LocationID": "PM-DB-1", "Type": "Dryer Box",
                     "extra": {"slot_targets": slot_targets}})
    if locations_raises:
        def _boom():
            raise RuntimeError("locations.json corrupt")
        monkeypatch.setattr(locations_db, "load_locations_list", _boom)
    else:
        monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)
    # Isolate the PUT /api/printer_map post-save sync (it re-runs the Phase-3
    # printer-rows + Phase-4 toolheads[] migrations and persists them). Without
    # this no-op, save_locations_list would overwrite the REAL data/locations.json
    # with the tiny `rows` stub above — the long-standing dev-data wipe documented
    # in reference_fcc_e2e_sweep_pollution (the "rename/bindings test", 53→2).
    monkeypatch.setattr(locations_db, "save_locations_list", lambda *_a, **_k: True)
    sbl = spools_by_loc or {}
    if spool_raises:
        def _sboom(loc):
            raise RuntimeError("Spoolman unreachable")
        monkeypatch.setattr(spoolman_api, "get_spools_at_location_strict", _sboom)
    else:
        monkeypatch.setattr(spoolman_api, "get_spools_at_location_strict",
                            lambda loc: sbl.get(str(loc).strip().upper(), []))


def test_put_printer_map_add_and_edit_allowed(client, monkeypatch):
    _ref_env(monkeypatch)  # nothing referenced; SEED printer_map is {"xl-1": ...}
    new_pm = {"XL-1": {"printer_name": "XL Renamed", "position": 2},
              "XL-6": {"printer_name": "XL Renamed", "position": 5}}
    r = client.put("/api/printer_map", json={"printer_map": new_pm})
    assert r.status_code == 200
    assert set(r.get_json()["printer_map"].keys()) == {"XL-1", "XL-6"}


def test_put_printer_map_remove_unreferenced_allowed(client, monkeypatch):
    _ref_env(monkeypatch)  # XL-1 not referenced anywhere
    r = client.put("/api/printer_map", json={"printer_map": {"XL-9": {"printer_name": "New", "position": 0}}})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_put_printer_map_remove_bound_to_slot_blocked(client, monkeypatch):
    _ref_env(monkeypatch, slot_targets={"1": "XL-1"})  # a dryer slot points at XL-1
    r = client.put("/api/printer_map", json={"printer_map": {"XL-9": {"printer_name": "New", "position": 0}}})
    assert r.status_code == 409
    d = r.get_json()
    assert d["ok"] is False and any(b["location_id"] == "XL-1" for b in d["blocked"])


def test_put_printer_map_remove_with_spools_blocked(client, monkeypatch):
    _ref_env(monkeypatch, spools_by_loc={"XL-1": [{"id": 1}]})  # a spool sits at XL-1
    r = client.put("/api/printer_map", json={"printer_map": {"XL-9": {"printer_name": "New", "position": 0}}})
    assert r.status_code == 409
    assert r.get_json()["ok"] is False


# --- Phase 3 review fixes: guard FAILS CLOSED + PRINTER:<prefix> sentinel ---

def test_put_printer_map_fails_closed_when_spoolman_unreachable(client, monkeypatch):
    _ref_env(monkeypatch, spool_raises=True)  # can't verify spools
    r = client.put("/api/printer_map", json={"printer_map": {"XL-9": {"printer_name": "New", "position": 0}}})
    assert r.status_code == 409
    d = r.get_json()
    assert d["ok"] is False
    assert any("could not verify" in " ".join(b["reasons"]).lower() for b in d["blocked"])


def test_put_printer_map_fails_closed_when_locations_unreadable(client, monkeypatch):
    _ref_env(monkeypatch, locations_raises=True)  # can't scan slot_targets
    r = client.put("/api/printer_map", json={"printer_map": {"XL-9": {"printer_name": "New", "position": 0}}})
    assert r.status_code == 409
    assert r.get_json()["ok"] is False


def test_put_printer_map_blocks_last_toolhead_of_pool_prefix(client, monkeypatch):
    # a dryer pool slot feeds PRINTER:XL; SEED's only XL-* toolhead is XL-1 —
    # removing it drops the XL prefix, so the PRINTER:XL slot would dangle.
    _ref_env(monkeypatch, slot_targets={"4": "PRINTER:XL"})
    r = client.put("/api/printer_map", json={"printer_map": {"CORE1-M0": {"printer_name": "C1", "position": 0}}})
    assert r.status_code == 409
    d = r.get_json()
    assert any("PRINTER:XL" in " ".join(b["reasons"]) for b in d["blocked"])


def test_put_printer_map_allows_pool_prefix_when_another_toolhead_remains(client, monkeypatch):
    # keep an XL-* toolhead so the XL prefix survives -> the PRINTER:XL slot is fine
    _ref_env(monkeypatch, slot_targets={"4": "PRINTER:XL"})
    r = client.put("/api/printer_map", json={"printer_map": {"XL-2": {"printer_name": "XL", "position": 1}}})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_put_printer_map_lowercase_resubmit_is_not_a_removal(client, monkeypatch):
    _ref_env(monkeypatch, slot_targets={"1": "XL-1"})  # XL-1 IS bound
    # resubmit the existing key in lowercase + edit its name -> NOT a removal
    r = client.put("/api/printer_map", json={"printer_map": {"xl-1": {"printer_name": "XL Renamed", "position": 0}}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert "XL-1" in r.get_json()["printer_map"]  # canonicalized, kept


def test_put_printer_map_write_fault_is_500(client, monkeypatch):
    # L271 Phase 4 (step 4): the PUT now persists onto the Printer rows; a failed
    # locations.json write is the infra fault that yields 500 (was a config write).
    import locations_db
    _ref_env(monkeypatch)
    monkeypatch.setattr(locations_db, "save_locations_list", lambda *_a, **_k: False)
    r = client.put("/api/printer_map", json={"printer_map": {"XL-1": {"printer_name": "X", "position": 0}}})
    assert r.status_code == 500  # infra fault, not client bad-input


def test_put_printer_map_validation_error_is_400(client, monkeypatch):
    # A genuinely bad shape (missing name) is rejected by the canonicalizer BEFORE
    # any write — a client 400, no rows touched.
    _ref_env(monkeypatch)
    r = client.put("/api/printer_map", json={"printer_map": {"XL-1": {"position": 0}}})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_put_printer_map_rename_propagates_to_printer_row(client, monkeypatch):
    # L271 Phase 4 (step 4): printer_name is now the Printer row's Name (single
    # source of truth). Editing it in the editor must propagate to the row Name —
    # neither toolheads[] fold nor the rows migration touches Name, so the PUT
    # syncs it explicitly. (Restores the rename behavior the Step-3 GET shim broke.)
    import locations_db
    captured = {}
    _ref_env(monkeypatch)  # seeds XL Printer row Name "🦝 XL", toolheads [{XL-1, 0}]
    monkeypatch.setattr(locations_db, "save_locations_list",
                        lambda locs, *a, **k: (captured.__setitem__("locs", locs), True)[1])
    r = client.put("/api/printer_map",
                   json={"printer_map": {"XL-1": {"printer_name": "🦝 XL Pro", "position": 0}}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    xl = next(row for row in captured["locs"] if row.get("LocationID") == "XL")
    assert xl["Name"] == "🦝 XL Pro"  # rename propagated to the row


def test_put_printer_map_preserves_arbitrary_positions_verbatim(client, monkeypatch):
    # HARD CONSTRAINT: position IS the FilaBridge toolhead_id (0-based), sent
    # verbatim. The PUT must store positions EXACTLY — never auto-renumber/compact.
    # A deliberately NON-CONTIGUOUS set (gap at 2..6) proves no resequencing.
    import locations_db
    captured = {}
    _ref_env(monkeypatch)  # old_map = {XL-1}; keeping XL-1 means no guarded removal
    monkeypatch.setattr(locations_db, "save_locations_list",
                        lambda locs, *a, **k: (captured.__setitem__("locs", locs), True)[1])
    pm = {"XL-1": {"printer_name": "🦝 XL", "position": 0},
          "XL-2": {"printer_name": "🦝 XL", "position": 1},
          "XL-7": {"printer_name": "🦝 XL", "position": 7}}  # gap: no 2..6
    r = client.put("/api/printer_map", json={"printer_map": pm})
    assert r.status_code == 200
    xl = next(row for row in captured["locs"] if row.get("LocationID") == "XL")
    positions = {th["location_id"]: th["position"] for th in xl["toolheads"]}
    assert positions == {"XL-1": 0, "XL-2": 1, "XL-7": 7}  # verbatim, gap preserved


def test_canonicalize_printer_map_rejects_bool_position():
    _, err = config_loader._canonicalize_printer_map({"XL-1": {"printer_name": "X", "position": True}})
    assert err and "boolean" in err.lower()


# --- L18 Phase 4: config export / import ---

def test_export_redacts_secret(client):
    r = client.get("/api/config/export")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "secret-key-123" not in body  # plaintext NOT in the export
    d = json.loads(body)
    assert d["SCRAPER_API_KEY"] == config_schema.SECRET_SENTINEL
    assert d["server_ip"] == "192.168.1.29"  # full backup — other keys present
    assert "printer_map" in d


def test_export_include_secrets(client):
    r = client.get("/api/config/export?include_secrets=1")
    d = json.loads(r.get_data(as_text=True))
    assert d["SCRAPER_API_KEY"] == "secret-key-123"  # plaintext only when explicitly asked


def test_export_corrupt_config_is_409(client, monkeypatch):
    # A present-but-unreadable config must NOT export as an empty {} "backup".
    monkeypatch.setattr(config_loader, "load_config_raw", lambda: None)
    r = client.get("/api/config/export")
    assert r.status_code == 409
    assert r.get_json()["ok"] is False


def test_import_dry_run_returns_diff_no_write(client, cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    r = client.post("/api/config/import", json={"config": {"sync_delay": 1.5}, "dry_run": True})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] and d["dry_run"] is True
    assert any(x["key"] == "sync_delay" for x in d["diff"])
    assert cfg_file.read_text(encoding="utf-8") == before  # dry-run writes nothing


def test_import_applies_patch_only_ignoring_non_schema(client, cfg_file):
    r = client.post("/api/config/import", json={"config": {
        "sync_delay": 2.5,
        "printer_map": {"BOGUS": {"printer_name": "x", "position": 0}},  # not a schema field
        "comment": "hacked",
    }})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] and "sync_delay" in d["saved"]
    assert "printer_map" in d["ignored"] and "comment" in d["ignored"]
    on_disk = _read(cfg_file)
    assert on_disk["sync_delay"] == 2.5  # applied
    assert list(on_disk["printer_map"].keys()) == ["xl-1"]  # UNTOUCHED (ignored)
    assert on_disk["comment"] == "--- DEV CONFIGURATION ---"  # UNTOUCHED


def test_import_validation_rejects_bad_no_write(client, cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    r = client.post("/api/config/import", json={"config": {"sync_delay": "abc"}})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False
    assert cfg_file.read_text(encoding="utf-8") == before


def test_import_secret_sentinel_keeps_existing(client, cfg_file):
    r = client.post("/api/config/import", json={"config": {
        "SCRAPER_API_KEY": config_schema.SECRET_SENTINEL, "sync_delay": 3.0}})
    assert r.status_code == 200 and r.get_json()["ok"]
    on_disk = _read(cfg_file)
    assert on_disk["SCRAPER_API_KEY"] == "secret-key-123"  # sentinel -> kept
    assert on_disk["sync_delay"] == 3.0


def test_import_non_dict_body_400(client):
    assert client.post("/api/config/import", json=[1, 2, 3]).status_code == 400
    assert client.post("/api/config/import", json={"config": "nope"}).status_code == 400


def test_import_round_trips_redacted_export(client, cfg_file):
    # export (redacted) then import it back -> secret preserved via the sentinel
    exported = json.loads(client.get("/api/config/export").get_data(as_text=True))
    r = client.post("/api/config/import", json={"config": exported})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert _read(cfg_file)["SCRAPER_API_KEY"] == "secret-key-123"


def test_import_new_secret_masked_in_diff_and_response(client, cfg_file):
    # TOP-PRIORITY regression guard: a NEW (non-sentinel) secret submitted on
    # import must NEVER be echoed back in the dry-run diff OR the apply response.
    hostile = "hostile-new-key-xyz"
    r = client.post("/api/config/import",
                    json={"config": {"SCRAPER_API_KEY": hostile, "sync_delay": 1.0}, "dry_run": True})
    assert r.status_code == 200
    assert hostile not in r.get_data(as_text=True)  # plaintext never echoed
    sec = [x for x in r.get_json()["diff"] if x["key"] == "SCRAPER_API_KEY"]
    assert sec and sec[0]["to"] == "(new secret)"
    # apply: still not echoed; on-disk gets the new value
    r2 = client.post("/api/config/import", json={"config": {"SCRAPER_API_KEY": hostile}})
    assert r2.status_code == 200 and hostile not in r2.get_data(as_text=True)
    assert _read(cfg_file)["SCRAPER_API_KEY"] == hostile  # applied, just never echoed


def test_import_patch_leaves_omitted_keys(client, cfg_file):
    # PATCH, not replace: importing only sync_delay must leave other keys as-is.
    client.post("/api/config/import", json={"config": {"sync_delay": 4.0}})
    on_disk = _read(cfg_file)
    assert on_disk["sync_delay"] == 4.0
    assert on_disk["server_ip"] == "192.168.1.29"
    assert on_disk["spoolman_port"] == 7913
    assert on_disk["dryer_slots"] == ["PM-DB-1", "PM-DB-2"]


def test_import_apply_write_fault_is_500(client, monkeypatch):
    monkeypatch.setattr(config_loader, "save_config",
                        lambda v: {"ok": False, "error": "config write failed: disk full"})
    r = client.post("/api/config/import", json={"config": {"sync_delay": 1.0}})
    assert r.status_code == 500 and r.get_json()["ok"] is False


def test_import_apply_refuse_on_corrupt_is_409(client, monkeypatch):
    monkeypatch.setattr(config_loader, "save_config",
                        lambda v: {"ok": False, "error": "refusing to save: the existing config ..."})
    r = client.post("/api/config/import", json={"config": {"sync_delay": 1.0}})
    assert r.status_code == 409


def test_import_deeply_nested_json_is_400_not_500(client):
    # RecursionError from json.loads on deep nesting must be a clean 400, not 500.
    deep = "[" * 50000 + "]" * 50000  # ~100KB, under the size cap -> reaches the parser
    r = client.post("/api/config/import", data=deep, content_type="application/json")
    assert r.status_code == 400


def test_import_oversized_body_is_413(client):
    big = '{"config": {"sync_delay": 1.0, "x": "' + ("a" * (600 * 1024)) + '"}}'
    r = client.post("/api/config/import", data=big, content_type="application/json")
    assert r.status_code == 413
