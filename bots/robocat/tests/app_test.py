## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import robocat.app as app_module


def _make_job_event(build_status, pipeline_id=12345, build_name="test-job"):
    return SimpleNamespace(data={
        "build_status": build_status,
        "pipeline_id": pipeline_id,
        "build_name": build_name,
        "build_id": 99,
        "project_id": 1,
        "build_stage": "test",
        "build_allow_failure": False,
    })


@pytest.fixture
def clear_queue():
    # Setup: drain any items left over from a previous test.
    while not app_module.mr_queue.empty():
        app_module.mr_queue.get_nowait()
    yield
    # Teardown: drain any items added by the current test so the next test starts clean.
    while not app_module.mr_queue.empty():
        app_module.mr_queue.get_nowait()


class TestJobEventFilter:
    @pytest.mark.parametrize("status", ["created", "pending", "running"])
    def test_non_terminal_statuses_not_queued(self, status, clear_queue):
        event = _make_job_event(status)
        asyncio.run(app_module.job_event(event))
        assert app_module.mr_queue.empty(), (
            f"Expected queue to be empty for status={status!r}, "
            f"but got {app_module.mr_queue.qsize()} item(s)")

    @pytest.mark.parametrize("status", ["created", "pending", "running"])
    def test_non_terminal_statuses_short_circuit_before_queue(self, status, clear_queue):
        event = _make_job_event(status)
        with patch.object(app_module.mr_queue, "put") as mock_put:
            asyncio.run(app_module.job_event(event))
        mock_put.assert_not_called()

    @pytest.mark.parametrize("status", ["success", "failed"])
    def test_terminal_statuses_are_queued(self, status, clear_queue):
        event = _make_job_event(status)
        asyncio.run(app_module.job_event(event))
        assert app_module.mr_queue.qsize() == 1, (
            f"Expected 1 queued item for status={status!r}, "
            f"but got {app_module.mr_queue.qsize()}")
        item = app_module.mr_queue.get_nowait()
        assert item.payload["status"] == status

    def test_only_terminal_events_queued_under_high_volume(self, clear_queue):
        # Simulate a busy pipeline: many non-terminal transitions per job, few terminal outcomes.
        events = (
            [_make_job_event("created", pipeline_id=i, build_name=f"job-{i}") for i in range(50)]
            + [_make_job_event("pending", pipeline_id=i, build_name=f"job-{i}") for i in range(50)]
            + [_make_job_event("running", pipeline_id=i, build_name=f"job-{i}") for i in range(50)]
            + [_make_job_event("success", pipeline_id=i, build_name=f"job-{i}") for i in range(10)]
            + [_make_job_event("failed", pipeline_id=i, build_name=f"job-{i}") for i in range(5)]
        )
        for event in events:
            asyncio.run(app_module.job_event(event))

        assert app_module.mr_queue.qsize() == 15, (
            f"Expected 15 queued items (10 success + 5 failed), "
            f"but got {app_module.mr_queue.qsize()}")
        queued_statuses = [app_module.mr_queue.get_nowait().payload["status"] for _ in range(15)]
        assert set(queued_statuses) == {"success", "failed"}
