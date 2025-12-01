import socket
import time

import Pachet
import fragmentare_pachet as f
import base64
import json

TEXT = "Hello guyes" * 6000

content_b64 = base64.b64encode(TEXT.encode("utf-8")).decode("utf-8")

fragments = f.split_payload(content_b64, "storage/big.txt")

# packet = b'\x40\x02\x04\xD2' + b'\xFF' + \
#     json.dumps({
#         "path": "storage/test/hello.txt",
#         "content": content_b64
#     }).encode("utf-8")

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

Server_Ip = socket.gethostbyname(socket.gethostname()) #ia ip-ul hostului, in cazul dat laptopul personal
Server_Port = 5683 # portul predestinat unencrypted CoAP

Socket_Server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # setez la transmitere prin UDP
Socket_Server.bind(("0.0.0.0", Server_Port)) # Atasez portul de coap pentru server

#client.sendto(packet,("127.0.0.1", Server_Port))
for i, frag in enumerate(fragments):
    packet = f.build_fragment_pachet(2, frag, 5000 + i)
    client.sendto(packet, ("127.0.0.1", 5683))
    print(f"Fragment {i+1}/{len(fragments)} trimis")


if __name__ == '__main__':
    print(Server_Ip)

    while True:
        data,addr_client = Socket_Server.recvfrom(65535)
        header, payload = Pachet.parse_packet(data)
        print("header:",header)
        print("payload:",payload)
        #Pachet.build_and_send_acknowledgement(Socket_Server,addr_client,1,"OK")
        Pachet.handle_request(header, payload, addr_client, Socket_Server)
        time.sleep(1)
        #datac,addr_server = client.recvfrom(1024)
        #header1,payload1 = Pachet.parse_packet(datac)
        #print("header1:",header1)
        #print("payload1:",payload1)
        #Pachet.handle_request(header,payload,addr_client,Socket_Server)
        time.sleep(1)

