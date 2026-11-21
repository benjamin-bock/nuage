# Cloud Save Sync

[![build](https://github.com/benjamin-bock/cloud-save-sync/actions/workflows/build.yml/badge.svg)](https://github.com/benjamin-bock/cloud-save-sync/actions/workflows/build.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**Bidirectional sync of your PC game saves to the cloud** (OneDrive, Google Drive, Dropbox, iCloud…),
so you can continue your progress on another device. Cross-platform desktop app for **Windows, Linux and macOS**.

No account needed on our side: everything goes to *your own* cloud account. The sync engine is
[`rclone bisync`](https://rclone.org/bisync/) (true two-way sync), bundled with the app.

## Features

- **True sync, not just backup** (rclone `bisync`): changes, renames **and deletions** propagate both ways (PC ↔ cloud).
  Conflicts (file changed on both sides) → the newest wins, the loser is kept as `*.conflictN`. No data loss.
- **Automatic save-folder detection** per OS (see [Where saves are looked for](#where-saves-are-looked-for)).
- **Auto-sync**: syncs ~3 s after every file change (file watcher) + periodic safety sync.
- **New PC detection**: if the local folder is empty and the cloud has saves, they are downloaded first — the cloud is never wiped by an empty folder.
- **Cloud providers**: any rclone remote (OneDrive, Google Drive, Dropbox, Mega…), `icloud`,
  or a **local cloud folder** (`onedrive-local`, `gdrive-local`, `dropbox-local`) — no OAuth at all,
  perfect for work/school accounts (see [AADSTS700016 error](#aadsts700016-error-on-onedrive-oauth)).
- **GUI** (Tkinter, zero extra deps) + full **CLI** for headless/server use.
- Packaged as a single standalone `.exe` / binary per OS (see [Releases](https://github.com/benjamin-bock/cloud-save-sync/releases)).

## Install

### Windows (no terminal needed)

1. Download the latest `CloudSaveSync-windows-amd64.exe` from [Releases](https://github.com/benjamin-bock/cloud-save-sync/releases)
   (or build it yourself, see [Build](#build)).
2. Double-click **`setup.bat`** in the source folder once: it connects your cloud (choice `1) onedrive-local`
   recommended — no OAuth), auto-scans your save folders, runs the first sync, then opens the app.
3. In the app: check the folders, click **🔄 Sync now**, then **▶ Auto-sync**.

### From source (Windows / Linux / macOS)

Requirements: Python 3.10+ with Tkinter.
- Windows / macOS: official installer from [python.org](https://www.python.org/downloads/) (Tkinter included).
- Linux: `sudo apt install python3 python3-tk` (or your distro's equivalent).

```bash
git clone https://github.com/benjamin-bock/cloud-save-sync.git
cd cloud-save-sync
python scripts/fetch_rclone.py      # download the rclone binary for your platform (vendor/)
python savesync.py                  # launch the GUI
# or CLI:
python savesync.py --cli init       # pick your provider (e.g. onedrive-local)
python savesync.py --cli scan --auto
python savesync.py --cli sync
```

Linux/macOS one-liner setup: `sh setup.sh`.

> Windows: if `python` says "run without arguments to install" (Microsoft Store stub),
> open a **new** terminal (the fixed PATH is at the top of the registry) or use `.\run.ps1`.

## Usage

### GUI

| Button | Action |
|---|---|
| 🔎 Scan | detect save folders → tick the ones to watch |
| ➕ Add… | add a folder manually |
| ➖ Remove | stop watching a folder (cloud copy is kept) |
| 🔄 Sync now | bidirectional sync immediately |
| 👁 Status | dry-run: what would change |
| 🧹 Clean | drop false positives / deleted paths from the watch list |
| ▶ Auto-sync / ⏹ Stop | sync on every file change + periodic sync |
| ⚙ Settings | cloud provider, root folder, engine, conflict policy, intervals |

### CLI

```bash
python savesync.py --cli init                 # interactive configuration
python savesync.py --cli scan [--auto]        # detect (and optionally add) save folders
python savesync.py --cli add "<path>"         # watch a folder manually
python savesync.py --cli remove "<key>"       # stop watching
python savesync.py --cli list                 # list watched folders
python savesync.py --cli sync                 # sync now
python savesync.py --cli status               # dry-run
python savesync.py --cli conflicts            # list *.conflictN
python savesync.py --cli resync ["<key>"]     # force an initial resync
python savesync.py --cli clean                # remove false positives
python savesync.py --cli watch                # continuous auto-sync
```

### On the other device

Same app + same cloud account, then `scan --auto` (or ➕ Add) and `sync`:
saves arrive automatically (new-PC detection). On Windows you can also install the
scheduled task (below) on both machines.

## Where saves are looked for

| OS | Scanned roots |
|---|---|
| Windows | `%APPDATA%`, `%LOCALAPPDATA%`, **`%LOCALAPPDATA%\..\LocalLow`** (Unity games: `LocalLow\<Studio>\<Game>\user1.dat`, e.g. Hollow Knight Silksong — `.dat`/`.bin` accepted), `Saved Games`, `Documents\Saved Games`, `Documents\My Games`, `Packages\<Publisher>\<Game>` (Microsoft Store games) |
| Linux | `~/.config`, `~/.local/share`, `~/.var/app` (Flatpak), Steam/Proton: `compatdata/<appid>/pfx/drive_c/users/<user>/{AppData\Roaming,AppData\Local,AppData\LocalLow,Documents,Saved Games}` |
| macOS | `~/Library/Application Support`, `~/Library/Containers/<bundle>/Data`, Steam macOS (compatdata) |

Heuristic: a folder is suggested if it contains `.sav`/`.save`/… files or its name contains "save".
Known false positives (rclone cache, crash reports, launchers, editors, "unsaved-meetings"…) are excluded
automatically. For a game in an exotic location, add the folder manually (➕ Add) or list its parent in
`"extra_roots"` in the config file.

## Configuration

Config file (JSON):

| Path | File |
|---|---|
| Windows | `%APPDATA%\savesync\config.json` |
| Linux | `~/.config/savesync/config.json` |
| macOS | `~/Library/Application Support/savesync/config.json` |

```json
{
  "remote": "onedrive-local",
  "remote_dir": "SaveSync",
  "engine": "bisync",
  "conflict_resolve": "newer",
  "compare": "size,modtime",
  "interval_sec": 300,
  "watch_debounce_sec": 3,
  "folders": [{"key": "CPY_SAVES", "path": "C:\\Users\\you\\AppData\\Roaming\\CPY_SAVES", "resynced": true}]
}
```

| Key | Meaning |
|---|---|
| `remote` | rclone remote (`onedrive`, `gdrive`, `dropbox`…), `onedrive-local` / `gdrive-local` / `dropbox-local` (local folder of the official cloud client, **no OAuth**), `icloud`, or `local:<path>` |
| `remote_dir` | root folder in the cloud (saves go to `<remote>:<remote_dir>/<key>`) |
| `engine` | `bisync` (true sync) or `copy` (backup, never deletes) |
| `conflict_resolve` | `newer` / `older` / `larger` / `smaller` |
| `extra_roots` | extra folders to scan for saves |

## Automation

- **Windows**: `powershell -File packaging\Install-Task.ps1` → scheduled task syncing every 15 min + at logon.
- **Linux**: `packaging/cloud-save-sync.service` (systemd user unit — see the comments in the file) or
  `packaging/CloudSaveSync.desktop` for autostart (launches the GUI with auto-sync).
- **macOS**: add the app to Login Items (System Settings → General → Login Items).

## Build (standalone binary)

```bash
pip install -r requirements-build.txt   # pyinstaller
python scripts/fetch_rclone.py --all     # all platforms, or just the current one

# Windows
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/windows-amd64/rclone.exe;vendor/windows-amd64"
# Linux
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/linux-amd64/rclone;vendor/linux-amd64"
# macOS (arm64)
pyinstaller --onefile --windowed --name CloudSaveSync savesync.py --add-data "vendor/macos-arm64/rclone;vendor/macos-arm64"
```

The binary embeds rclone (extracted at launch). GitHub Actions builds all three automatically on every
push/tag: see [.github/workflows/build.yml](.github/workflows/build.yml).

## Troubleshooting

- **`AADSTS700016` error during `rclone config` for OneDrive** (work/school account, e.g. university):
  the tenant blocks rclone's default app. **Recommended fix: use `onedrive-local`** as the provider —
  the app syncs into the already-locally-synced OneDrive folder (`%USERPROFILE%\OneDrive\SaveSync\...`)
  and the official OneDrive client does the upload. No OAuth. Same idea with `gdrive-local` / `dropbox-local`.
  Alternatives: use Google Drive/Dropbox via rclone (no Azure involved), or register your own Azure AD app
  and set its `client_id`/`client_secret` in `rclone config`.
- `rclone remote 'onedrive' does not exist` → run `rclone config` once (or `setup.bat`/`setup.sh`).
- Expired cloud token → `rclone config` again to reconnect the remote.
- Changed cloud account → `resync` to start clean.
- Don't run syncs on two machines at the same time (bisync holds a 2-min lock on the cloud).
- Files locked by a running game are skipped by rclone and picked up on the next cycle.
- A game is not detected → add its folder manually (➕ Add / `add <path>`).

## Project layout

```
cloud-save-sync/
├── savesync.py              # entry point (GUI by default, --cli for the CLI)
├── savesync/
│   ├── core.py              # engine: config, detection, bisync, watcher
│   ├── cli.py               # CLI commands
│   └── gui.py               # Tkinter GUI
├── scripts/fetch_rclone.py  # downloads rclone per platform into vendor/
├── vendor/                  # bundled rclone binaries (win/linux/mac × amd64/arm64)
├── packaging/               # Install-Task.ps1, systemd unit, .desktop
├── .github/workflows/       # CI build
├── setup.bat / setup.sh     # one-click first-time setup
└── run.ps1 / run.bat        # launchers from source
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome!

## License

[MIT](LICENSE) — do whatever you want, just keep the copyright notice.
