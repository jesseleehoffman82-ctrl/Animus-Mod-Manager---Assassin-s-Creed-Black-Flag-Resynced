# Animus Mod & Outfit Manager

Standalone mod loader project for Assassin's Creed IV: Black Flag Resynced.

This folder is intentionally separate from `jackdaw-workshop` so the mod loader can become its own app, package format, and installer without tangling it with the ship preview/editor prototype.

## Current Contents

```text
jackdaw-mod-loader/
  README.md
  mods/
    LOADER_APP_SPEC.md
    README.md
    backups/
    installed/
    packages/
    schema/
    source/
  tools/
    jmod.py
```

## Desktop interface

Run `Start-Animus-Mod-Manager.cmd` to open the current HTML/CSS/JavaScript
interface in its native .NET WebView2 window. The native host runs backend
operations in isolated Python worker processes, so Python never owns or blocks
the desktop message loop. Mod installation logic remains in the tested backend
modules.

## First Goal

Build a small Lenny's Mod Loader-style app:

- scan `.jmod` packages
- validate manifests
- show conflicts and load order
- keep game files untouched until Apply
- dry-run FORGE installs
- backup and restore originals
- revalidate mods after game updates

## Current Resynced Reality

Resynced does not have official AnvilToolkit support yet, and the public modding scene is still young. The loader should not assume every mod is a texture mod.

V1 should support several practical mod types:

- FORGE resource mods when the replacement is already game-ready
- loose-file mods copied into known game folders
- compatible proxy-DLL chains where the loader or mod author documents a safe
  secondary filename (`versionHooked.dll` or `wininet.dll`)
- reversible config patches
- save/profile utilities
- runtime-assisted mods later, after stable signatures are mapped

The key rule is that v1 should not require AnvilToolkit.

`version.dll` is a single Windows loader entry point, so Animus never merges
arbitrary DLL binaries. Identical/Ultimate ASI Loader copies are shared. A
custom proxy can coexist when Ultimate ASI Loader or the mod's documented
installation rule provides a secondary filename; otherwise Animus blocks the
second proxy without overwriting the active one.

## Companion Project

Runtime hook research now lives beside this loader:

```text
../resynced-script-hook/
```

The loader should eventually install or manage the hook, but the native hook stays separate so file-based mod installs and runtime modding can evolve independently.

## Helper Commands

```powershell
python .\tools\jmod.py validate .\mods\source\01-jackdaw-cosmetic-pack
python .\tools\jmod.py pack .\mods\source\01-jackdaw-cosmetic-pack
python .\tools\jmod.py inspect .\mods\packages\Example-1.0.0.jmod
```

## Outfit & Weapon Manager

The loader includes a built-in **Texture Manager** for outfit and weapon skins
(the OUTFIT MANAGER and WEAPON MANAGER buttons in the GUI, or the `outfit` /
`weapon` CLI commands). It is **completely independent of Outfit Workshop** --
OW never needs to be installed or opened. The manager reads the downloaded
pack's texture files itself and injects them into the game with its own code.

### One-click install

Pick a downloaded pack (`.zip`, `.7z`, `.tar`, single `.dds`/`.png`, or an
extracted folder) and the manager imports it **and activates it** in one step -
no manual texture mapping, no running OW. Packs that ship textures nested in
subfolders are found automatically.

How it works:

- An outfit or weapon skin is a folder of texture files named with a material
  id + slot (e.g. `hood_0x22D90B0A877_slot1_mask.dds`). DDS are used as-is;
  PNG are re-encoded to the slot's BC format (BC1/BC3) with a full mip chain.
- Importing copies the textures into `mods/textures/<pack-id>/` and validates
  each one against the actual `DataPC_boot.forge` slot (size, format family,
  colour space).
- **Outfits and weapons each have their own tab/list.** Many packs can be
  **enabled** at once (tick the ON column), the list is **reorderable** (MOVE
  UP / MOVE DOWN), and **APPLY CHANGES** merges all enabled packs in a tab into
  one injected set. When two enabled packs touch the same forge slot, the
  **bottom-most pack wins** and a conflict is logged. This is the MO2/Lenny's
  model: toggles are independent of order, and apply is explicit (nothing
  touches the game until you click APPLY CHANGES).
- **RESTORE TO VANILLA** reverts whatever is currently injected, byte-for-byte.
- Injection writes external texture mips in place and re-packs the embedded
  mip tail by appending the material and repointing its TOC entry. Every write
  is journaled with byte backups (`mods/textures/journal.json` + `backups/`),
  so the active set can always be reverted to vanilla.

CLI:

```powershell
python .\tools\Animus_loader\cli.py outfit install .\path\to\outfit.zip
python .\tools\Animus_loader\cli.py weapon install .\path\to\weapon.7z
python .\tools\Animus_loader\cli.py outfit enable <id> on --apply
python .\tools\Animus_loader\cli.py outfit enable <id> off
python .\tools\Animus_loader\cli.py outfit order <id1>,<id2>,<id3>   # bottom wins
python .\tools\Animus_loader\cli.py outfit apply
python .\tools\Animus_loader\cli.py outfit list|import|switch|revert|status
python .\tools\Animus_loader\cli.py weapon enable <id> on --apply
python .\tools\Animus_loader\cli.py weapon apply
python .\tools\Animus_loader\cli.py outfit revert   # restore vanilla

# Nexus metadata links
python .\tools\Animus_loader\cli.py mod-set-nexus "<mod-name>" <mod-id>
python .\tools\Animus_loader\cli.py mod-check-updates
python .\tools\Animus_loader\cli.py outfit set-nexus <pack-id> <mod-id>
python .\tools\Animus_loader\cli.py outfit check-updates
```

Notes / limits:

- Requires the game's `oo2core_*_win64.dll` (present in the game folder) for
  Oodle compression.
- BC7 (normal/surface) slots need a ready DDS; PNG can only encode BC1/BC3.
- Keep the game closed while applying/reverting.
- The outfit tab's enabled set and the weapon tab's enabled set are each
  applied independently. If you happen to enable an outfit and weapon that
  touch the *identical* forge slot, the two Apply presses each take effect for
  their own category (last apply wins) -- the visible "current applied state"
  is whatever you applied most recently.

## Nexus metadata and update checks

The manager can check whether a `.jmod` mod or an outfit/weapon pack has a
newer version on Nexus, like MO2's "Mod Update Check". It reads public mod
metadata through the Nexus Mods GraphQL endpoint. No Nexus login, API key, or
account credential is requested or stored.

To use it:

1. Link each mod/pack to its Nexus mod id:
   - `.jmod` mods: `cli.py mod-set-nexus "<mod-name>" <mod-id> --version <installed>`
     (or add a `nexus: { game_id, mod_id }` block to the manifest).
   - outfit/weapon packs: `cli.py outfit set-nexus <pack-id> <mod-id> --version <installed>`
2. Use the item's Nexus action or update check to view its public metadata and
   open its mod page.
3. Download updates manually in your browser, then choose **Update Mod** in
   Animus and select the downloaded archive.
   Texture Manager (for packs) -- items whose installed version is older than
   the Nexus latest are flagged.

Only mods/packs that have a Nexus id are checked; others are skipped. The game
id is Assassin's Creed IV: Black Flag Resynced's Nexus id (9408). Metadata
requires network access; installing and managing local archives works offline.
