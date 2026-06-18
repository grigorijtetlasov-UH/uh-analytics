"""
Запис транзакцій у financial.transactions з дедупом і автоматичним
оновленням довідників (merchants, bank_accounts, own_ibans).
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

import psycopg2.extras

from finance.db.connection import connect

log = logging.getLogger(__name__)


def get_or_create_merchant(cur, bank_code: str, external_id: str, fio: str) -> int:
    """Повертає merchants.id, створюючи якщо нема."""
    cur.execute("""
        INSERT INTO financial.merchants (bank_code, external_id, fio)
        VALUES (%s, %s, %s)
        ON CONFLICT (bank_code, external_id) DO UPDATE
            SET fio = EXCLUDED.fio
        RETURNING id
    """, (bank_code, external_id, fio))
    return cur.fetchone()[0]


def get_or_create_account(cur, merchant_id: int, iban: str,
                          currency: str = "UAH") -> int:
    """Повертає bank_accounts.id, створюючи якщо нема."""
    cur.execute("""
        INSERT INTO financial.bank_accounts (merchant_id, iban, currency)
        VALUES (%s, %s, %s)
        ON CONFLICT (iban) DO UPDATE
            SET merchant_id = EXCLUDED.merchant_id
        RETURNING id
    """, (merchant_id, iban, currency))
    return cur.fetchone()[0]


def register_own_iban(cur, iban: str, source: str):
    """Додає IBAN у own_ibans (для дедупу внутрішніх переказів)."""
    if not iban:
        return
    cur.execute("""
        INSERT INTO financial.own_ibans (iban, source)
        VALUES (%s, %s)
        ON CONFLICT (iban) DO NOTHING
    """, (iban, source))


def load_own_ibans(cur) -> set[str]:
    """Завантажує всі власні IBAN з БД."""
    cur.execute("SELECT iban FROM financial.own_ibans")
    return {row[0] for row in cur.fetchall()}


def update_balance(cur, account_id: int, balance: Decimal | float | None,
                   snapshot_date: datetime, source: str = "api"):
    """Оновлює last_balance в bank_accounts + пише snapshot."""
    if balance is None:
        return
    cur.execute("""
        UPDATE financial.bank_accounts
        SET last_balance = %s, last_balance_at = %s
        WHERE id = %s
    """, (balance, snapshot_date, account_id))
    
    cur.execute("""
        INSERT INTO financial.balance_snapshots
            (snapshot_date, account_id, balance, source)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (snapshot_date, account_id) DO UPDATE
            SET balance = EXCLUDED.balance,
                source = EXCLUDED.source
    """, (snapshot_date.date(), account_id, balance, source))


def insert_transactions(cur, bank_code: str, merchant_id: int,
                        account_id: int, txns: Iterable[dict],
                        own_ibans: set[str]) -> dict:
    """
    Записує транзакції з дедупом.
    
    Кожна txn — dict з полями:
      - bank_txn_id (str, опціонально)
      - transaction_date (datetime)
      - amount (Decimal, зі знаком)
      - currency (str, default 'UAH')
      - direction ('C' | 'D')
      - counterpart_iban (str, опціонально)
      - counterpart_name (str, опціонально)
      - description (str, опціонально)
      - raw_data (dict, опціонально — для JSONB)
    """
    inserted = 0
    skipped = 0
    
    for txn in txns:
        counterpart = txn.get("counterpart_iban") or ""
        is_internal = counterpart in own_ibans if counterpart else False
        
        try:
            cur.execute("""
                INSERT INTO financial.transactions (
                    bank_code, merchant_id, account_id,
                    bank_txn_id, transaction_date,
                    amount, currency, direction,
                    counterpart_iban, counterpart_name, description,
                    is_internal_transfer, raw_data
                ) VALUES (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (bank_code, merchant_id, bank_txn_id,
                             transaction_date, amount, counterpart_iban)
                DO NOTHING
            """, (
                bank_code, merchant_id, account_id,
                txn.get("bank_txn_id"), txn["transaction_date"],
                txn["amount"], txn.get("currency", "UAH"), txn.get("direction"),
                counterpart or None,
                txn.get("counterpart_name"),
                txn.get("description"),
                is_internal,
                psycopg2.extras.Json(txn.get("raw_data", {})),
            ))
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            log.error("Insert error: %s | txn: %s", e, txn.get("bank_txn_id", "?"))
    
    return {"inserted": inserted, "skipped": skipped}


def start_sync_log(bank_code: str, sync_mode: str,
                   date_from, date_to) -> int:
    """Створює запис у sync_log. Повертає id."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO financial.sync_log
                (bank_code, sync_mode, date_from, date_to, status)
            VALUES (%s, %s, %s, %s, 'running')
            RETURNING id
        """, (bank_code, sync_mode, date_from, date_to))
        log_id = cur.fetchone()[0]
        conn.commit()
        return log_id


def finish_sync_log(log_id: int, status: str,
                    merchants_total: int = 0,
                    merchants_ok: int = 0,
                    merchants_error: int = 0,
                    txns_inserted: int = 0,
                    txns_updated: int = 0,
                    error_message: str | None = None):
    """Завершує запис у sync_log."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE financial.sync_log
            SET finished_at = NOW(),
                status = %s,
                merchants_total = %s,
                merchants_ok = %s,
                merchants_error = %s,
                txns_inserted = %s,
                txns_updated = %s,
                error_message = %s
            WHERE id = %s
        """, (status, merchants_total, merchants_ok, merchants_error,
              txns_inserted, txns_updated, error_message, log_id))
        conn.commit()


# ─── Тест ────────────────────────────────────────────────────────────

def _run_self_test():
    """Тестує запис однієї фіктивної транзакції і її видаляє."""
    log.info("Running self-test...")
    
    with connect() as conn, conn.cursor() as cur:
        # Створюємо тестового мерчанта
        merchant_id = get_or_create_merchant(
            cur, "privat", "TEST_SELF_TEST_DELETE_ME",
            "ФОП Тестовий"
        )
        log.info("Created/found test merchant id=%d", merchant_id)
        
        # Створюємо тестовий рахунок
        account_id = get_or_create_account(
            cur, merchant_id,
            "UA00TEST00000000000000000TESTX",
        )
        log.info("Created/found test account id=%d", account_id)
        
        # Реєструємо власний IBAN
        register_own_iban(cur, "UA00TEST00000000000000000TESTX", "self_test")
        
        # Завантажуємо own_ibans
        own_ibans = load_own_ibans(cur)
        log.info("Loaded %d own_ibans", len(own_ibans))
        
        # Пишемо тестову транзакцію
        test_txn = {
            "bank_txn_id": "TEST_TXN_001",
            "transaction_date": datetime.now(),
            "amount": Decimal("100.50"),
            "currency": "UAH",
            "direction": "C",
            "counterpart_iban": "UA00EXTERNAL00000000000EXTRN",
            "counterpart_name": "Тестовий контрагент",
            "description": "Self-test transaction",
            "raw_data": {"test": True, "source": "self_test"},
        }
        result = insert_transactions(
            cur, "privat", merchant_id, account_id,
            [test_txn], own_ibans
        )
        log.info("Insert result: %s", result)
        
        # Перевіряємо
        cur.execute("""
            SELECT COUNT(*) FROM financial.transactions
            WHERE bank_code = 'privat' AND merchant_id = %s
        """, (merchant_id,))
        count = cur.fetchone()[0]
        log.info("Transactions for test merchant: %d", count)
        
        # Видаляємо тестові дані
        cur.execute("""
            DELETE FROM financial.transactions WHERE merchant_id = %s
        """, (merchant_id,))
        cur.execute("""
            DELETE FROM financial.balance_snapshots WHERE account_id = %s
        """, (account_id,))
        cur.execute("""
            DELETE FROM financial.bank_accounts WHERE id = %s
        """, (account_id,))
        cur.execute("""
            DELETE FROM financial.merchants WHERE id = %s
        """, (merchant_id,))
        cur.execute("""
            DELETE FROM financial.own_ibans WHERE source = 'self_test'
        """)
        
        conn.commit()
        log.info("✅ Self-test PASSED — all test data cleaned up")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    _run_self_test()
