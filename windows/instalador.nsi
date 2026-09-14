; Goal Pacer Setup.exe: instalação por usuário (sem administrador), gerada por dev/empacotar.py a partir deste modelo.
;
; Cada versão vai para a própria pasta ($INSTDIR\<versão>: python\ embutido e goal-pacer\ com o manifesto assinado), então
; o Setup da versão nova nunca sobrescreve o Python que o painel está usando. Depois de copiar, roda o instalador da
; versão (instalar.py --instalar-ou-atualizar --de-app): instala, ou atualiza a instalação que já existe conferindo o
; manifesto com a lista de assinantes dela. Registra a desinstalação em Configurações > Aplicativos.
;
; Valores trocados pelo empacotar: {{VERSAO}}, {{SAIDA}}, {{ARQUIVOS}} (o conteúdo da pasta da versão: python\ e
; goal-pacer\, com o separador do sistema que compila) e {{ICONE}}.

Unicode true
ManifestDPIAware true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define VERSAO "{{VERSAO}}"
!define CHAVE "Software\Microsoft\Windows\CurrentVersion\Uninstall\GoalPacer"

Name "Goal Pacer"
OutFile "{{SAIDA}}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\Goal Pacer"
SetCompressor /SOLID lzma
BrandingText "Goal Pacer ${VERSAO}"
ShowInstDetails show
ShowUninstDetails show

!define MUI_ICON "{{ICONE}}"
!define MUI_UNICON "{{ICONE}}"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION AbrirGoalPacer
!define MUI_FINISHPAGE_RUN_TEXT "$(abrir)"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "English"

LangString abrir ${LANG_PORTUGUESEBR} "Abrir o Goal Pacer"
LangString abrir ${LANG_ENGLISH} "Open Goal Pacer"
LangString preparando ${LANG_PORTUGUESEBR} "Preparando o Goal Pacer neste computador..."
LangString preparando ${LANG_ENGLISH} "Setting up Goal Pacer on this computer..."
LangString falhou ${LANG_PORTUGUESEBR} "A instalação parou. As linhas da lista dizem o motivo; depois de resolver, abra este instalador outra vez."
LangString falhou ${LANG_ENGLISH} "Setup stopped. The lines in the list say why; once it is fixed, open this installer again."
LangString removendo ${LANG_PORTUGUESEBR} "Removendo jobs, painel e atalhos. Suas metas ficam em .goal-pacer\dados."
LangString removendo ${LANG_ENGLISH} "Removing jobs, dashboard and shortcuts. Your goals stay in .goal-pacer\dados."

Section "Goal Pacer"
  SetOutPath "$INSTDIR\${VERSAO}"
  File /r "{{ARQUIVOS}}"
  SetOutPath "$INSTDIR"
  File "/oname=goal-pacer.ico" "{{ICONE}}"
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONUTF8", t "1")i'
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONIOENCODING", t "mbcs:replace")i'
  DetailPrint "$(preparando)"
  nsExec::ExecToLog '"$INSTDIR\${VERSAO}\python\python.exe" "$INSTDIR\${VERSAO}\goal-pacer\scripts\instalar.py" --origem-padrao "$INSTDIR\${VERSAO}\goal-pacer" --nao-interativo --instalar-ou-atualizar --de-app "$INSTDIR\${VERSAO}"'
  Pop $0
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP "$(falhou)"
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Desinstalar Goal Pacer.exe"
  WriteRegStr HKCU "${CHAVE}" "DisplayName" "Goal Pacer"
  WriteRegStr HKCU "${CHAVE}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "${CHAVE}" "Publisher" "Goal Pacer"
  WriteRegStr HKCU "${CHAVE}" "DisplayIcon" "$INSTDIR\goal-pacer.ico"
  WriteRegStr HKCU "${CHAVE}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE}" "UninstallString" '"$INSTDIR\Desinstalar Goal Pacer.exe"'
  WriteRegStr HKCU "${CHAVE}" "QuietUninstallString" '"$INSTDIR\Desinstalar Goal Pacer.exe" /S'
  WriteRegStr HKCU "${CHAVE}" "GoalPacerVersao" "${VERSAO}"
  WriteRegDWORD HKCU "${CHAVE}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE}" "NoRepair" 1
SectionEnd

Function AbrirGoalPacer
  ExecShell "open" "$SMPROGRAMS\Goal Pacer.lnk"
FunctionEnd

Section "Uninstall"
  ReadRegStr $1 HKCU "${CHAVE}" "GoalPacerVersao"
  DetailPrint "$(removendo)"
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONUTF8", t "1")i'
  System::Call 'Kernel32::SetEnvironmentVariable(t "PYTHONIOENCODING", t "mbcs:replace")i'
  nsExec::ExecToLog '"$INSTDIR\$1\python\python.exe" "$PROFILE\.goal-pacer\app\scripts\instalar.py" --uninstall --nao-interativo'
  Pop $0
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${CHAVE}"
SectionEnd
