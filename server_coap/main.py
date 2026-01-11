import socket
import json
import base64
import threading
import time

from Pachet import handle_request, parse_packet
from threading_manager import start_workers, stop_workers

SERVER_PORT = 5683

# Socket server
server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_sock.bind(("0.0.0.0", SERVER_PORT))

print(f"[*] Server CoAP pornit pe port {SERVER_PORT}")

# Pornește worker
start_workers()


def test_client():
    """Test automat la pornire"""
    time.sleep(1)

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.settimeout(5.0)

    test_content = "Test automat la pornire server".encode("utf-8")
    content_b64 = base64.b64encode(test_content).decode("utf-8")

    payload_json = json.dumps({
        "path": "storage/test_automat.txt",
        "content": content_b64
    }).encode("utf-8")

    # Header CoAP: Ver=1, Type=0 (CON), Code=0.02 (POST), MsgID=12345
    header = bytes([0x40, 0x02, 0x30, 0x39])
    packet = header + bytes([0xFF]) + payload_json

    print("[TEST] Trimit pachet upload...\n")

    try:
        client_sock.sendto(packet, ("127.0.0.1", SERVER_PORT))

        data, addr = client_sock.recvfrom(65535)
        header_resp, resp_payload = parse_packet(data)

        if resp_payload.get("status") == "created":
            print(f"[TEST] ✓ Fișier creat: {resp_payload.get('path')}")
        else:
            print(f"[TEST] Eroare: {resp_payload}")

    except socket.timeout:
        print("[TEST] Timeout")
    except Exception as e:
        print(f"[TEST] Eroare: {e}")
    finally:
        client_sock.close()


# Test în thread separat
threading.Thread(target=test_client, daemon=True).start()

# Loop principal
try:
    print("[*] Așteaptă cereri...\n")

    while True:
        try:
            data, client_addr = server_sock.recvfrom(65535)

            header, payload = parse_packet(data)

            # Ignoră ACK-uri goale
            if header['type'] == 2 and header['code'] == 0 and not payload:
                continue

            handle_request(header, payload, client_addr, server_sock)

        except Exception as e:
            print(f"[!] Eroare recvfrom: {e}")
            continue

except KeyboardInterrupt:
    print("\n[*] Oprire server...")
finally:
    stop_workers()
    server_sock.close()
    print("[*] Server oprit")