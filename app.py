import stripe
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for
from flask_mail import Mail, Message
from geopy.geocoders import Nominatim
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

# 1. Initialize App and Load Environment
load_dotenv()
app = Flask(__name__)

# 2. Secure Configuration
stripe.api_key = os.getenv("STRIPE_API_KEY")

# Mail Config - Using the safer SSL/465 combination for Cloud Hosting
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=465,
    MAIL_USE_SSL=True,
    MAIL_USE_TLS=False,
    MAIL_USERNAME='greengrizzly52@gmail.com',
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD") 
)
mail = Mail(app)
geolocator = Nominatim(user_agent="car_hunter_romania_v1")

# --- Helper Function ---
def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return 9999
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    d = 2 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))
    return d * 6371

# --- Routes ---

@app.route('/')
def home():
    # Clear ads on home page
    return render_template('index.html', ads=[])

@app.route('/search', methods=['POST'])
def search_and_pay():
    query = request.form.get('query', '')
    max_price = request.form.get('max_price', '999999')
    user_city = request.form.get('user_city', 'Bucuresti')
    distance = request.form.get('distance', '100')
    avoid = request.form.get('avoid', '')

    try:
        # Manual URL construction to prevent Flask from encoding Stripe brackets
        base_success_url = url_for('success', _external=True)
        success_url = (
            f"{base_success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            f"&q={query}&p={max_price}&c={user_city}&d={distance}&a={avoid}"
        )
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'ron',
                    'product_data': {'name': f'Search Results: {query}'},
                    'unit_amount': 500, 
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=url_for('home', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"STRIPE ERROR: {e}")
        return f"Payment System Error: {e}", 500

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    
    # Validation
    if not session_id or "{CHECKOUT_SESSION_ID}" in session_id:
        return "Invalid session. Please ensure you completed the payment.", 400
        
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        user_email = session.customer_details.email 
    except Exception as e:
        print(f"RETRIEVAL ERROR: {e}")
        return "Could not verify payment with Stripe.", 500
    
    # Get Search Params from URL
    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # --- DATABASE SEARCH ---
    user_loc = geolocator.geocode(f"{user_city}, Romania")
    u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)

    filtered_ads = []
    db_path = os.path.join(os.getcwd(), 'market.db')
    
    if os.path.exists(db_path):
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
                filtered_ads.append(ad)
        filtered_ads.sort(key=lambda x: x['km_away'])

    # --- EMAIL (BULLETPROOF WRAPPER) ---
    if filtered_ads:
        try:
            msg = Message(f"Car Results: {query}", 
                          sender=app.config['MAIL_USERNAME'], 
                          recipients=[user_email])
            msg.body = f"Top results for {query}:\n\n" + \
                       "\n".join([f"- {a['name']}: {a['price']}€ ({a['km_away']}km) {a['link']}" for a in filtered_ads[:5]])
            
            # If this fails, the except block catches it and the code keeps running!
            mail.send(msg)
        except Exception as e:
            # We log the error but do NOT crash the page
            print(f"CRITICAL MAIL FAILURE (Handled): {e}")

    # Return the results page NO MATTER WHAT
    return render_template('index.html', ads=filtered_ads)

# --- RENDER PORT BINDING ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)