; MyWhisper installer (Inno Setup 6).
; Built by scripts\build_installer.ps1, which passes AppVersion, SourceDir, OutputDir
; and, when a certificate is available, Sign=1 plus the "mysign" sign tool.
;
; Per-user install: no administrator rights, nothing outside the user's profile.
; The GPU runtime matching the graphics card is downloaded at the end
; (MyWhisper.exe --setup-runtime); the Whisper model at the first launch.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\dist\MyWhisper"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6C4F2B8E-3D1A-4E7B-9F0C-5A2D8E1B7C34}
AppName=MyWhisper
AppVersion={#AppVersion}
AppVerName=MyWhisper {#AppVersion}
AppPublisher=MyWhisper
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Installation de MyWhisper
DefaultDirName={localappdata}\Programs\MyWhisper
DefaultGroupName=MyWhisper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=MyWhisper-Setup-{#AppVersion}
SetupIconFile=..\build\mywhisper.ico
UninstallDisplayIcon={app}\MyWhisper.exe
UninstallDisplayName=MyWhisper
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
#ifdef Sign
SignTool=mysign
SignedUninstaller=yes
#endif

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.SetupRuntime=Détection de la carte graphique et téléchargement de l'accélération…
en.SetupRuntime=Detecting the graphics card and downloading GPU acceleration…
fr.DeleteData=Supprimer aussi les modèles téléchargés, l'accélération graphique et les réglages de MyWhisper ?%n%nChoisissez Non pour les garder (réinstallation plus rapide).
en.DeleteData=Also delete the downloaded models, the GPU acceleration and MyWhisper's settings?%n%nChoose No to keep them (faster reinstall).
fr.LaunchApp=Lancer MyWhisper
en.LaunchApp=Launch MyWhisper

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
; Same AppUserModelID as the running app (app.py), so a pinned shortcut groups with its window.
Name: "{group}\MyWhisper"; Filename: "{app}\MyWhisper.exe"; AppUserModelID: "MyWhisper.MyWhisper"
Name: "{group}\{cm:UninstallProgram,MyWhisper}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\MyWhisper"; Filename: "{app}\MyWhisper.exe"; AppUserModelID: "MyWhisper.MyWhisper"; Tasks: desktopicon

[Registry]
; "Start with Windows" is written by the app itself; only remove it on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "MyWhisper"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\MyWhisper.exe"; Parameters: "--setup-runtime"; StatusMsg: "{cm:SetupRuntime}"; Flags: waituntilterminated; Check: not WizardSilent
Filename: "{app}\MyWhisper.exe"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM MyWhisper.exe /F"; Flags: runhidden; RunOnceId: "KillMyWhisper"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { The GPU runtime is large and tied to this version: always removed. }
    DelTree(ExpandConstant('{localappdata}\MyWhisper\runtime'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\MyWhisper\logs'), True, True, True);
    if (not UninstallSilent) and
       (MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    begin
      DelTree(ExpandConstant('{localappdata}\MyWhisper'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\MyWhisper'), True, True, True);
    end;
  end;
end;
