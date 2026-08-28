"""PNG -> DDS encoding for outfit texture packs.

Outfit Workshop's "paint a PNG" workflow supplies a flat PNG for a slot and
re-encodes it into the slot's BC format on install. This module implements
software BC1 (DXT1) and BC3 (DXT5) encoders in numpy so PNG packs work without
Outfit Workshop or TexEncode.

Animus uses its bundled copy of Microsoft's MIT-licensed DirectXTex
``texconv`` utility for BC1, BC3, and BC7. The in-process BC1/BC3 encoder is
kept as a fallback for development/source checkouts missing the native tool.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


class PngEncodeError(Exception):
    pass


def _load_rgba(path: Path, W: int, H: int):
    with Image.open(path) as im:
        if (im.width, im.height) != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        arr = np.asarray(im.convert("RGBA")).astype(np.uint8)
    return arr


def _pad_to_blocks(rgba: np.ndarray) -> np.ndarray:
    H, W = rgba.shape[:2]
    ph = ((H + 3) // 4) * 4
    pw = ((W + 3) // 4) * 4
    if (H, W) == (ph, pw):
        return rgba
    out = np.zeros((ph, pw, rgba.shape[2]), dtype=np.uint8)
    out[:H, :W] = rgba
    return out


def _encode_bc1(rgba: np.ndarray) -> np.ndarray:
    rgba = _pad_to_blocks(rgba)
    H, W = rgba.shape[:2]
    out = np.empty((H // 4, W // 4, 8), dtype=np.uint8)
    rgb = rgba[..., :3].astype(np.int16)
    for by in range(0, H, 4):
        for bx in range(0, W, 4):
            block = rgb[by:by + 4, bx:bx + 4].reshape(-1, 3)
            out[by // 4, bx // 4] = _dxt1_block(block)
    return out


def _dxt1_block(px) -> np.ndarray:
    lo = px.min(axis=0).astype(np.int16)
    hi = px.max(axis=0).astype(np.int16)
    # If the block is ~single colour, use the 1-bit-alpha palette.
    if (hi - lo).max() < 16:
        c0 = ((lo[0] & 0xF8) << 8) | ((lo[1] & 0xFC) << 3) | (lo[2] >> 3)
        c1 = ((hi[0] & 0xF8) << 8) | ((hi[1] & 0xFC) << 3) | (hi[2] >> 3)
        if c0 <= c1:
            c0, c1 = c1, c0
        colors = _rgb565_palette(c0, c1, single=True)
        idx = _nearest_indices(px, colors)
        bits = 0
        for i in idx:
            bits = (bits << 2) | i
        return np.array([
            c0 & 0xFF, (c0 >> 8) & 0xFF,
            c1 & 0xFF, (c1 >> 8) & 0xFF,
            (bits >> 0) & 0xFF, (bits >> 8) & 0xFF,
            (bits >> 16) & 0xFF, (bits >> 24) & 0xFF,
        ], dtype=np.uint8)

    c0 = ((lo[0] & 0xF8) << 8) | ((lo[1] & 0xFC) << 3) | (lo[2] >> 3)
    c1 = ((hi[0] & 0xF8) << 8) | ((hi[1] & 0xFC) << 3) | (hi[2] >> 3)
    if c0 <= c1:
        c0, c1 = c1, c0
    colors = _rgb565_palette(c0, c1, single=False)
    idx = _nearest_indices(px, colors)
    bits = 0
    for i in idx:
        bits = (bits << 2) | i
    return np.array([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        (bits >> 0) & 0xFF, (bits >> 8) & 0xFF,
        (bits >> 16) & 0xFF, (bits >> 24) & 0xFF,
    ], dtype=np.uint8)


def _encode_bc3(rgba: np.ndarray) -> np.ndarray:
    rgba = _pad_to_blocks(rgba)
    H, W = rgba.shape[:2]
    out = np.empty((H // 4, W // 4, 16), dtype=np.uint8)
    for by in range(0, H, 4):
        for bx in range(0, W, 4):
            block = rgba[by:by + 4, bx:bx + 4]
            out[by // 4, bx // 4] = _dxt5_block(block)
    return out


def _downscale(rgba: np.ndarray, W: int, H: int) -> np.ndarray:
    """Area-average downscale an RGBA array to WxH."""
    if (rgba.shape[1], rgba.shape[0]) == (W, H):
        return rgba
    from PIL import Image
    im = Image.fromarray(rgba)
    return np.asarray(im.resize((W, H), Image.LANCZOS)).astype(np.uint8)


def _dxt5_block(rgba) -> np.ndarray:
    rgb = rgba[..., :3].astype(np.int16).reshape(-1, 3)
    alpha = rgba[..., 3].astype(np.int16).reshape(-1)
    lo = rgb.min(axis=0).astype(np.int16)
    hi = rgb.max(axis=0).astype(np.int16)
    c0 = ((lo[0] & 0xF8) << 8) | ((lo[1] & 0xFC) << 3) | (lo[2] >> 3)
    c1 = ((hi[0] & 0xF8) << 8) | ((hi[1] & 0xFC) << 3) | (hi[2] >> 3)
    if c0 <= c1:
        c0, c1 = c1, c0
    colors = _rgb565_palette(c0, c1, single=False)
    idx = _nearest_indices(rgb, colors)
    bits = 0
    for i in idx:
        bits = (bits << 2) | i

    amin, amax = int(alpha.min()), int(alpha.max())
    if amin == amax:
        a0 = amin; a1 = amin
    else:
        a0 = amax; a1 = amin
    if a0 > a1:
        table = [a0, a1, (6 * a0 + 1 * a1) // 7, (5 * a0 + 2 * a1) // 7,
                 (4 * a0 + 3 * a1) // 7, (3 * a0 + 4 * a1) // 7,
                 (2 * a0 + 5 * a1) // 7, (1 * a0 + 6 * a1) // 7]
        # 8-entry table, 3-bit indices
    else:
        table = [a0, a1, (4 * a0 + 1 * a1) // 5, (3 * a0 + 2 * a1) // 5,
                 (2 * a0 + 3 * a1) // 5, (1 * a0 + 4 * a1) // 5, 0, 255]
    aidx = []
    for a in alpha:
        aidx.append(int(np.argmin(np.abs(np.array(table) - a))))
    abits = 0
    for i in aidx:
        abits = (abits << 3) | i
    # alpha is 2 bytes then 6 bytes; layout DXT5: a0,a1,48 bits alpha (little)
    a_bytes = bytearray(8)
    a_bytes[0] = a0 & 0xFF
    a_bytes[1] = a1 & 0xFF
    for i in range(6):
        a_bytes[2 + i] = (abits >> (8 * i)) & 0xFF
    color_bytes = np.array([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        (bits >> 0) & 0xFF, (bits >> 8) & 0xFF,
        (bits >> 16) & 0xFF, (bits >> 24) & 0xFF,
    ], dtype=np.uint8)
    return np.concatenate([np.frombuffer(bytes(a_bytes), dtype=np.uint8), color_bytes])


def _rgb565_palette(c0, c1, single):
    r0 = ((c0 >> 11) & 0x1F) << 3; g0 = ((c0 >> 5) & 0x3F) << 2; b0 = (c0 & 0x1F) << 3
    r1 = ((c1 >> 11) & 0x1F) << 3; g1 = ((c1 >> 5) & 0x3F) << 2; b1 = (c1 & 0x1F) << 3
    if single:
        return np.array([[r0, g0, b0], [r1, g1, b1], [(r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2],
                         [(r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2]], dtype=np.int16)
    return np.array([[r0, g0, b0], [r1, g1, b1],
                     [(2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3],
                     [(r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3]], dtype=np.int16)


def _nearest_indices(px, colors):
    d = ((px[None, :, :] - colors[:, None, :]) ** 2).sum(axis=2)
    return np.argmin(d, axis=0)


def _dds_header(W: int, H: int, mips: int, fourcc: bytes) -> bytes:
    # Build the canonical 128-byte DDS_HEADER.
    b = bytearray()
    b += struct.pack("<I", 0x20534444)  # "DDS "
    b += struct.pack("<I", 124)
    b += struct.pack("<I", 0x00001007)  # CAPS|HEIGHT|WIDTH|PIXELFORMAT|LINEARSIZE|MIPMAPCOUNT
    b += struct.pack("<I", H)
    b += struct.pack("<I", W)
    b += struct.pack("<I", 0)  # pitchOrLinearSize (filled below)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", mips)
    b += b"\x00" * 44  # reserved1[11]
    # DDS_PIXELFORMAT
    b += struct.pack("<I", 32)
    b += struct.pack("<I", 0x4)  # dwFlags DDPF_FOURCC
    b += fourcc
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    # caps + caps2/3/4 + reserved2 -> total header 128 bytes
    b += b"\x00" * 20
    return bytes(b)


def encode_png_to_dds(path: Path, slot_info) -> bytes:
    """Encode a PNG into a DDS for the given slot family/size."""
    family = getattr(slot_info, "family", None)
    W = getattr(slot_info, "W", None)
    H = getattr(slot_info, "H", None)
    if family in ("BC1", "BC3", "BC7") and _texconv_path().is_file():
        return _encode_directxtex(path, slot_info)
    if family not in ("BC1", "BC3"):
        raise PngEncodeError(
            f"PNG cannot be encoded to {family}. Supply a ready DDS "
            f"for this slot instead (often the normal/surface maps).")
    rgba = _load_rgba(path, W, H)
    block = 8 if family == "BC1" else 16
    fourcc = b"DXT1" if family == "BC1" else b"DXT5"
    # Build the full mip chain so external + embedded mips can be filled.
    chunks = []
    w, h = W, H
    level = 0
    while True:
        mip = _downscale(rgba, w, h)
        if family == "BC1":
            chunks.append(_encode_bc1(mip).tobytes())
        else:
            chunks.append(_encode_bc3(mip).tobytes())
        if w == 1 and h == 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
        level += 1
    blocks = b"".join(chunks)
    mip_count = len(chunks)
    header = _dds_header(W, H, mip_count, fourcc)
    # set pitchOrLinearSize
    header = header[:20] + struct.pack("<I", len(blocks)) + header[24:]
    return header + blocks


def _texconv_path() -> Path:
    return (Path(__file__).resolve().parents[2] / "tools" / "third_party" /
            "directxtex" / "texconv.exe")


def _encode_directxtex(path: Path, slot_info) -> bytes:
    """Encode a PNG to the slot's exact BC format, size, and colour space."""
    exe = _texconv_path()
    if not exe.is_file():
        raise PngEncodeError(
            "Animus' BC7 texture encoder is missing. Reinstall Animus Mod Manager.")

    W = int(getattr(slot_info, "W"))
    H = int(getattr(slot_info, "H"))
    srgb = bool(getattr(slot_info, "srgb", 0))
    family = str(getattr(slot_info, "family"))
    fmt = f"{family}_UNORM{'_SRGB' if srgb else ''}"

    with tempfile.TemporaryDirectory(prefix="animus_bc7_") as temp:
        out_dir = Path(temp)
        args = [
            str(exe), "-nologo", "-y", "--ignore-srgb",
            "-f", fmt, "-w", str(W), "-h", str(H), "-m", "0",
            "-if", "FANT", "-sepalpha", "-o", str(out_dir),
        ]
        # The editable PNG bytes are already gamma-encoded. Marking input and
        # output as sRGB preserves those values while emitting the required
        # BC7_UNORM_SRGB DDS format.
        if srgb:
            args.append("-srgb")
        args.append(str(path))
        try:
            completed = subprocess.run(
                args, check=True, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "DirectXTex failed").strip()
            raise PngEncodeError(f"Could not encode {path.name} as {family}: {detail}") from exc

        output = out_dir / f"{path.stem}.DDS"
        if not output.is_file():
            # DirectXTex normally uses an upper-case extension, but accept
            # either spelling across tool releases.
            output = out_dir / f"{path.stem}.dds"
        if not output.is_file():
            detail = (completed.stdout or completed.stderr or "no DDS was produced").strip()
            raise PngEncodeError(f"Could not encode {path.name} as {family}: {detail}")

        data = output.read_bytes()
        from .texture import parse_dds
        try:
            _mips, out_w, out_h, dxgi, _block = parse_dds(data)
        except ValueError as exc:
            raise PngEncodeError(f"Texture encoder produced an invalid DDS: {exc}") from exc
        expected_dxgi = {
            ("BC1", False): 71, ("BC1", True): 72,
            ("BC3", False): 77, ("BC3", True): 78,
            ("BC7", False): 98, ("BC7", True): 99,
        }[(family, srgb)]
        if (out_w, out_h, dxgi) != (W, H, expected_dxgi):
            raise PngEncodeError(
                f"Texture encoder produced {out_w}x{out_h} DXGI {dxgi}; "
                f"the game slot requires {W}x{H} DXGI {expected_dxgi}.")
        return data
