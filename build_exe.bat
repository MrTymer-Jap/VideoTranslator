@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building VideoTranslator.exe ...
python -m PyInstaller --noconfirm --clean VideoTranslator.spec
echo.
echo Done: dist\VideoTranslator.exe
pause
