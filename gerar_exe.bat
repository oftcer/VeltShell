@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "WindowsVPS" --hidden-import=paramiko --collect-all paramiko windows_vps.py
copy /Y "dist\WindowsVPS.exe" "WindowsVPS.exe" >nul
echo OK: WindowsVPS.exe
