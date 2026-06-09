@echo off
REM ============================================================
REM  UH Analytics - daily dashboard update
REM  Run by Windows Task Scheduler at 15:00
REM  Or manually by double-click
REM ============================================================

REM Force Python to use UTF-8
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d D:\uh-analytics-NEW

REM API key ?????? SalesDrive
if exist .secrets\sd_api_key.txt (
    for /f "delims=" %%K in (.secrets\sd_api_key.txt) do set SD_API_KEY=%%K
)

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
echo [1/6] git pull...
git pull --rebase >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL git pull. See %LOG%
    goto :error
)
echo   OK

REM Step 2: SalesDrive API incremental
echo [2/6] python salesdrive_api.py --incremental...
python salesdrive_api.py --incremental --inc-days 14 >> %LOG% 2>&1
if errorlevel 1 (
    echo   WARN API incremental failed, continuing with cached data
    echo   WARN salesdrive_api.py failed, continuing >> %LOG%
) else (
    echo   OK
)

REM Step 3: fetch_data.py
echo [3/6] python fetch_data.py...
python fetch_data.py >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL fetch_data.py. See %LOG%
    goto :error
)
echo   OK

REM Step 4: generate_dashboard.py
echo [4/6] python generate_dashboard.py...
python generate_dashboard.py >> %LOG% 2>&1
if errorlevel 1 (
    echo   FAIL generate_dashboard.py. See %LOG%
    goto :error
)
echo   OK

REM Step 5: git add + commit
echo [5/6] git commit...
git add . >> %LOG% 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Daily auto-report %date:~6,4%-%date:~3,2%-%date:~0,2%" >> %LOG% 2>&1
    if errorlevel 1 (
        echo   FAIL git commit. See %LOG%
        goto :error
    )
    echo   OK committed
) else (
    echo   SKIP no changes to commit
    echo  No changes to commit >> %LOG%
    goto :done
)

REM Step 6: git push
echo [6/6] git push...
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
echo  Dashboard: https://unitedhome.digital/
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
