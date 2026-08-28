"""Measured Jackdaw crew texture targets for Black Flag Resynced.

The identifiers were imported from the locally installed Ship Workshop v1.0
catalog.  Animus keeps its own compact copy so Crew installs do not depend on
Ship Workshop remaining installed or being at a particular Documents path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CrewTarget:
    texture_id: int
    material_id: int
    key: str
    width: int
    height: int

    @property
    def set_name(self) -> str:
        rules = (
            ("MrBonesB", "Skeleton Crew (B)"),
            ("MrBonesC", "Skeleton Crew (C)"),
            ("EndGame_01", "End Game 1"),
            ("EndGame_02", "End Game 2"),
            ("EndGame_03", "End Game 3"),
            ("MasterAssassin", "Master Assassin"),
            ("Animus", "Animus"),
            ("Ivory", "Ivory"),
        )
        return next((label for token, label in rules if token in self.key), "Standard")

    @property
    def piece(self) -> str:
        for piece in ("InnerShirt", "Shirt", "Torso", "Pants", "Sash", "Bandana", "Bracer"):
            if piece in self.key:
                variant = re.search(r"_([ABCD])_", self.key)
                return f"{piece} ({variant.group(1)})" if variant else piece
        return self.key

    @property
    def display_name(self) -> str:
        return f"{self.set_name}: {self.piece}"


CREW_TARGETS = (
    CrewTarget(0x239C81E435F, 0x239C81E4362, "Bracer_S_JackdawPirates", 512, 512),
    CrewTarget(0x23DE0B8D27D, 0x239C81D433B, "Bandana_S_JackdawPirates", 512, 512),
    CrewTarget(0x239C81B34F0, 0x239C81B34F3, "Sash_S_JackdawPirates", 2048, 1024),
    CrewTarget(0x239C81AF3B0, 0x239C81AF3B3, "Pants_S_JackdawPirates", 2048, 1024),
    CrewTarget(0x23F15D3E7A4, 0x23F15D3E7A7, "Pants_S_JackdawPirates_Animus", 2048, 1024),
    CrewTarget(0x241EA894858, 0x241EA89485B, "Pants_S_JackdawPirates_EndGame_03", 2048, 1024),
    CrewTarget(0x23FF13FBBE5, 0x23FF13FBBE8, "Sash_S_JackdawPirates_Animus", 2048, 1024),
    CrewTarget(0x2408F8F4880, 0x2408F8F4883, "Sash_S_JackdawPirates_EndGame_02", 2048, 1024),
    CrewTarget(0x24310F8BC23, 0x24310F8BC26, "Sash_S_JackdawPirates_EndGame_03", 2048, 1024),
    CrewTarget(0x2408F85B399, 0x2408F85B39C, "Torso_S_JackdawPirates_EndGame_01", 2048, 1024),
    CrewTarget(0x241EA871777, 0x241EA87177A, "Torso_S_JackdawPirates_EndGame_03", 2048, 1024),
    CrewTarget(0x245F6A22D0A, 0x245F6A25359, "Bandana_U_JackdawSkeletonCrew_MrBonesB", 1024, 1024),
    CrewTarget(0x24255B5BC82, 0x24255B650A3, "JackdawSkeletonCrew_MrBonesC_Pants", 2048, 1024),
    CrewTarget(0x24255B5BC8C, 0x24255B653F9, "JackdawSkeletonCrew_MrBonesC_Sash", 2048, 1024),
    CrewTarget(0x24255B5BC96, 0x24255B6542B, "JackdawSkeletonCrew_MrBonesC_Torso", 2048, 2048),
    CrewTarget(0x23F15D1612E, 0x23F15D0006F, "Pants_S_JackdawPirates_MasterAssassin", 2048, 1024),
    CrewTarget(0x245F6A22D1E, 0x245F6A27351, "Pants_U_JackdawSkeletonCrew_MrBonesB", 2048, 1024),
    CrewTarget(0x245F6A22D28, 0x245F6A28025, "Sash_U_JackdawSkeletonCrew_MrBonesB", 2048, 1024),
    CrewTarget(0x23DE0B0BF4C, 0x23DE0B057C9, "Torso_S_JackDawPirates_InnerShirt", 2048, 2048),
    CrewTarget(0x23FF13ED1A5, 0x23F15D40105, "Torso_S_JackDawPirates_InnerShirt_Animus", 2048, 2048),
    CrewTarget(0x2408F83151A, 0x23F15DE19A0, "Torso_S_JackDawPirates_InnerShirt_EndGame_01", 2048, 2048),
    CrewTarget(0x241EA8606DF, 0x23F15DE1AFE, "Torso_S_JackDawPirates_InnerShirt_EndGame_02", 2048, 2048),
    CrewTarget(0x241EA87E335, 0x23F15DF403F, "Torso_S_JackDawPirates_InnerShirt_EndGame_03", 2048, 2048),
    CrewTarget(0x2408F82421D, 0x23F15DE1742, "Torso_S_JackDawPirates_InnerShirt_Ivory", 2048, 2048),
    CrewTarget(0x23F15D122D2, 0x23F15D04A5C, "Torso_S_JackDawPirates_InnerShirt_MasterAssassin", 2048, 2048),
    CrewTarget(0x239C81C2EB0, 0x239C81C2E4D, "Torso_S_JackdawPirates", 2048, 1024),
    CrewTarget(0x241EA8174D1, 0x23F15DE1B30, "Torso_S_JackdawPirates_A_EndGame_02", 2048, 1024),
    CrewTarget(0x23F15D46F34, 0x23F15D400D3, "Torso_S_JackdawPirates_Animus", 2048, 1024),
    CrewTarget(0x24310F717E8, 0x241EA82DA62, "Torso_S_JackdawPirates_B_EndGame_02", 2048, 1024),
    CrewTarget(0x23F15DF7044, 0x23F15DE1774, "Torso_S_JackdawPirates_Ivory", 2048, 1024),
    CrewTarget(0x23F15D0BB84, 0x23F15D02AC8, "Torso_S_JackdawPirates_MasterAssassin", 2048, 1024),
    CrewTarget(0x23DE0B0EB8C, 0x23DE0B0EAA9, "Torso_S_JackdawPirates_Shirt", 2048, 2048),
    CrewTarget(0x23F15D6C60D, 0x23F15D400A1, "Torso_S_JackdawPirates_Shirt_Animus", 2048, 2048),
    CrewTarget(0x2408F8762C2, 0x23F15DE196E, "Torso_S_JackdawPirates_Shirt_EndGame_01", 2048, 2048),
    CrewTarget(0x241EA811FA4, 0x23F15DE1ACC, "Torso_S_JackdawPirates_Shirt_EndGame_02", 2048, 2048),
    CrewTarget(0x241EA88F050, 0x23F15DF400D, "Torso_S_JackdawPirates_Shirt_EndGame_03", 2048, 2048),
    CrewTarget(0x2408F80FFC8, 0x23F15DE1710, "Torso_S_JackdawPirates_Shirt_Ivory", 2048, 2048),
    CrewTarget(0x23F15D26327, 0x23F15D04A8E, "Torso_S_JackdawPirates_Shirt_MasterAssassin", 2048, 2048),
    CrewTarget(0x245F6A22D32, 0x245F6A29CF5, "Torso_U_JackdawSkeletonCrew_MrBonesB", 2048, 1024),
    CrewTarget(0x245F6A22D3C, 0x245F6A28CF9, "Torso_U_JackdawSkeletonCrew_MrBonesB_InnerShirt", 2048, 2048),
)

_BY_TEXTURE = {target.texture_id: target for target in CREW_TARGETS}


def target_for_texture(texture_id: int) -> CrewTarget | None:
    """Return the measured crew target for a texture asset id."""
    return _BY_TEXTURE.get(texture_id)


def target_for_filename(filename: str) -> CrewTarget | None:
    """Recognize a Ship Workshop export or similarly named crew texture."""
    name = filename.casefold()
    # Longest first prevents a base target matching its named variants.
    for target in sorted(CREW_TARGETS, key=lambda item: len(item.key), reverse=True):
        if target.key.casefold() in name:
            return target
    return None
