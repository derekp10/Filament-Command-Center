import pytest
import sys
import os

# Add the inventory-hub directory to the Python path so we can import state
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))
import state

@pytest.fixture
def clean_logs():
    """Fixture to ensure a clean state.RECENT_LOGS before and after each test."""
    state.RECENT_LOGS.clear()
    yield
    state.RECENT_LOGS.clear()

def test_add_log_entry_no_color(clean_logs):
    """Test Case 1: No color provided should just return the message without a swatch."""
    state.add_log_entry("Test Message")
    
    assert len(state.RECENT_LOGS) == 1
    recent_msg = state.RECENT_LOGS[0]['msg']
    assert "Test Message" == recent_msg
    assert "background-color" not in recent_msg
    assert "conic-gradient" not in recent_msg

def test_add_log_entry_single_color(clean_logs):
    """Test Case 2: Single hex color should generate standard background-color css."""
    state.add_log_entry("Single Color Spool", color_hex="FF0000")
    
    assert len(state.RECENT_LOGS) == 1
    recent_msg = state.RECENT_LOGS[0]['msg']
    
    # Assert background-color is used and conic-gradient isn't
    assert "background-color:#FF0000;" in recent_msg
    assert "conic-gradient" not in recent_msg
    assert "Single Color Spool" in recent_msg

def test_add_log_entry_multi_color_two(clean_logs):
    """Test Case 3: Two comma-separated colors should generate a 50/50 conic gradient."""
    state.add_log_entry("Dual Color Spool", color_hex="FF0000,00FF00")
    
    assert len(state.RECENT_LOGS) == 1
    recent_msg = state.RECENT_LOGS[0]['msg']
    
    # Assert background: conic-gradient(...) is used
    assert "background: conic-gradient(" in recent_msg
    
    # Check mathematically proportional splits (0% 50%, 50% 100%)
    assert "#FF0000 0% 50.0%" in recent_msg
    assert "#00FF00 50.0% 100.0%" in recent_msg
    assert "background-color:" not in recent_msg

def test_add_log_entry_multi_color_three(clean_logs):
    """Test Case 4: Three comma-separated colors should mathematically split into 33.3% wedges."""
    state.add_log_entry("Tri Color Spool", color_hex="FF0000,00FF00,0000FF")
    
    assert len(state.RECENT_LOGS) == 1
    recent_msg = state.RECENT_LOGS[0]['msg']
    
    assert "background: conic-gradient(" in recent_msg
    
    # Check computationally generated thirds
    assert "#FF0000 0% 33.33" in recent_msg
    assert "#00FF00 33.33" in recent_msg
    assert "#0000FF 66.67" in recent_msg

def test_add_log_entry_malformed_color(clean_logs):
    """Test Case 5: Malformed colors (e.g., empty strings between commas) should be handled gracefully."""
    # Extra commas shouldn't crash it, and it should filter empty strings if possible
    # or at least not throw an error and fall back to something safe.
    state.add_log_entry("Malformed Color String", color_hex="FF0000,,00FF00,")
    
    assert len(state.RECENT_LOGS) == 1
    recent_msg = state.RECENT_LOGS[0]['msg']
    
    # Assuming the implementation gracefully splits and filters empty values
    assert "background: conic-gradient(" in recent_msg
    assert "#FF0000" in recent_msg
    assert "#00FF00" in recent_msg
