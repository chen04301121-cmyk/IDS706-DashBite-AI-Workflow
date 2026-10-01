"""Publish complete files to polling readers with a same-directory rename."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_output(destination: Path):
    """Readers see the old complete file or the new one, never a partial write."""
    destination = Path(destination)
    fd, name = tempfile.mkstemp(prefix=".pending-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
