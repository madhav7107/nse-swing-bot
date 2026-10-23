"""
Opening Range Breakout (ORB) Strategy with Midpoint Stop Loss
Inspired by Jake Schincariol's Day Trader Skill v2 (Pack of 11 skills).

Mechanics:
1. Opening Range: 09:15 AM to 09:30 AM IST (15-minute bar).
2. Entry: 5-minute bar closes strictly above 15m high (BUY) or below 15m low (SELL).
3. Stop Loss: Exactly at the midpoint of the 15-minute range (cuts risk by 50%).
4. Target: 2 times the risk (2R institutional target).
5. EOD Rule: Must be squared off (flat) by 03:15 PM IST.
"""

import pandas as pd
from typing import Dict, Any, Optional
import config
from data_engine import get_stock_data, get_latest_price

def analyze_orb_signal(df_5m: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Scans for a 15-minute Opening Range Breakout on 5-minute candlestick data.
    """
    if df_5m is None or len(df_5m) < 4:
        return None
        
    now_ist = config.get_ist_now()
    
    # Needs to be between 09:30 AM and 02:45 PM IST
    if now_ist.hour < 9 or (now_ist.hour == 9 and now_ist.minute < 30):
        return None
    if now_ist.hour > 14 or (now_ist.hour == 14 and now_ist.minute > 45):
        return None
        
    # Isolate today's bars
    try:
        df_today = df_5m.copy()
        
        # First 3 bars (09:15, 09:20, 09:25) constitute the 15-minute opening range
        orb_bars = df_today.iloc[:3]
        orb_high = float(orb_bars["High"].max())
        orb_low = float(orb_bars["Low"].min())
        orb_range = orb_high - orb_low
        
        # Reject abnormal ranges (e.g., massive circuit limit moves)
        if orb_range <= 0 or (orb_range / orb_low) > 0.05:
            return None
            
        orb_midpoint = round((orb_high + orb_low) / 2.0, 2)
        
        # Check current / latest completed bar
        latest_bar = df_today.iloc[-1]
        current_close = float(latest_bar["Close"])
        current_volume = float(latest_bar.get("Volume", 0))
        avg_volume = float(df_today["Volume"].mean()) if "Volume" in df_today else 1.0
        
        # Bullish Breakout: Bar closed above ORB high
        if current_close > orb_high and current_volume >= avg_volume * 0.8:
            risk = current_close - orb_midpoint
            if risk <= 0:
                return None
            target = round(current_close + (2.0 * risk), 2)
            
            return {
                "symbol": symbol,
                "strategy": "ORB_MIDPOINT_BREAKOUT",
                "pattern": "15-Min Opening Range Breakout (Bullish)",
                "direction": "BUY",
                "entry_price": round(current_close, 2),
                "stop_loss": orb_midpoint,
                "target_price": target,
                "risk_per_share": round(risk, 2),
                "rr_ratio": 2.0,
                "confluence_score": 85,
                "orb_high": round(orb_high, 2),
                "orb_low": round(orb_low, 2),
                "orb_midpoint": orb_midpoint,
                "trade_type": "INTRADAY",
                "notes": f"ORB Range: Rs. {round(orb_low, 2)} - {round(orb_high, 2)}. Midpoint SL: Rs. {orb_midpoint}"
            }
            
        # Bearish Breakdown: Bar closed below ORB low
        elif current_close < orb_low and current_volume >= avg_volume * 0.8:
            risk = orb_midpoint - current_close
            if risk <= 0:
                return None
            target = round(current_close - (2.0 * risk), 2)
            
            return {
                "symbol": symbol,
                "strategy": "ORB_MIDPOINT_BREAKOUT",
                "pattern": "15-Min Opening Range Breakdown (Bearish)",
                "direction": "SELL",
                "entry_price": round(current_close, 2),
                "stop_loss": orb_midpoint,
                "target_price": target,
                "risk_per_share": round(risk, 2),
                "rr_ratio": 2.0,
                "confluence_score": 85,
                "orb_high": round(orb_high, 2),
                "orb_low": round(orb_low, 2),
                "orb_midpoint": orb_midpoint,
                "trade_type": "INTRADAY",
                "notes": f"ORB Range: Rs. {round(orb_low, 2)} - {round(orb_high, 2)}. Midpoint SL: Rs. {orb_midpoint}"
            }
            
    except Exception as e:
        print(f"[ORB Strategy Error for {symbol}] {e}")
        return None
        
    return None
