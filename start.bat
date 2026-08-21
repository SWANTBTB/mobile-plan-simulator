@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   料金シミュレーター 起動中...
echo   ブラウザで http://127.0.0.1:5000 を開いてください
echo   終了する場合は Ctrl+C を押してください
echo ========================================
echo.
"C:\Users\GUTITUBO-PC\AppData\Local\Python\pythoncore-3.14-64\python.exe" app.py
pause
