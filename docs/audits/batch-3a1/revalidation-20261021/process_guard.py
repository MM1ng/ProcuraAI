"""Narrow Windows subprocess audit argument normalization (no process launches)."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re

_split = ctypes.windll.shell32.CommandLineToArgvW
_split.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
_split.restype = ctypes.POINTER(wintypes.LPWSTR)
_free = ctypes.windll.kernel32.LocalFree
_free.argtypes = [wintypes.HLOCAL]
_free.restype = wintypes.HLOCAL


def normalize(argv):
    if isinstance(argv, str):
        count = ctypes.c_int()
        pointer = _split(argv, ctypes.byref(count))
        if not pointer:
            raise ValueError("Invalid Windows command line")
        try:
            return [pointer[i] for i in range(count.value)]
        finally:
            _free(ctypes.cast(pointer, wintypes.HLOCAL))
    return list(argv)


def allowed_process(executable, argv, root):
    args = normalize(argv)
    if not args:
        return None
    binary = args[0].lower()
    if executable is not None and str(executable).lower() not in {binary, binary + ".exe"}:
        return None
    if binary in {"whoami", "whoami.exe"} and args[1:] == ["/user", "/fo", "csv", "/nh"]:
        return {"name": "whoami", "purpose": "identity ACL setup; stdout not published"}
    if binary not in {"icacls", "icacls.exe"} or len(args) != 6:
        return None
    path = Path(args[1]).resolve()
    if not path.is_relative_to(root.resolve()) or args[2:4] != ["/inheritance:r", "/grant:r"]:
        return None
    if not re.fullmatch(r"\*S-1-(?:\d+-)*\d+:\(OI\)\(CI\)F", args[4]):
        return None
    if args[5] != "*S-1-5-18:(OI)(CI)F":
        return None
    return {"name": "icacls", "purpose": "ACL only under isolated runtime", "path": str(path)}
