template_police = """{message}

More info: [https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot|https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot|smart-link]

h5. 🚔 Workflow Police
"""  # noqa

template_robocat = """{message}

h5. 🐱 Robocat v{version}. See its [documentation|https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot]
"""  # noqa

issue_moved_to_qa = """Issue moved to QA because merge requests for all "fixVersions" were merged into their respective branches:

* {branches}
"""  # noqa

issue_closed = """Issue closed because merge requests for all "fixVersions" were merged into their respective branches:

* {branches}
"""

reopen_issue = """Returning the issue, workflow violation found:

* {reason}.

{{color:#97a0af}}Issues closed with a resolution “{{color}}{{color:#97a0af}}*{resolution}*{{color}}{{color:#97a0af}}“ come under mandatory Workflow Police inspection. Please, consider changing resolution value if the issue *does not imply any code changes*.{{color}}
"""  # noqa

followup_mrs_created = """Merge requests for cherry-picking changes were autocreated for the following branches:

* {branches}
"""

followup_error = """An error occured while trying to execute follow-up actions for merge request [{mr_url}|{mr_url}]:

{{noformat}}{error}{{noformat}}

Please, investigate the problem - check this merge request and all related Jira issues.
"""
