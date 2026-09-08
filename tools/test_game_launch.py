from pathlib import Path
import tempfile
from unittest import mock

from Animus_loader.game_launch import game_executable, launch_game, steam_app_id, steam_build_id, steam_executable


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
        (root / "Steam" / "steamapps" / "appmanifest_3751950.acf").write_text(
            '"AppState" { "buildid" "24833802" }', encoding="utf-8")
        assert steam_build_id(game) == "24833802"


def test_tolerates_a_narrow_future_executable_rename() -> None:
    with tempfile.TemporaryDirectory() as raw:
        game = Path(raw)
        renamed = game / "ACBlackFlagResynced.exe"
        renamed.write_bytes(b"")
        (game / "UbisoftConnectInstaller.exe").write_bytes(b"")
        assert game_executable(game) == renamed


def test_steam_build_launches_through_steam() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = _game_tree(root)
        with mock.patch("Animus_loader.game_launch.subprocess.Popen") as popen, \
                mock.patch("Animus_loader.game_launch.game_process_running", return_value=False), \
                mock.patch("Animus_loader.game_launch.wait_for_game_start", return_value=True):
            assert launch_game(game) == "steam"
        command = popen.call_args.args[0]
        assert command == [str(root / "Steam" / "steam.exe"), "-applaunch", "3751950"]


def test_non_steam_build_keeps_direct_launch_fallback() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        game = _game_tree(root, with_app_id=False)
        with mock.patch("Animus_loader.game_launch.subprocess.Popen") as popen, \
                mock.patch("Animus_loader.game_launch.game_process_running", return_value=False):
            assert launch_game(game) == "direct"
        assert popen.call_args.args[0] == [str(game / "ACBlackFlag.exe")]


def test_reports_failed_steam_start_instead_of_false_success() -> None:
    with tempfile.TemporaryDirectory() as raw:
        game = _game_tree(Path(raw))
        with mock.patch("Animus_loader.game_launch.subprocess.Popen"), \
                mock.patch("Animus_loader.game_launch.game_process_running", return_value=False), \
                mock.patch("Animus_loader.game_launch.wait_for_game_start", return_value=False):
            try:
                launch_game(game)
            except RuntimeError as exc:
                assert "DLL/ASI mod may be incompatible" in str(exc)
            else:
                raise AssertionError("A failed Steam launch was reported as successful")


if __name__ == "__main__":
    test_detects_steam_install_and_app_id()
    test_tolerates_a_narrow_future_executable_rename()
    test_steam_build_launches_through_steam()
    test_non_steam_build_keeps_direct_launch_fallback()
    test_reports_failed_steam_start_instead_of_false_success()
    print("game launch tests passed")
