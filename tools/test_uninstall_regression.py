"""Uninstall versus disable regressions; temporary files and mocked game writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from Animus_loader.core import Loader, LoaderError
from Animus_loader.packs import PackManager, PackError
from Animus_loader.desktop_rpc import DesktopRpc


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.loader = Loader(self.game, mods_root=self.root / "mods")
        self.manager = PackManager(self.game, self.loader.mods_root)
        self.rpc = DesktopRpc.__new__(DesktopRpc)
        self.rpc.game_dir, self.rpc.loader, self.rpc.manager = self.game, self.loader, self.manager
        self.rpc.logs = []

    def mod(self, filename):
        path = self.loader.packages_dir / filename
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(dict(format="jackdaw-mod-v1", game="AC4BF-Resynced",
                name="Example", version="1.0", author="test", category="loose-file",
                targets=[dict(forge="", resource_id="0x0", mode="loose-file", occurrence=0,
                    bms_block=0, file="data.ini", dest="data.ini")])))
            z.writestr("data.ini", b"mod")
        return path

    def outfit(self, enabled=True):
        folder = self.manager.textures_root / "example"
        folder.mkdir()
        (folder / "meta.json").write_text(json.dumps(dict(id="example", name="Example", category="outfit", slots=[])))
        self.manager._save_library(dict(packs=[dict(id="example", name="Example", category="outfit")],
                                        enabled={"example": enabled}, active=None))

    def test_uninstall_all_duplicate_packages_stays_gone(self):
        source = self.mod("one.jmod")
        self.mod("duplicate.jmod")
        self.loader.apply(source)
        self.rpc.dispatch("uninstall_mod", ["Example"])
        self.assertFalse((self.game / "data.ini").exists())
        self.assertEqual(self.loader.list_installed(), [])
        self.assertEqual(self.rpc.state()["mods"], [])
        self.assertEqual(len(list((self.loader.mods_root / "removed-packages").rglob("*.jmod"))), 2)
        reopened = Loader(self.game, mods_root=self.loader.mods_root)
        self.assertEqual(reopened.discover_packages(), [])

    def test_disable_keeps_package_uninstall_disabled_removes_it(self):
        self.loader.apply(self.mod("one.jmod"))
        self.rpc.dispatch("toggle_mod", ["Example"])
        self.assertFalse(self.rpc.state()["mods"][0]["enabled"])
        self.rpc.dispatch("uninstall_mod", ["Example"])
        self.assertEqual(self.rpc.state()["mods"], [])

    def test_failed_remove_returns_packages_and_state(self):
        self.loader.apply(self.mod("one.jmod"))
        (self.game / "data.ini").write_bytes(b"external")
        state = self.loader.state_path.read_bytes()
        with self.assertRaises(LoaderError):
            self.rpc.dispatch("uninstall_mod", ["Example"])
        self.assertEqual(len(self.loader.discover_packages()), 1)
        self.assertEqual(self.loader.state_path.read_bytes(), state)
        self.assertEqual((self.game / "data.ini").read_bytes(), b"external")

    def test_failed_outfit_uninstall_does_not_disable(self):
        self.outfit()
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, "revert_all", side_effect=PackError("old journal")):
            with self.assertRaises(PackError):
                self.manager.remove_pack("example")
        self.assertEqual(self.manager.library_path.read_bytes(), before)
        self.assertIsNotNone(self.manager.get_pack("example"))

    def test_failed_enable_does_not_change_checkbox(self):
        self.outfit(enabled=False)
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, "revert_all", side_effect=PackError("old journal")):
            with self.assertRaises(PackError):
                self.rpc.dispatch("toggle_pack", ["outfit", "example", True])
        self.assertEqual(self.manager.library_path.read_bytes(), before)

    def test_failed_conflict_enable_does_not_change_library(self):
        self.outfit(enabled=False)
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, "revert_all", side_effect=PackError("old journal")):
            with self.assertRaises(PackError):
                self.manager.activate_imported("example", disable_conflicts=True)
        self.assertEqual(self.manager.library_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
