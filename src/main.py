import os
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config import load_config, get_project_root
from src.downloader import download_fno_bhavcopy
from src.database import (
    init_database, store_daily_iv, store_daily_metrics,
    get_historical_ivs, get_symbol_history_count, get_data_coverage
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

def main():
    print("=== NSE IVP/IVR Analysis Started ===")
    print(f"Time: {datetime.now()}")

    init_database()
    output_dir = get_project_root() / "output"
    output_dir.mkdir(exist_ok=True)

    print("\nDownloading F&O bhavcopy...")
    bhavcopy = download_fno_bhavcopy()
    if bhavcopy is None:
        print("Error: Could not download bhavcopy")
        return

    print(f"Downloaded {len(bhavcopy)} rows of data")

    # Column mapping (F&O bhavcopy format)
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
        print(f"Renamed columns: {rename_dict}")

    # Extract ALL symbols that have options (CE/PE)
    options_data = bhavcopy[bhavcopy['OPTION_TYP'].isin(['CE', 'PE'])]
    if len(options_data) == 0:
        print("No options found in bhavcopy")
        return

    symbols = options_data['SYMBOL'].unique()
    print(f"Found {len(symbols)} F&O symbols (stocks + indices)")

    today = datetime.now().strftime("%Y-%m-%d")
    stock_metrics = []

    print("\nProcessing symbols...")

    for symbol in symbols:
        try:
            stock_data = bhavcopy[bhavcopy['SYMBOL'] == symbol]
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
                print(f"  {symbol}: Invalid spot")
                continue

            # Options for this symbol
            options = stock_data[stock_data['OPTION_TYP'].isin(['CE', 'PE'])]
            if len(options) == 0:
                continue

            # ATM strike
            strikes = options['STRIKE_PR'].unique()
            if len(strikes) == 0:
                continue
            strike_floats = [safe_float(s) for s in strikes]
            atm_strike = min(strike_floats, key=lambda x: abs(x - spot))

            # Call option
            call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'PE')]
                if len(call) == 0:
                    continue

            opt_price = safe_float(call['CLOSE'].iloc[0])
            # Approx IV based on moneyness
            if opt_price > 0 and spot > 0:
                moneyness = abs(spot - atm_strike) / spot
                current_iv = 20 + (moneyness * 60)
                current_iv = max(10, min(80, current_iv))
            else:
                current_iv = 25.0

            expiry = str(call['EXPIRY_DT'].iloc[0]) if 'EXPIRY_DT' in call.columns else 'N/A'

            # Store today's IV (force uppercase)
            store_daily_iv(today, symbol.upper(), current_iv, spot, expiry, atm_strike, 'CE')

            # Get historical days for this symbol
            hist_days = get_symbol_history_count(symbol.upper())

            # Get historical IVs for IVR/IVP
            hist_data = get_historical_ivs(symbol.upper(), days=252)
            if len(hist_data) > 0:
                historical_ivs = hist_data['iv'].tolist()
                ivr = calculate_ivr(current_iv, historical_ivs)
                ivp = calculate_ivp(current_iv, historical_ivs)
                store_daily_metrics(today, symbol.upper(), ivr, ivp, current_iv)
            else:
                ivr = 50.0
                ivp = 50.0

            stock_metrics.append({
                'symbol': symbol.upper(),
                'iv': round(current_iv, 1),
                'ivr': round(ivr, 1),
                'ivp': round(ivp, 1),
                'hist_days': hist_days
            })

            print(f"  {symbol.upper()}: IV={current_iv:.1f}%, IVP={ivp:.0f}%, IVR={ivr:.1f}, Days={hist_days}")

        except Exception as e:
            print(f"  {symbol}: Error - {e}")
            traceback.print_exc()
            continue

    # Save JSON output
    output_path = get_project_root() / "output" / "daily_ivp_ivr.json"
    output_data = {'date': today, 'stocks': stock_metrics}
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to {output_path}")

    # Overall coverage for Telegram header
    coverage = get_data_coverage()
    total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)

    # Send Telegram
    print("\nSending Telegram notification...")
    if stock_metrics:
        message = format_results(stock_metrics, today, total_days, oldest, newest)
        send_telegram_message(message)
    else:
        print("No metrics to send")

    print("\n=== Analysis Complete ===")
    if stock_metrics:
        high_ivp = [s for s in stock_metrics if s['ivp'] >= 80]
        low_ivp = [s for s in stock_metrics if s['ivp'] <= 20]
        print(f"\nSummary:")
        print(f"  Total symbols processed: {len(stock_metrics)}")
        print(f"  High IVP (>80%): {len(high_ivp)}")
        print(f"  Low IVP (<20%): {len(low_ivp)}")

if __name__ == "__main__":
    main()
