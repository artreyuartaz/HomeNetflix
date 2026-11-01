; Inno Setup script. Build with installer\build_installer.ps1
#define AppName "Home Flix"
#define AppVersion "1.0"

[Setup]
AppId={{6B1F5C2E-8A47-4D0B-9E53-2C7A1D4F90A1}
AppName={#AppName}
AppVersion={#AppVersion}
; Per-user install so .env and history.json stay editable without admin rights
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=HomeFlix-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Home Flix automatically when I log in to Windows"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "stage\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 18; Tasks: desktopicon
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 18
Name: "{group}\{#AppName} Settings (.env)"; Filename: "notepad.exe"; Parameters: """{app}\.env"""
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}"; Description: "Start {#AppName} now"; Flags: postinstall nowait skipifsilent

; .env and history.json are user data: they are not listed in [Files], so upgrades and uninstalls keep them.
[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\static"
Type: files; Name: "{app}\homeflix.log"
Type: filesandordirs; Name: "{app}\thumbs"

[Code]
var
  VideoPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  VideoPage := CreateInputDirPage(wpSelectDir, 'Video Library', 'Where are your videos?',
    'Choose the drive and folder that contain your videos. You can change this later from ' +
    'Start Menu > Home Flix > Home Flix Settings (.env).', False, '');
  VideoPage.Add('');
  VideoPage.Values[0] := ExpandConstant('{%USERPROFILE}\Videos');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // Upgrade: keep the existing settings
  Result := (PageID = VideoPage.ID) and FileExists(WizardDirValue + '\.env');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
  EnvFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvFile := ExpandConstant('{app}\.env');
    if not FileExists(EnvFile) then
    begin
      SetArrayLength(Lines, 16);
      Lines[0] := '# ===== Home Flix settings =====';
      Lines[1] := '# Edit, save, then restart Home Flix (use the Quit button in the app, then the shortcut).';
      Lines[2] := '';
      Lines[3] := '# Where your videos live (drive + folder). No quotes needed.';
      Lines[4] := '#   VIDEOS_DIR=E:\Home Movies';
      Lines[5] := '#   VIDEOS_DIR=\\NAS\share\videos';
      Lines[6] := 'VIDEOS_DIR=' + VideoPage.Values[0];
      Lines[7] := '';
      Lines[8] := '# VLC (leave blank to auto-detect)';
      Lines[9] := 'VLC_PATH=';
      Lines[10] := '';
      Lines[11] := '# Optional';
      Lines[12] := '# VLC_FULLSCREEN=true';
      Lines[13] := '# PORT=8000';
      Lines[14] := '# Thumbnails need ffmpeg (auto-detected). If it is not found, set:';
      Lines[15] := '# FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe';
      SaveStringsToUTF8File(EnvFile, Lines, False);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    if not (FileExists(ExpandConstant('{commonpf}\VideoLAN\VLC\vlc.exe')) or
            FileExists(ExpandConstant('{commonpf32}\VideoLAN\VLC\vlc.exe'))) then
      MsgBox('VLC media player was not found on this PC. Home Flix plays videos in VLC, ' +
             'so install it from videolan.org (or set VLC_PATH in the settings file).',
             mbInformation, MB_OK);
end;
