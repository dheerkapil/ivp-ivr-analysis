# NSE IVP/IVR Analysis

Automated daily analysis of Implied Volatility Percentile (IVP) and Implied Volatility Rank (IVR) for NSE F&O stocks.

## Features

- 📊 Fetches daily F&O bhavcopy from NSE
- 📈 Calculates IV, IVP, and IVR for all F&O stocks
- 📱 Sends **one** Telegram report per trading day, as soon as the bhavcopy is out
- 🔁 Retries every 30 minutes from 18:00 to 00:00 IST until the data appears
- 🗓️ Skips NSE trading holidays automatically
- ⚠️ Alerts you if no data could be fetched by the end of the window
- ☁️ Runs automatically via GitHub Actions
- 📦 One JSON file per trading day in `data/daily/`

## How the daily alert works

The workflow fires on a 30-minute ladder — `18:00, 18:30, … 23:30, 00:00` IST,
Mon–Fri. Every run asks one question: *has today's report gone out yet?*

- **Trading holiday** (checked against NSE's holiday list) → send a one-off
  "market closed" notice on the first check of the day, then do nothing else.
- **Data is available** → compute IV/IVR/IVP, send the full report, record the
  day as sent in `data/state.json`, and stop. Later slots that day do nothing.
- **Data not published yet** (NSE posts the F&O bhavcopy around 18:00 IST, and
  as late as ~21:00 on monthly-expiry Thursdays) → exit quietly and wait for the
  next slot.
- **Nothing by midnight IST** → send a single "no data" alert and close the day.

So you get **exactly one report per trading day**, at the earliest slot where the
data exists — never a duplicate flood, and never a silent failure.

### Trading holidays

The day under report is checked against NSE's holiday list (`FO` segment), taken
live from NSE's `holiday-master` API with a bundled fallback in
`config/nse_holidays.json` for when the API is unreachable. On a holiday you get
a single **"NSE Trading Holiday"** notice on the first check of the day (sent
once — tracked in `data/state.json`), and nothing else; there's no spurious
late-night "no data" alert.

The bundled fallback is **refreshed weekly** — on the first run on/after Monday
18:00 IST, the live list is fetched and the file rewritten if anything changed
(the change is committed). If NSE is unreachable that week, the sync retries on
the next slot. When no list at all can be found for a year the check fails open
(assumes a trading day), so a missed holiday costs at most one alert rather than
a dropped report.

### Delivery guarantees

- A failed Telegram send (or missing credentials) makes the Actions run **fail
  (red)** instead of silently passing, and a note goes to
  `TELEGRAM_ERROR_CHAT_ID` when that secret is set.
- All dates are computed in **IST**, not the runner's UTC clock — important
  because GitHub frequently runs the late slots after midnight IST.

### A note on GitHub's scheduler

GitHub's `schedule` trigger is best-effort and, on this repository, has been
delivering runs **4–6 hours late** (a slot written for 18:30 IST has been firing
around 00:30 IST). The dense ladder plus the "send once" state means you still
get a single correct report — but the delivery time can drift. If exact timing
matters, trigger the workflow from an external scheduler (e.g. a cron service
calling `workflow_dispatch` via the GitHub API) instead of relying on
`schedule`.

## Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with Telegram credentials
4. Run: `python src/main.py`

### Secrets

| Secret | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Chat that receives the daily report |
| `TELEGRAM_ERROR_CHAT_ID` | *(optional)* chat for failure / no-data alerts |

## Telegram Notification Example
