"""The README (Group 55.1) and the docs it retired (55.2): links that lead somewhere, and
words for anyone.

  1. every relative link and picture in README.md, and in the two retired docs that now
     point to it, names a file that is in the repo;
  2. the README names none of the owner's own setup (CLAUDE.md, "no setup's own names":
     made-up examples only; the same check as the in-app help's);
  3. the leftover "Inventory Hub" text is gone from the config examples, while the names
     the rename leaves alone (the logger, the folder, the container) stay.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_help_texts_55 import setup_names_in

HUB = Path(__file__).resolve().parent.parent
REPO = HUB.parent
README = REPO / "README.md"
RETIRED = [REPO / "docs" / "Filament-Command-Center (FCC)" / "INVENTORY_SYSTEM_MANUAL.md",
           REPO / "docs" / "Filament-Command-Center (FCC)" / "SCANNER_STYLE_GUIDE.md"]

_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _relative_links(path: Path) -> list:
    out = []
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            continue   # a web address or an anchor in the same page
        out.append(target.split("#", 1)[0])
    return out


@pytest.mark.parametrize("doc", [README] + RETIRED, ids=lambda p: p.name)
def test_every_relative_link_leads_to_a_file_in_the_repo(doc):
    assert doc.exists(), f"{doc} is missing"
    links = _relative_links(doc)
    assert links, f"{doc.name} links to nothing"
    for target in links:
        resolved = (doc.parent / target).resolve()
        assert resolved.exists(), f"{doc.name}: {target!r} leads nowhere ({resolved})"
        assert REPO in resolved.parents or resolved == REPO, f"{doc.name}: {target!r} leaves the repo"


def test_the_readmes_pictures_are_there_and_dated():
    text = README.read_text(encoding="utf-8")
    pictures = [t for t in _relative_links(README) if t.lower().endswith(".png")]
    assert 4 <= len(pictures) <= 6, f"the README shows 4 to 6 pictures, it shows {len(pictures)}"
    assert re.search(r"taken \d{4}-\d{2}-\d{2}", text), "the README's pictures carry the day they were taken"


def test_the_readme_names_none_of_the_owners_setup():
    hits = setup_names_in(README.read_text(encoding="utf-8"))
    assert not hits, (f"the README names the owner's own setup: {sorted(set(hits))}. Use made-up "
                      "examples (SHELF-1, DRYBOX-1, PRINTER-1), never his ids or names (CLAUDE.md).")


def test_no_lan_address_in_the_readme():
    text = README.read_text(encoding="utf-8")
    assert not re.search(r"\b(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text), "a LAN address in the README"
    assert "/mnt/" not in text, "a TrueNAS path in the README"


def test_the_leftover_inventory_hub_text_is_gone_from_the_config_examples():
    for path in (REPO / "config.json.example", HUB / ".env.example"):
        assert "INVENTORY HUB" not in path.read_text(encoding="utf-8").upper(), path


def test_the_names_the_rename_leaves_alone_stay():
    """The full rename stays on the buglist (Derek, 2026-10-19): the logger name, which
    tests pin, the compose service and the container keep theirs."""
    assert 'getLogger("InventoryHub")' in (HUB / "state.py").read_text(encoding="utf-8") \
        or "getLogger('InventoryHub')" in (HUB / "state.py").read_text(encoding="utf-8")
    compose = (HUB / "docker-compose.yml").read_text(encoding="utf-8")
    assert "container_name: inventory_hub" in compose and "inventory-hub:" in compose
