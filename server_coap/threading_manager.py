import threading
import queue

# Coadă pentru răspunsuri (FIFO)
response_queue = queue.Queue()

#Flag pentru controlul workerului
_running = False

#referinta la worker
_worker_thread = None


#functia pentru a evita blocarea la sendto(in caz ca e facut in main)
def response_worker():
    #Thread simplu - trimite răspunsuri din coadă, se ocupa doar de trimitere
    global _running
    while _running:
        try:
            #extragem un item din coada
            #arunca queue empty daca nu gaseste nimic
            item = response_queue.get(timeout=1.0)

            #extragem informatiile din itme
            sock = item['sock']
            client_addr = item['client_addr']
            packet = item['packet']

            #trimitem pachetul la client
            sock.sendto(packet, client_addr)
            print(f"Răspuns trimis către client {client_addr}")

            #incheiem operatia
            response_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Eroare trimitere răspuns: {e}")

#porneste threadul pentru raspunsuri
def start_workers():
    global _running, _worker_thread
    if not _running:
        #setarea flagului global
        _running = True
        #setez functia de executie, deamon true- thread pe fundal
        _worker_thread = threading.Thread(target=response_worker, daemon=True)
        #pornim threadul
        _worker_thread.start()
        print("ResponseWorker pornit")

#opreste threadul pentru raspunsuri
def stop_workers():
    global _running
    _running = False
    if _worker_thread:
        #se asteapta pana threadul se termina
        _worker_thread.join(timeout=2.0)
    print("ResponseWorker oprit")

#punem in coada un raspuns
def submit_response(sock, client_addr, packet):
    response_queue.put({
        'sock': sock,
        'client_addr': client_addr,
        'packet': packet
    })

#creeaza un thread nou pentru procesare, se apeleaza din pachet.py de fiecare
#data cand este primit un pachet
def handle_request_in_thread(handler_func, header, payload, client_addr, sock):
    #Creează thread nou pentru fiecare cerere

    def worker():
        try:
            #are loc procesarea efectiva
            handler_func(header, payload, client_addr, sock)
        except Exception as e:
            print(f"Eroare procesare cerere: {e}")
            import traceback
            traceback.print_exc()
    #se adauga worker ca target
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()