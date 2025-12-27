import os
import shutil
import struct
import json
import base64
import fragmentare_pachet as frag
from threading_manager import get_manager

PAYLOAD_MARKER = 0xFF

STORAGE = "storage" # directorul de baza pentru stocare

#coduri de raspuns si eroare
COAP = {
    "CREATED": 65,         # 2.01
    "DELETED": 66,         # 2.02
    "CONTENT": 69,         # 2.05
    "BAD_REQUEST": 128,    # 4.00  LIPSA PAYLOAD-ULUI ACOLO UNDE ESTE NECESAR
    "NOT_FOUND": 132,      # 4.04  PATH-UL FURNIZAT DE UTILIZATOR NU CORESPUNDE CERINTEI APLICATIEI 
    "UNPROCESSABLE": 150,  # 4.22  LIPSA UNUI CAMP NECESAR DIN PAYLOAD
    "SERVER_ERROR": 160    # 5.00
}

def exista_storage():
    if not os.path.exists(STORAGE):
        os.makedirs(STORAGE)

def valideaza_director(file_path):
    """
    returneaza true daca path-ul se incepe cu storage/ si false daca invers
    """
    if not file_path:
        return False

    path = file_path.split("/")
    return path[0] == STORAGE

def build_and_submit_response(sock, client_addr, msg_id, new_payload, new_code=69, new_msg_type=2):
    """
    Construiește un mesaj CoAP de tip specificat sau ACK (type = 2) și îl trimite 
    către ResponseWorker (prin ThreadingManager) pentru trimitere.
    """
    
    # Header CoAP - Construcția rămâne la fel
    version = 1
    msg_type = new_msg_type       # ACK
    tkl = 0
    code = new_code    
    first_byte = (version << 6) | (msg_type << 4) | tkl

    header = struct.pack("!BBH", first_byte, code, msg_id)

    # Pachet final
    packet = header + bytes([PAYLOAD_MARKER]) + new_payload

    # Prin ThreadingManager, punem pachetul ack in response_queue (ResponseWorker)
    get_manager().submit_response(sock, client_addr, packet)







"""
    UPLOAD REQUEST
"""
def upload_request(payload,msg_type,msg_id,client_addr, sock):

    if not payload:
        print("Trimit pachet eroare: necesar un payload!")
        if msg_type == 0:  # CON
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")
    content = payload.get("content")

    if not file_path or content is None:
        print("Trimit pachet eroare: payload incomplet")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload gresit"
            }).encode("utf-8")
            print("!!!!!!!file path:")
            print(file_path)
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    if frag.is_fragment_upload(payload):
        handle_fragmented_upload(payload, msg_type, msg_id, client_addr, sock)
    else:
        handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock)


def handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock):
    try:
        #decodare base64
        file_bytes = base64.b64decode(content)

        #creare director parinte
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as file:
            file.write(file_bytes)
            """urmatoarele 2 linii de cod sunt necesare pentru adaugarea fisierului cand serverul e pornit"""
            file.flush()
            os.fsync(file.fileno())

        file_size = os.path.getsize(file_path)

        ack_payload = json.dumps({
            "status": "created",
            "path": file_path,
            "size": file_size
        }).encode("utf-8")

        if msg_type == 0:
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["CREATED"])

        print(f"Fisier creat: {file_path} ({file_size} bytes)")

    except Exception as e:
        print(f"Error upload: {e}")
        if  msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload gresit"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])

def handle_fragmented_upload(payload, msg_type, msg_id, client_addr, sock):
    file_path = payload.get("path")
    content = payload.get("content")

    index, total, size = frag.get_fragment_info(payload)

    print(f"Fragment primit: {index + 1}/{total} pentru {file_path}")

    is_complete, assembled_content = frag.assembler.assemble_content(
        file_path,index,total,content
    )

    if msg_type == 0:
        ack_payload = json.dumps({
            "status": "fragment_received",
            "fragment": {
                "index": index,
                "total": total
            },
            "progress": frag.assembler.get_progress(file_path)
        }).encode("utf-8")
        build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["CONTENT"])

    if is_complete:
        try:
            file_bytes = base64.b64decode(assembled_content)

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as file:
                file.write(file_bytes)
                """urmatoarele 2 linii de cod sunt necesare pentru adaugarea fisierului cand serverul e pornit"""
                file.flush()
                os.fsync(file.fileno())

            file_size = os.path.getsize(file_path)

            print(f"Fisier complet asamblat: {file_path} ({file_size} bytes)")

            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "created",
                    "path": file_path,
                    "size": file_size,
                    "fragment": total
                }).encode("utf-8")

        except Exception as e:
            print(f"Error assamblare fragmente: {e}")
            frag.assembler.clear_path(file_path)
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": f"Assembly failed: {str(e)}"
                }).encode("utf-8")
                build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


"""
    DOWNLOAD REQUEST
"""


def download_request(payload, msg_type, msg_id, client_addr, sock):
    if not payload:
        print("Trimit pachet eroare: la acest tip de request e necesar un payload!")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")

    if not file_path:
        print("Trimit pachet eroare: lipsește path")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["UNPROCESSABLE"])
        return

    # Validare path
    if not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Unable to execute"
            }).encode("utf-8")
            build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["NOT_FOUND"])
        return

    try:
        # Verificare existență fișier
        if not os.path.exists(file_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "File not found"
                }).encode("utf-8")
                build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["NOT_FOUND"])
            return

        if not os.path.isfile(file_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Path is not a file"
                }).encode("utf-8")
                build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["NOT_FOUND"])
            return

        # Citire fișier
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Encodare base64
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        file_size = len(file_bytes)
        file_name = os.path.basename(file_path)

        # Verificăm dacă e nevoie de fragmentare
        fragments_needed = frag.fragmente_necesare(content_b64)

        if fragments_needed > 1:
            # Download fragmentat
            print(f"[+] Fișier mare detectat: {file_size} bytes, {fragments_needed} fragmente")

            # Trimitem un răspuns inițial cu informații despre fragmentare
            if msg_type == 0:
                info_payload = json.dumps({
                    "name": file_name,
                    "size": file_size,
                    "fragmented": True,
                    "total_fragments": fragments_needed
                }).encode("utf-8")
                build_and_submit_response(sock, client_addr, msg_id, info_payload, COAP["CONTENT"])

            # Trimitem fragmentele
            frag.handle_fragmented_download(file_path, content_b64, sock, client_addr, msg_id + 1)

            print(f"[+] Download fragmentat complet: {file_path}")
        else:
            # Download normal (un singur pachet)
            ack_payload = json.dumps({
                "name": file_name,
                "size": file_size,
                "content": content_b64
            }).encode("utf-8")
            if msg_type == 0:
                build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["CONTENT"])
            elif msg_type == 1:

                build_and_submit_response(sock,client_addr,msg_id, ack_payload, COAP["CONTENT"], 0)
            print(f"[+] Fișier descărcat: {file_path} ({file_size} bytes)")

    except Exception as e:
        print(f"[!] Eroare download: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_submit_response(sock, client_addr, msg_id, ack_payload, COAP["SERVER_ERROR"])

"""
    LISTARE DIRECTOR
"""
def listare_director(payload,msg_type,msg_id,client_addr, sock):
    if not payload:
        print("Trimit pachet eroare: necesar payload")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    dir_path = payload.get("path" , "")

    if not dir_path:
        print(f"Trimit pachet eroare: lipseste path")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    if dir_path == "storage/" or dir_path == "storage":
        dir_path = STORAGE
    elif not valideaza_director(dir_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Unable to execute"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(dir_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Directory not found"
                }).encode("utf-8")
                build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        if not os.path.isdir(dir_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Path is not a directory"
                }).encode("utf-8")
                build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        items = []
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isfile(item_path):
                items.append(item + "/")
            else:
                items.append(item)

        ack_payload = json.dumps({
            "name": os.path.basename(dir_path.rstrip("/")),
            "type": "directory",
            "items": items
        }).encode("utf-8")

        if msg_type == 0:
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["CONTENT"])
        elif msg_type == 1:
                build_and_submit_response(sock,client_addr,msg_id, ack_payload, COAP["CONTENT"], 0)
        print(f"Director listat: {dir_path}")

    except Exception as e:
        print(f"Error listare: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


"""
    DELETE REQUEST
"""
def delete_request(payload,msg_type,msg_id,client_addr,sock):
    if not payload:
        print("Trimit pachet eroare: necesar payload")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    file_path = payload.get("path")

    if not file_path:
        print(f"Trimit pachet eroare: lipseste path")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Unable to execute"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(file_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Path not found"
                }).encode("utf-8")
                build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        if os.path.isfile(file_path):
            os.remove(file_path)
            print(f"Fisier sters: {file_path}")
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
            print(f"Director sters: {file_path}")

        ack_payload = json.dumps({
            "status": "deleted",
            "path": file_path
        }).encode("utf-8")

        if msg_type == 0:
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["DELETED"])

    except Exception as e:
        print(f"Error delete: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


"""
    MOVE REQUEST
"""
def move_request(payload,msg_type,msg_id,client_addr,sock):
    if not payload:
        print("Trimit pachet eroare: necesar payload")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    source = payload.get("source")
    destination = payload.get("destination")

    if not source or not destination:
        print(f"Trimit pachet eroare: lipseste source and destination")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(source) or not valideaza_director(destination):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Unable to execute"
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(source):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Source not found"
                }).encode("utf-8")
                build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        shutil.move(source, destination)

        ack_payload = json.dumps({
            "status": "moved",
            "from": source,
            "to": destination
        }).encode("utf-8")

        if msg_type == 0:
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["MOVED"])

        print(f"Fisier mutat: {source} -> {destination}")

    except Exception as e:
        print(f"Error move: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_submit_response(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])
