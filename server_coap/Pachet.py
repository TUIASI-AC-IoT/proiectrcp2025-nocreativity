from functii import (
    upload_request,
    download_request,
    listare_director,
    delete_request,
    move_request,
)
from threading_manager import handle_request_in_thread
import json
import struct

PAYLOAD_MARKER = 0xFF


def parse_coap_header(data):
    #Parsează header CoAP (4 bytes)
    if len(data) < 4:
        raise ValueError("Pachet prea scurt")

    first_byte, code, msg_id = struct.unpack("!BBH", data[:4])

    return {
        "version": (first_byte >> 6) & 0x03,
        "type": (first_byte >> 4) & 0x03,
        "tkl": first_byte & 0x0F,
        "code": code,
        "message_id": msg_id
    }


def parse_packet(data):
    #Parsează pachet CoAP complet
    if PAYLOAD_MARKER in data:
        header_part, payload_part = data.split(bytes([PAYLOAD_MARKER]), 1)
    else:
        header_part, payload_part = data, b""

    header = parse_coap_header(header_part)
    payload = {}

    if payload_part:
        try:
            payload = json.loads(payload_part.decode('utf-8'))
        except json.JSONDecodeError:
            print("Eroare parsare JSON")

    return header, payload


def handle_request(header, payload, client_addr, sock):
    #Procesează cerere în thread separat
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    print(f"\nCerere de la {client_addr}: Code={code}, Type={msg_type}, MsgID={msg_id}")

    # Thread nou pentru procesare, functii in threading_manager.py
    handle_request_in_thread(process_request, header, payload, client_addr, sock)


def process_request(header, payload, client_addr, sock):
    #Procesează cererea efectivă
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    try:
        if code == 1:  # GET
            path = payload.get("path", "")
            if path.endswith("/"):
                listare_director(payload, msg_type, msg_id, client_addr, sock)
            else:
                download_request(payload, msg_type, msg_id, client_addr, sock)

        elif code == 2:  # POST
            upload_request(payload, msg_type, msg_id, client_addr, sock)

        elif code == 4:  # DELETE
            delete_request(payload, msg_type, msg_id, client_addr, sock)

        elif code == 5:  # MOVE
            move_request(payload, msg_type, msg_id, client_addr, sock)

        else:
            print(f"Cod necunoscut: {code}")

    except Exception as e:
        print(f"Eroare procesare: {e}")
        import traceback
        traceback.print_exc()