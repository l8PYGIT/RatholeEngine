#!/usr/bin/env python3
"""Generate GitHub banners, Open Graph card, and PNG diagram mirrors.

Uses headless Chromium via Playwright to rasterize Apple Glass HTML banners
and docs/assets/*.svg mirrors with exact dimensions and clean typography:

    python3 tools/gen_banners.py --version v2.3.0
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"


def banner_html(version: str, theme: str) -> str:
    dark = theme == "dark"
    bg = (
        "radial-gradient(circle at 12% 10%, rgba(124,58,237,0.30), transparent 48%),"
        "radial-gradient(circle at 90% 90%, rgba(10,132,255,0.22), transparent 50%),"
        "linear-gradient(135deg, #060b16 0%, #0b1427 52%, #111c36 100%)"
        if dark
        else
        "radial-gradient(circle at 10% 8%, rgba(124,58,237,0.13), transparent 46%),"
        "radial-gradient(circle at 90% 92%, rgba(0,122,255,0.12), transparent 48%),"
        "linear-gradient(135deg, #f3f6fd 0%, #eef2ff 50%, #e7f0ff 100%)"
    )
    dot = "rgba(148,163,184,0.14)" if dark else "rgba(71,85,105,0.11)"
    frame_bg = "rgba(11,19,36,0.72)" if dark else "rgba(255,255,255,0.88)"
    frame_bd = "rgba(255,255,255,0.14)" if dark else "rgba(15,23,42,0.10)"
    ink = "#f8fafc" if dark else "#0f172a"
    sub = "#cbd5e1" if dark else "#334155"
    muted = "#94a3b8" if dark else "#64748b"
    ver_bg = "rgba(14,165,233,0.18)" if dark else "rgba(2,132,199,0.10)"
    ver_bd = "rgba(56,189,248,0.45)" if dark else "rgba(2,132,199,0.32)"
    ver_fg = "#7dd3fc" if dark else "#0369a1"
    chip_bg = "rgba(15,25,46,0.88)" if dark else "rgba(255,255,255,0.95)"
    chip_bd = "rgba(148,163,184,0.25)" if dark else "rgba(15,23,42,0.12)"
    topo_bg = "rgba(9,16,32,0.68)" if dark else "rgba(248,250,252,0.88)"
    card_bg = "rgba(15,25,46,0.92)" if dark else "#ffffff"
    card_bd = "rgba(148,163,184,0.22)" if dark else "rgba(15,23,42,0.12)"
    edge_bg = "rgba(10,132,255,0.14)" if dark else "rgba(0,122,255,0.08)"
    edge_bd = "#38bdf8" if dark else "#0284c7"
    edge_pill_bg = "rgba(15,23,42,0.85)" if dark else "rgba(241,245,249,0.95)"
    logo_bg = "rgba(124,58,237,0.16)" if dark else "rgba(124,58,237,0.10)"
    logo_bd = "rgba(167,139,250,0.45)" if dark else "rgba(124,58,237,0.30)"

    chips = [
        ("#38bdf8", "WebSocket/TLS"),
        ("#a78bfa", "KCP FEC"),
        ("#34d399", "Backhaul SMUX"),
        ("#60a5fa", "FRP TCP/KCP/QUIC"),
        ("#fbbf24", "GRE L3"),
        ("#fb7185", "Paqet PCK"),
        ("#c084fc", "Managed Xray"),
        ("#22d3ee", "Auto-Tuner rthprof1:"),
        ("#f472b6", "REST Agent"),
    ]
    chip_html = "".join(
        f'<span class="chip"><i style="background:{c}"></i>{lbl}</span>'
        for c, lbl in chips
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1280px; height: 420px; overflow: hidden;
    font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
    background: {bg};
    position: relative;
    display: flex; align-items: center; justify-content: center;
  }}
  .dots {{
    position: absolute; inset: 0;
    background-image: radial-gradient({dot} 1.2px, transparent 1.2px);
    background-size: 24px 24px;
    pointer-events: none;
  }}
  .frame {{
    position: relative;
    width: 1208px; height: 362px;
    border-radius: 22px;
    background: {frame_bg};
    border: 1.4px solid {frame_bd};
    box-shadow: 0 24px 60px rgba(0,0,0,{0.35 if dark else 0.08});
    padding: 28px 34px;
    display: flex; align-items: center; justify-content: space-between; gap: 28px;
  }}
  .left {{ flex: 1; min-width: 0; }}
  .head {{ display: flex; align-items: center; gap: 20px; margin-bottom: 14px; }}
  .logo-box {{
    width: 78px; height: 78px; border-radius: 20px; flex-shrink: 0;
    background: {logo_bg}; border: 1.5px solid {logo_bd};
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 28px rgba(124,58,237,{0.25 if dark else 0.14});
  }}
  .title-row {{ display: flex; align-items: center; gap: 14px; }}
  h1 {{ font-size: 46px; font-weight: 800; letter-spacing: -0.025em; color: {ink}; line-height: 1.05; }}
  .ver {{
    padding: 4px 13px; border-radius: 999px; font-size: 15px; font-weight: 700;
    background: {ver_bg}; border: 1.2px solid {ver_bd}; color: {ver_fg};
  }}
  .subtitle {{ margin-top: 6px; font-size: 19px; font-weight: 500; color: {sub}; }}
  .tagline {{ margin: 12px 0 18px; font-size: 16px; color: {sub}; letter-spacing: -0.005em; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 8px 9px; max-width: 700px; }}
  .chip {{
    display: inline-flex; align-items: center; gap: 7px;
    padding: 6px 13px; border-radius: 999px;
    background: {chip_bg}; border: 1px solid {chip_bd};
    color: {ink}; font-size: 13px; font-weight: 600;
  }}
  .chip i {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}

  .topo {{
    width: 446px; height: 304px; flex-shrink: 0;
    border-radius: 18px;
    background: {topo_bg}; border: 1.2px solid {card_bd};
    padding: 16px 18px;
    display: flex; flex-direction: column;
  }}
  .topo-hdr {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: {muted};
    margin-bottom: 10px;
  }}
  .topo-ports {{ color: {"#34d399" if dark else "#059669"}; display: flex; align-items: center; gap: 6px; }}
  .topo-ports i {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; display: inline-block; }}
  .topo-svg {{ width: 100%; height: 244px; }}
</style>
</head>
<body>
  <div class="dots"></div>
  <div class="frame">
    <div class="left">
      <div class="head">
        <div class="logo-box">
          <svg width="56" height="56" viewBox="0 0 120 120" fill="none">
            <circle cx="60" cy="60" r="50" stroke="#7c3aed" stroke-width="6" opacity="0.32"/>
            <circle cx="60" cy="60" r="38" stroke="#8b5cf6" stroke-width="6" opacity="0.58"/>
            <circle cx="60" cy="60" r="26" stroke="#a78bfa" stroke-width="6" opacity="0.90"/>
            <circle cx="60" cy="60" r="15" fill="#1e293b"/>
            <path d="M40 60 H72" stroke="#f8fafc" stroke-width="6" stroke-linecap="round"/>
            <path d="M64 50 L79 60 L64 70 Z" fill="#f8fafc"/>
          </svg>
        </div>
        <div>
          <div class="title-row">
            <h1>RatholeEngine</h1>
            <span class="ver">{version}</span>
          </div>
          <div class="subtitle">Multi-Location Reverse Tunnel Engine &middot; rathole + Nginx</div>
        </div>
      </div>
      <div class="tagline">One Domain &middot; One Cert &middot; Port 443 &middot; 9 Carriers &middot; Auto-Tuner &amp; Central Web Hub</div>
      <div class="chips">{chip_html}</div>
    </div>

    <div class="topo">
      <div class="topo-hdr">
        <span>REVERSE TUNNEL TOPOLOGY</span>
        <span class="topo-ports"><i></i>443 &middot; 7000 &middot; GRE &middot; PCK</span>
      </div>
      <svg class="topo-svg" viewBox="0 0 410 244" font-family="Segoe UI, system-ui, sans-serif">
        <defs>
          <marker id="mB" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,1 L9,5 L0,9 z" fill="{edge_bd}"/>
          </marker>
          <marker id="mV" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,1 L9,5 L0,9 z" fill="#a78bfa"/>
          </marker>
          <marker id="mG" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,1 L9,5 L0,9 z" fill="#34d399"/>
          </marker>
        </defs>

        <!-- Clients -->
        <rect x="6" y="74" width="90" height="82" rx="12" fill="{card_bg}" stroke="{card_bd}" stroke-width="1.2"/>
        <circle cx="51" cy="95" r="4.5" fill="{edge_bd}"/>
        <text x="51" y="117" text-anchor="middle" fill="{ink}" font-size="12" font-weight="700">Clients</text>
        <text x="51" y="135" text-anchor="middle" fill="{muted}" font-size="9.8">WSS / path</text>

        <!-- Arrow Clients -> Iran Edge -->
        <line x1="96" y1="115" x2="128" y2="115" stroke="{edge_bd}" stroke-width="2.2" marker-end="url(#mB)"/>

        <!-- Iran Edge -->
        <rect x="132" y="54" width="114" height="122" rx="14" fill="{edge_bg}" stroke="{edge_bd}" stroke-width="1.8"/>
        <text x="189" y="80" text-anchor="middle" fill="{ink}" font-size="12.5" font-weight="800">Iran Edge</text>
        <text x="189" y="99" text-anchor="middle" fill="{edge_bd}" font-size="11" font-weight="700">Nginx :443</text>
        <rect x="142" y="110" width="94" height="22" rx="6" fill="{edge_pill_bg}" stroke="{card_bd}" stroke-width="0.9"/>
        <text x="189" y="125" text-anchor="middle" fill="{ink}" font-size="10" font-weight="600">/eu &middot; /de &middot; #/tuner</text>
        <text x="189" y="156" text-anchor="middle" fill="{muted}" font-size="9.5">Zero Open Node Ports</text>

        <!-- Dashed Reverse Tunnels -->
        <path d="M 284 42 C 264 42, 266 90, 248 90" fill="none" stroke="#a78bfa" stroke-width="2" stroke-dasharray="5 3.5" marker-end="url(#mV)"/>
        <line x1="284" y1="115" x2="250" y2="115" stroke="{edge_bd}" stroke-width="2" stroke-dasharray="5 3.5" marker-end="url(#mB)"/>
        <path d="M 284 190 C 264 190, 266 142, 248 142" fill="none" stroke="#34d399" stroke-width="2" stroke-dasharray="5 3.5" marker-end="url(#mG)"/>

        <!-- 3 Foreign Nodes -->
        <rect x="286" y="10" width="118" height="62" rx="11" fill="{card_bg}" stroke="{card_bd}" stroke-width="1.2"/>
        <circle cx="300" cy="30" r="4" fill="#34d399"/>
        <text x="311" y="34" fill="{ink}" font-size="11.5" font-weight="700">EU Node 1</text>
        <text x="298" y="54" fill="{muted}" font-size="9.8">FRP QUIC / KCP</text>

        <rect x="286" y="84" width="118" height="62" rx="11" fill="{card_bg}" stroke="{card_bd}" stroke-width="1.2"/>
        <circle cx="300" cy="104" r="4" fill="#38bdf8"/>
        <text x="311" y="108" fill="{ink}" font-size="11.5" font-weight="700">DE Node 2</text>
        <text x="298" y="128" fill="{muted}" font-size="9.8">Backhaul WSMUX</text>

        <rect x="286" y="158" width="118" height="62" rx="11" fill="{card_bg}" stroke="{card_bd}" stroke-width="1.2"/>
        <circle cx="300" cy="178" r="4" fill="#a78bfa"/>
        <text x="311" y="182" fill="{ink}" font-size="11.5" font-weight="700">Foreign N</text>
        <text x="298" y="202" fill="{muted}" font-size="9.8">Paqet &middot; Xray &middot; GRE</text>
      </svg>
    </div>
  </div>
</body>
</html>"""


def social_preview_html(version: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1280px; height: 640px; overflow: hidden;
    font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
    background:
      radial-gradient(circle at 12% 10%, rgba(124,58,237,0.32), transparent 46%),
      radial-gradient(circle at 90% 90%, rgba(10,132,255,0.22), transparent 48%),
      linear-gradient(135deg, #060b16 0%, #0b1427 52%, #111c36 100%);
    display: flex; align-items: center; justify-content: center;
    position: relative;
  }}
  .dots {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(148,163,184,0.14) 1.25px, transparent 1.25px);
    background-size: 24px 24px;
  }}
  .frame {{
    position: relative;
    width: 1140px; height: 516px;
    border-radius: 26px;
    background: rgba(11,19,36,0.78);
    border: 1.5px solid rgba(255,255,255,0.14);
    box-shadow: 0 30px 80px rgba(0,0,0,0.45);
    padding: 46px 54px 36px;
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .top {{ display: flex; align-items: center; gap: 24px; }}
  .logo-box {{
    width: 92px; height: 92px; border-radius: 22px; flex-shrink: 0;
    background: rgba(124,58,237,0.16); border: 1.6px solid rgba(167,139,250,0.46);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 34px rgba(124,58,237,0.28);
  }}
  .title-row {{ display: flex; align-items: center; gap: 16px; }}
  h1 {{ font-size: 54px; font-weight: 800; letter-spacing: -0.025em; color: #f8fafc; line-height: 1.05; }}
  .ver {{
    padding: 5px 15px; border-radius: 999px; font-size: 17px; font-weight: 700;
    background: rgba(14,165,233,0.18); border: 1.2px solid rgba(56,189,248,0.45); color: #7dd3fc;
  }}
  .sub {{ margin-top: 8px; font-size: 22px; color: #cbd5e1; font-weight: 500; }}
  .sub2 {{ margin-top: 6px; font-size: 16.5px; color: #94a3b8; }}

  .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 26px; }}
  .card {{
    background: rgba(15,25,46,0.90);
    border: 1.2px solid rgba(148,163,184,0.20);
    border-radius: 16px;
    padding: 20px 22px;
  }}
  .ico {{
    width: 34px; height: 34px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 14px; font-size: 17px;
  }}
  .ico.v {{ background: rgba(124,58,237,0.18); border: 1px solid rgba(167,139,250,0.40); color: #c4b5fd; }}
  .ico.b {{ background: rgba(14,165,233,0.16); border: 1px solid rgba(56,189,248,0.40); color: #7dd3fc; }}
  .ico.g {{ background: rgba(16,185,129,0.16); border: 1px solid rgba(52,211,153,0.40); color: #6ee7b7; }}
  .card h3 {{ font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }}
  .card p {{ font-size: 14px; line-height: 1.52; color: #94a3b8; }}

  .foot {{
    border-top: 1px solid rgba(148,163,184,0.18);
    padding-top: 16px;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 15px; color: #94a3b8;
  }}
  .foot b {{ color: #f8fafc; }}
</style>
</head>
<body>
  <div class="dots"></div>
  <div class="frame">
    <div>
      <div class="top">
        <div class="logo-box">
          <svg width="64" height="64" viewBox="0 0 120 120" fill="none">
            <circle cx="60" cy="60" r="50" stroke="#7c3aed" stroke-width="6" opacity="0.32"/>
            <circle cx="60" cy="60" r="38" stroke="#8b5cf6" stroke-width="6" opacity="0.58"/>
            <circle cx="60" cy="60" r="26" stroke="#a78bfa" stroke-width="6" opacity="0.90"/>
            <circle cx="60" cy="60" r="15" fill="#1e293b"/>
            <path d="M40 60 H72" stroke="#f8fafc" stroke-width="6" stroke-linecap="round"/>
            <path d="M64 50 L79 60 L64 70 Z" fill="#f8fafc"/>
          </svg>
        </div>
        <div>
          <div class="title-row">
            <h1>RatholeEngine</h1>
            <span class="ver">{version}</span>
          </div>
          <div class="sub">Multi-Location Reverse Tunnel System on rathole + Nginx</div>
          <div class="sub2">One port &middot; One domain &middot; 9 carriers &middot; Auto-Tuner (rthprof1:) &middot; Managed Xray &amp; Monitor Bot</div>
        </div>
      </div>

      <div class="cards">
        <div class="card">
          <div class="ico v">&#9889;</div>
          <h3>9 Carriers + Managed Xray</h3>
          <p>WebSocket/TLS, KCP FEC, Plain, Noise, Backhaul SMUX, FRP, GRE L3, FRP+GRE &amp; Paqet PCK + REALITY/XHTTP cover scanner.</p>
        </div>
        <div class="card">
          <div class="ico b">&#9881;</div>
          <h3>RatholeHub + Auto-Tuner</h3>
          <p>Offline Apple Glass UI, TOTP 2FA &amp; RBAC, 6-stage kernel/MTU/carrier benchmark &amp; portable rthprof1: AI profiles.</p>
        </div>
        <div class="card">
          <div class="ico g">&#128737;</div>
          <h3>Agent + Monitor &amp; Signing</h3>
          <p>Key-auth SSH or HTTPS REST Agent (:8089), standalone Telegram monitor relay, Ed25519 signed updates &amp; watchdog rollback.</p>
        </div>
      </div>
    </div>

    <div class="foot">
      <span><b>github.com/l8PYGIT/RatholeEngine</b> &middot; Offline-Ready &middot; AGPL-3.0</span>
      <span>Telegram Channel: <b>@l8PY4NET</b></span>
    </div>
  </div>
</body>
</html>"""


def render_svg_png(page, svg_path: pathlib.Path, png_path: pathlib.Path, scale: float = 1.5) -> None:
    svg_text = svg_path.read_text(encoding="utf-8")
    # Parse intrinsic width/height from svg tag
    import re
    mw = re.search(r'width="(\d+)"', svg_text)
    mh = re.search(r'height="(\d+)"', svg_text)
    w = int(mw.group(1)) if mw else 1200
    h = int(mh.group(1)) if mh else 660
    page.set_viewport_size({"width": w, "height": h})
    page.set_content(
        f'<!DOCTYPE html><html><body style="margin:0;padding:0;overflow:hidden;background:transparent;">{svg_text}</body></html>',
        wait_until="load",
    )
    page.screenshot(path=str(png_path), type="png", omit_background=True)
    print(f"wrote {png_path.relative_to(ROOT)} ({w}x{h}, {png_path.stat().st_size} B)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v2.3.0")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 1) Banners (1280x420)
            for theme, fname in [("dark", "banner-dark.png"), ("light", "banner-light.png")]:
                page = browser.new_page(viewport={"width": 1280, "height": 420}, device_scale_factor=1)
                page.set_content(banner_html(args.version, theme), wait_until="load")
                out = ASSETS / fname
                page.screenshot(path=str(out), type="png")
                print(f"wrote {out.relative_to(ROOT)} (1280x420, {out.stat().st_size} B)")
                page.close()

            # 2) Social Preview (1280x640)
            page = browser.new_page(viewport={"width": 1280, "height": 640}, device_scale_factor=1)
            page.set_content(social_preview_html(args.version), wait_until="load")
            sp = ASSETS / "social-preview.png"
            page.screenshot(path=str(sp), type="png")
            print(f"wrote {sp.relative_to(ROOT)} (1280x640, {sp.stat().st_size} B)")
            page.close()

            # 3) SVG -> PNG mirrors
            page = browser.new_page(viewport={"width": 1220, "height": 680}, device_scale_factor=1.5)
            for stem in ("architecture", "architecture-detailed", "traffic-steps"):
                render_svg_png(page, ASSETS / f"{stem}.svg", ASSETS / f"{stem}.png")
            page.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
