@echo off
rem ROM Sorter / Oyun Ayikla - Windows (Python ile). Python istemiyorsan Releases'teki ROM-Sorter.exe'yi kullan.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
rem "py" (python.org kurulumu) once; "python" Microsoft Store kisayolu olabilir, gercekten calisiyor mu dene.
set PY=
py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY python -c "import sys" >nul 2>nul && set PY=python
if not defined PY (
  echo.
  echo   Python bulunamadi / Python not found.
  echo   Kur / Install: https://www.python.org/downloads/  ^(isaretle / tick "Add python.exe to PATH"^)
  echo   Ya da Python gerektirmeyen ROM-Sorter.exe: https://github.com/umutap01/oyun-ayikla/releases
  echo.
  pause & exit /b 1
)
%PY% -c "import PIL" 2>nul || %PY% -m pip install -r requirements.txt
start "" http://127.0.0.1:8736
%PY% src\sunucu.py %*
pause
