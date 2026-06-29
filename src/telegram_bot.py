import os
import requests
from datetime import datetime

def send_telegram_message(message):
    """Send a message via Telegram bot"""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("Telegram credentials not found in environment")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False

def format_results(stock_metrics, date):
    """Format the results as a Telegram message"""
    if not stock_metrics:
        return "No data available for today"
    
    # Sort by IVP descending
    sorted_metrics = sorted(stock_metrics, key=lambda x: x['ivp'], reverse=True)
    
    message = f"📊 *NSE IVP/IVR Report* - {date}\n\n"
    message += "*Sorted by IV Percentile (Highest → Lowest)*\n\n"
    message += "```\n"
    message += "┌────────────┬──────┬──────┬──────┐\n"
    message += "│ STOCK      │ IV   │ IVP  │ IVR  │\n"
    message += "├────────────┼──────┼──────┼──────┤\n"
    
    for stock in sorted_metrics[:20]:  # Show top 20
        symbol = stock['symbol'][:10].ljust(10)
        iv = str(round(stock['iv'], 1)).ljust(4)
        ivp = str(int(round(stock['ivp']))).ljust(4)
        ivr = str(round(stock['ivr'], 1)).ljust(4)
        message += f"│ {symbol} │ {iv} │ {ivp}% │ {ivr} │\n"
    
    message += "└────────────┴──────┴──────┴──────┘\n"
    message += "```\n\n"
    
    # Add recommendations
    high_ivp = [s for s in sorted_metrics if s['ivp'] >= 80]
    low_ivp = [s for s in sorted_metrics if s['ivp'] <= 20]
    
    if high_ivp:
        message += f"🔴 *High IVP (>80%)*: {', '.join([s['symbol'] for s in high_ivp[:5]])}\n"
        message += "   *Consider credit spreads*\n\n"
    
    if low_ivp:
        message += f"🟢 *Low IVP (<20%)*: {', '.join([s['symbol'] for s in low_ivp[:5]])}\n"
        message += "   *Consider debit spreads*\n"
    
    return message