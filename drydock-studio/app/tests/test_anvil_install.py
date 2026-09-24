import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/"tools"/"anvil_install.py"
spec=importlib.util.spec_from_file_location("anvil_install",MODULE)
anvil=importlib.util.module_from_spec(spec)
spec.loader.exec_module(anvil)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.game=self.root/"game"
        self.design=self.root/"design"
        self.game.mkdir();self.design.mkdir()
        (self.game/"ACBlackFlag.exe").write_bytes(b"test-build")
        self.parent=self.game/"DataPC_boot_patch_01.forge"
        self.parent.write_bytes(b"scimitar-parent")
        (self.design/"finish.png").write_bytes(b"test-finish")
        self.doc=self.design/"design.jackdaw.json"
        self.doc.write_text(json.dumps(dict(schema=1,entries=[dict(output="finish.png")])))
        self.pkgdir=self.design/"exports"/"anvil"
        self.pkgdir.mkdir(parents=True)
        self.payload=self.pkgdir/"payload.forge"
        self.payload.write_bytes(b"scimitar-patch")
        self.manifest=self.pkgdir/"install-package.json"
        self.support=dict(slot_verified=True,texture_routing_verified=True,builder_revision="test")
        self.build=patch.object(anvil,"BUILD_107",anvil.digest(self.game/"ACBlackFlag.exe"))
        self.build.start();self.addCleanup(self.build.stop)
        self.data=dict(format="jackdaw-anvil-patch-v1",builder_revision="test",game_sha256=anvil.BUILD_107,
                       design_sha256=anvil.digest(self.doc),design_assets=[dict(path="finish.png",sha256=anvil.digest(self.design/"finish.png"))],
                       patches=[dict(path="payload.forge",target="DataPC_boot_patch_02.forge",sha256=anvil.digest(self.payload),
                                     parent=self.parent.name,parent_sha256=anvil.digest(self.parent))])
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data))

    def install(self):
        return anvil.install(self.manifest,self.design,self.game,self.support,running=False)

    def test_install_preserves_parent_and_records_exact_bytes(self):
        before=self.parent.read_bytes()
        result=self.install()
        self.assertEqual(result["status"],"installed")
        self.assertEqual(self.parent.read_bytes(),before)
        self.assertEqual((self.game/"DataPC_boot_patch_02.forge").read_bytes(),self.payload.read_bytes())
        self.assertEqual(anvil.read_json(result["transaction"])["status"],"installed")

    def test_running_game_blocks_before_writes(self):
        with self.assertRaisesRegex(ValueError,"running"):
            anvil.install(self.manifest,self.design,self.game,self.support,running=True)
        self.assertFalse((self.game/"DataPC_boot_patch_02.forge").exists())

    def test_unverified_slot_blocks(self):
        self.support["slot_verified"]=False
        with self.assertRaisesRegex(ValueError,"validation"):self.install()

    def test_never_overwrites_existing_mod(self):
        target=self.game/"DataPC_boot_patch_02.forge"
        target.write_bytes(b"another mod")
        with self.assertRaisesRegex(ValueError,"already exists"):self.install()
        self.assertEqual(target.read_bytes(),b"another mod")

    def test_changed_design_rejected(self):
        self.doc.write_text(self.doc.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"Design has changed"):self.install()

    def test_external_png_edit_rejected(self):
        (self.design/"finish.png").write_bytes(b"photoshop edit")
        with self.assertRaisesRegex(ValueError,"PNG has changed"):self.install()

    def test_changed_game_rejected(self):
        (self.game/"ACBlackFlag.exe").write_bytes(b"new build")
        with self.assertRaisesRegex(ValueError,"builds do not match"):self.install()

    def test_changed_parent_rejected(self):
        self.parent.write_bytes(b"updated archive")
        with self.assertRaisesRegex(ValueError,"parent archive"):self.install()

    def test_path_traversal_rejected(self):
        self.data["patches"][0]["target"]="../outside.forge";self.save()
        with self.assertRaisesRegex(ValueError,"destination"):self.install()

    def test_corrupt_payload_rejected(self):
        self.payload.write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError,"Patch content"):self.install()

    def test_missing_finish_coverage_rejected(self):
        self.data["design_assets"]=[];self.save()
        with self.assertRaisesRegex(ValueError,"cover"):self.install()

    def test_failed_copy_removes_partial_file(self):
        def fail(src,dst):
            dst.write(b"partial");raise OSError("disk full")
        with patch.object(anvil.shutil,"copyfileobj",side_effect=fail):
            with self.assertRaisesRegex(OSError,"disk full"):self.install()
        self.assertFalse((self.game/"DataPC_boot_patch_02.forge").exists())
        journals=list((self.pkgdir/"transactions").glob("*/transaction.json"))
        self.assertEqual(anvil.read_json(journals[0])["status"],"rolled-back-after-error")


if __name__=="__main__":unittest.main()
