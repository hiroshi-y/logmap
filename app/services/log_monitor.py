"""Log monitor - watches for new QSOs in Turbo HAMLOG database.

Polls the .hdb file for new records and emits events via callback.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .hamlog_reader import HamlogReader, HamlogQso
from .location_resolver import LocationResolver, ResolvedLocation

logger = logging.getLogger(__name__)


@dataclass
class QsoEvent:
    """A processed QSO event ready for the dashboard."""
    callsign: str
    date: str
    time_on: str
    band: str
    mode: str
    latitude: float
    longitude: float
    city_name: str
    city_name_en: str
    country: str
    distance_km: float
    resolve_method: str
    jcc_code: str
    grid_square: str


class LogMonitor:
    """Monitors Turbo HAMLOG .hdb file for new QSO records."""

    def __init__(self, reader: HamlogReader, resolver: LocationResolver,
                 poll_interval: float = 3.0,
                 on_new_qso=None):
        """
        Args:
            reader: HamlogReader instance.
            resolver: LocationResolver instance.
            poll_interval: Seconds between checks for new records.
            on_new_qso: Callback function(QsoEvent) called for each new QSO.
        """
        self._reader = reader
        self._resolver = resolver
        self._poll_interval = poll_interval
        self._on_new_qso = on_new_qso
        self._last_count = 0
        self._stop_event = threading.Event()
        self._sleep_fn: Callable = time.sleep  # overridden when using eventlet
        self._thread = None
        self._today_qsos: list[QsoEvent] = []
        self._stats = {
            "total_qsos": 0,
            "farthest_call": "",
            "farthest_location": "",
            "farthest_distance": 0.0,
        }

    def start(self, background_task_fn=None, sleep_fn=None) -> None:
        """Start monitoring in a background thread.

        Args:
            background_task_fn: Optional callable to start the background
                task (e.g. ``socketio.start_background_task``).
            sleep_fn: Optional sleep function (e.g. ``socketio.sleep``)
                that yields to the event loop.  Required when using
                eventlet/gevent so the poll loop doesn't block.
        """
        if self._thread and hasattr(self._thread, 'is_alive') and self._thread.is_alive():
            return

        if sleep_fn:
            self._sleep_fn = sleep_fn

        # Initialize with current record count
        self._last_count = self._reader.get_record_count()
        self._stop_event.clear()

        if background_task_fn:
            self._thread = background_task_fn(self._poll_loop)
        else:
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()

        logger.info(
            "Log monitor started. Current records: %d, polling every %.1fs",
            self._last_count, self._poll_interval,
        )

    def stop(self) -> None:
        """Stop monitoring."""
        self._stop_event.set()
        if self._thread and hasattr(self._thread, 'join'):
            self._thread.join(timeout=2)
        self._thread = None
        logger.info("Log monitor stopped.")

    def get_today_qsos(self) -> list[QsoEvent]:
        """Get all QSOs currently loaded."""
        return list(self._today_qsos)

    def get_stats(self) -> dict:
        """Get current statistics."""
        return dict(self._stats)

    def load_initial_qsos(self, count: int = 20) -> list[QsoEvent]:
        """Load the last N QSOs for initial display."""
        records = self._reader.read_last_n_records(count)
        events = []
        for rec in records:
            event = self._process_qso(rec)
            if event:
                events.append(event)
        self._today_qsos = events
        self._update_stats()
        return events

    def _poll_loop(self) -> None:
        """Main polling loop - runs in background thread."""
        while not self._stop_event.is_set():
            try:
                current_count = self._reader.get_record_count()

                if current_count > self._last_count:
                    new_records = self._reader.read_records_from(self._last_count)
                    self._last_count = current_count

                    for rec in new_records:
                        event = self._process_qso(rec)
                        if event:
                            self._today_qsos.append(event)
                            self._update_stats()
                            if self._on_new_qso:
                                self._on_new_qso(event)

            except Exception as e:
                logger.error("Error in poll loop: %s", e)

            self._sleep_fn(self._poll_interval)

    def _process_qso(self, rec: HamlogQso) -> QsoEvent | None:
        """Process a raw QSO record into a QsoEvent with location."""
        location = self._resolver.resolve(
            callsign=rec.callsign,
            jcc_code=rec.jcc_code,
            grid_square=rec.gl,
        )
        if not location:
            logger.warning("Could not resolve location for %s", rec.callsign)
            return None

        return QsoEvent(
            callsign=rec.callsign,
            date=rec.date,
            time_on=rec.time_on,
            band=rec.band,
            mode=rec.mode,
            latitude=location.latitude,
            longitude=location.longitude,
            city_name=location.city_name,
            city_name_en=location.city_name_en,
            country=location.country,
            distance_km=location.distance_km,
            resolve_method=location.method,
            jcc_code=rec.jcc_code,
            grid_square=rec.gl,
        )

    def _update_stats(self) -> None:
        """Update cumulative statistics."""
        self._stats["total_qsos"] = len(self._today_qsos)
        for qso in self._today_qsos:
            if qso.distance_km > self._stats["farthest_distance"]:
                self._stats["farthest_distance"] = qso.distance_km
                self._stats["farthest_call"] = qso.callsign
                self._stats["farthest_location"] = qso.city_name
