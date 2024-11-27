## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from .commit_message_check_rule import CommitMessageCheckRule
from .essential_rule import EssentialRule
from .follow_up_rule import FollowUpRule
from .job_status_check_rule import JobStatusCheckRule
from .nx_submodule_check_rule import NxSubmoduleCheckRule
from .post_processing_rule import PostProcessingRule
from .process_related_projects_issues import ProcessRelatedProjectIssuesRule
from .workflow_check_rule import WorkflowCheckRule

ALL_RULES = [
    CommitMessageCheckRule,
    EssentialRule,
    FollowUpRule,
    JobStatusCheckRule,
    NxSubmoduleCheckRule,
    PostProcessingRule,
    ProcessRelatedProjectIssuesRule,
    WorkflowCheckRule,
]
