# Building Animus Mod Manager 0.1.2 Beta

These instructions build and verify the source corresponding to the submitted
Windows x64 Nexus release.

## 1. Requirements

- Windows 10 or Windows 11 x64
- Git
- .NET 10 SDK x64
- Python 3.14 x64 with `pip`
- Microsoft Edge WebView2 SDK `1.0.3856.49`
- 7-Zip command-line binaries
- Microsoft DirectXTex `texconv.exe`
- Inno Setup 7 only when building the optional installer

End users require the **.NET 10 Desktop Runtime x64**, not the SDK. The SDK is
needed only to compile the application.

## 2. Place external SDK and utility files

Third-party compiled redistributables are not duplicated in the browsable
source tree. Place the official files in these locations before publishing:

```text
desktop/lib/Microsoft.Web.WebView2.Core.dll
desktop/lib/Microsoft.Web.WebView2.WinForms.dll
desktop/lib/runtimes/win-x64/native/WebView2Loader.dll
tools/third_party/7zip/7z.exe
tools/third_party/7zip/7z.dll
tools/third_party/7zip/License.txt
tools/third_party/directxtex/texconv.exe
tools/third_party/directxtex/LICENSE.txt
```

The WebView2 assemblies must come from Microsoft WebView2 SDK version
`1.0.3856.49`. DirectXTex must come from Microsoft's official DirectXTex
release. 7-Zip must come from the official 7-Zip distribution.

## 3. Install Python build dependencies

```powershell
py -3.14 -m pip install -r tools/requirements.txt
```

The public packaging script downloads the official Python 3.14.7 embeddable
x64 archive and verifies this SHA-256 before using it:

```text
d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15
```

## 4. Build the native desktop host

```powershell
$env:DOTNET_CLI_HOME = Join-Path (Get-Location) '.dotnet-cli'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'

dotnet publish desktop/AnimusModManager.csproj `
  -c Release `
  -r win-x64 `
  --self-contained false `
  -p:PublishSingleFile=false `
  -p:DebugType=None `
  -p:DebugSymbols=false `
  -o build
```

The output is a framework-dependent .NET 10 Windows x64 application.

## 5. Run regression tests

Run every command from the repository root:

```powershell
py -3.14 tools/test_import_nexus_zip.py
py -3.14 tools/test_loader_loose.py
py -3.14 tools/test_loader_outfits.py
py -3.14 tools/test_loader.py
py -3.14 tools/test_nexus_updates.py
```

The suites cover manifest-free Nexus archives, loose-file deployment, outfit
replacement and conflict behavior, core installation/restoration, and Nexus
metadata/update behavior.

## 6. Build the public portable release

```powershell
./build-public-beta.ps1 -Version 0.1.2-beta
```

This creates:

```text
release/Animus-Mod-Manager-0.1.2-beta-win-x64/
release/Animus-Mod-Manager-0.1.2-beta-win-x64.zip
```

The script publishes the framework-dependent .NET 10 host; downloads and
checksum-verifies official embedded Python; copies required Python packages,
the authored backend/interface, and official third-party utilities; removes
test folders, nested archives, and Python caches; and creates SHA-256 manifests.

## 7. Build the Nexus-clean archive

```powershell
./build-nexus-clean.ps1 -Version 0.1.2-beta
```

This creates `release/Animus-Mod-Manager-0.1.2.zip`. The script enforces an
executable allow-list, rejects nested archives and command scripts, verifies
that no managed user mod files are present, imports the packaged Python
backend, and writes SHA-256 manifests.

Expected executable allow-list:

```text
AnimusModManager.exe
runtime/python/python.exe
tools/third_party/7zip/7z.exe
tools/third_party/directxtex/texconv.exe
```

## 8. Optional installer

```powershell
./build-installer.ps1 -Version 0.1.2-beta
```

The installer checks for Microsoft .NET 10 Desktop Runtime x64 and preserves
managed mods and backups during reinstall or repair. It is not included in the
Nexus portable archive submitted for review.

## Security-relevant behavior

- The manager modifies selected files only inside the user-selected game and
  managed-library directories.
- It creates backups before supported managed replacements.
- It does not inject into a running process.
- It does not install a Windows service or scheduled task.
- It does not modify antivirus or firewall settings.
- It does not contain an automatic updater.
- Direct Nexus authentication and downloads are disabled in this beta.
