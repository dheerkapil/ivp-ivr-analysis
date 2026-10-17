import sys
import traceback
import argparse
import bisect
from pathlib import Path
from datetime import datetime, timedelta
import time
import pandas as pd
import sqlite3

sys.path.append(str(Path(__file__).parent.parent))

from src.downloader import download_fno_bhavcopy
from src.database import init_database, store_daily_iv, DB_PATH
from src.iv_calculator import calculate_iv
from src.metrics import calculate_ivr, calculate_ivp, compute_iv_rank_percentile
from src.config import IV_WINDOW_DAYS, YEAR_TRADING_DAYS
from src.daily_files import export_all


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


def process_day_data(df, date_str):
    """
    Process a single day's DataFrame and store IVs using true Black-Scholes IV.
    date_str: YYYY-MM-DD
    """
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

    today_dt = datetime.strptime(date_str, "%Y-%m-%d")
    risk_free_rate = 0.05  # 5% – you can adjust

    processed = 0
    for symbol in symbols:
        try:
            stock_data = df[df['SYMBOL'] == symbol]
            if len(stock_data) == 0:
                continue

            # Spot price
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

            # Get ATM option (prefer CE, else PE)
            call = opts[(opts['STRIKE_PR'] == atm_strike) & (opts['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                call = opts[(opts['STRIKE_PR'] == atm_strike) & (opts['OPTION_TYP'] == 'PE')]
                if len(call) == 0:
                    continue

            opt_price = safe_float(call['CLOSE'].iloc[0])
            expiry_str = call['EXPIRY_DT'].iloc[0] if 'EXPIRY_DT' in call.columns else None
            if expiry_str:
                try:
                    expiry_dt = datetime.strptime(expiry_str, "%d-%b-%Y")
                except:
                    expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                time_to_expiry = (expiry_dt - today_dt).days / 365.0
                time_to_expiry = max(time_to_expiry, 0.001)
            else:
                time_to_expiry = 0.05  # fallback ~18 days

            option_type = call['OPTION_TYP'].iloc[0]  # 'CE' or 'PE'

            # ---- Calculate true IV ----
            if opt_price > 0 and spot > 0 and atm_strike > 0 and time_to_expiry > 0:
                try:
                    current_iv = calculate_iv(opt_price, spot, atm_strike, time_to_expiry, risk_free_rate, option_type)
                    current_iv = max(5, min(150, current_iv))
                except Exception as e:
                    print(f"    IV calc failed for {symbol}: {e}, using placeholder")
                    moneyness = abs(spot - atm_strike) / spot
                    current_iv = 20 + (moneyness * 60)
            else:
                moneyness = abs(spot - atm_strike) / spot
                current_iv = 20 + (moneyness * 60)

            expiry = str(call['EXPIRY_DT'].iloc[0]) if 'EXPIRY_DT' in call.columns else 'N/A'
            store_daily_iv(date_str, symbol, current_iv, spot, expiry, atm_strike, option_type)
            processed += 1
            if processed % 100 == 0:
                print(f"    Processed {processed} records...")

        except Exception as e:
            print(f"    Error with {symbol}: {e}")
            traceback.print_exc()
            continue

    return processed


def compute_all_metrics(window_days=IV_WINDOW_DAYS):
    """
    Compute IVP/IVR for every (date, symbol) using a trailing window that ends
    on that date (not "now"), then store into daily_metrics.

    The daily run uses datetime.now() for its window, which is correct for
    today's reading but wrong for history – hence this separate pass.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT symbol, date, iv FROM daily_iv ORDER BY symbol, date"
    ).fetchall()
    conn.close()

    if not rows:
        print("compute_all_metrics: no IV data")
        return 0

    by_symbol = {}
    for sym, d, iv in rows:
        by_symbol.setdefault(sym, []).append((d, iv))

    metric_rows = []
    for sym, series in by_symbol.items():
        dates = [x[0] for x in series]
        ivs = [x[1] for x in series]
        for i, d in enumerate(dates):
            cutoff = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=window_days)).strftime("%Y-%m-%d")
            lo = bisect.bisect_left(dates, cutoff)
            window = ivs[lo:i + 1]   # window INCLUDES the current reading
            cur = ivs[i]
            ivr, ivp = compute_iv_rank_percentile(cur, window)
            metric_rows.append((d, sym, ivr, ivp, cur))

    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        """INSERT OR REPLACE INTO daily_metrics
           (date, symbol, iv_rank, iv_percentile, current_iv)
           VALUES (?, ?, ?, ?, ?)""",
        metric_rows,
    )
    conn.commit()
    conn.close()
    print(f"compute_all_metrics: {len(metric_rows)} rows across {len({r[0] for r in metric_rows})} dates")
    return len(metric_rows)


def backfill(target_days=500):
    print(f"Starting backfill – target: collect {target_days} total trading days (no trimming).")
    init_database()

    existing_dates = get_existing_dates()
    existing_count = len(existing_dates)
    print(f"Currently have {existing_count} distinct trading days.")

    if existing_count >= target_days:
        print(f"Already have {existing_count} days – no additional days needed.")
    else:
        needed = target_days - existing_count
        print(f"Need to add {needed} new trading days.")

        end_date = datetime.now()
        current = end_date
        added = 0
        total_processed = 0

        min_date = datetime(2024, 1, 1)

        while added < needed and current >= min_date:
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
                print(f"  ✅ Downloaded ({added+1}/{needed})")

                processed = process_day_data(data, date_str)
                total_processed += processed
                added += 1
                existing_dates.add(date_str)
                print(f"  Stored {processed} records for {date_str}")
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

    # ---- Compute IVP/IVR for every historical date ----
    compute_all_metrics()

    # ---- Write one file per day (durable backup + daily repo activity) ----
    # Publish only the rolling year; earlier days were warm-up for the ranks.
    export_all(keep_last=YEAR_TRADING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical IV data without trimming")
    parser.add_argument('--target', type=int, default=YEAR_TRADING_DAYS + 60,
                        help='Number of trading days to collect (default: a year + warm-up)')
    args = parser.parse_args()
    backfill(target_days=args.target)
