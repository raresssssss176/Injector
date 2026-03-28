import stripe
import sqlite3
import os
import resend
from flask import Flask, render_template, request, redirect, url_for, session
from geopy.geocoders import Nominatim
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- CONFIG ---
stripe.api_key = os.getenv("STRIPE_API_KEY")
resend.api_key = os.getenv("RESEND_API_KEY")
app.secret_key = os.getenv("SESSION_KEY")

# Simple admin access for your "Sandwich Shop" sub-app
SANDWICHES = [
    {"id": "1", "name": "Pesto", "price": 5, "img": "20260319_173017.jpg"},
    {"id": "2", "name": "Simplu", "price": 4, "img": "20260319_173139.jpg"},
    {"id": "3", "name": "Dulce", "price": 5, "img": "20260319_173448.jpg"},
    {"id": "4", "name": "Cu paine de casa", "price": 5, "img": "20260319_173929.jpg"},
    {"id": "5", "name": "Cu paine prajita si bacon", "price": 6, "img": "20260319_174626.jpg"}
]

geolocator = Nominatim(user_agent="car_hunter_romania_v2", timeout=10)

def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return 9999
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    d = 2 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))
    return d * 6371

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html', ads=[], is_teaser=False)

@app.route('/search', methods=['POST'])
def search_teaser():
    """Performs a free search but only returns 3 'locked' results."""
    query = request.form.get('query', '')
    max_price = int(request.form.get('max_price') or 999999)
    user_city = request.form.get('user_city', 'Bucuresti')
    max_dist = float(request.form.get('distance') or 100)
    avoid_words = request.form.get('avoid', '').lower().split(',')

    # 1. Geolocation
    try:
        user_loc = geolocator.geocode(f"{user_city}, Romania")
        u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)
    except:
        u_lat, u_lon = (44.4268, 26.1025)

    # 2. Database Query
    teaser_ads = []
    total_found = 0
    try:
        db_path = os.path.join(os.getcwd(), 'market.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ads WHERE name LIKE ? AND price <= ?", (f'%{query}%', max_price))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            dist = haversine(u_lat, u_lon, row['lat'], row['lon'])
            is_bad = any(w.strip() in row['name'].lower() for w in avoid_words if w.strip())
            if dist <= max_dist and not is_bad:
                ad = dict(row)
                ad['km_away'] = round(dist, 1)
                teaser_ads.append(ad)
        
        teaser_ads.sort(key=lambda x: x['km_away'])
        total_found = len(teaser_ads)
        
        # 3. SECURE BLUR: Replace real data with placeholders for the teaser
        # This prevents users from seeing the price/link in the HTML source code.
        display_ads = []
        for ad in teaser_ads[:3]:
            locked_ad = ad.copy()
            locked_ad['price'] = "???"
            locked_ad['link'] = "#"
            display_ads.append(locked_ad)

    except Exception as e:
        print(f"Teaser Search Error: {e}")
        display_ads = []

    return render_template('index.html', 
                           ads=display_ads, 
                           is_teaser=True, 
                           total_found=total_found,
                           params=request.form)

@app.route('/buy-results', methods=['POST'])
def buy_results():
    """Redirects user to Stripe to unlock the full list."""
    # Capture the same filters used in the teaser
    q = request.form.get('q')
    p = request.form.get('p')
    c = request.form.get('c')
    d = request.form.get('d')
    a = request.form.get('a')

    try:
        base_success_url = url_for('success', _external=True)
        success_url = (
            f"{base_success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            f"&q={q}&p={p}&c={c}&d={d}&a={a}"
        )
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'ron', 
                    'product_data': {'name': f'Unlock {q} Results near {c}'}, 
                    'unit_amount': 1200 # 12.00 RON
                }, 
                'quantity': 1
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=url_for('home', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Stripe Error: {e}", 500

@app.route('/success')
def success():
    """Retrieved after payment. Shows ALL results and emails the user."""
    session_id = request.args.get('session_id')
    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # 1. Retrieve Email from Stripe
    user_email = None
    if session_id and "{CHECKOUT_SESSION_ID}" not in session_id:
        try:
            stripe_session = stripe.checkout.Session.retrieve(session_id)
            user_email = stripe_session.customer_details.email 
        except: pass

    # 2. Geolocation
    try:
        user_loc = geolocator.geocode(f"{user_city}, Romania")
        u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)
    except: u_lat, u_lon = (44.4268, 26.1025)

    # 3. Full Database Search (No Limit)
    all_ads = []
    try:
        conn = sqlite3.connect('market.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ads WHERE name LIKE ? AND price <= ?", (f'%{query}%', max_price))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            dist = haversine(u_lat, u_lon, row['lat'], row['lon'])
            is_bad = any(w.strip() in row['name'].lower() for w in avoid_words if w.strip())
            if dist <= max_dist and not is_bad:
                ad = dict(row)
                ad['km_away'] = round(dist, 1)
                all_ads.append(ad)
        all_ads.sort(key=lambda x: x['km_away'])
    except Exception as e: print(f"Db Error: {e}")

    # 4. Email Results via Resend
    if all_ads and user_email:
        try:
            ad_text = "\n".join([f"- {a['name']}: {a['price']}€ ({a['km_away']}km) {a['link']}" for a in all_ads[:10]])
            resend.Emails.send({
                "from": "CarHunter <alerts@carhunterengine.com>",
                "to": [user_email],
                "subject": f"Unlocked: {len(all_ads)} cars for {query}",
                "text": f"Success! Here are your matches:\n\n{ad_text}"
            })
        except: pass

    return render_template('index.html', ads=all_ads, is_teaser=False)

# --- ADMIN / SANDWICH SHOP ---

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == os.getenv("ADMIN_PASSWORD"):
        session['is_sandwich_pro'] = True  
        return redirect(url_for('sandwich_shop'))
    return "Wrong password!", 401

@app.route('/sandwiches')
def sandwich_shop():
    if not session.get('is_sandwich_pro'):
        return redirect(url_for('home'))
    return render_template('sandwiches.html', menu=SANDWICHES)

@app.route('/order-sandwich/<item_id>', methods=['POST'])
def order_sandwich(item_id):
    sandwich = next((s for s in SANDWICHES if s['id'] == item_id), None)
    if not sandwich: return "Not found", 404

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price_data': {'currency': 'ron', 'product_data': {'name': sandwich['name']}, 'unit_amount': int(sandwich['price'] * 100)}, 'quantity': 1}],
        mode='payment',
        success_url=url_for('home', _external=True),
        cancel_url=url_for('sandwich_shop', _external=True),
    )
    return redirect(checkout_session.url, code=303)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)