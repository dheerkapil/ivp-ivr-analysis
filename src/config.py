import json
import os
from pathlib import Path

# ── IV rank / percentile window ───────────────────────────
# The rank/percentile is measured over a trailing window that INCLUDES the
# current reading. Including it keeps both metrics inside [0, 100] by
# construction — the current value cannot sit outside the window's own
# min/max. Excluding it is what let IVR exceed 100 on new highs and fall
# below 0 on new lows.
IV_WINDOW_DAYS = 365      # calendar days (~252 trading days = 1 year)
MIN_HISTORY_DAYS = 60     # don't publish a rank until this many observations
TRIM_KEEP_DAYS = 400      # retention — keep a little more than the window
YEAR_TRADING_DAYS = 252   # how many trading days we publish (the rolling year)


def load_config():
    """Load configuration from config/fno_stocks.json"""
    config_path = Path(__file__).parent.parent / "config" / "fno_stocks.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent
