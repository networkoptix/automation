#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path, PurePosixPath
import sys

import robocat.rule.helpers.open_source_file_checker


SCRIPT_DESCRIPTION = """
This script is to be used for checking source files for compatibility with Open Source standards
(absence of "bad" words, correc copyright notes etc.)
"""


def check_directory(repo_directory: Path, check_directory: Path, consider_directory_context: bool):
    Checker = robocat.rule.helpers.open_source_file_checker.OpenSourceFileChecker

    logging.info(f"Checking {check_directory}...")
    for entry in check_directory.rglob("*"):
        if entry.is_dir():
            continue

        if consider_directory_context:
            check_path = PurePosixPath(entry.relative_to(repo_directory))
        else:
            check_path = PurePosixPath(entry)

        if Checker.is_check_needed(str(check_path), consider_directory_context):
            logging.debug(f"Checking {entry}...")
            with open(entry, encoding="latin1") as f:
                errors = Checker(file_name=check_path, file_content=f.read()).file_errors()
                if not errors:
                    continue
                errors_as_string = "\n".join(e.raw_text for e in errors)
                logging.info(f"Problems found while checking {entry}:\n{errors_as_string}")
        else:
            logging.debug(f"No check is needed for {check_path}")
    logging.info(f"Done!")


def main():
    parser = argparse.ArgumentParser(
        sys.argv[0], description=SCRIPT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-dir",
        type=str,
        required=False,
        default=None,
        help='The repository directory. If not specified, the current directory is used.')
    parser.add_argument(
        "--check-dir",
        type=str,
        required=False,
        default=None,
        help=(
            'A directory to check. If not specified, the "open" and "open_candidate" directories '
            'will be checked. To check everything in the repo directory specify ".".'))
    parser.add_argument(
        "--check-everything",
        default=False,
        required=False,
        action='store_true',
        help=(
            'If this argument is specified, the files that reside in "special" directories (like '
            '"artifacts/", "licenses/", etc. are also checked.'))
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default=logging.INFO,
        help="The level of the log file. Default value: INFO.")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s\t%(message)s')

    repo_directory = Path(arguments.repo_dir) if arguments.repo_dir else Path.cwd()

    if arguments.check_dir:
        check_directories = [repo_directory / arguments.check_dir]
    else:
        check_directories = [repo_directory / "open", repo_directory / "open_candidate"]
    for cd in check_directories:
        check_directory(
            repo_directory=repo_directory.resolve(),
            check_directory=cd.resolve(),
            consider_directory_context=not arguments.check_everything)


if __name__ == '__main__':
    main()
