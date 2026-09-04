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
from dataclasses import dataclass, field
from pathlib import Path

from .forge import ForgeArchive, ForgeError, Oodle, compress_material
from .texture import PlanItem, parse_filename, plan_texture
from .crew_catalog import target_for_filename, target_for_texture
from .general_texture_catalog import target_for_general_filename
from .sail_catalog import get_sail_target, target_for_sail_filename
from .nexus import NEXUS_GAME_ID

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
                    sail_target_id: str | None = None) -> Pack:
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
                                            sail_target_id=sail_target_id)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            if suffix in (".dds", ".png"):
                self._validate_pack_category([source_dir], category, {}, source_dir.parent)
                return self._import_files([source_dir], name or source_dir.stem,
                                          category, str(source_dir), {}, sail_target_id)
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
        self._validate_pack_category(files, category, metadata, source_dir)
        name = (name or metadata.get("name") or source_dir.name).strip() or "Unnamed Pack"
        return self._import_files(files, name, category, str(source_dir), metadata,
                                  sail_target_id)

    @staticmethod
    def _validate_pack_category(files: list[Path], requested: str,
                                metadata: dict, source_dir: Path) -> None:
        """Reject only confidently identified packs from an incorrect tab."""
        declared = str(metadata.get("pack_category") or "").casefold().strip()
        aliases = {
            "outfits": CATEGORY_OUTFIT, "outfit": CATEGORY_OUTFIT,
            "weapons": CATEGORY_WEAPON, "weapon": CATEGORY_WEAPON,
            "crew": CATEGORY_CREW,
            "sails": CATEGORY_SAIL, "sail": CATEGORY_SAIL,
            "general": CATEGORY_GENERAL, "ship": CATEGORY_GENERAL,
        }
        detected = aliases.get(declared)
        names = " ".join([source_dir.name, *(path.name for path in files)]).casefold()
        if detected is None and any(target_for_filename(path.name) for path in files):
            detected = CATEGORY_CREW
        if detected is None:
            markers = {
                CATEGORY_SAIL: ("sail",),
                CATEGORY_GENERAL: ("cannon", "mortar", "swivel", "culverin", "longgun",
                                   "figurehead", "ship hull", "jackdaw hull", "ship wheel", "cabin"),
                CATEGORY_OUTFIT: ("outfit", "robe", "redingote"),
                CATEGORY_WEAPON: ("pistol", "sword", "blade", "weapon skin"),
            }
            matches = [kind for kind, words in markers.items()
                       if any(word in names for word in words)]
            if len(matches) == 1:
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

    @staticmethod
    def _pack_metadata(source_dir: Path) -> dict:
        """Extract optional author/version data shipped inside an ordinary pack.

        Nexus archives are inconsistent, so this deliberately accepts common
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
                if heading.startswith("outfit"):
                    metadata.setdefault("pack_category", CATEGORY_OUTFIT)
                elif heading.startswith("sail"):
                    metadata.setdefault("pack_category", CATEGORY_SAIL)
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
        nexus_title = re.sub(
            r"\s+\d+\s+\S+\s+\d{4}-\d{2}-\d{2}T.*$", "", fallback).strip()
        if nexus_title and nexus_title != fallback:
            return nexus_title
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
                      sail_target_id: str | None = None) -> Pack:
        """Validate + copy a set of texture files into a new library pack."""
        import shutil
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

            slots: list[PackSlot] = []
            imported = []
            errors: list[str] = []
            replaces: set[str] = set()
            for path in files:
                mat, slot, kind = parse_filename(path.name)
                if selected_sail is not None:
                    mat, slot, kind = (selected_sail.material_id,
                                       selected_sail.slot, "selected-sail-target")
                if mat is None and category == CATEGORY_CREW:
                    crew_target = target_for_filename(path.name)
                    if crew_target is not None:
                        mat, slot, kind = crew_target.material_id, 0, "crew-catalog"
                if mat is None and category == CATEGORY_GENERAL:
                    general_target = target_for_general_filename(path.name)
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
                data = self._texture_to_dds(path, slot_info)
                dest.write_bytes(data)
                imported.append(str(dest.relative_to(p_dir)))
                slots.append(PackSlot(mat, slot, slot_info.tex, slot_info.W,
                                      slot_info.H, slot_info.family, slot_info.srgb))
                if category == CATEGORY_CREW:
                    crew_target = target_for_texture(slot_info.tex)
                    if crew_target is not None:
                        replaces.add(crew_target.display_name)
                elif category == CATEGORY_GENERAL:
                    general_target = target_for_general_filename(path.name)
                    if general_target is not None:
                        replaces.add(general_target.display_name)
                elif category == CATEGORY_SAIL:
                    sail_target = selected_sail or target_for_sail_filename(path.name)
                    if sail_target is not None:
                        replaces.add(sail_target.display_name)

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
            if selected_sail is not None:
                meta["sail_target_id"] = selected_sail.id
                meta["sail_texture_id"] = f"0x{selected_sail.texture_id:X}"
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

    def activate_imported(self, pack_id: str, disable_conflicts: bool = False) -> dict:
        """Enable an imported pack, optionally disabling every enabled overlap."""
        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        conflicts = self.enabled_conflicts(pack)
        if conflicts and not disable_conflicts:
            return {"pack": pack, "conflicts": conflicts, "requires_confirmation": True}
        for conflict in conflicts:
            self.set_enabled(conflict["id"], False)
        self.set_enabled(pack.id, True)
        applied = self.apply_staged(pack.category)
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

    def _texture_to_dds(self, path: Path, slot_info) -> bytes:
        """Return DDS bytes for the texture (passthrough for DDS, encode PNG)."""
        if path.suffix.lower() == ".dds":
            return path.read_bytes()
        from .png import encode_png_to_dds
        return encode_png_to_dds(path, slot_info)

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
                       appended=raw.get("appended", []))

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

    def _apply_plans(self, packs: list[Pack], categories: list[str],
                     by_id: dict) -> dict:
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
                          forge_size=self.forge_path.stat().st_size)

        # --- phase 1: external mips (in-place) ---
        for _pack, plan in resolved:
            for m in plan.external:
                original = archive.read_at(m.offset, m.forge_len)
                backup = self.backups_dir / f"RAW_{m.rid:016X}.bin"
                backup.write_bytes(original)
                journal.external.append(JournalEntry(
                    m.rid, m.offset, m.forge_len, _sha16(original),
                    _sha16(m.data), backup, pack_id=_pack.id))
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
            archive.repoint_toc(mat, new_off, new_len)
            journal.embedded.append(JournalEmbedded(
                mat, toc_pos, orig_off, orig_len, new_off, new_len, pack_id=_pack.id))
            journal.appended.append([new_off, new_len])
            self._save_journal(journal)

        return {
            "packs": [p.id for p in packs],
            "external_mips": sum(len(plan.external) for _, plan in resolved),
            "materials": len(by_mat),
            "conflicts": conflicts,
            "errors": errors,
        }

    def apply_staged(self, category: str | None = None) -> dict:
        """Apply all enabled packs (in load order) for a category, or all.

        Returns the apply result. Does NOT auto-activate single-packs; the
        staged "enabled" list is the source of truth.
        """
        lib = self._load_library()
        if category:
            categories = [category]
            packs = [self.get_pack(pid) for pid in self._staged(category)]
        else:
            categories = []
            packs = []
            for cat in PACK_CATEGORIES:
                packs.extend(self.get_pack(pid) for pid in self._staged(cat))
            categories = list(PACK_CATEGORIES)
        packs = [p for p in packs if p is not None]
        # The journal represents the complete injected set. Always restore it
        # before rebuilding, including when the final pack was just disabled.
        self.revert_all()
        if not packs:
            return {"packs": [], "external_mips": 0, "materials": 0,
                    "conflicts": [], "errors": [], "applied": 0}
        by_id = {p.id: p for p in packs}
        return self._apply_plans(packs, categories, by_id)

    def revert_all(self) -> dict:
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

        # Write reversals.
        restored = 0
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
        import shutil

        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")

        self.set_enabled(pack_id, False)
        applied = self.apply_staged()

        lib = self._load_library()
        lib["packs"] = [item for item in lib.get("packs", [])
                        if item.get("id") != pack_id]
        lib.setdefault("enabled", {}).pop(pack_id, None)
        if lib.get("active") == pack_id:
            lib["active"] = None
        self._save_library(lib)
        shutil.rmtree(pack.dir, ignore_errors=False)
        return {"removed": pack_id, "name": pack.name, "applied": applied}

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

    # ------------------------------------------------------------------ #
    # nexus update tracking
    # ------------------------------------------------------------------ #
    def set_nexus(self, pack_id: str, mod_id: int, game_id: int | None = None,
                  version: str | None = None) -> None:
        """Attach Nexus metadata and cache its author for the pack table."""
        pack = self.get_pack(pack_id)
        if pack is None:
            raise PackError(f"Unknown pack id: {pack_id}")
        meta_path = pack.dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        resolved_game_id = game_id or NEXUS_GAME_ID
        meta["nexus"] = {
            "game_id": resolved_game_id,
            "mod_id": int(mod_id),
        }
        if version is not None:
            meta["version"] = str(version)
        # A linked Nexus page is the best source for archives that do not ship
        # a manifest/readme author. Metadata lookup is helpful but must not
        # prevent the link being saved while Nexus is unavailable.
        try:
            from .nexus import NexusClient
            nexus_meta = NexusClient().mod(
                int(mod_id), int(resolved_game_id))
            author = nexus_meta.get("uploaded_by") or nexus_meta.get("author")
            if author:
                meta["author"] = str(author)
            if not version and nexus_meta.get("version"):
                meta["version"] = str(nexus_meta["version"])
            if nexus_meta.get("summary") and not meta.get("description"):
                meta["description"] = str(nexus_meta["summary"])
        except Exception:
            pass
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def _pack_meta(self, pack: Pack) -> dict:
        meta_path = pack.dir / "meta.json"
        if not meta_path.is_file():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def check_updates(self, client=None) -> list[dict]:
        """Check all packs (any category) against Nexus for newer versions.

        Returns a list of result dicts: {id, name, category, game_id, mod_id,
        current, latest, has_update, error}.
        """
        from .nexus import NexusClient
        client = client or NexusClient()
        results: list[dict] = []
        for pack in self.list_packs():
            meta = self._pack_meta(pack)
            nexus = meta.get("nexus")
            if not nexus:
                results.append({"id": pack.id, "name": pack.name,
                                "category": pack.category,
                                "game_id": None, "mod_id": None,
                                "has_update": False,
                                "error": "no nexus id"})
                continue
            game_id = nexus.get("game_id", NEXUS_GAME_ID)
            mod_id = nexus.get("mod_id")
            current = meta.get("version")
            latest = None
            err = None
            try:
                latest = client.latest_version(int(mod_id), int(game_id))
            except Exception as exc:  # network / api
                err = str(exc)
            has_update = False
            if latest and current and latest != current:
                try:
                    has_update = _version_gt(latest, current)
                except ValueError:
                    has_update = latest != current
            results.append({
                "id": pack.id,
                "name": pack.name,
                "category": pack.category,
                "game_id": game_id,
                "mod_id": mod_id,
                "current": current,
                "latest": latest,
                "has_update": has_update,
                "error": err,
            })
        return results


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
