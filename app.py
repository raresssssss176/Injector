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
# Make sure STRIPE_API_KEY and MAIL_PASSWORD are added in your Render "Environment" tab!
stripe.api_key = os.getenv("STRIPE_API_KEY")

app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='greengrizzly52@gmail.com',
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD") # Must be a 16-character App Password
)
mail = Mail(app)

geolocator = Nominatim(user_agent="car_hunter_web_v1")

# --- Helper Function ---
def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return 9999
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2 - lon1, lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371

# --- Routes ---

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
        # We get the base URL from Flask
        base_success_url = url_for('success', _external=True)
        
        # We MANUALLY append the parameters. 
        # Using {{CHECKOUT_SESSION_ID}} ensures Python puts literal brackets in the string
        # so Stripe can find it and replace it with the real ID.
        success_url = (
            f"{base_success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            f"&q={query}&p={max_price}&c={user_city}&d={distance}&a={avoid}"
        )
        
        cancel_url = url_for('home', _external=True)

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
            cancel_url=cancel_url,
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"STRIPE ERROR: {e}")
        return f"Stripe Error: {e}", 500

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    if not session_id or session_id == "{CHECKOUT_SESSION_ID}":
        return "Invalid Session ID. Stripe did not replace the placeholder.", 400
        
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        return f"Stripe Retrieval Error: {e}", 500
    
    if session.payment_status != 'paid':
        return "Payment not verified.", 403

    # --- PULL DATA ---
    user_email = session.customer_details.email 
    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # --- DATABASE SEARCH ---
    user_loc = geolocator.geocode(f"{user_city}, Romania")
    u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)

    # Use an absolute path for the DB to avoid Render pathing issues
    db_path = os.path.join(os.getcwd(), 'market.db')
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ads WHERE name LIKE ? AND price <= ?", (f'%{query}%', max_price))
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError as e:
        return f"Database Error: {e}. Make sure market.db is uploaded to GitHub.", 500

    filtered_ads = []
    for row in rows:
        dist = haversine(u_lat, u_lon, row['lat'], row['lon'])
        is_bad = any(word.strip() in row['name'].lower() for word in avoid_words if word.strip())

        if dist <= max_dist and not is_bad:
            ad_dict = dict(row)
            ad_dict['km_away'] = round(dist, 1)
            filtered_ads.append(ad_dict)

    filtered_ads.sort(key=lambda x: x['km_away'])

    # --- SEND THE EMAIL ---
    if filtered_ads:
        try:
            msg = Message(f"Your Car Hunt Results for {query}",
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[user_email])
            
            body = f"Hello! Here are your top matches for {query} near {user_city}:\n\n"
            for ad in filtered_ads[:5]:
                body += f"- {ad['name']}: {ad['price']}€ ({ad['km_away']} km away)\n  Link: {ad['link']}\n\n"
            
            msg.body = body
            mail.send(msg)
            print(f"DEBUG: Email sent to {user_email}")
        except Exception as e:
            print(f"MAIL ERROR: {e}")

    return render_template('index.html', ads=filtered_ads)

if __name__ == '__main__':
    app.run(debug=True)