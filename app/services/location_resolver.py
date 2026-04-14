"""Location resolver - determines coordinates and city name for a QSO.

Resolution order:
1. JCC code via Hamlog.mst / JCC table (Japanese stations only).
2. Grid square from FT8/other digital modes (4 or 6 char Maidenhead).
3. cty.dat prefix match (country-level fallback).

JCC/MST is skipped for non-Japanese callsigns because HAMLOG's CODE field
may contain a DXCC entity number that accidentally matches a Japanese MST
entry, causing foreign stations to be placed in Japan.
"""

import logging
from dataclasses import dataclass

from .cty_parser import CtyDat
from .geo_utils import grid_to_latlon, haversine_distance
from .hamlog_mst import HamlogMst
from .jcc_resolver import JccResolver
from .qrz_client import QrzClient
from .us_states import latlon_to_us_state

logger = logging.getLogger(__name__)


@dataclass
class ResolvedLocation:
    """Result of location resolution."""
    latitude: float
    longitude: float
    city_name: str
    city_name_en: str
    country: str
    method: str  # "mst", "jcc", "grid", "cty"
    distance_km: float = 0.0
    filled_grid_square: str = ""  # grid fetched via QRZ (needs writeback); empty otherwise


class LocationResolver:
    """Resolve callsign/QSO data to geographic coordinates."""

    def __init__(
        self,
        cty: CtyDat,
        jcc: JccResolver,
        station_lat: float,
        station_lon: float,
        mst: HamlogMst | None = None,
        qrz: QrzClient | None = None,
    ):
        self._cty = cty
        self._jcc = jcc
        self._mst = mst
        self._qrz = qrz
        self._station_lat = station_lat
        self._station_lon = station_lon

    def resolve(
        self,
        callsign: str,
        jcc_code: str = "",
        grid_square: str = "",
    ) -> ResolvedLocation | None:
        """Resolve a QSO to a location.

        Priority:
        1. Grid square (most precise, authoritative for all stations)
        2. Hamlog.mst / JCC code (Japanese city names for domestic QSOs)
        3. cty.dat prefix match (country-level fallback)
        """
        # JCC/MST codes are only meaningful for Japanese stations.
        # Foreign stations may have a DXCC entity number in HAMLOG's CODE
        # field that accidentally matches a Japanese MST entry.
        is_ja = False
        if jcc_code:
            entity = self._cty.lookup(callsign)
            is_ja = entity is not None and entity.name == "Japan"

        if is_ja and jcc_code:
            result = self._resolve_mst(jcc_code)
            if result:
                return result
            result = self._resolve_jcc(jcc_code)
            if result:
                return result

        if grid_square and len(grid_square) >= 4:
            result = self._resolve_grid(callsign, grid_square)
            if result:
                return result

        # No usable grid was supplied.  For non-Japanese stations, ask QRZ
        # for the operator's registered grid before falling back to cty.dat.
        # The returned grid is reported via filled_grid_square so the caller
        # can write it back to the HAMLOG database.
        if self._qrz and not is_ja:
            qrz_grid = self._qrz.lookup_grid(callsign)
            if qrz_grid and len(qrz_grid) >= 4:
                result = self._resolve_grid(callsign, qrz_grid)
                if result:
                    result.filled_grid_square = qrz_grid
                    return result

        result = self._resolve_cty(callsign)
        if result:
            return result

        logger.warning("Could not resolve location for %s", callsign)
        return None

    # ---- Strategies --------------------------------------------------------

    def _resolve_mst(self, code: str) -> ResolvedLocation | None:
        if not self._mst:
            return None
        entry = self._mst.lookup(code)
        if not entry:
            return None
        dist = haversine_distance(
            self._station_lat, self._station_lon, entry.latitude, entry.longitude,
        )
        return ResolvedLocation(
            latitude=entry.latitude,
            longitude=entry.longitude,
            city_name=entry.qth,
            city_name_en=entry.qth,
            country="Japan",
            method="mst",
            distance_km=round(dist, 1),
        )

    def _resolve_jcc(self, code: str) -> ResolvedLocation | None:
        info = self._jcc.lookup(code)
        if not info:
            return None
        lat, lon = info["lat"], info["lon"]
        dist = haversine_distance(self._station_lat, self._station_lon, lat, lon)
        return ResolvedLocation(
            latitude=lat,
            longitude=lon,
            city_name=info["name"],
            city_name_en=info.get("name_en", info["name"]),
            country="Japan",
            method="jcc",
            distance_km=round(dist, 1),
        )

    def _resolve_grid(self, callsign: str, grid_square: str) -> ResolvedLocation | None:
        coords = grid_to_latlon(grid_square)
        if not coords:
            return None
        lat, lon = coords
        dist = haversine_distance(self._station_lat, self._station_lon, lat, lon)
        country = ""
        entity = self._cty.lookup(callsign)
        if entity:
            country = entity.name
        # For US stations, prepend the state code derived from lat/lon.
        if country == "United States":
            state = latlon_to_us_state(lat, lon)
            city_name = f"{state}, {country}" if state else country
        else:
            city_name = country or f"Grid {grid_square.upper()}"
        return ResolvedLocation(
            latitude=lat,
            longitude=lon,
            city_name=city_name,
            city_name_en=city_name,
            country=country,
            method="grid",
            distance_km=round(dist, 1),
        )

    def _resolve_cty(self, callsign: str) -> ResolvedLocation | None:
        entity = self._cty.lookup(callsign)
        if not entity:
            return None
        lat, lon = entity.latitude, entity.longitude
        dist = haversine_distance(self._station_lat, self._station_lon, lat, lon)
        return ResolvedLocation(
            latitude=lat,
            longitude=lon,
            city_name=entity.name,
            city_name_en=entity.name,
            country=entity.name,
            method="cty",
            distance_km=round(dist, 1),
        )
