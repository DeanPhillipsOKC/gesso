"""YAML files read once per process: a stroke card or element file is parsed again only when it changes on disk.

    read(path) -> its parsed contents (a fresh copy each call, so a caller can change it)

publish asked for the stroke cards about 60 times a lesson and parsed all 28 files each time, about half of
publish's time (#87). The answer is the same as yaml.safe_load's: the cache is keyed on the file's path, size, and
modification time, so an edited file is read again.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

_cache: dict[str, tuple[tuple[int, int], object]] = {}


def read(path: Path) -> object:
    path = Path(path)
    st = path.stat()
    key, stamp = str(path.resolve()), (st.st_mtime_ns, st.st_size)
    hit = _cache.get(key)
    if hit is None or hit[0] != stamp:
        hit = (stamp, yaml.safe_load(path.read_text(encoding="utf-8")))
        _cache[key] = hit
    return copy.deepcopy(hit[1])
