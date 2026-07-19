from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class FileRecord:
    """In-memory record of one raw source file, as tracked by the file/data index
    (implementation_plan.md §6). `file_role` distinguishes the single actively-appended
    `live` file from `archived` files (LoggerNet `_Historical` or `.backup` rollovers),
    which are parsed once and never touched again once `status` is `closed`.
    """

    file_name: str
    file_role: Literal["live", "archived"]
    size: int
    time_start: datetime | None
    time_end: datetime | None
    variables: list[str]
    status: Literal["active", "closed"]
