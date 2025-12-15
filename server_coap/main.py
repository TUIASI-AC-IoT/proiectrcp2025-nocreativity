import socket
import json
import base64
import threading
import time
import queue

from Pachet import handle_request, parse_packet
import threading_manager as tm

SERVER_PORT = 5683

# Socket server
server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_sock.bind(("0.0.0.0", SERVER_PORT))

#coada globala pentru pachetele primite
incoming = queue.Queue()

manager = tm.get_manager()

print(f"[*] Server CoAP pornit pe port {SERVER_PORT}")
print(f"[*] Așteaptă cereri... (Ctrl+C pentru oprire)\n")


def process_incoming_packets():
    while True:
        try:
            data, client_addr = incoming.get()
            header, payload = parse_packet(data)
            if header['type'] == 2 and header['code'] == 0 and not payload:  # ACK empty, ignor
                continue
            handle_request(header, payload, client_addr, server_sock, incoming)
        except Exception as e:
            print(f"[!] Eroare procesare pachet din coadă: {e}")

# def test_client():
#     # Așteptăm sa se porneasca serverul
#     time.sleep(2)
#
#     # NU fac bind() pe client, las  OS-ul sa aleaga portul
#     client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     client_sock.settimeout(5.0)
#
#     test_content = "Salut din test! Fișier uploadat automat la pornire.".encode("utf-8")
#     content_b64 = base64.b64encode(test_content).decode("utf-8")
#
#     payload_json = json.dumps({
#         "path": "storage/test_upload_automat.txt",
#         "content": content_b64
#     }).encode("utf-8")
#
#     # Header CoAP: Ver=1, Type=0 (CON), TKL=0, Code=0.02 (POST), Message ID=12345
#     header = bytes([0x40, 0x02, 0x30, 0x39])  # MsgID = 12345 (0x3039)
#     packet = header + bytes([0xFF]) + payload_json
#
#     print("[TEST] Trimit pachet upload de test către server...\n")
#
#     try:
#         client_sock.sendto(packet, ("127.0.0.1", SERVER_PORT))
#         print("[TEST] Pachet trimis cu succes ,fără eroare la sendto ")
#
#         # Așteptăm răspunsul
#         data, addr = client_sock.recvfrom(65535)
#         header_resp, resp_payload = parse_packet(data)
#
#         print(f"[TEST] Răspuns primit de la server:")
#         print(f"    Code: {header_resp['code']} ({'2.01 Created' if header_resp['code'] == 65 else 'Eroare'})")
#         print(f"    Payload: {resp_payload}")
#
#         if resp_payload.get("status") == "created":
#             print(f"\n[TEST] SUCCESS! Fișierul a fost creat: {resp_payload.get('path')}")
#             print(f"    Dimensiune: {resp_payload.get('size')} bytes")
#         else:
#             print(f"\n[TEST] Eroare la creare fișier: {resp_payload}")
#
#     except socket.timeout:
#         print("[TEST] Timeout – serverul nu a răspuns la timp")
#     except Exception as e:
#         print(f"[TEST] Eroare neașteptată: {type(e).__name__}: {e}")
#     finally:
#         client_sock.close()

# Pornim thread-ul de procesare
threading.Thread(target=process_incoming_packets, daemon=True).start()

# # Pornim testul în thread separat
# threading.Thread(target=test_client, daemon=True).start()

try:
    while True:
        try:
            data, client_addr = server_sock.recvfrom(5003)
            #pun pachetul in coada
            incoming.put((data, client_addr))
        except Exception as e:
            print(f"[!] Eroare recvfrom in main thread: {e}")
            continue

except KeyboardInterrupt:
    print("\n[*] Oprire server...")
finally:
    tm.shutdown_manager()
    server_sock.close()