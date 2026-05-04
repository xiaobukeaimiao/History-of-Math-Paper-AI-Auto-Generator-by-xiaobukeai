@echo off
chcp 65001 >nul

echo 正在开始打包...

pyinstaller --onefile ^
 --workpath "./build" ^
 --distpath ".." ^
 --specpath "." ^
 "..\AI Paper Generator.py"
echo 打包结束，正在清理中间文件...

if exist "build" rd /s /q "build"
if exist "AI Paper Generator.spec" del /q "AI Paper Generator.spec"

echo.
echo 打包完成！
pause