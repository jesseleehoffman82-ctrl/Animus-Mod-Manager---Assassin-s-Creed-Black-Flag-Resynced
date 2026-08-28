"""End-to-end test of the outfit library + FORGE texture injector.

Builds a small synthetic `scimitar` FORGE archive with one material that has a
single TextureMap (128x128 BC3) whose external mips (lvl 0,1) live in the TOC
and whose remaining mips (lvl 2..7) live in an embedded pixel tail. Then:

  1. imports an outfit pack (a DDS) into the library,
  2. switches it active (injects external mips in place + re-packs the embedded
     tail and repoints the material's TOC),
  3. reverts it and checks the forge is byte-for-byte restored.

Uses an UNCOMPRESSED material so no Oodle dll is needed (the pipeline handles
non-BMS materials as passthrough).
"""

from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from Animus_loader import outfits  # noqa: E402
from Animus_loader.forge import ForgeArchive, Oodle  # noqa: E402
from Animus_loader.texture import parse_dds, plan_texture  # noqa: E402
from Animus_loader.packs import CATEGORY_OUTFIT, CATEGORY_WEAPON, PackManager  # noqa: E402

TEST_ROOT = Path(__file__).resolve().parent / "_test_outfits"
GAME_DIR = TEST_ROOT / "game"
MODS_ROOT = TEST_ROOT / "mods"
FORGE = GAME_DIR / "DataPC_boot.forge"

MAT = 0x2128A456A2D
TEX = 0x257340FC0BE
W = H = 128
BLOCK = 16  # BC3


def mip_len(w: int, h: int) -> int:
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK


def build_material_res():
    """A single-slot BC3 material with an embedded pixel tail (marker after
    the descriptor, matching how real materials lay out W/H/fmt then data)."""
    marker_off = 46
    payload = 12000
    res = bytearray(marker_off + 4 + payload + 20)
    # descriptor at hdr=0: g at +1, hash at +9, 0x01 at +13
    struct.pack_into("<Q", res, 1, TEX)
    struct.pack_into("<I", res, 9, 0xA2B7E917)
    res[13] = 0x01
    struct.pack_into("<I", res, 14, W)
    struct.pack_into("<I", res, 18, H)
    struct.pack_into("<I", res, 30, 0x05)   # BC3
    struct.pack_into("<I", res, 38, 0)      # sRGB
    struct.pack_into("<I", res, 42, 8)      # mipcount
    # embedded pixel tail marker + payload
    struct.pack_into("<I", res, marker_off, payload)
    for i in range(marker_off + 4, marker_off + 4 + payload):
        res[i] = (i * 7) & 0xFF
    return bytes(res), marker_off + 4


def build_dds(external, embedded):
    """Build a BC3 DDS with 8 mips; mips 0,1 -> external bytes, 2..7 embedded."""
    miplens = [mip_len(W >> l, H >> l) for l in range(8)]
    mips = []
    for l, ln in enumerate(miplens):
        if l < 2:
            mips.append(external[l])
        else:
            mips.append(embedded[l])
    data = b"".join(mips)
    b = bytearray()
    b += struct.pack("<I", 0x20534444)
    b += struct.pack("<I", 124)
    b += struct.pack("<I", 0x00001007)
    b += struct.pack("<I", H)
    b += struct.pack("<I", W)
    b += struct.pack("<I", len(data))
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 8)
    b += b"\x00" * 44
    b += struct.pack("<I", 32)
    b += struct.pack("<I", 0x4)
    b += b"DXT5"
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    b += struct.pack("<I", 0)
    # caps (4) + caps2/3/4 (12) + reserved2 (4) = 20 bytes -> total 128
    b += b"\x00" * 20
    return bytes(b) + data


def build_forge():
    """Build the scimitar archive: header + TOC + material + 2 external mips."""
    material, pixel_start = build_material_res()
    ext0 = bytes((i * 11) & 0xFF for i in range(mip_len(W, H)))
    ext1 = bytes((i * 13) & 0xFF for i in range(mip_len(W >> 1, H >> 1)))

    # rids: external mip0, mip1; material
    rid_ext0 = (0xA0000000000 | TEX) << 20 | 0
    rid_ext1 = (0xA0000000000 | TEX) << 20 | 1
    entries = [  # (fid, data)
        (MAT, material),
        (rid_ext0, ext0),
        (rid_ext1, ext1),
    ]
    # Sort so TOC order matches our dict assumptions (any order is fine).
    header_len = 64
    count = len(entries)
    hoff = header_len
    toc_off = hoff + 12
    data_off = toc_off + count * 24

    blob = bytearray(b"\x00" * data_off)
    blob[0:8] = b"scimitar"
    struct.pack_into("<Q", blob, 13, hoff)

    # header block at hoff
    blob[hoff:hoff + 12] = struct.pack("<IQ", count, toc_off)

    # TOC rows
    cur = data_off
    for i, (fid, data) in enumerate(entries):
        struct.pack_into("<QQII", blob, toc_off + i * 24, cur, fid, len(data), 0x272E1126)
        cur += len(data)

    for _, data in entries:
        blob.extend(data)
    FORGE.write_bytes(bytes(blob))
    return material, ext0, ext1, pixel_start


def main() -> int:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    GAME_DIR.mkdir(parents=True)
    MODS_ROOT.mkdir(parents=True)

    material, ext0, ext1, pixel_start = build_forge()
    orig = FORGE.read_bytes()

    mgr = outfits.OutfitManager(game_dir=GAME_DIR, mods_root=MODS_ROOT)

    # Build an outfit pack folder with a DDS.
    src = TEST_ROOT / "pack" / "EdwardRobes"
    src.mkdir(parents=True)
    dds = build_dds([ext0, ext1], {
        2: bytes((0x20 + i) & 0xFF for i in range(mip_len(32, 32))),
        3: bytes((0x40 + i) & 0xFF for i in range(mip_len(16, 16))),
        4: bytes((0x60 + i) & 0xFF for i in range(mip_len(8, 8))),
        5: bytes((0x80 + i) & 0xFF for i in range(mip_len(4, 4))),
        6: bytes((0xA0 + i) & 0xFF for i in range(mip_len(2, 2))),
        7: bytes((0xC0 + i) & 0xFF for i in range(mip_len(1, 1))),
    })
    (src / f"hood_0x{MAT:X}_slot0.dds").write_bytes(dds)

    # 1. Import.
    outfit = mgr.import_outfit(src, name="Edward's Robes")
    assert len(outfit.slots) == 1 and outfit.slots[0].mat == MAT
    assert len(mgr.list_outfits()) == 1

    # 2. Switch active -> apply.
    result = mgr.switch_outfit(outfit.id)
    assert result["applied"] and result["applied"]["external_mips"] == 2

    # Verify external mips were written in place.
    archive = ForgeArchive(FORGE, Oodle(GAME_DIR))
    rid0 = (0xA0000000000 | TEX) << 20 | 0
    rid1 = (0xA0000000000 | TEX) << 20 | 1
    assert archive.read_raw(rid0) == ext0
    assert archive.read_raw(rid1) == ext1

    # Verify material TOC was repointed (new entry appended) and the embedded
    # tail was patched to the DDS data using the expected layout.
    off, ln = archive.read_toc_row(MAT)
    assert ln == len(material), "material length should stay the same"
    new_res = archive.read_material(MAT)
    # Check the first embedded level (lvl2, 32x32) region matches the DDS data.
    dds_lvl2 = dds_data_at(dds, 2)
    pitch = 256
    rows = (32 + 3) // 4    # 8
    rb = (32 + 3) // 4 * 16  # 128
    for r in range(rows):
        start = pixel_start + r * pitch
        assert new_res[start:start + rb] == dds_lvl2[r * rb:(r + 1) * rb], \
            f"embedded lvl2 row {r} not patched correctly"
    # And that the new material differs from the original (embedded changed).
    assert new_res != material, "material should have changed after apply"

    assert mgr.active_outfit() == outfit.id

    # 3. Revert.
    rev = mgr.revert_all()
    assert rev["reverted"] >= 1
    assert FORGE.read_bytes() == orig, "forge not restored to original bytes"
    assert mgr.active_outfit() is None
    assert mgr._load_journal() is None

    # 4. PNG pack import: PNG is encoded to a DDS in the library and validates.
    import numpy as np
    from PIL import Image
    png_src = TEST_ROOT / "pack_png" / "Painted"
    png_src.mkdir(parents=True)
    png_arr = np.zeros((W, H, 3), dtype=np.uint8)
    png_arr[..., 0] = 90
    png_arr[..., 1] = 140
    png_arr[..., 2] = 30
    Image.fromarray(png_arr).save(png_src / f"hood_0x{MAT:X}_slot0.png")
    png_outfit = mgr.import_outfit(png_src, name="Painted Outfit")
    assert len(png_outfit.slots) == 1, "PNG pack should import 1 slot"
    stored = png_outfit.dir / "textures" / f"0x{MAT:X}_slot0.dds"
    assert stored.is_file()
    archive = ForgeArchive(FORGE, Oodle(GAME_DIR))
    plan = plan_texture(archive, MAT, 0, stored.read_bytes(), stored.name)
    assert len(plan.external) == 2, "encoded PNG should plan 2 external mips"

    # 5. Weapon pack: same engine, different category. Verify shared active set.
    pmgr = PackManager(game_dir=GAME_DIR, mods_root=MODS_ROOT)
    wep_src = TEST_ROOT / "pack_wep" / "Sword"
    wep_src.mkdir(parents=True)
    (wep_src / f"sword_0x{MAT:X}_slot0.dds").write_bytes(dds)
    wep = pmgr.import_pack(wep_src, name="Sword Skin", category=CATEGORY_WEAPON)
    assert len(pmgr.list_packs(category=CATEGORY_WEAPON)) == 1
    assert len(pmgr.list_packs(category="outfit")) == 2  # both outfits still listed

    # Activate a weapon -> it must revert the active outfit (single active set).
    assert mgr.active_outfit() is None  # PNG pack was imported, not activated
    result = pmgr.switch_pack(wep.id)
    assert result["applied"], "weapon should apply"
    assert pmgr.active_pack_id() == wep.id
    assert mgr.active_outfit() is None or mgr.active_outfit() != outfit.id

    # Switching back to an outfit reverts the weapon (no conflicts).
    result2 = mgr.switch_outfit(outfit.id)
    assert result2["applied"], "outfit should apply after weapon"
    assert result2["reverted"], "switching to outfit must revert the active weapon"
    assert pmgr.active_pack_id() == outfit.id
    assert mgr.active_outfit() == outfit.id

    # 6. Final revert to vanilla.
    rev = pmgr.revert_all()
    assert FORGE.read_bytes() == orig, "forge not restored to original bytes after weapon/outfit cycle"
    assert pmgr._load_journal() is None
    assert pmgr.active_pack_id() is None

    # 7. One-click install from a .zip archive (the Nexus download shape).
    import zipfile
    zsrc = TEST_ROOT / "pack_zip" / "download"
    zdir = zsrc / "assin_black_flag" / "outfit"
    zdir.mkdir(parents=True)
    (zdir / f"hood_0x{MAT:X}_slot0.dds").write_bytes(dds)  # nested in subfolders
    zip_path = TEST_ROOT / "outfitpack.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for sub in zdir.rglob("*"):
            if sub.is_file():
                z.write(sub, sub.relative_to(zsrc).as_posix())
    result = pmgr.install(zip_path, name="Zip Outfit", category=CATEGORY_OUTFIT)
    zip_pack_id = result["pack"].id
    assert result["active_id"] == result["pack"].id, "install should activate the pack"
    assert mgr.active_outfit() == result["pack"].id, "outfit view should show same active"
    assert pmgr.active_pack_id() == result["pack"].id
    # the zip's texture made it into the library + was injected
    assert pmgr.list_packs(category=CATEGORY_OUTFIT)
    assert pmgr._load_journal() is not None

    # Revert to end clean.
    pmgr.revert_all()
    assert FORGE.read_bytes() == orig, "forge not restored after zip install revert"
    assert pmgr.active_pack_id() is None

    # 8. MO2-style staged apply: enable TWO packs touching the same slot, the
    #    bottom-most (higher priority) wins; disable one -> re-apply clean.
    a = mgr.import_outfit(src, name="Outfit A")
    b = mgr.import_outfit(png_src, name="Outfit B")   # different bytes, same slot
    pmgr.set_enabled(zip_pack_id, False)  # disable the earlier zip outfit
    pmgr.set_enabled(a.id, True)
    pmgr.set_enabled(b.id, True)
    # Order: [a, b] -> b is bottom (highest priority) and should win slot0.
    pmgr.set_order(CATEGORY_OUTFIT, [a.id, b.id])
    staged = pmgr._staged(CATEGORY_OUTFIT)
    assert staged == [a.id, b.id], f"staged order wrong: {staged}"
    res = pmgr.apply_staged(CATEGORY_OUTFIT)
    assert res["external_mips"] == 2, "one slot should be injected (merged, not duplicated)"
    assert len(res["conflicts"]) == 1, "should report 1 conflict (two packs, one slot)"
    assert res["conflicts"][0]["winner"] == "Outfit B", "bottom-most pack should win"

    archive = ForgeArchive(FORGE, Oodle(GAME_DIR))
    rid0 = (0xA0000000000 | TEX) << 20 | 0
    # b (Outfit B) is the PNG-encoded pack: verify its mip0 won.
    b_tex = b.dir / "textures" / f"0x{MAT:X}_slot0.dds"
    b_mips, *_ = parse_dds(b_tex.read_bytes())
    assert archive.read_raw(rid0) == b_mips[0]["veri"], "winner pack's texture should be in the forge"

    # Disable b -> re-apply -> a wins.
    pmgr.set_enabled(b.id, False)
    res2 = pmgr.apply_staged(CATEGORY_OUTFIT)
    assert res2["external_mips"] == 2
    assert not res2["conflicts"], "no conflict after disabling b"
    a_tex = a.dir / "textures" / f"0x{MAT:X}_slot0.dds"
    a_mips, *_ = parse_dds(a_tex.read_bytes())
    assert archive.read_raw(rid0) == a_mips[0]["veri"], "a should win after b disabled"

    # Disabling the final staged pack and applying must restore vanilla; the UI
    # uses this path for its immediate enable/disable checkboxes.
    pmgr.set_enabled(a.id, False)
    empty = pmgr.apply_staged()
    assert not empty["packs"]
    assert FORGE.read_bytes() == orig, "disabling final pack must restore vanilla"
    assert pmgr._load_journal() is None

    # An explicit final revert remains harmless when already vanilla.
    pmgr.revert_all()
    assert FORGE.read_bytes() == orig, "forge not restored after staged apply/revert"
    assert pmgr._load_journal() is None

    # 9. Per-pack revert: apply ONE pack and revert it cleanly.
    # First clear any leftover enabled packs from earlier sections.
    for pid in list(pmgr._staged(CATEGORY_OUTFIT)):
        pmgr.set_enabled(pid, False)
    pmgr2 = PackManager(game_dir=GAME_DIR, mods_root=MODS_ROOT)
    a2 = mgr.import_outfit(src, name="Outfit C")
    pmgr2.set_enabled(a2.id, True)
    pmgr2.apply_staged(CATEGORY_OUTFIT)
    rid0b = (0xA0000000000 | TEX) << 20 | 0
    a2_mips, *_ = parse_dds((a2.dir / "textures" / f"0x{MAT:X}_slot0.dds").read_bytes())
    arch2 = ForgeArchive(FORGE, Oodle(GAME_DIR))
    assert arch2.read_raw(rid0b) == a2_mips[0]["veri"], "a2 should be injected"
    res_p = pmgr2.revert_pack(a2.id)
    assert res_p["reverted"] >= 2, f"revert_pack should restore external mips: {res_p}"
    assert pmgr2._load_journal() is None, "journal should be gone after reverting only pack"
    assert FORGE.read_bytes() == orig, "forge must be vanilla after per-pack revert of sole pack"

    print("OUTFIT TESTS PASSED")
    return 0


def dds_data_at(dds: bytes, lvl: int) -> bytes:
    mips, _, _, _, _ = parse_dds(dds)
    return mips[lvl]["veri"]


if __name__ == "__main__":
    raise SystemExit(main())
