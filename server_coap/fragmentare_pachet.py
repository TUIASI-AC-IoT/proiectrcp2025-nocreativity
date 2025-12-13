import json
import struct
import math
import socket
import time

MAX_SIZE_PACHET = 14000
HEADER_SIZE = 4
PAYLOAD_MARKER_SIZE = 1
FRAGMENT_OVERHEAD = 200 #spatiu pentru metadata JSON

MAX_PAYLOAD_SIZE = MAX_SIZE_PACHET - HEADER_SIZE - PAYLOAD_MARKER_SIZE - FRAGMENT_OVERHEAD

PAYLOAD_MARKER = 0xFF

def fragmente_necesare(content_b64):
    content_size = len(content_b64)
    if content_size <= MAX_PAYLOAD_SIZE:
        return 1

    return math.ceil(content_size / MAX_PAYLOAD_SIZE)

def split_payload(content_b64,path):
    total_fragments = fragmente_necesare(content_b64)

    if total_fragments == 1:
        return [{
            "path": path,
            "content": content_b64,
        }]

    fragments = []

    for i in range (total_fragments):
        start = i*MAX_PAYLOAD_SIZE
        end = min(start+MAX_PAYLOAD_SIZE, len(content_b64))

        fragment_payload = {
            "path": path,
            "content": content_b64[start:end],
            "fragment": {
                "index": i,
                "total": total_fragments,
                "size": len(content_b64[start:end])
            }
        }

        fragments.append(fragment_payload)

    return fragments


def build_fragment_pachet(code, fragment_payload, msg_id, msg_type=0):
    version = 1
    tkl = 0

    first_byte = (version << 6) | (msg_type << 4) | tkl
    header = struct.pack("!BBH",first_byte,code,msg_id)

    payload = json.dumps(fragment_payload).encode("utf-8")
    pachet = header + bytes([PAYLOAD_MARKER]) + payload

    return pachet

def is_fragment_upload(payload):
    return isinstance(payload, dict) and "fragment" in payload

def get_fragment_info(payload):
    if not is_fragment_upload(payload):
        return None

    fragment_info = payload.get("fragment",{})
    return (
        fragment_info.get("index"),
        fragment_info.get("total"),
        fragment_info.get("size")
    )


class AsamblareFragment:
    def __init__(self):
        self.fragments = {}
        self.expected_total = {}

    def add_fragment(self,path,index,total,content):
        if path not in self.fragments:
            self.fragments[path] = {}
            self.expected_total[path] = total

        self.fragments[path][index] = content

        if len(self.fragments[path]) == total:
            assembled = []
            for i in range (total):
                if i not in self.fragments[path]:
                    return (False, None)
                assembled.append(self.fragments[path][i])

            assembled_content = "".join(assembled)

            del self.fragments[path]
            del self.expected_total[path]

            return (True, assembled_content)

        return (False, None)


    def assemble_content(self, path, index, total, content):
        return self.add_fragment(path, index, total, content)

    def get_progress(self, path):
        if path not in self.fragments:
            return None

        received = len(self.fragments[path])
        total = self.expected_total.get(path,0)
        percentage = (received / total * 100) if total>0 else 0

        return {
            "received": received,
            "total": total,
            "percentage": round(percentage,2)
        }

    def clear_path(self,path):
        if path in self.fragments:
            del self.fragments[path]
        if path in self.expected_total:
            del self.expected_total[path]


assembler = AsamblareFragment()


def handle_fragmented_download(file_path, file_content_b64, sock, client_addr, msg_id_base):
    fragments = split_payload(file_content_b64, file_path)
    total_fragments = len(fragments)

    print(f"[+] Download fragmentat început: {total_fragments} fragmente către {client_addr}")

    original_timeout = sock.gettimeout()
    sock.settimeout(5.0)

    try:
        for i in range(total_fragments):
            fragment_payload = fragments[i]
            msg_id = msg_id_base + i
            attempts = 0
            max_attempts = 10

            while attempts < max_attempts:
                packet = build_fragment_pachet(69, fragment_payload, msg_id)
                sock.sendto(packet, client_addr)
                print(f"    → Trimis fragment {i + 1}/{total_fragments} (msg_id={msg_id}, încercare {attempts + 1})")

                try:
                    data, addr = sock.recvfrom(65535)
                    if addr != client_addr:
                        continue
                    if len(data) < 4:
                        continue

                    recv_type = (data[0] >> 4) & 0x03
                    recv_msg_id = (data[2] << 8) | data[3]

                    if recv_type == 2 and recv_msg_id == msg_id:
                        print(f"    ← ACK primit pentru fragment {i + 1}/{total_fragments}")
                        break

                except socket.timeout:
                    attempts += 1
                    print(f"    Timeout – retransmit fragment {i + 1}/{total_fragments} ({attempts}/{max_attempts})")

            else:
                print(f"[!] EȘEC definitiv la livrare fragment {i + 1}")
                return False

        print(f"[+] Download fragmentat COMPLET ({total_fragments} fragmente livrate)")
        return True

    except Exception as e:
        print(f"[!] Eroare în download fragmentat: {e}")
        return False
    finally:
        # SIGUR: restaurăm timeout-ul doar dacă socket-ul e valid
        try:
            sock.settimeout(original_timeout)
        except:
            pass

def get_fragment_statistics():
    return {
        "active_files": len(assembler.fragments),
        "files": {
            path: assembler.get_progress(path)
            for path in assembler.fragments.keys()
        }
    }