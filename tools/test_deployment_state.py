"""Automatic texture deployment and honest checkbox regressions."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import test_loader_outfits as fixture
from Animus_loader import packs
from Animus_loader.desktop_rpc import DesktopRpc


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        game = self.root / "game"
        game.mkdir()
        self.forge = game / "DataPC_boot.forge"
        with patch.object(fixture, "FORGE", self.forge):
            _, ext0, ext1, _ = fixture.build_forge()
        dds = fixture.build_dds([ext0, ext1], {
            level: bytes([32 + level]) * fixture.mip_len(max(1, 128 >> level), max(1, 128 >> level))
            for level in range(2, 8)
        })
        self.source = self.root / "Outfit"
        self.source.mkdir()
        (self.source / f"0x{fixture.MAT:X}_slot0.dds").write_bytes(dds)
        self.manager = packs.PackManager(game, self.root / "mods")
        self.rpc = DesktopRpc.__new__(DesktopRpc)
        self.rpc.manager = self.manager

    def test_install_automatically_deploys(self):
        result = self.manager.install(self.source)
        self.assertIn(result["pack"].id, self.manager.deployed_pack_ids())
        self.assertTrue(self.manager._load_journal().complete)
        self.assertTrue(self.rpc.list_packs("outfit")[0]["enabled"])

    def test_missing_or_incomplete_journal_never_shows_enabled(self):
        pack = self.manager.import_pack(self.source)
        self.manager.set_enabled(pack.id, True)
        row = self.rpc.list_packs("outfit")[0]
        self.assertFalse(row["enabled"])
        self.assertTrue(row["deployment_pending"])
        self.manager.apply_staged()
        journal = self.manager._load_journal()
        journal.complete = False
        self.manager._save_journal(journal)
        self.assertFalse(self.rpc.list_packs("outfit")[0]["enabled"])

    def test_invalid_new_pack_leaves_previous_deployment_intact(self):
        original = self.manager.install(self.source)["pack"]
        broken = self.manager.import_pack(self.source, name="Broken")
        next((broken.dir / "textures").glob("*.dds")).unlink()
        self.manager.set_enabled(broken.id, True)
        before = self.forge.read_bytes()
        journal_before = self.manager.journal_path.read_bytes()
        with self.assertRaises(packs.PackError):
            self.manager.apply_staged()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual(journal_before, self.manager.journal_path.read_bytes())
        rows = {r["id"]: r for r in self.rpc.list_packs("outfit")}
        self.assertTrue(rows[original.id]["enabled"])
        self.assertFalse(rows[broken.id]["enabled"])

    def test_mid_write_failure_restores_previous_deployment(self):
        original = self.manager.install(self.source)["pack"]
        before = self.forge.read_bytes()
        compress = packs.compress_material
        attempts = 0
        def fail_once(*args):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("simulated compression failure")
            return compress(*args)
        with patch.object(packs, "compress_material", side_effect=fail_once):
            with self.assertRaisesRegex(packs.PackError, "Previous deployment was restored"):
                self.manager.apply_staged()
        self.assertEqual(before, self.forge.read_bytes())
        self.assertEqual({original.id}, self.manager.deployed_pack_ids())


if __name__ == "__main__":
    unittest.main()
