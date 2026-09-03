"""Regression test for manifest-free Nexus loose-file archives."""

from __future__ import annotations

import tempfile
import tarfile
import zipfile
from pathlib import Path

from Animus_loader.core import Loader, LoaderError


def fake_dll(marker: bytes) -> bytes:
    data = bytearray(512)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    data[0x100:0x100 + len(marker)] = marker
    return bytes(data)


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = root / "game"
        game.mkdir()
        (game / "ACBlackFlag.exe").write_bytes(b"test")
        source = root / "LootMultiplier 0.1.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("XINPUT9_1_0.dll", b"proxy")
            archive.writestr("acbfr-core.dll", b"core")
            archive.writestr("acbfr-loot.ini", b"multiplier=5\n")
            archive.writestr(
                "README.txt",
                "LOOT MULTIPLIER - Assassin's Creed IV Black Flag Resynced\n"
                "version 0.1 Beta\n",
            )

        loader = Loader(game_dir=game, mods_root=root / "managed")
        managed, package, converted = loader.import_package(source)
        assert converted
        assert package.name == "Loot Multiplier"
        assert package.version == "0.1 Beta"
        assert {target.dest for target in package.targets} == {
            "XINPUT9_1_0.dll", "acbfr-core.dll", "acbfr-loot.ini",
        }
        assert managed.suffix == ".jmod"

        loader.apply(managed)
        assert (game / "XINPUT9_1_0.dll").read_bytes() == b"proxy"
        assert (game / "acbfr-core.dll").read_bytes() == b"core"
        assert (game / "acbfr-loot.ini").read_text() == "multiplier=5\n"
        loader.remove(package.name)
        assert not (game / "XINPUT9_1_0.dll").exists()
        assert not (game / "acbfr-core.dll").exists()
        assert not (game / "acbfr-loot.ini").exists()

        # Conventional video replacers belong in the normal Mods tab. Their
        # top-level videos/ paths are relative to the game root, and originals
        # must be restored when the mod is disabled or removed.
        videos = game / "videos"
        videos.mkdir()
        (videos / "ANVIL_Logo.webm").write_bytes(b"original-anvil")
        video_source = root / "Resynced Fast Launch 2 1.1.zip"
        with zipfile.ZipFile(video_source, "w") as archive:
            archive.writestr("videos/ANVIL_Logo.webm", b"blank-video")
            archive.writestr("videos/en/Epilepsy.webm", b"blank-warning")
            archive.writestr(
                "ReadMe.txt",
                "RESYNCED FAST LAUNCH - Assassin's Creed IV Black Flag Resynced\n"
                "version 1.1\n",
            )

        video_managed, video_package, video_converted = loader.import_package(video_source)
        assert video_converted
        assert video_package.name == "Resynced Fast Launch"
        assert video_package.version == "1.1"
        assert {target.dest for target in video_package.targets} == {
            "videos/ANVIL_Logo.webm", "videos/en/Epilepsy.webm",
        }

        loader.apply(video_managed)
        assert (videos / "ANVIL_Logo.webm").read_bytes() == b"blank-video"
        assert (videos / "en" / "Epilepsy.webm").read_bytes() == b"blank-warning"
        loader.remove(video_package.name)
        assert (videos / "ANVIL_Logo.webm").read_bytes() == b"original-anvil"
        assert not (videos / "en" / "Epilepsy.webm").exists()

        # Exercise the non-ZIP extraction/normalization route without relying
        # on an external test fixture. RAR and 7z use this same normalized-tree
        # importer after the bundled 7-Zip extractor has unpacked them.
        tar_payload = root / "tar-payload"
        (tar_payload / "videos").mkdir(parents=True)
        (tar_payload / "videos" / "HUB_BootFlow_Intro.webm").write_bytes(b"blank-intro")
        (tar_payload / "ReadMe.txt").write_text("Copy videos into the game folder.\n")
        tar_source = root / "Fast Videos 3 1.2 2026-08-29T10-00Z abc123.tgz"
        with tarfile.open(tar_source, "w:gz") as archive:
            archive.add(tar_payload / "videos", arcname="videos")
            archive.add(tar_payload / "ReadMe.txt", arcname="ReadMe.txt")

        tar_managed, tar_package, tar_converted = loader.import_package(tar_source)
        assert tar_converted
        assert tar_package.name == "Fast Videos"
        assert tar_package.version == "1.2"
        assert {target.dest for target in tar_package.targets} == {
            "videos/HUB_BootFlow_Intro.webm",
        }
        loader.apply(tar_managed)
        assert (videos / "HUB_BootFlow_Intro.webm").read_bytes() == b"blank-intro"
        loader.remove(tar_package.name)
        assert not (videos / "HUB_BootFlow_Intro.webm").exists()

        # Universal downloads can contain mutually exclusive original-game
        # and Resynced payload folders. Select and flatten only the explicit
        # Resynced x64/DX12 option rather than copying both folders verbatim.
        universal = root / "Walk By Default 428 3 2026-08-25T04-28Z AbCd123.zip"
        with zipfile.ZipFile(universal, "w") as archive:
            archive.writestr(
                "1. Steam and Ubisoft Connect (Standard 32-bit)/version.dll",
                fake_dll(b"32 BIT OPTION"),
            )
            archive.writestr(
                "2. Black Flag Resynced (64-bit DX12)/version.dll",
                fake_dll(b"RESYNCED OPTION"),
            )
            archive.writestr(
                "2. Black Flag Resynced (64-bit DX12)/walking.conf",
                b"enabled=true\n",
            )
            archive.writestr(
                "README.txt",
                "Rename the existing version.dll file to wininet.dll before installing.\n",
            )
        universal_managed, universal_package, converted = loader.import_package(universal)
        assert converted
        assert universal_package.version == "3"
        assert universal_package.manifest["nexus"]["mod_id"] == 428
        assert universal_package.manifest["proxy_chain"]["secondary"] == "wininet.dll"
        assert universal_package.manifest["selected_archive_root"].startswith("2.")
        assert {target.dest for target in universal_package.targets} == {
            "version.dll", "walking.conf",
        }
        assert b"RESYNCED OPTION" in next(
            target.replacement for target in universal_package.targets
            if target.dest == "version.dll"
        )

        blocked = root / "unsafe.zip"
        with zipfile.ZipFile(blocked, "w") as archive:
            archive.writestr("setup.exe", b"no")
        try:
            loader.import_package(blocked)
        except LoaderError as exc:
            assert "installer or script" in str(exc)
        else:
            raise AssertionError("Executable installer archive was not rejected")

    print("manifest-free Nexus ZIP import test passed")


if __name__ == "__main__":
    main()
