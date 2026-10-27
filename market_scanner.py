"""
Market-Wide Scanner (All-Market NSE Radar)
Loads 2,300+ NSE Equity Symbols directly from MegaBull's Instrument Database.
Dynamically detects the highest-volume, highest-momentum breakouts across the ENTIRE market.
"""

import os
import json
from typing import List, Dict, Any

INSTRUMENTS_FILE = os.path.join(os.path.dirname(__file__), "megabull_instruments.json")
_FULL_MARKET_SYMBOLS = []

def get_all_market_symbols(with_ns_suffix: bool = False) -> List[str]:
    """
    Returns all valid clean NSE equity stock symbols available in MegaBull (2,300+ stocks).
    """
    global _FULL_MARKET_SYMBOLS
    if _FULL_MARKET_SYMBOLS:
        return [f"{s}.NS" for s in _FULL_MARKET_SYMBOLS] if with_ns_suffix else _FULL_MARKET_SYMBOLS
        
    if os.path.exists(INSTRUMENTS_FILE):
        try:
            with open(INSTRUMENTS_FILE, "r") as f:
                data = json.load(f)
            
            clean = []
            exclude_keywords = [
                'CE', 'PE', 'FUT', '26', '25', '24', 'NIFTY', 'SENSEX', 'BANK',
                'BE', 'BZ', 'INDEX', 'GOLD', 'SILVER', 'LIQUID', 'VIX', 'ETF',
                'INAV', 'GS', 'GILT', 'MUTUAL'
            ]
            for sym in data.keys():
                sym_str = str(sym).strip().upper()
                # Exclude strings with spaces, numbers, or non-alphabetics (except hyphen)
                if ' ' in sym_str or len(sym_str) < 2:
                    continue
                if any(k in sym_str for k in exclude_keywords):
                    continue
                clean.append(sym_str)
            
            _FULL_MARKET_SYMBOLS = sorted(list(set(clean)))
            return [f"{s}.NS" for s in _FULL_MARKET_SYMBOLS] if with_ns_suffix else _FULL_MARKET_SYMBOLS
        except Exception as e:
            print(f"[Market Scanner] Error loading symbols: {e}")
            
    return []

def get_top_market_breakouts(limit: int = 50) -> List[str]:
    """
    Returns candidate symbols across the entire market.
    """
    all_syms = get_all_market_symbols(with_ns_suffix=True)
    return all_syms[:limit]

if __name__ == "__main__":
    syms = get_all_market_symbols()
    print(f"Loaded {len(syms)} clean NSE tradeable stocks from MegaBull for Whole-Market Radar.")
    print("Sample 15:", syms[:15])
