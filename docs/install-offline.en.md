# Offline / Manual File Install

Use this guide when the target server has limited, firewalled, or no direct access to GitHub.
Download (or build) the release archive once on your computer or jump host, upload it to the server, and run `bootstrap.sh --local` completely offline for binary installation and updates.

!!! info "Always grab the Release `rathole-manager.zip`, not GitHub's `Source code (zip)`"
    The `rathole-manager.zip` asset from [**GitHub Releases**](https://github.com/l8PYGIT/RatholeEngine/releases/latest) bundles the patched `rathole` core binaries (`x86_64` and `aarch64` with `SHA256SUMS`) and the `backhaul` uTLS binaries (`linux-amd64` and `linux-arm64`), so the installers never touch GitHub during setup.

    GitHub's auto-generated `Source code (zip)` does not include compiled core binaries and will fall back to downloading `rathole` from the network.

---

## Step 1 — Obtain the bundle files

You only need two files: **`rathole-manager.zip`** (or `.tar.gz`) and **`bootstrap.sh`**.

=== "Download from GitHub Releases (Recommended)"

    Download both assets from the [latest RatholeEngine Release](https://github.com/l8PYGIT/RatholeEngine/releases/latest) (or a pinned tag like `v2.1.0`):

    - `rathole-manager.zip` *(manager scripts + Hub UI + `rathole` & `backhaul` cores + `SHA256SUMS`)*
    - `bootstrap.sh` *(local & offline bootstrapper)*

    Or fetch them on a machine with internet access:

    ```bash
    curl -fLO https://github.com/l8PYGIT/RatholeEngine/releases/latest/download/rathole-manager.zip
    curl -fLO https://github.com/l8PYGIT/RatholeEngine/releases/latest/download/bootstrap.sh
    ```

=== "Build locally from source (`package.sh`)"

    If you cloned or modified the repository, run on Linux / macOS / WSL:

    ```bash
    bash package.sh
    # Output: rathole-manager.zip (or rathole-manager.tar.gz if zip is unavailable)
    ```

    Copy **`rathole-manager.zip`** and **`bootstrap.sh`** from the repository root.

    !!! warning "Windows packaging note"
        Do not build the archive with Windows PowerShell `Compress-Archive` (it writes backslash path separators). Use the official Release asset or `bash package.sh` (LF endings and forward slashes). As a safety net, `bootstrap.sh` automatically normalizes backslashes and CRLF line endings during extraction.

---

## Step 2 — Upload files to the server

Copy both files into `/root/` on the Iran edge server or foreign node:

=== "Linux / macOS (`scp`)"

    ```bash
    scp rathole-manager.zip bootstrap.sh root@<SERVER_IP>:/root/
    ```

    With a custom SSH port (e.g. `2222`):

    ```bash
    scp -P 2222 rathole-manager.zip bootstrap.sh root@<SERVER_IP>:/root/
    ```

=== "Windows (PowerShell / WinSCP)"

    In Windows PowerShell:

    ```powershell
    scp .\rathole-manager.zip .\bootstrap.sh root@<SERVER_IP>:/root/
    ```

    Or upload `rathole-manager.zip` and `bootstrap.sh` to `/root/` via **WinSCP**, **Termius**, or **FileZilla** over SFTP.

Quick sanity check on the server:

```bash
cd /root && ls -lh rathole-manager.zip bootstrap.sh
```

---

## Step 3 — Run the offline installer

Log in as `root` (or use `sudo`) and choose the mode matching your server.
`bootstrap.sh` auto-detects `rathole-manager.zip` / `.tar.gz` in the current directory, and passing **`--local`** explicitly skips any download or prompt.

=== "Interactive (Easiest)"

    ```bash
    cd /root
    sudo bash bootstrap.sh --local ./rathole-manager.zip
    ```

    Select your mode from the menu:
    - `1` ← **Iran panel** (prompts for domain & certificate paths)
    - `2` ← **Foreign node** (prompts for `server`, `name`, `token`, `inbound-port`)
    - `3` ← **Update** existing installation with automatic snapshot & rollback
    - `4` ← **Stage only** into `/opt/rathole-manager` without running installers

=== "Iran Panel (Non-interactive)"

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --panel \
      --domain    panel.example.ir \
      --fullchain /root/cert/panel.example.ir/fullchain.pem \
      --key       /root/cert/panel.example.ir/privkey.pem
    ```

    > Base OS packages (`nginx`, `jq`, `openssl`, `python3`, etc.) are installed via your system package manager (`apt`), while all GitHub core binaries come strictly from the local bundle.

=== "Foreign Node (Non-interactive)"

    First run `sudo ratholectl add trk01 2087` on the Iran panel to generate the node token, then on the foreign node (all node flags must go after `--`):

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --node -- \
      --server panel.example.ir:443 \
      --name trk01 \
      --token <TOKEN> \
      --inbound-port 2087
    ```

    To manage the node without SSH later, run `sudo install-agent.sh --role node` after installation.

=== "Offline Update (Snapshot + Auto-Rollback)"

    Safely upgrade an already installed panel, node, or hub (roles are auto-detected):

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --update
    ```

    `update.sh` takes a full snapshot in `/var/backups/rathole-manager/`, installs the new files, runs per-role health checks, and automatically rolls back on failure.

=== "Stage Only (`--no-run`)"

    Extract, normalize LF endings, set executable permissions in `/opt/rathole-manager`, and stop without running any installer:

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --no-run
    ```

    Then run installers manually whenever ready:

    ```bash
    sudo bash /opt/rathole-manager/install-panel.sh --domain panel.example.ir ...
    sudo bash /opt/rathole-manager/install-node.sh --server ...
    ```

=== "Direct Install without `bootstrap.sh`"

    If you only uploaded `rathole-manager.zip`:

    ```bash
    unzip -o /root/rathole-manager.zip -d /tmp/rh
    sudo mkdir -p /opt/rathole-manager
    sudo cp -rf /tmp/rh/rathole-manager/. /opt/rathole-manager/
    find /opt/rathole-manager -type f \( -name '*.sh' -o -name '*.py' -o -name 'ratholectl' -o -name 'ratholenode' \) -exec sed -i 's/\r$//' {} +
    sudo chmod +x /opt/rathole-manager/*.sh /opt/rathole-manager/ratholectl /opt/rathole-manager/ratholenode

    # Run the desired installer:
    sudo bash /opt/rathole-manager/install-panel.sh
    # Or on a foreign node:
    # sudo bash /opt/rathole-manager/install-node.sh --server panel.example.ir:443 --name trk01 --token <TOKEN> --inbound-port 2087
    # Or to upgrade an existing install:
    # sudo bash /opt/rathole-manager/update.sh
    ```

---

## Step 4 — Upload TLS Certificates or Restore Backups (Optional)

=== "Copy TLS certificates manually"

    ```bash
    # Local machine:
    scp fullchain.pem privkey.pem root@<IRAN_IP>:/tmp/

    # Iran server:
    sudo mkdir -p /root/cert/panel.example.ir
    sudo install -m 644 /tmp/fullchain.pem /root/cert/panel.example.ir/fullchain.pem
    sudo install -m 600 /tmp/privkey.pem   /root/cert/panel.example.ir/privkey.pem
    rm -f /tmp/fullchain.pem /tmp/privkey.pem
    ```

=== "Restore from a backup archive (`--restore`)"

    If migrating from an existing server backup created by `ratholectl backup` or `ratholenode backup`:

    ```bash
    # Iran panel restore:
    sudo ratholectl init --restore /root/rathole-panel-backup-YYYYMMDD-HHMMSS.tar.gz

    # Foreign node restore:
    sudo bash /opt/rathole-manager/install-node.sh --restore /root/rathole-node-backup-YYYYMMDD-HHMMSS.tar.gz
    ```

---

## Step 5 — Verify & Troubleshoot

```bash
# On the Iran panel:
sudo ratholectl status
sudo ratholectl doctor

# On a foreign node:
sudo ratholenode status
sudo ratholenode logs 50
```

| Symptom | Likely Cause | Fix |
|---|---|---|
| `unzip: command not found` on offline host | Minimal OS image lacks `unzip` | Use `rathole-manager.tar.gz` (`tar` is preinstalled) or install `unzip` via `apt` |
| Installer falls back to downloading `rathole` from GitHub | Uploaded GitHub `Source code (zip)` instead of Release `rathole-manager.zip` | Download `rathole-manager.zip` from [**Releases**](https://github.com/l8PYGIT/RatholeEngine/releases/latest) containing `core/SHA256SUMS` |
| Checksum error or corrupt archive | Partial upload or Windows `Compress-Archive` zip | Re-upload cleanly or run `bash package.sh`; check with `unzip -t rathole-manager.zip` |
| `\r: command not found` when running directly | Extracted manually without LF normalization | Run via `bootstrap.sh --local` or run the `sed -i 's/\r$//'` step above |

---

**Related pages:** [Quick Start (Online)](quickstart.en.md) · [Step-by-step Manual Install](install-manual.md) · [Troubleshooting & Rollback](wiki/Troubleshooting.md) · [نسخهٔ فارسی](install-offline.md)
