@echo off
cd /d "%~dp0.."
echo building cookbook...
python 02_pdf_creation\main_generate_cookbook.py
echo exitcode=%errorlevel%
