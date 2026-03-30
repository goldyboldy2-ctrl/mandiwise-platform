import requests
import sqlite3
import os
import csv
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
API_KEY  = os.getenv("DATAGOV_API_KEY")
BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
DB_PATH  = "data/mandiwise.db"
ON_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

TARGET_CROPS  = ["Onion", "Tomato", "Potato", "Garlic", "Ginger",
                 "Brinjal", "Cauliflower", "Cabbage", "Bitter Gourd", "Lady Finger",
                 "Banana", "Mango", "Pomegranate", "Grapes", "Apple",
                 "Arhar (Tur/Red Gram)", "Urad", "Moong", "Chana", "Masur",
                 "Turmeric", "Dry Chillies", "Cumin (Jeera)", "Coriander",
                 "Soyabean", "Mustard", "Groundnut", "Wheat", "Rice", "Maize"]

TARGET_STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
                 "Chhattisgarh", "Goa", "Gujarat", "Haryana",
                 "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
                 "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
                 "Mizoram", "Nagaland", "Odisha", "Punjab",
                 "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
                 "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
                 "Andaman and Nicobar Islands", "Chandigarh", "Delhi",
                 "Jammu and Kashmir", "Ladakh", "Lakshadweep",
                 "Puducherry", "Dadra and Nagar Haveli"]

os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/scraper.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

def init_db():
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

def fetch_prices(commodity, state, limit=500):
    params = {
        "api-key"                : API_KEY,
        "format"                 : "json",
        "limit"                  : limit,
        "offset"                 : 0,
        "filters[commodity]"     : commodity,
        "filters[state.keyword]" : state,
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        time.sleep(1)
        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"Error {commodity}/{state}: {e}")
        time.sleep(5)
        return None

def record_exists(conn, commodity, market, price_date):
    result = conn.execute("""
        SELECT id FROM mandi_prices
        WHERE commodity = ? AND market = ? AND price_date = ?
    """, (commodity, market, price_date)).fetchone()
    return result is not None

def save_to_db(records):
    if not records:
        return 0, 0
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    skipped = 0
    for r in records:
        try:
            price_date = r.get("arrival_date") or r.get("price_date")
            commodity  = r.get("commodity")
            market     = r.get("market")
            if record_exists(conn, commodity, market, price_date):
                skipped += 1
                continue
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
                price_date,
                datetime.now().isoformat()
            ))
            saved += 1
        except Exception as e:
            log.warning(f"Skipped record: {e}")
    conn.commit()
    conn.close()
    return saved, skipped

def save_to_csv(all_records):
    if not all_records:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    csv_path = f"prices/prices_{today}.csv"
    Path("prices").mkdir(exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "state", "district", "market", "commodity",
            "variety", "grade", "min_price", "max_price",
            "modal_price", "price_date"
        ])
        for r in all_records:
            writer.writerow([
                r.get("state"), r.get("district"), r.get("market"),
                r.get("commodity"), r.get("variety"), r.get("grade"),
                r.get("min_price"), r.get("max_price"), r.get("modal_price"),
                r.get("arrival_date") or r.get("price_date")
            ])
    log.info(f"CSV saved: {csv_path} ({len(all_records)} records)")

def print_summary():
    if ON_GITHUB:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT commodity, COUNT(*) as total,
               ROUND(AVG(modal_price), 2) as avg_price,
               MAX(price_date) as latest
        FROM mandi_prices
        GROUP BY commodity
        ORDER BY total DESC
        LIMIT 15
    """)
    print("\n-- MandiWise Summary ------------------------------------")
    print(f"{'Crop':<25} {'Records':>8} {'Avg Rs':>10} {'Latest':>12}")
    print("-" * 58)
    for row in cursor.fetchall():
        print(f"{row[0]:<25} {row[1]:>8} {row[2]:>10} {row[3]:>12}")
    print("-" * 58)
    conn.close()

def run():
    log.info("=== MandiWise Scraper Started ===")
    log.info(f"Environment: {'GitHub Actions' if ON_GITHUB else 'Local'}")

    if not ON_GITHUB:
        init_db()

    total_saved   = 0
    total_skipped = 0
    all_records   = []

    for crop in TARGET_CROPS:
        for state in TARGET_STATES:
            log.info(f"Fetching: {crop} | {state}")
            data = fetch_prices(crop, state)
            if not data:
                continue
            records = data.get("records", [])
            if not records:
                continue
            all_records.extend(records)
            if not ON_GITHUB:
                saved, skipped  = save_to_db(records)
                total_saved    += saved
                total_skipped  += skipped
                log.info(f"  Saved {saved} | Skipped {skipped}")
            else:
                log.info(f"  Fetched {len(records)} records")

    save_to_csv(all_records)

    if not ON_GITHUB:
        log.info(f"=== Done. Saved {total_saved} | Skipped {total_skipped} ===")
        print_summary()
    else:
        log.info(f"=== Done. Total records fetched: {len(all_records)} ===")

if __name__ == "__main__":
    run()
