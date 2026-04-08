"""Turbo HAMLOG .hdb file reader.

Turbo HAMLOG stores QSO records in a fixed-length binary file format (.hdb).
Each record is a fixed number of bytes. The file has a header followed by records.

Reference: Turbo HAMLOG record format (Hamlog50.hdb)
- Header: 2048 bytes
- Each record: 256 bytes (Turbo HAMLOG v5)

Record fields (offsets are approximate - may need adjustment for specific versions):
"""

import os
import struct
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Turbo HAMLOG v5 constants
HEADER_SIZE = 2048
RECORD_SIZE = 256


@dataclass
class HamlogQso:
    """Represents a single QSO record from Turbo HAMLOG."""
    callsign: str
    date: str           # YYYY/MM/DD
    time_on: str        # HHMM
    band: str           # e.g. "7", "14", "144", "430"
    mode: str           # e.g. "CW", "SSB", "FM", "FT8"
    rst_sent: str
    rst_rcvd: str
    qth: str            # QTH field
    name: str           # Operator name
    remarks: str        # Remarks / notes
    jcc_code: str       # JCC/JCG code
    gl: str             # Grid locator
    frequency: str      # Frequency string

    @property
    def datetime_str(self) -> str:
        return f"{self.date} {self.time_on}"


def _read_fixed_string(data: bytes, offset: int, length: int,
                       encoding: str = "shift_jis") -> str:
    """Read a fixed-length string from binary data, stripping null bytes."""
    raw = data[offset:offset + length]
    # Strip null bytes and trailing spaces
    raw = raw.split(b"\x00")[0]
    try:
        return raw.decode(encoding).strip()
    except (UnicodeDecodeError, ValueError):
        try:
            return raw.decode("latin-1").strip()
        except (UnicodeDecodeError, ValueError):
            return ""


class HamlogReader:
    """Reader for Turbo HAMLOG .hdb files."""

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._record_count = 0

    @property
    def filepath(self) -> str:
        return self._filepath

    def get_record_count(self) -> int:
        """Get the total number of records in the file."""
        if not os.path.exists(self._filepath):
            return 0
        file_size = os.path.getsize(self._filepath)
        if file_size <= HEADER_SIZE:
            return 0
        return (file_size - HEADER_SIZE) // RECORD_SIZE

    def read_record(self, index: int) -> HamlogQso | None:
        """Read a single QSO record by index (0-based)."""
        try:
            with open(self._filepath, "rb") as f:
                offset = HEADER_SIZE + index * RECORD_SIZE
                f.seek(offset)
                data = f.read(RECORD_SIZE)
                if len(data) < RECORD_SIZE:
                    return None
                return self._parse_record(data)
        except (IOError, OSError) as e:
            logger.error("Error reading record %d: %s", index, e)
            return None

    def read_last_n_records(self, n: int) -> list[HamlogQso]:
        """Read the last N records from the file."""
        total = self.get_record_count()
        if total == 0:
            return []

        start = max(0, total - n)
        records = []

        try:
            with open(self._filepath, "rb") as f:
                for i in range(start, total):
                    offset = HEADER_SIZE + i * RECORD_SIZE
                    f.seek(offset)
                    data = f.read(RECORD_SIZE)
                    if len(data) < RECORD_SIZE:
                        break
                    qso = self._parse_record(data)
                    if qso and qso.callsign:
                        records.append(qso)
        except (IOError, OSError) as e:
            logger.error("Error reading records: %s", e)

        return records

    def read_records_from(self, start_index: int) -> list[HamlogQso]:
        """Read all records starting from a given index."""
        total = self.get_record_count()
        if start_index >= total:
            return []

        records = []
        try:
            with open(self._filepath, "rb") as f:
                for i in range(start_index, total):
                    offset = HEADER_SIZE + i * RECORD_SIZE
                    f.seek(offset)
                    data = f.read(RECORD_SIZE)
                    if len(data) < RECORD_SIZE:
                        break
                    qso = self._parse_record(data)
                    if qso and qso.callsign:
                        records.append(qso)
        except (IOError, OSError) as e:
            logger.error("Error reading records from %d: %s", start_index, e)

        return records

    def _parse_record(self, data: bytes) -> HamlogQso | None:
        """Parse a single 256-byte record into a HamlogQso.

        Turbo HAMLOG v5 record layout (approximate offsets):
        Offset  Length  Field
        0       12      Callsign
        12      8       Date (YYYYMMDD)
        20      4       Time (HHMM)
        24      4       Band code / Frequency
        28      4       Mode
        32      3       RST Sent
        35      3       RST Received
        38      30      QTH (Shift_JIS)
        68      20      Name (Shift_JIS)
        88      64      Remarks (Shift_JIS)
        152     8       JCC/JCG code
        160     6       Grid Locator
        166     10      Frequency string
        (remaining bytes are padding/reserved)

        NOTE: These offsets are approximate. Actual offsets may vary by
        Turbo HAMLOG version. Adjust as needed.
        """
        try:
            callsign = _read_fixed_string(data, 0, 12, "ascii")
            if not callsign:
                return None

            date_raw = _read_fixed_string(data, 12, 8, "ascii")
            time_raw = _read_fixed_string(data, 20, 4, "ascii")

            # Format date
            date_str = date_raw
            if len(date_raw) == 8:
                date_str = f"{date_raw[:4]}/{date_raw[4:6]}/{date_raw[6:8]}"

            band = _read_fixed_string(data, 24, 4, "ascii")
            mode = _read_fixed_string(data, 28, 4, "ascii")
            rst_sent = _read_fixed_string(data, 32, 3, "ascii")
            rst_rcvd = _read_fixed_string(data, 35, 3, "ascii")
            qth = _read_fixed_string(data, 38, 30, "shift_jis")
            name = _read_fixed_string(data, 68, 20, "shift_jis")
            remarks = _read_fixed_string(data, 88, 64, "shift_jis")
            jcc_code = _read_fixed_string(data, 152, 8, "ascii")
            gl = _read_fixed_string(data, 160, 6, "ascii")
            frequency = _read_fixed_string(data, 166, 10, "ascii")

            return HamlogQso(
                callsign=callsign.upper(),
                date=date_str,
                time_on=time_raw,
                band=self._normalize_band(band, frequency),
                mode=mode.upper(),
                rst_sent=rst_sent,
                rst_rcvd=rst_rcvd,
                qth=qth,
                name=name,
                remarks=remarks,
                jcc_code=jcc_code,
                gl=gl,
                frequency=frequency,
            )
        except Exception as e:
            logger.error("Error parsing record: %s", e)
            return None

    def _normalize_band(self, band: str, frequency: str) -> str:
        """Normalize band designation to standard format."""
        # Try to determine band from frequency if band field is unclear
        band = band.strip()
        if band:
            return band

        # Attempt to parse from frequency
        try:
            freq_mhz = float(frequency)
            if freq_mhz < 0.5:
                return "135k"
            elif freq_mhz < 2:
                return "1.8"
            elif freq_mhz < 4:
                return "3.5"
            elif freq_mhz < 8:
                return "7"
            elif freq_mhz < 11:
                return "10"
            elif freq_mhz < 15:
                return "14"
            elif freq_mhz < 19:
                return "18"
            elif freq_mhz < 22:
                return "21"
            elif freq_mhz < 26:
                return "24"
            elif freq_mhz < 30:
                return "28"
            elif freq_mhz < 55:
                return "50"
            elif freq_mhz < 148:
                return "144"
            elif freq_mhz < 450:
                return "430"
            elif freq_mhz < 1300:
                return "1200"
        except (ValueError, TypeError):
            pass

        return band or "?"
