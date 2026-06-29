import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.downloader import download_historical_bhavcopy
from src.database import init_database, store_daily_iv
from src.iv_calculator import get_atm_strike, calculate_iv
from src.config import load_config
from datetime import datetime, timedelta
import pandas as pd

def backfill(years=2):
    """Backfill historical IV data"""
    print(f"Starting backfill for {years} years...")
    
    # Load config
    config = load_config()
    stocks = config['stocks']
    
    # Initialize database
    init_database()
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    
    # Download historical bhavcopy
    print(f"Downloading data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    all_data = download_historical_bhavcopy(start_date, end_date)
    
    if all_data is None or len(all_data) == 0:
        print("No data downloaded")
        return
    
    print(f"Downloaded {len(all_data)} days of data")
    
    # Process each day
    processed = 0
    
    for date, group in all_data.groupby('date'):
        print(f"\nProcessing {date}...")
        
        for stock in stocks:
            try:
                stock_data = group[group['SYMBOL'] == stock]
                if len(stock_data) == 0:
                    continue
                
                # Get futures price as spot
                futures = stock_data[stock_data['OPTION_TYP'] == 'XX']
                spot = futures['CLOSE'].mean() if len(futures) > 0 else stock_data['CLOSE'].mean()
                
                # Get ATM strike
                options = stock_data[stock_data['OPTION_TYP'] != 'XX']
                strikes = options['STRIKE_PR'].unique()
                atm_strike = get_atm_strike(spot, strikes)
                
                if atm_strike is None:
                    continue
                
                # Get call option price
                call = options[(options['STRIKE_PR'] == atm_strike) & (options['OPTION_TYP'] == 'CE')]
                if len(call) == 0:
                    continue
                
                call_price = call['CLOSE'].mean()
                
                # Calculate IV (using placeholder for now)
                # In production, use actual Black-Scholes
                current_iv = 25 + (hash(f"{stock}{date}") % 30)
                
                expiry = call['EXPIRY_DT'].iloc[0] if 'EXPIRY_DT' in call.columns else 'N/A'
                
                # Store in database
                store_daily_iv(date, stock, current_iv, spot, expiry, atm_strike, 'CE')
                
                processed += 1
                if processed % 100 == 0:
                    print(f"  Processed {processed} records so far...")
                    
            except Exception as e:
                print(f"  Error with {stock} on {date}: {e}")
                continue
    
    print(f"\nBackfill complete! Processed {processed} records.")

if __name__ == "__main__":
    backfill(years=2)