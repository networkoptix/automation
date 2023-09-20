from pathlib import Path
from functools import lru_cache
from typing import Optional, Iterable, Union

from nx_lint.constants import TAB, SPACE, CR, LF

_known_binary_file_types = (
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".tif", ".tiff", ".bmp", ".dib", ".cr2", ".pdf",
    ".exe", ".dll", ".obj", ".pyc", ".pyo", ".so", ".pyd", ".avi", ".mp4", ".mp3", ".wav", ".dump",
    ".jar", ".woff", ".ttf", ".bin", ".eot", ".sqlite", ".mkv", ".snk", ".zip",
)

_known_escape_sequences = {
    0x0A: r"\n",
    0x0D: r"\r",
    0x09: r"\t",
    0x5C: r"\\",
}


@lru_cache(maxsize=None)
def is_text_file(file: Path) -> bool:
    """ Determines if a file is binary by checking a list of known binary extensions.
    """
    return file.suffix not in _known_binary_file_types


@lru_cache(maxsize=None)
def git_repo_root() -> Optional[Path]:
    """ Returns the root of the git repository that contains the current directory, or None if the
        current directory is not in a git repository.
    """
    from subprocess import run, PIPE

    git = run(["git", "rev-parse", "--show-toplevel"], stdout=PIPE, stderr=PIPE)
    if git.returncode == 0:
        return Path(git.stdout.decode().strip())
    # If it failed, we are definitely not in a git repo.
    return None


@lru_cache(maxsize=None)
def is_tracked(file: Path) -> bool:
    """ Returns whether the given file is tracked by git. """
    from subprocess import run, PIPE

    git = run(["git", "ls-files", "--error-unmatch", str(file)], stdout=PIPE, stderr=PIPE)
    return git.returncode == 0


@lru_cache(maxsize=None)
def is_different_from_git_head(file: Path) -> bool:
    """ Returns whether according to git, the given file has modifications that are not staged or
        commited.
    """
    from subprocess import run, PIPE

    git = run(["git", "diff", "--name-only"], stdout=PIPE, stderr=PIPE)
    files = set(Path(line).resolve() for line in git.stdout.decode().splitlines())
    return file.resolve() in files


@lru_cache(maxsize=None)
def is_in_nx_submodule(path: Path) -> bool:
    """ Returns whether the given path is in an nx_submodule. """
    repo = git_repo_root()
    return (path.parent / "_nx_submodule").is_file() or (
        bool(repo)
        and path.parent.resolve() != repo.resolve()
        and is_in_nx_submodule(path.parent)
    )


@lru_cache(maxsize=None)
def is_crlf_file(file_path: Path) -> bool:
    """ Returns whether there is a .gitattributes file in the git repo root that mandates CRLF line
        endings for this file. It is performing a glob match (although it's not guaranteed to be
        exactly the same as the glob match performed by git).
    """
    from globmatch import glob_match

    if repo := git_repo_root():
        git_attributes = repo / ".gitattributes"
        if git_attributes.is_file():
            patterns = [
                "**/" + line.split(" ")[0]
                for line in git_attributes.read_text().splitlines()
                if "eol=crlf" in line
            ]
            return glob_match(file_path, patterns)
    return False


def is_tab_or_space(char: int) -> bool:
    """ Returns whether the given character is a Tab or Space. """
    return char in (TAB, SPACE)


def is_ascii_printable(char: int) -> bool:
    return 32 <= char < 127


def split_lines(text: bytes) -> Iterable[bytes]:
    """ Generator that splits the given text into lines, preserving line endings.
        re.split is almost capable of doing the same, but it does not preserve the line endings,
        or preserves them as separate lines. The line endings are preserved because the rules
        operate line-by-line.
    """
    line_start = 0
    for index, b in enumerate(text):
        # We don't need to check for CR, because breaking after LF covers CR+LF as well.
        if b == LF:
            yield text[line_start:index+1]
            line_start = index + 1
    if line_start < len(text):
        # When this is true, it means that the last line does not end with a LF.
        yield text[line_start:]


def as_bytes(*char_codes: int) -> bytes:
    """ Convert a character to a byte string. """
    return b"".join(bytes((c,)) for c in char_codes)


def escape_ascii_char(char: Union[bytes, int]) -> str:
    if type(char) not in (bytes, int):
        raise TypeError("Value must be a bytes object or an int")
    if type(char) is int:
        char = bytes((char,))
    if len(char) != 1:
        raise ValueError("Value must be a single ASCII character")

    code = ord(char)
    if code in _known_escape_sequences:
        return _known_escape_sequences[code]
    elif is_ascii_printable(code):
        return char.decode("ascii")
    else:
        return f"\\x{code:02X}"


def escape_unicode_char(char: str) -> str:
    if type(char) is not str:
        raise TypeError("Value must be a str object")
    if len(char) != 1:
        raise ValueError("Value must be a single character")

    code = ord(char)
    if code < 0x80:
        return escape_ascii_char(code)
    elif code <= 0xFFFF:
        return f"\\u{code:04X}"
    else:
        return f"\\U{code:08X}"
