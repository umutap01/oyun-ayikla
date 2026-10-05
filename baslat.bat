@echo off
rem ROM Sorter / Oyun Ayikla - Windows
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul || (echo Python 3.10+ gerekli / required: https://www.python.org/downloads/ & pause & exit /b 1)
python -c "import PIL" 2>nul || python -m pip install -r requirements.txt
start "" http://127.0.0.1:8736
python src\sunucu.py %*
pause
