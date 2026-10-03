"""Filesystem boundary shared by news generation and publication.

Checks the existing path chain; it is not a concurrent adversarial-filesystem lock.
"""
from pathlib import Path
import os
import re
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]
NEWS_SCOPE = 'news-only-v1'
NEWS_TOP = {'news.json', 'status.json', 'stream.json', 'stream-status.json', 'events.json',
            'source-health.json', 'deepread.json', 'weekly.json', 'signals.json'}


def owns(name):
    if not isinstance(name, str) or '\\' in name or Path(name).as_posix() != name:
        return False
    if name == 'feed.xml':
        return True
    path = Path(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    if len(path.parts) == 2 and path.parts[0] == 'data':
        return path.name in NEWS_TOP
    if len(path.parts) != 3 or path.parts[0] != 'data':
        return False
    folder, file = path.parts[1:]
    if folder in {'archive', 'deepread'}:
        if file == 'index.json' or (folder == 'archive' and file == 'search-index.json'):
            return True
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', file):
            try:
                datetime.fromisoformat(file[:-5])
                return True
            except ValueError:
                return False
        if folder == 'archive' and re.fullmatch(r'search-\d{4}-\d{2}\.json', file):
            try:
                datetime.fromisoformat(file[7:-5] + '-01')
                return True
            except ValueError:
                return False
    return folder == 'weekly' and bool(re.fullmatch(r'\d{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])\.json', file))


def safe_path(path: Path, *, write=False, allow_releases=False) -> Path:
    raw = Path(path).absolute()
    for entry in [raw, *raw.parents]:
        if entry.is_symlink():
            raise ValueError('News path contains a symbolic link')
    # Normalize consistently only after inspecting the original parent chain.
    path = Path(os.path.abspath(raw))
    if 'classics' in path.parts or 'research' in path.parts or path.name == 'research.json':
        raise ValueError('News path enters a paper namespace')
    if not allow_releases and 'releases' in path.parts:
        raise ValueError('News output cannot enter immutable releases')
    if path.is_relative_to(REPO):
        relative = path.relative_to(REPO)
        parts = relative.parts
        allowed = bool(parts) and parts[0] == '.build'
        if parts and parts[0] == 'public':
            public_name = Path(*parts[1:]).as_posix()
            allowed = (len(parts) == 1 or public_name in {'data', 'data/archive', 'data/deepread',
                       'data/weekly', 'data/release.json'} or owns(public_name))
            if allow_releases and len(parts) >= 2 and parts[1] == 'releases':
                suffix = Path(*parts[3:]).as_posix()
                allowed = (len(parts) <= 3 or suffix in {'manifest.json', 'data', 'data/archive',
                           'data/deepread', 'data/weekly'} or owns(suffix))
        if not allowed:
            raise ValueError('News path enters trusted repository inputs')
    for entry in [path, *path.parents]:
        if entry.is_symlink():
            raise ValueError('News path contains a symbolic link')
        if entry != path and entry.exists() and not entry.is_dir():
            raise ValueError('News path has a non-directory parent')
    if write and path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError('News output has multiple hard links')
    return path
