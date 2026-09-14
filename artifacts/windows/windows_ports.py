"""Native Windows primitives for the forthcoming installer manager.

Uses the same creation-time-qualified stop event as Framework and deployment.
No PID-only termination, console control broadcast, shell, or taskkill fallback.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as wt
import os
from pathlib import Path
import re
import socket
import struct
import time

if os.name != 'nt':
    raise ImportError('windows_ports requires native Windows')

k32 = ctypes.WinDLL('kernel32', use_last_error=True)


def _api(name, result, *arguments):
    function = getattr(k32, name)
    function.restype, function.argtypes = result, arguments
    return function


_open_process = _api('OpenProcess', wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_close = _api('CloseHandle', wt.BOOL, wt.HANDLE)
_wait = _api('WaitForSingleObject', wt.DWORD, wt.HANDLE, wt.DWORD)
_times = _api('GetProcessTimes', wt.BOOL, wt.HANDLE, *([ctypes.POINTER(wt.FILETIME)] * 4))
_image = _api('QueryFullProcessImageNameW', wt.BOOL, wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
_open_event = _api('OpenEventW', wt.HANDLE, wt.DWORD, wt.BOOL, wt.LPCWSTR)
_set_event = _api('SetEvent', wt.BOOL, wt.HANDLE)
_create_file = _api('CreateFileW', wt.HANDLE, wt.LPCWSTR, wt.DWORD, wt.DWORD,
                    wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE)
_attributes = _api('GetFileAttributesW', wt.DWORD, wt.LPCWSTR)
_tcp_table = ctypes.WinDLL('iphlpapi', use_last_error=True).GetExtendedTcpTable
_tcp_table.restype = wt.DWORD
_tcp_table.argtypes = [wt.LPVOID, ctypes.POINTER(wt.DWORD), wt.BOOL, wt.ULONG, ctypes.c_int, wt.ULONG]


def _listeners(family):
    size = wt.DWORD()
    # OWNER_PID_LISTENER returns only active listeners, never TIME_WAIT sockets.
    result = _tcp_table(None, ctypes.byref(size), False, family, 3, 0)
    if result not in (0, 122):
        raise ctypes.WinError(result)
    for attempt in range(5):
        buffer = ctypes.create_string_buffer(size.value)
        result = _tcp_table(buffer, ctypes.byref(size), False, family, 3, 0)
        if result == 122:  # Table changed while allocating the buffer.
            continue
        if result:
            raise ctypes.WinError(result)
        data = buffer.raw
        count = struct.unpack_from('<I', data)[0]
        width = 24 if family == socket.AF_INET else 56
        if 4 + count * width > len(data):
            raise RuntimeError('Invalid Windows TCP table size')
        for index in range(count):
            row = data[4 + index*width:4 + (index+1)*width]
            if family == socket.AF_INET:
                address = socket.inet_ntop(family, row[4:8])
                port = struct.unpack_from('!H', row, 8)[0]
            else:
                address = socket.inet_ntop(family, row[:16])
                port = struct.unpack_from('!H', row, 20)[0]
            yield address, port
        return
    raise RuntimeError('Windows TCP listener table kept changing; retry preflight')


def _error():
    return ctypes.WinError(ctypes.get_last_error())


@contextmanager
def directory_lock(root):
    """Exclusive non-inheritable file handle; released even after a process crash.

    Keep the marker after closing so a second manager cannot acquire a different
    file while the first still holds its lock. Windows denies deletion while open.
    """
    root = Path(root).absolute()
    marker = root / '.semantic-management.lock'
    for path in (marker, root, *root.parents):
        attributes = _attributes(str(path))
        if attributes == 0xFFFFFFFF:
            if ctypes.get_last_error() not in (2, 3):
                raise _error()
        elif attributes & 0x400:
            raise RuntimeError(f'Reparse points are not supported in the installation path: {path}')
    handle = _create_file(str(marker), 0xC0000000, 0, None, 4, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise _error()
    try:
        yield
    finally:
        _close(handle)


def check_port(port, host='127.0.0.1'):
    """Reject an active Windows listener, including one using SO_REUSEADDR."""
    # Windows permits a specific-address listener alongside an existing reusable
    # wildcard listener. Exclusive bind alone does not detect that conflict.
    for family in (socket.AF_INET, socket.AF_INET6):
        for address, active_port in _listeners(family):
            if active_port == port and (host == '0.0.0.0' or address in ('0.0.0.0', '::', host, '::ffff:'+host)):
                raise RuntimeError(f'Port {host}:{port} already has an active listener')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((host, port))
            listener.listen(1)
        except OSError as error:
            raise RuntimeError(f'Port {host}:{port} is unavailable; choose another component port') from error


@contextmanager
def _process(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or not 0 < pid <= 0xFFFFFFFF:
        raise ValueError('Invalid process ID')
    handle = _open_process(0x1000 | 0x100000, False, pid)
    if not handle:
        error = _error()
        if error.winerror == 87:
            yield None
            return
        raise error
    try:
        result = _wait(handle, 0)
        if result == 0xFFFFFFFF:
            raise _error()
        yield handle if result == 258 else None
    finally:
        _close(handle)


def _record(pid, handle):
    created, exited, kernel, user = (wt.FILETIME() for _ in range(4))
    if not _times(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
        raise _error()
    buffer = ctypes.create_unicode_buffer(32768)
    size = wt.DWORD(len(buffer))
    if not _image(handle, 0, buffer, ctypes.byref(size)):
        raise _error()
    return {'pid': pid, 'created': f'{created.dwHighDateTime:08x}{created.dwLowDateTime:08x}',
            'executable': str(Path(buffer.value).resolve())}


def process_record(pid):
    with _process(pid) as handle:
        return _record(pid, handle) if handle else None


def _matches(actual, expected):
    return actual['created'] == expected['created'] and (
        os.path.normcase(actual['executable']) == os.path.normcase(expected['executable']))


def stop(record, timeout=20):
    """Request graceful stop and wait using a held process handle.

    A missing endpoint or timeout preserves the running process and caller's
    state. Creation time plus executable identity protects stale PID records.
    """
    if not re.fullmatch('[0-9a-f]{16}', record.get('created', '')) or not Path(record.get('executable', '')).is_absolute():
        raise ValueError('Missing process creation/executable identity')
    if not 0 < timeout <= 3600:
        raise ValueError('Invalid stop timeout')
    with _process(record['pid']) as handle:
        if not handle:
            return
        if not _matches(_record(record['pid'], handle), record):
            raise RuntimeError('Process identity changed; refusing stop')
        name = f"Local\\InsightOS.Semantic.Stop.{record['pid']}.{record['created']}"
        deadline = time.monotonic() + min(2, timeout)
        while True:
            event = _open_event(2, False, name)
            if event:
                break
            error = _error()
            if error.winerror != 2 or time.monotonic() >= deadline:
                raise RuntimeError('Graceful stop endpoint unavailable; process preserved') from error
            time.sleep(0.02)
        try:
            if not _set_event(event):
                raise _error()
        finally:
            _close(event)
        result = _wait(handle, int(timeout * 1000))
        if result == 258:
            raise TimeoutError('Graceful stop timed out; process and state must be preserved')
        if result != 0:
            raise _error()
