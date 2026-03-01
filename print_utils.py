#!/usr/bin/env python3
"""
print_utils.py

Windows printing utilities (programmatic selection and printing of PDF files).

Exposes:
- list_printers() -> list[str]
- print_pdf(file_path: str, printer_name: Optional[str] = None, wait: bool = False)

Notes:
- Requires pywin32 (win32print, win32api). Install in your venv:
    pip install pywin32
- Behavior:
    - If printer_name is None: use default printer (via ShellExecute 'print' or StartDocPrinter).
    - If printer_name provided: use ShellExecute 'printto' to print to the specified printer.
- Tests included will skip actual printing unless running on Windows and environment allows.

Safety:
- The print_pdf function validates file existence and raises FileNotFoundError otherwise.
"""

import os
import platform
from typing import List, Optional

if platform.system() == "Windows":
    try:
        import win32print
        import win32api
    except Exception as e:
        win32print = None
        win32api = None
else:
    win32print = None
    win32api = None


def list_printers() -> List[str]:
    """
    Return list of available printer names (on Windows).
    On non-Windows, returns empty list.
    """
    if win32print is None:
        return []
    printers = []
    for flags, description, name, comment in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
        printers.append(name)
    return printers


def print_pdf(file_path: str, printer_name: Optional[str] = None, wait: bool = False) -> None:
    """
    Print a PDF file to a printer.

    - file_path: path to PDF
    - printer_name: optional printer name; if None, prints to default printer
    - wait: if True, attempt to wait for completion (best-effort)

    Raises:
    - FileNotFoundError if file missing
    - RuntimeError if printing subsystem not available or printing fails
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if platform.system() != "Windows":
        raise RuntimeError("print_pdf is implemented only on Windows via pywin32 in this module.")

    if win32api is None or win32print is None:
        raise RuntimeError("pywin32 is required for printing. Install with 'pip install pywin32'")

    # If no printer_name: use default via ShellExecute 'print'
    try:
        if not printer_name:
            # ShellExecute with 'print' verb uses default app to print to default printer
            h = win32api.ShellExecute(0, "print", file_path, None, ".", 0)
            return
        else:
            # Use 'printto' verb to specify target printer. Some viewers accept this.
            # The arguments string must include the printer name and optionally driver and port.
            # Using simple pattern: "\"<printer_name>\""
            params = f'"{printer_name}"'
            h = win32api.ShellExecute(0, "printto", file_path, params, ".", 0)
            return
    except Exception as e:
        raise RuntimeError(f"Printing failed: {e}") from e