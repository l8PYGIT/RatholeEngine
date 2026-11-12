# Native FRP Core & GRE Tunnel Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate FRP reverse-tunnel core (`fatedier/frp`) and Linux GRE L3 kernel tunnel into `tunnel-engine` native Rust codebase with full parity to `ratholectl` / `ratholenode` bash commands.

**Architecture:**
- **FRP Core:** Native generation of `/etc/frp/frps.toml` (Iran) and `/etc/frp/frpc.toml` (Foreign Node), supporting TCP, KCP, QUIC, and WebSocket carrier transports with `tcpMux = true`. Managed via `frps.service` and `frpc.service`.
- **GRE Core:** Linux L3 encapsulation commands (`ip tunnel`, `ip link set mtu 1476`, `ip addr add <ip>/30`, iptables TCPMSS clamping).
- **Parity CLI:** `ratholectl frp ...`, `ratholectl gre ...`, `ratholenode frp ...`, `ratholenode gre ...`.
- **Zero-Downtime Migration:** Parse `.frp_port`, `.frp_token`, `.frp_transport`, and `TUNNEL=frp` from legacy state files.

**Tech Stack:**
- Rust 2021 (no extra crates beyond existing clap, serde, anyhow)
- Static compilation via `x86_64-unknown-linux-musl` in Alpine chroot
- Ponytail principles: stdlib/native Linux commands, in-place writes, minimal diffs.

---

### Task 1: State Models & Transports (`engine/src/lib.rs`)

**Files:**
- Modify: `engine/src/lib.rs`
- Modify: `engine/tests/test_state.rs`

- [ ] **Step 1: Write tests for Frp and Gre in `test_state.rs`**
- [ ] **Step 2: Add `FrpTransport` enum (Tcp, Kcp, Quic, WebSocket)**
- [ ] **Step 3: Update `TransportMode` to support `Frp` and `Gre`**
- [ ] **Step 4: Add FRP and GRE fields to `PanelState` and `NodeState`**
- [ ] **Step 5: Run tests and commit**

---

### Task 2: Config & Network Command Generators (`engine/src/config_gen.rs`)

**Files:**
- Modify: `engine/src/config_gen.rs`
- Modify: `engine/tests/test_config_gen.rs`

- [ ] **Step 1: Write tests for `render_frp_server_toml` and `render_frp_client_toml`**
- [ ] **Step 2: Implement `render_frp_server_toml(&PanelState) -> Result<Option<String>>`**
- [ ] **Step 3: Implement `render_frp_client_toml(&NodeState, ...) -> Result<Option<String>>`**
- [ ] **Step 4: Implement GRE command generators (setup & teardown args)**
- [ ] **Step 5: Run tests and commit**

---

### Task 3: Process & Process Orchestration (`engine/src/orchestrator.rs`)

**Files:**
- Modify: `engine/src/orchestrator.rs`
- Modify: `engine/tests/test_orchestrator.rs`

- [ ] **Step 1: Write test for FRP and GRE service orchestration in `test_orchestrator.rs`**
- [ ] **Step 2: Add `/etc/frp/frps.toml` and `/etc/frp/frpc.toml` to `OrchestratorPaths`**
- [ ] **Step 3: Update `regenerate_panel` to write FRP server config and reload `frps.service`**
- [ ] **Step 4: Update `regenerate_client` to write FRP client config and reload `frpc.service`**
- [ ] **Step 5: Implement `setup_gre_interface` and `teardown_gre_interface` with `CommandRunner`**
- [ ] **Step 6: Run tests and commit**

---

### Task 4: CLI Dispatcher & Parity Commands (`engine/src/main.rs`)

**Files:**
- Modify: `engine/src/main.rs`
- Modify: `engine/tests/test_cli_dispatch.rs`

- [ ] **Step 1: Write CLI dispatch tests for FRP and GRE subcommands**
- [ ] **Step 2: Add `Frp` and `Gre` subcommands to `PanelCommands`**
- [ ] **Step 3: Add `Frp` and `Gre` subcommands to `NodeCommands`**
- [ ] **Step 4: Wire handlers for `cmd_frp` and `cmd_gre`**
- [ ] **Step 5: Run tests and commit**

---

### Task 5: Legacy State Migration (`engine/src/migration.rs`)

**Files:**
- Modify: `engine/src/migration.rs`
- Modify: `engine/tests/test_migration.rs`

- [ ] **Step 1: Write tests for migrating legacy FRP and GRE panel/node state**
- [ ] **Step 2: Parse `.frp_port`, `.frp_token`, `.frp_transport`, and `transport="frp"` in `migrate_old_panel_state`**
- [ ] **Step 3: Parse `TUNNEL=frp`, `FRP_REMOTE`, `FRP_TOKEN` in `migrate_old_node_state`**
- [ ] **Step 4: Run all test suites across the workspace and commit**

---

### Task 6: Static Linux Binary Build & Release Verification

**Files:**
- Build in Alpine chroot: `x86_64-unknown-linux-musl`
- Update: `dist/tunnel-engine-linux-x86_64`
- Push to GitHub: `loopy-iri/tunnel-engine` (Release v0.2.2)
