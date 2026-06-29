import nselib
from nselib import capital_market
from datetime import datetime

print("=== nselib attributes ===")
for attr in dir(nselib):
    if not attr.startswith('_'):
        print(f"  {attr}")

print("\n=== capital_market attributes ===")
for attr in dir(capital_market):
    if not attr.startswith('_'):
        print(f"  {attr}")

print("\n=== Searching for bhavcopy functions ===")
for attr in dir(nselib):
    if 'bhav' in attr.lower():
        print(f"  nselib has: {attr}")

for attr in dir(capital_market):
    if 'bhav' in attr.lower():
        print(f"  capital_market has: {attr}")

print("\n=== Attempting to download ===")
date_str = datetime.now().strftime('%d-%m-%Y')
print(f"Date: {date_str}")

if hasattr(capital_market, 'fno_bhav_copy'):
    print("Found capital_market.fno_bhav_copy - trying...")
    try:
        result = capital_market.fno_bhav_copy(date_str)
        print(f"Success! Result type: {type(result)}")
    except Exception as e:
        print(f"Error: {e}")

if hasattr(nselib, 'fno_bhav_copy'):
    print("Found nselib.fno_bhav_copy - trying...")
    try:
        result = nselib.fno_bhav_copy(date_str)
        print(f"Success! Result type: {type(result)}")
    except Exception as e:
        print(f"Error: {e}")
