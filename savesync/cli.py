"""Interface en ligne de commande de Cloud Save Sync."""
from __future__ import annotations

import argparse
import sys

from . import core


def _prompt(text: str, default: str) -> str:
    try:
        v = input(f"{text} [{default}]: ").strip()
    except EOFError:
        v = ""
    return v or default


def cmd_init(args) -> int:
    cfg = core.load_config()
    print("=== Configuration de Cloud Save Sync ===")
    print("Providers cloud via rclone : onedrive, gdrive (Google Drive), dropbox, mega...")
    print("Ou 'icloud' (iCloud Drive) ou 'local:<chemin>' (dossier local).")
    cfg["remote"] = _prompt("Nom du provider / remote rclone", cfg["remote"])
    cfg["remote_dir"] = _prompt("Dossier racine dans le cloud", cfg["remote_dir"])
    cfg["engine"] = _prompt("Moteur : bisync (sync) ou copy (backup)", cfg["engine"])
    cfg["conflict_resolve"] = _prompt("Conflits : newer/older/larger/smaller", cfg["conflict_resolve"])
    cfg["interval_sec"] = int(_prompt("Intervalle de synchro (s) pour watch", str(cfg["interval_sec"])))
    core.save_config(cfg)
    print(f"Config enregistree dans {core.config_path()}")
    if not core.is_local_backend(cfg) and not core.find_rclone():
        print("ATTENTION : rclone introuvable -> scripts/fetch_rclone.py ou PATH")
    elif not core.is_local_backend(cfg):
        print("Si ce n'est pas fait : rclone config  (connecte ton cloud)")
    print("Etape suivante : scan --auto   puis   sync")
    return 0


def cmd_scan(args) -> int:
    if args.auto:
        core.clean_config()  # retire les anciens faux positifs avant de re-scanner
    found = core.scan()
    if not found:
        print("Aucun dossier de sauvegarde detecte.")
        return 0
    print("Dossiers de sauvegardes detectes :")
    for i, (root, p) in enumerate(found):
        print(f"  [{i}] {p}")
    if args.auto:
        cfg = core.load_config()
        for root, p in found:
            if not any(f.get("path") == str(p) for f in cfg.get("folders", [])):
                core.add_folder(str(p), cfg)
        print("Terminé. Verifie avec : list")
    else:
        print('Ajout manuel : add "<chemin>"   |   tout ajouter : scan --auto')
    return 0


def cmd_add(args) -> int:
    core.add_folder(args.path)
    return 0


def cmd_remove(args) -> int:
    core.remove_folder(args.key)
    return 0


def cmd_list(args) -> int:
    cfg = core.load_config()
    folders = [f for f in cfg.get("folders", []) if f.get("path")]
    if not folders:
        print("Aucun dossier surveille.")
        return 0
    print(f"Cloud : {cfg['remote']}:{cfg['remote_dir']}   moteur : {cfg['engine']}   "
          f"conflits : {cfg['conflict_resolve']}")
    for f in folders:
        state = "sync" if f.get("resynced") else "resync prevu"
        print(f"  [{f['key']}] ({state}) {f['path']}")
    return 0


def cmd_sync(args) -> int:
    results = core.sync_all(dry_run=args.dry_run)
    return 0 if all(r["ok"] for r in results) else 1


def cmd_status(args) -> int:
    cfg = core.load_config()
    for f in cfg.get("folders", []):
        if not f.get("path"):
            continue
        r = core.sync_one(cfg, f, dry_run=True)
        out = "\n".join(
            ln for ln in r["output"].splitlines()
            if "NOTICE" not in ln and "Bisync" not in ln
        ).strip()
        print(f"[{f['key']}] {'a jour' if not out else ''}")
        if out:
            print(out)
    return 0


def cmd_conflicts(args) -> int:
    core.list_conflicts()
    return 0


def cmd_resync(args) -> int:
    core.force_resync(key=args.key or None)
    return 0


def cmd_clean(args) -> int:
    core.clean_config()
    return 0


def cmd_watch(args) -> int:
    w = core.Watcher()
    try:
        if args.once:
            core.sync_all()
            return 0
        w.start()
        while w.is_alive():
            w.join(timeout=1.0)
    except KeyboardInterrupt:
        w.stop()
        w.join(timeout=5)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="savesync",
        description="Sync bidirectionnel des sauvegardes de jeux vers le cloud (rclone bisync).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="configuration interactive").set_defaults(func=cmd_init)

    ps = sub.add_parser("scan", help="detecter les dossiers de sauvegardes")
    ps.add_argument("--auto", action="store_true", help="ajoute tout automatiquement")
    ps.set_defaults(func=cmd_scan)

    pa = sub.add_parser("add", help="ajouter un dossier")
    pa.add_argument("path")
    pa.set_defaults(func=cmd_add)

    pr = sub.add_parser("remove", help="retirer un dossier")
    pr.add_argument("key")
    pr.set_defaults(func=cmd_remove)

    sub.add_parser("list", help="lister les dossiers surveilles").set_defaults(func=cmd_list)
    psy = sub.add_parser("sync", help="synchroniser maintenant")
    psy.add_argument("--dry-run", action="store_true")
    psy.set_defaults(func=cmd_sync)
    sub.add_parser("status", help="dry-run : ce qui changerait").set_defaults(func=cmd_status)
    sub.add_parser("conflicts", help="lister les *.conflictN").set_defaults(func=cmd_conflicts)
    pre = sub.add_parser("resync", help="forcer un resync initial")
    pre.add_argument("key", nargs="?", default=None)
    pre.set_defaults(func=cmd_resync)
    pw = sub.add_parser("watch", help="surveillance continue (auto-sync)")
    pw.add_argument("--once", action="store_true", help="un seul cycle (test)")
    pw.set_defaults(func=cmd_watch)
    sub.add_parser("clean", help="retirer les dossiers devenus faux positifs/inexistants").set_defaults(func=cmd_clean)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
