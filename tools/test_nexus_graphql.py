"""Regression checks for the public, metadata-only Nexus client."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from Animus_loader.nexus import GRAPHQL_ENDPOINT, NexusClient  # noqa: E402


class FakeResponse:
    def __init__(self, document: dict):
        self.payload = json.dumps(document).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


def main() -> int:
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = {key.lower(): value for key, value in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"data": {"mod": {
            "modId": 458,
            "gameId": 9408,
            "name": "Example",
            "author": "Author",
            "version": "1.2.3",
        }}})

    with patch("Animus_loader.nexus.request.urlopen", fake_urlopen):
        metadata = NexusClient(timeout=7).mod(458, 2996)

    assert captured["url"] == GRAPHQL_ENDPOINT
    assert captured["timeout"] == 7
    assert captured["body"]["variables"] == {"modId": "458", "gameId": "9408"}
    assert "authorization" not in captured["headers"]
    assert "apikey" not in captured["headers"]
    assert metadata["gameId"] == 9408
    assert metadata["version"] == "1.2.3"
    print("NEXUS GRAPHQL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
