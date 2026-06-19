import os, json
import requests
KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
PID = "ChIJ116jiRLb1EARi8yUEHPU8qA"
if not KEY:
    print("❌ нема GOOGLE_PLACES_KEY у .env"); raise SystemExit(1)
print("=== 1) ЛЕГАСІ Place Details ===")
try:
    r = requests.get("https://maps.googleapis.com/maps/api/place/details/json",
                     params={"place_id": PID, "fields": "name,rating,user_ratings_total,reviews",
                             "language": "uk", "key": KEY}, timeout=20)
    j = r.json(); res = j.get("result", {})
    print("  status:", j.get("status"), "| error:", j.get("error_message", ""))
    print("  name:", res.get("name"), "| rating:", res.get("rating"), "| total:", res.get("user_ratings_total"))
    rv = res.get("reviews", []); print("  reviews:", len(rv))
    if rv: print("  review[0]:", json.dumps({k: rv[0].get(k) for k in ("author_name","rating","time","relative_time_description","text")}, ensure_ascii=False)[:320])
except Exception as e:
    print("  легасі FAIL:", e)
print("\n=== 2) НОВИЙ Places API v1 ===")
try:
    r = requests.get(f"https://places.googleapis.com/v1/places/{PID}",
                     headers={"X-Goog-Api-Key": KEY, "X-Goog-FieldMask": "displayName,rating,userRatingCount,reviews", "Accept-Language": "uk"}, timeout=20)
    print("  HTTP:", r.status_code); j = r.json()
    if r.status_code == 200:
        print("  name:", (j.get("displayName") or {}).get("text"), "| rating:", j.get("rating"), "| count:", j.get("userRatingCount"))
        rv = j.get("reviews", []); print("  reviews:", len(rv))
        if rv: print("  review[0] keys:", list(rv[0].keys())); print("  review[0]:", json.dumps(rv[0], ensure_ascii=False)[:320])
    else:
        print("  error:", json.dumps(j, ensure_ascii=False)[:320])
except Exception as e:
    print("  v1 FAIL:", e)
