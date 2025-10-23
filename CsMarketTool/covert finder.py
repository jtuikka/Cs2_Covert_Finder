import requests
import time
import sys
import re

# Allow UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

# ===============================
# Configuration
# ===============================

APP_ID = 730        # Counter-Strike 2
CURRENCY = 3        # 3 = Euro
REQUEST_DELAY = 1.5 # seconds between API calls
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
            # Add StatTrak™ prefix if selected
            if stattrak and not name.startswith("StatTrak™"):
                name = f"StatTrak™ {name}"

            # Add wear if not already specified
            if "(" not in name and ")" not in name:
                name = f"{name} ({wear_suffix})"

            items.append(name)

        print(f"Loaded {len(items)} items from {file_path} with wear: {wear_suffix}")
        if stattrak:
            print("Mode: StatTrak™ enabled")
        else:
            print("Mode: Normal (non-StatTrak™)")
        return items

    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        sys.exit(1)


def get_market_price(item_name):
    """
    Fetch the lowest Steam Market price for a given item.
    Retries indefinitely on 429, non-200, network errors, or bad responses.
    """
    url = "https://steamcommunity.com/market/priceoverview/"
    params = {
        "appid": APP_ID,
        "currency": CURRENCY,
        "market_hash_name": item_name
    }

    while True:
        try:
            response = requests.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            print(f"🌐 Network error for: {item_name} — {e}. Waiting 2s and retrying...")
            time.sleep(2)
            continue

        if response.status_code == 429:
            print(f"⚠️ Request failed (429) for: {item_name} — waiting 2 seconds and retrying...")
            time.sleep(2)
            continue

        if response.status_code != 200:
            print(f"⚠️ HTTP {response.status_code} for: {item_name} — waiting 2s and retrying...")
            time.sleep(2)
            continue

        try:
            data = response.json()
        except Exception:
            print(f"⚠️ Invalid JSON response for: {item_name} — waiting 2s and retrying...")
            time.sleep(2)
            continue

        if not data.get("success"):
            print(f"⚠️ No data (success=false) for: {item_name} — waiting 2s and retrying...")
            time.sleep(2)
            continue

        return data.get("lowest_price", "N/A")


def parse_price(price_str):
    """
    Convert price string like:
      '1 577,29€' or '$4.15' or '27,--€'
    into a float for sorting.
    """
    if not price_str:
        return float('inf')

    s = price_str.replace('\xa0', ' ').strip()
    s = s.replace(',--', ',00').replace('.--', '.00')
    s = re.sub(r'(\d)\s*,-(?!\d)', r'\1,00', s)

    m = re.search(r'[\d][\d\s\.,-]*', s)
    if not m:
        return float('inf')
    num = m.group(0).replace(' ', '')

    if ',' in num and '.' in num:
        num = num.replace('.', '').replace(',', '.')
    elif ',' in num:
        num = num.replace(',', '.')
    else:
        parts = num.split('.')
        if len(parts) > 2:
            num = ''.join(parts[:-1]) + '.' + parts[-1]

    num = re.sub(r'[^0-9\.]', '', num)

    try:
        return float(num)
    except ValueError:
        return float('inf')


def main():
    """Main program logic."""

    # Ask wear condition
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

    # Ask StatTrak mode
    stattrak_input = input("Enable StatTrak™ mode? (y/n, default=n): ").strip().lower()
    stattrak = stattrak_input == "y"

    # Load items
    items = load_items_from_file(ITEM_FILE, wear_suffix, stattrak)
    results = []

    print("\nFetching prices from Steam Market...\n")

    for name in items:
        price = get_market_price(name)
        results.append((name, price))
        print(f"{name:70} -> {price}")
        time.sleep(REQUEST_DELAY)

    # Summary
    print("\n==============================")
    print("Covert Items - Price Summary")
    print("==============================\n")

    for name, price in results:
        print(f"{name:70} | {price}")

    print(f"\nTotal items checked: {len(results)}")

    # Sort by numeric price
    sorted_results = sorted(results, key=lambda x: parse_price(x[1]))

    # Top 10 cheapest
    print("\n==============================")
    print("💰 Top 10 Cheapest Items")
    print("==============================\n")

    for name, price in sorted_results[:10]:
        print(f"{name:70} | {price}")


# ===============================
# Entry Point
# ===============================
if __name__ == "__main__":
    main()
