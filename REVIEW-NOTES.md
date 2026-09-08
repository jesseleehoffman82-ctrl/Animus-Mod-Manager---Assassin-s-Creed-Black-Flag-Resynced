# 0.1.7 beta review refresh — 2026-09-05

This is a local review build, not a Nexus approval or antivirus guarantee.
Compatibility target: game Title Update 1.0.7 (Steam build 24833802); application version: 0.1.7 beta.
See GAME-COMPATIBILITY.md for the measured executable and validation scope.
The application and matching source archives are rebuilt together. SHA256SUMS.txt
inside the application identifies every shipped file; adjacent .sha256 files
identify the archives supplied for review.

## Changes

- No Nexus account, API key, GraphQL, OAuth, SSO or download integration is included.
- WebView navigation and native messages are restricted to the local interface;
  external shell links permit only HTTP/HTTPS.
- Manifest targets reject absolute, traversal and drive-relative paths; resolved
  targets must remain inside the selected game folder. Payload checksums are verified.
- Successful earlier writes are rolled back when a subsequent install target fails.
- Rectangular texture mip layouts now use both width and height.
- Sail selection is limited to ten base textures; old catalogue IDs remain readable.
- Includes the existing launch-detection fixes and complete portable build scripts.

## Distribution contents

The public manager includes its .NET desktop host, local Python backend and UI,
and required Python, WebView2, 7-Zip and DirectXTex runtime components.
It does not contain the developer's Cheats payload, ASI loader, fort plugins,
game assets, installed mod library, save files or credentials.
The manager can deploy a user's independently downloaded DLL mods onto disk;
those mods can execute inside the game, but they are not bundled with Animus.

## Review request

Please review the updated application archive against its matching source archive.
The previously reported API-key implementation has been removed. Executables
remain because they provide the desktop host and documented extraction/conversion
functions. We understand these require your manual review.

Runtime smoke tests and automated tests cannot establish that every third-party
mod is compatible or that the application has no bugs. This release does not claim
to bypass automated quarantine.
