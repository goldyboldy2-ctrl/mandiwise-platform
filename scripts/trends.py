import sqlite3
import os
from datetime import datetime

DB_PATH = "data/mandiwise.db"

def get_trend(prices):
    if len(prices) < 2:
        return "insufficient data"
    first = prices[0]
    last  = prices[-1]
    change = ((last - first) / first) * 100 if first > 0 else 0
    if change > 3:
        return f"RISING +{round(change,1)}%"
    elif change < -3:
        return f"FALLING {round(change,1)}%"
    else:
        return f"STABLE {round(change,1)}%"

def analyse():
    conn = sqlite3.connect(DB_PATH)

    print("\n══ MandiWise Trend Analysis ══════════════════════════")
    print(f"  Generated: {datetime.now().strftime('%d %b %Y %H:%M')}")
    print("══════════════════════════════════════════════════════\n")

    # Get all unique commodities
    commodities = conn.execute(
        "SELECT DISTINCT commodity FROM mandi_prices ORDER BY commodity"
    ).fetchall()

    for (commodity,) in commodities:
        print(f"── {commodity} ──────────────────────────────────────")

        # Get last 7 days average price per date
        rows = conn.execute("""
            SELECT price_date,
                   ROUND(AVG(modal_price), 2) as avg_price,
                   COUNT(*) as mandi_count
            FROM mandi_prices
            WHERE commodity = ?
              AND modal_price > 0
            GROUP BY price_date
            ORDER BY price_date ASC
        """, (commodity,)).fetchall()

        if not rows:
            print("  No data\n")
            continue

        prices = [row[1] for row in rows]
        trend  = get_trend(prices)

        # Print date wise prices
        for row in rows:
            bar_len = int(row[1] / 100)
            bar     = "█" * min(bar_len, 30)
            print(f"  {row[0]:>12}  ₹{row[1]:>8}  {bar}")

        print(f"\n  Trend    : {trend}")
        print(f"  Latest   : ₹{prices[-1]} per quintal")
        print(f"  Mandis   : {rows[-1][2]} markets reporting")
        print()

    conn.close()

if __name__ == "__main__":
    analyse()