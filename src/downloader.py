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
        # NSE F&O bhavcopy URL format
        date_str = date.strftime("%d%m%Y")
        
        # Try the standard NSE URL for F&O bhavcopy
        url = f"https://archives.nseindia.com/content/nsccl/fo{date_str}.csv.zip"
        
        print(f"Downloading F&O bhavcopy from: {url}")
        
        # Download the zip file
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/zip'
        })
        
        if response.status_code != 200:
            print(f"Failed to download: HTTP {response.status_code}")
            # Try alternative URL
            alt_url = f"https://archives.nseindia.com/content/nsccl/fo{date.strftime('%d%b%Y').upper()}.csv.zip"
            print(f"Trying alternative: {alt_url}")
            response = requests.get(alt_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
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
            time.sleep(2)  # Be respectful to NSE servers
        current += timedelta(days=1)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
