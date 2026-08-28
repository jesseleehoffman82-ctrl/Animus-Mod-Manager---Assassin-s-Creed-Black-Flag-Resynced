"""End-to-end tests for loose files and version.dll compatibility chaining."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from Animus_loader import Loader, LoaderError  # noqa: E402

TEST_ROOT = Path(__file__).resolve().parent / "_test_loose"
GAME_DIR = TEST_ROOT / "game"
MODS_ROOT = TEST_ROOT / "mods"


def fake_dll(marker: bytes) -> bytes:
    data = bytearray(512)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    data[0x100:0x100 + len(marker)] = marker
    return bytes(data)


def main() -> int:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    GAME_DIR.mkdir(parents=True)
    (MODS_ROOT / "packages").mkdir(parents=True)

    # Simulate a pre-existing custom x64 version proxy.
    preexisting = fake_dll(b"CUSTOM VERSION PROXY")
    (GAME_DIR / "version.dll").write_bytes(preexisting)

    # Incoming recognized Ultimate ASI Loader.
    replacement = fake_dll(b"Ultimate-ASI-Loader TEST")

    # Package resources.
    res_dir = MODS_ROOT / "_src" / "resources"
    res_dir.mkdir(parents=True)
    (res_dir / "version.dll").write_bytes(replacement)

    manifest = {
        "format": "jackdaw-mod-v1",
        "game": "AC4BF-Resynced",
        "name": "Test Loose Pack",
        "version": "1.0.0",
        "author": "test",
        "category": "loose-file",
        "targets": [
            {
                "mode": "loose-file",
                "file": "resources/version.dll",
                "dest": "version.dll",
            }
        ],
    }
    package = MODS_ROOT / "packages" / "test-loose.jmod"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.write(res_dir / "version.dll", "resources/version.dll")

    loader = Loader(game_dir=GAME_DIR, mods_root=MODS_ROOT)

    # 1. Apply - ASI loader becomes primary; old proxy is preserved as hook.
    entries = loader.apply(package)
    assert len(entries) == 1, "expected 1 backup entry"
    assert (GAME_DIR / "version.dll").read_bytes() == replacement, "file not replaced"
    assert (GAME_DIR / "versionHooked.dll").read_bytes() == preexisting, "existing proxy not chained"
    assert entries[0]["mode"] == "loose-file"
    assert entries[0]["original_hex"] == preexisting.hex(), "original not captured"
    assert entries[0]["compatibility"] == "asi-loader-with-preserved-proxy"

    # 2. Remove - should restore preexisting and remove temporary chain copy.
    restored = loader.remove("Test Loose Pack")
    assert len(restored) == 1, "expected 1 restored"
    assert (GAME_DIR / "version.dll").read_bytes() == preexisting, "original not restored"
    assert not (GAME_DIR / "versionHooked.dll").exists(), "chain copy not removed"

    # 3. State empty.
    assert loader.list_installed() == [], "state should be empty"

    # 4. Existing ASI loader + incoming custom proxy: custom DLL is installed
    #    directly as versionHooked.dll and removed without touching the loader.
    (GAME_DIR / "version.dll").write_bytes(replacement)
    custom = fake_dll(b"SECOND CUSTOM PROXY")
    (res_dir / "version.dll").write_bytes(custom)
    manifest["name"] = "Test Chained Pack"
    chained_package = MODS_ROOT / "packages" / "test-chained.jmod"
    with zipfile.ZipFile(chained_package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.write(res_dir / "version.dll", "resources/version.dll")
    chained = loader.apply(chained_package)
    assert (GAME_DIR / "version.dll").read_bytes() == replacement
    assert (GAME_DIR / "versionHooked.dll").read_bytes() == custom
    assert chained[0]["compatibility"] == "chained-behind-asi-loader"

    # Register a package sharing the current ASI loader, then ensure it cannot
    # be disabled before the chained custom proxy that depends on it.
    (res_dir / "version.dll").write_bytes(replacement)
    manifest["name"] = "Test Managed Loader"
    managed_loader = MODS_ROOT / "packages" / "test-managed-loader.jmod"
    with zipfile.ZipFile(managed_loader, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.write(res_dir / "version.dll", "resources/version.dll")
    loader.apply(managed_loader)
    try:
        loader.remove("Test Managed Loader")
        raise AssertionError("dependent proxy should block primary loader removal")
    except LoaderError as exc:
        assert "depend" in str(exc).lower()

    loader.remove("Test Chained Pack")
    loader.remove("Test Managed Loader")
    assert (GAME_DIR / "version.dll").read_bytes() == replacement
    assert not (GAME_DIR / "versionHooked.dll").exists()

    print("LOOSE-FILE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
