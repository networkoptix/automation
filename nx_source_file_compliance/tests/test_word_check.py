## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import unittest

from source_file_compliance._make_trademarks_re import get_trademarks_from_file
from source_file_compliance._source_file_compliance import (
    _find_offensive_words,
    _find_trademarks,
    _find_license_words,
    _find_disclosure_words,
    _get_config_path,
)

_offensive_words_criteria_reference = [
    (case.split(' ', 1)[1], case.split(' ', 1)[0][:-1])
    for case in _get_config_path('test_cases/offensive_words.txt').read_text().splitlines()]

_trademarks_criteria_reference = [
    (case.split(' ', 1)[1], case.split(' ', 1)[0][:-1])
    for case in _get_config_path('test_cases/trademarks.txt').read_text().splitlines()] + (
    [
        (trademark, 'positive')
        for trademark in get_trademarks_from_file(
            _get_config_path('organization_domains.txt'),
            _get_config_path('trademark_common_words.txt').read_text().splitlines())
    ])

_license_words_criteria_reference = [
    (case.split(' ', 1)[1], case.split(' ', 1)[0][:-1])
    for case in _get_config_path('test_cases/license_words.txt').read_text().splitlines()]

_disclosure_words_criteria_reference = [
    (case.split(' ', 1)[1], case.split(' ', 1)[0][:-1])
    for case in _get_config_path('test_cases/disclosure_words.txt').read_text().splitlines()]


class TestFindWords(unittest.TestCase):

    def _check_correctness(self, func, words_reference):
        for [phrase, verdict] in words_reference:
            words = [*func(phrase)]
            with self.subTest(phrase=phrase, verdict=verdict):
                if verdict == 'positive':
                    self.assertTrue(words, msg=f'False negative for "{phrase}"')
                else:
                    self.assertListEqual(words, [], msg=f'False positive for "{phrase}"')

    def test_offensive_search(self):
        self._check_correctness(_find_offensive_words, _offensive_words_criteria_reference)

    def test_trademark_search(self):
        self._check_correctness(_find_trademarks, _trademarks_criteria_reference)

    def test_license_words_search(self):
        self._check_correctness(_find_license_words, _license_words_criteria_reference)

    def test_implementation_disclosure_words_search(self):
        self._check_correctness(_find_disclosure_words, _disclosure_words_criteria_reference)
