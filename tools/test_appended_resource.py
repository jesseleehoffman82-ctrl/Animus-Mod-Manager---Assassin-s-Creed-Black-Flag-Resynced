"""Journaled arbitrary-size FORGE resource deployment tests."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from Animus_loader.core import Loader, LoaderError
from Animus_loader.forge import ForgeArchive, Oodle


def make_forge(path: Path, rid: int, payload: bytes) -> None:
    header = bytearray(1050)
    header[:9] = b"scimitar\0"
    struct.pack_into("<I", header, 9, 50)
    struct.pack_into("<Q", header, 13, 1050)
    resource_offset = 1070
    toc_offset = resource_offset + len(payload)
    data = bytes(header) + struct.pack("<IQ", 1, toc_offset) + b"\xff" * 8
    data += payload + struct.pack("<QQII", resource_offset, rid, len(payload), 1)
    path.write_bytes(data)


class AppendedResourceTests(unittest.TestCase):
    def test_partial_failure_restores_bytes_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / "game"
            game.mkdir()
            forge = game / "DataPC_boot.forge"
            make_forge(forge, 0x123, b"original")
            before = forge.read_bytes()
            package = root / "partial.jmod"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.json", json.dumps({
                    "format": "jackdaw-mod-v1", "game": "AC4BF-Resynced",
                    "name": "Partial", "version": "1", "author": "test",
                    "targets": [dict(mode="appended-resource", forge=forge.name,
                                     resource_id=hex(rid), file="data.bin")
                                for rid in (0x123, 0x456)],
                }))
                archive.writestr("data.bin", b"longer replacement")
            loader = Loader(game, root / "mods")
            with self.assertRaises(LoaderError):
                loader.apply(package)
            self.assertEqual(before, forge.read_bytes())
            self.assertEqual([], loader.list_installed())

    def test_apply_disable_restores_toc_and_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game, mods = root / "game", root / "mods"
            game.mkdir()
            rid, original, replacement = 0x123, b"old-resource", b"new-resource-is-longer"
            forge = game / "DataPC_boot.forge"
            make_forge(forge, rid, original)
            original_size = forge.stat().st_size
            package = root / "test.jmod"
            manifest = {
                "format": "jackdaw-mod-v1", "game": "AC4BF-Resynced",
                "name": "Append test", "version": "1", "author": "test",
                "targets": [{
                    "forge": forge.name, "resource_id": hex(rid),
                    "mode": "appended-resource", "file": "resources/new.bin",
                    "sha256": hashlib.sha256(replacement).hexdigest(),
                    "expected_original_size": len(original),
                    "expected_original_sha256": hashlib.sha256(original).hexdigest(),
                }],
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("resources/new.bin", replacement)
            loader = Loader(game, mods_root=mods)
            loader.apply(package)
            current = ForgeArchive(forge, Oodle(game))
            self.assertEqual(current.read_raw(rid), replacement)
            self.assertGreater(forge.stat().st_size, original_size)
            loader.disable("Append test")
            restored = ForgeArchive(forge, Oodle(game))
            self.assertEqual(restored.read_raw(rid), original)
            self.assertEqual(forge.stat().st_size, original_size)


if __name__ == "__main__":
    unittest.main()
