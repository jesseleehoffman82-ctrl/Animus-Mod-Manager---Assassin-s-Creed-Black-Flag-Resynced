# External dependencies

No third-party dependency source, binary, or game asset is included in this directory. Obtain dependencies from their authors and preserve their applicable licenses when packaging.

| Component | Prototype use | Distribution status |
| --- | --- | --- |
| Windows PowerShell / WPF | Desktop interface | Provided separately by Microsoft |
| WebView2 SDK / runtime | Embedded browser | Microsoft redistribution terms apply |
| HelixToolkit.Wpf | WPF model preview | Obtain upstream package and license separately |
| Three.js and compatible helper modules | Browser renderer and postprocessing | MIT-licensed upstream projects; exact dependency bootstrap not yet pinned |
| Python | Backend scripts / fixture tests | Install separately; PSF license |
| Pillow / NumPy | Some conversion utilities | Optional per script imports; not bundled |
| AnvilToolkit 1.3.7 | Reflection-based native resource inspection and packaging experiments | User-installed external tool; not included or relicensed |
| ShipWorkshop backend | Legacy texture extraction adapter | External dependency absent from snapshot |
| 3D Gen Studio | Optional generation/viewer integration | External application absent from snapshot |
| Game data and proprietary decompression libraries | Local extraction / reconstruction | Not distributed or licensed by this project |

Any third-party notices in externally obtained packages remain authoritative. Listing a dependency here does not grant redistribution rights or establish compatibility with its newest version.
