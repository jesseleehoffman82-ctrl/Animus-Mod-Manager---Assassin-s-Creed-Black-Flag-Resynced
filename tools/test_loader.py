"""End-to-end test of the loader's byte-patch apply/remove cycle.

Builds a small synthetic "forge" file that contains the two needle patterns,
then applies the boarding-officers package, verifies the patch, removes it,
and verifies the restore. Does NOT touch the real game.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from Animus_loader import Loader, LoaderError  # noqa: E402

TEST_ROOT = Path(__file__).resolve().parent / "_test"
GAME_DIR = TEST_ROOT / "game"
MODS_ROOT = TEST_ROOT / "mods"

LUCY_NEEDLE = bytes.fromhex("9f5381202d020000")
LUCY_PATCH = bytes.fromhex("6c5381202d020000")
ADEWALE_NEEDLE = bytes.fromhex("b85381202d020000")
ADEWALE_PATCH = bytes.fromhex("6c5381202d020000")

FORGE_PREFIX = b"TESTFORGE" + b"\x00" * 128
FORGE_SUFFIX = b"\x00" * 512


def build_test_forge(path: Path) -> None:
    blob = FORGE_PREFIX + LUCY_NEEDLE + b"\xaa" * 64 + ADEWALE_NEEDLE + b"\xbb" * 64 + FORGE_SUFFIX
    path.write_bytes(blob)


def build_package(path: Path) -> None:
    manifest = {
        "format": "jackdaw-mod-v1",
        "game": "AC4BF-Resynced",
        "name": "Test Boarding Pack",
        "version": "1.0.0",
        "author": "test",
        "targets": [
            {
                "forge": "DataPC_boot.forge",
                "resource_id": "0x0000022D208152C2",
                "occurrence": 0,
                "bms_block": 0,
                "mode": "byte-patch",
                "needle": LUCY_NEEDLE.hex(),
                "patch": LUCY_PATCH.hex(),
                "original": LUCY_NEEDLE.hex(),
            },
            {
                "forge": "DataPC_boot.forge",
                "resource_id": "0x0000022D208152A6",
                "occurrence": 0,
                "bms_block": 0,
                "mode": "byte-patch",
                "needle": ADEWALE_NEEDLE.hex(),
                "patch": ADEWALE_PATCH.hex(),
                "original": ADEWALE_NEEDLE.hex(),
            },
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))


def main() -> int:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    GAME_DIR.mkdir(parents=True)
    MODS_ROOT.mkdir(parents=True)
    (MODS_ROOT / "packages").mkdir(parents=True)

    forge = GAME_DIR / "DataPC_boot.forge"
    build_test_forge(forge)
    package = MODS_ROOT / "packages" / "test-board-pack.jmod"
    build_package(package)

    loader = Loader(game_dir=GAME_DIR, mods_root=MODS_ROOT)

    # 1. Verify needle present in original.
    original = forge.read_bytes()
    assert LUCY_NEEDLE in original, "Lucy needle missing from test forge"
    assert ADEWALE_NEEDLE in original, "Adewale needle missing from test forge"

    # 2. Apply.
    backups = loader.apply(package, priority=0)
    assert len(backups) == 2, f"expected 2 backups, got {len(backups)}"

    patched = forge.read_bytes()
    assert LUCY_PATCH in patched, "Lucy patch not applied"
    assert ADEWALE_PATCH in patched, "Adewale patch not applied"
    assert LUCY_NEEDLE not in patched, "Lucy needle should be gone after patch"
    assert ADEWALE_NEEDLE not in patched, "Adewale needle should be gone after patch"

    # 3. State recorded.
    records = loader.list_installed()
    assert len(records) == 1 and records[0].name == "Test Boarding Pack", "state not recorded"

    # 4. Disable -> restore, but retain a disabled library record.
    restored = loader.disable("Test Boarding Pack")
    assert len(restored) == 2, f"expected 2 restored file writes, got {len(restored)}"
    restored_bytes = forge.read_bytes()
    assert restored_bytes == original, "forge not restored to original bytes"
    records = loader.list_installed()
    assert len(records) == 1 and not records[0].enabled, "disabled state should be retained"
    assert records[0].name == "Test Boarding Pack", "disabled package should remain in library"

    # 5. Re-enable, then uninstall removes the record entirely.
    loader.apply(package, priority=0)
    loader.remove("Test Boarding Pack")
    assert loader.list_installed() == [], "state should be empty after remove"

    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
