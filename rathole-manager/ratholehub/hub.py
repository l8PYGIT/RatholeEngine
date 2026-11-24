#!/usr/bin/env python3
# ratholehub — panel mrkzi mdirit tunnel rathole/kcp (REST API + UI)
# - bedoon vabstgi pip (fght stdlib)
# - pshtshnh: ejra-ye ratholectl/ratholenode rooye serverha az trigh SSH (kelid)
# - rooye 127.0.0.1 mishnvd; nginx zir damnhi TLS srvsh midahad (yek port/yek damnh hefz mishavad)
#
# tanzimat:  /etc/ratholehub/config.json   , inventory: /etc/ratholehub/inventory.json
# mtghirhai mhiti baraye tst lvkal: RATHOLEHUB_CONF, RATHOLEHUB_INV, RATHOLEHUB_MOCK=1
import os, sys, json, hmac, hashlib, time, subprocess, re, secrets, threading, shlex, shutil, traceback, ipaddress, tempfile


from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import urllib.request

CONF_PATH = os.environ.get("RATHOLEHUB_CONF", "/etc/ratholehub/config.json")
INV_PATH  = os.environ.get("RATHOLEHUB_INV",  "/etc/ratholehub/inventory.json")
MOCK      = os.environ.get("RATHOLEHUB_MOCK") == "1"
AUDIT_PATH = os.environ.get("RATHOLEHUB_AUDIT", "/etc/ratholehub/audit.log")
MON_CONF_PATH = os.environ.get("RATHOLEMON_CONF", "/etc/ratholehub/monitor.json")

# ---------- tanzimat va inventory ----------
# RLock (na Lock) ta helper-haye atomic betavanand read-modify-write ra yekja
# ghofl konand va daroon-esh save_config/set_inventory (ke khodeshan ghofl migirand) seda bezanand.
_lock = threading.RLock()

# mhdvdsazi nrkhe tlashe vrvd (zde brute-force). kelid = IP.
_LOGIN_FAILS = {}
_LOGIN_MAX = 5            # hdaksr tlashe namvfgh
_LOGIN_WINDOW = 300       # pnjrhi sanihai
_login_lock = threading.Lock()
_metrics_lock = threading.Lock()
_OVERVIEW_CACHE = {}
_LAST_DRIFT_SUMMARY = None
_LOGIN_FAILS_TOTAL = 0
_HTTP_REQS = {"GET": 0, "POST": 0, "PUT": 0, "DELETE": 0}

def _prune_login_fails(now):
    # Prune expired entries to prevent memory leaks from scan traffic
    expired = [ip for ip, fails in _LOGIN_FAILS.items() if not fails or now - fails[-1] >= _LOGIN_WINDOW]
    for ip in expired:
        _LOGIN_FAILS.pop(ip, None)

def login_allowed(ip):
    now = time.time()
    with _login_lock:
        _prune_login_fails(now)
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW]
        if fails:
            _LOGIN_FAILS[ip] = fails
        else:
            _LOGIN_FAILS.pop(ip, None)
        return len(fails) < _LOGIN_MAX

def login_record_fail(ip):
    global _LOGIN_FAILS_TOTAL
    now = time.time()
    with _login_lock:
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW]
        fails.append(now)
        _LOGIN_FAILS[ip] = fails
        if len(_LOGIN_FAILS) > 500:
            _prune_login_fails(now)
    with _metrics_lock:
        _LOGIN_FAILS_TOTAL += 1

def login_reset(ip):
    with _login_lock:
        _LOGIN_FAILS.pop(ip, None)

def _hash_password(pw):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 200000)
    return "pbkdf2_sha256$%s$%s" % (salt.hex(), dk.hex())

def _verify_password(pw, stored):
    if not isinstance(stored, str) or not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        parts = stored.split("$")
        if len(parts) != 3:
            return False
        try:
            salt = bytes.fromhex(parts[1])
            expected = bytes.fromhex(parts[2])
        except ValueError:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 200000)
        return hmac.compare_digest(dk, expected)
    return hmac.compare_digest(hashlib.sha256(pw.encode("utf-8")).hexdigest(), stored)

# mghadir pishfrze naamn ke hrgz nbaid dar mohit vaghai estefade shavand.
_INSECURE_TOKEN = "changeme"
_INSECURE_PW_SHA = hashlib.sha256(b"admin").hexdigest()

def load_json(path, default):
    """khvandn JSON. fght "nbvde file" bhsvrt default brmigrdd;
    faile khrab/ghirghablkhvandn khata midahad ta ba kanfige pishfrze naamn ejra nshvim."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        raise RuntimeError("khvandn %s shekast khord (file khrab ya bedoon dstrsi?): %s" % (path, e))


def save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, path)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
def _strip_ansi(s):
    return _ANSI.sub("", s or "")

def get_config():
    cfg = load_json(CONF_PATH, {
        "api_token": _INSECURE_TOKEN,
        "admin_password_sha256": _INSECURE_PW_SHA,
        "listen_host": "127.0.0.1", "listen_port": 8088,
        "proxy": "",
        "ssh_key_path": "", "ssh_opts": ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                                          "-o", "StrictHostKeyChecking=accept-new"],
        "bundle_dir": "/opt/ratholehub/bundle",
    })
    cfg["_insecure"] = (cfg.get("api_token") == _INSECURE_TOKEN
                        or cfg.get("admin_password_sha256") == _INSECURE_PW_SHA)
    return cfg

def get_proxy(server=None):
    if server and server.get("proxy"):
        p = str(server.get("proxy", "")).strip()
        return "" if p.lower() in ("direct", "none", "off") else p
    cfg = get_config()
    p = str(cfg.get("proxy", "")).strip()
    return "" if p.lower() in ("direct", "none", "off") else p

def get_inventory():
    inv = load_json(INV_PATH, [])
    return inv if isinstance(inv, list) else []

def set_inventory(inv):
    with _lock:
        save_json(INV_PATH, inv)

def update_inventory(mutator):
    # read-modify-write-e atomic: kolle chrkhe zir-e _lock ta do darkhast-e hamzaman
    # (ThreadingHTTPServer) update-e hamdigar ra pak nakonand. mutator(inv) -> inv-e jadid.
    with _lock:
        inv = get_inventory()
        new_inv = mutator(inv)
        if new_inv is not None:
            save_json(INV_PATH, new_inv)
        return new_inv

def save_config(cfg):
    # fildhai dakhli (ba _ shrva) zkhirh nmishvnd.
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with _lock:
        save_json(CONF_PATH, clean)
        try:
            os.chmod(CONF_PATH, 0o600)
        except Exception:
            pass

def update_config(mutator):
    # read-modify-write-e atomic baraye config (mesl update_inventory).
    with _lock:
        cfg = get_config()
        new_cfg = mutator(cfg)
        save_config(new_cfg if new_cfg is not None else cfg)
        return new_cfg if new_cfg is not None else cfg

def _redact_cmd_for_audit(action, cmd):
    parts = list(cmd)
    if action == "add_svc" and len(parts) > 3:
        parts[3] = "***REDACTED***"
    elif action == "add_bh_svc" and len(parts) > 4:
        parts[4] = "***REDACTED***"
    elif action == "upstream_add_svc" and len(parts) > 5:
        parts[5] = "***REDACTED***"
    elif action == "kcp_on" and len(parts) > 4:
        parts[4] = "***REDACTED***"
    elif action == "upstream_kcp_on" and len(parts) > 6:
        parts[6] = "***REDACTED***"
    elif action == "backhaul_on" and parts and parts[0] == "ratholenode" and len(parts) > 4:
        parts[4] = "***REDACTED***"
    elif action == "frp_on" and len(parts) > 4:
        if parts[0] == "ratholenode" or parts[4] not in ("tcp", "kcp", "quic", "websocket"):
            parts[4] = "***REDACTED***"
    elif action == "paqet_on" and parts:
        if parts[0] == "ratholectl" and len(parts) > 4:
            parts[4] = "***REDACTED***"
        elif parts[0] == "ratholenode" and len(parts) > 4 and not parts[4].startswith("--"):
            parts[4] = "***REDACTED***"
    elif action == "xray_setup":
        for i in range(1, len(parts)):
            if parts[i] in ("--private-key", "--uuid") and i + 1 < len(parts):
                parts[i + 1] = "***REDACTED***"
            elif parts[i].startswith("--private-key="):
                parts[i] = "--private-key=***REDACTED***"
            elif parts[i].startswith("--uuid="):
                parts[i] = "--uuid=***REDACTED***"
    return " ".join(parts)

def _redact_proxy_creds(proxy):
    p = str(proxy or "").strip()
    if not p:
        return ""
    try:
        parsed = urlparse(p)
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://***@{host}{port}"
    except Exception:
        pass
    return p

def _public_server(s):
    out = {k: v for k, v in s.items() if k != "api_token"}
    if s.get("transport") == "api":
        out["api_token_set"] = bool(s.get("api_token"))
    if "proxy" in out:
        out["proxy"] = _redact_proxy_creds(out["proxy"])
    return out

def audit_log(user, server, action, cmd, rc):
    # sbte append-only ba SHA-256 hash chain az har amliate nvshtari baraye rdgiri va tashkhis-e dastkari.
    try:
        d = os.path.dirname(AUDIT_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        with _lock:
            prev = last_audit_hash(AUDIT_PATH)
            entry = build_chained_audit_entry(user, server, action, cmd, rc, prev)
            line = json.dumps(entry, ensure_ascii=False)
            fd = os.open(AUDIT_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass  # log nbaid masir asli ra bshknd

def read_audit(limit=100):
    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        out.reverse()
        return out
    except FileNotFoundError:
        return []
    except Exception:
        return []

# ---------- vaziat-e khod-e server-e hub (uptime/load/mem/disk/serviceha) ----------
_HUB_START = time.time()

# noskhe-i ke hub «akharin» midanad: az MANAGER_VERSION-e common.sh (bundle ke deploy mishavad)
# khande mishavad ta ba noskhe-ye nasb-shode rooye har server moghayese shavad. fallback: rشته-ye sabet.
HUB_FALLBACK_VERSION = "1.4.7"
def hub_manager_version():
    cands = []
    try:
        cands.append(os.path.join(get_config().get("bundle_dir", ""), "rathole-manager", "common.sh"))
        cands.append(os.path.join(get_config().get("bundle_dir", ""), "common.sh"))
    except Exception:
        pass
    cands += ["/opt/ratholehub/bundle/rathole-manager/common.sh",
              "/usr/local/bin/common.sh", "/etc/rathole-manager/common.sh"]
    for p in cands:
        try:
            if p and os.path.isfile(p):
                with open(p, encoding="utf-8", errors="ignore") as f:
                    m = re.search(r'^\s*MANAGER_VERSION="?([^"\s]+)"?', f.read(), re.M)
                    if m:
                        return m.group(1)
        except Exception:
            continue
    return HUB_FALLBACK_VERSION

def hub_status():
    # hame-ye bakhsh-ha best-effort hastand; rooye system-haye bedoon /proc ya systemctl
    # (masalan test-e local rooye Windows/Mac) faghat field-haye mojood barmigardand.
    st = {"time": int(time.time()), "mock": MOCK,
          "hub_uptime": int(time.time() - _HUB_START),
          "python": "%d.%d.%d" % sys.version_info[:3]}
    try:
        with open("/proc/uptime") as f:
            st["uptime"] = int(float(f.read().split()[0]))
    except Exception:
        pass
    try:
        st["load"] = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass
    try:
        mi = {}
        with open("/proc/meminfo") as f:
            for ln in f:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    mi[k.strip()] = int(v.strip().split()[0])
        if mi.get("MemTotal"):
            st["mem_total_kb"] = mi["MemTotal"]
            st["mem_avail_kb"] = mi.get("MemAvailable", 0)
    except Exception:
        pass
    try:
        du = shutil.disk_usage("/")
        st["disk_total"] = du.total
        st["disk_free"] = du.free
    except Exception:
        pass
    svcs = {}
    if shutil.which("systemctl"):
        for u in ("ratholehub", "nginx"):
            try:
                r = subprocess.run(["systemctl", "is-active", u],
                                   capture_output=True, text=True, timeout=5)
                svcs[u] = (r.stdout or "").strip() or "unknown"
            except Exception:
                svcs[u] = "unknown"
    st["services"] = svcs
    st["latest_version"] = hub_manager_version()
    st["proxy"] = get_config().get("proxy", "")
    return st

# ---------- aatbarsnji vrvdi + whitelist dstvrha ----------
# in bakhsh be hubcmds.py montaghel shod (file-e kuchak va ghabel-e morur, bedoon vabastegi
# be baghi-ye hub) — ba `from hubcmds import *` haman nam-ha dar in namespace mimanand
# ta baghi-ye kod (va test-ha) bedoon taghir kar konand.
from hubcmds import (  # noqa: F401  (nam-ha dar sartasar-e hub estefade mishavand)
    RE_NAME, RE_HOST, RE_PORT, RE_PROFILE, RE_IPPORT, RE_KEY, RE_B64, RE_ID, RE_PW,
    RE_EMAIL, RE_PATH, RE_SLUG, RE_HEADER, RE_BH_SRV, RE_BH_CLI, RE_BH_TOK, RE_CHAN,
    RE_COUNT, build_iran_cmd, build_node_cmd, build_cmd, WRITE_ACTIONS, _diag,
)
from hubdiag import compute_fleet_drift, synthesize_link_test
from hubsec import (
    SCOPES, scope_allows, create_scoped_token, public_token_view,
    resolve_auth, check_csrf, generate_totp_secret, verify_totp,
    totp_provisioning_uri, generate_recovery_codes, consume_recovery_code,
    last_audit_hash, build_chained_audit_entry, verify_audit_chain,
    render_prometheus_metrics,
)
from tg_relay import diagnose_relay, TelegramRelayManager, TelegramClient, redact_secrets
import hubupdate
from monitor import (
    load_monitor_config, save_monitor_config, validate_monitor_update,
    public_monitor_config,
)

# ---------- ejra-ye az rah dvr (Agent API ya SSH) ----------
def _norm_agent_url(url):
    u = (url or "").strip().rstrip("/")
    low = u.lower()
    if low.startswith("https://"):
        return "https://" + u[8:]
    if low.startswith("http://"):
        return "http://" + u[7:]
    return ("http://" + u) if u else ""

def build_agent_request(server, cmd_args, timeout=120):
    url = _norm_agent_url(server.get("api_url"))
    url = url + "/api/exec"
    token = server.get("api_token", "")
    payload = json.dumps({"cmd": cmd_args, "timeout": timeout}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    return urllib.request.Request(url, data=payload, headers=headers)

def valid_proxy_url(value):
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or v.lower() in ("direct", "none", "off"):
        return True
    if any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() or ch in "'\"`$;|&><()\\" for ch in v):
        return False
    try:
        parsed = urlparse(v)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname:
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    return parsed.path in ("", "/") and not parsed.query and not parsed.fragment

_SAFE_SSH_OPT_KV = re.compile(
    r"^(?:BatchMode=(?:yes|no)"
    r"|ConnectTimeout=([1-9][0-9]{0,2})"
    r"|StrictHostKeyChecking=(?:accept-new|yes|no)"
    r"|ServerAliveInterval=([1-9][0-9]{0,2})"
    r"|ServerAliveCountMax=([1-9][0-9]?)"
    r"|IdentitiesOnly=(?:yes|no))$"
)

def _valid_ssh_kv(kv):
    m = _SAFE_SSH_OPT_KV.match(kv)
    if not m:
        return False
    if m.group(1) and not (1 <= int(m.group(1)) <= 300):
        return False
    if m.group(2) and not (1 <= int(m.group(2)) <= 300):
        return False
    if m.group(3) and not (1 <= int(m.group(3)) <= 20):
        return False
    return True

def valid_ssh_opts(opts):
    if not isinstance(opts, list) or not all(isinstance(x, str) for x in opts):
        return False
    i = 0
    while i < len(opts):
        item = opts[i]
        if any(ord(ch) < 32 for ch in item):
            return False
        if item == "-o":
            if i + 1 >= len(opts) or not _valid_ssh_kv(opts[i + 1]):
                return False
            i += 2
        elif item.startswith("-o") and len(item) > 2:
            if not _valid_ssh_kv(item[2:]):
                return False
            i += 1
        else:
            return False
    return True

def valid_ssh_key_path(path):
    if path == "":
        return True
    if not isinstance(path, str) or any(ord(ch) < 32 for ch in path):
        return False
    norm = path.replace("\\", "/")
    if not norm.startswith("/") or ".." in norm.split("/"):
        return False
    if not re.fullmatch(r"/[A-Za-z0-9_./-]{1,255}", norm):
        return False
    cand = os.path.realpath(path)
    allowed_roots = [os.path.realpath("/etc/ratholehub"), os.path.realpath("/root/.ssh")]
    home_ssh = os.path.realpath(os.path.expanduser("~/.ssh"))
    if home_ssh not in allowed_roots:
        allowed_roots.append(home_ssh)
    conf_dir = os.path.realpath(os.path.dirname(os.path.abspath(CONF_PATH)))
    disallowed = {os.path.realpath(p) for p in ("/", "/dev", "/tmp", "/etc")}
    if conf_dir not in disallowed:
        allowed_roots.append(conf_dir)
    for root in allowed_roots:
        try:
            if os.path.commonpath([cand, root]) == root and cand != root:
                return True
        except ValueError:
            continue
    return False

def valid_agent_url(value):
    try:
        parsed = urlparse(value)
        return (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                and parsed.port != 0 and not parsed.username and not parsed.password
                and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
                and not any(ord(ch) < 32 for ch in value))
    except ValueError:
        return False

def run_on_agent(server, cmd_args, timeout=120):
    proxy = get_proxy(server)
    handlers = []
    if proxy:
        if proxy.lower().startswith("socks"):
            return {"rc": 1, "out": "", "err": "SOCKS5 proxy is not supported by urllib for Agent API; use HTTP proxy or direct"}
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    url = _norm_agent_url(server.get("api_url"))
    if url.startswith("https://"):
        import ssl
        ctx = ssl.create_default_context()
        if server.get("insecure_ssl") or os.environ.get("RATHOLE_AGENT_INSECURE_SSL") == "1":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    req = build_agent_request(server, cmd_args, timeout=timeout)
    try:
        with opener.open(req, timeout=timeout + 5) as resp:
            data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8"))
            return {
                "rc": data.get("rc", 0),
                "out": _strip_ansi(data.get("out", "")),
                "err": _strip_ansi(data.get("err", ""))
            }
    except urllib.error.HTTPError as e:
        err_msg = ""
        try:
            err_data = json.loads(e.read(65536).decode("utf-8"))
            err_msg = err_data.get("error", "")
        except Exception:
            err_msg = str(e)
        return {"rc": e.code, "out": "", "err": f"HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": f"Agent connection error: {e}"}

def run_on_server(server, cmd_args, timeout=120):
    if MOCK:
        return mock_run(server, cmd_args)
    if server.get("transport") == "api":
        return run_on_agent(server, cmd_args, timeout=timeout)
    cfg = get_config()
    ssh = _ssh_base(cfg, server) + [shlex.join(cmd_args)]  # hefz-e argv dar shell-e remote
    try:
        p = subprocess.run(ssh, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": _strip_ansi(p.stdout), "err": _strip_ansi(p.stderr)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "SSH timeout"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}

def _ssh_base(cfg, server):
    raw_opts = cfg.get("ssh_opts", [])
    if not valid_ssh_opts(raw_opts):
        raise ValueError("invalid ssh_opts")
    ssh = ["ssh"] + list(raw_opts)
    proxy = get_proxy(server)
    if proxy:
        if not valid_proxy_url(proxy):
            raise ValueError("invalid proxy URL")
        bridge_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "ssh_proxy.py"))
        py_bin = sys.executable or "python3"
        ssh += ["-o", f"ProxyCommand={shlex.quote(py_bin)} {shlex.quote(bridge_script)} {shlex.quote(proxy)} %h %p"]
    if cfg.get("ssh_key_path"):
        if not valid_ssh_key_path(cfg["ssh_key_path"]):
            raise ValueError("invalid ssh_key_path")
        ssh += ["-i", cfg["ssh_key_path"]]
    ssh += ["-p", str(server.get("ssh_port", 22)),
            "%s@%s" % (server.get("ssh_user", "root"), server["host"]), "--"]
    return ssh

def iran_main_server(s):
    # maghsad-e daghigh-e tunnel-e asli (SERVER=domain:443) ra az yek server-e Iran migirad.
    # dar halat-e pishfarz (ws+TLS) node bayad be DOMAIN vasl shavad (na host/IP-e SSH), chon
    # ratholenode az SERVER ham remote_addr va ham SNI ra misazad. domain ra az 'status --json'
    # migirim; agar darnayamad be host-e inventory fallback mikonim.
    # bazgasht: (server_str, domain)  — masalan ("rp01.l1t.ir:443", "rp01.l1t.ir")
    domain = ""
    try:
        st = run_on_server(s, ["ratholectl", "status", "--json"])
        d = json.loads(st.get("out", "") or "{}")
        domain = str(d.get("domain", "") or "").strip()
    except (ValueError, TypeError):
        domain = ""
    if domain and RE_HOST.match(domain):
        return "%s:443" % domain, domain
    host = iran_public_host(s)
    return ("%s:443" % host if host else ""), ""

def iran_public_host(server, fallback=""):
    def usable(value):
        value = str(value or "").strip()
        return value if (RE_HOST.fullmatch(value) and value not in ("localhost", "::1")
                         and not value.startswith(("127.", "0.0.0.0"))) else ""
    # public_ip-e khod-e Iran baraye data-plane ast; host-e inventory momken ast IP-e SSH/VPN bashad.
    override = usable(server.get("public_ip"))
    if override:
        return override
    inventory = usable(server.get("host"))
    reported = ""
    domain = ""
    try:
        response = run_on_server(server, ["ratholectl", "status", "--json"])
        if response.get("rc") == 0:
            status = json.loads(response.get("out", "") or "{}")
            reported = usable(status.get("public_ip"))
            domain = usable(status.get("domain"))
    except (ValueError, TypeError, AttributeError):
        pass
    lan_ranges = tuple(ipaddress.ip_network(net) for net in
                       ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                        "100.64.0.0/10", "169.254.0.0/16"))
    def is_lan(value):
        try:
            ip = ipaddress.ip_address(value)
            return any(ip in net for net in lan_ranges)
        except ValueError:
            return False
    if reported and not is_lan(reported):
        return reported
    if inventory and not is_lan(inventory):
        return inventory
    return domain or reported or inventory or usable(fallback)


def _relay_deploy_to_server(server, cfg, gh, chan, proxy_url, req_sig):
    work_dir = tempfile.mkdtemp(prefix="rth-hub-deploy-")
    try:
        dl = hubupdate.download_verified_release(
            gh_repo=gh,
            channel=chan,
            proxy_url=proxy_url,
            inventory=get_inventory(),
            ssh_cfg=cfg,
            pubkey_path=str(cfg.get("update_pubkey_path", "") or ""),
            require_sig=bool(req_sig),
            dest_dir=work_dir,
        )
        ssh_base = _ssh_base(cfg, server)
        res = hubupdate.push_and_run_update(
            server,
            ssh_base,
            dl["bootstrap_path"],
            dl["bundle_path"],
            dl["bundle_name"],
            gh,
            dl["release"],
            require_sig=bool(req_sig),
            timeout=600,
        )
        sig_tag = "Ed25519 verified" if (dl.get("sig") or {}).get("verified") else "SHA256 checked"
        hdr = "[hub-relay via=%s release=%s %s]\n" % (dl.get("via", "?"), dl.get("release", chan), sig_tag)
        res["out"] = hdr + (res.get("out") or "")
        return res
    except Exception as exc:
        return {"rc": 1, "out": "", "err": redact_secrets(str(exc), [proxy_url] if proxy_url else ())}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def deploy_to_server(server, opts=None):
    # apdit az GitHub: install.sh-e akharin Release ra rooye server migirad (ba mirror-haye
    # ghproxy baraye dor zadan-e filtering) va ba --update ejra mikonad. agar direct dar Iran
    # filter bashad va relay_mode='auto' ya 'relay' bashad, Hub khodesh az proxy/node relay
    # release ra ba Ed25519 migirad va ba SSH stdin push mikonad.
    o = opts if isinstance(opts, dict) else {}
    relay_ov = str(o.get("relay", "") or "").strip()
    if relay_ov and relay_ov not in hubupdate.UPDATE_RELAY_MODES:
        return {"rc": 1, "out": "", "err": "update relay mode namotabar: %r" % relay_ov}
    req_sig_ov = o.get("require_sig", None)
    if req_sig_ov is not None and not isinstance(req_sig_ov, (bool, int)):
        return {"rc": 1, "out": "", "err": "require_sig namotabar"}
    cfg = get_config()
    chan = str(cfg.get("update_channel", "stable"))
    relay_mode = relay_ov or str(cfg.get("update_relay_mode", "auto") or "auto")
    req_sig = bool(req_sig_ov) if req_sig_ov is not None else bool(cfg.get("update_require_sig", False))
    if MOCK:
        return {"rc": 0, "out": "[mock deploy→%s] github install.sh --update (kanal=%s, relay=%s, sig=%s)" % (
            server.get("name"), chan, relay_mode, "on" if req_sig else "off"), "err": ""}
    # slug az config (sabet، na vorodi-ye karbar) va ba regex etebarsanji mishavad.
    gh = str(cfg.get("gh_repo", "l8PYGIT/RatholeEngine"))
    if not RE_SLUG.match(gh):
        return {"rc": 1, "out": "", "err": "gh_repo namotabar dar config: %r" % gh}
    # kanal-e apdit az config (default stable). faghat stable/beta mojaz ast (RE_CHAN).
    # CHERA MOHEM: 'stable' → releases/latest/download ke pre-release ha ra NADIDE migirad.
    # agar server rooye beta bashad va bدون in latest=noskhe-ye stable-e ghadimi tar bashad،
    # apdit an ra DOWNGRADE mikonad va backhaul/features-e jadid ra kharab mikonad. baraye
    # server-haye beta bayad kanal='beta' bashad ta tag-e daghigh (releases.atom) resolve shavad.
    if not RE_CHAN.match(chan):
        return {"rc": 1, "out": "", "err": "update_channel namotabar dar config: %r (stable|beta)" % chan}
    if relay_mode not in hubupdate.UPDATE_RELAY_MODES:
        return {"rc": 1, "out": "", "err": "update_relay_mode namotabar dar config: %r" % relay_mode}
    uproxy = str(cfg.get("update_proxy", "") or "").strip()
    if uproxy and not valid_proxy_url(uproxy):
        return {"rc": 1, "out": "", "err": "update_proxy namotabar dar config"}
    hub_dl_proxy = uproxy or get_proxy(server)

    if server.get("transport") == "api":
        cli = "ratholectl" if server.get("role") == "iran" else "ratholenode"
        cmd = [cli, "update", chan]
        if uproxy:
            cmd += ["--proxy", uproxy]
        if req_sig:
            cmd.append("--require-sig")
        return run_on_server(server, cmd, timeout=600)

    if relay_mode == "relay":
        return _relay_deploy_to_server(server, cfg, gh, chan, hub_dl_proxy, req_sig)

    # yek script-e khoddATka ke rooye server ejra mishavad. tanha meghdar-haye tazrigh-shode
    # slug (RE_SLUG), kanal (RE_CHAN), req_sig (0|1) va uproxy (valid_proxy_url) hastand.
    req_sig_flag = "1" if req_sig else "0"
    uproxy_q = shlex.quote(uproxy) if uproxy else "''"
    remote = r'''set -e
GH="%s"
CHAN="%s"
UPROXY=%s
REQ_SIG="%s"
MIRRORS=("" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/")
REL="latest"
if [ "$CHAN" = "beta" ]; then
  TAG=""
  if [ -n "$UPROXY" ]; then
    AT="$(printf 'proxy = "%%s"\n' "$UPROXY" | curl --config - -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 15 --retry 1 "https://github.com/${GH}/releases.atom" 2>/dev/null || true)"
    TAG="$(printf '%%s' "$AT" | grep -oE 'releases/tag/v[0-9A-Za-z._-]+' | sed 's#.*releases/tag/##' | grep -E -- '-(beta|rc|alpha)' | head -n1 || true)"
  else
    for M in "${MIRRORS[@]}"; do
      AT="$(curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 15 --retry 1 "${M}https://github.com/${GH}/releases.atom" 2>/dev/null)" || continue
      TAG="$(printf '%%s' "$AT" | grep -oE 'releases/tag/v[0-9A-Za-z._-]+' | sed 's#.*releases/tag/##' | grep -E -- '-(beta|rc|alpha)' | head -n1 || true)"
      [ -n "$TAG" ] && break
    done
  fi
  [ -n "$TAG" ] || { echo "hich noskhe-ye beta peyda nashod (releases.atom)" >&2; exit 1; }
  REL="$TAG"
fi
if [ "$REL" = "latest" ]; then PATH_SEG="releases/latest/download/install.sh"; else PATH_SEG="releases/download/${REL}/install.sh"; fi
T="$(mktemp)"
trap 'rm -f "$T"' EXIT
ok=0
if [ -n "$UPROXY" ]; then
  if printf 'proxy = "%%s"\n' "$UPROXY" | curl --config - -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 1 "https://github.com/${GH}/${PATH_SEG}" -o "$T" 2>/dev/null; then ok=1; fi
else
  for M in "${MIRRORS[@]}"; do
    if curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 1 "${M}https://github.com/${GH}/${PATH_SEG}" -o "$T" 2>/dev/null; then ok=1; break; fi
  done
fi
[ "$ok" = 1 ] || { echo "download install.sh az hameye mirror-ha shekast khord (filtering?)" >&2; exit 1; }
RATHOLE_GH="$GH" RATHOLE_RELEASE="$REL" RATHOLE_UPDATE_PROXY="$UPROXY" RATHOLE_REQUIRE_SIG="$REQ_SIG" bash "$T" --update
''' % (gh, chan, uproxy_q, req_sig_flag)
    res = run_on_server(server, ["bash", "-c", remote], timeout=600)
    if relay_mode == "auto" and hubupdate.looks_like_network_failure(res):
        r2 = _relay_deploy_to_server(server, cfg, gh, chan, hub_dl_proxy, req_sig)
        if r2.get("rc") == 0:
            r2["out"] = "[auto-relay] direct GitHub fetch failed; retrying via Hub tunnel relay...\n" + (r2.get("out") or "")
            return r2
        err1 = (res.get("err") or "").strip()
        err2 = (r2.get("err") or "").strip()
        return {"rc": r2.get("rc", 1), "out": (res.get("out") or "") + (r2.get("out") or ""),
                "err": f"{err1} | auto-relay: {err2}".strip(" |")}
    return res

# ---------- provision khodkar (ba ramz SSH → nصب kelid + deploy + sabt) ----------
def ensure_hub_key():
    # motmaen mishavad hub yek jft-kelid SSH darad; agar nabashad misazad va masir ra dar config zakhire mikonad.
    cfg = get_config()
    kp = cfg.get("ssh_key_path") or "/etc/ratholehub/id_ed25519"
    if not valid_ssh_key_path(kp):
        raise ValueError("ssh_key_path namotabar ast")
    pub = kp + ".pub"
    if not (os.path.exists(kp) and os.path.exists(pub)):
        os.makedirs(os.path.dirname(kp), exist_ok=True)
        # agar yeki az do file nesfe-nim bashad, pak kon ta ssh-keygen gير nakonad
        for f in (kp, pub):
            try: os.remove(f)
            except OSError: pass
        r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "ratholehub", "-f", kp, "-q"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not os.path.exists(pub):
            raise RuntimeError("ssh-keygen shekast: " + (r.stderr or r.stdout or "?"))
        try: os.chmod(kp, 0o600)
        except OSError: pass
    if cfg.get("ssh_key_path") != kp:
        # atomic: faghat ssh_key_path ra rooye naskhe-ye taze bezan (na kolle cfg-e bayat)
        # ta ba _config_save-e hamzaman (masalan taghir-e ramz) race nakonad.
        def _set_kp(c):
            c["ssh_key_path"] = kp
            return c
        update_config(_set_kp)
    with open(pub, "r", encoding="utf-8") as f:
        return kp, f.read().strip()

def provision_server(d):
    # vorodi: name, role, host, ssh_user, ssh_port, ssh_password
    # marahel: 1) nصب kelid-e omoomi-ye hub rooye server ba ramz  2) deploy (scp + update.sh)  3) sabt dar inventory
    name = str(d.get("name", "")); role = str(d.get("role", ""))
    host = str(d.get("host", "")); user = str(d.get("ssh_user", "root"))
    port = str(d.get("ssh_port", "22")); pw = str(d.get("ssh_password", ""))
    if not RE_NAME.match(name) or role not in ("iran", "node") or not RE_HOST.match(host) \
       or not RE_NAME.match(user) or not RE_PORT.match(port):
        return {"rc": 1, "out": "", "err": "field-haye namotabar (name/role/host/user/port)"}
    if not pw:
        return {"rc": 1, "out": "", "err": "ramz SSH lazem ast"}
    if any(s.get("name") == name for s in get_inventory()):
        return {"rc": 1, "out": "", "err": "in nam az ghabl vojood darad"}
    server = {"name": name, "role": role, "host": host, "ssh_user": user, "ssh_port": int(port)}
    # baraye node: server-e Iran-e main ra moshakhas kon (vorodi iran_server ya, agar
    # faghat yek server Iran dar hub bashad, hamon). in tunnel-e asli (SERVER) ra baad az
    # deploy tanzim mikonad ta node digar «?» nashan nadahad.
    iran_host = ""; iran_srv = None
    if role == "node":
        want = str(d.get("iran_server", "")).strip()
        irs = [s for s in get_inventory() if s.get("role") == "iran"]
        if want:
            match = next((s for s in irs if s.get("name") == want or s.get("host") == want), None)
            if match:
                iran_host = str(match.get("host", "")); iran_srv = match
            elif RE_HOST.match(want):
                iran_host = want
        elif len(irs) == 1:
            iran_host = str(irs[0].get("host", "")); iran_srv = irs[0]
    if MOCK:
        update_inventory(lambda inv: inv + [server] if not any(s.get("name") == name for s in inv) else inv)
        return {"rc": 0, "out": "[mock provision→%s] kelid nصب shod + deploy + be hub ezafe shod" % name, "err": ""}
    if not shutil.which("sshpass"):
        return {"rc": 1, "out": "", "err": "sshpass rooye hub nصب nist. nصب kon: apt install -y sshpass"}
    try:
        kp, pubkey = ensure_hub_key()
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
    logs = []
    opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=12", "-o", "NumberOfPasswordPrompts=1"]
    target = "%s@%s" % (user, host)
    # 1) nصب kelid-e omoomi dar authorized_keys (idempotent — dobare ezafe nemikonad)
    q = shlex.quote(pubkey)
    remote = ("set -e; umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
              "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
              "grep -qF %s ~/.ssh/authorized_keys || printf '%%s\\n' %s >> ~/.ssh/authorized_keys" % (q, q))
    ssh_env = os.environ.copy()
    ssh_env["SSHPASS"] = pw
    try:
        r = subprocess.run(["sshpass", "-e", "ssh"] + opts + ["-p", port, target, remote],
                           capture_output=True, text=True, timeout=45, env=ssh_env)
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "timeout dar atesal ba ramz (host/port/firewall?)"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
    logs.append("== nصب kelid SSH ==\n" + (_strip_ansi(r.stdout) or "(ok)") +
                (("\n[stderr] " + _strip_ansi(r.stderr)) if r.stderr.strip() else ""))
    if r.returncode != 0:
        emsg = r.stderr.strip() or r.stdout.strip() or "khata"
        low = emsg.lower()
        if "permission denied" in low or "authentication" in low:
            emsg = "ramz/karbar eshtebah ast ya vorod ba ramz roo server baste ast (PasswordAuthentication)."
        return {"rc": r.returncode, "out": "\n\n".join(logs), "err": "nصب kelid shekast khord: " + emsg}
    # 2) deploy ba kelid (scp scripts + update.sh) — server hanoz dar inventory nist pas mostaghim server dict ra midahim
    dep = deploy_to_server(server)
    logs.append("== deploy (github-update) ==\n" + (dep.get("out", "") or "") +
                (("\n[stderr] " + dep.get("err", "")) if dep.get("err") else ""))
    # 2.5) baraye node: tunnel-e asli (SERVER) ra be server-e Iran vasl kon ta «?» nashan nadahad.
    # maghsad = DOMAIN-e omoomi-ye Iran (na host/IP-e SSH) ta SNI ba cert bekhanad va tunnel bala biad.
    if role == "node" and iran_host and dep.get("rc") == 0:
        main_srv = (iran_main_server(iran_srv)[0] if iran_srv else "") or (iran_host + ":443")
        sset = run_on_server(server, ["ratholenode", "set", "SERVER", main_srv])
        logs.append("== tunnel-e asli → %s ==\n" % main_srv + (sset.get("out", "") or "") +
                    (("\n[stderr] " + sset.get("err", "")) if sset.get("err") else ""))
    elif role == "node" and not iran_host:
        logs.append("== [هشدار] server Iran-e main tanzim nashod — dar safhe-ye node ba «tanzim tunnel asli» vaslesh kon. ==")
    # 3) sabt dar inventory (hata agar deploy naghes bood, kelid nصب shode va etesal ba kelid barقarار ast)
    update_inventory(lambda inv: inv + [server] if not any(s.get("name") == name for s in inv) else inv)
    logs.append("== be hub ezafe shod: %s (%s) — az in pas atesal ba kelid ast ==" % (name, role))
    note = "" if dep.get("rc") == 0 else "\n[هشدار] deploy kamel nashod (rc=%s)؛ mitavani baad dokme «apdit» ra bezani." % dep.get("rc")
    return {"rc": 0, "out": "\n\n".join(logs) + note, "err": ""}

def mock_run(server, cmd_args):
    # prefix-e mohafez ('timeout N ...') baraye tatbigh-e mock bi-marbut ast — bardar.
    # (dar vaghe-iat SSH an ra ejra mikonad؛ inja faghat naghshe-ye dastoor mohem ast.)
    if len(cmd_args) >= 3 and cmd_args[0] == "timeout":
        cmd_args = cmd_args[2:]
    j = " ".join(cmd_args)
    role = server.get("role")

    if j == "ratholectl ls":
        return {"rc": 0, "out":
                "NAME           PORT     INBOUND      API        TRANSPORT  SNI              USER PATH\n"
                "--------------------------------------------------------------------------------\n"
                "trk01          1005     8444         -          backhaul   -                https://d/trk01\n"
                "trk02          1006     8445         9001       kcp        -                https://d/trk02\n"
                "noisenode      1008     8447         -          noise      -                https://d/noisenode\n"
                "gamenodetrk    1007     2101         7001       ws         gmtrk.l1t.ir     https://d/gamenodetrk\n"
                "plainnode      1009     8449         -          plain      -                https://d/plainnode\n"
                "frpnode        1010     8450         -          frp        -                https://d/frpnode\n"
                "grenode        1011     8451         -          gre        -                https://d/grenode", "err": ""}
    if cmd_args[:2] == ["ratholectl", "show"] and len(cmd_args) >= 3:
        nm = cmd_args[2]
        return {"rc": 0, "out":
            "──────── dstvr nasb rooye node kharej (curl yek-khatti) ────────\n"
            "curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \\\n"
            "  --server rp01.l1t.ir:443 --name %s --token a0370655deadbeefcafe1234 --inbound-port 8444\n"
            "────────────────────────────────────────" % nm, "err": ""}
    if j == "ratholectl version":
        return {"rc": 0, "out": "manager_version=1.4.7\nrole=panel\nrathole_version=0.5.0", "err": ""}
    if j == "ratholenode version":
        return {"rc": 0, "out": "manager_version=1.4.6\nrole=node\nrathole_version=0.5.0", "err": ""}
    if cmd_args[:2] == ["ratholectl", "ip-cert"]:
        return {"rc": 0, "out": "WSS-e self-signed faal shod.", "err": ""}
    if cmd_args[:2] == ["ratholectl", "ip-cert-show"]:
        return {"rc": 0, "out": "-----BEGIN CERTIFICATE-----\nTU9DSw==\n-----END CERTIFICATE-----\n", "err": ""}
    if j == "ratholectl status --json":
        is_shz = server.get("name") == "iran-shiraz"
        dom = "shz01.l1t.ir" if is_shz else "rp01.l1t.ir"
        ip = server.get("host") or ("185.231.114.88" if is_shz else "5.202.4.40")
        return {"rc": 0, "out": json.dumps({
            "domain": dom, "public_ip": ip,
            "transport": "websocket+TLS (443)",
            "ports": {"control": 2333, "fake": 8080, "sub": 2096, "internal": 8443,
                      "plain": 8880, "direct": None, "hub": 8088, "noise": 2334,
                      "backhaul": 3080, "frp": 7000},
            "direct_header": "X-Cdn-Id",
            "cert": {"fullchain": f"/etc/letsencrypt/live/{dom}/fullchain.pem",
                     "key": f"/etc/letsencrypt/live/{dom}/privkey.pem",
                     "exists": "yes", "expiry": "Oct 12 09:00:00 2026 GMT", "self_signed": "no"},
            "services": {"rathole_server": "yes", "nginx": "yes", "nginx_config_ok": "yes",
                         "noise": "yes", "backhaul": "yes", "fakeweb": "yes", "frps": "yes", "paqet": "no"},
            "features": {"fakeweb": {"configured": True, "active": True, "port": 8080},
                         "direct": {"configured": True, "active": True, "port": 8443},
                         "frp": {"configured": True, "active": True, "port": 7000},
                         "gre": {"configured": True, "active": True, "name": "gre1"},
                         "paqet": {"configured": False, "active": False, "remote": "", "mode": "fast", "block": "aes-128-gcm", "nodes": []}},
            "sni_count": 1, "node_count": 7,
            "nodes": [
                {"name": "trk01", "port": 1005, "inbound_port": 8444, "api_local_port": None,
                 "sni": None, "transport": "backhaul"},
                {"name": "trk02", "port": 1006, "inbound_port": 8445, "api_local_port": 9001,
                 "sni": None, "transport": "kcp"},
                {"name": "noisenode", "port": 1008, "inbound_port": 8447, "api_local_port": None,
                 "sni": None, "transport": "noise"},
                {"name": "gamenodetrk", "port": 1007, "inbound_port": 2101, "api_local_port": 7001,
                 "sni": "gmtrk.l1t.ir", "transport": None},
                {"name": "plainnode", "port": 1009, "inbound_port": 8449, "api_local_port": None,
                 "sni": None, "transport": "plain"},
                {"name": "frpnode", "port": 1010, "inbound_port": 8450, "api_local_port": None,
                 "sni": None, "transport": "frp"},
                {"name": "grenode", "port": 1011, "inbound_port": 8451, "api_local_port": None,
                 "sni": None, "transport": "gre"}
            ]
        }), "err": ""}
    if j == "ratholectl backhaul show":
        return {"rc": 0, "out":
            "──────── faalsazi backhaul (SMUX core) rooye node kharej ────────\n"
            "rooye node in ra bezan (tunnel-e mux az haman domain/443 obur miknd):\n"
            "  ratholenode backhaul on rp01.l1t.ir 4e9c1f7a2b8d6053ae71cc94f20d3b6857aa19ef wssmux balanced\n"
            "────────────────────────────────────────", "err": ""}
    if j == "ratholectl backhaul status":
        return {"rc": 0, "out": "backhaul (SMUX core): roshan  backhaul-server ru-ye 127.0.0.1:3080 "
                "(server=wsmux / client=wssmux, profile=balanced, az nginx/443)  (node-ha: 1)\n"
                "  node-haye backhaul: trk01", "err": ""}
    if j == "ratholenode backhaul status":
        return {"rc": 0, "out": "backhaul client: active  → rp01.l1t.ir:443 (transport=wssmux, profile=balanced)", "err": ""}
    if j == "ratholectl paths":
        return {"rc": 0, "out": "──────── masir-e config-ha va file-ha ────────\n"
                "  ✓  state.json             /etc/rathole-manager/state.json\n"
                "  ✓  server.toml            /etc/rathole/server.toml\n"
                "  ✓  nginx rathole.conf     /etc/nginx/conf.d/rathole.conf\n"
                "  ✓  cert fullchain         /etc/letsencrypt/live/rp01.l1t.ir/fullchain.pem", "err": ""}
    if j == "ratholectl kcp status":
        return {"rc": 0, "out": "kcp: roshan  UDP :443 → 127.0.0.1:2333  (profile: balanced)\n"
                "  estetar: UDP/443 ~ QUIC/HTTP3\n  service: active\n  gvshdadn UDP:443: blh", "err": ""}
    if j == "ratholectl game ls":
        return {"rc": 0, "out": "NAME           SNI                    DATA     NODE-INBOUND\n"
                "------------------------------------------------------------\n"
                "gmtrk          gmtrk.l1t.ir           1007     8444", "err": ""}
    if j == "ratholectl doctor":
        return {"rc": 0, "out": "OK rathole-server faal ast\nOK nginx faal ast\n"
                "OK  node trk01 rooye port 1005 amade ast\n"
                "OK  node trk02 rooye port 1006 amade ast\n"
                "OK  node noisenode rooye port 1008 amade ast\n"
                "OK  node plainnode rooye port 1009 amade ast\n"
                "OK  node frpnode rooye port 1010 amade ast\n"
                "OK  node grenode rooye port 1011 amade ast\n"
                "WARN node gamenodetrk rooye port 1007 gvsh nmidhd (klaint node vsl nist?)\n"
                "khlash: OK=7  FAIL=1", "err": ""}
    if cmd_args[:2] == ["ratholectl", "logs"] or cmd_args[:3] == ["ratholenode", "logs", "all"]:
        # nemune-ye kutah: sakhtar-e vaghei + neshan dadan-e inke token-ha REDACT shode-and.
        return {"rc": 0, "out":
                "\n===== kolli =====\n"
                "naghsh      : %s\nratholectl  : manager_version=1.6.3\n"
                "\n===== unit: rathole-server  (halat: active/enabled) =====\n"
                "Jul 31 12:00:01 rp01 rathole[811]: control channel established\n"
                "\n===== state.json (/etc/rathole-manager/state.json) =====\n"
                "{\"domain\":\"rp01.l1t.ir\",\"nodes\":[{\"name\":\"trk01\",\"token\":\"***REDACTED***\"}]}\n"
                "\n===== payan =====" % ("panel (Iran)" if role == "iran" else "node (kharej)"),
                "err": ""}
    if j == "ratholenode ls":
        s_nm = server.get("name", "trk01")
        inb_map = {"trk01": "8444", "trk02": "8445", "noisenode": "8447", "gamenodetrk": "2101", "plainnode": "8449", "frpnode": "8450", "grenode": "8451"}
        inb = inb_map.get(s_nm, "8444")
        return {"rc": 0, "out": f"tunnel be: rp01.l1t.ir:443  (hame serviceha rooye yek channel kontroli)\n"
                f"SERVICE          INBOUND    TOKEN\n-------------------------------------------\n"
                f"{s_nm}            {inb}       a0370655…", "err": ""}
    if j == "ratholenode kcp status":
        return {"rc": 0, "out": "halat tunnel: kcp\n  local: 127.0.0.1:29900   remote(UDP): 5.202.4.40:443   profile: balanced\n"
                "  estetar: UDP/443 ~ QUIC/HTTP3\n  kcp-client: active\n  rathole-client: active", "err": ""}
    if j == "ratholenode upstream ls":
        return {"rc": 0, "out": "tunnel asli (main): rp01.l1t.ir:443  [tunnel=kcp]\n"
                "upstream 'iran2nobody': rp02.btli.ir:443  [tunnel=ws]\n    trk01b|***|1102", "err": ""}
    if j == "ratholectl noise status":
        return {"rc": 0, "out": "noise (ramznegari-shode): roshan  rathole-noise rooye port-e omomi 2334  (node-haye noise: 1)\n"
                "  node-haye noise: gamenodetrk\n"
                "  gvshdadn TCP:2334: blh\n  rathole-noise: active", "err": ""}
    if j == "ratholectl noise show":
        return {"rc": 0, "out": "──────── faalsazi halat noise rooye node kharej ────────\n"
                "  ratholenode noise on 5.202.4.40:2334 Qm9ndXNMb2NrS2V5RXhhbXBsZUJhc2U2NFBhZGRpbmc= Noise_NK_25519_ChaChaPoly_BLAKE2s\n"
                "bazgsht: ratholenode noise off", "err": ""}
    if j == "ratholectl plain status":
        return {"rc": 0, "out": "plain (bedoon TLS): roshan  listener HTTP rooye port 8880\n"
                "  gvshdadn TCP:8880: blh", "err": ""}
    if j == "ratholectl direct status":
        return {"rc": 0, "out": "direct-IP (header-based): roshan   port 8081   header: X-Cdn-Id\n"
                "  gvshdadn TCP:8081: blh\n  node-ha:  trk01 -> \"X-Cdn-Id: trk01\"", "err": ""}
    if j == "ratholectl frp status":
        return {"rc": 0, "out": "FRP (reverse tunnel): roshan  port 7000 (tcp)\n  gvshdadn :7000: blh\n  frps: active", "err": ""}
    if j == "ratholectl frp show":
        return {"rc": 0, "out": "──────── faalsazi FRP rooye node kharej ────────\n"
                "  ratholenode frp on 5.202.4.40:7000 4e9c1f7a2b8d6053ae71cc94f20d3b68 tcp\n"
                "───────────────────────────────────────────────", "err": ""}
    if j == "ratholenode frp status":
        return {"rc": 0, "out": "halat tunnel: frp\n  remote: 5.202.4.40:7000   transport: tcp\n  frpc: active", "err": ""}
    if j == "ratholectl gre status":
        return {"rc": 0, "out": "GRE tunnel: roshan  interface: gre1 (tunnel: 10.10.10.1/30, peer: 198.51.100.5)\n  link status: UP", "err": ""}
    if j == "ratholenode gre status":
        return {"rc": 0, "out": "GRE tunnel: roshan  interface: gre1 (tunnel: 10.10.10.2/30, peer: 5.202.4.40)\n  link status: UP", "err": ""}
    if cmd_args[:2] == ["ratholectl", "test"]:
        nm = cmd_args[2] if len(cmd_args) >= 3 else "trk01"
        cnt = 5
        for i, tok in enumerate(cmd_args):
            if tok == "--count" and i + 1 < len(cmd_args) and cmd_args[i + 1].isdigit():
                cnt = int(cmd_args[i + 1])
        port_map = {"trk01": 1005, "trk02": 1006, "gamenodetrk": 1007, "noisenode": 1008, "plainnode": 1009, "frpnode": 1010, "grenode": 1011}
        tr_map = {"trk01": "backhaul", "trk02": "kcp", "gamenodetrk": "ws", "noisenode": "noise", "plainnode": "plain", "frpnode": "frp", "grenode": "gre"}
        is_game = (nm == "gamenodetrk")
        return {"rc": 0, "out": json.dumps({
            "ok": True, "verdict": "healthy", "probe_mode": "tls_direct" if is_game else "http_ws",
            "host": "127.0.0.1", "port": port_map.get(nm, 1005),
            "count": cnt, "ok_count": cnt, "loss_pct": 0.0,
            "rtt_ms": {"min": 14.2, "avg": 18.4, "max": 24.1, "p95": 23.0},
            "jitter_ms": 2.3, "listener_up": True,
            "http_status": None if is_game else 101,
            "tls_version": "TLSv1.3" if is_game else None,
            "detail": None, "backends": [], "gre": None,
            "role": "panel", "node": nm, "transport": tr_map.get(nm, "ws"),
            "inbound_port": 8444, "sni": "gmtrk.l1t.ir" if is_game else None,
            "service": {"name": "rathole-backhaul-server" if nm == "trk01" else "rathole-server", "active": True, "status": "yes"},
        }), "err": ""}
    if cmd_args[:2] == ["ratholenode", "test"]:
        cnt = 5
        for i, tok in enumerate(cmd_args):
            if tok == "--count" and i + 1 < len(cmd_args) and cmd_args[i + 1].isdigit():
                cnt = int(cmd_args[i + 1])
        snm = server.get("name", "trk01")
        inb_map = {"trk01": 8444, "trk02": 8445, "noisenode": 8447, "gamenodetrk": 2101, "plainnode": 8449, "frpnode": 8450, "grenode": 8451}
        return {"rc": 0, "out": json.dumps({
            "ok": True, "verdict": "healthy", "probe_mode": "ws_tls",
            "host": "rp01.l1t.ir", "port": 443,
            "count": cnt, "ok_count": cnt, "loss_pct": 0.0,
            "rtt_ms": {"min": 11.8, "avg": 15.1, "max": 19.6, "p95": 18.9},
            "jitter_ms": 1.6, "listener_up": True,
            "http_status": 101, "tls_version": "TLSv1.3", "detail": None,
            "backends": [{"name": snm, "lane": "rathole", "port": inb_map.get(snm, 8444), "up": True, "rtt_ms": 0.4}],
            "gre": None, "role": "node", "transport": "ws",
            "endpoint": "rp01.l1t.ir:443",
            "service": {"name": "rathole-client", "active": True, "status": "yes"},
        }), "err": ""}
    if cmd_args == ["ratholectl", "history", "--json"]:
        return {"rc": 0, "out": json.dumps({
            "dir": "/etc/rathole-manager/history", "count": 1,
            "revisions": [{"rev": 1, "id": "rev-mock-001", "ts": "20261123T150000Z", "domain": "rp01.l1t.ir", "node_count": 7, "nodes": ["trk01"]}],
        }), "err": ""}
    if cmd_args[:2] == ["ratholectl", "undo"]:
        return {"rc": 0, "out": "[DRY-RUN] pish-namayesh undo" if "--dry-run" in cmd_args else "state be revision bazgasht.", "err": ""}
    if cmd_args == ["ratholenode", "endpoints", "ls", "--json"]:
        return {"rc": 0, "out": json.dumps({
            "primary": "rp01.l1t.ir:443", "active": "rp01.l1t.ir:443",
            "backups": ["5.202.4.41:443"],
            "scores": {
                "rp01.l1t.ir:443": {"score": 98.5, "last_ok": True, "last_ms": 18, "ok_count": 5, "fail_count": 0},
                "5.202.4.41:443": {"score": 94.0, "last_ok": True, "last_ms": 34, "ok_count": 3, "fail_count": 0},
            },
        }), "err": ""}
    if cmd_args == ["ratholenode", "endpoints", "test", "--json"]:
        return {"rc": 0, "out": json.dumps({
            "active": "rp01.l1t.ir:443", "primary": "rp01.l1t.ir:443",
            "results": [
                {"addr": "rp01.l1t.ir:443", "score": 98.5, "last_ok": True, "last_ms": 18, "ok_count": 6, "fail_count": 0},
                {"addr": "5.202.4.41:443", "score": 94.0, "last_ok": True, "last_ms": 34, "ok_count": 4, "fail_count": 0},
            ],
        }), "err": ""}
    if cmd_args[:3] in (["ratholenode", "endpoints", "add"], ["ratholenode", "endpoints", "rm"], ["ratholenode", "endpoints", "switch"]) and len(cmd_args) >= 4:
        return {"rc": 0, "out": f"endpoints {cmd_args[2]}: {cmd_args[3]}", "err": ""}
    if cmd_args[:2] == ["ratholectl", "paqet"]:
        sub = cmd_args[2] if len(cmd_args) > 2 else "status"
        if sub == "status":
            return {"rc": 0, "out": "paqet (Direct PCK client): khamoosh", "err": ""}
        if sub == "show":
            return {"rc": 0, "out": "paqet remote=198.51.100.5:9999 mode=fast block=aes-128-gcm", "err": ""}
        return {"rc": 0, "out": f"[mock] ratholectl paqet {sub} ok", "err": ""}
    if cmd_args[:2] == ["ratholenode", "paqet"]:
        sub = cmd_args[2] if len(cmd_args) > 2 else "status"
        if sub == "status":
            return {"rc": 0, "out": "paqet server: active  listen=:9999 mode=fast block=aes-128-gcm iface=eth0", "err": ""}
        if sub == "show":
            ip = server.get("host") or "198.51.100.5"
            return {"rc": 0, "out": f"ratholectl paqet on {ip}:9999 0123456789abcdef0123456789abcdef fast --block aes-128-gcm", "err": ""}
        return {"rc": 0, "out": f"[mock] ratholenode paqet {sub} ok", "err": ""}
    if len(cmd_args) >= 3 and cmd_args[0] in ("ratholectl", "ratholenode") and cmd_args[1] == "xray" and cmd_args[2] == "scan":
        return {"rc": 0, "out": json.dumps({
            "ok": True, "port": 443, "recommended": "www.microsoft.com",
            "results": [
                {"domain": "www.microsoft.com", "ok": True, "verdict": "GOOD", "tls_version": "TLSv1.3", "alpn": "h2", "rtt_ms": 18.4, "detail": ""},
                {"domain": "aws.amazon.com", "ok": True, "verdict": "GOOD", "tls_version": "TLSv1.3", "alpn": "h2", "rtt_ms": 24.1, "detail": ""},
            ],
        }), "err": ""}
    if cmd_args[:2] == ["ratholenode", "xray"]:
        sub = cmd_args[2] if len(cmd_args) > 2 else "status"
        if sub == "status":
            return {"rc": 0, "out": json.dumps({
                "configured": True, "active": True, "mode": "reality",
                "listen": "127.0.0.1", "port": 8443,
                "dest": "www.microsoft.com:443", "sni": "www.microsoft.com",
                "public_key": "mOCKPubKey1234567890abcdef1234567890abcdefA",
                "short_id": "a1b2c3d4e5f60718", "path": "/xhttp", "xhttp_mode": "auto",
                "tls": False, "proxy_protocol": False,
            }), "err": ""}
        if sub == "uri":
            ip = server.get("host") or "198.51.100.5"
            return {"rc": 0, "out": f"vless://11111111-2222-4333-8444-555555555555@{ip}:443?type=tcp&security=reality&encryption=none&flow=xtls-rprx-vision&sni=www.microsoft.com&fp=chrome&pbk=mOCKPubKey&sid=a1b2c3d4#rathole-reality", "err": ""}
        return {"rc": 0, "out": f"[mock] ratholenode xray {sub} ok", "err": ""}
    if j.startswith("ratholenode set SERVER "):
        return {"rc": 0, "out": "tanzim shod: SERVER = %s\n[mock] tunnel-e asli be-ruz shod." % cmd_args[-1], "err": ""}
    return {"rc": 0, "out": "[mock] %s → %s" % (role, j), "err": ""}


# ---------- parser hai khorooji CLI → dadhi sakhtarmnd ----------
def parse_iran_ls(text):
    nodes = []
    for line in (text or "").splitlines():
        t = line.rstrip()
        s = t.strip()
        if not s or s.startswith("NAME") or set(s) <= set("-"):
            continue
        p = t.split()
        if len(p) >= 2 and p[1].isdigit():
            # sotoon-haye jadid (transport/sni) az CLI-e taze miayand; ba CLI-e ghadimi
            # (bedoon-e in do sotoon) ham sazgar bemanim: age nabashand, path hamon p[4] ast.
            n = {"name": p[0], "port": p[1], "inbound": p[2] if len(p) > 2 else "",
                 "inbound_port": p[2] if len(p) > 2 else "",
                 "api": p[3] if len(p) > 3 else "-"}
            if len(p) >= 7:  # NAME PORT INBOUND API TRANSPORT SNI PATH
                tr = p[4]
                n["transport"] = None if tr in ("ws", "-", "") else tr
                n["sni"] = None if p[5] in ("-", "") else p[5]
                n["path"] = p[6]
            else:            # CLI-e ghadimi: p[4]=PATH
                n["path"] = p[4] if len(p) > 4 else ""
            nodes.append(n)
    return nodes

def parse_kcp_status(text):
    text = text or ""
    enabled = ("roshan" in text) or (re.search(r"halat tunnel[:：]?\s*kcp", text) is not None)
    port = None; profile = None; mode = None
    m = re.search(r"UDP\s*:?(\d+)", text)
    if m: port = m.group(1)
    m = re.search(r"profile[:：]?\s*([A-Za-z]+)", text)
    if m: profile = m.group(1)
    m = re.search(r"halat tunnel[:：]?\s*(\w+)", text)
    if m: mode = m.group(1)
    stealth = "QUIC" in text
    return {"enabled": enabled, "port": port, "profile": profile, "mode": mode, "stealth": stealth}

def parse_kcp_connect(text):
    # az khorooji "ratholectl kcp show" khat "ratholenode kcp on <IP>:<port> <key> <profile>" ra darmiavarad.
    for line in (text or "").splitlines():
        m = re.search(r"ratholenode\s+kcp\s+on\s+(\S+:\d+)\s+([A-Fa-f0-9]{8,64})\s+(\w+)", line)
        if m:
            return {"remote": m.group(1), "key": m.group(2), "profile": m.group(3)}
    return None

def parse_kcp_key(text):
    # key ra mostaghel az tashkhis IP darmiavarad (rooye Iran curl baraye IP momken ast kar nakonad).
    m = re.search(r"ratholenode\s+kcp\s+on\s+\S+\s+([A-Fa-f0-9]{8,64})\s+\w+", text or "")
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Fa-f0-9]{24,64})\b", text or "")  # fallback: token hex
    return m.group(1) if m else None

def parse_noise_connect(text):
    # az khorooji "ratholectl noise show" khat "ratholenode noise on <IP>:<port> <pubkey> [pattern]" ra darmiavarad.
    for line in (text or "").splitlines():
        m = re.search(r"ratholenode\s+noise\s+on\s+\S+:(\d+)\s+([A-Za-z0-9+/]{40,64}={0,2})(?:\s+(\S+))?", line)
        if m:
            return {"port": m.group(1), "pubkey": m.group(2), "pattern": m.group(3) or ""}
    return None


def parse_backhaul_connect(text):
    # az khorooji "ratholectl backhaul show" khat
    # "ratholenode backhaul on <domain> <token> <transport> <profile>" ra darmiavarad.
    for line in (text or "").splitlines():
        # NOKTE: 'wssmux' bayad GHABL az 'wss' biayad — alternation-e Python chap-be-rast ast va
        # ba (wss|wssmux) faghat 'wss' match mishavad va 'mux ...' baghi mimanad (profile gom mishavad).
        m = re.search(r"ratholenode\s+backhaul\s+on\s+(\S+)\s+([A-Fa-f0-9]{16,64})\s+(wssmux|wsmux|wss|ws)"
                      r"(?:\s+(balanced|lossy|aggressive))?", line)
        if m:
            return {"domain": m.group(1), "token": m.group(2),
                    "transport": m.group(3), "profile": m.group(4) or "balanced"}
    return None

def parse_version(text):
    # khorooji-ye "ratholectl/ratholenode version" (print_version) → manager/rathole version.
    t = text or ""
    out = {"manager": "", "rathole": ""}
    m = re.search(r"manager_version=(\S+)", t)
    if m: out["manager"] = m.group(1)
    m = re.search(r"rathole_version=(\S+)", t)
    if m: out["rathole"] = m.group(1)
    return out

def parse_node_connect(text):
    # az khorooji "ratholectl show <name>" (print_node_install) name/token/inbound-e vaghei
    # ra darmiavarad — token dar 'ls' mask ast, pas az inja migirim.
    t = text or ""
    out = {}
    m = re.search(r"--name\s+([A-Za-z0-9_-]{1,40})", t)
    if m: out["name"] = m.group(1)
    m = re.search(r"--token\s+([A-Za-z0-9._=+/-]{6,255})", t)
    if m: out["token"] = m.group(1)
    m = re.search(r"--inbound-port\s+(\d{1,5})", t)
    if m: out["inbound"] = m.group(1)
    m = re.search(r"--api-token\s+([A-Za-z0-9._=+/-]{6,255})", t)
    if m: out["api_token"] = m.group(1)
    m = re.search(r"--api-inbound-port\s+(\d{1,5})", t)
    if m: out["api_inbound"] = m.group(1)
    return out if (out.get("token") and out.get("inbound") and out.get("name")) else None

def parse_noise_status(text):
    # khorooji-ye "ratholectl/ratholenode noise status" ra parse mikonad → enabled/port/count/nodes/mode.
    text = text or ""
    enabled = ("roshan" in text) or (re.search(r"halat tunnel[:：]?\s*noise", text) is not None)
    port = None; count = None; nodes = []; mode = None
    m = re.search(r"port-e omomi\s*(\d+)", text)
    if m: port = m.group(1)
    if not port:
        m = re.search(r":(\d+)", text)   # fallback (samt-e node: remote IP:PORT)
        if m: port = m.group(1)
    m = re.search(r"node-haye noise[:：]?\s*(\d+)", text)
    if m: count = m.group(1)
    m = re.search(r"node-haye noise[:：]\s*([A-Za-z0-9_,\s-]+)$", text, re.M)
    if m:
        nodes = [x.strip() for x in m.group(1).split(",") if x.strip() and not x.strip().isdigit()]
    m = re.search(r"halat tunnel[:：]?\s*(\w+)", text)
    if m: mode = m.group(1)
    return {"enabled": enabled, "port": port, "count": count, "nodes": nodes, "mode": mode}

def parse_game_ls(text):
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("NAME") or set(s) <= set("-"):
            continue
        p = line.split()
        if len(p) >= 2:
            out.append({"name": p[0], "sni": p[1], "data": p[2] if len(p) > 2 else "",
                        "inbound": p[3] if len(p) > 3 else ""})
    return out


def parse_plain_status(text):
    # khorooji-ye "ratholectl plain status" → enabled/port. (ingress: masir-e ws bedoon TLS)
    text = text or ""
    enabled = "roshan" in text
    port = None
    m = re.search(r"port\s+(\d+)", text)
    if m: port = m.group(1)
    return {"enabled": enabled, "port": port}

def parse_direct_status(text):
    # khorooji-ye "ratholectl direct status" → enabled/port/header. (ingress: header-routing bedoon TLS)
    text = text or ""
    enabled = "roshan" in text
    port = None; header = None
    m = re.search(r"port\s+(\d+)", text)
    if m: port = m.group(1)
    m = re.search(r"header[:：]\s+([A-Za-z0-9-]+)", text)
    if m: header = m.group(1)
    return {"enabled": enabled, "port": port, "header": header or "X-Cdn-Id"}

def parse_backhaul_status(text):
    text = text or ""
    enabled = bool(re.search(r"\b(roshan|active)\b", text))
    port = None
    m = re.search(r":(\d+)", text)
    if m: port = m.group(1)
    nodes = []
    m = re.search(r"node-haye backhaul[:：]\s*([A-Za-z0-9_,\s-]+)$", text, re.M)
    if m:
        nodes = [x.strip() for x in m.group(1).split(",") if x.strip()]
    tr = re.search(r"(?:transport[=:]\s*|server=)([a-z]+)", text)
    profile = re.search(r"profile[=:]\s*([a-z]+)", text)
    return {"enabled": enabled, "port": port, "nodes": nodes,
            "transport": tr.group(1) if tr else None,
            "profile": profile.group(1) if profile else None}

def parse_frp_status(text):
    text = text or ""
    enabled = bool(re.search(r"\b(roshan|active)\b", text)) or ("halat tunnel: frp" in text)
    port = None
    m = re.search(r"port\s+(\d+)", text)
    if m: port = m.group(1)
    if not port:
        m = re.search(r":(\d+)", text)
        if m: port = m.group(1)
    tr = re.search(r"transport[=:]\s*(tcp|quic|kcp|websocket)\b", text)
    if not tr:
        tr = re.search(r"port\s+\d+\s+\((tcp|quic|kcp|websocket)\)", text)
    return {"enabled": enabled, "port": port, "transport": tr.group(1) if tr else None}

def parse_gre_status(text):
    text = text or ""
    enabled = ("roshan" in text) or ("UP" in text) or ("active" in text)
    name = "gre1"
    m = re.search(r"gre\d+", text)
    if m: name = m.group(0)
    return {"enabled": enabled, "name": name}

def parse_paqet_status(text):
    text = text or ""
    low = text.lower()
    enabled = ("roshan" in text) or bool(re.search(r"\bactive\b", low) and "inactive" not in low)
    m_mode = re.search(r"mode[=:]\s*(normal|fast[23]?)\b", text)
    m_blk = re.search(r"block[=:]\s*([A-Za-z0-9-]+)\b", text)
    m_rem = re.search(r"(?:→|->)\s*(\S+:\d+)", text)
    m_port = re.search(r"listen=?:?(\d+)", text)
    return {
        "enabled": enabled,
        "mode": m_mode.group(1) if m_mode else "fast",
        "block": m_blk.group(1) if m_blk else "aes-128-gcm",
        "remote": m_rem.group(1) if m_rem else "",
        "port": m_port.group(1) if m_port else "",
    }

def parse_paqet_connect(text):
    text = text or ""
    m = re.search(
        r"ratholectl\s+paqet\s+on\s+(\S+:\d+)\s+([A-Za-z0-9._=+/-]{8,255})"
        r"(?:\s+(normal|fast[23]?))?(?:\s+--block\s+([A-Za-z0-9-]+))?",
        text,
    )
    if not m:
        return None
    return {
        "remote": m.group(1),
        "key": m.group(2),
        "mode": m.group(3) or "fast",
        "block": m.group(4) or "aes-128-gcm",
    }

def parse_doctor(text):
    # alave bar shomaresh OK/FAIL, vaziat har node ra ham darmiavarad
    # (khatt-haye "OK node X rooye port P amade ast" / "WARN node X ... gvsh nmidhd")
    # ta graph/panel betavanad har edge ra sabz/ghermez konad.
    text = re.sub(r"\x1b\[[0-9;]*m", "", text or "")  # hazf-e rang-haye ANSI (agar tty bood)
    nodes = {}
    for line in text.splitlines():
        m = re.match(r"\s*(OK|WARN|FAIL)\s+node\s+([A-Za-z0-9_-]+)\s+rooye\s+port", line)
        if m:
            nodes[m.group(2)] = "ok" if m.group(1) == "OK" else "warn"
    m = re.search(r"OK=(\d+)\s+FAIL=(\d+)", text)
    if m:
        return {"ok": int(m.group(1)), "fail": int(m.group(2)), "nodes": nodes}
    return {"ok": text.count("OK "), "fail": text.count("FAIL"), "nodes": nodes}

def parse_node_ls(text):
    svcs = []; server = None
    for line in (text or "").splitlines():
        t = line.strip()
        m = re.search(r"tunnel be[:：]\s*(\S+)", t)
        if m:
            server = m.group(1); continue
        if not t or t.startswith("SERVICE") or set(t) <= set("-"):
            continue
        p = t.split()
        if len(p) >= 2 and p[1].isdigit():
            svcs.append({"name": p[0], "inbound": p[1]})
    return {"server": server, "services": svcs}

# ---- parse-e khoruji JSON-e adaptive state (bedoon-e secret-ha) ----
# faqat field-haye motalab-e shenakhte-shode ra bar-migardanad.
_ADAPTIVE_ALLOWED_KEYS = frozenset({
    "time", "current", "classification", "latency_ms", "consecutive_failures",
    "consecutive_recoveries", "last_switch_ts", "chain", "active_endpoint",
    "primary_recoveries", "last_reason",
})

def parse_adaptive_state(raw):
    """raw: string ya dict. -> dict ba field-haye motabar ya {'classification':'unknown'}."""
    try:
        if isinstance(raw, str):
            d = json.loads(raw)
        elif isinstance(raw, dict):
            d = raw
        else:
            return {"classification": "unknown"}
        # tanha field-haye motalab-e shenakhte-shode ra bar-migardanad
        result = {k: v for k, v in d.items() if k in _ADAPTIVE_ALLOWED_KEYS}
        if "classification" not in result:
            result["classification"] = "unknown"
        return result
    except Exception:
        return {"classification": "unknown"}

def parse_upstream_ls(text):
    main = None; ups = []; cur = None
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        mt = re.search(r"\[tunnel=(\w+)\]", t)
        um = re.search(r"upstream '([^']+)'", t)
        if um and mt:
            srv = re.search(r"'[^']+'\s*[:：]?\s*(\S+)\s*\[tunnel=", t)
            cur = {"id": um.group(1), "server": (srv.group(1) if srv else ""), "tunnel": mt.group(1), "services": []}
            ups.append(cur); continue
        if ("main" in t) and mt:
            srv = re.search(r"[:：]\s*(\S+)\s*\[tunnel=", t)
            main = {"server": (srv.group(1) if srv else ""), "tunnel": mt.group(1)}; cur = None; continue
        if "|" in t and cur is not None:
            parts = t.split("|")
            if len(parts) >= 2:
                cur["services"].append({"name": parts[0].strip(), "inbound": parts[-1].strip()})
    return {"main": main, "upstreams": ups}

# ---------- token/nshst ----------
def make_session_token(cfg):
    # kvki nshst = hmac( api_token , expiry )
    exp = str(int(time.time()) + 86400)
    sig = hmac.new(cfg["api_token"].encode(), exp.encode(), hashlib.sha256).hexdigest()
    return "%s.%s" % (exp, sig)

def check_session(cfg, token):
    tok = cfg.get("api_token") or ""
    if not tok:
        return False
    try:
        exp, sig = token.split(".", 1)
        if int(exp) < time.time(): return False
        good = hmac.new(tok.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(good, sig)
    except Exception:
        return False

def authed(cfg, headers, cookies):
    # Bearer token (legacy ya scoped) ya kvki nshst (baraye UI)
    return resolve_auth(cfg, headers, cookies, check_session) is not None


def collect_server_overview(s):
    name = s.get("name", "")
    role = s.get("role")
    host_fallback = s.get("host") or (urlparse(s.get("api_url") or "").hostname if s.get("transport") == "api" else None)
    ov = {"server": name, "role": role, "host": host_fallback, "reachable": True}
    def R(args):
        return run_on_server(s, args)
    if role == "iran":
        # Sariat-e bala: be jaye 12 dastoor-e motavali + `doctor` (ke 6-9s rooye WS probe
        # hang mikonad), status --json + kcp status + version ra hamzaman ejra mikonim.
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_st = pool.submit(R, ["ratholectl", "status", "--json"])
            f_kcp = pool.submit(R, ["ratholectl", "kcp", "status"])
            f_ver = pool.submit(R, ["ratholectl", "version"])
            r_st, r_kcp, r_ver = f_st.result(), f_kcp.result(), f_ver.result()
        if r_st.get("rc") not in (0, None):
            ov["reachable"] = False; ov["error"] = r_st.get("err", "") or ("rc=%s" % r_st.get("rc")); return ov
        st = {}
        raw = r_st.get("out", "") or ""
        try:
            st = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            print(f"[hub] status --json parse failed for {name}: {e}")
            print(f"[hub] raw output: {raw[:200]}")
            st = {}
        ov["status"] = st
        ov["kcp"] = parse_kcp_status(r_kcp.get("out", ""))
        ov["version"] = parse_version(r_ver.get("out", ""))
        if isinstance(st, dict) and ("nodes" in st or "features" in st):
            ov["domain"] = st.get("domain") or ""
            if not ov["host"] and st.get("public_ip"):
                ov["host"] = st.get("public_ip")
            raw_nodes = st.get("nodes") or []
            norm_nodes = []
            for nd in raw_nodes:
                if not isinstance(nd, dict):
                    continue
                inb = nd.get("inbound_port") if nd.get("inbound_port") is not None else nd.get("inbound")
                norm_nodes.append({
                    "name": nd.get("name", ""),
                    "port": str(nd.get("port", "")) if nd.get("port") is not None else "",
                    "inbound": str(inb) if inb is not None else "",
                    "inbound_port": str(inb) if inb is not None else "",
                    "api_port": str(nd.get("api_local_port")) if nd.get("api_local_port") else "",
                    "sni": nd.get("sni") or "",
                    "transport": nd.get("transport") or "ws",
                })
            ov["nodes"] = norm_nodes
            ov["game"] = [{"name": x["name"], "sni": x["sni"], "port": x["port"]} for x in norm_nodes if x.get("sni")]
            feats = st.get("features") or {}
            f_pl = feats.get("plain") or {}
            f_dr = feats.get("direct") or {}
            f_nz = feats.get("noise") or {}
            f_bh = feats.get("backhaul") or {}
            f_frp = feats.get("frp") or {}
            f_gre = feats.get("gre") or {}
            f_pq = feats.get("paqet") or {}
            nz_nodes = [x["name"] for x in norm_nodes if x.get("transport") == "noise"]
            ov["plain"] = {"enabled": bool(f_pl.get("configured")), "port": f_pl.get("port")}
            ov["direct"] = {"enabled": bool(f_dr.get("configured")), "port": f_dr.get("port"), "header": st.get("direct_header") or ""}
            ov["noise"] = {"enabled": bool(f_nz.get("configured")), "active": bool(f_nz.get("active")), "port": f_nz.get("port"), "nodes": nz_nodes, "count": len(nz_nodes)}
            ov["backhaul"] = {"enabled": bool(f_bh.get("configured")), "active": bool(f_bh.get("active")), "port": f_bh.get("port"), "mode": f_bh.get("mode"), "transport": f_bh.get("transport")}
            ov["frp"] = {"enabled": bool(f_frp.get("configured")), "active": bool(f_frp.get("active")), "port": f_frp.get("port"), "transport": f_frp.get("transport")}
            ov["gre"] = {"enabled": bool(f_gre.get("configured")), "active": bool(f_gre.get("active")), "name": f_gre.get("name"), "remote_ip": f_gre.get("remote_ip"), "tunnel_ip": f_gre.get("tunnel_ip")}
            ov["paqet"] = {"enabled": bool(f_pq.get("configured")), "active": bool(f_pq.get("active")), "remote": f_pq.get("remote") or "", "mode": f_pq.get("mode") or "fast", "block": f_pq.get("block") or "aes-128-gcm", "nodes": list(f_pq.get("nodes") or [])}
            svcs = st.get("services") or {}
            h_ok, h_fail = 0, 0
            for k in ("rathole_server", "nginx", "nginx_config_ok"):
                if k in svcs:
                    if svcs[k] == "yes": h_ok += 1
                    else: h_fail += 1
            for k in ("noise", "backhaul", "frp", "paqet"):
                if svcs.get(k) in ("yes", "no"):
                    if svcs[k] == "yes": h_ok += 1
                    else: h_fail += 1
            ov["health"] = {"ok": h_ok, "fail": h_fail, "nodes": {}}
        else:
            # Fallback baraye panel-haye ghadimi ke status --json nadarand (hamzaman, bedoone doctor-e kond)
            with ThreadPoolExecutor(max_workers=4) as pool:
                f_ls = pool.submit(R, ["ratholectl", "ls"])
                f_nz = pool.submit(R, ["ratholectl", "noise", "status"])
                f_pl = pool.submit(R, ["ratholectl", "plain", "status"])
                f_dr = pool.submit(R, ["ratholectl", "direct", "status"])
                f_gm = pool.submit(R, ["ratholectl", "game", "ls"])
                f_bh = pool.submit(R, ["ratholectl", "backhaul", "status"])
                f_frp = pool.submit(R, ["ratholectl", "frp", "status"])
                f_gre = pool.submit(R, ["ratholectl", "gre", "status"])
                f_pq = pool.submit(R, ["ratholectl", "paqet", "status"])
                r_ls = f_ls.result()
                if r_ls.get("rc") not in (0, None):
                    ov["reachable"] = False; ov["error"] = r_ls.get("err", "") or ("rc=%s" % r_ls.get("rc")); return ov
                ov["nodes"] = parse_iran_ls(r_ls.get("out", ""))
                ov["noise"] = parse_noise_status(f_nz.result().get("out", ""))
                ov["plain"] = parse_plain_status(f_pl.result().get("out", ""))
                ov["direct"] = parse_direct_status(f_dr.result().get("out", ""))
                ov["game"] = parse_game_ls(f_gm.result().get("out", ""))
                ov["backhaul"] = parse_backhaul_status(f_bh.result().get("out", ""))
                ov["frp"] = parse_frp_status(f_frp.result().get("out", ""))
                ov["gre"] = parse_gre_status(f_gre.result().get("out", ""))
                ov["paqet"] = parse_paqet_status(f_pq.result().get("out", ""))
                ov["health"] = {"ok": 0, "fail": 0, "nodes": {}}
    else:
        r = R(["ratholenode", "ls"])
        if r.get("rc") not in (0, None):
            ov["reachable"] = False; ov["error"] = r.get("err", "") or ("rc=%s" % r.get("rc")); return ov
        nls = parse_node_ls(r.get("out", ""))
        ov["main_server"] = nls["server"]; ov["services"] = nls["services"]
        with ThreadPoolExecutor(max_workers=5) as pool:
            f_bls = pool.submit(R, ["ratholenode", "backhaul", "ls"])
            f_st  = pool.submit(R, ["ratholenode", "status", "--json"])
            f_kcp = pool.submit(R, ["ratholenode", "kcp", "status"])
            f_nz  = pool.submit(R, ["ratholenode", "noise", "status"])
            f_bh  = pool.submit(R, ["ratholenode", "backhaul", "status"])
            f_frp = pool.submit(R, ["ratholenode", "frp", "status"])
            f_gre = pool.submit(R, ["ratholenode", "gre", "status"])
            f_pq  = pool.submit(R, ["ratholenode", "paqet", "status"])
            f_xr  = pool.submit(R, ["ratholenode", "xray", "status", "--json"])
            f_ups = pool.submit(R, ["ratholenode", "upstream", "ls"])
            f_ver = pool.submit(R, ["ratholenode", "version"])
            bls = parse_node_ls(f_bls.result().get("out", ""))
            ov["backhaul_services"] = bls["services"]
            try:
                raw = f_st.result().get("out", "") or "{}"
                node_status = json.loads(raw)
                if isinstance(node_status, dict) and "main" in node_status:
                    ov["status"] = node_status
                    ov["main_tunnel"] = node_status.get("main", {}).get("transport", "ws")
            except Exception:
                ov["status"] = {}
            ov["kcp"] = parse_kcp_status(f_kcp.result().get("out", ""))
            ov["noise"] = parse_noise_status(f_nz.result().get("out", ""))
            ov["backhaul"] = parse_backhaul_status(f_bh.result().get("out", ""))
            ov["frp"] = parse_frp_status(f_frp.result().get("out", ""))
            ov["gre"] = parse_gre_status(f_gre.result().get("out", ""))
            ov["paqet"] = parse_paqet_status(f_pq.result().get("out", ""))
            try:
                xraw = f_xr.result().get("out", "") or "{}"
                xdata = json.loads(xraw)
                ov["xray"] = xdata if isinstance(xdata, dict) else {}
            except Exception:
                ov["xray"] = {}
            ups = parse_upstream_ls(f_ups.result().get("out", ""))
            ov["upstreams"] = ups["upstreams"]
            ov["version"] = parse_version(f_ver.result().get("out", ""))
        if not ov.get("status", {}).get("main", {}).get("transport"):
            if ov.get("frp", {}).get("enabled"):
                ov["main_tunnel"] = "frp"
            elif ov.get("backhaul", {}).get("enabled"):
                ov["main_tunnel"] = "backhaul"
            elif ov.get("noise", {}).get("enabled"):
                ov["main_tunnel"] = "noise"
            elif ov.get("kcp", {}).get("enabled"):
                ov["main_tunnel"] = "kcp"
            elif not ov.get("main_tunnel"):
                ov["main_tunnel"] = (ups.get("main") or {}).get("tunnel", ov["kcp"].get("mode", "ws"))
    if name:
        with _metrics_lock:
            _OVERVIEW_CACHE[name] = {
                "role": role,
                "reachable": ov.get("reachable", True),
                "nodes": list(ov.get("nodes") or []),
                "services": list(ov.get("services") or []),
                "backhaul_services": list(ov.get("backhaul_services") or []),
            }
    return ov


def _parse_cli_link_test(res):
    if not isinstance(res, dict):
        return None, False
    out_s = (res.get("out") or "").strip()
    err_s = (res.get("err") or "").strip()
    rc = res.get("rc")
    low = (err_s + "\n" + out_s).lower()
    unsupported = (rc not in (0, None)) and ("dstvr nashenakhte" in low or "unknown" in low or "usage:" in low)
    if out_s.startswith("{"):
        try:
            parsed = json.loads(out_s)
            if isinstance(parsed, dict):
                return parsed, unsupported
        except Exception:
            pass
    if unsupported:
        return None, True
    if rc not in (0, None):
        return {"ok": False, "verdict": "failed", "detail": (err_s or out_s or ("rc=%s" % rc))[:200]}, False
    return None, False


# ---------- HTTP handler ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "ratholehub/0.1"
    timeout = 30

    def _cookies(self):
        raw = self.headers.get("Cookie", "")
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1); out[k] = v
        return out

    def _send(self, code, body, ctype="application/json", extra_headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            # saghf-e andaze-ye body (1 MiB) va jelogiri az Content-Length-e manfi/na-motabar
            if not 0 < n <= 1048576:
                return {}
            obj = json.loads(self.rfile.read(n) or b"{}")
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def log_message(self, *a):
        pass  # sakt

    def _record_http(self, method):
        with _metrics_lock:
            _HTTP_REQS[method] = _HTTP_REQS.get(method, 0) + 1

    def _auth(self, cfg, required_scope="read", mutating=False):
        info = resolve_auth(cfg, self.headers, self._cookies(), check_session)
        if not info:
            self._send(401, {"error": "unauthorized"})
            return None
        if mutating:
            ok_csrf, csrf_err = check_csrf(self.headers, info)
            if not ok_csrf:
                self._send(403, {"error": csrf_err})
                return None
        if not scope_allows(info["scope"], required_scope):
            self._send(403, {"error": "insufficient scope", "required": required_scope, "granted": info["scope"]})
            return None
        self._auth_info = info
        return info

    # ---- GET ----
    def do_GET(self):
        self._record_http("GET")
        cfg = get_config()
        path = urlparse(self.path).path
        if path == "/" or path == "/hub/" or path == "/hub":
            body, ctype = ui_asset("index.html")
            if body is None:
                return self._send(500, {"error": "ui/index.html peyda nashod (nasb-e naghes?)"})
            return self._send(200, body, ctype)
        # asset-haye UI — ham zir '/' va ham zir '/hub/' (nginx hub ra zir /hub/ mizanad).
        # faghat nam-e file-e akhar estefade mishavad va bayad dar UI_FILES bashad.
        if "/ui/" in path:
            asset_name = path.rsplit("/", 1)[-1]
            body, ctype = ui_asset(asset_name)
            if body is not None:
                # font-ha cache-e tulani-tar migirand؛ HTML/CSS/JS no-cache mimanand ta baad az update stale nashavand.
                cc = "public, max-age=86400" if ctype.startswith("font/") else "no-cache"
                return self._send(200, body, ctype, {"Cache-Control": cc})
            return self._send(404, {"error": "not found"})
        if path in ("/api/health", "/hub/api/health"):
            return self._send(200, {"ok": True, "mock": MOCK})
        if path in ("/metrics", "/hub/metrics"):
            p = "/metrics"
        else:
            p = path.replace("/hub", "", 1) if path.startswith("/hub/api") else path
        info = self._auth(cfg, required_scope="read")
        if not info:
            return
        if p == "/metrics":
            return self._metrics()
        if p == "/api/servers":
            return self._send(200, [_public_server(s) for s in get_inventory()])
        if p == "/api/hubstatus":
            return self._send(200, hub_status())
        if p == "/api/config":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._config_view()
        if p == "/api/tokens":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._tokens_list()
        if p == "/api/2fa/status":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._2fa_status()
        if p == "/api/monitor/config":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._monitor_config_get()
        if p == "/api/audit":
            q = parse_qs(urlparse(self.path).query)
            try: lim = max(1, min(500, int(q.get("limit", ["100"])[0])))
            except Exception: lim = 100
            return self._send(200, read_audit(lim))
        if p == "/api/audit/verify":
            return self._send(200, verify_audit_chain(AUDIT_PATH))
        if p == "/api/fleet/drift":
            return self._fleet_drift()
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/status$", p)
        if m:
            return self._status(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/discover$", p)
        if m:
            return self._discover(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/overview$", p)
        if m:
            return self._overview(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/details$", p)
        if m:
            return self._details(m.group(1))
        for pat, fn in (
            (r"^/api/servers/([A-Za-z0-9_-]+)/frpconnect$", self._frpconnect),
            (r"^/api/servers/([A-Za-z0-9_-]+)/kcpconnect$", self._kcpconnect),
            (r"^/api/servers/([A-Za-z0-9_-]+)/noiseconnect$", self._noiseconnect),
            (r"^/api/servers/([A-Za-z0-9_-]+)/backhaulconnect$", self._backhaulconnect),
            (r"^/api/servers/([A-Za-z0-9_-]+)/paqetconnect$", self._paqetconnect),
            (r"^/api/servers/([A-Za-z0-9_-]+)/mainconnect$", self._mainconnect),
        ):
            m = re.match(pat, p)
            if m:
                if not scope_allows(info["scope"], "operate"):
                    return self._send(403, {"error": "insufficient scope", "required": "operate"})
                return fn(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/nodeconnect/([A-Za-z0-9_-]+)$", p)
        if m:
            if not scope_allows(info["scope"], "operate"):
                return self._send(403, {"error": "insufficient scope", "required": "operate"})
            return self._nodeconnect(m.group(1), m.group(2))
        return self._send(404, {"error": "not found"})


    # ---- POST/DELETE ----
    def do_POST(self):
        self._record_http("POST")
        cfg = get_config()
        path = urlparse(self.path).path
        p = path.replace("/hub", "", 1) if path.startswith("/hub/api") else path
        if p == "/api/login":
            ip = self._client_ip()
            if not login_allowed(ip):
                return self._send(429, {"error": "too many attempts; try later"})
            data = self._body_json()
            pw = str(data.get("password", ""))
            if _verify_password(pw, cfg.get("admin_password_sha256", "")):
                totp_cfg = cfg.get("totp") if isinstance(cfg.get("totp"), dict) else {}
                if totp_cfg.get("enabled") and totp_cfg.get("secret"):
                    code = str(data.get("totp") or data.get("code") or "").strip()
                    if not code:
                        return self._send(401, {"error": "totp_required", "totp_required": True})
                    sec = totp_cfg["secret"]
                    step = verify_totp(sec, code, last_step=totp_cfg.get("last_step"))
                    if step is not None:
                        def _set_step(c):
                            if isinstance(c.get("totp"), dict):
                                c["totp"]["last_step"] = step
                            return c
                        update_config(_set_step)
                    else:
                        ok_rec, rem_hashes = consume_recovery_code(totp_cfg.get("recovery_hashes") or [], code)
                        if ok_rec:
                            def _use_rec(c):
                                if isinstance(c.get("totp"), dict):
                                    c["totp"]["recovery_hashes"] = rem_hashes
                                return c
                            update_config(_use_rec)
                            audit_log("admin@" + ip, "hub", "2fa_recovery_used", "remaining=%d" % len(rem_hashes), 0)
                        else:
                            login_record_fail(ip)
                            return self._send(401, {"error": "bad totp", "totp_required": True})
                login_reset(ip)
                tok = make_session_token(cfg)
                return self._send(200, {"ok": True, "token": cfg["api_token"]},
                                  extra_headers={"Set-Cookie": "rhsession=%s; HttpOnly; SameSite=Strict; Path=/" % tok})
            login_record_fail(ip)
            return self._send(401, {"error": "bad password"})

        info = self._auth(cfg, required_scope="read", mutating=True)
        if not info:
            return

        if p == "/api/servers":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._add_server(self._body_json())
        if p == "/api/provision":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._provision(self._body_json())
        if p == "/api/config":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._config_save(self._body_json())
        if p == "/api/tokens":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._token_create(self._body_json())
        if p == "/api/2fa/setup":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._2fa_setup()
        if p == "/api/2fa/enable":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._2fa_enable(self._body_json())
        if p == "/api/2fa/disable":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._2fa_disable(self._body_json())
        if p == "/api/monitor/config":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._monitor_config_save(self._body_json())
        if p == "/api/monitor/diagnose-relay":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._monitor_diagnose_relay(self._body_json())
        if p == "/api/monitor/test":
            if not scope_allows(info["scope"], "admin"):
                return self._send(403, {"error": "insufficient scope", "required": "admin"})
            return self._monitor_test(self._body_json())

        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/action$", p)
        if m:
            d = self._body_json()
            act = str(d.get("action", ""))
            req_scope = "operate" if (act in WRITE_ACTIONS or act == "deploy") else "read"
            if not scope_allows(info["scope"], req_scope):
                return self._send(403, {"error": "insufficient scope", "required": req_scope})
            return self._action(m.group(1), d)
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/link-test$", p)
        if m:
            return self._link_test(m.group(1), self._body_json())
        if p == "/api/ip-tls/prepare":
            if not scope_allows(info["scope"], "operate"):
                return self._send(403, {"error": "insufficient scope", "required": "operate"})
            return self._prepare_ip_tls(self._body_json())
        return self._send(404, {"error": "not found"})

    def do_PUT(self):
        self._record_http("PUT")
        cfg = get_config()
        p = urlparse(self.path).path
        p = p.replace("/hub", "", 1) if p.startswith("/hub/api") else p
        if not self._auth(cfg, required_scope="admin", mutating=True):
            return
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)$", p)
        if m:
            return self._edit_server(m.group(1), self._body_json())
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        self._record_http("DELETE")
        cfg = get_config()
        p = urlparse(self.path).path
        p = p.replace("/hub", "", 1) if p.startswith("/hub/api") else p
        if not self._auth(cfg, required_scope="admin", mutating=True):
            return
        m_tok = re.match(r"^/api/tokens/(tok_[a-f0-9]{12})$", p)
        if m_tok:
            return self._token_revoke(m_tok.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)$", p)
        if m:
            name = m.group(1)
            update_inventory(lambda inv: [s for s in inv if s.get("name") != name])
            audit_log(self._user(), name, "del_server", "delete", 0)
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

    # ---- helpers ----
    def _find(self, name):
        for s in get_inventory():
            if s.get("name") == name:
                return s
        return None

    def _client_ip(self):
        peer_ip = self.client_address[0] if getattr(self, "client_address", None) else "127.0.0.1"
        if peer_ip in ("127.0.0.1", "::1", "localhost"):
            return self.headers.get("X-Real-IP") or peer_ip
        return peer_ip

    def _user(self):
        # hvite user + IP klaint baraye audit
        info = getattr(self, "_auth_info", None)
        ip = self._client_ip()
        if isinstance(info, dict) and info.get("principal"):
            return "%s@%s" % (info["principal"], ip)
        return ip

    def _add_server(self, d):
        name = str(d.get("name", "")); role = str(d.get("role", ""))
        transport = str(d.get("transport", "ssh")).lower()
        if transport not in ("ssh", "api"):
            transport = "ssh"
        proxy = str(d.get("proxy", "")).strip()
        if not valid_proxy_url(proxy):
            return self._send(400, {"error": "invalid proxy"})

        if transport == "api":
            api_url = _norm_agent_url(str(d.get("api_url", "")))
            api_token = str(d.get("api_token", "")).strip()
            if not RE_NAME.match(name) or role not in ("iran", "node") or not valid_agent_url(api_url) or not api_token:
                return self._send(400, {"error": "invalid fields for api transport"})
            srv = {"name": name, "role": role, "transport": "api", "api_url": api_url, "api_token": api_token}
            if d.get("insecure_ssl"): srv["insecure_ssl"] = True
            if proxy: srv["proxy"] = proxy
        else:
            host = str(d.get("host", "")); user = str(d.get("ssh_user", "root"))
            port = str(d.get("ssh_port", "22"))
            if not RE_NAME.match(name) or role not in ("iran", "node") or not RE_HOST.match(host) \
               or not RE_NAME.match(user) or not RE_PORT.match(port):
                return self._send(400, {"error": "invalid fields"})
            srv = {"name": name, "role": role, "transport": "ssh", "host": host,
                   "ssh_user": user, "ssh_port": int(port)}
            if proxy: srv["proxy"] = proxy

        # check-and-append atomic zir-e yek ghofl ta do add-e hamzaman ham-digar ra pak nakonand.
        with _lock:
            inv = get_inventory()
            if any(s.get("name") == name for s in inv):
                return self._send(409, {"error": "name exists"})
            inv.append(srv)
            set_inventory(inv)
        audit_log(self._user(), name, "add_server", f"role={role} transport={transport}", 0)
        return self._send(200, {"ok": True})

    def _provision(self, d):
        # nصب khodkar: ba ramz SSH vasl mishavad, kelid-e hub ra nصب mikonad,
        # scriptha ra deploy mikonad va server ra be hub ezafe mikonad.
        res = provision_server(d)
        audit_log(self._user(), str(d.get("name", "?")), "provision",
                  "provision role=%s host=%s" % (d.get("role", "?"), d.get("host", "?")), res.get("rc"))
        code = 200 if res.get("rc") == 0 else 400
        return self._send(code, res)

    def _config_view(self):

        # hrgz ramz/token ra brnmigrdanim; fght mtaditai bikhtr.
        cfg = get_config()
        tok = cfg.get("api_token", "")
        uproxy = str(cfg.get("update_proxy", "") or "")
        return self._send(200, {
            "listen_host": cfg.get("listen_host"),
            "listen_port": cfg.get("listen_port"),
            "proxy": _redact_proxy_creds(cfg.get("proxy", "")),
            "ssh_key_path": cfg.get("ssh_key_path"),
            "ssh_opts": cfg.get("ssh_opts"),
            "insecure": cfg.get("_insecure", False),
            "api_token_hint": (tok[:4] + "…" + tok[-4:]) if len(tok) >= 8 else "(unset)",
            "totp_enabled": bool((cfg.get("totp") or {}).get("enabled")),
            "scoped_tokens_count": len(cfg.get("tokens") or []),
            "update_channel": cfg.get("update_channel", "stable"),
            "update_relay_mode": cfg.get("update_relay_mode", "auto"),
            "update_proxy": _redact_proxy_creds(uproxy),
            "update_proxy_set": bool(uproxy),
            "update_require_sig": bool(cfg.get("update_require_sig", False)),
            "mock": MOCK,
        })

    def _tokens_list(self):
        cfg = get_config()
        toks = [public_token_view(x) for x in (cfg.get("tokens") or []) if isinstance(x, dict)]
        return self._send(200, {"tokens": toks})

    def _token_create(self, d):
        if not isinstance(d, dict):
            return self._send(400, {"error": "invalid body"})
        name = str(d.get("name", "") or "")
        scope = str(d.get("scope", "read") or "read")
        exp_at = None
        if d.get("expires_days") not in (None, ""):
            try:
                days = int(d["expires_days"])
                if not 1 <= days <= 3650:
                    return self._send(400, {"error": "expires_days must be 1..3650"})
                exp_at = int(time.time()) + days * 86400
            except Exception:
                return self._send(400, {"error": "invalid expires_days"})
        try:
            raw_tok, rec = create_scoped_token(name, scope, expires_at=exp_at)
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        def _add_tok(c):
            toks = list(c.get("tokens") or [])
            toks.append(rec)
            c["tokens"] = toks
            return c
        update_config(_add_tok)
        audit_log(self._user(), "hub", "token_create", "name=%s scope=%s" % (rec["name"], rec["scope"]), 0)
        return self._send(201, {"ok": True, "token": raw_tok, "record": public_token_view(rec)})

    def _token_revoke(self, tok_id):
        removed = {"flag": False}
        def _rm_tok(c):
            toks = list(c.get("tokens") or [])
            kept = [x for x in toks if x.get("id") != tok_id]
            removed["flag"] = len(kept) < len(toks)
            c["tokens"] = kept
            return c
        update_config(_rm_tok)
        if not removed["flag"]:
            return self._send(404, {"error": "token not found"})
        audit_log(self._user(), "hub", "token_revoke", "id=%s" % tok_id, 0)
        return self._send(200, {"ok": True})

    def _2fa_status(self):
        cfg = get_config()
        t = cfg.get("totp") if isinstance(cfg.get("totp"), dict) else {}
        return self._send(200, {
            "enabled": bool(t.get("enabled")),
            "recovery_remaining": len(t.get("recovery_hashes") or []),
        })

    def _2fa_setup(self):
        sec = generate_totp_secret()
        def _set_pending(c):
            c["totp_pending_secret"] = sec
            return c
        update_config(_set_pending)
        return self._send(200, {"ok": True, "secret": sec, "otpauth_uri": totp_provisioning_uri(sec)})

    def _2fa_enable(self, d):
        code = str((d or {}).get("code", "") or "")
        cfg = get_config()
        pending = cfg.get("totp_pending_secret") or ""
        if not pending:
            return self._send(400, {"error": "2fa setup not initiated"})
        step = verify_totp(pending, code)
        if step is None:
            return self._send(400, {"error": "invalid verification code"})
        plain_codes, rec_hashes = generate_recovery_codes(8)
        def _activate(c):
            c["totp"] = {
                "enabled": True,
                "secret": pending,
                "recovery_hashes": rec_hashes,
                "last_step": step,
            }
            c.pop("totp_pending_secret", None)
            return c
        update_config(_activate)
        audit_log(self._user(), "hub", "2fa_enable", "totp+recovery=8", 0)
        return self._send(200, {"ok": True, "recovery_codes": plain_codes})

    def _2fa_disable(self, d):
        d = d if isinstance(d, dict) else {}
        cfg = get_config()
        t = cfg.get("totp") if isinstance(cfg.get("totp"), dict) else {}
        if not t.get("enabled"):
            return self._send(400, {"error": "2fa not enabled"})
        pw = str(d.get("password", "") or "")
        if not _verify_password(pw, cfg.get("admin_password_sha256", "")):
            return self._send(403, {"error": "bad password"})
        code = str(d.get("code", "") or "")
        ok_code = verify_totp(t.get("secret", ""), code, last_step=t.get("last_step")) is not None
        if not ok_code:
            ok_code, _ = consume_recovery_code(t.get("recovery_hashes") or [], code)
        if not ok_code:
            return self._send(401, {"error": "invalid totp or recovery code"})
        def _clear(c):
            c.pop("totp", None)
            c.pop("totp_pending_secret", None)
            return c
        update_config(_clear)
        audit_log(self._user(), "hub", "2fa_disable", "totp disabled", 0)
        return self._send(200, {"ok": True})

    def _monitor_service_active(self, cfg):
        if MOCK:
            return bool(cfg.get("enabled"))
        try:
            r = subprocess.run(["systemctl", "is-active", "--quiet", "ratholemonitor"], timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    def _monitor_config_get(self):
        cur = load_monitor_config(MON_CONF_PATH)
        pub = public_monitor_config(cur)
        pub["service_active"] = self._monitor_service_active(cur)
        return self._send(200, pub)

    def _monitor_config_save(self, d):
        cur = load_monitor_config(MON_CONF_PATH)
        new_cfg, err = validate_monitor_update(cur, d)
        if err:
            return self._send(400, {"error": err})
        save_monitor_config(new_cfg, MON_CONF_PATH)
        if not MOCK and os.path.exists("/etc/systemd/system/ratholemonitor.service"):
            try:
                if new_cfg.get("enabled"):
                    subprocess.run(["systemctl", "enable", "--now", "ratholemonitor"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    subprocess.run(["systemctl", "restart", "ratholemonitor"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                else:
                    subprocess.run(["systemctl", "stop", "ratholemonitor"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                pass
        audit_log(
            self._user(),
            "hub",
            "monitor_config_save",
            "enabled=%s relay_mode=%s chats=%d" % (
                bool(new_cfg.get("enabled")),
                new_cfg.get("relay_mode", "auto"),
                len(new_cfg.get("allowed_chat_ids") or []),
            ),
            0,
        )
        pub = public_monitor_config(new_cfg)
        pub["service_active"] = self._monitor_service_active(new_cfg)
        return self._send(200, {"ok": True, "config": pub})

    def _monitor_diagnose_relay(self, d=None):
        d = d if isinstance(d, dict) else {}
        cur = load_monitor_config(MON_CONF_PATH)
        px = str(d.get("proxy") if "proxy" in d else cur.get("proxy", "") or "").strip()
        inv = get_inventory()
        if MOCK:
            nodes = [s for s in inv if isinstance(s, dict) and s.get("role") == "node"]
            ssh_nodes = [
                {
                    "name": str(s.get("name") or "node"),
                    "host": str(s.get("host") or ""),
                    "ok": True,
                    "latency_ms": round(142.0 + i * 18.0, 1),
                    "error": "",
                }
                for i, s in enumerate(nodes[:5])
            ]
            best = ssh_nodes[0]["name"] if ssh_nodes else None
            px_ok = bool(px)
            rec = "ssh_auto" if best else ("proxy" if px_ok else "none")
            summary = (
                "Direct failed; %d/%d foreign SSH nodes reached Telegram (fastest: %s)."
                % (len(ssh_nodes), len(ssh_nodes), best)
                if best else "Direct failed; no SSH nodes available in inventory."
            )
            return self._send(200, {
                "direct": {"ok": False, "latency_ms": 0.0, "bot_username": "", "error": "mock blocked in Iran"},
                "proxy": {
                    "configured": bool(px),
                    "proxy": redact_secrets(px, [px]),
                    "ok": px_ok,
                    "latency_ms": 95.0 if px_ok else 0.0,
                    "error": "",
                },
                "ssh_nodes": ssh_nodes,
                "recommended_mode": rec,
                "best_ssh_node": best,
                "summary": summary,
            })

        cfg = get_config()
        res = diagnose_relay(
            cur.get("bot_token", ""),
            inv,
            proxy_url=px,
            ssh_key_path=cfg.get("ssh_key_path", ""),
            ssh_opts=cfg.get("ssh_opts") or [],
            api_base=cur.get("api_base", "https://api.telegram.org"),
        )
        return self._send(200, res)

    def _monitor_test(self, d=None):
        cur = load_monitor_config(MON_CONF_PATH)
        tok = str(cur.get("bot_token") or "").strip()
        chats = list(cur.get("allowed_chat_ids") or [])
        if not tok or not chats:
            return self._send(400, {"error": "bot_token and allowed_chat_ids must be configured first"})
        if MOCK:
            audit_log(self._user(), "hub", "monitor_test", "via=mock sent=%d" % len(chats), 0)
            return self._send(200, {"ok": True, "via": "mock", "node": None, "sent": len(chats)})

        cfg = get_config()
        px = str(cur.get("proxy") or "").strip()
        relay_mgr = TelegramRelayManager(
            relay_mode=cur.get("relay_mode", "auto"),
            proxy_url=px,
            inventory_fn=get_inventory,
            ssh_key_path=cfg.get("ssh_key_path", ""),
            ssh_opts=cfg.get("ssh_opts") or [],
            api_base=cur.get("api_base", "https://api.telegram.org"),
        )
        client = TelegramClient(tok, relay_mgr)
        try:
            sent = 0
            for cid in chats:
                client.send_message(cid, "🔔 <b>RatholeEngine Monitor</b>: test delivery from Hub succeeded.", parse_mode="HTML")
                sent += 1
            rt = relay_mgr.active_route()
            audit_log(self._user(), "hub", "monitor_test", "via=%s node=%s sent=%d" % (rt.get("mode"), rt.get("node") or "-", sent), 0)
            return self._send(200, {"ok": True, "via": rt.get("mode"), "node": rt.get("node"), "sent": sent})
        except Exception as e:
            err_s = redact_secrets(str(e), [tok, px])
            audit_log(self._user(), "hub", "monitor_test", "error=" + err_s[:120], 1)
            return self._send(502, {"ok": False, "error": err_s})
        finally:
            relay_mgr.close()

    def _metrics(self):
        inv = get_inventory()
        inv_counts = {"iran": 0, "node": 0}
        for s in inv:
            r = s.get("role")
            inv_counts["iran" if r == "iran" else "node"] += 1
        audit_res = verify_audit_chain(AUDIT_PATH)
        with _metrics_lock:
            cache_snap = dict(_OVERVIEW_CACHE)
            drift_snap = dict(_LAST_DRIFT_SUMMARY) if isinstance(_LAST_DRIFT_SUMMARY, dict) else None
            fails_tot = int(_LOGIN_FAILS_TOTAL)
            reqs_snap = dict(_HTTP_REQS)
        body = render_prometheus_metrics({
            "uptime_seconds": max(0, int(time.time() - _HUB_START)),
            "inventory_counts": inv_counts,
            "overview_cache": cache_snap,
            "drift_summary": drift_snap,
            "audit_total": audit_res.get("total", 0),
            "login_failures_total": fails_tot,
            "http_requests_by_method": reqs_snap,
        })
        return self._send(200, body, ctype="text/plain; version=0.0.4; charset=utf-8")

    def _config_save(self, d):
        # tghiire ramz admin va/ya chrkhshe token API az dakhl panel.
        # kolle read-modify-write zir-e _lock ta ba ensure_hub_key/save-e digar race nakonad.
        with _lock:
            cfg = get_config()
            changed = []
            new_pw = d.get("new_password")
            if new_pw is not None:
                cur = str(d.get("current_password", ""))
                if not _verify_password(cur, cfg.get("admin_password_sha256", "")):
                    return self._send(403, {"error": "current password incorrect"})
                if not RE_PW.match(str(new_pw)):
                    return self._send(400, {"error": "password must be 6-128 chars"})
                cfg["admin_password_sha256"] = _hash_password(str(new_pw))
                changed.append("password")
            new_token = None
            if d.get("rotate_token"):
                new_token = secrets.token_hex(24)
                cfg["api_token"] = new_token
                changed.append("api_token")
            if "proxy" in d:
                if not isinstance(d["proxy"], str):
                    return self._send(400, {"error": "invalid proxy"})
                if "***@" not in d["proxy"]:
                    if not valid_proxy_url(d["proxy"]):
                        return self._send(400, {"error": "invalid proxy"})
                    cfg["proxy"] = d["proxy"].strip(); changed.append("proxy")
            if "update_channel" in d:
                uchan = str(d["update_channel"] or "").strip()
                if not RE_CHAN.match(uchan):
                    return self._send(400, {"error": "invalid update_channel"})
                cfg["update_channel"] = uchan; changed.append("update_channel")
            if "update_relay_mode" in d:
                umode = str(d["update_relay_mode"] or "").strip()
                if umode not in hubupdate.UPDATE_RELAY_MODES:
                    return self._send(400, {"error": "invalid update_relay_mode"})
                cfg["update_relay_mode"] = umode; changed.append("update_relay_mode")
            if "update_proxy" in d:
                if not isinstance(d["update_proxy"], str):
                    return self._send(400, {"error": "invalid update_proxy"})
                if "***@" not in d["update_proxy"]:
                    if not valid_proxy_url(d["update_proxy"]):
                        return self._send(400, {"error": "invalid update_proxy"})
                    cfg["update_proxy"] = d["update_proxy"].strip(); changed.append("update_proxy")
            if "update_require_sig" in d:
                ur = d["update_require_sig"]
                if not isinstance(ur, (bool, int)):
                    return self._send(400, {"error": "invalid update_require_sig"})
                cfg["update_require_sig"] = bool(ur); changed.append("update_require_sig")
            # ssh_key_path: masir-e file (reshte). ssh_opts: HATMAN list-e reshte
            # (chvn _ssh_base list(...)-esh mikonad; reshte be karaktr-ha shekaste mishavad).
            if "ssh_key_path" in d:
                if not isinstance(d["ssh_key_path"], str) or not valid_ssh_key_path(d["ssh_key_path"]):
                    return self._send(400, {"error": "invalid ssh_key_path"})
                cfg["ssh_key_path"] = d["ssh_key_path"]; changed.append("ssh_key_path")
            if "ssh_opts" in d:
                v = d["ssh_opts"]
                if not valid_ssh_opts(v):
                    return self._send(400, {"error": "ssh_opts contains disallowed or invalid options"})
                cfg["ssh_opts"] = v; changed.append("ssh_opts")
            if not changed:
                return self._send(400, {"error": "nothing to change"})
            save_config(cfg)
        audit_log(self._user(), "-", "config_save", ",".join(changed), 0)
        out = {"ok": True, "changed": changed}
        if new_token:
            out["api_token"] = new_token  # tnha bar namayesh token jadid
        return self._send(200, out)

    def _edit_server(self, name, d):
        # viraishe mtaditai atsal (host/user/port) bedoon hazf/afzoodan dvbarh.
        # aval hame-ye field-ha ra etebar-sanji va jam mikonim, sps atomic emal mikonim.
        changes = {}
        if "api_url" in d:
            api_url = _norm_agent_url(str(d["api_url"]))
            if not valid_agent_url(api_url): return self._send(400, {"error": "bad API URL"})
            changes["api_url"] = api_url
        if "api_token" in d and str(d["api_token"]).strip():
            changes["api_token"] = str(d["api_token"]).strip()
        if "proxy" in d:
            px = str(d["proxy"] or "").strip()
            if not valid_proxy_url(px): return self._send(400, {"error": "bad proxy"})
            changes["proxy"] = px
        if "insecure_ssl" in d:
            changes["insecure_ssl"] = bool(d["insecure_ssl"])
        if "host" in d:
            if not RE_HOST.match(str(d["host"])): return self._send(400, {"error": "bad host"})
            changes["host"] = str(d["host"])
        if "public_ip" in d:
            public_ip = str(d["public_ip"] or "").strip()
            if public_ip and not RE_HOST.fullmatch(public_ip):
                return self._send(400, {"error": "bad public IP"})
            changes["public_ip"] = public_ip
        if "ssh_user" in d:
            if not RE_NAME.match(str(d["ssh_user"])): return self._send(400, {"error": "bad user"})
            changes["ssh_user"] = str(d["ssh_user"])
        if "ssh_port" in d:
            if not RE_PORT.match(str(d["ssh_port"])): return self._send(400, {"error": "bad port"})
            changes["ssh_port"] = int(d["ssh_port"])
        if "role" in d:
            if d["role"] not in ("iran", "node"): return self._send(400, {"error": "bad role"})
            changes["role"] = d["role"]
        found = {}
        with _lock:
            inv = get_inventory()
            target = None
            for srv in inv:
                if srv.get("name") == name:
                    target = srv; break
            if not target:
                return self._send(404, {"error": "server not found"})
            if target.get("transport") != "api" and ("api_url" in changes or "api_token" in changes):
                return self._send(400, {"error": "server does not use Agent API"})
            target.update(changes)
            if not target.get("proxy"):
                target.pop("proxy", None)
            found = _public_server(target)
            set_inventory(inv)
        audit_log(self._user(), name, "edit_server", "metadata", 0)
        return self._send(200, {"ok": True, "server": found})

    def _prepare_ip_tls(self, d):
        iran_name = str(d.get("iran", "")); node_name = str(d.get("node", ""))
        if not RE_NAME.match(iran_name) or not RE_NAME.match(node_name):
            return self._send(400, {"error": "invalid server name"})
        iran = self._find(iran_name); node = self._find(node_name)
        if not iran or iran.get("role") != "iran" or not node or node.get("role") != "node":
            return self._send(400, {"error": "iran/node pair not found"})
        if node.get("transport") == "api":
            return self._send(400, {"error": "Public certificate upload requires SSH transport on node"})
        ip = str(iran.get("host", ""))
        try:
            import ipaddress
            ipaddress.IPv4Address(ip)
        except ValueError:
            return self._send(400, {"error": "Iran inventory host must be an IPv4 address"})
        # ip-cert yek vhost/default cert-e IP ezafe mikonad; domain va cert-e omoomi-ye panel ra
        # avaz nemikonad. in invariant baraye node-haye domain-based-e mojood zaroori ast.
        made = run_on_server(iran, ["ratholectl", "ip-cert", ip])
        if made.get("rc") != 0:
            return self._send(200, {"ok": False, **made})
        pub = run_on_server(iran, ["ratholectl", "ip-cert-show", ip])
        pem = pub.get("out", "")
        if (pub.get("rc") != 0 or len(pem) > 65536 or
                not pem.startswith("-----BEGIN CERTIFICATE-----") or
                not pem.rstrip().endswith("-----END CERTIFICATE-----")):
            return self._send(200, {"ok": False, "rc": pub.get("rc", 1), "out": "", "err": "public certificate read failed"})
        cfg = get_config(); trust = "/etc/rathole/ip-root-ca.crt"
        if MOCK:
            rc, err = 0, ""
        else:
            remote = _ssh_base(cfg, node) + ["install", "-D", "-m", "0644", "/dev/stdin", trust]
            try:
                put = subprocess.run(remote, input=pem, capture_output=True, text=True, timeout=30)
                rc, err = put.returncode, _strip_ansi(put.stderr)
            except subprocess.TimeoutExpired:
                rc, err = 124, "SSH timeout while installing public certificate"
            except Exception as e:
                rc, err = 1, str(e)
        audit_log(self._user(), node_name, "ip_tls_prepare", "install public certificate for %s" % ip, rc)
        if rc != 0:
            return self._send(200, {"ok": False, "rc": rc, "out": "", "err": err})
        return self._send(200, {"ok": True, "rc": 0, "server": "%s:443" % ip,
                                "tls_hostname": ip, "tls_trusted_root": trust})

    def _action(self, name, d):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        action = str(d.get("action", "")); args = d.get("args", {}) or {}
        if action == "deploy":
            res = deploy_to_server(s, opts=args)
            audit_log(self._user(), name, "deploy", "github-update (install.sh --update)", res.get("rc"))
            return self._send(200, {"server": name, "cmd": "github-update (install.sh --update)", **res})
        cmd = build_cmd(s.get("role"), action, args)
        if not cmd:
            return self._send(400, {"error": "unknown or invalid action"})
        res = run_on_server(s, cmd)
        safe_cmd = _redact_cmd_for_audit(action, cmd)
        if action in WRITE_ACTIONS:
            audit_log(self._user(), name, action, safe_cmd, res.get("rc"))
        return self._send(200, {"server": name, "cmd": safe_cmd, **res})

    def _details(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        role = s.get("role")
        if role == "iran":
            cmds = [("ls", ["ratholectl", "ls"]), ("kcp status", ["ratholectl", "kcp", "status"]),
                    ("noise status", ["ratholectl", "noise", "status"]),
                    # doctor inja ham ba mohafez: in safhe timeout=30 darad، pas dastoor-e
                    # gir-karde bayad SAMT-E SERVER ham baste shavad، na faghat SSH-e mahalli.
                    ("game ls", ["ratholectl", "game", "ls"]), ("doctor", _diag(["ratholectl", "doctor"], 25))]
        else:
            cmds = [("show", ["ratholenode", "show"]), ("kcp status", ["ratholenode", "kcp", "status"]),
                    ("noise status", ["ratholenode", "noise", "status"]),
                    ("upstream ls", ["ratholenode", "upstream", "ls"]), ("logs", ["ratholenode", "logs", "40"])]
        parts = []
        for label, c in cmds:
            r = run_on_server(s, c, timeout=30)
            body = (r.get("out", "") or "").rstrip()
            if r.get("err"):
                body += ("\n[stderr] " + r["err"].rstrip())
            parts.append("===== %s =====\n%s" % (label, body or "(khali)"))
        return self._send(200, {"server": name, "text": "\n\n".join(parts)})

    def _paqetconnect(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "node":
            return self._send(400, {"error": "paqetconnect fght baraye node kharej ast"})
        show = run_on_server(s, ["ratholenode", "paqet", "show"])
        info = parse_paqet_connect(show.get("out", ""))
        if show.get("rc") != 0 or not info or not info.get("key"):
            return self._send(200, {"ok": False, "error": "paqet roshan nist ya key peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        host_part, _, port_part = info["remote"].rpartition(":")
        inv_host = str(s.get("host") or "").strip()
        if (not host_part or host_part in ("127.0.0.1", "0.0.0.0")) and inv_host:
            host_part = inv_host
        if not RE_HOST.fullmatch(host_part) or not RE_PORT.fullmatch(port_part):
            return self._send(200, {"ok": False, "error": "paqet host/port peida nashod"})
        return self._send(200, {
            "ok": True,
            "remote": "%s:%s" % (host_part, port_part),
            "key": info["key"],
            "mode": info.get("mode", "fast"),
            "block": info.get("block", "aes-128-gcm"),
        })

    def _frpconnect(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "frpconnect fght baraye server iran ast"})
        show = run_on_server(s, ["ratholectl", "frp", "show"])
        match = re.search(r"ratholenode\s+frp\s+on\s+(\S+):(\d{1,5})\s+([A-Za-z0-9._=+/-]{6,255})\s+(tcp|kcp|quic|websocket)\b", show.get("out", ""))
        if show.get("rc") != 0 or not match or not 1 <= int(match[2]) <= 65535:
            return self._send(200, {"ok": False, "error": "FRP token/port peida nashod"})
        host = iran_public_host(s, match[1])
        if not RE_HOST.fullmatch(host):
            return self._send(200, {"ok": False, "error": "FRP host peida nashod"})
        return self._send(200, {"ok": True, "host": host, "port": match[2],
                                "remote": "%s:%s" % (host, match[2]),
                                "token": match[3], "transport": match[4]})

    def _kcpconnect(self, name):
        # az server Iran khatte etesal KCP (remote/key/profile daghigh) ra migirad ta
        # form node bedoon typo por shavad (elate asli 'dasti kar mikard vali panel na').
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "kcpconnect fght baraye server iran ast"})
        # 1) az 'kcp show' faghat key ra migirim (tashkhis IP rooye Iran ba curl momken ast shekast bokhorad).
        show = run_on_server(s, ["ratholectl", "kcp", "show"])
        info = parse_kcp_connect(show.get("out", ""))
        key = (info or {}).get("key") or parse_kcp_key(show.get("out", ""))
        # 2) port/profile/enabled ra az 'kcp status' migirim (motmaen-tar).
        st = parse_kcp_status(run_on_server(s, ["ratholectl", "kcp", "status"]).get("out", ""))
        port = st.get("port") or (info or {}).get("remote", ":443").split(":")[-1] or "443"
        profile = st.get("profile") or (info or {}).get("profile") or "balanced"
        if not key:
            return self._send(200, {"ok": False, "error": "kcp roshan nist ya key peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        # 3) remote = host-e inventory (haman IP-i ke hub baa an be Iran vasl mishavad) + port-e KCP.
        host = iran_public_host(s, (info or {}).get("remote", "").rsplit(":", 1)[0])
        if not host:
            return self._send(200, {"ok": False, "error": "host-e Iran peida nashod"})
        remote = "%s:%s" % (host, port)
        return self._send(200, {"ok": True, "remote": remote, "key": key, "profile": profile})

    def _noiseconnect(self, name):
        # az server Iran khatte etesal noise (port + pubkey) ra migirad ta form node bedoon typo por shavad.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "noiseconnect fght baraye server iran ast"})
        show = run_on_server(s, ["ratholectl", "noise", "show"])
        info = parse_noise_connect(show.get("out", ""))
        if not info or not info.get("pubkey"):
            return self._send(200, {"ok": False, "error": "noise roshan nist ya pubkey peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        # remote = host-e inventory + port-e noise (az khatte connect).
        match = re.search(r"noise\s+on\s+(\S+):\d+", show.get("out", ""))
        host = iran_public_host(s, match[1] if match else "")
        if not host:
            return self._send(200, {"ok": False, "error": "host-e Iran peida nashod"})
        remote = "%s:%s" % (host, info.get("port", "2334"))
        return self._send(200, {"ok": True, "remote": remote, "pubkey": info["pubkey"],
                                "pattern": info.get("pattern", "")})

    def _backhaulconnect(self, name):
        # az server Iran khatte etesal backhaul (domain + token + transport + profile) ra migirad
        # ta form-e node bedoon-e typo por shavad — token dasti copy nashavad.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "backhaulconnect fght baraye server iran ast"})
        show = run_on_server(s, ["ratholectl", "backhaul", "show"])
        info = parse_backhaul_connect(show.get("out", ""))
        if not info or not info.get("token"):
            return self._send(200, {"ok": False, "error": "backhaul roshan nist ya token peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        status = {}
        try:
            status = json.loads(run_on_server(s, ["ratholectl", "status", "--json"]).get("out", "") or "{}")
        except Exception:
            pass
        bh = (status.get("features") or {}).get("backhaul") or {}
        mode = bh.get("mode", "nginx_tls")
        transport = bh.get("transport", info.get("transport", "wssmux"))
        if mode == "direct_ip":
            remote = "%s:%s" % (status.get("public_ip") or s.get("host"), bh.get("port") or "")
            client_transport = transport
        else:
            remote = info.get("domain")
            client_transport = info.get("transport", "wssmux")
        # direct-IP ba wss/wssmux ham TLS darad (khod-e backhaul terminate mikonad، ba gvahi-ye
        # self-signed-e ip-cert). ba pin kardan-e gvahi (--ca)، direct-IP ham verify mishavad.
        tls = mode == "nginx_tls" or client_transport in ("wss", "wssmux")
        out = {"ok": True, "domain": info.get("domain", ""), "remote_addr": remote,
               "mode": mode, "token": info["token"], "transport": client_transport,
               "tls": tls, "encrypted": tls, "verified": mode == "nginx_tls",
               "profile": info.get("profile", "balanced")}
        if mode == "direct_ip" and client_transport in ("wss", "wssmux"):
            ip_tls = status.get("ip_tls") if isinstance(status.get("ip_tls"), dict) else {}
            out["ip_tls_ip"] = ip_tls.get("ip") or status.get("public_ip") or s.get("host") or ""
            out["ca_pin_supported"] = True
        return self._send(200, out)

    def _nodeconnect(self, name, node):
        # az server Iran, meshkhassat-e yek node (name/token/inbound) ra migirad ta betavan
        # ba yek dokme rooye node-e kharej (ya upstream-esh) be-onvan service sim-keshi kard.
        # token dar 'ls' mask ast — pas az 'ratholectl show <node>' migirim.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "nodeconnect fght baraye server iran ast"})
        if not RE_NAME.match(node):
            return self._send(400, {"error": "name-e node namotabar"})
        show = run_on_server(s, ["ratholectl", "show", node])
        info = parse_node_connect(show.get("out", ""))
        if not info:
            return self._send(200, {"ok": False, "error": "node peida nashod ya token/inbound darnayamad",
                                    "raw": show.get("out", "") + show.get("err", "")})
        try:
            result = run_on_server(s, ["ratholectl", "status", "--json"])
            status = json.loads(result.get("out", "") or "{}")
            peer = next((n for n in status.get("nodes", []) if n.get("name") == node), {})
            port = int(peer.get("port", 0))
        except (ValueError, TypeError, AttributeError):
            port = 0
        if result.get("rc") != 0 or not 1 <= port <= 65535:
            return self._send(200, {"ok": False, "error": "port-e Iran peida nashod"})
        return self._send(200, {"ok": True, "name": info["name"], "token": info["token"],
                                "inbound": info["inbound"], "remote_port": str(port),
                                "transport": peer.get("transport") or "ws",
                                "api_token": info.get("api_token", ""),
                                "api_inbound": info.get("api_inbound", "")})

    def _mainconnect(self, name):
        # az server Iran, MAGHSAD-e daghigh-e tunnel-e asli (SERVER) ra migirad ta hangam-e
        # «tanzim tunnel asli» rooye node meghdar-e dorost set shavad. dar halat-e pishfarz
        # (ws+TLS) node bayad be DOMAIN-e omoomi vasl shavad (na host/IP-e SSH-e inventory),
        # chon ratholenode az SERVER ham remote_addr va ham hostname/SNI ra misazad — agar
        # SNI ba cert nakhanad, tunnel bala nemiayad. domain ra az 'status --json' migirim.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "mainconnect fght baraye server iran ast"})
        server, domain = iran_main_server(s)
        result = run_on_server(s, ["ratholectl", "control-path", "show"])
        match = re.search(r"^control_path=(/[^\s]*)$", result.get("out", ""), re.M)
        control_path = match[1] if match else ""
        if result.get("rc") == 0 and "default '/'" in result.get("out", ""):
            control_path = "/"
        if control_path and not re.fullmatch(r"/(?:[A-Za-z0-9_./-]{1,120})?", control_path):
            control_path = ""
        host = iran_public_host(s)
        dial_ip = "%s:443" % host if host else ""
        return self._send(200, {"ok": bool(server), "server": server,
                                "domain": domain, "tls_hostname": domain, "control_path": control_path,
                                "dial_ip": dial_ip, "host": host})

    def _discover(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "discover fght baraye server iran ast"})

        res = run_on_server(s, ["ratholectl", "ls"])
        nodes = []
        for line in (res.get("out", "") or "").splitlines():
            t = line.strip()
            if not t or t.startswith("NAME") or set(t) <= set("- "):
                continue
            parts = t.split()
            if parts and parts[0] not in nodes:
                nodes.append(parts[0])
        return self._send(200, {"server": name, "nodes": nodes, "raw": res.get("out", "")})

    def _status(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        role = s.get("role")
        checks = (["status", "doctor", "kcp_status", "plain_status", "direct_status", "noise_status", "backhaul_status"]
                  if role == "iran" else ["status", "kcp_status", "plain_status", "noise_status", "backhaul_status", "watchdog_status", "adaptive_status", "upstream_ls"])
        out = {}
        for act in checks:
            cmd = build_cmd(role, act, {})
            out[act] = run_on_server(s, cmd) if cmd else {"rc": 1, "err": "n/a"}
        return self._send(200, {"server": name, "role": role, "checks": out})

    def _overview(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        return self._send(200, collect_server_overview(s))

    def _fleet_drift(self):
        global _LAST_DRIFT_SUMMARY
        inv = get_inventory()
        ovs = {}
        if inv:
            workers = min(8, max(1, len(inv)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {s["name"]: pool.submit(collect_server_overview, s) for s in inv if s.get("name")}
                for sname, fut in futs.items():
                    try:
                        ovs[sname] = fut.result()
                    except Exception as e:
                        ovs[sname] = {"server": sname, "reachable": False, "error": str(e)}
        res = compute_fleet_drift(inv, ovs, hub_version=hub_manager_version())
        with _metrics_lock:
            _LAST_DRIFT_SUMMARY = dict(res.get("summary") or {})
        return self._send(200, res)

    def _link_test(self, name, d):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        d = d if isinstance(d, dict) else {}
        cnt_raw = str(d.get("count", "5") if d.get("count") is not None else "5")
        if not RE_COUNT.match(cnt_raw):
            return self._send(400, {"error": "invalid count (1..20)"})
        inv = get_inventory()
        role = s.get("role")

        if role == "iran":
            node = str(d.get("node", "") or "")
            if not RE_NAME.match(node):
                return self._send(400, {"error": "invalid or missing node name"})
            peer = str(d.get("peer", "") or "")
            if peer and not RE_NAME.match(peer):
                return self._send(400, {"error": "invalid peer name"})
            peer_srv = None
            for x in inv:
                if x.get("role") != "iran" and x.get("name") == (peer or node):
                    peer_srv = x
                    break
            iran_cmd = build_iran_cmd("link_test", {"name": node, "count": cnt_raw})
            node_cmd = build_node_cmd("link_test", {"count": cnt_raw}) if peer_srv else None
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_ir = pool.submit(run_on_server, s, iran_cmd)
                f_nd = pool.submit(run_on_server, peer_srv, node_cmd) if peer_srv else None
                iran_raw = f_ir.result()
                node_raw = f_nd.result() if f_nd else None
            iran_json, iran_unsup = _parse_cli_link_test(iran_raw)
            node_json, node_unsup = _parse_cli_link_test(node_raw) if node_raw else (None, False)
            res = synthesize_link_test(node, iran_json, node_json, peer_name=peer_srv["name"] if peer_srv else None)
            if iran_unsup:
                res["unsupported"] = True
            if node_unsup:
                res["node_unsupported"] = True
            return self._send(200, res)

        iran_name = str(d.get("iran", "") or "")
        node_name = str(d.get("node", "") or "")
        if iran_name and not RE_NAME.match(iran_name):
            return self._send(400, {"error": "invalid iran server name"})
        if node_name and not RE_NAME.match(node_name):
            return self._send(400, {"error": "invalid node name"})
        iran_srv = self._find(iran_name) if (iran_name and node_name) else None
        if iran_srv and iran_srv.get("role") != "iran":
            iran_srv = None
        node_cmd = build_node_cmd("link_test", {"count": cnt_raw})
        iran_cmd = build_iran_cmd("link_test", {"name": node_name, "count": cnt_raw}) if iran_srv else None
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_nd = pool.submit(run_on_server, s, node_cmd)
            f_ir = pool.submit(run_on_server, iran_srv, iran_cmd) if iran_srv else None
            node_raw = f_nd.result()
            iran_raw = f_ir.result() if f_ir else None
        node_json, node_unsup = _parse_cli_link_test(node_raw)
        iran_json, iran_unsup = _parse_cli_link_test(iran_raw) if iran_raw else (None, False)
        res = synthesize_link_test(node_name or name, iran_json, node_json, peer_name=name)
        if node_unsup:
            res["unsupported"] = True
        if iran_unsup:
            res["iran_unsupported"] = True
        return self._send(200, res)


# ---------- UI (az disk، na inline) ----------
# UI (HTML/CSS/JS/i18n) be pooshe-ye ui/ montaghel shod ta ba highlight/lint-e vaghei
# virayesh shavad. hanooz "faghat stdlib" ast — hich vabastegi-ye pip ezafe nashod.
#
# AMNIAT: masir HARGEZ az vorodi-ye karbar sakhte nemishavad. yek naghshe-ye SABET az
# masir-e URL be nam-e file darim؛ har chiz-e digar 404 migirad. pas '../' ya masir-e
# motlagh nemitavanad az pooshe-ye ui/ birun beravad.
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
UI_FILES = {
    "index.html":      "text/html",
    "app.css":         "text/css",
    "app.js":          "application/javascript",
    "i18n.js":         "application/javascript",
    "vazirmatn.woff2": "font/woff2",
}
_ui_cache = {}
_ui_lock = threading.Lock()


def ui_asset(name):
    # (body_bytes, content_type) ya (None, None) agar name dar whitelist nabashad.
    ctype = UI_FILES.get(name)
    if ctype is None:
        return None, None
    path = os.path.join(UI_DIR, name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, None
    with _ui_lock:
        hit = _ui_cache.get(name)
        if hit and hit[0] == mtime:
            return hit[1], ctype
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError:
        return None, None
    with _ui_lock:
        _ui_cache[name] = (mtime, body)
    return body, ctype


def main():
    cfg = get_config()
    host = os.environ.get("RATHOLEHUB_HOST", cfg.get("listen_host", "127.0.0.1"))
    port = int(os.environ.get("RATHOLEHUB_PORT", cfg.get("listen_port", 8088)))
    if cfg.get("_insecure"):
        sys.stderr.write(
            "\n[!!] hoshdar amniati: token/rmze pishfrze naamn faal ast.\n"
            "     ghabl az gharar dadn panel psht nginx, config.json ra ba mghadir ghvi bsaz:\n"
            "       api_token, admin_password_sha256\n\n")
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print("ratholehub rooye http://%s:%d (mock=%s)" % (host, port, MOCK))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
