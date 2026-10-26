@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo  Python + Git + 패키지 자동 설치
echo ==========================================
echo.

rem ---- 1) Python 확인 ----
set "PY="
where python >nul 2>nul && python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul && set "PY=python"
if defined PY goto :have_python
where py >nul 2>nul && py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul && set "PY=py -3"

if defined PY goto :have_python

echo [1/3] Python 3.12 이상이 없어 설치합니다...
where winget >nul 2>nul
if errorlevel 1 goto :download_installer
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :download_installer
goto :after_install

:download_installer
echo winget을 사용할 수 없어 python.org에서 직접 내려받습니다...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
if not exist "%TEMP%\python-installer.exe" goto :download_fail
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%TEMP%\python-installer.exe" >nul 2>nul
goto :after_install

:download_fail
echo [오류] Python 설치 파일을 내려받지 못했습니다. 인터넷 연결을 확인하세요.
goto :fail

:after_install
rem 새로 설치된 Python 경로를 현재 창에 반영
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
where python >nul 2>nul && set "PY=python"
if defined PY goto :show_version
echo [오류] Python 설치 후에도 인식되지 않습니다. 이 창을 닫고 install.bat을 다시 실행하세요.
goto :fail

:have_python
echo [1/3] Python이 이미 설치되어 있습니다.

:show_version
%PY% --version
echo.

rem ---- 2) Git 확인 ----
where git >nul 2>nul
if not errorlevel 1 goto :have_git

echo [2/3] Git이 없어 설치합니다...
where winget >nul 2>nul
if errorlevel 1 goto :git_download
winget install -e --id Git.Git --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :git_download
goto :git_after_install

:git_download
echo winget을 사용할 수 없어 GitHub에서 직접 내려받습니다...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe' -OutFile '%TEMP%\git-installer.exe'"
if not exist "%TEMP%\git-installer.exe" goto :git_download_fail
"%TEMP%\git-installer.exe" /VERYSILENT /NORESTART /CURRENTUSER
del "%TEMP%\git-installer.exe" >nul 2>nul
goto :git_after_install

:git_download_fail
echo [오류] Git 설치 파일을 내려받지 못했습니다. 인터넷 연결을 확인하세요.
goto :fail

:git_after_install
set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%ProgramFiles%\Git\cmd;%PATH%"
where git >nul 2>nul
if not errorlevel 1 goto :show_git
echo [오류] Git 설치 후에도 인식되지 않습니다. 이 창을 닫고 install.bat을 다시 실행하세요.
goto :fail

:have_git
echo [2/3] Git이 이미 설치되어 있습니다.

:show_git
git --version
echo.

rem ---- 3) 패키지 설치 ----
echo [3/3] 패키지를 설치합니다: fastapi, uvicorn, python-multipart, jinja2, openpyxl, pandas, google-genai, streamlit, openai, filelock
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :pip_fail

echo.
echo ==========================================
echo  설치 완료!
echo ==========================================
pause
exit /b 0

:pip_fail
echo [오류] 패키지 설치에 실패했습니다.

:fail
echo.
echo 설치에 실패했습니다.
pause
exit /b 1
