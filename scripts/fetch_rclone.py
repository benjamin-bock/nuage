#!/usr/bin/env python3
"""Telecharge le binaire rclone adapté à la plateforme dans vendor/.

Usage : python scripts/fetch_rclone.py [--all]
  --all : télécharge pour toutes les plateformes cibles (windows/linux/macos amd64+arm64),
          utile avant un build multi-plateforme. Sinon, seulement la plateforme courante.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://downloads.rclone.org"
ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"

TARGETS = {
    "windows-amd64": ("rclone-current-windows-amd64.zip", "rclone.exe"),
    "linux-amd64": ("rclone-current-linux-amd64.zip", "rclone"),
    "linux-arm64": ("rclone-current-linux-arm64.zip", "rclone"),
    "macos-amd64": ("rclone-current-osx-amd64.zip", "rclone"),
    "macos-arm64": ("rclone-current-osx-arm64.zip", "rclone"),
}


def current_target() -> str:
    s = platform.system()
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "amd64"
    if s == "Windows":
        return "windows-amd64"
    if s == "Darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def fetch(target: str) -> Path | None:
    zip_name, bin_name = TARGETS[target]
    dest_dir = VENDOR / target
    dest = dest_dir / bin_name
    if dest.is_file():
        print(f"OK (déjà présent) : {dest}")
        return dest
    url = f"{BASE}/{zip_name}"
    print(f"Téléchargement {url} ...")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / zip_name
        req = urllib.request.Request(url, headers={"User-Agent": "cloud-save-sync/3.0 (+https://rclone.org)"})
        with urllib.request.urlopen(req) as resp, open(zpath, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        with zipfile.ZipFile(zpath) as z:
            member = next(
                n for n in z.namelist()
                if n.endswith("/" + bin_name) or n == bin_name
            )
            z.extract(member, td)
        src = Path(td) / member
        shutil.copy2(src, dest)
    if bin_name != "rclone.exe":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installé : {dest}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="toutes les plateformes cibles")
    args = ap.parse_args()
    targets = list(TARGETS) if args.all else [current_target()]
    ok = True
    for t in targets:
        try:
            fetch(t)
        except Exception as e:
            print(f"ECHEC {t}: {e}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
