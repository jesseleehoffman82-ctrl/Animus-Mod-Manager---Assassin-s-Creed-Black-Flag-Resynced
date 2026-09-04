"""Safe legacy mappings for non-category ship texture packs.

Modern Animus texture packs should encode a material id and slot in each
filename or provide an Animus manifest. A few established packs predate
the manager and contain only Workshop-facing design names. Exact mappings live
here so those packs can be managed without making fuzzy target guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneralTextureTarget:
    material_id: int
    slot: int
    display_name: str


# Black Cannons recommends the final Gold Jackdaw upgrades.
# The source archive provides one PNG per weapon type but no resource ids.
_EXACT_TARGETS = {
    "dark light mortar": GeneralTextureTarget(0x22EDF546B3F, 0, "Gold Light Mortar"),
    "dark lower cannons": GeneralTextureTarget(0x22EDF5469D7, 0, "Gold Lower Cannons"),
    "dark siege mortar": GeneralTextureTarget(0x250FA46628C, 0, "Gold Siege Mortar"),
    "dark swivel gun": GeneralTextureTarget(0x22EDF547D17, 0, "Gold Swivel Gun"),
    "dark upper cannons": GeneralTextureTarget(0x22EDF5462A5, 0, "Gold Upper Cannons"),
}


def target_for_general_filename(filename: str) -> GeneralTextureTarget | None:
    """Return a target only for an exact reviewed legacy design filename."""
    stem = filename.rsplit(".", 1)[0]
    normalized = re.sub(r"[^a-z0-9]+", " ", stem.casefold()).strip()
    return _EXACT_TARGETS.get(normalized)
