@echo off
cd /d "C:\miro\GoogleDrive\My Drive\06_foldersync\obsidian_miro\03_projects\kookboek"
start "cookbook-build" /b cmd /c "C:\Users\mirom\AppData\Local\Programs\Python\Python310\python.exe 02_pdf_creation\main_generate_cookbook.py --temp-dir exports/_temp > C:\Users\mirom\AppData\Local\Temp\cb_build.log 2>&1"
