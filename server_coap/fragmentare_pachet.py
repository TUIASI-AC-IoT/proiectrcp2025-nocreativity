import json
import struct
import math

MAX_SIZE_PACHET = 1400
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
    fragments = split_payload(file_content_b64,file_path)
    print(f"Download fragmentat: {len(fragments)} fragmente")

    for i, fragment_payload in enumerate(fragments):
        packet = build_fragment_pachet(1,fragment_payload, msg_id_base+i)

        sock.sendto(packet,client_addr)

        print(f"Fragment {i+1}/{len(fragments)} trimis catre {client_addr}")

    return True

def get_fragment_statistics():
    return {
        "active_files": len(assembler.fragments),
        "files": {
            path: assembler.get_progress(path)
            for path in assembler.fragments.keys()
        }
    }