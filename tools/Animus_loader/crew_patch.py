"""Fixed-target crew material packages; never guess or merge FORGE destinations."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import tempfile
import zipfile

from .core import LoaderError

PATCH_FILE = "DataPC_boot_patch_02.forge"
MAX_PACKAGE = 64 * 1024 * 1024


def metadata(package):
    value = package.manifest.get("crew_patch")
    if value is None:
        return None
    if not isinstance(value, dict) or not re.fullmatch(r"[a-z0-9-]{1,80}", str(value.get("target_id", ""))):
        raise LoaderError("Invalid crew material target metadata.")
    if not isinstance(value.get("target_name"), str) or not value["target_name"].strip():
        raise LoaderError("Crew material package must name its fixed vanilla target.")
    if len(package.targets) != 1:
        raise LoaderError("Crew material packages must contain exactly one patch archive.")
    target = package.targets[0]
    if target.mode != "loose-file" or target.dest != PATCH_FILE or not target.replacement.startswith(b"scimitar"):
        raise LoaderError("Crew material packages may only deploy a valid boot patch FORGE.")
    checks = value.get("source_resources")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 256:
        raise LoaderError("Crew material package lacks source-resource compatibility checks.")
    for check in checks:
        if (not isinstance(check, dict) or check.get("archive") != "DataPC_boot.forge"
                or not re.fullmatch(r"[0-9a-fA-F]{1,16}", str(check.get("id", "")))
                or not re.fullmatch(r"[0-9a-fA-F]{64}", str(check.get("raw_sha256", "")))):
            raise LoaderError("Invalid crew material source-resource check.")
    return value


@contextmanager
def package_source(source, _depth=0):
    """Inspect native packages or one wrapped .jmod without importing anything.

    Texture-only archives return None. Nested packages are bounded and written
    under our own temporary filename, never an archive-supplied filesystem path.
    """
    source = Path(source)
    if source.suffix.lower() not in {".zip", ".jmod"}:
        yield None
        return
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise LoaderError("The selected archive is not a valid ZIP/JMOD.") from exc
    with archive:
        names = archive.namelist()
        if "manifest.json" in names:
            info = archive.getinfo("manifest.json")
            if info.file_size > 1024 * 1024:
                raise LoaderError("Package manifest is too large.")
            manifest = json.loads(archive.read(info))
            if manifest.get("crew_patch") is not None:
                if sum(e.file_size for e in archive.infolist()) > MAX_PACKAGE:
                    raise LoaderError("Crew material package exceeds the 64 MB limit.")
                yield source
            else:
                yield None
            return
        nested = [e for e in archive.infolist() if e.filename.lower().endswith(".jmod")]
        if not nested:
            yield None
            return
        if _depth or len(nested) != 1 or nested[0].file_size > MAX_PACKAGE:
            raise LoaderError("Select an archive containing exactly one crew .jmod (up to 64 MB).")
        with tempfile.TemporaryDirectory(prefix="animus_crew_") as folder:
            path = Path(folder) / "crew.jmod"
            path.write_bytes(archive.read(nested[0]))
            with package_source(path, _depth=1) as inner:
                if inner is None:
                    raise LoaderError("This .jmod has no Crew material metadata. Use its updated Crew package.")
                yield inner


def preflight(loader, package):
    """No writes: validate source build, ownership, and conflicts before apply."""
    meta = metadata(package)
    installed = loader.list_installed()
    destinations = {str(t.dest or t.forge).casefold() for t in package.targets}
    # Protect active crew patch archives even when another package is installed
    # through the Mods tab. Two complete FORGEs cannot be merged by copy order.
    for record in installed:
        if not record.enabled or record.name == package.name:
            continue
        for entry in record.backups:
            if str(entry.get("dest", "")).casefold() in destinations and (
                    meta is not None or entry.get("crew_material_patch")):
                raise LoaderError(f"'{record.name}' already uses this patch archive. Disable it first; crew material archives cannot be merged.")
    if meta is None:
        return
    path = loader._safe_game_path(PATCH_FILE)
    owner = next((r for r in installed if r.name == package.name and r.enabled), None)
    if path.exists():
        entries = owner.backups if owner else []
        expected = next((e.get("installed_sha256") for e in entries if e.get("dest") == PATCH_FILE), None)
        if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise LoaderError(f"{PATCH_FILE} already exists or was changed outside the manager. It was not overwritten. Remove/restore its existing mod first.")
    validate_source_resources(loader, package)


def validate_source_resources(loader, package):
    """Validate a fixed crew patch against stock resources without ownership checks.

    Release builders use this read-only half of preflight even when an older
    test package is currently installed. Runtime installation still calls the
    full preflight above and therefore keeps its destination/conflict guards.
    """
    meta = metadata(package)
    if meta is None:
        return
    from .forge import ForgeArchive
    archive = ForgeArchive(loader.game_dir / "DataPC_boot.forge", None)
    for check in meta["source_resources"]:
        actual = hashlib.sha256(archive.read_raw(int(check["id"], 16))).hexdigest()
        if actual != check["raw_sha256"].lower():
            raise LoaderError(f"Crew patch is incompatible with the current game resources (0x{check['id']}). Nothing was installed.")


def rows(loader):
    installed = {r.name: r for r in loader.list_installed()}
    result = []
    for path in loader.discover_packages():
        try:
            package = loader.read_package(path)
            meta = metadata(package)
        except (LoaderError, ValueError):
            continue
        if meta is None:
            continue
        record = installed.get(package.name)
        result.append(dict(id=package.name, name=package.name, version=package.version,
                           author=package.author, description=package.manifest.get("description", ""),
                           replaces=[meta["target_name"]], slots=1,
                           managed_type="crew-material", enabled=bool(record and record.enabled),
                           target_id=meta["target_id"], path=str(path), shared_with=[]))
    for row in result:
        row["shared_with"] = [dict(id=r["id"], name=r["name"], enabled=r["enabled"])
                              for r in result if r is not row and r["target_id"] == row["target_id"]]
    return result
