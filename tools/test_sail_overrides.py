"""Sail patch-archive deployment: isolated synthetic archives, never live game data."""
import json
import unittest
from unittest.mock import patch

from test_deployment_state import DeploymentTests
from Animus_loader import packs


class SailOverrideTests(unittest.TestCase):
    setUp = DeploymentTests.setUp

    def sail(self):
        pack = self.manager.import_pack(self.source)
        lib = self.manager._load_library()
        next(p for p in lib["packs"] if p["id"] == pack.id)["category"] = "sail"
        self.manager._save_library(lib)
        self.manager.set_enabled(pack.id, True)
        return self.manager.get_pack(pack.id)

    def shadow(self, name="DataPC_boot_patch_01.forge"):
        path = self.forge.parent / name
        path.write_bytes(self.forge.read_bytes())
        return path

    def test_all_copies_patched_and_disabled_exactly_restored(self):
        original = self.forge.read_bytes()
        shadow = self.shadow()
        renderer = self.shadow("DataPC_boot_dx12.forge")
        sail = self.sail()
        result = self.manager.apply_staged()
        self.assertEqual(2, len(result["sail_override_archives"]))
        self.assertNotEqual(original, shadow.read_bytes())
        self.assertEqual(self.forge.read_bytes(), shadow.read_bytes())
        self.assertEqual(self.forge.read_bytes(), renderer.read_bytes())
        self.assertEqual({sail.id}, self.manager.deployed_pack_ids())
        self.manager.set_enabled(sail.id, False)
        self.manager.apply_staged()
        for path in (self.forge, shadow, renderer):
            self.assertEqual(original, path.read_bytes())

    def test_legacy_journal_upgrades_without_losing_library(self):
        original = self.forge.read_bytes()
        sail = self.sail()
        self.manager.apply_staged()
        raw = json.loads(self.manager.journal_path.read_text())
        raw.pop("overrides")
        self.manager.journal_path.write_text(json.dumps(raw))
        shadow = self.forge.parent / "DataPC_boot_patch_01.forge"
        shadow.write_bytes(original)
        before = self.manager.library_path.read_bytes()
        self.manager.apply_staged()
        self.assertEqual(self.forge.read_bytes(), shadow.read_bytes())
        self.assertEqual(before, self.manager.library_path.read_bytes())
        self.assertIsNotNone(self.manager.get_pack(sail.id))
        self.manager.revert_all()
        self.assertEqual(original, shadow.read_bytes())

    def test_invalid_override_leaves_previous_install_untouched(self):
        self.sail()
        self.manager.apply_staged()
        shadow = self.shadow()
        shadow.write_bytes(b"invalid archive")
        before = self.forge.read_bytes()
        journal = self.manager.journal_path.read_bytes()
        with self.assertRaises(Exception):
            self.manager.apply_staged()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual(journal, self.manager.journal_path.read_bytes())

    def test_targeted_repair_does_not_rewrite_base_or_library(self):
        original = self.forge.read_bytes()
        sail = self.sail()
        self.manager.apply_staged()
        shadow = self.forge.parent / "DataPC_boot_patch_01.forge"
        shadow.write_bytes(original)
        before = self.forge.read_bytes()
        library = self.manager.library_path.read_bytes()
        self.manager.repair_sail_overrides()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual(before, shadow.read_bytes())
        self.assertEqual(library, self.manager.library_path.read_bytes())
        self.assertEqual({sail.id}, self.manager.deployed_pack_ids())
        self.manager.revert_all()
        self.assertEqual(original, self.forge.read_bytes())
        self.assertEqual(original, shadow.read_bytes())

    def test_targeted_repair_failure_preserves_base(self):
        original = self.forge.read_bytes()
        self.sail()
        self.manager.apply_staged()
        shadow = self.forge.parent / "DataPC_boot_patch_01.forge"
        shadow.write_bytes(original)
        before = self.forge.read_bytes()
        journal = self.manager.journal_path.read_bytes()
        with patch.object(packs, "compress_material", side_effect=ValueError("failure")):
            with self.assertRaises(ValueError):
                self.manager.repair_sail_overrides()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual(original, shadow.read_bytes())
        self.assertEqual(journal, self.manager.journal_path.read_bytes())

    def test_child_failure_rolls_back_all_archives(self):
        shadow = self.shadow()
        original = shadow.read_bytes()
        self.sail()
        compress = packs.compress_material
        calls = 0
        def fail_child(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated patch archive compression failure")
            return compress(*args)
        with patch.object(packs, "compress_material", side_effect=fail_child):
            with self.assertRaisesRegex(packs.PackError, "Previous deployment was restored"):
                self.manager.apply_staged()
        self.assertEqual(original, self.forge.read_bytes())
        self.assertEqual(original, shadow.read_bytes())
        self.assertEqual(set(), self.manager.deployed_pack_ids())

    def test_child_failure_restores_previous_complete_deployment(self):
        shadow = self.shadow()
        sail = self.sail()
        self.manager.apply_staged()
        before = self.forge.read_bytes()
        compress = packs.compress_material
        calls = 0
        def fail_child_once(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated patch archive failure")
            return compress(*args)
        with patch.object(packs, "compress_material", side_effect=fail_child_once):
            with self.assertRaisesRegex(packs.PackError, "Previous deployment was restored"):
                self.manager.apply_staged()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual(before, shadow.read_bytes())
        self.assertEqual({sail.id}, self.manager.deployed_pack_ids())

    def test_missing_child_journal_does_not_report_enabled(self):
        self.shadow()
        self.sail()
        self.manager.apply_staged()
        child = self.manager._override_manager("DataPC_boot_patch_01.forge")
        child.journal_path.unlink()
        self.assertEqual(set(), self.manager.deployed_pack_ids())

    def test_normal_outfit_does_not_touch_shadow(self):
        shadow = self.shadow()
        before = shadow.read_bytes()
        self.manager.install(self.source)
        self.assertEqual(before, shadow.read_bytes())

    def test_revert_pack_includes_override(self):
        shadow = self.shadow()
        original = shadow.read_bytes()
        sail = self.sail()
        self.manager.apply_staged()
        self.manager.revert_pack(sail.id)
        self.assertEqual(original, self.forge.read_bytes())
        self.assertEqual(original, shadow.read_bytes())
        self.assertIsNotNone(self.manager.get_pack(sail.id))


if __name__ == "__main__":
    unittest.main()
