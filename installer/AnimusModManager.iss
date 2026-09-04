#define MyAppName "Animus Mod & Outfit Manager"
#define MyAppVersion "0.1.7-beta"
#define MyAppPublisher "Animus Mod & Outfit Manager Project"
#define MyAppExeName "AnimusModManager.exe"
#define MySourceDir "..\release\Animus-Mod-Manager-0.1.7-beta-win-x64"

[Setup]
AppId={{C23FBEF0-088A-4500-9259-663C0D0ECA59}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright © 2026 Animus Mod & Outfit Manager Project
VersionInfoVersion=0.1.7.0
VersionInfoProductVersion=0.1.7.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Installer for Animus Mod & Outfit Manager
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\Animus Mod Manager
DefaultGroupName=Animus Mod & Outfit Manager
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\release
OutputBaseFilename=Animus-Mod-Manager-0.1.7-Beta-Setup
SetupIconFile=..\desktop\assets\animus.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
ChangesEnvironment=no
ChangesAssociations=no
CreateUninstallRegKey=yes
Uninstallable=yes
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Managed packages, settings and recovery backups are user data. Never remove
; this directory automatically during uninstall or an in-place beta upgrade.
Name: "{app}\mods"; Flags: uninsneveruninstall
Name: "{app}\mods\packages"; Flags: uninsneveruninstall
Name: "{app}\mods\installed"; Flags: uninsneveruninstall
Name: "{app}\mods\backups"; Flags: uninsneveruninstall
Name: "{app}\mods\textures"; Flags: uninsneveruninstall
Name: "{app}\mods\textures\backups"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Animus Mod & Outfit Manager"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Animus Mod & Outfit Manager"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Animus Mod & Outfit Manager"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Remove shortcuts created under the former display name during an upgrade.
Type: files; Name: "{autodesktop}\Animus Mod Manager.lnk"
Type: files; Name: "{group}\Animus Mod Manager.lnk"

[UninstallDelete]
; Only clear disposable logs/cache. The managed mod library and backups remain.
Type: files; Name: "{app}\mods\animus-native-shell.log"
Type: files; Name: "{app}\mods\animus-mod-manager.log"

[Code]
var
  ExistingInstallPath: String;
  ExistingInstallVersion: String;

function IsDotNet10DesktopRuntimeInstalled(): Boolean;
var
  DotNetRoot: String;
  FindRec: TFindRec;
begin
  Result := False;
  if not RegQueryStringValue(
    HKLM64,
    'SOFTWARE\dotnet\Setup\InstalledVersions\x64\sharedhost',
    'Path', DotNetRoot) then
    DotNetRoot := ExpandConstant('{pf64}\dotnet');

  if FindFirst(AddBackslash(DotNetRoot) + 'shared\Microsoft.WindowsDesktop.App\10.*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          Result := True;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function FindAnimusInstallUnderRoot(RootKey: Integer; var InstallPath: String;
  var InstalledVersion: String): Boolean;
var
  Names: TArrayOfString;
  I: Integer;
  KeyName: String;
  DisplayName: String;
begin
  Result := False;
  if not RegGetSubkeyNames(
    RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall', Names) then
    Exit;

  for I := 0 to GetArrayLength(Names) - 1 do
  begin
    KeyName := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + Names[I];
    DisplayName := '';
    if RegQueryStringValue(RootKey, KeyName, 'DisplayName', DisplayName) and
      ((Pos('animus mod manager', LowerCase(DisplayName)) > 0) or
       (Pos('animus mod & outfit manager', LowerCase(DisplayName)) > 0)) then
    begin
      InstallPath := '';
      InstalledVersion := '';
      RegQueryStringValue(RootKey, KeyName, 'InstallLocation', InstallPath);
      RegQueryStringValue(RootKey, KeyName, 'DisplayVersion', InstalledVersion);
      Result := True;
      Exit;
    end;
  end;
end;

function FindAnimusInstallAtPath(Candidate: String; var InstallPath: String): Boolean;
begin
  Result := FileExists(AddBackslash(Candidate) + '{#MyAppExeName}');
  if Result then
    InstallPath := Candidate;
end;

function FindExistingInstall(var InstallPath: String; var InstalledVersion: String): Boolean;
var
  UninstallKey: String;
begin
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C23FBEF0-088A-4500-9259-663C0D0ECA59}_is1';
  Result := RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', InstallPath);
  if Result then
    RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', InstalledVersion);

  if not Result then
  begin
    Result := RegQueryStringValue(HKLM64, UninstallKey, 'InstallLocation', InstallPath);
    if Result then
      RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', InstalledVersion);
  end;

  if not Result then
  begin
    Result := RegQueryStringValue(HKLM32, UninstallKey, 'InstallLocation', InstallPath);
    if Result then
      RegQueryStringValue(HKLM32, UninstallKey, 'DisplayVersion', InstalledVersion);
  end;

  { Early beta installers used different application metadata. Locate those by
    their display name so they are still upgraded in place. }
  if not Result then
    Result := FindAnimusInstallUnderRoot(HKCU, InstallPath, InstalledVersion);
  if not Result then
    Result := FindAnimusInstallUnderRoot(HKLM64, InstallPath, InstalledVersion);
  if not Result then
    Result := FindAnimusInstallUnderRoot(HKLM32, InstallPath, InstalledVersion);

  { Portable/early builds may not have an uninstall registry entry. }
  if not Result then
    Result := FindAnimusInstallAtPath(
      ExpandConstant('{localappdata}\Programs\Animus Mod Manager'), InstallPath);
  if not Result then
    Result := FindAnimusInstallAtPath(
      ExpandConstant('{localappdata}\Programs\Animus Mod & Outfit Manager'), InstallPath);
  if not Result then
    Result := FindAnimusInstallAtPath(
      ExpandConstant('{userappdata}\Animus Mod Manager'), InstallPath);

  if Result and (InstallPath = '') then
  begin
    InstallPath := ExpandConstant('{localappdata}\Programs\Animus Mod Manager');
  end;
end;

function InitializeSetup(): Boolean;
var
  InstallPath: String;
  InstalledVersion: String;
  VersionText: String;
  ErrorCode: Integer;
begin
  Result := True;

  if not IsDotNet10DesktopRuntimeInstalled() then
  begin
    if MsgBox(
      'Animus Mod & Outfit Manager requires Microsoft .NET 10 Desktop Runtime (x64).' + #13#10 + #13#10 +
      'Choose Yes to open the official Microsoft download page. Install the Desktop Runtime, then run Setup again.',
      mbInformation, MB_YESNO) = IDYES then
      ShellExec('', 'https://dotnet.microsoft.com/en-us/download/dotnet/10.0', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
    Result := False;
    Exit;
  end;

  if not FindExistingInstall(InstallPath, InstalledVersion) then
    Exit;

  ExistingInstallPath := InstallPath;
  ExistingInstallVersion := InstalledVersion;

  if InstalledVersion <> '' then
    VersionText := 'Version ' + InstalledVersion + ' is already installed.'
  else
    VersionText := 'Animus Mod & Outfit Manager is already installed.';

  Result := MsgBox(
    VersionText + #13#10 + #13#10 +
    'Location:' + #13#10 + InstallPath + #13#10 + #13#10 +
    'Choose Yes to reinstall or repair Animus Mod & Outfit Manager. Program files will be overwritten, while managed mods, settings and backups will be preserved.' + #13#10 + #13#10 +
    'Choose No to cancel Setup.',
    mbConfirmation, MB_YESNO) = IDYES;
end;

procedure InitializeWizard();
begin
  { If an early installer used another AppId, Inno Setup cannot recover its
    previous directory automatically. Reuse the directory we detected. }
  if ExistingInstallPath <> '' then
    WizardForm.DirEdit.Text := ExistingInstallPath;
end;
