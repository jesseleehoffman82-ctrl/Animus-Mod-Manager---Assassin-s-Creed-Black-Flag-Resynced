# Game 1.0.7 compatibility — 2026-09-06

Animus application version 0.1.7 beta supports the current Resynced 1.0.7
installation. The manager's application version and the game's version are
independent. No rollback of the manager security, backup, texture-layout,
crew, or ten-sail-picker fixes was necessary.

Steam reports build 24833802. Measured executable:

- Name: ACBlackFlag.exe
- Size: 469524824 bytes
- SHA-256: 614dab4a20a5d5c6256792e1daa6d05669c97a751079b10df1725d6965ad766d

Read-only validation confirmed executable detection, all ten selected sail
materials and all forty crew materials in the installed DataPC_boot.forge. The
game's oo2core_9_win64.dll also passed an in-memory compress/decompress round
trip against a live 1.0.7 material resource. These checks do not establish
compatibility of every third-party mod or replace an in-game installation test.

The manager resolves archive resources from the installed archive's table of
contents; it does not use a fixed executable address map. The proprietary Oodle
DLL is read from the user's game installation and is not included in the public
manager or source archive.

Native Cheats/ASI mods and the fort extender have separate executable-specific
compatibility requirements. Updating the manager does not automatically update
those mods, their build guards, or the game executable. Existing archive backups
from another game build must not be blindly written over the 1.0.7 archives.
