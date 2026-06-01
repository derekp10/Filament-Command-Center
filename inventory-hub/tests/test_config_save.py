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
    "filabridge_port": 5001,
    "sync_delay": 0.5,
    "spoolman_db_path": "\\\\TRUENAS\\App_Data\\Spoolman\\spoolman.db",
    "print_settings": {"mode": "browser", "csv_path": "/output/test_queue.csv"},
    "buy_more_url_template": "https://www.amazon.com/s?k={{vendor}}",
    "printer_map": {"xl-1": {"printer_name": "🦝 XL", "position": 0}},
    "dryer_slots": ["PM-DB-1", "PM-DB-2"],
    "auto_recover_filabridge_errors": True,
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
    result = config_loader.save_config({"auto_recover_filabridge_errors": "false"})
    assert result["ok"] is True
    assert _read(cfg_file)["auto_recover_filabridge_errors"] is False


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
    for k in ("server_ip", "spoolman_port", "filabridge_port", "printer_map", "dryer_slots"):
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
