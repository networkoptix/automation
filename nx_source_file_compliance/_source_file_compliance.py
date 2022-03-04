import os
import re
from pathlib import Path
from typing import Collection, List, Union

from ._make_trademarks_re import make_trademarks_re
from ._generic_repo_check_config import RepoCheckConfig

_boundary_re = re.compile(
    r'(?<=[a-z])(?=[A-Z])|'
    r'(?<=[A-Z])(?=[a-z])|'
    r'(?<=_)|'
    r'\b')
_case_re = re.compile(
    r'[A-Z][a-z]+|'
    r'[a-z]+|'
    r'[A-Z]+')
_offensive_re = re.compile(
    r'crazy|awful|stolen|shit|stupid|silly|ugly|hack|blya|fuck|porn|huy|huj|hui|zheppa|wtf|'
    r'(?<!s)hell(?!o)|mess(?!age|aging)',
    flags=re.IGNORECASE)
_trademarks_re = make_trademarks_re(Path(__file__).parent / 'organization_domains.txt')
_license_words_re = re.compile(
    r'\b(copyright|gpl\b)',
    flags=re.IGNORECASE)
_mpl = (
    'Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/')
_trademark_exceptions_re = re.compile(
    r'com/networkoptix/nxwitness|spaceX|Nvidia (Tegra|GPU|GeForce)|Google {0,1}Test|'
    r'application/x-noptix-[\w-]+|google-services\.json|GoogleService-Info\.plist|InitGoogleMock|'
    r'\"mts\"|SEI UNIT|Bad SEI detected. SEI too short|skip this sei message|'
    r'github.com/google/googletest|googletest|groups.google.com|developer.download.nvidia.com|'
    r'nx_copyright_owner \"Network Optix\"|networkoptix.atlassian.net')
_license_words_exceptions_re = re.compile(
    r'\"copyright\"|\bcopyright_identification_|\b1 - Copyrighted\.(?:\s|$)|'
    r'nx_copyright \"Copyright \(c\)|nx_copyright_owner \"Network Optix\"')


class WordError:

    def __init__(self, path, line_idx, match, reason):
        self.path = path
        self.line = line_idx + 1
        self.col = match.start() + 1
        self.word = match.group()
        self.reason = reason

    def __repr__(self):
        return f"{self.path}:{self.line}:{self.col}: {self.reason} word: \"{self.word}\""


class LineError:

    def __init__(self, path, line_idx, actual, expected):
        self.path = path
        self.line = line_idx + 1
        self.actual = actual
        self.expected = expected

    def __repr__(self):
        return f"{self.path}:{self.line}: line is \"{self.actual}\" expected \"{self.expected}\""


class FileError:

    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f"{self.path}: unknown file type"


def _is_a_morpheme(line, start, end):
    """Tell if a substring is a meaningful part of a word"""
    # The full string is necessary to check for boundary based on letter case.
    case_ok = _case_re.fullmatch(line, start, end) is not None
    is_prefix = _boundary_re.match(line, start) is not None
    is_suffix = _boundary_re.match(line, end) is not None
    return case_ok and (is_prefix or is_suffix)


def _find_offensive_words(line):
    for m in _offensive_re.finditer(line):
        if _is_a_morpheme(line, m.start(), m.end()):
            yield m


def _find_trademarks(line, consider_exceptions=True):
    for m in _trademarks_re.finditer(line):
        if consider_exceptions and _is_a_trademark_exception(line, m):
            continue
        words = m.group().split(' ')
        if len(words) > 1:
            yield m
        # Can't use _is_a_morpheme() for words like 'InParas', 'AgileVision', 'IncoreSoft' etc.
        # In case if match is a full word just yielding it
        elif any([words == [elem] for elem in line.split(' ')]):
            yield m
        elif _is_a_morpheme(line, m.start(), m.end()):
            yield m


def _is_a_trademark_exception(line, match):
    for exception in _trademark_exceptions_re.finditer(line):
        if exception.start() <= match.start() and match.end() <= exception.end():
            return True
    return False


def _find_license_words(line):
    for m in _license_words_re.finditer(line):
        if not _is_a_license_word_exception(line, m):
            yield m


def _is_a_license_word_exception(line, match):
    for exception in _license_words_exceptions_re.finditer(line):
        if exception.start() <= match.start() and match.end() <= exception.end():
            return True
    return False


def is_check_needed(
        path: str, repo_config: RepoCheckConfig):
    opensource_roots = repo_config["opensource_roots"]
    if opensource_roots and not any(path.startswith(f"{d}/") for d in opensource_roots):
        return False

    if any(d for d in repo_config["excluded_dirs"] if path.startswith(f"{d}/")):
        return False

    if path in repo_config["excluded_file_paths"]:
        return False

    file_path_object = Path(path)
    for pattern in repo_config["excluded_file_name_patterns"]:
        if file_path_object.match(pattern):
            return False

    return True


def check_file_content(path, content) -> Collection[Union[WordError, LineError, FileError]]:

    def _check_mpl(line_idx, prefix, postfix=''):
        line = lines[line_idx]
        expected = prefix + _mpl + postfix
        if line != expected:
            errors.append(LineError(path, line_idx, line, expected))

    def _check_words(
            start_line_idx,
            end_line_idx=None,
            license_words=True,
            consider_trademark_exceptions=True,
            ):
        if end_line_idx is None:
            end_line_idx = len(lines)
        for line_idx in range(start_line_idx, end_line_idx):
            if license_words:
                for m in _find_license_words(lines[line_idx]):
                    errors.append(WordError(path, line_idx, m, 'license'))
            for m in _find_trademarks(lines[line_idx], consider_trademark_exceptions):
                errors.append(WordError(path, line_idx, m, 'trademark'))
            for m in _find_offensive_words(lines[line_idx]):
                errors.append(WordError(path, line_idx, m, 'offensive'))

    def _check_empty(line_idx):
        line = lines[line_idx]
        if line != '':
            errors.append(LineError(path, line_idx, line, ''))

    def _check_shebang():
        allowed_shebangs = ['#!/bin/bash', '#!/bin/bash -e']
        if lines[0] not in allowed_shebangs:
            errors.append(LineError(path, 0, lines[0], ' or '.join(allowed_shebangs)))

    errors: List[Union[WordError, LineError, FileError]] = []

    lines = content.splitlines()
    name = path.name
    stem, ext = os.path.splitext(name)
    if ext == '.in':  # .in files are preprocessed with CMake, where it evaluates its variables.
        name = stem
        stem, ext = os.path.splitext(name)
    if name in {'CMakeLists.txt', 'Doxyfile'} or ext in {'.cmake', '.yaml', '.yml'}:
        _check_mpl(line_idx=0, prefix='## ')
        _check_words(start_line_idx=1)
    elif ext == '.md':
        _check_words(start_line_idx=0, end_line_idx=1)
        _check_empty(line_idx=1)
        _check_mpl(line_idx=2, prefix='// ')
        if name == 'readme.md':
            _check_words(start_line_idx=3, license_words=False)
        else:
            _check_words(start_line_idx=3)
    elif ext in {'.h', '.cpp', '.c', '.mm', '.ts', '.js', '.txt', '.inc', '.go', '.qml'}:
        _check_mpl(line_idx=0, prefix='// ')
        _check_empty(line_idx=1)
        if ext in {'.h', '.cpp', '.inc'}:
            _check_words(start_line_idx=2)
        else:
            _check_words(start_line_idx=2)
    elif ext in {'.sh', '.py'} or name in {'applauncher', 'prerm', 'postinst', 'client'}:
        if ext == '.py':
            _check_words(start_line_idx=0, end_line_idx=1)
        else:
            _check_shebang()
        _check_empty(line_idx=1)
        _check_mpl(line_idx=2, prefix='## ')
        _check_words(start_line_idx=3)
    elif ext == '.bat':
        _check_mpl(line_idx=0, prefix=':: ')
        _check_words(start_line_idx=1)
    elif ext == '.applescript':
        _check_mpl(line_idx=0, prefix='-- ')
        _check_empty(line_idx=1)
        _check_words(start_line_idx=2)
    elif ext == '.html':
        _check_mpl(line_idx=0, prefix='<!-- ', postfix=' -->')
        _check_empty(line_idx=1)
        _check_words(start_line_idx=2)
    else:
        errors.append(FileError(path))

    return errors
