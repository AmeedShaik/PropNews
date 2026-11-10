"""Fetch 1-minute data for DXY, US10Y, Gold, WTI and major FX pairs -> data/markets.json.

Source: Yahoo Finance public chart endpoint (unofficial, free, no key; may be rate-limited).

Usage
  python scripts/fetch_markets.py           # one snapshot (GitHub Actions)
  python scripts/fetch_markets.py --watch   # local: every 10 s on weekdays, every 5 min otherwise
"""
import json, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "markets.json"
SYMBOLS = {
    "DXY": "DX-Y.NYB", "US10Y": "^TNX", "GOLD": "GC=F", "WTI": "CL=F",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X", "USDCAD": "CAD=X", "USDCHF": "CHF=X",
}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1m&range=1d"
KEEP_MIN = 900  # last 15 hours of 1-minute bars (covers the whole release day)


def get(sym):
    req = urllib.request.Request(URL.format(s=urllib.parse.quote(sym)),
                                 headers={"User-Agent": "Mozilla/5.0 (PropNews dashboard)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode())
    res = j["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = res["indicators"]["quote"][0].get("close") or []
    bars = [[t * 1000, round(c, 5)] for t, c in zip(ts, closes) if c is not None]
    meta = res.get("meta", {})
    last = meta.get("regularMarketPrice") or (bars[-1][1] if bars else None)
    return {"symbol": sym, "last": last, "prev_close": meta.get("chartPreviousClose"), "bars": bars[-KEEP_MIN:]}


def run_once():
    data, errors = {}, []
    def job(item):
        k, s = item
        try:
            return k, get(s), None
        except Exception as e:
            return k, None, f"{k}: {e}"
    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, v, err in ex.map(job, SYMBOLS.items()):
            if v: data[k] = v
            if err: errors.append(err)
    if not data:
        raise RuntimeError("; ".join(errors))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"source": "Yahoo Finance (unofficial)",
                               "fetched_at": datetime.now(timezone.utc).isoformat(),
                               "symbols": data, "errors": errors}, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)  # atomic: the browser never reads a half-written file
    print(datetime.now().strftime("%H:%M:%S"), f"{len(data)}/{len(SYMBOLS)} symbols",
          ("ERR " + "; ".join(errors)) if errors else "")


def main():
    if "--watch" not in sys.argv:
        try:
            run_once()
        except Exception as e:
            print("Markets fetch failed:", e, "(keeping previous file)")
        return
    print("Watching markets. Ctrl+C to stop.")
    while True:
        try:
            run_once()
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(10 if datetime.now(timezone.utc).weekday() < 5 else 300)


if __name__ == "__main__":
    main()
