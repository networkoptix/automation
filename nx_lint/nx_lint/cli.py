import sys
import logging

from pathlib import Path

from nx_lint.argument_parser import NxLintArgumentParser
from nx_lint.utils import git_repo_root


def main():
    parser = NxLintArgumentParser()
    parser.add_argument(
        "--output-format",
        choices=["log", "simple"],
        default="simple",
        help="Output format for lint results.")
    parser.add_argument(
        "-r",
        "--repo-dir",
        type=str,
        default=".",
        help="The repository directory. If not specified, the current directory is used.")
    check_target_group = parser.add_mutually_exclusive_group()
    check_target_group.add_argument(
        "--check-dir",
        type=str,
        required=False,
        default=None,
        help=(
            'A directory to check. If neither this parameter nor "check-file-list" parameter is '
            "specified, the entire repository will be checked."))
    check_target_group.add_argument(
        "--check-file-list",
        type=Path,
        required=False,
        default=None,
        help=(
            "A file with the list of files to check. File paths can be relative to the repo "
            "directory."))
    parser.add_argument(
        "--log-level",
        choices=logging._nameToLevel.keys(),
        default=logging.INFO,
        help="The level of the log file. Default value: INFO.")
    parser.add_argument(
        "--display-absolute-paths",
        default=False,
        action="store_true",
        help="Display absolute file paths instead of relative to the repo directory.")
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Single file to lint. Overrides --check-dir and --check-file-list.")
    parser.add_argument(
        "--always-succeed",
        action="store_true",
        default=False,
        help="Always return 0, even if linting fails. Useful for integration with editors.")
    parser.add_argument(
        "-e",
        "--enable-rule",
        dest="enabled_rules",
        action="append",
        default=[],
        help="Enable a specific rule. Can be specified multiple times. If no rules are specified, "
             "all rules are enabled. This overrides the enabled_rules setting in nx_lint.json.")
    parser.add_argument(
        "--write-csv",
        dest="csv_file",
        type=Path,
        default=None,
        help="Write lint results to a CSV file.")
    parser.add_argument(
        "--fix",
        dest="fix_rules",
        action="append",
        default=[],
        help="Fix a specific violation if an automated fix is possible. Can be specified multiple "
             "times. If no rule names are specified, nothing is fixed. Pass ALL to fix all "
             "violations that can be fixed automatically.")
    parser.add_argument(
        "--no-backup",
        "-nb",
        action="store_false",
        dest="create_backups",
        default=True,
        help="Never create a backup file when fixing a violation. By default, a backup file is "
             "created if a fix is applied to a file that contains changes not tracked by git.")
    is_in_git = git_repo_root() is not None
    parser.add_argument(
        "-u",
        "--include-untracked",
        default=not is_in_git,
        action="store_true",
        dest="include_untracked",
        help="Do not exclude files that are neither tracked nor staged by git. If this option is "
             "not specified, such files are excluded, and their filenames are printed.")

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s\t%(message)s"
    )

    from nx_lint.linter import lint_files

    violation_count = lint_files(args)
    if violation_count == 0 or args.always_succeed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
