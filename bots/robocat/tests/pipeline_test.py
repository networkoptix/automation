## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from automation_tools.tests.gitlab_constants import DEFAULT_COMMIT
from robocat.pipeline import JobStatus, Pipeline
from tests.fixtures import *


class TestPipeline:
    @pytest.mark.parametrize(("mr_state", "expected_status"), [
        [{
            "pipelines_list": [(
                DEFAULT_COMMIT,
                "manual",
                [("test:no-bot-start", "manual", "")],
            )],
        }, JobStatus.manual,
        ],
        [{
            "pipelines_list": [(
                DEFAULT_COMMIT,
                "manual",
                [("test", "failed", "")],
            )],
        }, JobStatus.failed,
        ],
        [{
            "pipelines_list": [(
                DEFAULT_COMMIT,
                "manual",
                [("test", "manual", "")],
            )],
        }, JobStatus.running,
        ],
        [{
            "pipelines_list": [(
                DEFAULT_COMMIT,
                "manual",
                [("test:no-bot-start", "running", "")],
            )],
        }, JobStatus.running,
        ],
    ])
    def test_run_pipeline(self, mr_manager, expected_status):
        pipeline = Pipeline(mr_manager._get_project()._gitlab_project.pipelines.list()[0])
        pipeline.play()
        assert pipeline.jobs()[-1].status == expected_status
