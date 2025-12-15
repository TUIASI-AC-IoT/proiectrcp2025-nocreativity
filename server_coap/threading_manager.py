import threading
import queue
import time


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
                task_func, args, callback = self.task_queue.get(timeout=1.0)

                try:
                    result = task_func(*args)

                    if callback:
                        callback(result, None)

                except Exception as e:
                    if callback:
                        callback(None, e)

                finally:
                    self.task_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[!] Eroare critică în IOWorker: {e}")

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
                response_data = self.response_queue.get(timeout=1.0)

                try:
                    sock = response_data['sock']
                    client_addr = response_data['client_addr']
                    packet = response_data['packet']

                    sock.sendto(packet, client_addr)
                    print(f"[<] Răspuns trimis către {client_addr}")

                except Exception as e:
                    print(f"[!] Eroare trimitere răspuns: {e}")

                finally:
                    self.response_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[!] Eroare critică în ResponseWorker: {e}")

    def stop(self):
        """Oprește worker-ul"""
        self.running = False


class RequestProcessor(threading.Thread):
    """Thread dedicat pentru procesarea unei singure cereri"""

    def __init__(self, task, io_queue, response_queue, handler_func, extra_args=None):
        super().__init__(daemon=True, name=f"RequestProcessor-{task.client_addr}")
        self.task = task
        self.io_queue = io_queue
        self.response_queue = response_queue
        self.handler_func = handler_func
        self.extra_args = extra_args or ()

    def run(self):
        try:
            print(f"\n[*] Thread procesare pentru {self.task.client_addr}")
            print(f"    Code: {self.task.header.get('code')}")
            print(f"    Message ID: {self.task.header.get('message_id')}")

            if self.extra_args:
                self.handler_func(
                    self.task.header,
                    self.task.payload,
                    self.task.client_addr,
                    self.task.sock,
                    self.io_queue,
                    self.response_queue,
                    *self.extra_args
                )
            else:
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

    def __init__(self, num_io_workers=1, num_response_workers=1):
        self.io_queue = queue.Queue()
        self.response_queue = queue.Queue()

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
        self.last_cleanup = time.time()
        self.cleanup_interval = 10.0  # Curățare la fiecare 10 secunde

    def submit_request(self, header, payload, client_addr, sock, handler_func, extra_args=None):
        """Submitează o cerere pentru procesare"""
        task = RequestTask(header, payload, client_addr, sock)
        processor = RequestProcessor(
            task,
            self.io_queue,
            self.response_queue,
            handler_func,
            extra_args
        )

        with self.lock:
            self.active_processors.append(processor)

        processor.start()

        # Curățare periodică, nu la fiecare cerere
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_processors()
            self.last_cleanup = current_time

    def _cleanup_processors(self):
        """Curăță thread-urile de procesare terminate - OPTIMIZAT"""
        with self.lock:
            before = len(self.active_processors)
            self.active_processors = [p for p in self.active_processors if p.is_alive()]
            after = len(self.active_processors)

            if before != after:
                print(f"[*] Cleanup: {before - after} thread-uri terminate curățate")

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

        # Curățare finală
        self._cleanup_processors()

        # Oprim worker-ii
        for worker in self.io_workers:
            worker.stop()

        for worker in self.response_workers:
            worker.stop()

        # Așteptăm să termine task-urile curente (cu timeout)
        print("[*] Așteptăm finalizarea task-urilor I/O...")
        try:
            self.io_queue.join()
        except:
            pass

        print("[*] Așteptăm finalizarea răspunsurilor...")
        try:
            self.response_queue.join()
        except:
            pass

        # Așteptăm să se termine thread-urile
        for worker in self.io_workers:
            worker.join(timeout=2.0)
            if worker.is_alive():
                print(f"[!] {worker.name} nu s-a oprit complet")

        for worker in self.response_workers:
            worker.join(timeout=2.0)
            if worker.is_alive():
                print(f"[!] {worker.name} nu s-a oprit complet")

        print("[+] ThreadingManager oprit")


# Instanță globală
_manager = None
_manager_lock = threading.Lock()


def get_manager():
    """Returnează instanța globală a ThreadingManager (thread-safe)"""
    global _manager

    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = ThreadingManager()

    return _manager


def shutdown_manager():
    """Oprește manager-ul global"""
    global _manager

    if _manager:
        with _manager_lock:
            if _manager:
                _manager.shutdown()
                _manager = None