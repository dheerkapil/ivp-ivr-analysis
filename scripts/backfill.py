while downloaded_days < days:
    if current.weekday() >= 5:
        current -= timedelta(days=1)
        continue

    print(f"\nAttempting: {current.strftime('%Y-%m-%d')}")
    data = download_fno_bhavcopy(current)
    if data is not None and not data.empty:
        date_str = current.strftime('%Y-%m-%d')
        data['date'] = date_str
        print(f"  ✅ Downloaded ({downloaded_days+1}/{days})")
        
        processed = process_day_data(data, date_str)
        total_processed += processed
        downloaded_days += 1
        processed_dates.append(date_str)
        print(f"  Stored {processed} records for {date_str}")
    else:
        print(f"  ❌ No data for {current.strftime('%Y-%m-%d')}")

    current -= timedelta(days=1)
    time.sleep(1)