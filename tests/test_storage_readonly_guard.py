"""Static guard: application code must never call write operations on S3/fsspec."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "open_csi_publisher"
FORBIDDEN = re.compile(
    r"\.(put|put_file|pipe|pipe_file|rm|rm_file|mkdir|makedirs|touch|mv|cp_file|copy"
    r"|put_object|delete_object|upload_file|write_bytes)\(|open\([^)]*[\"'][wax]"
)


def test_storage_module_has_no_write_operations():
    text = (SRC / "storage.py").read_text(encoding="utf-8")
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)


def test_storage_module_opens_files_read_only():
    text = (SRC / "storage.py").read_text(encoding="utf-8")
    opens = re.findall(r"\.open\((.*)\)$", text, re.M)
    assert opens and all(o.strip().endswith('"rb"') for o in opens), opens
