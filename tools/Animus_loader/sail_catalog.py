"""Measured Sail Workshop targets for established sail texture archives.

Older sail mods contain a friendly PNG filename rather than the material/slot
identifier Animus normally requires.  Keep exact, reviewed aliases here so the
importer never has to guess from a generic word such as ``sails``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SailTarget:
    material_id: int
    slot: int
    display_name: str
    id: str = ""
    texture_id: int = 0
    kind: str = "sail-set"


def _selectable(target_id: str, container: int, texture: int, slot: int,
                display_name: str, kind: str = "sail-set") -> SailTarget:
    return SailTarget(container, slot, display_name, target_id, texture, kind)


# Independently validated resource coordinates from the installed game. The
# Spanish target is in a different source FORGE and remains hidden until the
# manager's transaction journal supports multi-FORGE texture deployments.
_SELECTABLE_TARGETS = (
    _selectable("empty", 0x21A46750CDA, 0x21A46750CD3, 0, "Plain / Empty Sails"),
    _selectable("common", 0x21824073E7D, 0x21824073E7D, 0, "White / Common Sails"),
    _selectable("assassin", 0x23005FE9CEF, 0x23005FE9CEC, 0, "Assassin Sails"),
    _selectable("athena", 0x23F9DA998FF, 0x23F9DA998FC, 0, "Athena Sails"),
    _selectable("black-bart", 0x220636B8310, 0x220636B830D, 0, "Black Bart Sails"),
    _selectable("blackbeard", 0x2382211ED47, 0x2382211ED44, 0, "Blackbeard Sails"),
    _selectable("altair", 0x2382213C96E, 0x2382213C96B, 0, "Altaïr Sails"),
    _selectable("death-vessel", 0x238221385AD, 0x238221385AA, 0, "Death Vessel Sails"),
    _selectable("elite-ship", 0x23E5DA07E60, 0x23E5DA07E5D, 0, "Elite Ship Sails"),
    _selectable("hornigold", 0x2382211F201, 0x2382211F1FE, 0, "Hornigold Sails"),
    _selectable("split-blood", 0x23E26379B08, 0x23E26379B05, 0, "Split Blood Sails"),
    _selectable("blue-white", 0x23F9DA8ADFE, 0x23F9DA8ADFE, 0, "Blue & White Sails"),
    _selectable("dark-green", 0x23F9DAA4645, 0x23F9DAA4645, 0, "Dark Green Sails"),
    _selectable("orange", 0x23F9DAAC9F1, 0x23F9DAAC9F1, 0, "Orange Sails"),
    _selectable("navy-blue", 0x23F9DAB4311, 0x23F9DAB4311, 0, "Navy Blue Sails"),
    _selectable("crimson", 0x23F9DABA3DF, 0x23F9DABA3DF, 0, "Crimson Sails"),
    _selectable("ezio", 0x23822140EA5, 0x23822140EA2, 0, "Ezio Sails"),
    _selectable("iconic-super", 0x2382211FB27, 0x2382211FB24, 0, "Iconic Super Sails"),
    _selectable("iconic-01", 0x2382214A0A6, 0x2382214A0A3, 0, "Iconic Sails 01"),
    _selectable("iconic-02", 0x21A4675500C, 0x21A46755005, 0, "Iconic Sails 02"),
    _selectable("iconic-03", 0x2382214BC86, 0x2382214BC83, 0, "Iconic Sails 03"),
    _selectable("jackdaw-02", 0x22063680AAA, 0x22063680AAA, 0, "Jackdaw Sails 02"),
    _selectable("red-striped", 0x22063685111, 0x22063685111, 0, "Red Striped Sails"),
    _selectable("kraken", 0x23DFC769C94, 0x23DFC769C91, 0, "Kraken Sails"),
    _selectable("ipswich-legendary", 0x23F9DA2E6AD, 0x23F9DA2E6AA, 0, "Legendary Ipswich Sails"),
    _selectable("animus-store", 0x23F9DA186D5, 0x23F9DA186D2, 0, "Animus Sails"),
    _selectable("master-assassin-store", 0x23822122380, 0x2382212237D, 0, "Master Assassin Sails"),
    _selectable("pirate-04", 0x23822135AC0, 0x23822135ABD, 0, "Pirate Sails 04"),
    _selectable("pirate-05", 0x23822124C4E, 0x23822124C4B, 0, "Pirate Sails 05"),
    _selectable("pirate-06", 0x23822136B45, 0x23822136B42, 0, "Pirate Sails 06"),
    _selectable("stede-bonnet", 0x21B0A9E1CEE, 0x21B0A9E1CE7, 0, "Stede Bonnet Sails"),
    _selectable("blue-white-checkered", 0x2473BD38B59, 0x2473BD38B59, 0, "Blue & White Checkered Sails"),
    _selectable("connor", 0x2382214013C, 0x23822140139, 0, "Connor Kenway Sails"),
    _selectable("dark-compass", 0x23F9DA2CDE2, 0x23F9DA2CDE2, 0, "Dark Compass Emblem Sails"),
    _selectable("emblem-animus", 0x23DB381E3BA, 0x23F9DA1C7D2, 0, "Animus Emblem Layer", "emblem"),
    _selectable("emblem-black-skull-a", 0x21A4674E368, 0x2191055484E, 1, "Black Skull Emblem Layer A", "emblem"),
    _selectable("emblem-black-skull-b", 0x21A4674E368, 0x21910551545, 0, "Black Skull Emblem Layer B", "emblem"),
    _selectable("emblem-british", 0x21B0A9BAE70, 0x21B0A9C12F2, 0, "British Emblem Layer", "emblem"),
    _selectable("emblem-death-vessel", 0x220636CB57C, 0x238221385B2, 0, "Death Vessel Emblem Layer", "emblem"),
    _selectable("emblem-fearless", 0x2353F878FC7, 0x24E40919BBE, 0, "Fearless Emblem Layer", "emblem"),
    _selectable("emblem-ipswich", 0x2353F878FD1, 0x23F9DA891C4, 0, "Ipswich Emblem Layer", "emblem"),
    _selectable("emblem-master-assassin", 0x2353F878CBA, 0x238221223A5, 0, "Master Assassin Emblem Layer", "emblem"),
    _selectable("emblem-portuguese", 0x21B0A9BAE80, 0x21B0A9C3450, 0, "Portuguese Emblem Layer", "emblem"),
    _selectable("emblem-ranger", 0x23EB09905C4, 0x241415F02EE, 0, "Ranger Emblem Layer", "emblem"),
    _selectable("emblem-ultimate", 0x23DB382343C, 0x23F9DA2FF72, 0, "Ultimate Emblem Layer", "emblem"),
)

_BY_ID = {target.id: target for target in _SELECTABLE_TARGETS}


def sail_targets() -> tuple[SailTarget, ...]:
    # Legacy IDs remain resolvable for packs installed with the longer picker.
    main_ids = (
        "common", "empty", "red-striped", "blue-white", "dark-green",
        "orange", "navy-blue", "crimson", "blue-white-checkered", "dark-compass",
    )
    return tuple(_BY_ID[target_id] for target_id in main_ids)


def get_sail_target(target_id: str) -> SailTarget | None:
    return _BY_ID.get(str(target_id).casefold().strip())


_RED_STRIPED = SailTarget(0x22063685111, 0, "Red Striped Sails")

# IDs are taken from Sail Workshop's runtime-resolved catalogue. Each resource
# is also the material containing its single TextureMap slot in DataPC_boot.forge.
_EXACT_TARGETS = {
    "red striped sails": _RED_STRIPED,
    # Black Striped Sails BF Logo was authored for the Jackdaw-only
    # Red Striped slot, but its archive predates target IDs in filenames.
    "black striped sails bf logo": _RED_STRIPED,
    "white common sails": SailTarget(0x21824073E7D, 0, "White / Common Sails"),
    "blue white sails": SailTarget(0x23F9DA8ADFE, 0, "Blue & White Sails"),
    "dark green sails": SailTarget(0x23F9DAA4645, 0, "Dark Green Sails"),
    "orange sails": SailTarget(0x23F9DAAC9F1, 0, "Orange Sails"),
    "navy blue sails": SailTarget(0x23F9DAB4311, 0, "Navy Blue Sails"),
    "crimson sails": SailTarget(0x23F9DABA3DF, 0, "Crimson Sails"),
    "dark compass emblem sails": SailTarget(0x23F9DA2CDE2, 0, "Dark Compass Emblem Sails"),
    "blue white checkered sails": SailTarget(0x2473BD38B59, 0, "Blue & White Checkered Sails"),
}


def target_for_sail_filename(filename: str) -> SailTarget | None:
    """Return a target only for an exact known Sail Workshop-style name."""
    stem = filename
    while "." in stem and stem.rsplit(".", 1)[1].casefold() in {"png", "dds"}:
        stem = stem.rsplit(".", 1)[0]
    normalized = re.sub(r"[^a-z0-9]+", " ", stem.casefold()).strip()
    return _EXACT_TARGETS.get(normalized)
