; Installer Windows di StemForge (BUILD_SPEC §9.7) — Inno Setup 6.3+.
;
;   python packaging\windows\make_ico.py
;   iscc /DAppVersion=1.0.0 packaging\windows\stemforge.iss
;
; Legge l'app da packaging\dist\StemForge (PyInstaller) e l'icona da
; packaging\build\icon.ico; scrive dist\StemForge-<versione>-windows-x64-setup.exe.
;
; Scelte:
; - installazione PER UTENTE, senza diritti di amministratore: niente
;   richiesta UAC, niente PC aziendali bloccati; chi vuole installare per
;   tutti lo sceglie dal dialogo iniziale o con /ALLUSERS.
; - "Apri con" per i formati audio: un ProgID proprio elencato sotto
;   OpenWithProgids di ogni estensione, più la voce Applications\ con i
;   SupportedTypes. Il valore predefinito delle estensioni e la UserChoice
;   non si toccano: StemForge compare nel menu senza rubare l'associazione.
; - alla disinstallazione si CHIEDE se eliminare modelli, calibrazione e
;   log (~1 GB in %LOCALAPPDATA%\StemForge): lasciarli in silenzio sarebbe
;   un GB perso, cancellarli in silenzio un download da rifare. In modalità
;   silenziosa nessuno può rispondere, quindi i dati restano.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; Solo per il collaudo della domanda di disinstallazione su una cartella
; finta (packaging\windows\check_uninstall_prompt.py): il "Sì" non deve
; poter cancellare i modelli veri della macchina di build.
#ifndef DataDirName
  #define DataDirName "StemForge"
#endif
#define AppName "StemForge"
#define AppExe "StemForge.exe"
#define ProgId "StemForge.AudioFile"

[Setup]
AppId={{6B7C2E1F-4A3D-4F8B-9C21-5E0D7A9B3F42}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=StemForge
AppPublisherURL=https://github.com/Giovanniavino/stemforge
AppSupportURL=https://github.com/Giovanniavino/stemforge/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\dist
OutputBaseFilename=StemForge-{#AppVersion}-windows-x64-setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
italian.DeleteUserData=Eliminare anche i modelli di separazione scaricati, la calibrazione e i log (circa 1 GB)?%n%n%1%n%nSe pensi di reinstallare StemForge, scegli No: eviterai di riscaricare i modelli.
english.DeleteUserData=Also delete the downloaded separation models, the calibration and the logs (about 1 GB)?%n%n%1%n%nIf you plan to reinstall StemForge, choose No to avoid downloading the models again.
italian.DeleteFailed=Impossibile eliminare del tutto %1: puoi cancellarla a mano.
english.DeleteFailed=Could not fully delete %1: you can remove it by hand.
italian.AudioFileType=File audio
english.AudioFileType=Audio file

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\StemForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; il ProgID che "Apri con" propone: icona e comando sono quelli dell'app
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "{cm:AudioFileType}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: """{app}\{#AppExe}"",0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
; la voce Applications\ dà il nome mostrato e limita l'app ai tipi audio
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""
; un valore vuoto sotto OpenWithProgids aggiunge l'app al menu e basta;
; si toglie solo il NOSTRO valore, la chiave dell'estensione resta
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: none; ValueName: "{#ProgId}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{localappdata}\{#DataDirName}');
  { /SILENT e /VERYSILENT: nessuno può rispondere, i dati restano }
  if UninstallSilent() or not DirExists(DataDir) then
    Exit;
  if MsgBox(FmtMessage(CustomMessage('DeleteUserData'), [DataDir]),
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
  begin
    if not DelTree(DataDir, True, True, True) then
      MsgBox(FmtMessage(CustomMessage('DeleteFailed'), [DataDir]), mbError, MB_OK);
  end;
end;
