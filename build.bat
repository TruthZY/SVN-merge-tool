@echo off
chcp 65001 >nul
echo ========================================
echo   SVN分支合并工具 - 打包脚本
echo ========================================
echo.

:: 检查 pyinstaller 是否已安装
where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到 PyInstaller，正在安装...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [错误] PyInstaller 安装失败，请手动执行: pip install pyinstaller
        pause
        exit /b 1
    )
)

echo [1/3] 清理旧的构建文件...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /q "*.spec"

echo [2/3] 开始打包...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "SVN分支合并工具" ^
    --add-data "data;data" ^
    --hidden-import "data" ^
    --hidden-import "data.interfaces" ^
    --hidden-import "data.merge_service" ^
    --hidden-import "data.svn_provider" ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败！请检查上方错误信息。
    pause
    exit /b 1
)

echo [3/3] 复制configs目录到输出目录...
if not exist "dist\configs" mkdir "dist\configs"
if exist "configs\*" (
    xcopy /s /y "configs\*" "dist\configs\" >nul
    echo   已复制现有配置文件到 dist\configs\
) else (
    echo   configs目录为空，将在首次运行时自动生成示例配置
)

echo.
echo ========================================
echo   打包完成！
echo   输出位置: dist\SVN分支合并工具.exe
echo   配置目录: dist\configs\
echo.
echo   使用方法:
echo     1. 将 dist 目录整体复制到目标机器
echo     2. 在 dist\configs\ 中放置你的配置JSON文件
echo     3. 双击运行 SVN分支合并工具.exe
echo ========================================
pause
