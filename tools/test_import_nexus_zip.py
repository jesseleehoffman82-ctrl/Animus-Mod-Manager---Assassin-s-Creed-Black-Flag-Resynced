"""Regression test for manifest-free Nexus loose-file archives."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from Animus_loader.core import Loader, LoaderError


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
