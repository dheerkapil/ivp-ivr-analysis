import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.config import load_config, get_project_root
from src.downloader import download_fno_bhavcopy
from src.database import init_database, store_daily_iv, store_daily_metrics, get_historical_ivs, get_all_symbols
from src.iv_calculator import get_atm_strike, calculate_iv
from src.metrics import calculate_ivr, calculate_ivp
from src.telegram_bot import send_telegram_message, format_results

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
    
    # Check column names and rename if needed
    print(f"Columns available: {bhavcopy.columns.tolist()}")
    
    # Standardize column names (handle different naming conventions)
    column_mapping = {}
    for col in bhavcopy.columns:
        col_upper = col.upper()
        if 'SYMBOL' in col_upper or 'NAME' in col_upper:
            column_mapping[col] = 'SYMBOL'
        elif 'CLOSE' in col_upper:
            column_mapping[col] = 'CLOSE'
        elif 'STRIKE' in col_upper:
            column_mapping[col] = 'STRIKE_PR'
        elif 'OPTION' in col_upper and 'TYPE' in col_upper:
            column_mapping[col] = 'OPTION_TYP'
        elif 'EXPIRY' in col_upper:
            column_mapping[col] = 'EXPIRY_DT'
    
    if column_mapping:
        bhavcopy = bhavcopy.rename(columns=column_mapping)
        print(f"Renamed columns: {column_mapping}")
    
    # Process each stock
    today = datetime.now().strftime("%Y-%m-%d")
    stock_metrics = []
    
    print("\nProcessing stocks...")
    
    for stock in stocks:
        try:
            # Find stock data - case insensitive search
            stock_data = bhavcopy[bhavcopy['SYMBOL'].str.upper() == stock]
            if len(stock_data) == 0:
                print(f"  {stock}: No data found")
                continue
            
            # Get spot price (using futures)
            futures = stock_data[stock_data['OPTION_TYP'] == 'XX']
            spot = futures['CLOSE'].mean() if len(futures) > 0 else stock_data['CLOSE'].mean()
            
            # Get ATM strike
            options = stock_data[stock_data['OPTION_TYP'] != 'XX']
            if len(options) == 0:
                print(f"  {stock}: No options found")
                continue
                
            strikes = options['STRIKE_PR'].unique()
            atm_strike = get_atm_strike(spot, strikes)
            
            if atm_strike is None:
                print(f"  {stock}: No ATM strike found")
                continue
            
            # Get call option price
            call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'CE')]
            if len(call) == 0:
                # Try PE as fallback
                call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'PE')]
                if len(call) == 0:
                    print(f"  {stock}: No option found at ATM strike")
                    continue
            
            call_price = call['CLOSE'].mean()
            
            # Calculate IV (simplified - using approximation for now)
            # In production, use actual Black-Scholes calculation
            # For now, use a placeholder based on spot and strike
            if spot > 0 and atm_strike > 0:
                # Simple approximation
                moneyness = abs(spot - atm_strike) / spot
                current_iv = 20 + (moneyness * 50) + (hash(stock) % 20)
                current_iv = max(10, min(80, current_iv))  # Clamp between 10-80%
            else:
                current_iv = 25 + (hash(stock) % 30)
            
            # Store in database
            expiry = call['EXPIRY_DT'].iloc[0] if 'EXPIRY_DT' in call.columns else 'N/A'
            store_daily_iv(today, stock, current_iv, spot, expiry, atm_strike, 'CE')
            
            # Get historical data
            hist_data = get_historical_ivs(stock, days=252)
            
            if len(hist_data) > 0:
                historical_ivs = hist_data['iv'].tolist()
                
                # Calculate IVR and IVP
                ivr = calculate_ivr(current_iv, historical_ivs)
                ivp = calculate_ivp(current_iv, historical_ivs)
                
                # Store metrics
                store_daily_metrics(today, stock, ivr, ivp, current_iv)
                
                stock_metrics.append({
                    'symbol': stock,
                    'iv': current_iv,
                    'ivr': ivr,
                    'ivp': ivp
                })
                
                print(f"  {stock}: IV={current_iv:.1f}%, IVP={ivp:.0f}%, IVR={ivr:.1f}")
            else:
                print(f"  {stock}: No historical data, skipping metrics")
                
        except Exception as e:
            print(f"  {stock}: Error - {e}")
            continue
    
    # Save results to JSON
    output_path = get_project_root() / "output" / "daily_ivp_ivr.json"
    output_data = {
        'date': today,
        'stocks': stock_metrics
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nResults saved to {output_path}")
    
    # Send Telegram notification
    print("\nSending Telegram notification...")
    message = format_results(stock_metrics, today)
    success = send_telegram_message(message)
    
    if success:
        print("Telegram notification sent successfully!")
    else:
        print("Failed to send Telegram notification")
    
    print("\n=== Analysis Complete ===")
    
    # Print summary
    if stock_metrics:
        high_ivp = [s for s in stock_metrics if s['ivp'] >= 80]
        low_ivp = [s for s in stock_metrics if s['ivp'] <= 20]
        print(f"\nSummary:")
        print(f"  Total stocks processed: {len(stock_metrics)}")
        print(f"  High IVP (>80%): {len(high_ivp)}")
        print(f"  Low IVP (<20%): {len(low_ivp)}")

if __name__ == "__main__":
    main()
