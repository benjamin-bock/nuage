#!/bin/sh
# Cloud Save Sync - installation automatique (Linux / macOS)
# Double-clic ou : sh setup.sh   -> ouvre un terminal, fait tout, puis lance la GUI.
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Cloud Save Sync - installation automatique"
echo "============================================================"

PY=python3
command -v python3 >/dev/null 2>&1 || { echo "ERREUR : python3 introuvable (Linux : sudo apt install python3 python3-tk)"; exit 1; }

# rclone embarque pour cette plateforme ?
ARCH=$(uname -m)
case "$(uname -s)" in
  Darwin) case "$ARCH" in arm64) RCLONE=vendor/macos-arm64/rclone ;; *) RCLONE=vendor/macos-amd64/rclone ;; esac ;;
  *)      case "$ARCH" in aarch64|arm64) RCLONE=vendor/linux-arm64/rclone ;; *) RCLONE=vendor/linux-amd64/rclone ;; esac ;;
esac
if [ ! -x "$RCLONE" ]; then
  echo "Telechargement de rclone ($RCLONE)..."
  "$PY" scripts/fetch_rclone.py
fi

echo
echo "Connexion du compte cloud a rclone : 'n' (new remote), nomme-le"
echo "'gdrive' (Google Drive), 'dropbox', 'onedrive'... puis connecte-toi."
"$RCLONE" config

# cree la config de l'app si absente
"$PY" -c "from savesync import core; import os; p=core.config_path(); os.path.exists(str(p)) or core.save_config(core.load_config()); print('config:', p)"

echo
echo "Scan automatique des dossiers de sauvegardes..."
"$PY" savesync.py --cli scan --auto

echo
echo "Premier sync vers le cloud..."
"$PY" savesync.py --cli sync

echo
echo "============================================================"
echo "  Termine ! Lancement de l'interface graphique..."
echo "============================================================"
"$PY" savesync.py
