#!/usr/bin/env bash
set -uo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
D="$(mktemp -d)"
cleanup(){
  rm -rf "$D"
}
trap cleanup EXIT

find_py(){
  local c
  for c in python3 python python.exe; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import json' >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}
PY_BIN="$(find_py)" || fail "Python 3 is required"

# Source ratholectl in library mode with root/nginx/systemd stubbed
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"

STATE="$D/state.json"
STATE_HIST_DIR="$D/history"
RTH_HISTORY_MAX=20
REGEN_COUNT=0
export STATE STATE_HIST_DIR RTH_HISTORY_MAX

need_root(){ return 0; }
regenerate(){
  REGEN_COUNT=$((REGEN_COUNT + 1))
  return 0
}

cat > "$STATE" <<'JSON'
{
  "domain": "init.example.com",
  "control_port": 2333,
  "proxy_protocol": false,
  "nodes": [
    {"name": "de01", "port": 1001, "inbound_port": 8444}
  ]
}
JSON

# 1) Empty history initially
h0="$(cmd_history --json)" || fail "cmd_history --json failed initially"
"$PY_BIN" - "$h0" <<'PY' || fail "initial history check failed: $h0"
import json, sys
d = json.loads(sys.argv[1])
assert d["count"] == 0, d
assert d["revisions"] == [], d
PY
ok "cmd_history --json reports count=0 before first mutation"

# 2) state_set with bool, duplicate no-op dedup, num, state_jq, str
state_set '.proxy_protocol' true bool || fail "state_set bool failed"
[ "$(jq -r '(.proxy_protocol | type) + ":" + (.proxy_protocol | tostring)' "$STATE")" = "boolean:true" ] || fail "proxy_protocol was not written as JSON boolean"
cnt_after_1="$(find "$STATE_HIST_DIR" -maxdepth 1 -name 'rev-*.json' | wc -l | tr -d ' ')"
[ "$cnt_after_1" = "1" ] || fail "expected 1 snapshot after first mutation, got $cnt_after_1"

# Identical no-op mutation must be deduplicated by cmp -s
state_set '.proxy_protocol' true bool || fail "state_set identical bool failed"
cnt_after_dup="$(find "$STATE_HIST_DIR" -maxdepth 1 -name 'rev-*.json' | wc -l | tr -d ' ')"
[ "$cnt_after_dup" = "1" ] || fail "duplicate snapshot was not suppressed (count=$cnt_after_dup)"
ok "state_set supports bool type and suppresses duplicate pre-mutation snapshots"

state_set '.control_port' 2444 num || fail "state_set num failed"
state_jq '.nodes += [{"name":"fr01","port":1002,"inbound_port":8445}]' || fail "state_jq failed"
state_set '.domain' 'step2.example.com' str || fail "state_set str failed"

h1="$(cmd_history --json)" || fail "cmd_history --json after mutations failed"
"$PY_BIN" - "$h1" <<'PY' || fail "history list assertion failed: $h1"
import json, sys
d = json.loads(sys.argv[1])
assert d["count"] == 4, d
revs = d["revisions"]
assert len(revs) == 4
assert revs[0]["rev"] == 1
assert revs[0]["domain"] == "init.example.com"
assert revs[0]["node_count"] == 2
assert revs[1]["rev"] == 2
assert revs[1]["node_count"] == 1
assert revs[1]["nodes"] == ["de01"]
PY
human_hist="$(cmd_history)" || fail "human cmd_history failed"
grep -Fq 'rev 1' <<<"$human_hist" || fail "human cmd_history output missing rev 1: $human_hist"
ok "cmd_history --json and human table record snapshots newest-first"

# 3) --dry-run previews without changing state or calling regenerate
before_regen="$REGEN_COUNT"
dry_out="$(cmd_undo --dry-run 2)" || fail "cmd_undo --dry-run 2 failed"
grep -Fq '[DRY-RUN]' <<<"$dry_out" || fail "dry-run output missing [DRY-RUN]"
[ "$REGEN_COUNT" = "$before_regen" ] || fail "cmd_undo --dry-run should not call regenerate"
[ "$(jq -r '.domain' "$STATE")" = "step2.example.com" ] || fail "cmd_undo --dry-run mutated live state"
[ "$(jq '.nodes | length' "$STATE")" = "2" ] || fail "cmd_undo --dry-run mutated node count"
ok "cmd_undo --dry-run previews target revision without mutating state or regenerating"

# 4) Actual rollback to rev 2 (init.example.com, 1 node) and reversible undo of undo
cmd_undo 2 >/dev/null || fail "cmd_undo 2 failed"
[ "$REGEN_COUNT" = "$((before_regen + 1))" ] || fail "cmd_undo 2 did not invoke regenerate"
[ "$(jq -r '.domain' "$STATE")" = "init.example.com" ] || fail "cmd_undo 2 did not restore domain"
[ "$(jq '.nodes | length' "$STATE")" = "1" ] || fail "cmd_undo 2 did not restore single node"

# Pre-undo state (step2.example.com, 2 nodes) must now be rev 1 so undo 1 reverses it
cmd_undo 1 >/dev/null || fail "cmd_undo 1 reversal failed"
[ "$REGEN_COUNT" = "$((before_regen + 2))" ] || fail "cmd_undo 1 reversal did not invoke regenerate"
[ "$(jq -r '.domain' "$STATE")" = "step2.example.com" ] || fail "cmd_undo 1 did not reverse back to step2.example.com"
[ "$(jq '.nodes | length' "$STATE")" = "2" ] || fail "cmd_undo 1 did not restore 2 nodes"
ok "cmd_undo restores target revision cleanly and remains reversible"

# 5) Retention pruning under RTH_HISTORY_MAX=3
RTH_HISTORY_MAX=3
for i in 1 2 3 4 5; do
  state_set '.control_port' "$((2500 + i))" num || fail "state_set retention step $i failed"
done
kept_cnt="$(find "$STATE_HIST_DIR" -maxdepth 1 -name 'rev-*.json' | wc -l | tr -d ' ')"
[ "$kept_cnt" -eq 3 ] || fail "expected RTH_HISTORY_MAX=3 to keep 3 snapshots, got $kept_cnt"
latest_snap="$(find "$STATE_HIST_DIR" -maxdepth 1 -name 'rev-*.json' | sort | tail -n 1)"
[ "$(jq -r '.control_port' "$latest_snap")" = "2504" ] || fail "newest kept snapshot had wrong control_port"
[ "$(jq -r '.control_port' "$STATE")" = "2505" ] || fail "live state control_port mismatch after pruning loop"
ok "RTH_HISTORY_MAX=3 prunes older snapshots cleanly"

# 6) Validation rejects invalid revision numbers
if (cmd_undo 0) >/dev/null 2>&1; then
  fail "cmd_undo accepted rev=0"
fi
if (cmd_undo "../1") >/dev/null 2>&1; then
  fail "cmd_undo accepted path traversal rev"
fi
if (cmd_undo 99) >/dev/null 2>&1; then
  fail "cmd_undo accepted nonexistent rev=99"
fi
ok "cmd_undo rejects invalid or out-of-range revision arguments"
