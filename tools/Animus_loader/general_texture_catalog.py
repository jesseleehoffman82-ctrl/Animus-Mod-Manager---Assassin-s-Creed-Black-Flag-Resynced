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

# Material IDs checked against the live 1.0.7 archive. Order: light mortar,
# lower cannons (culverins), siege mortar, swivel, upper cannons (long guns).
CANNON_SETS = {
    "standard": (0x229598FC861, 0x22EAF606D62, 0x231BF93A09C, 0x227351E8918, 0x220F56D7D9A),
    "bronze": (0x22EDF52B81A, 0x22EDF52B706, 0x250FA48026B, 0x22EDF52B692, 0x22404FC0EBD),
    "copper": (0x22EDF546A03, 0x22EDF5462DD, 0x250FA47C824, 0x22EDF546C05, 0x22EDF5447F6),
    "silver": (0x22EDF546B20, 0x22EDF546985, 0x250FA47484A, 0x22EDF547CDC, 0x22EDF544773),
    "gold": tuple(target.material_id for target in _EXACT_TARGETS.values()),
}


def cannon_choices():
    return [{"id": key, "name": key.title() + (" (shared base textures)" if key == "standard" else ""),
             "kind": "cannon set"} for key in CANNON_SETS]


def target_for_general_filename(filename: str, cannon_set: str | None = None) -> GeneralTextureTarget | None:
    """Return a target only for an exact reviewed legacy design filename."""
    stem = filename.rsplit(".", 1)[0]
    normalized = re.sub(r"[^a-z0-9]+", " ", stem.casefold()).strip()
    original = _EXACT_TARGETS.get(normalized)
    if cannon_set is None or original is None:
        return original
    if cannon_set not in CANNON_SETS:
        raise ValueError(f"Unknown cannon set: {cannon_set}")
    index = list(_EXACT_TARGETS).index(normalized)
    return GeneralTextureTarget(CANNON_SETS[cannon_set][index], original.slot,
                                original.display_name.replace("Gold", cannon_set.title()))
