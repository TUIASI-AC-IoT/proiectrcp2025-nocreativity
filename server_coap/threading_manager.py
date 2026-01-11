import threading
import queue

# Coadă pentru răspunsuri
response_queue = queue.Queue()
_running = False
_worker_thread = None


def response_worker():
    #Thread simplu - trimite răspunsuri din coadă
    global _running
    while _running:
        try:
            item = response_queue.get(timeout=1.0)

            sock = item['sock']
            client_addr = item['client_addr']
            packet = item['packet']

            sock.sendto(packet, client_addr)
            print(f"Răspuns trimis către client {client_addr}")

            response_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Eroare trimitere răspuns: {e}")


def start_workers():
    #Pornește thread-ul worker
    global _running, _worker_thread
    if not _running:
        _running = True
        _worker_thread = threading.Thread(target=response_worker, daemon=True)
        _worker_thread.start()
        print("ResponseWorker pornit")


def stop_workers():
    #Oprește thread-ul worker
    global _running
    _running = False
    if _worker_thread:
        _worker_thread.join(timeout=2.0)
    print("ResponseWorker oprit")


def submit_response(sock, client_addr, packet):
    #Pune un răspuns în coadă
    response_queue.put({
        'sock': sock,
        'client_addr': client_addr,
        'packet': packet
    })


def handle_request_in_thread(handler_func, header, payload, client_addr, sock):
    #Creează thread nou pentru fiecare cerere

    def worker():
        try:
            handler_func(header, payload, client_addr, sock)
        except Exception as e:
            print(f"Eroare procesare cerere: {e}")
            import traceback
            traceback.print_exc()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()