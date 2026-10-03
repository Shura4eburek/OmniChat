@echo off
rem OmniVoice installer: uv -> Python packages -> projects folder -> desktop shortcut -> UI.
rem The heavy parts (ffmpeg, the WSL training environment) are installed from the UI:
rem section "Ustanovka", button "Ustanovit zavisimosti".
rem Set OMNIVOICE_DRYRUN=1 to only print the commands (nothing is installed or launched).
rem echo keeps the previous errorlevel, so error checks after %RUN% commands are skipped in a dry run.
setlocal EnableExtensions
cd /d "%~dp0" || goto :fail_dir
set "TOOL_DIR=%~dp0"
if "%TOOL_DIR:~-1%"=="\" set "TOOL_DIR=%TOOL_DIR:~0,-1%"
set "PROJECTS=%USERPROFILE%\omnivoice-projects"
set "RUN="
if "%OMNIVOICE_DRYRUN%"=="1" set "RUN=echo [dry-run]"
if defined RUN echo DRY RUN: the commands are only printed, nothing is installed or launched.

echo.
echo === OmniVoice setup ===
echo Folder: %TOOL_DIR%
echo.

echo [1/5] Checking uv...
where uv >nul 2>nul
if not errorlevel 1 goto :have_uv
echo uv not found - installing it from https://astral.sh/uv ...
%RUN% powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
if not defined RUN if errorlevel 1 goto :fail_uv
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
:have_uv
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if defined RUN set "UV=uv"
if not defined UV goto :fail_uv
echo uv: %UV%

echo.
echo [2/5] Installing Python packages - uv sync, a few minutes the first time...
%RUN% "%UV%" sync --all-extras --inexact
if not defined RUN if errorlevel 1 goto :fail_sync

echo.
echo [3/5] Projects folder: %PROJECTS%
if not exist "%PROJECTS%\" %RUN% mkdir "%PROJECTS%"
if not defined RUN if errorlevel 1 goto :fail_dir

echo.
echo [4/5] Desktop shortcut OmniVoice...
set "OV_TARGET=%UV%"
set "OV_ARGS=run omnivoice ui --projects "%PROJECTS%""
set "OV_DIR=%TOOL_DIR%"
%RUN% powershell -NoProfile -ExecutionPolicy Bypass -c "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'OmniVoice.lnk')); $s.TargetPath=$env:OV_TARGET; $s.Arguments=$env:OV_ARGS; $s.WorkingDirectory=$env:OV_DIR; $s.Description='OmniVoice'; $s.Save()"
if not defined RUN if errorlevel 1 goto :fail_lnk

echo.
echo [5/5] Starting OmniVoice in the browser. Keep this window open while you work; close it to stop.
echo Next: open the section "Ustanovka" and press "Ustanovit zavisimosti".
%RUN% "%UV%" run omnivoice ui --projects "%PROJECTS%"
if not defined RUN if errorlevel 1 goto :fail_ui
exit /b 0

:fail_uv
echo.
echo ERROR: could not install uv automatically.
echo Install it by hand: https://docs.astral.sh/uv/getting-started/installation/
echo then run this file again.
goto :fail

:fail_sync
echo.
echo ERROR: "uv sync" failed - see the messages above.
echo Check the internet connection, close other OmniVoice windows and run this file again.
goto :fail

:fail_dir
echo.
echo ERROR: could not open the folder "%~dp0" or create "%PROJECTS%".
goto :fail

:fail_lnk
echo.
echo ERROR: could not create the desktop shortcut.
echo You can still start OmniVoice from this folder with: uv run omnivoice ui
goto :fail

:fail_ui
echo.
echo ERROR: OmniVoice stopped with an error - see the messages above.
goto :fail

:fail
echo.
pause
exit /b 1
