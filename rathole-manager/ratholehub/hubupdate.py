#!/usr/bin/env python3
# hubupdate.py — download va tayid-e Ed25519 release baraye Hub + ersal-e relay-shode be server-ha.
# Faghat Python 3 stdlib (+ tg_relay); hich dependency khareji nadarad.
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urljoin, urlparse

try:
    import tg_relay
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import tg_relay


UPDATE_RELAY_MODES = ("auto", "direct", "relay")
DEFAULT_PUBKEY_PATHS = (
    "/usr/local/share/rathole/keys/release-ed25519.pub",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "keys", "release-ed25519.pub")),
)
_RE_SLUG = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,64}\Z")
_RE_REL = re.compile(r"^(?:latest|v?[0-9][0-9A-Za-z._-]{0,63})\Z")
_RE_SUM_LINE = re.compile(r"^([A-Fa-f0-9]{64})\s+[*]?(.+?)\s*$")
_ALLOWED_BUNDLES = ("rathole-manager.zip", "rathole-manager.tar.gz")
_REDIRECT_CODES = (301, 302, 303, 307, 308)


class VerificationError(ValueError):
    """Cryptographic signature or SHA-256 verification failed."""


def _make_conn(parsed, proxy_url="", timeout=60, ssl_context=None):
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("invalid download URL scheme or host")
    port = parsed.port or (443 if scheme == "https" else 80)
    if scheme == "https":
        return tg_relay.ProxyHTTPSConnection(
            parsed.hostname,
            port=port,
            context=ssl_context,
            timeout=timeout,
            proxy_url=proxy_url,
            proxy_ssl_context=ssl_context,
        )
    return tg_relay.ProxyHTTPConnection(
        parsed.hostname,
        port=port,
        timeout=timeout,
        proxy_url=proxy_url,
        proxy_ssl_context=ssl_context,
    )


def _open_http_response(url, proxy_url="", timeout=60, max_redirects=5, ssl_context=None):
    if proxy_url and not tg_relay.valid_proxy_url(proxy_url):
        raise ValueError("invalid proxy URL")
    current = str(url or "").strip()
    hops = 0
    while True:
        parsed = urlparse(current)
        conn = _make_conn(parsed, proxy_url=proxy_url, timeout=timeout, ssl_context=ssl_context)
        req_path = parsed.path or "/"
        if parsed.query:
            req_path = f"{req_path}?{parsed.query}"
        headers = {
            "User-Agent": "ratholehub/1.0",
            "Accept": "*/*",
            "Connection": "close",
        }
        try:
            conn.request("GET", req_path, headers=headers)
            resp = conn.getresponse()
            status = int(resp.status)
            if status in _REDIRECT_CODES:
                loc = resp.getheader("Location", "") or ""
                try:
                    resp.read(4096)
                except Exception:
                    pass
                conn.close()
                if not loc:
                    raise RuntimeError(f"HTTP {status} missing Location")
                if hops >= int(max_redirects):
                    raise RuntimeError("too many HTTP redirects")
                nxt = urljoin(current, loc)
                nxt_scheme = (urlparse(nxt).scheme or "").lower()
                if nxt_scheme not in ("http", "https"):
                    raise RuntimeError(f"disallowed redirect scheme: {nxt_scheme}")
                current = nxt
                hops += 1
                continue
            if not (200 <= status < 300):
                conn.close()
                raise RuntimeError(f"HTTP {status} for {tg_relay.redact_secrets(current)}")
            return status, current, resp, conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            raise


def http_download_file(url, dest_path, proxy_url="", timeout=60, max_redirects=5, max_bytes=120 * 1024 * 1024, ssl_context=None):
    status, final_url, resp, conn = _open_http_response(
        url, proxy_url=proxy_url, timeout=timeout, max_redirects=max_redirects, ssl_context=ssl_context
    )
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    tmp = dest_path + ".tmp"
    total = 0
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > int(max_bytes):
                    raise RuntimeError("download exceeded max_bytes limit")
                f.write(chunk)
        os.replace(tmp, dest_path)
        return status, final_url
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def resolve_beta_tag_via_relay(gh_repo, proxy_url="", base_url="https://github.com", timeout=20, ssl_context=None):
    if not _RE_SLUG.match(str(gh_repo or "")):
        raise ValueError(f"invalid repo slug: {gh_repo!r}")
    atom_url = f"{base_url.rstrip('/')}/{gh_repo}/releases.atom"
    _st, _final, resp, conn = _open_http_response(
        atom_url, proxy_url=proxy_url, timeout=timeout, max_redirects=4, ssl_context=ssl_context
    )
    try:
        body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    for m in re.finditer(r"releases/tag/(v[0-9A-Za-z._-]+)", body):
        tag = m.group(1)
        if re.search(r"-(beta|rc|alpha)", tag):
            return tag
    raise RuntimeError(f"no beta/prerelease tag found in {gh_repo} releases.atom")


def verify_sha256sums(sums_path, files_map):
    if not sums_path or not os.path.isfile(sums_path):
        raise VerificationError("SHA256SUMS file not found")
    expected = {}
    with open(sums_path, "r", encoding="utf-8", errors="replace") as f:
        for raw_ln in f:
            ln = raw_ln.strip()
            if not ln:
                continue
            m = _RE_SUM_LINE.match(ln)
            if not m:
                continue
            digest = m.group(1).lower()
            fname = m.group(2).lstrip("*").strip()
            if fname.startswith("./"):
                fname = fname[2:]
            expected[fname] = digest
    for name, local_path in (files_map or {}).items():
        key = str(name).lstrip("./")
        if key not in expected:
            raise VerificationError(f"{key} missing from SHA256SUMS")
        if not local_path or not os.path.isfile(local_path):
            raise VerificationError(f"local file missing for checksum verification: {key}")
        h = hashlib.sha256()
        with open(local_path, "rb") as fh:
            while True:
                blk = fh.read(65536)
                if not blk:
                    break
                h.update(blk)
        actual = h.hexdigest().lower()
        if actual != expected[key]:
            raise VerificationError(f"SHA256 mismatch for {key}")
    return True


def find_signing_pubkey(pubkey_path=""):
    cands = []
    if pubkey_path:
        cands.append(str(pubkey_path))
    env_pub = os.environ.get("RATHOLE_SIGNING_PUBKEY", "")
    if env_pub:
        cands.append(env_pub)
    cands.extend(DEFAULT_PUBKEY_PATHS)
    for c in cands:
        if c and os.path.isfile(c) and os.path.getsize(c) > 0:
            return c
    return ""


def verify_ed25519_sig(file_path, sig_path, pubkey_path="", require_sig=False):
    if not file_path or not os.path.isfile(file_path):
        raise VerificationError("target file missing for Ed25519 verification")
    if not sig_path or not os.path.isfile(sig_path) or os.path.getsize(sig_path) == 0:
        if require_sig:
            raise VerificationError("Ed25519 signature required but missing")
        return {"verified": False, "pubkey": "", "reason": "no signature"}

    pub = find_signing_pubkey(pubkey_path)
    if not pub:
        if require_sig:
            raise VerificationError("Ed25519 signature required but no public key found")
        return {"verified": False, "pubkey": "", "reason": "no pubkey"}

    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        raise VerificationError("openssl unavailable for Ed25519 verification")

    with open(sig_path, "rb") as f:
        raw_input = f.read()

    import base64
    raw_sig = None
    compact = re.sub(rb"\s+", b"", raw_input)
    try:
        dec = base64.b64decode(compact, validate=True)
        if len(dec) == 64:
            raw_sig = dec
    except Exception:
        pass
    if raw_sig is None and len(raw_input) == 64:
        raw_sig = raw_input
    if raw_sig is None or len(raw_sig) != 64:
        raise VerificationError("invalid Ed25519 signature format")

    fd, tmp_sig = tempfile.mkstemp(prefix="rth-sig-")
    try:
        with os.fdopen(fd, "wb") as tf:
            tf.write(raw_sig)
        proc = subprocess.run(
            [openssl_bin, "pkeyutl", "-verify", "-pubin", "-inkey", pub, "-rawin", "-sigfile", tmp_sig, "-in", file_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
    finally:
        try:
            os.remove(tmp_sig)
        except OSError:
            pass

    if proc.returncode != 0:
        raise VerificationError("invalid Ed25519 signature")
    return {"verified": True, "pubkey": pub, "reason": "ok"}


def _build_candidates(proxy_url="", inventory=None):
    cands = []
    if proxy_url:
        cands.append((f"proxy ({tg_relay.redact_secrets(proxy_url, [proxy_url])})", "proxy", proxy_url, None))
    cands.append(("direct", "direct", "", None))
    for srv in (inventory or []):
        if not isinstance(srv, dict):
            continue
        if srv.get("role") == "node" and srv.get("transport", "ssh") != "api" and srv.get("host"):
            name = str(srv.get("name", srv.get("host")))
            cands.append((f"ssh_relay:{name}", "ssh", "", srv))
    return cands


def _download_attempt(gh_repo, channel, active_proxy, attempt_dir, base_url, pubkey_path, require_sig, timeout, ssl_context):
    if channel == "beta":
        rel = resolve_beta_tag_via_relay(
            gh_repo, proxy_url=active_proxy, base_url=base_url, timeout=min(timeout, 25), ssl_context=ssl_context
        )
    elif channel in ("stable", "latest", ""):
        rel = "latest"
    else:
        if not _RE_REL.match(str(channel)):
            raise ValueError(f"invalid release tag: {channel!r}")
        rel = str(channel)

    base = f"{base_url.rstrip('/')}/{gh_repo}/releases"
    dl = f"{base}/latest/download" if rel == "latest" else f"{base}/download/{rel}"

    boot_path = os.path.join(attempt_dir, "bootstrap.sh")
    http_download_file(f"{dl}/bootstrap.sh", boot_path, proxy_url=active_proxy, timeout=timeout, ssl_context=ssl_context)

    bundle_name = ""
    bundle_path = ""
    last_bundle_err = None
    for bname in _ALLOWED_BUNDLES:
        cand_path = os.path.join(attempt_dir, bname)
        try:
            http_download_file(f"{dl}/{bname}", cand_path, proxy_url=active_proxy, timeout=timeout, ssl_context=ssl_context)
            bundle_name = bname
            bundle_path = cand_path
            break
        except Exception as exc:
            last_bundle_err = exc
    if not bundle_path:
        raise RuntimeError(f"bundle download failed: {last_bundle_err}")

    sums_path = os.path.join(attempt_dir, "SHA256SUMS")
    has_sums = False
    try:
        http_download_file(f"{dl}/SHA256SUMS", sums_path, proxy_url=active_proxy, timeout=min(timeout, 30), ssl_context=ssl_context)
        has_sums = os.path.isfile(sums_path) and os.path.getsize(sums_path) > 0
    except Exception:
        if require_sig:
            raise VerificationError("SHA256SUMS missing but require_sig is enabled")

    sig_path = os.path.join(attempt_dir, "SHA256SUMS.sig")
    if has_sums:
        try:
            http_download_file(f"{dl}/SHA256SUMS.sig", sig_path, proxy_url=active_proxy, timeout=min(timeout, 30), ssl_context=ssl_context)
        except Exception:
            if os.path.exists(sig_path):
                try:
                    os.remove(sig_path)
                except OSError:
                    pass
        sig_info = verify_ed25519_sig(sums_path, sig_path, pubkey_path=pubkey_path, require_sig=require_sig)
        verify_sha256sums(sums_path, {bundle_name: bundle_path, "bootstrap.sh": boot_path})
    else:
        if require_sig:
            raise VerificationError("SHA256SUMS missing for signature verification")
        sig_info = {"verified": False, "pubkey": "", "reason": "no SHA256SUMS"}

    return rel, bundle_name, boot_path, bundle_path, sig_info


def download_verified_release(
    gh_repo,
    channel="stable",
    proxy_url="",
    inventory=None,
    ssh_cfg=None,
    ssh_base_fn=None,
    pubkey_path="",
    require_sig=False,
    base_url="https://github.com",
    timeout=60,
    ssl_context=None,
    dest_dir="",
):
    del ssh_base_fn
    if not _RE_SLUG.match(str(gh_repo or "")):
        raise ValueError(f"invalid gh_repo slug: {gh_repo!r}")
    if proxy_url and not tg_relay.valid_proxy_url(proxy_url):
        raise ValueError("invalid proxy URL")

    root_dir = dest_dir or tempfile.mkdtemp(prefix="rth-release-")
    os.makedirs(root_dir, exist_ok=True)
    attempts = []
    cands = _build_candidates(proxy_url=proxy_url, inventory=inventory)

    for idx, (label, kind, cand_proxy, node) in enumerate(cands):
        attempt_dir = os.path.join(root_dir, f"try-{idx}")
        os.makedirs(attempt_dir, exist_ok=True)
        tunnel = None
        active_proxy = cand_proxy
        try:
            if kind == "ssh":
                srv_rec = {
                    "name": node.get("name", node.get("host", "node")),
                    "host": node.get("host", ""),
                    "user": node.get("ssh_user") or node.get("user") or "root",
                    "port": node.get("ssh_port") or node.get("port") or 22,
                }
                tunnel = tg_relay.SshRelayTunnel(
                    srv_rec,
                    ssh_key_path=(ssh_cfg or {}).get("ssh_key_path", ""),
                    ssh_opts=(ssh_cfg or {}).get("ssh_opts", []),
                    local_port=tg_relay.pick_free_local_port(),
                )
                active_proxy = tunnel.proxy_url

            rel, bname, boot_p, bundle_p, sig_info = _download_attempt(
                gh_repo,
                channel,
                active_proxy,
                attempt_dir,
                base_url,
                pubkey_path,
                bool(require_sig),
                timeout,
                ssl_context,
            )
            final_boot = os.path.join(root_dir, "bootstrap.sh")
            final_bundle = os.path.join(root_dir, bname)
            os.replace(boot_p, final_boot)
            os.replace(bundle_p, final_bundle)
            shutil.rmtree(attempt_dir, ignore_errors=True)
            attempts.append({"via": label, "ok": True})
            return {
                "ok": True,
                "via": label,
                "release": rel,
                "bundle_name": bname,
                "bootstrap_path": final_boot,
                "bundle_path": final_bundle,
                "work_dir": root_dir,
                "sig": sig_info,
                "attempts": attempts,
            }
        except VerificationError:
            shutil.rmtree(attempt_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(attempt_dir, ignore_errors=True)
            err_s = tg_relay.redact_secrets(str(exc), [proxy_url] if proxy_url else ())
            attempts.append({"via": label, "ok": False, "error": err_s})
        finally:
            if tunnel is not None:
                try:
                    if hasattr(tunnel, "close"):
                        tunnel.close()
                    elif hasattr(tunnel, "stop"):
                        tunnel.stop()
                except Exception:
                    pass

    summary = "; ".join(f"{a['via']}: {a.get('error', '?')}" for a in attempts)
    raise RuntimeError(f"release download failed via all paths ({summary})")


def push_and_run_update(server, ssh_base_cmd, bootstrap_path, bundle_path, bundle_name, gh_repo, release_tag, require_sig=False, timeout=600):
    del server
    if bundle_name not in _ALLOWED_BUNDLES:
        raise ValueError(f"invalid bundle_name: {bundle_name!r}")
    if not _RE_SLUG.match(str(gh_repo or "")):
        raise ValueError(f"invalid gh_repo: {gh_repo!r}")
    if not _RE_REL.match(str(release_tag or "")):
        raise ValueError(f"invalid release_tag: {release_tag!r}")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for src, arcname, mode in ((bootstrap_path, "bootstrap.sh", 0o755), (bundle_path, bundle_name, 0o644)):
            ti = tf.gettarinfo(src, arcname=arcname)
            ti.mode = mode
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            with open(src, "rb") as fh:
                tf.addfile(ti, fh)

    req_flag = "1" if require_sig else "0"
    remote_script = (
        "set -e\n"
        'T="$(mktemp -d)"\n'
        'trap \'rm -rf "$T"\' EXIT\n'
        'tar -xf - -C "$T"\n'
        f'export RATHOLE_GH="{gh_repo}" RATHOLE_RELEASE="{release_tag}" RATHOLE_REQUIRE_SIG="{req_flag}"\n'
        f'bash "$T/bootstrap.sh" --local "$T/{bundle_name}" --update\n'
    )
    cmd = list(ssh_base_cmd) + ["bash", "-c", remote_script]
    try:
        proc = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=timeout)
        out_s = (proc.stdout or b"").decode("utf-8", errors="replace")
        err_s = (proc.stderr or b"").decode("utf-8", errors="replace")
        return {"rc": proc.returncode, "out": out_s, "err": err_s}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "SSH relayed update timeout"}
    except Exception as exc:
        return {"rc": 1, "out": "", "err": str(exc)}


_NET_FAIL_MARKERS = (
    "download install.sh",
    "filtering",
    "mirror",
    "releases.atom",
    "curl:",
    "could not resolve",
    "failed to connect",
    "timed out",
    "connection reset",
    "connection refused",
    "network is unreachable",
    "baste (rathole-manager",
    "download bootstrap.sh",
)


def looks_like_network_failure(res):
    if not isinstance(res, dict) or res.get("rc", 0) == 0:
        return False
    combined = (str(res.get("err", "")) + "\n" + str(res.get("out", ""))).lower()
    return any(m in combined for m in _NET_FAIL_MARKERS)
