import sqlite3
import datetime
import json
import os
from typing import Dict, List, Optional
import config

def get_connection():
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Account balance table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account (
        id INTEGER PRIMARY KEY,
        balance REAL NOT NULL,
        initial_capital REAL NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Trades table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL DEFAULT 'BUY',
        entry_date TEXT NOT NULL,
        entry_price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        stop_loss REAL NOT NULL,
        original_sl REAL NOT NULL,
        target_price REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        exit_date TEXT,
        exit_price REAL,
        pnl REAL,
        pnl_pct REAL,
        exit_reason TEXT,
        strategy TEXT DEFAULT 'ZONE_BOUNCE',
        notes TEXT
    )
    """)
    
    # Daily equity snapshot table for portfolio curve
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equity_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        cash_balance REAL NOT NULL,
        invested_amount REAL NOT NULL,
        total_equity REAL NOT NULL,
        unrealized_pnl REAL NOT NULL,
        open_positions INTEGER NOT NULL
    )
    """)

    # Initialize account if empty
    cursor.execute("SELECT COUNT(*) FROM account")
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO account (id, balance, initial_capital, created_at, updated_at) VALUES (1, ?, ?, ?, ?)",
            (config.INITIAL_CAPITAL, config.INITIAL_CAPITAL, now, now)
        )
    
    conn.commit()
    conn.close()
    restore_from_json()

def get_account_balance() -> float:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return float(row["balance"])
    return config.INITIAL_CAPITAL

def update_account_balance(new_balance: float):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE account SET balance = ?, updated_at = ? WHERE id = 1",
        (new_balance, now)
    )
    conn.commit()
    conn.close()
    backup_to_json()

def log_trade_entry(symbol: str, entry_price: float, quantity: int, stop_loss: float, target_price: float, notes: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trades (
            symbol, direction, entry_date, entry_price, quantity,
            stop_loss, original_sl, target_price, status, strategy, notes
        ) VALUES (?, 'BUY', ?, ?, ?, ?, ?, ?, 'OPEN', 'ZONE_BOUNCE', ?)
    """, (symbol, now, entry_price, quantity, stop_loss, stop_loss, target_price, notes))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    backup_to_json()
    return trade_id

def log_trade_exit(trade_id: int, exit_price: float, exit_reason: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("SELECT entry_price, quantity FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    entry_price = float(row["entry_price"])
    quantity = int(row["quantity"])
    pnl = (exit_price - entry_price) * quantity
    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
    
    status = "CLOSED_PROFIT" if pnl >= 0 else "CLOSED_LOSS"
    if "TRAILING" in exit_reason.upper():
        status = "CLOSED_TRAILING"
    elif "TARGET" in exit_reason.upper():
        status = "CLOSED_TARGET"
    elif "STOP" in exit_reason.upper():
        status = "CLOSED_STOPLOSS"
    
    cursor.execute("""
        UPDATE trades 
        SET status = ?, exit_date = ?, exit_price = ?, pnl = ?, pnl_pct = ?, exit_reason = ?
        WHERE id = ?
    """, (status, now, exit_price, pnl, pnl_pct, exit_reason, trade_id))
    
    # Return invested capital + PnL back into account balance within the same transaction
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    acc_row = cursor.fetchone()
    current_balance = float(acc_row["balance"]) if acc_row else config.INITIAL_CAPITAL
    trade_total_returned = (entry_price * quantity) + pnl
    cursor.execute(
        "UPDATE account SET balance = ?, updated_at = ? WHERE id = 1",
        (current_balance + trade_total_returned, now)
    )
    
    conn.commit()
    conn.close()

def update_stop_loss(trade_id: int, new_sl: float, note: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE trades SET stop_loss = ?, notes = notes || ' | ' || ? WHERE id = ?", (new_sl, note, trade_id))
    conn.commit()
    conn.close()
    backup_to_json()

def get_open_trades() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_closed_trades(limit: int = 50) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status != 'OPEN' ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def log_equity_snapshot(invested_amount: float, unrealized_pnl: float, open_positions: int):
    conn = get_connection()
    cursor = conn.cursor()
    cash = get_account_balance()
    total_equity = cash + invested_amount + unrealized_pnl
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO equity_history (timestamp, cash_balance, invested_amount, total_equity, unrealized_pnl, open_positions)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now, cash, invested_amount, total_equity, unrealized_pnl, open_positions))
    conn.commit()
    conn.close()
    backup_to_json()

def get_performance_stats() -> Dict:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), SUM(pnl), AVG(pnl_pct) FROM trades WHERE status != 'OPEN'")
    total_trades, total_pnl, avg_pnl_pct = cursor.fetchone()
    total_trades = total_trades or 0
    total_pnl = total_pnl or 0.0
    avg_pnl_pct = avg_pnl_pct or 0.0
    
    cursor.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE status != 'OPEN' AND pnl > 0")
    winning_trades, gross_profit = cursor.fetchone()
    winning_trades = winning_trades or 0
    gross_profit = gross_profit or 0.0
    
    cursor.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE status != 'OPEN' AND pnl <= 0")
    losing_trades, gross_loss = cursor.fetchone()
    losing_trades = losing_trades or 0
    gross_loss = abs(gross_loss or 0.0)
    
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
    
    cash = get_account_balance()
    cursor.execute("SELECT SUM(entry_price * quantity) FROM trades WHERE status = 'OPEN'")
    invested = cursor.fetchone()[0] or 0.0
    
    conn.close()
    
    return {
        "initial_capital": config.INITIAL_CAPITAL,
        "cash_balance": round(cash, 2),
        "invested_capital": round(invested, 2),
        "total_equity": round(cash + invested, 2),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 1),
        "total_realized_pnl": round(total_pnl, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
        "profit_factor": round(profit_factor, 2)
    }


def backup_to_json():
    """Backs up all trades and account balance to a persistent JSON file."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades")
        trades = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT balance, initial_capital FROM account WHERE id = 1")
        acc = cursor.fetchone()
        account_data = dict(acc) if acc else {}
        conn.close()
        
        data = {
            "account": account_data,
            "trades": trades,
            "backup_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(config.BACKUP_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Backup Error] {e}")

def restore_from_json():
    """Restores trades and balance from JSON backup if database is empty."""
    try:
        if not os.path.exists(config.BACKUP_PATH):
            return
        with open(config.BACKUP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        trades = data.get("trades", [])
        if not trades:
            return
            
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades")
        if cursor.fetchone()[0] == 0:
            print(f"[Persistence] Restoring {len(trades)} trades from backup...")
            for t in trades:
                cursor.execute("""
                    INSERT OR REPLACE INTO trades (
                        id, symbol, direction, entry_date, entry_price, quantity,
                        stop_loss, original_sl, target_price, status, exit_date,
                        exit_price, pnl, pnl_pct, exit_reason, strategy, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t.get("id"), t["symbol"], t.get("direction", "BUY"), t["entry_date"],
                    t["entry_price"], t["quantity"], t["stop_loss"], t.get("original_sl", t["stop_loss"]),
                    t["target_price"], t["status"], t.get("exit_date"), t.get("exit_price"),
                    t.get("pnl"), t.get("pnl_pct"), t.get("exit_reason"),
                    t.get("strategy", "ZONE_BOUNCE"), t.get("notes", "")
                ))
            acc = data.get("account", {})
            if "balance" in acc:
                cursor.execute("UPDATE account SET balance = ? WHERE id = 1", (acc["balance"],))
            conn.commit()
            print("[Persistence] Successfully restored trades and balance from backup!")
        conn.close()
    except Exception as e:
        print(f"[Restore Error] {e}")
