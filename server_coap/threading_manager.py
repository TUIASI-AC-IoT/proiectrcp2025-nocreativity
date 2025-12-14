"""
Manager pentru threading conform arhitecturii din documentație

ARHITECTURĂ:
Main Thread → Thread Procesare Cereri → Thread I/O Fișiere + Thread Răspuns

Main Thread:
- Ascultă socket UDP în loop infinit
- Pentru fiecare pachet primit, creează Thread de Procesare

Thread Procesare Cereri:
- Decodifică pachetul CoAP
- Identifică metoda (GET, POST, DELETE, etc.)
- Creează Thread pentru operații I/O (dacă e necesar)
- Creează Thread pentru răspuns

Thread I/O Fișiere:
- Execută operații de citire/scriere/ștergere fișiere
- Nu blochează thread-ul principal
- Returnează rezultatul către Thread Răspuns

Thread Răspuns:
- Așteaptă rezultatul de la Thread I/O
- Construiește pachetul de răspuns
- Trimite ACK/Response către client
"""

import threading
import queue
import time
from typing import Callable, Any, Dict


class RequestTask:
    """Reprezintă o cerere de procesat"""

    def __init__(self, header, payload, client_addr, sock):
        self.header = header
        self.payload = payload
        self.client_addr = client_addr
        self.sock = sock
        self.result = None
        self.error = None
        self.result_ready = threading.Event()

    def set_result(self, result):
        """Setează rezultatul operației"""
        self.result = result
        self.result_ready.set()

    def set_error(self, error):
        """Setează o eroare"""
        self.error = error
        self.result_ready.set()

    def wait_for_result(self, timeout=None):
        """Așteaptă rezultatul"""
        return self.result_ready.wait(timeout)


class IOWorker(threading.Thread):
    """
    Thread Worker pentru operații I/O pe fișiere
    Procesează operații fără a bloca thread-ul principal
    """

    def __init__(self, task_queue, name="IOWorker"):
        super().__init__(daemon=True, name=name)
        self.task_queue = task_queue
        self.running = True

    def run(self):
        """Loop principal pentru procesare operații I/O"""
        while self.running:
            try:
                # Așteptăm un task (cu timeout pentru a verifica self.running)
                task_func, args, callback = self.task_queue.get(timeout=1.0)

                try:
                    # Executăm operația I/O
                    result = task_func(*args)

                    # Apelăm callback-ul cu rezultatul
                    if callback:
                        callback(result, None)

                except Exception as e:
                    # Raportăm eroarea
                    if callback:
                        callback(None, e)

                finally:
                    self.task_queue.task_done()

            except queue.Empty:
                continue

    def stop(self):
        """Oprește worker-ul"""
        self.running = False


class ResponseWorker(threading.Thread):
    """
    Thread Worker pentru trimiterea răspunsurilor
    Construiește și trimite pachete CoAP către clienți
    """

    def __init__(self, response_queue, name="ResponseWorker"):
        super().__init__(daemon=True, name=name)
        self.response_queue = response_queue
        self.running = True

    def run(self):
        """Loop principal pentru trimitere răspunsuri"""
        while self.running:
            try:
                # Așteptăm un răspuns de trimis
                response_data = self.response_queue.get(timeout=1.0)

                try:
                    sock = response_data['sock']
                    client_addr = response_data['client_addr']
                    packet = response_data['packet']

                    # Trimitem pachetul
                    sock.sendto(packet, client_addr)

                    print(f"[<] DE LA WORKER Răspuns trimis către {client_addr}")

                except Exception as e:
                    print(f"[!] Eroare trimitere răspuns: {e}")

                finally:
                    self.response_queue.task_done()

            except queue.Empty:
                continue

    def stop(self):
        """Oprește worker-ul"""
        self.running = False


class RequestProcessor(threading.Thread):
    """
    Thread pentru procesarea unei cereri individuale
    Conform schemei: Decodifică → Identifică metoda → Creează thread-uri I/O și Răspuns
    """

    def __init__(self, task, io_queue, response_queue, handler_func):
        super().__init__(daemon=True, name=f"RequestProcessor-{task.client_addr}")
        self.task = task
        self.io_queue = io_queue
        self.response_queue = response_queue
        self.handler_func = handler_func

    def run(self):
        """Procesează cererea"""
        try:
            print(f"\n[*] Thread procesare pentru {self.task.client_addr}")
            print(f"    Code: {self.task.header.get('code')}")
            print(f"    Message ID: {self.task.header.get('message_id')}")

            # Apelăm handler-ul care va folosi io_queue pentru operații I/O
            # și response_queue pentru a trimite răspunsuri
            self.handler_func(
                self.task.header,
                self.task.payload,
                self.task.client_addr,
                self.task.sock,
                self.io_queue,
                self.response_queue
            )

        except Exception as e:
            print(f"[!] Eroare în RequestProcessor: {e}")
            import traceback
            traceback.print_exc()


class ThreadingManager:
    """
    Manager central pentru threading conform arhitecturii din documentație

    Creează și gestionează:
    - Pool de worker threads pentru I/O
    - Pool de worker threads pentru răspunsuri
    - Thread-uri individuale pentru fiecare cerere
    """

    def __init__(self, num_io_workers=4, num_response_workers=2):
        # Cozi pentru comunicare între thread-uri
        self.io_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Pool-uri de worker threads
        self.io_workers = []
        self.response_workers = []

        # Creăm worker-ii pentru I/O
        for i in range(num_io_workers):
            worker = IOWorker(self.io_queue, name=f"IOWorker-{i}")
            worker.start()
            self.io_workers.append(worker)
            print(f"[+] Pornit IOWorker-{i}")

        # Creăm worker-ii pentru răspunsuri
        for i in range(num_response_workers):
            worker = ResponseWorker(self.response_queue, name=f"ResponseWorker-{i}")
            worker.start()
            self.response_workers.append(worker)
            print(f"[+] Pornit ResponseWorker-{i}")

        # Tracking pentru thread-uri active
        self.active_processors = []
        self.lock = threading.Lock()

    def submit_request(self, header, payload, client_addr, sock, handler_func):
        """
        Submitează o cerere nouă pentru procesare

        Creează un Thread de Procesare Cereri conform schemei din documentație

        Args:
            header: Header-ul pachetului CoAP
            payload: Payload-ul JSON
            client_addr: Adresa clientului
            sock: Socket-ul serverului
            handler_func: Funcția care procesează cererea
        """
        # Creăm task-ul
        task = RequestTask(header, payload, client_addr, sock)

        # Creăm Thread de Procesare pentru această cerere
        processor = RequestProcessor(
            task,
            self.io_queue,
            self.response_queue,
            handler_func
        )

        # Salvăm referința
        with self.lock:
            self.active_processors.append(processor)

        # Pornim thread-ul
        processor.start()

        # Curățăm thread-urile terminate (non-blocking)
        self._cleanup_processors()

    def _cleanup_processors(self):
        """Curăță thread-urile de procesare terminate"""
        with self.lock:
            self.active_processors = [p for p in self.active_processors if p.is_alive()]

    def submit_io_operation(self, operation_func, args, callback):
        """
        Submitează o operație I/O pentru execuție în thread pool

        Args:
            operation_func: Funcția de executat (ex: read_file, write_file)
            args: Argumentele pentru funcție
            callback: Funcție apelată cu (result, error) când operația se termină
        """
        self.io_queue.put((operation_func, args, callback))

    def submit_response(self, sock, client_addr, packet):
        """
        Submitează un răspuns pentru trimitere

        Args:
            sock: Socket-ul serverului
            client_addr: Adresa clientului
            packet: Pachetul de trimis (bytes)
        """
        self.response_queue.put({
            'sock': sock,
            'client_addr': client_addr,
            'packet': packet
        })

    def get_statistics(self):
        """Returnează statistici despre thread-uri"""
        with self.lock:
            return {
                'io_workers': len(self.io_workers),
                'response_workers': len(self.response_workers),
                'active_processors': len(self.active_processors),
                'io_queue_size': self.io_queue.qsize(),
                'response_queue_size': self.response_queue.qsize()
            }

    def shutdown(self):
        """Oprește toate thread-urile worker"""
        print("\n[*] Oprire ThreadingManager...")

        # Oprim worker-ii
        for worker in self.io_workers:
            worker.stop()

        for worker in self.response_workers:
            worker.stop()

        # Așteptăm să termine task-urile curente
        self.io_queue.join()
        self.response_queue.join()

        # Așteptăm să se termine thread-urile
        for worker in self.io_workers:
            worker.join(timeout=2.0)

        for worker in self.response_workers:
            worker.join(timeout=2.0)

        print("[+] ThreadingManager oprit")


# Instanță globală
_manager = None


def get_manager():
    """Returnează instanța globală a ThreadingManager"""
    global _manager
    if _manager is None:
        _manager = ThreadingManager()
    return _manager


def shutdown_manager():
    """Oprește manager-ul global"""
    global _manager
    if _manager:
        _manager.shutdown()
        _manager = None