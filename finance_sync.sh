#!/usr/bin/env bash
set -uo pipefail
cd /home/uh/uh-analytics
echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) finance sync =====" >> finance/sync.log
venv/bin/python -m finance.sync_finance --days 3 >> finance/sync.log 2>&1

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) finance render =====" >> finance/sync.log
./run.sh render_finance.py >> finance/sync.log 2>&1
