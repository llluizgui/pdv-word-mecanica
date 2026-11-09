@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PDV Word Mecanica 1.8.1 - Abrir pelo codigo-fonte
echo =================================================
echo  PDV WORD MECANICA 1.8.1 - MODO DE TESTE
echo =================================================
echo.
echo Este metodo inicia o codigo Python local.
echo Nao instala o arquivo EXE, nao desativa antivirus
echo e nao altera as politicas do Windows.
echo.
if not exist "app.py" (
  echo ERRO: app.py nao encontrado.
  echo Extraia todo o ZIP do GitHub antes de iniciar.
  pause
  exit /b 1
)
where py >nul 2>&1
if errorlevel 1 (
  echo ERRO: Python nao encontrado.
  echo Instale Python 3.12 do site oficial python.org.
  pause
  exit /b 1
)
set "PYCMD=py -3.12"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 nao localizado. Tentando versao Python 3 padrao...
  set "PYCMD=py -3"
)
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente isolado de teste...
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo ERRO: nao foi possivel criar ambiente Python.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import tkinter; import reportlab; from PIL import Image" >nul 2>&1
if errorlevel 1 (
  echo Instalando as bibliotecas do aplicativo...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check "reportlab==4.4.9" "Pillow>=10,<13"
  if errorlevel 1 (
    echo ERRO: falha ao instalar as dependencias. Verifique sua conexao.
    pause
    exit /b 1
  )
)
echo.
echo Abrindo o PDV Word Mecanica...
".venv\Scripts\python.exe" "app.py"
if errorlevel 1 (
  echo.
  echo O PDV nao abriu. Copie o erro acima para diagnostico.
  pause
  exit /b 1
)
endlocal
