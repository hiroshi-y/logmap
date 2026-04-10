"""Turbo HAMLOG Hamlog.hdb reader.

Hamlog.hdb is a dBASE III compatible file. The header begins at offset 0
and contains record-count, header-length and record-size (see dBASE spec).
Field descriptors follow the 32-byte file header and are terminated by 0x0D.

Field layout (as present in Turbo HAMLOG Ver5.x Hamlog.hdb, confirmed against
hiroshi-y's live file):

    offset  len type name
       0      1   -   delete mark (0x20 = active, 0x2A = deleted)
       1      6   C   CALLS   (first 6 chars, indexed)
       7     14   C   IGN     (rest of the 20-byte callsign column,
                               contains portable suffix like "/3")
      21      4   B   DATE   [century, yy, mm, dd]
      25      2   B   TIME   [hh, mm | 0x80 for UTC]
      27      6   C   CODE   (JCC/JCG)
      33      6   C   GL     (grid locator)
      39      3   C   QSL
      42      2   C   FLAG
      44      3   C   HIS    (RST sent)
      47      3   C   MY     (RST rcvd)
      50      7   C   FREQ
      57      4   C   MODE
      61     12   C   NAME
      73     28   C   QTH    (Shift_JIS)
     101     54   C   RMK1   (Shift_JIS)
     155     54   C   RMK2   (Shift_JIS)

IMPORTANT: Turbo HAMLOG opens Hamlog.hdb with exclusive access by default.
To allow external readers (like LogMap), start HAMLOG with the `-S` switch,
e.g. `Hamlogw.exe -S`. See the HAMLOG50 API documentation for details.
"""

import ctypes
import ctypes.wintypes
import logging
import os
import struct
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# dBASE header constants
DBASE_HEADER_BASE = 32  # size of the file header before field descriptors
DBASE_FIELD_SIZE = 32   # size of each field descriptor
DBASE_HEADER_TERMINATOR = 0x0D

# Record delete marker: 0x20 = active, 0x2A = deleted
DELETE_MARK_ACTIVE = 0x20

# Retry settings for file access (Dropbox sync can briefly lock the file)
_OPEN_RETRIES = 5
_OPEN_RETRY_DELAY = 0.3  # seconds

# Windows API constants
_GENERIC_READ = 0x80000000
_FILE_SHARE_ALL = 0x07  # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
_OPEN_EXISTING = 3
_FILE_BEGIN = 0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Properly type CreateFileW so the HANDLE comparison works on both
# 32-bit and 64-bit Python (default restype is c_int which breaks the
# INVALID_HANDLE_VALUE check).
_kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    ctypes.wintypes.LPCWSTR,  # lpFileName
    ctypes.wintypes.DWORD,    # dwDesiredAccess
    ctypes.wintypes.DWORD,    # dwShareMode
    ctypes.c_void_p,          # lpSecurityAttributes
    ctypes.wintypes.DWORD,    # dwCreationDisposition
    ctypes.wintypes.DWORD,    # dwFlagsAndAttributes
    ctypes.wintypes.HANDLE,   # hTemplateFile
]
_kernel32.GetFileSize.restype = ctypes.wintypes.DWORD
_kernel32.GetFileSize.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.wintypes.DWORD)]
_kernel32.SetFilePointer.restype = ctypes.wintypes.DWORD
_kernel32.SetFilePointer.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LONG, ctypes.POINTER(ctypes.wintypes.LONG), ctypes.wintypes.DWORD]
_kernel32.ReadFile.restype = ctypes.wintypes.BOOL
_kernel32.ReadFile.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

_INVALID_HANDLE = ctypes.wintypes.HANDLE(-1).value


def _win32_read(path: str, offset: int = 0, size: int | None = None) -> bytes:
    """Read bytes from a file using Win32 API with maximum sharing.

    Bypasses Python's file-object layer entirely to avoid fd/handle
    lifetime issues.  Uses ``CreateFileW`` with full sharing so the file
    can be read while HAMLOG and Dropbox both hold it open.
    """
    handle = _kernel32.CreateFileW(
        path, _GENERIC_READ, _FILE_SHARE_ALL,
        None, _OPEN_EXISTING, 0, None,
    )
    if handle == _INVALID_HANDLE:
        err = ctypes.get_last_error()
        raise PermissionError(
            f"CreateFileW failed for {path} (win32 error {err})"
        )
    try:
        if size is None:
            size = _kernel32.GetFileSize(handle, None)
            if size == 0xFFFFFFFF:
                return b""
            size = max(0, size - offset)
        if offset:
            _kernel32.SetFilePointer(handle, offset, None, _FILE_BEGIN)
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.wintypes.DWORD(0)
        _kernel32.ReadFile(handle, buf, size, ctypes.byref(bytes_read), None)
        return buf.raw[: bytes_read.value]
    finally:
        _kernel32.CloseHandle(handle)


@dataclass
class HamlogQso:
    """A single QSO record from Turbo HAMLOG."""
    callsign: str
    date: str           # YYYY/MM/DD
    time_on: str        # HH:MM (UTC if utc=True)
    utc: bool
    band: str           # e.g. "7", "14", "144"
    mode: str           # e.g. "CW", "SSB", "FT8"
    rst_sent: str
    rst_rcvd: str
    qth: str
    name: str
    remarks: str
    jcc_code: str
    gl: str             # grid locator
    frequency: str      # raw frequency text (e.g. "7.075")

    @property
    def datetime_str(self) -> str:
        return f"{self.date} {self.time_on}{'Z' if self.utc else ''}"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _decode_ascii(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("ascii", errors="replace").strip()


def _decode_sjis(raw: bytes) -> str:
    raw = raw.split(b"\x00")[0]
    try:
        return raw.decode("cp932").strip()
    except (UnicodeDecodeError, ValueError):
        return raw.decode("latin-1", errors="replace").strip()


def _format_date(raw: bytes) -> str:
    """Decode the 4-byte date field [century, yy, mm, dd] -> 'YYYY/MM/DD'."""
    if len(raw) < 4 or raw[0] == 0:
        return ""
    century, yy, mm, dd = raw[0], raw[1], raw[2], raw[3]
    if mm == 0 or dd == 0:
        return ""
    year = century * 100 + yy
    return f"{year:04d}/{mm:02d}/{dd:02d}"


def _format_time(raw: bytes) -> tuple[str, bool]:
    """Decode the 2-byte time field [hh, mm | 0x80=UTC] -> ('HH:MM', is_utc)."""
    if len(raw) < 2:
        return ("", False)
    hour = raw[0] & 0x3F
    minute_byte = raw[1]
    is_utc = bool(minute_byte & 0x80)
    minute = minute_byte & 0x7F
    if hour > 23 or minute > 59:
        return ("", is_utc)
    return (f"{hour:02d}:{minute:02d}", is_utc)


def _freq_to_band(freq_text: str) -> str:
    """Map a frequency text (MHz) to the conventional amateur band label."""
    try:
        freq_mhz = float(freq_text)
    except (TypeError, ValueError):
        return freq_text.strip() or "?"
    bands = [
        (0.5,    "135k"),
        (2.0,    "1.8"),
        (4.0,    "3.5"),
        (6.0,    "5"),
        (8.0,    "7"),
        (12.0,   "10"),
        (15.5,   "14"),
        (19.0,   "18"),
        (22.0,   "21"),
        (26.0,   "24"),
        (30.0,   "28"),
        (55.0,   "50"),
        (148.0,  "144"),
        (450.0,  "430"),
        (1300.0, "1200"),
        (2500.0, "2400"),
        (5900.0, "5600"),
    ]
    for upper, label in bands:
        if freq_mhz < upper:
            return label
    return "SHF"


# ---------------------------------------------------------------------------
# HamlogReader
# ---------------------------------------------------------------------------

class HamlogReader:
    """Read QSOs from a Turbo HAMLOG Hamlog.hdb file (dBASE III format)."""

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._header_len: int = 0
        self._record_size: int = 0
        self._fields: list[tuple[str, int, int]] = []  # (name, offset, length)
        self._header_loaded = False

    @property
    def filepath(self) -> str:
        return self._filepath

    @staticmethod
    def _read_with_retry(path: str, offset: int = 0, size: int | None = None) -> bytes:
        """Read bytes from file via Win32 shared mode, with retry."""
        for attempt in range(_OPEN_RETRIES):
            try:
                return _win32_read(path, offset, size)
            except PermissionError:
                if attempt == _OPEN_RETRIES - 1:
                    raise
                time.sleep(_OPEN_RETRY_DELAY)
        return b""

    # ---- Header / structure ------------------------------------------------

    def _load_header(self) -> bool:
        """Parse the dBASE header to learn record layout. Returns True on success."""
        if self._header_loaded:
            return True
        if not os.path.exists(self._filepath):
            return False
        try:
            data = self._read_with_retry(self._filepath)
            if len(data) < DBASE_HEADER_BASE:
                return False

            header_len = struct.unpack_from("<H", data, 8)[0]
            record_size = struct.unpack_from("<H", data, 10)[0]
            if header_len <= DBASE_HEADER_BASE or record_size < 1:
                return False

            # Read field descriptors from header area
            fields: list[tuple[str, int, int]] = []
            field_offset = 1  # byte 0 in each record is the delete mark
            pos = DBASE_HEADER_BASE
            while pos + DBASE_FIELD_SIZE <= len(data):
                if data[pos] == DBASE_HEADER_TERMINATOR:
                    break
                fd = data[pos: pos + DBASE_FIELD_SIZE]
                name = fd[:11].split(b"\x00")[0].decode("ascii", errors="replace")
                flen = fd[16]
                fields.append((name, field_offset, flen))
                field_offset += flen
                pos += DBASE_FIELD_SIZE

            self._header_len = header_len
            self._record_size = record_size
            self._fields = fields
            self._header_loaded = True
            logger.info(
                "HDB header: header_len=%d, record_size=%d, fields=%d",
                header_len, record_size, len(fields),
            )
            return True
        except (IOError, OSError, PermissionError) as e:
            logger.error(
                "Cannot open Hamlog.hdb (%s). Is HAMLOG started with '-S'?", e,
            )
            return False

    def _field(self, name: str) -> tuple[int, int] | None:
        for fname, off, flen in self._fields:
            if fname == name:
                return (off, flen)
        return None

    # ---- Public record API -------------------------------------------------

    def get_record_count(self) -> int:
        """Return the number of *active* (non-deleted) records in the file."""
        if not self._load_header():
            return 0
        try:
            file_size = os.path.getsize(self._filepath)
        except OSError:
            return 0
        if file_size <= self._header_len:
            return 0
        raw_count = (file_size - self._header_len) // self._record_size
        return max(0, raw_count)

    def read_record(self, index: int) -> HamlogQso | None:
        if not self._load_header():
            return None
        try:
            offset = self._header_len + index * self._record_size
            data = self._read_with_retry(self._filepath, offset, self._record_size)
        except (IOError, OSError, PermissionError) as e:
            logger.error("Read error on record %d: %s", index, e)
            return None
        if len(data) < self._record_size:
            return None
        return self._parse_record(data)

    def read_last_n_records(self, n: int) -> list[HamlogQso]:
        total = self.get_record_count()
        if total == 0:
            return []
        start = max(0, total - n)
        return self._read_range(start, total)

    def read_records_from(self, start_index: int) -> list[HamlogQso]:
        total = self.get_record_count()
        if start_index >= total:
            return []
        return self._read_range(start_index, total)

    # ---- Internals ---------------------------------------------------------

    def _read_range(self, start: int, stop: int) -> list[HamlogQso]:
        records: list[HamlogQso] = []
        if not self._load_header():
            return records
        try:
            offset = self._header_len + start * self._record_size
            size = (stop - start) * self._record_size
            block = self._read_with_retry(self._filepath, offset, size)
        except (IOError, OSError, PermissionError) as e:
            logger.error("Read error in range %d..%d: %s", start, stop, e)
            return records

        rsize = self._record_size
        for i in range(0, len(block), rsize):
            data = block[i:i + rsize]
            if len(data) < rsize:
                break
            qso = self._parse_record(data)
            if qso:
                records.append(qso)
        return records

    def _get(self, data: bytes, name: str) -> bytes:
        loc = self._field(name)
        if not loc:
            return b""
        off, flen = loc
        return data[off:off + flen]

    def _parse_record(self, data: bytes) -> HamlogQso | None:
        # Skip deleted records
        if not data or data[0] != DELETE_MARK_ACTIVE:
            return None

        # HAMLOG stores the base callsign in CALLS(6) and the portable
        # suffix — without the slash — right-aligned in IGN(14). For
        # example JO3OPP/3 is stored as CALLS="JO3OPP", IGN="             3".
        # Reassemble as "CALLS/IGN" when IGN is non-empty.
        base = _decode_ascii(self._get(data, "CALLS"))
        suffix = _decode_ascii(self._get(data, "IGN"))
        if not base:
            return None
        callsign = f"{base}/{suffix}" if suffix else base

        date_raw = self._get(data, "DATE")
        time_raw = self._get(data, "TIME")
        date_str = _format_date(date_raw)
        time_str, is_utc = _format_time(time_raw)

        freq_text = _decode_ascii(self._get(data, "FREQ"))
        mode = _decode_ascii(self._get(data, "MODE")).upper()

        return HamlogQso(
            callsign=callsign.upper(),
            date=date_str,
            time_on=time_str,
            utc=is_utc,
            band=_freq_to_band(freq_text),
            mode=mode,
            rst_sent=_decode_ascii(self._get(data, "HIS")),
            rst_rcvd=_decode_ascii(self._get(data, "MY")),
            qth=_decode_sjis(self._get(data, "QTH")),
            name=_decode_sjis(self._get(data, "NAME")),
            remarks=_decode_sjis(self._get(data, "RMK1")),
            jcc_code=_decode_ascii(self._get(data, "CODE")),
            gl=_decode_ascii(self._get(data, "GL")),
            frequency=freq_text,
        )
