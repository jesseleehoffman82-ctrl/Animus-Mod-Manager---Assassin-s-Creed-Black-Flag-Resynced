"""Run all offline regressions without overwriting existing test fixtures or user data."""
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    tools = Path(__file__).resolve().parent
    sys.path.insert(0, str(tools))
    isolated = {"test_loader", "test_loader_loose", "test_loader_outfits", "test_decoded_resource"}
    count = 0
    for path in sorted(tools.glob("test_*.py")):
        print(f"Running {path.name}", flush=True)
        if path.stem in isolated:
            module = importlib.import_module(path.stem)
            with tempfile.TemporaryDirectory(prefix="animus-regression-") as raw:
                module.TEST_ROOT = Path(raw) / "fixture"
                module.GAME_DIR = module.TEST_ROOT / "game"
                module.MODS_ROOT = module.TEST_ROOT / "mods"
                if hasattr(module, "FORGE"):
                    module.FORGE = module.GAME_DIR / "DataPC_boot.forge"
                if module.main() not in (None, 0):
                    raise RuntimeError(f"Failed: {path.name}")
        else:
            subprocess.run([sys.executable, str(path)], check=True, cwd=tools.parent)
        count += 1
    print(f"PASS: {count} regression suites (temporary synthetic game data only).")


if __name__ == "__main__":
    main()
