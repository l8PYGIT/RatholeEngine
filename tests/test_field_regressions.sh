#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RATHOLENODE_LIB_ONLY=1
source "$ROOT/rathole-manager/ratholenode"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/node.env"; SVC_FILE="$TMP/services.conf"; CLIENT_TOML="$TMP/client.toml"
printf 'SERVER=panel.example\n' > "$ENV_FILE"
printf 'n1|token123|2087\n' > "$SVC_FILE"
gen_client
grep -q 'remote_addr = "panel.example:443"' "$CLIENT_TOML"
printf 'SERVER=panel.example:8443\n' > "$ENV_FILE"
gen_client
grep -q 'remote_addr = "panel.example:8443"' "$CLIENT_TOML"
need_root(){ :; }
# Invalid inputs must fail BEFORE changing the registry.
cp "$SVC_FILE" "$TMP/original"
for port in 0 65536 999999 x; do
 if (cmd_add_svc bad token123 "$port") >/dev/null 2>&1; then echo "accepted bad port $port"; exit 1; fi
 cmp "$SVC_FILE" "$TMP/original"
done
for token in 'token ' ' token' $'token\nother'; do
 if (cmd_add_svc bad "$token" 2087) >/dev/null 2>&1; then echo 'accepted bad token'; exit 1; fi
 cmp "$SVC_FILE" "$TMP/original"
done
# Standalone installer must reject a copied token with whitespace without package writes.
if (id(){ echo 0; }; export -f id; bash "$ROOT/rathole-manager/install-node.sh" --server panel.example --name n1 --token 'token ' --inbound-port 2087) >"$TMP/error" 2>&1; then exit 1; fi
grep -q 'token namotabar' "$TMP/error"
echo 'ok - default TLS port, explicit port, invalid ports and copied tokens'
