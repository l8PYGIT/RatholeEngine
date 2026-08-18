#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$ROOT/rathole-manager/ratholectl"

# doctor bayad command-ha ra be soorat-e argv ejra konad؛ eval
# mitavanad meghdar-e config/state ra be shell code tabdil konad.
if grep -qE 'eval[[:space:]]+"\$2"' "$CLI"; then
  echo "not ok - doctor hanooz eval-e command darad" >&2
  exit 1
fi

grep -q 'check_active(){' "$CLI"
grep -q 'check_listen(){' "$CLI"
bash -n "$CLI"
echo "ok - doctor command checks argv-safe hastand"
