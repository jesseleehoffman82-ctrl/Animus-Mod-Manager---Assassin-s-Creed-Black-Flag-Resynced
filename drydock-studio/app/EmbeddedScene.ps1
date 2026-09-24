# The renderer lives in the existing viewport; native records remain the single
# source of truth for editing, design persistence, and PNG targets.
$script:embeddedReady=$false
function Send-EmbeddedMessage($message) {
    if ($script:embeddedReady -and $viewportWebBrowser.CoreWebView2) {$viewportWebBrowser.CoreWebView2.PostWebMessageAsJson(($message|ConvertTo-Json -Depth 8 -Compress))}
}
function Sync-EmbeddedFinishes {
    if (-not $script:embeddedReady) {return}
    $finishes=@()
    foreach ($record in $zoneRecords) {
        $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)]
        if (-not $state -or -not $state.Output) {continue}
        $hash=(Get-FileHash -LiteralPath $state.Output -Algorithm SHA256).Hash.ToLowerInvariant()
        $name='design-'+$hash+'.png';$dest=Join-Path $script:nativeFinishRoot $name
        if (-not(Test-Path -LiteralPath $dest)) {Copy-Item -LiteralPath $state.Output -Destination $dest}
        $finishes+=@{key="$($record.Component)/$($record.Zone)";url=('https://jackdaw-assets.local/'+$name);flipV=[bool]$state.FlipV}
    }
    Send-EmbeddedMessage @{type='state';finishes=@($finishes)}
}
function Initialize-EmbeddedScene {
    [IO.File]::AppendAllText((Join-Path $dataRoot 'embedded-init.log'),"Initialize`n")
    $script:embeddedBrowser=$viewportWebBrowser
    $viewportWebBrowser.DefaultBackgroundColor=[Drawing.Color]::FromArgb(255,9,23,35)
    $properties=[Microsoft.Web.WebView2.Wpf.CoreWebView2CreationProperties]::new();$properties.UserDataFolder=Join-Path $dataRoot 'embedded-depth-browser';$viewportWebBrowser.CreationProperties=$properties
    $viewportWebBrowser.Visibility='Hidden';$script:nativeViewport.Visibility='Collapsed';$viewportInputLayer.Visibility='Collapsed'
    foreach($name in @('LegacyComponentControls','LegacyViewportHelp','ResetView')) {$window.FindName($name).Visibility='Collapsed'}
    $viewportWebBrowser.Add_CoreWebView2InitializationCompleted({param($sender,$eventArgs)
        [IO.File]::AppendAllText((Join-Path $dataRoot 'embedded-init.log'),("Core ready: "+$eventArgs.IsSuccess+' '+$eventArgs.InitializationException+"`n"))
        if(-not $eventArgs.IsSuccess){Set-UiText $footer ('Embedded renderer could not start: '+$eventArgs.InitializationException);return}
        $core=$sender.CoreWebView2
        $core.SetVirtualHostNameToFolderMapping('jackdaw-viewer.local',(Join-Path $appRoot 'high-detail-viewer'),[Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
        $core.SetVirtualHostNameToFolderMapping('jackdaw-assets.local',$script:nativeFinishRoot,[Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
        $core.Settings.AreDefaultContextMenusEnabled=$false
        $core.Add_DOMContentLoaded({
            $viewportWebBrowser.Visibility='Visible'
            $window.FindName('StartupModelLoader').Visibility='Collapsed'
        })
        [void]$core.AddScriptToExecuteOnDocumentCreatedAsync("window.addEventListener('error',e=>window.chrome.webview.postMessage({type:'error',message:e.message}));window.addEventListener('unhandledrejection',e=>window.chrome.webview.postMessage({type:'error',message:String(e.reason)}));")
        $core.Add_WebMessageReceived({param($sender,$eventArgs)
            if (-not $eventArgs.Source.StartsWith('https://jackdaw-viewer.local/')) {return}
            try {
                $message=$eventArgs.WebMessageAsJson|ConvertFrom-Json
                switch($message.type) {
                    'ready' {
                        if ($message.source_sha256 -ne $script:nativeFinishData.source_sha256) {throw 'The renderer loaded a different model revision.'}
                        $script:embeddedReady=$true;$script:hdActive=$true;$script:hdSelected=$null
                        $viewportWebBrowser.Visibility='Visible';$script:nativeViewport.Visibility='Collapsed';$viewportInputLayer.Visibility='Collapsed'
                        Sync-EmbeddedFinishes
                        [IO.File]::WriteAllText((Join-Path $dataRoot 'embedded-preview-loaded.json'),($message|ConvertTo-Json))
                        Set-UiText $footer 'Embedded preview ready · Shadows and ambient occlusion enabled.'
                        if ($env:JACKDAW_EMBEDDED_REVIEW) {Start-EmbeddedReviewCapture}
                    }
                    'surface-selected' {
                        $script:embeddedSelectionKeys=@($message.keys)
                        $record=$zoneRecords | Where-Object {"$($_.Component)/$($_.Zone)" -eq $message.key} | Select-Object -First 1
                        if ($record) {$script:hdSelected=Get-NativeSailRecord $record;if(-not $script:hdSelected){$script:hdSelected=$record};Show-NativePartEdges $script:hdSelected;Update-TexturePreview}
                    }
                    'selection-cleared' {Clear-NativePartSelection}
                    'paint-applied' {
                        $record=$zoneRecords | Where-Object {"$($_.Component)/$($_.Zone)" -eq $message.key} | Select-Object -First 1
                        if (-not $record -or -not $message.png.StartsWith('data:image/png;base64,')) {throw 'Invalid paint result.'}
                        $paintFolder=Join-Path $script:currentProject 'editable'
                        [void][IO.Directory]::CreateDirectory($paintFolder)
                        $paintPath=Join-Path $paintFolder ('paint-'+[guid]::NewGuid().ToString('N')+'.png')
                        [IO.File]::WriteAllBytes($paintPath,[Convert]::FromBase64String($message.png.Substring(22)))
                        $previousKeys=$script:embeddedSelectionKeys;$script:embeddedSelectionKeys=@()
                        $previousShared=$window.FindName('HDShared').IsChecked;$window.FindName('HDShared').IsChecked=$false
                        try {
                            foreach ($target in (Get-NativeFinishTargets $record)) {
                                $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $target)]
                                if($state){$state.Tint='#ffffff'}
                            }
                            Apply-NativeFinishPng $record $paintPath | Out-Null
                            Save-NativeDesignAfterEdit
                        } finally {$script:embeddedSelectionKeys=$previousKeys;$window.FindName('HDShared').IsChecked=$previousShared}
                    }
                    'textures' {$script:texturesEnabled=[bool]$message.enabled;Update-TextureToggleButton}
                    'error' {Set-UiText $footer ('Renderer: '+$message.message);[IO.File]::WriteAllText((Join-Path $dataRoot 'embedded-preview-error.txt'),$message.message)}
                    'state-applied' {Set-WorkflowStatus 'Saved · preview updated'}
                }
            } catch {Set-UiText $footer $_.Exception.Message}
        })
        $core.Navigate('https://jackdaw-viewer.local/index.html?embedded=1&assets=https://jackdaw-assets.local/&v=workflow-depth-1')
    })
    $script:embeddedInitialization=$viewportWebBrowser.EnsureCoreWebView2Async($null)
}
function Start-EmbeddedReviewCapture {
    $script:reviewTick=0;$script:reviewTimer=[Windows.Threading.DispatcherTimer]::new();$script:reviewTimer.Interval=[TimeSpan]::FromSeconds(2)
    $script:reviewTimer.Add_Tick({
        $script:reviewTick++
        if($script:reviewTick -eq 1 -and $env:JACKDAW_REVIEW_DRAWER){$window.FindName('GenerationDrawerToggle').RaiseEvent([Windows.RoutedEventArgs]::new([Windows.Controls.Button]::ClickEvent))}
        if($script:reviewTick -eq 3 -and $env:JACKDAW_REVIEW_DRAWER){
            $shell=$window.FindName('GenerationDrawerShell');$prompt=$window.FindName('AiPromptInput');$preview=$window.FindName('GeneratedPreviewPanel')
            $before=$prompt.Text;$prompt.Text='Drawer retention check'
            $window.FindName('GenerationDrawerToggle').RaiseEvent([Windows.RoutedEventArgs]::new([Windows.Controls.Button]::ClickEvent))
            $window.FindName('GenerationDrawerToggle').RaiseEvent([Windows.RoutedEventArgs]::new([Windows.Controls.Button]::ClickEvent))
            $report=@{previewWidth=$preview.ActualWidth;promptWidth=$prompt.ActualWidth;open=$script:generationDrawerOpen;contentsRetained=($prompt.Text -eq 'Drawer retention check');previewInsideDrawer=$shell.IsAncestorOf($preview);promptInsideDrawer=$shell.IsAncestorOf($prompt)};$prompt.Text=$before
            [IO.File]::WriteAllText($env:JACKDAW_EMBEDDED_REVIEW+'-drawer.json',($report|ConvertTo-Json))
        }
        if($script:reviewTick -eq 2 -and $env:JACKDAW_REVIEW_SAIL_MOTION){$script:sailTestTask=$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync("(()=>{try{return {test:window.jackdawViewer.testSails(),details:window.jackdawViewer.debug()}}catch(e){return 'FAIL: '+e.message}})()")}
        if($script:reviewTick -eq 2 -and $env:JACKDAW_REVIEW_LANTERNS) {
            $script:lanternTestTask=$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync("(()=>{const k='jackdaw-depth-settings',saved=localStorage.getItem(k),box=document.getElementById('lanterns');box.checked=false;box.dispatchEvent(new Event('change'));const off=window.jackdawViewer.debug().lanterns;box.checked=true;box.dispatchEvent(new Event('change'));const on=window.jackdawViewer.debug().lanterns;if(saved===null)localStorage.removeItem(k);else localStorage.setItem(k,saved);return {off,on,pass:off.enabled===0&&on.enabled===on.count&&on.count>0}})()")
        }
        if($script:reviewTick -eq 2 -and $env:JACKDAW_REVIEW_PAINT_TEST) {$script:paintTestTask=$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync("(()=>{try{return window.jackdawViewer.testPaint()}catch(e){return 'FAIL: '+e.message}})()")}
        if($script:reviewTick -eq 1 -and $env:JACKDAW_REVIEW_SAIL_PNG) {
            # Diagnostic preview only: no design state or project files are changed.
            $reviewName='review-sail-'+(Get-FileHash -LiteralPath $env:JACKDAW_REVIEW_SAIL_PNG).Hash.ToLowerInvariant()+'.png'
            Copy-Item -LiteralPath $env:JACKDAW_REVIEW_SAIL_PNG -Destination (Join-Path $script:nativeFinishRoot $reviewName) -Force
            $reviewFinishes=@($zoneRecords | Where-Object {(Get-NativeFinishMeta $_.Component $_.Zone).material_id -eq '2296875182504'} | ForEach-Object {@{key="$($_.Component)/$($_.Zone)";url=('https://jackdaw-assets.local/'+$reviewName);flipV=$true}})
            Send-EmbeddedMessage @{type='state';finishes=$reviewFinishes}
            Send-EmbeddedMessage @{type='fit'}
        }
        if($script:reviewTick -eq 1 -and $env:JACKDAW_EMBEDDED_REVIEW_FOCUS -eq 'cabin') {
            Send-EmbeddedMessage @{type='focus';mode='cabin'}
            # Review the textures without changing the user's persisted viewer preference.
            $null=$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync("(()=>{const k='jackdaw-depth-settings',v=localStorage.getItem(k);window.jackdawViewer.receive({type:'textures',enabled:true});if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)})()")
        }
        if($script:reviewTick -eq 3) {$script:reviewDebugTask=$viewportWebBrowser.CoreWebView2.ExecuteScriptAsync('JSON.stringify(window.jackdawViewer.debug())')}
        if($script:reviewTick -ge 4 -and $script:reviewDebugTask.IsCompleted) {
            if($script:sailTestTask -and $script:sailTestTask.IsCompleted){[IO.File]::WriteAllText($env:JACKDAW_EMBEDDED_REVIEW+'-sail-test.json',$script:sailTestTask.Result)}
            if($script:lanternTestTask -and $script:lanternTestTask.IsCompleted){[IO.File]::WriteAllText($env:JACKDAW_EMBEDDED_REVIEW+'-lantern-test.json',$script:lanternTestTask.Result)}
            if($script:paintTestTask -and $script:paintTestTask.IsCompleted){[IO.File]::WriteAllText($env:JACKDAW_EMBEDDED_REVIEW+'-paint-test.json',$script:paintTestTask.Result)}
            [IO.File]::WriteAllText($env:JACKDAW_EMBEDDED_REVIEW+'.json',$script:reviewDebugTask.Result)
            $script:reviewStream=[IO.File]::Create($env:JACKDAW_EMBEDDED_REVIEW+'.png')
            $script:reviewCaptureTask=$viewportWebBrowser.CoreWebView2.CapturePreviewAsync([Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat]::Png,$script:reviewStream)
            $script:reviewDebugTask=$null;$script:reviewTimer.Stop()
            $script:reviewCloseTimer=[Windows.Threading.DispatcherTimer]::new();$script:reviewCloseTimer.Interval=[TimeSpan]::FromSeconds(1)
            $script:reviewCloseTimer.Add_Tick({if($script:reviewCaptureTask.IsCompleted){$script:reviewStream.Dispose();$script:reviewCloseTimer.Stop();if($env:JACKDAW_EMBEDDED_REVIEW_EXIT -eq '1'){$window.Close()}}});$script:reviewCloseTimer.Start()
        }
    });$script:reviewTimer.Start()
}
$textureToggle.Add_Click({Send-EmbeddedMessage @{type='textures';enabled=$script:texturesEnabled}})
$window.Add_ContentRendered({if(-not $LoadTest){try{Initialize-EmbeddedScene}catch{[IO.File]::AppendAllText((Join-Path $dataRoot 'embedded-init.log'),($_|Out-String));Set-UiText $footer $_.Exception.Message}}})
$window.Add_Closed({if($viewportWebBrowser){$viewportWebBrowser.Dispose()}})
