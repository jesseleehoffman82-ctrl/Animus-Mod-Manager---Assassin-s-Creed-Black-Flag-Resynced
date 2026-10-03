# Changelog

## 0.1.7 Beta â€” refreshed 2026-10-03

- Disable and uninstall now preflight loose-file ownership and restore backups
  before removal. Mid-operation failures restore files and library state.
- Failed outfit/weapon/crew/sail rebuilds no longer silently leave a pack marked
  disabled. Locked package folders do not remove the item from the library.
- Removed texture packs are moved out of the active package directory into
  recovery storage and do not return to the list after restarting.
- Includes the September cannon alpha/target selection and sail override fixes.
- Editable sail PNGs now receive one vertical orientation correction before
  encoding; native DDS imports are unchanged. Texture boundary checks cover
  reviewed sail resources in both base and patch archives.
- Seventeen offline regression suites and packaged-source integrity checks are
  used for this refresh. These are not a guarantee of every mod's compatibility.


## 0.1.7 Beta — cannon PNG alpha repair 2026-09-15

- Reviewed cannon PNG imports now replace RGB colour while retaining the
  original game alpha channel separately at every mip level. Previously an
  opaque editor PNG replaced near-zero cannon alpha with 255.
- Updating an enabled cannon pack reads original pixels from validated restore
  records, not from the already-patched game texture. Update previews use that
  same baseline without deploying anything.
- The fix is scoped to reviewed cannon PNG mappings; explicit DDS imports,
  outfits, sails, crew and normal/surface maps keep their existing behavior.
- Added synthetic original-baseline, damaged-backup and per-mip alpha tests.
  The local Silver Black Cannons set was re-encoded and checked against the
  original alpha data. Visual confirmation in-game is still required.

## 0.1.7 Beta — sail override repair 2026-09-15

- Sail texture deployment now also patches matching resources in installed
  boot patch and renderer archives, which can override the base archive.
- Each archive has its own restore journal and backups. Enabling, disabling,
  uninstalling and failed-install rollback include those sail copies.
- Patch-archive plans are checked before reverting a working deployment;
  missing/incomplete override journals no longer count as fully deployed.
- Added an explicit base-only deployment repair that leaves the base archive,
  installed library, outfits and DLL/ASI mods alone. Do not downgrade to an older
  manager while a multi-archive sail deployment is active: restore it first
  using this version so all archive journals are handled.
- Synthetic deployment/rollback regressions pass; in-game appearance still
  requires equipping the selected vanilla sail cosmetic and checking visually.

## 0.1.7 Beta — cannon-set selection 2026-09-15

- Recognized Black Cannons archives in the Mods tab now prompt for Standard,
  Bronze, Copper, Silver or Gold weapon materials before installation.
- Update Mod also offers the picker, retaining the previous set as its default.
  Use Update Mod to move an existing gold-only install onto your equipped tier.
- The supplied upper/lower cannon, mortar and swivel designs target the selected
  set together. Base/Standard textures may also be shared by NPC ships; the
  picker warns about this. Selecting a set does not equip or buy game upgrades.
- Selected destinations appear in row hover details and installation logs.
- Checked all 25 material/texture plans against the local 1.0.7 archives without
  modifying the game. Actual appearance on each tier still needs gameplay tests.

## 0.1.7 Beta — local update feedback 2026-09-15

- Update Mod now inspects the replacement archive before asking for confirmation
  in a centered, draggable Animus-styled window showing the mod name and
  current → replacement version. Cancelling does not change the installed copy.
- All category tables now show Version and Status. Successful updates retain an
  Updated label, timestamp and version transition across refreshes and restarts.
- Texture packs read versions from JSON, explicit README labels and recognized
  Nexus download filenames. Missing versions are shown as Unknown; reinstalling
  an identical version is identified as a reinstall, not an invented version bump.
- Added offline update-preview and version/status persistence regression coverage.

## 0.1.7 Beta — review refresh 2026-09-14

- Outfit installation still deploys automatically. Validate requested texture
  payloads before restoring the prior deployment; roll back a failed rebuild.
- Texture checkmarks now reflect a completed deployment journal, not only saved
  selections. Missing/incomplete deployments are shown as not deployed.
- Journal texture changes before writing and mark the journal complete only
  after all material updates succeed. Added four deployment regression tests.

- Weapons rejects outfit packs and unidentifiable texture packs before import.
  Archive names, nested folders and replacement metadata remain available to
  category validation for ZIP, RAR and 7z installs.
- Native-manifest ZIP imports are stored as `.jmod` so installed mods remain
  discoverable after refresh/relaunch and can be disabled or uninstalled.
- Normal startup prefers the executable's own application folder over a
  shortcut's working directory, preventing accidental use of an older library.
- Includes journaled appended-resource support for fixed-target crew packages,
  with ownership checks on removal and rollback after a partial install failure.
- Added category, native-ZIP lifecycle and appended-resource rollback regressions;
  a single offline runner isolates generated fixtures in temporary folders.
- Retains Steam-based launch handling for Steam Input. No third-party cheats,
  controller drivers, game files, installed mods or Nexus API integration bundled.
- Allows 45 seconds for Steam/Ubisoft startup and reports an unconfirmed launch
  without claiming the game crashed when it may still be waiting on client setup.

## 0.1.7 Beta — 2026-09-03

- Revalidated executable detection, all ten selectable sail materials, all
  forty crew materials, and the Oodle codec against Resynced Title Update 1.0.7
  (Steam build 24833802).
- Added an Animus-styled sail-target picker during sail installation so users
  can choose which vanilla sail cosmetic a custom design replaces.
- Added 45 game-validated sail targets from the current Title Update 1.0.7
  archive, including advanced emblem layers.
- Multiple sail designs can remain installed and enabled when assigned to
  different targets; designs assigned to the same target use the existing
  conflict warning and replacement workflow.
- Sail updates now retain their previously selected vanilla target.
- Added a Crew target picker with automatic multi-texture pack detection or
  manual assignment to one of 40 validated individual crew textures.
- Crew rows now identify the replaced vanilla texture and show every installed
  pack sharing that target, including disabled packs.
- Rebuilding one texture category now preserves enabled replacements from all
  other tabs in the same complete, journaled FORGE deployment.
- Kept Jackdaw Drydock Studio's separate-slot hull/sail injection system fully
  independent; Animus continues to use reversible vanilla replacements.
- Removed all mod-site metadata, account, update-checking, and direct-download
  integration. Archives are downloaded separately and selected locally.

## 0.1.6 Beta — 2026-09-03

- Added a dedicated Sails tab with install, update, rename, enable/disable,
  uninstall, package details, and restore-to-vanilla workflows.
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

- Removed the retired account-authentication and direct-download implementation;
  updates are installed from a selected local archive.
- Added release auditing that rejects credential, authentication, or download
  code before a public package can be created.
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
- Cleaned download-service transport metadata from automatically detected mod names.
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
- Vanilla outfit replacement labels, authors, package details, and shared-slot
  detection.
- Shared outfit-slot confirmation that disables all enabled alternatives
  before activating a replacement.
- Automatic ordinary archive import when `manifest.json` is absent.
- Compatibility handling for supported `version.dll` proxy combinations.
- Portable preloader and in-game loaded-mod confirmation.
