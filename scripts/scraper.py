import requests
import sqlite3
import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY  = os.getenv("DATAGOV_API_KEY")
BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
DB_PATH  = "data/mandiwise.db"

TARGET_CROPS  = ["Onion", "Tomato", "Potato", "Wheat", "Rice"]
TARGET_STATES = ["Maharashtra", "Uttar Pradesh", "Karnataka", "Madhya Pradesh"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/scraper.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

def init_db():
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mandi_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            state       TEXT,
            district    TEXT,
            market      TEXT,
            commodity   TEXT,
            variety     TEXT,
            grade       TEXT,
            min_price   REAL,
            max_price   REAL,
            modal_price REAL,
            price_date  TEXT,
            fetched_at  TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commodity_date
        ON mandi_prices(commodity, price_date)
    """)
    conn.commit()
    conn.close()
    log.info("Database ready")

def fetch_prices(commodity, state, offset=0, limit=100):
    params = {
        "api-key"                : API_KEY,
        "format"                 : "json",
        "limit"                  : limit,
        "offset"                 : offset,
        "filters[commodity]"     : commodity,
        "filters[state.keyword]" : state,
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        time.sleep(0.5)
        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"API error for {commodity} / {state}: {e}")
        time.sleep(2)
        return None

def save_records(records):
    if not records:
        return 0
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    for r in records:
        try:
            conn.execute("""
                INSERT INTO mandi_prices
                (state, district, market, commodity, variety, grade,
                 min_price, max_price, modal_price, price_date, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("state"),
                r.get("district"),
                r.get("market"),
                r.get("commodity"),
                r.get("variety"),
                r.get("grade"),
                float(r.get("min_price",   0) or 0),
                float(r.get("max_price",   0) or 0),
                float(r.get("modal_price", 0) or 0),
                r.get("arrival_date") or r.get("price_date"),
                datetime.now().isoformat()
            ))
            saved += 1
        except Exception as e:
            log.warning(f"Skipped record: {e}")
    conn.commit()
    conn.close()
    return saved

def print_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT commodity, COUNT(*) as total,
               ROUND(AVG(modal_price),2) as avg_price,
               MAX(price_date) as latest_date
        FROM mandi_prices
        GROUP BY commodity
        ORDER BY total DESC
    """)
    print("\n── MandiWise Price Summary ──────────────────────")
    print(f"{'Crop':<12} {'Records':>8} {'Avg Price':>12} {'Latest Date':>14}")
    print("─" * 50)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]:>8} {row[2]:>12} {row[3]:>14}")
    print("─" * 50)
    conn.close()

def run():
    log.info("=== MandiWise Scraper Started ===")
    init_db()
    total_saved = 0
    for crop in TARGET_CROPS:
        for state in TARGET_STATES:
            log.info(f"Fetching: {crop} | {state}")
            data = fetch_prices(crop, state, limit=100)
            if not data:
                continue
            records = data.get("records", [])
            count   = save_records(records)
            total_saved += count
            log.info(f"  Saved {count} records")
    log.info(f"=== Done. Total records saved: {total_saved} ===")
    print_summary()

if __name__ == "__main__":
    run()