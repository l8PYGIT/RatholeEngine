# Design Spec: Ruthless Network, Kernel & Tunnel Auto-Tuner (`rathole-tuner`)

**Date:** 2026-11-24
**Scope:** Zero-dependency (Python 3 stdlib) bidirectional network, kernel, MTU/MSS, offload, qdisc, buffer, tunnel-carrier, and non-kernel stack benchmark & auto-tuning subsystem (`rathole-tuner`), usable standalone on any Linux server pair and natively integrated into `ratholectl`, `ratholenode`, and `RatholeHub` (`#/tuner`), with portable AI-analyzable JSON + compressed Base64url (`rthprof1:...`) datacenter profiles, live A/B/N profile comparison, Dead-Man's-Switch Watchdog protection, and reboot-persistent Apply / 1-command Rollback.

---

## 1. Goals & Design Principles

1. **Zero external runtime dependencies:** Runs on vanilla Python 3 stdlib on Linux without `pip` and without requiring `iperf3`, `mtr`, or `netperf` to be installed or reachable through filtered repositories.
2. **Bidirectional true measurement:** Measures not only single-stream peak bandwidth, but also multi-stream saturation, simultaneous directional traffic, **Loaded RTT / Bufferbloat** (latency under saturation), tail jitter (`p99 - p50`), kernel `TCP_INFO` retransmissions/delivery rate, UDP packet loss, NIC/qdisc drops, and throughput stability (CoV).
3. **Two explicit execution modes (`brutal` vs `safe`):**
   - **`brutal`:** Performs live, aggressive kernel/NIC sweeps (interface MTU, route `initcwnd`/`initrwnd`/`advmss`, `tc qdisc`, `ethtool` offloads/rings, `txqueuelen`, `sysctl` buffers/CC/TCP knobs) bounded by strict safety invariants, pre-flight atomic Snapshot, dual-side Dead-Man's-Switch Watchdog, and deterministic baseline restoration after every stage.
   - **`safe`:** Runs zero global kernel/NIC mutations; restricts tests to socket-level `TCP_MAXSEG` sweeps, PMTU `IP_PMTUDISC_DO` / ICMP DF probes, isolated ephemeral-port tunnel carrier tests, and read-only non-kernel configuration/host audits.
4. **Never permanently mutate without explicit approval:** Benchmarking always restores the baseline configuration upon completion (or interruption/timeout). Persistent activation happens only via explicit `apply` (`--apply` / Hub `Apply` action), which writes persistent sysctl + boot-restore systemd state and saves a rollback snapshot.
5. **Portable AI-ready & shareable datacenter profiles (`rathole.netprofile.v1`):** Produces sanitized JSON reports and compact verified Base64url strings (`rthprof1:...`) so operators can feed measurements into an LLM/AI for cross-datacenter analysis, build per-datacenter preset libraries (e.g., `iran:arvan` <-> `node:hetzner`), share profiles safely with others, and live A/B/N test external or AI-crafted profiles on any real link.

---

## 2. Package & Module Architecture

All tuner code lives under `rathole-manager/tuner/` with a standalone executable entrypoint `rathole-manager/rathole-tuner` installed to `/usr/local/bin/rathole-tuner` (and Python package installed to `/usr/local/share/rathole/tuner/`).

| Module / File | Single Responsibility | Key Inputs / Outputs |
|---|---|---|
| `rathole-manager/rathole-tuner` | Standalone CLI entrypoint; resolves package from script dir or `/usr/local/share/rathole` | Subcommands -> JSON/table stdout + exit code |
| `tuner/__init__.py` | Package version, schema constants (`SCHEMA_VERSION = "rathole.netprofile.v1"`, `PROFILE_PREFIX = "rthprof1:"`) | Shared constants |
| `tuner/__main__.py` | `python3 -m tuner` module entrypoint and CLI subcommand dispatch | Parsed CLI args -> module invocation |
| `tuner/protocol.py` | Length-prefixed TCP JSON control framing with HMAC-SHA256 (`timestamp` + `nonce` + payload), 60s replay window, nonce deduplication, 1 MiB frame limit, strict action allow-list | `FrameSocket`, `sign_frame`, `verify_frame`, allowed actions only (zero shell execution) |
| `tuner/sysstate.py` | Host capability discovery, atomic Snapshot/Restore, `getsockopt(IPPROTO_TCP, TCP_INFO)` reader, `/proc/net/snmp` + `/sys/class/net/<dev>/statistics` counters | Capabilities dict, Snapshot JSON, `apply_candidate()`, `restore_snapshot()` |
| `tuner/watchdog.py` | Independent child process Dead-Man's-Switch (`TTL = 45s`, `Heartbeat = 5s`, configurable); local snapshot restore on timeout/crash without needing network connectivity | Arms on snapshot path; disarms cleanly on revert/exit |
| `tuner/probes.py` | Pure stdlib high-throughput load & telemetry engine: bidirectional PMTU binary search, unloaded RTT/jitter, multi-worker bulk streams (`256 KiB` `memoryview` buffers), concurrent `50 ms` Loaded-RTT Bufferbloat probe, UDP pacer/loss probe, burst short-flow probe | Structured metric dict per trial (`throughput_mbps`, `loaded_rtt_ms`, `jitter_ms`, `tcp_info`, `udp_loss_pct`, `stability_cov`) |
| `tuner/sweep.py` | 6-stage coordinate-descent search (`Stage 0`..`Stage 5`) + Top-3 Soak vs Baseline; supports `brutal` / `safe`, normal (3-8 min) and `--deep` modes | Ordered candidate list -> Stage summaries + Top-K finalists |
| `tuner/carriers.py` | Ephemeral-port isolated benchmarks of installed tunnel cores (`raw-tcp`, `raw-udp`, `rathole-ws`, `rathole-plain`, `rathole-noise`, `kcp`, `backhaul`, `frp`, `gre`, `paqet`) without touching live user ports | Per-carrier performance matrix + best per-carrier profile (`kcp`, `backhaul`, `frp`, `paqet`) |
| `tuner/audit.py` | Non-kernel system & application inspector (`CPU governor`, `RPS/XPS`, `systemd LimitNOFILE`, `fs.file-max`, `ip_local_port_range`/`ip_local_reserved_ports`, `nginx` config, `xray` config) | Severity-ranked findings + machine-readable `non_kernel_recommendations` |
| `tuner/scoring.py` | 5-dimensional composite scorer (`T`, `L`, `J`, `R`, `S` on `0..100`) with Hard-Fail Gate across all 4 goal profiles | Per-trial scores for `balanced`, `low-latency`, `max-throughput`, `anti-loss` |
| `tuner/profile.py` | Canonical JSON serializer, PII sanitizer (strips IPs/domains/keys by default), `rthprof1:<base64url(gzip(canonical_json))>` codec, `SHA-256` integrity hash, strict declarative Allow-List validator | Exported JSON / `rthprof1:...` string; validated import dict |
| `tuner/apply.py` | Persistent atomic writer: `/etc/sysctl.d/99-rathole-tune.conf`, `/etc/rathole-tuner/applied-profile.json`, `rathole-net-tune.service` systemd unit (`apply-boot`), pre-apply backup snapshot, and `rollback` | Durable host config + pre-apply snapshot path |
| `tuner/responder.py` | Peer daemon (`--listen`): hosts HMAC control channel, bulk/echo/UDP probe listeners, local `watchdog.py`, isolated responder tunnel endpoints, `--idle-timeout` auto-shutdown | Serves orchestrator sessions cleanly and auto-cleans on disconnect |
| `tuner/orchestrator.py` | Coordinator (`--peer`): manages `run`, `test-profile`, `compare`; streams heartbeats every `5s`, writes atomic `progress.json` for Hub polling, restores baseline in `finally` | Full report + `rathole.netprofile.v1` JSON + `rthprof1:...` output |

### Control Protocol (`tuner/protocol.py`)

- Transport: TCP length-prefixed frames (`4-byte big-endian uint32` length + UTF-8 JSON body, max `1 MiB` per frame).
- Envelope fields: `id`, `action`, `ts` (UTC unix timestamp), `nonce` (16-byte random hex), `payload` (dict), `hmac` (`HMAC-SHA256(token, canonical_message)`).
- Replay protection: Rejects frames with `|now - ts| > 60` seconds or previously seen `nonce` within the TTL window.
- Strict action allow-list:
  - `hello` — protocol version negotiation and role handshake
  - `caps` — report kernel, NIC, sysctl/qdisc/offload capabilities, RAM, and installed tunnel binaries
  - `snapshot` — capture pre-flight snapshot on responder and arm local Watchdog
  - `heartbeat` — reset responder Watchdog deadline (sent every `5s`)
  - `apply_cand` — apply declarative, validated candidate settings (`sysctl`, `mtu`, `route`, `qdisc`, `offload`, `txqueuelen`) on responder side
  - `revert` — immediately restore responder pre-flight snapshot
  - `stats` — fetch responder `TCP_INFO`, `/proc/net/snmp`, NIC/qdisc counters
  - `carrier_start` / `carrier_stop` — start or stop ephemeral isolated carrier benchmark process (`kcptun`, `backhaul`, `frp`, `paqet`, `rathole`) on an isolated probe port (`29900-29999`)
  - `audit` — return non-kernel `audit.py` telemetry from responder
  - `shutdown` — disarm Watchdog, verify baseline restored, exit responder cleanly
- Zero arbitrary commands: Neither control frames nor imported profiles ever contain or execute shell strings (`subprocess.run(..., shell=False)` exclusively).

---

## 3. Data Flow & Execution Modes (`brutal` vs `safe`)

### Execution Lifecycle

```
[Orchestrator (Source / Iran)] <--- HMAC Control + Data/Echo Probes ---> [Responder (Peer / Foreign Node)]
        |                                                                            |
        +--- 1. Capabilities Discovery (kernel, CC, qdisc, NIC/virt, RAM, cores) ----+
        +--- 2. Pre-Flight Atomic Snapshot + Arm Independent Watchdog (both ends) ---+
        +--- 3. Staged Sweeps: apply_cand -> Traffic + Loaded RTT + TCP_INFO -> revert
        +--- 4. Brutal Top-3 Soak Final vs Baseline (simultaneous load + bufferbloat)
        +--- 5. Isolated Tunnel Carrier Matrix (installed cores on test ports) -----+
        +--- 6. Non-Kernel Stack Audit (nginx, xray, systemd, RPS/XPS, governor) ----+
        +--- 7. Guaranteed Baseline Restore + Disarm Watchdog + Stop Responder ------+
        +--- 8. Score All 4 Goals -> Build rathole.netprofile.v1 JSON + rthprof1:... +
```

### Mode Boundaries

| Capability / Mutation | `safe` Mode | `brutal` Mode |
|---|---|---|
| Bidirectional PMTU probe (`ICMP DF` + `UDP IP_PMTUDISC_DO`) | Yes | Yes |
| TCP Segment / MSS probe via per-socket `setsockopt(TCP_MAXSEG)` | Yes | Yes + interface MTU + `ip route advmss` + `iptables -t mangle TCPMSS` + `tcp_mtu_probing`/`tcp_base_mss` |
| Unloaded + Loaded RTT (Bufferbloat), Multi-stream & Bidirectional probes | Yes | Yes |
| Live global `sysctl` mutations (`rmem`/`wmem`, `tcp_notsent_lowat`, CC, `initcwnd`) | No (read-only audit + BDP math recommendation) | Yes (with Snapshot + Watchdog + Rollback) |
| Live NIC mutations (`ip link mtu`, `tc qdisc`, `ethtool -K`/`-G`, `txqueuelen`) | No | Yes (with Snapshot + Watchdog + Rollback; auto-skips unsupported virtual drivers) |
| Isolated carrier benchmarks (`ws`, `kcp`, `backhaul`, `frp`, `gre`, `paqet`) | Yes (ephemeral ports only) | Yes (ephemeral ports + optimal host tuning active during Top-K) |
| Non-kernel audit (`nginx`, `xray`, `ulimit`, `RPS/XPS`, CPU governor) | Yes (read-only) | Yes (read-only report + optional `--apply` recommendations) |

Progress updates are atomically persisted after every trial to `/var/lib/rathole-tuner/jobs/<job_id>/progress.json` (`phase`, `stage_index`, `stage_total`, `completed_trials`, `estimated_trials`, `current_candidate`, `best_so_far`, `elapsed_s`) for CLI live display and Hub UI polling.

---

## 4. Ruthless Parameter Matrix & 6-Stage Search Pipeline

Default runtime targets **3–8 minutes** via coordinate descent with pruning (`--deep` expands trial durations from 5s/10s to 12s/25s, runs 3 repetitions per Top-K finalist, and doubles burst concurrency). Unsupported kernel/NIC knobs detected in Stage 0 are logged as `unsupported` and skipped cleanly.

### Stage 0 — Baseline, PMTU & Capability Discovery (~20s)
- Inventory: kernel version, CPU count, RAM (`MiB`), virtualization type (`kvm`/`xen`/`openvz`/`lxc`), outbound interface + driver (`ethtool -i`), `tcp_available_congestion_control`, installed `qdisc` modules (`fq`, `fq_codel`, `cake`), installed tunnel binaries (`rathole`, `kcptun-*`, `backhaul-*`, `frps`/`frpc`, `paqet`, `xray`, `nginx`).
- Baseline benchmark: unloaded RTT/jitter (`20` samples), TCP single-stream, TCP 4-stream + simultaneous `50ms` Loaded-RTT probe, bidirectional TCP, short-flow burst, UDP loss/jitter probe.
- Bidirectional PMTU discovery: binary search (`1200..1500` B) using ICMP `DF` and `UDP IP_PMTUDISC_DO`, cross-checked against live socket `TCP_INFO.tcpi_pmtu` and `tcpi_snd_mss` to catch silent PMTU blackholes.

### Stage 1 — MTU, TCP Segment (`MSS`), NIC Offloads & Rings (~45s)
- MTU / MSS candidates (bounded by discovered forward/reverse PMTU and MTU floor): `[PMTU, PMTU-20, PMTU-40, 1460, 1420, 1380, 1350, 1280]` (plus GRE overhead deduction `-24/-28/-44/-48` if GRE is present).
- In `safe` mode: swept per-socket via `TCP_MAXSEG`; in `brutal` mode: swept via `ip link set dev <iface> mtu <M>` (or `ip route advmss` + scoped `iptables -t mangle POSTROUTING -m comment --comment rathole-tuner-<id> -j TCPMSS --set-mss <M>`), paired with `net.ipv4.tcp_mtu_probing` (`0`, `1`, `2`), `net.ipv4.tcp_base_mss` (`512`, `1024`, `1200`, `1360`), and `net.ipv4.tcp_min_snd_mss`.
- NIC offloads (`ethtool -K`, `brutal` only): test toggling `tso`, `gso`, `gro`, `lro` (exposes broken VirtIO/vNIC hypervisor offload checksum bugs that drop throughput or spike retransmits).
- Interface queues: `txqueuelen` (`500`, `1000`, `2000`, `5000`) and `ethtool -G` RX/TX ring sizes (default vs 50% max vs 100% hardware max when supported).

### Stage 2 — Congestion Control, Packet Scheduler (`qdisc`) & TCP Pacing (~60s)
- Congestion Control candidates dynamically filtered from `/proc/sys/net/ipv4/tcp_available_congestion_control`: prioritizes `bbr`, `bbr2`/`bbr3`, `cubic`, `hybla`, `westwood`, `reno`.
- `qdisc` candidates (`tc qdisc replace dev <iface> root`): current default vs `fq` (optimal BBR pacing) vs `fq_codel` vs `cake` (if kernel `sch_cake` is present, with optional `bandwidth` cap sweep at 95% measured capacity to eliminate upstream ISP bufferbloat).
- Backpressure / low-latency queue depth: `net.ipv4.tcp_notsent_lowat` swept across `[16384, 32768, 65536, 131072, 4294967295]`.

### Stage 3 — BDP-Scaled Buffers, TCP/UDP Kernel Knobs & Route Windows (~60s)
- Compute Bandwidth-Delay Product from Stage 0–2 measurements:
  $$\text{BDP} = \frac{\text{Bandwidth}_{\text{bps}}}{8} \times \text{RTT}_{\text{s}}$$
- Sweep `1x`, `2x`, `4x`, `8x` BDP buffer profiles (strictly capped at `min(64 MiB, 10% Host RAM)`):
  - `net.core.rmem_max`, `net.core.wmem_max`, `net.core.rmem_default`, `net.core.wmem_default`
  - `net.ipv4.tcp_rmem`, `net.ipv4.tcp_wmem`, `net.ipv4.udp_rmem_min`, `net.ipv4.udp_wmem_min`
- Route initial windows (`ip route change ...`): `initcwnd` / `initrwnd` in `[10, 20, 32, 64]`.
- TCP behavior sweep:
  - `net.ipv4.tcp_slow_start_after_idle` (`0` vs `1`)
  - `net.ipv4.tcp_ecn` (`0`, `1`, `2`)
  - `net.ipv4.tcp_timestamps` (`0`, `1`), `net.ipv4.tcp_fastopen` (`0`, `3`), `net.ipv4.tcp_sack` (`0`, `1`), `net.ipv4.tcp_dsack` (`0`, `1`)
  - `net.ipv4.tcp_autocorking` (`0`, `1`), `net.ipv4.tcp_frto` (`0`, `2`), `net.ipv4.tcp_early_retrans` (`3`), `net.ipv4.tcp_thin_linear_timeouts` (`0`, `1`)
  - `net.ipv4.tcp_tw_reuse` (`0`, `1`, `2`), `net.core.netdev_max_backlog`, `net.core.netdev_budget`, `net.core.somaxconn`, `net.ipv4.tcp_max_syn_backlog`, `net.netfilter.nf_conntrack_max` (when `nf_conntrack` module loaded).

### Stage 4 — Isolated Carrier Live Matrix & Non-Kernel Audit (~60–90s)
Using isolated ephemeral ports (`29900-29999`) so active user tunnels are untouched:
- Raw baseline (`raw-tcp`, `raw-udp`) vs installed cores detected on both sides:
  - `rathole` (`ws`, `plain`, `noise`)
  - `kcp` (`kcptun` profiles `balanced` / `lossy` / `aggressive` + PMTU-derived `mtu` `1280..1400`)
  - `backhaul` (`ws` / `wsmux` across `balanced` / `lossy` / `aggressive`)
  - `frp` (`tcp`, `kcp`, `quic`, `websocket`)
  - `gre` / `frp_gre` (if tunnel interface active: probe inner MTU/MSS)
  - `paqet` (if installed and permitted)
- Concurrent `audit.py` inspection on both hosts checking:
  - CPU scaling governor (`performance` vs `powersave`), multi-queue RPS/XPS mask (`rps_cpus` / `xps_cpus`)
  - Systemd `LimitNOFILE`, `fs.file-max`, `ip_local_port_range`, `ip_local_reserved_ports` conflicts
  - `nginx` (`worker_processes`, `worker_connections`, `proxy_buffering off`, `tcp_nodelay`, `access_log` on data location, SSL session cache)
  - `xray` (`/etc/xray/config.json`: `mux.enabled`, `sockopt.tcpNoDelay`/`tcpFastOpen`/`tcpKeepAliveIdle`, `policy.levels.0.bufferSize`, `log.loglevel`, `dns.servers`, `domainStrategy`)

### Stage 5 — Brutal Top-3 Finalist Soak vs Baseline (~60–90s)
- Re-evaluates Baseline + Top-3 distinct candidate combinations under heavier multi-phase stress (multi-stream saturation + bidirectional full-duplex + rapid short-flow bursts + `50ms` Loaded-RTT Bufferbloat monitoring) so transient lucky spikes are eliminated before declaring the winner.

---

## 5. Safety Invariants & Guardrails

1. **Atomic Pre-Flight Snapshot:** Saved to `/var/lib/rathole-tuner/snapshots/pre-<ts>.json` (mode `0600`) on **both** orchestrator and responder before any mutation occurs.
2. **Independent Watchdog Process:** Both sides spawn `watchdog.py` as a detached process with `TTL = 45s` (`brutal`). Orchestrator dispatches signed `heartbeat` frames every `5s`. If control/SSH breaks for `>= 45s`, Watchdog runs `restore_snapshot()` autonomously with no network dependency.
3. **Host Resource Floor & Caps:**
   - Maximum socket buffer (`rmem_max`/`wmem_max` and `tcp_rmem[2]`/`tcp_wmem[2]`) never exceeds `min(64 MiB, 10% of total system RAM)` to prevent OOM under high concurrency.
   - Interface MTU floor is strictly enforced: `>= 1280` when IPv6 is configured on the interface, and `>= 576` for IPv4-only.
4. **Firewall Hygiene:** Never touches `iptables`/`nftables` `filter` tables or any pre-existing `mangle` rule. Any temporary `TCPMSS` test rule carries comment tag `rathole-tuner-<session_id>` and is swept cleanly on revert.
5. **Graceful Virtualization Degrade:** Containerized/virtualized environments (OpenVZ, LXC, restricted VirtIO) returning `EPERM`, `EOPNOTSUPP`, or missing `/proc/sys/*` paths record that knob as `unsupported` without failing the run.
6. **Guaranteed Restoration:** Control-plane shutdown, `SIGINT`/`SIGTERM`, exceptions, and normal completion always restore the baseline snapshot in a `try/finally` block before tearing down the responder.

---

## 6. 5-Dimensional Scoring Formula & Hard-Fail Gate

Every candidate trial computes 5 normalized sub-scores on `[0.0, 100.0]`:

1. **`T` (Throughput, `0..100`):** Normalized against the best observed weighted capacity across all non-disqualified candidates (plus Baseline):
   $$\text{RawT} = 0.40 \cdot \text{Mbps}_{1\text{-stream}} + 0.40 \cdot \text{Mbps}_{N\text{-stream}} + 0.20 \cdot \text{Mbps}_{\text{bidir}}$$
2. **`L` (Loaded Latency / Bufferbloat, `0..100`):** Measures responsiveness while the pipe is saturated:
   $$\Delta_{\text{bloat}} = \max(0, \text{LoadedRTT}_{p95} - \text{UnloadedRTT}_{p50})$$
   Penalizes both absolute `LoadedRTT_p95` and $\Delta_{\text{bloat}} / \max(10\text{ ms}, \text{UnloadedRTT}_{p50})$.
3. **`J` (Jitter & Tail Stability, `0..100`):** Penalizes elevated `RTT_p99 - RTT_p50` tail spikes and average inter-packet jitter.
4. **`R` (Reliability, `0..100`):** Combines `TCP_INFO` retransmission rate (`tcpi_total_retrans / tcpi_segs_out`), UDP packet loss %, and kernel NIC/qdisc drop deltas.
5. **`S` (Throughput Consistency, `0..100`):** Computed from the per-second Coefficient of Variation ($\text{CoV} = \sigma / \mu$) across the test window (`100 * max(0, 1 - CoV)`), rejecting sawtooth/stalling configs.

### Hard-Fail Gate (Disqualification)

A candidate is immediately marked `disqualified = true` (`score = 0.0`) if any of the following triggers during a trial:
- Control channel dropped or stream timed out / aborted prematurely
- Measured UDP or probe packet loss `> 15.0%`
- Measured TCP retransmission ratio `> 10.0%` AND `> 2.0x` Baseline retransmission ratio

### Goal Weight Matrix

Every completed trial is scored simultaneously across all 4 built-in goal profiles so users/Hub can switch optimization priorities after a single run:

| Goal Profile | `T` (Throughput) | `L` (Loaded RTT) | `J` (Jitter/Tail) | `R` (Reliability) | `S` (Consistency) | Target Use Case |
|---|---|---|---|---|---|---|
| `balanced` | `30%` | `25%` | `15%` | `15%` | `15%` | General web, streaming, mixed Xray workloads |
| `low-latency` | `15%` | `35%` | `25%` | `15%` | `10%` | Gaming, voice/video calls, interactive SSH, instant UI |
| `max-throughput` | `45%` | `15%` | `10%` | `15%` | `15%` | Large downloads, backups, bulk transfers |
| `anti-loss` | `20%` | `15%` | `15%` | `30%` | `20%` | Packet-lossy / DPI-throttled international paths |

---

## 7. Portable AI-Analyzable JSON & Base64url Profile Schema (`rathole.netprofile.v1`)

### JSON Format (`rathole.netprofile.v1`)

```json
{
  "schema": "rathole.netprofile.v1",
  "meta": {
    "id": "prof_20261124_171000_a1b2c3",
    "name": "arvan-to-hetzner-anti-loss",
    "created_at": "2026-11-24T13:40:00Z",
    "tuner_version": "2.3.0",
    "mode": "brutal",
    "goal": "balanced",
    "tags": {
      "iran_dc": "arvan-thr",
      "node_dc": "hetzner-fsn1",
      "isp_note": "mci-edge"
    }
  },
  "environment": {
    "iran": { "kernel": "6.8.0", "cpus": 4, "ram_mb": 4096, "virt": "kvm", "nic_driver": "virtio_net", "available_cc": ["cubic", "bbr"] },
    "node": { "kernel": "6.8.0", "cpus": 2, "ram_mb": 2048, "virt": "kvm", "nic_driver": "virtio_net", "available_cc": ["cubic", "bbr"] },
    "pmtu": { "forward_bytes": 1460, "reverse_bytes": 1460, "blackhole_detected": false }
  },
  "diagnostics": [
    { "code": "bufferbloat_high", "severity": "warning", "detail": "Baseline loaded RTT +118ms vs unloaded 42ms; resolved by fq + tcp_notsent_lowat=32768" }
  ],
  "benchmarks": {
    "baseline": { "throughput_mbps": 184.2, "loaded_rtt_p95_ms": 160.4, "jitter_ms": 14.2, "retrans_pct": 1.8, "stability_cov": 0.24, "scores": { "balanced": 51.3 } },
    "winner":   { "throughput_mbps": 412.6, "loaded_rtt_p95_ms": 48.1,  "jitter_ms": 3.1,  "retrans_pct": 0.2, "stability_cov": 0.05, "scores": { "balanced": 91.8, "low-latency": 93.4, "max-throughput": 89.2, "anti-loss": 92.1 } },
    "top_candidates": [],
    "carriers": {}
  },
  "iran_config": {
    "mtu": 1460,
    "mss_clamp": 0,
    "qdisc": { "kind": "fq", "params": {} },
    "txqueuelen": 2000,
    "route": { "initcwnd": 32, "initrwnd": 32, "advmss": 1420 },
    "offloads": { "tso": true, "gso": true, "gro": true },
    "sysctl": {
      "net.core.default_qdisc": "fq",
      "net.ipv4.tcp_congestion_control": "bbr",
      "net.ipv4.tcp_notsent_lowat": 32768,
      "net.ipv4.tcp_mtu_probing": 1,
      "net.ipv4.tcp_base_mss": 1024,
      "net.ipv4.tcp_slow_start_after_idle": 0,
      "net.ipv4.tcp_ecn": 0,
      "net.core.rmem_max": 16777216,
      "net.core.wmem_max": 16777216,
      "net.ipv4.tcp_rmem": "4096 131072 16777216",
      "net.ipv4.tcp_wmem": "4096 65536 16777216"
    }
  },
  "node_config": {
    "mtu": 1460,
    "mss_clamp": 0,
    "qdisc": { "kind": "fq", "params": {} },
    "txqueuelen": 2000,
    "route": { "initcwnd": 32, "initrwnd": 32, "advmss": 1420 },
    "offloads": { "tso": true, "gso": true, "gro": true },
    "sysctl": {
      "net.core.default_qdisc": "fq",
      "net.ipv4.tcp_congestion_control": "bbr",
      "net.ipv4.tcp_notsent_lowat": 32768,
      "net.ipv4.tcp_mtu_probing": 1,
      "net.ipv4.tcp_base_mss": 1024,
      "net.ipv4.tcp_slow_start_after_idle": 0,
      "net.ipv4.tcp_ecn": 0,
      "net.core.rmem_max": 16777216,
      "net.core.wmem_max": 16777216,
      "net.ipv4.tcp_rmem": "4096 131072 16777216",
      "net.ipv4.tcp_wmem": "4096 65536 16777216"
    },
    "recommended_carrier": { "lane": "kcp", "profile": "balanced", "mtu": 1360 }
  },
  "non_kernel_recommendations": {
    "nginx": [],
    "xray": [],
    "system": []
  },
  "integrity": {
    "sha256": "<hex-sha256-of-canonical-payload-without-integrity>"
  }
}
```

### Compact Base64url String (`rthprof1:...`)

- Encoding: `rthprof1:` + `urlsafe_b64encode(gzip(canonical_json(sort_keys=True, separators=(",", ":")))).rstrip("=")`
- Note: Uses standard `gzip` framing (`zlib.compressobj(level=9, wbits=31)`) so standard tools and scripts can inspect/decode easily.
- Size caps: Maximum `64 KiB` encoded string (`RE_TUNER_PROFILE` limit), maximum `512 KiB` decompressed JSON (zip-bomb protection via bounded read).
- **PII Sanitization:** By default, `export` strips server IPs, domain names, SSH hosts, proxy tokens, and private keys, keeping only hardware/kernel/datacenter tags (`meta.tags` + `environment`).
- **Strict Declarative Allow-List (`profile.validate()`):** When importing/testing/applying any JSON or `rthprof1:...` string (e.g., modified by AI or shared by another operator):
  - Rejects unknown schemas (`!= "rathole.netprofile.v1"`), mismatched `integrity.sha256`, or invalid Base64url padding/checksum.
  - Validates every field in `iran_config` / `node_config` against a strict allow-list:
    - `mtu`: int `[576, 1500]` (and runtime `>= 1280` if IPv6 active)
    - `mss_clamp`: int `0` or `[536, 1460]`
    - `txqueuelen`: int `[100, 20000]`
    - `qdisc.kind`: enum `{"default", "pfifo_fast", "fq", "fq_codel", "cake"}`; `cake` optional numeric `bandwidth_mbps` `[1, 100000]`
    - `route.initcwnd` / `initrwnd`: int `[4, 128]`; `route.advmss`: int `[0, 1460]`
    - `offloads`: bool map strictly over `{"tso", "gso", "gro", "lro"}`
    - `sysctl`: strictly allow-listed keys (`net.core.default_qdisc`, `net.ipv4.tcp_congestion_control`, `net.ipv4.tcp_notsent_lowat`, `net.ipv4.tcp_mtu_probing`, `net.ipv4.tcp_base_mss`, `net.ipv4.tcp_min_snd_mss`, `net.ipv4.tcp_slow_start_after_idle`, `net.ipv4.tcp_ecn`, `net.ipv4.tcp_timestamps`, `net.ipv4.tcp_fastopen`, `net.ipv4.tcp_sack`, `net.ipv4.tcp_dsack`, `net.ipv4.tcp_autocorking`, `net.ipv4.tcp_frto`, `net.ipv4.tcp_early_retrans`, `net.ipv4.tcp_thin_linear_timeouts`, `net.ipv4.tcp_tw_reuse`, `net.core.rmem_max`, `net.core.wmem_max`, `net.core.rmem_default`, `net.core.wmem_default`, `net.core.netdev_max_backlog`, `net.core.netdev_budget`, `net.core.somaxconn`, `net.ipv4.tcp_max_syn_backlog`, `net.ipv4.tcp_rmem`, `net.ipv4.tcp_wmem`, `net.ipv4.udp_rmem_min`, `net.ipv4.udp_wmem_min`, `net.netfilter.nf_conntrack_max`) with exact type/range bounds + `10% RAM` clamping at apply time.
    - No shell command, file path, or arbitrary string is ever accepted.
- **Live Profile Testing & Comparison:**
  - `test-profile`: Runs Baseline vs imported `rathole.netprofile.v1` JSON or `rthprof1:...` string live under Watchdog protection (defaults to `brutal` with safe automatic fallback if needed) and outputs delta %.
  - `compare`: Runs Baseline + 2..N profiles back-to-back on the live link and emits a ranked leaderboard across all 4 goals.

---

## 8. CLI, Hub Integration, Security & Packaging

### Standalone & Native CLI

1. **Standalone CLI (`/usr/local/bin/rathole-tuner`):**
   - `rathole-tuner listen --port <p> --token <hex> [--idle-timeout 600]`
   - `rathole-tuner run --peer <host:port> --token <hex> [--mode brutal|safe] [--goal balanced|low-latency|max-throughput|anti-loss] [--deep] [--tag k:v] [--out-dir <path>] [--apply]`
   - `rathole-tuner test-profile --peer <host:port> --token <hex> --profile <path|rthprof1:...>`
   - `rathole-tuner compare --peer <host:port> --token <hex> <p1> <p2> [...]`
   - `rathole-tuner export <report.json> [--format json|base64] [--name <str>] [--tag k:v]`
   - `rathole-tuner validate <path|rthprof1:...>`
   - `rathole-tuner apply <path|rthprof1:...> [--side iran|node]`
   - `rathole-tuner apply-boot` (invoked by `rathole-net-tune.service` on boot from `/etc/rathole-tuner/applied-profile.json`)
   - `rathole-tuner rollback`
   - `rathole-tuner status [--json]`

2. **Native `ratholectl` & `ratholenode` Subcommands (`bench`):**
   - `ratholectl bench <listen|run|test-profile|compare|export|validate|apply|rollback|status> ...`
   - `ratholenode bench <listen|run|test-profile|compare|export|validate|apply|rollback|status> ...`
   - Wrapping inside `ratholectl` / `ratholenode` automatically passes local tunnel state metadata (carrier info, GRE interface, Nginx/Xray paths) and keeps `ratholeagent.py`'s `ALLOWED_BINARIES` (`ratholectl`, `ratholenode`, `systemctl`, `journalctl`, `jq`, `tail`) completely unchanged — no new binary added to the REST Agent attack surface.

3. **Persistent Apply Layout (`tuner/apply.py`):**
   - Writes sysctl drops to `/etc/sysctl.d/99-rathole-tune.conf` (preserving `/etc/sysctl.d/99-rathole-reserved-ports.conf`).
   - Saves non-sysctl settings (`mtu`, `mss_clamp`, `qdisc`, `txqueuelen`, `route`, `offloads`) to `/etc/rathole-tuner/applied-profile.json` and installs `/etc/systemd/system/rathole-net-tune.service` (`After=network-online.target`, `ExecStart=/usr/local/bin/rathole-tuner apply-boot`).
   - `rollback` restores `/var/lib/rathole-tuner/snapshots/pre-apply-<ts>.json`, removes `/etc/rathole-tuner/applied-profile.json`, restores `/etc/sysctl.d/99-rathole-tune.conf` from snapshot (or removes if none existed), runs `sysctl --system`, and disables `rathole-net-tune.service`.

### Hub Security (`ratholehub/hubcmds.py` & `hub.py`)

- **Regex validation (`hubcmds.py`, all anchored with `\Z`):**
  - `RE_TUNER_MODE = ^(brutal|safe)\Z`
  - `RE_TUNER_GOAL = ^(balanced|low-latency|max-throughput|anti-loss)\Z`
  - `RE_TUNER_PROFILE = ^rthprof1:[A-Za-z0-9_-]{16,65536}\Z`
  - `RE_TUNER_SIDE = ^(iran|node)\Z`
  - `RE_TAG_STR = ^[A-Za-z0-9_.,:-]{1,120}\Z`
  - Reuse `RE_PORT`, `RE_KEY` (16..64 hex for HMAC token), `RE_IPPORT`, `RE_ID` (job/profile id).
- **Actions added to `build_iran_cmd` / `build_node_cmd`:**
  - Read-only: `bench_status` -> `["rathole...", "bench", "status", "--json"]`, `bench_job` -> `["rathole...", "bench", "job", id]`
  - Mutating (added to `WRITE_ACTIONS` -> requires `admin` role + CSRF + Audit log): `bench_listen_start`, `bench_listen_stop`, `bench_run_safe`, `bench_run_brutal`, `bench_test_profile`, `bench_apply`, `bench_rollback`.
- **Hub Async Job Orchestration (`hub.py`):**
  - `POST /api/tuner/start`: Generates random 32-byte hex session `token` (never logged in audit), spawns `bench_listen_start` on target Node (ephemeral `--port`, `--idle-timeout 900`), executes `bench_run_brutal`/`safe` or `bench_test_profile` on Iran server in a background thread, updates job state, and guarantees `bench_listen_stop` in `finally` or on Cancel.
  - `GET /api/tuner/jobs/<id>`: Live progress percentages, current stage, intermediate best score, and final result report + Base64url profile string.
  - `POST /api/tuner/jobs/<id>/cancel`: Cancels background thread and executes `bench_listen_stop` + verifies responder reversion.
  - `GET`, `POST`, `DELETE /api/tuner/profiles`: Persistent profile library at `/var/lib/ratholehub/tuner-profiles.json` (`0600`) with datacenter tags (`iran_dc`, `node_dc`, `name`, `profile_b64`, parsed metrics/summary). Validates incoming JSON or `rthprof1:...` strictly with `profile.validate()` before saving.
  - `POST /api/tuner/apply`: Validates stored/provided `rthprof1:...` profile, applies `iran_config` to selected Iran server and `node_config` to selected Node server atomically (or rolls back Iran if Node apply fails), records pre-apply state in Audit log.
  - `POST /api/tuner/rollback`: Rolls back both servers to their pre-apply snapshots.
  - `RATHOLEHUB_MOCK=1`: Returns deterministic mock benchmark progress/result and lets Hub UI + API tests verify full flows locally without live servers.

### Hub UI (`#/tuner` Route)

- Files updated: `rathole-manager/ratholehub/ui/index.html` (nav link + `#/tuner` view container), `rathole-manager/ratholehub/ui/app.js`, `rathole-manager/ratholehub/ui/i18n.js` (bilingual FA/EN), `rathole-manager/ratholehub/ui/app.css`.
- Layout & Controls:
  1. **Runner Card:** Select `Iran Server` <-> `Foreign Node`, Mode (`brutal` with Watchdog / `safe`), Goal (`balanced` / `low-latency` / `max-throughput` / `anti-loss`), `Deep` toggle, optional datacenter tags (`iran_dc`, `node_dc`), `Start Benchmark` + `Safe Stop` buttons.
  2. **Live Progress & Stage Timeline:** 6-stage indicator + live best score badge during execution.
  3. **Results Comparison Card:** Side-by-side `Baseline` vs `Winner` (Throughput Mbps, Loaded RTT p95 & Bufferbloat delta, Jitter, Retrans/Loss, Stability CoV, 5D Score), Top-K candidate table, isolated carrier matrix (`ws`/`kcp`/`backhaul`/`frp`/`gre`/`paqet`), non-kernel `Nginx`/`Xray`/system findings, plus one-click buttons: **`Copy JSON (for AI)`**, **`Copy Base64 (rthprof1)`**, **`Save to Library`**, **`Apply to Both Servers`**, and **`Rollback`**.
  4. **Datacenter Profile Library & A/B Tester Card:** Saved per-datacenter presets, **`Import JSON / rthprof1:...`** modal (accepts pasted JSON or Base64url string from AI or community), and **`Live Test vs Current Link`** action (`test-profile` / `compare`).

### Packaging, Install & Updates

- `rathole-manager/install-panel.sh`, `rathole-manager/install-node.sh`, and `rathole-manager/update.sh`: Install/sync `rathole-manager/tuner/*.py` into `/usr/local/share/rathole/tuner/` and `rathole-manager/rathole-tuner` into `/usr/local/bin/rathole-tuner` (`chmod 755`, LF normalized).
- `package.sh` and `tools/build_zip.py`: Automatically include everything under `rathole-manager/`, bundling `tuner/` and `rathole-tuner` into `rathole-manager.zip`.

---

## 9. Verification & Automated Test Plan

1. **`tests/test_tuner_core.py` (Python `unittest`):**
   - `protocol.py`: HMAC signing/verification, tampered payload rejection, timestamp window rejection, replay nonce rejection, oversized frame (>1 MiB) rejection, action allow-list rejection.
   - `profile.py`: Canonical JSON serialization, `rthprof1:` encode/decode round-trip, zip-bomb limit rejection, tampered `sha256` rejection, PII stripping verification, Allow-List validator rejecting unknown `sysctl` keys, out-of-range MTU (`<576` / `>1500`), shell metacharacters, and `sysctl` buffer values exceeding `10% RAM`.
   - `scoring.py`: Verifies exact weight rankings across `balanced`, `low-latency`, `max-throughput`, `anti-loss` and verifies Hard-Fail Gate disqualifies loss > 15% / excessive retransmit even with high raw Mbps.
   - `sysstate.py` & `apply.py`: Temp-dir mocked sysctl/applied-profile generation, preserves `99-rathole-reserved-ports.conf`, creates `rathole-net-tune.service` content, and executes `rollback` cleanly.
   - `watchdog.py`: Integration test spawning real watchdog subprocess with 1s TTL on temp snapshot and asserting automatic restoration fires when heartbeat stops.
2. **`tests/test_tuner_loopback.py` (Python `unittest` End-to-End):**
   - Spawns real `Responder` + `Orchestrator` over `127.0.0.1` with injected virtual sysstate/mutator driver; exercises full `run` -> `export --format base64` -> `validate` -> `test-profile` -> `compare` pipeline end-to-end and asserts baseline restoration and clean process shutdown.
3. **`tests/test_tuner_hub.py` & `tests/test_hub_provisioning.js`:**
   - Tests all new `hubcmds.py` regexes against injection payloads (newlines, `;`, `|`, `..`, oversized Base64), verifies `WRITE_ACTIONS` vs read-only permissions, exercises `/api/tuner/*` endpoints in `RATHOLEHUB_MOCK=1`, and validates `#/tuner` UI bindings & i18n keys.
4. **Shell & Packaging Checks (WSL Ubuntu):**
   - `bash -n` and `shellcheck --severity=error` on modified `ratholectl`, `ratholenode`, `install-panel.sh`, `install-node.sh`, `update.sh`.
   - `python3 -m py_compile` on all new Python files + full existing regression suite + `tests/test_release_bundle.sh`.
