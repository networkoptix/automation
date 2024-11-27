## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import os
import re
import importlib.resources
from pathlib import Path
from typing import Collection, List, NamedTuple, Union, Optional
from urllib.parse import urlparse

from ._make_trademarks_re import make_trademarks_re
from ._repo_check_config import RepoCheckConfig


def _get_config_path(resource_name: Optional[str] = None) -> Path:
    base_path = (
        Path(os.environ['NX_SOURCE_FILE_COMPLIANCE_CONFIG_DIR'])
        if 'NX_SOURCE_FILE_COMPLIANCE_CONFIG_DIR' in os.environ
        else Path(importlib.resources.files('source_file_compliance')) / 'config')
    return base_path / resource_name if resource_name else base_path


_mpl = (
    'Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/')

# -------------------------------------------------------------------------------------------------
# Auxillary regex patterns.

_boundary_re = re.compile(
    r'(?<=[a-z])(?=[A-Z])|'
    r'(?<=[A-Z])(?=[a-z])|'
    r'(?<=_)|'
    r'\b')
# Simplified pattern to match potential URLs starting with http:// or https://.
_url_re = re.compile(r"http[s]?://[^\s]+")
_case_re = re.compile(r'[A-Z]?(?:[a-z_]+\b)|(?:[A-Z_]+\b)')

# -------------------------------------------------------------------------------------------------
# Configurable regex patterns.

_trademarks_re = make_trademarks_re(_get_config_path())
_trademark_exceptions_re = re.compile(
    '|'.join(_get_config_path('trademark_exception_patterns.txt').read_text().splitlines()))
_disclosure_words_re = re.compile(
    '|'.join(_get_config_path('disclosure_word_patterns.txt').read_text().splitlines()),
    flags=re.IGNORECASE)
_offensive_re = re.compile(
    '|'.join(_get_config_path('offensive_word_patterns.txt').read_text().splitlines()),
    flags=re.IGNORECASE)
_license_words_re = re.compile(
    '|'.join(_get_config_path('license_word_patterns.txt').read_text().splitlines()),
    flags=re.IGNORECASE)
_license_words_exceptions_re = re.compile(
    '|'.join(_get_config_path('license_word_exception_patterns.txt').read_text().splitlines()))


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

    def _message(self, path: Path) -> str:
        return f"{path}:{self.line}:{self.col}: {self.reason} word: {self.word_quoted}"

    def __repr__(self):
        return self._message(self.path)

    def to_string(self, relative_to: Path = None) -> str:
        path = str(Path(self.path).relative_to(relative_to)) if relative_to else self.path
        return self._message(path)


class LineError:

    def __init__(self, path, line_idx, actual, expected):
        self.path = path
        self.line = line_idx + 1
        self.actual = actual
        self.description_of_expected = expected

    def _message(self, path: Path) -> str:
        return (
            f"{path}:{self.line}: line contents are {self.actual!r}, but expected " +
            self.description_of_expected)

    def __repr__(self):
        return self._message(self.path)

    def to_string(self, relative_to: Path = None) -> str:
        path = str(Path(self.path).relative_to(relative_to)) if relative_to else self.path
        return self._message(path)


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


def _is_valid_url(url: str) -> bool:
    try:
        parsed_url = urlparse(url)
        return all([parsed_url.scheme, parsed_url.netloc])
    except ValueError:
        return False


def _is_a_trademark_exception(line, match):
    for exception in _trademark_exceptions_re.finditer(line):
        if exception.start() <= match.start() and match.end() <= exception.end():
            return True
    if url_match := _url_re.search(line):
        # If the match is inside a URL, consider it an exception.
        if _is_valid_url(url_match.group()):
            if url_match.start() <= match.start() and match.end() <= url_match.end():
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

    def _check_has_mpl(line_idx: int, dry_run: bool = False) -> bool:
        line = lines[line_idx] if len(lines) > line_idx else None

        if line is None:
            return False

        if _mpl not in line:
            if not dry_run:
                errors.append(
                    LineError(path, line_idx, line, f"Comment with the contents '{_mpl}'"))
            return False

        # At this point, we know that the line contains the MPL license text, but we need to ensure
        # that it is the only thing on the line, i.e. no other license text is present.
        # The following constant was chosen as a relaxed constraint for all kinds of languages
        # (present and future). The len() check ensures that the line is only longer by a couple of
        # characters that are necessary for signifying a comment in any language (plus some
        # whitespace). Any further deviation is disallowed to avoid e.g. a different license text
        # also being present on the same line.
        COMMENT_CHARS_LEN = 9
        if len(line) > len(_mpl) + COMMENT_CHARS_LEN:
            if not dry_run:
                errors.append(
                    LineError(path, line_idx, line, f"a comment with the contents {_mpl!r}"))
            return False

        return True

    def _check_has_empty_line(line_idx):
        if line_idx >= len(lines):
            return
        line: str = lines[line_idx]
        if line != '':
            errors.append(LineError(path, line_idx, line, 'an empty line'))

    def _has_shebang():
        return lines[0].startswith('#!')

    def _check_has_shebang():
        if not _has_shebang():
            errors.append(LineError(path, 0, lines[0], "a line starting with '#!'"))

    def _check_no_bad_words(
            start_line_idx: int = 0,
            end_line_idx: Optional[int] = None,
            license_words: bool = True,
            expected_mpl_line_idx: Optional[int] = None):
        # Skip the bad words check for the "copyright" line.
        skip_line_idx: Optional[int] = None
        if expected_mpl_line_idx is not None:
            if len(lines) > expected_mpl_line_idx:
                if _mpl in lines[expected_mpl_line_idx]:
                    skip_line_idx = expected_mpl_line_idx

        new_errors = _check_words(
            lines=lines,
            start_line_idx=start_line_idx,
            end_line_idx=end_line_idx,
            should_check_license_words=license_words,
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

    wix_files = {
        '.wxs', '.wxl', '.wxi'
    }

    minimal_check_filetypes = {
        '.properties'
    }

    # Files of some types can have a shebang. If the file has it, start searching for the license
    # string from the third line instead of the first one; the second line must be empty.
    if lines[0].startswith('#!'):
        _check_has_empty_line(line_idx=1)
        mpl_license_line = 2
    else:
        mpl_license_line = 0

    if name in {'CMakeLists.txt', 'Doxyfile', 'Dockerfile'} or ext == '.cmake':
        _check_has_mpl(line_idx=mpl_license_line)
        _check_has_empty_line(line_idx=mpl_license_line + 1)
        _check_no_bad_words(start_line_idx=mpl_license_line + 2)
    elif name == "conanfile.py":
        # We set license_words to False because conan recipes do contain license words
        # legitimately, referring to the license of the package being built.
        if _has_shebang():
            _check_has_empty_line(line_idx=1)
            _check_has_mpl(line_idx=2)
            _check_no_bad_words(expected_mpl_line_idx=2, license_words=False)
        else:
            _check_has_mpl(line_idx=0)
            _check_no_bad_words(start_line_idx=1, license_words=False)
    elif ext in {'.json', '.yaml', '.yml'}:
        # TODO: Consider removing mpl check for these types of files.
        mpl_line_idx = 0 if _check_has_mpl(line_idx=0, dry_run=True) else None
        _check_no_bad_words(expected_mpl_line_idx=mpl_line_idx)
    elif ext == '.md':
        _check_has_empty_line(line_idx=1)
        _check_has_mpl(line_idx=2)
        _check_no_bad_words(expected_mpl_line_idx=2, license_words=(name != 'readme.md'))
    elif ext in cpp_like:
        _check_has_mpl(line_idx=0)
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.xml':
        _check_has_mpl(line_idx=0)
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext in wix_files:
        _check_has_mpl(line_idx=1)
        _check_has_empty_line(line_idx=2)
        _check_no_bad_words(start_line_idx=3)
    elif ext == '.sh' or name in {'applauncher', 'prerm', 'postinst', 'client'}:
        _check_has_shebang()
        _check_has_empty_line(line_idx=1)
        _check_has_mpl(line_idx=2)
        _check_no_bad_words(expected_mpl_line_idx=2)
    elif ext == '.py':
        if _has_shebang():
            _check_has_empty_line(line_idx=1)
            _check_has_mpl(line_idx=2)
            _check_no_bad_words(expected_mpl_line_idx=2)
        else:
            _check_has_mpl(line_idx=0)
            _check_no_bad_words(start_line_idx=1)
    elif ext == '.bat':
        _check_has_mpl(line_idx=0)
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.applescript':
        _check_has_mpl(line_idx=0)
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.html':
        _check_has_mpl(line_idx=0)
        _check_has_empty_line(line_idx=1)
        _check_no_bad_words(start_line_idx=2)
    elif ext == '.css':
        _check_has_mpl(line_idx=0)
        _check_no_bad_words(start_line_idx=2)
    elif ext in minimal_check_filetypes:
        _check_no_bad_words(start_line_idx=0)
    else:
        errors.append(FileError(path))

    return errors


def _check_words(
        lines: List[str],
        start_line_idx: int,
        end_line_idx: Optional[int] = None,
        should_check_license_words: bool = True,
        should_check_disclosure_words: bool = False,
        path: Path = None,
        skip_line_idx: Optional[int] = None) -> List[WordError]:
    if start_line_idx >= len(lines):
        return []
    if end_line_idx is None or end_line_idx > len(lines):
        end_line_idx = len(lines)
    errors = []
    for line_idx in range(start_line_idx, end_line_idx):
        if line_idx == skip_line_idx:
            continue
        if should_check_license_words:
            for search_result in _find_license_words(lines[line_idx]):
                errors.append(WordError(path, line_idx, search_result, 'license'))
        if should_check_disclosure_words:
            for word_search_result in _find_disclosure_words(lines[line_idx]):
                errors.append(WordError(
                    path,
                    line_idx,
                    word_search_result,
                    'implementation disclosure'))
        for word_search_result in _find_trademarks(lines[line_idx]):
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
        should_check_license_words=license_words,
        should_check_disclosure_words=disclosure_words)
