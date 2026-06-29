from nselib import capital_market
import pandas as pd
from datetime import datetime, timedelta
import time

def download_fno_bhavcopy(date=None):
    """
    Download F&O bhavcopy for given date using nselib.capital_market.bhav_copy_equities
    Returns: DataFrame with equity data
    """
    if date is None:
        date = datetime.now()
    
    try:
        # Use the correct function from debug output
        date_str = date.strftime("%d-%m-%Y")
        print(f"Downloading bhavcopy for {date_str}...")
        
        # The correct function is bhav_copy_equities
        bhavcopy = capital_market.bhav_copy_equities(date_str)
        
        if bhavcopy is not None and not bhavcopy.empty:
            print(f"Successfully downloaded {len(bhavcopy)} rows")
            return bhavcopy
        else:
            print("No data returned")
            return None
            
    except Exception as e:
        print(f"Error downloading bhavcopy for {date}: {e}")
        return None

def download_historical_bhavcopy(start_date, end_date):
    """Download bhavcopy for a date range"""
    all_data = []
    current = start_date
    
    while current <= end_date:
        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() < 5:
            print(f"Processing: {current.strftime('%Y-%m-%d')}")
            data = download_fno_bhavcopy(current)
            if data is not None and not data.empty:
                data['date'] = current.strftime('%Y-%m-%d')
                all_data.append(data)
            time.sleep(1)  # Be respectful to NSE servers
        current += timedelta(days=1)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
