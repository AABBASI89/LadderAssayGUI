@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  LadderAssay GUI - Python environment setup
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.11 from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH", then re-run this file.
    pause
    exit /b 1
)

if not exist "ladderassay\Scripts\python.exe" (
    echo Creating virtual environment in ladderassay ...
    python -m venv ladderassay
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment ladderassay already exists - reusing it.
)

echo.
echo Installing Python packages ...
"ladderassay\Scripts\python.exe" -m pip install --upgrade pip
"ladderassay\Scripts\python.exe" -m pip install PyQt5 pyqtgraph numpy opencv-python pypylon pyfirmata
if errorlevel 1 (
    echo [ERROR] Package installation failed. See messages above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Python environment installed successfully.
echo ============================================================
echo.
echo  REMINDER - the following must be installed MANUALLY:
echo.
echo  1. Basler Pylon SDK (Pylon Camera Software Suite)
echo       https://www.baslerweb.com/en/downloads/software/
echo       Required by pypylon to talk to the Basler cameras.
echo       During setup, include the USB/GigE drivers as needed.
echo.
echo  2. Arduino IDE
echo       https://www.arduino.cc/en/software
echo.
echo  3. Firmata firmware on the Arduino board (needed by pyfirmata)
echo       Open Arduino IDE, then:
echo         File ^> Examples ^> Firmata ^> StandardFirmata
echo       Select your board and COM port, then click Upload.
echo       (The pyfirmata Python package was already installed above.)
echo.
echo  Close the Arduino IDE Serial Monitor before running the GUI,
echo  since it will hold the COM port.
echo ============================================================
echo.
echo To run the GUI:
echo     ladderassay\Scripts\python.exe main.py
echo.
pause
endlocal
