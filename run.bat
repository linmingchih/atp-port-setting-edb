@echo off
setlocal

REM --- Paths ---
set "ROOT=%~dp0"
pushd "%ROOT%"
set "VENV_DIR=.venv"
set "VENV_PY=%ROOT%%VENV_DIR%\Scripts\python.exe"

REM --- Create venv if missing ---
if not exist "%VENV_PY%" (
    echo [INFO] Creating virtual environment...
    py -3 -m venv "%VENV_DIR%" 2>nul
    if not exist "%VENV_PY%" (
        echo [WARN] "py -3" failed or not found. Trying "python -m venv"...
        python -m venv "%VENV_DIR%"
    )
    if not exist "%VENV_PY%" (
        echo [ERROR] Failed to create venv. Ensure Python is installed and in PATH.
        popd
        pause
        exit /b 1
    )
)

REM --- Upgrade pip and install deps into the venv explicitly ---
if exist "requirements.txt" (
    echo [INFO] Upgrading pip...
    "%VENV_PY%" -m pip install --upgrade pip
    echo [INFO] Installing dependencies from requirements.txt...
    "%VENV_PY%" -m pip install -r requirements.txt --prefer-binary
) else (
    echo [WARN] requirements.txt not found. Installing Flask to proceed...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install flask
)

REM --- Verify Flask is importable before starting ---
echo [INFO] Verifying Flask installation...
"%VENV_PY%" -c "import flask,sys; print('Flask OK', flask.__version__, 'at', sys.executable)" || (
    echo [ERROR] Flask is not installed in the venv. Check requirements.txt or internet access.
    popd
    pause
    exit /b 1
)

REM --- Start app if not already running (by window title) ---
echo [INFO] Checking if server is already running...
tasklist /v /fi "imagename eq python.exe" | find /i "ATP Port Setting EDB" >nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Server is already running.
) else (
    echo [INFO] Starting the Flask application...
    if not exist "logs" mkdir "logs"
    start "ATP Port Setting EDB" cmd /c "\"%VENV_PY%\" -u src\main.py 1>>logs\server.log 2>>&1"
    timeout /t 3 /nobreak >nul
)

REM --- Open browser ---
echo [INFO] Opening web browser...
start "" http://127.0.0.1:5001/

popd
endlocal
pause
