"""Tests for Nexus update-check logic (no network).

Verifies version comparison and that PackManager.check_updates builds correct
results using a stubbed NexusClient and hand-built pack meta (avoids the real
forge requirement).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from Animus_loader.packs import _version_gt, PackManager  # noqa: E402


class FakeNexusClient:
    def __init__(self, versions: dict):
        self.versions = versions

    def latest_version(self, mod_id: int, game_id: int = None):
        if mod_id not in self.versions:
            raise RuntimeError("network down / not found")
        return self.versions[mod_id]


def build_pack(mgr: PackManager, pack_id: str, name: str, version: str | None,
               mod_id: int | None, category: str = "outfit") -> None:
    """Hand-create a library pack with optional nexus/version meta."""
    p_dir = mgr.textures_root / pack_id
    (p_dir / "textures").mkdir(parents=True, exist_ok=True)
    (p_dir / "textures" / "0x1E_slot0.dds").write_bytes(b"D" * 16)
    meta = {"id": pack_id, "name": name, "category": category,
            "files": [], "slots": []}
    if version:
        meta["version"] = version
    if mod_id is not None:
        meta["nexus"] = {"game_id": 2996, "mod_id": mod_id}
    (p_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    lib = mgr._load_library()
    lib["packs"].append({"id": pack_id, "name": name, "category": category})
    mgr._save_library(lib)


def main() -> int:
    # 1. version compare
    assert _version_gt("2.0.0", "1.9.9") is True
    assert _version_gt("1.0.1", "1.0.0") is True
    assert _version_gt("1.0", "1.0.1") is False
    assert _version_gt("1.10", "1.9") is True
    assert _version_gt("1.0.0", "1.0.0") is False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        game = root / "game"
        game.mkdir(parents=True)
        mods = root / "mods"
        (game / "DataPC_boot.forge").write_bytes(b"scimitar" + b"\x00" * 300)
        mgr = PackManager(game_dir=game, mods_root=mods)

        build_pack(mgr, "old-skin", "Old Skin", "1.0.0", 4321)
        build_pack(mgr, "uptodate", "Up To Date", "1.2.0", 4321)
        build_pack(mgr, "non-exus", "No Nexus", None, None)
        build_pack(mgr, "badmod", "Broken", "0.1.0", 9999)  # fake client will raise

        fake = FakeNexusClient({4321: "1.2.0"})
        results = mgr.check_updates(client=fake)

        by_id = {r["id"]: r for r in results}
        assert by_id["old-skin"]["has_update"] is True, by_id["old-skin"]
        assert by_id["old-skin"]["latest"] == "1.2.0"
        assert by_id["uptodate"]["has_update"] is False, by_id["uptodate"]
        assert by_id["non-exus"]["has_update"] is False and by_id["non-exus"]["mod_id"] is None
        assert by_id["badmod"]["error"], "network/down mod should surface an error"

    print("NEXUS UPDATE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())