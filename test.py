import os
from dotenv import load_dotenv

# Path to your file
env_path = r"C:\Users\Rares\Desktop\olxapp\OLX_SaaS\.env"

# We manually open it with utf-8-sig to bypass Windows "BOM" errors
with open(env_path, encoding='utf-8-sig') as f:
    load_dotenv(stream=f, override=True)

stripe_key = os.getenv("STRIPE_API_KEY")

if stripe_key:
    print(f"✅ FINAL SUCCESS! Key found: {stripe_key[:10]}...")
else:
    # If this fails, let's see what is actually inside the file
    with open(env_path, 'r') as f:
        print("--- File Content Raw ---")
        print(f.read())