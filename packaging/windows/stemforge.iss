; Installer Windows di StemForge (BUILD_SPEC §9.7) — Inno Setup 6.
;
;   iscc /DAppVersion=1.0.0 packaging\windows\stemforge.iss
;
; Scelte:
; - installazione PER UTENTE, senza diritti di amministratore: niente
;   richiesta UAC, niente PC aziendali bloccati; chi vuole installare per
;   tutti sceglie dal dialogo iniziale (PrivilegesRequiredOverridesAllowed).
; - "Apri con" per i formati audio, registrato solo sotto Applications\:
;   StemForge compare nel menu senza rubare l'associazione predefinita.
; - alla disinstallazione si CHIEDE se eliminare i modelli scaricati
;   (~1 GB in %LOCALAPPDATA%\StemForge): lasciarli in silenzio sarebbe
;   un GB perso, cancellarli in silenzio un download da rifare.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "StemForge"
#define AppExe "StemForge.exe"

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
PrivilegesRequiredOverridesAllowed=dialog
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
italian.DeleteModels=Eliminare anche i modelli di separazione scaricati (circa 1 GB)?%n%nSe pensi di reinstallare StemForge, scegli No: eviterai di riscaricarli.
english.DeleteModels=Also delete the downloaded separation models (about 1 GB)?%n%nIf you plan to reinstall StemForge, choose No to avoid downloading them again.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\StemForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: none; ValueName: "Applications\{#AppExe}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: none; ValueName: "Applications\{#AppExe}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: none; ValueName: "Applications\{#AppExe}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: none; ValueName: "Applications\{#AppExe}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\StemForge');
    if DirExists(DataDir) and not UninstallSilent() then
    begin
      if MsgBox(CustomMessage('DeleteModels'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
