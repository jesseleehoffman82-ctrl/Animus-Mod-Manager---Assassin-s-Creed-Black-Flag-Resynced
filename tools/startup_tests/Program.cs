using System.Reflection;

// Exercise the compiled manager resolver, without starting its UI or touching
// a real library. AppContext.BaseDirectory is this dedicated test output.
var assembly = Assembly.LoadFrom(Path.GetFullPath(args[0]));
var method = assembly.GetType("AnimusModManager.Program", true)!.GetMethod(
    "ResolveRoot", BindingFlags.Static | BindingFlags.NonPublic)!;
var originalCwd = Directory.GetCurrentDirectory();
var temporary = Path.Combine(Path.GetTempPath(), "animus-startup-test-" + Guid.NewGuid());
var ownMarker = Path.Combine(AppContext.BaseDirectory, "tools", "Animus_loader", "web", "index.html");
if (File.Exists(ownMarker)) throw new Exception("Test output already has a frontend; refusing to overwrite it.");
string Resolve(params string[] values) => (string)method.Invoke(null, new object[] { values })!;
void AssertEqual(string expected, string actual)
{
    if (!string.Equals(Path.GetFullPath(expected).TrimEnd(Path.DirectorySeparatorChar),
                       Path.GetFullPath(actual).TrimEnd(Path.DirectorySeparatorChar),
                       StringComparison.OrdinalIgnoreCase))
        throw new Exception($"Expected {expected}, got {actual}");
}
try
{
    var oldMarker = Path.Combine(temporary, "tools", "Animus_loader", "web", "index.html");
    Directory.CreateDirectory(Path.GetDirectoryName(oldMarker)!);
    File.WriteAllText(oldMarker, "test only");
    Directory.CreateDirectory(Path.GetDirectoryName(ownMarker)!);
    File.WriteAllText(ownMarker, "test only");
    Directory.SetCurrentDirectory(temporary);
    AssertEqual(AppContext.BaseDirectory, Resolve());
    AssertEqual(temporary, Resolve(temporary));
    AssertEqual(AppContext.BaseDirectory, Resolve(Path.Combine(temporary, "missing")));
    File.Delete(ownMarker);
    AssertEqual(temporary, Resolve());
    Console.WriteLine("PASS: compiled startup resolver (own installation, explicit root, invalid root, CWD fallback).");
}
finally
{
    Directory.SetCurrentDirectory(originalCwd);
    if (File.Exists(ownMarker)) File.Delete(ownMarker);
    Directory.Delete(temporary, recursive: true);
}
