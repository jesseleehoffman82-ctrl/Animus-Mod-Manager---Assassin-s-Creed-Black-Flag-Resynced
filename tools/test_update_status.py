"""Update preview, version propagation and durable status, using synthetic data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from Animus_loader.core import Loader
from Animus_loader.desktop_rpc import DesktopRpc
from Animus_loader.packs import PackManager
from test_deployment_state import DeploymentTests


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.rpc = DesktopRpc.__new__(DesktopRpc)
        self.rpc.game_dir = self.game
        self.rpc.loader = Loader(self.game, self.root / "mods")
        self.rpc.manager = PackManager(self.game, self.root / "mods")
        self.rpc.logs = []

    def package(self, version):
        path = self.root / f"Test-{version}.jmod"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "format": "jackdaw-mod-v1", "game": "AC4BF-Resynced", "name": "Test mod",
                "version": version, "category": "loose-file", "author": "Tester",
                "targets": [{"mode": "loose-file", "file": "payload/config.ini", "dest": "test/config.ini"}],
            }))
            archive.writestr("payload/config.ini", f"version={version}")
        return path

    def test_preview_does_not_deploy_or_modify_library_then_update_persists(self):
        path, _, _ = self.rpc.loader.import_package(self.package("1.0"))
        self.rpc.loader.apply(path)
        new = self.package("2.0")
        before = snapshot(self.root)
        result, state = self.rpc.dispatch("preview_update", ["mod", "Test mod", str(new)])
        self.assertIsNone(state)
        self.assertEqual((result["name"], result["previous_version"], result["version"]), ("Test mod", "1.0", "2.0"))
        self.assertEqual(before, snapshot(self.root))  # cancel at this point is a no-op
        result, state = self.rpc.dispatch("update_mod_path", ["Test mod", str(new)])
        row = state["mods"][0]
        self.assertEqual(row["version"], "2.0")
        self.assertEqual(row["previous_version"], "1.0")
        self.assertEqual(row["updated_version"], "2.0")
        self.assertTrue(row["updated_at"])
        self.assertTrue(row["enabled"])
        self.assertEqual((self.game / "test/config.ini").read_text(), "version=2.0")
        self.assertEqual(row["updated_at"], self.rpc.state()["mods"][0]["updated_at"])
        self.rpc.dispatch("rename_item", ["mod", "Test mod", "Renamed mod"])
        self.assertEqual(row["updated_at"], self.rpc.state()["mods"][0]["updated_at"])

    def test_failed_preview_has_no_update_status(self):
        with self.assertRaises(Exception):
            self.rpc.dispatch("preview_update", ["mod", "missing", str(self.package("2.0"))])
        self.assertEqual({}, self.rpc._update_history())

    def test_unknown_version_is_not_invented(self):
        self.assertEqual(Loader._loose_archive_metadata("Some mod", "")[1], "Unknown")
        source = self.root / "readme-source"
        source.mkdir()
        (source / "README.txt").write_text("Version: 3.2 beta\nAuthor: Example")
        self.assertEqual(PackManager._pack_metadata(source)["version"], "3.2 beta")


class TextureUpdateTests(DeploymentTests):
    def setUp(self):
        super().setUp()
        self.rpc.game_dir = self.forge.parent
        self.rpc.loader = Loader(self.forge.parent, self.root / "mods")
        self.rpc.logs = []

    def test_updates_in_every_texture_category(self):
        # Category detection has its own rejection suite. Here use the same
        # synthetic resource to exercise the shared update workflow in all tabs.
        with patch.object(PackManager, "_validate_pack_category"):
            for category in ("outfit", "weapon", "crew", "sail", "general"):
                with self.subTest(category=category):
                    (self.source / "meta.json").write_text(json.dumps({"version": "1.0"}))
                    old = self.manager.import_pack(self.source, category=category)
                    self.manager.set_enabled(old.id, True)
                    self.manager.apply_staged()
                    (self.source / "meta.json").write_text(json.dumps({"version": "2.0"}))
                    before = snapshot(self.root)
                    preview, _ = self.rpc.dispatch("preview_update", [category, old.id, str(self.source)])
                    self.assertEqual("1.0", preview["previous_version"])
                    self.assertEqual("2.0", preview["version"])
                    self.assertEqual(before, snapshot(self.root))
                    result, state = self.rpc.dispatch("update_pack_path", [category, old.id, str(self.source)])
                    tab = {"outfit": "outfits", "weapon": "weapons", "crew": "crew", "sail": "sails", "general": "mods"}[category]
                    row = next(r for r in state[tab] if r["id"] == result["id"])
                    self.assertEqual("2.0", row["version"])
                    self.assertEqual("1.0", row["previous_version"])
                    self.assertTrue(row["enabled"])
                    self.assertTrue(row["updated_at"])
                    self.assertIsNone(self.manager.get_pack(old.id))
                    self.manager.remove_pack(result["id"])


if __name__ == "__main__":
    unittest.main()
