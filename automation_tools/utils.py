## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import datetime
import json
import sys
import traceback

import yaml


class AutomationError(Exception):
    pass


def parse_config_file(filepath: Path):
    if filepath.suffix == '.json':
        def parse_file(f):
            return json.load(f)
    elif filepath.suffix == '.yaml':
        def parse_file(f):
            return yaml.safe_load(f)
    else:
        raise NotImplementedError(f'Unsupported file extension: {filepath}')

    with open(filepath, 'r') as f:
        return parse_file(f)


def config_from_filename(filename: str) -> dict:
    return parse_config_file(Path(filename))


def parse_config_string(config_string: str, type: str):
    if type == "json":
        return json.loads(config_string)
    if type == "yaml":
        return yaml.safe_load(config_string)
    else:
        raise NotImplementedError(f"Unsupported config type: {type}")


def flatten_list(list_of_lists: list):
    return [i for e in list_of_lists for i in (e if isinstance(e, list) else [e])]


class cached:
    def __init__(self, invalidation_period: datetime.timedelta = None):
        self._invalidation_period = invalidation_period

        self._last_update = None
        self._value = None

    def __call__(self, value_generator):
        def wrapped(*args):
            if self._is_value_valid():
                return self._value

            self._value = value_generator(*args)
            self._last_update = datetime.datetime.now()
            return self._value
        return wrapped

    def _is_value_valid(self):
        if self._last_update is None:
            return False
        if self._invalidation_period is None:
            return True

        return datetime.datetime.now() - self._last_update < self._invalidation_period


@dataclass
class User:
    username: str
    name: str = ""
    email: str = ""


def merge_dicts(left: dict, right: dict) -> Iterable[tuple[Any, Any]]:
    """ Recursively merges two dictionaries. Merging happens from left to right. Identical keys,
        when both values are dictionaries, are merged; otherwise the value from the right dict
        is used.
    """
    for key in set(left.keys()) | set(right.keys()):
        if key in left and key in right:
            if isinstance(left[key], dict) and isinstance(right[key], dict):
                yield (key, dict(merge_dicts(left[key], right[key])))
            else:
                yield (key, right[key])
        elif key in left:
            yield (key, left[key])
        else:
            yield (key, right[key])


def get_exception_info(exception: Exception) -> tuple[str, str]:
    # format_exception() interface has been changed in version 3.10.
    if sys.version_info[0] == 3 and sys.version_info[1] < 10:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        stack_trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
    else:
        stack_trace = traceback.format_exception(exception)
    stack_trace_repr = [repr(frame) for frame in stack_trace]
    exception_info = f"{exception.__class__.__name__}: {exception}"
    return (stack_trace_repr, exception_info)
