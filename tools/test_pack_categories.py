"""Category rejection must happen before import, without changing installed mods."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from Animus_loader.packs import PackError, PackManager


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manager = PackManager(self.root / "game", self.root / "mods")
        self.manager.library_path.write_text(json.dumps({
            "packs": [{"id": "existing", "name": "Keep me", "category": "outfit"}],
            "active": "existing", "staged": {"outfit": ["existing"]},
        }))
        self.before = self.snapshot()

    def snapshot(self):
        return {str(p.relative_to(self.manager.mods_root)): p.read_bytes()
                for p in self.manager.mods_root.rglob("*") if p.is_file()}

    def archive(self, name, entries):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for entry, value in entries.items():
                z.writestr(entry, value)
        return path

    def rejected(self, source, message="Outfits tab"):
        with patch.object(self.manager, "_import_files") as importer:
            with self.assertRaisesRegex(PackError, message):
                self.manager.import_pack(source, category="weapon")
            importer.assert_not_called()
        self.assertEqual(self.before, self.snapshot())

    def test_archive_name_survives_extraction(self):
        self.rejected(self.archive("Duncan Outfit.zip", {"0x2128A456A2D.dds": b"x"}))

    def test_nested_folder_survives_extraction(self):
        self.rejected(self.archive("download.zip", {"Morgan Redingote/0x2128A456A2D.dds": b"x"}))

    def test_readme_replacement(self):
        self.rejected(self.archive("download.zip", {
            "0x2128A456A2D.dds": b"x", "README.txt": "Replaces vanilla outfit: Duncan's Robes"}))

    def test_metadata_name(self):
        self.rejected(self.archive("download.zip", {
            "0x2128A456A2D.dds": b"x", "meta.json": '{"name":"Duncan Outfit"}'}))

    def test_mixed_weapon_and_outfit(self):
        self.rejected(self.archive("Swords and outfits.zip", {"0x2128A456A2D.dds": b"x"}))

    def test_weapon_metadata_does_not_override_outfit_evidence(self):
        self.rejected(self.archive("Outfit.zip", {
            "0x2128A456A2D.dds": b"x", "meta.json": '{"category":"weapon"}'}))

    def test_unknown_hash_only_pack_is_not_assumed_weapon(self):
        self.rejected(self.archive("download.zip", {"0x2128A456A2D.dds": b"x"}),
                      "could not be identified")

    def test_single_outfit_image(self):
        source = self.root / "Outfit_0x2128A456A2D.png"
        source.write_bytes(b"x")
        self.rejected(source)

    def test_valid_routes_still_reach_import(self):
        for title, category in (("Pistol", "weapon"), ("Sword", "weapon"),
                                ("Blunderbuss", "weapon"), ("Weapons", "weapon"),
                                ("Outfit", "outfit"), ("download", "outfit")):
            with self.subTest(title=title, category=category):
                source = self.archive(title + ".zip", {"0x2128A456A2D.dds": b"x"})
                with patch.object(self.manager, "_import_files", return_value="accepted") as importer:
                    self.assertEqual("accepted", self.manager.import_pack(source, category=category))
                    importer.assert_called_once()

    def test_rar_and_7z_use_same_archive_validation(self):
        for suffix in ("rar", "7z"):
            source = self.root / ("Duncan Outfit." + suffix)
            source.write_bytes(b"placeholder")
            def extract(_source, dest):
                (dest / "0x2128A456A2D.dds").write_bytes(b"x")
            with patch.object(self.manager, "_extract_archive", side_effect=extract):
                self.rejected(source)


if __name__ == "__main__":
    unittest.main()
