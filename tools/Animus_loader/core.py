"""Animus Mod & Outfit Manager - core installer engine.

Applies `.jmod` packages to the Assassin's Creed IV: Black Flag Resynced game
with full backup/revert, conflict detection, and load-order resolution.

This mirrors the spirit of Lenny's Mod Loader for RDR2: you drop packages into
`mods/packages/`, enable the ones you want, and the loader applies them safely.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = "jackdaw-mod-v1"
GAME = "AC4BF-Resynced"


def _version_key(v: str):
    """Split a version string into comparable numeric groups."""
    return [int(x) for x in re.findall(r"\d+", str(v))]


def _version_gt(a: str, b: str) -> bool:
    """Return True if version a is strictly newer than b."""
    ka, kb = _version_key(a), _version_key(b)
    for x, y in zip(ka, kb):
        if x != y:
            return x > y
    return len(ka) > len(kb)

FORGE_ARCHIVE_MAGIC = b"scimitar"
# Historical helper name retained for BMS-container discovery below.
FORGE_MAGIC = bytes.fromhex("33 aa fb 57 99 fa 04 10")

# Default install locations (overridable).
DEFAULT_GAME_DIR = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Assassin's Creed Black Flag Resynced"
)


class LoaderError(Exception):
    """Raised when a package cannot be applied safely."""


@dataclass
class Target:
    forge: str
    resource_id: int
    occurrence: int
    bms_block: int
    mode: str
    file: str
    replacement: bytes
    sha256: str | None = None
    expected_original: bytes | None = None
    expected_original_size: int | None = None
    expected_original_sha256: str | None = None
    needle: bytes | None = None
    patch_offset: int | None = None
    patch: bytes | None = None
    original: bytes | None = None
    dest: str | None = None


@dataclass
class Package:
    """A validated, resolved .jmod package ready to apply."""

    name: str
    version: str
    author: str
    manifest: dict
    targets: list[Target] = field(default_factory=list)
    category: str = "forge-resource"


@dataclass
class InstallRecord:
    """Installed state for a single enabled package."""

    name: str
    version: str
    author: str
    enabled: bool = True
    priority: int = 0
    backups: list[dict] = field(default_factory=list)


class ForgeEditor:
    """Thin, safe reader/writer for DataPC*.forge archives.

    V1 supports replacing the raw stored bytes of a resource occurrence in-place
    when the replacement is the same size. Larger/smaller replacements require
    append-and-repoint, which is a separate injector stage and out of scope here.
    """

    def __init__(self, path: Path):
        self.path = path

    def find_resource_offsets(self, resource_id: int) -> list[int]:
        """Locate the stored payload offset for a resource through the TOC."""
        return [offset for offset, _size in self.find_resource_entries(resource_id)]

    def find_resource_entries(self, resource_id: int) -> list[tuple[int, int]]:
        """Return ``(payload offset, stored size)`` entries from the FORGE TOC.

        A raw search for the resource ID is unsafe because it finds the ID
        inside the TOC row rather than the resource payload itself.
        """
        with self.path.open("rb") as handle:
            header = handle.read(64)
            if len(header) < 64 or header[:8] != FORGE_ARCHIVE_MAGIC:
                raise LoaderError(f"{self.path.name}: invalid scimitar FORGE header")
            header_table_offset = struct.unpack_from("<Q", header, 13)[0]
            handle.seek(header_table_offset)
            table_header = handle.read(12)
            if len(table_header) != 12:
                raise LoaderError(f"{self.path.name}: truncated FORGE table header")
            count, toc_offset = struct.unpack("<IQ", table_header)
            handle.seek(toc_offset)
            matches: list[tuple[int, int]] = []
            for _ in range(count):
                row = handle.read(24)
                if len(row) != 24:
                    raise LoaderError(f"{self.path.name}: truncated FORGE TOC")
                offset, found_id, stored_size, _class_hash = struct.unpack(
                    "<QQII", row
                )
                if found_id == resource_id:
                    matches.append((offset, stored_size))
            return matches

    def validate_resource_offsets(self, resource_id: int) -> list[int]:
        """Return valid resource offsets for a resource id.

        The returned offsets are payload offsets, never TOC-row ID locations.
        """
        return self.find_resource_offsets(resource_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_proxy_dll(data: bytes) -> dict:
    """Return a conservative fingerprint for a Windows proxy DLL."""
    result = {
        "valid_pe": False,
        "architecture": "unknown",
        "machine": None,
        "kind": "unknown",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if len(data) < 0x40 or data[:2] != b"MZ":
        return result
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset < 0x40 or pe_offset + 6 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        return result
    machine = int.from_bytes(data[pe_offset + 4:pe_offset + 6], "little")
    result["valid_pe"] = True
    result["machine"] = f"0x{machine:04X}"
    result["architecture"] = {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}.get(machine, "unknown")
    if any(marker in data for marker in (
        b"Ultimate-ASI-Loader",
        b"Ultimate ASI Loader",
        b"IsUltimateASILoader",
        b"github.com/ThirteenAG/Ultimate-ASI-Loader",
    )):
        result["kind"] = "ultimate-asi-loader"
    else:
        result["kind"] = "proxy-dll"
    return result


def load_toc(path: Path, toc_offset: int, toc_count: int) -> list[tuple[int, int, int, int]]:
    """Read forge TOC: (offset, resource_id, stored_size, class_hash)."""
    rows = []
    with path.open("rb") as handle:
        handle.seek(toc_offset)
        for _ in range(toc_count):
            row = struct_unpack(handle)
            if row is None:
                break
            rows.append(row)
    return rows


def struct_unpack(handle):
    import struct

    raw = handle.read(24)
    if len(raw) != 24:
        return None
    return struct.unpack("<QQII", raw)


class Loader:
    """Orchestrates package enable/disable/apply/restore."""

    def __init__(self, game_dir: Path = DEFAULT_GAME_DIR, mods_root: Path | None = None):
        self.game_dir = Path(game_dir)
        self.root = Path(__file__).resolve().parents[2]  # jackdaw-mod-loader/
        self.mods_root = mods_root or (self.root / "mods")
        self.packages_dir = self.mods_root / "packages"
        self.backups_dir = self.mods_root / "backups"
        self.installed_dir = self.mods_root / "installed"
        self.state_path = self.installed_dir / "installed-mods.json"
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.installed_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # package discovery
    # ------------------------------------------------------------------ #
    def discover_packages(self) -> list[Path]:
        return sorted(
            self.packages_dir.glob("*.jmod"),
            key=lambda p: p.name.lower(),
        )

    def read_package(self, package_path: Path) -> Package:
        if not package_path.is_file():
            raise LoaderError(f"Package not found: {package_path}")
        try:
            archive = zipfile.ZipFile(package_path)
        except zipfile.BadZipFile as exc:
            raise LoaderError(f"Not a valid .jmod zip: {package_path}") from exc
        try:
            if "manifest.json" not in archive.namelist():
                raise LoaderError("Package is missing manifest.json")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            pkg = self._manifest_to_package(manifest, archive)
        finally:
            archive.close()
        return pkg

    def import_package(self, source: Path) -> tuple[Path, Package, bool]:
        """Import a native .jmod or a conventional loose-file archive.

        Most Nexus authors understandably ship the files a player should copy
        beside the game executable rather than an Animus-specific manifest.
        Convert that well-defined archive shape into an internal .jmod so the
        normal backup, enable/disable, and uninstall machinery still owns every
        installed file.  Ambiguous and executable installer archives are
        rejected instead of being copied into the game by guesswork.

        Returns ``(managed_path, package, converted)``.
        """
        source = Path(source)
        if not source.is_file():
            raise LoaderError(f"Package not found: {source}")

        source_name = source.name.lower()
        archive_suffix = ".tar.gz" if source_name.endswith(".tar.gz") else source.suffix.lower()
        external_archives = {".7z", ".rar", ".tar", ".tar.gz", ".tgz"}

        if archive_suffix in external_archives:
            # Reuse the hardened extractor used by outfit/weapon/crew packs,
            # then normalize the extracted tree to ZIP so the same manifest,
            # path-safety, file-type, and wrapper-folder rules apply to every
            # conventional mod archive format.
            from .packs import PackError, PackManager

            with tempfile.TemporaryDirectory(prefix="animus_mod_archive_") as raw:
                temporary_root = Path(raw)
                extracted = temporary_root / "extracted"
                extracted.mkdir()
                try:
                    PackManager._extract_archive(source, extracted)
                except PackError as exc:
                    raise LoaderError(str(exc)) from exc

                normalized = temporary_root / "normalized.zip"
                with zipfile.ZipFile(normalized, "w", compression=zipfile.ZIP_DEFLATED) as output:
                    for path in sorted(extracted.rglob("*")):
                        if path.is_file():
                            output.write(path, path.relative_to(extracted).as_posix())
                target = self._convert_loose_zip(normalized, display_source=source)
                return target, self.read_package(target), True

        try:
            with zipfile.ZipFile(source) as archive:
                names = {item.filename.replace("\\", "/") for item in archive.infolist()}
                if "manifest.json" in names:
                    package = self.read_package(source)
                    target = self.packages_dir / source.name
                    if source.resolve() != target.resolve():
                        shutil.copy2(source, target)
                    return target, package, False
        except zipfile.BadZipFile as exc:
            raise LoaderError(
                f"Unsupported mod package '{source.name}'. Select a .jmod or ZIP archive."
            ) from exc

        target = self._convert_loose_zip(source)
        return target, self.read_package(target), True

    def _convert_loose_zip(self, source: Path, display_source: Path | None = None) -> Path:
        """Turn a safe, conventional Nexus loose-file ZIP into a .jmod."""
        archive_source = display_source or source
        documentation_exts = {
            ".txt", ".md", ".rtf", ".pdf", ".png", ".jpg", ".jpeg",
            ".gif", ".webp", ".url",
        }
        installable_exts = {
            ".dll", ".asi", ".ini", ".cfg", ".conf", ".toml", ".json",
            ".xml", ".yaml", ".yml", ".lua", ".dat", ".bin", ".pak",
            ".forge", ".webm",
        }
        blocked_exts = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".lnk"}

        with zipfile.ZipFile(source) as archive:
            entries = []
            for item in archive.infolist():
                if item.is_dir():
                    continue
                raw = item.filename.replace("\\", "/").lstrip("/")
                path = Path(raw)
                if not raw or path.is_absolute() or ".." in path.parts:
                    raise LoaderError(f"Unsafe path in archive: {item.filename}")
                if any(part in {"__MACOSX", ".git"} for part in path.parts) or path.name == ".DS_Store":
                    continue
                entries.append((item, path))

            if not entries:
                raise LoaderError(f"'{source.name}' is empty.")

            # Nexus archives often add one wrapper directory. Strip it only
            # when every useful file shares it; all remaining paths stay intact.
            first_parts = {path.parts[0] for _, path in entries}
            strip_wrapper = len(first_parts) == 1 and all(len(path.parts) > 1 for _, path in entries)
            if strip_wrapper:
                entries = [(item, Path(*path.parts[1:])) for item, path in entries]
            selected_root = self._select_resynced_option(entries)
            if selected_root:
                entries = [
                    (item, path) for item, path in entries
                    if len(path.parts) == 1 or path.parts[0] == selected_root
                ]

            def deployment_path(path: Path) -> Path:
                if selected_root and len(path.parts) > 1 and path.parts[0] == selected_root:
                    return Path(*path.parts[1:])
                return path

            installable = []
            documents = []
            unknown = []
            for item, path in entries:
                relative = deployment_path(path)
                suffix = relative.suffix.lower()
                if suffix in blocked_exts:
                    raise LoaderError(
                        f"'{source.name}' contains an installer or script ({relative.as_posix()}). "
                        "Animus will not execute third-party installers automatically."
                    )
                if suffix in documentation_exts:
                    documents.append((item, relative))
                elif suffix in installable_exts:
                    installable.append((item, relative))
                else:
                    unknown.append(relative.as_posix())

            if unknown:
                preview = ", ".join(unknown[:4])
                if len(unknown) > 4:
                    preview += f" and {len(unknown) - 4} more"
                raise LoaderError(
                    f"Animus could not determine where these archive files belong: {preview}. "
                    "This mod needs an Animus manifest or a supported installer rule."
                )
            has_known_payload = any(
                path.suffix.lower() in {".dll", ".asi", ".forge", ".pak"}
                or (
                    path.suffix.lower() == ".webm"
                    and bool(path.parts)
                    and path.parts[0].lower() == "videos"
                )
                for _, path in installable
            )
            if not installable or not has_known_payload:
                raise LoaderError(
                    f"'{archive_source.name}' does not look like a supported game-root mod. "
                    "No DLL, ASI, FORGE, PAK, or videos/WEBM payload was found."
                )

            readme_text = ""
            for item, path in documents:
                if path.suffix.lower() in {".txt", ".md"} and "readme" in path.name.lower():
                    readme_text = archive.read(item).decode("utf-8", errors="replace")
                    break
            name, version = self._loose_archive_metadata(archive_source.stem, readme_text)
            nexus_mod_id = self._nexus_archive_mod_id(archive_source.stem)
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "Imported-Mod"
            target = self.packages_dir / f"{safe_name}.jmod"
            temporary = target.with_suffix(".tmp.jmod")
            manifest = {
                "format": FORMAT,
                "game": GAME,
                "name": name,
                "version": version,
                "author": "unknown",
                "category": "loose-file",
                "description": "Imported from a conventional Nexus loose-file archive.",
                "source_archive": archive_source.name,
                "targets": [],
            }
            if nexus_mod_id is not None:
                manifest["nexus"] = {"game_id": 9408, "mod_id": nexus_mod_id}
            if selected_root:
                manifest["selected_archive_root"] = selected_root
            chain_alias = self._proxy_chain_alias(readme_text, nexus_mod_id)
            if chain_alias:
                manifest["proxy_chain"] = {
                    "secondary": chain_alias,
                    "source": "documented-install-rule",
                }
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for index, (item, relative) in enumerate(installable):
                    resource = f"resources/{index:03d}-{relative.name}"
                    output.writestr(resource, archive.read(item))
                    manifest["targets"].append({
                        "mode": "loose-file",
                        "file": resource,
                        "dest": relative.as_posix(),
                    })
                for item, relative in documents:
                    output.writestr(f"documentation/{relative.as_posix()}", archive.read(item))
                output.writestr("manifest.json", json.dumps(manifest, indent=2))
            temporary.replace(target)
            return target

    @staticmethod
    def _loose_archive_metadata(fallback: str, readme: str) -> tuple[str, str]:
        name = fallback
        version = "1.0"
        # Nexus download names commonly end with:
        #   <mod id> <version> <UTC timestamp> <download token>
        # Remove that transport metadata before showing the package in the UI.
        nexus_suffix = re.search(
            r"(?i)\s+\d+\s+v?(\d+(?:\.\d+)*(?:\s*(?:alpha|beta))?)"
            r"\s+\d{4}-\d{2}-\d{2}T[^ ]+\s+[A-Za-z0-9]+$",
            fallback,
        )
        if nexus_suffix:
            name = fallback[:nexus_suffix.start()].strip()
            version = nexus_suffix.group(1).strip()
        title = re.search(
            r"(?im)^\s*([A-Z][A-Z0-9 '&_.-]{2,}?)\s+-\s+Assassin(?:'s)? Creed",
            readme,
        )
        if title:
            name = " ".join(word.capitalize() for word in title.group(1).split())
        found_version = re.search(r"(?im)^\s*version\s+([^\r\n]+?)\s*$", readme)
        if found_version:
            version = found_version.group(1).strip()
        elif not nexus_suffix:
            filename_version = re.search(r"(?i)(?:^|[ _-])v?(\d+(?:\.\d+)+(?:\s*(?:alpha|beta))?)", fallback)
            if filename_version:
                version = filename_version.group(1).strip()
        return name, version

    @staticmethod
    def _select_resynced_option(entries: list[tuple[object, Path]]) -> str | None:
        """Choose an explicit Resynced/64-bit option from a universal archive."""
        roots = sorted({path.parts[0] for _, path in entries if len(path.parts) > 1})
        if len(roots) < 2:
            return None

        def score(root: str) -> int:
            label = root.lower().replace("_", " ").replace("-", " ")
            value = 0
            if "resynced" in label:
                value += 100
            if "64 bit" in label or "x64" in label:
                value += 30
            if "dx12" in label or "directx 12" in label:
                value += 20
            if "32 bit" in label or "standard" in label or "original" in label:
                value -= 100
            return value

        ranked = sorted(((score(root), root) for root in roots), reverse=True)
        if ranked[0][0] <= 0:
            return None
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None
        return ranked[0][1]

    @staticmethod
    def _nexus_archive_mod_id(fallback: str) -> int | None:
        """Read Nexus' trailing mod id from a downloaded archive filename."""
        match = re.search(
            r"(?i)\s+(\d+)\s+v?\d+(?:\.\d+)*(?:\s*(?:alpha|beta))?"
            r"\s+\d{4}-\d{2}-\d{2}T[^ ]+\s+[A-Za-z0-9]+$",
            fallback,
        )
        return int(match.group(1)) if match else None

    @staticmethod
    def _proxy_chain_alias(readme: str, nexus_mod_id: int | None) -> str | None:
        """Return a documented secondary proxy filename, never a guess.

        Proxy DLLs are executable code; renaming one arbitrarily is unsafe.
        A chain is enabled only when an included readme explicitly documents
        it, or when a reviewed Nexus-specific rule records the same published
        installation instruction.
        """
        documented = re.search(
            r"(?is)rename.{0,80}(?:existing|old|current).{0,40}version\.dll"
            r".{0,80}(wininet\.dll|versionhooked\.dll)",
            readme or "",
        )
        if documented:
            return documented.group(1).lower()
        # Nexus mod 428 explicitly instructs users to rename an existing
        # version.dll to wininet.dll so its proxy can load it.
        return "wininet.dll" if nexus_mod_id == 428 else None

    def _manifest_to_package(self, manifest: dict, archive) -> Package:
        if manifest.get("format") != FORMAT:
            raise LoaderError("Unsupported manifest format")
        if manifest.get("game") != GAME:
            raise LoaderError("Unsupported game in manifest")
        name = manifest.get("name") or "Untitled"
        version = manifest.get("version") or "0.0.0"
        author = manifest.get("author") or "unknown"
        targets: list[Target] = []
        raw_targets = manifest.get("targets") or []
        for index, target in enumerate(raw_targets, start=1):
            resource_id = target.get("resource_id", "0")
            try:
                rid = int(resource_id, 0)
            except ValueError as exc:
                raise LoaderError(f"Target {index} has invalid resource_id") from exc
            file = target.get("file", "")
            replacement = archive.read(file) if file else b""
            needle_hex = target.get("needle")
            patch_hex = target.get("patch")
            targets.append(
                Target(
                    forge=target.get("forge", ""),
                    resource_id=rid,
                    occurrence=target.get("occurrence", 0),
                    bms_block=target.get("bms_block", 0),
                    mode=target.get("mode", "decoded-resource"),
                    file=file,
                    replacement=replacement,
                    sha256=target.get("sha256"),
                    expected_original=(
                        bytes.fromhex(target["expected_original"])
                        if target.get("expected_original") else None
                    ),
                    expected_original_size=target.get("expected_original_size"),
                    expected_original_sha256=target.get("expected_original_sha256"),
                    needle=bytes.fromhex(needle_hex) if needle_hex else None,
                    patch_offset=int(target.get("patch_offset", 0), 0) if target.get("patch_offset") else None,
                    patch=bytes.fromhex(patch_hex) if patch_hex else None,
                    original=bytes.fromhex(target["original"]) if target.get("original") else None,
                    dest=target.get("dest"),
                )
            )
        return Package(
            name=name,
            version=version,
            author=author,
            manifest=manifest,
            targets=targets,
            category=manifest.get("category", "forge-resource"),
        )

    # ------------------------------------------------------------------ #
    # state
    # ------------------------------------------------------------------ #
    def _compact_legacy_state(self) -> None:
        """Remove duplicated inline backup bytes from oversized state files.

        Older builds stored every loose-file backup twice: once in the backup
        file and again as a hex string in installed-mods.json. A large video
        replacer could therefore turn the JSON file into several gigabytes and
        make startup, toggles, and uninstall appear to hang. The backup file is
        already the authoritative copy, so replace only those legacy strings
        with null using a bounded-memory streaming pass.
        """
        if not self.state_path.is_file() or self.state_path.stat().st_size < 16 * 1024 * 1024:
            return

        marker = b'"original_hex": "'
        temp_path = self.state_path.with_suffix(".json.compacting")
        buffer = b""
        skipping_value = False
        try:
            with self.state_path.open("rb") as source, temp_path.open("wb") as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    eof = not chunk
                    data = buffer + chunk
                    buffer = b""
                    while data:
                        if skipping_value:
                            closing_quote = data.find(b'"')
                            if closing_quote < 0:
                                data = b""
                                break
                            data = data[closing_quote + 1:]
                            skipping_value = False
                            continue

                        position = data.find(marker)
                        if position >= 0:
                            target.write(data[:position])
                            target.write(b'"original_hex": null')
                            data = data[position + len(marker):]
                            skipping_value = True
                            continue

                        if eof:
                            target.write(data)
                            data = b""
                        else:
                            tail = min(len(data), len(marker) - 1)
                            target.write(data[:-tail] if tail else data)
                            buffer = data[-tail:] if tail else b""
                            data = b""
                    if eof:
                        break
            if skipping_value:
                raise LoaderError("Installed-mod state ended inside an inline backup value")
            # Validate the compacted file before replacing the user's state.
            json.loads(temp_path.read_text(encoding="utf-8"))
            os.replace(temp_path, self.state_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _load_state(self) -> list[InstallRecord]:
        if not self.state_path.is_file():
            return []
        try:
            self._compact_legacy_state()
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return [
                InstallRecord(
                    name=rec.get("name", ""),
                    version=rec.get("version", ""),
                    author=rec.get("author", ""),
                    enabled=rec.get("enabled", True),
                    priority=rec.get("priority", 0),
                    backups=rec.get("backups", []),
                )
                for rec in raw
            ]
        except (json.JSONDecodeError, OSError, MemoryError):
            return []

    def _save_state(self, records: list[InstallRecord]) -> None:
        payload = [
            {
                "name": rec.name,
                "version": rec.version,
                "author": rec.author,
                "enabled": rec.enabled,
                "priority": rec.priority,
                "backups": rec.backups,
            }
            for rec in records
        ]
        temp_path = self.state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, self.state_path)

    def list_installed(self) -> list[InstallRecord]:
        return self._load_state()

    def detect_conflicts(self) -> list[dict]:
        """Report loose-file destinations claimed by more than one package.

        Returns a list of {dest, packages:[...]} records. This is the key
        collision surface: files like version.dll can only be owned by one
        package at a time.
        """
        claimed: dict[str, list[dict]] = {}
        for path in self.discover_packages():
            try:
                pkg = self.read_package(path)
            except LoaderError:
                continue
            for target in pkg.targets:
                if target.mode == "loose-file" and target.dest:
                    kind = None
                    chain_alias = None
                    if Path(target.dest).as_posix().lower() == "version.dll":
                        kind = inspect_proxy_dll(target.replacement).get("kind")
                        chain = pkg.manifest.get("proxy_chain")
                        if isinstance(chain, dict):
                            candidate = Path(str(chain.get("secondary", ""))).as_posix().lower()
                            if candidate in {"wininet.dll", "versionhooked.dll"}:
                                chain_alias = candidate
                    claimed.setdefault(target.dest, []).append({
                        "name": pkg.name,
                        "dll_kind": kind,
                        "chain_alias": chain_alias,
                    })
        conflicts = []
        for dest, owners in claimed.items():
            if len(owners) <= 1:
                continue
            if Path(dest).as_posix().lower() == "version.dll":
                loaders = [item for item in owners if item["dll_kind"] == "ultimate-asi-loader"]
                custom = [item for item in owners if item["dll_kind"] != "ultimate-asi-loader"]
                if loaders and len(custom) <= 1:
                    continue
                if len(owners) == 2 and any(item.get("chain_alias") for item in owners):
                    continue
            conflicts.append({"dest": dest, "names": [item["name"] for item in owners]})
        return conflicts

    def set_nexus(self, name: str, mod_id: int, game_id: int | None = None,
                  version: str | None = None) -> None:
        """Attach Nexus mod metadata to a .jmod package manifest (for update
        checks). Rewrites the package in place."""
        import zipfile
        path = next((p for p in self.discover_packages()
                     if self._name_of_package(p) == name), None)
        if path is None:
            raise LoaderError(f"Unknown mod: {name}")
        from .nexus import NEXUS_GAME_ID, NexusClient
        resolved_game_id = game_id or NEXUS_GAME_ID
        nexus_meta: dict = {}
        try:
            nexus_meta = NexusClient().mod(int(mod_id), int(resolved_game_id))
        except Exception:
            # Saving the public page link must still work while Nexus is down.
            pass
        tmp = path.with_suffix(".tmp.jmod")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
            manifest = json.loads(src.read("manifest.json").decode("utf-8"))
            manifest["nexus"] = {
                "game_id": resolved_game_id,
                "mod_id": int(mod_id),
            }
            if version is not None:
                manifest["version"] = str(version)
            elif nexus_meta.get("version"):
                manifest["version"] = str(nexus_meta["version"])
            if nexus_meta.get("author"):
                manifest["author"] = str(nexus_meta["author"])
            if nexus_meta.get("summary") and not manifest.get("description"):
                manifest["description"] = str(nexus_meta["summary"])
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "manifest.json":
                    data = json.dumps(manifest, indent=2).encode("utf-8")
                dst.writestr(item, data)
        tmp.replace(path)

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a managed mod while retaining its deployment record."""
        new_name = str(new_name).strip()
        if not new_name:
            raise LoaderError("A mod name cannot be empty.")
        if len(new_name) > 120:
            raise LoaderError("A mod name cannot exceed 120 characters.")
        if old_name == new_name:
            return
        existing = [self._name_of_package(path) for path in self.discover_packages()]
        if any(name.casefold() == new_name.casefold() for name in existing
               if name.casefold() != old_name.casefold()):
            raise LoaderError(f"A mod named '{new_name}' already exists.")
        path = next((candidate for candidate in self.discover_packages()
                     if self._name_of_package(candidate) == old_name), None)
        if path is None:
            raise LoaderError(f"Unknown mod: {old_name}")

        tmp = path.with_suffix(".tmp.jmod")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
            manifest = json.loads(src.read("manifest.json").decode("utf-8"))
            manifest["name"] = new_name
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "manifest.json":
                    data = json.dumps(manifest, indent=2).encode("utf-8")
                dst.writestr(item, data)
        tmp.replace(path)

        records = self._load_state()
        for record in records:
            if record.name == old_name:
                record.name = new_name
        self._save_state(records)

    def _name_of_package(self, path) -> str:
        try:
            return self.read_package(path).name
        except LoaderError:
            return path.stem

    def check_updates(self, client=None) -> list[dict]:
        """Check all .jmod packages that carry a Nexus id for updates."""
        from .nexus import NexusClient
        client = client or NexusClient()
        results: list[dict] = []
        for path in self.discover_packages():
            try:
                pkg = self.read_package(path)
            except LoaderError:
                continue
            manifest = pkg.manifest
            nexus = manifest.get("nexus")
            if not nexus:
                results.append({"name": pkg.name, "path": str(path),
                                "has_update": False, "mod_id": None, "error": "no nexus id"})
                continue
            game_id = nexus.get("game_id", 9408)
            mod_id = nexus.get("mod_id")
            current = pkg.version
            latest = None
            err = None
            try:
                latest = client.latest_version(int(mod_id), int(game_id))
            except Exception as exc:
                err = str(exc)
            has_update = False
            if latest and current and latest != current:
                try:
                    has_update = _version_gt(latest, current)
                except ValueError:
                    has_update = latest != current
            results.append({
                "name": pkg.name,
                "path": str(path),
                "game_id": game_id,
                "mod_id": mod_id,
                "current": current,
                "latest": latest,
                "has_update": has_update,
                "error": err,
            })
        return results

    # ------------------------------------------------------------------ #
    # apply
    # ------------------------------------------------------------------ #
    def _apply_target(self, pkg: Package, target: Target) -> list[dict]:
        """Apply one target; return a backup record entry."""
        if target.mode == "byte-patch":
            return self._apply_byte_patch(pkg, target)
        if target.mode == "loose-file":
            return self._apply_loose_file(pkg, target)
        if target.mode != "decoded-resource":
            raise LoaderError(
                f"Unsupported install mode for {pkg.name}: {target.mode}"
            )
        if not target.replacement:
            raise LoaderError(f"{pkg.name}: target has an empty replacement resource")

        forge_path = self.game_dir / target.forge
        if not forge_path.is_file():
            raise LoaderError(
                f"{pkg.name}: forge not found at {forge_path} (wrong game folder?)"
            )

        editor = ForgeEditor(forge_path)
        entries = editor.find_resource_entries(target.resource_id)
        if not entries:
            raise LoaderError(f"{pkg.name}: resource 0x{target.resource_id:016X} not found in {target.forge}")

        occurrence = target.occurrence
        if occurrence >= len(entries):
            raise LoaderError(
                f"{pkg.name}: occurrence {occurrence} out of range (found {len(entries)})"
            )
        offset, stored_size = entries[occurrence]

        if len(target.replacement) != stored_size:
            raise LoaderError(
                f"{pkg.name}: replacement size {len(target.replacement)} != stored size {stored_size} "
                f"(same-size in-place replacement required)"
            )
        if (
            target.expected_original_size is not None
            and stored_size != target.expected_original_size
        ):
            raise LoaderError(
                f"{pkg.name}: stored size {stored_size} != expected original size "
                f"{target.expected_original_size}"
            )

        with forge_path.open("rb") as handle:
            handle.seek(offset)
            original = handle.read(stored_size)

        if len(original) != stored_size:
            raise LoaderError(
                f"{pkg.name}: stored resource is truncated at 0x{offset:X}"
            )

        if target.expected_original and original != target.expected_original:
            raise LoaderError(
                f"{pkg.name}: original bytes at 0x{offset:X} do not match expected original"
            )
        if target.expected_original_sha256:
            found = hashlib.sha256(original).hexdigest()
            if found != target.expected_original_sha256:
                raise LoaderError(
                    f"{pkg.name}: original sha256 mismatch (expected {target.expected_original_sha256}, found {found})"
                )

        # Backup the exact stored block before overwriting.
        backup_name = f"{forge_path.name}.{pkg.name}.{pkg.version}.{offset:X}.bak"
        backup_path = self.backups_dir / backup_name
        backup_path.write_bytes(original)
        backup_entry = {
            "forge": target.forge,
            "resource_id": f"0x{target.resource_id:016X}",
            "occurrence": occurrence,
            "offset": offset,
            "backup": str(backup_path),
            "original_hex": None,
        }

        # Apply.
        with forge_path.open("r+b") as handle:
            handle.seek(offset)
            handle.write(target.replacement)
        return backup_entry

    def _apply_byte_patch(self, pkg: Package, target: Target) -> list[dict]:
        """Apply a find-and-replace byte patch with original-byte validation."""
        if not target.needle or target.patch is None:
            raise LoaderError(f"{pkg.name}: byte-patch target needs 'needle' and 'patch' hex strings")
        if len(target.needle) != len(target.patch):
            raise LoaderError(f"{pkg.name}: needle and patch must be the same length for in-place replace")

        forge_path = self.game_dir / target.forge
        if not forge_path.is_file():
            raise LoaderError(f"{pkg.name}: forge not found at {forge_path}")

        # Scan the whole file for the needle.
        occurrences: list[int] = []
        with forge_path.open("rb") as handle:
            cursor = 0
            overlap = b""
            while True:
                chunk = handle.read(1 << 20)
                if not chunk:
                    break
                data = overlap + chunk
                start = 0
                while True:
                    pos = data.find(target.needle, start)
                    if pos < 0:
                        break
                    occurrences.append(cursor - len(overlap) + pos)
                    start = pos + 1
                overlap = data[-(len(target.needle) - 1):]
                cursor += len(chunk)

        if target.occurrence >= len(occurrences):
            raise LoaderError(
                f"{pkg.name}: needle occurrence {target.occurrence} not found in {target.forge}"
            )
        offset = occurrences[target.occurrence]

        with forge_path.open("rb") as handle:
            handle.seek(offset)
            original = handle.read(len(target.needle))

        if target.original and original != target.original:
            raise LoaderError(
                f"{pkg.name}: bytes at 0x{offset:X} do not match the expected original"
            )

        backup_name = f"{forge_path.name}.{pkg.name}.{pkg.version}.{offset:X}.bak"
        backup_path = self.backups_dir / backup_name
        backup_path.write_bytes(original)
        backup_entry = {
            "forge": target.forge,
            "resource_id": f"0x{target.resource_id:016X}",
            "occurrence": target.occurrence,
            "offset": offset,
            "mode": "byte-patch",
            "needle": target.needle.hex(),
            "patch": target.patch.hex(),
            "backup": str(backup_path),
            "original_hex": None,
        }

        with forge_path.open("r+b") as handle:
            handle.seek(offset)
            handle.write(target.patch)
        return backup_entry

    def proxy_status(self) -> dict:
        """Describe the active version.dll and manager-owned proxy chain."""
        version_path = self.game_dir / "version.dll"
        hook_path = self.game_dir / "versionHooked.dll"
        if version_path.is_file():
            info = inspect_proxy_dll(version_path.read_bytes())
            info["present"] = True
        else:
            info = {
                "present": False, "valid_pe": False, "architecture": "unknown",
                "machine": None, "kind": "missing", "sha256": None,
            }
        hook_info = inspect_proxy_dll(hook_path.read_bytes()) if hook_path.is_file() else None
        owners: list[str] = []
        chained: list[str] = []
        chain_files: list[str] = []
        for record in self._load_state():
            if not record.enabled:
                continue
            for backup in record.backups:
                if backup.get("mode") != "loose-file":
                    continue
                dest = str(backup.get("dest", "")).replace("\\", "/").lower()
                if dest == "version.dll":
                    owners.append(record.name)
                elif backup.get("chain_loader_dest") and dest:
                    chained.append(record.name)
                    chain_files.append(dest)
        chain_files = sorted(set(chain_files))
        hook_present = any((self.game_dir / name).is_file() for name in chain_files)
        if not chain_files and hook_path.is_file():
            chain_files = ["versionhooked.dll"]
            hook_present = True
        info.update({
            "hook_present": hook_present,
            "hook": hook_info,
            "chain_files": chain_files,
            "owners": owners,
            "chained": chained,
            "compatible": not chained or hook_present,
        })
        return info

    def ensure_proxy_compatibility(self) -> dict:
        """Normalize legacy enabled version.dll owners into one safe chain.

        Older manager builds allowed several enabled packages to overwrite the
        same proxy filename. If exactly one custom proxy and an Ultimate ASI
        Loader are present, preserve the ASI loader as version.dll and move the
        custom proxy to the documented versionHooked.dll chain position.
        """
        records = self._load_state()
        intents: list[tuple[InstallRecord, bytes, dict]] = []
        for record in records:
            if not record.enabled:
                continue
            content = self._package_target_bytes(record.name, "version.dll")
            if content is None:
                continue
            info = inspect_proxy_dll(content)
            if info["valid_pe"]:
                intents.append((record, content, info))
        loaders = [item for item in intents if item[2]["kind"] == "ultimate-asi-loader"]
        custom = [item for item in intents if item[2]["kind"] != "ultimate-asi-loader"]
        if not loaders or not custom:
            return {"changed": False, "message": None}
        if len(custom) > 1:
            return {
                "changed": False,
                "message": "Multiple custom version.dll proxies are enabled; only one can be chained safely.",
            }

        custom_record, custom_bytes, custom_info = custom[0]
        loader_record, loader_bytes, loader_info = loaders[0]
        if custom_info["architecture"] != loader_info["architecture"]:
            return {
                "changed": False,
                "message": "Enabled version.dll proxies use different architectures and cannot be chained.",
            }
        version_path = self.game_dir / "version.dll"
        hook_path = self.game_dir / "versionHooked.dll"
        if hook_path.is_file() and hook_path.read_bytes() != custom_bytes:
            return {
                "changed": False,
                "message": "versionHooked.dll is occupied by an unknown proxy; automatic chaining was skipped.",
            }

        current = version_path.read_bytes() if version_path.is_file() else b""
        current_info = inspect_proxy_dll(current) if current else {"kind": "missing"}
        if current and current_info.get("kind") not in {"ultimate-asi-loader", "proxy-dll"}:
            return {"changed": False, "message": "Unknown version.dll detected; automatic chaining was skipped."}
        already_chained = any(
            record.name == custom_record.name and
            any(Path(str(entry.get("dest", ""))).as_posix().lower() == "versionhooked.dll" and
                entry.get("chain_loader_dest") == "version.dll" for entry in record.backups)
            for record in records
        )
        if (already_chained and hook_path.is_file() and hook_path.read_bytes() == custom_bytes and
                current_info.get("kind") == "ultimate-asi-loader"):
            return {"changed": False, "message": None}

        hook_path.write_bytes(custom_bytes)
        if current_info.get("kind") != "ultimate-asi-loader":
            version_path.write_bytes(loader_bytes)
        active_loader_hash = sha256_file(version_path)

        for record in records:
            for index, entry in enumerate(record.backups):
                if (entry.get("mode") != "loose-file" or
                        Path(str(entry.get("dest", ""))).as_posix().lower() != "version.dll"):
                    continue
                if record.name == custom_record.name:
                    migrated = dict(entry)
                    migrated.update({
                        "file": "versionHooked.dll", "dest": "versionHooked.dll",
                        "requested_dest": "version.dll", "backup": None, "original_hex": None,
                        "installed_sha256": custom_info["sha256"],
                        "dll_kind": custom_info["kind"], "chain_loader_dest": "version.dll",
                        "chain_loader_sha256": active_loader_hash,
                        "compatibility": "normalized-behind-asi-loader",
                    })
                    record.backups[index] = migrated
                elif record.name == loader_record.name:
                    entry["installed_sha256"] = active_loader_hash
                    entry["dll_kind"] = "ultimate-asi-loader"
                    entry["compatibility"] = "normalized-primary-loader"
        self._save_state(records)
        return {
            "changed": True,
            "message": f"Chained '{custom_record.name}' behind Ultimate ASI Loader.",
        }

    def _package_target_bytes(self, package_name: str, destination: str) -> bytes | None:
        for path in self.discover_packages():
            try:
                package = self.read_package(path)
            except LoaderError:
                continue
            if package.name != package_name:
                continue
            for target in package.targets:
                if (target.mode == "loose-file" and target.dest and
                        Path(target.dest).as_posix().lower() == destination.lower()):
                    return target.replacement
        return None

    def _package_proxy_chain_alias(self, package_name: str) -> str | None:
        """Return a package's explicitly declared secondary proxy filename."""
        for path in self.discover_packages():
            try:
                package = self.read_package(path)
            except LoaderError:
                continue
            if package.name != package_name:
                continue
            chain = package.manifest.get("proxy_chain")
            alias = chain.get("secondary") if isinstance(chain, dict) else None
            normalized = Path(str(alias or "")).as_posix().lower()
            if normalized in {"wininet.dll", "versionhooked.dll"}:
                return normalized
            return None
        return None

    def _managed_owner_for_bytes(self, destination: str, content: bytes) -> tuple[InstallRecord, dict] | None:
        for record in self._load_state():
            if not record.enabled:
                continue
            expected = self._package_target_bytes(record.name, destination)
            if expected != content:
                continue
            for backup in record.backups:
                if (backup.get("mode") == "loose-file" and
                        Path(str(backup.get("dest", ""))).as_posix().lower() == destination.lower()):
                    return record, backup
        return None

    def _save_migrated_record(self, migrated: InstallRecord, entry: dict) -> None:
        records = self._load_state()
        for record in records:
            if record.name != migrated.name:
                continue
            for index, backup in enumerate(record.backups):
                if (backup.get("mode") == "loose-file" and
                        Path(str(backup.get("dest", ""))).as_posix().lower() == "version.dll"):
                    record.backups[index] = entry
                    self._save_state(records)
                    return

    def _write_backup(self, path: Path, pkg: Package, original: bytes) -> Path:
        backup_name = f"{path.name}.{pkg.name}.{pkg.version}.bak"
        backup_path = self.backups_dir / backup_name
        backup_path.write_bytes(original)
        return backup_path

    def _apply_version_proxy(self, pkg: Package, target: Target, dest_path: Path) -> dict:
        incoming = target.replacement
        incoming_info = inspect_proxy_dll(incoming)
        if not incoming_info["valid_pe"]:
            raise LoaderError(f"{pkg.name}: version.dll is not a valid Windows PE DLL")

        incoming_hash = incoming_info["sha256"]
        if not dest_path.is_file():
            dest_path.write_bytes(incoming)
            return {
                "mode": "loose-file", "file": "version.dll", "dest": "version.dll",
                "backup": None, "original_hex": None,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "compatibility": "installed-primary",
            }

        existing = dest_path.read_bytes()
        existing_info = inspect_proxy_dll(existing)
        if existing == incoming:
            return {
                "mode": "loose-file", "file": "version.dll", "dest": "version.dll",
                "backup": None, "original_hex": None, "shared": True,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "compatibility": "shared-identical",
            }
        if not existing_info["valid_pe"]:
            raise LoaderError(
                f"{pkg.name}: an unknown non-PE version.dll already exists. "
                "It was not overwritten; remove it manually only if you know its owner."
            )
        if existing_info["architecture"] != incoming_info["architecture"]:
            raise LoaderError(
                f"{pkg.name}: version.dll architecture conflict "
                f"({existing_info['architecture']} installed, {incoming_info['architecture']} requested)"
            )

        existing_ual = existing_info["kind"] == "ultimate-asi-loader"
        incoming_ual = incoming_info["kind"] == "ultimate-asi-loader"
        if existing_ual and incoming_ual:
            return {
                "mode": "loose-file", "file": "version.dll", "dest": "version.dll",
                "backup": None, "original_hex": None, "shared": True,
                "installed_sha256": existing_info["sha256"], "dll_kind": existing_info["kind"],
                "compatibility": "shared-asi-loader",
            }

        hook_path = self.game_dir / "versionHooked.dll"
        if existing_ual and not incoming_ual:
            if hook_path.is_file() and hook_path.read_bytes() != incoming:
                raise LoaderError(
                    f"{pkg.name}: versionHooked.dll is already occupied by another proxy. "
                    "Only one chained version proxy can be active."
                )
            hook_original = hook_path.read_bytes() if hook_path.is_file() else None
            hook_backup = self._write_backup(hook_path, pkg, hook_original) if hook_original is not None else None
            hook_path.write_bytes(incoming)
            return {
                "mode": "loose-file", "file": "versionHooked.dll", "dest": "versionHooked.dll",
                "requested_dest": "version.dll",
                "backup": str(hook_backup) if hook_backup else None,
                "original_hex": None,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "chain_loader_dest": "version.dll",
                "chain_loader_sha256": existing_info["sha256"],
                "compatibility": "chained-behind-asi-loader",
            }

        if incoming_ual and not existing_ual:
            if hook_path.is_file() and hook_path.read_bytes() != existing:
                raise LoaderError(
                    f"{pkg.name}: cannot preserve the existing version.dll because "
                    "versionHooked.dll is already occupied."
                )
            managed = self._managed_owner_for_bytes("version.dll", existing)
            hook_path.write_bytes(existing)
            if managed:
                owner, old_entry = managed
                migrated = dict(old_entry)
                migrated.update({
                    "file": "versionHooked.dll", "dest": "versionHooked.dll",
                    "requested_dest": "version.dll", "backup": None, "original_hex": None,
                    "installed_sha256": existing_info["sha256"],
                    "dll_kind": existing_info["kind"], "chain_loader_dest": "version.dll",
                    "chain_loader_sha256": incoming_hash,
                    "compatibility": "migrated-behind-asi-loader",
                })
                self._save_migrated_record(owner, migrated)
                original = None
                backup_path = None
                external_hook = None
            else:
                original = existing
                backup_path = self._write_backup(dest_path, pkg, original)
                external_hook = "versionHooked.dll"
            dest_path.write_bytes(incoming)
            return {
                "mode": "loose-file", "file": "version.dll", "dest": "version.dll",
                "backup": str(backup_path) if backup_path else None,
                "original_hex": None,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "external_chain_hook": external_hook,
                "external_chain_sha256": existing_info["sha256"] if external_hook else None,
                "compatibility": "asi-loader-with-preserved-proxy",
            }

        # Some custom proxies explicitly support loading a second proxy under
        # another DLL name. Never invent this alias: it comes from a reviewed
        # Nexus rule or the package's own install documentation.
        managed = self._managed_owner_for_bytes("version.dll", existing)
        incoming_chain = pkg.manifest.get("proxy_chain")
        incoming_alias = (
            Path(str(incoming_chain.get("secondary", ""))).as_posix().lower()
            if isinstance(incoming_chain, dict) else ""
        )
        if incoming_alias not in {"wininet.dll", "versionhooked.dll"}:
            incoming_alias = ""

        existing_alias = self._package_proxy_chain_alias(managed[0].name) if managed else None
        if incoming_alias:
            alias_path = self.game_dir / incoming_alias
            if alias_path.is_file():
                raise LoaderError(
                    f"{pkg.name}: cannot create the documented DLL chain because "
                    f"{incoming_alias} is already occupied."
                )
            alias_path.write_bytes(existing)
            if managed:
                owner, old_entry = managed
                migrated = dict(old_entry)
                migrated.update({
                    "file": incoming_alias, "dest": incoming_alias,
                    "requested_dest": "version.dll", "backup": None,
                    "original_hex": None,
                    "installed_sha256": existing_info["sha256"],
                    "dll_kind": existing_info["kind"],
                    "chain_loader_dest": "version.dll",
                    "chain_loader_sha256": incoming_hash,
                    "compatibility": f"chained-as-{incoming_alias}",
                })
                self._save_migrated_record(owner, migrated)
                backup_path = None
                external_hook = None
            else:
                backup_path = self._write_backup(dest_path, pkg, existing)
                external_hook = incoming_alias
            dest_path.write_bytes(incoming)
            return {
                "mode": "loose-file", "file": "version.dll", "dest": "version.dll",
                "backup": str(backup_path) if backup_path else None,
                "original_hex": None,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "external_chain_hook": external_hook,
                "external_chain_sha256": existing_info["sha256"] if external_hook else None,
                "compatibility": f"primary-with-{incoming_alias}-chain",
            }

        if existing_alias and managed:
            alias_path = self.game_dir / existing_alias
            if alias_path.is_file():
                raise LoaderError(
                    f"{pkg.name}: cannot join the existing DLL chain because "
                    f"{existing_alias} is already occupied."
                )
            alias_path.write_bytes(incoming)
            return {
                "mode": "loose-file", "file": existing_alias, "dest": existing_alias,
                "requested_dest": "version.dll", "backup": None, "original_hex": None,
                "installed_sha256": incoming_hash, "dll_kind": incoming_info["kind"],
                "chain_loader_dest": "version.dll",
                "chain_loader_sha256": existing_info["sha256"],
                "compatibility": f"chained-as-{existing_alias}",
            }

        raise LoaderError(
            f"{pkg.name}: version.dll conflicts with another custom proxy DLL. "
            "Neither mod declares a safe chaining filename, so Animus left both files unchanged."
        )

    def _apply_loose_file(self, pkg: Package, target: Target) -> list[dict]:
        """Copy a file into the game directory with backup of any existing file."""
        if not target.replacement:
            raise LoaderError(f"{pkg.name}: loose-file target has empty content")
        if not target.dest:
            raise LoaderError(f"{pkg.name}: loose-file target is missing 'dest'")
        # Sanitize the destination so it cannot escape the game directory.
        dest = Path(target.dest)
        if dest.is_absolute() or ".." in dest.parts:
            raise LoaderError(f"{pkg.name}: loose-file destination is unsafe: {target.dest}")
        dest_path = self.game_dir / dest
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if dest.as_posix().lower() == "version.dll":
            return self._apply_version_proxy(pkg, target, dest_path)

        original = None
        if dest_path.is_file():
            original = dest_path.read_bytes()

        if original == target.replacement:
            return {
                "mode": "loose-file", "file": dest.as_posix(), "dest": target.dest,
                "backup": None, "original_hex": None, "shared": True,
                "installed_sha256": hashlib.sha256(target.replacement).hexdigest(),
            }

        backup_path = None
        if original is not None:
            backup_path = self._write_backup(dest_path, pkg, original)

        dest_path.write_bytes(target.replacement)
        return {
            "mode": "loose-file",
            "file": dest.as_posix(),
            "dest": target.dest,
            "backup": str(backup_path) if backup_path else None,
            "original_hex": None,
            "installed_sha256": hashlib.sha256(target.replacement).hexdigest(),
        }

    def apply(self, package_path: Path, priority: int = 0) -> list[dict]:
        """Apply a package's targets and record backups.

        Idempotent: any previously recorded backups for this package are
        restored first, so re-applying never double-patches.
        """
        pkg = self.read_package(package_path)
        # Restore any previous state for this package first.
        self.remove(pkg.name)
        backups: list[dict] = []
        for target in pkg.targets:
            backups.append(self._apply_target(pkg, target))
        # Record install state.
        records = self._load_state()
        record = InstallRecord(pkg.name, pkg.version, pkg.author, enabled=True, priority=priority)
        record.backups = backups
        records.append(record)
        self._save_state(records)
        return backups

    def remove(self, name: str) -> list[Path]:
        """Restore backups for a package and drop it from state."""
        records = self._load_state()
        record = next((r for r in records if r.name == name), None)
        if record is None:
            return []
        remaining = [r for r in records if r.name != name]

        # A chained proxy cannot run without its primary ASI loader. Refuse to
        # remove that loader until its dependants have been disabled first.
        for backup in record.backups:
            if backup.get("mode") != "loose-file":
                continue
            destination = Path(str(backup.get("dest", ""))).as_posix().lower()
            dependants = [
                other.name
                for other in remaining if other.enabled
                for entry in other.backups
                if Path(str(entry.get("chain_loader_dest", ""))).as_posix().lower() == destination
            ]
            if dependants:
                raise LoaderError(
                    f"Cannot disable '{name}' while chained mod(s) depend on it: "
                    + ", ".join(dependants)
                )

        restored: list[Path] = []
        for backup in record.backups:
            if backup.get("mode") == "loose-file":
                destination = str(backup.get("dest", ""))
                dest_path = self.game_dir / destination
                if backup.get("shared"):
                    continue

                installed_hash = backup.get("installed_sha256")
                current_hash = sha256_file(dest_path) if dest_path.is_file() else None
                if installed_hash and current_hash and current_hash != installed_hash:
                    raise LoaderError(
                        f"Cannot safely remove '{name}': {destination} was changed by another tool."
                    )

                # If another enabled package shares the exact same file, hand
                # it responsibility for restoring the original on final removal.
                consumer = None
                if installed_hash and current_hash == installed_hash:
                    for other in remaining:
                        if not other.enabled:
                            continue
                        for entry in other.backups:
                            same_dest = Path(str(entry.get("dest", ""))).as_posix().lower() == Path(destination).as_posix().lower()
                            if same_dest and entry.get("installed_sha256") == installed_hash:
                                consumer = entry
                                break
                        if consumer is not None:
                            break
                if consumer is not None:
                    consumer["shared"] = False
                    consumer["backup"] = backup.get("backup")
                    consumer["original_hex"] = backup.get("original_hex")
                    consumer["compatibility"] = "shared-ownership-transferred"
                    continue

                original = None
                backup_file = Path(backup.get("backup", "")) if backup.get("backup") else None
                if backup_file and backup_file.is_file():
                    original = backup_file.read_bytes()
                elif backup.get("original_hex"):
                    original = bytes.fromhex(backup["original_hex"])
                if original is not None:
                    dest_path.write_bytes(original)
                    restored.append(dest_path)
                elif dest_path.is_file() and (not installed_hash or current_hash == installed_hash):
                    dest_path.unlink()
                    restored.append(dest_path)

                external_hook = backup.get("external_chain_hook")
                if external_hook:
                    hook_path = self.game_dir / str(external_hook)
                    expected_hook = backup.get("external_chain_sha256")
                    if hook_path.is_file() and (not expected_hook or sha256_file(hook_path) == expected_hook):
                        hook_path.unlink()
                continue

            forge_path = self.game_dir / backup.get("forge", "")
            if not forge_path.is_file():
                continue
            offset = backup.get("offset")
            original = None
            backup_file = Path(backup.get("backup", ""))
            if backup_file.is_file():
                original = backup_file.read_bytes()
            elif backup.get("original_hex"):
                original = bytes.fromhex(backup["original_hex"])
            if original is None:
                continue
            with forge_path.open("r+b") as handle:
                handle.seek(int(offset))
                handle.write(original)
            restored.append(forge_path)
        self._save_state(remaining)
        return restored

    def disable(self, name: str) -> list[Path]:
        """Restore a package while retaining it as a disabled library entry.

        ``remove`` is the uninstall primitive and deliberately drops the
        install record.  A UI toggle is different: the package remains owned
        by the manager and visible in the list, but none of its writes remain
        active in the game.
        """
        records = self._load_state()
        record = next((item for item in records if item.name == name), None)
        if record is None:
            return []

        restored = self.remove(name)
        record.enabled = False
        record.backups = []
        remaining = self._load_state()
        remaining.append(record)
        self._save_state(remaining)
        return restored


# Build a minimal FORGE TOC reader that the installer can use for future
# update-safe lookups. Kept small to avoid coupling to the full graph scanner.
def find_forge_toc(path: Path, magic: bytes = FORGE_MAGIC, max_sweep: int = 200) -> list[int]:
    """Best-effort locate of the TOC by scanning for the forge magic.

    Not required for the in-place patch path, but useful for a future
    injector-driven backend.
    """
    candidates = []
    with path.open("rb") as handle:
        cursor = 0
        chunk = handle.read(1 << 20)
        while chunk and len(candidates) < max_sweep:
            start = 0
            while True:
                pos = chunk.find(magic, start)
                if pos < 0:
                    break
                candidates.append(cursor + pos)
                start = pos + 1
            cursor += len(chunk)
            chunk = handle.read(1 << 20)
    return candidates
