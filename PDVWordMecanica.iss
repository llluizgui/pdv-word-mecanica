#define MyAppName "PDV Word Mecanica"
#define MyAppVersion "1.2.0"
#define MyAppExeName "PDVWordMecanica.exe"
[Setup]
AppId={{F4EC1DD2-F9C5-4FD5-AE62-BA3E65FEE9A3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\PDV Word Mecanica
DefaultGroupName={#MyAppName}
OutputDir=instalador
OutputBaseFilename=PDVWord_Mecanica_Setup_1.2.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
[Files]
Source: "dist\PDVWordMecanica\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\PDV Word Mecanica"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\PDV Word Mecanica"; Filename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir PDV Word Mecanica"; Flags: nowait postinstall skipifsilent
