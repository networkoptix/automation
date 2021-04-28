# Script collection for automating routine gitlab/jira operations


## fix_issues_with_new_branch


## check_open_source
To run this script you need a path to the robocat directory to be in the PYTHONPATH environment
variable, e.g

`PYTHONPATH=./bots/robocat ./scripts/check_open_sources/check_open_sources.py --repo-directory
<vms_directory> <open_source_directory>`
to run it from the repository root).

Also there is a non-standard library `source_file_compliance` that is needed by this script. To
install it, run

`pip install git+http://gerrit.lan.hdw.mx/qa/func_tests@master#subdirectory=source_file_compliance`
