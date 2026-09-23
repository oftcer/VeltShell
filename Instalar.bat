@echo off
title VeltShell
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set "PY=py -3"
    ) else (
        echo Python nao encontrado. Instale Python 3.10+ e marque "Add to PATH".
        pause
        exit /b 1
    )
)

echo.
echo  Instalando o que o VeltShell precisa...
%PY% -m pip install "paramiko>=3.4.0"
if errorlevel 1 (
    echo Falha na instalacao.
    pause
    exit /b 1
)

if not exist "%~dp0ssh.txt" (
    if exist "%~dp0ssh.txt.example" copy /Y "%~dp0ssh.txt.example" "%~dp0ssh.txt" >nul
    echo.
    echo  Preencha ssh.txt com IP, usuario e senha. O bloco de notas vai abrir.
    notepad "%~dp0ssh.txt"
)

echo.
echo  Abrindo VeltShell...
%PY% "%~dp0windows_vps.py"
if errorlevel 1 pause
exit /b 0
