@echo off
chcp 936 >nul 2>&1
title Novel Studio - 长篇小说创作工作台

cd /d "%~dp0"

echo ========================================================================
echo              Novel Studio 写作专家系统 · Windows 一键启动器
echo ========================================================================
echo.

:: ------------------------------------------------------------------------
:: 步骤 1：检测 8000 端口是否已被占用
:: ------------------------------------------------------------------------
set "PORT_PID="
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    set "PORT_PID=%%a"
)

if not defined PORT_PID goto CHECK_UV

echo [提示] 检测到端口 8000 当前已在运行中 (PID: %PORT_PID%)！
echo.
echo   [1] 直接在浏览器打开 Web 界面 (推荐，默认)
echo   [2] 强制重启后台服务
echo   [3] 彻底停止服务并退出
echo.
set "CHOICE=1"
set /p "CHOICE=请输入选项 [1/2/3] (直接回车默认选 1): "
if "%CHOICE%"=="1" (
    start http://127.0.0.1:8000
    exit /b 0
)
if "%CHOICE%"=="2" (
    echo 正在停止现有后台服务 (PID: %PORT_PID%)...
    taskkill /F /PID %PORT_PID% >nul 2>&1
    timeout /t 1 /nobreak >nul
    goto CHECK_UV
)
if "%CHOICE%"=="3" (
    echo 正在关闭服务 (PID: %PORT_PID%)...
    taskkill /F /PID %PORT_PID% >nul 2>&1
    echo [成功] 服务已关闭，文件占用与端口已全部释放。
    pause
    exit /b 0
)

:CHECK_UV
:: ------------------------------------------------------------------------
:: 步骤 2：自动检测或安装 uv 环境
:: ------------------------------------------------------------------------
set "PATH=%LOCALAPPDATA%\bin;%USERPROFILE%\.cargo\bin;%PATH%"

where uv >nul 2>&1
if %errorlevel% equ 0 goto SYNC_ENV

echo [1/3] 未检测到 uv 环境，正在为您自动下载安装官方 uv（极速轻量依赖管理器）...
echo 请保持网络畅通，约需几秒钟...
powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"

where uv >nul 2>&1
if %errorlevel% equ 0 goto SYNC_ENV

if exist "%LOCALAPPDATA%\bin\uv.exe" (
    set "PATH=%LOCALAPPDATA%\bin;%PATH%"
    goto SYNC_ENV
)
if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto SYNC_ENV
)

echo.
echo [错误] 自动安装 uv 失败，可能由于网络受限。
echo 请访问 https://github.com/astral-sh/uv 手动安装 uv 后重试。
echo.
pause
exit /b 1

:SYNC_ENV
:: ------------------------------------------------------------------------
:: 步骤 3：准备 Python 运行环境与依赖
:: ------------------------------------------------------------------------
echo [2/3] 正在检查并同步 Python 运行环境（首次运行约需 10-30 秒）...
uv sync --extra web
if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖环境同步失败，请检查网络连接后重试。
    pause
    exit /b 1
)

:: ------------------------------------------------------------------------
:: 步骤 4：启动服务
:: ------------------------------------------------------------------------
echo [3/3] 正在启动 Novel Studio 创作服务器...
echo.
echo ========================================================================
echo  【服务已就绪】正在自动在浏览器中打开: http://127.0.0.1:8000
echo.
echo  【如何关闭程序】
echo   - 直接关闭本终端黑框（点击右上角 [X]）即可彻底关闭整个程序！
echo   - 也可以在本窗口按 [Ctrl + C] 退出。
echo   - 端口 8000 与文件占用会随窗口关闭立刻释放，无任何后台残留。
echo ========================================================================
echo.

uv run na-studio
