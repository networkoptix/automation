## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from source_file_compliance._source_file_compliance import _find_trademarks, _get_config_path


def test_trademark_exceptions():
    trademark_exceptions = [
        (case.split(' ', 1)[0][:-1], case.split(' ', 1)[1])
        for case in _get_config_path(
            'test_cases/trademark_exceptions.txt').read_text().splitlines()]
    for [expected, text] in trademark_exceptions:
        assert bool(list(_find_trademarks(text))) == (expected == 'positive')
