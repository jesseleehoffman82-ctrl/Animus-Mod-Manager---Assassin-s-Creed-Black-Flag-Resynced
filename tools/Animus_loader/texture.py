"""DDS and material-slot parsing for outfit texture injection.

Turns a DDS file (named with a material id + slot) into a concrete plan of
bytes to write into the FORGE archive: same-size external mips (in-place) and
the embedded mip tail (append-and-repoint).

Pure logic -- no game writes here; the orchestrator in `outfits.py` applies the
plan through a journaled `ForgeArchive`.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from .forge import (
    DXGI,
    ENUM_FAMILY,
    FAMILY_BLOCK,
    ForgeArchive,
    TEXTURE_MAP_HASH,
)

#: Material id patterns found in outfit texture filenames.
RE_IC = re.compile(r"^IC_([0-9A-Fa-f]{9,13})_tm([0-9A-Fa-f]{9,13})_(\d+)_", re.I)
RE_0X = re.compile(r"0x([0-9A-Fa-f]{9,13})")
RE_SLOT = re.compile(r"(?:^|[_\-.])s(?:lot)?(\d+)(?:[_\-.]|$)", re.I)


def parse_filename(name: str) -> tuple[int | None, int | None, str]:
    """Parse a texture filename -> (mat_id, slot, kind) or (None, None, reason)."""
    m = RE_IC.match(name)
    if m:
        return int(m.group(1), 16), int(m.group(3)), "IC_export"
    m = RE_0X.search(name)
    if m:
        mat = int(m.group(1), 16)
        s = RE_SLOT.search(name)
        if s:
            return mat, int(s.group(1)), "0x+slot"
        return mat, 0, "0x-no-slot"
    return None, None, "no material id found"


def parse_dds(dds: bytes):
    """Parse a DDS into (mips, W, H, dxgi, block).

    mips is a list of dicts: {lvl, veri, w, h}.
    """
    if dds[:4] != b"DDS ":
        raise ValueError("not a DDS file")
    H = struct.unpack_from("<I", dds, 12)[0]
    W = struct.unpack_from("<I", dds, 16)[0]
    fc = dds[84:88]
    if fc == b"DX10":
        dxgi = struct.unpack_from("<I", dds, 128)[0]
        data_off = 148
    else:
        dxgi = {b"DXT1": 71, b"DXT3": 74, b"DXT5": 77}.get(fc, 0)
        data_off = 128
    if dxgi not in DXGI:
        raise ValueError(f"unsupported texture format (DXGI={dxgi})")
    block = DXGI[dxgi][0]
    mips = []
    off = data_off
    w, h = W, H
    while off < len(dds):
        n = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
        if off + n > len(dds):
            break
        mips.append({"lvl": len(mips), "veri": dds[off:off + n], "w": w, "h": h})
        if w == 1 and h == 1:
            break
        off += n
        w = max(1, w // 2)
        h = max(1, h // 2)
    return mips, W, H, dxgi, block


@dataclass
class Slot:
    """A single TextureMap descriptor inside a decompressed material."""

    mat: int
    slot: int
    tex: int
    hdr: int
    W: int
    H: int
    fmt_enum: int
    srgb: int
    mipcount: int
    family: str | None
    block: int | None


def find_slots(res: bytes) -> list[tuple[int, int]]:
    """Return sorted [(descriptor_offset, texture_id)] for every TextureMap."""
    out = []
    pat = struct.pack("<I", TEXTURE_MAP_HASH)
    i = res.find(pat)
    while i >= 0:
        if i >= 9 and i + 5 <= len(res) and res[i + 4] == 0x01:
            g = struct.unpack_from("<Q", res, i - 8)[0]
            if 0x10000000 < g < 0xFFFFFFFFFFFFF:
                out.append((i - 9, g))
        i = res.find(pat, i + 1)
    return sorted(out)


def read_slot(res: bytes, mat: int, slot: int, slots: list[tuple[int, int]] | None = None) -> Slot:
    slots = slots or find_slots(res)
    if slot >= len(slots):
        raise ValueError(f"there is no slot {slot} here (this material has {len(slots)} textures)")
    hdr, tex = slots[slot]
    W = struct.unpack_from("<I", res, hdr + 14)[0]
    H = struct.unpack_from("<I", res, hdr + 18)[0]
    fmt_enum = struct.unpack_from("<I", res, hdr + 30)[0]
    srgb = struct.unpack_from("<I", res, hdr + 38)[0]
    mipcount = struct.unpack_from("<I", res, hdr + 42)[0]
    family = ENUM_FAMILY.get(fmt_enum)
    return Slot(mat, slot, tex, hdr, W, H, fmt_enum, srgb, mipcount, family,
                FAMILY_BLOCK.get(family) if family else None)


def _align(x: int, a: int = 256) -> int:
    return ((x + a - 1) // a) * a


def _find_embedded(res: bytes, data_start: int, data_end: int, tol: int = 64):
    """Locate the embedded pixel tail's u32 length marker.

    Returns (marker_offset, pixel_start, length) or None.
    """
    ic_len = data_end - data_start
    best = None
    for q in range(data_start, max(data_start, min(data_start + 4096, data_end - 4))):
        v = struct.unpack_from("<I", res, q)[0]
        if not (10000 < v < ic_len):
            continue
        end = q + 4 + v
        if end <= data_end and (data_end - end) <= tol:
            if best is None or v > best[2]:
                best = (q, q + 4, v)
    return best


def _layout(W: int, block: int, first_level: int, length: int):
    """Compute the embedded mip layout: [(lvl, rel_off, pitch, rows, rowbytes)]."""
    out = []
    off = 0
    w = max(1, W >> first_level)
    lvl = first_level
    while w >= 1:
        bw = max(1, (w + 3) // 4)
        rowbytes = bw * block
        pitch = _align(rowbytes, 256)
        n = pitch * bw
        if off + n > length:
            break
        out.append((lvl, off, pitch, bw, rowbytes))
        off += n
        if w == 1:
            break
        w //= 2
        lvl += 1
    return out, off


@dataclass
class ExternalMip:
    lvl: int
    rid: int
    offset: int
    forge_len: int
    data: bytes
    w: int
    h: int


@dataclass
class EmbeddedTail:
    pixel_start: int
    length: int
    first_level: int
    layout: list
    used: int


@dataclass
class PlanItem:
    """A resolved, validated outfit texture ready to inject."""

    filename: str
    mat: int
    slot: int
    tex: int
    slot_info: Slot
    mips: list
    external: list[ExternalMip] = field(default_factory=list)
    embedded: EmbeddedTail | None = None

    @property
    def material_res_len(self) -> int:
        return 0  # filled in by the orchestrator


def plan_texture(archive: ForgeArchive, mat: int, slot: int, dds: bytes,
                 filename: str = "outfit.dds") -> PlanItem:
    """Validate a DDS against a material slot and build the inject plan."""
    if not archive.has(mat):
        raise ValueError(f"material 0x{mat:X} is not in this game archive")
    res = archive.read_material(mat)
    slots = find_slots(res)
    slot_info = read_slot(res, mat, slot, slots)
    if slot_info.family is None:
        raise ValueError(f"unknown texture format in the archive (enum 0x{slot_info.fmt_enum:X})")

    mips, W, H, dxgi, block = parse_dds(dds)
    dxgi_block, dxgi_srgb, dxgi_family = DXGI[dxgi]

    # Size gate.
    if (W, H) != (slot_info.W, slot_info.H):
        raise ValueError(
            f"the image is {W}x{H} but this slot needs {slot_info.W}x{slot_info.H}")
    # Format family + colour-space gate.
    if dxgi_family != slot_info.family:
        raise ValueError(f"this file is {dxgi_family} but the slot needs {slot_info.family}")
    if dxgi_srgb != slot_info.srgb:
        raise ValueError(
            f"colour space mismatch: slot needs {slot_info.family}{'_sRGB' if slot_info.srgb else ''}")

    # External mips (same-size in-place writes).
    base = (0xA0000000000 | slot_info.tex) << 20
    external: list[ExternalMip] = []
    for lvl in range(slot_info.mipcount):
        rid = base | lvl
        if not archive.has(rid):
            continue
        off, ln, _ = archive.offset_of(rid)
        dm = next((m for m in mips if m["lvl"] == lvl), None)
        if not dm or ln != len(dm["veri"]):
            raise ValueError(
                f"size gate: encoded mip{lvl} does not fit the reserved space "
                f"(archive={ln}, file={len(dm['veri']) if dm else 'none'})")
        external.append(ExternalMip(lvl, rid, off, ln, dm["veri"], dm["w"], dm["h"]))

    # Embedded tail (append-and-repoint).
    data_start = slot_info.hdr + 14
    data_end = slots[slot + 1][0] if slot + 1 < len(slots) else len(res)
    c = _find_embedded(res, data_start, data_end)
    embedded = None
    if c:
        marker_off, pixel_start, length = c
        first_level = len(external)
        layout, used = _layout(slot_info.W, slot_info.block, first_level, length)
        embedded = EmbeddedTail(pixel_start, length, first_level, layout, used)

    return PlanItem(filename, mat, slot, slot_info.tex, slot_info, mips,
                    external, embedded)
