#!/usr/bin/env python3
"""Dual-theme Apple Glass SVG diagram generator for docs/assets/*.svg.

Generates both the default Dark Glass diagrams (<name>.svg, used everywhere on
GitHub dark mode and the MkDocs documentation site) and Light Glass variants
(<name>-light.svg, paired via <picture> in README.md):

    python3 tools/gen_diagrams.py
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "assets"
FONT = "Segoe UI, system-ui, -apple-system, Arial, sans-serif"


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


THEMES = {
    "dark": {
        "bg0": "#060b16",
        "bg1": "#0d1528",
        "bg2": "#121c36",
        "dot": "rgba(148,163,184,0.13)",
        "orb1": "rgba(124,58,237,0.22)",
        "orb2": "rgba(10,132,255,0.20)",
        "hdr_fill": "rgba(255,255,255,0.05)",
        "hdr_stroke": "rgba(255,255,255,0.13)",
        "title": "#f8fafc",
        "subtitle": "#94a3b8",
        "ink": "#f1f5f9",
        "text": "#cbd5e1",
        "muted": "#94a3b8",
        "zone_fill": "rgba(15,23,42,0.58)",
        "card_fill": "#0f192e",
        "card_soft": "rgba(255,255,255,0.045)",
        "pill_bg": "#0b1324",
        "line": "#64748b",
        "data": "#38bdf8",
        "rev": "#a78bfa",
        "ok": "#34d399",
        "warn": "#fbbf24",
        "err": "#fb7185",
        "accents": {
            "blue": ("rgba(10,132,255,0.12)", "#38bdf8", "#e0f2fe", "#93c5fd"),
            "green": ("rgba(16,185,129,0.12)", "#34d399", "#d1fae5", "#86efac"),
            "violet": ("rgba(124,58,237,0.14)", "#a78bfa", "#ede9fe", "#c4b5fd"),
            "amber": ("rgba(245,158,11,0.12)", "#fbbf24", "#fef3c7", "#fcd34d"),
            "red": ("rgba(244,63,94,0.12)", "#fb7185", "#ffe4e6", "#fda4af"),
            "slate": ("rgba(148,163,184,0.09)", "#64748b", "#f1f5f9", "#cbd5e1"),
        },
        "ver_bg": "rgba(10,132,255,0.20)",
        "ver_stroke": "rgba(56,189,248,0.45)",
        "ver_fg": "#7dd3fc",
    },
    "light": {
        "bg0": "#f6f8fc",
        "bg1": "#eef2ff",
        "bg2": "#e8f1ff",
        "dot": "rgba(71,85,105,0.10)",
        "orb1": "rgba(124,58,237,0.11)",
        "orb2": "rgba(0,122,255,0.10)",
        "hdr_fill": "rgba(255,255,255,0.86)",
        "hdr_stroke": "rgba(15,23,42,0.11)",
        "title": "#0f172a",
        "subtitle": "#475569",
        "ink": "#0f172a",
        "text": "#334155",
        "muted": "#64748b",
        "zone_fill": "rgba(255,255,255,0.72)",
        "card_fill": "#ffffff",
        "card_soft": "rgba(248,250,252,0.92)",
        "pill_bg": "#ffffff",
        "line": "#475569",
        "data": "#0284c7",
        "rev": "#7c3aed",
        "ok": "#059669",
        "warn": "#d97706",
        "err": "#dc2626",
        "accents": {
            "blue": ("rgba(0,122,255,0.08)", "#007aff", "#0c4a6e", "#1d4ed8"),
            "green": ("rgba(5,150,105,0.08)", "#059669", "#064e3b", "#047857"),
            "violet": ("rgba(124,58,237,0.08)", "#7c3aed", "#4c1d95", "#6d28d9"),
            "amber": ("rgba(217,119,6,0.08)", "#d97706", "#78350f", "#b45309"),
            "red": ("rgba(220,38,38,0.08)", "#dc2626", "#7f1d1d", "#b91c1c"),
            "slate": ("rgba(100,116,139,0.08)", "#64748b", "#1e293b", "#475569"),
        },
        "ver_bg": "rgba(0,122,255,0.11)",
        "ver_stroke": "rgba(0,122,255,0.30)",
        "ver_fg": "#0369a1",
    },
}


class Svg:
    def __init__(self, width: int, height: int, title: str, subtitle: str = "", theme: str = "dark"):
        self.w = width
        self.h = height
        self.theme = theme
        self.t = THEMES[theme]
        self.parts: list[str] = []
        t = self.t
        hdr_h = 66 if subtitle else 50
        sub_svg = (
            f'  <text x="{width / 2}" y="62" text-anchor="middle" fill="{t["subtitle"]}" '
            f'font-size="12.5">{esc(subtitle)}</text>\n'
            if subtitle
            else ""
        )
        self.parts.append(
            f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="{FONT}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{t['bg0']}"/>
      <stop offset="52%" stop-color="{t['bg1']}"/>
      <stop offset="100%" stop-color="{t['bg2']}"/>
    </linearGradient>
    <radialGradient id="orbA" cx="20%" cy="15%" r="55%">
      <stop offset="0%" stop-color="{t['orb1']}"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>
    <radialGradient id="orbB" cx="85%" cy="85%" r="55%">
      <stop offset="0%" stop-color="{t['orb2']}"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>
    <pattern id="dotGrid" width="24" height="24" patternUnits="userSpaceOnUse">
      <circle cx="2" cy="2" r="1.15" fill="{t['dot']}"/>
    </pattern>
    <marker id="arr" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,1 L9,5 L0,9 z" fill="{t['data']}"/>
    </marker>
    <marker id="arrV" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,1 L9,5 L0,9 z" fill="{t['rev']}"/>
    </marker>
    <marker id="arrG" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,1 L9,5 L0,9 z" fill="{t['ok']}"/>
    </marker>
    <marker id="arrR" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,1 L9,5 L0,9 z" fill="{t['err']}"/>
    </marker>
    <marker id="arrN" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,1 L9,5 L0,9 z" fill="{t['line']}"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="url(#bgGrad)"/>
  <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="url(#orbA)"/>
  <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="url(#orbB)"/>
  <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="url(#dotGrid)"/>
  <rect x="20" y="16" width="{width - 40}" height="{hdr_h}" rx="14" fill="{t['hdr_fill']}" stroke="{t['hdr_stroke']}" stroke-width="1.2"/>
  <text x="{width / 2}" y="{41 if subtitle else 46}" text-anchor="middle" fill="{t['title']}" font-size="18.5" font-weight="700">{esc(title)}</text>
{sub_svg}  <rect x="{width - 92}" y="27" width="56" height="22" rx="11" fill="{t['ver_bg']}" stroke="{t['ver_stroke']}" stroke-width="1"/>
  <text x="{width - 64}" y="42" text-anchor="middle" fill="{t['ver_fg']}" font-size="11" font-weight="700">v2.1.0</text>
"""
        )

    def zone(self, x, y, w, h, accent="slate", title=None):
        soft, stroke, title_col, _ = self.t["accents"][accent]
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{self.t["zone_fill"]}" '
            f'stroke="{stroke}" stroke-opacity="0.45" stroke-width="1.3"/>\n'
        )
        if title:
            self.parts.append(
                f'  <text x="{x + 16}" y="{y + 22}" font-size="11" font-weight="700" '
                f'letter-spacing="0.06em" fill="{title_col}">{esc(title)}</text>\n'
            )

    def card(self, x, y, w, title, lines=(), accent="blue", h=None, align="center", size=12.5, soft=False):
        bg_tint, stroke, title_col, sub_col = self.t["accents"][accent]
        fill = bg_tint if soft else self.t["card_fill"]
        if h is None:
            h = 30 + len(lines) * 17 + (10 if lines else 12)
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" fill="{fill}" '
            f'stroke="{stroke}" stroke-opacity="0.58" stroke-width="1.2"/>\n'
        )
        tx = x + w / 2 if align == "center" else x + 14
        anchor = "middle" if align == "center" else "start"
        ty = y + (22 if lines else h / 2 + 4.5)
        self.parts.append(
            f'  <text x="{tx}" y="{ty}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="700" fill="{title_col}">{esc(title)}</text>\n'
        )
        for i, line in enumerate(lines):
            self.parts.append(
                f'  <text x="{tx}" y="{y + 41 + i * 17}" text-anchor="{anchor}" font-size="11" '
                f'fill="{sub_col}">{esc(line)}</text>\n'
            )
        return h

    def pill(self, cx, cy, text, accent="blue", w=None, h=22, size=10.5):
        bg_tint, stroke, fg, _ = self.t["accents"][accent]
        if w is None:
            w = max(56, int(len(text) * size * 0.60 + 18))
        x = cx - w / 2
        y = cy - h / 2
        self.parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{self.t["pill_bg"]}" '
            f'stroke="{stroke}" stroke-opacity="0.65" stroke-width="1"/>\n'
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{bg_tint}"/>\n'
            f'  <text x="{cx}" y="{cy + 3.5}" text-anchor="middle" font-size="{size}" '
            f'font-weight="700" fill="{fg}">{esc(text)}</text>\n'
        )

    def arrow(self, x1, y1, x2, y2, kind="data", dashed=False, width=2.0):
        colors = {
            "data": (self.t["data"], "arr"),
            "rev": (self.t["rev"], "arrV"),
            "ok": (self.t["ok"], "arrG"),
            "err": (self.t["err"], "arrR"),
            "line": (self.t["line"], "arrN"),
        }
        col, marker = colors[kind]
        d = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" '
            f'stroke-width="{width}"{d} marker-end="url(#{marker})"/>\n'
        )

    def path(self, d_attr, kind="data", dashed=False, width=2.0):
        colors = {
            "data": (self.t["data"], "arr"),
            "rev": (self.t["rev"], "arrV"),
            "ok": (self.t["ok"], "arrG"),
            "err": (self.t["err"], "arrR"),
            "line": (self.t["line"], "arrN"),
        }
        col, marker = colors[kind]
        d = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(
            f'  <path d="{d_attr}" fill="none" stroke="{col}" stroke-width="{width}"'
            f'{d} marker-end="url(#{marker})"/>\n'
        )

    def text(self, x, y, txt, size=11, color=None, weight="500", anchor="start"):
        col = color or self.t["muted"]
        self.parts.append(
            f'  <text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{col}">{esc(txt)}</text>\n'
        )

    def line(self, x1, y1, x2, y2, color=None, width=1.2, dashed=False):
        col = color or self.t["line"]
        d = ' stroke-dasharray="4 4"' if dashed else ""
        self.parts.append(
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" '
            f'stroke-opacity="0.55" stroke-width="{width}"{d}/>\n'
        )

    def save(self, stem: str):
        OUT.mkdir(parents=True, exist_ok=True)
        fname = f"{stem}.svg" if self.theme == "dark" else f"{stem}-light.svg"
        path = OUT / fname
        path.write_text("".join(self.parts) + "</svg>\n", encoding="utf-8", newline="\n")
        return path


def emit_both(stem: str, builder):
    for th in ("dark", "light"):
        p = builder(th).save(stem)
        print("wrote", p.relative_to(p.parent.parent.parent), f"({p.stat().st_size} B)")


# ---------------------------------------------------------------------------
# 1) architecture.svg — 4 roles, 1 public port, all lanes
# ---------------------------------------------------------------------------
def build_architecture(theme: str) -> Svg:
    s = Svg(
        1200,
        660,
        "RatholeEngine — 4 Roles, 1 Public Port (:443)",
        "One domain · one TLS cert · URL-path routing to many foreign nodes · SSH & REST Agent control",
        theme,
    )

    # Column 1: Users
    s.zone(24, 100, 240, 396, accent="blue", title="USERS · IRAN")
    s.card(40, 136, 208, "Xray / V2Ray Client", ["VLESS + WebSocket + TLS", "wss://domain:443/trk01"], accent="blue")
    s.card(40, 234, 208, "Direct-IP Client", ["Raw Iran IP · :8081 HTTP", "Header X-Cdn-Id: <node>"], accent="blue")
    s.card(40, 332, 208, "Browser / Web Hub", ["Fake site on /", "Admin Hub on /hub/"], accent="blue")
    s.text(144, 466, "Zero client port config change", size=10.5, anchor="middle")

    # Column 2: Iran Server
    s.zone(322, 100, 496, 396, accent="green", title="IRAN SERVER — PUBLIC :443 DEFAULT")
    s.card(340, 136, 460, "Nginx Edge :443 (HTTPS / Stream SNI)", ["Terminates Let's Encrypt TLS · map $uri -> 127.0.0.1:<port>"], accent="green")
    s.card(340, 214, 460, "Rathole Server (Loopback)", ["ws/kcp/plain/noise · tls = false · secret control /_rh/<hex> -> :2333"], accent="green")

    # 3 compact independent lane cards
    s.card(340, 294, 146, "Backhaul SMUX", ["127.0.0.1:3080", "/channel + /tunnel"], accent="amber", size=11.5)
    s.card(497, 294, 146, "FRP Core", ["frps :7000", "TCP + UDP (kcp/quic)"], accent="amber", size=11.5)
    s.card(654, 294, 146, "GRE L3 Kernel", ["gre1 /30 (proto 47)", "MTU 1476 + TCPMSS"], accent="amber", size=11.5)

    s.card(
        340,
        390,
        460,
        "Services & Node Inventory (state.json)",
        ["/trk01 -> :1001   /nld01 -> :1002   /usa01 -> :1003", "Loopback <name>_api services for panel <-> node sync"],
        accent="green",
        soft=True,
    )

    # Column 3: Foreign Nodes & Internet
    s.zone(876, 100, 300, 344, accent="violet", title="FOREIGN NODES — NO PUBLIC PORT")
    s.card(894, 136, 264, "eu-node1 · Xray + Client", ["/trk01 -> :2087 · outbound tunnel"], accent="violet", size=11.5)
    s.card(894, 214, 264, "de-node2 · Xray + Client", ["/nld01 -> :2087 · Backhaul / FRP"], accent="violet", size=11.5)
    s.card(894, 292, 264, "us-node3 · Xray + Client", ["/usa01 -> :2087 · WS / KCP / GRE"], accent="violet", size=11.5)
    s.text(1026, 392, "Matching clients: rathole / backhaul / frpc", size=10.5, anchor="middle")
    s.text(1026, 412, "services.conf + bh-services.conf", size=10.5, anchor="middle")

    s.zone(876, 464, 300, 152, accent="slate", title="OPEN INTERNET")
    s.card(894, 498, 264, "Xray Exit -> Target", ["Decrypts VLESS & forwards traffic"], accent="slate", size=11.5)

    # Bottom Control Plane Bar (Role 3 & 4)
    s.zone(24, 514, 794, 102, accent="violet", title="MANAGEMENT PLANE — RATHOLEHUB + REST AGENT")
    s.card(40, 546, 370, "RatholeHub (hub.py + Apple Glass UI)", ["SSH key argv OR HTTPS REST API · Ctrl+K · two-sided sync"], accent="violet", size=11.5)
    s.card(430, 546, 370, "REST Agent (ratholeagent.py :8089)", ["Optional SSH-free daemon · Bearer token (0600) · strict allow-list"], accent="violet", size=11.5)

    # Clean Arrows + Pill Labels in gaps
    s.arrow(248, 166, 336, 166, kind="data", width=2.3)
    s.pill(293, 142, "443 TLS", accent="blue", w=62)

    s.arrow(876, 236, 804, 236, kind="rev", dashed=True, width=2.4)
    s.pill(846, 210, "Reverse", accent="violet", w=66)

    s.arrow(1026, 444, 1026, 494, kind="ok", width=2.2)
    s.path("M 818 566 L 846 566 L 846 416 L 872 416", kind="rev", dashed=True, width=1.9)
    s.pill(846, 490, "SSH / Agent", accent="violet", w=84)

    s.text(
        24,
        640,
        "TLS terminates at Nginx (except Game/SNI on node & Noise own crypto). State changes regenerate configs in place preserving inodes.",
        size=11,
    )
    return s


# ---------------------------------------------------------------------------
# 2) transport-modes.svg — compact 4x2 grid + 3 ingress cards
# ---------------------------------------------------------------------------
def build_transport_modes(theme: str) -> Svg:
    s = Svg(
        1200,
        740,
        "Transport & Ingress Modes — 8 Carriers, 3 Ingress Modes",
        "User URL paths and node inbound ports never change when switching tunnel carriers.",
        theme,
    )

    carriers = [
        ("1 · WebSocket + TLS", "DEFAULT · RATHOLE", "green",
         "wss://domain:443 -> Nginx TLS -> control /_rh/<hex> :2333",
         "Server stays tls = false; traffic blends with HTTPS on :443."),
        ("2 · KCP (UDP + FEC)", "LOSSY LINKS · QUIC-LIKE", "blue",
         "kcptun client :29901.. -> UDP :443 -> rathole :2333",
         "Profiles balanced/lossy/aggressive; immune to TCP-over-TCP."),
        ("3 · Plain WebSocket", "NO-TLS HTTP · OPT-IN", "amber",
         "http://domain:8880 -> Nginx HTTP -> control /_rh/<hex>",
         "Lighter transport without TLS overhead (explicit opt-in)."),
        ("4 · Noise (X25519)", "ENCRYPTED · NO CERT", "violet",
         "rathole-noise client -> TCP :2334 rathole-noise server",
         "Dedicated encrypted instance; bypasses Nginx completely."),
        ("5 · Backhaul (SMUX)", "DUAL-CORE · HIGH CONCURRENCY", "green",
         "wss/wssmux -> Nginx /channel + /tunnel -> 127.0.0.1:3080",
         "Go core w/ uTLS Chrome fingerprint & separate bh-services.conf."),
        ("6 · FRP Core (fatedier/frp)", "TCP · KCP · QUIC · WS", "amber",
         "frpc -> frps :7000/TCP (tcp/ws) + :7000/UDP (kcp/quic)",
         "v2.0.5 preserves selected frp_transport & auto-opens UFW UDP."),
        ("7 · GRE (Kernel L3)", "IP TUNNEL · PROTO 47", "violet",
         "Node 10.10.10.2/30 <-> Iran 10.10.10.1/30 (gre1)",
         "Direct Linux kernel L3 link with MTU 1476 & iptables TCPMSS."),
        ("8 · FRP + GRE Hybrid", "RESILIENT L3 + MUX", "red",
         "frpc over GRE IP -> frps bound inside 10.10.10.0/30",
         "No public FRP port exposed; QUIC/KCP mux inside GRE packets."),
    ]

    col_w = 568
    row_h = 104
    for idx, (title, tag, acc, flow, note) in enumerate(carriers):
        col = idx % 2
        row = idx // 2
        x = 24 + col * (col_w + 16)
        y = 100 + row * (row_h + 12)
        bg_tint, stroke, title_col, sub_col = s.t["accents"][acc]
        s.parts.append(
            f'  <rect x="{x}" y="{y}" width="{col_w}" height="{row_h}" rx="12" fill="{s.t["card_fill"]}" '
            f'stroke="{stroke}" stroke-opacity="0.52" stroke-width="1.2"/>\n'
        )
        s.pill(x + 96, y + 24, title, accent=acc, w=168, h=24, size=11)
        s.text(x + col_w - 16, y + 28, tag, size=10, color=sub_col, weight="700", anchor="end")
        s.text(x + 18, y + 58, flow, size=11.5, color=s.t["ink"], weight="600")
        s.text(x + 18, y + 82, note, size=10.5, color=s.t["muted"])

    # Bottom Ingress Zone
    iy = 568
    s.zone(24, iy, 1152, 146, accent="slate", title="USER INGRESS MODES (NOT TUNNEL CARRIERS)")
    ingress = [
        ("Game / SNI (L4 Passthrough)", ["Nginx stream on :443 passes TLS raw", "Cert + VLESS Vision live on node"]),
        ("Direct-IP (:8081 HTTP)", ["Connect directly to Iran IP (no domain)", "Hidden header X-Cdn-Id: <node> routes"]),
        ("Proxy & Fakeweb", ["/name/ reverse-proxy without rathole", "Decoy site fallback served on :8080"]),
    ]
    for i, (t, lines) in enumerate(ingress):
        s.card(42 + i * 378, iy + 36, 360, t, lines, accent="blue" if i < 2 else "slate", size=12)

    return s


# ---------------------------------------------------------------------------
# 3) hub-architecture.svg — Hub + Security + SSH/Agent + v2.0.5 UI
# ---------------------------------------------------------------------------
def build_hub_architecture(theme: str) -> Svg:
    s = Svg(
        1200,
        690,
        "RatholeHub — Control Plane Architecture (SSH + REST Agent)",
        "Pure Python stdlib backend + offline Apple Glass UI · Never runs raw shell strings.",
        theme,
    )

    # Admin column
    s.zone(24, 100, 240, 326, accent="blue", title="ADMIN")
    s.card(40, 138, 208, "Browser UI (v2.1.0)", ["Apple Glass Light/Dark", "Offline Vazirmatn · ⌘K", "KPI + Live Filters"], accent="blue")
    s.card(40, 260, 208, "Nginx /hub/", ["Terminates TLS on :443", "-> 127.0.0.1:8088", "Or SSH local forward"], accent="blue")
    s.text(144, 404, "HMAC cookie or Bearer token", size=10.5, anchor="middle")

    # Hub column
    s.zone(316, 100, 444, 536, accent="violet", title="RATHOLEHUB (hub.py — stdlib only)")
    s.card(336, 136, 404, "ThreadingHTTPServer Handler", ["Rate-limited auth (5/5m) · parallel fetch + TTL cache"], accent="violet")
    s.card(336, 212, 404, "hubcmds.py — Security Allow-List", ["Maps action + RE_* validated args -> exact argv list"], accent="violet")
    s.card(336, 290, 194, "SSH Transport", ["_ssh_base + shlex", "Optional proxy bridge"], accent="green", size=11.5)
    s.card(546, 290, 194, "REST Agent Client", ["POST /api/exec JSON", "TLS or insecure_ssl opt"], accent="blue", size=11.5)
    s.card(336, 386, 404, "Locked State & Redacted Audit Log", ["inventory.json · config.json · audit.log (masked secrets)"], accent="slate")
    s.card(
        336,
        464,
        404,
        "Per-Node & Service Controls (v2.1.0)",
        ["Inline carrier selector w/ auto-revert on node sync failure", "⋯ menu: carrier/proto · doctor · VLESS · peer · remove pair"],
        accent="blue",
        soft=True,
    )

    # Managed Fleet column
    s.zone(816, 100, 360, 536, accent="green", title="MANAGED FLEET (inventory.json)")
    s.card(834, 136, 324, "Iran Panels (role: iran)", ["ratholectl — nginx + server lanes + status JSON"], accent="green", size=11.5)
    s.card(834, 216, 324, "Foreign Nodes (role: node)", ["ratholenode — services.conf + bh-services.conf"], accent="green", size=11.5)
    s.card(
        834,
        298,
        324,
        "REST Agent (ratholeagent.py :8089)",
        ["Strict allow-list: ratholectl/node, systemctl,", "journalctl, jq, tail · 0600 token · no slash path"],
        accent="violet",
        size=11.5,
    )
    s.card(
        834,
        412,
        324,
        "Lifecycle & Safe Rollback (update.sh)",
        ["deploy -> install.sh --update on target", "Snapshot -> health check -> cgroup-safe", "deferred agent restart -> auto-rollback on fail"],
        accent="green",
        soft=True,
        size=11.5,
    )

    s.arrow(248, 178, 332, 178, kind="data")
    s.arrow(248, 296, 332, 188, kind="data")
    s.path("M 760 288 L 788 288 L 788 172 L 830 172", kind="ok", width=2.1)
    s.pill(788, 230, "SSH", accent="green", w=46)
    s.arrow(740, 338, 830, 338, kind="data", dashed=True, width=2.1)
    s.pill(788, 366, "HTTPS", accent="blue", w=54)

    s.text(24, 666, "Strict argv execution only: zero shell interpolation on hub or REST Agent; every mutation is recorded in audit.log.", size=11)
    return s


# ---------------------------------------------------------------------------
# 4) state-regenerate-reload.svg (with FIXED fail -> auto-revert arrow from Step 3!)
# ---------------------------------------------------------------------------
def build_state_regenerate(theme: str) -> Svg:
    s = Svg(
        1200,
        444,
        "Central Principle: State -> Regenerate -> Validate -> Hot-Reload",
        "Never hand-edit generated configs — mutate state safely, commit in place, validate nginx, then reload.",
        theme,
    )

    steps = [
        ("1 · Mutate State", "blue", [
            "ratholectl: state_jq atomic write",
            "to state.json (single source)",
            "ratholenode: node.env +",
            "services.conf / bh-services.conf",
        ]),
        ("2 · Regenerate", "blue", [
            "gen_server_toml() / gen_nginx_conf()",
            "gen_client() / backhaul TOML",
            "rth_commit_config(): flock +",
            "cat tmp > file (inode preserved!)",
        ]),
        ("3 · Validate Gate", "amber", [
            "Snapshot known-good config to",
            ".rathole-good.bak BEFORE apply",
            "Run nginx -t (http + stream)",
            "Stop immediately if validation fails",
        ]),
        ("4 · Hot-Reload", "green", [
            "systemctl reload nginx",
            "rathole config_watcher detects",
            "in-place write -> zero drops",
            "Restart only if transport changed",
        ]),
    ]

    x = 28
    step_centers = []
    for i, (title, acc, lines) in enumerate(steps):
        w = 266
        s.zone(x, 102, w, 134, accent=acc)
        s.card(x + 10, 112, w - 20, title, lines, accent=acc, align="left", size=12, h=114)
        step_centers.append(x + w / 2)
        if i < 3:
            s.arrow(x + w + 2, 169, x + 286, 169, kind="ok" if i == 2 else "data", width=2.4)
        x += 292

    # Bottom outcome cards: Fail (left under steps 1-3) & Pass (right under step 4)
    s.card(
        28,
        286,
        558,
        "Validation Failed -> Auto-Revert (.rathole-good.bak)",
        ["Restores both HTTP and Stream nginx configs + state before exit.", "Live reverse tunnels remain untouched and nginx never stays broken."],
        accent="red",
        soft=True,
    )
    s.card(
        614,
        286,
        558,
        "Validation Passed -> Active Tunnels Survive",
        ["Inode preservation keeps rathole config_watcher hot-reloading smoothly.", "Applies identically across ws/kcp/plain/noise, Backhaul, FRP, GRE & Agent."],
        accent="green",
        soft=True,
    )

    # Fixed arrows from Step 3 (Validate) to Red Revert, and Step 4 (Hot-Reload) to Green Survive
    s.path(f"M {step_centers[2]} 236 L {step_centers[2]} 262 L 460 262 L 460 282", kind="err", dashed=True, width=2.3)
    s.pill(612, 262, "fail -> revert", accent="red", w=88)

    s.arrow(step_centers[3], 236, step_centers[3], 282, kind="ok", width=2.4)
    s.pill(step_centers[3], 259, "pass", accent="green", w=54)

    s.text(28, 414, "Why rth_commit_config uses 'cat tmp > dst' instead of 'mv': mv replaces the file inode and breaks inotify/config_watcher.", size=11)
    return s


# ---------------------------------------------------------------------------
# 5) architecture-detailed.svg — nginx rules, lanes & port ownership
# ---------------------------------------------------------------------------
def build_architecture_detailed(theme: str) -> Svg:
    s = Svg(
        1200,
        680,
        "Detailed Reference — Nginx Rules, Lanes & Port Ownership",
        "Everything inside Iran binds 127.0.0.1 except :443 (and optional lanes you explicitly enable).",
        theme,
    )

    s.zone(24, 100, 372, 314, accent="blue", title="NGINX :443 — L7 ROUTING")
    for i, (rule, desc) in enumerate([
        ("location = /_rh/<32hex>", "Secret rathole control path -> :2333"),
        ("location = / (Upgrade)", "Fallback WS control -> :2333, else fake"),
        ("location /<node>", "map $uri -> 127.0.0.1:<data port>"),
        ("location /channel|/tunnel", "Proxy to Backhaul 127.0.0.1:3080"),
        ("location /hub/ & /sub/", "Hub web panel :8088 & subscriptions :2096"),
    ]):
        s.card(40, 134 + i * 54, 340, rule, [desc], accent="blue", align="left", size=11, h=46)

    s.zone(414, 100, 356, 314, accent="green", title="RATHOLE LANE (LOOPBACK)")
    for i, (t, desc) in enumerate([
        ("Control :2333", "Serves ws / kcp / plain ingress"),
        ("Data Listeners :1001..", "Dedicated loopback port per node"),
        ("<name>_api Services", "Loopback panel <-> node mgmt bridge"),
        ("server.toml", "tls = false; in-place config_watcher"),
    ]):
        s.card(430, 134 + i * 66, 324, t, [desc], accent="green", align="left", size=11.5, h=56)

    s.zone(788, 100, 388, 314, accent="violet", title="INDEPENDENT LANES & AGENT")
    for i, (t, desc) in enumerate([
        ("Backhaul (SMUX)", "127.0.0.1:3080 via Nginx /channel + /tunnel"),
        ("FRP (fatedier/frp)", ":7000/TCP (tcp/ws) + :7000/UDP (kcp/quic)"),
        ("GRE L3 Kernel", "gre1 10.10.10.0/30 · MTU 1476 · proto 47"),
        ("REST Agent", "rathole-agent.service :8089 (Bearer TLS)"),
    ]):
        s.card(804, 134 + i * 66, 356, t, [desc], accent="violet", align="left", size=11.5, h=56)

    s.zone(24, 434, 1152, 206, accent="slate", title="PORT OWNERSHIP MAP — IRAN SERVER")
    ports = [
        ("443 / TCP", "Nginx TLS / Stream", "Public default", "green", True),
        ("443 / UDP", "kcptun server", "Only if KCP on", "blue", False),
        ("8880 / TCP", "Nginx Plain HTTP", "Optional lane", "amber", False),
        ("2334 / TCP", "rathole-noise", "Optional lane", "violet", False),
        ("7000 / TCP+UDP", "frps Server", "Optional FRP lane", "amber", False),
        ("8089 / TCP", "REST Agent API", "Optional HTTP(S)", "violet", False),
        ("127.0.0.1:2333", "rathole control", "Loopback only", "slate", False),
        ("127.0.0.1:3080", "backhaul-server", "Loopback only", "slate", False),
    ]
    for i, (port, who, note, acc, pub) in enumerate(ports):
        col = i % 4
        row = i // 4
        s.card(42 + col * 282, 470 + row * 78, 266, port, [f"{who} · {note}"], accent=acc, soft=pub, size=12, h=66)

    s.text(24, 662, "Green = exposed by default. Other ports open ONLY when that specific carrier or agent is explicitly enabled.", size=11)
    return s


# ---------------------------------------------------------------------------
# 6) traffic-steps.svg — Packet journey + encapsulation
# ---------------------------------------------------------------------------
def build_traffic_steps(theme: str) -> Svg:
    s = Svg(
        1220,
        450,
        "Packet Journey — User to Open Internet",
        "Step 0: node maintains reverse tunnel via /_rh/<32 hex> control path (or / fallback) -> :2333",
        theme,
    )

    nodes = [
        ("User Xray", ["VLESS + WS", "/trk01"], "blue", "1", "TLS/443"),
        ("Nginx :443", ["TLS termination", "map $uri -> :1001"], "blue", "2", "local"),
        ("rathole server", ["data :1001", "(Iran loopback)"], "violet", "3", "tunnel"),
        ("rathole client", ["on foreign node", "(abroad)"], "green", "4", ":2087"),
        ("Xray (node)", ["ws inbound :2087", "decrypts VLESS"], "green", "5", "exit"),
        ("Open Internet", ["Target server"], "slate", "", ""),
    ]

    w = 162
    gap = 38
    for i, (title, lines, acc, step_num, label) in enumerate(nodes):
        x = 24 + i * (w + gap)
        s.card(x, 126, w, title, lines, accent=acc, size=12.5, h=86)
        if i < len(nodes) - 1:
            kind = "rev" if i == 2 else "data"
            dashed = (i == 2)
            s.arrow(x + w + 2, 169, x + w + gap - 4, 169, kind=kind, dashed=dashed, width=2.2)
            s.pill(x + w + gap / 2, 112, f"{step_num} · {label}", accent="violet" if i == 2 else "blue", w=54, h=20, size=9.5)

    s.text(610, 244, "Return Path (6 -> 10): Open Internet -> Node Xray -> Reverse Tunnel -> rathole server -> Nginx :443 -> User", size=11.5, color=s.t["ink"], weight="600", anchor="middle")

    # Encapsulation nested card
    s.zone(220, 272, 780, 134, accent="slate", title="WIRE ENCAPSULATION BETWEEN USER AND IRAN SERVER")
    s.card(244, 306, 732, "Outer TLS (Nginx :443)", [], accent="blue", soft=True, h=82, align="left", size=11)
    s.card(390, 314, 566, "WebSocket Frame (/trk01)", [], accent="violet", soft=True, h=66, align="left", size=11)
    s.card(566, 324, 370, "VLESS  ->  User Traffic", ["Decrypted ONLY by Xray on the node"], accent="green", h=48, size=11.5)

    s.text(610, 430, "Nginx and rathole never inspect or decrypt VLESS payloads inside the WebSocket tunnel.", size=11, anchor="middle")
    return s


# ---------------------------------------------------------------------------
# 7) traffic-flow-flowchart.svg — Clean Apple Glass replacement for Mermaid PNG/SVG
# ---------------------------------------------------------------------------
def build_traffic_flowchart(theme: str) -> Svg:
    s = Svg(
        1220,
        520,
        "Traffic Routing Flowchart — Default WebSocket/TLS Lane",
        "Shows both Step 0 reverse control channel establishment and live user request dispatch.",
        theme,
    )

    s.card(24, 210, 152, "User Client", ["VLESS + WS", "wss://domain/trk01"], accent="blue")

    s.zone(236, 98, 480, 378, accent="green", title="IRAN SERVER (panel.example.ir)")
    s.card(256, 210, 170, "Nginx :443", ["Let's Encrypt TLS", "Splits by URI / header"], accent="blue")
    s.card(488, 128, 208, "Fake Site / Panel", ["127.0.0.1:8080", "Normal HTTP requests"], accent="slate", size=11.5)
    s.card(488, 224, 208, "rathole control", ["127.0.0.1:2333", "Matches /_rh/<32 hex>"], accent="violet", size=11.5)
    s.card(488, 326, 208, "rathole data trk01", ["127.0.0.1:1001", "map $uri -> /trk01"], accent="green", size=11.5)

    s.zone(778, 198, 290, 278, accent="violet", title="FOREIGN NODE (trk01)")
    s.card(798, 234, 250, "rathole client", ["Dials outbound wss/443", "Opens data channels"], accent="violet", size=11.5)
    s.card(798, 344, 250, "Xray Inbound WS", ["127.0.0.1:2087", "Unwraps VLESS"], accent="green", size=11.5)

    s.card(1096, 344, 102, "Internet", ["Open Web"], accent="slate", size=12, h=76)

    # Arrows
    s.arrow(176, 248, 252, 248, kind="data", width=2.4)
    s.pill(214, 224, "1 · WSS", accent="blue", w=54, h=20, size=9.5)

    s.path("M 426 226 L 444 226 L 444 164 L 484 164", kind="line")
    s.arrow(426, 252, 484, 252, kind="rev")
    s.path("M 426 270 L 444 270 L 444 364 L 484 364", kind="ok", width=2.4)
    s.pill(444, 318, "2 · map $uri", accent="green", w=74, h=20, size=9.5)

    # Control tunnel from node -> nginx control -> rathole control
    s.path("M 923 476 L 923 496 L 340 496 L 340 296", kind="rev", dashed=True, width=2.0)
    s.pill(630, 496, "0 · Persistent outbound control tunnel (wss /_rh/<hex> -> :2333)", accent="violet", w=350, h=22, size=10)

    # Tunnel relay to client -> Xray -> Internet
    s.path("M 696 364 L 744 364 L 744 272 L 794 272", kind="rev", dashed=True, width=2.4)
    s.pill(748, 314, "3 · Tunnel", accent="violet", w=68, h=20, size=9.5)
    s.arrow(923, 310, 923, 340, kind="data")
    s.pill(923, 325, "4 · :2087", accent="blue", w=64, h=18, size=9.5)
    s.arrow(1048, 382, 1092, 382, kind="ok", width=2.4)
    return s


# ---------------------------------------------------------------------------
# 8) traffic-flow-sequence.svg — Clean Apple Glass Sequence Diagram
# ---------------------------------------------------------------------------
def build_traffic_sequence(theme: str) -> Svg:
    s = Svg(
        1220,
        690,
        "Packet & Tunnel Sequence Diagram — Control Setup + User Session",
        "Chronological lifecycle of control tunnel registration and end-to-end encrypted data flow.",
        theme,
    )

    actors = [
        ("User Xray", "blue"),
        ("Nginx :443", "blue"),
        ("rathole server", "violet"),
        ("rathole client", "green"),
        ("Xray (Node)", "green"),
        ("Internet", "slate"),
    ]
    xs = [110, 310, 510, 710, 910, 1110]
    for (name, acc), cx in zip(actors, xs):
        s.card(cx - 72, 98, 144, name, [], accent=acc, size=11.5, h=36)
        s.card(cx - 72, 632, 144, name, [], accent=acc, size=11.5, h=36)
        s.line(cx, 134, cx, 632, dashed=True)

    # Phase 0 band
    s.zone(40, 148, 1140, 148, accent="violet", title="PHASE 0 — CONTROL CHANNEL ESTABLISHMENT (PERSISTENT)")
    s.arrow(xs[3], 202, xs[1], 202, kind="rev", width=2.1)
    s.pill((xs[1] + xs[3]) / 2, 186, "1 · TLS + WS Upgrade /_rh/<hex>", accent="violet", w=190, h=20, size=9.5)

    s.arrow(xs[1], 240, xs[2], 240, kind="data", width=2.1)
    s.pill((xs[1] + xs[2]) / 2, 224, "2 · -> 127.0.0.1:2333", accent="blue", w=126, h=20, size=9.5)

    s.arrow(xs[2], 278, xs[3], 278, kind="ok", dashed=True, width=2.1)
    s.pill((xs[2] + xs[3]) / 2, 262, "3 · Heartbeat Active (30s)", accent="green", w=150, h=20, size=9.5)

    # Phase 1 band
    s.zone(40, 310, 1140, 308, accent="green", title="PHASE 1 — USER SESSION (PER CONNECTION)")
    steps = [
        (0, 1, 366, "4 · wss /trk01 (VLESS+WS)", "data", False, "blue", 156),
        (1, 2, 408, "5 · map $uri -> :1001", "data", False, "blue", 136),
        (2, 3, 450, "6 · Open mux stream", "rev", True, "violet", 126),
        (3, 4, 492, "7 · Forward -> :2087", "data", False, "green", 126),
        (4, 5, 534, "8 · Decrypt VLESS -> Web", "ok", False, "green", 154),
        (5, 0, 588, "9 · Encrypted Reverse Return Path (Internet -> Xray -> Tunnel -> Nginx -> User)", "rev", True, "violet", 490),
    ]
    for a, b, y, lbl, kind, dashed, acc, pw in steps:
        s.arrow(xs[a], y, xs[b], y, kind=kind, dashed=dashed, width=2.1)
        s.pill((xs[a] + xs[b]) / 2, y - 15, lbl, accent=acc, w=pw, h=20, size=9.5)

    return s


if __name__ == "__main__":
    for stem, fn in [
        ("transport-modes", build_transport_modes),
        ("architecture", build_architecture),
        ("hub-architecture", build_hub_architecture),
        ("state-regenerate-reload", build_state_regenerate),
        ("architecture-detailed", build_architecture_detailed),
        ("traffic-steps", build_traffic_steps),
        ("traffic-flow-flowchart", build_traffic_flowchart),
        ("traffic-flow-sequence", build_traffic_sequence),
    ]:
        emit_both(stem, fn)
    print("done (16 SVGs generated)")
