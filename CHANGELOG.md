# Changelog

## 0.1.2 Beta — 2026-08-27

- Migrated the native desktop host to the .NET 10 Desktop Runtime.
- Changed public publishing to framework-dependent deployment, removing the
  bundled Microsoft .NET runtime files.
- Added a matching source-review package and reproducible build instructions
  for distribution safety review.
- Preserved the shared outfit-slot cancellation fix and Windows 11 rounded
  corners from the previous build.

## 0.1.1 Beta — 2026-08-27

- Consolidated the splash screen and manager into one application executable.
- Simplified the portable release layout for clearer security scanning and review.
- Retained the native interface, bundled backend, archive support, and managed mod library.

## 0.1.0-beta.1 — 2026-08-23

- Native Animus-themed Windows interface with resizable compact layout.
- Managed mod installation, enable/disable, update, rename, details, and
  uninstall workflows.
- ZIP/RAR/7Z outfit, weapon, and crew texture-pack installation.
- MO2-style persistent managed library with reversible deployment and backups.
- Vanilla outfit replacement labels, authors, Nexus links, and shared-slot
  detection.
- Shared outfit-slot confirmation that disables all enabled alternatives
  before activating a replacement.
- Automatic ordinary Nexus archive import when `manifest.json` is absent.
- Compatibility handling for supported `version.dll` proxy combinations.
- Portable preloader and in-game loaded-mod confirmation.
