from dataclasses import dataclass, field

from tests.mocks.gitlab import GitlabManagerMock
from tests.mocks.pipeline import PipelineManagerMock, JobsManagerMock
from tests.mocks.commit import CommitsManagerMock
from tests.mocks.file import FileManagerMock
from tests.mocks.merge_request import MergeRequestMock

DEFAULT_PROJECT_ID = 1


@dataclass
class MergeRequestManagerMock():
    merge_requests: dict = field(default_factory=dict)

    def get(self, mr_id, **_):
        return self.merge_requests[mr_id]

    def mock_add_mr(self, mr: MergeRequestMock):
        self.merge_requests[mr.iid] = mr


@dataclass
class UserManagerMock():
    members: list = field(default_factory=lambda: [
        UserManagerMock.UserMock(id=1, name="user1"),
        UserManagerMock.UserMock(id=2, name="user2"),
        UserManagerMock.UserMock(id=10, name="mshevchenko")
    ])

    @dataclass
    class UserMock():
        id: int = 1
        name: str = "foobar"

    def list(self, query: None, **_):
        if query is None:
            return self.members
        return [u for u in self.members if u.name == query]

    def get(self, user_id, **_):
        return [u for u in self.members if u.id == user_id][0]


@dataclass
class ProjectMock:
    id: int = DEFAULT_PROJECT_ID
    mergerequest_list: list = field(default_factory=list)

    mergerequests: MergeRequestManagerMock = field(
        default_factory=MergeRequestManagerMock, init=False)
    pipelines: PipelineManagerMock = field(
        default_factory=PipelineManagerMock, init=False)
    jobs: JobsManagerMock = field(default_factory=JobsManagerMock, init=False)
    commits: CommitsManagerMock = field(default_factory=CommitsManagerMock, init=False)
    members: UserManagerMock = field(
        default_factory=UserManagerMock, init=False)
    files: FileManagerMock = field(
        default_factory=FileManagerMock, init=False)

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)

    def __post_init__(self):
        self.manager.gitlab.projects.mock_add_project(self)
