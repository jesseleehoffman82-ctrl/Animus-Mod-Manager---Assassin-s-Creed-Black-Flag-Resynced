"""Install a Jackdaw design as an isolated Script Hook cosmetic slot.

No FORGE archive or stock resource is edited. The native hook must provide a
verified runtime resource redirect before an installed slot affects the game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


FORMAT = "jackdaw-custom-cosmetic-v1"
GAME_EXES = ("ACBlackFlag.exe", "ACBlackFlag_Plus.exe")
GAME_PROCESS_NAMES = {"acblackflag.exe", "acblackflag_plus.exe"}
SUPPORTED_EXECUTABLES = {
    "ACBlackFlag.exe": {
        "bytes": 478_845_280,
        "sha256": "8d52238155c9491f329c0b78af2d00ee67ab5e03946eea83e12b061b64b23140",
    },
}
APPROVED_HOOKS = {
    # Launch-tested production hook. It stages isolated slots but deliberately
    # does not expose unverified native inventory insertion.
    "e1b10d1e6228c8c8419d5c2ec11eeee9a6fc5d3d02a8dde86e976ea8ed9c86ed": {
        "bytes": 3_397_471,
        "capability": "isolated-slot-staging-v1",
        "visible_slot_insertion": False,
        "runtime_redirect_verified": False,
    },
}
COSMETIC_NATIVE_CONTRACT = {
    "sails": {
        "template_resource_id": "0x000002317C9DE7C3",
        "synthetic_resource_id": "0x00007F4A44530001",
    },
    "hull": {
        "template_resource_id": "0x000002317C9DDAD3",
        "synthetic_resource_id": "0x00007F4A44530002",
    },
    "figurehead": {
        "template_resource_id": "0x000002317C9DD721",
        "synthetic_resource_id": "0x00007F4A44530003",
    },
    "crew": {
        "template_resource_id": "0x000002317C9DEF04",
        "synthetic_resource_id": "0x00007F4A44530004",
    },
}
CUSTOM_SLOT_PRESENTATION = {
    "accent_name": "violet",
    "accent_hex": "#8B5CF6",
    "inherit_native_focus_animation": True,
    "inherit_native_selection_animation": True,
    "action_label": "Equip",
}
SCOPE_CATEGORIES = {
    "Whole ship": ("sails", "hull", "figurehead", "crew"),
    "Sails": ("sails",),
    "Hull": ("hull",),
    "Figurehead": ("figurehead",),
    "Crew": ("crew",),
    # Black Flag has no independent cannon/body-detail cosmetic menu. These
    # materials therefore travel with the custom Hull appearance entry.
    "Cannons": ("hull",),
    "Mortar": ("hull",),
    "Selected parts": ("hull",),
}


class InjectError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_game_dir(game_dir: Path) -> dict:
    if not game_dir.is_dir() or not (game_dir / "DataPC_boot.forge").is_file():
        raise InjectError("The selected folder is not a recognized Black Flag Resynced installation")
    exe = next((game_dir / name for name in GAME_EXES if (game_dir / name).is_file()), None)
    if exe is None:
        raise InjectError("No supported Black Flag executable was found")
    expected = SUPPORTED_EXECUTABLES.get(exe.name)
    actual_size = exe.stat().st_size
    if expected is None or actual_size != expected["bytes"]:
        raise InjectError(
            f"Unsupported game build: {exe.name} is {actual_size} bytes. "
            "Custom cosmetic insertion is locked to the verified Resynced executable"
        )
    actual_hash = sha256_file(exe)
    if actual_hash != expected["sha256"]:
        raise InjectError(
            f"Unsupported game build: {exe.name} SHA-256 is {actual_hash}. "
            "No hook or cosmetic slot was installed"
        )
    return {
        "exe_name": exe.name,
        "exe_bytes": actual_size,
        "exe_sha256": actual_hash,
        "build_guard_verified": True,
        "asi_loader_present": (game_dir / "version.dll").is_file(),
    }


def is_game_running() -> bool:
    if os.name != "nt":
        return False
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False)
    text = result.stdout.lower()
    return any(f'"{name}"' in text for name in GAME_PROCESS_NAMES)


def safe_slot_id(value: str) -> str:
    slot = re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower()).strip("-.")
    if not slot:
        raise InjectError("The custom cosmetic slot id is empty")
    return slot[:80]


def read_package(package_dir: Path) -> tuple[dict, list[Path]]:
    patch_path = package_dir / "patch.json"
    if not patch_path.is_file():
        raise InjectError("patch.json is missing; click Apply Jackdaw Design first")
    patch = json.loads(patch_path.read_text(encoding="utf-8-sig"))
    if patch.get("shared_textures_overwritten") is not False:
        raise InjectError("Refusing package: shared_textures_overwritten must be false")
    pngs = sorted(package_dir.glob("*.png"))
    if not pngs:
        raise InjectError("The prepared package contains no PNG textures")
    return patch, pngs


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def validate_hook_binary(path: Path) -> dict:
    if not path.is_file():
        raise InjectError("The selected Script Hook binary is missing")
    digest = sha256_file(path)
    approved = APPROVED_HOOKS.get(digest)
    if approved is None or path.stat().st_size != approved["bytes"]:
        raise InjectError(
            f"Unapproved Script Hook binary ({digest}). The Studio refused to install experimental runtime code"
        )
    return {"sha256": digest, **approved}


def install(package_dir: Path, game_dir: Path, slot_value: str, hook_binary: Path | None) -> dict:
    if is_game_running():
        raise InjectError("Black Flag is running. Close it before injecting a cosmetic slot")
    game = validate_game_dir(game_dir)
    patch, pngs = read_package(package_dir)
    hook_capability = validate_hook_binary(hook_binary) if hook_binary else None
    scope = str(patch.get("target_scope") or "Whole ship")
    if scope not in SCOPE_CATEGORIES:
        raise InjectError(f"Unsupported cosmetic scope: {scope}")
    base_slot_id = safe_slot_id(slot_value)
    hook_root = game_dir / "resynced_hook"
    slots_root = hook_root / "custom_cosmetics"
    transaction_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    staging_root = slots_root / ".staging" / transaction_id
    transaction_backup_root = hook_root / "backups" / "custom_cosmetics" / transaction_id
    active_path = slots_root / "active.json"
    previous_active = active_path.read_bytes() if active_path.is_file() else None
    active_backup = transaction_backup_root / "active.json"
    validation_path = slots_root / "runtime-validation.json"
    previous_validation = validation_path.read_bytes() if validation_path.is_file() else None
    validation_backup = transaction_backup_root / "runtime-validation.json"
    installed_slots: dict[str, str] = {}
    backup_paths: list[str] = []
    destinations: list[Path] = []
    hook_destination = game_dir / "scripts" / "ResyncedScriptHook.asi"
    hook_backup: Path | None = None
    committed: list[Path] = []
    moved_previous: list[tuple[Path, Path]] = []
    hook_changed = False
    try:
        # Build every slot outside its live destination first. Nothing visible
        # to the hook changes until every texture and manifest is complete.
        for category in SCOPE_CATEGORIES[scope]:
            slot_id = safe_slot_id(f"{base_slot_id}-{category}")
            staged = staging_root / slot_id
            (staged / "textures").mkdir(parents=True, exist_ok=False)
            for source in pngs:
                shutil.copy2(source, staged / "textures" / source.name)
            manifest = {
                "format": FORMAT,
                "slot_id": slot_id,
                "display_name": f"Custom {category.title()}",
                "category": category,
                "target_scope": scope,
                "install_strategy": "runtime-loose-override",
                "stock_resources_overwritten": False,
                "forge_archives_modified": False,
                "native_contract": COSMETIC_NATIVE_CONTRACT[category],
                "presentation": CUSTOM_SLOT_PRESENTATION,
                "texture_routing": {
                    "mode": "isolated-runtime-loose-override",
                    "category": category,
                    "stock_resource_fallback": COSMETIC_NATIVE_CONTRACT[category]["template_resource_id"],
                },
                "textures": [
                    {"file": f"textures/{p.name}", "sha256": sha256_file(p), "bytes": p.stat().st_size}
                    for p in pngs
                ],
                "created_at_unix": int(time.time()),
            }
            atomic_json(staged / "manifest.json", manifest)
            installed_slots[category] = slot_id

        transaction_backup_root.mkdir(parents=True, exist_ok=True)
        if previous_active is not None:
            active_backup.write_bytes(previous_active)
        if previous_validation is not None:
            validation_backup.write_bytes(previous_validation)
        for category, slot_id in installed_slots.items():
            destination = slots_root / slot_id
            if destination.exists():
                backup = transaction_backup_root / slot_id
                shutil.move(str(destination), str(backup))
                moved_previous.append((destination, backup))
                backup_paths.append(str(backup))
            shutil.move(str(staging_root / slot_id), str(destination))
            destinations.append(destination)
            committed.append(destination)

        selection = {
            "format": "jackdaw-custom-cosmetic-selection-v2",
            "active_slots": installed_slots,
            "updated_at_unix": int(time.time()),
        }
        for category, slot_id in installed_slots.items():
            selection[f"active_{category}"] = slot_id
        atomic_json(active_path, {
            **selection,
            # Plugin API v2 compatibility; v3 reads the category-specific keys.
            "active_slot": next(iter(installed_slots.values())),
            "category": next(iter(installed_slots.keys())),
        })
        atomic_json(validation_path, {
            "format": "jackdaw-cosmetic-runtime-validation-v1",
            "status": "staged",
            "detail": "installed package has not been validated in a running game session",
            "transaction_id": transaction_id,
            "exe_sha256": game["exe_sha256"],
            "registered_count": 0,
            "stock_resources_overwritten": False,
            "forge_archives_modified": False,
            "runtime_texture_redirect_verified": False,
        })

        if hook_binary and hook_binary.is_file():
            hook_backup_root = hook_root / "backups" / "hooks" / transaction_id
            if hook_destination.is_file():
                hook_backup = hook_backup_root / hook_destination.name
                hook_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(hook_destination, hook_backup)
            atomic_copy(hook_binary, hook_destination)
            hook_changed = True

        state = {
            "format": "jackdaw-custom-cosmetic-install-v1",
            "transaction_id": transaction_id,
            "slot_id": base_slot_id,
            "slots": installed_slots,
            "slot_paths": [str(path) for path in destinations],
            "backup_paths": backup_paths,
            "active_selection_had_backup": previous_active is not None,
            "active_selection_backup": str(active_backup) if previous_active is not None else None,
            "runtime_validation_backup": str(validation_backup) if previous_validation is not None else None,
            "hook_backup": str(hook_backup) if hook_backup else None,
            "hook_previously_present": hook_backup is not None,
            "hook_changed": hook_changed,
            "stock_resources_overwritten": False,
            "forge_archives_modified": False,
            "asi_loader_present": game["asi_loader_present"],
            "hook_binary_installed": hook_destination.is_file(),
            "hook_sha256": hook_capability["sha256"] if hook_capability else None,
            "hook_capability": hook_capability["capability"] if hook_capability else None,
            "visible_slot_insertion_enabled": bool(hook_capability and hook_capability["visible_slot_insertion"]),
            "runtime_redirect_verified": bool(hook_capability and hook_capability["runtime_redirect_verified"]),
            "build_guard_verified": game["build_guard_verified"],
            "game_exe_name": game["exe_name"],
            "game_exe_bytes": game["exe_bytes"],
            "game_exe_sha256": game["exe_sha256"],
            "installed_at_unix": int(time.time()),
        }
        for destination in destinations:
            atomic_json(destination / "install-state.json", state)
        transaction_state = hook_root / "install-state" / f"{transaction_id}.json"
        atomic_json(transaction_state, state)
        atomic_json(hook_root / "install-state" / "latest.json", state)
        return state
    except Exception:
        # Restore the complete pre-injection state. This covers failures while
        # committing slots, updating active.json, replacing the hook, or
        # writing validation state.
        for destination in reversed(committed):
            if destination.exists():
                shutil.rmtree(destination)
        for destination, backup in reversed(moved_previous):
            if backup.exists():
                shutil.move(str(backup), str(destination))
        if previous_active is None:
            active_path.unlink(missing_ok=True)
        else:
            active_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = active_path.with_suffix(active_path.suffix + ".rollback")
            temporary.write_bytes(previous_active)
            os.replace(temporary, active_path)
        if previous_validation is None:
            validation_path.unlink(missing_ok=True)
        else:
            validation_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = validation_path.with_suffix(validation_path.suffix + ".rollback")
            temporary.write_bytes(previous_validation)
            os.replace(temporary, validation_path)
        if hook_changed:
            if hook_backup and hook_backup.is_file():
                atomic_copy(hook_backup, hook_destination)
            else:
                hook_destination.unlink(missing_ok=True)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


def rollback_latest(game_dir: Path) -> dict:
    if is_game_running():
        raise InjectError("Black Flag is running. Close it before rolling back a cosmetic slot")
    game = validate_game_dir(game_dir)
    hook_root = game_dir / "resynced_hook"
    latest_path = hook_root / "install-state" / "latest.json"
    if not latest_path.is_file():
        raise InjectError("No Jackdaw Workshop injection transaction is available to roll back")
    state = json.loads(latest_path.read_text(encoding="utf-8-sig"))
    if state.get("format") != "jackdaw-custom-cosmetic-install-v1":
        raise InjectError("The latest injection state has an unsupported format")
    if state.get("game_exe_sha256") != game["exe_sha256"]:
        raise InjectError("Rollback state belongs to a different Black Flag executable build")
    if state.get("forge_archives_modified") is not False or state.get("stock_resources_overwritten") is not False:
        raise InjectError("Unsafe rollback state rejected")

    slots_root = hook_root / "custom_cosmetics"
    active_path = slots_root / "active.json"
    validation_path = slots_root / "runtime-validation.json"
    hook_destination = game_dir / "scripts" / "ResyncedScriptHook.asi"
    removed_slots: list[str] = []
    restored_slots: list[str] = []
    slot_paths = [Path(raw) for raw in state.get("slot_paths") or []]
    backup_paths = [Path(raw) for raw in state.get("backup_paths") or []]
    backup_root = hook_root / "backups" / "custom_cosmetics"
    hook_backup_root = hook_root / "backups" / "hooks"
    active_backup = Path(state["active_selection_backup"]) if state.get("active_selection_backup") else None
    validation_backup = Path(state["runtime_validation_backup"]) if state.get("runtime_validation_backup") else None
    hook_backup = Path(state["hook_backup"]) if state.get("hook_backup") else None

    # Complete preflight before moving or deleting anything.
    for destination in slot_paths:
        try:
            destination.relative_to(slots_root)
        except ValueError as exc:
            raise InjectError(f"Rollback slot path escapes the custom cosmetic root: {destination}") from exc
    for backup in backup_paths:
        try:
            backup.relative_to(backup_root)
        except ValueError as exc:
            raise InjectError(f"Rollback backup path is outside the Jackdaw backup root: {backup}") from exc
        if not backup.is_dir():
            raise InjectError(f"Previous slot backup is missing: {backup}")
    if active_backup:
        try:
            active_backup.relative_to(backup_root)
        except ValueError as exc:
            raise InjectError("Active-selection backup path is outside the Jackdaw backup root") from exc
        if not active_backup.is_file():
            raise InjectError("The previous active-selection backup is missing")
    if validation_backup:
        try:
            validation_backup.relative_to(backup_root)
        except ValueError as exc:
            raise InjectError("Runtime-validation backup path is outside the Jackdaw backup root") from exc
        if not validation_backup.is_file():
            raise InjectError("The previous runtime-validation backup is missing")
    if state.get("hook_changed") and hook_backup:
        try:
            hook_backup.relative_to(hook_backup_root)
        except ValueError as exc:
            raise InjectError("Hook backup path is outside the Jackdaw backup root") from exc
        if not hook_backup.is_file():
            raise InjectError("The previous Script Hook backup is missing")

    transaction_id = str(state.get("transaction_id") or "unknown")
    quarantine = hook_root / "backups" / "rollbacks" / transaction_id
    moved_current: list[tuple[Path, Path]] = []
    moved_backups: list[tuple[Path, Path]] = []
    active_before = active_path.read_bytes() if active_path.is_file() else None
    validation_before = validation_path.read_bytes() if validation_path.is_file() else None
    hook_before = hook_destination.read_bytes() if hook_destination.is_file() else None
    try:
        for destination in slot_paths:
            if destination.is_dir():
                quarantined = quarantine / "replaced" / destination.name
                quarantined.parent.mkdir(parents=True, exist_ok=True)
                if quarantined.exists():
                    raise InjectError(f"Rollback quarantine already exists: {quarantined}")
                shutil.move(str(destination), str(quarantined))
                moved_current.append((destination, quarantined))
                removed_slots.append(str(destination))

        for backup in backup_paths:
            destination = slots_root / backup.name
            if destination.exists():
                raise InjectError(f"Cannot restore previous slot because its destination exists: {destination}")
            shutil.move(str(backup), str(destination))
            moved_backups.append((backup, destination))
            restored_slots.append(str(destination))

        if active_backup:
            temporary = active_path.with_suffix(".json.rollback")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(active_backup, temporary)
            os.replace(temporary, active_path)
        else:
            active_path.unlink(missing_ok=True)

        if validation_backup:
            temporary = validation_path.with_suffix(".json.rollback")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(validation_backup, temporary)
            os.replace(temporary, validation_path)
        else:
            validation_path.unlink(missing_ok=True)

        if state.get("hook_changed"):
            if hook_backup:
                atomic_copy(hook_backup, hook_destination)
            elif not state.get("hook_previously_present"):
                hook_destination.unlink(missing_ok=True)
    except Exception:
        for backup, destination in reversed(moved_backups):
            if destination.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(backup))
        for destination, quarantined in reversed(moved_current):
            if quarantined.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(quarantined), str(destination))
        if active_before is None:
            active_path.unlink(missing_ok=True)
        else:
            active_path.parent.mkdir(parents=True, exist_ok=True)
            active_path.write_bytes(active_before)
        if validation_before is None:
            validation_path.unlink(missing_ok=True)
        else:
            validation_path.parent.mkdir(parents=True, exist_ok=True)
            validation_path.write_bytes(validation_before)
        if hook_before is None:
            hook_destination.unlink(missing_ok=True)
        else:
            hook_destination.parent.mkdir(parents=True, exist_ok=True)
            hook_destination.write_bytes(hook_before)
        raise

    rollback_state = {
        "format": "jackdaw-custom-cosmetic-rollback-v1",
        "rolled_back_transaction_id": state.get("transaction_id"),
        "removed_slots": removed_slots,
        "restored_slots": restored_slots,
        "stock_resources_overwritten": False,
        "forge_archives_modified": False,
        "build_guard_verified": True,
        "game_exe_sha256": game["exe_sha256"],
        "rolled_back_at_unix": int(time.time()),
    }
    atomic_json(hook_root / "install-state" / f"rollback-{transaction_id}.json", rollback_state)
    latest_path.unlink(missing_ok=True)
    return rollback_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Install an isolated Jackdaw custom cosmetic slot")
    parser.add_argument("--package-dir")
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--slot-id")
    parser.add_argument("--hook-binary")
    parser.add_argument("--rollback-latest", action="store_true")
    args = parser.parse_args()
    try:
        if args.rollback_latest:
            result = rollback_latest(Path(args.game_dir).resolve())
        else:
            if not args.package_dir or not args.slot_id:
                raise InjectError("--package-dir and --slot-id are required for installation")
            result = install(
                Path(args.package_dir).resolve(), Path(args.game_dir).resolve(), args.slot_id,
                Path(args.hook_binary).resolve() if args.hook_binary else None,
            )
        print(json.dumps(result))
        return 0
    except (InjectError, OSError, shutil.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
