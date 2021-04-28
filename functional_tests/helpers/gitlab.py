from copy import deepcopy
import datetime
import time
from typing import Dict, List, Optional

import gitlab

import helpers.tests_config


def create_merge_request(project, mr_parameters: Dict[str, str]):
    parameters = deepcopy(mr_parameters)

    parameters.setdefault("assignee_ids", []).append(helpers.tests_config.BOT_USER_ID)
    parameters.setdefault("squash", helpers.tests_config.DO_SQUASH)
    parameters.setdefault("remove_source_branch", helpers.tests_config.DO_REMOVE_SOURCE_BRANCH)
    parameters.setdefault("approvals_before_merge ", len(helpers.tests_config.APPROVERS))

    time.sleep(2)  # Wait for some time to allow gitlab to do all the post-MR-creation magic.

    return project.mergerequests.create(parameters)


def approve_mr_as_user(mr, user_name: str):
    gitlab_instance = mr.manager.gitlab
    effective_user = gitlab_instance.users.list(search=user_name)[0]
    tomorrow_date_string = str(datetime.date.today() + datetime.timedelta(days=1))
    impersonation_token = effective_user.impersonationtokens.create(
        {"name": user_name, "scopes": ["api"], "expires_at": tomorrow_date_string})
    user_gitlab = gitlab.Gitlab(gitlab_instance.url, private_token=impersonation_token.token)
    user_mr = user_gitlab.projects.get(mr.project_id).mergerequests.get(mr.iid)
    user_mr.approve()


def update_mr_data(mr):
    gitlab_instance = mr.manager.gitlab
    return gitlab_instance.projects.get(mr.project_id).mergerequests.get(mr.iid)


def approve_mr_and_wait_pipeline(mr, exclude_approvers: Optional[List[str]] = None):
    wait_last_mr_pipeline_status(mr, ["running"])
    approve_mr(mr, exclude_approvers)
    wait_last_mr_pipeline_status(mr, ["success"])


def wait_last_mr_pipeline_status(mr, status_list: List[str], max_pipeline_wait_time_s: int = 30):
    pipeline_start_wait_time = time.time()
    current_status = mr.pipelines()[0]["status"]
    while current_status not in status_list:
        assert time.time() - pipeline_start_wait_time < max_pipeline_wait_time_s, (
            f'Pipeline has status "{current_status}" after {max_pipeline_wait_time_s} seconds; '
            'expected "{}".'.format('" or "'.join(status_list)))
        time.sleep(1)
        current_status = mr.pipelines()[0]["status"]


def approve_mr(mr, exclude_approvers: Optional[List[str]] = None):
    for approver in helpers.tests_config.APPROVERS:
        if exclude_approvers and approver in exclude_approvers:
            continue
        approve_mr_as_user(mr, approver)


def get_last_opened_mr(project):
    opened_merge_requests = project.mergerequests.list(state="opened")
    if not opened_merge_requests:
        return None
    return opened_merge_requests[0]


def resolve_discussion(mr, discussion_id: str):
    gitlab_instance = mr.manager.gitlab
    url = f"/projects/{mr.project_id}/merge_requests/{mr.iid}/discussions/{discussion_id}"
    gitlab_instance.http_put(url, post_data={"resolved": True})
