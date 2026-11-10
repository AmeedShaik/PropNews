"""Fetch official US release ACTUALS from the BLS public API and write data/actuals.json.

Covers the releases that move gold most: CPI / Core CPI (m/m, y/y), NFP, Unemployment Rate,
Average Hourly Earnings, PPI. Titles match the Forex Factory calendar so the dashboard can
auto-fill the "Actual" column and compute the bias.

Usage
  python scripts/fetch_actuals.py           # one fetch (GitHub Actions)
  python scripts/fetch_actuals.py --watch   # local near-real-time: polls every 15 s
                                            # from 08:29-08:45 New York time on weekdays
Env
  BLS_API_KEY  free key from https://data.bls.gov/registrationEngine/
               (without key: 25 requests/day, enough for Actions but NOT for --watch)
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "actuals.json"
API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES = {
    "CUSR0000SA0":    "cpi",        # CPI-U all items, SA (index)
    "CUSR0000SA0L1E": "core",       # CPI-U less food & energy, SA
    "CUUR0000SA0":    "cpi_nsa",    # NSA for y/y (BLS headline y/y is NSA)
    "CUUR0000SA0L1E": "core_nsa",
    "CES0000000001":  "nfp",        # total nonfarm payrolls, SA (thousands)
    "LNS14000000":    "ur",         # unemployment rate, SA
    "CES0500000003":  "ahe",        # avg hourly earnings, total private, SA
    "WPSFD4":         "ppi",        # PPI final demand, SA
    "WPSFD49104":     "core_ppi",   # PPI final demand less foods, energy & trade, SA
}

def fetch():
    y = datetime.now().year
    body = {"seriesid": list(SERIES), "startyear": str(y - 2), "endyear": str(y)}
    key = os.environ.get("BLS_API_KEY", "").strip()
    if key:
        body["registrationkey"] = key
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "PropNews/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode())
    if j.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError("BLS: " + "; ".join(j.get("message", [])) )
    out = {}
    for s in j["Results"]["series"]:
        pts = []
        for d in s.get("data", []):
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            try:
                v = float(d["value"])
            except ValueError:
                continue                        # '-' = missing month
            pts.append(((int(d["year"]), int(d["period"][1:])), v))
        out[SERIES[s["seriesID"]]] = dict(sorted(pts, reverse=True))  # newest first
    return out

def prev_month(p, n=1):
    y, m = p
    m -= n
    while m <= 0:
        m += 12; y -= 1
    return (y, m)

def compute(d):
    items = []
    def add(titles, key, fn):
        s = d.get(key) or {}
        if not s:
            return
        p = next(iter(s))
        try:
            val = fn(s, p)
        except (KeyError, ZeroDivisionError):
            return
        items.append({"titles": titles, "period": f"{p[0]}-{p[1]:02d}", "actual": val})
    pct = lambda x: f"{x:.1f}%"
    mm = lambda s, p: pct(round((s[p] / s[prev_month(p)] - 1) * 100 + 1e-9, 1))
    yy = lambda s, p: pct(round((s[p] / s[prev_month(p, 12)] - 1) * 100 + 1e-9, 1))
    add(["CPI m/m"], "cpi", mm)
    add(["Core CPI m/m"], "core", mm)
    add(["CPI y/y"], "cpi_nsa", yy)
    add(["Core CPI y/y"], "core_nsa", yy)
    add(["Non-Farm Employment Change"], "nfp", lambda s, p: f"{round(s[p] - s[prev_month(p)]):d}K")
    add(["Unemployment Rate"], "ur", lambda s, p: pct(s[p]))
    add(["Average Hourly Earnings m/m"], "ahe", mm)
    add(["PPI m/m"], "ppi", mm)
    add(["Core PPI m/m"], "core_ppi", mm)
    return items

def load_old():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}

def run_once():
    old = load_old()
    seen = old.get("first_seen", {})            # "title|period" -> ISO time first observed
    now = datetime.now(timezone.utc).isoformat()
    items = compute(fetch())
    for it in items:
        k = it["titles"][0] + "|" + it["period"]
        it["first_seen"] = seen.setdefault(k, now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": "BLS public API", "fetched_at": now,
                               "items": items, "first_seen": seen}, indent=1), encoding="utf-8")
    print(now, " | ".join(f'{i["titles"][0]} {i["actual"]} ({i["period"]})' for i in items))

def et_now():
    # US Eastern without extra deps: DST 2nd Sun Mar -> 1st Sun Nov
    u = datetime.now(timezone.utc)
    y = u.year
    mar = datetime(y, 3, 8, 7, tzinfo=timezone.utc); mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, 6, tzinfo=timezone.utc); nov += timedelta(days=(6 - nov.weekday()) % 7)
    return u + timedelta(hours=-4 if mar <= u < nov else -5)

def main():
    if "--watch" not in sys.argv:
        try:
            run_once()
        except Exception as e:
            print("Actuals fetch failed:", e, "(keeping previous file)")
        return
    print("Watching BLS. Fast polling 08:29-08:45 ET on weekdays. Ctrl+C to stop.")
    while True:
        et = et_now()
        hot = et.weekday() < 5 and (8, 29) <= (et.hour, et.minute) <= (8, 45)
        try:
            run_once()
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(15 if hot else 600)

if __name__ == "__main__":
    main()
