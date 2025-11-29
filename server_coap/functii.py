import os
import struct
import json
import base64
PAYLOAD_MARKER = 0xFF

#coduri de raspuns si eroare
COAP = {
    "CREATED": 65,         # 2.01
    "CONTENT": 69,         # 2.05
    "BAD_REQUEST": 128,    # 4.00  LIPSA PAYLOAD-ULUI ACOLO UNDE ESTE NECESAR
    "NOT_FOUND": 132,      # 4.04  PATH-UL FURNIZAT DE UTILIZATOR NU CORESPUNDE CERINTEI APLICATIEI 
    "UNPROCESSABLE": 150,  # 4.22  LIPSA UNUI CAMP NECESAR DIN PAYLOAD
    "SERVER_ERROR": 160    # 5.00
}

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



    
def upload_request(payload,msg_type,msg_id,client_addr, sock):
    if(payload):
        file_path = payload.get("path")
        content = payload.get("content")

        if not file_path or content is None:
            print( "Trimit pachet eroare: payload incomplet")
            if msg_type==0:
                ack_payload=json.dumps({ "status": "error","message": "Missing fields"}).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["UNPROCESSABLE"])  # PARTI NECESARE DIN PAYLOAD LIPSESC 
            return

        parts = file_path.split("/")
        # folderul in care este incarcat orice trimite clientul este "storage"
        if parts[0] != "storage":
            if msg_type==0:
                ack_payload=json.dumps({ "status": "error","message": "Unable to execute"}).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["NOT_FOUND"])  # UNABLE TO EXECUTE PT CA PATH-UL DAT DE UTILIZATOR NU E CONFORM CERINTEI APLICATIEI
            return
        try:
            file_bytes = base64.b64decode(content) # citim fisierul primit sub forma de bytes 
        except Exception:
            print("Content nu este base64 valid")
            if msg_type == 0:
                ack_payload = json.dumps({
                    "status": "error",
                    "message": "Invalid binary payload"
                }).encode("utf-8")
                build_and_send_acknowledgement(sock, client_addr, msg_id, ack_payload, COAP["UNPROCESSABLE"])
            return

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # scriu in fisier file_bytes 
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        ack_payload=json.dumps({ "status": "created","path": file_path,"size": os.path.getsize(file_path)}).encode("utf-8")
        if msg_type==0:
            build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["CREATED"])
        print(f"Fișierul a fost creat în {file_path}")
    else:
        print("Trimit pachet eroare: la acest tip de request e necesar un payload!")
        if msg_type==0:
                ack_payload=json.dumps({ "status": "error","message": "Payload required"}).encode("utf-8")
                build_and_send_acknowledgement(sock,client_addr,msg_id,ack_payload,COAP["BAD_REQUEST"])  # UN TIP DE EROARE PENTRU LIPSTA PAYLOAD-ULUI ACOLO UNDE VA FI NECESAR 