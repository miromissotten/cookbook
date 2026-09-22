@echo off
cd /d "%~dp0."
echo running verify_pdf.py...
python verify_pdf.py > "%TEMP%\vp.txt" 2>&1
echo exitcode=%errorlevel% >> "%TEMP%\vp.txt"
