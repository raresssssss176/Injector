import requests
import sqlite3
import time
import random
from datetime import datetime
from aihelper import summarize_car
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import os
from dotenv import load_dotenv

load_dotenv()

# CONFIGURATION
DATADOME_COOKIE = os.environ.get("DATADOME_COOKIE")

# Initialize Geocoder
geolocator = Nominatim(user_agent="car_hunter_romania_v1")

def get_coords(city_name):
    """Converts a city name into Latitude and Longitude via API."""
    try:
        location = geolocator.geocode(f"{city_name}, Romania")
        if location:
            return location.latitude, location.longitude
    except (GeocoderTimedOut, Exception):
        return None, None
    return None, None

def cleanup_old_ads():
    """Deletes ads that haven't been seen in the last 24 hours."""
    with sqlite3.connect('market.db') as conn:
        cursor = conn.cursor()
        # Delete records where last_seen is older than 1 day
        cursor.execute("""
            DELETE FROM ads 
            WHERE last_seen < datetime('now', '-1 day')
        """)
        conn.commit()
        print(f"cleaned up {cursor.rowcount} expired ads.")

def save_to_db(ad_id, title, price_str, url, summary, city):
    # 1. Price Cleaning
    clean_price = ''.join(filter(str.isdigit, price_str)) 
    clean_price = int(clean_price) if clean_price else 0

    with sqlite3.connect('market.db') as conn:
        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ads 
            (id TEXT PRIMARY KEY, name TEXT, price INTEGER, link TEXT, 
             ai_summary TEXT, location TEXT, lat REAL, lon REAL, last_seen TEXT)
        ''')

        # 2. SMART LOOKUP: Check if we already have coordinates for this city
        cursor.execute('SELECT lat, lon FROM ads WHERE location = ? AND lat IS NOT NULL LIMIT 1', (city,))
        geo_result = cursor.fetchone()

        if geo_result:
            lat, lon = geo_result[0], geo_result[1]
        else:
            # Only call API if city is unknown
            lat, lon = get_coords(city)
            time.sleep(1.1) # Respect Nominatim's 1-call-per-second rule

        # 3. UPSERT (Update or Insert)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO ads (id, name, price, link, ai_summary, location, lat, lon, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET 
                ai_summary=excluded.ai_summary, 
                price=excluded.price,
                location=excluded.location,
                lat=excluded.lat,
                lon=excluded.lon,
                last_seen=excluded.last_seen
        ''', (ad_id, title, clean_price, url, summary, city, lat, lon, timestamp))
        conn.commit()

GRAPHQL_QUERY = """
query ListingSearchQuery($searchParameters: [SearchParameter!] = []) {
  clientCompatibleListings(searchParameters: $searchParameters) {
    ... on ListingSuccess {
      data {
        id
        title
        description
        url
        location { city { name } }
        params {
          key
          value { ... on PriceParam { value currency } }
        }
      }
    }
  }
}
"""

def run():
    print("🚀 Starting Car Hunter Scraper...")
    
    cookies = {
        'deviceGUID': 'e0ba844f-cba0-4e76-b48c-8b37dd10f636',
        'datadome': 'qjBwY28eJkMNwmBh2QLKETGsSHWSuGCMUBavrbTfMMfSoaeGp1wkiV0tsbzC_Ici7~frX8EuoPytYO7cN0bFDYTWG~m0MEZlBTqiWQb~jDAaoGmo28P0L3K8W2Ap8vx6',
        '__user_id_P&S': '532946208',
        'laquesisff': 'aut-1425#aut-388#buy-2279#buy-2489#carparts-312#cars-78563#dat-2874#dc-83#de-2724#decision-256#decision-657#do-3481#ema-518#ema-54#euonb-114#eus-1773#f8nrp-1779#jobs-7611#kuna-307#mart-1341#oec-1238#oesx-2798#oesx-4295#pay-287#pos-1043#pos-2021#pos-2216#posting-1419#posting-1638#rm-28#rm-707#rm-780#rm-824#rm-852#sd-3192#srt-1289#srt-1346#srt-1434#srt-1593#srt-1758#srt-684#uacc-529#udp-1535#up-90',
        'laquesis': 'ema-249@a#eupp-3842@a#jobs-10612@a#oesx-5284@b#oesx-5576@b#olxeu-42926@a#olxeu-42958@a#pos-2829@b#recpl-1312@a',
        'lqstatus': '1772882204377|19c764a18efx2daeeb98|recpl-1154|||0|1772881184377|0',
        'PHPSESSID': '6o4teepqvhh859fng46t58eljt',
        'onap': '19b32962758x7e95150d-16-19cc7f4067ax69585a31-93-1772883667568',
    }

    headers = {
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        'referer': 'https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/q-skoda/?currency=EUR',
        'x-client': 'DESKTOP',
    }
    
    payload = {
        'query': GRAPHQL_QUERY,
        'variables': {
            'searchParameters': [
                {'key': 'offset', 'value': '39'},
                {'key': 'limit', 'value': '39'}, 
                {'key': 'category_id', 'value': '84'},
            ]
        }
    }

    # Execute the request
    response = requests.post(
        'https://www.olx.ro/apigateway/graphql', 
        headers=headers, 
        cookies=cookies, 
        json=payload
    )

    if response.status_code == 200:
        print("📡 Connected to OLX API...")
        data = response.json()
        
        # Accessing the correct path in the GraphQL response
        listings = data.get('data', {}).get('clientCompatibleListings', {}).get('data', [])
        
        if not listings:
            print("⚠️ No listings found. Your cookies might be expired.")
            return

        for ad in listings:
            price_val = "0"
            for p in ad.get('params', []):
                if p['key'] == 'price':
                    # Extracting value from PriceParam structure
                    price_data = p.get('value', {})
                    price_val = str(price_data.get('value', '0'))
            
            city_name = "Unknown"
            if ad.get('location') and ad['location'].get('city'):
                city_name = ad['location']['city'].get('name', 'Unknown')
            
            # AI Analysis
            analysis = summarize_car(ad['title'], ad.get('description', 'No description found')) 
            
            save_to_db(ad['id'], ad['title'], price_val, ad['url'], analysis, city_name)
            print(f"✅ Processed {ad['title']} in {city_name} (Price: {price_val} RON)")
            
            # Random sleep to avoid getting banned
            time.sleep(random.uniform(2, 4))
    else:
        print(f"❌ HTTP Error {response.status_code}")
        if response.status_code == 403:
            print("🛑 DataDome blocked the request. You need a fresh cookie!")


    response = requests.post('https://www.olx.ro/apigateway/graphql', headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        listings = data['data']['clientCompatibleListings'].get('data', [])
        
        for ad in listings:
            price_val = "0"
            for p in ad.get('params', []):
                if p['key'] == 'price':
                    price_val = f"{p['value'].get('value', '0')}"
            
            city_name = "Unknown"
            if ad.get('location') and ad['location'].get('city'):
                city_name = ad['location']['city'].get('name', 'Unknown')
            
            # AI Analysis
            analysis = summarize_car(ad['title'], ad.get('description', 'No description found')) 
            
            save_to_db(ad['id'], ad['title'], price_val, ad['url'], analysis, city_name)
            print(f"✅ Processed {ad['title']} in {city_name}")
            
            time.sleep(random.uniform(2, 4))
    else:
        print(f"❌ HTTP Error {response.status_code}")

if __name__ == "__main__":
    run()
    cleanup_old_ads()