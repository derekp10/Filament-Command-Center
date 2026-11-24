import requests
import errno
import os
import re
import socket
import struct
import threading
import time
from typing import Dict, List, Optional
import bgcode_decode  # binary-gcode (.bgcode) decoder for the cancel prefix-parse

# Per-operation memo for get_printer_state (L3 fix A). A single
# perform_smart_move probes the SAME printer in BOTH its phase-1 and phase-2
# (auto-deploy) passes; without this the recursion hits the network twice and,
# on an offline printer, pays the full timeout twice — the dominant cost in the
# slot-assign latency. The logic.perform_smart_move wrapper begins/clears it per
# top-level move, so it is strictly scoped and never serves stale state to
# unrelated requests. When no cache is active (the common case for every other
# caller) get_printer_state behaves exactly as before — no memoization.
_probe_cache = threading.local()


def begin_probe_cache():
    """Start a fresh per-operation get_printer_state memo on this thread."""
    _probe_cache.data = {}


def clear_probe_cache():
    """Tear down the per-operation memo. Idempotent."""
    _probe_cache.data = None


def fetch_printer_credentials(filabridge_url: str, printer_name: str):
    """Return ``{'ip_address','api_key'}`` for a printer, or ``None``.

    FilaBridge Phase-2 cutover: credentials now live on the first-class
    Type:"Printer" row in locations.json (``printer_creds``), read here via
    ``locations_db.get_printer_credentials``. ``filabridge_url`` is retained for
    the call-site/back-compat contract (every consumer + test stub passes it) but
    is now UNUSED — the same pattern Scope 1 used to retire ``_fb_spool_location``'s
    FilaBridge read. A one-time boot seed primed the rows from FilaBridge before it
    was decommissioned; it was removed in Group 56.5, and a row's connection is now
    entered in Settings → Printer Connections.

    Lazy local import of ``locations_db`` to avoid a circular import at module
    load (``locations_db`` / ``app`` import ``prusalink_api``).
    """
    try:
        import locations_db
        return locations_db.get_printer_credentials(printer_name)
    except Exception as e:
        print(f"Error reading printer credentials for {printer_name!r}: {e}")
        return None


def _parse_weights_from_match(match) -> Dict[int, float]:
    weights_str = match.group(1)
    weights = [w.strip() for w in weights_str.split(',')]
    usage = {}
    for idx, w in enumerate(weights):
        try:
            val = float(w)
            if val > 0:
                usage[idx] = val
        except ValueError:
            pass
    return usage


def parse_footer_usage(gcode_content: str) -> Dict[int, float]:
    """Parse the slicer's full per-tool ``filament used [g]`` footer →
    ``{tool_index: grams}`` — the COMPLETE-print estimate (exactly what FilaBridge
    bills). Used by FCC's Phase-2 FINISHED-completion deduct (the footer is exact;
    the cancel prefix-parse is only for PARTIAL/cancelled prints). Same indexing
    space as ``parse_partial_filament_usage`` (the comma-separated array is tool
    0,1,2,…). Empty dict when the footer is absent."""
    if not gcode_content:
        return {}
    m = _GCODE_G_RE.search(gcode_content)
    return _parse_weights_from_match(m) if m else {}


def pushed_before(gcode_content: str, reached_fraction) -> bool:
    """Group 64 fix review (FW1): whether any tool pushed filament out before the cut
    at `reached_fraction` (the file-byte fraction, as measure_filament_usage reads it),
    counted with no MMU rule: an MMU print's first load is no filament used by the
    slicer's count, though its E moves run (a purge line). False when nothing was
    pushed out (a cancel during preheat), or the file can't be walked."""
    try:
        total = len(gcode_content.encode('utf-8'))
        cut = int(max(0.0, min(1.0, float(reached_fraction))) * total)
        cuts, _whole = _walk_extrusion(gcode_content, [cut], 0, mmu=None)
        return any(mm > 0 for mm in cuts[0][0].values())
    except Exception:
        return False


def footer_usage_present(gcode_content: str) -> bool:
    """True when the file carries a per-tool ``filament used [g] = …`` footer line,
    even one that lists only zeros: Group 56.3 tells a completion whose footer
    couldn't be read from one whose footer lists no filament."""
    return bool(gcode_content) and _GCODE_G_RE.search(gcode_content) is not None


# --- Cancelled-print partial usage (FilaBridge absorption §9.2, slice 3) ------

def _download_file_bytes(ip_address: str, api_key: str, filename: str) -> Optional[bytes]:
    """Download a print file's raw bytes from PrusaLink. After a print STOPS the
    file un-404s (it's locked + 404 while printing), so this works at cancel
    time. Returns the bytes, or None on failure."""
    filename = filename.lstrip('/')
    url = f"http://{ip_address}/{filename}"
    headers = {'X-Api-Key': api_key} if api_key else {}
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.ok:
            return resp.content
        print(f"download_gcode_content: HTTP {resp.status_code} for {filename}")
    except Exception as e:
        print(f"download_gcode_content failed for {filename}: {e}")
    return None


def download_gcode_content(ip_address: str, api_key: str, filename: str) -> Optional[str]:
    """Download the full print file as ASCII G-code text, transparently decoding
    binary G-code (`.bgcode`) — its body is heatshrink+MeatPack compressed, so a
    naive text decode is garbage; `bgcode_decode` reconstructs the moves so the
    prefix-parse can run on Derek's real (binary) prints. Returns None on
    failure. (For binary gcode, prefer `fetch_cancel_gcode`, which also remaps
    the progress fraction from compressed-file to decoded-text space.)"""
    raw = _download_file_bytes(ip_address, api_key, filename)
    if raw is None:
        return None
    try:
        if bgcode_decode.is_bgcode(raw):
            return bgcode_decode.decode_bgcode(raw).get("gcode") or None
        return raw.decode("utf-8", "replace")
    except Exception as e:
        print(f"download_gcode_content: decode failed for {filename}: {e}")
        return None


def fetch_cancel_gcode(ip_address: str, api_key: str, filename: str,
                       reached_fraction: float, extra_fractions=None) -> Optional[Dict]:
    """Download + decode a print file for the cancelled-print parser.

    Returns ``{"gcode": ascii_text, "fraction": effective_fraction}`` or None on
    failure. For binary G-code the printer's ``progress`` (a byte position in
    the COMPRESSED .bgcode file) is remapped to the matching position in the
    DECODED text, so the prefix-parse slices at the right point even though the
    header/thumbnail/metadata blocks (which carry no extrusion) sit before the
    G-code in the file. For plain ASCII gcode the fraction passes through.

    `extra_fractions` (hotfix 2026-11-11): more progress values to cut the same
    file at, the print's recorded mid-print swaps (the run-out split's
    boundaries). Each is remapped exactly as `reached_fraction` is and comes back
    in order as ``"fractions"``, so one download serves the print's usage and its
    split; the split used to download the file a second time (another 20 minutes
    on the INDX).

    A file that downloaded but can't be read (Group 64.4) answers
    ``{"gcode": None, "decode_error": "<why>"}``: a ``.bgcode`` that decodes to no
    G-code, or a decode that raises. None means only that the download failed (the
    file locked behind the printer's screen, a network blip), which the queue
    retries for 72 hours; a file that never decodes used to be downloaded again on
    every idle tick for those 72 hours too, and is given up after a few tries now.
    An empty plain-text body is still a failed download, as before.
    """
    raw = _download_file_bytes(ip_address, api_key, filename)
    if raw is None:
        return None
    try:
        if bgcode_decode.is_bgcode(raw):
            dec = bgcode_decode.decode_bgcode(raw)
            if not dec.get("gcode"):
                return {"gcode": None,
                        "decode_error": "its binary G-code decoded to no G-code"}

            def _remap(p):
                return bgcode_decode.progress_to_decoded_fraction(dec, p)
            text = dec["gcode"]
        else:
            def _remap(p):
                return max(0.0, min(1.0, float(p)))
            text = raw.decode("utf-8", "replace")
        out = {"gcode": text, "fraction": _remap(reached_fraction)}
        if extra_fractions:
            out["fractions"] = [_remap(p) for p in extra_fractions]
        # Group 65.1 (1b): how a progress value is placed in this file, so the review
        # can cut it at every whole percent in the same walk (its figures, for
        # "Charge the whole print" and a percentage typed later). The caller's call is
        # unchanged: the 34 stand-ins that answer four arguments keep working, and a
        # result without it keeps no figures.
        out["remap"] = _remap
        return out
    except Exception as e:
        print(f"fetch_cancel_gcode: failed for {filename}: {e}")
        return {"gcode": None,
                "decode_error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__}


_GCODE_G_RE = re.compile(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)')
_GCODE_MM_RE = re.compile(r';?\s*filament used \[mm\]\s*=\s*([0-9.,\s]+)')
_TOOL_RE = re.compile(r'^T(\d+)(?![0-9])')
_E_RE = re.compile(r'E(-?\d*\.?\d+)')
# Every move that can extrude: G0 / G1 lines AND G2 / G3 arcs (Group 56.1),
# with or WITHOUT a trailing space (Prusa no-spaces gcode emits
# `G1X92.3Y9.4E.001` and `G3X122.82Y109.2I7.785J7.955E.23882`), zero-padded
# (`G01`, `G03`, which the firmware reads as G1 / G3) or not. The lookahead keeps
# G10 / G11 / G12 / G28 / G29 out, padded or not. Arc-fitted prints put 4-9% of a
# tool's filament on arcs (the raccoon INDX print: 48.43 g counted against a
# 52.27 g footer without them, 52.26 g with them).
_EXTRUDING_MOVE_RE = re.compile(r'^G0*[0-3](?![0-9])')
# PrusaSlicer 2.9.6's `;EXCLUDE_E_START` / `;EXCLUDE_E_END` custom G-code tags:
# moves between them "aren't incorporated into filament consumption" (its
# release notes), so the slicer's footer leaves them out and the walk must too.
# The Core One INDX profile (2.5.12 on) wraps the park (`G27 ... R8`: the firmware
# pulls the filament back 8 mm, and no E move in the file says so) and, each time
# a tool already used is picked up again, the tool lock (`G1 E1.6 ; Final lock
# tool`) and the restore of those 8 mm (`; Restore filament retracted by G27 R on
# park`); with a wipe tower, `G1 E2.0` and the rest of the restore. A tool's first
# pick-up primes 1.6 mm outside the tags, and counts. Counted, the lock and the
# restore made a small four-colour print walk to ~2.5x its footer (job 1134,
# hotfix 2026-11-02). Read as the slicer reads it (GCodeProcessor::process_gcode_line
# / process_tags): a whole-line comment, blanks before the ';' trimmed, the tag
# right after the ';' as a prefix, case as written. An older INDX profile wrote the
# words as bare lines with no ';' (the raccoon capture): the slicer counted those
# moves, so a bare line is no tag.
_EXCLUDE_E_TAG_RE = re.compile(r'\s*;EXCLUDE_E_(START|END)')
# PrusaSlicer 2.9.6's other custom tags, `;FLUSH_START` / `;FLUSH_END`, read the same
# way (GCodeProcessor::process_tags): what a move between them pushes out is added to
# its tool's count in full (UsedFilaments::update_flush_per_extruder), paying no debt,
# and a pull-back between them owes none (Group 64.5). The INDX profile wraps each
# pick-up's flush in them; files from a slicer before 2.9.6 carry the tags too, and
# walk to their footers either way (a pull-back inside a flush is the only place the
# two counts differ).
_FLUSH_TAG_RE = re.compile(r'\s*;FLUSH_(START|END)')
# Group 64.5: G90 / G91 (absolute / relative positioning for every axis, E
# included), zero-padded or not; G90.1-style subcodes are no such line.
_POSITIONING_RE = re.compile(r'^G0*9([01])(?![0-9.])')
# An axis word on a G92 line other than E (X, Y, Z, or a rotary axis).
_AXIS_WORD_RE = re.compile(r'[XYZABC]-?\d*\.?\d')
# Group 64.6: the slicer's MMU rule. For a single-extruder multi-material print
# with more than one extruder and a wipe tower (an MMU), GCodeProcessor::apply_config
# keeps a parking position and an extra loading move (`parking_pos_retraction`,
# `extra_loading_move`), and UsedFilaments::increase_caches starts each extruder
# owing the parking distance (its filament waits parked in the MMU, so its first
# load is no filament used) and counts the first counted move after each tool change
# the extra loading move less (the wipe tower unloads the parking distance and loads
# parking + extra back). Read from the file's own config block: a plain .gcode's, or
# the copy bgcode_decode appends from a .bgcode's Slicer-Metadata block.
_SLICER_CONFIG_BEGIN = "; prusaslicer_config = begin"
_MMU_CONFIG_RE = re.compile(
    r'(?m)^;[ \t]*(single_extruder_multi_material|wipe_tower|parking_pos_retraction'
    r'|extra_loading_move|nozzle_diameter)[ \t]*=[ \t]*(.*?)[ \t\r]*$')


def _config_block_start(text: str) -> int:
    """Where the file's config block begins: the last line that is exactly the
    begin marker (a CRLF file's \\r allowed), never the marker's words inside another
    line (a start G-code that holds them, kept on its own config line after the real
    marker: Group 64 review, W2). -1 when there is none."""
    end = len(text)
    while True:
        at = text.rfind(_SLICER_CONFIG_BEGIN, 0, end)
        if at < 0:
            return -1
        line_end = text.find('\n', at)
        line = text[at:line_end if line_end >= 0 else len(text)]
        if (at == 0 or text[at - 1] == '\n') and line.rstrip('\r \t') == _SLICER_CONFIG_BEGIN:
            return at
        end = at


def _mmu_rule(gcode_content: str):
    """``(parking mm, extra loading mm)`` when the file's config block says the
    slicer counted it as an MMU print (single extruder multi material, a wipe tower,
    more than one extruder by its `nozzle_diameter` list, as apply_config reads
    them), else None."""
    at = _config_block_start(gcode_content)
    if at < 0:
        return None
    cfg = {}
    for m in _MMU_CONFIG_RE.finditer(gcode_content, at):
        cfg.setdefault(m.group(1), m.group(2))
    if cfg.get("single_extruder_multi_material") != "1" or cfg.get("wipe_tower") != "1":
        return None
    if len([v for v in cfg.get("nozzle_diameter", "").split(",") if v.strip()]) < 2:
        return None
    try:
        return float(cfg["parking_pos_retraction"]), float(cfg["extra_loading_move"])
    except (KeyError, ValueError):
        return None


def _walk_extrusion(gcode_content: str, cut_bytes: List[int], default_tool: int, mmu=None):
    """One pass over a print file: each tool's extruded mm up to every byte in
    `cut_bytes`, and over the whole file.

    A line counts toward a cut only when it ENDS at or before that byte (a line
    the printer had started but not finished is left out). Returns
    ``(cuts, whole)``: ``cuts`` is a list in `cut_bytes` order of
    ``({tool: mm}, saw_tool)``, and ``whole`` is the same pair for the file.

    One rule for both E modes (Group 64.5): one E axis, as the slicer keeps it (a
    tool picked up takes the axis where it is; Group 64 review, W3), and each tool a
    high-water mark of it (what it owes is how far the axis is below its mark);
    new filament is what the position passes the mark by. A relative move (``M83``
    for E, or ``G91`` for every axis: E is relative under either, as PrusaSlicer's
    GCodeProcessor reads them, so ``G90`` doesn't undo ``M83``) adds to the
    position; an absolute one sets it. So a retract the file takes back adds
    nothing, and one it never takes back (each tool's last, the park's at a
    cancel) stays counted, as the slicer's footer counts it: the walk used to net
    them in relative E and land ~0.8 mm per tool under its footer. ``G92 E<v>``
    moves the position to v and keeps a retract still owed (the mark is v plus
    what was owed), so the un-retract after it isn't new filament; a bare ``G92``
    is ``G92 E0``, and one naming only other axes leaves E alone. Inline ``;``
    comments are ignored.
    A move between the slicer's ``;EXCLUDE_E_START`` / ``;EXCLUDE_E_END`` tags
    adds no filament, as in the slicer's own count (`_EXCLUDE_E_TAG_RE`), but it
    still moves E: the mark moves by the move's own delta, so a retract before it
    is still owed and E past the moved mark counts (the slicer's count, for any
    excluded move). Tool changes and ``G92`` inside the tags act as anywhere else;
    a START with no END leaves out the rest of the file and an END with no START
    does nothing, as in the slicer. A move between ``;FLUSH_START`` /
    ``;FLUSH_END`` (`_FLUSH_TAG_RE`) moves the mark with the position too, and what
    it pushes out counts in full; an excluded move inside a flush counts nothing.
    `mmu` (Group 64.6, `_mmu_rule`): ``(parking mm, extra loading mm)`` for an MMU
    print, counted as the slicer counts one. Each tool starts owing the parking
    distance; the first counted move (not excluded, not a flush, E moving) after a T
    naming another tool counts the extra loading move less; the walk starts on the
    slicer's first extruder, 0, rather than `default_tool` (a file with no T at all
    is still folded onto its footer's sole tool by the caller). A cut then counts
    each tool's mm as they are: a debt there may be an unload's parking distance,
    which was never counted, so it comes off nothing.
    """
    order = sorted(range(len(cut_bytes)), key=lambda i: cut_bytes[i])
    cuts = [None] * len(cut_bytes)
    nxt = 0
    park, extra_load = mmu if mmu else (0.0, 0.0)
    active_tool = 0 if mmu else default_tool
    tool_changed = False         # MMU: a tool change whose first counted move hasn't come
    relative_e = False           # M83 (E relative) vs M82 (E absolute, the default)
    relative_all = False         # G91 (every axis relative) vs G90 (absolute, the default)
    e_pos: Dict[int, float] = {}    # the one E axis: the active tool's entry is where it
                                    # is; an idle tool's entry only keeps, with its mark,
                                    # what that tool owes (the T branch hands it the axis)
    e_mark: Dict[int, float] = {}   # per-tool high-water mark of the axis (a tool not
                                    # seen yet owes `park`: 0 but on an MMU)
    extruded_mm: Dict[int, float] = {}
    saw_tool = False
    exclude_e = False            # between ;EXCLUDE_E_START and ;EXCLUDE_E_END
    flushing = False             # between ;FLUSH_START and ;FLUSH_END
    consumed = 0

    for line in gcode_content.splitlines(keepends=True):
        consumed += len(line.encode('utf-8'))
        # Every cut this line runs past sees the state before the line: what each
        # tool had pushed out, and the retract it still owed then (worked out once
        # the walk ends, below).
        while nxt < len(order) and consumed > cut_bytes[order[nxt]]:
            cuts[order[nxt]] = (dict(extruded_mm),
                                {t: max(0.0, e_mark.get(t, park) - e_pos.get(t, 0.0)) for t in extruded_mm},
                                saw_tool)
            nxt += 1
        code = line.split(';', 1)[0].strip()
        if not code:
            # A whole-line comment (or a blank line): only a tag acts here. The
            # substring test keeps the regex off the many lines that can't be one.
            if 'EXCLUDE_E_' in line:
                tag = _EXCLUDE_E_TAG_RE.match(line)
                if tag:
                    exclude_e = tag.group(1) == 'START'
            if 'FLUSH_' in line:
                tag = _FLUSH_TAG_RE.match(line)
                if tag:
                    flushing = tag.group(1) == 'START'
            continue
        upper = code.upper()

        tmatch = _TOOL_RE.match(upper)
        if tmatch:
            tool = int(tmatch.group(1))
            if mmu and tool != active_tool:
                tool_changed = True
            if tool != active_tool and active_tool in e_pos:
                # One E axis for every tool, as the slicer keeps it (Group 64 review,
                # W3): the new tool takes the axis where it is, keeping only what it
                # owes. Relative E counts the same either way; in absolute E a custom
                # tool change that moves E on both sides of the T counted 2 mm short.
                owed_new = e_mark.get(tool, e_pos.get(tool, 0.0) + park) - e_pos.get(tool, 0.0)
                e_pos[tool] = e_pos[active_tool]
                e_mark[tool] = e_pos[tool] + owed_new
            active_tool = tool
            saw_tool = True
            continue
        if upper.startswith('M82'):
            relative_e = False
            continue
        if upper.startswith('M83'):
            relative_e = True
            continue
        mode = _POSITIONING_RE.match(upper)
        if mode:
            relative_all = mode.group(1) == '1'      # G91 relative, G90 absolute
            continue
        if upper.startswith('G92'):
            em = _E_RE.search(upper)
            if em is None and _AXIS_WORD_RE.search(upper[3:]):
                continue        # G92 naming only other axes: E stays where it is
            # G92 E<v> (a bare G92 is E0) moves E to v: a retract still owed stays
            # owed, so the un-retract after it isn't new filament.
            pos = e_pos.get(active_tool, 0.0)
            owed = e_mark.get(active_tool, park) - pos
            v = float(em.group(1)) if em else 0.0
            e_pos[active_tool] = v
            e_mark[active_tool] = v + owed
            continue
        if _EXTRUDING_MOVE_RE.match(upper):
            em = _E_RE.search(upper)
            if not em:
                continue
            e = float(em.group(1))
            pos = e_pos.get(active_tool, 0.0)
            new = pos + e if (relative_e or relative_all) else e
            mark = e_mark.get(active_tool, park)
            if exclude_e:
                # Not filament, but E moves: the mark moves by the same delta.
                mark += new - pos
            elif flushing:
                # A flush: what it pushes out counts in full, paying no debt, and a
                # pull-back owes none (the mark moves with the position).
                if new > pos:
                    extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + (new - pos)
                mark += new - pos
            else:
                if tool_changed and new != pos:
                    # MMU: the first counted move after a tool change counts the
                    # extra loading move less (the slicer's recent_toolchange).
                    mark += extra_load
                    tool_changed = False
                if new > mark:
                    # Only E past the running mark is new filament (a retract and its
                    # re-prime below the mark add nothing; a retract never taken back
                    # stays counted, as in the slicer's footer).
                    extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + (new - mark)
                    mark = new
            e_mark[active_tool] = mark
            e_pos[active_tool] = new

    whole = (dict(extruded_mm), saw_tool)
    for i in order[nxt:]:
        cuts[i] = whole
    # A cut counts what each tool pushed out, less a retract still pending then:
    # pulled back into the tool, not used (the next prime gives it back), so a
    # cancel isn't charged it. A tool that pushes out nothing more after the cut
    # had finished: it keeps its whole count, a retract the file never takes back
    # included, as the slicer's footer (and a completion's charge) counts it.
    for i, snap in enumerate(cuts):
        if snap is whole:
            continue
        mm_at, owed_at, saw_at = snap
        if mmu:
            cuts[i] = (mm_at, saw_at)
            continue
        cuts[i] = ({t: (mm if mm >= extruded_mm.get(t, 0.0) - 1e-9
                        else max(0.0, mm - owed_at.get(t, 0.0)))
                    for t, mm in mm_at.items()}, saw_at)
    return cuts, whole


def measure_filament_usage(gcode_content: str, reached_fractions) -> Optional[Dict]:
    """Per-toolhead grams a print used up to each of `reached_fractions`, from ONE
    pass over the file (Group 56.2) — the cancelled-print partial-deduction core
    (FilaBridge absorption design §9.2, rung 1) and the run-out split's boundaries.

    A cancelled print's ``filament used [g]`` footer is the FULL-job estimate, so
    deducting it would massively over-charge. Instead the gcode is walked from the
    start, summing each tool's real extrusion up to the byte actually reached
    (PrusaLink ``progress`` is ``sd_percent_done`` = the gcode FILE-BYTE fraction)
    and on to the end of the file. Each tool's charge is the share of its own
    whole-file extrusion reached, times the footer's grams for that tool, never
    more than the footer: ``footer_g × partial_mm / whole_mm``. The footer is the
    slicer's count of the whole job, so a walk that over- or under-counts the file
    as a whole can't move a cancel's charge past it (since Group 64.5 / 64.6 the walk
    is the slicer's own count, to 0.005 mm per tool on every capture here). A tool
    whose walk sums to nothing over the file falls back to mm × the footer's own g/mm
    (a guard: the count only grows, so no walk reaches it).

    Critically this is PER-TOOLHEAD by construction: a tool never selected before
    the cancel sums to zero extrusion and is simply absent from that result (the XL
    "untouched head deducts 0" invariant, satisfied natively).

    Args:
        gcode_content: the FULL gcode file text (footer + body). Cut bytes are
            computed against this content's length, so it must be the whole file,
            not a Range subset.
        reached_fractions: progress values 0.0..1.0 (``progress`` percent / 100).

    Returns:
        ``{"partials": [{tool: grams}, ...], "whole": {tool: grams},
        "footer": {tool: grams}}``: one partial per fraction, in order (untouched
        tools omitted; empty when nothing extruded before that cut), the whole-file
        walk at the footer's g/mm (what the 2% check compares, unscaled), and the
        footer's grams for every tool it gives a g/mm for. ``None`` when the file
        lacks the per-tool ``[g]`` / ``[mm]`` footer needed to convert.
    """
    if not gcode_content:
        return None

    # --- per-tool grams-per-mm from the slicer footers ---------------------
    g_match = _GCODE_G_RE.search(gcode_content)
    mm_match = _GCODE_MM_RE.search(gcode_content)
    if not g_match or not mm_match:
        return None
    grams = _parse_weights_from_match(g_match)
    mms = _parse_weights_from_match(mm_match)
    g_per_mm = {
        tool: grams[tool] / mm
        for tool, mm in mms.items()
        if mm > 0 and tool in grams
    }
    if not g_per_mm:
        return None

    total_bytes = len(gcode_content.encode('utf-8'))
    cut_bytes = [int(max(0.0, min(1.0, float(f))) * total_bytes) for f in reached_fractions]

    # When the gcode carries no explicit `Tn` (a single-material print whose
    # one tool is selected outside the body, common on MMU), attribute all
    # extrusion to the sole tool the footer marks as used. Multi-tool prints
    # have `Tn` changes and start at tool 0.
    default_tool = next(iter(g_per_mm)) if len(g_per_mm) == 1 else 0
    cuts, whole = _walk_extrusion(gcode_content, cut_bytes, default_tool,
                                  mmu=_mmu_rule(gcode_content))

    def _fold(walked):
        mm_by_tool, saw_tool = walked
        # If we never saw a Tn but accumulated onto a default that has no g/mm,
        # fold it onto the sole footer tool (single-material, no explicit select).
        if not saw_tool and len(g_per_mm) == 1 and mm_by_tool:
            return {next(iter(g_per_mm)): sum(mm_by_tool.values())}
        return mm_by_tool

    whole_mm = _fold(whole)
    partials = []
    for cut, walked in zip(cut_bytes, cuts):
        result = {}
        if cut > 0:
            for tool, mm in _fold(walked).items():
                if mm <= 0 or tool not in g_per_mm:
                    continue
                total_mm = whole_mm.get(tool, 0.0)
                if total_mm > 0:
                    charge = grams[tool] * mm / total_mm
                else:
                    charge = mm * g_per_mm[tool]
                result[tool] = round(min(charge, grams[tool]), 4)
        partials.append(result)
    return {
        "partials": partials,
        "whole": {tool: round(mm * g_per_mm[tool], 4)
                  for tool, mm in whole_mm.items() if mm > 0 and tool in g_per_mm},
        "footer": {tool: grams[tool] for tool in g_per_mm},
    }


def parse_partial_filament_usage(gcode_content: str, reached_fraction: float) -> Dict[int, float]:
    """``{toolhead_index: grams}`` a print used up to `reached_fraction` (0.0..1.0):
    :func:`measure_filament_usage` for one cut. Untouched tools are omitted (the
    caller treats absent as 0). Empty dict when nothing extruded before the cut, or
    the footer lacks the per-tool g/mm metadata needed to convert."""
    measured = measure_filament_usage(gcode_content, [reached_fraction])
    return measured["partials"][0] if measured else {}


# Marker PrusaSlicer emits immediately before each planned color change, e.g.
# `;COLOR_CHANGE,T0,#FF8800`. Scanning THIS (not the bare `M600`, which a user can
# remap via `color_change_gcode`) is the deterministic boundary signal. Both the
# T-index and the hex are optional in older/edge slicer output, so capture
# defensively. The `\b` after COLOR_CHANGE is load-bearing: without it (and with the
# optional groups) `.match` would accept any line starting `;COLOR_CHANGE…` —
# `;COLOR_CHANGE_DATA`, `;COLOR_CHANGEDFOO` — emitting spurious boundaries. Matched
# per-line (after lstrip), so no MULTILINE needed.
_COLOR_CHANGE_RE = re.compile(
    r';\s*COLOR_CHANGE\b(?:\s*,\s*T(\d+))?(?:\s*,\s*(#?[0-9A-Fa-f]{6}))?',
    re.IGNORECASE)


def parse_color_change_segments(gcode_content: str) -> List[Dict]:
    """22.3(b) SCAFFOLD — the boundary primitive for per-segment apportionment of a
    single-extruder Color-Change (M600) print.

    PrusaSlicer emits a ``;COLOR_CHANGE,T<n>,#RRGGBB`` marker immediately before each
    planned color change. This scans the DECODED gcode for those markers and returns
    the ordered cut boundaries — each marker line's start byte offset, the equivalent
    file-byte FRACTION (the SAME 0..1 space ``parse_partial_filament_usage`` slices on,
    so a downstream split can prefix-parse to a boundary directly), the tool index, and
    the hex color.

    Returns ``[{seq, byte_offset, fraction, tool, color}, …]`` in file order (empty when
    the print has no color changes — i.e. not a Color-Change print). The segments it
    implies are ``[0 → b0], [b0 → b1], …, [b_last → 1.0]``.

    SCOPE: segmentation boundaries ONLY. Computing per-segment GRAMS (integrate E
    between consecutive boundaries with the existing ``parse_partial_filament_usage``
    E-walk, then attribute segment k → the spool loaded after the k-th resume from the
    ``swap_log``) is the validated-math step DEFERRED until Derek's real M600 capture
    confirms the footer/marker behavior (Group 22.3(b)). This function is pure and is
    NOT wired to any weight write — building the boundary scanner now de-risks that step
    without touching the live deduct path. Research note: for a single configured
    extruder the ``filament used [g]`` footer is a SINGLE total (no per-color array), so
    per-segment grams MUST come from this E-integration, not the footer.

    ⚠️ UNVALIDATED ASSUMPTION (confirm with the real capture before the consumer lands):
    this relies on the ``;COLOR_CHANGE`` COMMENT line surviving the binary-gcode decode
    (the whole fleet is ``.bgcode``). If PrusaSlicer's binary encoder strips body comments
    (or Derek's "output comments" slicer setting is off), the decoded text carries no
    marker and this returns ``[]`` on every real print — in which case the boundary
    signal must move to the executable ``M600``/``M601`` line instead. The Group 22.3(b)
    experiment checklist captures the raw decoded ``.bgcode`` precisely to settle this.
    """
    if not gcode_content:
        return []
    total_bytes = len(gcode_content.encode('utf-8')) or 1
    segments: List[Dict] = []
    consumed = 0
    seq = 0
    for line in gcode_content.splitlines(keepends=True):
        m = _COLOR_CHANGE_RE.match(line.lstrip())
        if m:
            color = m.group(2)
            if color and not color.startswith('#'):
                color = '#' + color
            segments.append({
                "seq": seq,
                "byte_offset": consumed,
                "fraction": round(consumed / total_bytes, 6),
                "tool": int(m.group(1)) if m.group(1) is not None else None,
                "color": color,
            })
            seq += 1
        consumed += len(line.encode('utf-8'))
    return segments


# The run-out split's boundaries (22.3(b)) used to come from a second download of
# the print file here (compute_segment_usage). Since the hotfix of 2026-11-11 they
# are cut from the print's one download: fetch_cancel_gcode's `extra_fractions`,
# walked in the same pass as the cancel's usage (print_deduct._compute_cancel_usage).


def get_printer_state(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Cached front door for the PrusaLink state probe (L3 fix A).

    Memoizes per-operation when a probe cache is active (see begin_probe_cache),
    so a single perform_smart_move probes a given printer ONCE across its
    phase-1/phase-2 auto-deploy recursion instead of twice. With no active cache
    it just calls through, so every other caller (/api/printer_state, usage
    deduction) is unchanged.
    """
    key = (filabridge_url, printer_name)
    cache = getattr(_probe_cache, "data", None)
    if cache is not None and key in cache:
        return cache[key]
    result = _probe_printer_state(filabridge_url, printer_name)
    if cache is not None:
        cache[key] = result
    return result


def _probe_printer_state(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Best-effort PrusaLink state probe for a named printer. Returns a dict
    {state: str, is_active: bool} or None on any failure (fail-open — the
    caller treats None as "unknown" and does not block user actions).

    Tries the v1 status endpoint first (newer PrusaLink firmware), then falls
    back to the legacy /api/printer shape. Timeouts are deliberately short
    so the assignment-flow warning doesn't stall the UI when the printer is
    unreachable (offline, networked elsewhere, cold-rebooting, etc.).

    `is_active` is true only when PrusaLink reports a state in which a spool
    swap would physically disrupt the print: PRINTING, PAUSING, RESUMING.
    PAUSED, BUSY (heating/homing/prep), Operational, Idle, Finished, and
    Stopped all read as not-active so eject/swap operations can proceed —
    those are exactly the moments the user wants to swap filament (13.8).
    """
    # PrusaLink states classified as "active print" — anything outside this
    # set is fair game for eject / smart-move / quick-swap.
    _ACTIVE_PRINT_STATES = {"PRINTING", "PAUSING", "RESUMING"}
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        _note_probe_failure(printer_name, "no_ip")
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}

    # v1 status — returns {"printer": {"state": "PRINTING", ...}, ...}
    why = "unreadable"
    try:
        r = requests.get(f"http://{ip}/api/v1/status", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            printer = body.get("printer") or {}
            state_str = str(printer.get("state", "")).upper()
            if state_str:
                _note_probe_failure(printer_name, None)
                return {"state": state_str, "is_active": state_str in _ACTIVE_PRINT_STATES}
        else:
            why = f"http {r.status_code}"
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        # L3 fix B: a connection-level failure (timeout / refused / no route)
        # means the printer is unreachable. The legacy endpoint lives on the
        # SAME ip:port and will time out too — skip it instead of burning a
        # second 2s timeout. Halves the probe cost for an offline printer.
        _note_probe_failure(printer_name, _connection_failure_kind(e))
        return None
    except Exception:
        # v1 answered but the body was unusable (bad JSON / odd shape) — fall
        # through and try the legacy endpoint, which may parse on old firmware.
        pass

    # Legacy /api/printer — returns {"state": {"text": "Printing", "flags": {...}}, ...}
    try:
        r = requests.get(f"http://{ip}/api/printer", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            flags = (body.get("state") or {}).get("flags") or {}
            state_text = str((body.get("state") or {}).get("text", "")).upper()
            # Legacy /api/printer only exposes `printing` and `paused` flags
            # — there's no "pausing/resuming" distinction. Per 13.8 we drop
            # the paused-blocks-eject behavior; mid-print pause is exactly
            # when a user wants to swap filament. Block only on the active
            # printing flag.
            is_active = bool(flags.get("printing")) or state_text in _ACTIVE_PRINT_STATES
            if state_text:
                _note_probe_failure(printer_name, None)
                return {"state": state_text, "is_active": is_active}
        elif why == "unreadable":
            why = f"http {r.status_code}"
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        why = _connection_failure_kind(e)
    except Exception:
        pass

    _note_probe_failure(printer_name, why)
    return None


# Group 65.1 (2): why each printer's last state probe failed, beside its unchanged
# answer (None, fail-open, for every caller): "no_ip" (no PrusaLink IP saved),
# "timeout", "refused" (the printer answered, and nothing listens: it is on the
# network), "no_route", "connection" (another connection failure), "http <status>",
# "unreadable" (a body FCC couldn't read). Cleared by an answer. The print monitor reads
# it to stay quiet about a printer with no IP saved, and (65.1 (3)) to tell PrusaLink
# stuck from a printer that doesn't answer at all.
_LAST_PROBE_FAILURE = {}


def _note_probe_failure(printer_name, why):
    if why is None:
        _LAST_PROBE_FAILURE.pop(printer_name, None)
    else:
        _LAST_PROBE_FAILURE[printer_name] = why


def _connection_failure_kind(e):
    if isinstance(e, requests.exceptions.Timeout):
        return "timeout"
    text = str(e).lower()
    if "refused" in text:
        return "refused"
    if "no route" in text or "unreachable" in text:
        return "no_route"
    return "connection"


def last_probe_failure(printer_name):
    """Why `printer_name`'s last state probe failed (see _LAST_PROBE_FAILURE), or None
    when it answered (or was never probed)."""
    return _LAST_PROBE_FAILURE.get(printer_name)


def _icmp_checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return (~total) & 0xFFFF


def _icmp_socket(kind):
    """An ICMP socket of `kind` (the tests' seam)."""
    return socket.socket(socket.AF_INET, kind, socket.IPPROTO_ICMP)


_UNREACHABLE = {getattr(errno, n) for n in ("EHOSTUNREACH", "ENETUNREACH", "EHOSTDOWN") if hasattr(errno, n)}


def icmp_echo(host, timeout=1.0):
    """Group 65.1 (3): one ICMP echo to `host` (an IP, a port after ':' ignored), the
    standard library only (the image has no `ping` program). True when it answers
    within `timeout`, False when it doesn't (or the network can't reach it), None when
    FCC can't send one: neither the unprivileged datagram socket (which works when the
    container's net.ipv4.ping_group_range covers its group, Docker's default since
    20.10) nor a raw one (which needs NET_RAW) opens. A host name is resolved once and
    a reply counts only from that address (Group 65 review, RW3: a reply never matched a
    name, and a printer that answers was called off); a name FCC can't resolve, an
    address that isn't IPv4, and a send the system refuses for a reason that isn't the
    network's are None too (WD12: FCC never pinged it). Never raises."""
    raw = str(host or "").strip()
    if not raw or raw.startswith("[") or raw.count(":") > 1:
        return None          # none, or an IPv6 address: this echo is IPv4 only
    try:
        ip = socket.gethostbyname(raw.split(":")[0])
    except (OSError, UnicodeError):
        return None
    ident = os.getpid() & 0xFFFF
    payload = b"fcc-reach"
    for kind in (socket.SOCK_DGRAM, socket.SOCK_RAW):
        try:
            sock = _icmp_socket(kind)
        except OSError:
            continue
        try:
            packet = struct.pack("!BBHHH", 8, 0, 0, ident, 1) + payload
            packet = struct.pack("!BBHHH", 8, 0, _icmp_checksum(packet), ident, 1) + payload
            deadline = time.monotonic() + float(timeout)
            sock.settimeout(float(timeout))
            try:
                sock.sendto(packet, (ip, 0))
            except OSError as e:
                # Only the network saying it can't reach the printer means it doesn't answer.
                return False if getattr(e, "errno", None) in _UNREACHABLE else None
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                sock.settimeout(left)
                try:
                    data, addr = sock.recvfrom(1024)
                except (socket.timeout, OSError):
                    return False
                if kind == socket.SOCK_RAW and data:
                    data = data[(data[0] & 0x0F) * 4:]      # a raw socket hands back the IP header
                if addr and addr[0] == ip and len(data) >= 8 and data[0] == 0:   # an echo reply
                    return True
        except Exception:
            return None
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return None


def _parse_v1_job(body: Dict) -> Optional[Dict]:
    """Normalize a PrusaLink ``/api/v1/job`` body to the tracker's shape."""
    f = body.get("file") or {}
    refs = f.get("refs") or {}
    # refs.download is the storage-relative URL PrusaLink serves the gcode at
    # (e.g. "/usb/Print.bgcode"); path/name are fallbacks for odd firmware.
    filename = refs.get("download") or f.get("path") or f.get("name")
    if not filename:
        return None
    prog = body.get("progress")
    if prog is None:
        prog = (body.get("job") or {}).get("progress")
    try:
        progress = max(0.0, min(1.0, float(prog) / 100.0)) if prog is not None else 0.0
    except (TypeError, ValueError):
        progress = 0.0
    return {
        "job_id": body.get("id"),
        "filename": filename,
        "progress": progress,
        "file_meta": f.get("meta") or {},
    }


def _parse_legacy_job(body: Dict) -> Optional[Dict]:
    """Normalize a legacy PrusaLink ``/api/job`` body (older firmware)."""
    job = body.get("job") or {}
    f = job.get("file") or {}
    filename = f.get("path") or f.get("name") or f.get("display")
    if not filename:
        return None
    completion = (body.get("progress") or {}).get("completion")
    try:
        # Legacy `completion` is a 0..1 fraction on most firmware but a
        # 0..100 percent on some builds — normalize defensively.
        c = float(completion) if completion is not None else 0.0
        progress = c / 100.0 if c > 1.0 else c
        progress = max(0.0, min(1.0, progress))
    except (TypeError, ValueError):
        progress = 0.0
    return {
        "job_id": body.get("id") or job.get("id"),
        "filename": filename,
        "progress": progress,
        "file_meta": {},
    }


def get_printer_job(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Best-effort fetch of the CURRENTLY-LOADED print job for a named printer.

    ``get_printer_state`` returns only the state enum; the cancelled-print
    detector (FilaBridge absorption design §9.3 / build slice 2a) also needs the
    running job's filename, id, and byte-progress to compute the PARTIAL deduct.
    PrusaLink tears the job block down the instant a print STOPS, so the tracker
    calls this on every IN-PROGRESS poll and latches the values for use on the
    later terminal edge — reading it post-cancel returns nothing.

    Returns ``{"job_id", "filename", "progress", "file_meta"}`` or None when
    there's no active job or the printer is unreachable. ``progress`` is the
    gcode FILE-BYTE fraction 0.0..1.0 (PrusaLink ``progress`` percent / 100 —
    the same proxy ``parse_partial_filament_usage`` slices on). ``filename`` is
    the storage-relative path PrusaLink serves the gcode at
    (``file.refs.download``, else ``file.path`` / ``file.name``), ready to hand
    to ``download_gcode_content``. Fails open (None) on any error.
    """
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}

    # v1 job — {"id", "progress"(0-100), "file": {"refs": {"download"}, "path",
    # "name", "meta": {...}}, ...}. 204/empty body when the printer is idle.
    try:
        r = requests.get(f"http://{ip}/api/v1/job", headers=headers, timeout=2)
        if r.status_code == 204:
            return None  # no active job
        if r.ok and r.content:
            parsed = _parse_v1_job(r.json() or {})
            if parsed:
                return parsed
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # Unreachable — the legacy endpoint lives on the same host and will
        # time out too; skip it (same L3 fix-B reasoning as the state probe).
        return None
    except Exception:
        pass  # odd/empty body — fall through to the legacy shape

    # Legacy /api/job — {"job": {"file": {"name","path"}}, "progress": {"completion"}}
    try:
        r = requests.get(f"http://{ip}/api/job", headers=headers, timeout=2)
        if r.ok and r.content:
            return _parse_legacy_job(r.json() or {})
    except Exception:
        pass
    return None


def get_printer_mmu_flag(filabridge_url: str, printer_name: str) -> Optional[bool]:
    """Best-effort probe of `/api/v1/info.mmu` on the named printer.

    Returns True when an MMU unit is attached/enabled, False when it's
    definitively not, or None when the printer is unreachable or the
    firmware doesn't expose the field. Callers treat None as "unknown" —
    do not block behaviour on an unknown answer.

    Note: the `mmu` field reflects hardware attachment, not per-print
    routing. A Core One with MMU3 attached but printing via direct feed
    still reports `mmu: true`. Used by the usage-deduction path to pick
    between M0/M1 alias locations when printer_map has both.
    """
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}
    try:
        r = requests.get(f"http://{ip}/api/v1/info", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            if "mmu" in body:
                return bool(body.get("mmu"))
    except Exception:
        pass
    return None
