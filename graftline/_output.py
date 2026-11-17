"""Publish complete owned bytes without replacing another output."""
import os
from pathlib import Path
import secrets
import sys


def publish_bytes(path, data, *, mode=0o600):
    path = Path(path)
    temporary = path.parent / ('.graftline-' + secrets.token_hex(16) + '.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    published = False
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        published = True
    finally:
        try:
            os.unlink(temporary)
        except OSError as error:
            if not published:
                raise
            print(f'Complete output published at {path}; staging cleanup failed at {temporary}: {error}', file=sys.stderr)
