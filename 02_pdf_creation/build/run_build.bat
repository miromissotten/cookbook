@echo off
cd /d "%~dp0.."
echo building cookbook...
python main_generate_cookbook.py
echo exitcode=%errorlevel%
