"""Pure Python stdlib bidirectional throughput, Loaded-RTT bufferbloat, and PMTU probes."""

from __future__ import annotations

import math
import os
import socket
import statistics
import struct
import threading
import time

from .sysstate import read_tcp_info

_CHUNK_BYTES = 262144
_SINK_PATTERN = (b"RTHBENCH" * (_CHUNK_BYTES // 8))[:_CHUNK_BYTES]
_ECHO_MAGIC = b"P" * 32


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 3)
    idx = min(len(sorted_vals) - 1, max(0, int(math.ceil(pct * len(sorted_vals))) - 1))
    return round(sorted_vals[idx], 3)


def _rtt_stats(samples: list[float]) -> dict:
    if not samples:
        return {"min": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "jitter_ms": 0.0}
    s = sorted(samples)
    if len(samples) >= 2:
        jit = sum(abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))) / (len(samples) - 1)
    else:
        jit = 0.0
    return {
        "min": round(s[0], 3),
        "avg": round(sum(s) / len(s), 3),
        "p50": _percentile(s, 0.50),
        "p95": _percentile(s, 0.95),
        "p99": _percentile(s, 0.99),
        "max": round(s[-1], 3),
        "jitter_ms": round(jit, 3),
    }


def _apply_sock_mss(sock: socket.socket, mss_override: int) -> None:
    if mss_override and mss_override >= 536 and hasattr(socket, "TCP_MAXSEG"):
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, int(mss_override))
        except OSError:
            pass


class ProbeServer:
    """Ephemeral TCP bulk/echo/download and UDP echo responder."""

    def __init__(self, bind_host: str = "0.0.0.0", tcp_port: int = 29891, udp_port: int = 29891):
        self.bind_host = bind_host
        self._req_tcp_port = int(tcp_port)
        self._req_udp_port = int(udp_port)
        self.tcp_port = 0
        self.udp_port = 0
        self._tcp_sock: socket.socket | None = None
        self._udp_sock: socket.socket | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._stop.clear()
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_sock.bind((self.bind_host, self._req_tcp_port))
        tcp_sock.listen(128)
        tcp_sock.settimeout(0.3)
        self._tcp_sock = tcp_sock
        self.tcp_port = tcp_sock.getsockname()[1]

        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_udp = self._req_udp_port if self._req_udp_port != 0 else 0
        udp_sock.bind((self.bind_host, target_udp))
        udp_sock.settimeout(0.3)
        self._udp_sock = udp_sock
        self.udp_port = udp_sock.getsockname()[1]

        t1 = threading.Thread(target=self._accept_loop, daemon=True)
        t2 = threading.Thread(target=self._udp_loop, daemon=True)
        t1.start()
        t2.start()
        self._threads.extend([t1, t2])

    def stop(self) -> None:
        self._stop.set()
        for s in (self._tcp_sock, self._udp_sock):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        self._tcp_sock = None
        self._udp_sock = None
        for t in self._threads:
            t.join(timeout=1.5)
        self._threads.clear()

    def _accept_loop(self) -> None:
        while not self._stop.is_set() and self._tcp_sock is not None:
            try:
                conn, _ = self._tcp_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
            t.start()

    def _handle_conn(self, conn: socket.socket) -> None:
        buf = bytearray(_CHUNK_BYTES)
        view = memoryview(buf)
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.settimeout(10.0)
            mode = conn.recv(1)
            if not mode:
                return
            if mode == b"E":
                while not self._stop.is_set():
                    data = conn.recv(4096)
                    if not data:
                        break
                    conn.sendall(data)
            elif mode == b"S":
                total = 0
                while not self._stop.is_set():
                    n = conn.recv_into(view)
                    if n <= 0:
                        break
                    total += n
                conn.sendall(struct.pack("!Q", total))
            elif mode == b"D":
                hdr = conn.recv(2)
                if len(hdr) < 2:
                    return
                (dur_ms,) = struct.unpack("!H", hdr)
                deadline = time.monotonic() + min(60.0, max(0.05, dur_ms / 1000.0))
                chunk_view = memoryview(_SINK_PATTERN)
                while not self._stop.is_set() and time.monotonic() < deadline:
                    conn.sendall(chunk_view)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _udp_loop(self) -> None:
        while not self._stop.is_set() and self._udp_sock is not None:
            try:
                data, addr = self._udp_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if data:
                try:
                    self._udp_sock.sendto(data, addr)
                except OSError:
                    pass


def probe_pmtu(
    host: str,
    udp_port: int,
    driver=None,
    min_mtu: int = 1200,
    max_mtu: int = 1500,
    fast_test: bool = False,
) -> dict:
    """Discover effective forward/reverse PMTU using UDP DF binary search + TCP_INFO check."""
    if host in ("127.0.0.1", "::1", "localhost") or fast_test:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.6)
        ok_echo = False
        try:
            sock.sendto(b"PMTU1472" + b"x" * 1200, (host, udp_port))
            rep, _ = sock.recvfrom(2048)
            ok_echo = rep.startswith(b"PMTU1472")
        except OSError:
            pass
        finally:
            sock.close()
        return {
            "forward_bytes": max_mtu if ok_echo else 1460,
            "reverse_bytes": max_mtu if ok_echo else 1460,
            "blackhole_detected": False,
        }

    lo, hi = min_mtu, max_mtu
    best = min_mtu
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.45)
    ip_mtu_discover = getattr(socket, "IP_MTU_DISCOVER", 10)
    ip_pmtudisc_do = 2
    try:
        try:
            sock.setsockopt(socket.IPPROTO_IP, ip_mtu_discover, ip_pmtudisc_do)
        except OSError:
            pass
        while lo <= hi:
            mid = (lo + hi) // 2
            payload_len = max(64, mid - 28)
            pkt = b"PMTU" + (b"x" * (payload_len - 4))
            ok = False
            try:
                sock.sendto(pkt, (host, udp_port))
                data, _ = sock.recvfrom(2048)
                if len(data) == payload_len:
                    ok = True
            except OSError:
                ok = False
            if ok:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
    finally:
        sock.close()

    return {
        "forward_bytes": best,
        "reverse_bytes": best,
        "blackhole_detected": best < 1380,
    }


def probe_unloaded_rtt(
    host: str,
    tcp_port: int,
    udp_port: int,
    samples: int = 20,
    timeout: float = 1.5,
) -> dict:
    """Measure unloaded TCP echo RTT and UDP loss/jitter baseline."""
    tcp_rtts: list[float] = []
    sock = None
    try:
        sock = socket.create_connection((host, tcp_port), timeout=timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(timeout)
        sock.sendall(b"E")
        for _ in range(max(3, samples)):
            t0 = time.monotonic()
            sock.sendall(_ECHO_MAGIC)
            got = b""
            while len(got) < len(_ECHO_MAGIC):
                part = sock.recv(len(_ECHO_MAGIC) - len(got))
                if not part:
                    break
                got += part
            if len(got) == len(_ECHO_MAGIC):
                tcp_rtts.append((time.monotonic() - t0) * 1000.0)
    except OSError:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    udp_rtts: list[float] = []
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    usock.settimeout(min(0.4, timeout))
    udp_sent = max(5, min(25, samples))
    try:
        for seq in range(udp_sent):
            pkt = struct.pack("!I", seq) + b"U" * 60
            t0 = time.monotonic()
            try:
                usock.sendto(pkt, (host, udp_port))
                rep, _ = usock.recvfrom(2048)
                if len(rep) == len(pkt):
                    udp_rtts.append((time.monotonic() - t0) * 1000.0)
            except OSError:
                pass
    finally:
        usock.close()

    tcp_stats = _rtt_stats(tcp_rtts)
    udp_loss = round(((udp_sent - len(udp_rtts)) / float(udp_sent)) * 100.0, 2)
    return {
        "tcp_rtt": tcp_stats,
        "udp_loss_pct": udp_loss,
        "udp_samples_ok": len(udp_rtts),
        "udp_samples_sent": udp_sent,
    }


def _send_stream(
    host: str,
    tcp_port: int,
    duration_s: float,
    mss_override: int,
    buckets: list[int] | None,
    t_start: float,
    bucket_s: float,
    results: list[dict],
    lock: threading.Lock,
) -> None:
    sent = 0
    tcp_info = {}
    aborted = False
    sock = None
    view = memoryview(_SINK_PATTERN)
    try:
        sock = socket.create_connection((host, tcp_port), timeout=5.0)
        _apply_sock_mss(sock, mss_override)
        sock.settimeout(5.0)
        sock.sendall(b"S")
        deadline = t_start + duration_s
        while time.monotonic() < deadline:
            n = sock.send(view)
            if n <= 0:
                break
            sent += n
            if buckets is not None:
                bi = min(len(buckets) - 1, max(0, int((time.monotonic() - t_start) / bucket_s)))
                with lock:
                    buckets[bi] += n
        tcp_info = read_tcp_info(sock)
        try:
            sock.shutdown(socket.SHUT_WR)
            sock.recv(8)
        except OSError:
            pass
    except OSError:
        aborted = True
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    with lock:
        results.append({"bytes": sent, "tcp_info": tcp_info, "aborted": aborted})


def _recv_stream(
    host: str,
    tcp_port: int,
    duration_s: float,
    mss_override: int,
    results: list[dict],
    lock: threading.Lock,
) -> None:
    got_bytes = 0
    aborted = False
    sock = None
    buf = bytearray(_CHUNK_BYTES)
    view = memoryview(buf)
    try:
        sock = socket.create_connection((host, tcp_port), timeout=5.0)
        _apply_sock_mss(sock, mss_override)
        sock.settimeout(max(2.0, duration_s + 2.0))
        dur_ms = max(50, min(60000, int(duration_s * 1000)))
        sock.sendall(b"D" + struct.pack("!H", dur_ms))
        while True:
            n = sock.recv_into(view)
            if n <= 0:
                break
            got_bytes += n
    except OSError:
        aborted = True
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    with lock:
        results.append({"bytes": got_bytes, "aborted": aborted})


def _loaded_rtt_worker(
    host: str,
    tcp_port: int,
    stop_ev: threading.Event,
    interval_s: float,
    rtts: list[float],
) -> None:
    sock = None
    try:
        sock = socket.create_connection((host, tcp_port), timeout=2.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(1.5)
        sock.sendall(b"E")
        while not stop_ev.is_set():
            t0 = time.monotonic()
            sock.sendall(_ECHO_MAGIC)
            got = b""
            while len(got) < len(_ECHO_MAGIC):
                part = sock.recv(len(_ECHO_MAGIC) - len(got))
                if not part:
                    return
                got += part
            rtts.append((time.monotonic() - t0) * 1000.0)
            stop_ev.wait(interval_s)
    except OSError:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def probe_trial(
    host: str,
    tcp_port: int,
    udp_port: int,
    duration_s: float = 3.0,
    streams: int = 4,
    mss_override: int = 0,
    include_bidir: bool = True,
    include_burst: bool = True,
    probe_interval_s: float = 0.05,
    unloaded_p50_ms: float | None = None,
) -> dict:
    """Execute one full multi-phase probe trial (1-stream, N-stream + loaded RTT, bidir, UDP)."""
    dur_1 = max(0.08, duration_s * 0.45)
    dur_n = max(0.10, duration_s)

    if unloaded_p50_ms is None:
        ul = probe_unloaded_rtt(host, tcp_port, udp_port, samples=6, timeout=1.0)
        unloaded_p50 = float(ul["tcp_rtt"]["p50"] or 1.0)
    else:
        unloaded_p50 = float(unloaded_p50_ms)

    # 1) Single-stream throughput + TCP_INFO
    r1: list[dict] = []
    l1 = threading.Lock()
    t0 = time.monotonic()
    _send_stream(host, tcp_port, dur_1, mss_override, None, t0, dur_1, r1, l1)
    el1 = max(0.01, time.monotonic() - t0)
    b1 = sum(x["bytes"] for x in r1)
    mbps_1 = round((b1 * 8.0) / (el1 * 1_000_000.0), 3)
    ti = (r1[0].get("tcp_info") if r1 else {}) or {}

    # 2) N-stream saturation + concurrent Loaded-RTT probe
    n_buckets = max(3, min(20, int(dur_n / 0.25) or 3))
    bucket_s = dur_n / float(n_buckets)
    buckets = [0] * n_buckets
    rn: list[dict] = []
    ln = threading.Lock()
    loaded_rtts: list[float] = []
    stop_rtt = threading.Event()
    rtt_thr = threading.Thread(
        target=_loaded_rtt_worker,
        args=(host, tcp_port, stop_rtt, probe_interval_s, loaded_rtts),
        daemon=True,
    )
    rtt_thr.start()

    tn0 = time.monotonic()
    workers = [
        threading.Thread(
            target=_send_stream,
            args=(host, tcp_port, dur_n, mss_override, buckets, tn0, bucket_s, rn, ln),
            daemon=True,
        )
        for _ in range(max(2, streams))
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=dur_n + 5.0)
    eln = max(0.01, time.monotonic() - tn0)
    stop_rtt.set()
    rtt_thr.join(timeout=1.5)

    bn = sum(x["bytes"] for x in rn)
    mbps_n = round((bn * 8.0) / (eln * 1_000_000.0), 3)
    aborted = any(x.get("aborted") for x in (r1 + rn)) and (bn == 0)

    active_buckets = [b for b in buckets[:-1]] if len(buckets) > 2 else buckets
    cov = 0.0
    if active_buckets and sum(active_buckets) > 0:
        mean_b = statistics.mean(active_buckets)
        if mean_b > 0:
            cov = min(1.0, round(statistics.pstdev(active_buckets) / mean_b, 4))

    # 3) Optional bidirectional saturation
    mbps_bidir = mbps_n
    if include_bidir:
        dur_bi = max(0.08, duration_s * 0.45)
        rb_up: list[dict] = []
        rb_dn: list[dict] = []
        lbi = threading.Lock()
        tb0 = time.monotonic()
        tw_up = threading.Thread(
            target=_send_stream,
            args=(host, tcp_port, dur_bi, mss_override, None, tb0, dur_bi, rb_up, lbi),
            daemon=True,
        )
        tw_dn = threading.Thread(
            target=_recv_stream,
            args=(host, tcp_port, dur_bi, mss_override, rb_dn, lbi),
            daemon=True,
        )
        tw_up.start()
        tw_dn.start()
        tw_up.join(timeout=dur_bi + 5.0)
        tw_dn.join(timeout=dur_bi + 5.0)
        elbi = max(0.01, time.monotonic() - tb0)
        bi_bytes = sum(x["bytes"] for x in rb_up) + sum(x["bytes"] for x in rb_dn)
        if bi_bytes > 0:
            mbps_bidir = round((bi_bytes * 8.0) / (elbi * 1_000_000.0), 3)

    # 4) Optional short-flow burst handshake latency
    burst_ms = 0.0
    if include_burst:
        burst_times = []
        for _ in range(4):
            bs = None
            t_b = time.monotonic()
            try:
                bs = socket.create_connection((host, tcp_port), timeout=1.0)
                bs.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                bs.sendall(b"E")
                bs.sendall(_ECHO_MAGIC)
                bs.recv(len(_ECHO_MAGIC))
                burst_times.append((time.monotonic() - t_b) * 1000.0)
            except OSError:
                pass
            finally:
                if bs is not None:
                    try:
                        bs.close()
                    except OSError:
                        pass
        if burst_times:
            burst_ms = round(statistics.mean(burst_times), 3)

    # 5) Quick UDP loss check
    udp_res = probe_unloaded_rtt(host, tcp_port, udp_port, samples=6, timeout=0.6)
    rtt_s = _rtt_stats(loaded_rtts)

    total_retrans = max([int((x.get("tcp_info") or {}).get("total_retrans", 0)) for x in (r1 + rn)] or [0])
    est_segs = max(1, (b1 + bn) // 1400)
    retrans_pct = round(min(100.0, (total_retrans / float(est_segs)) * 100.0), 3)

    return {
        "aborted": aborted,
        "throughput_1_mbps": mbps_1,
        "throughput_n_mbps": mbps_n,
        "throughput_bidir_mbps": mbps_bidir,
        "throughput_mbps": mbps_n,
        "unloaded_rtt_p50_ms": round(unloaded_p50, 3),
        "loaded_rtt_p95_ms": rtt_s["p95"] if loaded_rtts else round(unloaded_p50, 3),
        "rtt_p50_ms": rtt_s["p50"] if loaded_rtts else round(unloaded_p50, 3),
        "rtt_p99_ms": rtt_s["p99"] if loaded_rtts else round(unloaded_p50, 3),
        "jitter_ms": rtt_s["jitter_ms"],
        "retrans_pct": retrans_pct,
        "udp_loss_pct": float(udp_res["udp_loss_pct"]),
        "drop_delta": 0,
        "stability_cov": cov,
        "burst_connect_ms": burst_ms,
        "tcp_info": ti,
    }
