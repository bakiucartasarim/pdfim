#define MyAppName      "PDFim"
#define MyAppVersion   "1.4"
#define MyAppPublisher "PDFim"
#define MyAppExeName   "PDFim.exe"
#define MyAppURL       ""
#define SrcDir         "dist\PDFim"

[Setup]
AppId={{A4B3C2D1-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=dist\installer
OutputBaseFilename=PDFim_Setup_v{#MyAppVersion}
SetupIconFile=pdfim.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0


[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Ek kısayollar:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Görev çubuğuna sabitle"; GroupDescription: "Ek kısayollar:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Tüm uygulama dosyaları
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Başlat menüsü
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}'i Kaldır"; Filename: "{uninstallexe}"
; Masaüstü
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Registry]
; PDF dosya ilişkilendirmesi

; .pdf uzantısını PDFim ile ilişkilendir (mevcut ilişkilendirmeye ek olarak)
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFim.Document"; ValueData: ""; Flags: uninsdeletevalue

; PDFim.Document ProgID tanımla
Root: HKCU; Subkey: "Software\Classes\PDFim.Document"; ValueType: string; ValueName: ""; ValueData: "PDF Belgesi (PDFim)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\PDFim.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\PDFim.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; "PDFim ile Aç" — sağ tık menüsü
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFim"; ValueType: string; ValueName: ""; ValueData: "PDFim ile Aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFim"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFim\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Uygulama bilgisi (Programı Ekle/Kaldır)
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
// Kurulum öncesi bilgi mesajı yok, minimal kurulum
