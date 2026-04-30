@echo off
setlocal

cd /d "%~dp0"

echo Video Transcoder Tool Launcher
echo ==============================
echo Using Python Environment: D:\Anaconda3\python.exe
echo Starting the transcoder tool...
echo.

D:\Anaconda3\python.exe -X utf8 "Loudness-balance.py"

echo.
echo Program ended or closed
pause
