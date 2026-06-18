#!/bin/bash
# UH Analytics — daily SalesDrive → PostgreSQL sync
# Запускається cron-ом щодня

set -e
cd /home/uh/uh-analytics

LOG_DIR="/home/uh/uh-analytics/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/db_sync_$(date +%Y-%m-%d).log"

{
echo "============================================================"
echo " DB SYNC: $(date)"
echo "============================================================"

# Інкремент — тягнемо все що змінювалось за останні 3 дні
# (бо статуси старих замовлень оновлюються коли вони доставляються)
./run.sh sync_salesdrive_db.py --incremental --days 3 || echo "  WARN: sync failed"

echo "============================================================"
echo " DONE: $(date)"
echo "============================================================"
} >> "$LOG" 2>&1
