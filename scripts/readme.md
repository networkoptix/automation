# Script collection for automating routine gitlab/jira operations


## fix_issues_with_new_branch


## open_source_check
To run this script, you need the path to the robocat directory to be in the PYTHONPATH environment
variable, e.g.:

`PYTHONPATH=.:./bots/robocat ./scripts/open_source_check/open_source_check.py --repo-dir
<repo_directory>`
to run it from the repository root).
Also to run this script it is necessary to install dependencies from the file
`bots/robocat/requirements.txt`: `pip install -r bots/robocat/requirements.txt`.

This script has a handful of parameters for tuning the checks - run the script with "--help"
to find more information.
