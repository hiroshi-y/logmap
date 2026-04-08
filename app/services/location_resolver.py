"""Location resolver - determines coordinates and city name for a QSO.

Uses multiple strategies in priority order:
1. JCC code (for Japanese stations)
2. Grid square (from digital modes like FT8)
3. cty.dat prefix lookup (fallback for CW/Phone)
"""

import logging
from dataclasses import dataclass

from .geo_utils import grid_to_latlon, haversine_distance
from .cty_parser import CtyDat
from .jcc_resolver import JccResolver

logger = logging.getLogger(__name__)


@dataclass
class ResolvedLocation:
    """Result of location resolution."""
    latitude: float
    longitude: float
    city_name: str
    city_name_en: str
    country: str
    method: str  # "jcc", "grid", "cty"
    distance_km: float = 0.0


class LocationResolver:
    """Resolve callsign/QSO data to geographic coordinates."""

    def __init__(self, cty: CtyDat, jcc: JccResolver,
                 station_lat: float, station_lon: float):
        self._cty = cty
        self._jcc = jcc
        self._station_lat = station_lat
        self._station_lon = station_lon

    def resolve(self, callsign: str, jcc_code: str = "",
                grid_square: str = "") -> ResolvedLocation | None:
        """Resolve a QSO to a location.

        Args:
            callsign: The callsign of the contacted station.
            jcc_code: JCC code if available (Japanese stations).
            grid_square: Grid square locator if available (FT8 etc.).

        Returns:
            ResolvedLocation or None if resolution failed.
        """
        # Strategy 1: JCC code
        if jcc_code:
            result = self._resolve_jcc(callsign, jcc_code)
            if result:
                return result

        # Strategy 2: Grid square
        if grid_square and len(grid_square) >= 4:
            result = self._resolve_grid(callsign, grid_square)
            if result:
                return result

        # Strategy 3: cty.dat fallback
        result = self._resolve_cty(callsign)
        if result:
            return result

        logger.warning("Could not resolve location for %s", callsign)
        return None

    def _resolve_jcc(self, callsign: str, jcc_code: str) -> ResolvedLocation | None:
        info = self._jcc.lookup(jcc_code)
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

        # Try to get country name from cty.dat
        country = ""
        entity = self._cty.lookup(callsign)
        if entity:
            country = entity.name

        city_name = f"Grid {grid_square.upper()}"
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
