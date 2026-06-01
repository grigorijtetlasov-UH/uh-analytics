#!/bin/bash
# Завантажує змінні з .env і запускає Python-команду
# Використання: ./run.sh fetch_data.py
#               ./run.sh salesdrive_api.py --incremental

set -e

cd "$(dirname "$0")"

# Завантажуємо .env (експортуємо всі змінні)
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "ERROR: .env not found"
    exit 1
fi

# Активуємо venv
source venv/bin/activate

# Запускаємо Python з аргументами
python "$@"
