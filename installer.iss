#define AppName "Schneepegel Brotenau"
#define AppExe "Schneepegel Brotenau.exe"

[Setup]
AppId={{F50C3F96-54D9-48CC-A6F8-38F3649C7E8C}
AppName={#AppName}
AppVersion=1.0.0
AppPublisher=Schneepegel Brotenau
DefaultDirName={localappdata}\Programs\Schneepegel Brotenau
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=yes
WizardStyle=modern
SetupIconFile=desktop\app.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=dist\installer
OutputBaseFilename=Schneepegel_Brotenau_Setup
Compression=zip/7
SolidCompression=no
CloseApplications=no
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "dist\Schneepegel Brotenau\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Schneepegel Brotenau öffnen"; Flags: nowait postinstall skipifsilent
