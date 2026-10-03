"""Sail PNGs are upright designs; DDS blocks are already game-oriented."""
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from Animus_loader import png
from Animus_loader.packs import PackManager


class SailOrientationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = PackManager(self.root / 'game', self.root / 'mods')
        self.path = self.root / 'Black_Striped_Sails_BF_Logo.png'
        self.pixels = np.zeros((16,16,4),dtype=np.uint8)
        self.pixels[:8,:8] = (240,20,30,255)
        self.pixels[:8,8:] = (20,230,40,255)
        self.pixels[8:,:8] = (30,40,240,255)
        self.pixels[8:,8:] = (230,210,20,255)
        Image.fromarray(self.pixels).save(self.path)
        self.slot = SimpleNamespace(tex=0x22063685111,W=16,H=16,family='BC7',srgb=1)

    def test_flip_before_encoder_preserves_channels(self):
        expected = self.pixels[::-1].copy()
        def inspect(path, slot):
            np.testing.assert_array_equal(np.asarray(Image.open(path)),expected)
            self.assertIs(slot,self.slot)
            return b'encoded'
        with patch.object(png,'encode_png_to_dds',side_effect=inspect):
            self.assertEqual(self.manager._texture_to_dds(self.path,self.slot,sail_design=True),b'encoded')
        np.testing.assert_array_equal(np.asarray(Image.open(self.path)),self.pixels)

    def test_dds_never_flipped_or_reencoded(self):
        dds = self.root / 'sail.DDS';dds.write_bytes(b'DDS original blocks')
        with patch.object(png,'encode_sail_png') as encoder:
            self.assertEqual(self.manager._texture_to_dds(dds,self.slot,sail_design=True),dds.read_bytes())
            encoder.assert_not_called()

    def test_other_categories_keep_original_orientation(self):
        with patch.object(png,'encode_png_to_dds',return_value=b'normal') as normal, \
             patch.object(png,'encode_sail_png') as sail:
            self.assertEqual(self.manager._texture_to_dds(self.path,self.slot),b'normal')
            normal.assert_called_once_with(self.path,self.slot)
            sail.assert_not_called()

    def test_import_routes_sail_and_records_policy(self):
        with patch('Animus_loader.packs.ForgeArchive'),patch.object(self.manager,'_oodle'), \
             patch.object(self.manager,'_slot_for',return_value=self.slot), \
             patch.object(self.manager,'_texture_to_dds',return_value=b'dds') as encoder:
            pack=self.manager.import_pack(self.path,category='sail',sail_target_id='red-striped')
            self.assertTrue(encoder.call_args.kwargs['sail_design'])
            meta=self.manager._pack_meta(pack)
            self.assertEqual(list(meta['sail_orientation'].values()),['editable-png-flip-y-v1'])
            self.assertEqual(meta['sail_target_id'],'red-striped')

    @unittest.skipUnless(png._texconv_path().is_file(),'DirectXTex not bundled')
    def test_native_bc7_roundtrip_is_flipped_once(self):
        result=self.manager._texture_to_dds(self.path,self.slot,sail_design=True)
        decoded=np.asarray(Image.open(BytesIO(result)).convert('RGBA'),dtype=np.int16)
        self.assertLess(float(np.abs(decoded-self.pixels[::-1].astype(np.int16)).mean()),4)
        self.assertGreater(float(np.abs(decoded-self.pixels.astype(np.int16)).mean()),40)
        dds=self.root/'installed.dds';dds.write_bytes(result)
        self.assertEqual(self.manager._texture_to_dds(dds,self.slot,sail_design=True),result)


if __name__ == '__main__':
    unittest.main()
