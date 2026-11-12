# Field reliability validation

These fixes address reproduced installation, diagnostics and adaptive-controller
failures. They do not claim exhaustive absence of bugs across every environment.

## Test matrix

Three user-authorized Linux hosts were used: two Ubuntu 24.04 / kernel 6.8 hosts
(front end and foreign node), and one AWS / kernel 7.0 host with Python 3.14.
Production credentials, public addresses, private keys and raw logs are excluded.

- Full Python regressions with explicitly supplied real binaries on every host.
- Full shell regression suite on every host. Missing jq initially caused misleading
  failures on one node; installing jq fixed both and the node installer now requires it.
- Real Rathole TCP, WebSocket and Noise payload checks on every host.
- Real FRP TCP/KCP/QUIC/WebSocket, Backhaul WS/WSMUX and three kcptun profiles:
  wrong-key rejection, payload delivery, stopped-client failure and reconnection,
  using ephemeral loopback listeners on every host.
- Real kernel GRE in isolated network namespaces on every host: payload, MTU 1476,
  link failure/recovery and FRP carried over GRE.
- Actual transient systemd units on every host reproduced the configuration-lock
  failure and verified the scoped ReadWritePaths fix. Production units were untouched.
- Real tar snapshot/restore of temporary config/unit fixtures on every host, including
  an unhealthy-after-restore failure result; service-control calls were stubbed.
- Generated nginx configuration on the front end, in a separate nginx instance:
  TLS/path routing, reverse proxy, hub/sub paths, plain/header routing and SNI passthrough.
- Actual WSS-to-KCP failover and WSS recovery using a real core, nginx, kcptun, temporary
  state, hot reload and payload verification. Cooldown, hostname rejection and an
  alternate with a listening local socket but a dead remote were checked.
- Live front-end-to-foreign-node payloads over FRP TCP/KCP/WebSocket and Backhaul
  WS/WSMUX succeeded for both nodes; three raw kcptun profiles worked node-to-front-end.
- Three authenticated requests through each existing production WSS/TLS tunnel returned
  the expected node egress. Existing production core/panel state was not switched.
- Browser code: provisioning regression suite and overlapping-poll/retry checks.

## Negative results and limits

FRP/QUIC worked on loopback on all hosts but timed out over both tested Internet
paths, including extended retries. This is an unresolved path-specific observation,
not evidence that QUIC works on these routes and not a confirmed manager defect.
GRE/GRE+FRP were tested in namespaces, not over the providers' public GRE paths.

No production reboot, destructive full-system rollback or clean OS installation was
performed. Snapshot tests validate real archive bytes and error propagation while
stubbing service restarts. Per-node TLS ingress tests require nginx and were run only
on the front-end host. There is no throughput claim or guarantee against filtering.

Backhaul's inherited TLS verification policy is unchanged by this contribution.
Third-party x-ui runtime/user state remains externally managed. The complete patched
source was tested in isolated source/lab paths, not installed wholesale on production.

## Reproduce opt-in checks

```sh
RATHOLE_TEST_BIN=/path/to/rathole python3 tests/test_real_core.py -v
FRPS_TEST_BIN=/path/to/frps FRPC_TEST_BIN=/path/to/frpc \
BACKHAUL_TEST_BIN=/path/to/backhaul KCP_SERVER_TEST_BIN=/path/to/kcptun-server \
KCP_CLIENT_TEST_BIN=/path/to/kcptun-client python3 tests/test_real_carriers.py -v
RATHOLE_REAL_GRE=1 FRPS_TEST_BIN=/path/to/frps FRPC_TEST_BIN=/path/to/frpc bash tests/test_real_gre.sh
RATHOLE_REAL_SYSTEMD=1 RATHOLE_TEST_BIN=/path/to/rathole bash tests/test_real_systemd_lock.sh
RATHOLE_REAL_SNAPSHOT=1 bash tests/test_real_snapshot.sh
NGINX_TEST_BIN=/path/to/nginx python3 tests/test_real_nginx.py -v
NGINX_TEST_BIN=/path/to/nginx RATHOLE_TEST_BIN=/path/to/rathole \
KCP_SERVER_TEST_BIN=/path/to/kcptun-server KCP_CLIENT_TEST_BIN=/path/to/kcptun-client \
python3 tests/test_real_adaptive.py -v
```

GRE/systemd/snapshot scripts are explicitly opt-in and require a suitable Linux/root
lab. Their default invocation skips destructive/system-level operations. The ordinary
Python suite skips optional binary tests unless their paths are explicitly supplied.
