from functii import (
    upload_request,
    download_request,
    listare_director,
    delete_request,
    move_request,
)
import threading_manager as tm
import json
import struct



PAYLOAD_MARKER = 0xFF  # Arată începutul payload-ului


def parse_coap_header(data):
    """Parsează primii 4 bytes ai headerului CoAP"""
    if len(data) < 4:
        raise ValueError("Pachet prea scurt pentru header CoAP")

    # Despachetăm primii 4 bytes: (Version/Type/TKL, Code, Message ID)
    first_byte, code, msg_id = struct.unpack("!BBH", data[:4])

    version = (first_byte >> 6) & 0x03
    msg_type = (first_byte >> 4) & 0x03
    tkl = first_byte & 0x0F

    header = {
        "version": version,
        "type": msg_type,
        "tkl": tkl,
        "code": code,
        "message_id": msg_id
    }

    return header


def parse_packet(data):
    """Parsează un pachet CoAP complet"""
    if PAYLOAD_MARKER in data:
        header_part, payload_part = data.split(bytes([PAYLOAD_MARKER]), 1)
    else:
        header_part, payload_part = data, b""  # Nu există payload

    header = parse_coap_header(header_part)
    payload = {}

    if payload_part:
        try:
            payload = json.loads(payload_part.decode('utf-8'))  # Decodificăm payload-ul JSON
        except json.JSONDecodeError:
            print("[!] Eroare parsare JSON payload")

    return header, payload


def is_ack_packet(header):
    """
    Verifică dacă pachetul este un ACK
    """
    return header.get("type") == 2  # Type = 2 pentru ACK


def handle_request(header, payload, client_addr, sock, packet_queue=None):
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    print(f"\n[>] Cerere primită de la {client_addr}")
    print(f"    Code: {code}, Type: {msg_type}, Message ID: {msg_id}")

    manager = tm.get_manager()

    # Transmitem packet_queue mai departe
    manager.submit_request(
        header, payload, client_addr, sock,
        process_request_threaded,
        extra_args=(packet_queue,)  # doar coada
    )



def process_request_threaded(header, payload, client_addr, sock, io_queue, response_queue, packet_queue=None):
    """
    handler_func primește:
    - header, payload, client_addr, sock, io_queue, response_queue
    - și packet_queue ca argument extra (transmis din main.py prin extra_args)
    """
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    print(f"[*] Thread Procesare: identificat cod={code}")

    if code == 1:  # GET
        path = payload.get("path", "")
        if path.endswith("/"):
            print("[*] → Listare director")
            listare_director(payload, msg_type, msg_id, client_addr, sock)
        else:
            print("[*] → Download fișier")
            # !!Aici transmit packet_queue mai departe
            download_request(payload, msg_type, msg_id, client_addr, sock, packet_queue=packet_queue)

    elif code == 2:  # POST
        print("[*] → Upload fișier")
        upload_request(payload, msg_type, msg_id, client_addr, sock)

    elif code == 4:  # DELETE
        print("[*] → Ștergere")
        delete_request(payload, msg_type, msg_id, client_addr, sock)

    elif code == 5:  # MOVE
        print("[*] → Mutare fișier")
        move_request(payload, msg_type, msg_id, client_addr, sock)

    else:
        print(f"[!] Cod necunoscut: {code}")