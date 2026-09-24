"""Preflight and transactional installation of verified Anvil patch packages.

PNG editing and native patch building are separate stages. Never install loose
PNGs, the old ASI staging hook, or an unverified slot candidate as a finished mod.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

APP = Path(__file__).resolve().parents[1]
BUILD_107 = "614dab4a20a5d5c6256792e1daa6d05669c97a751079b10df1725d6965ad766d"
EXE_BYTES_107 = 469524824


def digest(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def local_file(root, relative):
    if not relative or Path(relative).is_absolute():
        raise ValueError("Expected a relative package path")
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Missing or unsafe package file: {relative}")
    return path


def game_running():
    if os.name != "nt":
        return False
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True)
    return any(f'"{name}"' in result.stdout.lower() for name in ("acblackflag.exe", "acblackflag_plus.exe"))


def find_toolkit():
    # Explicit configuration takes precedence over automatic discovery.
    settings = APP / "user-data" / "anvil-toolkit-path.txt"
    candidates = [Path(settings.read_text().strip())] if settings.is_file() else []
    candidates += sorted((Path.home()/"Documents").glob("AnvilToolkit*1.3.7*"))
    return next((str(p.resolve()) for p in candidates if (p/"AnvilToolkit.dll").is_file() and (p/"AnvilToolkit.exe").is_file()), None)


def preflight(design, game, support, running=None):
    design, game = Path(design), Path(game)
    problems = []
    exe = game / "ACBlackFlag.exe"
    if not exe.is_file() or not (game/"DataPC_boot.forge").is_file():
        problems.append("Select the installed Black Flag Resynced folder.")
    elif exe.stat().st_size != EXE_BYTES_107 or digest(exe) != BUILD_107:
        problems.append("This executable differs from the inspected 1.0.7 build.")
    if running if running is not None else game_running():
        problems.append("Close the game before installing a design.")
    if not support.get("slot_verified"):
        problems.append("The new hull cosmetic entry still needs in-game equip and save/reload verification on 1.0.7.")
    if not support.get("texture_routing_verified"):
        problems.append("Routing edited finishes into the isolated hull appearance is not yet verified.")
    document = design / "design.jackdaw.json"
    if not document.is_file():
        problems.append("Save a Studio design first.")
    else:
        doc = read_json(document)
        if doc.get("schema") != 1:
            problems.append("Unsupported design format.")
        elif not doc.get("entries"):
            problems.append("The saved design has no edited finishes.")
        metadata = APP/"user-data"/"ship-preview"/"native-current-metadata.json"
        if metadata.is_file() and doc.get("model_sha256") != read_json(metadata).get("source_sha256"):
            problems.append("Save the design with the current model before building its patch.")
        for entry in doc.get("entries", []):
            local_file(design, entry["output"])
    package = design/"exports"/"anvil"/"install-package.json"
    if not package.is_file():
        problems.append("A native Anvil patch package has not been built for this design.")
    return dict(status="blocked" if problems else "ready", game_version="1.0.7", toolkit=find_toolkit(),
                reasons=problems, package=str(package), game_files_changed=False)


def validate_package(package_path, design, game, support):
    if not support.get("slot_verified") or not support.get("texture_routing_verified"):
        raise ValueError("Native slot and texture routing have not passed validation")
    package_path, design, game = Path(package_path), Path(design), Path(game)
    manifest = read_json(package_path)
    if manifest.get("format") != "jackdaw-anvil-patch-v1" or manifest.get("builder_revision") != support.get("builder_revision"):
        raise ValueError("Unsupported patch builder")
    if manifest.get("game_sha256") != BUILD_107 or digest(game/"ACBlackFlag.exe") != BUILD_107:
        raise ValueError("Patch and installed game builds do not match")
    if manifest.get("design_sha256") != digest(design/"design.jackdaw.json"):
        raise ValueError("Design has changed since the patch was built")
    assets = manifest.get("design_assets", [])
    expected_assets = {entry["output"] for entry in read_json(design/"design.jackdaw.json")["entries"]}
    if {entry["path"] for entry in assets} != expected_assets:
        raise ValueError("Patch does not cover the current design finishes")
    for entry in assets:
        if digest(local_file(design,entry["path"])) != entry["sha256"]:
            raise ValueError("An edited PNG has changed since patch creation")
    files = []
    seen = set()
    for entry in manifest.get("patches", []):
        target = entry["target"]
        if not re.fullmatch(r"DataPC_[A-Za-z0-9_]+_patch_\d{2,}\.forge", target) or target in seen:
            raise ValueError("Invalid or repeated patch destination")
        seen.add(target)
        source = local_file(package_path.parent, entry["path"])
        with source.open("rb") as header:
            magic = header.read(8)
        if digest(source) != entry["sha256"] or magic != b"scimitar":
            raise ValueError("Patch content is invalid or has changed")
        if (game/target).exists():
            raise ValueError(f"{target} already exists; rebuild against the current patch chain")
        parent = local_file(game, entry["parent"])
        if digest(parent) != entry["parent_sha256"]:
            raise ValueError("A parent archive has changed; rebuild the patch")
        files.append((source, game/target, entry["sha256"]))
    if not files:
        raise ValueError("Patch package is empty")
    return files


def install(package, design, game, support, running=None):
    if running if running is not None else game_running():
        raise ValueError("The game is running; installation was not started")
    files = validate_package(package, design, game, support)
    transaction = Path(design)/"exports"/"anvil"/"transactions"/uuid.uuid4().hex
    transaction.mkdir(parents=True, exist_ok=False)
    record = dict(status="installing", game=str(Path(game).resolve()), files=[])
    journal = transaction/"transaction.json"
    def save():
        temporary = journal.with_suffix(".tmp")
        temporary.write_text(json.dumps(record,indent=2)+"\n")
        os.replace(temporary,journal)
    created = []
    save()
    try:
        for source, target, checksum in files:
            # Journal first, and exclusive create: never overwrite another mod.
            record["files"].append(dict(name=target.name, sha256=checksum))
            save()
            with target.open("xb") as dest:
                created.append(target)
                with source.open("rb") as src:
                    shutil.copyfileobj(src,dest)
            if digest(target) != checksum:
                raise ValueError("Installed patch failed verification")
        record["status"]="installed"
        save()
    except Exception:
        for target in reversed(created):
            target.unlink()
        record["status"]="rolled-back-after-error"
        save()
        raise
    return dict(status="installed", transaction=str(journal), game_files_changed=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "install"])
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--game", required=True, type=Path)
    args=parser.parse_args()
    try:
        support=read_json(APP/"tools"/"anvil-support.json")
        result=preflight(args.design,args.game,support)
        if args.action == "install" and result["status"] == "ready":
            result=install(result["package"],args.design,args.game,support)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps(dict(status="error",reasons=[str(exc)],game_files_changed=False)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
