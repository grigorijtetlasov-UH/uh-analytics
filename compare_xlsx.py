"""
compare_xlsx.py — швидке порівняння двох SalesDrive-вивантажок:
ручної (з UI) і API (від salesdrive_api.py).

Використання:
    python compare_xlsx.py data/crm/months/salesdrive_2026-05_full.xlsx data/crm/months/salesdrive_2026-05_api.xlsx
"""
import sys
from pathlib import Path
import pandas as pd


def summarize(path: Path) -> dict:
    df = pd.read_excel(path)
    out = {
        "файл": path.name,
        "рядків": len(df),
        "колонок": len(df.columns),
    }
    if "Номер 1С" in df.columns:
        out["унікальних замовлень (Номер 1С)"] = df["Номер 1С"].dropna().nunique()
        out["рядків без Номер 1С (ліди)"] = df["Номер 1С"].isna().sum()
    if "Статус" in df.columns:
        out["унікальних статусів"] = df["Статус"].nunique()
        top_statuses = df["Статус"].value_counts().head(5).to_dict()
        out["топ-5 статусів"] = "\n      " + "\n      ".join(
            f"{k}: {v}" for k, v in top_statuses.items())
    if "Сайт" in df.columns:
        top_sites = df["Сайт"].value_counts().head(5).to_dict()
        out["топ-5 сайтів"] = "\n      " + "\n      ".join(
            f"{k}: {v}" for k, v in top_sites.items())
    if "Сума [Товари/Послуги]" in df.columns:
        out["сума всіх позицій ₴"] = f"{df['Сума [Товари/Послуги]'].sum():,.0f}".replace(",", " ")
    if "Дата" in df.columns:
        dates = pd.to_datetime(df["Дата"], errors="coerce").dropna()
        if len(dates):
            out["період"] = f"{dates.min().strftime('%Y-%m-%d')} ... {dates.max().strftime('%Y-%m-%d')}"
    return out


def main():
    if len(sys.argv) < 3:
        print(f"Використання: python {sys.argv[0]} <manual.xlsx> <api.xlsx>")
        return 1

    p1, p2 = Path(sys.argv[1]), Path(sys.argv[2])
    if not p1.exists():
        print(f"❌ Не знайдено: {p1}")
        return 2
    if not p2.exists():
        print(f"❌ Не знайдено: {p2}")
        return 2

    s1 = summarize(p1)
    s2 = summarize(p2)

    print()
    print(f"{'параметр':<35} | {'manual':<30} | {'api':<30}")
    print(f"{'-'*35}-+-{'-'*30}-+-{'-'*30}")
    keys = list(dict.fromkeys(list(s1.keys()) + list(s2.keys())))
    for k in keys:
        v1 = str(s1.get(k, "—"))
        v2 = str(s2.get(k, "—"))
        marker = " " if v1 == v2 else "≠"
        print(f"{k:<35} {marker}| {v1:<30} | {v2:<30}")
    print()


if __name__ == "__main__":
    sys.exit(main())
