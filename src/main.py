"""Daily IVP/IVR report driver.

One report per trading day
--------------------------
The workflow fires on a 30-minute ladder from 16:30 to 00:00 IST. Every run
asks the same question — "has the report for today's trading day gone out yet?"
— and answers it from data/state.json, which the workflow commits. The first
run that finds the day's bhavcopy computes, sends the full report and records
the day as sent; every later run sees that and exits silently. So the user gets
exactly one report, as soon as the data is available, no matter how many slots
fire (or how late GitHub runs them).

If no data has appeared by the time the window closes (midnight IST), a single
"no data" alert is sent instead, and the day is closed.

Loud failure
------------
A send that fails is never swallowed: the run exits non-zero so the Actions job
goes red, and a note is pushed to TELEGRAM_ERROR_CHAT_ID (when configured).
"""

import sys
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config import (
    load_config, IV_WINDOW_DAYS, TRIM_KEEP_DAYS,
    now_ist, trading_day_for, window_closed,
)
from src.downloader import fetch_bhavcopy, OK, NOT_PUBLISHED, ERROR
from src.database import (
    init_database, store_daily_iv, store_daily_metrics,
    get_historical_ivs, get_symbol_history_count, get_data_coverage,
    trim_old_data, DB_PATH,
)
from src.metrics import compute_iv_rank_percentile
from src.contracts import compute_symbol_iv
from src.state import already_sent, mark_sent, already_failed, mark_failed
from src.telegram_bot import (
    send_telegram_message, send_error_notification,
    format_results, credentials_present,
)

RISK_FREE_RATE = 0.05


# ── metric computation ────────────────────────────────────
def compute_and_store_metrics(date):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT symbol, iv FROM daily_iv WHERE date = ?", (date,)
    ).fetchall()
    conn.close()
    if not rows:
        return []

    stock_metrics = []
    for symbol, current_iv in rows:
        hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
        window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
        ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
        store_daily_metrics(date, symbol, ivr, ivp, current_iv)
        stock_metrics.append({
            'symbol': symbol,
            'iv': round(current_iv, 1),
            'ivr': ivr,
            'ivp': ivp,
            'hist_days': get_symbol_history_count(symbol),
        })
    return stock_metrics


def load_metrics_for_date(date):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT symbol, current_iv, iv_rank, iv_percentile
           FROM daily_metrics WHERE date = ?""",
        (date,),
    ).fetchall()
    conn.close()
    if not rows:
        return []
    return [
        {
            'symbol': symbol,
            'iv': round(iv, 1),
            'ivr': ivr,
            'ivp': ivp,
            'hist_days': get_symbol_history_count(symbol),
        }
        for symbol, iv, ivr, ivp in rows
    ]


def process_bhavcopy(bhavcopy, date_str):
    """Compute and store IV + IVR/IVP for every symbol in one day's bhavcopy."""
    column_mapping = {
        'TckrSymb': 'SYMBOL',
        'ClsPric': 'CLOSE',
        'StrkPric': 'STRIKE_PR',
        'OptnTp': 'OPTION_TYP',
        'XpryDt': 'EXPIRY_DT',
        'UndrlygPric': 'UNDERLYING_PRICE',
    }
    rename_dict = {o: n for o, n in column_mapping.items() if o in bhavcopy.columns}
    if rename_dict:
        bhavcopy = bhavcopy.rename(columns=rename_dict)

    if 'OPTION_TYP' not in bhavcopy.columns:
        print("No OPTION_TYP column — cannot process this file")
        return 0

    options_data = bhavcopy[bhavcopy['OPTION_TYP'].isin(['CE', 'PE'])]
    if len(options_data) == 0:
        print("No options found in bhavcopy")
        return 0

    symbols = options_data['SYMBOL'].unique()
    today_dt = datetime.strptime(date_str, "%Y-%m-%d")

    # Group once instead of filtering the whole frame per symbol (O(n) not O(n²)).
    by_symbol = {sym: g for sym, g in bhavcopy.groupby('SYMBOL')}

    processed = 0
    for symbol in symbols:
        stock_data = by_symbol.get(symbol)
        if stock_data is None or len(stock_data) == 0:
            continue
        try:
            picked = compute_symbol_iv(stock_data, today_dt, RISK_FREE_RATE)
            if picked is None:
                continue
            current_iv, spot, expiry, atm_strike, option_type = picked
            store_daily_iv(date_str, symbol, current_iv, spot, str(expiry), atm_strike, option_type)

            hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
            window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
            ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
            store_daily_metrics(date_str, symbol, ivr, ivp, current_iv)
            processed += 1
        except Exception as e:
            print(f"Error with {symbol}: {e}")
            continue
    print(f"Processed {processed} symbols for {date_str}")
    return processed


# ── delivery ──────────────────────────────────────────────
def deliver_report(date_str, when, stock_metrics):
    """Send the full report. Returns True only if every message went out."""
    coverage = get_data_coverage()
    total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
    messages = format_results(stock_metrics, date_str, total_days, oldest, newest)

    print(f"Sending {len(messages)} Telegram message(s) for {date_str}...")
    ok = True
    for idx, msg in enumerate(messages):
        print(f"Sending part {idx+1}/{len(messages)}")
        if not send_telegram_message(msg):
            ok = False

    if not ok:
        send_error_notification(
            f"⚠️ *IVP/IVR delivery failed* — one or more messages for {date_str} "
            f"did not send. The run is marked failed and will retry on the next slot."
        )
        return False

    mark_sent(date_str, when.isoformat())
    print(f"=== Report for {date_str} delivered — day closed. ===")
    return True


def deliver_no_data(date_str, when, status):
    """Send the end-of-window 'no data' alert. Returns True if it went out."""
    reason = {
        NOT_PUBLISHED: "NSE never published a bhavcopy for this date (HTTP 404) — "
                       "it may have been a market holiday.",
        ERROR: "every download attempt failed (network or file-parse error).",
    }.get(status, "no usable data was found.")

    msg = (f"⚠️ *NSE IVP/IVR Report* — {date_str}\n\n"
           f"No report could be generated: {reason}\n\n"
           f"The retry window (16:30–24:00 IST) has closed. "
           f"Nothing more will be sent for {date_str}.")
    if send_error_notification(msg):
        mark_failed(date_str, when.isoformat())
        print(f"=== Sent 'no data' alert for {date_str} — day closed. ===")
        return True
    print("❌ Could not deliver the 'no data' alert either.")
    return False


# ── entry point ───────────────────────────────────────────
def main():
    now = now_ist()
    target = trading_day_for(now)
    target_str = target.strftime("%Y-%m-%d")
    print(f"=== NSE IVP/IVR run — {now:%Y-%m-%d %H:%M %Z} "
          f"(trading day under report: {target_str}) ===")

    load_config()
    init_database()

    if not credentials_present():
        print("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send any alert.")
        return 1

    # Already handled today? Nothing to do.
    if already_sent(target_str):
        print(f"Report for {target_str} already sent — exiting quietly.")
        return 0

    bhavcopy, status = fetch_bhavcopy(target)

    if status == OK and bhavcopy is not None:
        process_bhavcopy(bhavcopy, target_str)
        stock_metrics = load_metrics_for_date(target_str) or compute_and_store_metrics(target_str)
        if not stock_metrics:
            send_error_notification(
                f"⚠️ *IVP/IVR error* — the bhavcopy for {target_str} downloaded fine "
                f"but produced no IVs. Nothing was sent; the run will retry."
            )
            return 1
        if not deliver_report(target_str, now, stock_metrics):
            return 1
        trim_old_data(TRIM_KEEP_DAYS)
        return 0

    # No usable data this run.
    if window_closed(now):
        if already_failed(target_str):
            print(f"'No data' alert for {target_str} already sent — exiting quietly.")
            return 0
        return 0 if deliver_no_data(target_str, now, status) else 1

    print(f"No report for {target_str} yet (status={status}); will retry on the next slot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
