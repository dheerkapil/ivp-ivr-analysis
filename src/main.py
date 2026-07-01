import os
import json
import sys
import sqlite3
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config import load_config, get_project_root
from src.downloader import download_fno_bhavcopy
from src.database import (
    init_database, store_daily_iv, store_daily_metrics,
    get_historical_ivs, get_symbol_history_count, get_data_coverage,
    trim_old_data, DB_PATH
)
from src.metrics import calculate_ivr, calculate_ivp
from src.telegram_bot import send_telegram_message, format_results

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def load_metrics_for_date(date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol, current_iv, iv_rank, iv_percentile
        FROM daily_metrics
        WHERE date = ?
    """, (date,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return []
    stock_metrics = []
    for symbol, iv, ivr, ivp in rows:
        hist_days = get_symbol_history_count(symbol)
        stock_metrics.append({
            'symbol': symbol,
            'iv': round(iv, 1),
            'ivr': round(ivr, 1),
            'ivp': round(ivp, 1),
            'hist_days': hist_days
        })
    return stock_metrics

def get_latest_data_date(table='daily_iv'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"SELECT MAX(date) FROM {table}")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def compute_and_store_metrics(date):
    """Compute IVP/IVR for all symbols on a given date using historical IVs, and store in daily_metrics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, iv FROM daily_iv WHERE date = ?", (date,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    stock_metrics = []
    for symbol, current_iv in rows:
        hist_data = get_historical_ivs(symbol, days=252)
        if len(hist_data) > 0:
            historical_ivs = hist_data['iv'].tolist()
            ivr = calculate_ivr(current_iv, historical_ivs)
            ivp = calculate_ivp(current_iv, historical_ivs)
        else:
            ivr = 50.0
            ivp = 50.0
        store_daily_metrics(date, symbol, ivr, ivp, current_iv)
        hist_days = get_symbol_history_count(symbol)
        stock_metrics.append({
            'symbol': symbol,
            'iv': round(current_iv, 1),
            'ivr': round(ivr, 1),
            'ivp': round(ivp, 1),
            'hist_days': hist_days
        })
    return stock_metrics

def send_report_for_date(date, data_label=None):
    # First try to load from metrics table
    stock_metrics = load_metrics_for_date(date)
    if not stock_metrics:
        # If metrics not found, compute them from IV data
        print(f"Metrics not found for {date}, computing from daily_iv...")
        stock_metrics = compute_and_store_metrics(date)
    if not stock_metrics:
        print(f"No data found for {date}")
        return False

    coverage = get_data_coverage()
    total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
    date_display = f"{date} (latest available: {data_label})" if data_label else date
    messages = format_results(stock_metrics, date_display, total_days, oldest, newest)
    for idx, msg in enumerate(messages):
        print(f"Sending part {idx+1}/{len(messages)}")
        send_telegram_message(msg)
    return True

def process_bhavcopy(bhavcopy):
    today = datetime.now().strftime("%Y-%m-%d")
    column_mapping = {
        'TckrSymb': 'SYMBOL',
        'ClsPric': 'CLOSE',
        'StrkPric': 'STRIKE_PR',
        'OptnTp': 'OPTION_TYP',
        'XpryDt': 'EXPIRY_DT',
        'UndrlygPric': 'UNDERLYING_PRICE'
    }
    rename_dict = {old: new for old, new in column_mapping.items() if old in bhavcopy.columns}
    if rename_dict:
        bhavcopy = bhavcopy.rename(columns=rename_dict)

    options_data = bhavcopy[bhavcopy['OPTION_TYP'].isin(['CE', 'PE'])]
    if len(options_data) == 0:
        print("No options found in bhavcopy")
        return

    symbols = options_data['SYMBOL'].unique()
    for symbol in symbols:
        try:
            stock_data = bhavcopy[bhavcopy['SYMBOL'] == symbol]
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

            options = stock_data[stock_data['OPTION_TYP'].isin(['CE', 'PE'])]
            if len(options) == 0:
                continue
            strikes = options['STRIKE_PR'].unique()
            if len(strikes) == 0:
                continue
            strike_floats = [safe_float(s) for s in strikes]
            atm_strike = min(strike_floats, key=lambda x: abs(x - spot))

            call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'PE')]
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

            store_daily_iv(today, symbol, current_iv, spot, expiry, atm_strike, 'CE')
            # Store metrics immediately (though will be recomputed later if needed)
            hist_data = get_historical_ivs(symbol, days=252)
            if len(hist_data) > 0:
                historical_ivs = hist_data['iv'].tolist()
                ivr = calculate_ivr(current_iv, historical_ivs)
                ivp = calculate_ivp(current_iv, historical_ivs)
                store_daily_metrics(today, symbol, ivr, ivp, current_iv)
            else:
                store_daily_metrics(today, symbol, 50.0, 50.0, current_iv)
        except Exception as e:
            print(f"Error with {symbol}: {e}")
            traceback.print_exc()
            continue

def main():
    print("=== NSE IVP/IVR Analysis Started ===")
    print(f"Time: {datetime.now()}")

    config = load_config()
    init_database()

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Check if we have metrics for today
    if load_metrics_for_date(today):
        print(f"✅ Sending report for today ({today})")
        send_report_for_date(today)
        trim_old_data(253)
        print("=== Analysis Complete (today's metrics present) ===")
        return

    # 2. If no today's metrics, check if we have IV data for today
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM daily_iv WHERE date = ?", (today,))
    count_today_iv = cursor.fetchone()[0]
    conn.close()

    if count_today_iv > 0:
        print(f"✅ Today's IV data found – computing metrics and sending report.")
        stock_metrics = compute_and_store_metrics(today)
        if stock_metrics:
            send_report_for_date(today)
            trim_old_data(253)
            print("=== Analysis Complete (metrics computed from IV) ===")
            return

    # 3. No today's data – get latest available date from daily_iv
    latest_iv_date = get_latest_data_date('daily_iv')
    if latest_iv_date:
        print(f"⚠️ No data for today. Sending latest available report from {latest_iv_date}")
        send_report_for_date(latest_iv_date, data_label="previous trading day")
        # Attempt to download today's data for future
        print("\nAttempting to download today's bhavcopy...")
        try:
            bhavcopy = download_fno_bhavcopy()
            if bhavcopy is not None:
                process_bhavcopy(bhavcopy)
                trim_old_data(253)
                print("✅ Today's data processed successfully.")
            else:
                print("No bhavcopy available today (market closed or not yet published).")
        except Exception as e:
            print(f"Download attempt failed: {e}")
        print("=== Analysis Complete (using latest available data) ===")
        return

    # 4. No data at all
    print("No data found in database. Sending notification.")
    msg = ("📊 *NSE IVP/IVR Report*\n\n"
           "No historical data available yet. Please run the "
           "**Backfill Historical Data** workflow from the Actions tab "
           "to build the database. After that, the daily report will appear here.")
    send_telegram_message(msg)

    # Attempt download anyway
    print("Attempting to download today's bhavcopy...")
    try:
        bhavcopy = download_fno_bhavcopy()
        if bhavcopy is not None:
            process_bhavcopy(bhavcopy)
            trim_old_data(253)
            print("✅ Today's data processed successfully.")
        else:
            print("No bhavcopy available today.")
    except Exception as e:
        print(f"Download attempt failed: {e}")

    print("=== Analysis Complete ===")

if __name__ == "__main__":
    main()