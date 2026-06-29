import os
import requests
from datetime import datetime

def send_telegram_message(message):
    """Send a single message via Telegram bot"""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("❌ Telegram credentials not found in environment")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        print(f"📤 Sending message (length: {len(message)} chars)")
        response = requests.post(url, json=payload, timeout=10)
        print(f"📥 Response status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Telegram notification sent successfully!")
            return True
        else:
            print(f"❌ Telegram API error: {response.status_code} - {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Exception sending Telegram message: {e}")
        return False

def format_results(stock_metrics, date, total_days=0, oldest=None, newest=None):
    """Return a list of messages (each <= 4096 chars) to send"""
    if not stock_metrics:
        return ["No data available for today"]
    
    sorted_metrics = sorted(stock_metrics, key=lambda x: x['ivp'], reverse=True)
    
    # Build the header (common for all messages)
    coverage_line = ""
    if total_days > 0 and oldest and newest:
        coverage_line = f"📅 Historical data: {total_days} days (of 252) – from {oldest} to {newest}\n\n"
    elif total_days > 0:
        coverage_line = f"📅 Historical data: {total_days} days (of 252)\n\n"
    
    header = f"📊 *NSE IVP/IVR Report* - {date}\n\n"
    header += coverage_line
    header += f"*Total symbols: {len(sorted_metrics)}*\n\n"
    header += "*Sorted by IV Percentile (Highest → Lowest)*\n\n"
    header += "```\n"
    header += f"{'STOCK':<12} {'IVP':>6} {'IVR':>6} {'IV':>6} {'Days':>6}\n"
    header += f"{'-'*12} {'-'*6} {'-'*6} {'-'*6} {'-'*6}\n"
    
    # Build rows
    rows = []
    for stock in sorted_metrics:
        symbol = stock['symbol'][:12]
        ivp = f"{int(round(stock['ivp']))}%"
        ivr = f"{round(stock['ivr'], 1)}"
        iv = f"{round(stock['iv'], 1)}"
        days = str(stock.get('hist_days', 0))
        rows.append(f"{symbol:<12} {ivp:>6} {ivr:>6} {iv:>6} {days:>6}")
    
    # Split rows into chunks of 50 (adjust if needed)
    chunk_size = 50
    messages = []
    
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i+chunk_size]
        body = "\n".join(chunk)
        # Add closing code block for each chunk
        if i == 0:
            # First message includes header and first chunk
            full_msg = header + body + "\n```"
        else:
            # Subsequent messages just have the table continuation
            full_msg = f"*Continued...*\n\n```\n" + body + "\n```"
        
        # Append footer only to the last message
        if i + chunk_size >= len(rows):
            full_msg += "\n\n" + footer_text(sorted_metrics)
        
        messages.append(full_msg)
    
    return messages

def footer_text(sorted_metrics):
    """Generate recommendations and warnings (common for all)"""
    high_ivp = [s for s in sorted_metrics if s['ivp'] >= 80]
    low_ivp = [s for s in sorted_metrics if s['ivp'] <= 20]
    low_history = [s for s in sorted_metrics if s.get('hist_days', 0) < 30]
    
    footer = ""
    if high_ivp:
        footer += f"\n🔴 *High IVP (>80%)*: {', '.join([s['symbol'] for s in high_ivp[:5]])}"
        if len(high_ivp) > 5:
            footer += f" and {len(high_ivp)-5} more"
        footer += "\n   *Consider credit spreads*"
    
    if low_ivp:
        footer += f"\n\n🟢 *Low IVP (<20%)*: {', '.join([s['symbol'] for s in low_ivp[:5]])}"
        if len(low_ivp) > 5:
            footer += f" and {len(low_ivp)-5} more"
        footer += "\n   *Consider debit spreads*"
    
    if low_history:
        footer += f"\n\n⚠️ *Low history (<30 days)*: {', '.join([s['symbol'] for s in low_history[:5]])}"
        if len(low_history) > 5:
            footer += f" and {len(low_history)-5} more"
        footer += "\n   IVP/IVR for these stocks are less reliable."
    
    return footer