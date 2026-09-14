@echo off
rem Clique duplo no Windows: instala o Goal Pacer desta pasta, ou atualiza a instalacao que ja existe para a versao
rem desta pasta, e abre o app. Deu certo: esta janela fecha sozinha; parou: a mensagem fica na tela.
rem Na primeira vez o Windows pode avisar que o arquivo veio da internet: "Mais informacoes" > "Executar assim mesmo".
rem O que roda e o scripts\instalar.py ao lado deste arquivo, com o Python 3.9+ do computador; sem Python, o winget
rem instala o Python 3.12 so para este usuario (sem administrador).
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
title Goal Pacer
echo Instalando o Goal Pacer...
echo.

if not exist "%~dp0scripts\instalar.py" goto dentro_do_zip
call :achar_python
if not defined PY call :python_pelo_winget
if not defined PY goto sem_python

"%PY%" "%~dp0scripts\instalar.py" --origem-padrao "%~dp0." --nao-interativo --instalar-ou-atualizar --abrir %*
if errorlevel 1 goto falhou
echo.
echo Pronto: o Goal Pacer abriu. Esta janela fecha sozinha.
timeout /t 5 >nul 2>nul
exit /b 0

:dentro_do_zip
echo Este arquivo foi aberto de dentro do zip, sem o resto da pasta.
echo Clique com o botao direito no zip, escolha "Extrair tudo" e abra o Instalar Goal Pacer.cmd da pasta extraida.
pause
exit /b 4

:falhou
echo.
echo A instalacao parou: a mensagem acima diz o que fazer. Depois, clique duas vezes neste arquivo outra vez.
pause
exit /b 1

:sem_python
echo.
echo Nao achei o Python 3.9 ou mais novo. Instale pelo python.org e clique duas vezes neste arquivo outra vez.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 4

:python_pelo_winget
where winget >nul 2>nul || exit /b 0
echo O Goal Pacer precisa do Python 3. Instalando o Python 3.12 pelo winget, so para este usuario...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :achar_python
exit /b 0

:achar_python
set "PY="
for %%v in (3.14 3.13 3.12 3.11 3.10 3.9) do if not defined PY for /f "delims=" %%p in ('py -%%v -c "import sys; print(sys.executable)" 2^>nul') do call :tentar "%%p"
for %%v in (314 313 312 311 310 39) do if not defined PY call :tentar "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
if not defined PY for /f "delims=" %%p in ('where python 2^>nul') do call :tentar "%%p"
exit /b 0

:tentar
if defined PY exit /b 0
if not exist "%~1" exit /b 0
echo "%~1" | find /i "\WindowsApps\" >nul && exit /b 0
"%~1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>nul && set "PY=%~1"
exit /b 0
