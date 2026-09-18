import os
import json
import csv
import io
import urllib.request
import urllib.error
import config

MEGABULL_API_BASE = "https://api.megabull.in"
INSTRUMENTS_FILE = os.path.join(os.path.dirname(__file__), "megabull_instruments.json")
_INSTRUMENT_MAP = {}

def get_headers():
    api_key = getattr(config, "MEGABULL_API_KEY", "dc09ce27-75b6-4f06-b3e9-646c484ab7ee")
    return {
        "api-key": api_key,
        "User-Agent": "SR-Trading-Bot/1.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def load_instrument_map():
    global _INSTRUMENT_MAP
    if _INSTRUMENT_MAP:
        return _INSTRUMENT_MAP

    if os.path.exists(INSTRUMENTS_FILE):
        try:
            with open(INSTRUMENTS_FILE, "r") as f:
                _INSTRUMENT_MAP = json.load(f)
                if len(_INSTRUMENT_MAP) > 100:
                    return _INSTRUMENT_MAP
        except Exception:
            pass

    # Download from MegaBull S3
    try:
        url = "https://megabull-open.s3.us-east-1.amazonaws.com/Instrument-default.csv"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            reader = csv.DictReader(io.StringIO(res.read().decode("utf-8", errors="ignore")))
            mapping = {}
            for row in reader:
                sym = row.get("tradingSymbol")
                tok = row.get("instrumentToken")
                if sym and tok:
                    mapping[sym] = tok
            _INSTRUMENT_MAP = mapping
            try:
                with open(INSTRUMENTS_FILE, "w") as f:
                    json.dump(_INSTRUMENT_MAP, f)
            except Exception:
                pass
            return _INSTRUMENT_MAP
    except Exception as e:
        print(f"[MegaBull] Instrument download error: {e}")
        return _INSTRUMENT_MAP

def get_instrument_token(symbol: str) -> str:
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").strip()
    mapping = load_instrument_map()
    return mapping.get(clean_sym)

def get_account_profile() -> dict:
    url = f"{MEGABULL_API_BASE}/api/user/my"
    req = urllib.request.Request(url, headers=get_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        print(f"[MegaBull] get_account_profile error: {e}")
        return {}

def place_order(symbol: str, qty: int, order_type: str, price: float) -> dict:
    """
    order_type: 'BUY' or 'SELL'
    """
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").strip()
    token = get_instrument_token(clean_sym)
    if not token:
        print(f"[MegaBull] Instrument token not found for {clean_sym}")
        return {"error": f"Token not found for {clean_sym}"}

    payload = {
        "type": order_type.upper(),
        "duration": "CNC",
        "orderType": "MKT",
        "qty": int(qty),
        "price": float(price),
        "instrumentToken": str(token)
    }

    url = f"{MEGABULL_API_BASE}/api/order/buysell"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=get_headers(),
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode())
            print(f"[MegaBull] {order_type} order placed for {clean_sym} (Qty: {qty}): Order ID {data.get('id')}")
            return data
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"[MegaBull] Order failed for {clean_sym}: {e.code} - {err_msg}")
        return {"error": err_msg, "code": e.code}
    except Exception as e:
        print(f"[MegaBull] Order exception: {e}")
        return {"error": str(e)}

def get_holdings() -> list:
    url = f"{MEGABULL_API_BASE}/api/holding/my"
    req = urllib.request.Request(url, headers=get_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        print(f"[MegaBull] get_holdings error: {e}")
        return []

def sync_megabull_to_db():
    """
    2-Way Sync Engine:
    Synchronizes live MegaBull portfolio (cash balance + active holdings)
    with local SQLite database so that:
    1. Render cloud restarts never lose trade tracking or active positions.
    2. 1R Trailing Stop-Loss monitors all live MegaBull positions.
    3. The Web Dashboard displays all real positions and real P&L.
    """
    if not getattr(config, "MEGABULL_ENABLED", False):
        return
        
    try:
        import datetime
        from trade_logger import get_connection, backup_to_json
        
        profile = get_account_profile()
        if not profile:
            return
            
        virtual_left = profile.get("virtualMoneyLeft")
        total_virtual = profile.get("virtualMoney", 500000.0)
        
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Update account balance with live MegaBull cash
        if virtual_left is not None:
            cursor.execute("SELECT id FROM account WHERE id = 1")
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE account SET balance = ?, initial_capital = ?, updated_at = ? WHERE id = 1",
                    (float(virtual_left), float(total_virtual), now)
                )
            else:
                cursor.execute(
                    "INSERT INTO account (id, balance, initial_capital, created_at, updated_at) VALUES (1, ?, ?, ?, ?)",
                    (float(virtual_left), float(total_virtual), now, now)
                )
            conn.commit()
            
        # 2. Sync holdings
        mb_holdings = get_holdings()
        mb_symbols = {}
        for h in mb_holdings:
            name = h.get("instrumentName")
            qty = int(h.get("qty", 0))
            if name and qty > 0:
                mb_symbols[name] = h
                
        # Fetch current open trades in DB
        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
        db_open_trades = [dict(r) for r in cursor.fetchall()]
        db_symbols = {t["symbol"].replace(".NS", "").replace(".BO", "").strip(): t for t in db_open_trades}
        
        # A. If holding exists in MegaBull but NOT in DB, insert it!
        for name, h in mb_symbols.items():
            sym = f"{name}.NS"
            qty = int(h.get("qty", 0))
            buy_price = float(h.get("avgBuyPrice", 0.0) or h.get("priceAvg", 0.0))
            if buy_price <= 0:
                continue
                
            if name not in db_symbols:
                # Calculate initial SL (3.5% swing SL) & Target (1:2 RR = 7%)
                sl = round(buy_price * 0.965, 2)
                tgt = round(buy_price * 1.07, 2)
                cursor.execute("""
                    INSERT INTO trades (
                        symbol, direction, entry_date, entry_price, quantity,
                        stop_loss, original_sl, target_price, status, strategy, notes
                    ) VALUES (?, 'BUY', ?, ?, ?, ?, ?, ?, 'OPEN', 'INSTITUTIONAL_SWING', ?)
                """, (sym, now, buy_price, qty, sl, sl, tgt, "Synced from MegaBull Live Portfolio"))
                print(f"[MegaBull Sync] Inserted active holding: {sym} ({qty} shares @ Rs {buy_price})")
            else:
                # Update quantity if changed
                existing = db_symbols[name]
                if existing["quantity"] != qty or abs(existing["entry_price"] - buy_price) > 0.05:
                    cursor.execute(
                        "UPDATE trades SET quantity = ?, entry_price = ? WHERE id = ?",
                        (qty, buy_price, existing["id"])
                    )
                    
        # B. If trade is OPEN in DB but NO LONGER in MegaBull, mark it as closed!
        for clean_name, t in db_symbols.items():
            if clean_name not in mb_symbols:
                exit_price = float(t.get("target_price", t["entry_price"]))
                cursor.execute("""
                    UPDATE trades 
                    SET status = 'CLOSED_SYNC', exit_date = ?, exit_price = ?, exit_reason = 'Closed on MegaBull App'
                    WHERE id = ?
                """, (now, exit_price, t["id"]))
                print(f"[MegaBull Sync] Marked {clean_name} as CLOSED (No longer in MegaBull holdings).")
                
        conn.commit()
        conn.close()
        backup_to_json()
    except Exception as e:
        print(f"[MegaBull Sync Error] {e}")

if __name__ == "__main__":
    print("Testing MegaBull module...")
    user = get_account_profile()
    print("User:", user.get("firstName"), user.get("lastName"), "| Virtual Balance: Rs.", user.get("virtualMoneyLeft"))
    tok = get_instrument_token("RELIANCE")
    print("RELIANCE token:", tok)
    sync_megabull_to_db()
