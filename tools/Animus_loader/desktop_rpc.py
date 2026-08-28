"""One-shot JSON RPC adapter for the native Animus Mod Manager shell.

Each request is read from stdin and each response is written to stdout.  The
desktop host starts a fresh Python process per operation, so Python can never
own or block the native UI message loop.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .core import DEFAULT_GAME_DIR, Loader, LoaderError
from .nexus import NexusClient, find_api_key, mod_page_url, save_api_key
from .packs import CATEGORY_CREW, CATEGORY_OUTFIT, CATEGORY_WEAPON, PackError, PackManager

ROOT = Path(__file__).resolve().parents[2]
MODS_ROOT = ROOT / "mods"
SETTINGS_PATH = MODS_ROOT / "settings.json"


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


class DesktopRpc:
    def __init__(self) -> None:
        settings = _load_settings()
        self.game_dir = Path(settings.get("game_dir") or DEFAULT_GAME_DIR)
        self.loader = Loader(game_dir=self.game_dir)
        self.manager = PackManager(self.game_dir, self.loader.mods_root)
        self.logs: list[dict] = []
        try:
            compatibility = self.loader.ensure_proxy_compatibility()
            if compatibility.get("message"):
                self.log(
                    str(compatibility["message"]),
                    "ok" if compatibility.get("changed") else "warn",
                )
        except (LoaderError, OSError) as exc:
            self.log(f"DLL compatibility check: {exc}", "warn")

    def log(self, message: str, tag: str = "info") -> None:
        self.logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "tag": tag,
            "message": message,
        })

    def _find_package(self, name: str) -> Path | None:
        for path in self.loader.discover_packages():
            try:
                if self.loader.read_package(path).name == name:
                    return path
            except LoaderError:
                continue
        return None

    @staticmethod
    def _nexus_info(metadata: dict) -> dict | None:
        nexus = metadata.get("nexus") if isinstance(metadata, dict) else None
        if not isinstance(nexus, dict) or not nexus.get("mod_id"):
            return None
        mod_id = int(nexus["mod_id"])
        return {
            "game_id": int(nexus.get("game_id", 2996)),
            "mod_id": mod_id,
            "url": mod_page_url(mod_id),
        }

    def list_mods(self) -> list[dict]:
        installed = {record.name: record for record in self.loader.list_installed()}
        result = []
        for path in self.loader.discover_packages():
            try:
                package = self.loader.read_package(path)
            except LoaderError as exc:
                result.append({
                    "name": path.stem, "version": "-", "author": "-",
                    "targets": 0, "enabled": False, "invalid": True,
                    "error": str(exc), "path": str(path),
                })
                continue
            record = installed.get(package.name)
            compatibility = [
                str(entry["compatibility"])
                for entry in (record.backups if record else [])
                if entry.get("compatibility")
            ]
            result.append({
                "id": package.name,
                "name": package.name,
                "version": package.version,
                "author": package.author,
                "description": package.manifest.get("description", ""),
                "nexus": self._nexus_info(package.manifest),
                "targets": len(package.targets),
                "enabled": bool(record and record.enabled),
                "dll_compatibility": compatibility[-1] if compatibility else None,
                "invalid": False,
                "category": package.category,
                "path": str(path),
            })
        return result

    def list_packs(self, category: str) -> list[dict]:
        staged = set(self.manager._staged(category))
        packs = self.manager.list_packs(category=category)
        result = []
        for pack in packs:
            meta = self.manager._pack_meta(pack)
            replaces = meta.get("replaces") or []
            if isinstance(replaces, str):
                replaces = [replaces]
            result.append({
                "id": pack.id,
                "name": pack.name,
                "version": meta.get("version", ""),
                "author": meta.get("author", ""),
                "description": meta.get("description", ""),
                "replaces": replaces,
                "slots": len(pack.slots),
                "enabled": pack.id in staged,
                "shared_with": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "enabled": bool(item.get("enabled")),
                    }
                    for item in self.manager.sharing_packs(pack)
                ],
                "nexus": self._nexus_info(meta),
            })
        return result

    def state(self) -> dict:
        return {
            "game_dir": str(self.game_dir),
            "game_found": (self.game_dir / "ACBlackFlag.exe").is_file(),
            "mods": self.list_mods(),
            "outfits": self.list_packs(CATEGORY_OUTFIT),
            "weapons": self.list_packs(CATEGORY_WEAPON),
            "crew": self.list_packs(CATEGORY_CREW),
            "proxy_status": self.loader.proxy_status(),
            "nexus_key_set": bool(find_api_key(self.loader.mods_root)),
        }

    def dispatch(self, method: str, args: list) -> tuple[object, dict | None]:
        if method in {"get_state", "refresh"}:
            if method == "refresh":
                self.log("Refreshed.")
            state = self.state()
            return state, None

        if method in {"set_game_dir", "detect_game_dir"}:
            game_dir = Path(args[0]) if method == "set_game_dir" else DEFAULT_GAME_DIR
            settings = _load_settings()
            settings["game_dir"] = str(game_dir)
            _save_settings(settings)
            self.game_dir = game_dir
            self.loader = Loader(game_dir=game_dir)
            self.manager = PackManager(game_dir, self.loader.mods_root)
            compatibility = self.loader.ensure_proxy_compatibility()
            if compatibility.get("message"):
                self.log(
                    str(compatibility["message"]),
                    "ok" if compatibility.get("changed") else "warn",
                )
            self.log(f"Game folder set to {game_dir}", "ok")
            state = self.state()
            return state, None

        if method == "get_mod_details":
            path = self._find_package(str(args[0]))
            if not path:
                return {"ok": False, "error": "Package not found"}, None
            package = self.loader.read_package(path)
            record = next((item for item in self.loader.list_installed() if item.name == package.name), None)
            compatibility = [
                str(entry["compatibility"])
                for entry in (record.backups if record else [])
                if entry.get("compatibility")
            ]
            return {
                "ok": True, "name": package.name, "version": package.version,
                "author": package.author, "category": package.category,
                "description": package.manifest.get("description", ""),
                "nexus": self._nexus_info(package.manifest),
                "path": str(path),
                "dll_compatibility": compatibility[-1] if compatibility else None,
                "targets": [{
                    "forge": target.forge,
                    "resource_id": f"0x{target.resource_id:016X}",
                    "mode": target.mode,
                    "occurrence": target.occurrence,
                } for target in package.targets],
            }, None

        if method == "get_pack_details":
            pack = self.manager.get_pack(str(args[0]))
            if pack is None:
                return {"ok": False, "error": "Texture pack not found"}, None
            meta = self.manager._pack_meta(pack)
            replaces = meta.get("replaces") or []
            if isinstance(replaces, str):
                replaces = [replaces]
            return {
                "ok": True,
                "id": pack.id,
                "name": pack.name,
                "category": pack.category,
                "version": meta.get("version", ""),
                "author": meta.get("author", ""),
                "description": meta.get("description", ""),
                "replaces": replaces,
                "slots": len(pack.slots),
                "nexus": self._nexus_info(meta),
                "path": str(pack.dir),
                "targets": [{
                    "forge": "DataPC_boot.forge",
                    "resource_id": f"0x{slot.mat:016X}",
                    "mode": f"texture-slot-{slot.slot}",
                } for slot in pack.slots],
            }, None

        if method == "install_mod_path":
            source = Path(args[0])
            target, package, converted = self.loader.import_package(source)
            backups = self.loader.apply(target, priority=0)
            if converted:
                self.log(
                    f"Imported ordinary Nexus archive as a managed loose-file mod ({len(package.targets)} file(s)).",
                    "info",
                )
            self.log(
                f"Installed '{package.name} v{package.version}' — {len(backups)} target(s) patched",
                "ok",
            )
            return {
                "ok": True,
                "name": package.name,
                "enabled": True,
                "converted": converted,
            }, self.state()

        if method == "toggle_mod":
            name = str(args[0])
            installed = {record.name: record for record in self.loader.list_installed()}
            if name in installed and installed[name].enabled:
                restored = self.loader.disable(name)
                self.log(f"Disabled '{name}'; restored {len(restored)} file(s)", "ok")
            else:
                path = self._find_package(name)
                if not path:
                    raise LoaderError(f"Could not find package for '{name}'")
                package = self.loader.read_package(path)
                backups = self.loader.apply(path, priority=0)
                self.log(f"Enabled '{package.name}' — {len(backups)} target(s) patched", "ok")
            return {"ok": True}, self.state()

        if method in {"uninstall_mod", "remove_mod_files"}:
            name = str(args[0])
            restored = self.loader.remove(name)
            path = self._find_package(name)
            if path and path.is_file():
                path.unlink()
            self.log(f"Removed '{name}'; restored {len(restored)} file(s)", "ok")
            return {"ok": True}, self.state()

        if method == "update_mod_path":
            old_name, source = str(args[0]), Path(args[1])
            old_path = self._find_package(old_name)
            target, package, converted = self.loader.import_package(source)
            restored = self.loader.remove(old_name)
            if old_path and old_path.is_file() and old_path.resolve() != target.resolve():
                old_path.unlink()
            backups = self.loader.apply(target, priority=0)
            self.log(
                f"Updated '{old_name}' with '{package.name} v{package.version}' — "
                f"restored {len(restored)} old and patched {len(backups)} target(s).",
                "ok",
            )
            return {"ok": True, "name": package.name, "converted": converted}, self.state()

        if method == "open_mod_folder":
            path = self._find_package(str(args[0]))
            target = path if path else self.loader.packages_dir
            if os.name == "nt":
                if target.is_file():
                    subprocess.Popen(["explorer", "/select,", str(target)])
                else:
                    os.startfile(str(target))  # type: ignore[attr-defined]
            return {"ok": True}, None

        if method == "set_nexus_link":
            item_type, item_id, mod_id = str(args[0]), str(args[1]), int(args[2])
            if item_type == "mod":
                self.loader.set_nexus(item_id, mod_id)
            elif item_type in {CATEGORY_OUTFIT, CATEGORY_WEAPON, CATEGORY_CREW}:
                self.manager.set_nexus(item_id, mod_id)
            else:
                raise ValueError(f"Unsupported Nexus item type: {item_type}")
            self.log(f"Linked '{item_id}' to Nexus mod {mod_id}.", "ok")
            return self.state(), None

        if method == "rename_item":
            item_type, item_id, new_name = map(str, args[:3])
            if item_type == "mod":
                self.loader.rename(item_id, new_name)
            elif item_type in {CATEGORY_OUTFIT, CATEGORY_WEAPON, CATEGORY_CREW}:
                self.manager.rename_pack(item_id, new_name)
            else:
                raise ValueError(f"Unsupported item type: {item_type}")
            self.log(f"Renamed '{item_id}' to '{new_name.strip()}'.", "ok")
            return {"ok": True, "name": new_name.strip()}, self.state()

        if method == "launch_game":
            executable = self.game_dir / "ACBlackFlag.exe"
            if not executable.is_file():
                raise LoaderError(f"Game executable not found: {executable}")
            subprocess.Popen(
                [str(executable)],
                cwd=str(self.game_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self.log("Launching Assassin's Creed Black Flag Resynced.", "ok")
            return {"ok": True}, None

        if method == "install_pack_path":
            category, path = str(args[0]), Path(args[1])
            pack = self.manager.import_pack(path, category=category)
            conflicts = self.manager.enabled_conflicts(pack)
            if conflicts:
                self.log(
                    f"'{pack.name}' shares texture slots with {len(conflicts)} enabled pack(s); waiting for confirmation.",
                    "warn",
                )
                return {
                    "ok": False,
                    "requires_confirmation": True,
                    "pending_action": "install",
                    "pack_id": pack.id,
                    "pack_name": pack.name,
                    "category": category,
                    "conflicts": conflicts,
                }, None
            result = self.manager.activate_imported(pack.id)
            self.log(f"Installed '{pack.name}' ({len(pack.slots)} slot(s)). Enabled + applied.", "ok")
            return {"ok": True}, self.state()

        if method == "resolve_pack_install":
            category, pack_id = str(args[0]), str(args[1])
            pack = self.manager.get_pack(pack_id)
            if pack is None or pack.category != category:
                raise PackError("The outfit pack awaiting confirmation could not be found.")
            result = self.manager.activate_imported(pack_id, disable_conflicts=True)
            disabled = result.get("disabled", [])
            disabled_names = ", ".join(item["name"] for item in disabled)
            if disabled_names:
                self.log(f"Disabled conflicting pack(s): {disabled_names}.", "warn")
            self.log(f"Installed '{pack.name}' and made it active.", "ok")
            return self.state(), None

        if method == "resolve_pack_conflict":
            category, pack_id = str(args[0]), str(args[1])
            action = str(args[2]) if len(args) > 2 else "enable"
            pack = self.manager.get_pack(pack_id)
            if pack is None or pack.category != category:
                raise PackError("The outfit awaiting confirmation could not be found.")
            result = self.manager.activate_imported(pack_id, disable_conflicts=True)
            disabled = result.get("disabled", [])
            disabled_names = ", ".join(item["name"] for item in disabled)
            if disabled_names:
                self.log(f"Disabled conflicting pack(s): {disabled_names}.", "warn")
            verb = "Installed" if action == "install" else "Enabled"
            self.log(f"{verb} '{pack.name}' and made it active.", "ok")
            return self.state(), None

        if method == "cancel_pack_install":
            pack_id = str(args[0])
            pack = self.manager.discard_imported(pack_id)
            self.log(f"Cancelled installation of '{pack.name}'; existing outfits were left unchanged.", "info")
            return self.state(), None

        if method == "cancel_pack_enable":
            pack = self.manager.get_pack(str(args[0]))
            self.log(
                f"Kept '{pack.name if pack else str(args[0])}' disabled; existing outfit remained active.",
                "info",
            )
            return self.state(), None

        if method == "update_pack_path":
            category, old_id, source = str(args[0]), str(args[1]), Path(args[2])
            old_pack = self.manager.get_pack(old_id)
            if old_pack is None or old_pack.category != category:
                raise PackError("The texture pack being updated could not be found.")
            was_enabled = old_id in set(self.manager._staged(category))
            old_meta = self.manager._pack_meta(old_pack)
            new_pack = self.manager.import_pack(source, category=category)
            new_meta_path = new_pack.dir / "meta.json"
            new_meta = self.manager._pack_meta(new_pack)
            for field in ("nexus", "author"):
                if old_meta.get(field) and not new_meta.get(field):
                    new_meta[field] = old_meta[field]
            new_meta_path.write_text(json.dumps(new_meta, indent=2) + "\n", encoding="utf-8")
            self.manager.set_enabled(new_pack.id, was_enabled)
            self.manager.remove_pack(old_id)
            self.log(
                f"Updated '{old_pack.name}' with '{new_pack.name}' "
                f"({len(new_pack.slots)} texture slot(s)).",
                "ok",
            )
            return {"ok": True, "id": new_pack.id, "name": new_pack.name}, self.state()

        if method == "toggle_pack":
            category, pack_id, enabled = str(args[0]), str(args[1]), bool(args[2])
            pack = self.manager.get_pack(pack_id)
            if pack is None or pack.category != category:
                raise PackError("The selected texture pack could not be found.")
            if enabled:
                conflicts = self.manager.enabled_conflicts(pack)
                if conflicts:
                    return {
                        "ok": False,
                        "requires_confirmation": True,
                        "pending_action": "enable",
                        "pack_id": pack.id,
                        "pack_name": pack.name,
                        "category": category,
                        "conflicts": conflicts,
                    }, None
            self.manager.set_enabled(pack_id, enabled)
            result = self.manager.apply_staged()
            self.log(f"{'Enabled' if enabled else 'Disabled'} '{pack.name if pack else pack_id}' and applied changes.", "ok")
            for conflict in result.get("conflicts", []):
                self.log(
                    f"Conflict slot {conflict['slot']}: '{conflict['loser']}' overridden by '{conflict['winner']}'.",
                    "warn",
                )
            state = self.state()
            return state, None

        if method == "apply_changes":
            result = self.manager.apply_staged(str(args[0]))
            self.log(f"Applied {len(result.get('packs', []))} enabled pack(s).", "ok")
            for conflict in result.get("conflicts", []):
                self.log(
                    f"Conflict slot {conflict['slot']}: '{conflict['loser']}' overridden by '{conflict['winner']}'.",
                    "warn",
                )
            return {"ok": True}, self.state()

        if method == "revert_pack":
            pack_id = str(args[0])
            pack = self.manager.get_pack(pack_id)
            result = self.manager.revert_pack(pack_id)
            self.log(f"Reverted '{pack.name if pack else pack_id}' ({result['reverted']} write(s)).", "ok")
            return {"ok": True}, self.state()

        if method == "remove_pack":
            pack_id = str(args[0])
            pack = self.manager.get_pack(pack_id)
            result = self.manager.remove_pack(pack_id)
            self.log(f"Uninstalled '{pack.name if pack else pack_id}' and rebuilt enabled texture packs.", "ok")
            return {"ok": True, "removed": result["removed"]}, self.state()

        if method == "open_pack_folder":
            pack = self.manager.get_pack(str(args[0]))
            if pack is None:
                raise ValueError("Texture pack not found")
            if os.name == "nt":
                os.startfile(str(pack.dir))  # type: ignore[attr-defined]
            return {"ok": True}, None

        if method == "revert_all":
            result = self.manager.revert_all()
            self.log(f"Reverted {result['reverted']} write(s) to vanilla.", "ok")
            return {"ok": True}, self.state()

        if method == "move_pack":
            category, pack_id, direction = map(str, args[:3])
            ordered = [pack.id for pack in self.manager.list_packs(category=category)]
            if pack_id in ordered:
                old = ordered.index(pack_id)
                new = old + (1 if direction == "down" else -1)
                if 0 <= new < len(ordered):
                    ordered[old], ordered[new] = ordered[new], ordered[old]
                    self.manager.set_order(category, ordered)
            state = self.state()
            return state, None

        if method == "save_nexus_key":
            key = str(args[0]).strip()
            save_api_key(self.loader.mods_root, key)
            self.log("Nexus API key saved." if key else "Nexus API key cleared.", "ok")
            state = self.state()
            return state, None

        if method == "check_updates":
            key = find_api_key(self.loader.mods_root)
            if not key:
                self.log("Nexus is not connected. Use CONNECT TO NEXUS first.", "warn")
                return {"ok": False}, None
            client = NexusClient(api_key=key, mods_root=self.loader.mods_root)
            mod_results = self.loader.check_updates(client=client)
            pack_results = self.manager.check_updates(client=client)
            for item in [*mod_results, *pack_results]:
                if item.get("has_update"):
                    self.log(f"Update available for {item['name']}: {item.get('current') or '?'} → {item['latest']}", "warn")
            self.log("Update check finished.", "ok")
            return {"ok": True}, None

        raise ValueError(f"Unknown desktop method: {method}")


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    rpc = DesktopRpc()
    try:
        result, state = rpc.dispatch(str(request.get("method", "")), request.get("args") or [])
        response = {"result": result, "state": state, "logs": rpc.logs, "error": None}
    except (LoaderError, PackError, OSError, ValueError, RuntimeError) as exc:
        rpc.log(str(exc), "err")
        response = {"result": None, "state": None, "logs": rpc.logs, "error": str(exc)}
    json.dump(response, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
