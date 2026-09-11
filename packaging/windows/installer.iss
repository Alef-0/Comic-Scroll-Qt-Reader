; Inno Setup Script for Comic Scroll Reader
; Compatible with Inno Setup 6+

#define MyAppName "Comic Scroll Reader"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Alef-0"
#define MyAppURL "https://github.com/Alef-0/Comic-Scroll-Qt-Reader"
#define MyAppExeName "comic-scroll-reader.exe"

[Setup]
AppId={{C0M1C-5CR0LL-R3AD3R-V100}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\copyright
OutputDir=..\..\dist
OutputBaseFilename=comic-scroll-reader-{#MyAppVersion}-setup
SetupIconFile=..\..\comic_scroll_reader\assets\csr_app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\build\pyinstaller_dist\comic-scroll-reader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Register comic archives in Windows "Open with" without taking over defaults
Root: HKCR; Subkey: ".cbz\OpenWithProgids"; ValueType: string; ValueName: "ComicScrollReader.cbz"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCR; Subkey: "ComicScrollReader.cbz"; ValueType: string; ValueData: "CBZ Comic Book"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ComicScrollReader.cbz\DefaultIcon"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCR; Subkey: "ComicScrollReader.cbz\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCR; Subkey: ".cbr\OpenWithProgids"; ValueType: string; ValueName: "ComicScrollReader.cbr"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCR; Subkey: "ComicScrollReader.cbr"; ValueType: string; ValueData: "CBR Comic Book"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ComicScrollReader.cbr\DefaultIcon"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCR; Subkey: "ComicScrollReader.cbr\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Right-click directory context menu: "Open with Comic Scroll Reader"
Root: HKCR; Subkey: "Directory\shell\ComicScrollReader"; ValueType: string; ValueData: "Open with Comic Scroll Reader"; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\ComicScrollReader"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"""
Root: HKCR; Subkey: "Directory\shell\ComicScrollReader\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCR; Subkey: "Directory\Background\shell\ComicScrollReader"; ValueType: string; ValueData: "Open with Comic Scroll Reader"; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\Background\shell\ComicScrollReader"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"""
Root: HKCR; Subkey: "Directory\Background\shell\ComicScrollReader\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%V"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
