param([switch]$SelfTest, [switch]$LoadTest)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Xaml
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -Path (Join-Path $appRoot 'Microsoft.Web.WebView2.Wpf.dll')
Add-Type -Path (Join-Path $appRoot 'HelixToolkit.Wpf.dll')
$modelPath = Join-Path $appRoot 'jackdaw\jackdaw-model-full.j3d'
if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    throw 'The verified Jackdaw native viewer model is missing. Rebuild jackdaw-model-full.j3d from jackdaw-model-full.glb; obsolete preview models are not allowed as fallbacks.'
}
$script:modelPath = $modelPath
$dataRoot = Join-Path $appRoot 'user-data'
$projectsRoot = Join-Path $dataRoot 'projects'
$exportRoot = Join-Path $appRoot 'exported-pngs'
New-Item -ItemType Directory -Force -Path $projectsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $exportRoot | Out-Null
$script:gameFolder = $null
$script:exactTextureMaterials = @{}

function Read-ModelHeader([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        $magic = [Text.Encoding]::ASCII.GetString($reader.ReadBytes(8))
        if ($magic -ne "JACK3D1`0") { throw 'The Jackdaw preview model has an invalid header.' }
        return @{ Components = $reader.ReadUInt32(); Zones = $reader.ReadUInt32(); Bytes = $stream.Length }
    }
    finally { $stream.Dispose() }
}

if ($SelfTest) {
    $header = Read-ModelHeader $modelPath
    "Jackdaw preview OK: $($header.Components) components, $($header.Zones) zones, $($header.Bytes) bytes"
    exit 0
}

function Find-Game {
    $candidates = [Collections.Generic.List[string]]::new()
    foreach ($base in @(${env:ProgramFiles}, ${env:ProgramFiles(x86)})) {
        if ($base) { $candidates.Add((Join-Path $base "Steam\steamapps\common\Assassin's Creed Black Flag Resynced")) }
    }
    foreach ($drive in 'C','D','E','F','G','H') {
        $candidates.Add("${drive}:\SteamLibrary\steamapps\common\Assassin's Creed Black Flag Resynced")
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'DataPC_boot.forge') -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Get-PersistedGameFolder {
    $settingsPath = Join-Path $dataRoot 'settings.json'
    if (-not (Test-Path -LiteralPath $settingsPath -PathType Leaf)) { return $null }
    try {
        $s = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        if ($s -and $s.PSObject.Properties['gameFolder'] -and
            (Test-Path -LiteralPath (Join-Path ([string]$s.gameFolder) 'DataPC_boot.forge') -PathType Leaf)) {
            return [string]$s.gameFolder
        }
    } catch { }
    return $null
}

function Save-PersistedGameFolder([string]$folder) {
    if (-not $folder) { return }
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'DataPC_boot.forge') -PathType Leaf)) { return }
    $settingsPath = Join-Path $dataRoot 'settings.json'
    [ordered]@{ gameFolder = $folder } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $settingsPath -Encoding utf8
}

$xaml = [System.IO.File]::ReadAllText((Join-Path $appRoot 'window_layout.xaml'))

$reader = [System.Xml.XmlNodeReader]::new(([xml]$xaml))
$window = [Windows.Markup.XamlReader]::Load($reader)
$script:uiDispatcher = $window.Dispatcher
$gameStatus = $window.FindName('GameStatus')
$projectTitle = $window.FindName('ProjectTitle')
$modelStatus = $window.FindName('ModelStatus')
$viewportWebBrowser = $window.FindName('ViewportWebBrowser')
$viewportHost = $window.FindName('ViewportHost')
$viewportInputLayer = $window.FindName('ViewportInputLayer')
$loadingText = $window.FindName('LoadingText')
$pngCollection = $window.FindName('PngCollection')
$zones = $window.FindName('Zones')
$targetFlyout = $window.FindName('TargetFlyout')
$closeTargetFlyout = $window.FindName('CloseTargetFlyout')
$pngSearch = $window.FindName('PngSearch')
$pngSearchHint = $window.FindName('PngSearchHint')
$footer = $window.FindName('Footer')
$texturePreview = $window.FindName('TexturePreview')
$texturePreviewEmpty = $window.FindName('TexturePreviewEmpty')
$replacementPreview = $window.FindName('ReplacementPreview')
$replacementPreviewEmpty = $window.FindName('ReplacementPreviewEmpty')
$generatedPreviewPanel = $window.FindName('GeneratedPreviewPanel')
$textureName = $window.FindName('TextureName')
$textureHint = $window.FindName('TextureHint')
$textureInfo = $window.FindName('TextureInfo')
$submenuTextureName = $window.FindName('SubmenuTextureName')
$submenuTextureInfo = $window.FindName('SubmenuTextureInfo')
$selectedThumb = $window.FindName('SelectedThumb')
$targetSubTitle = $window.FindName('TargetSubTitle')
$AiPromptInput = $window.FindName('AiPromptInput')
$AiGenerateButton = $window.FindName('AiGenerateButton')
$AiStyleReferenceButton = $window.FindName('AiStyleReferenceButton')
$AiCancelButton = $window.FindName('AiCancelButton')
$AiStatusText = $window.FindName('AiStatusText')
$applyDesign = $window.FindName('ApplyDesign')
$injectDesign = $window.FindName('InjectDesign')
$rollbackInjection = if ($injectDesign -and $injectDesign.ContextMenu) { $injectDesign.ContextMenu.Items[0] } else { $null }
$applySplitButton = $window.FindName('ApplySplitButton')
$applyDesignMenu = $window.FindName('ApplyDesignMenu')
$applyScopeWhole = $window.FindName('ApplyScopeWhole')
$applyScopeSails = $window.FindName('ApplyScopeSails')
$applyScopeHull = $window.FindName('ApplyScopeHull')
$applyScopeFigurehead = $window.FindName('ApplyScopeFigurehead')
$applyScopeCrew = $window.FindName('ApplyScopeCrew')
$applyScopeCannons = $window.FindName('ApplyScopeCannons')
$applyScopeMortar = $window.FindName('ApplyScopeMortar')
$applyScopeCabin = $window.FindName('ApplyScopeCabin')
$applyScopeSelected = $window.FindName('ApplyScopeSelected')
$designProgressBar = $window.FindName('DesignProgressBar')
$designProgressText = $window.FindName('DesignProgressText')
$designProgressPercent = $window.FindName('DesignProgressPercent')
$designProgressDetails = $window.FindName('DesignProgressDetails')
$sailGroupMode = $window.FindName('SailGroupMode')
$sailDisplayMode = $window.FindName('SailDisplayMode')
$categoryHelp = $window.FindName('CategoryHelp')
$lightingMode = $window.FindName('LightingMode')
$textureToggle = $window.FindName('TextureToggle')
$catButtons = [ordered]@{
    Sails = $window.FindName('CatSails')
    Hulls = $window.FindName('CatHulls')
    Cannons = $window.FindName('CatCannons')
    Mortars = $window.FindName('CatMortars')
    Flags = $window.FindName('CatFlags')
    Figureheads = $window.FindName('CatFigureheads')
    Wheels = $window.FindName('CatWheels')
    Cabin = $window.FindName('CatCabin')
    'Sail Regions' = $window.FindName('CatSailRegions')
    'Hull Regions' = $window.FindName('CatHullRegions')
    Masts = $window.FindName('CatMasts')
    Rigging = $window.FindName('CatRigging')
    'Flag Regions' = $window.FindName('CatFlagRegions')
    'Weapon Regions' = $window.FindName('CatWeaponRegions')
    Lanterns = $window.FindName('CatLanterns')
    Details = $window.FindName('CatDetails')
    Ram = $window.FindName('CatRam')
    Rudder = $window.FindName('CatRudder')
}
$texturePreview.Cursor = [System.Windows.Input.Cursors]::Hand
if ($selectedThumb) { $selectedThumb.Cursor = [System.Windows.Input.Cursors]::Hand }
if (-not $script:applyDesignScopeName) { $script:applyDesignScopeName = 'Whole ship' }

function Set-UiText {
    param($Element, [string]$Value)
    if ($null -eq $Element) { return }
    if ($script:uiDispatcher -and -not $script:uiDispatcher.CheckAccess()) {
        $script:uiDispatcher.Invoke([Action]{ $Element.Text = $Value })
        return
    }
    if ($Element.PSObject.Properties['Text']) {
        $Element.Text = $Value
    }
}

function Invoke-OnUiThread {
    param([scriptblock]$block)
    if (-not $script:uiDispatcher) { return & $block }
    if ($script:uiDispatcher.CheckAccess()) { return & $block }
    $script:lazyUiResult = $null
    $script:uiDispatcher.Invoke([Action]{ $script:lazyUiResult = & $block })
    return $script:lazyUiResult
}

function Invoke-UiRefresh {
    try {
        if ($window -and $window.Dispatcher) {
            $window.Dispatcher.Invoke([Action]{} , [Windows.Threading.DispatcherPriority]::Background) | Out-Null
        }
    }
    catch { }
}

function Set-DesignProgress {
    param(
        [string]$Status = 'Ready to apply Jackdaw design.',
        [int]$Percent = 0,
        [string]$Details = ''
    )
    $Percent = [Math]::Max(0, [Math]::Min(100, $Percent))
    if ($designProgressBar) { $designProgressBar.Value = $Percent }
    if ($designProgressText) { $designProgressText.Text = $Status }
    if ($designProgressPercent) { $designProgressPercent.Text = "$Percent%" }
    if ($designProgressDetails) {
        if ([string]::IsNullOrWhiteSpace($Details)) {
            $Details = if ($Percent -ge 100) { 'Operation complete.' } elseif ($Percent -gt 0) { 'Processing Jackdaw textures...' } else { 'Waiting for an operation.' }
        }
        $designProgressDetails.Text = $Details
    }
    Invoke-UiRefresh
}

$script:designProgressResetTimer = [Windows.Threading.DispatcherTimer]::new()
$script:designProgressResetTimer.Interval = [TimeSpan]::FromMilliseconds(1250)
$script:designProgressResetTimer.Add_Tick({
    $script:designProgressResetTimer.Stop()
    Set-DesignProgress 'Ready to apply Jackdaw design.' 0 'Waiting for an operation.'
})

function Reset-DesignProgressSoon {
    param([int]$DelayMilliseconds = 1250)
    if ($DelayMilliseconds -lt 250) { $DelayMilliseconds = 250 }
    $script:designProgressResetTimer.Stop()
    $script:designProgressResetTimer.Interval = [TimeSpan]::FromMilliseconds($DelayMilliseconds)
    $script:designProgressResetTimer.Start()
}

function Set-ApplyDesignScope {
    param([string]$ScopeName)
    if ([string]::IsNullOrWhiteSpace($ScopeName)) { $ScopeName = 'Whole ship' }
    $script:applyDesignScopeName = $ScopeName
    Set-UiText $footer "Apply scope set to $ScopeName."
    Set-DesignProgress "Apply scope set to $ScopeName." 0 "Scope: $ScopeName"
    Reset-DesignProgressSoon 900
}

if ($applyDesignMenu -and $applyDesignMenu.ContextMenu) {
    $applyDesignMenu.Add_Click({
        if ($applyDesignMenu.ContextMenu) {
            if ($applySplitButton) {
                $applyDesignMenu.ContextMenu.PlacementTarget = $applySplitButton
                $applyDesignMenu.ContextMenu.MinWidth = [Math]::Max(160, $applySplitButton.ActualWidth)
            }
            $applyDesignMenu.ContextMenu.Placement = [System.Windows.Controls.Primitives.PlacementMode]::Bottom
            $applyDesignMenu.ContextMenu.HorizontalOffset = 0
            $applyDesignMenu.ContextMenu.VerticalOffset = 2
            $applyDesignMenu.ContextMenu.IsOpen = $true
        }
    })
    if ($applyScopeWhole) { $applyScopeWhole.Add_Click({ Set-ApplyDesignScope 'Whole ship' }) }
    if ($applyScopeHull) { $applyScopeHull.Add_Click({ Set-ApplyDesignScope 'Hull' }) }
    if ($applyScopeSails) { $applyScopeSails.Add_Click({ Set-ApplyDesignScope 'Sails' }) }
    if ($applyScopeFigurehead) { $applyScopeFigurehead.Add_Click({ Set-ApplyDesignScope 'Figurehead' }) }
    if ($applyScopeCrew) { $applyScopeCrew.Add_Click({ Set-ApplyDesignScope 'Crew' }) }
    if ($applyScopeCannons) { $applyScopeCannons.Add_Click({ Set-ApplyDesignScope 'Cannons' }) }
    if ($applyScopeMortar) { $applyScopeMortar.Add_Click({ Set-ApplyDesignScope 'Mortar' }) }
    if ($applyScopeCabin) { $applyScopeCabin.Add_Click({ Set-ApplyDesignScope 'Cabin' }) }
    if ($applyScopeSelected) { $applyScopeSelected.Add_Click({ Set-ApplyDesignScope 'Selected parts' }) }
}

$componentNames = @(
    'Outer hull',
    'Deck',
    'Bow structure',
    'Stern cabin',
    'Standing rigging',
    'Masts and yardarms',
    'Sails',
    'Mast flag',
    'Cannons',
    'Swivel guns',
    'Light mortar',
    'Ship lanterns',
    'Rigging parts',
    'Ship greebles',
    'Ram',
    'Rudder'
)

# 26 named LOD0 visual groups embedded in OBD_SHP_BRG_Jackdaw.
$sailNames = @(
    'Main Spanker', 'Main Topsail Starboard Wing', 'Main Topsail Port Wing',
    'Main Topsail', 'Main Topgallant Starboard Wing', 'Main Topgallant Port Wing',
    'Main Topgallant', 'Main Course Starboard Wing', 'Main Course Port Wing',
    'Main Course', 'Main Course Staysail', 'Fore Topsail Starboard Wing',
    'Fore Topsail Port Wing', 'Fore Topsail', 'Fore Topgallant Starboard Wing',
    'Fore Topgallant Port Wing', 'Fore Topgallant', 'Fore Royal Starboard Wing',
    'Fore Royal Port Wing', 'Fore Royal', 'Fore Course Starboard Wing',
    'Fore Course Port Wing', 'Fore Course', 'Top Jib', 'Flying Jib', 'Course Jib'
)

$componentColors = @(
    '#2E5F7E',
    '#C69A4A',
    '#4E7E98',
    '#8A603D',
    '#4E8F8B',
    '#6B8FA8',
    '#C9C4B5',
    '#2A2526',
    '#7A6A4A',
    '#4A5A6A',
    '#5A4A5A',
    '#3A5A4A',
    '#6A5A4A',
    '#4A4A5A',
    '#7B6A4B',
    '#5C6670'
)
$componentGroups = @()
$zoneRecords = [Collections.Generic.List[object]]::new()
$catalogPath = Join-Path $appRoot 'ship_hedefler.json'
$script:shipCatalog = $null
$script:visibleZoneRecords = [Collections.Generic.List[object]]::new()
$script:activeCategory = 'Sails'
$script:searchQuery = ''
$script:syncingSelection = $false
$script:expandedHullGroups = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$script:hullGroupsPrimed = $false
$script:thumbnailEpoch = 0
$script:thumbnailJob = $null
$script:thumbnailJobEpoch = -1
$script:thumbnailBatchHadSuccess = $false
$script:thumbnailSkipped = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$script:thumbnailImageCache = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
$script:thumbnailPathCache = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
$script:textureCacheRoot = $null
$script:textureCacheIndexed = $false
$script:visibleListEpoch = 0
$script:visibleThumbnailQueue = [Collections.Generic.Queue[object]]::new()
$script:lastPreviewImagePath = $null
$script:lastPreviewImageSource = $null
$script:thumbnailTimer = [Windows.Threading.DispatcherTimer]::new()
$script:thumbnailTimer.Interval = [TimeSpan]::FromMilliseconds(400)
$script:thumbnailTimer.Add_Tick({
    try { Apply-ThumbnailBackfill } catch { }
})
$script:visibleThumbnailTimer = [Windows.Threading.DispatcherTimer]::new()
$script:visibleThumbnailTimer.Interval = [TimeSpan]::FromMilliseconds(20)
$script:visibleThumbnailTimer.Add_Tick({
    try { Process-VisibleThumbnailQueue } catch { }
})
$script:searchTimer = [Windows.Threading.DispatcherTimer]::new()
$script:searchTimer.Interval = [TimeSpan]::FromMilliseconds(180)
$script:searchTimer.Add_Tick({
    $script:searchTimer.Stop()
    Apply-SearchFilter
})
$script:activeView = 'jackdaw'
$script:currentSailViewMode = 'Default game sails'
$script:texturesEnabled = $true
$script:previousSailDisplayMode = 'Default game sails'
$script:clayPreviewMaterial = $null
$rootModel = [Windows.Media.Media3D.Model3DGroup]::new()
$script:ambientLight = [Windows.Media.Media3D.AmbientLight]::new([Windows.Media.Color]::FromRgb(28,48,72))
$script:keyLight = [Windows.Media.Media3D.DirectionalLight]::new([Windows.Media.Color]::FromRgb(235,226,204), [Windows.Media.Media3D.Vector3D]::new(-0.4,-0.6,-1))
$script:fillLight = [Windows.Media.Media3D.DirectionalLight]::new([Windows.Media.Color]::FromRgb(74,120,148), [Windows.Media.Media3D.Vector3D]::new(0.45,0.15,-1))
$rootModel.Children.Add($script:ambientLight)
$rootModel.Children.Add($script:keyLight)
$rootModel.Children.Add($script:fillLight)
for ($index=0; $index -lt $componentNames.Count; $index++) {
    $group = [Windows.Media.Media3D.Model3DGroup]::new()
    $componentGroups += $group
    $rootModel.Children.Add($group)
}
$script:dragMode = $null

$script:camera = [Windows.Media.Media3D.PerspectiveCamera]::new()
$script:camera.FieldOfView = 40
$script:camera.NearPlaneDistance = 0.1
$script:camera.FarPlaneDistance = 1000
$script:defaultYaw = -1.30
$script:defaultPitch = 0.30
$script:yaw = $script:defaultYaw
$script:pitch = $script:defaultPitch
$script:distance = 2.12
$script:defaultDistance = $script:distance
$script:minDistance = 0.10
$script:maxDistance = 20.0
$script:defaultModelCenter = [Windows.Media.Media3D.Point3D]::new(0,0,0)
$script:modelCenter = $script:defaultModelCenter

function Update-Camera {
    if ($null -eq $script:camera) { return }
    $horizontal = $script:distance * [Math]::Cos($script:pitch)
    $position = [Windows.Media.Media3D.Point3D]::new(
        $script:modelCenter.X + $horizontal * [Math]::Cos($script:yaw),
        $script:modelCenter.Y + $horizontal * [Math]::Sin($script:yaw),
        $script:modelCenter.Z + $script:distance * [Math]::Sin($script:pitch))
    $script:camera.Position = $position
    $script:camera.LookDirection = [Windows.Media.Media3D.Vector3D]::new(
        $script:modelCenter.X - $position.X,
        $script:modelCenter.Y - $position.Y,
        $script:modelCenter.Z - $position.Z)
    # The extracted ship uses Z-up. Leaving WPF's default Y-up here makes the
    # horizon roll and causes orbit/pan directions to feel inconsistent.
    $script:camera.UpDirection = [Windows.Media.Media3D.Vector3D]::new(0,0,1)
}
Update-Camera

function Set-PreviewRenderer([string]$renderer) {
    # Choose which surface renders the Jackdaw:
    #   '3dgen' -> the 3DGenStudio WebView mesh-editor shows the complete
    #              104-zone model (hull, sails, flag, cannons, swivel, mortar,
    #              lanterns, rigging, greebles) with per-zone highlight.
    #   'native' -> the built-in Helix viewport (the 33-zone JACK3D1 preview)
    #               used as an offline fallback when the studio is unreachable.
    $useWebView = ($script:embeddedReady -or $renderer -eq '3dgen') -and ($null -ne $viewportWebBrowser)
    if ($null -ne $viewportWebBrowser) {
        $viewportWebBrowser.Visibility = if ($useWebView) { [Windows.Visibility]::Visible } else { [Windows.Visibility]::Collapsed }
    }
    if ($null -ne $script:nativeViewport) {
        $script:nativeViewport.Visibility = if ($useWebView) { [Windows.Visibility]::Collapsed } else { [Windows.Visibility]::Visible }
    }
}

function Initialize-NativeViewport {
    if ($null -ne $script:nativeViewport) { return $script:nativeViewport }
    $vp = [HelixToolkit.Wpf.HelixViewport3D]::new()
    $vp.Name = 'NativeViewport'
    $vp.Background = [Windows.Media.Brushes]::Transparent
    $vp.ShowViewCube = $false
    $vp.ShowCoordinateSystem = $true
    # The existing manual orbit handlers + Update-Camera own the camera, so
    # disable Helix's built-in navigation to avoid two competing controllers.
    $vp.IsRotationEnabled = $false
    $vp.IsPanEnabled = $false
    $vp.IsZoomEnabled = $false
    $vp.IsMoveEnabled = $false
    $vp.IsInertiaEnabled = $false
    $vp.ZoomExtentsWhenLoaded = $false
    $vp.Camera = $script:camera
    $modelVisual = [Windows.Media.Media3D.ModelVisual3D]::new()
    $modelVisual.Content = $rootModel
    $vp.Children.Add($modelVisual)
    if ($null -ne $viewportHost -and $null -ne $viewportWebBrowser) {
        # Keep the renderer below the dedicated input layer and HUD controls.
        # Adding it last put Helix above the controls and let its internal
        # visual tree steal mouse capture from the manual camera controller.
        $viewportHost.Children.Insert(1, $vp)
    }
    $script:nativeViewport = $vp
    Set-PreviewRenderer 'native'
    return $vp
}
[void](Initialize-NativeViewport)

function Apply-ViewerLighting {
    $mode = 'Soft'
    if ($lightingMode -and $lightingMode.SelectedItem) {
        $modeText = [string]$lightingMode.SelectedItem.Content
        if ($modeText -match 'Bright') { $mode = 'Bright' }
        elseif ($modeText -match 'Studio') { $mode = 'Studio' }
        elseif ($modeText -match 'Flat') { $mode = 'Flat' }
        elseif ($modeText -match 'Neutral') { $mode = 'Neutral' }
    }
    switch ($mode) {
        'Neutral' {
            $script:ambientLight.Color = [Windows.Media.Color]::FromRgb(55,55,55)
            $script:keyLight.Color = [Windows.Media.Color]::FromRgb(235,235,235)
            $script:fillLight.Color = [Windows.Media.Color]::FromRgb(130,130,130)
        }
        'Bright' {
            $script:ambientLight.Color = [Windows.Media.Color]::FromRgb(56,78,104)
            $script:keyLight.Color = [Windows.Media.Color]::FromRgb(255,245,220)
            $script:fillLight.Color = [Windows.Media.Color]::FromRgb(116,160,192)
        }
        'Studio' {
            $script:ambientLight.Color = [Windows.Media.Color]::FromRgb(22,38,54)
            $script:keyLight.Color = [Windows.Media.Color]::FromRgb(244,232,210)
            $script:fillLight.Color = [Windows.Media.Color]::FromRgb(88,124,160)
        }
        'Flat' {
            $script:ambientLight.Color = [Windows.Media.Color]::FromRgb(90,90,90)
            $script:keyLight.Color = [Windows.Media.Color]::FromRgb(210,210,210)
            $script:fillLight.Color = [Windows.Media.Color]::FromRgb(210,210,210)
        }
        default {
            $script:ambientLight.Color = [Windows.Media.Color]::FromRgb(28,48,72)
            $script:keyLight.Color = [Windows.Media.Color]::FromRgb(235,226,204)
            $script:fillLight.Color = [Windows.Media.Color]::FromRgb(74,120,148)
        }
    }
}

function Get-SailViewMode {
    if ($sailDisplayMode -and $sailDisplayMode.SelectedItem) {
        return [string]$sailDisplayMode.SelectedItem.Content
    }
    # The old mode ComboBox is no longer exposed in the compact release UI.
    # Keep honoring the internal mode so Apply PNG / Use PNG on all sails does
    # not immediately replace the user's preview with the default material.
    if (-not [string]::IsNullOrWhiteSpace([string]$script:currentSailViewMode)) {
        return [string]$script:currentSailViewMode
    }
    return 'Default game sails'
}

function Set-SailViewMode([string]$mode) {
    $script:currentSailViewMode = $mode
    if (-not $sailDisplayMode) { return }
    switch ($mode) {
        'Custom preview' { $sailDisplayMode.SelectedIndex = 1 }
        'Model only' { $sailDisplayMode.SelectedIndex = 2 }
        default { $sailDisplayMode.SelectedIndex = 0 }
    }
}

function New-SolidMaterial([string]$hexColor) {
    $color = [Windows.Media.ColorConverter]::ConvertFromString($hexColor)
    return [Windows.Media.Media3D.DiffuseMaterial]::new([Windows.Media.SolidColorBrush]::new($color))
}

function Get-TextureCacheRoot {
    if ($script:textureCacheRoot) { return $script:textureCacheRoot }
    if (-not $script:currentProject) { return $null }
    $script:textureCacheRoot = Join-Path $script:currentProject 'game-cache'
    if (-not (Test-Path -LiteralPath $script:textureCacheRoot)) {
        New-Item -ItemType Directory -Force -Path $script:textureCacheRoot | Out-Null
    }
    return $script:textureCacheRoot
}

function Get-FirstExistingPath([string[]]$paths) {
    foreach ($path in $paths) {
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        if (Test-Path -LiteralPath $path) { return $path }
    }
    return $null
}

function Get-PreviewAssetRoots {
    $roots = @($appRoot)
    $workspaceRoot = 'C:\Users\YOUR_USER\Documents\Codex\2026-08-01\w'
    if (Test-Path -LiteralPath $workspaceRoot) {
        $roots += $workspaceRoot
    }
    return @($roots | Select-Object -Unique)
}

function Get-PreviewAssetPath([string[]]$relativePaths) {
    foreach ($root in Get-PreviewAssetRoots) {
        foreach ($relative in $relativePaths) {
            if ([string]::IsNullOrWhiteSpace($relative)) { continue }
            $candidate = Join-Path $root $relative
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

function New-ThumbnailImageSource([string]$path, [int]$decodeWidth = 88) {
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path)) { return $null }
    $cacheKey = "{0}|{1}" -f $decodeWidth, ([IO.Path]::GetFullPath($path))
    if ($script:thumbnailImageCache.ContainsKey($cacheKey)) {
        return $script:thumbnailImageCache[$cacheKey]
    }
    try {
        $image = [Windows.Media.Imaging.BitmapImage]::new()
        $image.BeginInit()
        $image.CacheOption = 'OnLoad'
        $image.DecodePixelWidth = $decodeWidth
        $image.UriSource = [Uri]::new($path)
        $image.EndInit()
        $image.Freeze()
        $script:thumbnailImageCache[$cacheKey] = $image
        return $image
    }
    catch {
        return $null
    }
}

function Get-LibraryLoadingThumbnail {
    if ($script:libraryLoadingThumbnail) { return $script:libraryLoadingThumbnail }
    $drawing = [Windows.Media.DrawingGroup]::new()
    $background = [Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(8,28,39))
    $outline = [Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(54,108,127))
    $accent = [Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(214,166,74))
    $drawing.Children.Add([Windows.Media.GeometryDrawing]::new(
        $background,[Windows.Media.Pen]::new($outline,2.0),
        [Windows.Media.RectangleGeometry]::new([Windows.Rect]::new(1,1,70,70),5,5)))
    $drawing.Children.Add([Windows.Media.GeometryDrawing]::new(
        $null,[Windows.Media.Pen]::new($accent,2.0),
        [Windows.Media.Geometry]::Parse('M 17,20 L55,20 55,52 17,52 Z M 21,46 L31,35 38,41 44,34 52,45')))
    $drawing.Children.Add([Windows.Media.GeometryDrawing]::new(
        $accent,$null,[Windows.Media.EllipseGeometry]::new([Windows.Point]::new(45,29),3.5,3.5)))
    $drawing.Freeze()
    $image = [Windows.Media.DrawingImage]::new($drawing)
    $image.Freeze()
    $script:libraryLoadingThumbnail = $image
    return $image
}

function Get-JackdawFallbackThumbnail([string]$lookupKey, [string]$group) {
    $key = ([string]$lookupKey).ToLowerInvariant()
    $groupName = ([string]$group).ToLowerInvariant()

    $genericSailThumb = Get-PreviewAssetPath @(
        'work\candidate-meshes\jackdaw-full-sail-preview.png',
        'work\candidate-meshes\jackdaw-game-sails-assembly.png',
        'work\exact-trace\jackdaw-motioncloth-exact-check.png',
        'work\candidate-meshes\game-sails-2385-preview.png',
        'work\exact-trace\sails-223479.png',
        'work\exact-trace\sails-22f447.png'
    )
    $genericHullThumb = Get-PreviewAssetPath @(
        'work\exact-trace\jackdaw-root-mesh-upright.png',
        'work\exact-trace\jackdaw-root-mesh.png',
        'work\candidate-meshes\jackdaw-assembly-preview.png'
    )

    if ($key -match 'jackdaw_03|pt_jackdaw_06|motioncloth|full_sail|main sail|stay sail') {
        return Get-PreviewAssetPath @(
            'work\exact-trace\jackdaw-motioncloth-exact-check.png',
            'work\candidate-meshes\jackdaw-full-sail-preview.png',
            'work\candidate-meshes\jackdaw-game-sails-assembly.png',
            $genericSailThumb
        )
    }
    if ($key -match 'jackdaw_02|pt_jackdaw_05|jib|foremast|mast') {
        return Get-PreviewAssetPath @(
            'work\candidate-meshes\jackdaw-game-sails-assembly.png',
            'work\candidate-meshes\game-sails-2385-preview.png',
            'work\exact-trace\jackdaw-root-plus-two-mast-cloth-front.png',
            $genericSailThumb
        )
    }
    if ($key -match 'pt_jackdaw_04|pattern|blackskull|redbull|ultimate|ezio|athena|assassin|spanish|animus|dlc|iconic') {
        return Get-PreviewAssetPath @(
            'work\exact-trace\sails-223479.png',
            'work\exact-trace\sails-22f447.png',
            'work\candidate-meshes\game-sails-2385-preview.png',
            $genericSailThumb
        )
    }

    if ($groupName -eq 'sail') { return $genericSailThumb }
    return $genericHullThumb
}

function Get-RecordDisplayTexturePath($record) {
    if (-not $record) { return $null }
    if ($record.Texture -and (Test-Path -LiteralPath $record.Texture)) { return $record.Texture }
    if ($record.Thumbnail -and (Test-Path -LiteralPath $record.Thumbnail)) { return $record.Thumbnail }

    if ($record.Kind -eq 'Catalog') {
        $sourceKey = if ($record.Source -and $record.Source.anahtar) { [string]$record.Source.anahtar } elseif ($record.ResourceId) { [string]$record.ResourceId } else { [string]$record.Label }
        # Cache-only on the UI thread (no synchronous forge extraction here).
        $exact = Get-CachedThumbnailPath $sourceKey
        if ($exact -and (Test-Path -LiteralPath $exact)) { return $exact }
        # Never substitute a model render for a texture-library entry. The
        # category warmer will replace the empty tile with the real extracted
        # texture when it becomes available.
        return $null
    }

    $groupName = if ($record.Group) { [string]$record.Group } else { '' }
    return Get-JackdawFallbackThumbnail -lookupKey ($record.Label + ' ' + $record.DisplayName + ' ' + $record.Hint) -group $groupName
}

function Get-ThumbnailSourceKey($record) {
    if (-not $record) { return $null }
    if ($record.PSObject.Properties['ThumbnailSourceKey'] -and $record.ThumbnailSourceKey) { return [string]$record.ThumbnailSourceKey }
    if ($record.Source -and $record.Source.anahtar) { return [string]$record.Source.anahtar }
    if ($record.anahtar) { return [string]$record.anahtar }
    if ($record.ResourceId) { return [string]$record.ResourceId }
    if ($record.id) { return [string]$record.id }
    if ($record.Kind -eq 'Catalog') { return [string]$record.Label }
    return $null
}

function Get-CachedThumbnailPath([string]$sourceKey) {
    if ([string]::IsNullOrWhiteSpace($sourceKey)) { return $null }
    $cacheRoot = Get-TextureCacheRoot
    if (-not $cacheRoot) { return $null }
    if (-not $script:textureCacheIndexed) {
        foreach ($file in Get-ChildItem -LiteralPath $cacheRoot -Filter *.png -File -ErrorAction SilentlyContinue) {
            $script:thumbnailPathCache[$file.BaseName] = $file.FullName
        }
        $script:textureCacheIndexed = $true
    }
    $safe = ($sourceKey -replace '[^A-Za-z0-9_.-]+', '_')
    if ($script:thumbnailPathCache.ContainsKey($safe)) { return $script:thumbnailPathCache[$safe] }
    return $null
}

function Get-QuickThumbnail($record) {
    if (-not $record) { return $null }
    # Hull items come through as raw catalog entries (anahtar/grup), not converted
    # Catalog records, so treat them the same way for thumbnail lookup.
    $isCatalog = ($record.Kind -eq 'Catalog') -or $record.anahtar -or $record.id
    $path = $null
    if ($isCatalog) {
        # PNG THUMBNAIL LOCK: catalog tiles may only resolve the exact PNG whose
        # filename is derived from this catalog key inside game-cache. Never trust
        # a previously assigned ImageSource here; older builds assigned model
        # renders to Thumbnail and those objects could otherwise survive refreshes.
        $sourceKey = Get-ThumbnailSourceKey $record
        $cached = Get-CachedThumbnailPath $sourceKey
        if ($cached) { $path = $cached }
        else { return Get-LibraryLoadingThumbnail }
    } elseif ($record.Thumbnail -is [Windows.Media.ImageSource]) {
        return $record.Thumbnail
    } elseif ($record.Texture -and (Test-Path -LiteralPath $record.Texture)) {
        $path = $record.Texture
    } elseif ($record.Thumbnail -and (Test-Path -LiteralPath $record.Thumbnail)) {
        $path = [string]$record.Thumbnail
    }
    if (-not $path) { return $null }
    $img = New-ThumbnailImageSource $path 72
    if ($img) {
        $thumbProp = $record.PSObject.Properties['Thumbnail']
        if ($thumbProp -and -not $thumbProp.IsReadOnly) { $record.Thumbnail = $img }
        return $img
    }
    return $null
}

function Queue-VisibleThumbnail($record, [int]$index, [int]$epoch) {
    if (-not $record -or $index -lt 0) { return }
    $sourceKey = Get-ThumbnailSourceKey $record
    $path = $null
    if ($sourceKey) { $path = Get-CachedThumbnailPath $sourceKey }
    if (-not $path -and $record.Kind -ne 'Catalog' -and $record.Kind -ne 'Group') {
        if ($record.Texture -and (Test-Path -LiteralPath $record.Texture -PathType Leaf)) { $path = [string]$record.Texture }
        elseif ($record.Thumbnail -is [string] -and (Test-Path -LiteralPath $record.Thumbnail -PathType Leaf)) { $path = [string]$record.Thumbnail }
    }
    if (-not $path) { return }
    $script:visibleThumbnailQueue.Enqueue([pscustomobject]@{
        Epoch = $epoch
        Index = $index
        Key = [string]$sourceKey
        Path = [string]$path
    })
}

function Process-VisibleThumbnailQueue {
    # Decode at most two 72px images per dispatcher pass so input and scrolling
    # run between PNG decodes instead of waiting on an entire texture category.
    $processed = 0
    while ($script:visibleThumbnailQueue.Count -gt 0 -and $processed -lt 2) {
        $work = $script:visibleThumbnailQueue.Dequeue()
        if ($work.Epoch -ne $script:visibleListEpoch) { continue }
        $index = [int]$work.Index
        if ($index -lt 0 -or $index -ge $script:visibleZoneRecords.Count) { continue }
        $record = $script:visibleZoneRecords[$index]
        $recordKey = Get-ThumbnailSourceKey $record
        if ($work.Key -and $recordKey -and $work.Key -ne $recordKey) { continue }
        $image = New-ThumbnailImageSource ([string]$work.Path) 72
        if (-not $image) { continue }

        $copy = $record | Select-Object *
        $copy.Thumbnail = $image
        $previousGuard = [bool]$script:syncingSelection
        $selectedZoneIndex = $zones.SelectedIndex
        $selectedPngIndex = $pngCollection.SelectedIndex
        $script:syncingSelection = $true
        try {
            $script:visibleZoneRecords[$index] = $copy
            if ($index -lt $zones.Items.Count) { $zones.Items[$index] = $copy }
            if ($index -lt $pngCollection.Items.Count) { $pngCollection.Items[$index] = $copy }
            if ($selectedZoneIndex -ge 0 -and $selectedZoneIndex -lt $zones.Items.Count) { $zones.SelectedIndex = $selectedZoneIndex }
            if ($selectedPngIndex -ge 0 -and $selectedPngIndex -lt $pngCollection.Items.Count) { $pngCollection.SelectedIndex = $selectedPngIndex }
        }
        finally { $script:syncingSelection = $previousGuard }
        $processed++
    }
    if ($script:visibleThumbnailQueue.Count -eq 0) { $script:visibleThumbnailTimer.Stop() }
}

function New-PanelPreviewImageSource([string]$path, [int]$decodeWidth = 640) {
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    $fullPath = [IO.Path]::GetFullPath($path)
    if ($script:lastPreviewImageSource -and $script:lastPreviewImagePath -eq $fullPath) {
        return $script:lastPreviewImageSource
    }
    try {
        $image = [Windows.Media.Imaging.BitmapImage]::new()
        $image.BeginInit()
        $image.CacheOption = 'OnLoad'
        $image.DecodePixelWidth = $decodeWidth
        $image.UriSource = [Uri]::new($fullPath)
        $image.EndInit()
        $image.Freeze()
        $script:lastPreviewImagePath = $fullPath
        $script:lastPreviewImageSource = $image
        return $image
    }
    catch { return $null }
}

function Start-CatalogWarm {
    if (-not $script:shipCatalog -or -not $script:gameFolder) { return }
    if ($script:thumbnailJob) {
        $runState = $script:thumbnailJob.State
        if ($runState -eq 'Running' -or $runState -eq 'NotStarted') { return }
        Remove-Job -Job $script:thumbnailJob -Force -ErrorAction SilentlyContinue
        $script:thumbnailJob = $null
    }
    $launcher = Get-PythonLauncher
    if (-not $launcher) { return }
    $extractor = Get-TextureExtractorScript
    if (-not (Test-Path -LiteralPath $extractor)) { return }
    if (-not $catalogPath -or -not (Test-Path -LiteralPath $catalogPath)) { return }
    $cacheRoot = Get-TextureCacheRoot
    if (-not $cacheRoot) { return }

    # Index the cache once, then reuse it on every category change instead of
    # rescanning hundreds of extracted PNGs from disk.
    if (-not $script:textureCacheIndexed) { $null = Get-CachedThumbnailPath '__index_only__' }
    $cacheHit = @{}
    foreach ($cachedKey in $script:thumbnailPathCache.Keys) { $cacheHit[$cachedKey] = $true }

    # Collect every catalog texture still missing from the cache. The measured
    # Jackdaw Hull set is promoted ahead of the general catalog so the complete
    # default ship material pass becomes available immediately after the sails.
    $jackdawHullKeys = @{
        'STD_Ornate_Wood_01A' = $true
        'STD_Wood_01A' = $true
        'STD_Wood_FloorDeck_02A' = $true
        'STD_Wood_Painted_Metal_01A' = $true
        'STD_Wood_PlanksHull_01A_6m' = $true
        'STD_Wood_PlanksHull_02A' = $true
        'STD_Wood_PlanksHullPainted_02A' = $true
        'STD_Wood_TrimDeco_01A' = $true
    }
    # Restore the complete library cache. The library had been fully populated
    # before the model update; limiting extraction to the open category caused
    # empty tiles throughout categories the user had not revisited yet.
    $needed = [Collections.Generic.List[object]]::new()
    foreach ($item in $script:shipCatalog.hedefler) {
        if (-not $item.kullanilabilir) { continue }
        $key = if ($item.anahtar) { $item.anahtar } elseif ($item.id) { $item.id } else { $item.ad }
        if ([string]::IsNullOrWhiteSpace([string]$key)) { continue }
        if ($cacheHit.ContainsKey([string]$key)) { continue }
        if ($script:thumbnailSkipped.Contains([string]$key)) { continue }
        [void]$needed.Add([pscustomobject]@{
            Key = [string]$key
            JackdawHull = $jackdawHullKeys.ContainsKey([string]$key)
            Hull = ($item.grup -eq 'hull')
        })
    }
    # Extract the default sail atlas first. The file is recovered from the
    # user's own game installation and is never bundled with the release.
    $ordered = @($needed | Sort-Object `
        @{ Expression = {
            if ($_.Key -eq 'PT_Jackdaw_04') { 0 }
            elseif ($_.JackdawHull) { 1 }
            elseif ($_.Hull) { 2 }
            else { 3 }
        } }, `
        @{ Expression = { $_.Key } })
    $work = [Collections.Generic.List[object]]::new()
    # Small batches keep scrolling/searching responsive. Apply-ThumbnailBackfill
    # schedules the next batch only after this one has completed.
    $maxWork = 8
    foreach ($o in $ordered) {
        if ($work.Count -ge $maxWork) { break }
        [void]$work.Add($o)
    }
    if ($work.Count -eq 0) { return }

    $script:thumbnailEpoch++
    $script:thumbnailJobEpoch = $script:thumbnailEpoch
    $script:thumbnailBatchHadSuccess = $false

    $sb = {
        param($workList, $launcher, $extractor, $game, $catalog, $cacheRoot)
        $out = [Collections.Generic.List[object]]::new()
        foreach ($w in $workList) {
            $key = [string]$w.Key
            $safe = ($key -replace '[^A-Za-z0-9_.-]+', '_')
            $output = Join-Path $cacheRoot ($safe + '.png')
            $dir = Split-Path -Parent $output
            if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
            $args = @($extractor, '--game', $game, '--catalog', $catalog, '--target', $key, '--output', $output)
            $success = $false
            try {
                $null = & $launcher @args 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $output)) { $success = $true }
            }
            catch { }
            [void]$out.Add([pscustomobject]@{ Key = $key; Path = $output; Success = $success })
        }
        return @($out)
    }

    try {
        $script:thumbnailJob = Start-Job -ScriptBlock $sb -ArgumentList $work, $launcher, $extractor, $script:gameFolder, $catalogPath, $cacheRoot
        $script:thumbnailTimer.Start()
    }
    catch {
        $script:thumbnailJob = $null
    }
}

function Apply-ThumbnailBackfill {
    $job = $script:thumbnailJob
    if (-not $job) { return }
    $results = Receive-Job -Job $job -ErrorAction SilentlyContinue
    if ($results -and $script:thumbnailJobEpoch -eq $script:thumbnailEpoch) {
        foreach ($r in $results) {
            $key = [string]$r.Key
            if ([string]::IsNullOrWhiteSpace($key)) { continue }
            if ([bool]$r.Success) {
                $script:thumbnailBatchHadSuccess = $true
                $safeKey = ($key -replace '[^A-Za-z0-9_.-]+', '_')
                $script:thumbnailPathCache[$safeKey] = [string]$r.Path
                if ($script:thumbnailSkipped.Contains($key)) { [void]$script:thumbnailSkipped.Remove($key) }
                # A sail may currently be showing the bundled white fallback.
                # Drop that cached material so Refresh-JackdawMaterials loads
                # the newly extracted PT_Jackdaw_04 image from game-cache.
                if ($script:exactTextureMaterials.ContainsKey($key)) {
                    $script:exactTextureMaterials.Remove($key)
                }
            } else {
                # Failed this attempt; don't retry it forever in the background loop.
                [void]$script:thumbnailSkipped.Add($key)
                continue
            }
            for ($i = 0; $i -lt $script:visibleZoneRecords.Count; $i++) {
                $rec = $script:visibleZoneRecords[$i]
                $recKey = Get-ThumbnailSourceKey $rec
                if (-not $recKey -or $recKey -ne $key) { continue }
                Queue-VisibleThumbnail $rec $i $script:visibleListEpoch
            }
            if ($script:visibleThumbnailQueue.Count -gt 0) { $script:visibleThumbnailTimer.Start() }
        }
    }
    if ($script:thumbnailBatchHadSuccess) { try { Refresh-JackdawMaterials } catch { } }
    if ($job.State -in 'Completed','Failed','Stopped') {
        $script:thumbnailTimer.Stop()
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        $script:thumbnailJob = $null
        if ($script:thumbnailBatchHadSuccess) {
            Start-CatalogWarm
        }
    }
}

function Get-RecordOriginalTexturePath($record) {
    if ($record -and $record.Kind -eq 'Zone' -and (Get-Command Get-NativeFinishPath -ErrorAction SilentlyContinue)) {$nativePath=Get-NativeFinishPath $record.Component $record.Zone;if ($nativePath) {return $nativePath}}
    if (-not $record) { return $null }
    if ($record.OriginalTexture -and (Test-Path -LiteralPath $record.OriginalTexture)) { return $record.OriginalTexture }
    if ($record.Kind -eq 'Catalog') {
        $sourceKey = if ($record.Source -and $record.Source.anahtar) { [string]$record.Source.anahtar } elseif ($record.ResourceId) { [string]$record.ResourceId } else { [string]$record.Label }
        # Cache-only on the UI thread: never run the Python forge extractor here,
        # or clicking a texture preview freezes the app. The background warmer
        # fills the cache; the explicit Export button handles on-demand extraction.
        $exact = Get-CachedThumbnailPath $sourceKey
        if ($exact -and (Test-Path -LiteralPath $exact)) { return $exact }
        return $null
    }
    if ($record.Texture -and (Test-Path -LiteralPath $record.Texture)) { return $record.Texture }
    return $null
}

function Get-RecordThumbnailSource($record) {
    if (-not $record) { return $null }

    $thumbPath = $null
    if ($record.Kind -eq 'Catalog') {
        # Same strict lock as Get-QuickThumbnail: a catalog preview can only be
        # sourced from its key-matched extracted PNG, never a generic model image.
        $sourceKey = if ($record.Source -and $record.Source.anahtar) { [string]$record.Source.anahtar } elseif ($record.ResourceId) { [string]$record.ResourceId } else { [string]$record.Label }
        # Cache-only on the UI thread; on-demand forge extraction is the job of the
        # background warmer and the explicit Export button, never the click path.
        $exact = Get-CachedThumbnailPath $sourceKey
        if ($exact -and (Test-Path -LiteralPath $exact)) {
            $thumbPath = $exact
        }
        else { return Get-LibraryLoadingThumbnail }
    } elseif ($record.Thumbnail -is [Windows.Media.ImageSource]) {
        return $record.Thumbnail
    } elseif ($record.Texture -and (Test-Path -LiteralPath $record.Texture)) {
        $thumbPath = $record.Texture
    }
    if (-not $thumbPath) {
        $thumbPath = Get-RecordDisplayTexturePath $record
    }
    $thumb = New-ThumbnailImageSource $thumbPath 72
    if ($thumb) {
        $record.Thumbnail = $thumb
        return $thumb
    }
    return $null
}

function Show-PreviewImageWindow([string]$path, [string]$title) {
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path)) { return }
    $image = [Windows.Media.Imaging.BitmapImage]::new()
    $image.BeginInit()
    $image.CacheOption = 'OnLoad'
    $image.UriSource = [Uri]::new($path)
    $image.EndInit()
    $image.Freeze()

    $safeTitle = if ($title) { $title } else { 'PNG Preview' }
    $safePath = $path
    $viewerXaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="$safeTitle"
        Width="1100" Height="900"
        WindowStartupLocation="CenterOwner"
        ResizeMode="CanResize"
        Background="#08131C"
        Foreground="#EADFC7">
  <Grid Margin="14">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <TextBlock Text="$safeTitle" FontSize="18" FontWeight="SemiBold" Margin="0,0,0,10"/>
    <Border Grid.Row="1" Background="#051018" CornerRadius="8" Padding="12">
      <ScrollViewer HorizontalScrollBarVisibility="Auto" VerticalScrollBarVisibility="Auto">
        <Image x:Name="ZoomImage" Stretch="None"/>
      </ScrollViewer>
    </Border>
    <TextBlock Grid.Row="2" Text="$safePath" Foreground="#91A8B3" FontSize="11" Margin="2,10,0,0" TextWrapping="Wrap"/>
  </Grid>
</Window>
"@
    $reader = [System.Xml.XmlNodeReader]::new([xml]$viewerXaml)
    $viewer = [Windows.Markup.XamlReader]::Load($reader)
    $viewer.FindName('ZoomImage').Source = $image
    $viewer.Owner = $window
    [void]$viewer.ShowDialog()
}

function Get-ExportFolder([string]$category) {
    $bucket = if ([string]::IsNullOrWhiteSpace($category)) { 'misc' } else { ($category.ToLowerInvariant() -replace '[^a-z0-9]+', '-') }
    $path = Join-Path $exportRoot $bucket
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return $path
}

function Get-ExactTextureTarget($key) {
    if (-not $script:shipCatalog -or [string]::IsNullOrWhiteSpace([string]$key)) { return $null }
    $needle = ([string]$key).Trim().ToLowerInvariant()
    foreach ($item in $script:shipCatalog.hedefler) {
        $candidates = @($item.id, $item.anahtar, $item.kisa_ad, $item.ad) | Where-Object { $_ }
        foreach ($candidate in $candidates) {
            if ($needle -eq ([string]$candidate).Trim().ToLowerInvariant()) {
                return $item
            }
        }
    }
    foreach ($item in $script:shipCatalog.hedefler) {
        $candidates = @($item.id, $item.anahtar, $item.kisa_ad, $item.ad) | Where-Object { $_ }
        foreach ($candidate in $candidates) {
            if (([string]$candidate).ToLowerInvariant().Contains($needle)) {
                return $item
            }
        }
    }
    return $null
}

function Get-TextureExtractorScript {
    return (Join-Path $appRoot 'tools\jackdaw_extract_texture.py')
}

function Get-PythonLauncher {
    $localCandidates = @(
        (Join-Path $appRoot 'python\pythonw.exe'),
        (Join-Path $appRoot 'python\python.exe'),
        (Join-Path $appRoot 'pythonw.exe'),
        (Join-Path $appRoot 'python.exe'),
        'C:\Program Files\PyManager\python.exe',
        'C:\Users\YOUR_USER\AppData\Local\Programs\Python\Python314\python.exe',
        'C:\Users\YOUR_USER\AppData\Local\Programs\Python\Python313\python.exe'
    )
    foreach ($candidate in $localCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    foreach ($candidate in @('py', 'python3', 'python')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) { return $candidate }
    }
    return $null
}

function Invoke-ExactTextureExport([string]$targetKey, [string]$outputPath) {
    if (-not $script:gameFolder) { return $null }
    $helper = Get-TextureExtractorScript
    if (-not (Test-Path -LiteralPath $helper)) { return $null }
    $target = Get-ExactTextureTarget $targetKey
    if (-not $target) { return $null }
    $launcher = Get-PythonLauncher
    if (-not $launcher) { return $null }
    $outputDir = Split-Path -Parent $outputPath
    if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }
    $args = @(
        $helper,
        '--game', $script:gameFolder,
        '--catalog', $catalogPath,
        '--target', ($(if ($target.anahtar) { $target.anahtar } else { $target.id })),
        '--output', $outputPath
    )
    try {
        $result = & $launcher @args 2>&1
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $outputPath)) {
            return $outputPath
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-ExactTexturePath([string]$targetKey) {
    if ([string]::IsNullOrWhiteSpace($targetKey)) { return $null }
    $cacheRoot = Get-TextureCacheRoot
    if (-not $cacheRoot) { return $null }
    $safe = ($targetKey -replace '[^A-Za-z0-9_.-]+', '_')
    $cachedPath = Join-Path $cacheRoot ($safe + '.png')
    if (Test-Path -LiteralPath $cachedPath) { return $cachedPath }
    return (Invoke-ExactTextureExport -targetKey $targetKey -outputPath $cachedPath)
}

function Get-SelectedTextureSourceKey($selected) {
    if (-not $selected) { return $null }
    if ($selected.Kind -eq 'Catalog') {
        if ($selected.Source -and $selected.Source.anahtar) { return [string]$selected.Source.anahtar }
        if ($selected.ResourceId) { return [string]$selected.ResourceId }
        return [string]$selected.Label
    }
    return Get-DefaultAppearanceTextureKey -component $selected.Component -zone $selected.Zone
}

function Export-SelectedTexture([object]$selected) {
    if (-not $selected) { return $null }
    if (-not $script:gameFolder) {
        [Windows.MessageBox]::Show('Pick the Black Flag Resynced game folder first.','Game not found') | Out-Null
        return $null
    }
    $sourceKey = Get-SelectedTextureSourceKey $selected
    if ([string]::IsNullOrWhiteSpace([string]$sourceKey)) {
        [Windows.MessageBox]::Show('This selection does not have a known game texture key yet.','Nothing to export') | Out-Null
        return $null
    }

    $projectFolder = if ($script:currentProject) { [IO.Path]::GetFullPath([string]$script:currentProject) } else { $appRoot }
    $editableDir = Join-Path $projectFolder 'editable'
    New-Item -ItemType Directory -Force -Path $editableDir | Out-Null

    $safeName = ([string]$sourceKey -replace '[^A-Za-z0-9_.-]+', '_').Trim('_')
    if ([string]::IsNullOrWhiteSpace($safeName)) { $safeName = 'jackdaw_texture' }
    $exportDir = Get-ExportFolder $selected.Group
    $outputPath = Join-Path $exportDir ($safeName + '.png')
    $extracted = Invoke-ExactTextureExport -targetKey $sourceKey -outputPath $outputPath
    if (-not $extracted) {
        [Windows.MessageBox]::Show(
            "We couldn't export that texture yet. Make sure Python is installed and the game folder is set, then try again.",
            'Export failed'
        ) | Out-Null
        return $null
    }

    $selected.Texture = $extracted
    $selected.Thumbnail = $extracted
    if ($selected.Geometry) {
        $material = New-TextureMaterial $extracted
        $selected.Geometry.Material = $material
        $selected.Geometry.BackMaterial = $material
        Set-AppliedPreviewMaterial $selected $material
    }
    Copy-Item -LiteralPath $extracted -Destination (Join-Path $editableDir (Split-Path $extracted -Leaf)) -Force
    Save-PreviewCache $selected $extracted
    if ($selected.Component -eq $sailComponentIndex) { Set-SailViewMode 'Custom preview' }
    Apply-SailViewMode
    Update-TexturePreview
    Set-UiText $footer "Exported $(Split-Path $extracted -Leaf) to the app's exported-pngs folder."
    Set-DesignProgress 'Texture exported.' 100 "Exported: $(Split-Path $extracted -Leaf)"
    Reset-DesignProgressSoon
    return $extracted
}

function Get-DefaultAppearanceTextureKey([int]$component, [int]$zone) {
    switch ($component) {
        # These bindings come from ShipVanity_Hull -> Jackdaw Hull's measured
        # EntityGroup/Material/TextureSet chain.  They are recovered from the
        # installed game at runtime; no Ubisoft texture ships with the app.
        0 { return 'STD_Wood_PlanksHullPainted_02A' }
        1 { return 'STD_Wood_FloorDeck_02A' }
        2 { return 'STD_Wood_TrimDeco_01A' }
        3 { return 'STD_Ornate_Wood_01A' }
        4 { return 'STD_Wood_01A' }
        5 { return 'STD_Wood_Mast_01A' }
        6 {
            # Runtime-extracted from the user's installed game. Never ship the
            # copyrighted atlas inside the Workshop release.
            return 'PT_Jackdaw_04'
        }
6 {
            # Runtime-extracted from the user's installed game. Never ship the
            # copyrighted atlas inside the Workshop release.
            return 'PT_Jackdaw_04'
        }
        7 { return 'PT_Jackdaw_Pirate_01' }
        8 {
            # Cannon diffuse from the user's extracted game cache.
            return 'UNQ_COM_Culverin_01A'
        }
        9 { return 'UNQ_COM_SwivelGun_01A' }
        10 { return 'UNQ_COM_LightMortar_01A' }
        default { return $null }
    }
}

function Get-DefaultAppearanceMaterial([int]$component, [int]$zone) {
    if (Get-Command Get-NativeFinishMaterial -ErrorAction SilentlyContinue) {$nativeMaterial=Get-NativeFinishMaterial $component $zone;if ($nativeMaterial) {return $nativeMaterial}}
    $key = Get-DefaultAppearanceTextureKey $component $zone
    if ($key) {
        if (-not $script:exactTextureMaterials.ContainsKey($key)) {
            # Use only already-cached textures here so model load never blocks on a
            # subprocess; the background cache warmer fills the rest in later.
            $path = Get-CachedThumbnailPath $key
            if (-not $path -and $component -eq 6 -and $key -eq 'PT_Jackdaw_04') {
                # Use a neutral canvas only while the authentic atlas is being
                # recovered from the local game in the background.
                $bundledWhite = Join-Path $appRoot 'assets\jackdaw-sail-white.png'
                if (Test-Path -LiteralPath $bundledWhite -PathType Leaf) { $path = $bundledWhite }
            }
            if ($path) {
                try {
                    return $script:exactTextureMaterials[$key] = New-TextureMaterial $path
                }
                catch {
                    # Cache write succeeded but material failed; leave unset so a
                    # later warm pass retries instead of caching a dead null.
                    $script:exactTextureMaterials.Remove($key)
                }
            } else {
                # Not cached yet - don't store anything, so the next refresh pass
                # retries once the background warmer writes the file to disk.
            }
        }
        if ($script:exactTextureMaterials.ContainsKey($key) -and $null -ne $script:exactTextureMaterials[$key]) {
            return $script:exactTextureMaterials[$key]
        }
    }
    return New-ZoneMaterial $component $zone
}

function Prime-DefaultJackdawTextures {
    # Start filling the disk cache in the background instead of extracting
    # synchronously at model load (which previously froze the UI on launch).
    Start-CatalogWarm
}

function Get-ClayPreviewMaterial {
    if (-not $script:clayPreviewMaterial) {
        # Blender-style neutral solid shading: medium gray diffuse clay with a
        # restrained specular response so small hull and rigging forms remain
        # legible without resembling painted or metallic material.
        $group = [Windows.Media.Media3D.MaterialGroup]::new()
        $diffuseBrush = [Windows.Media.SolidColorBrush]::new(
            [Windows.Media.Color]::FromRgb(142,142,142))
        $specularBrush = [Windows.Media.SolidColorBrush]::new(
            [Windows.Media.Color]::FromRgb(62,62,62))
        $diffuseBrush.Freeze()
        $specularBrush.Freeze()
        $group.Children.Add([Windows.Media.Media3D.DiffuseMaterial]::new($diffuseBrush))
        $group.Children.Add([Windows.Media.Media3D.SpecularMaterial]::new($specularBrush,32.0))
        $group.Freeze()
        $script:clayPreviewMaterial = $group
    }
    return $script:clayPreviewMaterial
}

function Update-TextureToggleButton {
    if (-not $textureToggle) { return }
    $textureToggle.Content = if ($script:texturesEnabled) { 'Textures: On' } else { 'Textures: Off' }
    $textureToggle.ToolTip = 'Whole ship: toggle all textures and applied designs / neutral grey clay. Geometry, UVs and game files are unchanged.'
}

function Get-PreviewMaterialKey($zone) {
    # Standalone preview tabs can reuse component/zone numbers. Scope to model.
    return '{0}|{1}|{2}' -f $script:modelPath, $zone.Component, $zone.Zone
}

function Set-AppliedPreviewMaterial($zone, $material) {
    if (-not $script:appliedPreviewMaterials) { $script:appliedPreviewMaterials = @{} }
    $script:appliedPreviewMaterials[(Get-PreviewMaterialKey $zone)] = $material
}

function Apply-SailViewMode {
    # One display policy for EVERY component, including newly added ship parts.
    # Pending imported/generated PNGs do not become applied materials here.
    $script:currentSailViewMode = Get-SailViewMode
    foreach ($zone in $zoneRecords) {
        if (-not $zone.Geometry) { continue }
        if (-not $script:texturesEnabled -or $script:currentSailViewMode -eq 'Model only') {
            $material = Get-ClayPreviewMaterial
        } else {
            $material = $zone.BaseMaterial
            $key = Get-PreviewMaterialKey $zone
            if ($script:appliedPreviewMaterials -and $script:appliedPreviewMaterials.ContainsKey($key) -and
                ($zone.Component -ne $sailComponentIndex -or $script:currentSailViewMode -eq 'Custom preview')) {
                $material = $script:appliedPreviewMaterials[$key]
            }
        }
        $zone.Geometry.Material = $material
        $zone.Geometry.BackMaterial = $material
    }
    Update-TextureToggleButton
}

function Refresh-JackdawMaterials {
    # Re-resolve the default appearance material for every zone and push it onto
    # the geometry. Runs after the background warmer fills the disk cache so
    # textures that weren't ready at model load finally show up on the model.
    foreach ($zone in $zoneRecords) {
        if (-not $zone.Geometry) { continue }
        try {
            $zone.BaseMaterial = Get-DefaultAppearanceMaterial $zone.Component $zone.Zone
            $zone.Geometry.Material = $zone.BaseMaterial
            $zone.Geometry.BackMaterial = $zone.BaseMaterial
        } catch { }
    }
    Apply-SailViewMode
}

function New-ZoneMaterial([int]$component, [int]$zone) {
    # Zones 0-4: Plain white base for modding
    if ($zone -lt 5) {
        return [Windows.Media.Media3D.DiffuseMaterial]::new([Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(255,255,255)))
    }
    $color = [Windows.Media.ColorConverter]::ConvertFromString($componentColors[$component])
    $factor = 1.0
    $color = [Windows.Media.Color]::FromRgb(
        [byte][Math]::Min(255,$color.R*$factor),
        [byte][Math]::Min(255,$color.G*$factor),
        [byte][Math]::Min(255,$color.B*$factor))
    return [Windows.Media.Media3D.DiffuseMaterial]::new([Windows.Media.SolidColorBrush]::new($color))
}

function Get-ZoneHint([int]$component, [int]$zone) {
    switch ($component) {
        0 { return "Use this on the outer hull paint and side plating. This is one of the blue Jackdaw hull areas the preview can isolate." }
        1 { return "Use this on the deck boards and upper walking surfaces." }
        2 { return "Use this on the bow/prow detail and front trim." }
        3 { return "Use this on the stern cabin and rear trim." }
        4 { return "Use this on the standing rigging, ropework, and small structural lines." }
        5 { return "Use this on the masts and yardarms. The preview keeps these blue-toned to match the hull styling." }
        6 {
            $group = switch ($zone) {
                { $_ -lt 11 } { 'mainmast square or wing cloth' }
                { $_ -lt 23 } { 'foremast square or wing cloth' }
                default       { 'bowsprit jib cloth' }
            }
            return "Extracted $group, surface $($zone + 1) of 26. This surface is independently clickable; original UV mapping is preserved."
        }
        7 { return "Recovered high-detail Jackdaw mast flag with the original pirate-pattern UV mapping." }
        8 { return "Use this on the Jackdaw broadside cannons (culverins). Surface $($zone + 1) is independently clickable with its original UVs." }
        9 { return "Use this on the Jackdaw swivel guns. Surface $($zone + 1) is independently clickable with its original UVs." }
        10 { return "Use this on the Jackdaw light mortar and its carriage. Surface $($zone + 1) keeps its original UVs." }
        11 { return "Use this on the ship lanterns. Placed from decoded in-game positions; original UVs preserved." }
        12 { return "Use this on the loose rigging parts. Surface $($zone + 1) with original UVs." }
        13 { return "Use this on the ship greebles (figureheads, bowsprit trim, deck details). Surface $($zone + 1) with original UVs." }
        14 { return "Jackdaw ram surface $($zone + 1). The original mesh UV coordinates are preserved." }
        15 { return "Jackdaw rudder surface $($zone + 1). The original mesh UV coordinates are preserved." }
        default { return "This texture zone is part of the Jackdaw preview." }
    }
}

function Get-CategoryComponents([string]$category) {
    switch ($category) {
        'Sails' { return @(6) }
        'Flags' { return @(7) }
        'Figureheads' { return @() }
        'Wheels' { return @() }
        'Hulls' { return @(0,1,2,3,4,5) }
        'Cabin' { return @(3) }
        'Cannons' { return @(8) }
        'Mortars' { return @(10) }
        'Sail Regions' { return @(6) }
        'Hull Regions' { return @(0) }
        'Masts' { return @(5) }
        'Rigging' { return @(4,12) }
        'Flag Regions' { return @(7) }
        'Weapon Regions' { return @(8,9,10) }
        'Lanterns' { return @(11) }
        'Details' { return @(1,2,3,13) }
        'Ram' { return @(14) }
        'Rudder' { return @(15) }
        default { return @(6) }
    }
}

function Get-CatalogGroup([string]$category) {
    switch ($category) {
        'Sails' { return 'sail' }
        'Flags' { return 'flag' }
        'Figureheads' { return 'figurehead' }
        'Wheels' { return 'wheel' }
        'Hulls' { return 'hull' }
        'Cabin' { return 'cabin' }
        'Cannons' { return 'cannon' }
        'Mortars' { return 'cannon' }
        default { return $null }
    }
}

function Load-ShipCatalog {
    if (-not (Test-Path -LiteralPath $catalogPath)) { return $null }
    try {
        return (Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Format-CatalogLabel($item) {
    $name = if ($item.kisa_ad) { $item.kisa_ad } else { $item.ad }
    $risk = if ($item.risk) { $item.risk } else { 'UNKNOWN' }
    $size = if ($item.w -and $item.h) { "{0}x{1}" -f $item.w, $item.h } else { 'unknown' }
    return "{0}  |  {1}  |  {2}" -f $name, $size, $risk
}

function Convert-CatalogRecord($item, [int]$index) {
    $ships = @()
    if ($item.gemi_siniflari_adli) {
        $ships = @($item.gemi_siniflari_adli)
    } elseif ($item.gemi_siniflari) {
        $ships = @($item.gemi_siniflari.PSObject.Properties.Name)
    }
    $shipText = if ($ships.Count -gt 0) { $ships -join ', ' } elseif ($item.alt_tur) { [string]$item.alt_tur } elseif ($item.kisa_ad) { [string]$item.kisa_ad } else { 'catalog texture' }
    [pscustomobject]@{
        Label = Format-CatalogLabel $item
        DisplayName = if ($item.ad) { $item.ad } elseif ($item.kisa_ad) { $item.kisa_ad } else { Format-CatalogLabel $item }
        Summary = if ($shipText) { $shipText } else { 'catalog texture' }
        Size = if ($item.w -and $item.h) { "{0}x{1}" -f $item.w, $item.h } else { 'unknown' }
        State = if ($item.kullanilabilir) { 'catalog' } else { 'locked' }
        Thumbnail = $null
        Component = -1
        Zone = $index
        MaterialID = $null
        Geometry = $null
        OriginalTexture = $null
        Texture = $null
        Hint = if ($item.kapsam_kaniti) { $item.kapsam_kaniti } elseif ($item.uyari) { $item.uyari } else { 'Catalog entry from the ShipWorkshop target list.' }
        Kind = 'Catalog'
        ResourceId = $item.id
        Group = $item.grup
        Risk = $item.risk
        ShipFamilies = $shipText
        Source = $item
    }
}

function Convert-ZoneRecord($record) {
    $textureLeaf = if ($record.Texture -and (Test-Path -LiteralPath $record.Texture)) { Split-Path $record.Texture -Leaf } else { 'No PNG yet' }
    $materialText = if ($null -ne $record.MaterialID) { '0x{0:X16}' -f [UInt64]$record.MaterialID } else { 'unknown material' }
    $partName = if ($record.Component -ge 0 -and $record.Component -lt $componentNames.Count) { $componentNames[$record.Component] } else { 'Ship part' }
    [pscustomobject]@{
        Label = "$partName - surface $($record.Zone + 1)"
        DisplayName = "$partName - surface $($record.Zone + 1)"
        Summary = "Material $materialText"
        Size = '-'
        State = if ($record.Texture) { $textureLeaf } else { 'SOURCE MAP PENDING' }
        Thumbnail = $record.Texture
        Component = $record.Component
        Zone = $record.Zone
        MaterialID = $record.MaterialID
        Geometry = $record.Geometry
        OriginalTexture = $record.Texture
        Texture = $record.Texture
        Hint = "$($record.Hint) Material ID: $materialText"
        Kind = 'Zone'
        ResourceId = $null
        Group = $componentNames[$record.Component]
        Risk = 'LOCAL'
        ShipFamilies = $componentNames[$record.Component]
        Source = $record
    }
}

function Get-PrimaryFamilyLabel($item) {
    if (-not $item) { return $null }
    if ($item.gemi_siniflari_adli -and $item.gemi_siniflari_adli.Count -gt 0) {
        return [string]$item.gemi_siniflari_adli[0]
    }
    if ($item.gemi_siniflari) {
        $keys = @($item.gemi_siniflari.PSObject.Properties.Name)
        if ($keys.Count -gt 0) { return [string]$keys[0] }
    }
    if ($item.ShipFamilies) {
        $split = @($item.ShipFamilies -split '\s*\|\s*')
        if ($split.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$split[0])) {
            return [string]$split[0]
        }
    }
    return $null
}

function Get-ShipFamilyLabels($item) {
    if (-not $item) { return @() }
    $labels = [Collections.Generic.List[string]]::new()
    if ($item.gemi_siniflari_adli) {
        foreach ($label in @($item.gemi_siniflari_adli)) {
            if ([string]::IsNullOrWhiteSpace([string]$label)) { continue }
            [void]$labels.Add([string]$label)
        }
    } elseif ($item.gemi_siniflari) {
        foreach ($label in @($item.gemi_siniflari.PSObject.Properties.Name)) {
            if ([string]::IsNullOrWhiteSpace([string]$label)) { continue }
            [void]$labels.Add([string]$label)
        }
    }
    if ($labels.Count -eq 0 -and $item.ShipFamilies) {
        foreach ($label in @($item.ShipFamilies -split '\s*\|\s*')) {
            if ([string]::IsNullOrWhiteSpace([string]$label)) { continue }
            [void]$labels.Add([string]$label)
        }
    }
    if ($labels.Count -eq 0) { return @() }
    return @($labels | Select-Object -Unique)
}

function New-HullFamilyGroup([string]$family, [object[]]$items, [bool]$expanded) {
    $familyName = if ([string]::IsNullOrWhiteSpace($family)) { 'Unsorted Hulls' } else { $family }
    $firstKey = if ($items.Count -gt 0) { Get-ThumbnailSourceKey $items[0] } else { $null }
    [pscustomobject]@{
        Label = $familyName
        DisplayName = if ($expanded) { "▾ $familyName" } else { "▸ $familyName" }
        Summary = if ($items.Count -eq 1) { '1 texture set' } else { "{0} texture sets" -f $items.Count }
        Size = '-'
        State = 'group'
        Thumbnail = Get-LibraryLoadingThumbnail
        ThumbnailSourceKey = $firstKey
        Component = -1
        Zone = -1
        MaterialID = $null
        Geometry = $null
        OriginalTexture = $null
        Texture = $null
        Hint = "Click to $(if ($expanded) { 'collapse' } else { 'expand' }) this texture set."
        Kind = 'Group'
        ResourceId = $null
        Group = $familyName
        Risk = 'INFO'
        ShipFamilies = $familyName
        IsGroupHeader = $true
        GroupKey = $familyName
        IsExpanded = $expanded
        ChildCount = $items.Count
    }
}

function Format-HullLeaf($child, [string]$family) {
    $name = if ($child.kisa_ad) { [string]$child.kisa_ad } elseif ($child.ad) { [string]$child.ad } elseif ($child.anahtar) { [string]$child.anahtar } else { '' }
    $ships = if ($child.gemi_siniflari_adli) { @($child.gemi_siniflari_adli) } elseif ($child.gemi_siniflari) { @($child.gemi_siniflari.PSObject.Properties.Name) } else { @() }
    $shipText = if ($ships.Count -gt 0) { $ships -join ', ' } elseif ($child.alt_tur) { [string]$child.alt_tur } else { $name }
    [pscustomobject]@{
        Label = $name
        DisplayName = '   ' + $name
        Summary = if ($shipText) { $shipText } else { 'hull texture' }
        Size = if ($child.w -and $child.h) { "{0}x{1}" -f $child.w, $child.h } else { 'unknown' }
        State = if ($child.kullanilabilir) { 'catalog' } else { 'locked' }
        Thumbnail = Get-LibraryLoadingThumbnail
        ThumbnailSourceKey = Get-ThumbnailSourceKey $child
        Component = -1
        Zone = -1
        MaterialID = $null
        Geometry = $null
        OriginalTexture = $null
        Texture = $null
        Hint = if ($child.kapsam_kaniti) { $child.kapsam_kaniti } elseif ($child.uyari) { $child.uyari } else { 'Hull texture variant for this ship family.' }
        Kind = 'Catalog'
        ResourceId = $child.id
        Group = 'hull'
        Risk = $child.risk
        ShipFamilies = $shipText
        Source = $child
        IsGroupHeader = $false
        GroupKey = $family
    }
}

function Get-HullVisibleRecords([object[]]$items) {
    $results = [Collections.Generic.List[object]]::new()
    $grouped = @{}
    foreach ($item in $items) {
        $families = @(Get-ShipFamilyLabels $item)
        if ($families.Count -eq 0) { $families = @('Unsorted Hulls') }
        foreach ($family in $families) {
            if (-not $grouped.ContainsKey($family)) {
                $grouped[$family] = [Collections.Generic.List[object]]::new()
            }
            [void]$grouped[$family].Add($item)
        }
    }

    $orderedFamilies = @(
        $grouped.Keys |
            Sort-Object @{ Expression = { if ($_ -match 'Jackdaw') { 0 } elseif ($_ -match 'HMS Prince') { 1 } elseif ($_ -match 'Brig') { 2 } else { 3 } } }, { $_ }
    )

    foreach ($family in $orderedFamilies) {
        $children = @($grouped[$family])
        $expanded = $script:expandedHullGroups.Contains($family)
        if ($script:searchQuery -and -not [string]::IsNullOrWhiteSpace($script:searchQuery)) {
            $matchingChildren = @($children | Where-Object { Record-MatchesSearch $_ $script:searchQuery })
            if ($matchingChildren.Count -eq 0 -and -not (Record-MatchesSearch (New-HullFamilyGroup $family $children $true) $script:searchQuery)) {
                continue
            }
            $header = New-HullFamilyGroup $family $matchingChildren $true
            [void]$results.Add($header)
            foreach ($child in $matchingChildren) {
                $childCopy = Format-HullLeaf $child $family
                [void]$results.Add($childCopy)
            }
            continue
        }

        $header = New-HullFamilyGroup $family $children $expanded
        [void]$results.Add($header)
        if ($expanded) {
            foreach ($child in $children) {
                $childCopy = Format-HullLeaf $child $family
                [void]$results.Add($childCopy)
            }
        }
    }
    return @($results)
}

function Get-VisibleRecords([string]$category) {
    $group = Get-CatalogGroup $category
    if (-not $group -or -not $script:shipCatalog) { return @() }
    $items = @($script:shipCatalog.hedefler | Where-Object { $_.grup -eq $group -and $_.kullanilabilir })
    if ($category -eq 'Sails') {
        $items = @(
            $items |
                Sort-Object `
                    @{ Expression = { if (($_.ad -match 'Jackdaw') -or ($_.kisa_ad -match 'Jackdaw')) { 0 } else { 1 } } }, `
                    @{ Expression = { if ($_.kisa_ad) { $_.kisa_ad } else { $_.ad } } }
        )
    } elseif ($category -eq 'Hulls') {
        $items = @(
            $items |
                Sort-Object `
                    @{ Expression = { if ($_.gemi_siniflari_adli) { ($_.gemi_siniflari_adli -join ', ') } elseif ($_.gemi_siniflari) { ($_.gemi_siniflari.PSObject.Properties.Name -join ', ') } elseif ($_.alt_tur) { [string]$_.alt_tur } else { '' } } }, `
                    @{ Expression = { if ($_.kisa_ad) { $_.kisa_ad } else { $_.ad } } }
        )
        if (-not $script:hullGroupsPrimed) {
            foreach ($item in $items) {
                foreach ($family in @(Get-ShipFamilyLabels $item)) {
                    if ([string]::IsNullOrWhiteSpace($family)) { continue }
                    if ($family -match 'Jackdaw' -or $family -match 'HMS Prince' -or $family -match 'Brig') { [void]$script:expandedHullGroups.Add($family) }
                }
            }
            if ($script:expandedHullGroups.Count -eq 0 -and $items.Count -gt 0) {
                $firstFamily = Get-PrimaryFamilyLabel $items[0]
                if ($firstFamily) { [void]$script:expandedHullGroups.Add($firstFamily) }
            }
            $script:hullGroupsPrimed = $true
        }
        return Get-HullVisibleRecords $items
    } elseif ($category -eq 'Mortars') {
        $items = @($items | Where-Object { ((($_.ad + ' ') + ($_.kisa_ad + ' ') + ($_.id + ' ') + ($_.anahtar)) -match '(?i)mortar') })
        $items = @($items | Sort-Object @{ Expression = { if ($_.kisa_ad) { $_.kisa_ad } else { $_.ad } } })
        return @(
            for ($i = 0; $i -lt $items.Count; $i++) {
                Convert-CatalogRecord $items[$i] $i
            }
        )
    }
    return @(
        for ($i = 0; $i -lt $items.Count; $i++) {
            Convert-CatalogRecord $items[$i] $i
        }
    )
}

function Get-DefaultJackdawSailIndex {
    if (-not $script:visibleZoneRecords -or $script:visibleZoneRecords.Count -eq 0) { return -1 }
    $priority = @(
        'Jackdaw_03',
        'Jackdaw_02',
        'PT_Jackdaw_06',
        'PT_Jackdaw_05',
        'PT_Jackdaw_04',
        'Bulk_Sail_PT_Jackdaw_04'
    )
    foreach ($needle in $priority) {
        for ($i = 0; $i -lt $script:visibleZoneRecords.Count; $i++) {
            $record = $script:visibleZoneRecords[$i]
            $text = @($record.Label, $record.DisplayName, $record.Source.ad, $record.Source.kisa_ad) -join ' '
            if ($text -match [regex]::Escape($needle)) {
                return $i
            }
        }
    }
    return 0
}

function Get-SourceRecords([string]$category) {
    $selectedComponents = @(Get-CategoryComponents $category)
    return @($zoneRecords | Where-Object { $selectedComponents -contains $_.Component } | ForEach-Object { Convert-ZoneRecord $_ })
}

function Record-MatchesSearch($record, [string]$query) {
    if ([string]::IsNullOrWhiteSpace($query)) { return $true }
    $haystack = @(
        $record.DisplayName
        $record.Summary
        $record.Size
        $record.State
        $record.Label
        $record.Risk
        $record.ShipFamilies
        $record.Group
        $record.ResourceId
        $record.Hint
    ) -join ' '
    return $haystack.IndexOf($query, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Refresh-VisibleList {
    # A category refresh can be called from either list's SelectionChanged
    # handler (notably when a Hull family header expands/collapses). Preserve
    # the caller's synchronization guard for the entire refresh. Clearing it
    # here used to let the second list fire recursively while the first handler
    # was still rebuilding both lists, eventually hanging the UI.
    $selectionGuardOnEntry = [bool]$script:syncingSelection
    $script:visibleListEpoch++
    $currentListEpoch = $script:visibleListEpoch
    $script:visibleThumbnailTimer.Stop()
    $script:visibleThumbnailQueue.Clear()
    $script:visibleZoneRecords.Clear()
    # ItemCollection.Clear() is itself a refresh operation, so it must happen
    # before DeferRefresh is active. Doing it inside the deferred window throws
    # and leaves every category panel empty.
    $zones.Items.Clear()
    $pngCollection.Items.Clear()
    # Suspend control initialization while rows are populated. ItemCollection's
    # DeferRefresh cannot be used here because WPF forbids Clear/Add while its
    # CollectionView is deferred.
    $zones.BeginInit()
    $pngCollection.BeginInit()
    $records = @()
    if ($script:shipCatalog) {
        $records = @(Get-VisibleRecords $script:activeCategory)
    }
    if (-not $records -or $records.Count -eq 0) {
        $records = @(Get-SourceRecords $script:activeCategory)
    }
    if ($records.Count -eq 0) {
        $records = @(
            [pscustomobject]@{
                Label = 'No mapped textures yet'
                DisplayName = 'No mapped textures yet'
                Summary = 'This category is still being built.'
                Size = '-'
                State = 'COMING SOON'
                Thumbnail = $null
                Component = -1
                Zone = -1
                MaterialID = $null
                Geometry = $null
                Texture = $null
                Hint = 'This section is not mapped yet.'
                Kind = 'Placeholder'
                ResourceId = $null
                Group = $script:activeCategory
                Risk = 'INFO'
                ShipFamilies = 'unmapped'
                Source = $null
            }
        )
    }
    # Show the list immediately; set known/cached thumbnails now and
    # generate any missing game textures in the background so the UI never freezes.
    try {
        foreach ($record in $records) {
            if ($script:activeCategory -ne 'Hulls' -and -not (Record-MatchesSearch $record $script:searchQuery)) { continue }
            $thumbnailProperty = $record.PSObject.Properties['Thumbnail']
            if ($thumbnailProperty -and -not $thumbnailProperty.IsReadOnly) {
                $record.Thumbnail = Get-LibraryLoadingThumbnail
            }
            [void]$script:visibleZoneRecords.Add($record)
            [void]$zones.Items.Add($record)
            [void]$pngCollection.Items.Add($record)
            Queue-VisibleThumbnail $record ($script:visibleZoneRecords.Count - 1) $currentListEpoch
        }
    }
    finally {
        $zones.EndInit()
        $pngCollection.EndInit()
    }
    if ($script:visibleThumbnailQueue.Count -gt 0) { $script:visibleThumbnailTimer.Start() }
    Start-CatalogWarm
    if ($zones.Items.Count -gt 0) {
        $script:syncingSelection = $true
        try {
            $defaultIndex = if ($script:activeCategory -eq 'Sails') { Get-DefaultJackdawSailIndex } else { 0 }
            if ($defaultIndex -lt 0 -or $defaultIndex -ge $zones.Items.Count) { $defaultIndex = 0 }
            $zones.SelectedIndex = $defaultIndex
            $pngCollection.SelectedIndex = $defaultIndex
        }
        finally {
            $script:syncingSelection = $selectionGuardOnEntry
        }
        # SelectionChanged is deliberately suppressed while the two library
        # lists are synchronized. Refresh the detail panel explicitly so a newly
        # opened category never keeps the previous category's title/preview.
        try { Update-TexturePreview } catch { }
    }
    if ($window.FindName('PanelTitle')) {
        $panelTitleText = switch ($script:activeCategory) {
            'Sails' { if ($script:shipCatalog) { 'SAIL TARGETS' } else { 'SAIL PANELS' } }
            'Flags' { 'FLAG TARGETS' }
            'Figureheads' { 'FIGUREHEAD TARGETS' }
            'Wheels' { 'WHEEL TARGETS' }
            'Hulls' { 'HULL TARGETS' }
            'Cabin' { 'CABIN TARGETS' }
            'Cannons' { 'CANNON TARGETS' }
            'Mortars' { 'MORTAR TARGETS' }
            'Sail Regions' { 'SAIL PANEL REGIONS' }
            'Hull Regions' { 'HULL MATERIAL REGIONS' }
            'Masts' { 'MAST MATERIAL REGIONS' }
            'Rigging' { 'RIGGING & NETTING REGIONS' }
            'Flag Regions' { 'FLAG MATERIAL REGIONS' }
            'Weapon Regions' { 'WEAPON MATERIAL REGIONS' }
            'Lanterns' { 'LANTERN MATERIAL REGIONS' }
            'Details' { 'DECK & HULL DETAIL REGIONS' }
            'Ram' { 'RAM MATERIAL REGIONS' }
            'Rudder' { 'RUDDER MATERIAL REGIONS' }
            default { 'PNG TARGETS' }
        }
        Set-UiText $window.FindName('PanelTitle') $panelTitleText
    }
    if ($window.FindName('PanelCount')) {
        $countText = if (($script:visibleZoneRecords.Count -eq 1) -and ($script:visibleZoneRecords[0].Kind -eq 'Placeholder')) { '0 mapped' } else { "{0} entries" -f $script:visibleZoneRecords.Count }
        if ($script:activeCategory -eq 'Hulls') {
            $leafCount = @($script:visibleZoneRecords | Where-Object { -not $_.IsGroupHeader }).Count
            $groupCount = @($script:visibleZoneRecords | Where-Object { $_.IsGroupHeader }).Count
            $countText = "{0} groups • {1} textures" -f $groupCount, $leafCount
        }
        Set-UiText $window.FindName('PanelCount') $countText
    }
    if ($categoryHelp) {
        $categoryHelpText = switch ($script:activeCategory) {
            'Sails' { if ($script:shipCatalog) { 'Sail texture library. Thumbnails load from your installed game only while this category is open.' } else { 'Exact sail cloth zones for the Jackdaw sails.' } }
            'Hulls' { 'Ship-family groups. Click a hull set to expand its textures.' }
            'Cannons' { 'Cannon and swivel-gun texture library from your installed game.' }
            'Mortars' { 'Mortar barrels, carriages, and siege mortar skins from the cannon texture set.' }
            'Flags' { 'Flag and streamer texture library from your installed game.' }
            'Figureheads' { 'Figurehead texture library from your installed game.' }
            'Wheels' { 'Ship wheel texture library from your installed game.' }
            'Cabin' { 'Jackdaw cabin prop and furnishing texture library from your installed game.' }
            'Sail Regions' { 'Every physical sail surface remains independently selectable with its original UV coordinates.' }
            'Hull Regions' { 'Exact selectable hull surfaces. The material ID is shown before any PNG is applied.' }
            'Masts' { 'Exact mast and yardarm surfaces from the current Jackdaw model.' }
            'Rigging' { 'Exact rigging and netting surfaces from the current Jackdaw model.' }
            'Flag Regions' { 'Exact mast-flag surfaces from the current Jackdaw model.' }
            'Weapon Regions' { 'Cannon, swivel, and mortar surfaces. Missing extraction is reported as zero mapped parts.' }
            'Lanterns' { 'Exact ship-lantern surfaces from the current Jackdaw model.' }
            'Details' { 'Deck, bow, stern, and greeble surfaces from the current Jackdaw model.' }
            'Ram' { 'Exact ram surfaces. This part remains independently toggleable and customizable.' }
            'Rudder' { 'Exact rudder surfaces from the current Jackdaw model.' }
            default { 'Texture targets recovered from the installed game catalog.' }
        }
        Set-UiText $categoryHelp $categoryHelpText
    }
    foreach ($pair in $catButtons.GetEnumerator()) {
        $btn = $pair.Value
        if (-not $btn) { continue }
        $on = ($pair.Key -eq $script:activeCategory)
        $btn.Background = [Windows.Media.SolidColorBrush]::new(
            [Windows.Media.Color]::FromRgb(
                $(if ($on) { 0xD6 } else { 0x12 }),
                $(if ($on) { 0xA6 } else { 0x33 }),
                $(if ($on) { 0x4A } else { 0x44 })))
        $btn.Foreground = [Windows.Media.SolidColorBrush]::new(
                [Windows.Media.Color]::FromRgb(
                    $(if ($on) { 0x14 } else { 0xEA }),
                    $(if ($on) { 0x21 } else { 0xDF }),
                    $(if ($on) { 0x2A } else { 0xC7 })))
    }
}

function Apply-SearchFilter {
    if ($pngSearch) {
        $script:searchQuery = [string]$pngSearch.Text
    }
    Refresh-VisibleList
}

function Set-Category([string]$category) {
    $script:activeCategory = $category
    $script:lastCategoryError = $null
    try {
        Refresh-VisibleList
    }
    catch {
        $script:lastCategoryError = $_ | Out-String
        if ($category -eq 'Hulls') {
            $script:activeCategory = 'Hulls'
            $script:visibleZoneRecords.Clear()
            $zones.Items.Clear()
            $pngCollection.Items.Clear()
            $fallback = @(Get-SourceRecords 'Hulls')
            foreach ($record in $fallback) {
                $null = Get-QuickThumbnail $record
                [void]$script:visibleZoneRecords.Add($record)
                [void]$zones.Items.Add($record)
                [void]$pngCollection.Items.Add($record)
            }
            Start-CatalogWarm
            $zones.SelectedIndex = if ($zones.Items.Count -gt 0) { 0 } else { -1 }
            if ($pngCollection -and $pngCollection.Items.Count -gt 0) { $pngCollection.SelectedIndex = 0 }
            Set-UiText $categoryHelp 'Hull grouping hit an invalid catalog entry, so the app is showing the safe fallback list.'
            Set-UiText $footer 'Hull view loaded in fallback mode to avoid a crash.'
        } else {
            throw
        }
    }
}

function Ensure-DefaultProject {
    $script:currentProject = Join-Path $projectsRoot 'Active Jackdaw'
    foreach ($sub in 'editable','guides','previews') {
        New-Item -ItemType Directory -Force -Path (Join-Path $script:currentProject $sub) | Out-Null
    }
}
Ensure-DefaultProject
$script:shipCatalog = Load-ShipCatalog

foreach ($pair in $catButtons.GetEnumerator()) {
    $name = $pair.Key
    $btn = $pair.Value
    if ($btn) {
        $btn.Add_Click({
            Set-Category $name
            if ($targetFlyout -and $targetFlyout.Tag -ne 'Docked') { $targetFlyout.Visibility = 'Visible' }
        }.GetNewClosure())
    }
}
if ($closeTargetFlyout) {
    $closeTargetFlyout.Add_Click({
        if ($targetFlyout) { $targetFlyout.Visibility = 'Collapsed' }
    })
}
if ($targetFlyout) {
    function Test-IsWithinElement($source, $ancestor) {
        if (-not $source -or -not $ancestor) { return $false }
        $current = $source
        while ($current) {
            if ([object]::ReferenceEquals($current, $ancestor)) { return $true }
            if ($current -isnot [Windows.DependencyObject]) { break }
            $parent = $null
            try { $parent = [Windows.Media.VisualTreeHelper]::GetParent($current) } catch { }
            if (-not $parent) {
                try { $parent = [Windows.LogicalTreeHelper]::GetParent($current) } catch { }
            }
            $current = $parent
        }
        return $false
    }
    function Close-TargetFlyoutForOutsideClick($source) {
        if ($targetFlyout.Tag -eq 'Docked') { return }
        if ($targetFlyout.Visibility -eq [Windows.Visibility]::Visible -and
            -not (Test-IsWithinElement $source $targetFlyout)) {
            $targetFlyout.Visibility = [Windows.Visibility]::Collapsed
        }
    }
    # Standard flyout behavior: any real mouse click elsewhere in the Drydock
    # closes the texture submenu. PreviewMouseDown runs before controls such as
    # the viewport consume the event. Category buttons still work normally—the
    # preview event closes the old flyout and their Click handler opens the new one.
    $window.Add_PreviewMouseDown({
        param($sender, $eventArgs)
        Close-TargetFlyoutForOutsideClick $eventArgs.OriginalSource
    })
    $window.Add_PreviewKeyDown({
        param($sender, $eventArgs)
        if ($targetFlyout.Tag -ne 'Docked' -and $eventArgs.Key -eq [Windows.Input.Key]::Escape -and
            $targetFlyout.Visibility -eq [Windows.Visibility]::Visible) {
            $targetFlyout.Visibility = [Windows.Visibility]::Collapsed
            $eventArgs.Handled = $true
        }
    })
    $window.Add_Deactivated({
        if ($targetFlyout.Tag -ne 'Docked' -and $targetFlyout.Visibility -eq [Windows.Visibility]::Visible) {
            $targetFlyout.Visibility = [Windows.Visibility]::Collapsed
        }
    })
}

# 4-view switcher: Ship / Cannon / Mortar / Cabin. Each loads its own
# standalone JACK3D1 part model into the 3D viewport for texture preview.
$viewButtons = [ordered]@{
    ship = $window.FindName('ViewShip')
    cannon = $window.FindName('ViewCannons')
    mortar = $window.FindName('ViewMortar')
    swivel = $window.FindName('ViewSwivel')
    cabin = $window.FindName('ViewCabin')
}
foreach ($pair in $viewButtons.GetEnumerator()) {
    $viewMode = $pair.Key
    $btn = $pair.Value
    if ($btn) {
        $btn.Add_Click({ Set-ViewMode $viewMode }.GetNewClosure())
    }
}
if ($pngSearch) {
    $pngSearch.Add_TextChanged({
        if ($pngSearchHint) {
            $pngSearchHint.Visibility = if ([string]::IsNullOrWhiteSpace($pngSearch.Text)) { 'Visible' } else { 'Collapsed' }
        }
        $script:searchTimer.Stop()
        $script:searchTimer.Start()
    })
    $pngSearch.Add_GotKeyboardFocus({
        if ($pngSearchHint -and [string]::IsNullOrWhiteSpace($pngSearch.Text)) {
            $pngSearchHint.Visibility = 'Collapsed'
        }
    })
    $pngSearch.Add_LostKeyboardFocus({
        if ($pngSearchHint) {
            $pngSearchHint.Visibility = if ([string]::IsNullOrWhiteSpace($pngSearch.Text)) { 'Visible' } else { 'Collapsed' }
        }
    })
}
if ($lightingMode) {
    $lightingMode.Add_SelectionChanged({ Apply-ViewerLighting })
}
if ($sailDisplayMode) {
    $sailDisplayMode.Add_SelectionChanged({
        $script:currentSailViewMode = Get-SailViewMode
        Apply-SailViewMode
    })
}
if ($textureToggle) {
    $textureToggle.Add_Click({
        if ($script:texturesEnabled) {
            $script:previousSailDisplayMode = Get-SailViewMode
            $script:texturesEnabled = $false
            Set-UiText $footer 'Clay preview enabled - textures are hidden and game files remain unchanged.'
        } else {
            $script:texturesEnabled = $true
            if ($sailDisplayMode) {
                $restoreIndex = 0
                switch ($script:previousSailDisplayMode) {
                    'Custom preview' { $restoreIndex = 1 }
                    'Model only' { $restoreIndex = 0 }
                    default { $restoreIndex = 0 }
                }
                $sailDisplayMode.SelectedIndex = $restoreIndex
            }
            Set-UiText $footer 'Textured preview restored.'
        }
        Apply-SailViewMode
    })
    Update-TextureToggleButton
}
Apply-ViewerLighting

function Load-JackdawModel {
    $loadTimer=[Diagnostics.Stopwatch]::StartNew()
    $loadPath = if ($script:modelPath) { $script:modelPath } else { $modelPath }
    $stream = [IO.File]::OpenRead($loadPath)
    try {
        $binary = [IO.BinaryReader]::new($stream)
        $magic = [Text.Encoding]::ASCII.GetString($binary.ReadBytes(8))
        if ($magic -ne "JACK3D1`0") { throw 'Invalid preview model.' }
        $componentCount = $binary.ReadUInt32()
        $zoneCount = $binary.ReadUInt32()
        $minX=[double]::MaxValue; $minY=[double]::MaxValue; $minZ=[double]::MaxValue
        $maxX=[double]::MinValue; $maxY=[double]::MinValue; $maxZ=[double]::MinValue
        for ($record=0; $record -lt $zoneCount; $record++) {
            $component = [int]$binary.ReadUInt32()
            $zone = [int]$binary.ReadUInt32()
            [void]$binary.ReadUInt32()
            $materialId = $binary.ReadUInt64()
            $vertexCount = [int]$binary.ReadUInt32()
            $indexCount = [int]$binary.ReadUInt32()
            if ($component -lt 0 -or $component -ge $componentGroups.Count) {
                # A record referencing an unknown component would crash the
                # WPF collections below; skip it instead of aborting the load.
                $binary.BaseStream.Seek(($vertexCount * 32) + ($indexCount * 4), [IO.SeekOrigin]::Current) | Out-Null
                continue
            }
            $mesh=[JackdawFastModelReader]::ReadMesh($binary,$vertexCount,$indexCount)
            $bounds=$mesh.Bounds
            if(-not $bounds.IsEmpty){
                $minX=[Math]::Min($minX,$bounds.X);$maxX=[Math]::Max($maxX,$bounds.X+$bounds.SizeX)
                $minY=[Math]::Min($minY,$bounds.Y);$maxY=[Math]::Max($maxY,$bounds.Y+$bounds.SizeY)
                $minZ=[Math]::Min($minZ,$bounds.Z);$maxZ=[Math]::Max($maxZ,$bounds.Z+$bounds.SizeZ)
            }
            $material = Get-DefaultAppearanceMaterial $component $zone
            $geometry = [Windows.Media.Media3D.GeometryModel3D]::new($mesh, $material)
            $geometry.BackMaterial = $material
            $componentGroups[$component].Children.Add($geometry)
            $label = "$($componentNames[$component]) - zone $($zone + 1)"
            $recordInfo = [pscustomobject]@{
                Label = $label
                DisplayName = $label
                Summary = (Get-ZoneHint $component $zone)
                Size = '-'
                State = 'local'
                Component = $component
                Zone = $zone
                MaterialID = $materialId
                Geometry = $geometry
                BaseMaterial = $material
                Texture = $null
                Hint = (Get-ZoneHint $component $zone)
                Kind = 'Zone'
                ResourceId = $null
                Group = $componentNames[$component]
                Risk = 'LOCAL'
                ShipFamilies = $componentNames[$component]
            }
            $zoneRecords.Add($recordInfo)
        }
        if ($maxX -gt $minX) {
            $script:modelCenter = [Windows.Media.Media3D.Point3D]::new(($minX+$maxX)/2,($minY+$maxY)/2,($minZ+$maxZ)/2)
            $script:defaultModelCenter = $script:modelCenter
            $extent = [Math]::Max($maxX-$minX,[Math]::Max($maxY-$minY,$maxZ-$minZ))
            $script:minDistance = [Math]::Max(0.05, $extent * 0.30)
            $script:maxDistance = [Math]::Max($script:minDistance * 6.0, $extent * 12.0)
            $script:distance = [Math]::Max($script:minDistance, $extent * 2.2)
            $script:defaultDistance = $script:distance
            Update-Camera
            # Do not call Helix ZoomExtents here. It mutates the camera behind
            # the manual orbit state and made the first drag jump violently.
        }
        Set-UiText $modelStatus ("{0} components | {1} selectable zones" -f $componentCount, $zoneCount)
        $loadingText.Visibility = 'Collapsed'
        Set-UiText $footer ("Genuine Jackdaw geometry loaded | {0} texture zones | source archive unchanged" -f $zoneCount)
        Prime-DefaultJackdawTextures
        Set-Category $script:activeCategory
        Apply-SailViewMode
        Refresh-JackdawMaterials
        if ((Get-Command Restore-NativeDesign -ErrorAction SilentlyContinue) -and -not $LoadTest) {try {Restore-NativeDesign} catch {Set-UiText $footer $_.Exception.Message}}
    }
    finally { $stream.Dispose();$loadTimer.Stop();[IO.File]::WriteAllText((Join-Path $dataRoot 'native-load-timing.json'),(@{milliseconds=$loadTimer.ElapsedMilliseconds;surfaces=$zoneRecords.Count}|ConvertTo-Json)) }
}

function Set-ViewMode([string]$mode) {
    if ($script:embeddedReady) {Send-EmbeddedMessage @{type='focus';mode=$mode};return}
    # Swap the 3D viewport between the full Ship and the individual part
    # models (Cannon / Mortar / Cabin). Each part model is a standalone JACK3D1
    # so it becomes the centered subject of the preview, letting the user apply
    # a texture to that exact part and see it before applying in-game.
    foreach ($pair in $viewButtons.GetEnumerator()) {
        if ($pair.Value) { $pair.Value.Tag = if ($pair.Key -eq $mode) { 'Active' } else { $null } }
    }
    $jackdawDir = Join-Path $appRoot 'jackdaw'
    $path = switch ($mode) {
        'cannon' { Join-Path $jackdawDir 'cannon.j3d' }
        'mortar' { Join-Path $jackdawDir 'mortar.j3d' }
        'swivel' { Join-Path $jackdawDir 'swivel.j3d' }
        'cabin'  { Join-Path $jackdawDir 'cabin.j3d' }
        default  { Join-Path $jackdawDir 'jackdaw-model-full.j3d' }
    }
    if (-not (Test-Path -LiteralPath $path)) {
        # Fall back to the ship model if the part isn't built yet
        $path = Join-Path $jackdawDir 'jackdaw-model-full.j3d'
    }
    $script:modelPath = $path
    # Remove only the previous geometry groups. Clearing rootModel also deletes
    # the ambient/key/fill lights, which made every later tab (and Ship when
    # returning to it) render completely black.
    foreach ($oldGroup in @($componentGroups)) {
        if ($oldGroup) { [void]$rootModel.Children.Remove($oldGroup) }
    }
    $componentGroups = @()
    for ($index=0; $index -lt $componentNames.Count; $index++) {
        $group = [Windows.Media.Media3D.Model3DGroup]::new()
        $componentGroups += $group
        $rootModel.Children.Add($group)
    }
    $zoneRecords.Clear()
    $script:visibleZoneRecords.Clear()
    $zones.Items.Clear()
    $pngCollection.Items.Clear()
    Load-JackdawModel
    Apply-ViewerLighting
    Refresh-JackdawMaterials
    $script:hdSelected=$null
    if (Get-Command Set-HighDetailVisible -ErrorAction SilentlyContinue) { Set-HighDetailVisible ($mode -eq 'ship') }
    Set-UiText $modelStatus ("View: $mode")
    Set-UiText $footer ("$mode view loaded - click a zone to apply a texture")
}
Ensure-DefaultProject

function Get-SelectedZone {
    if ($script:hdActive -and $script:hdSelected) { return $script:hdSelected }
    if ($zones.SelectedIndex -lt 0 -or $zones.SelectedIndex -ge $script:visibleZoneRecords.Count) { return $null }
    $record=$script:visibleZoneRecords[$zones.SelectedIndex]
    if (Get-Command Get-NativeSailRecord -ErrorAction SilentlyContinue) {return (Get-NativeSailRecord $record)}
    return $record
}

function Get-RegionCategoryForComponent([int]$component) {
    switch ($component) {
        0 { return 'Hull Regions' }
        { $_ -in @(1,2,3,13) } { return 'Details' }
        { $_ -in @(4,12) } { return 'Rigging' }
        5 { return 'Masts' }
        6 { return 'Sail Regions' }
        7 { return 'Flag Regions' }
        { $_ -in @(8,9,10) } { return 'Weapon Regions' }
        11 { return 'Lanterns' }
        14 { return 'Ram' }
        15 { return 'Rudder' }
        default { return $null }
    }
}

function Show-ZoneSelectionHighlight($record) {
    if (Get-Command Show-NativePartEdges -ErrorAction SilentlyContinue) {Show-NativePartEdges $record}
}

function Select-ModelZoneAtPoint([Windows.Point]$point) {
    if (-not $script:nativeViewport -or $script:nativeViewport.Visibility -ne [Windows.Visibility]::Visible) { return $false }
    try {
        if (-not [object]::ReferenceEquals($script:selectionLookupSource,$zoneRecords)) {
            $script:selectionRecordByGeometry=@{}
            foreach ($item in $zoneRecords) {if ($item.Geometry) {$script:selectionRecordByGeometry[$item.Geometry]=$item}}
            $script:selectionLookupSource=$zoneRecords
        }
        $hits = @([HelixToolkit.Wpf.Viewport3DHelper]::FindHits($script:nativeViewport.Viewport, $point))
        foreach ($hit in $hits) {
            $record = $script:selectionRecordByGeometry[$hit.Model]
            if (-not $record) { continue }
            $record=Get-NativeSailRecord $record
            $meta=Get-NativeFinishMeta $record.Component $record.Zone
            if ($meta -and -not $meta.area) {continue}
            if (Toggle-NativePartSelection $record) {return $true}
            $category = Get-RegionCategoryForComponent ([int]$record.Component)
            if ($category) { Set-Category $category }
            for ($index = 0; $index -lt $script:visibleZoneRecords.Count; $index++) {
                $candidate = $script:visibleZoneRecords[$index]
                if ($candidate.Kind -eq 'Zone' -and $candidate.Component -eq $record.Component -and $candidate.Zone -eq $record.Zone) {
                    $zones.SelectedIndex = $index
                    if ($pngCollection -and $pngCollection.Items.Count -gt $index) { $pngCollection.SelectedIndex = $index }
                    $zones.ScrollIntoView($zones.Items[$index])
                    Update-TexturePreview
                    Show-ZoneSelectionHighlight $candidate
                    Set-UiText $footer "Selected $($candidate.DisplayName) - $($candidate.Summary)"
                    return $true
                }
            }
        }
        Clear-NativePartSelection
    } catch { Set-UiText $footer ('Selection could not be updated: '+$_.Exception.Message) }
    return $false
}

function Toggle-HullGroupExpansion([string]$groupKey) {
    if ([string]::IsNullOrWhiteSpace($groupKey)) { return }
    if ($script:expandedHullGroups.Contains($groupKey)) {
        [void]$script:expandedHullGroups.Remove($groupKey)
    } else {
        [void]$script:expandedHullGroups.Add($groupKey)
    }
}

function Get-PreviewCachePath($selected) {
    if (-not $selected -or -not $script:currentProject) { return $null }
    $previewDir = Join-Path $script:currentProject 'previews'
    New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
    $safe = if ($selected.Kind -eq 'Catalog' -and $selected.ResourceId) {
        '{0}_{1}' -f ($selected.Group -replace '[^A-Za-z0-9]+', '_'), ($selected.ResourceId -replace '[^0-9A-Fa-fx]+', '')
    } else {
        ($selected.Label -replace '[^A-Za-z0-9]+', '_')
    }
    return (Join-Path $previewDir ($safe + '.png'))
}

function Update-TexturePreview {
    $selected = Get-SelectedZone
    if (-not $selected) {
        $texturePreview.Source = $null
        if ($replacementPreview) { $replacementPreview.Source = $null }
        $texturePreviewEmpty.Visibility = 'Visible'
        if ($replacementPreviewEmpty) { $replacementPreviewEmpty.Visibility = 'Visible' }
        Set-UiText $textureName 'No texture selected'
        Set-UiText $submenuTextureName 'No texture selected'
        Set-UiText $submenuTextureInfo 'Select a texture above'
        Set-UiText $textureHint 'Pick a zone on the Jackdaw to see where its PNG belongs.'
        if ($selectedThumb) { $selectedThumb.Source = $null }
        if ($targetSubTitle) { Set-UiText $targetSubTitle 'Select a texture to view its details.' }
        if ($textureInfo) { Set-UiText $textureInfo 'No original PNG selected' }
        return
    }
    $textureNameText = if ($selected.Kind -eq 'Catalog') { $selected.DisplayName } else { $selected.Label }
    Set-UiText $textureName $textureNameText
    Set-UiText $submenuTextureName $textureNameText
    Set-UiText $textureHint $selected.Hint
    if ($targetSubTitle) {
        $targetSubTitleText = if ($selected.Kind -eq 'Zone' -and $selected.Hint) { [string]$selected.Hint } elseif ($selected.Summary) { [string]$selected.Summary } else { [string]$selected.Hint }
        Set-UiText $targetSubTitle $targetSubTitleText
    }
    if ($textureInfo) {
        Set-UiText $textureInfo 'No PNG exported yet'
    }
    $originalPath = Get-RecordOriginalTexturePath $selected
    $replacementPath = $null
    if ($script:generatedPreviewPath -and [object]::ReferenceEquals($script:generatedPreviewRecord, $selected) -and (Test-Path -LiteralPath $script:generatedPreviewPath)) {
        $replacementPath = $script:generatedPreviewPath
    }
    if ($originalPath -and (Test-Path -LiteralPath $originalPath)) {
        $image = New-PanelPreviewImageSource $originalPath 640
        $texturePreview.Source = $image
        if ($selectedThumb) { $selectedThumb.Source = $image }
        $texturePreviewEmpty.Visibility = 'Collapsed'
    } else {
        $texturePreview.Source = $null
        if ($selectedThumb) { $selectedThumb.Source = $null }
        $texturePreviewEmpty.Visibility = 'Visible'
        Set-UiText $texturePreviewEmpty 'No PNG chosen yet for this zone.'
    }
    if ($replacementPreview -and $replacementPreviewEmpty) {
        if ($replacementPath -and (Test-Path -LiteralPath $replacementPath) -and ($replacementPath -ne $originalPath)) {
            $repImage = New-PanelPreviewImageSource $replacementPath 640
            $replacementPreview.Source = $repImage
            $replacementPreviewEmpty.Visibility = 'Collapsed'
        } else {
            $replacementPreview.Source = $null
            $replacementPreviewEmpty.Visibility = 'Visible'
            Set-UiText $replacementPreviewEmpty 'Your generated texture will appear here.'
        }
    }
    if ($textureInfo) {
        $originalLeaf = if ($originalPath) { Split-Path $originalPath -Leaf } else { 'not mapped yet' }
        $replacementLeaf = if ($replacementPath -and ($replacementPath -ne $originalPath)) { Split-Path $replacementPath -Leaf } else { 'No imported PNG yet' }
        $categoryLabel = if ($script:activeCategory) { $script:activeCategory } else { 'Texture' }
        if ($selected.Kind -eq 'Zone') {
            $materialText = if ($null -ne $selected.MaterialID) { '0x{0:X16}' -f [UInt64]$selected.MaterialID } else { 'unknown' }
            $appliedLeaf = if ($selected.Texture -and (Test-Path -LiteralPath $selected.Texture)) { Split-Path $selected.Texture -Leaf } elseif ($replacementPath) { Split-Path $replacementPath -Leaf } else { 'No custom PNG applied' }
            Set-UiText $textureInfo ("Material: {0}`nApplied: {1}" -f $materialText, $appliedLeaf)
        } else {
            Set-UiText $textureInfo ("Source: {0}  |  Library: {1}" -f $originalLeaf, $categoryLabel)
        }
    }
    if ($submenuTextureInfo) {
        $submenuSize = if ($selected.Size) { [string]$selected.Size } else { 'Extracted game texture' }
        $submenuCategory = if ($script:activeCategory) { [string]$script:activeCategory } else { 'Jackdaw' }
        Set-UiText $submenuTextureInfo ("{0}  |  {1}" -f $submenuSize, $submenuCategory)
    }
}

$pngCollection.Add_SelectionChanged({
    # Ignore the partner list's programmatic selection without touching the
    # guard owned by that outer operation. A return inside try would still run
    # finally and clear the outer guard, reopening the recursive event path.
    if ($script:syncingSelection) { return }
    try {
        $script:syncingSelection = $true
        if ($pngCollection.SelectedIndex -ge 0 -and $pngCollection.SelectedIndex -lt $zones.Items.Count) {
            $zones.SelectedIndex = $pngCollection.SelectedIndex
        }
        $selected = Get-SelectedZone
        if ($selected -and $selected.IsGroupHeader) {
            $selectedGroupKey = [string]$selected.GroupKey
            Toggle-HullGroupExpansion $selectedGroupKey
            Refresh-VisibleList
            for ($i = 0; $i -lt $zones.Items.Count; $i++) {
                $item = $zones.Items[$i]
                if ($item -and $item.IsGroupHeader -and $item.GroupKey -eq $selectedGroupKey) {
                    $zones.SelectedIndex = $i
                    if ($pngCollection -and $pngCollection.Items.Count -gt $i) { $pngCollection.SelectedIndex = $i }
                    break
                }
            }
            return
        }
        Update-TexturePreview
        Show-ZoneSelectionHighlight $selected
    }
    finally {
        $script:syncingSelection = $false
    }
})
$zones.Add_SelectionChanged({
    if ($script:syncingSelection) { return }
    try {
    $script:syncingSelection = $true
    if ($zones.SelectedIndex -ge 0 -and $zones.SelectedIndex -lt $pngCollection.Items.Count) {
        $pngCollection.SelectedIndex = $zones.SelectedIndex
    }
    $selected = Get-SelectedZone
    if ($selected -and $selected.IsGroupHeader) {
        $selectedGroupKey = [string]$selected.GroupKey
        Toggle-HullGroupExpansion $selectedGroupKey
        Refresh-VisibleList
        for ($i = 0; $i -lt $zones.Items.Count; $i++) {
            $item = $zones.Items[$i]
            if ($item -and $item.IsGroupHeader -and $item.GroupKey -eq $selectedGroupKey) {
                $zones.SelectedIndex = $i
                if ($pngCollection -and $pngCollection.Items.Count -gt $i) { $pngCollection.SelectedIndex = $i }
                break
            }
        }
        $script:syncingSelection = $false
        return
    }
    Update-TexturePreview
    Show-ZoneSelectionHighlight $selected
    $script:syncingSelection = $false
    } finally {
        $script:syncingSelection = $false
    }
})
function New-TextureMaterial([string]$path,[bool]$FlipV=$false) {
    try {
        if ([string]::IsNullOrWhiteSpace($path)) { throw 'empty path' }
        $image = [Windows.Media.Imaging.BitmapImage]::new()
        $image.BeginInit(); $image.CacheOption='OnLoad'; $image.UriSource=[Uri]::new($path); $image.EndInit(); $image.Freeze()
        $brush = [Windows.Media.ImageBrush]::new($image)
        $brush.Stretch = 'Fill'; $brush.TileMode = 'Tile'
        # GLB UVs address the atlas directly; do not fit the entire image
        # to each primitive's UV bounds (especially partial sail panels).
        $brush.ViewportUnits = [Windows.Media.BrushMappingMode]::Absolute
        $brush.Viewport = [Windows.Rect]::new(0,0,1,1)
        if ($FlipV) {$brush.RelativeTransform=[Windows.Media.ScaleTransform]::new(1,-1,0.5,0.5)}
        $brush.Freeze()
        $material=[Windows.Media.Media3D.DiffuseMaterial]::new($brush)
        $material.Freeze()
        return $material
    }
    catch {
        return New-SolidMaterial '#6B7280'
    }
}

function Save-PreviewCache($selected, [string]$path) {
    $cachePath = Get-PreviewCachePath $selected
    if (-not $cachePath) { return }
    try {
        Copy-Item -LiteralPath $path -Destination $cachePath -Force
        $selected.Texture = $cachePath
        $selected.Thumbnail = New-ThumbnailImageSource $cachePath 72
    }
    catch {
        $selected.Texture = $path
        $selected.Thumbnail = New-ThumbnailImageSource $path 72
    }
    if ($zones) { $zones.Items.Refresh() }
    if ($pngCollection) { $pngCollection.Items.Refresh() }
}

function Choose-TexturePath {
    $dialog = [Microsoft.Win32.OpenFileDialog]::new()
    $dialog.Title = 'Choose your edited texture PNG'
    $dialog.Filter = 'PNG image (*.png)|*.png'
    if ($dialog.ShowDialog($window)) { return $dialog.FileName }
    return $null
}

function Get-ApplyDesignScopeName {
    if ([string]::IsNullOrWhiteSpace($script:applyDesignScopeName)) {
        $script:applyDesignScopeName = 'Whole ship'
    }
    return [string]$script:applyDesignScopeName
}

function Get-ApplyDesignScopeFolderName {
    param([string]$ScopeName)
    switch ($ScopeName) {
        'Sails' { return 'sails' }
        'Hull' { return 'hull' }
        'Figurehead' { return 'figurehead' }
        'Crew' { return 'crew' }
        'Cannons' { return 'cannons' }
        'Mortar' { return 'mortar' }
        'Cabin' { return 'cabin' }
        'Selected parts' { return 'selected-parts' }
        default { return 'jackdaw-default' }
    }
}

function Get-PreparedDesignPackagePath {
    param([string]$ProjectFolder, [string]$ScopeName)
    $scopeFolder = Get-ApplyDesignScopeFolderName $ScopeName
    if ($scopeFolder -eq 'jackdaw-default') {
        return Join-Path $ProjectFolder 'ready-to-import\jackdaw-default'
    }
    return Join-Path $ProjectFolder ("ready-to-import\jackdaw-default\" + $scopeFolder)
}

function Get-CustomCosmeticSlotId {
    param([string]$ProjectFolder, [string]$ScopeName)
    $designName = Split-Path $ProjectFolder -Leaf
    $raw = ("jackdaw-workshop-{0}-{1}" -f $designName, $ScopeName).ToLowerInvariant()
    $slot = [Text.RegularExpressions.Regex]::Replace($raw, '[^a-z0-9_.-]+', '-')
    return $slot.Trim('-','.')
}

$window.FindName('ChoosePng').Add_Click({
    $selected = Get-SelectedZone
    if (-not $selected) { return }
    Export-SelectedTexture $selected | Out-Null
})
$window.FindName('ExportGenerated').Add_Click({
    $selected = Get-SelectedZone
    if (-not $selected -or -not $script:generatedPreviewPath -or
        -not [object]::ReferenceEquals($script:generatedPreviewRecord, $selected) -or
        -not (Test-Path -LiteralPath $script:generatedPreviewPath)) {
        [Windows.MessageBox]::Show('Generate a result for the selected texture first.','No generated result') | Out-Null
        return
    }
    $dialog = [Microsoft.Win32.SaveFileDialog]::new()
    $dialog.Title = 'Export UV-compatible generated texture'
    $dialog.Filter = 'PNG image (*.png)|*.png'
    $dialog.FileName = Split-Path $script:generatedPreviewPath -Leaf
    if ($dialog.ShowDialog($window)) {
        Copy-Item -LiteralPath $script:generatedPreviewPath -Destination $dialog.FileName -Force
        Set-UiText $AiStatusText 'Generated result exported. The extracted source texture was not modified.'
        Set-UiText $footer "Exported generated texture to $($dialog.FileName)"
    }
})
$window.FindName('ImportPngButton').Add_Click({
    $selected = Get-SelectedZone
    if (-not $selected -or $selected.IsGroupHeader) {
        [Windows.MessageBox]::Show('Select a texture target first, then choose Import PNG.','Choose a texture target') | Out-Null
        return
    }
    $path = Choose-TexturePath
    if (-not $path) { return }
    if ((Get-Command Import-DesignPng -ErrorAction SilentlyContinue) -and (Get-NativeFinishMeta $selected.Component $selected.Zone)) {Invoke-WorkflowAction {Import-DesignPng $selected $path};return}

    if ($script:currentProject) {
        $editableDir = Join-Path ([IO.Path]::GetFullPath([string]$script:currentProject)) 'editable'
        New-Item -ItemType Directory -Force -Path $editableDir | Out-Null
        $editablePath = Join-Path $editableDir (Split-Path $path -Leaf)
        if ([IO.Path]::GetFullPath($path) -ne [IO.Path]::GetFullPath($editablePath)) {
            Copy-Item -LiteralPath $path -Destination $editablePath -Force
        }
    }

    Save-PreviewCache $selected $path
    Update-TexturePreview
    Set-DesignProgress 'Custom PNG imported.' 100 'Replacement preview is ready to apply.'
    Set-UiText $footer "Imported $(Split-Path $path -Leaf). Review it in Replacement Preview, then click Apply PNG to Selected Part."
    Reset-DesignProgressSoon
})
$window.FindName('ApplyComponent').Add_Click({
    $selected = Get-SelectedZone
    if (-not $selected -or $selected.IsGroupHeader) {
        [Windows.MessageBox]::Show('Select a texture target first.','Choose a texture target') | Out-Null
        return
    }
    $originalPath = Get-RecordOriginalTexturePath $selected
    $path = $null
    if ($script:generatedPreviewPath -and [object]::ReferenceEquals($script:generatedPreviewRecord, $selected) -and (Test-Path -LiteralPath $script:generatedPreviewPath)) {
        $path = [IO.Path]::GetFullPath([string]$script:generatedPreviewPath)
    } elseif ($selected.Texture -and (Test-Path -LiteralPath $selected.Texture)) {
        $candidate = [IO.Path]::GetFullPath([string]$selected.Texture)
        $originalFull = if ($originalPath -and (Test-Path -LiteralPath $originalPath)) { [IO.Path]::GetFullPath([string]$originalPath) } else { $null }
        if (-not $originalFull -or $candidate -ne $originalFull) { $path = $candidate }
    }
    if (-not $path) {
        $cachePath = Get-PreviewCachePath $selected
        if ($cachePath -and (Test-Path -LiteralPath $cachePath)) { $path = $cachePath }
    }
    if (-not $path) {
        [Windows.MessageBox]::Show('Import your edited PNG first. It will appear in Replacement Preview before anything is applied.','Import a PNG first') | Out-Null
        return
    }
    if (Get-Command Apply-NativeFinishPng -ErrorAction SilentlyContinue) {
        if (Apply-NativeFinishPng $selected $path) {
            Save-PreviewCache $selected $selected.Texture
            Update-TexturePreview
            return
        }
    }
    if ($selected.Geometry) {
        $material = New-TextureMaterial $path
        $selected.Geometry.Material = $material
        $selected.Geometry.BackMaterial = $material
        Set-AppliedPreviewMaterial $selected $material
        $selected.Texture = $path
    }
    if ($selected.Geometry) {
        Set-UiText $footer "Applied $(Split-Path $path -Leaf) to $($selected.Label) in the preview - game files unchanged"
    } else {
        Set-UiText $footer "Stored $(Split-Path $path -Leaf) for $($selected.Label). Choose the matching ship zone to preview its UV placement."
    }
    Save-PreviewCache $selected $path
    Set-DesignProgress 'Replacement applied to preview.' 100 "Selected target: $($selected.Label)"
    if ($selected.Component -eq $sailComponentIndex) { Set-SailViewMode 'Custom preview' }
    Apply-SailViewMode
    Update-TexturePreview
    Reset-DesignProgressSoon
})

$sailComponentIndex = 6
function Get-SailGroupZones([string]$mode) {
    $sails = @($zoneRecords | Where-Object Component -eq $sailComponentIndex)
    switch ($mode) {
        'Selected sail panel' { return @((Get-SelectedZone) | Where-Object { $_ -and $_.Component -eq $sailComponentIndex }) }
        'Main-mast square cloth' { return @($sails | Where-Object Zone -lt 11) }
        'Foremast square cloth' { return @($sails | Where-Object { $_.Zone -ge 11 -and $_.Zone -lt 23 }) }
        'Fore-and-aft / stay cloth' { return @($sails | Where-Object { $_.Zone -in @(0,10,23,24,25) }) }
        'All sails' { return @($sails) }
        default { return @() }
    }
}
$window.FindName('ApplySailGroup').Add_Click({
    $mode = $null
    if ($sailGroupMode -and $sailGroupMode.SelectedItem) {
        $mode = [string]$sailGroupMode.SelectedItem.Content
    }
    if (-not $mode) { $mode = 'Selected sail panel' }
    $path = Choose-TexturePath
    if (-not $path) { return }
    $targets = @(Get-SailGroupZones $mode)
    if ($targets.Count -eq 0) {
        [Windows.MessageBox]::Show('No sail panels matched the chosen group.','Sail group') | Out-Null
        return
    }
    foreach ($zone in $targets) {
        $material = New-TextureMaterial $path
        $zone.Geometry.Material = $material
        $zone.Geometry.BackMaterial = $material
        Set-AppliedPreviewMaterial $zone $material
        $zone.Texture = $path
    }
    Set-UiText $footer "Previewing $(Split-Path $path -Leaf) on $mode - game files unchanged"
    if ($script:currentProject) { Copy-Item -LiteralPath $path -Destination (Join-Path $script:currentProject 'editable') -Force }
    Save-PreviewCache $targets[0] $path
    if ($targets[0].Component -eq $sailComponentIndex) { Set-SailViewMode 'Custom preview' }
    if ($targets[0].Component -eq $sailComponentIndex) { Apply-SailViewMode }
    Update-TexturePreview
    Set-DesignProgress 'Sail group preview updated.' 100 "$($targets.Count) sail panels updated"
    Reset-DesignProgressSoon
})
$window.FindName('ApplyAllSails').Add_Click({
    $path = Choose-TexturePath
    if (-not $path) { return }
    $sailRecord=Get-NativeSailRecord ($zoneRecords | Where-Object {$_.Component -eq 6} | Select-Object -First 1)
    if ($sailRecord) {Set-NativeFinish $sailRecord $path $null 'design';return}
    $targets = @(Get-SailGroupZones 'All sails')
    foreach ($zone in $targets) {
        $material = New-TextureMaterial $path
        $zone.Geometry.Material = $material
        $zone.Geometry.BackMaterial = $material
        Set-AppliedPreviewMaterial $zone $material
        $zone.Texture = $path
    }
    Set-UiText $footer "Previewing $(Split-Path $path -Leaf) across all exact Jackdaw sail panels - game files unchanged"
    if ($script:currentProject) { Copy-Item -LiteralPath $path -Destination (Join-Path $script:currentProject 'editable') -Force }
    Save-PreviewCache $targets[0] $path
    Set-SailViewMode 'Custom preview'
    Apply-SailViewMode
    Update-TexturePreview
    Set-DesignProgress 'All-sails preview updated.' 100 "$($targets.Count) sail panels updated"
    Reset-DesignProgressSoon
})

$applyDesign.Add_Click({
    if (Get-Command Export-NativeDesignPackage -ErrorAction SilentlyContinue) {Invoke-WorkflowAction {$folder=Export-NativeDesignPackage;Start-Process explorer.exe -ArgumentList ('"'+$folder+'"')};return}
    $selected = Get-SelectedZone
    if (-not $script:currentProject) {
        [Windows.MessageBox]::Show('Create or select a design first.','Choose a design') | Out-Null
        return
    }
    if (-not $selected) {
        [Windows.MessageBox]::Show('Pick a texture zone first.','Choose a zone') | Out-Null
        return
    }

    $projectFolder = [IO.Path]::GetFullPath([string]$script:currentProject)
    $editableDir = Join-Path $projectFolder 'editable'
    if (-not (Test-Path -LiteralPath $editableDir -PathType Container)) {
        [Windows.MessageBox]::Show('This design does not have an editable PNG folder yet.','Nothing to apply') | Out-Null
        return
    }

    $pngs = @(Get-ChildItem -LiteralPath $editableDir -Filter '*.png' -File -ErrorAction SilentlyContinue)
    if ($pngs.Count -eq 0) {
        [Windows.MessageBox]::Show('Add or export at least one PNG before applying the design.','Nothing to apply') | Out-Null
        return
    }

    $scopeName = Get-ApplyDesignScopeName
    $importRoot = Get-PreparedDesignPackagePath $projectFolder $scopeName
    New-Item -ItemType Directory -Force -Path $importRoot | Out-Null
    $pngCount = [Math]::Max(1, $pngs.Count)
    Set-DesignProgress "Preparing ${scopeName} package..." 8 "0 / $pngCount textures processed"
    Invoke-UiRefresh
    $copied = 0
    foreach ($png in $pngs) {
        Copy-Item -LiteralPath $png.FullName -Destination (Join-Path $importRoot $png.Name) -Force
        $copied++
        $pct = 8 + [int]([Math]::Round((($copied / $pngCount) * 82), 0))
        Set-DesignProgress "Packing $($png.Name)..." $pct "$copied / $pngCount textures processed"
    }

    Set-DesignProgress "Writing patch manifest..." 94 "$copied / $pngCount textures processed"
    $manifest = [ordered]@{
        profile = 'Jackdaw Default'
        mode = 'custom-cosmetic-slot'
        target = 'Jackdaw custom appearance registry'
        target_scope = $scopeName
        cosmetic_categories = if ($scopeName -eq 'Whole ship') { @('sails','hull','figurehead','crew') } elseif ($scopeName -eq 'Sails') { @('sails') } elseif ($scopeName -eq 'Figurehead') { @('figurehead') } elseif ($scopeName -eq 'Crew') { @('crew') } elseif ($scopeName -eq 'Cabin') { @() } else { @('hull') }
        patch_strategy = 'runtime_loose_override'
        cannons_bundled_with = 'hull'
        cabin_injectable = $false
        design_folder = $projectFolder
        editable_png_folder = $editableDir
        ready_to_import_folder = $importRoot
        files = @($pngs | ForEach-Object { $_.Name })
        npc_ship_changes_allowed = $false
        shared_textures_overwritten = $false
        notes = @(
            'This package is meant to register isolated Jackdaw cosmetic slots.',
            'Shared NPC ship textures should stay untouched.',
            "Selected scope: $scopeName.",
            'Sails, hull, figurehead, and crew are separate game cosmetic families.',
            'Cannons travel with the hull slot; cabin designs stay workshop-only.'
        )
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $importRoot 'patch.json') -Encoding UTF8

    Set-DesignProgress "Jackdaw package ready." 100 "$copied / $pngCount textures processed"
    Set-UiText $footer "Jackdaw import package ready for ${scopeName}: $(Split-Path $importRoot -Leaf)"
    Invoke-UiRefresh
    Start-Process explorer.exe -ArgumentList @($importRoot)
    Reset-DesignProgressSoon 1400
})

if ($injectDesign) {
    $injectDesign.Add_Click({Invoke-NativeInstallDesign})
}

$window.FindName('RevertDesign').Add_Click({
    $script:nativeFinishStates=@{}
    $script:generatedPreviewPath=$null;$script:generatedPreviewRecord=$null
    if (Get-Command Save-NativeDesignAfterEdit -ErrorAction SilentlyContinue) {Save-NativeDesignAfterEdit}

    $script:appliedPreviewMaterials = @{}
    foreach ($zone in $zoneRecords) {
        if (-not $zone.Geometry) { continue }
        $zone.Geometry.Material = $zone.BaseMaterial
        $zone.Geometry.BackMaterial = $zone.BaseMaterial
        $zone.Texture = $null
    }
    if ($sailDisplayMode) {
        $sailDisplayMode.SelectedIndex = 0
    }
    Set-SailViewMode 'Default game sails'
    Set-UiText $footer 'Jackdaw preview reverted to the default game appearance.'
    Apply-SailViewMode
    Update-TexturePreview
    Set-DesignProgress 'Preview reverted.' 100 'Original Jackdaw preview restored.'
    Reset-DesignProgressSoon
})

$texturePreview.Add_MouseLeftButtonUp({
    $selected = Get-SelectedZone
    if (-not $selected) { return }
    $path = Get-RecordOriginalTexturePath $selected
    if (-not $path) { return }
    $title = if ($selected.Kind -eq 'Catalog') { $selected.DisplayName } else { $selected.Label }
    Show-PreviewImageWindow $path $title
})
if ($generatedPreviewPanel) {
    $generatedPreviewPanel.Add_MouseLeftButtonUp({
        if (-not $script:generatedPreviewPath -or -not (Test-Path -LiteralPath $script:generatedPreviewPath)) { return }
        $selected = $script:generatedPreviewRecord
        $title = if ($selected -and $selected.DisplayName) { "$($selected.DisplayName) - Generated Texture" } elseif ($selected -and $selected.Label) { "$($selected.Label) - Generated Texture" } else { 'Generated Texture' }
        Show-PreviewImageWindow $script:generatedPreviewPath $title
    })
}
if ($selectedThumb) {
    $selectedThumb.Add_MouseLeftButtonUp({
        $selected = Get-SelectedZone
        if (-not $selected) { return }
        $path = Get-RecordOriginalTexturePath $selected
        if (-not $path) { return }
        $title = if ($selected.Kind -eq 'Catalog') { $selected.DisplayName } else { $selected.Label }
        Show-PreviewImageWindow $path $title
    })
}

# The release GLB exposes the exact authored ram and rudder under dedicated
# top-level groups.  Control those nodes by their glTF extras/name instead of
# assigning them fake legacy J3D component indexes.
$script:glbGroupVisibility = @{ RAM = $true; RUDDER = $true }
function Set-GlbComponentGroupVisibility([string]$GroupName, [bool]$Visible) {
    if (-not $GroupName) { return }
    $normalized = $GroupName.ToUpperInvariant()
    $script:glbGroupVisibility[$normalized] = $Visible
    if ($null -eq $viewportWebBrowser -or $null -eq $viewportWebBrowser.CoreWebView2 -or
        -not $viewportWebBrowser.CoreWebView2.IsReady) { return }

    $command = [ordered]@{ group = $normalized; visible = $Visible } | ConvertTo-Json -Compress
    $js = @"
(function(command) {
    function resolveScene() {
        var canvases = document.querySelectorAll('canvas');
        for (var ci = 0; ci < canvases.length; ci++) {
            var c = canvases[ci];
            var fiberKey = Object.keys(c).find(function(k) {
                return k.indexOf('__reactFiber') === 0 || k.indexOf('__fiber') === 0;
            });
            var root = c.__r3f || (fiberKey ? c[fiberKey] : null);
            if (root && root.store) {
                var state = root.store.getState();
                if (state && state.scene) return state.scene;
            }
            var renderer = c._renderer || c.__renderer || c.renderer;
            if (renderer && renderer.scene) return renderer.scene;
        }
        return null;
    }
    function belongsToGroup(obj, target) {
        var data = obj.userData || {};
        var values = [data.component_group, data.group, obj.name];
        for (var i = 0; i < values.length; i++) {
            if (values[i] == null) continue;
            var value = String(values[i]).toUpperCase().replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
            if (value === target || value === 'GROUP :: ' + target ||
                value.indexOf('COMPONENT :: ' + target + ' ::') === 0) return true;
        }
        return false;
    }
    var scene = resolveScene();
    if (!scene) return { applied: false, reason: 'no_scene' };
    var matched = 0;
    scene.traverse(function(obj) {
        if (belongsToGroup(obj, command.group)) {
            obj.visible = !!command.visible;
            matched++;
        }
    });
    return { applied: matched > 0, group: command.group, visible: !!command.visible, matched: matched };
})($command);
"@
    try { [void]$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($js) } catch { }
}

$checkNames = @('ShowOuterHull','ShowDeck','ShowBow','ShowStern','ShowRigging','ShowMasts','ShowSails')
for ($component=0; $component -lt $checkNames.Count; $component++) {
    $box = $window.FindName($checkNames[$component])
    $captured = $component
    $box.Add_Checked({ $componentGroups[$captured].Transform = [Windows.Media.Media3D.Transform3D]::Identity }.GetNewClosure())
    $box.Add_Unchecked({ $componentGroups[$captured].Transform = [Windows.Media.Media3D.ScaleTransform3D]::new(0,0,0) }.GetNewClosure())
}
foreach ($toggle in @(@('ShowRam','RAM',14), @('ShowRudder','RUDDER',15))) {
    $box = $window.FindName($toggle[0])
    $capturedGroup = $toggle[1]
    $capturedComponent = [int]$toggle[2]
    if ($box) {
        $box.Add_Checked({
            $componentGroups[$capturedComponent].Transform = [Windows.Media.Media3D.Transform3D]::Identity
            Set-GlbComponentGroupVisibility $capturedGroup $true
        }.GetNewClosure())
        $box.Add_Unchecked({
            $componentGroups[$capturedComponent].Transform = [Windows.Media.Media3D.ScaleTransform3D]::new(0,0,0)
            Set-GlbComponentGroupVisibility $capturedGroup $false
        }.GetNewClosure())
    }
}

$script:dragging = $false
$script:lastPoint = [Windows.Point]::new(0,0)
$script:dragStartPoint = $script:lastPoint
$script:didDrag = $false
$script:viewportInputSurface = if ($viewportInputLayer) { $viewportInputLayer } elseif ($script:nativeViewport) { $script:nativeViewport } else { $viewportHost }

function Stop-ViewportDrag {
    $surface = $script:viewportInputSurface
    $script:dragging = $false
    $script:dragMode = $null
    if ($surface) {
        if ($surface.IsMouseCaptured) { [Windows.Input.Mouse]::Capture($null) | Out-Null }
        $surface.Cursor = [Windows.Input.Cursors]::Arrow
    }
}

$script:viewportInputSurface.Add_MouseLeftButtonDown({
    param($sender,$event)
    if ($script:dragging) { Stop-ViewportDrag }
    $script:dragging = $true
    $script:dragMode = 'rotate'
    $script:lastPoint = $event.GetPosition($script:viewportInputSurface)
    $script:dragStartPoint = $script:lastPoint
    $script:didDrag = $false
    $script:viewportInputSurface.Cursor = [Windows.Input.Cursors]::SizeAll
    $script:viewportInputSurface.Focus() | Out-Null
    [Windows.Input.Mouse]::Capture($script:viewportInputSurface, [Windows.Input.CaptureMode]::Element) | Out-Null
    $event.Handled = $true
})
$script:viewportInputSurface.Add_MouseLeftButtonUp({
    param($sender,$event)
    $wasClick = ($script:dragMode -eq 'rotate' -and -not $script:didDrag)
    $clickPoint = $event.GetPosition($script:viewportInputSurface)
    if ($script:dragMode -eq 'rotate') { Stop-ViewportDrag }
    if ($wasClick) { [void](Select-ModelZoneAtPoint $clickPoint) }
    $event.Handled = $true
})
$script:viewportInputSurface.Add_MouseRightButtonDown({
    param($sender,$event)
    if ($script:dragging) { Stop-ViewportDrag }
    $script:dragging = $true
    $script:dragMode = 'move-model'
    $script:lastPoint = $event.GetPosition($script:viewportInputSurface)
    $script:dragStartPoint = $script:lastPoint
    $script:didDrag = $false
    $script:viewportInputSurface.Cursor = [Windows.Input.Cursors]::ScrollAll
    $script:viewportInputSurface.Focus() | Out-Null
    [Windows.Input.Mouse]::Capture($script:viewportInputSurface, [Windows.Input.CaptureMode]::Element) | Out-Null
    $event.Handled = $true
})
$script:viewportInputSurface.Add_MouseRightButtonUp({
    param($sender,$event)
    if ($script:dragMode -eq 'move-model') { Stop-ViewportDrag }
    $event.Handled = $true
})
$script:viewportInputSurface.Add_LostMouseCapture({
    if ($script:dragging) {
        $script:dragging = $false
        $script:dragMode = $null
        $script:viewportInputSurface.Cursor = [Windows.Input.Cursors]::Arrow
    }
})
$script:viewportInputSurface.Add_MouseMove({
    param($sender,$event)
    if (-not $script:dragging) { return }
    if (($script:dragMode -eq 'rotate' -and $event.LeftButton -ne [Windows.Input.MouseButtonState]::Pressed) -or
        ($script:dragMode -eq 'move-model' -and $event.RightButton -ne [Windows.Input.MouseButtonState]::Pressed)) {
        Stop-ViewportDrag
        return
    }
    $point = $event.GetPosition($script:viewportInputSurface)
    $dx = $point.X - $script:lastPoint.X
    $dy = $point.Y - $script:lastPoint.Y
    if (-not $script:didDrag) {
        $totalX = $point.X - $script:dragStartPoint.X
        $totalY = $point.Y - $script:dragStartPoint.Y
        $script:didDrag = (($totalX * $totalX + $totalY * $totalY) -ge 9.0)
    }
    if (-not $script:didDrag) {$event.Handled=$true;return}
    if ($script:dragMode -eq 'rotate') {
        $width = [Math]::Max(240.0, $script:viewportInputSurface.ActualWidth)
        $height = [Math]::Max(180.0, $script:viewportInputSurface.ActualHeight)
        $script:yaw -= $dx * (4.8 / $width)
        $script:pitch = [Math]::Max(-1.35,[Math]::Min(1.35,$script:pitch - $dy * (3.2 / $height)))
    } elseif ($script:dragMode -eq 'move-model') {
        # Translate the camera target so the projected ship follows the right-
        # drag cursor exactly, including at high or low orbit angles.
        $forward = [Windows.Media.Media3D.Vector3D]::new(
            $script:modelCenter.X - $script:camera.Position.X,
            $script:modelCenter.Y - $script:camera.Position.Y,
            $script:modelCenter.Z - $script:camera.Position.Z)
        if ($forward.LengthSquared -gt 0.0000001) { $forward.Normalize() }
        $worldUp = [Windows.Media.Media3D.Vector3D]::new(0,0,1)
        $right = [Windows.Media.Media3D.Vector3D]::CrossProduct($forward,$worldUp)
        if ($right.LengthSquared -gt 0.0000001) { $right.Normalize() }
        $screenUp = [Windows.Media.Media3D.Vector3D]::CrossProduct($right,$forward)
        if ($screenUp.LengthSquared -gt 0.0000001) { $screenUp.Normalize() }
        $height = [Math]::Max(180.0, $script:viewportInputSurface.ActualHeight)
        $worldPerPixel = (2.0 * $script:distance * [Math]::Tan(($script:camera.FieldOfView * [Math]::PI / 180.0) / 2.0)) / $height
        $script:modelCenter = [Windows.Media.Media3D.Point3D]::new(
            $script:modelCenter.X - ($right.X * $dx * $worldPerPixel) + ($screenUp.X * $dy * $worldPerPixel),
            $script:modelCenter.Y - ($right.Y * $dx * $worldPerPixel) + ($screenUp.Y * $dy * $worldPerPixel),
            $script:modelCenter.Z - ($right.Z * $dx * $worldPerPixel) + ($screenUp.Z * $dy * $worldPerPixel))
    }
    $script:lastPoint = $point
    Update-Camera
    $event.Handled = $true
})
$script:viewportInputSurface.Add_MouseWheel({
    param($sender,$event)
    $notches = [double]$event.Delta / 120.0
    $zoomFactor = [Math]::Pow(0.86, $notches)
    $script:distance = [Math]::Max($script:minDistance, [Math]::Min($script:maxDistance, $script:distance * $zoomFactor))
    Update-Camera
    $event.Handled = $true
})
$window.FindName('ResetView').Add_Click({
    Stop-ViewportDrag
    $script:yaw = $script:defaultYaw
    $script:pitch = $script:defaultPitch
    $script:distance = $script:defaultDistance
    $script:modelCenter=$script:defaultModelCenter
    Update-Camera
})

# ============================================================================
# AI Texture Generator
# ============================================================================

$script:genStudioProjectId = $null
$script:aiGenerating = $false
$script:generatedPreviewPath = $null
$script:generatedPreviewRecord = $null
$script:aiStyleReferencePath = $null

function Get-TextureGenerationMetadata {
    param($Selected, [string]$SourcePath)
    $bitmap = [System.Drawing.Bitmap]::new($SourcePath)
    try {
        $hasAlpha = (($bitmap.PixelFormat -band [System.Drawing.Imaging.PixelFormat]::Alpha) -ne 0) -or
                    (($bitmap.PixelFormat -band [System.Drawing.Imaging.PixelFormat]::PAlpha) -ne 0)
        return [ordered]@{
            textureName = if ($Selected.DisplayName) { [string]$Selected.DisplayName } else { [string]$Selected.Label }
            textureCategory = if ($Selected.Group) { [string]$Selected.Group } else { [string]$script:activeCategory }
            resolution = ('{0}x{1}' -f $bitmap.Width, $bitmap.Height)
            alphaInformation = if ($hasAlpha) { 'Original texture contains an alpha channel; preserve it pixel-for-pixel.' } else { 'Original texture has no alpha channel; do not introduce transparency.' }
            materialTextureSlot = if ($Selected.Label) { [string]$Selected.Label } else { 'selected material slot' }
            uvTarget = if ($Selected.ResourceId) { [string]$Selected.ResourceId } else { 'component {0}, zone {1}' -f $Selected.Component, $Selected.Zone }
        }
    } finally { $bitmap.Dispose() }
}

function Get-UvLockedGenerationPrompt {
    param([string]$UserPrompt, $Metadata)
    return @"
Modify the supplied original game texture only.

Preserve the exact canvas dimensions, aspect ratio, UV island positions, transparency and alpha regions, seams, orientation, texture boundaries, mapped regions, and padding between UV islands.

Do not move, rotate, resize, crop, add, delete, or rearrange any mapped regions.

Only change the visual appearance inside the existing texture layout according to the user's design request.

The generated output must remain directly compatible with the game's existing UV mapping and must be applicable to the current 3D model without changing UV coordinates.

Selected texture metadata:
- Texture name: $($Metadata.textureName)
- Texture category: $($Metadata.textureCategory)
- Resolution: $($Metadata.resolution)
- Alpha information: $($Metadata.alphaInformation)
- Material / texture slot: $($Metadata.materialTextureSlot)
- UV target: $($Metadata.uvTarget)

User design request:
$UserPrompt
"@
}

function Save-UvLockedGeneratedTexture {
    param([string]$SourcePath, [string]$GeneratedPath, [string]$DestinationPath)
    $source = [System.Drawing.Bitmap]::new($SourcePath)
    $generated = [System.Drawing.Bitmap]::new($GeneratedPath)
    $normalized = [System.Drawing.Bitmap]::new($source.Width, $source.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($normalized)
        try {
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
            $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($generated, 0, 0, $source.Width, $source.Height)
        } finally { $graphics.Dispose() }

        # Enforce the source alpha mask locally so transparent UV padding and
        # cutout boundaries cannot be changed even if the model ignores text.
        $source32 = [System.Drawing.Bitmap]::new($source.Width, $source.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $g = [System.Drawing.Graphics]::FromImage($source32)
            try { $g.DrawImageUnscaled($source, 0, 0) } finally { $g.Dispose() }
            $rect = [System.Drawing.Rectangle]::new(0, 0, $source.Width, $source.Height)
            $srcData = $source32.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
            $dstData = $normalized.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
            try {
                $byteCount = [Math]::Abs($srcData.Stride) * $source.Height
                $srcBytes = [byte[]]::new($byteCount)
                $dstBytes = [byte[]]::new($byteCount)
                [Runtime.InteropServices.Marshal]::Copy($srcData.Scan0, $srcBytes, 0, $byteCount)
                [Runtime.InteropServices.Marshal]::Copy($dstData.Scan0, $dstBytes, 0, $byteCount)
                for ($i = 3; $i -lt $byteCount; $i += 4) { $dstBytes[$i] = $srcBytes[$i] }
                [Runtime.InteropServices.Marshal]::Copy($dstBytes, 0, $dstData.Scan0, $byteCount)
            } finally {
                $source32.UnlockBits($srcData)
                $normalized.UnlockBits($dstData)
            }
        } finally { $source32.Dispose() }

        $destinationDir = Split-Path -Parent $DestinationPath
        New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
        $normalized.Save($DestinationPath, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $normalized.Dispose(); $generated.Dispose(); $source.Dispose()
    }
    return $DestinationPath
}

function Get-OrCreateGenStudioProject {
    if ($null -ne $script:genStudioProjectId) {
        return $script:genStudioProjectId
    }
    try {
        $projects = Invoke-RestMethod -Uri 'http://localhost:3001/api/projects' -Method Get -ErrorAction SilentlyContinue
        if ($projects -and $projects.value) {
            $existing = $projects.value | Where-Object { $_.name -eq 'Jackdaw Workshop' }
            if ($existing) {
                $script:genStudioProjectId = $existing.id
                return $script:genStudioProjectId
            }
        }
        # Create new project
        $newProject = Invoke-RestMethod -Uri 'http://localhost:3001/api/projects' -Method Post -Body '{"name":"Jackdaw Workshop"}' -ContentType 'application/json' -ErrorAction SilentlyContinue
        if ($newProject -and $newProject.id) {
            $script:genStudioProjectId = $newProject.id
            return $script:genStudioProjectId
        }
    } catch {
        Set-UiText $AiStatusText "Failed to connect to 3DGenStudio project API"
    }
    return $null
}

function Invoke-AiTextureGeneration {
    param([string]$Prompt)
    if ($script:aiGenerating) { return }
    $selected = Get-SelectedZone
    if (-not $selected -or $selected.IsGroupHeader) {
        Set-UiText $AiStatusText 'Select an extracted game texture before generating.'
        return
    }
    $sourcePath = Get-RecordOriginalTexturePath $selected
    if (-not $sourcePath -or -not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        Set-UiText $AiStatusText 'The selected extracted game texture is unavailable. Export or extract it first.'
        return
    }
    $script:aiGenerating = $true
    Set-UiText $AiStatusText 'Editing the selected game texture with UV layout locked...'
    $AiGenerateButton.IsEnabled = $false
    $AiCancelButton.IsEnabled = $false

    $projectId = Get-OrCreateGenStudioProject
    if (-not $projectId) {
        Set-UiText $AiStatusText 'Cannot connect to 3DGenStudio. Check that it is running.'
        $script:aiGenerating = $false
        $AiGenerateButton.IsEnabled = $true
        $AiCancelButton.IsEnabled = $true
        return
    }

    try {
        $metadata = Get-TextureGenerationMetadata -Selected $selected -SourcePath $sourcePath
        $combinedPrompt = Get-UvLockedGenerationPrompt -UserPrompt $Prompt -Metadata $metadata
        $sourceAbs = (Get-Item -LiteralPath $sourcePath).FullName
        $uploadArgs = @('-s', '-X', 'POST', 'http://localhost:3001/api/assets/upload', '-F', "projectId=$projectId", '-F', 'type=image', '-F', "name=uv-source-$(Get-Date -Format 'yyyyMMdd-HHmmss')", '-F', "file=@$sourceAbs")
        $uploadResult = (curl.exe $uploadArgs 2>&1) | ConvertFrom-Json
        if (-not $uploadResult -or -not $uploadResult.id) { throw '3DGenStudio could not accept the selected source texture.' }

        $styleReferenceId = $null
        if ($script:aiStyleReferencePath -and (Test-Path -LiteralPath $script:aiStyleReferencePath -PathType Leaf)) {
            $styleAbs = (Get-Item -LiteralPath $script:aiStyleReferencePath).FullName
            $styleArgs = @('-s', '-X', 'POST', 'http://localhost:3001/api/assets/upload', '-F', "projectId=$projectId", '-F', 'type=image', '-F', "name=style-reference-$(Get-Date -Format 'yyyyMMdd-HHmmss')", '-F', "file=@$styleAbs")
            $styleUpload = (curl.exe $styleArgs 2>&1) | ConvertFrom-Json
            if ($styleUpload -and $styleUpload.id) {
                $styleReferenceId = $styleUpload.id
                $combinedPrompt += "`n`nAn additional image is supplied only as a visual style reference. Never copy its composition, dimensions, boundaries, or layout. The first supplied game texture exclusively controls all UV structure."
            }
        }

        $body = @{
            projectId = $projectId
            assetId = $uploadResult.id
            imageSource = $uploadResult.id
            selectedApi = 'openai_gpt_image_1'
            prompt = $combinedPrompt
            name = "jackdaw_uv_edit_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        }
        if ($styleReferenceId) { $body.styleReference = $styleReferenceId }
        $body = $body | ConvertTo-Json -Depth 8

        $result = Invoke-RestMethod -Uri 'http://localhost:3001/api/image-edits/api' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 180 -ErrorAction Stop

        if ($result -and $result.imagePath) {
            $imagePath = $result.imagePath
            if (Test-Path $imagePath) {
                try {
                    $generatedDir = if ($script:currentProject) { Join-Path $script:currentProject 'generated' } else { Join-Path $dataRoot 'generated' }
                    $safeName = ([string]$metadata.textureName -replace '[^A-Za-z0-9_.-]+', '_').Trim('_')
                    if (-not $safeName) { $safeName = 'jackdaw_texture' }
                    $uvLockedPath = Join-Path $generatedDir ("{0}_{1}.png" -f $safeName, (Get-Date -Format 'yyyyMMdd_HHmmss'))
                    Save-UvLockedGeneratedTexture -SourcePath $sourcePath -GeneratedPath $imagePath -DestinationPath $uvLockedPath | Out-Null
                    $img = [Windows.Media.Imaging.BitmapImage]::new()
                    $img.BeginInit()
                    $img.CacheOption = 'OnLoad'
                    $img.UriSource = [Uri]::new($uvLockedPath)
                    $img.EndInit()
                    $img.Freeze()
                    $script:generatedPreviewPath = $uvLockedPath
                    $script:generatedPreviewRecord = $selected
                    if ($replacementPreview) { $replacementPreview.Source = $img }
                    if ($replacementPreviewEmpty) { $replacementPreviewEmpty.Visibility = 'Collapsed' }
                    Set-UiText $AiStatusText 'Generated Preview ready. The extracted source remains unchanged until Apply or Export.'
                } catch {
                    Set-UiText $AiStatusText "Generated but could not display: $($_.Exception.Message)"
                }
            } else {
                Set-UiText $AiStatusText "Generated but file not found at: $imagePath"
            }
        } elseif ($result -and $result.error) {
            Set-UiText $AiStatusText "Generation failed: $($result.error)"
        } else {
            Set-UiText $AiStatusText 'Image editing returned an unexpected response.'
        }
    } catch {
        $msg = $_.Exception.Message
        if ($msg -match 'API key') {
            Set-UiText $AiStatusText "OpenAI API key not configured in 3DGenStudio settings."
        } else {
            Set-UiText $AiStatusText "Error: $msg"
        }
    } finally {
        $script:aiGenerating = $false
        $AiGenerateButton.IsEnabled = $true
        $AiCancelButton.IsEnabled = $true
    }
}

if ($AiGenerateButton) {
    $AiGenerateButton.Add_Click({
        $prompt = if ($AiPromptInput) { $AiPromptInput.Text } else { '' }
        if ([string]::IsNullOrWhiteSpace($prompt)) {
            Set-UiText $AiStatusText 'Please enter a prompt describing the texture.'
            return
        }
        Invoke-AiTextureGeneration $prompt
    })
}

if ($AiStyleReferenceButton) {
    $AiStyleReferenceButton.Add_Click({
        $dialog = [Microsoft.Win32.OpenFileDialog]::new()
        $dialog.Title = 'Choose an optional style reference image'
        $dialog.Filter = 'Image files (*.png;*.jpg;*.jpeg;*.webp)|*.png;*.jpg;*.jpeg;*.webp'
        if ($dialog.ShowDialog($window)) {
            $script:aiStyleReferencePath = $dialog.FileName
            Set-UiText $AiStatusText "Style reference: $(Split-Path $dialog.FileName -Leaf). The selected game texture still controls the UV layout."
        }
    })
}

if ($AiCancelButton) {
    $AiCancelButton.Add_Click({
        if (-not $script:aiGenerating) {
            Set-UiText $AiStatusText 'Ready.'
            if ($AiPromptInput) { $AiPromptInput.Text = '' }
            $script:aiStyleReferencePath = $null
        }
    })
}

# ============================================================================
# Optional 3DGenStudio connection (user-started for AI texture generation)
# ============================================================================

function Test-3DGenStudioReady {
    # Only a valid JSON API response counts as "ready" — a restarting backend
    # can answer with an HTML shell or an empty body, which would otherwise
    # surface as "Invalid JSON primitive" later.
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri 'http://localhost:3001/api/projects' -Method Get -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200 -and $response.Headers['Content-Type'] -match 'application/json') {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Invoke-StudioJson {
    # Retry-safe JSON call against the 3DGenStudio backend. The backend can
    # restart a few times at startup (service crashes), so transient failures
    # must not fail the pipeline.
    param(
        [string]$Method,
        [string]$Uri,
        [string]$Body,
        [string]$ContentType,
        [int]$Attempts = 4,
        [int]$TimeoutSec = 4
    )
    if (-not (Test-3DGenStudioReady)) {
        throw '3DGenStudio backend is not responding'
    }
    $lastError = $null
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        try {
            if ($Body) {
                return Invoke-RestMethod -Uri $Uri -Method $Method -Body $Body -ContentType $ContentType -TimeoutSec $TimeoutSec -ErrorAction Stop
            }
            return Invoke-RestMethod -Uri $Uri -Method $Method -TimeoutSec $TimeoutSec -ErrorAction Stop
        } catch {
            $lastError = $_
            Start-Sleep -Milliseconds 1200
        }
    }
    throw $lastError
}

# ============================================================================
# Optional model upload bridge (never invoked during Drydock startup)
# ============================================================================

function Start-JackdawAssetExtraction {
    # Validate the verified standalone artifacts only. Never recreate or copy
    # one of the retired preview models into the release folder.
    Set-UiText $loadingText 'Preparing Jackdaw model...'
    $outputDir = Join-Path $appRoot 'jackdaw'
    $canonicalGlb = Join-Path $outputDir 'jackdaw-model-full.glb'
    $nativeBridge = Join-Path $outputDir 'jackdaw-model-full.j3d'
    if (-not (Test-Path -LiteralPath $canonicalGlb -PathType Leaf) -or
        -not (Test-Path -LiteralPath $nativeBridge -PathType Leaf)) {
        throw 'The verified Jackdaw model artifacts are missing. Retired preview models cannot be restored automatically.'
    }
    Set-UiText $loadingText 'Verified Jackdaw model ready'
}

function Send-AssetsTo3DGenStudio {
    param([string]$appRoot)
    try {
        # Verify 3DGenStudio is running
        $projects = Invoke-StudioJson -Method 'Get' -Uri 'http://localhost:3001/api/projects'
        $project = $projects | Where-Object { $_.name -eq 'Jackdaw Workshop' }
        if (-not $project) {
            # Create the Jackdaw Workshop project if it does not exist yet
            Set-UiText $loadingText 'Creating Jackdaw Workshop project in 3DGenStudio...'
            try {
                $newProject = Invoke-StudioJson -Method 'Post' -Uri 'http://localhost:3001/api/projects' -Body '{"name":"Jackdaw Workshop"}' -ContentType 'application/json'
                $project = $newProject
            } catch {
                Set-UiText $loadingText 'Could not create 3DGenStudio project'
                return
            }
        }
        $projectId = $project.id

        # The complete Jackdaw (104 UV-mapped zones) is what 3DGenStudio displays.
# It is a build artifact produced by build_full_jackdaw.py. If it is absent,
# rebuild it; NEVER let a plain J3D->GLB conversion of the 33-zone hull/sails
# model overwrite the full ship on every launch.
$jackdawDir = Join-Path $appRoot 'jackdaw'
$glbPath = Join-Path $jackdawDir 'jackdaw-model-full.glb'
if (-not (Test-Path -LiteralPath $glbPath)) {
    Set-UiText $loadingText 'Verified jackdaw-model-full.glb is missing'
    return
}

        # Upload converted GLB via curl.exe multipart form (reliable on Windows)
        if (-not (Test-3DGenStudioReady)) {
            Set-UiText $loadingText '3DGenStudio backend restarted — retrying upload...'
            Start-Sleep -Seconds 2
            if (-not (Test-3DGenStudioReady)) {
                Set-UiText $loadingText '3DGenStudio backend is not ready — please relaunch the app'
                return
            }
        }
        $glbAbsPath = (Get-Item $glbPath).FullName
        # Reuse the existing jackdaw-model-full asset when present instead of
        # creating a duplicate on every launch (keeps the studio project clean
        # and skips the redundant upload).
        $result = $null
        try {
            $assetsJson = Invoke-RestMethod -Uri "http://localhost:3001/api/assets?projectId=$projectId" -Method Get -TimeoutSec 6 -ErrorAction Stop
            # The backend may return a bare array, a { value: [...] } wrapper,
            # or a single object; normalize all shapes before filtering.
            if ($assetsJson -is [System.Collections.IDictionary] -and $null -ne $assetsJson.value) {
                $assetsJson = $assetsJson.value
            }
            if ($assetsJson -isnot [System.Collections.IEnumerable] -or $assetsJson -is [string]) {
                $assetsJson = @($assetsJson)
            }
            $existingAsset = @($assetsJson | Where-Object { $_ -and $_.name -eq 'jackdaw-model-full' } | Select-Object -First 1)
            if ($existingAsset) {
                $result = @{ id = [string]$existingAsset.id }
                Set-UiText $loadingText ('Refreshing model asset {0} in 3DGenStudio' -f $existingAsset.id)
            }
        } catch { }
        if (-not $result) {
            $uploadArgs = @(
                '-s', '-X', 'POST',
                "http://localhost:3001/api/assets/upload",
                "-F", "projectId=$projectId",
                "-F", "type=mesh",
                "-F", "name=jackdaw-model-full",
                "-F", "file=@$glbAbsPath"
            )
            # Attach the sub-mesh inventory sidecar (node names, material slots, UV bounds)
            $meshSidecar = Join-Path $jackdawDir 'jackdaw-model-full.mesh.json'
            if (Test-Path $meshSidecar) {
                $uploadArgs += @("-F", "metadata=<$meshSidecar")
            }
            $uploadOutput = curl.exe $uploadArgs 2>&1
            if (-not $uploadOutput) {
                Set-UiText $loadingText 'Model upload failed — empty response from 3DGenStudio'
                return
            }
            $result = $uploadOutput | ConvertFrom-Json
            Set-UiText $loadingText ('Model uploaded to 3DGenStudio (asset {0})' -f $result.id)
        }

        # Purge the viewport scene BEFORE mounting the new model: dispose all
        # lingering geometries/materials/textures, remove ghost child nodes,
        # and re-instantiate the studio lighting so each load starts clean.
        $purgeResult = Invoke-OnUiThread { Invoke-ViewportScenePurge }
        if ($purgeResult.purged) {
            Set-UiText $loadingText ('Viewport purged: {0} geometries, {1} materials, {2} textures, {3} nodes, {4} lights restored' -f $purgeResult.disposedGeometries, $purgeResult.disposedMaterials, $purgeResult.disposedTextures, $purgeResult.removedNodes, $purgeResult.relitLights)
        }

        # Also call mesh editor save to load the mesh in the viewport
        try {
            $meshArgs = @(
                '-s', '-X', 'POST',
                "http://localhost:3001/api/meshes/editor/save",
                "-F", "assetId=$($result.id)",
                "-F", "name=jackdaw-model-full",
                "-F", "saveMode=replace",
                "-F", "meshFile=@$glbAbsPath"
            )
            $meshOutput = curl.exe $meshArgs 2>&1
            if ($meshOutput) {
                $meshResult = $meshOutput | ConvertFrom-Json
            }
        }
        catch {
            Set-UiText $loadingText ('Model uploaded — mesh editor: {0}' -f $_.Exception.Message)
        }

        # Track the mounted sub-meshes by their GLTF node-name strings
        # (child.name), never by auto-incrementing ids or array indices, so
        # targeting stays stable across reloads and re-imports.
        $subMeshNames = @()

        # Open 3DGenStudio's Mesh Editor on the saved asset so the model is
        # actually mounted in the viewport. The frontend mounts a mesh ONLY
        # when the window is on the /mesh-editor route with the resolved
        # asset URL (the ZG editor component requires a `url` query param; the
        # project board route does not mount any mesh). The editor/save
        # response ($meshResult) already carries the {id, filename, filePath,
        # name} fields needed to build that URL.
        if ($meshResult -and $meshResult.id) {
            $meshEditorUrl = 'http://localhost:3001/mesh-editor?' + (
                'assetId={0}&filePath={1}&name={2}&projectId={3}&url={4}' -f
                $meshResult.id,
                [Uri]::EscapeDataString([string]$meshResult.filePath),
                [Uri]::EscapeDataString([string]$meshResult.name),
                $projectId,
                [Uri]::EscapeDataString('http://localhost:3001/assets/' + $meshResult.filename)
            )
        } else {
            $meshEditorUrl = "http://localhost:3001/#/projects/$projectId"
        }

        Invoke-OnUiThread {
            if ($null -ne $viewportWebBrowser) {
                try {
                    $viewportWebBrowser.Source = [Uri]::new($meshEditorUrl)
                    Apply-JackdawViewportTheme
                    # Wait for WebView2 CoreWebView2 to initialize, then inject camera-fit JS
                    $viewportWebBrowser.Add_DocumentReadyStateChanged({
                        if ($viewportWebBrowser.CoreWebView2 -and $viewportWebBrowser.CoreWebView2.IsReady) {
                            Invoke-CameraFitForLoadedModel
                        }
                    })
                    # Also do a direct check in case it's already ready
                    if ($viewportWebBrowser.CoreWebView2 -and $viewportWebBrowser.CoreWebView2.IsReady) {
                        Invoke-CameraFitForLoadedModel
                    }
                } catch { }
            }
        }

        # Poll for the mounted sub-mesh names now that the editor has loaded.
        # Call Invoke-ReadSubMeshNames directly on this background thread: its
        # ExecuteScriptAsync round-trip would otherwise block the WPF dispatcher
        # up to 60 times and freeze the UI while waiting for the editor.
        if ($null -ne $viewportWebBrowser) {
            for ($i = 0; $i -lt 60; $i++) {
                Start-Sleep -Milliseconds 500
                $subMeshNames = Invoke-ReadSubMeshNames
                if (@($subMeshNames).Count -gt 0) { break }
            }
        }
        if (@($subMeshNames).Count -gt 0) {
            $display = (@($subMeshNames) | Select-Object -First 8) -join ', '
            if (@($subMeshNames).Count -gt 8) { $display += ', ...' }
            Set-UiText $loadingText ('Model loaded — {0} named sub-meshes: {1}' -f @($subMeshNames).Count, $display)
            Invoke-OnUiThread { Set-PreviewRenderer '3dgen' }
        } else {
            Set-UiText $loadingText 'Model saved — viewport refresh pending'
        }
    }
    catch {
        Set-UiText $loadingText ('3DGenStudio connection failed: {0}' -f $_.Exception.Message)
        Invoke-OnUiThread { Set-PreviewRenderer 'native' }
    }
}

# ============================================================================
# Camera Fit & Lighting Fix for 3DGenStudio Viewport
# ============================================================================
# After the GLB is uploaded and loaded, the model is at origin (centered +
# scaled by the converter) but the camera may still be at its default
# position. 3DGenStudio's R3F viewport uses React Three Fiber + drei's
# CameraControls.
#
# Strategy (in priority order):
#   1. Click any "Fit" / "Reset" / "Center" / "View" button in 3DGenStudio's UI
#   2. Find the Three.js renderer's scene via React Fiber root, compute the
#      mesh bounding box, and manually position the camera to frame it
#   3. Try to find a CameraControls instance on the window and call reset()
# ============================================================================

function Invoke-CameraFitForLoadedModel {
    # Wait for CoreWebView2 to be ready
    $maxWait = 30
    $elapsed = 0
    while (-not $viewportWebBrowser.CoreWebView2 -and $elapsed -lt $maxWait) {
        Start-Sleep -Milliseconds 200
        $elapsed += 0.2
    }
    if (-not $viewportWebBrowser.CoreWebView2) {
        Set-UiText $loadingText 'WebView2 CoreWebView2 not available — camera fit skipped'
        return
    }

    # Step 1: Wait for the mesh to be loaded in the viewport
    # The viewport shows "Mesh loaded in viewport (Mesh N)" when ready
    for ($i = 0; $i -lt 20; $i++) {
        $meshCheck = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync(
            'document.body.innerText.includes("Mesh loaded")'
        ).GetAwaiter().GetResult()
        if ($meshCheck -eq "true" -or $meshCheck -eq $true) {
            break
        }
        Start-Sleep -Milliseconds 500
    }

    # Step 2: Try to click a "Fit" / "Reset" / "Center" / "View" button
    $clickFitJS = @'
(function() {
    var allEls = document.querySelectorAll("button, [role=button], [data-testid], .btn, [class*='btn']");
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var text = (el.textContent || el.innerText || el.title || "").trim().toLowerCase();
        if (text.indexOf("fit") !== -1 || text.indexOf("reset") !== -1 ||
            text.indexOf("center") !== -1 || text.indexOf("view all") !== -1 ||
            text.indexOf("show all") !== -1 || text.indexOf("fit camera") !== -1 ||
            text.indexOf("fit model") !== -1) {
            el.click();
            return { clicked: true, text: (el.textContent || el.innerText || el.title || "unknown") };
        }
    }
    return { clicked: false };
})();
'@
    try {
        $clickResult = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($clickFitJS).GetAwaiter().GetResult()
        if ($clickResult -and $clickResult -ne "null") {
            try {
                $parsed = $clickResult | ConvertFrom-Json
                if ($parsed.clicked) {
                    Set-UiText $loadingText ('Fit button clicked: {0}' -f $parsed.text)
                    return
                }
            } catch { }
        }
    } catch {
        # Non-fatal
    }

    # Step 3: Manual camera-fit via Three.js renderer scene traversal
    # This works regardless of whether drei's CameraControls is used or not.
    # It finds the Three.js renderer through the React Fiber root on the canvas,
    # walks the scene graph to find all meshes, computes the bounding box,
    # and repositions the camera to frame the model.
    $manualFitJS = @'
(function() {
    try {
        // Find the canvas element used by Three.js / R3F
        var canvas = document.querySelector("canvas");
        if (!canvas) return { method: "no_canvas" };

        // Get the Three.js renderer from the React Fiber root
        // React 18 stores the fiber root on the host instance
        var fiberRoot = canvas.__reactFiber$ || canvas.__reactFiberRoot$ || canvas._reactRootInstance;
        var renderer = null;

        // Try to find renderer via React internals
        if (fiberRoot) {
            var current = fiberRoot.current;
            if (current && current.memoizedState && current.memoizedState.containerInfo) {
                var host = current.memoizedState.containerInfo;
                if (host && host._renderer) { renderer = host._renderer; }
            }
        }

        // Fallback: check for renderer on canvas
        if (!renderer) {
            renderer = canvas._renderer || canvas.__renderer || canvas.renderer;
        }

        if (!renderer || !renderer.domElement) {
            // Try a broader search — the renderer may be stored on the window
            // or on the React Fiber root of the document
            var roots = [];
            try { roots = Object.values(document.querySelectorAll("canvas")).map(function(c) { return c.__reactFiber$ || c._reactRootInstance; }); } catch(e) {}
            for (var r = 0; r < roots.length; r++) {
                var root = roots[r];
                if (root && root.current && root.current.memoizedState) {
                    var ms = root.current.memoizedState;
                    if (ms && ms.memoizedUpdaters) {
                        // R3F stores the renderer in the update queue
                        for (var key in ms) {
                            if (ms[key] && ms[key].callbackNode != null) {
                                // Found the fiber root — try to get renderer
                                var fiber = root.current;
                                while (fiber && !fiber.stateNode) fiber = fiber.child;
                                if (fiber && fiber.stateNode && fiber.stateNode._renderer) {
                                    renderer = fiber.stateNode._renderer;
                                    break;
                                }
                            }
                        }
                    }
                }
            }
        }

        if (!renderer) {
            // Last resort: look for THREE in window or on the canvas
            if (typeof window !== "undefined" && window.THREE) {
                return { method: "three_found", has_three: true };
            }
            return { method: "no_renderer" };
        }

        // Get the scene and camera from the renderer
        var scene = renderer.scene;
        if (!scene) return { method: "no_scene" };

        // Find the camera — R3F stores it in the fiber root state
        var camera = null;
        if (fiberRoot && fiberRoot.current) {
            var node = fiberRoot.current;
            while (node) {
                if (node.stateNode && node.stateNode.isCamera) {
                    camera = node.stateNode;
                    break;
                }
                if (node.child) { node = node.child; }
                else { break; }
            }
        }

        // Fallback: search the scene for a PerspectiveCamera
        if (!camera) {
            scene.traverse(function(obj) {
                if (obj.isPerspectiveCamera || obj.isOrthographicCamera) {
                    camera = obj;
                }
            });
        }

        if (!camera) return { method: "no_camera" };

        // Find all meshes and compute bounding box
        var box = new THREE.Box3();
        var hasMeshes = false;
        scene.traverse(function(obj) {
            if (obj.isMesh || obj.isGroup) {
                if (obj.isMesh && obj.geometry) {
                    var geo = obj.geometry;
                    if (geo.boundingBox) {
                        box.union(geo.boundingBox.clone().applyMatrix4(obj.matrixWorld));
                        hasMeshes = true;
                    } else if (geo.attributes && geo.attributes.position) {
                        var pos = geo.attributes.position;
                        var m = new THREE.Matrix4().copy(obj.matrixWorld);
                        for (var i = 0; i < pos.count; i++) {
                            var v = new THREE.Vector3(pos.getX(i), pos.getY(i), pos.getZ(i));
                            v.applyMatrix4(m);
                            if (!hasMeshes) { box.setFromCenterAndSize(v, new THREE.Vector3()); hasMeshes = true; }
                            else box.expandByPoint(v);
                        }
                    }
                }
            }
        });

        if (!hasMeshes) return { method: "no_meshes" };

        // Compute center and size
        var center = box.getCenter(new THREE.Vector3());
        var size = box.getSize(new THREE.Vector3());
        var maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim === 0) return { method: "zero_size" };

        // Move model center to origin
        var offset = center.clone().negate();
        scene.traverse(function(obj) {
            if (obj.isMesh || obj.isGroup || obj.isObject3D) {
                obj.position.add(offset);
            }
        });

        // Update bounding box after centering
        box.setFromObject(scene);
        center = box.getCenter(new THREE.Vector3());
        size = box.getSize(new THREE.Vector3());
        maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim === 0) return { method: "zero_size_after" };

        // Calculate camera distance to frame the model
        // Use a FOV of 45 degrees (default for PerspectiveCamera)
        var fov = camera.fov || 45;
        var aspect = canvas.clientWidth / canvas.clientHeight || 1;
        var horizontalFov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(fov / 2)) * aspect);
        var distance = (maxDim / 2) / Math.tan(horizontalFov / 2);
        distance *= 1.5; // 50% padding

        // Position the camera along the negative Z axis from the center
        camera.position.set(center.x, center.y, center.z + distance);
        camera.lookAt(center.x, center.y, center.z);

        // Update camera projection matrix
        if (camera.isPerspectiveCamera) {
            camera.updateProjectionMatrix();
        }

        return { method: "manual_fit", center: center.toArray(), distance: distance, size: size.toArray() };
    } catch (err) {
        return { method: "error", error: err.message };
    }
})();
'@
    try {
        $fitResult = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($manualFitJS).GetAwaiter().GetResult()
        if ($fitResult -and $fitResult -ne "null") {
            try {
                $parsed = $fitResult | ConvertFrom-Json
                if ($parsed.method -eq "manual_fit") {
                    Set-UiText $loadingText ('Camera fitted: center=({0},{1},{2}) dist={3:F1}' -f
                        $parsed.center[0], $parsed.center[1], $parsed.center[2], $parsed.distance)
                } elseif ($parsed.method -eq "three_found") {
                    Set-UiText $loadingText 'Three.js found in window — camera fit attempted'
                } else {
                    Set-UiText $loadingText ('Camera fit result: {0}' -f $parsed.method)
                }
            } catch { }
        }
    } catch {
        # Non-fatal
    }

    # Step 4: Try to find CameraControls on window and call reset
    $ccResetJS = @'
(function() {
    // Look for CameraControls instances on the window
    var keys = Object.keys(window);
    for (var i = 0; i < keys.length; i++) {
        var val = window[keys[i]];
        if (val && val.isCameraControls && typeof val.reset === "function") {
            val.reset(true);
            return { method: "camera_controls_reset" };
        }
    }
    // Also check for controls stored on globalThis
    for (var i = 0; i < keys.length; i++) {
        var val = globalThis[keys[i]];
        if (val && val.isCameraControls && typeof val.reset === "function") {
            val.reset(true);
            return { method: "global_this_reset" };
        }
    }
    return { method: "no_camera_controls_found" };
})();
'@
    try {
        $ccResult = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($ccResetJS).GetAwaiter().GetResult()
        if ($ccResult -and $ccResult -ne "null") {
            try {
                $parsed = $ccResult | ConvertFrom-Json
                Set-UiText $loadingText ('CameraControls: {0}' -f $parsed.method)
            } catch { }
        }
    } catch {
        # Non-fatal
    }

    Set-UiText $loadingText 'Camera fit complete — model should now be visible'
}

# ============================================================================
# Viewport Scene Purge & Stable Sub-Mesh Identification
# ============================================================================
# Every model reload leaks old geometries in the Three.js scene graph, which
# produces ghost models and endlessly incrementing mesh indices. The purge
# below runs a full scene traversal before any new model is mounted: it
# disposes all geometries/materials/textures, removes every child node to
# reset the root container, and re-instantiates the studio's own lighting.
# Sub-mesh targeting is bound strictly to GLTF node-name strings
# (child.name), never to runtime child.id / array indices, so names stay
# stable across arbitrary reloads and re-imports.
# ============================================================================

function Invoke-ViewportScenePurge {
    if ($null -eq $viewportWebBrowser -or $null -eq $viewportWebBrowser.CoreWebView2 -or -not $viewportWebBrowser.CoreWebView2.IsReady) {
        return @{ purged = $false; error = 'viewport not ready' }
    }
    $script = @'
(function() {
    function resolveScene() {
        var canvases = document.querySelectorAll("canvas");
        for (var ci = 0; ci < canvases.length; ci++) {
            var c = canvases[ci];
            var root = c.__r3f || c[Object.keys(c).find(function(k) { return k.indexOf("__reactFiber") === 0 || k.indexOf("__fiber") === 0; })];
            if (root && root.store) {
                var state = root.store.getState();
                if (state && state.scene) return { scene: state.scene };
            }
        }
        for (var ci = 0; ci < canvases.length; ci++) {
            var c = canvases[ci];
            var r = c._renderer || c.__renderer || c.renderer;
            if (r && r.scene) return { scene: r.scene };
        }
        return null;
    }
    var info = resolveScene();
    if (!info) return { purged: false, error: "no_scene" };
    var scene = info.scene;
    var disposedGeometries = 0, disposedMaterials = 0, disposedTextures = 0;
    var lightsBefore = [];
    scene.traverse(function(obj) {
        if (obj.isLight) {
            lightsBefore.push({
                ctor: obj.constructor,
                type: obj.type,
                color: obj.color ? obj.color.getHex() : null,
                intensity: obj.intensity,
                castShadow: !!obj.castShadow,
                x: obj.position.x, y: obj.position.y, z: obj.position.z
            });
        }
        if (obj.geometry && obj.geometry.dispose) { obj.geometry.dispose(); disposedGeometries++; }
        if (obj.material) {
            var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            for (var mi = 0; mi < mats.length; mi++) {
                var m = mats[mi];
                if (!m) continue;
                for (var key in m) {
                    var v = m[key];
                    if (v && v.isTexture && v.dispose) { v.dispose(); disposedTextures++; }
                }
                if (m.dispose) { m.dispose(); disposedMaterials++; }
            }
        }
    });
    var removedNodes = 0;
    while (scene.children.length) { scene.remove(scene.children[0]); removedNodes++; }
    var relitLights = 0;
    for (var li = 0; li < lightsBefore.length; li++) {
        var L = lightsBefore[li];
        try {
            var light = new L.ctor(L.color, L.intensity);
            light.castShadow = L.castShadow;
            light.position.set(L.x, L.y, L.z);
            scene.add(light);
            relitLights++;
        } catch (e) { }
    }
    try { window.__jackdawSubMeshNames = null; } catch (e) { }
    return {
        purged: true,
        disposedGeometries: disposedGeometries,
        disposedMaterials: disposedMaterials,
        disposedTextures: disposedTextures,
        removedNodes: removedNodes,
        relitLights: relitLights
    };
})()
'@
    try {
        $raw = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($script).GetAwaiter().GetResult()
        if ($raw -and $raw -ne 'null') { return $raw | ConvertFrom-Json }
    } catch { }
    return @{ purged = $false; error = 'injection failed' }
}

function Apply-JackdawViewportTheme {
    # Strip 3DGenStudio's own app chrome from the mesh-editor page so the WebView
    # shows only the 3D canvas, matching the Jackdaw app's dark UI. Injected on
    # document creation so it survives editor reloads, then applied immediately.
    if ($null -eq $viewportWebBrowser -or $null -eq $viewportWebBrowser.CoreWebView2) { return }
    $css = @'
html, body, #root { height: 100% !important; width: 100% !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; background: #07191f !important; }
.header, header, [class*="app-header"], [class*="topbar"], [class*="navbar"], [class*="navigation"] { display: none !important; }
.mesh-editor-layout { height: 100vh !important; width: 100vw !important; max-height: 100vh !important; }
.mesh-editor-page { height: 100% !important; padding: 0 !important; overflow: hidden !important; }
.mesh-editor-shell { height: 100% !important; display: flex !important; flex-direction: column !important; }
.mesh-editor-toolbar { display: none !important; }
.mesh-editor-canvas-shell { flex: 1 1 auto !important; height: auto !important; min-height: 0 !important; }
canvas { outline: none !important; }
'@
    $js = "(function(){var s=document.getElementById('jackdaw-viewport-theme');if(!s){s=document.createElement('style');s.id='jackdaw-viewport-theme';document.head.appendChild(s);}s.textContent=" + ($css | ConvertTo-Json -Compress) + ";})()"
    try {
        $viewportWebBrowser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync($js).GetAwaiter().GetResult() | Out-Null
        $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($js).GetAwaiter().GetResult() | Out-Null
    } catch { }
}

function Invoke-ReadSubMeshNames {
    if ($null -eq $viewportWebBrowser -or $null -eq $viewportWebBrowser.CoreWebView2 -or -not $viewportWebBrowser.CoreWebView2.IsReady) {
        return @()
    }
    $script = @'
(function() {
    function resolveScene() {
        var canvases = document.querySelectorAll("canvas");
        for (var ci = 0; ci < canvases.length; ci++) {
            var c = canvases[ci];
            var root = c.__r3f || c[Object.keys(c).find(function(k) { return k.indexOf("__reactFiber") === 0 || k.indexOf("__fiber") === 0; })];
            if (root && root.store) {
                var state = root.store.getState();
                if (state && state.scene) return { scene: state.scene };
            }
        }
        for (var ci = 0; ci < canvases.length; ci++) {
            var c = canvases[ci];
            var r = c._renderer || c.__renderer || c.renderer;
            if (r && r.scene) return { scene: r.scene };
        }
        return null;
    }
    var info = resolveScene();
    if (!info) return [];
    var names = [];
    info.scene.traverse(function(obj) {
        if (obj.isMesh && obj.name && names.indexOf(obj.name) === -1) names.push(obj.name);
    });
    try { window.__jackdawSubMeshNames = names; } catch (e) { }
    return names;
})()
'@
    try {
        $raw = $viewportWebBrowser.CoreWebView2.ExecuteScriptAsync($script).GetAwaiter().GetResult()
        if ($raw -and $raw -ne 'null' -and $raw -ne '[]') {
            $parsed = $raw | ConvertFrom-Json
            if ($parsed) { return @($parsed) }
        }
    } catch { }
    return @()
}

$game = Find-Game
if (-not $game) { $game = Get-PersistedGameFolder }
if ($game) {
    $script:gameFolder = $game
    Save-PersistedGameFolder $game
    $forgeCount = @(Get-ChildItem -LiteralPath $game -Filter 'DataPC*.forge' -File -ErrorAction SilentlyContinue).Count
    Set-UiText $gameStatus ("Game recognized | {0} archives | read only" -f $forgeCount)
    $gameStatus.Foreground = [Windows.Media.Brushes]::LightGreen
} else {
    Set-UiText $gameStatus 'Game folder not found automatically'
}

function Start-StartupPipelineBackground {
    # Drydock is a standalone application. 3DGenStudio is opened only when a
    # user explicitly requests an AI generation action; it must never launch,
    # upload, or replace the viewport model during ordinary Drydock startup.
    Set-PreviewRenderer 'native'
    Set-UiText $loadingText 'Verified Jackdaw model ready'
}

$window.Add_ContentRendered({
    # Populate the initial category (Sails) right away so the app is usable
    # the instant it appears; all heavy post-launch work runs in the background.
    [void](Initialize-NativeViewport)
    # Let the opening frame and browser initialization run before native preparation.
    [void]$window.Dispatcher.BeginInvoke([Windows.Threading.DispatcherPriority]::ContextIdle,[Action]{
        try {Load-JackdawModel;Update-TexturePreview}
        catch {$window.FindName('StartupLoadingStage').Text='Model could not load';Set-UiText $footer $_.Exception.Message}
    })
})
. (Join-Path $appRoot 'FastModelReader.ps1')
. (Join-Path $appRoot 'NativeSilhouette.ps1')
. (Join-Path $appRoot 'NativeFinishEditor.ps1')
. (Join-Path $appRoot 'NativeMetalShading.ps1')
. (Join-Path $appRoot 'NativeDesignWorkflow.ps1')
. (Join-Path $appRoot 'NativeInstallWorkflow.ps1')
. (Join-Path $appRoot 'GenerationDrawer.ps1')
. (Join-Path $appRoot 'EmbeddedScene.ps1')
# Resolve exact per-surface bindings now that the native metadata is loaded.
Refresh-JackdawMaterials
if ($LoadTest) {
    [void](Initialize-NativeViewport)
    Load-JackdawModel
    $sailGeoms = @($componentGroups[$sailComponentIndex].Children | Where-Object { $_ -is [Windows.Media.Media3D.GeometryModel3D] })
    "Jackdaw WPF load OK: $($zoneRecords.Count) selectable zones | $($componentGroups.Count) components | native viewport: $([bool]$script:nativeViewport) | $($sailGeoms.Count) sail sub-meshes"
    $hull = $zoneRecords | Where-Object { $_.Component -eq 0 -and $_.Zone -eq 0 } | Select-Object -First 1
    $sail = $zoneRecords | Where-Object { $_.Component -eq $sailComponentIndex -and $_.Zone -eq 0 } | Select-Object -First 1
    foreach ($z in @($hull,$sail)) {
        if (-not $z) { continue }
        $b = $z.Geometry.Material.Brush
        "zone [$($z.Component)/$($z.Zone)] $($z.Label) brush=$($b.GetType().Name) $([bool]($b -is [Windows.Media.ImageBrush]))"
    }

    # --- Sail default-texture audit ---
    $defaultKeys = @{}
    $imgBrushSails = 0
    foreach ($i in 0..($sailGeoms.Count-1)) {
        $z = $zoneRecords | Where-Object { $_.Component -eq $sailComponentIndex -and $_.Zone -eq $i } | Select-Object -First 1
        $k = Get-DefaultAppearanceTextureKey $sailComponentIndex $i
        $defaultKeys[$k] = 1 + [int]$defaultKeys[$k]
        if ($z -and $z.Geometry.Material.Brush -is [Windows.Media.ImageBrush]) { $imgBrushSails++ }
    }
    "sail default key distribution: " + (($defaultKeys.GetEnumerator() | ForEach-Object { "$($_.Key)x$($_.Value)" }) -join ', ')
    "sail geometries with ImageBrush: $imgBrushSails / $($sailGeoms.Count)"
    "default ship texture bindings: " + ((0..5 | ForEach-Object {
        "$($componentNames[$_])=$(Get-DefaultAppearanceTextureKey $_ 0)"
    }) -join ' | ')
    "library category counts: " + ((@('Sails','Hulls','Cannons','Mortars','Flags','Figureheads','Wheels','Cabin') | ForEach-Object {
        $categoryName = $_
        $categoryRecords = @(Get-VisibleRecords $categoryName)
        "$categoryName=$(@($categoryRecords | Where-Object { -not $_.IsGroupHeader }).Count)"
    }) -join ' | ')
    "material region counts: " + ((@('Sail Regions','Hull Regions','Masts','Rigging','Flag Regions','Weapon Regions','Lanterns','Details','Ram','Rudder') | ForEach-Object {
        $categoryName = $_
        "$categoryName=$(@(Get-SourceRecords $categoryName).Count)"
    }) -join ' | ')
    $selectionProbe = @(Get-SourceRecords 'Hull Regions') | Select-Object -First 1
    Show-ZoneSelectionHighlight $selectionProbe
    if (-not ($script:selectionBox -is [Windows.Controls.Image]) -or -not $script:silhouetteModel -or $script:silhouetteModel.Children.Count -lt 1) {throw 'Selection silhouette missing'}
    $mask=[byte[]]::new(20*20*4)
    foreach ($y in 5..14) {foreach ($x in 5..14) {$mask[($y*20+$x)*4+3]=255}}
    $mask[(10*20+10)*4+3]=0 # an interior hole must not be outlined
    $glow=[JackdawSilhouette]::Glow($mask,20,20)
    if ($glow[(10*20+4)*4+3] -eq 0 -or $glow[(10*20+10)*4+3] -ne 0 -or $glow[(8*20+8)*4+3] -ne 0) {throw 'Silhouette includes internal edges or misses the exterior'}
    foreach ($zone in $zoneRecords) {
        $meta=Get-NativeFinishMeta $zone.Component $zone.Zone
        if ($meta -and (Get-NativeDiffuseBrush $zone.BaseMaterial).ImageSource.UriSource.LocalPath -ne (Get-NativeFinishPath $zone.Component $zone.Zone)) {throw 'Per-surface default texture mismatch'}
    }
    'PASS: exterior-only silhouette; internal holes unlit; exact per-surface startup texture assignments'
    $silhouetteRender=[JackdawSilhouette]::Render($script:silhouetteModel,$script:nativeViewport.Camera,600,400)
    $silhouettePixels=[byte[]]::new(600*400*4);$silhouetteRender.CopyPixels($silhouettePixels,2400,0)
    $litPixels=0;for ($pixel=3;$pixel -lt $silhouettePixels.Length;$pixel+=4) {if ($silhouettePixels[$pixel] -gt 0) {$litPixels++}}
    if ($litPixels -lt 10) {throw ('Actual selected geometry produced no silhouette. Bounds='+$script:silhouetteModel.Bounds+' Camera='+$script:nativeViewport.Camera.Position+' Look='+$script:nativeViewport.Camera.LookDirection)}
    $encoder=[Windows.Media.Imaging.PngBitmapEncoder]::new();$encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($silhouetteRender))
    $output=[IO.File]::Create((Join-Path $dataRoot 'silhouette-verification.png'));try {$encoder.Save($output)} finally {$output.Dispose()}
    "PASS: actual hull silhouette rendered ($litPixels glow pixels)"
    $probeMeta=Get-NativeFinishMeta $selectionProbe.Component $selectionProbe.Zone
    $samePart=@($zoneRecords | Where-Object { (Get-NativeFinishMeta $_.Component $_.Zone).part -eq $probeMeta.part }) | Select-Object -Last 1
    if (-not (Toggle-NativePartSelection $samePart) -or $script:selectionBox -or $script:nativeLastSelected -or (Get-SelectedZone)) {throw 'Click-again deselection failed'}
    Show-NativePartEdges $selectionProbe
    Clear-NativePartSelection
    if ($script:selectionBox -or $script:nativeLastSelected -or (Get-SelectedZone)) {throw 'Empty-space deselection failed'}
    foreach ($zone in $zoneRecords) {
        if (-not [object]::ReferenceEquals($zone.Geometry.Material,$zone.BaseMaterial)) {throw 'Deselect did not restore the textured model'}
    }
    'PASS: same-part toggle and clear remove the glow, clear selection and restore unfaded materials'
    if ($targetFlyout.Tag -eq 'Docked') {
        $targetFlyout.Visibility = [Windows.Visibility]::Visible
        Close-TargetFlyoutForOutsideClick $AiPromptInput
        if ($targetFlyout.Visibility -ne [Windows.Visibility]::Visible) { throw 'Docked texture workspace was hidden' }
        'texture workspace routing: docked and persistent'
    } else {
        # Legacy flyout routing regression: interaction inside must keep it open,
        # while any element outside it closes it.
        $targetFlyout.Visibility = [Windows.Visibility]::Visible
        Close-TargetFlyoutForOutsideClick $zones
        if ($targetFlyout.Visibility -ne [Windows.Visibility]::Visible) { throw 'Texture submenu regression: an inside click closed the flyout' }
        Close-TargetFlyoutForOutsideClick $AiPromptInput
        if ($targetFlyout.Visibility -ne [Windows.Visibility]::Collapsed) { throw 'Texture submenu regression: an outside click did not close the flyout' }
        'texture submenu click-away routing: inside stays open | outside closes'
    }
    # Regression: selecting a Hull family header used to recursively bounce
    # between the two synchronized lists until PowerShell stopped responding.
    Set-Category 'Hulls'
    $hullHeaderIndex = -1
    for ($i = 0; $i -lt $script:visibleZoneRecords.Count; $i++) {
        if ($script:visibleZoneRecords[$i].IsGroupHeader) { $hullHeaderIndex = $i; break }
    }
    if ($hullHeaderIndex -lt 0) {
        throw ("Hull group regression: no group header was produced. Category error: {0}" -f $script:lastCategoryError)
    }
    $hullGroupKey = [string]$script:visibleZoneRecords[$hullHeaderIndex].GroupKey
    $wasExpanded = $script:expandedHullGroups.Contains($hullGroupKey)
    $pngCollection.SelectedIndex = -1
    $hullClickTimer = [Diagnostics.Stopwatch]::StartNew()
    $pngCollection.SelectedIndex = $hullHeaderIndex
    $hullClickTimer.Stop()
    $isExpanded = $script:expandedHullGroups.Contains($hullGroupKey)
    if ($isExpanded -eq $wasExpanded) {
        throw "Hull group regression: clicking '$hullGroupKey' did not toggle its state"
    }
    if ($script:syncingSelection) {
        throw 'Hull group regression: selection synchronization guard remained stuck'
    }
    "Hull group click OK: $hullGroupKey toggled in $($hullClickTimer.ElapsedMilliseconds) ms | $($script:visibleZoneRecords.Count) visible rows"
    $uncachedCatalogItem = @($script:shipCatalog.hedefler | Where-Object {
        $auditKey = if ($_.anahtar) { [string]$_.anahtar } elseif ($_.id) { [string]$_.id } else { [string]$_.ad }
        -not (Get-CachedThumbnailPath $auditKey)
    } | Select-Object -First 1)
    if ($uncachedCatalogItem.Count -gt 0) {
        $uncachedRecord = Convert-CatalogRecord $uncachedCatalogItem[0] 0
        "uncached library tile uses empty placeholder: $($null -eq (Get-QuickThumbnail $uncachedRecord))"
        $modelFallbackPath = Get-JackdawFallbackThumbnail -lookupKey 'forced-lock-audit' -group 'hull'
        if ($modelFallbackPath) { $uncachedRecord.Thumbnail = New-ThumbnailImageSource $modelFallbackPath 72 }
        "PNG thumbnail lock rejects model fallback: $($null -eq (Get-QuickThumbnail $uncachedRecord))"
    }
    $cachedCatalogItem = @($script:shipCatalog.hedefler | Where-Object {
        $auditKey = if ($_.anahtar) { [string]$_.anahtar } elseif ($_.id) { [string]$_.id } else { [string]$_.ad }
        [bool](Get-CachedThumbnailPath $auditKey)
    } | Select-Object -First 1)
    if ($cachedCatalogItem.Count -gt 0) {
        $cachedRecord = Convert-CatalogRecord $cachedCatalogItem[0] 0
        $cachedOriginal = Get-RecordOriginalTexturePath $cachedRecord
        "cached library tile resolves actual PNG: $([bool]($cachedOriginal -and (Test-Path -LiteralPath $cachedOriginal)))"
    }
    $clay = Get-ClayPreviewMaterial
    "clay preview material: $($clay.GetType().Name) | layers=$($clay.Children.Count) | diffuse+specular=$([bool](($clay.Children[0] -is [Windows.Media.Media3D.DiffuseMaterial]) -and ($clay.Children[1] -is [Windows.Media.Media3D.SpecularMaterial])))"

    # Regression: each preview-tab reload must retain the three lights. The old
    # implementation cleared rootModel and silently removed them, rendering
    # every part and the returning Ship view black.
    $tabLighting = @()
    foreach ($testMode in @('cannon','mortar','swivel','ship')) {
        Set-ViewMode $testMode
        $lightCount = @($rootModel.Children | Where-Object {
            $_ -is [Windows.Media.Media3D.Light]
        }).Count
        $hasRenderableMaterial = [bool]($zoneRecords.Count -gt 0 -and
            $null -ne $zoneRecords[0].Geometry.Material)
        $tabLighting += "$testMode=$lightCount/$hasRenderableMaterial"
        if ($lightCount -ne 3 -or -not $hasRenderableMaterial) {
            throw "Preview tab regression: $testMode retained $lightCount lights; renderable material=$hasRenderableMaterial"
        }
    }
    "preview tab lighting/material retention: " + ($tabLighting -join ' | ')
    Test-NativeMetalShading
    Test-NativeSailGroup
    Test-NativeFinishPixels
    Test-NativeDesignWorkflow
    if ($env:JACKDAW_REVIEW_IMAGE) { . (Join-Path $appRoot '..\..\scripts\export_native_metal_review.ps1') }
    exit 0
}

[void]$window.ShowDialog()

