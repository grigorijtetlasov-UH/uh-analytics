"""
finance/banks/privatbank.py
Адаптер PrivatBank ACP (Автоклієнт) → financial.transactions.

API:  https://acp.privatbank.ua/api/statements   (headers: id, token)
  • Виписка: /transactions?startDate=DD-MM-YYYY&endDate=DD-MM-YYYY (дати ЧЕРЕЗ ДЕФІС!)
  • acc необов'язковий — без нього віддає всі рахунки мерчанта; фільтруємо по AUT_MY_ACC.
  • Внутрішні перекази позначає upsert (counterpart_iban ∈ own_ibans), тут не рахуємо.
  • Жорсткого rate-limit немає. Довгі періоди ріжемо на вікна ≤90 днів.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import certifi
import requests

from finance.banks.base import Account, BankAdapter, Transaction

BASE_URL = "https://acp.privatbank.ua/api/statements"
KYIV = ZoneInfo("Europe/Kyiv")
CHUNK_DAYS = 90


class PrivatBankAdapter(BankAdapter):
    bank_code = "privat"

    def __init__(self, creds_dir, logger=None):
        super().__init__(creds_dir, logger)
        self._creds: list[tuple[str, str, str]] = []   # [(merchant_id, token, fio), ...]
        self._token_by_mid: dict[str, str] = {}
        self._txn_cache: dict[tuple, list[dict]] = {}   # (mid, from, to) -> транзакції (кеш на запуск)
        self.failed: list[tuple[str, str]] = []         # (merchant_id, error) — для звіту

    # ── credentials: merchant_id:token  # ФІО ──────────────────────
    def load_credentials(self) -> None:
        path = self.creds_dir / "privat_credentials.txt"
        if not path.exists():
            raise FileNotFoundError(f"Не знайдено {path}")
        creds = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            mid, rest = line.split(":", 1)
            parts = rest.split("#", 1)
            mid = mid.strip()
            token = parts[0].strip()
            fio = parts[1].strip() if len(parts) > 1 else mid[:8]
            if token:
                creds.append((mid, token, fio))
                self._token_by_mid[mid] = token
        if not creds:
            raise ValueError("privat_credentials.txt порожній / не розпарсився")
        self._creds = creds
        self.log.info("Завантажено %d PrivatBank мерчантів", len(creds))

    # ── HTTP з пагінацією ──────────────────────────────────────────
    def _headers(self, mid: str, token: str) -> dict:
        return {"id": mid, "token": token, "Content-Type": "application/json;charset=utf8"}

    def _get_paged(self, mid: str, token: str, path: str, params: dict, key: str) -> list[dict]:
        out, next_id = [], None
        while True:
            p = dict(params)
            if next_id:
                p["next_page_id"] = next_id
            r = requests.get(f"{BASE_URL}{path}", headers=self._headers(mid, token),
                             params=p, timeout=30, verify=certifi.where())
            r.raise_for_status()
            data = r.json()
            out.extend(data.get(key, []))
            if data.get("exist_next_page") == "True":
                next_id = data.get("next_page_id")
            else:
                break
        return out

    def _merchant_txns(self, mid: str, token: str,
                       date_from: date, date_to: date) -> list[dict]:
        """Усі транзакції мерчанта за період (вікнами ≤90 днів). Кеш на запуск."""
        key = (mid, date_from, date_to)
        if key in self._txn_cache:
            return self._txn_cache[key]
        out: list[dict] = []
        win = date_from
        while win <= date_to:
            chunk_to = min(win + timedelta(days=CHUNK_DAYS), date_to)
            out += self._get_paged(
                mid, token, "/transactions",
                {"startDate": win.strftime("%d-%m-%Y"),
                 "endDate": chunk_to.strftime("%d-%m-%Y"), "limit": 500},
                "transactions")
            win = chunk_to + timedelta(days=1)
        self._txn_cache[key] = out
        return out

    # ── accounts (balance/final, фолбек на транзакції) ─────────────
    def fetch_accounts(self) -> list[Account]:
        if not self._creds:
            self.load_credentials()
        win_to = date.today()
        win_from = win_to - timedelta(days=35)
        out: list[Account] = []
        for mid, token, fio in self._creds:
            try:
                balances = self._get_paged(
                    mid, token, "/balance/final",
                    {"startDate": win_from.strftime("%d.%m.%Y"),
                     "endDate": win_to.strftime("%d.%m.%Y"), "limit": 500},
                    "balances")
            except Exception as e:
                self.log.error("balance/final FAILED merchant %s…: %s", mid[:8], e)
                self.failed.append((mid, str(e)))
                continue

            bal_by_iban: dict[str, dict] = {}
            for b in balances:
                iban = b.get("acc") or ""
                if iban:
                    bal_by_iban[iban] = b

            # фолбек: рахунки з транзакцій, якщо балансів нема
            if not bal_by_iban:
                try:
                    for t in self._merchant_txns(mid, token, win_from, win_to):
                        iban = t.get("AUT_MY_ACC")
                        if iban:
                            bal_by_iban.setdefault(iban, {})
                except Exception as e:
                    self.log.error("transactions FAILED merchant %s…: %s", mid[:8], e)
                    self.failed.append((mid, str(e)))
                    continue

            for iban, b in bal_by_iban.items():
                bal = b.get("balanceOut")
                out.append(Account(
                    external_id=mid,
                    fio=fio,
                    iban=iban,
                    currency=b.get("currency", "UAH") or "UAH",
                    balance=Decimal(str(bal)) if bal not in (None, "") else None,
                    provider_account_id=iban,
                    raw=b,
                ))
            self.log.info("%s [%s…]: %d рахунків", fio, mid[:8], len(bal_by_iban))
        return out

    # ── transactions ───────────────────────────────────────────────
    @staticmethod
    def _parse_dt(t: dict) -> Optional[datetime]:
        raw = (t.get("DATE_TIME_DAT_OD_TIM_P") or "").strip()
        if raw:
            try:
                return datetime.strptime(raw, "%d.%m.%Y %H:%M:%S").replace(tzinfo=KYIV)
            except ValueError:
                pass
        dat = (t.get("DAT_OD") or "")[:10]
        if dat:
            try:
                return datetime.strptime(dat, "%d.%m.%Y").replace(tzinfo=KYIV)
            except ValueError:
                pass
        return None

    def fetch_transactions(self, account: Account,
                           date_from: date, date_to: date) -> Iterable[Transaction]:
        mid = account.external_id
        token = self._token_by_mid.get(mid)
        if token is None:
            raise ValueError(f"Немає токена для merchant {mid}")
        for t in self._merchant_txns(mid, token, date_from, date_to):
            if t.get("AUT_MY_ACC") != account.iban:
                continue
            dt = self._parse_dt(t)
            if dt is None:
                continue
            yield self._to_txn(t, account, dt)

    @staticmethod
    def _to_txn(t: dict, account: Account, dt: datetime) -> Transaction:
        amount = Decimal(str(t.get("SUM", "0") or "0"))
        if t.get("TRANTYPE") == "D":
            amount = -amount
        txn_id = (t.get("ID") or t.get("REF") or
                  f"{t.get('DAT_OD','')}|{t.get('NUM_DOC','')}|"
                  f"{t.get('SUM','')}|{t.get('AUT_CNTR_ACC','')}")
        return Transaction(
            bank_txn_id=str(txn_id),
            transaction_date=dt,
            amount=amount,
            description=t.get("OSND") or "",
            counterpart_iban=t.get("AUT_CNTR_ACC") or None,
            counterpart_name=t.get("AUT_CNTR_NAM") or None,
            currency=t.get("CCY", account.currency) or account.currency,
            raw_data=t,
        )


# ── self-test ──────────────────────────────────────────────────────
def _self_test(live: bool):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    creds_dir = Path("~/finance/credentials").expanduser()
    pb = PrivatBankAdapter(creds_dir)
    pb.load_credentials()
    print(f"\n✅ Мерчантів PrivatBank: {len(pb._creds)}")
    if not live:
        for mid, tok, fio in pb._creds:
            print(f"   • {fio:24} | id {mid[:8]}… | token …{tok[-4:]}")
        print("\n(offline. Для API: python -m finance.banks.privatbank --live)")
        return
    pb._creds = [next(c for c in pb._creds if "Баклан" in c[2])]
    accs = pb.fetch_accounts()
    print()
    for a in accs:
        print(f"   {a.fio} | {a.iban} | {a.currency} | balance={a.balance}")
    end, start = date.today(), date.today() - timedelta(days=31)
    for a in accs:
        n = 0
        rows = []
        for tx in pb.fetch_transactions(a, start, end):
            n += 1
            if n <= 5:
                rows.append(f"  {tx.transaction_date:%m-%d %H:%M} | {tx.amount:>12} {tx.direction} | "
                            f"{(tx.counterpart_name or '')[:18]:<18} | {tx.description[:28]}")
        if n:
            print(f"\n=== {a.iban} ({n} транз.) ===")
            print("\n".join(rows))


if __name__ == "__main__":
    import sys
    _self_test(live="--live" in sys.argv)
