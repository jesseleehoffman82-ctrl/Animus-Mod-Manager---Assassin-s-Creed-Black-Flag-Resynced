# Animus Mod & Outfit Manager 0.1.5 Beta

Portable mod manager for Assassin's Creed IV: Black Flag Resynced.

## Start the manager

1. Extract the complete ZIP to a normal folder.
2. Run `AnimusModManager.exe` from the extracted folder.
3. Select **Detect** in the manager, or browse to the Black Flag Resynced game folder.

Do not run the application from inside the ZIP. Keep the game closed while
installing, enabling, disabling, updating, or removing managed content.

This portable release contains no installer, launcher script, personal mod
data, or nested archive. Its native splash screen starts the included manager
without running a command script. The included Python, 7-Zip, WebView2, and
DirectXTex components support the documented manager features.

Microsoft .NET 10 Desktop Runtime (x64) is required. Download it from the
official Microsoft .NET 10 page if Windows reports that the required framework
is missing: https://dotnet.microsoft.com/en-us/download/dotnet/10.0

Supported package categories include mods, outfits, weapons, and crew
customization. ZIP, 7Z, and RAR mod archives can be selected from inside the
manager.

This is a public beta. Please include the activity-log message and the name of
the selected mod archive when reporting a problem.

Nexus integration is metadata-only. Animus uses the public Nexus GraphQL
endpoint without authentication and never asks for or stores an API key.
Downloads remain manual: download an archive in your browser, then install or
update it from inside the manager.
