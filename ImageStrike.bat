@echo off
chcp 65001 >nul
title ImageStrike
cd /d "%~dp0"

set "APP=%~dp0ImageStrike.py"
set "PYEXE=%~dp0.venv\Scripts\python.exe"

echo ==========================================================================
echo  ImageStrike - CTF 图片隐写综合利用工具
echo ==========================================================================
echo.

rem ------------------------------------------------ 1) 准备依赖环境
where uv >nul 2>nul
if not errorlevel 1 (
    echo [*] 正在同步依赖 ^(首次运行需要联网下载^)...
    call uv sync --quiet
    if errorlevel 1 (
        echo [!] uv sync 失败，若已有可用的虚拟环境会继续尝试启动。
    )
)

if not exist "%PYEXE%" (
    echo [!] 没有找到虚拟环境：%PYEXE%
    echo.
    echo     请先安装 uv：https://docs.astral.sh/uv/
    echo     然后在当前目录执行一次：uv sync
    echo.
    pause
    exit /b 1
)

rem ------------------------------------------------ 2) 启动
rem  不带参数：打开图形界面
rem  带参数：透传给程序，等价于命令行模式，例如
rem      ImageStrike.bat --list
rem      ImageStrike.bat --cli 6 broken.png
"%PYEXE%" "%APP%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [!] 程序退出码 %RC%，按任意键关闭窗口。
    pause >nul
)

exit /b %RC%
