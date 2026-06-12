"""Minimal pure-Python decoder for PrusaSlicer **binary G-code** (`.bgcode`).

Derek's whole fleet slices to binary G-code, and PrusaLink exposes no measured
filament metadata over the LAN — so the cancelled-print partial-deduct
(FilaBridge absorption §9.2 rung 1) needs the ACTUAL per-tool extrusion, which
only exists inside the compressed G-code blocks of the `.bgcode` file. This
module decodes those blocks back to ASCII G-code so the existing
`prusalink_api.parse_partial_filament_usage` prefix-parser can run on Derek's
real prints.

Format reference: the bgcode container spec (libbgcode). Header = magic `GCDE` +
uint32 version + uint16 checksum_type, then a sequence of blocks:
    uint16 type, uint16 compression, uint32 uncompressed_size,
    [uint32 compressed_size if compression != 0],
    block parameters (2-byte `encoding` for metadata/gcode; 6 bytes for
    thumbnails), data, then a 4-byte CRC32 if checksum_type != 0.

On Derek's files (probed live 2026-06-11) the G-code blocks are
`heatshrink (window=12, lookahead=4)` compressed and `MeatPack+comments`
encoded; metadata blocks are `deflate` (zlib) INI. This is a clean-room
implementation from those formats — heatshrink (ISC) and MeatPack are small,
deterministic algorithms; zlib is stdlib. Zero new dependencies.

This decoder is READ-ONLY/decode-only (no encoder) and tolerant: it skips
thumbnail/metadata blocks and only reconstructs the G-code body + a
byte-position map so a `.bgcode` print-progress fraction (a position in the
COMPRESSED file) can be translated to the matching offset in the decoded G-code.
"""
from __future__ import annotations

import re
import struct
import zlib
from typing import Dict, List, Optional, Tuple

BGCODE_MAGIC = b"GCDE"

# Block types
_BT_FILE_META = 0
_BT_GCODE = 1
_BT_SLICER_META = 2
_BT_PRINTER_META = 3
_BT_PRINT_META = 4
_BT_THUMBNAIL = 5
_META_TYPES = (_BT_FILE_META, _BT_SLICER_META, _BT_PRINTER_META, _BT_PRINT_META)
# Compression
_COMP_NONE = 0
_COMP_DEFLATE = 1
_COMP_HS_11_4 = 2
_COMP_HS_12_4 = 3
# G-code block encoding
_ENC_NONE = 0
_ENC_MEATPACK = 1
_ENC_MEATPACK_COMMENTS = 2

# Decompression-bomb guard: real G-code blocks decompress to well under 1 MB,
# so 64 MB is a huge margin while preventing a malformed/adversarial block from
# exhausting memory in the unattended daemon.
_MAX_BLOCK_OUTPUT = 64 * 1024 * 1024

# PrusaSlicer time-progress markers: `M73 P{percent} R{minutes}`. The printer's
# reported `progress` is this time-based value, so inverting it through these
# markers (percent -> reached byte) is exact; a raw byte mapping over-counts.
_M73_RE = re.compile(r'\bM73\b[^\n]*?\bP(\d+)')


def is_bgcode(data) -> bool:
    """True if `data` (bytes or str) begins with the bgcode magic `GCDE`."""
    if isinstance(data, str):
        data = data.encode("latin-1", "ignore")
    return bool(data) and data[:4] == BGCODE_MAGIC


# --- heatshrink decoder (window_sz2, lookahead_sz2) -------------------------

def heatshrink_decode(data: bytes, window: int, lookahead: int) -> bytes:
    """Decode a heatshrink-compressed byte string. MSB-first bitstream: a 1-tag
    bit = an 8-bit literal; a 0-tag = a backref of (window)-bit index and
    (lookahead)-bit count, where distance = index+1 and length = count+1."""
    out = bytearray()
    nbits = len(data) * 8
    pos = 0

    def get(n: int) -> Optional[int]:
        nonlocal pos
        if pos + n > nbits:
            return None
        v = 0
        p = pos
        for _ in range(n):
            v = (v << 1) | ((data[p >> 3] >> (7 - (p & 7))) & 1)
            p += 1
        pos = p
        return v

    while True:
        if len(out) > _MAX_BLOCK_OUTPUT:
            break  # decompression-bomb guard
        tag = get(1)
        if tag is None:
            break
        if tag == 1:
            b = get(8)
            if b is None:
                break
            out.append(b)
        else:
            idx = get(window)
            if idx is None:
                break
            cnt = get(lookahead)
            if cnt is None:
                break
            # Backref into heatshrink's zero-initialized circular window: a
            # distance larger than the output so far references not-yet-written
            # (zero) slots, so negative positions yield 0x00 rather than an
            # error (matches the reference decoder). For len(out) > 2^window a
            # valid distance (<= 2^window) keeps `start` >= 0, so indexing the
            # absolute output is equivalent to the circular buffer.
            start = len(out) - (idx + 1)
            length = cnt + 1
            for i in range(length):
                src = start + i
                out.append(out[src] if src >= 0 else 0)
    return bytes(out)


# --- MeatPack decoder -------------------------------------------------------

_MP_CMD = 0xFF
_MP_CMD_ENABLE = 0xFB
_MP_CMD_DISABLE = 0xFA
_MP_CMD_RESET = 0xF9
_MP_CMD_NOSPACES_ON = 0xF7
_MP_CMD_NOSPACES_OFF = 0xF6
# 4-bit nibble → character. 0x0F means "this char is an unpacked literal byte
# that follows in the stream". In no-spaces mode the space slot becomes 'E'.
_MP_LUT = b"0123456789. \nGX\x00"


def meatpack_decode(data: bytes, packing: bool = False, no_spaces: bool = False):
    """Decode a MeatPack byte stream back to ASCII.

    Framing (verified against real Prusa bgcode): a command is ``0xFF 0xFF
    <cmd>`` (enable/disable packing, no-spaces toggle); a lone ``0xFF`` (not
    doubled) is a packed byte whose BOTH nibbles are literal, so the next two
    bytes are the chars. Otherwise a packed byte holds two chars — FIRST in the
    low nibble, SECOND in the high nibble — and a nibble of 0xF means that char
    is a full literal byte taken from the stream next. In no-spaces mode the
    space slot (nibble 11) becomes ``'E'`` (the encoder strips spaces, so the
    decoded G-code is legitimately space-less, e.g. ``G1X92.3Y9.4E.001``).

    `packing`/`no_spaces` seed the state and the final state is returned, so a
    multi-block file can thread state across G-code block boundaries.
    Returns ``(bytes, packing, no_spaces)``.
    """
    out = bytearray()
    i = 0
    n = len(data)

    def lut(nib: int) -> int:
        if nib == 11 and no_spaces:
            return ord("E")
        return _MP_LUT[nib]

    while i < n:
        c = data[i]
        if c == _MP_CMD:
            if i + 1 < n and data[i + 1] == _MP_CMD:
                # 0xFF 0xFF <cmd>
                i += 2
                if i < n:
                    cmd = data[i]
                    i += 1
                    if cmd == _MP_CMD_ENABLE:
                        packing = True
                    elif cmd == _MP_CMD_DISABLE:
                        packing = False
                    elif cmd == _MP_CMD_RESET:
                        packing = False
                        no_spaces = False
                    elif cmd == _MP_CMD_NOSPACES_ON:
                        no_spaces = True
                    elif cmd == _MP_CMD_NOSPACES_OFF:
                        no_spaces = False
                continue
            # lone 0xFF: both nibbles literal → next two bytes are the chars
            i += 1
            if i < n:
                out.append(data[i]); i += 1
            if i < n:
                out.append(data[i]); i += 1
            continue
        i += 1
        if not packing:
            out.append(c)
            continue
        low = c & 0x0F
        high = (c >> 4) & 0x0F
        if low == 0x0F:
            if i < n:
                out.append(data[i]); i += 1
        else:
            out.append(lut(low))
        if high == 0x0F:
            if i < n:
                out.append(data[i]); i += 1
        else:
            out.append(lut(high))
    return bytes(out), packing, no_spaces


# --- block walk + reassembly ------------------------------------------------

def _decompress(comp: int, data: bytes, usize: int) -> bytes:
    if comp == _COMP_NONE:
        return data
    if comp == _COMP_DEFLATE:
        # Cap output (bomb guard): decompress at most _MAX_BLOCK_OUTPUT bytes.
        return zlib.decompressobj().decompress(data, _MAX_BLOCK_OUTPUT)
    if comp == _COMP_HS_11_4:
        return heatshrink_decode(data, 11, 4)
    if comp == _COMP_HS_12_4:
        return heatshrink_decode(data, 12, 4)
    raise ValueError(f"bgcode: unknown compression {comp}")


def decode_bgcode(raw: bytes) -> Dict:
    """Decode a `.bgcode` file to ASCII G-code.

    Returns ``{"gcode": str, "gmap": [(bg_start, bg_end, dec_start, dec_end)],
    "filesize": int}``. ``gmap`` maps each G-code block's byte span in the
    COMPRESSED file to its span in the decoded text, so a print-progress
    fraction (a position in the .bgcode file) can be mapped to the matching
    decoded offset via :func:`progress_to_decoded_fraction`.
    """
    if not is_bgcode(raw):
        raise ValueError("not a bgcode file")
    n = len(raw)
    if n < 10:   # magic(4) + version(4) + checksum_type(2) — truncated header
        return {"gcode": "", "gmap": [], "filesize": n,
                "filament_g": "", "filament_mm": ""}
    checksum_type, = struct.unpack_from("<H", raw, 8)
    off = 10
    parts: List[str] = []
    gmap: List[Tuple[int, int, int, int]] = []
    dec_pos = 0
    mp_packing = False   # MeatPack state threaded across G-code blocks
    mp_no_spaces = False
    footer_g = ""
    footer_mm = ""
    while off < n:
        bg_start = off
        if off + 8 > n:
            break
        btype, comp, usize = struct.unpack_from("<HHI", raw, off)
        off += 8
        csize = None
        if comp != _COMP_NONE:
            if off + 4 > n:
                break
            csize, = struct.unpack_from("<I", raw, off)
            off += 4
        if btype == _BT_THUMBNAIL:
            if off + 6 > n:
                break
            off += 6
            enc = None
        else:
            if off + 2 > n:
                break
            enc, = struct.unpack_from("<H", raw, off)
            off += 2
        dsize = csize if comp != _COMP_NONE else usize
        if dsize < 0:
            break
        data = raw[off:off + dsize]
        off += dsize
        if checksum_type != 0:
            off += 4  # CRC32
        bg_end = off
        # Decompress + decode is wrapped so a single corrupt/truncated block
        # (bad deflate, malformed bitstream) is skipped — the rest of the file
        # (other G-code blocks + the footer) still decodes. gmap uses BYTE
        # offsets to stay consistent with parse_partial_filament_usage, which
        # slices on UTF-8 byte position.
        try:
            if btype == _BT_GCODE:
                block = _decompress(comp, data, usize)
                if enc in (_ENC_MEATPACK, _ENC_MEATPACK_COMMENTS):
                    block, mp_packing, mp_no_spaces = meatpack_decode(
                        block, mp_packing, mp_no_spaces)
                text = block.decode("utf-8", "replace")
                nbytes = len(text.encode("utf-8"))
                gmap.append((bg_start, bg_end, dec_pos, dec_pos + nbytes))
                dec_pos += nbytes
                parts.append(text)
            elif btype in _META_TYPES:
                ini = _decompress(comp, data, usize).decode("utf-8", "replace")
                if "filament used" in ini and not (footer_g and footer_mm):
                    gm = re.search(r"filament used \[g\]\s*=\s*([0-9.,\s]+)", ini)
                    mm = re.search(r"filament used \[mm\]\s*=\s*([0-9.,\s]+)", ini)
                    if gm:
                        footer_g = gm.group(1).strip()
                    if mm:
                        footer_mm = mm.group(1).strip()
        except Exception:
            continue  # skip this block; offsets already advanced

    gcode = "".join(parts)
    # PrusaSlicer stores per-tool 'filament used' in the Print-Metadata block,
    # NOT as G-code comments, when slicing to bgcode. The prefix-parser needs
    # those footers (they give the mm->g ratio), so append them. Appending past
    # all the moves keeps the byte-position map intact (footers carry no E).
    if footer_g and footer_mm:
        gcode += f"\n; filament used [mm] = {footer_mm}\n; filament used [g] = {footer_g}\n"
    # M73 progress markers: PrusaSlicer emits `M73 P{percent} R{minutes}` lines
    # throughout, and the printer's reported `progress` IS this time-based value
    # (NOT a byte position). Capture each marker's (percent, decoded-byte-pos) so
    # progress_to_decoded_fraction can invert progress -> the exact byte reached;
    # a gcode-byte mapping over-counts because progress is time-based, not linear
    # in bytes (validated 2026-06-12 against scale ground truth).
    m73 = []
    bpos = 0
    for line in gcode.splitlines(keepends=True):
        mk = _M73_RE.search(line)
        if mk:
            m73.append((int(mk.group(1)), bpos))
        bpos += len(line.encode("utf-8"))
    return {"gcode": gcode, "gmap": gmap, "filesize": n, "m73": m73,
            "filament_g": footer_g, "filament_mm": footer_mm}


def _m73_byte_for_percent(m73: List[Tuple[int, int]], pct: float) -> int:
    """Interpolate the decoded-byte position for a progress percent from the
    M73 markers ``[(percent, byte_pos)]`` (in file order, percent non-decreasing).
    Linear between bracketing markers; clamps to the ends."""
    if pct <= m73[0][0]:
        return m73[0][1]
    if pct >= m73[-1][0]:
        return m73[-1][1]
    prev = m73[0]
    for cur in m73[1:]:
        if cur[0] >= pct:
            (p0, b0), (p1, b1) = prev, cur
            if p1 == p0:
                return b1
            return int(b0 + (pct - p0) / (p1 - p0) * (b1 - b0))
        prev = cur
    return m73[-1][1]


def progress_to_decoded_fraction(decoded: Dict, progress01: float) -> float:
    """Map a `.bgcode` print-progress fraction (0..1) to the equivalent fraction
    of the DECODED G-code, so `parse_partial_filament_usage` slices at the right
    point.

    PRIMARY (PrusaSlicer files): the printer's reported ``progress`` is the M73
    TIME-based value the slicer embeds (`M73 P{percent}`), NOT a byte position —
    so invert it through the file's own M73 markers (percent -> reached decoded
    byte). This is exact to the slicer's time model: validated 2026-06-12 against
    physical scale weights (51% -> 1.08 g, 76% -> 1.49 g, each matching the
    weighed part + a constant ~0.23 g of startup skirt/prime the spool really
    loses). A raw byte mapping over-counts because progress is time-, not
    byte-, linear.

    FALLBACK (no M73 markers — non-PrusaSlicer gcode): span ``progress`` across
    the G-code blocks' COMPRESSED byte range ``[gmap[0][0], gmap[-1][1]]`` and map
    through the block table. (NOT ``progress * filesize`` — the incompressible PNG
    thumbnail occupies the front of the file, so a whole-file offset collapsed
    every sub-~52% cancel to decoded 0.0, a silent 0 g under-deduction; fixed
    2026-06-12.)"""
    gcode = decoded.get("gcode") or ""
    declen = len(gcode.encode("utf-8"))
    if not gcode or declen <= 0:
        return 0.0
    m73 = decoded.get("m73") or []
    gmap = decoded.get("gmap") or []
    if len(m73) < 2 and not gmap:
        return 0.0  # no G-code body / no position info — nothing was reached
    p = max(0.0, min(1.0, float(progress01)))
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0

    if len(m73) >= 2:
        return min(1.0, _m73_byte_for_percent(m73, p * 100.0) / declen)

    if not gmap:
        return 0.0
    gcode_start, gcode_end = gmap[0][0], gmap[-1][1]
    span = gcode_end - gcode_start
    if span <= 0:
        return p
    target = gcode_start + p * span
    if target <= gmap[0][0]:
        return 0.0
    if target >= gmap[-1][1]:
        return 1.0
    for bg_start, bg_end, dec_start, dec_end in gmap:
        if target < bg_start:
            return dec_start / declen  # in a gap (a metadata block between G-code blocks)
        if bg_start <= target <= bg_end:
            blkspan = bg_end - bg_start
            frac_in = (target - bg_start) / blkspan if blkspan else 0.0
            return (dec_start + frac_in * (dec_end - dec_start)) / declen
    return 1.0
