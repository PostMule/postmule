; PostMule Setup — Inno Setup 6.x
; Build: run installer\build.ps1 from the repo root.
;
; Wizard flow (5 custom pages):
;   Page 1 — Google Account Setup   (credentials.json file picker + instructions)
;   Page 2 — AI Setup               (Gemini API key)
;   Page 3 — Alert Email            (where to send alerts)
;   Page 4 — Virtual Mailbox        (provider + sender email + subject prefix)
;   Page 5 — Daily Run Schedule     (time HH:MM)
; After installation, CurStepChanged(ssPostInstall) calls:
;   postmule.exe configure <all collected values>

#define AppName    "PostMule"
#define AppVersion "0.1.0"
#define AppPublisher "PostMule"
#define AppURL     "https://github.com/PostMule/app"
#define AppExe     "postmule.exe"
#define AppGUID    "{{B7F3C2A1-4D9E-4F8B-A3C6-1E2D5F6A8B9C}"

[Setup]
AppId={#AppGUID}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=PostMuleSetup
; SetupIconFile=..\postmule\web\static\favicon.ico  ; uncomment after adding favicon
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
; Data directory lives in user's AppData, not install dir — survives upgrades
UsedUserAreasWarning=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller one-folder bundle (built by build.ps1 before running ISCC)
Source: "..\dist\postmule\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu
Name: "{group}\PostMule Dashboard"; Filename: "{app}\{#AppExe}"; \
  Parameters: "serve"; WorkingDir: "{userappdata}\PostMule"; \
  Comment: "Open the PostMule web dashboard"
Name: "{group}\Uninstall PostMule"; Filename: "{uninstallexe}"
; Desktop (optional — user can untick)
Name: "{autodesktop}\PostMule Dashboard"; Filename: "{app}\{#AppExe}"; \
  Parameters: "serve"; WorkingDir: "{userappdata}\PostMule"; \
  Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[UninstallRun]
; Remove the Task Scheduler entry before files are deleted
Filename: "{app}\{#AppExe}"; Parameters: "uninstall-task"; \
  RunOnceId: "RemoveTask"; Flags: runhidden waituntilterminated

[Run]
; After install: start server in background, then open dashboard
Filename: "{app}\{#AppExe}"; Parameters: "serve"; \
  WorkingDir: "{userappdata}\PostMule"; \
  Description: "Start PostMule and open the dashboard"; \
  Flags: postinstall nowait skipifsilent shellexec

; ============================================================
; Pascal Script — custom wizard pages + post-install configure
; ============================================================
[Code]

// ---------------------------------------------------------------------------
// Global state collected across wizard pages
// ---------------------------------------------------------------------------
var
  // Page handles
  PageGoogle  : TWizardPage;
  PageGemini  : TWizardPage;
  PageEmail   : TWizardPage;
  PageVpm     : TWizardPage;
  PageSchedule: TWizardPage;

  // Controls — Google page
  MemoGoogleInstr: TNewMemo;
  EditJsonPath   : TNewEdit;
  BtnBrowse      : TNewButton;

  // Controls — Gemini page
  MemoGeminiInstr: TNewMemo;
  EditGeminiKey  : TNewEdit;

  // Controls — Alert email page
  EditAlertEmail: TNewEdit;

  // Controls — VPM page
  CboVpmProvider: TNewComboBox;
  LblSender     : TNewStaticText;
  EditVpmSender : TNewEdit;
  LblPrefix     : TNewStaticText;
  EditVpmPrefix : TNewEdit;

  // Controls — Schedule page
  EditRunTime: TNewEdit;

  // Collected values (populated in NextButtonClick)
  CredJsonPath: String;
  GeminiKey   : String;
  AlertEmail  : String;
  VpmProvider : String;
  VpmSender   : String;
  VpmPrefix   : String;
  RunTime     : String;


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

procedure OpenUrl(const Url: String);
begin
  ShellExec('open', Url, '', '', SW_SHOW, ewNoWait, 0);
end;

function IsValidTime(const T: String): Boolean;
var
  H, M: Integer;
  Parts: TArrayOfString;
begin
  Result := False;
  if Length(T) <> 5 then Exit;
  if T[3] <> ':' then Exit;
  if not TryStrToInt(Copy(T, 1, 2), H) then Exit;
  if not TryStrToInt(Copy(T, 4, 2), M) then Exit;
  Result := (H >= 0) and (H <= 23) and (M >= 0) and (M <= 59);
end;

function GetVpmSlug(Index: Integer): String;
begin
  case Index of
    0: Result := 'vpm';
    1: Result := 'earth_class';
    2: Result := 'traveling_mailbox';
    3: Result := 'postscan';
  else
    Result := 'vpm';
  end;
end;

// Use PowerShell Windows Forms to show a file-open dialog.
// Returns the selected path, or '' if cancelled.
function BrowseForJsonFile(): String;
var
  TmpPs, TmpOut, Cmd: String;
  ResultCode: Integer;
begin
  Result := '';
  TmpPs  := ExpandConstant('{tmp}\pm_browse.ps1');
  TmpOut := ExpandConstant('{tmp}\pm_json_path.txt');

  // Write the PowerShell helper script
  SaveStringToFile(TmpPs,
    'Add-Type -AssemblyName System.Windows.Forms' + #13#10 +
    '$d = New-Object System.Windows.Forms.OpenFileDialog' + #13#10 +
    '$d.Title  = "Select your Google credentials.json file"' + #13#10 +
    '$d.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"' + #13#10 +
    '$d.InitialDirectory = [Environment]::GetFolderPath("Desktop")' + #13#10 +
    'if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {' + #13#10 +
    '  $d.FileName | Out-File -FilePath "' + TmpOut + '" -Encoding UTF8 -NoNewline' + #13#10 +
    '}',
    False);

  Exec('powershell.exe',
    '-NonInteractive -ExecutionPolicy Bypass -File "' + TmpPs + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if FileExists(TmpOut) then begin
    LoadStringFromFile(TmpOut, Result);
    Result := Trim(Result);
    DeleteFile(TmpOut);
  end;
  DeleteFile(TmpPs);
end;

// Callback for the Browse button on Page 1
procedure OnBrowseClick(Sender: TObject);
var
  Path: String;
begin
  Path := BrowseForJsonFile();
  if Path <> '' then
    EditJsonPath.Text := Path;
end;

// Callback for the "Get my credentials.json →" link on Page 1
procedure OnGoogleLinkClick(Sender: TObject);
begin
  OpenUrl('https://github.com/PostMule/app/wiki/google-credentials');
end;

// Callback for the "Get a free Gemini API key →" link on Page 2
procedure OnGeminiLinkClick(Sender: TObject);
begin
  OpenUrl('https://aistudio.google.com/app/apikey');
end;


// ---------------------------------------------------------------------------
// InitializeWizard — build the 5 custom pages
// ---------------------------------------------------------------------------
procedure InitializeWizard();
var
  Lbl: TNewStaticText;
  LinkBtn: TNewButton;
  Y: Integer;
begin
  // ----------------------------------------------------------------
  // Page 1 — Google Account Setup
  // ----------------------------------------------------------------
  PageGoogle := CreateCustomPage(wpSelectDir,
    'Google Account Setup',
    'PostMule uses Google Drive (storage) and Gmail (email). ' +
    'You need a free Google Cloud credentials file.');

  Y := 0;

  MemoGoogleInstr := TNewMemo.Create(PageGoogle);
  MemoGoogleInstr.Parent   := PageGoogle.Surface;
  MemoGoogleInstr.SetBounds(0, Y, PageGoogle.SurfaceWidth, 80);
  MemoGoogleInstr.ReadOnly  := True;
  MemoGoogleInstr.ScrollBars := ssNone;
  MemoGoogleInstr.Color     := clBtnFace;
  MemoGoogleInstr.Text      :=
    'Steps:' + #13#10 +
    '1. Click the link below to open the PostMule setup guide.' + #13#10 +
    '2. Follow the instructions to create a free Google Cloud project.' + #13#10 +
    '3. Download credentials.json and select it with the Browse button.' + #13#10 +
    '(You can skip this step and connect your Google account later.)';
  Inc(Y, 88);

  LinkBtn := TNewButton.Create(PageGoogle);
  LinkBtn.Parent  := PageGoogle.Surface;
  LinkBtn.SetBounds(0, Y, 220, 23);
  LinkBtn.Caption := 'Open setup guide →';
  LinkBtn.OnClick := @OnGoogleLinkClick;
  Inc(Y, 32);

  Lbl := TNewStaticText.Create(PageGoogle);
  Lbl.Parent  := PageGoogle.Surface;
  Lbl.SetBounds(0, Y, PageGoogle.SurfaceWidth, 16);
  Lbl.Caption := 'credentials.json path (leave blank to configure later):';
  Inc(Y, 20);

  EditJsonPath := TNewEdit.Create(PageGoogle);
  EditJsonPath.Parent := PageGoogle.Surface;
  EditJsonPath.SetBounds(0, Y, PageGoogle.SurfaceWidth - 84, 22);
  EditJsonPath.Text := '';

  BtnBrowse := TNewButton.Create(PageGoogle);
  BtnBrowse.Parent  := PageGoogle.Surface;
  BtnBrowse.SetBounds(PageGoogle.SurfaceWidth - 80, Y, 80, 22);
  BtnBrowse.Caption := 'Browse...';
  BtnBrowse.OnClick := @OnBrowseClick;

  // ----------------------------------------------------------------
  // Page 2 — AI Setup (Gemini API key)
  // ----------------------------------------------------------------
  PageGemini := CreateCustomPage(PageGoogle.ID,
    'AI Setup — Gemini API Key',
    'PostMule uses Google Gemini to read and classify your mail. ' +
    'The free tier covers typical household use.');

  Y := 0;

  MemoGeminiInstr := TNewMemo.Create(PageGemini);
  MemoGeminiInstr.Parent    := PageGemini.Surface;
  MemoGeminiInstr.SetBounds(0, Y, PageGemini.SurfaceWidth, 64);
  MemoGeminiInstr.ReadOnly  := True;
  MemoGeminiInstr.ScrollBars := ssNone;
  MemoGeminiInstr.Color     := clBtnFace;
  MemoGeminiInstr.Text      :=
    'Sign in to Google AI Studio and create a free API key.' + #13#10 +
    'Copy the key and paste it below.' + #13#10 +
    '(You can also enter it later in Settings → Providers.)';
  Inc(Y, 72);

  LinkBtn := TNewButton.Create(PageGemini);
  LinkBtn.Parent  := PageGemini.Surface;
  LinkBtn.SetBounds(0, Y, 240, 23);
  LinkBtn.Caption := 'Get a free Gemini API key →';
  LinkBtn.OnClick := @OnGeminiLinkClick;
  Inc(Y, 36);

  Lbl := TNewStaticText.Create(PageGemini);
  Lbl.Parent  := PageGemini.Surface;
  Lbl.SetBounds(0, Y, PageGemini.SurfaceWidth, 16);
  Lbl.Caption := 'Gemini API key (leave blank to enter later):';
  Inc(Y, 20);

  EditGeminiKey := TNewEdit.Create(PageGemini);
  EditGeminiKey.Parent := PageGemini.Surface;
  EditGeminiKey.SetBounds(0, Y, PageGemini.SurfaceWidth, 22);
  EditGeminiKey.Text := '';
  EditGeminiKey.PasswordChar := '*';

  // ----------------------------------------------------------------
  // Page 3 — Alert Email
  // ----------------------------------------------------------------
  PageEmail := CreateCustomPage(PageGemini.ID,
    'Alert Email Address',
    'PostMule sends you a daily summary and urgent alerts. ' +
    'Enter the email address where you want to receive them.');

  Y := 0;

  Lbl := TNewStaticText.Create(PageEmail);
  Lbl.Parent  := PageEmail.Surface;
  Lbl.SetBounds(0, Y, PageEmail.SurfaceWidth, 16);
  Lbl.Caption := 'Your email address:';
  Inc(Y, 20);

  EditAlertEmail := TNewEdit.Create(PageEmail);
  EditAlertEmail.Parent := PageEmail.Surface;
  EditAlertEmail.SetBounds(0, Y, PageEmail.SurfaceWidth, 22);
  EditAlertEmail.Text := '';

  // ----------------------------------------------------------------
  // Page 4 — Virtual Mailbox Provider
  // ----------------------------------------------------------------
  PageVpm := CreateCustomPage(PageEmail.ID,
    'Virtual Mailbox Provider',
    'PostMule watches for scan notification emails from your virtual ' +
    'mailbox service (e.g. Virtual Post Mail, Earth Class Mail).');

  Y := 0;

  Lbl := TNewStaticText.Create(PageVpm);
  Lbl.Parent  := PageVpm.Surface;
  Lbl.SetBounds(0, Y, PageVpm.SurfaceWidth, 16);
  Lbl.Caption := 'Mailbox provider:';
  Inc(Y, 20);

  CboVpmProvider := TNewComboBox.Create(PageVpm);
  CboVpmProvider.Parent := PageVpm.Surface;
  CboVpmProvider.SetBounds(0, Y, 240, 22);
  CboVpmProvider.Style := csDropDownList;
  CboVpmProvider.Items.Add('Virtual Post Mail (vpm)');
  CboVpmProvider.Items.Add('Earth Class Mail');
  CboVpmProvider.Items.Add('Traveling Mailbox');
  CboVpmProvider.Items.Add('PostScan Mail');
  CboVpmProvider.ItemIndex := 0;
  Inc(Y, 32);

  LblSender := TNewStaticText.Create(PageVpm);
  LblSender.Parent  := PageVpm.Surface;
  LblSender.SetBounds(0, Y, PageVpm.SurfaceWidth, 16);
  LblSender.Caption := 'Scan notification sender email (leave blank for default):';
  Inc(Y, 20);

  EditVpmSender := TNewEdit.Create(PageVpm);
  EditVpmSender.Parent := PageVpm.Surface;
  EditVpmSender.SetBounds(0, Y, PageVpm.SurfaceWidth, 22);
  EditVpmSender.Text := '';
  Inc(Y, 32);

  LblPrefix := TNewStaticText.Create(PageVpm);
  LblPrefix.Parent  := PageVpm.Surface;
  LblPrefix.SetBounds(0, Y, PageVpm.SurfaceWidth, 16);
  LblPrefix.Caption := 'Scan notification subject prefix (leave blank for default):';
  Inc(Y, 20);

  EditVpmPrefix := TNewEdit.Create(PageVpm);
  EditVpmPrefix.Parent := PageVpm.Surface;
  EditVpmPrefix.SetBounds(0, Y, PageVpm.SurfaceWidth, 22);
  EditVpmPrefix.Text := '';

  // ----------------------------------------------------------------
  // Page 5 — Daily Run Schedule
  // ----------------------------------------------------------------
  PageSchedule := CreateCustomPage(PageVpm.ID,
    'Daily Run Schedule',
    'PostMule runs automatically every night to process your mail. ' +
    'Choose a time when your computer is likely to be on.');

  Y := 0;

  Lbl := TNewStaticText.Create(PageSchedule);
  Lbl.Parent  := PageSchedule.Surface;
  Lbl.SetBounds(0, Y, PageSchedule.SurfaceWidth, 16);
  Lbl.Caption := 'Daily run time (HH:MM, 24-hour, e.g. 02:00):';
  Inc(Y, 20);

  EditRunTime := TNewEdit.Create(PageSchedule);
  EditRunTime.Parent := PageSchedule.Surface;
  EditRunTime.SetBounds(0, Y, 80, 22);
  EditRunTime.Text := '02:00';
  Inc(Y, 36);

  Lbl := TNewStaticText.Create(PageSchedule);
  Lbl.Parent  := PageSchedule.Surface;
  Lbl.SetBounds(0, Y, PageSchedule.SurfaceWidth, 80);
  Lbl.Caption :=
    'PostMule is registered as a Windows Task Scheduler job.' + #13#10 +
    'If your PC is off at the scheduled time, Windows will run the' + #13#10 +
    'task as soon as the machine comes back online.';
  Lbl.WordWrap := True;
end;


// ---------------------------------------------------------------------------
// NextButtonClick — validate each custom page before allowing Next
// ---------------------------------------------------------------------------
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  // Page 1 — Google credentials (optional, so no hard block)
  if CurPageID = PageGoogle.ID then begin
    CredJsonPath := Trim(EditJsonPath.Text);
    if (CredJsonPath <> '') and not FileExists(CredJsonPath) then begin
      MsgBox('The file "' + CredJsonPath + '" was not found.' + #13#10 +
             'Please browse again or leave the field blank to configure later.',
             mbError, MB_OK);
      Result := False;
    end;
  end;

  // Page 2 — Gemini key (optional)
  if CurPageID = PageGemini.ID then begin
    GeminiKey := Trim(EditGeminiKey.Text);
    // No validation — blank is fine
  end;

  // Page 3 — Alert email (required)
  if CurPageID = PageEmail.ID then begin
    AlertEmail := Trim(EditAlertEmail.Text);
    if AlertEmail = '' then begin
      MsgBox('Please enter an alert email address.' + #13#10 +
             'PostMule uses this to send you daily summaries and urgent alerts.',
             mbError, MB_OK);
      Result := False;
    end else if (Pos('@', AlertEmail) = 0) or (Pos('.', AlertEmail) = 0) then begin
      MsgBox('"' + AlertEmail + '" does not look like a valid email address.' + #13#10 +
             'Please check and try again.', mbError, MB_OK);
      Result := False;
    end;
  end;

  // Page 4 — VPM (all fields optional)
  if CurPageID = PageVpm.ID then begin
    VpmProvider := GetVpmSlug(CboVpmProvider.ItemIndex);
    VpmSender   := Trim(EditVpmSender.Text);
    VpmPrefix   := Trim(EditVpmPrefix.Text);
  end;

  // Page 5 — Schedule (must be valid HH:MM)
  if CurPageID = PageSchedule.ID then begin
    RunTime := Trim(EditRunTime.Text);
    if not IsValidTime(RunTime) then begin
      MsgBox('"' + RunTime + '" is not a valid time.' + #13#10 +
             'Please enter a time in HH:MM format, e.g. 02:00.',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;


// ---------------------------------------------------------------------------
// UpdateReadyMemo — shown on the "Ready to Install" summary page
// ---------------------------------------------------------------------------
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypesInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  S := S + 'Install folder:' + NewLine + Space + MemoDirInfo + NewLine + NewLine;

  if CredJsonPath <> '' then
    S := S + 'Google credentials:' + NewLine + Space + CredJsonPath + NewLine + NewLine
  else
    S := S + 'Google credentials:' + NewLine + Space + '(configure later in dashboard)' + NewLine + NewLine;

  if GeminiKey <> '' then
    S := S + 'Gemini API key:' + NewLine + Space + '****' + Copy(GeminiKey, Length(GeminiKey) - 3, 4) + NewLine + NewLine
  else
    S := S + 'Gemini API key:' + NewLine + Space + '(configure later in Settings → Providers)' + NewLine + NewLine;

  S := S + 'Alert email:' + NewLine + Space + AlertEmail + NewLine + NewLine;
  S := S + 'Virtual mailbox provider:' + NewLine + Space + VpmProvider + NewLine + NewLine;
  S := S + 'Daily run time:' + NewLine + Space + RunTime + NewLine;

  Result := S;
end;


// ---------------------------------------------------------------------------
// CurStepChanged — call `postmule configure` after files are laid down
// ---------------------------------------------------------------------------
procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, DataDir, Params: String;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then Exit;

  AppDir  := ExpandConstant('{app}');
  DataDir := ExpandConstant('{userappdata}\PostMule');

  // Build the parameter string for `postmule configure`
  Params := 'configure'
    + ' --data-dir "' + DataDir + '"'
    + ' --alert-email "' + AlertEmail + '"'
    + ' --vpm-provider "' + VpmProvider + '"'
    + ' --run-time "' + RunTime + '"';

  if CredJsonPath <> '' then
    Params := Params + ' --credentials-json "' + CredJsonPath + '"';

  if GeminiKey <> '' then
    Params := Params + ' --gemini-key "' + GeminiKey + '"';

  if VpmSender <> '' then
    Params := Params + ' --vpm-sender "' + VpmSender + '"';

  if VpmPrefix <> '' then
    Params := Params + ' --vpm-prefix "' + VpmPrefix + '"';

  if not Exec(AppDir + '\' + '{#AppExe}', Params, DataDir,
              SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    MsgBox('PostMule configuration step failed (could not start postmule.exe).' + #13#10 +
           'You can configure PostMule manually by opening the dashboard.',
           mbError, MB_OK);
  end else if ResultCode <> 0 then begin
    MsgBox('PostMule configuration returned an error (code ' + IntToStr(ResultCode) + ').' + #13#10 +
           'Your settings have been partially applied. Open the dashboard to complete setup.',
           mbInformation, MB_OK);
  end;
end;
