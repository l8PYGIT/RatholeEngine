#!/usr/bin/env python3
import os
import zipfile
import stat

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ZIP = os.path.join(REPO_ROOT, "rathole-manager.zip")

def main():
    print(f"Building {OUT_ZIP}...")
    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)

    items = ["rathole-manager", "docs", "LICENSE", "NOTICE"]
    
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            full_path = os.path.join(REPO_ROOT, item)
            if not os.path.exists(full_path):
                continue
            if os.path.isfile(full_path):
                zinfo = zipfile.ZipInfo(item)
                zinfo.external_attr = 0o644 << 16
                with open(full_path, "rb") as f:
                    zf.writestr(zinfo, f.read())
            elif os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    for d in dirs:
                        dir_path = os.path.join(root, d)
                        rel_dir = os.path.relpath(dir_path, REPO_ROOT).replace("\\", "/") + "/"
                        zinfo = zipfile.ZipInfo(rel_dir)
                        zinfo.external_attr = 0o755 << 16
                        zf.writestr(zinfo, b"")
                    for f in files:
                        file_path = os.path.join(root, f)
                        rel_file = os.path.relpath(file_path, REPO_ROOT).replace("\\", "/")
                        
                        # Determine permission (executable if .sh or ratholectl/ratholenode/ratholeagent.py)
                        is_exec = (f.endswith(".sh") or f in ("ratholectl", "ratholenode", "ratholeagent.py") or "bin" in rel_file)
                        perm = 0o755 if is_exec else 0o644
                        
                        zinfo = zipfile.ZipInfo(rel_file)
                        zinfo.external_attr = perm << 16
                        with open(file_path, "rb") as fp:
                            zf.writestr(zinfo, fp.read())

    size_mb = os.path.getsize(OUT_ZIP) / (1024 * 1024)
    print(f"Done! {OUT_ZIP} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    main()
