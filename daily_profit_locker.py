"""
Daily Profit Target & Profit-Locking Engine
Enforces:
1. Daily Profit Target Stop: Auto square-off & shutdown once total net profit reaches Rs. 5,000.
2. Trailing Profit Lock: Trigger at Rs. 3,000 profit; auto shutdown if drops to Rs. 1,500 floor (never let green turn red).
3. Max Daily Loss Cap: Shut down immediately if daily net loss hits Rs. 2,000.
"""

import os
import json
import datetime
from typing import Tuple, Dict, Any
import config

STATE_FILE = os.path.join(os.path.dirname(__file__), "daily_profit_state.json")

def _load_state() -> Dict[str, Any]:
    today_str = config.get_ist_now().strftime("%Y-%m-%d")
    default_state = {
        "date": today_str,
        "trailing_lock_activated": False,
        "peak_profit": 0.0,
        "is_shut_down": False,
        "shutdown_reason": ""
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                if state.get("date") == today_str:
                    return state
        except Exception:
            pass
    return default_state

def _save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[DailyProfitLocker] Save state error: {e}")

def get_today_cumulative_pnl() -> Tuple[float, float, float]:
    """
    Returns (realized_net_pnl, unrealized_pnl, total_net_pnl) for today.
    """
    today_str = config.get_ist_now().strftime("%Y-%m-%d")
    from trade_logger import get_closed_trades, get_open_trades
    
    # 1. Closed trades today
    closed = get_closed_trades(limit=50)
    today_closed = [t for t in closed if today_str in str(t.get("exit_date", ""))]
    realized_net = sum(float(t.get("pnl") or 0.0) for t in today_closed)
    
    # 2. Open trades today (from local DB and MegaBull)
    unrealized = 0.0
    open_trades = get_open_trades()
    for t in open_trades:
        # Estimate from latest quotes
        try:
            from paper_broker import get_latest_price
            sym = t.get("symbol", "")
            ltp = get_latest_price(sym)
            if ltp:
                ep = float(t.get("entry_price", 0))
                q = int(t.get("quantity", 0))
                d = t.get("direction", "BUY")
                pnl = (ltp - ep) * q if d == "BUY" else (ep - ltp) * q
                unrealized += pnl
        except Exception:
            pass
            
    total_net = realized_net + unrealized
    return round(realized_net, 2), round(unrealized, 2), round(total_net, 2)

def check_daily_profit_locking_status() -> Tuple[str, str, Dict[str, Any]]:
    """
    Evaluates profit locking rules and returns (status, reason, metadata).
    status: 'ACTIVE' or 'SHUTDOWN'
    """
    state = _load_state()
    today_str = config.get_ist_now().strftime("%Y-%m-%d")
    
    # Already shut down today
    if state.get("is_shut_down", False):
        return "SHUTDOWN", state.get("shutdown_reason", "Daily limit active"), state

    realized, unrealized, total_net = get_today_cumulative_pnl()
    
    # Track peak profit
    if total_net > state.get("peak_profit", 0.0):
        state["peak_profit"] = total_net

    target_goal = getattr(config, "DAILY_PROFIT_GOAL", 5000.0)
    trailing_trigger = getattr(config, "TRAILING_PROFIT_LOCK_TRIGGER", 3000.0)
    trailing_floor = getattr(config, "TRAILING_PROFIT_LOCK_FLOOR", 1500.0)
    max_daily_loss = getattr(config, "MAX_DAILY_LOSS_INR", 2000.0)

    # RULE 1: Daily Profit Target Stop (Rs. 5,000)
    if total_net >= target_goal:
        reason = f"TARGET HIT: Daily Net Profit reached Rs. {total_net:,.2f} (Target: Rs. {target_goal:,.2f})! All positions closed & trading shut down for today."
        state["is_shut_down"] = True
        state["shutdown_reason"] = reason
        _save_state(state)
        return "SHUTDOWN", reason, state

    # RULE 2: Trailing Profit Lock
    # Activate lock when profit touches Rs. 3,000
    if total_net >= trailing_trigger and not state.get("trailing_lock_activated", False):
        state["trailing_lock_activated"] = True
        print(f"[DailyProfitLocker] Trailing Profit Lock ACTIVATED at Rs. {total_net:,.2f}. Protected Floor: Rs. {trailing_floor:,.2f}.")

    # If lock is active and profit drops down to Rs. 1,500 floor
    if state.get("trailing_lock_activated", False) and total_net <= trailing_floor:
        reason = f"TRAILING PROFIT LOCK: Profit dropped to Rs. {total_net:,.2f} after reaching Rs. {state.get('peak_profit'):,.2f} (Floor: Rs. {trailing_floor:,.2f}). Trading shut down to keep the day green!"
        state["is_shut_down"] = True
        state["shutdown_reason"] = reason
        _save_state(state)
        return "SHUTDOWN", reason, state

    # RULE 4: Max Daily Loss Cap (Rs. 2,000)
    if total_net <= -max_daily_loss:
        reason = f"MAX DAILY LOSS LIMIT: Net Loss reached -Rs. {abs(total_net):,.2f} (Cap: Rs. {max_daily_loss:,.2f}). Trading shut down immediately to protect capital!"
        state["is_shut_down"] = True
        state["shutdown_reason"] = reason
        _save_state(state)
        return "SHUTDOWN", reason, state

    _save_state(state)
    return "ACTIVE", f"Current Net PnL: Rs. {total_net:,.2f} (Peak: Rs. {state.get('peak_profit', 0):,.2f})", state

if __name__ == "__main__":
    status, reason, state = check_daily_profit_locking_status()
    print(f"Status: {status} | Reason: {reason}")
    print(f"State: {json.dumps(state, indent=2)}")
