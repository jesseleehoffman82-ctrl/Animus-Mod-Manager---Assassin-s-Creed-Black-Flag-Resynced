"""Regression for standalone sails whose metadata mimics a pixel length."""
import struct
import unittest
from Animus_loader.texture import _find_embedded

class TextureBoundaryTests(unittest.TestCase):
    def test_sail_false_length_before_real_pool(self):
        size=4096*4096
        resource=bytearray(326+size)
        struct.pack_into('<I',resource,268,size+1)
        struct.pack_into('<I',resource,322,size)
        self.assertEqual((322,326,size),_find_embedded(resource,68,len(resource)))
        self.assertEqual((322,326,size),_find_embedded(resource,68,len(resource),tol=0))

    def test_exact_mode_rejects_header_false_positive(self):
        resource=bytearray(20326)
        struct.pack_into('<I',resource,268,20001)
        self.assertIsNone(_find_embedded(resource,68,len(resource),tol=0))

    def test_legacy_material_suffix_is_supported(self):
        resource=bytearray(46+4+12000+20)
        struct.pack_into('<I',resource,46,12000)
        self.assertEqual((46,50,12000),_find_embedded(resource,14,len(resource)))

    def test_ambiguous_exact_anchors_rejected(self):
        resource=bytearray(20326)
        struct.pack_into('<I',resource,268,len(resource)-272)
        struct.pack_into('<I',resource,322,len(resource)-326)
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            _find_embedded(resource,68,len(resource))

if __name__=='__main__':unittest.main()
