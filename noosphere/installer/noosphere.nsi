; NSIS installer script for the Noosphere CLI.
;
; Build prerequisites:
;   1. Run scripts\build_windows.ps1 so dist\noosphere\ exists.
;   2. Install the EnVar NSIS plugin: https://nsis.sourceforge.io/EnVar_plug-in
;      (place EnVar.dll in the NSIS Plugins\x86-unicode\ directory).
;
; Then from the installer\ directory:
;     makensis noosphere.nsi
;
; This installer adds the install directory to the system PATH via the
; EnVar plugin so users can invoke `noosphere` from any shell.

!include "MUI2.nsh"

Name "Noosphere"
OutFile "..\dist\Noosphere-Setup.exe"
InstallDir "$PROGRAMFILES64\Theseus\Noosphere"
InstallDirRegKey HKLM "Software\Theseus\Noosphere" "InstallDir"
RequestExecutionLevel admin

!define MUI_ICON "..\assets\noosphere.ico"
!define MUI_UNICON "..\assets\noosphere.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\noosphere\*.*"

  ; --- Add install dir to system PATH (EnVar plugin handles idempotency) ---
  EnVar::SetHKLM
  EnVar::AddValue "Path" "$INSTDIR"
  Pop $0
  DetailPrint "EnVar AddValue result: $0"

  ; --- Start Menu shortcut: open cmd in install dir ---
  CreateDirectory "$SMPROGRAMS\Theseus"
  CreateShortcut "$SMPROGRAMS\Theseus\Noosphere CLI.lnk" \
    "$SYSDIR\cmd.exe" \
    '/K "cd /d $INSTDIR && echo Noosphere CLI. Run noosphere --help to get started."' \
    "$INSTDIR\noosphere.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  WriteRegStr HKLM "Software\Theseus\Noosphere" "InstallDir" "$INSTDIR"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere" \
    "DisplayName" "Noosphere CLI"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere" \
    "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere" \
    "DisplayIcon" "$INSTDIR\noosphere.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere" \
    "Publisher" "Theseus"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere" \
    "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Theseus\Noosphere CLI.lnk"
  RMDir "$SMPROGRAMS\Theseus"

  ; --- Remove install dir from system PATH ---
  EnVar::SetHKLM
  EnVar::DeleteValue "Path" "$INSTDIR"
  Pop $0
  DetailPrint "EnVar DeleteValue result: $0"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKLM "Software\Theseus\Noosphere"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Noosphere"
SectionEnd
