# Prop Firm News Blackout Dashboard (Live)

Live economic-calendar news guard for prop-firm traders (FTMO ±2 min, FundingPips ±5 min, custom).

## How the live data works
`index.html` (GitHub Pages) → reads `data/calendar.json` (same origin) ← written every 30 min by
**GitHub Actions** (`scripts/fetch_calendar.py`) from the Forex Factory weekly feed.
If that file is missing, the page tries the feed directly, then falls back to clearly-labelled **DEMO** data.

## Setup (one time)
1. Create a new GitHub repo and push these files to `main`:
   ```
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<you>/news-blackout.git
   git push -u origin main
   ```
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
4. **Actions → Update calendar & deploy → Run workflow** (first run).
5. Open `https://<you>.github.io/news-blackout/`.

## Run locally
Double-click `run.bat` (needs Python) → http://localhost:8000
(Opening index.html directly via file:// can't read data/calendar.json, so it will try the feed directly / show DEMO.)

## Notes
- Feed covers the current week (Sun–Sat, New York time); it is rate limited, so don't poll it more often than needed.
- The header shows **LIVE** + data age, or **DEMO** if live data failed. Use ⟳ Refresh to reload.
- Time Simulator still works on live events for testing alerts.
- Always confirm your firm's current news rules.
