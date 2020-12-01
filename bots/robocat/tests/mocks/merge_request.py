from dataclasses import dataclass, field
from functools import namedtuple
from typing import Any
from gitlab.exceptions import GitlabMRClosedError

from tests.mocks.gitlab import GitlabManagerMock
from tests.mocks.pipeline import PipelineMock
from tests.mocks.commit import CommitMock
from tests.common_constants import BOT_USERNAME, DEFAULT_COMMIT, DEFAULT_MR_ID

DEFAULT_APPROVERS_NUMBER = 2


@dataclass
class AwardEmojiManagerMock:
    emojis: set = field(default_factory=dict)
    username: str = BOT_USERNAME

    AwardEmojiMock = namedtuple("Emoji", ["name", "id", "user"])

    def list(self, **_):
        return self.emojis.values()

    def _key(self, name):
        return f"{self.username}:{name}"

    def create(self, params, **_):
        key = self._key(params["name"])
        assert key not in self.emojis, (
            f"Emoji {params['name']} for user {self.username} already exists.")
        self.emojis[key] = self.AwardEmojiMock(
            name=params["name"], id=params["name"], user={"username": self.username})

    def delete(self, name, **_):
        key = self._key(name)
        assert key in self.emojis, f"Emoji {name} for user {self.username} doesn't exist."
        del self.emojis[key]


@dataclass
class ApprovalsMock:
    approvals_left: int = 999
    approved_by: list = field(default_factory=list)


@dataclass
class ApprovalsManagerMock:
    approvals: ApprovalsMock = field(default_factory=ApprovalsMock)

    def get(self):
        return self.approvals


@dataclass
class VersionsManagerMock:
    merge_request: Any

    @dataclass
    class VersionMock:
        head_commit_sha: str
        diffs: list = field(default_factory=list)
        base_commit_sha: str = "1"
        start_commit_sha: str = "1"
        id: int = 0

    def list(self, **_):
        return [self.VersionMock(head_commit_sha=self.merge_request.commits_list[-1]["sha"])]

    def get(self, id, **_):
        files = []
        for c in self.merge_request.commits_list:
            files.extend(c["files"])
        return self.VersionMock(
            id=id,
            head_commit_sha=self.merge_request.commits_list[-1]["sha"],
            diffs=[{"new_path": f, "deleted_file": False} for f in files])


@dataclass
class NotesManagerMock:
    merge_request: Any
    notes: list = field(default_factory=list)

    def create(self, params):
        if params["body"] == "/wip":
            self.merge_request.work_in_progress = True
            return

        self.notes.append(params["body"])

    def list(self):
        return self.notes


@dataclass
class DiscussionsManagerMock:
    merge_request: Any
    discussions: list = field(default_factory=list)

    @dataclass
    class DiscussionMock:
        body: str = ""
        position: dict = field(default_factory=dict)

    def create(self, params):
        self.discussions.append(
            self.DiscussionMock(body=params["body"], position=params["position"]))
        self.merge_request.blocking_discussions_resolved = False

    def list(self):
        return [d.body for d in self.discussions]


@dataclass
class MergeRequestMock:
    project: Any  # ProjectMock

    iid: int = DEFAULT_MR_ID
    title: str = "Do Zorz at work"
    target_branch: str = "x/zorz_branch"
    has_conflicts: bool = False
    work_in_progress: bool = False
    blocking_discussions_resolved: bool = True
    assignees: list = field(default_factory=list)
    squash: bool = True
    description: str = ""

    # Fake field for testing purposes
    needs_rebase: bool = False

    emojis_list: list = field(default_factory=list)
    approvers_list: list = field(default_factory=list)
    needed_approvers_number: int = DEFAULT_APPROVERS_NUMBER
    pipelines_list: list = field(default_factory=lambda: [(DEFAULT_COMMIT["sha"], "manual")])
    commits_list: list = field(default_factory=lambda: [DEFAULT_COMMIT])

    # Managers, must not be directly initialized.
    awardemojis: AwardEmojiManagerMock = field(default_factory=AwardEmojiManagerMock, init=False)
    approvals: ApprovalsManagerMock = field(default_factory=ApprovalsManagerMock, init=False)
    notes: NotesManagerMock = field(default=None, init=False)
    discussions: DiscussionsManagerMock = field(default=None, init=False)
    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)
    diffs: VersionsManagerMock = field(default=None, init=False)
    assignee_ids: list = field(default_factory=list, init=False)

    # Data fields to check merge request state.
    rebased: bool = field(default=False, init=False)
    merged: bool = field(default=False, init=False)

    def __post_init__(self):
        # Bind to "self.project".
        self.manager.gitlab = self.project.manager.gitlab
        self.project.mergerequests.mock_add_mr(self)

        # Create notes manager and bind it to itself.
        self.notes = NotesManagerMock(merge_request=self)

        # Create discussions manager and bind it to itself.
        self.discussions = DiscussionsManagerMock(merge_request=self)

        # Create versions ("diff" in gitlab library terminology) manager and bind it to itself.
        self.diffs = VersionsManagerMock(merge_request=self)

        # Initialize other fields.
        for name in self.emojis_list:
            self.awardemojis.create({'name': name})

        approvals = self.approvals.get()
        approvals.approvals_left = max(
            self.needed_approvers_number - len(set(self.approvers_list)), 0)
        for approver in set(self.approvers_list):
            approvals.approved_by.append({"user": {"username": approver}})

        for p_id, p_data in enumerate(self.pipelines_list):
            pipeline = PipelineMock(project=self.project, id=p_id, sha=p_data[0], status=p_data[1])
            self.project.pipelines.mock_add_pipeline(pipeline)

        for commit_data in self.commits_list:
            self._register_commit(commit_data)

        for assignee in self.assignees:
            assignee = self.project.users.list(username=assignee["username"])[0]
            self.assignee_ids.append(assignee.id)

    def _register_commit(self, commit_data):
        commit = CommitMock(**commit_data)
        self.project.commits.mock_add_commit(commit)

    # Gitlab library merge request interface implementation.
    @property
    def sha(self):
        if not self.commits_list:
            return None
        return self.commits_list[-1]["sha"]

    @property
    def approvals_left(self):
        return self.approvals.get().approvals_left

    @property
    def project_id(self):
        return self.project.id

    def pipelines(self):
        result = []
        for pipeline in sorted(self.project.pipelines.list(), key=lambda p: p.id):
            result.append({
                "id": pipeline.id,
                "sha": pipeline.sha,
                "status": pipeline.status,
                "web_url": pipeline.web_url
            })
        # NOTE: Gitlab returns pipeline with the highest ID first
        return list(reversed(result))

    def rebase(self):
        self.rebased = True

    def merge(self, **_):
        if self.needs_rebase:
            raise GitlabMRClosedError()
        self.merged = True

    def changes(self):
        files = []
        for c in self.commits_list:
            files.extend(c["files"])
        return {"changes": [{"new_path": f, "deleted_file": False} for f in files]}

    def save(self):
        users = self.project.users.list()
        for assignee_id in self.assignee_ids:
            assignee = [u for u in users if u.id == assignee_id][0]
            self.assignees.append({"username": assignee.name})

    def comments(self):
        return self.notes.list() + self.discussions.list()
