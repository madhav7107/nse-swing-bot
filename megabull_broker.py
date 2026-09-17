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

if __name__ == "__main__":
    print("Testing MegaBull module...")
    user = get_account_profile()
    print("User:", user.get("firstName"), user.get("lastName"), "| Virtual Balance: Rs.", user.get("virtualMoneyLeft"))
    tok = get_instrument_token("RELIANCE")
    print("RELIANCE token:", tok)
