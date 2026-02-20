import pytest # type: ignore
import os
import json
import tempfile
import csv

# We need to test locations_db, but it imports 'state' which sets up logging.
# Let's mock state.logger to prevent it from cluttering test output or failing if run without full context.
import sys
import logging
class DummyState:
    class DummyLogger:
        def info(self, msg): pass
        def error(self, msg): pass
        def warning(self, msg): pass
    logger = DummyLogger()

sys.modules['state'] = DummyState() # type: ignore

# Add the inventory-hub directory to the Python path so we can import locations_db
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))

# Now we can safely import the module under test
import locations_db # type: ignore

@pytest.fixture
def temp_workspace():
    """Provides a temporary directory for isolated DB testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override the file paths in locations_db to use our temp dir
        original_csv = locations_db.CSV_FILE
        original_json = getattr(locations_db, 'JSON_FILE', 'locations.json')
        
        locations_db.CSV_FILE = os.path.join(tmpdir, "3D Print Supplies - Locations.csv")
        locations_db.JSON_FILE = os.path.join(tmpdir, "locations.json")
        
        yield tmpdir
        
        # Restore originals
        locations_db.CSV_FILE = original_csv
        locations_db.JSON_FILE = original_json

def test_fresh_install_empty_list(temp_workspace):
    """Test Case 1: If no JSON and no CSV exist, return empty list."""
    assert not os.path.exists(locations_db.JSON_FILE)
    assert not os.path.exists(locations_db.CSV_FILE)
    
    locations = locations_db.load_locations_list()
    assert locations == []
    
    # It shouldn't have created any files just by loading
    assert not os.path.exists(locations_db.JSON_FILE)

def test_csv_to_json_migration(temp_workspace):
    """Test Case 2: If CSV exists but JSON doesn't, it should migrate the data."""
    # 1. Create a dummy CSV
    csv_data = [
        {"LocationID": "LID-1", "Name": "Test Shelf", "Type": "Cart", "Max Spools": "10"},
        {"LocationID": "LID-2", "Name": "Dryer", "Type": "Dryer Box", "Max Spools": "4"}
    ]
    with open(locations_db.CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
        writer.writeheader()
        writer.writerows(csv_data)
        
    assert os.path.exists(locations_db.CSV_FILE)
    assert not os.path.exists(locations_db.JSON_FILE)
    
    # 2. Trigger migration
    locations = locations_db.load_locations_list()
    
    # 3. Assertions
    assert len(locations) == 2
    assert locations[0]['LocationID'] == "LID-1"
    
    # Ensure JSON was created
    assert os.path.exists(locations_db.JSON_FILE)
    
    # Ensure CSV was backed up
    backup_path = locations_db.CSV_FILE.replace(".csv", "_BACKUP.csv")
    assert os.path.exists(backup_path)
    assert not os.path.exists(locations_db.CSV_FILE)
    
    # Verify JSON content
    with open(locations_db.JSON_FILE, 'r') as f:
        json_content = json.load(f)
        assert len(json_content) == 2
        assert json_content[1]['Name'] == "Dryer"

def test_standard_read_write(temp_workspace):
    """Test Case 3: Writing to JSON and reading it back works perfectly."""
    test_data = [
        {"LocationID": "LID-99", "Name": "Storage", "Type": "Shelf"}
    ]
    
    # Save it
    locations_db.save_locations_list(test_data)
    
    # Ensure it created the JSON file
    assert os.path.exists(locations_db.JSON_FILE)
    assert not os.path.exists(locations_db.CSV_FILE)
    
    # Load it
    loaded_data = locations_db.load_locations_list()
    
    assert len(loaded_data) == 1
    assert loaded_data[0]['LocationID'] == "LID-99"
    assert loaded_data[0]['Name'] == "Storage"
