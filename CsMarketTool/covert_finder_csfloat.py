import requests
import time
import sys
import re
import random
from urllib.parse import quote_plus

# Allow UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

# ===============================
# Configuration
# ===============================
CSFLOAT_API = "https://csfloat.com/api/v1/listings"
REQUEST_DELAY = (1.8, 3.5)  # random delay range
ITEM_FILE = "covert_items.txt"

# ===============================
# Functions
# ===============================

def load_items_from_file(file_path, wear_suffix, stattrak=False):
    """Read item names from file and apply wear + optional StatTrak™ prefix."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            base_items = [line.strip() for line in f if line.strip()]

        items = []
        for name in base_items:
            if stattrak and not name.startswith("StatTrak™"):
                name = f"StatTrak™ {name}"

            if "(" not in name and ")" not in name:
                name = f"{name} ({wear_suffix})"

            items.append(name)

        print(f"Loaded {len(items)} items from {file_path} with wear: {wear_suffix}")
        print("Mode:", "StatTrak™" if stattrak else "Normal (non-StatTrak™)")
        return items

    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        sys.exit(1)


def get_csfloat_data(session, item_name):
    """Fetch lowest direct-buy price and total number of listings (including auctions) from CSFloat."""
    safe_name = item_name.replace("™", "%E2%84%A2").strip()
    url = f"{CSFLOAT_API}?limit=50&market_hash_name={quote_plus(safe_name)}" # try to get as many as possible

    try:
        r = session.get(url, timeout=15)
    except requests.RequestException as e:
        print(f"🌐 Network error for {item_name}: {e}")
        return "N/A", 0

    if r.status_code == 429:
        wait = random.uniform(10, 20)
        print(f"⚠️ Rate limit hit for {item_name}. Waiting {wait:.1f}s...")
        time.sleep(wait)
        return get_csfloat_data(session, item_name)

    if r.status_code != 200:
        print(f"⚠️ HTTP {r.status_code} for {item_name}")
        return "N/A", 0

    try:
        data = r.json()
    except Exception:
        print(f"⚠️ Invalid JSON for {item_name}")
        return "N/A", 0

    results = data.get("data") or data.get("results") or []
    if not results:
        print(f"ℹ️ No listings for {item_name}.")
        return "N/A", 0

    # Separate direct-buy and auction listings
    buy_now_listings = [r for r in results if r.get("type") == "buy_now"]
    auction_listings = [r for r in results if r.get("type") == "auction"]

    # ✅ Listing count = total entries (buy_now + auction)
    total_count = len(results)

    # ✅ Use only buy_now listings for lowest price
    if buy_now_listings:
        lowest = min(buy_now_listings, key=lambda x: x.get("price", float("inf")))
        lowest_price = lowest.get("price", 0) / 100.0
        price_str = f"{lowest_price:.2f}"
    else:
        price_str = "N/A"

    return price_str, total_count



def parse_price(price):
    """Convert numeric or string price to float for sorting."""
    try:
        if isinstance(price, (int, float)):
            return float(price)
        price = str(price).replace(",", ".").replace("€", "").strip()
        return float(re.findall(r"[\d.]+", price)[0])
    except Exception:
        return float("inf")


def main():
    """Main program logic."""
    # === Wear condition selection ===
    print("Choose wear condition for all items:")
    print("1. Factory New")
    print("2. Minimal Wear")
    print("3. Field-Tested")
    print("4. Well-Worn")
    print("5. Battle-Scarred")
    choice = input("Enter number (default = 3): ").strip() or "3"

    wear_options = {
        "1": "Factory New",
        "2": "Minimal Wear",
        "3": "Field-Tested",
        "4": "Well-Worn",
        "5": "Battle-Scarred"
    }
    wear_suffix = wear_options.get(choice, "Field-Tested")

    stattrak_input = input("Enable StatTrak™ mode? (y/n, default=n): ").strip().lower()
    stattrak = stattrak_input == "y"

    # === Load items ===
    items = load_items_from_file(ITEM_FILE, wear_suffix, stattrak)
    results = []
    total_items = 0

    print("\nFetching prices from CSFloat...\n")

    # === Create session (persistent connection) ===
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://csfloat.com/",
        # ⚠️ Replace with your own valid cookies
        "Cookie": "_gid=GA1.2.1979049140.1761229477; _gcl_au=1.1.984629146.1761229478; stripe_mid=4462fe5a-7fd2-4509-9cfd-82ebc004c3a764e374; session=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdGVhbV9pZCI6Ijc2NTYxMTk4ODc1NTI4ODU4Iiwibm9uY2UiOjAsImltcGVyc29uYXRlZCI6ZmFsc2UsImlzcyI6ImNzdGVjaCIsImV4cCI6MTc2MTY2MTc2N30.8mw-OtU9jPrDAl_QJ1QuxOotUcIFvJMdAtmw-G_ZaMo; _ga=GA1.2.668232667.1761229477; stripe_sid=b59e0868-65df-4500-afb8-e2c219fb25bb735784; _ga_3V4JQEGNYC=GS2.1.s1761244554$o2$g1$t1761244617$j60$l0$h0"
    })

    # === Process items ===
    for name in items:
        price, count = get_csfloat_data(session, name)
        results.append((name, price, count))
        total_items += count
        print(f"{name:70} -> {price} € | Listings: {count}")
        time.sleep(random.uniform(*REQUEST_DELAY))  # random human-like delay

    # === Summary ===
    print("\n==============================")
    print("CSFloat Covert Items - Price Summary")
    print("==============================\n")

    for name, price, count in results:
        print(f"{name:70} | {price:>10} $ | Listings: {count}")

    print(f"\nTotal items checked: {len(results)}")

    # === Sort and print cheapest ===
    sorted_results = sorted(results, key=lambda x: parse_price(x[1]))
    print("\n==============================")
    print("💰 Top 10 Cheapest Items")
    print("==============================\n")

    for name, price, count in sorted_results[:10]:
        print(f"{name:70} | {price:>10} $ | Listings: {count}")

    print(f"\nTotal individual items available: {total_items}")


# ===============================
# Entry Point
# ===============================
if __name__ == "__main__":
    main()
