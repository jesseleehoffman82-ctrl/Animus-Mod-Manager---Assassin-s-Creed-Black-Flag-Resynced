"""Outfit library (compatibility layer over the shared texture-pack engine).

Outfits and weapons now share the single `PackManager` backend in `packs.py`
so there is exactly one active injected set at a time (no conflicts). This
module keeps the old outfit-specific names working.
"""

from __future__ import annotations

from pathlib import Path

from .packs import (
    CATEGORY_OUTFIT,
    Journal,
    JournalEmbedded,
    JournalEntry,
    OUTFIT_FORGE,
    Pack,
    PackError as OutfitError,
    PackManager,
    PackSlot as OutfitSlot,
    _make_id,
    _sha16,
)

#: Default archive outfits are injected into.
OUTFIT_FORGE = OUTFIT_FORGE


class Outfit(Pack):
    """An outfit texture pack (category "outfit")."""


class OutfitManager(PackManager):
    """Outfit-oriented view of the shared texture-pack manager."""

    def __init__(self, game_dir: Path, mods_root: Path | None = None,
                 forge_name: str = OUTFIT_FORGE):
        super().__init__(game_dir, mods_root=mods_root, forge_name=forge_name)

    def list_outfits(self) -> list[Outfit]:
        return [Outfit(o.id, o.name, o.category, o.dir, o.slots)
                for o in self.list_packs(category=CATEGORY_OUTFIT)]

    def get_outfit(self, oid: str) -> Outfit | None:
        pack = self.get_pack(oid)
        if pack is None:
            return None
        return Outfit(pack.id, pack.name, pack.category, pack.dir, pack.slots)

    def active_outfit(self) -> str | None:
        return self.active_pack_id()

    def import_outfit(self, source_dir: Path, name: str | None = None) -> Outfit:
        pack = self.import_pack(source_dir, name=name, category=CATEGORY_OUTFIT)
        return Outfit(pack.id, pack.name, pack.category, pack.dir, pack.slots)

    def install_outfit(self, source: Path, name: str | None = None) -> Outfit:
        """One-click outfit install: import + activate."""
        pack = self.import_pack(source, name=name, category=CATEGORY_OUTFIT)
        self.switch_pack(pack.id)
        return Outfit(pack.id, pack.name, pack.category, pack.dir, pack.slots)

    def switch_outfit(self, oid: str | None) -> dict:
        return self.switch_pack(oid)

    def _apply_outfit(self, outfit: Outfit) -> dict:
        return self._apply_pack(outfit)

    def _texture_to_dds(self, path: Path, slot_info):
        return super()._texture_to_dds(path, slot_info)


__all__ = [
    "Outfit",
    "OutfitError",
    "OutfitManager",
    "OutfitSlot",
    "Journal",
    "JournalEmbedded",
    "JournalEntry",
    "OUTFIT_FORGE",
    "_make_id",
    "_sha16",
]