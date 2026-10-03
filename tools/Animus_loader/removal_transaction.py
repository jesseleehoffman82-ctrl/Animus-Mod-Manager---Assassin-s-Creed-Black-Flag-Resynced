"""Disk-backed rollback of owned files/ranges during a removal operation."""
import json
import shutil
import tempfile
from pathlib import Path


class RemovalTransaction:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='remove-', dir=root))
        self.entries = []
        self.keys = set()

    def capture(self, path, offset=None, length=None):
        path = Path(path).resolve()
        key = (str(path), offset, length)
        if key in self.keys:
            return
        self.keys.add(key)
        exists = path.is_file()
        if offset is not None and not exists:
            raise OSError(f'Missing archive: {path}')
        saved = self.root / str(len(self.entries))
        size = path.stat().st_size if exists else None
        if exists:
            if offset is None:
                shutil.copyfile(path, saved)
            else:
                if offset < 0 or length < 0 or offset + length > size:
                    raise OSError(f'Invalid restore range in {path}')
                with path.open('rb') as src, saved.open('wb') as dst:
                    src.seek(offset)
                    left = length
                    while left:
                        block = src.read(min(left, 1024 * 1024))
                        if not block:
                            raise OSError(f'Short read in {path}')
                        dst.write(block)
                        left -= len(block)
        self.entries.append(dict(path=str(path), saved=str(saved), offset=offset,
                                 length=length, size=size, exists=exists))
        (self.root / 'recovery.json').write_text(json.dumps(self.entries, indent=2))

    def rollback(self):
        failures = []
        for e in reversed(self.entries):
            path = Path(e['path'])
            try:
                if e['offset'] is not None:
                    with path.open('r+b') as dst, Path(e['saved']).open('rb') as src:
                        dst.truncate(e['size'])
                        dst.seek(e['offset'])
                        shutil.copyfileobj(src, dst)
                elif e['exists']:
                    shutil.copyfile(e['saved'], path)
                else:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f'{path}: {exc}')
        if failures:
            raise OSError(f'Recovery incomplete; backups retained at {self.root}: ' + '; '.join(failures))

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)
