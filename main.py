import socket
import threading
import time

import Pachet

packet = b'\x40\x01\x04\xD2' + b'\xFF' + \
    b'{"action":"discover","device":"client1"}'

#client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

Server_Ip = socket.gethostbyname(socket.gethostname()) #ia ip-ul hostului, in cazul dat laptopul personal
Server_Port = 5683 # portul predestinat unencrypted CoAP

Socket_Server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # setez la transmitere prin UDP
Socket_Server.bind(("0.0.0.0", Server_Port)) # Atasez portul de coap pentru server

#client.sendto(packet,("255.255.255.255", Server_Port))



if __name__ == '__main__':
    print(Server_Ip)

    while True:
        data,addr_client = Socket_Server.recvfrom(1024)
        header, payload = Pachet.parse_packet(data)
        print("header:",header)
        print("payload:",payload)
        #Pachet.build_and_send_acknowledgement(Socket_Server,addr_client,1,"OK")
        Pachet.handle_request(header,payload,addr_client,Socket_Server)
        time.sleep(1)
        #datac,addr_server = client.recvfrom(1024)
        #header1,payload1 = Pachet.parse_packet(datac)
        #print("header1:",header1)
        #print("payload1:",payload1)
        #Pachet.handle_request(header,payload,addr_client,Socket_Server)
        time.sleep(1)

