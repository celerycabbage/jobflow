#ifndef MyAppVersion
  #define MyAppVersion "0.3.0"
#endif
#ifndef PublishDir
  #define PublishDir "JobFlow.Desktop\\bin\\Release\\net8.0-windows7.0\\win-x64\\publish"
#endif
#ifndef OutputDir
  #define OutputDir "..\\artifacts"
#endif

[Setup]
AppId={{E83A24F6-6D8B-4A19-930F-77A7A5B11D22}
AppName=JobFlow
AppVersion={#MyAppVersion}
AppPublisher=JobFlow
DefaultDirName={autopf}\JobFlow
DefaultGroupName=JobFlow
OutputDir={#OutputDir}
OutputBaseFilename=jobflow-desktop-setup-win-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\JobFlow.Desktop.exe
SetupIconFile=JobFlow.Desktop\Assets\JobFlow.ico
#ifdef SignCommand
SignTool=jobflowsign
SignedUninstaller=yes
#endif

[Files]
#ifdef SignCommand
Source: "{#PublishDir}\JobFlow.Desktop.exe"; DestDir: "{app}"; Flags: ignoreversion signonce
Source: "{#PublishDir}\server\JobFlow.Server.exe"; DestDir: "{app}\server"; Flags: ignoreversion signonce
#else
Source: "{#PublishDir}\JobFlow.Desktop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PublishDir}\server\JobFlow.Server.exe"; DestDir: "{app}\server"; Flags: ignoreversion
#endif
Source: "{#PublishDir}\server\*"; Excludes: "JobFlow.Server.exe"; DestDir: "{app}\server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "register-protocol.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PublishDir}\runtime\docker-compose.yml"; DestDir: "{app}\runtime"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\JobFlow"; Filename: "{app}\JobFlow.Desktop.exe"
Name: "{autodesktop}\JobFlow"; Filename: "{app}\JobFlow.Desktop.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："
Name: startup; Description: "登录 Windows 后启动 JobFlow"; GroupDescription: "自动启动："

[Registry]
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JobFlow"; ValueData: """{app}\JobFlow.Desktop.exe"""; Tasks: startup; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\jobflow"; ValueType: string; ValueData: "URL:JobFlow Capture Protocol"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\jobflow"; ValueName: "URL Protocol"; ValueType: string; ValueData: ""
Root: HKA; Subkey: "Software\Classes\jobflow\shell\open\command"; ValueType: string; ValueData: """{app}\JobFlow.Desktop.exe"" ""%1"""

[Run]
Filename: "{app}\JobFlow.Desktop.exe"; Description: "启动 JobFlow"; Flags: nowait postinstall skipifsilent
