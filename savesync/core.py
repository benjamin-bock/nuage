"""Core of Cloud Save Sync (cross-platform: Windows / Linux / macOS).

Sync engine: rclone bisync (true bidirectional sync, deletions propagated,
conflicts resolved with the loser kept as *.conflictN).
Legacy backup mode: "copy" engine (nothing is ever deleted).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

APP_NAME = "savesync"

SAVE_EXTS = {".sav", ".save", ".savegame", ".sg", ".zsav", ".ess", ".dsv", ".sav2"}
# LocalLow (Unity/Chromium games): saves are often .dat/.bin (e.g. Hollow Knight Silksong)
LOCALLOW_EXTS = SAVE_EXTS | {".dat", ".bin"}
# folders NEVER suggested (known false positives): dir name or path component
BLOCK_PATTERNS = (
    "crashreport", "crashdumps", "launcher", "editor", "unsaved", "rclone",
    "savesync", "telemetry", "cache", "logs", "temp",
)

DEFAULTS = {
    "remote": "onedrive",          # rclone remote (onedrive, gdrive, dropbox...), "onedrive-local", "icloud" or "local:<path>"
    "remote_dir": "SaveSync",      # root folder in the cloud
    "engine": "bisync",            # "bisync" (sync) or "copy" (backup)
    "conflict_resolve": "newer",   # newer / older / larger / smaller
    "compare": "size,modtime",     # rclone compare fields
    "interval_sec": 300,           # periodic sync in watch mode
    "watch_debounce_sec": 3,       # watch debounce delay
    "folders": [],                 # [{key, path, resynced}]
}


# ---------------------------------------------------------------- config ----

def system() -> str:
    return platform.system()  # "Windows" | "Linux" | "Darwin"


def config_dir() -> Path:
    s = system()
    if s == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif s == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    cfg.setdefault("folders", [])
    return cfg


def save_config(cfg: dict) -> None:
    config_path().write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- rclone ----

def _rclone_config_file() -> Path:
    if system() == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "rclone" / "rclone.conf"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rclone" / "rclone.conf"


def find_rclone() -> str | None:
    """Bundled rclone (vendor/) first, then PATH."""
    exe_names = ["rclone.exe"] if system() == "Windows" else ["rclone"]
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile extraction dir
    if meipass:
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parent.parent)  # project root
    for base in bases:
        for name in exe_names:
            candidates = [base / "vendor" / name, base / "bin" / name, base / name]
            vendor = base / "vendor"
            if vendor.is_dir():
                candidates += list(vendor.glob(f"*/{name}"))
            for p in candidates:
                if p.is_file():
                    return str(p)
    return shutil.which("rclone")


class RcloneError(RuntimeError):
    pass


def rclone(args: list[str], timeout: int = 900) -> tuple[int, str]:
    exe = find_rclone()
    if not exe:
        raise RcloneError(
            "rclone not found. Run scripts/fetch_rclone.py (or install rclone in the PATH)."
        )
    # avoid the "Config file not found" NOTICE
    conf = _rclone_config_file()
    try:
        conf.parent.mkdir(parents=True, exist_ok=True)
        if not conf.exists():
            conf.write_text("", encoding="utf-8")
    except OSError:
        pass
    proc = subprocess.run(
        [exe, *args], capture_output=True, text=True, errors="replace", timeout=timeout
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in out.splitlines() if "not found - using defaults" not in ln and ln.strip()]
    return proc.returncode, "\n".join(lines)


# --------------------------------------------------------------- backends ---

# "local folder already synced by the cloud client" backends (OneDrive, Google Drive,
# Dropbox): zero OAuth, ideal for work/school accounts blocked by AADSTS700016.
LOCAL_SYNC_REMOTES = {
    "onedrive-local": ["OneDrive"],   # prefer the personal OneDrive, else the first OneDrive*
    "gdrive-local": ["Google Drive", "GoogleDrive"],
    "dropbox-local": ["Dropbox"],
}


def _local_sync_base(remote: str) -> Path:
    home = Path.home()
    for name in LOCAL_SYNC_REMOTES.get(remote, []):
        p = home / name
        if p.is_dir():
            return p
    if remote == "onedrive-local":
        matches = sorted(home.glob("OneDrive*"), key=lambda p: (len(p.name), p.name))
        if matches:
            return matches[0]
    raise RcloneError(
        f"Local folder of the {remote} client not found under {home}. "
        "Install/sync the cloud client first (OneDrive, Google Drive for desktop, Dropbox)."
    )


def _icloud_drive() -> Path:
    s = system()
    cands = []
    if s == "Windows":
        cands = [Path.home() / "iCloud Drive", Path.home() / "iCloudDrive"]
    elif s == "Darwin":
        cands = [Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"]
    for c in cands:
        if c.is_dir():
            return c
    raise RcloneError(
        "iCloud folder not found. Windows: install 'iCloud for Windows'. "
        "macOS: enable iCloud Drive in System Settings."
    )


def is_local_backend(cfg: dict) -> bool:
    remote = str(cfg["remote"])
    return remote == "icloud" or remote.startswith("local:") or remote in LOCAL_SYNC_REMOTES


def remote_spec(cfg: dict, key: str) -> str:
    """Remote spec for a key: 'onedrive:SaveSync/key' or a local path."""
    remote = str(cfg["remote"])
    if remote == "icloud":
        return str(_icloud_drive() / cfg["remote_dir"] / key)
    if remote in LOCAL_SYNC_REMOTES:
        return str(_local_sync_base(remote) / cfg["remote_dir"] / key)
    if remote.startswith("local:"):
        return str(Path(remote[6:]) / cfg["remote_dir"] / key)
    return f"{remote}:{cfg['remote_dir']}/{key}"


# ------------------------------------------------------------------ sync ----

def _bisync(cfg: dict, local: str, remote: str, resync: bool = False,
            dry_run: bool = False) -> tuple[int, str]:
    args = [
        "bisync", local, remote,
        "--compare", cfg["compare"],
        "--transfers", "4", "--checkers", "8",
        "--max-lock", "2m", "--resilient", "--recover",
        "--stats", "0",
    ]
    if cfg.get("conflict_resolve"):
        args += ["--conflict-resolve", cfg["conflict_resolve"]]
    if resync:
        args += ["--resync"]
    if dry_run:
        args += ["--dry-run"]
    code, out = rclone(args)
    # bisync sometimes refuses to proceed ("Safety abort: all files were changed on one side")
    # -> legitimate for save folders: retry with --force
    if code != 0 and "Safety abort" in out and not dry_run:
        code, out = rclone(args + ["--force"])
    return code, out


def sync_one(cfg: dict, folder: dict, dry_run: bool = False, log=print) -> dict:
    local = folder["path"]
    key = folder["key"]
    remote = remote_spec(cfg, key)
    result = {"key": key, "ok": False, "resynced": False, "output": ""}

    if not Path(local).is_dir():
        result["output"] = f"folder does not exist, skipped: {local}"
        log(f"  [{key}] {result['output']}")
        return result

    if cfg.get("engine", "bisync") == "copy":
        common = ["--update", "--transfers", "4", "--checkers", "8", "--stats", "0"]
        rclone(["copy", remote, local, "--create-empty-src-dirs", *common])
        code, out = rclone(["copy", local, remote, *common])
        result.update(ok=code == 0, output=out)
        log(f"  sync(copy)  [{key}]")
        return result

    # the local backend requires the remote root to exist
    rclone(["mkdir", remote])

    if not folder.get("resynced"):
        # first sync for this key. If new PC (local empty + cloud full),
        # pre-fill from the cloud so the cloud is never overwritten by an empty folder.
        local_empty = not any(p.is_file() for p in Path(local).rglob("*"))
        code_lsf, out_lsf = rclone(["lsf", "--files-only", remote])
        remote_empty = code_lsf != 0 or not out_lsf.strip()
        if local_empty and not remote_empty:
            log(f"  [{key}] new PC detected: pre-filling from the cloud...")
            rclone(["copy", remote, local, "--create-empty-src-dirs", "--stats", "0"])
        code, out = _bisync(cfg, local, remote, resync=not dry_run, dry_run=dry_run)
        if code != 0 and not dry_run:
            result["output"] = out
            log(f"  resync [{key}] failed:\n{out}")
            return result
        folder["resynced"] = True
        result["resynced"] = True
        save_config(cfg)
        log(f"  initial resync  [{key}]  ->  {remote}")
        result.update(ok=True, output=out)
        return result

    code, out = _bisync(cfg, local, remote, dry_run=dry_run)
    if dry_run:
        result.update(ok=True, output=out)
        return result
    if code != 0:
        result["output"] = out
        log(f"  sync [{key}] failed:\n{out}")
        return result
    result.update(ok=True, output=out)
    if ".conflict" in out:
        log(f"  sync  [{key}]  (conflicts -> *.conflictN, see 'conflicts')")
    else:
        log(f"  sync  [{key}]")
    return result


def check_remote(cfg: dict, log=print) -> bool:
    """Check that the rclone remote exists (clear message instead of cryptic errors)."""
    remote = str(cfg.get("remote", ""))
    if is_local_backend(cfg):
        return True
    try:
        code, out = rclone(["listremotes"])
    except RcloneError as e:
        log(f"ERROR: {e}")
        return False
    remotes = {ln.strip().rstrip(":") for ln in out.splitlines() if ln.strip()}
    if remote in remotes:
        return True
    log(f"ERROR: rclone remote '{remote}' does not exist yet in rclone.conf.")
    log("  Connect your cloud account ONCE: run setup.bat (or setup.sh)")
    log(f"  (or: rclone config  -> 'n' -> name it '{remote}')")
    log("  then run sync again.")
    return False


def is_folder_junk(f: dict) -> bool:
    """Folder to drop from watching: missing, or a false positive (blocklist, app/rclone config)."""
    p = Path(f.get("path", ""))
    if not p.is_dir():
        return True
    low = str(p).lower()
    if any(b in low for b in BLOCK_PATTERNS):
        return True
    rp = p.resolve()
    if config_dir().resolve() in rp.parents or _rclone_config_file().parent.resolve() in rp.parents:
        return True
    return False


def clean_config(cfg: dict | None = None, log=print) -> dict:
    """Remove folders that became useless (false positives, deleted paths)."""
    cfg = cfg or load_config()
    folders = [f for f in cfg.get("folders", []) if f.get("path")]
    kept = [f for f in folders if not is_folder_junk(f)]
    removed = len(folders) - len(kept)
    cfg["folders"] = kept
    save_config(cfg)
    for f in folders:
        if f not in kept:
            log(f"  removed: [{f.get('key')}] {f.get('path')}")
    log(f"Cleanup done: {removed} folder(s) removed, {len(kept)} kept.")
    return cfg


def sync_all(cfg: dict | None = None, dry_run: bool = False, log=print) -> list[dict]:
    cfg = cfg or load_config()
    folders = [f for f in cfg.get("folders", []) if f.get("path")]
    if not folders:
        log("No folder watched. Run 'scan --auto' or 'add <path>'.")
        return []
    if not check_remote(cfg, log):
        return []
    results = []
    for f in folders:
        results.append(sync_one(cfg, f, dry_run=dry_run, log=log))
    if not dry_run and any(r["resynced"] for r in results):
        save_config(cfg)
    return results


def list_conflicts(cfg: dict | None = None, log=print) -> dict:
    cfg = cfg or load_config()
    found = {}
    for f in cfg.get("folders", []):
        if not f.get("path"):
            continue
        remote = remote_spec(cfg, f["key"])
        local_c = [
            str(p) for p in Path(f["path"]).rglob("*")
            if p.is_file() and re.search(r"\.conflict\d+$", p.name)
        ]
        code, out = rclone(["lsf", "-R", "--files-only", remote])
        remote_c = []
        if code == 0:
            remote_c = [ln for ln in out.splitlines() if re.search(r"\.conflict\d+$", ln)]
        if local_c or remote_c:
            found[f["key"]] = {"local": local_c, "remote": remote_c}
            log(f"[{f['key']}]")
            for c in local_c:
                log(f"  local: {c}")
            for c in remote_c:
                log(f"  cloud: {c}")
    if not found:
        log("No conflicts.")
    return found


def force_resync(cfg: dict | None = None, key: str | None = None, log=print) -> list[dict]:
    cfg = cfg or load_config()
    for f in cfg.get("folders", []):
        if key is None or f.get("key") == key:
            f["resynced"] = False
    save_config(cfg)
    return sync_all(cfg, log=log)


# -------------------------------------------------------------- detection ---

def _xdg(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, str(default)))


def scan_roots(cfg: dict | None = None) -> list[Path]:
    """Known game-save roots, per platform (+ extra_roots from the config)."""
    home = Path.home()
    s = system()
    roots: list[Path] = []

    def add(p):
        p = Path(p)
        if p.is_dir() and p not in roots:
            roots.append(p)

    if s == "Windows":
        for v in ("APPDATA", "LOCALAPPDATA"):
            if os.environ.get(v):
                add(Path(os.environ[v]))
        # LocalLow is a SIBLING of LOCALAPPDATA: AppData\LocalLow (Unity/Chromium games)
        # LocalLow\<Studio>\<Game>\default\user1.dat (e.g. Hollow Knight Silksong)
        if os.environ.get("LOCALAPPDATA"):
            add(Path(os.environ["LOCALAPPDATA"]).parent / "LocalLow")
        add(home / "Saved Games")
        add(home / "Documents" / "Saved Games")
        add(home / "Documents" / "My Games")
        packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
        if packages.is_dir():
            # Microsoft Store games: Packages\<Publisher>\<Game>\... -> each <Game> becomes a root
            for pub in packages.iterdir():
                if pub.is_dir():
                    for game in pub.iterdir():
                        if game.is_dir():
                            add(game)
    elif s == "Darwin":
        add(home / "Library" / "Application Support")
        containers = home / "Library" / "Containers"
        if containers.is_dir():
            # sandboxed apps: Containers/<bundle>/Data/... -> Data becomes a root
            for bundle in containers.iterdir():
                data = bundle / "Data"
                if data.is_dir():
                    add(data)
        _add_steam(roots, home / "Library" / "Application Support" / "Steam", add)
    else:  # Linux
        add(_xdg("XDG_CONFIG_HOME", home / ".config"))   # some games (Unity...) write here
        add(_xdg("XDG_DATA_HOME", home / ".local" / "share"))
        add(home / ".var" / "app")                        # Flatpak
        _add_steam(roots, home / ".steam" / "steam", add)
        _add_steam(roots, _xdg("XDG_DATA_HOME", home / ".local" / "share") / "Steam", add)
    if cfg:
        for p in cfg.get("extra_roots", []) or []:
            add(Path(p).expanduser())
    return roots


def _add_steam(roots: list[Path], steam_dir: Path, add) -> None:
    """Steam + Proton: compatdata/<appid>/pfx/drive_c/users/<user>/... becomes a root."""
    compat = steam_dir / "steamapps" / "compatdata"
    if not compat.is_dir():
        return
    for appid in compat.iterdir():
        pfx = appid / "pfx" / "drive_c"
        if not pfx.is_dir():
            continue
        users = pfx / "users"
        if users.is_dir():
            for user in users.iterdir():
                if not user.is_dir():
                    continue
                add(user / "AppData" / "Roaming")
                add(user / "AppData" / "Local")
                add(user / "AppData" / "LocalLow")
                add(user / "Documents")
                add(user / "Saved Games")
        else:
            add(pfx)


def looks_like_save_dir(d: Path, exts: set[str] = SAVE_EXTS,
                        max_files: int = 150, max_depth: int = 2) -> bool:
    """True if the folder contains save files, looking recursively up to max_depth
    levels (e.g. Unity game whose saves are in <game>/default/user1.dat).
    max_depth=0 -> direct files only. Blocked subdirs (cache, logs...) are skipped."""
    try:
        if "save" in d.name.lower():
            return True
        base = str(d)
        seen = 0
        for cur, dirs, files in os.walk(d):
            depth = cur[len(base):].count(os.sep)
            # prune: max depth + blocked dirs
            dirs[:] = [] if depth >= max_depth else [
                dn for dn in dirs
                if not any(b in dn.lower() for b in BLOCK_PATTERNS)
            ]
            for fn in files:
                seen += 1
                if Path(fn).suffix.lower() in exts or "save" in fn.lower():
                    return True
                if seen >= max_files:
                    return False
    except OSError:
        return False
    return False


def _is_blocked(root: Path, p: Path) -> bool:
    """Exclude known false positives (rclone cache, crashreports, launchers...)."""
    try:
        rel = os.path.relpath(str(p), str(root))
    except ValueError:
        rel = str(p)
    parts = [c.lower() for c in rel.split(os.sep)]
    return any(b in part for part in parts for b in BLOCK_PATTERNS)


def scan(cfg: dict | None = None) -> list[tuple[Path, Path]]:
    """Returns [(root, detected_folder), ...] (depth 2 under each root)."""
    cfg = cfg if cfg is not None else load_config()
    found = []
    for root in scan_roots(cfg):
        exts = LOCALLOW_EXTS if "locallow" in str(root).lower() else SAVE_EXTS
        try:
            children = [d for d in root.iterdir() if d.is_dir()]
        except OSError:
            continue
        for c in children:
            if _is_blocked(root, c):
                continue
            # 1) the child itself if its direct files/name say "save" (game folder)
            if looks_like_save_dir(c, exts, max_depth=0):
                found.append((root, c))
                continue
            # 2) else grandchildren (per-game granularity: Studio\Game),
            #    looking for saves up to 2 levels inside them
            matched_gc = []
            try:
                for g in c.iterdir():
                    if g.is_dir() and not _is_blocked(root, g) and looks_like_save_dir(g, exts, max_depth=2):
                        matched_gc.append(g)
            except OSError:
                pass
            if matched_gc:
                found.extend((root, g) for g in matched_gc)
            # 3) else the child recursively (saves nested directly under the child)
            elif looks_like_save_dir(c, exts, max_depth=2):
                found.append((root, c))
    # dedupe + exclude our own config dir (its name contains "save")
    conf = config_dir().resolve()
    seen = set()
    out = []
    for root, p in found:
        rp = p.resolve()
        if rp == conf or conf in rp.parents:
            continue
        if str(rp) not in seen:
            seen.add(str(rp))
            out.append((root, p))
    return out


def key_for(path: str | Path, root: str | Path | None = None) -> str:
    path = Path(path)
    if root is None:
        root = next(
            (r for r in scan_roots() if str(path).lower().startswith(str(r).lower())),
            path.parent,
        )
    rel = os.path.relpath(str(path), str(root))
    return re.sub(r'[\\/:*?"<>|]', "_", rel)


def add_folder(path: str, cfg: dict | None = None, log=print) -> dict:
    cfg = cfg or load_config()
    full = str(Path(path).expanduser().resolve())
    if not Path(full).is_dir():
        raise FileNotFoundError(f"Path does not exist: {full}")
    if any(f.get("path") == full for f in cfg.get("folders", [])):
        log(f"Already watched: {full}")
        return cfg
    key = key_for(full)
    cfg.setdefault("folders", []).append({"key": key, "path": full, "resynced": False})
    save_config(cfg)
    log(f"Added: [{key}]  {full}")
    return cfg


def remove_folder(key: str, cfg: dict | None = None, log=print) -> dict:
    cfg = cfg or load_config()
    cfg["folders"] = [f for f in cfg.get("folders", []) if f.get("key") != key]
    save_config(cfg)
    log(f"Removed: {key}")
    return cfg


# ----------------------------------------------------------------- watch ----

class Watcher(threading.Thread):
    """Watches folders (mtime polling) and syncs:
    - ~debounce seconds after the last change of a folder -> sync that folder
    - every interval_sec seconds -> full sync (safety net)
    """

    def __init__(self, log=print, on_sync=None):
        super().__init__(daemon=True)
        self.log = log
        self.on_sync = on_sync or (lambda *a, **k: None)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    @staticmethod
    def _snapshot(folder: str) -> dict:
        snap = {}
        base = Path(folder)
        if not base.is_dir():
            return snap
        for p in base.rglob("*"):
            if p.is_file():
                try:
                    snap[str(p.relative_to(base))] = p.stat().st_mtime
                except OSError:
                    pass
        return snap

    def run(self):
        self.log("Watch active (Ctrl+C / Stop to quit).")
        snaps: dict[str, dict] = {}
        pending: dict[str, float] = {}
        last_full = 0.0
        while not self._stop_event.is_set():
            try:
                cfg = load_config()
            except Exception as e:
                self.log(f"config unreadable: {e}")
                time.sleep(5)
                continue
            debounce = float(cfg.get("watch_debounce_sec", 3))
            interval = float(cfg.get("interval_sec", 300))
            now = time.time()
            folders = [f for f in cfg.get("folders", []) if f.get("path")]
            for f in folders:
                key, path = f["key"], f["path"]
                snap = self._snapshot(path)
                if key not in snaps:
                    snaps[key] = snap
                    continue
                if snap != snaps[key]:
                    snaps[key] = snap
                    pending[key] = now
                if key in pending and now - pending[key] >= debounce:
                    del pending[key]
                    self.log(f"--- change detected [{key}] {time.strftime('%H:%M:%S')} ---")
                    try:
                        self.on_sync(sync_one(cfg, f, log=self.log))
                    except Exception as e:
                        self.log(f"sync error [{key}]: {e}")
            if now - last_full >= interval:
                self.log(f"--- periodic sync {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                try:
                    for r in sync_all(cfg, log=self.log):
                        self.on_sync(r)
                except Exception as e:
                    self.log(f"periodic sync error: {e}")
                last_full = now
            self._stop_event.wait(1.0)
        self.log("Watch stopped.")
