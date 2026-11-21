#!/usr/bin/env python3
"""
ssh_proxy.py - Pure Python stdlib SOCKS5 & HTTP CONNECT proxy bridge for SSH ProxyCommand.
Usage:
    python3 ssh_proxy.py <proxy_url> <target_host> <target_port>
Supports:
    - socks5://[user:pass@]host:port (or socks5h://)
    - http://[user:pass@]host:port (or https://)
"""
import sys, socket, urllib.parse, base64, threading, ssl

def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Unexpected EOF while reading from proxy socket")
        buf.extend(chunk)
    return bytes(buf)

def _redact_proxy_url(proxy_url):
    try:
        p = urllib.parse.urlparse(proxy_url)
        if p.username or p.password:
            host = p.hostname or ""
            port = f":{p.port}" if p.port else ""
            return f"{p.scheme}://***@{host}{port}"
    except Exception:
        pass
    return proxy_url

def connect_socks5(sock, proxy_parsed, target_host, target_port):
    user = urllib.parse.unquote(proxy_parsed.username or "")
    pw = urllib.parse.unquote(proxy_parsed.password or "")
    if user and pw:
        sock.sendall(b"\x05\x02\x00\x02")  # method 0: no auth, method 2: user/pw
    else:
        sock.sendall(b"\x05\x01\x00")      # method 0: no auth

    resp = recv_exact(sock, 2)
    if resp[0] != 5:
        raise ConnectionError("Invalid SOCKS5 greeting response")

    auth_method = resp[1]
    if auth_method == 2:  # user/pass
        u_bytes = user.encode()
        p_bytes = pw.encode()
        sock.sendall(b"\x01" + bytes([len(u_bytes)]) + u_bytes + bytes([len(p_bytes)]) + p_bytes)
        auth_resp = recv_exact(sock, 2)
        if auth_resp[1] != 0:
            raise ConnectionError("SOCKS5 authentication failed")
    elif auth_method != 0:
        raise ConnectionError(f"Unsupported SOCKS5 auth method: {auth_method}")

    # Connect to target_host (using DOMAINNAME type 0x03)
    target_bytes = target_host.encode("idna")
    port_bytes = int(target_port).to_bytes(2, "big")
    req = b"\x05\x01\x00\x03" + bytes([len(target_bytes)]) + target_bytes + port_bytes
    sock.sendall(req)

    reply = recv_exact(sock, 4)
    if reply[0] != 5:
        raise ConnectionError("Invalid SOCKS5 connect response")
    if reply[1] != 0:
        raise ConnectionError(f"SOCKS5 connect error code: {reply[1]}")

    # Consume bound address
    atyp = reply[3]
    if atyp == 1:
        recv_exact(sock, 4 + 2)  # IPv4 + port
    elif atyp == 3:
        n = recv_exact(sock, 1)[0]
        recv_exact(sock, n + 2)  # domain + port
    elif atyp == 4:
        recv_exact(sock, 16 + 2) # IPv6 + port

def connect_http(sock, proxy_parsed, target_host, target_port):
    req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
    req += f"Host: {target_host}:{target_port}\r\n"
    if proxy_parsed.username or proxy_parsed.password:
        user = urllib.parse.unquote(proxy_parsed.username or "")
        pw = urllib.parse.unquote(proxy_parsed.password or "")
        raw_auth = f"{user}:{pw}".encode()
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
        if len(resp_data) > 16384:
            raise ConnectionError("HTTP proxy CONNECT response headers exceeded 16 KiB")

    idx = resp_data.index(b"\r\n\r\n")
    head = resp_data[:idx]
    extra = resp_data[idx + 4:]
    first_line = head.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
    parts = first_line.split()
    if len(parts) < 2 or parts[1] != "200":
        raise ConnectionError(f"HTTP proxy error: {first_line}")
    return extra

def bridge(sock, initial=b""):
    if initial:
        sys.stdout.buffer.write(initial)
        sys.stdout.buffer.flush()

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
    proxy_port = parsed.port or (1080 if "socks" in scheme else (443 if scheme == "https" else 8080))

    extra = b""
    sock = None
    try:
        sock = socket.create_connection((proxy_host, proxy_port), timeout=15.0)
        if scheme in ("socks5", "socks5h", "socks"):
            connect_socks5(sock, parsed, target_host, target_port)
        elif scheme in ("http", "https"):
            if scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=proxy_host)
            extra = connect_http(sock, parsed, target_host, target_port) or b""
        else:
            raise ValueError(f"Unsupported proxy scheme: {scheme}")
        sock.settimeout(None)
    except Exception as e:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        sys.stderr.write(f"[ssh_proxy] Failed to connect via {_redact_proxy_url(proxy_url)}: {e}\n")
        sys.exit(1)

    bridge(sock, initial=extra)

if __name__ == "__main__":
    main()
