# Changelog

## 0.1.7 Beta — 2026-09-03

- Added an Animus-styled sail-target picker during sail installation so users
  can choose which vanilla sail cosmetic a custom design replaces.
- Added 45 game-validated sail targets from the current Title Update 1.0.7
  archive, including advanced emblem layers.
- Multiple sail designs can remain installed and enabled when assigned to
  different targets; designs assigned to the same target use the existing
  conflict warning and replacement workflow.
- Sail updates now retain their previously selected vanilla target.
- Kept Jackdaw Drydock Studio's separate-slot hull/sail injection system fully
  independent; Animus continues to use reversible vanilla replacements.

## 0.1.6 Beta — 2026-09-03

- Added a dedicated Sails tab with install, update, rename, enable/disable,
  uninstall, Nexus metadata, and restore-to-vanilla workflows.
- Added vanilla sail replacement labels and shared-slot detection, including
  disabled designs that still occupy the same sail slot.
- Added the outfit-style conflict prompt so enabling or installing a competing
  sail design can disable the active design before deployment.
- Added managed general texture replacements to the Mods tab for ship assets
  that do not belong to the dedicated outfit, weapon, crew, or sail views.
- Added category validation that redirects confidently identified texture
  packs to the correct tab instead of deploying them under the wrong system.
- Added a reviewed legacy mapping for the Black Cannons mod's five recommended
  Gold Jackdaw weapon targets, removing its Ship Workshop dependency.
- Added compatibility mappings for established Sail Workshop-style PNG names,
  including Black Striped Sails BF Logo, which now targets the Jackdaw-only Red
  Striped Sails slot without requiring material IDs in the archive filename.
- Verified all mapped outfit, weapon, crew, sail, and ship-texture targets
  against Title Update 1.0.7 (Steam build 24833802). Stale material pointers
  from a replaced game archive are now retired safely before enabled packs are
  rebuilt against the updated FORGE layout.

## 0.1.5 Beta — 2026-09-03

- Replaced the retired personal-key and Nexus SSO integration with public,
  unauthenticated Nexus GraphQL metadata lookups.
- Removed direct Nexus file-download code; downloads remain in the user's
  browser and updates are installed from a selected local archive.
- Corrected the Black Flag Resynced Nexus game identifier to 9408.
- Added release auditing that rejects legacy Nexus credentials, authentication
  endpoints, or direct-download code before a Nexus package can be created.
- Added reversible multi-proxy DLL chaining for documented secondary aliases,
  including Walk By Default's `version.dll` → `wininet.dll` compatibility rule.
- Made supported custom-proxy chaining independent of installation order and
  improved Ultimate ASI Loader identification.

## 0.1.4 Beta — 2026-08-29

- Renamed the application to **Animus Mod & Outfit Manager** across the native
  window, interface, splash screen, installer, shortcuts, and documentation.
- Made the footer version load automatically from the packaged release version
  instead of requiring a separate hard-coded UI edit.

## 0.1.3 Beta — 2026-08-29

- Added conventional mod installation from RAR, 7z, TAR, and TGZ archives in
  the normal Mods tab using the same safe extraction and backup workflow.
- Added managed `videos/*.webm` replacement support for intro-skip and other
  game-root video packages, including complete restoration on disable/remove.
- Cleaned Nexus transport metadata from automatically detected mod names.
- Fixed large loose-file and video mods duplicating backup data into the
  installed-state file, which could block game detection, mod loading, and
  complete uninstall operations.
- Added automatic bounded-memory repair for state files created by the affected
  build; existing packages and backup files are preserved.

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
