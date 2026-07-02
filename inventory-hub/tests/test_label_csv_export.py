"""Label-CSV export robustness (Option-B standalone sweep, 2026-06-16).

Derek runs a Brother P-touch label template that links the FCC label-export
CSV as its DATABASE source; while P-touch is open it holds a Windows file
handle, so a UI export used to fail SILENTLY (short toast, no Activity Log).

Pins:
  - `_write_label_csv` writes the overwrite path atomically (temp + os.replace),
    leaves no stray temp file, and on a locked target raises (cleaning the temp)
    rather than leaving a torn file.
  - the /api/print_batch_csv endpoint surfaces a lock LOUDLY: success=False,
    locked=True, an Activity Log ERROR entry, and a P-touch-aware message — and
    logs the success path too.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
import labels_csv  # L316 step 3: moved-symbol patch targets live here now  # noqa: E402


# ---------------------------------------------------------------------------
# _write_label_csv — the atomic helper
# ---------------------------------------------------------------------------

def test_overwrite_writes_atomically_with_no_temp_left(tmp_path):
    path = str(tmp_path / "labels_spool.csv")
    rows = [{"ID": "1", "Brand": "Acme"}, {"ID": "2", "Brand": "Beta"}]
    app_module._write_label_csv(path, ["ID", "Brand"], rows, overwrite=True, write_header=True)
    content = (tmp_path / "labels_spool.csv").read_text(encoding="utf-8")
    assert "ID,Brand" in content
    assert "1,Acme" in content and "2,Beta" in content
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "labels_spool.csv"]
    assert leftovers == [], f"atomic overwrite left stray files: {leftovers}"


def test_append_adds_rows_keeping_single_header(tmp_path):
    path = str(tmp_path / "labels_spool.csv")
    app_module._write_label_csv(path, ["ID", "Brand"], [{"ID": "1", "Brand": "Acme"}],
                                overwrite=True, write_header=True)
    app_module._write_label_csv(path, ["ID", "Brand"], [{"ID": "2", "Brand": "Beta"}],
                                overwrite=False, write_header=False)
    lines = [ln for ln in (tmp_path / "labels_spool.csv").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines.count("ID,Brand") == 1, "append must not duplicate the header"
    assert "1,Acme" in lines and "2,Beta" in lines


def test_overwrite_locked_target_raises_and_cleans_temp(tmp_path, monkeypatch):
    """A held handle (P-touch/Excel) makes os.replace raise PermissionError;
    the helper must propagate it AND remove its temp file, leaving the
    original target untouched (never a torn write)."""
    path = str(tmp_path / "labels_spool.csv")
    (tmp_path / "labels_spool.csv").write_text("ID,Brand\nold,old\n", encoding="utf-8")

    def _boom(src, dst):
        raise PermissionError(13, "locked by another process")

    monkeypatch.setattr(app_module.os, "replace", _boom)
    with pytest.raises(PermissionError):
        app_module._write_label_csv(path, ["ID", "Brand"], [{"ID": "1", "Brand": "Acme"}],
                                    overwrite=True, write_header=True)
    leftovers = sorted(p.name for p in tmp_path.iterdir())
    assert leftovers == ["labels_spool.csv"], f"temp not cleaned after lock: {leftovers}"
    assert (tmp_path / "labels_spool.csv").read_text(encoding="utf-8").strip().endswith("old,old"), \
        "original target must be untouched on a failed atomic write"


def test_locked_overwrite_tags_offending_filename(tmp_path, monkeypatch):
    """On a lock the raised PermissionError carries the basename of the file
    actually held open, so the endpoint names the right file (the main labels
    CSV and slots_to_print.csv can be locked independently)."""
    path = str(tmp_path / "labels_locations.csv")

    def _boom(src, dst):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(app_module.os, "replace", _boom)
    with pytest.raises(PermissionError) as ei:
        app_module._write_label_csv(path, ["ID"], [{"ID": "1"}], overwrite=True, write_header=True)
    assert getattr(ei.value, "fcc_locked_name", None) == "labels_locations.csv"


# ---------------------------------------------------------------------------
# /api/print_batch_csv — never-silent contract
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return app_module.app.test_client()


def _fake_spool(sid):
    return {
        "id": sid,
        "remaining_weight": 500,
        "filament": {"material": "PLA", "vendor": {"name": "Acme"}, "extra": {}, "color_hex": "AABBCC"},
    }


def _stub_label_helpers(monkeypatch):
    """Decouple the endpoint test from label data-extraction internals."""
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: _fake_spool(sid))
    monkeypatch.setattr(app_module.config_loader, "load_config", lambda: {})
    monkeypatch.setattr(labels_csv, "get_color_name", lambda f: "TestColor")
    monkeypatch.setattr(labels_csv, "get_smart_type", lambda m, e: "PLA")
    monkeypatch.setattr(labels_csv, "get_best_hex", lambda f: "AABBCC")


def test_endpoint_surfaces_lock_loudly(client, monkeypatch):
    logs = []
    _stub_label_helpers(monkeypatch)

    def _locked(*a, **k):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(labels_csv, "_write_label_csv", _locked)
    monkeypatch.setattr(app_module.state, "add_log_entry", lambda msg, *a, **k: logs.append((msg,) + tuple(a)))

    resp = client.post("/api/print_batch_csv", json={"ids": [1], "mode": "spool", "clear_old": True})
    body = resp.get_json()
    assert body["success"] is False
    assert body.get("locked") is True, "lock must be flagged so the UI can guide the user"
    assert "lock" in body["msg"].lower()
    assert logs, "a locked export must write an Activity Log entry (never silent)"
    assert any(len(t) > 1 and t[1] == "ERROR" for t in logs), "lock must log at ERROR severity"
    assert any("lock" in t[0].lower() for t in logs)


def test_endpoint_logs_success(client, monkeypatch):
    logs = []
    captured = {}
    _stub_label_helpers(monkeypatch)

    def _capture(path, fieldnames, rows, *, overwrite, write_header):
        captured["rows"] = list(rows)
        captured["overwrite"] = overwrite

    monkeypatch.setattr(labels_csv, "_write_label_csv", _capture)
    monkeypatch.setattr(app_module.state, "add_log_entry", lambda msg, *a, **k: logs.append((msg,) + tuple(a)))

    resp = client.post("/api/print_batch_csv", json={"ids": [1, 2], "mode": "spool", "clear_old": True})
    body = resp.get_json()
    assert body["success"] is True
    assert body["count"] == 2
    assert captured["overwrite"] is True
    assert any("Label CSV" in t[0] for t in logs), "a successful export must write an Activity Log entry"
