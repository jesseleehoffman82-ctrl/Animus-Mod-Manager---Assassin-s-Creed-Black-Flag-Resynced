# Building Animus Mod & Outfit Manager 0.1.7 Beta

This source package corresponds to the public Windows x64 release of Animus
Mod Manager 0.1.7 Beta.

## Requirements

- Windows 10 or Windows 11 x64
- .NET 10 SDK x64
- Python 3.14 x64
- Microsoft Edge WebView2 SDK 1.0.3856.49

## Native desktop host

1. Place these official WebView2 SDK files under `desktop/lib`:
   - `Microsoft.Web.WebView2.Core.dll`
   - `Microsoft.Web.WebView2.WinForms.dll`
   - `runtimes/win-x64/native/WebView2Loader.dll`
2. From the source-package root, run:

   `dotnet publish desktop/AnimusModManager.csproj -c Release -r win-x64 --self-contained false -p:PublishSingleFile=false -p:DebugType=None -p:DebugSymbols=false -o build`

The result requires Microsoft .NET 10 Desktop Runtime x64. The application
host launches the local Python RPC backend and displays the HTML/CSS/JavaScript
interface through Microsoft Edge WebView2.

## Python backend tests

Install the development dependencies:

`py -3.14 -m pip install -r tools/requirements.txt`

Run the regression tests from the source-package root:

`py -3.14 tools/test_loader_loose.py`

`py -3.14 tools/test_loader_outfits.py`

`py -3.14 tools/test_loader.py`

## Distribution design

## Rebuilding the portable distribution for review

Use PowerShell 7 from the source root. Obtain the WebView2 SDK version listed
above from Microsoft's NuGet package Microsoft.Web.WebView2, then copy its
lib/netcoreapp3.0 Core and WinForms assemblies to desktop/lib and its
runtimes/win-x64/native/WebView2Loader.dll to the matching path below desktop/lib.

Place the official 7-Zip x64 7z.exe, 7z.dll and License.txt under
tools/third_party/7zip. Place official DirectXTex texconv.exe and LICENSE.txt
under tools/third_party/directxtex. The matching public distribution includes
these redistributables and their SHA-256 inventory, so reviewers can also reuse
those exact third-party files after checking SHA256SUMS.txt. No authored manager
binaries need to be reused. Keep the directory hierarchy intact.

Install the pinned Python dependencies above, then run:

    ./build-public-beta.ps1 -PortableOnly
    ./build-nexus-clean.ps1
    ./build-source-review.ps1

The scripts download and hash-check Python 3.14.7, publish the authored desktop
host, copy the backend/UI and runtime dependencies, test packaged imports and
generate release ZIPs with checksum inventories. The optional installer build
is not required for this portable review package.

Run every offline regression with:

    Get-ChildItem tools/test_*.py | ForEach-Object { py -3.14 $_.FullName; if ($LASTEXITCODE) { throw "Test failed: $_" } }

The tests use synthetic game data; do not launch the real game as part of building.
Build outputs can vary with SDK/toolchain versions; compare the authored source
and runtime behavior as well as the supplied release hashes.

The public application package adds official redistributable components that
are intentionally not duplicated in this source-only archive: embedded Python,
7-Zip, DirectXTex and the WebView2 SDK assemblies. Animus patches selected game
files on disk and does not inject code into the running game process.
