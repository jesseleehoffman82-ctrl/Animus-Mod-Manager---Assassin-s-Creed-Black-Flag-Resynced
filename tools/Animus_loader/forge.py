"""Black Flag Resynced FORGE archive backend.

Reverse-engineered from the game's `scimitar` archives and Outfit Workshop's
reference implementation. Provides:

  * ForgeArchive   -- read the TOC and a raw resource by id
  * Oodle          -- load the game's oo2core dll and compress/decompress
  * BMS block      -- decompress a material blob and re-pack one after edits

Only touched on the outfit install path; the main mod loader keeps using the
existing byte-patch/loose-file backends in `core.py`.
"""

from __future__ import annotations

import ctypes
import os
import struct
import zlib
from pathlib import Path

#: Magic that identifies a Black Flag `scimitar` FORGE archive header.
FORGE_MAGIC = b"scimitar"

#: Signature of the compressed resource container (BMS blocks).
BMS_MAGIC = b"\x33\xAA\xFB\x57\x99\xFA\x04\x10"

#: TextureMap class hash used to find slot descriptors inside a material.
TEXTURE_MAP_HASH = 0xA2B7E917

#: DXGI format enum -> (bytes-per-block, sRGB, family).
DXGI = {
    71: (8, 0, "BC1"), 72: (8, 1, "BC1"),
    74: (16, 0, "BC2"), 75: (16, 1, "BC2"),
    77: (16, 0, "BC3"), 78: (16, 1, "BC3"),
    80: (8, 0, "BC4"), 83: (16, 0, "BC5"),
    95: (16, 0, "BC6H"),
    98: (16, 0, "BC7"), 99: (16, 1, "BC7"),
}

#: Material descriptor format enum -> texture family.
ENUM_FAMILY = {0x02: "BC1", 0x03: "BC1", 0x05: "BC3", 0x0A: "BC7"}

#: bytes-per-block per family.
FAMILY_BLOCK = {"BC1": 8, "BC2": 16, "BC3": 16, "BC4": 8, "BC5": 16, "BC6H": 16, "BC7": 16}


class ForgeError(Exception):
    """Raised for forge-format or archive problems."""


def _find_oodle_dll(game_dir: Path, env: str = "OODLE_DLL") -> Path | None:
    """Locate an oo2core dll. Prefers the game's own copy (always present)."""
    candidates: list[Path] = []
    ev = os.environ.get(env)
    if ev:
        candidates.append(Path(ev))
    if game_dir:
        candidates.append(game_dir / "oo2core_9_win64.dll")
        candidates.append(game_dir / "oo2core_7_win64.dll")
        candidates.append(game_dir / "oo2core_8_win64.dll")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class Oodle:
    """Thin wrapper around the game's Oodle DLL (compress + decompress).

    The DLL is loaded lazily on first use so constructing an archive for
    read-only or non-compressed synthetic work never fails.
    """

    def __init__(self, game_dir: Path):
        self._path = _find_oodle_dll(game_dir)
        self._decompress = None
        self._compress = None

    def _ensure(self):
        if self._decompress is not None:
            return
        if self._path is None:
            raise ForgeError(
                "Could not find oo2core dll next to the game. This is required to "
                "read and write the outfit textures inside the FORGE archives."
            )
        lib = ctypes.CDLL(str(self._path))
        self._decompress = lib.OodleLZ_Decompress
        self._decompress.restype = ctypes.c_longlong
        self._decompress.argtypes = [
            ctypes.c_char_p, ctypes.c_longlong, ctypes.c_char_p, ctypes.c_longlong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_longlong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_longlong, ctypes.c_int,
        ]
        self._compress = lib.OodleLZ_Compress
        self._compress.restype = ctypes.c_int
        self._compress.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_size_t,
        ]

    def decompress(self, data: bytes, raw_len: int) -> bytes | None:
        self._ensure()
        out = ctypes.create_string_buffer(raw_len + 64)
        n = self._decompress(data, len(data), out, raw_len, 1, 0, 0, None, 0,
                             None, None, None, 0, 3)
        return out.raw[:raw_len] if n == raw_len else None

    def compress(self, data: bytes, codec: int = 9, level: int = 6) -> bytes:
        self._ensure()
        out = ctypes.create_string_buffer(len(data) + 65536)
        n = self._compress(codec, data, len(data), out, level, None, None, None, None, 0)
        if n <= 0:
            raise ForgeError("Oodle compression failed")
        return out.raw[:n]


def _read_bms_block(data: bytes, off: int, oodle: Oodle):
    """Decompress one BMS block at `off`. Returns (payload, next_offset) or
    (None, off) if the block magic is not present."""
    if data[off:off + 8] != BMS_MAGIC:
        return None, off
    p = off + 8
    ver = struct.unpack_from("<H", data, p)[0]
    p += 2
    p += 1 + 4  # skip 1 byte + 4 bytes (unknown header fields)
    t = struct.unpack_from("<I", data, p)[0]
    if t >= 0x10000:
        pc = struct.unpack_from("<H", data, p)[0]
        p += 2
    else:
        pc = t
        p += 4
    sizes = []
    for _ in range(pc):
        if ver <= 1:
            sizes.append((struct.unpack_from("<H", data, p)[0], struct.unpack_from("<H", data, p + 2)[0]))
            p += 4
        else:
            sizes.append((struct.unpack_from("<I", data, p)[0], struct.unpack_from("<I", data, p + 4)[0]))
            p += 8
    payload = bytearray()
    cur = p
    for raw_len, comp_len in sizes:
        chunk = data[cur + 4:cur + 4 + comp_len]
        if comp_len == raw_len:
            payload += chunk
        else:
            decoded = oodle.decompress(chunk, raw_len)
            if decoded is None:
                raise ForgeError("Oodle decompression of a FORGE block failed")
            payload += decoded
        cur += 4 + comp_len
    return bytes(payload), cur


def decompress_bms(data: bytes, oodle: Oodle) -> bytes:
    """Decompress a material blob. Returns raw if it has no BMS wrapper."""
    if data[:8] != BMS_MAGIC:
        return data
    b1, n1 = _read_bms_block(data, 0, oodle)
    b2, _ = _read_bms_block(data, n1, oodle)
    return b2 if b2 is not None else b1


def compress_material(raw: bytes, res: bytes, oodle: Oodle) -> bytes:
    """Re-pack a decompressed material `res` into the archive's compressed form.

    Keeps the original block1 header + piece boundaries so the archive stays
    structurally identical, re-compressing only the changed pieces.
    """
    b1, n1 = _read_bms_block(raw, 0, oodle)
    if b1 is None:
        # Material was stored uncompressed; just return res directly.
        return res
    block1 = raw[0:n1]
    hdr = raw[n1:n1 + 19]
    pc = struct.unpack_from("<I", raw, n1 + 15)[0]
    sizes_raw = []
    q = n1 + 19
    for _ in range(pc):
        u, c = struct.unpack_from("<II", raw, q)
        q += 8
        sizes_raw.append(u)
    if sum(sizes_raw) != len(res):
        raise ForgeError("Material piece sizes do not match after edit")
    pieces = []
    o = 0
    for u in sizes_raw:
        piece = res[o:o + u]
        o += u
        comp = oodle.compress(piece)
        if len(comp) >= u:
            comp = piece
        pieces.append((u, comp))
    sizes = b"".join(struct.pack("<II", u, len(c)) for u, c in pieces)
    body = b"".join(
        struct.pack("<I", zlib.adler32(c) & 0xFFFFFFFF) + c for u, c in pieces
    )
    return block1 + hdr + sizes + body


class ForgeArchive:
    """Reader for the `scimitar` FORGE archive header and TOC.

    Read-only: the outfit install path applies edits through this object but
    writes via explicit helper methods so every mutation can be journaled.
    """

    def __init__(self, path: Path, oodle: Oodle):
        self.path = Path(path)
        self.oodle = oodle
        self._entries: dict[int, tuple[int, int, int]] = {}
        self._row_offset: dict[int, int] = {}
        self._toc_offset = 0
        self._load()

    def _load(self) -> None:
        with self.path.open("rb") as handle:
            hdr = handle.read(64)
            if hdr[:8] != FORGE_MAGIC:
                raise ForgeError(f"{self.path.name} is not a scimitar FORGE archive")
            hoff = struct.unpack_from("<Q", hdr, 13)[0]
            handle.seek(hoff)
            head = handle.read(12)
            count = struct.unpack_from("<I", head, 0)[0]
            self._toc_offset = struct.unpack_from("<Q", head, 4)[0]
            handle.seek(self._toc_offset)
            toc_bytes = handle.read(count * 24)
        self._entries = {}
        self._row_offset = {}
        for i in range(count):
            off, fid, ln, ext = struct.unpack_from("<QQII", toc_bytes, i * 24)
            self._entries[fid] = (off, ln, ext)
            self._row_offset[fid] = self._toc_offset + i * 24

    @property
    def entries(self) -> dict[int, tuple[int, int, int]]:
        return dict(self._entries)

    def has(self, fid: int) -> bool:
        return fid in self._entries

    def offset_of(self, fid: int) -> tuple[int, int, int]:
        if fid not in self._entries:
            raise ForgeError(f"resource 0x{fid:X} is not in {self.path.name}")
        return self._entries[fid]

    def read_raw(self, fid: int) -> bytes:
        off, ln, _ = self.offset_of(fid)
        with self.path.open("rb") as handle:
            handle.seek(off)
            return handle.read(ln)

    def read_material(self, fid: int) -> bytes:
        return decompress_bms(self.read_raw(fid), self.oodle)

    def toc_entry_offset(self, fid: int) -> int:
        """Absolute file offset of the 24-byte TOC row for a resource id."""
        if fid not in self._row_offset:
            raise ForgeError(f"resource 0x{fid:X} is not in {self.path.name}")
        return self._row_offset[fid]

    # ------------------------------------------------------------------ #
    # low-level write primitives (used by the journaled injector)
    # ------------------------------------------------------------------ #
    def read_at(self, offset: int, length: int) -> bytes:
        with self.path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(length)

    def write_at(self, offset: int, data: bytes) -> None:
        with self.path.open("r+b") as handle:
            handle.seek(offset)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def read_toc_row(self, fid: int) -> tuple[int, int]:
        """Return the (offset, length) currently recorded for a resource id."""
        row = self.toc_entry_offset(fid)
        data = self.read_at(row, 24)
        return (struct.unpack_from("<Q", data, 0)[0],
                struct.unpack_from("<I", data, 16)[0])

    def append_block(self, data: bytes) -> int:
        """Append `data` to the end of the archive; returns its offset."""
        with self.path.open("r+b") as handle:
            handle.seek(0, os.SEEK_END)
            new_off = handle.tell()
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return new_off

    def repoint_toc(self, fid: int, new_off: int, new_len: int) -> None:
        """Repoint a resource's TOC entry to a new offset/length."""
        row = self.toc_entry_offset(fid)
        with self.path.open("r+b") as handle:
            handle.seek(row)
            handle.write(struct.pack("<Q", new_off))
            handle.seek(row + 16)
            handle.write(struct.pack("<I", new_len))
            handle.flush()
            os.fsync(handle.fileno())

    def truncate(self, length: int) -> None:
        with self.path.open("r+b") as handle:
            handle.truncate(length)

    def size(self) -> int:
        return self.path.stat().st_size
