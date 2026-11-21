"""Command-line interface for Cloud Save Sync."""
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
    print("=== Cloud Save Sync configuration ===")
    print("Providers: 'onedrive-local' (RECOMMENDED: local OneDrive folder, no OAuth,")
    print("  also works with work/school accounts), 'gdrive-local', 'dropbox-local',")
    print("  'icloud', 'local:<path>', or an rclone remote: onedrive, gdrive, dropbox, mega...")
    cfg["remote"] = _prompt("Provider / rclone remote name", cfg["remote"])
    cfg["remote_dir"] = _prompt("Root folder in the cloud", cfg["remote_dir"])
    cfg["engine"] = _prompt("Engine: bisync (sync) or copy (backup)", cfg["engine"])
    cfg["conflict_resolve"] = _prompt("Conflicts: newer/older/larger/smaller", cfg["conflict_resolve"])
    cfg["interval_sec"] = int(_prompt("Sync interval (s) for watch", str(cfg["interval_sec"])))
    core.save_config(cfg)
    print(f"Config saved to {core.config_path()}")
    if not core.is_local_backend(cfg) and not core.find_rclone():
        print("WARNING: rclone not found -> scripts/fetch_rclone.py or PATH")
    elif not core.is_local_backend(cfg):
        print("If not done yet: rclone config  (connect your cloud)")
    print("Next step: scan --auto   then   sync")
    return 0


def cmd_scan(args) -> int:
    if args.auto:
        core.clean_config()  # drop old false positives before rescanning
    found = core.scan()
    if not found:
        print("No save folder detected.")
        return 0
    print("Detected save folders:")
    for i, (root, p) in enumerate(found):
        print(f"  [{i}] {p}")
    if args.auto:
        cfg = core.load_config()
        for root, p in found:
            if not any(f.get("path") == str(p) for f in cfg.get("folders", [])):
                core.add_folder(str(p), cfg)
        print("Done. Check with: list")
    else:
        print('Manual add: add "<path>"   |   add all: scan --auto')
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
        print("No folder watched.")
        return 0
    print(f"Cloud: {cfg['remote']}:{cfg['remote_dir']}   engine: {cfg['engine']}   "
          f"conflicts: {cfg['conflict_resolve']}")
    for f in folders:
        state = "synced" if f.get("resynced") else "resync pending"
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
        print(f"[{f['key']}] {'up to date' if not out else ''}")
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
        description="Bidirectional sync of game save folders to the cloud (rclone bisync).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="interactive configuration").set_defaults(func=cmd_init)

    ps = sub.add_parser("scan", help="detect save folders")
    ps.add_argument("--auto", action="store_true", help="add everything automatically")
    ps.set_defaults(func=cmd_scan)

    pa = sub.add_parser("add", help="add a folder")
    pa.add_argument("path")
    pa.set_defaults(func=cmd_add)

    pr = sub.add_parser("remove", help="remove a folder")
    pr.add_argument("key")
    pr.set_defaults(func=cmd_remove)

    sub.add_parser("list", help="list watched folders").set_defaults(func=cmd_list)
    psy = sub.add_parser("sync", help="sync now")
    psy.add_argument("--dry-run", action="store_true")
    psy.set_defaults(func=cmd_sync)
    sub.add_parser("status", help="dry-run: what would change").set_defaults(func=cmd_status)
    sub.add_parser("conflicts", help="list *.conflictN files").set_defaults(func=cmd_conflicts)
    pre = sub.add_parser("resync", help="force an initial resync")
    pre.add_argument("key", nargs="?", default=None)
    pre.set_defaults(func=cmd_resync)
    pw = sub.add_parser("watch", help="continuous watching (auto-sync)")
    pw.add_argument("--once", action="store_true", help="single cycle (test)")
    pw.set_defaults(func=cmd_watch)
    sub.add_parser("clean", help="remove folders that became false positives/missing").set_defaults(func=cmd_clean)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
