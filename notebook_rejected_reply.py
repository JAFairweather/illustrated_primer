"""Private, write-once failed-output evidence; never a reply/recovery authority.

Only the validated transport envelope observer supplies these bytes. Nothing
reads this directory during Respond, recovery or native insertion.
"""
import os
from pathlib import Path
import re
import stat
import tempfile

from notebook_model_transport import MAX_RESPONSE


def retain_rejected_reply(cache, request, raw, folder='rejected-replies'):
    if (not isinstance(request, str) or not re.fullmatch(r'notebook-[0-9a-f]{32}', request)
            or not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RESPONSE):
        raise ValueError('bounded request-bound rejection evidence required')
    directory = Path(cache) / folder
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise ValueError('private rejection directory required')
    # Publish a fully written inode, never a partial final filename. A link is
    # atomic and refuses an existing destination (including a symlink).
    fd, temporary = tempfile.mkstemp(prefix='.rejection-', dir=directory)
    try:
        with os.fdopen(fd, 'wb', buffering=0) as stream:
            remaining = memoryview(raw)
            while remaining:
                count = stream.write(remaining)
                if not count:
                    raise OSError('incomplete rejection evidence write')
                remaining = remaining[count:]
            os.fsync(stream.fileno())
        os.link(temporary, directory / (request+'.json'))
    finally:
        os.unlink(temporary)


def retain_reply(cache, request, raw):
    """The same private write-once copy for an accepted reply, kept for offline replay only."""
    return retain_rejected_reply(cache, request, raw, 'replies')
