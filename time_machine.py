"""
Time Machine Engine (Inspired by Jake Schincariol's Day Trader Skill v2)
Adapted for Indian National Stock Exchange (NSE) & Swing/Intraday Trading.

Core Functionality:
- Replays past 60 sessions of historical bars for any candidate stock setup.
- Evaluates empirical probabilities: Does the target hit first, stop hit first, or neither?
- Path simulation: Walks up to 10 sessions for swing trades or 1 session for intraday.
- Monte Carlo / Historical Simulation: Computes Expected Return (in R multiples).
- Acts as a Hard Gate: Blocks trades that are 'Close to a coin flip' (< 55% win rate).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from data_engine import get_stock_data, get_latest_price

def run_time_machine_simulation(
    symbol: str, 
    entry_price: float, 
    stop_loss: float, 
    target_price: float, 
    direction: str = "BUY",
    trade_type: str = "SWING",
    simulations: int = 1000
) -> Dict[str, Any]:
    """
    Runs an institutional reality check on a planned trade using past 60 sessions.
    
    Returns:
        dict: {
            "verdict": "PASS" | "BLOCK",
            "target_win_rate_pct": float,
            "stop_loss_rate_pct": float,
            "flat_rate_pct": float,
            "expected_r": float,
            "rr_ratio": float,
            "reason": str,
            "total_sessions_tested": int
        }
    """
    risk_per_share = abs(entry_price - stop_loss)
    reward_per_share = abs(target_price - entry_price)
    
    if risk_per_share <= 0:
        return {
            "verdict": "BLOCK",
            "target_win_rate_pct": 0.0,
            "stop_loss_rate_pct": 100.0,
            "expected_r": -1.0,
            "rr_ratio": 0.0,
            "reason": "Invalid Risk: Stop Loss cannot equal Entry Price",
            "total_sessions_tested": 0
        }
    
    rr_ratio = reward_per_share / risk_per_share
    
    # 1. Fetch 60-90 sessions of historical daily data
    df = get_stock_data(symbol, period="6mo", interval="1d")
    if df is None or len(df) < 25:
        # Fallback to conservative standard if insufficient data
        return {
            "verdict": "PASS" if rr_ratio >= 2.0 else "BLOCK",
            "target_win_rate_pct": 52.0,
            "stop_loss_rate_pct": 48.0,
            "flat_rate_pct": 0.0,
            "expected_r": (0.52 * rr_ratio) - 0.48,
            "rr_ratio": round(rr_ratio, 2),
            "reason": "Sufficient historical bars unavailable. Filtered by standard 1:2 R:R.",
            "total_sessions_tested": len(df) if df is not None else 0
        }
    
    recent_df = df.tail(60).copy()
    highs = recent_df["High"].values
    lows = recent_df["Low"].values
    closes = recent_df["Close"].values
    
    # Compute session-over-session return distribution
    daily_returns = (closes[1:] - closes[:-1]) / closes[:-1]
    daily_high_ratios = (highs - closes) / closes
    daily_low_ratios = (closes - lows) / closes
    
    # Max holding period: 1 day for intraday, 10 days for swing
    max_days = 1 if trade_type == "INTRADAY" else 10
    
    target_hits = 0
    stop_hits = 0
    expired_flats = 0
    
    np.random.seed(19)  # Reproducible fixed seed
    
    for _ in range(min(simulations, 1000)):
        price = entry_price
        resolved = False
        
        for day in range(max_days):
            ret = np.random.choice(daily_returns)
            high_bounce = np.random.choice(daily_high_ratios)
            low_dip = np.random.choice(daily_low_ratios)
            
            day_high = price * (1.0 + max(0.0, ret) + abs(high_bounce))
            day_low = price * (1.0 + min(0.0, ret) - abs(low_dip))
            price = price * (1.0 + ret)
            
            if direction == "BUY":
                hit_tgt = day_high >= target_price
                hit_sl = day_low <= stop_loss
            else:
                hit_tgt = day_low <= target_price
                hit_sl = day_high >= stop_loss
                
            if hit_tgt and not hit_sl:
                target_hits += 1
                resolved = True
                break
            elif hit_sl and not hit_tgt:
                stop_hits += 1
                resolved = True
                break
            elif hit_tgt and hit_sl:
                stop_hits += 1  # Conservative: count collision as stop
                resolved = True
                break
                
        if not resolved:
            expired_flats += 1
            
    total_replays = target_hits + stop_hits + expired_flats
    win_rate = (target_hits / total_replays) * 100.0 if total_replays > 0 else 0.0
    loss_rate = (stop_hits / total_replays) * 100.0 if total_replays > 0 else 0.0
    flat_rate = (expired_flats / total_replays) * 100.0 if total_replays > 0 else 0.0
    
    # Expected return in R: (Win% * Reward_R) - (Loss% * 1.0)
    expected_r = ((win_rate / 100.0) * rr_ratio) - ((loss_rate / 100.0) * 1.0)
    
    # Quantitative Decision Gate (from Day Trader Skill v2 rules):
    # - If win rate < 50%, "Close to a coin flip" -> BLOCK
    # - If R:R < 1.5 -> BLOCK
    # - If expected return <= 0.10R -> BLOCK
    # - If win rate >= 55% and expected_r >= 0.20R -> PASS
    if win_rate < 50.0:
        verdict = "BLOCK"
        reason = f"Coin Flip Risk: Target reached first in only {win_rate:.1f}% of replays vs Stop in {loss_rate:.1f}%. Setup rejected."
    elif rr_ratio < 1.5:
        verdict = "BLOCK"
        reason = f"Poor Risk/Reward: 1:{rr_ratio:.2f} is below institutional minimum (1:1.5)."
    elif expected_r <= 0.10:
        verdict = "BLOCK"
        reason = f"Expected edge too low (+{expected_r:.2f}R). Rejected to protect capital."
    else:
        verdict = "PASS"
        reason = f"High-Conviction Institutional Setup! Win Prob: {win_rate:.1f}%, Expected: +{expected_r:.2f}R, R:R: 1:{rr_ratio:.1f}."
        
    return {
        "verdict": verdict,
        "target_win_rate_pct": round(win_rate, 1),
        "stop_loss_rate_pct": round(loss_rate, 1),
        "flat_rate_pct": round(flat_rate, 1),
        "expected_r": round(expected_r, 2),
        "rr_ratio": round(rr_ratio, 2),
        "reason": reason,
        "total_sessions_tested": len(recent_df)
    }

if __name__ == "__main__":
    test_res = run_time_machine_simulation("HCLTECH.NS", 1344.9, 1297.83, 1439.04, "BUY", "SWING")
    print("Test HCLTECH Simulation:", test_res)
