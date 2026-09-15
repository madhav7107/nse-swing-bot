from typing import Tuple, Dict
import config
from trade_logger import get_account_balance, get_open_trades

def calculate_position_size(entry_price: float, stop_loss: float) -> Tuple[bool, int, str]:
    """
    Computes exact share quantity to purchase based on strict risk management rules:
    1. Maximum risk per trade = 1.5% of current equity
    2. Maximum exposure in single stock = 25% of portfolio
    3. Maximum concurrent open positions = 5
    """
    open_trades = get_open_trades()
    if len(open_trades) >= config.MAX_OPEN_POSITIONS:
        return False, 0, f"Max open positions reached ({len(open_trades)}/{config.MAX_OPEN_POSITIONS})"
    
    current_cash = get_account_balance()
    if current_cash <= 1000:
        return False, 0, "Insufficient cash balance"
    
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0:
        return False, 0, "Invalid stop loss level (must be below entry price)"
    
    # Dollar risk amount (e.g. ₹1,500 on ₹100,000)
    max_risk_amount = current_cash * (config.RISK_PER_TRADE_PCT / 100.0)
    
    # Shares based on risk
    qty_by_risk = int(max_risk_amount / risk_per_share)
    
    # Shares based on max capital allocation (e.g. 25% of capital = ₹25,000 max per position)
    max_allocation = current_cash * (config.MAX_CAPITAL_PER_TRADE_PCT / 100.0)
    qty_by_capital = int(max_allocation / entry_price)
    
    # Take the safer (smaller) quantity
    qty = min(qty_by_risk, qty_by_capital)
    
    # Total cost must not exceed available cash
    total_cost = qty * entry_price
    if total_cost > current_cash:
        qty = int(current_cash / entry_price)
        total_cost = qty * entry_price
        
    if qty < 1:
        return False, 0, f"Share price ₹{entry_price} too high for allocated risk capital"
        
    actual_risk = qty * risk_per_share
    return True, qty, f"Approved: {qty} shares (Total Investment: ₹{round(total_cost, 2)}, Max Risk: ₹{round(actual_risk, 2)})"
