"""Cannon RGB edits retain per-mip game alpha, including during updates."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from test_deployment_state import DeploymentTests
from Animus_loader import packs
from Animus_loader.png import encode_cannon_rgb
from Animus_loader.texture import parse_dds


class BaselineTests(unittest.TestCase):
    setUp = DeploymentTests.setUp

    def test_enabled_update_uses_original_backups(self):
        source = next(self.source.glob('*.dds'))
        archive = packs.ForgeArchive(self.forge, self.manager._oodle())
        slot = self.manager._slot_for(archive, __import__('test_loader_outfits').MAT, 0, source)
        baseline = self.manager._original_texture_dds(slot, source.read_bytes())
        self.manager.install(self.source)
        # The currently deployed DDS has different embedded pixels.
        self.assertNotEqual(source.read_bytes(), baseline)
        self.assertEqual(baseline, self.manager._original_texture_dds(slot, source.read_bytes()))
        self.manager.revert_all()
        self.assertEqual(baseline, self.manager._original_texture_dds(slot, source.read_bytes()))

    def test_corrupt_backup_rejected_without_writes(self):
        source = next(self.source.glob('*.dds'))
        self.manager.install(self.source)
        archive = packs.ForgeArchive(self.forge, self.manager._oodle())
        slot = self.manager._slot_for(archive, __import__('test_loader_outfits').MAT, 0, source)
        entry = self.manager._load_journal().external[0]
        entry.backup.write_bytes(b'broken')
        before = self.forge.read_bytes()
        with self.assertRaises(packs.PackError):
            self.manager._original_texture_dds(slot, source.read_bytes())
        self.assertEqual(before, self.forge.read_bytes())


@dataclass
class Slot:
    W: int = 8
    H: int = 8
    family: str = 'BC3'
    srgb: int = 1


def baseline_dds():
    from Animus_loader.png import _dds_header
    header = bytearray(_dds_header(8, 8, 4, b'DX10'))
    result = bytes(header) + struct.pack('<IIIII', 78, 3, 0, 1, 0)
    for level, width in enumerate((8, 4, 2, 1)):
        # Constant per-level alpha, with an opaque red BC1 colour block.
        block = bytes([level, level]) + bytes(6) + struct.pack('<HHI', 0xF800, 0, 0)
        result += block * (max(1, (width+3)//4) ** 2)
    return result


class EncoderTests(unittest.TestCase):
    def test_each_level_keeps_its_alpha_and_rgb_even_when_alpha_zero(self):
        baseline = baseline_dds()
        mips, _, _, _, _ = parse_dds(baseline)
        calls = []
        def encode(path, slot, mip_count=0):
            with Image.open(path) as image:
                level = len(calls)
                self.assertEqual(image.getchannel('A').getextrema(), (level, level))
                self.assertEqual(image.getpixel((0, 0))[:3], (40, 60, 80))
                self.assertEqual(image.size, (slot.W, slot.H))
            self.assertEqual(mip_count, 1)
            header = bytearray(baseline[:148])
            struct.pack_into('<I', header, 12, slot.H)
            struct.pack_into('<I', header, 16, slot.W)
            struct.pack_into('<I', header, 28, 1)
            calls.append(slot.W)
            return bytes(header) + mips[level]['veri']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'colour.png'
            Image.new('RGBA', (8, 8), (40, 60, 80, 255)).save(path)
            with patch('Animus_loader.png._encode_directxtex', side_effect=encode):
                output = encode_cannon_rgb(path, Slot(), baseline)
        self.assertEqual(calls, [8, 4, 2])
        self.assertEqual(output, baseline)  # includes unmodified 1x1 tail


if __name__ == '__main__':
    unittest.main()
