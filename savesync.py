#!/usr/bin/env python3
"""Cloud Save Sync — entry point.

No arguments      -> launches the GUI (falls back to CLI if no display).
`savesync.py gui` -> GUI
`savesync.py --cli ...` -> command line (init, scan, sync, watch, ...)
"""
import sys


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "gui":
        from savesync.gui import main as gui_main
        gui_main()
        return 0
    if args and args[0] == "--cli":
        from savesync.cli import main as cli_main
        return cli_main(args[1:])
    if not args:
        try:
            from savesync.gui import main as gui_main
            gui_main()
            return 0
        except Exception:
            from savesync.cli import main as cli_main
            return cli_main(["--help"])
    from savesync.cli import main as cli_main
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
