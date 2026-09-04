"""Launch the game through its owning client when one can be identified."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def game_executable(game_dir: Path) -> Path | None:
    """Return the Resynced game executable without accepting helper installers.

    Ubisoft currently ships ``ACBlackFlag.exe``. The narrow fallback tolerates
    a future Resynced rename while deliberately excluding broad matches such as
    UbisoftConnectInstaller.exe and third-party helper programs.
    """
    game_dir = Path(game_dir)
    preferred = game_dir / "ACBlackFlag.exe"
    if preferred.is_file():
        return preferred
    candidates = [
        path for path in game_dir.glob("*.exe")
        if re.match(r"^ac.*black.*flag.*\.exe$", path.name, re.IGNORECASE)
    ]
    return candidates[0] if len(candidates) == 1 else None


def steam_app_id(game_dir: Path) -> str | None:
    """Return the numeric Steam app id shipped with the selected game build."""
    marker = Path(game_dir) / "steam_appid.txt"
    try:
        contents = marker.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    match = re.search(r"(?<!\d)(\d{3,12})(?!\d)", contents)
    return match.group(1) if match else None


def steam_executable(game_dir: Path) -> Path | None:
    """Find Steam from a normal ``steamapps/common/<game>`` installation."""
    game_dir = Path(game_dir).resolve()
    for parent in game_dir.parents:
        if parent.name.casefold() != "steamapps":
            continue
        candidate = parent.parent / "steam.exe"
        if candidate.is_file():
            return candidate
    return None


def steam_build_id(game_dir: Path) -> str | None:
    """Read the installed Steam build id for compatibility diagnostics."""
    app_id = steam_app_id(game_dir)
    if not app_id:
        return None
    resolved = Path(game_dir).resolve()
    steamapps = next((parent for parent in resolved.parents
                      if parent.name.casefold() == "steamapps"), None)
    if steamapps is None:
        return None
    try:
        manifest = (steamapps / f"appmanifest_{app_id}.acf").read_text(
            encoding="utf-8", errors="ignore")
    except OSError:
        return None
    match = re.search(r'"buildid"\s+"(\d+)"', manifest, re.IGNORECASE)
    return match.group(1) if match else None


def launch_game(game_dir: Path) -> str:
    """Launch the game and return ``steam`` or ``direct`` for UI logging.

    Steam must own the launch when a Steam app id is present.  Starting the EXE
    directly can leave Steam Input's virtual controller tied to the previous
    process after a quick relaunch, which is especially visible with DualShock
    controllers.
    """
    game_dir = Path(game_dir)
    executable = game_executable(game_dir)
    if executable is None:
        raise FileNotFoundError(f"Game executable not found in: {game_dir}")

    app_id = steam_app_id(game_dir)
    steam = steam_executable(game_dir) if app_id else None
    if app_id and steam:
        subprocess.Popen(
            [str(steam), "-applaunch", app_id],
            cwd=str(steam.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return "steam"

    if app_id and os.name == "nt":
        os.startfile(f"steam://run/{app_id}")  # type: ignore[attr-defined]
        return "steam"

    subprocess.Popen(
        [str(executable)],
        cwd=str(game_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return "direct"
