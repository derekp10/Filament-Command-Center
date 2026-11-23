"""Group 65.2 (b): a scan of every print file FCC reads for slicer tags FCC doesn't
know, and for tag words written without their ';'.

Derek, 2026-11-03: "Is there any way to have FCC find and flag any bgcode that uses
something new ... I'd like to try to prevent changes in how the systems perform from
sneaking up on us like this in the future."

Why a tag matters. PrusaSlicer reads a comment as a tag only right after its ';' (its
GCodeProcessor's process_tags, a prefix match), and a few tags change its filament
count: ;EXCLUDE_E_START / ;EXCLUDE_E_END keep the moves between them out of it, and
;FLUSH_START / ;FLUSH_END count a flush's push in full. FCC's walk
(prusalink_api._walk_extrusion) reads exactly those. A tag FCC doesn't know may be one
the slicer counts by and FCC doesn't. A tag word with no ';' is no tag to either: the
old INDX profile (2026-10-01 to 10-20) wrote EXCLUDE_E_START and EXCLUDE_E_END as bare
lines, so the slicer counted the moves its tool-change meant to leave out. This scan
would have flagged that on the INDX's first print (job 1095, 2026-09-30), a month before
job 1134 surfaced it.

It only logs, one WARNING per printer and word per FCC run, kept in memory (step 2, the
per-printer fingerprint, will keep it in a store). print_deduct._compute_cancel_usage
calls it right after a file's text arrives, before the walk's own warnings, so a cause
comes first, for every file FCC reads (cancelled, finished, ambiguous, queued). It never
raises. The file name and the words come from the file, so both are escaped
(html.escape; this module can't import print_deduct._esc without a cycle).

Not seen (heuristics): a lower-case or spaced tag, and a tag in a file FCC never
downloads. Measured by the 2026-11-03 scoping: 0.4-0.5 s on a 27-32 MB body, on the
download's own thread.
"""
import html
import re
import threading

import state  # type: ignore

# The tags FCC knows, each with what it does to the filament count. A tag joins this
# list only with a test of what the walk does with it (tests/test_print_file_watch_65.py
# fails on a tag it has no walk case for): copying the slicer's list wholesale would
# have marked EXCLUDE_E known while the walk still counted it.
KNOWN_TAGS = {
    # PrusaSlicer 2.9.6 / 2.9.7 GCodeProcessor Reserved_Tags: none changes the count.
    "TYPE": "a move's type (perimeter, infill ...): no part of the count",
    "WIPE_START": "a wipe begins: it sets the move type only",
    "WIPE_END": "a wipe ends: it sets the move type only",
    "HEIGHT": "a layer height: no part of the count",
    "WIDTH": "an extrusion width: no part of the count",
    "LAYER_CHANGE": "a new layer: no part of the count",
    "COLOR_CHANGE": "a colour change; the M600 is a move of its own, the tag no part of the count",
    "PAUSE_PRINT": "a pause; the tag is no part of the count",
    "CUSTOM_GCODE": "custom G-code follows; the tag is no part of the count",
    "_GP_FIRST_LINE_M73_PLACEHOLDER": "the slicer's print-time placeholder",
    "_GP_LAST_LINE_M73_PLACEHOLDER": "the slicer's print-time placeholder",
    "_GP_ESTIMATED_PRINTING_TIME_PLACEHOLDER": "the slicer's print-time placeholder",
    # PrusaSlicer 2.9.6's Custom_Tags (not in 2.9.5): both pairs change the count, and
    # the walk reads them as the slicer does (prusalink_api._FLUSH_TAG_RE and
    # _EXCLUDE_E_TAG_RE).
    "FLUSH_START": "a flush begins: its push counts in full, a pull-back owes nothing",
    "FLUSH_END": "a flush ends",
    "EXCLUDE_E_START": "the moves after it are no filament used, until EXCLUDE_E_END",
    "EXCLUDE_E_END": "ends EXCLUDE_E_START's stretch",
    # Markers Derek's printer profiles write: no part of the slicer's count.
    "BEFORE_LAYER_CHANGE": "a profile's marker before a layer change",
    "AFTER_LAYER_CHANGE": "a profile's marker after a layer change",
    "Z": "a profile's layer-height marker (;Z:0.2)",
    "_TOOLCHANGE_TIME": "a profile's marker at the first tool select (;_TOOLCHANGE_TIME12.5)",
    "_TOOLCHANGE_END": "a profile's marker at the first tool select",
}

# A tag's shape: ';' at the line's start (after any blanks), then capitals or
# underscores right after it (digits inside a name too, between capitals or
# underscores: ;_GP_FIRST_LINE_M73_PLACEHOLDER), optional digits at its end (a decimal
# too: ;_TOOLCHANGE_TIME12.5), then the line's end, ':' or a blank. A name of one
# character counts only right before ':' (;Z:0.2), so ;G29 and ;M73 are no tags. It
# skips the comments people write (";G29 P1 ...", ";PET-family ...",
# "; RETRACT AFTER TOOLCHANGE START").
_TAG_RE = re.compile(r'^[ \t]*;([A-Z_]+(?:\d+[A-Z_]+)*)(\d+(?:\.\d+)?)?(?=[:\s]|$)', re.M)
# A tag word alone on a line with no ';': capitals and digits joined by underscores
# (EXCLUDE_E_START), blanks around it at most. A G-code line (G1 X10, M83, T0) has no
# underscore or has words after it.
_BARE_RE = re.compile(r'^[ \t]*(_?[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[ \t]*\r?$', re.M)

_EXCLUDE_E_WORDS = ("EXCLUDE_E_START", "EXCLUDE_E_END")

# (printer, kind, word) already said in this FCC run.
_SAID = set()
_SAID_LOCK = threading.Lock()


def _esc(text):
    return html.escape(str(text), quote=False)


def _and_list(items):
    items = [str(i) for i in items]
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def find_tags(content):
    """{"unknown": [names], "bare": [words]} in the order each first appears: the
    tag-shaped comments whose name FCC doesn't know, and the tag words alone on a line
    with no ';'. Pure: logs nothing."""
    unknown, bare = {}, {}
    if not content:
        return {"unknown": [], "bare": []}
    for m in _TAG_RE.finditer(content):
        name = m.group(1)
        if len(name) == 1 and (m.group(2) or content[m.end(1):m.end(1) + 1] != ":"):
            continue
        if name not in KNOWN_TAGS:
            unknown.setdefault(name, None)
    for m in _BARE_RE.finditer(content):
        bare.setdefault(m.group(1), None)
    return {"unknown": list(unknown), "bare": list(bare)}


def _new_words(printer_name, kind, words):
    with _SAID_LOCK:
        fresh = [w for w in words if (printer_name, kind, w) not in _SAID]
        _SAID.update((printer_name, kind, w) for w in fresh)
    return fresh


def _say_bare(printer_name, filename, words):
    named = _and_list(words)
    one = len(words) == 1
    if all(w in _EXCLUDE_E_WORDS for w in words):
        line = (f"⚠️ {_esc(printer_name)}: '{_esc(filename)}' has {_esc(named)} on "
                f"{'a line of its own' if one else 'lines of their own'}, without the ';' that makes "
                f"{'it a slicer tag' if one else 'them slicer tags'}, so the slicer counts the moves "
                f"{'after it' if one else 'between them'} as filament used (and so does FCC). Check the "
                f"printer profile's tool-change G-code.")
    else:
        line = (f"⚠️ {_esc(printer_name)}: '{_esc(filename)}' has {_esc(named)} on "
                f"{'a line of its own' if one else 'lines of their own'}, without the ';' that would make "
                f"{'it a slicer tag' if one else 'them slicer tags'}, so neither the slicer nor FCC reads "
                f"{'it as one' if one else 'them as tags'}. Check the printer profile's G-code.")
        if any(w in _EXCLUDE_E_WORDS for w in words):
            line += (" With EXCLUDE_E_START and EXCLUDE_E_END bare, the moves between them count as "
                     "filament used, in the slicer's count and FCC's.")
    state.add_log_entry(line, "WARNING", "ffaa00")


def _say_unknown(printer_name, filename, names):
    tags = ", ".join(";" + n for n in names)
    state.add_log_entry(
        f"⚠️ {_esc(printer_name)}: '{_esc(filename)}' uses "
        f"{'a slicer tag' if len(names) == 1 else 'slicer tags'} FCC doesn't know: {_esc(tags)}. "
        f"FCC may count this printer's filament differently from the slicer.", "WARNING", "ffaa00")


def scan_tags(printer_name, filename, content):
    """Scan a print file's text and log what's new for this printer: one WARNING for
    tag words with no ';', one for tags FCC doesn't know, each naming only the words
    not said for this printer in this FCC run. Returns find_tags's answer (every word
    found, said or not), or None when the scan failed. Never raises."""
    try:
        found = find_tags(content)
        bare = _new_words(printer_name, "bare", found["bare"])
        if bare:
            _say_bare(printer_name, filename, bare)
        unknown = _new_words(printer_name, "unknown", found["unknown"])
        if unknown:
            _say_unknown(printer_name, filename, unknown)
        return found
    except Exception as e:
        try:
            state.logger.warning(f"65.2: the tag scan of {filename!r} on {printer_name} failed: {e}")
        except Exception:
            pass
        return None


def forget():
    """Tests: forget what this run has said."""
    with _SAID_LOCK:
        _SAID.clear()
