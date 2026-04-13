"""LogMap - Amateur Radio Dashboard
Entry point for the application.
"""

import argparse
import ctypes
import ctypes.wintypes
import os
import sys

import yaml

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from app.server import create_app, socketio, start_monitoring, monitor

# ---- Immediate Ctrl+C handler via Win32 ----------------------------------
# Python's signal.SIGINT is checked only periodically and can be delayed by
# eventlet's event loop.  SetConsoleCtrlHandler fires at the OS level.

@ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.DWORD)
def _ctrl_handler(event):
    if event == 0:  # CTRL_C_EVENT
        if monitor:
            monitor.stop()
        os._exit(0)
    return False

ctypes.WinDLL("kernel32").SetConsoleCtrlHandler(_ctrl_handler, True)


def main():
    if "-?" in sys.argv:
        sys.argv = [("-h" if a == "-?" else a) for a in sys.argv]
    parser = argparse.ArgumentParser(description="LogMap amateur radio dashboard")
    parser.add_argument(
        "-c", "--config",
        default=os.path.join(os.path.dirname(__file__), "config.yaml"),
        help="path to config.yaml (default: config.yaml in project root)",
    )
    parser.add_argument(
        "-g", "--grid",
        default=None,
        help="station QTH as Maidenhead grid square (default: PM95UQ)",
    )
    parser.add_argument(
        "-n", "--initial-qsos",
        type=int,
        default=None,
        help="number of past QSOs to preload (default: 100)",
    )
    parser.add_argument(
        "-k", "--open-cards",
        type=int,
        default=None,
        help="number of latest QSO cards to show open (default: 1)",
    )
    args = parser.parse_args()

    app = create_app(
        config_path=args.config,
        grid_square=args.grid,
        open_cards=args.open_cards,
    )

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    host = config.get("dashboard", {}).get("host", "0.0.0.0")
    port = config.get("dashboard", {}).get("port", 5000)

    start_monitoring(initial_qso_count=args.initial_qsos)

    print(f"LogMap Dashboard starting on http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    socketio.run(app, host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
