@echo off
cd /d "%~dp0"

echo Starting the Python web server in a separate visible window...
start "Teams Captions Server" python .\teams_captions.py

echo Waiting 3 seconds for the server to fully start...
timeout /t 3 /nobreak >nul

echo Opening web interface...
start "" "http://localhost:5000/"

exit
