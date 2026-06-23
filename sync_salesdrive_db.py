#!/usr/bin/env python3
"""sync_salesdrive_db.py — SalesDrive → PostgreSQL (v2, реальні поля)"""
import os, sys, time, argparse, logging
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import Json
import requests

API_KEY  = os.getenv("SD_API_KEY")
BASE_URL = os.getenv("SD_BASE_URL", "https://matrasroll.salesdrive.me")
ENDPOINT = f"{BASE_URL}/api/order/list/"

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME", "salesdrive"),
    "user":     os.getenv("DB_USER", "sd_sync"),
    "password": os.getenv("DB_PASSWORD"),
}

PAGE_SIZE, RATE_LIMIT_S, RETRY_S, RETRY_MAX = 100, 40, 65, 5

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)


# ── API ─────────────────────────────────────────────────────────────────────
def _api_call(params):
    headers = {"Form-Api-Key": API_KEY, "Accept": "application/json"}
    for attempt in range(1, RETRY_MAX + 1):
        try:
            r = requests.get(ENDPOINT, headers=headers, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 429):
                if "API limit reached" in r.text[:200] or r.status_code == 429:
                    log.warning(f"  rate-limit ({attempt}/{RETRY_MAX}), wait {RETRY_S}s")
                    time.sleep(RETRY_S); continue
            r.raise_for_status()
        except (requests.ConnectionError, requests.Timeout) as e:
            log.warning(f"  network err ({attempt}/{RETRY_MAX}): {e}")
            time.sleep(RETRY_S)
    raise RuntimeError(f"Failed after {RETRY_MAX} attempts")


def fetch_orders(date_from, date_to, filter_by="orderTime"):
    log.info(f"SalesDrive: {date_from} -> {date_to} (by {filter_by})")
    all_orders, page = [], 1
    while True:
        params = {
            "page": page, "limit": PAGE_SIZE,
            f"filter[{filter_by}][from]": date_from,
            f"filter[{filter_by}][to]":   date_to,
        }
        data = _api_call(params)
        items = data.get("data") or []
        if not items: break
        all_orders.extend(items)
        log.info(f"  page {page}: {len(items)} (total {len(all_orders)})")
        if len(items) < PAGE_SIZE: break
        page += 1
        time.sleep(RATE_LIMIT_S)
    log.info(f"Total: {len(all_orders)}")
    return all_orders


# ── Парсинг — справжні поля SalesDrive ──────────────────────────────────────
DELIVERY_MARKERS = ["оплата послуги доставка", "доставка нова пошта",
                    "доставка укрпошта", "доставка justin"]

def _is_delivery(n): return any(m in (n or "").lower() for m in DELIVERY_MARKERS)
def _is_warranty(n): return "гарант" in (n or "").lower()
def _is_cover(n):    return any(m in (n or "").lower() for m in ["чохол", "наматрацник"])

def _parse_dt(s):
    if not s: return None
    if isinstance(s, str):
        s = s.replace("Z", "+00:00")
        # SalesDrive іноді віддає "2026-06-01 23:48:33" без T
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        try: return datetime.fromisoformat(s)
        except: return None
    return None

def _to_int(v):
    if v in (None, ""): return None
    try: return int(v)
    except: return None

def _to_dec(v):
    if v in (None, ""): return None
    try: return float(v)
    except: return None


def parse_order(raw):
    """SalesDrive JSON → row для orders. Реальні ключі."""
    # Контакт — масив, беремо першого
    contacts = raw.get("contacts") or []
    primary = contacts[0] if contacts else {}
    
    # Phone — теж масив
    phones = primary.get("phone") or []
    phone = phones[0] if phones else None
    
    # ПІБ з трьох полів
    fname = primary.get("fName") or ""
    lname = primary.get("lName") or ""
    mname = primary.get("mName") or ""
    full_name = " ".join(p for p in [lname, fname, mname] if p).strip() or None
    
    # Email — теж масив
    emails = primary.get("email") or []
    email = emails[0] if emails else None
    
    return {
        "id":              raw.get("id"),
        "order_id_1c":     raw.get("nomer1S"),
        "nomer_1s":        raw.get("nomer1S"),
        "external_id":     raw.get("externalId"),
        "status_id":       _to_int(raw.get("statusId")),
        "status_name":     None,  # довідник окремо
        
        "site_id":         _to_int(raw.get("sajt")),
        "site_name":       None,  # довідник окремо
        
        "manager_id":      _to_int(raw.get("userId")),
        "manager_name":    None,  # довідник окремо
        
        "form_id":         _to_int(raw.get("formId")),
        "organization_id": _to_int(raw.get("organizationId")),
        
        "customer_id":     str(primary.get("id")) if primary.get("id") else None,
        "customer_name":   full_name,
        "customer_phone":  phone,
        "customer_email":  email,
        
        "order_time":      _parse_dt(raw.get("orderTime")),
        "update_at":       _parse_dt(raw.get("updateAt")),
        "payment_date":    _parse_dt(raw.get("paymentDate")),
        "holder_time":     _parse_dt(raw.get("holderTime")),
        "time_entry_order": _parse_dt(raw.get("timeEntryOrder")),
        
        # Фінанси (повний набір)
        "total_amount":       _to_dec(raw.get("paymentAmount")),
        "payed_amount":       _to_dec(raw.get("payedAmount")),
        "rest_pay":           _to_dec(raw.get("restPay")),
        "discount_amount":    _to_dec(raw.get("discountAmount")),
        "cost_price_amount":  _to_dec(raw.get("costPriceAmount")),
        "expenses_amount":    _to_dec(raw.get("expensesAmount")),
        "profit_amount":      _to_dec(raw.get("profitAmount")),
        "commission_amount":  _to_dec(raw.get("commissionAmount")),
        "shipping_costs":     _to_dec(raw.get("shipping_costs")),
        
        # delivery_amount залишаємо як alias до shipping_costs
        "delivery_amount":    _to_dec(raw.get("shipping_costs")),
        "items_amount":       None,  # buduemo з products нижче
        
        "payment_method_id":    _to_int(raw.get("payment_method")),
        "payment_method_name":  None,
        "delivery_type_id":     None,
        "delivery_type_name":   None,
        "shipping_method":      _to_int(raw.get("shipping_method")),
        
        "category_ids":       None,
        "request_type_id":    _to_int(raw.get("typeId")),
        
        # UTM
        "utm_source":      raw.get("utmSource"),
        "utm_medium":      raw.get("utmMedium"),
        "utm_campaign":    raw.get("utmCampaign"),
        "utm_content":     raw.get("utmContent"),
        "utm_term":        raw.get("utmTerm"),
        "utm_source_full": raw.get("utmSourceFull"),
        
        # Адреса
        "oblast":              raw.get("oblast"),
        "rajon":               raw.get("rajon"),
        "naselenij_punkt":     raw.get("naselenijPunkt"),
        "vul_ta_no_viddilenna": raw.get("vulTaNoViddilenna"),
        
        # Причини
        "rejection_reason":      raw.get("rejectionReason"),
        "pricina_vidmovi":       raw.get("pricinaVidmovi"),
        "pricina_obrobki":       raw.get("pricinaObrobki"),
        "problemne_zaperechenna": raw.get("problemneZaperecenna"),
        "osibka_menedzera":      raw.get("osibkaMenedzera"),
        
        # Категорія
        "kategoria_zvernenna":   raw.get("kategoriaZvernenna"),
        "menedzer_na_magazini":  raw.get("menedzerNaMagazini"),
        
        # Кампанія
        "campaign_id":           str(raw.get("campaignId")) if raw.get("campaignId") else None,
        "tip_stvorenna_zaavki":  raw.get("tipStvorennaZaavki"),
        
        "comment":          raw.get("comment"),
        "items_count":      len(raw.get("products") or []),
    }


def parse_items(raw):
    """products[].text — справжнє поле з назвою товару."""
    order_id = raw.get("id")
    out = []
    for prod in (raw.get("products") or []):
        # КЛЮЧОВЕ: поле зветься 'text', а не 'name'
        name = prod.get("text") or prod.get("documentName") or ""
        out.append({
            "order_id":     order_id,
            "product_id":   str(prod.get("productId") or ""),
            "product_name": name,
            "sku":          prod.get("sku") or prod.get("parameter"),
            "quantity":     _to_dec(prod.get("amount")) or 1,
            "price":        _to_dec(prod.get("price")),
            "discount":     _to_dec(prod.get("discount")) or 0,
            "is_delivery":  _is_delivery(name),
            "is_warranty":  _is_warranty(name),
            "is_cover":     _is_cover(name),
            "category_id":   None,  # в products нема category_id напряму
            "category_name": prod.get("manufacturer"),  # вирубник як категорія
        })
    return out


# ── DB ──────────────────────────────────────────────────────────────────────
def upsert_dicts(conn, orders):
    """Заповнюємо довідники sites/managers/statuses ID-ами що зустрілись."""
    sites = set()
    managers = set()
    statuses = set()
    for o in orders:
        if o.get("sajt"):    sites.add(int(o["sajt"]))
        if o.get("userId"):  managers.add(int(o["userId"]))
        if o.get("statusId"): statuses.add(int(o["statusId"]))
    
    with conn.cursor() as cur:
        for sid in sites:
            cur.execute("""INSERT INTO sites (id, last_seen) VALUES (%s, NOW())
                ON CONFLICT (id) DO UPDATE SET last_seen = NOW()""", (sid,))
        for mid in managers:
            cur.execute("""INSERT INTO managers (id, last_seen) VALUES (%s, NOW())
                ON CONFLICT (id) DO UPDATE SET last_seen = NOW()""", (mid,))
        for stid in statuses:
            cur.execute("""INSERT INTO statuses (id, last_seen) VALUES (%s, NOW())
                ON CONFLICT (id) DO UPDATE SET last_seen = NOW()""", (stid,))
    conn.commit()


def upsert_batch(conn, orders):
    if not orders: return 0, 0, 0
    inserted = updated = items_total = 0
    
    upsert_dicts(conn, orders)
    
    with conn.cursor() as cur:
        # orders_raw
        raw_rows = [(o["id"], Json(o)) for o in orders if o.get("id")]
        cur.executemany("""
            INSERT INTO orders_raw (id, data, synced_at) VALUES (%s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, synced_at = NOW()
        """, raw_rows)
        
        # orders
        for po in [parse_order(o) for o in orders if o.get("id")]:
            cur.execute("""
                INSERT INTO orders (
                    id, order_id_1c, nomer_1s, external_id, status_id,
                    site_id, manager_id, form_id, organization_id,
                    customer_id, customer_name, customer_phone, customer_email,
                    order_time, update_at, payment_date, holder_time, time_entry_order,
                    total_amount, payed_amount, rest_pay, discount_amount,
                    cost_price_amount, expenses_amount, profit_amount, commission_amount,
                    shipping_costs, delivery_amount, items_amount,
                    payment_method_id, shipping_method,
                    category_ids, request_type_id,
                    utm_source, utm_medium, utm_campaign, utm_content, utm_term, utm_source_full,
                    oblast, rajon, naselenij_punkt, vul_ta_no_viddilenna,
                    rejection_reason, pricina_vidmovi, pricina_obrobki,
                    problemne_zaperechenna, osibka_menedzera,
                    kategoria_zvernenna, menedzer_na_magazini,
                    campaign_id, tip_stvorenna_zaavki, items_count, comment, synced_at
                ) VALUES (
                    %(id)s, %(order_id_1c)s, %(nomer_1s)s, %(external_id)s, %(status_id)s,
                    %(site_id)s, %(manager_id)s, %(form_id)s, %(organization_id)s,
                    %(customer_id)s, %(customer_name)s, %(customer_phone)s, %(customer_email)s,
                    %(order_time)s, %(update_at)s, %(payment_date)s, %(holder_time)s, %(time_entry_order)s,
                    %(total_amount)s, %(payed_amount)s, %(rest_pay)s, %(discount_amount)s,
                    %(cost_price_amount)s, %(expenses_amount)s, %(profit_amount)s, %(commission_amount)s,
                    %(shipping_costs)s, %(delivery_amount)s, %(items_amount)s,
                    %(payment_method_id)s, %(shipping_method)s,
                    %(category_ids)s, %(request_type_id)s,
                    %(utm_source)s, %(utm_medium)s, %(utm_campaign)s, %(utm_content)s, %(utm_term)s, %(utm_source_full)s,
                    %(oblast)s, %(rajon)s, %(naselenij_punkt)s, %(vul_ta_no_viddilenna)s,
                    %(rejection_reason)s, %(pricina_vidmovi)s, %(pricina_obrobki)s,
                    %(problemne_zaperechenna)s, %(osibka_menedzera)s,
                    %(kategoria_zvernenna)s, %(menedzer_na_magazini)s,
                    %(campaign_id)s, %(tip_stvorenna_zaavki)s, %(items_count)s, %(comment)s, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    status_id=EXCLUDED.status_id, manager_id=EXCLUDED.manager_id,
                    update_at=EXCLUDED.update_at, payment_date=EXCLUDED.payment_date,
                    total_amount=EXCLUDED.total_amount, payed_amount=EXCLUDED.payed_amount,
                    rest_pay=EXCLUDED.rest_pay, profit_amount=EXCLUDED.profit_amount,
                    rejection_reason=EXCLUDED.rejection_reason,
                    comment=EXCLUDED.comment,
                    items_count=EXCLUDED.items_count, synced_at=NOW()
                RETURNING (xmax = 0) AS inserted
            """, po)
            row = cur.fetchone()
            if row and row[0]: inserted += 1
            else: updated += 1
        
        # order_items: видалити старі для цих замовлень, потім вставити нові
        order_ids = [o["id"] for o in orders if o.get("id")]
        cur.execute("DELETE FROM order_items WHERE order_id = ANY(%s)", (order_ids,))
        all_items = [it for o in orders for it in parse_items(o)]
        if all_items:
            cur.executemany("""
                INSERT INTO order_items (
                    order_id, product_id, product_name, sku,
                    quantity, price, discount, is_delivery, is_warranty, is_cover,
                    category_id, category_name
                ) VALUES (
                    %(order_id)s, %(product_id)s, %(product_name)s, %(sku)s,
                    %(quantity)s, %(price)s, %(discount)s, %(is_delivery)s, %(is_warranty)s, %(is_cover)s,
                    %(category_id)s, %(category_name)s
                )
            """, all_items)
            items_total = len(all_items)
    
    conn.commit()
    return inserted, updated, items_total


def log_start(conn, mode, df, dt):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO sync_log (sync_mode, date_from, date_to, status)
            VALUES (%s, %s, %s, 'running') RETURNING id""", (mode, df, dt))
        sid = cur.fetchone()[0]
    conn.commit()
    return sid

def log_finish(conn, sid, recv, ins, upd, status='ok', err=None):
    with conn.cursor() as cur:
        cur.execute("""UPDATE sync_log SET finished_at=NOW(),
            orders_received=%s, orders_inserted=%s, orders_updated=%s,
            status=%s, error_message=%s WHERE id=%s""",
            (recv, ins, upd, status, err, sid))
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to",   dest="date_to")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--since-min", dest="since_min", type=int, default=None,
                    help="інкремент за останні N хвилин (точність до хвилини, по updateAt)")
    args = ap.parse_args()
    
    if not API_KEY: log.error("SD_API_KEY not set"); sys.exit(1)
    if not DB_CONFIG["password"]: log.error("DB_PASSWORD not set"); sys.exit(1)
    
    if args.month:
        y, m = args.month.split("-")
        df = f"{args.month}-01"
        nm = datetime(int(y)+1, 1, 1) if m == "12" else datetime(int(y), int(m)+1, 1)
        dt = (nm - timedelta(days=1)).strftime("%Y-%m-%d")
        mode, filter_by = f"month {args.month}", "orderTime"
    elif args.since_min is not None:
        now = datetime.now()
        dt = now.strftime("%Y-%m-%d %H:%M:%S")
        df = (now - timedelta(minutes=args.since_min)).strftime("%Y-%m-%d %H:%M:%S")
        mode, filter_by = f"incremental {args.since_min}min", "updateAt"
    elif args.incremental:
        dt = datetime.now().strftime("%Y-%m-%d")
        df = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        mode, filter_by = f"incremental {args.days}d", "updateAt"
    elif args.date_from and args.date_to:
        df, dt = args.date_from, args.date_to
        mode, filter_by = "range", "orderTime"
    else:
        ap.print_help(); sys.exit(1)
    
    log.info(f"=== SalesDrive -> PostgreSQL [{mode}] ===")
    log.info(f"Range: {df} -> {dt}")
    
    conn = psycopg2.connect(**DB_CONFIG)
    log.info("DB connected")
    sid = log_start(conn, mode, df, dt)
    
    try:
        orders = fetch_orders(df, dt, filter_by=filter_by)
        log.info(f"Writing {len(orders)} orders...")
        total_ins = total_upd = total_items = 0
        for i in range(0, len(orders), 100):
            batch = orders[i:i+100]
            ins, upd, its = upsert_batch(conn, batch)
            total_ins += ins; total_upd += upd; total_items += its
            log.info(f"  batch {i//100+1}: +{ins} new, ~{upd} upd, {its} items")
        log_finish(conn, sid, len(orders), total_ins, total_upd, 'ok')
        log.info(f"DONE: {len(orders)} recv, {total_ins} ins, {total_upd} upd, {total_items} items")
    except Exception as e:
        log.error(f"FAIL: {e}")
        log_finish(conn, sid, 0, 0, 0, 'error', str(e))
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
