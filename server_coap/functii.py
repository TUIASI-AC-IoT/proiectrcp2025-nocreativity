import os
import shutil
import struct
import json
import base64
import fragmentare_pachet as frag


MAX_SIZE_PACHET = 14000
HEADER_SIZE = 4
PAYLOAD_MARKER_SIZE = 1
FRAGMENT_OVERHEAD = 200 #spatiu pentru metadata JSON

RAW_MAX = 14000 - 4 - 1 - 200
MAX_PAYLOAD_SIZE = RAW_MAX - (RAW_MAX % 4)

PAYLOAD_MARKER = 0xFF

STORAGE = "storage" # directorul de baza pentru stocare

#coduri de raspuns si eroare
COAP = {
    "CREATED": 65,         # 2.01
    "DELETED": 66,         # 2.02
    "VALID":   67,         # 2.03
    "CHANGED": 68,         # 2.04
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
    returneaza true daca path-ul se incepe cu storage/ si flase daca invers
    """
    if not file_path:
        return False

    path = file_path.split("/")
    return path[0] == STORAGE



def build_and_send_acknowledgement(sock, client_addr, msg_id, new_payload ,new_code = 69):
    """
    Trimite un mesaj CoAP de tip ACK (type = 2) către clientul care a trimis un CON.
    
    sock        -> socket-ul UDP deja deschis
    client_addr -> (ip, port) al clientului
    msg_id      -> Message ID al cererii originale (trebuie să fie același!)
    info        -> mesaj text/JSON trimis în payload (opțional)
    """

    # Header CoAP 
    version = 1
    msg_type = 2       # ACK
    tkl = 0
    code = new_code       
    first_byte = (version << 6) | (msg_type << 4) | tkl

    header = struct.pack("!BBH", first_byte, code, msg_id)

    # Payload JSON 
    payload = new_payload

    # Pachet final
    packet = header + bytes([PAYLOAD_MARKER]) + payload

    # Trimitem pachetul 
    sock.sendto(packet, client_addr)
    print(f"[<] Trimis ACK către {client_addr} (msg_id={msg_id}, code={code})")



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
            build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["BAD_REQUEST"])
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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Path invalid"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    if frag.is_fragment_upload(payload):
        handle_fragmented_upload(payload, msg_type, msg_id, client_addr, sock)
    else:
        handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock)


def handle_normal_upload(file_path, content, msg_type, msg_id, client_addr, sock):
    try:
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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["CREATED"])

        print(f"Fisier creat: {file_path} ({file_size} bytes)")

    except Exception as e:
        print(f"Error upload: {e}")
        if  msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload gresit"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])

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
        build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["CONTENT"])

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
                build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["CREATED"])

        except Exception as e:
            print(f"Error assamblare fragmente: {e}")
            frag.assembler.clear_path(file_path)
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": f"Assembly failed: {str(e)}"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


"""
    DOWNLOAD REQUEST
"""


def download_request(payload, msg_type, msg_id, client_addr, sock, packet_queue=None):
    if not payload:
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Payload required"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")
    if not file_path or not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Invalid or missing path"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["NOT_FOUND"])
        return

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "File not found"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["NOT_FOUND"])
        return

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        file_size = len(file_bytes)
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        encoded_size = len(content_b64)

        # Determin dacă trebuie fragmentare
        if encoded_size > MAX_PAYLOAD_SIZE:
            # Caz fragmentat - necesită packet_queue pentru a primi ACK-urile
            if packet_queue is None:
                raise Exception("packet_queue required for fragmented download")

            handle_fragmented_download(
                file_path, content_b64, file_size, sock, client_addr, msg_id, msg_type, packet_queue
            )
        else:
            handle_normal_download(
                file_path, file_size, content_b64, sock, client_addr, msg_id, msg_type
            )

    except Exception as e:
        print(f"[!] Eroare la download: {e}")
        if msg_type == 0:
            error_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_send_acknowledgement(sock, client_addr, msg_id, error_payload, COAP["SERVER_ERROR"])


def handle_normal_download(file_path, file_size, content_b64, sock, client_addr, msg_id, msg_type):
    response_payload = json.dumps({
        "name": os.path.basename(file_path),
        "size": file_size,
        "content": content_b64
    }).encode("utf-8")

    if msg_type == 0:
        build_and_send_acknowledgement(sock, client_addr, msg_id, response_payload, COAP["CONTENT"])

    print(f"[+] Fișier descărcat normal: {file_path} ({file_size} bytes)")


def handle_fragmented_download(file_path, content_b64, file_size, sock, client_addr, msg_id_base, msg_type,packet_queue):
    total_fragments = frag.fragmente_necesare(content_b64)

    print(f"[+] Fișier mare ({file_size} bytes → {len(content_b64)} b64). Fragmentare în {total_fragments} părți.")

    # Trimit mai întâi un răspuns informativ pentru client
    if msg_type == 0:
        info_payload = json.dumps({
            "name": os.path.basename(file_path),
            "size": file_size,
            "fragmented": True,
            "total_fragments": total_fragments
        }).encode("utf-8")
        build_and_send_acknowledgement(sock, client_addr, msg_id_base, info_payload, COAP["CONTENT"])


    success = frag.handle_fragmented(
        file_path, content_b64, sock, client_addr, msg_id_base, packet_queue
    )

    if not success and msg_type == 0:
        error_payload = json.dumps({
            "status": "error",
            "message": "Fragmented transfer failed"
        }).encode("utf-8")
        build_and_send_acknowledgement(sock, client_addr, msg_id_base, error_payload, COAP["SERVER_ERROR"])


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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["BAD_REQUEST"])
        return

    dir_path = payload.get("path" , "")

    if not dir_path:
        print(f"Trimit pachet eroare: lipseste path")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing fields"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if dir_path == "storage/" or dir_path == "storage":
        dir_path = STORAGE
    elif not valideaza_director(dir_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Path invalid"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(dir_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Directory not found"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        if not os.path.isdir(dir_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Path is not a directory"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        items = []
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                items.append(item + "/")
            else:
                items.append(item)

        ack_payload = json.dumps({
            "name": os.path.basename(dir_path.rstrip("/")),
            "type": "directory",
            "items": items
        }).encode("utf-8")

        if msg_type == 0:
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["CONTENT"])

        print(f"Director listat: {dir_path}")

    except Exception as e:
        print(f"Error listare: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["BAD_REQUEST"])
        return

    file_path = payload.get("path")

    if not file_path:
        print(f"Trimit pachet eroare: lipseste path")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Missing path"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(file_path):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Path invalid"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(file_path):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Path not found"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["DELETED"])

    except Exception as e:
        print(f"Error delete: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])


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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["BAD_REQUEST"])
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
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])
        return

    if not valideaza_director(source) or not valideaza_director(destination):
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": "Path invalid"
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
        return

    try:
        if not os.path.exists(source):
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Source not found"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])
            return

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        shutil.move(source, destination)

        ack_payload = json.dumps({
            "status": "moved",
            "from": source,
            "to": destination
        }).encode("utf-8")

        if msg_type == 0:
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["CHANGED"])

        print(f"Fisier mutat: {source} -> {destination}")

    except Exception as e:
        print(f"Error move: {e}")
        if msg_type == 0:
            ack_payload = json.dumps({
                "status": "error",
                "message": str(e)
            }).encode("utf-8")
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["SERVER_ERROR"])
