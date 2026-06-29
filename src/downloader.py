import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import zipfile
from io import BytesIO

def download_fno_bhavcopy(date=None):
    """
    Download F&O bhavcopy directly from NSE website
    Returns: DataFrame with F&O data
    """
    if date is None:
        date = datetime.now()
    
    try:
        # Correct URL format
        date_str = date.strftime("%Y%m%d")
        url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
        
        print(f"Downloading F&O bhavcopy from: {url}")
        
        # Use a more complete browser-like header
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Download with a longer timeout and allow redirects
        response = requests.get(url, timeout=60, headers=headers, allow_redirects=True)
        
        if response.status_code != 200:
            print(f"Failed to download: HTTP {response.status_code}")
            # Try alternative URL with lowercase
            alt_url = f"https://nsearchives.nseindia.com/content/fo/bhavcopy_nse_fo_0_0_0_{date_str}_f_0000.csv.zip"
            print(f"Trying alternative: {alt_url}")
            response = requests.get(alt_url, timeout=60, headers=headers, allow_redirects=True)
            
            if response.status_code != 200:
                print(f"Alternative also failed: HTTP {response.status_code}")
                return None
        
        # Read the zip content directly into pandas
        with zipfile.ZipFile(BytesIO(response.content)) as z:
            # Find the CSV file inside the zip
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
            if not csv_files:
                print("No CSV file found in zip")
                return None
            
            # Read the first CSV file
            with z.open(csv_files[0]) as f:
                df = pd.read_csv(f)
        
        print(f"Successfully downloaded {len(df)} rows of F&O data")
        return df
        
    except Exception as e:
        print(f"Error downloading F&O bhavcopy for {date}: {e}")
        return None

def download_historical_bhavcopy(start_date, end_date):
    """Download F&O bhavcopy for a date range"""
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
            time.sleep(3)  # Increased delay to be more respectful
        current += timedelta(days=1)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
