# Contributing

Thanks for your interest in Cloud Save Sync!

## How to contribute

1. **Fork** the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes (keep the code English, stdlib-only for the app itself).
3. Test locally:
   ```bash
   python -m py_compile savesync.py savesync/*.py
   python savesync.py --cli scan          # detection smoke test
   python savesync.py --cli add <testdir> && python savesync.py --cli sync   # with a local: backend
   ```
4. Commit with a clear message and open a **Pull Request** against `main`.

## Ideas / good first issues

- New save-location heuristics per platform (see `scan_roots()` in `savesync/core.py`)
- A system-tray icon for the GUI
- Better conflict UI (show `*.conflictN` diffs in the app)
- Translations (i18n) of the GUI
- Tests (pytest) for `core.py`

## Reporting bugs

Open an issue with: OS + version, app version, the exact CLI command or GUI steps,
and the log output (the journal pane in the GUI).
