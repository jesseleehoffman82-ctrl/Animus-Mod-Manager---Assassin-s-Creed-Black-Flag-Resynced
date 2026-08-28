"""JSON bridge API between the HTML/CSS/JS frontend and the existing Python
mod-management backend (core.py / packs.py / outfits.py / nexus.py).

This module does NOT reimplement any mod-management logic. Every method here
is a thin wrapper that calls into the existing `Loader` / `PackManager`
classes and returns JSON-serializable data for the web UI to render.

The frontend (web/app.js) calls these methods via `window.pywebview.api.*`.
Long-running operations run on a background thread and push results back to
the page via `window.evaluate_js(...)` calling `window.animusLog(...)` and
`window.animusSetState(...)` (defined in web/app.js), mirroring the
threaded pattern used by the previous Tkinter GUI (`_run_threaded`).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.request
from pathlib import Path
from datetime import datetime

import webview

from .core import DEFAULT_GAME_DIR, Loader, LoaderError
from .packs import PackError, PackManager, CATEGORY_CREW, CATEGORY_OUTFIT, CATEGORY_WEAPON
from .nexus import NexusClient, NexusError, save_api_key, find_api_key


class Api:
    """Exposed to JS as `window.pywebview.api`."""

    def __init__(self, loader: Loader, manager: PackManager):
        self.loader = loader
        self.manager = manager
        self.window: "webview.Window | None" = None

    # ------------------------------------------------------------------ #
    # push helpers (Python -> JS)
    # ------------------------------------------------------------------ #
    def _log(self, message: str, tag: str = "info") -> None:
        if not self.window:
            return
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "tag": tag,
            "message": message,
        }
        try:
            self.window.evaluate_js(f"window.animusLog({json.dumps(entry)})")
        except Exception:
            pass

    def _push_state(self) -> None:
        if not self.window:
            return
        try:
            state = self.get_state()
            self.window.evaluate_js(f"window.animusSetState({json.dumps(state)})")
        except Exception:
            pass

    def _rebuild_manager(self) -> None:
        self.manager = PackManager(game_dir=self.loader.game_dir,
                                   mods_root=self.loader.mods_root)

    def _create_file_dialog(self, dialog_type, *, kind: str = "all", **kwargs):
        """Show a file picker without touching WinForms across threads.

        pywebview 6.2.1 can deadlock when ``create_file_dialog`` is invoked by
        a JS-API worker on Windows.  Use an isolated STA PowerShell process for
        native Windows pickers, leaving the WebView message pump completely
        untouched.  Other platforms retain pywebview's normal implementation.
        """
        if not self.window:
            return None

        if os.name != "nt":
            return self.window.create_file_dialog(dialog_type, **kwargs)

        mode = "folder" if dialog_type == webview.FileDialog.FOLDER else "open"
        script = Path(__file__).with_name("native_dialog.ps1")
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(script), "-Mode", mode, "-Kind", kind,
        ]
        directory = str(kwargs.get("directory") or "")
        if directory:
            command.extend(["-InitialDirectory", directory])

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False,
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "Native file picker failed").strip()
            raise RuntimeError(detail)
        selected = completed.stdout.strip()
        return (selected,) if selected else None

    # ------------------------------------------------------------------ #
    # state / read-only
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict:
        game_dir = self.loader.game_dir
        exe = game_dir / "ACBlackFlag.exe"
        return {
            "game_dir": str(game_dir),
            "game_found": exe.is_file(),
            "mods": self.list_mods(),
            "outfits": self.list_packs(CATEGORY_OUTFIT),
            "weapons": self.list_packs(CATEGORY_WEAPON),
            "crew": self.list_packs(CATEGORY_CREW),
            "proxy_status": self.loader.proxy_status(),
            "nexus_key_set": bool(find_api_key(self.loader.mods_root)),
        }

    def list_mods(self) -> list[dict]:
        mods = []
        installed = {r.name: r for r in self.loader.list_installed()}
        for path in self.loader.discover_packages():
            try:
                pkg = self.loader.read_package(path)
            except LoaderError as exc:
                mods.append({
                    "name": path.stem, "version": "-", "author": "-",
                    "targets": 0, "enabled": False, "invalid": True,
                    "error": str(exc), "path": str(path),
                })
                continue
            record = installed.get(pkg.name)
            enabled = bool(record and record.enabled)
            compatibility = [
                str(entry["compatibility"])
                for entry in (record.backups if record else [])
                if entry.get("compatibility")
            ]
            mods.append({
                "name": pkg.name,
                "version": pkg.version,
                "author": pkg.author,
                "targets": len(pkg.targets),
                "enabled": enabled,
                "dll_compatibility": compatibility[-1] if compatibility else None,
                "invalid": False,
                "category": pkg.category,
                "path": str(path),
            })
        return mods

    def list_packs(self, category: str) -> list[dict]:
        staged = set(self.manager._staged(category))
        packs = self.manager.list_packs(category=category)
        result = []
        for pack in packs:
            result.append({
                "id": pack.id,
                "name": pack.name,
                "slots": len(pack.slots),
                "enabled": pack.id in staged,
            })
        return result

    def get_mod_details(self, name: str) -> dict:
        path = self._find_package_path(name)
        if not path:
            return {"ok": False, "error": "Package not found"}
        try:
            pkg = self.loader.read_package(path)
        except LoaderError as exc:
            return {"ok": False, "error": str(exc)}
        targets = [
            {"forge": t.forge, "resource_id": f"0x{t.resource_id:016X}",
             "mode": t.mode, "occurrence": t.occurrence}
            for t in pkg.targets
        ]
        return {
            "ok": True, "name": pkg.name, "version": pkg.version,
            "author": pkg.author, "category": pkg.category,
            "targets": targets, "path": str(path),
        }

    # ------------------------------------------------------------------ #
    # game folder
    # ------------------------------------------------------------------ #
    def browse_game_dir(self) -> dict:
        if self.window:
            result = self._create_file_dialog(
                webview.FileDialog.FOLDER, directory=str(self.loader.game_dir))
            if result:
                self.loader.game_dir = Path(result[0])
                self._rebuild_manager()
                self._log(f"Game folder set to {self.loader.game_dir}")
        return self.get_state()

    def detect_game_dir(self) -> dict:
        self.loader = Loader(game_dir=DEFAULT_GAME_DIR)
        self._rebuild_manager()
        self._log(f"Detected game folder: {self.loader.game_dir}")
        return self.get_state()

    def refresh(self) -> dict:
        self._log("Refreshed.", "info")
        return self.get_state()

    def launch_game(self) -> dict:
        executable = self.loader.game_dir / "ACBlackFlag.exe"
        if not executable.is_file():
            self._log(f"Game executable not found: {executable}", "err")
            return {"ok": False}
        subprocess.Popen(
            [str(executable)],
            cwd=str(self.loader.game_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        self._log("Launching Assassin's Creed Black Flag Resynced.", "ok")
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # window chrome (frameless titlebar controls)
    # ------------------------------------------------------------------ #
    def win_minimize(self) -> None:
        if self.window:
            self.window.minimize()

    def win_toggle_maximize(self) -> None:
        if self.window:
            self.window.toggle_fullscreen() if False else self.window.maximize()

    def win_restore(self) -> None:
        if self.window:
            self.window.restore()

    def win_close(self) -> None:
        if self.window:
            self.window.destroy()

    # ------------------------------------------------------------------ #
    # mods
    # ------------------------------------------------------------------ #
    def _find_package_path(self, name: str) -> Path | None:
        for path in self.loader.discover_packages():
            try:
                pkg = self.loader.read_package(path)
            except LoaderError:
                continue
            if pkg.name == name:
                return path
        return None

    def install_mod(self) -> dict:
        if not self.window:
            return {"ok": False}
        chosen = self._create_file_dialog(
            webview.FileDialog.OPEN,
            kind="mod",
            file_types=("Animus or Nexus mod (*.jmod;*.zip)", "All files (*.*)"))
        if not chosen:
            return {"ok": False}
        path = Path(chosen[0])
        threading.Thread(target=self._do_install_mod, args=(path,), daemon=True).start()
        return {"ok": True, "started": True}

    def _do_install_mod(self, path: Path) -> None:
        try:
            target, pkg, converted = self.loader.import_package(path)
            backups = self.loader.apply(target, priority=0)
            if converted:
                self._log(f"Imported ordinary Nexus archive ({len(pkg.targets)} managed file(s)).", "info")
            self._log(f"Installed '{pkg.name} v{pkg.version}' — "
                      f"{len(backups)} target(s) patched", "ok")
        except (LoaderError, OSError) as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def toggle_mod(self, name: str) -> dict:
        threading.Thread(target=self._do_toggle_mod, args=(name,), daemon=True).start()
        return {"ok": True, "started": True}

    def _do_toggle_mod(self, name: str) -> None:
        installed = {r.name: r for r in self.loader.list_installed()}
        record = installed.get(name)
        enabled = bool(record and record.enabled)
        try:
            if enabled:
                restored = self.loader.disable(name)
                self._log(f"Disabled '{name}'; restored {len(restored)} file(s)", "ok")
            else:
                path = self._find_package_path(name)
                if not path:
                    self._log(f"Could not find package for '{name}'", "err")
                    return
                pkg = self.loader.read_package(path)
                backups = self.loader.apply(path, priority=0)
                self._log(f"Enabled '{pkg.name} v{pkg.version}' — "
                          f"{len(backups)} target(s) patched", "ok")
        except (LoaderError, OSError) as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def uninstall_mod(self, name: str) -> dict:
        threading.Thread(target=self._do_uninstall_mod, args=(name,), daemon=True).start()
        return {"ok": True, "started": True}

    def _do_uninstall_mod(self, name: str) -> None:
        try:
            restored = self.loader.remove(name)
            detail = f"; restored {len(restored)} file(s)" if restored else ""
            self._log(f"Uninstalled '{name}'{detail}", "ok")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        # Fully remove the package file so the mod disappears from the list.
        path = self._find_package_path(name)
        if path and path.is_file():
            try:
                path.unlink()
                self._log(f"Removed '{name}' package file.", "ok")
            except OSError as exc:
                self._log(f"Could not remove package file: {exc}", "warn")
        self._push_state()

    def remove_mod_files(self, name: str) -> dict:
        """Delete the .jmod package from the packages folder (fully remove from list)."""
        threading.Thread(target=self._do_remove_mod_files, args=(name,),
                         daemon=True).start()
        return {"ok": True, "started": True}

    def _do_remove_mod_files(self, name: str) -> None:
        try:
            self.loader.remove(name)  # restore any active state first
        except Exception:  # noqa: BLE001
            pass
        path = self._find_package_path(name)
        if path and path.is_file():
            try:
                path.unlink()
                self._log(f"Removed '{name}' package file.", "ok")
            except OSError as exc:
                self._log(f"Could not remove package: {exc}", "err")
        else:
            self._log(f"No package file found for '{name}'.", "info")
        self._push_state()

    def open_mod_folder(self, name: str) -> dict:
        path = self._find_package_path(name)
        folder = path.parent if path else self.loader.packages_dir
        try:
            if path and path.is_file() and os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception as exc:
            self._log(f"Could not open folder: {exc}", "err")
        return {"ok": True}

    def get_mod_nexus(self, name: str) -> dict | None:
        """Return the Nexus id/version metadata attached to a .jmod, if any."""
        path = self._find_package_path(name)
        if not path:
            return None
        try:
            pkg = self.loader.read_package(path)
        except LoaderError:
            return None
        nexus = (pkg.manifest or {}).get("nexus")
        if not nexus:
            return None
        return {"game_id": nexus.get("game_id", 2996),
                "mod_id": nexus.get("mod_id"), "version": pkg.version}

    def update_mod(self, name: str) -> dict:
        """Download the latest version of a Nexus-linked mod and install it."""
        threading.Thread(target=self._do_update_mod, args=(name,), daemon=True).start()
        return {"ok": True, "started": True}

    def _do_update_mod(self, name: str) -> None:
        meta = self.get_mod_nexus(name)
        if not meta:
            self._log(f"No Nexus link on '{name}'. Set one via the mod's "
                      f"manifest (nexus: game_id/mod_id).", "warn")
            return
        api_key = find_api_key(self.loader.mods_root)
        if not api_key:
            self._log("No Nexus API key set. Save one first.", "warn")
            return
        client = NexusClient(api_key=api_key, mods_root=self.loader.mods_root)
        try:
            latest = client.latest_file(meta["mod_id"], meta.get("game_id", 2996))
        except NexusError as exc:
            self._log(f"Update check failed: {exc}", "err")
            return
        if not latest or not latest.get("download_url"):
            self._log(f"No downloadable update file found for '{name}' "
                      f"(may need a premium Nexus account).", "warn")
            return
        self._log(f"Downloading {latest['name']} "
                  f"({latest.get('version') or '?'})...", "info")
        target = self.loader.packages_dir / (latest["name"] or f"{name}-update.jmod")
        try:
            urllib.request.urlretrieve(latest["download_url"], target)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Download failed: {exc}", "err")
            return
        self._log(f"Downloaded {target.name}. Installing...", "info")
        try:
            pkg = self.loader.read_package(target)
            backups = self.loader.apply(target, priority=0)
            self._log(f"Updated '{pkg.name} v{pkg.version}' — "
                      f"{len(backups)} target(s) patched", "ok")
        except (LoaderError, OSError) as exc:
            self._log(f"Installing update failed: {exc}", "err")
        except Exception as exc:  # noqa: BLE001
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    # ------------------------------------------------------------------ #
    # outfits / weapons / crew (shared PackManager)
    # ------------------------------------------------------------------ #
    def install_pack(self, category: str) -> dict:
        if not self.window:
            return {"ok": False}
        chosen = self._create_file_dialog(
            webview.FileDialog.OPEN,
            kind="pack",
            file_types=("Pack archive (*.zip;*.7z;*.rar;*.tar;*.tgz)",
                       "Texture (*.dds;*.png)", "All files (*.*)"))
        if not chosen:
            return {"ok": False}
        path = Path(chosen[0])
        threading.Thread(target=self._do_install_pack, args=(category, path),
                         daemon=True).start()
        return {"ok": True, "started": True}

    def _do_install_pack(self, category: str, path: Path) -> None:
        try:
            result = self.manager.install(path, category=category)
            pack = result["pack"]
            self._log(f"Installed '{pack.name}' ({len(pack.slots)} slot(s)). "
                      f"Enabled + applied.", "ok")
        except PackError as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def toggle_pack(self, category: str, pack_id: str, enabled: bool) -> dict:
        self.manager.set_enabled(pack_id, enabled)
        pack = self.manager.get_pack(pack_id)
        label = pack.name if pack else pack_id
        result = self.manager.apply_staged()
        self._log(f"{'Enabled' if enabled else 'Disabled'} '{label}' and applied changes.", "ok")
        for conflict in result.get("conflicts", []):
            self._log(f"Conflict slot {conflict['slot']}: '{conflict['loser']}' "
                      f"overridden by '{conflict['winner']}'.", "warn")
        return self.get_state()

    def apply_changes(self, category: str) -> dict:
        threading.Thread(target=self._do_apply_changes, args=(category,),
                         daemon=True).start()
        return {"ok": True, "started": True}

    def _do_apply_changes(self, category: str) -> None:
        try:
            result = self.manager.apply_staged(category)
            if result.get("packs"):
                n = len(result["packs"])
                self._log(f"Applied {n} enabled pack(s) "
                          f"({result['external_mips']} mips, "
                          f"{result['materials']} materials).", "ok")
                for c in result.get("conflicts", []):
                    self._log(f"Conflict slot {c['slot']}: '{c['loser']}' "
                              f"overridden by '{c['winner']}' (lower in list).", "warn")
            else:
                self._log("No enabled packs to apply.", "info")
        except PackError as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def revert_pack(self, pack_id: str) -> dict:
        threading.Thread(target=self._do_revert_pack, args=(pack_id,), daemon=True).start()
        return {"ok": True, "started": True}

    def _do_revert_pack(self, pack_id: str) -> None:
        pack = self.manager.get_pack(pack_id)
        name = pack.name if pack else pack_id
        try:
            result = self.manager.revert_pack(pack_id)
            self._log(f"Reverted '{name}' ({result['reverted']} write(s)).", "ok")
            for issue in result.get("issues", []):
                if issue and issue != "no journal":
                    self._log(f"Note: {issue}", "warn")
        except (PackError, OSError) as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def revert_all(self) -> dict:
        threading.Thread(target=self._do_revert_all, daemon=True).start()
        return {"ok": True, "started": True}

    def _do_revert_all(self) -> None:
        try:
            result = self.manager.revert_all()
            self._log(f"Reverted {result['reverted']} write(s) to vanilla.", "ok")
        except (PackError, OSError) as exc:
            self._log(str(exc), "err")
        except Exception as exc:  # pragma: no cover
            self._log(f"Unexpected error: {exc}", "err")
        self._push_state()

    def move_pack(self, category: str, pack_id: str, direction: str) -> dict:
        ordered = [p.id for p in self.manager.list_packs(category=category)]
        if pack_id not in ordered:
            return self.get_state()
        i = ordered.index(pack_id)
        j = i + 1 if direction == "down" else i - 1
        if 0 <= j < len(ordered):
            ordered[i], ordered[j] = ordered[j], ordered[i]
            self.manager.set_order(category, ordered)
        return self.get_state()

    # ------------------------------------------------------------------ #
    # nexus
    # ------------------------------------------------------------------ #
    def save_nexus_key(self, key: str) -> dict:
        key = (key or "").strip()
        save_api_key(self.loader.mods_root, key)
        self._log("Nexus API key saved." if key else "Nexus API key cleared.", "ok")
        return self.get_state()

    def check_updates(self) -> dict:
        threading.Thread(target=self._do_check_updates, daemon=True).start()
        return {"ok": True, "started": True}

    def _do_check_updates(self) -> None:
        api_key = find_api_key(self.loader.mods_root)
        if not api_key:
            self._log("No Nexus API key set. Paste a key and SAVE first.", "warn")
            return
        self._log("Checking for updates...", "info")
        try:
            client = NexusClient(api_key=api_key, mods_root=self.loader.mods_root)
            mod_results = self.loader.check_updates(client=client)
            pack_results = self.manager.check_updates(client=client)
        except Exception as exc:  # pragma: no cover
            self._log(f"Update check failed: {exc}", "err")
            return
        for r in mod_results:
            if r.get("error") and r.get("error") != "no nexus id":
                self._log(f"[mod] {r['name']}: {r['error']}", "err")
            elif r.get("mod_id") is None:
                continue
            elif r.get("has_update"):
                self._log(f"Update available [mod] {r['name']}: "
                          f"{r.get('current') or '?'} -> {r['latest']}", "warn")
            else:
                self._log(f"[mod] {r['name']}: up to date ({r.get('latest')})", "info")
        for r in pack_results:
            if r.get("error") and r.get("error") != "no nexus id":
                self._log(f"[{r.get('category')}] {r['name']}: {r['error']}", "err")
            elif r.get("mod_id") is None:
                continue
            elif r.get("has_update"):
                self._log(f"Update available [{r.get('category')}] {r['name']}: "
                          f"{r.get('current') or '?'} -> {r['latest']}", "warn")
            else:
                self._log(f"[{r.get('category')}] {r['name']}: up to date "
                          f"({r.get('latest')})", "info")
        self._log("Update check finished.", "ok")
