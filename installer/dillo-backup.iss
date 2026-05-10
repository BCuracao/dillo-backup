; ─────────────────────────────────────────────────────────────────────
;  Dillo Backup — Inno Setup Script
;
;  Compiles the contents of dist/dillo/ into a Windows installer.
;  Run: ISCC.exe installer\dillo-backup.iss
;  Or:  python installer/build_windows.py  (calls ISCC automatically)
; ─────────────────────────────────────────────────────────────────────

#define MyAppName "Dillo Backup"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Dillo Backup"
#define MyAppURL "https://github.com/dillo-backup"
#define MyAppExeName "DilloBackup.exe"

[Setup]
AppId={{B8E4F2A1-3C7D-4E9F-A1B2-5D8F6E3A7C9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\Dillo Backup
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Dillo-Backup-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
SetupIconFile=dillo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Launcher
Source: "..\dist\dillo\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Application icon (used by shortcuts)
Source: "dillo.ico"; DestDir: "{app}"; Flags: ignoreversion

; Backend (PyInstaller onedir output)
Source: "..\dist\dillo\backend\dillo-backend\*"; DestDir: "{app}\backend\dillo-backend"; Flags: ignoreversion recursesubdirs createallsubdirs

; Frontend (Next.js standalone)
Source: "..\dist\dillo\frontend\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs

; Node.js runtime
Source: "..\dist\dillo\node\*"; DestDir: "{app}\node"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dillo.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dillo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any runtime-created files in the install directory
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\backend\__pycache__"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Do you want to remove all Dillo Backup user data (backups database, logs)?',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\Dillo Backup'), True, True, True);
    end;
  end;
end;
