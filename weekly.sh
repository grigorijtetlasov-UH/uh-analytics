#!/bin/bash
set -e
cd /home/uh/uh-analytics
LOG_DIR="/home/uh/uh-analytics/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/weekly_$(date +%Y-%m-%d).log"
MONTH=$(date +%Y-%m)
{
echo "=== WEEKLY RUN: $(date) | month=$MONTH ==="
echo "[1/2] git pull..."
git pull --rebase
echo "[2/2] salesdrive_api --month $MONTH..."
./run.sh salesdrive_api.py --month "$MONTH" || echo "WARN: full month failed"
echo "=== SUCCESS: $(date) ==="
} >> "$LOG" 2>&1
