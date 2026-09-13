@echo off
rem Local launcher: double-click to start the web UI (opens browser automatically)
cd /d %~dp0
"D:\soft\conda\python.exe" -m streamlit run frontend/app.py --server.headless false
pause
