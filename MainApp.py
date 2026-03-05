import requests
import sqlite3
import time
import random
from datetime import datetime
from aihelper import summarize_car
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# CONFIGURATION
DATADOME_COOKIE = "qjBwY28eJkMNwmBh2QLKETGsSHWSuGCMUBavrbTfMMfSoaeGp1wkiV0tsbzC_Ici7~frX8EuoPytYO7cN0bFDYTWG~m0MEZlBTqiWQb~jDAaoGmo28P0L3K8W2Ap8vx6here"

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
    headers = {
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        'cookie': f'datadome={DATADOME_COOKIE}',
    }
    
    payload = {
        'query': GRAPHQL_QUERY,
        'variables': {
            'searchParameters': [
                {'key': 'offset', 'value': '0'},
                {'key': 'limit', 'value': '10'}, 
                {'key': 'category_id', 'value': '84'},
            ]
        }
    }

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