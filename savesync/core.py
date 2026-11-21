"""Coeur de Cloud Save Sync (multi-plateforme : Windows / Linux / macOS).

Moteur de sync : rclone bisync (vrai sync bidirectionnel, suppressions propagees,
conflits resolus avec conservation du perdant en *.conflictN).
Mode backup legacy : moteur "copy" (rien n'est jamais supprime).
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
# LocalLow (jeux Unity/Chromium) : les saves sont souvent en .dat/.bin (ex: Hollow Knight Silksong)
LOCALLOW_EXTS = SAVE_EXTS | {".dat", ".bin"}
# dossiers a NE JAMAIS proposer (faux positifs connus) : nom ou composant de chemin
BLOCK_PATTERNS = (
    "crashreport", "crashdumps", "launcher", "editor", "unsaved", "rclone",
    "savesync", "telemetry", "cache", "logs", "temp",
)

DEFAULTS = {
    "remote": "onedrive",          # remote rclone (onedrive, gdrive, dropbox...), "icloud" ou "local:<chemin>"
    "remote_dir": "SaveSync",      # dossier racine dans le cloud
    "engine": "bisync",            # "bisync" (sync) ou "copy" (backup)
    "conflict_resolve": "newer",   # newer / older / larger / smaller
    "compare": "size,modtime",     # champs de comparaison rclone
    "interval_sec": 300,           # synchro periodique en mode watch
    "watch_debounce_sec": 3,       # delai anti-rebond du watch
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
    """rclone embarque (vendor/) puis PATH."""
    exe_names = ["rclone.exe"] if system() == "Windows" else ["rclone"]
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)  # dossier d'extraction PyInstaller (onefile)
    if meipass:
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parent.parent)  # racine du projet
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
            "rclone introuvable. Lance scripts/fetch_rclone.py (ou installe rclone dans le PATH)."
        )
    # evite le NOTICE "Config file not found"
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
        "Dossier iCloud introuvable. Windows : installe 'iCloud for Windows'. "
        "macOS : iCloud Drive doit etre active dans les reglages iCloud."
    )


# Backends "dossier local déjà synchronisé par le client cloud" (OneDrive, Google Drive,
# Dropbox) : zero OAuth, ideal pour les comptes pro/ecole bloques par AADSTS700016.
LOCAL_SYNC_REMOTES = {
    "onedrive-local": ["OneDrive"],   # prefere le OneDrive perso, sinon le 1er OneDrive*
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
        f"Dossier local du client {remote} introuvable sous {home}. "
        "Installe/synchronise le client cloud (OneDrive, Google Drive for desktop, Dropbox)."
    )


def is_local_backend(cfg: dict) -> bool:
    remote = str(cfg["remote"])
    return remote == "icloud" or remote.startswith("local:") or remote in LOCAL_SYNC_REMOTES


def remote_spec(cfg: dict, key: str) -> str:
    """Spec rclone du dossier distant pour une cle : 'onedrive:SaveSync/cle' ou chemin local."""
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
    # bisync refuse parfois d'avancer ("Safety abort: all files were changed on one side")
    # -> legitime pour des dossiers de saves : on retente avec --force
    if code != 0 and "Safety abort" in out and not dry_run:
        code, out = rclone(args + ["--force"])
    return code, out


def sync_one(cfg: dict, folder: dict, dry_run: bool = False, log=print) -> dict:
    local = folder["path"]
    key = folder["key"]
    remote = remote_spec(cfg, key)
    result = {"key": key, "ok": False, "resynced": False, "output": ""}

    if not Path(local).is_dir():
        result["output"] = f"dossier inexistant, ignore : {local}"
        log(f"  [{key}] {result['output']}")
        return result

    if cfg.get("engine", "bisync") == "copy":
        common = ["--update", "--transfers", "4", "--checkers", "8", "--stats", "0"]
        rclone(["copy", remote, local, "--create-empty-src-dirs", *common])
        code, out = rclone(["copy", local, remote, *common])
        result.update(ok=code == 0, output=out)
        log(f"  sync(copy)  [{key}]")
        return result

    # le backend local exige que la racine distante existe
    rclone(["mkdir", remote])

    if not folder.get("resynced"):
        # 1er sync pour cette cle. Si nouveau PC (local vide + cloud plein),
        # pre-remplit depuis le cloud pour ne pas ecraser le cloud.
        local_empty = not any(Path(local).rglob("*")) or not any(
            p.is_file() for p in Path(local).rglob("*")
        )
        code_lsf, out_lsf = rclone(["lsf", "--files-only", remote])
        remote_empty = code_lsf != 0 or not out_lsf.strip()
        if local_empty and not remote_empty:
            log(f"  [{key}] nouveau PC detecte : pre-remplissage depuis le cloud...")
            rclone(["copy", remote, local, "--create-empty-src-dirs", "--stats", "0"])
        code, out = _bisync(cfg, local, remote, resync=not dry_run, dry_run=dry_run)
        if code != 0 and not dry_run:
            result["output"] = out
            log(f"  resync [{key}] a echoue :\n{out}")
            return result
        folder["resynced"] = True
        result["resynced"] = True
        save_config(cfg)
        log(f"  resync initial  [{key}]  ->  {remote}")
        result.update(ok=True, output=out)
        return result

    code, out = _bisync(cfg, local, remote, dry_run=dry_run)
    if dry_run:
        result.update(ok=True, output=out)
        return result
    if code != 0:
        result["output"] = out
        log(f"  sync [{key}] a echoue :\n{out}")
        return result
    result.update(ok=True, output=out)
    if ".conflict" in out:
        log(f"  sync  [{key}]  (conflits -> *.conflictN, commande 'conflicts')")
    else:
        log(f"  sync  [{key}]")
    return result


def check_remote(cfg: dict, log=print) -> bool:
    """Vérifie que le remote rclone existe (sinon message clair au lieu d'erreurs cryptiques)."""
    remote = str(cfg.get("remote", ""))
    if is_local_backend(cfg):
        return True
    try:
        code, out = rclone(["listremotes"])
    except RcloneError as e:
        log(f"ERREUR : {e}")
        return False
    remotes = {ln.strip().rstrip(":") for ln in out.splitlines() if ln.strip()}
    if remote in remotes:
        return True
    log(f"ERREUR : le remote rclone '{remote}' n'existe pas encore dans rclone.conf.")
    log("  Connecte ton compte cloud UNE fois :  double-clic sur setup.bat")
    log("  (ou: vendor\\windows-amd64\\rclone.exe config  -> 'n' -> nomme-le '" + remote + "')")
    log("  puis relance le sync.")
    return False


def is_folder_junk(f: dict) -> bool:
    """Dossier à retirer du suivi : inexistant, ou faux positif (blocklist, config app/rclone)."""
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
    """Retire les dossiers devenus inutiles (faux positifs, chemins supprimés)."""
    cfg = cfg or load_config()
    folders = [f for f in cfg.get("folders", []) if f.get("path")]
    kept = [f for f in folders if not is_folder_junk(f)]
    removed = len(folders) - len(kept)
    cfg["folders"] = kept
    save_config(cfg)
    for f in folders:
        if f not in kept:
            log(f"  retire : [{f.get('key')}] {f.get('path')}")
    log(f"Nettoyage termine : {removed} dossier(s) retire(s), {len(kept)} conserve(s).")
    return cfg


def sync_all(cfg: dict | None = None, dry_run: bool = False, log=print) -> list[dict]:
    cfg = cfg or load_config()
    folders = [f for f in cfg.get("folders", []) if f.get("path")]
    if not folders:
        log("Aucun dossier surveille. Lance 'scan --auto' ou 'add <chemin>'.")
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
                log(f"  local : {c}")
            for c in remote_c:
                log(f"  cloud : {c}")
    if not found:
        log("Aucun conflit.")
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
    """Racines connues de sauvegardes de jeux, par plateforme (+ extra_roots de la config)."""
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
        # LocalLow est un FRERE de LOCALAPPDATA : AppData\LocalLow (jeux Unity/Chromium)
        # LocalLow\<Studio>\<Jeu>\default\user1.dat (ex: Hollow Knight Silksong)
        if os.environ.get("LOCALAPPDATA"):
            add(Path(os.environ["LOCALAPPDATA"]).parent / "LocalLow")
        add(home / "Saved Games")
        add(home / "Documents" / "Saved Games")
        add(home / "Documents" / "My Games")
        packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
        if packages.is_dir():
            # jeux Microsoft Store : Packages/<Editeur>/<Jeu>/... -> chaque <Jeu> devient une racine
            for pub in packages.iterdir():
                if pub.is_dir():
                    for game in pub.iterdir():
                        if game.is_dir():
                            add(game)
    elif s == "Darwin":
        add(home / "Library" / "Application Support")
        containers = home / "Library" / "Containers"
        if containers.is_dir():
            # apps sandboxees : Containers/<bundle>/Data/... -> Data devient une racine
            for bundle in containers.iterdir():
                data = bundle / "Data"
                if data.is_dir():
                    add(data)
        _add_steam(roots, home / "Library" / "Application Support" / "Steam", add)
    else:  # Linux
        add(_xdg("XDG_CONFIG_HOME", home / ".config"))   # certains jeux (Unity...) écrivent ici
        add(_xdg("XDG_DATA_HOME", home / ".local" / "share"))
        add(home / ".var" / "app")                        # Flatpak
        _add_steam(roots, home / ".steam" / "steam", add)
        _add_steam(roots, _xdg("XDG_DATA_HOME", home / ".local" / "share") / "Steam", add)
    if cfg:
        for p in cfg.get("extra_roots", []) or []:
            add(Path(p).expanduser())
    return roots


def _add_steam(roots: list[Path], steam_dir: Path, add) -> None:
    """Steam + Proton : compatdata/<appid>/pfx/drive_c/users/<user>/... devient racine."""
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
    """Vrai si le dossier contient des fichiers de sauvegarde, en regardant
    récursivement jusqu'à max_depth niveaux (ex: jeu Unity dont les saves sont
    dans <jeu>/default/user1.dat). max_depth=0 -> fichiers directs uniquement.
    Les sous-dossiers "bloqués" (cache, logs...) sont ignorés."""
    try:
        if "save" in d.name.lower():
            return True
        base = str(d)
        seen = 0
        for cur, dirs, files in os.walk(d):
            depth = cur[len(base):].count(os.sep)
            # prune : profondeur max + dossiers bloques
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
    """Exclut les faux positifs connus (cache rclone, crashreports, launchers...)."""
    try:
        rel = os.path.relpath(str(p), str(root))
    except ValueError:
        rel = str(p)
    parts = [c.lower() for c in rel.split(os.sep)]
    return any(b in part for part in parts for b in BLOCK_PATTERNS)


def scan(cfg: dict | None = None) -> list[tuple[Path, Path]]:
    """Retourne [(root, dossier_detecte), ...] (profondeur 2 sous chaque racine)."""
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
            # 1) le fils lui-même si ses fichiers directs/nom disent "save" (dossier du jeu)
            if looks_like_save_dir(c, exts, max_depth=0):
                found.append((root, c))
                continue
            # 2) sinon les petits-enfants (granularité par jeu : Studio\Jeu),
            #    en cherchant les saves jusqu'à 2 niveaux à l'intérieur
            matched_gc = []
            try:
                for g in c.iterdir():
                    if g.is_dir() and not _is_blocked(root, g) and looks_like_save_dir(g, exts, max_depth=2):
                        matched_gc.append(g)
            except OSError:
                pass
            if matched_gc:
                found.extend((root, g) for g in matched_gc)
            # 3) sinon le fils en récursif (saves enfouies directement sous le fils)
            elif looks_like_save_dir(c, exts, max_depth=2):
                found.append((root, c))
    # dedoublonne + exclut notre propre dossier de config (le nom contient "save")
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
        raise FileNotFoundError(f"Chemin inexistant : {full}")
    if any(f.get("path") == full for f in cfg.get("folders", [])):
        log(f"Deja surveille : {full}")
        return cfg
    key = key_for(full)
    cfg.setdefault("folders", []).append({"key": key, "path": full, "resynced": False})
    save_config(cfg)
    log(f"Ajoute : [{key}]  {full}")
    return cfg


def remove_folder(key: str, cfg: dict | None = None, log=print) -> dict:
    cfg = cfg or load_config()
    cfg["folders"] = [f for f in cfg.get("folders", []) if f.get("key") != key]
    save_config(cfg)
    log(f"Retire : {key}")
    return cfg


# ----------------------------------------------------------------- watch ----

class Watcher(threading.Thread):
    """Surveille les dossiers (polling mtime) et synchro :
    - ~debounce secondes apres le dernier changement d'un dossier -> sync de ce dossier
    - toutes les interval_sec secondes -> sync complet (secours)
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
        self.log("Watch actif (Ctrl+C / Stop pour arreter).")
        snaps: dict[str, dict] = {}
        pending: dict[str, float] = {}
        synced_at: dict[str, float] = {}
        last_full = 0.0
        while not self._stop_event.is_set():
            try:
                cfg = load_config()
            except Exception as e:
                self.log(f"config illisible : {e}")
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
                    synced_at[key] = now
                    continue
                if snap != snaps[key]:
                    snaps[key] = snap
                    pending[key] = now
                if key in pending and now - pending[key] >= debounce:
                    del pending[key]
                    self.log(f"--- changement detecte [{key}] {time.strftime('%H:%M:%S')} ---")
                    try:
                        self.on_sync(sync_one(cfg, f, log=self.log))
                    except Exception as e:
                        self.log(f"erreur synchro [{key}] : {e}")
                    synced_at[key] = now
            if now - last_full >= interval:
                self.log(f"--- synchro periodique {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                try:
                    for r in sync_all(cfg, log=self.log):
                        self.on_sync(r)
                except Exception as e:
                    self.log(f"erreur synchro periodique : {e}")
                last_full = now
            self._stop_event.wait(1.0)
        self.log("Watch arrete.")
