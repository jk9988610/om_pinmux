@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

@REM 可执行文件(Hex)文件名前缀
set HEX_NAME=SE71M

@REM 可执行文件(Hex)文件路径
set HEX_PATH=.\

@REM 可执行文件(Hex)输出文件路径
set OUTPUT_PATH=.\

@REM 软件版本文件路径
set VERSION_FILE_PATH=..\periph\user_config.h

@REM 定义需要提取的宏
set PROJECT_ID_H="#define iPROJECT_ID_H"
set PROJECT_ID_L="#define iPROJECT_ID_L"
set VERSION_ID_L="#define iREAL_VERSION_ID"
set CONSUMER_NAME="#define iCONSUMER_NAME"
set PROJECT_NAME="#define iPROJECT_NAME"

@REM 获取系统日期 - 使用完整4位年份
for /f "tokens=2 delims==" %%a in ('wmic OS get LocalDateTime /value') do set datetime=%%a
set YEAR=%datetime:~0,4%
set MONTH=%datetime:~4,2%
set DAY=%datetime:~6,2%
set CURRENT_DATE=%YEAR%%MONTH%%DAY%
echo 日期: %CURRENT_DATE%

@REM 从头文件提取产品ID、消费者名称、项目名称和版本信息
for /f "tokens=3 delims= " %%i in ('findstr /c:%PROJECT_ID_H% %VERSION_FILE_PATH%') do set ID_H=%%i
for /f "tokens=3 delims= " %%i in ('findstr /c:%PROJECT_ID_L% %VERSION_FILE_PATH%') do set ID_L=%%i
for /f "tokens=3 delims= " %%i in ('findstr /c:%CONSUMER_NAME% %VERSION_FILE_PATH%') do set CONSUMER=%%i
for /f "tokens=3 delims= " %%i in ('findstr /c:%PROJECT_NAME% %VERSION_FILE_PATH%') do set PROJ=%%i
for /f "tokens=3 delims= " %%i in ('findstr /c:%VERSION_ID_L% %VERSION_FILE_PATH%') do set VER=%%i

@REM 处理ID值（移除0x前缀并补零）
set ID_L=%ID_L:~2%
call :pad_zero ID_L 4

@REM 处理名称（去除引号）
set CONSUMER=%CONSUMER:~1,-1%
set PROJ=%PROJ:~1,-1%

echo 产品ID: %ID_L%
echo 消费者: %CONSUMER%
echo 项目名称: %PROJ%
echo 软件版本: V%VER%

@REM 验证源文件是否存在
set "SRC_FILE=%HEX_PATH%\%HEX_NAME%.bin"
if not exist "%SRC_FILE%" (
    echo 错误: 源文件 %SRC_FILE% 不存在!
    goto :eof
)

@REM 创建输出目录(如果不存在)
if not exist "%OUTPUT_PATH%" mkdir "%OUTPUT_PATH%"

@REM 临时复制文件用于MD5计算
set "TEMP_FILE=%OUTPUT_PATH%\temp_file.bin"
copy /b "%SRC_FILE%" "%TEMP_FILE%" > nul

echo 计算MD5校验码...

@REM 使用certutil计算MD5并保存到临时文件
certutil -hashfile "%TEMP_FILE%" MD5 > temp_md5.txt 2>nul

@REM 使用PowerShell提取MD5值
for /f "tokens=*" %%a in ('powershell -command "$content = Get-Content 'temp_md5.txt'; $md5 = $content | Where-Object { $_ -match '[0-9A-Fa-f]{32}' } | Select-Object -First 1; if ($md5) { [regex]::Match($md5, '[0-9A-Fa-f]{32}').Value } else { '' }"') do (
    set "md5=%%a"
)

@REM 清理临时文件
del "%TEMP_FILE%" temp_md5.txt > nul 2>&1

@REM 确保MD5值有效
if "!md5!"=="" (
    echo 错误: 无法获取有效的MD5值!
    goto :eof
)

@REM 转换为小写并提取最后4个字符(2字节)
set "md5=!md5:~0,32!"  REM 确保只取前32个字符
set "md5=!md5: =!"      REM 移除所有空格
set "md5=!md5:A=a!"    REM 转换为小写
set "md5=!md5:B=b!"
set "md5=!md5:C=c!"
set "md5=!md5:D=d!"
set "md5=!md5:E=e!"
set "md5=!md5:F=f!"
set "md5_tail=!md5:~-4!"  REM 只取最后4个字符
echo MD5: !md5!
echo 校验码: !md5_tail!

@REM 定制Hex文件名 - 格式: SE71M_001C_BYC_T9_20250516_V2_0B0E.bin
set "output_file_name=%HEX_NAME%_%ID_L%_%CONSUMER%_%PROJ%_V%VER%_%CURRENT_DATE%_!md5_tail!"
echo 输出文件名: !output_file_name!.bin

@REM 复制源文件到最终目标文件
set "DEST_FILE=%OUTPUT_PATH%\!output_file_name!.bin"
copy /b "%SRC_FILE%" "%DEST_FILE%" > nul

echo 完成! 输出文件: %DEST_FILE%
pause

goto :eof

:pad_zero 变量名 宽度
    set "var=!%~1!"
    set "pad=0000000000!var!"
    set "%~1=!pad:~-%~2!"
exit /b