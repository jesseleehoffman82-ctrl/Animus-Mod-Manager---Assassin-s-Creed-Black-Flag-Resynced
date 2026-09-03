"""Animus Mod & Outfit Manager package."""

from .core import (
    FORMAT,
    GAME,
    DEFAULT_GAME_DIR,
    ForgeEditor,
    InstallRecord,
    Loader,
    LoaderError,
    Package,
    Target,
    sha256_file,
)
from .forge import ForgeArchive, Oodle
from .outfits import OutfitError, OutfitManager
from .packs import CATEGORY_CREW, CATEGORY_OUTFIT, CATEGORY_WEAPON, Pack, PackError, PackManager
from .nexus import NEXUS_GAME_ID, NexusClient, NexusError

__all__ = [
    "FORMAT",
    "GAME",
    "DEFAULT_GAME_DIR",
    "ForgeEditor",
    "InstallRecord",
    "Loader",
    "LoaderError",
    "Package",
    "Target",
    "sha256_file",
    "ForgeArchive",
    "Oodle",
    "OutfitError",
    "OutfitManager",
    "CATEGORY_OUTFIT",
    "CATEGORY_WEAPON",
    "CATEGORY_CREW",
    "Pack",
    "PackError",
    "PackManager",
    "NEXUS_GAME_ID",
    "NexusClient",
    "NexusError",
]
