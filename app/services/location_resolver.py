"""Location resolver - determines coordinates and city name for a QSO.

Resolution order:
1. Hamlog.mst CODE lookup (Turbo HAMLOG's own master table; authoritative
   for any JCC/JCG/ward code in the HDB).
2. Grid square from FT8/other digital modes (4 or 6 char Maidenhead).
3. cty.dat prefix match for foreign stations.

The old JCC lookup table (``JccResolver``) is kept as a last-resort fallback
but is not consulted when Hamlog.mst is available.
"""

import logging
from dataclasses import dataclass

from .cty_parser import CtyDat
from .geo_utils import grid_to_latlon, haversine_distance
from .hamlog_mst import HamlogMst
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
    method: str  # "mst", "jcc", "grid", "cty"
    distance_km: float = 0.0


class LocationResolver:
    """Resolve callsign/QSO data to geographic coordinates."""

    def __init__(
        self,
        cty: CtyDat,
        jcc: JccResolver,
        station_lat: float,
        station_lon: float,
        mst: HamlogMst | None = None,
    ):
        self._cty = cty
        self._jcc = jcc
        self._mst = mst
        self._station_lat = station_lat
        self._station_lon = station_lon

    def resolve(
        self,
        callsign: str,
        jcc_code: str = "",
        grid_square: str = "",
    ) -> ResolvedLocation | None:
        """Resolve a QSO to a location."""
        if jcc_code:
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
