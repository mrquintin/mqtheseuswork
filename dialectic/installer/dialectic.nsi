; NSIS installer script for Dialectic.
;
; Build prerequisite: run scripts\build_windows.ps1 so dist\Dialectic\ exists.
; Then from the installer\ directory:
;     makensis dialectic.nsi

!include "MUI2.nsh"

Name "Dialectic"
OutFile "..\dist\Dialectic-Setup.exe"
InstallDir "$PROGRAMFILES64\Theseus\Dialectic"
InstallDirRegKey HKLM "Software\Theseus\Dialectic" "InstallDir"
RequestExecutionLevel admin

!define MUI_ICON "..\assets\dialectic.ico"
!define MUI_UNICON "..\assets\dialectic.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\Dialectic\*.*"

  CreateDirectory "$SMPROGRAMS\Theseus"
  CreateShortcut "$SMPROGRAMS\Theseus\Dialectic.lnk" "$INSTDIR\Dialectic.exe"
  CreateShortcut "$DESKTOP\Dialectic.lnk" "$INSTDIR\Dialectic.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  WriteRegStr HKLM "Software\Theseus\Dialectic" "InstallDir" "$INSTDIR"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic" \
    "DisplayName" "Dialectic"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic" \
    "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic" \
    "DisplayIcon" "$INSTDIR\Dialectic.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic" \
    "Publisher" "Theseus"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic" \
    "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Theseus\Dialectic.lnk"
  Delete "$DESKTOP\Dialectic.lnk"
  RMDir "$SMPROGRAMS\Theseus"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKLM "Software\Theseus\Dialectic"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dialectic"
SectionEnd
