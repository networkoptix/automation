# Script collection for automating routine gitlab/jira operations


## fix_issues_with_new_branch


## open_source_check
To run this script, it is necessary to install the `open_source_compliance` library:
`pip install nx_source_file_compliance/`

The script checks the repository specified by the `--repo-dir` parameter. If you need to take into
account repository-specific settings like file directories to exclude from the checks, file
patterns to exclude from the check, etc., specify the `--repo-name` parameter, e.g.:

`./scripts/open_source_check/open_source_check.py --repo-name vms --repo-dir ../nx`

For the full list of all the available check options, run the script with the `--help` parameter:
`./scripts/open_source_check/open_source_check.py --help`.
