"""Read-only ZIP integrity/source audit. Not an antivirus scan or Nexus approval.
Usage: py -3.14 tools/audit_release.py APPLICATION.zip SOURCE.zip SOURCE_ROOT
"""
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
import sys
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(path, app):
    issues, files, roots = [], {}, set()
    with zipfile.ZipFile(path) as z:
        for entry in z.infolist():
            name = entry.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or ".." in parts or ":" in name:
                issues.append("Unsafe path: " + name)
                continue
            roots.add(parts[0])
            if entry.is_dir():
                continue
            if entry.flag_bits & 1:
                issues.append("Encrypted entry: " + name)
                continue
            relative = "/".join(parts[1:])
            if relative in files:
                issues.append("Duplicate entry: " + relative)
            files[relative] = z.read(entry)  # Validates each CRC.
    if len(roots) != 1:
        issues.append("Expected one top-level folder")
    binaries, authored = [], {}
    for name, data in files.items():
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".whl", ".npz"} or data.startswith((b"PK\x03\x04", b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07")):
            issues.append("Nested archive: " + name)
        if data.startswith(b"MZ") or suffix in {".exe", ".dll", ".pyd", ".asi"}:
            binaries.append(name)
        if app and (name.startswith("mods/") or suffix in {".bat", ".cmd", ".ps1", ".vbs", ".hta", ".asi"}):
            issues.append("Unexpected user data or executable script: " + name)
        if name.startswith(("tools/Animus_loader/", "desktop/")) and suffix in {".py", ".js", ".html", ".css", ".cs", ".csproj"}:
            authored[name] = sha(data)
            for marker in ("nexus_api_key", "nexus_key.json", "api.nexusmods.com", "graphql.nexusmods.com", "sso.nexusmods.com"):
                if marker in data.decode("utf-8-sig", errors="replace").lower():
                    issues.append("Retired API marker " + marker + ": " + name)
    if app:
        inventory = files.get("SHA256SUMS.txt", b"")
        expected = {name: checksum.lower() for checksum, name in
                    (line.split("  ", 1) for line in inventory.decode("utf-8-sig").splitlines())}
        actual = {name: sha(data) for name, data in files.items() if name != "SHA256SUMS.txt"}
        issues.extend("Checksum mismatch: " + name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
    elif binaries:
        issues.append("Compiled binaries in source archive")
    return dict(path=str(path.resolve()), sha256=sha(path.read_bytes()), files=len(files),
                binary_counts=dict(Counter(PurePosixPath(p).suffix.lower() for p in binaries)),
                executables=[p for p in binaries if p.endswith(".exe")], issues=issues), authored


def main():
    app, app_code = inspect(Path(sys.argv[1]), True)
    source, source_code = inspect(Path(sys.argv[2]), False)
    root = Path(sys.argv[3])
    mismatch = [name for name, value in app_code.items() if source_code.get(name) != value]
    working = [name for name, value in source_code.items() if not (root / name).is_file() or sha((root / name).read_bytes()) != value]
    passed = not (app["issues"] or source["issues"] or mismatch or working)
    print(json.dumps(dict(application=app, source=source, application_source_mismatches=mismatch,
                          working_source_mismatches=working, passed=passed), indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
