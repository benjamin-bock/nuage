"""Tkinter GUI for Cloud Save Sync (Windows / Linux / macOS)."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import time
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import core


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, cfg: dict, on_save):
        super().__init__(master)
        self.title("Settings")
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.resizable(False, False)
        self.transient(master)

        rows = [
            ("Provider / rclone remote", "remote",
             "onedrive-local (recommended, no OAuth), onedrive, gdrive, dropbox, icloud, local:<path>"),
            ("Cloud root folder", "remote_dir", ""),
            ("Engine", "engine", "bisync (sync) or copy (backup)"),
            ("Conflicts", "conflict_resolve", "newer / older / larger / smaller"),
            ("rclone compare", "compare", "e.g. size,modtime"),
            ("Sync interval (s)", "interval_sec", "watch mode"),
            ("Watch debounce (s)", "watch_debounce_sec", ""),
        ]
        self.vars = {}
        for i, (label, key, hint) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=str(self.cfg.get(key, "")))
            ttk.Entry(self, textvariable=v, width=42).grid(row=i, column=1, padx=8, pady=4)
            if hint:
                ttk.Label(self, text=hint, foreground="gray").grid(row=i, column=2, sticky="w", padx=4)
            self.vars[key] = v

        ttk.Button(self, text="Save", command=self._save).grid(
            row=len(rows), column=0, columnspan=3, pady=10)

    def _save(self):
        for key, v in self.vars.items():
            val = v.get().strip()
            if key in ("interval_sec", "watch_debounce_sec"):
                val = int(val) if val else core.DEFAULTS[key]
            self.cfg[key] = val
        self.on_save(self.cfg)
        self.destroy()


class ScanDialog(tk.Toplevel):
    """List of detected folders, with checkboxes."""

    def __init__(self, master, found: list[tuple], on_add):
        super().__init__(master)
        self.title("Detected save folders")
        self.on_add = on_add
        self.transient(master)
        ttk.Label(self, text=f"{len(found)} folder(s) detected — check the ones to watch:").pack(
            anchor="w", padx=8, pady=4)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8)
        self.listbox = tk.Listbox(frame, selectmode="extended", width=100, height=18)
        scroll = ttk.Scrollbar(frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.found = found
        for _, p in found:
            self.listbox.insert("end", str(p))
        for i in range(len(found)):
            self.listbox.selection_set(i)
        ttk.Button(self, text="Add selected", command=self._add).pack(pady=8)

    def _add(self):
        sel = self.listbox.curselection()
        self.on_add([self.found[i] for i in sel])
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cloud Save Sync")
        self.geometry("960x600")
        self.cfg = core.load_config()
        self.msgq: queue.Queue = queue.Queue()
        self.watcher: core.Watcher | None = None
        self.worker: threading.Thread | None = None

        self._build_ui()
        self.refresh_tree()
        self._set_status()
        self.after(200, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- UI ----
    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=6)
        self.btn = {}
        for label, cmd in [
            ("⚙ Settings", self.open_settings),
            ("🔎 Scan", self.do_scan),
            ("➕ Add…", self.do_add),
            ("➖ Remove", self.do_remove),
            ("🔄 Sync now", self.do_sync),
            ("👁 Status", self.do_status),
            ("🧹 Clean", self.do_clean),
            ("▶ Auto-sync", self.do_start_watch),
            ("⏹ Stop", self.do_stop_watch),
        ]:
            b = ttk.Button(toolbar, text=label, command=cmd)
            b.pack(side="left", padx=2)
            self.btn[label] = b

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=6, pady=4)

        top = ttk.Frame(paned)
        paned.add(top, weight=3)
        ttk.Label(top, text="Watched folders:").pack(anchor="w")
        cols = ("key", "path", "state")
        self.tree = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse")
        for c, w in (("key", 200), ("path", 560), ("state", 90)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w)
        yscroll = ttk.Scrollbar(top, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=2)
        ttk.Label(bottom, text="Log:").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(bottom, height=12, state="disabled",
                                                  wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("error", foreground="#cc3333")
        self.log_text.tag_config("warn", foreground="#cc8800")
        self.log_text.tag_config("ok", foreground="#228833")

        self.status = ttk.Label(self, text="", anchor="w")
        self.status.pack(fill="x", padx=6, pady=2)

    def _set_status(self):
        r = self.cfg.get("remote", "?")
        rd = self.cfg.get("remote_dir", "")
        n = len([f for f in self.cfg.get("folders", []) if f.get("path")])
        self.status.config(
            text=f"Cloud: {r}:{rd}   |   engine: {self.cfg.get('engine')}   |   "
                 f"{n} folder(s)   |   config: {core.config_path()}")

    def log(self, msg: str, tag: str | None = None):
        self.msgq.put((msg, tag))

    def _drain_queue(self):
        try:
            while True:
                msg, tag = self.msgq.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n", tag)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._drain_queue)

    def refresh_tree(self):
        self.cfg = core.load_config()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for f in self.cfg.get("folders", []):
            if not f.get("path"):
                continue
            state = "synced" if f.get("resynced") else "resync"
            self.tree.insert("", "end", iid=f["key"],
                             values=(f["key"], f["path"], state))
        self._set_status()

    # --------------------------------------------------------- actions ----
    def _run_bg(self, fn, done=None):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Cloud Save Sync", "An operation is already running.")
            return
        self.worker = threading.Thread(target=self._bg_wrap, args=(fn, done), daemon=True)
        self.worker.start()

    def _bg_wrap(self, fn, done):
        try:
            fn()
        except Exception as e:
            self.log(f"ERROR: {e}", "error")
        finally:
            if done:
                self.after(0, done)

    def open_settings(self):
        SettingsDialog(self, self.cfg, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_cfg):
        core.save_config(new_cfg)
        self.cfg = core.load_config()
        self._set_status()
        self.log("Settings saved.")

    def do_scan(self):
        self.log("Scanning for save folders...")
        found = core.scan()
        if not found:
            self.log("Nothing detected. Add a folder manually (➕).")
            return
        self.log(f"{len(found)} folder(s) detected.")
        ScanDialog(self, found, on_add=lambda sel: self._add_scanned(sel))

    def _add_scanned(self, sel):
        cfg = core.load_config()
        for root, p in sel:
            if not any(f.get("path") == str(p) for f in cfg.get("folders", [])):
                core.add_folder(str(p), cfg, log=lambda m: self.log(m))
        self.refresh_tree()

    def do_add(self):
        path = filedialog.askdirectory(title="Choose the game's save folder")
        if not path:
            return
        try:
            core.add_folder(path, log=lambda m: self.log(m))
        except FileNotFoundError as e:
            messagebox.showerror("Error", str(e))
        self.refresh_tree()

    def do_remove(self):
        sel = self.tree.selection()
        if not sel:
            return
        key = sel[0]
        if messagebox.askyesno("Remove", f"Stop watching [{key}]?\n"
                                 "(files already in the cloud are kept)"):
            core.remove_folder(key, log=lambda m: self.log(m))
            self.refresh_tree()

    def do_sync(self):
        self.log(f"--- sync {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        self._run_bg(lambda: core.sync_all(log=self.log), done=self.refresh_tree)

    def do_status(self):
        self.log("--- status (dry-run) ---")
        def run():
            cfg = core.load_config()
            for f in cfg.get("folders", []):
                if not f.get("path"):
                    continue
                r = core.sync_one(cfg, f, dry_run=True)
                out = "\n".join(ln for ln in r["output"].splitlines()
                                if "NOTICE" not in ln and "Bisync" not in ln).strip()
                self.log(f"[{f['key']}] {'up to date' if not out else 'changes:'}")
                if out:
                    self.log(out)
        self._run_bg(run)

    def do_clean(self):
        self.log("Cleaning folders (false positives / deleted paths)...")
        def run():
            core.clean_config(log=self.log)
        self._run_bg(run, done=self.refresh_tree)

    def do_start_watch(self):
        if self.watcher and self.watcher.is_alive():
            return
        self.log("Auto-sync started (watch + periodic sync).")
        self.watcher = core.Watcher(log=self.log)
        self.watcher.start()

    def do_stop_watch(self):
        if self.watcher:
            self.watcher.stop()
            self.log("Auto-sync stop requested...")
            self.watcher = None

    def _on_close(self):
        if self.watcher:
            self.watcher.stop()
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
