import sys
import traceback
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import time
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

from src.downloader import download_fno_bhavcopy
from src.database import init_database, store_daily_iv, trim_old_data

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def process_day_data(df, date):
    """Process a single day's DataFrame and store IVs"""
    # Column mapping (same as main.py)
    column_mapping = {
        'TckrSymb': 'SYMBOL',
        'ClsPric': 'CLOSE',
        'StrkPric': 'STRIKE_PR',
        'OptnTp': 'OPTION_TYP',
        'XpryDt': 'EXPIRY_DT',
        'UndrlygPric': 'UNDERLYING_PRICE'
    }
    rename_dict = {old: new for old, new in column_mapping.items() if old in df.columns}
    if rename_dict:
        df = df.rename(columns=rename_dict)

    required_cols = ['SYMBOL', 'CLOSE', 'STRIKE_PR', 'OPTION_TYP']
    for col in required_cols:
        if col not in df.columns:
            print(f"  Missing column '{col}' – skipping day")
            return 0

    options = df[df['OPTION_TYP'].isin(['CE', 'PE'])]
    symbols = options['SYMBOL'].unique()
    print(f"  Found {len(symbols)} symbols with options")

    processed = 0
    for symbol in symbols:
        try:
            stock_data = df[df['SYMBOL'] == symbol]
            if len(stock_data) == 0:
                continue

            spot = 0.0
            if 'UNDERLYING_PRICE' in stock_data.columns:
                spot = safe_float(stock_data['UNDERLYING_PRICE'].iloc[0])
            if spot <= 0:
                futures = stock_data[stock_data['OPTION_TYP'] == 'XX']
                if len(futures) > 0:
                    spot = safe_float(futures['CLOSE'].iloc[0])
            if spot <= 0:
                spot = safe_float(stock_data['CLOSE'].iloc[0])
            if spot <= 0:
                continue

            opts = stock_data[stock_data['OPTION_TYP'].isin(['CE', 'PE'])]
            if len(opts) == 0:
                continue
            strikes = opts['STRIKE_PR'].unique()
            if len(strikes) == 0:
                continue
            strike_floats = [safe_float(s) for s in strikes]
            atm_strike = min(strike_floats, key=lambda x: abs(x - spot))

            call = opts[(opts['STRIKE_PR'] == atm_strike) & (opts['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                call = opts[(opts['STRIKE_PR'] == atm_strike) & (opts['OPTION_TYP'] == 'PE')]
                if len(call) == 0:
                    continue

            opt_price = safe_float(call['CLOSE'].iloc[0])
            if opt_price > 0 and spot > 0:
                moneyness = abs(spot - atm_strike) / spot
                current_iv = 20 + (moneyness * 60)
                current_iv = max(10, min(80, current_iv))
            else:
                current_iv = 25.0

            expiry = str(call['EXPIRY_DT'].iloc[0]) if 'EXPIRY_DT' in call.columns else 'N/A'

            store_daily_iv(date, symbol, current_iv, spot, expiry, atm_strike, 'CE')
            processed += 1
            if processed % 100 == 0:
                print(f"    Processed {processed} records...")

        except Exception as e:
            print(f"    Error with {symbol}: {e}")
            traceback.print_exc()
            continue

    return processed

def backfill(days=365):
    print(f"Starting backfill for the last {days} trading days...")
    init_database()

    end_date = datetime.now()
    current = end_date
    downloaded_days = 0
    total_processed = 0
    processed_dates = []

    max_attempts = days * 3
    attempts = 0

    while downloaded_days < days and attempts < max_attempts:
        attempts += 1
        if current.weekday() >= 5:
            current -= timedelta(days=1)
            continue

        print(f"\nAttempting: {current.strftime('%Y-%m-%d')}")
        data = download_fno_bhavcopy(current)
        if data is not None and not data.empty:
            date_str = current.strftime('%Y-%m-%d')
            data['date'] = date_str
            print(f"  ✅ Downloaded ({downloaded_days+1}/{days})")
            
            # Process this day's data immediately
            processed = process_day_data(data, date_str)
            total_processed += processed
            downloaded_days += 1
            processed_dates.append(date_str)
            print(f"  Stored {processed} records for {date_str}")
        else:
            print(f"  ❌ No data for {current.strftime('%Y-%m-%d')}")

        current -= timedelta(days=1)
        time.sleep(1)

    print(f"\nDownloaded {downloaded_days} trading days")
    print(f"Total records stored: {total_processed}")

    if downloaded_days == 0:
        print("No data downloaded")
        return

    # Auto‑trim to 253 days
    trim_old_data(253)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical IV data")
    parser.add_argument('--days', type=int, default=365,
                        help='Number of recent trading days to backfill (default: 365)')
    args = parser.parse_args()
    backfill(days=args.days)
