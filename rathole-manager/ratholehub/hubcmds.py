# hubcmds.py — HASSAS-TARIN BAKHSH-E HUB: naghshe-ye action → argv-list.
#
# CHERA joda: hub HARGEZ reshte-ye kham rooye server ejra nemikonad. har action be yek
# LIST-e argv naghshe mishavad va har arg ba yek regex etebarsanji mishavad; SSH har arg
# ra jodagane pass midahad. in file amdan kuchak negah dashte mishavad ta ghabel-e
# morur bashad — moghe-e ezafe kardan-e action-e jadid:
#   1) an ra be build_iran_cmd YA build_node_cmd ezafe kon,
#   2) HAR argument ra ba RE_* etebarsanji kon (hich interpolation-e shl),
#   3) agar minevisad (na faghat mikhanad) be WRITE_ACTIONS ham ezafe kon.
#
# in module be hich chiz-e digar-e hub vabaste nist (faghat re) ta betavan
# mostaghel test-esh kard.

import ipaddress
import re

# ---------- aatbarsnji vrvdi (zd tzrigh) ----------
# nokte: anchor ba \Z (na $) chvn dar Python `$` yek newline-e entehai ra ham
# ghabool mikonad (masalan "trk01\n") — ke mitavanad be command-e SSH/audit tzrigh shavad.
RE_NAME    = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
RE_HOST    = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
# port-e motabar: 1..65535; vorodi ghabl az SSH/API rad mishavad.
_PORT = r"(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])"
RE_PORT    = re.compile(r"^" + _PORT + r"\Z")
RE_PROFILE = re.compile(r"^(balanced|lossy|aggressive)\Z")
RE_IPPORT  = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}:" + _PORT + r"\Z")
RE_KEY     = re.compile(r"^[A-Fa-f0-9]{8,64}\Z")
RE_B64     = re.compile(r"^[A-Za-z0-9+/]{40,64}={0,2}\Z")   # kelid-e omomi-ye noise (base64)
RE_ID      = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
RE_PW      = re.compile(r"^.{6,128}\Z")   # hdaghl 6 karaktr baraye ramz
RE_EMAIL   = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,20}\Z")
RE_CONTROL_PATH = re.compile(r"^(?!.*\.\.)/[A-Za-z0-9_./-]{0,120}\Z")
RE_PATH    = re.compile(r"^(?!.*\.\.)/[A-Za-z0-9_./-]{1,255}\Z")   # masir file gvahi (mtlgh)
RE_SLUG    = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,64}\Z")   # owner/repo-ye GitHub
RE_CHAN    = re.compile(r"^(stable|beta)\Z")                                # kanal-e apdit-e hub
RE_HEADER  = re.compile(r"^[A-Za-z0-9-]{1,40}\Z")   # naam-e header-e masiryabi-ye direct
RE_BH_SRV  = re.compile(r"^(ws|wsmux)\Z")           # transport-e backhaul samt-e Iran (bedoon TLS)
RE_BH_CLI  = re.compile(r"^(wss|wssmux)\Z")         # transport-e backhaul samt-e node (TLS be nginx:443)
RE_BH_ANY  = re.compile(r"^(ws|wsmux|wss|wssmux)\Z") # node: TLS/443 ya direct-IP bedoon TLS
RE_BH_MODE = re.compile(r"^(nginx_tls|direct_ip)\Z")
RE_BH_TOK  = re.compile(r"^[A-Fa-f0-9]{16,64}\Z")   # token-e moshtarak-e backhaul (openssl rand -hex)
# upstream-e reverse-proxy: DAGHIGHAN scheme://host:port — bedoon masir/query/metachar.
# in meghdar mostaghim be conf-e nginx miravad، pas har chiz-e digar rad mishavad.
RE_UPSTREAM = re.compile(r"^https?://[A-Za-z0-9][A-Za-z0-9._-]{0,254}:" + _PORT + r"\Z")
RE_LINES    = re.compile(r"^[0-9]{1,4}\Z")   # tedad-e khat-e log (hadaksar 9999)
RE_FRP_TR   = re.compile(r"^(tcp|kcp|quic|websocket)\Z")
_OCT        = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
RE_IP       = re.compile(r"^" + _OCT + r"\." + _OCT + r"\." + _OCT + r"\." + _OCT + r"\Z")
_RE_IP_CHR  = re.compile(r"^[0-9A-Fa-f:.]{2,45}\Z")
RE_GRE_KEY  = re.compile(r"^[0-9]{1,10}\Z")
RE_MTU      = re.compile(r"^[0-9]{3,4}\Z")
RE_PP_TOGGLE = re.compile(r"^(on|off|status)\Z")
RE_PP_VER    = re.compile(r"^(v1|v2|off|status)\Z")
RE_COUNT     = re.compile(r"^(?:[1-9]|1[0-9]|20)\Z")
RE_CHAIN     = re.compile(r"^(?:ws|noise|kcp|frp|plain)(?:,(?:ws|noise|kcp|frp|plain)){0,4}\Z")
RE_PAQET_MODE  = re.compile(r"^(normal|fast|fast2|fast3)\Z")
RE_PAQET_BLOCK = re.compile(r"^(aes|aes-128|aes-128-gcm|salsa20|xor|sm4|none)\Z")
RE_PAQET_KEY   = re.compile(r"^[A-Za-z0-9._=+/-]{8,255}\Z")
RE_MAC         = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")
RE_IFACE       = re.compile(r"^[A-Za-z0-9._:-]{1,32}\Z")
RE_XRAY_MODE   = re.compile(r"^(reality|xhttp)\Z")
RE_XHTTP_MODE  = re.compile(r"^(auto|packet-up|stream-up|stream-one)\Z")
RE_UUID        = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
RE_HEX_SID     = re.compile(r"^[A-Fa-f0-9]{2,16}\Z")
RE_B64URL      = re.compile(r"^[A-Za-z0-9_-]{40,50}\Z")
RE_DOMAINS_CSV = re.compile(r"^[A-Za-z0-9.-]+(?:,[A-Za-z0-9.-]+){0,31}\Z")


def _valid_ip(val):
    if not isinstance(val, str) or not _RE_IP_CHR.match(val):
        return False
    try:
        ipaddress.ip_address(val)
        return True
    except ValueError:
        return False


def _valid_gre_key(val):
    return isinstance(val, str) and bool(RE_GRE_KEY.match(val)) and 0 <= int(val) <= 4294967295


def _valid_mtu(val):
    return isinstance(val, str) and bool(RE_MTU.match(val)) and 576 <= int(val) <= 1500


_INT_OK_KEYS = frozenset({
    "port", "inbound", "api_port", "remote_port", "lines",
    "interval", "failures", "recoveries", "value", "gre_key", "mtu", "count", "rev",
    "conn", "top", "timeout",
})
_BOOL_OK_KEYS = frozenset({"probe_candidates", "allow_insecure", "tls_verify", "proxy_protocol", "tls"})

class _SafeArgs(dict):
    # wrapper baraye dict: vorodi-haye gheyre-string (list/dict/bool/int baraye esm) be '\x00'
    # tabdil mishavand ta regex-ha bedoon-e TypeError anha ra rad konand.
    def get(self, key, default=""):
        v = super().get(key, default)
        if v is None or v == "":
            return default
        if isinstance(v, str):
            return v
        if key in _BOOL_OK_KEYS:
            if type(v) is bool:
                return "1" if v else "0"
            if type(v) is int and v in (0, 1):
                return str(v)
            return "\x00"
        if key in _INT_OK_KEYS and type(v) is int:
            return str(v)
        return "\x00"


# ---------- defense-in-depth: har dastoor-e tashkhisi ba `timeout` pichide mishavad ----------
# CHERA: vaghti SSH samt-e hub timeout mishavad، subprocess-e mahalli koshte mishavad AMMA
# process-e rooye server ZENDE mimanad. yek dastoor-e gir-karde (masalan probe-e websocket-e
# doctor ta ghabl az v1.6.3 ke rooye 101 baraye hamishe montazer mimand) ba har klik yek
# process-e jadid roo ham jam mikard. `timeout` in ra samt-e SERVER mibandad.
# adad HAMISHE sabet ast — hich vorodi-ye karbar be inja nemiresad.
def _diag(argv, secs=90):
    return ["timeout", str(int(secs))] + argv

# ---------- whitelist dstvrha (bedoon shl dlkhvah) ----------
# har action → sazndhi argumenthaye amn. brmigrdand list arg baraye CLI.
def build_iran_cmd(action, a):
    if not isinstance(a, dict): return None
    a = _SafeArgs(a)
    if action == "ls":         return ["ratholectl", "ls"]
    if action == "doctor":     return _diag(["ratholectl", "doctor"], 60)
    if action == "logs":
        n = str(a.get("lines", "") or "200")
        if not RE_LINES.match(n): return None
        return _diag(["ratholectl", "logs", n], 150)
    if action == "kcp_status": return ["ratholectl", "kcp", "status"]
    if action == "kcp_off":    return ["ratholectl", "kcp", "off"]
    if action == "tune":       return ["ratholectl", "tune"]
    if action == "regen":      return ["ratholectl", "regen"]
    if action == "fakeweb_start":
        port = str(a.get("port", "") or "")
        cmd = ["ratholectl", "fakeweb", "start"]
        if port:
            if not RE_PORT.match(port): return None
            cmd.append(port)
        return cmd
    if action == "fakeweb_stop":   return ["ratholectl", "fakeweb", "stop"]
    if action == "fakeweb_rm":     return ["ratholectl", "fakeweb", "rm"]
    if action == "fakeweb_status": return ["ratholectl", "fakeweb", "status"]
    if action == "restart":        return ["ratholectl", "restart"]
    if action == "status":         return ["ratholectl", "status", "--json"]
    if action == "paths":          return ["ratholectl", "paths"]
    if action == "version":        return ["ratholectl", "version"]
    # ---- damnh / gvahi TLS ----
    if action == "tls_info":   return ["ratholectl", "info"]
    if action == "tls_certs":  return ["ratholectl", "certs"]
    if action == "domain_primary":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        cmd = ["ratholectl", "domain", "primary", d]
        if a.get("certbot"): cmd.append("--certbot")
        em = str(a.get("email","") or "")
        if em:
            if not RE_EMAIL.match(em): return None
            cmd += ["--email", em]
        fc = str(a.get("fullchain","") or "")
        if fc:
            if not RE_PATH.match(fc): return None
            cmd += ["--fullchain", fc]
        ky = str(a.get("key","") or "")
        if ky:
            if not RE_PATH.match(ky): return None
            cmd += ["--key", ky]
        return cmd
    if action == "domain_ls":  return ["ratholectl", "domain", "ls"]
    if action == "domain_rm":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        return ["ratholectl", "domain", "rm", d]
    if action == "domain_add":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        cmd = ["ratholectl", "domain", "add", d]
        if a.get("certbot"): cmd.append("--certbot")
        em = str(a.get("email","") or "")
        if em:
            if not RE_EMAIL.match(em): return None
            cmd += ["--email", em]
        fc = str(a.get("fullchain","") or "")
        if fc:
            if not RE_PATH.match(fc): return None
            cmd += ["--fullchain", fc]
        ky = str(a.get("key","") or "")
        if ky:
            if not RE_PATH.match(ky): return None
            cmd += ["--key", ky]
        return cmd
    if action == "tls_cert":
        domain = a.get("domain", ""); email = str(a.get("email", "") or "")
        if not RE_HOST.match(domain): return None
        cmd = ["ratholectl", "cert", domain]
        if email:
            if not RE_EMAIL.match(email): return None
            cmd.append(email)
        return cmd
    if action == "kcp_show":   return ["ratholectl", "kcp", "show"]
    if action == "kcp_on":
        port = a.get("port", "443"); profile = a.get("profile", "balanced")
        if not RE_PORT.match(str(port)) or not RE_PROFILE.match(str(profile)): return None
        return ["ratholectl", "kcp", "on", str(port), str(profile)]
    # ---- plain: tunnel-e websocket bedoon-e TLS (listener HTTP rooye port jda) ----
    if action == "plain_status": return ["ratholectl", "plain", "status"]
    if action == "plain_show":   return ["ratholectl", "plain", "show"]
    if action == "plain_off":    return ["ratholectl", "plain", "off"]
    if action == "plain_on":
        port = str(a.get("port", "8880") or "8880")
        if not RE_PORT.match(port): return None
        return ["ratholectl", "plain", "on", port]
    # ---- direct-IP: masiryabi ba header rooye port-e sade (bedoon TLS/auth) ----
    if action == "direct_status": return ["ratholectl", "direct", "status"]
    if action == "direct_show":   return ["ratholectl", "direct", "show"]
    if action == "direct_off":    return ["ratholectl", "direct", "off"]
    if action == "direct_on":
        port   = str(a.get("port", "8081") or "8081")
        header = str(a.get("header", "X-Cdn-Id") or "X-Cdn-Id")
        if not RE_PORT.match(port):     return None
        if not RE_HEADER.match(header): return None
        return ["ratholectl", "direct", "on", "--port", port, "--header", header]
    # ---- noise: tunnel-e ramznegari-shode (Noise) rooye instans-e dovom ----
    if action == "noise_status": return ["ratholectl", "noise", "status"]
    if action == "noise_show":   return ["ratholectl", "noise", "show"]
    if action == "noise_off":    return ["ratholectl", "noise", "off"]
    if action == "noise_on":
        port = str(a.get("port", "2334") or "2334")
        if not RE_PORT.match(port): return None
        return ["ratholectl", "noise", "on", port]
    if action in ("noise_node_on", "noise_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "noise", "node", name, ("on" if action == "noise_node_on" else "off")]
    # ---- backhaul: core-e SMUX-e joda posht-e nginx/443 (tak-port hefz mishavad) ----
    if action == "backhaul_status": return ["ratholectl", "backhaul", "status"]
    if action == "backhaul_logs":   return ["ratholectl", "backhaul", "logs"]
    if action == "backhaul_show":   return ["ratholectl", "backhaul", "show"]
    if action == "backhaul_off":    return ["ratholectl", "backhaul", "off"]
    if action == "backhaul_on":
        port      = str(a.get("port", "3080") or "3080")
        transport = a.get("transport", "wsmux") or "wsmux"
        profile   = a.get("profile", "balanced") or "balanced"
        mode      = a.get("mode", "nginx_tls") or "nginx_tls"
        # transport be mode vabaste ast: dar nginx_tls، nginx TLS ra terminate mikonad pas server
        # HATMAN bedoon-e TLS ast (ws/wsmux). dar direct_ip nginx dar masir nist، pas khod-e
        # backhaul mitavanad TLS ra terminate konad (wss/wssmux ba gvahi-ye ip-cert).
        if not RE_PORT.match(port):        return None
        if not RE_PROFILE.match(profile):  return None
        if not RE_BH_MODE.match(mode):     return None
        if mode == "direct_ip":
            if not RE_BH_ANY.match(transport): return None
            if port == "443": return None
        else:
            if not RE_BH_SRV.match(transport): return None
        return ["ratholectl", "backhaul", "on", port, transport, profile, mode]
    if action in ("backhaul_node_on", "backhaul_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "backhaul", "node", name, ("on" if action == "backhaul_node_on" else "off")]
    # ---- reverse-proxy-e gheyre-tunnel: /<name>/ -> upstream-e delkhah ----
    if action == "proxy_ls":  return ["ratholectl", "proxy", "ls"]
    if action == "proxy_rm":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "proxy", "rm", name]
    if action == "proxy_add":
        name = a.get("name", ""); up = a.get("upstream", "")
        # upstream mostaghim be conf-e nginx miravad — pas SAKHT-GIRANE mahdud mishavad:
        # faghat scheme://host:port. hich masir/query/metachar.
        if not RE_NAME.match(name): return None
        if not RE_UPSTREAM.match(up): return None
        return ["ratholectl", "proxy", "add", name, up]
    # ---- frp: core-e reverse-tunnel-e fatedier/frp (frps) ----
    if action == "frp_status": return ["ratholectl", "frp", "status"]
    if action == "frp_show":   return ["ratholectl", "frp", "show"]
    if action == "frp_ready":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "frp", "ready", name]
    if action == "frp_off":    return ["ratholectl", "frp", "off"]
    if action == "frp_on":
        port      = str(a.get("port", "7000") or "7000")
        token     = str(a.get("token", "") or "")
        transport = str(a.get("transport", "tcp") or "tcp")
        if not RE_PORT.match(port): return None
        if token and not RE_KEY.match(token) and not RE_BH_TOK.match(token): return None
        if not RE_FRP_TR.match(transport): return None
        cmd = ["ratholectl", "frp", "on", port]
        if token: cmd.append(token)
        if transport: cmd.append(transport)
        return cmd
    if action in ("frp_node_on", "frp_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "frp", "node", name, ("on" if action == "frp_node_on" else "off")]
    if action == "frp_proxy_protocol":
        ver = str(a.get("version", "status") or "status")
        if not RE_PP_VER.match(ver): return None
        return ["ratholectl", "frp", "proxy-protocol", ver]
    # ---- gre: tunnel-e shabake-ye L3 Linux (ip tunnel / ip6gre) ----
    if action == "gre_status": return ["ratholectl", "gre", "status"]
    if action == "gre_probe":
        peer = str(a.get("peer_ip", "") or "")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(peer) or not RE_NAME.match(name): return None
        return ["ratholectl", "gre", "probe", peer, name]
    if action == "gre_auto_mtu":
        peer = str(a.get("peer_ip", "") or "")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(peer) or not RE_NAME.match(name): return None
        return ["ratholectl", "gre", "auto-mtu", peer, name]
    if action == "gre_off":
        name = str(a.get("name", "") or "")
        cmd = ["ratholectl", "gre", "off"]
        if name:
            if not RE_NAME.match(name): return None
            cmd.append(name)
        return cmd
    if action == "gre_on":
        rem = str(a.get("remote_ip", "") or "")
        tip = str(a.get("tunnel_ip", "10.10.10.1") or "10.10.10.1")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(rem) or not _valid_ip(tip) or not RE_NAME.match(name): return None
        cmd = ["ratholectl", "gre", "on", rem, tip, name]
        gkey = str(a.get("gre_key", "") or "")
        if gkey:
            if not _valid_gre_key(gkey): return None
            if int(gkey) > 0:
                cmd += ["--key", str(int(gkey))]
        mtu = str(a.get("mtu", "") or "")
        if mtu:
            if not _valid_mtu(mtu): return None
            cmd += ["--mtu", str(int(mtu))]
        return cmd
    # ---- service game (SNI rooye 443 + TLS rooye node) ----

    if action == "game_ls":   return ["ratholectl", "game", "ls"]
    if action == "game_proxy_protocol":
        mode = str(a.get("mode", "status") or "status")
        if not RE_PP_TOGGLE.match(mode): return None
        return ["ratholectl", "game", "proxy-protocol", mode]
    if action == "game_show":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "game", "show", name]
    if action == "game_add":
        name = a.get("name", ""); inbound = str(a.get("inbound", "")); sni = a.get("sni", "")
        if not RE_NAME.match(name) or not RE_PORT.match(inbound) or not RE_HOST.match(sni): return None
        return ["ratholectl", "game", "add", name, inbound, sni]
    if action == "game_rm":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "game", "rm", name]
    if action == "game_cert":
        sni = a.get("sni", "")
        if not RE_HOST.match(sni): return None
        return ["ratholectl", "game", "cert", sni]
    # ---- mdirit node aadi ----
    if action == "add_node":
        name = a.get("name", ""); inbound = str(a.get("inbound", "")); api = str(a.get("api_port", "") or "")
        if not RE_NAME.match(name) or not RE_PORT.match(inbound): return None
        cmd = ["ratholectl", "add", name, inbound]
        if api:
            if not RE_PORT.match(api): return None
            cmd += ["--api-port", api]
        return cmd
    if action == "rm_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "rm", name]
    if action == "show_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "show", name]
    if action == "edit_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        cmd = ["ratholectl", "edit", name]
        inbound = str(a.get("inbound", "") or "")
        if inbound:
            if not RE_PORT.match(inbound): return None
            cmd += ["--inbound", inbound]
        api = str(a.get("api_port", "") or "")
        if api:
            if api != "off" and not RE_PORT.match(api): return None
            cmd += ["--api-port", api]
        if len(cmd) == 3: return None  # hich tghiiri dade nashode
        return cmd
    if action == "rename_node":
        old = a.get("old", ""); new = a.get("new", "")
        if not RE_NAME.match(old) or not RE_NAME.match(new): return None
        return ["ratholectl", "rename", old, new]
    if action == "rotate_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "rotate", name]
    if action == "set_config":
        key = a.get("key", ""); val = str(a.get("value", ""))
        if key not in ("domain", "fullchain", "key", "nginx-conf",
                       "fake-port", "sub-port", "control-port",
                       "sub-path", "hub-path"): return None
        if key in ("fake-port", "sub-port", "control-port"):
            if not RE_PORT.match(val): return None
        elif key in ("sub-path", "hub-path"):
            # faghat yek segment-e sade (mesl 'subs' ya '/subs'); slash-haye atraf
            # ghabl az ersal bardashte mishavand. segment-e rezerv niz dar ratholectl
            # (is_reserved_name / normalize_path_seg) rad mishavad.
            seg = val.strip("/")
            if not RE_NAME.match(seg): return None
            val = seg
        elif key in ("domain",):
            if not RE_HOST.match(val): return None
        else:
            # fullchain/key/nginx-conf: masir-e file-e motlagh.
            # HATMAN ba RE_PATH etebar-sanji shavad — SSH argv ra be shl-e remote
            # micharband, pas har metachar-e shl (; | & $() `) inja RCE mishavad.
            if not RE_PATH.match(val): return None
        return ["ratholectl", "set", key, val]
    if action == "backup":
        return ["ratholectl", "backup"]
    if action == "backup_offsite_status":
        return ["ratholectl", "backup", "offsite", "show"]
    if action == "restore_test":
        path = str(a.get("path", "") or "")
        if not RE_PATH.match(path): return None
        return ["ratholectl", "restore", "--test", path]
    if action == "enable":
        return ["ratholectl", "enable"]
    if action == "regen_full":
        return ["ratholectl", "regen"]
    if action == "hub_status":
        return ["ratholectl", "hub", "status"]
    if action == "link_test":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        cnt = str(a.get("count", "5") or "5")
        if not RE_COUNT.match(cnt): return None
        return ["ratholectl", "test", name, "--count", cnt, "--json"]
    if action == "state_history":
        return ["ratholectl", "history", "--json"]
    if action == "state_undo":
        rev = str(a.get("rev", "1") or "1")
        if not RE_COUNT.match(rev): return None
        return ["ratholectl", "undo", rev]
    if action == "state_undo_dry_run":
        rev = str(a.get("rev", "1") or "1")
        if not RE_COUNT.match(rev): return None
        return ["ratholectl", "undo", "--dry-run", rev]
    # ---- paqet: Direct PCK raw TCP+KCP client ----
    if action == "paqet_status": return ["ratholectl", "paqet", "status"]
    if action == "paqet_show":   return ["ratholectl", "paqet", "show"]
    if action == "paqet_off":    return ["ratholectl", "paqet", "off"]
    if action == "paqet_on":
        remote = str(a.get("remote", "") or "")
        key    = str(a.get("key", "") or "")
        mode   = str(a.get("mode", "fast") or "fast")
        block  = str(a.get("block", "aes-128-gcm") or "aes-128-gcm")
        conn   = str(a.get("conn", "1") or "1")
        if not RE_IPPORT.match(remote) or not RE_PAQET_KEY.match(key): return None
        if not RE_PAQET_MODE.match(mode) or not RE_PAQET_BLOCK.match(block): return None
        if not conn.isdigit() or not (1 <= int(conn) <= 256): return None
        cmd = ["ratholectl", "paqet", "on", remote, key, "--mode", mode, "--block", block, "--conn", conn]
        for flag, val, chk in (
            ("--iface", str(a.get("iface", "") or ""), lambda v: bool(RE_IFACE.match(v))),
            ("--local-ip", str(a.get("local_ip", "") or ""), lambda v: bool(RE_IP.match(v))),
            ("--router-mac", str(a.get("router_mac", "") or ""), lambda v: bool(RE_MAC.match(v))),
        ):
            if val:
                if not chk(val): return None
                cmd += [flag, val]
        return cmd
    if action in ("paqet_node_on", "paqet_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "paqet", "node", name, ("on" if action == "paqet_node_on" else "off")]
    # ---- Managed Xray cover scanner ----
    if action == "xray_scan":
        cmd = ["ratholectl", "xray", "scan"]
        domains   = str(a.get("domains", "") or "").strip()
        top       = str(a.get("top", "") or "").strip()
        timeout_v = str(a.get("timeout", "") or "").strip()
        if domains:
            if not RE_DOMAINS_CSV.match(domains): return None
            cmd += ["--domains", domains]
        if top:
            if not top.isdigit() or not (1 <= int(top) <= 50): return None
            cmd += ["--top", top]
        if timeout_v:
            if not timeout_v.isdigit() or not (1 <= int(timeout_v) <= 30): return None
            cmd += ["--timeout", timeout_v]
        cmd.append("--json")
        return cmd
    return None

def build_node_cmd(action, a):
    if not isinstance(a, dict): return None
    a = _SafeArgs(a)
    if action == "control_path_clear": return ["ratholenode", "control-path", "clear"]
    if action == "control_path_set":
        path = a.get("path", "")
        if not isinstance(path, str) or not RE_CONTROL_PATH.match(path): return None
        return ["ratholenode", "control-path", "set", path]
    if action == "show":        return ["ratholenode", "show"]
    if action == "ls":          return ["ratholenode", "ls"]
    if action == "logs":
        n = str(a.get("lines", "") or "200")
        if not RE_LINES.match(n): return None
        return _diag(["ratholenode", "logs", "all", n], 150)
    if action == "upstream_ls": return ["ratholenode", "upstream", "ls"]
    if action == "status":      return ["ratholenode", "status", "--json"]
    if action == "kcp_status":  return ["ratholenode", "kcp", "status"]
    if action == "kcp_off":     return ["ratholenode", "kcp", "off"]
    if action == "plain_status": return ["ratholenode", "plain", "status"]
    if action == "plain_off":    return ["ratholenode", "plain", "off"]
    if action == "plain_on":
        remote = a.get("remote", "")
        if not RE_IPPORT.match(remote): return None
        return ["ratholenode", "plain", "on", remote]
    if action == "noise_status": return ["ratholenode", "noise", "status"]
    if action == "noise_off":    return ["ratholenode", "noise", "off"]
    if action == "noise_on":
        remote = a.get("remote", "")
        pubkey = a.get("pubkey", "")
        if not RE_IPPORT.match(remote): return None
        if not RE_B64.match(pubkey): return None
        cmd = ["ratholenode", "noise", "on", remote, pubkey]
        pattern = a.get("pattern", "")
        if pattern:
            if not RE_HOST.match(pattern): return None
            cmd.append(pattern)
        return cmd
    # ---- backhaul: client-e SMUX ke be domain/443 (nginx → backhaul-server) vasl mishavad ----
    if action == "backhaul_status": return ["ratholenode", "backhaul", "status"]
    if action == "backhaul_logs":   return ["ratholenode", "backhaul", "logs"]
    if action == "backhaul_ls":     return ["ratholenode", "backhaul", "ls"]
    if action == "backhaul_off":    return ["ratholenode", "backhaul", "off"]
    if action == "backhaul_on":
        mode      = a.get("mode", "nginx_tls") or "nginx_tls"
        remote    = a.get("remote_addr", "") or a.get("domain", "")  # payload-e ghadimi
        token     = a.get("token", "")
        transport = a.get("transport", "wssmux") or "wssmux"
        profile   = a.get("profile", "balanced") or "balanced"
        if not RE_BH_MODE.match(mode):       return None
        if not RE_BH_TOK.match(token):       return None
        if not RE_BH_ANY.match(transport):   return None
        if not RE_PROFILE.match(profile):    return None
        if mode == "nginx_tls":
            # client hamishe be nginx:443 mizanad → faghat variant-e TLS-dar، ba host/domain ya host:443.
            if not (RE_HOST.match(remote) or RE_IPPORT.match(remote)) or not RE_BH_CLI.match(transport): return None
        else:
            # direct-IP: endpoint bayad host:port-e sarih bashad. har chahar transport mojaz ast —
            # ws/wsmux bedoon-e ramz، wss/wssmux ba gvahi-ye self-signed-e samt-e Iran.
            if not RE_IPPORT.match(remote): return None
            if transport not in ("ws", "wsmux", "wss", "wssmux"): return None
        cmd = ["ratholenode", "backhaul", "on", remote, token, transport, profile]
        tls_ca = str(a.get("tls_ca", "") or "")
        if tls_ca:
            if not RE_PATH.match(tls_ca): return None
            cmd.extend(["--ca", tls_ca])
        tls_sni = str(a.get("tls_sni", "") or "")
        if tls_sni:
            if not RE_HOST.match(tls_sni): return None
            cmd.extend(["--sni", tls_sni])
        tv = str(a.get("tls_verify", "") or "").strip().lower()
        if tv in ("1", "true", "yes"):
            cmd.append("--verify")
        elif tv not in ("", "0", "false", "no"):
            return None
        return cmd
    if action == "add_bh_svc":
        name = a.get("name", ""); token = a.get("token", ""); inbound = str(a.get("inbound", ""))
        if not RE_NAME.match(name) or not RE_BH_TOK.match(token) or not RE_PORT.match(inbound): return None
        return ["ratholenode", "backhaul", "add-svc", name, token, inbound]
    if action == "rm_bh_svc":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholenode", "backhaul", "rm-svc", name]
    # ---- frp: client-e reverse-tunnel (frpc) ----
    if action == "frp_status": return ["ratholenode", "frp", "status"]
    if action == "frp_off":    return ["ratholenode", "frp", "off"]
    if action == "frp_on":
        rem   = str(a.get("remote", "") or "")
        tok   = str(a.get("token", "") or "")
        tr    = str(a.get("transport", "tcp") or "tcp")
        rport = str(a.get("remote_port", "") or "")
        if not RE_IPPORT.match(rem): return None
        if not RE_KEY.match(tok) and not RE_BH_TOK.match(tok): return None
        if not RE_FRP_TR.match(tr): return None
        if rport:
            if not RE_PORT.match(rport): return None
            return ["ratholenode", "frp", "on", rem, tok, tr, rport]
        return ["ratholenode", "frp", "on", rem, tok, tr]
    if action == "frp_proxy_protocol":
        ver = str(a.get("version", "status") or "status")
        if not RE_PP_VER.match(ver): return None
        return ["ratholenode", "frp", "proxy-protocol", ver]
    # ---- gre: tunnel-e shabake-ye L3 Linux (ip tunnel / ip6gre) ----
    if action == "gre_status": return ["ratholenode", "gre", "status"]
    if action == "gre_probe":
        peer = str(a.get("peer_ip", "") or "")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(peer) or not RE_NAME.match(name): return None
        return ["ratholenode", "gre", "probe", peer, name]
    if action == "gre_auto_mtu":
        peer = str(a.get("peer_ip", "") or "")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(peer) or not RE_NAME.match(name): return None
        return ["ratholenode", "gre", "auto-mtu", peer, name]
    if action == "gre_off":
        name = str(a.get("name", "") or "")
        cmd = ["ratholenode", "gre", "off"]
        if name:
            if not RE_NAME.match(name): return None
            cmd.append(name)
        return cmd
    if action == "gre_on":
        rem  = str(a.get("remote_ip", "") or "")
        tip  = str(a.get("tunnel_ip", "10.10.10.2") or "10.10.10.2")
        name = str(a.get("name", "gre1") or "gre1")
        if not _valid_ip(rem) or not _valid_ip(tip) or not RE_NAME.match(name): return None
        cmd = ["ratholenode", "gre", "on", rem, tip, name]
        gkey = str(a.get("gre_key", "") or "")
        if gkey:
            if not _valid_gre_key(gkey): return None
            if int(gkey) > 0:
                cmd += ["--key", str(int(gkey))]
        mtu = str(a.get("mtu", "") or "")
        if mtu:
            if not _valid_mtu(mtu): return None
            cmd += ["--mtu", str(int(mtu))]
        return cmd
    if action == "backup_offsite_status":
        return ["ratholenode", "backup", "offsite", "show"]
    if action == "restore_test":
        path = str(a.get("path", "") or "")
        if not RE_PATH.match(path): return None
        return ["ratholenode", "restore", "--test", path]
    if action == "link_test":
        cnt = str(a.get("count", "5") or "5")
        if not RE_COUNT.match(cnt): return None
        return ["ratholenode", "test", "--count", cnt, "--json"]
    if action == "migrate":     return ["ratholenode", "migrate"]

    if action == "tune":        return ["ratholenode", "tune"]
    if action == "apply":       return ["ratholenode", "apply"]
    if action == "kcp_on":
        remote = a.get("remote", ""); key = a.get("key", ""); profile = a.get("profile", "balanced")
        if not RE_IPPORT.match(remote) or not RE_KEY.match(key) or not RE_PROFILE.match(profile): return None
        return ["ratholenode", "kcp", "on", remote, key, profile]
    if action == "upstream_kcp_on":
        uid = a.get("id", ""); remote = a.get("remote", ""); key = a.get("key", ""); profile = a.get("profile", "balanced")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote) or not RE_KEY.match(key) or not RE_PROFILE.match(profile): return None
        return ["ratholenode", "upstream", "kcp", uid, "on", remote, key, profile]
    if action == "upstream_kcp_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "kcp", uid, "off"]
    if action == "upstream_kcp_status":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "kcp", uid, "status"]
    # read-only: ayb-yabi-ye upstream (NA dar WRITE_ACTIONS)
    if action == "upstream_logs":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "logs", uid]
    if action == "upstream_status":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "status", uid]
    # ---- hamel-e per-upstream: hamsan-e tunnel-e asli vali baraye har upstream joda ----
    if action == "upstream_plain_on":
        uid = a.get("id", ""); remote = a.get("remote", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote): return None
        return ["ratholenode", "upstream", "plain", uid, "on", remote]
    if action == "upstream_plain_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "plain", uid, "off"]
    if action == "upstream_noise_on":
        uid = a.get("id", ""); remote = a.get("remote", ""); pubkey = a.get("pubkey", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote): return None
        if not RE_B64.match(pubkey): return None
        cmd = ["ratholenode", "upstream", "noise", uid, "on", remote, pubkey]
        pattern = a.get("pattern", "")
        if pattern:
            if not RE_HOST.match(pattern): return None
            cmd.append(pattern)
        return cmd
    if action == "upstream_noise_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "noise", uid, "off"]
    if action == "upstream_ws":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "ws", uid]
    if action == "upstream_apply":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "apply", uid]
    if action == "upstream_restart":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "restart", uid]
    if action == "restart":
        return ["ratholenode", "restart"]
    if action == "version":
        return ["ratholenode", "version"]
    if action == "set_server":
        # sazgari ba UI/API ghadimi: faghat endpoint ra set kon.
        server = a.get("server", "")
        if not (RE_IPPORT.match(server) or RE_HOST.match(server)): return None
        return ["ratholenode", "set", "SERVER", server]
    if action == "set_main":
        # endpoint-e dial + SNI/cert hostname + public trust root atomik.
        server = a.get("server", "")
        hostname = a.get("tls_hostname", "") or ""
        trusted_root = a.get("tls_trusted_root", "") or ""
        if not (RE_IPPORT.match(server) or RE_HOST.match(server)): return None
        if hostname and not RE_HOST.match(hostname): return None
        if trusted_root and not RE_PATH.match(trusted_root): return None
        if trusted_root and not hostname: return None
        return ["ratholenode", "set-main", server, hostname, trusted_root] if trusted_root else (["ratholenode", "set-main", server, hostname] if hostname else ["ratholenode", "set-main", server])
    if action == "watchdog_on":
        iv = str(a.get("interval", "60") or "60")
        if not RE_PORT.match(iv): return None
        return ["ratholenode", "watchdog", "on", iv]
    if action == "watchdog_off":    return ["ratholenode", "watchdog", "off"]
    if action == "watchdog_status": return ["ratholenode", "watchdog", "status"]
    # ---- mdirit service rooye node ----
    if action == "add_svc":
        name = a.get("name", ""); token = a.get("token", ""); inbound = str(a.get("inbound", ""))
        rport = str(a.get("remote_port", "") or "")
        if not RE_NAME.match(name) or not RE_KEY.match(token) or not RE_PORT.match(inbound): return None
        if rport:
            if not RE_PORT.match(rport): return None
            return ["ratholenode", "add-svc", name, token, inbound, rport]
        return ["ratholenode", "add-svc", name, token, inbound]
    if action == "rm_svc":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholenode", "rm-svc", name]
    if action == "upstream_add":
        uid = a.get("id", ""); server = a.get("server", ""); host = a.get("host", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(server): return None
        cmd = ["ratholenode", "upstream", "add", uid, server]
        if host:
            if not RE_HOST.match(host): return None
            cmd.append(host)
        return cmd
    if action == "upstream_add_svc":
        uid = a.get("id", ""); name = a.get("name", ""); token = a.get("token", ""); inbound = str(a.get("inbound", ""))
        if not RE_ID.match(uid) or not RE_NAME.match(name) or not RE_KEY.match(token) or not RE_PORT.match(inbound): return None
        return ["ratholenode", "upstream", "add-svc", uid, name, token, inbound]
    if action == "upstream_rm_svc":
        uid = a.get("id", ""); name = a.get("name", "")
        if not RE_ID.match(uid) or not RE_NAME.match(name): return None
        return ["ratholenode", "upstream", "rm-svc", uid, name]
    if action == "upstream_rm":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "rm", uid]
    # ---- adaptive filtering (Task 8 + M5) ----
    if action == "adaptive_off":    return ["ratholenode", "adaptive", "off"]
    if action == "adaptive_status": return ["ratholenode", "adaptive", "status"]
    if action == "adaptive_test":   return ["ratholenode", "adaptive", "test", "--json"]
    if action == "adaptive_test_all": return ["ratholenode", "adaptive", "test", "--all", "--json"]
    if action == "adaptive_run":    return ["ratholenode", "adaptive", "run"]
    if action == "adaptive_on":
        iv  = str(a.get("interval", "30") or "30")
        fa  = str(a.get("failures", "3") or "3")
        rec = str(a.get("recoveries", "5") or "5")
        if not RE_PORT.match(iv) or not RE_PORT.match(fa) or not RE_PORT.match(rec): return None
        cmd = ["ratholenode", "adaptive", "on", "--interval", iv, "--failures", fa, "--recoveries", rec]
        chain = str(a.get("chain", "") or "").strip()
        if chain:
            parts = chain.split(",")
            if not RE_CHAIN.match(chain) or len(set(parts)) != len(parts): return None
            cmd.extend(["--chain", chain])
        pc = str(a.get("probe_candidates", "") or "").strip().lower()
        if pc in ("1", "true", "yes"):
            cmd.append("--probe-candidates")
        elif pc not in ("", "0", "false", "no"):
            return None
        ai = str(a.get("allow_insecure", "") or "").strip().lower()
        if ai in ("1", "true", "yes"):
            cmd.append("--allow-insecure")
        elif ai not in ("", "0", "false", "no"):
            return None
        return cmd
    # ---- backup endpoints ba health score (M5) ----
    if action == "endpoints_ls":     return ["ratholenode", "endpoints", "ls", "--json"]
    if action == "endpoints_test":   return ["ratholenode", "endpoints", "test", "--json"]
    if action in ("endpoints_add", "endpoints_rm", "endpoints_switch"):
        addr = a.get("addr", "")
        if not RE_IPPORT.match(addr): return None
        sub = action.split("_", 1)[1]
        return ["ratholenode", "endpoints", sub, addr]
    # ---- paqet: Direct PCK raw TCP+KCP server ----
    if action == "paqet_status": return ["ratholenode", "paqet", "status"]
    if action == "paqet_show":   return ["ratholenode", "paqet", "show"]
    if action == "paqet_off":    return ["ratholenode", "paqet", "off"]
    if action == "paqet_on":
        port  = str(a.get("port", "9999") or "9999")
        key   = str(a.get("key", "") or "")
        mode  = str(a.get("mode", "fast") or "fast")
        block = str(a.get("block", "aes-128-gcm") or "aes-128-gcm")
        conn  = str(a.get("conn", "1") or "1")
        if not RE_PORT.match(port): return None
        if key and not RE_PAQET_KEY.match(key): return None
        if not RE_PAQET_MODE.match(mode) or not RE_PAQET_BLOCK.match(block): return None
        if not conn.isdigit() or not (1 <= int(conn) <= 256): return None
        cmd = ["ratholenode", "paqet", "on", port]
        if key:
            cmd.append(key)
        cmd += ["--mode", mode, "--block", block, "--conn", conn]
        for flag, val, chk in (
            ("--iface", str(a.get("iface", "") or ""), lambda v: bool(RE_IFACE.match(v))),
            ("--local-ip", str(a.get("local_ip", "") or ""), lambda v: bool(RE_IP.match(v))),
            ("--router-mac", str(a.get("router_mac", "") or ""), lambda v: bool(RE_MAC.match(v))),
        ):
            if val:
                if not chk(val): return None
                cmd += [flag, val]
        return cmd
    # ---- Managed Xray (REALITY+Vision / XHTTP + Cover Scanner) ----
    if action == "xray_status": return ["ratholenode", "xray", "status", "--json"]
    if action == "xray_off":    return ["ratholenode", "xray", "off"]
    if action == "xray_scan":
        cmd = ["ratholenode", "xray", "scan"]
        domains   = str(a.get("domains", "") or "").strip()
        top       = str(a.get("top", "") or "").strip()
        timeout_v = str(a.get("timeout", "") or "").strip()
        if domains:
            if not RE_DOMAINS_CSV.match(domains): return None
            cmd += ["--domains", domains]
        if top:
            if not top.isdigit() or not (1 <= int(top) <= 50): return None
            cmd += ["--top", top]
        if timeout_v:
            if not timeout_v.isdigit() or not (1 <= int(timeout_v) <= 30): return None
            cmd += ["--timeout", timeout_v]
        cmd.append("--json")
        return cmd
    if action == "xray_uri":
        host = str(a.get("host", "") or "").strip()
        port = str(a.get("port", "") or "").strip()
        cmd = ["ratholenode", "xray", "uri"]
        if port and not host: return None
        if host:
            if not RE_HOST.match(host): return None
            cmd.append(host)
            if port:
                if not RE_PORT.match(port): return None
                cmd.append(port)
        return cmd
    if action == "xray_setup":
        mode = str(a.get("mode", "reality") or "reality")
        if not RE_XRAY_MODE.match(mode): return None
        cmd = ["ratholenode", "xray", "setup", mode]
        port   = str(a.get("port", "") or "").strip()
        listen = str(a.get("listen", "") or "").strip()
        uuid_v = str(a.get("uuid", "") or "").strip()
        dest   = str(a.get("dest", "") or "").strip()
        sni    = str(a.get("sni", "") or "").strip()
        sid    = str(a.get("short_id", "") or "").strip()
        priv_k = str(a.get("private_key", "") or "").strip()
        pub_k  = str(a.get("public_key", "") or "").strip()
        xpath  = str(a.get("path", "") or "").strip()
        xmode  = str(a.get("xhttp_mode", "") or "").strip()
        xhost  = str(a.get("host", "") or "").strip()
        tls_v  = str(a.get("tls", "") or "").strip().lower()
        cert_f = str(a.get("cert", "") or "").strip()
        key_f  = str(a.get("key", "") or "").strip()
        pp_v   = str(a.get("proxy_protocol", "") or "").strip().lower()
        if port:
            if not RE_PORT.match(port): return None
            cmd += ["--port", port]
        if listen:
            if not _valid_ip(listen): return None
            cmd += ["--listen", listen]
        if uuid_v:
            if not RE_UUID.match(uuid_v): return None
            cmd += ["--uuid", uuid_v]
        if mode == "reality":
            if dest:
                if not RE_IPPORT.match(dest): return None
                cmd += ["--dest", dest]
            if sni:
                if not RE_HOST.match(sni): return None
                cmd += ["--sni", sni]
            if sid:
                if not RE_HEX_SID.match(sid): return None
                cmd += ["--short-id", sid]
            if priv_k or pub_k:
                if not (RE_B64URL.match(priv_k) and RE_B64URL.match(pub_k)): return None
                cmd += ["--private-key", priv_k, "--public-key", pub_k]
        else:
            if xpath:
                if not RE_PATH.match(xpath): return None
                cmd += ["--path", xpath]
            if xmode:
                if not RE_XHTTP_MODE.match(xmode): return None
                cmd += ["--mode", xmode]
            if xhost:
                if not RE_HOST.match(xhost): return None
                cmd += ["--host", xhost]
            if tls_v in ("1", "true", "yes"):
                if not (RE_PATH.match(cert_f) and RE_PATH.match(key_f)): return None
                cmd += ["--tls", "--cert", cert_f, "--key", key_f]
            elif tls_v not in ("", "0", "false", "no"):
                return None
        if pp_v in ("1", "true", "yes"):
            cmd.append("--proxy-protocol")
        elif pp_v not in ("", "0", "false", "no"):
            return None
        return cmd
    return None


WRITE_ACTIONS = {
    # iran
    "add_node", "rm_node", "edit_node", "rename_node", "rotate_node",
    "set_config", "kcp_on", "kcp_off", "game_add", "game_rm", "game_cert",
    "tls_cert", "domain_add", "domain_rm", "domain_primary",
    "fakeweb_start", "fakeweb_stop", "fakeweb_rm", "tune", "restart",
    "plain_on", "plain_off",
    "direct_on", "direct_off",
    "noise_on", "noise_off", "noise_node_on", "noise_node_off",
    "backhaul_on", "backhaul_off", "backhaul_node_on", "backhaul_node_off",
    "proxy_add", "proxy_rm",
    "frp_on", "frp_off", "frp_node_on", "frp_node_off", "frp_proxy_protocol",
    "gre_on", "gre_off", "gre_auto_mtu", "game_proxy_protocol",
    "paqet_on", "paqet_off", "paqet_node_on", "paqet_node_off",

    "backup", "state_undo", "enable", "regen_full", "regen",
    # node
    "control_path_set", "control_path_clear", "add_svc", "rm_svc", "add_bh_svc", "rm_bh_svc", "kcp_on", "kcp_off", "apply", "restart", "set_server", "set_main",
    "upstream_add", "upstream_add_svc", "upstream_rm", "upstream_rm_svc",
    "upstream_kcp_on", "upstream_kcp_off", "upstream_apply", "upstream_restart",
    "upstream_plain_on", "upstream_plain_off",
    "upstream_noise_on", "upstream_noise_off", "upstream_ws",

    "watchdog_on", "watchdog_off", "migrate", "deploy",
    "adaptive_on", "adaptive_off", "adaptive_run",
    "endpoints_add", "endpoints_rm", "endpoints_switch",
    "xray_setup", "xray_off",

}

def build_cmd(role, action, args):
    return build_iran_cmd(action, args) if role == "iran" else build_node_cmd(action, args)
