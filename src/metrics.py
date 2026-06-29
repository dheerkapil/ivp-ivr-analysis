import pandas as pd
import numpy as np

def calculate_ivr(current_iv, historical_ivs):
    """
    Calculate IV Rank: (Current - Low) / (High - Low) * 100
    """
    if len(historical_ivs) == 0:
        return 50.0
    
    high = max(historical_ivs)
    low = min(historical_ivs)
    
    if high == low:
        return 50.0
    
    return ((current_iv - low) / (high - low)) * 100

def calculate_ivp(current_iv, historical_ivs):
    """
    Calculate IV Percentile: (% of days IV was below current)
    """
    if len(historical_ivs) == 0:
        return 50.0
    
    count_below = sum(1 for iv in historical_ivs if iv < current_iv)
    total = len(historical_ivs)
    
    return (count_below / total) * 100

def get_high_ivp_stocks(metrics, threshold=80):
    """Get stocks with IVP above threshold"""
    return [s for s in metrics if s['ivp'] >= threshold]

def get_low_ivp_stocks(metrics, threshold=20):
    """Get stocks with IVP below threshold"""
    return [s for s in metrics if s['ivp'] <= threshold]