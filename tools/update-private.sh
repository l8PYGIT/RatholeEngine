#!/usr/bin/env bash
# update-e repo-ye private: API-ye GitHub -> release assets -> bootstrap --local --update.
# baraye node/panel/hub yeksan ast; naghsh az nasb-e mojood tashkhis dade mishavad.
set +x
set -euo pipefail
umask 077

die(){ printf '[!] %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die 'ba sudo bash tools/update-private.sh ejra kon.'
for tool in curl python3; do command -v "$tool" >/dev/null || die "$tool nasb nist."; done
repo="${RATHOLE_GH:-loopy-iri/tunnelplus}"
release="${RATHOLE_RELEASE:-latest}"
[[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || die 'repo bayad owner/repo bashad.'
[[ "$release" =~ ^[A-Za-z0-9._-]+$ ]] || die 'release namotabar ast.'
github_token="${RATHOLE_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"
if [ -z "$github_token" ]; then
  IFS= read -r -s -p 'GitHub token (makhfi): ' github_token < /dev/tty || die 'token ra ba RATHOLE_GH_TOKEN bede.'
  printf '\n' >&2
fi
[[ "$github_token" =~ ^[A-Za-z0-9_]+$ ]] && [ "${#github_token}" -le 256 ] || die 'token khali ya namotabar ast.'

tmp="$(mktemp -d)"
trap 'unset github_token RATHOLE_GH_TOKEN GH_TOKEN GITHUB_TOKEN; rm -rf -- "$tmp"' EXIT
api="https://api.github.com/repos/$repo"
fetch(){
  # credential dar argv-e curl ya mirror-e omoomi gharar nemigirad.
  printf 'header = "Authorization: Bearer %s"\n' "$github_token" |
    curl --config - --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 300 --retry 2 \
      -H "Accept: $3" "$1" -o "$2"
}
endpoint="$api/releases/latest"
[ "$release" = latest ] || endpoint="$api/releases/tags/$release"
fetch "$endpoint" "$tmp/release.json" application/vnd.github+json || die 'daryaft release nashod; dastresi Contents:read va tag ra check kon.'
metadata="$(python3 - "$tmp/release.json" <<'PY'
import json,sys
assets=json.load(open(sys.argv[1],encoding='utf-8')).get('assets',[])
def asset(name):
    found=next((a for a in assets if a.get('name')==name),{})
    value=found.get('id')
    return value if type(value) is int and value>0 else None
bootstrap=asset('bootstrap.sh')
bundle=asset('rathole-manager.zip')
ext='zip'
if not bundle: bundle=asset('rathole-manager.tar.gz');ext='tar.gz'
if not bootstrap or not bundle:
    sys.exit('Release bayad bootstrap.sh va rathole-manager.zip (ya .tar.gz) dashte bashad.')
print(bootstrap,bundle,ext)
PY
)" || die 'asset-haye nasb dar in release kamel nistand.'
read -r bootstrap_id bundle_id extension <<< "$metadata"
fetch "$api/releases/assets/$bootstrap_id" "$tmp/bootstrap.sh" application/octet-stream || die 'download bootstrap shekast khord.'
fetch "$api/releases/assets/$bundle_id" "$tmp/rathole-manager.$extension" application/octet-stream || die 'download bundle shekast khord.'
unset github_token RATHOLE_GH_TOKEN GH_TOKEN GITHUB_TOKEN
printf '[+] Release %s daryaft shod; update ba backup va health-check shoroo mishavad.\n' "$release"
RATHOLE_GH="$repo" RATHOLE_RELEASE="$release" bash "$tmp/bootstrap.sh" --local "$tmp/rathole-manager.$extension" --update
