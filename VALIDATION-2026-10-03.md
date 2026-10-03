# 0.1.7 Beta refresh â€” 3 October 2026

Target: Windows x64, Resynced Title Update 1.0.7, .NET 10 Desktop Runtime.

## Scope

Includes transactional disable/uninstall, texture-category and deployment fixes,
cannon target/alpha handling, sail override journals and PNG orientation
correction. Nexus API/account/download integration is absent. No trainer,
crew recolour, installed mod library or game files are bundled.

## Verification

- All 17 offline Python regression suites passed using synthetic test data.
- The uninstall suite covers 15 cases, including late ownership conflicts,
  failed deletion, state-save failure, missing backups, failed texture rebuilds,
  locked package directories and restarting after uninstall.
- Before upload, application and source ZIPs must pass tools/audit_release.py:
  CRCs, one root directory, inventory hashes, matching authored source, no
  nested archives, user mod files or retired API implementation.
- The compiled startup resolver is checked without launching a real game.

These checks do not certify all third-party mods, physical controller input,
in-game appearance, antivirus verdicts or Nexus approval. Earlier local gameplay
checks are not a new independent test of this release package.

## Recovery

Disable keeps the item in the library. Uninstall removes it from the active
library and restores owned changes; removed texture package files are retained
in recovery storage. A reported failure is not a completed uninstall.
Close the game before modifying managed content.
