@echo off
setlocal
cd /d "%~dp0"
if not exist ".build_tmp" mkdir ".build_tmp"
set "TMP=%CD%\.build_tmp"
set "TEMP=%CD%\.build_tmp"
set "PYINSTALLER_CONFIG_DIR=%CD%\.build_tmp\pyinstaller-cache"
set "STAGE=%CD%\build\portable-stage-%RANDOM%-%RANDOM%"
set "BASE_PYTHON=python"
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "BASE_PYTHON=py -3"

echo.
echo Building ISUZU_Offer_App portable Windows app...
echo.
echo Using Python:
%BASE_PYTHON% -c "import sys; print(sys.executable)"
echo.

if exist ".build_venv\Scripts\python.exe" (
    ".build_venv\Scripts\python.exe" -m pip --version >nul 2>nul
    if errorlevel 1 (
        echo Existing local build environment is incomplete. Repair it before building.
        pause
        exit /b 1
    )
)

if not exist ".build_venv\Scripts\python.exe" (
    echo Creating local build environment...
    %BASE_PYTHON% -m venv .build_venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create the local build environment.
        echo Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

".build_venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo ERROR: Could not update pip in the local build environment.
    pause
    exit /b 1
)

".build_venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

".build_venv\Scripts\python.exe" -m PyInstaller ISUZUOfferGenerator.spec --distpath "%STAGE%" --workpath "%STAGE%-work"
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed.
    echo Scroll up to see the real error message.
    pause
    exit /b 1
)

".build_venv\Scripts\python.exe" prepare_distribution.py "%STAGE%\ISUZU_Offer_App"
if errorlevel 1 (
    echo.
    echo ERROR: Package preparation failed.
    pause
    exit /b 1
)

if not exist "%STAGE%\ISUZU_Offer_App\ISUZU_Offer_App.exe" (
    echo.
    echo ERROR: Expected app was not created:
    echo %STAGE%\ISUZU_Offer_App\ISUZU_Offer_App.exe
    echo.
    echo Current dist folder contents:
    dir "%STAGE%" /b
    pause
    exit /b 1
)

echo.
echo Done.
echo Staged build; existing dist and user data were not overwritten.
echo Smoke-test this folder before promoting or distributing it:
echo %STAGE%\ISUZU_Offer_App
echo.
pause
