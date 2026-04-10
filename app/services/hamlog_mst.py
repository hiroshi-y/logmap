"""Parser for Turbo HAMLOG's Hamlog.mst master file.

Hamlog.mst is a dBASE III file shipped with Turbo HAMLOG that maps the
internal CODE (what HAMLOG calls a JCC/JCG code — note this is *not* the
JARL standard JCC numbering) to a human-readable QTH string and the exact
latitude/longitude of the city/ward.

Field layout (verified against hiroshi-y's live Hamlog.mst):

    offset  len  name   notes
      0      1    -     delete mark (0x20 = active)
      1      6    CODE  6-char code (trailing spaces)
      7     34    QTH   prefecture + city in Shift_JIS
     41      1    FLG   flag
     42      2    HED   2-byte "front" character in Shift_JIS
     44      1    ERIA  JARL area (1..0)
     45      3    CFM   confirmed bitmap
     48      2    WKD   worked bitmap
     50      6    IDO   lat_deg, lat_min, lat_sec, lon_deg, lon_min, lon_sec
                         (each byte is an unsigned integer; DMS encoding)

Unlike standard JARL numbering (13=Tokyo, 25=Shiga, ...) HAMLOG uses its
own area codes such as 1301 = 埼玉県浦和市, 2001 = 愛知県名古屋市, 2309 =
滋賀県甲賀市, etc. Always look up CODE via this parser, never assume a
prefix mapping.
"""

from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MstEntry:
    """A single HAMLOG master-file entry."""
    code: str
    qth: str
    latitude: float
    longitude: float
    area: str  # JARL area number as printable ASCII


def _decode_sjis(raw: bytes) -> str:
    raw = raw.split(b"\x00")[0]
    try:
        return raw.decode("cp932").rstrip(" \u3000\t")
    except (UnicodeDecodeError, ValueError):
        return raw.decode("latin-1", errors="replace").strip()


def _dms_to_decimal(raw: bytes) -> tuple[float, float] | None:
    """Decode a 6-byte DMS IDO field to (lat, lon).

    Byte layout: [lat_deg, lat_min, lat_sec, lon_deg, lon_min, lon_sec].
    Returns None if the record has no coordinates (all zeros).
    """
    if len(raw) < 6:
        return None
    lat_d, lat_m, lat_s, lon_d, lon_m, lon_s = raw[:6]
    if lat_d == 0 and lon_d == 0:
        return None
    lat = lat_d + lat_m / 60 + lat_s / 3600
    lon = lon_d + lon_m / 60 + lon_s / 3600
    return (lat, lon)


class HamlogMst:
    """Parses Hamlog.mst and answers CODE lookups."""

    def __init__(self):
        self._entries: dict[str, MstEntry] = {}

    def load(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            logger.warning("Hamlog.mst not found: %s", filepath)
            return

        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except (IOError, OSError, PermissionError) as e:
            logger.error("Cannot read Hamlog.mst: %s", e)
            return

        if len(data) < 32:
            logger.error("Hamlog.mst too small to be a valid dBASE file")
            return

        rec_count = struct.unpack_from("<I", data, 4)[0]
        header_len = struct.unpack_from("<H", data, 8)[0]
        rec_size = struct.unpack_from("<H", data, 10)[0]
        if header_len == 0 or rec_size == 0:
            logger.error("Hamlog.mst header looks invalid")
            return

        loaded = 0
        for i in range(rec_count):
            rec = data[header_len + i * rec_size : header_len + (i + 1) * rec_size]
            if not rec or rec[0] != 0x20:
                continue

            code = rec[1:7].decode("ascii", errors="replace").strip()
            if not code:
                continue

            qth_raw = rec[7:41]
            # Some entries have annotations after a spaces/asterisks block.
            qth = _decode_sjis(qth_raw).split("*", 1)[0].rstrip()

            ido = rec[50:56]
            coords = _dms_to_decimal(ido)
            if coords is None:
                continue
            lat, lon = coords

            area_byte = rec[44:45]
            area = area_byte.decode("ascii", errors="replace").strip() or "?"

            self._entries[code] = MstEntry(
                code=code,
                qth=qth,
                latitude=lat,
                longitude=lon,
                area=area,
            )
            loaded += 1

        logger.info("Loaded %d entries from Hamlog.mst", loaded)

    def lookup(self, code: str) -> MstEntry | None:
        """Look up a HAMLOG CODE. Trims spaces; tries the literal key only."""
        key = code.strip()
        if not key:
            return None
        return self._entries.get(key)

    def __len__(self) -> int:
        return len(self._entries)
