#!/usr/bin/env python3
"""Diagram generator for docs/assets/*.svg.

The hand-authored SVGs predate the FRP/GRE/Backhaul carriers and the REST
Agent, so they no longer match the code. This script regenerates them from a
small DSL so they stay in sync: change the data below, run

    python3 tools/gen_diagrams.py

Style (same as the original hand-drawn set): white background, dark title
banner, per-zone pastel boxes, #334155 data-path arrows, #9333ea dashed
reverse-tunnel arrows, Segoe UI.
"""
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "assets"

INK = "#0f172a"
MUTED = "#475569"
LINE = "#334155"
REV = "#9333ea"
OK = "#16a34a"


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self, width, height, title, subtitle=""):
        self.w = width
        self.h = height
        self.parts = []
        head = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="Segoe UI, Arial, sans-serif">
  <defs>
    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/>
    </marker>
    <marker id="arrU" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{REV}"/>
    </marker>
    <marker id="arrB" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#0284c7"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>
  <rect x="20" y="16" width="{width-40}" height="{60 if subtitle else 46}" rx="8" fill="{INK}"/>
  <text x="{width//2}" y="39" text-anchor="middle" fill="#ffffff" font-size="19" font-weight="bold">{esc(title)}</text>
'''
        if subtitle:
            head += (f'  <text x="{width//2}" y="59" text-anchor="middle" fill="#cbd5e1" '
                     f'font-size="12.5">{esc(subtitle)}</text>\n')
        self.parts.append(head)

    def zone(self, x, y, w, h, fill="#f8fafc", stroke="#94a3b8", rx=12, dash=None, opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity else ""
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.5"{d}{o}/>\n')

    def label(self, x, y, text, size=12.5, color=MUTED, weight="bold", anchor="middle"):
        self.parts.append(
            f'  <text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{esc(text)}</text>\n')

    def badge(self, x, y, w, h, text, fill=INK, color="#ffffff", size=13):
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}"/>\n'
            f'  <text x="{x + w/2}" y="{y + h/2 + 4.5}" text-anchor="middle" font-size="{size}" '
            f'font-weight="bold" fill="{color}">{esc(text)}</text>\n')

    def box(self, x, y, w, title, lines=(), h=None, fill="#e0f2fe", stroke="#0284c7",
            title_color="#075985", line_color="#0c4a6e", size=12.5):
        """Box that grows to fit its title + lines (26px title band, 17px per line)."""
        if h is None:
            h = 26 + 17 * len(lines) + 10
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.5"/>\n')
        self.parts.append(
            f'  <text x="{x + w/2}" y="{y + 22}" text-anchor="middle" font-size="{size}" '
            f'font-weight="bold" fill="{title_color}">{esc(title)}</text>\n')
        for i, line in enumerate(lines):
            self.parts.append(
                f'  <text x="{x + w/2}" y="{y + 41 + i*17}" text-anchor="middle" font-size="11" '
                f'fill="{line_color}">{esc(line)}</text>\n')
        return h

    def arrow(self, x1, y1, x2, y2, color=LINE, dashed=False, marker="arr", width=2.2):
        d = ' stroke-dasharray="7 6"' if dashed else ""
        self.parts.append(
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{width}"{d} marker-end="url(#{marker})"/>\n')

    def note(self, x, y, text, color=MUTED, size=11, anchor="start"):
        self.parts.append(
            f'  <text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'fill="{color}">{esc(text)}</text>\n')

    def raw(self, markup):
        self.parts.append(markup)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / name
        path.write_text("".join(self.parts) + "</svg>\n", encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(path.parent.parent.parent), f"({path.stat().st_size} B)")


# ---------------------------------------------------------------------------
# 1) transport-modes.svg — every carrier and ingress mode
# ---------------------------------------------------------------------------
def transport_modes():
    rows = [
        ("1", "websocket + TLS", "DEFAULT · rathole lane", "#ecfdf5", "#059669", "#065f46",
         "rathole client (node)", ["wss://domain:443", "tls = true → nginx"],
         "nginx :443 (TCP)", ["$http_upgrade on /", "→ rathole control :2333"],
         "nginx (Iran)", ["Let's Encrypt cert"]),
        ("2", "kcp (UDP + FEC)", "parallel · lossy links", "#eff6ff", "#2563eb", "#1e3a8a",
         "kcptun client (node)", ["local :29901.. → UDP", "profile: balanced…"],
         "kcptun server (Iran)", ["UDP :443 (QUIC-like)", "→ control :2333"],
         "none on carrier", ["FEC only; rathole ws", "still inside"]),
        ("3", "plain (no TLS)", "lighter · unencrypted", "#fefce8", "#ca8a04", "#713f12",
         "rathole client (node)", ["http://domain:8880", "tls = false"],
         "nginx :8880 (http)", ["separate listener", "→ control :2333"],
         "none", ["explicit opt-in", "ALLOW_INSECURE"]),
        ("4", "noise (encrypted)", "no TLS / no cert", "#fdf4ff", "#a21caf", "#701a75",
         "rathole client #2 (node)", ["transport = noise", "X25519 pubkey"],
         "rathole-noise (Iran)", ["separate instance", "public port :2334"],
         "noise itself", ["own crypto", "no nginx in path"]),
        ("5", "Backhaul (SMUX)", "separate Go core", "#f0fdf4", "#16a34a", "#14532d",
         "backhaul-client (node)", ["wss / wssmux", "one muxed stream"],
         "backhaul-server (Iran)", ["127.0.0.1:3080", "hardcoded /channel + /tunnel"],
         "nginx (Iran)", ["terminates TLS", "server side stays ws"]),
        ("6", "FRP", "fatedier/frp core", "#fff7ed", "#ea580c", "#7c2d12",
         "frpc (node)", ["transport tcp|kcp|quic|ws", "shared token"],
         "frps (Iran)", ["public port :7000", "proxy → 127.0.0.1"],
         "tcp / quic layer", ["tls only if websocket", "+ nginx"]),
        ("7", "GRE (L3)", "kernel ip tunnel", "#f5f3ff", "#7c3aed", "#4c1d95",
         "node tunnel end", ["10.10.10.2/30", "MTU 1476 · TCPMSS clamp"],
         "Iran tunnel end", ["10.10.10.1/30", "proto 47 (gre)"],
         "none", ["raw L3 underlay", "carries other lanes"]),
        ("8", "FRP + GRE", "hybrid", "#fef2f2", "#dc2626", "#7f1d1d",
         "frpc over GRE IP", ["FRP stream inside GRE", "tcp|kcp|quic|ws"],
         "frps over GRE IP", ["no public FRP port", "L3 link first"],
         "tcp / quic layer", ["verify with gre probe"]),
    ]

    ROW_H = 132
    h = 150 + len(rows) * ROW_H + 220
    s = Svg(1160, h,
            "Transport & ingress modes — 8 carriers, 3 ingress modes",
            "Services, tokens and user paths never change — only the lane that carries the tunnel does.")

    s.label(150, 96, "FOREIGN NODE (client side)")
    s.label(580, 96, "IRAN ENTRY / CORE")
    s.label(1000, 96, "TLS TERMINATION")

    y = 110
    for num, name, tag, fill, stroke, tcol, l_t, l_l, c_t, c_l, r_t, r_l in rows:
        s.zone(20, y, 1120, ROW_H - 14, fill=fill, stroke=stroke)
        s.badge(34, y + 10, 190, 30, f"{num} · {name}")
        s.note(236, y + 30, tag, color=tcol, size=11.5)
        s.box(42, y + 48, 216, l_t, l_l, fill="#ffffff", stroke=stroke,
              title_color=tcol, line_color=stroke, size=11.5)
        s.box(470, y + 48, 240, c_t, c_l, fill="#ffffff", stroke=stroke,
              title_color=tcol, line_color=stroke, size=11.5)
        s.box(900, y + 48, 220, r_t, r_l, fill="#ffffff", stroke=stroke,
              title_color=tcol, line_color=stroke, size=11.5)
        s.arrow(260, y + 82, 466, y + 82)
        s.arrow(712, y + 82, 896, y + 82)
        y += ROW_H

    # ingress modes
    s.zone(20, y + 6, 1120, 168, fill="#f8fafc", stroke="#64748b")
    s.badge(34, y + 18, 300, 30, "INGRESS MODES (not carriers)", fill="#64748b")
    ingress = [
        ("game / SNI", ["443 switches to nginx stream", "TLS terminates on the node", "VLESS + TLS + Vision"]),
        ("direct-IP", ["node chosen by header", "X-Cdn-Id: <node>", "plain HTTP listener"]),
        ("proxy / fakeweb", ["non-tunnel reverse proxy", "/<name>/ → any upstream", "decoy site on :8080"]),
    ]
    x = 42
    for title, lines in ingress:
        s.box(x, y + 58, 340, title, lines, fill="#ffffff", stroke="#64748b",
              title_color="#334155", line_color="#475569", size=12)
        x += 360
    s.note(580, y + 206,
           "Each Iran path belongs to exactly one lane — switching lanes keeps the public path and the Iran-side port.",
           color="#64748b", size=11.5, anchor="middle")
    s.save("transport-modes.svg")


# ---------------------------------------------------------------------------
# 2) architecture.svg — roles, one public port, lanes
# ---------------------------------------------------------------------------
def architecture():
    s = Svg(1160, 760,
            "RatholeEngine — 4 roles, 1 public port",
            "One domain · one certificate · nginx :443 · user traffic routed to a node by URL path.")

    # users
    s.zone(20, 96, 240, 300, fill="#eff6ff", stroke="#2563eb")
    s.label(140, 120, "USERS (IRAN)")
    s.box(40, 132, 200, "Xray / V2Ray client", ["VLESS + WS", "addr = domain:443"], fill="#ffffff",
          stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8")
    s.box(40, 226, 200, "Direct-IP client", ["hidden header", "X-Cdn-Id: <node>"], fill="#ffffff",
          stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8")
    s.box(40, 320, 200, "Browser", ["fake site / panel"], fill="#ffffff",
          stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8")

    # iran server
    s.zone(300, 96, 460, 600, fill="#f0fdf4", stroke="#16a34a")
    s.label(530, 120, "IRAN SERVER — public :443 only")
    s.box(320, 134, 420, "nginx :443", ["TLS termination (Let's Encrypt) · map $uri → backend port"],
          fill="#ffffff", stroke="#16a34a", title_color="#14532d", line_color="#166534")
    s.box(320, 218, 420, "rathole server", ["transport websocket · tls = false · control :2333"],
          fill="#ffffff", stroke="#16a34a", title_color="#14532d", line_color="#166534")
    lanes = [
        ("Backhaul (SMUX lane)", "backhaul-server 127.0.0.1:3080 · /channel + /tunnel"),
        ("FRP lane", "frps :7000 · tcp|kcp|quic|websocket"),
        ("GRE lane", "gre1 10.10.10.1/30 · MTU 1476 · proto 47"),
    ]
    yy = 292
    for name, detail in lanes:
        hh = s.box(320, yy, 420, name, [detail], fill="#ffffff", stroke="#16a34a",
                   title_color="#14532d", line_color="#166534")
        yy += hh + 10
    s.box(320, yy + 4, 420, "Services / inventory", [
        "/trk01 → 127.0.0.1:1001   /nld01 → :1002   /usa01 → :1003",
        "+ <name>_api services (loopback) for panel ↔ node",
    ], fill="#ecfdf5", stroke="#059669", title_color="#065f46", line_color="#047857")

    # nodes
    s.zone(800, 96, 340, 420, fill="#fdf4ff", stroke="#a21caf")
    s.label(970, 120, "FOREIGN NODES — no public port")
    node_y = 134
    for name, path in [("trk01 — Xray", "/trk01 · inbound :2087"),
                       ("nld01 — Xray", "/nld01 · inbound :2087"),
                       ("usa01 — Xray", "/usa01 · inbound :2087")]:
        hh = s.box(820, node_y, 300, name, [path, "outbound-only tunnel"], fill="#ffffff",
                   stroke="#a21caf", title_color="#701a75", line_color="#86198f", size=11.5)
        node_y += hh + 12
    s.note(970, node_y + 18, "each node runs the matching client:", color="#701a75", size=11, anchor="middle")
    s.note(970, node_y + 36, "rathole / backhaul / frpc", color="#701a75", size=11, anchor="middle")

    # internet
    s.zone(800, 536, 340, 160, fill="#f8fafc", stroke="#64748b")
    s.label(970, 560, "OPEN INTERNET")
    s.box(820, 572, 300, "Xray on the node", ["opens VLESS → target"], fill="#ffffff",
          stroke="#64748b", title_color="#334155", line_color="#475569", size=11.5)
    s.box(820, 636, 300, "user traffic exits here", [], fill="#ffffff", stroke="#64748b",
          title_color="#334155", size=10.5)

    # arrows
    s.arrow(240, 163, 316, 163, marker="arr")           # users → nginx
    s.arrow(970, 516, 970, 536, color=REV, dashed=True, marker="arrU")   # nodes → internet
    s.arrow(740, 255, 800, 150, color=REV, dashed=True, marker="arrU")   # node → iran (tunnel)
    s.note(690, 232, "reverse tunnel", color=REV, size=10.5, anchor="end")
    s.note(278, 150, "https / wss 443", color=MUTED, size=10.5, anchor="middle")

    s.note(20, 736, "TLS is terminated only by nginx (except: game/SNI terminates on the node, noise carries its own crypto).",
           color="#64748b", size=11.5)
    s.save("architecture.svg")


# ---------------------------------------------------------------------------
# 3) hub-architecture.svg — control plane, SSH + REST Agent
# ---------------------------------------------------------------------------
def hub_architecture():
    s = Svg(1160, 780,
            "Hub — one control plane, two transports (SSH or REST Agent)",
            "The hub never builds shell strings: every action becomes a validated argv list.")

    s.zone(20, 96, 250, 240, fill="#eff6ff", stroke="#2563eb")
    s.label(145, 120, "ADMIN")
    s.box(40, 132, 210, "Browser UI", ["BEARER token or", "rhsession cookie"], fill="#ffffff",
          stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8")
    s.box(40, 226, 210, "nginx /hub/", ["TLS + public entry", "→ 127.0.0.1:8088"], fill="#ffffff",
          stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8")

    s.zone(300, 96, 400, 560, fill="#f8fafc", stroke="#64748b")
    s.label(500, 120, "HUB (hub.py — stdlib only, loopback)")
    s.box(320, 132, 360, "Handler (ThreadingHTTPServer)", ["auth · login rate-limit · audit log"],
          fill="#ffffff", stroke="#64748b", title_color="#334155", line_color="#475569")
    s.box(320, 206, 360, "hubcmds.py — allow-list", ["action + args → validated argv",
                                                      "every arg checked by RE_* regex"],
          fill="#ffffff", stroke="#64748b", title_color="#334155", line_color="#475569")
    s.box(320, 290, 170, "SSH transport", ["run_on_server", "_ssh_base", "argv, one arg each"],
          fill="#ecfdf5", stroke="#059669", title_color="#065f46", line_color="#047857", size=11.5)
    s.box(510, 290, 170, "REST Agent", ["run_on_agent", "POST /api/exec", "Bearer token"],
          fill="#f5f3ff", stroke="#7c3aed", title_color="#4c1d95", line_color="#5b21b6", size=11.5)
    s.box(320, 398, 360, "Persistent state", ["inventory.json · config.json",
                                               "atomic writes under a lock"],
          fill="#ffffff", stroke="#64748b", title_color="#334155", line_color="#475569", size=11.5)
    s.box(320, 478, 360, "Service controls (v2.0.2)", [
        "carrier + protocol · health test · VLESS config",
        "manage peer · remove both ends",
        "carrier labels show the reported protocol (? = unknown)",
    ], fill="#eff6ff", stroke="#2563eb", title_color="#1e3a8a", line_color="#1d4ed8", size=11.5)

    s.zone(730, 96, 410, 640, fill="#f0fdf4", stroke="#16a34a")
    s.label(935, 120, "MANAGED FLEET (inventory.json)")
    s.box(750, 132, 370, "Iran server #1 (role: iran)", [
        "ratholectl — rathole server + nginx",
        "add/rm node · kcp · noise · backhaul · frp · gre"], fill="#ffffff", stroke="#16a34a",
        title_color="#14532d", line_color="#166534", size=11.5)
    s.box(750, 230, 370, "Iran server #2 … N", ["each fronts its own domain / 443"],
          fill="#ffffff", stroke="#16a34a", title_color="#14532d", line_color="#166534", size=11.5)
    s.box(750, 296, 370, "Foreign node #1 (role: node)", [
        "ratholenode — rathole client",
        "services.conf + bh-services.conf"], fill="#ffffff", stroke="#16a34a",
        title_color="#14532d", line_color="#166534", size=11.5)
    s.box(750, 394, 370, "Foreign node #2 … N", ["outbound-only tunnels"],
          fill="#ffffff", stroke="#16a34a", title_color="#14532d", line_color="#166534", size=11.5)
    s.box(750, 460, 370, "Lifecycle", [
        "deploy_to_server → install.sh --update on the server",
        "snapshot → health check → auto-rollback",
        "audit log: user · server · action · rc"], fill="#ecfdf5", stroke="#059669",
        title_color="#065f46", line_color="#047857", size=11.5)
    s.box(750, 576, 370, "REST Agent (optional)", [
        "ratholeagent.py · rathole-agent.service :8089",
        "GET /api/ping · POST /api/exec (argv, allow-list)"], fill="#f5f3ff", stroke="#7c3aed",
        title_color="#4c1d95", line_color="#5b21b6", size=11.5)

    s.arrow(250, 162, 316, 162)
    s.arrow(250, 250, 316, 250)
    s.arrow(695, 336, 748, 176)
    s.note(700, 268, "ssh", color=MUTED, size=10.5, anchor="middle")
    s.arrow(700, 336, 748, 618, color=REV, dashed=True, marker="arrU")
    s.note(714, 500, "https", color=REV, size=10.5, anchor="middle")

    s.note(20, 700, "Security model: no string interpolation into a shell — the hub only ever sends argv lists, validated before they leave the process.",
           color="#64748b", size=11.5)
    s.save("hub-architecture.svg")


# ---------------------------------------------------------------------------
# 4) state-regenerate-reload.svg
# ---------------------------------------------------------------------------
def state_regenerate():
    s = Svg(1160, 560,
            "Central design principle: state → regenerate → hot-reload",
            "Never hand-edit a generated config — mutate state, regenerate, validate, reload.")

    steps = [
        ("1 · mutate state", ["ratholectl: state.json (jq)", "ratholenode: node.env +",
                              "services.conf + bh-services.conf", "the single source of truth"]),
        ("2 · regenerate()", ["gen_server_toml()", "gen_nginx_conf() (+ stream/SNI)",
                              "gen_client() / gen_backhaul_client_toml()", "write .tmp → cat > file (inode kept)"]),
        ("3 · validate", ["nginx -t (http + stream)", "snapshot known-good first",
                          "gate before touching live nginx"]),
        ("4 · hot-reload", ["systemctl reload nginx", "rathole config_watcher re-reads",
                            "tunnels stay up", "restart only for transport changes"]),
    ]
    x = 20
    for i, (title, lines) in enumerate(steps):
        fill = "#eff6ff" if i < 3 else "#f0fdf4"
        stroke = "#2563eb" if i < 3 else "#16a34a"
        tcol = "#1e3a8a" if i < 3 else "#14532d"
        s.zone(x, 100, 250, 210, fill=fill, stroke=stroke)
        s.label(x + 125, 126, title, color=tcol)
        for j, line in enumerate(lines):
            s.note(x + 20, 156 + j * 20, line, color="#334155", size=11)
        if i < 3:
            s.arrow(x + 250, 205, x + 288, 205)
        x += 290

    s.arrow(880, 310, 880, 366, color="#dc2626", marker="arr")
    s.zone(20, 348, 540, 92, fill="#fef2f2", stroke="#dc2626")
    s.label(290, 374, "fail · 4′ auto-revert", color="#7f1d1d")
    s.note(40, 398, "restore http AND stream conf from the pre-regen snapshot /", color="#991b1b", size=11)
    s.note(40, 418, ".rathole-good.bak — nginx never stays broken", color="#991b1b", size=11)

    s.zone(600, 348, 540, 92, fill="#f0fdf4", stroke="#16a34a")
    s.label(870, 374, "pass · active tunnels survive", color="#14532d")
    s.note(620, 398, "config_watcher re-reads server.toml in place (inode preserved);", color="#166534", size=11)
    s.note(620, 418, "the node prefers hot-reload and only restarts for kcp / noise", color="#166534", size=11)

    s.note(20, 500, "Same pattern for every lane: rathole (ws/kcp/plain/noise), Backhaul (bh-services.conf), FRP (frps.toml), GRE (ip tunnel), and the REST agent (rathole-agent.service).",
           color="#64748b", size=11.5)
    s.save("state-regenerate-reload.svg")


# ---------------------------------------------------------------------------
# 5) architecture-detailed.svg — layer-by-layer reference
# ---------------------------------------------------------------------------
def architecture_detailed():
    s = Svg(1160, 740,
            "Detailed reference — nginx rules, lanes and port ownership",
            "Everything on the Iran side is 127.0.0.1 except :443 (and the optional lane ports you enable).")

    s.zone(20, 96, 360, 352, fill="#eff6ff", stroke="#2563eb")
    s.label(200, 120, "NGINX :443 — L7 (default)")
    rules = [
        ("location = /", "websocket → control backend, else fake site"),
        ("location /<node>", "map $uri → 127.0.0.1:<data port>"),
        ("location /_rh/<hex>", "secret rathole control path"),
        ("location /channel|/tunnel", "→ backhaul-server 127.0.0.1:3080"),
        ("location /sub/", "→ Pasargad subscriptions :2096"),
    ]
    yy = 136
    for r, d in rules:
        hh = s.box(36, yy, 328, r, [d], fill="#ffffff", stroke="#2563eb",
                   title_color="#1e3a8a", line_color="#1d4ed8", size=11)
        yy += hh + 8

    s.zone(400, 96, 340, 352, fill="#f0fdf4", stroke="#16a34a")
    s.label(570, 120, "RATHOLE LANE")
    local = [
        ("control :2333", "ws / kcp / plain / noise"),
        ("data :1001..", "one listener per node"),
        ("*_api services", "panel ↔ node, loopback only"),
        ("server.toml", "transport tls = false"),
    ]
    yy = 136
    for r, d in local:
        hh = s.box(416, yy, 308, r, [d], fill="#ffffff", stroke="#16a34a",
                   title_color="#14532d", line_color="#166534", size=11)
        yy += hh + 8
    s.label(570, 432, "config_watcher hot-reloads in place", size=11, color="#166534")

    s.zone(760, 96, 380, 352, fill="#fdf4ff", stroke="#a21caf")
    s.label(950, 120, "INDEPENDENT LANES")
    indep = [
        ("Backhaul (SMUX)", "127.0.0.1:3080 · /channel + /tunnel"),
        ("FRP", "frps :7000 · tcp|kcp|quic|websocket"),
        ("GRE", "gre1 · 10.10.10.0/30 · MTU 1476"),
        ("REST Agent", "rathole-agent.service :8089"),
    ]
    yy = 136
    for r, d in indep:
        hh = s.box(776, yy, 348, r, [d], fill="#ffffff", stroke="#a21caf",
                   title_color="#701a75", line_color="#86198f", size=11)
        yy += hh + 8
    s.label(950, 432, "start/stop independently of the rathole lane", size=11, color="#86198f")

    s.zone(20, 472, 1120, 196, fill="#f8fafc", stroke="#64748b")
    s.label(580, 498, "PORT MAP — who listens where on the Iran server")
    cols = [
        ("443/tcp", "nginx", "public · TLS", True),
        ("443/udp", "kcptun", "only if kcp is on", False),
        ("8880/tcp", "plain ws", "optional lane", False),
        ("2334/tcp", "rathole-noise", "optional lane", False),
        ("7000/tcp+udp", "frps", "optional lane", False),
        ("8089/tcp", "REST agent", "optional, token", False),
        ("127.0.0.1:2333", "control", "loopback only", False),
        ("127.0.0.1:3080", "backhaul", "loopback only", False),
    ]
    x = 36
    for port, who, note, public in cols:
        fill = "#ecfdf5" if public else "#ffffff"
        stroke = "#059669" if public else "#94a3b8"
        s.box(x, 512, 132, port, [who, note], fill=fill, stroke=stroke,
              title_color="#065f46" if public else "#334155",
              line_color="#047857" if public else "#475569", size=11)
        x += 140
    s.note(580, 626, "green = exposed by default · white = opened only when you enable that lane",
           color="#64748b", size=11.5, anchor="middle")

    s.note(20, 712, "User paths never move between lanes: the nginx map target and the node inbound stay the same when you switch carrier.",
           color="#64748b", size=11.5)
    s.save("architecture-detailed.svg")


if __name__ == "__main__":
    transport_modes()
    architecture()
    hub_architecture()
    state_regenerate()
    architecture_detailed()
    print("done")