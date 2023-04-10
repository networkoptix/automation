#!/usr/bin/env python3

import argparse
import itertools
import logging
from pathlib import Path
import sys
from typing import Iterable

import source_file_compliance


SCRIPT_DESCRIPTION = f"""
This script is to be used for checking source files for compatibility with Open Source standards
(absence of "bad" words, correc copyright notes etc.)

source_file_compliance library version: {source_file_compliance.__version__}
"""


def check_file_list(
        config_file_path: Path,
        repo_directory: Path,
        check_files: Iterable[Path],
        display_relative_paths: bool) -> bool:
    no_errors_found = True

    if config_file_path:
        repo_configuration = source_file_compliance.RepoCheckConfig.load(config_file_path)
    else:
        repo_configuration = source_file_compliance.RepoCheckConfig([], [], [], [])

    for entry in check_files:
        if entry.is_dir():
            continue

        logging.debug(f"Checking {entry}...")
        errors = source_file_compliance.check_file_if_needed(
            path=entry, repo_config=repo_configuration, repo_root=repo_directory)
        if errors is None:
            logging.debug(f"No check is needed for {entry}")
        if not errors:
            continue

        no_errors_found = False

        relative_to = repo_directory if display_relative_paths else None
        errors_as_string = "\n".join(e.to_string(relative_to=relative_to) for e in errors)
        logging.info(f"Problems found while checking {entry}:\n{errors_as_string}")

    logging.info(f"Done!")

    return no_errors_found


def main():
    parser = argparse.ArgumentParser(
        sys.argv[0], description=SCRIPT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--config",
        required=False,
        default=None,
        type=Path,
        help="Path to the configuration file.")
    parser.add_argument(
        "--repo-name",
        choices=["vms"],
        required=False,
        default=None,
        type=str,
        help="LEFT FOR COMPATIBILITY - DO NOT USE.")
    parser.add_argument(
        "--repo-dir",
        type=str,
        required=False,
        default=None,
        help='The repository directory. If not specified, the current directory is used.')
    check_target_group = parser.add_mutually_exclusive_group()
    check_target_group.add_argument(
        "--check-dir",
        type=str,
        required=False,
        default=None,
        help=(
            'A directory to check. If neither this parameter nor "check-file-list" parameter is '
            'specified, the "open/" and "open_candidate/" directories will be checked. To check '
            'everything in the repo directory specify ".".'))
    check_target_group.add_argument(
        "--check-file-list",
        type=Path,
        required=False,
        default=None,
        help=(
            'A file with the list of files to check. File paths can be relative to the repo '
            'directory.'))
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default=logging.INFO,
        help="The level of the log file. Default value: INFO.")
    parser.add_argument(
        "--display-relative-paths",
        default=False,
        required=False,
        action="store_true",
        help="Show file paths relative to the repo directory instead of absolute.")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s\t%(message)s')

    repo_directory = (Path(arguments.repo_dir) if arguments.repo_dir else Path.cwd()).resolve()

    if arguments.check_dir:
        logging.info(
            f"Checking open-source requirements for {arguments.check_dir!r} directory "
            f"in {repo_directory.as_posix()!r}")
        check_files = (repo_directory / arguments.check_dir).rglob("*")
    elif arguments.check_file_list:
        logging.info(
            f"Checking open-source requirements for the files listed in "
            f"{arguments.check_file_list.as_posix()!r} directory")
        with open(arguments.check_file_list) as file_list:
            check_files = [repo_directory / Path(f.rstrip()) for f in file_list.readlines()]
    else:
        logging.info(
            'Checking open-source requirements for "open/" and "open_candidate/" directories in '
            f"{repo_directory.as_posix()!r}")
        check_files = itertools.chain(
            (repo_directory / "open").rglob("*"),
            (repo_directory / "open_candidate").rglob("*"))

    result = check_file_list(
        config_file_path=arguments.config,
        repo_directory=repo_directory.resolve(),
        check_files=check_files,
        display_relative_paths=arguments.display_relative_paths)

    if not result:
        sys.exit("FAILURE: Problems were found during the check, see above.")

    print("No problems were found during the check.")


if __name__ == '__main__':
    main()
