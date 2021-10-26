FUNCTEST_GROUP_NAME = "dev-functests"
FUNCTEST_PROJECT_NAME = "testrepo"
BOT_USER_ID = 78
DO_SQUASH = True
DO_REMOVE_SOURCE_BRANCH = True

JIRA_PROJECT = "VMS"
JIRA_ASSIGNEE_ID = "557058:d03e1d81-655d-4fe8-a74f-3c1dcb6ba0e9"  # Service account

APPROVERS = ["root", "ptolstov"]

TARGET_BRANCHES = ["master", "vms_5.0", "vms_4.2", "vms_4.2_patch"]

POST_MR_SLEEP_S = 10  # Gitlab post-MR-creation magic timeout
