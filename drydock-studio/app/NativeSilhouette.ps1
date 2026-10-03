Add-Type -ReferencedAssemblies @('PresentationCore','PresentationFramework','WindowsBase','System.Xaml') -TypeDefinition @'
using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Media.Media3D;
public static class JackdawSilhouette {
    // Flood only the exterior background. Internal seams and holes cannot glow.
    public static byte[] Glow(byte[] mask,int w,int h) {
        int n=w*h;var exterior=new bool[n];var queue=new int[n];int head=0,tail=0;
        Action<int> push=i=>{if(!exterior[i]&&mask[i*4+3]<32){exterior[i]=true;queue[tail++]=i;}};
        for(int x=0;x<w;x++){push(x);push((h-1)*w+x);}
        for(int y=0;y<h;y++){push(y*w);push(y*w+w-1);}
        while(head<tail){int i=queue[head++],x=i%w,y=i/w;if(x>0)push(i-1);if(x<w-1)push(i+1);if(y>0)push(i-w);if(y<h-1)push(i+w);}
        // Visit the narrow boundary band, not an 81-sample kernel at every background pixel.
        var distance=new byte[n];for(int i=0;i<n;i++)distance[i]=17;
        for(int i=0;i<n;i++) {
            if(mask[i*4+3]<32)continue;int x=i%w,y=i/w;
            if(x>0&&x<w-1&&y>0&&y<h-1&&mask[(i-1)*4+3]>=32&&mask[(i+1)*4+3]>=32&&mask[(i-w)*4+3]>=32&&mask[(i+w)*4+3]>=32)continue;
            for(int dy=-4;dy<=4;dy++)for(int dx=-4;dx<=4;dx++) {
                int d=dx*dx+dy*dy,xx=x+dx,yy=y+dy;
                if(d>16||xx<0||xx>=w||yy<0||yy>=h)continue;
                int j=yy*w+xx;if(exterior[j]&&d<distance[j])distance[j]=(byte)d;
            }
        }
        var output=new byte[n*4];
        for(int i=0;i<n;i++) {
            int best=distance[i];if(best>16)continue;
            double falloff=1-Math.Sqrt(best)/5;byte a=(byte)(150*falloff*falloff);
            output[i*4]=a;output[i*4+1]=(byte)(216*a/255);output[i*4+2]=(byte)(143*a/255);output[i*4+3]=a;
        }
        return output;
    }
    static double Edge(Point a,Point b,double x,double y) {return (x-a.X)*(b.Y-a.Y)-(y-a.Y)*(b.X-a.X);}
    static byte[] CloseSeams(byte[] input,int w,int h,bool fillRows) {
        // Seal sub-pixel cracks between adjoining material surfaces before
        // finding the exterior, so atlas seams cannot become internal outlines.
        var source=input;
        for(int pass=0;pass<4;pass++) {
            var dest=new byte[source.Length];bool dilate=pass<2;
            for(int y=0;y<h;y++)for(int x=0;x<w;x++) {
                bool filled=!dilate;
                for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
                    int xx=x+dx,yy=y+dy;bool on=xx>=0&&xx<w&&yy>=0&&yy<h&&source[(yy*w+xx)*4+3]>=32;
                    if(dilate)filled|=on;else filled&=on;
                }
                if(filled)dest[(y*w+x)*4+3]=255;
            }
            source=dest;
        }
        // Major parts can be open shells (the hull has no closed deck cap).
        // Fill their projected interior rather than tracing the cavity walls.
        if(fillRows)for(int y=0;y<h;y++) {
            int left=w,right=-1;
            for(int x=0;x<w;x++)if(source[(y*w+x)*4+3]>=32){left=Math.Min(left,x);right=x;}
            for(int x=left;x<=right;x++)source[(y*w+x)*4+3]=255;
        }
        return source;
    }
    static void Raster(Model3D model,Matrix3D parent,ProjectionCamera camera,Vector3D forward,Vector3D right,Vector3D up,int w,int h,int projectionWidth,byte[] mask) {
        var matrix=model.Transform.Value;matrix.Append(parent);
        var group=model as Model3DGroup;
        if(group!=null){foreach(var child in group.Children)Raster(child,matrix,camera,forward,right,up,w,h,projectionWidth,mask);return;}
        var gm=model as GeometryModel3D;if(gm==null)return;
        var mesh=gm.Geometry as MeshGeometry3D;if(mesh==null)return;
        var points=new Point[mesh.Positions.Count];var valid=new bool[points.Length];
        var perspective=camera as PerspectiveCamera;var ortho=camera as OrthographicCamera;
        double tangent=perspective==null?0:Math.Tan(perspective.FieldOfView*Math.PI/360);
        for(int i=0;i<points.Length;i++) {
            var delta=matrix.Transform(mesh.Positions[i])-camera.Position;double z=Vector3D.DotProduct(delta,forward);
            if(z<=camera.NearPlaneDistance)continue;
            double scale=perspective==null?projectionWidth/ortho.Width:projectionWidth/(2*z*tangent);
            points[i]=new Point(w*.5+Vector3D.DotProduct(delta,right)*scale,h*.5-Vector3D.DotProduct(delta,up)*scale);valid[i]=true;
        }
        for(int t=0;t+2<mesh.TriangleIndices.Count;t+=3) {
            int ia=mesh.TriangleIndices[t],ib=mesh.TriangleIndices[t+1],ic=mesh.TriangleIndices[t+2];
            if(!valid[ia]||!valid[ib]||!valid[ic])continue;
            var a=points[ia];var b=points[ib];var c=points[ic];double area=Edge(a,b,c.X,c.Y);if(Math.Abs(area)<1e-8)continue;
            int x0=Math.Max(0,(int)Math.Floor(Math.Min(a.X,Math.Min(b.X,c.X)))),x1=Math.Min(w-1,(int)Math.Ceiling(Math.Max(a.X,Math.Max(b.X,c.X))));
            int y0=Math.Max(0,(int)Math.Floor(Math.Min(a.Y,Math.Min(b.Y,c.Y)))),y1=Math.Min(h-1,(int)Math.Ceiling(Math.Max(a.Y,Math.Max(b.Y,c.Y))));
            for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++) {
                double e1=Edge(a,b,x+.5,y+.5),e2=Edge(b,c,x+.5,y+.5),e3=Edge(c,a,x+.5,y+.5);
                if((e1>=0&&e2>=0&&e3>=0)||(e1<=0&&e2<=0&&e3<=0))mask[(y*w+x)*4+3]=255;
            }
        }
    }
    public static System.Threading.Tasks.Task<BitmapSource> BeginRender(Model3DGroup model,Camera camera,int w,int h,bool fillRows=true) {
        if(!model.IsFrozen||!camera.IsFrozen)throw new ArgumentException("Worker inputs must be frozen");
        return System.Threading.Tasks.Task.Factory.StartNew(()=>Render(model,camera,w,h,fillRows));
    }
    public static BitmapSource Render(Model3DGroup model,Camera camera,int w,int h,bool fillRows=true) {
        var projection=camera as ProjectionCamera;if(projection==null)throw new ArgumentException("Projection camera required");
        var forward=projection.LookDirection;forward.Normalize();var right=Vector3D.CrossProduct(forward,projection.UpDirection);right.Normalize();var up=Vector3D.CrossProduct(right,forward);up.Normalize();
        int pad=128,pw=w+pad*2,ph=h+pad*2;var mask=new byte[pw*ph*4];Raster(model,Matrix3D.Identity,projection,forward,right,up,pw,ph,w,mask);
        var padded=Glow(CloseSeams(mask,pw,ph,fillRows),pw,ph);var cropped=new byte[w*h*4];
        for(int y=0;y<h;y++)Buffer.BlockCopy(padded,((y+pad)*pw+pad)*4,cropped,y*w*4,w*4);
        var result=BitmapSource.Create(w,h,96,96,PixelFormats.Pbgra32,null,cropped,w*4);result.Freeze();return result;
    }
}
'@
$script:silhouetteImage=[Windows.Controls.Image]::new()
$script:silhouetteImage.IsHitTestVisible=$false
$script:silhouetteImage.Stretch='Fill'
[Windows.Controls.Panel]::SetZIndex($script:silhouetteImage,5)
$viewportHost.Children.Add($script:silhouetteImage) | Out-Null
function Update-NativeSilhouette {
    if (-not $script:silhouetteModel -or -not $script:nativeViewport) {return}
    $width=[Math]::Max(1,[int]$viewportHost.ActualWidth);$height=[Math]::Max(1,[int]$viewportHost.ActualHeight)
    if ($width -lt 10 -or $height -lt 10) {return}
    $camera=$script:nativeViewport.Camera
    $signature="$width/$height/$($camera.Position)/$($camera.LookDirection)/$($camera.UpDirection)"
    if ($signature -eq $script:silhouetteSignature) {return}
    if ($script:silhouetteTask) {
        if (-not $script:silhouetteTask.IsCompleted) {return}
        if (-not $script:silhouetteTask.IsFaulted -and $script:silhouettePendingSignature -eq $signature -and [object]::ReferenceEquals($script:silhouettePendingModel,$script:silhouetteModel)) {
            $script:silhouetteImage.Source=$script:silhouetteTask.Result
            $script:silhouetteSignature=$signature
        }
        $script:silhouetteTask=$null
        if ($signature -eq $script:silhouetteSignature) {return}
    }
    $snapshot=$camera.CloneCurrentValue();$snapshot.Freeze()
    $script:silhouettePendingSignature=$signature;$script:silhouettePendingModel=$script:silhouetteModel
    $script:silhouetteImage.Source=$null
    $script:silhouetteTask=[JackdawSilhouette]::BeginRender($script:silhouetteModel,$snapshot,$width,$height,$script:silhouetteFillRows)
}
function Set-NativeSilhouette($partZones) {
    $model=[Windows.Media.Media3D.Model3DGroup]::new()
    $white=[Windows.Media.Media3D.EmissiveMaterial]::new([Windows.Media.Brushes]::White);$white.Freeze()
    foreach ($zone in $partZones) {
        $mesh=[Windows.Media.Media3D.GeometryModel3D]::new($zone.Geometry.Geometry,$white)
        $mesh.BackMaterial=$white;$mesh.Transform=$zone.Geometry.Transform
        $model.Children.Add($mesh)
    }
    $model.Freeze()
    $script:silhouetteModel=$model;$script:silhouetteSignature=$null
    $script:selectionBox=$script:silhouetteImage
    Update-NativeSilhouette
}
$script:silhouetteTimer=[Windows.Threading.DispatcherTimer]::new()
$script:silhouetteTimer.Interval=[TimeSpan]::FromMilliseconds(80)
$script:silhouetteTimer.Add_Tick({Update-NativeSilhouette})
$script:silhouetteTimer.Start()
$window.Add_Closed({$script:silhouetteTimer.Stop()})
