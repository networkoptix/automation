## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import asdict, dataclass, field
import enum
import time
from typing import Optional, TypedDict, Union


class GitlabEventType(enum.Enum):
    merge_request = enum.auto()
    pipeline = enum.auto()
    job = enum.auto()
    comment = enum.auto()


class MrPreviousData(TypedDict):
    state: str


class GitlabMrRelatedEventData(TypedDict):
    mr_id: int
    mr_state: str


class GitlabMrEventData(GitlabMrRelatedEventData):
    mr_previous_data: Optional[MrPreviousData]
    code_changed: Optional[bool]


class GitlabPipelineEventData(GitlabMrRelatedEventData):
    raw_pipeline_status: str
    pipeline_id: str


class GitlabCommentEventData(GitlabMrRelatedEventData):
    added_comment: str


class GitlabJobEventData(TypedDict):
    job_id: str
    pipeline_id: str
    project_id: str
    name: str
    status: str
    stage: str
    allow_failure: bool


@dataclass(order=True)
class GitlabEventData:
    payload: Union[GitlabMrRelatedEventData, GitlabJobEventData] = field(compare=False)
    event_type: GitlabEventType = field(compare=False)
    # Remember the time when the event was received - used for profiling.
    receive_time: float = field(compare=False, default_factory=time.time)
    # Lower value means higher priority, hence older events are processed first.
    priority: int = field(default_factory=time.time_ns)

    def as_string_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}
