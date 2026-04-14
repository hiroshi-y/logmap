"""QRZ.com XML Logbook Data API client.

Minimal client for looking up a callsign's grid square (Maidenhead locator).
Uses session-key auth: login once with username/password, reuse the key
until it expires, then re-login on demand.

API reference: https://www.qrz.com/XML/current_spec.html
"""

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


_API_URL = "https://xmldata.qrz.com/xml/current/"
_AGENT = "logmap-1.0"
_NS = {"q": "http://xmldata.qrz.com"}


class QrzError(Exception):
    """QRZ API returned an error."""


class QrzClient:
    """QRZ XML API client with in-memory grid cache."""

    def __init__(self, username: str, password: str, timeout: float = 5.0):
        self._username = username
        self._password = password
        self._timeout = timeout
        self._session_key: str | None = None
        self._grid_cache: dict[str, str | None] = {}  # callsign -> grid (or None if not found)

    def lookup_grid(self, callsign: str) -> str | None:
        """Return grid square for callsign, or None if not found."""
        if not callsign:
            return None
        key = callsign.upper()
        if key in self._grid_cache:
            return self._grid_cache[key]
        try:
            grid = self._do_lookup(key)
        except (QrzError, OSError, ET.ParseError) as e:
            logger.warning("QRZ lookup failed for %s: %s", key, e)
            return None
        self._grid_cache[key] = grid
        return grid

    # ---- internals ---------------------------------------------------------

    def _ensure_session(self) -> None:
        if self._session_key:
            return
        self._login()

    def _login(self) -> None:
        params = {
            "username": self._username,
            "password": self._password,
            "agent": _AGENT,
        }
        root = self._request(params)
        session = root.find("q:Session", _NS)
        if session is None:
            raise QrzError("No Session element in login response")
        key_el = session.find("q:Key", _NS)
        err_el = session.find("q:Error", _NS)
        if key_el is None or not (key_el.text or "").strip():
            msg = (err_el.text if err_el is not None else "unknown").strip()
            raise QrzError(f"Login failed: {msg}")
        self._session_key = key_el.text.strip()
        logger.info("QRZ session established")

    def _do_lookup(self, callsign: str) -> str | None:
        self._ensure_session()
        try:
            return self._lookup_with_key(callsign)
        except QrzError as e:
            # Session may have expired; try once more with a fresh login.
            logger.info("QRZ re-login after error: %s", e)
            self._session_key = None
            self._login()
            return self._lookup_with_key(callsign)

    def _lookup_with_key(self, callsign: str) -> str | None:
        params = {"s": self._session_key, "callsign": callsign}
        root = self._request(params)
        session = root.find("q:Session", _NS)
        if session is not None:
            err = session.find("q:Error", _NS)
            if err is not None and (err.text or "").strip():
                msg = err.text.strip()
                # "Not found" is not a fatal error; other errors invalidate session.
                if "not found" in msg.lower():
                    return None
                raise QrzError(msg)
        callsign_el = root.find("q:Callsign", _NS)
        if callsign_el is None:
            return None
        grid_el = callsign_el.find("q:grid", _NS)
        if grid_el is None or not (grid_el.text or "").strip():
            return None
        return grid_el.text.strip()

    def _request(self, params: dict) -> ET.Element:
        url = _API_URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=self._timeout) as resp:
            data = resp.read()
        return ET.fromstring(data)
