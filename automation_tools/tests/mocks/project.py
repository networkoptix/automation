from dataclasses import dataclass, field
import time
from typing import Any, Dict, Set
from gitlab import GitlabCreateError

from automation_tools.tests.mocks.gitlab import GitlabManagerMock
from automation_tools.tests.mocks.pipeline import PipelineManagerMock, JobsManagerMock
from automation_tools.tests.mocks.commit import CommitsManagerMock, CommitMock
from automation_tools.tests.mocks.file import FileManagerMock
from automation_tools.tests.mocks.merge_request import MergeRequestMock
from automation_tools.tests.mocks.user import UserManagerMock
from automation_tools.tests.gitlab_constants import DEFAULT_PROJECT_ID


@dataclass
class ProjectApprovalsMock:
    reset_approvals_on_push: bool = True


@dataclass
class ProjectApprovalsManagerMock:
    approvals: ProjectApprovalsMock = field(default_factory=ProjectApprovalsMock)

    def get(self):
        return self.approvals


@dataclass
class MergeRequestManagerMock:
    merge_requests: dict = field(default_factory=dict)
    project: Any = None
    # Merge Requests where the "target" is the other project.
    mock_shadow_merge_requests: dict = field(default_factory=dict)

    def get(self, mr_id, **_):
        return self.merge_requests[mr_id]

    def add_mock_mr(self, mr: MergeRequestMock):
        self.merge_requests[mr.iid] = mr

    def create(self, params):
        # If the target branch is in another project, call `create` for that project, not this one.
        if params["target_project_id"] != self.project.id:
            target_project = self.project.manager.gitlab.projects.get(params["target_project_id"])
            mr = target_project.mergerequests.create(
                dict(params, **{"source_project": self.project}))
            self.mock_shadow_merge_requests[mr.iid] = mr
            return mr

        for mr in self.merge_requests.values():
            if mr.state != "opened":
                continue
            if mr.source_branch != params["source_branch"]:
                continue
            if mr.target_branch != params["target_branch"]:
                continue
            raise GitlabCreateError(
                'Another open merge request already exists for this source branch')

        source_project = params.get("source_project", self.project)
        source_branch = next(
            b for b in source_project.branches.list() if b.name == params["source_branch"])
        target_branch = next(
            b for b in self.project.branches.list() if b.name == params["target_branch"])
        commits = [
            {"sha": c.sha, "message": c.message}
            for c in source_branch.commit.values() if c.sha not in target_branch.commit.keys()]

        mr = MergeRequestMock(
            project=self.project,
            commits_list=commits,
            iid=time.time_ns(),
            title=params["title"],
            assignee_ids=params["assignee_ids"],
            source_branch=params["source_branch"],
            target_branch=params["target_branch"],
            source_project_id=source_project.id,
            target_project_id=self.project.id,
            mock_ignored_sha=[c.sha for c in self.project.commits.list()])

        self.merge_requests[mr.iid] = mr
        return mr

    def list(self, **_):
        return self.merge_requests.values()


@dataclass
class BranchMock:
    name: str
    commit: dict = field(default_factory=lambda: {
        "000000000000": CommitMock(sha="000000000000", message="")})


@dataclass
class BranchManagerMock:
    branches: list = field(default_factory=lambda: [
        BranchMock(b) for b in ["master", "vms_5.1", "vms_4.2", "feature1"]])
    mock_conflicts: Dict[str, Set] = field(default_factory=dict)

    def create(self, params):
        new_branch = params["branch"]
        if any(b for b in self.branches if b.name == new_branch):
            raise GitlabCreateError(f"Branch {new_branch} exists")
        self.branches.append(BranchMock(new_branch))

    def list(self):
        return self.branches

    def mock_get_by_name(self, branch: str) -> BranchMock:
        return next(b for b in self.branches if b.name == branch)


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
    path_with_namespace: str = "dev/nx"
    approvals: ProjectApprovalsManagerMock = field(default_factory=ProjectApprovalsManagerMock)

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock)

    def __post_init__(self):
        self.manager.gitlab.projects.add_mock_project(self)
        self.mergerequests.project = self
        self.commits.project = self

    def add_mock_commit(self, branch: str, sha: str, commit_msg: str):
        if sha not in self.commits.commits:
            self.commits.add_mock_commit(CommitMock(sha=sha, message=commit_msg, project=self))
        branch_object = self.branches.mock_get_by_name(branch)
        branch_object.commit[sha] = self.commits.get(sha)

        try:
            mr = next(
                mr for mr in self.mergerequests.merge_requests.values()
                if mr.source_branch == branch)
        except StopIteration:
            # Try to find if there is a Merge Request in some other project where the "source" is
            # this project.
            try:
                mr = next(
                    mr for mr in self.mergerequests.mock_shadow_merge_requests.values()
                    if mr.source_branch == branch)
            except StopIteration:
                return  # No Merge Requests for this branch.

        if sha not in [c["sha"] for c in mr.commits_list] and sha not in mr.mock_ignored_sha:
            mr.commits_list.append({"sha": sha})

    def add_mock_branch(self, branch: str):
        if branch not in [b.name for b in self.branches.list()]:
            self.branches.create({"branch": branch})

    @property
    def namespace(self):
        return {"full_path": f"project{self.id}/test"}

    @property
    def ssh_url_to_repo(self):
        return f"gitlab:/{self.namespace['full_path']}"
