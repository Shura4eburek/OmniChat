@echo off
chcp 65001 >nul
rem OmniVoice installer: uv -> Python packages -> projects folder -> desktop shortcut -> UI.
rem UTF-8 without BOM, CRLF; chcp 65001 above makes cmd read the Russian lines below as UTF-8.
rem The heavy parts (ffmpeg, the WSL training environment) are installed from the UI:
rem section «Установка», button «Установить зависимости».
rem Set OMNIVOICE_DRYRUN=1 to only print the commands (nothing is installed or launched).
rem echo keeps the previous errorlevel, so error checks after %RUN% commands are skipped in a dry run.
setlocal EnableExtensions
pushd "%~dp0" || goto :fail_dir
set "TOOL_DIR=%~dp0"
if "%TOOL_DIR:~-1%"=="\" set "TOOL_DIR=%TOOL_DIR:~0,-1%"
set "PROJECTS=%USERPROFILE%\omnivoice-projects"
set "RUN="
if "%OMNIVOICE_DRYRUN%"=="1" set "RUN=echo [dry-run]"
if defined RUN echo ПРОБНЫЙ ЗАПУСК: команды только выводятся, ничего не устанавливается и не запускается.

echo.
echo === Установка OmniVoice ===
echo Папка: "%TOOL_DIR%"
echo.

echo [1/5] Проверяю uv...
where uv >nul 2>nul
if not errorlevel 1 goto :have_uv
echo uv не найден — устанавливаю его с https://astral.sh/uv ...
%RUN% powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
if not defined RUN if errorlevel 1 goto :fail_uv
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
:have_uv
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if defined RUN set "UV=uv"
if not defined UV goto :fail_uv
echo uv: "%UV%"

echo.
echo [2/5] Устанавливаю Python-пакеты: uv sync, в первый раз — несколько минут...
%RUN% "%UV%" sync --all-extras --inexact
if not defined RUN if errorlevel 1 goto :fail_sync

echo.
echo [3/5] Папка проектов: "%PROJECTS%"
if not exist "%PROJECTS%\" %RUN% mkdir "%PROJECTS%"
if not defined RUN if errorlevel 1 goto :fail_dir

echo.
echo [4/5] Создаю ярлык OmniVoice на рабочем столе...
set "OV_TARGET=%UV%"
set "OV_ARGS=run omnivoice ui --projects "%PROJECTS%""
set "OV_DIR=%TOOL_DIR%"
%RUN% powershell -NoProfile -ExecutionPolicy Bypass -c "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'OmniVoice.lnk')); $s.TargetPath=$env:OV_TARGET; $s.Arguments=$env:OV_ARGS; $s.WorkingDirectory=$env:OV_DIR; $s.Description='OmniVoice'; $s.Save()"
if not defined RUN if errorlevel 1 goto :fail_lnk

echo.
echo [5/5] Запускаю OmniVoice в браузере. Не закрывай это окно, пока работаешь; закрой его, чтобы остановить OmniVoice.
echo Дальше: открой раздел «Установка» и нажми «Установить зависимости».
%RUN% "%UV%" run omnivoice ui --projects "%PROJECTS%"
if not defined RUN if errorlevel 1 goto :fail_ui
exit /b 0

:fail_uv
echo.
echo ОШИБКА: не удалось установить uv автоматически.
echo Установи его вручную: https://docs.astral.sh/uv/getting-started/installation/
echo и запусти этот файл ещё раз.
goto :fail

:fail_sync
echo.
echo ОШИБКА: «uv sync» завершился с ошибкой — смотри сообщения выше.
echo Проверь подключение к интернету, закрой другие окна OmniVoice и запусти этот файл ещё раз.
goto :fail

:fail_dir
echo.
echo ОШИБКА: не удалось открыть папку "%~dp0" или создать папку "%PROJECTS%".
goto :fail

:fail_lnk
echo.
echo ОШИБКА: не удалось создать ярлык на рабочем столе.
echo OmniVoice можно запустить и из этой папки командой: uv run omnivoice ui
goto :fail

:fail_ui
echo.
echo ОШИБКА: OmniVoice остановился с ошибкой — смотри сообщения выше.
goto :fail

:fail
echo.
pause
exit /b 1
