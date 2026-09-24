# Bulk native mesh construction replaces per-vertex PowerShell dispatch.
Add-Type -ReferencedAssemblies @('PresentationCore','WindowsBase') -TypeDefinition @'
using System;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Media3D;
public static class JackdawFastModelReader {
 public static MeshGeometry3D ReadMesh(BinaryReader reader,int vertices,int indices){
  if(vertices<0||indices<0||vertices>10000000||indices>60000000)throw new InvalidDataException("Invalid mesh size");
  var p=new Point3DCollection(vertices);var n=new Vector3DCollection(vertices);var uv=new PointCollection(vertices);var tri=new Int32Collection(indices);
  for(int i=0;i<vertices;i++){
   p.Add(new Point3D(reader.ReadSingle(),reader.ReadSingle(),reader.ReadSingle()));
   n.Add(new Vector3D(reader.ReadSingle(),reader.ReadSingle(),reader.ReadSingle()));
   uv.Add(new Point(reader.ReadSingle(),reader.ReadSingle()));
  }
  for(int i=0;i<indices;i++){uint index=reader.ReadUInt32();if(index>=vertices)throw new InvalidDataException("Invalid triangle index");tri.Add((int)index);}
  var mesh=new MeshGeometry3D{Positions=p,Normals=n,TextureCoordinates=uv,TriangleIndices=tri};mesh.Freeze();return mesh;
 }
}
'@
