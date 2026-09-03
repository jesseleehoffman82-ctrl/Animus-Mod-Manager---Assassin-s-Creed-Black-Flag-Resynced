# Changelog

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
