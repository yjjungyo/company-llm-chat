@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -m venv .venv
    if errorlevel 1 (echo Python 3.10+ 설치를 확인하세요. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
python -m streamlit run app.py --server.port 8502
pause
