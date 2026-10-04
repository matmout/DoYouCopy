; DoYouCopy installer (Inno Setup 6).
; Built by scripts\build_installer.ps1, which passes AppVersion, SourceDir, OutputDir
; and, when a certificate is available, Sign=1 plus the "mysign" sign tool.
;
; Per-user install: no administrator rights, nothing outside the user's profile.
; The GPU runtime matching the graphics card is downloaded at the end
; (DoYouCopy.exe --setup-runtime); the Whisper model at the first launch.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\dist\DoYouCopy"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
; New identity since the app was renamed; MyWhisper (the former name) is replaced at [Run].
AppId={{E942453C-C236-4DDF-98A3-7AAF44D01E2E}
AppName=DoYouCopy
AppVersion={#AppVersion}
AppVerName=DoYouCopy {#AppVersion}
AppPublisher=DoYouCopy
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Installation de DoYouCopy
DefaultDirName={localappdata}\Programs\DoYouCopy
DefaultGroupName=DoYouCopy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=DoYouCopy-Setup-{#AppVersion}
SetupIconFile=..\build\doyoucopy.ico
UninstallDisplayIcon={app}\DoYouCopy.exe
UninstallDisplayName=DoYouCopy
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
fr.DeleteData=Supprimer aussi l'historique (dictées, transcriptions et enregistrements audio), les modèles téléchargés et les réglages de DoYouCopy ?%n%nChoisissez Non pour les garder (réinstallation plus rapide).
en.DeleteData=Also delete the history (dictations, transcripts and audio recordings), the downloaded models and DoYouCopy's settings?%n%nChoose No to keep them (faster reinstall).
fr.LaunchApp=Lancer DoYouCopy
en.LaunchApp=Launch DoYouCopy
fr.StartMenuIcon=Créer un raccourci dans le menu Démarrer
en.StartMenuIcon=Create a Start menu shortcut
fr.Shortcuts=Raccourcis (modifiables ensuite dans les réglages de DoYouCopy) :
en.Shortcuts=Shortcuts (can be changed later in DoYouCopy's settings):

[Tasks]
; The app's settings can add or remove the same shortcuts later
; (src/doyoucopy/desktop/shortcuts.py writes the very same paths).
Name: "startmenuicon"; Description: "{cm:StartMenuIcon}"; GroupDescription: "{cm:Shortcuts}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:Shortcuts}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
; Same AppUserModelID as the running app (app.py), so a pinned shortcut groups with its window.
Name: "{group}\DoYouCopy"; Filename: "{app}\DoYouCopy.exe"; AppUserModelID: "DoYouCopy.DoYouCopy"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,DoYouCopy}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{userdesktop}\DoYouCopy"; Filename: "{app}\DoYouCopy.exe"; AppUserModelID: "DoYouCopy.DoYouCopy"; Tasks: desktopicon

[UninstallDelete]
; Shortcuts created later from the settings are not in the uninstall log.
Type: files; Name: "{userdesktop}\DoYouCopy.lnk"
Type: files; Name: "{group}\DoYouCopy.lnk"
Type: dirifempty; Name: "{group}"

[Registry]
; "Start with Windows" is written by the app itself; only remove it on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "DoYouCopy"; Flags: uninsdeletevalue dontcreatekey

[Run]
; Upgrade from MyWhisper, the former name: close it, move its data (models, history,
; settings, GPU runtime) to the DoYouCopy folders, then uninstall it silently.
Filename: "{cmd}"; Parameters: "/C taskkill /IM MyWhisper.exe /F"; Flags: runhidden waituntilterminated; Check: HasMyWhisper
Filename: "{app}\DoYouCopy.exe"; Parameters: "--migrate"; Flags: waituntilterminated; Check: HasMyWhisper
Filename: "{code:MyWhisperUninstaller}"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; Flags: waituntilterminated; Check: HasMyWhisper
Filename: "{app}\DoYouCopy.exe"; Parameters: "--setup-runtime"; StatusMsg: "{cm:SetupRuntime}"; Flags: waituntilterminated; Check: not WizardSilent
Filename: "{app}\DoYouCopy.exe"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM DoYouCopy.exe /F"; Flags: runhidden; RunOnceId: "KillDoYouCopy"

[Code]
const
  MyWhisperKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C4F2B8E-3D1A-4E7B-9F0C-5A2D8E1B7C34}_is1';

function MyWhisperUninstaller(Param: String): String;
begin
  if not RegQueryStringValue(HKCU, MyWhisperKey, 'UninstallString', Result) then
    Result := '';
  Result := RemoveQuotes(Result);
end;

function HasMyWhisper: Boolean;
begin
  Result := (MyWhisperUninstaller('') <> '') and FileExists(MyWhisperUninstaller(''));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { The GPU runtime is large and tied to this version: always removed. }
    DelTree(ExpandConstant('{localappdata}\DoYouCopy\runtime'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\DoYouCopy\logs'), True, True, True);
    if (not UninstallSilent) and
       (MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    begin
      DelTree(ExpandConstant('{localappdata}\DoYouCopy'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\DoYouCopy'), True, True, True);
    end;
  end;
end;
