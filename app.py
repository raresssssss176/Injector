import stripe
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for
from flask_mail import Mail, Message
from geopy.geocoders import Nominatim
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- SECURE CONFIGURATION ---
stripe.api_key = os.environ.get("STRIPE_API_KEY")

app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='greengrizzly52@gmail.com',
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD")
)
mail = Mail(app)
geolocator = Nominatim(user_agent="car_hunter_web_v1")

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
        # Use url_for for the base, then manually add the Stripe placeholder
        # This prevents the { } from being converted into %7B %7D
        base_url = url_for('success', _external=True)
        success_url = (
            f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
            f"&q={query}&p={max_price}&c={user_city}&d={distance}&a={avoid}"
        )
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_creation='always',
            line_items=[{
                'price_data': {
                    'currency': 'ron',
                    'product_data': {'name': f'Car Hunt Results: {query}'},
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
        return f"Stripe Error: {e}", 500

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    # Retrieval logic
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        return f"Error retrieving payment: {e}", 400
        
    if session.payment_status != 'paid':
        return "Payment not verified.", 403

    user_email = session.customer_details.email 
    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # --- DATABASE SEARCH ---
    user_loc = geolocator.geocode(f"{user_city}, Romania")
    u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)

    db_path = os.path.join(os.getcwd(), 'market.db')
    filtered_ads = []
    
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

    # --- EMAIL ---
    if filtered_ads:
        try:
            msg = Message(f"Your Car Hunt Results for {query}",
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[user_email])
            body = f"Hello! Top matches for {query} near {user_city}:\n\n"
            for ad in filtered_ads[:5]:
                body += f"- {ad['name']}: {ad['price']}€ ({ad['km_away']} km away)\n Link: {ad['link']}\n\n"
            msg.body = body
            mail.send(msg)
        except Exception as e:
            print(f"MAIL ERROR (Non-fatal): {e}")

    return render_template('index.html', ads=filtered_ads)

# --- THE RENDER BOOT FIX ---
if __name__ == '__main__':
    # Using '0.0.0.0' and the PORT env variable is required for Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)