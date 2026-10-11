#ifndef OutputRoot
#error Use packaging/build_release.py
#endif
#ifndef BuildRoot
#error BuildRoot required
#endif
#define Version "2.3.3"
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
OutputDir={#OutputRoot}
OutputBaseFilename=CardVault-{#Version}-Setup-x64
SetupIconFile={#BuildRoot}\CardVault.ico
UninstallDisplayIcon={app}\CardVault.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce
[Files]
Source: "{#OutputRoot}\CardVault-{#Version}-Windows-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\CardVault"; Filename: "{app}\CardVault.exe"
Name: "{autodesktop}\CardVault"; Filename: "{app}\CardVault.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\CardVault.exe"; Description: "Launch CardVault"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: files; Name: "{app}\_internal\PySide6\opengl32sw.dll"
Type: files; Name: "{app}\_internal\PySide6\plugins\platforms\qdirect2d.dll"
Type: files; Name: "{app}\_internal\PySide6\plugins\imageformats\qpdf.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6opengl.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6pdf.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6qml.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6qmlmeta.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6qmlmodels.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6qmlworkerscript.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6quick.dll"
Type: files; Name: "{app}\_internal\PySide6\qt6virtualkeyboard.dll"
Type: files; Name: "{app}\_internal\PySide6\plugins\platforminputcontexts\qtvirtualkeyboardplugin.dll"
