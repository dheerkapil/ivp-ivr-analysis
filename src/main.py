import os
import json
import sys
import sqlite3
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config import load_config, get_project_root, IV_WINDOW_DAYS, TRIM_KEEP_DAYS
from src.downloader import download_fno_bhavcopy
from src.database import (
    init_database, store_daily_iv, store_daily_metrics,
    get_historical_ivs, get_symbol_history_count, get_data_coverage,
    trim_old_data, DB_PATH
)
from src.metrics import calculate_ivr, calculate_ivp, compute_iv_rank_percentile
from src.iv_calculator import calculate_iv
from src.contracts import compute_symbol_iv
from src.telegram_bot import send_telegram_message, format_results

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def compute_and_store_metrics(date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, iv FROM daily_iv WHERE date = ?", (date,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    stock_metrics = []
    for symbol, current_iv in rows:
        hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
        window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
        ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
        store_daily_metrics(date, symbol, ivr, ivp, current_iv)
        hist_days = get_symbol_history_count(symbol)
        stock_metrics.append({
            'symbol': symbol,
            'iv': round(current_iv, 1),
            'ivr': ivr,
            'ivp': ivp,
            'hist_days': hist_days
        })
    return stock_metrics

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
            'ivr': ivr,
            'ivp': ivp,
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

def process_bhavcopy(bhavcopy, date_str):
    """Process a bhavcopy for a specific date (date_str in YYYY-MM-DD)"""
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
    today_dt = datetime.strptime(date_str, "%Y-%m-%d")
    risk_free_rate = 0.05

    for symbol in symbols:
        try:
            stock_data = bhavcopy[bhavcopy['SYMBOL'] == symbol]
            if len(stock_data) == 0:
                continue

            picked = compute_symbol_iv(stock_data, today_dt, risk_free_rate)
            if picked is None:
                continue
            current_iv, spot, expiry, atm_strike, option_type = picked
            store_daily_iv(date_str, symbol, current_iv, spot, str(expiry), atm_strike, option_type)

            hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
            window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
            ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
            store_daily_metrics(date_str, symbol, ivr, ivp, current_iv)
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

    # Check if we have IV data for today
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM daily_iv WHERE date = ?", (today,))
    count_today_iv = cursor.fetchone()[0]
    conn.close()

    if count_today_iv > 0:
        print(f"✅ Today's IV data found – recomputing metrics for {today}.")
        stock_metrics = compute_and_store_metrics(today)
        coverage = get_data_coverage()
        total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
        print("\nSending Telegram notification...")
        messages = format_results(stock_metrics, today, total_days, oldest, newest)
        for idx, msg in enumerate(messages):
            print(f"Sending part {idx+1}/{len(messages)}")
            send_telegram_message(msg)
        trim_old_data(TRIM_KEEP_DAYS)
        print("=== Analysis Complete (metrics recomputed) ===")
        return

    # If no today's IV, try to download today's bhavcopy; if fails, fallback to previous days
    print("No today's IV found. Attempting to download bhavcopy...")

    # Try to download starting from today, going backwards up to 10 days
    max_days_back = 10
    bhavcopy = None
    date_used = None
    for offset in range(max_days_back + 1):
        candidate_date = datetime.now() - timedelta(days=offset)
        if candidate_date.weekday() >= 5:  # skip weekends
            continue
        candidate_date_str = candidate_date.strftime("%Y-%m-%d")
        print(f"Attempting to download bhavcopy for {candidate_date_str}...")
        bhavcopy = download_fno_bhavcopy(candidate_date)
        if bhavcopy is not None:
            date_used = candidate_date_str
            print(f"✅ Downloaded bhavcopy for {date_used}")
            break
        else:
            print(f"❌ No bhavcopy for {candidate_date_str}")

    if bhavcopy is not None and date_used is not None:
        # Process the downloaded bhavcopy for the found date
        process_bhavcopy(bhavcopy, date_used)
        stock_metrics = load_metrics_for_date(date_used)
        if not stock_metrics:
            stock_metrics = compute_and_store_metrics(date_used)
        coverage = get_data_coverage()
        total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
        print("\nSending Telegram notification...")
        messages = format_results(stock_metrics, date_used, total_days, oldest, newest)
        for idx, msg in enumerate(messages):
            print(f"Sending part {idx+1}/{len(messages)}")
            send_telegram_message(msg)
        trim_old_data(TRIM_KEEP_DAYS)
        print(f"=== Analysis Complete (fresh download from {date_used}) ===")
        return

    # If no bhavcopy found at all, fallback to latest cached
    print("No bhavcopy found for recent days. Sending latest cached report.")
    latest_date = get_latest_data_date('daily_iv')
    if latest_date:
        stock_metrics = load_metrics_for_date(latest_date)
        if not stock_metrics:
            stock_metrics = compute_and_store_metrics(latest_date)
        coverage = get_data_coverage()
        total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
        messages = format_results(stock_metrics, latest_date, total_days, oldest, newest)
        for idx, msg in enumerate(messages):
            print(f"Sending part {idx+1}/{len(messages)}")
            send_telegram_message(msg)
        print("=== Analysis Complete (cached) ===")
        return

    # No data at all
    msg = ("📊 *NSE IVP/IVR Report*\n\n"
           "No historical data available yet. Please run the "
           "**Backfill Historical Data** workflow from the Actions tab "
           "to build the database. After that, the daily report will appear here.")
    send_telegram_message(msg)
    print("=== Analysis Complete ===")

if __name__ == "__main__":
    main()