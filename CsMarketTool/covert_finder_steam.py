
import requests
import time
import sys
import re
import random
import json
from pathlib import Path
from datetime import datetime

# Allow UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

# ===============================
# Configuration
# ===============================

APP_ID = 730        # Counter-Strike 2
CURRENCY = 1        # 1 = USD (most consistent across Steam Market API)
REQUEST_DELAY = 3.0 # seconds between API calls (increased to avoid cooldown)
ITEM_FILE = Path(__file__).parent / "covert_items.txt"
DATA_DIR = Path(__file__).parent / "market_data"
DATA_DIR.mkdir(exist_ok=True)


# ===============================
# Functions
# ===============================

def load_base_items(file_path):
    """Read base item names from file (without wear suffixes)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            base_items = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(base_items)} base items from {file_path}")
        return base_items
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        sys.exit(1)


def get_all_variants_for_item(base_name, headers):
    """
    Fetch all variants (all wears + StatTrak) for a base item with ONE API call.
    Uses Steam Market search to get multiple results at once.
    Returns dict mapping variant_name -> (price, count).
    """
    render_url = "https://steamcommunity.com/market/search/render/"
    render_params = {
        "appid": APP_ID,
        "query": base_name,  # Search by base name without wear
        "norender": 1,
        "currency": CURRENCY,
        "count": 100  # Get more results to capture all variants
    }

    while True:
        try:
            render_response = requests.get(render_url, params=render_params, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(f"🌐 Network error for {base_name}: {e}. Retrying in 2s...")
            time.sleep(2)
            continue

        if render_response.status_code == 429:
            print(f"⚠️ Rate limited (429) for {base_name}. Waiting 10s...")
            time.sleep(10)
            continue
        if render_response.status_code != 200:
            print(f"⚠️ HTTP {render_response.status_code} for {base_name}. Waiting 5s...")
            time.sleep(5)
            continue

        try:
            render_data = render_response.json()
        except Exception as e:
            print(f"⚠️ Error parsing data for {base_name}: {e}")
            time.sleep(2)
            continue

        variants = {}
        
        if render_data.get("success") and render_data.get("results"):
            # Process all results that match our base item
            for result in render_data["results"]:
                hash_name = result.get("hash_name", "")
                # Check if this result belongs to our base item
                if base_name in hash_name:
                    sell_count = result.get("sell_listings", "N/A")
                    lowest_price = result.get("sell_price_text", "N/A")
                    
                    # Warn if EUR prices appear (Steam API sometimes ignores currency param)
                    if lowest_price and "€" in str(lowest_price):
                        print(f"⚠️ EUR price detected for {hash_name}: {lowest_price} (API may be returning mixed currencies)")
                    
                    variants[hash_name] = (lowest_price, sell_count)
        
        if variants:
            print(f"✓ Found {len(variants)} variants for {base_name}")
            return variants
        else:
            print(f"⚠️ No variants found for {base_name}")
            return {}



def parse_price(price_str):
    """
    Convert price string to float for sorting.
    Handles USD ($1,234.56) and EUR (1 234,56€) formats.
    """
    if not price_str or price_str == "N/A":
        return float('inf')

    s = price_str.replace('\xa0', ' ').strip()
    
    # Remove currency symbols
    s = s.replace('$', '').replace('€', '').replace('£', '').strip()
    
    # Handle ,-- or .-- (means .00)
    s = s.replace(',--', '.00').replace('.--', '.00')
    
    # Extract all digits, spaces, dots, and commas
    m = re.search(r'[\d][\d\s\.,]*', s)
    if not m:
        return float('inf')
    
    num = m.group(0)
    
    # Detect format:
    # USD: 1,234.56 (comma for thousands, dot for decimals)
    # EUR: 1 234,56 or 1.234,56 (space/dot for thousands, comma for decimals)
    
    # Count dots and commas
    dot_count = num.count('.')
    comma_count = num.count(',')
    
    # Remove spaces (used as thousand separators in some locales)
    num = num.replace(' ', '')
    
    if comma_count > 0 and dot_count > 0:
        # Both present - determine which is decimal separator
        last_comma_pos = num.rfind(',')
        last_dot_pos = num.rfind('.')
        
        if last_dot_pos > last_comma_pos:
            # USD format: 1,234.56
            num = num.replace(',', '')  # Remove thousand separator
        else:
            # EUR format: 1.234,56
            num = num.replace('.', '').replace(',', '.')
    elif comma_count > 0:
        # Only comma - check position
        last_comma = num.rfind(',')
        if len(num) - last_comma == 3:  # X,XX means decimal
            num = num.replace(',', '.')
        else:
            # Comma is thousand separator (unlikely in modern USD)
            num = num.replace(',', '')
    elif dot_count > 1:
        # Multiple dots = thousand separators (e.g., 1.234.567)
        parts = num.split('.')
        num = ''.join(parts[:-1]) + '.' + parts[-1]
    # else: single dot or no separator - keep as is (USD format)
    
    try:
        return float(num)
    except ValueError:
        return float('inf')


def save_results_to_json(results, wear_filter, stattrak_filter):
    """
    Save results to timestamped JSON file for later analysis/graphing.
    
    Format:
    {
      "timestamp": "2025-10-24T14:30:00",
      "filters": {"wear": "all", "stattrak": "both"},
      "total_listings": 1234,
      "items": [
        {
          "name": "AK-47 | Asiimov (Field-Tested)",
          "base_name": "AK-47 | Asiimov",
          "wear": "Field-Tested",
          "stattrak": false,
          "price": "123,45€",
          "price_numeric": 123.45,
          "listings": 42
        },
        ...
      ]
    }
    """
    timestamp = datetime.now()
    filename = DATA_DIR / f"steam_market_data_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
    
    # Calculate total listings
    total_listings = 0
    for _, _, count in results:
        try:
            total_listings += int(count) if count != "N/A" else 0
        except ValueError:
            pass
    
    # Parse items into structured format
    items_data = []
    for name, price, count in results:
        # Determine wear condition
        wear = None
        for w in ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]:
            if f"({w})" in name:
                wear = w
                break
        
        # Determine if StatTrak
        is_stattrak = "StatTrak™" in name
        
        # Extract base name (without wear and StatTrak)
        base_name = name.replace("StatTrak™ ", "")
        if wear:
            base_name = base_name.replace(f" ({wear})", "")
        
        # Parse numeric price
        price_numeric = parse_price(price)
        if price_numeric == float('inf'):
            price_numeric = None
        
        # Parse listings count
        try:
            listings_int = int(count) if count != "N/A" else 0
        except ValueError:
            listings_int = 0
        
        items_data.append({
            "name": name,
            "base_name": base_name,
            "wear": wear,
            "stattrak": is_stattrak,
            "price": price,
            "price_numeric": price_numeric,
            "listings": listings_int
        })
    
    # Create final data structure
    data = {
        "timestamp": timestamp.isoformat(),
        "source": "steam_market",
        "filters": {
            "wear": wear_filter,
            "stattrak": stattrak_filter
        },
        "total_listings": total_listings,
        "total_items": len(results),
        "items": items_data
    }
    
    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Data saved to: {filename}")
    return filename


def main():
    """Main program logic."""

    # Ask wear condition filter
    print("Choose wear condition filter:")
    print("1. Factory New")
    print("2. Minimal Wear")
    print("3. Field-Tested")
    print("4. Well-Worn")
    print("5. Battle-Scarred")
    print("6. All (show all wear conditions)")
    choice = input("Enter number (default = 6 for all): ").strip() or "6"

    wear_filter_options = {
        "1": "Factory New",
        "2": "Minimal Wear",
        "3": "Field-Tested",
        "4": "Well-Worn",
        "5": "Battle-Scarred",
        "6": "all"
    }
    wear_filter = wear_filter_options.get(choice, "all")

    # Ask StatTrak filter
    stattrak_input = input("StatTrak filter (both/only/no, default=both): ").strip().lower() or "both"

    # HTTP headers
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://steamcommunity.com/market/",
    }

    # Load base items
    base_items = load_base_items(ITEM_FILE)
    all_results = []

    print("\nFetching prices from Steam Market...\n")

    for base_name in base_items:
        # Get all variants with ONE API call
        variants = get_all_variants_for_item(base_name, headers)
        
        # Filter by wear and StatTrak
        for variant_name, (price, count) in variants.items():
            # Apply wear filter
            if wear_filter != "all":
                if f"({wear_filter})" not in variant_name:
                    continue
            
            # Apply StatTrak filter
            if stattrak_input == "only":
                if "StatTrak™" not in variant_name:
                    continue
            elif stattrak_input == "no":
                if "StatTrak™" in variant_name:
                    continue
            # "both" means no filtering
            
            all_results.append((variant_name, price, count))
            print(f"{variant_name:70} -> {price}  |  Listings: {count}")
        
        # Random delay to avoid rate limits
        delay = REQUEST_DELAY + random.uniform(0.5, 2.0)
        time.sleep(delay)

    # Summary
    print("\n==============================")
    print("Covert Items - Price Summary")
    print("==============================\n")

    for name, price, count in all_results:
        print(f"{name:70} | {price:>10} | Listings: {count}")

    print(f"\nTotal items checked: {len(all_results)}")

    # Sort by numeric price
    sorted_results = sorted(all_results, key=lambda x: parse_price(x[1]))

    # Top 10 cheapest
    print("\n==============================")
    print("💰 Top 10 Cheapest Items")
    print("==============================\n")

    for name, price, count in sorted_results[:10]:
        print(f"{name:70} | {price:>10} | Listings: {count}")

    # Count total listings (handle N/A values)
    total_listings = 0
    for _, _, count in all_results:
        try:
            total_listings += int(count) if count != "N/A" else 0
        except ValueError:
            pass
    
    print(f"\nTotal listings in Steam Market: {total_listings}")
    
    # Save results to JSON file
    save_results_to_json(all_results, wear_filter, stattrak_input)

# ===============================
# Entry Point
# ===============================
if __name__ == "__main__":
    main()
