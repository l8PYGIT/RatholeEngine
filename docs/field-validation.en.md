# Field reliability validation

These fixes address observed installation failures and hub overload. They do not
claim exhaustive absence of bugs across all optional carriers.

## Executed on three user-authorized Linux hosts

- Two Ubuntu 24.04 hosts (Iran front end and a foreign node), kernel 6.8;
  one foreign AWS host with kernel 7.0 and Python 3.14.
- 22 existing shell regression scripts on each host. Two initial failures on one
  foreign node were traced to missing jq; both passed after installing jq.
- Final changed-code run: 110 Python tests per host, all passing with the opt-in
  real-core suite enabled. Field regression, node configuration, failure propagation
  and hardening shell tests were also rerun successfully on every host.
- Real installed Rathole core: TCP, WebSocket and Noise loopback payload round trips
  on all three hosts (nine integration checks). These tests use temporary files,
  ephemeral loopback ports and child processes, without changing production state.
- Existing WSS/TLS nginx tunnels: three authenticated VLESS requests through the Iran
  domain to each foreign node. All six requests returned the expected node egress.
- Local JS checks: 45 provisioning cases, plus an overlapping-poll/retry test.

## Scope and limitations

FRP/GRE/Backhaul/KCP/adaptive/rollback coverage in the shell regression suite uses
stubs and generated configuration checks. This is not proof of end-to-end operation
of each optional carrier across an actual filtered Internet path. Live destructive
failover, host reboot, fresh install and full rollback were not exercised against
production servers. No performance throughput claim follows from these checks.

The project code was tested in temporary source directories on these hosts; it was
not deployed wholesale to production. Deployment-specific credentials, IP addresses,
private keys, live state and raw logs are deliberately excluded from the contribution.

To reproduce the optional binary checks:

```sh
RATHOLE_TEST_BIN=/path/to/rathole python3 tests/test_real_core.py -v
```

The normal Python suite skips these checks unless the binary is explicitly supplied.
