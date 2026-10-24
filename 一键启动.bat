@echo off
chcp 936 >nul 2>&1
title Novel Studio - 长篇小说创作工作台

cd /d "%~dp0"

echo ========================================================================
echo              Novel Studio 写作专家系统 · Windows 一键启动器
echo ========================================================================
echo.

:: ------------------------------------------------------------------------
:: 步骤 1：释放 8000 端口（自动清理先前可能残留的进程）
:: ------------------------------------------------------------------------
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [提示] 发现 8000 端口被占用 [PID: %%a]，正在自动重置释放...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

:: ------------------------------------------------------------------------
:: 步骤 2：自动检测或安装 uv 环境
:: ------------------------------------------------------------------------
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\bin;%USERPROFILE%\.cargo\bin;%PATH%"

where uv >nul 2>&1
if %errorlevel% equ 0 goto SYNC_ENV

echo [1/3] 未检测到 uv 环境，正在为您自动下载安装官方 uv（极速轻量依赖管理器）...
echo 请保持网络畅通，约需几秒钟...
powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"

where uv >nul 2>&1
if %errorlevel% equ 0 goto SYNC_ENV

if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    goto SYNC_ENV
)
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

if %errorlevel% neq 0 (
    echo.
    echo ========================================================================
    echo  [提示] 服务异常退出 [退出码: %errorlevel%]。
    echo ========================================================================
    pause
)
