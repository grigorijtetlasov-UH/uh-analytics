"""
finance/sync_finance.py — оркестратор фінансового синку.

Банк-адаптери → financial схема через finance.db.upsert.

Запуск:
  python -m finance.sync_finance --bank mono --days 31 --dry-run   # прев'ю, без запису
  python -m finance.sync_finance --bank mono --days 2              # інкремент (cron)
  python -m finance.sync_finance --full                            # повний з 2024-01-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from finance.db import upsert
from finance.db.connection import connect
from finance.banks.base import BankAdapter
from finance.banks.monobank import MonobankAdapter
from finance.banks.privatbank import PrivatBankAdapter
from finance.banks.novapay import NovaPayAdapter

CREDS_DIR = "~/finance/credentials"

# Реєстр адаптерів. privat/novapay додамо наступними файлами.
ADAPTERS: dict[str, type[BankAdapter]] = {
    "mono": MonobankAdapter,
    "privat": PrivatBankAdapter,
    "novapay": NovaPayAdapter,
}

log = logging.getLogger("finance.sync")


def sync_bank(adapter: BankAdapter, date_from: date, date_to: date,
              sync_mode: str, dry_run: bool) -> dict:
    bank = adapter.bank_code
    log.info("════ Синк банку '%s'  %s … %s  (%s%s) ════",
             bank, date_from, date_to, sync_mode, ", DRY-RUN" if dry_run else "")

    stats = {"merchants": 0, "accounts": 0, "inserted": 0, "skipped": 0, "errors": 0}
    log_id = upsert.start_sync_log(bank, sync_mode, date_from, date_to) if not dry_run else None

    try:
        adapter.load_credentials()
        accounts = adapter.fetch_accounts()
        log.info("[%s] отримано %d рахунків", bank, len(accounts))

        with connect() as conn, conn.cursor() as cur:
            # ── Фаза 1: довідники, баланси, own_ibans ──
            resolved = []                       # [(account, merchant_id, account_id), ...]
            merchants = set()
            for acc in accounts:
                mid = upsert.get_or_create_merchant(cur, bank, acc.external_id, acc.fio)
                aid = upsert.get_or_create_account(cur, mid, acc.iban, acc.currency)
                upsert.register_own_iban(cur, acc.iban, bank)
                if acc.balance is not None and not dry_run:
                    upsert.update_balance(cur, aid, acc.balance, datetime.now(timezone.utc))
                resolved.append((acc, mid, aid))
                merchants.add(mid)
            stats["merchants"], stats["accounts"] = len(merchants), len(resolved)
            conn.commit()

            own_ibans = upsert.load_own_ibans(cur)
            log.info("[%s] own_ibans у БД: %d", bank, len(own_ibans))

            # ── Фаза 2: транзакції (коміт після кожного рахунку) ──
            for acc, mid, aid in resolved:
                try:
                    txns = [t.to_upsert()
                            for t in adapter.fetch_transactions(acc, date_from, date_to)]
                except Exception as e:
                    log.error("[%s] fetch_transactions FAILED %s: %s", bank, acc.iban, e)
                    stats["errors"] += 1
                    continue
                if not txns:
                    continue
                if dry_run:
                    log.info("[%s][dry-run] %s: %d транзакцій (не пишемо)", bank, acc.iban, len(txns))
                    stats["inserted"] += len(txns)
                    continue
                res = upsert.insert_transactions(cur, bank, mid, aid, txns, own_ibans)
                conn.commit()
                stats["inserted"] += res["inserted"]
                stats["skipped"] += res["skipped"]
                log.info("[%s] %s: +%d нових, %d дублів",
                         bank, acc.iban, res["inserted"], res["skipped"])

        status = "success" if stats["errors"] == 0 else "partial"
        if not dry_run:
            upsert.finish_sync_log(log_id, status,
                                   merchants_total=stats["merchants"],
                                   merchants_ok=stats["merchants"],
                                   merchants_error=stats["errors"],
                                   txns_inserted=stats["inserted"])
        return {"bank": bank, "status": status, **stats}

    except Exception as e:
        log.exception("[%s] синк впав", bank)
        if not dry_run and log_id:
            upsert.finish_sync_log(log_id, "error", error_message=str(e)[:500])
        return {"bank": bank, "status": "error", "error": str(e), **stats}


def main():
    ap = argparse.ArgumentParser(description="UH Finance sync")
    ap.add_argument("--days", type=int, default=2,
                    help="скільки днів назад тягнути (default 2 — інкремент із запасом)")
    ap.add_argument("--full", action="store_true", help="повний синк з 2024-01-01")
    ap.add_argument("--bank", default="all", help="mono | privat | novapay | all")
    ap.add_argument("--dry-run", action="store_true", help="прев'ю без запису в БД")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    date_to = date.today()
    if args.full:
        date_from, sync_mode = date(2024, 1, 1), "full"
    else:
        date_from, sync_mode = date_to - timedelta(days=args.days), "incremental"

    banks = list(ADAPTERS) if args.bank == "all" else [args.bank]
    results = []
    for code in banks:
        cls = ADAPTERS.get(code)
        if cls is None:
            log.warning("Адаптер '%s' ще не реалізовано — пропускаю", code)
            continue
        results.append(sync_bank(cls(CREDS_DIR), date_from, date_to, sync_mode, args.dry_run))

    # ── Підсумок ──
    print("\n" + "═" * 56)
    print(f"📊 SYNC SUMMARY   {date_from} → {date_to}   (mode={sync_mode}"
          f"{', DRY-RUN' if args.dry_run else ''})")
    print("═" * 56)
    total = 0
    for r in results:
        icon = {"success": "✅", "partial": "🟡", "error": "🔴"}.get(r["status"], "❓")
        total += r.get("inserted", 0)
        line = (f"{icon} {r['bank']:8} | мерч {r.get('merchants',0):2} | "
                f"рах {r.get('accounts',0):2} | +{r.get('inserted',0)} нових "
                f"({r.get('skipped',0)} дублів)")
        if r.get("error"):
            line += f"  ⚠ {r['error'][:50]}"
        print(line)
    print("═" * 56)
    print(f"Разом нових транзакцій: {total}\n")

    # Telegram-алерт (модуль ще не створено — м'яко пропускаємо)
    try:
        from finance.alerts.telegram import notify_sync
        notify_sync(results, date_from, date_to, sync_mode)
    except Exception:
        pass

    if any(r["status"] == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
