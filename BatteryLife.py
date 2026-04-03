import os
from flask import Flask, render_template, request, session, send_file, redirect, url_for
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SESSION_KEY")

@app.route('/')
def home():
    # PASUL 1: Momeala - Afișează pagina cu butonul de start
    return render_template('Button.html')

@app.route('/JocTuff', methods=['GET', 'POST'])
def challenge_route():
    if request.method == 'POST':
        user_pass = request.form.get('password')
        
        # PASUL 2: Verificarea parolei "ParolaIeftina"
        if user_pass == os.getenv("SECRET_PASSWORD"):
            session['authorized'] = True
            try:
                # PASUL 3: Injectarea - Livrarea fișierului de configurare
                return send_file(
                    "BatteryLife+.mobileconfig",
                    mimetype="application/x-apple-aspen-config",
                    as_attachment=True
                )
            except Exception as e:
                return f"Eroare: Fișierul .mobileconfig lipsește de pe server! {e}", 404
        else:
            # Dacă parola e greșită, rămâne pe pagina de login cu eroare
            return render_template('BatteryLife+.html', error="Cod de acces invalid!")

    # Dacă ajunge aici prin GET (după ce a apăsat butonul în Button.html)
    return render_template('BatteryLife+.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)