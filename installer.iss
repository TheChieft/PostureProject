; installer.iss
; -------------
; Inno Setup 6 script for PostureProject.
;
; Build locally (PowerShell, from repo root, AFTER running build.ps1):
;   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; The CI workflow passes /DMyAppVersion=X.Y.Z on the command line.
; Locally it defaults to the #define below — keep it in sync with version_info.txt.

; ── Version (overridden by CI via /DMyAppVersion=) ────────────────────────────
#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif

; ── App metadata ──────────────────────────────────────────────────────────────
#define MyAppName        "PostureProject"
#define MyAppPublisher   "PostureProject"
#define MyAppURL         "https://github.com/TheChieft/PostureProject"
#define MyAppExeName     "PostureProject.exe"
#define MyAppDescription "Monitor de postura con temporizador Pomodoro"

[Setup]
; Stable GUID — DO NOT change after first public release (enables in-place upgrades)
AppId={{F3A71C2D-04E5-4B60-8A9C-B7D6E5F4A3B1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppCopyright=PolyForm Noncommercial 1.0.0

; Installation path
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Branding
SetupIconFile=assets\icon.ico

; Output
OutputDir=dist
OutputBaseFilename=PostureProject-Setup-v{#MyAppVersion}
Compression=lzma2/ultra
SolidCompression=yes
InternalCompressLevel=ultra

; Windows 10 1809+ required (needed for newer MediaPipe / Python 3.11)
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; UAC: ask only if needed, allow user-level install
PrivilegesRequiredOverridesAllowed=dialog commandline

; Modern wizard (Windows 11 look)
WizardStyle=modern
WizardResizable=no

; Uninstall
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; \
  Flags: unchecked

[Files]
; All PyInstaller output — DLLs, models, assets, everything
Source: "dist\PostureProject\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop (optional, unchecked by default)
Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch after install
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Iniciar {#MyAppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[Registry]
; Register in Windows "Apps & Features" with version and publisher
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; \
  ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; \
  Flags: uninsdeletekey

[UninstallDelete]
; Remove logs and any leftover files from app directory
Type: filesandordirs; Name: "{app}\logs"
