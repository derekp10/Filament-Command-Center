"""In-app help (Group 55.3): every daily dialog has its help, and the words keep FCC's rules.

static/js/modules/help_texts.js holds the words: one
window.registerHelp({key, title, match, lines, scopes, sections}) per dialog, and the
dialog's ? button names its key (data-fcc-help="<key>"). The help is drawn in the
shortcut window by shortcuts_registry.js. This file checks, offline:

  1. every entry is well formed: a key, a title, plain lines, a `match` naming its dialog;
  2. each entry's dialog exists (a modal id in a template, an overlay id or an
     overlayHas selector's id or attribute in the page's own scripts, help_texts.js left
     out), and every scope it lists has keys registered under it, so a keys table can't
     come out empty unseen;
  3. every ? button names an entry and is a real button with a name, every entry has a
     ? button somewhere (a template, or a script that draws its header: those found only
     as text here, SCRIPT_DRAWN, are drawn for real by test_help_buttons_55_js.py), and
     every question an entry matches draws its ?;
  4. no words name the owner's own setup (CLAUDE.md, "no setup's own names": "It's
     useful for me, but including it in something others might use, just causes
     confusion."): none of his ids, printer names or emoji, and none of the ids in
     dev's data/locations.json when it is on this machine;
  5. no "|" in the words: tests/test_toolhead_types_one_list.py reads a string holding
     "|" and a head Type's words as a Type test.

It can't see whether a line is TRUE: that is a reading of the code (the Group 55
build checked every line against it), and a review's job when a dialog changes.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

# The shared node driver's module warns once when node is missing (a PytestWarning in
# the run's summary), and with FCC_REQUIRE_NODE=1 fails collection instead.
from test_core1_return_ejectall_js import NODE, RESULT_MARK

HUB = Path(__file__).resolve().parent.parent
REPO = HUB.parent
HELP_JS = HUB / "static" / "js" / "modules" / "help_texts.js"
JS_ROOT = HUB / "static" / "js"
TEMPLATES = HUB / "templates"

needs_node = pytest.mark.skipif(NODE is None, reason=(
    "node is not on PATH: the in-app help's word checks (test_help_texts_55.py) did NOT run. "
    "Install Node.js (see CLAUDE.md Testing), or set FCC_REQUIRE_NODE=1 to fail instead of skipping."))

# The owner's own setup, as it shows in his locations, printers and names. A word that
# matches one of these in help text, a README or a placeholder is his, never a made-up
# example (CLAUDE.md "no setup's own names"; made-up ones: SHELF-1, DRYBOX-1, PRINTER-1,
# HEAD-1). Case-sensitive, at word edges.
SETUP_NAME_PATTERNS = [
    r"\bXL(?:-\d+)?\b", r"\bCORE ?1\b", r"\bRCOI(?:-\d+)?\b", r"\bLR-MDB\b", r"\bPM-DB\b",
    r"\bCR-CT\b", r"\bCR-WLN\b", r"\bDR-CT\b", r"\bCore One\b", r"\bINDX\b", "\U0001F99D",
]

DRIVER_JS = r"""
const fs = require('fs');
const vm = require('vm');
const entries = [];
const win = { registerHelp: (e) => { entries.push(e); } };
const ctx = { window: win, console };
win.window = win;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx, { filename: 'help_texts.js' });
process.stdout.write('__RESULT_MARK__' + JSON.stringify(entries));
"""


def _dev_location_ids() -> list:
    """The LocationIDs in dev's data/locations.json (git-ignored, so only on the owner's
    machine), three characters or longer: the two-letter room ids are ordinary letters."""
    path = HUB / "data" / "locations.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    ids = {str(r.get("LocationID") or "").strip() for r in rows if isinstance(r, dict)}
    return sorted(i for i in ids if len(i) >= 3)


def setup_names_in(text: str) -> list:
    """Every piece of `text` that names the owner's own setup."""
    hits = []
    for pat in SETUP_NAME_PATTERNS:
        hits += re.findall(pat, text)
    for loc in _dev_location_ids():
        if re.search(r"(?<![\w-])" + re.escape(loc) + r"(?![\w-])", text):
            hits.append(loc)
    return hits


@pytest.fixture(scope="module")
def entries(tmp_path_factory) -> list:
    if NODE is None:
        pytest.skip("node is not on PATH")
    script = tmp_path_factory.mktemp("help") / "driver.js"
    script.write_text(DRIVER_JS.replace("__RESULT_MARK__", RESULT_MARK), encoding="utf-8")
    proc = subprocess.run([NODE, str(script), str(HELP_JS)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    out = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and out, (
        f"help_texts.js didn't run in node (rc={proc.returncode})\n{proc.stdout}\n{proc.stderr}")
    return json.loads(out[-1][len(RESULT_MARK):])


def _all_words(entry: dict) -> list:
    words = [entry.get("title") or ""] + list(entry.get("lines") or [])
    for sec in entry.get("sections") or []:
        words.append(sec.get("title") or "")
        words += list(sec.get("lines") or [])
    return words


def _page_text(exclude=()) -> str:
    """Every template and page script, as text (for ids and help buttons), less the
    scripts named in `exclude`."""
    parts = [p.read_text(encoding="utf-8") for p in sorted(TEMPLATES.rglob("*.html"))]
    parts += [p.read_text(encoding="utf-8") for p in sorted(JS_ROOT.rglob("*.js"))
              if not p.name.endswith(".min.js") and p.name not in exclude]
    return "\n".join(parts)


def _page_scripts() -> dict:
    """The page's own scripts by file name, help_texts.js left out."""
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(JS_ROOT.rglob("*.js"))
            if not p.name.endswith(".min.js") and p.name != HELP_JS.name}


def _overlay_ids(entry) -> list:
    m = entry.get("match") or {}
    return [m["overlay"]] if isinstance(m.get("overlay"), str) else list(m.get("overlay") or [])


def _dataset_name(attr: str):
    """data-fcc-picker-mode -> fccPickerMode: the attribute as a script sets it."""
    if not attr.startswith("data-"):
        return None
    head, *rest = attr[len("data-"):].split("-")
    return head + "".join(w[:1].upper() + w[1:] for w in rest)


def _registered_scopes() -> set:
    text = _page_text()
    return set(re.findall(r"scope:\s*['\"]([^'\"]+)['\"]", text))


# The dialogs Group 55.3 covers first (the task file's list), by help key.
FIRST_DIALOGS = {
    "location-list", "location-window", "spool-window", "filament-window", "wizard",
    "weigh-out", "quick-weigh", "move-question", "slot-picker", "printer-picker",
    "print-queue", "label-backlog",
    # The Quick-Swap question, its own since the Group 55 review (R1-4).
    "swap-question",
}


# ---------------------------------------------------------------------------
# 1. Well formed.
# ---------------------------------------------------------------------------

@needs_node
def test_every_entry_is_well_formed(entries):
    keys = [e.get("key") for e in entries]
    assert len(keys) == len(set(keys)), f"a help key is registered twice: {keys}"
    for e in entries:
        key = e.get("key")
        assert isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9-]*", key), f"bad key {key!r}"
        assert isinstance(e.get("title"), str) and e["title"].strip(), f"{key}: no title"
        lines = e.get("lines")
        assert isinstance(lines, list) and 2 <= len(lines) <= 8, (
            f"{key}: help is 2 to 8 plain lines (a few lines a person reads at a glance), "
            f"got {len(lines) if isinstance(lines, list) else lines!r}")
        for sec in e.get("sections") or []:
            assert isinstance(sec.get("title"), str) and sec["title"].strip(), f"{key}: a section has no title"
            assert isinstance(sec.get("lines"), list) and sec["lines"], f"{key}: a section has no lines"
            assert sec.get("when") is None or isinstance(sec["when"], str), f"{key}: a section's `when` is a selector"
        for line in _all_words(e):
            assert isinstance(line, str) and line == line.strip() and line, f"{key}: an empty or padded line"
            assert len(line) <= 260, f"{key}: a line over 260 characters reads as a wall: {line!r}"
            assert "<" not in line and ">" not in line, (
                f"{key}: help lines are plain text (they are escaped when drawn): {line!r}")
        match = e.get("match") or {}
        assert match.get("modal") or match.get("overlay") or match.get("overlayHas"), (
            f"{key}: `match` names no dialog (modal, overlay or overlayHas)")


@needs_node
def test_the_first_dialogs_all_have_help(entries):
    missing = FIRST_DIALOGS - {e["key"] for e in entries}
    assert not missing, f"Group 55.3's first dialogs without help: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 2. Each entry's dialog and scopes exist.
# ---------------------------------------------------------------------------

@needs_node
def test_each_entrys_dialog_exists(entries):
    """Every modal id, overlay id, and id or attribute in an `overlayHas` selector that an
    entry matches on is in the page's own templates and scripts. help_texts.js is left out:
    it names them all itself, so reading it too passed every rename and typo (Group 55
    review, R3-3), and the ? key then opened the full list over that dialog."""
    text = _page_text(exclude={HELP_JS.name})
    for e in entries:
        m = e.get("match") or {}
        if m.get("modal"):
            assert f'id="{m["modal"]}"' in text, f"{e['key']}: no element with id {m['modal']!r} in the templates"
        for oid in _overlay_ids(e):
            # Mounted with that id: mountOverlay's `id`, a question's `ids.overlay`, or
            # confirmActivePrint's own default. A name alone isn't enough: the Quick-Swap
            # question's ? names its id too, so a renamed mount still passed.
            mounted = re.search(r"\b(?:id|overlay):\s*'" + re.escape(oid) + "'", text) or f"|| '{oid}'" in text
            assert mounted, (f"{e['key']}: no script mounts an overlay with the id {oid!r} "
                             f"(mountOverlay's id, or a question's ids.overlay)")
        for sel in ([m["overlayHas"]] if m.get("overlayHas") else []):
            for eid in re.findall(r"#([A-Za-z][\w-]*)", sel):
                assert f'id="{eid}"' in text or f"'{eid}'" in text or f'"{eid}"' in text, (
                    f"{e['key']}: no template or script draws the id #{eid} its overlayHas looks for")
            for attr in re.findall(r"\[([A-Za-z][\w-]*)", sel):
                camel = _dataset_name(attr)
                assert attr in text or (camel and f".{camel}" in text), (
                    f"{e['key']}: no template or script sets the attribute {attr} its overlayHas looks for")


@needs_node
def test_every_question_an_entry_matches_draws_its_help_button(entries):
    """Group 55 review, R4-3: the ? key gave help over the Quick-Swap question and "Record it
    as coming from…", which drew no ?, so a person with no keyboard couldn't reach it. Every
    overlay an entry's `match` lists is drawn with its ?: by confirmActivePrint (its own
    overlay, or one a caller names in `ids.overlay`: its `help` defaults to that overlay's)
    or with window.fccCornerHelpHtml('<id>'). The browser tests see each one drawn."""
    js = _page_scripts()
    assert "ids.overlay || 'fcc-active-print-confirm-overlay'" in js["inv_core.js"]
    assert "window.fccHelpKeyForOverlayId(overlayId)" in js["inv_core.js"]
    for e in entries:
        for oid in _overlay_ids(e):
            if oid == "fcc-active-print-confirm-overlay":       # confirmActivePrint's own
                continue
            drawn = [name for name, src in js.items()
                     if f"fccCornerHelpHtml('{oid}')" in src
                     or re.search(r"\boverlay:\s*'" + re.escape(oid) + "'", src)]
            assert drawn, (
                f"{e['key']}: the overlay {oid!r} draws no ? (pass it to confirmActivePrint as "
                f"ids.overlay, or put window.fccCornerHelpHtml('{oid}') in its top right corner)")


@needs_node
def test_every_scope_it_lists_has_keys(entries):
    scopes = _registered_scopes()
    for e in entries:
        listed = list(e.get("scopes") or [])
        for sec in e.get("sections") or []:
            listed += list(sec.get("scopes") or [])
        unknown = [s for s in listed if s not in scopes]
        assert not unknown, (
            f"{e['key']}: no shortcut is registered under {unknown}, so its keys table would be "
            f"empty. Registered scopes: {sorted(scopes)}")


# ---------------------------------------------------------------------------
# 3. ? buttons and entries match.
# ---------------------------------------------------------------------------

_HELP_BTN = re.compile(r"data-fcc-help=(?:\\?[\"'])([a-z0-9-]+)")

# The ? buttons a script draws with its key in a variable, so no data-fcc-help="<key>"
# names them: each key, the module, and the text there that names or picks it. The
# browser tests (test_in_app_help_55_e2e.py) and test_help_buttons_55_js.py prove each
# one is drawn; this keeps the list honest when that code moves.
SCRIPT_DRAWN = {
    "quick-weigh": ("inv_weigh_out.js", "helpKey: 'quick-weigh'"),
    "slot-picker": ("slot_picker.js", "'printer-picker' : 'slot-picker'"),
    "printer-picker": ("slot_picker.js", "'printer-picker' : 'slot-picker'"),
    # confirmActivePrint's ? asks the registry for its overlay's help: the move doors'
    # overlays are the move question's (test_help_buttons_55_js.py).
    "move-question": ("inv_core.js", "window.fccHelpKeyForOverlayId(overlayId)"),
    # The Quick-Swap question's ? is its overlay's help, through window.fccCornerHelpHtml.
    "swap-question": ("inv_quickswap.js", "fccCornerHelpHtml('fcc-quickswap-confirm-overlay')"),
}


@needs_node
def test_every_help_button_names_an_entry_and_every_entry_has_one(entries):
    text = _page_text()
    named = set(_HELP_BTN.findall(text))
    for key, (module, words) in SCRIPT_DRAWN.items():
        src = (JS_ROOT / "modules" / module).read_text(encoding="utf-8")
        assert words in src, f"{key}: {module} no longer holds {words!r}: update SCRIPT_DRAWN"
        named.add(key)
    keys = {e["key"] for e in entries}
    assert named, "no ? button (data-fcc-help) on the page"
    assert not (named - keys), f"? buttons naming no help entry: {sorted(named - keys)}"
    assert not (keys - named), f"help entries with no ? button anywhere: {sorted(keys - named)}"


def _help_button_tags():
    """Every tag with a data-fcc-help="…" in a template, and every <button …> with one in
    a script (a template literal), as (where, tag)."""
    for path in sorted(TEMPLATES.rglob("*.html")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<[^>]*data-fcc-help=\"[^\"]+\"[^>]*>", src, re.S):
            yield path.name, m.group(0)
    for path in sorted(JS_ROOT.rglob("*.js")):
        if path.name.endswith(".min.js"):
            continue
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<button\b[^>]*data-fcc-help=\"[^\"]+\"[^>]*>", src, re.S):
            yield path.name, m.group(0)


def test_every_help_button_is_a_named_button():
    tags = list(_help_button_tags())
    assert {where for where, _ in tags} >= {"modals_loc_mgr.html", "modals_details.html", "weight_entry.js",
                                           "slot_picker.js", "inv_core.js"}, sorted({w for w, _ in tags})
    for where, tag in tags:
        at = f"{where}: {tag[:120]}"
        assert tag.startswith("<button"), f"a ? that isn't a <button>: {at}"
        assert 'type="button"' in tag, f"a ? button without type=\"button\": {at}"
        assert "fcc-help-btn" in tag, f"a ? button without its look (.fcc-help-btn): {at}"
        assert "aria-label=" in tag, f"a ? button without a name for a screen reader: {at}"


# ---------------------------------------------------------------------------
# 4. and 5. The words.
# ---------------------------------------------------------------------------

@needs_node
def test_no_help_words_name_the_owners_setup(entries):
    for e in entries:
        for line in _all_words(e):
            hits = setup_names_in(line)
            assert not hits, (
                f"{e['key']}: {hits} in {line!r}. Help uses made-up examples (SHELF-1, DRYBOX-1, "
                f"PRINTER-1, HEAD-1, #42), never the owner's own ids or names (CLAUDE.md).")


@needs_node
def test_no_pipe_in_the_help_words(entries):
    for e in entries:
        for line in _all_words(e):
            assert "|" not in line, f"{e['key']}: a '|' in {line!r} (the toolhead-Type canary's rule)"


# ---------------------------------------------------------------------------
# 6. No scan codes. A help names the button, or the QR a person sees beside it, never the
#    text a QR carries (Derek, 2026-11-11, of "CMD:EJECTALL asks…" in the location
#    window's help: "out of left field for someone not familiar with how QR code commands
#    work in the back end"). The key rows a help lists under its words are held to the same
#    rule. The full shortcut list's "Scan Commands" section is the codes' own reference,
#    which no help lists.
# ---------------------------------------------------------------------------

SCAN_CODE = re.compile(r"\b(?:CMD|LOC|SPL|ID|LEG):\S+")


def scan_codes_in(text: str) -> list:
    """Every scan code written out in `text` ("CMD:EJECTALL", "LOC:SHELF-1")."""
    return SCAN_CODE.findall(text)


def _shortcut_blocks():
    """Every registerShortcut({...}) in the page's scripts, as (file, scope, the call's
    whole text): its keys and its description, however the description is built."""
    for name, src in _page_scripts().items():
        for m in re.finditer(r"registerShortcut\(\s*\{", src):
            start = m.end() - 1
            depth, j, quote = 0, start, None
            while j < len(src):
                c = src[j]
                if quote:
                    if c == "\\":
                        j += 2
                        continue
                    if c == quote:
                        quote = None
                elif c in "'\"`":
                    quote = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            block = src[start:j + 1]
            scope = re.search(r"scope:\s*['\"]([^'\"]+)['\"]", block)
            yield name, scope.group(1) if scope else "", block


def _listed_scopes(entries) -> set:
    listed = set()
    for e in entries:
        listed.update(e.get("scopes") or [])
        for sec in e.get("sections") or []:
            listed.update(sec.get("scopes") or [])
    return listed


@needs_node
def test_no_help_names_a_scan_code(entries):
    for e in entries:
        for line in _all_words(e):
            codes = scan_codes_in(line)
            assert not codes, (
                f"{e['key']}: {codes} in {line!r}. Name the button, or the QR beside it, not the "
                f"text the QR carries (Derek, 2026-11-11).")
    listed = _listed_scopes(entries)
    seen = set()
    for name, scope, block in _shortcut_blocks():
        if scope not in listed:
            continue
        seen.add(scope)
        codes = scan_codes_in(block)
        assert not codes, (
            f"{name}: the {scope!r} key row {block[:140]!r} names {codes}, and a help lists that "
            f"scope's keys under its words. Name the button or the QR beside it instead.")
    assert seen == listed, f"no key rows found for {sorted(listed - seen)}: the check read nothing there"


@pytest.mark.parametrize("text, codes", [
    ("CMD:EJECTALL asks, then takes out every spool here", ["CMD:EJECTALL"]),
    ("a slot's code (CMD:SLOT:2) does what clicking it does", ["CMD:SLOT:2)"]),
    ("this place's label (LOC:SHELF-1) puts your buffer here", ["LOC:SHELF-1)"]),
    ("the 📷 CANCEL QR beside Cancel cancels", []),
    ("Filament ID: 5, PAID:5", []),
])
def test_the_scan_code_check_catches_what_it_should(text, codes):
    assert scan_codes_in(text) == codes


@pytest.mark.parametrize("text, names", [
    ("Scan XL-3's label", ["XL-3"]),
    ("the 🦝 Core One INDX", ["Core One", "INDX", "\U0001F99D"]),
    ("put it in LR-MDB-1 slot 2", ["LR-MDB"]),
    ("put it in DRYBOX-1 slot 2", []),
    ("XLarge text", []),
])
def test_the_setup_name_check_catches_what_it_should(text, names):
    hits = setup_names_in(text)
    for n in names:
        assert n in hits, f"{n!r} not caught in {text!r}"
    if not names:
        assert hits == [], f"a made-up example read as the owner's: {hits} in {text!r}"
