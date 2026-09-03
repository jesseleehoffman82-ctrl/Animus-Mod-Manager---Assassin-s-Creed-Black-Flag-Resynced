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


def write_proxy_package(mods_root: Path, filename: str, name: str, payload: bytes,
                        chain_alias: str | None = None) -> Path:
    package = mods_root / "packages" / filename
    manifest = {
        "format": "jackdaw-mod-v1",
        "game": "AC4BF-Resynced",
        "name": name,
        "version": "1.0.0",
        "author": "test",
        "category": "loose-file",
        "targets": [{
            "mode": "loose-file",
            "file": "resources/version.dll",
            "dest": "version.dll",
        }],
    }
    if chain_alias:
        manifest["proxy_chain"] = {"secondary": chain_alias}
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("resources/version.dll", payload)
    return package


def main() -> int:
    nexus_name = "Walk By Default 428 3 2026-08-25T04-28Z AbCd123"
    assert Loader._nexus_archive_mod_id(nexus_name) == 428
    assert Loader._loose_archive_metadata(nexus_name, "")[1] == "3"
    assert Loader._proxy_chain_alias("", 428) == "wininet.dll"

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
    assert entries[0]["original_hex"] is None, "backup bytes must not be duplicated in state"
    assert Path(entries[0]["backup"]).read_bytes() == preexisting, "original backup not captured"
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

    # 5. Two custom proxies can coexist only when one explicitly declares a
    #    supported secondary alias. This models Walk By Default (Nexus 428),
    #    whose documented chain loads the previous proxy as wininet.dll.
    chain_game = TEST_ROOT / "chain-game"
    chain_mods = TEST_ROOT / "chain-mods"
    chain_game.mkdir()
    (chain_mods / "packages").mkdir(parents=True)
    goated_proxy = fake_dll(b"GOATED CUSTOM PROXY")
    walking_proxy = fake_dll(b"WALKING CUSTOM PROXY")
    goated_package = write_proxy_package(
        chain_mods, "goated.jmod", "Goated", goated_proxy)
    walking_package = write_proxy_package(
        chain_mods, "walking.jmod", "Walk By Default", walking_proxy,
        "wininet.dll")
    chain_loader = Loader(game_dir=chain_game, mods_root=chain_mods)
    chain_loader.apply(goated_package)
    walking_entries = chain_loader.apply(walking_package)
    assert (chain_game / "version.dll").read_bytes() == walking_proxy
    assert (chain_game / "wininet.dll").read_bytes() == goated_proxy
    assert walking_entries[0]["compatibility"] == "primary-with-wininet.dll-chain"
    try:
        chain_loader.remove("Walk By Default")
        raise AssertionError("primary proxy removal should be blocked while its chain is active")
    except LoaderError as exc:
        assert "depend" in str(exc).lower()
    chain_loader.remove("Goated")
    chain_loader.remove("Walk By Default")
    assert not (chain_game / "version.dll").exists()
    assert not (chain_game / "wininet.dll").exists()

    # 6. Installation order does not matter: installing the secondary custom
    #    proxy after the chain-capable primary places it directly in the alias.
    reverse_game = TEST_ROOT / "reverse-game"
    reverse_mods = TEST_ROOT / "reverse-mods"
    reverse_game.mkdir()
    (reverse_mods / "packages").mkdir(parents=True)
    walking_first = write_proxy_package(
        reverse_mods, "walking.jmod", "Walk By Default", walking_proxy,
        "wininet.dll")
    goated_second = write_proxy_package(
        reverse_mods, "goated.jmod", "Goated", goated_proxy)
    reverse_loader = Loader(game_dir=reverse_game, mods_root=reverse_mods)
    reverse_loader.apply(walking_first)
    goated_entries = reverse_loader.apply(goated_second)
    assert (reverse_game / "version.dll").read_bytes() == walking_proxy
    assert (reverse_game / "wininet.dll").read_bytes() == goated_proxy
    assert goated_entries[0]["compatibility"] == "chained-as-wininet.dll"
    reverse_loader.remove("Goated")
    reverse_loader.remove("Walk By Default")

    print("LOOSE-FILE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
