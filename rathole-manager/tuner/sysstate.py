"""Linux system capability discovery, atomic snapshot/restore, TCP_INFO, and counters."""

from __future__ import annotations

import copy
import datetime
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess

from .profile import clamp_config_for_ram

BASE_SNAPSHOT_SYSCTLS = (
    "net.core.default_qdisc",
    "net.ipv4.tcp_congestion_control",
    "net.ipv4.tcp_notsent_lowat",
    "net.ipv4.tcp_mtu_probing",
    "net.ipv4.tcp_base_mss",
    "net.ipv4.tcp_min_snd_mss",
    "net.ipv4.tcp_slow_start_after_idle",
    "net.ipv4.tcp_ecn",
    "net.ipv4.tcp_timestamps",
    "net.ipv4.tcp_fastopen",
    "net.ipv4.tcp_sack",
    "net.ipv4.tcp_dsack",
    "net.ipv4.tcp_autocorking",
    "net.ipv4.tcp_frto",
    "net.ipv4.tcp_early_retrans",
    "net.ipv4.tcp_thin_linear_timeouts",
    "net.ipv4.tcp_tw_reuse",
    "net.core.rmem_max",
    "net.core.wmem_max",
    "net.core.rmem_default",
    "net.core.wmem_default",
    "net.core.netdev_max_backlog",
    "net.core.netdev_budget",
    "net.core.somaxconn",
    "net.ipv4.tcp_max_syn_backlog",
    "net.ipv4.tcp_rmem",
    "net.ipv4.tcp_wmem",
    "net.ipv4.udp_rmem_min",
    "net.ipv4.udp_wmem_min",
    "net.netfilter.nf_conntrack_max",
)


class SysDriver:
    """Abstract system interaction boundary for kernel/NIC/file inspection."""

    def read_text(self, path: str) -> str | None:
        raise NotImplementedError

    def write_text(self, path: str, content: str, mode: int = 0o644) -> None:
        raise NotImplementedError

    def file_exists(self, path: str) -> bool:
        raise NotImplementedError

    def remove_file(self, path: str) -> None:
        raise NotImplementedError

    def list_dir(self, path: str) -> list[str]:
        raise NotImplementedError

    def which(self, name: str) -> str | None:
        raise NotImplementedError

    def run(self, argv: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
        raise NotImplementedError

    def read_sysctl(self, key: str) -> str | None:
        raise NotImplementedError

    def write_sysctl(self, key: str, value: str) -> tuple[bool, str]:
        raise NotImplementedError

    def get_ram_mb(self) -> int:
        raise NotImplementedError

    def get_cpu_count(self) -> int:
        return os.cpu_count() or 1


class RealLinuxDriver(SysDriver):
    """Production Linux driver executing argv-only commands without a shell."""

    def read_text(self, path: str) -> str | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None

    def write_text(self, path: str, content: str, mode: int = 0o644) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{path}.tmp.{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, path)

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def remove_file(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def list_dir(self, path: str) -> list[str]:
        try:
            return sorted(os.listdir(path))
        except OSError:
            return []

    def which(self, name: str) -> str | None:
        return shutil.which(name) or (
            f"/usr/local/bin/{name}" if os.path.isfile(f"/usr/local/bin/{name}") else None
        )

    def run(self, argv: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                argv, shell=False, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except FileNotFoundError:
            return 127, "", f"missing binary: {argv[0]}"
        except subprocess.TimeoutExpired:
            return 124, "", f"timeout running {argv[0]}"

    def _proc_path(self, key: str) -> str:
        return "/proc/sys/" + key.replace(".", "/")

    def read_sysctl(self, key: str) -> str | None:
        txt = self.read_text(self._proc_path(key))
        if txt is not None:
            return " ".join(txt.strip().split())
        rc, out, _ = self.run(["sysctl", "-n", key])
        return " ".join(out.strip().split()) if rc == 0 else None

    def write_sysctl(self, key: str, value: str) -> tuple[bool, str]:
        rc, _, err = self.run(["sysctl", "-w", f"{key}={value}"])
        if rc == 0:
            return True, ""
        return False, (err or "").strip() or "sysctl failed"

    def get_ram_mb(self) -> int:
        mem = self.read_text("/proc/meminfo") or ""
        m = re.search(r"MemTotal:\s+(\d+)\s+kB", mem)
        if m:
            return max(64, int(m.group(1)) // 1024)
        return 1024


class MockSysDriver(SysDriver):
    """Deterministic in-memory driver for unit, loopback, and CI testing."""

    def __init__(
        self,
        ram_mb: int = 2048,
        cpus: int = 4,
        iface: str = "eth0",
        ipv6_active: bool = False,
        cpu_governor: str = "performance",
        available_cc: list[str] | None = None,
        available_qdisc: list[str] | None = None,
        unsupported_ops: set[str] | None = None,
    ):
        self.ram_mb = int(ram_mb)
        self.cpus = int(cpus)
        self.iface = iface
        self.ipv6_active = bool(ipv6_active)
        self.mtu = 1500
        self.txqueuelen = 1000
        self.qdisc_line = "qdisc fq_codel 0: root refcnt 2 limit 10240p"
        self.route_line = f"default via 192.0.2.1 dev {iface} proto static initcwnd 10 initrwnd 10"
        self.offloads = {"tso": True, "gso": True, "gro": True, "lro": False}
        self.unsupported_ops = set(unsupported_ops or ())
        self.iptables_mangle: list[str] = []
        self.files: dict[str, str] = {}
        self.dirs: dict[str, list[str]] = {}
        self.bins = {"ip", "sysctl", "tc", "ethtool", "iptables", "systemctl", "rathole", "xray", "nginx"}
        self.sysctls = {
            "net.core.default_qdisc": "fq_codel",
            "net.ipv4.tcp_congestion_control": "cubic",
            "net.ipv4.tcp_available_congestion_control": " ".join(available_cc or ["cubic", "bbr", "reno"]),
            "net.ipv4.tcp_notsent_lowat": "4294967295",
            "net.ipv4.tcp_mtu_probing": "0",
            "net.ipv4.tcp_base_mss": "1024",
            "net.ipv4.tcp_min_snd_mss": "48",
            "net.ipv4.tcp_slow_start_after_idle": "1",
            "net.ipv4.tcp_ecn": "2",
            "net.ipv4.tcp_timestamps": "1",
            "net.ipv4.tcp_fastopen": "1",
            "net.ipv4.tcp_sack": "1",
            "net.ipv4.tcp_dsack": "1",
            "net.ipv4.tcp_autocorking": "1",
            "net.ipv4.tcp_frto": "2",
            "net.ipv4.tcp_early_retrans": "3",
            "net.ipv4.tcp_thin_linear_timeouts": "0",
            "net.ipv4.tcp_tw_reuse": "2",
            "net.core.rmem_max": "212992",
            "net.core.wmem_max": "212992",
            "net.core.rmem_default": "212992",
            "net.core.wmem_default": "212992",
            "net.core.netdev_max_backlog": "1000",
            "net.core.netdev_budget": "300",
            "net.core.somaxconn": "4096",
            "net.ipv4.tcp_max_syn_backlog": "4096",
            "net.ipv4.tcp_rmem": "4096 131072 6291456",
            "net.ipv4.tcp_wmem": "4096 16384 4194304",
            "net.ipv4.udp_rmem_min": "4096",
            "net.ipv4.udp_wmem_min": "4096",
            "net.netfilter.nf_conntrack_max": "262144",
            "fs.file-max": "1048576",
            "net.ipv4.ip_local_port_range": "32768 60999",
        }
        self.available_qdisc = list(available_qdisc or ["fq", "fq_codel", "pfifo_fast"])
        self.files["/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"] = cpu_governor + "\n"
        self.files[f"/sys/class/net/{iface}/statistics/tx_dropped"] = "0\n"
        self.files[f"/sys/class/net/{iface}/statistics/rx_dropped"] = "0\n"
        self.files["/proc/net/snmp"] = (
            "Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens AttemptFails EstabResets "
            "CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts\n"
            "Tcp: 1 200 120000 -1 100 50 1 0 10 10000 10000 12 0 0\n"
        )
        self.systemd_cmds: list[list[str]] = []

    def read_text(self, path: str) -> str | None:
        if path in self.files:
            return self.files[path]
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        return None

    def write_text(self, path: str, content: str, mode: int = 0o644) -> None:
        if path.startswith("/etc/tuner_mock") or os.path.isabs(path) and not path.startswith("/proc") and not path.startswith("/sys"):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
        self.files[path] = content

    def file_exists(self, path: str) -> bool:
        return path in self.files or os.path.exists(path)

    def remove_file(self, path: str) -> None:
        self.files.pop(path, None)
        try:
            os.remove(path)
        except OSError:
            pass

    def list_dir(self, path: str) -> list[str]:
        if path in self.dirs:
            return self.dirs[path]
        return []

    def which(self, name: str) -> str | None:
        return f"/usr/local/bin/{name}" if name in self.bins else None

    def read_sysctl(self, key: str) -> str | None:
        return self.sysctls.get(key)

    def write_sysctl(self, key: str, value: str) -> tuple[bool, str]:
        if key in self.unsupported_ops:
            return False, "operation not permitted"
        if key == "net.ipv4.tcp_congestion_control":
            avail = self.sysctls.get("net.ipv4.tcp_available_congestion_control", "").split()
            if value not in avail:
                return False, f"cc {value} unavailable"
        self.sysctls[key] = str(value)
        return True, ""

    def get_ram_mb(self) -> int:
        return self.ram_mb

    def get_cpu_count(self) -> int:
        return self.cpus

    def run(self, argv: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
        if not argv:
            return 1, "", "empty"
        cmd = argv[0]
        if cmd == "sysctl":
            if len(argv) >= 2 and argv[1] == "--system":
                return 0, "", ""
            return 0, "", ""
        if cmd == "ip":
            return self._mock_ip(argv[1:])
        if cmd == "tc":
            return self._mock_tc(argv[1:])
        if cmd == "ethtool":
            return self._mock_ethtool(argv[1:])
        if cmd in ("iptables", "ip6tables"):
            return self._mock_iptables(argv)
        if cmd == "systemctl":
            self.systemd_cmds.append(list(argv))
            return 0, "active", ""
        return 0, "", ""

    def _mock_ip(self, args: list[str]) -> tuple[int, str, str]:
        joined = " ".join(args)
        if joined.startswith("-6 addr show") or (args[:2] == ["addr", "show"]):
            if self.ipv6_active and "-6" in args:
                return 0, f"2: {self.iface} inet6 2001:db8::1/64 scope global", ""
            return 0, f"2: {self.iface} inet 192.0.2.10/24 scope global {self.iface}", ""
        if args[:2] == ["route", "get"] or args[:3] == ["route", "show", "default"]:
            return 0, self.route_line, ""
        if args[:2] == ["route", "change"]:
            if "route" in self.unsupported_ops:
                return 2, "", "RTNETLINK answers: Operation not supported"
            parts = args[2:]
            base = re.sub(r"\s+(?:initcwnd|initrwnd|advmss)\s+\d+", "", self.route_line)
            extras = []
            for k in ("initcwnd", "initrwnd", "advmss"):
                if k in parts:
                    idx = parts.index(k)
                    if idx + 1 < len(parts):
                        extras.append(f"{k} {parts[idx + 1]}")
            self.route_line = base + (" " + " ".join(extras) if extras else "")
            return 0, "", ""
        if args[:3] == ["link", "show", "dev"]:
            return 0, f"2: {self.iface}: <BROADCAST,MULTICAST,UP> mtu {self.mtu} qdisc mq state UP qlen {self.txqueuelen}", ""
        if args[:2] == ["link", "set"]:
            if "mtu" in args:
                idx = args.index("mtu")
                self.mtu = int(args[idx + 1])
            if "txqueuelen" in args:
                idx = args.index("txqueuelen")
                self.txqueuelen = int(args[idx + 1])
            return 0, "", ""
        return 0, "", ""

    def _mock_tc(self, args: list[str]) -> tuple[int, str, str]:
        if args[:2] == ["qdisc", "show"]:
            return 0, self.qdisc_line, ""
        if args[:2] == ["qdisc", "replace"]:
            if "qdisc" in self.unsupported_ops:
                return 2, "", "Error: Specified qdisc not found."
            kind = args[args.index("root") + 1] if "root" in args else "fq"
            if kind not in self.available_qdisc and kind not in ("default", "pfifo_fast"):
                return 2, "", f"Specified qdisc {kind} not found."
            tail = " ".join(args[args.index("root") + 2:]) if "root" in args else ""
            self.qdisc_line = f"qdisc {kind} 0: root refcnt 2 {tail}".strip()
            return 0, "", ""
        return 0, "", ""

    def _mock_ethtool(self, args: list[str]) -> tuple[int, str, str]:
        if args[0] == "-i":
            return 0, "driver: virtio_net\nversion: 1.0.0\n", ""
        if args[0] == "-k":
            lines = [f"tcp-segmentation-offload: {'on' if self.offloads.get('tso') else 'off'}",
                     f"generic-segmentation-offload: {'on' if self.offloads.get('gso') else 'off'}",
                     f"generic-receive-offload: {'on' if self.offloads.get('gro') else 'off'}",
                     f"large-receive-offload: {'on' if self.offloads.get('lro') else 'off'}"]
            return 0, "\n".join(lines), ""
        if args[0] == "-K":
            if "offloads" in self.unsupported_ops:
                return 1, "", "Operation not supported"
            for i in range(2, len(args) - 1, 2):
                k, v = args[i], args[i + 1]
                if k in self.offloads:
                    self.offloads[k] = (v == "on")
            return 0, "", ""
        return 0, "", ""

    def _mock_iptables(self, argv: list[str]) -> tuple[int, str, str]:
        if "-S" in argv:
            return 0, "-P POSTROUTING ACCEPT\n" + "\n".join(self.iptables_mangle), ""
        if "-A" in argv or "-I" in argv:
            idx = argv.index("-A") if "-A" in argv else argv.index("-I")
            rule = "-A " + " ".join(argv[idx + 1:])
            self.iptables_mangle.append(rule)
            return 0, "", ""
        if "-D" in argv:
            idx = argv.index("-D")
            target = " ".join(argv[idx + 1:])
            self.iptables_mangle = [r for r in self.iptables_mangle if target not in r]
            return 0, "", ""
        return 0, "", ""


def _detect_out_route(driver: SysDriver, peer_ip: str) -> tuple[str, str]:
    rc, out, _ = driver.run(["ip", "route", "get", peer_ip] if peer_ip else ["ip", "route", "show", "default"])
    if rc != 0 or not out.strip():
        rc, out, _ = driver.run(["ip", "route", "show", "default"])
    line = (out.splitlines()[0] if out else "").strip()
    m = re.search(r"\bdev\s+(\S+)", line)
    iface = m.group(1) if m else "eth0"
    return iface, line


def _check_ipv6_active(driver: SysDriver, iface: str) -> bool:
    rc, out, _ = driver.run(["ip", "-6", "addr", "show", "dev", iface])
    return rc == 0 and "inet6 " in (out or "") and "global" in (out or "")


def discover_capabilities(driver: SysDriver, peer_ip: str = "") -> dict:
    """Inspect kernel, CPU/RAM, virtualization, NIC, CC, qdiscs, and installed cores."""
    iface, route_line = _detect_out_route(driver, peer_ip)
    ipv6_active = _check_ipv6_active(driver, iface)
    cc_raw = driver.read_sysctl("net.ipv4.tcp_available_congestion_control") or ""
    avail_cc = [c for c in cc_raw.split() if c]

    nic_driver = "unknown"
    has_ethtool = bool(driver.which("ethtool"))
    if has_ethtool:
        rc, et_out, _ = driver.run(["ethtool", "-i", iface])
        if rc == 0:
            m = re.search(r"driver:\s*(\S+)", et_out)
            if m:
                nic_driver = m.group(1)

    avail_qdisc = []
    has_tc = bool(driver.which("tc"))
    for qname in ("fq", "fq_codel", "cake"):
        if hasattr(driver, "available_qdisc"):
            if qname in driver.available_qdisc:
                avail_qdisc.append(qname)
        else:
            if driver.file_exists(f"/lib/modules/{platform.release()}/kernel/net/sched/sch_{qname}.ko"):
                avail_qdisc.append(qname)
            elif qname in ("fq", "fq_codel"):
                avail_qdisc.append(qname)

    virt = "unknown"
    dmi = (driver.read_text("/sys/class/dmi/id/sys_vendor") or "").lower()
    if "qemu" in dmi or "kvm" in dmi or "red hat" in dmi:
        virt = "kvm"
    elif "vmware" in dmi:
        virt = "vmware"
    elif "microsoft" in dmi:
        virt = "hyperv"
    elif driver.file_exists("/proc/vz"):
        virt = "openvz"

    cores = {}
    for b in ("rathole", "kcptun-server", "kcptun-client", "backhaul-server", "backhaul-client", "frps", "frpc", "paqet", "xray", "nginx"):
        cores[b] = bool(driver.which(b))

    return {
        "kernel": platform.release(),
        "cpus": driver.get_cpu_count(),
        "ram_mb": driver.get_ram_mb(),
        "virt": virt,
        "iface": iface,
        "route_line": route_line,
        "ipv6_active": ipv6_active,
        "nic_driver": nic_driver,
        "available_cc": avail_cc,
        "available_qdisc": sorted(set(avail_qdisc)),
        "has_ethtool": has_ethtool,
        "has_tc": has_tc,
        "has_iptables": bool(driver.which("iptables")),
        "installed_cores": cores,
    }


def _parse_offloads(driver: SysDriver, iface: str) -> dict:
    rc, out, _ = driver.run(["ethtool", "-k", iface])
    if rc != 0:
        return {}
    mapping = {
        "tcp-segmentation-offload": "tso",
        "generic-segmentation-offload": "gso",
        "generic-receive-offload": "gro",
        "large-receive-offload": "lro",
    }
    res = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = [p.strip() for p in line.split(":", 1)]
        if k in mapping and (v.startswith("on") or v.startswith("off")):
            res[mapping[k]] = v.startswith("on")
    return res


def _parse_route_params(route_line: str) -> dict:
    out = {}
    for key in ("initcwnd", "initrwnd", "advmss"):
        m = re.search(rf"\b{key}\s+(\d+)", route_line or "")
        if m:
            out[key] = int(m.group(1))
    return out


def capture_snapshot(driver: SysDriver, iface: str = "", peer_ip: str = "", save_path: str | None = None) -> dict:
    """Capture complete reversible baseline snapshot of sysctls, MTU, route, qdisc, and offloads."""
    det_iface, route_line = _detect_out_route(driver, peer_ip)
    target_iface = iface or det_iface

    mtu = 1500
    txq = 1000
    rc, link_out, _ = driver.run(["ip", "link", "show", "dev", target_iface])
    if rc == 0:
        m = re.search(r"\bmtu\s+(\d+)", link_out)
        if m:
            mtu = int(m.group(1))
        m_q = re.search(r"\bqlen\s+(\d+)", link_out)
        if m_q:
            txq = int(m_q.group(1))

    _, qd_out, _ = driver.run(["tc", "qdisc", "show", "dev", target_iface])
    qd_kind = "fq_codel"
    m_qd = re.search(r"qdisc\s+([A-Za-z0-9_]+)\s+\S+\s+root", qd_out or "")
    if m_qd:
        qd_kind = m_qd.group(1)

    sysctls = {}
    for k in BASE_SNAPSHOT_SYSCTLS:
        val = driver.read_sysctl(k)
        if val is not None:
            sysctls[k] = val

    snap = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "iface": target_iface,
        "peer_ip": peer_ip,
        "mtu": mtu,
        "txqueuelen": txq,
        "qdisc": {"kind": qd_kind, "raw": (qd_out or "").strip()},
        "route": _parse_route_params(route_line),
        "route_line": route_line,
        "offloads": _parse_offloads(driver, target_iface),
        "sysctl": sysctls,
    }
    if save_path:
        driver.write_text(save_path, json.dumps(snap, indent=2) + "\n", mode=0o600)
    return snap


def _sweep_mangle_rules(driver: SysDriver, session_id: str) -> None:
    tag = f"rathole-tuner-{session_id}"
    for ipt in ("iptables", "ip6tables"):
        if not driver.which(ipt):
            continue
        rc, out, _ = driver.run([ipt, "-t", "mangle", "-S", "POSTROUTING"])
        if rc != 0:
            continue
        for line in out.splitlines():
            if line.startswith("-A ") and tag in line:
                toks = [t.strip('"') for t in line[3:].split()]
                if toks:
                    driver.run([ipt, "-t", "mangle", "-D"] + toks)


def _strip_route_target(route_line: str) -> list[str]:
    cleaned = re.sub(r"\s+(?:initcwnd|initrwnd|advmss)\s+\d+", "", route_line or "").strip()
    cleaned = re.sub(r"\s+src\s+\S+", "", cleaned)
    cleaned = re.sub(r"\s+uid\s+\d+", "", cleaned)
    return [t for t in cleaned.split() if t]


def apply_candidate(
    driver: SysDriver,
    config: dict,
    iface: str,
    peer_ip: str = "",
    session_id: str = "tuner",
    ram_mb: int | None = None,
    ipv6_active: bool | None = None,
) -> dict:
    """Apply validated candidate configuration safely with RAM cap, MTU floor, and tracking."""
    ram = ram_mb if ram_mb is not None else driver.get_ram_mb()
    v6 = _check_ipv6_active(driver, iface) if ipv6_active is None else bool(ipv6_active)
    cfg = clamp_config_for_ram(config or {}, ram)
    applied = []
    unsupported = []
    errors = []

    if cfg.get("mtu") is not None:
        mtu_floor = 1280 if v6 else 576
        target_mtu = max(mtu_floor, min(1500, int(cfg["mtu"])))
        rc, _, err = driver.run(["ip", "link", "set", "dev", iface, "mtu", str(target_mtu)])
        if rc == 0:
            applied.append(f"mtu={target_mtu}")
        else:
            unsupported.append(f"mtu:{err.strip()}")

    if cfg.get("txqueuelen") is not None:
        txq = max(100, min(20000, int(cfg["txqueuelen"])))
        rc, _, err = driver.run(["ip", "link", "set", "dev", iface, "txqueuelen", str(txq)])
        if rc == 0:
            applied.append(f"txqueuelen={txq}")
        else:
            unsupported.append(f"txqueuelen:{err.strip()}")

    qd = cfg.get("qdisc")
    if isinstance(qd, dict) and qd.get("kind"):
        kind = qd["kind"]
        if kind in ("default", "pfifo_fast"):
            cmd = ["tc", "qdisc", "replace", "dev", iface, "root", "pfifo_fast"]
        else:
            cmd = ["tc", "qdisc", "replace", "dev", iface, "root", kind]
            bw = (qd.get("params") or {}).get("bandwidth_mbps")
            if kind == "cake" and bw:
                cmd += ["bandwidth", f"{int(bw)}mbit", "besteffort"]
        rc, _, err = driver.run(cmd)
        if rc == 0:
            applied.append(f"qdisc={kind}")
        else:
            unsupported.append(f"qdisc:{kind}:{err.strip()}")

    offs = cfg.get("offloads")
    if isinstance(offs, dict) and offs and driver.which("ethtool"):
        args = ["ethtool", "-K", iface]
        for k, v in offs.items():
            args += [k, "on" if v else "off"]
        rc, _, err = driver.run(args)
        if rc == 0:
            applied.append("offloads")
        else:
            unsupported.append(f"offloads:{err.strip()}")

    rt = cfg.get("route")
    if isinstance(rt, dict) and rt:
        _, route_line = _detect_out_route(driver, peer_ip)
        base_toks = _strip_route_target(route_line)
        if base_toks:
            cmd = ["ip", "route", "change"] + base_toks
            for rk in ("initcwnd", "initrwnd", "advmss"):
                if rt.get(rk):
                    cmd += [rk, str(int(rt[rk]))]
            rc, _, err = driver.run(cmd)
            if rc == 0:
                applied.append("route")
            else:
                unsupported.append(f"route:{err.strip()}")

    _sweep_mangle_rules(driver, session_id)
    mss = int(cfg.get("mss_clamp") or 0)
    if mss > 0 and driver.which("iptables"):
        tag = f"rathole-tuner-{session_id}"
        rc, _, err = driver.run([
            "iptables", "-t", "mangle", "-I", "POSTROUTING", "1",
            "-o", iface, "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN",
            "-m", "comment", "--comment", tag,
            "-j", "TCPMSS", "--set-mss", str(mss),
        ])
        if rc == 0:
            applied.append(f"mss_clamp={mss}")
        else:
            unsupported.append(f"mss_clamp:{err.strip()}")

    sysctls = cfg.get("sysctl") or {}
    ordered_keys = sorted(sysctls.keys(), key=lambda k: (0 if "qdisc" in k else 1, k))
    for k in ordered_keys:
        ok, err = driver.write_sysctl(k, str(sysctls[k]))
        if ok:
            applied.append(f"{k}={sysctls[k]}")
        else:
            unsupported.append(f"{k}:{err}")

    return {"applied": applied, "unsupported": unsupported, "errors": errors}


def restore_snapshot(driver: SysDriver, snapshot: dict, session_id: str = "tuner") -> dict:
    """Restore system configuration back to pre-flight snapshot."""
    if not snapshot:
        return {"ok": False, "detail": "empty snapshot"}
    iface = snapshot.get("iface", "eth0")
    _sweep_mangle_rules(driver, session_id)

    for k, v in sorted((snapshot.get("sysctl") or {}).items()):
        driver.write_sysctl(k, str(v))

    if snapshot.get("mtu"):
        driver.run(["ip", "link", "set", "dev", iface, "mtu", str(int(snapshot["mtu"]))])
    if snapshot.get("txqueuelen"):
        driver.run(["ip", "link", "set", "dev", iface, "txqueuelen", str(int(snapshot["txqueuelen"]))])

    qd = (snapshot.get("qdisc") or {}).get("kind")
    if qd:
        driver.run(["tc", "qdisc", "replace", "dev", iface, "root", qd])

    offs = snapshot.get("offloads") or {}
    if offs and driver.which("ethtool"):
        args = ["ethtool", "-K", iface]
        for k, v in offs.items():
            args += [k, "on" if v else "off"]
        driver.run(args)

    base_toks = _strip_route_target(snapshot.get("route_line", ""))
    rt = snapshot.get("route") or {}
    if base_toks:
        cmd = ["ip", "route", "change"] + base_toks
        for rk in ("initcwnd", "initrwnd", "advmss"):
            if rk in rt:
                cmd += [rk, str(int(rt[rk]))]
        if len(cmd) > 3 + len(base_toks):
            driver.run(cmd)
    return {"ok": True}


def read_tcp_info(sock: socket.socket) -> dict:
    """Read Linux getsockopt(TCP_INFO) counters safely; empty dict on non-Linux/errors."""
    if not hasattr(socket, "TCP_INFO"):
        return {}
    try:
        raw = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 256)
        if len(raw) < 104:
            return {}
        # Standard Linux struct tcp_info offsets (u8*8 + u32*24 prefix)
        fields = struct.unpack_from("=8B24I", raw, 0)
        return {
            "state": fields[0],
            "retransmits": fields[2],
            "rto_us": fields[8],
            "snd_mss": fields[11],
            "rcv_mss": fields[12],
            "rtt_ms": round(fields[23] / 1000.0, 3),
            "rttvar_ms": round(fields[24] / 1000.0, 3),
            "snd_cwnd": fields[26],
            "pmtu": fields[22],
            "total_retrans": fields[31],
        }
    except OSError:
        return {}


def read_net_counters(driver: SysDriver, iface: str) -> dict:
    """Read kernel Tcp RetransSegs/OutSegs from /proc/net/snmp and NIC drop counters."""
    snmp = driver.read_text("/proc/net/snmp") or ""
    out_segs = 0
    retrans_segs = 0
    lines = snmp.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("Tcp:") and idx + 1 < len(lines) and lines[idx + 1].startswith("Tcp:"):
            hdr = line.split()
            vals = lines[idx + 1].split()
            if len(hdr) == len(vals):
                mp = dict(zip(hdr, vals))
                out_segs = int(mp.get("OutSegs", 0) or 0)
                retrans_segs = int(mp.get("RetransSegs", 0) or 0)
            break

    tx_drop = int((driver.read_text(f"/sys/class/net/{iface}/statistics/tx_dropped") or "0").strip() or 0)
    rx_drop = int((driver.read_text(f"/sys/class/net/{iface}/statistics/rx_dropped") or "0").strip() or 0)
    return {
        "out_segs": out_segs,
        "retrans_segs": retrans_segs,
        "tx_dropped": tx_drop,
        "rx_dropped": rx_drop,
    }
