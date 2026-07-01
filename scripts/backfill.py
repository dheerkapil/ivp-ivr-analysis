import sys
import traceback
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import time
import pandas as pd
import sqlite3

sys.path.append(str(Path(__file__).parent.parent))

from src.downloader import download_fno_bhavcopy
from src.database import init_database, store_daily_iv, trim_old_data, DB_PATH

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def get_existing_dates():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM daily_iv")
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}

def process_day_data(df, date):
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

def count_trimmed_days(target=253):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM daily_iv ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()
    all_dates = [row[0] for row in rows]
    if len(all_dates) <= target:
        return len(all_dates)
    return target

def backfill(target_keep=253):
    print(f"Starting backfill – target: keep {target_keep} trading days after trimming.")
    init_database()

    existing_dates = get_existing_dates()
    existing_count = len(existing_dates)
    print(f"Currently have {existing_count} distinct trading days.")

    trimmed_count = count_trimmed_days(target_keep)
    if trimmed_count >= target_keep:
        print(f"Already have {trimmed_count} days after trimming – target reached.")
        trim_old_data(target_keep)
        return

    needed = target_keep - trimmed_count
    print(f"Need to add {needed} more days to reach {target_keep} after trim.")

    end_date = datetime.now()
    current = end_date
    added = 0
    total_processed = 0

    min_date = datetime(2024, 1, 1)

    while trimmed_count < target_keep and current >= min_date:
        if current.weekday() >= 5:
            current -= timedelta(days=1)
            continue

        date_str = current.strftime('%Y-%m-%d')

        if date_str in existing_dates:
            current -= timedelta(days=1)
            continue

        print(f"\nAttempting new date: {date_str}")
        data = download_fno_bhavcopy(current)

        if data is not None and not data.empty:
            data['date'] = date_str
            print(f"  ✅ Downloaded ({added+1})")

            processed = process_day_data(data, date_str)
            total_processed += processed
            added += 1
            existing_dates.add(date_str)
            print(f"  Stored {processed} records for {date_str}")

            trimmed_count = count_trimmed_days(target_keep)
            print(f"  Now {trimmed_count} days would remain after trim (target: {target_keep})")
        else:
            print(f"  ❌ No data for {date_str}")

        current -= timedelta(days=1)
        time.sleep(1)

    if added == 0:
        print("No new data added.")
    else:
        print(f"\nAdded {added} new trading days.")
        print(f"Total records added: {total_processed}")

    final_count = len(get_existing_dates())
    print(f"Database now has {final_count} distinct trading days total.")

    trimmed_final = count_trimmed_days(target_keep)
    print(f"After trimming to {target_keep} days, you will have {trimmed_final} days.")

    if trimmed_final < target_keep:
        print(f"⚠️ Only {trimmed_final} days available – reached 2024-01-01.")

    trim_old_data(target_keep)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical IV data")
    parser.add_argument('--target', type=int, default=253,
                        help='Number of trading days to keep after trimming (default: 253)')
    args = parser.parse_args()
    backfill(target_keep=args.target)