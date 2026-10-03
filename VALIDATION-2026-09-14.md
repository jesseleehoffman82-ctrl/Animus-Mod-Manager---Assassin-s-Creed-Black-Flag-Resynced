# September 14 review-build validation

Application: 0.1.7 Beta. Target: Resynced 1.0.7, Steam build 24833802.

## Passed

- Ten offline Python regression suites, including category rejection, ZIP
  discovery, uninstall/re-enable, texture deployment, crew patches, partial
  failure rollback, safe paths, and Steam/external-library launch routing.
- Compiled C# startup resolver: own installation, explicit development root,
  invalid argument fallback and working-directory fallback.
- Native .NET 10 host compilation, Python syntax and JavaScript syntax checks.
- Packaged Python backend starts and detects the installed game/build.
- A launch request through the packaged backend reached Steam. Steam initially
  paused at RunningInstallScript; after completing setup, ACBlackFlag.exe
  opened a responding game window. This was not an immediate game crash.

## Remaining manual check

Physical controller response during gameplay/relaunch has not yet been
confirmed for this review build. Steam-based launch routing is preserved; the
manager does not configure controllers, install drivers or alter Steam Input.

## Scope

Tests that deploy or remove content used disposable synthetic game folders.
No installed user mods, fort-overhaul files, game archives or controller settings
were changed by this review. The live launch check used the existing game setup.
Process/window detection is not proof that every installed mod works in-game.

Package CRC/checksum, source-correspondence and contents audits are required
before publication. The release remains unsigned. These checks are not an
antivirus verdict, a guarantee of bug-free behavior, or a Nexus approval.
