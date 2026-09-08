"""Crew material lifecycle tests. Temporary game fixtures only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from Animus_loader.core import Loader, LoaderError
from Animus_loader.packs import PackManager
from Animus_loader.desktop_rpc import DesktopRpc
from Animus_loader import crew_patch


class CrewMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.loader = Loader(self.game, mods_root=self.root / "mods")
        self.rpc = DesktopRpc.__new__(DesktopRpc)
        self.rpc.loader, self.rpc.game_dir = self.loader, self.game
        self.rpc.manager = PackManager(self.game, self.loader.mods_root)
        self.rpc.logs = []
        self.mock = patch("Animus_loader.forge.ForgeArchive")
        self.forge = self.mock.start()
        self.addCleanup(self.mock.stop)
        self.forge.return_value.read_raw.return_value = b"stock-resource"
        self.dest = self.game / crew_patch.PATCH_FILE

    def package(self, name="Rugged test", payload=b"scimitar-fixture", digest=None):
        result = self.root / (name.replace(" ", "-") + ".jmod")
        manifest = dict(format="jackdaw-mod-v1", game="AC4BF-Resynced", name=name,
                        version="1.0", author="test", category="loose-file",
                        crew_patch=dict(target_id="rugged-rags", target_name="Rugged Rags",
                          source_resources=[dict(id="123", archive="DataPC_boot.forge",
                            raw_sha256=digest or hashlib.sha256(b"stock-resource").hexdigest())]),
                        targets=[dict(forge="", resource_id="0x0", occurrence=0, bms_block=0,
                            mode="loose-file", dest=crew_patch.PATCH_FILE, file="resources/patch.forge",
                            sha256=hashlib.sha256(payload).hexdigest())])
        with zipfile.ZipFile(result, "w") as z:
            z.writestr("manifest.json", json.dumps(manifest))
            z.writestr("resources/patch.forge", payload)
        return result

    def test_picker_install_disable_enable_remove(self):
        source = self.package()
        wrapper = self.root / "download.zip"
        with zipfile.ZipFile(wrapper, "w") as z:
            z.write(source, "folder/recolor.jmod")
        choices, _ = self.rpc.dispatch("get_crew_targets", [str(wrapper)])
        self.assertEqual(choices["default_id"], "rugged-rags")
        self.assertTrue(choices["fixed_material"])
        self.assertFalse(self.dest.exists())
        self.rpc.dispatch("install_pack_path", ["crew", str(wrapper), "rugged-rags"])
        self.assertEqual(self.dest.read_bytes(), b"scimitar-fixture")
        self.assertEqual(self.rpc.state()["mods"], [])
        self.assertEqual(self.rpc.state()["crew"][0]["replaces"], ["Rugged Rags"])
        self.rpc.dispatch("toggle_mod", ["Rugged test"])
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.rpc.state()["crew"][0]["enabled"])
        self.rpc.dispatch("toggle_mod", ["Rugged test"])
        self.assertTrue(self.dest.exists())
        self.rpc.dispatch("uninstall_mod", ["Rugged test"])
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.rpc.state()["crew"], [])

    def test_unknown_existing_archive_untouched(self):
        self.dest.write_bytes(b"another-tool")
        with self.assertRaisesRegex(LoaderError, "not overwritten"):
            self.rpc.dispatch("install_pack_path", ["crew", str(self.package()), "rugged-rags"])
        self.assertEqual(self.dest.read_bytes(), b"another-tool")
        self.assertEqual(self.loader.discover_packages(), [])

    def test_source_mismatch_and_wrong_choice_no_writes(self):
        with self.assertRaisesRegex(LoaderError, "incompatible"):
            self.rpc._install_crew_material(self.package(digest="0" * 64))
        with self.assertRaisesRegex(LoaderError, "fixed vanilla"):
            self.rpc._install_crew_material(self.package(), selected="other-crew")
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.loader.discover_packages(), [])

    def test_conflict_even_through_core(self):
        self.rpc._install_crew_material(self.package())
        second = self.package("Other crew", b"scimitar-second")
        with self.assertRaisesRegex(LoaderError, "Disable it first"):
            self.loader.apply(second)
        self.assertEqual(self.dest.read_bytes(), b"scimitar-fixture")

    def test_update_retains_rename_and_disabled_state(self):
        self.rpc._install_crew_material(self.package())
        self.rpc.dispatch("rename_item", ["mod", "Rugged test", "My crew"])
        self.rpc.dispatch("toggle_mod", ["My crew"])
        self.rpc.dispatch("update_mod_path", ["My crew", str(self.package("New recolor", b"scimitar-new"))])
        row = self.rpc.state()["crew"][0]
        self.assertEqual(row["name"], "My crew")
        self.assertFalse(row["enabled"])
        self.assertFalse(self.dest.exists())
        self.rpc.dispatch("toggle_mod", ["My crew"])
        self.assertEqual(self.dest.read_bytes(), b"scimitar-new")

    def test_failed_update_preserves_working_version(self):
        self.rpc._install_crew_material(self.package())
        package_path = self.rpc._find_package("Rugged test")
        before = package_path.read_bytes()
        state = self.loader.state_path.read_bytes()
        with self.assertRaisesRegex(LoaderError, "incompatible"):
            self.rpc.dispatch("update_mod_path", ["Rugged test", str(self.package("Bad", digest="0"*64))])
        self.assertEqual(package_path.read_bytes(), before)
        self.assertEqual(self.loader.state_path.read_bytes(), state)
        self.assertEqual(self.dest.read_bytes(), b"scimitar-fixture")

    def test_modified_file_remove_refused(self):
        self.rpc._install_crew_material(self.package())
        self.dest.write_bytes(b"external-change")
        with self.assertRaises(LoaderError):
            self.rpc.dispatch("uninstall_mod", ["Rugged test"])
        self.assertEqual(self.dest.read_bytes(), b"external-change")

    def test_failed_deployment_rolls_back_active_update(self):
        self.rpc._install_crew_material(self.package())
        package_path = self.rpc._find_package("Rugged test")
        before = package_path.read_bytes()
        state = self.loader.state_path.read_bytes()
        with patch.object(self.loader, "_apply_target", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                self.rpc.dispatch("update_mod_path", ["Rugged test", str(self.package("New", b"scimitar-new"))])
        self.assertEqual(package_path.read_bytes(), before)
        self.assertEqual(self.loader.state_path.read_bytes(), state)
        self.assertEqual(self.dest.read_bytes(), b"scimitar-fixture")

    def test_restore_vanilla(self):
        self.rpc._install_crew_material(self.package())
        self.rpc.dispatch("revert_all", ["crew"])
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.rpc.state()["crew"][0]["enabled"])


if __name__ == "__main__":
    unittest.main()
