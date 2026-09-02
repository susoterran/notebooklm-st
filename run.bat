@echo off
chcp 65001 >nul
setlocal
title notebooklm-st
cd /d "%~dp0"

rem .ps1 은 더블클릭하면 편집기로 열린다. 이 래퍼가 run.ps1 을 실행 정책에
rem 걸리지 않게 띄우고, 서버가 뜨면 브라우저를 열어준다.

rem 주소·포트의 정본은 .streamlit\config.toml 이다.
set "ADDRESS=127.0.0.1"
set "PORT=8501"
if exist ".streamlit\config.toml" (
    for /f "tokens=2 delims== " %%a in ('findstr /r /c:"^ *address *=" ".streamlit\config.toml"') do set "ADDRESS=%%~a"
    for /f "tokens=2 delims== " %%a in ('findstr /r /c:"^ *port *=" ".streamlit\config.toml"') do set "PORT=%%~a"
)

rem config 가 headless 라 앱이 브라우저를 직접 열지 않는다. 포트가 열릴
rem 때까지 기다렸다가 기본 브라우저로 연다(최대 90초).
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "$end=(Get-Date).AddSeconds(90); while((Get-Date) -lt $end){ try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('%ADDRESS%',%PORT%); $c.Close(); Start-Process 'http://%ADDRESS%:%PORT%'; break }catch{ Start-Sleep -Milliseconds 500 } }"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
    echo.
    echo [!] 실행이 코드 %CODE% 로 끝났습니다. 위 메시지를 확인하세요.
    pause
)
exit /b %CODE%
