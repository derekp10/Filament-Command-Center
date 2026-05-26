"""Meta-test: forbid direct PATCH to Spoolman with `extra` in production code.

Background (2026-05-20 incident):
  Three call sites (sweep_unused, remove_choice, ensure_filament_attributes_cleaned)
  were sending `requests.patch(.../api/v1/filament/<id>, json={"extra": {...}})`
  with only a subset of the `extra` dict. Spoolman's PATCH on `extra`
  REPLACES the whole sub-document — so every "restored" filament lost
  every sibling extra (product_url, nozzle_temp_max, original_color, ...).

The fix in those sites is to either:
  (a) route through `spoolman_api.update_filament`/`update_spool`/`update_vendor`
      which fetch+merge existing extras first, OR
  (b) snapshot the FULL extras dict and pass it back whole.

This test enforces (a)-by-default: production code outside the helper
module must not PATCH Spoolman with `extra` directly. Tests and the
helpers themselves are allowed.

If you have a genuine reason to bypass the helpers (none come to mind),
explicitly mark the call with `# noqa: spoolman-extra-patch` and the
test will accept it. That makes the bypass auditable in code review
instead of invisible.
"""
from __future__ import annotations

import re
from pathlib import Path

INV_HUB = Path(__file__).resolve().parent.parent
ALLOWED_FILES = {
    # The helpers themselves own the merge logic — by definition they
    # PATCH directly with `extra`. Internal to spoolman_api only.
    "spoolman_api.py",
}
SCAN_GLOBS = ["*.py", "static/js/**/*.js", "templates/**/*.html"]

# Match `requests.patch(...)` or `_req.patch(...)` invocations whose
# json payload literal contains `extra`. We anchor on the patch call
# and look forward through the next ~6 lines for the `extra` token.
PATCH_CALL = re.compile(r"\b(?:requests|_req)\.patch\s*\(", re.MULTILINE)


def _violations_in_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    hits = []
    for m in PATCH_CALL.finditer(text):
        start_idx = text[: m.start()].count("\n")
        # Inspect the call block — up to 6 lines forward, which covers
        # every existing call shape in the repo.
        block = "\n".join(lines[start_idx : start_idx + 6])
        if "/api/v1/filament" not in block and "/api/v1/spool" not in block and "/api/v1/vendor" not in block:
            continue
        if "noqa: spoolman-extra-patch" in block:
            continue  # auditable opt-out
        if '"extra"' in block or "'extra'" in block:
            hits.append((start_idx + 1, lines[start_idx].strip()[:120]))
    return hits


def test_no_direct_extra_patch_in_production_code():
    offenders = []
    for py in INV_HUB.glob("*.py"):
        if py.name in ALLOWED_FILES or py.name.startswith("test_"):
            continue
        for lineno, snippet in _violations_in_file(py):
            offenders.append(f"  {py.name}:{lineno}  {snippet}")
    assert not offenders, (
        "Direct PATCH on Spoolman with `extra` payload found outside the "
        "merge-safe helpers. Spoolman's PATCH replaces the whole `extra` "
        "sub-document, so partial payloads silently wipe siblings — this "
        "is the 2026-05-19 wipe class of bug.\n"
        "  Either route through `spoolman_api.update_filament` / "
        "`update_spool` / `update_vendor` (which merge), OR snapshot the "
        "FULL extras dict and pass it back whole, OR mark the line "
        "`# noqa: spoolman-extra-patch` with a comment justifying the "
        "bypass.\n\nViolations:\n" + "\n".join(offenders)
    )
