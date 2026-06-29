from nselib.capital_market import fno_bhav_copy
import pandas as pd
from datetime import datetime, timedelta
import time

def download_fno_bhavcopy(date=None):
    """
    Download F&O bhavcopy for given date
    Returns: DataFrame with option data
    """
    if date is None:
        date = datetime.now()
    
    try:
        # Fetch bhavcopy using nselib
        bhavcopy = fno_bhav_copy(date.strftime("%d-%m-%Y"))
        return bhavcopy
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
            print(f"Downloading: {current.strftime('%Y-%m-%d')}")
            data = download_fno_bhavcopy(current)
            if data is not None:
                data['date'] = current.strftime('%Y-%m-%d')
                all_data.append(data)
            time.sleep(1)  # Be respectful to NSE servers
        current += timedelta(days=1)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
