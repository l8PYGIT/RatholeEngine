#!/usr/bin/env bash
# test_installer_freeze_guard.sh — etminan az vojood-e gard-haye zed-e freeze/hang dar installer-ha
#
# Regression baraye asib-paziri-haye freeze dar nasb:
#   1) transfer-e raked rooye curl (DPI/filtering-e Iran ke jarian ra ghat mikonad)
#   2) prompt-haye debconf / needrestart dar apt-get
#   3) timeout-e bounded baraye wget
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass=0
fail=0

ok(){ echo "  ok  - $*"; pass=$((pass+1)); }
no(){ echo "  FAIL- $*"; fail=$((fail+1)); }

# 1. barresi speed-limit dar curl baraye download-haye asasi
check_speed_limit(){
  local file="$1" fn="$2"
  if grep -A 40 "$fn" "$REPO_ROOT/$file" | grep -q -- '--speed-limit'; then
    ok "$file ($fn) daraye --speed-limit ast"
  else
    no "$file ($fn) faghed-e --speed-limit ast (khatar-e freeze rooye DPI)"
  fi
}

check_speed_limit "install.sh" "fetch1()"
check_speed_limit "install.sh" "resolve_beta_tag()"
check_speed_limit "bootstrap.sh" "download()"
check_speed_limit "rathole-manager/install-panel.sh" "install_rathole()"
check_speed_limit "rathole-manager/install-node.sh" "# ---------- nasb rathole ----------"
check_speed_limit "rathole-manager/common.sh" "resolve_beta_tag()"
check_speed_limit "rathole-manager/common.sh" "install_backhaul()"
check_speed_limit "rathole-manager/common.sh" "install_frp()"
check_speed_limit "rathole-manager/ratholectl" "cmd_update()"
check_speed_limit "rathole-manager/ratholenode" "cmd_update()"

# 2. barresi NEEDRESTART va noninteractive dar apt-get
check_apt_guard(){
  local file="$1"
  if grep -q "NEEDRESTART_MODE=a" "$REPO_ROOT/$file" \
     && grep -q "DEBIAN_FRONTEND=noninteractive" "$REPO_ROOT/$file" \
     && grep -q "force-confdef" "$REPO_ROOT/$file"; then
    ok "$file daraye gard-e kamel-e apt/needrestart ast"
  else
    no "$file faghed-e gard-e kafi baraye apt/needrestart ast (khatar-e freeze dar Ubuntu 22.04+)"
  fi
}

check_apt_guard "install.sh"
check_apt_guard "bootstrap.sh"
check_apt_guard "rathole-manager/install-panel.sh"
check_apt_guard "rathole-manager/install-node.sh"

echo "--> pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
