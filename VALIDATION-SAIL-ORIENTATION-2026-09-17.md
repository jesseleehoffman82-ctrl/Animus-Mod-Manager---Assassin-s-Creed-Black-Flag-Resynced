# Sail design orientation correction

## Evidence

The current Black & White Striped sail pack targets Red Striped Sails,
texture/material `0x22063685111`, slot 0. Its 4096x4096 PNG atlas uses
upright editor orientation. The original game atlas stores the same sail
sections vertically inverted. Installing without converting orientation
places rectangular and triangular sail sections in the wrong UV regions.

Read-only inspection of both DataPC_boot.forge and DataPC_boot_patch_01.forge
confirmed that deployed pixels matched the library DDS. The original 326-byte
resource prefix remained intact. The earlier resource-boundary repair is still
present and was not the cause of this symptom.

## Change

- Sail PNG imports now flip vertically before DDS compression and mip generation.
- Conversion happens once at import, not when enabling or deploying a pack.
- Existing DDS inputs remain byte-for-byte unchanged: they must already use
  game-native orientation. Raw game-oriented PNG exports should be supplied as
  DDS instead of treating them as upright editable sail designs.
- Other categories retain their existing conversion and alpha policies.
- New sail metadata records the conversion policy per texture.
- No mesh, UV coordinates, material headers, launch code or executable changes.

The correction handles orientation; it cannot make an arbitrary image layout
fit a different sail mesh/atlas.

## Validation

`py -3.14 tools/run_regressions.py`: all 17 suites passed, including five new
sail orientation cases, native BC7 encode/decode, DDS passthrough, unchanged
non-sail behavior, and import routing/metadata.

A separate dry-run rebuilt the user's exact original PNG (archive CRC32
7C5BDEFE) and verified the decoded DDS against an independently flipped source:
mean RGB channel error 0.23944 / 255. Both original game resource prefixes are
preserved and the replacement pixels match the corrected DDS exactly.

Installed-app deployment requires Animus and the game to be closed. The targeted
repair retains the pack ID, library/enabled state and original restore journals,
and makes backups before writing. In-game appearance still requires user testing.
