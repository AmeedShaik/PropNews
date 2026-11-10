"""Fetch official release ACTUALS and write data/actuals.json.

  BLS (US): CPI / Core CPI (m/m, y/y), NFP, Unemployment Rate, Avg Hourly Earnings, PPI, Core PPI
  EIA (US): Crude Oil Inventories (weekly change, commercial crude excl. SPR)  -> drives WTI bias

Titles match the Forex Factory calendar so the dashboard auto-fills the "Actual" column.

Usage
  python scripts/fetch_actuals.py           # one fetch (GitHub Actions)
  python scripts/fetch_actuals.py --watch   # local: polls every 15 s in release windows
Env
  BLS_API_KEY  https://data.bls.gov/registrationEngine/
  EIA_API_KEY  https://www.eia.gov/opendata/register.php   (optional; enables WTI auto actual)
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "actuals.json"
BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
EIA_API = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
SERIES = {
    "CUSR0000SA0": "cpi", "CUSR0000SA0L1E": "core", "CUUR0000SA0": "cpi_nsa", "CUUR0000SA0L1E": "core_nsa",
    "CES0000000001": "nfp", "LNS14000000": "ur", "CES0500000003": "ahe", "WPSFD4": "ppi", "WPSFD49104": "core_ppi",
}
UA = {"User-Agent": "PropNews/1.0"}


# ---------------- BLS ----------------
def fetch_bls():
    y = datetime.now().year
    body = {"seriesid": list(SERIES), "startyear": str(y - 2), "endyear": str(y)}
    key = os.environ.get("BLS_API_KEY", "").strip()
    if key:
        body["registrationkey"] = key
    req = urllib.request.Request(BLS_API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode())
    if j.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError("BLS: " + "; ".join(j.get("message", [])))
    out = {}
    for s in j["Results"]["series"]:
        pts = []
        for d in s.get("data", []):
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            try:
                v = float(d["value"])
            except ValueError:
                continue
            pts.append(((int(d["year"]), int(d["period"][1:])), v))
        out[SERIES[s["seriesID"]]] = dict(sorted(pts, reverse=True))
    return out


def prev_month(p, n=1):
    y, m = p
    m -= n
    while m <= 0:
        m += 12; y -= 1
    return (y, m)


def compute_bls(d):
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
        items.append({"titles": titles, "kind": "monthly", "period": f"{p[0]}-{p[1]:02d}", "actual": val})
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


# ---------------- EIA (crude inventories) ----------------
def fetch_eia():
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        return []
    q = urllib.parse.urlencode([
        ("api_key", key), ("frequency", "weekly"), ("data[0]", "value"),
        ("facets[series][]", "WCESTUS1"),          # commercial crude stocks excl. SPR (thousand bbl)
        ("sort[0][column]", "period"), ("sort[0][direction]", "desc"), ("offset", "0"), ("length", "3")])
    with urllib.request.urlopen(urllib.request.Request(EIA_API + "?" + q, headers=UA), timeout=30) as r:
        j = json.loads(r.read().decode())
    rows = sorted(j["response"]["data"], key=lambda x: x["period"], reverse=True)
    if len(rows) < 2:
        raise RuntimeError("EIA: not enough rows")
    chg = (float(rows[0]["value"]) - float(rows[1]["value"])) / 1000.0   # -> million barrels
    return [{"titles": ["Crude Oil Inventories"], "kind": "weekly", "period": rows[0]["period"], "actual": f"{chg:.1f}M"}]


# ---------------- write ----------------
def load_old():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_once():
    old = load_old()
    old_items = old.get("items", [])
    errors = []
    try:
        bls = compute_bls(fetch_bls())
    except Exception as e:
        errors.append(f"BLS: {e}")
        bls = [i for i in old_items if i.get("kind", "monthly") == "monthly"]
    try:
        eia = fetch_eia()
    except Exception as e:
        errors.append(f"EIA: {e}")
        eia = [i for i in old_items if i.get("kind") == "weekly"]
    seen = old.get("first_seen", {})
    now = datetime.now(timezone.utc).isoformat()
    items = bls + eia
    for it in items:
        it["first_seen"] = seen.setdefault(it["titles"][0] + "|" + it["period"], now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"source": "BLS + EIA public APIs", "fetched_at": now, "items": items,
                               "first_seen": seen, "errors": errors}, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    print(now[11:19], " | ".join(f'{i["titles"][0]} {i["actual"]}' for i in items), ("ERR " + "; ".join(errors)) if errors else "")


def et_now():
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
            print("Actuals fetch failed:", e)
        return
    print("Watching BLS (08:29-08:45 ET Mon-Fri) and EIA (10:29-10:45 ET Wed/Thu). Ctrl+C to stop.")
    while True:
        et = et_now()
        hm = (et.hour, et.minute)
        hot = (et.weekday() < 5 and (8, 29) <= hm <= (8, 45)) or (et.weekday() in (2, 3) and (10, 29) <= hm <= (10, 45))
        try:
            run_once()
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(15 if hot else 600)


if __name__ == "__main__":
    main()
