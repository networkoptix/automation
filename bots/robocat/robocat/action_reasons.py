## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import enum


# TODO: Refactor reasons to store their context and messages.
class CheckFailureReason(enum.Enum):
    conflicts = enum.auto()
    failed_pipeline = enum.auto()
    unresolved_threads = enum.auto()
    bad_project_list = enum.auto()


class WaitReason(enum.Enum):
    no_commits = "no commits in MR"
    not_approved = "not enough non-bot approvals"
    pipeline_running = "pipeline is in progress"
