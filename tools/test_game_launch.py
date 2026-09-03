from pathlib import Path
import tempfile
from unittest import mock

from Animus_loader.game_launch import launch_game, steam_app_id, steam_executable


def _game_tree(root: Path, with_app_id: bool = True) -> Path:
    game = root / "Steam" / "steamapps" / "common" / "Black Flag"
    game.mkdir(parents=True)
    (root / "Steam" / "steam.exe").write_bytes(b"")
    (game / "ACBlackFlag.exe").write_bytes(b"")
    if with_app_id:
        (game / "steam_appid.txt").write_bytes(b"3751950\n\x00")
    return game


def test_detects_steam_install_and_app_id() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = _game_tree(root)
        assert steam_app_id(game) == "3751950"
        assert steam_executable(game) == (root / "Steam" / "steam.exe")


def test_steam_build_launches_through_steam() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = _game_tree(root)
        with mock.patch("Animus_loader.game_launch.subprocess.Popen") as popen:
            assert launch_game(game) == "steam"
        command = popen.call_args.args[0]
        assert command == [str(root / "Steam" / "steam.exe"), "-applaunch", "3751950"]


def test_non_steam_build_keeps_direct_launch_fallback() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = _game_tree(root, with_app_id=False)
        with mock.patch("Animus_loader.game_launch.subprocess.Popen") as popen:
            assert launch_game(game) == "direct"
        assert popen.call_args.args[0] == [str(game / "ACBlackFlag.exe")]


if __name__ == "__main__":
    test_detects_steam_install_and_app_id()
    test_steam_build_launches_through_steam()
    test_non_steam_build_keeps_direct_launch_fallback()
    print("game launch tests passed")
