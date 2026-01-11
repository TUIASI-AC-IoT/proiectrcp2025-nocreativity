import os
import shutil
import struct
import json
import base64
import fragmentare_pachet as frag
from threading_manager import submit_response

PAYLOAD_MARKER = 0xFF
STORAGE = "storage"

# Coduri CoAP
COAP = {
    "CREATED": 65,  # 2.01
    "DELETED": 66,  # 2.02
    "CHANGED": 68,  # 2.04
    "CONTENT": 69,  # 2.05
    "BAD_REQUEST": 128,  # 4.00
    "NOT_FOUND": 132,  # 4.04
    "UNPROCESSABLE": 150,  # 4.22
    "SERVER_ERROR": 160  # 5.00
}


def exista_storage():
    if not os.path.exists(STORAGE):
        os.makedirs(STORAGE)


def valideaza_director(file_path):
    """True dacă path începe cu storage/"""
    if not file_path:
        return False
    return file_path.split("/")[0] == STORAGE


def build_response(sock, client_addr, msg_id, payload, code=69, msg_type=2):
    """Construiește și trimite răspuns"""
    first_byte = (1 << 6) | (msg_type << 4)  # version=1, tkl=0
    header = struct.pack("!BBH", first_byte, code, msg_id)
    packet = header + bytes([PAYLOAD_MARKER]) + payload
    submit_response(sock, client_addr, packet)


# ============================================================================
# UPLOAD
# ============================================================================

def upload_request(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Payload required"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")
    content = payload.get("content")

    if not file_path or content is None:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Missing fields"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Path invalid"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    if frag.is_fragment_upload(payload):
        handle_fragmented_upload(payload, msg_type, msg_id, client_addr, sock)
    else:
        handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock)


def handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock):
    try:
        file_bytes = base64.b64decode(content)

        if len(file_bytes) > frag.MAX_FILE_SIZE:
            raise ValueError(f"Fișier prea mare: max {frag.MAX_FILE_SIZE} bytes")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(file_bytes)
            f.flush()
            os.fsync(f.fileno())

        file_size = os.path.getsize(file_path)

        if msg_type == 0:
            resp = json.dumps({"status": "created", "path": file_path, "size": file_size}).encode("utf-8")
            build_response(sock, client_addr, msg_id, resp, COAP["CREATED"])

        print(f"[+] Upload: {file_path} ({file_size} bytes)")

    except Exception as e:
        print(f"[!] Eroare upload: {e}")
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])


def handle_fragmented_upload(payload, msg_type, msg_id, client_addr, sock):
    """Upload fragmentat - ACK la fiecare fragment + final"""
    file_path = payload.get("path")
    content = payload.get("content")

    index, total, size = frag.get_fragment_info(payload)

    print(f"[←] Fragment {index + 1}/{total} pentru {file_path}")

    is_complete, assembled = frag.assembler.add_fragment(file_path, index, total, content)

    # ACK pentru fiecare fragment (nu doar progres)
    if not is_complete:
        progress = frag.assembler.get_progress(file_path)
        if progress:
            print(f"    Progres: {progress['received']}/{progress['total']} ({progress['percentage']:.1f}%)")

        # Trimite ACK intermediar
        if msg_type == 0:
            resp = json.dumps({
                "status": "fragment_received",
                "fragment": {"index": index, "total": total}
            }).encode("utf-8")
            build_response(sock, client_addr, msg_id, resp, COAP["CONTENT"])
        return

    # COMPLET - salvăm și trimitem ACK
    try:
        file_bytes = base64.b64decode(assembled)

        if len(file_bytes) > frag.MAX_FILE_SIZE:
            raise ValueError(f"Fișier prea mare: max {frag.MAX_FILE_SIZE} bytes")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(file_bytes)
            f.flush()
            os.fsync(f.fileno())

        file_size = os.path.getsize(file_path)

        print(f"[+] Upload complet: {file_path} ({file_size} bytes, {total} fragmente)")

        if msg_type == 0:
            resp = json.dumps({
                "status": "created",
                "path": file_path,
                "size": file_size,
                "fragments": total
            }).encode("utf-8")
            build_response(sock, client_addr, msg_id, resp, COAP["CREATED"])

    except Exception as e:
        print(f"[!] Eroare asamblare: {e}")
        frag.assembler.clear_path(file_path)
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])


# ============================================================================
# DOWNLOAD
# ============================================================================

def download_request(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Payload required"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")
    if not file_path or not valideaza_director(file_path):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Invalid path"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "File not found"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        file_size = len(file_bytes)

        if file_size > frag.MAX_FILE_SIZE:
            raise ValueError(f"Fișier prea mare: max {frag.MAX_FILE_SIZE} bytes")

        content_b64 = base64.b64encode(file_bytes).decode("utf-8")

        if len(content_b64) > frag.MAX_PAYLOAD_SIZE:
            handle_fragmented_download(file_path, content_b64, file_size, sock, client_addr, msg_id, msg_type)
        else:
            handle_normal_download(file_path, file_size, content_b64, sock, client_addr, msg_id, msg_type)

    except Exception as e:
        print(f"[!] Eroare download: {e}")
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])


def handle_normal_download(file_path, file_size, content_b64, sock, client_addr, msg_id, msg_type):
    if msg_type == 0:
        resp = json.dumps({
            "name": os.path.basename(file_path),
            "size": file_size,
            "content": content_b64
        }).encode("utf-8")
        build_response(sock, client_addr, msg_id, resp, COAP["CONTENT"])

    print(f"[+] Download: {file_path} ({file_size} bytes)")


def handle_fragmented_download(file_path, content_b64, file_size, sock, client_addr, msg_id, msg_type):
    total = frag.fragmente_necesare(content_b64)

    print(f"[+] Download fragmentat: {file_size} bytes → {total} fragmente")

    # Info inițial
    if msg_type == 0:
        info = json.dumps({
            "name": os.path.basename(file_path),
            "size": file_size,
            "fragmented": True,
            "total_fragments": total
        }).encode("utf-8")
        build_response(sock, client_addr, msg_id, info, COAP["CONTENT"])

    # Trimite fragmente
    frag.handle_fragmented(file_path, content_b64, sock, client_addr, msg_id)


# ============================================================================
# LISTARE
# ============================================================================

def listare_director(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Payload required"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["BAD_REQUEST"])
        return

    dir_path = payload.get("path", "")

    if not dir_path:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Missing path"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["UNPROCESSABLE"])
        return

    if dir_path in ["storage/", "storage"]:
        dir_path = STORAGE
    elif not valideaza_director(dir_path):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Path invalid"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(dir_path):
            if msg_type == 0:
                error = json.dumps({"status": "error", "message": "Directory not found"}).encode("utf-8")
                build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
            return

        if not os.path.isdir(dir_path):
            if msg_type == 0:
                error = json.dumps({"status": "error", "message": "Not a directory"}).encode("utf-8")
                build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
            return

        items = []
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            items.append(item + "/" if os.path.isdir(item_path) else item)

        resp = json.dumps({
            "name": os.path.basename(dir_path.rstrip("/")),
            "type": "directory",
            "items": items
        }).encode("utf-8")

        if msg_type == 0:
            build_response(sock, client_addr, msg_id, resp, COAP["CONTENT"])
        elif msg_type == 1:
            build_response(sock, client_addr, msg_id, resp, COAP["CONTENT"], 0)

        print(f"[+] Listare: {dir_path}")

    except Exception as e:
        print(f"[!] Eroare listare: {e}")
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])


# ============================================================================
# DELETE
# ============================================================================

def delete_request(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Payload required"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")

    if not file_path:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Missing path"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Path invalid"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(file_path):
            if msg_type == 0:
                error = json.dumps({"status": "error", "message": "Path not found"}).encode("utf-8")
                build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
            return

        if os.path.isfile(file_path):
            os.remove(file_path)
            print(f"[+] Șters fișier: {file_path}")
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
            print(f"[+] Șters director: {file_path}")

        if msg_type == 0:
            resp = json.dumps({"status": "deleted", "path": file_path}).encode("utf-8")
            build_response(sock, client_addr, msg_id, resp, COAP["DELETED"])

    except Exception as e:
        print(f"[!] Eroare delete: {e}")
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])


# ============================================================================
# MOVE
# ============================================================================

def move_request(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Payload required"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["BAD_REQUEST"])
        return

    source = payload.get("source")
    destination = payload.get("destination")

    if not source or not destination:
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Missing fields"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(source) or not valideaza_director(destination):
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": "Path invalid"}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(source):
            if msg_type == 0:
                error = json.dumps({"status": "error", "message": "Source not found"}).encode("utf-8")
                build_response(sock, client_addr, msg_id, error, COAP["NOT_FOUND"])
            return

        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)

        if msg_type == 0:
            resp = json.dumps({"status": "moved", "from": source, "to": destination}).encode("utf-8")
            build_response(sock, client_addr, msg_id, resp, COAP["CHANGED"])

        print(f"[+] Mutat: {source} → {destination}")

    except Exception as e:
        print(f"[!] Eroare move: {e}")
        if msg_type == 0:
            error = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            build_response(sock, client_addr, msg_id, error, COAP["SERVER_ERROR"])