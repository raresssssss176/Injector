import stripe
import sqlite3
import os
import resend
from flask import Flask, render_template, request, redirect, url_for
from geopy.geocoders import Nominatim
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- CONFIG ---
stripe.api_key = os.getenv("STRIPE_API_KEY")
resend.api_key = os.getenv("RESEND_API_KEY")

# Geopy with high timeout to avoid hanging the worker
geolocator = Nominatim(user_agent="car_hunter_romania_v2", timeout=10)

def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return 9999
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    d = 2 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))
    return d * 6371

@app.route('/')
def home():
    return render_template('index.html', ads=[])

@app.route('/search', methods=['POST'])
def search_and_pay():
    query = request.form.get('query', '')
    max_price = request.form.get('max_price', '999999')
    user_city = request.form.get('user_city', 'Bucuresti')
    distance = request.form.get('distance', '100')
    avoid = request.form.get('avoid', '')

    try:
        base_success_url = url_for('success', _external=True)
        # Manually building success URL to protect the {CHECKOUT_SESSION_ID} curly brackets
        success_url = (
            f"{base_success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            f"&q={query}&p={max_price}&c={user_city}&d={distance}&a={avoid}"
        )
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'ron', 
                    'product_data': {'name': f'Car Search: {query}'}, 
                    'unit_amount': 1200
                }, 
                'quantity': 1
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=url_for('home', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"Stripe Setup Error: {e}")
        return f"Payment Initialization Error: {e}", 500

@app.route('/success')
def success():
    # 1. Collect URL parameters
    session_id = request.args.get('session_id')
    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # 2. Retrieve Email from Stripe
    user_email = None
    if session_id and "{CHECKOUT_SESSION_ID}" not in session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            user_email = session.customer_details.email 
        except Exception as e:
            print(f"Stripe retrieval failed: {e}")

    # 3. Geolocation (with Bucharest fallback)
    try:
        user_loc = geolocator.geocode(f"{user_city}, Romania")
        u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)
    except:
        u_lat, u_lon = (44.4268, 26.1025)

    # 4. Database Search
    filtered_ads = []
    try:
        db_path = os.path.join(os.getcwd(), 'market.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Basic keyword search
            cursor.execute("SELECT * FROM ads WHERE name LIKE ? AND price <= ?", (f'%{query}%', max_price))
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                dist = haversine(u_lat, u_lon, row['lat'], row['lon'])
                is_bad = any(w.strip() in row['name'].lower() for w in avoid_words if w.strip())
                if dist <= max_dist and not is_bad:
                    ad = dict(row)
                    ad['km_away'] = round(dist, 1)
                    filtered_ads.append(ad)
            
            filtered_ads.sort(key=lambda x: x['km_away'])
    except Exception as e:
        print(f"Database/Filter Error: {e}")

    # 5. Fast API Email (Resend)
    # This is non-blocking and won't cause the 500 Internal Server Error
    if filtered_ads and user_email:
        try:
            ad_text = "\n".join([f"- {a['name']}: {a['price']}€ ({a['km_away']}km) {a['link']}" for a in filtered_ads[:5]])
            
            resend.Emails.send({
                "from": "CarHunter <alerts@carhunterengine.com>",
                "to": [user_email],
                "subject": f"Your Matches for {query}",
                "text": f"Found {len(filtered_ads)} cars near {user_city}!\n\nTop Matches:\n{ad_text}"
            })
            print(f"API email successfully triggered for {user_email}")
        except Exception as e:
            print(f"Resend API Failure (Silent): {e}")

    # 6. Always return results to the user
    return render_template('index.html', ads=filtered_ads)

if __name__ == '__main__':
    # Required for Render deployment
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)