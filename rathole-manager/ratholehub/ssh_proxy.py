#!/usr/bin/env python3
"""
ssh_proxy.py - Pure Python stdlib SOCKS5 & HTTP CONNECT proxy bridge for SSH ProxyCommand.
Usage:
    python3 ssh_proxy.py <proxy_url> <target_host> <target_port>
Supports:
    - socks5://[user:pass@]host:port (or socks5h://)
    - http://[user:pass@]host:port (or https://)
"""
import sys, socket, urllib.parse, base64, threading

def connect_socks5(sock, proxy_parsed, target_host, target_port):
    user = proxy_parsed.username
    pw = proxy_parsed.password
    if user and pw:
        sock.sendall(b"\x05\x02\x00\x02")  # method 0: no auth, method 2: user/pw
    else:
        sock.sendall(b"\x05\x01\x00")      # method 0: no auth

    resp = sock.recv(2)
    if len(resp) < 2 or resp[0] != 5:
        raise ConnectionError("Invalid SOCKS5 greeting response")
    
    auth_method = resp[1]
    if auth_method == 2:  # user/pass
        u_bytes = user.encode()
        p_bytes = pw.encode()
        sock.sendall(b"\x01" + bytes([len(u_bytes)]) + u_bytes + bytes([len(p_bytes)]) + p_bytes)
        auth_resp = sock.recv(2)
        if len(auth_resp) < 2 or auth_resp[1] != 0:
            raise ConnectionError("SOCKS5 authentication failed")
    elif auth_method != 0:
        raise ConnectionError(f"Unsupported SOCKS5 auth method: {auth_method}")

    # Connect to target_host (using DOMAINNAME type 0x03)
    target_bytes = target_host.encode("idna")
    port_bytes = int(target_port).to_bytes(2, "big")
    req = b"\x05\x01\x00\x03" + bytes([len(target_bytes)]) + target_bytes + port_bytes
    sock.sendall(req)

    reply = sock.recv(4)
    if len(reply) < 4 or reply[0] != 5:
        raise ConnectionError("Invalid SOCKS5 connect response")
    if reply[1] != 0:
        raise ConnectionError(f"SOCKS5 connect error code: {reply[1]}")
    
    # Consume bound address
    atyp = reply[3]
    if atyp == 1:
        sock.recv(4 + 2)  # IPv4 + port
    elif atyp == 3:
        n = sock.recv(1)[0]
        sock.recv(n + 2)  # domain + port
    elif atyp == 4:
        sock.recv(16 + 2) # IPv6 + port

def connect_http(sock, proxy_parsed, target_host, target_port):
    req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
    req += f"Host: {target_host}:{target_port}\r\n"
    if proxy_parsed.username and proxy_parsed.password:
        raw_auth = f"{proxy_parsed.username}:{proxy_parsed.password}".encode()
        auth = base64.b64encode(raw_auth).decode()
        req += f"Proxy-Authorization: Basic {auth}\r\n"
    req += "Proxy-Connection: Keep-Alive\r\n\r\n"
    sock.sendall(req.encode("latin1"))

    resp_data = b""
    while b"\r\n\r\n" not in resp_data:
        chunk = sock.recv(1024)
        if not chunk:
            raise ConnectionError("HTTP proxy closed connection during CONNECT handshake")
        resp_data += chunk
    
    first_line = resp_data.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
    parts = first_line.split()
    if len(parts) < 2 or parts[1] != "200":
        raise ConnectionError(f"HTTP proxy error: {first_line}")

def bridge(sock):
    def stdin_to_sock():
        try:
            while True:
                data = sys.stdin.buffer.read(8192)
                if not data:
                    break
                sock.sendall(data)
        except Exception:
            pass
        finally:
            try:
                sock.shutdown(socket.SHUT_WR)
            except Exception:
                pass

    t = threading.Thread(target=stdin_to_sock, daemon=True)
    t.start()

    try:
        while True:
            data = sock.recv(8192)
            if not data:
                break
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    except Exception:
        pass

def main():
    if len(sys.argv) < 4:
        sys.stderr.write("Usage: ssh_proxy.py <proxy_url> <target_host> <target_port>\n")
        sys.exit(1)

    proxy_url = sys.argv[1]
    target_host = sys.argv[2]
    target_port = int(sys.argv[3])

    parsed = urllib.parse.urlparse(proxy_url)
    scheme = (parsed.scheme or "socks5").lower()
    proxy_host = parsed.hostname or "127.0.0.1"
    proxy_port = parsed.port or (1080 if "socks" in scheme else 8080)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    try:
        sock.connect((proxy_host, proxy_port))
        if scheme in ("socks5", "socks5h", "socks"):
            connect_socks5(sock, parsed, target_host, target_port)
        elif scheme in ("http", "https"):
            connect_http(sock, parsed, target_host, target_port)
        else:
            raise ValueError(f"Unsupported proxy scheme: {scheme}")
        sock.settimeout(None)
    except Exception as e:
        sys.stderr.write(f"[ssh_proxy] Failed to connect via {proxy_url}: {e}\n")
        sys.exit(1)

    bridge(sock)

if __name__ == "__main__":
    main()
