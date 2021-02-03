from dataclasses import dataclass, field
import time
from typing import Any, Dict, Set
from gitlab import GitlabCreateError

from tests.mocks.gitlab import GitlabManagerMock
from tests.mocks.pipeline import PipelineManagerMock, JobsManagerMock
from tests.mocks.commit import CommitsManagerMock
from tests.mocks.file import FileManagerMock
from tests.mocks.merge_request import MergeRequestMock
from tests.mocks.user import UserManagerMock

DEFAULT_PROJECT_ID = 1


@dataclass
class MergeRequestManagerMock:
    merge_requests: dict = field(default_factory=dict)
    project: Any = None

    def get(self, mr_id, **_):
        return self.merge_requests[mr_id]

    def add_mock_mr(self, mr: MergeRequestMock):
        self.merge_requests[mr.iid] = mr

    def create(self, params):
        for mr in self.merge_requests.values():
            if mr.state != "opened":
                continue
            if mr.source_branch != params["source_branch"]:
                continue
            if mr.target_branch != params["target_branch"]:
                continue
            raise GitlabCreateError(
                'Another open merge request already exists for this source branch')

        mr = MergeRequestMock(
            project=self.project,
            commits_list=[],
            iid=time.time_ns(),
            title=params["title"],
            assignee_ids=params["assignee_ids"],
            source_branch=params["source_branch"],
            target_branch=params["target_branch"])

        self.merge_requests[mr.iid] = mr
        return mr

    def list(self, **_):
        return self.merge_requests.values()


@dataclass
class BranchManagerMock:
    branches: list = field(default_factory=lambda: ["master", "feature1"])
    mock_conflicts: Dict[str, Set] = field(default_factory=dict)

    def create(self, params):
        new_branch = params["branch"]
        if any(b for b in self.branches if b == new_branch):
            raise GitlabCreateError(f"Branch {new_branch} exists")
        self.branches.append(new_branch)


@dataclass
class ProjectMock:
    id: int = DEFAULT_PROJECT_ID
    mergerequest_list: list = field(default_factory=list)

    mergerequests: MergeRequestManagerMock = field(
        default_factory=MergeRequestManagerMock, init=False)
    pipelines: PipelineManagerMock = field(default_factory=PipelineManagerMock, init=False)
    jobs: JobsManagerMock = field(default_factory=JobsManagerMock, init=False)
    commits: CommitsManagerMock = field(default_factory=CommitsManagerMock, init=False)
    users: UserManagerMock = field(default_factory=UserManagerMock, init=False)
    files: FileManagerMock = field(default_factory=FileManagerMock, init=False)
    branches: BranchManagerMock = field(default_factory=BranchManagerMock, init=False)

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)

    def __post_init__(self):
        self.manager.gitlab.projects.add_mock_project(self)
        self.mergerequests.project = self
        self.commits.project = self

    def add_mock_commit_to_mr_by_branch(self, branch, sha):
        mr = next(
            mr for mr in self.mergerequests.merge_requests.values() if mr.source_branch == branch)
        mr.commits_list.append({"sha": sha})
