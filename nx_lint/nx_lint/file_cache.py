## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
from pathlib import Path
from typing import Iterator, Tuple, Optional, Dict

from nx_lint.utils import is_text_file, split_lines


class FileCache:
    def __init__(self):
        self.cache: Dict[str, list[bytes]] = {}
        self.bytes_cache = {}

    def lines_of(self, file_path: Path, enable_filter: bool = True) -> Iterator[Tuple[int, bytes]]:
        """ Returns an iterator of (line_num, line) tuples for the given file path. """
        if not is_text_file(file_path):
            return
        if str(file_path.absolute()) not in self.cache:
            with file_path.open("rb") as fp:
                logging.debug(f"{file_path} not in cache, reading...")
                self.cache[str(file_path.absolute())] = list(split_lines(fp.read()))
        disabled = False
        line_num = 1
        for line in self.cache[str(file_path.absolute())]:
            if not (disabled and enable_filter):
                yield line_num, line
            if b"nx_lint: off" in line:
                disabled = True
            elif b"nx_lint: on" in line:
                disabled = False
            line_num += 1

    def cached_contents_of(self, file_path: Path) -> list[bytes]:
        """ Returns the cached contents of the given file in the form of a list of lines. """
        fpath = str(file_path.absolute())
        if fpath not in self.cache:
            with file_path.open("rb") as fp:
                logging.debug(f"{file_path} not in cache, reading...")
                self.cache[fpath] = list(split_lines(fp.read()))
        return self.cache[fpath]

    def bytes_of(self, file_path: Path) -> Optional[bytes]:
        if not is_text_file(file_path):
            return None
        if str(file_path.absolute()) not in self.bytes_cache:
            with file_path.open("rb") as fp:
                self.bytes_cache[str(file_path.absolute())] = fp.read()
        return self.bytes_cache[str(file_path.absolute())]
