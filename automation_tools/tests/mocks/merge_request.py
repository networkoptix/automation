## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import namedtuple
from typing import Any, Optional
import time
import uuid

from automation_tools.tests.mocks.gitlab import GitlabManagerMock
from automation_tools.tests.mocks.pipeline import PipelineMock, JobMock
from automation_tools.tests.mocks.commit import CommitMock
from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    DEFAULT_PROJECT_ID,
    USERS,
    DEFAULT_REQUIRED_APPROVALS_COUNT,
    DEFAULT_JIRA_ISSUE_KEY,
    BOT_USERNAME)
from automation_tools.mr_data_structures import ApprovalsInfo
try:
    from robocat.note import MessageId, NoteDetails
    import robocat.comments
except ImportError:
    # For testing Workflow Police we don't need Robocat, but need some functionality from this
    # module. So if we can't import Robocat modules, we assume that we are testing the Workflow
    # Police and do not need these imports.
    pass

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
class MergRequestApprovalsMock:
    approved: bool = True
    approvals_left: int = 999
    approvals_required: int = DEFAULT_REQUIRED_APPROVALS_COUNT
    approved_by: list = field(default_factory=list)


@dataclass
class MergeRequestApprovalsManagerMock:
    approvals: MergRequestApprovalsMock = field(default_factory=MergRequestApprovalsMock)

    def get(self):
        return self.approvals

    def update(self, new_data):
        if "approvals_required" in new_data:
            approvals_count_change = (
                new_data["approvals_required"] - self.approvals.approvals_required)
            self.approvals.approvals_required = new_data["approvals_required"]
            self.approvals.approvals_left = max(
                0, self.approvals.approvals_left + approvals_count_change)

        if "approvals_left" in new_data:
            self.approvals.approvals_left = max(0, new_data["approvals_left"])


@dataclass
class VersionsManagerMock:
    merge_request: Any

    @dataclass
    class VersionMock:
        head_commit_sha: str
        base_commit_sha: str
        start_commit_sha: str
        diffs: list = field(default_factory=list)
        id: int = 0

    def list(self, **_):
        return [self.VersionMock(
            head_commit_sha=self.merge_request.commits_list[-1]["sha"],
            start_commit_sha=self.merge_request.commits_list[0]["sha"],
            base_commit_sha=self.merge_request.mock_base_commit_sha)]

    def get(self, id, **_):
        files = []
        for c in self.merge_request.commits_list:
            files.extend(c["files"])
        return self.VersionMock(
            id=id,
            head_commit_sha=self.merge_request.commits_list[-1]["sha"],
            diffs=[{"new_path": f, "deleted_file": False} for f in files])


@dataclass
class NoteMock:
    id: int
    body: str
    created_at: str
    author: dict[str, str]
    resolvable: bool
    resolved: bool
    resolved_by: str

    @property
    def _attrs(self):
        return asdict(self)


@dataclass
class NotesManagerMock:
    merge_request: Any
    notes: list = field(default_factory=list[NoteMock])
    counter: int = 0

    def create(self, params, mock_discussion=None):
        if params["body"] == "/draft":
            self.merge_request.work_in_progress = True
            return

        note = NoteMock(
            id=self.counter + 1,
            body=params["body"],
            created_at=datetime.now().isoformat(),
            author={"username": params.get("author", BOT_USERNAME)},
            resolvable=params.get("resolvable", False),
            resolved=params.get("resolved", None),
            resolved_by=params.get("resolved_by", None))

        if not mock_discussion:
            discussion_params = {"body": params["body"], "position": None, "mock_resolved": True}
            mock_discussion = self.merge_request.discussions.create(
                discussion_params, mock_note=note)

        self.notes.append(note)
        return note

    def list(self):
        return list(reversed(self.notes))  # Gitlab returns notes in the reversed order.

    def get(self, id: int) -> Optional[NoteMock]:
        return next(iter(n for n in self.notes if n.id == id), None)

    def update(self, id: int, new_data: dict[str, str]):
        if (note := self.get(id)):
            for f, v in new_data.items():
                setattr(note, f, v)

            self.merge_request.discussions._update_note(note)


@dataclass
class DiscussionsManagerMock:
    merge_request: Any
    discussions: list = field(default_factory=list)

    @dataclass
    class DiscussionMock:
        manager: Any
        position: dict = field(default_factory=dict)
        resolved: bool = False
        mock_is_visible: bool = True  # Fake field for testing purposes.
        id: str = field(default_factory=lambda: uuid.uuid1().hex, init=False)
        notes: list = field(default_factory=list, init=False)

        @property
        def attributes(self):
            return {"notes": self.notes}

        def save(self):
            for d in self.manager.discussions:
                if not d.resolved:
                    self.manager.merge_request.blocking_discussions_resolved = False
                    return

            self.manager.merge_request.blocking_discussions_resolved = True

    def create(self, params, mock_is_visible: bool = True, mock_note: NoteMock = None):
        discussion = self.DiscussionMock(
            manager=self, position=params["position"], mock_is_visible=mock_is_visible)
        discussion.resolved = params.get("mock_resolved", False)

        if not mock_note:
            note_params = {
                "body": params["body"],
                "resolvable": True,
                "resolved": discussion.resolved,
            }
            mock_note = self.merge_request.notes.create(note_params, mock_discussion=discussion)

        discussion.notes.append(mock_note._attrs)
        self.discussions.append(discussion)
        self.merge_request.blocking_discussions_resolved &= discussion.resolved
        return discussion

    def list(self, **_):
        return [d for d in self.discussions if d.mock_is_visible]

    def get(self, id: str) -> Optional[DiscussionMock]:
        return next(iter(d for d in self.discussions if d.id == id), None)

    def _update_note(self, note: NoteMock):
        for discussion in self.discussions:
            for i, discussion_note in enumerate(discussion.notes):
                if discussion_note["id"] == note.id:
                    discussion.notes[i] = note._attrs


@dataclass
class MergeRequestMock:
    project: Any  # ProjectMock

    iid: int = field(default_factory=time.time_ns)
    title: str = f"{DEFAULT_JIRA_ISSUE_KEY}: Do Zorz at work"
    has_conflicts: bool = False
    work_in_progress: bool = False
    blocking_discussions_resolved: bool = True
    assignees: list = field(default_factory=lambda: [{"username": BOT_USERNAME}])
    reviewers: list = field(default_factory=list)
    squash: bool = True
    description: str = ""
    state: str = "opened"
    source_branch: str = "feature1"
    target_branch: str = "master"
    author: dict = field(default_factory=lambda: USERS[0])
    web_url: str = ""
    squash_commit_sha: Optional[str] = None
    source_project_id: int = DEFAULT_PROJECT_ID
    target_project_id: int = DEFAULT_PROJECT_ID
    diverged_commits_count: int = 0

    # Fake fields for testing purposes.
    mock_rebased: bool = field(default=False, init=False)
    mock_huge_mr: bool = False
    mock_base_commit_sha: str = "000000000000"
    mock_ignored_sha: list = field(default_factory=list)
    mock_force_unapproved: bool = False

    emojis_list: list = field(default_factory=list)
    approvers_list: set = field(default_factory=set)
    needed_approvers_number: int = DEFAULT_APPROVERS_NUMBER
    pipelines_list: list = field(default_factory=lambda: [(DEFAULT_COMMIT["sha"], "manual")])
    commits_list: list = field(default_factory=lambda: [DEFAULT_COMMIT])
    assignee_ids: list = field(default_factory=list)
    reviewer_ids: list = field(default_factory=list)
    mock_original_mr_id: Optional[int] = None

    detailed_merge_status: str = "mergeable"

    # Managers, must not be directly initialized.
    awardemojis: AwardEmojiManagerMock = field(default_factory=AwardEmojiManagerMock, init=False)
    approvals: MergeRequestApprovalsManagerMock = field(
        default_factory=MergeRequestApprovalsManagerMock, init=False)
    notes: NotesManagerMock = field(default=None, init=False)
    discussions: DiscussionsManagerMock = field(default=None, init=False)
    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)
    diffs: VersionsManagerMock = field(default=None, init=False)

    def __post_init__(self):
        # Bind to "self.project".
        self.manager.gitlab = self.project.manager.gitlab
        self.project.mergerequests.add_mock_mr(self)

        # Create notes manager and bind it to itself.
        self.notes = NotesManagerMock(merge_request=self)

        # Create discussions manager and bind it to itself.
        self.discussions = DiscussionsManagerMock(merge_request=self)
        if not self.blocking_discussions_resolved:
            self.discussions.create(
                {"body": "default discussion", "position": None}, mock_is_visible=False)

        # Create versions ("diff" in gitlab library terminology) manager and bind it to itself.
        self.diffs = VersionsManagerMock(merge_request=self)

        # Initialize other fields.
        for name in self.emojis_list:
            self.awardemojis.create({'name': name})

        approvals = self.approvals.get()
        approvals.approvals_left = max(
            self.needed_approvers_number - len(self.approvers_list), 0)
        for approver in self.approvers_list:
            approvals.approved_by.append({"user": {"username": approver}})
        if self.mock_force_unapproved:
            approvals.approved = False

        for p_id, p_data in enumerate(self.pipelines_list):
            pipeline = PipelineMock(
                project=self.project,
                mr=self,
                id=p_id, sha=p_data[0],
                status=p_data[1])
            if len(p_data) > 2:  # Mock pipeline with jobs.
                for job_id, job_data in enumerate(p_data[2]):
                    self.project.jobs.add_mock_job(JobMock(
                        id=p_id * 10000 + job_id,
                        pipeline_ref=pipeline,
                        name=job_data[0],
                        status=job_data[1],
                        stage=(job_data[2] if len(job_data) > 2 else "default")))
            self.project.pipelines.add_mock_pipeline(pipeline)

        for commit_data in self.commits_list:
            self._register_commit(commit_data)

        for assignee in self.assignees:
            assignee = self.project.users.list(username=assignee["username"])[0]
            self.assignee_ids.append(assignee.id)

        for reviewer in self.reviewers:
            reviewer = self.project.users.list(username=reviewer["username"])[0]
            self.reviewer_ids.append(reviewer.id)

        if self.mock_original_mr_id:
            message = robocat.comments.Message(
                id=MessageId.FollowUpInitialMessage,
                params={"branch": self.target_branch, "original_mr_url": self.web_url})
            data_text = str(NoteDetails(
                message_id=message.id,
                sha=self.squash_commit_sha or "",
                data={"original_mr_id": self.mock_original_mr_id}))
            self.notes.create({"body": message.format_body(data_text)})

    def _register_commit(self, commit_data):
        commit = CommitMock(**commit_data)
        self.mock_source_project.commits.add_mock_commit(commit)
        # Add to current commit files all the files from the previous commits.
        for listed_commit in self.commits_list:
            for path, file_data in listed_commit.get("files", {}).items():
                self.project.files.add_mock_file(
                    ref=commit.sha, path=path, data=file_data["raw_data"])

    @property
    def mock_source_project(self):
        try:
            return self.manager.gitlab.projects.get(self.source_project_id)
        except KeyError:
            return self.project

    def add_mock_commit(self, commit_data: dict):
        self.commits_list.append(commit_data)
        self._register_commit(commit_data)

    def add_mock_pipeline(self, pipeline_data: dict):
        new_pipeline_id = len(self.project.pipelines.list())
        pipeline = PipelineMock(
            mr=self,
            project=self.project,
            id=new_pipeline_id,
            sha=pipeline_data.get("sha", self.sha),
            status=pipeline_data.get("status", "success"))
        for job_data in pipeline_data["jobs"]:
            self.project.jobs.add_mock_job(
                JobMock(pipeline_ref=pipeline, name=job_data[0], status=job_data[1]))
        self.project.pipelines.add_mock_pipeline(pipeline)

    # Gitlab library merge request interface implementation.
    @property
    def sha(self):
        if not self.commits_list:
            return None
        return self.commits_list[-1]["sha"]

    def get_approvals_info(self) -> ApprovalsInfo:
        return ApprovalsInfo(
            is_approved=self.approvals.get().approved,
            approvals_left=self.approvals.get().approvals_left,
            approvals_required=self.approvals.get().approvals_required)

    @property
    def project_id(self):
        return self.project.id

    def pipelines(self):
        result = []
        for pipeline in sorted(self.project.pipelines.list(), key=lambda p: p.id):
            result.append({
                "created_at": pipeline.created_at,
                "id": pipeline.id,
                "project_id": pipeline.project_id,
                "sha": pipeline.sha,
                "status": pipeline.status,
                "web_url": pipeline.web_url,
            })
        # NOTE: Gitlab returns pipeline with the highest ID first
        return list(reversed(result))

    def rebase(self):
        self.mock_rebased = True

    def merge(self, **_):
        self.state = "merged"
        self.squash_commit_sha = self.commits_list[-1]["sha"]

    def changes(self):
        files = {}
        for c in self.commits_list:
            files = {**files, **c["files"]}
        return {
            "changes": [
                {
                    "new_path": name,
                    "deleted_file": descr.get("is_deleted", False),
                    "new_file": descr.get("is_new", False),
                    "renamed_file": descr.get("is_renamed", False),
                    "b_mode": descr.get("mode", "100644"),
                    "diff": descr.get("diff", ""),
                } for name, descr in files.items()],
            "changes_count": str(len(files)) + ("+" if self.mock_huge_mr else ""),
        }

    def save(self):
        users = self.project.users.list()

        for assignee_id in self.assignee_ids:
            assignee = [u for u in users if u.id == assignee_id][0]
            self.assignees.append({"username": assignee.username})

        for reviewer_id in self.reviewer_ids:
            reviewer = [u for u in users if u.id == reviewer_id][0]
            self.reviewers.append({"username": reviewer.username})

    def mock_comments(self):
        # Reverse notes list for the more convenient order (from the earliest note to the latest).
        return [n.body for n in reversed(self.notes.list())]

    def commits(self):
        return [
            self.mock_source_project.commits.get(c["sha"]) for c in reversed(self.commits_list)]

    def approve(self):
        self.approvals.get().approved_by.append({"user": {"username": BOT_USERNAME}})
        self.approvals.update({"approvals_left": self.approvals.get().approvals_left - 1})
