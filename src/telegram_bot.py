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
    # ... (keep the same as your current version)
