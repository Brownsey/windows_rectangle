"""Single-instance guard implementations.

`WindowsMutexSingleInstance` uses ctypes -> CreateMutexW; lazy-imports
ctypes inside `acquire()` so the module is importable on non-Windows.
`MemorySingleInstance` is the in-process fallback for tests and dev.
"""

from __future__ import annotations

import logging
import sys

from ..ports.single_instance import DEFAULT_MUTEX_NAME

_log = logging.getLogger(__name__)

# Win32 error: the mutex already existed → another instance is running.
_ERROR_ALREADY_EXISTS = 183


class MemorySingleInstance:
    """Holds a single shared set keyed by mutex name. Single process only —
    fine for tests, useless against an actual second process."""

    _held: set[str] = set()

    def __init__(self, name: str = DEFAULT_MUTEX_NAME) -> None:
        self.name = name
        self._has_lock = False

    def acquire(self) -> bool:
        if self.name in type(self)._held:
            return False
        type(self)._held.add(self.name)
        self._has_lock = True
        return True

    def release(self) -> None:
        if self._has_lock:
            type(self)._held.discard(self.name)
            self._has_lock = False


class WindowsMutexSingleInstance:
    """Real Windows implementation via `CreateMutexW`.

    Acquires a named mutex; if it already exists in the kernel namespace,
    another instance owns it -> acquire() returns False.
    """

    def __init__(self, name: str = DEFAULT_MUTEX_NAME) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsMutexSingleInstance requires Windows")
        self.name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(None, False, self.name)
        err = ctypes.get_last_error()
        if not handle:
            _log.warning("CreateMutexW failed: err=%s", err)
            return False
        if err == _ERROR_ALREADY_EXISTS:
            # We got a handle but didn't create — close it and report failure.
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(self._handle)
        self._handle = None


def best_available(
    name: str = DEFAULT_MUTEX_NAME,
) -> WindowsMutexSingleInstance | MemorySingleInstance:
    if sys.platform == "win32":
        return WindowsMutexSingleInstance(name)
    return MemorySingleInstance(name)
