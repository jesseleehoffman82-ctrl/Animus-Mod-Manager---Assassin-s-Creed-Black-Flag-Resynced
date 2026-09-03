"""Unauthenticated Nexus Mods GraphQL metadata client.

Animus Mod & Outfit Manager intentionally does not authenticate users, accept
personal API keys, or download files from Nexus Mods. This client reads only
public mod metadata. Users download archives from Nexus and select them in the
manager's file picker.
"""

from __future__ import annotations

import json
from urllib import error, request

NEXUS_GAME_ID = 9408
NEXUS_GAME_DOMAIN = "assassinscreedblackflagresynced"
GRAPHQL_ENDPOINT = "https://api.nexusmods.com/v2/graphql"
DEFAULT_TIMEOUT = 20


def mod_page_url(mod_id: int, game_domain: str = NEXUS_GAME_DOMAIN) -> str:
    """Return the public Nexus page for a game-scoped mod ID."""
    return f"https://www.nexusmods.com/{game_domain}/mods/{int(mod_id)}"


class NexusError(Exception):
    """Raised when public Nexus metadata cannot be retrieved."""


class NexusClient:
    """Small, metadata-only GraphQL client with no authentication support."""

    _MOD_QUERY = """
        query AnimusModMetadata($modId: ID!, $gameId: ID!) {
          mod(modId: $modId, gameId: $gameId) {
            modId
            gameId
            name
            author
            version
            summary
            pictureUrl
            thumbnailUrl
            updatedAt
            status
          }
        }
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout

    @staticmethod
    def _game_id(game_id: int | None) -> int:
        # Early builds stored the original Black Flag game ID. This manager is
        # Resynced-only, whose Nexus GraphQL game ID is 9408.
        return NEXUS_GAME_ID if game_id in (None, 2996) else int(game_id)

    def mod(self, mod_id: int, game_id: int = NEXUS_GAME_ID) -> dict:
        """Fetch public metadata for one Nexus mod."""
        payload = self._post(
            self._MOD_QUERY,
            {"modId": str(int(mod_id)), "gameId": str(self._game_id(game_id))},
        )
        metadata = payload.get("mod")
        if not isinstance(metadata, dict):
            raise NexusError(f"Nexus mod {int(mod_id)} was not found.")
        return metadata

    def latest_version(self, mod_id: int, game_id: int = NEXUS_GAME_ID) -> str | None:
        """Return the public version string for a linked Nexus mod."""
        latest = self.mod(mod_id, game_id).get("version")
        return str(latest) if latest else None

    def _post(self, query: str, variables: dict) -> dict:
        encoded = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = request.Request(
            GRAPHQL_ENDPOINT,
            data=encoded,
            method="POST",
            headers={
                "User-Agent": "Animus-Mod-Outfit-Manager/0.1.5",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raise NexusError(f"Nexus GraphQL HTTP {exc.code}.") from exc
        except error.URLError as exc:
            raise NexusError(f"Nexus metadata unavailable: {exc.reason}") from exc

        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NexusError("Nexus returned an invalid metadata response.") from exc

        errors = document.get("errors")
        if errors:
            messages = [str(item.get("message", "Unknown GraphQL error"))
                        for item in errors if isinstance(item, dict)]
            raise NexusError("Nexus metadata error: " + "; ".join(messages))
        data = document.get("data")
        if not isinstance(data, dict):
            raise NexusError("Nexus returned no metadata.")
        return data
