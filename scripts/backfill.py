import sys
import traceback
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent.parent))

from src.downloader import download_historical_bhavcopy
from src.database import init_database, store_daily_iv, prune_old_data

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def backfill(days=10):
    print(f"Starting backfill for the last {days} trading days...")
    init_database()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days*2)  # buffer for weekends/holidays

    print(f"Downloading data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    all_data = download_historical_bhavcopy(start_date, end_date)

    if all_data is None or len(all_data) == 0:
        print("No data downloaded")
        return

    print(f"Downloaded {len(all_data)} rows across all days")

    # Column mapping
    column_mapping = {
        'TckrSymb': 'SYMBOL',
        'ClsPric': 'CLOSE',
        'StrkPric': 'STRIKE_PR',
        'OptnTp': 'OPTION_TYP',
        'XpryDt': 'EXPIRY_DT',
        'UndrlygPric': 'UNDERLYING_PRICE'
    }
    rename_dict = {old: new for old, new in column_mapping.items() if old in all_data.columns}
    if rename_dict:
        all_data = all_data.rename(columns=rename_dict)
        print(f"Renamed columns: {rename_dict}")

    required_cols = ['SYMBOL', 'CLOSE', 'STRIKE_PR', 'OPTION_TYP']
    for col in required_cols:
        if col not in all_data.columns:
            print(f"Error: Required column '{col}' not found in bhavcopy")
            return

    processed = 0
    dates = sorted(all_data['date'].unique(), reverse=True)[:days]
    print(f"Processing {len(dates)} trading days (the most recent {days} days)")

    for date in dates:
        group = all_data[all_data['date'] == date]
        print(f"\nProcessing {date}...")
        options = group[group['OPTION_TYP'].isin(['CE', 'PE'])]
        symbols = options['SYMBOL'].unique()
        print(f"  Found {len(symbols)} symbols with options")

        for symbol in symbols:
            try:
                stock_data = group[group['SYMBOL'] == symbol]
                if len(stock_data) == 0:
                    continue

                # Spot
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

                store_daily_iv(date, symbol.upper(), current_iv, spot, expiry, atm_strike, 'CE')
                processed += 1
                if processed % 100 == 0:
                    print(f"  Processed {processed} records...")

            except Exception as e:
                print(f"  Error with {symbol} on {date}: {e}")
                traceback.print_exc()
                continue

    print(f"\nBackfill complete! Processed {processed} records.")
    
    # Always prune to keep only the most recent 504 trading days
    prune_old_data(days_to_keep=504)
    print("✅ Database pruned to 504 days.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical IV data")
    parser.add_argument('--days', type=int, default=10,
                        help='Number of recent trading days to backfill (default: 10)')
    args = parser.parse_args()
    backfill(days=args.days)
