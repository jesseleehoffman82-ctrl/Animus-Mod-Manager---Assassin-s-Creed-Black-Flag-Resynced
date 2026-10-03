from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent


def backend_roots() -> list[Path]:
    roots = [
        ROOT / "vendor" / "shipworkshop-v1.0.1",
        ROOT.parent / "shipworkshop-v1.0.1",
        Path(r"C:\Users\YOUR_USER\Documents\Codex\2026-08-01\w\work\shipworkshop-v1.0.1"),
    ]
    return [r for r in roots if r.exists()]


def find_backend_root() -> Path:
    for root in backend_roots():
        py = root / "python" / "python.exe"
        cli = root / "src" / "ship_cli.py"
        if py.exists() and cli.exists():
            return root
    raise RuntimeError("ShipWorkshop backend was not found next to the app.")


BACKEND_ROOT = find_backend_root()
BACKEND_PYTHON = BACKEND_ROOT / "python" / "python.exe"
BACKEND_CLI = BACKEND_ROOT / "src" / "ship_cli.py"


def ensure_oodle_dlls() -> None:
    dll_name = "oo2core_7_win64.dll"
    candidates = [
        ROOT.parent / "anviltoolkit-run" / "Libs",
        ROOT.parent / "anviltoolkit-136-bin" / "Libs",
        Path(r"C:\Users\YOUR_USER\Documents\Codex\2026-08-01\w\work\anviltoolkit-run\Libs"),
        Path(r"C:\Users\YOUR_USER\Documents\Codex\2026-08-01\w\work\anviltoolkit-136-bin\Libs"),
        BACKEND_ROOT / "tools",
    ]
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    (BACKEND_ROOT / "tools").mkdir(parents=True, exist_ok=True)
    for source_dir in candidates:
        source = source_dir / dll_name
        if not source.exists():
            continue
        for dest_dir in (TOOLS_DIR, BACKEND_ROOT / "tools"):
            dest = dest_dir / dll_name
            if not dest.exists():
                shutil.copy2(source, dest)
        return


ensure_oodle_dlls()


def load_catalog(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeError:
        return json.loads(path.read_text(encoding="utf-8"))


def find_target(catalog: dict, key: str) -> dict:
    needle = str(key).strip().lower()
    if not needle:
        raise KeyError("empty target key")

    fields = ("id", "anahtar", "kisa_ad", "ad")
    for item in catalog.get("hedefler", []):
        for field in fields:
            value = item.get(field)
            if value and str(value).strip().lower() == needle:
                return item

    for item in catalog.get("hedefler", []):
        for field in fields:
            value = item.get(field)
            if value and needle in str(value).strip().lower():
                return item

    raise KeyError(f"no catalog target matched {key!r}")


def run_backend(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BACKEND_PYTHON), str(BACKEND_CLI), *args],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_game_registered(game: Path) -> None:
    if not game.exists():
        raise RuntimeError(f"Game folder does not exist: {game}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a Jackdaw texture target to PNG.")
    parser.add_argument("--game", required=True, help="Game folder containing DataPC_boot.forge")
    parser.add_argument("--catalog", required=True, help="Path to ship_hedefler.json")
    parser.add_argument("--target", required=True, help="Target id, key, or name")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--level", type=int, default=0, help="Mip level to export")
    args = parser.parse_args()

    game = Path(args.game).resolve()
    catalog_path = Path(args.catalog).resolve()
    output = Path(args.output).resolve()

    catalog = load_catalog(catalog_path)
    target = find_target(catalog, args.target)
    export_key = target.get("anahtar") or target.get("id") or args.target

    ensure_game_registered(game)

    output.parent.mkdir(parents=True, exist_ok=True)
    result = run_backend("export", str(export_key), "-o", str(output))
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(
            "ShipWorkshop export failed.\n"
            f"{result.stdout}\n{result.stderr}".strip()
        )

    print(json.dumps({
        "target": export_key,
        "output": str(output),
        "stdout": result.stdout[-2000:],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
