"""MCI history storage — PostgreSQL (schema mci). Reuses finance.db.connection."""
from __future__ import annotations
from psycopg2.extras import Json
from finance.db.connection import connect
from mci.models import MCIResult


def save_result(result: MCIResult) -> None:
    d = result.to_dict()
    sd = result.timestamp.date()
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mci.snapshots (snapshot_date, ts, score, label, advice, sub_indexes, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s, now()) "
            "ON CONFLICT (snapshot_date) DO UPDATE SET ts=EXCLUDED.ts, score=EXCLUDED.score, "
            "label=EXCLUDED.label, advice=EXCLUDED.advice, sub_indexes=EXCLUDED.sub_indexes, updated_at=now()",
            (sd, result.timestamp, d["score"], d["label"], d["advice"], Json(d["sub_indexes"])),
        )
        for si in d["sub_indexes"]:
            cur.execute(
                "INSERT INTO mci.sub_scores (snapshot_date, name, score, weight, weighted, signals) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (snapshot_date, name) DO UPDATE SET score=EXCLUDED.score, "
                "weight=EXCLUDED.weight, weighted=EXCLUDED.weighted, signals=EXCLUDED.signals",
                (sd, si["name"], si["score"], si["weight"], si["weighted"], Json(si.get("signals", []))),
            )
        conn.commit()


def load_history(limit: int = 365) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT score, label, advice, ts, sub_indexes FROM mci.snapshots "
                    "ORDER BY snapshot_date DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    out = []
    for score, label, advice, ts, sub in reversed(rows):
        out.append({"score": float(score), "label": label, "advice": advice,
                    "timestamp": ts.isoformat(), "sub_indexes": sub})
    return out


def get_trend(days: int = 7) -> str:
    history = load_history(limit=days)
    if len(history) < 2:
        return "Недостатньо даних для тренду"
    scores = [e["score"] for e in history]
    half = len(scores) // 2
    avg_old = sum(scores[:half]) / max(1, half)
    avg_new = sum(scores[half:]) / max(1, len(scores) - half)
    diff = avg_new - avg_old
    if diff > 5:
        return f"Тренд вгору: +{diff:.1f} за {days} днів"
    if diff < -5:
        return f"Тренд вниз: {diff:.1f} за {days} днів"
    return f"Стабільно: {diff:+.1f} за {days} днів"
