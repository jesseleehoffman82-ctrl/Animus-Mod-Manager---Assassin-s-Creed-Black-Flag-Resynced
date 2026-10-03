"""Cannon selection uses exact reviewed filename mappings, not fuzzy guesses."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from Animus_loader.core import Loader
from Animus_loader.desktop_rpc import DesktopRpc
from Animus_loader.packs import PackManager, PackError
from Animus_loader.general_texture_catalog import CANNON_SETS, target_for_general_filename, cannon_choices

NAMES = ["Dark Light Mortar.png", "Dark Lower Cannons.png", "Dark Siege Mortar.png",
         "Dark Swivel Gun.png", "Dark Upper Cannons.png"]


class CannonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Black Cannons.zip"
        with zipfile.ZipFile(self.source, "w") as z:
            for name in NAMES:
                z.writestr(name, b"fixture")
        self.rpc = DesktopRpc.__new__(DesktopRpc)
        self.rpc.game_dir = self.root / "game"
        self.rpc.loader = Loader(self.rpc.game_dir, self.root / "mods")
        self.rpc.manager = PackManager(self.rpc.game_dir, self.root / "mods")
        self.rpc.logs = []

    def test_choices_do_not_import_or_deploy(self):
        with patch.object(self.rpc.manager, "import_pack") as importer:
            result, state = self.rpc.dispatch("install_mod_path", [str(self.source)])
        self.assertTrue(result["requires_cannon_target"])
        self.assertEqual(len(result["targets"]), 5)
        self.assertIsNone(state)
        importer.assert_not_called()
        self.assertFalse(self.rpc.manager.library_path.exists())
        self.assertFalse(self.rpc.game_dir.exists())

    def test_all_tiers_import_with_selected_ids(self):
        info = SimpleNamespace(tex=42, W=1024, H=1024, family="BC7", srgb=1)
        with patch("Animus_loader.packs.ForgeArchive"), patch.object(self.rpc.manager,"_oodle"), \
             patch.object(self.rpc.manager,"_slot_for",return_value=info), \
             patch.object(self.rpc.manager,"_texture_to_dds",return_value=b"dds fixture"):
            for tier, ids in CANNON_SETS.items():
                pack = self.rpc.manager.import_pack(self.source,category="general",cannon_set=tier)
                self.assertEqual(tuple(s.mat for s in pack.slots), ids)
                meta = self.rpc.manager._pack_meta(pack)
                self.assertEqual(meta["cannon_set"],tier)
                self.assertTrue(all(name.startswith(tier.title()) for name in meta["replaces"]))
                choices = self.rpc._cannon_targets(self.source,pack.id)
                self.assertEqual(choices["default_id"],tier)

    def test_unrecognized_and_invalid_targets_not_guessed(self):
        self.assertIsNone(target_for_general_filename("Random cannon.png","silver"))
        self.assertEqual(target_for_general_filename(NAMES[1],"silver").material_id,0x22EDF546985)
        self.assertEqual(target_for_general_filename(NAMES[1]).material_id,0x22EDF5469D7)
        with self.assertRaises(PackError):
            self.rpc.manager.import_pack(self.source,category="general",cannon_set="made-up")
        self.assertEqual(self.rpc.manager.list_packs(),[])

    def test_cannon_set_forwarded_to_preview_and_update(self):
        pack = SimpleNamespace(id="old",name="Cannons",category="general",dir=self.root)
        meta = {"version":"1","cannon_set":"silver"}
        incoming = SimpleNamespace(id="new",name="New",category="general",dir=self.root,slots=[])
        with patch.object(self.rpc.manager,"get_pack",return_value=pack), \
             patch.object(PackManager,"_pack_meta",return_value=meta), \
             patch.object(PackManager,"import_pack",return_value=incoming) as importer, \
             patch.object(self.rpc.manager,"set_enabled"), patch.object(self.rpc.manager,"remove_pack"), \
             patch.object(self.rpc,"state",return_value={}):
            self.rpc._preview_update("general","old",self.source)
            self.assertEqual(importer.call_args.kwargs["cannon_set"],"silver")
            self.rpc.dispatch("update_pack_path",["general","old",str(self.source)])
            self.assertEqual(importer.call_args.kwargs["cannon_set"],"silver")
            self.rpc.dispatch("update_pack_path",["general","old",str(self.source),"copper"])
            self.assertEqual(importer.call_args.kwargs["cannon_set"],"copper")


if __name__ == "__main__":
    unittest.main()
