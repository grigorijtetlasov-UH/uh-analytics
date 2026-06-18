"""
finance/banks/novapay.py
Адаптер NovaPay Business API (SOAP/JWT) → financial.transactions.

Особливості NovaPay, враховані тут:
  • Авторизація UserAuthenticationJWT: refresh_token + login + public_certificate.
    refresh_token ОДНОРАЗОВИЙ — ротується при кожному вході. Новий зберігаємо в
    novapay_state.json ОДРАЗУ після успіху (інакше втратимо доступ).
  • Один логін → багато клієнтів (ФОП) → у кожного рахунки (IBAN).
  • GetPaymentsList повертає <payments> як вкладений html-escaped XML
    (<Payments><Docs .../></Payments>) → html.unescape + ElementTree.
  • <ID/> у Docs порожнє → bank_txn_id = хеш стабільних полів.
  • Напрям: PaymentType=Debit → витрата (−), Credit → прихід (+).
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

import certifi
import requests

from finance.banks.base import Account, BankAdapter, Transaction

try:
    from zoneinfo import ZoneInfo
    KYIV = ZoneInfo("Europe/Kyiv")
except Exception:
    KYIV = timezone(timedelta(hours=2))

ENDPOINT = "https://business.novapay.ua/Services/ClientAPIService.svc"
DEFAULT_LOGIN = "BaklanAYu"
ENVELOPE = ('<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:tem="http://tempuri.org/"><soap:Header/>'
            '<soap:Body>{body}</soap:Body></soap:Envelope>')


class NovaPayAdapter(BankAdapter):
    bank_code = "novapay"
    # Беремо лише проведені платежі (Conducted) — реальний рух коштів.
    COMPLETED_STATUSES = {"Conducted"}

    def __init__(self, creds_dir, logger=None, login: str = DEFAULT_LOGIN):
        super().__init__(creds_dir, logger)
        self.login = login
        self._state_path = self.creds_dir / "novapay_state.json"
        self._refresh_token: Optional[str] = None
        self._public_certificate: Optional[str] = None
        self._jwt: Optional[str] = None

    # ── credentials ────────────────────────────────────────────────
    def load_credentials(self) -> None:
        if not self._state_path.exists():
            raise FileNotFoundError(f"Не знайдено {self._state_path}")
        st = json.loads(self._state_path.read_text(encoding="utf-8"))
        self._refresh_token = st["refresh_token"]
        self._public_certificate = st["public_certificate"]

    # ── SOAP helper ────────────────────────────────────────────────
    def _call(self, action: str, body_inner: str) -> str:
        headers = {"Content-Type": "text/xml; charset=utf-8",
                   "SOAPAction": f"http://tempuri.org/IClientAPIService/{action}"}
        r = requests.post(ENDPOINT, data=ENVELOPE.format(body=body_inner).encode("utf-8"),
                          headers=headers, timeout=40, verify=certifi.where())
        r.raise_for_status()
        return r.text

    @staticmethod
    def _val(xml: str, tag: str, default: str = "") -> str:
        m = re.search(rf"<(?:[^>:]*:)?{re.escape(tag)}(?:\s[^>]*)?>([^<]*)</(?:[^>:]*:)?{re.escape(tag)}>",
                      xml, re.DOTALL)
        return m.group(1).strip() if m else default

    @staticmethod
    def _blocks(xml: str, tag: str) -> list[str]:
        return re.findall(rf"<(?:[^>:]*:)?{re.escape(tag)}(?:\s[^>]*)?>(.+?)</(?:[^>:]*:)?{re.escape(tag)}>",
                          xml, re.DOTALL)

    # ── auth (ротує токен, зберігає state) ─────────────────────────
    def _authenticate(self) -> None:
        if self._refresh_token is None:
            self.load_credentials()
        body = (f"<tem:UserAuthenticationJWT><tem:request>"
                f"<tem:refresh_token>{self._refresh_token}</tem:refresh_token>"
                f"<tem:login>{self.login}</tem:login>"
                f"<tem:public_certificate>{self._public_certificate}</tem:public_certificate>"
                f"</tem:request></tem:UserAuthenticationJWT>")
        raw = self._call("UserAuthenticationJWT", body)
        jwt = self._val(raw, "jwt")
        if not jwt:
            title = self._val(raw, "title") or self._val(raw, "ExceptionMessage")
            raise RuntimeError(f"NovaPay auth failed: {title or raw[:300]}")
        new_rt = self._val(raw, "refresh_token") or self._refresh_token
        new_pc = self._val(raw, "public_certificate") or self._public_certificate
        self._refresh_token, self._public_certificate = new_rt, new_pc
        self._state_path.write_text(
            json.dumps({"refresh_token": new_rt, "public_certificate": new_pc},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        self._jwt = jwt
        self.log.info("NovaPay: авторизовано, токен ротовано й збережено")

    # ── accounts ───────────────────────────────────────────────────
    def fetch_accounts(self) -> list[Account]:
        if not self._jwt:
            self._authenticate()
        raw = self._call("GetClientsList",
                         f"<tem:GetClientsList><tem:request><tem:jwt>{self._jwt}</tem:jwt>"
                         f"</tem:request></tem:GetClientsList>")
        clients = [(self._val(b, "id"), self._val(b, "name")) for b in self._blocks(raw, "Clients")]
        out: list[Account] = []
        for cid, name in clients:
            raw_a = self._call("GetAccountsList",
                              f"<tem:GetAccountsList><tem:request><tem:jwt>{self._jwt}</tem:jwt>"
                              f"<tem:client_id>{cid}</tem:client_id></tem:request></tem:GetAccountsList>")
            for b in self._blocks(raw_a, "Accounts"):
                out.append(Account(
                    external_id=cid,
                    fio=name,
                    iban=self._val(b, "IBAN"),
                    currency=self._val(b, "currency") or "UAH",
                    provider_account_id=self._val(b, "id"),
                    raw={"client_id": cid, "name": name},
                ))
        self.log.info("NovaPay: %d клієнтів, %d рахунків", len(clients), len(out))
        return out

    # ── transactions ───────────────────────────────────────────────
    def _parse_payments(self, raw_xml: str) -> list[dict]:
        m = re.search(r"<payments>(.*?)</payments>", raw_xml, re.DOTALL)
        if not m:
            return []
        inner = html.unescape(m.group(1)).strip()
        if not inner:
            return []
        try:
            root = ET.fromstring(inner)
        except ET.ParseError as e:
            self.log.warning("NovaPay payments XML parse error: %s", e)
            return []
        docs = []
        for d in root.findall("Docs"):
            docs.append({
                "amount": d.get("Amount"),
                "currency": d.get("CurrencyTag", "UAH"),
                "code": d.findtext("Code", ""),
                "org_date": d.findtext("OrgDate", ""),
                "day_date": d.findtext("DayDate", ""),
                "created": d.findtext("Created", ""),
                "payment_type": d.findtext("PaymentType", ""),
                "status": d.findtext("StatusDocument", ""),
                "purpose": d.findtext("Purpose", ""),
                "credit_name": d.findtext("CreditName", ""),
                "credit_iban": d.findtext("CreditCodeIBAN", ""),
                "debit_name": d.findtext("DebitName", ""),
                "debit_iban": d.findtext("DebitCodeIBAN", ""),
            })
        return docs

    @staticmethod
    def _parse_dt(s: str) -> Optional[datetime]:
        s = (s or "").strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=KYIV)
            except ValueError:
                continue
        return None

    @staticmethod
    def _txn_id(account_id: str, doc: dict) -> str:
        key = "|".join([account_id or "", doc.get("code") or "",
                        doc.get("created") or doc.get("day_date") or "",
                        doc.get("amount") or "", doc.get("credit_iban") or "",
                        doc.get("debit_iban") or "", doc.get("purpose") or ""])
        return "np-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]

    def _to_txn(self, account: Account, doc: dict) -> Optional[Transaction]:
        try:
            amt = Decimal((doc.get("amount") or "").replace(" ", ""))
        except (InvalidOperation, TypeError):
            return None
        dt = (self._parse_dt(doc.get("created")) or self._parse_dt(doc.get("day_date"))
              or self._parse_dt(doc.get("org_date")))
        if dt is None:
            return None
        if (doc.get("payment_type") or "").lower() == "debit":
            amount = -amt
            cp_name, cp_iban = doc.get("credit_name"), doc.get("credit_iban")
        else:
            amount = amt
            cp_name, cp_iban = doc.get("debit_name"), doc.get("debit_iban")
        return Transaction(
            bank_txn_id=self._txn_id(account.provider_account_id, doc),
            transaction_date=dt,
            amount=amount,
            description=doc.get("purpose") or "",
            counterpart_iban=cp_iban or None,
            counterpart_name=cp_name or None,
            currency=doc.get("currency") or account.currency,
            raw_data=doc,
        )

    def fetch_transactions(self, account: Account,
                           date_from: date, date_to: date) -> Iterable[Transaction]:
        if not self._jwt:
            self._authenticate()
        df, dt = date_from.strftime("%d.%m.%Y"), date_to.strftime("%d.%m.%Y")
        body = (f"<tem:GetPaymentsList><tem:request><tem:jwt>{self._jwt}</tem:jwt>"
                f"<tem:account_id>{account.provider_account_id}</tem:account_id>"
                f"<tem:date_from>{df}</tem:date_from><tem:date_to>{dt}</tem:date_to>"
                f"<tem:date_type>process</tem:date_type></tem:request></tem:GetPaymentsList>")
        for doc in self._parse_payments(self._call("GetPaymentsList", body)):
            if doc.get("status") not in self.COMPLETED_STATUSES:
                continue
            tx = self._to_txn(account, doc)
            if tx is not None:
                yield tx


# ── self-test ──────────────────────────────────────────────────────
def _self_test(live: bool):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    np = NovaPayAdapter(Path("~/finance/credentials").expanduser())
    np.load_credentials()
    print(f"\n✅ creds: токен ...{np._refresh_token[-6:]}, сертифікат {len(np._public_certificate)} симв")
    if not live:
        print("\n(offline. Для API: python -m finance.banks.novapay --live)")
        return
    print("\n🌐 LIVE: авторизація + клієнти/рахунки…")
    accs = np.fetch_accounts()
    print(f"   рахунків: {len(accs)}")
    for a in accs[:6]:
        print(f"   {a.fio[:30]:30} [{a.external_id}] | {a.iban} | acc_id={a.provider_account_id}")
    if not accs:
        return
    a0 = accs[0]
    end, start = date.today(), date.today() - timedelta(days=20)
    df, dt = start.strftime("%d.%m.%Y"), end.strftime("%d.%m.%Y")
    body = (f"<tem:GetPaymentsList><tem:request><tem:jwt>{np._jwt}</tem:jwt>"
            f"<tem:account_id>{a0.provider_account_id}</tem:account_id>"
            f"<tem:date_from>{df}</tem:date_from><tem:date_to>{dt}</tem:date_to>"
            f"<tem:date_type>process</tem:date_type></tem:request></tem:GetPaymentsList>")
    docs = np._parse_payments(np._call("GetPaymentsList", body))
    print(f"\n🌐 {a0.fio} {df}-{dt}: всього docs={len(docs)}")
    print("   СТАТУСИ:", dict(Counter(d['status'] for d in docs)))
    print("   PaymentType:", dict(Counter(d['payment_type'] for d in docs)))
    print("   суми (перші 8):", [d['amount'] for d in docs[:8]])
    txns = [t for d in docs if d.get("status") in np.COMPLETED_STATUSES and (t := np._to_txn(a0, d)) is not None]
    print(f"\n   зібрано транзакцій (усі docs): {len(txns)}")
    for tx in txns[:8]:
        print(f"   {tx.transaction_date:%Y-%m-%d %H:%M} | {tx.amount:>14} {tx.currency} | "
              f"{tx.direction} | {(tx.counterpart_name or '')[:22]:22} | {tx.description[:28]}")


if __name__ == "__main__":
    _self_test(live="--live" in sys.argv)
