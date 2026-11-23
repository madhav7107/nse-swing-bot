"""
Monthly Target Manager with Dynamic Carry-Forward Logic
Manages capital growth targeting 1% per month (Rs. 5,000 on Rs. 5,00,000 capital)
with cumulative shortfall tracking and capital protection.
"""

import os
import json
import datetime
from typing import Dict, Any, Tuple
import config

TARGET_STATE_FILE = os.path.join(os.path.dirname(__file__), "monthly_target_state.json")

def get_current_month_key() -> str:
    now = config.get_ist_now()
    return now.strftime("%Y-%m")

def load_target_state() -> Dict[str, Any]:
    if os.path.exists(TARGET_STATE_FILE):
        try:
            with open(TARGET_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[MonthlyTargetManager] Error loading state: {e}")
            
    # Default initial state
    return {
        "capital": getattr(config, "INITIAL_CAPITAL", 500000.0),
        "monthly_target_pct": 1.0,
        "base_monthly_target_inr": 5000.0,
        "start_month": "2026-11",
        "months": {},
        "last_updated": None
    }

def save_target_state(state: Dict[str, Any]):
    state["last_updated"] = config.get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
    with open(TARGET_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def calculate_monthly_performance() -> Dict[str, Any]:
    """
    Computes monthly realized profits from trade database/backup,
    applies carry-forward shortfall logic, and determines active targets.
    """
    from trade_logger import get_closed_trades
    state = load_target_state()
    base_target = state.get("base_monthly_target_inr", 5000.0)
    
    # Fetch all closed trades
    closed_trades = get_closed_trades(limit=500)
    
    # Group realized PnL by month (YYYY-MM)
    monthly_pnl: Dict[str, float] = {}
    for t in closed_trades:
        exit_date = str(t.get("exit_date", ""))
        pnl = float(t.get("pnl") or 0.0)
        if exit_date and len(exit_date) >= 7:
            m_key = exit_date[:7]
            monthly_pnl[m_key] = monthly_pnl.get(m_key, 0.0) + pnl
            
    # Ensure current month is present
    current_month = get_current_month_key()
    if current_month not in monthly_pnl:
        monthly_pnl[current_month] = 0.0

    # Calculate carry-forward shortfall chronologically
    sorted_months = sorted(list(monthly_pnl.keys()))
    cumulative_shortfall = 0.0
    history = {}
    
    for m in sorted_months:
        realized = monthly_pnl.get(m, 0.0)
        target_for_this_month = base_target + cumulative_shortfall
        
        if m < current_month:
            # Past month: evaluate surplus or shortfall
            shortfall_this_month = target_for_this_month - realized
            if shortfall_this_month > 0:
                cumulative_shortfall = shortfall_this_month
            else:
                # Target was met or exceeded: reset shortfall to 0
                cumulative_shortfall = 0.0
                
            history[m] = {
                "month": m,
                "target": round(target_for_this_month, 2),
                "realized": round(realized, 2),
                "status": "ACHIEVED" if realized >= target_for_this_month else "SHORTFALL",
                "shortfall_carried_forward": round(cumulative_shortfall, 2)
            }
        else:
            # Current month: active target
            history[m] = {
                "month": m,
                "target": round(target_for_this_month, 2),
                "realized": round(realized, 2),
                "status": "ACHIEVED" if realized >= target_for_this_month else "IN_PROGRESS",
                "remaining_to_target": max(0.0, round(target_for_this_month - realized, 2))
            }

    current_target = base_target + cumulative_shortfall
    current_realized = monthly_pnl.get(current_month, 0.0)
    current_remaining = max(0.0, current_target - current_realized)
    is_target_achieved = current_realized >= current_target

    report = {
        "current_month": current_month,
        "base_target_inr": base_target,
        "cumulative_shortfall_carried": round(cumulative_shortfall, 2),
        "active_dynamic_target_inr": round(current_target, 2),
        "current_month_realized_pnl": round(current_realized, 2),
        "remaining_to_goal": round(current_remaining, 2),
        "target_achieved": is_target_achieved,
        "preservation_mode": is_target_achieved, # When achieved, lock profits & reduce risk
        "history": history
    }
    
    state["months"] = history
    save_target_state(state)
    return report

def get_risk_multiplier() -> Tuple[float, str]:
    """
    Returns risk sizing multiplier based on progress towards monthly target:
    - If target achieved this month -> 0.4x (Capital Preservation Mode: lock profit)
    - If in progress -> 1.0x (Standard 0.5% risk per trade)
    - If monthly drawdown limit breached -> 0.0x (Trading Paused for the month)
    """
    perf = calculate_monthly_performance()
    current_pnl = perf.get("current_month_realized_pnl", 0.0)
    max_monthly_drawdown = getattr(config, "MAX_MONTHLY_DRAWDOWN_INR", 7500.0)
    
    # 1. Hard Monthly Drawdown Guard (-1.5% max)
    if current_pnl <= -max_monthly_drawdown:
        return 0.0, f"BLOCK: Monthly Max Drawdown reached (Rs. {abs(current_pnl):,.2f} / Rs. {max_monthly_drawdown:,.2f}). Trading paused to preserve capital."
        
    # 2. Capital Preservation Mode (Target already achieved!)
    if perf.get("target_achieved", False):
        return 0.4, f"PRESERVATION MODE: Monthly target of Rs. {perf['active_dynamic_target_inr']:,.2f} achieved! Risk reduced to 40% to lock monthly gains."

    return 1.0, f"STANDARD MODE: Target Rs. {perf['active_dynamic_target_inr']:,.2f} (Realized: Rs. {perf['current_month_realized_pnl']:,.2f}, Remaining: Rs. {perf['remaining_to_goal']:,.2f})"

if __name__ == "__main__":
    rep = calculate_monthly_performance()
    print("Monthly Performance Report:")
    print(json.dumps(rep, indent=2))
    mult, reason = get_risk_multiplier()
    print(f"Risk Multiplier: {mult} ({reason})")
