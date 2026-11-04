"""Saving a file whole or not at all, the one way the engine does it.

The text goes to a temporary file of its own beside the file, then is moved over it, so that a
reader never sees half a file and two saves at once never share a temporary name (audit ARCH-04:
each module had written through one fixed `.partial` name, which two saves at once could rename
from under each other).
"""

import os
import tempfile
from pathlib import Path


def write_whole(file_path: Path, contents: str | bytes) -> None:
    """Write a file whole: to a temporary file of its own beside it, then moved over it.

    The folder is made when missing. When the write fails, the file is left as it was and the
    temporary file is removed.

    Args:
        file_path: The file.
        contents: Its text, or its bytes.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=file_path.parent, prefix=f".{file_path.name}."
    )
    temporary_path = Path(temporary_name)
    file_bytes = contents.encode() if isinstance(contents, str) else contents
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(file_bytes)
        temporary_path.replace(file_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
