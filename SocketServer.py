import socket

def start_monitor(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen(5)
        print(f"[*] Monitorul 'BatteryLife+' este pornit pe {host}:{port}")
        print("[*] Se așteaptă conexiuni de la iPhone...")

        while True:
            conn, addr = s.accept()
            with conn:
                # Primim datele (primul pachet conține de obicei URL-ul)
                data = conn.recv(1024)
                if data:
                    request_text = data.decode('utf-8', errors='ignore')
                    # Extragem prima linie (ex: GET http://google.com HTTP/1.1)
                    first_line = request_text.split('\n')[0]
                    print(f"[ACCES] Dispozitiv {addr[0]} a vizitat: {first_line}")
                    
                    # Îi trimitem un răspuns gol sau o eroare ca să nu rămână conexiunea agățată
                    conn.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")

# Pornește-l pe calculatorul de acasă (asigură-te că portul 8888 este deschis în router!)
start_monitor("0.0.0.0", 8888)