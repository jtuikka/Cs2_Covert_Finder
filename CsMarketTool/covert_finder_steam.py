import requests
import time
import sys
import re
import random

# Allow UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

# ===============================
# Configuration
# ===============================

APP_ID = 730        # Counter-Strike 2
CURRENCY = 3        # 3 = Euro
REQUEST_DELAY = 3.0 # seconds between API calls (increased to avoid cooldown)
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
    Fetch the lowest Steam Market price and number of active sell listings.
    Uses only search/render endpoint to get both price and listing count in one request.
    Retries indefinitely on rate limits or failed requests.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://steamcommunity.com/market/",
    }

    # Use search render endpoint to get both price and sell_listings in one request
    render_url = "https://steamcommunity.com/market/search/render/"
    render_params = {
        "appid": APP_ID,
        "query": item_name,
        "norender": 1,
        "currency": CURRENCY
    }

    while True:
        # --- Get price and listing count in one request ---
        try:
            render_response = requests.get(render_url, params=render_params, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(f"🌐 Network error for {item_name}: {e}. Retrying in 2s...")
            time.sleep(2)
            continue

        if render_response.status_code == 429:
            print(f"⚠️ Rate limited (429) for {item_name}. Waiting 10s...")
            time.sleep(10)
            continue
        if render_response.status_code != 200:
            print(f"⚠️ HTTP {render_response.status_code} for {item_name}. Waiting 5s...")
            time.sleep(5)
            continue

        lowest_price = "N/A"
        sell_count = "N/A"
        
        try:
            render_data = render_response.json()
            
            # Check if we have results and the list is not empty
            if render_data.get("success") and render_data.get("results") and len(render_data["results"]) > 0:
                # Find the exact match by hash_name
                matching_result = None
                for result in render_data["results"]:
                    if result.get("hash_name") == item_name:
                        matching_result = result
                        break
                
                if matching_result:
                    sell_count = matching_result.get("sell_listings", "N/A")
                    lowest_price = matching_result.get("sell_price_text", "N/A")
                else:
                    # Item with exact name not found
                    print(f"⚠️ Item not found on market: {item_name}")
                    return "N/A", "0"
            elif render_data.get("success") and render_data.get("total_count") == 0:
                # Item not found, but this is valid response
                print(f"⚠️ Item not found on market: {item_name}")
                return "N/A", "0"
        except Exception as e:
            print(f"⚠️ Error parsing data for {item_name}: {e}")

        # If both missing, retry
        if lowest_price == "N/A" and sell_count == "N/A":
            print(f"⚠️ No valid data for {item_name}. Retrying in 2s...")
            time.sleep(2)
            continue

        return lowest_price, sell_count


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
        price, count = get_market_price(name)
        results.append((name, price, count))
        print(f"{name:70} -> {price}  |  Listings: {count}")
        # Random delay to appear more human-like and avoid rate limits
        delay = REQUEST_DELAY + random.uniform(0.5, 2.0)
        time.sleep(delay)

    # Summary
    print("\n==============================")
    print("Covert Items - Price Summary")
    print("==============================\n")

    for name, price, count in results:
        print(f"{name:70} | {price:>10} | Listings: {count}")

    print(f"\nTotal items checked: {len(results)}")

    # Sort by numeric price
    sorted_results = sorted(results, key=lambda x: parse_price(x[1]))

    # Top 10 cheapest
    print("\n==============================")
    print("💰 Top 10 Cheapest Items")
    print("==============================\n")

    for name, price, count in sorted_results[:10]:
        print(f"{name:70} | {price:>10} | Listings: {count}")

    print("Total listings in Steam Market:", sum(int(c) for _, _, c in results))
# ===============================
# Entry Point
# ===============================
if __name__ == "__main__":
    main()
