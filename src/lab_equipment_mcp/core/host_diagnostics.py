from __future__ import annotations

import ctypes.util
from pathlib import Path


def find_visa_libraries() -> list[str]:
    candidates = [
        Path(r"C:\Windows\System32\visa32.dll"),
        Path(r"C:\Windows\System32\visa64.dll"),
        Path(r"C:\Windows\SysWOW64\visa32.dll"),
        Path(r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\visa64.dll"),
        Path(r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin\visa32.dll"),
    ]
    found = [str(path) for path in candidates if path.exists()]
    for library in ("visa32", "visa64"):
        resolved = ctypes.util.find_library(library)
        if resolved and resolved not in found:
            found.append(resolved)
    return found
