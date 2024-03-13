## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest
from .mock_file_cache import MockFileCache


@pytest.fixture
def binary_cache():
    def _create(data):
        return MockFileCache(bytes_data=data)

    return _create


@pytest.fixture
def lines_cache():
    def _create(lines):
        return MockFileCache(lines=lines)

    return _create
