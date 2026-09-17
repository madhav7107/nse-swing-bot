from typing import Dict, List
import config
from trade_logger import (
    get_open_trades, get_account_balance, update_account_balance,
    log_trade_entry, log_trade_exit, update_stop_loss, log_equity_snapshot
)
from risk_manager import calculate_position_size
from data_engine import get_stock_data, get_latest_price
try:
    from ntfy_notifier import notify_buy, notify_target_hit, notify_stop_loss_hit, notify_trailing_sl
except ImportError:
    def notify_buy(trade): pass
    def notify_target_hit(trade, ltp, pnl): pass
    def notify_stop_loss_hit(trade, ltp, pnl): pass
    def notify_trailing_sl(symbol, old_sl, new_sl, ltp): pass

def execute_paper_buy(setup: Dict) -> bool:
    """
    Simulates buying a stock in Paper Trading mode.
    Deducts capital, logs the trade, and creates a risk-managed position.
    """
    symbol = setup["symbol"]
    entry_price = setup["entry_price"]
    stop_loss = setup["stop_loss"]
    target_price = setup["target_price"]
    
    # Check if already holding this symbol
    open_trades = get_open_trades()
    for t in open_trades:
        if t["symbol"] == symbol:
            print(f"Already holding an active position in {symbol}. Skipping duplicate entry.")
            return False
            
    # Calculate position size
    approved, qty, reason = calculate_position_size(entry_price, stop_loss)
    if not approved:
        print(f"Order rejected for {symbol}: {reason}")
        return False
        
    cost = qty * entry_price
    current_balance = get_account_balance()
    update_account_balance(current_balance - cost)
    
    trade_id = log_trade_entry(
        symbol=symbol,
        entry_price=entry_price,
        quantity=qty,
        stop_loss=stop_loss,
        target_price=target_price,
        notes=setup.get("reason", "")
    )
    
    # Synchronize order to MegaBull app if enabled
    if getattr(config, "MEGABULL_ENABLED", False):
        try:
            from megabull_broker import place_order as mb_place_order
            mb_res = mb_place_order(symbol, qty, "BUY", entry_price)
            if mb_res and "id" in mb_res:
                print(f"[MegaBull] Successfully synced BUY order ID: {mb_res['id']} to MegaBull account!")
        except Exception as mb_err:
            print(f"[MegaBull Order Sync Error] {mb_err}")

    notify_buy({
        "symbol": symbol,
        "entry_price": entry_price,
        "quantity": qty,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "pattern": setup.get("pattern", "Zone Bounce"),
        "confluence_score": setup.get("confluence_score", 75)
    })
    print(f"[PAPER ORDER EXECUTED] Bought {qty} shares of {symbol} at Rs. {entry_price} (Target: Rs. {target_price}, SL: Rs. {stop_loss})")
    return True

def monitor_and_manage_positions():
    """
    Loops through all active open positions:
    - Checks whether Stop-Loss or Target was triggered during today's price action
    - Dynamically trails Stop-Loss to Breakeven (Cost) once 1R profit is achieved
    - Trails further using 20 EMA to maximize profits
    """
    open_trades = get_open_trades()
    if not open_trades:
        print("No open swing positions currently to monitor.")
        return
        
    print(f"Monitoring {len(open_trades)} active positions...")
    total_invested = 0.0
    unrealized_pnl = 0.0
    
    for trade in open_trades:
        symbol = trade["symbol"]
        trade_id = trade["id"]
        entry_price = float(trade["entry_price"])
        stop_loss = float(trade["stop_loss"])
        target_price = float(trade["target_price"])
        qty = int(trade["quantity"])
        invested = entry_price * qty
        total_invested += invested
        
        df = get_stock_data(symbol, period="5d", interval="1d")
        if df is None or df.empty:
            continue
            
        today = df.iloc[-1]
        today_high = float(today["High"])
        today_low = float(today["Low"])
        today_close = float(today["Close"])
        
        pos_pnl = (today_close - entry_price) * qty
        unrealized_pnl += pos_pnl
        
        # 1. Check Stop Loss Hit
        if today_low <= stop_loss:
            exit_price = stop_loss
            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
            log_trade_exit(trade_id, exit_price, "Stop Loss Triggered")
            
            # Sync exit to MegaBull app
            if getattr(config, "MEGABULL_ENABLED", False):
                try:
                    from megabull_broker import place_order as mb_place_order
                    mb_place_order(symbol, qty, "SELL", exit_price)
                except Exception as mb_err:
                    print(f"[MegaBull SL Exit Sync Error] {mb_err}")

            notify_stop_loss_hit(trade, exit_price, pnl)
            print(f"[STOP-LOSS HIT] on {symbol} at Rs. {exit_price} (P&L: Rs. {round(pnl, 2)})")
            continue
            
        # 2. Check Target Hit
        if today_high >= target_price:
            exit_price = target_price
            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
            log_trade_exit(trade_id, exit_price, "Target Reached")
            
            # Sync exit to MegaBull app
            if getattr(config, "MEGABULL_ENABLED", False):
                try:
                    from megabull_broker import place_order as mb_place_order
                    mb_place_order(symbol, qty, "SELL", exit_price)
                except Exception as mb_err:
                    print(f"[MegaBull Target Exit Sync Error] {mb_err}")

            notify_target_hit(trade, exit_price, pnl)
            print(f"[TARGET REACHED] on {symbol} at Rs. {exit_price} (P&L: +Rs. {round(pnl, 2)})")
            continue
            
        # 3. Dynamic Trailing Stop Loss Management
        if config.TRAILING_STOP_ENABLED:
            initial_risk = entry_price - float(trade["original_sl"])
            one_r_level = entry_price + initial_risk
            
            # Step A: Move to Breakeven (Entry Price) once 1R profit reached
            if today_high >= one_r_level and stop_loss < entry_price:
                new_sl = round(entry_price * 1.002, 2) # Slightly above cost to cover brokerage/charges
                update_stop_loss(trade_id, new_sl, "Moved SL to Breakeven (Cost)")
                notify_trailing_sl(symbol, stop_loss, new_sl, today_close)
                print(f"[TRAILING SL] {symbol}: Profit > 1R. Moved Stop Loss to Cost (Rs. {new_sl})")
                stop_loss = new_sl
                
            # Step B: Trail with 20 EMA once in strong profit
            ema20 = float(today["EMA_20"])
            if today_close > one_r_level and ema20 > stop_loss and ema20 < today_close:
                new_sl = round(ema20 * 0.995, 2)
                if new_sl > stop_loss:
                    update_stop_loss(trade_id, new_sl, f"Trailed SL using 20 EMA (Rs. {new_sl})")
                    notify_trailing_sl(symbol, stop_loss, new_sl, today_close)
                    print(f"[TRAILING SL] {symbol}: Trailed Stop Loss to Rs. {new_sl} using 20 EMA")
    
    # Save daily portfolio snapshot
    log_equity_snapshot(total_invested, unrealized_pnl, len(open_trades))
