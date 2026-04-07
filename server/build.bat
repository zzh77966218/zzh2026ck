@echo off
REM 远程控制服务器端 - Windows EXE 构建脚本

echo ========================================
echo   远程控制服务器 - 构建脚本
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 正在安装依赖...
pip install -r requirements.txt
pip install qrcode
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 创建图标目录
if not exist "assets" mkdir assets

REM 检查图标
set ICON_ARG=
if exist "assets\icon.ico" (
    set ICON_ARG=--icon assets\icon.ico
)

REM 构建EXE
echo.
echo [2/3] 正在构建EXE文件...
pyinstaller --onefile --windowed --name "RemoteControlServer" %ICON_ARG% --add-data ".;." server.py

if errorlevel 1 (
    echo [错误] 构建失败
    pause
    exit /b 1
)

REM 复制依赖文件
echo.
echo [3/3] 正在整理输出文件...
if not exist "dist" mkdir dist
if exist "build" rmdir /s /q build
if exist "RemoteControlServer.spec" del "RemoteControlServer.spec"
if exist "dist\RemoteControlServer.exe" (
    echo.
    echo ========================================
    echo   构建成功!
    echo   输出文件: dist\RemoteControlServer.exe
    echo ========================================
)

echo.
echo 按任意键退出...
pause >nul
