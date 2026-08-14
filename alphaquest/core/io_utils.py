from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write *data* atomically in the same directory as *path*.

    Quest books are edited in-place and a power loss/app crash during write should
    never leave a half-written SNBT/JSON5 file.  A temporary sibling file is fully
    flushed and then moved over the destination with os.replace(), which is atomic
    on supported local filesystems.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    try:
        mode = path.stat().st_mode
    except OSError:
        pass

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8", newline: str | None = "\n") -> None:
    if newline is not None:
        # Normalize line endings before encoding. This keeps generated files stable
        # across Windows/Linux without changing embedded escaped newlines.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if newline != "\n":
            text = text.replace("\n", newline)
    atomic_write_bytes(Path(path), text.encode(encoding))
