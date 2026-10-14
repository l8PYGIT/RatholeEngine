# FRP Core & GRE Tunnel Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the FRP (`fatedier/frp`) reverse-tunnel core and GRE (Linux L3 `ip tunnel`) kernel network tunnel into `rathole-manager` across `common.sh`, `ratholectl`, `ratholenode`, `hub.py`, `hubcmds.py`, and the Hub Web UI.

**Architecture:**
- **FRP Core:** `frps` on Iran, `frpc` on Foreign Node. Generates `/etc/frp/frps.toml` and `/etc/frp/frpc.toml`. Supports TCP, KCP, QUIC, and WebSocket carrier transports with built-in `tcpMux`. Managed via systemd units (`frps.service`, `frpc.service`).
- **GRE Core:** Linux L3 encapsulation using `ip tunnel add gre1 mode gre ...`, MTU clamping to 1476 via iptables TCPMSS, `net.ipv4.ip_forward=1`, and point-to-point `/30` subnet routing (10.10.10.1 ↔ 10.10.10.2).
- **Hub & UI:** Whitelisted CLI actions in `hubcmds.py`, API endpoints and mock responses in `hub.py`, carrier options, badges, and animated cables on the visual patchboard in `app.js` and `app.css`.

**Tech Stack:**
- Bash (`set -uo pipefail`, standard rathole-manager style)
- Go binary distribution (`fatedier/frp`) via ghproxy mirrors
- Linux kernel `iproute2` (`ip tunnel`, `ip link`, `ip addr`) and `iptables`
- Python 3 stdlib for `hub.py` and `hubcmds.py`
- Vanilla ES6 + SVG/CSS in `app.js` and `app.css`

## Global Constraints
- Preserve in-place writes (inode preservation) for hot-reload.
- Pure Python 3 stdlib (zero pip dependencies).
- Pure vanilla JS/CSS (zero npm dependencies).
- Maintain Finglish convention in CLI logs / Bash comments per AGENTS.md, with standard Persian in Hub UI.
- All 45 existing python tests must continue to pass.

---

### Task 1: Add FRP and GRE Helpers in `rathole-manager/common.sh`

**Files:**
- Modify: `rathole-manager/common.sh`
- Test: `tests/test_common_frp_gre.py`

**Interfaces:**
- `install_frp(role)`: downloads and installs `frps` or `frpc` (version v0.61.1 or latest)
- `frp_systemd_unit(role)`: writes `/etc/systemd/system/frp<role>.service`
- `gre_setup_interface(name, local_ip, remote_ip, tunnel_ip, peer_ip)`: configures GRE interface and MTU
- `gre_teardown_interface(name)`: cleans up GRE interface and iptables rules

- [ ] **Step 1: Write test for FRP and GRE helper signatures in Python**
- [ ] **Step 2: Implement `install_frp` in `common.sh` with mirror fallback**
- [ ] **Step 3: Implement `gre_setup_interface` and `gre_teardown_interface` in `common.sh`**
- [ ] **Step 4: Verify syntax with `bash -n rathole-manager/common.sh`**

---

### Task 2: Implement FRP Core in `ratholectl` and `ratholenode`

**Files:**
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`

**Interfaces:**
- `ratholectl frp on|off|status|show`: configures `/etc/frp/frps.toml` and controls `frps.service`
- `ratholenode frp on|off|status`: configures `/etc/frp/frpc.toml` and controls `frpc.service`

- [ ] **Step 1: Add `cmd_frp()` and TOML generation in `ratholectl`**
- [ ] **Step 2: Add `cmd_frp()` and client proxy TOML generation in `ratholenode`**
- [ ] **Step 3: Verify syntax with `bash -n rathole-manager/ratholectl` and `bash -n rathole-manager/ratholenode`**

---

### Task 3: Implement GRE Tunnel Commands in `ratholectl` and `ratholenode`

**Files:**
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`

**Interfaces:**
- `ratholectl gre on <node_ip> [tunnel_ip] [gre_name]`: brings up GRE server endpoint
- `ratholectl gre off [gre_name]`: tears down GRE endpoint
- `ratholectl gre status`: shows `ip tunnel show` and ping status
- `ratholenode gre on <iran_ip> [tunnel_ip] [gre_name]`: brings up GRE client endpoint
- `ratholenode gre off`: tears down GRE client endpoint
- `ratholenode gre status`: shows status

- [ ] **Step 1: Implement `cmd_gre()` in `ratholectl`**
- [ ] **Step 2: Implement `cmd_gre()` in `ratholenode`**
- [ ] **Step 3: Verify syntax with `bash -n`**

---

### Task 4: Whitelist Actions and Add Hub API & Mocks in `hubcmds.py` & `hub.py`

**Files:**
- Modify: `rathole-manager/ratholehub/hubcmds.py`
- Modify: `rathole-manager/ratholehub/hub.py`
- Test: `tests/test_hub_frp_gre.py`

**Interfaces:**
- Add `frp_on`, `frp_off`, `frp_status`, `frp_show` to `WRITE_ACTIONS`
- Add `gre_on`, `gre_off`, `gre_status` to `WRITE_ACTIONS`
- Add command builders in `build_iran_cmd` and `build_node_cmd`
- Add mock outputs in `hub.py:mock_run` for FRP and GRE

- [ ] **Step 1: Add action definitions and regex validation in `hubcmds.py`**
- [ ] **Step 2: Add mock handler outputs in `hub.py:mock_run`**
- [ ] **Step 3: Write and pass unit tests in `tests/test_hub_frp_gre.py`**

---

### Task 5: UI & Visual Patchboard Integration in `app.js`, `app.css`, and `i18n.js`

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.css`
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/i18n.js`

**Interfaces:**
- Cable styling: `.cable-wire.frp` (vibrant orange/red `#f97316`) and `.cable-wire.gre` (emerald green `#10b981`)
- Badges: `.b-frp` and `.b-gre`
- Fast carrier switch modal: include `FRP` and `GRE`
- Mini wiring strip and patch board rack labels

- [ ] **Step 1: Add FRP and GRE CSS styles in `app.css`**
- [ ] **Step 2: Add translations in `i18n.js`**
- [ ] **Step 3: Update `buildWiringModel`, carrier selectors, and inspector in `app.js`**
- [ ] **Step 4: Verify with Playwright screenshots**
