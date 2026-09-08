"""Offline regressions; only disposable synthetic game directories are used."""
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from Animus_loader.core import Loader, LoaderError
from Animus_loader.texture import _layout


def run():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        game = root / "game"
        game.mkdir()
        loader = Loader(game, root / "mods")
        package = root / "test.jmod"
        base = {"format": "jackdaw-mod-v1", "game": "AC4BF-Resynced",
                "name": "Test", "version": "1.0.0", "author": "test"}

        def write(targets):
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.json", json.dumps(dict(base, targets=targets)))
                archive.writestr("resources/data", b"new")

        def target(dest, **extra):
            return dict(mode="loose-file", dest=dest, file="resources/data", **extra)

        for path in ("../outside", "C:outside", "/outside", "safe:file", "folder/../../outside"):
            write([target(path)])
            try:
                loader.apply(package)
                raise AssertionError(f"Accepted unsafe path {path}")
            except LoaderError:
                pass
        write([dict(mode="byte-patch", forge="../outside", needle="AA", patch="BB")])
        try:
            loader.apply(package)
            raise AssertionError("Accepted unsafe forge path")
        except LoaderError:
            pass
        write([target("valid.bin", sha256="0" * 64)])
        try:
            loader.apply(package)
            raise AssertionError("Accepted corrupt payload")
        except LoaderError:
            pass
        (game / "valid.bin").write_bytes(b"original")
        write([target("valid.bin"), dict(mode="unsupported", forge="missing.forge")])
        try:
            loader.apply(package)
            raise AssertionError("Accepted unsupported second target")
        except LoaderError:
            pass
        assert (game / "valid.bin").read_bytes() == b"original"
        (game / "a").mkdir()
        (game / "b").mkdir()
        (game / "a/file.bin").write_bytes(b"first")
        (game / "b/file.bin").write_bytes(b"second")
        write([target("a/file.bin"), target("b/file.bin")])
        loader.apply(package)
        loader.remove("Test")
        assert (game / "a/file.bin").read_bytes() == b"first"
        assert (game / "b/file.bin").read_bytes() == b"second"
        assert loader.list_installed() == []
        write([target("valid.bin", sha256=hashlib.sha256(b"new").hexdigest())])
        loader.apply(package)
        loader.remove("Test")
        assert (game / "valid.bin").read_bytes() == b"original"
    wide, _ = _layout(1024, 512, 16, 0, 10**7)
    tall, _ = _layout(512, 1024, 16, 0, 10**7)
    assert wide[0][3:] == (128, 4096)
    assert tall[0][3:] == (256, 2048)
    print("RELEASE SAFETY TESTS PASSED")


if __name__ == "__main__":
    run()
