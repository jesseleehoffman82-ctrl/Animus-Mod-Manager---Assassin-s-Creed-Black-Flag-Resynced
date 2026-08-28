# Animus Mod Manager — Public Beta

Version 0.1.2 Beta for Windows x64

Animus Mod Manager manages mods, outfit replacements, weapon textures, and
crew textures for Assassin's Creed IV: Black Flag Resynced. This is an early
public test build. Keep backups and report the activity-log text when a test
fails.

## Install

1. Extract the entire ZIP to a normal writable folder. Do not run it from
   inside the ZIP or place it in the game directory.
2. Run `AnimusModManager.exe`.
3. Use **Detect**, or browse to the folder containing `ACBlackFlag.exe`.
4. Keep the game closed while installing, enabling, disabling, updating, or
   removing mods and texture packs.

The beta is portable. It includes its Python runtime and does not need the .NET
SDK or a separate Python installation. Microsoft .NET 10 Desktop Runtime (x64)
is required. Microsoft Edge WebView2 Runtime is also required and is normally
already installed on supported Windows 10/11 systems.

Official .NET 10 download:
https://dotnet.microsoft.com/en-us/download/dotnet/10.0

## Outfit conflicts

Only one replacement for a vanilla outfit slot should be enabled. When a new
outfit shares a slot, Animus lists all enabled conflicts and offers to disable
them before continuing. Disabled alternatives stay installed and remain shown
in the shared-slot hover information.

## Recovery

- Use the relevant enable/disable control to rebuild the deployed set.
- Use **Restore Vanilla** in a texture category when its deployed files need
  to be restored.
- Do not delete the `mods/backups` or `mods/textures/backups` folders while
  changes are deployed.
- Include `mods/animus-native-shell.log` and the visible activity log when
  reporting a failure. Never publish a Nexus API credential with a report.

## Beta limitations

- This release is unsigned. Windows SmartScreen or antivirus software may
  warn about a new, low-reputation executable. Verify the SHA-256 checksum
  before running it. Do not download builds from unofficial mirrors.
- Direct Nexus downloads are not enabled until Nexus approves the application.
- Some archives do not provide author, version, Nexus, or replacement-slot
  metadata; Animus uses safe detection and displays unknown fields when needed.
- PNG conversion supports the formats currently handled by the built-in
  texture pipeline. Some texture slots require a game-ready DDS.
- The game must remain closed while files are being patched or restored.

## Reporting a beta issue

Please include:

- the mod/outfit archive name and its Nexus page;
- the exact activity-log message;
- whether the item was installing, enabling, disabling, updating, or removing;
- whether the game was running;
- the game build/store version.

Do not upload copyrighted game archives, personal Nexus credentials, or full
game files with a report.
