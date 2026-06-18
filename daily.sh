#!/bin/bash
# UH Analytics — daily auto-update on VPS
# Runs by cron at 10:00 UTC (12:00 Kyiv)
set -e
cd /home/uh/uh-analytics
LOG_DIR="/home/uh/uh-analytics/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_$(date +%Y-%m-%d).log"
{
echo "============================================================"
echo " RUN: $(date)"
echo "============================================================"
echo "[1/7] git sync..."
git stash || true
git pull --rebase || true
git stash pop || true
echo "  OK"
echo "[2/7] salesdrive_api --incremental --inc-days 3..."
./run.sh salesdrive_api.py --incremental --inc-days 3 || echo "  WARN: API failed, continuing"
echo "[3/7] fetch_data.py..."
./run.sh fetch_data.py
echo "  OK"
echo "[4/7] generate_dashboard.py (старий — місячний month.html + history)..."
./run.sh generate_dashboard.py || echo "  WARN: monthly gen failed, continuing"
echo "  OK"
echo "[5/7] НОВИЙ дашборд: dashboard_data.py + render_dashboard.py..."
./run.sh dashboard_data.py
./run.sh render_dashboard.py
cp docs/preview.html docs/index.html
echo "  OK новий дашборд -> docs/index.html"
echo "[6/7] git commit..."
git add docs/ history/
if git diff --cached --quiet; then
    echo "  SKIP no changes"
else
    git commit -m "Daily auto-report $(date +%Y-%m-%d)"
    echo "  OK committed"
fi
echo "[7/7] git push..."
git push
echo "  OK pushed"
echo "============================================================"
echo " SUCCESS: $(date)"
echo "============================================================"
} >> "$LOG" 2>&1
