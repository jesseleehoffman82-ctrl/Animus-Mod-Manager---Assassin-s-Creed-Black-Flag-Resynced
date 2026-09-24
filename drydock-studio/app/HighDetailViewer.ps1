# Embedded PBR preview. The texture-prompt/generation backend remains unchanged.
function Send-HighDetailMessage($message) {
    if ($script:hdBrowser -and $script:hdReady) {
        $script:hdBrowser.CoreWebView2.PostWebMessageAsJson(($message | ConvertTo-Json -Depth 5 -Compress))
    }
}
function Set-HighDetailVisible([bool]$visible) {
    $script:hdActive = $visible -and $script:hdReady
    if ($script:hdBrowser) { $script:hdBrowser.Visibility = if ($script:hdActive) { 'Visible' } else { 'Collapsed' } }
    if ($script:nativeViewport) { $script:nativeViewport.Visibility = if ($script:hdActive) { 'Collapsed' } else { 'Visible' } }
    if ($viewportInputLayer) { $viewportInputLayer.Visibility = if ($script:hdActive) { 'Collapsed' } else { 'Visible' } }
    foreach ($name in @('LegacyComponentControls','LegacyViewportHelp')) {$control=$window.FindName($name);if ($control) {$control.Visibility=if ($script:hdActive) {'Collapsed'} else {'Visible'}}}
    if ($lightingMode) { $lightingMode.Visibility = if ($script:hdActive) { 'Collapsed' } else { 'Visible' } }
}
function Apply-HighDetailPng($record,[string]$path) {
    if (-not $script:hdActive -or -not $record.HDSurfaceId -or -not (Test-Path -LiteralPath $path)) { return $false }
    $name = 'custom-' + [Guid]::NewGuid().ToString('N') + '.png'
    Copy-Item -LiteralPath $path -Destination (Join-Path $script:hdAssetRoot $name)
    Send-HighDetailMessage @{type='apply';surfaceId=[string]$record.HDSurfaceId;shared=[bool]$record.HDShared;url=('https://jackdaw-assets.local/'+$name)}
    $record.Texture=$path
    return $true
}
function Select-HighDetailSurface($message) {
    if (-not $script:hdRecords) { $script:hdRecords=@{} }
    $item = @($script:shipCatalog.hedefler | Where-Object { $_.id -eq $message.textureId } | Select-Object -First 1)
    if ($item.Count) { $record=Convert-CatalogRecord $item[0] 0 }
    else {
        $record=Convert-CatalogRecord ([pscustomobject]@{id=$message.textureId;anahtar=$message.label;ad=$message.label;grup='hull';kullanilabilir=$false;kapsam_kaniti='Local preview material; no game injection target asserted.'}) 0
    }
    $record | Add-Member NoteProperty HDSurfaceId ([string]$message.surfaceId)
    $record | Add-Member NoteProperty HDShared ([bool]$message.shared)
    $record.Label=$message.label
    $previewName=if ($message.previewDiffuse -match '^[a-zA-Z0-9_-]+$') { $message.previewDiffuse } else { $message.textureId };$record.OriginalTexture=Join-Path $script:hdAssetRoot ($previewName+'.png')
    $record.Thumbnail=$record.OriginalTexture
    $record.Hint=if ($message.shared) { 'PNG applies to every surface using this material.' } else { 'Change the color or add a PNG. Surface detail is kept automatically.' }
    if ($script:hdRecords.ContainsKey([string]$message.surfaceId)) { $record=$script:hdRecords[[string]$message.surfaceId];$record.HDShared=[bool]$message.shared }
    else { $script:hdRecords[[string]$message.surfaceId]=$record }
    $record | Add-Member NoteProperty HDTint ([string]$message.tint) -Force
    $script:hdSelected=$record
    $info=$window.FindName('MeshInfo')
    if ($info) { $info.Text="Vertices: $($message.vertices)   Triangles: $($message.triangles)`nUV sets: $($message.uvSets)   Texture: $($message.textureSize -join ' x ')" }
    $window.FindName('HDShared').IsChecked=[bool]$record.HDShared
    Update-TexturePreview
    if ($targetFlyout) { $targetFlyout.Visibility='Visible' }
    Set-UiText $footer $record.Hint
}
function Initialize-HighDetailViewer {
    [IO.File]::AppendAllText((Join-Path $PSScriptRoot 'viewer-startup.log'), ('Initialize appRoot='+$appRoot+' dataRoot='+$dataRoot+[Environment]::NewLine))
    $env:PATH=$appRoot+[IO.Path]::PathSeparator+$env:PATH
    $script:hdAssetRoot=Join-Path $appRoot 'user-data\ship-preview'
    if (-not (Test-Path -LiteralPath (Join-Path $script:hdAssetRoot 'preview-manifest.json')) -or -not (Test-Path -LiteralPath (Join-Path $script:hdAssetRoot 'Jackdaw-default-textures.glb'))) {
        if ($script:nativeViewport) {$script:nativeViewport.Visibility='Collapsed'}
        Set-UiText $footer 'Current ship preview is missing. Restore the preview deployment; the older model is not shown.'
        return
    }
    if ($script:nativeViewport) {$script:nativeViewport.Visibility='Collapsed'}
    Set-UiText $footer 'Loading the current assembled Jackdaw...'
    $script:hdBrowser=$window.FindName('HighDetailViewport')
    if (-not $script:hdBrowser) {throw 'The integrated preview control is missing from the app layout.'}
    $script:hdBrowser.DefaultBackgroundColor=[System.Drawing.Color]::Transparent
    $script:hdBrowser.Visibility='Visible'
    $script:hdBrowser.CreationProperties=[Microsoft.Web.WebView2.Wpf.CoreWebView2CreationProperties]::new()
    $script:hdBrowser.CreationProperties.UserDataFolder=Join-Path $dataRoot 'high-detail-browser'
    # HighDetailViewport is declared in the app layout; it participates in WPF clipping and layering.
    $script:hdBrowser.Add_CoreWebView2InitializationCompleted({param($sender,$eventArgs)
        [IO.File]::AppendAllText((Join-Path $PSScriptRoot 'viewer-startup.log'),('WebView completed: '+$eventArgs.IsSuccess+' '+$eventArgs.InitializationException+[Environment]::NewLine))
        if (-not $eventArgs.IsSuccess) { Set-UiText $footer 'High-detail renderer could not start. The older ship preview is hidden.'; return }
        $core=$sender.CoreWebView2
        $core.SetVirtualHostNameToFolderMapping('jackdaw-viewer.local',(Join-Path $appRoot 'high-detail-viewer'),[Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
        $core.SetVirtualHostNameToFolderMapping('jackdaw-assets.local',$script:hdAssetRoot,[Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
        $core.Add_WebMessageReceived({param($sender,$eventArgs)
            if (-not $eventArgs.Source.StartsWith('https://jackdaw-viewer.local/')) { return }
            try {
                $m=$eventArgs.WebMessageAsJson | ConvertFrom-Json
                switch ($m.type) {
                    'ready' { $script:hdReady=$true;Set-HighDetailVisible ($script:modelPath.EndsWith('jackdaw-model-full.j3d'));Send-HighDetailMessage @{type='textures';enabled=$script:texturesEnabled};Set-UiText $modelStatus 'Assembled Jackdaw';Set-UiText $footer "Current assembled ship loaded. Select a major area to customize it.";$m | Add-Member NoteProperty controlType ($script:hdBrowser.GetType().Name);$m | Add-Member NoteProperty viewportSize @($script:hdBrowser.ActualWidth,$script:hdBrowser.ActualHeight);$m | Add-Member NoteProperty parent ($script:hdBrowser.Parent.Name);$m | Add-Member NoteProperty backgroundAlpha ($script:hdBrowser.DefaultBackgroundColor.A);[IO.File]::WriteAllText((Join-Path $dataRoot 'preview-loaded.json'),($m | ConvertTo-Json)) }
                    'surface-selected' { Select-HighDetailSurface $m }
                    'selection-cleared' { $script:hdSelected=$null;$window.FindName('MeshInfo').Text='Click a major area to inspect its mesh.';Update-TexturePreview }
                    'textures' { $script:texturesEnabled=[bool]$m.enabled;Update-TextureToggleButton }
                    'applied' { Set-UiText $footer 'Design applied. Surface detail retained.' }
                    'finish-color' { if ($script:hdSelected) {$script:hdSelected.HDTint=$m.hex};Set-UiText $footer 'Color updated. Surface detail retained.' }
                    'edit-error' { Set-UiText $footer ('Design could not be applied: '+$m.message) }
                    'export-finish' {
                        if ($m.data -notmatch '^data:image/png;base64,') {throw 'Invalid finish image'}
                        $dialog=New-Object Microsoft.Win32.SaveFileDialog;$dialog.Filter='PNG image (*.png)|*.png';$dialog.FileName=$m.filename
                        if ($dialog.ShowDialog($window)) {[IO.File]::WriteAllBytes($dialog.FileName,[Convert]::FromBase64String($m.data.Substring(22)));Set-UiText $footer 'Finish PNG saved.'}
                    }
                    'restored' { if ($script:hdSelected) { $script:hdSelected.Texture=$null;if ([object]::ReferenceEquals($script:generatedPreviewRecord,$script:hdSelected)) {$script:generatedPreviewPath=$null;$script:generatedPreviewRecord=$null} };Update-TexturePreview;Set-UiText $footer 'Default finish restored.' }
                    'error' { $script:hdActive=$false;if ($script:hdBrowser) {$script:hdBrowser.Visibility='Visible'};if ($script:nativeViewport) {$script:nativeViewport.Visibility='Collapsed'};Set-UiText $footer ('High-detail preview: '+$m.message) }
                }
            } catch { Set-UiText $footer ('Preview message: '+$_.Exception.Message) }
        })
        $viewerRevision=(Get-Item -LiteralPath (Join-Path $appRoot 'high-detail-viewer/viewer.js')).LastWriteTimeUtc.Ticks
        $core.Navigate('https://jackdaw-viewer.local/index.html?embedded=1&assets=https://jackdaw-assets.local/&v='+$viewerRevision)
    })
    $script:hdInitialization=$script:hdBrowser.EnsureCoreWebView2Async($null)
    [IO.File]::AppendAllText((Join-Path $PSScriptRoot 'viewer-startup.log'),('WebView initialization requested: '+$script:hdInitialization.Status+[Environment]::NewLine))
}
if ($textureToggle) { $textureToggle.Add_Click({ Send-HighDetailMessage @{type='textures';enabled=$script:texturesEnabled} }) }
$settingsButton=$window.FindName('ViewerSettings')
if ($settingsButton) { $settingsButton.Add_Click({Send-HighDetailMessage @{type='settings'}}) }
$sharedButton=$window.FindName('HDShared')
if ($sharedButton) { $sharedButton.Add_Click({ if ($script:hdSelected) {$script:hdSelected.HDShared=[bool]$sharedButton.IsChecked;Send-HighDetailMessage @{type='scope';shared=[bool]$sharedButton.IsChecked}} }) }
$restoreButton=$window.FindName('HDRestore')
if ($restoreButton) { $restoreButton.Add_Click({Send-HighDetailMessage @{type='restore'}}) }
if ($zones) { $zones.Add_SelectionChanged({ $script:hdSelected=$null;Send-HighDetailMessage @{type='clear-selection'} }) }
$window.Add_ContentRendered({try {Initialize-HighDetailViewer} catch {[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'viewer-startup.log'),($_ | Out-String));Set-UiText $footer ('Viewer startup failed: '+$_.Exception.Message)}})
$window.Add_Closed({if ($script:hdBrowser) {$script:hdBrowser.Dispose()}})

$colorButton=$window.FindName('HDFinishColor')
if ($colorButton) {$colorButton.Add_Click({
    if (-not $script:hdSelected) {Set-UiText $footer 'Select a ship part first.';return}
    Add-Type -AssemblyName System.Windows.Forms
    $dialog=New-Object System.Windows.Forms.ColorDialog
    $dialog.FullOpen=$true
    if ($script:hdSelected.HDTint -match '^#[0-9a-fA-F]{6}$') {$dialog.Color=[System.Drawing.ColorTranslator]::FromHtml($script:hdSelected.HDTint)}
    try {if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $hex='#{0:X2}{1:X2}{2:X2}' -f $dialog.Color.R,$dialog.Color.G,$dialog.Color.B
        Send-HighDetailMessage @{type='tint';hex=$hex}
    }} finally {$dialog.Dispose()}
})}
$exportFinishButton=$window.FindName('HDExportFinish')
if ($exportFinishButton) {$exportFinishButton.Add_Click({Send-HighDetailMessage @{type='export-finish'}})}

$integratedReset=$window.FindName('ResetView')
if ($integratedReset) {$integratedReset.Add_Click({if ($script:hdActive) {Send-HighDetailMessage @{type='fit'}}})}
