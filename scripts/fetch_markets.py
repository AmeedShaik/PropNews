"""Fetch DXY, US10Y yield and Gold 1-minute data and write data/markets.json.

Source: Yahoo Finance public chart endpoint (unofficial, free, no key; may be rate-limited).
  DXY   -> DX-Y.NYB   (ICE US Dollar Index)
  US10Y -> ^TNX       (10-year Treasury yield, in %)
  GOLD  -> GC=F       (COMEX gold futures, proxy for XAUUSD direction)

Usage
  python scripts/fetch_markets.py           # one snapshot (GitHub Actions)
  python scripts/fetch_markets.py --watch   # local: every 10 s on weekdays, every 5 min otherwise
"""
import json, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "markets.json"
SYMBOLS = {"DXY": "DX-Y.NYB", "US10Y": "^TNX", "GOLD": "GC=F"}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1m&range=1d"
KEEP_MIN = 180  # keep the last 3 hours of 1-minute bars


def get(sym):
    req = urllib.request.Request(URL.format(s=urllib.request.quote(sym)),
                                 headers={"User-Agent": "Mozilla/5.0 (PropNews dashboard)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode())
    res = j["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = res["indicators"]["quote"][0].get("close") or []
    bars = [[t * 1000, round(c, 4)] for t, c in zip(ts, closes) if c is not None]
    meta = res.get("meta", {})
    last = meta.get("regularMarketPrice") or (bars[-1][1] if bars else None)
    return {"symbol": sym, "last": last, "prev_close": meta.get("chartPreviousClose"),
            "bars": bars[-KEEP_MIN:]}


def run_once():
    data, errors = {}, []
    for k, s in SYMBOLS.items():
        try:
            data[k] = get(s)
        except Exception as e:  # keep going with the others
            errors.append(f"{k}: {e}")
    if not data:
        raise RuntimeError("; ".join(errors))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"source": "Yahoo Finance (unofficial)",
                               "fetched_at": datetime.now(timezone.utc).isoformat(),
                               "symbols": data, "errors": errors}), encoding="utf-8")
    tmp.replace(OUT)  # atomic, so the browser never reads a half-written file
    print(datetime.now().strftime("%H:%M:%S"),
          " | ".join(f"{k} {v['last']}" for k, v in data.items()), (" ERR " + "; ".join(errors)) if errors else "")


def main():
    if "--watch" not in sys.argv:
        try:
            run_once()
        except Exception as e:
            print("Markets fetch failed:", e, "(keeping previous file)")
        return
    print("Watching DXY / US10Y / Gold. Ctrl+C to stop.")
    while True:
        try:
            run_once()
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(10 if datetime.now(timezone.utc).weekday() < 5 else 300)


if __name__ == "__main__":
    main()
