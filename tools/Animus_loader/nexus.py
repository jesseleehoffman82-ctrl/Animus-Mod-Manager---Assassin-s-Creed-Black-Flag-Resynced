"""Nexus Mods API client (stdlib only) for update checks.

MO2 and Vortex both use the Nexus REST API for "is there an update?" checks.
This module mimics that: given a pack's Nexus mod id, it fetches the mod's
latest version and compares it to the installed one.

Requires a Nexus API key (free, from your Nexus account page) passed via the
NEXUS_API_KEY env var or the `nexus_key.json` file in mods/textures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

#: Nexus game id for Assassin's Creed IV: Black Flag.
NEXUS_GAME_ID = 2996
NEXUS_GAME_DOMAIN = "assassinscreedblackflagresynced"


def mod_page_url(mod_id: int, game_domain: str = NEXUS_GAME_DOMAIN) -> str:
    """Return the public Nexus page for a game-scoped mod id."""
    return f"https://www.nexusmods.com/{game_domain}/mods/{int(mod_id)}"

API_BASE = "https://api.nexusmods.com/v1"
DEFAULT_TIMEOUT = 20


class NexusError(Exception):
    """Raised for Nexus API problems."""


def find_api_key(mods_root: Path | None) -> str | None:
    """Resolve an API key: env var wins, else the local key file."""
    env = os.environ.get("NEXUS_API_KEY")
    if env:
        return env.strip() or None
    if mods_root is None:
        return None
    key_file = Path(mods_root) / "textures" / "nexus_key.json"
    if key_file.is_file():
        try:
            data = json.loads(key_file.read_text(encoding="utf-8"))
            k = data.get("api_key", "") if isinstance(data, dict) else ""
            return k.strip() or None
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_api_key(mods_root: Path, api_key: str) -> None:
    key_file = Path(mods_root) / "textures" / "nexus_key.json"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(json.dumps({"api_key": api_key}, indent=2) + "\n", encoding="utf-8")


class NexusClient:
    """Minimal Nexus REST client (no third-party deps)."""

    def __init__(self, api_key: str | None = None, mods_root: Path | None = None,
                 timeout: int = DEFAULT_TIMEOUT):
        if api_key:
            self.api_key = api_key.strip()
        elif mods_root is not None:
            self.api_key = find_api_key(mods_root) or ""
        else:
            self.api_key = ""
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    def mod(self, mod_id: int, game_id: int = NEXUS_GAME_ID) -> dict:
        """Fetch the mod metadata JSON."""
        return self._get(f"/games/{game_id}/mods/{mod_id}.json")

    def latest_version(self, mod_id: int, game_id: int = NEXUS_GAME_ID) -> str | None:
        """Return the mod's latest available version string (or None)."""
        data = self.mod(mod_id, game_id)
        latest = data.get("version")
        if not latest:
            files = data.get("files") or []
            if files:
                latest = files[0].get("version") or files[0].get("file_version")
        return str(latest) if latest else None

    def latest_file(self, mod_id: int, game_id: int = NEXUS_GAME_ID) -> dict | None:
        """Return the newest main file for a mod: {name, version, size, download_url}."""
        data = self.mod(mod_id, game_id)
        files = data.get("files") or []
        main = [f for f in files if f.get("category_name", "").lower() != "optional"]
        files = main or files
        if not files:
            return None
        f = files[0]
        url = None
        try:
            dl = self._get(f"/games/{game_id}/mods/{mod_id}/files/{f.get('file_id')}/download_link.json")
            url = (dl or {}).get("download_link")
        except NexusError:
            url = None
        return {
            "name": f.get("file_name"),
            "version": f.get("version") or f.get("file_version"),
            "size": f.get("size"),
            "download_url": url,
        }

    def changed_days(self, mod_id: int, periods: int = 30,
                     game_id: int = NEXUS_GAME_ID) -> list:
        """Return changelog entries for the mod (last `periods` days)."""
        data = self._get(f"/games/{game_id}/mods/{mod_id}/changelogs.json?periods={periods}d")
        return data.get("changelogs") or []

    # ------------------------------------------------------------------ #
    def _get(self, path: str) -> dict:
        url = API_BASE + path
        headers = {
            "User-Agent": "Animus-Mod-Manager/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["apikey"] = self.api_key
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404:
                raise NexusError(f"Nexus mod not found (404): {path}")
            if exc.code == 403:
                raise NexusError(
                    "Nexus API rejected the request (403). Ensure the API key is valid. "
                    "Set it via the Nexus API key field or NEXUS_API_KEY env var.")
            raise NexusError(f"Nexus HTTP {exc.code}: {path}")
        except error.URLError as exc:
            raise NexusError(f"Nexus network error: {exc.reason}")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise NexusError("Nexus returned non-JSON response.")
