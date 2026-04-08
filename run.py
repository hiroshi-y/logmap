"""LogMap - Amateur Radio Dashboard
Entry point for the application.
"""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from app.server import create_app, socketio, start_monitoring


def main():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    # Allow config override via command line
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    app = create_app(config_path)

    # Read dashboard settings from config
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    host = config.get("dashboard", {}).get("host", "0.0.0.0")
    port = config.get("dashboard", {}).get("port", 5000)

    # Start log monitoring
    start_monitoring()

    print(f"LogMap Dashboard starting on http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    socketio.run(app, host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
