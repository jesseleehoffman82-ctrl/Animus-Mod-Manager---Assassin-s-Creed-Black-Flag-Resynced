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
    public static void Render(string original,string design,string hex,string output) {
        using(var source=new Bitmap(original))
        using(var bitmap=new Bitmap(source.Width,source.Height,PixelFormat.Format32bppArgb)) {
            using(var g=Graphics.FromImage(bitmap)) {
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
    return $script:nativeFinishMaterials[$path]
}
function Get-NativeFinishTargets($record) {
    $meta=Get-NativeFinishMeta $record.Component $record.Zone
    if (-not $meta) {return @()}
    $all=[bool]$window.FindName('HDShared').IsChecked
    return @($zoneRecords | Where-Object {
        $other=Get-NativeFinishMeta $_.Component $_.Zone
        $other -and $other.material_id -eq $meta.material_id -and ($all -or $other.part -eq $meta.part)
    })
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
        $renderKey=$original+'|'+$state.Design+'|'+$state.Tint
        if (-not $rendered.ContainsKey($renderKey)) {
            $output=Join-Path $script:nativeFinishRoot ('native-finish-'+[Guid]::NewGuid().ToString('N')+'.png')
            [JackdawNativeFinish]::Render($original,$state.Design,$state.Tint,$output)
            $rendered[$renderKey]=@{Path=$output;Material=(New-TextureMaterial $output)}
        }
        $result=$rendered[$renderKey];$state.Output=$result.Path;$target.Texture=$result.Path
        Set-AppliedPreviewMaterial $target $result.Material
        if ($target.Component -eq $sailComponentIndex) {$script:currentSailViewMode='Custom preview'}
    }
    Apply-SailViewMode;Show-NativePartEdges $record;Update-TexturePreview
    Set-UiText $footer 'Finish updated on the selected part.'
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
    if ($script:selectionBox -and $script:nativeViewport) {[void]$script:nativeViewport.Children.Remove($script:selectionBox);$script:selectionBox=$null}
    Apply-SailViewMode
    if (-not $record -or -not $record.Geometry -or -not $script:nativeViewport) {return}
    $meta=Get-NativeFinishMeta $record.Component $record.Zone
    if (-not $meta -or -not $meta.area) {return}
    $script:nativeLastSelected=$record
    $info=$script:nativeFinishData.parts.PSObject.Properties[$meta.part].Value
    if (-not $info -or $info.count -le 0) {return}
    if (-not $script:nativeOutlineCache.ContainsKey($meta.part)) {$script:nativeOutlineCache[$meta.part]=[JackdawNativeFinish]::Points($script:nativeOutlineBytes,$info.offset,$info.count)}
    $edges=[HelixToolkit.Wpf.LinesVisual3D]::new();$edges.Points=$script:nativeOutlineCache[$meta.part]
    $edges.Color=[Windows.Media.Color]::FromRgb(232,186,112);$edges.Thickness=1.4
    $script:nativeViewport.Children.Add($edges);$script:selectionBox=$edges
    if ($script:nativeFocusFade) {
        $faded=@{}
        foreach ($zone in $zoneRecords) {
            $other=Get-NativeFinishMeta $zone.Component $zone.Zone
            if ($other -and $other.part -eq $meta.part) {continue}
            $material=$zone.Geometry.Material;if (-not $material) {continue};$key=$material.GetHashCode()
            if (-not $faded.ContainsKey($key)) {$copy=$material.CloneCurrentValue();Set-NativeMaterialFade $copy;$faded[$key]=$copy}
            $zone.Geometry.Material=$faded[$key];$zone.Geometry.BackMaterial=$faded[$key]
        }
    }
    $partZones=@($zoneRecords | Where-Object {(Get-NativeFinishMeta $_.Component $_.Zone).part -eq $meta.part})
    $vertices=0;$triangles=0
    foreach ($zone in $partZones) {$vertices+=$zone.Geometry.Geometry.Positions.Count;$triangles+=$zone.Geometry.Geometry.TriangleIndices.Count/3}
    $window.FindName('MeshInfo').Text="$($meta.area)`nVertices: $vertices   Triangles: $triangles`nUV sets: 1"
}
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
