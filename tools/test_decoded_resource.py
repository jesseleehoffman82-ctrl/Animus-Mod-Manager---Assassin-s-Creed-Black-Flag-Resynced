"""Offline decoded-resource install/restore test using a synthetic FORGE."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from Animus_loader import Loader  # noqa: E402


TEST_ROOT = Path(__file__).resolve().parent / "_test_decoded"
GAME_DIR = TEST_ROOT / "game"
MODS_ROOT = TEST_ROOT / "mods"
RESOURCE_ID = 0x22599A4A978
ORIGINAL = b"ORIGINAL-STORED-BLOCK"
REPLACEMENT = b"REPLACEMENT-RESOURCE!"


def build_forge(path: Path) -> tuple[int, bytes]:
    assert len(ORIGINAL) == len(REPLACEMENT)
    header_table_offset = 0x40
    toc_offset = 0x60
    payload_offset = 0x100
    blob = bytearray(payload_offset + len(ORIGINAL))
    blob[:8] = b"scimitar"
    struct.pack_into("<Q", blob, 13, header_table_offset)
    struct.pack_into("<IQ", blob, header_table_offset, 1, toc_offset)
    struct.pack_into(
        "<QQII", blob, toc_offset, payload_offset, RESOURCE_ID, len(ORIGINAL), 0x3F742D26
    )
    blob[payload_offset : payload_offset + len(ORIGINAL)] = ORIGINAL
    path.write_bytes(blob)
    return payload_offset, bytes(blob)


def build_package(path: Path) -> None:
    manifest = {
        "format": "jackdaw-mod-v1",
        "game": "AC4BF-Resynced",
        "name": "Decoded Resource Test",
        "version": "1.0.0",
        "author": "test",
        "targets": [
            {
                "forge": "DataPC_test.forge",
                "resource_id": f"0x{RESOURCE_ID:016X}",
                "occurrence": 0,
                "bms_block": 0,
                "mode": "decoded-resource",
                "file": "resources/replacement.bin",
                "expected_original_size": len(ORIGINAL),
                "expected_original_sha256": hashlib.sha256(ORIGINAL).hexdigest(),
            }
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("resources/replacement.bin", REPLACEMENT)


def main() -> int:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    GAME_DIR.mkdir(parents=True)
    (MODS_ROOT / "packages").mkdir(parents=True)
    forge = GAME_DIR / "DataPC_test.forge"
    payload_offset, original_forge = build_forge(forge)
    package = MODS_ROOT / "packages" / "decoded-test.jmod"
    build_package(package)

    loader = Loader(game_dir=GAME_DIR, mods_root=MODS_ROOT)
    backups = loader.apply(package)
    assert len(backups) == 1
    patched = forge.read_bytes()
    assert patched[payload_offset : payload_offset + len(REPLACEMENT)] == REPLACEMENT
    assert struct.unpack_from("<Q", patched, 0x60 + 8)[0] == RESOURCE_ID

    loader.remove("Decoded Resource Test")
    assert forge.read_bytes() == original_forge
    print("DECODED RESOURCE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
