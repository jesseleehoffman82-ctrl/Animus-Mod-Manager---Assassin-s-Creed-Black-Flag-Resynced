"""Texture pack library and FORGE texture injector.

Outfits, weapons, crew skins, and sail designs are texture packs that write into the same
`DataPC_boot.forge` material+slot locations. They share one backend so there is
exactly ONE active injected set at a time -- activating a weapon reverts any
active outfit and vice versa. Conflicts are impossible by design.

Backend notes
-------------
Injection happens on `DataPC_boot.forge`:
  * external texture mips (rid = (0xA0000000000 | tex) << 20 | lvl) are
    same-size writes at their existing archive offsets;
  * the embedded mip tail lives inside the compressed material; editing it
    means re-packing the material, appending it to the end of the forge and
    repointing that material's TOC entry.

Every write is journaled with byte backups so any pack can be reverted to
vanilla independently (and "restore all" replays the reversals).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from copy import copy
from dataclasses import dataclass, field, replace
from pathlib import Path

from .forge import ForgeArchive, ForgeError, Oodle, compress_material, decompress_bms
from .texture import PlanItem, parse_filename, plan_texture
from .crew_catalog import get_crew_target, target_for_filename, target_for_texture
from .general_texture_catalog import target_for_general_filename
from .sail_catalog import get_sail_target, target_for_sail_filename

#: Default archive packs are injected into.
OUTFIT_FORGE = "DataPC_boot.forge"

CATEGORY_OUTFIT = "outfit"
CATEGORY_WEAPON = "weapon"
CATEGORY_CREW = "crew"
CATEGORY_SAIL = "sail"
CATEGORY_GENERAL = "general"
PACK_CATEGORIES = (CATEGORY_OUTFIT, CATEGORY_WEAPON, CATEGORY_CREW, CATEGORY_SAIL, CATEGORY_GENERAL)


class PackError(Exception):
    """Raised for texture-pack library or injection problems."""


@dataclass
class PackSlot:
    mat: int
    slot: int
    tex: int
    W: int
    H: int
    family: str | None
    srgb: int


@dataclass
class Pack:
    id: str
    name: str
    category: str
    dir: Path
    slots: list[PackSlot] = field(default_factory=list)


@dataclass
class JournalEntry:
    rid: int
    offset: int
    length: int
    sha_orig: str
    sha_new: str
    backup: Path
    pack_id: str = ""


@dataclass
class JournalEmbedded:
    mat: int
    toc_pos: int
    orig_off: int
    orig_len: int
    new_off: int
    new_len: int
    pack_id: str = ""


@dataclass
class Journal:
    packs: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    forge: str = ""
    forge_size: int = 0
    external: list[JournalEntry] = field(default_factory=list)
    embedded: list[JournalEmbedded] = field(default_factory=list)
    appended: list = field(default_factory=list)  # [ [off, len], ... ]
    complete: bool = True
    overrides: list[str] = field(default_factory=list)


def _sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class PackManager:
    """Coordinates the shared texture-pack library + journaled forge injection.

    One active set at a time: `switch_pack` reverts whatever is active (outfit
    or weapon) and injects the new pack.
    """

    def __init__(self, game_dir: Path, mods_root: Path | None = None,
                 forge_name: str = OUTFIT_FORGE):
        self.game_dir = Path(game_dir)
        self.root = Path(__file__).resolve().parents[2]
        self.mods_root = Path(mods_root) if mods_root else (self.root / "mods")
        self.textures_root = self.mods_root / "textures"
        self.library_path = self.textures_root / "library.json"
        self.journal_path = self.textures_root / "journal.json"
        self.backups_dir = self.textures_root / "backups"
        self.forge_path = self.game_dir / forge_name
        for d in (self.textures_root, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # library
    # ------------------------------------------------------------------ #
    def _load_library(self) -> dict:
        if not self.library_path.is_file():
            return {"packs": [], "active": None}
        try:
            return json.loads(self.library_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"packs": [], "active": None}

    def _save_library(self, lib: dict) -> None:
        self.library_path.write_text(
            json.dumps(lib, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ #
    # staged state (MO2-style enable + order)
    # ------------------------------------------------------------------ #
    def _staged(self, category: str) -> list[str]:
        """Return the ordered pack ids staged (enabled) for a category.

        The list is in load order: the LAST entry is highest priority (bottom
        of the list wins), matching MO2. Existing "active" is folded in so old
        single-pack installs keep working.
        """
        lib = self._load_library()
        packs = [p for p in lib.get("packs", [])
                 if p.get("category", CATEGORY_OUTFIT) == category]
        order = [p["id"] for p in packs]
        enabled = lib.get("enabled", {})
        staged = [pid for pid in order if enabled.get(pid, False)]
        active = lib.get("active")
        if active and active in order and active not in staged:
            staged.append(active)
        return staged

    def set_enabled(self, pack_id: str, enabled: bool) -> None:
        """Enable/disable a pack (staged; not written until apply)."""
        lib = self._load_library()
        lib.setdefault("enabled", {})
        lib["enabled"][pack_id] = bool(enabled)
        if not enabled and lib.get("active") == pack_id:
            lib["active"] = None
        self._save_library(lib)

    def set_order(self, category: str, ordered_ids: list[str]) -> None:
        """Persist a new visual order for a category (bottom = highest priority)."""
        lib = self._load_library()
        category_packs = [p for p in lib.get("packs", [])
                          if p.get("category", CATEGORY_OUTFIT) == category]
        known = {p["id"] for p in category_packs}
        by_id = {p["id"]: p for p in category_packs}
        ordered = [by_id[pid] for pid in ordered_ids if pid in known]
        # any category pack not in the new order stays at the end
        listed = {pid for pid in ordered_ids}
        for p in category_packs:
            if p["id"] not in listed:
                ordered.append(p)
        others = [p for p in lib.get("packs", [])
                  if p.get("category", CATEGORY_OUTFIT) != category]
        lib["packs"] = others + ordered
        self._save_library(lib)

    def list_packs(self, category: str | None = None) -> list[Pack]:
        lib = self._load_library()
        packs = []
        for meta in lib.get("packs", []):
            if category and meta.get("category", CATEGORY_OUTFIT) != category:
                continue
            pack_id = meta["id"]
            p_dir = self.textures_root / pack_id
            meta_path = p_dir / "meta.json"
            slots: list[PackSlot] = []
            if meta_path.is_file():
                try:
                    m = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    m = {}
                slots = [PackSlot(int(s["mat"], 16), s["slot"], int(s["tex"], 16),
                                  s["W"], s["H"], s.get("family"), s.get("srgb", 0))
                         for s in m.get("slots", [])]
            packs.append(Pack(pack_id, meta.get("name", pack_id),
                              meta.get("category", CATEGORY_OUTFIT), p_dir, slots))
        return packs

    def get_pack(self, pack_id: str) -> Pack | None:
        for p in self.list_packs():
            if p.id == pack_id:
                return p
        return None

    def active_pack_id(self) -> str | None:
        return self._load_library().get("active")

    def active_pack(self) -> Pack | None:
        aid = self.active_pack_id()
        if aid is None:
            return None
        return self.get_pack(aid)

    # ------------------------------------------------------------------ #
    # import
    # ------------------------------------------------------------------ #
    def import_pack(self, source_dir: Path, name: str | None = None,
                    category: str = CATEGORY_OUTFIT,
                    sail_target_id: str | None = None,
                    crew_target_id: str | None = None,
                    _archive_name: str | None = None,
                    cannon_set: str | None = None) -> Pack:
        """Import a folder/archive of DDS/PNG textures (named mat id + slot).

        `source_dir` can be a folder, a `.zip`, a `.7z` (if py7zr installed),
        a single `.dds`, or a single `.png`. Textures are found recursively so
        packs that ship nested in a subfolder still work.
        """
        source_dir = Path(source_dir)
        if source_dir.is_file():
            import shutil
            import tempfile
            suffix = source_dir.suffix.lower()
            if suffix in (".zip", ".7z", ".rar", ".tar", ".tar.gz", ".tgz"):
                tmp = Path(tempfile.mkdtemp(prefix="animus_pack_"))
                try:
                    self._extract_archive(source_dir, tmp)
                    detected_name = name or self._archive_pack_name(tmp, source_dir.stem)
                    return self.import_pack(tmp, name=detected_name, category=category,
                                            sail_target_id=sail_target_id,
                                            crew_target_id=crew_target_id,
                                            _archive_name=source_dir.stem, cannon_set=cannon_set)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            if suffix in (".dds", ".png"):
                self._validate_pack_category([source_dir], category, {}, source_dir.parent)
                return self._import_files([source_dir], name or source_dir.stem,
                                          category, str(source_dir), {}, sail_target_id,
                                          crew_target_id, cannon_set)
            raise PackError(f"Unsupported pack file: {source_dir.name}")
        if not source_dir.is_dir():
            raise PackError(f"Not a folder or archive: {source_dir}")

        files = sorted(
            p for p in source_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in (".dds", ".png")
            and not any(part.lower() in {"_reference_do_not_edit", "reference_do_not_edit"}
                        for part in p.parts)
        )
        if not files:
            raise PackError(f"No .dds or .png files found in {source_dir}")
        metadata = self._pack_metadata(source_dir)
        if "version" not in metadata and _archive_name:
            # Nexus download filenames carry an explicit version before their
            # timestamp; do not mistake a resource id or game version for it.
            match = re.search(r"(?i)\s+\d+\s+v?(\d+(?:\.\d+)*(?:\s*(?:alpha|beta))?)\s+\d{4}-\d{2}-\d{2}T\S+\s+[A-Za-z0-9]+$", _archive_name)
            if not match:
                match = re.search(r"(?i)(?:^|[ _-])v(\d+(?:\.\d+)+(?:[-_](?:alpha|beta)\d*)?)(?=$|[ _-])", _archive_name)
            if match:
                metadata["version"] = match.group(1).strip()
        self._validate_pack_category(files, category, metadata, source_dir,
                                     archive_name=_archive_name)
        name = (name or metadata.get("name") or source_dir.name).strip() or "Unnamed Pack"
        return self._import_files(files, name, category, str(source_dir), metadata,
                                  sail_target_id, crew_target_id, cannon_set)

    @staticmethod
    def _validate_pack_category(files: list[Path], requested: str,
                                metadata: dict, source_dir: Path,
                                archive_name: str | None = None) -> None:
        """Reject wrong categories; Weapons also requires positive identification."""
        declared = str(metadata.get("pack_category") or "").casefold().strip()
        aliases = {
            "outfits": CATEGORY_OUTFIT, "outfit": CATEGORY_OUTFIT,
            "weapons": CATEGORY_WEAPON, "weapon": CATEGORY_WEAPON,
            "crew": CATEGORY_CREW,
            "sails": CATEGORY_SAIL, "sail": CATEGORY_SAIL,
            "general": CATEGORY_GENERAL, "ship": CATEGORY_GENERAL,
        }
        detected = aliases.get(declared)
        names = " ".join([
            archive_name or "", source_dir.name,
            str(metadata.get("name") or ""),
            *(str(path.relative_to(source_dir)) for path in files),
        ]).casefold()
        if detected is None and any(target_for_filename(path.name) for path in files):
            detected = CATEGORY_CREW
        if detected is None or requested == CATEGORY_WEAPON:
            markers = {
                CATEGORY_SAIL: ("sail",),
                CATEGORY_GENERAL: ("cannon", "mortar", "swivel", "culverin", "longgun",
                                   "figurehead", "ship hull", "jackdaw hull", "ship wheel", "cabin"),
                CATEGORY_OUTFIT: ("outfit", "robe", "redingote"),
                CATEGORY_WEAPON: ("pistol", "sword", "blade", "weapon", "blunderbuss", "musket"),
            }
            matches = [kind for kind, words in markers.items()
                       if any(word in names for word in words)]
            # An outfit must not become a weapon just because the archive
            # also mentions swords, or its manifest says 'weapon'.
            if requested == CATEGORY_WEAPON and CATEGORY_OUTFIT in matches:
                detected = CATEGORY_OUTFIT
            elif detected is None and len(matches) == 1:
                detected = matches[0]
        if detected is not None and detected != requested:
            destinations = {
                CATEGORY_OUTFIT: "Outfits",
                CATEGORY_WEAPON: "Weapons",
                CATEGORY_CREW: "Crew",
                CATEGORY_SAIL: "Sails",
                CATEGORY_GENERAL: "Mods",
            }
            raise PackError(
                f"This appears to be a {detected} texture pack. "
                f"Install it from the {destinations[detected]} tab instead."
            )
        if requested == CATEGORY_WEAPON and detected is None:
            raise PackError(
                "This pack could not be identified as a weapon texture pack. "
                "Nothing was installed. Outfit packs belong in the Outfits tab. "
                "Weapon packs need an identifying name (such as pistol or sword) "
                "or metadata declaring their weapon category."
            )

    @staticmethod
    def _pack_metadata(source_dir: Path) -> dict:
        """Extract optional author/version data shipped inside an ordinary pack.

        Mod archives are inconsistent, so this deliberately accepts common
        manifest JSON keys and explicit README labels while avoiding guesses
        based on folder or archive names.
        """
        metadata: dict = {}
        json_names = {"manifest.json", "mod.json", "info.json", "metadata.json", "meta.json"}
        key_aliases = {
            "name": ("name", "mod_name", "title"),
            "author": ("author", "authors", "uploaded_by", "uploader", "created_by", "creator"),
            "version": ("version", "mod_version"),
            "description": ("description", "summary"),
            "pack_category": ("pack_category", "texture_category", "category", "type"),
        }

        def find_value(data, aliases):
            if not isinstance(data, dict):
                return None
            lowered = {str(key).casefold(): value for key, value in data.items()}
            for alias in aliases:
                value = lowered.get(alias)
                if aliases == ("version", "mod_version") and isinstance(value, (int, float)) and not isinstance(value, bool):
                    return str(value)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, list):
                    names = [str(item).strip() for item in value if str(item).strip()]
                    if names:
                        return ", ".join(names)
            for value in data.values():
                if isinstance(value, dict):
                    found = find_value(value, aliases)
                    if found:
                        return found
            return None

        candidates = sorted(
            path for path in source_dir.rglob("*")
            if path.is_file() and path.name.casefold() in json_names
            and path.stat().st_size <= 512 * 1024)
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            for field, aliases in key_aliases.items():
                if field not in metadata:
                    value = find_value(data, aliases)
                    if value:
                        metadata[field] = value

        readmes = sorted(
            path for path in source_dir.rglob("*")
            if path.is_file() and "readme" in path.name.casefold()
            and path.suffix.casefold() in {".txt", ".md"}
            and path.stat().st_size <= 512 * 1024)
        readme_texts = []
        for path in readmes:
            try:
                readme_texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue

        # Workshop exports name the exact vanilla wardrobe/sail entry in their
        # first line. Keep that separate from the mod's own display name.
        for text in readme_texts:
            match = re.search(
                r"(?im)^(?:OUTFIT|SAIL|SHIP) WORKSHOP export\s*--\s*(.+?)(?:\s*\(|\s*$)", text)
            if not match:
                match = re.search(
                    r"(?im)^\s*(?:replaces\s+(?:vanilla\s+)?(?:outfit|sail)|vanilla\s+(?:outfit|sail)|(?:outfit|sail)\s+slot)\s*[:=-]\s*(.+?)\s*$",
                    text,
                )
            if match:
                metadata["replaces"] = [match.group(1).strip()]
                heading = match.group(0).casefold()
                if re.search(r"\boutfit\b", heading):
                    metadata.setdefault("pack_category", CATEGORY_OUTFIT)
                elif re.search(r"\bsail\b", heading):
                    metadata.setdefault("pack_category", CATEGORY_SAIL)
                break

        if "version" not in metadata:
            for text in readme_texts:
                match = re.search(r"(?im)^\s*(?:mod\s+)?version\s*[:=]\s*(\S[^\r\n]*)", text)
                if match:
                    metadata["version"] = match.group(1).strip()
                    break
        if "author" not in metadata:
            author_pattern = re.compile(
                r"(?im)^\s*(?:mod\s+author|author|created\s+by|made\s+by)\s*[:=-]\s*(.+?)\s*$")
            for text in readme_texts:
                match = author_pattern.search(text)
                if match:
                    metadata["author"] = match.group(1).strip()
                    break
        return metadata

    @staticmethod
    def _archive_pack_name(extracted: Path, fallback: str) -> str:
        """Keep the mod title distinct from the vanilla outfit it replaces."""
        cleaned_title = re.sub(
            r"\s+\d+\s+\S+\s+\d{4}-\d{2}-\d{2}T.*$", "", fallback).strip()
        if cleaned_title and cleaned_title != fallback:
            return cleaned_title
        children = [p for p in extracted.iterdir()
                    if p.name not in {"__MACOSX", ".DS_Store"}]
        if len(children) == 1 and children[0].is_dir():
            return children[0].name.replace("_", " ").strip()
        return fallback.strip() or "Imported Pack"

    @staticmethod
    def _find_7z() -> str | None:
        """Locate Animus' bundled 7-Zip, then a system installation."""
        import shutil
        bundled = (Path(__file__).resolve().parents[2] / "tools" /
                   "third_party" / "7zip" / "7z.exe")
        if bundled.is_file():
            return str(bundled)
        exe = (shutil.which("7z") or shutil.which("7za")
               or shutil.which("7zr") or shutil.which("unrar")
               or shutil.which("rar") or shutil.which("bsdtar"))
        if exe:
            return exe
        candidates = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files\WinRAR\Rar.exe",
        ]
        if os.name == "nt":
            candidates.append(r"C:\Program Files\WinRAR\UnRAR.exe")
        for c in candidates:
            p = Path(c)
            if p.is_file():
                return str(p)
        return None

    @staticmethod
    def _extract_archive(src: Path, dest: Path) -> None:
        import shutil
        import subprocess
        import tarfile
        import zipfile
        suffix = src.suffix.lower()
        root = dest.resolve()
        if suffix == ".zip":
            with zipfile.ZipFile(src) as z:
                for member in z.infolist():
                    # guard against zip-slip (path traversal)
                    target = (dest / member.filename).resolve()
                    if target != root and root not in target.parents:
                        raise PackError(f"Unsafe path in archive: {member.filename}")
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as srcf, open(target, "wb") as dstf:
                            shutil.copyfileobj(srcf, dstf)
        elif suffix == ".tar" or suffix == ".gz" or suffix == ".tgz":
            with tarfile.open(src) as t:
                for member in t.getmembers():
                    if not (member.isdir() or member.isreg()):
                        raise PackError(f"Archive contains an unsupported link or device: {member.name}")
                    member_path = Path(member.name)
                    target = (dest / member_path).resolve()
                    if target != root and root not in target.parents:
                        raise PackError(f"Unsafe path in archive: {member.name}")
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source_file = t.extractfile(member)
                    if source_file is None:
                        raise PackError(f"Could not read archive member: {member.name}")
                    with source_file, open(target, "wb") as destination_file:
                        shutil.copyfileobj(source_file, destination_file)
        elif suffix in {".7z", ".rar"}:
            exe = PackManager._find_7z()
            if exe:
                try:
                    completed = subprocess.run(
                        [exe, "x", str(src), f"-o{dest}", "-y"],
                        check=True, capture_output=True, text=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or "7-Zip extraction failed").strip()
                    raise PackError(f"Could not unpack {src.name}: {detail}") from exc
            elif suffix == ".7z":
                try:
                    import py7zr
                    with py7zr.SevenZipFile(src) as z:
                        z.extractall(dest)
                except ImportError as exc:
                    raise PackError("Animus' bundled 7-Zip extractor is missing.") from exc
            else:
                raise PackError("Animus' bundled 7-Zip extractor is missing.")

            # Reject links and any result resolving outside the temporary
            # extraction directory before the importer reads the content.
            for extracted in dest.rglob("*"):
                if extracted.is_symlink():
                    raise PackError(f"Archive contains an unsupported link: {extracted.name}")
                if root not in extracted.resolve().parents and extracted.resolve() != root:
                    raise PackError(f"Unsafe path extracted from archive: {extracted}")
        else:
            raise PackError(f"Unsupported archive: {src.name} (use .zip, .7z, or .rar)")

    def _import_files(self, files: list, name: str, category: str,
                      source_label: str, metadata: dict | None = None,
                      sail_target_id: str | None = None,
                      crew_target_id: str | None = None,
                      cannon_set: str | None = None) -> Pack:
        """Validate + copy a set of texture files into a new library pack."""
        import shutil
        if cannon_set is not None:
            from .general_texture_catalog import CANNON_SETS
            if category != CATEGORY_GENERAL or cannon_set not in CANNON_SETS:
                raise PackError("Select a supported cannon set in the Mods tab.")
        pack_id = _make_id(name)
        p_dir = self.textures_root / pack_id
        tex_dir = p_dir / "textures"
        tex_dir.mkdir(parents=True, exist_ok=True)
        try:
            archive = ForgeArchive(self.forge_path, self._oodle())

            selected_sail = None
            if category == CATEGORY_SAIL and sail_target_id:
                selected_sail = get_sail_target(sail_target_id)
                if selected_sail is None:
                    raise PackError(f"Unknown vanilla sail target: {sail_target_id}")
                if len(files) != 1:
                    raise PackError(
                        "This sail archive contains multiple texture images. "
                        "Install one sail design at a time so its vanilla target is unambiguous."
                    )

            selected_crew = None
            if category == CATEGORY_CREW and crew_target_id and crew_target_id != "auto":
                selected_crew = get_crew_target(crew_target_id)
                if selected_crew is None:
                    raise PackError(f"Unknown vanilla crew target: {crew_target_id}")
                if len(files) != 1:
                    raise PackError(
                        "This crew archive contains multiple texture images. "
                        "Choose automatic filename detection for a full crew pack, or install "
                        "one texture at a time when assigning an individual vanilla target."
                    )

            slots: list[PackSlot] = []
            imported = []
            sail_orientations = {}
            errors: list[str] = []
            replaces: set[str] = set()
            for path in files:
                mat, slot, kind = parse_filename(path.name)
                if selected_sail is not None:
                    mat, slot, kind = (selected_sail.material_id,
                                       selected_sail.slot, "selected-sail-target")
                if selected_crew is not None:
                    mat, slot, kind = (selected_crew.material_id, 0,
                                       "selected-crew-target")
                if mat is None and category == CATEGORY_CREW:
                    crew_target = target_for_filename(path.name)
                    if crew_target is not None:
                        mat, slot, kind = crew_target.material_id, 0, "crew-catalog"
                if mat is None and category == CATEGORY_GENERAL:
                    general_target = target_for_general_filename(path.name, cannon_set)
                    if general_target is not None:
                        mat, slot, kind = general_target.material_id, general_target.slot, "general-catalog"
                if mat is None and category == CATEGORY_SAIL:
                    sail_target = target_for_sail_filename(path.name)
                    if sail_target is not None:
                        mat, slot, kind = sail_target.material_id, sail_target.slot, "sail-catalog"
                if mat is None:
                    errors.append(f"{path.name}: {kind}")
                    continue
                try:
                    slot_info = self._slot_for(archive, mat, slot, path)
                except (ValueError, ForgeError) as exc:
                    errors.append(f"{path.name}: {exc}")
                    continue
                dest = tex_dir / f"0x{mat:X}_slot{slot}.dds"
                if category == CATEGORY_GENERAL and kind == "general-catalog":
                    data = self._texture_to_dds(path, slot_info, preserve_game_alpha=True)
                elif category == CATEGORY_SAIL:
                    data = self._texture_to_dds(path, slot_info, sail_design=True)
                    sail_orientations[str(dest.relative_to(p_dir))] = (
                        "game-native-dds" if path.suffix.lower() == ".dds"
                        else "editable-png-flip-y-v1")
                else:
                    data = self._texture_to_dds(path, slot_info)
                dest.write_bytes(data)
                imported.append(str(dest.relative_to(p_dir)))
                slots.append(PackSlot(mat, slot, slot_info.tex, slot_info.W,
                                      slot_info.H, slot_info.family, slot_info.srgb))
                if category == CATEGORY_CREW:
                    crew_target = selected_crew or target_for_texture(slot_info.tex)
                    if crew_target is not None:
                        replaces.add(crew_target.display_name)
                elif category == CATEGORY_GENERAL:
                    general_target = target_for_general_filename(path.name, cannon_set)
                    if general_target is not None:
                        replaces.add(general_target.display_name)
                elif category == CATEGORY_SAIL:
                    sail_target = selected_sail or target_for_sail_filename(path.name)
                    if sail_target is not None:
                        replaces.add(sail_target.display_name)

            if cannon_set and errors:
                raise PackError("The selected cannon set could not be imported completely:\n" + "\n".join(errors))
            if not slots:
                if category == CATEGORY_GENERAL:
                    raise PackError(
                        "Texture files were found, but their vanilla game targets could not be identified. "
                        "General texture mods need material/slot IDs in their filenames or an Animus target manifest. "
                        "Design-only Workshop PNGs cannot be patched safely until a vanilla target is selected.\n" +
                        "\n".join(errors)
                    )
                raise PackError("No textures could be imported.\n" + "\n".join(errors))

            meta = {
                "id": pack_id,
                "name": name,
                "category": category,
                "source": source_label,
                "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": imported,
                "slots": [
                    {"mat": f"0x{s.mat:X}", "slot": s.slot, "tex": f"0x{s.tex:X}",
                     "W": s.W, "H": s.H, "family": s.family, "srgb": s.srgb}
                    for s in slots
                ],
                "import_notes": errors,
            }
            for field in ("author", "version", "description", "replaces"):
                value = (metadata or {}).get(field)
                if value:
                    meta[field] = value if field == "replaces" else str(value)
            if replaces:
                meta["replaces"] = sorted(replaces)
            if sail_orientations:
                meta["sail_orientation"] = sail_orientations
            if category == CATEGORY_GENERAL and any(target_for_general_filename(p.name) for p in files):
                meta["cannon_set"] = cannon_set or "gold"
            if selected_sail is not None:
                meta["sail_target_id"] = selected_sail.id
                meta["sail_texture_id"] = f"0x{selected_sail.texture_id:X}"
            if selected_crew is not None:
                meta["crew_target_id"] = selected_crew.id
                meta["crew_texture_id"] = f"0x{selected_crew.texture_id:X}"
            (p_dir / "meta.json").write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8")

            lib = self._load_library()
            lib["packs"].append({"id": pack_id, "name": name, "category": category})
            self._save_library(lib)
            return Pack(pack_id, name, category, p_dir, slots)
        except Exception:
            # A failed conversion must never leave a ghost pack directory that
            # can reappear on refresh or relaunch.
            shutil.rmtree(p_dir, ignore_errors=True)
            raise

    def install(self, source: Path, name: str | None = None,
                category: str = CATEGORY_OUTFIT) -> dict:
        """One-click install: import a pack, enable it, and apply it."""
        pack = self.import_pack(source, name=name, category=category)
        self.set_enabled(pack.id, True)
        applied = self.apply_staged(category)
        lib = self._load_library()
        lib["active"] = pack.id
        self._save_library(lib)
        result = {"pack": pack, **applied}
        result["active_id"] = pack.id
        return result

    def enabled_conflicts(self, pack: Pack) -> list[dict]:
        """Return enabled packs that compete for the same wardrobe/texture slot."""
        return self._pack_conflicts(pack, enabled_only=True)

    def sharing_packs(self, pack: Pack) -> list[dict]:
        """Return every installed pack sharing the slot, enabled or disabled."""
        return self._pack_conflicts(pack, enabled_only=False)

    def _pack_conflicts(self, pack: Pack, enabled_only: bool) -> list[dict]:
        wanted = {(slot.mat, slot.slot) for slot in pack.slots}
        wanted_replacements = self._replacement_keys(pack)
        enabled = set(self._staged(pack.category))
        conflicts = []
        for other in self.list_packs(category=pack.category):
            if other.id == pack.id or (enabled_only and other.id not in enabled):
                continue
            shared = sorted(wanted & {(slot.mat, slot.slot) for slot in other.slots})
            other_replacements = self._replacement_keys(other)
            shared_replacements = sorted(wanted_replacements & other_replacements)
            # Named outfit/sail metadata identifies the replaced vanilla entry
            # more accurately than a shared generic material. Fall back to raw
            # texture overlap when either pack lacks usable replacement data.
            uses_named_replacement = pack.category in {CATEGORY_OUTFIT, CATEGORY_SAIL}
            same_replacement = bool(shared_replacements)
            texture_fallback = bool(shared) and not (wanted_replacements and other_replacements)
            if same_replacement or texture_fallback or (not uses_named_replacement and shared):
                conflicts.append({
                    "id": other.id,
                    "name": other.name,
                    "enabled": other.id in enabled,
                    "slots": [f"0x{mat:X}:{slot}" for mat, slot in shared],
                    "replacements": shared_replacements,
                })
        return conflicts

    def _replacement_keys(self, pack: Pack) -> set[str]:
        """Normalize equivalent labels such as Duncan's outfit – Edward."""
        meta = self._pack_meta(pack)
        values = meta.get("replaces") or []
        if isinstance(values, str):
            values = [values]
        keys = set()
        for value in values:
            label = str(value).casefold().replace("’", "'")
            label = re.sub(r"\s*[-–—]\s*(?:edward|duncan|player|npc|male|female)\s*$", "", label)
            label = re.sub(r"\b([a-z0-9]+)'s\b", r"\1", label)
            label = re.sub(r"[^a-z0-9]+", " ", label).strip()
            if label:
                keys.add(label)
        return keys

    def apply_enabled_changes(self, changes: dict[str, bool]) -> dict:
        """Commit requested checkbox changes only when deployment succeeds."""
        self.revert_all(validate_only=True)
        previous = self.library_path.read_bytes() if self.library_path.exists() else None
        try:
            for pack_id, enabled in changes.items():
                self.set_enabled(pack_id, enabled)
            return self.apply_staged()
        except Exception:
            if previous is None:
                self.library_path.unlink(missing_ok=True)
            else:
                self.library_path.write_bytes(previous)
            raise

    def activate_imported(self, pack_id: str, disable_conflicts: bool = False) -> dict:
        """Enable an imported pack, optionally disabling every enabled overlap."""
        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        conflicts = self.enabled_conflicts(pack)
        if conflicts and not disable_conflicts:
            return {"pack": pack, "conflicts": conflicts, "requires_confirmation": True}
        changes = {conflict['id']: False for conflict in conflicts}
        changes[pack.id] = True
        applied = self.apply_enabled_changes(changes)
        lib = self._load_library()
        lib["active"] = pack.id
        self._save_library(lib)
        return {"pack": pack, "disabled": conflicts, **applied, "active_id": pack.id}

    def discard_imported(self, pack_id: str) -> Pack:
        """Remove a newly imported, never-enabled pack without touching game files."""
        import shutil

        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        if pack_id in set(self._staged(pack.category)):
            raise PackError("Cannot discard a pack after it has been enabled.")
        lib = self._load_library()
        lib["packs"] = [item for item in lib.get("packs", []) if item.get("id") != pack_id]
        lib.setdefault("enabled", {}).pop(pack_id, None)
        if lib.get("active") == pack_id:
            lib["active"] = None
        self._save_library(lib)
        shutil.rmtree(pack.dir, ignore_errors=False)
        return pack

    def _oodle(self) -> Oodle:
        return Oodle(self.game_dir)

    def _slot_for(self, archive: ForgeArchive, mat: int, slot: int, path: Path):
        """Validate a texture against a material slot and return its Slot."""
        from .texture import find_slots, read_slot
        res = archive.read_material(mat)
        slots = find_slots(res)
        if slot >= len(slots):
            raise ValueError(f"no slot {slot} (this material has {len(slots)} textures)")
        return read_slot(res, mat, slot, slots)

    def _texture_to_dds(self, path: Path, slot_info, preserve_game_alpha: bool = False,
                        sail_design: bool = False) -> bytes:
        """Return DDS bytes for the texture (passthrough for DDS, encode PNG)."""
        if path.suffix.lower() == ".dds":
            return path.read_bytes()
        if sail_design:
            from .png import encode_sail_png
            return encode_sail_png(path, slot_info)
        from .png import encode_png_to_dds
        data = encode_png_to_dds(path, slot_info)
        if preserve_game_alpha:
            from .png import encode_cannon_rgb
            baseline_manager = getattr(self, "_baseline_manager", self)
            baseline = baseline_manager._original_texture_dds(slot_info, data)
            return encode_cannon_rgb(path, slot_info, baseline)
        return data

    def _original_texture_dds(self, slot_info, template: bytes) -> bytes:
        """Read pre-install pixels, using owned restore records when deployed.

        Never use already-recoloured live alpha as the baseline for an update.
        No game writes; malformed/missing backups fail before import completes.
        """
        archive = ForgeArchive(self.forge_path, self._oodle())
        plan = plan_texture(archive, slot_info.mat, slot_info.slot, template)
        journal = self._load_journal()
        if journal and journal.forge != str(self.forge_path.resolve()):
            raise PackError("Texture baseline journal belongs to a different game install")
        original = archive.read_material(plan.mat)
        for entry in journal.embedded if journal else []:
            if entry.mat != plan.mat:
                continue
            if archive.read_toc_row(plan.mat) != (entry.new_off, entry.new_len):
                raise PackError("Cannon material changed outside Animus; cannot recover its original alpha safely")
            original = decompress_bms(archive.read_at(entry.orig_off, entry.orig_len), self._oodle())
        chunks = {m["lvl"]: bytearray(m["veri"]) for m in plan.mips}
        filled = set()
        for mip in plan.external:
            data = archive.read_at(mip.offset, mip.forge_len)
            for entry in journal.external if journal else []:
                if entry.rid != mip.rid:
                    continue
                if _sha16(data) not in (entry.sha_new, entry.sha_orig):
                    raise PackError("Cannon mip changed outside Animus; original alpha cannot be recovered safely")
                data = entry.backup.read_bytes()
                if len(data) != entry.length or _sha16(data) != entry.sha_orig:
                    raise PackError("Cannon alpha backup is damaged")
            chunks[mip.lvl] = bytearray(data)
            filled.add(mip.lvl)
        if plan.embedded:
            if len(original) != len(archive.read_material(plan.mat)):
                raise PackError("Original cannon material layout no longer matches")
            for lvl, roff, pitch, rows, rb in plan.embedded.layout:
                if lvl not in chunks:
                    continue
                start = plan.embedded.pixel_start + roff
                for row in range(rows):
                    chunks[lvl][row*rb:(row+1)*rb] = original[start+row*pitch:start+row*pitch+rb]
                filled.add(lvl)
        if filled != set(chunks):
            raise PackError("Cannot read every original cannon mip; alpha preservation aborted")
        head = 148 if template[84:88] == b"DX10" else 128
        return template[:head] + b"".join(chunks[i] for i in sorted(chunks))

    # ------------------------------------------------------------------ #
    # journal
    # ------------------------------------------------------------------ #
    def _load_journal(self) -> Journal | None:
        if not self.journal_path.is_file():
            return None
        try:
            raw = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        ext = [JournalEntry(int(e["rid"], 16), e["offset"], e["length"],
                            e["sha_orig"], e["sha_new"], Path(e["backup"]),
                            pack_id=e.get("pack_id", ""))
               for e in raw.get("external", [])]
        emb = [JournalEmbedded(int(e["mat"], 16), e["toc_pos"], e["orig_off"],
                               e["orig_len"], e["new_off"], e["new_len"],
                               pack_id=e.get("pack_id", ""))
               for e in raw.get("embedded", [])]
        return Journal(packs=raw.get("packs", []),
                       categories=raw.get("categories", []),
                       forge=raw.get("forge", ""),
                       forge_size=raw.get("forge_size", 0),
                       external=ext, embedded=emb,
                       appended=raw.get("appended", []),
                       complete=raw.get("complete", True),
                       overrides=raw.get("overrides", []))

    def _save_journal(self, journal: Journal) -> None:
        raw = {
            "packs": journal.packs,
            "categories": journal.categories,
            "forge": journal.forge,
            "forge_size": journal.forge_size,
            "external": [
                {"rid": f"0x{e.rid:016X}", "offset": e.offset, "length": e.length,
                 "sha_orig": e.sha_orig, "sha_new": e.sha_new,
                 "backup": str(e.backup), "pack_id": e.pack_id}
                for e in journal.external
            ],
            "embedded": [
                {"mat": f"0x{e.mat:X}", "toc_pos": e.toc_pos, "orig_off": e.orig_off,
                 "orig_len": e.orig_len, "new_off": e.new_off, "new_len": e.new_len,
                 "pack_id": e.pack_id}
                for e in journal.embedded
            ],
            "appended": journal.appended,
            "complete": journal.complete,
            "overrides": journal.overrides,
        }
        self.journal_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ #
    # apply / switch / revert
    # ------------------------------------------------------------------ #
    def switch_pack(self, pack_id: str | None) -> dict:
        """Legacy single-pack switch: revert active, then inject one pack."""
        lib = self._load_library()
        active = lib.get("active")
        result = {"reverted": None, "applied": None}
        if active and (pack_id is None or pack_id != active):
            result["reverted"] = self.revert_all()
        if pack_id is None:
            lib["active"] = None
            self._save_library(lib)
            return result
        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        lib["active"] = pack_id
        self._save_library(lib)
        result["applied"] = self._apply_pack(pack)
        return result

    def _plans_for(self, pack: Pack, archive: ForgeArchive) -> tuple[list[PlanItem], list[str]]:
        """Build + validate inject plans for one pack."""
        plans: list[PlanItem] = []
        errors: list[str] = []
        for slot in pack.slots:
            tex = pack.dir / "textures" / f"0x{slot.mat:X}_slot{slot.slot}.dds"
            if not tex.is_file():
                errors.append(f"missing {tex.name}")
                continue
            try:
                plans.append(plan_texture(archive, slot.mat, slot.slot,
                                          tex.read_bytes(), tex.name))
            except (ValueError, ForgeError) as exc:
                errors.append(f"{tex.name}: {exc}")
        return plans, errors

    def _apply_pack(self, pack: Pack) -> dict:
        """Apply a single pack (used by legacy switch_pack)."""
        if self._load_journal() is not None:
            self.revert_all()
        return self._apply_plans([pack], [pack.category], {pack.id: pack})

    def _override_manager(self, name: str) -> PackManager:
        # Never trust a journal-supplied path outside these game archives.
        if not re.fullmatch(r"DataPC_boot(?:_patch_\d+|_dx12)\.forge", name, re.I):
            raise PackError("Invalid sail override archive in deployment journal")
        manager = copy(self)
        manager.forge_path = self.game_dir / name
        manager.journal_path = self.textures_root / f"journal-{name}.json"
        manager.backups_dir = self.backups_dir / name
        manager._is_override = True
        return manager

    def _sail_overrides(self, packs: list[Pack]) -> list[tuple[PackManager, list[Pack]]]:
        """Validate matching sail resources in boot patch/renderer archives.

        Update every existing copy rather than guessing archive precedence.
        No unrelated resources, code mods, or entire archives are replaced.
        """
        sails = [p for p in packs if p.category == CATEGORY_SAIL]
        if self.forge_path.name != OUTFIT_FORGE or not sails:
            return []
        result = []
        for path in sorted(self.game_dir.glob("DataPC_boot*.forge")):
            if not re.fullmatch(r"DataPC_boot(?:_patch_\d+|_dx12)\.forge", path.name, re.I):
                continue
            manager = self._override_manager(path.name)
            archive = ForgeArchive(path, self._oodle())
            selected = []
            for pack in sails:
                slots = [s for s in pack.slots if archive.has(s.mat)]
                if not slots:
                    continue
                subset = replace(pack, slots=slots)
                plans, errors = manager._plans_for(subset, archive)
                if errors or not plans:
                    raise PackError(f"Nothing was changed; {path.name}: " +
                                    "\n".join(errors or ["no sail textures to apply"]))
                selected.append(subset)
            if selected:
                result.append((manager, selected))
        return result

    def _apply_plans(self, packs: list[Pack], categories: list[str],
                     by_id: dict) -> dict:
        overrides = self._sail_overrides(packs)
        for manager, _ in overrides:
            if manager.journal_path.exists():
                raise PackError("Sail archive recovery record already exists; keep its backups: "
                                + str(manager.journal_path))
        result = self._apply_single_archive(packs, categories, by_id,
                                           [m.forge_path.name for m, _ in overrides])
        for manager, selected in overrides:
            manager.backups_dir.mkdir(parents=True, exist_ok=True)
            applied = manager._apply_single_archive(selected, [CATEGORY_SAIL], by_id)
            result["external_mips"] += applied["external_mips"]
            result["materials"] += applied["materials"]
        journal = self._load_journal()
        journal.complete = True
        self._save_journal(journal)
        result["sail_override_archives"] = [m.forge_path.name for m, _ in overrides]
        return result

    def repair_sail_overrides(self) -> dict:
        """Migrate a complete base-only deployment without rewriting other mods.

        This explicit repair is not run during startup or state rendering.
        Existing multi-archive deployments use normal apply/revert instead.
        """
        previous = self._load_journal()
        if previous is None or not previous.complete or previous.overrides:
            raise PackError("Sail repair requires a complete, base-only deployment journal")
        self.revert_all(validate_only=True)
        selected = [self.get_pack(pid) for pid in previous.packs]
        overrides = self._sail_overrides([p for p in selected if p is not None])
        if not overrides:
            return {"sail_override_archives": [], "materials": 0}
        for manager, _ in overrides:
            if manager.journal_path.exists():
                raise PackError("Existing sail archive recovery record must be resolved first: "
                                + str(manager.journal_path))
        original_journal = self.journal_path.read_bytes()
        journal = replace(previous, complete=False,
                          overrides=[m.forge_path.name for m, _ in overrides])
        self._save_journal(journal)
        materials = 0
        try:
            for manager, subset in overrides:
                manager.backups_dir.mkdir(parents=True, exist_ok=True)
                result = manager._apply_single_archive(subset, [CATEGORY_SAIL],
                                                       {p.id: p for p in subset})
                materials += result["materials"]
            journal.complete = True
            self._save_journal(journal)
        except Exception:
            # Never revert the base deployment here. Only undo this repair.
            for manager, _ in overrides:
                manager.revert_all(validate_only=True)
            for manager, _ in reversed(overrides):
                manager.revert_all()
            self.journal_path.write_bytes(original_journal)
            raise
        return {"sail_override_archives": journal.overrides, "materials": materials}

    def _apply_single_archive(self, packs: list[Pack], categories: list[str],
                              by_id: dict, overrides: list[str] | None = None) -> dict:
        """Inject a set of packs (MO2-style merge), journaling everything.

        `packs` is in load order (highest priority LAST). When two enabled packs
        touch the same material+slot, the later pack wins.
        """
        archive = ForgeArchive(self.forge_path, self._oodle())
        all_plans: list[tuple[Pack, PlanItem]] = []
        errors: list[str] = []
        for pack in packs:
            plans, perr = self._plans_for(pack, archive)
            errors.extend(perr)
            for p in plans:
                all_plans.append((pack, p))
        if errors:
            raise PackError("Some textures could not be applied:\n" + "\n".join(errors))
        if not all_plans:
            raise PackError("No textures to apply.")

        # Resolve conflicts: per (mat, slot), the last (highest priority) wins.
        by_slot: dict[tuple[int, int], tuple[Pack, PlanItem]] = {}
        conflicts: list[dict] = []
        for pack, plan in all_plans:
            key = (plan.mat, plan.slot)
            if key in by_slot:
                conflicts.append({
                    "mat": plan.mat, "slot": plan.slot,
                    "winner": pack.name, "loser": by_slot[key][0].name,
                })
            by_slot[key] = (pack, plan)
        resolved = list(by_slot.values())

        journal = Journal(packs=[p.id for p in packs],
                          categories=categories,
                          forge=str(self.forge_path.resolve()),
                          forge_size=self.forge_path.stat().st_size,
                          overrides=overrides or [],
                          complete=False)

        # --- phase 1: external mips (in-place) ---
        for _pack, plan in resolved:
            for m in plan.external:
                original = archive.read_at(m.offset, m.forge_len)
                backup = self.backups_dir / f"RAW_{m.rid:016X}.bin"
                backup.write_bytes(original)
                journal.external.append(JournalEntry(
                    m.rid, m.offset, m.forge_len, _sha16(original),
                    _sha16(m.data), backup, pack_id=_pack.id))
                self._save_journal(journal)
                archive.write_at(m.offset, m.data)
            self._save_journal(journal)

        # --- phase 2: embedded tails (re-pack + append + repoint) ---
        by_mat: dict[int, list[PlanItem]] = {}
        for _pack, plan in resolved:
            if plan.embedded is not None:
                by_mat.setdefault(plan.mat, []).append(plan)
        for mat, group in sorted(by_mat.items()):
            raw = archive.read_raw(mat)
            original_res = archive.read_material(mat)
            res = bytearray(original_res)
            for plan in group:
                g = plan.embedded
                mipmap = {m["lvl"]: m for m in plan.mips}
                for lvl, roff, pitch, rows, rb in g.layout:
                    m = mipmap.get(lvl)
                    if m is None:
                        continue
                    src = m["veri"]
                    if len(src) < rb * rows:
                        continue
                    base = g.pixel_start + roff
                    for r in range(rows):
                        res[base + r * pitch: base + r * pitch + rb] = src[r * rb:(r + 1) * rb]
            if len(res) != len(original_res):
                raise PackError(f"embedded write changed material size for 0x{mat:X} -- aborted")
            res = bytes(res)

            new_entry = compress_material(raw, res, self._oodle())
            toc_pos = archive.toc_entry_offset(mat)
            orig_off, orig_len = archive.read_toc_row(mat)
            new_off = archive.append_block(new_entry)
            new_len = len(new_entry)
            journal.embedded.append(JournalEmbedded(
                mat, toc_pos, orig_off, orig_len, new_off, new_len, pack_id=_pack.id))
            journal.appended.append([new_off, new_len])
            self._save_journal(journal)
            archive.repoint_toc(mat, new_off, new_len)

        journal.complete = not journal.overrides
        self._save_journal(journal)

        return {
            "packs": [p.id for p in packs],
            "external_mips": sum(len(plan.external) for _, plan in resolved),
            "materials": len(by_mat),
            "conflicts": conflicts,
            "errors": errors,
        }

    def apply_staged(self, category: str | None = None) -> dict:
        """Rebuild the complete enabled texture set in load order.

        The journal describes the complete patched FORGE state. Reapplying only
        the category that changed would first restore every other category and
        then silently omit it. Therefore ``category`` is retained for API
        compatibility, but every apply rebuilds outfits, weapons, crew, sails,
        and general textures together. The staged enabled lists remain the
        source of truth.
        """
        categories = list(PACK_CATEGORIES)
        packs = []
        for cat in PACK_CATEGORIES:
            packs.extend(self.get_pack(pid) for pid in self._staged(cat))
        packs = [p for p in packs if p is not None]
        # Check every requested payload before removing a working deployment.
        # Previously a missing/invalid new DDS could restore all outfits first,
        # then fail and leave the enabled checkmarks behind without a journal.
        if packs:
            archive = ForgeArchive(self.forge_path, self._oodle())
            errors = []
            for pack in packs:
                plans, perr = self._plans_for(pack, archive)
                errors.extend(f"{pack.name}: {error}" for error in perr)
                if not plans and not perr:
                    errors.append(f"{pack.name}: no textures to apply")
            if errors:
                raise PackError("Nothing was changed; textures could not be applied:\n" + "\n".join(errors))
            self._sail_overrides(packs)  # Validate patch archives before any revert.
        previous = self._load_journal()
        previous_packs = [self.get_pack(pid) for pid in previous.packs] if previous else []
        previous_packs = [p for p in previous_packs if p is not None]
        # The journal represents the complete injected set. Always restore it
        # before rebuilding, including when the final pack was just disabled.
        self.revert_all()
        if not packs:
            return {"packs": [], "external_mips": 0, "materials": 0,
                    "conflicts": [], "errors": [], "applied": 0}
        by_id = {p.id: p for p in packs}
        try:
            return self._apply_plans(packs, categories, by_id)
        except Exception as failure:
            # Roll back partial writes, then restore the last complete set.
            # Keep recovery metadata if ownership checks prevent safe rollback.
            try:
                self.revert_all()
                if previous and previous.complete and previous_packs:
                    self._apply_plans(previous_packs, previous.categories,
                                      {p.id: p for p in previous_packs})
            except Exception as recovery:
                raise PackError(f"Texture deployment failed: {failure}. Recovery also failed: {recovery}. "
                                "Recovery records were retained; do not delete backups.") from failure
            raise PackError(f"Texture deployment failed: {failure}. Previous deployment was restored.") from failure

    def deployed_pack_ids(self) -> set[str]:
        """A requested checkbox alone is not proof of successful deployment."""
        journal = self._load_journal()
        if journal is None or not journal.complete or not self.forge_path.is_file():
            return set()
        if journal.forge != str(self.forge_path.resolve()):
            return set()
        for name in journal.overrides:
            manager = self._override_manager(name)
            child = manager._load_journal()
            if (child is None or not child.complete or not manager.forge_path.is_file()
                    or child.forge != str(manager.forge_path.resolve())):
                return set()
        return set(journal.packs)

    def revert_all(self, validate_only: bool = False) -> dict:
        """Revert the currently-injected set back to vanilla.

        A Ubisoft title update can replace/repack ``DataPC_boot.forge`` while
        Animus has an active texture journal. External mip locations may remain
        valid, while material TOC rows point at brand-new update data. A TOC
        row which points at neither our patched entry nor its former entry is
        therefore detached: our appended material is no longer active and must
        not be relinked or used to truncate the newly updated archive.
        """
        journal = self._load_journal()
        if journal is None:
            return {"reverted": 0, "issues": [], "packs": []}
        archive = ForgeArchive(self.forge_path, self._oodle())
        issues: list[str] = []
        active_external: list[JournalEntry] = []
        active_embedded: list[JournalEmbedded] = []
        detached_embedded: list[JournalEmbedded] = []

        # Validate everything before writing a single byte.
        if str(self.forge_path.resolve()) != journal.forge:
            issues.append("journal belongs to a different game install")
        current_size = self.forge_path.stat().st_size
        for e in journal.external:
            backup = Path(e.backup)
            if not backup.is_file():
                issues.append(f"{e.rid:016X}: backup missing")
                continue
            data = backup.read_bytes()
            if len(data) != e.length or _sha16(data) != e.sha_orig:
                issues.append(f"{e.rid:016X}: backup damaged")
                continue
            if e.offset + e.length > current_size:
                issues.append(f"{e.rid:016X}: target past end of archive")
                continue
            now = archive.read_at(e.offset, e.length)
            now_sha = _sha16(now)
            if now_sha == e.sha_new:
                active_external.append(e)
            elif now_sha == e.sha_orig:
                # Steam/Ubisoft already restored this block during an update.
                continue
            else:
                issues.append(f"{e.rid:016X}: bytes changed by another tool")
        for k in journal.embedded:
            now_off, now_len = archive.read_toc_row(k.mat)
            if (now_off, now_len) == (k.new_off, k.new_len):
                active_embedded.append(k)
            elif (now_off, now_len) == (k.orig_off, k.orig_len):
                # Already returned to the exact pre-install material.
                continue
            else:
                # A game update repacked/repointed this material. Our appended
                # resource is detached, so touching the new TOC row would roll
                # the game backward or corrupt the updated archive.
                detached_embedded.append(k)

        if issues:
            raise PackError("Cannot revert safely:\n" + "\n".join(issues))

        children = [self._override_manager(name) for name in journal.overrides]
        for manager in children:
            manager.revert_all(validate_only=True)

        if validate_only:
            return {"reverted": 0, "issues": [], "packs": journal.packs}

        # Write reversals.
        restored = sum(manager.revert_all()["reverted"] for manager in children)
        for k in active_embedded:
            archive.repoint_toc(k.mat, k.orig_off, k.orig_len)
            restored += 1
        for e in active_external:
            archive.write_at(e.offset, Path(e.backup).read_bytes())
            restored += 1

        # Reclaim appended tail if it fully covers the end.
        appended = journal.appended
        if appended and not detached_embedded:
            start = min(o for o, _ in appended)
            end = max(o + l for o, l in appended)
            if end == current_size and sum(l for _, l in appended) == current_size - start:
                try:
                    archive.truncate(start)
                except OSError:
                    pass

        self.journal_path.unlink(missing_ok=True)
        if not getattr(self, "_is_override", False):
            lib = self._load_library()
            lib["active"] = None
            self._save_library(lib)
        return {
            "reverted": restored,
            "issues": issues,
            "packs": journal.packs,
            "detached_after_game_update": len(detached_embedded),
        }

    def status(self) -> dict:
        """Read-only status: active pack + journal presence."""
        return {
            "active": self.active_pack_id(),
            "journal": self._load_journal() is not None,
            "forge_exists": self.forge_path.is_file(),
            "staged_outfit": self._staged(CATEGORY_OUTFIT),
            "staged_weapon": self._staged(CATEGORY_WEAPON),
            "staged_crew": self._staged(CATEGORY_CREW),
            "staged_sail": self._staged(CATEGORY_SAIL),
            "staged_general": self._staged(CATEGORY_GENERAL),
        }

    def revert_pack(self, pack_id: str) -> dict:
        """Revert one pack's injected textures back to vanilla.

        External texture mips are restored exactly. Embedded (material tail)
        edits are restored only if no OTHER enabled pack touches the same
        material; otherwise that material is left as-is (its bytes may merge
        multiple packs) and a note is returned.
        """
        journal = self._load_journal()
        if journal is None:
            return {"reverted": 0, "issues": ["no journal"], "pack": pack_id}
        if journal.overrides:
            # Rebuild the remaining set across all archives; a base-only revert
            # would leave the overridden sail visible in the game.
            self.revert_all(validate_only=True)
            self.set_enabled(pack_id, False)
            self.apply_staged()
            return {"reverted": 1, "issues": [], "pack": pack_id}
        archive = ForgeArchive(self.forge_path, self._oodle())
        issues: list[str] = []
        restored: list = []

        mine_ext = [e for e in journal.external if e.pack_id == pack_id]
        mine_emb = [e for e in journal.embedded if e.pack_id == pack_id]

        # external: verify then restore the pack's own bytes
        for e in mine_ext:
            backup = Path(e.backup)
            if not backup.is_file():
                issues.append(f"{e.rid:016X}: backup missing")
                continue
            data = backup.read_bytes()
            if len(data) != e.length or _sha16(data) != e.sha_orig:
                issues.append(f"{e.rid:016X}: backup damaged")
                continue
            now = archive.read_at(e.offset, e.length)
            if _sha16(now) != e.sha_new:
                issues.append(f"{e.rid:016X}: bytes changed by another tool (skip)")
                continue
            archive.write_at(e.offset, data)
            restored.append(e.rid)

        # Embedded: only if this pack is the sole owner of that material.
        shared_mats = {k.mat for k in journal.embedded
                       if k.pack_id != pack_id}
        for k in mine_emb:
            if k.mat in shared_mats:
                issues.append(f"material 0x{k.mat:X} is shared with another enabled pack; "
                              f"left as-is (revert after disabling the other pack)")
                continue
            now_off, now_len = archive.read_toc_row(k.mat)
            if (now_off, now_len) != (k.new_off, k.new_len):
                issues.append(f"0x{k.mat:X}: TOC no longer matches what we wrote (skip)")
                continue
            archive.repoint_toc(k.mat, k.orig_off, k.orig_len)
            restored.append(f"mat:{k.mat:X}")

        # Drop this pack's entries from the journal and re-save.
        journal.external = [e for e in journal.external if e.pack_id != pack_id]
        journal.embedded = [e for e in journal.embedded if e.pack_id != pack_id]
        journal.packs = [p for p in journal.packs if p != pack_id]

        # Reclaim appended tail if no embedded entries remain and they cover the end.
        if not journal.embedded and journal.appended:
            current_size = self.forge_path.stat().st_size
            start = min(o for o, _ in journal.appended)
            end = max(o + l for o, l in journal.appended)
            if end == current_size and sum(l for _, l in journal.appended) == current_size - start:
                try:
                    archive.truncate(start)
                except OSError:
                    pass

        if not journal.external and not journal.embedded:
            self.journal_path.unlink(missing_ok=True)
            lib = self._load_library()
            lib["active"] = None
            self._save_library(lib)
        else:
            self._save_journal(journal)
        return {"reverted": len(restored), "issues": issues, "pack": pack_id}

    def remove_pack(self, pack_id: str) -> dict:
        """Safely remove a managed outfit/weapon/crew pack from the library.

        The complete enabled texture set is rebuilt first so none of this
        pack's injected bytes survive after its library files are removed.
        """
        import uuid

        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        previous = self.library_path.read_bytes()
        applied = self.apply_enabled_changes({pack_id: False})
        # Recoverable removal, consistent with ordinary mod archives. Never
        # recursively delete a live pack after dropping its ownership record.
        recovery = self.mods_root / 'removed-packages' / uuid.uuid4().hex / pack.id
        moved = False
        try:
            recovery.parent.mkdir(parents=True, exist_ok=True)
            pack.dir.rename(recovery)
            moved = True
            lib = self._load_library()
            lib['packs'] = [item for item in lib.get('packs', []) if item.get('id') != pack_id]
            lib.setdefault('enabled', {}).pop(pack_id, None)
            if lib.get('active') == pack_id:
                lib['active'] = None
            self._save_library(lib)
        except Exception as failure:
            try:
                if moved:
                    recovery.rename(pack.dir)
                self.library_path.write_bytes(previous)
                self.apply_staged()
            except Exception as repair:
                raise PackError(f'Uninstall failed: {failure}. Recovery failed: {repair}. Keep all backups.') from failure
            raise
        return {'removed': pack_id, 'name': pack.name, 'applied': applied, 'recovery': str(recovery)}

    def rename_pack(self, pack_id: str, new_name: str) -> None:
        """Rename a library pack without changing its stable id or deployment."""
        new_name = str(new_name).strip()
        if not new_name:
            raise PackError("A pack name cannot be empty.")
        if len(new_name) > 120:
            raise PackError("A pack name cannot exceed 120 characters.")
        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        if any(other.id != pack_id and other.name.casefold() == new_name.casefold()
               for other in self.list_packs()):
            raise PackError(f"A pack named '{new_name}' already exists.")

        lib = self._load_library()
        for item in lib.get("packs", []):
            if item.get("id") == pack_id:
                item["name"] = new_name
                break
        meta_path = pack.dir / "meta.json"
        meta = self._pack_meta(pack)
        meta["name"] = new_name
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        self._save_library(lib)

    def _pack_meta(self, pack: Pack) -> dict:
        meta_path = pack.dir / "meta.json"
        if not meta_path.is_file():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

def _make_id(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "-", name).strip("-").lower() or "pack"
    return f"{base}-{int(time.time() * 1000)}"


def _name_of(lib: dict, pack_id: str) -> str:
    for p in lib.get("packs", []):
        if p["id"] == pack_id:
            return p.get("name", pack_id)
    return pack_id


def _version_key(v: str):
    """Split a version string into comparable numeric groups."""
    return [int(x) for x in re.findall(r"\d+", str(v))]


def _version_gt(a: str, b: str) -> bool:
    """Return True if version a is strictly newer than b (MO2-style compare)."""
    ka, kb = _version_key(a), _version_key(b)
    for x, y in zip(ka, kb):
        if x != y:
            return x > y
    return len(ka) > len(kb)
