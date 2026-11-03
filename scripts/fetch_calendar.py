"""Fetch this week's economic calendar (Forex Factory JSON feed) and save to data/calendar.json.
Run by GitHub Actions on a schedule. Keeps the previous file if the fetch fails."""
import json, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "calendar.json"

def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (news-blackout-dashboard)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            events = json.loads(r.read().decode("utf-8"))
        if not isinstance(events, list) or not events:
            raise ValueError("empty or invalid feed")
    except Exception as e:
        print(f"Fetch failed: {e}. Keeping existing {OUT.name}.")
        return 0  # don't fail the deploy; dashboard shows last good data + age
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(events),
        "events": events,
    }, indent=1), encoding="utf-8")
    high = sum(1 for e in events if str(e.get("impact", "")).lower() == "high")
    print(f"Saved {len(events)} events ({high} high impact) -> {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
