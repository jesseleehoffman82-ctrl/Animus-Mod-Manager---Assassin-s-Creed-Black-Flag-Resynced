using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;

// Uses the user's installed toolkit; no toolkit binaries are distributed here.
if (args.Length < 3) {
    Console.Error.WriteLine("AnvilBridge <toolkit-folder> <list|patch> <base-forge> [output-file]");
    return 2;
}
try {
    string toolkit = Path.GetFullPath(args[0]);
    string source = Path.GetFullPath(args[2]);
    string? requestedOutput = args.Length > 3 ? Path.GetFullPath(args[3]) : null;
    string? extraFolder = args.Length > 4 ? Path.GetFullPath(args[4]) : null;
    Environment.CurrentDirectory = toolkit;
    Environment.SetEnvironmentVariable("PATH", Path.Combine(toolkit,"Libs") + ";" + Environment.GetEnvironmentVariable("PATH"));
    AssemblyLoadContext.Default.Resolving += (_, name) => {
        string path = Path.Combine(toolkit,"Libs",name.Name+".dll");
        return File.Exists(path) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(path) : null;
    };
    var asm = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(toolkit,"AnvilToolkit.dll"));
    var gameType = asm.GetType("AnvilToolkit.Utils.Game",true)!;
    var game = Enum.Parse(gameType,"BlackFlagResynced");
    asm.GetType("AnvilToolkit.Utils.DataStorage",true)!.GetField("ActiveGame")!.SetValue(null,game);
    // Headless operation uses numeric IDs; the optional online name catalogue
    // must not open a download dialog in a console worker.
    var fileList = asm.GetType("AnvilToolkit.Utils.GameFileList",true)!.GetField("List")!;
    fileList.SetValue(null,Activator.CreateInstance(fileList.FieldType));
    var forgeType = asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Containers.ForgeFile",true)!;
    object forge;
    if (args[1] == "schema-xml") {
        if (requestedOutput == null || File.Exists(requestedOutput)) throw new ArgumentException("A new XML output path is required");
        var storage=asm.GetType("AnvilToolkit.Utils.DataStorage",true)!;
        asm.GetType("AnvilToolkit.Utils.HashedData",true)!.GetField("HashedStrings")!.SetValue(null,new Dictionary<uint,string>());
        storage.GetField("GlobalScimitarClassReader")!.SetValue(null,Activator.CreateInstance(asm.GetType("AnvilToolkit.FileTypes.AnvilNext.ScimitarClassReader",true)!));
        dynamic schema=storage.GetMethod("LoadLocalSchema")!.Invoke(null,new object[]{game,false,false})!;
        storage.GetField("ActiveSchema")!.SetValue(null,schema);
        dynamic document=schema.ReadFile(source);
        if(document == null) throw new Exception("Schema reader returned no document");
        System.Xml.Linq.XElement xml=document.ToXml();
        if(xml == null) throw new Exception("Schema reader returned no XML");
        using var output=new FileStream(requestedOutput,FileMode.CreateNew,FileAccess.Write);
        xml.Save(output);
        Console.WriteLine(JsonSerializer.Serialize(new {status="exported",schema="ACBlackFlagResynced",output=requestedOutput}));
    } else if (args[1] == "mesh-audit") {
        var storage=asm.GetType("AnvilToolkit.Utils.DataStorage",true)!;
        var hashes=asm.GetType("AnvilToolkit.Utils.HashedData",true)!.GetField("HashedStrings")!;
        hashes.SetValue(null,new Dictionary<uint,string>());
        var readerType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.ScimitarClassReader",true)!;
        var classReader=Activator.CreateInstance(readerType)!;
        storage.GetField("GlobalScimitarClassReader")!.SetValue(null,classReader);
        var schema=storage.GetMethod("LoadLocalSchema")!.Invoke(null,new object[]{game,false,false});
        storage.GetField("ActiveSchema")!.SetValue(null,schema);
        using var binary=new BinaryReader(File.OpenRead(source));
        binary.BaseStream.Position=1;
        var baseType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.ScimitarClass",true)!;
        var meshType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Models.Mesh",true)!;
        object baseObject=Activator.CreateInstance(baseType,new object[]{binary,game,0u})!;
        dynamic mesh=Activator.CreateInstance(meshType,new[]{baseObject})!;
        meshType.GetMethod("ReadFromFileRPG")!.Invoke(mesh,new object[]{binary});
        if(mesh.Failed || mesh.Vertices.Count==0) throw new Exception("Native mesh reader failed");
        var options=new JsonSerializerOptions {IncludeFields=true};
        static double[] V4(dynamic v) => v==null ? new double[4] : new double[]{(double)v.x,(double)v.y,(double)v.z,(double)v.w};
        static double[] V2(dynamic v) => v==null ? new double[2] : new double[]{(double)v.x,(double)v.y};
        var vertices=new List<object>();
        foreach(dynamic v in mesh.Vertices) vertices.Add(new {position=V4(v.Position),uv0=V2(v.TEXCOORD_0),uv1=V2(v.TEXCOORD_1),color0=V4(v.Color0),color1=V4(v.Color1)});
        var meshReport=new {vertices=(int)mesh.Vertices.Count,faces=(int)mesh.Faces.Count,vertexFormat=mesh.VertexFormat.ToString(),
            materials=mesh.CompiledMeshMaterials,vertexSample=vertices[0],readBytes=binary.BaseStream.Position,totalBytes=binary.BaseStream.Length};
        Console.WriteLine(JsonSerializer.Serialize(meshReport,options));
        if(requestedOutput!=null) {
            File.WriteAllText(requestedOutput,JsonSerializer.Serialize(vertices,options));
        }
    } else if (args[1] == "repack") {
        if (args.Length != 5 || File.Exists(requestedOutput)) throw new ArgumentException("New output and replacement folder required");
        byte[] original=File.ReadAllBytes(source);
        var dataType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Containers.DataFile",true)!;
        dynamic container=Activator.CreateInstance(dataType,new object[]{original,game})!;
        using var originalReader=new BinaryReader(new MemoryStream(original));
        object? metadata=dataType.GetMethod("GetMetaData")!.Invoke(null,new object[]{originalReader,game});
        var replacements=JsonSerializer.Deserialize<Dictionary<string,string>>(File.ReadAllText(Path.Combine(extraFolder!,"replacements.json")))!;
        var files=new List<dynamic>();
        var expected=new Dictionary<ulong,byte[]>();
        foreach(dynamic pair in container.FilesByID) {
            dynamic file=pair.Value;
            string id=((ulong)file.ID).ToString("X16");
            if(replacements.TryGetValue(id,out string? relative)) {
                string replacement=Path.GetFullPath(Path.Combine(extraFolder!,relative));
                if(!replacement.StartsWith(extraFolder!+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new Exception("Replacement outside folder");
                byte[] bytes=File.ReadAllBytes(replacement);
                if(bytes.Length<13 || bytes[0]!=0 || BitConverter.ToUInt32(bytes,9)!=(uint)file.Type) throw new Exception("Replacement class mismatch");
                file.ID=BitConverter.ToUInt64(bytes,1);
                file.Data=bytes;
                file.Name=((ulong)file.ID).ToString("X16")+".bin";
                replacements.Remove(id);
            }
            files.Add(file);
            expected.Add((ulong)file.ID,(byte[])file.Data);
        }
        if(replacements.Count!=0) throw new Exception("Replacement resource missing in source container");
        container.FilesByID.Clear();
        foreach(dynamic file in files) container.FilesByID.Add((ulong)file.ID,file);
        Directory.CreateDirectory(Path.GetDirectoryName(requestedOutput!)!);
        using(var output=new FileStream(requestedOutput!,FileMode.CreateNew)) {
            var method=dataType.GetMethods().Single(m=>m.Name=="Serialize" && m.GetParameters().Length==4 && m.GetParameters()[0].ParameterType==typeof(Stream));
            var result=((bool,string))method.Invoke(container,new object?[]{output,"",metadata,false})!;
            if(result.Item1) throw new Exception(result.Item2);
        }
        dynamic check=Activator.CreateInstance(dataType,new object[]{File.ReadAllBytes(requestedOutput!),game})!;
        if(check.FilesByID.Count!=expected.Count) throw new Exception("Round-trip resource count changed");
        foreach(var pair in expected) {
            if(!check.FilesByID.ContainsKey(pair.Key) || !((byte[])check.FilesByID[pair.Key].Data).SequenceEqual(pair.Value)) throw new Exception("Round-trip resource bytes changed");
        }
        Console.WriteLine(JsonSerializer.Serialize(new {output=requestedOutput,resources=expected.Count,status="round-trip-verified-not-game-tested"}));
    } else if (args[1] == "patch") {
        if (args.Length < 4 || args.Length > 5) throw new ArgumentException("Output file required");
        string output = requestedOutput!;
        if (File.Exists(output)) throw new IOException("Output already exists; refusing to overwrite");
        if (Path.GetDirectoryName(output) == Path.GetDirectoryName(source)) throw new IOException("Build patches in a staging folder, not in the game directory");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        forge = forgeType.GetMethod("CreateNewPatchForge")!.Invoke(null,new object[]{source}) ?? throw new Exception("Toolkit could not create patch");
        forgeType.GetField("ShowMessages")!.SetValue(forge,false);
        if(extraFolder!=null) {
            var dataType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Containers.DataFile",true)!;
            dynamic directory=((Array)forgeType.GetProperty("Directories")!.GetValue(forge)!).GetValue(0)!;
            var entries=new List<object>();
            foreach(var entry in directory.Entries) entries.Add(entry);
            foreach(string path in Directory.GetFiles(extraFolder,"*.data").Order())
                entries.Add(dataType.GetMethod("CreateForgeEntry")!.Invoke(null,new object[]{path,(uint)DateTimeOffset.UtcNow.ToUnixTimeSeconds(),game})!);
            var array=Array.CreateInstance(asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Containers.ForgeEntry",true)!,entries.Count);
            for(int i=0;i<entries.Count;i++) array.SetValue(entries[i],i);
            directory.GetType().GetProperty("Entries").SetValue(directory,array);
        }
        await (Task)forgeType.GetMethod("Serialize")!.Invoke(forge,new object[]{"",output,game})!;
        if (!File.Exists(output) || new FileInfo(output).Length == 0) throw new IOException("Toolkit did not write a patch");
        Console.WriteLine(JsonSerializer.Serialize(new { output, bytes=new FileInfo(output).Length, status="staged-unverified" }));
    } else if (args[1] == "list" || args[1] == "extract") {
        forge=Activator.CreateInstance(forgeType)!;
        using var stream=(Stream)forgeType.GetMethod("OpenStream")!.Invoke(forge,new object[]{"",source})!;
        var entries = new List<object>();
        foreach (dynamic directory in (Array)forgeType.GetProperty("Directories")!.GetValue(forge)!)
            foreach (dynamic entry in directory.Entries) {
                entries.Add(new { id=((ulong)entry.ID).ToString("X16"), name=(string?)entry.Name, offset=(long)entry.Offset, bytes=(int)entry.LengthOnDisk });
                if (args[1] == "extract" && args.Length == 5 && ((ulong)entry.ID).ToString("X16").Equals(args[4],StringComparison.OrdinalIgnoreCase)) {
                    Directory.CreateDirectory(requestedOutput!);
                    stream.Position=(long)entry.Offset;
                    byte[] data=new byte[(int)entry.LengthOnDisk];
                    stream.ReadExactly(data);
                    var dataType=asm.GetType("AnvilToolkit.FileTypes.AnvilNext.Containers.DataFile",true)!;
                    dynamic container=Activator.CreateInstance(dataType,new object[]{data,game})!;
                    if (container.FilesByID.Count == 0) throw new Exception("Toolkit decoded no resources");
                    var extracted = new List<object>();
                    foreach (dynamic pair in container.FilesByID) {
                        dynamic file=pair.Value;
                        string name=((ulong)file.ID).ToString("X16")+"."+((uint)file.Type).ToString("X8")+".bin";
                        string path=Path.Combine(requestedOutput!,name);
                        using var dest=new FileStream(path,FileMode.CreateNew);
                        dest.Write((byte[])file.Data);
                        extracted.Add(new {name,bytes=((byte[])file.Data).Length});
                    }
                    Console.WriteLine(JsonSerializer.Serialize(extracted));
                    return 0;
                }
            }
        if(args[1]=="extract") throw new Exception("Resource not found or wrong arguments");
        Console.WriteLine(JsonSerializer.Serialize(entries));
    } else throw new ArgumentException("Unknown command");
    return 0;
} catch (Exception e) {
    Console.Error.WriteLine(e.ToString());
    return 1;
}
