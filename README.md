# Cloud Save Sync v3 — app.exe + GUI multi-plateforme (Windows / Linux / macOS)

> **Windows, zéro terminal** : double-clique `dist\CloudSaveSync.exe` (ou le raccourci
> `CloudSaveSync.lnk` sur ton Bureau). Pour la **première configuration** (connexion du
> compte cloud), double-clique `setup.bat` : il ouvre un terminal, fait les commandes
> (rclone config → scan auto → premier sync) puis lance l'app.
> Sur Linux/macOS : `sh setup.sh`.

Application graphique qui **synchronise en bidirectionnel** les sauvegardes de tes jeux
vers le cloud (OneDrive, Google Drive, Dropbox, Mega… via rclone, ou iCloud), pour
continuer ta progression sur un autre appareil.

- **Vrai sync** (moteur `rclone bisync`) : modifications, renommages **et suppressions**
  propagés dans les deux sens. Conflit (modifié des 2 côtés) → le plus récent gagne,
  l'autre est conservé en `*.conflictN` (aucune perte).
- **Détection auto** des dossiers de saves, par OS (voir tableau ci-dessous).
- **Auto-sync** : bouton ▶ dans l'app (sync ~3 s après chaque changement de fichier +
  synchro périodique), ou tâche planifiée / service systemd.
- **Nouveau PC** : détecté automatiquement (dossier vide + cloud plein) → les saves
  du cloud sont téléchargées d'abord, le cloud n'est jamais écrasé.
- Moteur backup legacy (`copy`, jamais de suppression) sélectionnable dans les paramètres.
- 100 % local + ton propre compte cloud. Python stdlib uniquement (Tkinter), rclone embarqué.

## Arborescence

```
cloud-save-sync/
├── dist/CloudSaveSync.exe # ← L'APP WINDOWS (autonome, rclone embarqué) + raccourci Bureau
├── setup.bat              # 1er run Windows : double-clic, fait tout et lance l'app
├── setup.sh               # idem Linux/macOS
├── run.ps1 / run.bat      # lance depuis les sources (GUI ou --cli ...)
├── savesync.py            # point d'entrée (GUI par défaut, --cli pour la CLI)
├── savesync/              # core.py (moteur), cli.py, gui.py (Tkinter)
├── scripts/fetch_rclone.py
├── vendor/                # binaires rclone embarqués (win/linux/mac × amd64/arm64)
├── packaging/             # Install-Task.ps1, service systemd, .desktop
└── README.md
```

## Lancer depuis les sources

Prérequis : Python 3.10+ avec Tkinter.
- Windows : installeur officiel python.org (Tkinter inclus).
- Linux : `sudo apt install python3 python3-tk` (ou équivalent).
- macOS : installeur python.org (Tkinter inclus).

```powershell
# Windows — le plus simple (trouve Python tout seul, même si le stub Microsoft Store bloque "python") :
.\run.ps1                             # lance la GUI
.\run.ps1 --cli init                  # configure le cloud (ex: onedrive)
.\run.ps1 --cli scan --auto           # détecte + ajoute tous les dossiers de saves
.\run.ps1 --cli sync                  # premier sync
# ou directement : python savesync.py / python savesync.py --cli ...
```
```bash
# Linux / macOS
python3 scripts/fetch_rclone.py       # télécharge rclone pour ta plateforme (vendor/)
python3 savesync.py                   # lance la GUI
python3 savesync.py --cli scan --auto
python3 savesync.py --cli sync
```
> Windows : si `python` dit « exécutez sans arguments pour installer » (stub Microsoft Store),
> ouvre un **nouveau** terminal PowerShell (le PATH corrigé est en tête du registre) ou utilise `.\run.ps1`.

Premier lancement : connecte ton cloud à rclone une fois pour toutes :
```bash
vendor/windows-amd64/rclone.exe config        # Windows
vendor/linux-amd64/rclone config              # Linux
vendor/macos-arm64/rclone config              # macOS (arm64)
```
puis choisis `n`, nomme le remote (`onedrive`, `gdrive`, `dropbox`…) et connecte-toi.
Dans l'app, mets ce nom de remote dans ⚙ Paramètres.

## Utilisation de la GUI

| Bouton | Action |
|---|---|
| 🔎 Scanner | détecte les dossiers de saves → coche ceux à surveiller |
| ➕ Ajouter… | ajouter un dossier manuellement |
| ➖ Retirer | retirer un dossier (le cloud est conservé) |
| 🔄 Sync maintenant | sync bidirectionnel immédiat |
| 👁 Statut | dry-run : ce qui changerait |
| ▶ Auto-sync / ⏹ Stop | watch : sync auto à chaque changement de fichier |
| ⚙ Paramètres | provider cloud, dossier racine, moteur, conflits, intervalles |

CLI équivalente : `python savesync.py --cli <commande>` (`list`, `status`, `conflicts`,
`resync [cle]`, `watch`…).

## Sur l'autre appareil

Même appli + même compte cloud, puis `scan --auto` (ou ➕ manuel) et `sync` :
les saves du cloud arrivent automatiquement (détection "nouveau PC").

## Où sont cherchées les sauvegardes

| OS | Racines scannées |
|---|---|
| Windows | `%APPDATA%`, `%LOCALAPPDATA%`, **`%LOCALAPPDATA%\LocalLow`** (jeux Unity : `LocalLow\<Studio>\<Jeu>\user1.dat`, ex. Hollow Knight Silksong — extensions `.dat`/`.bin` acceptées), `Saved Games`, `Documents\Saved Games`, `Documents\My Games`, `Packages\<éditeur>\<jeu>` (jeux Microsoft Store) |

Faux positifs exclus automatiquement (cache rclone, crashreports, launchers, éditeurs,
"unsaved-meetings"…). Pour un jeu dans un dossier exotique, ajoute la racine dans
`extra_roots` de la config (`%APPDATA%\savesync\config.json`) ou via ➕ Ajouter dans la GUI.
| Linux | `~/.config`, `~/.local/share`, `~/.var/app` (Flatpak), Steam/Proton : `compatdata/<appid>/pfx/drive_c/users/<user>/{AppData\Roaming,AppData\Local,AppData\LocalLow,Documents,Saved Games}` |
| macOS | `~/Library/Application Support`, `~/Library/Containers/<bundle>/Data`, Steam macOS (compatdata) |

Heuristique : un dossier est proposé s'il contient des fichiers `.sav/.save/...`
ou si son nom contient "save". Notre propre dossier de config est exclu.

## Automatisation

- **Windows** : `powershell -File packaging\Install-Task.ps1` → sync toutes les 15 min + à l'ouverture de session.
- **Linux** : `packaging/cloud-save-sync.service` (systemd user, voir commentaires du fichier) ou `packaging/CloudSaveSync.desktop` en autostart (démarre la GUI, auto-sync au lancement).
- **macOS** : lance l'app au login (Préférences Système → Général → Éléments de connexion).

## Build d'un exécutable autonome (PyInstaller)

```bash
pip install pyinstaller
# Windows
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/windows-amd64/rclone.exe;vendor/windows-amd64"
# Linux
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/linux-amd64/rclone;vendor/linux-amd64"
# macOS (arm64)
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/macos-arm64/rclone;vendor/macos-arm64"
```
Le binaire embarque rclone (extrait automatiquement au lancement). macOS : penser à
signer/notariser (`codesign --force --deep --sign "Developer ID" dist/CloudSaveSync.app`)
si distribution hors cercle de confiance.

## Notes & dépannage

- Config : `%APPDATA%\savesync\config.json` (Windows), `~/.config/savesync/config.json`
  (Linux), `~/Library/Application Support/savesync/config.json` (macOS).
- Ne lance pas de sync simultanés sur deux machines (bisync pose un lock 2 min côté cloud).
- Token cloud expiré → relance `rclone config` pour reconnecter le remote.
- Changer de compte cloud → `resync` pour repartir proprement.
- Fichiers verrouillés par un jeu en cours : ignorés par rclone, repris au cycle suivant.
- iCloud : choisis `icloud` comme provider (Windows : iCloud for Windows ; macOS : iCloud Drive
  activé) → backend en dossier local, pas besoin de rclone.
