"""Dead-Man's-Switch watchdog process restoring snapshots if connectivity breaks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from .sysstate import RealLinuxDriver, restore_snapshot


class WatchdogController:
    """Spawns and manages an independent watchdog subprocess via heartbeat mtime."""

    def __init__(self, state_dir: str, session_id: str = "tuner"):
        self.state_dir = state_dir
        self.session_id = session_id
        self.hb_path = os.path.join(state_dir, f"wd_{session_id}.hb")
        self.disarm_path = os.path.join(state_dir, f"wd_{session_id}.disarm")
        self._proc: subprocess.Popen | None = None

    def arm(
        self,
        snapshot_path: str,
        ttl_s: float = 45.0,
        mock_restore_marker: str | None = None,
    ) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        for p in (self.disarm_path,):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        with open(self.hb_path, "w", encoding="utf-8") as fh:
            fh.write(f"{time.time()}\n")

        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ)
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = pkg_root if not existing_pp else f"{pkg_root}{os.pathsep}{existing_pp}"

        cmd = [
            sys.executable,
            "-m",
            "tuner.watchdog",
            "--snapshot",
            snapshot_path,
            "--heartbeat",
            self.hb_path,
            "--disarm",
            self.disarm_path,
            "--ttl",
            str(float(ttl_s)),
            "--session",
            self.session_id,
        ]
        if mock_restore_marker:
            cmd += ["--mock-restore-marker", mock_restore_marker]

        self._proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def heartbeat(self) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        with open(self.hb_path, "w", encoding="utf-8") as fh:
            fh.write(f"{time.time()}\n")

    def disarm(self) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        with open(self.disarm_path, "w", encoding="utf-8") as fh:
            fh.write("disarmed\n")
        if self._proc is not None:
            try:
                self._proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None


def _run_loop(args) -> int:
    poll = min(0.2, max(0.05, args.ttl / 6.0))
    while True:
        if os.path.exists(args.disarm):
            return 0
        try:
            last_hb = os.path.getmtime(args.heartbeat)
        except OSError:
            last_hb = 0.0
        if time.time() - last_hb > args.ttl:
            if args.mock_restore_marker:
                parent = os.path.dirname(args.mock_restore_marker)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(args.mock_restore_marker, "w", encoding="utf-8") as fh:
                    fh.write("restored\n")
                return 0
            try:
                with open(args.snapshot, "r", encoding="utf-8") as fh:
                    snap = json.load(fh)
                restore_snapshot(RealLinuxDriver(), snap, session_id=args.session)
            except Exception:
                return 1
            return 0
        time.sleep(poll)


def main() -> int:
    ap = argparse.ArgumentParser(description="rathole-tuner watchdog")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--heartbeat", required=True)
    ap.add_argument("--disarm", required=True)
    ap.add_argument("--ttl", type=float, default=45.0)
    ap.add_argument("--session", default="tuner")
    ap.add_argument("--mock-restore-marker", default="")
    args = ap.parse_args()
    return _run_loop(args)


if __name__ == "__main__":
    sys.exit(main())
