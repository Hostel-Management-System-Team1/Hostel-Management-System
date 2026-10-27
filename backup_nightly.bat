@echo off
setlocal

set "PROJECT_DIR=C:\Users\VISHNU SR\Downloads\HMS-Team1"
set "BACKUP_DIR=C:\Users\VISHNU SR\Downloads\hms-backups"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

cd /d "%PROJECT_DIR%"
if errorlevel 1 exit /b 1

echo.>> "%BACKUP_DIR%\nightly-backup.log"
echo Backup started: %date% %time%>> "%BACKUP_DIR%\nightly-backup.log"

"%PROJECT_DIR%\.venv\Scripts\python.exe" "%PROJECT_DIR%\manage.py" backup_database >> "%BACKUP_DIR%\nightly-backup.log" 2>&1

if errorlevel 1 (
    echo Backup FAILED: %date% %time%>> "%BACKUP_DIR%\nightly-backup.log"
    exit /b 1
)

echo Backup completed: %date% %time%>> "%BACKUP_DIR%\nightly-backup.log"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$cutoff = (Get-Date).AddDays(-7); Get-ChildItem -LiteralPath '%BACKUP_DIR%' -Filter 'hms-*.dump' -File | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force"

if errorlevel 1 (
    echo WARNING: Backup succeeded but old-backup cleanup may have failed: %date% %time%>> "%BACKUP_DIR%\nightly-backup.log"
    exit /b 1
)

echo Backup cleanup completed: %date% %time%>> "%BACKUP_DIR%\nightly-backup.log"
exit /b 0