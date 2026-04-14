"""Turbo HAMLOG Hamlog.hdb writer - updates individual fields in existing records.

Used to back-fill grid squares that were missing from FT8/WSJT-X logged QSOs
after being resolved via the QRZ.com XML API.

Only overwrites a single field (GL by default) of a single record; never
truncates or reorders the file.  Uses Win32 CreateFileW with maximum share
access so HAMLOG (started with `-S`) and Dropbox can continue using the file.
"""

import ctypes
import ctypes.wintypes
import logging
import time

from .hamlog_reader import HamlogReader

logger = logging.getLogger(__name__)

_GENERIC_WRITE = 0x40000000
_GENERIC_READ = 0x80000000
_FILE_SHARE_ALL = 0x07
_OPEN_EXISTING = 3
_FILE_BEGIN = 0

_WRITE_RETRIES = 10
_WRITE_RETRY_DELAY = 0.5

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
    ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
    ctypes.wintypes.HANDLE,
]
_kernel32.SetFilePointer.restype = ctypes.wintypes.DWORD
_kernel32.SetFilePointer.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.wintypes.LONG,
    ctypes.POINTER(ctypes.wintypes.LONG), ctypes.wintypes.DWORD,
]
_kernel32.WriteFile.restype = ctypes.wintypes.BOOL
_kernel32.WriteFile.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
_INVALID_HANDLE = ctypes.wintypes.HANDLE(-1).value


def _win32_write(path: str, offset: int, data: bytes) -> None:
    handle = _kernel32.CreateFileW(
        path, _GENERIC_READ | _GENERIC_WRITE, _FILE_SHARE_ALL,
        None, _OPEN_EXISTING, 0, None,
    )
    if handle == _INVALID_HANDLE:
        err = ctypes.get_last_error()
        raise PermissionError(
            f"CreateFileW(write) failed for {path} (win32 error {err})"
        )
    try:
        _kernel32.SetFilePointer(handle, offset, None, _FILE_BEGIN)
        written = ctypes.wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(data, len(data))
        ok = _kernel32.WriteFile(
            handle, buf, len(data), ctypes.byref(written), None,
        )
        if not ok or written.value != len(data):
            err = ctypes.get_last_error()
            raise OSError(f"WriteFile failed (wrote {written.value}/{len(data)}, err {err})")
    finally:
        _kernel32.CloseHandle(handle)


class HamlogWriter:
    """Write individual fields back to a Turbo HAMLOG .hdb file."""

    def __init__(self, reader: HamlogReader):
        self._reader = reader

    def update_grid(self, record_index: int, grid: str) -> bool:
        """Write *grid* (ASCII) to the GL field of record *record_index*.

        Returns True on success, False otherwise.  The grid is upper-cased
        and space-padded / truncated to the field length (6 bytes).
        """
        if record_index is None or record_index < 0:
            return False
        if not grid:
            return False

        layout = self._reader.get_layout()
        if not layout:
            logger.warning("Cannot load HDB layout; aborting grid writeback")
            return False
        header_len, record_size, fields = layout

        gl_off = gl_len = None
        for name, off, flen in fields:
            if name == "GL":
                gl_off, gl_len = off, flen
                break
        if gl_off is None:
            logger.warning("GL field not found in HDB layout")
            return False

        payload = grid.strip().upper().encode("ascii", errors="replace")
        payload = payload[:gl_len].ljust(gl_len, b" ")
        file_offset = header_len + record_index * record_size + gl_off

        path = self._reader.filepath
        for attempt in range(_WRITE_RETRIES):
            try:
                _win32_write(path, file_offset, payload)
                logger.info(
                    "HDB writeback: record=%d GL=%r", record_index, payload,
                )
                return True
            except (PermissionError, OSError) as e:
                if attempt == _WRITE_RETRIES - 1:
                    logger.error("Grid writeback failed: %s", e)
                    return False
                time.sleep(_WRITE_RETRY_DELAY)
        return False
