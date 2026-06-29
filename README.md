# NSE IVP/IVR Analysis

Automated daily analysis of Implied Volatility Percentile (IVP) and Implied Volatility Rank (IVR) for NSE F&O stocks.

## Features

- 📊 Fetches daily F&O bhavcopy from NSE
- 📈 Calculates IV, IVP, and IVR for all F&O stocks
- 📱 Sends Telegram notification with sorted results
- ☁️ Runs automatically via GitHub Actions
- 📦 Outputs JSON for easy integration

## Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with Telegram credentials
4. Run: `python src/main.py`

## Telegram Notification Example
