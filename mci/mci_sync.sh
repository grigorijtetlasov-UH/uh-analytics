#!/usr/bin/env bash
set -uo pipefail
cd /home/uh/uh-analytics
echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) mci =====" >> mci/sync.log
venv/bin/python -m mci.main --notify >> mci/sync.log 2>&1
