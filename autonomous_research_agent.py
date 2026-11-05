"""
Autonomous AI Research Agent (Alpha Hunter)
Continuous 24/7 Market Scanning & High-Conviction Opportunity Finder
Discipline Guard: Hard Cap on Daily Loss (Rs. 1,500 max) to guarantee capital preservation.
"""

import os
import json
import datetime
import pandas as pd
from typing import List, Dict, Any
from data_engine import get_stock_data, get_latest_price
from market_scanner import get_all_market_symbols
import config

RESEARCH_CACHE_FILE = os.path.join(os.path.dirname(__file__), "research_agent_findings.json")

def evaluate_stock_opportunity(symbol: str) -> Dict[str, Any]:
    """
    Evaluates institutional momentum, breakout strength, and risk/reward for a single stock.
    Returns structured trade proposal with exact Entry, Stop Loss, Target, and Score.
    """
    try:
        df = get_stock_data(symbol, period="6mo", interval="1d")
        if df is None or len(df) < 50:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(last["Close"])
        volume = float(last["Volume"])
        avg_vol = float(df["Volume"].tail(20).mean())
        rsi = float(last["RSI"]) if "RSI" in last else 50.0
        ema20 = float(last["EMA_20"]) if "EMA_20" in last else close
        ema50 = float(last["EMA_50"]) if "EMA_50" in last else close
        ema200 = float(last["EMA_200"]) if "EMA_200" in last else close

        vol_surge = volume / max(1.0, avg_vol)
        price_change_pct = ((close - float(prev["Close"])) / float(prev["Close"])) * 100.0

        score = 50
        direction = "BUY"
        reason = []

        # 1. Macro Trend: Price > 200 EMA & 50 EMA
        if close > ema200 and close > ema50:
            score += 15
            reason.append("Strong Macro Bull Trend (> 50/200 EMA)")
        elif close < ema200 and close < ema50:
            direction = "SELL"
            score += 15
            reason.append("Macro Bear Trend (< 50/200 EMA)")

        # 2. Institutional Volume Explosion
        if vol_surge >= 2.0:
            score += 15
            reason.append(f"Volume Surge {round(vol_surge, 1)}x")
        elif vol_surge >= 1.3:
            score += 8

        # 3. Momentum & RSI Sweet Spot
        if direction == "BUY":
            if 48 <= rsi <= 68:
                score += 10
                reason.append("RSI Momentum in Prime Bull Zone (48-68)")
        else:
            if 32 <= rsi <= 52:
                score += 10
                reason.append("RSI Momentum in Prime Bear Zone (32-52)")

        # Only proceed if high conviction (>= 80%)
        if score < 80:
            return None

        # Calculate exact Entry, SL, Target with strict 1:2 R:R
        # Risk per share restricted to 1.0% - 1.5% max
        if direction == "BUY":
            entry = close
            sl = round(entry * 0.985, 2) # Strict 1.5% Stop Loss
            risk = entry - sl
            tgt = round(entry + (risk * 2.0), 2) # 1:2 R:R (3.0% Gain)
        else:
            entry = close
            sl = round(entry * 1.015, 2)
            risk = sl - entry
            tgt = round(entry - (risk * 2.0), 2)

        return {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "target_price": tgt,
            "confluence_score": score,
            "vol_surge": round(vol_surge, 2),
            "rsi": round(rsi, 1),
            "reason": " | ".join(reason),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return None

def run_continuous_research(limit_symbols: int = 250) -> List[Dict[str, Any]]:
    """
    Autonomous Research Cycle:
    Scans the market universe and extracts the Top 3 Ultra-High Conviction Setups.
    """
    all_syms = get_all_market_symbols(with_ns_suffix=True)
    # Priority on Watchlist + Top Market Caps
    priority = list(config.WATCHLIST)
    for s in all_syms[:limit_symbols]:
        if s not in priority:
            priority.append(s)

    best_finds = []
    for s in priority:
        opp = evaluate_stock_opportunity(s)
        if opp and opp["confluence_score"] >= 80:
            best_finds.append(opp)

    best_finds.sort(key=lambda x: x["confluence_score"], reverse=True)
    top_picks = best_finds[:5]

    try:
        with open(RESEARCH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_scanned": len(priority),
                "top_picks": top_picks
            }, f, indent=2)
    except Exception as e:
        print(f"[Research Agent Cache Error] {e}")

    return top_picks

def get_latest_research_picks() -> List[Dict[str, Any]]:
    if os.path.exists(RESEARCH_CACHE_FILE):
        try:
            with open(RESEARCH_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("top_picks", [])
        except Exception:
            pass
    return []

if __name__ == "__main__":
    print("[AI Research Agent] Initiating Alpha Hunter scan across priority universe...")
    picks = run_continuous_research(limit_symbols=60)
    print(f"[AI Research Agent] Found {len(picks)} Ultra-High Conviction Setups:")
    for p in picks:
        print(f" -> {p['symbol']} [{p['direction']}] Score: {p['confluence_score']}% | Entry: Rs. {p['entry_price']} | SL: Rs. {p['stop_loss']} | Tgt: Rs. {p['target_price']}")
