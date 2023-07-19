import os
import re
from pathlib import Path
from typing import Collection, List, NamedTuple, Union, Optional

from ._make_trademarks_re import make_trademarks_re
from ._repo_check_config import RepoCheckConfig

_boundary_re = re.compile(
    r'(?<=[a-z])(?=[A-Z])|'
    r'(?<=[A-Z])(?=[a-z])|'
    r'(?<=_)|'
    r'\b')
_case_re = re.compile(r'[A-Z]?(?:[a-z_]+\b)|(?:[A-Z_]+\b)')
_offensive_re = re.compile(
    r'crazy|awful|stolen|shit|stupid|silly|ugly|hack|blya|fuck|porn|huy|huj|hui|zheppa|wtf|'
    r'(?<!s)hell(?!o)|mess(?!age|aging)',
    flags=re.IGNORECASE)
_trademarks_re = make_trademarks_re(Path(__file__).parent / 'organization_domains.txt')
_license_words_re = re.compile(
    r'\b(copyright|gpl\b)',
    flags=re.IGNORECASE)
_disclosure_words_re = re.compile(
    r'protect|activat|licens|signature',
    flags=re.IGNORECASE)
_mpl = (
    'Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/')
_trademark_exceptions_re = re.compile(
    r'updates\.networkoptix\.com|com/networkoptix/nxwitness|spaceX|Google {0,1}Test|\"mts\"|'
    r'application/x-noptix-[\w-]+|google-services\.json|GoogleService-Info\.plist|InitGoogleMock|'
    r'sub_pic_cpb_params_in_pic_timing_sei_flag|SEI_MSG|sei_payload|github.com/google/googletest|'
    r'googletest|groups.google.com|hanwha_edge1|dw_edge2|Network Optix <support@networkoptix.com>|'
    r'networkoptix-metavms|nx_copyright_owner \"Network Optix\"|networkoptix.atlassian.net')
_license_words_exceptions_re = re.compile(
    r'\"copyright\"|\bcopyright_identification_|\b1 - Copyrighted\.(?:\s|$)|'
    r'nx_copyright \"Copyright \(c\)|nx_copyright_owner \"Network Optix\"')


class WordSearchResult(NamedTuple):
    stem_start: str
    stem: str
    word: str


class WordError:

    def __init__(self, path: str, line_idx: int, search_result: WordSearchResult, reason: str):
        self.path = path
        self.line = line_idx + 1
        self.col = search_result.stem_start + 1
        self.word = search_result.word
        self.stem = search_result.stem
        self.reason = reason

    @property
    def word_quoted(self):
        if self.stem != self.word:
            return f'`{self.word}` (stem `{self.stem}`)'
        return f'`{self.word}`'

    def __repr__(self):
        return f"{self.path}:{self.line}:{self.col}: {self.reason} word: {self.word_quoted}"

    def to_string(self, relative_to: Path = None) -> str:
        path = str(Path(self.path).relative_to(relative_to)) if relative_to else self.path
        return f"{path}:{self.line}:{self.col}: {self.reason} word: {self.word_quoted}"


class LineError:

    def __init__(self, path, line_idx, actual, expected):
        self.path = path
        self.line = line_idx + 1
        self.actual = actual
        self.expected = expected

    def __repr__(self):
        return f"{self.path}:{self.line}: line is \"{self.actual}\" expected \"{self.expected}\""

    def to_string(self, relative_to: Path = None) -> str:
        path = str(Path(self.path).relative_to(relative_to)) if relative_to else self.path
        return f"{path}:{self.line}: line is \"{self.actual}\" expected \"{self.expected}\""


class FileError:

    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f"{self.path}: unknown file type"

    def to_string(self, relative_to: Path = None) -> str:
        path = str(Path(self.path).relative_to(relative_to)) if relative_to else self.path
        return f"{path}: unknown file type"


def _get_word_by_substring(line: str, start: int, end: int) -> str:
    """Check if a substring is a meaningful part of a word and return the whole word"""
    # Check if the substring is in one case except maybe the first letter which can be capitalized.
    if not _case_re.match(line, start, end):
        return ""
    if not _boundary_re.match(line, start) and not _boundary_re.match(line, end):
        return ""
    full_word_start = start - m.start() if (m := re.search(r"\W", line[:start][::-1])) else 0
    full_word_end = end + m.start() if (m := re.search(r"\W", line[end:])) else len(line)
    return line[full_word_start:full_word_end]


def _find_offensive_words(line):
    for m in _offensive_re.finditer(line):
        if full_word := _get_word_by_substring(line, m.start(), m.end()):
            yield WordSearchResult(m.start(), m.group(), full_word)


def _find_disclosure_words(line: str):
    for m in _disclosure_words_re.finditer(line):
        if full_word := _get_word_by_substring(line, m.start(), m.end()):
            yield WordSearchResult(m.start(), m.group(), full_word)


def _find_trademarks(line, consider_exceptions=True):
    for m in _trademarks_re.finditer(line):
        if consider_exceptions and _is_a_trademark_exception(line, m):
            continue
        words = m.group().split(' ')
        if len(words) > 1 or any([words == [elem] for elem in line.split(' ')]):
            yield WordSearchResult(m.start(), m.group(), m.group())
        # The pattern found is not a whole word.
        elif full_word := _get_word_by_substring(line, m.start(), m.end()):
            yield WordSearchResult(m.start(), m.group(), full_word)


def _is_a_trademark_exception(line, match):
    for exception in _trademark_exceptions_re.finditer(line):
        if exception.start() <= match.start() and match.end() <= exception.end():
            return True
    return False


def _find_license_words(line):
    for m in _license_words_re.finditer(line):
        if not _is_a_license_word_exception(line, m):
            yield WordSearchResult(m.start(), m.group(), m.group())


def _is_a_license_word_exception(line, match):
    for exception in _license_words_exceptions_re.finditer(line):
        if exception.start() <= match.start() and match.end() <= exception.end():
            return True
    return False


def is_check_needed(path: Path, repo_config: RepoCheckConfig, repo_root: Path = None):
    check_path = path.relative_to(repo_root) if repo_root else path
    opensource_roots = repo_config.opensource_roots
    if opensource_roots and not any(check_path.is_relative_to(d) for d in opensource_roots):
        return False

    if any(check_path.is_relative_to(d) for d in repo_config.excluded_dirs):
        return False

    if any(check_path == p for p in repo_config.excluded_file_paths):
        return False

    if any(check_path.match(p) for p in repo_config.excluded_file_name_patterns):
        return False

    return True


def check_file_if_needed(
        path: str,
        repo_config: RepoCheckConfig = None,
        repo_root: Path = None) -> Optional[Collection[Union[WordError, LineError, FileError]]]:

    def _check_has_mpl(
            line_idx: int, prefix: str, postfix: str = '', dry_run: bool = False) -> bool:
        line = lines[line_idx] if len(lines) > line_idx else None
        expected = prefix + _mpl + postfix
        if line != expected:
            if not dry_run:
                errors.append(LineError(path, line_idx, line, expected))
            return False

        return True

    def _check_has_empty_line(line_idx):
        if line_idx >= len(lines):
            return
        line: str = lines[line_idx]
        if line != '':
            errors.append(LineError(path, line_idx, line, ''))

    def _check_has_shebang():
        allowed_shebangs = ['#!/bin/bash', '#!/bin/bash -e']
        if lines[0] not in allowed_shebangs:
            errors.append(LineError(path, 0, lines[0], ' or '.join(allowed_shebangs)))

    def _check_no_bad_words(
            start_line_idx: int = 0,
            end_line_idx: Optional[int] = None,
            license_words: bool = True,
            consider_trademark_exceptions: bool = True,
            expected_mpl_line_idx: Optional[int] = None):
        # Skip the bad words check for the Copyright line.
        skip_line_idx: Optional[int] = None
        if expected_mpl_line_idx is not None:
            if len(lines) > expected_mpl_line_idx:
                if _mpl in lines[expected_mpl_line_idx]:
                    skip_line_idx = expected_mpl_line_idx

        new_errors = _check_words(
            lines=lines,
            start_line_idx=start_line_idx,
            end_line_idx=end_line_idx,
            license_words=license_words,
            consider_trademark_exceptions=consider_trademark_exceptions,
            path=path,
            skip_line_idx=skip_line_idx)
        errors.extend(new_errors)

    if not is_check_needed(path=path, repo_config=repo_config, repo_root=repo_root):
        return None

    errors: List[Union[WordError, LineError, FileError]] = []

    lines: List[str] = []
    with open(path, encoding="latin1") as f:
        lines = f.read().splitlines()

    # There are certain files that contain no lines, such as .keep files which is a convention to
    # keep empty directories in git.
    if not lines:
        return None

    name = path.name
    stem, ext = os.path.splitext(name)
    if ext == '.in':  # .in files are preprocessed with CMake, where it evaluates its variables.
        name = stem
        stem, ext = os.path.splitext(name)

    cpp_like = {
        '.h', '.cpp', '.c', '.mm', '.ts', '.js', '.mjs', '.txt', '.inc', '.go', '.qml',
        '.java', '.gradle'
    }

    # Files of some types can have a shebang. If the file has it, start searching for the license
    # string from the third line instead of the first one; the second line must be empty.
    if lines[0].startswith('#!'):
        _check_has_empty_line(line_idx=1)
        mpl_license_line = 2
    else:
        mpl_license_line = 0

    if name in {'CMakeLists.txt', 'Doxyfile', 'Dockerfile'} or ext == '.cmake':
        _check_has_mpl(line_idx=mpl_license_line, prefix='## ')
        _check_has_empty_line(line_idx=mpl_license_line+1)
        _check_no_bad_words(start_line_idx=mpl_license_line+2)
    elif ext in {'.json', '.yaml', '.yml'}:
        # TODO: Consider removing mpl check for these types of files.
        mpl_line_idx = 0 if _check_has_mpl(line_idx=0, prefix='## ', dry_run=True) else None
        _check_no_bad_words(expected_mpl_line_idx=mpl_line_idx)
    elif ext == '.md':
        _check_has_empty_line(line_idx=1)
        _check_has_mpl(line_idx=2, prefix='// ')
        _check_no_bad_words(expected_mpl_line_idx=2, license_words=(name != 'readme.md'))
    elif ext in cpp_like:
        _check_has_mpl(line_idx=0, prefix='// ')
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext in {'.sh', '.py'} or name in {'applauncher', 'prerm', 'postinst', 'client'}:
        # TODO: Improve this check: extend the list of the allowed shebangs to include python
        # files, add checking of the presence of the empty line after the shebang to
        # _check_has_shebang().
        if ext != '.py':
            _check_has_shebang()
        _check_has_empty_line(line_idx=1)
        _check_has_mpl(line_idx=2, prefix='## ')
        _check_no_bad_words(expected_mpl_line_idx=2)
    elif ext == '.bat':
        _check_has_mpl(line_idx=0, prefix=':: ')
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.applescript':
        _check_has_mpl(line_idx=0, prefix='-- ')
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.html':
        _check_has_mpl(line_idx=0, prefix='<!-- ', postfix=' -->')
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.css':
        _check_has_mpl(line_idx=0, prefix='/* ', postfix=' */')
        _check_no_bad_words(start_line_idx=2)
    else:
        errors.append(FileError(path))

    return errors


def _check_words(
        lines: List[str],
        start_line_idx: int,
        end_line_idx: Optional[int] = None,
        license_words: bool = True,
        disclosure_words: bool = False,
        consider_trademark_exceptions: bool = True,
        path: Path = None,
        skip_line_idx: Optional[int] = None,
        ) -> List[WordError]:

    if start_line_idx >= len(lines):
        return []
    if end_line_idx is None or end_line_idx > len(lines):
        end_line_idx = len(lines)
    errors = []
    for line_idx in range(start_line_idx, end_line_idx):
        if line_idx == skip_line_idx:
            continue
        if license_words:
            for search_result in _find_license_words(lines[line_idx]):
                errors.append(WordError(path, line_idx, search_result, 'license'))
        if disclosure_words:
            for word_search_result in _find_disclosure_words(lines[line_idx]):
                errors.append(WordError(
                    path,
                    line_idx,
                    word_search_result,
                    'implementation disclosure'))
        for word_search_result in _find_trademarks(lines[line_idx], consider_trademark_exceptions):
            errors.append(WordError(path, line_idx, word_search_result, 'trademark'))
        for word_search_result in _find_offensive_words(lines[line_idx]):
            errors.append(WordError(path, line_idx, word_search_result, 'offensive'))

    return errors


def check_text(
        text: str,
        license_words: bool = True,
        disclosure_words: bool = True) -> Collection[WordError]:
    return _check_words(
        lines=text.splitlines(),
        start_line_idx=0,
        license_words=license_words,
        disclosure_words=disclosure_words)
