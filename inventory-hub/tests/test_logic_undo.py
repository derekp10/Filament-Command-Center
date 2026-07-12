"""Unit tests for `logic.perform_smart_move` / `perform_undo` recording semantics.

Moved here from the legacy project-root `tests/` directory (2026-05-12, Group
16.1) so the regression sweep actually covers it. Covers UNDO_STACK origin
tracking, buffer-origin restoration, and the live-spool fetch path.
"""
import pytest
from unittest.mock import patch, MagicMock

import logic
import state


@pytest.fixture
def mock_state():
    # Setup fresh state before each test
    state.UNDO_STACK = []
    state.GLOBAL_BUFFER = []

    # Mock logger to avoid console spam
    with patch('state.logger', MagicMock()):
        with patch('state.add_log_entry', MagicMock()):
            yield state

@pytest.fixture
def mock_spoolman():
    with patch('logic.spoolman_api') as mock_api:
        # L298 Phase 0 — the undo snapshot/restore iterates
        # spoolman_api.SYSTEM_MANAGED_EXTRAS; a bare MagicMock would iterate empty,
        # so give it the real key set to exercise the true rollback behavior.
        mock_api.SYSTEM_MANAGED_EXTRAS = frozenset(
            {'container_slot', 'physical_source', 'physical_source_slot'}
        )
        # Mock spoolman API responses
        mock_api.get_spool.return_value = {
            'id': 123,
            'location': 'OLD_SHELF',
            'extra': {}
        }
        mock_api.format_spool_display.return_value = {
            'text': 'Test Spool',
            'color': '#ff0000'
        }
        mock_api.get_spools_at_location.return_value = []
        yield mock_api

@pytest.fixture
def mock_config():
    with patch('logic.config_loader') as mock_cfg:
        mock_cfg.load_config.return_value = {
            "printer_map": {
                "CORE1": {"printer_name": "core", "position": 0},
                "CORE1-M4": {"printer_name": "core", "position": 4}
            }
        }
        mock_cfg.get_api_urls.return_value = ("http://spoolman", "http://filabridge")
        yield mock_cfg

@pytest.fixture
def mock_locations():
    with patch('logic.locations_db') as mock_db:
        mock_db.load_locations_list.return_value = [
            {'LocationID': 'NEW_SHELF', 'Type': 'Shelf'},
            {'LocationID': 'DRYER-01', 'Type': 'Dryer Box'},
            {'LocationID': 'PRINTER-1', 'Type': 'Tool Head'},
            {'LocationID': 'CORE1-M4', 'Type': 'MMU Slot'}
        ]
        yield mock_db

@pytest.fixture
def mock_requests():
    with patch('logic.requests') as mock_req:
        yield mock_req


def test_standard_undo_recording(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """Test Case 1: Standard Undo properly records source location"""

    # 1. Perform a move
    result = logic.perform_smart_move("NEW_SHELF", [123])

    # 2. Assert Move recorded success
    assert result['status'] == 'success'
    assert len(mock_state.UNDO_STACK) == 1

    record = mock_state.UNDO_STACK[0]
    assert record['target'] == "NEW_SHELF"
    assert record['moves'][123] == "OLD_SHELF" # ensure it remembered the old place
    assert record['origin'] == ""

    # 3. Perform Undo
    undo_result = logic.perform_undo()
    assert undo_result['success'] == True
    assert len(mock_state.UNDO_STACK) == 0

    # Ensure Spoolman was told to put it back.
    # L298 Phase 0: undo now restores the pre-move system-managed extras too
    # (all '' here — the mock spool had an empty extra). The write routes through
    # spoolman_api.update_spool (which sanitizes to wire form + read-merge-writes),
    # NOT a raw requests.patch — pinning the 2026-07-11 wire-format fix.
    mock_spoolman.update_spool.assert_called_with(123, {"location": "OLD_SHELF", "extra": {"container_slot": "", "physical_source": "", "physical_source_slot": ""}})
    mock_requests.patch.assert_not_called()

    # Ensure buffer wasn't polluted
    assert len(mock_state.GLOBAL_BUFFER) == 0


def test_buffer_restoration_undo(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """Test Case 2: Buffer Origin gets correctly pushed back into GLOBAL_BUFFER"""

    # 1. Perform move specifically from buffer
    result = logic.perform_smart_move("NEW_SHELF", [123], origin='buffer')

    # 2. Assert Move recorded success
    assert result['status'] == 'success'
    assert len(mock_state.UNDO_STACK) == 1

    record = mock_state.UNDO_STACK[0]
    assert record['origin'] == "buffer"

    # 3. Perform Undo
    undo_result = logic.perform_undo()
    assert undo_result['success'] == True

    # 4. Verify Buffer Injection
    assert len(mock_state.GLOBAL_BUFFER) == 1
    assert mock_state.GLOBAL_BUFFER[0]['id'] == 123
    assert mock_state.GLOBAL_BUFFER[0]['display'] == 'Test Spool'

    # Ensure Spoolman was ALSO told to put it back (buffer shouldn't prevent physical rollback)
    # L298 Phase 0: undo now restores the pre-move system-managed extras too
    # (all '' here — the mock spool had an empty extra), via update_spool.
    mock_spoolman.update_spool.assert_called_with(123, {"location": "OLD_SHELF", "extra": {"container_slot": "", "physical_source": "", "physical_source_slot": ""}})


def test_missing_ghost_cleanup_on_undo(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """Test Case 3 (L298 Phase 0): reverting a move that stamped a phantom
    physical_source properly CLEARS it on undo — while preserving sibling extras.
    Pre-fix, perform_undo restored only `location`, leaving the ghost trail."""
    # Post-move the spool carries a phantom physical_source/slot (the ghost) plus
    # an unrelated sibling extra; the undo record snapshotted the PRE-move state
    # (no ghost). Undo must read-merge-write: clear the 3 system-managed keys back
    # to their pre-move '' and keep spool_type.
    mock_spoolman.get_spool.return_value = {
        'id': 123, 'location': 'NEW_SHELF',
        'extra': {'physical_source': 'HOME-BOX', 'physical_source_slot': '2',
                  'container_slot': '3', 'spool_type': 'PLA'},
    }
    mock_state.UNDO_STACK = [{
        'target': 'NEW_SHELF', 'moves': {123: 'OLD_SHELF'},
        'extras': {123: {'container_slot': '', 'physical_source': '', 'physical_source_slot': ''}},
        'labels': {123: 'Test Spool'}, 'ejections': {}, 'origin': '',
    }]
    assert logic.perform_undo()['success'] is True
    args, _ = mock_spoolman.update_spool.call_args   # update_spool(sid, payload)
    payload = args[1]
    assert payload['location'] == 'OLD_SHELF'
    assert payload['extra']['physical_source'] == ''        # phantom ghost cleared
    assert payload['extra']['physical_source_slot'] == ''
    assert payload['extra']['container_slot'] == ''
    assert payload['extra']['spool_type'] == 'PLA'          # sibling extra preserved


def test_undo_restores_prior_slot_and_ghost(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """L298 Phase 0: a full rollback — a spool moved OUT of a bound slot returns
    to its exact prior container_slot + physical_source on undo (not just its
    location). This is what makes a bulk-move undo trustworthy."""
    # Snapshot = the spool's real prior seat; current (post-move) state differs.
    mock_spoolman.get_spool.return_value = {
        'id': 123, 'location': 'DEST', 'extra': {'container_slot': '', 'physical_source': '', 'spool_type': 'PETG'},
    }
    mock_state.UNDO_STACK = [{
        'target': 'DEST', 'moves': {123: 'PM-DB-XL-L'},
        'extras': {123: {'container_slot': '2', 'physical_source': 'PM-DB-XL-L', 'physical_source_slot': '2'}},
        'labels': {123: 'Test Spool'}, 'ejections': {}, 'origin': '',
    }]
    assert logic.perform_undo()['success'] is True
    args, _ = mock_spoolman.update_spool.call_args   # update_spool(sid, payload)
    payload = args[1]
    assert payload['location'] == 'PM-DB-XL-L'
    assert payload['extra']['container_slot'] == '2'          # exact prior slot restored
    assert payload['extra']['physical_source'] == 'PM-DB-XL-L'
    assert payload['extra']['physical_source_slot'] == '2'
    assert payload['extra']['spool_type'] == 'PETG'          # sibling preserved

def test_undo_extra_payload_reaches_spoolman_wire_sanitized(mock_state, monkeypatch):
    """REGRESSION (caught live 2026-07-11): the undo extra-restore must reach
    Spoolman as JSON-encoded strings. Pre-fix, perform_undo raw-PATCHed the
    snapshot with unwrapped '' values → Spoolman 400'd the WHOLE request
    (location included) → the undo silently no-op'd while reporting success. The
    Phase-0 mock tests all patched the HTTP layer, so none could see the
    wire-format rejection. This runs the REAL spoolman_api.update_spool (mocking
    ONLY the HTTP layer) and asserts every extra value on the wire is valid JSON
    and the unrelated sibling extra survives."""
    import json as _json
    import spoolman_api

    state.UNDO_STACK = [{
        'target': 'DEST', 'moves': {123: 'PM-DB-XL-L'},
        'extras': {123: {'container_slot': '', 'physical_source': '', 'physical_source_slot': ''}},
        'labels': {123: 'S'}, 'ejections': {}, 'origin': '',
    }]

    # The live spool carries a sibling extra (wire form) that must survive.
    existing_spool = {'id': 123, 'location': 'DEST', 'extra': {'spool_type': '"PLA"'}}
    captured = {}

    class _GetResp:
        ok = True
        status_code = 200
        def json(self):
            return existing_spool

    class _PatchResp:
        ok = True
        status_code = 200
        def json(self):
            return {'id': 123}

    fake_requests = MagicMock()
    fake_requests.get.side_effect = lambda *a, **k: _GetResp()
    def _patch(url, json=None, *a, **k):
        captured['json'] = json
        return _PatchResp()
    fake_requests.patch.side_effect = _patch

    monkeypatch.setattr(spoolman_api, 'requests', fake_requests)
    monkeypatch.setattr(spoolman_api.config_loader, 'get_api_urls', lambda: ('http://sm', 'http://fb'))

    assert logic.perform_undo()['success'] is True

    # A PATCH reached the wire (pre-fix, the raw logic.requests path meant
    # spoolman_api.update_spool was never called → this stays empty).
    assert 'json' in captured, "no PATCH was sent — undo did not write via update_spool"
    payload = captured['json']
    assert payload['location'] == 'PM-DB-XL-L'
    # EVERY extra value must be valid JSON on the wire — the guard against the bug.
    for k, v in payload['extra'].items():
        _json.loads(v)  # raises on the pre-fix raw '' → the regression trip-wire
    assert _json.loads(payload['extra']['container_slot']) == ''   # restored empty
    assert _json.loads(payload['extra']['spool_type']) == 'PLA'    # sibling preserved


def test_empty_toolhead_buffer_swap(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """Test Case 4: Verify origin='buffer' is retained when moving into an empty toolhead slot."""
    # This mirrors the user's exact workflow: Buffer -> CORE1-M4 -> Undo

    # 1. Perform move specifically from buffer into empty Toolhead MMU Slot
    result = logic.perform_smart_move("CORE1-M4", [123], origin='buffer')

    # 2. Assert Move recorded success and retained origin correctly BEFORE undo
    assert result['status'] == 'success'
    assert len(mock_state.UNDO_STACK) == 1

    record = mock_state.UNDO_STACK[0]
    print(record)
    assert record['origin'] == "buffer" # FAILING HERE?

    # 3. Perform Undo
    undo_result = logic.perform_undo()
    assert undo_result['success'] == True

    # 4. Verify Buffer Injection (This is what is failing for user)
    assert len(mock_state.GLOBAL_BUFFER) == 1


def test_undo_log_line_names_spool_and_source(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """The Undo activity-log line must name the spool + its source, not just a
    count (the '↩️ Undid: Moved 1 -> CR' readability bug, 2026-06-15)."""
    # 1. The move captures the rich display label alongside the source location.
    logic.perform_smart_move("NEW_SHELF", [123])
    record = mock_state.UNDO_STACK[0]
    assert record['labels'][123] == 'Test Spool'

    # 2. Undo emits a readable from→to line (not the count-only summary).
    logic.perform_undo()
    logged = [c.args[0] for c in state.add_log_entry.call_args_list if c.args]
    undo_lines = [m for m in logged if isinstance(m, str) and m.startswith("↩️ Undid:")]
    assert undo_lines, "no Undo line was logged"
    assert undo_lines[-1] == "↩️ Undid: moved Test Spool from OLD_SHELF -> NEW_SHELF"


def test_undo_empty_stack_message_signals_move_only_scope(mock_state):
    """Hitting Undo with nothing to undo should make the move-only scope clear
    (Derek hit Undo expecting a weight rollback)."""
    mock_state.UNDO_STACK = []
    res = logic.perform_undo()
    assert res['success'] is False
    assert "moves only" in res['msg'].lower()


def test_undo_log_line_lists_multiple_spools(mock_state, mock_spoolman, mock_config, mock_locations, mock_requests):
    """A multi-spool undo names every spool + its source, with the destination
    stated ONCE in the header (not repeated per segment)."""
    mock_spoolman.get_spool.side_effect = lambda sid: {
        123: {'id': 123, 'location': 'OLD_A', 'extra': {}},
        124: {'id': 124, 'location': 'OLD_B', 'extra': {}},
    }.get(int(sid))
    mock_spoolman.format_spool_display.side_effect = lambda sd: {
        123: {'text': 'Spool A', 'color': '#fff'},
        124: {'text': 'Spool B', 'color': '#000'},
    }[int(sd['id'])]

    logic.perform_smart_move("NEW_SHELF", [123, 124])
    logic.perform_undo()

    logged = [c.args[0] for c in state.add_log_entry.call_args_list if c.args]
    line = [m for m in logged if isinstance(m, str) and m.startswith("↩️ Undid:")][-1]
    assert "2 spools -> NEW_SHELF" in line
    assert "Spool A from OLD_A" in line
    assert "Spool B from OLD_B" in line
    # destination stated once (in the header), not repeated per segment
    assert line.count("-> NEW_SHELF") == 1, f"target should appear once: {line!r}"


def test_undo_legacy_record_without_labels_renders(mock_state):
    """A record from before the `labels` field (e.g. in-flight across a hot
    reload) still renders without KeyError, falling back to #sid."""
    state.UNDO_STACK = [{
        'target': 'CR', 'moves': {77: 'LR'}, 'ejections': {},
        'summary': 'Moved 1 -> CR', 'origin': ''
    }]
    # A legacy record (no 'extras') restores location only, but still routes the
    # write through spoolman_api.update_spool — mock it so no live call is made.
    with patch('logic.spoolman_api.update_spool', return_value={'id': 77}) as upd, \
         patch('logic.config_loader') as cfg:
        cfg.get_api_urls.return_value = ("http://spoolman", "http://fb")
        res = logic.perform_undo()

    assert res['success'] is True
    upd.assert_called_once_with(77, {"location": "LR"})   # location-only restore
    logged = [c.args[0] for c in state.add_log_entry.call_args_list if c.args]
    line = [m for m in logged if isinstance(m, str) and m.startswith("↩️ Undid:")][-1]
    assert "#77 from LR -> CR" in line


def test_undo_empty_moves_record_no_double_moved(mock_state):
    """A legacy/no-move record (empty moves + old 'Moved N -> X' summary) must NOT
    render the double word '↩️ Undid: moved Moved 1 -> CR'."""
    state.UNDO_STACK = [{
        'target': 'CR', 'moves': {}, 'ejections': {},
        'summary': 'Moved 1 -> CR', 'origin': ''
    }]
    with patch('logic.requests'), patch('logic.config_loader') as cfg:
        cfg.get_api_urls.return_value = ("http://spoolman", "http://fb")
        res = logic.perform_undo()

    assert res['success'] is True
    logged = [c.args[0] for c in state.add_log_entry.call_args_list if c.args]
    line = [m for m in logged if isinstance(m, str) and m.startswith("↩️ Undid:")][-1]
    assert line == "↩️ Undid: Moved 1 -> CR", f"unexpected legacy render: {line!r}"
    assert "moved Moved" not in line


def test_get_live_spools_data(mock_spoolman):
    """Test rapid Spoolman querying for Live Refresh."""
    # mock_spoolman fixture already sets:
    # get_spool.return_value = {'id': 123, ...}
    # format_spool_display.return_value = {'text': 'Test Spool', 'color': '#ff0000'}

    # Passing 123 triggers the mock, passing 404 tests graceful handling
    mock_spoolman.get_spool.side_effect = lambda sid: {'id': sid} if sid == 123 else None

    res = logic.get_live_spools_data([123, 404])

    # Assert successful fetch
    assert "123" in res
    assert res["123"]["display"] == "Test Spool"
    assert res["123"]["color"] == "#ff0000"

    # Assert missing ID is gracefully ignored
    assert "404" not in res
