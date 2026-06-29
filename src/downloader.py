import pandas as pd
from datetime import datetime, timedelta
import time

def find_bhav_copy_function():
    """Find the correct bhavcopy function in nselib"""
    try:
        import nselib
        # Try different possible locations
        possible_locations = [
            (nselib, 'fno_bhav_copy'),
            (nselib, 'get_fno_bhav_copy'),
            (nselib.capital_market, 'fno_bhav_copy'),
            (nselib.capital_market, 'get_fno_bhav_copy'),
            (nselib.fno, 'fno_bhav_copy'),
            (nselib.fno, 'get_fno_bhav_copy'),
            (nselib, 'bhav_copy_fno'),
            (nselib.capital_market, 'bhav_copy_fno'),
        ]
        
        for module, func_name in possible_locations:
            if hasattr(module, func_name):
                return getattr(module, func_name)
        
        # If none found, try to find any function containing 'bhav'
        for module in [nselib, nselib.capital_market]:
            for attr_name in dir(module):
                if 'bhav' in attr_name.lower() and 'fno' in attr_name.lower():
                    print(f"Found possible function: {attr_name}")
                    return getattr(module, attr_name)
        
        return None
    except Exception as e:
        print(f"Error finding bhavcopy function: {e}")
        return None

def download_fno_bhavcopy(date=None):
    """
    Download F&O bhavcopy for given date
    Returns: DataFrame with option data
    """
    if date is None:
        date = datetime.now()
    
    try:
        # Find the correct function
        bhav_func = find_bhav_copy_function()
        if bhav_func is None:
            print("Could not find bhavcopy function in nselib")
            return None
        
        # Try to download
        bhavcopy = bhav_func(date.strftime("%d-%m-%Y"))
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
