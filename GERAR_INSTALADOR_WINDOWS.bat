@echo off
setlocal
cd /d "%~dp0"
echo === PDV Word Mecanica - Build Windows ===
where py >nul 2>&1
if errorlevel 1 (echo ERRO: Python nao encontrado no computador de compilacao. & pause & exit /b 1)
py -m venv .buildvenv
if errorlevel 1 (echo Falha ao criar ambiente. & pause & exit /b 1)
call .buildvenv\Scripts\activate.bat
python -m pip install --upgrade pip pyinstaller==6.16.0 reportlab==4.4.9
if errorlevel 1 (echo Falha ao instalar PyInstaller. & pause & exit /b 1)
pyinstaller --noconfirm --clean --windowed --onedir --name PDVWordMecanica app.py
if errorlevel 1 (echo Falha ao gerar executavel. & pause & exit /b 1)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo ERRO: Instale Inno Setup 6 para gerar o instalador. & pause & exit /b 1)
"%ISCC%" PDVWordMecanica.iss
if errorlevel 1 (echo Falha ao gerar instalador. & pause & exit /b 1)
echo.
echo Instalação pronta na pasta instalador.
pause
