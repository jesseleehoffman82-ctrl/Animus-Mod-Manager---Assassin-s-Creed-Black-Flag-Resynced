# Local design documents store stable part/material identities, never zone indices.
$script:workflowLoading=$false
$script:workflowDocument=$null
function Get-DesignPartKey($meta) {
    $value=$meta.part+'|'+$meta.material_id
    if ($meta.material_id -eq '2296875182504') {$value='all-sails|'+$meta.material_id}
    $hash=[Security.Cryptography.SHA256]::Create()
    try {return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($value)))).Replace('-','').Substring(0,24).ToLowerInvariant()} finally {$hash.Dispose()}
}
function Get-DesignLocalPath([string]$folder,[string]$relative) {
    if (-not $relative -or [IO.Path]::IsPathRooted($relative)) {throw 'Invalid design asset path.'}
    $root=[IO.Path]::GetFullPath($folder).TrimEnd('\')+'\'
    $path=[IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {throw 'Design asset is outside its folder.'}
    return $path
}
function Set-WorkflowStatus([string]$message) {
    $name=Split-Path $script:currentProject -Leaf
    $window.FindName('WorkflowStatus').Text="$name  /  $message"
}
function Save-NativeDesign {
    if ($script:workflowLoading) {return}
    if (-not $script:modelPath.EndsWith('jackdaw-model-full.j3d')) {Set-ViewMode 'ship'}
    $entries=@{}; $folder=$script:currentProject
    foreach ($sub in @('inputs','finishes','editable','previews')) {[void][IO.Directory]::CreateDirectory((Join-Path $folder $sub))}
    foreach ($record in $zoneRecords) {
        $meta=Get-NativeFinishMeta $record.Component $record.Zone
        $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)]
        if (-not $meta -or -not $state -or -not $state.Output) {continue}
        $id=Get-DesignPartKey $meta
        if ($entries.ContainsKey($id)) {continue}
        $input=$null
        if ($state.Design) {
            $input="inputs/$id.png"; $dest=Get-DesignLocalPath $folder $input
            if ([IO.Path]::GetFullPath($state.Design) -ne $dest) {Copy-Item -LiteralPath $state.Design -Destination $dest -Force}
        }
        $output="finishes/$id.png"; $dest=Get-DesignLocalPath $folder $output
        if ([IO.Path]::GetFullPath($state.Output) -ne $dest) {Copy-Item -LiteralPath $state.Output -Destination $dest -Force}
        $entries[$id]=[ordered]@{id=$id;part=$meta.part;material_id=$meta.material_id;area=$meta.area;source_preview=$meta.diffuse;input=$input;output=$output;tint=$state.Tint;flip_v=[bool]$state.FlipV}
    }
    $doc=[ordered]@{schema=1;name=(Split-Path $folder -Leaf);model_sha256=$script:nativeFinishData.source_sha256;updated_utc=[DateTime]::UtcNow.ToString('o');entries=@($entries.Values | Sort-Object id)}
    $path=Join-Path $folder 'design.jackdaw.json';$temp=$path+'.tmp'
    [IO.File]::WriteAllText($temp,($doc|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temp -Destination $path -Force
    $script:workflowDocument=$doc
    if (Get-Command Sync-EmbeddedFinishes -ErrorAction SilentlyContinue) {Sync-EmbeddedFinishes}
    Set-WorkflowStatus ("Saved · {0} edited finishes" -f $entries.Count)
}
function Save-NativeDesignAfterEdit {
    if ($script:workflowLoading) {return}
    try {Save-NativeDesign} catch {Set-WorkflowStatus 'Save failed';Set-UiText $footer ("Edit is still in memory. Save failed: "+$_.Exception.Message)}
}
function Read-NativeDesign([string]$path) {
    $doc=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($doc.schema -ne 1) {throw 'This design format is not supported.'}
    if ($doc.model_sha256 -ne $script:nativeFinishData.source_sha256) {throw 'This design uses a different model revision. Its edits have not been applied.'}
    $folder=Split-Path ([IO.Path]::GetFullPath($path)) -Parent
    $known=@{};foreach($meta in $script:nativeFinishZones.Values) {$known[(Get-DesignPartKey $meta)]=$true}
    foreach ($entry in $doc.entries) {
        if (-not $known.ContainsKey($entry.id) -or (Get-DesignPartKey $entry) -ne $entry.id) {throw 'A design finish does not match this ship.'}
        if ($entry.tint -notmatch '^#[0-9a-fA-F]{6}$') {throw 'Invalid finish color.'}
        foreach ($relative in @($entry.output,$entry.input)) {
            if ($relative -and -not (Test-Path -LiteralPath (Get-DesignLocalPath $folder $relative) -PathType Leaf)) {throw "Missing design asset: $relative"}
        }
    }
    return @{Document=$doc;Folder=$folder}
}
function Restore-NativeDesign {
    if ($script:workflowLoading -or -not $script:modelPath.EndsWith('jackdaw-model-full.j3d')) {return}
    $path=Join-Path $script:currentProject 'design.jackdaw.json'
    if (-not (Test-Path -LiteralPath $path)) {Set-WorkflowStatus 'Ready';return}
    $loaded=Read-NativeDesign $path
    $script:workflowLoading=$true
    try {
        $script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{};$materials=@{}
        foreach ($entry in $loaded.Document.entries) {
            $output=Get-DesignLocalPath $loaded.Folder $entry.output
            $input=if ($entry.input) {Get-DesignLocalPath $loaded.Folder $entry.input} else {$null}
            $materials[$entry.id]=New-TextureMaterial $output -FlipV ([bool]$entry.flip_v)
            foreach ($record in $zoneRecords) {
                $meta=Get-NativeFinishMeta $record.Component $record.Zone
                if (-not $meta -or (Get-DesignPartKey $meta) -ne $entry.id) {continue}
                $script:nativeFinishStates[(Get-PreviewMaterialKey $record)]=@{Tint=$entry.tint;Design=$input;Output=$output;FlipV=[bool]$entry.flip_v}
                $record.Texture=$output
                Set-AppliedPreviewMaterial $record (Add-NativeMetalShading $materials[$entry.id] $record.Component $record.Zone)
                if ($record.Component -eq 6) {$script:currentSailViewMode='Custom preview'}
            }
        }
        $script:workflowDocument=$loaded.Document
        Apply-SailViewMode
        if (Get-Command Sync-EmbeddedFinishes -ErrorAction SilentlyContinue) {Sync-EmbeddedFinishes}
        Set-WorkflowStatus ("Saved · {0} edited finishes" -f @($loaded.Document.entries).Count)
    } finally {$script:workflowLoading=$false}
}
function Open-NativeDesign([string]$path) {
    # Validate every reference before replacing the current session.
    $loaded=Read-NativeDesign $path
    Save-NativeDesign
    $script:currentProject=$loaded.Folder
    $script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{}
    Set-ViewMode 'ship';Restore-NativeDesign;Clear-NativePartSelection
}
function Get-EditableDesignPng($record) {
    $meta=Get-NativeFinishMeta $record.Component $record.Zone
    if (-not $meta) {throw 'Select a surface on the assembled ship first.'}
    $id=Get-DesignPartKey $meta
    $folder=Join-Path $script:currentProject 'editable';[void][IO.Directory]::CreateDirectory($folder)
    $path=Join-Path $folder ($id+'.png')
    if (-not (Test-Path -LiteralPath $path)) {
        $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)]
        $source=if ($state -and $state.Output) {$state.Output} else {Get-NativeFinishPath $record.Component $record.Zone}
        Copy-Item -LiteralPath $source -Destination $path
    }
    return $path
}
function Import-DesignPng($record,[string]$path) {
    $source=Get-NativeFinishPath $record.Component $record.Zone
    if (-not $source) {throw 'Select a surface on the assembled ship first.'}
    $a=[Drawing.Image]::FromFile($source)
    try {
        $b=[Drawing.Image]::FromFile($path)
        try {if ($a.Width -ne $b.Width -or $a.Height -ne $b.Height) {throw "Use the original PNG dimensions: $($a.Width) x $($a.Height)."}} finally {$b.Dispose()}
    } finally {$a.Dispose()}
    # Copy into the project before applying. External edits are an already
    # flattened finish, so do not multiply the previous color a second time.
    $dest=Get-EditableDesignPng $record
    if ([IO.Path]::GetFullPath($path) -ne [IO.Path]::GetFullPath($dest)) {Copy-Item -LiteralPath $path -Destination $dest -Force}
    foreach ($target in @(Get-NativeFinishTargets $record)) {$state=$script:nativeFinishStates[(Get-PreviewMaterialKey $target)];if ($state) {$state.Tint='#ffffff'}}
    Set-NativeFinish $record $dest $null 'design'
    Set-UiText $footer 'PNG applied and design saved.'
}
function Export-NativeDesignPackage {
    Save-NativeDesign
    $folder=Join-Path $script:currentProject ('exports/design-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
    [void][IO.Directory]::CreateDirectory($folder)
    Copy-Item -LiteralPath (Join-Path $script:currentProject 'design.jackdaw.json') -Destination $folder
    foreach ($entry in $script:workflowDocument.entries) {
        foreach ($relative in @($entry.input,$entry.output)) {
            if (-not $relative) {continue}
            $dest=Get-DesignLocalPath $folder $relative;[void][IO.Directory]::CreateDirectory((Split-Path $dest -Parent))
            Copy-Item -LiteralPath (Get-DesignLocalPath $script:currentProject $relative) -Destination $dest -Force
        }
    }
    [IO.File]::WriteAllText((Join-Path $folder 'README.txt'),'Open design.jackdaw.json in Jackdaw Studio using the matching model revision. These are Studio appearance edits, not an installable game patch. Game texture and cosmetic-slot mappings still require verification.')
    Set-WorkflowStatus 'Design exported'
    return $folder
}

function Invoke-WorkflowAction([scriptblock]$action) {
    try {& $action} catch {Set-UiText $footer $_.Exception.Message;[Windows.MessageBox]::Show($_.Exception.Message,'Design workflow')|Out-Null}
}
$window.FindName('DesignSave').Add_Click({Invoke-WorkflowAction {Save-NativeDesign}})
$window.FindName('DesignOpen').Add_Click({Invoke-WorkflowAction {
    $dialog=[Microsoft.Win32.OpenFileDialog]::new();$dialog.Filter='Jackdaw design (*.jackdaw.json)|*.jackdaw.json';$dialog.InitialDirectory=$projectsRoot
    if ($dialog.ShowDialog($window)) {Open-NativeDesign $dialog.FileName}
}})
$window.FindName('DesignNew').Add_Click({Invoke-WorkflowAction {
    $dialog=[Microsoft.Win32.SaveFileDialog]::new();$dialog.Title='Name your new design';$dialog.Filter='Jackdaw design (*.jackdaw.json)|*.jackdaw.json';$dialog.FileName='My Jackdaw.jackdaw.json';$dialog.InitialDirectory=$projectsRoot
    if ($dialog.ShowDialog($window)) {
        $name=[IO.Path]::GetFileName($dialog.FileName) -replace '\.jackdaw\.json$',''
        $folder=Join-Path (Split-Path $dialog.FileName -Parent) $name
        if (Test-Path -LiteralPath $folder) {throw 'A folder with that name already exists. Choose another design name.'}
        Save-NativeDesign;$script:currentProject=$folder;$script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{}
        Set-ViewMode 'ship';Clear-NativePartSelection;Save-NativeDesign
    }
}})
$window.FindName('EditExternal').Add_Click({Invoke-WorkflowAction {
    $record=Get-SelectedZone;$path=Get-EditableDesignPng $record
    $settings=Join-Path $dataRoot 'texture-editor.txt'
    $editor=if (Test-Path -LiteralPath $settings) {[IO.File]::ReadAllText($settings).Trim()} else {$null}
    if (-not $editor -or -not (Test-Path -LiteralPath $editor)) {
        $dialog=[Microsoft.Win32.OpenFileDialog]::new();$dialog.Title='Choose Photoshop or your PNG editor';$dialog.Filter='Editor application (*.exe)|*.exe'
        if (-not $dialog.ShowDialog($window)) {return}
        $editor=$dialog.FileName;[IO.File]::WriteAllText($settings,$editor)
    }
    Start-Process -FilePath $editor -ArgumentList ('"'+$path+'"')
    Set-UiText $footer 'Edit the project PNG, save it in your editor, then choose Reload PNG.'
}})
$window.FindName('ReloadExternal').Add_Click({Invoke-WorkflowAction {$record=Get-SelectedZone;Import-DesignPng $record (Get-EditableDesignPng $record)}})
$window.FindName('DesignFolder').Add_Click({Invoke-WorkflowAction {[void][IO.Directory]::CreateDirectory($script:currentProject);Start-Process explorer.exe -ArgumentList ('"'+$script:currentProject+'"')}})

# Put editing controls beside the selected part, not inside the library flyout.
$hostPanel=$window.FindName('FinishControlsHost')
foreach ($name in @('HDFinishColor','HDShared','HDRestore','HDExportFinish')) {
    $control=$window.FindName($name);$control.Parent.Children.Remove($control);[void]$hostPanel.Children.Add($control)
}
$mesh=$window.FindName('MeshInfo');$mesh.Parent.Content=$null;[void]$hostPanel.Children.Add($mesh)
$sourcePanel=$texturePreview.Parent.Parent;$sourcePanel.Parent.Children.Remove($sourcePanel);$sourcePanel.Height=130;$sourcePanel.Margin='0,8,0,8';[void]$hostPanel.Children.Add($sourcePanel)
$window.FindName('HDExportFinish').Content='Export finish PNG'
$window.FindName('HDFinishColor').Content='Change color'
$window.FindName('ChoosePng').Content='Export source PNG'
$window.FindName('ApplyComponent').Content='Apply preview'
$window.FindName('ApplyAllSails').Visibility='Collapsed'
[Windows.Controls.Grid]::SetColumnSpan($window.FindName('ApplyComponent'),3)
$window.FindName('ExportGenerated').Content='Export preview'
$window.FindName('InjectDesign').IsEnabled=$false
$window.FindName('InjectDesign').ToolTip='Experimental: game-slot mappings are not yet verified for saved Studio designs.'
$window.FindName('TargetFlyout').Child.RowDefinitions[3].Height=[Windows.GridLength]::new(0)
$window.FindName('TargetFlyout').Child.RowDefinitions[4].Height=[Windows.GridLength]::new(0)
Set-WorkflowStatus 'Ready'

function Test-NativeDesignWorkflow {
    $oldFolder=$script:currentProject
    $folder=Join-Path $dataRoot ('workflow-test-'+[Guid]::NewGuid().ToString('N'))
    try {
        $script:currentProject=$folder
        $script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{}
        $record=$zoneRecords | Where-Object { $meta=Get-NativeFinishMeta $_.Component $_.Zone; $_.Component -eq 1 -and $meta.material_id -eq '2254710118072'} | Select-Object -First 1
        $original=Get-NativeFinishPath $record.Component $record.Zone
        $originalHash=(Get-FileHash -LiteralPath $original).Hash
        Set-NativeFinish $record $null '#b4d3e8' 'color'
        $path=Join-Path $folder 'design.jackdaw.json'
        $saved=Read-NativeDesign $path
        if (@($saved.Document.entries).Count -ne 1) {throw 'Expected one saved brass finish'}
        $outputHash=(Get-FileHash -LiteralPath (Get-DesignLocalPath $folder $saved.Document.entries[0].output)).Hash
        $script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{}
        Restore-NativeDesign
        $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)]
        if ($state.Tint -ne '#b4d3e8' -or (Get-FileHash -LiteralPath $state.Output).Hash -ne $outputHash) {throw 'Saved finish did not restore'}
        $edit=Get-EditableDesignPng $record
        Import-DesignPng $record $edit
        $firstHash=(Get-FileHash -LiteralPath $script:nativeFinishStates[(Get-PreviewMaterialKey $record)].Output).Hash
        Import-DesignPng $record $edit
        if ((Get-FileHash -LiteralPath $script:nativeFinishStates[(Get-PreviewMaterialKey $record)].Output).Hash -ne $firstHash) {throw 'External reload compounded the tint'}
        if ((Get-FileHash -LiteralPath $original).Hash -ne $originalHash) {throw 'Source PNG changed'}
        $sail=Get-NativeSailRecord ($zoneRecords | Where-Object Component -eq 6 | Select-Object -First 1)
        Set-NativeFinish $sail $null '#dddddd' 'color'
        $saved=Read-NativeDesign $path
        if (@($saved.Document.entries).Count -ne 2) {throw 'Shared sails should save as one finish'}
        Restore-NativeDesign
        $restored=@($zoneRecords | Where-Object {$_.Component -eq 6 -and $script:nativeFinishStates.ContainsKey((Get-PreviewMaterialKey $_))})
        if ($restored.Count -ne 26) {throw 'Saved sail group did not restore all 26 cloth surfaces'}
        $export=Export-NativeDesignPackage
        $package=Read-NativeDesign (Join-Path $export 'design.jackdaw.json')
        if (@($package.Document.entries).Count -ne 2) {throw 'Export omitted finishes'}
        $script:embeddedSelectionKeys=@("$($record.Component)/$($record.Zone)","$($sail.Component)/$($sail.Zone)")
        $multi=@(Get-NativeFinishTargets $record)
        if (@($multi | Where-Object Component -eq 6).Count -ne 26 -or -not ($multi -contains $record)) {throw 'Multi-selection omitted selected material or sail group'}
        $script:embeddedSelectionKeys=@()
        $window.FindName('RevertDesign').RaiseEvent([Windows.RoutedEventArgs]::new([Windows.Controls.Button]::ClickEvent))
        if ($script:nativeFinishStates.Count -or $script:appliedPreviewMaterials.Count) {throw 'Revert left applied finishes in memory'}
        $reverted=Read-NativeDesign $path
        if (@($reverted.Document.entries).Count) {throw 'Revert did not persist the empty design'}
        Restore-NativeDesign
        if ($script:nativeFinishStates.Count) {throw 'Reverted finishes returned after reopening'}
        'PASS: multi-selection includes selected surfaces; Revert clears and persists finishes across reopen'
        $rejected=$false;try {Get-DesignLocalPath $folder '../outside.png'|Out-Null} catch {$rejected=$true}
        if (-not $rejected) {throw 'Unsafe relative asset path accepted'}
        'PASS: design save/reopen, shared sail restore, external PNG reload without tint stacking, portable export, source preservation and path validation'
    } finally {
        $script:currentProject=$oldFolder;$script:nativeFinishStates=@{};$script:appliedPreviewMaterials=@{};$script:workflowDocument=$null
        foreach ($record in $zoneRecords) {$record.Texture=$null}
        Clear-NativePartSelection;Apply-SailViewMode;Set-WorkflowStatus 'Ready'
    }
}
