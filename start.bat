@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (py -3 netdash.py %* & goto :end)
where python >nul 2>nul && (python netdash.py %* & goto :end)
echo Python 3 nie je nainstalovany. Stiahni ho z https://www.python.org/downloads/ (zaskrtni "Add python.exe to PATH").
:end
pause
