@echo off
setlocal

REM Check for virtual environment
IF NOT EXIST .venv (
    echo "Creating virtual environment..."
    py -m venv .venv
    IF %ERRORLEVEL% NEQ 0 (
        echo "Error creating virtual environment. Please ensure Python is installed and in your PATH."
        exit /b 1
    )
    
    REM Activate virtual environment and install dependencies
    echo "Activating virtual environment and installing dependencies..."
    call .venv\Scripts\activate.bat
    .venv/Scripts/pip install -r requirements.txt --prefer-binary
) ELSE (
    call .venv\Scripts\activate.bat
)


REM Check if the server is already running
tasklist /fi "imagename eq python.exe" /v | find "main.py" >nul
if %errorlevel% == 0 (
    echo "Server is already running."
) else (
    echo "Starting the Flask application..."
    start "ATP Port Setting EDB" /b .venv/Scripts/python src/main.py
)


REM Open the web browser
echo "Opening web browser..."
start http://127.0.0.1:5001/

endlocal
