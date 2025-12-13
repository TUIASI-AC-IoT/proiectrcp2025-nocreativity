from functii import (
    upload_request,
    download_request,
    listare_director,
    delete_request,
    move_request,
    exista_storage
)
import fragmentare_pachet as f
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

    Args:
        header: Header-ul pachetului CoAP

    Returns:
        bool: True dacă este ACK
    """
    return header.get("type") == 2  # Type = 2 pentru ACK


def handle_request(header, payload, client_addr, sock):
    """
    Procesează cererea primită conform arhitecturii din documentație

    FLOW:
    1. Main Thread apelează această funcție
    2. Se creează un Thread de Procesare Cereri
    3. Thread-ul de procesare va delega către:
       - Thread I/O pentru operații pe fișiere
       - Thread Răspuns pentru trimiterea răspunsului

    Coduri suportate:
    - 1: GET (download fișier sau listare director)
    - 2: POST (upload fișier)
    - 4: DELETE (ștergere fișier/director)
    - 5: MOVE (mutare fișier)

    ACK-uri primite pentru fragmente sunt procesate separat
    """
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    # Verificăm dacă este un ACK pentru un fragment
    if is_ack_packet(header):
        print(f"[>] ACK primit de la {client_addr} (msg_id={msg_id})")

        # Procesăm ACK-ul pentru fragmentare
        f.process_fragment_ack(client_addr, msg_id)

        # Nu mai procesăm ca cerere normală
        return

    # Log cerere
    print(f"\n[>] Cerere primită în Main Thread de la {client_addr}")
    print(f"    Code: {code}, Type: {msg_type}, Message ID: {msg_id}")

    # Obținem manager-ul de threading
    manager = tm.get_manager()

    # Submitează cererea pentru procesare într-un Thread separat
    # Conform schemei: Main Thread → Thread de Procesare Cereri
    manager.submit_request(
        header, payload, client_addr, sock,
        process_request_threaded
    )


def process_request_threaded(header, payload, client_addr, sock, io_queue, response_queue):
    """
    Funcție care rulează în Thread de Procesare Cereri

    Conform schemei:
    - Decodifică pachetul (deja făcut în handle_request)
    - Identifică metoda
    - Creează Thread pentru I/O (dacă e necesar)
    - Creează Thread pentru răspuns

    Args:
        header: Header-ul pachetului
        payload: Payload-ul JSON
        client_addr: Adresa clientului
        sock: Socket-ul serverului
        io_queue: Coada pentru operații I/O
        response_queue: Coada pentru răspunsuri
    """
    code = header.get("code")
    msg_type = header.get("type")
    msg_id = header.get("message_id")

    print(f"[*] Thread Procesare: identificat cod={code}")

    # Identificăm metoda și apelăm handler-ul corespunzător
    # Handler-ii vor folosi io_queue și response_queue

    if code == 1:  # GET
        path = payload.get("path", "")
        if path.endswith("/"):
            print("[*] → Listare director (va folosi Thread I/O)")
            listare_director(payload, msg_type, msg_id, client_addr, sock)
        else:
            print("[*] → Download fișier (va folosi Thread I/O)")
            download_request(payload, msg_type, msg_id, client_addr, sock)

    elif code == 2:  # POST
        print("[*] → Upload fișier (va folosi Thread I/O)")
        upload_request(payload, msg_type, msg_id, client_addr, sock)

    elif code == 4:  # DELETE
        print("[*] → Ștergere (va folosi Thread I/O)")
        delete_request(payload, msg_type, msg_id, client_addr, sock)

    elif code == 5:  # MOVE
        print("[*] → Mutare fișier (va folosi Thread I/O)")
        move_request(payload, msg_type, msg_id, client_addr, sock)

    else:
        print(f"[!] Cod necunoscut: {code}")