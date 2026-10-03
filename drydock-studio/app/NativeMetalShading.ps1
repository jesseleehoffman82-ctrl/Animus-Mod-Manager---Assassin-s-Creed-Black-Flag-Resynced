# Preserve the original diffuse/atlas and add only masked metal highlights.
$script:nativeMetalProfiles=@{}
$profilePath=Join-Path $script:nativeFinishRoot 'native-metal-profiles.json'
if (Test-Path -LiteralPath $profilePath) {
    $profiles=Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    foreach ($property in $profiles.PSObject.Properties) {$script:nativeMetalProfiles[$property.Name]=$property.Value}
}
$script:nativeMetalCache=@{}
Add-Type -ReferencedAssemblies @('System.Drawing') -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class JackdawMetalFinish {
    public static void Render(string colorPath,string maskPath,string output) {
        using(var input=new Bitmap(colorPath)) using(var maskInput=new Bitmap(maskPath))
        using(var color=new Bitmap(maskInput.Width,maskInput.Height,PixelFormat.Format32bppArgb))
        using(var mask=new Bitmap(maskInput.Width,maskInput.Height,PixelFormat.Format32bppArgb)) {
            using(var g=Graphics.FromImage(color))g.DrawImage(input,0,0,color.Width,color.Height);
            using(var g=Graphics.FromImage(mask))g.DrawImage(maskInput,0,0,mask.Width,mask.Height);
            var rect=new Rectangle(0,0,color.Width,color.Height);
            var c=color.LockBits(rect,ImageLockMode.ReadWrite,PixelFormat.Format32bppArgb);
            var m=mask.LockBits(rect,ImageLockMode.ReadOnly,PixelFormat.Format32bppArgb);
            try {
                var pixels=new byte[color.Width*4];var weights=new byte[pixels.Length];
                for(int y=0;y<color.Height;y++) {
                    var cp=IntPtr.Add(c.Scan0,y*c.Stride);var mp=IntPtr.Add(m.Scan0,y*m.Stride);
                    Marshal.Copy(cp,pixels,0,pixels.Length);Marshal.Copy(mp,weights,0,weights.Length);
                    for(int x=0;x<pixels.Length;x+=4) {
                        for(int channel=0;channel<3;channel++)pixels[x+channel]=(byte)((pixels[x+channel]*weights[x]+127)/255);
                        pixels[x+3]=255;
                    }
                    Marshal.Copy(pixels,0,cp,pixels.Length);
                }
            } finally {color.UnlockBits(c);mask.UnlockBits(m);}
            color.Save(output,ImageFormat.Png);
        }
    }
}
'@
# Make previously omitted metal surfaces reachable through the existing editor.
foreach ($entry in $script:nativeFinishZones.Values) {
    if (-not $entry.area -and $script:nativeMetalProfiles.ContainsKey($entry.material_id)) {$entry.area='Metal fittings'}
}
function Get-NativeDiffuseBrush($material) {
    if ($material -is [Windows.Media.Media3D.DiffuseMaterial]) {return $material.Brush}
    if ($material -is [Windows.Media.Media3D.MaterialGroup]) {
        foreach ($child in $material.Children) {if ($child -is [Windows.Media.Media3D.DiffuseMaterial]) {return $child.Brush}}
    }
    return $null
}
function Add-NativeMetalShading($material,[int]$component,[int]$zone) {
    $meta=Get-NativeFinishMeta $component $zone
    if (-not $meta -or -not $script:nativeMetalProfiles.ContainsKey($meta.material_id)) {return $material}
    $profile=$script:nativeMetalProfiles[$meta.material_id]
    $cacheKey=$meta.material_id+'/'+$material.GetHashCode()
    if ($script:nativeMetalCache.ContainsKey($cacheKey)) {return $script:nativeMetalCache[$cacheKey]}
    $mapPath=Join-Path $script:nativeFinishRoot $profile.map
    $colorPath=(Get-NativeDiffuseBrush $material).ImageSource.UriSource.LocalPath
    if ($colorPath -ne (Join-Path $script:nativeFinishRoot $profile.base_diffuse)) {
        $mapPath=Join-Path $script:nativeFinishRoot ('metal-custom-'+[Guid]::NewGuid().ToString('N')+'.png')
        [JackdawMetalFinish]::Render($colorPath,(Join-Path $script:nativeFinishRoot $profile.strength_map),$mapPath)
    }
    $mapMaterial=New-TextureMaterial $mapPath
    $group=[Windows.Media.Media3D.MaterialGroup]::new()
    $group.Children.Add($material)
    $group.Children.Add([Windows.Media.Media3D.SpecularMaterial]::new($mapMaterial.Brush,[double]$profile.power))
    $group.Freeze();$script:nativeMetalCache[$cacheKey]=$group
    return $group
}
function Test-NativeMetalShading {
    $trimParts=@('0x0000020DE6EF80AC :: 2258732286124','0x0000020EA5C5B997 :: 2261933996439','0x0000020EA5C631B1 :: 2261934027185')
    $trim=@($zoneRecords | Where-Object {
        $meta=Get-NativeFinishMeta $_.Component $_.Zone
        $meta.material_id -eq '2254710118072' -and $trimParts -contains $meta.part
    })
    if ($trim.Count -ne 3) {throw 'Deck and railing brass surfaces are missing'}
    foreach ($record in $trim) {
        foreach ($target in @(Get-NativeFinishTargets $record)) {
            if ((Get-NativeFinishMeta $target.Component $target.Zone).material_id -ne '2254710118072') {throw 'Brass customization includes wood'}
        }
    }
    'PASS: three separate brass surfaces; custom finishes exclude surrounding wood'
    $count=0
    foreach ($record in $zoneRecords) {
        $meta=Get-NativeFinishMeta $record.Component $record.Zone
        if ($meta -and $script:nativeMetalProfiles.ContainsKey($meta.material_id)) {
            if (-not $meta.area) {throw 'Metal surface is not editable'}
            if ($record.BaseMaterial -isnot [Windows.Media.Media3D.MaterialGroup] -or $record.BaseMaterial.Children[1] -isnot [Windows.Media.Media3D.SpecularMaterial]) {throw 'Metal highlight missing'}
            if (-not (Get-NativeDiffuseBrush $record.BaseMaterial)) {throw 'Original diffuse lost'}
            $count++
        }
    }
    $folder=Join-Path $dataRoot 'native-finish-test';New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $color=Join-Path $folder 'metal-color.png';$mask=Join-Path $folder 'metal-mask.png';$output=Join-Path $folder 'metal-output.png'
    $b=[Drawing.Bitmap]::new(2,1);$b.SetPixel(0,0,[Drawing.Color]::Red);$b.SetPixel(1,0,[Drawing.Color]::Lime);$b.Save($color);$b.Dispose()
    $b=[Drawing.Bitmap]::new(2,1);$b.SetPixel(0,0,[Drawing.Color]::White);$b.SetPixel(1,0,[Drawing.Color]::Black);$b.Save($mask);$b.Dispose()
    [JackdawMetalFinish]::Render($color,$mask,$output)
    $b=[Drawing.Bitmap]::new($output);$first=$b.GetPixel(0,0);$second=$b.GetPixel(1,0);$b.Dispose()
    if ($first.R -ne 255 -or $first.G -ne 0 -or $second.R -ne 0 -or $second.G -ne 0 -or $second.B -ne 0) {throw 'Custom finish failed to preserve metal mask'}
    "PASS: $count editable metal surfaces retain diffuse plus highlights; custom color follows metal mask"
}
