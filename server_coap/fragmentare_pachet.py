import json
import struct
import math
import time
import threading

MAX_SIZE_PACHET = 14000
HEADER_SIZE = 4
PAYLOAD_MARKER_SIZE = 1
FRAGMENT_OVERHEAD = 200

RAW_MAX = 14000 - 4 - 1 - 200
MAX_PAYLOAD_SIZE = RAW_MAX - (RAW_MAX % 4)
PAYLOAD_MARKER = 0xFF

# Limite protecție
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
FRAGMENT_TIMEOUT = 300  # in secunde


def fragmente_necesare(content_b64):
    if not content_b64:
        return 0
    if len(content_b64) <= MAX_PAYLOAD_SIZE:
        return 1
    return math.ceil(len(content_b64) / MAX_PAYLOAD_SIZE)


def split_payload(content_b64, path):
    #Împarte base64 pe fragmente
    if not isinstance(content_b64, str):
        raise ValueError("content_b64 trebuie string")

    if len(content_b64) > MAX_FILE_SIZE * 4 / 3:
        raise ValueError(f"Fișier prea mare: max {MAX_FILE_SIZE} bytes")

    chunk_size = MAX_PAYLOAD_SIZE

    if len(content_b64) <= chunk_size:
        return [{
            "path": path,
            "content": content_b64,
            "fragment": {"index": 0, "total": 1, "size": len(content_b64)}
        }]

    total = math.ceil(len(content_b64) / chunk_size)
    fragments = []

    for i in range(total):
        start = i * chunk_size
        end = min(start + chunk_size, len(content_b64))

        fragments.append({
            "path": path,
            "content": content_b64[start:end],
            "fragment": {"index": i, "total": total, "size": len(content_b64[start:end])}
        })

    return fragments


def build_fragment_pachet(code, fragment_payload, msg_id, msg_type=0):
    version = 1
    tkl = 0
    first_byte = (version << 6) | (msg_type << 4) | tkl
    header = struct.pack("!BBH", first_byte, code, msg_id)
    payload = json.dumps(fragment_payload).encode("utf-8")
    return header + bytes([PAYLOAD_MARKER]) + payload


def is_fragment_upload(payload):
    return isinstance(payload, dict) and "fragment" in payload


def get_fragment_info(payload):
    if not is_fragment_upload(payload):
        return None
    info = payload.get("fragment", {})
    return (info.get("index"), info.get("total"), info.get("size"))


class AsamblareFragment:
    def __init__(self):
        self.fragments = {}
        self.expected_total = {}
        self.timestamps = {}
        self.lock = threading.Lock()

        # Thread cleanup
        cleanup = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup.start()

    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            self._cleanup_old()

    def _cleanup_old(self):
        with self.lock:
            now = time.time()
            expired = [p for p, t in self.timestamps.items() if now - t > FRAGMENT_TIMEOUT]
            for path in expired:
                print(f"[CLEANUP] Șterg fragmente expirate: {path}")
                self.clear_path(path)

    def add_fragment(self, path, index, total, content):
        with self.lock:
            if path not in self.fragments:
                self.fragments[path] = {}
                self.expected_total[path] = total
                self.timestamps[path] = time.time()

            self.timestamps[path] = time.time()
            self.fragments[path][index] = content

            if len(self.fragments[path]) == total:
                assembled = []
                for i in range(total):
                    if i not in self.fragments[path]:
                        return (False, None)
                    assembled.append(self.fragments[path][i])

                result = "".join(assembled)

                del self.fragments[path]
                del self.expected_total[path]
                del self.timestamps[path]

                return (True, result)

            return (False, None)

    def get_progress(self, path):
        with self.lock:
            if path not in self.fragments:
                return None
            received = len(self.fragments[path])
            total = self.expected_total.get(path, 0)
            percentage = (received / total * 100) if total > 0 else 0
            return {"received": received, "total": total, "percentage": round(percentage, 2)}

    def clear_path(self, path):
        with self.lock:
            if path in self.fragments:
                del self.fragments[path]
            if path in self.expected_total:
                del self.expected_total[path]
            if path in self.timestamps:
                del self.timestamps[path]


assembler = AsamblareFragment()


def handle_fragmented(file_path, file_content_b64, sock, client_addr, msg_id_base):

    try:
        fragments = split_payload(file_content_b64, file_path)
    except ValueError as e:
        print(f"Eroare validare: {e}")
        return False

    total = len(fragments)
    print(f"Download fragmentat: {total} fragmente → {client_addr}")

    try:
        for i in range(total):
            msg_id = msg_id_base + i + 1
            packet = build_fragment_pachet(69, fragments[i], msg_id)
            sock.sendto(packet, client_addr)

            if i < total - 1:
                time.sleep(0.001)  # Mic delay pentru UDP

        print(f"{total} fragmente trimise")
        return True
    except Exception as e:
        print(f"Eroare download fragmentat: {e}")
        return False