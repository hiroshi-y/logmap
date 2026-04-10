"""Flask application with SocketIO for real-time dashboard updates."""

import os
import logging
from dataclasses import asdict

import yaml
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from .i18n import set_language, get_all_translations, get_current_language
from .services.cty_parser import CtyDat
from .services.jcc_resolver import JccResolver
from .services.location_resolver import LocationResolver
from .services.hamlog_mst import HamlogMst
from .services.hamlog_reader import HamlogReader
from .services.log_monitor import LogMonitor, QsoEvent

logger = logging.getLogger(__name__)

# Global instances
socketio = SocketIO()
monitor: LogMonitor | None = None
config: dict = {}


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_app(config_path: str = "config.yaml") -> Flask:
    """Create and configure the Flask application."""
    global monitor, config

    # Load config
    config = load_config(config_path)

    # Set up logging
    log_level = config.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
        ],
    )
    log_file = config.get("logging", {}).get("file")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        )
        logging.getLogger().addHandler(file_handler)

    # Set language
    lang = config.get("dashboard", {}).get("language", "ja")
    set_language(lang)

    # Create Flask app
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.config["SECRET_KEY"] = os.urandom(24).hex()

    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins="*")

    # Initialize services
    base_dir = os.path.dirname(os.path.dirname(__file__))

    # cty.dat
    cty = CtyDat()
    cty_path = config.get("cty_dat", {}).get("file_path", "data/cty.dat")
    if not os.path.isabs(cty_path):
        cty_path = os.path.join(base_dir, cty_path)
    cty.load(cty_path)

    # JCC resolver
    jcc = JccResolver()
    jcc_path = config.get("jcc", {}).get("file_path", "data/jcc_codes.json")
    if not os.path.isabs(jcc_path):
        jcc_path = os.path.join(base_dir, jcc_path)
    jcc.load_from_file(jcc_path)

    # HAMLOG reader + master file
    hamlog_cfg = config.get("hamlog", {})
    data_dir = hamlog_cfg.get("data_dir", "C:\\Hamlog\\Data")
    hdb_path = os.path.join(data_dir, hamlog_cfg.get("db_file", "Hamlog.hdb"))
    mst_path = os.path.join(data_dir, hamlog_cfg.get("mst_file", "Hamlog.mst"))
    reader = HamlogReader(hdb_path)

    mst = HamlogMst()
    mst.load(mst_path)

    # Location resolver
    station = config.get("station", {})
    resolver = LocationResolver(
        cty=cty,
        jcc=jcc,
        station_lat=station.get("latitude", 35.6812),
        station_lon=station.get("longitude", 139.7671),
        mst=mst,
    )

    # Log monitor
    def on_new_qso(event: QsoEvent):
        """Callback when a new QSO is detected."""
        socketio.emit("new_qso", asdict(event))
        socketio.emit("stats_update", monitor.get_stats())

    monitor = LogMonitor(
        reader=reader,
        resolver=resolver,
        poll_interval=hamlog_cfg.get("poll_interval", 3),
        on_new_qso=on_new_qso,
    )

    # Register routes
    register_routes(app)

    # Register SocketIO events
    register_socket_events()

    return app


def register_routes(app: Flask) -> None:
    """Register HTTP routes."""

    @app.route("/")
    def index():
        translations = get_all_translations()
        station = config.get("station", {})
        google_api_key = config.get("google_maps", {}).get("api_key", "")
        return render_template(
            "dashboard.html",
            translations=translations,
            lang=get_current_language(),
            station_lat=station.get("latitude", 35.6812),
            station_lon=station.get("longitude", 139.7671),
            station_call=station.get("callsign", ""),
            google_api_key=google_api_key,
        )

    @app.route("/api/translations/<lang>")
    def get_translations(lang: str):
        if lang not in ("ja", "en"):
            lang = "ja"
        return jsonify(get_all_translations(lang))

    @app.route("/api/qsos")
    def get_qsos():
        if monitor:
            qsos = monitor.get_today_qsos()
            return jsonify([asdict(q) for q in qsos])
        return jsonify([])

    @app.route("/api/stats")
    def get_stats():
        if monitor:
            return jsonify(monitor.get_stats())
        return jsonify({
            "total_qsos": 0,
            "farthest_call": "",
            "farthest_location": "",
            "farthest_distance": 0.0,
        })


def register_socket_events() -> None:
    """Register SocketIO event handlers."""

    @socketio.on("connect")
    def handle_connect():
        logger.info("Client connected")
        if monitor:
            # Send initial data
            qsos = monitor.get_today_qsos()
            socketio.emit("initial_qsos", [asdict(q) for q in qsos])
            socketio.emit("stats_update", monitor.get_stats())

    @socketio.on("disconnect")
    def handle_disconnect():
        logger.info("Client disconnected")

    @socketio.on("change_language")
    def handle_change_language(data):
        lang = data.get("lang", "ja")
        set_language(lang)
        socketio.emit("language_changed", {
            "lang": lang,
            "translations": get_all_translations(lang),
        })


def start_monitoring(initial_qso_count: int | None = None) -> None:
    """Start the log monitor (call after app is created)."""
    if monitor:
        count = initial_qso_count if initial_qso_count is not None else config.get("dashboard", {}).get("initial_qso_count", 1)
        monitor.load_initial_qsos(count)
        monitor.start(background_task_fn=socketio.start_background_task)
