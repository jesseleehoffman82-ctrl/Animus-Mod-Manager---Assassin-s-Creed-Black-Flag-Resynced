import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "custom_cosmetic_injector.py"
SPEC = importlib.util.spec_from_file_location("custom_cosmetic_injector", MODULE_PATH)
injector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(injector)


class InjectorTransactionTests(unittest.TestCase):
    def make_fixture(self, root: Path):
        package = root / "package"
        game = root / "game"
        package.mkdir()
        (package / "patch.json").write_text(json.dumps({
            "shared_textures_overwritten": False,
            "target_scope": "Sails",
        }), encoding="utf-8")
        (package / "sail.png").write_bytes(b"png-test")
        (game / "scripts").mkdir(parents=True)
        (game / "scripts" / "ResyncedScriptHook.asi").write_bytes(b"old-hook")
        hook = root / "new-hook.asi"
        hook.write_bytes(b"new-hook")
        return package, game, hook

    @staticmethod
    def verified_game():
        return {
            "exe_name": "ACBlackFlag.exe",
            "exe_bytes": 478_845_280,
            "exe_sha256": injector.SUPPORTED_EXECUTABLES["ACBlackFlag.exe"]["sha256"],
            "build_guard_verified": True,
            "asi_loader_present": True,
        }

    @staticmethod
    def approved_hook():
        return {
            "sha256": next(iter(injector.APPROVED_HOOKS)),
            "bytes": 3_397_471,
            "capability": "isolated-slot-staging-v1",
            "visible_slot_insertion": False,
            "runtime_redirect_verified": False,
        }

    def test_success_commits_slot_selection_hook_and_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()):
                state = injector.install(package, game, "Test Slot", hook)
            slot = game / "resynced_hook" / "custom_cosmetics" / "test-slot-sails"
            self.assertTrue((slot / "textures" / "sail.png").is_file())
            self.assertEqual((game / "scripts" / "ResyncedScriptHook.asi").read_bytes(), b"new-hook")
            self.assertTrue(state["build_guard_verified"])
            self.assertFalse(state["forge_archives_modified"])
            self.assertFalse(state["visible_slot_insertion_enabled"])
            manifest = json.loads((slot / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["native_contract"]["synthetic_resource_id"], "0x00007F4A44530001")
            self.assertEqual(manifest["presentation"]["accent_hex"], "#8B5CF6")
            self.assertTrue(manifest["presentation"]["inherit_native_selection_animation"])
            self.assertTrue((game / "resynced_hook" / "install-state" / "latest.json").is_file())
            validation = json.loads((game / "resynced_hook" / "custom_cosmetics" / "runtime-validation.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "staged")
            self.assertEqual(validation["transaction_id"], state["transaction_id"])

    def test_failure_restores_previous_slot_selection_and_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            slot = game / "resynced_hook" / "custom_cosmetics" / "test-slot-sails"
            slot.mkdir(parents=True)
            (slot / "previous.txt").write_text("previous", encoding="utf-8")
            active = slot.parent / "active.json"
            active.write_text('{"active_slot":"previous"}\n', encoding="utf-8")
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()), \
                 mock.patch.object(injector, "atomic_copy", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    injector.install(package, game, "Test Slot", hook)
            self.assertEqual((slot / "previous.txt").read_text(encoding="utf-8"), "previous")
            self.assertEqual(active.read_text(encoding="utf-8"), '{"active_slot":"previous"}\n')
            self.assertEqual((game / "scripts" / "ResyncedScriptHook.asi").read_bytes(), b"old-hook")

    def test_unapproved_hook_is_rejected_before_game_state_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()):
                with self.assertRaises(injector.InjectError):
                    injector.install(package, game, "Test Slot", hook)
            self.assertEqual((game / "scripts" / "ResyncedScriptHook.asi").read_bytes(), b"old-hook")
            self.assertFalse((game / "resynced_hook").exists())

    def test_whole_ship_writes_four_distinct_native_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            patch_path = package / "patch.json"
            patch = json.loads(patch_path.read_text(encoding="utf-8"))
            patch["target_scope"] = "Whole ship"
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()):
                state = injector.install(package, game, "Four Slot Test", hook)
            self.assertEqual(set(state["slots"]), {"sails", "hull", "figurehead", "crew"})
            synthetic_ids = set()
            for category, slot_id in state["slots"].items():
                manifest_path = game / "resynced_hook" / "custom_cosmetics" / slot_id / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["category"], category)
                self.assertEqual(manifest["presentation"]["action_label"], "Equip")
                self.assertEqual(manifest["presentation"]["accent_name"], "violet")
                synthetic_ids.add(manifest["native_contract"]["synthetic_resource_id"])
            self.assertEqual(len(synthetic_ids), 4)

    def test_successful_install_can_be_rolled_back_transactionally(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()):
                state = injector.install(package, game, "Rollback Test", hook)
                rolled_back = injector.rollback_latest(game)
            slot = game / "resynced_hook" / "custom_cosmetics" / state["slots"]["sails"]
            self.assertFalse(slot.exists())
            self.assertEqual((game / "scripts" / "ResyncedScriptHook.asi").read_bytes(), b"old-hook")
            self.assertFalse((game / "resynced_hook" / "custom_cosmetics" / "active.json").exists())
            self.assertFalse((game / "resynced_hook" / "install-state" / "latest.json").exists())
            self.assertEqual(rolled_back["rolled_back_transaction_id"], state["transaction_id"])
            self.assertFalse(rolled_back["forge_archives_modified"])

    def test_rollback_restores_previous_runtime_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            slots = game / "resynced_hook" / "custom_cosmetics"
            slots.mkdir(parents=True)
            prior = b'{"status":"registered","process_id":99}\n'
            (slots / "runtime-validation.json").write_bytes(prior)
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()):
                injector.install(package, game, "Validation Restore", hook)
                self.assertNotEqual((slots / "runtime-validation.json").read_bytes(), prior)
                injector.rollback_latest(game)
            self.assertEqual((slots / "runtime-validation.json").read_bytes(), prior)

    def test_rollback_preflight_failure_preserves_current_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, game, hook = self.make_fixture(Path(temporary))
            previous = game / "resynced_hook" / "custom_cosmetics" / "rollback-test-sails"
            previous.mkdir(parents=True)
            (previous / "previous.txt").write_text("old", encoding="utf-8")
            with mock.patch.object(injector, "is_game_running", return_value=False), \
                 mock.patch.object(injector, "validate_game_dir", return_value=self.verified_game()), \
                 mock.patch.object(injector, "validate_hook_binary", return_value=self.approved_hook()):
                state = injector.install(package, game, "Rollback Test", hook)
                backup = Path(state["backup_paths"][0])
                __import__("shutil").rmtree(backup)
                with self.assertRaises(injector.InjectError):
                    injector.rollback_latest(game)
            current = game / "resynced_hook" / "custom_cosmetics" / state["slots"]["sails"]
            self.assertTrue((current / "textures" / "sail.png").is_file())
            self.assertEqual((game / "scripts" / "ResyncedScriptHook.asi").read_bytes(), b"new-hook")


if __name__ == "__main__":
    unittest.main()
