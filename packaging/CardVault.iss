#define Version "2.3.2"
[Setup]
AppId={{1753D345-8BBB-4849-B0A2-914F0CCFF875}
AppName=CardVault
AppVersion={#Version}
AppPublisher=CardVault
DefaultDirName={localappdata}\Programs\CardVault
DefaultGroupName=CardVault
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=CardVault-{#Version}-Setup-x64
SetupIconFile=..\build\release\CardVault.ico
UninstallDisplayIcon={app}\CardVault.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce
[Files]
Source: "..\release\CardVault-{#Version}-Windows-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\CardVault"; Filename: "{app}\CardVault.exe"
Name: "{autodesktop}\CardVault"; Filename: "{app}\CardVault.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\CardVault.exe"; Description: "Launch CardVault"; Flags: nowait postinstall skipifsilent
