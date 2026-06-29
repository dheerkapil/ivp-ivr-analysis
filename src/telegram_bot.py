import os
import requests
from datetime import datetime

def send_telegram_message(message):
    """Send a message via Telegram bot"""
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
    if not stock_metrics:
        return "No data available for today"
    
    sorted_metrics = sorted(stock_metrics, key=lambda x: x['ivp'], reverse=True)
    
    # Coverage header
    coverage_line = ""
    if total_days > 0 and oldest and newest:
        coverage_line = f"📅 Historical data: {total_days} days (of 252) – from {oldest} to {newest}\n\n"
    elif total_days > 0:
        coverage_line = f"📅 Historical data: {total_days} days (of 252)\n\n"
    
    message = f"📊 *NSE IVP/IVR Report* - {date}\n\n"
    message += coverage_line
    message += "*Sorted by IV Percentile (Highest → Lowest)*\n\n"
    message += "```\n"
    
    # Header with fixed widths
    message += f"{'STOCK':<12} {'IVP':>6} {'IVR':>6} {'IV':>6} {'Days':>6}\n"
    message += f"{'-'*12} {'-'*6} {'-'*6} {'-'*6} {'-'*6}\n"
    
    # Rows (top 20)
    for stock in sorted_metrics[:20]:
        symbol = stock['symbol'][:12]
        ivp = f"{int(round(stock['ivp']))}%"
        ivr = f"{round(stock['ivr'], 1)}"
        iv = f"{round(stock['iv'], 1)}"
        days = str(stock.get('hist_days', 0))
        message += f"{symbol:<12} {ivp:>6} {ivr:>6} {iv:>6} {days:>6}\n"
    
    message += "```\n\n"
    
    # Recommendations
    high_ivp = [s for s in sorted_metrics if s['ivp'] >= 80]
    low_ivp = [s for s in sorted_metrics if s['ivp'] <= 20]
    
    if high_ivp:
        message += f"🔴 *High IVP (>80%)*: {', '.join([s['symbol'] for s in high_ivp[:5]])}\n"
        message += "   *Consider credit spreads*\n\n"
    
    if low_ivp:
        message += f"🟢 *Low IVP (<20%)*: {', '.join([s['symbol'] for s in low_ivp[:5]])}\n"
        message += "   *Consider debit spreads*\n\n"
    
    low_history = [s for s in sorted_metrics if s.get('hist_days', 0) < 30]
    if low_history:
        message += f"⚠️ *Low history (<30 days)*: {', '.join([s['symbol'] for s in low_history[:5]])}\n"
        message += "   IVP/IVR for these stocks are less reliable.\n"
    
    return message
