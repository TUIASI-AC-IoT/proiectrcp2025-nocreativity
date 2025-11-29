import json
import struct
import functii

PAYLOAD_MARKER = 0xFF # arată inceputul payloadului


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
    if PAYLOAD_MARKER in data:
        header_part, payload_part = data.split(bytes([PAYLOAD_MARKER]), 1)
    else:
        header_part, payload_part = data, b"" #nu exista payload

    header = parse_coap_header(header_part)

    payload = {}
    if payload_part:
        try:
            payload = json.loads(payload_part.decode('utf-8')) #decodificam payloadul, il facem sub forma de json
        except json.JSONDecodeError:
            print("[!] Eroare parsare JSON payload")

    return header, payload



def handle_request(header, payload, client_addr, sock):
    """Procesează cererea primită în funcție de codul CoAP"""
    code = header.get("code")
    msg_type=header.get("type")
    msg_id=header.get("message_id")

    print(f"Cerere primita: code={code}, type={msg_type}, msg_id={msg_id}")
    print(f"De la: {client_addr}")
    print(f"Payload: {payload}")

    if code == 1:
        path = payload.get("path", "")
        if path.endswith("/"):
            print("Procesare: Listare director")
            functii.listare_director(payload,msg_type,msg_id,client_addr, sock)
        else:
            print("Procesare: Download fisier")
            functii.download_request(payload,msg_type,msg_id,client_addr, sock)
    elif code == 2:
        print("Procesare: Upload fisier")
        functii.upload_request(payload,msg_type,msg_id,client_addr, sock)
    elif code == 4:
        print("Procesare: Delete fisier")
        functii.delete_request(payload,msg_type,msg_id,client_addr, sock)
    elif code == 5:
        print("Procesare: Mutare fisier")
        functii.move_request(payload,msg_type,msg_id,client_addr, sock)
    else:
        print(f"cod necunoscut! {code}")