"""Launch the game through its owning client when one can be identified."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


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


def launch_game(game_dir: Path) -> str:
    """Launch the game and return ``steam`` or ``direct`` for UI logging.

    Steam must own the launch when a Steam app id is present.  Starting the EXE
    directly can leave Steam Input's virtual controller tied to the previous
    process after a quick relaunch, which is especially visible with DualShock
    controllers.
    """
    game_dir = Path(game_dir)
    executable = game_dir / "ACBlackFlag.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"Game executable not found: {executable}")

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
