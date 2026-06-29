import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "iv_history.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for daily IV history
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
    
    # Table for daily metrics
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
    """Store daily IV for a stock"""
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
    """Store daily IVP and IVR metrics"""
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
    """Get historical IV data for a symbol"""
    conn = sqlite3.connect(DB_PATH)
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    query = '''
        SELECT date, iv FROM daily_iv 
        WHERE symbol = ? AND date >= ?
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