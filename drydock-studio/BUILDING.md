# Source review and development

This snapshot is not a self-contained runnable distribution. There is currently no supported one-command build that produces a working Jackdaw preview from a clean game installation.

## Checks that can run without game assets

From this directory, with Python 3.10+ (tested here with Python 3.14):

```powershell
python -m unittest discover -s app/tests -v
```

The tests use temporary dummy game files and mocked validation state. They do not validate a real game install.

With the .NET 9 SDK and Windows desktop targeting support:

```powershell
dotnet build tools/anvil-bridge -c Release
```

The bridge compiles without redistributing AnvilToolkit. To use its inspection commands, supply your own compatible AnvilToolkit installation and locally obtained input files. The prototype was developed against AnvilToolkit 1.3.7 and game version 1.0.7; this is not a claim of compatibility with later releases.

## Desktop preview dependencies and blockers

The launcher invokes Windows PowerShell and WPF. Before it can run, the application directory needs matching WebView2 .NET assemblies and loader, HelixToolkit.Wpf, and an installed WebView2 runtime. These are not bundled.

The browser viewer expects Three.js at `app/high-detail-viewer/vendor/three/` and compatible helper modules at `vendor/stdlib/`, as shown by its import statements. Dependency pinning and a reproducible bootstrap remain unfinished; arbitrary latest dependency versions are not guaranteed compatible.

The UI also expects:
- A locally assembled `app/jackdaw/jackdaw-model-full.j3d` and supporting model metadata.
- Generated preview models, texture bindings, and texture images under local user-data paths.
- A generated `ship_hedefler.json` texture catalog.
- A configured Python runtime and extraction backend.

Those generated files and game-derived content are not included. The existing conversion scripts convert developer-prepared formats; they are not a complete extraction and assembly pipeline. The texture adapter references an external ShipWorkshop backend that is not included. Historical fallback paths use YOUR_USER placeholders and must not be treated as working setup instructions.

The optional 3D Gen Studio adapter references a separately installed local service/build. That service and its dependencies are not published here; generation is not an independently validated feature of this snapshot.

## Installation experiments

The Anvil workflow and legacy cosmetic-injector code are experimental. Real game modification is not part of these source-review instructions. Keep `slot_verified` and `texture_routing_verified` false in the supplied support configuration until actual compatibility and behavior are independently verified.

## Text encoding

Snapshot files are UTF-8. When editing or using Windows PowerShell 5.1, preserve appropriate encoding for non-ASCII UI text. Static syntax checks are not a runtime validation.

## Next development milestone

Replace developer-cache dependencies with an asset-free, reproducible setup and validated local reconstruction pipeline, then test the complete preview/edit/install/restore flow before publishing an installer.
