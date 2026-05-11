@echo off
REM ============================================================
REM  UH Analytics - daily dashboard update
REM  Run by Windows Task Scheduler at 15:00
REM  Or manually by double-click
REM ============================================================

REM Force Python to use UTF-8 for stdout/stderr
REM (needed because Python's default encoding on Windows is cp1251
REM  which cannot handle emoji and Ukrainian characters in print)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d D:\uh-analytics-NEW

REM Log file with date
set LOG=logs\daily_%date:~6,4%-%date:~3,2%-%date:~0,2%.log
if not exist logs mkdir logs

echo. >> %LOG%
echo ============================================================ >> %LOG%
echo  RUN: %date% %time% >> %LOG%
echo ============================================================ >> %LOG%

echo.
echo ============================================================
echo  UH Analytics - Daily Update
echo  %date% %time%
echo ============================================================
echo.

REM Step 1: git pull
echo [1/5] git pull...
git pull --rebase >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL git pull. See %LOG%
    goto :error
)
echo   OK

REM Step 2: fetch_data.py (without arg = yesterday)
echo [2/5] python fetch_data.py...
python fetch_data.py >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL fetch_data.py. See %LOG%
    goto :error
)
echo   OK

REM Step 3: generate_dashboard.py
echo [3/5] python generate_dashboard.py...
python generate_dashboard.py >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL generate_dashboard.py. See %LOG%
    goto :error
)
echo   OK

REM Step 4: git add + commit (if changes)
echo [4/5] git commit...
git add . >> %LOG% 2>&1

REM Check if there are staged changes
git diff --cached --quiet
if errorlevel 1 (
    REM There are changes
    git commit -m "Daily auto-report %date:~6,4%-%date:~3,2%-%date:~0,2%" >> %LOG% 2>&1
    if errorlevel 1 (
        echo   FAIL git commit. See %LOG%
        goto :error
    )
    echo   OK committed
) else (
    REM No changes
    echo   SKIP no changes to commit
    echo  No changes to commit >> %LOG%
    goto :done
)

REM Step 5: git push
echo [5/5] git push...
git push >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL git push. See %LOG%
    goto :error
)
echo   OK pushed

:done
echo.
echo ============================================================
echo  SUCCESS: %date% %time%
echo ============================================================
echo  Log: %LOG%
echo  Dashboard: https://grigorijtetlasov-uh.github.io/uh-analytics/
echo ============================================================
echo  SUCCESS >> %LOG%
exit /b 0

:error
echo.
echo ============================================================
echo  ERROR: %date% %time%
echo ============================================================
echo  See log: %LOG%
echo ============================================================
echo  ERROR >> %LOG%
exit /b 1
