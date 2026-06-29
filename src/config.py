import json
import os
from pathlib import Path

def load_config():
    """Load configuration from config/fno_stocks.json"""
    config_path = Path(__file__).parent.parent / "config" / "fno_stocks.json"
    with open(config_path, 'r') as f:
        return json.load(f)

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent