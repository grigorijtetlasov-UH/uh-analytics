"""
finance/banks/base.py
Базовий контракт для банк-адаптерів (Monobank, PrivatBank, NovaPay).
Адаптер віддає Account-и і Transaction-и у формі, яку розуміє
finance.db.upsert.insert_transactions(). У БД сам адаптер не пише.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class Account:
    """Один банківський рахунок (IBAN) одного ФОПа."""
    external_id: str                 # merchants.external_id (ФІО для mono, merchant_id для privat)
    fio: str                         # merchants.fio
    iban: str                        # bank_accounts.iban
    currency: str = "UAH"
    balance: Optional[Decimal] = None        # для update_balance()
    provider_account_id: Optional[str] = None  # id рахунку в API банку (для виписки)
    raw: dict = field(default_factory=dict)


@dataclass
class Transaction:
    """Транзакція у формі, готовій до insert_transactions()."""
    bank_txn_id: str
    transaction_date: datetime       # tz-aware
    amount: Decimal                  # зі знаком, грн (+ кредит / − дебет)
    description: str = ""
    counterpart_iban: Optional[str] = None
    counterpart_name: Optional[str] = None
    currency: str = "UAH"
    raw_data: dict = field(default_factory=dict)

    @property
    def direction(self) -> str:
        return "C" if self.amount >= 0 else "D"

    def to_upsert(self) -> dict:
        return {
            "bank_txn_id": self.bank_txn_id,
            "transaction_date": self.transaction_date,
            "amount": self.amount,
            "currency": self.currency,
            "direction": self.direction,
            "counterpart_iban": self.counterpart_iban,
            "counterpart_name": self.counterpart_name,
            "description": self.description,
            "raw_data": self.raw_data,
        }


class BankAdapter(ABC):
    """
    Базовий клас. Кожен банк реалізує:
      load_credentials() → fetch_accounts() → fetch_transactions().
    bank_code МАЄ збігатися з financial.banks.code ('privat'|'mono'|'novapay').
    """
    bank_code: str = "base"

    def __init__(self, creds_dir: str | Path, logger: logging.Logger | None = None):
        self.creds_dir = Path(creds_dir).expanduser()
        self.log = logger or logging.getLogger(f"finance.banks.{self.bank_code}")

    @abstractmethod
    def load_credentials(self) -> None:
        """Читає токени/ключі з self.creds_dir у пам'ять."""

    @abstractmethod
    def fetch_accounts(self) -> list[Account]:
        """Усі рахунки всіх ФОПів цього банку (+ баланси)."""

    @abstractmethod
    def fetch_transactions(self, account: Account,
                           date_from: date, date_to: date) -> Iterable[Transaction]:
        """Транзакції одного рахунку за період."""
