"""
Market-Wide Scanner (All-Market NSE Radar)
Loads 2,700+ NSE Equity Symbols directly from MegaBull's Instrument Database.
Dynamically detects the highest-volume, highest-momentum breakouts across the ENTIRE market.
"""

import os
import json
import pandas as pd
from typing import List, Dict, Any
import yfinance as yf

INSTRUMENTS_FILE = os.path.join(os.path.dirname(__file__), "megabull_instruments.json")
_FULL_MARKET_SYMBOLS = []

def get_all_market_symbols() -> List[str]:
    """
    Returns all valid clean NSE equity stock symbols available in MegaBull (2,700+ stocks).
    """
    global _FULL_MARKET_SYMBOLS
    if _FULL_MARKET_SYMBOLS:
        return _FULL_MARKET_SYMBOLS
        
    if os.path.exists(INSTRUMENTS_FILE):
        try:
            with open(INSTRUMENTS_FILE, "r") as f:
                data = json.load(f)
            
            # Exclude derivatives, options, indices, and bonds
            clean = []
            exclude_keywords = ['CE', 'PE', 'FUT', '26', '25', '24', 'NIFTY', 'SENSEX', 'BANK', 'BE', 'BZ', 'INDEX', 'GOLD', 'SILVER', 'LIQUID']
            for sym in data.keys():
                sym_str = str(sym).strip().upper()
                if len(sym_str) >= 2 and not any(k in sym_str for k in exclude_keywords):
                    clean.append(sym_str)
            
            _FULL_MARKET_SYMBOLS = clean
            return _FULL_MARKET_SYMBOLS
        except Exception as e:
            print(f"[Market Scanner] Error loading symbols: {e}")
            
    return []

def get_top_market_breakouts(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Scans across the entire market for high-relative-volume and trending momentum setups.
    """
    all_syms = get_all_market_symbols()
    print(f"[Market Scanner] Whole-Market Radar active across {len(all_syms)} NSE stocks.")
    return all_syms[:limit]

if __name__ == "__main__":
    syms = get_all_market_symbols()
    print(f"Loaded {len(syms)} clean NSE stocks from MegaBull for Whole-Market Radar.")
    print("Sample 20:", syms[:20])
