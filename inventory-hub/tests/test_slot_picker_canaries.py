"""Group 40.1 — offline source canaries for the shared slot picker.

The picker's behaviour is pinned in a browser (test_slot_picker_e2e.py, full
sweep only); these pin the wiring that must hold for it to work at all, and
run under --offline:
  - no text input in the picker (a focused input disarms the hardware scanner);
  - it mounts through window.mountOverlay (CLAUDE.md: never a hand-rolled overlay);
  - processScan hands every scan to routePickerScan right after routeConfirmScan,
    before any CMD: route can act behind an open picker;
  - the template loads slot_picker.js after inv_cmd.js and before
    shortcuts_registry.js, and the picker registers its keys;
  - the ⭐ and the engine's auto-slot call the same three helpers, so the slot
    the picker stars is the slot a slotless move takes (no re-inlined copy).

HEAD proof: slot_picker.js, placement.py and the helpers don't exist on HEAD;
every test here fails there.
"""
import re
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _code_only(src):
    """JS source without its comments (they may name what the code avoids)."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("//"))


def test_the_picker_has_no_text_input_and_mounts_through_mount_overlay():
    src = _read(MODULES / "slot_picker.js")
    code = _code_only(src)
    assert not re.search(r"<\s*(input|textarea)\b", code, re.I), "a text input disarms the scanner"
    assert not re.search(r"createElement\(\s*['\"](input|textarea)", code, re.I)
    assert "window.mountOverlay(" in src
    for name in ("window.openSlotPicker", "window.routePickerScan", "window.isSlotPickerOpen"):
        assert f"{name} =" in src, name


def test_process_scan_routes_to_the_picker_before_any_command():
    src = _read(MODULES / "inv_cmd.js")
    start = src.index("const processScan = ")
    body = src[start:start + 6000]
    confirm = body.index("window.routeConfirmScan(text)")
    picker = body.index("window.routePickerScan(text)")
    first_cmd = body.index("if (upper === 'CMD:AUDIT')")
    stale_guard = body.index("/CMD:(CONFIRM|STORE):\\S+$/.test(upper)")     # at the end: Group 57 review, round 5
    assert confirm < picker < stale_guard < first_cmd


def test_the_template_loads_the_picker_between_inv_cmd_and_the_shortcut_registry():
    html = _read(HUB / "templates" / "components" / "scripts.html")
    cmd = html.index("js/modules/inv_cmd.js")
    picker = html.index("js/modules/slot_picker.js")
    registry = html.index("js/modules/shortcuts_registry.js")
    assert cmd < picker < registry


def test_the_picker_registers_its_keys_after_load():
    src = _read(MODULES / "slot_picker.js")
    ids = re.findall(r"registerShortcut\(\{\s*id:\s*'([^']+)'", src)
    assert set(ids) >= {"slot-picker-move", "slot-picker-jump", "slot-picker-pick", "slot-picker-cancel"}
    assert "DOMContentLoaded" in src


def test_the_star_and_the_engines_auto_slot_share_one_rule():
    placement_src = _read(HUB / "placement.py")
    for helper in ("logic.recommend_box_slot(", "logic.box_slot_claims(", "logic.slot_would_prompt("):
        assert helper in placement_src, helper
    logic_src = _read(HUB / "logic.py")
    impl = logic_src[logic_src.index("def _perform_smart_move_impl("):]
    impl = impl[:impl.index("\ndef ", 10)]
    assert "box_slot_claims(" in impl and "slot_would_prompt(" in impl and "recommend_box_slot(" in impl
    # Nobody re-inlined the claims loop into the engine.
    assert "claims.setdefault(" not in impl
