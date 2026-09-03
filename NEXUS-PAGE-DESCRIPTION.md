# Animus Mod & Outfit Manager

## Mods, outfits, weapons and crew textures in one manager

**Animus Mod & Outfit Manager** is a portable mod-management tool built specifically
for **Assassin's Creed IV: Black Flag Resynced**. It provides one place to
install and manage general mods, outfit replacements, weapon skins and custom
crew textures—with reversible deployment, backups and outfit-slot conflict
detection.

This project was created because Black Flag's growing mod scene needed a
dedicated manager, especially for players who use several outfit replacements
and do not want to depend on Outfit Workshop for installation.

> **Public beta:** Version 0.1.5 Beta is an early testing release. Keep the
> game closed while Animus is changing files, retain the included backup
> folders and report any failed installation with the activity-log text.

---

## Main features

- Dedicated **Mods**, **Outfits**, **Weapons** and **Crew** libraries.
- Persistent enable/disable state across manager restarts.
- Installs supported ordinary Nexus ZIP mods even when `manifest.json` is not
  supplied, provided the archive has a layout Animus can identify safely.
- Imports outfit, weapon and crew texture packs from **ZIP, RAR, 7Z, TAR, DDS
  and PNG** sources.
- Automatically extracts nested folders inside downloaded texture archives.
- Shows the **vanilla outfit replaced** by each installed outfit when that
  information can be detected.
- Detects outfits assigned to the same vanilla wardrobe slot.
- Lists every outfit sharing a slot, including disabled alternatives.
- Before installing or enabling a conflicting outfit, offers to disable every
  enabled replacement already using that slot.
- Displays mod/outfit author, version, target count and available metadata.
- Rename managed entries without changing their installed identity.
- Update an item by selecting a replacement archive; Animus replaces the
  managed copy while preserving supported metadata.
- Open managed folders, view details, link a Nexus page and visit it directly.
- Game-folder detection, manual browsing and built-in game launch button.
- Manages compatible `version.dll` combinations instead of silently
  overwriting them. It shares Ultimate ASI Loader copies, supports its
  `versionHooked.dll` chain, and applies documented secondary aliases such as
  Walk By Default's `wininet.dll` rule in either installation order.
- Blocks two genuinely incompatible custom proxies without changing the game
  folder and explains why they cannot safely run together.
- Compact native Windows interface with an activity log and an unobtrusive
  in-game **MODS & OUTFITS LOADED** confirmation.

---

## Outfit management without Outfit Workshop

**Outfit Workshop is not required to install outfits with Animus Mod
Manager.** Players who already use Outfit Workshop may continue to do so, but
it is an optional tool rather than a dependency for Animus's outfit workflow.

Animus includes its own texture-pack pipeline. Outfit archives are extracted,
their texture targets are validated against the installed game and the
selected replacement is applied through Animus's managed deployment system.
Animus **patches the corresponding vanilla outfit resources; it does not
inject an outfit at runtime**. Outfit mods therefore replace an existing
Edward outfit slot rather than adding a completely new wardrobe slot. The
manager records the affected files, keeps recovery backups and can rebuild the
enabled outfit set when a replacement is switched or disabled.

Multiple outfit mods may remain installed as alternatives. Only the selected
replacement for a shared vanilla outfit slot should be enabled. If two packs
target Duncan Walpole's outfit, for example, Animus identifies the shared slot,
shows both packs in the library and asks before switching the active
replacement.

Disabling an outfit does **not** uninstall it. It stays in the list and can be
enabled again later.

---

## Reversible deployment and backups

Animus records the files and texture writes it manages. Original data is
backed up so the enabled set can be rebuilt or restored instead of forcing the
user to remember which archive overwrote which file.

- General mods remain in the managed library when disabled.
- Texture changes are journaled and backed up.
- **Restore Vanilla** is available for managed texture categories.
- Uninstalling removes the managed item and rebuilds the remaining enabled
  deployment.

Do not manually delete `mods/backups` or `mods/textures/backups` while managed
changes are deployed.

---

## Installation

1. Download the main beta ZIP.
2. Extract the **entire folder** somewhere writable. Do not run the manager
   from inside the ZIP and do not extract it directly into the game folder.
3. Run `AnimusModManager.exe`.
4. Select **Detect**, or use **Browse** to choose the folder containing
   `ACBlackFlag.exe`.
5. Keep the game closed while installing, enabling, disabling, updating,
   removing or restoring files.

The download is portable and includes its required Python and .NET runtimes.
Users do not need to install Python or the .NET SDK. Microsoft Edge WebView2
Runtime is required and is normally present on supported Windows 10/11
systems.

The archive is larger than a simple script because those portable runtimes are
included deliberately.

---

## Installing content

### General mods

Open the **Mods** tab, choose **Install Mod**, then select a supported `.jmod`
or `.zip` archive. Animus uses a package manifest when one is provided and can
import supported ordinary loose-file Nexus archives when their destination can
be inferred safely.

### Outfits, weapons and crew textures

Open the relevant category, select its install button and choose the downloaded
archive or texture. Animus supports ZIP, RAR, 7Z and common texture-pack forms.
If a new outfit shares a vanilla slot with enabled outfits, review the listed
conflicts and choose whether to disable them before continuing.

### Updating an installed item

Open the item's `...` menu and select **Update**. During this beta, the update
workflow asks for the newer archive on your computer and replaces the managed
version. Direct Nexus downloads are planned but are not enabled until Nexus
integration is approved.

---

## Current beta limitations

- This is an **unsigned beta executable**. Windows SmartScreen or antivirus
  software may warn about a new, low-reputation application. Verify the
  SHA-256 checksum shown on the Files page and download only from this page.
- Direct downloads through Nexus are not yet enabled.
- Metadata quality depends on the archive. Author, version, Nexus page or the
  vanilla replacement name may show as unknown when the download provides no
  usable information.
- Automatic archive importing is intentionally conservative. A mod with an
  ambiguous layout may need a proper Animus manifest rather than guessing at a
  dangerous destination.
- PNG conversion supports the formats currently handled by the built-in
  texture pipeline. Some slots require a game-ready DDS.
- The game must remain closed while managed files are being patched or
  restored.
- This first beta targets **64-bit Windows** and Black Flag Resynced.

---

## Guidance for mod authors

Animus works best when an archive has one clear root and preserves the same
relative paths expected under the game directory. Avoid bundling unrelated
optional variants into the same archive unless they are clearly separated.

For the best library information, include:

- mod name;
- author;
- version;
- short description;
- Nexus mod ID or page;
- the vanilla outfit/weapon/crew target, when applicable;
- explicit destination paths for loose files.

An Animus `manifest.json` is recommended for complex mods, patches or archives
whose destination cannot be determined safely. Simple supported archives can
still be imported without one.

---

## Reporting a beta issue

Please include:

- the archive name and its Nexus page;
- the exact activity-log message;
- whether you were installing, enabling, disabling, updating or removing;
- whether the game was running;
- your game build/store version;
- a screenshot when the problem is visual.

Do not upload copyrighted game archives, full game files or personal Nexus
credentials with a report.

---

## Credits and legal notice

Animus Mod & Outfit Manager is a community-created project and is not affiliated with
or endorsed by Ubisoft or Nexus Mods. Assassin's Creed and related names and
imagery belong to their respective owners. Included third-party runtime
components retain their own licenses, which are supplied with the download.

Thank you to the Black Flag Resynced modding community and the authors testing
new formats while the scene continues to grow.
