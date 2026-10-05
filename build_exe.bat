@echo off
rem Windows .exe derler: dist\ROM-Sorter.exe  (pip install pyinstaller pillow)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --console --name ROM-Sorter ^
  --icon src\simge.ico --add-data "src\index.html;." --hidden-import PIL.Image src\sunucu.py
