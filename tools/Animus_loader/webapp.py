"""Animus Mod & Outfit Manager - desktop shell hosting the HTML/CSS/JS frontend.

This is the new entry point. It embeds the web UI (tools/Animus_loader/web/)
inside a native, frameless pywebview window and exposes the existing Python
backend (core.py / packs.py / nexus.py) to it via api.py. No mod-management
logic lives here or in the frontend -- this module only wires the two
together.
"""

from __future__ import annotations

import faulthandler
import logging
from pathlib import Path

import webview

from .core import DEFAULT_GAME_DIR, Loader
from .packs import PackManager
from .api import Api

WEB_DIR = Path(__file__).parent / "web"
INDEX_HTML = WEB_DIR / "index.html"
LOG_PATH = Path(__file__).resolve().parents[2] / "mods" / "animus-mod-manager.log"


def main(argv: list[str] | None = None) -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    crash_log = LOG_PATH.open("a", encoding="utf-8")
    faulthandler.enable(crash_log)
    logging.info("Starting Animus Mod & Outfit Manager web interface")

    loader = Loader(game_dir=DEFAULT_GAME_DIR)
    manager = PackManager(game_dir=loader.game_dir, mods_root=loader.mods_root)
    api = Api(loader, manager)

    window = webview.create_window(
        "Animus Mod & Outfit Manager",
        url=str(INDEX_HTML),
        js_api=api,
        width=1360,
        height=900,
        min_size=(1180, 760),
        background_color="#0a0908",
        frameless=True,
        easy_drag=False,
    )
    api.window = window

    try:
        webview.start(debug=False)
    except BaseException:
        logging.exception("Desktop shell terminated unexpectedly")
        raise
    finally:
        crash_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
