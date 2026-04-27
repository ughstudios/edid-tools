@echo off
setlocal

set "APP_DIR=%~dp0"

if not exist "%APP_DIR%\edid_tools.py" (
    echo Could not find edid_tools.py in "%APP_DIR%".
    pause
    exit /b 1
)

pushd "%APP_DIR%" >nul

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 edid_tools.py gui
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python or add it to PATH.
        popd >nul
        pause
        exit /b 1
    )
    python edid_tools.py gui
)

set "EXIT_CODE=%errorlevel%"
popd >nul

if not "%EXIT_CODE%"=="0" (
    echo.
    echo EDID app exited with code %EXIT_CODE%.
    echo If the error says PySide6 is missing, run: pip install PySide6
    pause
)

exit /b %EXIT_CODE%
