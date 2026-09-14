"""One advisory lock per live artifact, shared by every runtime that rewrites it.

The routing snapshot and the checkpoint machine block live in the same
``PROJECT.md`` and each writer rewrites the whole file. If each runtime took its
own lock, a gate record and an effect reservation landing at the same moment
would race: the second writer would overwrite the first's block, and the gate
check inside ``checkpoint reserve`` could read a ``PASS`` that a concurrent
``RETRY`` was about to replace. Both runtimes therefore lock the *file*, under
one identity, through this module.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import tempfile


LOCK_ROOT_NAME = "ai-toolkit-artifact-locks"


def lock_root() -> Path:
    return Path(tempfile.gettempdir()) / f"{LOCK_ROOT_NAME}-{os.getuid()}"


@contextmanager
def artifact_lock(path: Path, error: type[Exception]):
    """Hold an exclusive lock keyed by the artifact path for the block's duration.

    ``error`` is the caller's exception type, so a checkpoint caller sees a
    ``CheckpointError`` and a snapshot caller a ``ProjectStateError`` for the
    same unsafe lock directory or file.
    """
    root = lock_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or root.is_symlink():
        raise error("artifact lock directory is unsafe")
    os.chmod(root, 0o700)
    identity = hashlib.sha256(str(path).encode()).hexdigest()
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root / f"{identity}.lock", flags, 0o600)
    try:
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.getuid()
            or lock_metadata.st_nlink != 1
        ):
            raise error("artifact lock file is unsafe")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
