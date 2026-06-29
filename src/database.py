import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "iv_history.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_iv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            iv REAL,
            spot REAL,
            expiry TEXT,
            strike REAL,
            option_type TEXT,
            UNIQUE(date, symbol)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            iv_rank REAL,
            iv_percentile REAL,
            current_iv REAL,
            UNIQUE(date, symbol)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

def store_daily_iv(date, symbol, iv, spot, expiry, strike, option_type='CE'):
    """Store daily IV – force uppercase for symbol"""
    symbol = symbol.upper()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_iv 
        (date, symbol, iv, spot, expiry, strike, option_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date, symbol, iv, spot, expiry, strike, option_type))
    conn.commit()
    conn.close()

def store_daily_metrics(date, symbol, iv_rank, iv_percentile, current_iv):
    """Store daily metrics – force uppercase for symbol"""
    symbol = symbol.upper()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_metrics 
        (date, symbol, iv_rank, iv_percentile, current_iv)
        VALUES (?, ?, ?, ?, ?)
    ''', (date, symbol, iv_rank, iv_percentile, current_iv))
    conn.commit()
    conn.close()

def get_historical_ivs(symbol, days=252):
    """Get historical IV data for a symbol (case‑insensitive)"""
    conn = sqlite3.connect(DB_PATH)
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = '''
        SELECT date, iv FROM daily_iv 
        WHERE UPPER(symbol) = UPPER(?) AND date >= ?
        ORDER BY date DESC
    '''
    df = pd.read_sql_query(query, conn, params=(symbol, cutoff_date))
    conn.close()
    return df

def get_all_symbols():
    """Get all symbols in the database"""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT DISTINCT symbol FROM daily_iv"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df['symbol'].tolist()

def get_data_coverage():
    """Return (total_days, oldest_date, newest_date) from daily_iv table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT date), MIN(date), MAX(date) FROM daily_iv")
    result = cursor.fetchone()
    conn.close()
    return result  # (count, oldest, newest)

def get_symbol_history_count(symbol):
    """Return number of historical IV days for a given symbol (case‑insensitive)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT date) FROM daily_iv WHERE UPPER(symbol) = UPPER(?)", (symbol,))
    result = cursor.fetchone()[0]
    conn.close()
    return result
