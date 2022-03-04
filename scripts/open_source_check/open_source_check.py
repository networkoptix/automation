#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path, PurePosixPath
import sys

import source_file_compliance


SCRIPT_DESCRIPTION = """
This script is to be used for checking source files for compatibility with Open Source standards
(absence of "bad" words, correc copyright notes etc.)
"""


def check_directory(
        repo_name: str,
        repo_directory: Path,
        check_directory: Path) -> bool:
    no_errors_found = True

    repo_configuration = source_file_compliance.repo_configurations.get(
        repo_name,
        source_file_compliance.GENERIC_REPO_CONFIG)
    logging.info(f"Checking {check_directory}...")
    for entry in check_directory.rglob("*"):
        if entry.is_dir():
            continue

        check_path = PurePosixPath(entry.relative_to(repo_directory))
        is_check_needed = source_file_compliance.is_check_needed(
            path=str(check_path),
            repo_config=repo_configuration)
        if is_check_needed:
            logging.debug(f"Checking {entry}...")
            with open(entry, encoding="latin1") as f:
                errors = source_file_compliance.check_file_content(path=entry, content=f.read())
                if not errors:
                    continue
                no_errors_found = False
                errors_as_string = "\n".join(repr(e) for e in errors)
                logging.info(f"Problems found while checking {entry}:\n{errors_as_string}")
        else:
            logging.debug(f"No check is needed for {check_path}")
    logging.info(f"Done!")

    return no_errors_found


def main():
    parser = argparse.ArgumentParser(
        sys.argv[0], description=SCRIPT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-name",
        choices=["vms"],
        required=False,
        default=None,
        type=str,
        help=(
            "The repository name. If set, determines repository-specific settings, like ignored "
            "file extensions, directory paths, etc."))
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

    result = True
    for cd in check_directories:
        result &= check_directory(
            repo_name=arguments.repo_name,
            repo_directory=repo_directory.resolve(),
            check_directory=cd.resolve())

    if not result:
        sys.exit("Some errors were found during the check.")

    print("No errors were found during the check.")


if __name__ == '__main__':
    main()
