@echo off

SET VENV_DIR=sof-discord-venv
SET REQUIREMENTS_FILE=requirements.txt

echo Checking for Python 3...
where python >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not found in PATH. Please install Python 3 and add it to your PATH to continue.
    pause
    EXIT /B 1
)

echo Creating virtual environment in '%VENV_DIR%'...
python -m venv "%VENV_DIR%"

echo Activating virtual environment...
IF EXIST "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
) ELSE (
    echo Error: Could not find virtual environment activation script.
    pause
    EXIT /B 1
)

echo Installing dependencies from '%REQUIREMENTS_FILE%'...
IF EXIST "%REQUIREMENTS_FILE%" (
    pip install -r "%REQUIREMENTS_FILE%"
    echo Dependencies installed successfully.
) ELSE (
    echo Warning: '%REQUIREMENTS_FILE%' not found. No dependencies installed.
)

echo Virtual environment '%VENV_DIR%' is set up and dependencies are installed.
echo To activate it in the future, open a new command prompt in this directory and run: %VENV_DIR%\Scripts\activate.bat
echo To deactivate, run: deactivate
pause