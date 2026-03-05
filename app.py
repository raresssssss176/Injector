import stripe
import sqlite3
from flask import Flask, render_template, request, redirect
from flask_mail import Mail, Message  # New Import
from geopy.geocoders import Nominatim
from math import radians, cos, sin, asin, sqrt
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- SECURE CONFIGURATION ---
stripe.api_key = os.environ.get("STRIPE_API_KEY")

app.config['MAIL_USERNAME'] = 'greengrizzly52@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")
# ... rest of mail config
# --- MAIL SETTINGS (Using Gmail as an example) ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'greengrizzly52@gmail.com'
app.config['MAIL_PASSWORD'] = 'qhel rpwh uopn udjv'
mail = Mail(app)

geolocator = Nominatim(user_agent="car_hunter_web_v1")

def haversine(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 9999
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2 - lon1, lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371

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
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_creation='always', # Ensures we capture the email
            line_items=[{
                'price_data': {
                    'currency': 'ron',
                    'product_data': {'name': f'Car Hunt Results: {query}'},
                    'unit_amount': 500, 
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.host_url + 'success?session_id={CHECKOUT_SESSION_ID}' + \
                        f'&q={query}&p={max_price}&c={user_city}&d={distance}&a={avoid}',
            cancel_url=request.host_url,
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Stripe Error: {e}", 500

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    session = stripe.checkout.Session.retrieve(session_id)
    
    if session.payment_status != 'paid':
        return "Payment not verified.", 403

    # --- PULL EMAIL FROM STRIPE ---
    user_email = session.customer_details.email 

    query = request.args.get('q', '')
    max_price = int(request.args.get('p') or 999999)
    user_city = request.args.get('c', 'Bucuresti')
    max_dist = float(request.args.get('d') or 100)
    avoid_words = request.args.get('a', '').lower().split(',')

    # --- DATABASE SEARCH ---
    user_loc = geolocator.geocode(f"{user_city}, Romania")
    u_lat, u_lon = (user_loc.latitude, user_loc.longitude) if user_loc else (44.4268, 26.1025)

    conn = sqlite3.connect('market.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads WHERE name LIKE ? AND price <= ?", (f'%{query}%', max_price))
    rows = cursor.fetchall()
    conn.close()

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
    try:
        msg = Message(f"Your Car Hunt Results for {query}",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[user_email])
        
        # Simple text body with the top 3 results
        body = f"Hello! Here are your top matches for {query} near {user_city}:\n\n"
        for ad in filtered_ads[:5]: # Send top 5
            body += f"- {ad['name']}: {ad['price']}€ ({ad['km_away']} km away)\n  Link: {ad['link']}\n\n"
        
        msg.body = body
        mail.send(msg)
        print(f"DEBUG: Email sent to {user_email}")
    except Exception as e:
        print(f"MAIL ERROR: {e}")

    return render_template('index.html', ads=filtered_ads)

if __name__ == '__main__':
    app.run(debug=True)