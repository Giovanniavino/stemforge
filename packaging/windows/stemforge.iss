; Installer Windows di StemForge (BUILD_SPEC §9.7) — Inno Setup 6.3+.
;
;   python packaging\windows\build_installer.py
;
; che genera packaging\build\icon.ico e chiama ISCC con /DAppVersion e
; /DLongestRelPath (percorso relativo più lungo dentro l'app, misurato).
; Legge l'app da packaging\dist\StemForge (PyInstaller); scrive
; dist\StemForge-<versione>-windows-x64-setup.exe.
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
; - percorsi lunghi: con i percorsi lunghi di Windows disattivati (il
;   default) un file oltre 259 caratteri non si apre, e l'app installata
;   in una cartella troppo profonda non caricherebbe le sue DLL. L'installer
;   rifiuta quella cartella con un messaggio chiaro invece di lasciare
;   un'app rotta; con i percorsi lunghi attivi la accetta.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef LongestRelPath
  #error Passa /DLongestRelPath=<n>: lo misura packaging\windows\build_installer.py
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
italian.PathTooLong=La cartella scelta è troppo lunga:%n%n%1%n%nCon i percorsi lunghi di Windows disattivati StemForge non potrebbe avviarsi da lì. Scegli una cartella di al massimo %2 caratteri.
english.PathTooLong=The selected folder is too long:%n%n%1%n%nWith Windows long paths disabled StemForge could not start from there. Choose a folder of at most %2 characters.

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
; un valore stringa vuoto sotto OpenWithProgids aggiunge l'app al menu e
; basta. NON "ValueType: none": Inno con none crea la chiave ma nessun
; valore, e l'app non compare nel menu (provato con ISCC 6.7.2).
; Si toglie solo il NOSTRO valore, OpenWithProgids solo se è rimasta vuota
; e la chiave dell'estensione solo se è vuota anch'essa (cioè se le aveva
; create l'installazione su un profilo nuovo). La riga della chiave
; .ext viene PRIMA di quella di OpenWithProgids: il disinstallatore
; ripercorre le voci al contrario, quindi la svuota prima di valutarla.
Root: HKA; Subkey: "Software\Classes\.wav"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.mp3"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.flac"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.ogg"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.m4a"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.aiff"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.aif"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  { MAX_PATH di Win32 (260) meno il terminatore }
  ClassicMaxPath = 259;
  LongestRelPath = {#LongestRelPath};

function LongPathsEnabled(): Boolean;
var
  Enabled: Cardinal;
begin
#ifdef AssumeLongPathsDisabled
  { solo collaudo (check_uninstall_prompt.py): il dev-box li ha attivi }
  Enabled := 0;
#else
  if not RegQueryDWordValue(HKLM, 'SYSTEM\CurrentControlSet\Control\FileSystem', 'LongPathsEnabled', Enabled) then
    Enabled := 0;
#endif
  Result := Enabled = 1;
end;

function MaxInstallDirLength(): Integer;
begin
  { cartella + separatore + percorso interno più lungo entro MAX_PATH }
  Result := ClassicMaxPath - 1 - LongestRelPath;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    Exit;
  Dir := RemoveBackslashUnlessRoot(WizardDirValue());
  if (Length(Dir) > MaxInstallDirLength()) and not LongPathsEnabled() then
  begin
    { in silenzio (/DIR= troppo lunga) il messaggio va nel log e Setup esce con errore }
    Log(Format('Cartella troppo lunga: %d caratteri, massimo %d', [Length(Dir), MaxInstallDirLength()]));
    SuppressibleMsgBox(FmtMessage(CustomMessage('PathTooLong'), [Dir, IntToStr(MaxInstallDirLength())]),
                       mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

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
