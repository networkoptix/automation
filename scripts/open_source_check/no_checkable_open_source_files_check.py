#!/usr/bin/env python3

import argparse
import itertools
import logging
from pathlib import Path
import sys
from typing import Iterable

import source_file_compliance

DEFAULT_CONFIG_NAME = "open_source_check_config.json"

SCRIPT_DESCRIPTION = f"""
This script is to be used for checking if there are no files that should be checked for
compatibility with Open Source standards (absence of "bad" words, correct copyright notes etc.) in
the supplied file list.
"""


def has_checkable_files(
        config_file_path: Path,
        repo_directory: Path,
        files_to_check: Iterable[Path]) -> bool:
    checkable_files_found = False

    if config_file_path.exists():
        repo_configuration = source_file_compliance.RepoCheckConfig.load(config_file_path)
    else:
        default_config_file = (Path(__file__).parent / DEFAULT_CONFIG_NAME).resolve()
        logging.warning(
            f"Config file {config_file_path.as_posix()!r} is not found. Using the default config "
            f"from {default_config_file.as_posix()!r}.")
        repo_configuration = source_file_compliance.RepoCheckConfig.load(default_config_file)

    for entry in files_to_check:
        if entry.is_dir():
            logging.warning(f"Bad input: {str(entry)!r} is a directory")
            continue

        is_check_needed = source_file_compliance.is_check_needed(
            path=entry, repo_config=repo_configuration, repo_root=repo_directory)

        if is_check_needed:
            checkable_files_found = True
            logging.info(f"Check is needed for {str(entry)!r}")
        else:
            logging.debug(f"No check is needed for {str(entry)!r}")

    logging.info(f"Done")

    return checkable_files_found


def create_argument_parser():
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
        "--repo-dir",
        type=str,
        required=False,
        default=None,
        help='The repository directory. If not specified, the current directory is used.')
    parser.add_argument(
        "--files-to-check-list",
        type=Path,
        required=True,
        default=None,
        help=(
            'A file with the list of files to check. File paths can be relative to the repo '
            'directory.'))
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default=logging.INFO,
        help="The level of the log file. Default value: INFO.")

    return parser


def main():
    arguments = create_argument_parser().parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s\t%(message)s')

    repo_directory = (Path(arguments.repo_dir) if arguments.repo_dir else Path.cwd()).resolve()
    if not arguments.config:
        config_file_path = (repo_directory / DEFAULT_CONFIG_NAME).resolve()
    else:
        config_file_path = arguments.config.resolve()

    logging.info(
        f"Checking open-source requirements for the files listed in file "
        f"{str(arguments.files_to_check_list)!r} using configuration file "
        f"{config_file_path.as_posix()!r}")
    with open(arguments.files_to_check_list) as file_list:
        files_to_check = [repo_directory / Path(f.rstrip()) for f in file_list.readlines()]

    result = has_checkable_files(
        config_file_path=config_file_path,
        repo_directory=repo_directory,
        files_to_check=files_to_check)

    if result:
        sys.exit("Some of the files must be checked, see above.")

    print("No files to check.")


if __name__ == '__main__':
    main()
