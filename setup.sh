#!/bin/sh
# Cloud Save Sync - automatic setup (Linux / macOS)
# Double-click or run: sh setup.sh  -> opens a terminal, does everything, then launches the GUI.
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Cloud Save Sync - automatic setup"
echo "============================================================"

PY=python3
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found (Linux: sudo apt install python3 python3-tk)"; exit 1; }

# bundled rclone for this platform?
ARCH=$(uname -m)
case "$(uname -s)" in
  Darwin) case "$ARCH" in arm64) RCLONE=vendor/macos-arm64/rclone ;; *) RCLONE=vendor/macos-amd64/rclone ;; esac ;;
  *)      case "$ARCH" in aarch64|arm64) RCLONE=vendor/linux-arm64/rclone ;; *) RCLONE=vendor/linux-amd64/rclone ;; esac ;;
esac
if [ ! -x "$RCLONE" ]; then
  echo "Downloading rclone ($RCLONE)..."
  "$PY" scripts/fetch_rclone.py
fi

echo
echo "Choose your cloud:"
echo "  1) onedrive-local (RECOMMENDED, no OAuth, works with work/school accounts)"
echo "  2) gdrive-local   3) dropbox-local   4) other rclone remote (onedrive, gdrive...)"
printf "Your choice [1]: "
read CHOIX
[ -z "$CHOIX" ] && CHOIX=1
case "$CHOIX" in
  1) REMOTE=onedrive-local ;;
  2) REMOTE=gdrive-local ;;
  3) REMOTE=dropbox-local ;;
  *) REMOTE=onedrive
     echo
     echo "Connect your cloud account to rclone: 'n' (new remote), name it"
     echo "'gdrive' (Google Drive), 'dropbox', 'onedrive'... then sign in."
     "$RCLONE" config ;;
esac

"$PY" -c "from savesync import core; cfg=core.load_config(); cfg['remote']='$REMOTE'; core.save_config(cfg); print('remote:', cfg['remote'], '->', core.config_path())"

echo
echo "Scanning save folders automatically..."
"$PY" savesync.py --cli scan --auto

echo
echo "First sync to the cloud..."
"$PY" savesync.py --cli sync

echo
echo "============================================================"
echo "  Done! Launching the GUI..."
echo "============================================================"
"$PY" savesync.py
