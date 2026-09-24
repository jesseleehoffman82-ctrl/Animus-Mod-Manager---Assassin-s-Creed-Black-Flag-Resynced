# The original native viewport, with the current finish controls and part edges.
$script:hdActive=$false
$script:nativeFinishRoot=Join-Path $appRoot 'user-data\ship-preview'
$script:nativeFinishData=Get-Content -LiteralPath (Join-Path $script:nativeFinishRoot 'native-current-metadata.json') -Raw | ConvertFrom-Json
$script:nativeFinishZones=@{}
foreach ($p in $script:nativeFinishData.zones.PSObject.Properties) {$script:nativeFinishZones[$p.Name]=$p.Value}
$script:nativeOutlineBytes=[IO.File]::ReadAllBytes((Join-Path $script:nativeFinishRoot 'native-part-outlines.bin'))
$script:nativeOutlineCache=@{};$script:nativeFinishStates=@{};$script:nativeFinishMaterials=@{};$script:nativeFocusFade=$true

Add-Type -ReferencedAssemblies @('System.Drawing','PresentationCore','WindowsBase') -TypeDefinition @'
using System;
using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Media.Media3D;
public static class JackdawNativeFinish {
    public static Point3DCollection Points(byte[] bytes,int offset,int count) {
        var points=new Point3DCollection(count);
        for(int i=0;i<count;i++,offset+=12) points.Add(new Point3D(BitConverter.ToSingle(bytes,offset),BitConverter.ToSingle(bytes,offset+4),BitConverter.ToSingle(bytes,offset+8)));
        points.Freeze();return points;
    }
    static double Linear(double x) {return x<=0.04045?x/12.92:Math.Pow((x+0.055)/1.055,2.4);}
    static byte Multiply(byte source,byte tint) {
        double x=Linear(source/255.0)*Linear(tint/255.0);
        return (byte)Math.Round(255*(x<=0.0031308?12.92*x:1.055*Math.Pow(x,1/2.4)-0.055));
    }
    public static void Render(string original,string design,string hex,string output) { Render(original,design,hex,output,false); }
    public static void Render(string original,string design,string hex,string output,bool currentSailAtlas) {
        using(var source=new Bitmap(original))
        using(var bitmap=new Bitmap(source.Width,source.Height,PixelFormat.Format32bppArgb)) {
            using(var g=Graphics.FromImage(bitmap)) {
                if(currentSailAtlas) source.RotateFlip(RotateFlipType.RotateNoneFlipY);
                g.DrawImage(source,0,0,bitmap.Width,bitmap.Height);
                if(!String.IsNullOrEmpty(design)) using(var png=new Bitmap(design)) g.DrawImage(png,0,0,bitmap.Width,bitmap.Height);
            }
            var color=ColorTranslator.FromHtml(hex);
            byte[][] lut={new byte[256],new byte[256],new byte[256]};byte[] factors={color.B,color.G,color.R};
            for(int c=0;c<3;c++) for(int i=0;i<256;i++) lut[c][i]=Multiply((byte)i,factors[c]);
            var data=bitmap.LockBits(new Rectangle(0,0,bitmap.Width,bitmap.Height),ImageLockMode.ReadWrite,PixelFormat.Format32bppArgb);
            try {var row=new byte[bitmap.Width*4];for(int y=0;y<bitmap.Height;y++) {IntPtr ptr=IntPtr.Add(data.Scan0,y*data.Stride);Marshal.Copy(ptr,row,0,row.Length);for(int i=0;i<row.Length;i+=4)for(int c=0;c<3;c++)row[i+c]=lut[c][row[i+c]];Marshal.Copy(row,0,ptr,row.Length);}}
            finally {bitmap.UnlockBits(data);}
            bitmap.Save(output,ImageFormat.Png);
        }
    }
}
'@

function Get-NativeFinishMeta([int]$component,[int]$zone) {
    if (-not $script:modelPath.EndsWith('jackdaw-model-full.j3d')) {return $null}
    return $script:nativeFinishZones["$component/$zone"]
}
function Get-NativeFinishPath([int]$component,[int]$zone) {
    $meta=Get-NativeFinishMeta $component $zone
    if ($meta) {return Join-Path $script:nativeFinishRoot ($meta.diffuse+'.png')}
    return $null
}
function Get-NativeFinishMaterial([int]$component,[int]$zone) {
    $path=Get-NativeFinishPath $component $zone
    if (-not $path) {return $null}
    if (-not $script:nativeFinishMaterials.ContainsKey($path)) {$script:nativeFinishMaterials[$path]=New-TextureMaterial $path}
    $base=$script:nativeFinishMaterials[$path]
    if (Get-Command Add-NativeMetalShading -ErrorAction SilentlyContinue) {return (Add-NativeMetalShading $base $component $zone)}
    return $base
}
# The white sail atlas is shared by 26 cloth surfaces. Other component-6
# materials belong to fittings and must never receive the cloth PNG.
function Get-NativeSailRecord($record) {
    if (-not $record -or $record.Component -ne 6) {return $record}
    return ($zoneRecords | Where-Object {$_.Component -eq 6 -and (Get-NativeFinishMeta $_.Component $_.Zone).material_id -eq '2296875182504'} | Select-Object -First 1)
}
function Get-NativeSelectionGroup($record) {
    if (-not $record) {return $null}
    if ($record.Component -eq 6) {return 'shared-sail-atlas'}
    return (Get-NativeFinishMeta $record.Component $record.Zone).part
}
function Get-NativeSelectionZones($record) {
    if ($record.Component -eq 6) {
        return @($zoneRecords | Where-Object {$_.Component -eq 6 -and (Get-NativeFinishMeta $_.Component $_.Zone).material_id -eq '2296875182504'})
    }
    $group=Get-NativeSelectionGroup $record
    return @($zoneRecords | Where-Object {(Get-NativeSelectionGroup $_) -eq $group})
}
function Get-NativeFinishTargets($record) {
    if ($script:embeddedSelectionKeys -and $script:embeddedSelectionKeys.Count -gt 1) {
        $chosen=@($zoneRecords | Where-Object { $script:embeddedSelectionKeys -contains "$($_.Component)/$($_.Zone)" })
        $targets=@{}
        foreach ($selectedRecord in $chosen) {
            $m=Get-NativeFinishMeta $selectedRecord.Component $selectedRecord.Zone
            foreach ($z in $zoneRecords) {
                $other=Get-NativeFinishMeta $z.Component $z.Zone
                if ($other -and $other.material_id -eq $m.material_id -and ($other.part -eq $m.part -or $m.material_id -eq '2296875182504' -or [bool]$window.FindName('HDShared').IsChecked)) {$targets[(Get-PreviewMaterialKey $z)]=$z}
            }
        }
        return @($targets.Values)
    }

    if ($record.Component -eq 6) {return @(Get-NativeSelectionZones $record)}
    $meta=Get-NativeFinishMeta $record.Component $record.Zone
    if (-not $meta) {return @()}
    $all=[bool]$window.FindName('HDShared').IsChecked
    return @($zoneRecords | Where-Object {
        $other=Get-NativeFinishMeta $_.Component $_.Zone
        $other -and $other.material_id -eq $meta.material_id -and ($all -or $other.part -eq $meta.part)
    })
}
function Test-NativeSailGroup {
    $cloth=@($zoneRecords | Where-Object {$_.Component -eq 6 -and (Get-NativeFinishMeta $_.Component $_.Zone).material_id -eq '2296875182504'})
    if ($cloth.Count -ne 26) {throw 'Expected 26 atlas cloth surfaces'}
    $targets=@(Get-NativeFinishTargets $cloth[0])
    if ($targets.Count -ne 26 -or @($targets | Where-Object {(Get-NativeFinishMeta $_.Component $_.Zone).material_id -ne '2296875182504'}).Count) {throw 'Shared atlas targets include fittings or omit cloth'}
    $originals=@($zoneRecords | ForEach-Object {$_.BaseMaterial})
    Show-NativePartEdges $cloth[0]
    if ($script:silhouetteModel.Children.Count -ne 26 -or $script:silhouetteFillRows) {throw 'Sail group outline configuration is incorrect'}
    if (-not (Toggle-NativePartSelection $cloth[-1]) -or $script:nativeLastSelected -or $script:selectionBox) {throw 'Different sail did not deselect the shared group'}
    for ($i=0;$i -lt $zoneRecords.Count;$i++) {if (-not [object]::ReferenceEquals($zoneRecords[$i].Geometry.Material,$originals[$i])) {throw 'Sail deselection changed a base material'}}
    'PASS: 26 shared-atlas cloth targets; fittings excluded; another sail clears the whole group; materials preserved'
}
function Set-NativeFinish($record,[string]$design,[string]$tint,[string]$mode) {
    $targets=Get-NativeFinishTargets $record
    $rendered=@{}
    foreach ($target in $targets) {
        $key=Get-PreviewMaterialKey $target
        if (-not $script:nativeFinishStates.ContainsKey($key)) {$script:nativeFinishStates[$key]=@{Tint='#ffffff';Design=$null}}
        $state=$script:nativeFinishStates[$key]
        if ($mode -eq 'color') {$state.Tint=$tint} else {$state.Design=$design}
        $original=Get-NativeFinishPath $target.Component $target.Zone
        $state.FlipV=((Get-NativeFinishMeta $target.Component $target.Zone).material_id -eq '2296875182504')
        $renderKey=$original+'|'+$state.Design+'|'+$state.Tint
        if (-not $rendered.ContainsKey($renderKey)) {
            $output=Join-Path $script:nativeFinishRoot ('native-finish-'+[Guid]::NewGuid().ToString('N')+'.png')
            [JackdawNativeFinish]::Render($original,$state.Design,$state.Tint,$output,[bool]$state.FlipV)
            $rendered[$renderKey]=@{Path=$output;Material=(New-TextureMaterial $output -FlipV ([bool]$state.FlipV))}
        }
        $result=$rendered[$renderKey];$state.Output=$result.Path;$target.Texture=$result.Path
        $finished=if (Get-Command Add-NativeMetalShading -ErrorAction SilentlyContinue) {Add-NativeMetalShading $result.Material $target.Component $target.Zone} else {$result.Material}
        Set-AppliedPreviewMaterial $target $finished
        if ($target.Component -eq $sailComponentIndex) {$script:currentSailViewMode='Custom preview'}
    }
    Apply-SailViewMode;Show-NativePartEdges $record;Update-TexturePreview
    Set-UiText $footer 'Finish updated on the selected part.'
    if (Get-Command Save-NativeDesignAfterEdit -ErrorAction SilentlyContinue) {Save-NativeDesignAfterEdit}
}
function Apply-NativeFinishPng($record,[string]$path) {
    if (-not (Get-NativeFinishMeta $record.Component $record.Zone)) {return $false}
    Set-NativeFinish $record $path $null 'design';return $true
}
function Set-NativeMaterialFade($material) {
    if ($material -is [Windows.Media.Media3D.MaterialGroup]) {foreach ($child in $material.Children) {Set-NativeMaterialFade $child};return}
    if ($material.Brush) {
        $animation=[Windows.Media.Animation.DoubleAnimation]::new(1.0,0.18,[Windows.Duration]::new([TimeSpan]::FromMilliseconds(250)))
        $material.Brush.BeginAnimation([Windows.Media.Brush]::OpacityProperty,$animation)
    }
}
function Show-NativePartEdges($record) {
    $script:silhouetteModel=$null;$script:silhouetteSignature=$null
    if ($script:silhouetteImage) {$script:silhouetteImage.Source=$null}
    $script:selectionBox=$null
    $script:nativeLastSelected=$null
    Apply-SailViewMode
    if (-not $record -or -not $record.Geometry -or -not $script:nativeViewport) {return}
    $meta=Get-NativeFinishMeta $record.Component $record.Zone
    if (-not $meta -or -not $meta.area) {return}
    $script:nativeLastSelected=$record
    $partZones=@(Get-NativeSelectionZones $record)
    $script:silhouetteFillRows=($record.Component -ne 6)
    if ($script:embeddedReady) {Send-EmbeddedMessage @{type='select';key="$($record.Component)/$($record.Zone)"}} else {Set-NativeSilhouette $partZones}
    if ($script:nativeFocusFade) {
        $faded=@{}
        foreach ($zone in $zoneRecords) {
            $other=Get-NativeFinishMeta $zone.Component $zone.Zone
            if ($other -and (Get-NativeSelectionGroup $zone) -eq (Get-NativeSelectionGroup $record)) {continue}
            $material=$zone.Geometry.Material;if (-not $material) {continue};$key=$material.GetHashCode()
            if (-not $faded.ContainsKey($key)) {$copy=$material.CloneCurrentValue();Set-NativeMaterialFade $copy;$faded[$key]=$copy}
            $zone.Geometry.Material=$faded[$key];$zone.Geometry.BackMaterial=$faded[$key]
        }
    }
    $partZones=@(Get-NativeSelectionZones $record)
    $vertices=0;$triangles=0
    foreach ($zone in $partZones) {$vertices+=$zone.Geometry.Geometry.Positions.Count;$triangles+=$zone.Geometry.Geometry.TriangleIndices.Count/3}
    $groupLabel=if ($record.Component -eq 6) {'All sails — shared PNG atlas'} else {$meta.area}
    $window.FindName('MeshInfo').Text="$groupLabel`nVertices: $vertices   Triangles: $triangles`nUV sets: 1"
}
function Clear-NativePartSelection {
    $script:embeddedSelectionKeys=@()
    if ($script:embeddedReady) {Send-EmbeddedMessage @{type='clear-selection'}}
    $previousSync=$script:syncingSelection
    try {
        $script:syncingSelection=$true
        $zones.SelectedIndex=-1
        if ($pngCollection) {$pngCollection.SelectedIndex=-1}
        $script:hdSelected=$null
        Show-NativePartEdges $null
        $window.FindName('MeshInfo').Text='Click a major area to inspect its mesh.'
        Update-TexturePreview
        Set-UiText $footer 'Selection cleared.'
    } finally {$script:syncingSelection=$previousSync}
}
function Toggle-NativePartSelection($record) {
    if (-not $script:nativeLastSelected -or -not $record) {return $false}
    $selectedMeta=Get-NativeFinishMeta $script:nativeLastSelected.Component $script:nativeLastSelected.Zone
    $clickedMeta=Get-NativeFinishMeta $record.Component $record.Zone
    if ($selectedMeta -and $clickedMeta -and (Get-NativeSelectionGroup $script:nativeLastSelected) -eq (Get-NativeSelectionGroup $record)) {
        Clear-NativePartSelection
        return $true
    }
    return $false
}
$window.FindName('HDFinishColor').Add_Click({
    $record=Get-SelectedZone;if (-not $record -or -not $record.Geometry) {Set-UiText $footer 'Select a ship part first.';return}
    $dialog=[Windows.Forms.ColorDialog]::new();$dialog.FullOpen=$true
    $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)];if ($state) {$dialog.Color=[Drawing.ColorTranslator]::FromHtml($state.Tint)}
    try {if ($dialog.ShowDialog() -eq 'OK') {Set-NativeFinish $record $null ('#{0:X2}{1:X2}{2:X2}' -f $dialog.Color.R,$dialog.Color.G,$dialog.Color.B) 'color'}} finally {$dialog.Dispose()}
})
$window.FindName('HDExportFinish').Add_Click({
    $record=Get-SelectedZone;if (-not $record) {return}
    $state=$script:nativeFinishStates[(Get-PreviewMaterialKey $record)]
    $path=if ($state -and $state.Output) {$state.Output} else {Get-RecordOriginalTexturePath $record}
    if (-not $path) {return}
    $dialog=[Microsoft.Win32.SaveFileDialog]::new();$dialog.Filter='PNG image (*.png)|*.png';$dialog.FileName='Jackdaw-finish.png'
    if ($dialog.ShowDialog($window)) {Copy-Item -LiteralPath $path -Destination $dialog.FileName -Force;Set-UiText $footer 'Finish PNG saved.'}
})
$window.FindName('HDRestore').Add_Click({
    $record=Get-SelectedZone;if (-not $record) {return}
    foreach ($target in (Get-NativeFinishTargets $record)) {
        $key=Get-PreviewMaterialKey $target;$script:nativeFinishStates.Remove($key)
        if ($script:appliedPreviewMaterials) {$script:appliedPreviewMaterials.Remove($key)}
        $target.Texture=$null
    }
    $script:generatedPreviewPath=$null;$script:generatedPreviewRecord=$null
    Show-NativePartEdges $record;Update-TexturePreview;Set-UiText $footer 'Default finish restored.'
    if (Get-Command Save-NativeDesignAfterEdit -ErrorAction SilentlyContinue) {Save-NativeDesignAfterEdit}
})
$window.FindName('ViewerSettings').Add_Click({
    if ($script:embeddedReady) {Send-EmbeddedMessage @{type='settings'};return}
    $menu=[Windows.Controls.ContextMenu]::new()
    foreach ($i in 0..4) {$item=[Windows.Controls.MenuItem]::new();$item.Header=@('Soft lighting','Bright lighting','Studio lighting','Flat lighting','Neutral lighting')[$i];$item.Tag=$i;$item.Add_Click({param($sender,$args)$lightingMode.SelectedIndex=[int]$sender.Tag});[void]$menu.Items.Add($item)}
    $fade=[Windows.Controls.MenuItem]::new();$fade.Header='Fade other parts';$fade.IsCheckable=$true;$fade.IsChecked=$script:nativeFocusFade
    $fade.Add_Click({param($sender,$args)$script:nativeFocusFade=$sender.IsChecked;Show-NativePartEdges $script:nativeLastSelected});[void]$menu.Items.Add($fade)
    $menu.PlacementTarget=$window.FindName('ViewerSettings');$menu.IsOpen=$true
})
$window.Add_ContentRendered({
    Set-UiText $modelStatus 'Assembled Jackdaw'
    Set-UiText $footer 'Native viewer ready. Select a major part to customize its finish.'
    [IO.File]::WriteAllText((Join-Path $dataRoot 'native-preview-loaded.json'),(@{renderer='HelixToolkit native';viewer_revision='20260911-comparison-repairs';surfaces=$zoneRecords.Count;source_sha256=$script:nativeFinishData.source_sha256;edge_parts=@($script:nativeFinishData.parts.PSObject.Properties).Count}|ConvertTo-Json))
})

function Test-NativeFinishPixels {
    $folder=Join-Path $dataRoot 'native-finish-test';New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $source=Join-Path $folder 'source.png';$design=Join-Path $folder 'design.png';$output=Join-Path $folder 'finish.png'
    $bitmap=[Drawing.Bitmap]::new(2,1);$bitmap.SetPixel(0,0,[Drawing.Color]::FromArgb(20,40,80));$bitmap.SetPixel(1,0,[Drawing.Color]::FromArgb(20,40,80));$bitmap.Save($source,[Drawing.Imaging.ImageFormat]::Png);$bitmap.Dispose()
    $bitmap=[Drawing.Bitmap]::new(2,1);$bitmap.SetPixel(1,0,[Drawing.Color]::FromArgb(200,60,30));$bitmap.Save($design,[Drawing.Imaging.ImageFormat]::Png);$bitmap.Dispose()
    [JackdawNativeFinish]::Render($source,$design,'#ffffff',$output)
    $bitmap=[Drawing.Bitmap]::new($output);$left=$bitmap.GetPixel(0,0);$right=$bitmap.GetPixel(1,0);$bitmap.Dispose()
    if ($left.R -ne 20 -or $left.G -ne 40 -or $left.B -ne 80 -or $right.R -ne 200 -or $right.G -ne 60 -or $right.B -ne 30) {throw 'Native PNG composition failed'}
    [JackdawNativeFinish]::Render($source,$design,'#00ff00',$output)
    $bitmap=[Drawing.Bitmap]::new($output);$right=$bitmap.GetPixel(1,0);$bitmap.Dispose()
    if ($right.R -ne 0 -or $right.G -ne 60 -or $right.B -ne 0) {throw 'Native tint/export failed'}
    'PASS: native finish transparency, tint and saved PNG pixels'
}
