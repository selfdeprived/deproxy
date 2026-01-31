import socket
import struct
import threading
import time
import uuid
import yaml

proxy_port = target_host = target_port = transfer_host = transfer_port = off_title = off_caption = on_title = on_caption = off_hex = on_hex = None

with open('config.yml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f) or {}

globals().update(config)

def encode_varint(val):
    total = b''
    if val == 0: return b'\x00'
    while val > 0:
        byte = val & 0x7F
        val >>= 7
        if val > 0:
            byte |= 0x80
        total += bytes([byte])
    return total

def is_server_up(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))

        s.send(b'\x07\x00\x00\x00\x00\x00\x00\x01')
        s.close()
        return True
    except:
        return False

def create_packet(text, color="#FF5555", mode="title"):
    # NBT body
    text_bytes = text.encode('utf-8')
    color_bytes = color.encode('utf-8')

    nbt = b'\x0a'  # TAG_Compound (\n)
    nbt += b'\x08' + struct.pack('>H', 5) + b'color'
    nbt += struct.pack('>H', len(color_bytes)) + color_bytes
    nbt += b'\x08' + struct.pack('>H', 4) + b'text'
    nbt += struct.pack('>H', len(text_bytes)) + text_bytes
    nbt += b'\x00'  # TAG_End

    # Type (e for title, c for subtitle)
    msg_type = b'e' if mode.lower() == "title" else b'c'

    # Merged NBT with type
    payload = msg_type + nbt

    # +Payload length byte at the start
    prefix = struct.pack('B', len(payload))

    return prefix + payload

def title_times(fade_in, stay, fade_out):
    # Type 'f' for times
    msg_type = b'f'

    # Big-endian Integer
    payload = msg_type + struct.pack('>III', fade_in, stay, fade_out)

    # +Payload length byte at the start
    prefix = struct.pack('B', len(payload))

    return prefix + payload

def valid_check(data):
    try:
        ptr = 0

        # Packet length
        pkt_len = 0
        shift = 0
        while True:
            b = data[ptr]
            pkt_len |= (b & 0x7f) << shift
            ptr += 1
            if not (b & 0x80): break
            shift += 7

        # Packet ID
        if data[ptr] != 0x00:
            return False
        ptr += 1

        # Protocol Version
        proto_ver = 0
        shift = 0
        while True:
            b = data[ptr]
            proto_ver |= (b & 0x7f) << shift
            ptr += 1
            if not (b & 0x80): break
            shift += 7

        # Hostname
        host_len = 0
        shift = 0
        while True:
            b = data[ptr]
            host_len |= (b & 0x7f) << shift
            ptr += 1
            if not (b & 0x80): break
            shift += 7

        host = data[ptr: ptr + host_len].decode('utf-8')
        ptr += host_len

        # Port
        port = struct.unpack('>H', data[ptr: ptr + 2])[0]
        ptr += 2

        print(f"[*] Packet verified! Host: {host}, Port: {port}, Protocol: {proto_ver}")
        return True

    except Exception as e:
        print(f"[*] Packet parsing error: {e}")
        return False

class ProxySession:
    def __init__(self, client_socket):
        self.client_socket = client_socket
        self.target_host = target_host
        self.target_port = target_port
        self.target_socket = None
        self.server_alive = True
        self.lock = threading.Lock()
        self.native_id = str( uuid.uuid4() )[:5]

    def log(self, message):
        print(f"[*] [THREAD–{self.native_id}] {message}")

    def start(self):
        try:
            self.target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.target_socket.connect((self.target_host, self.target_port))

            data = self.client_socket.recv(1024)
            if not data:
                return

            host_len_index = 4
            host_len = data[host_len_index]

            end_index = host_len_index + 1 + host_len + 3

            chopped = data[:end_index]

            next_state = chopped[-1]

            if next_state in (0x02, 0x03) and valid_check(chopped):
                self.target_socket.send(data)
                threading.Thread(target=self.bridge_server_to_client, daemon=True).start()
                threading.Thread(target=self.bridge_client_to_server, daemon=True).start()
                threading.Thread(target=self.keep_alive_filler, daemon=True).start()
                self.log("The player has passed through the proxy.")
            else:
                self.target_socket.send(data)

                try:
                    self.client_socket.settimeout(1.0)
                    status_request = self.client_socket.recv(1024)

                    if status_request:
                        self.target_socket.send(status_request)

                    self.target_socket.settimeout(1.0)
                    response = self.target_socket.recv(262144)

                    if response:
                        self.client_socket.send(response)
                        client_ping = self.client_socket.recv(1024)

                        if client_ping:
                            self.target_socket.send(client_ping)
                            pong = self.target_socket.recv(1024)
                            if pong:
                                self.client_socket.send(pong)

                except socket.timeout:
                    pass

                finally:
                    self.client_socket.close()
                    self.target_socket.close()

        except Exception as e:
            self.log(f"Error: {e}")
            if self.client_socket: self.client_socket.close()

    def keep_alive_filler(self):
        while True:
            time.sleep(10)
            if not self.server_alive:
                try:
                    with self.lock:
                        self.client_socket.send(b'\x00')  # Heartbeat
                except:
                    break

    def bridge_server_to_client(self):
        while True:
            try:
                data = self.target_socket.recv(262144)

                is_disconnect_packet = data[1] == 0x1d

                has_trigger_text = life_trigger.encode('utf-8') in data

                if is_disconnect_packet and has_trigger_text:
                    self.log("Server went offline. Entering Limbo Mode...")

                    self.server_alive = False
                    self.handle_reconnect_limbo()
                    break

                with self.lock:
                    self.client_socket.send(data)
            except:
                break

    def handle_reconnect_limbo(self):
        dot_count = 1
        self.client_socket.send( title_times(fade_in, stay, fade_out) )

        self.log(f"Waiting {await_shutdown} seconds for server to completely shut down!")
        time.sleep(await_shutdown)

        while not is_server_up(self.target_host, self.target_port):
            self.log("Server still offline... waiting...")

            dots = "." * dot_count
            # Title Packet
            self.client_socket.send(create_packet(off_title, off_hex, "title"))
            # Subtitle Packet
            self.client_socket.send(create_packet(off_caption.replace("%dots%", dots) if "%dots%" in off_caption else off_caption,
                                                  off_hex,
                                                  "subtitle")
                                    )

            dot_count = dot_count + 1 if dot_count < 3 else 1

            time.sleep(3)

        # Title Packet
        self.client_socket.send(create_packet(on_title, on_hex, "title"))
        # Subtitle Packet
        self.client_socket.send(create_packet(on_caption, on_hex, "subtitle"))

        self.log(f"Server detected! Waiting {await_running} seconds for final initialization!")
        time.sleep(await_running)

        try:
            with self.lock:
                server = bytes(transfer_host, encoding='utf-8')
                port = transfer_port

                selen = len(server)
                polen = len( str(port) )

                # Transfer Packet
                self.client_socket.send( encode_varint(selen + polen) + b's' + encode_varint(selen) + server + encode_varint(port) )
            self.log("Transfer Packet sent. Player should be reconnecting now.")
        except Exception as e:
            self.log(f"Failed to send transfer: {e}")

        self.client_socket.close()

    def bridge_client_to_server(self):
        while True:
            try:
                data = self.client_socket.recv(262144)

                if not data:
                    self.log("The player left the server by himself. Closing the session.")
                    self.server_alive = False
                    break

                if self.server_alive and self.target_socket:
                    try:
                        self.target_socket.send(data)
                    except:
                        pass
            except:
                break

        self.cleanup()

    def cleanup(self):
        self.log("Final resource cleanup.")
        try:
            self.target_socket.close()
        except:
            pass
        try:
            self.client_socket.close()
        except:
            pass

def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', proxy_port))
    server.listen(10)
    print(f"[*] Proxy active on port {proxy_port} -> {target_host}:{target_port}")

    while True:
        client, addr = server.accept()
        ProxySession(client).start()

if __name__ == "__main__":
    try:
        start_proxy()
    except KeyboardInterrupt:
        print(f"\r[*] Proxy server stopped.")
