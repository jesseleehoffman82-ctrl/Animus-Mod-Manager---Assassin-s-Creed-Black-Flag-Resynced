# Jackdaw Drydock Studio — prototype source

**Early development snapshot · 24 September 2026 · GPL-3.0-only**

This is the authored source for the Jackdaw Drydock Studio prototype, a 3D ship customization companion to Animus Mod & Outfit Manager. It is published for inspection, development, and contribution. **It is not a ready-to-run public application.**

## Current work

The development build has demonstrated a 3D ship preview, surface selection, PNG import and reload, experimental painting and undo, saved designs, adjustable preview lighting, and warm lantern lights. Material assignments, cabin/window appearance, UV mapping, and selection behavior still need correction.

A verified workflow to rebuild the Jackdaw from a fresh game installation and install a customized ship is **not complete**. Cosmetic-slot experiments are not validated for public use. The included Anvil support flags remain false; do not enable them to bypass missing validation.

## Source layout

- `app/*.ps1` and `app/window_layout.xaml`: Windows desktop interface, preview integration, design editing, and workflow code.
- `app/high-detail-viewer/`: authored JavaScript viewer, surface painting, lighting, and sail motion.
- `app/tools/`: format conversion, extraction adapter, and experimental installation checks.
- `app/tests/`: offline transaction and validation tests with temporary fixtures.
- `tools/anvil-bridge/`: .NET helper using a separately installed AnvilToolkit through reflection.
- `SOURCE-MANIFEST.json`: file hashes for the 36 staged source/configuration files.

See [BUILDING.md](BUILDING.md) for checks, dependencies, and missing pieces.

## Included and excluded

This snapshot includes the application modules and standalone helper source. It excludes third-party distributions, extracted or assembled game models, textures, native archive payloads, developer caches, saved designs, research dumps, and experimental patch binaries. It also excludes the private development workspace's historical assembly/audit scripts.

No model or texture is embedded in this source snapshot. Six historical personal-path occurrences were replaced with `C:\Users\YOUR_USER` placeholders. Legacy Windows text encodings were normalized to UTF-8 in this copy. The working development app was not modified.

The current UI still expects dependencies and local generated files that are intentionally absent. Publishing the source does not make the clean-install reconstruction workflow complete.

## Validation of this snapshot

- 19 Python fixture tests passed.
- Published PowerShell modules passed syntax parsing.
- Viewer JavaScript modules passed syntax checking.
- The .NET bridge compiled with zero warnings and zero errors.
- No application launch or live game installation was performed.

These checks validate source syntax and isolated transaction behavior, not model fidelity or game compatibility.

## License

Copyright (C) 2026 Jesse Hoffman.

The original Drydock source in this directory is licensed under the GNU General Public License version 3 only (`GPL-3.0-only`). See [LICENSE](LICENSE). It is provided without warranty, to the extent permitted by law.

Third-party dependencies retain their own terms; see [DEPENDENCIES.md](DEPENDENCIES.md). Game assets, logos, and imagery are not relicensed by this source publication. Unpublished files outside this snapshot are not covered by this grant.

Independent fan project; not affiliated with or endorsed by Ubisoft. Development is human-directed and AI-assisted.
