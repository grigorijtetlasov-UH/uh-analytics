#!/usr/bin/env python3
# callaider.py — дані AI-дзвінків з CallAIder Ringing API (PULL). → docs/callaider.json
# Запуск: ./run.sh callaider.py   (потрібен CALLAIDER_API_KEY у .env)
import os, json, datetime, time
from pathlib import Path
from collections import Counter
import requests

KEY = os.environ.get("CALLAIDER_API_KEY", "")
BASE = "https://api.callaider.ai/v1/ringing"
H = {"Authorization": f"Bearer {KEY}"}
OUT = Path("docs/callaider.json")

BRAND_KEYS = ["sofino", "matrasroll", "amebli", "hubstore"]


def g(p, tries=5):
    # CallAIder за Cloudflare іноді віддає 522/5xx — ретраїмо з backoff 6с×i.
    # 4xx (напр. 401) кидаємо одразу, без повторів.
    for i in range(1, tries + 1):
        try:
            r = requests.get(BASE + p, headers=H, timeout=90)
        except requests.RequestException as e:
            if i < tries:
                print(f"  ⚠ {type(e).__name__} на {p} — ретрай {i}/{tries} через {6*i}с")
                time.sleep(6 * i); continue
            raise
        if r.status_code == 200:
            return r.json()
        if 500 <= r.status_code < 600 and i < tries:
            print(f"  ⚠ {r.status_code} на {p} — ретрай {i}/{tries} через {6*i}с")
            time.sleep(6 * i); continue
        r.raise_for_status()      # 4xx або останній 5xx → кидаємо
    raise RuntimeError(f"CallAIder {p}: вичерпано {tries} спроб")


def brand_of(name):
    n = (name or "").lower()
    for k in BRAND_KEYS:
        if k in n:
            return k
    return "other"


def main():
    if not KEY:
        print("❌ нема CALLAIDER_API_KEY у .env"); raise SystemExit(1)
    camps = g("/campaigns")
    out = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "campaigns": [],
           "totals": {"calls": 0, "completed": 0, "failed": 0, "answered": 0,
                      "with_transcript": 0, "with_eval": 0}}
    for c in camps:
        cid = c["id"]
        try:
            stat = g(f"/campaigns/{cid}/statistics")
        except Exception as e:
            print(f"  {c.get('name')}: statistics FAIL — {e}"); stat = {}
        total = stat.get("totalCalls", 0) or 0
        completed = stat.get("completedCalls", 0) or 0
        failed = stat.get("failedCalls", 0) or 0
        evaluated = stat.get("evaluatedCalls", 0) or 0
        avgdur = round(stat.get("avgCallDuration", 0) or 0, 1)
        try:
            calls = g(f"/campaigns/{cid}/calls")
        except Exception as e:
            print(f"  {c.get('name')}: calls FAIL — {e}"); calls = []
        if not isinstance(calls, list):
            calls = []
        answered = sum(1 for x in calls if x.get("answeredAt") or (x.get("callDuration") or 0) > 0)
        with_tr = sum(1 for x in calls if x.get("transcript"))
        with_ev = sum(1 for x in calls if x.get("evaluationResult"))
        daily = Counter((x.get("createdAt") or "")[:10] for x in calls if x.get("createdAt"))
        ends = Counter(x.get("endReason") or "?" for x in calls)
        # тривалості (для розподілу)
        durs = [x.get("callDuration") or 0 for x in calls]
        buckets = {"0-10с": 0, "10-30с": 0, "30-60с": 0, "1-3хв": 0, "3хв+": 0}
        for d in durs:
            if d < 10: buckets["0-10с"] += 1
            elif d < 30: buckets["10-30с"] += 1
            elif d < 60: buckets["30-60с"] += 1
            elif d < 180: buckets["1-3хв"] += 1
            else: buckets["3хв+"] += 1
        calls_sorted = sorted(calls, key=lambda x: x.get("createdAt") or "", reverse=True)
        recent = [{"phone": x.get("callerNumber"), "duration": x.get("callDuration"),
                   "status": x.get("status"), "end": x.get("endReason"),
                   "date": (x.get("createdAt") or "")[:16].replace("T", " "),
                   "summary": (x.get("summary") or "")[:400],
                   "transcript": (x.get("transcript") or "")[:1500],
                   "eval": x.get("evaluationResult")} for x in calls_sorted[:40]]
        out["campaigns"].append({
            "id": cid, "name": c.get("name"), "brand": brand_of(c.get("name", "")),
            "type": c.get("type"), "status": c.get("status"),
            "total": total, "completed": completed, "failed": failed,
            "evaluated": evaluated, "avg_duration": avgdur, "answered": answered,
            "with_transcript": with_tr, "with_eval": with_ev,
            "daily": [{"date": d, "count": n} for d, n in sorted(daily.items())],
            "duration_buckets": buckets, "ends": dict(ends.most_common()),
            "recent": recent})
        for k in ("calls", "completed", "failed", "answered", "with_transcript", "with_eval"):
            out["totals"][k] += {"calls": total, "completed": completed, "failed": failed,
                                 "answered": answered, "with_transcript": with_tr,
                                 "with_eval": with_ev}[k]
        print(f"  {c.get('name')}: total {total} | answered {answered} | транскриптів {with_tr} "
              f"| eval {with_ev} | avg {avgdur}с")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {OUT} ({OUT.stat().st_size} байт) | всього дзвінків: {out['totals']['calls']}")


if __name__ == "__main__":
    main()
