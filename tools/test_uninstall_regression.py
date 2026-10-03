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

    def test_native_zip_remains_discoverable_and_uninstalls(self):
        source = self.mod("download.zip")
        managed, package, converted = self.loader.import_package(source)
        self.assertEqual(managed.suffix, ".jmod")
        self.assertFalse(converted)
        self.loader.apply(managed)
        reopened = Loader(self.game, mods_root=self.loader.mods_root)
        self.assertIn(managed, reopened.discover_packages())
        self.assertTrue(any(row["name"] == package.name for row in self.rpc.state()["mods"]))
        reopened.disable(package.name)
        self.assertIn(managed, reopened.discover_packages())
        self.assertFalse((self.game / "data.ini").exists())
        self.rpc.dispatch("uninstall_mod", [package.name])
        self.assertEqual(reopened.discover_packages(), [])

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

    def two_file_mod(self):
        source = self.mod('two.jmod')
        with zipfile.ZipFile(source) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        manifest['targets'].append(dict(manifest['targets'][0], file='second.ini', dest='second.ini'))
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            archive.writestr('data.ini', b'mod')
            archive.writestr('second.ini', b'second')
        self.loader.apply(source)

    def test_late_conflict_does_not_remove_first_file(self):
        self.two_file_mod()
        before = self.loader.state_path.read_bytes()
        (self.game / 'second.ini').write_bytes(b'external')
        with self.assertRaises(LoaderError):
            self.rpc.dispatch('uninstall_mod', ['Example'])
        self.assertEqual((self.game / 'data.ini').read_bytes(), b'mod')
        self.assertEqual(self.loader.state_path.read_bytes(), before)
        self.assertEqual(len(self.loader.discover_packages()), 1)

    def test_mid_delete_failure_restores_earlier_file(self):
        self.two_file_mod()
        before = self.loader.state_path.read_bytes()
        unlink = Path.unlink
        def locked(path, *args, **kwargs):
            if path == self.game / 'second.ini':
                raise PermissionError('locked by game')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', locked):
            with self.assertRaises(PermissionError):
                self.loader.remove('Example')
        self.assertEqual((self.game / 'data.ini').read_bytes(), b'mod')
        self.assertEqual((self.game / 'second.ini').read_bytes(), b'second')
        self.assertEqual(self.loader.state_path.read_bytes(), before)

    def test_disable_state_save_failure_restores_files(self):
        self.two_file_mod()
        before = self.loader.state_path.read_bytes()
        save = self.loader._save_state
        calls = 0
        def fail_disabled(records):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('state write failed')
            return save(records)
        with patch.object(self.loader, '_save_state', side_effect=fail_disabled):
            with self.assertRaises(OSError):
                self.loader.disable('Example')
        self.assertEqual(self.loader.state_path.read_bytes(), before)
        self.assertEqual((self.game / 'data.ini').read_bytes(), b'mod')

    def test_missing_original_backup_refuses_remove(self):
        (self.game / 'data.ini').write_bytes(b'original')
        self.loader.apply(self.mod('one.jmod'))
        record = self.loader.list_installed()[0]
        Path(record.backups[0]['backup']).unlink()
        with self.assertRaisesRegex(LoaderError, 'backup missing'):
            self.loader.remove('Example')
        self.assertEqual((self.game / 'data.ini').read_bytes(), b'mod')

    def test_failed_rebuild_restores_enabled_library(self):
        self.outfit()
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, 'revert_all', return_value={}), \
             patch.object(self.manager, 'apply_staged', side_effect=PackError('rebuild failed')):
            with self.assertRaises(PackError):
                self.manager.remove_pack('example')
        self.assertEqual(self.manager.library_path.read_bytes(), before)
        self.assertTrue((self.manager.textures_root / 'example').is_dir())

    def test_failed_toggle_rebuild_restores_enabled_library(self):
        self.outfit()
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, 'revert_all', return_value={}), \
             patch.object(self.manager, 'apply_staged', side_effect=PackError('rebuild failed')):
            with self.assertRaises(PackError):
                self.rpc.dispatch('toggle_pack', ['outfit', 'example', False])
        self.assertEqual(self.manager.library_path.read_bytes(), before)

    def test_locked_pack_restores_library_and_deployment(self):
        self.outfit()
        before = self.manager.library_path.read_bytes()
        with patch.object(self.manager, 'revert_all', return_value={}), \
             patch.object(self.manager, 'apply_staged', return_value={}) as apply, \
             patch.object(Path, 'rename', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                self.manager.remove_pack('example')
        self.assertEqual(self.manager.library_path.read_bytes(), before)
        self.assertEqual(apply.call_count, 2)
        self.assertTrue((self.manager.textures_root / 'example').is_dir())

    def test_texture_uninstall_moves_out_of_active_library(self):
        self.outfit()
        with patch.object(self.manager, 'revert_all', return_value={}), \
             patch.object(self.manager, 'apply_staged', return_value={}):
            result = self.manager.remove_pack('example')
        self.assertFalse((self.manager.textures_root / 'example').exists())
        self.assertTrue((Path(result['recovery']) / 'meta.json').is_file())
        reopened = PackManager(self.game, self.loader.mods_root)
        self.assertEqual(reopened.list_packs(), [])


if __name__ == "__main__":
    unittest.main()
