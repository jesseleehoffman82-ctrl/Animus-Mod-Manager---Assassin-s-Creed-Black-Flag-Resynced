# Animus Mod Manager

Animus Mod Manager is a lightweight mod manager inspired by Mod Organizer 2
and developed specifically for **Assassin's Creed IV: Black Flag Resynced**.
It manages gameplay mods, outfit replacements, weapon textures, and crew
appearances from one local Windows application.

This repository contains the complete authored source corresponding to
**Animus Mod Manager 0.1.2 Beta** and is published for transparency, security
review, and reproducible inspection of the Nexus Mods release.

## Architecture

- **C# / .NET 10 Windows Forms** provides the native desktop host, splash
  screen, window behavior, and local RPC bridge.
- **Microsoft Edge WebView2** renders the local HTML/CSS/JavaScript interface.
- **Python 3.14** implements archive inspection, managed deployment,
  backup/restoration, metadata handling, and outfit-slot conflict management.
- **7-Zip** supports ZIP, 7Z, and RAR package extraction.
- **Microsoft DirectXTex** supports documented texture conversion operations.

Animus patches and restores selected game files on disk while the game is
closed. The manager itself does **not** inject code into the running game
process, install a service, create a scheduled task, or modify Windows security
settings. Direct Nexus downloading and Nexus account authorization are not
enabled in this beta.

## Source layout

- `desktop/` — native .NET 10 application host
- `tools/Animus_loader/` — Python backend and local interface
- `tools/test_*.py` — regression tests
- `installer/` — optional Inno Setup definition
- `BUILDING.md` — complete build and verification instructions
- `DEVELOPMENT-NOTES.txt` — development history and architecture notes
- `THIRD-PARTY-NOTICES.md` — third-party component attribution

## Build and verification

See [BUILDING.md](BUILDING.md) for exact prerequisites, dependency placement,
test commands, public publishing commands, and release verification.

## Nexus release

- Nexus Mods page: https://www.nexusmods.com/assassinscreedblackflagresynced/mods/458
- Release version: `0.1.2-beta`
- Submitted application SHA-256:
  `f44a7b1bd2ebf765d0c442945c68417f1d4626cdc6f13885b25a4bb81e494546`

Generated releases, embedded runtimes, third-party compiled utilities,
personal mod libraries, backups, caches, credentials, and build outputs are
not committed to the browsable source tree.
