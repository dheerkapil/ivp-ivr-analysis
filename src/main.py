import os
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.config import load_config, get_project_root
from src.downloader import download_fno_bhavcopy
from src.database import init_database, store_daily_iv, store_daily_metrics, get_historical_ivs
from src.metrics import calculate_ivr, calculate_ivp
from src.telegram_bot import send_telegram_message, format_results

def safe_float(value):
    """Convert to float, handling None and NaN"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def main():
    print("=== NSE IVP/IVR Analysis Started ===")
    print(f"Time: {datetime.now()}")
    
    # Load config
    config = load_config()
    stocks = config['stocks']
    
    # Initialize database
    init_database()
    
    # Ensure output directory exists
    output_dir = get_project_root() / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Download today's bhavcopy
    print("\nDownloading F&O bhavcopy...")
    bhavcopy = download_fno_bhavcopy()
    
    if bhavcopy is None:
        print("Error: Could not download bhavcopy")
        return
    
    print(f"Downloaded {len(bhavcopy)} rows of data")
    
    # Map column names
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
    
    # Check required columns
    required_cols = ['SYMBOL', 'CLOSE', 'STRIKE_PR', 'OPTION_TYP']
    for col in required_cols:
        if col not in bhavcopy.columns:
            print(f"Error: Required column '{col}' not found in bhavcopy")
            return
    
    # Process each stock
    today = datetime.now().strftime("%Y-%m-%d")
    stock_metrics = []
    
    print("\nProcessing stocks...")
    
    for stock in stocks:
        try:
            # Find matching rows for this stock (case-insensitive)
            stock_data = bhavcopy[bhavcopy['SYMBOL'].str.upper() == stock]
            
            if len(stock_data) == 0:
                print(f"  {stock}: No data found")
                continue
            
            # --- Get spot price ---
            spot = 0.0
            if 'UNDERLYING_PRICE' in stock_data.columns:
                # Use underlying price from first row
                spot = safe_float(stock_data['UNDERLYING_PRICE'].iloc[0])
            if spot <= 0:
                # Try futures (OPTION_TYP == 'XX')
                futures = stock_data[stock_data['OPTION_TYP'] == 'XX']
                if len(futures) > 0:
                    spot = safe_float(futures['CLOSE'].iloc[0])
            if spot <= 0:
                # Fallback to first close price
                spot = safe_float(stock_data['CLOSE'].iloc[0])
            
            if spot <= 0:
                print(f"  {stock}: Invalid spot price ({spot})")
                continue
            
            # --- Get options (CE and PE) ---
            options = stock_data[stock_data['OPTION_TYP'].isin(['CE', 'PE'])]
            if len(options) == 0:
                print(f"  {stock}: No options found")
                continue
            
            # --- Find ATM strike ---
            strikes = options['STRIKE_PR'].unique()
            if len(strikes) == 0:
                print(f"  {stock}: No strikes found")
                continue
            
            # Convert strikes to float and find closest to spot
            strike_floats = [safe_float(s) for s in strikes]
            atm_strike = min(strike_floats, key=lambda x: abs(x - spot))
            
            # --- Find option at ATM strike (prefer CE) ---
            call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                # Try PE
                call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'PE')]
                if len(call) == 0:
                    print(f"  {stock}: No option at ATM strike {atm_strike}")
                    continue
            
            # --- Get option price ---
            opt_price = safe_float(call['CLOSE'].iloc[0])
            
            # --- Calculate IV approximation ---
            if opt_price > 0 and spot > 0:
                moneyness = abs(spot - atm_strike) / spot
                current_iv = 20 + (moneyness * 60)
                current_iv = max(10, min(80, current_iv))
            else:
                current_iv = 25.0  # default
            
            # --- Get expiry ---
            expiry = str(call['EXPIRY_DT'].iloc[0]) if 'EXPIRY_DT' in call.columns else 'N/A'
            
            # --- Store daily IV ---
            store_daily_iv(today, stock, current_iv, spot, expiry, atm_strike, 'CE')
            
            # --- Get historical data for IVR/IVP ---
            hist_data = get_historical_ivs(stock, days=252)
            
            if len(hist_data) > 0:
                historical_ivs = hist_data['iv'].tolist()
                ivr = calculate_ivr(current_iv, historical_ivs)
                ivp = calculate_ivp(current_iv, historical_ivs)
                store_daily_metrics(today, stock, ivr, ivp, current_iv)
            else:
                ivr = 50.0
                ivp = 50.0
                print(f"  {stock}: No historical data, using defaults")
            
            stock_metrics.append({
                'symbol': stock,
                'iv': round(current_iv, 1),
                'ivr': round(ivr, 1),
                'ivp': round(ivp, 1)
            })
            
            print(f"  {stock}: IV={current_iv:.1f}%, IVP={ivp:.0f}%, IVR={ivr:.1f}")
            
        except Exception as e:
            print(f"  {stock}: Error - {e}")
            traceback.print_exc()  # This will show the exact line number
            continue
    
    # Save results
    output_path = get_project_root() / "output" / "daily_ivp_ivr.json"
    output_data = {
        'date': today,
        'stocks': stock_metrics
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nResults saved to {output_path}")
    
    # Send Telegram
    print("\nSending Telegram notification...")
    if stock_metrics:
        message = format_results(stock_metrics, today)
        send_telegram_message(message)
    else:
        print("No metrics to send")
    
    print("\n=== Analysis Complete ===")
    
    if stock_metrics:
        high_ivp = [s for s in stock_metrics if s['ivp'] >= 80]
        low_ivp = [s for s in stock_metrics if s['ivp'] <= 20]
        print(f"\nSummary:")
        print(f"  Total stocks processed: {len(stock_metrics)}")
        print(f"  High IVP (>80%): {len(high_ivp)}")
        print(f"  Low IVP (<20%): {len(low_ivp)}")

if __name__ == "__main__":
    main()
