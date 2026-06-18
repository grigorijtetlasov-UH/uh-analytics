"""
PostgreSQL connection helper для financial schema.
Читає credentials з ~/uh-analytics/finance/.env
"""
import os
import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)

# Шлях до .env (на рівень вище від db/)
ENV_FILE = Path(__file__).parent.parent / ".env"


def _load_env() -> dict:
    """Простий парсер .env (без зовнішніх залежностей)."""
    config = {}
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"Не знайдено .env: {ENV_FILE}")
    
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def _get_config() -> dict:
    """Об'єднує .env з os.environ (env-vars мають пріоритет — для cron)."""
    config = _load_env()
    for key in ["FIN_DB_HOST", "FIN_DB_PORT", "FIN_DB_NAME",
                "FIN_DB_USER", "FIN_DB_PASSWORD"]:
        if key in os.environ:
            config[key] = os.environ[key]
    return config


@contextmanager
def connect():
    """
    Context manager для PostgreSQL з'єднання.
    
    Usage:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print(cur.fetchone())
    """
    config = _get_config()
    
    conn = psycopg2.connect(
        host=config["FIN_DB_HOST"],
        port=config.get("FIN_DB_PORT", "5432"),
        database=config["FIN_DB_NAME"],
        user=config["FIN_DB_USER"],
        password=config["FIN_DB_PASSWORD"],
        application_name="uh-finance-sync",
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def cursor(dict_cursor: bool = True):
    """
    Зручний shortcut: відкриває connection + cursor одним викликом.
    
    Usage:
        with cursor() as cur:
            cur.execute("SELECT * FROM financial.banks")
            for row in cur.fetchall():
                print(row['code'], row['name'])
    """
    with connect() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur
            conn.commit()


def test_connection() -> bool:
    """Швидкий тест: підключаємось і перевіряємо що бачимо financial схему."""
    try:
        with cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM financial.banks")
            result = cur.fetchone()
            log.info("DB connection OK — %d banks in financial schema", result["cnt"])
            return True
    except Exception as e:
        log.error("DB connection FAILED: %s", e)
        return False


if __name__ == "__main__":
    # Запуск як скрипт: python -m finance.db.connection
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if test_connection():
        print("\n✅ Connection works!")
    else:
        print("\n❌ Connection failed")
        exit(1)
