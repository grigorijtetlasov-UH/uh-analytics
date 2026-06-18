"""Backfill data/mci_history.json -> PostgreSQL (schema mci)."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from psycopg2.extras import Json
from finance.db.connection import connect

HISTORY = Path(__file__).parent / "data" / "mci_history.json"


def main() -> None:
    if not HISTORY.exists():
        print("немає", HISTORY); return
    entries = json.loads(HISTORY.read_text(encoding="utf-8"))
    print("записів у історії:", len(entries))
    ns = nu = 0
    with connect() as conn:
        cur = conn.cursor()
        for e in entries:
            ts = datetime.fromisoformat(e["timestamp"]); sd = ts.date()
            cur.execute(
                "INSERT INTO mci.snapshots (snapshot_date, ts, score, label, advice, sub_indexes, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s, now()) "
                "ON CONFLICT (snapshot_date) DO UPDATE SET ts=EXCLUDED.ts, score=EXCLUDED.score, "
                "label=EXCLUDED.label, advice=EXCLUDED.advice, sub_indexes=EXCLUDED.sub_indexes, updated_at=now()",
                (sd, ts, e["score"], e["label"], e.get("advice"), Json(e.get("sub_indexes", []))),
            )
            ns += 1
            for si in e.get("sub_indexes", []):
                cur.execute(
                    "INSERT INTO mci.sub_scores (snapshot_date, name, score, weight, weighted, signals) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (snapshot_date, name) DO UPDATE SET score=EXCLUDED.score, "
                    "weight=EXCLUDED.weight, weighted=EXCLUDED.weighted, signals=EXCLUDED.signals",
                    (sd, si["name"], si["score"], si["weight"],
                     si.get("weighted", si["score"] * si["weight"]), Json(si.get("signals", []))),
                )
                nu += 1
        conn.commit()
    print("backfill:", ns, "днів,", nu, "суб-індексів")


if __name__ == "__main__":
    main()
