"""
patch_api_xlsx.py — виправляє вже завантажений salesdrive_2026-05_api.xlsx БЕЗ
повторного звернення до API.

Що робить:
1. ВИДАЛЯЄ рядки-доставки ("Оплата послуги Доставка (Нова Пошта)" та подібні).
   Ці позиції приходять з API, але в ручному xlsx їх немає — псують крос-сейл,
   гарантії+чохли і виручку.
2. Підставляє правильні назви статусів замість 'id=72', 'id=47' тощо
3. Виправляє опечатку 'Спам на согласовании' → 'Спам на согласование'
4. Те саме для Сайтів і Менеджерів (на випадок якщо там теж є id=...)
5. Перезаписує файл

Використання:
    python patch_api_xlsx.py data/crm/months/salesdrive_2026-05_api.xlsx
"""
import sys
from pathlib import Path
import pandas as pd

# Імпорт словників і фільтрів з основного модуля
sys.path.insert(0, ".")
from salesdrive_api import (
    STATUS_ID_TO_NAME,
    SAJT_ID_TO_NAME,
    USER_ID_TO_NAME,
    _is_delivery_position,
)


def _to_int(v):
    try:
        if pd.isna(v):
            return None
        return int(v)
    except (ValueError, TypeError):
        return None


def patch_column(df, value_col, id_col, mapping, label):
    """Перезаписує value_col на основі id_col + mapping."""
    if value_col not in df.columns or id_col not in df.columns:
        print(f"  ⚠ пропускаю {label}: нема колонки {value_col} або {id_col}")
        return 0

    changed = 0
    new_values = []
    for value, id_v in zip(df[value_col], df[id_col]):
        id_int = _to_int(id_v)
        # Якщо є коректний id у словнику — підставляємо назву
        if id_int is not None and id_int in mapping:
            new_value = mapping[id_int]
            if new_value != value:
                changed += 1
            new_values.append(new_value)
        else:
            # Залишаємо як є (наприклад "id=999" для невідомого)
            new_values.append(value)

    df[value_col] = new_values
    return changed


def remove_delivery_rows(df):
    """Видаляє рядки-доставки (службові позиції з products[])."""
    if "Назва [Товари/Послуги]" not in df.columns:
        return df, 0

    names_lower = df["Назва [Товари/Послуги]"].fillna("").astype(str).str.lower()
    mask_delivery = names_lower.apply(_is_delivery_position)

    n_removed = int(mask_delivery.sum())
    df_clean = df[~mask_delivery].reset_index(drop=True)

    return df_clean, n_removed


# Перейменування колонок до формату, який чекає fetch_data.py і sales_kpi.py.
# Старі (неправильні) → нові (правильні).
COLUMN_RENAMES = {
    "Сума замовлення":            "Сума",
    "Кількість [Товари/Послуги]": "К-ть [Товари/Послуги]",
    "Ціна [Товари/Послуги]":      "Ціна за од. [Товари/Послуги]",
}


def rename_columns_for_compat(df):
    """Перейменовує колонки до формату ручної xlsx-вивантажки."""
    renamed = []
    for old, new in COLUMN_RENAMES.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
            renamed.append(f"{old} → {new}")
    return df, renamed


def main():
    if len(sys.argv) < 2:
        print(f"Використання: python {sys.argv[0]} <шлях.xlsx>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Не знайдено: {path}")
        return 2

    print(f"📂 Читаю: {path}")
    df = pd.read_excel(path)
    print(f"   {len(df)} рядків, {len(df.columns)} колонок")

    print()
    print("🔧 Виправляю...")

    # 0. Перейменувати колонки до формату fetch_data/sales_kpi
    df, renamed = rename_columns_for_compat(df)
    if renamed:
        print(f"   Перейменовано {len(renamed)} колонок:")
        for r in renamed:
            print(f"     {r}")
    else:
        print(f"   Колонки вже правильно названі (нічого міняти)")

    # 1. Видалити рядки-доставки
    df, n_removed = remove_delivery_rows(df)
    print(f"   Видалено доставок: {n_removed} рядків")

    # 2-4. Підставити назви замість id=...
    n1 = patch_column(df, "Статус", "Статус ID", STATUS_ID_TO_NAME, "Статус")
    print(f"   Статус: оновлено {n1} рядків")

    n2 = patch_column(df, "Сайт", "Сайт ID", SAJT_ID_TO_NAME, "Сайт")
    print(f"   Сайт: оновлено {n2} рядків")

    n3 = patch_column(df, "Менеджер", "Менеджер ID", USER_ID_TO_NAME, "Менеджер")
    print(f"   Менеджер: оновлено {n3} рядків")

    print()
    print(f"💾 Перезаписую: {path}")
    df.to_excel(path, index=False, engine="openpyxl")

    print()
    print(f"✓ Готово. Рядкiв пiсля очистки: {len(df)}")
    if "ID замовлення" in df.columns:
        print(f"  Унікальних замовлень: {df['ID замовлення'].nunique()}")
    if "Сума [Товари/Послуги]" in df.columns:
        s = df["Сума [Товари/Послуги]"].sum()
        print(f"  Сума товарiв: {s:,.0f}".replace(",", " ") + " ₴")
    print()
    print("  Топ-5 товарів:")
    for s, n in df["Назва [Товари/Послуги]"].value_counts().head(5).items():
        print(f"    {s}: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

