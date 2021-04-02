#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path
import sys

import robocat.rule.helpers.open_source_file_checker


SCRIPT_DESCRIPTION = """
This script is to be used for checking source files for compatibility with Open Source standards
(absence of "bad" words, correc copyright notes etc.)
"""

def main():
    parser = argparse.ArgumentParser(
        sys.argv[0], description=SCRIPT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-directory",
        type=str, default=".", help='Repository directory. Current directory is the default.')
    parser.add_argument("directory", type=str, help="A directory to check.")
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default=logging.INFO,
        help="The level of the log file. Default value: INFO.")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s\t%(message)s')

    Checker = robocat.rule.helpers.open_source_file_checker.OpenSourceFileChecker
    repo_directory = Path(arguments.repo_directory).resolve()
    check_directory = (repo_directory / arguments.directory).resolve()

    logging.info(f"Checking {check_directory}...")
    for entry in check_directory.rglob("*"):
        if entry.is_dir():
            continue
        relative_path = entry.relative_to(repo_directory)
        if Checker.is_check_needed(str(relative_path)):
            logging.debug(f"Checking {entry}...")
            with open(entry) as f:
                errors = Checker(file_name=relative_path, file_content=f.read()).file_errors()
                if not errors:
                    continue
                errors_as_string = "\n".join(str(e) for e in errors)
                logging.info(f"Problems found while checking {entry}:\n{errors_as_string}")
        else:
            logging.debug(f"No check is needed for {relative_path}")
    logging.info(f"Done!")

if __name__ == '__main__':
    main()
