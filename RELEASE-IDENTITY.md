# 0.1.7 Beta — September 14 review candidate

**Hold:** the candidate hashes below predate the outfit-deployment regression
fix. Rebuild the application/source pair and update this document after the
restored outfits pass the user's in-game check. Do not publish these older ZIPs.

Prepared on 14 September 2026. Publication is pending the user's physical
controller/gameplay confirmation. The existing GitHub assets have not yet been
replaced. Application version remains 0.1.7 Beta; compatibility target is
Resynced Title Update 1.0.7.

| GitHub release asset | SHA-256 |
| --- | --- |
| Animus-Mod-and-Outfit-Manager-0.1.7-beta-win-x64.zip | 59bc64a0923014c71df7436bc62c9e9c55e1cf72c8844cfed3770f9ad4987f4f |
| Animus-Mod-and-Outfit-Manager-0.1.7-Source.zip | 59a27fd8d0cebe675467ed0e48753b2c3b6f76ed504d9420a730b487a50e00b1 |

The application asset is byte-identical to the locally named
`Animus-Mod-Manager-0.1.7.zip`; the source asset is byte-identical to
`Animus-Mod-Manager-0.1.7-Source.zip`. Only their GitHub download names differ.

Review the matching source ZIP and its BUILD-INSTRUCTIONS.txt alongside the
application. The repository also includes BUILDING.md, GAME-COMPATIBILITY.md,
and REVIEW-NOTES.md. Python and UI source files in the application were compared
against the source ZIP, and the authored application code in the source ZIP was
compared against the source being published. These checks do not assert
bit-for-bit reproducible C# compiler output.

All 2,190 application files matched the shipped SHA256SUMS.txt inventory. The
package contains four EXEs, sixteen DLLs, and ninety-six Python native modules.
Archive integrity and source checks passed; this is not a Nexus approval or
antivirus guarantee. No third-party mods or experimental crew recolours are
bundled, and Nexus API/account/download integration is absent.

Ten offline regression suites and the compiled startup-path test passed. The
packaged backend successfully requested a Steam launch; Steam completed a setup
step before the game opened a responding window. Physical controller response
is still awaiting user confirmation; see VALIDATION-2026-09-14.md.

The September 8 GitHub assets remain available until this candidate is approved
for publication. Their application SHA-256 is
`a85d8b3d59038884f7896931541538454cfd744b89097ff0772194eb431eb117`
and source SHA-256 is
`47210ab0a10b48ac4273052c961349d430fe86f998d95881bbea1fde43de46a6`.

The previous release source is retained under the archival tag
`v0.1.7-beta-before-20260908`. Its application asset had SHA-256
`8c196398165e097436335d0267bf4f2ced7fed95efc1179cfb4636f25f450f87`
and its source ZIP had SHA-256
`691c1faadff3663726c7bf69a044bded09280e7cec516e4dc58f7db02dfa6f57`.
