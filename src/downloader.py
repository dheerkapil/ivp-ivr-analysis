import pandas as pd
from datetime import datetime, timedelta
import time

def get_bhavcopy_function():
    """
    Dynamically find the correct bhavcopy function in nselib
    """
    try:
        import nselib
        
        # List of possible function locations and names
        possible_functions = [
            # Format: (module, function_name)
            (nselib, 'fno_bhav_copy'),
            (nselib, 'get_fno_bhav_copy'),
            (nselib, 'bhav_copy_fno'),
            (nselib, 'get_bhav_copy_fno'),
            (nselib.capital_market, 'fno_bhav_copy'),
            (nselib.capital_market, 'get_fno_bhav_copy'),
            (nselib.capital_market, 'bhav_copy_fno'),
            (nselib.capital_market, 'get_bhav_copy_fno'),
            (nselib.fno, 'fno_bhav_copy'),
            (nselib.fno, 'get_fno_bhav_copy'),
        ]
        
        # Try each possible function
        for module, func_name in possible_functions:
            if hasattr(module, func_name):
                print(f"Found function: {module.__name__}.{func_name}")
                return getattr(module, func_name)
        
        # If not found, search for any function with 'bhav' in name
        for module in [nselib, nselib.capital_market]:
            if hasattr(module, '__name__'):
                for attr_name in dir(module):
                    if 'bhav' in attr_name.lower() and 'fno' in attr_name.lower():
                        print(f"Found alternative function: {module.__name__}.{attr_name}")
                        return getattr(module, attr_name)
        
        print("No bhavcopy function found in nselib")
        return None
        
    except ImportError:
        print("nselib not installed")
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
        bhav_func = get_bhavcopy_function()
        
        if bhav_func is None:
            print("Could not find bhavcopy function in nselib")
            return None
        
        # Download the data
        date_str = date.strftime("%d-%m-%Y")
        print(f"Downloading bhavcopy for {date_str}...")
        bhavcopy = bhav_func(date_str)
        
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
