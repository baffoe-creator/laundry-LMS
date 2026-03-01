import os
import sys
import platform
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import print_utils

def test_list_printers_runs():
    printers = print_utils.list_printers()
    # On non-Windows, it will be empty list; on Windows at least list returns something (maybe empty)
    assert isinstance(printers, list)

def test_print_pdf_missing_file_raises():
    # attempt to print a non-existent file -> should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        print_utils.print_pdf("this_file_does_not_exist_012345.pdf")

@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only test")
def test_print_pdf_no_printer_raises_or_runs(tmp_path):
    # This test attempts to print a small dummy file. We won't actually check the printer spooler.
    dummy = tmp_path / "dummy.txt"
    dummy.write_text("dummy")
    # If pywin32 not installed, print_pdf should raise RuntimeError
    try:
        printers = print_utils.list_printers()
    except Exception:
        printers = []
    # If no printers available, still calling print_pdf should attempt to use default and might succeed or raise
    # We call and expect no crash (but can't assert spooling). If system lacks pywin32, RuntimeError is expected.
    if platform.system() == "Windows":
        try:
            print_utils.print_pdf(str(dummy))
        except RuntimeError:
            pytest.skip("pywin32 not available or printing not supported in this environment")